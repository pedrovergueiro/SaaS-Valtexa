"""O fluxo do MVP, ponta a ponta.

Cliente → propriedade → talhão → coleta → upload grande → fila → ValTexa-B →
resultado → revisão do agrônomo → dataset → cliente vê.

O teste que mais importa aqui é o da coleta **aérea**: hoje não existe modelo
treinado para ela, e o comportamento correto é guardar, catalogar e mandar para
o agrônomo — nunca classificar. Se um dia alguém apontar a imagem aérea para o
modelo de folha, é este arquivo que quebra.
"""

from __future__ import annotations

import hashlib
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from tests.helpers import frame
from valtexa import worker
from valtexa.models import Collection, CollectionFileState, CollectionState

HOJE = date(2026, 9, 22)


# ---------------------------------------------------------------------------
# Utilitários
# ---------------------------------------------------------------------------


def cria_coleta(client: TestClient, token: dict, field_id: str, **extra) -> dict:
    corpo = {
        "field_id": field_id,
        "collected_on": HOJE.isoformat(),
        "source": "drone_third_party",
        "kind": "aerial_image",
        "operator_name": "Drones do Sul — piloto terceirizado",
        **extra,
    }
    resposta = client.post("/v1/admin/collections", json=corpo, headers=token)
    assert resposta.status_code == 201, resposta.text
    return resposta.json()


def sobe_arquivo(
    client: TestClient,
    token: dict,
    coleta_id: str,
    nome: str,
    dados: bytes,
    *,
    pedaco: int = 16,
    com_sha: bool = True,
) -> dict:
    """Declara e envia um arquivo em pedaços, como o painel faz."""
    declarado = {
        "filename": nome,
        "size_bytes": len(dados),
        "content_type": "image/jpeg",
    }
    if com_sha:
        declarado["sha256"] = hashlib.sha256(dados).hexdigest()

    resposta = client.post(
        f"/v1/admin/collections/{coleta_id}/files",
        json={"files": [declarado]},
        headers=token,
    )
    assert resposta.status_code == 201, resposta.text
    arquivo = resposta.json()[0]

    for inicio in range(0, len(dados), pedaco):
        parte = dados[inicio : inicio + pedaco]
        envio = client.put(
            f"/v1/admin/collections/{coleta_id}/files/{arquivo['id']}/chunk",
            params={"offset": inicio},
            content=parte,
            headers=token,
        )
        assert envio.status_code == 200, envio.text
    return envio.json()


def roda_worker(session_factory: sessionmaker, ciclos: int = 20) -> int:
    """Gira o worker até a fila esvaziar. Devolve quantos ciclos usou."""
    from valtexa import db

    with db.session_scope() as session:
        pass
    for volta in range(1, ciclos + 1):
        with db.session_scope() as session:
            if worker.process_collections(session) == 0:
                return volta
    return ciclos


# ---------------------------------------------------------------------------
# Fronteira entre o painel da ValTexa e o console do cliente
# ---------------------------------------------------------------------------


class TestFronteira:
    def test_cliente_nao_entra_no_painel_admin(
        self, client: TestClient, admin_token: dict, agronomist_token: dict, demo: dict
    ) -> None:
        """Nem o admin do cliente entra: o painel é da equipe da ValTexa."""
        for token in (admin_token, agronomist_token):
            resposta = client.get("/v1/admin/collections", headers=token)
            assert resposta.status_code == 403
            assert "equipe da ValTexa" in resposta.json()["detail"]

    def test_equipe_valtexa_entra(self, client: TestClient, platform_token: dict) -> None:
        assert client.get("/v1/admin/collections", headers=platform_token).status_code == 200

    def test_capacidades_de_plataforma_nao_vem_de_papel(
        self, client: TestClient, admin_token: dict, platform_token: dict
    ) -> None:
        do_cliente = client.get("/v1/auth/me", headers=admin_token).json()["capabilities"]
        da_equipe = client.get("/v1/auth/me", headers=platform_token).json()["capabilities"]
        assert "collection:manage" not in do_cliente
        assert "collection:manage" in da_equipe
        assert "dataset:manage" in da_equipe


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------


class TestUpload:
    def test_coleta_nasce_com_codigo_sequencial(
        self, client: TestClient, platform_token: dict, demo: dict
    ) -> None:
        primeira = cria_coleta(client, platform_token, demo["field_id"])
        segunda = cria_coleta(client, platform_token, demo["field_id"])
        assert primeira["code"] == "COL-2026-000001"
        assert segunda["code"] == "COL-2026-000002"

    def test_upload_em_pedacos_monta_o_arquivo(
        self, client: TestClient, platform_token: dict, demo: dict, store
    ) -> None:
        coleta = cria_coleta(client, platform_token, demo["field_id"])
        dados = frame("Healthy") * 6
        final = sobe_arquivo(client, platform_token, coleta["id"], "voo_0001.jpg", dados)

        assert final["complete"] is True
        assert final["received_bytes"] == len(dados)
        assert final["state"] == CollectionFileState.STORED.value

        arquivos = client.get(
            f"/v1/admin/collections/{coleta['id']}/files", headers=platform_token
        ).json()
        assert arquivos[0]["sha256"] == hashlib.sha256(dados).hexdigest()

    def test_pedaco_fora_de_ordem_diz_de_onde_continuar(
        self, client: TestClient, platform_token: dict, demo: dict, store
    ) -> None:
        """É o que torna o upload retomável: o 409 carrega o deslocamento certo."""
        coleta = cria_coleta(client, platform_token, demo["field_id"])
        dados = frame("Healthy") * 4
        declarados = client.post(
            f"/v1/admin/collections/{coleta['id']}/files",
            json={"files": [{"filename": "a.jpg", "size_bytes": len(dados)}]},
            headers=platform_token,
        ).json()
        arquivo_id = declarados[0]["id"]
        rota = f"/v1/admin/collections/{coleta['id']}/files/{arquivo_id}/chunk"

        client.put(rota, params={"offset": 0}, content=dados[:10], headers=platform_token)
        pulado = client.put(
            rota, params={"offset": 40}, content=dados[40:], headers=platform_token
        )
        assert pulado.status_code == 409
        assert pulado.headers["X-Received-Bytes"] == "10"

        # O painel lê o cabeçalho e continua exatamente dali.
        retomada = client.put(
            rota, params={"offset": 10}, content=dados[10:], headers=platform_token
        )
        assert retomada.status_code == 200
        assert retomada.json()["complete"] is True

    def test_reenvio_do_mesmo_pedaco_e_aceito(
        self, client: TestClient, platform_token: dict, demo: dict, store
    ) -> None:
        """A rede cai entre gravar e confirmar; o cliente reenvia o mesmo pedaço."""
        coleta = cria_coleta(client, platform_token, demo["field_id"])
        dados = frame("Healthy") * 4
        arquivo_id = client.post(
            f"/v1/admin/collections/{coleta['id']}/files",
            json={"files": [{"filename": "a.jpg", "size_bytes": len(dados)}]},
            headers=platform_token,
        ).json()[0]["id"]
        rota = f"/v1/admin/collections/{coleta['id']}/files/{arquivo_id}/chunk"

        client.put(rota, params={"offset": 0}, content=dados[:20], headers=platform_token)
        repetido = client.put(
            rota, params={"offset": 0}, content=dados[:20], headers=platform_token
        )
        assert repetido.status_code == 200
        assert repetido.json()["received_bytes"] == 20

    def test_sha256_divergente_recusa_o_arquivo(
        self, client: TestClient, platform_token: dict, demo: dict, store
    ) -> None:
        """Arquivo corrompido no caminho não entra no armazenamento."""
        coleta = cria_coleta(client, platform_token, demo["field_id"])
        dados = frame("Healthy") * 4
        arquivo_id = client.post(
            f"/v1/admin/collections/{coleta['id']}/files",
            json={
                "files": [
                    {
                        "filename": "a.jpg",
                        "size_bytes": len(dados),
                        "sha256": "0" * 64,
                    }
                ]
            },
            headers=platform_token,
        ).json()[0]["id"]

        resposta = client.put(
            f"/v1/admin/collections/{coleta['id']}/files/{arquivo_id}/chunk",
            params={"offset": 0},
            content=dados,
            headers=platform_token,
        )
        assert resposta.json()["state"] == CollectionFileState.REJECTED.value

        detalhe = client.get(
            f"/v1/admin/collections/{coleta['id']}/files", headers=platform_token
        ).json()[0]
        assert "sha256 não confere" in detalhe["error"]

    def test_progresso_tem_duas_barras(
        self, client: TestClient, platform_token: dict, demo: dict, store
    ) -> None:
        coleta = cria_coleta(client, platform_token, demo["field_id"])
        dados = frame("Healthy") * 4
        sobe_arquivo(client, platform_token, coleta["id"], "a.jpg", dados)

        atual = client.get(
            f"/v1/admin/collections/{coleta['id']}", headers=platform_token
        ).json()
        assert atual["progress"]["upload_percent"] == 100.0
        assert atual["progress"]["processing_percent"] == 0.0
        assert atual["progress"]["stored"] == 1


# ---------------------------------------------------------------------------
# Escolha do modelo — o ponto do MVP
# ---------------------------------------------------------------------------


class TestEscolhaDeModelo:
    def test_coleta_aerea_de_cafe_nao_tem_modelo_nenhum(
        self, client: TestClient, platform_token: dict, demo: dict
    ) -> None:
        """O painel avisa no formulário, não depois de 1.500 imagens.

        Para café visto de cima não existe nem modelo em quarentena: o único
        aéreo do catálogo, ``aerial-canopy``, é de milho. A recusa diz isso e
        lista o que de fato está treinado, em vez de apontar um vizinho que não
        serve.
        """
        coleta = cria_coleta(client, platform_token, demo["field_id"], kind="aerial_image")
        assert coleta["platform"] == "aerial"
        assert coleta["model_key"] is None
        motivo = coleta["no_model_reason"]
        assert "coffee" in motivo and "aerial" in motivo
        assert "aerial-canopy" not in motivo
        assert "coffee-foliar" in motivo  # o que existe, e é de solo

    def test_coleta_aerea_de_milho_aponta_o_modelo_em_formacao(
        self, client: TestClient, platform_token: dict, demo: dict, session_factory
    ) -> None:
        """Milho aéreo tem modelo no catálogo, só não tem peso treinado."""
        from valtexa.models import Field

        with session_factory() as session:
            campo = session.get(Field, demo["field_id"])
            milho = Field(
                tenant_id=campo.tenant_id,
                farm_id=campo.farm_id,
                name="Talhão de milho",
                crop="corn",
                boundary=campo.boundary,
            )
            session.add(milho)
            session.commit()
            milho_id = milho.id

        coleta = cria_coleta(client, platform_token, milho_id, kind="aerial_image")
        assert coleta["model_key"] is None
        assert "aerial-canopy" in coleta["no_model_reason"]
        assert "nenhum peso treinado" in coleta["no_model_reason"]

    def test_coleta_de_solo_resolve_o_modelo_da_cultura(
        self, client: TestClient, platform_token: dict, demo: dict
    ) -> None:
        coleta = cria_coleta(client, platform_token, demo["field_id"], kind="ground_image")
        assert coleta["platform"] == "ground"
        assert coleta["model_key"] == "coffee-foliar"
        assert coleta["no_model_reason"] is None

    def test_origem_de_drone_proprio_e_recusada(
        self, client: TestClient, platform_token: dict, demo: dict
    ) -> None:
        """O drone da ValTexa é fase futura: nenhuma coleta nasce com essa origem."""
        resposta = client.post(
            "/v1/admin/collections",
            json={
                "field_id": demo["field_id"],
                "collected_on": HOJE.isoformat(),
                "source": "drone_owned",
                "kind": "aerial_image",
            },
            headers=platform_token,
        )
        assert resposta.status_code == 422
        assert "fase futura" in resposta.json()["detail"]

    def test_missao_aerea_autonoma_responde_501(
        self, client: TestClient, platform_token: dict
    ) -> None:
        resposta = client.post("/v1/admin/drone-missions", headers=platform_token)
        assert resposta.status_code == 501
        assert "não faz parte do MVP" in resposta.json()["detail"]


# ---------------------------------------------------------------------------
# Processamento assíncrono
# ---------------------------------------------------------------------------


class TestProcessamento:
    def test_coleta_aerea_vai_toda_para_o_agronomo_sem_classificar(
        self,
        client: TestClient,
        platform_token: dict,
        demo: dict,
        store,
        session_factory: sessionmaker,
    ) -> None:
        """Nenhum classificador é chamado. É o resultado honesto, não uma falha."""
        coleta = cria_coleta(client, platform_token, demo["field_id"], kind="aerial_image")
        for i in range(3):
            sobe_arquivo(client, platform_token, coleta["id"], f"voo_{i}.jpg", frame("Healthy") * 3)

        fechada = client.post(
            f"/v1/admin/collections/{coleta['id']}/complete", headers=platform_token
        ).json()
        assert fechada["state"] == CollectionState.PROCESSING_QUEUED.value

        roda_worker(session_factory)

        final = client.get(
            f"/v1/admin/collections/{coleta['id']}", headers=platform_token
        ).json()
        assert final["state"] == CollectionState.REVIEW_REQUIRED.value
        assert final["progress"]["no_model"] == 3
        assert final["progress"]["analyzed"] == 0

        arquivos = client.get(
            f"/v1/admin/collections/{coleta['id']}/files", headers=platform_token
        ).json()
        assert {a["state"] for a in arquivos} == {CollectionFileState.NO_MODEL.value}
        # Nenhum rótulo de máquina: nada foi classificado.
        assert all(a["label"] is None for a in arquivos)

    def test_coleta_de_solo_passa_pelo_pipeline(
        self,
        client: TestClient,
        platform_token: dict,
        demo: dict,
        store,
        session_factory: sessionmaker,
    ) -> None:
        coleta = cria_coleta(client, platform_token, demo["field_id"], kind="ground_image")
        for i in range(3):
            sobe_arquivo(
                client, platform_token, coleta["id"], f"folha_{i}.jpg", frame("Rust") * 3
            )
        client.post(f"/v1/admin/collections/{coleta['id']}/complete", headers=platform_token)
        roda_worker(session_factory)

        final = client.get(
            f"/v1/admin/collections/{coleta['id']}", headers=platform_token
        ).json()
        assert final["progress"]["processed"] == 3
        assert final["progress"]["no_model"] == 0
        assert final["progress"]["analyzed"] + final["progress"]["needs_review"] == 3

        arquivos = client.get(
            f"/v1/admin/collections/{coleta['id']}/files", headers=platform_token
        ).json()
        assert all(a["label"] == "Rust" for a in arquivos)
        assert all(a["observation_id"] for a in arquivos)

    def test_lote_grande_atravessa_varios_ciclos_do_worker(
        self,
        client: TestClient,
        platform_token: dict,
        demo: dict,
        store,
        session_factory: sessionmaker,
    ) -> None:
        """O administrador fecha a aba: o progresso anda a cada ciclo, não de 0 a 100."""
        coleta = cria_coleta(client, platform_token, demo["field_id"], kind="ground_image")
        total = 60
        declarados = client.post(
            f"/v1/admin/collections/{coleta['id']}/files",
            json={
                "files": [
                    {"filename": f"f{i:04d}.jpg", "size_bytes": len(frame("Healthy"))}
                    for i in range(total)
                ]
            },
            headers=platform_token,
        ).json()
        for arquivo in declarados:
            client.put(
                f"/v1/admin/collections/{coleta['id']}/files/{arquivo['id']}/chunk",
                params={"offset": 0},
                content=frame("Healthy"),
                headers=platform_token,
            )
        client.post(f"/v1/admin/collections/{coleta['id']}/complete", headers=platform_token)

        from valtexa import db

        # Um ciclo só não dá conta: o lote é de 25 arquivos por vez.
        with db.session_scope() as session:
            assert worker.process_collections(session) == 25
        parcial = client.get(
            f"/v1/admin/collections/{coleta['id']}", headers=platform_token
        ).json()
        assert 0 < parcial["progress"]["processed"] < total

        roda_worker(session_factory)
        final = client.get(
            f"/v1/admin/collections/{coleta['id']}", headers=platform_token
        ).json()
        assert final["progress"]["processed"] == total

        fila = client.get("/v1/admin/jobs", headers=platform_token).json()
        assert fila[0]["state"] == "done"
        assert fila[0]["progress_done"] == fila[0]["progress_total"] == total

    def test_upload_sem_nenhum_arquivo_guardado_falha_a_coleta(
        self, client: TestClient, platform_token: dict, demo: dict, store
    ) -> None:
        coleta = cria_coleta(client, platform_token, demo["field_id"])
        client.post(
            f"/v1/admin/collections/{coleta['id']}/files",
            json={"files": [{"filename": "a.jpg", "size_bytes": 999}]},
            headers=platform_token,
        )
        fechada = client.post(
            f"/v1/admin/collections/{coleta['id']}/complete", headers=platform_token
        ).json()
        assert fechada["state"] == CollectionState.FAILED.value
        assert fechada["progress"]["failed"] == 1


# ---------------------------------------------------------------------------
# Revisão, dataset e publicação
# ---------------------------------------------------------------------------


class TestRevisaoEDataset:
    @pytest.fixture
    def coleta_aerea_processada(
        self,
        client: TestClient,
        platform_token: dict,
        demo: dict,
        store,
        session_factory: sessionmaker,
    ) -> dict:
        # Sem consentimento SIM do cliente, revisão não vira amostra (brief, seção
        # 32 — ver test_consentimento.py). Aqui o cliente autorizou por termo.
        autorizado = client.put(
            f"/v1/admin/tenants/{demo['tenant_id']}/data-consent",
            json={"allowed": True, "document_ref": "Termo de dados nº 1/2026"},
            headers=platform_token,
        )
        assert autorizado.status_code == 200, autorizado.text
        coleta = cria_coleta(client, platform_token, demo["field_id"], kind="aerial_image")
        for i in range(2):
            sobe_arquivo(client, platform_token, coleta["id"], f"voo_{i}.jpg", frame("Healthy") * 3)
        client.post(f"/v1/admin/collections/{coleta['id']}/complete", headers=platform_token)
        roda_worker(session_factory)
        return coleta

    def test_agronomo_ve_a_coleta_sem_modelo_na_fila(
        self, client: TestClient, agronomist_token: dict, coleta_aerea_processada: dict
    ) -> None:
        fila = client.get("/v1/diagnoses?status=needs_review", headers=agronomist_token).json()
        assert len(fila) >= 2
        motivos = [item["rationale"] for item in fila if item.get("rationale")]
        assert any("Não há modelo treinado" in motivo for motivo in motivos)

    def test_veredito_do_agronomo_fecha_o_arquivo_e_alimenta_o_dataset(
        self,
        client: TestClient,
        agronomist_token: dict,
        platform_token: dict,
        coleta_aerea_processada: dict,
    ) -> None:
        """A única forma de uma imagem aérea ficar analisada hoje: uma pessoa."""
        coleta_id = coleta_aerea_processada["id"]
        arquivos = client.get(
            f"/v1/admin/collections/{coleta_id}/files", headers=platform_token
        ).json()

        for arquivo in arquivos:
            resposta = client.post(
                f"/v1/diagnoses/{arquivo['diagnosis_id']}/review",
                json={
                    "label": "Falha_de_stand",
                    "confirmed": True,
                    "notes": "Reboleira visível no canto norte.",
                },
                headers=agronomist_token,
            )
            assert resposta.status_code == 200, resposta.text

        final = client.get(f"/v1/admin/collections/{coleta_id}", headers=platform_token).json()
        assert final["progress"]["no_model"] == 0
        assert final["progress"]["analyzed"] == len(arquivos)
        assert final["state"] == CollectionState.ANALYZED.value

        datasets = client.get("/v1/admin/datasets", headers=platform_token).json()
        aereo = next(d for d in datasets if d["platform"] == "aerial")
        assert aereo["samples"] == len(arquivos)
        assert aereo["labels"]["Falha_de_stand"] == len(arquivos)
        # A máquina não opinou: é o dataset de um modelo que ainda não existe.
        assert aereo["sem_modelo"] == len(arquivos)

    def test_corte_do_dataset_e_congelado_com_a_lista_de_amostras(
        self,
        client: TestClient,
        agronomist_token: dict,
        platform_token: dict,
        coleta_aerea_processada: dict,
    ) -> None:
        coleta_id = coleta_aerea_processada["id"]
        arquivos = client.get(
            f"/v1/admin/collections/{coleta_id}/files", headers=platform_token
        ).json()
        for arquivo in arquivos:
            client.post(
                f"/v1/diagnoses/{arquivo['diagnosis_id']}/review",
                json={"label": "Falha_de_stand", "confirmed": True},
                headers=agronomist_token,
            )

        dataset_id = next(
            d["id"]
            for d in client.get("/v1/admin/datasets", headers=platform_token).json()
            if d["platform"] == "aerial"
        )
        corte = client.post(
            f"/v1/admin/datasets/{dataset_id}/versions",
            json={"version": "v1", "notes": "Primeiro corte da coleta aérea."},
            headers=platform_token,
        )
        assert corte.status_code == 201, corte.text
        assert corte.json()["sample_count"] == len(arquivos)
        assert corte.json()["label_counts"] == {"Falha_de_stand": len(arquivos)}

        repetido = client.post(
            f"/v1/admin/datasets/{dataset_id}/versions",
            json={"version": "v1"},
            headers=platform_token,
        )
        assert repetido.status_code == 422

    def test_cliente_so_ve_depois_de_publicada(
        self,
        client: TestClient,
        admin_token: dict,
        platform_token: dict,
        coleta_aerea_processada: dict,
        agronomist_token: dict,
    ) -> None:
        coleta_id = coleta_aerea_processada["id"]
        assert client.get("/v1/collections", headers=admin_token).json() == []
        assert client.get(f"/v1/collections/{coleta_id}", headers=admin_token).status_code == 404

        publicada = client.post(
            f"/v1/admin/collections/{coleta_id}/release", headers=platform_token
        )
        assert publicada.status_code == 200, publicada.text

        do_cliente = client.get("/v1/collections", headers=admin_token).json()
        assert len(do_cliente) == 1
        assert do_cliente[0]["code"] == coleta_aerea_processada["code"]
        # O cliente lê, com todas as letras, o que a plataforma não soube responder.
        assert "Não há modelo treinado" in do_cliente[0]["no_model_reason"]

        imagens = client.get(f"/v1/collections/{coleta_id}/files", headers=admin_token).json()
        assert len(imagens) == 2
        assert all(item["asset_id"] for item in imagens)


# ---------------------------------------------------------------------------
# Isolamento entre clientes
# ---------------------------------------------------------------------------


class TestIsolamento:
    def test_coleta_de_um_cliente_nao_aparece_no_outro(
        self,
        client: TestClient,
        platform_token: dict,
        demo: dict,
        session_factory: sessionmaker,
        store,
    ) -> None:
        """Mesmo para a equipe da ValTexa: ela trabalha dentro de um cliente por vez."""
        coleta = cria_coleta(client, platform_token, demo["field_id"])

        from valtexa.models import Tenant

        with session_factory() as session:
            outro = Tenant(name="Outro Produtor", slug="outro-produtor")
            session.add(outro)
            session.commit()
            outro_id = outro.id

        noutro_cliente = {**platform_token, "X-Tenant-Id": outro_id}
        assert client.get("/v1/admin/collections", headers=noutro_cliente).json() == []
        assert (
            client.get(
                f"/v1/admin/collections/{coleta['id']}", headers=noutro_cliente
            ).status_code
            == 404
        )

    def test_talhao_de_outro_cliente_nao_vira_coleta(
        self, client: TestClient, platform_token: dict, demo: dict, session_factory: sessionmaker
    ) -> None:
        from valtexa.models import Farm, Field, Tenant

        with session_factory() as session:
            outro = Tenant(name="Vizinho", slug="vizinho")
            session.add(outro)
            session.flush()
            fazenda = Farm(
                tenant_id=outro.id, name="Do vizinho", center_lat=-22.4, center_lon=-45.4
            )
            session.add(fazenda)
            session.flush()
            talhao = Field(
                tenant_id=outro.id, farm_id=fazenda.id, name="T1", crop="coffee", boundary=[]
            )
            session.add(talhao)
            session.commit()
            talhao_id = talhao.id

        resposta = client.post(
            "/v1/admin/collections",
            json={
                "field_id": talhao_id,
                "collected_on": HOJE.isoformat(),
                "source": "drone_third_party",
                "kind": "aerial_image",
            },
            headers=platform_token,
        )
        assert resposta.status_code == 404


# ---------------------------------------------------------------------------
# Catálogo de modelos
# ---------------------------------------------------------------------------


def test_catalogo_mostra_o_que_nao_esta_treinado(
    client: TestClient, platform_token: dict
) -> None:
    """O painel precisa dizer a verdade sobre o que a plataforma sabe fazer."""
    catalogo = {m["key"]: m for m in client.get(
        "/v1/admin/models/catalog", headers=platform_token
    ).json()}

    assert catalogo["leaf-foliar"]["trained"] is True
    assert catalogo["coffee-foliar"]["trained"] is True
    assert catalogo["aerial-canopy"]["trained"] is False
    assert catalogo["aerial-canopy"]["platform"] == "aerial"
    assert "coleta" in catalogo["aerial-canopy"]["caveat"]


def test_estado_da_coleta_nao_anda_para_tras(
    client: TestClient, platform_token: dict, demo: dict, store
) -> None:
    coleta = cria_coleta(client, platform_token, demo["field_id"])
    sobe_arquivo(client, platform_token, coleta["id"], "a.jpg", frame("Healthy") * 3)
    client.post(f"/v1/admin/collections/{coleta['id']}/complete", headers=platform_token)

    # Fechar duas vezes é inofensivo; declarar arquivo depois, não.
    segunda = client.post(
        f"/v1/admin/collections/{coleta['id']}/complete", headers=platform_token
    )
    assert segunda.status_code == 200

    tardio = client.post(
        f"/v1/admin/collections/{coleta['id']}/files",
        json={"files": [{"filename": "tarde.jpg", "size_bytes": 10}]},
        headers=platform_token,
    )
    assert tardio.status_code == 422


def test_publicar_antes_do_resultado_e_recusado(
    client: TestClient, platform_token: dict, demo: dict
) -> None:
    coleta = cria_coleta(client, platform_token, demo["field_id"])
    resposta = client.post(
        f"/v1/admin/collections/{coleta['id']}/release", headers=platform_token
    )
    assert resposta.status_code == 422
    assert "ainda não tem resultado" in resposta.json()["detail"]


def test_coleta_guarda_o_original_sem_sobrescrever(
    client: TestClient, platform_token: dict, demo: dict, store, session_factory: sessionmaker
) -> None:
    """Duas coletas com a mesma imagem: os bytes originais continuam legíveis."""
    primeira = cria_coleta(client, platform_token, demo["field_id"])
    segunda = cria_coleta(client, platform_token, demo["field_id"])
    dados = frame("Healthy") * 5

    sobe_arquivo(client, platform_token, primeira["id"], "igual.jpg", dados)
    sobe_arquivo(client, platform_token, segunda["id"], "igual.jpg", dados)

    with session_factory() as session:
        from valtexa.models import Asset, CollectionFile

        arquivos = session.query(CollectionFile).all()
        assert len(arquivos) == 2
        for arquivo in arquivos:
            ativo = session.get(Asset, arquivo.asset_id)
            assert store.read(ativo.storage_key) == dados


def test_coleta_e_auditada_de_ponta_a_ponta(
    client: TestClient,
    platform_token: dict,
    admin_token: dict,
    demo: dict,
    store,
    session_factory: sessionmaker,
) -> None:
    coleta = cria_coleta(client, platform_token, demo["field_id"], kind="ground_image")
    sobe_arquivo(client, platform_token, coleta["id"], "a.jpg", frame("Healthy") * 3)
    client.post(f"/v1/admin/collections/{coleta['id']}/complete", headers=platform_token)
    roda_worker(session_factory)
    client.post(f"/v1/admin/collections/{coleta['id']}/release", headers=platform_token)

    trilha = client.get("/v1/audit", headers=admin_token).json()
    acoes = {item["action"] for item in trilha}
    assert {"collection.created", "collection.upload_completed", "collection.released"} <= acoes

    criacao = next(i for i in trilha if i["action"] == "collection.created")
    assert criacao["actor_label"] == "equipe@valtexa.dev"
    assert criacao["payload"]["code"] == coleta["code"]


def test_coleta_sem_modelo_publica_evento_proprio(
    client: TestClient,
    platform_token: dict,
    demo: dict,
    store,
    session_factory: sessionmaker,
) -> None:
    coleta = cria_coleta(client, platform_token, demo["field_id"], kind="aerial_image")
    sobe_arquivo(client, platform_token, coleta["id"], "a.jpg", frame("Healthy") * 3)
    client.post(f"/v1/admin/collections/{coleta['id']}/complete", headers=platform_token)
    roda_worker(session_factory)

    with session_factory() as session:
        from valtexa.models import OutboxEvent

        nomes = {linha.name for linha in session.query(OutboxEvent).all()}
    assert "collection.no_model" in nomes
    assert "collection.queued" in nomes


def test_estados_da_coleta_seguem_o_ciclo_do_mvp(
    client: TestClient,
    platform_token: dict,
    demo: dict,
    store,
    session_factory: sessionmaker,
) -> None:
    """A ordem exigida: upload → fila → IA → resultado → revisão → cliente."""
    coleta = cria_coleta(client, platform_token, demo["field_id"], kind="ground_image")
    vistos = [coleta["state"]]

    sobe_arquivo(client, platform_token, coleta["id"], "a.jpg", frame("Healthy") * 3)
    vistos.append(
        client.get(f"/v1/admin/collections/{coleta['id']}", headers=platform_token).json()["state"]
    )
    vistos.append(
        client.post(
            f"/v1/admin/collections/{coleta['id']}/complete", headers=platform_token
        ).json()["state"]
    )
    roda_worker(session_factory)
    vistos.append(
        client.get(f"/v1/admin/collections/{coleta['id']}", headers=platform_token).json()["state"]
    )

    assert vistos[:3] == [
        CollectionState.DRAFT.value,
        CollectionState.UPLOADING.value,
        CollectionState.PROCESSING_QUEUED.value,
    ]
    assert vistos[3] in {
        CollectionState.ANALYZED.value,
        CollectionState.REVIEW_REQUIRED.value,
    }

    with session_factory() as session:
        linha = session.get(Collection, coleta["id"])
        assert linha.upload_completed_at is not None
        assert linha.processing_started_at is not None
        assert linha.processing_finished_at is not None
