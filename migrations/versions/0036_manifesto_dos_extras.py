"""Manifesto dos arquivos que viajam ao lado do ONNX do modelo.

Revisão: 0036
Anterior: 0035

Uma coluna **anulável** em ``model_version`` (``extras_manifest_sha256``): o hash do manifesto
que ``valtexa-rover preparar-modelo`` imprime, com o SHA-256 de cada arquivo ao lado do ONNX
(perfil ``.edge.json``, cabeça, conformal, qualidade, novidade, rótulos). Versão antiga fica
sem manifesto e o robô continua conferindo só o ONNX, como antes. A volta remove a coluna.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0036"
down_revision: str | Sequence[str] | None = "0035"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("model_version") as lote:
        lote.add_column(sa.Column("extras_manifest_sha256", sa.String(length=64), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("model_version") as lote:
        lote.drop_column("extras_manifest_sha256")
