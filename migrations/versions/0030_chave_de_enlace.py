"""Chave do rádio da fazenda de cada robô, cadastrada pela plataforma.

Revisão: 0030
Anterior: 0029

Duas colunas anuláveis em ``device``: ``enlace_chave`` (o documento que o robô publica:
a pública X25519 do enlace assinada pela identidade Ed25519 dele) e ``enlace_chave_em``.
A base da fazenda busca as chaves dos robôs da fazenda dela em vez de alguém copiar
arquivo à mão. Nada existente muda de valor. A volta apaga as duas colunas.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0030"
down_revision: str | Sequence[str] | None = "0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("device") as batch:
        batch.add_column(sa.Column("enlace_chave", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("enlace_chave_em", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("device") as batch:
        batch.drop_column("enlace_chave_em")
        batch.drop_column("enlace_chave")
