"""Em que ordem o agrônomo revisa: o que mais ensina primeiro.

A fila cresce mais rápido do que alguém revisa — o rover manda dezenas de
quadros por fileira. Por novidade só, o topo fica cheio de fotos esquisitas, e a
folha que o modelo confunde entre duas doenças (a que mais melhora o próximo
treino) espera. Aqui cada item recebe uma pontuação explicável, somando:

* **fora do escopo** — o portão disse que não é folha: alguém precisa nomear o
  que é (pseudocaule? fruto?), e é daí que sai o dataset de pseudocaule;
* **discordância** entre as análises;
* **incerteza** — margem pequena entre as duas classes mais prováveis, ou
  conjunto conformal com mais de uma;
* **novidade** acima do limiar;
* **classe rara** entre as que o agrônomo já rotulou deste cliente.

É a ordem por incerteza do aprendizado ativo (``VALTEXA-B/app/active_learning.py``),
que no simulador chegou à mesma acurácia com 30% menos rótulos que a ordem
aleatória — sem os embeddings, que o SaaS não guarda.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from valtexa.config import settings
from valtexa.models import Agreement, Detection, Diagnosis

RARE_BELOW = 5
"""Classe com menos rótulos humanos que isto, neste cliente, conta como rara."""


@dataclass(frozen=True, slots=True)
class Priority:
    score: float
    reasons: list[str] = field(default_factory=list)


def _margin(probabilities: dict) -> float | None:
    values = sorted((float(v) for v in (probabilities or {}).values()), reverse=True)
    if len(values) < 2:
        return None
    return values[0] - values[1]


def priority(diagnosis: Diagnosis, primary: Detection | None, reviewed_labels: Counter) -> Priority:
    """A pontuação de um item da fila e os motivos, em português."""
    score, reasons = 0.0, []
    signals = (primary.signals if primary is not None else None) or {}

    if signals.get("in_scope") is False:
        score += 0.6
        reasons.append(f"não é folha: {signals.get('scene') or 'cena desconhecida'}")
    if diagnosis.agreement is Agreement.DISAGREE:
        score += 0.5
        reasons.append("as análises discordaram")

    probabilities = primary.probabilities if primary is not None else {}
    margin = _margin(probabilities)
    if margin is not None:
        score += 0.5 * (1.0 - margin)
        if margin < 0.2 and signals.get("frame"):
            # Num quadro do rover, `probabilities` é a fração dos recortes por
            # classe (ai_pipeline.frame_analysis), não a confiança do modelo.
            first, second = sorted(probabilities, key=probabilities.get, reverse=True)[:2]
            reasons.append(f"recortes divididos entre {first} e {second}")
        elif margin < 0.2:
            reasons.append(f"incerteza alta: margem {margin:.2f}".replace(".", ","))
    conformal = signals.get("prediction_set")
    if conformal is not None and len(conformal) != 1:
        score += 0.3
        reasons.append("conjunto conformal ambíguo" if conformal else "conjunto conformal vazio")

    novelty = diagnosis.novelty_score or 0.0
    score += 0.2 * min(novelty / settings.novelty_threshold, 2.0)
    if novelty > settings.novelty_threshold:
        reasons.append(f"novidade {novelty:.1f}".replace(".", ","))

    label = diagnosis.label
    if label and reviewed_labels[label] < RARE_BELOW:
        score += 0.3 / (1 + reviewed_labels[label])
        reasons.append(f"classe rara: {label}")

    return Priority(round(score, 4), reasons)
