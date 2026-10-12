"""Fusão por planta dos resultados do Rover (ponte Edge AI → ``/fields/{id}/frames``).

Revisão: 0026
Anterior: 0025

Três colunas anuláveis em ``edge_record`` (``fusion_status``, ``fusion_detail``,
``fused_at``): nulo é "ainda não foi para a fusão", e é o que o worker procura — pelo
índice ``ix_edge_record_kind_fusion``. Uma em ``mission`` (``fusion_closed_at``): quando a
passada da missão foi fechada na IA, depois de todos os resultados fundidos. Nada
existente muda de valor; os resultados já recebidos entram na fusão no próximo ciclo do
worker. A volta apaga as colunas e o índice.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0026"
down_revision: str | Sequence[str] | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("edge_record") as batch:
        batch.add_column(sa.Column("fusion_status", sa.String(length=16), nullable=True))
        batch.add_column(sa.Column("fusion_detail", sa.String(length=200), nullable=True))
        batch.add_column(sa.Column("fused_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_edge_record_kind_fusion", "edge_record", ["kind", "fusion_status"])
    with op.batch_alter_table("mission") as batch:
        batch.add_column(sa.Column("fusion_closed_at", sa.DateTime(timezone=True),
                                   nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("mission") as batch:
        batch.drop_column("fusion_closed_at")
    op.drop_index("ix_edge_record_kind_fusion", table_name="edge_record")
    with op.batch_alter_table("edge_record") as batch:
        batch.drop_column("fused_at")
        batch.drop_column("fusion_detail")
        batch.drop_column("fusion_status")
