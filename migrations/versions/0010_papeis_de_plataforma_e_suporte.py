"""Papéis da equipe da ValTexa e sessões de suporte ("entrar como cliente").

Revisão: 0010
Anterior: 0009

* ``user.platform_role`` substitui ``user.is_platform_admin``. Quem tinha a marca
  vira ``superadmin`` — o mesmo poder que tinha, agora com nome. A coluna antiga
  sai na mesma migração: duas fontes da verdade para "quem é da equipe" é o
  tipo de coisa que diverge em silêncio. O código continua lendo
  ``User.is_platform_admin`` (propriedade derivada do papel).
* ``support_session``: quem da equipe entrou em qual cliente, por quê, até
  quando, em que modo, e quando saiu.
* ``audit_entry.support_session_id``: liga cada ação feita dentro de uma sessão
  de suporte à sessão, para o cliente ver o que a equipe fez.

**Efeito ao aplicar:** a equipe da ValTexa deixa de entrar silenciosamente como
``admin`` em cliente de que não é membro. Para ver dados de um cliente, abre
sessão de suporte (``POST /v1/platform/support-sessions``).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | Sequence[str] | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("user") as batch_op:
        batch_op.add_column(sa.Column("platform_role", sa.String(length=16), nullable=True))
    op.execute(
        sa.text(
            "UPDATE \"user\" SET platform_role = 'superadmin' WHERE is_platform_admin = :sim"
        ).bindparams(sim=True)
    )
    with op.batch_alter_table("user") as batch_op:
        batch_op.drop_column("is_platform_admin")
        batch_op.create_index("ix_user_platform_role", ["platform_role"], unique=False)

    op.create_table(
        "support_session",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("user_id", sa.String(length=32), nullable=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("user_session_id", sa.String(length=32), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("ticket_ref", sa.String(length=80), nullable=True),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("assisted_reason", sa.Text(), nullable=True),
        sa.Column("assisted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_reason", sa.String(length=200), nullable=True),
        sa.Column("request_count", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_session_id"], ["user_session.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_support_session_user_id", "support_session", ["user_id"])
    op.create_index("ix_support_session_tenant_id", "support_session", ["tenant_id"])
    op.create_index("ix_support_session_ended_at", "support_session", ["ended_at"])
    op.create_index("ix_support_session_created_at", "support_session", ["created_at"])

    with op.batch_alter_table("audit_entry") as batch_op:
        batch_op.add_column(
            sa.Column("support_session_id", sa.String(length=32), nullable=True)
        )
        batch_op.create_index(
            "ix_audit_entry_support_session_id", ["support_session_id"], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table("audit_entry") as batch_op:
        batch_op.drop_index("ix_audit_entry_support_session_id")
        batch_op.drop_column("support_session_id")

    op.drop_index("ix_support_session_created_at", table_name="support_session")
    op.drop_index("ix_support_session_ended_at", table_name="support_session")
    op.drop_index("ix_support_session_tenant_id", table_name="support_session")
    op.drop_index("ix_support_session_user_id", table_name="support_session")
    op.drop_table("support_session")

    with op.batch_alter_table("user") as batch_op:
        batch_op.add_column(
            sa.Column(
                "is_platform_admin", sa.Boolean(), nullable=False, server_default=sa.false()
            )
        )
    # Qualquer papel de plataforma volta a ser a marca única de antes: é o que
    # ela significava. Volta-se a perder a distinção entre os papéis.
    op.execute(
        sa.text(
            "UPDATE \"user\" SET is_platform_admin = :sim WHERE platform_role IS NOT NULL"
        ).bindparams(sim=True)
    )
    with op.batch_alter_table("user") as batch_op:
        batch_op.drop_index("ix_user_platform_role")
        batch_op.drop_column("platform_role")
