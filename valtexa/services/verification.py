"""Verificação pós-tratamento.

Depois de uma aplicação, o rover volta ao mesmo lugar e a plataforma compara. A
regra central é negativa: **nada é declarado eficaz sem evidência**. Enquanto não
existir uma segunda passada de fato, a conclusão fica ``PENDING`` — não
"provavelmente funcionou".

Declarar sucesso por padrão seria a forma mais rápida de queimar a confiança do
produtor, porque ele vai até o talhão e olha.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from valtexa.models import (
    Application,
    Diagnosis,
    Product,
    SubjectType,
    Verification,
    VerificationConclusion,
    as_utc,
)
from valtexa.services import events

DEFAULT_WAIT_HOURS = 168.0
"""Sete dias. Um fungicida não mostra efeito visível em menos que isso, e uma
verificação cedo demais registraria "sem mudança" para um tratamento que estava
funcionando.
"""

MIN_SAMPLE = 8
"""Observações mínimas em cada janela para a comparação significar algo."""

IMPROVEMENT = 0.30
"""Redução relativa a partir da qual se declara melhora."""

WORSENING = -0.20


def schedule(session: Session, application: Application) -> Verification:
    """Agenda a verificação de uma aplicação, respeitando a reentrada.

    O intervalo de reentrada da bula não é burocracia: mandar o rover antes do
    prazo é expor o equipamento — e quem for buscá-lo — a resíduo.
    """
    product = session.get(Product, application.product_id) if application.product_id else None
    wait_hours = max(
        DEFAULT_WAIT_HOURS, (product.reentry_interval_h or 0.0) if product else 0.0
    )
    started = as_utc(application.started_at) or datetime.now(UTC)

    verification = Verification(
        tenant_id=application.tenant_id,
        application_id=application.id,
        field_id=application.field_id,
        zone_id=application.zone_id,
        scheduled_for=started + timedelta(hours=wait_hours),
        conclusion=VerificationConclusion.PENDING,
    )
    verification.before_ratio, verification.before_sample = _incidence_before(
        session, application
    )
    session.add(verification)

    events.publish(
        session,
        events.VERIFICATION_SCHEDULED,
        tenant_id=application.tenant_id,
        subject_type=SubjectType.VERIFICATION,
        subject_id=application.id,
        payload={
            "application_id": application.id,
            "scheduled_for": verification.scheduled_for.isoformat(),
        },
    )
    return verification


def due(session: Session, tenant_id: str, *, now: datetime | None = None) -> list[Verification]:
    """Verificações cuja hora chegou e que ainda não foram concluídas."""
    moment = now or datetime.now(UTC)
    return list(
        session.scalars(
            select(Verification).where(
                Verification.tenant_id == tenant_id,
                Verification.conclusion == VerificationConclusion.PENDING,
                Verification.scheduled_for <= moment,
            )
        )
    )


def conclude(
    session: Session, verification: Verification, *, now: datetime | None = None
) -> Verification:
    """Fecha a verificação comparando antes e depois.

    Amostra insuficiente vira ``INCONCLUSIVE``, nunca ``UNCHANGED``. As duas
    frases são diferentes: "não mudou" é um resultado; "não sei" é a ausência
    dele, e confundi-las inventaria eficácia onde não há medida.
    """
    moment = now or datetime.now(UTC)
    application = session.get(Application, verification.application_id)
    if application is None:
        verification.conclusion = VerificationConclusion.INCONCLUSIVE
        verification.notes = "Aplicação de origem não encontrada."
        return verification

    after_ratio, after_sample = _incidence_after(session, application, verification, moment)
    verification.after_ratio = after_ratio
    verification.after_sample = after_sample

    before = verification.before_ratio
    if (
        before is None
        or after_ratio is None
        or (verification.before_sample or 0) < MIN_SAMPLE
        or after_sample < MIN_SAMPLE
    ):
        verification.conclusion = VerificationConclusion.INCONCLUSIVE
        verification.notes = (
            f"Amostra insuficiente (antes: {verification.before_sample}, "
            f"depois: {after_sample}; mínimo {MIN_SAMPLE} em cada). "
            f"Sem base para afirmar eficácia."
        )
        _publish_conclusion(session, verification, application)
        return verification

    if before == 0.0:
        verification.effectiveness = 0.0 if after_ratio == 0.0 else -1.0
    else:
        verification.effectiveness = round((before - after_ratio) / before, 4)

    effectiveness = verification.effectiveness or 0.0
    if effectiveness >= IMPROVEMENT:
        verification.conclusion = VerificationConclusion.IMPROVED
    elif effectiveness <= WORSENING:
        verification.conclusion = VerificationConclusion.WORSENED
    else:
        verification.conclusion = VerificationConclusion.UNCHANGED

    verification.notes = (
        f"Incidência {before:.1%} → {after_ratio:.1%} "
        f"({verification.before_sample} → {after_sample} observações)."
    )
    application.verified = True
    _publish_conclusion(session, verification, application)
    return verification


def _incidence_before(session: Session, application: Application) -> tuple[float | None, int]:
    """Incidência do alvo na zona, na janela anterior à aplicação."""
    started = as_utc(application.started_at) or datetime.now(UTC)
    return _incidence(session, application, started - timedelta(days=7), started)


def _incidence_after(
    session: Session, application: Application, verification: Verification, now: datetime
) -> tuple[float | None, int]:
    scheduled = as_utc(verification.scheduled_for) or now
    stopped = as_utc(application.stopped_at) or as_utc(application.started_at) or now
    # A janela começa no fim da aplicação para não recontar o estado anterior.
    return _incidence(session, application, stopped, max(now, scheduled))


def _incidence(
    session: Session, application: Application, since: datetime, until: datetime
) -> tuple[float | None, int]:
    """Fração de diagnósticos com o alvo tratado, na zona e na janela."""
    target = _target_label(session, application)
    statement = select(Diagnosis).where(
        Diagnosis.tenant_id == application.tenant_id,
        Diagnosis.field_id == application.field_id,
        Diagnosis.created_at >= since,
        Diagnosis.created_at <= until,
    )
    if application.zone_id:
        statement = statement.where(Diagnosis.zone_id == application.zone_id)

    rows = list(session.scalars(statement))
    if not rows:
        return None, 0
    if target is None:
        return None, len(rows)
    affected = sum(1 for row in rows if row.effective_label == target)
    return affected / len(rows), len(rows)


def _target_label(session: Session, application: Application) -> str | None:
    """O alvo tratado, lido da missão que originou a aplicação."""
    from valtexa.models import Decision, Mission  # import local: evita ciclo

    mission = session.get(Mission, application.mission_id)
    if mission is None or not mission.decision_id:
        return None
    decision = session.get(Decision, mission.decision_id)
    if decision is None or not decision.diagnosis_id:
        return None
    diagnosis = session.get(Diagnosis, decision.diagnosis_id)
    return diagnosis.effective_label if diagnosis else None


def _publish_conclusion(
    session: Session, verification: Verification, application: Application
) -> None:
    events.publish(
        session,
        events.VERIFICATION_COMPLETED,
        tenant_id=verification.tenant_id,
        subject_type=SubjectType.VERIFICATION,
        subject_id=verification.id,
        payload={
            "application_id": application.id,
            "conclusion": verification.conclusion.value,
            "effectiveness": verification.effectiveness,
        },
    )
