"""Frota (brief, seções 22, 25 e 26): estado derivado do protocolo, versões e saúde.

O que estes testes seguram:

* os sete estados saem do que o robô informou (contato, missão, ``/sync``,
  falhas) e das decisões administrativas auditadas — ninguém os digita;
* o robô diz o software que roda ao abrir a sessão, e a troca fica na trilha;
* bateria, temperatura, armazenamento, enlace, horímetro e última
  sincronização chegam pela telemetria e pelo ``/sync``;
* vários robôs na mesma fazenda, cada um com a sua missão;
* Operações vê a frota de todos os clientes, com filtro por cliente e por
  "modelo diferente do designado"; papéis sem a capacidade não.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from tests.helpers import DeviceSession, provision, send_telemetry
from tests.test_end_to_end import ZONA
from valtexa.models import (
    AuditEntry,
    CredentialStatus,
    Device,
    DeviceCredential,
    DeviceStatus,
    PlatformRole,
)
from valtexa.services import fleet_state
from valtexa.services.fleet_state import FleetState

AGORA = datetime(2026, 10, 3, 12, 0, tzinfo=UTC)


def _robo(**campos) -> Device:
    base = {
        "status": DeviceStatus.ACTIVE,
        "last_seen_at": AGORA - timedelta(seconds=10),
        "active_faults": [],
        "sync_pending": 0,
        "active_mission_id": None,
    }
    device = Device(serial_number="X", name="X", **{**base, **campos})
    device.credentials = [DeviceCredential(key_id="k", public_key="p")]
    return device


class TestDerivacao:
    """A função pura: cada estado e a precedência entre eles."""

    @pytest.mark.parametrize(
        ("campos", "esperado"),
        [
            ({}, FleetState.DISPONIVEL),
            ({"active_mission_id": "m1"}, FleetState.EM_MISSAO),
            ({"sync_pending": 40}, FleetState.SINCRONIZANDO),
            ({"status": DeviceStatus.MAINTENANCE}, FleetState.MANUTENCAO),
            ({"last_seen_at": AGORA - timedelta(minutes=6)}, FleetState.OFFLINE),
            ({"last_seen_at": None}, FleetState.OFFLINE),
            ({"status": DeviceStatus.SUSPENDED}, FleetState.BLOQUEADO),
            ({"status": DeviceStatus.RETIRED}, FleetState.BLOQUEADO),
            ({"active_faults": [{"code": "MOTOR_L"}]}, FleetState.ERRO),
        ],
    )
    def test_cada_estado(self, campos: dict, esperado: FleetState) -> None:
        assert fleet_state.derive(_robo(**campos), AGORA).state is esperado

    def test_bloqueado_vence_offline(self) -> None:
        """Religar o enlace não libera um robô suspenso."""
        robo = _robo(status=DeviceStatus.SUSPENDED, last_seen_at=None)
        assert fleet_state.derive(robo, AGORA).state is FleetState.BLOQUEADO

    def test_offline_vence_a_falha_antiga(self) -> None:
        robo = _robo(active_faults=["E1"], last_seen_at=AGORA - timedelta(hours=2))
        situacao = fleet_state.derive(robo, AGORA)
        assert situacao.state is FleetState.OFFLINE
        assert "120 min" in situacao.reason

    def test_missao_vence_a_descarga_e_o_motivo_conta_as_duas(self) -> None:
        situacao = fleet_state.derive(_robo(active_mission_id="m", sync_pending=3), AGORA)
        assert situacao.state is FleetState.EM_MISSAO
        assert "3 registro" in situacao.reason

    def test_credencial_revogada_bloqueia(self) -> None:
        robo = _robo()
        robo.credentials[0].status = CredentialStatus.REVOKED
        assert fleet_state.derive(robo, AGORA).state is FleetState.BLOQUEADO

    def test_falha_vem_descrita(self) -> None:
        situacao = fleet_state.derive(_robo(active_faults=[{"code": "CAM_1"}, "GNSS"]), AGORA)
        assert "CAM_1" in situacao.reason and "GNSS" in situacao.reason


def _retrato(client: TestClient, headers: dict, device_id: str) -> dict:
    resposta = client.get(f"/v1/devices/{device_id}", headers=headers)
    assert resposta.status_code == 200, resposta.text
    return resposta.json()


@pytest.fixture
def rover(client: TestClient, admin_token: dict, demo: dict) -> DeviceSession:
    robo = provision(client, admin_token, "ROVER_SCOUT_V1", "FROTA-R1", demo["farm_id"])
    assert send_telemetry(robo, battery_percent=90.0).status_code == 200
    return robo


class TestProtocolo:
    def test_robo_novo_disponivel(
        self, client: TestClient, admin_token: dict, rover: DeviceSession
    ) -> None:
        retrato = _retrato(client, admin_token, rover.device_id)
        assert retrato["fleet_state"] == "disponivel"
        assert retrato["fleet_state_label"] == "Disponível"
        assert retrato["model_status"] == "sem_dado"

    def test_sessao_informa_as_versoes_e_a_troca_fica_na_trilha(
        self, client: TestClient, admin_token: dict, rover: DeviceSession, session: Session
    ) -> None:
        corpo = {
            "runtime_version": "0.4.0",
            "edge_ai_version": "0.2.1",
            "model_key": "coffee-foliar",
            "model_version": "1.0.0",
            "dnaty_version": "2.2.1",
            "hardware_version": "Rover Edge V1",
        }
        assert rover.request("POST", "/v1/device/session", json_body=corpo).status_code == 200
        retrato = _retrato(client, admin_token, rover.device_id)
        assert retrato["runtime_version"] == "0.4.0"
        assert retrato["edge_ai_version"] == "0.2.1"
        assert retrato["ai_model_key"] == "coffee-foliar"
        assert retrato["dnaty_version"] == "2.2.1"
        assert retrato["hardware_version"] == "Rover Edge V1"
        assert retrato["versions_reported_at"] is not None
        # A demonstração é café: coffee-foliar 1.0.0 é o que o registry designa.
        assert retrato["model_status"] == "conforme"
        assert retrato["designated_models"] == ["coffee-foliar@1.0.0"]

        # Sessão sem corpo (firmware antigo) não apaga nada.
        assert rover.request("POST", "/v1/device/session").status_code == 200
        rover.request("POST", "/v1/device/session", json_body={"runtime_version": "0.5.0"})
        assert _retrato(client, admin_token, rover.device_id)["edge_ai_version"] == "0.2.1"

        trilha = session.scalars(
            select(AuditEntry)
            .where(AuditEntry.action == "device.versions_reported")
            .order_by(AuditEntry.at)
        ).all()
        assert len(trilha) == 2
        assert trilha[1].payload == {
            "antes": {"runtime_version": "0.4.0"},
            "depois": {"runtime_version": "0.5.0"},
        }
        assert trilha[0].actor_type.value == "device"

    @pytest.mark.parametrize(
        ("chave", "versao", "esperado"),
        [
            ("coffee-foliar", "0.9.0", "fora_do_registry"),
            ("leaf-foliar", "1.0.0", "divergente"),
        ],
    )
    def test_modelo_diferente_do_designado(
        self,
        client: TestClient,
        admin_token: dict,
        rover: DeviceSession,
        chave: str,
        versao: str,
        esperado: str,
    ) -> None:
        rover.request(
            "POST", "/v1/device/session",
            json_body={"model_key": chave, "model_version": versao},
        )
        assert _retrato(client, admin_token, rover.device_id)["model_status"] == esperado

    def test_saude_pela_telemetria(
        self, client: TestClient, admin_token: dict, rover: DeviceSession
    ) -> None:
        send_telemetry(
            rover,
            temperature_c=41.5,
            link_quality=0.7,
            storage_total_bytes=64_000_000_000,
            storage_free_bytes=12_000_000_000,
            operating_hours=120.5,
        )
        retrato = _retrato(client, admin_token, rover.device_id)
        assert retrato["temperature_c"] == 41.5
        assert retrato["link_quality"] == 0.7
        assert retrato["storage_free_bytes"] == 12_000_000_000
        assert retrato["operating_hours"] == 120.5
        assert retrato["battery_percent"] == 90.0  # a amostra sem bateria não apaga a anterior

        # Horímetro só sobe.
        send_telemetry(rover, operating_hours=100.0)
        assert _retrato(client, admin_token, rover.device_id)["operating_hours"] == 120.5

    def test_falha_na_telemetria_e_erro_ate_a_proxima_limpa(
        self, client: TestClient, admin_token: dict, rover: DeviceSession
    ) -> None:
        send_telemetry(rover, faults=[{"code": "MOTOR_ESQ", "message": "sobrecorrente"}])
        retrato = _retrato(client, admin_token, rover.device_id)
        assert retrato["fleet_state"] == "erro"
        assert "MOTOR_ESQ" in retrato["fleet_state_reason"]
        send_telemetry(rover, faults=[])
        assert _retrato(client, admin_token, rover.device_id)["fleet_state"] == "disponivel"

    def test_lote_antigo_nao_volta_o_retrato(
        self, client: TestClient, admin_token: dict, rover: DeviceSession
    ) -> None:
        """Uma amostra de horas atrás, chegando pela descarga, não reabre um ERRO já limpo."""
        rover.sequence = 500
        send_telemetry(rover, faults=[])
        antiga = {
            "sequence_number": 10,
            "recorded_at": (datetime.now(UTC) - timedelta(hours=3)).isoformat(),
            "faults": ["E-ANTIGO"],
            "battery_percent": 20.0,
        }
        resposta = rover.request(
            "POST", "/v1/device/sync", json_body={"sync_id": "s-antigo", "samples": [antiga]}
        )
        assert resposta.json()["accepted"] == 1
        retrato = _retrato(client, admin_token, rover.device_id)
        assert retrato["fleet_state"] == "disponivel"
        assert retrato["battery_percent"] == 90.0

    def test_sincronizando_ate_o_robo_dizer_que_acabou(
        self, client: TestClient, admin_token: dict, rover: DeviceSession
    ) -> None:
        def lote(sync_id: str, restantes: int):
            amostra = {"sequence_number": rover.next_sequence(), "battery_percent": 80.0}
            return rover.request(
                "POST",
                "/v1/device/sync",
                json_body={"sync_id": sync_id, "samples": [amostra], "remaining": restantes},
            )

        assert lote("s1", 250).status_code == 200
        retrato = _retrato(client, admin_token, rover.device_id)
        assert retrato["fleet_state"] == "sincronizando"
        assert retrato["sync_pending"] == 250
        assert retrato["last_sync_at"] is None

        lote("s2", 0)
        retrato = _retrato(client, admin_token, rover.device_id)
        assert retrato["fleet_state"] == "disponivel"
        assert retrato["last_sync_at"] is not None

    def test_offline_pelo_tempo_sem_contato(
        self, client: TestClient, admin_token: dict, rover: DeviceSession, session: Session
    ) -> None:
        robo = session.get(Device, rover.device_id)
        robo.last_seen_at = datetime.now(UTC) - timedelta(minutes=30)
        session.commit()
        retrato = _retrato(client, admin_token, rover.device_id)
        assert retrato["fleet_state"] == "offline"
        assert retrato["connectivity"] == "offline"


class TestAdministracao:
    def test_manutencao_com_nota_e_data_de_saida(
        self, client: TestClient, admin_token: dict, rover: DeviceSession
    ) -> None:
        url = f"/v1/devices/{rover.device_id}/status"
        entrou = client.patch(
            url,
            json={"status": "maintenance", "maintenance_note": "troca da roda dianteira"},
            headers=admin_token,
        ).json()
        assert entrou["fleet_state"] == "manutencao"
        assert "roda dianteira" in entrou["fleet_state_reason"]
        assert entrou["last_maintenance_at"] is None

        saiu = client.patch(url, json={"status": "active"}, headers=admin_token).json()
        assert saiu["fleet_state"] == "disponivel"
        assert saiu["last_maintenance_at"] is not None
        assert saiu["maintenance_note"] is None

    def test_revogar_credenciais_bloqueia(
        self, client: TestClient, admin_token: dict, rover: DeviceSession
    ) -> None:
        client.post(f"/v1/devices/{rover.device_id}/revoke-credentials", headers=admin_token)
        assert _retrato(client, admin_token, rover.device_id)["fleet_state"] == "bloqueado"


def test_varios_robos_na_mesma_fazenda_cada_um_com_a_sua_missao(
    client: TestClient, admin_token: dict, operator_token: dict, demo: dict
) -> None:
    robos = [
        provision(client, admin_token, "ROVER_SCOUT_V1", f"MULTI-{i}", demo["farm_id"])
        for i in range(2)
    ]
    missoes = []
    for robo in robos:
        send_telemetry(robo, battery_percent=95.0)
        criada = client.post(
            "/v1/missions",
            json={
                "kind": "scout",
                "field_id": demo["field_id"],
                "zone_id": demo["zone_id"],
                "device_id": robo.device_id,
                "target_polygon": ZONA,
                "plan": {"swath_m": 40.0},
            },
            headers=operator_token,
        )
        assert criada.status_code == 201, criada.text
        mid = criada.json()["id"]
        avaliacao = client.post(f"/v1/missions/{mid}/authorize", headers=operator_token)
        assert avaliacao.json()["verdict"] == "safe_to_execute", avaliacao.text
        enviada = client.post(f"/v1/missions/{mid}/dispatch", headers=operator_token)
        assert enviada.status_code == 200, enviada.text
        missoes.append(mid)

    frota = {
        d["id"]: d
        for d in client.get(
            "/v1/devices", params={"farm_id": demo["farm_id"]}, headers=operator_token
        ).json()
    }
    for robo, mid in zip(robos, missoes, strict=True):
        assert frota[robo.device_id]["fleet_state"] == "em_missao"
        assert frota[robo.device_id]["active_mission_id"] == mid
    assert missoes[0] != missoes[1]


class TestFrotaDaPlataforma:
    def test_operacoes_ve_todos_os_clientes_com_filtros(
        self,
        client: TestClient,
        equipe,
        rover: DeviceSession,
        demo: dict,
        admin_token: dict,
    ) -> None:
        operacoes = equipe(PlatformRole.OPERACOES)
        todos = client.get("/v1/platform/fleet", headers=operacoes)
        assert todos.status_code == 200, todos.text
        meu = next(d for d in todos.json() if d["id"] == rover.device_id)
        assert meu["tenant_id"] == demo["tenant_id"]
        assert meu["tenant_name"]
        assert meu["fleet_state"] == "disponivel"

        vazio = client.get("/v1/platform/fleet", params={"tenant_id": "outro"}, headers=operacoes)
        assert vazio.json() == []

        assert client.get(
            "/v1/platform/fleet", params={"model_divergent": True}, headers=operacoes
        ).json() == []
        rover.request(
            "POST", "/v1/device/session",
            json_body={"model_key": "leaf-foliar", "model_version": "1.0.0"},
        )
        divergentes = client.get(
            "/v1/platform/fleet", params={"model_divergent": True}, headers=operacoes
        ).json()
        assert [d["id"] for d in divergentes] == [rover.device_id]

        por_estado = client.get(
            "/v1/platform/fleet", params={"fleet_state": "offline"}, headers=operacoes
        ).json()
        assert rover.device_id not in {d["id"] for d in por_estado}

    @pytest.mark.parametrize("papel", [PlatformRole.COMERCIAL])
    def test_sem_capacidade_nao_ve(self, client: TestClient, equipe, papel) -> None:
        assert client.get("/v1/platform/fleet", headers=equipe(papel)).status_code == 403

    @pytest.mark.parametrize(
        "papel", [PlatformRole.SUPORTE, PlatformRole.IA_DADOS, PlatformRole.SUPERADMIN]
    )
    def test_quem_ve(self, client: TestClient, equipe, papel) -> None:
        assert client.get("/v1/platform/fleet", headers=equipe(papel)).status_code == 200


def test_migracao_0016_ida_e_volta(tmp_path) -> None:
    from alembic import command
    from sqlalchemy import create_engine, inspect

    from valtexa import db

    url = f"sqlite:///{tmp_path / 'f.db'}"
    cfg = db.alembic_config(url)
    command.upgrade(cfg, "0016")
    colunas = {c["name"] for c in inspect(create_engine(url)).get_columns("device")}
    assert {"runtime_version", "dnaty_version", "sync_pending", "active_faults"} <= colunas
    command.downgrade(cfg, "0015")
    colunas = {c["name"] for c in inspect(create_engine(url)).get_columns("device")}
    assert "runtime_version" not in colunas and "sync_pending" not in colunas
