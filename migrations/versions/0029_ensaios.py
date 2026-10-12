"""Ensaios de validação do Rover: progresso do comando e resultado com veredito.

Revisão: 0029
Anterior: 0028

Uma coluna anulável em ``device_command`` (``progress``: o andamento de um ensaio em
execução) e uma tabela nova (``ensaio_resultado``: o veredito de cada ensaio, calculado
na plataforma). Nada existente muda de valor. A volta apaga a tabela e a coluna.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0029"
down_revision: str | Sequence[str] | None = "0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("device_command") as batch:
        batch.add_column(sa.Column("progress", sa.JSON(), nullable=True))
    op.create_table(
        "ensaio_resultado",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("device_id", sa.String(length=32), nullable=False),
        sa.Column("command_id", sa.String(length=32), nullable=True),
        sa.Column("ensaio", sa.String(length=32), nullable=False),
        sa.Column("fase", sa.Integer(), nullable=False),
        sa.Column("origem", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("aprovado", sa.Boolean(), nullable=True),
        sa.Column("params", sa.JSON(), nullable=False),
        sa.Column("criterios", sa.JSON(), nullable=False),
        sa.Column("medidas", sa.JSON(), nullable=False),
        sa.Column("laudo_robo", sa.JSON(), nullable=True),
        sa.Column("divergente", sa.Boolean(), nullable=False),
        sa.Column("simulado", sa.Boolean(), nullable=False),
        sa.Column("vale_portao", sa.Boolean(), nullable=False),
        sa.Column("observacao", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=32), nullable=True),
        sa.ForeignKeyConstraint(["device_id"], ["device.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["command_id"], ["device_command.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ensaio_resultado_device_ensaio", "ensaio_resultado",
                    ["device_id", "ensaio"])
    op.create_index("ix_ensaio_resultado_tenant_id", "ensaio_resultado", ["tenant_id"])
    op.create_index("ix_ensaio_resultado_created_at", "ensaio_resultado", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_ensaio_resultado_created_at", table_name="ensaio_resultado")
    op.drop_index("ix_ensaio_resultado_tenant_id", table_name="ensaio_resultado")
    op.drop_index("ix_ensaio_resultado_device_ensaio", table_name="ensaio_resultado")
    op.drop_table("ensaio_resultado")
    with op.batch_alter_table("device_command") as batch:
        batch.drop_column("progress")
