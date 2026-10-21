"""Vocabulário fechado do domínio.

Todos são ``StrEnum`` para que o valor gravado no banco, o que sai no JSON e o
que aparece num ``SELECT`` cru sejam o mesmo texto legível — um dump do banco
continua auditável sem consultar o código.
"""

from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    """Papéis dentro de um tenant. A ordem da lista é a ordem de privilégio."""

    OWNER = "owner"
    ADMIN = "admin"
    AGRONOMIST = "agronomist"
    """Diagnostica. É o único que pode confirmar um diagnóstico e aprovar receita."""

    OPERATOR = "operator"
    """Opera missões. Pode despachar, pausar e abortar, mas não aprova aplicação."""

    TECHNICIAN = "technician"
    """Cuida do hardware: provisiona, aposenta, atualiza firmware."""

    AUDITOR = "auditor"
    """Lê tudo, inclusive a auditoria. Não escreve nada."""

    VIEWER = "viewer"


class PlatformRole(StrEnum):
    """Papéis da equipe da ValTexa (brief, seção 28). Não existem dentro de cliente.

    Cada um enxerga só o que o trabalho pede — menor privilégio. O mapa de
    capacidades fica em :data:`valtexa.security.rbac.PLATFORM_ROLE_CAPABILITIES`.
    """

    SUPERADMIN = "superadmin"
    """Tudo, inclusive papéis de plataforma, planos e exclusões."""

    SUPORTE = "suporte"
    """Clientes, chamados, diagnóstico; entra como cliente com motivo e prazo."""

    IA_DADOS = "ia_dados"
    """Modelos, coletas, datasets, treinos, saúde da IA."""

    OPERACOES = "operacoes"
    """Frota, missões assistidas, contorno e relevo, logística."""

    COMERCIAL = "comercial"
    """Clientes, contratos, planos e uso — sem dado agronômico."""


class SupportMode(StrEnum):
    """Como a equipe está dentro de um cliente numa sessão de suporte."""

    LEITURA = "leitura"
    """Padrão: só lê. Qualquer escrita é recusada com 403."""

    ASSISTIDO = "assistido"
    """Escrita liberada, ligada explicitamente, com motivo e auditada."""


class SubscriptionStatus(StrEnum):
    TESTE = "teste"
    ATIVA = "ativa"
    SUSPENSA = "suspensa"
    CANCELADA = "cancelada"


class DeviceKind(StrEnum):
    ROVER = "rover"
    DRONE = "drone"
    DOCK = "dock"
    SENSOR = "sensor"
    GATEWAY = "gateway"
    """LEGADO: a base da fazenda, arquivada em 20/10/2026 (cada Rover tem a própria Starlink).
    O valor fica porque o banco pode ter dispositivos com ele; o catálogo de hardware não
    oferece mais nenhum modelo deste tipo (``services/hal.py``)."""


class DeviceStatus(StrEnum):
    UNPROVISIONED = "unprovisioned"
    ACTIVE = "active"
    MAINTENANCE = "maintenance"
    SUSPENDED = "suspended"
    RETIRED = "retired"


class CredentialStatus(StrEnum):
    ACTIVE = "active"
    ROTATING = "rotating"
    """A antiga ainda vale enquanto o robô não confirma a nova. Ver docs/AUTHENTICATION.md."""

    REVOKED = "revoked"


class Connectivity(StrEnum):
    OK = "ok"
    DEGRADED = "degraded"
    OFFLINE = "offline"


class RtkFix(StrEnum):
    NONE = "none"
    SINGLE = "single"
    FLOAT = "float"
    FIXED = "fixed"
    """Único aceitável para aplicação: precisão centimétrica."""


class MissionKind(StrEnum):
    SCOUT = "scout"
    """Rover percorre a lavoura coletando imagem e 3D."""

    SPRAY = "spray"
    """Drone aplica em área autorizada."""

    VERIFY = "verify"
    """Rover volta ao mesmo ponto depois do tratamento."""

    TRANSIT = "transit"


class MissionState(StrEnum):
    """Máquina de estados da missão. As transições válidas estão em
    :data:`valtexa.services.mission_manager.ALLOWED_TRANSITIONS`."""

    DRAFT = "draft"
    PENDING_SAFETY = "pending_safety"
    BLOCKED = "blocked"
    AUTHORIZED = "authorized"
    DISPATCHED = "dispatched"
    RUNNING = "running"
    PAUSED = "paused"
    PAUSED_FOR_RECHARGE = "paused_for_recharge"
    READY_TO_RESUME = "ready_to_resume"
    COMPLETED = "completed"
    ABORTED = "aborted"
    EXPIRED = "expired"


class SegmentState(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    SKIPPED = "skipped"


class EventSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class DetectionSource(StrEnum):
    EDGE = "edge"
    """Rodou no robô. Nunca autoriza nada — só decide o que vale a pena subir."""

    CLOUD_PRIMARY = "cloud_primary"
    CLOUD_SECONDARY = "cloud_secondary"
    HUMAN = "human"


class Agreement(StrEnum):
    AGREE = "agree"
    DISAGREE = "disagree"
    ABSTAIN = "abstain"
    """Ao menos uma das análises ficou abaixo do limiar de confiança."""

    UNAVAILABLE = "unavailable"
    """Só uma análise respondeu. Nunca é suficiente para AI_VALIDATED."""


class DiagnosisStatus(StrEnum):
    PENDING = "pending"
    AI_VALIDATED = "ai_validated"
    """As duas análises concordaram. **Não** é autorização para aplicar."""

    NEEDS_REVIEW = "needs_review"
    INCONCLUSIVE = "inconclusive"
    HUMAN_CONFIRMED = "human_confirmed"
    HUMAN_REJECTED = "human_rejected"


class DecisionOutcome(StrEnum):
    NO_ACTION = "no_action"
    OBSERVE = "observe"
    NEED_MORE_DATA = "need_more_data"
    HUMAN_REVIEW = "human_review"
    APPLICATION_CANDIDATE = "application_candidate"
    """Candidata. Ainda passa pela aprovação do agrônomo e pelo safety engine."""


class SafetyVerdict(StrEnum):
    SAFE_TO_EXECUTE = "safe_to_execute"
    BLOCKED = "blocked"


class SubjectType(StrEnum):
    MISSION = "mission"
    APPLICATION = "application"
    DEVICE = "device"
    DIAGNOSIS = "diagnosis"
    DECISION = "decision"
    OBSERVATION = "observation"
    PRODUCT = "product"
    TANK = "tank"
    USER = "user"
    FIELD = "field"
    VERIFICATION = "verification"
    COLLECTION = "collection"
    COLLECTION_FILE = "collection_file"
    DATASET = "dataset"
    DATASET_VERSION = "dataset_version"
    MODEL_VERSION = "model_version"
    TENANT = "tenant"
    SUPPORT_SESSION = "support_session"
    PLAN = "plan"
    SUBSCRIPTION = "subscription"
    DATA_CONSENT = "data_consent"
    OTA_PACKAGE = "ota_package"
    SUPPORT_TICKET = "support_ticket"
    INCIDENT = "incident"
    ALERT = "alert"
    ALERT_RULE = "alert_rule"
    PARECER = "parecer"
    FONTE = "fonte"
    PLANEJAMENTO = "planejamento"
    """Documento do repositório de conhecimento (cérebro agronômico)."""


class ActorType(StrEnum):
    """Quem agiu. Separar a IA do resto do sistema é o ponto desta lista.

    ``SYSTEM`` é o relógio: expiração, retenção, fila. ``AI`` é um modelo que
    emitiu juízo sobre uma imagem. As duas coisas não se auditam igual — a
    pergunta "o que a IA decidiu sozinha neste talhão?" precisa de resposta, e
    ela não sai de uma trilha em que modelo e cron aparecem com o mesmo nome.
    """

    USER = "user"
    DEVICE = "device"
    SYSTEM = "system"
    AI = "ai"


class ProductStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    EXPIRED = "expired"


class TankStatus(StrEnum):
    EMPTY = "empty"
    LOADED = "loaded"
    SEALED = "sealed"
    FAULT = "fault"


class ApplicationState(StrEnum):
    STARTED = "started"
    COMPLETED = "completed"
    ABORTED = "aborted"


class AssetKind(StrEnum):
    IMAGE = "image"
    THUMBNAIL = "thumbnail"
    POINTCLOUD = "pointcloud"
    MAP = "map"
    LOG = "log"


class EnergyState(StrEnum):
    NORMAL = "normal"
    LOW_BATTERY = "low_battery"
    RETURN_TO_BASE = "return_to_base"
    EMERGENCY_RETURN = "emergency_return"
    LANDED = "landed"


class OfflineAction(StrEnum):
    """O que o robô faz sozinho quando a nuvem some. Ver docs/OFFLINE_MODE.md."""

    CONTINUE = "continue"
    PAUSE = "pause"
    RETURN_TO_BASE = "return_to_base"
    LAND = "land"
    ABORT = "abort"


class VerificationConclusion(StrEnum):
    PENDING = "pending"
    IMPROVED = "improved"
    UNCHANGED = "unchanged"
    WORSENED = "worsened"
    INCONCLUSIVE = "inconclusive"


class CapturePlatform(StrEnum):
    """De onde a imagem foi tirada. Decide qual modelo pode analisá-la.

    O mesmo vocabulário do ``Platform`` de VALTEXA-B (``app/registry.py``). Não é
    detalhe de catalogação: uma foto aérea de dossel e uma foto de folha não
    respondem à mesma pergunta, e mandar uma ao modelo da outra devolve uma das
    classes do modelo errado com confiança alta e nada no resultado denunciando
    o erro. Ver ``VALTEXA-B/MODELS.md``.
    """

    GROUND = "ground"
    """Rover, celular, câmera de mão — a folha ocupa o quadro."""

    AERIAL = "aerial"
    """Drone. Dossel visto de cima, uma planta ocupa poucos pixels."""

    ANY = "any"


class CollectionSource(StrEnum):
    """Quem produziu os arquivos.

    ``DRONE_THIRD_PARTY`` é o MVP: operador terceirizado voa, entrega os
    arquivos, e a ValTexa importa pelo painel. ``DRONE_OWNED`` existe no
    vocabulário para a fase futura e **não tem caminho de ingestão implementado**
    — ver :mod:`valtexa.services.collections`.
    """

    DRONE_THIRD_PARTY = "drone_third_party"
    ROVER = "rover"
    HANDHELD = "handheld"
    DRONE_OWNED = "drone_owned"
    """FUTURO. Drone próprio autônomo. Nenhuma coleta é criada com esta origem."""


class CollectionKind(StrEnum):
    """O que veio dentro da coleta."""

    AERIAL_IMAGE = "aerial_image"
    """Quadros brutos de um voo."""

    ORTHOMOSAIC = "orthomosaic"
    """Mosaico já processado pelo operador. Uma imagem grande, georreferenciada."""

    GROUND_IMAGE = "ground_image"
    """Fotos de folha/planta, nível do solo."""

    OTHER = "other"


class CollectionState(StrEnum):
    """Ciclo de vida de uma coleta, do upload ao cliente.

    Só avança. ``FAILED`` é terminal para o lote, não para os arquivos: um
    arquivo com erro não derruba a coleta, ele fica em
    :class:`CollectionFileState.FAILED` e aparece no painel.
    """

    DRAFT = "draft"
    """Criada no painel, ainda recebendo arquivos."""

    UPLOADING = "uploading"
    UPLOAD_COMPLETED = "upload_completed"
    PROCESSING_QUEUED = "processing_queued"
    AI_PROCESSING = "ai_processing"
    RESULTS_GENERATED = "results_generated"
    REVIEW_REQUIRED = "review_required"
    ANALYZED = "analyzed"
    AVAILABLE_TO_CLIENT = "available_to_client"
    FAILED = "failed"
    CANCELLED = "cancelled"


class CollectionFileState(StrEnum):
    """Ciclo de vida de um arquivo dentro da coleta."""

    REGISTERED = "registered"
    """Declarado (nome, tamanho, sha256); nenhum byte recebido ainda."""

    UPLOADING = "uploading"
    STORED = "stored"
    """Bytes completos e conferidos contra o sha256 declarado."""

    PROCESSING = "processing"
    ANALYZED = "analyzed"
    NEEDS_REVIEW = "needs_review"
    NO_MODEL = "no_model"
    """Guardado e catalogado, sem modelo treinado que saiba respondê-lo.

    Não é erro nem pendência de código: é o estado honesto de uma imagem aérea
    enquanto ``aerial-canopy`` não estiver treinado. Ver ``VALTEXA-B/MODELS.md``.
    """

    FAILED = "failed"
    REJECTED = "rejected"
    """Recusado na validação: tipo não suportado, sha256 divergente, vazio."""


class JobKind(StrEnum):
    COLLECTION_INGEST = "collection_ingest"


class JobState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


class DatasetSampleState(StrEnum):
    """Situação de uma amostra dentro do dataset proprietário."""

    CANDIDATE = "candidate"
    """Anotada por um agrônomo, ainda não congelada em nenhuma versão."""

    INCLUDED = "included"
    """Já faz parte de ao menos uma :class:`DatasetVersion` fechada."""

    EXCLUDED = "excluded"
    """Retirada: rótulo revisto, imagem ruim, duplicata."""


class ModelVersionState(StrEnum):
    """Ciclo de vida de uma versão de modelo no registry (brief, seção 9).

    TREINAMENTO → VALIDAÇÃO → APROVADO → STAGING → PRODUÇÃO → DESCONTINUADO. As
    transições permitidas e quem pode fazê-las estão em
    :mod:`valtexa.services.model_registry`; toda transição fica na auditoria.
    """

    TREINAMENTO = "treinamento"
    VALIDACAO = "validacao"
    APROVADO = "aprovado"
    """Métricas conferidas e aprovadas por alguém de IA & Dados que não registrou a versão."""

    STAGING = "staging"
    """Pronta para rodar em paralelo, sem valer para decisão. É como uma versão se prova."""

    PRODUCAO = "producao"
    """A versão que atende. No máximo uma por ``model_key``."""

    DESCONTINUADO = "descontinuado"


class ReleaseScope(StrEnum):
    """Para quais clientes uma versão em PRODUÇÃO pode ser escolhida."""

    TODOS = "todos"
    CLIENTES = "clientes"
    """Só para os clientes com :class:`~valtexa.models.dataset.ModelRelease` ativa."""
