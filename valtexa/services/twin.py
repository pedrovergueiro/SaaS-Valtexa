"""Gêmeo digital da lavoura.

O gêmeo tem duas camadas. A cópia 3D — as plantas medidas rua a rua pelo rover,
com as fotos presas a elas — está em :mod:`valtexa.services.scene`. Aqui fica a
outra: a resposta a *o que mudou desde a última passada*. Cada observação está
amarrada a um ponto e a um instante, então o histórico de um talhão é uma
consulta, não um relatório montado à mão.

A série temporal é o que dá valor. Uma foto de hoje diz que há ferrugem; a série
diz que a incidência saiu de 4% para 31% em nove dias — e essa é a informação
que muda a decisão do produtor.

**É também a única defesa que funciona contra o limite medido do modelo.** Uma
doença fora do catálogo é respondida com alta confiança e passa pelos filtros
(``VALTEXA-B/MODELS.md``: 19% interceptados). O que ela *não* consegue esconder é
a estatística: se um talhão sempre deu 5% de ferrugem e passa a dar 40%, alguma
coisa aconteceu — mesmo com cada imagem parecendo confiante e normal.
:func:`anomalies` procura exatamente isso.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from valtexa.models import Diagnosis, DiagnosisStatus, Field, Observation, Zone

BASELINE_MIN_SAMPLE = 30
"""Observações mínimas na linha de base antes de acusar desvio.

Abaixo disso, a variação normal de amostragem produziria alarme toda semana.
"""

ANOMALY_RATIO = 3.0
"""Quantas vezes a incidência precisa crescer para virar anomalia."""

ANOMALY_FLOOR = 0.10
"""Piso absoluto: 1% virando 3% é ruído; a incidência precisa ter tamanho."""


@dataclass(frozen=True, slots=True)
class ClassCount:
    label: str
    count: int
    ratio: float


@dataclass(frozen=True, slots=True)
class FieldSnapshot:
    """O estado de um talhão numa janela de tempo."""

    field_id: str
    field_name: str
    crop: str
    since: datetime
    until: datetime
    observations: int
    diagnosed: int
    needs_review: int
    classes: tuple[ClassCount, ...]

    @property
    def dominant(self) -> ClassCount | None:
        return self.classes[0] if self.classes else None


@dataclass(frozen=True, slots=True)
class TimePoint:
    """Um ponto da série temporal."""

    day: date
    total: int
    counts: dict[str, int]

    def ratio(self, label: str) -> float:
        return self.counts.get(label, 0) / self.total if self.total else 0.0


@dataclass(frozen=True, slots=True)
class Anomaly:
    """Um desvio estatístico digno de atenção humana."""

    field_id: str
    zone_id: str | None
    label: str
    baseline_ratio: float
    current_ratio: float
    baseline_sample: int
    current_sample: int
    detail: str


def field_snapshot(
    session: Session, tenant_id: str, field_id: str, *, days: int = 7
) -> FieldSnapshot:
    """Retrato do talhão nos últimos ``days`` dias."""
    until = datetime.now(UTC)
    since = until - timedelta(days=days)
    field_row = session.get(Field, field_id)

    observations = session.scalar(
        select(func.count(Observation.id)).where(
            Observation.tenant_id == tenant_id,
            Observation.field_id == field_id,
            Observation.captured_at >= since,
        )
    )
    diagnoses = list(
        session.scalars(
            select(Diagnosis).where(
                Diagnosis.tenant_id == tenant_id,
                Diagnosis.field_id == field_id,
                Diagnosis.created_at >= since,
            )
        )
    )

    counts = Counter(row.effective_label for row in diagnoses if row.effective_label)
    total = sum(counts.values())
    classes = tuple(
        ClassCount(label=label, count=count, ratio=count / total if total else 0.0)
        for label, count in counts.most_common()
    )

    return FieldSnapshot(
        field_id=field_id,
        field_name=field_row.name if field_row else field_id,
        crop=field_row.crop if field_row else "",
        since=since,
        until=until,
        observations=observations or 0,
        diagnosed=len(diagnoses),
        needs_review=sum(
            1 for row in diagnoses if row.status is DiagnosisStatus.NEEDS_REVIEW
        ),
        classes=classes,
    )


def timeline(
    session: Session, tenant_id: str, field_id: str, *, days: int = 30
) -> list[TimePoint]:
    """Série diária de diagnósticos do talhão, do mais antigo ao mais recente."""
    since = datetime.now(UTC) - timedelta(days=days)
    rows = session.scalars(
        select(Diagnosis)
        .where(
            Diagnosis.tenant_id == tenant_id,
            Diagnosis.field_id == field_id,
            Diagnosis.created_at >= since,
        )
        .order_by(Diagnosis.created_at)
    )

    per_day: dict[date, Counter] = defaultdict(Counter)
    for row in rows:
        label = row.effective_label
        if label:
            per_day[row.created_at.date()][label] += 1

    return [
        TimePoint(day=day, total=sum(counter.values()), counts=dict(counter))
        for day, counter in sorted(per_day.items())
    ]


def anomalies(
    session: Session,
    tenant_id: str,
    field_id: str,
    *,
    current_days: int = 7,
    baseline_days: int = 30,
) -> list[Anomaly]:
    """Compara a janela recente com a linha de base e aponta o que saltou.

    É a detecção que funciona quando a de novidade falha. Ela não olha a imagem:
    olha a distribuição. Uma doença nova classificada com confiança como
    "ferrugem comum" continua invisível quadro a quadro — mas faz a ferrugem
    comum daquele talhão triplicar de uma semana para a outra, e isso aparece
    aqui.

    O que ela **não** faz é dizer *o que* mudou. Ela diz que mudou, e manda um
    agrônomo olhar. Para o modo de falha que ela cobre, é o suficiente.
    """
    now = datetime.now(UTC)
    current_since = now - timedelta(days=current_days)
    baseline_since = now - timedelta(days=baseline_days + current_days)

    baseline = _counts_between(session, tenant_id, field_id, baseline_since, current_since)
    current = _counts_between(session, tenant_id, field_id, current_since, now)

    baseline_total = sum(sum(counter.values()) for counter in baseline.values())
    if baseline_total < BASELINE_MIN_SAMPLE:
        return []

    found: list[Anomaly] = []
    for zone_id, current_counter in current.items():
        current_total = sum(current_counter.values())
        if current_total < BASELINE_MIN_SAMPLE // 3:
            continue
        baseline_counter = baseline.get(zone_id, Counter())
        baseline_total_zone = sum(baseline_counter.values())
        if baseline_total_zone < BASELINE_MIN_SAMPLE // 3:
            continue

        for label, count in current_counter.items():
            current_ratio = count / current_total
            baseline_ratio = baseline_counter.get(label, 0) / baseline_total_zone
            if current_ratio < ANOMALY_FLOOR:
                continue
            # Uma classe ausente na base não tem razão definida; tratamos o
            # aparecimento acima do piso como desvio por si só.
            grew = baseline_ratio == 0.0 or current_ratio / baseline_ratio >= ANOMALY_RATIO
            if not grew:
                continue
            found.append(
                Anomaly(
                    field_id=field_id,
                    zone_id=zone_id,
                    label=label,
                    baseline_ratio=round(baseline_ratio, 4),
                    current_ratio=round(current_ratio, 4),
                    baseline_sample=baseline_total_zone,
                    current_sample=current_total,
                    detail=(
                        f"{label}: {baseline_ratio:.1%} → {current_ratio:.1%} em "
                        f"{current_days} dias. Vale uma inspeção presencial."
                    ),
                )
            )
    return sorted(found, key=lambda item: item.current_ratio, reverse=True)


def zones_of(session: Session, tenant_id: str, field_id: str) -> list[Zone]:
    return list(
        session.scalars(
            select(Zone).where(Zone.tenant_id == tenant_id, Zone.field_id == field_id)
        )
    )


def _counts_between(
    session: Session, tenant_id: str, field_id: str, since: datetime, until: datetime
) -> dict[str | None, Counter]:
    """Contagem de rótulos por zona, na janela."""
    rows = session.scalars(
        select(Diagnosis).where(
            Diagnosis.tenant_id == tenant_id,
            Diagnosis.field_id == field_id,
            Diagnosis.created_at >= since,
            Diagnosis.created_at < until,
        )
    )
    per_zone: dict[str | None, Counter] = defaultdict(Counter)
    for row in rows:
        label = row.effective_label
        if label:
            per_zone[row.zone_id][label] += 1
    return per_zone
