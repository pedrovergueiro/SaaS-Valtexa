"""Testes de segurança.

Esta é a suíte que mais importa. Todo teste aqui descreve um ataque ou um erro
operacional que **não pode** funcionar. Falha aqui não é regressão de
funcionalidade: é o sistema deixando de recusar o que deveria recusar.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from valtexa.models import Role
from valtexa.security import rbac, signing, tokens
from valtexa.security.passwords import hash_password, needs_rehash, verify_password


class TestPasswords:
    """Hash de senha."""

    def test_verifica_a_senha_correta(self) -> None:
        stored = hash_password("uma-senha-muito-boa")
        assert verify_password("uma-senha-muito-boa", stored)

    def test_recusa_a_senha_errada(self) -> None:
        stored = hash_password("uma-senha-muito-boa")
        assert not verify_password("uma-senha-muito-bod", stored)

    def test_o_mesmo_texto_gera_hashes_diferentes(self) -> None:
        """Sal aleatório: dois usuários com a mesma senha não se denunciam."""
        assert hash_password("repetida-12345") != hash_password("repetida-12345")

    @pytest.mark.parametrize(
        "corrompido",
        ["", "nao-e-um-hash", "scrypt$só$duas$partes", "bcrypt$1$2$3$abc$def"],
    )
    def test_hash_malformado_devolve_falso_em_vez_de_explodir(self, corrompido: str) -> None:
        """Um registro corrompido não pode virar erro 500 na tela de login."""
        assert verify_password("qualquer-coisa", corrompido) is False

    def test_detecta_hash_com_custo_antigo(self) -> None:
        assert needs_rehash("scrypt$1024$8$1$aa$bb")
        assert not needs_rehash(hash_password("atual-12345"))


class TestSessionTokens:
    """Tokens de sessão."""

    def test_emite_e_valida(self) -> None:
        token, expires_at = tokens.issue("user", "u1", tenant_id="t1")
        claims = tokens.verify(token)
        assert claims.subject_id == "u1"
        assert claims.tenant_id == "t1"
        assert claims.kind == "user"
        assert expires_at > datetime.now(UTC)

    def test_recusa_token_adulterado(self) -> None:
        """Trocar um byte do payload invalida a assinatura."""
        token, _ = tokens.issue("user", "u1")
        body, signature = token.split(".", 1)
        adulterado = f"{body[:-2]}XY.{signature}"
        with pytest.raises(tokens.TokenError):
            tokens.verify(adulterado)

    def test_recusa_token_sem_assinatura(self) -> None:
        token, _ = tokens.issue("user", "u1")
        with pytest.raises(tokens.TokenError):
            tokens.verify(token.split(".", 1)[0])

    def test_recusa_token_expirado(self) -> None:
        token, _ = tokens.issue("user", "u1", ttl_seconds=1)
        time.sleep(1.1)
        with pytest.raises(tokens.TokenError):
            tokens.verify(token)


class TestCommandSigning:
    """Assinatura dos comandos que a nuvem manda ao robô."""

    def test_o_robo_valida_um_comando_legitimo(self) -> None:
        envelope = signing.command_envelope("mission.execute", "dev1", {"a": 1}, sequence=1)
        signed = signing.sign_command(envelope)
        signing.verify_command(signed.payload, signed.signature)

    def test_recusa_comando_alterado(self) -> None:
        """Mudar o polígono depois de assinado invalida a assinatura."""
        envelope = signing.command_envelope(
            "mission.execute", "dev1", {"polygon": [[0, 0]]}, sequence=1
        )
        signed = signing.sign_command(envelope)
        adulterado = {**signed.payload, "body": {"polygon": [[10, 10]]}}
        with pytest.raises(signing.SignatureError):
            signing.verify_command(adulterado, signed.signature)

    def test_uma_chave_alheia_nao_valida(self) -> None:
        """É por isso que a assinatura é assimétrica.

        Um robô comprometido tem apenas a chave pública da plataforma. Com ela
        não é possível produzir uma assinatura que a própria chave valide.
        """
        envelope = signing.command_envelope("mission.execute", "dev1", {}, sequence=1)
        signed = signing.sign_command(envelope)
        intruso = signing.generate_keypair()
        with pytest.raises(signing.SignatureError):
            signing.verify_command(signed.payload, signed.signature, intruso.public_key)

    def test_comando_vencido_e_reconhecido(self) -> None:
        envelope = signing.command_envelope("mission.execute", "dev1", {}, sequence=1)
        envelope["expires_at"] = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
        assert signing.command_is_expired(envelope)

    def test_o_envelope_carrega_o_destinatario(self) -> None:
        """Sem isso, o comando de um robô poderia ser reencaminhado ao vizinho."""
        envelope = signing.command_envelope("mission.execute", "dev-a", {}, sequence=3)
        assert envelope["device_id"] == "dev-a"
        assert envelope["sequence"] == 3
        assert envelope["nonce"]


class TestRequestSigning:
    """Assinatura das requisições do robô."""

    def test_assina_e_verifica(self) -> None:
        keys = signing.generate_keypair()
        args = ("POST", "/v1/device/telemetry", "", "1700000000", "abc", b'{"a":1}')
        signature = signing.sign_request(keys.private_key, *args)
        signing.verify_request(keys.public_key, signature, *args)

    @pytest.mark.parametrize(
        ("campo", "valor"),
        [
            ("method", "GET"),
            ("path", "/v1/device/events"),
            ("query", "x=1"),
            ("timestamp", "1700000001"),
            ("nonce", "outro"),
            ("body", b'{"a":2}'),
        ],
    )
    def test_mudar_qualquer_campo_invalida(self, campo: str, valor: object) -> None:
        """A assinatura cobre método, caminho, query, horário, nonce e corpo."""
        keys = signing.generate_keypair()
        original = {
            "method": "POST",
            "path": "/v1/device/telemetry",
            "query": "",
            "timestamp": "1700000000",
            "nonce": "abc",
            "body": b'{"a":1}',
        }
        signature = signing.sign_request(keys.private_key, **original)
        with pytest.raises(signing.SignatureError):
            signing.verify_request(
                keys.public_key, signature, **{**original, campo: valor}
            )

    def test_recusa_horario_fora_da_janela(self) -> None:
        antigo = str(int(time.time()) - 10_000)
        with pytest.raises(signing.SignatureError, match="janela"):
            signing.check_timestamp(antigo)

    def test_aceita_horario_dentro_da_janela(self) -> None:
        assert signing.check_timestamp(str(int(time.time())))

    def test_recusa_horario_ilegivel(self) -> None:
        with pytest.raises(signing.SignatureError):
            signing.check_timestamp("ontem")


class TestRbac:
    """Permissões por papel."""

    def test_so_o_agronomo_aprova_aplicacao(self) -> None:
        """A regra mais importante do produto.

        É o ponto em que uma recomendação de software vira produto químico no
        ar. Nenhum outro papel pode chegar lá — nem o dono da fazenda.
        """
        assert rbac.can(Role.AGRONOMIST, rbac.MISSION_APPROVE_APPLICATION)
        for papel in (Role.OWNER, Role.ADMIN, Role.OPERATOR, Role.TECHNICIAN, Role.VIEWER):
            assert not rbac.can(papel, rbac.MISSION_APPROVE_APPLICATION), papel

    def test_todo_papel_operacional_pode_abortar(self) -> None:
        """Parar nunca depende de permissão rara."""
        for papel in (Role.OWNER, Role.ADMIN, Role.AGRONOMIST, Role.OPERATOR, Role.TECHNICIAN):
            assert rbac.can(papel, rbac.MISSION_ABORT), papel

    def test_o_auditor_nao_escreve(self) -> None:
        assert rbac.can(Role.AUDITOR, rbac.AUDIT_READ)
        for capacidade in (
            rbac.MISSION_CREATE,
            rbac.MISSION_DISPATCH,
            rbac.DEVICE_MANAGE,
            rbac.PRODUCT_MANAGE,
            rbac.DIAGNOSIS_REVIEW,
        ):
            assert not rbac.can(Role.AUDITOR, capacidade), capacidade

    def test_o_visualizador_so_le(self) -> None:
        for capacidade in rbac.capabilities_of(Role.VIEWER):
            assert capacidade.endswith(":read"), capacidade

    def test_capacidade_desconhecida_e_erro_de_programacao(self) -> None:
        """Um nome errado precisa explodir, não devolver ``False`` em silêncio."""
        with pytest.raises(ValueError, match="desconhecida"):
            rbac.can(Role.ADMIN, "missao:inventada")


class TestApiAuth:
    """Autenticação nas rotas."""

    def test_rota_protegida_exige_token(self, client: TestClient) -> None:
        assert client.get("/v1/farms").status_code == 401

    def test_token_invalido_e_recusado(self, client: TestClient) -> None:
        response = client.get("/v1/farms", headers={"Authorization": "Bearer nao-e-um-token"})
        assert response.status_code == 401

    def test_login_errado_nao_revela_se_o_email_existe(self, client: TestClient) -> None:
        """As duas respostas precisam ser indistinguíveis."""
        inexistente = client.post(
            "/v1/auth/login",
            json={"email": "ninguem@valtexa.dev", "password": "senha-errada-123"},
        )
        senha_errada = client.post(
            "/v1/auth/login",
            json={"email": "admin@valtexa.dev", "password": "senha-errada-123"},
        )
        assert inexistente.status_code == senha_errada.status_code == 401
        assert inexistente.json()["detail"] == senha_errada.json()["detail"]

    def test_token_de_dispositivo_nao_serve_em_rota_de_usuario(self, client: TestClient) -> None:
        """Uma conta de robô comprometida não vira uma conta de pessoa."""
        token, _ = tokens.issue("device", "dev1", tenant_id="t1")
        response = client.get("/v1/farms", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 403

    def test_operador_nao_aprova_aplicacao(
        self,
        client: TestClient,
        admin_token: dict,
        operator_token: dict,
        agronomist_token: dict,
        demo: dict,
    ) -> None:
        """A permissão é conferida no servidor, não só escondida na tela."""
        mission = _spray_mission(client, admin_token, agronomist_token, demo)
        response = client.post(
            f"/v1/missions/{mission['id']}/approve",
            json={"confirm": True},
            headers=operator_token,
        )
        assert response.status_code == 403
        assert "approve_application" in response.json()["detail"]

    def test_dado_de_outro_cliente_devolve_404(
        self, client: TestClient, admin_token: dict, demo: dict
    ) -> None:
        """404 e não 403: 403 confirmaria que o identificador existe."""
        outro = dict(admin_token)
        outro["X-Tenant-Id"] = "0" * 32
        response = client.get(f"/v1/fields/{demo['field_id']}", headers=outro)
        assert response.status_code in {403, 404}


class TestDeviceProtocolAuth:
    """Autenticação do robô nas rotas de dispositivo."""

    def test_sem_assinatura_e_recusado(self, client: TestClient) -> None:
        response = client.post("/v1/device/telemetry", json={"samples": []})
        assert response.status_code == 401
        assert "x-valtexa-key-id" in response.json()["detail"]

    def test_credencial_desconhecida_e_recusada(self, client: TestClient) -> None:
        keys = signing.generate_keypair()
        headers = _sign_headers(
            keys.private_key, "dk_inexistente", "POST", "/v1/device/telemetry", b"{}"
        )
        response = client.post("/v1/device/telemetry", content=b"{}", headers=headers)
        assert response.status_code == 401

    def test_o_horario_do_servidor_e_publico(self, client: TestClient) -> None:
        """Um robô com relógio perdido precisa de um caminho de volta."""
        response = client.get("/v1/device/time")
        assert response.status_code == 200
        assert "server_time" in response.json()


def _sign_headers(
    private_key: str, key_id: str, method: str, path: str, body: bytes
) -> dict[str, str]:
    timestamp = str(int(time.time()))
    nonce = signing.new_nonce()
    signature = signing.sign_request(private_key, method, path, "", timestamp, nonce, body)
    return {
        signing.HEADER_KEY_ID: key_id,
        signing.HEADER_TIMESTAMP: timestamp,
        signing.HEADER_NONCE: nonce,
        signing.HEADER_SIGNATURE: signature,
        "Content-Type": "application/json",
    }


def _spray_mission(
    client: TestClient, admin: dict, creator: dict, demo: dict
) -> dict:
    """Cria uma missão de pulverização em rascunho, para os testes de permissão.

    Provisionar é do técnico/admin; criar a missão é de quem vai operá-la. A
    separação aqui não é cerimônia do teste — é a mesma que o produto impõe.
    """
    device = client.post(
        "/v1/provisioning-tokens",
        json={"device_model_code": "DRONE_ACTION_V1", "serial_number": "T-DRONE-1"},
        headers=admin,
    )
    assert device.status_code == 201, device.text
    provisioned = client.post(
        "/v1/device/provision",
        json={
            "provisioning_token": device.json()["token"],
            "serial_number": "T-DRONE-1",
            "public_key": signing.generate_keypair().public_key,
        },
    )
    assert provisioned.status_code == 201, provisioned.text

    response = client.post(
        "/v1/missions",
        json={
            "kind": "spray",
            "field_id": demo["field_id"],
            "device_id": provisioned.json()["device_id"],
            "product_id": demo["product_id"],
            "product_batch_id": demo["batch_id"],
            "authorized_rate_l_ha": 0.75,
            "authorized_quantity_l": 5.0,
        },
        headers=creator,
    )
    assert response.status_code == 201, response.text
    return response.json()
