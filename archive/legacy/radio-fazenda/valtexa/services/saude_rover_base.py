"""Retirado de valtexa/services/saude_rover.py em 20/10/2026: o ``health.base`` da base da fazenda."""

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

