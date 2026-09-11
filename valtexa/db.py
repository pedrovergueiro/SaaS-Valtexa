"""Sessão e ciclo de vida do banco.

A plataforma usa SQLAlchemy 2.0 no modo síncrono. O FastAPI executa rotas
síncronas num *threadpool*, então o handler não bloqueia o *event loop* — e o
código do domínio fica sem ``async`` espalhado por toda parte, que é onde a
maioria dos erros de transação aparece.
"""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from valtexa.config import BASE_DIR, settings

logger = logging.getLogger(__name__)

BASELINE_REVISION = "0001"
"""A migração que descreve o esquema de antes do Alembic.

O banco do piloto foi criado por ``create_all``. Ao encontrar um banco assim —
tabelas sem ``alembic_version`` —, :func:`migrate` o marca nesta revisão e
aplica o resto por cima, em vez de tentar recriar o que já existe.
"""


def _build_engine(url: str) -> Engine:
    """Cria o engine com os ajustes que cada banco exige."""
    if url.startswith("sqlite"):
        # ``check_same_thread`` é obrigatório porque o FastAPI atende cada rota
        # síncrona numa thread diferente do pool.
        return create_engine(url, connect_args={"check_same_thread": False}, future=True)
    return create_engine(url, pool_pre_ping=True, future=True)


engine = _build_engine(settings.database_url)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


@event.listens_for(Engine, "connect")
def _sqlite_pragmas(dbapi_connection: object, _record: object) -> None:
    """Liga integridade referencial e WAL no SQLite.

    O SQLite ignora ``FOREIGN KEY`` por padrão — sem este ``PRAGMA`` o banco
    aceitaria uma missão apontando para um dispositivo que não existe. O WAL
    permite leitura concorrente durante a escrita da telemetria.
    """
    # Decide pela conexão, não pela configuração: os testes contra Postgres
    # rodam com DATABASE_URL de SQLite, e um PRAGMA enviado ao Postgres é erro.
    if not isinstance(dbapi_connection, sqlite3.Connection):
        return
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()


def get_session() -> Iterator[Session]:
    """Dependência do FastAPI: uma sessão por requisição, sempre fechada."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    """Transação para uso fora do FastAPI (simulador, scripts, workers)."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def create_all() -> None:
    """Cria o esquema direto dos modelos, sem migração.

    Só para os testes, que recriam o banco a cada caso. A aplicação usa
    :func:`migrate`: um esquema criado por ``create_all`` não tem como evoluir
    sem perder dado.
    """
    from valtexa.models import Base  # importado aqui para evitar ciclo de import

    Base.metadata.create_all(bind=engine)


def alembic_config(url: str | None = None):
    """Configuração do Alembic apontando para ``url`` (padrão: ``DATABASE_URL``)."""
    from alembic.config import Config

    config = Config(str(BASE_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BASE_DIR / "migrations"))
    config.attributes["url"] = url or settings.database_url
    config.attributes["configure_logger"] = False
    return config


def head_revision() -> str:
    from alembic.script import ScriptDirectory

    return ScriptDirectory.from_config(alembic_config()).get_current_head()


def migrate(url: str | None = None) -> str:
    """Leva o banco à última migração. Devolve ``"adopted"`` ou ``"upgraded"``.

    Roda no start da aplicação. É idempotente: num banco já atualizado, não faz
    nada.
    """
    from alembic import command
    from sqlalchemy import inspect

    target = url or settings.database_url
    probe = _build_engine(target)
    try:
        tables = set(inspect(probe).get_table_names())
    finally:
        probe.dispose()

    config = alembic_config(target)
    action = "upgraded"
    if "tenant" in tables and "alembic_version" not in tables:
        logger.warning(
            "Banco criado antes das migrações: marcando a revisão %s e aplicando o resto.",
            BASELINE_REVISION,
        )
        command.stamp(config, BASELINE_REVISION)
        action = "adopted"
    command.upgrade(config, "head")
    return action
