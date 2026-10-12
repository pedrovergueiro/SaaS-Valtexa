"""O que o Rover Runtime sincroniza: registros da Edge AI e uploads em chunks.

Brief, seções 16, 18, 38 e 52. O banco guarda **só metadados**; os bytes vão
para o armazenamento de objetos (:mod:`valtexa.services.storage`).

* :class:`EdgeRecord` — um resultado da Edge AI (metadados da seção 16) ou um
  evento do robô (seção 40). A chave natural é ``(device_id, record_id)``: o ID
  nasce no robô, e o mesmo registro enviado duas vezes vira **uma** linha. O
  ``sha256`` é o do JSON canônico do conteúdo; mesmo ID com outro hash é
  conflito, não reenvio.
* :class:`EdgeUpload` — um arquivo chegando em pedaços. A chave natural é
  ``(device_id, upload_id)``. Os chunks ficam na área de *staging*
  (:mod:`valtexa.services.edge_sync`) até o arquivo inteiro conferir com o hash
  declarado; aí vira :class:`~valtexa.models.perception.Asset` (deduplicado por
  cliente e hash) e o *staging* é apagado.
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


class EdgeRecord(UUIDPrimaryKey, TenantScoped, Base):
    __tablename__ = "edge_record"
    __table_args__ = (
        UniqueConstraint("device_id", "record_id", name="uq_edge_record_device_record"),
        Index("ix_edge_record_tenant_mission", "tenant_id", "mission_id"),
        # Painel e saúde da IA: "resultados deste cliente nas últimas 24 h" (Parte 9).
        Index("ix_edge_record_tenant_kind_time", "tenant_id", "kind", "occurred_at"),
        # Worker da fusão por planta: "resultados que ainda não foram para a fusão".
        Index("ix_edge_record_kind_fusion", "kind", "fusion_status"),
    )

    device_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("device.id", ondelete="CASCADE"), nullable=False, index=True
    )
    record_id: Mapped[str] = mapped_column(String(64), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, doc="result | event")
    type: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True,
        doc="Categoria do resultado (NORMAL, POSSIVEL_DOENCA...) ou tipo do evento (seção 40).",
    )
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    mission_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("mission.id", ondelete="SET NULL")
    )
    field_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("field.id", ondelete="SET NULL"), index=True
    )
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    severity: Mapped[str | None] = mapped_column(String(16))
    label: Mapped[str | None] = mapped_column(String(120))
    confidence: Mapped[float | None] = mapped_column(Float)
    model_key: Mapped[str | None] = mapped_column(String(64))
    model_version: Mapped[str | None] = mapped_column(String(64))
    lat: Mapped[float | None] = mapped_column(Float)
    lon: Mapped[float | None] = mapped_column(Float)
    payload: Mapped[dict] = mapped_column(default=dict)
    observation_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("observation.id", ondelete="SET NULL"), index=True,
        doc="A observação que a nuvem abriu para este evento (ponte Edge AI → IA de nuvem).",
    )
    fusion_status: Mapped[str | None] = mapped_column(
        String(16),
        doc=(
            "Resultado na fusão por planta da IA (``services.fusao_borda``): nulo = pendente; "
            "ok, duplicado, sem_geometria, sem_recortes, sem_talhao ou recusado."
        ),
    )
    fusion_detail: Mapped[str | None] = mapped_column(String(200))
    fused_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EdgeUpload(UUIDPrimaryKey, TenantScoped, Timestamped, Base):
    __tablename__ = "edge_upload"
    __table_args__ = (
        UniqueConstraint("device_id", "upload_id", name="uq_edge_upload_device_upload"),
    )

    device_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("device.id", ondelete="CASCADE"), nullable=False, index=True
    )
    upload_id: Mapped[str] = mapped_column(String(80), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    content_type: Mapped[str] = mapped_column(String(64), nullable=False)
    chunk_size: Mapped[int] = mapped_column(Integer, nullable=False)
    total_chunks: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, doc="receiving | complete")
    record_id: Mapped[str | None] = mapped_column(String(64), index=True)
    role: Mapped[str | None] = mapped_column(String(32))
    tier: Mapped[str | None] = mapped_column(String(16))
    priority: Mapped[int | None] = mapped_column(Integer)
    asset_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("asset.id", ondelete="SET NULL")
    )
    deduplicated: Mapped[bool] = mapped_column(default=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
