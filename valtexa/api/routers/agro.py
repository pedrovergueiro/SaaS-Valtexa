"""Insumos, tanques, aplicações e verificação.

O elo ``tanque → lote → produto → missão`` nasce aqui. É o registro de carga que
o safety engine confere antes de liberar uma pulverização: sem ele, a plataforma
não teria como saber o que está fisicamente dentro do drone.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from valtexa.api.deps import Principal, get_scoped, require, scoped
from valtexa.db import get_session
from valtexa.models import (
    ActorType,
    Application,
    Device,
    Product,
    ProductBatch,
    SubjectType,
    Tank,
    TankStatus,
    Verification,
)
from valtexa.schemas import (
    ApplicationOut,
    BatchCreate,
    BatchOut,
    ProductCreate,
    ProductOut,
    TankCreate,
    TankLoad,
    TankOut,
    VerificationOut,
)
from valtexa.security import rbac
from valtexa.services import audit
from valtexa.services import verification as verification_service

router = APIRouter(tags=["insumos e aplicação"])


# ---------------------------------------------------------------------------
# Produtos e lotes
# ---------------------------------------------------------------------------


@router.get("/products", response_model=list[ProductOut], summary="Produtos cadastrados")
def list_products(
    principal: Principal = Depends(require(rbac.PRODUCT_READ)),
    session: Session = Depends(get_session),
) -> list[ProductOut]:
    rows = session.scalars(scoped(select(Product).order_by(Product.name), Product, principal))
    return [_product_out(row) for row in rows]


@router.post(
    "/products",
    response_model=ProductOut,
    status_code=status.HTTP_201_CREATED,
    summary="Cadastra um produto",
)
def create_product(
    payload: ProductCreate,
    principal: Principal = Depends(require(rbac.PRODUCT_MANAGE)),
    session: Session = Depends(get_session),
) -> ProductOut:
    """Cadastra um defensivo e o que ele está autorizado a tratar.

    ``allowed_crops`` e ``authorized_targets`` não são metadados decorativos: o
    safety engine bloqueia a aplicação quando a cultura do talhão ou o alvo
    diagnosticado não constam aqui. Cadastrar errado bloqueia; cadastrar de
    menos também. É de propósito — a lista fechada é o que impede a plataforma
    escolher um produto por conta própria.
    """
    if (
        payload.min_rate_l_ha is not None
        and payload.max_rate_l_ha is not None
        and payload.min_rate_l_ha > payload.max_rate_l_ha
    ):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Dose mínima maior que a máxima."
        )

    product = Product(tenant_id=principal.tenant_id, **payload.model_dump())
    session.add(product)
    audit.record(
        session,
        tenant_id=principal.tenant_id,
        action="product.created",
        subject_type=SubjectType.PRODUCT,
        subject_id=product.id,
        actor_type=ActorType.USER,
        actor_id=principal.user_id,
        actor_label=principal.user.email,
        payload={
            "allowed_crops": payload.allowed_crops,
            "authorized_targets": payload.authorized_targets,
        },
    )
    session.commit()
    return _product_out(product)


@router.post(
    "/products/{product_id}/batches",
    response_model=BatchOut,
    status_code=status.HTTP_201_CREATED,
    summary="Registra um lote",
)
def create_batch(
    product_id: str,
    payload: BatchCreate,
    principal: Principal = Depends(require(rbac.PRODUCT_MANAGE)),
    session: Session = Depends(get_session),
) -> BatchOut:
    """Um lote físico, com validade própria.

    A validade é conferida na hora de autorizar a missão, e não só aqui: um lote
    válido no cadastro pode ter vencido entre o planejamento e o voo.
    """
    get_scoped(session, Product, product_id, principal)
    batch = ProductBatch(
        tenant_id=principal.tenant_id, product_id=product_id, **payload.model_dump()
    )
    session.add(batch)
    session.commit()
    return BatchOut(
        id=batch.id,
        product_id=batch.product_id,
        code=batch.code,
        expires_on=batch.expires_on,
        quantity_l=batch.quantity_l,
    )


@router.get(
    "/products/{product_id}/batches", response_model=list[BatchOut], summary="Lotes de um produto"
)
def list_batches(
    product_id: str,
    principal: Principal = Depends(require(rbac.PRODUCT_READ)),
    session: Session = Depends(get_session),
) -> list[BatchOut]:
    get_scoped(session, Product, product_id, principal)
    rows = session.scalars(
        scoped(
            select(ProductBatch)
            .where(ProductBatch.product_id == product_id)
            .order_by(ProductBatch.code),
            ProductBatch,
            principal,
        )
    )
    return [
        BatchOut(
            id=row.id,
            product_id=row.product_id,
            code=row.code,
            expires_on=row.expires_on,
            quantity_l=row.quantity_l,
        )
        for row in rows
    ]


# ---------------------------------------------------------------------------
# Tanques
# ---------------------------------------------------------------------------


@router.get("/tanks", response_model=list[TankOut], summary="Tanques da frota")
def list_tanks(
    device_id: str | None = None,
    principal: Principal = Depends(require(rbac.PRODUCT_READ)),
    session: Session = Depends(get_session),
) -> list[TankOut]:
    statement = scoped(select(Tank).order_by(Tank.device_id, Tank.index), Tank, principal)
    if device_id:
        statement = statement.where(Tank.device_id == device_id)
    return [_tank_out(row) for row in session.scalars(statement)]


@router.post(
    "/tanks",
    response_model=TankOut,
    status_code=status.HTTP_201_CREATED,
    summary="Cadastra um tanque",
)
def create_tank(
    payload: TankCreate,
    principal: Principal = Depends(require(rbac.DEVICE_MANAGE)),
    session: Session = Depends(get_session),
) -> TankOut:
    get_scoped(session, Device, payload.device_id, principal)
    tank = Tank(tenant_id=principal.tenant_id, **payload.model_dump())
    session.add(tank)
    session.commit()
    return _tank_out(tank)


@router.post("/tanks/{tank_id}/load", response_model=TankOut, summary="Registra a carga")
def load_tank(
    tank_id: str,
    payload: TankLoad,
    principal: Principal = Depends(require(rbac.TANK_LOAD)),
    session: Session = Depends(get_session),
) -> TankOut:
    """Declara o que foi fisicamente colocado no tanque.

    É o registro que o safety engine compara com o produto autorizado na missão.
    Divergência entre os dois bloqueia a aplicação — e essa comparação é a que
    impede a pior falha possível do sistema: aplicar o produto errado numa área
    autorizada para outro.
    """
    tank = get_scoped(session, Tank, tank_id, principal)
    product = get_scoped(session, Product, payload.product_id, principal)
    batch = get_scoped(session, ProductBatch, payload.batch_id, principal)

    if batch.product_id != product.id:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "O lote não pertence a este produto."
        )
    if batch.is_expired(datetime.now(UTC).date()):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"Lote {batch.code!r} venceu em {batch.expires_on}.",
        )
    if payload.volume_l > tank.capacity_l:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"Volume de {payload.volume_l} L excede a capacidade de {tank.capacity_l} L.",
        )

    tank.loaded_product_id = product.id
    tank.loaded_batch_id = batch.id
    tank.current_level_l = payload.volume_l
    tank.status = TankStatus.LOADED
    tank.loaded_at = datetime.now(UTC)
    tank.loaded_by = principal.user_id

    audit.record(
        session,
        tenant_id=principal.tenant_id,
        action="tank.loaded",
        subject_type=SubjectType.TANK,
        subject_id=tank.id,
        actor_type=ActorType.USER,
        actor_id=principal.user_id,
        actor_label=principal.user.email,
        new_state=TankStatus.LOADED.value,
        payload={
            "product": product.name,
            "batch": batch.code,
            "volume_l": payload.volume_l,
        },
    )
    session.commit()
    return _tank_out(tank)


@router.post("/tanks/{tank_id}/empty", response_model=TankOut, summary="Esvazia o tanque")
def empty_tank(
    tank_id: str,
    principal: Principal = Depends(require(rbac.TANK_LOAD)),
    session: Session = Depends(get_session),
) -> TankOut:
    """Zera a carga. Um tanque vazio não autoriza aplicação nenhuma."""
    tank = get_scoped(session, Tank, tank_id, principal)
    tank.loaded_product_id = None
    tank.loaded_batch_id = None
    tank.current_level_l = 0.0
    tank.status = TankStatus.EMPTY
    tank.loaded_at = None
    session.commit()
    return _tank_out(tank)


# ---------------------------------------------------------------------------
# Aplicações e verificação
# ---------------------------------------------------------------------------


@router.get("/applications", response_model=list[ApplicationOut], summary="Aplicações realizadas")
def list_applications(
    field_id: str | None = None,
    limit: int = 100,
    principal: Principal = Depends(require(rbac.MISSION_READ)),
    session: Session = Depends(get_session),
) -> list[ApplicationOut]:
    """Histórico de aplicação — o comprovante do produtor e a prova para a fiscalização."""
    statement = scoped(
        select(Application).order_by(Application.started_at.desc()).limit(min(limit, 500)),
        Application,
        principal,
    )
    if field_id:
        statement = statement.where(Application.field_id == field_id)
    return [_application_out(row) for row in session.scalars(statement)]


@router.get(
    "/verifications", response_model=list[VerificationOut], summary="Verificações pós-tratamento"
)
def list_verifications(
    principal: Principal = Depends(require(rbac.MISSION_READ)),
    session: Session = Depends(get_session),
) -> list[VerificationOut]:
    rows = session.scalars(
        scoped(
            select(Verification).order_by(Verification.scheduled_for.desc()),
            Verification,
            principal,
        )
    )
    return [_verification_out(row) for row in rows]


@router.post(
    "/verifications/{verification_id}/conclude",
    response_model=VerificationOut,
    summary="Fecha uma verificação",
)
def conclude_verification(
    verification_id: str,
    principal: Principal = Depends(require(rbac.DIAGNOSIS_REVIEW)),
    session: Session = Depends(get_session),
) -> VerificationOut:
    """Compara antes e depois e conclui.

    Amostra insuficiente vira ``INCONCLUSIVE``, nunca ``UNCHANGED``: "não mudou"
    é um resultado, "não sei" é a ausência dele, e confundir os dois inventaria
    eficácia onde não há medida.
    """
    row = get_scoped(session, Verification, verification_id, principal)
    verification_service.conclude(session, row)
    session.commit()
    return _verification_out(row)


def _product_out(row: Product) -> ProductOut:
    return ProductOut(
        id=row.id,
        status=str(row.status),
        name=row.name,
        manufacturer=row.manufacturer,
        active_ingredient=row.active_ingredient,
        registration_number=row.registration_number,
        allowed_crops=row.allowed_crops,
        authorized_targets=row.authorized_targets,
        default_rate_l_ha=row.default_rate_l_ha,
        min_rate_l_ha=row.min_rate_l_ha,
        max_rate_l_ha=row.max_rate_l_ha,
        reentry_interval_h=row.reentry_interval_h,
        preharvest_interval_days=row.preharvest_interval_days,
        max_wind_ms=row.max_wind_ms,
    )


def _tank_out(row: Tank) -> TankOut:
    return TankOut(
        id=row.id,
        device_id=row.device_id,
        index=row.index,
        label=row.label,
        capacity_l=row.capacity_l,
        current_level_l=row.current_level_l,
        status=str(row.status),
        loaded_product_id=row.loaded_product_id,
        loaded_batch_id=row.loaded_batch_id,
        loaded_at=row.loaded_at,
    )


def _application_out(row: Application) -> ApplicationOut:
    return ApplicationOut(
        id=row.id,
        mission_id=row.mission_id,
        device_id=row.device_id,
        field_id=row.field_id,
        zone_id=row.zone_id,
        product_id=row.product_id,
        state=row.state,
        started_at=row.started_at,
        stopped_at=row.stopped_at,
        amount_used_l=row.amount_used_l,
        area_ha=row.area_ha,
        mean_rate_l_ha=row.mean_rate_l_ha,
        outside_polygon_points=row.outside_polygon_points,
        verified=row.verified,
    )


def _verification_out(row: Verification) -> VerificationOut:
    return VerificationOut(
        id=row.id,
        application_id=row.application_id,
        field_id=row.field_id,
        zone_id=row.zone_id,
        scheduled_for=row.scheduled_for,
        before_ratio=row.before_ratio,
        after_ratio=row.after_ratio,
        before_sample=row.before_sample,
        after_sample=row.after_sample,
        effectiveness=row.effectiveness,
        conclusion=row.conclusion,
        notes=row.notes,
    )
