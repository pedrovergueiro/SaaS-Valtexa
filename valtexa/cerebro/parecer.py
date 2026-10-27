"""O parecer (8.2): compositor **determinístico** a partir do dossiê e das fontes.

O compositor escreve uma lista de **afirmações**, cada uma com as citações que a sustentam
(``E<n>`` = item do dossiê, ``F<n>`` = trecho do repositório). Ele não acrescenta nada que não
esteja no dossiê ou na fonte: os números vêm dos dados dos itens; os nomes de doença, de
:data:`~valtexa.cerebro.rag.NOMES_ALVO`. Por construção, o texto dele passa no validador
(:mod:`valtexa.cerebro.validador`) — o teste confere.

Linguagem: hipótese, compatibilidade, probabilidade estimada. Nunca "é", "confirmado",
"certamente". O parecer mostra a hipótese principal **e** as alternativas.

Depois das afirmações vêm, sempre e sempre iguais na forma:

* as **verificações que faltam** antes de qualquer intervenção (diagnóstico, cultura, registro
  vigente, alvo, dose de bula, restrições, intervalo de segurança, condições ambientais), cada
  uma com a situação — ``a_verificar``, ``sem_fonte``, ``bloqueado`` ou ``sem_dado``. **Nunca
  "ok"**: quem dá por verificado é o responsável;
* o **fecho**: revisão do responsável e Safety Engine.
"""

from __future__ import annotations

import re
from typing import Any

from valtexa.cerebro.validador import CERTEZA, OPERACIONAL, dobra

VERSAO = "compositor-2"

FECHO = (
    "Este parecer é apoio à decisão: não autoriza nenhuma intervenção, não cria missão e não "
    "aprova prescrição. A recomendação final deve ser revisada pelo profissional responsável "
    "e submetida às verificações determinísticas de segurança (Safety Engine) antes de "
    "qualquer execução."
)

VERIFICACOES = (
    ("diagnostico", "Diagnóstico"),
    ("cultura", "Cultura"),
    ("registro_vigente", "Registro vigente do produto"),
    ("alvo_autorizado", "Alvo autorizado"),
    ("dose_de_bula", "Dose de bula"),
    ("restricoes", "Restrições de aplicação"),
    ("intervalo_de_seguranca", "Intervalo de segurança"),
    ("condicoes_ambientais", "Condições ambientais"),
)
SITUACOES = ("a_verificar", "sem_fonte", "bloqueado", "sem_dado")
REGULATORIAS = ("registro_vigente", "alvo_autorizado", "dose_de_bula", "restricoes",
                "intervalo_de_seguranca")


def num(valor: Any, casas: int = 2) -> str:
    """Número no jeito brasileiro (vírgula), sem zeros inúteis: 0.62 → "0,62", 3.0 → "3"."""
    if isinstance(valor, bool) or valor is None:
        return str(valor)
    if isinstance(valor, int):
        return str(valor)
    texto = f"{float(valor):.{casas}f}".rstrip("0").rstrip(".")
    return texto.replace(".", ",")


CULTURAS = {"coffee": "café", "corn": "milho", "soy": "soja", "banana": "banana",
            "citrus": "citros"}
SITUACAO_DIAGNOSTICO = {
    "pending": "pendente", "ai_validated": "as duas análises concordaram",
    "needs_review": "precisa de revisão", "inconclusive": "inconclusiva",
    "human_confirmed": "conferida pelo agrônomo", "human_rejected": "recusada pelo agrônomo",
}


def _cultura(codigo: str | None) -> str:
    return CULTURAS.get(str(codigo), str(codigo))


def _situacao(codigo: str | None) -> str:
    return SITUACAO_DIAGNOSTICO.get(str(codigo), str(codigo))


LIVRE_OMITIDO = "(texto livre omitido: parecia instrução)"
_LIVRE_PROIBIDO = re.compile(r"[\[\]\n\r\t<>{}]")
_TEM_NUMERO = re.compile(r"\d")
VEREDITOS_DE_REGRA = {
    "sustentada": "sustentada pelo histórico do cliente",
    "contrariada": "contrariada pelo histórico do cliente",
    "nao_mostrada": "o histórico do cliente não mostrou diferença",
    "poucos_dados": "ainda sem casos suficientes para medir",
    "nao_medida": "ainda não medida",
}
"""O mesmo que :data:`valtexa.services.ensino.VEREDITOS` (o compositor não importa serviço)."""


def livre(valor: Any, limite: int = 120) -> str:
    """Texto livre (nome do talhão, título e origem de fonte, identificador vindo do Rover) é
    **dado, não instrução**: entra no parecer como veio só quando não pode ser lido como
    citação (colchetes), marcação, ordem de aplicação, dose ou certeza. Senão, vira
    :data:`LIVRE_OMITIDO` — o identificador continua no dossiê para quem quiser conferir."""
    texto = str(valor if valor is not None else "")
    dobrado = dobra(texto)
    if (len(texto) > limite or _LIVRE_PROIBIDO.search(texto)
            or any(p.search(dobrado) for p in (*CERTEZA, *OPERACIONAL))):
        return LIVRE_OMITIDO
    return texto


def _nome(rotulo: str | None, hip: dict[str, Any]) -> str:
    if not rotulo:
        return "sem classe"
    nomes = (hip.get("nomes") or {}).get(rotulo) or []
    return f"{nomes[0]} ({livre(rotulo, 64)})" if nomes else livre(rotulo, 64)


class _Texto:
    def __init__(self) -> None:
        self.afirmacoes: list[dict[str, Any]] = []

    def diz(self, secao: str, texto: str, *citacoes: str) -> None:
        self.afirmacoes.append({"id": f"A{len(self.afirmacoes) + 1}", "secao": secao,
                                "texto": texto, "citacoes": sorted(set(citacoes),
                                                                   key=_ordem_citacao)})


def _ordem_citacao(c: str) -> tuple[str, int]:
    return (c[0], int(c[1:]) if c[1:].isdigit() else 0)


def _por_tipo(dossie: dict[str, Any], tipo: str) -> list[dict[str, Any]]:
    return [i for i in dossie["itens"] if i["tipo"] == tipo]


def compor(dossie: dict[str, Any], fontes: list[dict[str, Any]]) -> dict[str, Any]:
    """``{"afirmacoes", "verificacoes", "fecho"}`` — determinístico para o mesmo dossiê/fontes."""
    t = _Texto()
    caso = _por_tipo(dossie, "caso")[0]
    c = caso["dados"]
    hip = dossie["hipoteses"]
    onde = f"planta {livre(c['plant_ref'], 64)}" if c.get("plant_ref") else "observação"
    t.diz("caso", f"Caso: talhão {livre(c['talhao'])}, {onde}, cultura {livre(c['cultura'])}, "
                  f"dados até {c['data_do_caso']}.", caso["id"])

    # Hipóteses -----------------------------------------------------------------------------
    fusao = next((i for i in _por_tipo(dossie, "fusao_planta") if i["disponivel"]), None)
    visuais = _por_tipo(dossie, "visual")
    principal = hip.get("principal")
    resto = visuais
    if principal is None:
        t.diz("hipoteses", "Sem hipótese: não há classificação de imagem nem fusão por planta "
                           "para este caso.", caso["id"])
    elif fusao is not None and fusao["dados"].get("doenca_principal") == principal:
        d = fusao["dados"]
        t.diz("hipoteses",
              f"A fusão por planta tem maior compatibilidade com {_nome(principal, hip)}: "
              f"probabilidade estimada {num(d['posterior_principal'])}, a partir de "
              f"{d['recortes']} recortes em {d['quadros']} quadros "
              f"(situação da fusão: {d['situacao']}).", fusao["id"])
    else:
        v, resto = visuais[0], visuais[1:]
        t.diz("hipoteses",
              f"O classificador apresentou maior compatibilidade com {_nome(principal, hip)} "
              f"(confiança {num(v['dados']['confianca'])}; dupla validação: "
              f"{_situacao(v['dados']['situacao'])}).", v["id"])
    for v in resto:
        d = v["dados"]
        t.diz("hipoteses", f"Classificação da imagem {d['observation_id']}: "
                           f"{_nome(d['classe'], hip)}, confiança {num(d['confianca'])}, "
                           f"dupla validação: {_situacao(d['situacao'])}.", v["id"])
    if hip.get("alternativas"):
        nomes = "; ".join(_nome(a["classe"], hip) for a in hip["alternativas"])
        t.diz("hipoteses", f"Hipóteses alternativas que a evidência não descarta: {nomes}.",
              *[e for a in hip["alternativas"] for e in a["evidencias"]])
    elif visuais and all(v["dados"].get("conjunto_conformal") is None for v in visuais):
        t.diz("hipoteses", "As alternativas não estão quantificadas: o modelo não tem conjunto "
                           "conformal calibrado.", *[v["id"] for v in visuais])

    # Qualidade e limitações --------------------------------------------------------------
    for cap in _por_tipo(dossie, "captura"):
        d = cap["dados"]
        if d["recortes_medidos"]:
            t.diz("evidencia", f"Captura no Rover: {d['recortes_com_problema']} de "
                               f"{d['recortes_medidos']} recortes com problema de captura.",
                  cap["id"])
    for les in _por_tipo(dossie, "lesoes_3d"):
        if les["disponivel"] and les["dados"]["trilhas"]:
            d = les["dados"]
            estados = ", ".join(f"{k}: {n}" for k, n in sorted(d["por_estado"].items()))
            t.diz("evidencia", f"Lesões reencontradas na planta: {d['trilhas']} trilhas "
                               f"({estados}).", les["id"])
    for it in dossie["itens"]:
        if it["tipo"] == "caso":
            continue
        if not it["disponivel"]:
            t.diz("limitacoes", f"{it['titulo']}: indisponível ({it['motivo_indisponivel']}).",
                  it["id"])
            continue
        for lim in it["limitacoes"]:
            t.diz("limitacoes", f"{it['titulo']}: {lim}.", it["id"])

    # Histórico, gêmeo, clima ---------------------------------------------------------------
    for h in _por_tipo(dossie, "historico"):
        d = h["dados"]
        for r in d["rotulos_de_campo"][:1]:
            t.diz("historico", f"Rótulo de campo mais recente do agrônomo para a planta: "
                               f"{_nome(r['classe'], hip)} (passada {livre(r['passada'], 64)}).",
                  h["id"])
        if d["diagnosticos_do_talhao"]:
            partes = ", ".join(f"{k}: {n}" for k, n in d["diagnosticos_do_talhao"].items())
            t.diz("historico", f"Diagnósticos do talhão nos últimos {d['janela_dias']} dias "
                               f"(rótulo efetivo): {partes}.", h["id"])
        for p in d["pareceres_anteriores"]:
            decisoes = ", ".join(r["decisao"] for r in p["revisoes"]) or "sem revisão"
            t.diz("historico", f"Parecer anterior {p['parecer_id']}: {decisoes}.", h["id"])
    for ev in _por_tipo(dossie, "evolucao"):
        if not ev["disponivel"]:
            continue
        d = ev["dados"]
        seq = " → ".join(str(p["situacao"]) for p in d["passadas"])
        if seq:
            t.diz("historico", f"Situação da planta nas passadas fechadas: {seq}.", ev["id"])
        if d.get("audpc") is not None and len(d["passadas"]) >= 2:
            t.diz("historico", f"Área sob a curva de progresso (AUDPC) da incidência: "
                               f"{num(d['audpc'], 3)} ({d['audpc_unidade']}).", ev["id"])
    for g in _por_tipo(dossie, "gemeo"):
        if not g["disponivel"]:
            continue
        d = g["dados"]
        if d.get("planta"):
            pl = d["planta"]
            t.diz("risco", f"O gêmeo digital estima, para {_nome(d['doenca'], hip)}, risco de "
                           f"{num(pl['risco'])} para esta planta no horizonte de "
                           f"{d['horizonte_dias']} dias (faixa p10 {num(pl['risco_p10'])} a "
                           f"p90 {num(pl['risco_p90'])}, {d['membros']} membros).", g["id"])
        if d.get("infectadas_no_horizonte_esperado") is not None:
            t.diz("risco", f"No talhão, o gêmeo espera {num(d['infectadas_no_horizonte_esperado'])}"
                           f" plantas infectadas no horizonte ({d['horizonte']}).", g["id"])
    for cl in _por_tipo(dossie, "clima"):
        if cl["disponivel"]:
            d = cl["dados"]
            t.diz("clima", f"Clima de {d['inicio']} a {d['fim']} ({d['dias']} dias): "
                           f"temperatura média {num(d['t_media'], 1)} °C, umidade relativa "
                           f"média {num(d['ur_media'], 1)}%, chuva {num(d['chuva_mm'], 1)} mm, "
                           f"molhamento {num(d['molhamento_h'], 1)} h.", cl["id"])

    # Fontes --------------------------------------------------------------------------------
    if not fontes:
        t.diz("fontes", f"Sem fonte no repositório de conhecimento para a cultura "
                        f"{_cultura(c['cultura'])} e estas hipóteses: o parecer não cita "
                        "literatura, bula nem registro.", caso["id"])
    for f in fontes:
        aviso = ""
        if f["ficticio"]:
            aviso = " — FICTÍCIA (dado de teste)"
        elif f["bloqueio"]:
            aviso = f" — bloqueada para uso operacional: {f['bloqueio']}"
        secao = f", seção {livre(f['secao'])}" if f.get("secao") else ""
        t.diz("fontes", f"Fonte consultada: {livre(f['titulo'])}, versão {livre(f['versao'])} "
                        f"({f['tipo']}, {livre(f['origem'], 300)}{secao}){aviso}.", f["id"])

    # O que o agrônomo ensinou -----------------------------------------------------------------
    for li in _por_tipo(dossie, "licoes"):
        for x in li["dados"]["licoes"]:
            viu = "; ".join(s for s in (livre(s, 120) for s in x.get("sintomas") or [])
                            if s != LIVRE_OMITIDO)
            onde = ", ".join(v for v in (x.get("estrato"), x.get("face")) if v)
            porque = x.get("porque") or ""
            # Número no texto dele é afirmação dele, não evidência: fica no dossiê.
            porque = "" if _TEM_NUMERO.search(porque) else livre(porque, 400)
            partes = [p for p in (f"viu {viu}" if viu else "", f"onde: {onde}" if onde else "",
                                  porque if porque and porque != LIVRE_OMITIDO else "") if p]
            if not partes:
                continue
            local = "neste talhão" if x.get("do_talhao") else "em outro talhão do cliente"
            t.diz("licoes", f"{livre(x['autor'])} ensinou em {x['data']} ({local}), para "
                            f"{_nome(x['classe'], hip)}: " + "; ".join(partes) + ".", li["id"])

    # Regras dos agrônomos, com a medida -------------------------------------------------------
    for ra in _por_tipo(dossie, "regras_agronomo"):
        for x in ra["dados"]["regras"]:
            regra = x.get("regra") or ""
            regra = LIVRE_OMITIDO if _TEM_NUMERO.search(regra) else livre(regra, 300)
            com, sem = x.get("com_condicao"), x.get("sem_condicao")
            contagem = (f" ({com['com_doenca']} de {com['casos']} casos com a condição; "
                        f"{sem['com_doenca']} de {sem['casos']} sem)"
                        if com and sem and x["veredito"] != "poucos_dados" else "")
            t.diz("regras_agronomo",
                  f"Regra de {livre(x['autor'])}: {regra} — condição: {x['condicao']}, "
                  f"{'aumenta' if x['efeito'] == 'aumenta' else 'diminui'} "
                  f"{_nome(x['doenca'], hip)}. Medida: {VEREDITOS_DE_REGRA[x['veredito']]}"
                  f"{contagem}.", ra["id"])

    # Regras --------------------------------------------------------------------------------
    for r in _por_tipo(dossie, "regras"):
        for a in r["dados"]["aplicadas"]:
            t.diz("regras", f"Regra {a['codigo']}: {a['efeito']}.", r["id"],
                  *([a["evidencia"]] if a.get("evidencia") else []))

    return {"afirmacoes": t.afirmacoes, "verificacoes": verificacoes(dossie, fontes),
            "fecho": FECHO}


def verificacoes(dossie: dict[str, Any], fontes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """O que falta verificar antes de qualquer intervenção. Nenhuma sai como "ok"."""
    hip = dossie["hipoteses"]
    caso = _por_tipo(dossie, "caso")[0]
    cultura = caso["dados"]["cultura"]
    regulatorias = [f for f in fontes if f["regulatorio"]]
    vigentes = [f for f in regulatorias if f["uso_operacional"]]
    saida: list[dict[str, Any]] = []

    def item(codigo: str, situacao: str, detalhe: str, citacoes: list[str]) -> None:
        titulo = dict(VERIFICACOES)[codigo]
        saida.append({"codigo": codigo, "titulo": titulo, "situacao": situacao,
                      "detalhe": detalhe, "citacoes": sorted(set(citacoes), key=_ordem_citacao)})

    visuais = _por_tipo(dossie, "visual") + _por_tipo(dossie, "fusao_planta")
    motivos = [lim for v in visuais for lim in v["limitacoes"]]
    item("diagnostico", "a_verificar",
         "Confirmar a hipótese no campo; " + (
             f"{len(hip.get('alternativas') or [])} alternativa(s) não descartada(s). "
             if hip.get("principal") else "não há hipótese. ")
         + ("Limitações: " + "; ".join(motivos[:4]) + "." if motivos else ""),
         [v["id"] for v in visuais] or [caso["id"]])
    modelos = sorted({v["versao_modelo"] for v in visuais if v.get("versao_modelo")})
    item("cultura", "a_verificar",
         f"Cultura cadastrada no talhão: {_cultura(cultura)}. Conferir que o modelo ("
         + (", ".join(modelos) or "nenhum") + ") é o da cultura e do estágio.", [caso["id"]])
    alvo = hip.get("principal") or "a hipótese"
    if not regulatorias:
        situacao, base = "sem_fonte", (f"Sem bula nem registro MAPA no repositório para "
                                       f"{_cultura(cultura)} e {alvo}.")
        cit = [caso["id"]]
    elif not vigentes:
        situacao = "bloqueado"
        base = "Fonte regulatória sem uso operacional: " + "; ".join(
            f"{livre(f['titulo'])} ({f['bloqueio']})" for f in regulatorias) + "."
        cit = [f["id"] for f in regulatorias]
    else:
        situacao = "a_verificar"
        base = ("Há fonte regulatória verificada e dentro da validade (" + ", ".join(
            f["id"] for f in vigentes) + "); conferir nela, para o produto escolhido.")
        cit = [f["id"] for f in vigentes]
    textos = {
        "registro_vigente": "Registro do produto no MAPA vigente para a cultura.",
        "alvo_autorizado": f"O alvo ({alvo}) consta como autorizado na bula vigente.",
        "dose_de_bula": "Dose dentro da faixa da bula vigente. O parecer não indica dose.",
        "restricoes": "Restrições de aplicação da bula (cultura, estágio, modo de aplicação).",
        "intervalo_de_seguranca": "Intervalo de segurança (carência) até a colheita.",
    }
    for codigo in REGULATORIAS:
        item(codigo, situacao, f"{textos[codigo]} {base}", cit)
    clima = next((i for i in _por_tipo(dossie, "clima") if i["disponivel"]), None)
    if clima is None:
        item("condicoes_ambientais", "sem_dado",
             "Sem dado climático validado: vento, chuva e temperatura na hora da aplicação "
             "são conferidos pelo responsável e pelo Safety Engine.", [caso["id"]])
    else:
        item("condicoes_ambientais", "a_verificar",
             "O clima resumido é histórico; as condições na hora da aplicação (vento, chuva, "
             "temperatura) são conferidas pelo responsável e pelo Safety Engine.", [clima["id"]])
    return saida


def texto(composto: dict[str, Any]) -> str:
    """O parecer em texto corrido, seção a seção, com as citações entre colchetes."""
    titulos = {"caso": "Caso", "hipoteses": "Hipóteses", "evidencia": "Evidência",
               "limitacoes": "Limitações", "historico": "Histórico", "risco": "Risco (gêmeo)",
               "clima": "Clima", "licoes": "O que o agrônomo ensinou",
               "regras_agronomo": "Regras dos agrônomos", "fontes": "Fontes",
               "regras": "Regras determinísticas"}
    linhas: list[str] = []
    atual = None
    for a in composto["afirmacoes"]:
        if a["secao"] != atual:
            atual = a["secao"]
            linhas += ["", f"## {titulos.get(atual, atual)}"]
        linhas.append(f"- {a['texto']} [{', '.join(a['citacoes'])}]")
    linhas += ["", "## O que falta verificar antes de qualquer intervenção"]
    for v in composto["verificacoes"]:
        linhas.append(f"- {v['titulo']} — {v['situacao']}: {v['detalhe']} "
                      f"[{', '.join(v['citacoes'])}]")
    linhas += ["", composto["fecho"]]
    return "\n".join(linhas).strip() + "\n"
