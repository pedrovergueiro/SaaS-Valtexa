"""A cópia 3D da lavoura: uma passada do rover por uma rua.

O rover anda pela **rua** — a entrelinha — e o sensor lateral (LiDAR ou câmera
estéreo) enxerga as linhas de plantio dos dois lados. Cada passada vira um
``RowScan``: as plantas que o robô mediu (posição, altura, diâmetro de copa) e,
quando o hardware captura, a nuvem de pontos daquele trecho.

A cópia do talhão não é um arquivo: é a composição das passadas mais recentes.
Cada rua que o rover percorre substitui aquele pedaço da cópia — o que ele ainda
não percorreu fica em branco, e é isso que o console mostra. Ver
:mod:`valtexa.services.scene`.

As posições vêm em metros, num plano local com origem em ``origin_lon``/
``origin_lat`` (x para leste, y para norte, z para cima). Metro local, e não
grau, porque é a unidade em que o sensor mede e porque um centímetro em graus
decimais é a sétima casa — o JSON triplicaria de tamanho para dizer o mesmo.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from valtexa.models.base import Base, TenantScoped, Timestamped, UUIDPrimaryKey


class RowScan(UUIDPrimaryKey, TenantScoped, Timestamped, Base):
    """Uma passada do rover por uma rua, com o que o sensor 3D mediu."""

    __tablename__ = "row_scan"
    __table_args__ = (
        Index("ix_row_scan_field_time", "field_id", "captured_at"),
        # O upload é pesado e o enlace da lavoura cai: reenviar a mesma passada
        # tem de ser seguro, e a sequência do robô é a identidade dela.
        UniqueConstraint("device_id", "sequence_number", name="uq_row_scan_device_seq"),
    )

    farm_id: Mapped[str] = mapped_column(String(32), ForeignKey("farm.id"), nullable=False)
    field_id: Mapped[str] = mapped_column(String(32), ForeignKey("field.id"), nullable=False)
    mission_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("mission.id", ondelete="SET NULL"), index=True
    )
    device_id: Mapped[str] = mapped_column(String(32), ForeignKey("device.id"), nullable=False)
    sequence_number: Mapped[int] = mapped_column(BigInteger, nullable=False)
    segment_index: Mapped[int | None] = mapped_column(
        Integer, doc="O segmento da missão que esta passada executou."
    )
    row_index: Mapped[int | None] = mapped_column(
        Integer, doc="Número da rua, quando o rover consegue contar as linhas."
    )

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, doc="Fim da passada."
    )
    sensor: Mapped[str] = mapped_column(String(32), nullable=False, default="lidar")

    origin_lat: Mapped[float] = mapped_column(Float, nullable=False)
    origin_lon: Mapped[float] = mapped_column(Float, nullable=False)
    origin_alt_m: Mapped[float | None] = mapped_column(Float)
    path: Mapped[list] = mapped_column(
        nullable=False, default=list, doc="O eixo percorrido, [[lon, lat], ...]."
    )
    reach_m: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        doc=(
            "Alcance lateral do sensor, a partir do eixo. É o que define a faixa "
            "que esta passada atualiza na cópia: o que estava ali antes e não "
            "apareceu agora deixou de existir."
        ),
    )
    length_m: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    plants: Mapped[list] = mapped_column(
        nullable=False,
        default=list,
        doc="[[x, y, altura_m, copa_m], ...] em metros a partir da origem.",
    )
    plant_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    mean_height_m: Mapped[float | None] = mapped_column(Float)
    max_height_m: Mapped[float | None] = mapped_column(Float)

    pointcloud_asset_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("asset.id"))
    point_count: Mapped[int | None] = mapped_column(Integer)
