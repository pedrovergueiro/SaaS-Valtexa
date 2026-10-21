"""A base da fazenda na plataforma: o retrato dela e o caminho nuvem → base → rádios → Rover.

A base (VALTEXA-BASE, modelo ``FARM_BASE_V1``, tipo ``gateway``) é provisionada como um
robô e manda, assinado por ela, o ``health.base`` (padronizado em
:func:`valtexa.services.saude_rover._base`): internet/Starlink, fila do uplink por
prioridade, custódia, e cada Rover que ela atende com cada rádio (estado, RTT, perda,
vazão, RSSI/SNR) — mais as repetidoras da malha.

Daqui sai o que o console mostra: a lista de bases com a saúde de cada trecho e, no
centro de comando de um Rover, o **caminho** por onde ele fala agora. Rover que não
aparece no retrato de nenhuma base do cliente fala direto (``modo = "direto"``).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from valtexa.models import Device, DeviceModel, DeviceStatus, as_utc
from valtexa.models.enums import DeviceKind

RETRATO_VELHO = timedelta(minutes=5)
"""Retrato mais velho que isto não diz por onde o Rover fala agora."""


def bases(session: Session, tenant_id: str | None = None) -> list[Device]:
    consulta = (select(Device).join(DeviceModel, Device.device_model_id == DeviceModel.id)
                .where(DeviceModel.kind == DeviceKind.GATEWAY,
                       Device.status == DeviceStatus.ACTIVE))
    if tenant_id:
        consulta = consulta.where(Device.tenant_id == tenant_id)
    return list(session.scalars(consulta.order_by(Device.name)))


def _iso(t: datetime | None) -> str | None:
    t = as_utc(t)
    return t.isoformat() if t else None


def _segundos(t: datetime | None, agora: datetime) -> float | None:
    t = as_utc(t)
    return None if t is None else round((agora - t).total_seconds(), 1)


def retrato(device: Device) -> dict:
    return ((device.health or {}).get("base") or {}) if device.health else {}


def resumo(device: Device, agora: datetime | None = None) -> dict:
    """Uma base para a lista e o detalhe do console."""
    agora = agora or datetime.now(UTC)
    r = retrato(device)
    rovers = r.get("rovers") or []
    return {
        "id": device.id, "name": device.name, "serial_number": device.serial_number,
        "tenant_id": device.tenant_id, "farm_id": device.farm_id,
        "last_seen_at": _iso(device.last_seen_at),
        "contato_ha_s": _segundos(device.last_seen_at, agora),
        "reportado_em": _iso(device.health_reported_at),
        "internet": r.get("internet"), "uplink": r.get("uplink"), "custodia": r.get("custodia"),
        "disk_percent": (device.health or {}).get("disk_percent"),
        "rovers": rovers, "repetidoras": r.get("repetidoras") or [],
        "rovers_vivos": sum(1 for x in rovers if x.get("vivo")),
    }


def caminho(session: Session, rover: Device, agora: datetime | None = None) -> dict:
    """Por onde o Rover fala agora, trecho a trecho, pelo retrato mais novo que o cita."""
    agora = agora or datetime.now(UTC)
    melhor: tuple[Device, dict] | None = None
    for base in bases(session, rover.tenant_id):
        reportado = as_utc(base.health_reported_at)
        if reportado is None or agora - reportado > RETRATO_VELHO:
            continue
        for r in retrato(base).get("rovers") or []:
            # o nó do rádio se chama pelo serial (hardware.json) ou pelo id (a chave
            # publicada pela plataforma usa o id do dispositivo)
            if r.get("serial") in (rover.serial_number, rover.id) and (
                    melhor is None or reportado > as_utc(melhor[0].health_reported_at)):
                melhor = (base, r)
    if melhor is None:
        return {"modo": "direto"}
    base, r = melhor
    internet = retrato(base).get("internet") or {}
    return {
        "modo": "base",
        "base": {"id": base.id, "name": base.name, "serial_number": base.serial_number,
                 "reportado_em": _iso(base.health_reported_at)},
        "nuvem_base": {"ok": bool(internet.get("ok")), "quedas": internet.get("quedas"),
                       "contato_ha_s": _segundos(base.last_seen_at, agora)},
        "base_rover": {"vivo": bool(r.get("vivo")), "melhor": r.get("melhor"),
                       "em_travessia": bool(r.get("em_travessia")),
                       "enlaces": r.get("enlaces") or []},
        "uplink": retrato(base).get("uplink"),
    }
