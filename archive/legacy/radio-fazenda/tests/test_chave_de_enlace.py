"""Chave do rádio da fazenda pela plataforma: o robô publica, a base busca."""

from __future__ import annotations

import secrets

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from sqlalchemy import select

from tests.helpers import provision
from valtexa.models import AuditEntry
from valtexa.services.chave_de_enlace import ALGORITMO_PUBLICA


def _doc(privada_hex: str, nome: str, pub: str | None = None) -> dict:
    pub = pub or secrets.token_hex(32)
    chave = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(privada_hex))
    assinatura = chave.sign(f"{ALGORITMO_PUBLICA}\n{nome}\n{pub}".encode()).hex()
    return {"nome": nome, "enlace_pub": pub, "assinatura": assinatura}


def test_robo_publica_e_a_base_busca(client, admin_token, demo, session) -> None:
    rover = provision(client, admin_token, "ROVER_SCOUT_V1", "RV-EN-01", demo["farm_id"])
    base = provision(client, admin_token, "FARM_BASE_V1", "BASE-EN-01", demo["farm_id"])
    assert base.request("GET", "/v1/device/base/pares").json() == {}  # ninguém publicou

    doc = _doc(rover.private_key, rover.device_id)
    r = rover.request("PUT", "/v1/device/enlace/chave", json_body=doc)
    assert r.status_code == 200 and r.json()["enlace_pub"] == doc["enlace_pub"]
    assert len(r.json()["ed25519_pub"]) == 64  # a pública que a plataforma cadastrou

    pares = base.request("GET", "/v1/device/base/pares").json()
    assert set(pares) == {rover.device_id}
    par = pares[rover.device_id]
    assert par["enlace_pub"] == doc["enlace_pub"] and par["serial_number"] == "RV-EN-01"

    # publicar de novo a mesma chave não audita de novo; trocar audita
    rover.request("PUT", "/v1/device/enlace/chave", json_body=doc)
    rover.request("PUT", "/v1/device/enlace/chave", json_body=_doc(rover.private_key,
                                                                   rover.device_id))
    trilha = session.scalars(select(AuditEntry).where(
        AuditEntry.action == "device.enlace_chave")).all()
    assert len(trilha) == 2


def test_assinatura_de_outro_e_recusada(client, admin_token, demo) -> None:
    rover = provision(client, admin_token, "ROVER_SCOUT_V1", "RV-EN-02", demo["farm_id"])
    outra = Ed25519PrivateKey.generate().private_bytes_raw().hex()
    r = rover.request("PUT", "/v1/device/enlace/chave",
                      json_body=_doc(outra, rover.device_id))
    assert r.status_code == 422 and "não confere" in r.text
    ruim = {**_doc(rover.private_key, rover.device_id), "enlace_pub": "zz" * 32}
    assert rover.request("PUT", "/v1/device/enlace/chave", json_body=ruim).status_code == 422


def test_so_a_base_busca_as_chaves(client, admin_token, demo) -> None:
    rover = provision(client, admin_token, "ROVER_SCOUT_V1", "RV-EN-03", demo["farm_id"])
    assert rover.request("GET", "/v1/device/base/pares").status_code == 403
