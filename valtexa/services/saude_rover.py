"""Saúde do robô (brief, seção 35): o campo ``health`` da telemetria, padronizado.

O Health Monitor do ``rover/`` manda, a cada amostra, um dicionário ``health``
(``rover/valtexa_rover/runtime/health.py``). Aqui ele vira o retrato guardado no
robô (``device.health``) — que alimenta a frota, as métricas e os alertas — com
três cuidados:

* **só os campos conhecidos**, com tipo conferido e faixa limitada: o robô é
  autenticado, mas um JSON livre gravado a cada amostra cresceria sem controle e
  poderia carregar qualquer coisa até a tela;
* **``None`` continua ``None``**: o que o robô não mediu (GPU sem adapter, CPU na
  primeira leitura) não vira zero — zero de CPU é uma medida, ausência não;
* **o que é simulação vem dito** (``simulated``), e a tela mostra.

Robô que ainda não manda ``health`` (firmware antigo, protocolo da Parte 3) segue
funcionando: o retrato fica com o que a telemetria básica já trazia (bateria,
temperatura, disco, enlace).
"""

from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Any

from valtexa.models import Device, as_utc

MAX_CAMERAS = 16


def _num(valor: Any, *, minimo: float | None = None, maximo: float | None = None) -> float | None:
    if isinstance(valor, bool) or not isinstance(valor, int | float):
        return None
    numero = float(valor)
    if math.isnan(numero) or math.isinf(numero):
        return None
    if minimo is not None and numero < minimo:
        return None
    if maximo is not None and numero > maximo:
        return None
    return round(numero, 3)


def _inteiro(valor: Any) -> int | None:
    numero = _num(valor, minimo=0)
    return None if numero is None else int(numero)


def _texto(valor: Any, limite: int = 120) -> str | None:
    return str(valor)[:limite] if isinstance(valor, str) and valor else None


def _estado(valor: Any) -> str | None:
    return valor if valor in ("ok", "falha", "ausente", "nao_monitorado") else None


MAX_ROVERS_DA_BASE = 32
MAX_ENLACES = 8
ESTADOS_DE_ENLACE = ("vivo", "degradado", "morto")


def _base(bruto: Any) -> dict | None:
    """``health.base``: o retrato que a base da fazenda manda (valtexa_base.plataforma)."""
    if not isinstance(bruto, dict):
        return None
    internet = bruto.get("internet") if isinstance(bruto.get("internet"), dict) else {}
    uplink = bruto.get("uplink") if isinstance(bruto.get("uplink"), dict) else {}
    rovers = []
    for r in (bruto.get("rovers") or [])[:MAX_ROVERS_DA_BASE]:
        if not isinstance(r, dict) or not _texto(r.get("serial"), 64):
            continue
        enlaces = []
        for e in (r.get("enlaces") or [])[:MAX_ENLACES]:
            if isinstance(e, dict) and _texto(e.get("nome"), 32):
                enlaces.append({
                    "nome": _texto(e.get("nome"), 32),
                    "estado": e.get("estado") if e.get("estado") in ESTADOS_DE_ENLACE
                    else None,
                    "rtt_ms": _num(e.get("rtt_ms"), minimo=0),
                    "perda": _num(e.get("perda"), minimo=0, maximo=1),
                    "vazao_bps": _num(e.get("vazao_bps"), minimo=0),
                    "rssi_dbm": _num(e.get("rssi_dbm"), minimo=-200, maximo=50),
                    "snr_db": _num(e.get("snr_db"), minimo=-50, maximo=100),
                    "quedas": _inteiro(e.get("quedas")),
                })
        rovers.append({"serial": _texto(r.get("serial"), 64), "vivo": r.get("vivo") is True,
                       "melhor": _texto(r.get("melhor"), 32),
                       "em_travessia": r.get("em_travessia") is True, "enlaces": enlaces})
    repetidoras = [
        {"nome": _texto(x.get("nome"), 64), "vivo": x.get("vivo") is True,
         "bateria_pct": _num(x.get("bateria_pct"), minimo=0, maximo=100)}
        for x in (bruto.get("repetidoras") or [])[:MAX_ROVERS_DA_BASE]
        if isinstance(x, dict) and _texto(x.get("nome"), 64)]
    return {
        "nome": _texto(bruto.get("nome"), 64),
        "internet": {"ok": internet.get("ok") is True,
                     "quedas": _inteiro(internet.get("quedas")),
                     "ultima_falha": _texto(internet.get("ultima_falha"), 200)},
        "uplink": {f"P{i}": _inteiro(uplink.get(f"P{i}")) or 0 for i in range(5)},
        "custodia": _inteiro((bruto.get("custodia") or {}).get("pendentes")
                             if isinstance(bruto.get("custodia"), dict) else None),
        "rovers": rovers,
        "repetidoras": repetidoras,
    }


def padronizar(bruto: Any) -> dict | None:
    """O ``health`` da amostra, só com o que a plataforma conhece. ``None`` se inválido."""
    if not isinstance(bruto, dict):
        return None
    acel = bruto.get("accelerator") if isinstance(bruto.get("accelerator"), dict) else {}
    sensores = bruto.get("sensors") if isinstance(bruto.get("sensors"), dict) else {}
    rede = bruto.get("network") if isinstance(bruto.get("network"), dict) else {}
    sync = bruto.get("sync") if isinstance(bruto.get("sync"), dict) else None
    edge = bruto.get("edge_ai") if isinstance(bruto.get("edge_ai"), dict) else {}
    cameras = []
    for cam in (bruto.get("cameras") or [])[:MAX_CAMERAS]:
        if isinstance(cam, dict) and _texto(cam.get("id"), 64):
            cameras.append({"id": _texto(cam.get("id"), 64), "ok": cam.get("ok") is True,
                            "detail": _texto(cam.get("detail"), 200)})
    simulados = [s[:32] for s in (bruto.get("simulated") or []) if isinstance(s, str)][:16]
    return {
        "cpu_percent": _num(bruto.get("cpu_percent"), minimo=0, maximo=100),
        "memory_percent": _num(bruto.get("memory_percent"), minimo=0, maximo=100),
        "memory_used_bytes": _inteiro(bruto.get("memory_used_bytes")),
        "memory_total_bytes": _inteiro(bruto.get("memory_total_bytes")),
        "load_1m": _num(bruto.get("load_1m"), minimo=0),
        "accelerator": {
            "name": _texto(acel.get("name")),
            "providers": [p[:64] for p in (acel.get("providers") or [])
                          if isinstance(p, str)][:8],
            "percent": _num(acel.get("percent"), minimo=0, maximo=100),
            "memory_used_bytes": _inteiro(acel.get("memory_used_bytes")),
            "temperature_c": _num(acel.get("temperature_c"), minimo=-60, maximo=200),
        },
        "disk_percent": _num(bruto.get("disk_percent"), minimo=0, maximo=100),
        "temperature_c": _num(bruto.get("temperature_c"), minimo=-60, maximo=200),
        "battery_percent": _num(bruto.get("battery_percent"), minimo=0, maximo=100),
        "cameras": cameras,
        "sensors": {k: _estado(sensores.get(k)) for k in ("gps", "imu", "ambiente")},
        "network": {"online": rede.get("online") if isinstance(rede.get("online"), bool)
                    else None},
        "sync": None if sync is None else {
            "pending": _inteiro(sync.get("pending")),
            "failed": _inteiro(sync.get("failed")),
            "oldest_pending_s": _num(sync.get("oldest_pending_s"), minimo=0),
            "blocked": sync.get("blocked") is True,
            "last_ok_at": _texto(sync.get("last_ok_at"), 40),
        },
        "edge_ai": {"fps": _num(edge.get("fps"), minimo=0),
                    "latency_ms": _num(edge.get("latency_ms"), minimo=0),
                    "model_loaded": edge.get("model_loaded")
                    if isinstance(edge.get("model_loaded"), bool) else None},
        "simulated": simulados,
        "base": _base(bruto.get("base")),
    }


def aplicar(device: Device, sample: dict, recorded_at: datetime | None) -> None:
    """Grava o ``health`` da amostra mais recente no retrato do robô (se veio)."""
    saude = padronizar(sample.get("health"))
    if saude is None:
        return
    device.health = saude
    device.health_reported_at = recorded_at or datetime.now(UTC)


def disco_percentual(device: Device) -> float | None:
    """Uso do disco: do ``health`` se veio, senão da telemetria básica."""
    if device.health and device.health.get("disk_percent") is not None:
        return device.health["disk_percent"]
    total, livre = device.storage_total_bytes, device.storage_free_bytes
    if not total or livre is None:
        return None
    return round(100 * (total - livre) / total, 1)


def _primeiro(*valores: float | None) -> float | None:
    return next((v for v in valores if v is not None), None)


def retrato(device: Device, agora: datetime | None = None) -> dict:
    """O que a tela de observabilidade mostra de um robô: saúde + básicos + fila."""
    agora = agora or datetime.now(UTC)
    saude = dict(device.health or {})
    visto = as_utc(device.last_seen_at)
    return {
        "cpu_percent": saude.get("cpu_percent"),
        "memory_percent": saude.get("memory_percent"),
        "accelerator_percent": (saude.get("accelerator") or {}).get("percent"),
        "accelerator_name": (saude.get("accelerator") or {}).get("name"),
        "disk_percent": disco_percentual(device),
        "temperature_c": _primeiro(saude.get("temperature_c"), device.temperature_c),
        "battery_percent": _primeiro(saude.get("battery_percent"), device.battery_percent),
        "cameras_total": len(saude.get("cameras") or []),
        "cameras_ok": sum(1 for c in saude.get("cameras") or [] if c.get("ok")),
        "cameras": saude.get("cameras") or [],
        "sensors": saude.get("sensors") or {},
        "connectivity": device.connectivity.value,
        "last_seen_at": visto,
        "offline_minutes": None if visto is None
        else round((agora - visto).total_seconds() / 60, 1),
        "sync_pending": device.sync_pending,
        "sync_oldest_pending_s": (saude.get("sync") or {}).get("oldest_pending_s"),
        "sync_blocked": bool((saude.get("sync") or {}).get("blocked")),
        "last_sync_at": as_utc(device.last_sync_at),
        "edge_ai": saude.get("edge_ai") or {},
        "versions": {"runtime": device.runtime_version, "edge_ai": device.edge_ai_version,
                     "model": f"{device.ai_model_key}@{device.ai_model_version}"
                     if device.ai_model_key else None, "firmware": device.firmware_version},
        "faults": list(device.active_faults or []),
        "health_reported_at": as_utc(device.health_reported_at),
        "simulated": saude.get("simulated") or [],
    }


__all__ = ["aplicar", "disco_percentual", "padronizar", "retrato"]
