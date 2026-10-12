"""Mapa de cobertura do rádio da fazenda, por talhão.

Revisão: 0031
Anterior: 0030

Duas colunas anuláveis em ``field``: ``cobertura`` (a grade do levantamento que a base da
fazenda manda, com zonas mortas e repetidoras sugeridas) e ``cobertura_em``. O mapa vai
assinado na missão para o Rover. Nada existente muda de valor. A volta apaga as colunas.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0031"
down_revision: str | Sequence[str] | None = "0030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("field") as batch:
        batch.add_column(sa.Column("cobertura", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("cobertura_em", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("field") as batch:
        batch.drop_column("cobertura_em")
        batch.drop_column("cobertura")
