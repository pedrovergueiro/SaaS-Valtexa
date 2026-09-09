"""Cliente assinado do protocolo — o SDK que o firmware vai reimplementar.

Este arquivo é a referência executável de ``docs/DEVICE_PROTOCOL.md``. Quem for
escrever o firmware do rover ou do drone reproduz o que está aqui: gerar o par
de chaves, provisionar, assinar cada requisição e verificar o comando recebido.

Nada aqui é específico de simulação. É o cliente de verdade, e o simulador o usa
justamente para que o protocolo seja exercitado do jeito que o hardware vai
exercitar.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import UTC, datetime

import httpx

from valtexa.security import signing


class ProtocolError(RuntimeError):
    """O servidor recusou a requisição."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(f"HTTP {status_code}: {detail}")
        self.status_code = status_code
        self.detail = detail


@dataclass
class DeviceIdentity:
    """O que o robô guarda em memória não volátil depois do provisionamento.

    A chave privada nunca sai daqui. Num robô de verdade isto vive num elemento
    seguro ou, no mínimo, num arquivo com permissão restrita.
    """

    device_id: str
    tenant_id: str
    key_id: str
    private_key: str
    public_key: str
    platform_public_key: str
    serial_number: str


@dataclass
class DeviceClient:
    """Fala com a nuvem assinando cada requisição."""

    base_url: str
    identity: DeviceIdentity
    timeout: float = 30.0
    _sequence: int = field(default=0, init=False)
    _http: httpx.Client = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._http = httpx.Client(base_url=self.base_url.rstrip("/"), timeout=self.timeout)

    # --- provisionamento ----------------------------------------------------
    @classmethod
    def provision(
        cls,
        base_url: str,
        provisioning_token: str,
        serial_number: str,
        *,
        name: str | None = None,
        firmware_version: str = "sim-1.0.0",
        hardware_version: str = "sim-1",
        timeout: float = 30.0,
    ) -> DeviceClient:
        """Primeiro boot: gera o par de chaves e troca o convite por identidade.

        A privada é gerada **aqui**, no dispositivo, e só a pública sobe. É o que
        garante que nem a plataforma consegue se passar por este robô.
        """
        keypair = signing.generate_keypair()
        with httpx.Client(base_url=base_url.rstrip("/"), timeout=timeout) as http:
            response = http.post(
                "/v1/device/provision",
                json={
                    "provisioning_token": provisioning_token,
                    "serial_number": serial_number,
                    "public_key": keypair.public_key,
                    "name": name,
                    "firmware_version": firmware_version,
                    "hardware_version": hardware_version,
                    "protocol_version": "1.0",
                },
            )
        _raise_for_status(response)
        body = response.json()

        identity = DeviceIdentity(
            device_id=body["device_id"],
            tenant_id=body["tenant_id"],
            key_id=body["key_id"],
            private_key=keypair.private_key,
            public_key=keypair.public_key,
            platform_public_key=body["platform_public_key"],
            serial_number=serial_number,
        )
        return cls(base_url=base_url, identity=identity, timeout=timeout)

    # --- transporte ---------------------------------------------------------
    def request(
        self,
        method: str,
        path: str,
        *,
        json: dict | None = None,
        files: dict | None = None,
        data: dict | None = None,
        params: dict | None = None,
    ) -> httpx.Response:
        """Assina e envia.

        A assinatura é calculada sobre o corpo **já serializado**: montar a
        requisição primeiro e assinar depois é a única forma de o que foi
        assinado ser exatamente o que vai pelo fio. Assinar um dicionário e
        serializar depois abriria uma brecha entre as duas coisas.
        """
        request = self._http.build_request(
            method, path, json=json, files=files, data=data, params=params
        )
        # ``read()`` materializa o corpo. Um multipart (o upload de imagem) é
        # montado em streaming, e sem isto não haveria bytes para assinar — o
        # firmware tem a mesma restrição: só dá para assinar o que já existe
        # inteiro na memória.
        body = request.read()
        timestamp = str(int(time.time()))
        nonce = signing.new_nonce()
        signature = signing.sign_request(
            self.identity.private_key,
            method,
            request.url.path,
            request.url.query.decode("ascii"),
            timestamp,
            nonce,
            body,
        )
        request.headers[signing.HEADER_KEY_ID] = self.identity.key_id
        request.headers[signing.HEADER_TIMESTAMP] = timestamp
        request.headers[signing.HEADER_NONCE] = nonce
        request.headers[signing.HEADER_SIGNATURE] = signature

        response = self._http.send(request)
        _raise_for_status(response)
        return response

    def next_sequence(self) -> int:
        """Contador monotônico único do dispositivo.

        Um só para telemetria, eventos e observações. É o que torna a
        sincronização offline idempotente: reenviar o mesmo par
        (dispositivo, sequência) é ignorado pelo servidor, não duplicado.
        """
        self._sequence += 1
        return self._sequence

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> DeviceClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    # --- operações do protocolo --------------------------------------------
    def server_time(self) -> datetime:
        """Relógio do servidor, para alinhar antes de assinar."""
        response = self._http.get("/v1/device/time")
        _raise_for_status(response)
        return datetime.fromisoformat(response.json()["server_time"])

    def send_telemetry(self, samples: list[dict], sync_id: str | None = None) -> dict:
        return self.request(
            "POST", "/v1/device/telemetry", json={"samples": samples, "sync_id": sync_id}
        ).json()

    def send_events(self, records: list[dict], sync_id: str | None = None) -> dict:
        return self.request(
            "POST", "/v1/device/events", json={"events": records, "sync_id": sync_id}
        ).json()

    def sync(self, sync_id: str, samples: list[dict], records: list[dict]) -> dict:
        """Descarrega tudo que ficou preso offline. Pode ser repetido à vontade."""
        return self.request(
            "POST",
            "/v1/device/sync",
            json={"sync_id": sync_id, "samples": samples, "events": records},
        ).json()

    def upload_observation(self, metadata: dict, image: bytes, filename: str) -> dict:
        return self.request(
            "POST",
            "/v1/device/observations",
            files={"file": (filename, image, "image/jpeg")},
            data={"metadata": _compact_json(metadata)},
        ).json()

    def fetch_mission(self) -> dict | None:
        """Busca a missão pendente e **verifica a assinatura antes de devolver**.

        Esta verificação é o coração da segurança do lado do robô. Um comando
        que não passe por ela nunca deve chegar aos atuadores — nem o que veio
        de um servidor falso, nem o que foi adulterado no caminho, nem o que
        alguém gravou ontem e está reenviando hoje.

        Devolve o **corpo** do comando, já validado. Os campos de controle do
        envelope (destinatário, sequência, nonce, validade) são conferidos aqui
        e não seguem adiante: o que chega ao resto do firmware é só o que ele
        deve executar, e nunca um envelope ainda por verificar.
        """
        response = self.request("GET", "/v1/device/missions/current")
        if response.status_code == 204:
            return None

        envelope = response.json()
        payload = envelope["payload"]
        signing.verify_command(payload, envelope["signature"], self.identity.platform_public_key)

        if payload["device_id"] != self.identity.device_id:
            raise ProtocolError(403, "Comando endereçado a outro dispositivo.")
        if signing.command_is_expired(payload):
            raise ProtocolError(409, "Comando expirado; descartado sem executar.")
        return payload["body"]

    def ack_mission(self, mission_id: str, accepted: bool, reason: str | None = None) -> dict:
        return self.request(
            "POST",
            f"/v1/device/missions/{mission_id}/ack",
            json={"mission_id": mission_id, "accepted": accepted, "reason": reason},
        ).json()

    def complete_segment(self, mission_id: str, index: int, **state: float) -> dict:
        return self.request(
            "POST",
            f"/v1/device/missions/{mission_id}/segments/complete",
            json={"segment_index": index, **state},
        ).json()

    def pause_mission(self, mission_id: str, reason: str, **state: float) -> dict:
        return self.request(
            "POST", f"/v1/device/missions/{mission_id}/pause", json={"reason": reason, **state}
        ).json()

    def report_recharged(self, mission_id: str) -> dict:
        return self.request("POST", f"/v1/device/missions/{mission_id}/recharged").json()

    def complete_mission(self, mission_id: str) -> dict:
        return self.request("POST", f"/v1/device/missions/{mission_id}/complete").json()

    def start_application(self, mission_id: str, tank_id: str | None = None) -> dict:
        return self.request(
            "POST",
            "/v1/device/applications/start",
            json={
                "mission_id": mission_id,
                "started_at": datetime.now(UTC).isoformat(),
                "tank_id": tank_id,
            },
        ).json()

    def stop_application(
        self,
        application_id: str,
        amount_used_l: float,
        area_ha: float,
        track: list[list[float]],
        stop_reason: str | None = None,
    ) -> dict:
        return self.request(
            "POST",
            f"/v1/device/applications/{application_id}/stop",
            json={
                "stopped_at": datetime.now(UTC).isoformat(),
                "amount_used_l": amount_used_l,
                "area_ha": area_ha,
                "track": track,
                "stop_reason": stop_reason,
            },
        ).json()


def _compact_json(payload: dict) -> str:
    import json

    return json.dumps(payload, separators=(",", ":"), default=str)


def _raise_for_status(response: httpx.Response) -> None:
    if response.status_code < 400:
        return
    try:
        detail = response.json().get("detail", response.text)
    except ValueError:
        detail = response.text
    raise ProtocolError(response.status_code, str(detail))
