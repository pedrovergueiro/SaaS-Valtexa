"""Plantas do talhão: o que o rover viu, planta a planta, e o mapa delas.

A fonte é a fusão por planta do serviço de inferência (:mod:`valtexa.services.plant_map`).
Aqui ficam o escopo por cliente — o talhão tem de ser dele — e o vocabulário do
SaaS; o conteúdo vem como a inferência o produz.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from pydantic import Field as PydField
from sqlalchemy.orm import Session

from valtexa.api.deps import Principal, get_scoped, require
from valtexa.db import get_session
from valtexa.models import ActorType, CapturePlatform, Field, SubjectType
from valtexa.security import rbac
from valtexa.services import ai_pipeline, audit, plans, plant_map

router = APIRouter(tags=["plantas"])

PLANT_ID = r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$"
"""O id da planta vai no caminho da URL da inferência: sem barra, sem ``..``."""


def _unavailable(exc: plant_map.PlantMapUnavailableError) -> HTTPException:
    return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc))


def _gemeo(chamada: Any, *args: Any, sem_talhao: str) -> Any:
    """Chama a inferência para o gêmeo e traduz: recusa com o status dela (409 falta algo no
    talhão, 422 pedido proibido), fora do ar 503, talhão sem histórico 404."""
    try:
        body = chamada(*args)
    except plant_map.PlantMapRefusedError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc
    except plant_map.PlantMapUnavailableError as exc:
        raise _unavailable(exc) from exc
    if body is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, sem_talhao)
    return body


@router.get("/fields/{field_id}/plants", summary="Diagnóstico de cada planta do talhão")
def field_plants(
    field_id: str,
    pass_id: str | None = Query(default=None, description="Passada (missão); padrão: a última."),
    principal: Principal = Depends(require(rbac.FARM_READ)),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    """Uma entrada por planta: status, posterior por doença, incidência, câmeras que a viram.

    ``status`` é ``sadia``, ``suspeita``, ``doente`` ou ``revisar``. Vazio até o
    rover passar pelo talhão com a câmera no quadro.
    """
    get_scoped(session, Field, field_id, principal)
    try:
        return plant_map.plants(field_id, pass_id)
    except plant_map.PlantMapUnavailableError as exc:
        raise _unavailable(exc) from exc


@router.get("/fields/{field_id}/plants/map", summary="Mapa das plantas do talhão (GeoJSON)")
def field_plant_map(
    field_id: str,
    pass_id: str | None = Query(default=None),
    principal: Principal = Depends(require(rbac.FARM_READ)),
    session: Session = Depends(get_session),
) -> JSONResponse:
    get_scoped(session, Field, field_id, principal)
    try:
        body = plant_map.geojson(field_id, pass_id)
    except plant_map.PlantMapUnavailableError as exc:
        raise _unavailable(exc) from exc
    return JSONResponse(body, media_type="application/geo+json")


@router.get(
    "/fields/{field_id}/plants/{plant_id}/evolution",
    summary="Histórico de uma planta entre passadas",
)
def plant_evolution(
    field_id: str,
    plant_id: str = Path(pattern=PLANT_ID, description="Ex.: 1-P0009."),
    principal: Principal = Depends(require(rbac.FARM_READ)),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    get_scoped(session, Field, field_id, principal)
    try:
        body = plant_map.evolution(field_id, plant_id)
    except plant_map.PlantMapUnavailableError as exc:
        raise _unavailable(exc) from exc
    if body is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Planta não encontrada neste talhão.")
    return body


@router.get("/fields/{field_id}/prevalence", summary="Prevalência das doenças no talhão")
def field_prevalence(
    field_id: str,
    principal: Principal = Depends(require(rbac.FARM_READ)),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Quanto de cada doença o talhão tem, estimado sem rótulo, contra o do treino do modelo."""
    row = get_scoped(session, Field, field_id, principal)
    try:
        model_key = ai_pipeline.resolve_model(
            session, row.crop, CapturePlatform.GROUND, row.ai_model, tenant_id=row.tenant_id
        )
        body = plant_map.prevalence(field_id, model_key)
    except ai_pipeline.NoModelForCaptureError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except plant_map.PlantMapUnavailableError as exc:
        raise _unavailable(exc) from exc
    if body is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "O rover ainda não passou por este talhão.")
    return body


@router.get("/fields/{field_id}/plants/incidence", summary="Fração de plantas doentes do talhão")
def field_plant_incidence(
    field_id: str,
    pass_id: str | None = Query(default=None, description="Passada (missão); padrão: a última."),
    principal: Principal = Depends(require(rbac.FARM_READ)),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Plantas doentes / plantas vistas, corrigida pela sensibilidade e pelo alarme falso
    por planta da calibração da fusão, com intervalo de 95% (``method`` diz se houve
    calibração). Conta as sadias também: os quadros normais do Rover entram na fusão
    pelas probabilidades dos recortes (``services.fusao_borda``)."""
    get_scoped(session, Field, field_id, principal)
    try:
        body = plant_map.incidence(field_id, pass_id)
    except plant_map.PlantMapUnavailableError as exc:
        raise _unavailable(exc) from exc
    if body is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "O rover ainda não passou por este talhão.")
    return body


@router.post(
    "/fields/{field_id}/plants/prescription",
    summary="Em quais plantas o tratamento se paga (recomendação)",
)
def field_plant_prescription(
    field_id: str,
    pedido: dict[str, Any] = Body(
        description=(
            "O pedido de ``POST /fields/{id}/prescription`` de VALTEXA-B: ``doenca``, "
            "``produto`` (preço, dose, eficácia da bula, carência, culturas e doenças do "
            "registro), ``economia`` (perda por planta, custo, orçamento), ``contagio``, "
            "``dias_ate_colheita``, ``pass_id``. Os números são do produtor: sem padrão."
        ),
    ),
    formato: Literal["json", "geojson"] = Query(default="json"),
    principal: Principal = Depends(require(rbac.DECISION_READ)),
    session: Session = Depends(get_session),
) -> JSONResponse:
    """Prescrição planta a planta sobre a fusão calibrada: trata a planta quando ela, mais
    o que infectaria, vale mais que o tratamento. **Recomendação** — nada é aplicado sem o
    agrônomo aprovar uma missão de pulverização. 422 quando a bula, a carência ou o
    registro proíbem; 404 sem passada do rover no talhão."""
    get_scoped(session, Field, field_id, principal)
    plans.exigir_recurso(session, principal.tenant_id, "prescricao")
    try:
        body = plant_map.prescription(field_id, pedido, formato)
    except plant_map.PlantMapRefusedError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    except plant_map.PlantMapUnavailableError as exc:
        raise _unavailable(exc) from exc
    if body is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "O rover ainda não passou por este talhão.")
    media = "application/geo+json" if formato == "geojson" else "application/json"
    return JSONResponse(body, media_type=media)


# ---------------------------------------------------------------------------
# Gêmeo digital do talhão (``app.gemeo`` de VALTEXA-B)
# ---------------------------------------------------------------------------

SEM_PASSADA = "O rover ainda não passou por este talhão."
DOENCA = r"^[A-Za-z][A-Za-z_]{0,63}$"


@router.get("/fields/{field_id}/clima", summary="A série climática do talhão, por fonte")
def field_clima(
    field_id: str,
    principal: Principal = Depends(require(rbac.FARM_READ)),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    get_scoped(session, Field, field_id, principal)
    return _gemeo(plant_map.clima, field_id, sem_talhao=SEM_PASSADA)


@router.post("/fields/{field_id}/clima", summary="Acrescenta tempo ao talhão (estação)")
def field_clima_enviar(
    field_id: str,
    pedido: dict[str, Any] = Body(
        description=(
            "O pedido de ``POST /fields/{id}/clima`` de VALTEXA-B: ``registros_horarios`` "
            "(time, temperatura_c, ur, chuva_mm, molhamento opcional), ``dias`` prontos, ou "
            "``buscar_open_meteo`` (só se a inferência tiver CLIMA_OPEN_METEO ligado)."
        ),
    ),
    principal: Principal = Depends(require(rbac.FARM_MANAGE)),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    get_scoped(session, Field, field_id, principal)
    return _gemeo(plant_map.enviar_clima, field_id, pedido, sem_talhao=SEM_PASSADA)


@router.get("/fields/{field_id}/gemeo", summary="Gêmeo digital: o grafo e os modelos ajustados")
def field_gemeo(
    field_id: str,
    principal: Principal = Depends(require(rbac.FARM_READ)),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    get_scoped(session, Field, field_id, principal)
    return _gemeo(plant_map.gemeo, field_id, sem_talhao=SEM_PASSADA)


@router.post(
    "/fields/{field_id}/gemeo/ajuste",
    summary="Ajusta o modelo epidemiológico às passadas do talhão",
)
def field_gemeo_ajuste(
    field_id: str,
    doenca: str = Query(pattern=DOENCA, description="Classe do modelo, ex.: Rust."),
    principal: Principal = Depends(require(rbac.FARM_MANAGE)),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Leva minutos num talhão grande; um ajuste por talhão de cada vez (409 no segundo)."""
    get_scoped(session, Field, field_id, principal)
    return _gemeo(plant_map.ajustar_gemeo, field_id, doenca, sem_talhao=SEM_PASSADA)


@router.get(
    "/fields/{field_id}/gemeo/previsao",
    summary="Onde a doença vai estar: risco por planta, janelas de infecção e focos",
)
def field_gemeo_previsao(
    field_id: str,
    doenca: str = Query(pattern=DOENCA),
    horizonte_dias: int = Query(default=21, ge=1, le=90),
    membros: int = Query(default=16, ge=1, le=64),
    plantas: Literal["todas", "em_risco", "nenhuma"] = Query(default="em_risco"),
    principal: Principal = Depends(require(rbac.DECISION_READ)),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """O risco inclui o que o Rover ainda não vê (o latente). Sem ajuste, o modelo usa o
    prior e o aviso diz; além da previsão de tempo, climatologia, e o aviso diz também."""
    get_scoped(session, Field, field_id, principal)
    params = {"doenca": doenca, "horizonte_dias": horizonte_dias, "membros": membros,
              "plantas": plantas}
    return _gemeo(plant_map.previsao_gemeo, field_id, params, sem_talhao=SEM_PASSADA)


class LevantamentoAereoIn(BaseModel):
    """Um levantamento aéreo processado (fora da plataforma), em GeoJSON."""

    model_config = ConfigDict(extra="forbid")

    doenca: str = PydField(pattern=DOENCA)
    pass_id: str = PydField(min_length=1, max_length=80, description="Identificador do voo.")
    voado_em: datetime
    geojson: dict[str, Any] = PydField(
        description="FeatureCollection de Polygon/MultiPolygon com ``properties.tipo`` = "
                    "``cobertura`` (a área voada, uma) ou ``anomalia`` (região suspeita).")


def _aneis(geometria: dict[str, Any]) -> list[list[list[float]]]:
    tipo, coords = geometria.get("type"), geometria.get("coordinates")
    poligonos = [coords] if tipo == "Polygon" else coords if tipo == "MultiPolygon" else None
    if not poligonos:
        raise ValueError(f"geometria {tipo!r}: use Polygon ou MultiPolygon")
    return [[[float(p[0]), float(p[1])] for p in poligono[0]] for poligono in poligonos]


def levantamento_do_geojson(geojson: dict[str, Any]) -> tuple[list[list[float]],
                                                               list[list[list[float]]]]:
    """``(cobertura, anomalias)``. Recusa o que não for exatamente uma cobertura."""
    if geojson.get("type") != "FeatureCollection" or not isinstance(
            geojson.get("features"), list):
        raise ValueError("esperado um FeatureCollection")
    cobertura: list[list[list[float]]] = []
    anomalias: list[list[list[float]]] = []
    for f in geojson["features"][:10_000]:
        tipo = ((f or {}).get("properties") or {}).get("tipo")
        if tipo not in ("cobertura", "anomalia"):
            raise ValueError("cada feição precisa de properties.tipo = cobertura ou anomalia")
        (cobertura if tipo == "cobertura" else anomalias).extend(_aneis(f.get("geometry") or {}))
    if len(cobertura) != 1:
        raise ValueError("exatamente uma cobertura (a área voada) por levantamento")
    return cobertura[0], anomalias


@router.post(
    "/fields/{field_id}/gemeo/levantamento-aereo",
    summary="Importa um levantamento aéreo: as regiões suspeitas entram no gêmeo (canal drone)",
)
def field_gemeo_levantamento(
    field_id: str,
    pedido: LevantamentoAereoIn,
    principal: Principal = Depends(require(rbac.MISSION_CREATE)),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """O voo não é comandado pela plataforma (não há regra de segurança de voo de observação
    — decisão do Pedro): o resultado chega como arquivo. As regiões suspeitas viram evidência
    por planta no canal ``drone`` do gêmeo (suposição de projeto, dita na resposta) e mudam as
    prioridades; o plano do enxame manda o Rover olhar de perto."""
    get_scoped(session, Field, field_id, principal)
    try:
        cobertura, anomalias = levantamento_do_geojson(pedido.geojson)
    except (ValueError, TypeError, IndexError, KeyError) as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            f"GeoJSON do levantamento: {exc}") from exc
    corpo = _gemeo(plant_map.levantamento_gemeo, field_id, {
        "fonte": "drone", "pass_id": pedido.pass_id, "time": pedido.voado_em.isoformat(),
        "doenca": pedido.doenca, "cobertura": cobertura, "anomalias": anomalias},
        sem_talhao=SEM_PASSADA)
    digest = hashlib.sha256(json.dumps(pedido.geojson, sort_keys=True,
                                       separators=(",", ":")).encode()).hexdigest()
    audit.record(session, tenant_id=principal.tenant_id, action="gemeo.levantamento_aereo",
                 subject_type=SubjectType.FIELD, subject_id=field_id,
                 actor_type=ActorType.USER, actor_id=principal.user_id,
                 payload={"pass_id": pedido.pass_id, "doenca": pedido.doenca,
                          "geojson_sha256": digest, "anomalias": len(anomalias),
                          "cobertas": corpo.get("cobertas"),
                          "sinalizadas": corpo.get("sinalizadas")})
    session.commit()
    return {**corpo, "geojson_sha256": digest}


@router.post(
    "/fields/{field_id}/gemeo/prescricao",
    summary="Prescrição sobre o risco previsto, com a data de aplicação (recomendação)",
)
def field_gemeo_prescricao(
    field_id: str,
    pedido: dict[str, Any] = Body(
        description=(
            "O pedido de ``POST /fields/{id}/gemeo/prescricao`` de VALTEXA-B: ``doenca``, "
            "``produto`` e ``economia`` (como na prescrição por planta), ``residual_dias`` e "
            "``curativo`` da bula, ``horizonte_dias``. Os números são do produtor: sem padrão."
        ),
    ),
    formato: Literal["json", "geojson"] = Query(default="json"),
    principal: Principal = Depends(require(rbac.DECISION_READ)),
    session: Session = Depends(get_session),
) -> JSONResponse:
    """Trata onde a doença **vai** estar, antes da próxima janela de infecção, e diz o que
    cada cenário evita no gêmeo. **Recomendação** — nada é aplicado sem o agrônomo aprovar
    uma missão de pulverização."""
    get_scoped(session, Field, field_id, principal)
    plans.exigir_recurso(session, principal.tenant_id, "prescricao")
    body = _gemeo(plant_map.prescricao_gemeo, field_id, pedido, formato, sem_talhao=SEM_PASSADA)
    media = "application/geo+json" if formato == "geojson" else "application/json"
    return JSONResponse(body, media_type=media)
