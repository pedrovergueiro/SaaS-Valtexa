"""O protocolo robô ↔ nuvem.

Toda rota daqui exige requisição assinada — exceto ``/device/time``, que só
devolve o relógio do servidor e existe justamente para o robô se alinhar antes
de assinar qualquer coisa.

A regra que organiza o módulo inteiro: **o robô relata, a nuvem registra**. O
dispositivo nunca pede autorização em tempo real para agir; ele já recebeu a
missão assinada, com o polígono e as políticas dentro. Se a nuvem sumir, ele
continua operando pelo que tem embarcado. É o que separa um sistema que funciona
na lavoura de um que só funciona com 4G.

``docs/ROVER_INTEGRATION.md`` e ``docs/DRONE_INTEGRATION.md`` documentam cada
rota daqui no nível que o firmware precisa.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from valtexa.api.deps import DeviceCaller, current_device, require_active_device
from valtexa.config import settings
from valtexa.db import get_session
from valtexa.models import (
    ActorType,
    Application,
    ApplicationState,
    Asset,
    AssetKind,
    Device,
    Field,
    Mission,
    MissionKind,
    MissionState,
    Observation,
    SubjectType,
    Tank,
    as_utc,
)
from valtexa.models.fleet import PROTOCOL_VERSION
from valtexa.schemas import (
    ApplicationOut,
    ApplicationStart,
    ApplicationStop,
    EventBatch,
    IngestOut,
    Message,
    MissionAck,
    MissionPause,
    ObservationIn,
    ObservationOut,
    SegmentComplete,
    SignedCommandOut,
    SyncBatch,
    TelemetryBatch,
    TokenResponse,
)
from valtexa.security import tokens
from valtexa.services import (
    ai_pipeline,
    audit,
    events,
    geo,
    ingestion,
    mission_manager,
    storage,
    verification,
)

router = APIRouter(prefix="/device", tags=["protocolo do dispositivo"])

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}


@router.get("/time", summary="Relógio do servidor", response_model=dict)
def server_time() -> dict:
    """Referência de horário. Sem assinatura, de propósito.

    A assinatura depende de um horário dentro da janela de tolerância; exigir
    assinatura aqui deixaria um robô com relógio perdido sem caminho de volta.
    Nada é revelado além da hora.
    """
    now = datetime.now(UTC)
    return {
        "server_time": now.isoformat(),
        "unix": int(now.timestamp()),
        "protocol_version": PROTOCOL_VERSION,
        "clock_skew_tolerance_seconds": settings.device_clock_skew_seconds,
    }


@router.post("/session", response_model=TokenResponse, summary="Token de sessão do dispositivo")
def open_session(caller: DeviceCaller = Depends(current_device)) -> TokenResponse:
    """Troca uma requisição assinada por um token de curta duração.

    Conveniência para enlaces caros: o token evita uma assinatura por amostra de
    telemetria. Ele **não** substitui a assinatura em nada que mude o mundo
    físico — essas rotas continuam exigindo Ed25519.
    """
    token, expires_at = tokens.issue(
        "device", caller.device_id, tenant_id=caller.tenant_id, key_id=caller.credential.key_id
    )
    return TokenResponse(
        access_token=token,
        expires_at=expires_at,
        tenant_id=caller.tenant_id,
        role=None,
        capabilities=[],
    )


# ---------------------------------------------------------------------------
# Telemetria, eventos e sincronização
# ---------------------------------------------------------------------------


@router.post("/telemetry", response_model=IngestOut, summary="Envia telemetria")
def post_telemetry(
    payload: TelemetryBatch,
    caller: DeviceCaller = Depends(current_device),
    session: Session = Depends(get_session),
) -> IngestOut:
    """Recebe um lote de amostras."""
    _check_batch(len(payload.samples), settings.max_telemetry_batch, "amostras")
    result = ingestion.ingest_telemetry(
        session,
        caller.device,
        [sample.model_dump() for sample in payload.samples],
        sync_id=payload.sync_id,
    )
    session.commit()
    return _ingest_out(result)


@router.post("/events", response_model=IngestOut, summary="Envia eventos")
def post_events(
    payload: EventBatch,
    caller: DeviceCaller = Depends(current_device),
    session: Session = Depends(get_session),
) -> IngestOut:
    result = ingestion.ingest_events(
        session,
        caller.device,
        [event.model_dump() for event in payload.events],
        sync_id=payload.sync_id,
    )
    session.commit()
    return _ingest_out(result)


@router.post("/sync", response_model=IngestOut, summary="Descarrega um período offline")
def sync(
    payload: SyncBatch,
    caller: DeviceCaller = Depends(current_device),
    session: Session = Depends(get_session),
) -> IngestOut:
    """Recebe de uma vez tudo que o robô acumulou sem enlace.

    Idempotente: o robô pode reenviar o mesmo ``sync_id`` quantas vezes precisar
    — a conexão pode cair no meio da descarga, e reenviar é o comportamento
    correto do firmware. O que já entrou volta em ``duplicated``, não em erro.
    """
    total = len(payload.samples) + len(payload.events)
    _check_batch(total, settings.max_sync_batch, "registros")

    telemetry = ingestion.ingest_telemetry(
        session,
        caller.device,
        [sample.model_dump() for sample in payload.samples],
        sync_id=payload.sync_id,
    )
    device_events = ingestion.ingest_events(
        session,
        caller.device,
        [event.model_dump() for event in payload.events],
        sync_id=payload.sync_id,
    )
    session.commit()

    return IngestOut(
        accepted=telemetry.accepted + device_events.accepted,
        duplicated=telemetry.duplicated + device_events.duplicated,
        rejected=telemetry.rejected + device_events.rejected,
        errors=[*telemetry.errors, *device_events.errors],
    )


# ---------------------------------------------------------------------------
# Observações
# ---------------------------------------------------------------------------


@router.post(
    "/observations",
    response_model=ObservationOut,
    status_code=status.HTTP_201_CREATED,
    summary="Envia uma imagem observada",
)
def post_observation(
    metadata: str = Form(description="JSON conforme o esquema ObservationIn."),
    file: UploadFile = File(description="Imagem JPEG, PNG ou WebP."),
    caller: DeviceCaller = Depends(current_device),
    session: Session = Depends(get_session),
) -> ObservationOut:
    """Recebe imagem e metadados, guarda e roda o pipeline de percepção.

    O pipeline roda aqui, na mesma requisição, porque o robô precisa saber se a
    imagem foi aceita. O que ele **não** espera é decisão: o diagnóstico segue
    seu curso na nuvem, e nada do que sair daqui volta como ordem para o robô.
    """
    payload = _parse_metadata(metadata)
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            f"Tipo {file.content_type!r} não suportado. Use {sorted(ALLOWED_IMAGE_TYPES)}.",
        )

    field_row = session.get(Field, payload.field_id)
    if field_row is None or field_row.tenant_id != caller.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Talhão não encontrado.")

    if ingestion.observation_exists(session, caller.device_id, payload.sequence_number):
        existing = session.scalars(
            select(Observation).where(
                Observation.device_id == caller.device_id,
                Observation.sequence_number == payload.sequence_number,
            )
        ).first()
        return _observation_out(session, existing)

    data = file.file.read()
    try:
        stored = storage.store.put(data, file.content_type, namespace=caller.tenant_id)
    except storage.AssetTooLargeError as exc:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, str(exc)) from exc

    # O mesmo conteúdo já enviado reaproveita a linha. Acontece de verdade: um
    # reenvio depois de queda de enlace, ou o rover parado fotografando o mesmo
    # ponto. Duas linhas para os mesmos bytes só criariam divergência.
    asset = session.scalars(
        select(Asset).where(Asset.tenant_id == caller.tenant_id, Asset.sha256 == stored.sha256)
    ).first()
    if asset is None:
        asset = Asset(
            tenant_id=caller.tenant_id,
            kind=AssetKind.IMAGE,
            content_type=stored.content_type,
            size_bytes=stored.size_bytes,
            sha256=stored.sha256,
            storage_key=stored.key,
            device_id=caller.device_id,
            captured_at=payload.captured_at,
        )
        session.add(asset)
        session.flush()

    observation = Observation(
        tenant_id=caller.tenant_id,
        farm_id=field_row.farm_id,
        field_id=field_row.id,
        zone_id=payload.zone_id,
        mission_id=_mission_of(session, caller.device, payload.mission_id),
        device_id=caller.device_id,
        sequence_number=payload.sequence_number,
        captured_at=payload.captured_at,
        lat=payload.lat,
        lon=payload.lon,
        alt_m=payload.alt_m,
        heading_deg=payload.heading_deg,
        row_index=payload.row_index,
        image_asset_id=asset.id,
        edge_summary=payload.edge_summary,
        model_input_ok=payload.model_input_ok,
    )
    session.add(observation)
    session.flush()
    ingestion.bump_watermark(caller.device, payload.sequence_number)

    _run_pipeline(session, observation, data, file.filename or "frame.jpg", field_row.crop)
    session.commit()
    return _observation_out(session, observation)


# ---------------------------------------------------------------------------
# Missões
# ---------------------------------------------------------------------------


@router.get(
    "/missions/current",
    response_model=SignedCommandOut,
    responses={204: {"description": "Nada a fazer agora."}},
    summary="Busca a missão pendente",
)
def current_mission(
    caller: DeviceCaller = Depends(require_active_device),
    session: Session = Depends(get_session),
) -> SignedCommandOut | Response:
    """Devolve o comando assinado da missão despachada, se houver.

    O robô verifica a assinatura com a chave pública da plataforma antes de
    obedecer. Comando vencido é descartado sem execução — inclusive por este
    servidor, que nem chega a devolvê-lo.
    """
    mission = session.scalars(
        select(Mission)
        .where(
            Mission.device_id == caller.device_id,
            Mission.state.in_([MissionState.DISPATCHED, MissionState.RUNNING]),
        )
        .order_by(Mission.dispatched_at.desc())
        .limit(1)
    ).first()

    if mission is None or not mission.signature:
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    expires_at = as_utc(mission.expires_at)
    if expires_at is not None and expires_at <= datetime.now(UTC):
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    envelope = mission_manager.rebuild_envelope(mission)
    return SignedCommandOut(**envelope)


@router.post("/missions/{mission_id}/ack", response_model=Message, summary="Confirma o recebimento")
def acknowledge(
    mission_id: str,
    payload: MissionAck,
    caller: DeviceCaller = Depends(require_active_device),
    session: Session = Depends(get_session),
) -> Message:
    """Registra que o robô aceitou (ou recusou) a missão.

    A recusa é informação valiosa e é gravada como tal: o robô verifica a missão
    localmente antes de aceitar, e uma recusa significa que a nuvem e o
    dispositivo discordam sobre o que é seguro. Isso precisa aparecer para um
    humano, não sumir num log.
    """
    mission = _mission_for(session, caller, mission_id)

    if not payload.accepted:
        mission_manager.abort(
            session,
            mission,
            f"Recusada pelo dispositivo: {payload.reason or 'sem motivo informado'}",
            actor_type=ActorType.DEVICE,
            actor_id=caller.device_id,
        )
        session.commit()
        return Message(detail="Recusa registrada e missão abortada.")

    if mission.state is MissionState.DISPATCHED:
        mission_manager.transition(
            session,
            mission,
            MissionState.RUNNING,
            reason="Aceita pelo dispositivo.",
            actor_type=ActorType.DEVICE,
            actor_id=caller.device_id,
        )
    session.commit()
    return Message(detail="Missão aceita.")


@router.post(
    "/missions/{mission_id}/segments/complete",
    response_model=Message,
    summary="Conclui um segmento",
)
def complete_segment(
    mission_id: str,
    payload: SegmentComplete,
    caller: DeviceCaller = Depends(require_active_device),
    session: Session = Depends(get_session),
) -> Message:
    """Marca uma passada como concluída e grava o checkpoint.

    Este é o ponto que torna a retomada possível. Reportar por segmento, e não
    só no fim, é o que permite continuar de onde parou depois de uma recarga —
    ou de uma queda.
    """
    mission = _mission_for(session, caller, mission_id)
    mission_manager.complete_segment(
        session,
        mission,
        payload.segment_index,
        lat=payload.lat,
        lon=payload.lon,
        battery_percent=payload.battery_percent,
    )
    remaining = len(mission_manager.pending_segments(session, mission))
    session.commit()
    return Message(detail=f"Segmento {payload.segment_index} concluído. Faltam {remaining}.")


@router.post("/missions/{mission_id}/pause", response_model=Message, summary="Pausa para recarga")
def pause(
    mission_id: str,
    payload: MissionPause,
    caller: DeviceCaller = Depends(require_active_device),
    session: Session = Depends(get_session),
) -> Message:
    """O robô decidiu voltar à base. A nuvem registra; não autoriza.

    A decisão de retorno por energia é local e já foi tomada quando esta
    requisição chega. Depender da nuvem aqui deixaria um drone com 12% de
    bateria e sem sinal esperando resposta até cair.
    """
    mission = _mission_for(session, caller, mission_id)
    mission_manager.pause_for_recharge(
        session,
        mission,
        lat=payload.lat,
        lon=payload.lon,
        battery_percent=payload.battery_percent,
    )
    session.commit()
    return Message(detail="Pausa registrada. A missão retoma do último checkpoint.")


@router.post(
    "/missions/{mission_id}/recharged", response_model=Message, summary="Recarga concluída"
)
def recharged(
    mission_id: str,
    caller: DeviceCaller = Depends(require_active_device),
    session: Session = Depends(get_session),
) -> Message:
    mission = _mission_for(session, caller, mission_id)
    mission_manager.mark_ready_to_resume(session, mission)
    session.commit()
    return Message(detail="Pronto para retomar. Busque a missão em /device/missions/current.")


@router.post("/missions/{mission_id}/complete", response_model=Message, summary="Conclui a missão")
def complete_mission(
    mission_id: str,
    caller: DeviceCaller = Depends(require_active_device),
    session: Session = Depends(get_session),
) -> Message:
    """Encerra a missão. Uma varredura concluída dispara a leitura do gêmeo digital."""
    mission = _mission_for(session, caller, mission_id)
    mission_manager.transition(
        session,
        mission,
        MissionState.COMPLETED,
        reason="Concluída pelo dispositivo.",
        actor_type=ActorType.DEVICE,
        actor_id=caller.device_id,
    )
    session.commit()
    return Message(detail="Missão concluída.")


# ---------------------------------------------------------------------------
# Aplicação
# ---------------------------------------------------------------------------


@router.post(
    "/applications/start",
    response_model=ApplicationOut,
    status_code=status.HTTP_201_CREATED,
    summary="Abriu o bico",
)
def start_application(
    payload: ApplicationStart,
    caller: DeviceCaller = Depends(require_active_device),
    session: Session = Depends(get_session),
) -> ApplicationOut:
    """Registra o início de uma aplicação real.

    A nuvem não cria aplicação por conta própria: ela existe porque o drone
    reportou que abriu o bico. O registro só é aceito se a missão for de
    pulverização e estiver de fato em execução — não há como lançar aplicação
    contra uma missão de varredura ou já encerrada.
    """
    mission = _mission_for(session, caller, payload.mission_id)
    if mission.kind is not MissionKind.SPRAY:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Esta missão não é de pulverização."
        )
    if mission.state is not MissionState.RUNNING:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Missão em {mission.state.value!r}: aplicação só durante a execução.",
        )

    application = Application(
        tenant_id=caller.tenant_id,
        mission_id=mission.id,
        device_id=caller.device_id,
        tank_id=payload.tank_id or mission.tank_id,
        product_id=mission.product_id,
        product_batch_id=mission.product_batch_id,
        field_id=mission.field_id,
        zone_id=mission.zone_id,
        state=ApplicationState.STARTED,
        started_at=payload.started_at,
    )
    session.add(application)
    session.flush()

    audit.record(
        session,
        tenant_id=caller.tenant_id,
        action="application.started",
        subject_type=SubjectType.APPLICATION,
        subject_id=application.id,
        actor_type=ActorType.DEVICE,
        actor_id=caller.device_id,
        actor_label=caller.device.serial_number,
        payload={"mission_id": mission.id, "product_id": mission.product_id},
    )
    events.publish(
        session,
        events.APPLICATION_STARTED,
        tenant_id=caller.tenant_id,
        subject_type=SubjectType.APPLICATION,
        subject_id=application.id,
    )
    session.commit()
    return _application_out(application)


@router.post(
    "/applications/{application_id}/stop",
    response_model=ApplicationOut,
    summary="Fechou o bico",
)
def stop_application(
    application_id: str,
    payload: ApplicationStop,
    caller: DeviceCaller = Depends(require_active_device),
    session: Session = Depends(get_session),
) -> ApplicationOut:
    """Fecha a aplicação, confere a trilha contra o polígono e agenda a verificação.

    A conferência da trilha é auditoria posterior, não controle: quem impede a
    saída da área é o robô, em tempo real. O que se faz aqui é **detectar** que
    a contenção falhou — e um único ponto fora vira evento crítico, porque é
    exatamente o incidente que a plataforma existe para nunca deixar passar
    despercebido.
    """
    application = session.get(Application, application_id)
    if application is None or application.tenant_id != caller.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Aplicação não encontrada.")
    if application.device_id != caller.device_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Esta aplicação é de outro dispositivo.")

    mission = session.get(Mission, application.mission_id)
    outside = _points_outside(mission, payload.track)

    application.state = ApplicationState.COMPLETED
    application.stopped_at = payload.stopped_at
    application.amount_used_l = payload.amount_used_l
    application.area_ha = payload.area_ha
    application.track = payload.track
    application.outside_polygon_points = outside
    application.stop_reason = payload.stop_reason
    if payload.area_ha:
        application.mean_rate_l_ha = round(payload.amount_used_l / payload.area_ha, 3)

    _consume_tank(session, application, payload.amount_used_l)

    audit.record(
        session,
        tenant_id=caller.tenant_id,
        action="application.completed",
        subject_type=SubjectType.APPLICATION,
        subject_id=application.id,
        actor_type=ActorType.DEVICE,
        actor_id=caller.device_id,
        actor_label=caller.device.serial_number,
        payload={
            "amount_used_l": payload.amount_used_l,
            "area_ha": payload.area_ha,
            "outside_polygon_points": outside,
        },
    )
    events.publish(
        session,
        events.APPLICATION_COMPLETED,
        tenant_id=caller.tenant_id,
        subject_type=SubjectType.APPLICATION,
        subject_id=application.id,
    )
    if outside:
        events.publish(
            session,
            events.APPLICATION_OUT_OF_BOUNDS,
            tenant_id=caller.tenant_id,
            subject_type=SubjectType.APPLICATION,
            subject_id=application.id,
            payload={"points": outside, "total": len(payload.track)},
        )

    verification.schedule(session, application)
    session.commit()
    return _application_out(application)


# ---------------------------------------------------------------------------
# Auxiliares
# ---------------------------------------------------------------------------


def _run_pipeline(
    session: Session, observation: Observation, data: bytes, filename: str, crop: str
) -> None:
    """Roda os analisadores e grava detecções, diagnóstico e decisão."""
    try:
        analyzers = ai_pipeline.default_analyzers()
    except ai_pipeline.AnalyzerUnavailableError:
        analyzers = []

    detections, diagnosis = ai_pipeline.analyze_observation(
        observation, data, filename, crop, analyzers
    )
    session.add_all(detections)
    session.add(diagnosis)
    session.flush()

    if detections:
        diagnosis.primary_detection_id = detections[0].id
        if len(detections) > 1:
            diagnosis.secondary_detection_id = detections[1].id

    events.publish(
        session,
        events.DIAGNOSIS_CREATED,
        tenant_id=observation.tenant_id,
        subject_type=SubjectType.DIAGNOSIS,
        subject_id=diagnosis.id,
        payload={"status": diagnosis.status.value, "label": diagnosis.label},
    )
    if (diagnosis.novelty_score or 0.0) > settings.novelty_threshold:
        events.publish(
            session,
            events.NOVELTY_DETECTED,
            tenant_id=observation.tenant_id,
            subject_type=SubjectType.DIAGNOSIS,
            subject_id=diagnosis.id,
            payload={"novelty_score": diagnosis.novelty_score, "label": diagnosis.label},
        )


def _points_outside(mission: Mission | None, track: list) -> int:
    """Conta pontos da trilha fora do polígono autorizado."""
    if mission is None or not track:
        return 0
    try:
        geo.as_points(mission.target_polygon)
    except geo.InvalidPolygonError:
        return 0
    return sum(
        1
        for point in track
        if len(point) >= 2 and not geo.contains_point(mission.target_polygon, point[0], point[1])
    )


def _consume_tank(session: Session, application: Application, amount_l: float) -> None:
    """Debita o volume aplicado do tanque.

    Nunca abaixo de zero: um saldo negativo seria um número impossível
    circulando pelo resto do sistema. Aplicar mais do que havia significa que a
    medição está errada, e isso vira uma discrepância visível no relatório, não
    um estoque negativo silencioso.
    """
    if not application.tank_id:
        return
    tank = session.get(Tank, application.tank_id)
    if tank is None:
        return
    tank.current_level_l = max(0.0, tank.current_level_l - max(0.0, amount_l))


def _mission_for(session: Session, caller: DeviceCaller, mission_id: str) -> Mission:
    mission = session.get(Mission, mission_id)
    if mission is None or mission.tenant_id != caller.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Missão não encontrada.")
    if mission.device_id != caller.device_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Esta missão é de outro dispositivo.")
    return mission


def _mission_of(session: Session, device: Device, mission_id: str | None) -> str | None:
    if not mission_id:
        return None
    mission = session.get(Mission, mission_id)
    return mission_id if mission is not None and mission.device_id == device.id else None


def _parse_metadata(raw: str) -> ObservationIn:
    try:
        return ObservationIn(**json.loads(raw))
    except (ValueError, TypeError) as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, f"Campo 'metadata' inválido: {exc}"
        ) from exc


def _check_batch(size: int, limit: int, noun: str) -> None:
    if size > limit:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"Lote de {size} {noun} excede o limite de {limit} por requisição.",
        )


def _ingest_out(result: ingestion.IngestResult) -> IngestOut:
    return IngestOut(
        accepted=result.accepted,
        duplicated=result.duplicated,
        rejected=result.rejected,
        errors=list(result.errors),
    )


def _observation_out(session: Session, observation: Observation) -> ObservationOut:
    from valtexa.models import Diagnosis

    diagnosis = session.scalars(
        select(Diagnosis)
        .where(Diagnosis.observation_id == observation.id)
        .order_by(Diagnosis.created_at.desc())
        .limit(1)
    ).first()
    return ObservationOut(
        id=observation.id,
        field_id=observation.field_id,
        zone_id=observation.zone_id,
        mission_id=observation.mission_id,
        device_id=observation.device_id,
        captured_at=observation.captured_at,
        lat=observation.lat,
        lon=observation.lon,
        image_asset_id=observation.image_asset_id,
        diagnosis_id=diagnosis.id if diagnosis else None,
        diagnosis_status=diagnosis.status if diagnosis else None,
        label=diagnosis.label if diagnosis else None,
        confidence=diagnosis.confidence if diagnosis else None,
        novelty_score=diagnosis.novelty_score if diagnosis else None,
    )


def _application_out(application: Application) -> ApplicationOut:
    return ApplicationOut(
        id=application.id,
        mission_id=application.mission_id,
        device_id=application.device_id,
        field_id=application.field_id,
        zone_id=application.zone_id,
        product_id=application.product_id,
        state=application.state,
        started_at=application.started_at,
        stopped_at=application.stopped_at,
        amount_used_l=application.amount_used_l,
        area_ha=application.area_ha,
        mean_rate_l_ha=application.mean_rate_l_ha,
        outside_polygon_points=application.outside_polygon_points,
        verified=application.verified,
    )
