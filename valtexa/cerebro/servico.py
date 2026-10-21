"""Gerar, consultar e revisar pareceres — com auditoria de cada passo.

O que este módulo **escreve**: ``parecer``, ``revisao_parecer``, ``documento_conhecimento``
(pela ingestão) e ``audit_entry``. Nada mais. Não importa nem chama ``mission_manager``,
``safety_engine``, ``plans``, ``decision_engine`` (só lê a tabela ``decision``) nem o registro
de modelos: o Princípio de Ouro está no que este código **não alcança** — e o teste
``tests/test_cerebro_principio.py`` confere varrendo o código e o banco.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any

from sqlalchemy.orm import Session

from valtexa.cerebro import dossie as dossie_mod
from valtexa.cerebro import parecer as compositor
from valtexa.cerebro import provedor as provedores
from valtexa.cerebro import rag
from valtexa.cerebro.validador import Validador
from valtexa.models import ActorType, Field, SubjectType, as_utc
from valtexa.models.cerebro import DECISOES_REVISAO, Parecer, RevisaoParecer
from valtexa.services import audit

logger = logging.getLogger(__name__)

LIMITE_FONTES = 5
AFIRMACAO_OMITIDA = ("Afirmação omitida: o texto montado não passou na validação de citações "
                     "(ver recusas e o item citado do dossiê).")
LIMITE_REGULATORIAS = 3


class RevisaoInvalidaError(ValueError):
    pass


def consulta_rag(dossie: dict[str, Any]) -> tuple[str, rag.Filtros, rag.Filtros]:
    """A consulta que o parecer faz ao repositório: nomes das hipóteses e a cultura.

    Duas buscas: fontes técnicas e de histórico para as hipóteses (todas), e regulatórias
    (bula, registro MAPA) para a hipótese principal — é o que alimenta as verificações.
    """
    hip = dossie["hipoteses"]
    cultura = dossie["caso"]["cultura"]
    alvos = tuple(c for c in [hip.get("principal"), *[a["classe"] for a in
                                                      hip.get("alternativas") or []]] if c)
    nomes = [n for c in alvos for n in rag.nomes_do_alvo(c)]
    consulta = " ".join([*nomes, "sintomas", "manejo", "condicoes", "favoraveis"])
    tecnicas = rag.Filtros(cultura=cultura, alvos=alvos)
    regulatorias = rag.Filtros(cultura=cultura, alvos=alvos[:1],
                               tipos=("bula", "registro_mapa"))
    return consulta, tecnicas, regulatorias


def fontes_do_caso(session: Session, tenant_id: str, dossie: dict[str, Any], hoje: date
                   ) -> list[dict[str, Any]]:
    hip = dossie["hipoteses"]
    if not hip.get("principal") or (hip.get("principal_e_sadia") and not hip.get("alternativas")):
        return []
    consulta, tecnicas, regulatorias = consulta_rag(dossie)
    achados = rag.buscar(session, tenant_id, consulta, tecnicas, hoje=hoje, limite=LIMITE_FONTES)
    vistos = {a["trecho_id"] for a in achados}
    for r in rag.buscar(session, tenant_id, consulta + " registro bula alvo", regulatorias,
                        hoje=hoje, limite=LIMITE_REGULATORIAS):
        if r["trecho_id"] not in vistos:
            achados.append(r)
            vistos.add(r["trecho_id"])
    return [{"id": f"F{i + 1}", **a} for i, a in enumerate(achados)]


def gerar(session: Session, *, tenant_id: str, campo: Field, caso: dossie_mod.Caso,
          ia: dossie_mod.FonteDaIA, ator_id: str | None, agora: datetime,
          provedor_nome: str | None = None) -> Parecer:
    """Monta o dossiê, busca as fontes, compõe, (talvez) redige com o provedor e guarda.

    Não faz *commit*.
    """
    dossie = dossie_mod.montar(session, tenant_id, campo, caso, ia, agora=agora)
    fontes = fontes_do_caso(session, tenant_id, dossie, agora.date())
    composto = compositor.compor(dossie, fontes)
    validador = Validador(dossie, fontes)
    recusas: list[dict[str, Any]] = []
    proprias = validador.valida(composto["afirmacoes"])
    if proprias:  # o compositor não pode errar: se errar, é defeito, e fica à vista
        logger.error("compositor determinístico recusado pelo validador: %s", proprias)
        recusas.append({"origem": "compositor", "recusas": proprias})
        # E o texto recusado não sai no parecer: a afirmação vira uma omissão declarada,
        # com as mesmas citações (o leitor vai ao dossiê).
        recusados = {r["indice"] for r in proprias}
        composto = {**composto, "afirmacoes": [
            {**a, "texto": AFIRMACAO_OMITIDA} if i in recusados else a
            for i, a in enumerate(composto["afirmacoes"])]}
    modo, nome = "deterministico", None
    escolhido = provedores.escolhido(provedor_nome)
    if escolhido is not None:
        nome = escolhido.nome
        pedido = provedores.PedidoDeRedacao(dossie=dossie, fontes=fontes,
                                            rascunho=composto["afirmacoes"],
                                            imagens=dossie.get("imagens") or [])
        try:
            redigidas = escolhido.redigir(pedido)
        except Exception as exc:  # o provedor é de fora: qualquer falha cai no determinístico
            recusas.append({"origem": f"provedor:{nome}", "erro": str(exc)[:300]})
        else:
            problemas = validador.valida(redigidas) if isinstance(redigidas, list) and \
                redigidas else [{"indice": None, "motivos": ["resposta_vazia_ou_invalida"]}]
            if problemas:
                recusas.append({"origem": f"provedor:{nome}", "recusas": problemas})
            else:
                modo = "provedor"
                composto = {**composto, "afirmacoes": [
                    {"id": f"A{i + 1}", "secao": str(a.get("secao") or "texto"),
                     "texto": str(a["texto"]), "citacoes": [str(c) for c in a["citacoes"]]}
                    for i, a in enumerate(redigidas)]}
    corpo = {"afirmacoes": composto["afirmacoes"], "verificacoes": composto["verificacoes"],
             "fecho": composto["fecho"]}
    texto = compositor.texto(composto)
    p = Parecer(
        tenant_id=tenant_id, field_id=campo.id, caso_tipo=caso.tipo,
        plant_ref=dossie["caso"]["plant_ref"], observation_id=caso.observation_id,
        modo=modo, provedor=nome, versao_compositor=compositor.VERSAO, dossie=dossie,
        dossie_sha256=dossie_mod.sha256(dossie), fontes=fontes,
        afirmacoes=composto["afirmacoes"], verificacoes=composto["verificacoes"],
        recusas=recusas, texto=texto,
        sha256=dossie_mod.sha256({**corpo, "texto": texto, "fontes": fontes}),
        estado="aguardando_revisao", gerado_por=ator_id)
    session.add(p)
    audit.record(
        session, tenant_id=tenant_id, action="parecer.gerado", subject_type=SubjectType.PARECER,
        subject_id=p.id, actor_type=ActorType.USER if ator_id else ActorType.SYSTEM,
        actor_id=ator_id, new_state=p.estado, model_version=compositor.VERSAO,
        payload={"field_id": campo.id, "caso": caso.tipo, "plant_ref": p.plant_ref,
                 "observation_id": caso.observation_id, "modo": modo, "provedor": nome,
                 "dossie_sha256": p.dossie_sha256, "sha256": p.sha256,
                 "fontes": [{"documento_id": f["documento_id"], "versao": f["versao"],
                             "trecho_id": f["trecho_id"], "sha256_trecho": f["sha256_trecho"]}
                            for f in fontes],
                 "recusas": len(recusas)})
    session.flush()
    return p


def confere_integridade(p: Parecer) -> bool:
    """O parecer guardado é o que foi gerado (nada mexeu nas colunas depois)."""
    corpo = {"afirmacoes": p.afirmacoes, "verificacoes": p.verificacoes,
             "fecho": compositor.FECHO, "texto": p.texto, "fontes": p.fontes}
    return (dossie_mod.sha256(corpo) == p.sha256
            and dossie_mod.sha256(p.dossie) == p.dossie_sha256)


def revisar(session: Session, p: Parecer, *, revisor_id: str, papel: str, decisao: str,
            comentario: str | None, diagnostico_revisor: str | None,
            agora: datetime) -> RevisaoParecer:
    """O agrônomo registra o que achou. **Não autoriza nada** — nem missão, nem prescrição."""
    if decisao not in DECISOES_REVISAO:
        raise RevisaoInvalidaError(f"decisão: uma de {', '.join(DECISOES_REVISAO)}.")
    if decisao == "discorda" and not (comentario or "").strip():
        raise RevisaoInvalidaError("discordar pede um comentário (o que está errado).")
    if not confere_integridade(p):
        raise RevisaoInvalidaError("o parecer guardado não confere com o hash: não revise.")
    rev = RevisaoParecer(tenant_id=p.tenant_id, parecer_id=p.id, revisor_id=revisor_id,
                         papel=papel, decisao=decisao,
                         comentario=(comentario or "").strip() or None,
                         diagnostico_revisor=(diagnostico_revisor or "").strip() or None,
                         parecer_sha256=p.sha256, revisado_em=agora)
    session.add(rev)
    antes, p.estado = p.estado, "revisado"
    audit.record(session, tenant_id=p.tenant_id, action="parecer.revisado",
                 subject_type=SubjectType.PARECER, subject_id=p.id,
                 actor_type=ActorType.USER, actor_id=revisor_id, old_state=antes,
                 new_state=p.estado, reason=rev.comentario,
                 payload={"decisao": decisao, "diagnostico_revisor": rev.diagnostico_revisor,
                          "parecer_sha256": p.sha256, "revisao_id": rev.id, "papel": papel})
    session.flush()
    return rev


def resumo(p: Parecer) -> dict[str, Any]:
    hip = (p.dossie or {}).get("hipoteses") or {}
    return {"id": p.id, "field_id": p.field_id, "caso_tipo": p.caso_tipo,
            "plant_ref": p.plant_ref, "observation_id": p.observation_id, "modo": p.modo,
            "provedor": p.provedor, "estado": p.estado,
            "gerado_em": as_utc(p.created_at).isoformat(), "gerado_por": p.gerado_por,
            "hipotese_principal": hip.get("principal"),
            "alternativas": [a["classe"] for a in hip.get("alternativas") or []],
            "fontes": len(p.fontes or []), "recusas": len(p.recusas or []),
            "pendencias": sum(1 for v in p.verificacoes or []
                              if v["situacao"] in ("sem_fonte", "bloqueado", "sem_dado"))}


def fontes_hoje(session: Session, p: Parecer, hoje: date) -> list[dict[str, Any]]:
    """A situação **de hoje** de cada fonte que o parecer citou. O parecer é imutável e guarda
    a situação do dia em que foi gerado; uma bula verificada naquele dia pode estar vencida ou
    substituída hoje — e quem lê o parecer precisa ver isso antes de agir."""
    from valtexa.cerebro import conhecimento
    from valtexa.models.cerebro import DocumentoConhecimento

    saida = []
    for f in p.fontes or []:
        doc = session.get(DocumentoConhecimento, f.get("documento_id"))
        if doc is None:
            saida.append({"id": f["id"], "documento_id": f.get("documento_id"),
                          "existe": False, "uso_operacional": False,
                          "bloqueio": "documento não está mais no repositório", "mudou": True})
            continue
        sit = conhecimento.situacao(doc, hoje).to_dict()
        saida.append({"id": f["id"], "documento_id": doc.id, "existe": True,
                      "estado": doc.estado, "substituido_por": doc.substituido_por, **sit,
                      "mudou": (sit["uso_operacional"] != f.get("uso_operacional")
                                or doc.estado != f.get("estado"))})
    return saida


def detalhe(p: Parecer, revisoes: list[RevisaoParecer],
            fontes_de_hoje: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {**resumo(p), "versao_compositor": p.versao_compositor, "texto": p.texto,
            "afirmacoes": p.afirmacoes, "verificacoes": p.verificacoes,
            "fecho": compositor.FECHO, "fontes": p.fontes, "fontes_hoje": fontes_de_hoje,
            "dossie": p.dossie,
            "dossie_sha256": p.dossie_sha256, "sha256": p.sha256, "recusas": p.recusas,
            "integro": confere_integridade(p),
            "revisoes": [{"id": r.id, "revisor_id": r.revisor_id, "papel": r.papel,
                          "decisao": r.decisao, "comentario": r.comentario,
                          "diagnostico_revisor": r.diagnostico_revisor,
                          "parecer_sha256": r.parecer_sha256,
                          "revisado_em": as_utc(r.revisado_em).isoformat()} for r in revisoes],
            "aviso": "Apoio à decisão. A revisão do agrônomo não autoriza aplicação nem cria "
                     "missão; a execução passa pela aprovação própria e pelo Safety Engine."}
