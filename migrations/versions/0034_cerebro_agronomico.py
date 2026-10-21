"""Cérebro agronômico: repositório de conhecimento versionado e pareceres (8.1, 8.2).

Revisão: 0034
Anterior: 0033

Quatro tabelas novas (``documento_conhecimento``, ``trecho_conhecimento``, ``parecer``,
``revisao_parecer``). Nada existente muda. A volta apaga as quatro, na ordem das chaves.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0034"
down_revision: str | Sequence[str] | None = "0033"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _tempos() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "documento_conhecimento",
        sa.Column("id", sa.String(length=32), nullable=False),
        *_tempos(),
        sa.Column("tenant_id", sa.String(length=32), nullable=True),
        sa.Column("chave", sa.String(length=120), nullable=False),
        sa.Column("versao", sa.String(length=40), nullable=False),
        sa.Column("titulo", sa.String(length=300), nullable=False),
        sa.Column("tipo", sa.String(length=32), nullable=False),
        sa.Column("origem", sa.String(length=500), nullable=False),
        sa.Column("publicado_em", sa.Date(), nullable=True),
        sa.Column("verificado_em", sa.Date(), nullable=True),
        sa.Column("verificado_por", sa.String(length=32), nullable=True),
        sa.Column("valido_ate", sa.Date(), nullable=True),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("licenca", sa.String(length=200), nullable=False),
        sa.Column("culturas", sa.JSON(), nullable=False),
        sa.Column("alvos", sa.JSON(), nullable=False),
        sa.Column("ficticio", sa.Boolean(), nullable=False),
        sa.Column("estado", sa.String(length=16), nullable=False),
        sa.Column("substituido_por", sa.String(length=32), nullable=True),
        sa.Column("formato", sa.String(length=16), nullable=False),
        sa.Column("arquivo_nome", sa.String(length=255), nullable=True),
        sa.Column("conteudo", sa.Text(), nullable=False),
        sa.Column("ingerido_por", sa.String(length=32), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["verificado_por"], ["user.id"]),
        sa.ForeignKeyConstraint(["ingerido_por"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_documento_conhecimento_tenant_id", "documento_conhecimento",
                    ["tenant_id"])
    op.create_index("ix_documento_conhecimento_created_at", "documento_conhecimento",
                    ["created_at"])
    op.create_index("ix_documento_conhecimento_sha256", "documento_conhecimento", ["sha256"])
    op.create_index("ix_documento_conhecimento_chave", "documento_conhecimento",
                    ["chave", "versao"])
    op.create_index("ix_documento_conhecimento_tipo_estado", "documento_conhecimento",
                    ["tipo", "estado"])

    op.create_table(
        "trecho_conhecimento",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("documento_id", sa.String(length=32), nullable=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=True),
        sa.Column("ordem", sa.Integer(), nullable=False),
        sa.Column("secao", sa.String(length=300), nullable=True),
        sa.Column("texto", sa.Text(), nullable=False),
        sa.Column("inicio", sa.Integer(), nullable=False),
        sa.Column("fim", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(["documento_id"], ["documento_conhecimento.id"],
                                ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_trecho_conhecimento_documento_id", "trecho_conhecimento",
                    ["documento_id"])
    op.create_index("ix_trecho_conhecimento_tenant_id", "trecho_conhecimento", ["tenant_id"])

    op.create_table(
        "parecer",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        *_tempos(),
        sa.Column("field_id", sa.String(length=32), nullable=False),
        sa.Column("caso_tipo", sa.String(length=16), nullable=False),
        sa.Column("plant_ref", sa.String(length=80), nullable=True),
        sa.Column("observation_id", sa.String(length=32), nullable=True),
        sa.Column("modo", sa.String(length=16), nullable=False),
        sa.Column("provedor", sa.String(length=64), nullable=True),
        sa.Column("versao_compositor", sa.String(length=32), nullable=False),
        sa.Column("dossie", sa.JSON(), nullable=False),
        sa.Column("dossie_sha256", sa.String(length=64), nullable=False),
        sa.Column("fontes", sa.JSON(), nullable=False),
        sa.Column("afirmacoes", sa.JSON(), nullable=False),
        sa.Column("verificacoes", sa.JSON(), nullable=False),
        sa.Column("recusas", sa.JSON(), nullable=False),
        sa.Column("texto", sa.Text(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("estado", sa.String(length=24), nullable=False),
        sa.Column("gerado_por", sa.String(length=32), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["field_id"], ["field.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["observation_id"], ["observation.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["gerado_por"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_parecer_tenant_id", "parecer", ["tenant_id"])
    op.create_index("ix_parecer_created_at", "parecer", ["created_at"])
    op.create_index("ix_parecer_observation_id", "parecer", ["observation_id"])
    op.create_index("ix_parecer_field_planta", "parecer", ["field_id", "plant_ref"])

    op.create_table(
        "revisao_parecer",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        *_tempos(),
        sa.Column("parecer_id", sa.String(length=32), nullable=False),
        sa.Column("revisor_id", sa.String(length=32), nullable=False),
        sa.Column("papel", sa.String(length=24), nullable=False),
        sa.Column("decisao", sa.String(length=16), nullable=False),
        sa.Column("comentario", sa.Text(), nullable=True),
        sa.Column("diagnostico_revisor", sa.String(length=80), nullable=True),
        sa.Column("parecer_sha256", sa.String(length=64), nullable=False),
        sa.Column("revisado_em", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parecer_id"], ["parecer.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["revisor_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_revisao_parecer_tenant_id", "revisao_parecer", ["tenant_id"])
    op.create_index("ix_revisao_parecer_created_at", "revisao_parecer", ["created_at"])
    op.create_index("ix_revisao_parecer_parecer_id", "revisao_parecer", ["parecer_id"])


def downgrade() -> None:
    for indice in ("ix_revisao_parecer_parecer_id", "ix_revisao_parecer_created_at",
                   "ix_revisao_parecer_tenant_id"):
        op.drop_index(indice, table_name="revisao_parecer")
    op.drop_table("revisao_parecer")
    for indice in ("ix_parecer_field_planta", "ix_parecer_observation_id",
                   "ix_parecer_created_at", "ix_parecer_tenant_id"):
        op.drop_index(indice, table_name="parecer")
    op.drop_table("parecer")
    for indice in ("ix_trecho_conhecimento_tenant_id", "ix_trecho_conhecimento_documento_id"):
        op.drop_index(indice, table_name="trecho_conhecimento")
    op.drop_table("trecho_conhecimento")
    for indice in ("ix_documento_conhecimento_tipo_estado", "ix_documento_conhecimento_chave",
                   "ix_documento_conhecimento_sha256", "ix_documento_conhecimento_created_at",
                   "ix_documento_conhecimento_tenant_id"):
        op.drop_index(indice, table_name="documento_conhecimento")
    op.drop_table("documento_conhecimento")
