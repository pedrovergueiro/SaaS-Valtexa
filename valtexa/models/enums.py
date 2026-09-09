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


class DeviceKind(StrEnum):
    ROVER = "rover"
    DRONE = "drone"
    DOCK = "dock"
    SENSOR = "sensor"
    GATEWAY = "gateway"


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


class ActorType(StrEnum):
    USER = "user"
    DEVICE = "device"
    SYSTEM = "system"


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
