"""Papéis da equipe da ValTexa e "entrar como cliente" (brief, seções 28 e 29).

O que estes testes seguram:

* cada papel de plataforma só alcança o que o trabalho dele pede (menor privilégio);
* a equipe não entra mais em cliente de que não é membro sem sessão de suporte —
  o acesso silencioso como ``admin`` acabou;
* a sessão de suporte tem motivo, prazo, é **somente leitura por padrão**, só
  escreve em modo assistido explícito, e cada requisição fica na auditoria do
  cliente com o interno como ator; a saída também.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from tests.conftest import DEMO_PASSWORD
from valtexa import db
from valtexa.models import AuditEntry, Membership, PlatformRole, Role, SupportSession, User
from valtexa.security.passwords import hash_password

FAZENDA = {"name": "Fazenda do Suporte", "center_lat": -22.41, "center_lon": -45.45}


def _abrir_suporte(
    client: TestClient, headers: dict, tenant_id: str, **extra
) -> tuple[dict, dict]:
    corpo = {"tenant_id": tenant_id, "reason": "Cliente relatou missão travada", **extra}
    resposta = client.post("/v1/platform/support-sessions", json=corpo, headers=headers)
    assert resposta.status_code == 201, resposta.text
    dados = resposta.json()
    return dados, {"Authorization": f"Bearer {dados['access_token']}"}


# ---------------------------------------------------------------------------
# Migração: is_platform_admin → platform_role
# ---------------------------------------------------------------------------


def test_migracao_leva_a_marca_antiga_para_superadmin_e_volta(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'papeis.db'}"
    config = db.alembic_config(url)
    command.upgrade(config, "0009")
    engine = create_engine(url)
    agora = datetime.now(UTC).isoformat()
    with engine.begin() as conn:
        for uid, email, flag in (("u1", "equipe@x.dev", 1), ("u2", "cliente@x.dev", 0)):
            conn.execute(
                text(
                    'INSERT INTO "user" (id, created_at, updated_at, email, full_name, '
                    "password_hash, is_active, is_platform_admin) VALUES "
                    "(:id, :t, :t, :e, 'N', 'h', 1, :f)"
                ),
                {"id": uid, "t": agora, "e": email, "f": flag},
            )
    command.upgrade(config, "0010")
    with engine.connect() as conn:
        papeis = dict(conn.execute(text('SELECT id, platform_role FROM "user"')).all())
    assert papeis == {"u1": "superadmin", "u2": None}

    command.downgrade(config, "0009")
    with engine.connect() as conn:
        marcas = dict(conn.execute(text('SELECT id, is_platform_admin FROM "user"')).all())
    assert marcas == {"u1": 1, "u2": 0}
    engine.dispose()


def test_a_propriedade_antiga_continua_respondendo(session: Session) -> None:
    """``is_platform_admin`` virou derivado do papel; gravar ``True`` é ``superadmin``."""
    user = User(email="a@b.dev", full_name="A", password_hash="h", is_platform_admin=True)
    assert user.platform_role is PlatformRole.SUPERADMIN
    user.platform_role = PlatformRole.COMERCIAL
    user.is_platform_admin = True
    assert user.platform_role is PlatformRole.COMERCIAL, "não promove papel restrito"
    user.is_platform_admin = False
    assert user.platform_role is None


# ---------------------------------------------------------------------------
# Menor privilégio entre os papéis de plataforma
# ---------------------------------------------------------------------------


class TestPapeisDePlataforma:
    @pytest.mark.parametrize(
        ("papel", "rota", "esperado"),
        [
            (PlatformRole.COMERCIAL, "/v1/admin/collections", 403),
            (PlatformRole.COMERCIAL, "/v1/admin/datasets", 403),
            (PlatformRole.COMERCIAL, "/v1/admin/tenants", 200),
            (PlatformRole.IA_DADOS, "/v1/admin/collections", 200),
            (PlatformRole.IA_DADOS, "/v1/admin/datasets", 200),
            (PlatformRole.IA_DADOS, "/v1/platform/users", 403),
            (PlatformRole.OPERACOES, "/v1/admin/datasets", 403),
            (PlatformRole.OPERACOES, "/v1/admin/models/catalog", 200),
            (PlatformRole.SUPORTE, "/v1/admin/datasets", 403),
            (PlatformRole.SUPORTE, "/v1/platform/audit", 200),
            (PlatformRole.SUPORTE, "/v1/platform/users", 403),
            (PlatformRole.SUPERADMIN, "/v1/platform/users", 200),
        ],
    )
    def test_cada_papel_so_alcanca_o_que_lhe_cabe(
        self, client: TestClient, equipe, demo: dict, papel, rota, esperado
    ) -> None:
        headers = {**equipe(papel), "X-Tenant-Id": demo["tenant_id"]}
        resposta = client.get(rota, headers=headers)
        assert resposta.status_code == esperado, (papel, rota, resposta.text)

    def test_so_comercial_e_superadmin_criam_cliente(
        self, client: TestClient, equipe
    ) -> None:
        novo = {"tenant": {"name": "Sítio Novo", "slug": "sitio-novo"}}
        assert (
            client.post("/v1/admin/tenants", json=novo, headers=equipe(PlatformRole.SUPORTE))
        ).status_code == 403
        assert (
            client.post("/v1/admin/tenants", json=novo, headers=equipe(PlatformRole.COMERCIAL))
        ).status_code == 201

    def test_comercial_nao_abre_sessao_de_suporte(
        self, client: TestClient, equipe, demo: dict
    ) -> None:
        resposta = client.post(
            "/v1/platform/support-sessions",
            json={"tenant_id": demo["tenant_id"], "reason": "Quero ver a lavoura dele"},
            headers=equipe(PlatformRole.COMERCIAL),
        )
        assert resposta.status_code == 403

    def test_superadmin_da_e_tira_papel_e_derruba_sessoes(
        self, client: TestClient, equipe, session: Session
    ) -> None:
        suporte = equipe(PlatformRole.SUPORTE)
        alvo = session.scalars(
            select(User).where(User.email == "suporte@equipe.valtexa.dev")
        ).one()
        resposta = client.put(
            f"/v1/platform/users/{alvo.id}/platform-role",
            json={"platform_role": "comercial"},
            headers=equipe(PlatformRole.SUPERADMIN),
        )
        assert resposta.status_code == 200, resposta.text
        assert resposta.json()["platform_role"] == "comercial"
        # O token antigo caiu junto com o papel antigo.
        assert client.get("/v1/platform/audit", headers=suporte).status_code == 401

    def test_ninguem_muda_o_proprio_papel(
        self, client: TestClient, equipe, session: Session
    ) -> None:
        headers = equipe(PlatformRole.SUPERADMIN)
        eu = session.scalars(
            select(User).where(User.email == "superadmin@equipe.valtexa.dev")
        ).one()
        resposta = client.put(
            f"/v1/platform/users/{eu.id}/platform-role",
            json={"platform_role": None},
            headers=headers,
        )
        assert resposta.status_code == 409

    def test_me_da_equipe_sem_associacao_mostra_so_capacidades_de_plataforma(
        self, client: TestClient, equipe, demo: dict
    ) -> None:
        headers = {**equipe(PlatformRole.IA_DADOS), "X-Tenant-Id": demo["tenant_id"]}
        eu = client.get("/v1/auth/me", headers=headers).json()
        assert eu["access"] == "plataforma"
        assert eu["platform_role"] == "ia_dados"
        assert "collection:manage" in eu["capabilities"]
        assert "farm:read" not in eu["capabilities"]


# ---------------------------------------------------------------------------
# Fim do acesso silencioso
# ---------------------------------------------------------------------------


class TestSemAcessoSilencioso:
    @pytest.mark.parametrize("papel", list(PlatformRole))
    def test_equipe_sem_associacao_nao_le_dado_de_cliente(
        self, client: TestClient, equipe, demo: dict, papel
    ) -> None:
        headers = {**equipe(papel), "X-Tenant-Id": demo["tenant_id"]}
        for rota in ("/v1/farms", "/v1/missions", "/v1/audit", "/v1/observations"):
            resposta = client.get(rota, headers=headers)
            assert resposta.status_code == 403, (papel, rota)
            assert "sessão de suporte" in resposta.json()["detail"]

    def test_equipe_sem_associacao_nao_escreve_em_cliente(
        self, client: TestClient, equipe, demo: dict
    ) -> None:
        headers = {**equipe(PlatformRole.SUPERADMIN), "X-Tenant-Id": demo["tenant_id"]}
        assert client.post("/v1/farms", json=FAZENDA, headers=headers).status_code == 403

    def test_lista_de_clientes_da_equipe_nao_promete_admin(
        self, client: TestClient, equipe, demo: dict
    ) -> None:
        lista = client.get("/v1/auth/memberships", headers=equipe(PlatformRole.SUPORTE)).json()
        demo_item = next(item for item in lista if item["tenant_id"] == demo["tenant_id"])
        assert demo_item["access"] == "plataforma"
        assert demo_item["role"] == "viewer"


# ---------------------------------------------------------------------------
# Sessão de suporte
# ---------------------------------------------------------------------------


class TestSessaoDeSuporte:
    def test_motivo_e_obrigatorio(self, client: TestClient, equipe, demo: dict) -> None:
        resposta = client.post(
            "/v1/platform/support-sessions",
            json={"tenant_id": demo["tenant_id"], "reason": "ver"},
            headers=equipe(PlatformRole.SUPORTE),
        )
        assert resposta.status_code == 422

    def test_prazo_tem_teto(self, client: TestClient, equipe, demo: dict) -> None:
        resposta = client.post(
            "/v1/platform/support-sessions",
            json={
                "tenant_id": demo["tenant_id"],
                "reason": "Sessão longa demais para valer",
                "duration_minutes": 24 * 60,
            },
            headers=equipe(PlatformRole.SUPORTE),
        )
        assert resposta.status_code == 422

    def test_leitura_por_padrao(
        self, client: TestClient, equipe, demo: dict, session: Session
    ) -> None:
        dados, token = _abrir_suporte(client, equipe(PlatformRole.SUPORTE), demo["tenant_id"])
        assert dados["session"]["mode"] == "leitura"

        assert client.get("/v1/farms", headers=token).status_code == 200
        assert client.get("/v1/audit", headers=token).status_code == 200

        negado = client.post("/v1/farms", json=FAZENDA, headers=token)
        assert negado.status_code == 403
        assert "modo leitura" in negado.json()["detail"]

        trilha = session.scalars(
            select(AuditEntry).where(
                AuditEntry.support_session_id == dados["session"]["id"]
            )
        ).all()
        acoes = [linha.action for linha in trilha]
        assert "support.session_started" in acoes
        assert acoes.count("support.request") >= 2
        assert "support.request_denied" in acoes
        assert all(linha.tenant_id == demo["tenant_id"] for linha in trilha)
        assert all(linha.actor_label.startswith("suporte@") for linha in trilha)

    def test_escrita_so_no_modo_assistido_e_auditada(
        self, client: TestClient, equipe, demo: dict, session: Session
    ) -> None:
        dados, token = _abrir_suporte(client, equipe(PlatformRole.SUPORTE), demo["tenant_id"])
        sid = dados["session"]["id"]

        sem_motivo = client.post(
            f"/v1/platform/support-sessions/{sid}/mode",
            json={"mode": "assistido", "reason": ""},
            headers=token,
        )
        assert sem_motivo.status_code == 422

        ligado = client.post(
            f"/v1/platform/support-sessions/{sid}/mode",
            json={"mode": "assistido", "reason": "Cliente pediu ajuda para cadastrar"},
            headers=token,
        )
        assert ligado.status_code == 200, ligado.text
        assert ligado.json()["mode"] == "assistido"

        criada = client.post("/v1/farms", json=FAZENDA, headers=token)
        assert criada.status_code == 201, criada.text

        registro = session.scalars(
            select(AuditEntry).where(
                AuditEntry.action == "farm.created",
                AuditEntry.subject_id == criada.json()["id"],
            )
        ).one()
        assert registro.support_session_id == sid
        assert registro.tenant_id == demo["tenant_id"]
        interno = session.scalars(
            select(User).where(User.email == "suporte@equipe.valtexa.dev")
        ).one()
        assert registro.actor_id == interno.id

    def test_modo_assistido_nao_aprova_aplicacao(
        self, client: TestClient, equipe, demo: dict
    ) -> None:
        """Aprovar pulverização segue exclusivo do agrônomo do cliente."""
        _, token = _abrir_suporte(
            client,
            equipe(PlatformRole.SUPORTE),
            demo["tenant_id"],
            assisted_reason="Ajudar a configurar a missão",
        )
        eu = client.get("/v1/auth/me", headers=token).json()
        assert eu["access"] == "suporte"
        assert eu["support_session"]["mode"] == "assistido"
        assert "mission:approve_application" not in eu["capabilities"]
        assert "tenant:manage" not in eu["capabilities"]

    def test_saida_registrada_e_token_cai(
        self, client: TestClient, equipe, demo: dict, session: Session
    ) -> None:
        dados, token = _abrir_suporte(client, equipe(PlatformRole.SUPORTE), demo["tenant_id"])
        sid = dados["session"]["id"]
        saida = client.post(f"/v1/platform/support-sessions/{sid}/end", headers=token)
        assert saida.status_code == 200
        assert saida.json()["is_open"] is False
        assert client.get("/v1/farms", headers=token).status_code == 401

        fim = session.scalars(
            select(AuditEntry).where(
                AuditEntry.action == "support.session_ended",
                AuditEntry.support_session_id == sid,
            )
        ).one()
        assert fim.reason == "saiu"
        assert fim.payload["requisicoes"] >= 0

    def test_sessao_vencida_e_encerrada_como_expirou(
        self, client: TestClient, equipe, demo: dict, session: Session
    ) -> None:
        dados, token = _abrir_suporte(client, equipe(PlatformRole.SUPORTE), demo["tenant_id"])
        linha = session.get(SupportSession, dados["session"]["id"])
        linha.expires_at = datetime.now(UTC) - timedelta(minutes=1)
        session.commit()

        assert client.get("/v1/farms", headers=token).status_code == 401
        session.expire_all()
        linha = session.get(SupportSession, dados["session"]["id"])
        assert linha.ended_reason == "expirou"

    def test_token_de_suporte_nao_atravessa_cliente(
        self, client: TestClient, equipe, demo: dict, platform_token: dict
    ) -> None:
        outro = client.post(
            "/v1/admin/tenants",
            json={"tenant": {"name": "Outro", "slug": "outro-cliente"}},
            headers=platform_token,
        ).json()["tenant"]["id"]
        _, token = _abrir_suporte(client, equipe(PlatformRole.SUPORTE), demo["tenant_id"])
        resposta = client.get("/v1/farms", headers={**token, "X-Tenant-Id": outro})
        assert resposta.status_code == 403

    def test_token_de_suporte_nao_vale_em_rota_de_plataforma(
        self, client: TestClient, equipe, demo: dict
    ) -> None:
        _, token = _abrir_suporte(client, equipe(PlatformRole.SUPERADMIN), demo["tenant_id"])
        assert client.get("/v1/admin/tenants", headers=token).status_code == 403
        assert client.get("/v1/auth/memberships", headers=token).status_code == 403

    def test_o_cliente_ve_quem_entrou(
        self, client: TestClient, equipe, demo: dict, admin_token: dict
    ) -> None:
        dados, token = _abrir_suporte(client, equipe(PlatformRole.SUPORTE), demo["tenant_id"])
        client.get("/v1/farms", headers=token)
        lista = client.get("/v1/tenants/current/support-sessions", headers=admin_token)
        assert lista.status_code == 200
        item = next(i for i in lista.json() if i["id"] == dados["session"]["id"])
        assert item["user_email"] == "suporte@equipe.valtexa.dev"
        assert item["reason"] == "Cliente relatou missão travada"
        assert item["request_count"] >= 1

        trilha = client.get("/v1/audit", headers=admin_token).json()
        assert any(
            e["action"] == "support.request" and e["support_session_id"] == dados["session"]["id"]
            for e in trilha
        )


# ---------------------------------------------------------------------------
# Escalada dentro do cliente
# ---------------------------------------------------------------------------


class TestDonoSoPorDono:
    def test_gestor_nao_cria_dono(self, client: TestClient, admin_token: dict) -> None:
        resposta = client.post(
            "/v1/users",
            json={
                "email": "novo-dono@x.dev",
                "full_name": "Novo Dono",
                "password": "senha-longa-123",
                "role": "owner",
            },
            headers=admin_token,
        )
        assert resposta.status_code == 403

    def test_gestor_nao_promove_a_dono(
        self, client: TestClient, admin_token: dict, demo: dict, session: Session
    ) -> None:
        agronomo = session.scalars(
            select(User).where(User.email == "agronomo@valtexa.dev")
        ).one()
        resposta = client.patch(
            f"/v1/users/{agronomo.id}", json={"role": "owner"}, headers=admin_token
        )
        assert resposta.status_code == 403

    def test_dono_cria_dono(
        self, client: TestClient, demo: dict, session: Session
    ) -> None:
        dono = User(
            email="dono@valtexa.dev",
            full_name="Dono",
            password_hash=hash_password(DEMO_PASSWORD),
        )
        session.add(dono)
        session.flush()
        session.add(Membership(tenant_id=demo["tenant_id"], user_id=dono.id, role=Role.OWNER))
        session.commit()
        login = client.post(
            "/v1/auth/login", json={"email": "dono@valtexa.dev", "password": DEMO_PASSWORD}
        ).json()
        headers = {"Authorization": f"Bearer {login['access_token']}"}
        resposta = client.post(
            "/v1/users",
            json={
                "email": "socio@x.dev",
                "full_name": "Sócio",
                "password": "senha-longa-123",
                "role": "owner",
            },
            headers=headers,
        )
        assert resposta.status_code == 201, resposta.text
