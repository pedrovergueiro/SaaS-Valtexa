"""Cérebro agronômico: fontes de conhecimento, busca, pareceres e a revisão do agrônomo.

Ver ``valtexa/cerebro/`` e ``docs/CEREBRO.md``. Permissões:

* ler fontes, buscar e ler parecer — ``diagnosis:read``;
* pedir parecer — ``parecer:generate`` (dono, gestor, agrônomo);
* revisar parecer — ``diagnosis:review`` (só o agrônomo);
* ingerir/verificar fonte do cliente — ``knowledge:manage``; fonte da plataforma —
  ``platform:knowledge:manage`` (equipe da ValTexa).

Nenhuma destas rotas cria missão, aprova prescrição ou aplicação, muda limiar de modelo ou
chama o Safety Engine (Princípio de Ouro; ``tests/test_cerebro_principio.py``).
"""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from pydantic import Field as Campo
from sqlalchemy import select
from sqlalchemy.orm import Session

from valtexa.api.deps import (
    PlatformCaller,
    Principal,
    get_scoped,
    require,
    require_platform,
    scoped,
)
from valtexa.cerebro import conhecimento, dossie, provedor, rag, servico
from valtexa.config import settings
from valtexa.db import get_session
from valtexa.models import (
    AuditEntry,
    Diagnosis,
    Field,
    Observation,
    SubjectType,
    as_utc,
    utcnow,
)
from valtexa.models.cerebro import (
    DECISOES_REVISAO,
    TIPOS_DOCUMENTO,
    DocumentoConhecimento,
    Parecer,
    RevisaoParecer,
    TrechoConhecimento,
)
from valtexa.security import rbac
from valtexa.services import ensino

router = APIRouter(tags=["cérebro agronômico"])

PLANT_REF = r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$"


def fonte_da_ia() -> dossie.FonteDaIA:
    """As leituras da IA para o dossiê (o teste troca por um dublê)."""
    return dossie.FonteDaIAPadrao()


def _hoje() -> date:
    return utcnow().date()


# ---------------------------------------------------------------------------------------------
# Corpos
# ---------------------------------------------------------------------------------------------


class MetadadosIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chave: str = Campo(min_length=2, max_length=120)
    versao: str = Campo(min_length=1, max_length=40)
    titulo: str = Campo(min_length=1, max_length=300)
    tipo: Literal[TIPOS_DOCUMENTO]  # type: ignore[valid-type]
    origem: str = Campo(min_length=1, max_length=500)
    licenca: str = Campo(min_length=1, max_length=200)
    publicado_em: date | None = None
    verificado_em: date | None = None
    valido_ate: date | None = None
    culturas: list[str] = Campo(default_factory=list, max_length=50)
    alvos: list[str] = Campo(default_factory=list, max_length=50)
    ficticio: bool = False


class DocumentoIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metadados: MetadadosIn
    conteudo: str = Campo(min_length=1, max_length=conhecimento.MAX_BYTES,
                          description="O texto do arquivo, como veio da fonte (UTF-8).")
    formato: Literal["texto", "markdown"] = "texto"
    arquivo_nome: str | None = Campo(default=None, max_length=255)


class VerificacaoIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verificado_em: date
    valido_ate: date


class ParecerIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    caso: Literal["planta", "observacao"]
    plant_ref: str | None = Campo(default=None, pattern=PLANT_REF)
    observation_id: str | None = Campo(default=None, max_length=32)


class RevisaoIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decisao: Literal[DECISOES_REVISAO]  # type: ignore[valid-type]
    comentario: str | None = Campo(default=None, max_length=4000)
    diagnostico_revisor: str | None = Campo(default=None, max_length=80)
    registrar_diagnostico: bool = Campo(
        default=False,
        description="Discordando num caso de observação: registra o diagnóstico dele na "
        "observação, como na fila (vira amostra de treino e refaz a decisão).")


# ---------------------------------------------------------------------------------------------
# Fontes
# ---------------------------------------------------------------------------------------------


def _ingere(session: Session, tenant_id: str | None, pedido: DocumentoIn,
            ator_id: str) -> dict[str, Any]:
    try:
        doc, criado = conhecimento.ingerir(
            session, tenant_id=tenant_id, metadados=pedido.metadados.model_dump(),
            conteudo=pedido.conteudo, formato=pedido.formato, arquivo_nome=pedido.arquivo_nome,
            ator_id=ator_id, producao=settings.is_production)
    except conhecimento.DocumentoInvalidoError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    session.commit()
    return {**conhecimento.resumo(doc, _hoje()), "criado": criado}


def _visivel(session: Session, documento_id: str, tenant_id: str | None
             ) -> DocumentoConhecimento:
    doc = session.get(DocumentoConhecimento, documento_id)
    if doc is None or doc.tenant_id not in (None, tenant_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Fonte não encontrada.")
    return doc


def _lista(session: Session, tenant_id: str | None, *, tipo: str | None, cultura: str | None,
           incluir_substituidos: bool, so_plataforma: bool = False) -> list[dict[str, Any]]:
    q = select(DocumentoConhecimento).where(
        DocumentoConhecimento.tenant_id.is_(None) if so_plataforma
        else conhecimento.visiveis(tenant_id))
    if tipo:
        q = q.where(DocumentoConhecimento.tipo == tipo)
    if not incluir_substituidos:
        q = q.where(DocumentoConhecimento.estado == "vigente")
    hoje = _hoje()
    docs = session.scalars(q.order_by(DocumentoConhecimento.chave,
                                      DocumentoConhecimento.created_at)).all()
    return [conhecimento.resumo(d, hoje) for d in docs
            if cultura is None or cultura.lower() in (d.culturas or [])]


@router.get("/cerebro/fontes", summary="Fontes de conhecimento que o cliente lê")
def lista_fontes(
    tipo: str | None = Query(default=None),
    cultura: str | None = Query(default=None),
    incluir_substituidos: bool = Query(default=False),
    principal: Principal = Depends(require(rbac.DIAGNOSIS_READ)),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    """As da plataforma e as do cliente, com a situação regulatória de cada uma
    (``uso_operacional``, ``bloqueio``). Vazio até alguém ingerir fonte real."""
    return _lista(session, principal.tenant_id, tipo=tipo, cultura=cultura,
                  incluir_substituidos=incluir_substituidos)


@router.get("/cerebro/fontes/{documento_id}", summary="Uma fonte, com o conteúdo e os trechos")
def detalhe_fonte(
    documento_id: str,
    principal: Principal = Depends(require(rbac.DIAGNOSIS_READ)),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    doc = _visivel(session, documento_id, principal.tenant_id)
    trechos = session.scalars(select(TrechoConhecimento).where(
        TrechoConhecimento.documento_id == doc.id).order_by(TrechoConhecimento.ordem)).all()
    return {**conhecimento.resumo(doc, _hoje()), "conteudo": doc.conteudo,
            "trechos": [{"id": t.id, "ordem": t.ordem, "secao": t.secao, "inicio": t.inicio,
                         "fim": t.fim, "sha256": t.sha256} for t in trechos]}


@router.post("/cerebro/fontes", status_code=status.HTTP_201_CREATED,
             summary="Ingere uma fonte do cliente (histórico da propriedade, bula conferida)")
def ingere_fonte(
    pedido: DocumentoIn,
    principal: Principal = Depends(require(rbac.KNOWLEDGE_MANAGE)),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Uma versão de documento: o mesmo ``(chave, versao)`` com o mesmo conteúdo é idempotente;
    com outro, 422. Só o cliente que ingeriu lê."""
    return _ingere(session, principal.tenant_id, pedido, principal.user_id)


@router.post("/cerebro/fontes/{documento_id}/verificacao",
             summary="Registra a conferência de uma fonte do cliente contra a oficial")
def verifica_fonte(
    documento_id: str,
    pedido: VerificacaoIn,
    principal: Principal = Depends(require(rbac.KNOWLEDGE_MANAGE)),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    doc = _visivel(session, documento_id, principal.tenant_id)
    if doc.tenant_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "Fonte da plataforma: só a equipe da ValTexa registra a verificação.")
    try:
        conhecimento.verificar(session, doc, verificado_em=pedido.verificado_em,
                               valido_ate=pedido.valido_ate, ator_id=principal.user_id)
    except conhecimento.DocumentoInvalidoError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    session.commit()
    return conhecimento.resumo(doc, _hoje())


@router.get("/cerebro/busca", summary="Busca local (BM25) nas fontes, com citação ao trecho")
def busca(
    q: str = Query(min_length=2, max_length=300),
    cultura: str | None = Query(default=None),
    alvo: str | None = Query(default=None),
    tipo: str | None = Query(default=None),
    limite: int = Query(default=5, ge=1, le=20),
    principal: Principal = Depends(require(rbac.DIAGNOSIS_READ)),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    """Sem chamada externa. Cada resultado traz documento, versão, trecho, hashes e a situação
    regulatória — a citação que o parecer usaria."""
    filtros = rag.Filtros(cultura=cultura, alvos=(alvo,) if alvo else (),
                          tipos=(tipo,) if tipo else ())
    return rag.buscar(session, principal.tenant_id, q, filtros, hoje=_hoje(), limite=limite)


@router.get("/platform/cerebro/fontes", summary="Fontes da plataforma (equipe)")
def lista_fontes_plataforma(
    tipo: str | None = Query(default=None),
    incluir_substituidos: bool = Query(default=True),
    _equipe: PlatformCaller = Depends(require_platform(rbac.PLATFORM_KNOWLEDGE_MANAGE)),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    return _lista(session, None, tipo=tipo, cultura=None,
                  incluir_substituidos=incluir_substituidos, so_plataforma=True)


@router.post("/platform/cerebro/fontes", status_code=status.HTTP_201_CREATED,
             summary="Ingere uma fonte da plataforma (bula, MAPA, Embrapa, escala, artigo)")
def ingere_fonte_plataforma(
    pedido: DocumentoIn,
    equipe: PlatformCaller = Depends(require_platform(rbac.PLATFORM_KNOWLEDGE_MANAGE)),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Todo cliente lê. Regulatório sem ``verificado_em``/``valido_ate`` entra, mas fica
    **bloqueado** para uso operacional até a verificação."""
    return _ingere(session, None, pedido, equipe.user_id)


@router.post("/platform/cerebro/fontes/{documento_id}/verificacao",
             summary="Registra a conferência de uma fonte da plataforma")
def verifica_fonte_plataforma(
    documento_id: str,
    pedido: VerificacaoIn,
    equipe: PlatformCaller = Depends(require_platform(rbac.PLATFORM_KNOWLEDGE_MANAGE)),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    doc = session.get(DocumentoConhecimento, documento_id)
    if doc is None or doc.tenant_id is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Fonte da plataforma não encontrada.")
    try:
        conhecimento.verificar(session, doc, verificado_em=pedido.verificado_em,
                               valido_ate=pedido.valido_ate, ator_id=equipe.user_id)
    except conhecimento.DocumentoInvalidoError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    session.commit()
    return conhecimento.resumo(doc, _hoje())


# ---------------------------------------------------------------------------------------------
# Pareceres
# ---------------------------------------------------------------------------------------------


@router.post("/fields/{field_id}/pareceres", status_code=status.HTTP_201_CREATED,
             summary="Gera o parecer de um caso (planta ou observação)")
def gera_parecer(
    field_id: str,
    pedido: ParecerIn,
    principal: Principal = Depends(require(rbac.PARECER_GENERATE)),
    session: Session = Depends(get_session),
    ia: dossie.FonteDaIA = Depends(fonte_da_ia),
) -> dict[str, Any]:
    """Dossiê de evidências → fontes (busca local) → compositor determinístico (padrão) ou
    provedor de linguagem validado. O parecer sai ``aguardando_revisao`` e não autoriza nada."""
    campo = get_scoped(session, Field, field_id, principal)
    if pedido.caso == "planta":
        if not pedido.plant_ref:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                                "caso planta pede plant_ref.")
        caso = dossie.Caso("planta", campo.id, plant_ref=pedido.plant_ref)
    else:
        if not pedido.observation_id:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                                "caso observacao pede observation_id.")
        obs = get_scoped(session, Observation, pedido.observation_id, principal)
        if obs.field_id != campo.id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Observation não encontrado.")
        caso = dossie.Caso("observacao", campo.id, observation_id=obs.id)
    try:
        p = servico.gerar(session, tenant_id=principal.tenant_id, campo=campo, caso=caso, ia=ia,
                          ator_id=principal.user_id, agora=utcnow(),
                          provedor_nome=settings.cerebro_provedor)
    except provedor.ProvedorDesconhecidoError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    session.commit()
    return servico.detalhe(p, [])


@router.get("/fields/{field_id}/pareceres", summary="Pareceres do talhão")
def lista_pareceres(
    field_id: str,
    plant_ref: str | None = Query(default=None, pattern=PLANT_REF),
    principal: Principal = Depends(require(rbac.DIAGNOSIS_READ)),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    get_scoped(session, Field, field_id, principal)
    q = select(Parecer).where(Parecer.tenant_id == principal.tenant_id,
                              Parecer.field_id == field_id)
    if plant_ref:
        q = q.where(Parecer.plant_ref == plant_ref)
    return [servico.resumo(p) for p in session.scalars(
        q.order_by(Parecer.created_at.desc()).limit(200)).all()]


def _revisoes(session: Session, parecer_id: str) -> list[RevisaoParecer]:
    return list(session.scalars(select(RevisaoParecer).where(
        RevisaoParecer.parecer_id == parecer_id).order_by(RevisaoParecer.revisado_em)).all())


@router.get("/pareceres/{parecer_id}", summary="Um parecer: evidências, alternativas, fontes")
def detalhe_parecer(
    parecer_id: str,
    principal: Principal = Depends(require(rbac.DIAGNOSIS_READ)),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    p = get_scoped(session, Parecer, parecer_id, principal)
    return servico.detalhe(p, _revisoes(session, p.id), servico.fontes_hoje(session, p, _hoje()))


@router.get("/pareceres/{parecer_id}/auditoria", summary="Trilha de auditoria do parecer")
def auditoria_parecer(
    parecer_id: str,
    principal: Principal = Depends(require(rbac.DIAGNOSIS_READ)),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    """Quem gerou e quem revisou, quando, com o hash do parecer em cada passo."""
    p = get_scoped(session, Parecer, parecer_id, principal)
    entradas = session.scalars(select(AuditEntry).where(
        AuditEntry.tenant_id == principal.tenant_id,
        AuditEntry.subject_type == SubjectType.PARECER,
        AuditEntry.subject_id == p.id).order_by(AuditEntry.at)).all()
    return [{"id": e.id, "acao": e.action, "ator_tipo": e.actor_type.value,
             "ator_id": e.actor_id, "quando": as_utc(e.at).isoformat(),
             "de": e.old_state, "para": e.new_state, "motivo": e.reason,
             "sessao_de_suporte": e.support_session_id, "dados": e.payload}
            for e in entradas]


@router.post("/pareceres/{parecer_id}/revisao", status_code=status.HTTP_201_CREATED,
             summary="O agrônomo registra a revisão do parecer (não autoriza nada)")
def revisa_parecer(
    parecer_id: str,
    pedido: RevisaoIn,
    principal: Principal = Depends(require(rbac.DIAGNOSIS_REVIEW)),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    p = get_scoped(session, Parecer, parecer_id, principal)
    try:
        servico.revisar(session, p, revisor_id=principal.user_id, papel=principal.role.value,
                        decisao=pedido.decisao, comentario=pedido.comentario,
                        diagnostico_revisor=pedido.diagnostico_revisor, agora=utcnow())
    except servico.RevisaoInvalidaError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    if pedido.decisao == "discorda" and pedido.diagnostico_revisor:
        _licao_da_discordancia(session, principal, p, pedido)
    session.commit()
    return servico.detalhe(p, _revisoes(session, p.id), servico.fontes_hoje(session, p, _hoje()))


def _licao_da_discordancia(session: Session, principal: Principal, p: Parecer,
                           pedido: RevisaoIn) -> None:
    """A discordância do agrônomo é uma lição: o que ele acha que a planta tem e por quê.
    Com ``registrar_diagnostico``, vale como o veredito da fila naquela observação."""
    from pydantic import ValidationError

    from valtexa.api.routers.perception import aplicar_revisao
    from valtexa.schemas import DiagnosisReview

    rotulo = pedido.diagnostico_revisor.strip()
    explicacao = {"porque": pedido.comentario} if pedido.comentario else None
    if pedido.registrar_diagnostico:
        if p.caso_tipo != "observacao" or not p.observation_id:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                                "Registrar o diagnóstico só vale para parecer de observação.")
        diag = session.scalars(scoped(
            select(Diagnosis).where(Diagnosis.observation_id == p.observation_id)
            .order_by(Diagnosis.created_at.desc()), Diagnosis, principal)).first()
        if diag is None:
            raise HTTPException(status.HTTP_409_CONFLICT, "A observação não tem diagnóstico.")
        try:
            veredito = DiagnosisReview(label=rotulo, confirmed=True, notes=pedido.comentario,
                                       explicacao=explicacao)
        except ValidationError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                                "diagnostico_revisor precisa ser um nome de classe (letras, "
                                "números e _), ex.: Rust, Mancha_branca.") from exc
        aplicar_revisao(session, principal, diag, veredito, origem="parecer", parecer_id=p.id)
        return
    ensino.registrar(
        session, tenant_id=principal.tenant_id, field_id=p.field_id, origem="parecer",
        autor=principal.user, rotulo=rotulo,
        rotulo_da_ia=(p.dossie or {}).get("hipoteses", {}).get("principal"),
        explicacao=explicacao, observation_id=p.observation_id, parecer_id=p.id,
        plant_ref=p.plant_ref)
