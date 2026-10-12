"""Rotas de leitura para o console: telemetria, eventos, alertas e painel.

O fluxo ao vivo (SSE) mora em :mod:`valtexa.api.routers.stream`.

Tudo aqui é leitura agregada que a tela precisaria montar com dezenas de
chamadas. Nenhuma regra nova mora aqui — os alertas são o que outras partes do
sistema já concluíram (safety engine, gêmeo digital, ingestão), reunido num
lugar só.
"""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from valtexa.api.deps import Principal, get_scoped, require, scoped
from valtexa.config import settings
from valtexa.db import get_session
from valtexa.models import (
    Application,
    AuditEntry,
    Device,
    DeviceEvent,
    DeviceKind,
    DeviceStatus,
    Diagnosis,
    DiagnosisStatus,
    EventSeverity,
    Field,
    Mission,
    MissionCheckpoint,
    MissionSegment,
    MissionState,
    Observation,
    SegmentState,
    SubjectType,
    TelemetryRollup,
    TelemetrySample,
    Verification,
    VerificationConclusion,
    as_utc,
)
from valtexa.schemas import (
    AlertOut,
    ApplicationSummary,
    CheckpointOut,
    DashboardOut,
    DashboardOverviewOut,
    DeviceEventOut,
    DeviceSummary,
    MissionBrief,
    MissionHistoryOut,
    TelemetryOut,
    TelemetryRollupOut,
)
from valtexa.security import rbac
from valtexa.services import twin, verification, visao_operacional
from valtexa.services.ingestion import OFFLINE_AFTER

router = APIRouter(tags=["console"])

SEVERITY_RANK = {"critical": 0, "warning": 1, "info": 2}
MAX_FIELDS_FOR_ANOMALIES = 50
"""Teto de talhões varridos por pedido de alertas.

A detecção de anomalia faz duas consultas por talhão; acima disso ela precisa
virar tarefa do worker, com resultado gravado.
"""


# ---------------------------------------------------------------------------
# Telemetria e eventos de um dispositivo
# ---------------------------------------------------------------------------


@router.get(
    "/devices/{device_id}/telemetry",
    response_model=list[TelemetryOut],
    summary="Telemetria recente de um dispositivo",
)
def device_telemetry(
    device_id: str,
    minutes: int = Query(default=60, ge=1, le=7 * 24 * 60),
    limit: int = Query(default=600, ge=1, le=5000),
    principal: Principal = Depends(require(rbac.DEVICE_READ)),
    session: Session = Depends(get_session),
) -> list[TelemetryOut]:
    """Amostras cruas da janela, em ordem cronológica.

    Para janelas mais velhas que ``TELEMETRY_RETENTION_DAYS`` a amostra crua já
    não existe: use ``/telemetry/rollup``.
    """
    get_scoped(session, Device, device_id, principal)
    since = datetime.now(UTC) - timedelta(minutes=minutes)
    rows = list(
        session.scalars(
            select(TelemetrySample)
            .where(
                TelemetrySample.tenant_id == principal.tenant_id,
                TelemetrySample.device_id == device_id,
                TelemetrySample.recorded_at >= since,
            )
            .order_by(TelemetrySample.recorded_at.desc())
            .limit(limit)
        )
    )
    rows.reverse()
    return [
        TelemetryOut(
            sequence_number=row.sequence_number,
            recorded_at=row.recorded_at,
            received_at=row.received_at,
            mission_id=row.mission_id,
            lat=row.lat,
            lon=row.lon,
            alt_m=row.alt_m,
            heading_deg=row.heading_deg,
            speed_ms=row.speed_ms,
            rtk_fix=row.rtk_fix.value,
            battery_percent=row.battery_percent,
            battery_voltage_v=row.battery_voltage_v,
            temperature_c=row.temperature_c,
            energy_state=row.energy_state.value,
            mission_state=row.mission_state,
            link_quality=row.link_quality,
            sensors=row.sensors or {},
            faults=row.faults or [],
        )
        for row in rows
    ]


@router.get(
    "/devices/{device_id}/telemetry/rollup",
    response_model=list[TelemetryRollupOut],
    summary="Telemetria agregada por minuto",
)
def device_telemetry_rollup(
    device_id: str,
    days: int = Query(default=30, ge=1, le=730),
    principal: Principal = Depends(require(rbac.DEVICE_READ)),
    session: Session = Depends(get_session),
) -> list[TelemetryRollupOut]:
    get_scoped(session, Device, device_id, principal)
    since = datetime.now(UTC) - timedelta(days=days)
    rows = session.scalars(
        select(TelemetryRollup)
        .where(
            TelemetryRollup.tenant_id == principal.tenant_id,
            TelemetryRollup.device_id == device_id,
            TelemetryRollup.bucket_start >= since,
        )
        .order_by(TelemetryRollup.bucket_start)
        .limit(20_000)
    )
    return [
        TelemetryRollupOut(
            bucket_start=row.bucket_start,
            bucket_seconds=row.bucket_seconds,
            samples=row.samples,
            battery_min=row.battery_min,
            battery_avg=row.battery_avg,
            battery_max=row.battery_max,
            speed_avg_ms=row.speed_avg_ms,
            link_quality_avg=row.link_quality_avg,
            rtk_fixed_ratio=row.rtk_fixed_ratio,
            last_lat=row.last_lat,
            last_lon=row.last_lon,
        )
        for row in rows
    ]


@router.get(
    "/devices/{device_id}/events",
    response_model=list[DeviceEventOut],
    summary="Eventos relatados por um dispositivo",
)
def device_events(
    device_id: str,
    limit: int = Query(default=100, ge=1, le=1000),
    principal: Principal = Depends(require(rbac.DEVICE_READ)),
    session: Session = Depends(get_session),
) -> list[DeviceEventOut]:
    get_scoped(session, Device, device_id, principal)
    rows = session.scalars(
        select(DeviceEvent)
        .where(DeviceEvent.tenant_id == principal.tenant_id, DeviceEvent.device_id == device_id)
        .order_by(DeviceEvent.occurred_at.desc())
        .limit(limit)
    )
    return [_event_out(row) for row in rows]


# ---------------------------------------------------------------------------
# Missão: histórico e checkpoints
# ---------------------------------------------------------------------------


@router.get(
    "/missions/{mission_id}/history",
    response_model=list[MissionHistoryOut],
    summary="Linha do tempo de uma missão",
)
def mission_history(
    mission_id: str,
    principal: Principal = Depends(require(rbac.MISSION_READ)),
    session: Session = Depends(get_session),
) -> list[MissionHistoryOut]:
    """Toda transição, com quem fez e por quê.

    Lê da auditoria, mas só as entradas desta missão — o operador acompanha a
    própria missão sem precisar da permissão de ler a auditoria inteira.
    """
    get_scoped(session, Mission, mission_id, principal)
    rows = session.scalars(
        select(AuditEntry)
        .where(
            AuditEntry.tenant_id == principal.tenant_id,
            AuditEntry.subject_type == SubjectType.MISSION,
            AuditEntry.subject_id == mission_id,
        )
        .order_by(AuditEntry.at)
    )
    return [
        MissionHistoryOut(
            at=row.at,
            action=row.action,
            old_state=row.old_state,
            new_state=row.new_state,
            reason=row.reason,
            actor_type=row.actor_type.value,
            actor=row.actor_label or row.actor_id,
        )
        for row in rows
    ]


@router.get(
    "/missions/{mission_id}/checkpoints",
    response_model=list[CheckpointOut],
    summary="Checkpoints de uma missão",
)
def mission_checkpoints(
    mission_id: str,
    principal: Principal = Depends(require(rbac.MISSION_READ)),
    session: Session = Depends(get_session),
) -> list[CheckpointOut]:
    get_scoped(session, Mission, mission_id, principal)
    rows = session.scalars(
        select(MissionCheckpoint)
        .where(MissionCheckpoint.mission_id == mission_id)
        .order_by(MissionCheckpoint.created_at)
    )
    return [
        CheckpointOut(
            created_at=row.created_at,
            last_completed_segment=row.last_completed_segment,
            remaining_segments=len(row.remaining_segments or []),
            battery_percent=row.battery_percent,
            reason=row.reason,
            lat=row.last_lat,
            lon=row.last_lon,
        )
        for row in rows
    ]


# ---------------------------------------------------------------------------
# Alertas e painel
# ---------------------------------------------------------------------------


@router.get("/alerts", response_model=list[AlertOut], summary="Alertas ativos do cliente")
def alerts(
    days: int = Query(default=7, ge=1, le=90),
    principal: Principal = Depends(require(rbac.TENANT_READ)),
    session: Session = Depends(get_session),
) -> list[AlertOut]:
    """O que precisa de atenção humana agora, do mais grave ao mais leve.

    Não há estado próprio: cada alerta é derivado do que o resto do sistema já
    registrou. Resolver a causa — reconectar o robô, revisar a fila, corrigir o
    tanque — faz o alerta sumir sozinho.
    """
    return collect_alerts(session, principal.tenant_id, days=days)


@router.get("/dashboard", response_model=DashboardOut, summary="Painel do cliente")
def dashboard(
    principal: Principal = Depends(require(rbac.TENANT_READ)),
    session: Session = Depends(get_session),
) -> DashboardOut:
    now = datetime.now(UTC)
    tenant_id = principal.tenant_id

    devices = list(session.scalars(scoped(select(Device), Device, principal)))
    online = sum(1 for device in devices if _is_online(device, now))
    active = [device for device in devices if device.status is DeviceStatus.ACTIVE]
    low_battery = sum(
        1
        for device in active
        if device.kind in {DeviceKind.ROVER, DeviceKind.DRONE}
        and device.battery_percent is not None
        and device.battery_percent < settings.safety_min_battery_percent
    )

    by_state = dict(
        session.execute(
            select(Mission.state, func.count(Mission.id))
            .where(Mission.tenant_id == tenant_id)
            .group_by(Mission.state)
        ).all()
    )

    week = now - timedelta(days=7)
    observations_7d = session.scalar(
        select(func.count(Observation.id)).where(
            Observation.tenant_id == tenant_id, Observation.captured_at >= week
        )
    )
    labels = Counter(
        row.effective_label
        for row in session.scalars(
            select(Diagnosis).where(Diagnosis.tenant_id == tenant_id, Diagnosis.created_at >= week)
        )
        if row.effective_label
    )

    month = now - timedelta(days=30)
    count, liters, area = session.execute(
        select(
            func.count(Application.id),
            func.coalesce(func.sum(Application.amount_used_l), 0.0),
            func.coalesce(func.sum(Application.area_ha), 0.0),
        ).where(Application.tenant_id == tenant_id, Application.started_at >= month)
    ).one()

    pending_verifications = session.scalar(
        select(func.count(Verification.id)).where(
            Verification.tenant_id == tenant_id,
            Verification.conclusion == VerificationConclusion.PENDING,
        )
    )

    current_alerts = collect_alerts(session, tenant_id, days=7)
    alert_counts = Counter(alert.severity for alert in current_alerts)

    return DashboardOut(
        generated_at=now,
        devices=DeviceSummary(
            total=len(devices),
            active=len(active),
            online=online,
            offline=len(active) - sum(1 for device in active if _is_online(device, now)),
            low_battery=low_battery,
            by_kind=dict(Counter(device.kind.value for device in devices)),
        ),
        missions_by_state={state.value: total for state, total in by_state.items()},
        review_queue=_review_backlog(session, tenant_id),
        observations_7d=observations_7d or 0,
        labels_7d=dict(labels.most_common()),
        applications_30d=ApplicationSummary(
            count=count or 0, liters=round(float(liters), 2), area_ha=round(float(area), 3)
        ),
        verifications_pending=pending_verifications or 0,
        alert_counts={key: alert_counts.get(key, 0) for key in SEVERITY_RANK},
        alerts=current_alerts[:8],
        recent_missions=_recent_missions(session, tenant_id),
        overview=DashboardOverviewOut(**visao_operacional.painel(session, tenant_id, now)),
    )


def _elapsed(delta: timedelta) -> str:
    """Duração legível, sem fuso: um horário em UTC confunde quem está no campo."""
    minutes = max(1, int(delta.total_seconds() // 60))
    if minutes < 90:
        return f"{minutes} min"
    hours = minutes // 60
    if hours < 48:
        return f"{hours} h"
    return f"{hours // 24} dias"


def collect_alerts(session: Session, tenant_id: str, *, days: int = 7) -> list[AlertOut]:
    """Reúne os alertas do cliente. Usado pela rota e pelo painel."""
    now = datetime.now(UTC)
    since = now - timedelta(days=days)
    devices = {
        device.id: device
        for device in session.scalars(select(Device).where(Device.tenant_id == tenant_id))
    }
    found: list[AlertOut] = []

    # Eventos críticos relatados pelos robôs.
    for event in session.scalars(
        select(DeviceEvent)
        .where(
            DeviceEvent.tenant_id == tenant_id,
            DeviceEvent.severity == EventSeverity.CRITICAL,
            DeviceEvent.occurred_at >= since,
        )
        .order_by(DeviceEvent.occurred_at.desc())
        .limit(50)
    ):
        device = devices.get(event.device_id)
        found.append(
            AlertOut(
                id=f"event:{event.id}",
                kind="device_fault",
                severity="critical",
                title=f"{device.name if device else 'Dispositivo'}: {event.type}",
                detail=_summarize(event.payload),
                subject_type="device",
                subject_id=event.device_id,
                at=event.occurred_at,
            )
        )

    # Calda fora da área autorizada: o incidente que a plataforma existe para
    # nunca deixar passar despercebido.
    for application in session.scalars(
        select(Application).where(
            Application.tenant_id == tenant_id,
            Application.outside_polygon_points > 0,
            Application.started_at >= since,
        )
    ):
        found.append(
            AlertOut(
                id=f"application:{application.id}",
                kind="application_out_of_bounds",
                severity="critical",
                title="Aplicação fora da área autorizada",
                detail=(
                    f"{application.outside_polygon_points} ponto(s) da trilha fora do "
                    f"polígono. Verifique o drone antes da próxima missão."
                ),
                subject_type="application",
                subject_id=application.id,
                at=application.started_at,
            )
        )

    # Missões paradas na segurança.
    for mission in session.scalars(
        select(Mission).where(Mission.tenant_id == tenant_id, Mission.state == MissionState.BLOCKED)
    ):
        found.append(
            AlertOut(
                id=f"blocked:{mission.id}",
                kind="mission_blocked",
                severity="warning",
                title=f"Missão de {mission.kind.value} bloqueada pela segurança",
                detail=(mission.safety_reason or "Sem motivo registrado.")[:280],
                subject_type="mission",
                subject_id=mission.id,
                at=mission.updated_at,
            )
        )

    # Robôs ativos sem contato, e com bateria baixa.
    for device in devices.values():
        if device.status is not DeviceStatus.ACTIVE:
            continue
        if not _is_online(device, now):
            last = as_utc(device.last_seen_at)
            found.append(
                AlertOut(
                    id=f"offline:{device.id}",
                    kind="device_offline",
                    severity="warning",
                    title=f"{device.name} sem contato",
                    detail=(
                        f"Sem telemetria há {_elapsed(now - last)}."
                        if last
                        else "Nunca enviou telemetria desde o provisionamento."
                    ),
                    subject_type="device",
                    subject_id=device.id,
                    at=last or device.created_at,
                )
            )
        if (
            device.kind in {DeviceKind.ROVER, DeviceKind.DRONE}
            and device.battery_percent is not None
            and device.battery_percent < settings.safety_min_battery_percent
        ):
            found.append(
                AlertOut(
                    id=f"battery:{device.id}",
                    kind="low_battery",
                    severity="warning",
                    title=f"{device.name} com bateria em {device.battery_percent:.0f}%",
                    detail=(
                        f"Abaixo do mínimo de {settings.safety_min_battery_percent:.0f}% "
                        f"para autorizar missão."
                    ),
                    subject_type="device",
                    subject_id=device.id,
                    at=as_utc(device.last_seen_at) or now,
                )
            )

    # Desvios estatísticos do gêmeo digital — a detecção que funciona quando a
    # de novidade falha.
    fields = list(
        session.scalars(
            select(Field).where(Field.tenant_id == tenant_id).limit(MAX_FIELDS_FOR_ANOMALIES)
        )
    )
    for field_row in fields:
        for anomaly in twin.anomalies(session, tenant_id, field_row.id):
            found.append(
                AlertOut(
                    id=f"anomaly:{field_row.id}:{anomaly.zone_id}:{anomaly.label}",
                    kind="field_anomaly",
                    severity="warning",
                    title=f"{field_row.name}: {anomaly.label} fora do padrão",
                    detail=anomaly.detail,
                    subject_type="field",
                    subject_id=field_row.id,
                    at=now,
                )
            )

    backlog = _review_backlog(session, tenant_id)
    if backlog:
        found.append(
            AlertOut(
                id="review:backlog",
                kind="review_backlog",
                severity="info",
                title=f"{backlog} imagem(ns) aguardando o agrônomo",
                detail=(
                    "O que a máquina não fechou sozinha. É também o material do "
                    "dataset próprio."
                ),
                subject_type="diagnosis",
                subject_id=None,
                at=now,
            )
        )

    for item in verification.due(session, tenant_id, now=now):
        found.append(
            AlertOut(
                id=f"verification:{item.id}",
                kind="verification_due",
                severity="info",
                title="Verificação pós-tratamento na hora",
                detail="Uma segunda passada do rover fecha a comparação antes/depois.",
                subject_type="verification",
                subject_id=item.id,
                at=as_utc(item.scheduled_for) or now,
            )
        )

    found.sort(key=lambda alert: (SEVERITY_RANK[alert.severity], -as_utc(alert.at).timestamp()))
    return found


# ---------------------------------------------------------------------------
# Auxiliares
# ---------------------------------------------------------------------------


def _is_online(device: Device, now: datetime) -> bool:
    last = as_utc(device.last_seen_at)
    return last is not None and now - last <= OFFLINE_AFTER


def _review_backlog(session: Session, tenant_id: str) -> int:
    return (
        session.scalar(
            select(func.count(Diagnosis.id)).where(
                Diagnosis.tenant_id == tenant_id,
                Diagnosis.status.in_([DiagnosisStatus.NEEDS_REVIEW, DiagnosisStatus.INCONCLUSIVE]),
                Diagnosis.reviewed_at.is_(None),
            )
        )
        or 0
    )


def _recent_missions(session: Session, tenant_id: str, limit: int = 8) -> list[MissionBrief]:
    missions = list(
        session.scalars(
            select(Mission)
            .where(Mission.tenant_id == tenant_id)
            .order_by(Mission.created_at.desc())
            .limit(limit)
        )
    )
    if not missions:
        return []

    device_ids = sorted({mission.device_id for mission in missions})
    field_ids = sorted({mission.field_id for mission in missions})
    device_names = dict(
        session.execute(select(Device.id, Device.name).where(Device.id.in_(device_ids))).all()
    )
    field_names = dict(
        session.execute(select(Field.id, Field.name).where(Field.id.in_(field_ids))).all()
    )
    progress = {
        mission_id: (total, done)
        for mission_id, total, done in session.execute(
            select(
                MissionSegment.mission_id,
                func.count(MissionSegment.id),
                func.sum(case((MissionSegment.state == SegmentState.DONE, 1), else_=0)),
            )
            .where(MissionSegment.mission_id.in_([m.id for m in missions]))
            .group_by(MissionSegment.mission_id)
        ).all()
    }
    return [
        MissionBrief(
            id=mission.id,
            kind=mission.kind,
            state=mission.state,
            device_id=mission.device_id,
            device_name=device_names.get(mission.device_id),
            field_id=mission.field_id,
            field_name=field_names.get(mission.field_id),
            created_at=mission.created_at,
            segments_total=int(progress.get(mission.id, (0, 0))[0] or 0),
            segments_done=int(progress.get(mission.id, (0, 0))[1] or 0),
        )
        for mission in missions
    ]


def _event_out(row: DeviceEvent) -> DeviceEventOut:
    return DeviceEventOut(
        id=row.id,
        device_id=row.device_id,
        mission_id=row.mission_id,
        type=row.type,
        severity=row.severity.value,
        sequence_number=row.sequence_number,
        occurred_at=row.occurred_at,
        received_at=row.received_at,
        payload=row.payload or {},
    )


def _summarize(payload: dict | None) -> str:
    if not payload:
        return "Sem detalhes."
    parts = [f"{key}: {value}" for key, value in list(payload.items())[:4]]
    return "; ".join(parts)[:280]
