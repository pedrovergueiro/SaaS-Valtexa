"""Percepção e dupla validação.

Uma observação passa por *N* analisadores independentes e o resultado é um
:class:`~valtexa.models.perception.Diagnosis`. O ponto de todo o desenho é que
``AI_VALIDATED`` **não** é autorização para nada: é só o estado em que duas
análises independentes chegaram à mesma resposta com confiança suficiente. O que
pode virar ação é decidido depois, por regra determinística, e o que pode
acontecer no mundo físico é decidido depois ainda, pelo safety engine.

**Por que duas análises, e por que a independência é medida.** A limitação está
medida e documentada em ``VALTEXA-B/MODELS.md``: diante de uma doença real fora
do catálogo (cercosporiose retida do treino), o modelo respondeu com confiança
média 0,88, e os filtros de novidade e de confiança juntos interceptaram 19% dos
casos. Duas cópias correlacionadas do mesmo modelo **concordariam com a mesma
resposta errada** e produziriam uma falsa sensação de validação. Por isso o par
carrega a marca ``independent`` e, sem um analisador de fato independente,
nenhum diagnóstico chega a ``AI_VALIDATED`` — a fila do agrônomo cresce, que é o
comportamento correto e honesto.
"""

from __future__ import annotations

import hashlib
import logging
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol

import httpx

from valtexa.config import settings
from valtexa.models import (
    Agreement,
    Detection,
    DetectionSource,
    Diagnosis,
    DiagnosisStatus,
    Observation,
)

logger = logging.getLogger(__name__)

PIPELINE_VERSION = "1.0.0"
"""Sobe a cada mudança de regra de combinação. Fica gravado em cada diagnóstico."""

CROP_TO_MODEL = {
    "corn": "leaf-foliar",
    "milho": "leaf-foliar",
    "coffee": "coffee-foliar",
    "cafe": "coffee-foliar",
    "café": "coffee-foliar",
}
"""Cultura do talhão para modelo do catálogo de VALTEXA-B.

Uma cultura fora deste mapa **não** cai num modelo padrão: o pipeline recusa a
análise. Classificar folha de soja com o modelo de milho devolveria uma das
quatro classes de milho, com confiança alta, e nada no resultado denunciaria o
erro.
"""

HEALTHY_LABELS = frozenset({"Healthy", "Saudavel", "Saudável", "healthy"})
"""Rótulos que significam ausência de doença. Não geram recomendação de ação."""


class AnalyzerUnavailableError(RuntimeError):
    """O analisador não respondeu. Nunca é tratado como concordância."""


@dataclass(frozen=True, slots=True)
class Analysis:
    """O que um analisador devolve sobre uma imagem."""

    analyzer: str
    label: str | None
    confidence: float | None
    novelty_score: float | None = None
    abstained: bool = False
    probabilities: dict = field(default_factory=dict)
    model_key: str | None = None
    model_version: str | None = None
    latency_ms: float | None = None
    error: str | None = None

    @property
    def usable(self) -> bool:
        """Se o resultado pode entrar na combinação."""
        return self.error is None and self.label is not None and self.confidence is not None


class Analyzer(Protocol):
    """Contrato de um analisador."""

    name: str
    independent: bool
    """Se este analisador é estatisticamente independente do primário.

    ``False`` para qualquer coisa derivada dos mesmos pesos — TTA, recorte
    diferente, resolução diferente. Concordância entre dependentes não é
    evidência.
    """

    def analyze(self, image: bytes, filename: str, crop: str) -> Analysis: ...


class HttpModelAnalyzer:
    """Consome o serviço de inferência ``valtexa-disease-backend`` (VALTEXA-B)."""

    def __init__(
        self,
        name: str = "cloud-primary",
        base_url: str | None = None,
        model_key: str | None = None,
        independent: bool = True,
        timeout: float | None = None,
    ) -> None:
        self.name = name
        self.independent = independent
        self.base_url = (base_url or settings.inference_url).rstrip("/")
        self.model_key = model_key
        self.timeout = timeout or settings.inference_timeout_seconds

    def analyze(self, image: bytes, filename: str, crop: str) -> Analysis:
        model_key = self.model_key or model_for_crop(crop)
        started = time.perf_counter()
        try:
            response = httpx.post(
                f"{self.base_url}/predict",
                params={"model": model_key},
                files={"file": (filename, image, _content_type(filename))},
                timeout=self.timeout,
            )
            response.raise_for_status()
            body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("Analisador %s indisponível: %s", self.name, exc)
            return Analysis(
                analyzer=self.name,
                label=None,
                confidence=None,
                model_key=model_key,
                latency_ms=(time.perf_counter() - started) * 1000,
                error=f"{type(exc).__name__}: {exc}",
            )

        return Analysis(
            analyzer=self.name,
            label=body.get("predicted_class"),
            confidence=body.get("confidence"),
            novelty_score=body.get("novelty_score"),
            abstained=bool(body.get("abstained", False)),
            probabilities={
                item["class_name"]: item["probability"] for item in body.get("probabilities", [])
            },
            model_key=body.get("model_key", model_key),
            latency_ms=(time.perf_counter() - started) * 1000,
        )


@dataclass
class StaticAnalyzer:
    """Analisador de mentira, para simulador e testes.

    Devolve o que lhe mandarem devolver. É como o fluxo ponta a ponta roda sem
    GPU, sem rede e sem os pesos de 90 MB.
    """

    name: str = "stub"
    independent: bool = True
    responses: list[Analysis] = field(default_factory=list)
    default: Analysis | None = None
    _index: int = 0

    def analyze(self, image: bytes, filename: str, crop: str) -> Analysis:
        if self.responses:
            answer = self.responses[self._index % len(self.responses)]
            self._index += 1
            return Analysis(**{**answer.__dict__, "analyzer": self.name})
        if self.default is not None:
            return Analysis(**{**self.default.__dict__, "analyzer": self.name})
        return Analysis(analyzer=self.name, label="Healthy", confidence=0.99)


@dataclass(frozen=True, slots=True)
class PipelineOutcome:
    """O que a combinação concluiu, antes de virar linha no banco."""

    status: DiagnosisStatus
    agreement: Agreement
    label: str | None
    confidence: float | None
    novelty_score: float | None
    rationale: str
    independent_pair: bool
    analyses: tuple[Analysis, ...]


SIMULATION_MARKER = b"VTXSIM:"
"""Marca que o simulador anexa ao fim do arquivo de imagem.

JPEG ignora bytes depois do ``EOI``, então a marca viaja junto sem corromper o
arquivo. É andaime de simulação e nada mais: o :class:`SimulatedAnalyzer` a lê
para saber que resposta dar, e é assim que o fluxo ponta a ponta roda sem GPU,
sem rede e sem os 90 MB de pesos.
"""


@dataclass
class SimulatedAnalyzer:
    """Analisador falso e determinístico, para o simulador.

    Lê o rótulo verdadeiro da marca anexada pelo simulador e responde com uma
    confiança derivada do hash da imagem — mesma imagem, mesma resposta, como
    num modelo de verdade. ``bias`` desloca a confiança para que dois
    analisadores simulados não sejam cópias exatas um do outro.

    Só entra em cena com ``SIMULATED_INFERENCE=true``, que
    :meth:`Settings.production_problems` recusa em produção.
    """

    name: str = "sim"
    independent: bool = True
    bias: float = 0.0
    fallback: str = "Healthy"

    def analyze(self, image: bytes, filename: str, crop: str) -> Analysis:
        label, novelty = _read_marker(image, self.fallback)
        digest = hashlib.sha256(image + self.name.encode()).digest()
        # 0,80 a 0,99, deslocado pelo viés do analisador.
        confidence = min(0.99, max(0.05, 0.80 + digest[0] / 255 * 0.19 + self.bias))
        return Analysis(
            analyzer=self.name,
            label=label,
            confidence=round(confidence, 4),
            novelty_score=novelty,
            probabilities={label: round(confidence, 4)},
            model_key=f"simulated-{crop or 'generic'}",
            model_version="sim-1",
            latency_ms=1.0,
        )


def _read_marker(image: bytes, fallback: str) -> tuple[str, float]:
    """Extrai ``VTXSIM:<rótulo>[:<novidade>]`` do fim do arquivo."""
    position = image.rfind(SIMULATION_MARKER)
    if position < 0:
        return fallback, 0.4
    parts = image[position + len(SIMULATION_MARKER) :].decode("ascii", "ignore").split(":")
    label = parts[0].strip() or fallback
    try:
        novelty = float(parts[1]) if len(parts) > 1 else 0.4
    except ValueError:
        novelty = 0.4
    return label, novelty


def model_for_crop(crop: str) -> str:
    """Modelo do catálogo para a cultura do talhão."""
    key = CROP_TO_MODEL.get((crop or "").strip().lower())
    if key is None:
        raise AnalyzerUnavailableError(
            f"Não há modelo treinado para a cultura {crop!r}. "
            f"Culturas atendidas: {sorted(set(CROP_TO_MODEL.values()))}."
        )
    return key


def combine(analyses: Sequence[Analysis]) -> PipelineOutcome:
    """Combina as análises numa conclusão.

    A ordem das regras é deliberada — cada uma só é avaliada quando as anteriores
    não decidiram:

    1. menos de duas análises úteis → ``NEEDS_REVIEW``: uma opinião só nunca valida;
    2. qualquer uma abaixo do limiar de confiança → ``INCONCLUSIVE``;
    3. rótulos diferentes → ``NEEDS_REVIEW``: a discordância é o sinal;
    4. novidade acima do limiar → ``NEEDS_REVIEW``, mesmo com as duas concordando;
    5. concordância fraca (diferença de confiança grande) → ``NEEDS_REVIEW``;
    6. resto → ``AI_VALIDATED``.
    """
    usable = [analysis for analysis in analyses if analysis.usable]
    novelty = max(
        (a.novelty_score for a in analyses if a.novelty_score is not None), default=None
    )
    independent_pair = sum(1 for a in analyses if a.usable and _is_independent(a)) >= 2

    if not usable:
        return PipelineOutcome(
            status=DiagnosisStatus.INCONCLUSIVE,
            agreement=Agreement.UNAVAILABLE,
            label=None,
            confidence=None,
            novelty_score=novelty,
            rationale="Nenhum analisador respondeu.",
            independent_pair=False,
            analyses=tuple(analyses),
        )

    best = max(usable, key=lambda a: a.confidence or 0.0)

    if len(usable) < 2:
        return PipelineOutcome(
            status=DiagnosisStatus.NEEDS_REVIEW,
            agreement=Agreement.UNAVAILABLE,
            label=best.label,
            confidence=best.confidence,
            novelty_score=novelty,
            rationale=(
                "Só uma análise disponível. Uma opinião isolada não é dupla validação: "
                "vai para o agrônomo."
            ),
            independent_pair=False,
            analyses=tuple(analyses),
        )

    if any(a.abstained or (a.confidence or 0.0) < settings.min_confidence for a in usable):
        return PipelineOutcome(
            status=DiagnosisStatus.INCONCLUSIVE,
            agreement=Agreement.ABSTAIN,
            label=best.label,
            confidence=best.confidence,
            novelty_score=novelty,
            rationale=(
                f"Ao menos uma análise ficou abaixo de MIN_CONFIDENCE "
                f"({settings.min_confidence:.2f})."
            ),
            independent_pair=independent_pair,
            analyses=tuple(analyses),
        )

    labels = {a.label for a in usable}
    if len(labels) > 1:
        return PipelineOutcome(
            status=DiagnosisStatus.NEEDS_REVIEW,
            agreement=Agreement.DISAGREE,
            label=best.label,
            confidence=best.confidence,
            novelty_score=novelty,
            rationale=f"Análises discordaram: {sorted(labels)}.",
            independent_pair=independent_pair,
            analyses=tuple(analyses),
        )

    if novelty is not None and novelty > settings.novelty_threshold:
        return PipelineOutcome(
            status=DiagnosisStatus.NEEDS_REVIEW,
            agreement=Agreement.AGREE,
            label=best.label,
            confidence=best.confidence,
            novelty_score=novelty,
            rationale=(
                f"Novidade {novelty:.2f} acima do limiar "
                f"({settings.novelty_threshold:.2f}): a imagem destoa do que os "
                f"modelos conhecem, mesmo com as análises concordando."
            ),
            independent_pair=independent_pair,
            analyses=tuple(analyses),
        )

    confidences = [a.confidence or 0.0 for a in usable]
    spread = max(confidences) - min(confidences)
    if spread > settings.agreement_tolerance:
        return PipelineOutcome(
            status=DiagnosisStatus.NEEDS_REVIEW,
            agreement=Agreement.AGREE,
            label=best.label,
            confidence=min(confidences),
            novelty_score=novelty,
            rationale=(
                f"Mesmo rótulo, mas confianças distantes ({spread:.2f} > "
                f"{settings.agreement_tolerance:.2f}). Concordância frágil."
            ),
            independent_pair=independent_pair,
            analyses=tuple(analyses),
        )

    return PipelineOutcome(
        status=DiagnosisStatus.AI_VALIDATED,
        agreement=Agreement.AGREE,
        label=best.label,
        # A menor das confianças, não a maior: validar por consenso e depois
        # reportar o número mais otimista do par apagaria justamente a dúvida
        # que a segunda análise existe para revelar.
        confidence=min(confidences),
        novelty_score=novelty,
        rationale=(
            f"{len(usable)} análises concordaram em {best.label!r} "
            f"(confiança mínima {min(confidences):.3f})."
            + ("" if independent_pair else " Atenção: o par não é independente.")
        ),
        independent_pair=independent_pair,
        analyses=tuple(analyses),
    )


def analyze_observation(
    observation: Observation,
    image: bytes,
    filename: str,
    crop: str,
    analyzers: Sequence[Analyzer],
) -> tuple[list[Detection], Diagnosis]:
    """Roda o pipeline e monta as linhas do banco.

    Não adiciona nada à sessão nem faz *commit*: quem chamou decide a transação.
    """
    analyses = [analyzer.analyze(image, filename, crop) for analyzer in analyzers]
    outcome = combine(analyses)

    detections = [
        Detection(
            tenant_id=observation.tenant_id,
            observation_id=observation.id,
            source=(
                DetectionSource.CLOUD_PRIMARY if index == 0 else DetectionSource.CLOUD_SECONDARY
            ),
            analyzer=analysis.analyzer,
            model_key=analysis.model_key,
            model_version=analysis.model_version,
            label=analysis.label,
            confidence=analysis.confidence,
            novelty_score=analysis.novelty_score,
            abstained=analysis.abstained,
            probabilities=analysis.probabilities,
            latency_ms=analysis.latency_ms,
            error=analysis.error,
        )
        for index, analysis in enumerate(analyses)
    ]

    diagnosis = Diagnosis(
        tenant_id=observation.tenant_id,
        observation_id=observation.id,
        field_id=observation.field_id,
        zone_id=observation.zone_id,
        status=outcome.status,
        agreement=outcome.agreement,
        label=outcome.label,
        confidence=outcome.confidence,
        novelty_score=outcome.novelty_score,
        pipeline_version=PIPELINE_VERSION,
        rationale=outcome.rationale,
    )
    return detections, diagnosis


def default_analyzers() -> list[Analyzer]:
    """Os analisadores configurados neste processo.

    Hoje devolve **um só**: não existe segundo modelo de fato independente
    treinado. A consequência é intencional e está no contrato do
    :func:`combine` — nada chega a ``AI_VALIDATED``, e todo diagnóstico vai para
    a fila do agrônomo. Um segundo analisador entra aqui, e a partir daí o
    sistema valida sozinho.
    """
    if settings.simulated_inference:
        # Dois analisadores com vieses diferentes: o suficiente para a dupla
        # validação exercitar concordância, discordância e abstenção.
        return [
            SimulatedAnalyzer(name="sim-a", bias=0.0),
            SimulatedAnalyzer(name="sim-b", bias=-0.03),
        ]
    if not settings.inference_enabled:
        return []
    return [HttpModelAnalyzer(name="cloud-primary")]


def _is_independent(analysis: Analysis) -> bool:
    """Um analisador é independente até que se diga o contrário.

    A marca vive no objeto :class:`Analyzer`; aqui só sobra o nome. A convenção
    do prefixo evita carregar o analisador inteiro até o combinador.
    """
    return not analysis.analyzer.startswith("dependent:")


def _content_type(filename: str) -> str:
    lowered = filename.lower()
    if lowered.endswith(".png"):
        return "image/png"
    if lowered.endswith(".webp"):
        return "image/webp"
    return "image/jpeg"
