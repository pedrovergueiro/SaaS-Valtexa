"""Consenso antes do treino e regras do agrônomo medidas.

Revisão: 0038
Anterior: 0037

* ``opiniao_amostra`` — a segunda opinião sobre uma amostra do dataset;
* ``regra_agronomo`` — o que o agrônomo sabe, escrito como regra que se pode medir;
* ``dataset_version.criterio`` — a política com que o corte foi congelado e o que ficou fora
  (cortes antigos ficam com ``{}``: "um agrônomo basta", a regra de antes).

A volta desfaz as três.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0038"
down_revision: str | Sequence[str] | None = "0037"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _tempos() -> list[sa.Column]:
    return [sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False)]


def upgrade() -> None:
    with op.batch_alter_table("dataset_version") as lote:
        lote.add_column(sa.Column("criterio", sa.JSON(), nullable=False,
                                  server_default=sa.text("'{}'")))

    op.create_table(
        "opiniao_amostra",
        sa.Column("id", sa.String(length=32), nullable=False),
        *_tempos(),
        sa.Column("dataset_sample_id", sa.String(length=32), nullable=False),
        sa.Column("revisor_id", sa.String(length=32), nullable=True),
        sa.Column("revisor_rotulo", sa.String(length=255), nullable=False),
        sa.Column("origem", sa.String(length=16), nullable=False),
        sa.Column("rotulo", sa.String(length=120), nullable=False),
        sa.Column("concorda", sa.Boolean(), nullable=False),
        sa.Column("comentario", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["dataset_sample_id"], ["dataset_sample.id"],
                                ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["revisor_id"], ["user.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dataset_sample_id", "revisor_id",
                            name="uq_opiniao_amostra_revisor"),
    )
    op.create_index("ix_opiniao_amostra_created_at", "opiniao_amostra", ["created_at"])
    op.create_index("ix_opiniao_amostra_dataset_sample_id", "opiniao_amostra",
                    ["dataset_sample_id"])
    op.create_index("ix_opiniao_amostra_revisor_id", "opiniao_amostra", ["revisor_id"])

    op.create_table(
        "regra_agronomo",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        *_tempos(),
        sa.Column("autor_id", sa.String(length=32), nullable=True),
        sa.Column("autor_rotulo", sa.String(length=255), nullable=False),
        sa.Column("cultura", sa.String(length=64), nullable=False),
        sa.Column("doenca", sa.String(length=120), nullable=False),
        sa.Column("texto", sa.Text(), nullable=False),
        sa.Column("condicao", sa.JSON(), nullable=False),
        sa.Column("efeito", sa.String(length=16), nullable=False),
        sa.Column("ativa", sa.Boolean(), nullable=False),
        sa.Column("medida", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["autor_id"], ["user.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_regra_agronomo_tenant_id", "regra_agronomo", ["tenant_id"])
    op.create_index("ix_regra_agronomo_created_at", "regra_agronomo", ["created_at"])
    op.create_index("ix_regra_agronomo_autor_id", "regra_agronomo", ["autor_id"])
    op.create_index("ix_regra_agronomo_doenca", "regra_agronomo", ["doenca"])


def downgrade() -> None:
    op.drop_table("regra_agronomo")
    op.drop_table("opiniao_amostra")
    with op.batch_alter_table("dataset_version") as lote:
        lote.drop_column("criterio")
