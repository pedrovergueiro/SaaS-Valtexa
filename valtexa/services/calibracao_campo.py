"""A IA contra o agrônomo, em produção: acerto, cobertura conformal e calibração.

A garantia do conjunto conformal ("a classe certa está no conjunto em 90% das vezes") é da
calibração, feita com fotos de dataset. No campo ela pode cair — a banana cobria 57% para 90%
pedidos (30/09/2026) — e a cabeça nova do aprendizado contínuo muda tudo de novo. Este módulo
mede, por modelo e versão, com o que o agrônomo **confirmou** na fila:

* **acerto**: o rótulo da IA é o do agrônomo;
* **cobertura**: o rótulo do agrônomo está no conjunto conformal que a IA devolveu, contra a
  cobertura que a calibração prometeu (``set_coverage``, gravado na detecção);
* **calibração**: em cada faixa de confiança, quanto a IA acerta (e o ECE, a distância média
  entre as duas);
* **fora do catálogo**: o agrônomo escreveu uma classe que o modelo não tem — nenhum conjunto
  pode cobri-la, então ela sai da cobertura e é contada à parte.

**Viés que não some:** só vai para a fila o que a IA não fechou sozinha (discordância,
confiança baixa, novidade). Os números daqui são dos casos **difíceis** — piores que os da
lavoura inteira. Servem para ver a garantia quebrar, não para anunciar desempenho. A medida
sem esse viés é a campanha de validação de campo (``services.validacao_campo``), em que o
agrônomo anota planta por planta.

Intervalos de Wilson a 95%. Com menos de :data:`MINIMO` casos, o estado é ``poucos_dados``:
o intervalo é largo demais para dizer que a garantia quebrou.
"""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from valtexa.models import Detection, Diagnosis, DiagnosisStatus

MINIMO = 30
"""Casos revisados abaixo dos quais nenhuma conclusão sai (só os números)."""

FAIXAS = ((0.0, 0.5), (0.5, 0.7), (0.7, 0.9), (0.9, 1.0001))
"""Faixas de confiança da curva de calibração (a última inclui 1,0)."""

SEM_CONDICAO = {"Imagem_sem_condicao"}
"""Rótulos que dizem que a foto não serve: não entram em acerto nem cobertura."""


def wilson(k: int, n: int, z: float = 1.96) -> list[float] | None:
    if n == 0:
        return None
    p = k / n
    centro = (p + z * z / (2 * n)) / (1 + z * z / n)
    meia = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return [round(max(0.0, centro - meia), 4), round(min(1.0, centro + meia), 4)]


def _proporcao(k: int, n: int) -> dict:
    return {"k": k, "n": n, "taxa": round(k / n, 4) if n else None, "ic95": wilson(k, n)}


def _estado_da_cobertura(k: int, n: int, prometida: float | None) -> str:
    if prometida is None:
        return "sem_promessa"
    if n < MINIMO:
        return "poucos_dados"
    ic = wilson(k, n)
    return "abaixo" if ic is not None and ic[1] < prometida else "dentro"


def medir(session: Session, *, desde: datetime, tenant_id: str | None = None) -> list[dict]:
    """Um bloco por (modelo, versão) com casos confirmados pelo agrônomo desde ``desde``.

    ``tenant_id`` restringe a um cliente (o produtor vendo o próprio); sem ele, a plataforma.
    """
    consulta = (
        select(Diagnosis.reviewed_label, Detection)
        .join(Detection, Detection.id == Diagnosis.primary_detection_id)
        .where(
            Diagnosis.status == DiagnosisStatus.HUMAN_CONFIRMED,
            Diagnosis.reviewed_label.is_not(None),
            Diagnosis.reviewed_at >= desde,
        )
    )
    if tenant_id is not None:
        consulta = consulta.where(Diagnosis.tenant_id == tenant_id)

    grupos: dict[tuple, list] = defaultdict(list)
    for verdade, det in session.execute(consulta):
        if verdade in SEM_CONDICAO or det.label is None:
            continue
        grupos[(det.model_key, det.model_version)].append((verdade, det))

    saida = []
    for (chave, versao), casos in sorted(grupos.items(), key=lambda kv: -len(kv[1])):
        saida.append(_bloco(chave, versao, casos))
    return saida


def _bloco(chave: str | None, versao: str | None, casos: list) -> dict:
    fora = 0
    acertos = 0
    no_catalogo = 0
    cob_k = cob_n = 0
    tamanhos: list[int] = []
    prometidas: set[float] = set()
    por_classe: dict[str, dict] = defaultdict(lambda: {"n": 0, "acerto": 0, "cob_k": 0,
                                                       "cob_n": 0})
    faixas = [{"n": 0, "acerto": 0, "conf": 0.0} for _ in FAIXAS]
    for verdade, det in casos:
        classes = set((det.probabilities or {}).keys())
        if classes and verdade not in classes:
            fora += 1  # nenhum conjunto cobre classe que o modelo não tem
            continue
        no_catalogo += 1
        certo = det.label == verdade
        acertos += certo
        c = por_classe[verdade]
        c["n"] += 1
        c["acerto"] += certo
        if det.confidence is not None:
            for i, (lo, hi) in enumerate(FAIXAS):
                if lo <= det.confidence < hi:
                    faixas[i]["n"] += 1
                    faixas[i]["acerto"] += certo
                    faixas[i]["conf"] += det.confidence
                    break
        sinais = det.signals or {}
        conjunto = sinais.get("prediction_set")
        if conjunto is not None:
            dentro = verdade in conjunto
            cob_n += 1
            cob_k += dentro
            c["cob_n"] += 1
            c["cob_k"] += dentro
            tamanhos.append(len(conjunto))
            if sinais.get("set_coverage") is not None:
                prometidas.add(round(float(sinais["set_coverage"]), 4))

    # Promessas diferentes no mesmo grupo (calibração trocada no meio): vale a menor, a mais
    # fácil de cumprir — dizer "abaixo" exige quebrar até a mais branda.
    prometida = min(prometidas) if prometidas else None
    total_conf = sum(f["n"] for f in faixas)
    ece = (sum(abs(f["acerto"] / f["n"] - f["conf"] / f["n"]) * f["n"] for f in faixas if f["n"])
           / total_conf) if total_conf else None
    return {
        "model_key": chave,
        "model_version": versao,
        "revisados": len(casos),
        "fora_do_catalogo": fora,
        "acerto": _proporcao(acertos, no_catalogo),
        "cobertura": {
            **_proporcao(cob_k, cob_n),
            "prometida": prometida,
            "estado": _estado_da_cobertura(cob_k, cob_n, prometida),
            "tamanho_medio_do_conjunto": round(sum(tamanhos) / len(tamanhos), 2)
            if tamanhos else None,
        },
        "calibracao": {
            "ece": round(ece, 4) if ece is not None else None,
            "faixas": [
                {"de": lo, "ate": min(hi, 1.0), "n": f["n"],
                 "confianca_media": round(f["conf"] / f["n"], 4) if f["n"] else None,
                 "acerto": round(f["acerto"] / f["n"], 4) if f["n"] else None}
                for (lo, hi), f in zip(FAIXAS, faixas, strict=True)
            ],
        },
        "por_classe": {
            classe: {"n": c["n"], "acerto": _proporcao(c["acerto"], c["n"]),
                     "cobertura": _proporcao(c["cob_k"], c["cob_n"])}
            for classe, c in sorted(por_classe.items())
        },
        "vies": "Só casos que foram à fila (os que a IA não fechou sozinha): piores que a média.",
    }
