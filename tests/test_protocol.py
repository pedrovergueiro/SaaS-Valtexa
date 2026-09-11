"""Protocolo do dispositivo: provisionamento, ingestão, retomada e modo offline.

Estes testes cobrem as promessas que o firmware vai depender: que reenviar não
duplica, que a missão retoma do checkpoint, e que o estado só anda pelos
caminhos previstos.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from valtexa.models import (
    DeviceEvent,
    Mission,
    MissionKind,
    MissionState,
    TelemetrySample,
)
from valtexa.security import signing
from valtexa.services import ingestion, mission_manager

CAMPO = [[-45.4530, -22.4120], [-45.4500, -22.4120], [-45.4500, -22.4140], [-45.4530, -22.4140]]


class TestProvisioning:
    """Entrada de um robô na frota."""

    def test_provisiona_e_devolve_a_chave_publica_da_plataforma(
        self, client: TestClient, admin_token: dict
    ) -> None:
        token = _provisioning_token(client, admin_token, "P-1")
        keys = signing.generate_keypair()
        response = client.post(
            "/v1/device/provision",
            json={
                "provisioning_token": token,
                "serial_number": "P-1",
                "public_key": keys.public_key,
            },
        )
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["platform_public_key"] == signing.platform_public_key()
        assert body["key_id"].startswith("dk_")

    def test_convite_serve_uma_vez_so(self, client: TestClient, admin_token: dict) -> None:
        token = _provisioning_token(client, admin_token, "P-2")
        payload = {
            "provisioning_token": token,
            "serial_number": "P-2",
            "public_key": signing.generate_keypair().public_key,
        }
        assert client.post("/v1/device/provision", json=payload).status_code == 201
        segunda = client.post("/v1/device/provision", json=payload)
        assert segunda.status_code == 409

    def test_convite_amarrado_recusa_outro_numero_de_serie(
        self, client: TestClient, admin_token: dict
    ) -> None:
        """Roubar o convite de um robô não serve para cadastrar outro."""
        token = _provisioning_token(client, admin_token, "P-3")
        response = client.post(
            "/v1/device/provision",
            json={
                "provisioning_token": token,
                "serial_number": "OUTRO",
                "public_key": signing.generate_keypair().public_key,
            },
        )
        assert response.status_code == 403

    def test_convite_invalido_e_recusado(self, client: TestClient) -> None:
        response = client.post(
            "/v1/device/provision",
            json={
                "provisioning_token": "vtx_prov_inventado",
                "serial_number": "P-4",
                "public_key": signing.generate_keypair().public_key,
            },
        )
        assert response.status_code == 401

    def test_chave_publica_malformada_e_recusada(
        self, client: TestClient, admin_token: dict
    ) -> None:
        token = _provisioning_token(client, admin_token, "P-5")
        response = client.post(
            "/v1/device/provision",
            json={
                "provisioning_token": token,
                "serial_number": "P-5",
                "public_key": "chave-curta",
            },
        )
        assert response.status_code == 422


class TestIngestion:
    """Telemetria, eventos e sincronização offline."""

    def _sample(self, sequence: int) -> dict:
        return {
            "sequence_number": sequence,
            "recorded_at": datetime.now(UTC).isoformat(),
            "lat": -22.413,
            "lon": -45.4515,
            "battery_percent": 80.0,
        }

    def test_aceita_um_lote(self, frota: dict) -> None:
        result = ingestion.ingest_telemetry(
            frota["session"], frota["device"], [self._sample(1), self._sample(2)]
        )
        frota["session"].commit()
        assert result.accepted == 2

    def test_reenvio_e_idempotente(self, frota: dict) -> None:
        """A promessa central do modo offline.

        O robô pode reenviar o mesmo lote quantas vezes precisar — a conexão cai
        no meio da descarga, e reenviar é o comportamento correto do firmware.
        """
        session, device = frota["session"], frota["device"]
        lote = [self._sample(1), self._sample(2), self._sample(3)]

        primeiro = ingestion.ingest_telemetry(session, device, lote)
        session.commit()
        segundo = ingestion.ingest_telemetry(session, device, lote)
        session.commit()

        assert primeiro.accepted == 3
        assert segundo.accepted == 0
        assert segundo.duplicated == 3
        assert session.query(TelemetrySample).count() == 3

    def test_sequencia_fora_de_ordem_e_aceita(self, frota: dict) -> None:
        """Um lote preso offline chega fora de ordem, e é dado legítimo.

        Recusar sequência menor que a marca d'água jogaria fora exatamente o que
        a sincronização existe para recuperar.
        """
        session, device = frota["session"], frota["device"]
        ingestion.ingest_telemetry(session, device, [self._sample(10)])
        session.commit()
        atrasado = ingestion.ingest_telemetry(session, device, [self._sample(4)])
        session.commit()
        assert atrasado.accepted == 1

    def test_a_marca_dagua_nunca_retrocede(self, frota: dict) -> None:
        session, device = frota["session"], frota["device"]
        ingestion.ingest_telemetry(session, device, [self._sample(10)])
        session.commit()
        ingestion.ingest_telemetry(session, device, [self._sample(4)])
        session.commit()
        assert device.last_sequence_number == 10

    def test_amostra_sem_sequencia_e_recusada_sem_derrubar_o_lote(self, frota: dict) -> None:
        session, device = frota["session"], frota["device"]
        result = ingestion.ingest_telemetry(
            session, device, [self._sample(1), {"lat": 0.0}, self._sample(2)]
        )
        session.commit()
        assert result.accepted == 2
        assert result.rejected == 1
        assert result.errors

    def test_missao_de_outro_dispositivo_e_ignorada(self, frota: dict) -> None:
        """Um identificador alheio contaminaria o histórico do vizinho."""
        session, device = frota["session"], frota["device"]
        amostra = {**self._sample(1), "mission_id": "nao-existe"}
        result = ingestion.ingest_telemetry(session, device, [amostra])
        session.commit()
        assert result.accepted == 1
        assert session.query(TelemetrySample).one().mission_id is None

    def test_eventos_tambem_deduplicam(self, frota: dict) -> None:
        session, device = frota["session"], frota["device"]
        evento = {
            "sequence_number": 1,
            "type": "low_battery",
            "occurred_at": datetime.now(UTC).isoformat(),
        }
        ingestion.ingest_events(session, device, [evento])
        session.commit()
        repetido = ingestion.ingest_events(session, device, [evento])
        session.commit()
        assert repetido.duplicated == 1
        assert session.query(DeviceEvent).count() == 1

    def test_a_posicao_do_dispositivo_e_atualizada(self, frota: dict) -> None:
        session, device = frota["session"], frota["device"]
        ingestion.ingest_telemetry(session, device, [self._sample(1)])
        session.commit()
        assert device.last_lat == pytest.approx(-22.413)
        assert device.battery_percent == pytest.approx(80.0)


class TestMissionLifecycle:
    """Máquina de estados e retomada."""

    def _mission(self, frota: dict, kind: MissionKind = MissionKind.SCOUT) -> Mission:
        mission = mission_manager.create_mission(
            frota["session"],
            tenant_id=frota["tenant"].id,
            kind=kind,
            field_row=frota["field"],
            device=frota["device"],
        )
        frota["session"].commit()
        return mission

    def test_a_missao_nasce_em_rascunho_com_segmentos(self, frota: dict) -> None:
        mission = self._mission(frota)
        assert mission.state is MissionState.DRAFT
        assert mission.plan["segments"] > 0
        assert not mission.signature

    def test_a_area_padrao_respeita_a_margem(self, frota: dict) -> None:
        """Uma missão sobre a borda exata seria bloqueada por construção."""
        mission = self._mission(frota)
        assert mission.target_polygon != frota["field"].boundary

    def test_transicao_invalida_e_recusada(self, frota: dict) -> None:
        """A máquina de estados evita o caminho que ninguém previu com o robô no ar."""
        mission = self._mission(frota)
        with pytest.raises(mission_manager.MissionStateError):
            mission_manager.transition(frota["session"], mission, MissionState.RUNNING)

    def test_nao_despacha_sem_autorizacao(self, frota: dict) -> None:
        mission = self._mission(frota)
        with pytest.raises(mission_manager.MissionNotAuthorizedError):
            mission_manager.dispatch(frota["session"], mission)

    def test_autoriza_assina_e_despacha(self, frota: dict) -> None:
        session = frota["session"]
        mission = self._mission(frota)
        mission_manager.authorize(session, mission, wind_ms=2.0)
        session.commit()
        assert mission.state is MissionState.AUTHORIZED

        envelope = mission_manager.dispatch(session, mission)
        session.commit()
        assert mission.state is MissionState.DISPATCHED
        signing.verify_command(envelope["payload"], envelope["signature"])

    def test_o_comando_devolvido_e_sempre_o_mesmo(self, frota: dict) -> None:
        """Reassinar a cada leitura criaria dois comandos válidos para uma missão.

        O nonce precisa ser único por comando; duplicá-lo esvaziaria a proteção
        contra repetição.
        """
        session = frota["session"]
        mission = self._mission(frota)
        mission_manager.authorize(session, mission, wind_ms=2.0)
        primeiro = mission_manager.dispatch(session, mission)
        session.commit()
        segundo = mission_manager.rebuild_envelope(mission)
        assert primeiro == segundo

    def test_retoma_do_checkpoint_sem_refazer_tudo(self, frota: dict) -> None:
        """É o que torna o produto viável em área grande."""
        session = frota["session"]
        mission = self._mission(frota)
        mission_manager.authorize(session, mission, wind_ms=2.0)
        mission_manager.dispatch(session, mission)
        mission_manager.transition(session, mission, MissionState.RUNNING)
        total = len(mission.segments)

        mission_manager.complete_segment(session, mission, 0, battery_percent=40.0)
        mission_manager.pause_for_recharge(session, mission, battery_percent=22.0)
        session.commit()
        assert mission.state is MissionState.PAUSED_FOR_RECHARGE

        checkpoint = mission_manager.latest_checkpoint(session, mission)
        assert len(checkpoint.remaining_segments) == total - 1

        mission_manager.mark_ready_to_resume(session, mission)
        envelope = mission_manager.resume(session, mission)
        session.commit()
        assert mission.state is MissionState.RUNNING
        assert len(envelope["payload"]["body"]["segments"]) == total - 1

    def test_abortar_funciona_de_qualquer_estado_ativo(self, frota: dict) -> None:
        """Parar nunca pode falhar por estado."""
        session = frota["session"]
        mission = self._mission(frota)
        mission_manager.abort(session, mission, "teste")
        session.commit()
        assert mission.state is MissionState.ABORTED

    def test_abortar_libera_o_dispositivo(self, frota: dict) -> None:
        """Um ``active_mission_id`` parado travaria o robô para sempre."""
        session = frota["session"]
        mission = self._mission(frota)
        mission_manager.authorize(session, mission, wind_ms=2.0)
        mission_manager.dispatch(session, mission)
        session.commit()
        assert frota["device"].active_mission_id == mission.id

        mission_manager.abort(session, mission, "cancelada")
        session.commit()
        assert frota["device"].active_mission_id is None

    def test_politica_offline_de_pulverizacao_fecha_o_bico(self, frota: dict) -> None:
        """Aplicação é a única ação irreversível: é a última a seguir às cegas."""
        spray = mission_manager.default_offline_policy(MissionKind.SPRAY)
        scout = mission_manager.default_offline_policy(MissionKind.SCOUT)
        assert spray["stop_application"] is True
        assert spray["on_link_loss"] == "pause"
        assert scout["stop_application"] is False


def _provisioning_token(client: TestClient, headers: dict, serial: str) -> str:
    response = client.post(
        "/v1/provisioning-tokens",
        json={"device_model_code": "ROVER_SCOUT_V1", "serial_number": serial},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["token"]
