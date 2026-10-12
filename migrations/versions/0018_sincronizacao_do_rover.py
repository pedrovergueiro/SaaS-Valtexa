"""Sincronização do Rover Runtime: registros da Edge AI e uploads em chunks.

Revisão: 0018
Anterior: 0017

Duas tabelas novas, só de metadados (os bytes vão para o armazenamento de
objetos): ``edge_record`` (resultados e eventos, únicos por robô e ID) e
``edge_upload`` (arquivos chegando em pedaços, únicos por robô e ID do upload).
Nada existente muda; a volta apaga as duas.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018"
down_revision: str | Sequence[str] | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "edge_record",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("device_id", sa.String(length=32), nullable=False),
        sa.Column("record_id", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("type", sa.String(length=64), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("mission_id", sa.String(length=32), nullable=True),
        sa.Column("field_id", sa.String(length=32), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=True),
        sa.Column("label", sa.String(length=120), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("model_key", sa.String(length=64), nullable=True),
        sa.Column("model_version", sa.String(length=64), nullable=True),
        sa.Column("lat", sa.Float(), nullable=True),
        sa.Column("lon", sa.Float(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["device_id"], ["device.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["mission_id"], ["mission.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["field_id"], ["field.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("device_id", "record_id", name="uq_edge_record_device_record"),
    )
    op.create_index("ix_edge_record_tenant_id", "edge_record", ["tenant_id"])
    op.create_index("ix_edge_record_device_id", "edge_record", ["device_id"])
    op.create_index("ix_edge_record_type", "edge_record", ["type"])
    op.create_index("ix_edge_record_field_id", "edge_record", ["field_id"])
    op.create_index("ix_edge_record_tenant_mission", "edge_record", ["tenant_id", "mission_id"])

    op.create_table(
        "edge_upload",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("device_id", sa.String(length=32), nullable=False),
        sa.Column("upload_id", sa.String(length=80), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("content_type", sa.String(length=64), nullable=False),
        sa.Column("chunk_size", sa.Integer(), nullable=False),
        sa.Column("total_chunks", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("record_id", sa.String(length=64), nullable=True),
        sa.Column("role", sa.String(length=32), nullable=True),
        sa.Column("tier", sa.String(length=16), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=True),
        sa.Column("asset_id", sa.String(length=32), nullable=True),
        sa.Column("deduplicated", sa.Boolean(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["device_id"], ["device.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["asset_id"], ["asset.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("device_id", "upload_id", name="uq_edge_upload_device_upload"),
    )
    op.create_index("ix_edge_upload_tenant_id", "edge_upload", ["tenant_id"])
    op.create_index("ix_edge_upload_device_id", "edge_upload", ["device_id"])
    op.create_index("ix_edge_upload_sha256", "edge_upload", ["sha256"])
    op.create_index("ix_edge_upload_record_id", "edge_upload", ["record_id"])
    op.create_index("ix_edge_upload_created_at", "edge_upload", ["created_at"])


def downgrade() -> None:
    for nome in ("created_at", "record_id", "sha256", "device_id", "tenant_id"):
        op.drop_index(f"ix_edge_upload_{nome}", table_name="edge_upload")
    op.drop_table("edge_upload")
    for nome in ("tenant_mission", "field_id", "type", "device_id", "tenant_id"):
        op.drop_index(f"ix_edge_record_{nome}", table_name="edge_record")
    op.drop_table("edge_record")
