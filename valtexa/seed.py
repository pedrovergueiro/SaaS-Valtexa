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

# Contorno traçado sobre a foto aérea de uma lavoura de café de 5 alqueires
# mineiros (24,2 ha), no Sul de Minas. O formato é o da propriedade real — o
# polígono irregular com a mata entrando pelo leste, não um retângulo.
#
# A ÂNCORA é aproximada. O desenho veio da foto, que não é georreferenciada;
# as coordenadas põem esse desenho numa região de café perto de Pouso Alegre,
# para o mapa de satélite do console mostrar cafezal de verdade. Mover para a
# propriedade exata é trocar LAT0/LON0 — o formato e a área não mudam.
#
# 726 m no sentido leste-oeste por 571 m no norte-sul.
DEMO_FIELD_BOUNDARY = [
    [-45.864054, -21.902006],
    [-45.861603, -21.901326],
    [-45.859179, -21.903083],
    [-45.860778, -21.904279],
    [-45.860855, -21.904854],
    [-45.860314, -21.906218],
    [-45.862996, -21.906457],
    [-45.866220, -21.903777],
]

# O bloco norte, acima do carreador que corta a lavoura na foto.
DEMO_ZONE_BOUNDARY = [
    [-45.863600, -21.902300],
    [-45.861400, -21.901600],
    [-45.859800, -21.903000],
    [-45.862200, -21.903600],
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
    Garante também o catálogo inicial do Model Registry, sem o qual nenhum talhão
    da demonstração teria modelo (o start da API faz o mesmo).
    """
    from valtexa.services import model_registry

    model_registry.sincronizar_catalogo(session)
    existing = session.scalars(select(Tenant).where(Tenant.slug == DEMO_TENANT_SLUG)).first()
    if existing is not None:
        # Idempotente inclui **completar** o que falta: um banco de demonstração
        # criado antes de um papel novo existir continuaria sem ele, e a conta
        # que a documentação manda usar não entraria.
        _ensure_users(session, existing, admin_password)
        return _summary(session, existing)

    tenant = Tenant(name="Fazenda Demonstração", slug=DEMO_TENANT_SLUG)
    session.add(tenant)
    session.flush()

    _ensure_users(session, tenant, admin_password)

    farm = Farm(
        tenant_id=tenant.id,
        name="Sítio Boa Vista",
        timezone="America/Sao_Paulo",
        center_lat=-21.9040,
        center_lon=-45.8620,
        # A base fica na beira do carreador, no canto sul do talhão.
        base_lat=-21.9068,
        base_lon=-45.8630,
        area_ha=24.2,
    )
    session.add(farm)
    session.flush()

    field_row = Field(
        tenant_id=tenant.id,
        farm_id=farm.id,
        name="Talhão A — Café",
        crop="coffee",
        variety="Catuaí Vermelho IAC 144",
        crop_stage="Granação",
        # Café é perene: a lavoura da foto tem porte de lavoura formada.
        planted_on=date.today() - timedelta(days=5 * 365),
        row_spacing_m=3.5,
        boundary=DEMO_FIELD_BOUNDARY,
        area_ha=round(geo.area_ha(DEMO_FIELD_BOUNDARY), 4),
    )
    session.add(field_row)
    session.flush()

    zone = Zone(
        tenant_id=tenant.id,
        field_id=field_row.id,
        name="Bloco Norte",
        boundary=DEMO_ZONE_BOUNDARY,
        area_ha=round(geo.area_ha(DEMO_ZONE_BOUNDARY), 4),
    )
    session.add(zone)

    product = Product(
        tenant_id=tenant.id,
        name="Fungicida Demo Triazol + Estrobilurina",
        manufacturer="Fabricante Exemplo",
        active_ingredient="tebuconazol + azoxistrobina",
        registration_number="DEMO-00000",
        allowed_crops=["coffee"],
        # Os alvos são as classes que o coffee-foliar reconhece. Bicho-mineiro
        # fica de fora de propósito: é praga, não doença, e fungicida não a
        # controla — autorizar aqui seria a receita errada saindo do sistema.
        authorized_targets=["Rust", "Cercospora_Leaf_Spot", "Phoma_Leaf_Spot"],
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


# O último é da **equipe da ValTexa**, não do cliente: é quem importa coleta e
# mexe em dataset. A associação ao tenant existe só para ele conseguir trabalhar
# dentro deste cliente **como membro** (é a conta de demonstração e dos testes);
# o papel de plataforma dele é ``superadmin`` (``is_platform_admin=True``). A
# equipe de verdade não tem associação: entra por sessão de suporte.
DEMO_USERS: dict[str, tuple[Role, str, bool]] = {
    "admin@valtexa.dev": (Role.ADMIN, "Administrador da Demo", False),
    "agronomo@valtexa.dev": (Role.AGRONOMIST, "Agrônomo da Demo", False),
    "operador@valtexa.dev": (Role.OPERATOR, "Operador da Demo", False),
    "equipe@valtexa.dev": (Role.ADMIN, "Equipe ValTexa", True),
}


def _ensure_users(session: Session, tenant: Tenant, password: str) -> None:
    """Garante os usuários de demonstração e a associação deles ao cliente.

    Não mexe em quem já existe: senha e papel de uma conta em uso não são
    sobrescritos por um seed.
    """
    for email, (role, full_name, is_platform_admin) in DEMO_USERS.items():
        user = session.scalars(select(User).where(User.email == email)).first()
        if user is None:
            user = User(
                email=email,
                full_name=full_name,
                password_hash=hash_password(password),
                is_platform_admin=is_platform_admin,
            )
            session.add(user)
            session.flush()
        ja_associado = session.scalars(
            select(Membership).where(
                Membership.tenant_id == tenant.id, Membership.user_id == user.id
            )
        ).first()
        if ja_associado is None:
            session.add(Membership(tenant_id=tenant.id, user_id=user.id, role=role))


# ---------------------------------------------------------------------------
# A equipe da ValTexa
# ---------------------------------------------------------------------------

PLATFORM_TEAM: dict[str, str] = {
    "pedrol.vergueiro@gmail.com": "Pedro Vergueiro",
    "socio@valtexa.com.br": "Sócio ValTexa",
}
"""As contas de quem opera a plataforma, não de quem usa uma fazenda.

Nascem ``superadmin`` (``platform_role``) e **não têm associação a cliente
nenhum** — quem administra a ValTexa não é membro de uma fazenda. Para ver ou agir
nos dados de um cliente abre-se uma sessão de suporte, com motivo e prazo; toda
ação fica na auditoria com o nome de quem a fez e sob qual cliente.

O endereço do sócio é um lugar reservado até alguém dizer qual é o de verdade;
trocá-lo é editar esta linha e rodar o seed de novo, que não sobrescreve quem já
existe.
"""


def seed_platform_team(session: Session, *, password: str) -> list[str]:
    """Garante as contas da equipe da ValTexa. Devolve as que criou agora.

    Idempotente e conservador: **não** mexe em conta que já existe — nem senha,
    nem nome, nem a marca de administrador. Um seed que roda no start não pode
    rebaixar nem reabrir uma conta em uso.

    Dá ``superadmin`` (``is_platform_admin``) a quem está na lista e ainda não
    tem papel de plataforma — nunca rebaixa um papel já dado. Esse é o único
    campo que ele atualiza, e é de propósito: é o que conserta uma conta criada
    antes de a pessoa entrar para a equipe.
    """
    criadas: list[str] = []
    for email, nome in PLATFORM_TEAM.items():
        user = session.scalars(select(User).where(User.email == email)).first()
        if user is None:
            session.add(
                User(
                    email=email,
                    full_name=nome,
                    password_hash=hash_password(password),
                    is_platform_admin=True,
                )
            )
            criadas.append(email)
        elif not user.is_platform_admin:
            user.is_platform_admin = True
    session.commit()
    if criadas:
        logger.info("Equipe ValTexa criada: %s", ", ".join(criadas))
    return criadas


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
