"""Gêmeo digital, auditoria e barramento de eventos."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from valtexa.api.deps import Principal, get_scoped, require
from valtexa.db import get_session
from valtexa.models import AuditEntry, Field, OutboxEvent
from valtexa.schemas import (
    AnomalyOut,
    AuditOut,
    ClassCountOut,
    FieldSnapshotOut,
    OutboxEventOut,
    TimePointOut,
)
from valtexa.security import rbac
from valtexa.services import twin

router = APIRouter(tags=["gêmeo digital"])


@router.get(
    "/fields/{field_id}/snapshot",
    response_model=FieldSnapshotOut,
    summary="Estado atual de um talhão",
)
def snapshot(
    field_id: str,
    days: int = Query(default=7, ge=1, le=90),
    principal: Principal = Depends(require(rbac.FARM_READ)),
    session: Session = Depends(get_session),
) -> FieldSnapshotOut:
    """Retrato do talhão na janela pedida."""
    get_scoped(session, Field, field_id, principal)
    data = twin.field_snapshot(session, principal.tenant_id, field_id, days=days)
    return FieldSnapshotOut(
        field_id=data.field_id,
        field_name=data.field_name,
        crop=data.crop,
        since=data.since,
        until=data.until,
        observations=data.observations,
        diagnosed=data.diagnosed,
        needs_review=data.needs_review,
        classes=[
            ClassCountOut(label=item.label, count=item.count, ratio=item.ratio)
            for item in data.classes
        ],
    )


@router.get(
    "/fields/{field_id}/timeline",
    response_model=list[TimePointOut],
    summary="Série temporal do talhão",
)
def timeline(
    field_id: str,
    days: int = Query(default=30, ge=1, le=365),
    principal: Principal = Depends(require(rbac.FARM_READ)),
    session: Session = Depends(get_session),
) -> list[TimePointOut]:
    """Evolução diária dos diagnósticos.

    É a informação que muda a decisão do produtor. Uma foto diz que há ferrugem;
    a série diz que a incidência saiu de 4% para 31% em nove dias.
    """
    get_scoped(session, Field, field_id, principal)
    points = twin.timeline(session, principal.tenant_id, field_id, days=days)
    return [TimePointOut(day=p.day, total=p.total, counts=p.counts) for p in points]


@router.get(
    "/fields/{field_id}/anomalies",
    response_model=list[AnomalyOut],
    summary="Desvios estatísticos do talhão",
)
def anomalies(
    field_id: str,
    current_days: int = Query(default=7, ge=1, le=90),
    baseline_days: int = Query(default=30, ge=7, le=365),
    principal: Principal = Depends(require(rbac.FARM_READ)),
    session: Session = Depends(get_session),
) -> list[AnomalyOut]:
    """Compara a janela recente com a linha de base do próprio talhão.

    **É a detecção que funciona quando a de novidade falha.** Está medido em
    ``VALTEXA-B/MODELS.md``: diante de uma doença real fora do catálogo, os
    filtros de novidade e confiança interceptam 19% dos casos — o modelo
    responde com 0,88 de confiança média e o erro passa. Uma imagem por vez, não
    há como notar.

    O que o erro **não** consegue esconder é a estatística. Uma doença nova
    classificada consistentemente como "ferrugem comum" faz a ferrugem comum
    daquele talhão saltar de 5% para 40% de uma semana para a outra, e é
    exatamente isso que esta rota procura.

    O que ela não faz é dizer *o que* mudou. Ela diz que mudou e manda um
    agrônomo olhar — para o modo de falha que cobre, é o suficiente.
    """
    get_scoped(session, Field, field_id, principal)
    found = twin.anomalies(
        session,
        principal.tenant_id,
        field_id,
        current_days=current_days,
        baseline_days=baseline_days,
    )
    return [
        AnomalyOut(
            field_id=item.field_id,
            zone_id=item.zone_id,
            label=item.label,
            baseline_ratio=item.baseline_ratio,
            current_ratio=item.current_ratio,
            baseline_sample=item.baseline_sample,
            current_sample=item.current_sample,
            detail=item.detail,
        )
        for item in found
    ]


@router.get("/audit", response_model=list[AuditOut], summary="Trilha de auditoria")
def audit_log(
    subject_type: str | None = None,
    subject_id: str | None = None,
    action: str | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
    principal: Principal = Depends(require(rbac.AUDIT_READ)),
    session: Session = Depends(get_session),
) -> list[AuditOut]:
    """Quem fez o quê, quando e por quê.

    É a resposta à pergunta que a fiscalização faz: "por que este produto foi
    aplicado neste talhão neste dia?".
    """
    statement = (
        select(AuditEntry)
        .where(AuditEntry.tenant_id == principal.tenant_id)
        .order_by(AuditEntry.at.desc())
        .limit(limit)
    )
    if subject_type:
        statement = statement.where(AuditEntry.subject_type == subject_type)
    if subject_id:
        statement = statement.where(AuditEntry.subject_id == subject_id)
    if action:
        statement = statement.where(AuditEntry.action == action)

    return [
        AuditOut(
            id=row.id,
            at=row.at,
            actor_type=str(row.actor_type),
            actor_id=row.actor_id,
            actor_label=row.actor_label,
            action=row.action,
            subject_type=str(row.subject_type),
            subject_id=row.subject_id,
            old_state=row.old_state,
            new_state=row.new_state,
            reason=row.reason,
            rule_version=row.rule_version,
            model_version=row.model_version,
            payload=row.payload,
        )
        for row in session.scalars(statement)
    ]


@router.get("/events", response_model=list[OutboxEventOut], summary="Eventos de domínio")
def list_events(
    pending_only: bool = False,
    limit: int = Query(default=100, ge=1, le=1000),
    principal: Principal = Depends(require(rbac.AUDIT_READ)),
    session: Session = Depends(get_session),
) -> list[OutboxEventOut]:
    """Fila do *outbox*.

    Exposta para operação: um evento parado com ``last_error`` preenchido é a
    primeira pista de que uma integração quebrou.
    """
    statement = (
        select(OutboxEvent)
        .where(OutboxEvent.tenant_id == principal.tenant_id)
        .order_by(OutboxEvent.created_at.desc())
        .limit(limit)
    )
    if pending_only:
        statement = statement.where(OutboxEvent.delivered_at.is_(None))

    return [
        OutboxEventOut(
            id=row.id,
            name=row.name,
            subject_type=str(row.subject_type) if row.subject_type else None,
            subject_id=row.subject_id,
            payload=row.payload,
            created_at=row.created_at,
            delivered_at=row.delivered_at,
            attempts=row.attempts,
            last_error=row.last_error,
        )
        for row in session.scalars(statement)
    ]

