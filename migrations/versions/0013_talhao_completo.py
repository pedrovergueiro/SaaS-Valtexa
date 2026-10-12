"""Talhão completo: espaçamento entre plantas, linhas, fileiras de validação, observações.

Revisão: 0013
Anterior: 0012

Brief, seção 5. Tudo opcional e sem preenchimento: um talhão antigo continua
válido, e a IA continua usando o espaçamento padrão dela enquanto o talhão não
disser o seu.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: str | Sequence[str] | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("field") as batch_op:
        batch_op.add_column(sa.Column("plant_spacing_m", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("row_count", sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "validation_rows", sa.JSON(), nullable=False, server_default=sa.text("'[]'")
            )
        )
        batch_op.add_column(sa.Column("notes", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("field") as batch_op:
        batch_op.drop_column("notes")
        batch_op.drop_column("validation_rows")
        batch_op.drop_column("row_count")
        batch_op.drop_column("plant_spacing_m")
