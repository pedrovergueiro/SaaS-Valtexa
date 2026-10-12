"""Plantas do talhão: o que o rover viu, planta a planta, e o mapa delas.

A fonte é a fusão por planta do serviço de inferência (:mod:`valtexa.services.plant_map`).
Aqui ficam o escopo por cliente — o talhão tem de ser dele — e o vocabulário do
SaaS; o conteúdo vem como a inferência o produz.
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from valtexa.api.deps import Principal, get_scoped, require
from valtexa.db import get_session
from valtexa.models import CapturePlatform, Field
from valtexa.security import rbac
from valtexa.services import ai_pipeline, plans, plant_map

router = APIRouter(tags=["plantas"])

PLANT_ID = r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$"
"""O id da planta vai no caminho da URL da inferência: sem barra, sem ``..``."""


def _unavailable(exc: plant_map.PlantMapUnavailableError) -> HTTPException:
    return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc))


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
