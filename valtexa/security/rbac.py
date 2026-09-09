"""Permissões por papel.

O modelo é de capacidades nomeadas, não de hierarquia numérica. Um ``OWNER`` não
"vale mais" que um ``AGRONOMIST``: eles podem coisas diferentes. É o que permite
a regra que o produto exige — **só o agrônomo confirma um diagnóstico e aprova
uma receita** — sem que o dono da fazenda contorne isso por ser o dono.

A tabela abaixo é a fonte única. Nenhuma rota decide permissão por conta
própria; todas passam por :func:`can` através de :func:`valtexa.api.deps.require`.
"""

from __future__ import annotations

from valtexa.models.enums import Role

# --- catálogo de capacidades ------------------------------------------------
TENANT_READ = "tenant:read"
TENANT_MANAGE = "tenant:manage"
USER_MANAGE = "user:manage"

FARM_READ = "farm:read"
FARM_MANAGE = "farm:manage"

DEVICE_READ = "device:read"
DEVICE_PROVISION = "device:provision"
DEVICE_MANAGE = "device:manage"

MISSION_READ = "mission:read"
MISSION_CREATE = "mission:create"
MISSION_DISPATCH = "mission:dispatch"
MISSION_ABORT = "mission:abort"
MISSION_APPROVE_APPLICATION = "mission:approve_application"
"""Assinar a autorização de uma pulverização. Reservado ao agrônomo.

É a capacidade mais sensível da plataforma: é o ponto exato em que uma
recomendação de software vira produto químico no ar. Nenhum papel automático,
nenhuma integração e nenhuma IA a possui.
"""

DIAGNOSIS_READ = "diagnosis:read"
DIAGNOSIS_REVIEW = "diagnosis:review"

DECISION_READ = "decision:read"

PRODUCT_READ = "product:read"
PRODUCT_MANAGE = "product:manage"
TANK_LOAD = "tank:load"

AUDIT_READ = "audit:read"

ALL_CAPABILITIES = frozenset(
    {
        TENANT_READ,
        TENANT_MANAGE,
        USER_MANAGE,
        FARM_READ,
        FARM_MANAGE,
        DEVICE_READ,
        DEVICE_PROVISION,
        DEVICE_MANAGE,
        MISSION_READ,
        MISSION_CREATE,
        MISSION_DISPATCH,
        MISSION_ABORT,
        MISSION_APPROVE_APPLICATION,
        DIAGNOSIS_READ,
        DIAGNOSIS_REVIEW,
        DECISION_READ,
        PRODUCT_READ,
        PRODUCT_MANAGE,
        TANK_LOAD,
        AUDIT_READ,
    }
)

_READ_ONLY = frozenset(
    {TENANT_READ, FARM_READ, DEVICE_READ, MISSION_READ, DIAGNOSIS_READ, DECISION_READ, PRODUCT_READ}
)

ROLE_CAPABILITIES: dict[Role, frozenset[str]] = {
    # O dono administra a organização e opera, mas não assina receita
    # agronômica: essa responsabilidade é técnica e tem nome.
    Role.OWNER: _READ_ONLY
    | {
        TENANT_MANAGE,
        USER_MANAGE,
        FARM_MANAGE,
        DEVICE_PROVISION,
        DEVICE_MANAGE,
        MISSION_CREATE,
        MISSION_DISPATCH,
        MISSION_ABORT,
        PRODUCT_MANAGE,
        TANK_LOAD,
        AUDIT_READ,
    },
    Role.ADMIN: _READ_ONLY
    | {
        USER_MANAGE,
        FARM_MANAGE,
        DEVICE_PROVISION,
        DEVICE_MANAGE,
        MISSION_CREATE,
        MISSION_DISPATCH,
        MISSION_ABORT,
        PRODUCT_MANAGE,
        TANK_LOAD,
        AUDIT_READ,
    },
    Role.AGRONOMIST: _READ_ONLY
    | {
        DIAGNOSIS_REVIEW,
        MISSION_CREATE,
        MISSION_APPROVE_APPLICATION,
        MISSION_ABORT,
        PRODUCT_MANAGE,
    },
    # O operador conduz a frota e pode sempre abortar — parar nunca depende de
    # permissão especial. Criar e aprovar aplicação, não.
    Role.OPERATOR: _READ_ONLY | {MISSION_CREATE, MISSION_DISPATCH, MISSION_ABORT, TANK_LOAD},
    Role.TECHNICIAN: _READ_ONLY | {DEVICE_PROVISION, DEVICE_MANAGE, MISSION_ABORT},
    Role.AUDITOR: _READ_ONLY | {AUDIT_READ},
    Role.VIEWER: _READ_ONLY,
}


def can(role: Role, capability: str) -> bool:
    """Se o papel possui a capacidade."""
    if capability not in ALL_CAPABILITIES:
        raise ValueError(f"Capacidade desconhecida: {capability!r}")
    return capability in ROLE_CAPABILITIES.get(role, frozenset())


def capabilities_of(role: Role) -> frozenset[str]:
    """As capacidades do papel — o frontend usa isto para esconder o que não cabe."""
    return ROLE_CAPABILITIES.get(role, frozenset())
