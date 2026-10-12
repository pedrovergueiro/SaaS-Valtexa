"""Ponte Edge AI → IA de nuvem: o evento do robô ligado à observação que a nuvem abriu.

Revisão: 0021
Anterior: 0020

Uma coluna nova, anulável: ``edge_record.observation_id``. Nada existente muda;
a volta apaga a coluna.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0021"
down_revision: str | Sequence[str] | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("edge_record") as batch:
        batch.add_column(sa.Column("observation_id", sa.String(length=32), nullable=True))
        batch.create_foreign_key("fk_edge_record_observation", "observation",
                                 ["observation_id"], ["id"], ondelete="SET NULL")
        batch.create_index("ix_edge_record_observation_id", ["observation_id"])


def downgrade() -> None:
    with op.batch_alter_table("edge_record") as batch:
        batch.drop_index("ix_edge_record_observation_id")
        batch.drop_constraint("fk_edge_record_observation", type_="foreignkey")
        batch.drop_column("observation_id")
