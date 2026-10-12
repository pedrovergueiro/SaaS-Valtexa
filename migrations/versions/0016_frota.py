"""Frota: versões, saúde e sincronização de cada robô (brief, seções 22, 25 e 26).

Revisão: 0016
Anterior: 0015

Colunas novas em ``device``, todas preenchidas pelo próprio robô através do
protocolo (sessão, telemetria e ``/sync``). Nenhuma tem valor inventado: num
banco que já tem robôs elas nascem vazias, e o console mostra "sem dado" até o
robô informar. ``active_faults`` e ``sync_pending`` têm default no servidor para
a coluna obrigatória entrar numa tabela com linhas.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016"
down_revision: str | Sequence[str] | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OPCIONAIS = (
    ("runtime_version", sa.String(32)),
    ("edge_ai_version", sa.String(32)),
    ("ai_model_key", sa.String(64)),
    ("ai_model_version", sa.String(32)),
    ("dnaty_version", sa.String(32)),
    ("versions_reported_at", sa.DateTime(timezone=True)),
    ("temperature_c", sa.Float()),
    ("storage_total_bytes", sa.BigInteger()),
    ("storage_free_bytes", sa.BigInteger()),
    ("link_quality", sa.Float()),
    ("operating_hours", sa.Float()),
    ("last_sync_at", sa.DateTime(timezone=True)),
    ("last_maintenance_at", sa.DateTime(timezone=True)),
    ("maintenance_note", sa.Text()),
)


def upgrade() -> None:
    with op.batch_alter_table("device") as batch_op:
        for nome, tipo in OPCIONAIS:
            batch_op.add_column(sa.Column(nome, tipo, nullable=True))
        batch_op.add_column(
            sa.Column("active_faults", sa.JSON(), nullable=False, server_default=sa.text("'[]'"))
        )
        batch_op.add_column(
            sa.Column("sync_pending", sa.Integer(), nullable=False, server_default="0")
        )


def downgrade() -> None:
    with op.batch_alter_table("device") as batch_op:
        batch_op.drop_column("sync_pending")
        batch_op.drop_column("active_faults")
        for nome, _ in reversed(OPCIONAIS):
            batch_op.drop_column(nome)
