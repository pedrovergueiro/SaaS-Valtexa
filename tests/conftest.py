"""Ambiente dos testes.

Cada teste recebe um banco e um armazenamento próprios, em ``tmp_path``. Isolar
por teste custa alguns milissegundos e elimina a classe de falha em que um teste
passa sozinho e quebra na suíte.

As variáveis de ambiente são definidas **antes** de importar ``valtexa``: as
configurações são lidas uma vez por processo e ficam em cache.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest

_TEMP_ROOT = Path(tempfile.mkdtemp(prefix="valtexa-tests-"))
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_TEMP_ROOT / 'test.db'}")
os.environ.setdefault("STORAGE_DIR", str(_TEMP_ROOT / "storage"))
os.environ.setdefault("SIMULATED_INFERENCE", "true")
os.environ.setdefault("INFERENCE_ENABLED", "false")
os.environ.setdefault("LOG_LEVEL", "CRITICAL")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

from valtexa import db  # noqa: E402
from valtexa.db import get_session  # noqa: E402
from valtexa.main import app  # noqa: E402
from valtexa.models import (  # noqa: E402
    Base,
    Device,
    DeviceKind,
    DeviceModel,
    DeviceStatus,
    Farm,
    Field,
    Tenant,
)
from valtexa.seed import seed_demo, sync_device_models  # noqa: E402
from valtexa.services import storage  # noqa: E402
from valtexa.services.hal import REFERENCE_MODELS  # noqa: E402

DEMO_PASSWORD = "valtexa-demo-2026"


TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
"""Banco externo para a suíte, tipicamente um Postgres descartável.

Com ele definido, os mesmos testes rodam contra o banco de produção em vez do
SQLite. O esquema é apagado e recriado a cada teste: nunca aponte para um banco
com dado que importe.
"""


@pytest.fixture
def engine(tmp_path: Path):
    """Um banco por teste."""
    if TEST_DATABASE_URL:
        engine = create_engine(TEST_DATABASE_URL)
        Base.metadata.drop_all(engine)
    else:
        engine = create_engine(
            f"sqlite:///{tmp_path / 'test.db'}", connect_args={"check_same_thread": False}
        )
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def session_factory(engine) -> sessionmaker:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@pytest.fixture
def session(session_factory) -> Iterator[Session]:
    with session_factory() as session:
        yield session


@pytest.fixture
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> storage.LocalObjectStore:
    """Armazenamento isolado. Substitui a instância global do processo."""
    local = storage.LocalObjectStore(tmp_path / "storage")
    monkeypatch.setattr(storage, "store", local)
    return local


@pytest.fixture
def demo(session_factory, monkeypatch: pytest.MonkeyPatch, store) -> dict:
    """Fazenda de demonstração num banco limpo, com o catálogo de hardware."""
    _bind_sessions(monkeypatch, session_factory)
    with session_factory() as session:
        sync_device_models(session)
        data = seed_demo(session)
    return data


@pytest.fixture
def client(session_factory, demo, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """Cliente HTTP ligado ao banco do teste.

    O ``lifespan`` fica de fora — por isso o ``TestClient`` não é usado como
    gerenciador de contexto. Rodá-lo criaria o esquema no banco real do projeto e
    subiria a thread do *outbox*; aqui o esquema já existe, e os eventos são
    drenados explicitamente por quem precisa deles.
    """

    def _session_override() -> Iterator[Session]:
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = _session_override
    _bind_sessions(monkeypatch, session_factory)
    yield TestClient(app)
    app.dependency_overrides.clear()


def _bind_sessions(monkeypatch: pytest.MonkeyPatch, factory: sessionmaker) -> None:
    """Aponta para o banco do teste todas as sessões abertas fora do FastAPI.

    ``deps`` importa ``SessionLocal`` por nome, então trocar só ``db.SessionLocal``
    deixaria a checagem de nonce escrevendo no banco real do projeto — um teste
    contaminaria o ambiente de desenvolvimento.
    """
    from valtexa.api import deps

    monkeypatch.setattr(db, "SessionLocal", factory)
    monkeypatch.setattr(deps, "SessionLocal", factory)


@pytest.fixture
def admin_token(client: TestClient) -> dict[str, str]:
    return _login(client, "admin@valtexa.dev")


@pytest.fixture
def agronomist_token(client: TestClient) -> dict[str, str]:
    return _login(client, "agronomo@valtexa.dev")


@pytest.fixture
def operator_token(client: TestClient) -> dict[str, str]:
    return _login(client, "operador@valtexa.dev")


def _login(client: TestClient, email: str) -> dict[str, str]:
    response = client.post(
        "/v1/auth/login", json={"email": email, "password": DEMO_PASSWORD}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    return {"Authorization": f"Bearer {body['access_token']}", "X-Tenant-Id": body["tenant_id"]}


FROTA_CAMPO = [
    [-45.4530, -22.4120],
    [-45.4500, -22.4120],
    [-45.4500, -22.4140],
    [-45.4530, -22.4140],
]


@pytest.fixture
def frota(session: Session) -> dict:
    """Um tenant com rover e talhão, sem passar pela API."""
    tenant = Tenant(name="C", slug="c")
    session.add(tenant)
    session.flush()

    modelo = DeviceModel(**next(m for m in REFERENCE_MODELS if m["code"] == "ROVER_SCOUT_V1"))
    session.add(modelo)
    session.flush()

    farm = Farm(
        tenant_id=tenant.id, name="F", center_lat=-22.413, center_lon=-45.4515,
        base_lat=-22.4145, base_lon=-45.4515,
    )
    session.add(farm)
    session.flush()

    field_row = Field(
        tenant_id=tenant.id, farm_id=farm.id, name="T", crop="corn", boundary=FROTA_CAMPO
    )
    device = Device(
        tenant_id=tenant.id,
        serial_number="R-1",
        name="Rover",
        kind=DeviceKind.ROVER,
        device_model_id=modelo.id,
        farm_id=farm.id,
        status=DeviceStatus.ACTIVE,
        battery_percent=95.0,
    )
    session.add_all([field_row, device])
    session.commit()
    return {
        "session": session,
        "tenant": tenant,
        "farm": farm,
        "field": field_row,
        "device": device,
    }
