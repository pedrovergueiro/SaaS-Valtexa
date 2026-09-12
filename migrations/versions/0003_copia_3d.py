"""Cópia 3D: as passadas do rover por rua.

Revisão: 0003
Anterior: 0002

``row_scan`` guarda cada passada — as plantas medidas e a nuvem de pontos — de
que a cópia 3D do talhão é composta.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "row_scan",
        sa.Column("farm_id", sa.String(length=32), nullable=False),
        sa.Column("field_id", sa.String(length=32), nullable=False),
        sa.Column("mission_id", sa.String(length=32), nullable=True),
        sa.Column("device_id", sa.String(length=32), nullable=False),
        sa.Column("sequence_number", sa.BigInteger(), nullable=False),
        sa.Column("segment_index", sa.Integer(), nullable=True),
        sa.Column("row_index", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sensor", sa.String(length=32), nullable=False),
        sa.Column("origin_lat", sa.Float(), nullable=False),
        sa.Column("origin_lon", sa.Float(), nullable=False),
        sa.Column("origin_alt_m", sa.Float(), nullable=True),
        sa.Column("path", sa.JSON(), nullable=False),
        sa.Column("reach_m", sa.Float(), nullable=False),
        sa.Column("length_m", sa.Float(), nullable=False),
        sa.Column("plants", sa.JSON(), nullable=False),
        sa.Column("plant_count", sa.Integer(), nullable=False),
        sa.Column("mean_height_m", sa.Float(), nullable=True),
        sa.Column("max_height_m", sa.Float(), nullable=True),
        sa.Column("pointcloud_asset_id", sa.String(length=32), nullable=True),
        sa.Column("point_count", sa.Integer(), nullable=True),
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["device_id"], ["device.id"]),
        sa.ForeignKeyConstraint(["farm_id"], ["farm.id"]),
        sa.ForeignKeyConstraint(["field_id"], ["field.id"]),
        sa.ForeignKeyConstraint(["mission_id"], ["mission.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["pointcloud_asset_id"], ["asset.id"]),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("device_id", "sequence_number", name="uq_row_scan_device_seq"),
    )
    with op.batch_alter_table("row_scan", schema=None) as batch_op:
        batch_op.create_index("ix_row_scan_field_time", ["field_id", "captured_at"], unique=False)
        batch_op.create_index(batch_op.f("ix_row_scan_mission_id"), ["mission_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_row_scan_tenant_id"), ["tenant_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_row_scan_created_at"), ["created_at"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("row_scan", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_row_scan_created_at"))
        batch_op.drop_index(batch_op.f("ix_row_scan_tenant_id"))
        batch_op.drop_index(batch_op.f("ix_row_scan_mission_id"))
        batch_op.drop_index("ix_row_scan_field_time")

    op.drop_table("row_scan")
