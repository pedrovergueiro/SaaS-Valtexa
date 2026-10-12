"""Validação de campo: a ficha do agrônomo contra o diagnóstico por planta do Rover.

Brief, seção 44 (validação de campo) e o plano de validação do Rover (fase 5). O fluxo:

1. O Rover passa no talhão em **modo coleta** (``retencao.normal_sample_every = 1`` no
   ``rover.json``: todo quadro sobe em original) e a fusão por planta da IA monta as
   plantas (``services.fusao_borda``).
2. O agrônomo percorre as fileiras de validação e anota cada planta
   (:class:`~valtexa.models.PlantLabel`), na lista que :func:`plantas` devolve.
3. :func:`relatorio` mede o Rover contra o agrônomo; :func:`rotulos_csv` entrega o CSV que
   recalibra a Edge AI e a fusão em VALTEXA-B; ``training.import_campo`` tira dos originais
   os recortes de treino.

Positivo do Rover: planta ``suspeita``, ``doente`` ou ``revisar``. Positivo do agrônomo:
rótulo diferente de ``Healthy``.
"""

from __future__ import annotations

import csv
import io
import math
import re
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from valtexa.models import PlantLabel
from valtexa.services import plant_map

SADIA = "Healthy"
SINONIMOS_SADIA = {"healthy", "sadia", "sadio", "saudavel", "saudável"}
POSITIVOS_ROVER = {"suspeita", "doente", "revisar"}
_ROTULO = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_ .()-]{0,79}$")


class RotuloInvalidoError(ValueError):
    """Rótulo vazio, com vírgula ou caractere que quebraria o CSV de calibração."""


def normaliza_rotulo(rotulo: str) -> str:
    texto = (rotulo or "").strip()
    if texto.lower() in SINONIMOS_SADIA:
        return SADIA
    if not _ROTULO.match(texto):
        raise RotuloInvalidoError(
            "Rótulo: a classe do modelo (Healthy, Rust, Leaf_Miner_Damage...), sem vírgula."
        )
    return texto


def numero_da_fileira(row_ref: str | None) -> int | None:
    """``L03`` / ``G3`` / ``3`` → 3: o número que o cadastro de fileiras de validação usa."""
    if not row_ref:
        return None
    achado = re.search(r"(\d+)", str(row_ref))
    return int(achado.group(1)) if achado else None


def rotulos(session: Session, tenant_id: str, field_id: str,
            mission_id: str | None = None) -> list[PlantLabel]:
    consulta = select(PlantLabel).where(PlantLabel.tenant_id == tenant_id,
                                        PlantLabel.field_id == field_id)
    if mission_id:
        consulta = consulta.where(PlantLabel.mission_id == mission_id)
    return list(session.scalars(consulta.order_by(PlantLabel.mission_id, PlantLabel.plant_ref)))


def plantas(session: Session, talhao, mission_id: str) -> dict:
    """As plantas que a IA fundiu nesta passada, com o rótulo de campo ao lado.

    Levanta :class:`plant_map.PlantMapUnavailableError` sem serviço de IA.
    """
    da_ia = plant_map.plants(talhao.id, mission_id)
    anotados = {r.plant_ref: r for r in rotulos(session, talhao.tenant_id, talhao.id, mission_id)}
    fileiras = set(talhao.validation_rows or [])
    linhas = []
    for p in sorted(da_ia, key=lambda p: (str(p.get("row_id")), p.get("x_along_m") or 0)):
        rotulo = anotados.get(p["plant_id"])
        linhas.append({
            "plant_id": p["plant_id"],
            "row_id": p.get("row_id"),
            "x_along_m": p.get("x_along_m"),
            "in_validation_row": numero_da_fileira(p.get("row_id")) in fileiras,
            "status": p.get("status"),
            "primary_disease": p.get("primary_disease"),
            "primary_posterior": p.get("primary_posterior"),
            "zones_seen": p.get("zones_seen") or [],
            "label": rotulo.label if rotulo else None,
            "incidence_percent": rotulo.incidence_percent if rotulo else None,
            "notes": rotulo.notes if rotulo else None,
        })
    return {"field_id": talhao.id, "mission_id": mission_id,
            "validation_rows": sorted(fileiras), "plants": linhas,
            "labeled": sum(1 for x in linhas if x["label"]),
            "orphan_labels": sorted(set(anotados) - {p["plant_id"] for p in da_ia})}


def anota(session: Session, talhao, mission_id: str, plant_ref: str, *, label: str,
          incidence_percent: float | None, notes: str | None, user_id: str | None,
          row_ref: str | None = None) -> PlantLabel:
    """Cria ou troca o rótulo de uma planta nesta passada."""
    rotulo = session.scalars(select(PlantLabel).where(
        PlantLabel.field_id == talhao.id, PlantLabel.mission_id == mission_id,
        PlantLabel.plant_ref == plant_ref)).first()
    if rotulo is None:
        rotulo = PlantLabel(tenant_id=talhao.tenant_id, field_id=talhao.id,
                            mission_id=mission_id, plant_ref=plant_ref)
        session.add(rotulo)
    rotulo.label = normaliza_rotulo(label)
    rotulo.incidence_percent = incidence_percent
    rotulo.notes = notes
    rotulo.row_ref = row_ref or rotulo.row_ref
    rotulo.labeled_by = user_id
    rotulo.labeled_at = datetime.now(UTC)
    session.flush()
    return rotulo


def _wilson(k: int, n: int, z: float = 1.96) -> list[float] | None:
    if n == 0:
        return None
    p = k / n
    centro = (p + z * z / (2 * n)) / (1 + z * z / n)
    margem = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return [round(max(0.0, centro - margem), 4), round(min(1.0, centro + margem), 4)]


def relatorio(session: Session, talhao, mission_id: str) -> dict:
    """Rover contra agrônomo nas plantas rotuladas desta passada."""
    base = plantas(session, talhao, mission_id)
    rotuladas = [p for p in base["plants"] if p["label"]]
    doentes = [p for p in rotuladas if p["label"] != SADIA]
    sadias = [p for p in rotuladas if p["label"] == SADIA]
    achadas = [p for p in doentes if p["status"] in POSITIVOS_ROVER]
    doenca_certa = [p for p in achadas if p["primary_disease"] == p["label"]]
    alarmes = [p for p in sadias if p["status"] in POSITIVOS_ROVER]
    por_doenca: dict[str, list[int]] = {}
    for p in doentes:
        par = por_doenca.setdefault(p["label"], [0, 0])
        par[1] += 1
        par[0] += p["status"] in POSITIVOS_ROVER
    return {
        "field_id": talhao.id, "mission_id": mission_id,
        "plants_labeled": len(rotuladas),
        "diseased": len(doentes), "detected": len(achadas),
        "right_disease": len(doenca_certa),
        "sensitivity": round(len(achadas) / len(doentes), 4) if doentes else None,
        "sensitivity_ci95": _wilson(len(achadas), len(doentes)),
        "healthy": len(sadias), "false_alarms": len(alarmes),
        "false_alarm_rate": round(len(alarmes) / len(sadias), 4) if sadias else None,
        "false_alarm_ci95": _wilson(len(alarmes), len(sadias)),
        "by_disease": {k: {"detected": v[0], "diseased": v[1]}
                       for k, v in sorted(por_doenca.items())},
        "missed": [p["plant_id"] for p in doentes if p["status"] not in POSITIVOS_ROVER],
        "false_alarm_plants": [p["plant_id"] for p in alarmes],
        "orphan_labels": base["orphan_labels"],
        "note": ("Positivo do Rover: suspeita, doente ou revisar. Com menos de 30 plantas de "
                 "cada lado, os intervalos são largos — a taxa é indicação, não medida."),
    }


def rotulos_csv(session: Session, tenant_id: str, field_id: str,
                mission_id: str | None = None) -> str:
    """``field_id,plant_id,label,pass_id`` — o formato de ``--labels`` em VALTEXA-B."""
    saida = io.StringIO()
    escritor = csv.writer(saida, lineterminator="\n")
    escritor.writerow(["field_id", "plant_id", "label", "pass_id"])
    for r in rotulos(session, tenant_id, field_id, mission_id):
        escritor.writerow([field_id, r.plant_ref, r.label, r.mission_id])
    return saida.getvalue()
