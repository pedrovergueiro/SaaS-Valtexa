"""Dataset proprietário da ValTexa e o catálogo de versões de modelo.

O que dá valor à plataforma não é o classificador: é o dataset rotulado por
agrônomo que sai da operação. Cada correção humana numa fila de revisão é uma
amostra que nenhum dataset público tem — inclusive, e principalmente, de doença
e praga **fora do catálogo do modelo**, que é o modo de falha medido em
``VALTEXA-B/MODELS.md``.

O desenho separa três coisas que costumam ser confundidas:

**Amostra** (:class:`DatasetSample`) é a anotação de um agrônomo sobre uma
imagem: o rótulo dele, quem é ele, quando escreveu, e o que a máquina tinha
dito. Nasce ``CANDIDATE`` e é imutável em essência — rever o rótulo cria estado
``EXCLUDED`` e uma amostra nova, nunca um ``UPDATE`` por cima.

**Versão** (:class:`DatasetVersion`) é um corte congelado: "estas 4.812 amostras,
neste dia". É o que se treina e o que se cita num artigo. Sem congelar, dois
treinos com o mesmo nome de dataset não são comparáveis.

**Versão de modelo** (:class:`ModelVersion`) é o que foi treinado sobre um corte,
com a métrica que atingiu. A ligação ``ModelVersion.dataset_version_id`` é o que
torna possível responder, seis meses depois, de que dados veio a resposta que o
produtor recebeu.

**Não se treina a cada correção.** Uma anotação entra no dataset; o treino roda
sobre um corte fechado. Esta é a separação que impede a plataforma de reagir a
um rótulo isolado — o mesmo princípio que impede um diagnóstico isolado de virar
aplicação.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from valtexa.models.base import Base, TenantScoped, Timestamped, UUIDPrimaryKey, enum_column
from valtexa.models.enums import (
    CapturePlatform,
    DatasetSampleState,
    ModelVersionState,
    ReleaseScope,
)


class Dataset(UUIDPrimaryKey, Timestamped, Base):
    """Um conjunto de treinamento da ValTexa.

    Não é multi-tenant: o dataset é da plataforma, alimentado pela operação de
    vários clientes. As amostras carregam o ``tenant_id`` de origem, o que
    mantém a rastreabilidade e permite atender um pedido de exclusão de dados
    sem desmontar o conjunto inteiro.
    """

    __tablename__ = "dataset"

    key: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
        index=True,
        doc="Casa com o modelo de VALTEXA-B que se pretende treinar: 'coffee-foliar'.",
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    crop: Mapped[str] = mapped_column(String(64), nullable=False)
    platform: Mapped[CapturePlatform] = mapped_column(
        enum_column(CapturePlatform),
        nullable=False,
        doc="Aérea e de solo não se misturam no mesmo conjunto. Ver VALTEXA-B/MODELS.md.",
    )
    description: Mapped[str | None] = mapped_column(Text)

    samples: Mapped[list[DatasetSample]] = relationship(
        back_populates="dataset", cascade="all, delete-orphan", passive_deletes=True
    )
    versions: Mapped[list[DatasetVersion]] = relationship(
        back_populates="dataset", cascade="all, delete-orphan", passive_deletes=True
    )


class DatasetSample(UUIDPrimaryKey, Timestamped, Base):
    """Uma imagem anotada por um agrônomo, pronta para entrar num corte.

    ``label`` é livre de propósito: o valor da amostra está justamente em poder
    receber um nome que o modelo não conhece. Restringir a lista de rótulos ao
    catálogo do classificador fecharia o único caminho pelo qual uma doença nova
    entra no dataset.
    """

    __tablename__ = "dataset_sample"
    __table_args__ = (
        # A mesma imagem não entra duas vezes no mesmo dataset. O diagnóstico é
        # a origem da anotação, e um diagnóstico rende no máximo uma amostra.
        UniqueConstraint("dataset_id", "diagnosis_id", name="uq_dataset_sample_diagnosis"),
    )

    dataset_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("dataset.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tenant_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("tenant.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        doc="Cliente de origem. Não filtra leitura do dataset; serve à rastreabilidade.",
    )
    asset_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("asset.id", ondelete="CASCADE"), nullable=False, index=True
    )
    observation_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("observation.id", ondelete="SET NULL")
    )
    diagnosis_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("diagnosis.id", ondelete="SET NULL"), index=True
    )
    collection_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("collection.id", ondelete="SET NULL"), index=True
    )

    label: Mapped[str] = mapped_column(
        String(120), nullable=False, index=True, doc="O rótulo do agrônomo. Pode ser inédito."
    )
    machine_label: Mapped[str | None] = mapped_column(
        String(120), doc="O que o modelo dizia. Guardado para medir onde ele erra."
    )
    machine_confidence: Mapped[float | None] = mapped_column(Float)
    disagreed: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
        index=True,
        doc="Humano contradisse a máquina. É o subconjunto mais valioso do dataset.",
    )

    reviewer_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("user.id", ondelete="SET NULL"), index=True
    )
    reviewer_label: Mapped[str | None] = mapped_column(
        String(255), doc="E-mail do revisor no momento da anotação. Sobrevive à exclusão da conta."
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)

    state: Mapped[DatasetSampleState] = mapped_column(
        enum_column(DatasetSampleState),
        default=DatasetSampleState.CANDIDATE,
        nullable=False,
        index=True,
    )

    dataset: Mapped[Dataset] = relationship(back_populates="samples")


class DatasetVersion(UUIDPrimaryKey, Timestamped, Base):
    """Um corte congelado do dataset: o que foi para um treino.

    ``sample_ids`` guarda a lista exata de amostras do corte. Guardar a lista, e
    não um filtro por data, é o que torna o corte reproduzível: amostras podem
    ser excluídas depois, e um corte definido por consulta mudaria de conteúdo
    com o tempo.
    """

    __tablename__ = "dataset_version"
    __table_args__ = (UniqueConstraint("dataset_id", "version", name="uq_dataset_version"),)

    dataset_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("dataset.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[str] = mapped_column(String(32), nullable=False, doc="'v3', '2026.09.1'.")
    sample_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    label_counts: Mapped[dict] = mapped_column(
        default=dict, nullable=False, doc="Rótulo para quantidade. O desbalanceamento fica à vista."
    )
    sample_ids: Mapped[list] = mapped_column(default=list, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    criterio: Mapped[dict] = mapped_column(
        default=dict, nullable=False,
        doc="Quem entrou e por quê: a política (um, consenso, confiabilidade) e o que ficou fora.")
    frozen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    frozen_by: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("user.id", ondelete="SET NULL")
    )

    dataset: Mapped[Dataset] = relationship(back_populates="versions")


class ModelVersion(UUIDPrimaryKey, Timestamped, Base):
    """Uma versão de modelo no Model Registry (brief, seção 9).

    É a fonte da verdade sobre quais modelos existem e quais podem atender: o
    pipeline de análise (:mod:`valtexa.services.ai_pipeline`) resolve o modelo de
    um talhão lendo esta tabela, e o robô pergunta aqui qual modelo deve rodar —
    um robô nunca recebe modelo que não esteja nela em PRODUÇÃO.

    A plataforma **não treina** nem guarda pesos: ``original_artifact_*`` e
    ``optimized_artifact_*`` apontam para onde o artefato vive e com qual hash. O
    original e o otimizado (dNATY) ficam separados, como pede a seção 23.
    ``Detection.model_version`` grava o texto; aqui fica o que esse texto significa.
    """

    __tablename__ = "model_version"
    __table_args__ = (UniqueConstraint("model_key", "version", name="uq_model_version"),)

    model_key: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True, doc="'coffee-foliar', 'banana-foliar-cc'."
    )
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str | None] = mapped_column(String(160))
    state: Mapped[ModelVersionState] = mapped_column(
        enum_column(ModelVersionState),
        default=ModelVersionState.TREINAMENTO,
        nullable=False,
        index=True,
    )
    platform: Mapped[CapturePlatform] = mapped_column(
        enum_column(CapturePlatform), nullable=False
    )
    crop: Mapped[str | None] = mapped_column(String(64), doc="Cultura principal (rótulo).")
    crops: Mapped[list] = mapped_column(
        default=list,
        nullable=False,
        doc="Nomes da cultura que este modelo atende, em minúsculas ('café', 'cafe', 'coffee').",
    )
    problem: Mapped[str | None] = mapped_column(String(160), doc="Ex.: 'doença foliar'.")
    architecture: Mapped[str | None] = mapped_column(String(120))
    dataset_version_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("dataset_version.id", ondelete="SET NULL"), index=True
    )
    dataset_ref: Mapped[str | None] = mapped_column(
        String(255), doc="Dataset externo (fora deste banco): nome, versão, licença."
    )
    trained_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    metrics: Mapped[dict] = mapped_column(
        default=dict,
        nullable=False,
        doc="precision, recall, f1, map, fp, fn, acurácia de campo — só a equipe vê.",
    )
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    flops: Mapped[int | None] = mapped_column(BigInteger)
    latency_ms: Mapped[float | None] = mapped_column(Float)
    memory_mb: Mapped[float | None] = mapped_column(Float)
    target_hardware: Mapped[str | None] = mapped_column(String(120))
    original_artifact_uri: Mapped[str | None] = mapped_column(String(512))
    original_artifact_sha256: Mapped[str | None] = mapped_column(String(64))
    optimized_artifact_uri: Mapped[str | None] = mapped_column(String(512))
    optimized_artifact_sha256: Mapped[str | None] = mapped_column(String(64))
    optimized_size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    extras_manifest_sha256: Mapped[str | None] = mapped_column(
        String(64),
        doc="SHA-256 do manifesto dos arquivos que viajam ao lado do ONNX (perfil, cabeça, "
        "conformal...). O robô confere cada arquivo por ele; nulo = só o ONNX é conferido.",
    )
    dnaty_version: Mapped[str | None] = mapped_column(
        String(32), doc="Versão do dNATY que gerou o artefato otimizado (licença BSL 1.1)."
    )
    variant: Mapped[str] = mapped_column(
        String(32), default="padrão", nullable=False, doc="'campo', 'comercial'."
    )
    recommended: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    license: Mapped[str | None] = mapped_column(String(255), doc="Licença dos dados de treino.")
    caveat: Mapped[str | None] = mapped_column(Text, doc="Limitação conhecida, em português.")
    release_scope: Mapped[ReleaseScope] = mapped_column(
        enum_column(ReleaseScope), default=ReleaseScope.TODOS, nullable=False
    )
    notes: Mapped[str | None] = mapped_column(Text)
    registered_by: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("user.id", ondelete="SET NULL")
    )
    approved_by: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("user.id", ondelete="SET NULL")
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    promoted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), doc="Data de publicação: quando entrou em PRODUÇÃO."
    )
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ModelRelease(UUIDPrimaryKey, TenantScoped, Timestamped, Base):
    """Um modelo liberado para um cliente.

    Vale para a linha do modelo (``model_key``), não para uma versão: quando a
    versão nova entra em PRODUÇÃO, o cliente que tinha a anterior continua
    atendido. Só conta para versões com ``release_scope = clientes``; as de
    escopo ``todos`` atendem qualquer cliente. Revogar não apaga: grava
    ``revoked_at`` e quem revogou.
    """

    __tablename__ = "model_release"

    model_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    reason: Mapped[str | None] = mapped_column(Text)
    released_by: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("user.id", ondelete="SET NULL")
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_by: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("user.id", ondelete="SET NULL")
    )


class ModelOptimization(UUIDPrimaryKey, Timestamped, Base):
    """Uma rodada da etapa de otimização (dNATY) de uma versão (brief, seção 23).

    Guarda **toda** tentativa, aceita ou não: o benchmark do original e o do
    otimizado (precisão, recall, F1, latência, FPS, memória, tamanho, FLOPs), o
    critério de aceite usado, a comparação e o veredito com os motivos. Só uma
    tentativa **aceita** leva o artefato otimizado para a versão
    (``ModelVersion.optimized_artifact_*``); o original nunca é substituído — os
    dois ficam separados. O veredito é recalculado pelo registry a partir dos
    números (:mod:`valtexa.services.dnaty`), não copiado do relatório.
    """

    __tablename__ = "model_optimization"

    model_version_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("model_version.id", ondelete="CASCADE"), nullable=False,
        index=True,
    )
    tool: Mapped[str] = mapped_column(String(64), nullable=False)
    tool_version: Mapped[str | None] = mapped_column(String(32))
    dnaty_version: Mapped[str | None] = mapped_column(String(32))
    parameters: Mapped[dict] = mapped_column(default=dict, nullable=False)
    original_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    original_benchmark: Mapped[dict] = mapped_column(default=dict, nullable=False)
    optimized_artifact_uri: Mapped[str] = mapped_column(String(512), nullable=False)
    optimized_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    optimized_size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    optimized_benchmark: Mapped[dict] = mapped_column(default=dict, nullable=False)
    criterion: Mapped[dict] = mapped_column(default=dict, nullable=False)
    comparison: Mapped[dict] = mapped_column(default=dict, nullable=False)
    accepted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    reasons: Mapped[list] = mapped_column(default=list, nullable=False)
    license_note: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("user.id", ondelete="SET NULL")
    )


__all__ = [
    "Dataset", "DatasetSample", "DatasetVersion", "ModelOptimization", "ModelRelease",
    "ModelVersion",
]
