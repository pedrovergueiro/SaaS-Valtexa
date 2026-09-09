"""Sessão e ciclo de vida do banco.

A plataforma usa SQLAlchemy 2.0 no modo síncrono. O FastAPI executa rotas
síncronas num *threadpool*, então o handler não bloqueia o *event loop* — e o
código do domínio fica sem ``async`` espalhado por toda parte, que é onde a
maioria dos erros de transação aparece.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from valtexa.config import settings


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
    if not settings.database_url.startswith("sqlite"):
        return
    cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
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
    """Cria o esquema.

    Suficiente para o piloto. Quando houver dado em produção, o caminho é Alembic:
    ver ``docs/DEPLOYMENT.md``.
    """
    from valtexa.models import Base  # importado aqui para evitar ciclo de import

    Base.metadata.create_all(bind=engine)
