"""Versão do modelo por talhão e os sinais da IA em cada detecção.

``field.ai_model`` — banana e citros têm duas versões do modelo de diagnóstico
(``campo``, mais precisa, com dado de licença não comercial; ``comercial``, só
CC BY). O talhão guarda qual usar; nulo segue ``PRIMARY_MODELS`` ou a versão
recomendada do catálogo.

``detection.signals`` — o que a IA disse além do rótulo: o veredito do portão de
enquadramento (a imagem é folha em close?), o conjunto conformal e, num quadro do
rover, o resumo dos recortes por zona da planta. O default no servidor é o que
deixa a coluna obrigatória entrar num banco que já tem detecções.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | Sequence[str] | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("field", sa.Column("ai_model", sa.String(length=64), nullable=True))
    op.add_column(
        "detection",
        sa.Column("signals", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )


def downgrade() -> None:
    op.drop_column("detection", "signals")
    op.drop_column("field", "ai_model")
