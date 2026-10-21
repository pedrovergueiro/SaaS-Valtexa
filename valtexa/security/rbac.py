"""Permissões por papel.

O modelo é de capacidades nomeadas, não de hierarquia numérica. Um ``OWNER`` não
"vale mais" que um ``AGRONOMIST``: eles podem coisas diferentes. É o que permite
a regra que o produto exige — **só o agrônomo confirma um diagnóstico e aprova
uma receita** — sem que o dono da fazenda contorne isso por ser o dono.

A tabela abaixo é a fonte única. Nenhuma rota decide permissão por conta
própria; todas passam por :func:`can` através de :func:`valtexa.api.deps.require`.
"""

from __future__ import annotations

from valtexa.models.enums import PlatformRole, Role

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

COLLECTION_READ = "collection:read"
COLLECTION_MANAGE = "collection:manage"
"""Criar coleta, subir arquivo, publicar resultado.

É capacidade de equipe ValTexa, não de cliente. Quem importa uma coleta está
declarando de onde vieram aquelas imagens, e essa declaração precisa ter dono.
"""

DATASET_READ = "dataset:read"
DATASET_MANAGE = "dataset:manage"

AUDIT_READ = "audit:read"

PARECER_GENERATE = "parecer:generate"
"""Pedir ao cérebro agronômico um parecer de um caso. Ler é ``diagnosis:read``; revisar é
``diagnosis:review`` (o agrônomo). Nenhum dos três autoriza aplicação nem cria missão."""

KNOWLEDGE_MANAGE = "knowledge:manage"
"""Ingerir e verificar fonte de conhecimento **do cliente** (histórico da propriedade, bula
que o agrônomo conferiu). As fontes da plataforma são ``platform:knowledge:manage``."""

PLANEJAMENTO_GENERATE = "planejamento:generate"
"""Pedir ao cérebro um plano de apoio (fitossanitário, robótico, de insumos). Ler é
``decision:read``. Revisar depende do tipo: fitossanitário ``diagnosis:review`` (agrônomo),
robótico ``mission:create``, insumos ``product:manage``. Nenhum dos três cria missão, aprova
prescrição ou aplicação, nem muda limiar de modelo."""

SUPPORT_TICKET = "support:ticket"
"""Abrir chamado, comentar, fechar e reabrir (Parte 6, seção 49). Ler os chamados do
cliente é ``tenant:read``: todo mundo do cliente acompanha."""

ALL_CAPABILITIES = frozenset(
    {
        PARECER_GENERATE,
        PLANEJAMENTO_GENERATE,
        KNOWLEDGE_MANAGE,
        SUPPORT_TICKET,
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
        COLLECTION_READ,
        COLLECTION_MANAGE,
        DATASET_READ,
        DATASET_MANAGE,
        AUDIT_READ,
    }
)

_READ_ONLY = frozenset(
    {
        TENANT_READ,
        FARM_READ,
        DEVICE_READ,
        MISSION_READ,
        DIAGNOSIS_READ,
        DECISION_READ,
        PRODUCT_READ,
        COLLECTION_READ,
    }
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
        SUPPORT_TICKET,
        PARECER_GENERATE,
        KNOWLEDGE_MANAGE,
        PLANEJAMENTO_GENERATE,
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
        SUPPORT_TICKET,
        PARECER_GENERATE,
        KNOWLEDGE_MANAGE,
        PLANEJAMENTO_GENERATE,
    },
    Role.AGRONOMIST: _READ_ONLY
    | {
        DATASET_READ,
        DIAGNOSIS_REVIEW,
        MISSION_CREATE,
        MISSION_APPROVE_APPLICATION,
        MISSION_ABORT,
        PRODUCT_MANAGE,
        SUPPORT_TICKET,
        PARECER_GENERATE,
        KNOWLEDGE_MANAGE,
        PLANEJAMENTO_GENERATE,
    },
    # O operador conduz a frota e pode sempre abortar — parar nunca depende de
    # permissão especial. Criar e aprovar aplicação, não.
    Role.OPERATOR: _READ_ONLY
    | {MISSION_CREATE, MISSION_DISPATCH, MISSION_ABORT, TANK_LOAD, SUPPORT_TICKET,
       PLANEJAMENTO_GENERATE},
    Role.TECHNICIAN: _READ_ONLY
    | {DEVICE_PROVISION, DEVICE_MANAGE, MISSION_ABORT, SUPPORT_TICKET},
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


# ---------------------------------------------------------------------------
# Equipe da ValTexa (brief, seção 28)
# ---------------------------------------------------------------------------
#
# O papel de cliente diz o que alguém pode **na fazenda dele**; o papel de
# plataforma diz o que alguém da ValTexa pode **na plataforma**. São tabelas
# separadas e nenhuma herda da outra: nenhum ``OWNER``, por mais dono que seja,
# importa coleta; e nenhum papel de plataforma lê lavoura de cliente sem abrir
# uma sessão de suporte (ver :data:`SUPPORT_READ_CAPABILITIES`).

PLATFORM_TENANT_READ = "platform:tenant:read"
"""Listar clientes e ver o cadastro (sem dado agronômico)."""

PLATFORM_TENANT_MANAGE = "platform:tenant:manage"
"""Criar, editar, ativar e desativar cliente; registrar consentimento por contrato."""

PLATFORM_PLAN_READ = "platform:plan:read"
PLATFORM_PLAN_MANAGE = "platform:plan:manage"
"""Catálogo de planos e a assinatura de cada cliente."""

PLATFORM_USAGE_READ = "platform:usage:read"

PLATFORM_SUPPORT_SESSION = "platform:support:session"
"""Entrar como cliente, em modo leitura, com motivo e prazo."""

PLATFORM_SUPPORT_ASSIST = "platform:support:assist"
"""Ligar a escrita (modo assistido) dentro de uma sessão de suporte."""

PLATFORM_AUDIT_READ = "platform:audit:read"
"""Ler a auditoria de qualquer cliente e as sessões de suporte de todos."""

PLATFORM_ROLE_MANAGE = "platform:role:manage"
"""Dar e tirar papel de plataforma. Só o superadmin."""

PLATFORM_USER_READ = "platform:user:read"
"""Buscar qualquer conta da plataforma e ver a quais clientes ela pertence."""

PLATFORM_MODEL_READ = "platform:model:read"
"""Catálogo de modelos e versões treinadas."""

PLATFORM_FIELD_OPERATE = "platform:field:operate"
"""Relevo, contorno e planejamento de cobertura feitos pela equipe."""

PLATFORM_MODEL_MANAGE = "platform:model:manage"
"""Registrar versão de modelo, editar e mover no ciclo de vida. Aprovar exige, além
disso, papel IA & Dados ou superadmin e não ser quem registrou (ver model_registry)."""

PLATFORM_MODEL_RELEASE = "platform:model:release"
"""Liberar e revogar um modelo para um cliente."""

PLATFORM_FLEET_READ = "platform:fleet:read"
"""Frota de todos os clientes: estado, versões, saúde (sem lavoura nem imagem)."""

PLATFORM_OTA_MANAGE = "platform:ota:manage"
"""Publicar pacote de atualização (OTA) e destiná-lo a robôs; acompanhar e cancelar."""

PLATFORM_TICKET_READ = "platform:ticket:read"
"""Ver os chamados e incidentes de todos os clientes (sem entrar no cliente)."""

PLATFORM_TICKET_MANAGE = "platform:ticket:manage"
"""Atender chamado (status, prioridade, responsável, comentário interno) e gerir incidente."""

PLATFORM_ROVER_CONTROL = "platform:rover:control"
"""Centro de comando: testar peça, foto, controle remoto, modo autônomo, configuração e
modelo fixado de um Rover. Tudo assinado e auditado."""

PLATFORM_OBSERVABILITY_READ = "platform:observability:read"
"""Observabilidade: saúde dos componentes, métricas da API e da IA, frota, alertas e
``/metrics``. Sem dado agronômico de cliente."""

PLATFORM_ALERT_MANAGE = "platform:alert:manage"
"""Reconhecer alerta e mudar as regras padrão (limite, janela, ligada/desligada)."""

PLATFORM_KNOWLEDGE_MANAGE = "platform:knowledge:manage"
"""Ingerir e verificar as fontes da plataforma (bula, registro MAPA, Embrapa, escala, artigo)
que todo cliente lê. Quem ingere declara origem, versão, licença e verificação."""
PLATFORM_ONLY_CAPABILITIES = frozenset(
    {
        PLATFORM_KNOWLEDGE_MANAGE,
        PLATFORM_OBSERVABILITY_READ,
        PLATFORM_ALERT_MANAGE,
        PLATFORM_TICKET_READ,
        PLATFORM_TICKET_MANAGE,
        PLATFORM_OTA_MANAGE,
        PLATFORM_ROVER_CONTROL,
        PLATFORM_TENANT_READ,
        PLATFORM_TENANT_MANAGE,
        PLATFORM_PLAN_READ,
        PLATFORM_PLAN_MANAGE,
        PLATFORM_USAGE_READ,
        PLATFORM_SUPPORT_SESSION,
        PLATFORM_SUPPORT_ASSIST,
        PLATFORM_AUDIT_READ,
        PLATFORM_ROLE_MANAGE,
        PLATFORM_USER_READ,
        PLATFORM_MODEL_READ,
        PLATFORM_FIELD_OPERATE,
        PLATFORM_MODEL_MANAGE,
        PLATFORM_MODEL_RELEASE,
        PLATFORM_FLEET_READ,
    }
)

PLATFORM_CAPABILITIES = PLATFORM_ONLY_CAPABILITIES | {
    COLLECTION_MANAGE,
    DATASET_MANAGE,
    DATASET_READ,
}
"""Tudo o que só a equipe da ValTexa pode ter. Nenhum papel de cliente tem nada daqui
além de ``dataset:read`` (o agrônomo vê o dataset que ajudou a formar)."""

ALL_CAPABILITIES = ALL_CAPABILITIES | PLATFORM_ONLY_CAPABILITIES

PLATFORM_ROLE_CAPABILITIES: dict[PlatformRole, frozenset[str]] = {
    PlatformRole.SUPERADMIN: frozenset(PLATFORM_CAPABILITIES),
    PlatformRole.SUPORTE: frozenset(
        {
            PLATFORM_TENANT_READ,
            PLATFORM_PLAN_READ,
            PLATFORM_USAGE_READ,
            PLATFORM_SUPPORT_SESSION,
            PLATFORM_SUPPORT_ASSIST,
            PLATFORM_AUDIT_READ,
            PLATFORM_USER_READ,
            PLATFORM_FLEET_READ,
            PLATFORM_TICKET_READ,
            PLATFORM_TICKET_MANAGE,
            PLATFORM_OBSERVABILITY_READ,
        }
    ),
    PlatformRole.IA_DADOS: frozenset(
        {
            PLATFORM_OBSERVABILITY_READ,
            PLATFORM_ALERT_MANAGE,
            PLATFORM_TENANT_READ,
            PLATFORM_MODEL_READ,
            PLATFORM_MODEL_MANAGE,
            PLATFORM_MODEL_RELEASE,
            PLATFORM_FLEET_READ,
            PLATFORM_OTA_MANAGE,
            COLLECTION_MANAGE,
            DATASET_READ,
            DATASET_MANAGE,
            PLATFORM_TICKET_READ,
            PLATFORM_KNOWLEDGE_MANAGE,
        }
    ),
    PlatformRole.OPERACOES: frozenset(
        {
            PLATFORM_OBSERVABILITY_READ,
            PLATFORM_ALERT_MANAGE,
            PLATFORM_TICKET_READ,
            PLATFORM_TENANT_READ,
            PLATFORM_FIELD_OPERATE,
            PLATFORM_MODEL_READ,
            PLATFORM_FLEET_READ,
            PLATFORM_OTA_MANAGE,
            PLATFORM_ROVER_CONTROL,
        }
    ),
    # Comercial cuida de contrato e plano; não vê lavoura, imagem nem dataset.
    PlatformRole.COMERCIAL: frozenset(
        {
            PLATFORM_TENANT_READ,
            PLATFORM_TENANT_MANAGE,
            PLATFORM_PLAN_READ,
            PLATFORM_PLAN_MANAGE,
            PLATFORM_USAGE_READ,
        }
    ),
}


def platform_capabilities_of(platform_role: PlatformRole | None) -> frozenset[str]:
    """As capacidades de um papel de plataforma; vazio para quem não é da equipe."""
    if platform_role is None:
        return frozenset()
    return PLATFORM_ROLE_CAPABILITIES.get(platform_role, frozenset())


def platform_can(platform_role: PlatformRole | None, capability: str) -> bool:
    if capability not in ALL_CAPABILITIES:
        raise ValueError(f"Capacidade desconhecida: {capability!r}")
    return capability in platform_capabilities_of(platform_role)


def capabilities_for(
    role: Role | None,
    *,
    platform_role: PlatformRole | None = None,
    is_platform_admin: bool = False,
) -> frozenset[str]:
    """As capacidades efetivas de uma pessoa: o papel no cliente mais o de plataforma.

    ``is_platform_admin`` é o nome antigo e vale como ``superadmin``; fica para
    quem ainda chama assim.
    """
    efetivas = capabilities_of(role) if role is not None else frozenset()
    if platform_role is None and is_platform_admin:
        platform_role = PlatformRole.SUPERADMIN
    return efetivas | platform_capabilities_of(platform_role)


# ---------------------------------------------------------------------------
# Sessão de suporte ("entrar como cliente", brief seção 29)
# ---------------------------------------------------------------------------

SUPPORT_READ_CAPABILITIES = _READ_ONLY | {AUDIT_READ}
"""O que a equipe pode dentro de um cliente em modo **leitura** (o padrão).

Inclui ler a auditoria: é nela que se investiga "o que aconteceu com a missão
de ontem". Nenhuma escrita — e a dependência de autenticação recusa qualquer
método que não seja de leitura, mesmo em rota que não exija capacidade.
"""

SUPPORT_ASSISTED_ROLE = Role.ADMIN
"""Em modo **assistido** a equipe age com o papel de gestor do cliente.

Não é ``OWNER`` (não mexe em cadastro, plano ou dono) e não é ``AGRONOMIST``:
aprovar aplicação continua exclusivo do agrônomo do cliente, com nome e papel,
também quando quem está ajudando é a ValTexa.
"""
