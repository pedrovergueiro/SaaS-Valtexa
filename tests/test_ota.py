"""OTA (seção 24): publicação, alvo, acompanhamento — e o ``rover/`` de verdade atualizando.

A parte de integração usa o OTA Manager do pacote ``rover/`` contra a API real:
assinatura conferida com a chave OTA que o provisionamento entrega, download em
pedaços com queda de rede no meio, pacote adulterado no armazenamento,
configuração e runtime com volta automática.
"""

from __future__ import annotations

import hashlib
import io
import json
import tarfile
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from tests.helpers import DeviceSession, provision
from valtexa.models import AuditEntry, OtaDeployment, OtaPackage, PlatformRole
from valtexa.security import signing
from valtexa.services import model_registry, storage


def tar_de(arquivos: dict[str, bytes]) -> bytes:
    saida = io.BytesIO()
    with tarfile.open(fileobj=saida, mode="w") as tar:
        for nome, dados in arquivos.items():
            info = tarfile.TarInfo(nome)
            info.size = len(dados)
            tar.addfile(info, io.BytesIO(dados))
    return saida.getvalue()


def publicar(client: TestClient, headers: dict, kind: str, version: str, dados: bytes,
             model_version_id: str | None = None):
    params = {"kind": kind, "version": version}
    if model_version_id:
        params["model_version_id"] = model_version_id
    return client.post("/v1/platform/ota/packages", params=params, content=dados,
                       headers={**headers, "Content-Type": "application/x-tar"})


@pytest.fixture
def ops(equipe) -> dict:
    return equipe(PlatformRole.OPERACOES)


@pytest.fixture
def robo(client: TestClient, admin_token, demo) -> DeviceSession:
    return provision(client, admin_token, "ROVER_SCOUT_V1", "OTA-0001", demo["farm_id"])


@pytest.fixture
def modelo_em_producao(client: TestClient, robo: DeviceSession, demo, session: Session):
    """A versão em PRODUÇÃO do talhão ganha um artefato (bytes de teste) com hash."""
    designado = next(d for d in robo.request("GET", "/v1/device/models").json()
                     if d["field_id"] == demo["field_id"])
    versao = model_registry.em_producao(session, designado["model_key"])
    bruto = b"onnx-de-teste" * 100
    sha = hashlib.sha256(bruto).hexdigest()
    versao.original_artifact_sha256 = sha
    versao.original_artifact_uri = f"s3://modelos/{sha}.onnx"
    session.commit()
    return {"id": versao.id, "sha": sha, "bytes": bruto}


class TestPublicacao:
    def test_modelo_so_em_producao_e_com_o_hash_do_registry(
        self, client, ops, modelo_em_producao, session: Session
    ) -> None:
        sha, bruto = modelo_em_producao["sha"], modelo_em_producao["bytes"]
        errado = publicar(client, ops, "model", "m-1", tar_de({f"{sha}.onnx": bruto + b"x"}),
                          modelo_em_producao["id"])
        assert errado.status_code == 409 and "hash do registry" in errado.json()["detail"]
        sem_versao = publicar(client, ops, "model", "m-1", tar_de({f"{sha}.onnx": bruto}))
        assert sem_versao.status_code == 422
        ok = publicar(client, ops, "model", "m-1", tar_de({f"{sha}.onnx": bruto}),
                      modelo_em_producao["id"])
        assert ok.status_code == 201, ok.text
        corpo = ok.json()
        assert corpo["manifest"]["model"]["artifact_sha256"] == sha
        assert corpo["manifest"]["files"][0]["sha256"] == sha
        assert publicar(client, ops, "model", "m-1", tar_de({f"{sha}.onnx": bruto}),
                        modelo_em_producao["id"]).status_code == 409  # não se reescreve

        # Fora de PRODUÇÃO: recusado.
        from valtexa.models import ModelVersion, ModelVersionState
        versao = session.get(ModelVersion, modelo_em_producao["id"])
        versao.state = ModelVersionState.STAGING
        session.commit()
        r = publicar(client, ops, "model", "m-2", tar_de({f"{sha}.onnx": bruto}),
                     modelo_em_producao["id"])
        assert r.status_code == 409 and "PRODUÇÃO" in r.json()["detail"]

    @pytest.mark.parametrize("nome", ["../fora.txt", "/etc/passwd", "a/../../b"])
    def test_caminho_inseguro_e_recusado(self, client, ops, nome) -> None:
        r = publicar(client, ops, "config", "c-x", tar_de({nome: b"{}"}))
        assert r.status_code == 422

    def test_lixo_e_papeis(self, client, ops, equipe) -> None:
        assert publicar(client, ops, "config", "c-1", b"nao e tar").status_code == 422
        assert publicar(client, ops, "firmware", "f-1", tar_de({"a": b"1"})).status_code == 422
        comercial = equipe(PlatformRole.COMERCIAL)
        assert publicar(client, comercial, "config", "c-1",
                        tar_de({"rover.json": b"{}"})).status_code == 403
        suporte = equipe(PlatformRole.SUPORTE)  # vê a frota, não publica
        assert publicar(client, suporte, "config", "c-1",
                        tar_de({"rover.json": b"{}"})).status_code == 403
        assert client.get("/v1/platform/ota/deployments", headers=suporte).status_code == 200


class TestDestinoEAcompanhamento:
    def test_destino_assinado_estados_e_isolamento(
        self, client, ops, robo: DeviceSession, admin_token, demo, session: Session
    ) -> None:
        pacote = publicar(client, ops, "config", "c-1",
                          tar_de({"rover.json": b'{"sync": {"chunk_size": 4096}}'})).json()
        criados = client.post("/v1/platform/ota/deployments",
                              json={"package_id": pacote["id"], "tenant_id": demo["tenant_id"]},
                              headers=ops)
        assert criados.status_code == 201, criados.text
        meus = [d for d in criados.json() if d["device_id"] == robo.device_id]
        assert len(meus) == 1 and meus[0]["state"] == "pendente"
        dep = meus[0]["id"]
        # De novo: não duplica destino aberto.
        de_novo = client.post("/v1/platform/ota/deployments",
                              json={"package_id": pacote["id"], "device_ids": [robo.device_id]},
                              headers=ops)
        assert de_novo.json() == []

        itens = robo.request("GET", "/v1/device/ota").json()
        item = next(i for i in itens if i["deployment_id"] == dep)
        envelope = item["envelope"]
        signing.verify_ota(envelope["payload"], envelope["signature"])
        assert envelope["payload"]["device_id"] == robo.device_id
        assert envelope["payload"]["manifest"]["sha256"] == pacote["sha256"]
        with pytest.raises(signing.SignatureError):  # a chave das missões não serve
            signing.verify_command(envelope["payload"], envelope["signature"])

        parte = robo.request("GET", f"/v1/device/ota/{dep}/package?offset=10&length=50")
        assert parte.status_code == 200 and len(parte.content) == 50
        assert parte.headers["x-total-size"] == str(pacote["size_bytes"])

        # Outro robô (de outro cliente) não vê nem baixa.
        from tests.test_isolamento_openapi import _login
        from valtexa.models import Membership, Role, Tenant, User
        from valtexa.security.passwords import hash_password
        with session.begin_nested():
            t = Tenant(name="Outro OTA", slug="outro-ota")
            u = User(email="dono@outro-ota.dev", full_name="D",
                     password_hash=hash_password("valtexa-demo-2026"))
            session.add_all([t, u])
            session.flush()
            session.add(Membership(tenant_id=t.id, user_id=u.id, role=Role.OWNER))
        session.commit()
        alheio = provision(client, _login(client, "dono@outro-ota.dev"), "ROVER_SCOUT_V1",
                           "OTA-ALHEIO")
        assert alheio.request("GET", "/v1/device/ota").json() == []
        assert alheio.request("GET", f"/v1/device/ota/{dep}/package").status_code == 404
        assert alheio.request("POST", f"/v1/device/ota/{dep}/status",
                              json_body={"state": "aplicada"}).status_code == 404

        # Estados: só as transições do protocolo.
        assert robo.request("POST", f"/v1/device/ota/{dep}/status",
                            json_body={"state": "aplicada"}).status_code == 409
        for estado in ("baixando", "verificando", "instalando", "verificando_saude", "aplicada"):
            r = robo.request("POST", f"/v1/device/ota/{dep}/status",
                             json_body={"state": estado, "version_running": "c-1"})
            assert r.status_code == 200, r.text
        lista = client.get("/v1/platform/ota/deployments",
                           params={"package_id": pacote["id"]}, headers=ops).json()
        meu = next(d for d in lista if d["id"] == dep)
        assert meu["state"] == "aplicada" and meu["finished_at"]
        assert [h["state"] for h in meu["history"]] == [
            "pendente", "baixando", "verificando", "instalando", "verificando_saude", "aplicada"]
        assert robo.request("GET", "/v1/device/ota").json() == [] or all(
            i["deployment_id"] != dep for i in robo.request("GET", "/v1/device/ota").json())
        trilha = session.scalars(select(AuditEntry.action).where(
            AuditEntry.action.like("ota.%"))).all()
        assert {"ota.package_published", "ota.deployment_created", "ota.aplicada"} <= set(trilha)

    def test_cancelar_antes_de_instalar(self, client, ops, robo, demo) -> None:
        pacote = publicar(client, ops, "config", "c-2", tar_de({"rover.json": b"{}"})).json()
        dep = client.post("/v1/platform/ota/deployments",
                          json={"package_id": pacote["id"], "device_ids": [robo.device_id]},
                          headers=ops).json()[0]["id"]
        r = client.post(f"/v1/platform/ota/deployments/{dep}/cancel", headers=ops)
        assert r.status_code == 200 and r.json()["state"] == "cancelada"
        assert robo.request("GET", f"/v1/device/ota/{dep}/package").status_code == 410


# ---------------------------------------------------------------------------
# Integração com o rover/ de verdade
# ---------------------------------------------------------------------------

rover = pytest.importorskip("valtexa_rover")
pytest.importorskip("onnx")

from valtexa_rover import launcher  # noqa: E402
from valtexa_rover.clock import ManualClock  # noqa: E402
from valtexa_rover.hal.interfaces import Hardware  # noqa: E402
from valtexa_rover.hal.local import LocalDiskStorage, OnnxCpuAccelerator  # noqa: E402
from valtexa_rover.hal.simulated import (  # noqa: E402
    FlakyNetwork,
    SimulatedImu,
    SimulatedSensors,
    TrajectoryGps,
)
from valtexa_rover.runtime.client import DeviceIdentity  # noqa: E402
from valtexa_rover.runtime.core import RoverCore  # noqa: E402
from valtexa_rover.runtime.model_manager import FolderArtifactSource  # noqa: E402

from tests.test_rover_integracao import modelo_minusculo, ponte  # noqa: E402


@pytest.fixture
def robo_real(client: TestClient, robo: DeviceSession, tmp_path: Path):
    relogio = ManualClock(datetime.now(UTC))
    gps = TrajectoryGps([(-47.0, -22.0), (-47.0, -21.999)], relogio)
    rede = FlakyNetwork(ponte(client))
    hardware = Hardware(cameras=[], gps=gps, imu=SimulatedImu(relogio, gps),
                        sensors=SimulatedSensors(relogio),
                        storage=LocalDiskStorage(tmp_path / "rover"), network=rede,
                        accelerator=OnnxCpuAccelerator(), hardware_version="Rover Edge V1 (sim)")
    identidade = DeviceIdentity(robo.device_id, robo.key_id, robo.private_key,
                                signing.platform_public_key(), signing.ota_public_key())
    repo = tmp_path / "artefatos"
    repo.mkdir()

    def novo_core() -> RoverCore:
        core = RoverCore(hardware, tmp_path / "rover", identidade, clock=relogio,
                         artifact_source=FolderArtifactSource(repo),
                         config_path=tmp_path / "rover" / "rover.json")
        core.boot()
        core.ota.chunk_size = 1024
        return core

    return {"novo_core": novo_core, "rede": rede, "repo": repo, "dados": tmp_path / "rover"}


def _destinar(client, ops, pacote_id: str, device_id: str) -> str:
    r = client.post("/v1/platform/ota/deployments",
                    json={"package_id": pacote_id, "device_ids": [device_id]}, headers=ops)
    assert r.status_code == 201, r.text
    return r.json()[0]["id"]


def _estado(session: Session, dep: str) -> OtaDeployment:
    session.expire_all()
    return session.get(OtaDeployment, dep)


def test_rover_atualiza_modelo_com_queda_no_meio_do_download(
    client, ops, robo, robo_real, demo, session: Session, tmp_path: Path
) -> None:
    designado = next(d for d in robo.request("GET", "/v1/device/models").json()
                     if d["field_id"] == demo["field_id"])
    build = tmp_path / "build"
    sha = modelo_minusculo(build)
    versao = model_registry.em_producao(session, designado["model_key"])
    versao.original_artifact_sha256 = sha
    versao.original_artifact_uri = f"s3://modelos/{sha}.onnx"
    session.commit()
    arquivos = {p.name: p.read_bytes() for p in build.iterdir()}
    pacote = publicar(client, ops, "model", "mod-1", tar_de(arquivos), versao.id)
    assert pacote.status_code == 201, pacote.text
    dep = _destinar(client, ops, pacote.json()["id"], robo.device_id)

    core = robo_real["novo_core"]()
    rede = robo_real["rede"]
    pedidos = []
    original = rede.handler

    def cai(method, path, body, headers):
        resposta = original(method, path, body, headers)
        if "/package" in path:
            pedidos.append(path)
            if len(pedidos) == 2:
                rede.set_online(False)
        return resposta

    rede.handler = cai
    assert core.ota.step().deferred == "offline"
    assert _estado(session, dep).state == "baixando"
    core = robo_real["novo_core"]()  # reinício no meio do download
    rede.set_online(True)
    rel = core.ota.step()
    assert rel.applied == [dep], rel
    estado = _estado(session, dep)
    assert estado.state == "aplicada"
    assert estado.bytes_served == pacote.json()["size_bytes"], "cada byte servido uma vez"
    assert (robo_real["repo"] / f"{sha}.onnx").exists()
    # O Model Manager carrega o modelo designado pelo registry, com o hash conferido.
    core.start_mission("m-ota", demo["field_id"])
    assert core.engine.package.sha256 == sha


def test_rover_recusa_pacote_adulterado_no_armazenamento(
    client, ops, robo, robo_real, session: Session
) -> None:
    pacote = publicar(client, ops, "config", "c-adult",
                      tar_de({"rover.json": b'{"sync": {"chunk_size": 4096}}'})).json()
    dep = _destinar(client, ops, pacote["id"], robo.device_id)
    linha = session.get(OtaPackage, pacote["id"])
    caminho = storage.store.path(linha.storage_key)
    bruto = bytearray(caminho.read_bytes())
    bruto[600] ^= 0xFF  # alguém mexeu no bucket
    caminho.write_bytes(bytes(bruto))
    core = robo_real["novo_core"]()
    assert core.ota.step().rejected == [dep]
    assert _estado(session, dep).state == "recusada"
    assert "hash" in _estado(session, dep).detail
    assert not (robo_real["dados"] / "rover.json").exists()


def test_runtime_que_nao_sobe_volta_e_a_plataforma_ve(
    client, ops, robo, robo_real, session: Session
) -> None:
    init = b'RUNTIME_VERSION = "0.9.0"\nEDGE_AI_VERSION = "0.1.0"\n'
    pacote = publicar(client, ops, "runtime", "0.9.0",
                      tar_de({"valtexa_rover/__init__.py": init})).json()
    dep = _destinar(client, ops, pacote["id"], robo.device_id)
    core = robo_real["novo_core"]()
    assert core.ota.step().applied == [dep]
    assert _estado(session, dep).state == "verificando_saude"  # em teste até o boot
    core.close()
    for _ in range(3):  # o novo nunca confirma
        revertidos, _amb = launcher.prepare(robo_real["dados"])
    assert revertidos == ["runtime"]
    core = robo_real["novo_core"]()
    core.ota.step()
    estado = _estado(session, dep)
    assert estado.state == "revertida" and "não confirmou" in estado.detail
    assert json.loads((robo_real["dados"] / "ota" / "current.json").read_text()) == {}
