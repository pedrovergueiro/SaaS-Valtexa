"""Planos, limites e uso (brief, seção 31).

O que estes testes seguram: o plano limita de verdade — nas rotas que criam
fazenda, talhão, robô, usuário e missão —, com mensagem clara em português; a
assinatura suspensa ou vencida bloqueia criação sem tirar a consulta; e a
migração do texto livre não perde o que estava escrito.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from tests.helpers import provision, send_telemetry
from valtexa import db
from valtexa.models import AuditEntry, PlatformRole

FAZENDA = {"name": "Fazenda Nova", "center_lat": -22.41, "center_lon": -45.45}

# ~1,9 ha perto da fazenda de demonstração.
CONTORNO = [[-45.4530, -22.4120], [-45.4515, -22.4120], [-45.4515, -22.4132], [-45.4530, -22.4132]]


def _assinar(client: TestClient, comercial: dict, tenant_id: str, **corpo) -> dict:
    corpo.setdefault("plan_code", "essencial")
    resposta = client.put(
        f"/v1/admin/tenants/{tenant_id}/subscription", json=corpo, headers=comercial
    )
    assert resposta.status_code == 200, resposta.text
    return resposta.json()


def _uso(client: TestClient, headers: dict, recurso: str) -> float:
    plano = client.get("/v1/tenants/current/plan", headers=headers).json()
    return next(item["used"] for item in plano["usage"] if item["resource"] == recurso)


@pytest.fixture
def comercial(equipe) -> dict:
    return equipe(PlatformRole.COMERCIAL)


# ---------------------------------------------------------------------------
# Migração
# ---------------------------------------------------------------------------


def test_migracao_assina_o_piloto_e_preserva_o_texto(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'planos.db'}"
    config = db.alembic_config(url)
    command.upgrade(config, "0010")
    engine = create_engine(url)
    agora = datetime.now(UTC).isoformat()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO tenant (id, created_at, updated_at, name, slug, is_active, "
                "contracted_service) VALUES ('t1', :t, :t, 'Cliente', 'cliente', 1, "
                "'monitoramento com rover')"
            ),
            {"t": agora},
        )
    command.upgrade(config, "head")
    with engine.connect() as conn:
        linha = conn.execute(
            text(
                "SELECT p.code, s.status, s.notes FROM subscription s "
                "JOIN plan p ON p.id = s.plan_id WHERE s.tenant_id = 't1'"
            )
        ).one()
        servico = conn.execute(
            text("SELECT contracted_service FROM tenant WHERE id = 't1'")
        ).scalar()
    assert linha[0] == "piloto"
    assert linha[1] == "ativa"
    assert "monitoramento com rover" in linha[2]
    assert servico == "monitoramento com rover", "o texto original continua no cadastro"
    engine.dispose()


# ---------------------------------------------------------------------------
# Limites nas rotas de criação
# ---------------------------------------------------------------------------


class TestLimites:
    def test_sem_assinatura_nao_ha_limite(
        self, client: TestClient, admin_token: dict
    ) -> None:
        plano = client.get("/v1/tenants/current/plan", headers=admin_token).json()
        assert plano["has_subscription"] is False
        assert client.post("/v1/farms", json=FAZENDA, headers=admin_token).status_code == 201

    def test_fazenda(
        self, client: TestClient, admin_token: dict, comercial: dict, demo: dict
    ) -> None:
        _assinar(client, comercial, demo["tenant_id"])  # essencial: 1 fazenda
        resposta = client.post("/v1/farms", json=FAZENDA, headers=admin_token)
        assert resposta.status_code == 409
        detalhe = resposta.json()["detail"]
        assert "Limite do plano Essencial atingido" in detalhe
        assert "1 de 1 fazendas" in detalhe

    def test_talhao_e_hectares(
        self, client: TestClient, admin_token: dict, comercial: dict, demo: dict
    ) -> None:
        talhoes = _uso(client, admin_token, "fields")
        _assinar(
            client, comercial, demo["tenant_id"], overrides={"max_fields": int(talhoes)}
        )
        novo = {"name": "T2", "crop": "corn", "boundary": CONTORNO}
        rota = f"/v1/farms/{demo['farm_id']}/fields"
        resposta = client.post(rota, json=novo, headers=admin_token)
        assert resposta.status_code == 409
        assert "talhões" in resposta.json()["detail"]

        hectares = _uso(client, admin_token, "hectares")
        _assinar(
            client,
            comercial,
            demo["tenant_id"],
            overrides={"max_fields": None, "max_hectares": hectares + 0.5},
        )
        resposta = client.post(rota, json=novo, headers=admin_token)
        assert resposta.status_code == 409
        assert "hectares" in resposta.json()["detail"]

        _assinar(
            client,
            comercial,
            demo["tenant_id"],
            overrides={"max_fields": None, "max_hectares": hectares + 10},
        )
        assert client.post(rota, json=novo, headers=admin_token).status_code == 201

    def test_robo(
        self, client: TestClient, admin_token: dict, comercial: dict, demo: dict
    ) -> None:
        robos = _uso(client, admin_token, "devices")
        _assinar(client, comercial, demo["tenant_id"], overrides={"max_devices": int(robos)})
        resposta = client.post(
            "/v1/provisioning-tokens",
            json={"device_model_code": "ROVER_SCOUT_V1", "serial_number": "LIM-1"},
            headers=admin_token,
        )
        assert resposta.status_code == 409
        assert "robôs" in resposta.json()["detail"]

    def test_robo_tambem_no_provisionamento(
        self, client: TestClient, admin_token: dict, comercial: dict, demo: dict
    ) -> None:
        """O convite saiu com vaga; o robô chegou depois que a vaga acabou."""
        robos = _uso(client, admin_token, "devices")
        _assinar(
            client, comercial, demo["tenant_id"], overrides={"max_devices": int(robos) + 1}
        )
        provision(client, admin_token, "ROVER_SCOUT_V1", "LIM-A")
        _assinar(client, comercial, demo["tenant_id"], overrides={"max_devices": None})
        convite = client.post(
            "/v1/provisioning-tokens",
            json={"device_model_code": "ROVER_SCOUT_V1", "serial_number": "LIM-B"},
            headers=admin_token,
        ).json()
        _assinar(
            client, comercial, demo["tenant_id"], overrides={"max_devices": int(robos) + 1}
        )
        from valtexa.security import signing

        chaves = signing.generate_keypair()
        resposta = client.post(
            "/v1/device/provision",
            json={
                "provisioning_token": convite["token"],
                "serial_number": "LIM-B",
                "public_key": chaves.public_key,
                "firmware_version": "1.0.0",
            },
        )
        assert resposta.status_code == 409, resposta.text

    def test_usuario(
        self, client: TestClient, admin_token: dict, comercial: dict, demo: dict
    ) -> None:
        usuarios = _uso(client, admin_token, "users")
        _assinar(client, comercial, demo["tenant_id"], overrides={"max_users": int(usuarios)})
        resposta = client.post(
            "/v1/users",
            json={
                "email": "mais-um@x.dev",
                "full_name": "Mais Um",
                "password": "senha-longa-123",
                "role": "viewer",
            },
            headers=admin_token,
        )
        assert resposta.status_code == 409
        assert "usuários" in resposta.json()["detail"]

    def test_missoes_por_mes(
        self,
        client: TestClient,
        admin_token: dict,
        operator_token: dict,
        comercial: dict,
        demo: dict,
    ) -> None:
        _assinar(
            client, comercial, demo["tenant_id"], overrides={"max_missions_per_month": 1}
        )
        rover = provision(client, admin_token, "ROVER_SCOUT_V1", "LIM-M", demo["farm_id"])
        send_telemetry(rover, battery_percent=95.0)
        corpo = {"kind": "scout", "field_id": demo["field_id"], "device_id": rover.device_id}
        primeira = client.post("/v1/missions", json=corpo, headers=operator_token)
        assert primeira.status_code == 201, primeira.text
        segunda = client.post("/v1/missions", json=corpo, headers=operator_token)
        assert segunda.status_code == 409
        assert "missões neste mês" in segunda.json()["detail"]
        assert _uso(client, admin_token, "missions_month") == 1


class TestAssinatura:
    def test_suspensa_bloqueia_criacao_e_nao_a_leitura(
        self, client: TestClient, admin_token: dict, comercial: dict, demo: dict
    ) -> None:
        _assinar(client, comercial, demo["tenant_id"], plan_code="piloto", status="suspensa")
        resposta = client.post("/v1/farms", json=FAZENDA, headers=admin_token)
        assert resposta.status_code == 402
        assert "suspensa" in resposta.json()["detail"]
        assert client.get("/v1/farms", headers=admin_token).status_code == 200

    def test_vencida_bloqueia_criacao(
        self, client: TestClient, admin_token: dict, comercial: dict, demo: dict
    ) -> None:
        ontem = (datetime.now(UTC) - timedelta(days=1)).isoformat()
        _assinar(client, comercial, demo["tenant_id"], plan_code="piloto", ends_at=ontem)
        resposta = client.post("/v1/farms", json=FAZENDA, headers=admin_token)
        assert resposta.status_code == 402
        assert "venceu" in resposta.json()["detail"]

    def test_so_comercial_e_superadmin_mudam_plano(
        self, client: TestClient, equipe, demo: dict
    ) -> None:
        corpo = {"plan_code": "essencial"}
        rota = f"/v1/admin/tenants/{demo['tenant_id']}/subscription"
        suporte, ia = equipe(PlatformRole.SUPORTE), equipe(PlatformRole.IA_DADOS)
        assert client.put(rota, json=corpo, headers=suporte).status_code == 403
        assert client.get(rota, headers=suporte).status_code == 200
        assert client.put(rota, json=corpo, headers=ia).status_code == 403

    def test_cliente_nao_muda_o_proprio_plano(
        self, client: TestClient, admin_token: dict, demo: dict
    ) -> None:
        rota = f"/v1/admin/tenants/{demo['tenant_id']}/subscription"
        resposta = client.put(rota, json={"plan_code": "empresarial"}, headers=admin_token)
        assert resposta.status_code == 403

    def test_troca_de_plano_na_auditoria(
        self, client: TestClient, comercial: dict, demo: dict, session: Session
    ) -> None:
        _assinar(client, comercial, demo["tenant_id"], plan_code="essencial")
        _assinar(client, comercial, demo["tenant_id"], plan_code="profissional")
        trocas = session.scalars(
            select(AuditEntry)
            .where(AuditEntry.action == "plan.changed", AuditEntry.tenant_id == demo["tenant_id"])
            .order_by(AuditEntry.at)
        ).all()
        assert [t.new_state for t in trocas] == ["essencial", "profissional"]
        assert trocas[1].payload["antes"]["plano"] == "essencial"
        assert trocas[1].actor_label == "comercial@equipe.valtexa.dev"

    def test_sobreposicao_desconhecida_e_recusada(
        self, client: TestClient, comercial: dict, demo: dict
    ) -> None:
        resposta = client.put(
            f"/v1/admin/tenants/{demo['tenant_id']}/subscription",
            json={"plan_code": "essencial", "overrides": {"max_tratores": 3}},
            headers=comercial,
        )
        assert resposta.status_code == 422

    def test_o_cliente_ve_uso_e_limite(
        self, client: TestClient, admin_token: dict, comercial: dict, demo: dict
    ) -> None:
        _assinar(client, comercial, demo["tenant_id"], plan_code="profissional")
        plano = client.get("/v1/tenants/current/plan", headers=admin_token).json()
        assert plano["plan"]["code"] == "profissional"
        fazendas = next(i for i in plano["usage"] if i["resource"] == "farms")
        assert fazendas["used"] == 1
        assert fazendas["limit"] == 5
        assert fazendas["percent"] == 20.0


class TestCatalogo:
    def test_comercial_cria_e_altera_plano(
        self, client: TestClient, comercial: dict
    ) -> None:
        criado = client.post(
            "/v1/admin/plans",
            json={"code": "cooperativa", "name": "Cooperativa", "max_fields": 200},
            headers=comercial,
        )
        assert criado.status_code == 201, criado.text
        alterado = client.patch(
            f"/v1/admin/plans/{criado.json()['id']}",
            json={"max_fields": None, "max_devices": 20},
            headers=comercial,
        )
        assert alterado.status_code == 200
        assert alterado.json()["max_fields"] is None
        assert alterado.json()["max_devices"] == 20

    def test_codigo_repetido_e_conflito(self, client: TestClient, comercial: dict) -> None:
        resposta = client.post(
            "/v1/admin/plans", json={"code": "essencial", "name": "Outro"}, headers=comercial
        )
        assert resposta.status_code == 409

    def test_plano_inativo_nao_aceita_assinatura(
        self, client: TestClient, comercial: dict, demo: dict
    ) -> None:
        planos = client.get("/v1/admin/plans", headers=comercial).json()
        essencial = next(p for p in planos if p["code"] == "essencial")
        client.patch(
            f"/v1/admin/plans/{essencial['id']}", json={"is_active": False}, headers=comercial
        )
        resposta = client.put(
            f"/v1/admin/tenants/{demo['tenant_id']}/subscription",
            json={"plan_code": "essencial"},
            headers=comercial,
        )
        assert resposta.status_code == 409


class TestRecursos:
    """Verificação da Parte 2: ``Plan.features`` era gravado e não valia em rota nenhuma."""

    def test_lavoura_3d_fora_do_plano_e_recusada(
        self, client: TestClient, admin_token: dict, comercial: dict, demo: dict
    ) -> None:
        rota = f"/v1/fields/{demo['field_id']}/scene"
        assert client.get(rota, headers=admin_token).status_code == 200  # piloto: tudo

        _assinar(client, comercial, demo["tenant_id"], plan_code="essencial")
        for caminho in (rota, f"/v1/fields/{demo['field_id']}/row-scans"):
            resposta = client.get(caminho, headers=admin_token)
            assert resposta.status_code == 402, caminho
            assert "lavoura 3D" in resposta.json()["detail"]

        # O que não é 3D continua aberto.
        assert client.get(f"/v1/fields/{demo['field_id']}", headers=admin_token).status_code == 200

    def test_plano_com_o_recurso_libera(
        self, client: TestClient, admin_token: dict, comercial: dict, demo: dict
    ) -> None:
        _assinar(client, comercial, demo["tenant_id"], plan_code="empresarial")
        resposta = client.get(f"/v1/fields/{demo['field_id']}/scene", headers=admin_token)
        assert resposta.status_code == 200
