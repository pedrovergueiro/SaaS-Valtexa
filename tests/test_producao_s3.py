"""Object storage S3 de produção (Parte 9, seções 38 e 43), contra um S3 por HTTP.

O S3 é o ``moto`` em modo servidor (``ThreadedMotoServer``): o ``boto3`` de verdade
fala HTTP com ele, com assinatura SigV4, multipart, etiquetas, listagem paginada e
lifecycle. Não é a AWS nem o MinIO (o MinIO não pôde ser baixado nesta sessão): o
que o moto **não** confere — a assinatura das URLs pré-assinadas — é conferido aqui
por um verificador SigV4 independente, escrito a partir da especificação da AWS.
"""

from __future__ import annotations

import hashlib
import hmac
import uuid
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qsl, quote, urlsplit

import boto3
import httpx
import pytest
from botocore.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from tests.helpers import DeviceSession, provision
from tests.test_edge_sync import DADOS, abrir, enviar, mandar_chunk, registro
from tests.test_isolamento_openapi import atacante  # noqa: F401 - fixture
from valtexa.config import settings
from valtexa.models import Asset, Role
from valtexa.services import edge_sync, storage

moto_server = pytest.importorskip("moto.server")

CHAVE = "AKIAVALTEXATESTE0001"
SEGREDO = "segredo-do-teste-" + "x" * 23


@pytest.fixture(scope="module")
def s3_url():
    # 127.0.0.1 e não o padrão 0.0.0.0: no Windows não se conecta a 0.0.0.0.
    servidor = moto_server.ThreadedMotoServer(ip_address="127.0.0.1", port=0, verbose=False)
    servidor.start()
    host, porta = servidor.get_host_and_port()
    yield f"http://{host}:{porta}"
    servidor.stop()


def _cliente(url: str):
    return boto3.client(
        "s3", endpoint_url=url, region_name="us-east-1", aws_access_key_id=CHAVE,
        aws_secret_access_key=SEGREDO,
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


@pytest.fixture
def bucket(s3_url) -> str:
    nome = f"vtx-{uuid.uuid4().hex[:12]}"
    _cliente(s3_url).create_bucket(Bucket=nome)
    return nome


@pytest.fixture
def s3(s3_url, bucket, monkeypatch) -> storage.S3ObjectStore:
    """A plataforma inteira usando S3: objetos e *staging* dos chunks no bucket."""
    store = storage.S3ObjectStore(bucket, "vtx", client=_cliente(s3_url))
    monkeypatch.setattr(storage, "store", store)
    monkeypatch.setattr(edge_sync, "staging", storage.S3ChunkStaging(store, area="edge"))
    return store


def _replica(s3_url: str, bucket: str) -> storage.S3ObjectStore:
    """Outra réplica da API: outro processo, outro cliente boto3, mesmo bucket."""
    return storage.S3ObjectStore(bucket, "vtx", client=_cliente(s3_url))


# ---------------------------------------------------------------------------
# Verificador SigV4 de URL pré-assinada (independente do boto3)
# ---------------------------------------------------------------------------


def _hmac(chave: bytes, texto: str) -> bytes:
    return hmac.new(chave, texto.encode(), hashlib.sha256).digest()


def assinatura_valida(url: str, segredo: str = SEGREDO, agora: datetime | None = None) -> bool:
    """O que o S3 faz ao receber a URL: refaz a assinatura e confere a validade."""
    partes = urlsplit(url)
    params = dict(parse_qsl(partes.query, keep_blank_values=True))
    if params.get("X-Amz-Algorithm") != "AWS4-HMAC-SHA256":
        return False
    quando = datetime.strptime(params["X-Amz-Date"], "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
    if (agora or datetime.now(UTC)) > quando + timedelta(seconds=int(params["X-Amz-Expires"])):
        return False
    recebida = params.pop("X-Amz-Signature")
    consulta = "&".join(
        f"{quote(k, safe='-_.~')}={quote(v, safe='-_.~')}" for k, v in sorted(params.items())
    )
    canonico = "\n".join([
        "GET", quote(partes.path, safe="/-_.~"), consulta, f"host:{partes.netloc}", "",
        params["X-Amz-SignedHeaders"], "UNSIGNED-PAYLOAD",
    ])
    data, regiao, servico, _ = params["X-Amz-Credential"].split("/")[1:]
    escopo = f"{data}/{regiao}/{servico}/aws4_request"
    a_assinar = "\n".join([
        "AWS4-HMAC-SHA256", params["X-Amz-Date"], escopo,
        hashlib.sha256(canonico.encode()).hexdigest(),
    ])
    chave = _hmac(_hmac(_hmac(_hmac(f"AWS4{segredo}".encode(), data), regiao), servico),
                  "aws4_request")
    esperada = hmac.new(chave, a_assinar.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(esperada, recebida)


# ---------------------------------------------------------------------------
# Armazenamento
# ---------------------------------------------------------------------------


class TestObjetos:
    def test_guarda_le_e_etiqueta_a_categoria(self, s3: storage.S3ObjectStore, bucket) -> None:
        foto = s3.put(b"\xff\xd8 foto", "image/jpeg", namespace="cliente-a")
        nuvem = s3.put(b"ply", "application/x-ply", namespace="cliente-a")
        pacote = s3.put(b"tar", "application/x-tar", namespace="ota")
        assert s3.read(foto.key) == b"\xff\xd8 foto" and s3.exists(foto.key)

        def etiqueta(key: str) -> str:
            tags = s3.client.get_object_tagging(Bucket=bucket, Key=f"vtx/{key}")["TagSet"]
            return {t["Key"]: t["Value"] for t in tags}["categoria"]

        assert [etiqueta(o.key) for o in (foto, nuvem, pacote)] == \
            ["imagem", "nuvem_pontos", "ota"]
        s3.delete(foto.key)
        assert not s3.exists(foto.key)

    def test_objeto_grande_sobe_em_multipart(self, s3: storage.S3ObjectStore, bucket) -> None:
        dados = bytes(range(256)) * (36 * 1024 + 7)  # ~9,4 MB > limite de 8 MB
        guardado = s3.put(dados, "image/png", namespace="cliente-a")
        cabecalho = s3.client.head_object(Bucket=bucket, Key=f"vtx/{guardado.key}")
        # ETag de multipart é "md5-das-partes-N": prova que subiu em 2 partes.
        assert cabecalho["ETag"].strip('"').endswith("-2")
        assert s3.read(guardado.key) == dados
        assert guardado.sha256 == hashlib.sha256(dados).hexdigest()
        pendentes = s3.client.list_multipart_uploads(Bucket=bucket).get("Uploads", [])
        assert pendentes == []

    def test_parte_que_falha_aborta_o_multipart(self, s3: storage.S3ObjectStore, bucket,
                                                monkeypatch) -> None:
        original = s3.client.upload_part
        chamadas = []

        def falha_na_segunda(**kw):
            chamadas.append(kw["PartNumber"])
            if kw["PartNumber"] == 2:
                raise ConnectionError("rede caiu")
            return original(**kw)

        monkeypatch.setattr(s3.client, "upload_part", falha_na_segunda)
        with pytest.raises(ConnectionError):
            s3.put(b"y" * (9 * 1024 * 1024), "image/png", namespace="cliente-a")
        assert chamadas == [1, 2]
        assert s3.client.list_multipart_uploads(Bucket=bucket).get("Uploads", []) == []

    def test_chave_com_travessia_e_recusada(self, s3: storage.S3ObjectStore) -> None:
        with pytest.raises(storage.UnknownAssetError):
            s3.read("cliente-a/../cliente-b/aa/bb/x.jpg")
        with pytest.raises(storage.UnknownAssetError):
            s3.url_assinada("../segredo", 60)


class TestStagingCompartilhado:
    def test_chunks_de_um_upload_em_duas_replicas(self, s3_url, bucket) -> None:
        a = storage.S3ChunkStaging(_replica(s3_url, bucket))
        b = storage.S3ChunkStaging(_replica(s3_url, bucket))
        a.put("up1", 0, b"aa")
        b.put("up1", 2, b"cc")
        a.put("up1", 1, b"bb")
        assert b.received("up1") == {0, 1, 2} == a.received("up1")
        assert b.assemble("up1", 3) == b"aabbcc"
        a.clear("up1")
        assert b.received("up1") == set()

    def test_listagem_paginada_com_mais_de_mil_chunks(self, s3: storage.S3ObjectStore) -> None:
        staging = storage.S3ChunkStaging(s3)
        for i in range(1005):
            staging.put("grande", i, b"x")
        assert staging.received("grande") == set(range(1005))
        staging.clear("grande")
        assert staging.received("grande") == set()

    def test_upload_do_robo_troca_de_replica_no_meio(
        self, client: TestClient, admin_token, demo, s3_url, bucket, s3, monkeypatch,
        session: Session,
    ) -> None:
        """O caso que o disco local não atende: chunks 0 a 2 numa réplica, 3 e 4 e o
        ``complete`` noutra. Antes da Parte 9, o ``complete`` dava 409 para sempre."""
        robo = provision(client, admin_token, "ROVER_SCOUT_V1", "S3-R1", demo["farm_id"])
        assert abrir(robo, DADOS).status_code == 200
        for i in range(3):
            assert mandar_chunk(robo, "up-1", i, DADOS[i * 4096:(i + 1) * 4096]).status_code \
                == 200
        outra = _replica(s3_url, bucket)  # o balanceador mandou o resto para a réplica B
        monkeypatch.setattr(storage, "store", outra)
        monkeypatch.setattr(edge_sync, "staging", storage.S3ChunkStaging(outra, area="edge"))
        assert abrir(robo, DADOS).json()["received_chunks"] == [0, 1, 2]
        for i in (3, 4):
            mandar_chunk(robo, "up-1", i, DADOS[i * 4096:(i + 1) * 4096])
        fim = robo.request("POST", "/v1/device/uploads/up-1/complete",
                           json_body={"sha256": hashlib.sha256(DADOS).hexdigest()})
        assert fim.status_code == 200, fim.text
        asset = session.get(Asset, fim.json()["asset_id"])
        assert s3.read(asset.storage_key) == DADOS
        # O staging foi limpo no bucket: nenhum chunk sobrou.
        sobras = s3.client.list_objects_v2(Bucket=bucket, Prefix="vtx/_staging/")
        assert sobras.get("KeyCount", 0) == 0

    def test_coleta_em_pedacos_pelo_bucket(
        self, client: TestClient, platform_token, demo, s3: storage.S3ObjectStore, bucket,
        session: Session,
    ) -> None:
        from tests.test_collections import cria_coleta, sobe_arquivo

        coleta = cria_coleta(client, platform_token, demo["field_id"])
        dados = b"\xff\xd8\xff" + bytes(range(200))
        final = sobe_arquivo(client, platform_token, coleta["id"], "a.jpg", dados, pedaco=50)
        assert final["state"] == "stored", final
        asset = session.scalars(
            select(Asset).where(Asset.sha256 == hashlib.sha256(dados).hexdigest())).one()
        assert s3.read(asset.storage_key) == dados
        sobras = s3.client.list_objects_v2(Bucket=bucket, Prefix="vtx/_staging/coleta/")
        assert sobras.get("KeyCount", 0) == 0


class TestCicloDeVida:
    def test_politica_por_categoria_gravada_no_bucket(self, s3: storage.S3ObjectStore,
                                                      bucket) -> None:
        storage.aplicar_ciclo_de_vida(s3)
        regras = {r["ID"]: r for r in s3.client.get_bucket_lifecycle_configuration(
            Bucket=bucket)["Rules"]}
        assert regras["staging-chunks"]["Expiration"]["Days"] == settings.s3_staging_days
        assert regras["staging-chunks"]["Filter"]["Prefix"] == "vtx/_staging/"
        assert regras["multipart-incompleto"]["AbortIncompleteMultipartUpload"] == \
            {"DaysAfterInitiation": 1}
        imagem = regras["imagem-transicao"]
        assert imagem["Filter"]["And"]["Tags"] == [{"Key": "categoria", "Value": "imagem"}]
        assert [t["StorageClass"] for t in imagem["Transitions"]] == \
            ["STANDARD_IA", "GLACIER_IR"]
        # Foto do cliente não expira por padrão; log só se configurado.
        assert "Expiration" not in imagem and "log-expiracao" not in regras

    def test_expiracao_de_log_quando_configurada(self, monkeypatch) -> None:
        monkeypatch.setattr(storage, "settings",
                            settings.model_copy(update={"s3_logs_expire_days": 400}))
        regras = {r["ID"]: r for r in storage.politica_de_ciclo_de_vida("vtx")["Rules"]}
        assert regras["log-expiracao"]["Expiration"] == {"Days": 400}


# ---------------------------------------------------------------------------
# URL assinada (seção 43: acesso ao storage)
# ---------------------------------------------------------------------------


@pytest.fixture
def evento_com_foto(client: TestClient, admin_token, demo, s3) -> dict:
    robo: DeviceSession = provision(client, admin_token, "ROVER_SCOUT_V1", "S3-URL",
                                    demo["farm_id"])
    assert enviar(robo, [registro(robo, "ev-1", demo["field_id"])]).status_code == 200
    abrir(robo, DADOS)
    for i in range(5):
        mandar_chunk(robo, "up-1", i, DADOS[i * 4096:(i + 1) * 4096])
    fim = robo.request("POST", "/v1/device/uploads/up-1/complete",
                       json_body={"sha256": hashlib.sha256(DADOS).hexdigest()})
    assert fim.status_code == 200, fim.text
    linha = client.get("/v1/edge/records", headers=admin_token).json()
    pk = next(r["id"] for r in linha if r["record_id"] == "ev-1")
    return {"pk": pk, "rota": f"/v1/edge/records/{pk}/files/up-1/url"}


class TestUrlAssinada:
    def test_cliente_baixa_direto_do_bucket(self, client, admin_token, evento_com_foto) -> None:
        link = client.get(evento_com_foto["rota"], headers=admin_token)
        assert link.status_code == 200, link.text
        corpo = link.json()
        assert corpo["direct"] is True and corpo["expires_in"] == settings.s3_presign_seconds
        assert "X-Amz-Signature=" in corpo["url"] and "X-Amz-Expires=300" in corpo["url"]
        assert assinatura_valida(corpo["url"])
        assert httpx.get(corpo["url"]).content == DADOS

    def test_outro_cliente_nao_recebe_url(self, client, evento_com_foto, atacante) -> None:  # noqa: F811
        for papel in (Role.OWNER, Role.ADMIN, Role.AGRONOMIST):
            r = client.get(evento_com_foto["rota"], headers=atacante["tokens"][papel])
            assert r.status_code == 404, (papel, r.text)

    def test_url_adulterada_para_outro_objeto_nao_vale(
        self, client, admin_token, evento_com_foto, s3: storage.S3ObjectStore
    ) -> None:
        """Quem tem uma URL válida do cliente A troca o caminho para o objeto de B."""
        url = client.get(evento_com_foto["rota"], headers=admin_token).json()["url"]
        alheio = s3.put(b"foto do cliente B", "image/jpeg", namespace="cliente-b")
        caminho_a = urlsplit(url).path
        caminho_b = caminho_a.rsplit("/vtx/", 1)[0] + f"/vtx/{alheio.key}"
        adulterada = url.replace(caminho_a, caminho_b)
        assert adulterada != url
        assert assinatura_valida(url) and not assinatura_valida(adulterada)
        # E mudar a validade também invalida a assinatura.
        assert not assinatura_valida(url.replace("X-Amz-Expires=300", "X-Amz-Expires=99999"))

    def test_url_vence(self, client, admin_token, evento_com_foto) -> None:
        url = client.get(evento_com_foto["rota"], headers=admin_token).json()["url"]
        depois = datetime.now(UTC) + timedelta(seconds=settings.s3_presign_seconds + 5)
        assert assinatura_valida(url) and not assinatura_valida(url, agora=depois)

    def test_disco_local_devolve_a_rota_autenticada(
        self, client, admin_token, demo, store
    ) -> None:
        robo = provision(client, admin_token, "ROVER_SCOUT_V1", "LOC-URL", demo["farm_id"])
        enviar(robo, [registro(robo, "ev-1")])
        abrir(robo, DADOS)
        for i in range(5):
            mandar_chunk(robo, "up-1", i, DADOS[i * 4096:(i + 1) * 4096])
        robo.request("POST", "/v1/device/uploads/up-1/complete",
                     json_body={"sha256": hashlib.sha256(DADOS).hexdigest()})
        pk = client.get("/v1/edge/records", headers=admin_token).json()[0]["id"]
        corpo = client.get(f"/v1/edge/records/{pk}/files/up-1/url", headers=admin_token).json()
        assert corpo == {"url": f"/v1/edge/records/{pk}/files/up-1", "direct": False,
                         "expires_in": None}
        assert client.get(corpo["url"]).status_code == 401  # sem login, nada
        assert client.get(corpo["url"], headers=admin_token).content == DADOS


def test_subida_da_api_com_s3_nao_procura_pasta(s3: storage.S3ObjectStore) -> None:
    """O ``lifespan`` fazia ``store.root.mkdir`` — atributo que o S3 não tem: a API
    com ``STORAGE_BACKEND=s3`` não subia (achado da Parte 9)."""
    assert not hasattr(s3, "root")
    storage.preparar()  # não levanta


def test_s3_assets_do_banco_nao_tem_bytes(session: Session) -> None:
    """Seção 37: banco só com metadados (o Asset guarda chave, hash e tamanho)."""
    colunas = {c.name for c in Asset.__table__.columns}
    assert {"storage_key", "sha256", "size_bytes"} <= colunas
    assert not any(str(c.type).upper() in {"BLOB", "BYTEA", "LARGEBINARY"}
                   for c in Asset.__table__.columns)
    assert session.scalars(select(Asset)).all() == []
