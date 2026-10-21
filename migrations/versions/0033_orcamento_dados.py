"""Orçamento de dados por robô (Starlink própria, rodada 4).

Revisão: 0033
Anterior: 0032

Uma coluna nova, anulável (``device.orcamento_dados``): nada existente muda e o robô sem
teto da plataforma usa o do ``rover.json``. A volta apaga a coluna.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0033"
down_revision: str | Sequence[str] | None = "0032"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("device") as batch:
        batch.add_column(sa.Column("orcamento_dados", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("device") as batch:
        batch.drop_column("orcamento_dados")
