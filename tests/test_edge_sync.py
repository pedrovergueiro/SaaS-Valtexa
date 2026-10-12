"""Rotas de sincronização do Rover Runtime: idempotência, chunks, retomada e isolamento."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tests.helpers import DeviceSession, provision
from tests.test_isolamento_openapi import atacante  # noqa: F401 - fixture
from valtexa.models import Asset, EdgeRecord, EdgeUpload, PlatformRole
from valtexa.services import edge_sync


@pytest.fixture
def robo(client: TestClient, admin_token: dict, demo: dict) -> DeviceSession:
    return provision(client, admin_token, "ROVER_SCOUT_V1", "SYNC-001", demo["farm_id"])


def registro(robo: DeviceSession, rid: str, field_id: str | None = None, **extra) -> dict:
    corpo = {"id": rid, "kind": "event", "type": "IMAGE_EVENT_DETECTED",
             "device_id": robo.device_id, "field_id": field_id,
             "occurred_at": datetime.now(UTC).isoformat(),
             "payload": {"label": "Rust", "confidence": 0.91, "lat": -21.9, "lon": -45.8},
             **extra}
    return {"id": rid, "kind": "event", "type": "IMAGE_EVENT_DETECTED",
            "sha256": edge_sync.canonical_sha256(corpo), "body": corpo}


def enviar(robo: DeviceSession, registros: list[dict], remaining: int | None = None):
    corpo: dict = {"records": registros}
    if remaining is not None:
        corpo["remaining"] = remaining
    return robo.request("POST", "/v1/device/edge/records", json_body=corpo)


class TestRegistros:
    def test_mesmo_evento_duas_vezes_e_uma_ocorrencia(
        self, robo, demo, session: Session
    ) -> None:
        r = registro(robo, "ev-1", demo["field_id"])
        primeira = enviar(robo, [r])
        assert primeira.status_code == 200, primeira.text
        assert primeira.json()["accepted"] == ["ev-1"]
        segunda = enviar(robo, [r, r])  # reenvio, e duplicado dentro do mesmo lote
        assert segunda.json()["accepted"] == []
        assert segunda.json()["duplicated"] == ["ev-1", "ev-1"]
        assert session.scalar(select(func.count()).select_from(EdgeRecord)) == 1
        linha = session.scalars(select(EdgeRecord)).one()
        assert linha.field_id == demo["field_id"] and linha.label == "Rust"
        assert linha.confidence == pytest.approx(0.91) and linha.lat == pytest.approx(-21.9)

    def test_mesmo_id_com_outro_conteudo_e_conflito(self, robo, session: Session) -> None:
        enviar(robo, [registro(robo, "ev-1")])
        outro = registro(robo, "ev-1", payload={"label": "outra coisa"})
        resposta = enviar(robo, [outro]).json()
        assert resposta["conflicts"] == ["ev-1"] and resposta["accepted"] == []
        assert session.scalars(select(EdgeRecord)).one().payload["payload"]["label"] == "Rust"

    def test_hash_que_nao_confere_e_recusado(self, robo, session: Session) -> None:
        r = registro(robo, "ev-1")
        r["body"]["payload"]["label"] = "adulterado"
        resposta = enviar(robo, [r]).json()
        assert resposta["rejected"][0]["id"] == "ev-1"
        assert "sha256" in resposta["rejected"][0]["error"]
        assert session.scalar(select(func.count()).select_from(EdgeRecord)) == 0

    def test_registro_em_nome_de_outro_robo_e_recusado(self, robo) -> None:
        r = registro(robo, "ev-1", device_id="outro-robo")
        assert enviar(robo, [r]).json()["rejected"][0]["error"] == "registro de outro robô"

    def test_talhao_de_outro_cliente_nao_e_vinculado(
        self, client, robo, session: Session, equipe
    ) -> None:
        enviar(robo, [registro(robo, "ev-1", "talhao-que-nao-e-dele")])
        assert session.scalars(select(EdgeRecord)).one().field_id is None

    def test_remaining_deixa_a_frota_sincronizando(self, client, robo, admin_token) -> None:
        enviar(robo, [registro(robo, "ev-1")], remaining=40)
        frota = client.get("/v1/devices", headers=admin_token).json()
        meu = next(d for d in frota if d["id"] == robo.device_id)
        assert meu["fleet_state"] == "sincronizando"
        enviar(robo, [registro(robo, "ev-2")], remaining=0)
        frota = client.get("/v1/devices", headers=admin_token).json()
        meu = next(d for d in frota if d["id"] == robo.device_id)
        assert meu["fleet_state"] == "disponivel" and meu["last_sync_at"]

    def test_cliente_le_o_que_o_robo_sincronizou(self, client, robo, demo, admin_token) -> None:
        enviar(robo, [registro(robo, "ev-1", demo["field_id"])])
        lidos = client.get("/v1/edge/records", params={"field_id": demo["field_id"]},
                           headers=admin_token)
        assert lidos.status_code == 200, lidos.text
        assert [r["record_id"] for r in lidos.json()] == ["ev-1"]


def abrir(robo: DeviceSession, dados: bytes, upload_id: str = "up-1", chunk: int = 4096,
          **extra):
    return robo.request("POST", "/v1/device/uploads", json_body={
        "upload_id": upload_id, "sha256": hashlib.sha256(dados).hexdigest(),
        "size_bytes": len(dados), "content_type": "image/jpeg", "chunk_size": chunk,
        "record_id": "ev-1", "role": "original", "tier": "ORIGINAL", "priority": 2, **extra})


def mandar_chunk(robo: DeviceSession, upload_id: str, indice: int, pedaco: bytes):
    return robo.request("PUT", f"/v1/device/uploads/{upload_id}/chunks/{indice}",
                        content=pedaco, headers={"Content-Type": "application/octet-stream"})


DADOS = bytes(range(256)) * 70  # 17.920 bytes → 5 chunks de 4096


class TestUploads:
    def test_upload_com_queda_retoma_do_que_chegou(self, robo, store, session: Session) -> None:
        aberto = abrir(robo, DADOS).json()
        assert aberto["total_chunks"] == 5 and aberto["received_chunks"] == []
        for i in range(3):  # 3 de 5 e "cai"
            assert mandar_chunk(robo, "up-1", i, DADOS[i * 4096:(i + 1) * 4096]).status_code \
                == 200
        reaberto = abrir(robo, DADOS).json()  # a volta: a nuvem diz o que já tem
        assert reaberto["received_chunks"] == [0, 1, 2] and reaberto["status"] == "receiving"
        cedo = robo.request("POST", "/v1/device/uploads/up-1/complete",
                            json_body={"sha256": hashlib.sha256(DADOS).hexdigest()})
        assert cedo.status_code == 409 and "Faltam 2" in cedo.json()["detail"]
        for i in (3, 4):
            mandar_chunk(robo, "up-1", i, DADOS[i * 4096:(i + 1) * 4096])
        fim = robo.request("POST", "/v1/device/uploads/up-1/complete",
                           json_body={"sha256": hashlib.sha256(DADOS).hexdigest()})
        assert fim.status_code == 200, fim.text
        assert fim.json()["status"] == "complete" and fim.json()["asset_id"]
        asset = session.get(Asset, fim.json()["asset_id"])
        assert store.read(asset.storage_key) == DADOS  # bytes no object storage
        assert asset.meta["record_id"] == "ev-1"
        estado = robo.request("GET", "/v1/device/uploads/up-1").json()
        assert estado["received_chunks"] == [0, 1, 2, 3, 4]

    def test_reenvio_do_mesmo_arquivo_nao_duplica(self, robo, session: Session) -> None:
        abrir(robo, DADOS)
        for i in range(5):
            mandar_chunk(robo, "up-1", i, DADOS[i * 4096:(i + 1) * 4096])
        robo.request("POST", "/v1/device/uploads/up-1/complete",
                     json_body={"sha256": hashlib.sha256(DADOS).hexdigest()})
        # Mesmo arquivo, outro upload_id (o robô perdeu a confirmação e recomeçou).
        de_novo = abrir(robo, DADOS, upload_id="up-2").json()
        assert de_novo["status"] == "complete" and de_novo["deduplicated"] is True
        assert session.scalar(select(func.count()).select_from(Asset).where(
            Asset.sha256 == hashlib.sha256(DADOS).hexdigest())) == 1
        # Fechar de novo o primeiro é idempotente.
        outra = robo.request("POST", "/v1/device/uploads/up-1/complete",
                             json_body={"sha256": hashlib.sha256(DADOS).hexdigest()})
        assert outra.status_code == 200

    def test_chunk_errado_e_hash_que_nao_confere(self, robo, session: Session) -> None:
        abrir(robo, DADOS)
        assert mandar_chunk(robo, "up-1", 0, b"curto").status_code == 422
        assert mandar_chunk(robo, "up-1", 9, b"x" * 4096).status_code == 422
        errado = robo.request("PUT", "/v1/device/uploads/up-1/chunks/0", content=DADOS[:4096],
                              headers={"X-Chunk-Sha256": "0" * 64})
        assert errado.status_code == 422
        # Chunks com conteúdo trocado (tamanho certo): o todo não confere → descarta tudo.
        for i in range(5):
            pedaco = DADOS[i * 4096:(i + 1) * 4096]
            mandar_chunk(robo, "up-1", i, pedaco[::-1] if i == 2 else pedaco)
        fim = robo.request("POST", "/v1/device/uploads/up-1/complete",
                           json_body={"sha256": hashlib.sha256(DADOS).hexdigest()})
        assert fim.status_code == 422
        assert abrir(robo, DADOS).json()["received_chunks"] == []
        assert session.scalar(select(func.count()).select_from(Asset)) == 0

    def test_mesmo_upload_id_com_outro_conteudo_e_conflito(self, robo) -> None:
        abrir(robo, DADOS)
        assert abrir(robo, DADOS[:-1]).status_code == 409

    def test_tipo_e_tamanho(self, robo) -> None:
        assert abrir(robo, DADOS, content_type="text/html").status_code == 415
        grande = robo.request("POST", "/v1/device/uploads", json_body={
            "upload_id": "g", "sha256": "a" * 64, "size_bytes": 10**12,
            "content_type": "image/jpeg", "chunk_size": 4096})
        assert grande.status_code == 413

    def test_cota_de_armazenamento_do_plano(self, client, robo, demo, equipe) -> None:
        comercial = equipe(PlatformRole.COMERCIAL)
        assinatura = client.put(
            f"/v1/admin/tenants/{demo['tenant_id']}/subscription",
            json={"plan_code": "essencial", "overrides": {"max_storage_gb": 0.00001}},
            headers=comercial,
        )
        assert assinatura.status_code == 200, assinatura.text
        resposta = abrir(robo, DADOS)
        assert resposta.status_code == 409 and "armazenamento" in resposta.json()["detail"]

    def test_robo_de_outro_cliente_nao_ve_o_upload(
        self, robo, atacante, session: Session  # noqa: F811 - fixture importada
    ) -> None:
        abrir(robo, DADOS)
        intruso: DeviceSession = atacante["robo"]
        assert mandar_chunk(intruso, "up-1", 0, DADOS[:4096]).status_code == 404
        assert intruso.request("GET", "/v1/device/uploads/up-1").status_code == 404
        assert intruso.request("POST", "/v1/device/uploads/up-1/complete",
                               json_body={"sha256": "a" * 64}).status_code == 404
        assert session.scalar(select(func.count()).select_from(EdgeUpload)) == 1
