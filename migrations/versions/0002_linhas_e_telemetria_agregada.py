"""Orientação das linhas no talhão e telemetria agregada.

Revisão: 0002
Anterior: 0001

``field.row_azimuth_deg`` alinha o planejamento de cobertura às linhas de
plantio. ``telemetry_rollup`` recebe a telemetria crua depois da janela de
retenção, uma linha por minuto.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("field", schema=None) as batch_op:
        batch_op.add_column(sa.Column("row_azimuth_deg", sa.Float(), nullable=True))

    op.create_table(
        "telemetry_rollup",
        sa.Column("device_id", sa.String(length=32), nullable=False),
        sa.Column("bucket_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("bucket_seconds", sa.Integer(), nullable=False),
        sa.Column("samples", sa.Integer(), nullable=False),
        sa.Column("battery_min", sa.Float(), nullable=True),
        sa.Column("battery_avg", sa.Float(), nullable=True),
        sa.Column("battery_max", sa.Float(), nullable=True),
        sa.Column("speed_avg_ms", sa.Float(), nullable=True),
        sa.Column("link_quality_avg", sa.Float(), nullable=True),
        sa.Column("rtk_fixed_ratio", sa.Float(), nullable=True),
        sa.Column("last_lat", sa.Float(), nullable=True),
        sa.Column("last_lon", sa.Float(), nullable=True),
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["device_id"], ["device.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("device_id", "bucket_start", name="uq_rollup_device_bucket"),
    )
    with op.batch_alter_table("telemetry_rollup", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_telemetry_rollup_bucket_start"), ["bucket_start"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_telemetry_rollup_device_id"), ["device_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_telemetry_rollup_tenant_id"), ["tenant_id"], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table("telemetry_rollup", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_telemetry_rollup_tenant_id"))
        batch_op.drop_index(batch_op.f("ix_telemetry_rollup_device_id"))
        batch_op.drop_index(batch_op.f("ix_telemetry_rollup_bucket_start"))

    op.drop_table("telemetry_rollup")

    with op.batch_alter_table("field", schema=None) as batch_op:
        batch_op.drop_column("row_azimuth_deg")
