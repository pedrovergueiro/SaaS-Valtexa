"""Notificações (seção 48): avisos, entregas por canal e preferências.

Revisão: 0022
Anterior: 0021

Três tabelas novas: ``notification``, ``notification_delivery`` e
``notification_preference``. Nada existente muda; a volta apaga as três.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0022"
down_revision: str | Sequence[str] | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "notification",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=True),
        sa.Column("user_id", sa.String(length=32), nullable=False),
        sa.Column("audience", sa.String(length=16), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("subject_type", sa.String(length=32), nullable=True),
        sa.Column("subject_id", sa.String(length=32), nullable=True),
        sa.Column("link", sa.String(length=300), nullable=True),
        sa.Column("event_id", sa.String(length=32), nullable=True),
        sa.Column("dedup_key", sa.String(length=160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "dedup_key", name="uq_notification_user_dedup"),
    )
    op.create_index("ix_notification_tenant_id", "notification", ["tenant_id"])
    op.create_index("ix_notification_kind", "notification", ["kind"])
    op.create_index("ix_notification_event_id", "notification", ["event_id"])
    op.create_index("ix_notification_created_at", "notification", ["created_at"])
    op.create_index(
        "ix_notification_inbox", "notification", ["user_id", "audience", "tenant_id", "read_at"]
    )

    op.create_table(
        "notification_delivery",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("notification_id", sa.String(length=32), nullable=False),
        sa.Column("channel", sa.String(length=16), nullable=False),
        sa.Column("destination", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["notification_id"], ["notification.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("notification_id", "channel", name="uq_delivery_notification_channel"),
    )
    op.create_index("ix_notification_delivery_created_at", "notification_delivery", ["created_at"])
    op.create_index(
        "ix_notification_delivery_notification_id", "notification_delivery", ["notification_id"]
    )
    op.create_index("ix_delivery_due", "notification_delivery", ["status", "next_attempt_at"])

    op.create_table(
        "notification_preference",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("scope_key", sa.String(length=140), nullable=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=True),
        sa.Column("user_id", sa.String(length=32), nullable=True),
        sa.Column("role", sa.String(length=16), nullable=True),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("channels", sa.JSON(), nullable=False),
        sa.Column("threshold", sa.Float(), nullable=True),
        sa.Column("updated_by", sa.String(length=32), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["updated_by"], ["user.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("scope_key"),
    )
    op.create_index(
        "ix_notification_preference_created_at", "notification_preference", ["created_at"]
    )
    op.create_index(
        "ix_notification_preference_tenant_id", "notification_preference", ["tenant_id"]
    )
    op.create_index("ix_notification_preference_user_id", "notification_preference", ["user_id"])


def downgrade() -> None:
    for nome in ("user_id", "tenant_id", "created_at"):
        op.drop_index(f"ix_notification_preference_{nome}", table_name="notification_preference")
    op.drop_table("notification_preference")
    op.drop_index("ix_delivery_due", table_name="notification_delivery")
    for nome in ("notification_id", "created_at"):
        op.drop_index(f"ix_notification_delivery_{nome}", table_name="notification_delivery")
    op.drop_table("notification_delivery")
    for nome in ("inbox", "created_at", "event_id", "kind", "tenant_id"):
        op.drop_index(f"ix_notification_{nome}", table_name="notification")
    op.drop_table("notification")
