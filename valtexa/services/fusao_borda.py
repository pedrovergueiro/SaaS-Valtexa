"""Fusão por planta dos resultados do Rover Runtime (brief, seções 6, 7 e 44).

O Rover classifica cada quadro em recortes de 150 mm e manda, no resultado, as
probabilidades de **todos** os recortes (``tiles``) — inclusive dos quadros normais, que
sobem reduzidos a 320 px e não dão para a nuvem rodar o modelo de novo. Aqui cada
resultado vira um quadro da fusão por planta da IA (``POST /fields/{id}/frames`` de
VALTEXA-B), com a calibração medida para recortes da borda (``<pesos>.edge-fusion.json``).
Assim o diagnóstico por planta, a incidência e a prescrição do talhão contam também as
plantas sadias, não só os eventos que subiram em original.

Geometria de cada quadro (a fusão precisa da linha de plantas e do metro ao longo dela):

1. **da navegação**, quando o Rover manda ``navigation.row_left``/``row_right`` e
   ``x_m`` (a pilha de navegação sabe em que rua está e quanto andou) — preferida;
2. **do GNSS**, projetado no talhão: ``x_m`` ao longo de ``row_azimuth_deg`` e a linha
   pelo afastamento perpendicular, com ``row_spacing_m``. Supõe o Rover no meio da rua e
   o contorno do talhão a meia rua das linhas de fora (a linha ``G1`` é a primeira a
   partir do lado esquerdo do azimute). As linhas assim estimadas levam o prefixo ``G``.

Quadro sem a geometria (talhão sem azimute ou espaçamento, GNSS sem rumo, câmera sem
lado) não entra: ``fusion_status = sem_geometria``, com o motivo, e o painel mostra
quantos ficaram de fora. Nada aqui inventa posição.

Idempotência: cada resultado vai uma vez (``fusion_status`` deixa de ser nulo) e a IA
recusa o mesmo ``frame_id`` na mesma passada (``duplicado``). Serviço fora do ar: o
resultado fica pendente e vai no próximo ciclo do worker.

A passada da missão só é fechada na IA (consolida as plantas, compara com a anterior)
depois que os resultados chegaram: missão concluída, nenhum pendente e o número de
resultados igual ao ``frames_done`` do ``MISSION_COMPLETED`` do Rover — ou, se esse
evento não chegar, ``FECHA_SEM_EVENTO`` depois do último resultado recebido.
"""

from __future__ import annotations

import logging
import math
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from valtexa.models import Device, EdgeRecord, Field, Mission, MissionState
from valtexa.models.base import as_utc
from valtexa.services import geo, plant_map

logger = logging.getLogger(__name__)

HFOV_PADRAO = 127.0
"""Campo de visão horizontal da OAK-D Pro W, quando o resultado não diz."""

FECHA_SEM_EVENTO = timedelta(hours=6)
"""Sem o ``MISSION_COMPLETED`` do Rover, quanto esperar sem resultado novo para fechar."""

LOTE = 200


class SemGeometriaError(ValueError):
    """O quadro não diz (nem dá para estimar) a linha e a posição ao longo dela."""


# ---------------------------------------------------------------------------
# Geometria
# ---------------------------------------------------------------------------


def geometria(field: Field, corpo: dict) -> dict:
    """``row_id``, ``side`` (o da fusão) e ``x_m`` do quadro — ou :class:`SemGeometriaError`."""
    recortes = corpo.get("tiles") or {}
    lado = recortes.get("side")
    if lado not in ("left", "right"):
        raise SemGeometriaError("câmera sem lado (hardware.json: 'lado' de cada câmera)")
    nav = corpo.get("navigation") or {}
    linha, x = nav.get(f"row_{lado}"), nav.get("x_m")
    if linha is not None and _finito(x):
        return {"row_id": str(linha)[:80], "side": lado, "x_m": float(x), "fonte": "navegacao"}
    return _pelo_gnss(field, corpo, lado)


def _pelo_gnss(field: Field, corpo: dict, lado: str) -> dict:
    pos = corpo.get("position") or {}
    lat, lon, rumo = pos.get("lat"), pos.get("lon"), pos.get("heading_deg")
    if not (_finito(lat) and _finito(lon)):
        raise SemGeometriaError("sem posição GNSS e sem linha da navegação")
    if not _finito(rumo):
        raise SemGeometriaError("GNSS sem rumo (parado?) e sem linha da navegação")
    if field.row_azimuth_deg is None or not field.row_spacing_m or not field.boundary:
        raise SemGeometriaError("talhão sem azimute, espaçamento entre linhas ou contorno")
    try:
        contorno = geo.as_points(field.boundary)
    except geo.InvalidPolygonError as exc:
        raise SemGeometriaError(f"contorno do talhão inválido: {exc}") from exc
    origem = geo.centroid(contorno)
    az = math.radians(field.row_azimuth_deg)
    ao_longo = (math.sin(az), math.cos(az))  # (leste, norte) no sentido do azimute
    transversal = (math.cos(az), -math.sin(az))  # à direita de quem segue o azimute

    def projeta(ponto) -> tuple[float, float]:
        e, n = geo.to_local((float(ponto[0]), float(ponto[1])), origem[0], origem[1])
        return e * ao_longo[0] + n * ao_longo[1], e * transversal[0] + n * transversal[1]

    u, v = projeta((lon, lat))
    v_min = min(projeta(p)[1] for p in contorno)
    # Andando contra o azimute, a esquerda do Rover é a direita do azimute.
    sentido = 1.0 if math.cos(math.radians(float(rumo)) - az) >= 0 else -1.0
    para_o_lado = -sentido if lado == "left" else sentido
    v_linha = v + para_o_lado * field.row_spacing_m / 2
    numero = math.floor((v_linha - v_min) / field.row_spacing_m) + 1
    # A fusão põe o recorte ao longo da linha pelo sentido de avanço; aqui o eixo é o
    # azimute (fixo entre passadas), então quem anda contra ele troca o sinal do lado.
    lado_fusao = lado if sentido > 0 else ("right" if lado == "left" else "left")
    return {"row_id": f"G{numero}", "side": lado_fusao, "x_m": round(u, 3), "fonte": "gnss"}


def _finito(valor) -> bool:
    try:
        return valor is not None and math.isfinite(float(valor))
    except (TypeError, ValueError):
        return False


# ---------------------------------------------------------------------------
# O quadro para a IA
# ---------------------------------------------------------------------------


def quadro(field: Field, registro: EdgeRecord) -> dict:
    """O ``EdgeFrameIn`` de VALTEXA-B. :class:`SemGeometriaError` ou ``ValueError`` se não dá."""
    corpo = registro.payload or {}
    recortes = corpo.get("tiles") or {}
    rotulos, probs = recortes.get("labels"), recortes.get("probabilities")
    caixas = recortes.get("boxes") or []
    if not rotulos or not probs or len(probs) != len(caixas):
        raise ValueError("sem probabilidades por recorte (perfil com tile_probabilities=full)")
    altura = recortes.get("camera_height_mm")
    distancia = recortes.get("distance_mm")
    if not _finito(altura) or not _finito(distancia):
        raise SemGeometriaError("sem altura de câmera ou distância até a planta")
    geo_ = geometria(field, corpo)
    alturas = recortes.get("heights_mm") or [None] * len(caixas)
    zonas = recortes.get("zones") or [[] for _ in caixas]
    # A geometria 3D do Rover (Nível 2, 5.3). O conjunto conformal da borda NÃO vai: a fusão da
    # borda foi calibrada sem ele, e dividir a evidência pelo conjunto mudaria a calibração.
    geometrias = recortes.get("geometria")
    if not isinstance(geometrias, list) or len(geometrias) != len(caixas):
        geometrias = [None] * len(caixas)
    tiles = []
    for caixa, p, h, z, g in zip(caixas, probs, alturas, zonas, geometrias, strict=True):
        if len(p) != len(rotulos):
            raise ValueError("recorte com número de probabilidades diferente dos rótulos")
        melhor = max(range(len(p)), key=p.__getitem__)
        tiles.append({
            "box": list(caixa), "predicted_class": rotulos[melhor],
            "probabilities": dict(zip(rotulos, map(float, p), strict=True)),
            "confidence": float(p[melhor]), "height_mm": h, "zones": list(z or []),
            **({"geometria": g} if isinstance(g, dict) else {}),
        })
    frame = corpo.get("frame") or {}
    pos = corpo.get("position") or {}
    return {
        "row_id": geo_["row_id"],
        "side": geo_["side"],
        "x_m": geo_["x_m"],
        "camera_height_mm": float(altura),
        "distance_mm": float(distancia),
        "pass_id": registro.mission_id,
        "timestamp": as_utc(registro.occurred_at).isoformat(),
        "frame_id": registro.record_id,
        "camera_id": frame.get("camera_id"),
        "image_width_px": int(frame.get("width") or 0) or 4056,
        "hfov_deg": float(recortes.get("hfov_deg") or HFOV_PADRAO),
        "lat": pos.get("lat") if _finito(pos.get("lat")) else None,
        "lon": pos.get("lon") if _finito(pos.get("lon")) else None,
        "heading_deg": pos.get("heading_deg") if _finito(pos.get("heading_deg")) else None,
        # O espaçamento do cadastro: no café varia de 0,5 a 1 m entre fazendas, e é ele que
        # separa um pé do vizinho na fusão.
        "plant_spacing_m": field.plant_spacing_m if _finito(field.plant_spacing_m) else None,
        "tiles": tiles,
    }


# ---------------------------------------------------------------------------
# Worker
# ---------------------------------------------------------------------------


def _marca(registro: EdgeRecord, status: str, detalhe: str | None, agora: datetime) -> None:
    registro.fusion_status = status
    registro.fusion_detail = None if detalhe is None else str(detalhe)[:200]
    registro.fused_at = agora


def varrer(session: Session, limite: int = LOTE, *, agora: datetime | None = None) -> int:
    """Manda os resultados pendentes para a fusão. Devolve quantos saíram de pendente.

    Para no primeiro "serviço fora do ar": os que faltam vão no próximo ciclo, na ordem.
    """
    agora = agora or datetime.now(UTC)
    pendentes = list(session.scalars(
        select(EdgeRecord)
        .where(EdgeRecord.kind == "result", EdgeRecord.fusion_status.is_(None))
        .order_by(EdgeRecord.occurred_at)
        .limit(limite)
    ))
    feitos = 0
    talhoes: dict[str, Field | None] = {}
    for registro in pendentes:
        if not registro.field_id or not registro.mission_id or not registro.model_key:
            _marca(registro, "sem_talhao", "resultado sem talhão, missão ou modelo", agora)
            feitos += 1
            continue
        if registro.field_id not in talhoes:
            talhoes[registro.field_id] = session.get(Field, registro.field_id)
        talhao = talhoes[registro.field_id]
        try:
            corpo = quadro(talhao, registro)
        except SemGeometriaError as exc:
            _marca(registro, "sem_geometria", str(exc), agora)
            feitos += 1
            continue
        except (ValueError, TypeError, KeyError) as exc:
            _marca(registro, "sem_recortes", str(exc), agora)
            feitos += 1
            continue
        try:
            resposta = plant_map.ingest_edge_frame(registro.field_id, registro.model_key, corpo)
        except plant_map.PlantMapRefusedError as exc:
            _marca(registro, "recusado", str(exc), agora)
            feitos += 1
            continue
        except plant_map.PlantMapUnavailableError as exc:
            logger.info("Fusão da borda adiada: %s", exc)
            break
        _marca(registro, "duplicado" if resposta.get("duplicated") else "ok",
               resposta.get("calibration"), agora)
        feitos += 1
    session.flush()
    return feitos


def fechar_passadas(session: Session, *, agora: datetime | None = None) -> int:
    """Fecha na IA a passada de cada missão concluída cujos resultados já foram fundidos."""
    agora = agora or datetime.now(UTC)
    candidatas = session.scalars(
        select(Mission).where(Mission.state == MissionState.COMPLETED,
                              Mission.fusion_closed_at.is_(None))
        .where(select(EdgeRecord.id).where(EdgeRecord.mission_id == Mission.id,
                                           EdgeRecord.kind == "result").exists())
    )
    fechadas = 0
    for missao in candidatas:
        if not pronta_para_fechar(session, missao, agora):
            continue
        try:
            resposta = plant_map._request(
                "POST",
                f"/fields/{plant_map._seg(missao.field_id)}/passes/{plant_map._seg(missao.id)}"
                "/close",
            )
        except plant_map.PlantMapRefusedError as exc:
            logger.warning("Passada %s não fechou: %s", missao.id, exc)
            resposta = {}
        except plant_map.PlantMapUnavailableError as exc:
            logger.info("Fechamento da passada %s adiado: %s", missao.id, exc)
            break
        # 404: nenhum quadro da missão entrou na fusão (todos sem geometria) — nada a fechar.
        missao.fusion_closed_at = agora
        fechadas += 1 if resposta is not None else 0
    session.flush()
    return fechadas


def fecha_pelo_worker(session: Session, missao: Mission) -> bool:
    """A passada desta missão espera os resultados do Rover Runtime (fecha no worker)?

    Sim se o robô roda o Runtime (informou ``runtime_version``) ou se já há resultado
    sincronizado da missão. Os resultados sobem depois do ``complete`` quando o Rover
    esteve sem enlace; fechar na hora recusaria todos eles.
    """
    robo = session.get(Device, missao.device_id)
    if robo is not None and robo.runtime_version:
        return True
    return session.scalar(select(EdgeRecord.id).where(
        EdgeRecord.mission_id == missao.id, EdgeRecord.kind == "result").limit(1)) is not None


def pronta_para_fechar(session: Session, missao: Mission, agora: datetime) -> bool:
    base = select(func.count()).select_from(EdgeRecord).where(
        EdgeRecord.mission_id == missao.id, EdgeRecord.kind == "result")
    if session.scalar(base.where(EdgeRecord.fusion_status.is_(None))):
        return False
    recebidos = session.scalar(base) or 0
    concluido = session.scalars(
        select(EdgeRecord).where(EdgeRecord.mission_id == missao.id,
                                 EdgeRecord.kind == "event",
                                 EdgeRecord.type == "MISSION_COMPLETED")
    ).first()
    if concluido is not None:
        esperados = ((concluido.payload or {}).get("payload") or {}).get("frames_done")
        if isinstance(esperados, int) and recebidos >= esperados:
            return True
    ultimo = session.scalar(select(func.max(EdgeRecord.received_at)).where(
        EdgeRecord.mission_id == missao.id, EdgeRecord.kind == "result"))
    return ultimo is not None and agora - as_utc(ultimo) >= FECHA_SEM_EVENTO


def resumo(session: Session, mission_id: str) -> dict[str, int]:
    """Quantos resultados da missão em cada estado da fusão (painel e relatório)."""
    linhas = session.execute(
        select(EdgeRecord.fusion_status, func.count())
        .where(EdgeRecord.mission_id == mission_id, EdgeRecord.kind == "result")
        .group_by(EdgeRecord.fusion_status)
    )
    return {(status or "pendente"): n for status, n in linhas}
