"""Consentimento do cliente para uso dos dados no treino (brief, seção 32).

Revisão: 0012
Anterior: 0011

Uma tabela de histórico: cada decisão é uma linha (SIM ou NÃO, quem, quando, de
onde veio). O vigente é o mais recente. **Nenhuma linha é criada aqui:** sem
decisão registrada, a resposta é NÃO — inclusive para quem já era cliente. O
treino nunca usa dado de cliente por padrão.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | Sequence[str] | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "data_consent",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("allowed", sa.Boolean(), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_by", sa.String(length=32), nullable=True),
        sa.Column("decided_by_label", sa.String(length=255), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("document_ref", sa.String(length=200), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["decided_by"], ["user.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_data_consent_tenant_id", "data_consent", ["tenant_id"])
    op.create_index("ix_data_consent_decided_at", "data_consent", ["decided_at"])
    op.create_index("ix_data_consent_created_at", "data_consent", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_data_consent_created_at", table_name="data_consent")
    op.drop_index("ix_data_consent_decided_at", table_name="data_consent")
    op.drop_index("ix_data_consent_tenant_id", table_name="data_consent")
    op.drop_table("data_consent")
