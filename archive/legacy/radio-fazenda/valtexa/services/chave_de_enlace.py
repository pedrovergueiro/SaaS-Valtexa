"""Chaves do rádio da fazenda pela plataforma, no lugar do ``pares.json`` copiado à mão.

1. **O robô publica** (``PUT /v1/device/enlace/chave``, assinado pela identidade dele):
   a pública X25519 do enlace, assinada pela Ed25519 do próprio robô
   (``valtexa-rover enlace-chave --publicar``). A plataforma confere a assinatura com a
   chave que **ela** cadastrou no provisionamento — ninguém publica chave em nome de outro
   robô.
2. **A base busca** (``GET /v1/device/base/pares``, só dispositivo ``gateway``) as chaves
   dos robôs da fazenda dela (do cliente dela, se a base não tem fazenda) e confere cada
   assinatura de novo antes de usar (``valtexa_base.plataforma``).

A plataforma nunca vê chave privada: só públicas e assinaturas. O texto assinado é o mesmo
de ``rover/valtexa_rover/enlace/cripto.py`` (o contrato confere em
``tests/test_contrato_sistemas.py``).
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from sqlalchemy import select
from sqlalchemy.orm import Session

from valtexa.models import ActorType, Device, DeviceCredential, DeviceModel, SubjectType
from valtexa.models.enums import DeviceKind, DeviceStatus
from valtexa.services import audit

ALGORITMO_PUBLICA = "VALTEXA-ENLACE-X25519-V1"
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_HEX128 = re.compile(r"^[0-9a-f]{128}$")


class ChaveInvalidaError(ValueError):
    pass


def confere(doc: dict, publica_ed25519_hex: str) -> None:
    nome, pub, assinatura = doc.get("nome"), doc.get("enlace_pub"), doc.get("assinatura")
    if not isinstance(nome, str) or not 1 <= len(nome) <= 64:
        raise ChaveInvalidaError("nome do nó ausente ou longo demais")
    if not isinstance(pub, str) or not _HEX64.match(pub):
        raise ChaveInvalidaError("enlace_pub precisa ser a pública X25519 em hex (64)")
    if not isinstance(assinatura, str) or not _HEX128.match(assinatura):
        raise ChaveInvalidaError("assinatura precisa ser Ed25519 em hex (128)")
    texto = f"{ALGORITMO_PUBLICA}\n{nome}\n{pub}".encode()
    try:
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(publica_ed25519_hex)).verify(
            bytes.fromhex(assinatura), texto)
    except (InvalidSignature, ValueError) as exc:
        raise ChaveInvalidaError("assinatura não confere com a identidade deste robô") from exc


def publica(session: Session, device: Device, credencial: DeviceCredential, doc: dict) -> dict:
    confere(doc, credencial.public_key)
    salvo = {"nome": doc["nome"], "enlace_pub": doc["enlace_pub"],
             "assinatura": doc["assinatura"], "ed25519_pub": credencial.public_key}
    mudou = device.enlace_chave != salvo
    device.enlace_chave = salvo
    device.enlace_chave_em = datetime.now(UTC)
    if mudou:
        audit.record(session, action="device.enlace_chave", subject_type=SubjectType.DEVICE,
                     subject_id=device.id, actor_type=ActorType.DEVICE, actor_id=device.id,
                     tenant_id=device.tenant_id, new_state=doc["enlace_pub"][:16])
    return salvo


def pares_da_base(session: Session, base: Device) -> dict[str, dict]:
    """As chaves dos robôs que esta base atende: mesma fazenda (ou mesmo cliente)."""
    consulta = (select(Device).join(DeviceModel, Device.device_model_id == DeviceModel.id)
                .where(DeviceModel.kind == DeviceKind.ROVER,
                       Device.status == DeviceStatus.ACTIVE,
                       Device.tenant_id == base.tenant_id,
                       Device.enlace_chave.is_not(None)))
    if base.farm_id:
        consulta = consulta.where(Device.farm_id == base.farm_id)
    return {d.enlace_chave["nome"]: {**d.enlace_chave, "device_id": d.id,
                                     "serial_number": d.serial_number}
            for d in session.scalars(consulta.order_by(Device.serial_number))}
