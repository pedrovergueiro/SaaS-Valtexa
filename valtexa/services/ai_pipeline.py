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
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Protocol

import httpx
from sqlalchemy.orm import Session

from valtexa.config import settings
from valtexa.models import (
    Agreement,
    CapturePlatform,
    Detection,
    DetectionSource,
    Diagnosis,
    DiagnosisStatus,
    ModelVersion,
    ModelVersionState,
    Observation,
)

logger = logging.getLogger(__name__)

PIPELINE_VERSION = "1.0.0"
"""Sobe a cada mudança de regra de combinação. Fica gravado em cada diagnóstico."""

class AnalyzerUnavailableError(RuntimeError):
    """O analisador não respondeu. Nunca é tratado como concordância."""


BANANA = frozenset({"banana", "bananeira", "banana-prata", "banana-nanica"})
CITRUS = frozenset({"citrus", "citros", "laranja", "limão", "limao", "lima", "orange", "lemon"})

class NoModelForCaptureError(AnalyzerUnavailableError):
    """Nenhum modelo treinado responde a esta combinação de cultura e plataforma.

    É uma recusa deliberada, não uma falha. A imagem continua guardada,
    catalogada e georreferenciada; o que não acontece é uma resposta inventada.
    """


def resolve_model(
    session: Session,
    crop: str,
    platform: CapturePlatform,
    preferred: str | None = None,
    *,
    tenant_id: str | None = None,
) -> str:
    """O modelo que atende esta cultura nesta plataforma de captura, lido do registry.

    Só versões em PRODUÇÃO do Model Registry (:mod:`valtexa.services.model_registry`)
    atendem, e só as liberadas para o cliente (``tenant_id``) quando a versão tem
    liberação restrita. Antes, um espelho do catálogo de VALTEXA-B no código fazia
    este papel; a chave devolvida continua a mesma que a IA conhece
    (``banana-foliar``, ``citrus-foliar-cc``...).

    ``preferred`` é a versão escolhida no talhão; sem ela vale ``PRIMARY_MODELS``
    e, por fim, a versão recomendada. Uma escolha que não serve à cultura ou à
    plataforma é recusada com o motivo — nunca trocada em silêncio por outra, que
    responderia classes da cultura errada.

    Levanta :class:`NoModelForCaptureError` com o motivo por extenso quando nenhum
    atende — e o motivo vai inteiro para o painel e para o cliente.

    A separação por plataforma é a regra mais importante deste módulo. Uma foto
    aérea de dossel e uma foto de folha não respondem à mesma pergunta: podridão
    de colmo e sintoma radicular são **fisicamente invisíveis** de cima, e uma
    planta ocupa poucos pixels. Mandar um quadro aéreo ao ``coffee-foliar``
    devolveria uma das cinco classes de folha de café, com confiança alta,
    sobre uma imagem onde nenhuma delas pode ser vista.
    """
    from valtexa.services import model_registry

    cultura = (crop or "").strip().lower()
    candidatos = model_registry.candidatos(session, cultura, platform)
    atendem = model_registry.disponiveis(session, cultura, platform, tenant_id)
    escolha = preferred or settings.primary_model_map.get(cultura)
    if escolha:
        aceitos = {modelo.model_key for modelo in atendem}
        if escolha not in aceitos:
            raise NoModelForCaptureError(
                f"O modelo escolhido {escolha!r} não atende {cultura!r} em captura "
                f"{platform.value!r}. Versões que atendem: "
                f"{', '.join(sorted(aceitos)) or 'nenhuma'}."
            )
        return escolha
    if atendem:
        return atendem[0].model_key

    if any(m.state is ModelVersionState.PRODUCAO for m in candidatos):
        raise NoModelForCaptureError(
            f"Existe modelo para {cultura!r} em captura {platform.value!r}, mas não está "
            f"liberado para este cliente. A liberação é feita pela equipe da ValTexa."
        )
    if candidatos:
        motivo = "; ".join(
            f"{m.model_key} ({m.caveat or model_registry.ROTULOS[m.state].lower()})"
            for m in candidatos
        )
        raise NoModelForCaptureError(
            f"Existe modelo para {cultura!r} em captura {platform.value!r}, mas nenhum "
            f"treinado: {motivo}. As imagens ficam guardadas e vão para a fila do "
            f"agrônomo — é assim que o dataset desse modelo é formado."
        )

    disponiveis = sorted(
        f"{m.model_key} ({'/'.join(sorted(m.crops))}, {m.platform.value})"
        for m in model_registry.treinadas(session)
    )
    raise NoModelForCaptureError(
        f"Não há modelo treinado para {cultura!r} em captura {platform.value!r}. "
        f"Treinados hoje: {', '.join(disponiveis) or 'nenhum'}."
    )

HEALTHY_LABELS = frozenset({"Healthy", "Saudavel", "Saudável", "healthy"})
"""Rótulos que significam ausência de doença. Não geram recomendação de ação."""


@dataclass(frozen=True, slots=True)
class Analysis:
    """O que um analisador devolve sobre uma imagem."""

    analyzer: str
    label: str | None
    confidence: float | None
    novelty_score: float | None = None
    severity: float | None = None
    """Fração do quadro com lesão, quando o serviço de inferência mede."""

    abstained: bool = False
    probabilities: dict = field(default_factory=dict)
    model_key: str | None = None
    model_version: str | None = None
    latency_ms: float | None = None
    error: str | None = None
    in_scope: bool | None = None
    """Veredito do portão de enquadramento: ``False`` = não é folha em close."""

    scene: str | None = None
    """Cena que o portão viu, ex.: ``folha_banana``, ``pseudocaule``, ``tronco``."""

    prediction_set: tuple[str, ...] | None = None
    """Conjunto conformal: as classes que não dá para descartar."""

    set_coverage: float | None = None
    """A cobertura que a calibração promete para o conjunto (ex.: 0,9). Gravada para medir,
    com o rótulo do agrônomo, se a promessa vale no campo (``services.calibracao_campo``)."""

    frame: dict | None = None
    """Resumo do quadro do rover (``/predict/rover-frame``), quando foi um."""

    @property
    def signals(self) -> dict:
        """O que a IA disse além do rótulo — gravado em ``Detection.signals``."""
        out: dict = {}
        if self.in_scope is not None:
            out["in_scope"] = self.in_scope
        if self.scene is not None:
            out["scene"] = self.scene
        if self.prediction_set is not None:
            out["prediction_set"] = list(self.prediction_set)
        if self.set_coverage is not None:
            out["set_coverage"] = self.set_coverage
        if self.frame is not None:
            out["frame"] = self.frame
        return out

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

    def analyze(
        self,
        image: bytes,
        filename: str,
        crop: str,
        model: str | None = None,
        frame: RoverFrame | None = None,
        training_consent: bool = False,
    ) -> Analysis: ...


@dataclass(frozen=True, slots=True)
class RoverFrame:
    """A câmera do rover no instante do quadro — o que o recorte em escala física exige.

    Com ``camera_height_mm`` e ``distance_mm`` o serviço de inferência corta o
    quadro em pedaços de 150 mm e sabe a altura (e a zona da planta) de cada um.
    Com ``field_id``, ``row_id``, ``side``, ``x_m`` e ``pass_id`` também, o quadro
    alimenta a fusão por planta do talhão no serviço de inferência.
    """

    camera_height_mm: float
    distance_mm: float
    side: str | None = None
    x_m: float | None = None
    field_id: str | None = None
    row_id: str | None = None
    pass_id: str | None = None
    lat: float | None = None
    lon: float | None = None
    heading_deg: float | None = None
    camera_id: str | None = None
    frame_id: str | None = None
    captured_at: datetime | None = None
    """Instante da foto. Um lote sincronizado depois de o enlace cair chega horas
    depois; sem isto, o histórico da planta ficaria datado pela chegada."""

    def query(self, model_key: str) -> dict:
        params: dict = {
            "model": model_key,
            "camera_height_mm": self.camera_height_mm,
            "distance_mm": self.distance_mm,
            "only_findings": "false",
        }
        fusion = (self.field_id, self.row_id, self.side, self.x_m, self.pass_id)
        if all(value is not None for value in fusion):
            params.update(
                field_id=self.field_id,
                row_id=self.row_id,
                side=self.side,
                x_m=self.x_m,
                pass_id=self.pass_id,
            )
        for key in ("lat", "lon", "heading_deg", "camera_id", "frame_id"):
            value = getattr(self, key)
            if value is not None:
                params[key] = value
        if self.captured_at is not None:
            params["captured_at"] = self.captured_at.isoformat()
        return params


FRAME_REVIEW_SHARE = 0.25
"""Fração dos recortes no escopo marcados como estranhos ao modelo a partir da qual
o quadro inteiro vai para o agrônomo — o equivalente, no quadro, da novidade acima
do limiar numa foto só."""


TRAINING_CONSENT_HEADER = "X-Training-Consent"
"""O cabeçalho que o serviço de IA lê (``ia/app/review.py``)."""


class HttpModelAnalyzer:
    """Consome o serviço de inferência ``valtexa-disease-backend`` (VALTEXA-B)."""

    def __init__(
        self,
        name: str = "cloud-primary",
        base_url: str | None = None,
        model_key: str | None = None,
        independent: bool = True,
        timeout: float | None = None,
        crop_models: dict[str, str] | None = None,
    ) -> None:
        self.name = name
        self.independent = independent
        self.base_url = (base_url or settings.inference_url).rstrip("/")
        self.model_key = model_key
        self.timeout = timeout or settings.inference_timeout_seconds
        self.crop_models = crop_models

    def analyze(
        self,
        image: bytes,
        filename: str,
        crop: str,
        model: str | None = None,
        frame: RoverFrame | None = None,
        training_consent: bool = False,
    ) -> Analysis:
        if self.crop_models is not None:
            # Sem modelo para a cultura, o analisador se declara ausente em vez de
            # cair no modelo primário — uma "segunda opinião" dada pelo mesmo
            # modelo seria a pior forma de dependência.
            model_key = self.crop_models.get((crop or "").strip().lower())
            if model_key is None:
                return Analysis(
                    analyzer=self.name,
                    label=None,
                    confidence=None,
                    error=f"Sem modelo secundário para a cultura {crop!r}.",
                )
        else:
            model_key = model or self.model_key
            if model_key is None:
                # Quem escolhe o modelo é o registry, na resolução do talhão (com
                # banco). O analisador só fala HTTP: sem modelo designado, recusa.
                return Analysis(
                    analyzer=self.name,
                    label=None,
                    confidence=None,
                    error=f"Nenhum modelo designado pelo registry para a cultura {crop!r}.",
                )
        started = time.perf_counter()
        route, params = "/predict", {"model": model_key}
        if frame is not None:
            route, params = "/predict/rover-frame", frame.query(model_key)
        try:
            response = httpx.post(
                f"{self.base_url}{route}",
                params=params,
                files={"file": (filename, image, _content_type(filename))},
                # Brief, seção 32: a IA só põe a imagem na fila de revisão (que
                # alimenta o treino) quando o cliente consentiu. Sempre enviado:
                # sem o cabeçalho, a IA seguiria a configuração do servidor.
                headers={
                    **settings.inference_headers(),
                    TRAINING_CONSENT_HEADER: "1" if training_consent else "0",
                },
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

        latency = (time.perf_counter() - started) * 1000
        if frame is not None:
            return frame_analysis(self.name, body, model_key, latency)

        framing = body.get("framing") or {}
        prediction_set = body.get("prediction_set")
        return Analysis(
            analyzer=self.name,
            label=body.get("predicted_class"),
            confidence=body.get("confidence"),
            novelty_score=body.get("novelty_score"),
            severity=body.get("severity"),
            abstained=bool(body.get("abstained", False)),
            probabilities={
                item["class_name"]: item["probability"] for item in body.get("probabilities", [])
            },
            model_key=body.get("model_key", model_key),
            latency_ms=latency,
            in_scope=framing.get("in_scope"),
            scene=framing.get("scene"),
            prediction_set=None if prediction_set is None else tuple(prediction_set),
            set_coverage=body.get("set_coverage"),
        )


def frame_analysis(analyzer: str, body: dict, model_key: str, latency_ms: float) -> Analysis:
    """Resume o quadro do rover — dezenas de recortes — numa análise só.

    O rótulo é a doença mais frequente entre os recortes que o portão aceitou
    (uma lesão num recorte já é achado: é para isso que o rover chega perto), ou
    ``Healthy`` se nenhum tem doença. A confiança é a média dos recortes com esse
    rótulo, e ``probabilities`` guarda a **fração de recortes** de cada classe —
    não uma probabilidade do modelo, e o nome no resumo do quadro diz isso.

    Sem nenhum recorte no escopo (o quadro todo é pseudocaule, tronco ou fruto),
    a análise sai com ``in_scope=False``: não há folha para diagnosticar.
    """
    tiles = body.get("tiles") or []
    in_scope = [tile for tile in tiles if tile.get("in_scope") is not False]
    summary = {
        "tiles_analyzed": body.get("tiles_analyzed", len(tiles)),
        "tiles_in_scope": len(in_scope),
        "zone_summary": body.get("zone_summary") or {},
        "out_of_scope": body.get("out_of_scope") or {},
        "class_share": {},
        "needs_review_share": 0.0,
    }
    for key in ("plants", "field_prevalence", "sigatoka"):
        if body.get(key) is not None:
            summary[key] = body[key]

    if not in_scope:
        scenes = Counter(tile.get("scene") or "?" for tile in tiles)
        return Analysis(
            analyzer=analyzer,
            label=None,
            confidence=None,
            model_key=body.get("model_key", model_key),
            latency_ms=latency_ms,
            in_scope=False,
            scene=scenes.most_common(1)[0][0] if scenes else None,
            frame=summary,
            error=None if tiles else "Quadro sem recortes analisáveis.",
        )

    counts = Counter(tile["predicted_class"] for tile in in_scope)
    diseases = {name: n for name, n in counts.items() if name not in HEALTHY_LABELS}
    label = max(sorted(diseases), key=diseases.get) if diseases else "Healthy"
    confidences = [tile["confidence"] for tile in in_scope if tile["predicted_class"] == label]
    summary["class_share"] = {name: n / len(in_scope) for name, n in counts.items()}
    summary["needs_review_share"] = sum(bool(t.get("needs_review")) for t in in_scope) / len(
        in_scope
    )
    return Analysis(
        analyzer=analyzer,
        label=label,
        confidence=sum(confidences) / len(confidences) if confidences else None,
        probabilities=summary["class_share"],
        model_key=body.get("model_key", model_key),
        latency_ms=latency_ms,
        in_scope=True,
        frame=summary,
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

    def analyze(
        self,
        image: bytes,
        filename: str,
        crop: str,
        model: str | None = None,
        frame: RoverFrame | None = None,
        training_consent: bool = False,
    ) -> Analysis:
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

    def analyze(
        self,
        image: bytes,
        filename: str,
        crop: str,
        model: str | None = None,
        frame: RoverFrame | None = None,
        training_consent: bool = False,
    ) -> Analysis:
        label, novelty = _read_marker(image, self.fallback)
        digest = hashlib.sha256(image + self.name.encode()).digest()
        image_digest = hashlib.sha256(image).digest()
        # 0,80 a 0,99, deslocado pelo viés do analisador.
        confidence = min(0.99, max(0.05, 0.80 + digest[0] / 255 * 0.19 + self.bias))
        # Severidade da imagem, não do analisador: os dois simulados respondem o
        # mesmo número, como os dois reais recebem o mesmo da segmentação.
        severity = 0.0 if label in HEALTHY_LABELS else 0.03 + image_digest[1] / 255 * 0.32
        model_key = f"simulated-{crop or 'generic'}"
        if frame is not None:
            return self._frame(label, round(confidence, 4), novelty, crop, model_key)
        return Analysis(
            analyzer=self.name,
            label=label,
            confidence=round(confidence, 4),
            novelty_score=novelty,
            severity=round(severity, 3),
            probabilities={label: round(confidence, 4)},
            model_key=model_key,
            model_version="sim-1",
            latency_ms=1.0,
        )

    def _frame(
        self, label: str, confidence: float, novelty: float, crop: str, model_key: str
    ) -> Analysis:
        """O quadro do rover como um recorte só, resumido pelo mesmo código do real.

        Não inventa plantas nem severidade da Sigatoka: essas vêm da fusão do
        serviço de inferência, que o simulador não tem.
        """
        cultura = (crop or "").strip().lower()
        zone = "folhas_baixas" if cultura in BANANA else "copa" if cultura in CITRUS else "folha"
        finding = label not in HEALTHY_LABELS
        body = {
            "model_key": model_key,
            "tiles_analyzed": 1,
            "tiles": [
                {
                    "predicted_class": label,
                    "confidence": confidence,
                    "in_scope": True,
                    "zones": [zone],
                    "needs_review": novelty > settings.novelty_threshold,
                }
            ],
            "zone_summary": {
                zone: {"recortes": 1, "com_achado": int(finding), "fora_de_escopo": 0}
            },
        }
        analysis = frame_analysis(self.name, body, model_key, latency_ms=1.0)
        return replace(analysis, novelty_score=novelty, model_version="sim-1")


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


def versions_for_crop(
    session: Session, crop: str, platform: CapturePlatform, *, tenant_id: str | None = None
) -> list[ModelVersion]:
    """As versões em PRODUÇÃO liberadas para o cliente que atendem a cultura,
    a recomendada primeiro."""
    from valtexa.services import model_registry

    return model_registry.disponiveis(session, crop, platform, tenant_id)


def model_for_crop(session: Session, crop: str, *, tenant_id: str | None = None) -> str:
    """Modelo do registry para a cultura do talhão, em imagem de solo.

    Atalho histórico para :func:`resolve_model` com ``CapturePlatform.GROUND`` —
    é o caso do rover e do celular. Imagem aérea nunca passa por aqui.
    """
    return resolve_model(session, crop, CapturePlatform.GROUND, tenant_id=tenant_id)


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

    out_of_scope = [a for a in analyses if a.error is None and a.in_scope is False]
    if out_of_scope:
        # Antes de qualquer contagem de votos: o modelo foliar dá uma doença de
        # folha para qualquer imagem, com confiança, e um pseudocaule sadio sairia
        # "Fusariose". Não há rótulo a validar — há uma imagem para o agrônomo.
        scene = out_of_scope[0].scene or "?"
        return PipelineOutcome(
            status=DiagnosisStatus.NEEDS_REVIEW,
            agreement=Agreement.ABSTAIN,
            label=None,
            confidence=None,
            novelty_score=novelty,
            rationale=(
                f"O portão de enquadramento diz que a imagem não é folha em close "
                f"(cena {scene!r}): o modelo foliar não sabe lê-la."
            ),
            independent_pair=independent_pair,
            analyses=tuple(analyses),
        )

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

    ambiguous = [a for a in usable if a.prediction_set is not None and len(a.prediction_set) != 1]
    if ambiguous:
        conjunto = list(ambiguous[0].prediction_set or ())
        return PipelineOutcome(
            status=DiagnosisStatus.NEEDS_REVIEW,
            agreement=Agreement.ABSTAIN,
            label=best.label,
            confidence=best.confidence,
            novelty_score=novelty,
            rationale=(
                f"O conjunto conformal não é uma resposta única ({conjunto or 'vazio'}): "
                f"com a cobertura garantida, o modelo não consegue descartar as outras."
            ),
            independent_pair=independent_pair,
            analyses=tuple(analyses),
        )

    strange = [
        a
        for a in usable
        if a.frame and a.frame.get("needs_review_share", 0.0) >= FRAME_REVIEW_SHARE
    ]
    if strange:
        share = strange[0].frame["needs_review_share"]
        return PipelineOutcome(
            status=DiagnosisStatus.NEEDS_REVIEW,
            agreement=Agreement.ABSTAIN,
            label=best.label,
            confidence=best.confidence,
            novelty_score=novelty,
            rationale=(
                f"{share:.0%} dos recortes do quadro destoam do que o modelo conhece "
                f"(limite {FRAME_REVIEW_SHARE:.0%})."
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

    if not independent_pair:
        # Concordância entre análises correlacionadas não é evidência: os dois
        # modelos erram juntos justamente onde importa — na doença que nenhum
        # deles viu. Sem par independente, quem fecha é o agrônomo.
        return PipelineOutcome(
            status=DiagnosisStatus.NEEDS_REVIEW,
            agreement=Agreement.AGREE,
            label=best.label,
            confidence=min(confidences),
            novelty_score=novelty,
            rationale=(
                f"{len(usable)} análises concordaram em {best.label!r}, mas o par não é "
                "independente: concordância correlacionada não valida."
            ),
            independent_pair=False,
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
            f"{len(usable)} análises independentes concordaram em {best.label!r} "
            f"(confiança mínima {min(confidences):.3f})."
        ),
        independent_pair=True,
        analyses=tuple(analyses),
    )


def run_analyzers(
    image: bytes,
    filename: str,
    crop: str,
    analyzers: Sequence[Analyzer],
    *,
    model_key: str | None = None,
    frame: RoverFrame | None = None,
    training_consent: bool = False,
) -> list[Analysis]:
    """Chama os analisadores — só HTTP, nenhum acesso ao banco.

    Separado de :func:`analyze_observation` para rodar **antes** da transação:
    a inferência leva segundos, e uma transação aberta durante eles seguraria a
    linha do dispositivo (e, no SQLite, o banco inteiro).
    """
    return [
        analyzer.analyze(
            image,
            filename,
            crop,
            model=model_key if index == 0 else None,
            frame=frame,
            training_consent=training_consent,
        )
        for index, analyzer in enumerate(analyzers)
    ]


def analyze_observation(
    observation: Observation,
    image: bytes,
    filename: str,
    crop: str,
    analyzers: Sequence[Analyzer],
    *,
    model_key: str | None = None,
    frame: RoverFrame | None = None,
    analyses: Sequence[Analysis] | None = None,
) -> tuple[list[Detection], Diagnosis]:
    """Roda o pipeline e monta as linhas do banco.

    ``model_key`` é a versão escolhida para o analisador primário (o secundário
    tem o seu mapa próprio); ``frame``, a câmera do rover quando a imagem é um
    quadro inteiro. Com ``analyses`` (de :func:`run_analyzers`), não chama os
    analisadores de novo. Não adiciona nada à sessão nem faz *commit*: quem
    chamou decide a transação.
    """
    if analyses is None:
        analyses = run_analyzers(
            image, filename, crop, analyzers, model_key=model_key, frame=frame
        )
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
            signals=analysis.signals,
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
        severity=measured_severity(analyses),
        pipeline_version=PIPELINE_VERSION,
        rationale=outcome.rationale,
    )
    return detections, diagnosis


def measured_severity(analyses: Sequence[Analysis]) -> float | None:
    """A severidade medida, se algum analisador mediu.

    Não passa pelo combinador: é medida de área lesionada, não opinião sobre o
    rótulo — e os analisadores reais a recebem do mesmo modelo de segmentação.
    Por isso também não entra na regra de decisão: até ser validada em campo, é
    informação para o agrônomo, não gatilho de aplicação.
    """
    return next(
        (a.severity for a in analyses if a.error is None and a.severity is not None), None
    )


def default_analyzers() -> list[Analyzer]:
    """Os analisadores configurados neste processo.

    O primário sempre; o secundário quando ``SECONDARY_MODELS`` está
    configurado. O secundário só conta como par independente com
    ``SECONDARY_MODEL_INDEPENDENT=true`` — do contrário ele entra com o prefixo
    ``dependent:`` e o combinador não conta a concordância. Sem par
    independente, a consequência é intencional e está no contrato do
    :func:`combine`: nada chega a ``AI_VALIDATED``, e todo diagnóstico vai para
    a fila do agrônomo.
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

    analyzers: list[Analyzer] = [HttpModelAnalyzer(name="cloud-primary")]
    if settings.secondary_model_map:
        independent = settings.secondary_model_independent
        analyzers.append(
            HttpModelAnalyzer(
                # O prefixo é o que o combinador lê para não contar o par como
                # independente. Ver _is_independent.
                name="cloud-secondary" if independent else "dependent:cloud-secondary",
                crop_models=settings.secondary_model_map,
                independent=independent,
            )
        )
    return analyzers


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
