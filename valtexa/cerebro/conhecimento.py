"""Repositório de conhecimento versionado: ingestão, versões e a regra do regulatório.

Cada documento entra **numa versão**, com origem, data de publicação, ``verificado_em``,
``valido_ate``, ``sha256`` do conteúdo e licença. A versão é imutável: o mesmo
``(chave, versao)`` com outro conteúdo é recusado; uma versão nova do mesmo documento é outra
linha, e a anterior passa a ``substituido`` (fica para a auditoria: o parecer de ontem cita a
versão que valia ontem).

**Regulatório** (bula, registro MAPA): só vale para **recomendação operacional** quando
está vigente, verificado, dentro de ``valido_ate`` e não é fictício
(:func:`situacao`). Vencido ou não verificado continua consultável — o parecer mostra a
fonte e diz que ela **bloqueia** o uso operacional.

**Nada é inventado aqui.** O repositório nasce vazio; sem fonte real carregada, o parecer diz
"sem fonte". Dados de exemplo só nos testes, com ``ficticio=True`` — que nunca vale na
operação e é recusado em produção.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from valtexa.models import ActorType, SubjectType
from valtexa.models.cerebro import (
    TIPOS_DOCUMENTO,
    TIPOS_REGULATORIOS,
    DocumentoConhecimento,
    TrechoConhecimento,
)
from valtexa.services import audit

FORMATOS = ("texto", "markdown")
MAX_BYTES = 2_000_000
"""Teto do conteúdo de um documento (texto puro). Bula inteira cabe com folga."""
TAMANHO_TRECHO = 900
"""Caracteres por trecho (aproximado: o corte respeita parágrafo)."""
CHAVE = re.compile(r"^[a-z0-9][a-z0-9:._/-]{1,119}$")


class DocumentoInvalidoError(ValueError):
    """Metadado faltando ou errado, conteúdo inválido ou versão que já existe com outro texto."""


@dataclass(frozen=True)
class Situacao:
    """Se o documento pode embasar uma recomendação operacional, e por quê não."""

    regulatorio: bool
    uso_operacional: bool
    motivo: str | None

    def to_dict(self) -> dict[str, Any]:
        return {"regulatorio": self.regulatorio, "uso_operacional": self.uso_operacional,
                "bloqueio": self.motivo}


def situacao(doc: DocumentoConhecimento, hoje: date) -> Situacao:
    """A regra do 8.1: regulatório vencido ou não verificado **bloqueia** a operação.

    Fonte técnica (Embrapa, artigo, escala) nunca embasa dose, alvo ou registro — ela é
    contexto; por isso ``uso_operacional`` dela também é falso, mas sem "bloqueio": o motivo
    diz que não é fonte regulatória.
    """
    regulatorio = doc.tipo in TIPOS_REGULATORIOS
    if doc.ficticio:
        return Situacao(regulatorio, False, "fictício: dado de teste, nunca vale na operação")
    if doc.estado != "vigente":
        return Situacao(regulatorio, False, f"versão {doc.estado}")
    if not regulatorio:
        return Situacao(False, False, None)
    if doc.verificado_em is None:
        return Situacao(True, False, "não verificado na versão vigente")
    if doc.verificado_em > hoje:
        return Situacao(True, False, "data de verificação no futuro")
    if doc.valido_ate is None:
        return Situacao(True, False, "sem validade declarada (valido_ate)")
    if doc.valido_ate < hoje:
        return Situacao(True, False, f"vencido em {doc.valido_ate.isoformat()}")
    return Situacao(True, True, None)


def sha256_texto(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------------------------
# Metadados e trechos
# ---------------------------------------------------------------------------------------------

OBRIGATORIOS = ("chave", "versao", "titulo", "tipo", "origem", "licenca")


def _data(valor: Any, campo: str) -> date | None:
    if valor in (None, ""):
        return None
    if isinstance(valor, date):
        return valor
    try:
        return date.fromisoformat(str(valor))
    except ValueError as exc:
        raise DocumentoInvalidoError(f"{campo}: data inválida {valor!r} (use AAAA-MM-DD).") from exc


def _lista(valor: Any, campo: str) -> list[str]:
    if valor in (None, ""):
        return []
    if not isinstance(valor, list) or not all(isinstance(v, str) and v.strip() for v in valor):
        raise DocumentoInvalidoError(f"{campo}: lista de textos.")
    return [v.strip() for v in valor][:50]


def valida_metadados(meta: dict[str, Any]) -> dict[str, Any]:
    """Confere e normaliza. Não preenche nada que não veio: sem licença, sem origem, recusa."""
    if not isinstance(meta, dict):
        raise DocumentoInvalidoError("metadados: objeto JSON.")
    faltando = [c for c in OBRIGATORIOS if not str(meta.get(c) or "").strip()]
    if faltando:
        raise DocumentoInvalidoError(f"metadados obrigatórios faltando: {', '.join(faltando)}.")
    chave = str(meta["chave"]).strip().lower()
    if not CHAVE.match(chave):
        raise DocumentoInvalidoError("chave: minúsculas, dígitos e : . _ / - (2 a 120).")
    tipo = str(meta["tipo"]).strip()
    if tipo not in TIPOS_DOCUMENTO:
        raise DocumentoInvalidoError(f"tipo: um de {', '.join(TIPOS_DOCUMENTO)}.")
    desconhecidos = set(meta) - {*OBRIGATORIOS, "publicado_em", "verificado_em", "valido_ate",
                                 "culturas", "alvos", "ficticio"}
    if desconhecidos:
        raise DocumentoInvalidoError(
            f"metadados desconhecidos: {', '.join(sorted(desconhecidos))}.")
    saida = {
        "chave": chave,
        "versao": str(meta["versao"]).strip()[:40],
        "titulo": str(meta["titulo"]).strip()[:300],
        "tipo": tipo,
        "origem": str(meta["origem"]).strip()[:500],
        "licenca": str(meta["licenca"]).strip()[:200],
        "publicado_em": _data(meta.get("publicado_em"), "publicado_em"),
        "verificado_em": _data(meta.get("verificado_em"), "verificado_em"),
        "valido_ate": _data(meta.get("valido_ate"), "valido_ate"),
        "culturas": [c.lower() for c in _lista(meta.get("culturas"), "culturas")],
        "alvos": _lista(meta.get("alvos"), "alvos"),
        "ficticio": bool(meta.get("ficticio", False)),
    }
    if (saida["verificado_em"] and saida["valido_ate"]
            and saida["valido_ate"] < saida["verificado_em"]):
        raise DocumentoInvalidoError("valido_ate antes de verificado_em.")
    return saida


_TITULO_MD = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$")


def fatiar(conteudo: str, formato: str = "texto",
           tamanho: int = TAMANHO_TRECHO) -> list[dict[str, Any]]:
    """Trechos por parágrafo, juntados até ``tamanho``; ``conteudo[inicio:fim] == texto``.

    No Markdown, o título mais recente vira a ``secao`` do trecho (a citação diz de onde no
    documento ele veio). Um parágrafo maior que ``tamanho`` vira um trecho só, inteiro: cortar
    no meio da frase quebraria a citação.
    """
    paragrafos: list[tuple[int, int, str | None]] = []
    secao: str | None = None
    for m in re.finditer(r"[^\n]+(?:\n[^\n]+)*", conteudo):
        bloco = m.group(0)
        if not bloco.strip():
            continue
        if formato == "markdown":
            titulo = _TITULO_MD.match(bloco.splitlines()[0])
            if titulo:
                secao = titulo.group(1)[:300]
        paragrafos.append((m.start(), m.end(), secao))
    trechos: list[dict[str, Any]] = []
    atual: list[tuple[int, int, str | None]] = []

    def fecha() -> None:
        if not atual:
            return
        inicio, fim = atual[0][0], atual[-1][1]
        texto = conteudo[inicio:fim]
        trechos.append({"ordem": len(trechos), "secao": atual[0][2], "texto": texto,
                        "inicio": inicio, "fim": fim, "sha256": sha256_texto(texto)})
        atual.clear()

    for p in paragrafos:
        if atual and (p[1] - atual[0][0] > tamanho or p[2] != atual[0][2]):
            fecha()
        atual.append(p)
    fecha()
    return trechos


# ---------------------------------------------------------------------------------------------
# Ingestão
# ---------------------------------------------------------------------------------------------


def _mesmo_escopo(tenant_id: str | None):
    return (DocumentoConhecimento.tenant_id.is_(None) if tenant_id is None
            else DocumentoConhecimento.tenant_id == tenant_id)


def ingerir(
    session: Session,
    *,
    tenant_id: str | None,
    metadados: dict[str, Any],
    conteudo: str,
    formato: str = "texto",
    arquivo_nome: str | None = None,
    ator_id: str | None = None,
    producao: bool = False,
) -> tuple[DocumentoConhecimento, bool]:
    """Guarda uma versão de documento. ``(documento, criado)``; reenviar o mesmo é idempotente.

    ``tenant_id`` nulo: fonte da plataforma. Não faz *commit*.
    """
    meta = valida_metadados(metadados)
    if formato not in FORMATOS:
        raise DocumentoInvalidoError(f"formato: um de {', '.join(FORMATOS)}.")
    if not isinstance(conteudo, str) or not conteudo.strip():
        raise DocumentoInvalidoError("conteúdo vazio.")
    if len(conteudo.encode("utf-8")) > MAX_BYTES:
        raise DocumentoInvalidoError(f"conteúdo maior que {MAX_BYTES} bytes.")
    if meta["ficticio"] and producao:
        raise DocumentoInvalidoError("documento fictício não entra em produção.")
    digest = sha256_texto(conteudo)
    session.flush()  # a sessão pode não ter autoflush: o que veio antes nesta transação conta
    existente = session.scalars(select(DocumentoConhecimento).where(
        _mesmo_escopo(tenant_id), DocumentoConhecimento.chave == meta["chave"],
        DocumentoConhecimento.versao == meta["versao"])).first()
    if existente is not None:
        if existente.sha256 == digest:
            return existente, False
        raise DocumentoInvalidoError(
            f"{meta['chave']} versão {meta['versao']} já existe com outro conteúdo: "
            "versão é imutável — publique uma versão nova.")
    doc = DocumentoConhecimento(
        tenant_id=tenant_id, formato=formato, arquivo_nome=(arquivo_nome or None),
        conteudo=conteudo, sha256=digest, estado="vigente", ingerido_por=ator_id,
        verificado_por=ator_id if meta["verificado_em"] else None, **meta)
    session.add(doc)
    session.flush()
    anteriores = session.scalars(select(DocumentoConhecimento).where(
        _mesmo_escopo(tenant_id), DocumentoConhecimento.chave == meta["chave"],
        DocumentoConhecimento.estado == "vigente", DocumentoConhecimento.id != doc.id)).all()
    for velho in anteriores:
        velho.estado, velho.substituido_por = "substituido", doc.id
    for t in fatiar(conteudo, formato):
        session.add(TrechoConhecimento(documento_id=doc.id, tenant_id=tenant_id, **t))
    audit.record(
        session, tenant_id=tenant_id, action="fonte.ingerida", subject_type=SubjectType.FONTE,
        subject_id=doc.id, actor_type=ActorType.USER if ator_id else ActorType.SYSTEM,
        actor_id=ator_id, new_state="vigente",
        payload={"chave": doc.chave, "versao": doc.versao, "tipo": doc.tipo,
                 "sha256": digest, "substituiu": [v.id for v in anteriores],
                 "ficticio": doc.ficticio})
    session.flush()
    return doc, True


def verificar(session: Session, doc: DocumentoConhecimento, *, verificado_em: date,
              valido_ate: date, ator_id: str) -> DocumentoConhecimento:
    """Alguém conferiu esta versão contra a fonte oficial. Não muda o conteúdo (o hash fica)."""
    if valido_ate < verificado_em:
        raise DocumentoInvalidoError("valido_ate antes de verificado_em.")
    antes = {"verificado_em": doc.verificado_em and doc.verificado_em.isoformat(),
             "valido_ate": doc.valido_ate and doc.valido_ate.isoformat()}
    doc.verificado_em, doc.valido_ate, doc.verificado_por = verificado_em, valido_ate, ator_id
    audit.record(session, tenant_id=doc.tenant_id, action="fonte.verificada",
                 subject_type=SubjectType.FONTE, subject_id=doc.id, actor_type=ActorType.USER,
                 actor_id=ator_id, payload={"antes": antes, "verificado_em":
                                            verificado_em.isoformat(),
                                            "valido_ate": valido_ate.isoformat(),
                                            "sha256": doc.sha256})
    session.flush()
    return doc


def visiveis(tenant_id: str | None):
    """Filtro: as fontes que um cliente lê — as da plataforma e as dele, nunca as de outro."""
    if tenant_id is None:
        return DocumentoConhecimento.tenant_id.is_(None)
    return or_(DocumentoConhecimento.tenant_id.is_(None),
               DocumentoConhecimento.tenant_id == tenant_id)


def resumo(doc: DocumentoConhecimento, hoje: date) -> dict[str, Any]:
    return {
        "id": doc.id, "escopo": "plataforma" if doc.tenant_id is None else "cliente",
        "chave": doc.chave, "versao": doc.versao, "titulo": doc.titulo, "tipo": doc.tipo,
        "origem": doc.origem, "licenca": doc.licenca,
        "publicado_em": doc.publicado_em and doc.publicado_em.isoformat(),
        "verificado_em": doc.verificado_em and doc.verificado_em.isoformat(),
        "valido_ate": doc.valido_ate and doc.valido_ate.isoformat(),
        "sha256": doc.sha256, "culturas": list(doc.culturas or []),
        "alvos": list(doc.alvos or []), "ficticio": doc.ficticio, "estado": doc.estado,
        "substituido_por": doc.substituido_por, "formato": doc.formato,
        "arquivo_nome": doc.arquivo_nome, "ingerido_em": doc.created_at.isoformat(),
        **situacao(doc, hoje).to_dict(),
    }


# ---------------------------------------------------------------------------------------------
# Arquivo
# ---------------------------------------------------------------------------------------------


def ler_arquivo(caminho: Path | str, meta_caminho: Path | str | None = None
                ) -> tuple[dict[str, Any], str, str]:
    """``(metadados, conteudo, formato)`` de um arquivo ``.md``/``.txt`` e do ``.meta.json``.

    O metadado mora ao lado (``bula-x.md`` + ``bula-x.meta.json``): o texto do documento fica
    como veio da fonte, sem cabeçalho inventado. PDF não é lido aqui (sem dependência nova):
    extraia o texto antes e registre a extração na ``origem``.
    """
    caminho = Path(caminho)
    if caminho.suffix.lower() not in (".md", ".txt"):
        raise DocumentoInvalidoError("arquivo: .md ou .txt (texto UTF-8).")
    meta_caminho = Path(meta_caminho) if meta_caminho else caminho.with_suffix(".meta.json")
    if not meta_caminho.is_file():
        raise DocumentoInvalidoError(f"sem metadados: {meta_caminho.name} não existe.")
    bruto = caminho.read_bytes()
    if len(bruto) > MAX_BYTES:
        raise DocumentoInvalidoError(f"arquivo maior que {MAX_BYTES} bytes.")
    try:
        # Quebra de linha do Windows não é conteúdo: o mesmo documento salvo em outro sistema
        # tem de dar o mesmo hash (e a mesma versão não ser recusada por "outro texto").
        conteudo = bruto.decode("utf-8").replace("\r\n", "\n")
        meta = json.loads(meta_caminho.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DocumentoInvalidoError(f"arquivo ilegível: {exc}") from exc
    formato = "markdown" if caminho.suffix.lower() == ".md" else "texto"
    return meta, conteudo, formato
