"""Recuperação local (RAG) sobre o repositório de conhecimento: BM25 com filtros.

**Sem chamada externa** (nem de embedding): o índice é montado na hora, em memória, sobre os
trechos que passam pelos filtros — cultura, alvo e tipo — e que o cliente pode ler (as fontes
da plataforma e as dele). Para o tamanho de um repositório agronômico de fazenda (centenas de
documentos, dezenas de milhares de trechos) isso cabe numa requisição; acima disso, um índice
persistido (FTS do Postgres) entra atrás da mesma função — ver ``docs/CEREBRO.md``.

Cada resultado é **citável**: documento, versão, trecho, ``sha256`` do trecho e do documento,
e a situação regulatória (:func:`~valtexa.cerebro.conhecimento.situacao`). O parecer cita o
trecho pelo identificador ``F<n>``; quem audita confere ``conteudo[inicio:fim]`` contra o hash.

Tokenização: minúsculas, sem acento, palavras de 2+ letras, sem as palavras vazias mais comuns
do português, e o plural simples cortado ("folhas" → "folha"). Não há sinônimo nem radical
morfológico: "ferrugem" não acha "Hemileia" — por isso a consulta do parecer leva os nomes do
alvo (:data:`NOMES_ALVO`).
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from valtexa.cerebro import conhecimento
from valtexa.config import settings
from valtexa.models.cerebro import DocumentoConhecimento, TrechoConhecimento

K1 = 1.5
B = 0.75

_PALAVRAS_VAZIAS = (
    "a o as os de da do das dos e em no na nos nas um uma uns umas por para com sem que se "
    "ao aos ou como mais menos muito pela pelo pelas pelos sua seu suas seus ser sao foi sobre "
    "entre ate apos quando onde este esta estes estas esse essa isso nao sim tem the of and")
STOP = frozenset(_PALAVRAS_VAZIAS.split())

NOMES_ALVO: dict[str, tuple[str, ...]] = {
    # café (foco da rodada 4)
    "Rust": ("ferrugem", "ferrugem do cafeeiro", "Hemileia vastatrix"),
    "Cercospora_Leaf_Spot": ("cercosporiose", "mancha de olho pardo", "Cercospora coffeicola"),
    "Phoma_Leaf_Spot": ("phoma", "mancha de phoma", "Phoma tarda"),
    "Leaf_Miner_Damage": ("bicho-mineiro", "Leucoptera coffeella"),
    "Leucoptera_coffeella": ("bicho-mineiro", "Leucoptera coffeella"),
    "Healthy": ("sadia",),
}
"""Os nomes que uma fonte usa para cada classe do modelo. Só nomes de doença/praga, nenhuma
informação de manejo: o conteúdo vem sempre do documento."""


def nomes_do_alvo(rotulo: str) -> tuple[str, ...]:
    return (rotulo, *NOMES_ALVO.get(rotulo, ()))


def _dobra(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", texto.lower())
                   if not unicodedata.combining(c))


def tokens(texto: str) -> list[str]:
    saida = []
    for t in re.findall(r"[a-z0-9]+", _dobra(texto)):
        if len(t) < 2 or t in STOP:
            continue
        if len(t) > 4 and t.endswith("s") and not t.endswith("ss"):
            t = t[:-1]
        saida.append(t)
    return saida


@dataclass(frozen=True)
class Filtros:
    cultura: str | None = None
    alvos: tuple[str, ...] = ()
    """Qualquer um destes (rótulo do modelo ou nome) no ``alvos`` do documento."""
    tipos: tuple[str, ...] = ()
    incluir_substituidos: bool = False


def _alvo_bate(doc_alvos: list[str], pedidos: tuple[str, ...]) -> bool:
    if not pedidos:
        return True
    dobrados = {_dobra(a) for a in doc_alvos}
    desejados = {_dobra(n) for p in pedidos for n in nomes_do_alvo(p)}
    return bool(dobrados & desejados)


def _cultura_bate(doc_culturas: list[str], cultura: str | None) -> bool:
    # Documento sem cultura declarada não entra numa busca por cultura: a regra de "valer para
    # a cultura" é do documento dizer, não da busca supor.
    return cultura is None or _dobra(cultura) in {_dobra(c) for c in doc_culturas}


def candidatos(session: Session, tenant_id: str | None, filtros: Filtros
               ) -> list[tuple[DocumentoConhecimento, TrechoConhecimento]]:
    docs = session.scalars(select(DocumentoConhecimento).where(
        conhecimento.visiveis(tenant_id))).all()
    escolhidos = {
        d.id: d for d in docs
        if (filtros.incluir_substituidos or d.estado == "vigente")
        # Fictício é dado de teste: em produção não é nem recuperado (a ingestão já recusa;
        # isto pega o que tenha entrado antes, por cópia de banco de homologação).
        and not (d.ficticio and settings.is_production)
        and (not filtros.tipos or d.tipo in filtros.tipos)
        and _cultura_bate(list(d.culturas or []), filtros.cultura)
        and _alvo_bate(list(d.alvos or []), filtros.alvos)
    }
    if not escolhidos:
        return []
    trechos = session.scalars(select(TrechoConhecimento).where(
        TrechoConhecimento.documento_id.in_(list(escolhidos))).order_by(
        TrechoConhecimento.documento_id, TrechoConhecimento.ordem)).all()
    return [(escolhidos[t.documento_id], t) for t in trechos]


def buscar(session: Session, tenant_id: str | None, consulta: str, filtros: Filtros, *,
           hoje: date, limite: int = 5) -> list[dict[str, Any]]:
    """Os ``limite`` trechos de maior BM25 para a consulta, com a citação completa.

    Empate no escore sai pela ordem do documento e do trecho (determinístico: o mesmo
    repositório e a mesma consulta dão a mesma lista).
    """
    pares = candidatos(session, tenant_id, filtros)
    termos = tokens(consulta)
    if not pares or not termos:
        return []
    docs_tokens = [tokens(t.texto + " " + (t.secao or "") + " " + d.titulo) for d, t in pares]
    n = len(docs_tokens)
    media = sum(len(x) for x in docs_tokens) / n or 1.0
    df: Counter[str] = Counter()
    for toks in docs_tokens:
        df.update(set(toks))
    escores = []
    for i, toks in enumerate(docs_tokens):
        tf = Counter(toks)
        s = 0.0
        for termo in set(termos):
            if termo not in tf:
                continue
            idf = math.log(1 + (n - df[termo] + 0.5) / (df[termo] + 0.5))
            s += idf * tf[termo] * (K1 + 1) / (tf[termo] + K1 * (1 - B + B * len(toks) / media))
        if s > 0:
            escores.append((s, i))
    escores.sort(key=lambda par: (-par[0], par[1]))
    saida = []
    for s, i in escores[:limite]:
        doc, trecho = pares[i]
        saida.append(citacao(doc, trecho, hoje, escore=s))
    return saida


def citacao(doc: DocumentoConhecimento, trecho: TrechoConhecimento, hoje: date, *,
            escore: float | None = None) -> dict[str, Any]:
    return {
        "documento_id": doc.id, "chave": doc.chave, "versao": doc.versao,
        "titulo": doc.titulo, "tipo": doc.tipo, "origem": doc.origem, "licenca": doc.licenca,
        "escopo": "plataforma" if doc.tenant_id is None else "cliente",
        "sha256_documento": doc.sha256, "trecho_id": trecho.id, "ordem": trecho.ordem,
        "secao": trecho.secao, "inicio": trecho.inicio, "fim": trecho.fim,
        "sha256_trecho": trecho.sha256, "texto": trecho.texto,
        "alvos": list(doc.alvos or []), "culturas": list(doc.culturas or []),
        "ficticio": doc.ficticio, "estado": doc.estado,
        "verificado_em": doc.verificado_em and doc.verificado_em.isoformat(),
        "valido_ate": doc.valido_ate and doc.valido_ate.isoformat(),
        "escore": None if escore is None else round(escore, 4),
        **conhecimento.situacao(doc, hoje).to_dict(),
    }


def confere_citacao(session: Session, cit: dict[str, Any]) -> bool:
    """O trecho citado ainda é o que estava lá: mesmo texto, mesmo hash, mesma posição."""
    doc = session.get(DocumentoConhecimento, cit.get("documento_id"))
    trecho = session.get(TrechoConhecimento, cit.get("trecho_id"))
    if doc is None or trecho is None or trecho.documento_id != doc.id:
        return False
    recorte = doc.conteudo[trecho.inicio:trecho.fim]
    return (doc.sha256 == cit.get("sha256_documento") == conhecimento.sha256_texto(doc.conteudo)
            and trecho.sha256 == cit.get("sha256_trecho") == conhecimento.sha256_texto(recorte))
