"""Planejamento de apoio à decisão (8.3): o plano proposto e a revisão humana.

Duas tabelas, nenhuma muda o que já existe:

* ``plano_apoio`` — um plano **proposto** (fitossanitário, robótico ou de insumos), com o
  pedido, as **premissas registradas** (cada número que não foi medido diz de onde veio), o
  resultado e o ``sha256`` dos três. **Imutável**: pedir de novo cria outro plano.
* ``revisao_plano_apoio`` — o que a pessoa responsável achou (aceito, recusado, ajustar),
  com quem, quando, papel e o hash revisado. **Não autoriza nada**: aceitar um plano não
  cria missão, não aprova prescrição nem aplicação e não muda limiar de modelo
  (Princípio de Ouro, ``docs/SEGURANCA.md``).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from valtexa.models.base import Base, TenantScoped, Timestamped, UUIDPrimaryKey

TIPOS_PLANO = ("fitossanitario", "robotico", "insumos")
DECISOES_PLANO = ("aceito", "recusado", "ajustar")


class PlanoDeApoio(UUIDPrimaryKey, TenantScoped, Timestamped, Base):
    __tablename__ = "plano_apoio"
    __table_args__ = (Index("ix_plano_apoio_tipo_field", "tipo", "field_id"),)

    tipo: Mapped[str] = mapped_column(String(16), nullable=False)
    farm_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("farm.id", ondelete="CASCADE")
    )
    field_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("field.id", ondelete="CASCADE")
    )
    versao_motor: Mapped[str] = mapped_column(String(32), nullable=False)
    pedido: Mapped[dict] = mapped_column(default=dict)
    premissas: Mapped[list] = mapped_column(
        default=list, doc="[{codigo, texto, valor, origem}] — origem: padrao, pedido, medido, "
                          "simulado, cadastro."
    )
    resultado: Mapped[dict] = mapped_column(default=dict)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    estado: Mapped[str] = mapped_column(String(24), nullable=False, default="proposto")
    gerado_por: Mapped[str | None] = mapped_column(String(32), ForeignKey("user.id"))


class RevisaoPlanoDeApoio(UUIDPrimaryKey, TenantScoped, Timestamped, Base):
    __tablename__ = "revisao_plano_apoio"

    plano_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("plano_apoio.id", ondelete="CASCADE"), nullable=False, index=True
    )
    revisor_id: Mapped[str] = mapped_column(String(32), ForeignKey("user.id"), nullable=False)
    papel: Mapped[str] = mapped_column(String(24), nullable=False)
    decisao: Mapped[str] = mapped_column(String(16), nullable=False)
    comentario: Mapped[str | None] = mapped_column(Text)
    plano_sha256: Mapped[str] = mapped_column(
        String(64), nullable=False, doc="O plano exatamente como foi revisado."
    )
    revisado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
