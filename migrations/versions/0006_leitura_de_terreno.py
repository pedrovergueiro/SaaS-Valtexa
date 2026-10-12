"""A leitura de terreno guardada no talhão.

Revisão: 0006
Anterior: 0005

Duas colunas em ``field``: o resultado da última leitura de imagem e a data em
que ela foi feita.

Ficam gravadas porque quem produz e quem consome essa informação estão em telas
diferentes e em momentos diferentes: o encaixe de contorno a calcula, e é o
planejamento de missão que precisa dela — às vezes dias depois. Sem persistir, o
obstáculo achado teria que ser reencontrado a cada planejamento, o que significa
baixar tiles de novo, com a questão de licenciamento que vem junto (ver a nota no
topo de ``VALTEXA-B/app/basemap.py``).

A data existe para que o console possa dizer **quando** aquilo foi lido. Uma
leitura de um ano atrás descreve uma lavoura que já mudou, e um número sem data
seria lido como se fosse de hoje.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | Sequence[str] | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # JSON e não JSONB: a plataforma roda em SQLite no piloto e em Postgres em
    # produção, e este documento é lido inteiro, nunca consultado por dentro.
    op.add_column("field", sa.Column("terrain", sa.JSON(), nullable=True))
    op.add_column(
        "field", sa.Column("terrain_read_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("field", "terrain_read_at")
    op.drop_column("field", "terrain")
