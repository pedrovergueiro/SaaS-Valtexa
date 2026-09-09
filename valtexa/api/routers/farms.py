"""Fazendas, talhões e zonas."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from valtexa.api.deps import Principal, get_scoped, require, scoped
from valtexa.db import get_session
from valtexa.models import ActorType, Farm, Field, SubjectType, Zone
from valtexa.schemas import (
    FarmCreate,
    FarmOut,
    FieldCreate,
    FieldOut,
    ZoneCreate,
    ZoneOut,
)
from valtexa.security import rbac
from valtexa.services import audit, geo

router = APIRouter(tags=["fazendas"])


@router.get("/farms", response_model=list[FarmOut], summary="Lista as fazendas")
def list_farms(
    principal: Principal = Depends(require(rbac.FARM_READ)),
    session: Session = Depends(get_session),
) -> list[FarmOut]:
    farms = list(session.scalars(scoped(select(Farm).order_by(Farm.name), Farm, principal)))
    counts = dict(
        session.execute(
            scoped(
                select(Field.farm_id, func.count(Field.id)).group_by(Field.farm_id),
                Field,
                principal,
            )
        ).all()
    )
    return [_farm_out(farm, counts.get(farm.id, 0)) for farm in farms]


@router.post(
    "/farms",
    response_model=FarmOut,
    status_code=status.HTTP_201_CREATED,
    summary="Cadastra uma fazenda",
)
def create_farm(
    payload: FarmCreate,
    principal: Principal = Depends(require(rbac.FARM_MANAGE)),
    session: Session = Depends(get_session),
) -> FarmOut:
    farm = Farm(tenant_id=principal.tenant_id, **payload.model_dump())
    session.add(farm)
    audit.record(
        session,
        tenant_id=principal.tenant_id,
        action="farm.created",
        subject_type=SubjectType.FIELD,
        subject_id=farm.id,
        actor_type=ActorType.USER,
        actor_id=principal.user_id,
        actor_label=principal.user.email,
    )
    session.commit()
    return _farm_out(farm, 0)


@router.get("/farms/{farm_id}/fields", response_model=list[FieldOut], summary="Talhões")
def list_fields(
    farm_id: str,
    principal: Principal = Depends(require(rbac.FARM_READ)),
    session: Session = Depends(get_session),
) -> list[FieldOut]:
    get_scoped(session, Farm, farm_id, principal)
    rows = session.scalars(
        scoped(select(Field).where(Field.farm_id == farm_id).order_by(Field.name), Field, principal)
    )
    return [_field_out(row) for row in rows]


@router.post(
    "/farms/{farm_id}/fields",
    response_model=FieldOut,
    status_code=status.HTTP_201_CREATED,
    summary="Cadastra um talhão",
)
def create_field(
    farm_id: str,
    payload: FieldCreate,
    principal: Principal = Depends(require(rbac.FARM_MANAGE)),
    session: Session = Depends(get_session),
) -> FieldOut:
    """Cria o talhão e calcula a área a partir do limite.

    A área é derivada, e não informada: um número digitado à mão divergiria do
    polígono, e é ele que manda na dose e na cerca virtual.
    """
    get_scoped(session, Farm, farm_id, principal)
    _validate_polygon(payload.boundary, "boundary")

    row = Field(
        tenant_id=principal.tenant_id,
        farm_id=farm_id,
        area_ha=round(geo.area_ha(payload.boundary), 4),
        **payload.model_dump(),
    )
    session.add(row)
    audit.record(
        session,
        tenant_id=principal.tenant_id,
        action="field.created",
        subject_type=SubjectType.FIELD,
        subject_id=row.id,
        actor_type=ActorType.USER,
        actor_id=principal.user_id,
        actor_label=principal.user.email,
        payload={"area_ha": row.area_ha, "crop": row.crop},
    )
    session.commit()
    return _field_out(row)


@router.get("/fields/{field_id}", response_model=FieldOut, summary="Um talhão")
def get_field(
    field_id: str,
    principal: Principal = Depends(require(rbac.FARM_READ)),
    session: Session = Depends(get_session),
) -> FieldOut:
    return _field_out(get_scoped(session, Field, field_id, principal))


@router.get("/fields/{field_id}/zones", response_model=list[ZoneOut], summary="Zonas do talhão")
def list_zones(
    field_id: str,
    principal: Principal = Depends(require(rbac.FARM_READ)),
    session: Session = Depends(get_session),
) -> list[ZoneOut]:
    get_scoped(session, Field, field_id, principal)
    rows = session.scalars(
        scoped(select(Zone).where(Zone.field_id == field_id).order_by(Zone.name), Zone, principal)
    )
    return [_zone_out(row) for row in rows]


@router.post(
    "/fields/{field_id}/zones",
    response_model=ZoneOut,
    status_code=status.HTTP_201_CREATED,
    summary="Cadastra uma zona de manejo",
)
def create_zone(
    field_id: str,
    payload: ZoneCreate,
    principal: Principal = Depends(require(rbac.FARM_MANAGE)),
    session: Session = Depends(get_session),
) -> ZoneOut:
    """A zona precisa caber no talhão.

    Uma zona que vaza para fora abriria um caminho para autorizar aplicação
    além do limite — a checagem de cerca virtual do safety engine parte da
    geometria cadastrada aqui.
    """
    field_row = get_scoped(session, Field, field_id, principal)
    _validate_polygon(payload.boundary, "boundary")

    if not geo.polygon_contains_polygon(field_row.boundary, payload.boundary):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "A zona precisa estar contida no limite do talhão.",
        )

    zone = Zone(
        tenant_id=principal.tenant_id,
        field_id=field_id,
        area_ha=round(geo.area_ha(payload.boundary), 4),
        **payload.model_dump(),
    )
    session.add(zone)
    session.commit()
    return _zone_out(zone)


def _validate_polygon(polygon: list, field_name: str) -> None:
    try:
        geo.as_points(polygon)
    except geo.InvalidPolygonError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, f"{field_name}: {exc}"
        ) from exc


def _farm_out(farm: Farm, field_count: int) -> FarmOut:
    return FarmOut(
        id=farm.id,
        name=farm.name,
        timezone=farm.timezone,
        center_lat=farm.center_lat,
        center_lon=farm.center_lon,
        base_lat=farm.base_lat,
        base_lon=farm.base_lon,
        area_ha=farm.area_ha,
        fields=field_count,
    )


def _field_out(row: Field) -> FieldOut:
    return FieldOut(
        id=row.id,
        farm_id=row.farm_id,
        name=row.name,
        crop=row.crop,
        variety=row.variety,
        crop_stage=row.crop_stage,
        planted_on=row.planted_on,
        row_spacing_m=row.row_spacing_m,
        area_ha=row.area_ha,
        boundary=row.boundary,
    )


def _zone_out(row: Zone) -> ZoneOut:
    return ZoneOut(
        id=row.id, field_id=row.field_id, name=row.name, area_ha=row.area_ha, boundary=row.boundary
    )
