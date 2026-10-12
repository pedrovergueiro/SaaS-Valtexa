"""O que as telas do cliente mostram além do resultado da missão (brief, seções 45, 46 e 47).

Três leituras, todas sobre o que já está no banco e sempre dentro de um cliente:

1. :func:`mapa_da_missao` — rota percorrida (posições dos quadros que o robô
   analisou, na ordem), pontos de evento da Edge AI e plantas com o estado da fusão
   operacional (:func:`valtexa.services.missao_resultado.plantas_da_missao`, que
   esta leitura só consome);
2. :func:`linha_do_tempo` — o ciclo do talhão: missão → ocorrências → prescrição →
   aprovação → aplicação → verificação, cada passo com o vínculo que o banco guarda
   (decisão de origem, missão de aplicação, verificação da aplicação);
3. :func:`painel` — os números da seção 45 que o painel ainda não trazia: fazendas,
   talhões e hectares, ocorrências, sincronização por robô, saúde da frota e da IA.

Nada é estimado aqui: o que não existe no banco sai vazio ou ``None``.
"""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from valtexa.models import (
    Alert,
    Application,
    Decision,
    Detection,
    Device,
    DeviceStatus,
    Diagnosis,
    EdgeRecord,
    EdgeUpload,
    Farm,
    Field,
    Mission,
    MissionKind,
    Observation,
    Verification,
)
from valtexa.models.base import as_utc
from valtexa.services import missao_resultado, observabilidade
from valtexa.services.ingestion import OFFLINE_AFTER

MAX_PONTOS_ROTA = 2000
"""A rota desenhada no mapa: acima disso, uma posição a cada ``k`` (a última sempre)."""

EVENTOS_EDGE = missao_resultado.EVENTOS


def _iso(valor: datetime | None) -> str | None:
    return as_utc(valor).isoformat() if valor else None


def _decimar(pontos: list, maximo: int = MAX_PONTOS_ROTA) -> list:
    if len(pontos) <= maximo:
        return pontos
    passo = -(-len(pontos) // maximo)  # teto
    saida = pontos[::passo]
    if saida[-1] is not pontos[-1]:
        saida.append(pontos[-1])
    return saida


# ---------------------------------------------------------------------------
# 1. Mapa da missão
# ---------------------------------------------------------------------------


def mapa_da_missao(session: Session, mission: Mission) -> dict:
    registros = list(session.scalars(
        select(EdgeRecord)
        .where(EdgeRecord.tenant_id == mission.tenant_id, EdgeRecord.mission_id == mission.id)
        .order_by(EdgeRecord.occurred_at, EdgeRecord.id)
    ))
    originais = {
        (device_id, record_id) for device_id, record_id in session.execute(
            select(EdgeUpload.device_id, EdgeUpload.record_id).where(
                EdgeUpload.tenant_id == mission.tenant_id,
                EdgeUpload.record_id.in_([r.record_id for r in registros]),
                EdgeUpload.status == "complete", EdgeUpload.role == "original"))
    } if registros else set()

    rota = [[r.lon, r.lat] for r in registros
            if r.kind == "result" and r.lat is not None and r.lon is not None]
    eventos = []
    for r in registros:
        if r.lat is None or r.lon is None:
            continue
        if r.kind == "result" and r.type not in EVENTOS_EDGE:
            continue
        regiao = (r.payload or {}).get("region") or {}
        eventos.append({
            "id": r.id, "kind": r.kind, "type": r.type, "label": r.label,
            "severity": r.severity, "confidence": r.confidence, "lat": r.lat, "lon": r.lon,
            "at": _iso(r.occurred_at), "plant_id": regiao.get("plant_id"),
            "has_original": (r.device_id, r.record_id) in originais,
        })
    plantas = missao_resultado.plantas_da_missao(session, mission.tenant_id, mission.id)
    return {
        "mission_id": mission.id,
        "field_id": mission.field_id,
        "kind": mission.kind.value,
        "date": _iso(mission.started_at or mission.created_at),
        "planned_route": mission.waypoints or [],
        "track": _decimar(rota),
        "track_points_total": len(rota),
        "events": eventos,
        "plants": [
            {k: p[k] for k in ("plant_id", "row", "status", "label", "frames", "lat", "lon")}
            for p in plantas["plants"]
        ],
        "plants_without_position": sum(1 for p in plantas["plants"] if p["lat"] is None),
        "incidence": plantas["incidence"],
        "plants_seen": plantas["plants_seen"],
    }


# ---------------------------------------------------------------------------
# 2. Linha do tempo do talhão
# ---------------------------------------------------------------------------


def linha_do_tempo(session: Session, tenant_id: str, field_id: str, *,
                   limite_missoes: int = 30) -> list[dict]:
    """Passos do ciclo, do mais recente ao mais antigo.

    ``stage`` é ``missao``, ``ocorrencias``, ``prescricao``, ``aprovacao``,
    ``aplicacao`` ou ``verificacao``. Cada passo traz os IDs para a tela abrir o
    detalhe e ``origin_mission_id`` quando o banco sabe de qual varredura veio.
    """
    missoes = list(session.scalars(
        select(Mission).where(Mission.tenant_id == tenant_id, Mission.field_id == field_id)
        .order_by(Mission.created_at.desc()).limit(limite_missoes)
    ))
    passos: list[dict] = []

    # decisão → varredura de origem (a observação da decisão veio de qual missão)
    decisoes = [m.decision_id for m in missoes if m.decision_id]
    origem_da_decisao = dict(session.execute(
        select(Decision.id, Observation.mission_id)
        .join(Diagnosis, Diagnosis.id == Decision.diagnosis_id)
        .join(Observation, Observation.id == Diagnosis.observation_id)
        .where(Decision.tenant_id == tenant_id, Decision.id.in_(decisoes))
    ).all()) if decisoes else {}

    for m in missoes:
        quando = m.started_at or m.created_at
        if m.kind in (MissionKind.SCOUT, MissionKind.VERIFY):
            passos.append({
                "stage": "missao", "at": _iso(quando), "mission_id": m.id, "kind": m.kind.value,
                "state": m.state.value, "title": "Varredura" if m.kind is MissionKind.SCOUT
                else "Missão de verificação",
            })
            if m.started_at:
                plantas = missao_resultado.plantas_da_missao(session, tenant_id, m.id)
                inc = plantas["incidence"]
                if plantas["plants_seen"]:
                    passos.append({
                        "stage": "ocorrencias", "at": _iso(m.finished_at or quando),
                        "mission_id": m.id, "plants_seen": plantas["plants_seen"],
                        "diseased": inc["diseased"], "suspect": inc["suspect"],
                        "incidence": inc["ratio"], "by_label": inc["by_label"],
                    })
        elif m.kind is MissionKind.SPRAY:
            origem = origem_da_decisao.get(m.decision_id) if m.decision_id else None
            passos.append({
                "stage": "prescricao", "at": _iso(m.created_at), "mission_id": m.id,
                "state": m.state.value, "decision_id": m.decision_id,
                "origin_mission_id": origem, "rate_l_ha": m.authorized_rate_l_ha,
                "quantity_l": m.authorized_quantity_l, "product_id": m.product_id,
            })
            if m.approved_at:
                passos.append({
                    "stage": "aprovacao", "at": _iso(m.approved_at), "mission_id": m.id,
                    "approved_by": m.approved_by, "origin_mission_id": origem,
                })

    ids = [m.id for m in missoes if m.kind is MissionKind.SPRAY]
    aplicacoes = list(session.scalars(
        select(Application).where(Application.tenant_id == tenant_id,
                                  Application.field_id == field_id)
        .order_by(Application.started_at.desc()).limit(limite_missoes)
    ))
    for a in aplicacoes:
        passos.append({
            "stage": "aplicacao", "at": _iso(a.started_at), "application_id": a.id,
            "mission_id": a.mission_id, "state": a.state.value,
            "finished_at": _iso(a.stopped_at), "amount_used_l": a.amount_used_l,
            "area_ha": a.area_ha, "outside_polygon_points": a.outside_polygon_points,
            "in_listed_mission": a.mission_id in ids,
        })
    verificacoes = list(session.scalars(
        select(Verification).where(Verification.tenant_id == tenant_id,
                                   Verification.field_id == field_id)
        .order_by(Verification.created_at.desc()).limit(limite_missoes)
    ))
    for v in verificacoes:
        passos.append({
            "stage": "verificacao", "at": _iso(v.updated_at or v.created_at),
            "verification_id": v.id, "application_id": v.application_id,
            "mission_id": v.verification_mission_id, "conclusion": v.conclusion.value,
            "before_ratio": v.before_ratio, "after_ratio": v.after_ratio,
            "effectiveness": v.effectiveness, "scheduled_for": _iso(v.scheduled_for),
        })
    ordem = {"missao": 0, "ocorrencias": 1, "prescricao": 2, "aprovacao": 3,
             "aplicacao": 4, "verificacao": 5}
    passos.sort(key=lambda p: (p["at"] or "", ordem[p["stage"]]), reverse=True)
    return passos


# ---------------------------------------------------------------------------
# 3. Painel (seção 45)
# ---------------------------------------------------------------------------


def painel(session: Session, tenant_id: str, agora: datetime | None = None) -> dict:
    agora = agora or datetime.now(UTC)
    semana, dia = agora - timedelta(days=7), agora - timedelta(hours=24)

    fazendas = session.scalar(select(func.count(Farm.id)).where(Farm.tenant_id == tenant_id))
    talhoes, hectares = session.execute(
        select(func.count(Field.id), func.coalesce(func.sum(Field.area_ha), 0.0))
        .where(Field.tenant_id == tenant_id)
    ).one()

    ocorrencias = dict(session.execute(
        select(EdgeRecord.type, func.count(EdgeRecord.id)).where(
            EdgeRecord.tenant_id == tenant_id, EdgeRecord.kind == "result",
            EdgeRecord.type.in_(EVENTOS_EDGE), EdgeRecord.occurred_at >= semana)
        .group_by(EdgeRecord.type)
    ).all())
    feitas_30d = session.execute(
        select(func.count(Mission.id)).where(
            Mission.tenant_id == tenant_id, Mission.finished_at >= agora - timedelta(days=30),
            Mission.kind == MissionKind.SCOUT)
    ).scalar_one()
    area_varrida = session.execute(
        select(func.coalesce(func.sum(Field.area_ha), 0.0))
        .select_from(Mission).join(Field, Field.id == Mission.field_id)
        .where(Mission.tenant_id == tenant_id, Mission.kind == MissionKind.SCOUT,
               Mission.finished_at >= agora - timedelta(days=30))
    ).scalar_one()

    # sincronização: por robô, o que chegou por último e o que ainda está pela metade
    robos = list(session.scalars(select(Device).where(
        Device.tenant_id == tenant_id, Device.status != DeviceStatus.RETIRED
    ).order_by(Device.name)))
    ultimo = dict(session.execute(
        select(EdgeRecord.device_id, func.max(EdgeRecord.received_at))
        .where(EdgeRecord.tenant_id == tenant_id).group_by(EdgeRecord.device_id)
    ).all())
    pela_metade = dict(session.execute(
        select(EdgeUpload.device_id, func.count(EdgeUpload.id))
        .where(EdgeUpload.tenant_id == tenant_id, EdgeUpload.status != "complete")
        .group_by(EdgeUpload.device_id)
    ).all())
    alertas_abertos = Counter(dict(session.execute(
        select(Alert.subject_id, func.count(Alert.id)).where(
            Alert.tenant_id == tenant_id, Alert.subject_type == "device",
            Alert.state != "resolvido").group_by(Alert.subject_id)
    ).all()))
    sincronizacao, saude = [], Counter()
    for d in robos:
        visto = as_utc(d.last_seen_at)
        offline = visto is None or (agora - visto) > OFFLINE_AFTER
        oldest = ((d.health or {}).get("sync") or {}).get("oldest_pending_s")
        sincronizacao.append({
            "device_id": d.id, "name": d.name, "serial_number": d.serial_number,
            "online": not offline, "last_seen_at": _iso(visto),
            "last_sync_at": _iso(d.last_sync_at),
            "last_record_received_at": _iso(ultimo.get(d.id)),
            "queue_pending": d.sync_pending, "queue_oldest_s": oldest,
            "uploads_incomplete": pela_metade.get(d.id, 0),
            "open_alerts": alertas_abertos.get(d.id, 0),
        })
        if d.status is not DeviceStatus.ACTIVE:
            saude["inativo"] += 1
        elif offline:
            saude["offline"] += 1
        elif alertas_abertos.get(d.id):
            saude["com_alerta"] += 1
        else:
            saude["ok"] += 1

    # IA: o que a borda e a nuvem fizeram nas últimas 24 h, em linguagem operacional
    borda = session.execute(
        select(func.count(EdgeRecord.id)).where(
            EdgeRecord.tenant_id == tenant_id, EdgeRecord.kind == "result",
            EdgeRecord.occurred_at >= dia)
    ).scalar_one()
    nuvem, nuvem_erros = session.execute(
        select(func.count(Detection.id), func.count(Detection.error))
        .where(Detection.tenant_id == tenant_id, Detection.created_at >= dia)
    ).one()
    servico = observabilidade.estado_ia()["status"]
    modelos_borda = [
        {"model_key": k, "model_version": v, "results_24h": n}
        for k, v, n in session.execute(
            select(EdgeRecord.model_key, EdgeRecord.model_version, func.count(EdgeRecord.id))
            .where(EdgeRecord.tenant_id == tenant_id, EdgeRecord.kind == "result",
                   EdgeRecord.occurred_at >= dia, EdgeRecord.model_key.is_not(None))
            .group_by(EdgeRecord.model_key, EdgeRecord.model_version)
        ).all()
    ]
    return {
        "farms": fazendas or 0,
        "fields": talhoes or 0,
        "hectares": round(float(hectares or 0.0), 2),
        "occurrences_7d": sum(ocorrencias.values()),
        "occurrences_by_category_7d": ocorrencias,
        "scouts_completed_30d": feitas_30d,
        "hectares_scouted_30d": round(float(area_varrida or 0.0), 2),
        "sync": sincronizacao,
        "fleet_health": {k: saude.get(k, 0) for k in ("ok", "com_alerta", "offline", "inativo")},
        "ai_health": {
            "cloud_service": servico,
            "cloud_inferences_24h": nuvem,
            "cloud_errors_24h": nuvem_erros,
            "edge_results_24h": borda,
            "edge_models": modelos_borda,
        },
    }


__all__ = ["MAX_PONTOS_ROTA", "linha_do_tempo", "mapa_da_missao", "painel"]
