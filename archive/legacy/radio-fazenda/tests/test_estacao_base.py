"""A base da fazenda na plataforma: retrato, caminho até o Rover e alarmes."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from tests.helpers import provision, send_telemetry
from valtexa.models import Alert, Device
from valtexa.services import alertas

IA_OK = {"status": "ok", "detail": None}


def _retrato(**extra) -> dict:
    base = {
        "nome": "base-sede",
        "internet": {"ok": True, "quedas": 2, "ultima_falha": None},
        "uplink": {"P0": 0, "P1": 0, "P2": 3, "P3": 1, "P4": 40},
        "custodia": {"pendentes": 0},
        "rovers": [{"serial": "RT-0001", "vivo": True, "melhor": "subghz",
                    "em_travessia": False,
                    "enlaces": [
                        {"nome": "subghz", "estado": "vivo", "rtt_ms": 80.0, "perda": 0.02,
                         "vazao_bps": 900_000, "rssi_dbm": -78, "snr_db": 12, "quedas": 1},
                        {"nome": "wifi5", "estado": "morto", "rtt_ms": None, "perda": 1.0,
                         "vazao_bps": 0, "rssi_dbm": None, "snr_db": None, "quedas": 4}]}],
        "repetidoras": [{"nome": "rep-morro", "vivo": True, "bateria_pct": 64.0}],
    }
    base.update(extra)
    return base


@pytest.fixture
def fazenda(client, admin_token, demo):
    rover = provision(client, admin_token, "ROVER_SCOUT_V1", "RT-0001", demo["farm_id"])
    base = provision(client, admin_token, "FARM_BASE_V1", "BASE-01", demo["farm_id"])
    return rover, base


def test_retrato_da_base_e_caminho_do_rover(client, platform_token, fazenda) -> None:
    rover, base = fazenda
    painel = client.get(f"/v1/platform/rovers/{rover.device_id}/painel",
                        headers=platform_token).json()
    assert painel["caminho"] == {"modo": "direto"}  # nenhuma base o citou ainda

    assert send_telemetry(base, health={"base": _retrato(), "disk_percent": 31.0}
                          ).status_code == 200
    caminho = client.get(f"/v1/platform/rovers/{rover.device_id}/painel",
                         headers=platform_token).json()["caminho"]
    assert caminho["modo"] == "base" and caminho["base"]["serial_number"] == "BASE-01"
    assert caminho["nuvem_base"]["ok"] is True
    assert caminho["base_rover"]["melhor"] == "subghz"
    assert [e["estado"] for e in caminho["base_rover"]["enlaces"]] == ["vivo", "morto"]
    assert caminho["uplink"]["P4"] == 40

    bases = client.get("/v1/platform/bases", headers=platform_token).json()
    assert [b["serial_number"] for b in bases] == ["BASE-01"]
    assert bases[0]["rovers_vivos"] == 1 and bases[0]["repetidoras"][0]["bateria_pct"] == 64.0
    detalhe = client.get(f"/v1/platform/bases/{base.device_id}", headers=platform_token).json()
    assert detalhe["disk_percent"] == 31.0
    assert client.get(f"/v1/platform/bases/{rover.device_id}",
                      headers=platform_token).status_code == 404  # rover não é base


def test_retrato_e_padronizado(client, platform_token, fazenda, session) -> None:
    _rover, base = fazenda
    sujo = _retrato(rovers=[{"serial": "RT-0001", "vivo": "sim", "enlaces": [
        {"nome": "x", "estado": "ótimo", "perda": 7, "rtt_ms": -3, "rssi_dbm": 999}]},
        {"vivo": True}])
    send_telemetry(base, health={"base": sujo})
    salvo = session.get(Device, base.device_id).health["base"]
    r = salvo["rovers"]
    assert len(r) == 1 and r[0]["vivo"] is False  # sem serial não entra; "sim" não é True
    assert r[0]["enlaces"] == [{"nome": "x", "estado": None, "rtt_ms": None, "perda": None,
                                "vazao_bps": None, "rssi_dbm": None, "snr_db": None,
                                "quedas": None}]


def test_retrato_velho_nao_diz_o_caminho(client, platform_token, fazenda,
                                        session_factory) -> None:
    rover, base = fazenda
    send_telemetry(base, health={"base": _retrato()})
    with session_factory() as s:
        b = s.get(Device, base.device_id)
        b.health_reported_at = datetime.now(UTC) - timedelta(minutes=10)
        s.commit()
    painel = client.get(f"/v1/platform/rovers/{rover.device_id}/painel",
                        headers=platform_token).json()
    assert painel["caminho"] == {"modo": "direto"}


def test_alarmes_da_base(fazenda, session, session_factory) -> None:
    _rover, base = fazenda
    ruim = _retrato(
        uplink={"P0": 0, "P1": 20, "P2": 30, "P3": 10, "P4": 900},
        rovers=[{"serial": "RT-0001", "vivo": False, "enlaces": []},
                {"serial": "RT-0002", "vivo": True, "em_travessia": True, "enlaces": []}],
        repetidoras=[{"nome": "rep-morro", "vivo": True, "bateria_pct": 12.0},
                     {"nome": "rep-baixada", "vivo": False}])
    send_telemetry(base, health={"base": ruim})
    alertas.avaliar(session, ia=IA_OK)
    abertos = {a.kind: a for a in session.scalars(
        select(Alert).where(Alert.subject_id == base.device_id))}
    assert set(abertos) == {"enlace_degradado", "fila_base", "repetidora_bateria"}
    assert "RT-0001 sem nenhum rádio" in abertos["enlace_degradado"].message
    assert "RT-0002" not in abertos["enlace_degradado"].message  # zona morta mapeada
    assert abertos["fila_base"].value == 60.0  # P4 (lote) não conta
    assert "rep-baixada sem responder" in abertos["repetidora_bateria"].message

    with session_factory() as s:  # Starlink fora: a base cala
        b = s.get(Device, base.device_id)
        b.last_seen_at = datetime.now(UTC) - timedelta(minutes=12)
        s.commit()
    alertas.avaliar(session, ia=IA_OK)
    tipos = {a.kind for a in session.scalars(
        select(Alert).where(Alert.subject_id == base.device_id))}
    assert "base_sem_contato" in tipos and "rover_offline" not in tipos


def test_cliente_nao_ve_as_bases_da_plataforma(client, admin_token, fazenda) -> None:
    assert client.get("/v1/platform/bases", headers=admin_token).status_code in (401, 403)
