"""O agrônomo ensinando a IA: a lição com o porquê e as lesões marcadas.

Revisão: 0037
Anterior: 0036

Uma tabela nova, ``licao_agronomo`` (ver ``valtexa/models/ensino.py``); nada do que existe
muda. A volta apaga a tabela.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0037"
down_revision: str | Sequence[str] | None = "0036"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "licao_agronomo",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("field_id", sa.String(length=32), nullable=False),
        sa.Column("origem", sa.String(length=16), nullable=False),
        sa.Column("observation_id", sa.String(length=32), nullable=True),
        sa.Column("diagnosis_id", sa.String(length=32), nullable=True),
        sa.Column("parecer_id", sa.String(length=32), nullable=True),
        sa.Column("plant_ref", sa.String(length=80), nullable=True),
        sa.Column("autor_id", sa.String(length=32), nullable=True),
        sa.Column("autor_rotulo", sa.String(length=255), nullable=False),
        sa.Column("rotulo", sa.String(length=120), nullable=False),
        sa.Column("rotulo_da_ia", sa.String(length=120), nullable=True),
        sa.Column("sintomas", sa.JSON(), nullable=False),
        sa.Column("estrato", sa.String(length=24), nullable=True),
        sa.Column("face", sa.String(length=16), nullable=True),
        sa.Column("porque", sa.Text(), nullable=True),
        sa.Column("lesoes", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["field_id"], ["field.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["observation_id"], ["observation.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["diagnosis_id"], ["diagnosis.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["parecer_id"], ["parecer.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["autor_id"], ["user.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_licao_agronomo_tenant_id", "licao_agronomo", ["tenant_id"])
    op.create_index("ix_licao_agronomo_created_at", "licao_agronomo", ["created_at"])
    op.create_index("ix_licao_agronomo_observation_id", "licao_agronomo", ["observation_id"])
    op.create_index("ix_licao_agronomo_diagnosis_id", "licao_agronomo", ["diagnosis_id"])
    op.create_index("ix_licao_agronomo_field_rotulo", "licao_agronomo", ["field_id", "rotulo"])
    op.create_index("ix_licao_agronomo_autor", "licao_agronomo", ["autor_id"])


def downgrade() -> None:
    op.drop_table("licao_agronomo")
