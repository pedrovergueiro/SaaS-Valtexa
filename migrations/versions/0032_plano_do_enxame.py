"""Plano do enxame por talhão: quem vai olhar onde (Nível 4).

Revisão: 0032
Anterior: 0031

Uma tabela nova (``plano_enxame``). Nada existente muda. A volta apaga a tabela.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0032"
down_revision: str | Sequence[str] | None = "0031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "plano_enxame",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("farm_id", sa.String(length=32), nullable=False),
        sa.Column("field_id", sa.String(length=32), nullable=False),
        sa.Column("versao", sa.Integer(), nullable=False),
        sa.Column("estado", sa.String(length=16), nullable=False),
        sa.Column("entradas_sha256", sa.String(length=64), nullable=False),
        sa.Column("entradas", sa.JSON(), nullable=False),
        sa.Column("plano", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.String(length=32), nullable=True),
        sa.ForeignKeyConstraint(["farm_id"], ["farm.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["field_id"], ["field.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_plano_enxame_field_estado", "plano_enxame", ["field_id", "estado"])
    op.create_index("ix_plano_enxame_tenant_id", "plano_enxame", ["tenant_id"])
    op.create_index("ix_plano_enxame_created_at", "plano_enxame", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_plano_enxame_created_at", table_name="plano_enxame")
    op.drop_index("ix_plano_enxame_tenant_id", table_name="plano_enxame")
    op.drop_index("ix_plano_enxame_field_estado", table_name="plano_enxame")
    op.drop_table("plano_enxame")
