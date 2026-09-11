"""Retenção de dados: agregar telemetria antiga e limpar o que venceu.

A telemetria crua é a tabela que mais cresce — um rover a 1 Hz produz ~14 mil
amostras por jornada. Depois de ``TELEMETRY_RETENTION_DAYS`` ela vira uma linha
por minuto em :class:`~valtexa.models.operations.TelemetryRollup`, com o que um
relatório ainda precisa, e a amostra crua sai.

O que **nunca** é agregado nem apagado aqui: eventos de dispositivo e auditoria.
Telemetria é amostragem; evento é o registro que a fiscalização vai pedir.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from valtexa.config import settings
from valtexa.models import RtkFix, TelemetryRollup, TelemetrySample, UsedNonce, as_utc
from valtexa.services import events

BUCKET_SECONDS = 60
"""Largura da janela de agregação."""

BATCH = 5000
"""Amostras processadas por transação.

Agregar um dispositivo inteiro de uma vez carregaria meses de telemetria na
memória. Em lotes, o custo fica limitado e um processo interrompido no meio
retoma de onde parou: o que já foi agregado já foi apagado.
"""

EVENT_RETENTION_DAYS = 30


@dataclass(frozen=True, slots=True)
class RetentionReport:
    buckets_written: int
    samples_rolled_up: int
    nonces_purged: int
    events_purged: int


def run(session: Session, *, now: datetime | None = None) -> RetentionReport:
    """Executa toda a política de retenção."""
    written, rolled = rollup_telemetry(session, now=now)
    nonces = purge_nonces(session, now=now)
    purged = events.purge_delivered(session, older_than_days=EVENT_RETENTION_DAYS)
    return RetentionReport(written, rolled, nonces, purged)


def rollup_telemetry(
    session: Session,
    *,
    older_than_days: int | None = None,
    bucket_seconds: int = BUCKET_SECONDS,
    now: datetime | None = None,
) -> tuple[int, int]:
    """Agrega a telemetria mais velha que a janela. Devolve (janelas, amostras)."""
    moment = now or datetime.now(UTC)
    days = settings.telemetry_retention_days if older_than_days is None else older_than_days
    cutoff = moment - timedelta(days=days)

    device_ids = list(
        session.scalars(
            select(TelemetrySample.device_id)
            .where(TelemetrySample.recorded_at < cutoff)
            .distinct()
        )
    )

    written = rolled = 0
    for device_id in device_ids:
        while True:
            rows = list(
                session.scalars(
                    select(TelemetrySample)
                    .where(
                        TelemetrySample.device_id == device_id,
                        TelemetrySample.recorded_at < cutoff,
                    )
                    .order_by(TelemetrySample.recorded_at)
                    .limit(BATCH)
                )
            )
            if not rows:
                break

            groups: dict[datetime, list[TelemetrySample]] = defaultdict(list)
            for row in rows:
                groups[_bucket_start(as_utc(row.recorded_at), bucket_seconds)].append(row)

            # Uma janela pode ter ficado dividida entre dois lotes; a segunda
            # metade se soma à primeira em vez de criar uma linha duplicada.
            existing = {
                as_utc(rollup.bucket_start): rollup
                for rollup in session.scalars(
                    select(TelemetryRollup).where(
                        TelemetryRollup.device_id == device_id,
                        TelemetryRollup.bucket_start.in_(list(groups)),
                    )
                )
            }
            for start, samples in groups.items():
                rollup = existing.get(start)
                if rollup is None:
                    rollup = TelemetryRollup(
                        tenant_id=samples[0].tenant_id,
                        device_id=device_id,
                        bucket_start=start,
                        bucket_seconds=bucket_seconds,
                        samples=0,
                    )
                    session.add(rollup)
                    written += 1
                _merge(rollup, samples)

            session.execute(
                delete(TelemetrySample).where(TelemetrySample.id.in_([row.id for row in rows]))
            )
            session.commit()
            rolled += len(rows)

    return written, rolled


def purge_nonces(session: Session, *, now: datetime | None = None) -> int:
    """Remove nonces cuja janela de repetição já fechou.

    A requisição que os usou já seria recusada pela idade, então guardá-los não
    protege mais nada.
    """
    moment = now or datetime.now(UTC)
    result = session.execute(delete(UsedNonce).where(UsedNonce.expires_at < moment))
    session.commit()
    return result.rowcount or 0


def _bucket_start(moment: datetime, seconds: int) -> datetime:
    epoch = int(moment.timestamp())
    return datetime.fromtimestamp(epoch - epoch % seconds, tz=UTC)


def _merge(rollup: TelemetryRollup, samples: list[TelemetrySample]) -> None:
    """Soma amostras a uma janela, mantendo médias ponderadas pela contagem.

    A ponderação usa o total de amostras da janela, não o de valores presentes em
    cada campo. Quando um campo falta em parte das amostras a média sai com um
    viés pequeno — aceitável para o que a janela agregada serve: tendência, não
    auditoria.
    """
    previous = rollup.samples

    battery = [s.battery_percent for s in samples if s.battery_percent is not None]
    if battery:
        rollup.battery_min = _pick(min, rollup.battery_min, min(battery))
        rollup.battery_max = _pick(max, rollup.battery_max, max(battery))
    rollup.battery_avg = _weighted(rollup.battery_avg, previous, battery)
    rollup.speed_avg_ms = _weighted(
        rollup.speed_avg_ms, previous, [s.speed_ms for s in samples if s.speed_ms is not None]
    )
    rollup.link_quality_avg = _weighted(
        rollup.link_quality_avg,
        previous,
        [s.link_quality for s in samples if s.link_quality is not None],
    )
    rollup.rtk_fixed_ratio = _weighted(
        rollup.rtk_fixed_ratio,
        previous,
        [1.0 if s.rtk_fix is RtkFix.FIXED else 0.0 for s in samples],
    )

    positioned = [s for s in samples if s.lat is not None and s.lon is not None]
    if positioned:
        rollup.last_lat = positioned[-1].lat
        rollup.last_lon = positioned[-1].lon

    rollup.samples = previous + len(samples)


def _pick(chooser, current: float | None, candidate: float) -> float:
    return candidate if current is None else chooser(current, candidate)


def _weighted(current: float | None, current_n: int, values: list[float]) -> float | None:
    if not values:
        return current
    average = sum(values) / len(values)
    if current is None or current_n == 0:
        return average
    return (current * current_n + average * len(values)) / (current_n + len(values))
