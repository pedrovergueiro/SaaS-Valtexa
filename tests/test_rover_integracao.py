"""Integração: o pacote ``rover/`` contra o SaaS de verdade (API, banco, object storage).

O Rover roda com a HAL **simulada** (câmera de pasta, GPS de trajetória, rede
que cai e volta) e a Edge AI de verdade sobre um modelo ONNX **minúsculo gerado
no teste** — não há pesos reais neste repositório. O que é real aqui: a missão
assinada pela plataforma e conferida pelo robô, o modelo designado pelo Model
Registry com o hash conferido, a perda de rede no meio da missão, a retomada e
a sincronização (registros, eventos, arquivos em chunks, telemetria) contra as
rotas do SaaS, com idempotência e retomada de upload no meio de um arquivo.

A rede simulada leva cada requisição assinada pelo robô ao ``TestClient`` da
API: o mesmo caminho de bytes que um HTTPS levaria.
"""

from __future__ import annotations

import io
import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tests.helpers import DeviceSession, provision, send_telemetry
from tests.test_end_to_end import ZONA
from valtexa.models import Asset, Device, EdgeRecord, EdgeUpload, TelemetrySample
from valtexa.security import signing
from valtexa.services import model_registry

rover = pytest.importorskip("valtexa_rover")
pytest.importorskip("onnx")

from valtexa_rover.clock import ManualClock  # noqa: E402
from valtexa_rover.config import RuntimeConfig, SyncConfig  # noqa: E402
from valtexa_rover.hal.interfaces import Hardware, HttpResponse  # noqa: E402
from valtexa_rover.hal.local import LocalDiskStorage, OnnxCpuAccelerator  # noqa: E402
from valtexa_rover.hal.simulated import (  # noqa: E402
    FlakyNetwork,
    FolderCamera,
    SimulatedImu,
    SimulatedSensors,
    TrajectoryGps,
)
from valtexa_rover.runtime.client import DeviceIdentity  # noqa: E402
from valtexa_rover.runtime.core import RoverCore  # noqa: E402
from valtexa_rover.runtime.model_manager import FolderArtifactSource  # noqa: E402

LABELS = ["Healthy", "Rust", "Leaf_Miner_Damage", "Unknown_Background"]
CORES = {"verde": (0, 255, 0), "vermelho": (255, 0, 0), "azul": (0, 0, 255)}


def modelo_minusculo(destino: Path) -> str:
    """Média RGB → 3x4 → softmax. Reconhece a cor dominante; serve para exercer o caminho."""
    import hashlib

    from onnx import TensorProto, helper

    k = 4.0
    pesos = np.array([[-k, k, -k, 0], [k, -k, -k, 0], [-k, -k, k, 0]], dtype=np.float32)
    grafo = helper.make_graph(
        [helper.make_node("ReduceMean", ["input"], ["m"], axes=[1, 2], keepdims=0),
         helper.make_node("MatMul", ["m", "W"], ["z"]),
         helper.make_node("Softmax", ["z"], ["probs"], axis=1)],
        "teste",
        [helper.make_tensor_value_info("input", TensorProto.FLOAT, ["b", 32, 32, 3])],
        [helper.make_tensor_value_info("probs", TensorProto.FLOAT, ["b", 4])],
        initializer=[helper.make_tensor("W", TensorProto.FLOAT, pesos.shape, pesos.flatten())],
    )
    modelo = helper.make_model(grafo, opset_imports=[helper.make_opsetid("", 17)])
    modelo.ir_version = 8
    bruto = modelo.SerializeToString()
    sha = hashlib.sha256(bruto).hexdigest()
    destino.mkdir(parents=True, exist_ok=True)
    (destino / f"{sha}.onnx").write_bytes(bruto)
    (destino / f"{sha}.labels.json").write_text(json.dumps(LABELS))
    return sha


def foto(cor: str, seed: int) -> bytes:
    rng = np.random.default_rng(seed)
    pixels = np.zeros((360, 480, 3), dtype=np.int16) + np.array(CORES[cor])
    pixels += rng.integers(-40, 41, pixels.shape)
    saida = io.BytesIO()
    Image.fromarray(np.clip(pixels, 0, 255).astype(np.uint8)).save(saida, "JPEG", quality=95)
    return saida.getvalue()


def ponte(client: TestClient):
    """A "rede" do robô: cada requisição assinada vai à API real."""

    def enviar(method: str, path: str, body: bytes, headers: dict) -> HttpResponse:
        resposta = client.request(method, path, content=body, headers=headers)
        return HttpResponse(resposta.status_code, resposta.content, dict(resposta.headers))

    return enviar


@pytest.fixture
def cenario(client: TestClient, admin_token, operator_token, demo, session: Session,
            tmp_path: Path):
    robo: DeviceSession = provision(client, admin_token, "ROVER_SCOUT_V1", "RT-0001",
                                    demo["farm_id"])
    send_telemetry(robo, battery_percent=95.0)

    # Model Registry: a versão em PRODUÇÃO que o talhão usa passa a ter o artefato
    # (o modelo minúsculo) com hash. O ciclo de aprovação tem testes próprios
    # (test_model_registry.py); aqui só se dá ao registry um artefato para designar.
    repo = tmp_path / "artefatos"
    sha = modelo_minusculo(repo)
    designados = robo.request("GET", "/v1/device/models").json()
    meu = next(d for d in designados if d["field_id"] == demo["field_id"])
    versao = model_registry.em_producao(session, meu["model_key"])
    versao.original_artifact_sha256 = sha
    versao.original_artifact_uri = f"s3://modelos/{sha}.onnx"
    session.commit()

    # Missão de verdade: criada, autorizada e despachada pela plataforma.
    criada = client.post("/v1/missions", json={
        "kind": "scout", "field_id": demo["field_id"], "zone_id": demo["zone_id"],
        "device_id": robo.device_id, "target_polygon": ZONA, "plan": {"swath_m": 40.0},
    }, headers=operator_token)
    assert criada.status_code == 201, criada.text
    mid = criada.json()["id"]
    assert client.post(f"/v1/missions/{mid}/authorize", headers=operator_token).json()[
        "verdict"] == "safe_to_execute"
    assert client.post(f"/v1/missions/{mid}/dispatch", headers=operator_token).status_code == 200

    # Rover: HAL simulada; 30 quadros com 3 eventos (doença, praga, doença).
    sequencia = ["verde"] * 30
    for i, cor in ((5, "vermelho"), (14, "azul"), (24, "vermelho")):
        sequencia[i] = cor
    imagens = tmp_path / "imagens"
    imagens.mkdir()
    for i, cor in enumerate(sequencia):
        (imagens / f"{i:04d}_{cor}.jpg").write_bytes(foto(cor, i))

    relogio = ManualClock(datetime.now(UTC))  # a assinatura confere o horário do servidor
    gps = TrajectoryGps([tuple(p) for p in ZONA], relogio, speed_ms=1.0)
    rede = FlakyNetwork(ponte(client))
    hardware = Hardware(
        cameras=[FolderCamera("cam-0", imagens, relogio, loop=False)],
        gps=gps, imu=SimulatedImu(relogio, gps), sensors=SimulatedSensors(relogio),
        storage=LocalDiskStorage(tmp_path / "rover"), network=rede,
        accelerator=OnnxCpuAccelerator(), hardware_version="Rover Edge V1 (sim)",
    )
    identidade = DeviceIdentity(robo.device_id, robo.key_id, robo.private_key,
                                signing.platform_public_key())
    config = RuntimeConfig(sync=SyncConfig(chunk_size=8192, backoff_base_s=0.5,
                                           backoff_max_s=2))

    def novo_core() -> RoverCore:
        core = RoverCore(hardware, tmp_path / "rover", identidade, config=config,
                         clock=relogio, artifact_source=FolderArtifactSource(repo),
                         telemetry_interval_s=5, sync_requests_per_step=30, seed=7)
        core.boot()
        return core

    return {"robo": robo, "mission_id": mid, "sha": sha, "rede": rede, "relogio": relogio,
            "novo_core": novo_core, "sequencia": sequencia, "model_key": meu["model_key"]}


def _contagem(session: Session, modelo, **filtro) -> int:
    session.expire_all()
    consulta = select(func.count()).select_from(modelo)
    for chave, valor in filtro.items():
        consulta = consulta.where(getattr(modelo, chave) == valor)
    return session.scalar(consulta)


def test_missao_perde_a_rede_continua_e_sincroniza(
    client: TestClient, cenario, session: Session, admin_token, demo
) -> None:
    core: RoverCore = cenario["novo_core"]()
    rede: FlakyNetwork = cenario["rede"]
    relogio: ManualClock = cenario["relogio"]

    # 1. Missão assinada pela plataforma, conferida pelo robô.
    assert core.accept_cloud_mission() == cenario["mission_id"]
    assert core.engine.package.sha256 == cenario["sha"]

    def andar(n: int) -> None:
        for _ in range(n):
            core.step()
            relogio.advance(1.0)

    # 2. Dez quadros com rede: sobe enquanto captura.
    andar(10)
    online_ate_aqui = _contagem(session, EdgeRecord, device_id=core.identity.device_id)
    assert online_ate_aqui > 0

    # 3. A rede cai. A missão continua: captura, Edge AI, resultados, posição, eventos.
    rede.set_online(False)
    andar(12)
    assert _contagem(session, EdgeRecord, device_id=core.identity.device_id) == online_ate_aqui
    assert core.missions.current().frames_done == 22
    pendentes_offline = core.sync.pending()
    assert pendentes_offline > 0

    # 4. O robô reinicia no meio da missão, ainda sem rede, e continua dela.
    core.close()
    core = cenario["novo_core"]()
    assert core.missions.current().frames_done == 22
    andar(8)
    core.complete_mission()

    # 5. A rede volta — e cai de novo no meio de um arquivo (drop_after), e volta.
    rede.set_online(True)
    rede.drop_after(25)
    core.sync.run_until_idle()
    assert not rede.is_online() and core.sync.pending() > 0
    parcial = session.scalars(
        select(EdgeUpload).where(EdgeUpload.status == "receiving")).all()
    rede.set_online(True)
    relatorio = core.sync.run_until_idle()
    assert core.sync.pending() == 0, core.sync.queue_status()
    assert relatorio.failed == 0, relatorio.errors

    # --- Conferências no SaaS ----------------------------------------------------
    registros_rover = core.store.query("SELECT id, kind, type FROM records")
    session.expire_all()
    no_saas = session.scalars(
        select(EdgeRecord).where(EdgeRecord.device_id == core.identity.device_id)).all()
    assert sorted(r.record_id for r in no_saas) == sorted(r["id"] for r in registros_rover)
    resultados = [r for r in no_saas if r.kind == "result"]
    assert len(resultados) == 30
    eventos = [r for r in no_saas if r.type == "IMAGE_EVENT_DETECTED"]
    assert len(eventos) == 3
    assert all(e.mission_id == cenario["mission_id"] for e in eventos)
    assert {r.type for r in resultados} == {"NORMAL", "POSSIVEL_DOENCA", "POSSIVEL_PRAGA"}
    um = next(r for r in resultados if r.type == "POSSIVEL_DOENCA")
    assert um.field_id == demo["field_id"] and um.lat is not None
    assert um.model_key == cenario["model_key"]
    assert um.payload["model"]["sha256"] == cenario["sha"]
    assert um.payload["hardware"]["simulated"] is True
    nomes = {r.type for r in no_saas if r.kind == "event"}
    assert {"MISSION_STARTED", "MISSION_RESUMED", "MISSION_COMPLETED", "MODEL_UPDATED",
            "ROVER_OFFLINE", "ROVER_ONLINE", "UPLOAD_STARTED",
            "UPLOAD_COMPLETED"} <= nomes

    # Arquivos: cada um que o robô guardou virou objeto, conferido pelo hash.
    arquivos_rover = core.store.query("SELECT sha256 FROM files")
    uploads = session.scalars(select(EdgeUpload).where(
        EdgeUpload.device_id == core.identity.device_id)).all()
    assert all(u.status == "complete" for u in uploads)
    assert {u.sha256 for u in uploads} == {a["sha256"] for a in arquivos_rover}
    for u in uploads:
        assert session.get(Asset, u.asset_id).sha256 == u.sha256
    originais = [u for u in uploads if u.role == "original"]
    assert len(originais) == 3 and all(u.total_chunks > 1 for u in originais)
    assert parcial, "a queda tinha de pegar um upload pela metade"

    # Telemetria e frota.
    assert _contagem(session, TelemetrySample, device_id=core.identity.device_id) >= 6
    dispositivo = session.get(Device, core.identity.device_id)
    assert dispositivo.ai_model_key == cenario["model_key"]
    assert dispositivo.runtime_version == rover.RUNTIME_VERSION
    assert dispositivo.sync_pending == 0 and dispositivo.last_sync_at is not None

    # O cliente vê o que o robô sincronizou, com os arquivos.
    lidos = client.get("/v1/edge/records", params={
        "mission_id": cenario["mission_id"], "type": "POSSIVEL_DOENCA"}, headers=admin_token)
    assert lidos.status_code == 200
    assert len(lidos.json()) == 2 and lidos.json()[0]["files"][0]["role"] == "original"

    # --- Reenvio de tudo: nada duplica -----------------------------------------
    antes = (_contagem(session, EdgeRecord), _contagem(session, EdgeUpload),
             _contagem(session, Asset))
    with core.store.transaction() as conn:
        conn.execute("UPDATE sync_queue SET status = 'PENDENTE', chunks_done = 0, "
                     "next_attempt_at = 0")
    core.sync.run_until_idle()
    assert core.sync.pending() == 0
    assert (_contagem(session, EdgeRecord), _contagem(session, EdgeUpload),
            _contagem(session, Asset)) == antes
