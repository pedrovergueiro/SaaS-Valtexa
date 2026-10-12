"""Missões: criar, aprovar, autorizar, despachar, abortar.

A separação de responsabilidades está nas dependências de cada rota e é a
espinha do produto:

* criar uma missão — ``mission:create``;
* **aprovar uma pulverização** — ``mission:approve_application``, só o agrônomo;
* autorizar (rodar a segurança) — ``mission:dispatch``;
* despachar ao robô — ``mission:dispatch``;
* abortar — quase todo mundo, porque parar nunca pode depender de permissão rara.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from valtexa.api.deps import Principal, get_scoped, require, scoped
from valtexa.db import get_session
from valtexa.models import (
    ActorType,
    Device,
    Field,
    Mission,
    MissionKind,
    MissionSegment,
    MissionState,
    SafetyEvaluation,
    SegmentState,
    SubjectType,
)
from valtexa.schemas import (
    AbortRequest,
    MissionApproval,
    MissionCreate,
    MissionOut,
    MissionSegmentOut,
    RouteEdit,
    RouteReplan,
    SafetyCheckOut,
    SafetyEvaluationOut,
    SignedCommandOut,
)
from valtexa.security import rbac
from valtexa.services import (
    audit,
    geo,
    missao_resultado,
    mission_manager,
    plans,
    safety_engine,
    visao_operacional,
)

router = APIRouter(tags=["missões"])


@router.get("/missions", response_model=list[MissionOut], summary="Lista missões")
def list_missions(
    state: MissionState | None = None,
    device_id: str | None = None,
    field_id: str | None = None,
    limit: int = 100,
    principal: Principal = Depends(require(rbac.MISSION_READ)),
    session: Session = Depends(get_session),
) -> list[MissionOut]:
    statement = scoped(
        select(Mission).order_by(Mission.created_at.desc()).limit(min(limit, 500)),
        Mission,
        principal,
    )
    if state is not None:
        statement = statement.where(Mission.state == state)
    if device_id is not None:
        statement = statement.where(Mission.device_id == device_id)
    if field_id is not None:
        statement = statement.where(Mission.field_id == field_id)
    return [_mission_out(session, row) for row in session.scalars(statement)]


@router.post(
    "/missions",
    response_model=MissionOut,
    status_code=status.HTTP_201_CREATED,
    summary="Cria uma missão",
)
def create_mission(
    payload: MissionCreate,
    principal: Principal = Depends(require(rbac.MISSION_CREATE)),
    session: Session = Depends(get_session),
) -> MissionOut:
    """Cria a missão em rascunho e planeja a cobertura.

    Nasce em ``DRAFT``, sem assinatura e sem valer nada no mundo físico. O
    caminho até o robô passa obrigatoriamente por aprovação (se for
    pulverização) e pela camada de segurança.
    """
    field_row = get_scoped(session, Field, payload.field_id, principal)
    device = get_scoped(session, Device, payload.device_id, principal)

    # Sem polígono, create_mission usa o talhão menos a margem de segurança.
    # Mandar a borda exata daqui faria a cerca virtual bloquear toda missão
    # criada pela API — a borda do talhão nunca cabe dentro de si menos a margem.
    polygon = payload.target_polygon
    if polygon is not None:
        try:
            geo.as_points(polygon)
        except geo.InvalidPolygonError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc

    if payload.kind is MissionKind.SPRAY and not payload.product_id:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Missão de pulverização exige produto, lote, tanque e dose.",
        )
    plans.exigir(session, principal.tenant_id, "missions_month")

    mission = mission_manager.create_mission(
        session,
        tenant_id=principal.tenant_id,
        kind=payload.kind,
        field_row=field_row,
        device=device,
        target_polygon=polygon,
        created_by=principal.user_id,
        zone_id=payload.zone_id,
        plan=payload.plan,
        product_id=payload.product_id,
        product_batch_id=payload.product_batch_id,
        tank_id=payload.tank_id,
        authorized_rate_l_ha=payload.authorized_rate_l_ha,
        authorized_quantity_l=payload.authorized_quantity_l,
        decision_id=payload.decision_id,
    )
    plans.registrar_missao(session, principal.tenant_id)
    session.commit()
    return _mission_out(session, mission)


@router.get("/missions/{mission_id}", response_model=MissionOut, summary="Uma missão")
def get_mission(
    mission_id: str,
    principal: Principal = Depends(require(rbac.MISSION_READ)),
    session: Session = Depends(get_session),
) -> MissionOut:
    return _mission_out(session, get_scoped(session, Mission, mission_id, principal))


@router.get(
    "/missions/{mission_id}/segments",
    response_model=list[MissionSegmentOut],
    summary="Segmentos da cobertura",
)
def list_segments(
    mission_id: str,
    principal: Principal = Depends(require(rbac.MISSION_READ)),
    session: Session = Depends(get_session),
) -> list[MissionSegmentOut]:
    get_scoped(session, Mission, mission_id, principal)
    rows = session.scalars(
        select(MissionSegment)
        .where(MissionSegment.mission_id == mission_id)
        .order_by(MissionSegment.index)
    )
    return [
        MissionSegmentOut(
            index=row.index,
            state=row.state.value,
            path=row.path,
            estimated_energy_percent=row.estimated_energy_percent,
        )
        for row in rows
    ]


@router.post(
    "/missions/{mission_id}/approve",
    response_model=MissionOut,
    summary="Aprovação do agrônomo para pulverizar",
)
def approve(
    mission_id: str,
    payload: MissionApproval,
    principal: Principal = Depends(require(rbac.MISSION_APPROVE_APPLICATION)),
    session: Session = Depends(get_session),
) -> MissionOut:
    """Registra quem assume a responsabilidade técnica pela aplicação.

    É o ponto em que uma recomendação de software vira produto químico no ar.
    Nenhum papel automático, nenhuma integração e nenhuma IA chega aqui — a
    capacidade é exclusiva do agrônomo, e o safety engine reconfere o papel na
    hora de autorizar, porque entre a assinatura e o voo o papel pode ter sido
    revogado.
    """
    mission = get_scoped(session, Mission, mission_id, principal)
    if mission.kind is not MissionKind.SPRAY:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Só missão de pulverização precisa de aprovação."
        )
    if not payload.confirm:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Confirmação explícita é obrigatória.")
    if mission.state in mission_manager.TERMINAL_STATES:
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"Missão já encerrada em {mission.state.value!r}."
        )

    mission.approved_by = principal.user_id
    mission.approved_at = datetime.now(UTC)
    audit.record(
        session,
        tenant_id=principal.tenant_id,
        action="mission.approved",
        subject_type=SubjectType.MISSION,
        subject_id=mission.id,
        actor_type=ActorType.USER,
        actor_id=principal.user_id,
        actor_label=principal.user.email,
        reason=payload.notes,
        payload={
            "product_id": mission.product_id,
            "rate_l_ha": mission.authorized_rate_l_ha,
            "role": principal.role.value,
        },
    )
    session.commit()
    return _mission_out(session, mission)


@router.post(
    "/missions/{mission_id}/authorize",
    response_model=SafetyEvaluationOut,
    summary="Roda a camada de segurança",
)
def authorize(
    mission_id: str,
    wind_ms: float | None = None,
    principal: Principal = Depends(require(rbac.MISSION_DISPATCH)),
    session: Session = Depends(get_session),
) -> SafetyEvaluationOut:
    """Submete a missão à camada de segurança.

    Devolve o parecer completo — inclusive as verificações que passaram. Quando
    bloqueia, o operador vê de uma vez tudo que falta, em vez de descobrir um
    impedimento por tentativa.
    """
    mission = get_scoped(session, Mission, mission_id, principal)
    mission_manager.authorize(session, mission, actor_id=principal.user_id, wind_ms=wind_ms)
    session.commit()

    evaluation = session.scalars(
        select(SafetyEvaluation)
        .where(
            SafetyEvaluation.subject_type == SubjectType.MISSION,
            SafetyEvaluation.subject_id == mission.id,
        )
        .order_by(SafetyEvaluation.created_at.desc())
        .limit(1)
    ).first()
    return _evaluation_out(evaluation)


@router.post(
    "/missions/{mission_id}/dispatch",
    response_model=SignedCommandOut,
    summary="Assina e despacha ao robô",
)
def dispatch(
    mission_id: str,
    principal: Principal = Depends(require(rbac.MISSION_DISPATCH)),
    session: Session = Depends(get_session),
) -> SignedCommandOut:
    """Emite o comando assinado.

    Devolvido aqui para inspeção e para o simulador; o robô o busca em
    ``GET /v1/device/missions/current``.
    """
    mission = get_scoped(session, Mission, mission_id, principal)
    try:
        envelope = mission_manager.dispatch(session, mission, actor_id=principal.user_id)
    except mission_manager.MissionNotAuthorizedError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    session.commit()
    return SignedCommandOut(**envelope)


@router.post(
    "/missions/{mission_id}/resume", response_model=SignedCommandOut, summary="Retoma do checkpoint"
)
def resume(
    mission_id: str,
    principal: Principal = Depends(require(rbac.MISSION_DISPATCH)),
    session: Session = Depends(get_session),
) -> SignedCommandOut:
    """Emite um comando novo com os segmentos que faltam."""
    mission = get_scoped(session, Mission, mission_id, principal)
    try:
        envelope = mission_manager.resume(session, mission, actor_id=principal.user_id)
    except mission_manager.MissionStateError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    session.commit()
    return SignedCommandOut(**envelope)


@router.patch(
    "/missions/{mission_id}/route",
    response_model=MissionOut,
    summary="Corrige a rota à mão",
)
def edit_route(
    mission_id: str,
    payload: RouteEdit,
    principal: Principal = Depends(require(rbac.MISSION_CREATE)),
    session: Session = Depends(get_session),
) -> MissionOut:
    """Substitui o percurso pelo que o operador desenhou no mapa.

    Existe porque o planejador não conhece o terreno todo. Ele sabe a geometria
    do talhão e o que a leitura de imagem viu; não sabe que aquela cabeceira
    atola em maio, nem que o portão do fundo está trancado desde a safra
    passada. Quem sabe é quem opera — e, até aqui, esse conhecimento não tinha
    por onde entrar: a validação humana era aprovar ou recusar, nunca corrigir.

    O que o operador **não** consegue fazer por aqui é furar a cerca virtual.
    Uma passada que saia da área da missão ou atravesse obstáculo
    intransponível é recusada com o número da passada. Ele conhece o terreno
    melhor que o planejador; não conhece melhor que o limite do talhão, que é
    contrato, nem que a mata, que é física.
    """
    mission = get_scoped(session, Mission, mission_id, principal)
    try:
        mission_manager.replace_route(
            session, mission, payload.legs, actor_id=principal.user_id, reason=payload.reason
        )
    except mission_manager.RouteNotEditableError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except mission_manager.InvalidRouteError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    session.commit()
    return _mission_out(session, mission)


@router.post(
    "/missions/{mission_id}/replan",
    response_model=MissionOut,
    summary="Recalcula a rota com premissas novas",
)
def replan(
    mission_id: str,
    payload: RouteReplan,
    principal: Principal = Depends(require(rbac.MISSION_CREATE)),
    session: Session = Depends(get_session),
) -> MissionOut:
    """Refaz a rota pela máquina, e não à mão.

    Dois usos, e os dois aparecem no mesmo dia de trabalho. O primeiro é mudar
    premissa: a câmera é outra, as linhas correm noutro ângulo, o obstáculo
    precisa de mais folga. O segundo é mais comum e menos óbvio — **aplicar uma
    leitura de terreno que chegou depois**. A missão nasce antes de alguém rodar
    o encaixe de contorno, então a rota original não contorna nada; replanejar
    sem nenhum parâmetro é o que faz a mata entrar na conta.
    """
    mission = get_scoped(session, Mission, mission_id, principal)
    try:
        mission_manager.replan_route(
            session,
            mission,
            swath_m=payload.swath_m,
            azimuth_deg=payload.row_azimuth_deg,
            obstacle_margin_m=payload.obstacle_margin_m,
            actor_id=principal.user_id,
        )
    except mission_manager.RouteNotEditableError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except mission_manager.InvalidRouteError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    session.commit()
    return _mission_out(session, mission)


@router.post("/missions/{mission_id}/abort", response_model=MissionOut, summary="Aborta a missão")
def abort(
    mission_id: str,
    payload: AbortRequest,
    principal: Principal = Depends(require(rbac.MISSION_ABORT)),
    session: Session = Depends(get_session),
) -> MissionOut:
    """Interrompe a missão. Disponível a praticamente todos os papéis operacionais.

    Parar nunca deve depender de uma permissão rara: numa emergência, quem está
    perto do equipamento precisa conseguir agir.
    """
    mission = get_scoped(session, Mission, mission_id, principal)
    mission_manager.abort(
        session,
        mission,
        payload.reason,
        actor_type=ActorType.USER,
        actor_id=principal.user_id,
    )
    session.commit()
    return _mission_out(session, mission)


@router.get(
    "/missions/{mission_id}/safety",
    response_model=list[SafetyEvaluationOut],
    summary="Pareceres de segurança da missão",
)
def mission_safety(
    mission_id: str,
    principal: Principal = Depends(require(rbac.MISSION_READ)),
    session: Session = Depends(get_session),
) -> list[SafetyEvaluationOut]:
    """Histórico completo, não só o último.

    Ver que uma missão foi bloqueada três vezes antes de passar é informação
    operacional relevante — e é a primeira coisa que uma auditoria procura.
    """
    get_scoped(session, Mission, mission_id, principal)
    rows = session.scalars(
        select(SafetyEvaluation)
        .where(
            SafetyEvaluation.subject_type == SubjectType.MISSION,
            SafetyEvaluation.subject_id == mission_id,
        )
        .order_by(SafetyEvaluation.created_at.desc())
    )
    return [_evaluation_out(row) for row in rows]


@router.post(
    "/missions/{mission_id}/safety/preview",
    response_model=SafetyEvaluationOut,
    summary="Simula a avaliação sem mudar nada",
)
def preview_safety(
    mission_id: str,
    wind_ms: float | None = None,
    principal: Principal = Depends(require(rbac.MISSION_READ)),
    session: Session = Depends(get_session),
) -> SafetyEvaluationOut:
    """Roda as verificações sem gravar nem mudar o estado da missão.

    Serve para o operador ver o que falta enquanto ainda está montando a
    missão, sem sujar o histórico com bloqueios de rascunho.
    """
    mission = get_scoped(session, Mission, mission_id, principal)
    report = safety_engine.check_mission(session, mission, wind_ms=wind_ms)
    session.rollback()
    return SafetyEvaluationOut(
        id="preview",
        subject_type=SubjectType.MISSION.value,
        subject_id=mission.id,
        verdict=report.verdict,
        blocked_code=report.blocked_code,
        blocked_reason=report.blocked_reason,
        checks=[SafetyCheckOut(**check.as_dict()) for check in report.checks],
        engine_version=safety_engine.ENGINE_VERSION,
        created_at=datetime.now(UTC),
    )


def _evaluation_out(row: SafetyEvaluation | None) -> SafetyEvaluationOut:
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nenhum parecer de segurança registrado.")
    return SafetyEvaluationOut(
        id=row.id,
        subject_type=row.subject_type.value,
        subject_id=row.subject_id,
        verdict=row.verdict,
        blocked_code=row.blocked_code,
        blocked_reason=row.blocked_reason,
        checks=[SafetyCheckOut(**check) for check in row.checks],
        engine_version=row.engine_version,
        created_at=row.created_at,
    )


def _mission_out(session: Session, mission: Mission) -> MissionOut:
    total, done = session.execute(
        select(
            func.count(MissionSegment.id),
            func.sum(case((MissionSegment.state == SegmentState.DONE, 1), else_=0)),
        ).where(MissionSegment.mission_id == mission.id)
    ).one()
    return MissionOut(
        id=mission.id,
        kind=mission.kind,
        state=mission.state,
        farm_id=mission.farm_id,
        field_id=mission.field_id,
        zone_id=mission.zone_id,
        device_id=mission.device_id,
        target_polygon=mission.target_polygon,
        plan=mission.plan,
        product_id=mission.product_id,
        tank_id=mission.tank_id,
        authorized_rate_l_ha=mission.authorized_rate_l_ha,
        authorized_quantity_l=mission.authorized_quantity_l,
        created_by=mission.created_by,
        approved_by=mission.approved_by,
        approved_at=mission.approved_at,
        product_batch_id=mission.product_batch_id,
        decision_id=mission.decision_id,
        dispatched_at=mission.dispatched_at,
        started_at=mission.started_at,
        finished_at=mission.finished_at,
        abort_reason=mission.abort_reason,
        authorized_at=mission.authorized_at,
        expires_at=mission.expires_at,
        safety_status=mission.safety_status,
        safety_reason=mission.safety_reason,
        energy_policy=mission.energy_policy,
        offline_policy=mission.offline_policy,
        segments_total=total or 0,
        segments_done=int(done or 0),
        created_at=mission.created_at,
    )



# ---------------------------------------------------------------------------
# Resultado da missão: plantas, relatório e comparação (seções 7, 44 e 47)
# ---------------------------------------------------------------------------


@router.get("/missions/{mission_id}/plants", summary="Plantas vistas na missão e a incidência")
def mission_plants(
    mission_id: str,
    principal: Principal = Depends(require(rbac.DIAGNOSIS_READ)),
    session: Session = Depends(get_session),
) -> dict:
    """Fusão operacional por planta: quadros e câmeras da Edge AI + diagnóstico da nuvem.

    ``status`` por planta: ``doente`` (nuvem confirmou), ``suspeita`` (a Edge AI
    viu, a nuvem não fechou), ``revisar`` (com o agrônomo) ou ``sadia``.
    """
    missao = get_scoped(session, Mission, mission_id, principal)
    return missao_resultado.plantas_da_missao(session, missao.tenant_id, missao.id)


@router.get("/missions/{mission_id}/report", summary="Relatório da missão (seção 47)")
def mission_report(
    mission_id: str,
    principal: Principal = Depends(require(rbac.DIAGNOSIS_READ)),
    session: Session = Depends(get_session),
) -> dict:
    missao = get_scoped(session, Mission, mission_id, principal)
    return missao_resultado.relatorio(session, missao)


@router.get("/missions/{mission_id}/map", summary="Rota percorrida, eventos e plantas da missão")
def mission_map(
    mission_id: str,
    principal: Principal = Depends(require(rbac.DIAGNOSIS_READ)),
    session: Session = Depends(get_session),
) -> dict:
    """O que o mapa desenha por missão (seção 46).

    ``track``: posições dos quadros analisados pelo robô, na ordem (no máximo 2000;
    ``track_points_total`` diz quantas eram). ``events``: resultados da Edge AI que são
    evento e eventos com posição. ``plants``: estado de cada planta na fusão operacional.
    """
    missao = get_scoped(session, Mission, mission_id, principal)
    return visao_operacional.mapa_da_missao(session, missao)


@router.get("/missions/{mission_id}/comparison", summary="Compara com uma missão anterior")
def mission_comparison(
    mission_id: str,
    baseline_id: str,
    principal: Principal = Depends(require(rbac.DIAGNOSIS_READ)),
    session: Session = Depends(get_session),
) -> dict:
    nova = get_scoped(session, Mission, mission_id, principal)
    base = get_scoped(session, Mission, baseline_id, principal)
    if base.field_id != nova.field_id:
        raise HTTPException(status.HTTP_409_CONFLICT, "As duas missões são de talhões diferentes.")
    return missao_resultado.comparar(session, nova.tenant_id, base.id, nova.id)
