"""Suporte (brief, seção 49): chamados, comentários, histórico e incidentes.

* :class:`SupportTicket` — o chamado de **um** cliente: status, prioridade,
  vínculo opcional com robô e missão, responsável na equipe e, quando faz parte
  de um problema maior, o incidente. O cliente abre e acompanha os dele; a equipe
  vê todos no console da plataforma.
* :class:`TicketComment` — a conversa. ``internal`` marca a nota da equipe que o
  cliente **não** vê (a rota do cliente filtra; o teste de isolamento confere).
* :class:`TicketEvent` — o histórico: cada mudança de status, prioridade,
  responsável, incidente ou sessão de suporte, com quem e quando. Não se edita.
* :class:`Incident` — agrupa chamados de vários clientes que têm a mesma causa
  ("sincronização parada desde 14h"). É da plataforma (sem ``tenant_id``); o
  cliente o vê só pelo chamado dele, com a nota pública.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from valtexa.models.base import Base, TenantScoped, Timestamped, UUIDPrimaryKey, utcnow

TICKET_STATUSES = ("aberto", "em_atendimento", "aguardando_cliente", "resolvido", "fechado")
"""``resolvido`` é a equipe dizendo "achamos que está resolvido"; ``fechado`` é final
(o cliente confirma, ou o prazo passa). Os dois podem ser reabertos."""
TICKET_OPEN_STATUSES = ("aberto", "em_atendimento", "aguardando_cliente")
TICKET_PRIORITIES = ("baixa", "normal", "alta", "urgente")
INCIDENT_STATUSES = ("aberto", "investigando", "mitigado", "resolvido")
INCIDENT_SEVERITIES = ("baixa", "media", "alta", "critica")


def ticket_code(number: int) -> str:
    return f"CH-{number:05d}"


class Incident(UUIDPrimaryKey, Timestamped, Base):
    __tablename__ = "incident"

    number: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="aberto", index=True)
    severity: Mapped[str] = mapped_column(String(16), nullable=False, default="media")
    public_note: Mapped[str | None] = mapped_column(
        Text, doc="O que os clientes afetados leem no chamado deles."
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("user.id", ondelete="SET NULL")
    )

    @property
    def code(self) -> str:
        return f"INC-{self.number:04d}"


class SupportTicket(UUIDPrimaryKey, TenantScoped, Timestamped, Base):
    __tablename__ = "support_ticket"
    __table_args__ = (Index("ix_support_ticket_tenant_status", "tenant_id", "status"),)

    number: Mapped[int] = mapped_column(
        Integer, nullable=False, unique=True, doc="Sequencial da plataforma: CH-00001."
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="aberto", index=True)
    priority: Mapped[str] = mapped_column(String(16), nullable=False, default="normal",
                                          index=True)
    category: Mapped[str | None] = mapped_column(String(40))
    device_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("device.id", ondelete="SET NULL"), index=True
    )
    mission_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("mission.id", ondelete="SET NULL"), index=True
    )
    incident_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("incident.id", ondelete="SET NULL"), index=True
    )
    opened_by: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("user.id", ondelete="SET NULL")
    )
    opened_by_label: Mapped[str] = mapped_column(String(200), nullable=False)
    opened_via: Mapped[str] = mapped_column(
        String(16), nullable=False, doc="'cliente' (console do cliente) ou 'plataforma'."
    )
    assignee_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("user.id", ondelete="SET NULL"), index=True
    )
    first_response_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_activity_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    @property
    def code(self) -> str:
        return ticket_code(self.number)


class TicketComment(UUIDPrimaryKey, TenantScoped, Base):
    __tablename__ = "ticket_comment"

    ticket_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("support_ticket.id", ondelete="CASCADE"), nullable=False,
        index=True,
    )
    author_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("user.id", ondelete="SET NULL")
    )
    author_label: Mapped[str] = mapped_column(String(200), nullable=False)
    side: Mapped[str] = mapped_column(String(16), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    internal: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class TicketEvent(UUIDPrimaryKey, TenantScoped, Base):
    __tablename__ = "ticket_event"

    ticket_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("support_ticket.id", ondelete="CASCADE"), nullable=False,
        index=True,
    )
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(32))
    actor_label: Mapped[str] = mapped_column(String(200), nullable=False)
    side: Mapped[str] = mapped_column(String(16), nullable=False)
    kind: Mapped[str] = mapped_column(
        String(32), nullable=False,
        doc="aberto, status, prioridade, responsavel, incidente, comentario, sessao_suporte.",
    )
    old_value: Mapped[str | None] = mapped_column(String(200))
    new_value: Mapped[str | None] = mapped_column(String(200))
    note: Mapped[str | None] = mapped_column(Text)
    internal: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


__all__ = [
    "INCIDENT_SEVERITIES",
    "INCIDENT_STATUSES",
    "TICKET_OPEN_STATUSES",
    "TICKET_PRIORITIES",
    "TICKET_STATUSES",
    "Incident",
    "SupportTicket",
    "TicketComment",
    "TicketEvent",
    "ticket_code",
]
