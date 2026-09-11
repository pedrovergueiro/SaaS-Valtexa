"""Migrações: o esquema que o Alembic produz é o esquema dos modelos.

Roda contra SQLite por padrão e contra o banco de ``TEST_DATABASE_URL`` quando
ele estiver definido — é a checagem que garante que as migrações funcionam no
Postgres de produção, não só no arquivo local.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from alembic import command
from sqlalchemy import create_engine, inspect, text

from valtexa import db
from valtexa.models import Base


@pytest.fixture
def url(tmp_path: Path) -> str:
    target = os.environ.get("TEST_DATABASE_URL") or f"sqlite:///{tmp_path / 'migracao.db'}"
    engine = create_engine(target)
    Base.metadata.drop_all(engine)
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE IF EXISTS alembic_version"))
    engine.dispose()
    return target


def _schema(url: str) -> dict[str, set[str]]:
    engine = create_engine(url)
    inspector = inspect(engine)
    tables = {
        name: {column["name"] for column in inspector.get_columns(name)}
        for name in inspector.get_table_names()
        if name != "alembic_version"
    }
    engine.dispose()
    return tables


def _revision(url: str) -> str | None:
    engine = create_engine(url)
    with engine.connect() as connection:
        row = connection.execute(text("SELECT version_num FROM alembic_version")).first()
    engine.dispose()
    return row[0] if row else None


def test_migracoes_reproduzem_os_modelos(url: str) -> None:
    command.upgrade(db.alembic_config(url), "head")
    expected = {
        table.name: {column.name for column in table.columns}
        for table in Base.metadata.sorted_tables
    }
    assert _schema(url) == expected


def test_ida_e_volta(url: str) -> None:
    config = db.alembic_config(url)
    command.upgrade(config, "head")
    command.downgrade(config, db.BASELINE_REVISION)

    schema = _schema(url)
    assert "telemetry_rollup" not in schema
    assert "row_azimuth_deg" not in schema["field"]

    command.upgrade(config, "head")
    assert "telemetry_rollup" in _schema(url)


def test_banco_criado_antes_das_migracoes_e_adotado(url: str) -> None:
    """O banco do piloto nasceu com create_all; ele precisa entrar no trilho."""
    command.upgrade(db.alembic_config(url), db.BASELINE_REVISION)
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE alembic_version"))
    engine.dispose()

    assert db.migrate(url) == "adopted"
    assert "row_azimuth_deg" in _schema(url)["field"]
    assert _revision(url) == db.head_revision()


def test_banco_novo_e_migrado_do_zero(url: str) -> None:
    assert db.migrate(url) == "upgraded"
    assert _revision(url) == db.head_revision()
