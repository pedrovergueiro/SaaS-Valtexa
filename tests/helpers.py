"""Utilitários dos testes que falam o protocolo do robô.

Separados das fixtures porque são funções comuns, chamadas com argumentos — e
porque vários arquivos de teste precisam provisionar um robô e assinar
requisições do mesmo jeito que o firmware vai fazer.
"""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from valtexa.security import signing
from valtexa.services import ai_pipeline


class DeviceSession:
    """Assina as requisições de um dispositivo contra o ``TestClient``."""

    def __init__(self, client: TestClient, device_id: str, key_id: str, private_key: str) -> None:
        self.client = client
        self.device_id = device_id
        self.key_id = key_id
        self.private_key = private_key
        self.sequence = 0

    def next_sequence(self) -> int:
        self.sequence += 1
        return self.sequence

    def request(self, method: str, path: str, *, json_body: dict | None = None, **kwargs):
        body = b"" if json_body is None else json.dumps(json_body).encode()
        headers = self._headers(method, path, body)
        if json_body is not None:
            headers["Content-Type"] = "application/json"
            return self.client.request(method, path, content=body, headers=headers)
        if "files" in kwargs or "data" in kwargs:
            # Multipart: o corpo é montado pelo httpx, então a assinatura precisa
            # ser calculada sobre os bytes exatos que ele produzir.
            request = self.client.build_request(method, path, **kwargs)
            raw = request.read()
            request.headers.update(self._headers(method, path, raw))
            return self.client.send(request)
        return self.client.request(method, path, headers=headers)

    def _headers(self, method: str, path: str, body: bytes) -> dict[str, str]:
        timestamp = str(int(time.time()))
        nonce = signing.new_nonce()
        return {
            signing.HEADER_KEY_ID: self.key_id,
            signing.HEADER_TIMESTAMP: timestamp,
            signing.HEADER_NONCE: nonce,
            signing.HEADER_SIGNATURE: signing.sign_request(
                self.private_key, method, path, "", timestamp, nonce, body
            ),
        }


def provision(
    client: TestClient, admin: dict, model_code: str, serial: str, farm_id: str | None = None
) -> DeviceSession:
    """Provisiona um dispositivo, opcionalmente vinculado a uma fazenda.

    O vínculo importa: a leitura de vento que libera a pulverização é procurada
    entre as docks *daquela* fazenda. Um dispositivo sem fazenda existe, opera e
    reporta — mas o vento dele não vale para lugar nenhum.
    """
    token = client.post(
        "/v1/provisioning-tokens",
        json={"device_model_code": model_code, "serial_number": serial, "farm_id": farm_id},
        headers=admin,
    )
    assert token.status_code == 201, token.text

    keys = signing.generate_keypair()
    response = client.post(
        "/v1/device/provision",
        json={
            "provisioning_token": token.json()["token"],
            "serial_number": serial,
            "public_key": keys.public_key,
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["platform_public_key"] == signing.platform_public_key()
    return DeviceSession(client, body["device_id"], body["key_id"], keys.private_key)


def frame(label: str, novelty: float = 0.3) -> bytes:
    """Quadro simulado com a resposta esperada anexada ao fim do arquivo."""
    jpeg = b"\xff\xd8\xff\xe0" + b"\x00" * 32 + b"\xff\xd9"
    return jpeg + ai_pipeline.SIMULATION_MARKER + f"{label}:{novelty}".encode()


def send_telemetry(device: DeviceSession, **sample: object):
    """Uma amostra, com sequência e horário preenchidos."""
    payload = {
        "sequence_number": device.next_sequence(),
        "recorded_at": datetime.now(UTC).isoformat(),
        "rtk_fix": "fixed",
        **sample,
    }
    return device.request("POST", "/v1/device/telemetry", json_body={"samples": [payload]})


def send_event(device: DeviceSession, event_type: str, severity: str = "info", **payload: object):
    record = {
        "sequence_number": device.next_sequence(),
        "type": event_type,
        "severity": severity,
        "occurred_at": datetime.now(UTC).isoformat(),
        "payload": payload,
    }
    return device.request("POST", "/v1/device/events", json_body={"events": [record]})


def upload_observation(
    device: DeviceSession,
    field_id: str,
    *,
    label: str = "Healthy",
    novelty: float = 0.3,
    zone_id: str | None = None,
    mission_id: str | None = None,
    captured_at: datetime | None = None,
    lat: float = -12.7240,
    lon: float = -55.9075,
):
    sequence = device.next_sequence()
    metadata = {
        "sequence_number": sequence,
        "field_id": field_id,
        "zone_id": zone_id,
        "mission_id": mission_id,
        "captured_at": (captured_at or datetime.now(UTC)).isoformat(),
        "lat": lat,
        "lon": lon,
        "model_input_ok": True,
    }
    return device.request(
        "POST",
        "/v1/device/observations",
        files={"file": (f"f{sequence}.jpg", frame(label, novelty), "image/jpeg")},
        data={"metadata": json.dumps(metadata)},
    )
