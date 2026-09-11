"""Barramento de eventos com *outbox* transacional.

O problema que isto resolve: se a plataforma mudasse o estado no banco e depois
avisasse os interessados, um processo que morre no meio deixaria o sistema num
estado que ninguém observou — missão autorizada e nunca despachada, aplicação
concluída e nunca verificada.

A solução é gravar o evento na **mesma transação** que mudou o estado. Ou os
dois acontecem, ou nenhum. A entrega vem depois, de um processo que lê a tabela.

Consequência que todo handler precisa respeitar: a entrega é **ao menos uma
vez**. Um processo que morre entre entregar e marcar como entregue vai entregar
de novo. Handler não idempotente aqui vira aplicação duplicada no campo.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from valtexa.models import OutboxEvent, SubjectType

logger = logging.getLogger(__name__)

Handler = Callable[[Session, OutboxEvent], None]

_HANDLERS: dict[str, list[Handler]] = {}

MAX_ATTEMPTS = 8
"""Depois disso o evento para de ser tentado e fica visível como falha.

Repetir para sempre um evento quebrado transformaria a fila num laço infinito
que atrasa todos os outros.
"""


def publish(
    session: Session,
    name: str,
    *,
    tenant_id: str | None = None,
    subject_type: SubjectType | None = None,
    subject_id: str | None = None,
    payload: dict | None = None,
) -> OutboxEvent:
    """Enfileira um evento. Não faz *commit*: participa da transação de quem chamou."""
    event = OutboxEvent(
        tenant_id=tenant_id,
        name=name,
        subject_type=subject_type,
        subject_id=subject_id,
        payload=payload or {},
    )
    session.add(event)
    return event


def subscribe(name: str, handler: Handler) -> None:
    """Registra um handler para um nome de evento."""
    _HANDLERS.setdefault(name, []).append(handler)


def on(name: str) -> Callable[[Handler], Handler]:
    """Decorador equivalente a :func:`subscribe`."""

    def wrapper(handler: Handler) -> Handler:
        subscribe(name, handler)
        return handler

    return wrapper


def handlers_for(name: str) -> list[Handler]:
    return list(_HANDLERS.get(name, ()))


def pending(session: Session, limit: int = 100) -> list[OutboxEvent]:
    """Eventos ainda não entregues, do mais antigo ao mais novo."""
    statement = (
        select(OutboxEvent)
        .where(OutboxEvent.delivered_at.is_(None), OutboxEvent.attempts < MAX_ATTEMPTS)
        .order_by(OutboxEvent.created_at)
        .limit(limit)
    )
    return list(session.scalars(statement))


def drain(session: Session, limit: int = 100) -> int:
    """Entrega os eventos pendentes. Devolve quantos foram entregues.

    Cada evento é confirmado isoladamente: um handler que falha não impede a
    entrega dos demais nem faz o lote inteiro voltar para a fila.
    """
    delivered = 0
    for event in pending(session, limit):
        event.attempts += 1
        try:
            for handler in handlers_for(event.name):
                handler(session, event)
        except Exception as exc:
            event.last_error = f"{type(exc).__name__}: {exc}"
            logger.exception("Falha ao entregar evento %s (%s)", event.name, event.id)
            session.commit()
            continue
        event.delivered_at = datetime.now(UTC)
        event.last_error = None
        session.commit()
        delivered += 1
    return delivered


def purge_delivered(session: Session, older_than_days: int = 30) -> int:
    """Remove eventos já entregues e antigos. Devolve quantos saíram."""
    cutoff = datetime.now(UTC) - timedelta(days=older_than_days)
    statement = select(OutboxEvent).where(
        OutboxEvent.delivered_at.is_not(None), OutboxEvent.created_at < cutoff
    )
    removed = 0
    for event in session.scalars(statement):
        session.delete(event)
        removed += 1
    session.commit()
    return removed


# --- vocabulário -------------------------------------------------------------
# Um nome novo entra aqui e em docs/EVENTS.md, nunca só na chamada.

OBSERVATION_CREATED = "observation.created"
DIAGNOSIS_CREATED = "diagnosis.created"
DIAGNOSIS_VALIDATED = "diagnosis.validated"
DIAGNOSIS_NEEDS_REVIEW = "diagnosis.needs_review"
DIAGNOSIS_REVIEWED = "diagnosis.reviewed"
NOVELTY_DETECTED = "novelty.detected"
DECISION_CREATED = "decision.created"
SAFETY_APPROVED = "safety.approved"
SAFETY_BLOCKED = "safety.blocked"
MISSION_CREATED = "mission.created"
MISSION_AUTHORIZED = "mission.authorized"
MISSION_DISPATCHED = "mission.dispatched"
MISSION_STARTED = "mission.started"
MISSION_PAUSED = "mission.paused"
MISSION_RESUMED = "mission.resumed"
MISSION_COMPLETED = "mission.completed"
MISSION_ABORTED = "mission.aborted"
MISSION_EXPIRED = "mission.expired"
APPLICATION_STARTED = "application.started"
APPLICATION_COMPLETED = "application.completed"
APPLICATION_OUT_OF_BOUNDS = "application.out_of_bounds"
VERIFICATION_SCHEDULED = "verification.scheduled"
VERIFICATION_COMPLETED = "verification.completed"
DEVICE_PROVISIONED = "device.provisioned"
DEVICE_OFFLINE = "device.offline"
DEVICE_FAULT = "device.fault"
