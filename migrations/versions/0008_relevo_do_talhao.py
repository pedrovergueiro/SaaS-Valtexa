"""O relevo medido do talhão.

Revisão: 0008
Anterior: 0007

Duas colunas em ``field``: o resumo do relevo e quando ele foi medido.

Coluna própria, e não um campo dentro de ``terrain``, porque as duas medições
descrevem o mesmo pedaço de chão mas envelhecem em ritmos incomparáveis. A
cobertura do solo muda a cada safra — é por isso que a leitura de imagem cai
junto com o contorno. A encosta não muda nunca. Guardá-las juntas faria toda
releitura de imagem apagar uma consulta de DEM que continua perfeitamente
válida, e consulta de DEM custa dinheiro ou cota.

O relevo cai por um motivo só: contorno novo. Aí o pedaço de chão medido é
outro, e a medida antiga descreveria um talhão que não existe mais.

**Fica nulo em toda instalação** até alguém configurar ``ELEVATION_URL``. É
deliberado: um zero aqui seria lido como "terreno plano" e entraria no plano de
rota com a autoridade de uma medição.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | Sequence[str] | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("field", sa.Column("relief", sa.JSON(), nullable=True))
    op.add_column("field", sa.Column("relief_read_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("field", "relief_read_at")
    op.drop_column("field", "relief")
