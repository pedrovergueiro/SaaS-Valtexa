"""Notificações (brief, seção 48): o aviso, a entrega por canal e a preferência.

Três tabelas, cada uma com uma pergunta:

* :class:`Notification` — **o que** foi avisado a **quem**. Uma linha por
  destinatário: é a central de notificações (lida/não lida) e, ao mesmo tempo, o
  canal "dentro do SaaS". ``dedup_key`` único por pessoa é o que impede o mesmo
  evento de notificar duas vezes (o *outbox* entrega ao menos uma vez).
* :class:`NotificationDelivery` — **como** o aviso saiu por um canal externo
  (e-mail hoje; WhatsApp, push e SMS depois). Guarda o estado honesto da entrega:
  ``enviado``, ``nao_enviado`` (sem SMTP configurado, ou canal ainda não
  implementado — nunca finge que mandou), ``falhou`` (vai tentar de novo) e
  ``desistiu``.
* :class:`NotificationPreference` — quem quer receber o quê, por qual canal e a
  partir de qual limite. Vale em três camadas: a da pessoa, a do papel dela no
  cliente (definida pelo gestor) e o padrão do código
  (:data:`valtexa.services.notifications.TIPOS`).

O ``tenant_id`` daqui é **anulável** (por isso sem :class:`TenantScoped`): o aviso
da equipe da ValTexa (``audience='plataforma'``) não pertence a cliente nenhum,
mesmo quando fala de um. O isolamento é por **destinatário** (``user_id``) e, no
console do cliente, também por cliente — ver ``api/routers/notifications.py``.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from valtexa.models.base import Base, Timestamped, UUIDPrimaryKey, utcnow

AUDIENCES = ("cliente", "plataforma")
SEVERITIES = ("info", "aviso", "critico")
DELIVERY_STATES = ("pendente", "enviado", "nao_enviado", "falhou", "desistiu")
"""``nao_enviado`` e ``desistiu`` são finais sem envio; ``enviado`` é final com envio."""


class Notification(UUIDPrimaryKey, Base):
    __tablename__ = "notification"
    __table_args__ = (
        UniqueConstraint("user_id", "dedup_key", name="uq_notification_user_dedup"),
        Index("ix_notification_inbox", "user_id", "audience", "tenant_id", "read_at"),
    )

    tenant_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("tenant.id", ondelete="CASCADE"), index=True,
        doc="O cliente de que o aviso fala. Nulo em aviso só da plataforma.",
    )
    user_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("user.id", ondelete="CASCADE"), nullable=False,
        doc="O destinatário.",
    )
    audience: Mapped[str] = mapped_column(
        String(16), nullable=False,
        doc="'cliente' (console do cliente) ou 'plataforma' (console interno).",
    )
    kind: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(16), nullable=False, default="info")
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    subject_type: Mapped[str | None] = mapped_column(String(32))
    subject_id: Mapped[str | None] = mapped_column(String(32))
    link: Mapped[str | None] = mapped_column(
        String(300), doc="Caminho no console ('/missoes/<id>'), para o clique no aviso."
    )
    event_id: Mapped[str | None] = mapped_column(
        String(32), index=True,
        doc="O evento do outbox que gerou o aviso. Sem chave estrangeira: o outbox é limpo.",
    )
    dedup_key: Mapped[str] = mapped_column(String(160), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False, index=True
    )
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class NotificationDelivery(UUIDPrimaryKey, Timestamped, Base):
    __tablename__ = "notification_delivery"
    __table_args__ = (
        UniqueConstraint("notification_id", "channel", name="uq_delivery_notification_channel"),
        Index("ix_delivery_due", "status", "next_attempt_at"),
    )

    notification_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("notification.id", ondelete="CASCADE"), nullable=False,
        index=True,
    )
    channel: Mapped[str] = mapped_column(String(16), nullable=False)
    destination: Mapped[str | None] = mapped_column(
        String(255), doc="E-mail (ou telefone, nos canais futuros) congelado na criação."
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pendente")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class NotificationPreference(UUIDPrimaryKey, Timestamped, Base):
    __tablename__ = "notification_preference"

    scope_key: Mapped[str] = mapped_column(
        String(140), nullable=False, unique=True,
        doc=(
            "'<tenant|->:<user|->:<papel|->:<tipo>'. Único no banco: as colunas soltas "
            "têm nulos, e nulo não conta como repetido numa restrição UNIQUE."
        ),
    )
    tenant_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("tenant.id", ondelete="CASCADE"), index=True,
        doc="Nulo nas preferências da equipe da ValTexa.",
    )
    user_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("user.id", ondelete="CASCADE"), index=True,
        doc="Nulo quando a preferência é do papel (vale para todos com ele).",
    )
    role: Mapped[str | None] = mapped_column(
        String(16), doc="Papel no cliente ou papel de plataforma, quando é do papel."
    )
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    channels: Mapped[list] = mapped_column(default=list, nullable=False)
    threshold: Mapped[float | None] = mapped_column(
        Float, doc="Limite do tipo, quando ele tem um (incidência em %)."
    )
    updated_by: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("user.id", ondelete="SET NULL")
    )


__all__ = [
    "AUDIENCES",
    "DELIVERY_STATES",
    "SEVERITIES",
    "Notification",
    "NotificationDelivery",
    "NotificationPreference",
]
