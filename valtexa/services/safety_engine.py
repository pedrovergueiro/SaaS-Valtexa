"""Camada independente de segurança.

Este serviço decide se algo **pode** acontecer no mundo físico. Ele é o último
antes do hardware e o único cuja aprovação é obrigatória.

Três regras estruturais fazem dele uma camada de fato independente:

1. **Não importa nada do motor de decisão.** Se um dia a regra agronômica ficar
   errada, a segurança continua íntegra. A dependência é de propósito unilateral.
2. **Relê tudo do banco.** Nenhum valor chega por parâmetro — nem o produto, nem
   o polígono, nem quem aprovou. Um chamador comprometido não consegue mentir
   sobre o que vai ser executado, porque não é ele quem conta.
3. **Falha fechada.** Dado que falta é bloqueio, não é exceção. Um sensor de
   vento ausente bloqueia a pulverização; não a libera "porque não deu para
   verificar".

O parecer é gravado mesmo quando aprova. Um histórico só de bloqueios não
permitiria auditar por que algo *passou*.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from valtexa.config import settings
from valtexa.models import (
    Device,
    DeviceKind,
    DeviceStatus,
    Field,
    Membership,
    Mission,
    MissionKind,
    MissionState,
    ProductBatch,
    RtkFix,
    SafetyEvaluation,
    SafetyVerdict,
    SubjectType,
    Tank,
    TankStatus,
    TelemetrySample,
    as_utc,
)
from valtexa.models.agro import Product
from valtexa.security import rbac
from valtexa.services import elevation, geo
from valtexa.services.hal import capabilities_of

ENGINE_VERSION = "1.0.0"

# --- códigos de verificação --------------------------------------------------
# Estáveis: aparecem no banco, na auditoria e na tela do operador. Renomear um
# quebra o histórico.
DEVICE_EXISTS = "device_exists"
DEVICE_ACTIVE = "device_active"
DEVICE_TENANT = "device_tenant"
DEVICE_KIND = "device_kind"
DEVICE_CAPABILITY = "device_capability"
DEVICE_FREE = "device_free"
BATTERY = "battery"
RTK = "rtk"
MISSION_STATE = "mission_state"
MISSION_NOT_EXPIRED = "mission_not_expired"
GEOMETRY_VALID = "geometry_valid"
GEOFENCE = "geofence"
SLOPE = "slope"
APPROVAL = "approval"
APPROVER_ROLE = "approver_role"
PRODUCT_PRESENT = "product_present"
PRODUCT_ACTIVE = "product_active"
PRODUCT_REGISTERED = "product_registered"
PRODUCT_CROP = "product_crop"
BATCH_VALID = "batch_valid"
TANK_PRESENT = "tank_present"
TANK_DEVICE = "tank_device"
TANK_CONTENT = "tank_content"
TANK_VOLUME = "tank_volume"
RATE_RANGE = "rate_range"
WEATHER = "weather"


@dataclass(frozen=True, slots=True)
class Check:
    """Uma verificação e seu resultado."""

    code: str
    passed: bool
    detail: str

    def as_dict(self) -> dict:
        return {"code": self.code, "passed": self.passed, "detail": self.detail}


@dataclass(frozen=True, slots=True)
class SafetyReport:
    """O parecer completo."""

    verdict: SafetyVerdict
    checks: tuple[Check, ...]

    @property
    def blocked(self) -> tuple[Check, ...]:
        return tuple(check for check in self.checks if not check.passed)

    @property
    def blocked_code(self) -> str | None:
        failures = self.blocked
        return failures[0].code if failures else None

    @property
    def blocked_reason(self) -> str | None:
        failures = self.blocked
        if not failures:
            return None
        return " | ".join(f"{check.code}: {check.detail}" for check in failures)


def evaluate_mission(
    session: Session,
    mission: Mission,
    *,
    wind_ms: float | None = None,
    evaluated_by: str | None = None,
    now: datetime | None = None,
) -> SafetyEvaluation:
    """Avalia uma missão e devolve o parecer gravável. Não faz *commit*."""
    report = check_mission(session, mission, wind_ms=wind_ms, now=now)
    return SafetyEvaluation(
        tenant_id=mission.tenant_id,
        subject_type=SubjectType.MISSION,
        subject_id=mission.id,
        verdict=report.verdict,
        checks=[check.as_dict() for check in report.checks],
        blocked_code=report.blocked_code,
        blocked_reason=report.blocked_reason,
        engine_version=ENGINE_VERSION,
        evaluated_by=evaluated_by,
    )


def check_mission(
    session: Session,
    mission: Mission,
    *,
    wind_ms: float | None = None,
    now: datetime | None = None,
) -> SafetyReport:
    """Roda todas as verificações. Nenhuma interrompe as outras.

    Rodar tudo e só então concluir é deliberado: o operador precisa ver a lista
    completa de impedimentos de uma vez, não descobrir um por vez a cada
    tentativa.
    """
    moment = now or datetime.now(UTC)
    checks: list[Check] = []

    checks += _check_mission_state(mission, moment)
    device = session.get(Device, mission.device_id)
    checks += _check_device(session, mission, device, moment)
    checks += _check_geometry(session, mission)
    checks += _check_slope(session, mission)

    if mission.kind is MissionKind.SPRAY:
        checks += _check_approval(session, mission)
        checks += _check_product_chain(session, mission, moment)
        checks += _check_weather(session, mission, wind_ms)

    verdict = (
        SafetyVerdict.SAFE_TO_EXECUTE
        if all(check.passed for check in checks)
        else SafetyVerdict.BLOCKED
    )
    return SafetyReport(verdict=verdict, checks=tuple(checks))


# ---------------------------------------------------------------------------
# Verificações
# ---------------------------------------------------------------------------

_AUTHORIZABLE = {MissionState.DRAFT, MissionState.PENDING_SAFETY, MissionState.BLOCKED}


def _check_mission_state(mission: Mission, now: datetime) -> list[Check]:
    checks = [
        Check(
            MISSION_STATE,
            mission.state in _AUTHORIZABLE,
            f"Estado {mission.state.value!r}; autorizável a partir de "
            f"{sorted(state.value for state in _AUTHORIZABLE)}.",
        )
    ]
    expires_at = as_utc(mission.expires_at)
    checks.append(
        Check(
            MISSION_NOT_EXPIRED,
            expires_at is None or expires_at > now,
            "Sem validade definida."
            if expires_at is None
            else f"Válida até {expires_at:%d/%m %H:%M}.",
        )
    )
    return checks


def _check_device(
    session: Session, mission: Mission, device: Device | None, now: datetime
) -> list[Check]:
    if device is None:
        return [Check(DEVICE_EXISTS, False, f"Dispositivo {mission.device_id!r} não existe.")]

    checks = [
        Check(DEVICE_EXISTS, True, f"Dispositivo {device.serial_number}."),
        Check(
            DEVICE_TENANT,
            device.tenant_id == mission.tenant_id,
            "Dispositivo pertence ao mesmo cliente da missão.",
        ),
        Check(
            DEVICE_ACTIVE,
            device.status is DeviceStatus.ACTIVE,
            f"Status {device.status.value!r}; exigido 'active'.",
        ),
    ]

    expected_kind = DeviceKind.DRONE if mission.kind is MissionKind.SPRAY else DeviceKind.ROVER
    checks.append(
        Check(
            DEVICE_KIND,
            device.kind is expected_kind,
            f"Missão {mission.kind.value!r} exige {expected_kind.value!r}, "
            f"dispositivo é {device.kind.value!r}.",
        )
    )

    capabilities = capabilities_of(device.capabilities)
    missing = (
        capabilities.missing_for_spray()
        if mission.kind is MissionKind.SPRAY
        else capabilities.missing_for_scout()
    )
    checks.append(
        Check(
            DEVICE_CAPABILITY,
            not missing,
            "Hardware apto." if not missing else f"Capacidades ausentes: {missing}.",
        )
    )

    # Um dispositivo com missão ativa não pode receber outra: o robô tem um
    # corpo só, e duas autorizações simultâneas são duas verdades diferentes
    # sobre onde ele pode estar.
    free = device.active_mission_id in (None, mission.id)
    checks.append(
        Check(
            DEVICE_FREE,
            free,
            "Sem outra missão em curso." if free else f"Já executa {device.active_mission_id}.",
        )
    )

    battery = device.battery_percent
    checks.append(
        Check(
            BATTERY,
            battery is not None and battery >= settings.safety_min_battery_percent,
            f"Bateria {battery}% (mínimo {settings.safety_min_battery_percent}%)."
            if battery is not None
            else "Sem leitura de bateria: não é possível garantir energia para o retorno.",
        )
    )

    if mission.kind is MissionKind.SPRAY:
        checks.append(_check_rtk(session, device))
    return checks


def _check_rtk(session: Session, device: Device) -> Check:
    """Exige correção RTK fixa para pulverizar.

    Sem RTK o erro de posição é de metros. Aplicar defensivo com esse erro é
    aplicar na área do vizinho — e a responsabilidade seria da ValTexa.
    """
    latest = session.scalars(
        select(TelemetrySample)
        .where(TelemetrySample.device_id == device.id)
        .order_by(TelemetrySample.recorded_at.desc())
        .limit(1)
    ).first()
    if latest is None:
        return Check(RTK, False, "Sem telemetria recente: estado do RTK desconhecido.")
    return Check(
        RTK,
        latest.rtk_fix is RtkFix.FIXED,
        f"RTK {latest.rtk_fix.value!r}; exigido 'fixed' para aplicação.",
    )


def _check_slope(session: Session, mission: Mission) -> list[Check]:
    """Barra a missão cuja encosta passa do ângulo que o rover aguenta.

    A verificação **passa** quando não há relevo medido, e é assim de propósito:
    esta plataforma pode rodar sem fonte de elevação contratada, e transformar
    "não medi" em "não pode" travaria toda missão de toda instalação que ainda
    não ligou um DEM. O que não se pode é o contrário — tratar "não medi" como
    "é plano" sem dizer. Por isso a mensagem do parecer distingue os dois casos
    em letras, mesmo quando o veredito é o mesmo.

    Medido e acima do limite, aí sim bloqueia. Tombar numa encosta é perda total
    do equipamento, e é o tipo de dano que nenhum operador aceita ter aprovado
    sem aviso.
    """
    field_row = session.get(Field, mission.field_id)
    relevo = field_row.relief if field_row else None
    if not relevo:
        return [
            Check(
                SLOPE,
                True,
                "Relevo não medido: a rota foi planejada como se o talhão fosse "
                "plano. Confira a declividade no local antes de autorizar.",
            )
        ]

    device = session.get(Device, mission.device_id)
    capabilities = capabilities_of(device.capabilities if device else {})
    limite = capabilities.number("max_slope_deg", elevation.LIMITE_DE_TOMBAMENTO_PADRAO_DEG)
    maxima = float(relevo.get("declividade_maxima_deg") or 0.0)

    return [
        Check(
            SLOPE,
            maxima < limite,
            f"Declividade máxima medida {maxima:.0f}°, limite do modelo {limite:.0f}°"
            + (f" (fonte: {relevo.get('fonte')})." if relevo.get("fonte") else "."),
        )
    ]


def _check_geometry(session: Session, mission: Mission) -> list[Check]:
    """Valida o polígono e confere que ele cabe no talhão, com margem."""
    try:
        target = geo.as_points(mission.target_polygon)
    except geo.InvalidPolygonError as exc:
        return [Check(GEOMETRY_VALID, False, f"Polígono da missão inválido: {exc}")]

    checks = [Check(GEOMETRY_VALID, True, f"Polígono com {len(target)} vértices.")]

    field_row = session.get(Field, mission.field_id)
    if field_row is None:
        return [*checks, Check(GEOFENCE, False, "Talhão da missão não existe.")]

    try:
        allowed = geo.shrink(field_row.boundary, settings.geofence_margin_m)
    except geo.InvalidPolygonError as exc:
        return [*checks, Check(GEOFENCE, False, f"Limite do talhão inválido: {exc}")]

    inside = geo.polygon_contains_polygon(allowed, target)
    crosses = geo.edges_cross(allowed, target)
    checks.append(
        Check(
            GEOFENCE,
            inside and not crosses,
            (
                f"Área da missão contida no talhão com margem de "
                f"{settings.geofence_margin_m} m."
                if inside and not crosses
                else "Área da missão sai do talhão autorizado (ou cruza o limite)."
            ),
        )
    )
    return checks


def _check_approval(session: Session, mission: Mission) -> list[Check]:
    """Exige aprovação humana com o papel certo.

    A checagem do papel é refeita aqui, e não confiada ao momento em que a
    aprovação foi registrada, porque entre uma coisa e outra o papel pode ter
    sido revogado — e uma autorização assinada por quem já não é agrônomo não
    vale.
    """
    if not mission.approved_by:
        return [
            Check(APPROVAL, False, "Missão de aplicação sem aprovação humana registrada."),
            Check(APPROVER_ROLE, False, "Sem aprovador para verificar."),
        ]

    membership = session.scalars(
        select(Membership).where(
            Membership.tenant_id == mission.tenant_id, Membership.user_id == mission.approved_by
        )
    ).first()

    if membership is None:
        return [
            Check(APPROVAL, True, f"Aprovada por {mission.approved_by}."),
            Check(APPROVER_ROLE, False, "O aprovador não pertence mais a este cliente."),
        ]

    allowed = rbac.can(membership.role, rbac.MISSION_APPROVE_APPLICATION)
    return [
        Check(APPROVAL, True, f"Aprovada por {mission.approved_by}."),
        Check(
            APPROVER_ROLE,
            allowed,
            f"Papel {membership.role.value!r} "
            + ("pode aprovar aplicação." if allowed else "não pode aprovar aplicação."),
        ),
    ]


def _check_product_chain(session: Session, mission: Mission, now: datetime) -> list[Check]:
    """O elo tanque → lote → produto → missão.

    É a verificação que impede a pior falha do sistema: aplicar um produto numa
    área autorizada para outro.
    """
    if not mission.product_id:
        return [Check(PRODUCT_PRESENT, False, "Missão de aplicação sem produto definido.")]

    product = session.get(Product, mission.product_id)
    if product is None or product.tenant_id != mission.tenant_id:
        return [Check(PRODUCT_PRESENT, False, "Produto inexistente ou de outro cliente.")]

    checks = [
        Check(PRODUCT_PRESENT, True, f"Produto {product.name!r}."),
        Check(
            PRODUCT_ACTIVE,
            product.status.value == "active",
            f"Status do produto: {product.status.value!r}.",
        ),
        Check(
            PRODUCT_REGISTERED,
            bool(product.registration_number),
            "Registro no MAPA informado."
            if product.registration_number
            else "Produto sem número de registro.",
        ),
    ]

    field_row = session.get(Field, mission.field_id)
    crop = field_row.crop if field_row else ""
    checks.append(
        Check(
            PRODUCT_CROP,
            crop in (product.allowed_crops or []),
            f"Cultura {crop!r} "
            + (
                "consta entre as autorizadas."
                if crop in (product.allowed_crops or [])
                else f"não está em {product.allowed_crops}."
            ),
        )
    )
    checks.append(_check_rate(mission, product))
    checks.append(_check_batch(session, mission, now))
    checks += _check_tank(session, mission)
    return checks


def _check_rate(mission: Mission, product: Product) -> Check:
    rate = mission.authorized_rate_l_ha
    if rate is None:
        return Check(RATE_RANGE, False, "Dose da missão não informada.")
    minimum = product.min_rate_l_ha
    maximum = product.max_rate_l_ha
    if minimum is not None and rate < minimum:
        return Check(RATE_RANGE, False, f"Dose {rate} abaixo da mínima de bula ({minimum}).")
    if maximum is not None and rate > maximum:
        return Check(RATE_RANGE, False, f"Dose {rate} acima da máxima de bula ({maximum}).")
    return Check(RATE_RANGE, True, f"Dose {rate} L/ha dentro da faixa de bula.")


def _check_batch(session: Session, mission: Mission, now: datetime) -> Check:
    if not mission.product_batch_id:
        return Check(BATCH_VALID, False, "Missão sem lote de produto definido.")
    batch = session.get(ProductBatch, mission.product_batch_id)
    if batch is None or batch.product_id != mission.product_id:
        return Check(BATCH_VALID, False, "Lote inexistente ou de outro produto.")
    today: date = now.date()
    if batch.is_expired(today):
        return Check(BATCH_VALID, False, f"Lote {batch.code!r} vencido em {batch.expires_on}.")
    return Check(BATCH_VALID, True, f"Lote {batch.code!r} válido.")


def _check_tank(session: Session, mission: Mission) -> list[Check]:
    if not mission.tank_id:
        return [Check(TANK_PRESENT, False, "Missão de aplicação sem tanque definido.")]
    tank = session.get(Tank, mission.tank_id)
    if tank is None or tank.tenant_id != mission.tenant_id:
        return [Check(TANK_PRESENT, False, "Tanque inexistente ou de outro cliente.")]

    checks = [
        Check(TANK_PRESENT, True, f"Tanque {tank.index} do dispositivo."),
        Check(
            TANK_DEVICE,
            tank.device_id == mission.device_id,
            "Tanque pertence ao dispositivo da missão."
            if tank.device_id == mission.device_id
            else "Tanque é de outro dispositivo.",
        ),
    ]

    content_matches = (
        tank.status in {TankStatus.LOADED, TankStatus.SEALED}
        and tank.loaded_product_id == mission.product_id
        and (
            mission.product_batch_id is None
            or tank.loaded_batch_id == mission.product_batch_id
        )
    )
    checks.append(
        Check(
            TANK_CONTENT,
            content_matches,
            "Conteúdo do tanque confere com o produto e o lote autorizados."
            if content_matches
            else (
                f"Divergência: tanque está {tank.status.value!r} com produto "
                f"{tank.loaded_product_id!r}/lote {tank.loaded_batch_id!r}; a missão "
                f"autoriza {mission.product_id!r}/{mission.product_batch_id!r}."
            ),
        )
    )

    needed = mission.authorized_quantity_l
    enough = needed is not None and tank.current_level_l >= needed
    checks.append(
        Check(
            TANK_VOLUME,
            enough,
            f"Tanque com {tank.current_level_l} L para {needed} L autorizados."
            if enough
            else f"Volume insuficiente: {tank.current_level_l} L para {needed} L autorizados.",
        )
    )
    return checks


def _check_weather(session: Session, mission: Mission, wind_ms: float | None) -> list[Check]:
    """Vento. Sem leitura, bloqueia.

    Falhar fechado aqui é uma decisão de produto, não um detalhe: pulverizar sem
    saber o vento é como a deriva atinge a mata ciliar e a lavoura do vizinho.
    A leitura vem da dock, que fica no talhão — ver ``docs/DOCK_INTEGRATION.md``.
    """
    if wind_ms is None:
        wind_ms = _wind_from_dock(session, mission)
    if wind_ms is None:
        return [
            Check(
                WEATHER,
                False,
                "Sem leitura de vento. A pulverização exige o dado — a dock do "
                "talhão é a fonte esperada.",
            )
        ]

    limit = settings.safety_max_wind_ms
    product = session.get(Product, mission.product_id) if mission.product_id else None
    if product is not None and product.max_wind_ms is not None:
        limit = min(limit, product.max_wind_ms)

    return [
        Check(
            WEATHER,
            wind_ms <= limit,
            f"Vento {wind_ms:.1f} m/s (limite {limit:.1f} m/s).",
        )
    ]


def _wind_from_dock(session: Session, mission: Mission) -> float | None:
    """Última leitura de vento de uma dock da mesma fazenda."""
    latest = session.scalars(
        select(TelemetrySample)
        .join(Device, Device.id == TelemetrySample.device_id)
        .where(
            Device.tenant_id == mission.tenant_id,
            Device.farm_id == mission.farm_id,
            Device.kind == DeviceKind.DOCK,
        )
        .order_by(TelemetrySample.recorded_at.desc())
        .limit(1)
    ).first()
    if latest is None:
        return None
    value = (latest.sensors or {}).get("wind_ms")
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
