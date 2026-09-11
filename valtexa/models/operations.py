"""Missões, telemetria e eventos — o que acontece em campo.

A missão é o único contrato de execução. Um robô nunca recebe "vá até esta
coordenada e aplique": recebe uma missão assinada, com polígono autorizado,
produto, dose, validade e política de contingência. Fora do polígono e depois da
validade, nada é executado — a verificação é feita duas vezes, na nuvem antes de
despachar e no robô antes de agir.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from valtexa.models.base import Base, TenantScoped, Timestamped, UUIDPrimaryKey, enum_column
from valtexa.models.enums import (
    EnergyState,
    EventSeverity,
    MissionKind,
    MissionState,
    RtkFix,
    SafetyVerdict,
    SegmentState,
)


class Mission(UUIDPrimaryKey, TenantScoped, Timestamped, Base):
    """Uma tarefa fechada e autorizada para um dispositivo."""

    __tablename__ = "mission"

    kind: Mapped[MissionKind] = mapped_column(enum_column(MissionKind), nullable=False, index=True)
    state: Mapped[MissionState] = mapped_column(
        enum_column(MissionState), default=MissionState.DRAFT, nullable=False, index=True
    )

    farm_id: Mapped[str] = mapped_column(String(32), ForeignKey("farm.id"), nullable=False)
    field_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("field.id"), nullable=False, index=True
    )
    zone_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("zone.id"))
    device_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("device.id"), nullable=False, index=True
    )

    target_polygon: Mapped[list] = mapped_column(
        nullable=False,
        default=list,
        doc=(
            "O polígono autorizado, [[lon, lat], ...]. É a fronteira física da "
            "missão: o robô não atua fora dele, e o safety engine exige que ele "
            "esteja contido no talhão."
        ),
    )
    waypoints: Mapped[list] = mapped_column(default=list, doc="Rota planejada [[lon, lat], ...].")
    plan: Mapped[dict] = mapped_column(
        default=dict, doc="Parâmetros do voo/percurso: altura, velocidade, sobreposição, GSD."
    )

    # --- pulverização: nulo em missão de scout ---------------------------------
    product_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("product.id"))
    product_batch_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("product_batch.id")
    )
    tank_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("tank.id"))
    authorized_quantity_l: Mapped[float | None] = mapped_column(Float)
    authorized_rate_l_ha: Mapped[float | None] = mapped_column(Float)

    # --- procedência e aprovação -----------------------------------------------
    decision_id: Mapped[str | None] = mapped_column(
        String(32), doc="A recomendação que originou esta missão. Nulo em missão manual."
    )
    source_mission_id: Mapped[str | None] = mapped_column(
        String(32), doc="Em missão de verificação, a missão de aplicação verificada."
    )
    created_by: Mapped[str | None] = mapped_column(String(32), ForeignKey("user.id"))
    approved_by: Mapped[str | None] = mapped_column(
        String(32),
        ForeignKey("user.id"),
        doc="Quem aprovou a aplicação. Obrigatório em missão SPRAY — nenhuma IA preenche isto.",
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # --- validade e assinatura --------------------------------------------------
    authorized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    safety_status: Mapped[SafetyVerdict | None] = mapped_column(enum_column(SafetyVerdict))
    safety_reason: Mapped[str | None] = mapped_column(Text)
    signature: Mapped[str | None] = mapped_column(String(128))
    signing_key_id: Mapped[str | None] = mapped_column(String(32))
    nonce: Mapped[str | None] = mapped_column(String(64), unique=True)
    command_sequence: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    command_payload: Mapped[dict] = mapped_column(
        default=dict,
        doc=(
            "O envelope exato que foi assinado. Guardado byte a byte porque a "
            "assinatura cobre a serialização: remontar o envelope depois "
            "produziria outro nonce e outro horário, e a assinatura gravada "
            "deixaria de conferir. É também o que permite o robô rebuscar a "
            "mesma missão depois de uma queda de enlace."
        ),
    )

    # --- políticas embarcadas ---------------------------------------------------
    energy_policy: Mapped[dict] = mapped_column(
        default=dict, doc="Reservas e limiares que o robô aplica sozinho. Ver services/energy.py."
    )
    offline_policy: Mapped[dict] = mapped_column(
        default=dict, doc="O que fazer quando a nuvem some. Ver docs/OFFLINE_MODE.md."
    )
    abort_reason: Mapped[str | None] = mapped_column(Text)

    segments: Mapped[list[MissionSegment]] = relationship(
        back_populates="mission",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="MissionSegment.index",
    )
    checkpoints: Mapped[list[MissionCheckpoint]] = relationship(
        back_populates="mission",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="MissionCheckpoint.created_at",
    )

    @property
    def is_spray(self) -> bool:
        return self.kind is MissionKind.SPRAY


class MissionSegment(UUIDPrimaryKey, Timestamped, Base):
    """Um trecho da cobertura — tipicamente uma passada entre linhas.

    Segmentar é o que permite retomar: sem isso, um rover que voltou para
    recarregar teria de refazer a lavoura inteira.
    """

    __tablename__ = "mission_segment"
    __table_args__ = (UniqueConstraint("mission_id", "index", name="uq_segment_mission_index"),)

    mission_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("mission.id", ondelete="CASCADE"), nullable=False, index=True
    )
    index: Mapped[int] = mapped_column(Integer, nullable=False)
    path: Mapped[list] = mapped_column(nullable=False, default=list)
    state: Mapped[SegmentState] = mapped_column(
        enum_column(SegmentState), default=SegmentState.PENDING, nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    estimated_energy_percent: Mapped[float | None] = mapped_column(Float)

    mission: Mapped[Mission] = relationship(back_populates="segments")


class MissionCheckpoint(UUIDPrimaryKey, Timestamped, Base):
    """O último ponto confiável da missão.

    Gravado sempre que um segmento termina e sempre que a missão pausa. É a
    memória que permite ``READY_TO_RESUME`` continuar de onde parou.
    """

    __tablename__ = "mission_checkpoint"

    mission_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("mission.id", ondelete="CASCADE"), nullable=False, index=True
    )
    last_completed_segment: Mapped[int] = mapped_column(Integer, nullable=False, default=-1)
    remaining_segments: Mapped[list] = mapped_column(nullable=False, default=list)
    last_lat: Mapped[float | None] = mapped_column(Float)
    last_lon: Mapped[float | None] = mapped_column(Float)
    battery_percent: Mapped[float | None] = mapped_column(Float)
    reason: Mapped[str | None] = mapped_column(String(120))

    mission: Mapped[Mission] = relationship(back_populates="checkpoints")


class TelemetrySample(UUIDPrimaryKey, TenantScoped, Base):
    """Uma amostra do estado do robô.

    Sem ``Timestamped``: é a tabela que mais cresce, e ``updated_at`` não faz
    sentido em série temporal — telemetria é imutável depois de aceita.
    """

    __tablename__ = "telemetry_sample"
    __table_args__ = (
        Index("ix_telemetry_device_time", "device_id", "recorded_at"),
        UniqueConstraint("device_id", "sequence_number", name="uq_telemetry_device_seq"),
    )

    device_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("device.id", ondelete="CASCADE"), nullable=False
    )
    mission_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("mission.id", ondelete="SET NULL"), index=True
    )
    sequence_number: Mapped[int] = mapped_column(
        Integer, nullable=False, doc="Contador monotônico do robô. Deduplica o reenvio offline."
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, doc="Relógio do robô."
    )
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        doc="Relógio do servidor. A diferença para recorded_at mede o atraso da sincronização.",
    )

    lat: Mapped[float | None] = mapped_column(Float)
    lon: Mapped[float | None] = mapped_column(Float)
    alt_m: Mapped[float | None] = mapped_column(Float)
    heading_deg: Mapped[float | None] = mapped_column(Float)
    speed_ms: Mapped[float | None] = mapped_column(Float)
    rtk_fix: Mapped[RtkFix] = mapped_column(
        enum_column(RtkFix), default=RtkFix.NONE, nullable=False
    )
    hdop: Mapped[float | None] = mapped_column(Float)

    battery_percent: Mapped[float | None] = mapped_column(Float)
    battery_voltage_v: Mapped[float | None] = mapped_column(Float)
    battery_current_a: Mapped[float | None] = mapped_column(Float)
    temperature_c: Mapped[float | None] = mapped_column(Float)
    energy_state: Mapped[EnergyState] = mapped_column(
        enum_column(EnergyState), default=EnergyState.NORMAL, nullable=False
    )

    mission_state: Mapped[str | None] = mapped_column(String(32))
    link_quality: Mapped[float | None] = mapped_column(Float)
    motors: Mapped[dict] = mapped_column(default=dict)
    sensors: Mapped[dict] = mapped_column(default=dict)
    faults: Mapped[list] = mapped_column(default=list)
    sync_id: Mapped[str | None] = mapped_column(String(32), doc="Lote de sincronização de origem.")


class TelemetryRollup(UUIDPrimaryKey, TenantScoped, Base):
    """Telemetria antiga agregada em janelas.

    A amostra crua é a tabela que mais cresce: um rover a 1 Hz produz ~14 mil
    linhas por jornada. Depois da janela de retenção ela vira uma linha por
    minuto, com o que um relatório ainda precisa — mínimo, média e máximo de
    bateria, velocidade, qualidade de enlace e a última posição. Ver
    :mod:`valtexa.services.retention`.

    Evento **não** é agregado nunca: é o registro que a auditoria precisa íntegro.
    """

    __tablename__ = "telemetry_rollup"
    __table_args__ = (
        UniqueConstraint("device_id", "bucket_start", name="uq_rollup_device_bucket"),
    )

    device_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("device.id", ondelete="CASCADE"), nullable=False, index=True
    )
    bucket_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    bucket_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    samples: Mapped[int] = mapped_column(Integer, nullable=False)
    battery_min: Mapped[float | None] = mapped_column(Float)
    battery_avg: Mapped[float | None] = mapped_column(Float)
    battery_max: Mapped[float | None] = mapped_column(Float)
    speed_avg_ms: Mapped[float | None] = mapped_column(Float)
    link_quality_avg: Mapped[float | None] = mapped_column(Float)
    rtk_fixed_ratio: Mapped[float | None] = mapped_column(
        Float, doc="Fração das amostras com RTK fixo na janela."
    )
    last_lat: Mapped[float | None] = mapped_column(Float)
    last_lon: Mapped[float | None] = mapped_column(Float)


class DeviceEvent(UUIDPrimaryKey, TenantScoped, Base):
    """Um fato discreto relatado pelo robô.

    Diferente da telemetria: telemetria é amostragem contínua e descartável em
    agregação; evento é o que precisa sobreviver íntegro para a auditoria.
    """

    __tablename__ = "device_event"
    __table_args__ = (
        Index("ix_device_event_device_time", "device_id", "occurred_at"),
        UniqueConstraint("device_id", "sequence_number", name="uq_device_event_device_seq"),
    )

    device_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("device.id", ondelete="CASCADE"), nullable=False
    )
    mission_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("mission.id", ondelete="SET NULL"), index=True
    )
    type: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True, doc="Vocabulário em docs/EVENTS.md."
    )
    severity: Mapped[EventSeverity] = mapped_column(
        enum_column(EventSeverity), default=EventSeverity.INFO, nullable=False, index=True
    )
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload: Mapped[dict] = mapped_column(default=dict)
    sync_id: Mapped[str | None] = mapped_column(String(32))
