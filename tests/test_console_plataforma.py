"""Rotas que o console interno (/plataforma) consome — Fase 3.

``/platform/me``, ``/platform/tenants`` (plano, assinatura, uso, consentimento) e
``/platform/accounts`` (usuários globais e bloqueio). A escalada (papel de cliente
batendo nelas) é coberta também pelo teste gerado do OpenAPI.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from valtexa.models import AuditEntry, PlatformRole


def _demo(lista: list[dict], demo: dict) -> dict:
    return next(item for item in lista if item["id"] == demo["tenant_id"])


def _assina(client: TestClient, comercial: dict, demo: dict, **corpo) -> None:
    corpo.setdefault("plan_code", "profissional")
    resposta = client.put(
        f"/v1/admin/tenants/{demo['tenant_id']}/subscription", json=corpo, headers=comercial
    )
    assert resposta.status_code == 200, resposta.text


class TestQuemSou:
    def test_papel_e_capacidades(self, client: TestClient, equipe) -> None:
        comercial = equipe(PlatformRole.COMERCIAL)
        eu = client.get("/v1/platform/me", headers=comercial).json()
        assert eu["platform_role"] == "comercial"
        assert "platform:plan:manage" in eu["capabilities"]
        assert "platform:support:session" not in eu["capabilities"]
        assert eu["open_support_sessions"] == []

    def test_cliente_nao_passa(self, client: TestClient, admin_token: dict) -> None:
        assert client.get("/v1/platform/me", headers=admin_token).status_code == 403

    def test_sessao_aberta_aparece_para_retomar(
        self, client: TestClient, equipe, demo: dict
    ) -> None:
        suporte = equipe(PlatformRole.SUPORTE)
        aberta = client.post(
            "/v1/platform/support-sessions",
            json={"tenant_id": demo["tenant_id"], "reason": "Chamado 7: mapa vazio"},
            headers=suporte,
        )
        assert aberta.status_code == 201, aberta.text
        eu = client.get("/v1/platform/me", headers=suporte).json()
        assert [s["tenant_id"] for s in eu["open_support_sessions"]] == [demo["tenant_id"]]


class TestClientes:
    def test_linha_traz_plano_uso_e_consentimento(
        self, client: TestClient, equipe, demo: dict
    ) -> None:
        comercial = equipe(PlatformRole.COMERCIAL)
        sem_plano = _demo(client.get("/v1/platform/tenants", headers=comercial).json(), demo)
        assert sem_plano["plan_code"] is None and sem_plano["subscription_status"] is None

        _assina(client, comercial, demo)
        linha = _demo(client.get("/v1/platform/tenants", headers=comercial).json(), demo)
        assert linha["plan_code"] == "profissional"
        assert linha["subscription_status"] == "ativa"
        fazendas = next(item for item in linha["usage"] if item["resource"] == "farms")
        assert fazendas["used"] == 1
        assert linha["consent"]["decided"] in (True, False)
        assert linha["members"] >= 3

    def test_quem_nao_le_uso_recebe_a_lista_sem_numeros(
        self, client: TestClient, equipe, demo: dict
    ) -> None:
        _assina(client, equipe(PlatformRole.COMERCIAL), demo)
        operacoes = equipe(PlatformRole.OPERACOES)
        linha = _demo(client.get("/v1/platform/tenants", headers=operacoes).json(), demo)
        assert linha["usage"] == []
        assert linha["plan_name"]

    def test_aviso_de_80_por_cento(self, client: TestClient, equipe, demo: dict) -> None:
        comercial = equipe(PlatformRole.COMERCIAL)
        _assina(client, comercial, demo, plan_code="essencial", overrides={"max_farms": 1})
        linha = _demo(client.get("/v1/platform/tenants", headers=comercial).json(), demo)
        assert "fazendas" in linha["warnings"]

    def test_sessao_aberta_conta_no_cliente(
        self, client: TestClient, equipe, demo: dict
    ) -> None:
        suporte = equipe(PlatformRole.SUPORTE)
        client.post(
            "/v1/platform/support-sessions",
            json={"tenant_id": demo["tenant_id"], "reason": "Chamado 8: robô parado"},
            headers=suporte,
        )
        linha = _demo(client.get("/v1/platform/tenants", headers=suporte).json(), demo)
        assert linha["open_support_sessions"] == 1

    def test_busca(self, client: TestClient, equipe, demo: dict) -> None:
        comercial = equipe(PlatformRole.COMERCIAL)
        achados = client.get(
            "/v1/platform/tenants", params={"q": "nada-disso"}, headers=comercial
        ).json()
        assert achados == []


class TestUsuariosGlobais:
    def test_suporte_busca_qualquer_conta_com_vinculos(
        self, client: TestClient, equipe
    ) -> None:
        suporte = equipe(PlatformRole.SUPORTE)
        contas = client.get(
            "/v1/platform/accounts", params={"q": "agronomo"}, headers=suporte
        ).json()
        assert len(contas) == 1
        assert contas[0]["memberships"][0]["role"] == "agronomist"
        assert contas[0]["platform_role"] is None

    def test_so_a_equipe(self, client: TestClient, equipe) -> None:
        suporte = equipe(PlatformRole.SUPORTE)
        contas = client.get(
            "/v1/platform/accounts", params={"team_only": True}, headers=suporte
        ).json()
        assert contas and all(conta["platform_role"] for conta in contas)

    def test_comercial_nao_ve_usuarios(self, client: TestClient, equipe) -> None:
        comercial = equipe(PlatformRole.COMERCIAL)
        assert client.get("/v1/platform/accounts", headers=comercial).status_code == 403

    def test_superadmin_bloqueia_e_a_sessao_cai(
        self,
        client: TestClient,
        equipe,
        agronomist_token: dict,
        session: Session,
    ) -> None:
        superadmin = equipe(PlatformRole.SUPERADMIN)
        alvo = client.get(
            "/v1/platform/accounts", params={"q": "agronomo"}, headers=superadmin
        ).json()[0]
        resposta = client.put(
            f"/v1/platform/accounts/{alvo['id']}/active",
            json={"is_active": False, "reason": "desligado da cooperativa"},
            headers=superadmin,
        )
        assert resposta.status_code == 200
        assert resposta.json()["is_active"] is False
        assert client.get("/v1/farms", headers=agronomist_token).status_code == 401

        linha = session.scalars(
            select(AuditEntry).where(AuditEntry.action == "user.blocked")
        ).one()
        assert linha.reason == "desligado da cooperativa"

    def test_suporte_nao_bloqueia(self, client: TestClient, equipe) -> None:
        suporte = equipe(PlatformRole.SUPORTE)
        alvo = client.get(
            "/v1/platform/accounts", params={"q": "operador"}, headers=suporte
        ).json()[0]
        resposta = client.put(
            f"/v1/platform/accounts/{alvo['id']}/active",
            json={"is_active": False, "reason": "tentativa indevida"},
            headers=suporte,
        )
        assert resposta.status_code == 403

    def test_ninguem_bloqueia_a_si_mesmo(self, client: TestClient, equipe) -> None:
        superadmin = equipe(PlatformRole.SUPERADMIN)
        eu = client.get("/v1/platform/me", headers=superadmin).json()
        resposta = client.put(
            f"/v1/platform/accounts/{eu['id']}/active",
            json={"is_active": False, "reason": "engano total"},
            headers=superadmin,
        )
        assert resposta.status_code == 409


class TestCadastroDoClienteEmFoco:
    """As ferramentas internas (importar coleta, planejar) leem fazendas e talhões do
    cliente sem sessão de suporte — só cadastro, nenhum resultado agronômico."""

    def test_ia_dados_le_o_cadastro_do_cliente(
        self, client: TestClient, equipe, demo: dict
    ) -> None:
        ia = {**equipe(PlatformRole.IA_DADOS), "X-Tenant-Id": demo["tenant_id"]}
        fazendas = client.get("/v1/admin/farms", headers=ia)
        assert fazendas.status_code == 200, fazendas.text
        assert [f["id"] for f in fazendas.json()] == [demo["farm_id"]]
        talhoes = client.get("/v1/admin/fields", headers=ia).json()
        assert demo["field_id"] in {t["id"] for t in talhoes}

    def test_operacoes_tambem(self, client: TestClient, equipe, demo: dict) -> None:
        ops = {**equipe(PlatformRole.OPERACOES), "X-Tenant-Id": demo["tenant_id"]}
        assert client.get("/v1/admin/fields", headers=ops).status_code == 200

    def test_comercial_nao(self, client: TestClient, equipe, demo: dict) -> None:
        com = {**equipe(PlatformRole.COMERCIAL), "X-Tenant-Id": demo["tenant_id"]}
        assert client.get("/v1/admin/fields", headers=com).status_code == 403

    def test_sem_cliente_em_foco_e_400(self, client: TestClient, equipe) -> None:
        ia = equipe(PlatformRole.IA_DADOS)
        sem = {k: v for k, v in ia.items() if k != "X-Tenant-Id"}
        assert client.get("/v1/admin/farms", headers=sem).status_code == 400
