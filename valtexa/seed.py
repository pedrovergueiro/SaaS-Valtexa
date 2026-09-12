"""Carga inicial: catálogo de hardware e, opcionalmente, uma fazenda de exemplo.

O catálogo de modelos é **idempotente e sempre aplicado** no start: sem ele
nenhum robô consegue se provisionar. A fazenda de exemplo é opcional e existe
para o simulador e para uma demonstração ter o que mostrar.
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from valtexa.models import (
    Device,
    DeviceModel,
    Farm,
    Field,
    Membership,
    Product,
    ProductBatch,
    Role,
    Tenant,
    User,
    Zone,
)
from valtexa.security.passwords import hash_password
from valtexa.services import geo
from valtexa.services.hal import REFERENCE_MODELS

logger = logging.getLogger(__name__)

DEMO_TENANT_SLUG = "fazenda-demo"

# Um retângulo de ~304 x 200 m dentro de uma lavoura de milho em Sorriso (MT).
# As coordenadas são de talhão real: no mapa de satélite do console aparece
# lavoura, com as linhas de plantio e a estrada de terra — e não um bairro.
DEMO_FIELD_BOUNDARY = [
    [-55.9089, -12.7231],
    [-55.9061, -12.7231],
    [-55.9061, -12.7249],
    [-55.9089, -12.7249],
]
DEMO_ZONE_BOUNDARY = [
    [-55.9084, -12.7236],
    [-55.9071, -12.7236],
    [-55.9071, -12.7245],
    [-55.9084, -12.7245],
]


def sync_device_models(session: Session) -> int:
    """Garante que o catálogo de hardware existe. Devolve quantos foram criados.

    Idempotente por ``code``: rodar no start de todo processo é seguro, e é o
    que garante que um deploy novo já aceite o provisionamento de um robô.
    """
    created = 0
    for spec in REFERENCE_MODELS:
        existing = session.scalars(
            select(DeviceModel).where(DeviceModel.code == spec["code"])
        ).first()
        if existing is None:
            session.add(DeviceModel(**spec))
            created += 1
        else:
            # Capacidades evoluem com o firmware; o descritor acompanha.
            existing.capabilities = spec["capabilities"]
            existing.name = spec["name"]
    session.commit()
    return created


def seed_demo(session: Session, *, admin_password: str = "valtexa-demo-2026") -> dict:
    """Cria a fazenda de exemplo, com usuários, talhão, zona e produto.

    Idempotente: se o cliente de demonstração já existe, devolve o que há.
    """
    existing = session.scalars(select(Tenant).where(Tenant.slug == DEMO_TENANT_SLUG)).first()
    if existing is not None:
        return _summary(session, existing)

    tenant = Tenant(name="Fazenda Demonstração", slug=DEMO_TENANT_SLUG)
    session.add(tenant)
    session.flush()

    users = {
        "admin@valtexa.dev": (Role.ADMIN, "Administrador da Demo"),
        "agronomo@valtexa.dev": (Role.AGRONOMIST, "Agrônomo da Demo"),
        "operador@valtexa.dev": (Role.OPERATOR, "Operador da Demo"),
    }
    for email, (role, full_name) in users.items():
        user = session.scalars(select(User).where(User.email == email)).first()
        if user is None:
            user = User(
                email=email, full_name=full_name, password_hash=hash_password(admin_password)
            )
            session.add(user)
            session.flush()
        session.add(Membership(tenant_id=tenant.id, user_id=user.id, role=role))

    farm = Farm(
        tenant_id=tenant.id,
        name="Fazenda Santa Rita",
        timezone="America/Cuiaba",
        center_lat=-12.7240,
        center_lon=-55.9075,
        base_lat=-12.7252,
        base_lon=-55.9075,
        area_ha=120.0,
    )
    session.add(farm)
    session.flush()

    field_row = Field(
        tenant_id=tenant.id,
        farm_id=farm.id,
        name="Talhão A — Milho",
        crop="corn",
        variety="Híbrido precoce",
        crop_stage="V8",
        planted_on=date.today() - timedelta(days=55),
        row_spacing_m=0.5,
        boundary=DEMO_FIELD_BOUNDARY,
        area_ha=round(geo.area_ha(DEMO_FIELD_BOUNDARY), 4),
    )
    session.add(field_row)
    session.flush()

    zone = Zone(
        tenant_id=tenant.id,
        field_id=field_row.id,
        name="Zona Norte",
        boundary=DEMO_ZONE_BOUNDARY,
        area_ha=round(geo.area_ha(DEMO_ZONE_BOUNDARY), 4),
    )
    session.add(zone)

    product = Product(
        tenant_id=tenant.id,
        name="Fungicida Demo Triazol",
        manufacturer="Fabricante Exemplo",
        active_ingredient="tebuconazol",
        registration_number="DEMO-00000",
        allowed_crops=["corn"],
        authorized_targets=["Common_Rust", "Blight", "Gray_Leaf_Spot"],
        default_rate_l_ha=0.75,
        min_rate_l_ha=0.5,
        max_rate_l_ha=1.0,
        reentry_interval_h=24.0,
        preharvest_interval_days=30,
        max_wind_ms=6.0,
    )
    session.add(product)
    session.flush()

    session.add(
        ProductBatch(
            tenant_id=tenant.id,
            product_id=product.id,
            code="LOTE-DEMO-01",
            expires_on=date.today() + timedelta(days=365),
            quantity_l=200.0,
            received_on=date.today() - timedelta(days=10),
        )
    )
    session.commit()
    logger.info("Cliente de demonstração criado: %s", DEMO_TENANT_SLUG)
    return _summary(session, tenant)


def _summary(session: Session, tenant: Tenant) -> dict:
    farm = session.scalars(select(Farm).where(Farm.tenant_id == tenant.id)).first()
    field_row = session.scalars(select(Field).where(Field.tenant_id == tenant.id)).first()
    zone = session.scalars(select(Zone).where(Zone.tenant_id == tenant.id)).first()
    product = session.scalars(select(Product).where(Product.tenant_id == tenant.id)).first()
    batch = session.scalars(select(ProductBatch).where(ProductBatch.tenant_id == tenant.id)).first()
    devices = list(session.scalars(select(Device).where(Device.tenant_id == tenant.id)))
    return {
        "tenant_id": tenant.id,
        "tenant_slug": tenant.slug,
        "farm_id": farm.id if farm else None,
        "field_id": field_row.id if field_row else None,
        "zone_id": zone.id if zone else None,
        "product_id": product.id if product else None,
        "batch_id": batch.id if batch else None,
        "devices": {device.kind.value: device.id for device in devices},
        "created_at": datetime.now(UTC).isoformat(),
    }
