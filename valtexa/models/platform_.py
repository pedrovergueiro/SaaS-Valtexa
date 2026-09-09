"""Infraestrutura transversal: auditoria, barramento de eventos e antirreplay.

O nome tem sublinhado porque ``platform`` é módulo da biblioteca padrão.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from valtexa.models.base import Base, Timestamped, UUIDPrimaryKey, enum_column, utcnow
from valtexa.models.enums import ActorType, SubjectType


class AuditEntry(UUIDPrimaryKey, Base):
    """Registro imutável de uma ação relevante.

    Sem ``updated_at`` de propósito: auditoria que pode ser alterada não é
    auditoria. A regra de escrita é uma só — toda transição de estado de
    dispositivo, missão, diagnóstico, decisão ou aplicação passa por
    :func:`valtexa.services.audit.record`.
    """

    __tablename__ = "audit_entry"
    __table_args__ = (
        Index("ix_audit_subject", "subject_type", "subject_id"),
        Index("ix_audit_tenant_time", "tenant_id", "at"),
    )

    tenant_id: Mapped[str | None] = mapped_column(
        String(32), index=True, doc="Nulo em ações da plataforma que não pertencem a um cliente."
    )
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False, index=True
    )
    actor_type: Mapped[ActorType] = mapped_column(enum_column(ActorType), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(64))
    actor_label: Mapped[str | None] = mapped_column(
        String(160), doc="E-mail ou número de série, congelado no momento da ação."
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    subject_type: Mapped[SubjectType] = mapped_column(enum_column(SubjectType), nullable=False)
    subject_id: Mapped[str] = mapped_column(String(32), nullable=False)
    old_state: Mapped[str | None] = mapped_column(String(64))
    new_state: Mapped[str | None] = mapped_column(String(64))
    reason: Mapped[str | None] = mapped_column(Text)
    model_version: Mapped[str | None] = mapped_column(String(64))
    rule_version: Mapped[str | None] = mapped_column(String(32))
    ip: Mapped[str | None] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(default=dict)


class OutboxEvent(UUIDPrimaryKey, Base):
    """Evento de domínio persistido antes de ser entregue.

    É o padrão *transactional outbox*: o evento é gravado na **mesma transação**
    que mudou o estado. Ou os dois acontecem, ou nenhum. Sem isso, um processo
    que morre entre "missão autorizada" e "avisar quem interessa" deixaria o
    sistema num estado que ninguém observou.

    A entrega é ao-menos-uma-vez, então todo handler precisa ser idempotente.
    """

    __tablename__ = "outbox_event"
    __table_args__ = (Index("ix_outbox_pending", "delivered_at", "created_at"),)

    tenant_id: Mapped[str | None] = mapped_column(String(32), index=True)
    name: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True, doc="Ex.: 'mission.authorized'. Ver docs/EVENTS.md."
    )
    subject_type: Mapped[SubjectType | None] = mapped_column(enum_column(SubjectType))
    subject_id: Mapped[str | None] = mapped_column(String(32), index=True)
    payload: Mapped[dict] = mapped_column(default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False, index=True
    )
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text)


class UsedNonce(Timestamped, Base):
    """Nonce já consumido, para recusar a repetição de uma requisição assinada.

    A chave primária é o próprio nonce por dispositivo: a segunda tentativa de
    gravar viola a restrição e é rejeitada pelo banco, não por uma checagem em
    Python que duas requisições simultâneas poderiam driblar.
    """

    __tablename__ = "used_nonce"
    __table_args__ = (UniqueConstraint("device_id", "nonce", name="uq_nonce_device"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("device.id", ondelete="CASCADE"), nullable=False, index=True
    )
    nonce: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
        doc=(
            "Depois disto a linha pode ser apagada: a janela de tolerância de "
            "relógio já recusaria a requisição por idade."
        ),
    )
