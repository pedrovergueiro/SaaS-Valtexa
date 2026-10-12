"""Atualização remota (OTA) do Rover — brief, seção 24.

* :class:`OtaPackage` — um pacote publicado: tipo (``runtime``, ``edge_ai``,
  ``model``, ``config``), versão, SHA-256 e tamanho do arquivo (``.tar``), o
  manifesto (cada arquivo com o seu hash) e, para modelo, a versão do Model
  Registry que ele carrega. Os bytes ficam no armazenamento de objetos; o banco
  guarda só metadados. Pacote não se reescreve: versão nova é pacote novo.
* :class:`OtaDeployment` — o pacote destinado a **um** robô. Leva o envelope
  assinado (Ed25519, chave OTA da plataforma) que o robô confere antes de
  instalar, o estado que o robô vai informando e o histórico de estados.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from valtexa.models.base import Base, TenantScoped, Timestamped, UUIDPrimaryKey

OTA_KINDS = ("runtime", "edge_ai", "model", "config")

OTA_STATES = (
    "pendente", "baixando", "verificando", "instalando", "verificando_saude",
    "aplicada", "revertida", "falhou", "recusada", "cancelada",
)
"""``aplicada``, ``revertida``, ``falhou``, ``recusada`` e ``cancelada`` são finais."""

OTA_FINAL = frozenset({"aplicada", "revertida", "falhou", "recusada", "cancelada"})


class OtaPackage(UUIDPrimaryKey, Timestamped, Base):
    __tablename__ = "ota_package"
    __table_args__ = (UniqueConstraint("kind", "version", name="uq_ota_package_kind_version"),)

    kind: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    manifest: Mapped[dict] = mapped_column(default=dict, nullable=False)
    model_version_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("model_version.id", ondelete="SET NULL"), index=True
    )
    notes: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("user.id", ondelete="SET NULL")
    )


class OtaDeployment(UUIDPrimaryKey, TenantScoped, Timestamped, Base):
    __tablename__ = "ota_deployment"

    package_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("ota_package.id", ondelete="CASCADE"), nullable=False, index=True
    )
    device_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("device.id", ondelete="CASCADE"), nullable=False, index=True
    )
    state: Mapped[str] = mapped_column(String(24), nullable=False, default="pendente",
                                       index=True)
    detail: Mapped[str | None] = mapped_column(Text)
    envelope: Mapped[dict] = mapped_column(default=dict, nullable=False)
    history: Mapped[list] = mapped_column(default=list, nullable=False)
    bytes_served: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("user.id", ondelete="SET NULL")
    )


__all__ = ["OTA_FINAL", "OTA_KINDS", "OTA_STATES", "OtaDeployment", "OtaPackage"]
