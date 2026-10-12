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
from typing import TypeVar

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, object_session

from valtexa.api.deps import DeviceCaller, current_device, require_active_device
from valtexa.config import settings
from valtexa.db import get_session
from valtexa.models import (
    ActorType,
    Application,
    ApplicationState,
    Asset,
    AssetKind,
    CapturePlatform,
    Device,
    Field,
    Mission,
    MissionKind,
    MissionState,
    Observation,
    RowScan,
    SubjectType,
    Tank,
    as_utc,
)
from valtexa.models.fleet import PROTOCOL_VERSION
from valtexa.schemas import (
    ApplicationOut,
    ApplicationStart,
    ApplicationStop,
    DesignatedModelOut,
    DeviceSessionIn,
    EventBatch,
    IngestOut,
    Message,
    MissionAck,
    MissionPause,
    ObservationIn,
    ObservationOut,
    RowScanIn,
    RowScanOut,
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
    consent,
    events,
    fusao_borda,
    geo,
    ingestion,
    mission_manager,
    model_registry,
    plant_map,
    pointcloud,
    scene,
    storage,
    verification,
)

router = APIRouter(prefix="/device", tags=["protocolo do dispositivo"])

_Metadata = TypeVar("_Metadata", ObservationIn, RowScanIn)

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
def open_session(
    payload: DeviceSessionIn | None = None,
    caller: DeviceCaller = Depends(current_device),
    session: Session = Depends(get_session),
) -> TokenResponse:
    """Troca uma requisição assinada por um token de curta duração.

    Conveniência para enlaces caros: o token evita uma assinatura por amostra de
    telemetria. Ele **não** substitui a assinatura em nada que mude o mundo
    físico — essas rotas continuam exigindo Ed25519.

    No corpo (opcional) o robô diz o software que está rodando: runtime, Edge AI,
    modelo, dNATY (brief, seção 22). É daí que a frota sabe a versão de cada um;
    ninguém a digita. Uma troca de versão fica na trilha do cliente.
    """
    if payload is not None:
        _registra_versoes(session, caller.device, payload)
    caller.device.last_seen_at = datetime.now(UTC)
    session.commit()
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


_VERSOES = (
    ("firmware_version", "firmware_version"),
    ("hardware_version", "hardware_version"),
    ("runtime_version", "runtime_version"),
    ("edge_ai_version", "edge_ai_version"),
    ("ai_model_key", "model_key"),
    ("ai_model_version", "model_version"),
    ("dnaty_version", "dnaty_version"),
)


def _registra_versoes(session: Session, device: Device, payload: DeviceSessionIn) -> None:
    """Grava as versões informadas; campo ausente não apaga o que já se sabia."""
    antes: dict[str, str | None] = {}
    depois: dict[str, str | None] = {}
    for coluna, campo in _VERSOES:
        valor = getattr(payload, campo)
        if valor is None or valor == getattr(device, coluna):
            continue
        antes[coluna] = getattr(device, coluna)
        depois[coluna] = valor
        setattr(device, coluna, valor)
    device.versions_reported_at = datetime.now(UTC)
    if depois:
        audit.record(
            session,
            tenant_id=device.tenant_id,
            action="device.versions_reported",
            subject_type=SubjectType.DEVICE,
            subject_id=device.id,
            actor_type=ActorType.DEVICE,
            actor_id=device.id,
            actor_label=device.serial_number,
            payload={"antes": antes, "depois": depois},
        )


@router.get(
    "/models",
    response_model=list[DesignatedModelOut],
    summary="Modelos designados a este robô pelo registry",
)
def designated_models(
    caller: DeviceCaller = Depends(current_device),
    session: Session = Depends(get_session),
) -> list[DesignatedModelOut]:
    """Para cada talhão onde o robô trabalha, a versão em PRODUÇÃO que ele deve rodar.

    Brief, seções 9 e 22: um robô nunca recebe modelo arbitrário. A resposta só
    traz versão em PRODUÇÃO do Model Registry, liberada para o cliente, com o
    hash que o robô confere antes de carregar. Sem artefato com hash no registry,
    ``artifact_sha256`` vem nulo — e o robô não carrega nada.
    """
    saida = []
    for item in model_registry.designados(session, caller.device):
        versao = item.version
        otimizado = bool(versao and versao.optimized_artifact_sha256)
        saida.append(
            DesignatedModelOut(
                field_id=item.field_id,
                field_name=item.field_name,
                crop=item.crop,
                model_key=versao.model_key if versao else None,
                version=versao.version if versao else None,
                state=versao.state if versao else None,
                artifact_uri=(
                    None
                    if versao is None
                    else versao.optimized_artifact_uri if otimizado
                    else versao.original_artifact_uri
                ),
                artifact_sha256=(
                    None
                    if versao is None
                    else versao.optimized_artifact_sha256 if otimizado
                    else versao.original_artifact_sha256
                ),
                artifact_kind=(
                    None
                    if versao is None
                    else "otimizado" if otimizado
                    else "original" if versao.original_artifact_sha256
                    else None
                ),
                dnaty_version=versao.dnaty_version if otimizado and versao else None,
                target_hardware=versao.target_hardware if versao else None,
                reason=item.reason,
            )
        )
    return saida


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
    agora = datetime.now(UTC)
    caller.device.last_seen_at = agora
    caller.device.sync_pending = payload.remaining or 0
    if caller.device.sync_pending == 0:
        caller.device.last_sync_at = agora
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
    # O tipo é o que os bytes dizem, não só o cabeçalho (Parte 9, seção 43): o tipo
    # declarado já era conferido contra a lista, mas um HTML declarado "image/jpeg"
    # entrava e era guardado e servido como imagem.
    tipo = storage.tipo_de_imagem(data)
    if tipo is None:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            "O arquivo não é uma imagem JPEG, PNG, WebP ou TIFF.",
        )
    filename = file.filename or "frame.jpg"
    mission_id = _mission_of(session, caller.device, payload.mission_id)
    # A inferência vem antes de qualquer escrita: são segundos de HTTP, e com a
    # transação aberta a linha do dispositivo (a marca d'água) ficaria presa —
    # a telemetria do mesmo robô esperaria o diagnóstico de cada quadro.
    analyses = _analyses(
        data,
        filename,
        field_row,
        _rover_frame(payload, field_row, mission_id),
        training_consent=consent.permite_treino(session, field_row.tenant_id),
    )

    asset = _store_asset(session, caller, data, tipo, AssetKind.IMAGE, payload.captured_at)

    observation = Observation(
        tenant_id=caller.tenant_id,
        farm_id=field_row.farm_id,
        field_id=field_row.id,
        zone_id=payload.zone_id,
        mission_id=mission_id,
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

    _run_pipeline(session, observation, data, filename, field_row, analyses=analyses)
    session.commit()
    return _observation_out(session, observation)


# ---------------------------------------------------------------------------
# Cópia 3D
# ---------------------------------------------------------------------------


@router.post(
    "/row-scans",
    response_model=RowScanOut,
    status_code=status.HTTP_201_CREATED,
    summary="Envia a varredura 3D de uma rua",
)
def post_row_scan(
    metadata: str = Form(description="JSON conforme o esquema RowScanIn."),
    file: UploadFile | None = File(
        default=None, description="Nuvem de pontos em PLY binário. Opcional."
    ),
    caller: DeviceCaller = Depends(current_device),
    session: Session = Depends(get_session),
) -> RowScanOut:
    """Recebe uma passada por uma rua: as plantas medidas e a nuvem de pontos.

    Cada passada substitui, na cópia 3D do talhão, a faixa que o sensor
    enxergou. A nuvem é opcional — um rover só com câmera manda as plantas que
    mediu por estéreo — mas uma passada sem planta e sem nuvem não diz nada e é
    recusada.

    Idempotente pela sequência: o upload é pesado e o enlace cai, então reenviar
    a mesma passada devolve a que já entrou.
    """
    payload = _parse_metadata(metadata, RowScanIn)
    field_row = session.get(Field, payload.field_id)
    if field_row is None or field_row.tenant_id != caller.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Talhão não encontrado.")

    existing = session.scalars(
        select(RowScan).where(
            RowScan.device_id == caller.device_id,
            RowScan.sequence_number == payload.sequence_number,
        )
    ).first()
    if existing is not None:
        return RowScanOut(**scene.scan_summary(existing))

    if not payload.plants and file is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Passada sem plantas e sem nuvem de pontos."
        )
    # Um talhão trocado no firmware colaria a rua de um talhão na cópia do outro.
    if not any(
        geo.contains_point(field_row.boundary, point[0], point[1], include_boundary=True)
        for point in payload.path
    ):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "O eixo da passada não cruza o talhão informado."
        )

    asset_id: str | None = None
    point_count: int | None = None
    if file is not None:
        data = file.file.read()
        try:
            info = pointcloud.inspect(data)
        except pointcloud.PointCloudError as exc:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, f"Nuvem de pontos recusada: {exc}"
            ) from exc
        asset = _store_asset(
            session, caller, data, "application/x-ply", AssetKind.POINTCLOUD, payload.captured_at
        )
        asset_id, point_count = asset.id, info.points

    heights = [plant[2] for plant in payload.plants]
    scan_row = RowScan(
        tenant_id=caller.tenant_id,
        farm_id=field_row.farm_id,
        field_id=field_row.id,
        mission_id=_mission_of(session, caller.device, payload.mission_id),
        device_id=caller.device_id,
        sequence_number=payload.sequence_number,
        segment_index=payload.segment_index,
        row_index=payload.row_index,
        started_at=payload.started_at,
        captured_at=payload.captured_at,
        sensor=payload.sensor,
        origin_lat=payload.origin_lat,
        origin_lon=payload.origin_lon,
        origin_alt_m=payload.origin_alt_m,
        path=payload.path,
        reach_m=payload.reach_m,
        length_m=geo.path_length_m(payload.path),
        plants=payload.plants,
        plant_count=len(payload.plants),
        mean_height_m=round(sum(heights) / len(heights), 3) if heights else None,
        max_height_m=round(max(heights), 3) if heights else None,
        pointcloud_asset_id=asset_id,
        point_count=point_count,
    )
    session.add(scan_row)
    session.flush()
    ingestion.bump_watermark(caller.device, payload.sequence_number)

    events.publish(
        session,
        events.ROW_SCAN_RECEIVED,
        tenant_id=caller.tenant_id,
        subject_type=SubjectType.FIELD,
        subject_id=field_row.id,
        payload={
            "row_scan_id": scan_row.id,
            "mission_id": scan_row.mission_id,
            "segment_index": scan_row.segment_index,
            "plants": scan_row.plant_count,
            "points": point_count,
        },
    )
    session.commit()
    return RowScanOut(**scene.scan_summary(scan_row))


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
    # A passada do rover pelo talhão é a missão: fechá-la consolida cada planta
    # e aponta o que mudou desde a anterior. Melhor esforço — ver plant_map. Com o
    # Rover Runtime os resultados sincronizam depois (offline-first): quem fecha é o
    # worker, quando todos chegarem e forem fundidos (services.fusao_borda).
    if not fusao_borda.fecha_pelo_worker(session, mission):
        plant_map.close_pass(mission.field_id, mission.id)
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
        raise HTTPException(status.HTTP_409_CONFLICT, "Esta missão não é de pulverização.")
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


def _rover_frame(
    payload: ObservationIn, field_row: Field, mission_id: str | None
) -> ai_pipeline.RoverFrame | None:
    """A câmera do quadro, no formato do pipeline — ou nada, se é foto de folha."""
    camera = payload.camera
    if camera is None:
        return None
    return ai_pipeline.RoverFrame(
        camera_height_mm=camera.camera_height_mm,
        distance_mm=camera.distance_mm,
        side=camera.side,
        x_m=camera.x_m,
        field_id=field_row.id,
        row_id=None if payload.row_index is None else str(payload.row_index),
        # A passada é a missão; sem missão, o dia — a fusão compara passadas.
        pass_id=mission_id or payload.captured_at.date().isoformat(),
        lat=payload.lat,
        lon=payload.lon,
        heading_deg=payload.heading_deg,
        camera_id=camera.camera_id,
        frame_id=None if payload.sequence_number is None else str(payload.sequence_number),
        captured_at=payload.captured_at,
    )


def _analyses(
    data: bytes,
    filename: str,
    field_row: Field,
    frame: ai_pipeline.RoverFrame | None = None,
    *,
    training_consent: bool = False,
) -> list[ai_pipeline.Analysis]:
    """Chama os analisadores com a versão do modelo do talhão.

    Só lê o registry (qual modelo atende o talhão); a inferência em si não toca no banco.
    """
    try:
        analyzers = ai_pipeline.default_analyzers()
    except ai_pipeline.AnalyzerUnavailableError:
        analyzers = []

    try:
        model_key = ai_pipeline.resolve_model(
            object_session(field_row),
            field_row.crop,
            CapturePlatform.GROUND,
            field_row.ai_model,
            tenant_id=field_row.tenant_id,
        )
    except ai_pipeline.NoModelForCaptureError:
        model_key = None  # o analisador explica a recusa na própria análise
    return ai_pipeline.run_analyzers(
        data,
        filename,
        field_row.crop,
        analyzers,
        model_key=model_key,
        frame=frame,
        training_consent=training_consent,
    )


def _run_pipeline(
    session: Session,
    observation: Observation,
    data: bytes,
    filename: str,
    field_row: Field,
    *,
    analyses: list[ai_pipeline.Analysis],
) -> None:
    """Grava detecções, diagnóstico e decisão de análises já feitas (:func:`_analyses`)."""
    detections, diagnosis = ai_pipeline.analyze_observation(
        observation, data, filename, field_row.crop, [], analyses=analyses
    )
    session.add_all(detections)
    session.add(diagnosis)
    session.flush()

    if detections:
        diagnosis.primary_detection_id = detections[0].id
        if len(detections) > 1:
            diagnosis.secondary_detection_id = detections[1].id

    audit.record_ai_diagnosis(
        session, diagnosis, pipeline_version=ai_pipeline.PIPELINE_VERSION
    )

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


def _parse_metadata(raw: str, schema: type[_Metadata] = ObservationIn) -> _Metadata:
    try:
        return schema(**json.loads(raw))
    except (ValueError, TypeError) as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"Campo 'metadata' inválido: {exc}"
        ) from exc


def _store_asset(
    session: Session,
    caller: DeviceCaller,
    data: bytes,
    content_type: str,
    kind: AssetKind,
    captured_at: datetime,
) -> Asset:
    """Guarda o arquivo e devolve a linha de ``Asset``.

    O mesmo conteúdo já enviado reaproveita a linha. Acontece de verdade: um
    reenvio depois de queda de enlace, ou o rover parado fotografando o mesmo
    ponto. Duas linhas para os mesmos bytes só criariam divergência.
    """
    stored = storage.store.put(data, content_type, namespace=caller.tenant_id)
    asset = session.scalars(
        select(Asset).where(Asset.tenant_id == caller.tenant_id, Asset.sha256 == stored.sha256)
    ).first()
    if asset is None:
        try:
            # Savepoint: dois envios simultâneos dos mesmos bytes (mesmo cliente)
            # disputam a mesma linha; quem perde reaproveita a do outro.
            with session.begin_nested():
                asset = Asset(
                    tenant_id=caller.tenant_id,
                    kind=kind,
                    content_type=stored.content_type,
                    size_bytes=stored.size_bytes,
                    sha256=stored.sha256,
                    storage_key=stored.key,
                    device_id=caller.device_id,
                    captured_at=captured_at,
                )
                session.add(asset)
                session.flush()
        except IntegrityError:
            asset = session.scalars(
                select(Asset).where(
                    Asset.tenant_id == caller.tenant_id, Asset.sha256 == stored.sha256
                )
            ).one()
    return asset


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
        collection_id=observation.collection_id,
        captured_at=observation.captured_at,
        lat=observation.lat,
        lon=observation.lon,
        image_asset_id=observation.image_asset_id,
        diagnosis_id=diagnosis.id if diagnosis else None,
        diagnosis_status=diagnosis.status if diagnosis else None,
        label=diagnosis.label if diagnosis else None,
        confidence=diagnosis.confidence if diagnosis else None,
        novelty_score=diagnosis.novelty_score if diagnosis else None,
        severity=diagnosis.severity if diagnosis else None,
        signals=_primary_signals(session, diagnosis),
    )


def _primary_signals(session: Session, diagnosis) -> dict:
    """Os sinais da análise primária — portão, conformal e o resumo do quadro."""
    from valtexa.models import Detection

    if diagnosis is None or diagnosis.primary_detection_id is None:
        return {}
    detection = session.get(Detection, diagnosis.primary_detection_id)
    return dict(detection.signals or {}) if detection is not None else {}


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
