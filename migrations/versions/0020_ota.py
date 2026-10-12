"""Atualização remota (OTA) do Rover: pacotes e destinos.

Revisão: 0020
Anterior: 0019

Duas tabelas novas, só de metadados (os bytes dos pacotes ficam no armazenamento
de objetos): ``ota_package`` e ``ota_deployment``. Nada existente muda; a volta
apaga as duas.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0020"
down_revision: str | Sequence[str] | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ota_package",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("version", sa.String(length=64), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("storage_key", sa.String(length=512), nullable=False),
        sa.Column("manifest", sa.JSON(), nullable=False),
        sa.Column("model_version_id", sa.String(length=32), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=32), nullable=True),
        sa.ForeignKeyConstraint(["model_version_id"], ["model_version.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["user.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("kind", "version", name="uq_ota_package_kind_version"),
    )
    op.create_index("ix_ota_package_kind", "ota_package", ["kind"])
    op.create_index("ix_ota_package_model_version_id", "ota_package", ["model_version_id"])
    op.create_index("ix_ota_package_created_at", "ota_package", ["created_at"])

    op.create_table(
        "ota_deployment",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("package_id", sa.String(length=32), nullable=False),
        sa.Column("device_id", sa.String(length=32), nullable=False),
        sa.Column("state", sa.String(length=24), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("envelope", sa.JSON(), nullable=False),
        sa.Column("history", sa.JSON(), nullable=False),
        sa.Column("bytes_served", sa.BigInteger(), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(length=32), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["package_id"], ["ota_package.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["device_id"], ["device.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["user.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    for coluna in ("tenant_id", "package_id", "device_id", "state", "created_at"):
        op.create_index(f"ix_ota_deployment_{coluna}", "ota_deployment", [coluna])


def downgrade() -> None:
    for coluna in ("created_at", "state", "device_id", "package_id", "tenant_id"):
        op.drop_index(f"ix_ota_deployment_{coluna}", table_name="ota_deployment")
    op.drop_table("ota_deployment")
    for nome in ("created_at", "model_version_id", "kind"):
        op.drop_index(f"ix_ota_package_{nome}", table_name="ota_package")
    op.drop_table("ota_package")
