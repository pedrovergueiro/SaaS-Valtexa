"""Model Registry: campos da seção 9, estados novos e liberação por cliente.

Revisão: 0017
Anterior: 0016

``model_version`` já existia (0004) como um registro sem uso — nenhuma rota a
preenchia. Aqui ela ganha os campos da seção 9 do brief (cultura, problema,
arquitetura, dataset, métricas, tamanho, FLOPs, latência, memória,
hardware-alvo, artefato original e otimizado, dNATY, aprovação, publicação) e
os estados TREINAMENTO → VALIDAÇÃO → APROVADO → STAGING → PRODUÇÃO →
DESCONTINUADO. Os valores antigos são levados para os novos:

    registered, training → treinamento     trained    → validacao
    shadow               → staging         production → producao
    retired              → descontinuado

A volta leva ``aprovado`` para ``trained`` (o estado antigo não distinguia
aprovação). ``model_release`` é nova: liberação de um modelo para um cliente.

O catálogo de modelos é cadastrado no start da aplicação
(:func:`valtexa.services.model_registry.sincronizar_catalogo`), como planos e
hardware: só cria o que falta, nunca sobrescreve o que a equipe mudou.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: str | Sequence[str] | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OPCIONAIS = (
    ("name", sa.String(160)),
    ("problem", sa.String(160)),
    ("architecture", sa.String(120)),
    ("dataset_ref", sa.String(255)),
    ("trained_at", sa.DateTime(timezone=True)),
    ("size_bytes", sa.BigInteger()),
    ("flops", sa.BigInteger()),
    ("latency_ms", sa.Float()),
    ("memory_mb", sa.Float()),
    ("target_hardware", sa.String(120)),
    ("original_artifact_uri", sa.String(512)),
    ("original_artifact_sha256", sa.String(64)),
    ("optimized_artifact_uri", sa.String(512)),
    ("optimized_artifact_sha256", sa.String(64)),
    ("optimized_size_bytes", sa.BigInteger()),
    ("dnaty_version", sa.String(32)),
    ("license", sa.String(255)),
    ("caveat", sa.Text()),
    ("approved_at", sa.DateTime(timezone=True)),
)

IDA = {
    "registered": "treinamento",
    "training": "treinamento",
    "trained": "validacao",
    "shadow": "staging",
    "production": "producao",
    "retired": "descontinuado",
}
VOLTA = {
    "treinamento": "training",
    "validacao": "trained",
    "aprovado": "trained",
    "staging": "shadow",
    "producao": "production",
    "descontinuado": "retired",
}


def _troca_estados(mapa: dict[str, str]) -> None:
    tabela = sa.table("model_version", sa.column("state", sa.String))
    for antigo, novo in mapa.items():
        op.execute(tabela.update().where(tabela.c.state == antigo).values(state=novo))


def upgrade() -> None:
    with op.batch_alter_table("model_version") as batch_op:
        # A coluna nasceu (0004) como enum não nativo com o tamanho do maior valor
        # de então ("production", 10). "descontinuado" tem 13: o SQLite aceitava,
        # o Postgres recusa. Achado na Parte 5, na primeira migração num Postgres
        # de verdade — por isso a correção mora aqui, antes de existir banco migrado.
        batch_op.alter_column("state", existing_type=sa.String(10), type_=sa.String(32),
                              existing_nullable=False)
        for nome, tipo in OPCIONAIS:
            batch_op.add_column(sa.Column(nome, tipo, nullable=True))
        batch_op.add_column(
            sa.Column("crops", sa.JSON(), nullable=False, server_default=sa.text("'[]'"))
        )
        batch_op.add_column(
            sa.Column("variant", sa.String(32), nullable=False, server_default="padrão")
        )
        batch_op.add_column(
            sa.Column("recommended", sa.Boolean(), nullable=False, server_default=sa.true())
        )
        batch_op.add_column(
            sa.Column("release_scope", sa.String(8), nullable=False, server_default="todos")
        )
        batch_op.add_column(sa.Column("registered_by", sa.String(32), nullable=True))
        batch_op.add_column(sa.Column("approved_by", sa.String(32), nullable=True))
        batch_op.create_foreign_key(
            "fk_model_version_registered_by", "user", ["registered_by"], ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_foreign_key(
            "fk_model_version_approved_by", "user", ["approved_by"], ["id"], ondelete="SET NULL"
        )
    _troca_estados(IDA)

    op.create_table(
        "model_release",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("model_key", sa.String(length=64), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("released_by", sa.String(length=32), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_by", sa.String(length=32), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["released_by"], ["user.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["revoked_by"], ["user.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_model_release_tenant_id", "model_release", ["tenant_id"])
    op.create_index("ix_model_release_model_key", "model_release", ["model_key"])
    op.create_index("ix_model_release_created_at", "model_release", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_model_release_created_at", table_name="model_release")
    op.drop_index("ix_model_release_model_key", table_name="model_release")
    op.drop_index("ix_model_release_tenant_id", table_name="model_release")
    op.drop_table("model_release")

    _troca_estados(VOLTA)
    with op.batch_alter_table("model_version") as batch_op:
        batch_op.drop_constraint("fk_model_version_approved_by", type_="foreignkey")
        batch_op.drop_constraint("fk_model_version_registered_by", type_="foreignkey")
        for nome in ("approved_by", "registered_by", "release_scope", "recommended", "variant",
                     "crops"):
            batch_op.drop_column(nome)
        for nome, _ in reversed(OPCIONAIS):
            batch_op.drop_column(nome)
