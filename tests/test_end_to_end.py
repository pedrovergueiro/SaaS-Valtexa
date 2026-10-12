"""Fluxo completo, do provisionamento à verificação.

É o teste que responde ao critério de conclusão do projeto: *a plataforma opera
hoje em modo totalmente simulado*. Ele percorre a mesma cadeia do
``python -m simulator``, mas sem servidor no ar — roda em CI, em segundos.

O que ele prova, em ordem:

1. um robô entra na frota gerando o próprio par de chaves;
2. uma varredura é planejada, aprovada pela segurança e assinada;
3. o robô verifica a assinatura antes de aceitar;
4. imagens viram observações, diagnósticos e recomendações;
5. uma pulverização é **bloqueada** sem aprovação e sem o tanque certo;
6. o agrônomo aprova, a segurança libera, o drone aplica;
7. a verificação pós-tratamento é agendada e a auditoria registra tudo.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from fastapi.testclient import TestClient
from helpers import frame, provision

from valtexa.models import MissionState
from valtexa.security import signing

ZONA = [
    [-45.863600, -21.902300],
    [-45.861400, -21.901600],
    [-45.859800, -21.903000],
    [-45.862200, -21.903600],
]


def test_fluxo_completo_sem_hardware(
    client: TestClient, demo: dict, admin_token: dict, agronomist_token: dict, operator_token: dict
) -> None:
    """Rover coleta, IA diagnostica, agrônomo aprova, drone aplica."""
    farm_id = demo["farm_id"]
    rover = provision(client, admin_token, "ROVER_SCOUT_V1", "E2E-ROVER", farm_id)
    drone = provision(client, admin_token, "DRONE_ACTION_V1", "E2E-DRONE", farm_id)
    dock = provision(client, admin_token, "DOCK_BASE_V1", "E2E-DOCK", farm_id)

    # --- a dock informa o vento; sem isso a pulverização é bloqueada ---
    assert (
        dock.request(
            "POST",
            "/v1/device/telemetry",
            json_body={
                "samples": [
                    {
                        "sequence_number": dock.next_sequence(),
                        "recorded_at": datetime.now(UTC).isoformat(),
                        "sensors": {"wind_ms": 2.5},
                    }
                ]
            },
        ).status_code
        == 200
    )
    for device in (rover, drone):
        device.request(
            "POST",
            "/v1/device/telemetry",
            json_body={
                "samples": [
                    {
                        "sequence_number": device.next_sequence(),
                        "recorded_at": datetime.now(UTC).isoformat(),
                        "battery_percent": 95.0,
                        "rtk_fix": "fixed",
                    }
                ]
            },
        )

    # --- varredura ---
    mission = client.post(
        "/v1/missions",
        json={
            "kind": "scout",
            "field_id": demo["field_id"],
            "zone_id": demo["zone_id"],
            "device_id": rover.device_id,
            "target_polygon": ZONA,
            "plan": {"swath_m": 40.0},
        },
        headers=operator_token,
    )
    assert mission.status_code == 201, mission.text
    mission_id = mission.json()["id"]

    evaluation = client.post(f"/v1/missions/{mission_id}/authorize", headers=operator_token)
    assert evaluation.json()["verdict"] == "safe_to_execute", evaluation.json()["blocked_reason"]

    dispatched = client.post(f"/v1/missions/{mission_id}/dispatch", headers=operator_token)
    assert dispatched.status_code == 200

    # O robô verifica a assinatura antes de obedecer.
    fetched = rover.request("GET", "/v1/device/missions/current")
    assert fetched.status_code == 200
    envelope = fetched.json()
    signing.verify_command(envelope["payload"], envelope["signature"])
    assert envelope["payload"]["device_id"] == rover.device_id

    rover.request(
        "POST",
        f"/v1/device/missions/{mission_id}/ack",
        json_body={"mission_id": mission_id, "accepted": True},
    )

    # --- observações: metade com doença, algumas com novidade ---
    for index in range(12):
        label = "Common_Rust" if index % 2 == 0 else "Healthy"
        novelty = 1.6 if index in (3, 7) else 0.3
        response = rover.request(
            "POST",
            "/v1/device/observations",
            files={"file": (f"f{index}.jpg", frame(label, novelty), "image/jpeg")},
            data={
                "metadata": json.dumps(
                    {
                        "sequence_number": rover.next_sequence(),
                        "mission_id": mission_id,
                        "field_id": demo["field_id"],
                        "zone_id": demo["zone_id"],
                        "captured_at": datetime.now(UTC).isoformat(),
                        "lat": -21.9029,
                        "lon": -45.8624,
                        "model_input_ok": True,
                    }
                )
            },
        )
        assert response.status_code == 201, response.text

    rover.request("POST", f"/v1/device/missions/{mission_id}/complete")

    observations = client.get(
        "/v1/observations", params={"field_id": demo["field_id"]}, headers=operator_token
    ).json()
    assert len(observations) == 12
    assert all(row["diagnosis_id"] for row in observations)

    # --- a novidade separa material para o agrônomo ---
    queue = client.get("/v1/review/queue", headers=agronomist_token).json()
    assert queue, "a novidade deveria ter separado ao menos um item"

    reviewed = client.post(
        f"/v1/diagnoses/{queue[0]['id']}/review",
        json={"label": "Gray_Leaf_Spot", "confirmed": True},
        headers=agronomist_token,
    )
    assert reviewed.status_code == 200
    # O rótulo do agrônomo pode não existir no catálogo do modelo: é assim que
    # uma doença nova entra no dataset próprio.
    assert reviewed.json()["reviewed_label"] == "Gray_Leaf_Spot"

    # --- uma recomendação sai do diagnóstico ---
    saudavel = next(row for row in observations if row["label"] == "Common_Rust")
    decision = client.post(
        f"/v1/diagnoses/{saudavel['diagnosis_id']}/decide", headers=operator_token
    )
    assert decision.status_code == 200
    assert decision.json()["outcome"] in {
        "application_candidate",
        "observe",
        "need_more_data",
        "human_review",
    }

    # --- pulverização: bloqueada duas vezes antes de passar ---
    tanks = client.get("/v1/tanks", params={"device_id": drone.device_id}, headers=admin_token)
    tank_id = tanks.json()[0]["id"]

    spray = client.post(
        "/v1/missions",
        json={
            "kind": "spray",
            "field_id": demo["field_id"],
            "zone_id": demo["zone_id"],
            "device_id": drone.device_id,
            "target_polygon": ZONA,
            "product_id": demo["product_id"],
            "product_batch_id": demo["batch_id"],
            "tank_id": tank_id,
            "authorized_rate_l_ha": 0.75,
            "authorized_quantity_l": 5.0,
        },
        headers=agronomist_token,
    )
    assert spray.status_code == 201, spray.text
    spray_id = spray.json()["id"]

    sem_aprovacao = client.post(f"/v1/missions/{spray_id}/authorize", headers=operator_token)
    assert sem_aprovacao.json()["verdict"] == "blocked"
    assert "approval" in sem_aprovacao.json()["blocked_code"]

    aprovada = client.post(
        f"/v1/missions/{spray_id}/approve", json={"confirm": True}, headers=agronomist_token
    )
    assert aprovada.status_code == 200

    sem_tanque = client.post(f"/v1/missions/{spray_id}/authorize", headers=operator_token)
    assert sem_tanque.json()["verdict"] == "blocked"

    carregado = client.post(
        f"/v1/tanks/{tank_id}/load",
        json={"product_id": demo["product_id"], "batch_id": demo["batch_id"], "volume_l": 10.0},
        headers=admin_token,
    )
    assert carregado.status_code == 200

    liberada = client.post(f"/v1/missions/{spray_id}/authorize", headers=operator_token)
    assert liberada.json()["verdict"] == "safe_to_execute", liberada.json()["blocked_reason"]

    # --- aplicação ---
    client.post(f"/v1/missions/{spray_id}/dispatch", headers=operator_token)
    drone.request(
        "POST",
        f"/v1/device/missions/{spray_id}/ack",
        json_body={"mission_id": spray_id, "accepted": True},
    )

    started = drone.request(
        "POST",
        "/v1/device/applications/start",
        json_body={
            "mission_id": spray_id,
            "started_at": datetime.now(UTC).isoformat(),
            "tank_id": tank_id,
        },
    )
    assert started.status_code == 201, started.text
    application_id = started.json()["id"]

    stopped = drone.request(
        "POST",
        f"/v1/device/applications/{application_id}/stop",
        json_body={
            "stopped_at": datetime.now(UTC).isoformat(),
            "amount_used_l": 4.2,
            "area_ha": 1.3,
            "track": [[-45.8624, -21.9029, 0.02], [-45.8622, -21.903, 0.02]],
        },
    )
    assert stopped.status_code == 200, stopped.text
    assert stopped.json()["outside_polygon_points"] == 0

    # --- verificação e auditoria ---
    verifications = client.get("/v1/verifications", headers=operator_token).json()
    assert verifications, "a aplicação deveria ter agendado uma verificação"
    assert verifications[0]["conclusion"] == "pending", "eficácia sem evidência não é declarada"

    trail = client.get("/v1/audit", params={"limit": 500}, headers=admin_token).json()
    acoes = {entry["action"] for entry in trail}
    assert {"device.provisioned", "mission.approved", "application.completed"} <= acoes

    aprovacao = next(e for e in trail if e["action"] == "mission.approved")
    assert aprovacao["actor_label"] == "agronomo@valtexa.dev"


def test_a_missao_de_pulverizacao_nunca_e_assinada_enquanto_bloqueada(
    client: TestClient, demo: dict, admin_token: dict, agronomist_token: dict
) -> None:
    """Sem parecer favorável não existe assinatura — nem por engano."""
    drone = provision(client, admin_token, "DRONE_ACTION_V1", "E2E-DRONE-2")
    spray = client.post(
        "/v1/missions",
        json={
            "kind": "spray",
            "field_id": demo["field_id"],
            "device_id": drone.device_id,
            "target_polygon": ZONA,
            "product_id": demo["product_id"],
            "product_batch_id": demo["batch_id"],
            "authorized_rate_l_ha": 0.75,
            "authorized_quantity_l": 5.0,
        },
        headers=agronomist_token,
    ).json()

    client.post(f"/v1/missions/{spray['id']}/authorize", headers=admin_token)
    despacho = client.post(f"/v1/missions/{spray['id']}/dispatch", headers=admin_token)
    assert despacho.status_code == 409

    detalhe = client.get(f"/v1/missions/{spray['id']}", headers=admin_token).json()
    assert detalhe["state"] == MissionState.BLOCKED.value
    assert detalhe["safety_status"] == "blocked"

    # E o robô não recebe nada.
    assert drone.request("GET", "/v1/device/missions/current").status_code == 204
