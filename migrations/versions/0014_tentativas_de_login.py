"""Tentativas de login, para limitar quem tenta senha atrás de senha.

Tabela nova, sem dado a migrar. O downgrade só a remove.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: str | Sequence[str] | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "login_attempt",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("ip", sa.String(length=64), nullable=True),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=False),
    )
    op.create_index("ix_login_attempt_email_at", "login_attempt", ["email", "at"])
    op.create_index("ix_login_attempt_ip_at", "login_attempt", ["ip", "at"])


def downgrade() -> None:
    op.drop_index("ix_login_attempt_ip_at", table_name="login_attempt")
    op.drop_index("ix_login_attempt_email_at", table_name="login_attempt")
    op.drop_table("login_attempt")
