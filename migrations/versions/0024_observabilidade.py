"""Observabilidade (seções 34 e 35): estatística da API, saúde do robô e alertas.

Revisão: 0024
Anterior: 0023

Três tabelas novas (``api_request_stat``, ``alert_rule``, ``alert``) e duas colunas
anuláveis em ``device`` (``health``, ``health_reported_at``). Nada existente muda de
valor. As regras padrão de alerta **não** são criadas aqui: o catálogo é
sincronizado na subida da API (como o de planos), para que mudar um padrão no
código não exija migração. A volta apaga as tabelas e as colunas.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0024"
down_revision: str | Sequence[str] | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "api_request_stat",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("minute", sa.DateTime(timezone=True), nullable=False),
        sa.Column("instance", sa.String(length=64), nullable=False),
        sa.Column("method", sa.String(length=8), nullable=False),
        sa.Column("route", sa.String(length=200), nullable=False),
        sa.Column("status_class", sa.String(length=4), nullable=False),
        sa.Column("requests", sa.Integer(), nullable=False),
        sa.Column("errors", sa.Integer(), nullable=False),
        sa.Column("duration_ms_sum", sa.Float(), nullable=False),
        sa.Column("duration_ms_max", sa.Float(), nullable=False),
        sa.Column("buckets", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_api_request_stat_minute_route", "api_request_stat", ["minute", "route"])

    op.create_table(
        "alert_rule",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("scope_key", sa.String(length=80), nullable=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=True),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("threshold", sa.Float(), nullable=True),
        sa.Column("window_minutes", sa.Integer(), nullable=True),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("updated_by", sa.String(length=32), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["updated_by"], ["user.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("scope_key", name="uq_alert_rule_scope"),
    )
    op.create_index("ix_alert_rule_tenant_id", "alert_rule", ["tenant_id"])
    op.create_index("ix_alert_rule_kind", "alert_rule", ["kind"])

    op.create_table(
        "alert",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("rule_id", sa.String(length=32), nullable=True),
        sa.Column("tenant_id", sa.String(length=32), nullable=True),
        sa.Column("subject_type", sa.String(length=32), nullable=False),
        sa.Column("subject_id", sa.String(length=64), nullable=False),
        sa.Column("subject_label", sa.String(length=200), nullable=False),
        sa.Column("open_key", sa.String(length=160), nullable=True),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("value", sa.Float(), nullable=True),
        sa.Column("threshold", sa.Float(), nullable=True),
        sa.Column("fired_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acknowledged_by", sa.String(length=32), nullable=True),
        sa.Column("acknowledged_label", sa.String(length=200), nullable=True),
        sa.Column("ack_note", sa.Text(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["rule_id"], ["alert_rule.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["acknowledged_by"], ["user.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("open_key", name="uq_alert_open_key"),
    )
    op.create_index("ix_alert_kind", "alert", ["kind"])
    op.create_index("ix_alert_tenant_id", "alert", ["tenant_id"])
    op.create_index("ix_alert_state", "alert", ["state"])
    op.create_index("ix_alert_fired_at", "alert", ["fired_at"])
    op.create_index("ix_alert_tenant_state", "alert", ["tenant_id", "state"])

    with op.batch_alter_table("device") as batch:
        batch.add_column(sa.Column("health", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("health_reported_at", sa.DateTime(timezone=True),
                                   nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("device") as batch:
        batch.drop_column("health_reported_at")
        batch.drop_column("health")
    op.drop_index("ix_alert_tenant_state", table_name="alert")
    op.drop_index("ix_alert_fired_at", table_name="alert")
    op.drop_index("ix_alert_state", table_name="alert")
    op.drop_index("ix_alert_tenant_id", table_name="alert")
    op.drop_index("ix_alert_kind", table_name="alert")
    op.drop_table("alert")
    op.drop_index("ix_alert_rule_kind", table_name="alert_rule")
    op.drop_index("ix_alert_rule_tenant_id", table_name="alert_rule")
    op.drop_table("alert_rule")
    op.drop_index("ix_api_request_stat_minute_route", table_name="api_request_stat")
    op.drop_table("api_request_stat")
