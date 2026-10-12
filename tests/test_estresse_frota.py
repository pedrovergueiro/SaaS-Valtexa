"""Estresse da plataforma (seção 42): vários Rovers de dois clientes, ao mesmo tempo.

Seis ``rover/`` de verdade (HAL simulada), três por cliente, cada um numa thread,
rodando missão com a rede caindo em janelas diferentes e sincronizando contra a
API real **em paralelo** (uploads simultâneos, lotes de registros concorrentes).
SQLite trava escrita concorrente; o que der ``database is locked`` volta como
erro de servidor e o Rover tenta de novo com *backoff* — é parte do teste: nada
pode se perder nem duplicar, e nenhum cliente pode ver o do outro.
"""

from __future__ import annotations

import threading
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tests.helpers import provision
from valtexa.models import EdgeRecord, EdgeUpload, Membership, Role, Tenant, User
from valtexa.security import signing
from valtexa.security.passwords import hash_password
from valtexa.services import model_registry

pytest.importorskip("valtexa_rover")

from valtexa_rover.clock import ManualClock
from valtexa_rover.runtime.client import DeviceIdentity
from valtexa_rover.sim import (
    MODELO_DEMO_SHA256,
    CampoSimulado,
    PlanoDeRede,
    RoverSimulado,
)

from tests.test_rover_integracao import ponte

SENHA = "valtexa-demo-2026"
ROVERS_POR_CLIENTE = 3
PASSOS = 60


def _cliente(client: TestClient, session_factory, nome: str) -> dict:
    with session_factory() as s:
        t = Tenant(name=nome, slug=nome.lower().replace(" ", "-"))
        u = User(email=f"dono@{t.slug}.dev", full_name="Dono", password_hash=hash_password(SENHA))
        s.add_all([t, u])
        s.flush()
        s.add(Membership(tenant_id=t.id, user_id=u.id, role=Role.OWNER))
        s.commit()
    corpo = client.post("/v1/auth/login", json={"email": f"dono@{t.slug}.dev",
                                                "password": SENHA}).json()
    return {"Authorization": f"Bearer {corpo['access_token']}", "X-Tenant-Id": corpo["tenant_id"]}


def _talhao(client: TestClient, headers: dict, campo: CampoSimulado) -> tuple[str, str]:
    lats = [p.lat for p in campo.plantas]
    lons = [p.lon for p in campo.plantas]
    m = 0.0001
    contorno = [[min(lons) - m, min(lats) - m], [max(lons) + m, min(lats) - m],
                [max(lons) + m, max(lats) + m], [min(lons) - m, max(lats) + m],
                [min(lons) - m, min(lats) - m]]
    fazenda = client.post("/v1/farms", headers=headers, json={
        "name": "Fazenda", "center_lat": lats[0], "center_lon": lons[0]})
    assert fazenda.status_code == 201, fazenda.text
    talhao = client.post(f"/v1/farms/{fazenda.json()['id']}/fields", headers=headers, json={
        "name": "Talhão", "crop": "coffee", "boundary": contorno})
    assert talhao.status_code == 201, talhao.text
    return fazenda.json()["id"], talhao.json()["id"]


def test_seis_rovers_dois_clientes_em_paralelo(
    client: TestClient, session_factory, session: Session, demo, tmp_path: Path
) -> None:
    versao = model_registry.em_producao(session, "coffee-foliar")
    versao.original_artifact_sha256 = MODELO_DEMO_SHA256  # o modelo de demonstração
    versao.original_artifact_uri = "pacote://valtexa_rover/sim/modelo_demo.onnx"
    session.commit()

    rovers: list[tuple[str, RoverSimulado, str]] = []
    clientes = {}
    for c, nome in enumerate(("Cliente Norte", "Cliente Sul")):
        headers = _cliente(client, session_factory, nome)
        campo = CampoSimulado.gerar(-47.06 + c * 0.01, -22.9, linhas=2, plantas_por_linha=40,
                                    doentes={"L1-P010": "doenca", "L2-P030": "praga"})
        farm_id, field_id = _talhao(client, headers, campo)
        clientes[nome] = {"headers": headers, "rovers": []}
        for r in range(ROVERS_POR_CLIENTE):
            robo = provision(client, headers, "ROVER_SCOUT_V1", f"EST-{c}-{r}", farm_id)
            ident = DeviceIdentity(robo.device_id, robo.key_id, robo.private_key,
                                   signing.platform_public_key())
            sim = RoverSimulado(tmp_path / f"r{c}{r}", ident, ponte(client), campo,
                                clock=ManualClock(datetime.now(UTC)), cameras=2, seed=c * 10 + r,
                                sync_requests_per_step=6)
            sim.core.start_mission(f"local-{c}-{r}", field_id)
            rovers.append((nome, sim, robo.device_id))
            clientes[nome]["rovers"].append(robo.device_id)

    erros: list[BaseException] = []

    def missao(i: int, sim: RoverSimulado) -> None:
        try:
            # Cada robô perde a rede numa janela diferente.
            sim.rodar(PASSOS, PlanoDeRede(sem_rede=[(10 + 5 * i, 30 + 5 * i)]))
            sim.core.complete_mission()
            sim.sincronizar(max_passos=3000)
        except BaseException as exc:  # pragma: no cover - aparece no assert abaixo
            erros.append(exc)

    inicio = time.perf_counter()
    threads = [threading.Thread(target=missao, args=(i, sim)) for i, (_n, sim, _d) in
               enumerate(rovers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=600)
    duracao = time.perf_counter() - inicio
    assert not erros, erros
    # Algum robô pode ter terminado com itens adiados por backoff: termina em série.
    for _nome, sim, _d in rovers:
        assert sim.sincronizar(max_passos=3000) == 0

    session.expire_all()
    for _nome, sim, device_id in rovers:
        locais = sim.core.store.scalar("SELECT COUNT(*) FROM records")
        na_nuvem = session.scalar(select(func.count()).select_from(EdgeRecord)
                                  .where(EdgeRecord.device_id == device_id))
        assert na_nuvem == locais, "registro perdido ou duplicado"
        arquivos = sim.core.store.scalar("SELECT COUNT(*) FROM files")
        completos = session.scalar(select(func.count()).select_from(EdgeUpload).where(
            EdgeUpload.device_id == device_id, EdgeUpload.status == "complete"))
        assert completos == arquivos

    # Isolamento: cada cliente vê só os registros dos próprios robôs.
    for nome, dados in clientes.items():
        vistos = client.get("/v1/edge/records", headers=dados["headers"],
                            params={"limit": 1000}).json()
        assert vistos and {r["device_id"] for r in vistos} <= set(dados["rovers"]), nome

    total = session.scalar(select(func.count()).select_from(EdgeRecord))
    print(f"\n6 rovers x {PASSOS} passos x 2 câmeras: {total} registros, "
          f"{session.scalar(select(func.count()).select_from(EdgeUpload))} arquivos, "
          f"{duracao:.1f} s")
