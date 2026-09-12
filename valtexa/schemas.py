"""Contrato HTTP da plataforma.

Os modelos de saída são achatados de propósito: o cliente recebe identificadores
e valores, nunca o objeto ORM serializado por reflexão. Assim, adicionar uma
coluna interna não vaza para a API por acidente.

O contrato é o mesmo para o frontend e para os robôs. Quando o SaaS visual for
construído, ele consome exatamente estes esquemas — nenhuma rota nova, nenhuma
regra que só exista na tela.
"""

from __future__ import annotations

import math
from datetime import date, datetime
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints, field_validator

from valtexa.models.base import as_utc
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


class ApiModel(BaseModel):
    """Base de todos os esquemas: horário sempre em UTC, com o fuso explícito.

    O SQLite devolve o horário sem fuso. Serializado assim, o navegador o leria
    como hora *local* — e o console mostraria quatro horas de diferença em
    Sorriso, justamente no carimbo de uma aplicação de defensivo. Na entrada, a
    mesma regra vale para o robô: horário sem fuso é UTC, como diz o protocolo.
    """

    @field_validator("*", mode="after")
    @classmethod
    def _utc(cls, value: object) -> object:
        if isinstance(value, datetime):
            return as_utc(value)
        return value

Polygon = Annotated[
    list[list[float]],
    Field(
        min_length=3,
        description="Anel [[lon, lat], ...] em WGS84, sem repetir o primeiro ponto no fim.",
    ),
]
Slug = Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9-]{1,62}$")]
Name = Annotated[str, StringConstraints(min_length=1, max_length=160, strip_whitespace=True)]


class Message(ApiModel):
    """Resposta simples de confirmação."""

    detail: str


class ErrorResponse(ApiModel):
    detail: str


# ---------------------------------------------------------------------------
# Autenticação e organização
# ---------------------------------------------------------------------------


class LoginRequest(ApiModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=256)
    tenant: Slug | None = Field(
        default=None,
        description="Cliente a abrir. Opcional quando o usuário pertence a um só.",
    )


class TokenResponse(ApiModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
    tenant_id: str | None
    role: Role | None
    capabilities: list[str]


class MembershipOut(ApiModel):
    tenant_id: str
    tenant_name: str
    tenant_slug: str
    role: Role


class MeResponse(ApiModel):
    id: str
    email: str
    full_name: str
    is_platform_admin: bool
    active_tenant_id: str
    role: Role
    capabilities: list[str]
    memberships: list[MembershipOut]


class TenantCreate(ApiModel):
    name: Name
    slug: Slug
    document: str | None = Field(default=None, max_length=32)


class TenantOut(ApiModel):
    id: str
    name: str
    slug: str
    document: str | None
    is_active: bool
    created_at: datetime


class UserInvite(ApiModel):
    email: EmailStr
    full_name: Name
    password: str = Field(min_length=8, max_length=256)
    role: Role


class UserOut(ApiModel):
    id: str
    email: str
    full_name: str
    role: Role
    is_active: bool


# ---------------------------------------------------------------------------
# Geografia
# ---------------------------------------------------------------------------


class FarmCreate(ApiModel):
    name: Name
    center_lat: float = Field(ge=-90, le=90)
    center_lon: float = Field(ge=-180, le=180)
    base_lat: float | None = Field(default=None, ge=-90, le=90)
    base_lon: float | None = Field(default=None, ge=-180, le=180)
    timezone: str = "America/Sao_Paulo"
    area_ha: float | None = Field(default=None, gt=0)


class FarmOut(ApiModel):
    id: str
    name: str
    timezone: str
    center_lat: float
    center_lon: float
    base_lat: float | None
    base_lon: float | None
    area_ha: float | None
    fields: int = Field(description="Quantos talhões cadastrados.")


class FieldCreate(ApiModel):
    name: Name
    crop: Annotated[str, StringConstraints(min_length=2, max_length=64)]
    boundary: Polygon
    variety: str | None = None
    crop_stage: str | None = None
    planted_on: date | None = None
    row_spacing_m: float | None = Field(default=None, gt=0)
    row_azimuth_deg: float | None = Field(
        default=None,
        ge=0,
        lt=180,
        description="Direção das linhas, graus a partir do norte. 0 = N-S, 90 = L-O.",
    )


class FieldOut(ApiModel):
    id: str
    farm_id: str
    name: str
    crop: str
    variety: str | None
    crop_stage: str | None
    planted_on: date | None
    row_spacing_m: float | None
    row_azimuth_deg: float | None = None
    area_ha: float | None
    boundary: list[list[float]]


class ZoneCreate(ApiModel):
    name: Name
    boundary: Polygon


class ZoneOut(ApiModel):
    id: str
    field_id: str
    name: str
    area_ha: float | None
    boundary: list[list[float]]


# ---------------------------------------------------------------------------
# Frota
# ---------------------------------------------------------------------------


class DeviceModelOut(ApiModel):
    id: str
    code: str
    kind: DeviceKind
    name: str
    manufacturer: str | None
    protocol_version: str
    capabilities: dict


class ProvisioningTokenCreate(ApiModel):
    device_model_code: str
    farm_id: str | None = None
    serial_number: str | None = Field(
        default=None,
        description="Amarra o convite a um número de série. Recomendado em produção.",
    )
    ttl_hours: int = Field(default=72, ge=1, le=720)


class ProvisioningTokenOut(ApiModel):
    """O token em claro aparece **uma única vez**, nesta resposta."""

    id: str
    token: str
    expires_at: datetime
    device_model_code: str
    serial_number: str | None


class DeviceProvisionRequest(ApiModel):
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


class DeviceProvisionResponse(ApiModel):
    """O que o robô guarda para o resto da vida."""

    device_id: str
    tenant_id: str
    key_id: str
    platform_public_key: str = Field(
        description="Usada pelo robô para verificar as missões que a nuvem assina."
    )
    protocol_version: str
    server_time: datetime


class DeviceOut(ApiModel):
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


class DeviceStatusUpdate(ApiModel):
    status: DeviceStatus
    reason: str | None = None


# ---------------------------------------------------------------------------
# Protocolo do dispositivo
# ---------------------------------------------------------------------------


class TelemetryIn(ApiModel):
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


class DeviceEventIn(ApiModel):
    sequence_number: int = Field(ge=0)
    type: Annotated[str, StringConstraints(min_length=2, max_length=64)]
    occurred_at: datetime | None = None
    severity: str = "info"
    mission_id: str | None = None
    payload: dict = Field(default_factory=dict)


class TelemetryBatch(ApiModel):
    sync_id: str | None = Field(
        default=None, description="Identificador do lote, para rastrear a sincronização offline."
    )
    samples: list[TelemetryIn] = Field(min_length=1)


class EventBatch(ApiModel):
    sync_id: str | None = None
    events: list[DeviceEventIn] = Field(min_length=1)


class SyncBatch(ApiModel):
    """Descarga de um robô que ficou offline."""

    sync_id: str
    samples: list[TelemetryIn] = Field(default_factory=list)
    events: list[DeviceEventIn] = Field(default_factory=list)


class IngestOut(ApiModel):
    accepted: int
    duplicated: int = Field(description="Já conhecidos. Reenvio é esperado, não é erro.")
    rejected: int
    errors: list[str] = Field(default_factory=list)


class ObservationIn(ApiModel):
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


class ObservationOut(ApiModel):
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
    severity: float | None = Field(
        default=None, description="Fração do quadro com lesão, quando medida."
    )


class SignedCommandOut(ApiModel):
    """O envelope assinado que o robô verifica antes de agir."""

    payload: dict
    signature: str
    key_id: str
    algorithm: str


class MissionAck(ApiModel):
    """Confirmação de recebimento pelo robô."""

    mission_id: str
    accepted: bool
    reason: str | None = Field(
        default=None, description="Por que recusou. Obrigatório quando accepted=false."
    )


class SegmentComplete(ApiModel):
    segment_index: int = Field(ge=0)
    lat: float | None = None
    lon: float | None = None
    battery_percent: float | None = None


class MissionPause(ApiModel):
    reason: str = Field(max_length=120)
    lat: float | None = None
    lon: float | None = None
    battery_percent: float | None = None


# ---------------------------------------------------------------------------
# Missões
# ---------------------------------------------------------------------------


class MissionCreate(ApiModel):
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


class MissionSegmentOut(ApiModel):
    index: int
    state: str
    path: list[list[float]]
    estimated_energy_percent: float | None


class MissionOut(ApiModel):
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
    approved_at: datetime | None = None
    product_batch_id: str | None = None
    decision_id: str | None = None
    dispatched_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    abort_reason: str | None = None
    authorized_at: datetime | None
    expires_at: datetime | None
    safety_status: SafetyVerdict | None
    safety_reason: str | None
    energy_policy: dict
    offline_policy: dict
    segments_total: int
    segments_done: int
    created_at: datetime


class MissionApproval(ApiModel):
    """Assinatura do agrônomo. Sem isto nenhuma pulverização é autorizada."""

    confirm: bool = Field(
        description="Precisa ser verdadeiro. Existe para evitar clique acidental."
    )
    notes: str | None = None


class AbortRequest(ApiModel):
    reason: str = Field(min_length=3, max_length=500)


class SafetyCheckOut(ApiModel):
    code: str
    passed: bool
    detail: str


class SafetyEvaluationOut(ApiModel):
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


class DetectionOut(ApiModel):
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


class DiagnosisOut(ApiModel):
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
    severity: float | None = Field(
        default=None,
        description=(
            "Fração do quadro com lesão, em [0, 1]. Aproxima a severidade da folha "
            "quando ela preenche o quadro. Informação para o agrônomo: não entra na "
            "regra de decisão."
        ),
    )
    rationale: str | None
    pipeline_version: str
    reviewed_by: str | None
    reviewed_at: datetime | None
    reviewed_label: str | None
    created_at: datetime
    detections: list[DetectionOut] = Field(default_factory=list)


class DiagnosisReview(ApiModel):
    """O veredito do agrônomo."""

    label: Annotated[str, StringConstraints(pattern=r"^[A-Za-z][A-Za-z0-9_]{0,63}$")] = Field(
        description=(
            "A classe correta. Pode ser um nome que ainda não existe no catálogo "
            "do modelo — é assim que uma doença nova entra no dataset próprio."
        ),
        examples=["Gray_Leaf_Spot", "Cigarrinha"],
    )
    confirmed: bool = Field(
        default=True,
        description=(
            "Verdadeiro registra o diagnóstico do agrônomo — concorde ou não com a IA; "
            "corrigir o rótulo é confirmar com o rótulo certo. Falso descarta a imagem "
            "como sem condição de diagnóstico."
        ),
    )
    notes: str | None = None


class DecisionOut(ApiModel):
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


class ProductCreate(ApiModel):
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


class BatchCreate(ApiModel):
    code: Annotated[str, StringConstraints(min_length=1, max_length=64)]
    expires_on: date | None = None
    quantity_l: float | None = Field(default=None, gt=0)


class BatchOut(ApiModel):
    id: str
    product_id: str
    code: str
    expires_on: date | None
    quantity_l: float | None


class TankCreate(ApiModel):
    device_id: str
    index: int = Field(ge=0)
    capacity_l: float = Field(gt=0)
    label: str | None = None


class TankLoad(ApiModel):
    """Carga de um tanque. É o registro que o safety engine confere."""

    product_id: str
    batch_id: str
    volume_l: float = Field(gt=0)


class TankOut(ApiModel):
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


class ApplicationStart(ApiModel):
    """Reportado pelo drone quando abre o bico."""

    mission_id: str
    started_at: datetime
    tank_id: str | None = None


class ApplicationStop(ApiModel):
    stopped_at: datetime
    amount_used_l: float = Field(ge=0)
    area_ha: float | None = Field(default=None, ge=0)
    track: list[list[float]] = Field(
        default_factory=list, description="[[lon, lat, vazão], ...] — o mapa de aplicação."
    )
    stop_reason: str | None = None


class ApplicationOut(ApiModel):
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


class VerificationOut(ApiModel):
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


class ClassCountOut(ApiModel):
    label: str
    count: int
    ratio: float


class FieldSnapshotOut(ApiModel):
    field_id: str
    field_name: str
    crop: str
    since: datetime
    until: datetime
    observations: int
    diagnosed: int
    needs_review: int
    classes: list[ClassCountOut]


class TimePointOut(ApiModel):
    day: date
    total: int
    counts: dict[str, int]


class AnomalyOut(ApiModel):
    field_id: str
    zone_id: str | None
    label: str
    baseline_ratio: float
    current_ratio: float
    baseline_sample: int
    current_sample: int
    detail: str


# --- cópia 3D -------------------------------------------------------------------

MAX_PLANTS_PER_SCAN = 30_000
"""Plantas por passada. Uma rua de 300 m com seis linhas à vista tem ~9 000."""


class RowScanIn(ApiModel):
    """Metadados de uma passada. A nuvem de pontos, quando houver, vai no ``file``.

    Posições em metros no plano local com origem em ``origin_lon``/``origin_lat``:
    x para leste, y para norte, z para cima — o mesmo plano da nuvem de pontos.
    """

    sequence_number: int = Field(description="Sequência do robô; reenviar a mesma é seguro.")
    mission_id: str | None = None
    field_id: str
    segment_index: int | None = None
    row_index: int | None = None
    started_at: datetime | None = None
    captured_at: datetime = Field(description="Fim da passada.")
    sensor: str = Field(default="lidar", pattern="^(lidar|stereo|camera)$")
    origin_lat: float = Field(ge=-90, le=90)
    origin_lon: float = Field(ge=-180, le=180)
    origin_alt_m: float | None = None
    path: list[list[float]] = Field(
        min_length=2, max_length=5_000, description="Eixo percorrido, [[lon, lat], ...]."
    )
    reach_m: float = Field(
        gt=0, le=10, description="Alcance lateral do sensor a partir do eixo, em metros."
    )
    plants: list[list[float]] = Field(
        default_factory=list,
        max_length=MAX_PLANTS_PER_SCAN,
        description=(
            "Uma entrada por planta: [x, y, altura_m, copa_m] ou [x, y, altura_m, "
            "copa_m, verde], com verde em [0, 1] (índice de excesso de verde do RGB "
            "da planta)."
        ),
    )

    @field_validator("path")
    @classmethod
    def _check_path(cls, value: list[list[float]]) -> list[list[float]]:
        for point in value:
            if len(point) < 2 or not (-180 <= point[0] <= 180 and -90 <= point[1] <= 90):
                raise ValueError(f"Ponto do eixo inválido: {point!r}. Esperado [lon, lat].")
        return value

    @field_validator("plants")
    @classmethod
    def _check_plants(cls, value: list[list[float]]) -> list[list[float]]:
        for plant in value:
            if len(plant) not in (4, 5) or not all(math.isfinite(item) for item in plant):
                raise ValueError(
                    f"Planta inválida: {plant!r}. Esperado [x, y, altura, copa(, verde)]."
                )
            x, y, height, canopy = plant[:4]
            if abs(x) > 2_000 or abs(y) > 2_000:
                raise ValueError(f"Planta a mais de 2 km da origem da passada: {plant!r}.")
            if not 0 <= height <= 8 or not 0 <= canopy <= 6:
                raise ValueError(f"Altura ou copa fora do plausível: {plant!r}.")
            if len(plant) == 5 and not 0 <= plant[4] <= 1:
                raise ValueError(f"Índice de verde fora de [0, 1]: {plant!r}.")
        return value


class RowScanOut(ApiModel):
    id: str
    field_id: str
    mission_id: str | None
    device_id: str
    sequence_number: int
    segment_index: int | None
    row_index: int | None
    captured_at: datetime
    sensor: str
    reach_m: float
    length_m: float
    plant_count: int
    mean_height_m: float | None
    max_height_m: float | None
    point_count: int | None
    has_pointcloud: bool


class SceneZoneOut(ApiModel):
    id: str
    name: str
    boundary: list[list[float]]


class SceneScanOut(ApiModel):
    """Uma rua na cópia: onde o rover passou, quando, e o que mediu."""

    id: str
    captured_at: datetime
    device_id: str
    device_name: str | None
    mission_id: str | None
    segment_index: int | None
    row_index: int | None
    sensor: str
    reach_m: float
    length_m: float
    origin: list[float] = Field(description="Origem da passada no plano do talhão, [x, y].")
    path: list[list[float]]
    plant_count: int
    visible_plants: int = Field(
        description=(
            "Quantas plantas desta passada estão na cópia — as outras foram "
            "cobertas por uma passada mais nova."
        )
    )
    mean_height_m: float | None
    max_height_m: float | None
    point_count: int | None
    has_pointcloud: bool
    markers: dict[str, int] = Field(description="Observações nesta rua, por categoria.")


class ScenePlantsOut(ApiModel):
    """Plantas da cópia em colunas. Cada índice é uma planta."""

    x: list[float]
    y: list[float]
    height: list[float]
    canopy: list[float]
    greenness: list[float | None]
    scan: list[int] = Field(description="Índice em ``scans`` da passada que mediu a planta.")


class SceneMarkerOut(ApiModel):
    """Uma foto diagnosticada, presa à planta fotografada."""

    observation_id: str
    diagnosis_id: str | None
    x: float
    y: float
    z: float
    label: str | None
    category: str = Field(description="healthy, disease, pest, review ou other.")
    status: DiagnosisStatus | None
    confidence: float | None
    novelty_score: float | None
    severity: float | None
    captured_at: datetime
    plant: int | None = Field(
        description="Índice da planta em ``plants``, quando há uma a até 60 cm."
    )
    scan: int | None


class SceneDeviceOut(ApiModel):
    id: str
    name: str
    kind: DeviceKind
    x: float
    y: float
    battery_percent: float | None
    last_seen_at: datetime | None
    active_mission_id: str | None


class SceneMissionOut(ApiModel):
    """Uma varredura em andamento: as ruas que faltam aparecem na cópia."""

    mission_id: str
    state: MissionState
    segments: int
    done: int
    pending: list[list[list[float]]]


class ScenePassOut(ApiModel):
    day: date
    scans: int


class FieldSceneOut(ApiModel):
    """A cópia 3D do talhão.

    Coordenadas em metros no plano local do talhão: origem no centro do limite,
    x para leste, y para norte, z para cima.
    """

    field_id: str
    field_name: str
    crop: str
    crop_stage: str | None
    row_azimuth_deg: float | None
    row_spacing_m: float | None
    origin_lon: float
    origin_lat: float
    at: datetime
    since: datetime
    live: bool
    boundary: list[list[float]]
    zones: list[SceneZoneOut]
    field_area_m2: float
    scanned_area_m2: float
    coverage_ratio: float
    scans: list[SceneScanOut]
    plants: ScenePlantsOut
    markers: list[SceneMarkerOut]
    counts: dict[str, int]
    devices: list[SceneDeviceOut]
    missions: list[SceneMissionOut]
    passes: list[ScenePassOut]


class AuditOut(ApiModel):
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


class OutboxEventOut(ApiModel):
    id: str
    name: str
    subject_type: str | None
    subject_id: str | None
    payload: dict
    created_at: datetime
    delivered_at: datetime | None
    attempts: int
    last_error: str | None


class HealthResponse(ApiModel):
    status: str
    environment: str
    protocol_version: str
    database: str
    inference: str
    pending_events: int
    warnings: list[str] = Field(
        default_factory=list, description="O que impede este processo de ser produção."
    )


class UserUpdate(ApiModel):
    role: Role


# ---------------------------------------------------------------------------
# Console
# ---------------------------------------------------------------------------


class TelemetryOut(ApiModel):
    sequence_number: int
    recorded_at: datetime
    received_at: datetime
    mission_id: str | None
    lat: float | None
    lon: float | None
    alt_m: float | None
    heading_deg: float | None
    speed_ms: float | None
    rtk_fix: str
    battery_percent: float | None
    battery_voltage_v: float | None
    temperature_c: float | None
    energy_state: str
    mission_state: str | None
    link_quality: float | None
    sensors: dict
    faults: list[Any]


class TelemetryRollupOut(ApiModel):
    bucket_start: datetime
    bucket_seconds: int
    samples: int
    battery_min: float | None
    battery_avg: float | None
    battery_max: float | None
    speed_avg_ms: float | None
    link_quality_avg: float | None
    rtk_fixed_ratio: float | None
    last_lat: float | None
    last_lon: float | None


class DeviceEventOut(ApiModel):
    id: str
    device_id: str
    mission_id: str | None
    type: str
    severity: str
    sequence_number: int
    occurred_at: datetime
    received_at: datetime
    payload: dict


class MissionHistoryOut(ApiModel):
    at: datetime
    action: str
    old_state: str | None
    new_state: str | None
    reason: str | None
    actor_type: str
    actor: str | None


class CheckpointOut(ApiModel):
    created_at: datetime
    last_completed_segment: int
    remaining_segments: int
    battery_percent: float | None
    reason: str | None
    lat: float | None
    lon: float | None


class AlertOut(ApiModel):
    """Um alerta derivado do estado do sistema. Some quando a causa é resolvida."""

    id: str
    kind: str
    severity: str = Field(description="'critical', 'warning' ou 'info'.")
    title: str
    detail: str
    subject_type: str | None
    subject_id: str | None
    at: datetime


class DeviceSummary(ApiModel):
    total: int
    active: int
    online: int
    offline: int
    low_battery: int
    by_kind: dict[str, int]


class ApplicationSummary(ApiModel):
    count: int
    liters: float
    area_ha: float


class MissionBrief(ApiModel):
    id: str
    kind: MissionKind
    state: MissionState
    device_id: str
    device_name: str | None
    field_id: str
    field_name: str | None
    created_at: datetime
    segments_total: int
    segments_done: int


class DashboardOut(ApiModel):
    generated_at: datetime
    devices: DeviceSummary
    missions_by_state: dict[str, int]
    review_queue: int
    observations_7d: int
    labels_7d: dict[str, int]
    applications_30d: ApplicationSummary
    verifications_pending: int
    alert_counts: dict[str, int]
    alerts: list[AlertOut]
    recent_missions: list[MissionBrief]
