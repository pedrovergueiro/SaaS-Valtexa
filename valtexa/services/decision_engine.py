"""Motor de decisão: do diagnóstico à recomendação.

Regras determinísticas e versionadas. Nada de modelo aqui — a IA já falou, e o
que este serviço faz é decidir o que a resposta dela justifica, dado o
histórico, a cultura, o estágio e o que existe no depósito.

Duas invariantes valem para o módulo inteiro:

* **Este serviço nunca emite comando físico.** A saída máxima é
  ``APPLICATION_CANDIDATE``, que ainda precisa de aprovação humana e do parecer
  do safety engine para virar missão.
* **A decisão é reproduzível.** Tudo que a regra leu vai para ``Decision.inputs``.
  Reexecutar :func:`decide` com aquele dicionário devolve a mesma saída — é o que
  permite responder "por que o sistema recomendou isso em março".

A regra mais importante do conjunto é a de amostra. Um diagnóstico isolado nunca
vira aplicação: exige-se uma fração mínima da zona afetada sobre um número
mínimo de observações. É a defesa contra o modo de falha medido em
``VALTEXA-B/MODELS.md`` — o modelo respondendo com 0,88 de confiança a uma
doença que não conhece. Um erro desses é pontual; uma infestação real aparece em
dezenas de plantas vizinhas.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from valtexa.config import settings
from valtexa.models import (
    Application,
    ApplicationState,
    Decision,
    DecisionOutcome,
    Diagnosis,
    DiagnosisStatus,
    Field,
    Product,
    ProductStatus,
)
from valtexa.services.ai_pipeline import HEALTHY_LABELS

RULE_VERSION = "1.0.0"
"""Sobe a cada mudança de regra. Fica gravado em cada decisão."""

MIN_SAMPLE = 8
"""Observações mínimas na zona antes de qualquer recomendação de aplicação.

Abaixo disso não há como distinguir infestação de erro pontual do modelo.
"""

REAPPLICATION_COOLDOWN_DAYS = 7
"""Janela em que a mesma zona não recebe o mesmo produto de novo.

Sem isto, um talhão diagnosticado todo dia receberia aplicação todo dia — e o
produtor pagaria por isso antes de alguém notar.
"""

# --- códigos de motivo -------------------------------------------------------
HEALTHY = "healthy"
NOT_VALIDATED = "not_validated"
NEEDS_HUMAN = "needs_human"
NOVELTY = "novelty"
NOT_INDEPENDENT = "not_independent"
LOW_CONFIDENCE = "low_confidence"
SMALL_SAMPLE = "small_sample"
LOW_INCIDENCE = "low_incidence"
NO_PRODUCT = "no_product"
COOLDOWN = "cooldown"
RECOMMEND_APPLICATION = "recommend_application"


@dataclass(frozen=True, slots=True)
class DecisionContext:
    """Tudo que a regra lê. Serializado inteiro em ``Decision.inputs``."""

    label: str | None
    confidence: float | None
    status: str
    novelty_score: float | None
    independent_pair: bool
    crop: str
    crop_stage: str | None
    sample_size: int
    affected_ratio: float
    zone_area_ha: float | None
    available_product_id: str | None
    available_product_rate: float | None
    days_since_last_application: float | None
    last_application_product_id: str | None = None
    sample_unit: str = "observações"
    """``plantas`` quando a incidência veio da fusão por planta (evento da Edge AI)."""
    extra: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class DecisionResult:
    """A recomendação, antes de virar linha no banco."""

    outcome: DecisionOutcome
    reason_code: str
    rationale: str
    product_id: str | None = None
    rate_l_ha: float | None = None


def decide(context: DecisionContext) -> DecisionResult:
    """Aplica as regras, na ordem. A primeira que casa decide."""
    if context.label in HEALTHY_LABELS:
        return DecisionResult(
            DecisionOutcome.NO_ACTION, HEALTHY, "Diagnóstico saudável: nada a fazer."
        )

    if context.status == DiagnosisStatus.INCONCLUSIVE.value:
        return DecisionResult(
            DecisionOutcome.NEED_MORE_DATA,
            LOW_CONFIDENCE,
            "Diagnóstico inconclusivo. Repetir a passada com enquadramento melhor.",
        )

    if context.status == DiagnosisStatus.NEEDS_REVIEW.value:
        reason = NOVELTY if _is_novel(context) else NEEDS_HUMAN
        return DecisionResult(
            DecisionOutcome.HUMAN_REVIEW,
            reason,
            (
                "Novidade acima do limiar: pode ser doença, deficiência ou praga "
                "fora do catálogo. Só o agrônomo fecha."
                if reason == NOVELTY
                else "A dupla validação não fechou. Vai para o agrônomo."
            ),
        )

    if context.status not in {
        DiagnosisStatus.AI_VALIDATED.value,
        DiagnosisStatus.HUMAN_CONFIRMED.value,
    }:
        return DecisionResult(
            DecisionOutcome.HUMAN_REVIEW,
            NOT_VALIDATED,
            f"Diagnóstico em estado {context.status!r}: não sustenta ação automática.",
        )

    human_confirmed = context.status == DiagnosisStatus.HUMAN_CONFIRMED.value

    # Concordância entre análises correlacionadas não é evidência independente.
    # A exceção é o diagnóstico já confirmado por um agrônomo: aí a validação
    # humana substitui a segunda opinião de máquina.
    if not context.independent_pair and not human_confirmed:
        return DecisionResult(
            DecisionOutcome.HUMAN_REVIEW,
            NOT_INDEPENDENT,
            (
                "As análises não são independentes entre si, então a concordância "
                "delas não vale como validação. Precisa de um agrônomo."
            ),
        )

    if _is_novel(context):
        return DecisionResult(
            DecisionOutcome.HUMAN_REVIEW,
            NOVELTY,
            f"Novidade {context.novelty_score:.2f} acima do limiar, apesar da concordância.",
        )

    confidence = context.confidence or 0.0
    if confidence < settings.decision_min_confidence_for_application:
        return DecisionResult(
            DecisionOutcome.OBSERVE,
            LOW_CONFIDENCE,
            (
                f"Confiança {confidence:.2f} abaixo de "
                f"{settings.decision_min_confidence_for_application:.2f} para aplicar. "
                f"Manter em observação."
            ),
        )

    if context.sample_size < MIN_SAMPLE:
        return DecisionResult(
            DecisionOutcome.NEED_MORE_DATA,
            SMALL_SAMPLE,
            (
                f"Só {context.sample_size} observações na zona (mínimo {MIN_SAMPLE}). "
                f"Uma detecção isolada não distingue infestação de erro pontual."
            ),
        )

    if context.affected_ratio < settings.decision_min_incidence:
        return DecisionResult(
            DecisionOutcome.OBSERVE,
            LOW_INCIDENCE,
            (
                f"Incidência de {context.affected_ratio:.1%} abaixo do limiar de "
                f"{settings.decision_min_incidence:.1%}. Acompanhar."
            ),
        )

    if (
        context.days_since_last_application is not None
        and context.days_since_last_application < REAPPLICATION_COOLDOWN_DAYS
        and context.last_application_product_id == context.available_product_id
    ):
        return DecisionResult(
            DecisionOutcome.OBSERVE,
            COOLDOWN,
            (
                f"Mesma zona tratada há {context.days_since_last_application:.1f} dias "
                f"(carência de {REAPPLICATION_COOLDOWN_DAYS}). Avaliar o resultado "
                f"antes de repetir."
            ),
        )

    if context.available_product_id is None:
        return DecisionResult(
            DecisionOutcome.HUMAN_REVIEW,
            NO_PRODUCT,
            (
                f"Nenhum produto cadastrado e autorizado para {context.label!r} em "
                f"{context.crop!r}. Um agrônomo precisa indicar a receita."
            ),
        )

    return DecisionResult(
        DecisionOutcome.APPLICATION_CANDIDATE,
        RECOMMEND_APPLICATION,
        (
            f"{context.affected_ratio:.1%} de {context.sample_size} {context.sample_unit} com "
            f"{context.label!r}, confiança {confidence:.2f}. Candidata a aplicação — "
            f"depende de aprovação do agrônomo e do parecer de segurança."
        ),
        product_id=context.available_product_id,
        rate_l_ha=context.available_product_rate,
    )


def build_context(
    session: Session, diagnosis: Diagnosis, *, window_hours: int = 72
) -> DecisionContext:
    """Monta o contexto a partir do banco.

    A janela existe porque incidência é uma medida do *presente*: misturar as
    observações de duas semanas atrás diluiria um foco que apareceu ontem.
    """
    field_row = session.get(Field, diagnosis.field_id)
    crop = field_row.crop if field_row else ""
    since = datetime.now(UTC) - timedelta(hours=window_hours)

    statement = select(Diagnosis).where(
        Diagnosis.tenant_id == diagnosis.tenant_id,
        Diagnosis.field_id == diagnosis.field_id,
        Diagnosis.created_at >= since,
    )
    if diagnosis.zone_id:
        statement = statement.where(Diagnosis.zone_id == diagnosis.zone_id)
    neighbours = list(session.scalars(statement))

    sample_size = len(neighbours)
    target = diagnosis.effective_label
    affected = sum(1 for row in neighbours if row.effective_label == target)
    affected_ratio = affected / sample_size if sample_size else 0.0
    por_planta = _incidencia_por_planta(session, diagnosis, target)
    unidade = "observações"
    if por_planta is not None:
        (sample_size, affected_ratio), unidade = por_planta, "plantas"

    product = _pick_product(session, diagnosis.tenant_id, crop, target)
    last_application = _last_application(session, diagnosis)

    days_since = None
    if last_application is not None:
        delta = datetime.now(UTC) - _aware(last_application.started_at)
        days_since = delta.total_seconds() / 86_400

    return DecisionContext(
        label=target,
        confidence=diagnosis.confidence,
        status=diagnosis.status.value,
        novelty_score=diagnosis.novelty_score,
        independent_pair=_pair_was_independent(diagnosis),
        crop=crop,
        crop_stage=field_row.crop_stage if field_row else None,
        sample_size=sample_size,
        affected_ratio=affected_ratio,
        zone_area_ha=None,
        available_product_id=product.id if product else None,
        available_product_rate=product.default_rate_l_ha if product else None,
        days_since_last_application=days_since,
        last_application_product_id=(
            last_application.product_id if last_application is not None else None
        ),
        sample_unit=unidade,
    )


def _incidencia_por_planta(
    session: Session, diagnosis: Diagnosis, target: str | None
) -> tuple[int, float] | None:
    """Incidência por planta quando o diagnóstico nasceu de um evento da Edge AI.

    Com a Edge AI filtrando, só os eventos sobem em original para a nuvem: contar
    diagnósticos daria quase 100 % (no ponta a ponta, 75 % contra 7,4 % das plantas).
    A amostra certa são as plantas que o Rover viu na missão (fusão por planta de
    :mod:`valtexa.services.missao_resultado`). ``None`` para observação de outra origem.
    """
    from valtexa.models import Observation
    from valtexa.services.missao_resultado import plantas_da_missao

    observacao = session.get(Observation, diagnosis.observation_id)
    if (
        observacao is None
        or not observacao.mission_id
        or not (observacao.edge_summary or {}).get("edge_record_id")
    ):
        return None
    plantas = plantas_da_missao(session, diagnosis.tenant_id, observacao.mission_id)
    if not plantas["plants_seen"]:
        return None
    doentes = sum(
        1 for p in plantas["plants"] if p["status"] == "doente" and p["label"] == target
    )
    return plantas["plants_seen"], doentes / plantas["plants_seen"]


def evaluate(session: Session, diagnosis: Diagnosis) -> Decision:
    """Decide sobre um diagnóstico e monta a linha. Não faz *commit*."""
    context = build_context(session, diagnosis)
    result = decide(context)
    return Decision(
        tenant_id=diagnosis.tenant_id,
        diagnosis_id=diagnosis.id,
        field_id=diagnosis.field_id,
        zone_id=diagnosis.zone_id,
        outcome=result.outcome,
        reason_code=result.reason_code,
        rationale=result.rationale,
        rule_version=RULE_VERSION,
        inputs=context.as_dict(),
        recommended_product_id=result.product_id,
        recommended_rate_l_ha=result.rate_l_ha,
        affected_ratio=context.affected_ratio,
        sample_size=context.sample_size,
    )


def _is_novel(context: DecisionContext) -> bool:
    return (
        context.novelty_score is not None
        and context.novelty_score > settings.novelty_threshold
    )


def _pair_was_independent(diagnosis: Diagnosis) -> bool:
    """Reconstrói a marca de independência a partir das detecções gravadas.

    O diagnóstico guarda o veredito, não o par. Recontar aqui evita mais uma
    coluna que poderia divergir da realidade das detecções.
    """
    detections = [d for d in diagnosis.observation.detections if d.error is None and d.label]
    return len({d.analyzer for d in detections if not d.analyzer.startswith("dependent:")}) >= 2


def _pick_product(
    session: Session, tenant_id: str, crop: str, target: str | None
) -> Product | None:
    """O produto cadastrado, ativo e autorizado para esta cultura e este alvo.

    Nenhuma inferência: se ninguém cadastrou a autorização, não existe produto —
    e a recomendação vira ``HUMAN_REVIEW``, não uma escolha da máquina.
    """
    if not target:
        return None
    statement = select(Product).where(
        Product.tenant_id == tenant_id, Product.status == ProductStatus.ACTIVE
    )
    for product in session.scalars(statement):
        if crop in (product.allowed_crops or []) and target in (product.authorized_targets or []):
            return product
    return None


def _last_application(session: Session, diagnosis: Diagnosis) -> Application | None:
    statement = (
        select(Application)
        .where(
            Application.tenant_id == diagnosis.tenant_id,
            Application.field_id == diagnosis.field_id,
            Application.state == ApplicationState.COMPLETED,
        )
        .order_by(Application.started_at.desc())
        .limit(1)
    )
    if diagnosis.zone_id:
        statement = statement.where(Application.zone_id == diagnosis.zone_id)
    return session.scalars(statement).first()


def _aware(moment: datetime) -> datetime:
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)
