"""Resultado de ensaio de validação do Rover (ver ``valtexa.services.ensaios``).

Uma linha por ensaio terminado: o que o robô mediu (amostras brutas no comando de
origem) e o **veredito calculado aqui**, com os critérios da plataforma — o robô manda a
prévia dele (``laudo_robo``), que fica guardada só para comparar (``divergente``).

``origem``: ``rover`` (comando ``ensaio``), ``validacao_campo`` (FASE 5, a partir do
relatório Rover contra agrônomo) ou ``simulador``.
"""

from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from valtexa.models.base import Base, TenantScoped, Timestamped, UUIDPrimaryKey

STATUS = ("aprovado", "reprovado", "nao_avaliado", "cancelado", "erro")


class EnsaioResultado(UUIDPrimaryKey, TenantScoped, Timestamped, Base):
    __tablename__ = "ensaio_resultado"
    __table_args__ = (Index("ix_ensaio_resultado_device_ensaio", "device_id", "ensaio"),)

    device_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("device.id", ondelete="CASCADE"), nullable=False
    )
    command_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("device_command.id", ondelete="SET NULL")
    )
    ensaio: Mapped[str] = mapped_column(String(32), nullable=False)
    fase: Mapped[int] = mapped_column(Integer, nullable=False)
    origem: Mapped[str] = mapped_column(String(16), nullable=False, default="rover")
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    aprovado: Mapped[bool | None] = mapped_column(Boolean)
    params: Mapped[dict] = mapped_column(default=dict)
    criterios: Mapped[list] = mapped_column(default=list)
    medidas: Mapped[dict] = mapped_column(default=dict)
    laudo_robo: Mapped[dict | None] = mapped_column(
        doc="A prévia do robô (status, aprovado, critérios), sem as amostras.")
    divergente: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    simulado: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    vale_portao: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    observacao: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str | None] = mapped_column(String(32), ForeignKey("user.id"))
