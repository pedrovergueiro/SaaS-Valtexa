"""Planejamento fitossanitário (8.3): o que revisar, onde olhar, que alternativas existem.

Tudo aqui é **proposta com premissa registrada**. Cinco partes:

1. **Fila de casos para revisão** — cada diagnóstico ainda não conferido pelo agrônomo, um por
   planta (o mais recente), com ``escore = risco x incerteza x impacto``:

   * ``risco`` — a probabilidade estimada de doença: ``1 - P(sadia)`` nas probabilidades do
     classificador (sem a classe sadia, a confiança da classe de doença; diagnóstico "sadio",
     ``1 - confiança``). Quando o gêmeo deu risco para a planta, vale o maior dos dois, e a
     origem fica dita;
   * ``incerteza`` — o maior de: ``1 - margem`` entre as duas classes mais prováveis;
     ``1 - 1/|C|`` com conjunto conformal ``C`` de mais de uma classe; ``1`` quando as
     análises discordaram ou o modelo se absteve;
   * ``impacto`` — o peso da classe, **1 para todas por padrão** (premissa): quem diz que
     ferrugem pesa mais que phoma neste talhão é o agrônomo, no pedido.

   É a pergunta "o que vale o olho do agrônomo agora": um caso de alto risco e **sem** dúvida
   não precisa de revisão para ser entendido — ele aparece nas regiões prioritárias e nas
   alternativas. (A fila de ``services/review_priority.py`` é outra: o que mais **ensina** o
   modelo.)
2. **Comparação do histórico de sintomas** das plantas do topo da fila: a situação em cada
   passada fechada, a incidência da primeira à última, e as lesões reencontradas no
   referencial da planta (persistentes, novas, não revistas — ``plant_fusion`` da IA).
3. **Regiões prioritárias** — as tarefas do gêmeo (``/gemeo/prioridades``, valor da
   informação por trecho de rua) — as mesmas que o alocador do enxame usa.
4. **Alternativas de manejo** — monitorar, confirmar em campo, inspeção dirigida, tratamento
   localizado, tratamento em área total — cada uma com a evidência que a sustenta, o que falta
   e quem decide. **Nenhuma é escolhida aqui**; nenhuma traz produto nem dose.
5. **Rotação de ingredientes ativos por modo de ação** — só com produto **cadastrado** que
   tenha modo de ação, registro MAPA e fonte regulatória **vigente e verificada** no
   repositório de conhecimento (bula/registro para a cultura do talhão). O resto fica de fora,
   com o motivo. O limite de aplicações seguidas do mesmo grupo vem do pedido (da bula, do
   agrônomo); sem ele, o plano mostra a sequência e não julga.
"""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timedelta
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from valtexa.cerebro import conhecimento
from valtexa.models import (
    Agreement,
    Application,
    ApplicationState,
    Detection,
    Diagnosis,
    DiagnosisStatus,
    Field,
    Observation,
    Product,
    ProductStatus,
    as_utc,
)
from valtexa.models.cerebro import DocumentoConhecimento, Parecer
from valtexa.planejamento.premissas import Premissas
from valtexa.services import plant_map

VERSAO = "fitossanitario-1"
SADIA = frozenset({"Healthy", "healthy", "Sadia", "sadia"})
NAO_REVISADOS = (DiagnosisStatus.PENDING, DiagnosisStatus.AI_VALIDATED,
                 DiagnosisStatus.NEEDS_REVIEW, DiagnosisStatus.INCONCLUSIVE)
TIPOS_REGULATORIOS_PRODUTO = ("bula", "registro_mapa")


class IndisponivelError(Exception):
    pass


class FonteDaIA(Protocol):
    def evolucao(self, field_id: str, plant_ref: str) -> dict | None: ...
    def lesoes(self, field_id: str, plant_ref: str) -> dict | None: ...
    def previsao(self, field_id: str, doenca: str, horizonte_dias: int) -> dict | None: ...
    def prioridades(self, field_id: str, params: dict) -> dict | None: ...


class FonteDaIAPadrao:
    """O serviço de inferência da ValTexa (interno, não externo). Fora do ar → indisponível."""

    @staticmethod
    def _chama(funcao, *args):
        try:
            return funcao(*args)
        except plant_map.PlantMapUnavailableError as exc:
            raise IndisponivelError(str(exc)) from exc

    def evolucao(self, field_id: str, plant_ref: str) -> dict | None:
        return self._chama(plant_map.evolution, field_id, plant_ref)

    def lesoes(self, field_id: str, plant_ref: str) -> dict | None:
        return self._chama(plant_map.lesoes, field_id, plant_ref)

    def previsao(self, field_id: str, doenca: str, horizonte_dias: int) -> dict | None:
        return self._chama(plant_map.previsao_gemeo, field_id, {
            "doenca": doenca, "horizonte_dias": horizonte_dias, "plantas": "em_risco",
            "risco_minimo": 0.01})

    def prioridades(self, field_id: str, params: dict) -> dict | None:
        return self._chama(plant_map.prioridades_gemeo, field_id, params)


def le(funcao, *args) -> tuple[Any, str | None]:
    """``(resposta, motivo)``: a IA fora do ar ou sem dado vira motivo, não exceção."""
    try:
        r = funcao(*args)
    except IndisponivelError as exc:
        return None, f"IA indisponível: {str(exc)[:200]}"
    if r is None:
        return None, "sem dado na IA (o Rover ainda não passou ou o gêmeo não foi ajustado)"
    return r, None


# ---------------------------------------------------------------------------------------------
# 1. Fila de revisão
# ---------------------------------------------------------------------------------------------


def risco_visual(det: Detection | None, diag: Diagnosis) -> float | None:
    """P(doença) estimada pelo classificador (ver o topo do módulo)."""
    probs = {k: float(v) for k, v in ((det.probabilities if det else None) or {}).items()
             if isinstance(v, (int, float))}
    sadias = [v for k, v in probs.items() if k in SADIA]
    if sadias:
        return max(0.0, min(1.0, 1.0 - sum(sadias)))
    conf = diag.confidence if diag.confidence is not None else (det.confidence if det else None)
    if conf is None:
        return None
    return 1.0 - float(conf) if (diag.label or "") in SADIA else float(conf)


def incerteza(det: Detection | None, diag: Diagnosis) -> tuple[float, list[str]]:
    motivos: list[str] = []
    u = 0.0
    probs = sorted((float(v) for v in ((det.probabilities if det else None) or {}).values()
                    if isinstance(v, (int, float))), reverse=True)
    if len(probs) >= 2:
        margem = probs[0] - probs[1]
        u = max(u, 1.0 - margem)
        motivos.append(f"margem entre as duas classes mais prováveis {margem:.2f}")
    elif diag.confidence is not None:
        u = max(u, 1.0 - float(diag.confidence))
    conjunto = ((det.signals if det else None) or {}).get("prediction_set") or []
    if len(conjunto) > 1:
        u = max(u, 1.0 - 1.0 / len(conjunto))
        motivos.append(f"conjunto conformal com {len(conjunto)} classes")
    if diag.agreement is Agreement.DISAGREE:
        u = 1.0
        motivos.append("as análises discordaram")
    if det is not None and det.abstained:
        u = 1.0
        motivos.append("o modelo se absteve")
    if diag.status is DiagnosisStatus.INCONCLUSIVE:
        u = 1.0
        motivos.append("diagnóstico inconclusivo")
    return max(0.0, min(1.0, u)), motivos


def fila_de_revisao(session: Session, *, tenant_id: str, campo: Field, agora: datetime,
                    janela_dias: int, pesos: dict[str, float], peso_padrao: float,
                    riscos_gemeo: dict[str, float], limite: int) -> list[dict[str, Any]]:
    inicio = agora - timedelta(days=janela_dias)
    linhas = session.execute(
        select(Diagnosis, Observation).join(Observation, Observation.id == Diagnosis.observation_id)
        .where(Diagnosis.tenant_id == tenant_id, Diagnosis.field_id == campo.id,
               Diagnosis.status.in_(NAO_REVISADOS), Diagnosis.reviewed_by.is_(None),
               Observation.captured_at >= inicio)
        .order_by(Observation.captured_at.desc(), Diagnosis.id)).all()
    vistos: set[str] = set()
    por_planta: dict[str, Parecer] = {}
    por_obs: dict[str, Parecer] = {}
    for p in session.scalars(select(Parecer).where(
            Parecer.tenant_id == tenant_id, Parecer.field_id == campo.id)
            .order_by(Parecer.created_at, Parecer.id)):
        if p.plant_ref:
            por_planta[p.plant_ref] = p  # o mais recente fica
        if p.observation_id:
            por_obs[p.observation_id] = p
    itens = []
    for diag, obs in linhas:
        chave = obs.plant_ref or f"obs:{obs.id}"
        if chave in vistos:  # o mais recente da planta
            continue
        vistos.add(chave)
        det = session.get(Detection, diag.primary_detection_id) \
            if diag.primary_detection_id else None
        r_visual = risco_visual(det, diag)
        r_gemeo = riscos_gemeo.get(obs.plant_ref or "")
        risco_fontes = {k: round(v, 4) for k, v in (("visual", r_visual), ("gemeo", r_gemeo))
                        if v is not None}
        risco = max(risco_fontes.values()) if risco_fontes else 0.0
        u, motivos = incerteza(det, diag)
        rotulo = diag.label or "desconhecido"
        impacto = pesos.get(rotulo, peso_padrao)
        parecer = por_obs.get(obs.id) or (por_planta.get(obs.plant_ref)
                                           if obs.plant_ref else None)
        itens.append({
            "plant_ref": obs.plant_ref, "observation_id": obs.id, "diagnosis_id": diag.id,
            "capturado_em": as_utc(obs.captured_at).isoformat(), "rotulo": rotulo,
            "situacao": diag.status.value, "risco": round(risco, 4),
            "risco_por_fonte": risco_fontes, "incerteza": round(u, 4),
            "impacto": impacto, "escore": round(risco * u * impacto, 4),
            "motivos_da_incerteza": motivos,
            "parecer": {"id": parecer.id, "estado": parecer.estado} if parecer else None,
        })
    itens.sort(key=lambda i: (-i["escore"], -i["risco"], i["capturado_em"], i["diagnosis_id"]))
    return itens[:limite]


# ---------------------------------------------------------------------------------------------
# 2. Histórico de sintomas
# ---------------------------------------------------------------------------------------------


def historico_da_planta(ia: FonteDaIA, field_id: str, plant_ref: str,
                        limiar_tendencia: float) -> dict[str, Any]:
    ev, motivo_ev = le(ia.evolucao, field_id, plant_ref)
    les, motivo_les = le(ia.lesoes, field_id, plant_ref)
    saida: dict[str, Any] = {"plant_ref": plant_ref}
    if ev is None:
        saida["passadas"] = None
        saida["motivo_passadas"] = motivo_ev
    else:
        hist = ev.get("history") or []
        saida["passadas"] = [{"passada": h.get("pass_id"), "situacao": h.get("status"),
                              "doenca": h.get("primary_disease"),
                              "incidencia": h.get("incidence")} for h in hist]
        incs = [h.get("incidence") for h in hist if isinstance(h.get("incidence"), (int, float))]
        if len(incs) >= 2:
            delta = incs[-1] - incs[0]
            saida["incidencia_primeira_ultima"] = [incs[0], incs[-1]]
            saida["tendencia"] = ("subiu" if delta > limiar_tendencia else
                                  "caiu" if delta < -limiar_tendencia else "estavel")
        else:
            saida["tendencia"] = "uma passada só: sem comparação"
        saida["mudancas"] = [c.get("change") for c in ev.get("changes") or []]
    if les is None:
        saida["lesoes"] = None
        saida["motivo_lesoes"] = motivo_les
    else:
        trilhas = les.get("tracks") or []
        saida["lesoes"] = {"passadas": les.get("passes") or [],
                           "por_estado": dict(sorted(Counter(
                               t.get("state", "?") for t in trilhas).items())),
                           "por_doenca": dict(sorted(Counter(
                               t.get("disease") or "?" for t in trilhas).items()))}
    return saida


# ---------------------------------------------------------------------------------------------
# 3 e 4. Regiões prioritárias e alternativas de manejo
# ---------------------------------------------------------------------------------------------


def regioes(corpo: dict[str, Any] | None, limite: int) -> list[dict[str, Any]]:
    if not corpo:
        return []
    return [{"tipo": t.get("tipo"), "ruas": t.get("ruas"), "x_inicio_m": t.get("x_inicio_m"),
             "x_fim_m": t.get("x_fim_m"), "plantas": t.get("plantas"),
             "valor": t.get("valor"), "risco_medio": t.get("risco_medio"),
             "risco_maximo": t.get("risco_maximo"), "incerteza_bits": t.get("incerteza_bits"),
             "dias_sem_ver": t.get("dias_sem_ver"), "motivo": t.get("motivo")}
            for t in (corpo.get("tarefas") or [])[:limite]]


def alternativas(fila: list[dict[str, Any]], regioes_: list[dict[str, Any]],
                 previsao: dict[str, Any] | None, limiar_risco: float) -> list[dict[str, Any]]:
    """As opções de manejo, com a evidência de cada uma. O plano não escolhe."""
    plantas = (previsao or {}).get("plantas_detalhe") or []
    em_risco = [p for p in plantas if (p.get("risco") or 0.0) >= limiar_risco]
    esperado = (previsao or {}).get("infectadas_no_horizonte_esperado")
    faixa = (previsao or {}).get("infectadas_no_horizonte_p10_p90")
    focos = (previsao or {}).get("focos_no_horizonte")
    evid_gemeo = ({"plantas_com_risco_acima_do_limiar": len(em_risco),
                   "limiar_de_risco": limiar_risco,
                   "infectadas_no_horizonte_esperado": esperado,
                   "infectadas_no_horizonte_p10_p90": faixa, "focos_no_horizonte": focos,
                   "horizonte": (previsao or {}).get("horizonte")}
                  if previsao else None)
    incertos = [i for i in fila if i["incerteza"] >= 0.5]
    comum = "Decide o agrônomo responsável; qualquer execução passa pela aprovação própria " \
            "e pelo Safety Engine."
    return [
        {"codigo": "monitorar", "titulo": "Monitorar sem intervir",
         "quando_faz_sentido": "risco baixo e estável, ou evidência insuficiente para agir",
         "evidencia": {"gemeo": evid_gemeo, "casos_na_fila": len(fila)},
         "o_que_falta": ["próxima passada do Rover para comparar a evolução"],
         "custo_de_errar": "se o foco crescer, a intervenção fica maior depois",
         "quem_decide": comum},
        {"codigo": "confirmar_em_campo", "titulo": "Confirmar em campo os casos incertos",
         "quando_faz_sentido": "há casos com incerteza alta na fila",
         "evidencia": {"casos_com_incerteza_alta": len(incertos),
                       "plantas": [i["plant_ref"] or i["observation_id"] for i in incertos[:10]]},
         "o_que_falta": ["visita do agrônomo, rótulo de campo"],
         "custo_de_errar": "tempo do agrônomo em caso que não era doença",
         "quem_decide": comum},
        {"codigo": "inspecao_dirigida", "titulo": "Inspeção dirigida do Rover nas regiões "
                                                  "prioritárias",
         "quando_faz_sentido": "o gêmeo aponta trechos em que olhar muda a decisão",
         "evidencia": {"regioes": len(regioes_),
                       "valor_total": round(sum(r.get("valor") or 0.0 for r in regioes_), 4)},
         "o_que_falta": ["plano robótico (bateria, inclinação, obstáculos, orçamento de dados)",
                         "missão criada em rascunho por uma pessoa e autorizada pelo Safety "
                         "Engine"],
         "custo_de_errar": "tempo de Rover e dados da Starlink",
         "quem_decide": comum},
        {"codigo": "tratamento_localizado", "titulo": "Tratamento localizado nos focos",
         "quando_faz_sentido": "o risco está concentrado em poucas plantas ou focos",
         "evidencia": {"gemeo": evid_gemeo},
         "o_que_falta": ["diagnóstico confirmado", "produto com registro vigente para a "
                         "cultura e o alvo (rotação abaixo)", "dose de bula",
                         "intervalo de segurança", "condições ambientais na hora",
                         "aprovação do agrônomo na missão de aplicação"],
         "custo_de_errar": "foco fora do polígono tratado continua ativo",
         "quem_decide": comum},
        {"codigo": "tratamento_area_total", "titulo": "Tratamento em área total",
         "quando_faz_sentido": "o risco está espalhado pelo talhão",
         "evidencia": {"gemeo": evid_gemeo},
         "o_que_falta": ["os mesmos do tratamento localizado"],
         "custo_de_errar": "produto e custo onde não havia doença; pressão de seleção de "
                           "resistência",
         "quem_decide": comum},
    ]


# ---------------------------------------------------------------------------------------------
# 5. Rotação por modo de ação
# ---------------------------------------------------------------------------------------------


def elegibilidade(session: Session, produto: Product, *, tenant_id: str, cultura: str,
                  hoje: date) -> tuple[bool, str | None, dict[str, Any] | None]:
    """Se o produto entra na análise de rotação, e por quê não."""
    if produto.status is not ProductStatus.ACTIVE:
        return False, f"produto {produto.status.value}", None
    if not produto.modo_de_acao:
        return False, "sem modo de ação cadastrado", None
    if not produto.registration_number:
        return False, "sem registro MAPA no cadastro", None
    if not produto.active_ingredient:
        return False, "sem ingrediente ativo no cadastro", None
    if cultura not in (produto.allowed_crops or []):
        return False, f"cultura {cultura} não está entre as autorizadas no cadastro", None
    if not produto.fonte_documento_id:
        return False, "sem fonte (bula ou registro) no repositório de conhecimento", None
    doc = session.get(DocumentoConhecimento, produto.fonte_documento_id)
    if doc is None or doc.tenant_id not in (None, tenant_id):
        return False, "a fonte cadastrada não está no repositório", None
    if doc.tipo not in TIPOS_REGULATORIOS_PRODUTO:
        return False, f"a fonte é {doc.tipo}, não bula nem registro MAPA", None
    sit = conhecimento.situacao(doc, hoje)
    fonte = {"documento_id": doc.id, "chave": doc.chave, "versao": doc.versao,
             "titulo": doc.titulo, "verificado_em": doc.verificado_em
             and doc.verificado_em.isoformat(),
             "valido_ate": doc.valido_ate and doc.valido_ate.isoformat(), "sha256": doc.sha256}
    if not sit.uso_operacional:
        return False, f"fonte regulatória sem uso operacional: {sit.motivo}", fonte
    if cultura not in [c.lower() for c in doc.culturas or []]:
        return False, f"a fonte não cita a cultura {cultura}", fonte
    return True, None, fonte


def rotacao(session: Session, *, tenant_id: str, campo: Field, agora: datetime,
            janela_dias: int, max_seguidas: int | None, alvo: str | None) -> dict[str, Any]:
    hoje = agora.date()
    produtos = session.scalars(select(Product).where(Product.tenant_id == tenant_id)
                               .order_by(Product.name, Product.id)).all()
    elegiveis, fora = [], []
    for p in produtos:
        ok, motivo, fonte = elegibilidade(session, p, tenant_id=tenant_id, cultura=campo.crop,
                                          hoje=hoje)
        linha = {"product_id": p.id, "nome": p.name, "ingrediente_ativo": p.active_ingredient,
                 "modo_de_acao": p.modo_de_acao, "registro": p.registration_number,
                 "alvos_cadastrados": list(p.authorized_targets or []), "fonte": fonte}
        if ok:
            elegiveis.append(linha)
        else:
            fora.append({**linha, "motivo": motivo})
    por_id = {p.id: p for p in produtos}
    aplicacoes = session.scalars(select(Application).where(
        Application.tenant_id == tenant_id, Application.field_id == campo.id,
        Application.state == ApplicationState.COMPLETED,
        Application.started_at >= agora - timedelta(days=janela_dias))
        .order_by(Application.started_at, Application.id)).all()
    sequencia = []
    for a in aplicacoes:
        p = por_id.get(a.product_id or "")
        sequencia.append({"application_id": a.id, "em": as_utc(a.started_at).isoformat(),
                          "product_id": a.product_id, "produto": p.name if p else None,
                          "modo_de_acao": p.modo_de_acao if p else None})
    seguidas, ultimo = 0, None
    for s in reversed(sequencia):
        if s["modo_de_acao"] is None:
            break
        if ultimo is None:
            ultimo = s["modo_de_acao"]
        if s["modo_de_acao"] != ultimo:
            break
        seguidas += 1
    for e in elegiveis:
        repete = ultimo is not None and e["modo_de_acao"] == ultimo
        e["repete_o_ultimo_grupo"] = repete
        e["seguidas_se_usado"] = seguidas + 1 if repete else 1
        e["alvo_no_cadastro"] = None if alvo is None else alvo in e["alvos_cadastrados"]
        if max_seguidas is None:
            e["avaliacao"] = ("repete o grupo da última aplicação" if repete
                              else "grupo diferente do da última aplicação")
        elif e["seguidas_se_usado"] > max_seguidas:
            e["avaliacao"] = (f"passaria do limite de {max_seguidas} aplicação(ões) seguidas "
                              f"do grupo {e['modo_de_acao']}")
        else:
            e["avaliacao"] = "dentro do limite de aplicações seguidas do mesmo grupo"
    elegiveis.sort(key=lambda e: (e["repete_o_ultimo_grupo"], e["nome"], e["product_id"]))
    sem_modo = sum(1 for s in sequencia if s["modo_de_acao"] is None)
    avisos = []
    if not produtos:
        avisos.append("nenhum produto cadastrado: não dá para avaliar rotação")
    elif not elegiveis:
        avisos.append("nenhum produto cadastrado com modo de ação, registro e fonte regulatória "
                      "vigente para a cultura: não dá para avaliar rotação")
    if sem_modo:
        avisos.append(f"{sem_modo} aplicação(ões) do histórico com produto sem modo de ação: "
                      "a sequência pode estar incompleta")
    return {"elegiveis": elegiveis, "fora": fora, "historico": sequencia,
            "ultimo_grupo": ultimo, "seguidas_do_ultimo_grupo": seguidas,
            "max_seguidas": max_seguidas, "avisos": avisos,
            "nota": "Apoio à decisão: a escolha do produto e da dose é do agrônomo, na bula "
                    "vigente; a aplicação passa pela aprovação dele e pelo Safety Engine."}


# ---------------------------------------------------------------------------------------------
# O plano
# ---------------------------------------------------------------------------------------------


def planejar(session: Session, *, tenant_id: str, campo: Field, ia: FonteDaIA,
             pedido: dict[str, Any], agora: datetime) -> tuple[dict[str, Any], list[dict]]:
    """``(resultado, premissas)``. Determinístico para o mesmo banco, IA, pedido e instante."""
    pr = Premissas()
    doenca = pr.valor("doenca", pedido.get("doenca"), "Rust",
                      "doença do gêmeo para risco, regiões e alternativas")
    janela = pr.valor("janela_dias", pedido.get("janela_dias"), 30,
                      "diagnósticos dos últimos N dias entram na fila")
    pesos = pr.valor("pesos_impacto", pedido.get("pesos_impacto"), {},
                     "peso de impacto por classe (vazio: todas iguais)")
    peso_padrao = pr.anota("peso_impacto_padrao", "impacto de classe sem peso declarado: 1 — "
                           "não há base para dizer que uma doença pesa mais que outra sem o "
                           "agrônomo", 1.0, "padrao")
    limite = pr.valor("limite_fila", pedido.get("limite_fila"), 50, "itens da fila")
    n_hist = pr.valor("plantas_com_historico", pedido.get("plantas_com_historico"), 10,
                      "plantas do topo da fila com a comparação do histórico")
    limiar_tend = pr.valor("limiar_tendencia", pedido.get("limiar_tendencia"), 0.05,
                           "variação de incidência abaixo disto é 'estável'")
    limiar_risco = pr.valor("limiar_risco", pedido.get("limiar_risco"), 0.3,
                            "risco do gêmeo a partir do qual a planta conta como 'em risco' "
                            "nas alternativas (só descreve; não decide)")
    horizonte = pr.valor("horizonte_dias", pedido.get("horizonte_dias"), 14,
                         "horizonte da previsão do gêmeo")
    janela_rot = pr.valor("janela_rotacao_dias", pedido.get("janela_rotacao_dias"), 365,
                          "aplicações do talhão nos últimos N dias contam na rotação")
    max_seguidas = pr.valor("max_seguidas_mesmo_grupo", pedido.get("max_seguidas_mesmo_grupo"),
                            None, "limite de aplicações seguidas do mesmo grupo (da bula ou do "
                                  "agrônomo); sem ele, o plano não julga a rotação")
    pr.anota("risco", "risco = 1 - P(sadia) do classificador; com risco do gêmeo para a "
                      "planta, o maior dos dois", None, "padrao")
    pr.anota("incerteza", "incerteza = maior de (1 - margem top-2, 1 - 1/|conjunto conformal|, "
                          "1 se discordância/abstenção/inconclusivo)", None, "padrao")

    avisos: list[str] = []
    previsao, motivo_prev = le(ia.previsao, campo.id, doenca, horizonte)
    if motivo_prev:
        avisos.append(f"gêmeo: {motivo_prev}")
    riscos_gemeo = {p["plant_id"]: float(p["risco"]) for p in
                    (previsao or {}).get("plantas_detalhe") or []
                    if p.get("plant_id") and isinstance(p.get("risco"), (int, float))}
    fila = fila_de_revisao(session, tenant_id=tenant_id, campo=campo, agora=agora,
                           janela_dias=janela, pesos=pesos, peso_padrao=peso_padrao,
                           riscos_gemeo=riscos_gemeo, limite=limite)
    historicos = [historico_da_planta(ia, campo.id, i["plant_ref"], limiar_tend)
                  for i in fila if i["plant_ref"]][:n_hist]
    prio, motivo_prio = le(ia.prioridades, campo.id, {
        "doenca": doenca, "dias_ate_visita": 1, "segmento_m": 20.0, "max_tarefas": 20,
        "canal": "rover"})
    if motivo_prio:
        avisos.append(f"regiões prioritárias: {motivo_prio}")
    regs = regioes(prio, 20)
    resultado = {
        "versao": VERSAO, "field_id": campo.id, "cultura": campo.crop, "doenca": doenca,
        "fila_de_revisao": fila, "historico_de_sintomas": historicos,
        "regioes_prioritarias": regs,
        "alternativas_de_manejo": alternativas(fila, regs, previsao, limiar_risco),
        "rotacao": rotacao(session, tenant_id=tenant_id, campo=campo, agora=agora,
                           janela_dias=janela_rot, max_seguidas=max_seguidas, alvo=doenca),
        "avisos": avisos + (prio or {}).get("avisos", []),
    }
    return resultado, pr.lista()
