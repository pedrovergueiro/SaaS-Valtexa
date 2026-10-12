"""Fazenda completa: produtor, CPF/CNPJ, município, UF, cultura, CAR, responsável técnico.

Revisão: 0015
Anterior: 0014

Brief, seção 5 ("Fazendas: nome, localização, coordenadas, área,
proprietário/cliente, cultura, histórico"). Tudo opcional e sem preenchimento:
uma fazenda antiga continua válida e aparece no console com "cadastro
incompleto" até alguém completar.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: str | Sequence[str] | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

COLUNAS = (
    ("owner_name", sa.String(160)),
    ("owner_document", sa.String(14)),
    ("city", sa.String(120)),
    ("state", sa.String(2)),
    ("main_crop", sa.String(64)),
    ("car_code", sa.String(64)),
    ("technical_lead", sa.String(160)),
    ("notes", sa.Text()),
)


def upgrade() -> None:
    with op.batch_alter_table("farm") as batch_op:
        for nome, tipo in COLUNAS:
            batch_op.add_column(sa.Column(nome, tipo, nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("farm") as batch_op:
        for nome, _ in reversed(COLUNAS):
            batch_op.drop_column(nome)
