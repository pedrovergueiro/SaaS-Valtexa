"""Consenso federado (brief 7.1): o que os Rovers compartilham de fato, e como funde.

O ``merge_priors`` do dNATY funde **estatísticas de operadores de mutação** da busca de
arquitetura — normaliza cada prior (centra na média e escala ao máximo) e tira a média. Para
prevalência de doença isso **apaga o nível** (2% e 20% viram a mesma forma) e **ignora o
tamanho da amostra** (10 plantas valem o mesmo que 10 mil). Ver ``docs/FEDERADO.md`` e
``ia/tests/test_dnaty_merge_priors.py`` (medido). Aqui está o que serve:

**O que se compartilha**: contagens **validadas** por estrato — para cada (variedade, solo,
estágio) e classe, ``positivos`` de ``n`` plantas que o **agrônomo conferiu** (diagnóstico
``human_confirmed``/``human_rejected``) — com o protocolo que as produziu. Nada de imagem,
nada de peso de rede. As observações já sobem pela Starlink de cada Rover; as contagens são
montadas na plataforma (custo de subida **zero**). O que desce é o prior fundido (bytes
medidos em :func:`tamanho`).

**Compatibilidade** (:func:`compativel`): mesma taxonomia de classes (hash), mesmo modelo e
mesma cabeça, mesmo protocolo de validação, dentro da janela de tempo, números coerentes.
O que não bate é recusado, com o motivo — nunca "convertido".

**Anti-eco** (dois):

* a mesma observação não conta duas vezes: cada contagem carrega os ids das observações e a
  fusão descarta as repetidas (dois Rovers vendo a mesma planta, reenvio);
* o prior que volta a um talhão **não contém o dado dele** (deixa-um-de-fora por origem): o
  dado do próprio talhão entra lá como evidência local, uma vez só — a mesma regra do gêmeo.

**Fusão** (:func:`fundir`): Beta-binomial hierárquica com encolhimento empírico (método dos
momentos): por classe, ``p_medio`` agregado e a correlação intra-estrato ``rho`` dão a concentração
``kappa = (1 - rho)/rho``; o prior do estrato ``s`` para o talhão ``F`` é
``Beta(kappa p_-F + x_s,-F, kappa (1 - p_-F) + n_s,-F - x_s,-F)``, com a força total limitada a
``forca_maxima`` (premissa): o prior compartilhado nunca afoga o dado local.

**Avaliação antes de distribuir** (:func:`avaliar`): para cada talhão com dado, a
log-verossimilhança preditiva (Beta-binomial) do dado dele sob o prior fundido **sem ele**
contra o prior de referência (o do treino); distribui só se a média não piora.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import math
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

FORCA_MAXIMA = 200.0
"""Premissa: o prior fundido vale no máximo 200 plantas de evidência."""
KAPPA_MINIMO = 2.0


@dataclass(frozen=True)
class Protocolo:
    taxonomia_sha256: str
    modelo: str
    cabeca: str
    validacao: str

    @staticmethod
    def taxonomia(classes: Iterable[str]) -> str:
        return hashlib.sha256("\n".join(sorted(classes)).encode()).hexdigest()


@dataclass(frozen=True)
class Contagem:
    """Quantas das plantas conferidas de um talhão, num estrato, tinham a classe."""

    origem: str
    """O talhão que produziu a contagem (anti-eco por origem)."""
    estrato: tuple[str, str, str]
    """(variedade, solo, estágio) — ``"?"`` onde o cadastro não diz."""
    classe: str
    observacoes: frozenset[str]
    """As observações conferidas (anti-eco por observação)."""
    positivas: frozenset[str]
    """As que tinham a classe (subconjunto de ``observacoes``)."""
    inicio: date
    fim: date
    protocolo: Protocolo

    @property
    def n(self) -> int:
        return len(self.observacoes)

    @property
    def positivos(self) -> int:
        return len(self.positivas)


def compativel(c: Contagem, referencia: Protocolo, *, inicio: date, fim: date) -> str | None:
    """``None`` se entra; senão, o motivo."""
    if c.protocolo.taxonomia_sha256 != referencia.taxonomia_sha256:
        return "taxonomia de classes diferente"
    if (c.protocolo.modelo, c.protocolo.cabeca) != (referencia.modelo, referencia.cabeca):
        return "modelo ou cabeça diferente"
    if c.protocolo.validacao != referencia.validacao:
        return "protocolo de validação diferente"
    if c.inicio < inicio or c.fim > fim or c.inicio > c.fim:
        return "fora da janela de tempo"
    if not c.observacoes:
        return "contagem vazia"
    if not c.positivas <= c.observacoes:
        return "positivas fora das observações"
    return None


def sem_eco(contagens: Sequence[Contagem]) -> tuple[list[Contagem], int]:
    """Descarta a observação que já entrou (por classe), na ordem (origem, início): a mesma
    planta vista por dois Rovers, ou reenviada, conta uma vez. ``(limpas, descartadas)``."""
    vistas: dict[str, set[str]] = defaultdict(set)
    saida, descartadas = [], 0
    for c in sorted(contagens, key=lambda c: (c.origem, c.inicio, c.classe, c.estrato)):
        novas = c.observacoes - vistas[c.classe]
        descartadas += len(c.observacoes) - len(novas)
        vistas[c.classe] |= novas
        if novas:
            saida.append(Contagem(c.origem, c.estrato, c.classe, frozenset(novas),
                                  c.positivas & novas, c.inicio, c.fim, c.protocolo))
    return saida, descartadas


@dataclass(frozen=True)
class Beta:
    alfa: float
    beta: float

    @property
    def media(self) -> float:
        return self.alfa / (self.alfa + self.beta)

    @property
    def forca(self) -> float:
        return self.alfa + self.beta

    def to_dict(self) -> dict[str, float]:
        return {"alfa": round(self.alfa, 4), "beta": round(self.beta, 4),
                "media": round(self.media, 6), "forca": round(self.forca, 2)}


def concentracao(por_estrato: Sequence[tuple[int, int]], *, forca_maxima: float) -> float:
    """kappa = (1 - rho)/rho pela correlação intra-estrato ``rho`` (método dos momentos para a
    Beta-binomial). Estratos iguais (rho ≤ 0) → kappa máximo (junta tudo); muito diferentes → kappa
    pequeno (cada estrato fica com o próprio dado)."""
    dados = [(x, n) for x, n in por_estrato if n > 0]
    total = sum(n for _, n in dados)
    if len(dados) < 2 or total == 0:
        return forca_maxima
    p = sum(x for x, _ in dados) / total
    if p <= 0.0 or p >= 1.0:
        return forca_maxima
    k = len(dados)
    s = sum(n * (x / n - p) ** 2 for x, n in dados)
    denominador = p * (1 - p) * (total - sum(n * n for _, n in dados) / total)
    if denominador <= 0:
        return forca_maxima
    rho = (s - p * (1 - p) * (k - 1)) / denominador
    if rho <= 0:
        return forca_maxima
    return min(forca_maxima, max(KAPPA_MINIMO, (1 - rho) / rho))


def prior_para(contagens: Sequence[Contagem], *, destino: str, estrato: tuple[str, str, str],
               classe: str, forca_maxima: float = FORCA_MAXIMA) -> dict[str, Any]:
    """O prior da ``classe`` no ``estrato`` para o talhão ``destino`` — **sem o dado dele**."""
    outras = [c for c in contagens if c.classe == classe and c.origem != destino]
    por_estrato: dict[tuple[str, str, str], list[int]] = defaultdict(lambda: [0, 0])
    for c in outras:
        por_estrato[c.estrato][0] += c.positivos
        por_estrato[c.estrato][1] += c.n
    total = sum(n for _, n in por_estrato.values())
    if total == 0:
        return {"classe": classe, "estrato": list(estrato), "prior": None,
                "motivo": "sem contagem de outro talhão compatível"}
    # média com meia planta de cada lado (Jeffreys): zero positivos não vira Beta(0, b)
    p = (sum(x for x, _ in por_estrato.values()) + 0.5) / (total + 1.0)
    kappa = concentracao(list(map(tuple, por_estrato.values())), forca_maxima=forca_maxima)
    x_s, n_s = por_estrato.get(estrato, (0, 0))
    a, b = kappa * p + x_s, kappa * (1 - p) + (n_s - x_s)
    if a + b > forca_maxima:  # encolhe a força, mantém a média
        escala = forca_maxima / (a + b)
        a, b = a * escala, b * escala
    return {"classe": classe, "estrato": list(estrato), "prior": Beta(a, b).to_dict(),
            "kappa": round(kappa, 3), "media_geral": round(p, 6),
            "plantas_de_outros_talhoes": total, "plantas_do_estrato": n_s,
            "talhoes": len({c.origem for c in outras})}


def _lbeta(a: float, b: float) -> float:
    return math.lgamma(a) + math.lgamma(b) - math.lgamma(a + b)


def log_preditiva(x: int, n: int, prior: Beta) -> float:
    """log P(x de n | Beta-binomial(prior))."""
    return (math.lgamma(n + 1) - math.lgamma(x + 1) - math.lgamma(n - x + 1)
            + _lbeta(prior.alfa + x, prior.beta + n - x) - _lbeta(prior.alfa, prior.beta))


def avaliar(contagens: Sequence[Contagem], *, classe: str, referencia: Beta,
            forca_maxima: float = FORCA_MAXIMA) -> dict[str, Any]:
    """Deixa-um-talhão-de-fora: o dado de cada talhão sob o prior fundido sem ele, contra o
    prior de referência. Distribui só se a média não piora."""
    por_origem: dict[str, list[Contagem]] = defaultdict(list)
    for c in contagens:
        if c.classe == classe:
            por_origem[c.origem].append(c)
    linhas = []
    for origem, cs in sorted(por_origem.items()):
        for estrato in sorted({c.estrato for c in cs}):
            x = sum(c.positivos for c in cs if c.estrato == estrato)
            n = sum(c.n for c in cs if c.estrato == estrato)
            fundido = prior_para(contagens, destino=origem, estrato=estrato, classe=classe,
                                 forca_maxima=forca_maxima)["prior"]
            if fundido is None:
                continue
            fb = Beta(fundido["alfa"], fundido["beta"])
            linhas.append({"talhao": origem, "estrato": list(estrato), "x": x, "n": n,
                           "log_fundido": round(log_preditiva(x, n, fb), 4),
                           "log_referencia": round(log_preditiva(x, n, referencia), 4)})
    if not linhas:
        return {"classe": classe, "distribuir": False, "motivo": "nada para avaliar",
                "linhas": []}
    ganho = sum(r["log_fundido"] - r["log_referencia"] for r in linhas) / len(linhas)
    return {"classe": classe, "distribuir": ganho >= 0.0, "ganho_medio_log": round(ganho, 4),
            "motivo": None if ganho >= 0 else "o prior fundido prevê pior que a referência",
            "linhas": linhas}


def carga(contagens: Sequence[Contagem]) -> dict[str, Any]:
    """A representação compartilhada de um talhão/Rover num dia (o que subiria, se o Rover a
    montasse): por estrato e classe, x de n, com o protocolo e a janela — sem os ids (que
    ficam na plataforma, para o anti-eco)."""
    if not contagens:
        return {"protocolo": None, "contagens": []}
    p = contagens[0].protocolo
    return {"protocolo": {"taxonomia_sha256": p.taxonomia_sha256, "modelo": p.modelo,
                          "cabeca": p.cabeca, "validacao": p.validacao},
            "janela": [min(c.inicio for c in contagens).isoformat(),
                       max(c.fim for c in contagens).isoformat()],
            "contagens": [[*c.estrato, c.classe, c.positivos, c.n]
                          for c in sorted(contagens, key=lambda c: (c.estrato, c.classe))]}


def tamanho(objeto: Any) -> dict[str, int]:
    """Bytes do JSON canônico e do gzip dele (medidos, não estimados)."""
    bruto = json.dumps(objeto, sort_keys=True, ensure_ascii=False,
                       separators=(",", ":")).encode()
    return {"json_bytes": len(bruto), "gzip_bytes": len(gzip.compress(bruto, mtime=0))}


# ---------------------------------------------------------------------------------------------
# Com o banco: as contagens validadas do cliente, por talhão e versão de modelo
# ---------------------------------------------------------------------------------------------

VALIDACAO = "agronomo"
"""O protocolo de validação que entra: diagnóstico conferido pelo agrônomo (confirmado ou
recusado, com o rótulo efetivo dele)."""


def estrato_do_talhao(campo) -> tuple[str, str, str]:
    """(variedade, solo, estágio). O cadastro do talhão ainda não tem solo: ``"?"``."""
    return ((campo.variety or "?").strip().lower() or "?", "?",
            (campo.crop_stage or "?").strip().lower() or "?")


def contagens_do_cliente(session, tenant_id: str, *, inicio: date, fim: date
                         ) -> tuple[list[Contagem], dict[str, Protocolo]]:
    """As contagens conferidas pelo agrônomo, por (talhão, modelo, cabeça), e o protocolo de
    cada modelo/cabeça. Só do próprio cliente: entre clientes é decisão do Pedro (LGPD,
    consentimento próprio — o de treino não cobre)."""
    from datetime import UTC, datetime, time

    from sqlalchemy import select

    from valtexa.models import Detection, Diagnosis, DiagnosisStatus, Field

    ini = datetime.combine(inicio, time.min, tzinfo=UTC)
    fim_dt = datetime.combine(fim, time.max, tzinfo=UTC)
    linhas = session.execute(
        select(Diagnosis, Detection, Field)
        .join(Detection, Detection.id == Diagnosis.primary_detection_id)
        .join(Field, Field.id == Diagnosis.field_id)
        .where(Diagnosis.tenant_id == tenant_id,
               Diagnosis.status.in_((DiagnosisStatus.HUMAN_CONFIRMED,
                                     DiagnosisStatus.HUMAN_REJECTED)),
               Diagnosis.reviewed_at >= ini, Diagnosis.reviewed_at <= fim_dt)
        .order_by(Diagnosis.reviewed_at, Diagnosis.id)).all()
    grupos: dict[tuple[str, str, str], dict[str, Any]] = {}
    protocolos: dict[str, Protocolo] = {}
    for diag, det, campo in linhas:
        modelo = det.model_key or campo.ai_model or "?"
        cabeca = det.model_version or "?"
        classes = sorted((det.probabilities or {}).keys())
        if not classes:
            continue
        chave_p = f"{modelo}@{cabeca}"
        protocolos.setdefault(chave_p, Protocolo(Protocolo.taxonomia(classes), modelo, cabeca,
                                                 VALIDACAO))
        g = grupos.setdefault((campo.id, chave_p, "|".join(estrato_do_talhao(campo))), {
            "estrato": estrato_do_talhao(campo), "classes": classes, "obs": {}, "datas": []})
        efetivo = diag.reviewed_label or (diag.label if diag.status is
                                          DiagnosisStatus.HUMAN_CONFIRMED else None)
        g["obs"][diag.observation_id] = efetivo
        g["datas"].append(diag.reviewed_at.date())
    saida = []
    for (campo_id, chave_p, _), g in sorted(grupos.items()):
        obs = frozenset(g["obs"])
        for classe in g["classes"]:
            saida.append(Contagem(
                origem=campo_id, estrato=g["estrato"], classe=classe, observacoes=obs,
                positivas=frozenset(o for o, rotulo in g["obs"].items() if rotulo == classe),
                inicio=min(g["datas"]), fim=max(g["datas"]), protocolo=protocolos[chave_p]))
    return saida, protocolos
