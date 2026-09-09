"""Contrato HTTP da plataforma.

Os modelos de saída são achatados de propósito: o cliente recebe identificadores
e valores, nunca o objeto ORM serializado por reflexão. Assim, adicionar uma
coluna interna não vaza para a API por acidente.

O contrato é o mesmo para o frontend e para os robôs. Quando o SaaS visual for
construído, ele consome exatamente estes esquemas — nenhuma rota nova, nenhuma
regra que só exista na tela.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints

from valtexa.models.enums import (
    ApplicationState,
    Connectivity,
    DecisionOutcome,
    DeviceKind,
    DeviceStatus,
    DiagnosisStatus,
    MissionKind,
    MissionState,
    Role,
    RtkFix,
    SafetyVerdict,
    VerificationConclusion,
)

# ``model_`` é namespace protegido do Pydantic; o domínio usa "modelo" o tempo
# todo, então o namespace fica liberado nos esquemas que precisam.
ALLOW_MODEL_PREFIX = ConfigDict(protected_namespaces=())

Polygon = Annotated[
    list[list[float]],
    Field(
        min_length=3,
        description="Anel [[lon, lat], ...] em WGS84, sem repetir o primeiro ponto no fim.",
    ),
]
Slug = Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9-]{1,62}$")]
Name = Annotated[str, StringConstraints(min_length=1, max_length=160, strip_whitespace=True)]


class Message(BaseModel):
    """Resposta simples de confirmação."""

    detail: str


class ErrorResponse(BaseModel):
    detail: str


# ---------------------------------------------------------------------------
# Autenticação e organização
# ---------------------------------------------------------------------------


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=256)
    tenant: Slug | None = Field(
        default=None,
        description="Cliente a abrir. Opcional quando o usuário pertence a um só.",
    )


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
    tenant_id: str | None
    role: Role | None
    capabilities: list[str]


class MembershipOut(BaseModel):
    tenant_id: str
    tenant_name: str
    tenant_slug: str
    role: Role


class MeResponse(BaseModel):
    id: str
    email: str
    full_name: str
    is_platform_admin: bool
    active_tenant_id: str
    role: Role
    capabilities: list[str]
    memberships: list[MembershipOut]


class TenantCreate(BaseModel):
    name: Name
    slug: Slug
    document: str | None = Field(default=None, max_length=32)


class TenantOut(BaseModel):
    id: str
    name: str
    slug: str
    document: str | None
    is_active: bool
    created_at: datetime


class UserInvite(BaseModel):
    email: EmailStr
    full_name: Name
    password: str = Field(min_length=8, max_length=256)
    role: Role


class UserOut(BaseModel):
    id: str
    email: str
    full_name: str
    role: Role
    is_active: bool


# ---------------------------------------------------------------------------
# Geografia
# ---------------------------------------------------------------------------


class FarmCreate(BaseModel):
    name: Name
    center_lat: float = Field(ge=-90, le=90)
    center_lon: float = Field(ge=-180, le=180)
    base_lat: float | None = Field(default=None, ge=-90, le=90)
    base_lon: float | None = Field(default=None, ge=-180, le=180)
    timezone: str = "America/Sao_Paulo"
    area_ha: float | None = Field(default=None, gt=0)


class FarmOut(BaseModel):
    id: str
    name: str
    timezone: str
    center_lat: float
    center_lon: float
    base_lat: float | None
    base_lon: float | None
    area_ha: float | None
    fields: int = Field(description="Quantos talhões cadastrados.")


class FieldCreate(BaseModel):
    name: Name
    crop: Annotated[str, StringConstraints(min_length=2, max_length=64)]
    boundary: Polygon
    variety: str | None = None
    crop_stage: str | None = None
    planted_on: date | None = None
    row_spacing_m: float | None = Field(default=None, gt=0)


class FieldOut(BaseModel):
    id: str
    farm_id: str
    name: str
    crop: str
    variety: str | None
    crop_stage: str | None
    planted_on: date | None
    row_spacing_m: float | None
    area_ha: float | None
    boundary: list[list[float]]


class ZoneCreate(BaseModel):
    name: Name
    boundary: Polygon


class ZoneOut(BaseModel):
    id: str
    field_id: str
    name: str
    area_ha: float | None
    boundary: list[list[float]]


# ---------------------------------------------------------------------------
# Frota
# ---------------------------------------------------------------------------


class DeviceModelOut(BaseModel):
    id: str
    code: str
    kind: DeviceKind
    name: str
    manufacturer: str | None
    protocol_version: str
    capabilities: dict


class ProvisioningTokenCreate(BaseModel):
    device_model_code: str
    farm_id: str | None = None
    serial_number: str | None = Field(
        default=None,
        description="Amarra o convite a um número de série. Recomendado em produção.",
    )
    ttl_hours: int = Field(default=72, ge=1, le=720)


class ProvisioningTokenOut(BaseModel):
    """O token em claro aparece **uma única vez**, nesta resposta."""

    id: str
    token: str
    expires_at: datetime
    device_model_code: str
    serial_number: str | None


class DeviceProvisionRequest(BaseModel):
    """O que o robô envia no primeiro contato."""

    model_config = ALLOW_MODEL_PREFIX

    provisioning_token: str
    serial_number: Annotated[str, StringConstraints(min_length=3, max_length=64)]
    public_key: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")] = Field(
        description="Ed25519 bruta em hexadecimal, gerada dentro do robô."
    )
    name: str | None = None
    firmware_version: str | None = None
    hardware_version: str | None = None
    protocol_version: str = "1.0"


class DeviceProvisionResponse(BaseModel):
    """O que o robô guarda para o resto da vida."""

    device_id: str
    tenant_id: str
    key_id: str
    platform_public_key: str = Field(
        description="Usada pelo robô para verificar as missões que a nuvem assina."
    )
    protocol_version: str
    server_time: datetime


class DeviceOut(BaseModel):
    model_config = ALLOW_MODEL_PREFIX

    id: str
    serial_number: str
    name: str
    kind: DeviceKind
    status: DeviceStatus
    model_code: str
    farm_id: str | None
    firmware_version: str | None
    protocol_version: str | None
    connectivity: Connectivity
    battery_percent: float | None
    last_seen_at: datetime | None
    last_lat: float | None
    last_lon: float | None
    active_mission_id: str | None
    capabilities: dict


class DeviceStatusUpdate(BaseModel):
    status: DeviceStatus
    reason: str | None = None


# ---------------------------------------------------------------------------
# Protocolo do dispositivo
# ---------------------------------------------------------------------------


class TelemetryIn(BaseModel):
    """Uma amostra. Os campos são todos opcionais salvo a sequência."""

    sequence_number: int = Field(ge=0)
    recorded_at: datetime | None = None
    mission_id: str | None = None
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)
    alt_m: float | None = None
    heading_deg: float | None = None
    speed_ms: float | None = None
    rtk_fix: RtkFix | None = None
    hdop: float | None = None
    battery_percent: float | None = Field(default=None, ge=0, le=100)
    battery_voltage_v: float | None = None
    battery_current_a: float | None = None
    temperature_c: float | None = None
    energy_state: str | None = None
    mission_state: str | None = None
    link_quality: float | None = None
    motors: dict = Field(default_factory=dict)
    sensors: dict = Field(default_factory=dict)
    faults: list[Any] = Field(default_factory=list)


class DeviceEventIn(BaseModel):
    sequence_number: int = Field(ge=0)
    type: Annotated[str, StringConstraints(min_length=2, max_length=64)]
    occurred_at: datetime | None = None
    severity: str = "info"
    mission_id: str | None = None
    payload: dict = Field(default_factory=dict)


class TelemetryBatch(BaseModel):
    sync_id: str | None = Field(
        default=None, description="Identificador do lote, para rastrear a sincronização offline."
    )
    samples: list[TelemetryIn] = Field(min_length=1)


class EventBatch(BaseModel):
    sync_id: str | None = None
    events: list[DeviceEventIn] = Field(min_length=1)


class SyncBatch(BaseModel):
    """Descarga de um robô que ficou offline."""

    sync_id: str
    samples: list[TelemetryIn] = Field(default_factory=list)
    events: list[DeviceEventIn] = Field(default_factory=list)


class IngestOut(BaseModel):
    accepted: int
    duplicated: int = Field(description="Já conhecidos. Reenvio é esperado, não é erro.")
    rejected: int
    errors: list[str] = Field(default_factory=list)


class ObservationIn(BaseModel):
    """Metadados de uma imagem. A imagem vai no campo ``file`` do multipart."""

    sequence_number: int | None = None
    mission_id: str | None = None
    field_id: str
    zone_id: str | None = None
    captured_at: datetime
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    alt_m: float | None = None
    heading_deg: float | None = None
    row_index: int | None = None
    model_input_ok: bool | None = None
    edge_summary: dict = Field(default_factory=dict)


class ObservationOut(BaseModel):
    id: str
    field_id: str
    zone_id: str | None
    mission_id: str | None
    device_id: str
    captured_at: datetime
    lat: float
    lon: float
    image_asset_id: str | None
    diagnosis_id: str | None = None
    diagnosis_status: DiagnosisStatus | None = None
    label: str | None = None
    confidence: float | None = None
    novelty_score: float | None = None


class SignedCommandOut(BaseModel):
    """O envelope assinado que o robô verifica antes de agir."""

    payload: dict
    signature: str
    key_id: str
    algorithm: str


class MissionAck(BaseModel):
    """Confirmação de recebimento pelo robô."""

    mission_id: str
    accepted: bool
    reason: str | None = Field(
        default=None, description="Por que recusou. Obrigatório quando accepted=false."
    )


class SegmentComplete(BaseModel):
    segment_index: int = Field(ge=0)
    lat: float | None = None
    lon: float | None = None
    battery_percent: float | None = None


class MissionPause(BaseModel):
    reason: str = Field(max_length=120)
    lat: float | None = None
    lon: float | None = None
    battery_percent: float | None = None


# ---------------------------------------------------------------------------
# Missões
# ---------------------------------------------------------------------------


class MissionCreate(BaseModel):
    kind: MissionKind
    field_id: str
    device_id: str
    zone_id: str | None = None
    target_polygon: Polygon | None = Field(
        default=None, description="Sem polígono, a missão cobre o talhão inteiro."
    )
    plan: dict = Field(default_factory=dict)
    # Só para pulverização:
    product_id: str | None = None
    product_batch_id: str | None = None
    tank_id: str | None = None
    authorized_rate_l_ha: float | None = Field(default=None, gt=0)
    authorized_quantity_l: float | None = Field(default=None, gt=0)
    decision_id: str | None = None


class MissionSegmentOut(BaseModel):
    index: int
    state: str
    path: list[list[float]]
    estimated_energy_percent: float | None


class MissionOut(BaseModel):
    id: str
    kind: MissionKind
    state: MissionState
    farm_id: str
    field_id: str
    zone_id: str | None
    device_id: str
    target_polygon: list[list[float]]
    plan: dict
    product_id: str | None
    tank_id: str | None
    authorized_rate_l_ha: float | None
    authorized_quantity_l: float | None
    created_by: str | None
    approved_by: str | None
    authorized_at: datetime | None
    expires_at: datetime | None
    safety_status: SafetyVerdict | None
    safety_reason: str | None
    energy_policy: dict
    offline_policy: dict
    segments_total: int
    segments_done: int
    created_at: datetime


class MissionApproval(BaseModel):
    """Assinatura do agrônomo. Sem isto nenhuma pulverização é autorizada."""

    confirm: bool = Field(
        description="Precisa ser verdadeiro. Existe para evitar clique acidental."
    )
    notes: str | None = None


class AbortRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class SafetyCheckOut(BaseModel):
    code: str
    passed: bool
    detail: str


class SafetyEvaluationOut(BaseModel):
    id: str
    subject_type: str
    subject_id: str
    verdict: SafetyVerdict
    blocked_code: str | None
    blocked_reason: str | None
    checks: list[SafetyCheckOut]
    engine_version: str
    created_at: datetime


# ---------------------------------------------------------------------------
# Percepção
# ---------------------------------------------------------------------------


class DetectionOut(BaseModel):
    model_config = ALLOW_MODEL_PREFIX

    id: str
    source: str
    analyzer: str
    model_key: str | None
    label: str | None
    confidence: float | None
    novelty_score: float | None
    abstained: bool
    probabilities: dict
    latency_ms: float | None
    error: str | None


class DiagnosisOut(BaseModel):
    id: str
    observation_id: str
    field_id: str
    zone_id: str | None
    status: DiagnosisStatus
    agreement: str
    label: str | None
    effective_label: str | None
    confidence: float | None
    novelty_score: float | None
    rationale: str | None
    pipeline_version: str
    reviewed_by: str | None
    reviewed_at: datetime | None
    reviewed_label: str | None
    created_at: datetime
    detections: list[DetectionOut] = Field(default_factory=list)


class DiagnosisReview(BaseModel):
    """O veredito do agrônomo."""

    label: Annotated[str, StringConstraints(pattern=r"^[A-Za-z][A-Za-z0-9_]{0,63}$")] = Field(
        description=(
            "A classe correta. Pode ser um nome que ainda não existe no catálogo "
            "do modelo — é assim que uma doença nova entra no dataset próprio."
        ),
        examples=["Gray_Leaf_Spot", "Cigarrinha"],
    )
    confirmed: bool = Field(
        default=True, description="Falso registra que o palpite da máquina estava errado."
    )
    notes: str | None = None


class DecisionOut(BaseModel):
    id: str
    diagnosis_id: str | None
    field_id: str
    zone_id: str | None
    outcome: DecisionOutcome
    reason_code: str
    rationale: str
    rule_version: str
    recommended_product_id: str | None
    recommended_rate_l_ha: float | None
    affected_ratio: float | None
    sample_size: int | None
    mission_id: str | None
    inputs: dict
    created_at: datetime


# ---------------------------------------------------------------------------
# Insumos e aplicação
# ---------------------------------------------------------------------------


class ProductCreate(BaseModel):
    name: Name
    manufacturer: str | None = None
    active_ingredient: str | None = None
    registration_number: str | None = None
    allowed_crops: list[str] = Field(default_factory=list)
    authorized_targets: list[str] = Field(default_factory=list)
    default_rate_l_ha: float | None = Field(default=None, gt=0)
    min_rate_l_ha: float | None = Field(default=None, gt=0)
    max_rate_l_ha: float | None = Field(default=None, gt=0)
    reentry_interval_h: float | None = Field(default=None, ge=0)
    preharvest_interval_days: int | None = Field(default=None, ge=0)
    max_wind_ms: float | None = Field(default=None, gt=0)


class ProductOut(ProductCreate):
    id: str
    status: str


class BatchCreate(BaseModel):
    code: Annotated[str, StringConstraints(min_length=1, max_length=64)]
    expires_on: date | None = None
    quantity_l: float | None = Field(default=None, gt=0)


class BatchOut(BaseModel):
    id: str
    product_id: str
    code: str
    expires_on: date | None
    quantity_l: float | None


class TankCreate(BaseModel):
    device_id: str
    index: int = Field(ge=0)
    capacity_l: float = Field(gt=0)
    label: str | None = None


class TankLoad(BaseModel):
    """Carga de um tanque. É o registro que o safety engine confere."""

    product_id: str
    batch_id: str
    volume_l: float = Field(gt=0)


class TankOut(BaseModel):
    id: str
    device_id: str
    index: int
    label: str | None
    capacity_l: float
    current_level_l: float
    status: str
    loaded_product_id: str | None
    loaded_batch_id: str | None
    loaded_at: datetime | None


class ApplicationStart(BaseModel):
    """Reportado pelo drone quando abre o bico."""

    mission_id: str
    started_at: datetime
    tank_id: str | None = None


class ApplicationStop(BaseModel):
    stopped_at: datetime
    amount_used_l: float = Field(ge=0)
    area_ha: float | None = Field(default=None, ge=0)
    track: list[list[float]] = Field(
        default_factory=list, description="[[lon, lat, vazão], ...] — o mapa de aplicação."
    )
    stop_reason: str | None = None


class ApplicationOut(BaseModel):
    id: str
    mission_id: str
    device_id: str
    field_id: str
    zone_id: str | None
    product_id: str | None
    state: ApplicationState
    started_at: datetime
    stopped_at: datetime | None
    amount_used_l: float | None
    area_ha: float | None
    mean_rate_l_ha: float | None
    outside_polygon_points: int
    verified: bool


class VerificationOut(BaseModel):
    model_config = ALLOW_MODEL_PREFIX

    id: str
    application_id: str
    field_id: str
    zone_id: str | None
    scheduled_for: datetime | None
    before_ratio: float | None
    after_ratio: float | None
    before_sample: int | None
    after_sample: int | None
    effectiveness: float | None
    conclusion: VerificationConclusion
    notes: str | None


# ---------------------------------------------------------------------------
# Gêmeo digital, auditoria e eventos
# ---------------------------------------------------------------------------


class ClassCountOut(BaseModel):
    label: str
    count: int
    ratio: float


class FieldSnapshotOut(BaseModel):
    field_id: str
    field_name: str
    crop: str
    since: datetime
    until: datetime
    observations: int
    diagnosed: int
    needs_review: int
    classes: list[ClassCountOut]


class TimePointOut(BaseModel):
    day: date
    total: int
    counts: dict[str, int]


class AnomalyOut(BaseModel):
    field_id: str
    zone_id: str | None
    label: str
    baseline_ratio: float
    current_ratio: float
    baseline_sample: int
    current_sample: int
    detail: str


class AuditOut(BaseModel):
    model_config = ALLOW_MODEL_PREFIX

    id: str
    at: datetime
    actor_type: str
    actor_id: str | None
    actor_label: str | None
    action: str
    subject_type: str
    subject_id: str
    old_state: str | None
    new_state: str | None
    reason: str | None
    rule_version: str | None
    model_version: str | None
    payload: dict


class OutboxEventOut(BaseModel):
    id: str
    name: str
    subject_type: str | None
    subject_id: str | None
    payload: dict
    created_at: datetime
    delivered_at: datetime | None
    attempts: int
    last_error: str | None


class HealthResponse(BaseModel):
    status: str
    environment: str
    protocol_version: str
    database: str
    inference: str
    pending_events: int
    warnings: list[str] = Field(
        default_factory=list, description="O que impede este processo de ser produção."
    )
