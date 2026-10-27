"""Model Registry e AI Platform (brief, seções 8, 9, 10, 22 e 34).

O que estes testes seguram:

* o catálogo que vivia duplicado em ``ai_pipeline.py`` virou semente do registry,
  e a resolução do modelo do talhão lê o registry (mesmas chaves da IA);
* o ciclo TREINAMENTO → VALIDAÇÃO → APROVADO → STAGING → PRODUÇÃO →
  DESCONTINUADO só anda pelas transições válidas, auditadas; aprovar exige IA &
  Dados ou superadmin e não pode ser quem registrou; publicar exige hash e
  descontinua a versão anterior;
* liberação por cliente: o talhão só escolhe entre as versões liberadas para ele;
* o robô só recebe versão em PRODUÇÃO do registry;
* o produtor vê linguagem operacional, nunca a métrica técnica;
* a saúde da IA mostra o que tem dado e diz "sem dado" do resto.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from tests.helpers import DeviceSession, provision, send_telemetry, upload_observation
from valtexa.models import AuditEntry, Field, ModelVersion, ModelVersionState, PlatformRole
from valtexa.services import model_registry

HASH_A = "a" * 64
HASH_B = "b" * 64


def _versao(client: TestClient, headers: dict, **extra) -> dict:
    corpo = {
        "model_key": "coffee-foliar",
        "version": "2.0.0",
        "name": "Doenças foliares do café v2",
        "platform": "ground",
        "crops": ["coffee", "café", "cafe"],
        "architecture": "EfficientNetV2-S",
        "dataset_ref": "coffee-leaf 2026-09 (CC BY 4.0)",
        "target_hardware": "Rover Edge V1",
        **extra,
    }
    resposta = client.post("/v1/platform/models", json=corpo, headers=headers)
    assert resposta.status_code == 201, resposta.text
    return resposta.json()


def _mover(client: TestClient, headers: dict, vid: str, para: str, motivo: str | None = None):
    return client.post(
        f"/v1/platform/models/{vid}/transition",
        json={"to": para, "reason": motivo},
        headers=headers,
    )


@pytest.fixture
def ia(equipe) -> dict:
    return equipe(PlatformRole.IA_DADOS)


@pytest.fixture
def chefe(equipe) -> dict:
    return equipe(PlatformRole.SUPERADMIN)


class TestCatalogoInicial:
    def test_semente_tem_o_catalogo_antigo(self, registry: Session) -> None:
        linhas = registry.scalars(select(ModelVersion)).all()
        assert len(linhas) == len(model_registry.CATALOGO_INICIAL) == 8
        estados = {linha.model_key: linha.state for linha in linhas}
        assert estados["aerial-canopy"] is ModelVersionState.TREINAMENTO
        assert estados["rover-understory"] is ModelVersionState.TREINAMENTO
        assert estados["banana-foliar"] is ModelVersionState.PRODUCAO

    def test_reinicio_nao_desfaz_o_que_a_equipe_mudou(self, registry: Session) -> None:
        linha = registry.scalars(
            select(ModelVersion).where(ModelVersion.model_key == "leaf-foliar")
        ).one()
        linha.state = ModelVersionState.DESCONTINUADO
        registry.commit()
        assert model_registry.sincronizar_catalogo(registry) == 0
        registry.refresh(linha)
        assert linha.state is ModelVersionState.DESCONTINUADO


class TestRegistro:
    def test_ia_dados_registra_em_treinamento(self, client: TestClient, ia: dict) -> None:
        versao = _versao(client, ia)
        assert versao["state"] == "treinamento"
        assert versao["state_label"] == "Treinamento"
        assert versao["registered_by"]
        assert versao["next_states"] == ["validacao", "descontinuado"]

    def test_versao_repetida_e_recusada(self, client: TestClient, ia: dict) -> None:
        resposta = client.post(
            "/v1/platform/models",
            json={"model_key": "coffee-foliar", "version": "1.0.0", "platform": "ground",
                  "crops": ["coffee"]},
            headers=ia,
        )
        assert resposta.status_code == 409
        assert "já está no registry" in resposta.json()["detail"]

    @pytest.mark.parametrize(
        "papel", [PlatformRole.OPERACOES, PlatformRole.COMERCIAL, PlatformRole.SUPORTE]
    )
    def test_outros_papeis_nao_registram(self, client: TestClient, equipe, papel) -> None:
        resposta = client.post(
            "/v1/platform/models",
            json={"model_key": "x-y", "version": "1", "platform": "ground", "crops": ["soja"]},
            headers=equipe(papel),
        )
        assert resposta.status_code == 403

    def test_operacoes_le_o_registry(self, client: TestClient, equipe, demo: dict) -> None:
        resposta = client.get("/v1/platform/models", headers=equipe(PlatformRole.OPERACOES))
        assert resposta.status_code == 200
        assert {m["model_key"] for m in resposta.json()} >= {"coffee-foliar", "aerial-canopy"}


class TestCicloDeVida:
    def test_caminho_completo_publica_e_descontinua_a_anterior(
        self,
        client: TestClient,
        ia: dict,
        chefe: dict,
        session: Session,
        demo: dict,
        admin_token: dict,
    ) -> None:
        versao = _versao(client, ia, metrics={"precision": 0.91, "recall": 0.88, "f1": 0.895})
        vid = versao["id"]
        assert _mover(client, ia, vid, "validacao").status_code == 200

        # Quem registrou não aprova.
        proprio = _mover(client, ia, vid, "aprovado")
        assert proprio.status_code == 403
        assert "Quem registrou" in proprio.json()["detail"]

        aprovado = _mover(client, chefe, vid, "aprovado")
        assert aprovado.status_code == 200, aprovado.text
        assert aprovado.json()[0]["approved_by"]

        assert _mover(client, ia, vid, "staging").status_code == 200
        sem_hash = _mover(client, ia, vid, "producao")
        assert sem_hash.status_code == 409
        assert "hash" in sem_hash.json()["detail"]

        # Depois de aprovada, artefato não se edita: precisa ser registrado antes.
        tarde = client.patch(
            f"/v1/platform/models/{vid}", json={"original_artifact_sha256": HASH_A}, headers=ia
        )
        assert tarde.status_code == 409

        linha = session.get(ModelVersion, vid)
        linha.original_artifact_sha256 = HASH_A  # como se tivesse vindo no registro
        session.commit()
        publicado = _mover(client, ia, vid, "producao")
        assert publicado.status_code == 200, publicado.text
        afetadas = {v["version"]: v for v in publicado.json()}
        assert afetadas["2.0.0"]["state"] == "producao"
        assert afetadas["2.0.0"]["promoted_at"] is not None
        assert afetadas["1.0.0"]["state"] == "descontinuado"

        em_producao = client.get(
            "/v1/platform/models",
            params={"model_key": "coffee-foliar", "state": "producao"},
            headers=ia,
        ).json()
        assert [v["version"] for v in em_producao] == ["2.0.0"]

        detalhe = client.get(f"/v1/platform/models/{vid}", headers=ia).json()
        caminho = [(h["from_state"], h["to_state"]) for h in detalhe["history"]]
        assert caminho == [
            (None, "treinamento"),
            ("treinamento", "validacao"),
            ("validacao", "aprovado"),
            ("aprovado", "staging"),
            ("staging", "producao"),
        ]
        assert detalhe["history"][2]["actor_label"] == "superadmin@equipe.valtexa.dev"

        # O talhão de café segue em coffee-foliar (mesma chave que a IA conhece), agora 2.0.0.
        campos = client.get(f"/v1/farms/{demo['farm_id']}/fields", headers=admin_token).json()
        assert campos[0]["ai_model_in_use"] == "coffee-foliar"
        opcoes = client.get(f"/v1/fields/{demo['field_id']}/ai-models", headers=admin_token)
        assert [m["version"] for m in opcoes.json()] == ["2.0.0"]

    def test_salto_invalido_e_recusado(self, client: TestClient, ia: dict) -> None:
        vid = _versao(client, ia)["id"]
        resposta = _mover(client, ia, vid, "producao")
        assert resposta.status_code == 409
        assert "não é uma transição válida" in resposta.json()["detail"]

    def test_reprovar_exige_motivo(self, client: TestClient, ia: dict) -> None:
        vid = _versao(client, ia, metrics={"f1": 0.5})["id"]
        _mover(client, ia, vid, "validacao")
        assert _mover(client, ia, vid, "treinamento").status_code == 409
        voltou = _mover(client, ia, vid, "treinamento", "F1 abaixo do mínimo")
        assert voltou.status_code == 200

    def test_aprovar_sem_metrica_e_recusado(
        self, client: TestClient, ia: dict, chefe: dict
    ) -> None:
        vid = _versao(client, ia)["id"]
        _mover(client, ia, vid, "validacao")
        resposta = _mover(client, chefe, vid, "aprovado")
        assert resposta.status_code == 409
        assert "métricas" in resposta.json()["detail"]

    def test_transicao_fica_na_auditoria(
        self, client: TestClient, ia: dict, session: Session
    ) -> None:
        vid = _versao(client, ia)["id"]
        _mover(client, ia, vid, "descontinuado", "registro de teste")
        entrada = session.scalars(
            select(AuditEntry).where(
                AuditEntry.subject_id == vid, AuditEntry.action == "model_version.transition"
            )
        ).one()
        assert (entrada.old_state, entrada.new_state) == ("treinamento", "descontinuado")
        assert entrada.reason == "registro de teste"
        assert entrada.model_version == "coffee-foliar@2.0.0"
        assert entrada.actor_label == "ia_dados@equipe.valtexa.dev"

    def test_nao_descontinua_o_unico_modelo_que_um_talhao_escolheu(
        self, client: TestClient, ia: dict, admin_token: dict, demo: dict, session: Session
    ) -> None:
        client.put(
            f"/v1/fields/{demo['field_id']}/ai-model",
            json={"ai_model": "coffee-foliar"},
            headers=admin_token,
        )
        linha = session.scalars(
            select(ModelVersion).where(ModelVersion.model_key == "coffee-foliar")
        ).one()
        resposta = _mover(client, ia, linha.id, "descontinuado", "teste")
        assert resposta.status_code == 409
        assert "talhão" in resposta.json()["detail"]


class TestPipelineLeORegistry:
    def test_descontinuar_tira_o_modelo_do_talhao(
        self, client: TestClient, ia: dict, admin_token: dict, demo: dict, session: Session
    ) -> None:
        linha = session.scalars(
            select(ModelVersion).where(ModelVersion.model_key == "coffee-foliar")
        ).one()
        antes = client.get(f"/v1/farms/{demo['farm_id']}/fields", headers=admin_token).json()
        assert antes[0]["ai_model_in_use"] == "coffee-foliar"

        assert _mover(client, ia, linha.id, "descontinuado", "teste").status_code == 200
        depois = client.get(f"/v1/farms/{demo['farm_id']}/fields", headers=admin_token).json()
        assert depois[0]["ai_model_in_use"] is None

    def test_catalogo_admin_vem_do_registry(self, client: TestClient, ia: dict) -> None:
        catalogo = {m["key"]: m for m in client.get("/v1/admin/models/catalog", headers=ia).json()}
        assert catalogo["aerial-canopy"]["trained"] is False
        assert catalogo["banana-foliar"]["trained"] is True
        assert "café" in catalogo["coffee-foliar"]["crops"]


class TestLiberacaoPorCliente:
    def _restringe(self, session: Session, chave: str) -> None:
        linha = session.scalars(
            select(ModelVersion).where(ModelVersion.model_key == chave)
        ).one()
        linha.release_scope = "clientes"
        session.commit()

    def test_talhao_so_escolhe_entre_os_liberados(
        self,
        client: TestClient,
        ia: dict,
        admin_token: dict,
        demo: dict,
        session: Session,
    ) -> None:
        talhao = session.get(Field, demo["field_id"])
        talhao.crop = "banana"
        session.commit()
        self._restringe(session, "banana-foliar-cc")
        url = f"/v1/fields/{demo['field_id']}/ai-models"

        opcoes = [m["key"] for m in client.get(url, headers=admin_token).json()]
        assert opcoes == ["banana-foliar"]
        escolha = client.put(
            f"/v1/fields/{demo['field_id']}/ai-model",
            json={"ai_model": "banana-foliar-cc"},
            headers=admin_token,
        )
        assert escolha.status_code == 422

        liberada = client.post(
            "/v1/platform/model-releases",
            json={"tenant_id": demo["tenant_id"], "model_key": "banana-foliar-cc",
                  "reason": "contrato comercial assinado"},
            headers=ia,
        )
        assert liberada.status_code == 201, liberada.text
        de_novo = client.post(
            "/v1/platform/model-releases",
            json={"tenant_id": demo["tenant_id"], "model_key": "banana-foliar-cc"},
            headers=ia,
        )
        assert de_novo.json()["id"] == liberada.json()["id"]  # idempotente

        opcoes = [m["key"] for m in client.get(url, headers=admin_token).json()]
        assert opcoes == ["banana-foliar", "banana-foliar-cc"]
        assert client.put(
            f"/v1/fields/{demo['field_id']}/ai-model",
            json={"ai_model": "banana-foliar-cc"},
            headers=admin_token,
        ).status_code == 200

        revogada = client.post(
            f"/v1/platform/model-releases/{liberada.json()['id']}/revoke", headers=ia
        )
        assert revogada.json()["revoked_at"] is not None
        opcoes = [m["key"] for m in client.get(url, headers=admin_token).json()]
        assert opcoes == ["banana-foliar"]
        # Revogada, a escolha antiga do talhão deixa de atender — e o talhão diz isso.
        campos = client.get(f"/v1/farms/{demo['farm_id']}/fields", headers=admin_token).json()
        assert campos[0]["ai_model_in_use"] is None

        historico = client.get(
            "/v1/platform/model-releases",
            params={"tenant_id": demo["tenant_id"], "include_revoked": True},
            headers=ia,
        ).json()
        assert len(historico) == 1 and historico[0]["reason"] == "contrato comercial assinado"
        trilha = session.scalars(
            select(AuditEntry.action).where(AuditEntry.tenant_id == demo["tenant_id"])
        ).all()
        assert {"model.released", "model.release_revoked"} <= set(trilha)

    def test_comercial_nao_libera(self, client: TestClient, equipe, demo: dict) -> None:
        resposta = client.post(
            "/v1/platform/model-releases",
            json={"tenant_id": demo["tenant_id"], "model_key": "banana-foliar-cc"},
            headers=equipe(PlatformRole.COMERCIAL),
        )
        assert resposta.status_code == 403


class TestProdutorVeLinguagemOperacional:
    def test_seletor_sem_metrica_tecnica(
        self, client: TestClient, admin_token: dict, demo: dict, session: Session
    ) -> None:
        talhao = session.get(Field, demo["field_id"])
        talhao.crop = "citros"
        session.commit()
        resposta = client.get(f"/v1/fields/{demo['field_id']}/ai-models", headers=admin_token)
        assert resposta.status_code == 200
        texto = resposta.text
        for proibido in ("field_accuracy", "0.969", "metrics", "sha256", "flops", "dataset"):
            assert proibido not in texto
        campo = resposta.json()[0]
        assert campo["key"] == "citrus-foliar"
        assert campo["field_performance"].startswith("alto")
        assert campo["version"] == "1.0.0"

    def test_cliente_nao_alcanca_o_registry(self, client: TestClient, admin_token: dict) -> None:
        assert client.get("/v1/platform/models", headers=admin_token).status_code == 403
        assert client.get("/v1/platform/ai-health", headers=admin_token).status_code == 403


class TestRoboSoRecebeOQueEstaNoRegistry:
    @pytest.fixture
    def rover(self, client: TestClient, admin_token: dict, demo: dict) -> DeviceSession:
        return provision(client, admin_token, "ROVER_SCOUT_V1", "REG-R1", demo["farm_id"])

    def test_designado_em_producao_sem_artefato_nao_carrega(
        self, rover: DeviceSession, demo: dict
    ) -> None:
        resposta = rover.request("GET", "/v1/device/models")
        assert resposta.status_code == 200, resposta.text
        [item] = resposta.json()
        assert item["field_id"] == demo["field_id"]
        assert (item["model_key"], item["version"], item["state"]) == (
            "coffee-foliar", "1.0.0", "producao",
        )
        # O catálogo inicial não tem hash: o robô recebe nulo e não carrega nada.
        assert item["artifact_sha256"] is None
        assert item["artifact_kind"] is None
        assert item["extras_manifest_sha256"] is None

    def test_versao_nova_so_chega_ao_robo_em_producao(
        self,
        client: TestClient,
        rover: DeviceSession,
        ia: dict,
        chefe: dict,
    ) -> None:
        vid = _versao(
            client,
            ia,
            metrics={"f1": 0.9},
            original_artifact_uri="s3://modelos/coffee-foliar/2.0.0/original.keras",
            original_artifact_sha256=HASH_A,
        )["id"]
        # Parte 5: o otimizado só entra por uma rodada de otimização aceita
        # (benchmark original e otimizado, seção 23) — test_dnaty_registry.py.
        from tests.test_dnaty_registry import benchmark, otimizar, relatorio

        corpo = relatorio(benchmark(HASH_B, size_bytes=30_000_000, latency_ms_p50=20.0))
        corpo["otimizado"]["artifact_uri"] = "s3://modelos/coffee-foliar/2.0.0/dnaty.onnx"
        assert otimizar(client, ia, vid, corpo).json()["accepted"]
        _mover(client, ia, vid, "validacao")
        _mover(client, chefe, vid, "aprovado")
        _mover(client, ia, vid, "staging")
        em_staging = rover.request("GET", "/v1/device/models").json()[0]
        assert em_staging["version"] == "1.0.0"  # staging não vai para o robô

        _mover(client, ia, vid, "producao")
        item = rover.request("GET", "/v1/device/models").json()[0]
        assert item["version"] == "2.0.0"
        assert item["artifact_kind"] == "otimizado"
        assert item["artifact_sha256"] == HASH_B
        assert item["dnaty_version"] == "2.2.1"
        assert item["artifact_uri"].endswith("dnaty.onnx")

    def test_manifesto_dos_extras_chega_ao_robo_e_trava_na_aprovacao(
        self,
        client: TestClient,
        rover: DeviceSession,
        ia: dict,
        chefe: dict,
    ) -> None:
        manifesto = "c" * 64
        vid = _versao(
            client,
            ia,
            metrics={"f1": 0.9},
            original_artifact_uri="s3://modelos/coffee-foliar/2.0.0/original.onnx",
            original_artifact_sha256=HASH_A,
            extras_manifest_sha256=manifesto,
        )["id"]
        for headers, estado in ((ia, "validacao"), (chefe, "aprovado")):
            assert _mover(client, headers, vid, estado).status_code == 200
        # Trocar o manifesto depois da aprovação seria aprovar um perfil e publicar outro.
        troca = client.patch(
            f"/v1/platform/models/{vid}", json={"extras_manifest_sha256": "d" * 64}, headers=ia
        )
        assert troca.status_code == 409, troca.text
        for estado in ("staging", "producao"):
            assert _mover(client, ia, vid, estado).status_code == 200
        item = rover.request("GET", "/v1/device/models").json()[0]
        assert (item["version"], item["artifact_sha256"]) == ("2.0.0", HASH_A)
        assert item["extras_manifest_sha256"] == manifesto

    def test_manifesto_invalido_e_recusado(self, client: TestClient, ia: dict) -> None:
        resposta = client.post(
            "/v1/platform/models",
            json={"model_key": "coffee-foliar", "version": "9.0.0", "platform": "ground",
                  "crops": ["café"], "extras_manifest_sha256": "nao-e-hash"},
            headers=ia,
        )
        assert resposta.status_code == 422

    def test_robo_de_outro_cliente_nao_ve_talhao_alheio(
        self, client: TestClient, equipe, demo: dict, session_factory
    ) -> None:
        from tests.test_isolamento_openapi import _login
        from valtexa.models import Membership, Role, Tenant, User
        from valtexa.security.passwords import hash_password

        with session_factory() as sessao:
            tenant = Tenant(name="Outro", slug="outro-registry")
            dono = User(email="dono@outro.dev", full_name="D", password_hash=hash_password(
                "valtexa-demo-2026"))
            sessao.add_all([tenant, dono])
            sessao.flush()
            sessao.add(Membership(tenant_id=tenant.id, user_id=dono.id, role=Role.OWNER))
            sessao.commit()
        robo = provision(client, _login(client, "dono@outro.dev"), "ROVER_SCOUT_V1", "OUT-1")
        assert robo.request("GET", "/v1/device/models").json() == []


class TestSaudeDaIA:
    def test_mostra_o_medido_e_marca_simulacao(
        self,
        client: TestClient,
        admin_token: dict,
        demo: dict,
        ia: dict,
    ) -> None:
        robo = provision(client, admin_token, "ROVER_SCOUT_V1", "SAUDE-1", demo["farm_id"])
        send_telemetry(robo, battery_percent=90.0)
        assert upload_observation(robo, demo["field_id"]).status_code in (200, 201)
        robo.request(
            "POST", "/v1/device/session",
            json_body={"model_key": "leaf-foliar", "model_version": "1.0.0"},
        )

        saude = client.get("/v1/platform/ai-health", headers=ia)
        assert saude.status_code == 200, saude.text
        corpo = saude.json()
        assert {m["model_key"] for m in corpo["active_models"]} >= {"coffee-foliar"}
        assert corpo["models"], "a observação simulada gerou detecções"
        assert all(m["simulated"] for m in corpo["models"])
        assert sum(m["inferences"] for m in corpo["models"]) >= 1
        assert corpo["rovers_divergent"] == 1
        assert set(corpo["no_data"]) >= {"drift", "incidentes"}

    def test_sem_deteccao_nao_inventa(self, client: TestClient, ia: dict, demo: dict) -> None:
        corpo = client.get("/v1/platform/ai-health", headers=ia).json()
        assert corpo["models"] == []
        assert corpo["rovers_reporting"] == 0


def test_migracao_0017_leva_os_estados_e_volta(tmp_path) -> None:
    from datetime import UTC, datetime

    from alembic import command
    from sqlalchemy import create_engine, text

    from valtexa import db

    url = f"sqlite:///{tmp_path / 'r.db'}"
    cfg = db.alembic_config(url)
    command.upgrade(cfg, "0016")
    engine = create_engine(url)
    agora = datetime.now(UTC).isoformat()
    antigos = {"v1": "registered", "v2": "trained", "v3": "shadow", "v4": "production",
               "v5": "retired"}
    with engine.begin() as conn:
        for vid, estado in antigos.items():
            conn.execute(
                text(
                    "INSERT INTO model_version (id, created_at, updated_at, model_key, version, "
                    "state, platform, metrics) VALUES (:id, :t, :t, 'm', :id, :s, 'ground', '{}')"
                ),
                {"id": vid, "t": agora, "s": estado},
            )
    command.upgrade(cfg, "0017")
    with engine.connect() as conn:
        novos = dict(conn.execute(text("SELECT id, state FROM model_version")).all())
        escopo = conn.execute(text("SELECT DISTINCT release_scope FROM model_version")).scalar()
    assert novos == {"v1": "treinamento", "v2": "validacao", "v3": "staging",
                     "v4": "producao", "v5": "descontinuado"}
    assert escopo == "todos"
    command.downgrade(cfg, "0016")
    with engine.connect() as conn:
        voltou = dict(conn.execute(text("SELECT id, state FROM model_version")).all())
    assert voltou == {"v1": "training", "v2": "trained", "v3": "shadow", "v4": "production",
                      "v5": "retired"}
    engine.dispose()
