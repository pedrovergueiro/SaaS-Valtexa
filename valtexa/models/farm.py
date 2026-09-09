"""Geografia da lavoura: fazenda, talhão e zona.

Os limites são polígonos guardados como JSON — uma lista de pares
``[longitude, latitude]`` em WGS84, sem repetir o primeiro ponto no fim. Não há
PostGIS: as operações de que a plataforma precisa (ponto dentro do polígono,
área, distância) estão em :mod:`valtexa.services.geo`, são determinísticas e
testáveis, e rodam igual em SQLite e em Postgres.

Quando o volume justificar índice espacial, o caminho é migrar a coluna para
``geography(Polygon, 4326)`` mantendo o mesmo contrato de leitura.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import Date, Float, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from valtexa.models.base import Base, TenantScoped, Timestamped, UUIDPrimaryKey


class Farm(UUIDPrimaryKey, TenantScoped, Timestamped, Base):
    """Uma propriedade. É a unidade que tem base, dock e frota."""

    __tablename__ = "farm"

    name: Mapped[str] = mapped_column(String(160), nullable=False)
    timezone: Mapped[str] = mapped_column(
        String(64), default="America/Sao_Paulo", nullable=False, doc="Fuso para exibição."
    )
    center_lat: Mapped[float] = mapped_column(Float, nullable=False)
    center_lon: Mapped[float] = mapped_column(Float, nullable=False)
    base_lat: Mapped[float | None] = mapped_column(
        Float, doc="Ponto de retorno padrão. Nulo enquanto a base não é instalada."
    )
    base_lon: Mapped[float | None] = mapped_column(Float)
    area_ha: Mapped[float | None] = mapped_column(Float)

    fields: Mapped[list[Field]] = relationship(
        back_populates="farm", cascade="all, delete-orphan", passive_deletes=True
    )


class Field(UUIDPrimaryKey, TenantScoped, Timestamped, Base):
    """Um talhão: a menor área com cultura, estágio e histórico próprios."""

    __tablename__ = "field"
    __table_args__ = (UniqueConstraint("farm_id", "name", name="uq_field_farm_name"),)

    farm_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("farm.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    crop: Mapped[str] = mapped_column(
        String(64), nullable=False, doc="Cultura: 'corn', 'coffee', 'soy'. Casa com allowed_crops."
    )
    variety: Mapped[str | None] = mapped_column(String(120))
    crop_stage: Mapped[str | None] = mapped_column(
        String(64), doc="Estágio fenológico: 'V6', 'VT', 'R3'. Entra na regra de decisão."
    )
    planted_on: Mapped[date | None] = mapped_column(Date)
    row_spacing_m: Mapped[float | None] = mapped_column(Float)
    area_ha: Mapped[float | None] = mapped_column(Float)
    boundary: Mapped[list] = mapped_column(
        nullable=False,
        default=list,
        doc="Polígono [[lon, lat], ...]. É o limite externo de toda missão neste talhão.",
    )

    farm: Mapped[Farm] = relationship(back_populates="fields")
    zones: Mapped[list[Zone]] = relationship(
        back_populates="field", cascade="all, delete-orphan", passive_deletes=True
    )


class Zone(UUIDPrimaryKey, TenantScoped, Timestamped, Base):
    """Subdivisão de manejo dentro do talhão.

    É onde a aplicação localizada acontece: o motor de decisão recomenda por
    zona, não pelo talhão inteiro, e é isso que separa este produto de uma
    pulverização em área total.
    """

    __tablename__ = "zone"

    field_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("field.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    boundary: Mapped[list] = mapped_column(nullable=False, default=list)
    area_ha: Mapped[float | None] = mapped_column(Float)

    field: Mapped[Field] = relationship(back_populates="zones")
