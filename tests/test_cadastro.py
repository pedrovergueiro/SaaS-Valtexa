"""Cadastro de cliente e as contas da equipe da ValTexa.

Duas coisas que parecem administrativas e não são: quem entra em qual cliente é
a fronteira de multilocação, e um cadastro que grava pela metade deixa cliente
órfão no banco. Os dois casos têm teste aqui.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from valtexa.models import Farm, Field, Tenant, User
from valtexa.seed import PLATFORM_TEAM, seed_platform_team

CLIENTE = {
    "name": "Fazenda São João Agropecuária Ltda",
    "slug": "sao-joao",
    "document": "12.345.678/0001-90",
    "contact_name": "João da Silva",
    "email": "joao@saojoao.com.br",
    "phone": "(35) 99999-0000",
    "address": "Rodovia MG-290, km 12",
    "city": "Pouso Alegre",
    "state": "MG",
    "postal_code": "37550-000",
    "contracted_service": "Monitoramento com rover + coleta aérea",
}

PROPRIEDADE = {
    "name": "Sítio São João",
    "center_lat": -21.9040,
    "center_lon": -45.8620,
    "area_ha": 120.0,
}

TALHAO = {
    "name": "Talhão 1 — Café",
    "crop": "coffee",
    "variety": "Mundo Novo",
    "row_spacing_m": 3.5,
    "boundary": [
        [-45.8660, -21.9060],
        [-45.8590, -21.9060],
        [-45.8590, -21.9010],
        [-45.8660, -21.9010],
    ],
}


class TestQuemPodeCadastrar:
    def test_cliente_nao_cadastra_cliente(
        self, client: TestClient, admin_token: dict, demo: dict
    ) -> None:
        """O administrador de uma fazenda não cria outra empresa na plataforma."""
        resposta = client.post(
            "/v1/admin/tenants", json={"tenant": CLIENTE}, headers=admin_token
        )
        assert resposta.status_code == 403

    def test_apelido_repetido_e_recusado(
        self, client: TestClient, platform_token: dict
    ) -> None:
        """O apelido é a identidade pública: dois clientes com o mesmo se
        atropelariam em link e em token."""
        client.post("/v1/admin/tenants", json={"tenant": CLIENTE}, headers=platform_token)
        segunda = client.post(
            "/v1/admin/tenants",
            json={"tenant": {**CLIENTE, "name": "Outra Empresa"}},
            headers=platform_token,
        )
        assert segunda.status_code == 409
        assert "sao-joao" in segunda.json()["detail"]


class TestCadastroCompleto:
    def test_grava_cliente_propriedade_e_talhao(
        self, client: TestClient, platform_token: dict
    ) -> None:
        resposta = client.post(
            "/v1/admin/tenants",
            json={
                "tenant": CLIENTE,
                "plan_code": "profissional",
                "farm": PROPRIEDADE,
                "field": TALHAO,
            },
            headers=platform_token,
        )
        assert resposta.status_code == 201, resposta.text
        corpo = resposta.json()

        assert corpo["tenant"]["document"] == CLIENTE["document"]
        assert corpo["tenant"]["city"] == "Pouso Alegre"
        assert corpo["tenant"]["contracted_service"].startswith("Monitoramento")
        assert corpo["tenant"]["plan_code"] == "profissional"
        assert corpo["farm_id"] and corpo["field_id"]
        assert corpo["warnings"] == []

    def test_sem_plano_o_cliente_nasce_no_piloto_com_aviso(
        self, client: TestClient, platform_token: dict
    ) -> None:
        corpo = client.post(
            "/v1/admin/tenants", json={"tenant": CLIENTE}, headers=platform_token
        ).json()
        assert corpo["tenant"]["plan_code"] == "piloto"
        assert any("Piloto" in aviso for aviso in corpo["warnings"])

    def test_a_area_do_talhao_sai_do_contorno_e_nao_do_formulario(
        self, client: TestClient, platform_token: dict, session: Session
    ) -> None:
        """Área digitada erra; área medida do polígono, não. É a mesma conta que
        a cerca virtual usa, então as duas nunca discordam."""
        corpo = client.post(
            "/v1/admin/tenants",
            json={"tenant": CLIENTE, "farm": PROPRIEDADE, "field": TALHAO},
            headers=platform_token,
        ).json()

        campo = session.get(Field, corpo["field_id"])
        assert campo is not None
        assert campo.area_ha == pytest.approx(41.0, abs=5.0)
        assert len(campo.boundary) == 4

    def test_so_o_cliente_tambem_vale(
        self, client: TestClient, platform_token: dict
    ) -> None:
        """O cadastro começa numa ligação. Exigir talhão travaria o atendimento."""
        resposta = client.post(
            "/v1/admin/tenants", json={"tenant": CLIENTE}, headers=platform_token
        )
        assert resposta.status_code == 201
        corpo = resposta.json()
        assert corpo["farm_id"] is None
        assert corpo["tenant"]["farms"] == 0

    def test_talhao_sem_contorno_avisa_em_vez_de_recusar(
        self, client: TestClient, platform_token: dict
    ) -> None:
        """O contorno se desenha no editor, com satélite na frente — não ao telefone."""
        corpo = client.post(
            "/v1/admin/tenants",
            json={
                "tenant": CLIENTE,
                "farm": PROPRIEDADE,
                "field": {**TALHAO, "boundary": []},
            },
            headers=platform_token,
        ).json()

        assert corpo["field_id"] is not None
        assert any("sem contorno" in aviso for aviso in corpo["warnings"])

    def test_talhao_sem_propriedade_nao_fica_solto(
        self, client: TestClient, platform_token: dict
    ) -> None:
        corpo = client.post(
            "/v1/admin/tenants",
            json={"tenant": CLIENTE, "field": TALHAO},
            headers=platform_token,
        ).json()
        assert corpo["field_id"] is None
        assert any("ignorado" in aviso for aviso in corpo["warnings"])

    def test_contorno_invalido_nao_grava_cliente_nenhum(
        self, client: TestClient, platform_token: dict, session: Session
    ) -> None:
        """A transação é uma só: ou entra tudo, ou nada.

        Sem isso, um erro no talhão deixaria cliente e propriedade criados pela
        metade, e alguém teria que limpá-los à mão.
        """
        resposta = client.post(
            "/v1/admin/tenants",
            json={
                "tenant": CLIENTE,
                "farm": PROPRIEDADE,
                "field": {**TALHAO, "boundary": [[-45.86, -21.90], [-45.85, -21.90]]},
            },
            headers=platform_token,
        )
        assert resposta.status_code == 422

        assert session.scalars(select(Tenant).where(Tenant.slug == "sao-joao")).first() is None
        assert session.scalars(select(Farm).where(Farm.name == "Sítio São João")).first() is None

    def test_o_cadastro_fica_na_auditoria_com_quem_o_fez(
        self, client: TestClient, platform_token: dict
    ) -> None:
        corpo = client.post(
            "/v1/admin/tenants",
            json={"tenant": CLIENTE, "farm": PROPRIEDADE},
            headers=platform_token,
        ).json()

        # A equipe lê a trilha do cliente pela auditoria da plataforma: sem ser
        # membro, o /v1/audit do cliente exige sessão de suporte.
        trilha = client.get(
            "/v1/platform/audit",
            params={"tenant_id": corpo["tenant"]["id"]},
            headers=platform_token,
        ).json()
        registro = next(item for item in trilha if item["action"] == "tenant.onboarded")
        assert registro["actor_label"] == "equipe@valtexa.dev"
        assert registro["payload"]["document"] == CLIENTE["document"]


class TestAlteracao:
    def test_atualiza_contato_e_guarda_o_antes(
        self, client: TestClient, platform_token: dict
    ) -> None:
        criado = client.post(
            "/v1/admin/tenants", json={"tenant": CLIENTE}, headers=platform_token
        ).json()
        tenant_id = criado["tenant"]["id"]

        resposta = client.patch(
            f"/v1/admin/tenants/{tenant_id}",
            json={"phone": "(35) 98888-1111"},
            headers=platform_token,
        )
        assert resposta.status_code == 200
        assert resposta.json()["phone"] == "(35) 98888-1111"
        # O que não foi enviado não é apagado.
        assert resposta.json()["city"] == "Pouso Alegre"

        trilha = client.get(
            "/v1/platform/audit", params={"tenant_id": tenant_id}, headers=platform_token
        ).json()
        registro = next(item for item in trilha if item["action"] == "tenant.updated")
        assert registro["payload"]["antes"]["phone"] == CLIENTE["phone"]

    def test_cliente_inexistente_e_404(
        self, client: TestClient, platform_token: dict
    ) -> None:
        resposta = client.patch(
            "/v1/admin/tenants/nao-existe", json={"phone": "x"}, headers=platform_token
        )
        assert resposta.status_code == 404


class TestListagem:
    def test_a_lista_mostra_o_tamanho_da_operacao(
        self, client: TestClient, platform_token: dict
    ) -> None:
        """Um nome sozinho não diz se o cliente tem 2 ou 200 hectares."""
        client.post(
            "/v1/admin/tenants",
            json={"tenant": CLIENTE, "farm": PROPRIEDADE, "field": TALHAO},
            headers=platform_token,
        )
        lista = client.get("/v1/admin/tenants", headers=platform_token).json()
        novo = next(item for item in lista if item["slug"] == "sao-joao")
        assert novo["farms"] == 1
        assert novo["fields"] == 1
        assert novo["area_ha"] > 0


class TestEquipeDaValtexa:
    def test_o_seed_cria_as_contas_da_equipe(self, session: Session) -> None:
        criadas = seed_platform_team(session, password="uma-senha-de-teste-longa")
        assert set(criadas) == set(PLATFORM_TEAM)

        for email in PLATFORM_TEAM:
            user = session.scalars(select(User).where(User.email == email)).first()
            assert user is not None
            assert user.is_platform_admin is True

    def test_rodar_de_novo_nao_recria_nem_troca_senha(self, session: Session) -> None:
        """O seed roda a cada start. Se sobrescrevesse, toda reinicialização
        devolveria a senha do ambiente a uma conta cuja senha já foi trocada."""
        seed_platform_team(session, password="primeira-senha-longa")
        email = next(iter(PLATFORM_TEAM))
        antes = session.scalars(select(User).where(User.email == email)).first()
        assert antes is not None
        hash_antigo = antes.password_hash

        criadas = seed_platform_team(session, password="segunda-senha-longa")
        assert criadas == []

        session.expire_all()
        depois = session.scalars(select(User).where(User.email == email)).first()
        assert depois is not None
        assert depois.password_hash == hash_antigo

    def test_promove_quem_ja_existia_sem_a_marca(self, session: Session) -> None:
        """Conserta a conta criada antes de a pessoa entrar para a equipe."""
        email = next(iter(PLATFORM_TEAM))
        session.add(
            User(
                email=email,
                full_name="Criado antes",
                password_hash="x",
                is_platform_admin=False,
            )
        )
        session.commit()

        seed_platform_team(session, password="senha-de-teste-longa")
        session.expire_all()
        user = session.scalars(select(User).where(User.email == email)).first()
        assert user is not None
        assert user.is_platform_admin is True
        assert user.full_name == "Criado antes", "o seed não renomeia conta em uso"


class TestEscolhaDeCliente:
    def test_a_equipe_enxerga_todos_os_clientes_para_escolher(
        self, client: TestClient, platform_token: dict
    ) -> None:
        """O bug que isto segura: quem administra a plataforma e não é membro de
        fazenda nenhuma fazia login, caía na tela de escolher cliente e não via
        nenhum — trancado para fora do próprio sistema.
        """
        client.post("/v1/admin/tenants", json={"tenant": CLIENTE}, headers=platform_token)

        lista = client.get("/v1/auth/memberships", headers=platform_token).json()
        apelidos = {item["tenant_slug"] for item in lista}
        assert "sao-joao" in apelidos, "cliente sem associação não apareceu para a equipe"
        assert "fazenda-demo" in apelidos

    def test_o_papel_listado_e_o_mesmo_que_a_api_concede(
        self, client: TestClient, platform_token: dict
    ) -> None:
        """Se o console mostrasse um papel e a API aplicasse outro, a tela
        esconderia botões que funcionam — ou mostraria os que não funcionam."""
        criado = client.post(
            "/v1/admin/tenants", json={"tenant": CLIENTE}, headers=platform_token
        ).json()

        lista = client.get("/v1/auth/memberships", headers=platform_token).json()
        listado = next(item for item in lista if item["tenant_slug"] == "sao-joao")

        eu = client.get(
            "/v1/auth/me",
            headers={**platform_token, "X-Tenant-Id": criado["tenant"]["id"]},
        ).json()
        assert listado["role"] == eu["role"]

    def test_cliente_comum_so_ve_o_que_e_dele(
        self, client: TestClient, admin_token: dict, platform_token: dict
    ) -> None:
        """A fronteira de multilocação: um cliente jamais vê outro."""
        client.post("/v1/admin/tenants", json={"tenant": CLIENTE}, headers=platform_token)

        lista = client.get("/v1/auth/memberships", headers=admin_token).json()
        assert {item["tenant_slug"] for item in lista} == {"fazenda-demo"}


class TestDuasPortasMesmoRastro:
    """Cadastrar pelo onboarding e cadastrar pela tela de propriedades são duas
    portas para o mesmo ato. Se só uma deixa rastro, a trilha passa a depender
    de por onde a pessoa entrou — e uma auditoria assim não responde nada."""

    def test_o_cadastro_de_cliente_registra_a_propriedade_criada(
        self, client: TestClient, platform_token: dict
    ) -> None:
        resposta = client.post(
            "/v1/admin/tenants",
            json={
                "tenant": {"name": "Sítio da Trilha", "slug": "sitio-da-trilha"},
                "farm": {
                    "name": "Sede",
                    "center_lat": -21.9029,
                    "center_lon": -45.8624,
                    "base_lat": -21.9029,
                    "base_lon": -45.8624,
                },
            },
            headers=platform_token,
        )
        assert resposta.status_code == 201, resposta.text
        criado = resposta.json()

        trilha = client.get(
            "/v1/platform/audit",
            params={"action": "farm.created", "limit": 50, "tenant_id": criado["tenant"]["id"]},
            headers=platform_token,
        ).json()
        assert trilha, "a propriedade nasceu sem linha em 'farm.created'"
        assert trilha[0]["subject_id"] == criado["farm_id"]

    def test_o_cadastro_de_cliente_registra_o_talhao_criado(
        self, client: TestClient, platform_token: dict
    ) -> None:
        resposta = client.post(
            "/v1/admin/tenants",
            json={
                "tenant": {"name": "Sítio do Talhão", "slug": "sitio-do-talhao"},
                "farm": {
                    "name": "Sede",
                    "center_lat": -21.9029,
                    "center_lon": -45.8624,
                    "base_lat": -21.9029,
                    "base_lon": -45.8624,
                },
                "field": {
                    "name": "Quadra 1",
                    "crop": "coffee",
                    "boundary": [
                        [-45.8630, -21.9035],
                        [-45.8615, -21.9035],
                        [-45.8615, -21.9022],
                        [-45.8630, -21.9022],
                    ],
                },
            },
            headers=platform_token,
        )
        assert resposta.status_code == 201, resposta.text
        criado = resposta.json()

        trilha = client.get(
            "/v1/platform/audit",
            params={"action": "field.created", "limit": 50, "tenant_id": criado["tenant"]["id"]},
            headers=platform_token,
        ).json()
        assert trilha, "o talhão nasceu sem linha em 'field.created'"
        assert trilha[0]["subject_id"] == criado["field_id"]
        assert trilha[0]["payload"]["area_ha"] > 0
