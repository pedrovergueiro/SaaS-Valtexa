"""Centro de comando do Rover: comandos assinados, controle remoto e modelo fixado."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from tests.helpers import provision
from valtexa.models import Device, ModelVersion
from valtexa.security import signing


@pytest.fixture
def rover(client, admin_token, demo):
    return provision(client, admin_token, "ROVER_SCOUT_V1", "RV3-CC-01", demo["farm_id"])


def _url(rover, resto: str = "") -> str:
    return f"/v1/platform/rovers/{rover.device_id}{resto}"


def test_comando_assinado_ida_e_volta(client, platform_token, rover) -> None:
    r = client.post(_url(rover, "/comandos"), headers=platform_token,
                    json={"kind": "diagnostico", "params": {"pecas": ["gnss", "camera:esq-450"]}})
    assert r.status_code == 201, r.text
    comando_id = r.json()["id"]

    entregues = rover.request("GET", "/v1/device/commands").json()
    assert len(entregues) == 1
    envelope = entregues[0]
    # O robô confere a assinatura com a chave pública da plataforma antes de obedecer.
    signing.verify_command(envelope["payload"], envelope["signature"])
    corpo = envelope["payload"]["body"]
    assert envelope["payload"]["device_id"] == rover.device_id
    assert corpo == {"command_id": comando_id, "kind": "diagnostico",
                     "params": {"pecas": ["gnss", "camera:esq-450"]}}
    assert rover.request("GET", "/v1/device/commands").json() == []  # entregue uma vez

    laudo = {"ok": True, "pecas": {"gnss": {"ok": True, "fix": "fixed"}}}
    assert rover.request("POST", f"/v1/device/commands/{comando_id}/result",
                         json_body={"ok": True, "result": laudo}).status_code == 200
    painel = client.get(_url(rover, "/painel"), headers=platform_token).json()
    ultimo = painel["commands"][0]
    assert ultimo["state"] == "concluido" and ultimo["result"] == laudo
    assert painel["device"]["id"] == rover.device_id and "telemetry" in painel


def test_comando_invalido_e_cancelamento(client, platform_token, rover) -> None:
    assert client.post(_url(rover, "/comandos"), headers=platform_token,
                       json={"kind": "voar"}).status_code == 422
    assert client.post(_url(rover, "/comandos"), headers=platform_token,
                       json={"kind": "modo", "params": {"modo": "turbo"}}).status_code == 422
    r = client.post(_url(rover, "/comandos"), headers=platform_token,
                    json={"kind": "foto", "params": {"camera_id": "esq-1000"}})
    cid = r.json()["id"]
    assert client.post(_url(rover, f"/comandos/{cid}/cancelar"),
                       headers=platform_token).json()["state"] == "cancelado"
    assert rover.request("GET", "/v1/device/commands").json() == []


def test_controle_remoto_so_em_manual_com_homem_morto(client, platform_token, rover,
                                                       session_factory) -> None:
    assert client.post(_url(rover, "/teleop"), headers=platform_token,
                       json={"v": 0.3, "w": 0.0}).status_code == 409  # não está em manual

    cid = client.post(_url(rover, "/comandos"), headers=platform_token,
                      json={"kind": "modo", "params": {"modo": "manual"}}).json()["id"]
    rover.request("GET", "/v1/device/commands")
    rover.request("POST", f"/v1/device/commands/{cid}/result", json_body={"ok": True})

    assert client.post(_url(rover, "/teleop"), headers=platform_token,
                       json={"v": 1.5, "w": 0.0}).status_code == 409  # acima de 0,5 m/s
    estado = client.post(_url(rover, "/teleop"), headers=platform_token,
                         json={"v": 0.3, "w": -0.2}).json()
    assert estado["active"] and estado["v"] == 0.3

    ponto = rover.request("GET", "/v1/device/teleop").json()
    signing.verify_command(ponto["payload"], ponto["signature"])
    assert ponto["payload"]["body"]["v"] == 0.3 and ponto["payload"]["command"] == "device.teleop"
    seq = ponto["payload"]["sequence"]

    with session_factory() as s:  # 1 s sem renovar: o ponto vence
        robo = s.get(Device, rover.device_id)
        robo.teleop_until = datetime.now(UTC) - timedelta(seconds=1)
        s.commit()
    assert rover.request("GET", "/v1/device/teleop").status_code == 204

    parar = client.post(_url(rover, "/teleop/parar"), headers=platform_token).json()
    assert parar["v"] == 0.0 and parar["seq"] == seq + 1


def test_modelo_fixado_vale_na_designacao(client, platform_token, rover, session_factory,
                                          demo) -> None:
    with session_factory() as s:
        versao = s.scalars(select(ModelVersion).where(
            ModelVersion.model_key == "coffee-foliar")).first()
        versao.original_artifact_sha256 = "a" * 64
        versao.original_artifact_uri = "s3://modelos/cafe.onnx"
        chave, rotulo = versao.model_key, versao.version
        s.commit()
    disponiveis = client.get(_url(rover, "/modelos"), headers=platform_token).json()
    assert any(m["model_key"] == chave and m["version"] == rotulo for m in disponiveis)

    r = client.put(_url(rover, "/modelo"), headers=platform_token,
                   json={"model_key": chave, "version": rotulo})
    assert r.status_code == 200, r.text
    designados = rover.request("GET", "/v1/device/models").json()
    cafe = [d for d in designados if d["crop"] == "coffee"]
    assert cafe and all(d["model_key"] == chave and d["artifact_sha256"] == "a" * 64
                        for d in cafe)
    # Fixar já pede ao robô que recarregue os modelos.
    assert [c["payload"]["body"]["kind"] for c in rover.request(
        "GET", "/v1/device/commands").json()] == ["recarregar_modelos"]

    assert client.put(_url(rover, "/modelo"), headers=platform_token,
                      json={"model_key": "nao-existe", "version": "0"}).status_code == 422
    assert client.put(_url(rover, "/modelo"), headers=platform_token,
                      json={"model_key": None}).json() == {"pinned_model": None}


def test_cliente_nao_entra_no_centro_de_comando(client, admin_token, rover) -> None:
    assert client.get(_url(rover, "/painel"), headers=admin_token).status_code in (401, 403)
    assert client.post(_url(rover, "/comandos"), headers=admin_token,
                       json={"kind": "parar"}).status_code in (401, 403)
