"""Índices de produção (Parte 9): os que os modelos declaram e as migrações esqueceram.

Revisão: 0025
Anterior: 0024

``alembic check`` contra um banco migrado do zero acusou três índices que existem nos
modelos (``Timestamped.created_at``) e nunca foram criados por migração — em produção
(banco feito pelo Alembic) eles faltavam; nos testes (``create_all``) não:

* ``ix_alert_created_at``, ``ix_alert_rule_created_at`` (tabelas da 0024);
* ``ix_user_session_created_at`` (tabela da 0007).

E dois compostos para as consultas das Partes 7 e 8 (painel, saúde da IA, linha do
tempo do talhão): ``ix_edge_record_tenant_kind_time`` e ``ix_mission_field_kind``.

Só índices: nenhuma linha muda. No Postgres com a aplicação no ar, numa tabela grande,
prefira criar à mão com ``CREATE INDEX CONCURRENTLY`` antes do deploy (mesmo nome) —
a migração usa ``if_not_exists`` e passa direto (ver ``docs/DEPLOY.md``). A volta apaga
os cinco.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0025"
down_revision: str | Sequence[str] | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INDICES = (
    ("ix_alert_created_at", "alert", ["created_at"]),
    ("ix_alert_rule_created_at", "alert_rule", ["created_at"]),
    ("ix_user_session_created_at", "user_session", ["created_at"]),
    ("ix_edge_record_tenant_kind_time", "edge_record", ["tenant_id", "kind", "occurred_at"]),
    ("ix_mission_field_kind", "mission", ["field_id", "kind"]),
)


def upgrade() -> None:
    for nome, tabela, colunas in INDICES:
        op.create_index(nome, tabela, colunas, if_not_exists=True)


def downgrade() -> None:
    for nome, tabela, _ in reversed(INDICES):
        op.drop_index(nome, table_name=tabela, if_exists=True)
