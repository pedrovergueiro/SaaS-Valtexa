"""Entrada de dados do robô: telemetria, eventos e observações.

Tudo aqui é **idempotente por ``(dispositivo, sequência)``**. Um rover que
passou a manhã sem sinal reenvia o lote inteiro ao reconectar, e parte dele
pode já ter chegado por outro caminho. Reprocessar não pode duplicar nada.

A escolha de projeto que sustenta isso: o servidor não recusa sequência menor
que a última vista. Recusar seria perder dado legítimo que chegou fora de ordem
— o caso normal de uma sincronização offline, não a exceção. O que ele faz é
ignorar o par já gravado e seguir.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from valtexa.models import (
    Connectivity,
    Device,
    DeviceEvent,
    EnergyState,
    EventSeverity,
    Mission,
    Observation,
    RtkFix,
    SubjectType,
    TelemetrySample,
    as_utc,
)
from valtexa.services import events as bus

logger = logging.getLogger(__name__)

OFFLINE_AFTER = timedelta(minutes=5)
"""Sem contato por mais que isso, o dispositivo é considerado offline."""

DEGRADED_AFTER = timedelta(minutes=1)


@dataclass(frozen=True, slots=True)
class IngestResult:
    """O que aconteceu com um lote."""

    accepted: int
    duplicated: int
    rejected: int
    errors: tuple[str, ...] = ()

    @property
    def total(self) -> int:
        return self.accepted + self.duplicated + self.rejected


def ingest_telemetry(
    session: Session, device: Device, samples: list[dict], *, sync_id: str | None = None
) -> IngestResult:
    """Grava amostras de telemetria, ignorando as já conhecidas."""
    seen = _existing_sequences(session, TelemetrySample, device.id, samples)
    accepted = duplicated = rejected = 0
    errors: list[str] = []
    now = datetime.now(UTC)
    latest: dict | None = None

    for sample in samples:
        sequence = sample.get("sequence_number")
        if sequence is None:
            rejected += 1
            errors.append("Amostra sem sequence_number.")
            continue
        if sequence in seen:
            duplicated += 1
            continue

        try:
            row = TelemetrySample(
                tenant_id=device.tenant_id,
                device_id=device.id,
                mission_id=_valid_mission_id(session, device, sample.get("mission_id")),
                sequence_number=int(sequence),
                recorded_at=_parse_time(sample.get("recorded_at"), now),
                received_at=now,
                lat=sample.get("lat"),
                lon=sample.get("lon"),
                alt_m=sample.get("alt_m"),
                heading_deg=sample.get("heading_deg"),
                speed_ms=sample.get("speed_ms"),
                rtk_fix=_enum(RtkFix, sample.get("rtk_fix"), RtkFix.NONE),
                hdop=sample.get("hdop"),
                battery_percent=sample.get("battery_percent"),
                battery_voltage_v=sample.get("battery_voltage_v"),
                battery_current_a=sample.get("battery_current_a"),
                temperature_c=sample.get("temperature_c"),
                energy_state=_enum(EnergyState, sample.get("energy_state"), EnergyState.NORMAL),
                mission_state=sample.get("mission_state"),
                link_quality=sample.get("link_quality"),
                motors=sample.get("motors") or {},
                sensors=sample.get("sensors") or {},
                faults=sample.get("faults") or [],
                sync_id=sync_id,
            )
        except (TypeError, ValueError) as exc:
            rejected += 1
            errors.append(f"Amostra {sequence}: {exc}")
            continue

        session.add(row)
        seen.add(int(sequence))
        accepted += 1
        if latest is None or int(sequence) > latest["sequence_number"]:
            latest = {**sample, "sequence_number": int(sequence)}

    if latest is not None:
        _update_device_snapshot(device, latest, now)
    return IngestResult(accepted, duplicated, rejected, tuple(errors))


def ingest_events(
    session: Session, device: Device, records: list[dict], *, sync_id: str | None = None
) -> IngestResult:
    """Grava eventos do dispositivo e propaga os que o resto do sistema observa."""
    seen = _existing_sequences(session, DeviceEvent, device.id, records)
    accepted = duplicated = rejected = 0
    errors: list[str] = []
    now = datetime.now(UTC)

    for record in records:
        sequence = record.get("sequence_number")
        event_type = record.get("type")
        if sequence is None or not event_type:
            rejected += 1
            errors.append("Evento sem sequence_number ou sem type.")
            continue
        if sequence in seen:
            duplicated += 1
            continue

        row = DeviceEvent(
            tenant_id=device.tenant_id,
            device_id=device.id,
            mission_id=_valid_mission_id(session, device, record.get("mission_id")),
            type=str(event_type),
            severity=_enum(EventSeverity, record.get("severity"), EventSeverity.INFO),
            sequence_number=int(sequence),
            occurred_at=_parse_time(record.get("occurred_at"), now),
            received_at=now,
            payload=record.get("payload") or {},
            sync_id=sync_id,
        )
        session.add(row)
        seen.add(int(sequence))
        accepted += 1

        if row.severity is EventSeverity.CRITICAL:
            bus.publish(
                session,
                bus.DEVICE_FAULT,
                tenant_id=device.tenant_id,
                subject_type=SubjectType.DEVICE,
                subject_id=device.id,
                payload={"type": row.type, **row.payload},
            )

    return IngestResult(accepted, duplicated, rejected, tuple(errors))


def observation_exists(session: Session, device_id: str, sequence_number: int | None) -> bool:
    """Se já existe observação com esta sequência deste dispositivo."""
    if sequence_number is None:
        return False
    return (
        session.scalars(
            select(Observation.id)
            .where(
                Observation.device_id == device_id,
                Observation.sequence_number == sequence_number,
            )
            .limit(1)
        ).first()
        is not None
    )


def bump_watermark(device: Device, sequence_number: int | None) -> None:
    """Sobe a marca d'água do dispositivo, nunca a baixa."""
    if sequence_number is not None and sequence_number > device.last_sequence_number:
        device.last_sequence_number = int(sequence_number)


def refresh_connectivity(session: Session, device: Device, *, now: datetime | None = None) -> None:
    """Reclassifica o enlace pelo tempo desde o último contato."""
    moment = now or datetime.now(UTC)
    last_seen = as_utc(device.last_seen_at)
    previous = device.connectivity

    if last_seen is None or moment - last_seen > OFFLINE_AFTER:
        device.connectivity = Connectivity.OFFLINE
    elif moment - last_seen > DEGRADED_AFTER:
        device.connectivity = Connectivity.DEGRADED
    else:
        device.connectivity = Connectivity.OK

    if previous is not Connectivity.OFFLINE and device.connectivity is Connectivity.OFFLINE:
        bus.publish(
            session,
            bus.DEVICE_OFFLINE,
            tenant_id=device.tenant_id,
            subject_type=SubjectType.DEVICE,
            subject_id=device.id,
            payload={"last_seen_at": last_seen.isoformat() if last_seen else None},
        )


def _update_device_snapshot(device: Device, sample: dict, now: datetime) -> None:
    """Atualiza a última posição conhecida do dispositivo.

    Duplicar a telemetria aqui é deliberado: a tela da frota precisa de uma
    leitura por dispositivo, não de um ``MAX()`` sobre milhões de amostras.
    """
    device.last_seen_at = now
    device.connectivity = Connectivity.OK
    for field_name, key in (
        ("last_lat", "lat"),
        ("last_lon", "lon"),
        ("last_alt_m", "alt_m"),
        ("battery_percent", "battery_percent"),
    ):
        value = sample.get(key)
        if value is not None:
            setattr(device, field_name, value)
    bump_watermark(device, sample.get("sequence_number"))


def _existing_sequences(
    session: Session, model: type, device_id: str, records: list[dict]
) -> set[int]:
    """Sequências já gravadas, buscadas de uma vez.

    Uma consulta por registro faria a sincronização de um lote de mil amostras
    custar mil viagens ao banco.
    """
    wanted = {
        int(record["sequence_number"])
        for record in records
        if isinstance(record.get("sequence_number"), int | float | str)
        and str(record["sequence_number"]).lstrip("-").isdigit()
    }
    if not wanted:
        return set()
    rows = session.scalars(
        select(model.sequence_number).where(
            model.device_id == device_id, model.sequence_number.in_(wanted)
        )
    )
    return set(rows)


def _valid_mission_id(session: Session, device: Device, mission_id: object) -> str | None:
    """Aceita o vínculo com a missão só se ela existir e for deste dispositivo.

    Um identificador inválido violaria a chave estrangeira e derrubaria o lote
    inteiro; um identificador de outro robô contaminaria o histórico dele.
    """
    if not isinstance(mission_id, str) or not mission_id:
        return None
    mission = session.get(Mission, mission_id)
    if mission is None or mission.device_id != device.id:
        logger.warning(
            "Dispositivo %s citou missão %r que não é dele; vínculo ignorado.",
            device.serial_number,
            mission_id,
        )
        return None
    return mission_id


def _parse_time(value: object, fallback: datetime) -> datetime:
    if isinstance(value, datetime):
        return as_utc(value) or fallback
    if isinstance(value, str):
        try:
            return as_utc(datetime.fromisoformat(value)) or fallback
        except ValueError:
            return fallback
    return fallback


def _enum(enum_cls: type, value: object, default: object) -> object:
    if value is None:
        return default
    try:
        return enum_cls(value)
    except ValueError:
        return default
