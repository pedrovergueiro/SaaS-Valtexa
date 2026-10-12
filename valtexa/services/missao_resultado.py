"""Do que o Rover sincronizou ao resultado da missão (brief, seções 6, 7, 44 e 47).

Três peças, todas sobre o que já está no banco (``edge_record``, ``edge_upload``,
observações e diagnósticos):

1. **Ponte Edge AI → IA de nuvem** (:func:`encaminhar_para_nuvem`). Um resultado
   da Edge AI que é evento (POSSÍVEL DOENÇA/PRAGA, ANOMALIA) e cujo **original**
   já subiu vira uma :class:`~valtexa.models.Observation` e passa pelo mesmo
   pipeline de percepção da rota ``/v1/device/observations``: os analisadores da
   nuvem (dupla validação), diagnóstico, decisão. A Edge AI só **prioriza**; quem
   diagnostica é a nuvem (``edge_summary`` guarda o que o robô achou). Roda
   quando a segunda das duas peças chega (registro ou arquivo) e uma vez só
   (``edge_record.observation_id``).
2. **Fusão operacional por planta** (:func:`plantas_da_missao`). O robô diz, em
   cada resultado, diante de qual planta estava (``region.plant_id``, do mapa de
   plantas). Aqui se juntam todos os quadros e câmeras de cada planta com o
   diagnóstico da nuvem: ``doente`` (nuvem confirmou), ``suspeita`` (a Edge AI
   viu, a nuvem ainda não fechou), ``revisar`` (a nuvem mandou ao agrônomo),
   ``sadia``. Incidência = doentes / plantas vistas, com intervalo de Wilson.
   É uma regra simples e explicável; a **fusão calibrada** (posterior por doença)
   é a do serviço de IA (``ia/app/plant_fusion.py``), que entra quando o SaaS fala
   com ele (``/v1/fields/{id}/plants``).
3. **Relatório e comparação** (:func:`relatorio`, :func:`comparar`): seção 47.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from valtexa.models import (
    Decision,
    Device,
    Diagnosis,
    DiagnosisStatus,
    EdgeRecord,
    EdgeUpload,
    Farm,
    Field,
    Mission,
    MissionKind,
    Observation,
    Zone,
)
from valtexa.models.base import as_utc
from valtexa.services import consent, fusao_borda, geo, plant_map, storage
from valtexa.services.ai_pipeline import HEALTHY_LABELS

EVENTOS = {"POSSIVEL_DOENCA", "POSSIVEL_PRAGA", "ANOMALIA"}
CONFIRMADOS = {DiagnosisStatus.AI_VALIDATED, DiagnosisStatus.HUMAN_CONFIRMED}


# ---------------------------------------------------------------------------
# 1. Ponte Edge AI → IA de nuvem
# ---------------------------------------------------------------------------


def encaminhar_pendentes(session: Session, device: Device, record_ids: list[str]) -> int:
    """Depois de um lote de registros ou de um arquivo: encaminha o que ficou completo."""
    if not record_ids:
        return 0
    linhas = session.scalars(select(EdgeRecord).where(
        EdgeRecord.device_id == device.id, EdgeRecord.record_id.in_(record_ids),
        EdgeRecord.kind == "result", EdgeRecord.type.in_(EVENTOS),
        EdgeRecord.observation_id.is_(None)))
    return sum(1 for r in linhas if encaminhar_para_nuvem(session, device, r) is not None)


def varrer(session: Session, limite: int = 500) -> int:
    """Encaminha o que ficou para trás (IA de nuvem fora do ar na hora). Para o worker."""
    pendentes = session.scalars(
        select(EdgeRecord).join(EdgeUpload, (EdgeUpload.device_id == EdgeRecord.device_id)
                                & (EdgeUpload.record_id == EdgeRecord.record_id))
        .where(EdgeRecord.kind == "result", EdgeRecord.type.in_(EVENTOS),
               EdgeRecord.observation_id.is_(None), EdgeUpload.role == "original",
               EdgeUpload.status == "complete")
        .limit(limite)).all()
    feitos = 0
    for r in pendentes:
        if encaminhar_para_nuvem(session, session.get(Device, r.device_id), r) is not None:
            feitos += 1
    return feitos


def encaminhar_para_nuvem(session: Session, device: Device, record: EdgeRecord
                          ) -> Observation | None:
    if record.observation_id or record.kind != "result" or record.type not in EVENTOS:
        return None
    if record.field_id is None or record.lat is None or record.lon is None:
        return None  # sem talhão ou sem posição não há o que diagnosticar no mapa
    upload = session.scalars(select(EdgeUpload).where(
        EdgeUpload.device_id == device.id, EdgeUpload.record_id == record.record_id,
        EdgeUpload.role == "original", EdgeUpload.status == "complete")).first()
    if upload is None or upload.asset_id is None:
        return None  # o original ainda não subiu: volta a tentar quando subir
    from valtexa.api.routers.device_protocol import _analyses, _run_pipeline
    from valtexa.models import Asset

    asset = session.get(Asset, upload.asset_id)
    dados = storage.store.read(asset.storage_key)
    talhao = session.get(Field, record.field_id)
    corpo = record.payload or {}
    regiao = corpo.get("region") or {}
    analises = _analyses(dados, f"{record.record_id}.jpg", talhao, None,
                         training_consent=consent.permite_treino(session, talhao.tenant_id))
    obs = Observation(
        tenant_id=record.tenant_id,
        farm_id=talhao.farm_id,
        field_id=talhao.id,
        zone_id=_zona(session, talhao.id, record.lon, record.lat),
        mission_id=record.mission_id,
        device_id=device.id,
        captured_at=record.occurred_at,
        lat=record.lat,
        lon=record.lon,
        alt_m=(corpo.get("position") or {}).get("alt_m"),
        heading_deg=(corpo.get("position") or {}).get("heading_deg"),
        row_index=regiao.get("row"),
        plant_ref=regiao.get("plant_id"),
        image_asset_id=asset.id,
        edge_summary={"edge_record_id": record.record_id, "category": record.type,
                      "label": record.label, "confidence": record.confidence,
                      "model": (corpo.get("model") or {}).get("key"),
                      "model_version": (corpo.get("model") or {}).get("version"),
                      "camera_id": (corpo.get("frame") or {}).get("camera_id"),
                      "simulated_hardware": (corpo.get("hardware") or {}).get("simulated")},
    )
    session.add(obs)
    session.flush()
    _run_pipeline(session, obs, dados, f"{record.record_id}.jpg", talhao, analyses=analises)
    record.observation_id = obs.id
    return obs


def _zona(session: Session, field_id: str, lon: float, lat: float) -> str | None:
    for zona in session.scalars(select(Zone).where(Zone.field_id == field_id)):
        if zona.boundary and geo.contains_point(zona.boundary, lon, lat, include_boundary=True):
            return zona.id
    return None


# ---------------------------------------------------------------------------
# 2. Fusão operacional por planta
# ---------------------------------------------------------------------------


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    centro = (p + z * z / (2 * n)) / (1 + z * z / n)
    meia = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return (round(max(0.0, centro - meia), 4), round(min(1.0, centro + meia), 4))


def plantas_da_missao(session: Session, tenant_id: str, mission_id: str) -> dict:
    registros = list(session.scalars(select(EdgeRecord).where(
        EdgeRecord.tenant_id == tenant_id, EdgeRecord.mission_id == mission_id,
        EdgeRecord.kind == "result")))
    diagnosticos = {
        obs.id: diag for obs, diag in session.execute(
            select(Observation, Diagnosis)
            .join(Diagnosis, Diagnosis.observation_id == Observation.id)
            .where(Observation.tenant_id == tenant_id, Observation.mission_id == mission_id))
    }
    plantas: dict[str, dict] = defaultdict(lambda: {
        "frames": 0, "cameras": set(), "edge": Counter(), "cloud": [], "lat": [], "lon": [],
        "row": None})
    sem_regiao = 0
    for r in registros:
        regiao = (r.payload or {}).get("region") or {}
        pid = regiao.get("plant_id")
        if not pid:
            sem_regiao += 1
            continue
        p = plantas[pid]
        p["frames"] += 1
        p["cameras"].add(((r.payload or {}).get("frame") or {}).get("camera_id"))
        p["edge"][r.type] += 1
        p["row"] = regiao.get("row")
        if r.lat is not None:
            p["lat"].append(r.lat)
            p["lon"].append(r.lon)
        if r.observation_id and r.observation_id in diagnosticos:
            d = diagnosticos[r.observation_id]
            p["cloud"].append((d.effective_label, d.status, d.confidence, d.id))

    saida = []
    for pid, p in sorted(plantas.items()):
        confirmados = [c for c in p["cloud"] if c[1] in CONFIRMADOS and c[0]
                       and c[0] not in HEALTHY_LABELS]
        revisar = [c for c in p["cloud"] if c[1] is DiagnosisStatus.NEEDS_REVIEW]
        eventos_edge = sum(v for k, v in p["edge"].items() if k in EVENTOS)
        if confirmados:
            status, rotulo = "doente", Counter(c[0] for c in confirmados).most_common(1)[0][0]
        elif revisar:
            status, rotulo = "revisar", revisar[0][0]
        elif eventos_edge and not (p["cloud"] and all(
                c[1] in CONFIRMADOS and c[0] in HEALTHY_LABELS for c in p["cloud"])):
            status, rotulo = "suspeita", None
        else:
            status, rotulo = "sadia", None
        saida.append({
            "plant_id": pid, "row": p["row"], "status": status, "label": rotulo,
            "frames": p["frames"], "cameras": sorted(c for c in p["cameras"] if c),
            "edge_categories": dict(p["edge"]),
            "cloud_diagnoses": [{"diagnosis_id": c[3], "label": c[0], "status": c[1].value,
                                 "confidence": c[2]} for c in p["cloud"]],
            "lat": round(sum(p["lat"]) / len(p["lat"]), 7) if p["lat"] else None,
            "lon": round(sum(p["lon"]) / len(p["lon"]), 7) if p["lon"] else None,
        })
    n = len(saida)
    doentes = sum(1 for p in saida if p["status"] == "doente")
    suspeitas = sum(1 for p in saida if p["status"] in ("suspeita", "revisar"))
    por_rotulo = Counter(p["label"] for p in saida if p["status"] == "doente")
    return {
        "mission_id": mission_id,
        "plants": saida,
        "plants_seen": n,
        "results_without_plant": sem_regiao,
        "incidence": {
            "diseased": doentes, "suspect": suspeitas,
            "ratio": round(doentes / n, 4) if n else None,
            "interval_95": wilson(doentes, n),
            "ratio_with_suspect": round((doentes + suspeitas) / n, 4) if n else None,
            "by_label": dict(por_rotulo),
        },
        "method": "fusão operacional por planta (Edge AI + diagnóstico da nuvem; regra "
                  "simples). A fusão calibrada é a do serviço de IA.",
    }


# ---------------------------------------------------------------------------
# 3. Relatório e comparação
# ---------------------------------------------------------------------------


def comparar(session: Session, tenant_id: str, base_id: str, nova_id: str) -> dict:
    a = plantas_da_missao(session, tenant_id, base_id)
    b = plantas_da_missao(session, tenant_id, nova_id)
    antes = {p["plant_id"]: p["status"] for p in a["plants"]}
    depois = {p["plant_id"]: p["status"] for p in b["plants"]}
    ruins = {"doente", "suspeita", "revisar"}
    comuns = set(antes) & set(depois)
    ra, rb = a["incidence"]["ratio"], b["incidence"]["ratio"]
    return {
        "baseline_mission_id": base_id,
        "mission_id": nova_id,
        "incidence_before": ra,
        "incidence_after": rb,
        "delta": None if ra is None or rb is None else round(rb - ra, 4),
        "plants_compared": len(comuns),
        "recovered": sorted(p for p in comuns if antes[p] in ruins and depois[p] == "sadia"),
        "persisting": sorted(p for p in comuns if antes[p] in ruins and depois[p] in ruins),
        "new": sorted(p for p in comuns if antes[p] == "sadia" and depois[p] in ruins),
    }


def relatorio(session: Session, mission: Mission) -> dict:
    """Resumo de missão (seção 47): onde, quem, quando, o que se viu e o que se fez."""
    fazenda = session.get(Farm, mission.farm_id)
    talhao = session.get(Field, mission.field_id)
    robo = session.get(Device, mission.device_id)
    registros = list(session.scalars(select(EdgeRecord).where(
        EdgeRecord.tenant_id == mission.tenant_id, EdgeRecord.mission_id == mission.id)))
    resultados = [r for r in registros if r.kind == "result"]
    eventos = [r for r in registros if r.kind == "event"]
    plantas = plantas_da_missao(session, mission.tenant_id, mission.id)
    decisoes = list(session.scalars(
        select(Decision).join(Diagnosis, Diagnosis.id == Decision.diagnosis_id)
        .join(Observation, Observation.id == Diagnosis.observation_id)
        .where(Observation.tenant_id == mission.tenant_id,
               Observation.mission_id == mission.id)))
    inicio = as_utc(mission.started_at) or min(
        (as_utc(r.occurred_at) for r in resultados), default=None)
    fim = as_utc(mission.finished_at) or max(
        (as_utc(r.occurred_at) for r in resultados), default=None)
    prescricoes = list(session.scalars(select(Mission).where(
        Mission.tenant_id == mission.tenant_id, Mission.field_id == mission.field_id,
        Mission.kind == MissionKind.SPRAY, Mission.created_at >= mission.created_at)
        .order_by(Mission.created_at)))
    anteriores = list(session.scalars(select(Mission).where(
        Mission.tenant_id == mission.tenant_id, Mission.field_id == mission.field_id,
        Mission.kind == mission.kind, Mission.id != mission.id,
        Mission.created_at < mission.created_at).order_by(Mission.created_at.desc()).limit(5)))
    historico = []
    for m in anteriores:
        inc = plantas_da_missao(session, mission.tenant_id, m.id)["incidence"]["ratio"]
        historico.append({"mission_id": m.id, "date": _iso(m.started_at or m.created_at),
                          "incidence": inc})
    simulado = any(((r.payload or {}).get("hardware") or {}).get("simulated")
                   for r in resultados)
    return {
        "mission_id": mission.id,
        "kind": mission.kind.value,
        "state": mission.state.value,
        "farm": fazenda.name if fazenda else None,
        "field": talhao.name if talhao else None,
        "crop": talhao.crop if talhao else None,
        "rover": robo.serial_number if robo else None,
        "date": _iso(inicio),
        "duration_min": round((fim - inicio).total_seconds() / 60, 1) if inicio and fim else None,
        "area_ha": talhao.area_ha if talhao else None,
        "images_processed": len(resultados),
        "edge_categories": dict(Counter(r.type for r in resultados)),
        "events": dict(Counter(r.type for r in eventos)),
        "occurrences": [p for p in plantas["plants"] if p["status"] != "sadia"],
        "incidence": plantas["incidence"],
        "plants_seen": plantas["plants_seen"],
        "calibrated_fusion": _fusao_calibrada(session, mission),
        "recommendations": [{"decision_id": d.id, "outcome": d.outcome.value,
                             "rationale": d.rationale} for d in decisoes],
        "prescriptions": [{"mission_id": p.id, "state": p.state.value,
                           "product_id": p.product_id, "rate_l_ha": p.authorized_rate_l_ha,
                           "quantity_l": p.authorized_quantity_l,
                           "approved_at": _iso(p.approved_at)} for p in prescricoes],
        "history": historico,
        "comparison_with_previous": comparar(session, mission.tenant_id, anteriores[0].id,
                                             mission.id) if anteriores else None,
        "simulated": simulado,
        "generated_at": _iso(datetime.now().astimezone()),
    }


def _fusao_calibrada(session: Session, mission: Mission) -> dict:
    """A fusão calibrada da IA para esta passada, em melhor esforço (serviço fora: ``None``).

    ``edge_results`` diz quantos resultados do Rover entraram (``ok``), ficaram sem
    geometria, sem recortes ou pendentes — a incidência só vale para os que entraram.
    """
    try:
        incidencia = plant_map.incidence(mission.field_id, mission.id)
        motivo = None if incidencia is not None else "nenhum quadro desta missão na fusão"
    except plant_map.PlantMapUnavailableError as exc:
        incidencia, motivo = None, str(exc)
    return {"edge_results": fusao_borda.resumo(session, mission.id),
            "pass_closed": mission.fusion_closed_at is not None,
            "incidence": incidencia, "unavailable_reason": motivo}


def _iso(valor: datetime | None) -> str | None:
    return as_utc(valor).isoformat() if valor else None


__all__ = [
    "comparar",
    "encaminhar_para_nuvem",
    "encaminhar_pendentes",
    "plantas_da_missao",
    "relatorio",
    "varrer",
    "wilson",
]
