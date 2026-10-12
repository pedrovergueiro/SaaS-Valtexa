"""Recibo assinado das respostas do dispositivo (Parte 13, base da fazenda hostil).

Com o Rover falando pela base, um "200 aceito" fabricado pela base faria o robô apagar da
fila o que nunca chegou. A plataforma assina ``nonce | status | sha256(corpo)`` quando o
robô pede; o Runtime (``rover/valtexa_rover/enlace/rpc.py``) confere com a mesma conta.
"""

from __future__ import annotations

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from helpers import provision, send_telemetry
from valtexa_rover.enlace.rpc import confere_recibo

from valtexa.api.middleware import texto_do_recibo
from valtexa.security import signing


def test_recibo_assinado_amarrado_ao_nonce_status_e_corpo(client, admin_token, demo) -> None:
    rover = provision(client, admin_token, "ROVER_SCOUT_V1", "REC-1", demo["farm_id"])
    original = rover._headers

    def com_recibo(method, path, body):
        return {**original(method, path, body), "X-Valtexa-Recibo": "1"}

    rover._headers = com_recibo
    r = send_telemetry(rover, battery_pct=80)
    assert r.status_code < 300, r.text
    assinatura = r.headers["x-valtexa-recibo-assinatura"]
    nonce = r.request.headers["X-Valtexa-Nonce"]
    chave = Ed25519PublicKey.from_public_bytes(bytes.fromhex(signing.platform_public_key()))
    chave.verify(bytes.fromhex(assinatura), texto_do_recibo(nonce, r.status_code, r.content))
    # o Runtime do Rover confere com a mesma conta
    assert confere_recibo(signing.platform_public_key(), nonce, r.status_code, r.content,
                          dict(r.headers))
    assert not confere_recibo(signing.platform_public_key(), nonce, r.status_code,
                              r.content + b" ", dict(r.headers))
    assert not confere_recibo(signing.platform_public_key(), "outro-nonce", r.status_code,
                              r.content, dict(r.headers))
    # recusa (401) também é assinada — honesta, não serve de "aceito"
    rover._headers = lambda m, p, b: {**com_recibo(m, p, b), signing.HEADER_SIGNATURE: "00"}
    r = send_telemetry(rover, battery_pct=80)
    assert r.status_code == 401 and "x-valtexa-recibo-assinatura" in r.headers


def test_sem_pedido_de_recibo_ou_em_get_nada_muda(client, admin_token, demo) -> None:
    rover = provision(client, admin_token, "ROVER_SCOUT_V1", "REC-2", demo["farm_id"])
    r = send_telemetry(rover, battery_pct=70)
    assert r.status_code < 300 and "x-valtexa-recibo-assinatura" not in r.headers
    original = rover._headers
    rover._headers = lambda m, p, b: {**original(m, p, b), "X-Valtexa-Recibo": "1"}
    r = rover.request("GET", "/v1/device/missions/current")
    assert "x-valtexa-recibo-assinatura" not in r.headers
