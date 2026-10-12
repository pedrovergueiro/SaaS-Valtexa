"""Planos, assinaturas e uso (brief, seção 31).

Revisão: 0011
Anterior: 0010

Acaba com "serviço contratado = texto livre" sem perder o que foi escrito:

* cria ``plan``, ``subscription`` e ``usage_counter``;
* cria o plano ``piloto`` (sem limites) e assina **todo cliente existente** nele,
  copiando ``tenant.contracted_service`` para ``subscription.notes``. Quem já
  operava continua operando exatamente como antes; nenhum limite novo cai sobre
  um cliente sem alguém decidir;
* ``tenant.contracted_service`` **fica** (o console ainda o edita). Sai numa fase
  posterior, quando nada mais o ler.

Os demais planos do catálogo (essencial, profissional, empresarial) nascem no
start da aplicação (:func:`valtexa.services.plans.sincronizar_catalogo`), não
aqui: são dado comercial, editável, e não esquema.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | Sequence[str] | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "plan",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("max_hectares", sa.Float(), nullable=True),
        sa.Column("max_farms", sa.Integer(), nullable=True),
        sa.Column("max_fields", sa.Integer(), nullable=True),
        sa.Column("max_devices", sa.Integer(), nullable=True),
        sa.Column("max_users", sa.Integer(), nullable=True),
        sa.Column("max_missions_per_month", sa.Integer(), nullable=True),
        sa.Column("max_storage_gb", sa.Float(), nullable=True),
        sa.Column("retention_days", sa.Integer(), nullable=True),
        sa.Column("features", sa.JSON(), nullable=False),
        sa.Column("price_cents", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_plan_code", "plan", ["code"], unique=True)
    op.create_index("ix_plan_created_at", "plan", ["created_at"])

    op.create_table(
        "subscription",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("plan_id", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("overrides", sa.JSON(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("billing_customer_id", sa.String(length=120), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["plan_id"], ["plan.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", name="uq_subscription_tenant"),
    )
    op.create_index("ix_subscription_tenant_id", "subscription", ["tenant_id"])
    op.create_index("ix_subscription_plan_id", "subscription", ["plan_id"])
    op.create_index("ix_subscription_created_at", "subscription", ["created_at"])

    op.create_table(
        "usage_counter",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("period", sa.String(length=7), nullable=False),
        sa.Column("metric", sa.String(length=40), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "period", "metric", name="uq_usage_tenant_period_metric"
        ),
    )
    op.create_index("ix_usage_counter_tenant_id", "usage_counter", ["tenant_id"])
    op.create_index("ix_usage_counter_created_at", "usage_counter", ["created_at"])

    # --- dados: o plano piloto e a assinatura de quem já existe ---------------
    agora = datetime.now(UTC)
    plano_id = uuid.uuid4().hex
    plano = sa.table(
        "plan",
        sa.column("id", sa.String),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
        sa.column("code", sa.String),
        sa.column("name", sa.String),
        sa.column("description", sa.Text),
        sa.column("is_active", sa.Boolean),
        sa.column("features", sa.JSON),
    )
    op.bulk_insert(
        plano,
        [
            {
                "id": plano_id,
                "created_at": agora,
                "updated_at": agora,
                "code": "piloto",
                "name": "Piloto",
                "description": (
                    "Clientes do piloto e anteriores aos planos. Sem limites: é o que "
                    "mantém funcionando quem já operava antes da migração 0011."
                ),
                "is_active": True,
                "features": ["prescricao", "lavoura_3d", "validacao_campo", "relatorios"],
            }
        ],
    )

    conexao = op.get_bind()
    clientes = conexao.execute(
        sa.text("SELECT id, created_at, contracted_service FROM tenant")
    ).all()
    assinatura = sa.table(
        "subscription",
        sa.column("id", sa.String),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
        sa.column("tenant_id", sa.String),
        sa.column("plan_id", sa.String),
        sa.column("status", sa.String),
        sa.column("started_at", sa.DateTime(timezone=True)),
        sa.column("overrides", sa.JSON),
        sa.column("notes", sa.Text),
    )
    if clientes:
        op.bulk_insert(
            assinatura,
            [
                {
                    "id": uuid.uuid4().hex,
                    "created_at": agora,
                    "updated_at": agora,
                    "tenant_id": tenant_id,
                    "plan_id": plano_id,
                    "status": "ativa",
                    "started_at": _instante(criado) or agora,
                    "overrides": {},
                    "notes": (
                        f"Serviço contratado (texto anterior aos planos): {servico}"
                        if servico
                        else None
                    ),
                }
                for tenant_id, criado, servico in clientes
            ],
        )


def _instante(valor: object) -> datetime | None:
    """O SQLite devolve o horário como texto numa consulta crua; o Postgres, como datetime."""
    if valor is None or isinstance(valor, datetime):
        return valor
    try:
        return datetime.fromisoformat(str(valor))
    except ValueError:
        return None


def downgrade() -> None:
    op.drop_index("ix_usage_counter_created_at", table_name="usage_counter")
    op.drop_index("ix_usage_counter_tenant_id", table_name="usage_counter")
    op.drop_table("usage_counter")
    op.drop_index("ix_subscription_created_at", table_name="subscription")
    op.drop_index("ix_subscription_plan_id", table_name="subscription")
    op.drop_index("ix_subscription_tenant_id", table_name="subscription")
    op.drop_table("subscription")
    op.drop_index("ix_plan_created_at", table_name="plan")
    op.drop_index("ix_plan_code", table_name="plan")
    op.drop_table("plan")
