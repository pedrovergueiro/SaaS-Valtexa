"""Ciclo de vida da missão: planejar, autorizar, despachar, retomar, encerrar.

Toda transição passa por :func:`transition`, que recusa o que não está em
:data:`ALLOWED_TRANSITIONS`. Uma máquina de estados explícita evita a classe de
bug mais cara aqui: um caminho de código que "conserta" o estado no meio de um
tratamento de erro e leva a missão a um estado que ninguém previu, com o robô no
ar.

A retomada é o ponto sutil. Um rover que volta para recarregar precisa continuar
de onde parou; refazer a lavoura inteira torna o produto inviável em qualquer
propriedade acima de algumas dezenas de hectares. Por isso a cobertura é
quebrada em segmentos e cada segmento concluído grava um checkpoint.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from valtexa.config import settings
from valtexa.models import (
    ActorType,
    Device,
    Farm,
    Field,
    Mission,
    MissionCheckpoint,
    MissionKind,
    MissionSegment,
    MissionState,
    SafetyVerdict,
    SegmentState,
    SubjectType,
    as_utc,
)
from valtexa.security import signing
from valtexa.services import audit, energy, events, geo, safety_engine
from valtexa.services.hal import Capabilities, capabilities_of

ALLOWED_TRANSITIONS: dict[MissionState, frozenset[MissionState]] = {
    MissionState.DRAFT: frozenset({MissionState.PENDING_SAFETY, MissionState.ABORTED}),
    MissionState.PENDING_SAFETY: frozenset(
        {MissionState.AUTHORIZED, MissionState.BLOCKED, MissionState.ABORTED}
    ),
    # BLOCKED não é terminal: corrigido o impedimento, a missão volta para
    # avaliação. Obrigar a recriar do zero faria o operador perder o histórico
    # de por que ela foi bloqueada.
    MissionState.BLOCKED: frozenset({MissionState.PENDING_SAFETY, MissionState.ABORTED}),
    MissionState.AUTHORIZED: frozenset(
        {MissionState.DISPATCHED, MissionState.ABORTED, MissionState.EXPIRED}
    ),
    MissionState.DISPATCHED: frozenset(
        {MissionState.RUNNING, MissionState.ABORTED, MissionState.EXPIRED}
    ),
    MissionState.RUNNING: frozenset(
        {
            MissionState.PAUSED,
            MissionState.PAUSED_FOR_RECHARGE,
            MissionState.COMPLETED,
            MissionState.ABORTED,
        }
    ),
    MissionState.PAUSED: frozenset({MissionState.READY_TO_RESUME, MissionState.ABORTED}),
    MissionState.PAUSED_FOR_RECHARGE: frozenset(
        {MissionState.READY_TO_RESUME, MissionState.ABORTED}
    ),
    MissionState.READY_TO_RESUME: frozenset(
        {MissionState.RUNNING, MissionState.ABORTED, MissionState.EXPIRED}
    ),
    MissionState.COMPLETED: frozenset(),
    MissionState.ABORTED: frozenset(),
    MissionState.EXPIRED: frozenset(),
}

TERMINAL_STATES = frozenset(
    {MissionState.COMPLETED, MissionState.ABORTED, MissionState.EXPIRED}
)

ACTIVE_STATES = frozenset(
    {
        MissionState.DISPATCHED,
        MissionState.RUNNING,
        MissionState.PAUSED,
        MissionState.PAUSED_FOR_RECHARGE,
        MissionState.READY_TO_RESUME,
    }
)


class MissionStateError(RuntimeError):
    """Transição não permitida pela máquina de estados."""


class MissionNotAuthorizedError(RuntimeError):
    """Tentativa de despachar algo que a segurança não aprovou."""


def transition(
    session: Session,
    mission: Mission,
    target: MissionState,
    *,
    reason: str | None = None,
    actor_type: ActorType = ActorType.SYSTEM,
    actor_id: str | None = None,
) -> Mission:
    """Move a missão, recusando o que a máquina de estados não permite."""
    allowed = ALLOWED_TRANSITIONS.get(mission.state, frozenset())
    if target not in allowed:
        raise MissionStateError(
            f"Missão {mission.id}: transição {mission.state.value!r} → {target.value!r} "
            f"não permitida. Permitidas: {sorted(state.value for state in allowed) or 'nenhuma'}."
        )

    previous = mission.state
    mission.state = target
    _stamp(mission, target, reason)

    audit.record(
        session,
        tenant_id=mission.tenant_id,
        action="mission.transition",
        subject_type=SubjectType.MISSION,
        subject_id=mission.id,
        actor_type=actor_type,
        actor_id=actor_id,
        old_state=previous.value,
        new_state=target.value,
        reason=reason,
    )
    _publish_for(session, mission, target)
    _sync_device(session, mission, target)
    return mission


def plan_coverage(
    session: Session, mission: Mission, *, swath_m: float | None = None
) -> list[MissionSegment]:
    """Quebra a área da missão em segmentos de vaivém.

    A largura da faixa vem do descritor de capacidades do hardware, não de uma
    constante: um rover com câmera mais aberta cobre mais por passada, e o plano
    tem que refletir isso sem alteração de código.
    """
    device = session.get(Device, mission.device_id)
    capabilities = capabilities_of(device.capabilities if device else {})
    # Precedência: o que o operador pediu, depois o que o hardware declara. Uma
    # constante aqui obrigaria a alterar código para planejar com outra câmera.
    width = swath_m or float((mission.plan or {}).get("swath_m") or 0) or capabilities.swath_m

    field_row = session.get(Field, mission.field_id)
    azimuth = _row_azimuth(mission.plan or {}, field_row)

    legs = geo.boustrophedon(mission.target_polygon, width, azimuth_deg=azimuth)
    segments = [
        MissionSegment(
            mission_id=mission.id,
            index=index,
            path=[list(point) for point in leg],
            state=SegmentState.PENDING,
            estimated_energy_percent=_leg_energy_percent(leg, capabilities),
        )
        for index, leg in enumerate(legs)
    ]
    session.add_all(segments)

    mission.waypoints = [list(point) for leg in legs for point in leg]
    mission.plan = {
        **(mission.plan or {}),
        "swath_m": width,
        "row_azimuth_deg": azimuth,
        "segments": len(segments),
        "path_length_m": round(geo.path_length_m(mission.waypoints), 1),
        "area_ha": round(geo.area_ha(mission.target_polygon), 3),
    }
    return segments


def _leg_energy_percent(leg: list, capabilities: Capabilities) -> float:
    """Estimativa grosseira do custo energético de uma passada, em % de bateria.

    Comprimento dividido pela velocidade de cruzeiro, sobre a autonomia
    declarada. Ignora vento, terreno e o consumo dos sensores, então serve para
    ordenar segmentos e prever quantas recargas a missão vai exigir — não para
    decidir retorno. Essa decisão é do robô, com a bateria real na mão, e está
    em :mod:`valtexa.services.energy`.
    """
    speed = max(0.1, capabilities.cruise_speed_ms)
    endurance_s = max(60.0, capabilities.endurance_minutes * 60.0)
    return round(geo.path_length_m(leg) / speed / endurance_s * 100.0, 3)


def submit_for_safety(
    session: Session, mission: Mission, *, actor_id: str | None = None
) -> Mission:
    """Manda a missão para avaliação de segurança."""
    if mission.state is not MissionState.PENDING_SAFETY:
        transition(
            session,
            mission,
            MissionState.PENDING_SAFETY,
            reason="Enviada para avaliação de segurança.",
            actor_type=ActorType.USER if actor_id else ActorType.SYSTEM,
            actor_id=actor_id,
        )
    return mission


def authorize(
    session: Session,
    mission: Mission,
    *,
    actor_id: str | None = None,
    wind_ms: float | None = None,
) -> tuple[Mission, SafetyVerdict]:
    """Avalia a segurança e, se aprovada, autoriza e assina a missão.

    A assinatura só existe depois do parecer favorável. Missão bloqueada não tem
    assinatura, então nem por engano um comando dela é aceito pelo robô.
    """
    submit_for_safety(session, mission, actor_id=actor_id)

    evaluation = safety_engine.evaluate_mission(
        session, mission, wind_ms=wind_ms, evaluated_by=actor_id
    )
    session.add(evaluation)
    mission.safety_status = evaluation.verdict
    mission.safety_reason = evaluation.blocked_reason

    if evaluation.verdict is SafetyVerdict.BLOCKED:
        transition(
            session,
            mission,
            MissionState.BLOCKED,
            reason=evaluation.blocked_reason,
            actor_type=ActorType.SYSTEM,
        )
        events.publish(
            session,
            events.SAFETY_BLOCKED,
            tenant_id=mission.tenant_id,
            subject_type=SubjectType.MISSION,
            subject_id=mission.id,
            payload={"code": evaluation.blocked_code, "reason": evaluation.blocked_reason},
        )
        return mission, evaluation.verdict

    now = datetime.now(UTC)
    mission.authorized_at = now
    mission.expires_at = now + timedelta(seconds=settings.command_ttl_seconds)
    mission.energy_policy = _energy_policy(session, mission).as_dict()
    mission.offline_policy = default_offline_policy(mission.kind)

    transition(
        session,
        mission,
        MissionState.AUTHORIZED,
        reason="Aprovada pela camada de segurança.",
        actor_type=ActorType.USER if actor_id else ActorType.SYSTEM,
        actor_id=actor_id,
    )
    events.publish(
        session,
        events.SAFETY_APPROVED,
        tenant_id=mission.tenant_id,
        subject_type=SubjectType.MISSION,
        subject_id=mission.id,
    )
    return mission, evaluation.verdict


def dispatch(session: Session, mission: Mission, *, actor_id: str | None = None) -> dict:
    """Assina o comando e marca a missão como despachada.

    Devolve o envelope assinado — é literalmente o que vai pelo rádio.
    """
    if mission.state is not MissionState.AUTHORIZED:
        raise MissionNotAuthorizedError(
            f"Missão em {mission.state.value!r}: só AUTHORIZED pode ser despachada."
        )
    if mission.safety_status is not SafetyVerdict.SAFE_TO_EXECUTE:
        raise MissionNotAuthorizedError("Missão sem parecer favorável de segurança.")

    mission.command_sequence += 1
    envelope = signing.command_envelope(
        command="mission.execute",
        device_id=mission.device_id,
        body=mission_command_body(session, mission),
        sequence=mission.command_sequence,
        ttl_seconds=_remaining_ttl(mission),
    )
    signed = signing.sign_command(envelope)
    _store_command(mission, signed)

    transition(
        session,
        mission,
        MissionState.DISPATCHED,
        reason="Comando assinado e enviado ao dispositivo.",
        actor_type=ActorType.USER if actor_id else ActorType.SYSTEM,
        actor_id=actor_id,
    )
    return signed.as_dict()


def _store_command(mission: Mission, signed: signing.SignedCommand) -> None:
    """Guarda o envelope e a assinatura exatamente como foram emitidos."""
    mission.command_payload = signed.payload
    mission.signature = signed.signature
    mission.signing_key_id = signed.key_id
    mission.nonce = signed.payload["nonce"]


def rebuild_envelope(mission: Mission) -> dict:
    """Devolve o comando assinado tal como foi emitido.

    Reassinar a cada leitura seria mais simples e estaria errado: o envelope
    carrega nonce e horário de emissão, então uma nova assinatura seria um
    comando *diferente*. O robô que perdeu o enlace e rebuscou receberia dois
    comandos válidos para a mesma missão — e a proteção contra repetição, que
    depende de o nonce ser único por comando, deixaria de significar alguma
    coisa.
    """
    if not mission.signature or not mission.command_payload:
        raise MissionNotAuthorizedError(
            f"Missão {mission.id} não tem comando assinado para entregar."
        )
    return signing.SignedCommand(
        payload=mission.command_payload,
        signature=mission.signature,
        key_id=mission.signing_key_id or "",
    ).as_dict()


def mission_command_body(session: Session, mission: Mission) -> dict:
    """O corpo do comando que o robô recebe.

    Contém tudo que ele precisa para operar **sem consultar a nuvem** durante a
    missão: a área, a rota, o que fazer com pouca bateria e o que fazer se o
    enlace cair.
    """
    remaining = pending_segments(session, mission)
    return {
        "mission_id": mission.id,
        "kind": mission.kind.value,
        "field_id": mission.field_id,
        "target_polygon": mission.target_polygon,
        "segments": [
            {"index": segment.index, "path": segment.path} for segment in remaining
        ],
        "plan": mission.plan,
        "energy_policy": mission.energy_policy,
        "offline_policy": mission.offline_policy,
        "application": (
            {
                "product_id": mission.product_id,
                "batch_id": mission.product_batch_id,
                "tank_id": mission.tank_id,
                "rate_l_ha": mission.authorized_rate_l_ha,
                "max_quantity_l": mission.authorized_quantity_l,
            }
            if mission.is_spray
            else None
        ),
    }


def pending_segments(session: Session, mission: Mission) -> list[MissionSegment]:
    """Os segmentos que ainda faltam, na ordem."""
    return list(
        session.scalars(
            select(MissionSegment)
            .where(
                MissionSegment.mission_id == mission.id,
                MissionSegment.state.in_([SegmentState.PENDING, SegmentState.IN_PROGRESS]),
            )
            .order_by(MissionSegment.index)
        )
    )


def complete_segment(
    session: Session,
    mission: Mission,
    index: int,
    *,
    lat: float | None = None,
    lon: float | None = None,
    battery_percent: float | None = None,
) -> MissionCheckpoint:
    """Marca um segmento como concluído e grava o checkpoint.

    O checkpoint é gravado a cada segmento, e não só na pausa, porque a pausa
    nem sempre é ordenada: uma queda de energia ou de enlace no meio da faixa
    não avisa antes.
    """
    segment = session.scalars(
        select(MissionSegment).where(
            MissionSegment.mission_id == mission.id, MissionSegment.index == index
        )
    ).first()
    if segment is not None:
        segment.state = SegmentState.DONE
        segment.completed_at = datetime.now(UTC)
        # A sessão roda com ``autoflush=False``, então sem este flush a consulta
        # logo abaixo ainda enxergaria o segmento como pendente — e o checkpoint
        # gravaria como restante justamente a faixa que acabou de ser concluída.
        session.flush()

    remaining = [item.index for item in pending_segments(session, mission)]
    checkpoint = MissionCheckpoint(
        mission_id=mission.id,
        last_completed_segment=index,
        remaining_segments=remaining,
        last_lat=lat,
        last_lon=lon,
        battery_percent=battery_percent,
        reason="segment_completed",
    )
    session.add(checkpoint)
    return checkpoint


def latest_checkpoint(session: Session, mission: Mission) -> MissionCheckpoint | None:
    return session.scalars(
        select(MissionCheckpoint)
        .where(MissionCheckpoint.mission_id == mission.id)
        .order_by(MissionCheckpoint.created_at.desc())
        .limit(1)
    ).first()


def pause_for_recharge(
    session: Session,
    mission: Mission,
    *,
    lat: float | None = None,
    lon: float | None = None,
    battery_percent: float | None = None,
) -> Mission:
    """Pausa a missão para recarga, guardando onde parou."""
    remaining = [segment.index for segment in pending_segments(session, mission)]
    session.add(
        MissionCheckpoint(
            mission_id=mission.id,
            last_completed_segment=(min(remaining) - 1 if remaining else -1),
            remaining_segments=remaining,
            last_lat=lat,
            last_lon=lon,
            battery_percent=battery_percent,
            reason="low_battery",
        )
    )
    return transition(
        session,
        mission,
        MissionState.PAUSED_FOR_RECHARGE,
        reason=f"Bateria em {battery_percent}%: retorno à base para recarga.",
        actor_type=ActorType.DEVICE,
        actor_id=mission.device_id,
    )


def mark_ready_to_resume(session: Session, mission: Mission) -> Mission:
    """Recarga concluída: a missão pode continuar."""
    return transition(
        session,
        mission,
        MissionState.READY_TO_RESUME,
        reason="Recarga concluída.",
        actor_type=ActorType.DEVICE,
        actor_id=mission.device_id,
    )


def resume(session: Session, mission: Mission, *, actor_id: str | None = None) -> dict:
    """Retoma a missão do checkpoint, com um comando novo e assinado.

    A validade é renovada aqui. Reaproveitar a assinatura de horas atrás
    contornaria o prazo de expiração, que é justamente o que impede executar
    hoje uma autorização de ontem.
    """
    if mission.state is not MissionState.READY_TO_RESUME:
        raise MissionStateError(
            f"Missão em {mission.state.value!r}: só READY_TO_RESUME pode ser retomada."
        )

    mission.expires_at = datetime.now(UTC) + timedelta(seconds=settings.command_ttl_seconds)
    mission.command_sequence += 1
    envelope = signing.command_envelope(
        command="mission.resume",
        device_id=mission.device_id,
        body=mission_command_body(session, mission),
        sequence=mission.command_sequence,
        ttl_seconds=_remaining_ttl(mission),
    )
    signed = signing.sign_command(envelope)
    _store_command(mission, signed)

    transition(
        session,
        mission,
        MissionState.RUNNING,
        reason="Retomada a partir do último checkpoint.",
        actor_type=ActorType.USER if actor_id else ActorType.SYSTEM,
        actor_id=actor_id,
    )
    return signed.as_dict()


def abort(
    session: Session,
    mission: Mission,
    reason: str,
    *,
    actor_type: ActorType = ActorType.USER,
    actor_id: str | None = None,
) -> Mission:
    """Aborta a missão. Abortar nunca falha por estado, salvo se já terminou."""
    if mission.state in TERMINAL_STATES:
        return mission
    mission.abort_reason = reason
    return transition(
        session,
        mission,
        MissionState.ABORTED,
        reason=reason,
        actor_type=actor_type,
        actor_id=actor_id,
    )


EXPIRABLE_STATES = frozenset(
    {MissionState.AUTHORIZED, MissionState.DISPATCHED, MissionState.READY_TO_RESUME}
)
"""Estados em que uma missão pode vencer.

``RUNNING`` fica de fora de propósito: a validade impede *começar* uma missão
autorizada há muito tempo, não interromper uma que já está em execução. Parar um
robô no meio da faixa é decisão do operador (abortar), não do relógio.
"""


def expire_stale(session: Session, *, now: datetime | None = None) -> int:
    """Vence as missões cuja validade passou antes da execução. Devolve quantas.

    Sem isto, uma missão despachada para um robô que nunca a buscou ficaria
    "despachada" para sempre — e o robô, preso a ela por ``active_mission_id``,
    nunca mais receberia outra.
    """
    moment = now or datetime.now(UTC)
    stale = list(
        session.scalars(
            select(Mission).where(
                Mission.state.in_(EXPIRABLE_STATES),
                Mission.expires_at.is_not(None),
                Mission.expires_at < moment,
            )
        )
    )
    for mission in stale:
        transition(
            session,
            mission,
            MissionState.EXPIRED,
            reason="Validade do comando vencida antes da execução.",
        )
    return len(stale)


def _row_azimuth(plan: dict, field_row: Field | None) -> float:
    """Direção das linhas: a do plano, depois a do talhão, depois leste-oeste."""
    if plan.get("row_azimuth_deg") is not None:
        return float(plan["row_azimuth_deg"])
    if field_row is not None and field_row.row_azimuth_deg is not None:
        return float(field_row.row_azimuth_deg)
    return 90.0


def default_offline_policy(kind: MissionKind) -> dict:
    """O que o robô faz sozinho quando a nuvem some.

    Para pulverização a política é agressiva: sem enlace, fecha o bico. A
    aplicação é a única ação irreversível do sistema, e é a última que se deixa
    seguir às cegas.
    """
    if kind is MissionKind.SPRAY:
        return {
            "grace_seconds": 30,
            "on_link_loss": "pause",
            "stop_application": True,
            "after_grace": "return_to_base",
        }
    return {
        "grace_seconds": 300,
        "on_link_loss": "continue",
        "stop_application": False,
        "after_grace": "continue",
    }


def _energy_policy(session: Session, mission: Mission) -> energy.EnergyPolicy:
    device = session.get(Device, mission.device_id)
    farm = session.get(Farm, mission.farm_id)
    return energy.policy_for(
        capabilities_of(device.capabilities if device else {}),
        mission.target_polygon,
        farm.base_lat if farm else None,
        farm.base_lon if farm else None,
    )


def _remaining_ttl(mission: Mission) -> int:
    """Segundos restantes de validade, nunca menos de um minuto."""
    expires_at = as_utc(mission.expires_at)
    if expires_at is None:
        return settings.command_ttl_seconds
    return max(60, int((expires_at - datetime.now(UTC)).total_seconds()))


def _stamp(mission: Mission, target: MissionState, reason: str | None) -> None:
    now = datetime.now(UTC)
    if target is MissionState.DISPATCHED:
        mission.dispatched_at = now
    elif target is MissionState.RUNNING and mission.started_at is None:
        mission.started_at = now
    elif target in TERMINAL_STATES:
        mission.finished_at = now
        if target is MissionState.ABORTED and reason:
            mission.abort_reason = reason


_EVENT_FOR_STATE = {
    MissionState.AUTHORIZED: events.MISSION_AUTHORIZED,
    MissionState.DISPATCHED: events.MISSION_DISPATCHED,
    MissionState.RUNNING: events.MISSION_STARTED,
    MissionState.PAUSED: events.MISSION_PAUSED,
    MissionState.PAUSED_FOR_RECHARGE: events.MISSION_PAUSED,
    MissionState.READY_TO_RESUME: events.MISSION_RESUMED,
    MissionState.COMPLETED: events.MISSION_COMPLETED,
    MissionState.ABORTED: events.MISSION_ABORTED,
    MissionState.EXPIRED: events.MISSION_EXPIRED,
}


def _publish_for(session: Session, mission: Mission, target: MissionState) -> None:
    name = _EVENT_FOR_STATE.get(target)
    if name is None:
        return
    events.publish(
        session,
        name,
        tenant_id=mission.tenant_id,
        subject_type=SubjectType.MISSION,
        subject_id=mission.id,
        payload={"state": target.value, "device_id": mission.device_id},
    )


def _sync_device(session: Session, mission: Mission, target: MissionState) -> None:
    """Mantém ``Device.active_mission_id`` coerente com o estado da missão.

    É esse campo que impede duas missões simultâneas no mesmo robô; deixá-lo
    apontando para uma missão encerrada travaria o dispositivo para sempre.
    """
    device = session.get(Device, mission.device_id)
    if device is None:
        return
    if target in ACTIVE_STATES:
        device.active_mission_id = mission.id
    elif target in TERMINAL_STATES and device.active_mission_id == mission.id:
        device.active_mission_id = None


def create_mission(
    session: Session,
    *,
    tenant_id: str,
    kind: MissionKind,
    field_row: Field,
    device: Device,
    target_polygon: list | None = None,
    created_by: str | None = None,
    **extra: object,
) -> Mission:
    """Cria a missão e planeja a cobertura numa tacada.

    Sem polígono explícito, a área é o talhão **menos a margem de segurança** —
    e não o talhão inteiro. A distinção não é detalhe: a cerca virtual exige que
    a área da missão caiba dentro do limite com folga, então uma missão criada
    sobre a borda exata do talhão seria bloqueada por construção, sempre. A área
    operável é o miolo.
    """
    polygon = target_polygon or [
        list(point) for point in geo.shrink(field_row.boundary, settings.geofence_margin_m)
    ]
    mission = Mission(
        tenant_id=tenant_id,
        kind=kind,
        farm_id=field_row.farm_id,
        field_id=field_row.id,
        device_id=device.id,
        target_polygon=polygon,
        created_by=created_by,
        state=MissionState.DRAFT,
        **extra,
    )
    session.add(mission)
    session.flush()  # precisa do id para os segmentos
    plan_coverage(session, mission)

    audit.record(
        session,
        tenant_id=tenant_id,
        action="mission.created",
        subject_type=SubjectType.MISSION,
        subject_id=mission.id,
        actor_type=ActorType.USER if created_by else ActorType.SYSTEM,
        actor_id=created_by,
        new_state=MissionState.DRAFT.value,
    )
    events.publish(
        session,
        events.MISSION_CREATED,
        tenant_id=tenant_id,
        subject_type=SubjectType.MISSION,
        subject_id=mission.id,
        payload={"kind": kind.value, "device_id": device.id},
    )
    return mission
