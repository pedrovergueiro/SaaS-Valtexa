"""Rotas do console: telemetria, eventos, alertas, painel, stream e usuários."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from helpers import provision, send_event, send_telemetry, upload_observation

from valtexa.main import _mount_console


def test_telemetria_volta_em_ordem_cronologica(
    client: TestClient, demo: dict, admin_token: dict
) -> None:
    rover = provision(client, admin_token, "ROVER_SCOUT_V1", "C-ROVER-1", demo["farm_id"])
    for battery in (90.0, 80.0, 70.0):
        assert send_telemetry(rover, battery_percent=battery).status_code == 200

    rows = client.get(f"/v1/devices/{rover.device_id}/telemetry", headers=admin_token).json()
    assert [row["battery_percent"] for row in rows] == [90.0, 80.0, 70.0]


def test_eventos_do_dispositivo(client: TestClient, demo: dict, admin_token: dict) -> None:
    rover = provision(client, admin_token, "ROVER_SCOUT_V1", "C-ROVER-2", demo["farm_id"])
    send_event(rover, "fault_detected", severity="critical", motor="fl")

    events = client.get(f"/v1/devices/{rover.device_id}/events", headers=admin_token).json()
    assert events[0]["type"] == "fault_detected"
    assert events[0]["severity"] == "critical"
    assert events[0]["payload"] == {"motor": "fl"}


def test_dispositivo_de_outro_cliente_devolve_404(client: TestClient, admin_token: dict) -> None:
    response = client.get(f"/v1/devices/{'0' * 32}/telemetry", headers=admin_token)
    assert response.status_code == 404


def test_alertas_vem_do_mais_grave_ao_mais_leve(
    client: TestClient, demo: dict, admin_token: dict
) -> None:
    rover = provision(client, admin_token, "ROVER_SCOUT_V1", "C-ROVER-3", demo["farm_id"])
    send_telemetry(rover, battery_percent=20.0)
    send_event(rover, "fault_detected", severity="critical")
    # Uma dock que nunca mandou telemetria: sem contato desde o provisionamento.
    provision(client, admin_token, "DOCK_BASE_V1", "C-DOCK-1", demo["farm_id"])

    alerts = client.get("/v1/alerts", headers=admin_token).json()
    kinds = {alert["kind"] for alert in alerts}
    assert {"device_fault", "low_battery", "device_offline"} <= kinds

    order = ["critical", "warning", "info"]
    severities = [alert["severity"] for alert in alerts]
    assert severities == sorted(severities, key=order.index)


def test_painel_resume_o_cliente(client: TestClient, demo: dict, admin_token: dict) -> None:
    rover = provision(client, admin_token, "ROVER_SCOUT_V1", "C-ROVER-4", demo["farm_id"])
    send_telemetry(rover, battery_percent=95.0)
    upload_observation(rover, demo["field_id"], label="Common_Rust", novelty=1.8)

    board = client.get("/v1/dashboard", headers=admin_token).json()
    assert board["devices"]["total"] == 1
    assert board["devices"]["online"] == 1
    assert board["observations_7d"] == 1
    assert board["labels_7d"] == {"Common_Rust": 1}
    # Novidade acima do limiar: foi para o agrônomo.
    assert board["review_queue"] == 1
    assert set(board["alert_counts"]) == {"critical", "warning", "info"}


def test_operador_acompanha_a_missao_sem_ler_a_auditoria(
    client: TestClient, demo: dict, admin_token: dict, operator_token: dict
) -> None:
    rover = provision(client, admin_token, "ROVER_SCOUT_V1", "C-ROVER-5", demo["farm_id"])
    send_telemetry(rover, battery_percent=95.0)
    mission = client.post(
        "/v1/missions",
        json={"kind": "scout", "field_id": demo["field_id"], "device_id": rover.device_id},
        headers=operator_token,
    ).json()
    client.post(f"/v1/missions/{mission['id']}/authorize", headers=operator_token)

    assert client.get("/v1/audit", headers=operator_token).status_code == 403
    history = client.get(f"/v1/missions/{mission['id']}/history", headers=operator_token)
    assert history.status_code == 200
    states = [entry["new_state"] for entry in history.json() if entry["new_state"]]
    assert states[:3] == ["draft", "pending_safety", "authorized"]


def test_stream_entrega_os_eventos_do_cliente(
    client: TestClient, demo: dict, admin_token: dict, operator_token: dict
) -> None:
    start = (datetime.now(UTC) - timedelta(seconds=5)).isoformat()
    rover = provision(client, admin_token, "ROVER_SCOUT_V1", "C-ROVER-6", demo["farm_id"])
    send_telemetry(rover, battery_percent=95.0)
    client.post(
        "/v1/missions",
        json={"kind": "scout", "field_id": demo["field_id"], "device_id": rover.device_id},
        headers=operator_token,
    )

    response = client.get(
        "/v1/stream", params={"after": start, "timeout": 1, "poll": 0.1}, headers=admin_token
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    body = response.text
    assert "event: device.provisioned" in body
    assert "event: mission.created" in body
    assert "event: stream.end" in body


def test_stream_exige_autenticacao(client: TestClient) -> None:
    assert client.get("/v1/stream", params={"timeout": 1}).status_code == 401


def test_muda_papel_e_remove_do_cliente(client: TestClient, admin_token: dict) -> None:
    created = client.post(
        "/v1/users",
        json={
            "email": "novo@valtexa.dev",
            "full_name": "Pessoa Nova",
            "password": "senha-forte-123",
            "role": "viewer",
        },
        headers=admin_token,
    ).json()

    changed = client.patch(
        f"/v1/users/{created['id']}", json={"role": "agronomist"}, headers=admin_token
    )
    assert changed.json()["role"] == "agronomist"

    me = client.get("/v1/auth/me", headers=admin_token).json()
    proprio = client.patch(f"/v1/users/{me['id']}", json={"role": "viewer"}, headers=admin_token)
    assert proprio.status_code == 409, "ninguém rebaixa a si mesmo e tranca o cliente"

    assert client.delete(f"/v1/users/{created['id']}", headers=admin_token).status_code == 204
    emails = [user["email"] for user in client.get("/v1/users", headers=admin_token).json()]
    assert "novo@valtexa.dev" not in emails


def test_todos_os_talhoes_do_cliente(client: TestClient, demo: dict, operator_token: dict) -> None:
    rows = client.get("/v1/fields", headers=operator_token).json()
    assert [row["id"] for row in rows] == [demo["field_id"]]


def test_observacoes_recortadas_por_janela(
    client: TestClient, demo: dict, admin_token: dict
) -> None:
    rover = provision(client, admin_token, "ROVER_SCOUT_V1", "C-ROVER-7", demo["farm_id"])
    upload_observation(rover, demo["field_id"], captured_at=datetime.now(UTC) - timedelta(days=10))
    upload_observation(rover, demo["field_id"])

    since = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    rows = client.get(
        "/v1/observations",
        params={"field_id": demo["field_id"], "since": since},
        headers=admin_token,
    ).json()
    assert len(rows) == 1


def test_console_servido_com_fallback_de_spa(tmp_path: Path) -> None:
    """Qualquer rota do navegador cai no index; rota de API inexistente, não."""
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>console</title>")
    (dist / "assets" / "app.js").write_text("console.log(1)")
    (dist / "favicon.svg").write_text("<svg/>")

    app = FastAPI()

    @app.get("/v1/ping")
    def ping() -> dict:
        return {"ok": True}

    _mount_console(app, dist)
    web = TestClient(app)

    assert web.get("/missoes/123").text.startswith("<!doctype html>")
    assert web.get("/assets/app.js").text == "console.log(1)"
    assert web.get("/favicon.svg").text == "<svg/>"
    assert web.get("/v1/ping").json() == {"ok": True}
    assert web.get("/v1/nada").status_code == 404


def test_horarios_saem_com_fuso(client: TestClient, demo: dict, admin_token: dict) -> None:
    """Sem fuso, o navegador leria UTC como hora local."""
    rover = provision(client, admin_token, "ROVER_SCOUT_V1", "C-ROVER-8", demo["farm_id"])
    send_telemetry(rover, battery_percent=90.0)
    row = client.get(f"/v1/devices/{rover.device_id}/telemetry", headers=admin_token).json()[0]
    assert row["recorded_at"].endswith(("Z", "+00:00"))
    assert row["received_at"].endswith(("Z", "+00:00"))


def test_lista_de_clientes_sem_cliente_ativo(client: TestClient, admin_token: dict) -> None:
    headers = {"Authorization": admin_token["Authorization"]}
    rows = client.get("/v1/auth/memberships", headers=headers).json()
    assert [row["tenant_slug"] for row in rows] == ["fazenda-demo"]

