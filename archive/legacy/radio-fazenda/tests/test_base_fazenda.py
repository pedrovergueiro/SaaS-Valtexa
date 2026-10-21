"""Ponta a ponta da fazenda: o Runtime do Rover ⇄ rádio (EMULADO) ⇄ base ⇄ plataforma.

Tudo de verdade menos o rádio e o hardware do robô: a plataforma roda no **uvicorn** (HTTP
real, mesmo banco do teste), a base é o ``valtexa_base`` com UDP e a mesma fila SQLite de
produção, o Rover é o ``RoverCore`` com a HAL simulada e a rede ``RedeViaBase`` (protocolo
de enlace sobre dois relés UDP com perda). No meio da missão a **Starlink cai** (a base
fica sem nuvem) e depois **os dois rádios caem** (o Rover fica sem base); tudo volta
sozinho e a plataforma termina com cada registro e cada arquivo uma vez só.
"""

from __future__ import annotations

import socket
import threading
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from tests.helpers import DeviceSession, provision, send_telemetry
from tests.test_end_to_end import ZONA
from tests.test_rover_integracao import _contagem, foto, modelo_minusculo
from valtexa.models import EdgeRecord, EdgeUpload
from valtexa.security import signing
from valtexa.services import model_registry

pytest.importorskip("valtexa_rover")
pytest.importorskip("valtexa_base")
pytest.importorskip("onnx")

from valtexa_base.servico import BaseDaFazenda, ConfigDaBase
from valtexa_rover.clock import ManualClock
from valtexa_rover.config import RuntimeConfig, SyncConfig
from valtexa_rover.enlace.cripto import ChaveDeEnlace
from valtexa_rover.enlace.emulador import ModeloDeCanal, ReleUdp
from valtexa_rover.hal.interfaces import Hardware
from valtexa_rover.hal.local import LocalDiskStorage, OnnxCpuAccelerator
from valtexa_rover.hal.rede_base import ServicoDeEnlace
from valtexa_rover.hal.simulated import (
    FolderCamera,
    SimulatedImu,
    SimulatedSensors,
    TrajectoryGps,
)
from valtexa_rover.runtime.client import DeviceIdentity
from valtexa_rover.runtime.core import RoverCore
from valtexa_rover.runtime.model_manager import FolderArtifactSource


def _porta(tipo=socket.SOCK_DGRAM) -> int:
    with socket.socket(socket.AF_INET, tipo) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Starlink:
    def __init__(self) -> None:
        self.ok = True

    def __call__(self, pedido, timeout=None):
        if not self.ok:
            raise urllib.error.URLError("Network is unreachable (Starlink caída — teste)")
        return urllib.request.urlopen(pedido, timeout=timeout)


@pytest.fixture
def plataforma():
    """A API de verdade no uvicorn (o mesmo ``app`` e o mesmo banco do ``client``)."""
    import uvicorn

    from valtexa.main import app

    porta = _porta(socket.SOCK_STREAM)
    servidor = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=porta,
                                             log_level="warning"))
    t = threading.Thread(target=servidor.run, daemon=True)
    t.start()
    url = f"http://127.0.0.1:{porta}"
    fim = time.monotonic() + 30
    while time.monotonic() < fim:
        try:
            if urllib.request.urlopen(url + "/health", timeout=2).status == 200:
                break
        except OSError:
            time.sleep(0.1)
    yield url
    servidor.should_exit = True
    t.join(timeout=10)


def test_missao_inteira_pela_base_com_starlink_e_radio_caindo(
    client: TestClient, admin_token, operator_token, demo, session: Session, tmp_path: Path,
    plataforma: str, platform_token,
) -> None:
    # --- plataforma: robô, modelo designado e missão assinada ------------------------
    robo: DeviceSession = provision(client, admin_token, "ROVER_SCOUT_V1", "RT-0001",
                                    demo["farm_id"])
    send_telemetry(robo, battery_percent=95.0)
    repo = tmp_path / "artefatos"
    sha = modelo_minusculo(repo)
    meu = next(d for d in robo.request("GET", "/v1/device/models").json()
               if d["field_id"] == demo["field_id"])
    versao = model_registry.em_producao(session, meu["model_key"])
    versao.original_artifact_sha256 = sha
    versao.original_artifact_uri = f"s3://modelos/{sha}.onnx"
    session.commit()
    criada = client.post("/v1/missions", json={
        "kind": "scout", "field_id": demo["field_id"], "zone_id": demo["zone_id"],
        "device_id": robo.device_id, "target_polygon": ZONA, "plan": {"swath_m": 40.0},
    }, headers=operator_token)
    mid = criada.json()["id"]
    client.post(f"/v1/missions/{mid}/authorize", headers=operator_token)
    assert client.post(f"/v1/missions/{mid}/dispatch", headers=operator_token).status_code == 200

    # --- a fazenda: base + 2 rádios emulados (15 % de perda) --------------------------
    # A base também é dispositivo da plataforma (FARM_BASE_V1), com a identidade dela.
    base_ds = provision(client, admin_token, "FARM_BASE_V1", "BASE-T", demo["farm_id"])
    identidade_base = tmp_path / "base-identity.json"
    DeviceIdentity(base_ds.device_id, base_ds.key_id, base_ds.private_key,
                   signing.platform_public_key()).save(identidade_base)
    starlink = Starlink()
    k_base = ChaveDeEnlace.carregar_ou_criar(tmp_path / "base" / "enlace.key")
    portas = [_porta(), _porta()]
    reles = [ReleUdp(("127.0.0.1", 0), ("127.0.0.1", p),
                     ModeloDeCanal(banda_bps=b, atraso_s=a, perda=0.15), semente=i).iniciar()
             for i, (p, b, a) in enumerate(zip(portas, (250_000, 20e6), (0.04, 0.005),
                                               strict=True))]
    servico = ServicoDeEnlace(
        {"modo": "base", "nome": "RT-0001", "base_pub": k_base.publica.hex(),
         "chave": str(tmp_path / "rover-enlace.key"), "fila": str(tmp_path / "rover-enlace.db"),
         "estado": str(tmp_path / "run" / "enlace.json"), "sincrono": "NORMAL",
         "enlaces": [{"nome": n, "bind": f"127.0.0.1:{_porta()}",
                      "destino": f"{r.endereco[0]}:{r.endereco[1]}", "banda_bps": b}
                     for n, r, b in zip(("subghz", "alta"), reles, (250_000, 20e6),
                                        strict=True)]},
        tmp_path)
    base = BaseDaFazenda(ConfigDaBase(
        nome="base-teste", url_nuvem=plataforma, dados=tmp_path / "base",
        enlaces=[{"nome": n, "bind": f"127.0.0.1:{p}", "banda_bps": b}
                 for n, p, b in zip(("subghz", "alta"), portas, (250_000, 20e6), strict=True)],
        pares={"RT-0001": servico.no.chave.publica}, sincrono="NORMAL", sonda_s=0.5,
        plataforma={"identidade": str(identidade_base), "intervalo_s": 1}),
        abrir=starlink).iniciar()
    servico.iniciar()

    # --- o Rover: HAL simulada, Edge AI de verdade, rede "via base" -----------------
    sequencia = ["verde"] * 30
    for i, cor in ((5, "vermelho"), (14, "azul"), (24, "vermelho")):
        sequencia[i] = cor
    imagens = tmp_path / "imagens"
    imagens.mkdir()
    for i, cor in enumerate(sequencia):
        (imagens / f"{i:04d}_{cor}.jpg").write_bytes(foto(cor, i))
    relogio = ManualClock(datetime.now(UTC))
    gps = TrajectoryGps([tuple(p) for p in ZONA], relogio, speed_ms=1.0)
    hardware = Hardware(
        cameras=[FolderCamera("cam-0", imagens, relogio, loop=False)],
        gps=gps, imu=SimulatedImu(relogio, gps), sensors=SimulatedSensors(relogio),
        storage=LocalDiskStorage(tmp_path / "rover"), network=servico.rede,
        accelerator=OnnxCpuAccelerator(), hardware_version="Rover Edge V1 (sim)")
    core = RoverCore(hardware, tmp_path / "rover",
                     DeviceIdentity(robo.device_id, robo.key_id, robo.private_key,
                                    signing.platform_public_key()),
                     config=RuntimeConfig(sync=SyncConfig(chunk_size=8192, backoff_base_s=0.5,
                                                          backoff_max_s=2)),
                     clock=relogio, artifact_source=FolderArtifactSource(repo),
                     telemetry_interval_s=5, sync_requests_per_step=30, seed=7)
    try:
        fim = time.monotonic() + 15
        while not servico.rede.is_online() and time.monotonic() < fim:
            time.sleep(0.05)
        core.boot()
        assert core.accept_cloud_mission() == mid  # assinada pela plataforma, via base
        assert base.missoes.lista()[0]["mission_id"] == mid  # e guardada no cache da base

        def andar(n: int) -> None:
            for _ in range(n):
                core.step()
                relogio.advance(1.0)

        andar(10)
        online = _contagem(session, EdgeRecord, device_id=robo.device_id)
        assert online > 0

        # O retrato assinado da base chega à plataforma: o centro de comando mostra o
        # caminho nuvem → base → rádios → Rover.
        def caminho() -> dict:
            return client.get(f"/v1/platform/rovers/{robo.device_id}/painel",
                              headers=platform_token).json()["caminho"]

        fim = time.monotonic() + 15
        while caminho()["modo"] != "base" and time.monotonic() < fim:
            time.sleep(0.2)
        via = caminho()
        assert via["modo"] == "base" and via["base"]["serial_number"] == "BASE-T"
        assert via["nuvem_base"]["ok"] and via["base_rover"]["vivo"]
        assert {e["nome"] for e in via["base_rover"]["enlaces"]} == {"subghz", "alta"}

        # Vídeo ao vivo pela base: a estação liga, o robô fica sabendo pela consulta de
        # comandos e manda o quadro pelo slot "só o último vale" do rádio (P3, abaixo de
        # comando). Em missão, o quadro é o que o Runtime já capturou — a câmera não é
        # chamada de novo.
        from valtexa_rover.runtime.client import DeviceClient
        from valtexa_rover.runtime.comandos import CommandExecutor
        from valtexa_rover.runtime.video import TransmissorDeVideo

        assert client.post(f"/v1/platform/rovers/{robo.device_id}/video",
                           headers=platform_token,
                           json={"cameras": ["cam-0"], "fps": 4, "lado": 480}
                           ).status_code == 200
        video = TransmissorDeVideo(
            hardware, DeviceClient(core.identity, servico.rede, relogio), relogio,
            missao_em_curso=lambda: True, quadro_recente=core.ultimos_quadros.get,
            dormir=lambda _s: None)
        comandos = CommandExecutor(core)
        comandos.video = video
        comandos.poll()  # o pedido chega no cabeçalho da consulta de comandos, via base
        assert video.pedido() is not None
        fim = time.monotonic() + 15
        while video.enviados == 0 and time.monotonic() < fim:
            video.passo()
        assert video.enviados >= 1, video.estado()
        quadro = client.get(f"/v1/platform/rovers/{robo.device_id}/video/cam-0",
                            headers=platform_token)
        assert quadro.status_code == 200 and quadro.content.startswith(bytes([0xFF, 0xD8]))

        # A Starlink cai: o rádio continua, a base aceita e responde "sem internet".
        starlink.ok = False
        andar(8)
        assert _contagem(session, EdgeRecord, device_id=robo.device_id) == online
        assert servico.no.vivo("base")  # o rádio continua; a sincronização para
        assert not servico.rede.is_online()
        assert base.contagem["sem_internet"] > 0

        # Os dois rádios caem (morro e copa): o Rover segue a missão sem a base.
        for r in reles:
            r.ida.modelo.quedas.append((r._agora(), r._agora() + 8))
            r.volta.modelo.quedas.append((r._agora(), r._agora() + 8))
        time.sleep(4)
        assert not servico.no.vivo("base")
        andar(6)
        assert core.missions.current().frames_done == 24
        starlink.ok = True
        time.sleep(5)  # os rádios voltam sozinhos
        andar(6)
        core.complete_mission()

        fim = time.monotonic() + 180
        while core.sync.pending() and time.monotonic() < fim:
            core.sync.step()
            time.sleep(0.05)
        assert core.sync.pending() == 0, core.sync.queue_status()
        core.flush_mission_reports()
        registros_rover = core.store.query("SELECT id FROM records")
        arquivos = core.store.query("SELECT sha256 FROM files")
    finally:
        core.close()
        servico.parar()
        base.parar()
        for r in reles:
            r.parar()

    # --- conferências na plataforma ---------------------------------------------------
    session.expire_all()
    no_saas = session.scalars(select(EdgeRecord).where(
        EdgeRecord.device_id == robo.device_id)).all()
    assert sorted(r.record_id for r in no_saas) == sorted(r["id"] for r in registros_rover)
    assert len([r for r in no_saas if r.kind == "result"]) == 30
    assert len([r for r in no_saas if r.type == "IMAGE_EVENT_DETECTED"]) == 3
    nomes = {r.type for r in no_saas if r.kind == "event"}
    # uma queda = um ROVER_OFFLINE (não um par ONLINE/OFFLINE a cada passo do sync)
    assert len([r for r in no_saas if r.type == "ROVER_OFFLINE"]) <= 3
    assert {"MISSION_STARTED", "MISSION_COMPLETED", "ROVER_OFFLINE", "ROVER_ONLINE"} <= nomes
    uploads = session.scalars(select(EdgeUpload).where(
        EdgeUpload.device_id == robo.device_id)).all()
    assert uploads and all(u.status == "complete" for u in uploads)
    assert {u.sha256 for u in uploads} == {a["sha256"] for a in arquivos}
    originais = [u for u in uploads if u.role == "original"]
    assert len(originais) == 3 and all(u.total_chunks > 1 for u in originais)
    # cada "aceito" que fez o Rover apagar dado veio com o recibo assinado da plataforma
    assert servico.rede.recibos_conferidos > 50 and servico.rede.recibos_recusados == 0
    print(f"\nbase: {base.contagem} | custódia: guardadas {base.custodia.guardadas}, "
          f"entregues {base.custodia.entregues}, expiradas {base.custodia.expiradas} | "
          f"enlace do Rover: {servico.no.estat}")
