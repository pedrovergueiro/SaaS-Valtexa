"""Dados de cadastro do cliente: contato, endereço e serviço contratado.

Revisão: 0005
Anterior: 0004

Nove colunas em ``tenant``. Todas anuláveis, e isso é a decisão de projeto, não
preguiça: o cadastro de um cliente começa numa ligação, com o nome e o telefone,
e se completa depois. Uma coluna obrigatória aqui obrigaria quem atende a
inventar um endereço para conseguir salvar — e endereço inventado é pior que
campo vazio, porque parece preenchido e ninguém volta para conferir.

Nada é reescrito e nada muda de tipo, então a migração é reversível sem perda:
o ``downgrade`` só descarta colunas que não existiam antes.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | Sequence[str] | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

COLUNAS = (
    ("contact_name", sa.String(length=160)),
    ("email", sa.String(length=255)),
    ("phone", sa.String(length=40)),
    ("address", sa.String(length=255)),
    ("city", sa.String(length=120)),
    ("state", sa.String(length=2)),
    ("postal_code", sa.String(length=16)),
    ("contracted_service", sa.String(length=120)),
    ("notes", sa.String(length=1000)),
)


def upgrade() -> None:
    for nome, tipo in COLUNAS:
        op.add_column("tenant", sa.Column(nome, tipo, nullable=True))


def downgrade() -> None:
    for nome, _ in reversed(COLUNAS):
        op.drop_column("tenant", nome)
