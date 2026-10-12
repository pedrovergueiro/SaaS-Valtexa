"""Testes de segurança da Parte 9 (brief, seção 43) que faltavam na suíte.

Upload de arquivo (tipo pelo conteúdo, tamanho, caminho), resposta de arquivo que não
executa, corpo grande antes da autenticação, endpoints do Rover (replay, assinatura,
relógio, credencial revogada) e sessões (vencida no servidor, revogada). O que já
estava coberto é citado em ``docs/SEGURANCA.md`` com o teste de cada item.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from tests.helpers import DeviceSession, _path_query, frame, provision, upload_observation
from tests.test_collections import cria_coleta, sobe_arquivo
from tests.test_edge_sync import DADOS, abrir, enviar, mandar_chunk, registro
from valtexa.api.middleware import RawBodyMiddleware
from valtexa.models import Asset, CollectionFile, Observation, UserSession
from valtexa.security import signing

HTML = b"<html><script>fetch('/v1/auth/me')</script></html>"


@pytest.fixture
def robo(client: TestClient, admin_token: dict, demo: dict) -> DeviceSession:
    return provision(client, admin_token, "ROVER_SCOUT_V1", "SEC9-1", demo["farm_id"])


# ---------------------------------------------------------------------------
# Upload de arquivos
# ---------------------------------------------------------------------------


class TestUpload:
    def _observacao(self, robo: DeviceSession, demo: dict, dados: bytes, tipo: str):
        meta = {"sequence_number": robo.next_sequence(), "field_id": demo["field_id"],
                "captured_at": datetime.now(UTC).isoformat(), "lat": -21.9029,
                "lon": -45.8624, "model_input_ok": True}
        return robo.request("POST", "/v1/device/observations",
                            files={"file": ("f.jpg", dados, tipo)},
                            data={"metadata": json.dumps(meta)})

    def test_html_declarado_como_jpeg_e_recusado(self, robo, demo, session: Session) -> None:
        r = self._observacao(robo, demo, HTML, "image/jpeg")
        assert r.status_code == 415, r.text
        assert session.scalars(select(Asset)).all() == []

    def test_tipo_declarado_fora_da_lista_e_recusado(self, robo, demo) -> None:
        assert self._observacao(robo, demo, frame("Healthy"), "text/html").status_code == 415

    def test_tipo_guardado_e_o_dos_bytes(self, robo, demo, session: Session) -> None:
        r = self._observacao(robo, demo, frame("Healthy"), "image/png")  # é JPEG
        assert r.status_code in (200, 201), r.text
        assert session.scalars(select(Asset)).one().content_type == "image/jpeg"

    def test_coleta_com_extensao_de_imagem_e_conteudo_html_e_recusada(
        self, client, platform_token, demo, session: Session
    ) -> None:
        coleta = cria_coleta(client, platform_token, demo["field_id"])
        final = sobe_arquivo(client, platform_token, coleta["id"], "foto.jpg", HTML)
        assert final["state"] == "rejected"
        arquivo = session.get(CollectionFile, final["file_id"])
        assert "não é uma imagem" in arquivo.error and arquivo.asset_id is None

    def test_coleta_com_tipo_fora_da_lista_e_recusada(self, client, platform_token,
                                                     demo) -> None:
        coleta = cria_coleta(client, platform_token, demo["field_id"])
        r = client.post(f"/v1/admin/collections/{coleta['id']}/files", headers=platform_token,
                        json={"files": [{"filename": "x.html", "size_bytes": 10,
                                         "content_type": "text/html"}]})
        assert r.status_code in (400, 409, 422) and "não suportado" in r.text

    def test_nome_com_caminho_nao_vira_caminho(self, client, platform_token, demo,
                                               store, session: Session) -> None:
        coleta = cria_coleta(client, platform_token, demo["field_id"])
        dados = frame("Healthy")
        final = sobe_arquivo(client, platform_token, coleta["id"], "../../../etc/x.jpg", dados)
        assert final["state"] == "stored"
        asset = session.scalars(select(Asset)).one()
        assert ".." not in asset.storage_key
        assert asset.storage_key.endswith(hashlib.sha256(dados).hexdigest() + ".jpg")
        assert store.path(asset.storage_key).is_relative_to(store.root.resolve())

    def test_arquivo_maior_que_o_declarado_e_recusado(self, client, platform_token,
                                                      demo) -> None:
        coleta = cria_coleta(client, platform_token, demo["field_id"])
        arq = client.post(f"/v1/admin/collections/{coleta['id']}/files", headers=platform_token,
                          json={"files": [{"filename": "a.jpg", "size_bytes": 8}]}).json()[0]
        r = client.put(f"/v1/admin/collections/{coleta['id']}/files/{arq['id']}/chunk",
                       params={"offset": 0}, content=b"\xff\xd8\xff" + b"x" * 20,
                       headers=platform_token)
        assert r.status_code in (400, 409, 422) and "ultrapassa" in r.text

    def test_tipo_de_arquivo_do_rover_fora_da_lista_e_recusado(self, robo) -> None:
        r = abrir(robo, DADOS, content_type="text/html")
        assert r.status_code == 415, r.text


class TestRespostaDeArquivo:
    def test_arquivo_servido_nao_executa(self, client, admin_token, robo, demo,
                                         session: Session) -> None:
        """Mesmo um arquivo antigo, gravado antes da Parte 9 com tipo perigoso, sai inerte."""
        upload_observation(robo, demo["field_id"])
        obs = session.scalars(select(Observation)).one()
        asset = session.get(Asset, obs.image_asset_id)
        asset.content_type = "text/html"  # como teria entrado antes da correção
        session.commit()
        r = client.get(f"/v1/observations/{obs.id}/image", headers=admin_token)
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/octet-stream"
        assert r.headers["content-disposition"].startswith("attachment;")
        assert "sandbox" in r.headers["content-security-policy"]
        assert r.headers["x-content-type-options"] == "nosniff"

    def test_imagem_continua_inline(self, client, admin_token, robo, demo,
                                    session: Session) -> None:
        upload_observation(robo, demo["field_id"])
        obs = session.scalars(select(Observation)).one()
        r = client.get(f"/v1/observations/{obs.id}/image", headers=admin_token)
        assert r.headers["content-type"] == "image/jpeg"
        assert "content-disposition" not in r.headers

    def test_toda_resposta_tem_cabecalhos_de_seguranca(self, client) -> None:
        r = client.get("/health")
        assert r.headers["x-content-type-options"] == "nosniff"
        assert r.headers["x-frame-options"] == "DENY"


class TestCorpoGrande:
    def test_content_length_acima_do_teto_e_413_sem_autenticar(self, client) -> None:
        r = client.post("/v1/device/edge/records", content=b"x" * 10,
                        headers={"Content-Length": str(10**12)})
        assert r.status_code == 413

    def test_corpo_sem_tamanho_declarado_para_de_ser_lido_no_teto(self) -> None:
        chamou_a_rota = []

        async def rota(scope, receive, send):  # pragma: no cover - não deve rodar
            chamou_a_rota.append(1)

        mw = RawBodyMiddleware(rota, max_body_bytes=1000)
        enviados = []
        lidos = []

        async def receive():
            lidos.append(1)
            return {"type": "http.request", "body": b"x" * 400, "more_body": True}

        async def send(msg):
            enviados.append(msg)

        scope = {"type": "http", "path": "/v1/device/uploads", "headers": []}
        asyncio.run(mw(scope, receive, send))
        assert enviados[0]["status"] == 413 and chamou_a_rota == []
        assert len(lidos) == 3  # 400 + 400 + 400 > 1000: parou no terceiro pedaço


# ---------------------------------------------------------------------------
# Endpoints do Rover
# ---------------------------------------------------------------------------


def _assinado(robo: DeviceSession, metodo: str, caminho: str, corpo: bytes,
              quando: int | None = None) -> dict[str, str]:
    timestamp = str(quando if quando is not None else int(datetime.now(UTC).timestamp()))
    nonce = signing.new_nonce()
    return {
        signing.HEADER_KEY_ID: robo.key_id, signing.HEADER_TIMESTAMP: timestamp,
        signing.HEADER_NONCE: nonce, "Content-Type": "application/json",
        signing.HEADER_SIGNATURE: signing.sign_request(
            robo.private_key, metodo, *_path_query(caminho), timestamp, nonce, corpo),
    }


class TestRover:
    CAMINHO = "/v1/device/edge/records"

    def _corpo(self, robo: DeviceSession) -> bytes:
        return json.dumps({"records": [registro(robo, "ev-1")]}).encode()

    def test_replay_da_mesma_requisicao_e_recusado(self, client, robo) -> None:
        corpo = self._corpo(robo)
        cabecalhos = _assinado(robo, "POST", self.CAMINHO, corpo)
        assert client.post(self.CAMINHO, content=corpo, headers=cabecalhos).status_code == 200
        repetida = client.post(self.CAMINHO, content=corpo, headers=cabecalhos)
        assert repetida.status_code == 401 and "nonce" in repetida.text.lower()

    def test_corpo_trocado_depois_de_assinar_e_recusado(self, client, robo) -> None:
        cabecalhos = _assinado(robo, "POST", self.CAMINHO, self._corpo(robo))
        outro = json.dumps({"records": [registro(robo, "ev-forjado")]}).encode()
        assert client.post(self.CAMINHO, content=outro, headers=cabecalhos).status_code == 401

    def test_gravacao_antiga_fora_da_janela_e_recusada(self, client, robo) -> None:
        corpo = self._corpo(robo)
        velho = int((datetime.now(UTC) - timedelta(hours=1)).timestamp())
        r = client.post(self.CAMINHO, content=corpo,
                        headers=_assinado(robo, "POST", self.CAMINHO, corpo, velho))
        assert r.status_code == 401

    def test_assinatura_de_outro_robo_nao_vale(self, client, admin_token, demo, robo) -> None:
        outro = provision(client, admin_token, "ROVER_SCOUT_V1", "SEC9-2", demo["farm_id"])
        corpo = self._corpo(robo)
        cabecalhos = _assinado(robo, "POST", self.CAMINHO, corpo)
        cabecalhos[signing.HEADER_KEY_ID] = outro.key_id  # chave de um, assinatura de outro
        assert client.post(self.CAMINHO, content=corpo, headers=cabecalhos).status_code == 401

    def test_credencial_revogada_para_sync_e_upload_na_hora(
        self, client, admin_token, robo
    ) -> None:
        assert enviar(robo, [registro(robo, "ev-1")]).status_code == 200
        abrir(robo, DADOS)
        r = client.post(f"/v1/devices/{robo.device_id}/revoke-credentials", headers=admin_token)
        assert r.status_code in (200, 204), r.text
        assert enviar(robo, [registro(robo, "ev-2")]).status_code == 401
        assert mandar_chunk(robo, "up-1", 0, DADOS[:4096]).status_code == 401
        fim = robo.request("POST", "/v1/device/uploads/up-1/complete",
                           json_body={"sha256": hashlib.sha256(DADOS).hexdigest()})
        assert fim.status_code == 401


# ---------------------------------------------------------------------------
# Sessões
# ---------------------------------------------------------------------------


class TestSessoes:
    def test_sessao_vencida_no_servidor_cai_mesmo_com_token_valido(
        self, client, admin_token, session: Session
    ) -> None:
        assert client.get("/v1/farms", headers=admin_token).status_code == 200
        for linha in session.scalars(select(UserSession)):
            linha.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        session.commit()
        assert client.get("/v1/farms", headers=admin_token).status_code == 401

    def test_sessao_revogada_cai_em_todas_as_rotas_de_arquivo(
        self, client, admin_token, robo, demo, session: Session
    ) -> None:
        upload_observation(robo, demo["field_id"])
        obs = session.scalars(select(Observation)).one()
        rota = f"/v1/observations/{obs.id}/image"
        assert client.get(rota, headers=admin_token).status_code == 200
        client.post("/v1/auth/logout", headers=admin_token)
        assert client.get(rota, headers=admin_token).status_code == 401
        assert client.get(rota + "/url", headers=admin_token).status_code == 401


def test_dois_robos_com_serie_terminada_igual_provisionam(client, admin_token, demo) -> None:
    """Achado do ensaio de produção: o nome automático (modelo + 4 últimos dígitos da
    série) colidia em ``uq_device_tenant_name`` e o segundo provisionamento dava 500."""
    a = provision(client, admin_token, "ROVER_SCOUT_V1", "ROV-A-0007", demo["farm_id"])
    b = provision(client, admin_token, "ROVER_SCOUT_V1", "ROV-B-0007", demo["farm_id"])
    c = provision(client, admin_token, "ROVER_SCOUT_V1", "ROV-C-0007", demo["farm_id"])
    nomes = {client.get(f"/v1/devices/{r.device_id}", headers=admin_token).json()["name"]
             for r in (a, b, c)}
    assert len(nomes) == 3
