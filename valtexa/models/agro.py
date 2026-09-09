"""Produtos, tanques, aplicações e verificação do resultado.

O vínculo ``tanque → lote → produto → missão`` é o que impede a pior falha
possível do sistema: aplicar o produto errado numa área autorizada para outro.
A missão declara o produto; o tanque declara o que está dentro dele; o safety
engine compara os dois e bloqueia quando divergem.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from valtexa.models.base import Base, TenantScoped, Timestamped, UUIDPrimaryKey, enum_column
from valtexa.models.enums import (
    ApplicationState,
    ProductStatus,
    TankStatus,
    VerificationConclusion,
)


class Product(UUIDPrimaryKey, TenantScoped, Timestamped, Base):
    """Um defensivo, fertilizante foliar ou biológico cadastrado."""

    __tablename__ = "product"

    name: Mapped[str] = mapped_column(String(160), nullable=False)
    manufacturer: Mapped[str | None] = mapped_column(String(160))
    active_ingredient: Mapped[str | None] = mapped_column(String(255))
    registration_number: Mapped[str | None] = mapped_column(
        String(64), doc="Registro no MAPA. Ausente bloqueia a aplicação em modo estrito."
    )
    status: Mapped[ProductStatus] = mapped_column(
        enum_column(ProductStatus), default=ProductStatus.ACTIVE, nullable=False
    )

    allowed_crops: Mapped[list] = mapped_column(
        nullable=False,
        default=list,
        doc="Culturas em que o uso é autorizado: ['corn']. Vazio significa nenhuma.",
    )
    authorized_targets: Mapped[list] = mapped_column(
        nullable=False,
        default=list,
        doc="Alvos autorizados, no vocabulário do modelo: ['Common_Rust', 'Blight'].",
    )
    default_rate_l_ha: Mapped[float | None] = mapped_column(Float)
    min_rate_l_ha: Mapped[float | None] = mapped_column(Float)
    max_rate_l_ha: Mapped[float | None] = mapped_column(Float)
    reentry_interval_h: Mapped[float | None] = mapped_column(
        Float, doc="Intervalo de reentrada. O rover de verificação respeita este prazo."
    )
    preharvest_interval_days: Mapped[int | None] = mapped_column(Integer)
    max_wind_ms: Mapped[float | None] = mapped_column(
        Float, doc="Vento máximo da bula. Quando nulo vale o limite global da plataforma."
    )
    notes: Mapped[str | None] = mapped_column(Text)

    batches: Mapped[list[ProductBatch]] = relationship(
        back_populates="product", cascade="all, delete-orphan", passive_deletes=True
    )


class ProductBatch(UUIDPrimaryKey, TenantScoped, Timestamped, Base):
    """Um lote físico, com validade própria."""

    __tablename__ = "product_batch"
    __table_args__ = (UniqueConstraint("product_id", "code", name="uq_batch_product_code"),)

    product_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("product.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_on: Mapped[date | None] = mapped_column(Date)
    quantity_l: Mapped[float | None] = mapped_column(Float)
    received_on: Mapped[date | None] = mapped_column(Date)

    product: Mapped[Product] = relationship(back_populates="batches")

    def is_expired(self, today: date) -> bool:
        return self.expires_on is not None and self.expires_on < today


class Tank(UUIDPrimaryKey, TenantScoped, Timestamped, Base):
    """Um reservatório físico de um dispositivo.

    Cada tanque tem identidade própria porque um drone com dois tanques pode
    carregar produtos diferentes — e a missão precisa dizer de qual deles sai a
    calda.
    """

    __tablename__ = "tank"
    __table_args__ = (UniqueConstraint("device_id", "index", name="uq_tank_device_index"),)

    device_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("device.id", ondelete="CASCADE"), nullable=False, index=True
    )
    index: Mapped[int] = mapped_column(Integer, nullable=False, doc="Posição física: 0, 1, ...")
    label: Mapped[str | None] = mapped_column(String(64))
    capacity_l: Mapped[float] = mapped_column(Float, nullable=False)
    current_level_l: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    status: Mapped[TankStatus] = mapped_column(
        enum_column(TankStatus), default=TankStatus.EMPTY, nullable=False
    )
    loaded_product_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("product.id"))
    loaded_batch_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("product_batch.id"))
    loaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    loaded_by: Mapped[str | None] = mapped_column(String(32), ForeignKey("user.id"))


class Application(UUIDPrimaryKey, TenantScoped, Timestamped, Base):
    """Um episódio real de aplicação: bico aberto, calda saindo.

    É o registro que vira comprovante para o produtor e prova para a
    fiscalização. Nunca é criado pela nuvem por conta própria: nasce do evento
    ``application_started`` que o drone reporta.
    """

    __tablename__ = "application"

    mission_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("mission.id"), nullable=False, index=True
    )
    device_id: Mapped[str] = mapped_column(String(32), ForeignKey("device.id"), nullable=False)
    tank_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("tank.id"))
    product_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("product.id"))
    product_batch_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("product_batch.id")
    )
    field_id: Mapped[str] = mapped_column(String(32), ForeignKey("field.id"), nullable=False)
    zone_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("zone.id"))

    state: Mapped[ApplicationState] = mapped_column(
        enum_column(ApplicationState), default=ApplicationState.STARTED, nullable=False, index=True
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    stopped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    amount_used_l: Mapped[float | None] = mapped_column(Float)
    area_ha: Mapped[float | None] = mapped_column(Float)
    mean_rate_l_ha: Mapped[float | None] = mapped_column(Float)
    track: Mapped[list] = mapped_column(
        default=list, doc="Trilha [[lon, lat, vazão], ...]. É o mapa de aplicação."
    )
    outside_polygon_points: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        doc=(
            "Pontos da trilha fora do polígono autorizado. Qualquer valor acima "
            "de zero é incidente e vira evento crítico."
        ),
    )
    stop_reason: Mapped[str | None] = mapped_column(String(120))
    verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class Verification(UUIDPrimaryKey, TenantScoped, Timestamped, Base):
    """A comparação antes/depois de um tratamento.

    A conclusão fica ``PENDING`` até existir observação posterior de fato. A
    plataforma não declara que o tratamento funcionou sem uma segunda passada
    do rover: eficácia sem evidência é exatamente o que faria o produtor perder
    a confiança no sistema inteiro.
    """

    __tablename__ = "verification"

    application_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("application.id", ondelete="CASCADE"), nullable=False, index=True
    )
    verification_mission_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("mission.id")
    )
    field_id: Mapped[str] = mapped_column(String(32), ForeignKey("field.id"), nullable=False)
    zone_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("zone.id"))

    scheduled_for: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), doc="Respeita o intervalo de reentrada do produto."
    )
    before_ratio: Mapped[float | None] = mapped_column(
        Float, doc="Fração de observações com o alvo, antes."
    )
    after_ratio: Mapped[float | None] = mapped_column(Float)
    before_sample: Mapped[int | None] = mapped_column(Integer)
    after_sample: Mapped[int | None] = mapped_column(Integer)
    effectiveness: Mapped[float | None] = mapped_column(
        Float, doc="Redução relativa da incidência, em [-1, 1]. Negativo é piora."
    )
    conclusion: Mapped[VerificationConclusion] = mapped_column(
        enum_column(VerificationConclusion),
        default=VerificationConclusion.PENDING,
        nullable=False,
        index=True,
    )
    model_version: Mapped[str | None] = mapped_column(String(64))
    notes: Mapped[str | None] = mapped_column(Text)
