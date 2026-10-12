"""Validação de campo: o agrônomo anota as plantas que o Rover viu, e o Rover é medido.

Ver :mod:`valtexa.services.validacao_campo`. Leitura com ``farm:read``; anotar exige
``diagnosis:review`` (o papel do agrônomo).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, ConfigDict
from pydantic import Field as PField
from sqlalchemy.orm import Session

from valtexa.api.deps import Principal, get_scoped, require
from valtexa.db import get_session
from valtexa.models import ActorType, Field, Mission, SubjectType
from valtexa.security import rbac
from valtexa.services import audit, plant_map, validacao_campo

router = APIRouter(tags=["validação de campo"])

PLANT_ID = r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$"


class RotuloIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str = PField(min_length=1, max_length=80,
                        description="Classe do modelo: Healthy, Rust, Leaf_Miner_Damage...")
    incidence_percent: float | None = PField(default=None, ge=0, le=100,
                                             description="% de folhas com a doença (MIP).")
    notes: str | None = PField(default=None, max_length=2000)
    row_ref: str | None = PField(default=None, max_length=80)


def _missao_do_talhao(session: Session, talhao: Field, mission_id: str) -> Mission:
    missao = session.get(Mission, mission_id)
    if missao is None or missao.field_id != talhao.id or missao.tenant_id != talhao.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Missão não encontrada neste talhão.")
    return missao


def _ia(exc: plant_map.PlantMapUnavailableError) -> HTTPException:
    return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc))


@router.get("/fields/{field_id}/validacao/{mission_id}",
            summary="Plantas da passada com o rótulo de campo ao lado")
def plantas_da_validacao(
    field_id: str, mission_id: str,
    principal: Principal = Depends(require(rbac.FARM_READ)),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    talhao = get_scoped(session, Field, field_id, principal)
    _missao_do_talhao(session, talhao, mission_id)
    try:
        return validacao_campo.plantas(session, talhao, mission_id)
    except plant_map.PlantMapUnavailableError as exc:
        raise _ia(exc) from exc


@router.put("/fields/{field_id}/validacao/{mission_id}/{plant_ref}",
            summary="Anota o que a planta tem (agrônomo)")
def anota_planta(
    payload: RotuloIn,
    field_id: str, mission_id: str,
    plant_ref: str = Path(pattern=PLANT_ID),
    principal: Principal = Depends(require(rbac.DIAGNOSIS_REVIEW)),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    talhao = get_scoped(session, Field, field_id, principal)
    _missao_do_talhao(session, talhao, mission_id)
    try:
        rotulo = validacao_campo.anota(
            session, talhao, mission_id, plant_ref, label=payload.label,
            incidence_percent=payload.incidence_percent, notes=payload.notes,
            user_id=principal.user.id, row_ref=payload.row_ref)
    except validacao_campo.RotuloInvalidoError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    audit.record(session, action="field.plant_labeled", subject_type=SubjectType.FIELD,
                 subject_id=talhao.id, actor_type=ActorType.USER, actor_id=principal.user.id,
                 tenant_id=talhao.tenant_id, new_state=f"{plant_ref}={rotulo.label}",
                 reason=f"missão {mission_id}")
    session.commit()
    return {"plant_id": rotulo.plant_ref, "label": rotulo.label,
            "incidence_percent": rotulo.incidence_percent, "notes": rotulo.notes}


@router.delete("/fields/{field_id}/validacao/{mission_id}/{plant_ref}",
               status_code=status.HTTP_204_NO_CONTENT, summary="Apaga o rótulo de uma planta")
def apaga_rotulo(
    field_id: str, mission_id: str,
    plant_ref: str = Path(pattern=PLANT_ID),
    principal: Principal = Depends(require(rbac.DIAGNOSIS_REVIEW)),
    session: Session = Depends(get_session),
) -> None:
    talhao = get_scoped(session, Field, field_id, principal)
    for r in validacao_campo.rotulos(session, talhao.tenant_id, talhao.id, mission_id):
        if r.plant_ref == plant_ref:
            session.delete(r)
            session.commit()
            return
    raise HTTPException(status.HTTP_404_NOT_FOUND, "Planta sem rótulo nesta passada.")


@router.get("/fields/{field_id}/validacao/{mission_id}/relatorio",
            summary="Rover contra agrônomo: sensibilidade e alarme falso por planta")
def relatorio_da_validacao(
    field_id: str, mission_id: str,
    principal: Principal = Depends(require(rbac.FARM_READ)),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    talhao = get_scoped(session, Field, field_id, principal)
    _missao_do_talhao(session, talhao, mission_id)
    try:
        return validacao_campo.relatorio(session, talhao, mission_id)
    except plant_map.PlantMapUnavailableError as exc:
        raise _ia(exc) from exc


@router.get("/fields/{field_id}/validacao.csv", response_class=PlainTextResponse,
            summary="Rótulos de campo no formato de calibração (--labels)")
def rotulos_para_calibrar(
    field_id: str,
    mission_id: str | None = Query(default=None, description="Uma passada; padrão: todas."),
    principal: Principal = Depends(require(rbac.FARM_READ)),
    session: Session = Depends(get_session),
) -> PlainTextResponse:
    talhao = get_scoped(session, Field, field_id, principal)
    return PlainTextResponse(
        validacao_campo.rotulos_csv(session, talhao.tenant_id, talhao.id, mission_id),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="rotulos-{talhao.id}.csv"'},
    )
