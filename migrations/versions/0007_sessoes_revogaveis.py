"""Sessões de usuário, para que um token possa ser desdito.

Revisão: 0007
Anterior: 0006

Até aqui, o token de sessão era um papel assinado: valia até vencer, e nada no
servidor podia cancelá-lo. Doze horas é pouco para atrapalhar um invasor e muito
para um notebook roubado — e essa diferença é justamente a decisão que alguém
precisa poder tomar às pressas.

A tabela guarda uma linha por sessão aberta, e o token passa a carregar o ``id``
dela. Toda requisição autenticada confere a linha: custa uma consulta por
chamada, e é o que permite responder "esta sessão acabou **agora**".

Nada aqui guarda o token. As colunas descritivas (``user_agent``, ``ip_address``)
existem para a pessoa se reconhecer na lista e decidir o que derrubar; guardar o
token seria fazer uma segunda cópia da credencial e deixá-la à espera de
vazamento.

**Efeito ao aplicar:** os tokens emitidos antes desta migração não têm ``sid`` e
passam a ser recusados — todo mundo precisa entrar de novo. É deliberado:
aceitá-los manteria de pé exatamente as sessões que não se consegue alcançar.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | Sequence[str] | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_session",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("user_id", sa.String(length=32), nullable=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_by", sa.String(length=32), nullable=True),
        sa.Column("revoked_reason", sa.String(length=200), nullable=True),
        sa.Column("user_agent", sa.String(length=300), nullable=True),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["revoked_by"], ["user.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_user_session_user_id", "user_session", ["user_id"])
    op.create_index("ix_user_session_tenant_id", "user_session", ["tenant_id"])
    # A consulta quente é "sessões vivas desta pessoa", e ela filtra por
    # revogação. Sem este índice, cada requisição autenticada varreria a tabela
    # inteira — e é uma tabela que só cresce.
    op.create_index("ix_user_session_revoked_at", "user_session", ["revoked_at"])


def downgrade() -> None:
    op.drop_index("ix_user_session_revoked_at", table_name="user_session")
    op.drop_index("ix_user_session_tenant_id", table_name="user_session")
    op.drop_index("ix_user_session_user_id", table_name="user_session")
    op.drop_table("user_session")
