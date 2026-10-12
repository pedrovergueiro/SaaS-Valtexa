"""Rótulo de campo por planta (``plant_label``): a ficha do agrônomo na validação.

Revisão: 0027
Anterior: 0026

Uma tabela nova: o que o agrônomo anotou em cada planta das fileiras de validação, por
passada do Rover. Alimenta o relatório Rover contra agrônomo e a recalibração da IA (ver
``valtexa.models.validacao``). Nada existente muda. A volta apaga a tabela.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0027"
down_revision: str | Sequence[str] | None = "0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "plant_label",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("field_id", sa.String(length=32), nullable=False),
        sa.Column("mission_id", sa.String(length=32), nullable=False),
        sa.Column("plant_ref", sa.String(length=80), nullable=False),
        sa.Column("row_ref", sa.String(length=80), nullable=True),
        sa.Column("label", sa.String(length=80), nullable=False),
        sa.Column("incidence_percent", sa.Float(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("labeled_by", sa.String(length=32), nullable=True),
        sa.Column("labeled_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["field_id"], ["field.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["mission_id"], ["mission.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["labeled_by"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("field_id", "mission_id", "plant_ref", name="uq_plant_label_planta"),
    )
    op.create_index("ix_plant_label_field_mission", "plant_label", ["field_id", "mission_id"])
    op.create_index("ix_plant_label_tenant_id", "plant_label", ["tenant_id"])
    op.create_index("ix_plant_label_created_at", "plant_label", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_plant_label_created_at", table_name="plant_label")
    op.drop_index("ix_plant_label_tenant_id", table_name="plant_label")
    op.drop_index("ix_plant_label_field_mission", table_name="plant_label")
    op.drop_table("plant_label")
