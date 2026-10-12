"""Planos, assinaturas, uso e consentimento de dados.

Brief, seção 31: acabar com "serviço contratado = texto livre". O plano é o que
limita o cliente — hectares, talhões, rovers, usuários, missões por mês,
armazenamento, retenção — e liga recursos. A assinatura liga um cliente a um
plano, com estado e com sobreposições por cliente (o contrato que fugiu da
tabela). O uso mensal fica em :class:`UsageCounter`.

Brief, seção 32: dado de cliente só entra no treino com consentimento explícito,
SIM ou NÃO, registrado com quem e quando. :class:`DataConsent` é o histórico; o
vigente é o mais recente. Sem linha nenhuma, a resposta é NÃO.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from valtexa.models.base import Base, TenantScoped, Timestamped, UUIDPrimaryKey, enum_column
from valtexa.models.enums import SubscriptionStatus


class Plan(UUIDPrimaryKey, Timestamped, Base):
    """Um plano do catálogo comercial.

    Limite nulo é **sem limite**. Os limites são colunas, e não um JSON, para que
    o banco recuse valor de tipo errado e para que dê para responder "quem está
    no plano X com mais de N hectares" sem ler linha por linha.
    """

    __tablename__ = "plan"

    code: Mapped[str] = mapped_column(String(40), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, doc="Inativo: não aceita assinatura nova."
    )

    max_hectares: Mapped[float | None] = mapped_column(Float)
    max_farms: Mapped[int | None] = mapped_column(Integer)
    max_fields: Mapped[int | None] = mapped_column(Integer)
    max_devices: Mapped[int | None] = mapped_column(Integer, doc="Rovers e demais robôs.")
    max_users: Mapped[int | None] = mapped_column(Integer)
    max_missions_per_month: Mapped[int | None] = mapped_column(Integer)
    max_storage_gb: Mapped[float | None] = mapped_column(Float)
    retention_days: Mapped[int | None] = mapped_column(
        Integer, doc="Retenção de imagem normal, em dias. Aplicada pelo worker (fase 10)."
    )
    features: Mapped[list] = mapped_column(
        default=list,
        doc="Recursos ligados: 'prescricao', 'lavoura_3d', 'validacao_campo', 'relatorios'...",
    )
    price_cents: Mapped[int | None] = mapped_column(
        Integer, doc="Preço de referência mensal. Cobrança é manual nesta rodada."
    )


class Subscription(UUIDPrimaryKey, TenantScoped, Timestamped, Base):
    """A assinatura vigente de um cliente. Uma por cliente; a troca fica na auditoria."""

    __tablename__ = "subscription"
    __table_args__ = (UniqueConstraint("tenant_id", name="uq_subscription_tenant"),)

    plan_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("plan.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    status: Mapped[SubscriptionStatus] = mapped_column(
        enum_column(SubscriptionStatus), nullable=False, default=SubscriptionStatus.ATIVA
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), doc="Fim do contrato ou do teste. Nulo: sem data."
    )
    overrides: Mapped[dict] = mapped_column(
        default=dict,
        doc=(
            "Limites negociados só para este cliente, com o mesmo nome das colunas "
            "do plano: {'max_fields': 12}. ``null`` num valor tira o limite."
        ),
    )
    notes: Mapped[str | None] = mapped_column(
        Text,
        doc=(
            "Observação comercial. A migração 0011 guarda aqui o antigo "
            "``tenant.contracted_service``, para nada do que foi escrito se perder."
        ),
    )
    billing_customer_id: Mapped[str | None] = mapped_column(
        String(120), doc="Reservado para o gateway de cobrança (fora desta rodada)."
    )

    plan: Mapped[Plan] = relationship()


class UsageCounter(UUIDPrimaryKey, TenantScoped, Timestamped, Base):
    """Uso acumulado no mês, por métrica: ``missions``, ``frames_analyzed``...

    Só o que é *fluxo* vive aqui. O que é *estoque* (talhões, rovers, usuários,
    hectares) se conta direto nas tabelas, que é a fonte da verdade — um contador
    paralelo envelheceria a cada exclusão.
    """

    __tablename__ = "usage_counter"
    __table_args__ = (
        UniqueConstraint("tenant_id", "period", "metric", name="uq_usage_tenant_period_metric"),
    )

    period: Mapped[str] = mapped_column(String(7), nullable=False, doc="Mês, 'AAAA-MM', UTC.")
    metric: Mapped[str] = mapped_column(String(40), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False, default=0)


class DataConsent(UUIDPrimaryKey, TenantScoped, Timestamped, Base):
    """Uma decisão do cliente sobre o uso dos dados dele no treino dos modelos.

    Nunca é editada: mudar de ideia é uma linha nova. O histórico inteiro é o
    que responde, numa auditoria ou num pedido da LGPD, "em que data este
    cliente autorizou, e quem autorizou".
    """

    __tablename__ = "data_consent"

    allowed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    decided_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    decided_by: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("user.id", ondelete="SET NULL")
    )
    decided_by_label: Mapped[str] = mapped_column(
        String(255), nullable=False, doc="E-mail de quem registrou, congelado."
    )
    source: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        doc="'cliente' (no console) ou 'contrato' (registrado pela ValTexa com documento).",
    )
    document_ref: Mapped[str | None] = mapped_column(
        String(200), doc="Contrato ou termo que embasa o registro feito pela ValTexa."
    )
    notes: Mapped[str | None] = mapped_column(Text)
