"""Da imagem à recomendação: observação, detecção, diagnóstico, decisão, segurança.

A cadeia é deliberadamente longa e cada elo grava uma linha própria:

``Observation`` (o que foi visto)
→ ``Detection`` (o palpite de *cada* analisador, separado)
→ ``Diagnosis`` (o que sobrou depois da dupla validação)
→ ``Decision`` (o que se recomenda fazer)
→ ``SafetyEvaluation`` (se é permitido fazer)

Nenhum elo sobrescreve o anterior. Reprocessar uma imagem com um modelo novo
cria um ``Diagnosis`` novo; o antigo continua lá, com a versão do modelo que o
produziu. É o que permite responder, meses depois, "por que o sistema mandou
aplicar naquele talhão".
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from valtexa.models.base import Base, TenantScoped, Timestamped, UUIDPrimaryKey, enum_column
from valtexa.models.enums import (
    Agreement,
    AssetKind,
    DecisionOutcome,
    DetectionSource,
    DiagnosisStatus,
    SafetyVerdict,
    SubjectType,
)


class Asset(UUIDPrimaryKey, TenantScoped, Timestamped, Base):
    """Um arquivo no armazenamento de objetos.

    O conteúdo fica fora do banco; aqui ficam a procedência e o ``sha256``, que
    é o que permite provar que a imagem exibida na auditoria é a mesma que o
    robô enviou.
    """

    __tablename__ = "asset"
    # Único por cliente e conteúdo: o mesmo arquivo enviado duas vezes vira uma
    # linha só. Uma restrição global em ``storage_key`` estaria errada — dois
    # clientes podem enviar bytes idênticos, e cada um precisa da sua linha.
    __table_args__ = (UniqueConstraint("tenant_id", "sha256", name="uq_asset_tenant_sha256"),)

    kind: Mapped[AssetKind] = mapped_column(enum_column(AssetKind), nullable=False)
    content_type: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    storage_key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    device_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("device.id"))
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    meta: Mapped[dict] = mapped_column(default=dict, doc="EXIF, parâmetros do sensor, GSD.")


class Observation(UUIDPrimaryKey, TenantScoped, Timestamped, Base):
    """Um ponto no espaço e no tempo em que o robô olhou para a lavoura."""

    __tablename__ = "observation"
    __table_args__ = (
        Index("ix_observation_field_time", "field_id", "captured_at"),
        Index("ix_observation_device_seq", "device_id", "sequence_number"),
    )

    farm_id: Mapped[str] = mapped_column(String(32), ForeignKey("farm.id"), nullable=False)
    field_id: Mapped[str] = mapped_column(String(32), ForeignKey("field.id"), nullable=False)
    zone_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("zone.id"), index=True)
    mission_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("mission.id", ondelete="SET NULL"), index=True
    )
    device_id: Mapped[str] = mapped_column(String(32), ForeignKey("device.id"), nullable=False)
    sequence_number: Mapped[int | None] = mapped_column(
        BigInteger, doc="Sequência do robô, para deduplicar reenvio offline."
    )

    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lon: Mapped[float] = mapped_column(Float, nullable=False)
    alt_m: Mapped[float | None] = mapped_column(Float)
    heading_deg: Mapped[float | None] = mapped_column(Float)
    row_index: Mapped[int | None] = mapped_column(
        BigInteger, doc="Linha de plantio, quando o rover consegue contá-la."
    )
    plant_ref: Mapped[str | None] = mapped_column(
        String(64), doc="Identidade da planta no gêmeo digital, quando rastreada."
    )

    image_asset_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("asset.id"))
    thumbnail_asset_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("asset.id"))
    pointcloud_asset_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("asset.id"))

    edge_summary: Mapped[dict] = mapped_column(
        default=dict,
        doc=(
            "O que o robô concluiu sozinho antes de subir a imagem. Serve para "
            "priorizar o processamento, nunca para autorizar."
        ),
    )
    model_input_ok: Mapped[bool | None] = mapped_column(
        doc=(
            "Se o enquadramento é o que o modelo espera (folha preenchendo o "
            "quadro). Falso vira NEEDS_REVIEW direto: ver a seção de imagem "
            "aérea em VALTEXA-B/MODELS.md."
        )
    )

    detections: Mapped[list[Detection]] = relationship(
        back_populates="observation", cascade="all, delete-orphan", passive_deletes=True
    )
    diagnoses: Mapped[list[Diagnosis]] = relationship(
        back_populates="observation",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Diagnosis.created_at",
    )


class Detection(UUIDPrimaryKey, TenantScoped, Timestamped, Base):
    """O palpite de **um** analisador sobre **uma** observação.

    Guardar cada análise separada é o que torna a dupla validação auditável: dá
    para perguntar depois em quais casos a IA A e a IA B discordaram, e se a
    discordância foi um bom sinal de erro.
    """

    __tablename__ = "detection"

    observation_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("observation.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source: Mapped[DetectionSource] = mapped_column(
        enum_column(DetectionSource), nullable=False, index=True
    )
    analyzer: Mapped[str] = mapped_column(
        String(64), nullable=False, doc="Nome do analisador. Ver services/ai_pipeline.py."
    )
    model_key: Mapped[str | None] = mapped_column(String(64))
    model_version: Mapped[str | None] = mapped_column(String(64))
    label: Mapped[str | None] = mapped_column(String(64), index=True)
    confidence: Mapped[float | None] = mapped_column(Float)
    novelty_score: Mapped[float | None] = mapped_column(
        Float,
        doc=(
            "Distância normalizada ao que o modelo conhece. Acima de 1,0 é "
            "novidade. Limite medido: pega 4% de uma doença nova da mesma "
            "cultura. Ver VALTEXA-B/MODELS.md."
        ),
    )
    abstained: Mapped[bool] = mapped_column(default=False, nullable=False)
    probabilities: Mapped[dict] = mapped_column(default=dict)
    bbox: Mapped[list | None] = mapped_column(doc="[x, y, w, h] normalizado, quando houver.")
    latency_ms: Mapped[float | None] = mapped_column(Float)
    error: Mapped[str | None] = mapped_column(
        Text, doc="Preenchido quando o analisador falhou. Falha nunca vira concordância."
    )

    observation: Mapped[Observation] = relationship(back_populates="detections")


class Diagnosis(UUIDPrimaryKey, TenantScoped, Timestamped, Base):
    """O resultado da dupla validação sobre uma observação."""

    __tablename__ = "diagnosis"

    observation_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("observation.id", ondelete="CASCADE"), nullable=False, index=True
    )
    field_id: Mapped[str] = mapped_column(String(32), ForeignKey("field.id"), nullable=False)
    zone_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("zone.id"), index=True)

    status: Mapped[DiagnosisStatus] = mapped_column(
        enum_column(DiagnosisStatus), nullable=False, index=True
    )
    agreement: Mapped[Agreement] = mapped_column(enum_column(Agreement), nullable=False)
    label: Mapped[str | None] = mapped_column(String(64), index=True)
    confidence: Mapped[float | None] = mapped_column(Float)
    novelty_score: Mapped[float | None] = mapped_column(Float)
    severity: Mapped[float | None] = mapped_column(
        Float, doc="Severidade estimada em [0, 1]. Nulo enquanto o modelo só classifica."
    )

    primary_detection_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("detection.id"))
    secondary_detection_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("detection.id")
    )
    pipeline_version: Mapped[str] = mapped_column(String(32), nullable=False)
    rationale: Mapped[str | None] = mapped_column(Text)

    reviewed_by: Mapped[str | None] = mapped_column(String(32), ForeignKey("user.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_label: Mapped[str | None] = mapped_column(
        String(64),
        doc=(
            "O veredito do agrônomo. Pode ser um nome que não existe no catálogo "
            "do modelo — é assim que uma doença nova entra no dataset próprio."
        ),
    )
    review_notes: Mapped[str | None] = mapped_column(Text)

    observation: Mapped[Observation] = relationship(back_populates="diagnoses")

    @property
    def effective_label(self) -> str | None:
        """O rótulo que vale: o humano quando existe, senão o da máquina."""
        return self.reviewed_label or self.label


class Decision(UUIDPrimaryKey, TenantScoped, Timestamped, Base):
    """A recomendação do motor de decisão.

    Uma decisão é uma *recomendação*, nunca um comando. Mesmo
    ``APPLICATION_CANDIDATE`` só vira missão depois de aprovação humana e do
    parecer do safety engine.
    """

    __tablename__ = "decision"

    diagnosis_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("diagnosis.id", ondelete="SET NULL"), index=True
    )
    field_id: Mapped[str] = mapped_column(String(32), ForeignKey("field.id"), nullable=False)
    zone_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("zone.id"))

    outcome: Mapped[DecisionOutcome] = mapped_column(
        enum_column(DecisionOutcome), nullable=False, index=True
    )
    reason_code: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
        doc="Código estável. Ver services/decision_engine.py.",
    )
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    rule_version: Mapped[str] = mapped_column(String(32), nullable=False)
    inputs: Mapped[dict] = mapped_column(
        default=dict, doc="Tudo que a regra leu. Reexecutar a regra com isto reproduz a decisão."
    )

    recommended_product_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("product.id")
    )
    recommended_rate_l_ha: Mapped[float | None] = mapped_column(Float)
    target_polygon: Mapped[list | None] = mapped_column()
    affected_ratio: Mapped[float | None] = mapped_column(
        Float, doc="Fração das observações da zona com o mesmo diagnóstico."
    )
    sample_size: Mapped[int | None] = mapped_column(BigInteger)

    mission_id: Mapped[str | None] = mapped_column(
        String(32), doc="A missão que nasceu desta decisão, quando alguém a aprovou."
    )


class SafetyEvaluation(UUIDPrimaryKey, TenantScoped, Timestamped, Base):
    """O parecer do safety engine sobre algo que vai acontecer no mundo físico.

    Guardado mesmo quando aprova: um histórico só de bloqueios não permite
    auditar por que algo *passou*.
    """

    __tablename__ = "safety_evaluation"
    __table_args__ = (Index("ix_safety_subject", "subject_type", "subject_id"),)

    subject_type: Mapped[SubjectType] = mapped_column(enum_column(SubjectType), nullable=False)
    subject_id: Mapped[str] = mapped_column(String(32), nullable=False)
    verdict: Mapped[SafetyVerdict] = mapped_column(
        enum_column(SafetyVerdict), nullable=False, index=True
    )
    checks: Mapped[list] = mapped_column(
        nullable=False,
        default=list,
        doc="Uma entrada por verificação: {code, passed, detail}. Inclui as que passaram.",
    )
    blocked_reason: Mapped[str | None] = mapped_column(Text)
    blocked_code: Mapped[str | None] = mapped_column(String(64), index=True)
    engine_version: Mapped[str] = mapped_column(String(32), nullable=False)
    evaluated_by: Mapped[str | None] = mapped_column(
        String(32), doc="Usuário que disparou a avaliação, quando houve um."
    )
