"""Observabilidade (brief, seções 34 e 35): estatística da API e alertas.

* :class:`ApiRequestStat` — requisições por **minuto**, rota (o molde, não o
  caminho com id), método e classe de status, com a soma e o máximo da duração e
  os baldes do histograma. Cada réplica da API acumula em memória e **descarrega
  deltas** aqui a cada ``METRICS_FLUSH_SECONDS``: é o que deixa o worker (outro
  processo) avaliar "taxa de erro da API nos últimos 5 min" e o console mostrar
  latência por rota sem depender de qual réplica respondeu. As linhas são só de
  inserção (sem *upsert*): duas réplicas no mesmo minuto geram duas linhas, e a
  leitura soma.
* :class:`AlertRule` e :class:`Alert` — ver ``services/alertas.py``.
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

from valtexa.models.base import Base, Timestamped, UUIDPrimaryKey


class ApiRequestStat(UUIDPrimaryKey, Base):
    __tablename__ = "api_request_stat"
    __table_args__ = (Index("ix_api_request_stat_minute_route", "minute", "route"),)

    minute: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    instance: Mapped[str] = mapped_column(String(64), nullable=False)
    method: Mapped[str] = mapped_column(String(8), nullable=False)
    route: Mapped[str] = mapped_column(String(200), nullable=False)
    status_class: Mapped[str] = mapped_column(String(4), nullable=False, doc="2xx, 4xx, 5xx...")
    requests: Mapped[int] = mapped_column(Integer, nullable=False)
    errors: Mapped[int] = mapped_column(Integer, nullable=False, doc="Respostas 5xx.")
    duration_ms_sum: Mapped[float] = mapped_column(Float, nullable=False)
    duration_ms_max: Mapped[float] = mapped_column(Float, nullable=False)
    buckets: Mapped[list] = mapped_column(
        nullable=False, default=list,
        doc="Contagem por balde de latência (não cumulativa; o último é acima do maior "
            "limite). Limites em services/observabilidade.LIMITES_MS.",
    )


ALERT_STATES = ("disparado", "reconhecido", "resolvido")
ALERT_SEVERITIES = ("aviso", "critico")


class AlertRule(UUIDPrimaryKey, Timestamped, Base):
    """Uma regra de alerta. ``tenant_id`` nulo: a regra padrão, para todos.

    Um cliente pode ter a **sua** versão de uma regra de robô (limite próprio,
    ligada ou não): ela vale para os robôs dele no lugar da padrão. Regras da
    plataforma (API, IA, drift) não têm versão por cliente.
    """

    __tablename__ = "alert_rule"
    __table_args__ = (UniqueConstraint("scope_key", name="uq_alert_rule_scope"),)

    scope_key: Mapped[str] = mapped_column(String(80), nullable=False, doc="cliente:kind")
    tenant_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("tenant.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    threshold: Mapped[float | None] = mapped_column(Float)
    window_minutes: Mapped[int | None] = mapped_column(Integer)
    severity: Mapped[str] = mapped_column(String(16), nullable=False, default="aviso")
    updated_by: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("user.id", ondelete="SET NULL")
    )


class Alert(UUIDPrimaryKey, Timestamped, Base):
    """Uma ocorrência de alerta: disparou, alguém reconheceu, a condição passou.

    Há no máximo **um alerta aberto** por (regra, assunto): ``open_key`` é único e
    vira nulo quando o alerta resolve — a próxima violação abre outro alerta, e o
    histórico das anteriores fica.
    """

    __tablename__ = "alert"
    __table_args__ = (
        UniqueConstraint("open_key", name="uq_alert_open_key"),
        Index("ix_alert_tenant_state", "tenant_id", "state"),
    )

    kind: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    rule_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("alert_rule.id", ondelete="SET NULL")
    )
    tenant_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("tenant.id", ondelete="CASCADE"), index=True,
        doc="O cliente dono do assunto (robô). Nulo: alerta só da plataforma.",
    )
    subject_type: Mapped[str] = mapped_column(String(32), nullable=False)
    subject_id: Mapped[str] = mapped_column(String(64), nullable=False)
    subject_label: Mapped[str] = mapped_column(String(200), nullable=False)
    open_key: Mapped[str | None] = mapped_column(String(160))
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="disparado",
                                       index=True)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    value: Mapped[float | None] = mapped_column(Float)
    threshold: Mapped[float | None] = mapped_column(Float)
    fired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False,
                                               index=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    acknowledged_by: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("user.id", ondelete="SET NULL")
    )
    acknowledged_label: Mapped[str | None] = mapped_column(String(200))
    ack_note: Mapped[str | None] = mapped_column(Text)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


__all__ = ["ALERT_SEVERITIES", "ALERT_STATES", "Alert", "AlertRule", "ApiRequestStat"]
