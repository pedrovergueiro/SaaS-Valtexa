"""Etapa de otimização (dNATY) do Model Registry: benchmark original e otimizado.

Revisão: 0019
Anterior: 0018

Uma tabela nova, ``model_optimization``: cada rodada de otimização de uma versão
de modelo, aceita ou recusada, com os dois benchmarks, o critério e o veredito.
Nada existente muda; a volta apaga a tabela.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019"
down_revision: str | Sequence[str] | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "model_optimization",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("model_version_id", sa.String(length=32), nullable=False),
        sa.Column("tool", sa.String(length=64), nullable=False),
        sa.Column("tool_version", sa.String(length=32), nullable=True),
        sa.Column("dnaty_version", sa.String(length=32), nullable=True),
        sa.Column("parameters", sa.JSON(), nullable=False),
        sa.Column("original_sha256", sa.String(length=64), nullable=False),
        sa.Column("original_benchmark", sa.JSON(), nullable=False),
        sa.Column("optimized_artifact_uri", sa.String(length=512), nullable=False),
        sa.Column("optimized_sha256", sa.String(length=64), nullable=False),
        sa.Column("optimized_size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("optimized_benchmark", sa.JSON(), nullable=False),
        sa.Column("criterion", sa.JSON(), nullable=False),
        sa.Column("comparison", sa.JSON(), nullable=False),
        sa.Column("accepted", sa.Boolean(), nullable=False),
        sa.Column("reasons", sa.JSON(), nullable=False),
        sa.Column("license_note", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=32), nullable=True),
        sa.ForeignKeyConstraint(["model_version_id"], ["model_version.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["user.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_model_optimization_model_version_id", "model_optimization",
                    ["model_version_id"])
    op.create_index("ix_model_optimization_created_at", "model_optimization", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_model_optimization_created_at", table_name="model_optimization")
    op.drop_index("ix_model_optimization_model_version_id", table_name="model_optimization")
    op.drop_table("model_optimization")
