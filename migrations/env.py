"""Ambiente do Alembic: URL e metadados vêm da própria plataforma.

Chamado tanto pela linha de comando (``alembic upgrade head``) quanto pela
aplicação no start (:func:`valtexa.db.migrate`). No segundo caso a URL chega por
``config.attributes["url"]`` e o log não é reconfigurado — reconfigurar derrubaria
o logging que a aplicação já montou.
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlalchemy.engine import Connection

from valtexa.config import settings
from valtexa.models import Base

config = context.config

if config.config_file_name and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def _url() -> str:
    return config.attributes.get("url") or settings.database_url


def run_migrations_offline() -> None:
    """Gera SQL sem conectar — para revisar uma migração antes de aplicá-la."""
    context.configure(
        url=_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        render_as_batch=_url().startswith("sqlite"),
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        {"sqlalchemy.url": _url()}, prefix="sqlalchemy.", poolclass=pool.NullPool
    )
    with connectable.connect() as connection:
        _run(connection)
    connectable.dispose()


def _run(connection: Connection) -> None:
    sqlite = connection.dialect.name == "sqlite"
    if sqlite:
        # O SQLite só altera coluna recriando a tabela ("batch"). Com chave
        # estrangeira ligada, recriar uma tabela referenciada falharia — e a
        # aplicação liga a verificação em toda conexão (valtexa.db).
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
        # O PRAGMA abre uma transação implícita. Sem fechá-la aqui, a do
        # Alembic vira aninhada, não faz commit — e a migração inteira some no
        # rollback do fim da conexão, sem erro nenhum.
        connection.commit()
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        render_as_batch=sqlite,
    )
    with context.begin_transaction():
        context.run_migrations()
    if sqlite:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        connection.commit()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
