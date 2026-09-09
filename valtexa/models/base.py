"""Peças comuns a todas as tabelas.

Três decisões valem por todo o esquema:

* **Chave primária é UUID em texto.** Um identificador gerado no cliente permite
  que o robô crie a observação offline e sincronize depois sem renumerar nada.
* **Todo horário é UTC e ciente de fuso.** O robô, a nuvem e o produtor estão em
  relógios diferentes; converter para o fuso da fazenda é trabalho de exibição.
* **Quase tudo carrega ``tenant_id``.** É o eixo do isolamento entre clientes, e
  ele é verificado na consulta, não confiado no parâmetro da rota.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import ClassVar

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column
from sqlalchemy.types import JSON


class Base(DeclarativeBase):
    """Base declarativa com o mapeamento de tipos usado em todo o projeto."""

    type_annotation_map: ClassVar[dict] = {dict: JSON, list: JSON}


def new_id() -> str:
    """Identificador novo, sem hífens — cabe em URL e em payload de rádio."""
    return uuid.uuid4().hex


def utcnow() -> datetime:
    """Agora, em UTC e ciente de fuso."""
    return datetime.now(UTC)


def as_utc(value: datetime | None) -> datetime | None:
    """Devolve o horário em UTC.

    O SQLite não guarda o fuso: um ``datetime`` gravado com ``tzinfo`` volta da
    leitura sem ele. Comparar esse valor ingênuo com ``utcnow()`` levanta
    ``TypeError`` — e seria numa checagem de expiração de comando, o pior lugar
    possível para uma exceção. Aqui o horário volta a ser comparável.
    """
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def enum_column(enum_cls: type[Enum]) -> SAEnum:
    """Coluna de texto que aceita apenas os valores de ``enum_cls``.

    ``native_enum=False`` grava ``VARCHAR`` em vez de um tipo ``ENUM`` do banco, e
    ``values_callable`` faz gravar o *valor* (``"ai_validated"``) em vez do nome
    (``"AI_VALIDATED"``) — um ``SELECT`` cru continua legível.

    Sem ``create_constraint``: um ``CHECK`` no banco obrigaria uma migração para
    cada rótulo novo, e o vocabulário do domínio ainda vai crescer. A validação
    acontece no SQLAlchemy, na escrita e na leitura.
    """
    return SAEnum(
        enum_cls,
        native_enum=False,
        validate_strings=True,
        values_callable=lambda cls: [member.value for member in cls],
    )


class UUIDPrimaryKey:
    """Mixin da chave primária.

    O identificador é atribuído **na construção do objeto**, não no ``flush``.
    A diferença importa: quase toda escrita do domínio grava uma entrada de
    auditoria ou publica um evento apontando para a linha recém-criada, e com o
    padrão só do banco esse identificador ainda seria ``None`` naquele momento.
    Atribuir aqui elimina a classe inteira de bugs em que o rastro aponta para
    lugar nenhum.
    """

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)

    def __init__(self, **kwargs: object) -> None:
        kwargs.setdefault("id", new_id())
        super().__init__(**kwargs)


class Timestamped:
    """Mixin de criação e atualização."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class TenantScoped:
    """Mixin do isolamento multi-tenant.

    A coluna é ``NOT NULL`` e indexada porque toda consulta do produto filtra por
    ela. Ver :func:`valtexa.api.deps.scoped` — nenhuma leitura do domínio deve
    montar um ``select`` sem esse filtro.

    Usa ``declared_attr`` porque um mesmo objeto ``ForeignKey`` não pode ser
    compartilhado entre tabelas: cada classe precisa da sua própria instância.
    """

    @declared_attr
    @classmethod
    def tenant_id(cls) -> Mapped[str]:
        return mapped_column(
            String(32), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False, index=True
        )
