"""Suporte (seção 49): chamados, comentários, histórico e incidentes.

Revisão: 0023
Anterior: 0022

Quatro tabelas novas (``incident``, ``support_ticket``, ``ticket_comment``,
``ticket_event``) e uma coluna anulável nova em ``support_session``
(``ticket_id``: a sessão "entrar como cliente" pode apontar o chamado que a
motivou). Nada existente muda de valor; a volta apaga a coluna e as tabelas.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0023"
down_revision: str | Sequence[str] | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _datas() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "incident",
        sa.Column("id", sa.String(length=32), nullable=False),
        *_datas(),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("public_note", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(length=32), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], ["user.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("number"),
    )
    op.create_index("ix_incident_created_at", "incident", ["created_at"])
    op.create_index("ix_incident_status", "incident", ["status"])

    op.create_table(
        "support_ticket",
        sa.Column("id", sa.String(length=32), nullable=False),
        *_datas(),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("priority", sa.String(length=16), nullable=False),
        sa.Column("category", sa.String(length=40), nullable=True),
        sa.Column("device_id", sa.String(length=32), nullable=True),
        sa.Column("mission_id", sa.String(length=32), nullable=True),
        sa.Column("incident_id", sa.String(length=32), nullable=True),
        sa.Column("opened_by", sa.String(length=32), nullable=True),
        sa.Column("opened_by_label", sa.String(length=200), nullable=False),
        sa.Column("opened_via", sa.String(length=16), nullable=False),
        sa.Column("assignee_id", sa.String(length=32), nullable=True),
        sa.Column("first_response_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["device_id"], ["device.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["mission_id"], ["mission.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["incident_id"], ["incident.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["opened_by"], ["user.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["assignee_id"], ["user.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("number"),
    )
    for coluna in ("tenant_id", "created_at", "status", "priority", "device_id", "mission_id",
                   "incident_id", "assignee_id"):
        op.create_index(f"ix_support_ticket_{coluna}", "support_ticket", [coluna])
    op.create_index("ix_support_ticket_tenant_status", "support_ticket", ["tenant_id", "status"])

    op.create_table(
        "ticket_comment",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("ticket_id", sa.String(length=32), nullable=False),
        sa.Column("author_id", sa.String(length=32), nullable=True),
        sa.Column("author_label", sa.String(length=200), nullable=False),
        sa.Column("side", sa.String(length=16), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("internal", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ticket_id"], ["support_ticket.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["author_id"], ["user.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ticket_comment_tenant_id", "ticket_comment", ["tenant_id"])
    op.create_index("ix_ticket_comment_ticket_id", "ticket_comment", ["ticket_id"])

    op.create_table(
        "ticket_event",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("ticket_id", sa.String(length=32), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor_id", sa.String(length=32), nullable=True),
        sa.Column("actor_label", sa.String(length=200), nullable=False),
        sa.Column("side", sa.String(length=16), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("old_value", sa.String(length=200), nullable=True),
        sa.Column("new_value", sa.String(length=200), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("internal", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ticket_id"], ["support_ticket.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ticket_event_tenant_id", "ticket_event", ["tenant_id"])
    op.create_index("ix_ticket_event_ticket_id", "ticket_event", ["ticket_id"])

    with op.batch_alter_table("support_session") as batch:
        batch.add_column(sa.Column("ticket_id", sa.String(length=32), nullable=True))
        batch.create_foreign_key("fk_support_session_ticket", "support_ticket",
                                 ["ticket_id"], ["id"], ondelete="SET NULL")
        batch.create_index("ix_support_session_ticket_id", ["ticket_id"])


def downgrade() -> None:
    with op.batch_alter_table("support_session") as batch:
        batch.drop_index("ix_support_session_ticket_id")
        batch.drop_constraint("fk_support_session_ticket", type_="foreignkey")
        batch.drop_column("ticket_id")
    for tabela in ("ticket_event", "ticket_comment"):
        op.drop_index(f"ix_{tabela}_ticket_id", table_name=tabela)
        op.drop_index(f"ix_{tabela}_tenant_id", table_name=tabela)
        op.drop_table(tabela)
    op.drop_index("ix_support_ticket_tenant_status", table_name="support_ticket")
    for coluna in ("assignee_id", "incident_id", "mission_id", "device_id", "priority",
                   "status", "created_at", "tenant_id"):
        op.drop_index(f"ix_support_ticket_{coluna}", table_name="support_ticket")
    op.drop_table("support_ticket")
    op.drop_index("ix_incident_status", table_name="incident")
    op.drop_index("ix_incident_created_at", table_name="incident")
    op.drop_table("incident")
