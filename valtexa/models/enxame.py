"""O plano do enxame de um talhão (ver ``valtexa.services.enxame``).

Uma linha por plano calculado. O mais novo de um talhão é o ``ativo``; o anterior passa a
``substituido`` — fica para responder "por que o Rover 2 foi para a rua 14 na terça".
``entradas_sha256`` é a impressão do que o plano leu (frota e tarefas): se a frota mudou
desde então, o plano está desatualizado e a leitura diz isso.
"""

from __future__ import annotations

from sqlalchemy import ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from valtexa.models.base import Base, TenantScoped, Timestamped, UUIDPrimaryKey

ESTADOS = ("ativo", "substituido")


class PlanoDoEnxame(UUIDPrimaryKey, TenantScoped, Timestamped, Base):
    __tablename__ = "plano_enxame"
    __table_args__ = (Index("ix_plano_enxame_field_estado", "field_id", "estado"),)

    farm_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("farm.id", ondelete="CASCADE"), nullable=False
    )
    field_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("field.id", ondelete="CASCADE"), nullable=False
    )
    versao: Mapped[int] = mapped_column(Integer, nullable=False)
    estado: Mapped[str] = mapped_column(String(16), nullable=False, default="ativo")
    entradas_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    entradas: Mapped[dict] = mapped_column(default=dict)
    plano: Mapped[dict] = mapped_column(default=dict)
    created_by: Mapped[str | None] = mapped_column(String(32), ForeignKey("user.id"))
