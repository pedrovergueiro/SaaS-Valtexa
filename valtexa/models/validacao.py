"""Rótulo de campo por planta: a ficha do agrônomo nas fileiras de validação.

O Rover passa pelo talhão e a IA funde o que ele viu num diagnóstico por planta (ids da
fusão: ``L03-P0012``). Nas fileiras de validação (``Field.validation_rows``) o agrônomo
olha **cada** planta e anota o que ela tem — a verdade de campo. Com isso:

* o relatório **Rover contra agrônomo** (sensibilidade por planta, alarme falso nas sadias);
* o CSV ``field_id,plant_id,label,pass_id`` que recalibra a Edge AI e a fusão
  (``training.fit_edge fit --labels`` e ``training.fit_fusion fit --labels`` em VALTEXA-B,
  sobre o registro do Rover na IA);
* os recortes de campo para o treino (``training.import_campo`` em VALTEXA-B): plantas
  sadias dão recortes ``Healthy`` confiáveis; as doentes dão candidatos para revisão.

O rótulo é por planta **e** passada (missão): a mesma planta muda de uma semana para outra.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from valtexa.models.base import Base, TenantScoped, Timestamped, UUIDPrimaryKey


class PlantLabel(UUIDPrimaryKey, TenantScoped, Timestamped, Base):
    __tablename__ = "plant_label"
    __table_args__ = (
        UniqueConstraint("field_id", "mission_id", "plant_ref", name="uq_plant_label_planta"),
        Index("ix_plant_label_field_mission", "field_id", "mission_id"),
    )

    field_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("field.id", ondelete="CASCADE"), nullable=False
    )
    mission_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("mission.id", ondelete="CASCADE"), nullable=False,
        doc="A passada do Rover (missão) em que a planta foi avaliada.",
    )
    plant_ref: Mapped[str] = mapped_column(
        String(80), nullable=False, doc="O id da planta na fusão da IA (ex.: L03-P0012)."
    )
    row_ref: Mapped[str | None] = mapped_column(String(80))
    label: Mapped[str] = mapped_column(
        String(80), nullable=False,
        doc="Classe do modelo (Healthy, Rust, Leaf_Miner_Damage...) — o que a planta tem.",
    )
    incidence_percent: Mapped[float | None] = mapped_column(
        Float, doc="Fração de folhas com a doença, como o MIP mede (opcional)."
    )
    notes: Mapped[str | None] = mapped_column(Text)
    labeled_by: Mapped[str | None] = mapped_column(String(32), ForeignKey("user.id"))
    labeled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
