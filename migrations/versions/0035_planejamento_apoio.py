"""Planejamento de apoio à decisão (8.3) e o modo de ação do produto, com a fonte.

Revisão: 0035
Anterior: 0034

Duas tabelas novas (``plano_apoio``, ``revisao_plano_apoio``) e duas colunas **anuláveis** em
``product`` (``modo_de_acao``, ``fonte_documento_id``): produto antigo fica como estava (fora
da análise de rotação até alguém cadastrar o modo de ação e a fonte). A volta desfaz tudo.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0035"
down_revision: str | Sequence[str] | None = "0034"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _tempos() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade() -> None:
    with op.batch_alter_table("product") as lote:
        lote.add_column(sa.Column("modo_de_acao", sa.String(length=32), nullable=True))
        lote.add_column(sa.Column("fonte_documento_id", sa.String(length=32), nullable=True))
        lote.create_foreign_key("fk_product_fonte_documento", "documento_conhecimento",
                                ["fonte_documento_id"], ["id"], ondelete="SET NULL")

    op.create_table(
        "plano_apoio",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        *_tempos(),
        sa.Column("tipo", sa.String(length=16), nullable=False),
        sa.Column("farm_id", sa.String(length=32), nullable=True),
        sa.Column("field_id", sa.String(length=32), nullable=True),
        sa.Column("versao_motor", sa.String(length=32), nullable=False),
        sa.Column("pedido", sa.JSON(), nullable=False),
        sa.Column("premissas", sa.JSON(), nullable=False),
        sa.Column("resultado", sa.JSON(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("estado", sa.String(length=24), nullable=False),
        sa.Column("gerado_por", sa.String(length=32), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["farm_id"], ["farm.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["field_id"], ["field.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["gerado_por"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_plano_apoio_tenant_id", "plano_apoio", ["tenant_id"])
    op.create_index("ix_plano_apoio_created_at", "plano_apoio", ["created_at"])
    op.create_index("ix_plano_apoio_tipo_field", "plano_apoio", ["tipo", "field_id"])

    op.create_table(
        "revisao_plano_apoio",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        *_tempos(),
        sa.Column("plano_id", sa.String(length=32), nullable=False),
        sa.Column("revisor_id", sa.String(length=32), nullable=False),
        sa.Column("papel", sa.String(length=24), nullable=False),
        sa.Column("decisao", sa.String(length=16), nullable=False),
        sa.Column("comentario", sa.Text(), nullable=True),
        sa.Column("plano_sha256", sa.String(length=64), nullable=False),
        sa.Column("revisado_em", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["plano_id"], ["plano_apoio.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["revisor_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_revisao_plano_apoio_tenant_id", "revisao_plano_apoio", ["tenant_id"])
    op.create_index("ix_revisao_plano_apoio_created_at", "revisao_plano_apoio",
                    ["created_at"])
    op.create_index("ix_revisao_plano_apoio_plano_id", "revisao_plano_apoio", ["plano_id"])


def downgrade() -> None:
    for indice in ("ix_revisao_plano_apoio_plano_id", "ix_revisao_plano_apoio_created_at",
                   "ix_revisao_plano_apoio_tenant_id"):
        op.drop_index(indice, table_name="revisao_plano_apoio")
    op.drop_table("revisao_plano_apoio")
    for indice in ("ix_plano_apoio_tipo_field", "ix_plano_apoio_created_at",
                   "ix_plano_apoio_tenant_id"):
        op.drop_index(indice, table_name="plano_apoio")
    op.drop_table("plano_apoio")
    with op.batch_alter_table("product") as lote:
        lote.drop_constraint("fk_product_fonte_documento", type_="foreignkey")
        lote.drop_column("fonte_documento_id")
        lote.drop_column("modo_de_acao")
