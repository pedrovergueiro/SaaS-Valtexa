"""Coletas: um lote de arquivos que entrou na plataforma de uma vez.

É a unidade que o MVP inteiro gira em torno. Um operador terceirizado voa o
talhão, entrega os arquivos, e alguém da ValTexa importa esse lote pelo painel
administrativo. A coleta é o que dá nome, data, origem e rastro a esse lote —
sem ela um arquivo solto no armazenamento não diz de onde veio nem a que talhão
pertence.

Três decisões valem explicar:

**O código é humano, o identificador é UUID.** ``COL-2026-000001`` é o que
aparece no painel, no e-mail e na conversa com o operador; a chave primária
continua sendo UUID, como em todo o esquema. O código é único por ano, dentro do
cliente.

**O arquivo original nunca é sobrescrito.** :class:`CollectionFile` guarda o
``sha256`` declarado pelo remetente e o conferido na recepção. Divergiu, o
arquivo é recusado e o byte já gravado não substitui nada — o armazenamento é
endereçado por conteúdo (ver :mod:`valtexa.services.storage`), então dois
arquivos diferentes nunca ocupam a mesma chave.

**O upload é retomável por construção.** ``received_bytes`` é a única coisa que
o cliente precisa perguntar para saber de onde continuar. Não há tabela de
partes: o servidor aceita um pedaço no deslocamento que já tem e recusa qualquer
outro, o que torna a retomada trivial e o estado impossível de ficar furado.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import BigInteger, Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from valtexa.models.base import Base, TenantScoped, Timestamped, UUIDPrimaryKey, enum_column
from valtexa.models.enums import (
    CapturePlatform,
    CollectionFileState,
    CollectionKind,
    CollectionSource,
    CollectionState,
)


class Collection(UUIDPrimaryKey, TenantScoped, Timestamped, Base):
    """Um lote de arquivos de um talhão, com data, origem e destino."""

    __tablename__ = "collection"

    code: Mapped[str] = mapped_column(
        String(24), nullable=False, index=True, doc="COL-2026-000001. Único por cliente."
    )
    farm_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("farm.id", ondelete="CASCADE"), nullable=False, index=True
    )
    field_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("field.id", ondelete="CASCADE"), nullable=False, index=True
    )

    collected_on: Mapped[date] = mapped_column(
        Date, nullable=False, doc="Data do voo/percurso, não a do upload."
    )
    source: Mapped[CollectionSource] = mapped_column(enum_column(CollectionSource), nullable=False)
    kind: Mapped[CollectionKind] = mapped_column(enum_column(CollectionKind), nullable=False)
    platform: Mapped[CapturePlatform] = mapped_column(
        enum_column(CapturePlatform),
        nullable=False,
        doc="Derivada de kind. É ela que escolhe o modelo — ver services/collections.py.",
    )
    state: Mapped[CollectionState] = mapped_column(
        enum_column(CollectionState), default=CollectionState.DRAFT, nullable=False, index=True
    )

    operator_name: Mapped[str | None] = mapped_column(
        String(160), doc="Empresa/piloto que fez o voo. Texto livre: é dado de terceiro."
    )
    notes: Mapped[str | None] = mapped_column(Text)

    # --- contadores, mantidos por services/collections.py -----------------------
    # Ficam desnormalizados de propósito: o painel mostra a barra de progresso de
    # uma coleta com milhares de arquivos a cada poucos segundos, e um COUNT por
    # estado a cada atualização é o tipo de consulta que só dói em produção.
    file_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    bytes_total: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    bytes_received: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    files_stored: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    files_processed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    files_analyzed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    files_needs_review: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    files_no_model: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    files_failed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    model_key: Mapped[str | None] = mapped_column(
        String(64), doc="Modelo que o pipeline resolveu para esta coleta. Nulo: nenhum atende."
    )
    no_model_reason: Mapped[str | None] = mapped_column(
        Text, doc="Por que nenhum modelo atende. Vai inteiro para o painel e para o cliente."
    )

    upload_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    processing_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    processing_finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    released_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), doc="Quando ficou visível ao cliente."
    )

    created_by: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("user.id", ondelete="SET NULL"), index=True
    )
    released_by: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("user.id", ondelete="SET NULL")
    )

    files: Mapped[list[CollectionFile]] = relationship(
        back_populates="collection", cascade="all, delete-orphan", passive_deletes=True
    )

    @property
    def is_visible_to_client(self) -> bool:
        """Se o cliente pode ver esta coleta.

        O cliente não acompanha upload nem fila: para ele a coleta existe quando
        tem resultado. A complexidade operacional fica no painel da ValTexa.
        """
        return self.state is CollectionState.AVAILABLE_TO_CLIENT


class CollectionFile(UUIDPrimaryKey, TenantScoped, Timestamped, Base):
    """Um arquivo da coleta, do registro ao resultado da análise."""

    __tablename__ = "collection_file"

    collection_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("collection.id", ondelete="CASCADE"), nullable=False, index=True
    )
    filename: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        doc="Nome original, preservado para o operador se reconhecer. Nunca vira caminho.",
    )
    content_type: Mapped[str] = mapped_column(String(80), nullable=False)
    size_bytes: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        doc="Tamanho declarado. BigInteger porque um ortomosaico passa de 2 GB.",
    )
    sha256_declared: Mapped[str | None] = mapped_column(
        String(64), doc="Opcional. Quando vem, é conferido na recepção."
    )
    sha256: Mapped[str | None] = mapped_column(
        String(64), doc="Conferido sobre os bytes recebidos."
    )
    received_bytes: Mapped[int] = mapped_column(
        BigInteger, default=0, nullable=False, doc="De onde o upload continua."
    )

    state: Mapped[CollectionFileState] = mapped_column(
        enum_column(CollectionFileState),
        default=CollectionFileState.REGISTERED,
        nullable=False,
        index=True,
    )
    error: Mapped[str | None] = mapped_column(Text)

    # --- metadados de captura, quando o operador os entrega ---------------------
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lat: Mapped[float | None] = mapped_column(Float)
    lon: Mapped[float | None] = mapped_column(Float)
    alt_m: Mapped[float | None] = mapped_column(Float)

    asset_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("asset.id", ondelete="SET NULL"), index=True
    )
    observation_id: Mapped[str | None] = mapped_column(
        String(32),
        ForeignKey("observation.id", ondelete="SET NULL"),
        index=True,
        doc="A observação criada a partir deste arquivo, quando houve análise.",
    )

    collection: Mapped[Collection] = relationship(back_populates="files")

    @property
    def is_complete(self) -> bool:
        return self.received_bytes >= self.size_bytes > 0


class ProcessingJob(UUIDPrimaryKey, TenantScoped, Timestamped, Base):
    """Trabalho pesado que o worker executa fora da requisição.

    O administrador fecha a aba depois de subir 1.500 imagens; o processamento
    continua. É a razão de existir desta tabela — e a razão de ela guardar
    ``attempts`` e ``last_error``: um trabalho que falha precisa poder ser
    reenfileirado sem que ninguém perca o que aconteceu antes.

    A posse é por ``locked_until``: o worker que reivindica o trabalho grava um
    prazo, e um processo que morra no meio não deixa o trabalho preso para
    sempre.
    """

    __tablename__ = "processing_job"

    kind: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    state: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    subject_type: Mapped[str] = mapped_column(String(32), nullable=False)
    subject_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)

    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text)

    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    locked_by: Mapped[str | None] = mapped_column(String(64))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    progress_done: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    progress_total: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    payload: Mapped[dict] = mapped_column(default=dict, nullable=False)


__all__ = ["Collection", "CollectionFile", "ProcessingJob"]
