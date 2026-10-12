"""Centro de comando do Rover: comandos remotos assinados, controle remoto e modelo fixado.

Revisão: 0028
Anterior: 0027

Uma tabela nova (``device_command``: o que a equipe mandou ao robô e o que ele respondeu)
e colunas anuláveis em ``device``: o modelo fixado (``pinned_model_*``), o último modo
pedido (``control_mode``) e o ponto de ajuste do controle remoto (``teleop_*``, que vence
em ~1 s — o homem-morto). ``teleop_seq`` começa em 0. Nada existente muda de valor. A
volta apaga a tabela e as colunas.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0028"
down_revision: str | Sequence[str] | None = "0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "device_command",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("device_id", sa.String(length=32), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("params", sa.JSON(), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("envelope", sa.JSON(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=32), nullable=True),
        sa.ForeignKeyConstraint(["device_id"], ["device.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_device_command_device_state", "device_command", ["device_id", "state"])
    op.create_index("ix_device_command_tenant_id", "device_command", ["tenant_id"])
    op.create_index("ix_device_command_created_at", "device_command", ["created_at"])
    with op.batch_alter_table("device") as batch:
        batch.add_column(sa.Column("pinned_model_key", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("pinned_model_version", sa.String(length=32), nullable=True))
        batch.add_column(sa.Column("control_mode", sa.String(length=16), nullable=True))
        batch.add_column(sa.Column("teleop_v", sa.Float(), nullable=True))
        batch.add_column(sa.Column("teleop_w", sa.Float(), nullable=True))
        batch.add_column(sa.Column("teleop_until", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("teleop_seq", sa.Integer(), nullable=False,
                                   server_default="0"))
        batch.add_column(sa.Column("teleop_by", sa.String(length=32), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("device") as batch:
        for coluna in ("teleop_by", "teleop_seq", "teleop_until", "teleop_w", "teleop_v",
                       "control_mode", "pinned_model_version", "pinned_model_key"):
            batch.drop_column(coluna)
    op.drop_index("ix_device_command_created_at", table_name="device_command")
    op.drop_index("ix_device_command_tenant_id", table_name="device_command")
    op.drop_index("ix_device_command_device_state", table_name="device_command")
    op.drop_table("device_command")
