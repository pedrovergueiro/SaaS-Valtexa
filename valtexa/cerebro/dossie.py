"""Dossiê de evidências de um caso (uma planta ou uma observação/foco).

O dossiê é o **único** material do parecer: o compositor determinístico só escreve o que
está aqui, e o provedor de linguagem (quando ligado) só pode citar o que está aqui. Cada item
tem um identificador estável dentro do dossiê (``E1``, ``E2``...), a origem (sistema, tabela
ou rota, identificadores), a versão do modelo que o produziu e as **limitações** — o que o
item não diz.

Itens, nesta ordem (os que não existem para o caso ficam de fora; os que existem mas não
responderam entram com ``disponivel=False`` e o motivo):

``visual``          diagnóstico da nuvem (dupla validação): classe, confiança, conjunto
                    conformal (as hipóteses alternativas), novidade, portão de enquadramento;
``captura``         o que o Rover mediu do quadro: régua de captura por recorte, recortes com
                    conjunto conformal ambíguo, percepção ativa, profundidade;
``fusao_planta``    a fusão por planta (IA): posterior por doença, vistas, calibração;
``lesoes_3d``       as lesões no referencial da planta, reencontradas entre passadas;
``evolucao``        a planta nas passadas fechadas, mudanças e AUDPC;
``historico``       o que a plataforma sabe do talhão: rótulo de campo do agrônomo para a
                    planta, diagnósticos recentes do talhão, pareceres anteriores e revisões;
``gemeo``           o gêmeo digital: risco da planta no horizonte, faixa p10-p90, membros,
                    parâmetros ajustados ou de literatura, avisos;
``clima``           só se houver série **observada** (estação) ou de reanálise na janela —
                    previsão e climatologia não entram como histórico;
``regras``          as regras determinísticas da plataforma que se aplicam ao caso.

As leituras da IA (fusão, lesões, evolução, gêmeo, clima) vêm por :class:`FonteDaIA`, que o
teste troca por um dublê. **Os pesos reais não rodam aqui**: o que a fusão e o gêmeo devolvem
num teste é dado do dublê.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Protocol

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from valtexa.cerebro.rag import nomes_do_alvo
from valtexa.models import (
    Decision,
    Detection,
    Diagnosis,
    DiagnosisStatus,
    EdgeRecord,
    Field,
    Observation,
    PlantLabel,
    as_utc,
)
from valtexa.models.cerebro import Parecer, RevisaoParecer
from valtexa.services import plant_map
from valtexa.services.ai_pipeline import HEALTHY_LABELS

VERSAO = "dossie-1"
JANELA_CLIMA_DIAS = 14
JANELA_HISTORICO_DIAS = 90
HORIZONTE_GEMEO_DIAS = 14
RISCO_MINIMO_GEMEO = 0.01
"""A previsão lista as plantas com risco ≥ isto; abaixo, o dossiê diz "abaixo de 0,01"."""
FONTES_CLIMA_HISTORICO = ("estacao", "open-meteo:historico")
POSTERIOR_ALTERNATIVA = 0.10
"""Uma doença com posterior da fusão ≥ isto (e que não é a principal) entra como alternativa."""


class IndisponivelError(RuntimeError):
    """A leitura não respondeu (serviço fora, recusa, talhão sem histórico)."""


class FonteDaIA(Protocol):
    def planta(self, field_id: str, plant_ref: str) -> dict | None: ...
    def evolucao(self, field_id: str, plant_ref: str) -> dict | None: ...
    def lesoes(self, field_id: str, plant_ref: str) -> dict | None: ...
    def previsao(self, field_id: str, doenca: str, horizonte_dias: int) -> dict | None: ...
    def clima(self, field_id: str) -> dict | None: ...


class FonteDaIAPadrao:
    """O serviço de inferência da própria ValTexa (``settings.inference_url``), não serviço
    externo. Fora do ar, recusa e "sem histórico" viram :class:`IndisponivelError`/``None``."""

    @staticmethod
    def _chama(funcao, *args):
        try:
            return funcao(*args)
        except plant_map.PlantMapUnavailableError as exc:  # inclui a recusa (409/422)
            raise IndisponivelError(str(exc)) from exc

    def planta(self, field_id: str, plant_ref: str) -> dict | None:
        for p in self._chama(plant_map.plants, field_id) or []:
            if p.get("plant_id") == plant_ref:
                return p
        return None

    def evolucao(self, field_id: str, plant_ref: str) -> dict | None:
        return self._chama(plant_map.evolution, field_id, plant_ref)

    def lesoes(self, field_id: str, plant_ref: str) -> dict | None:
        return self._chama(plant_map.lesoes, field_id, plant_ref)

    def previsao(self, field_id: str, doenca: str, horizonte_dias: int) -> dict | None:
        return self._chama(plant_map.previsao_gemeo, field_id, {
            "doenca": doenca, "horizonte_dias": horizonte_dias, "plantas": "em_risco",
            "risco_minimo": RISCO_MINIMO_GEMEO})

    def clima(self, field_id: str) -> dict | None:
        return self._chama(plant_map.clima, field_id, True)


@dataclass(frozen=True)
class Caso:
    tipo: str
    """``planta`` ou ``observacao``."""
    field_id: str
    plant_ref: str | None = None
    observation_id: str | None = None


@dataclass
class _Montagem:
    itens: list[dict[str, Any]] = field(default_factory=list)

    def item(self, tipo: str, titulo: str, *, origem: dict[str, Any], dados: dict[str, Any],
             limitacoes: list[str] | None = None, versao_modelo: str | None = None,
             disponivel: bool = True, motivo: str | None = None) -> dict[str, Any]:
        novo = {"id": f"E{len(self.itens) + 1}", "tipo": tipo, "titulo": titulo,
                "disponivel": disponivel, "motivo_indisponivel": motivo, "origem": origem,
                "versao_modelo": versao_modelo, "dados": dados,
                "limitacoes": list(limitacoes or [])}
        self.itens.append(novo)
        return novo

    def indisponivel(self, tipo: str, titulo: str, origem: dict[str, Any], motivo: str) -> None:
        self.item(tipo, titulo, origem=origem, dados={}, disponivel=False, motivo=motivo,
                  limitacoes=["sem esta evidência, o parecer não fala deste aspecto"])


def _r(x: Any, casas: int = 4) -> Any:
    return round(float(x), casas) if isinstance(x, (int, float)) and not isinstance(x, bool) \
        else x


# ---------------------------------------------------------------------------------------------
# Itens que vêm do banco da plataforma
# ---------------------------------------------------------------------------------------------


def _visual(m: _Montagem, session: Session, diag: Diagnosis) -> dict[str, Any]:
    primaria = session.get(Detection, diag.primary_detection_id) if diag.primary_detection_id \
        else None
    sinais = (primaria.signals if primaria is not None else None) or {}
    conjunto = sinais.get("prediction_set")
    lim: list[str] = []
    if conjunto is None:
        lim.append("sem conjunto conformal: o modelo não tem calibração conformal, as "
                   "alternativas não estão quantificadas")
    elif len(conjunto) > 1:
        lim.append(f"conjunto conformal com {len(conjunto)} classes: não dá para descartar "
                   + ", ".join(c for c in conjunto if c != diag.label))
    elif len(conjunto) == 0:
        lim.append("conjunto conformal vazio: nenhuma classe conhecida é compatível")
    if diag.novelty_score is not None and diag.novelty_score > 1.0:
        lim.append("novidade acima de 1,0: a imagem está longe do que o modelo conhece")
    if sinais.get("in_scope") is False:
        lim.append("o portão de enquadramento viu outra coisa que não folha em close "
                   f"({sinais.get('scene') or 'cena desconhecida'})")
    if diag.status in (DiagnosisStatus.NEEDS_REVIEW, DiagnosisStatus.INCONCLUSIVE,
                       DiagnosisStatus.PENDING):
        lim.append(f"a dupla validação não fechou (situação {diag.status.value})")
    if diag.status is DiagnosisStatus.AI_VALIDATED:
        lim.append("as duas análises concordaram; isso ainda não é a confirmação do agrônomo")
    lim.append("classificação de imagem: compatibilidade com classes treinadas, não laudo")
    dados = {
        "observation_id": diag.observation_id, "diagnosis_id": diag.id,
        "classe": diag.label, "confianca": _r(diag.confidence), "situacao": diag.status.value,
        "concordancia": diag.agreement.value, "novidade": _r(diag.novelty_score),
        "conjunto_conformal": None if conjunto is None else list(conjunto),
        "enquadramento_ok": sinais.get("in_scope"), "cena": sinais.get("scene"),
        "rotulo_do_agronomo": diag.reviewed_label,
        "capturado_em": None,
    }
    obs = session.get(Observation, diag.observation_id)
    if obs is not None:
        dados["capturado_em"] = as_utc(obs.captured_at).isoformat()
        dados["plant_ref"] = obs.plant_ref
    return m.item(
        "visual", "Classificação da imagem (dupla validação)",
        origem={"sistema": "plataforma", "tabela": "diagnosis", "id": diag.id,
                "pipeline": diag.pipeline_version},
        versao_modelo=(f"{primaria.model_key}@{primaria.model_version}" if primaria is not None
                       and primaria.model_key else diag.pipeline_version),
        dados=dados, limitacoes=lim)


def _captura(m: _Montagem, session: Session, observation_id: str) -> None:
    registro = session.scalars(select(EdgeRecord).where(
        EdgeRecord.observation_id == observation_id, EdgeRecord.kind == "result")).first()
    if registro is None:
        return
    corpo = registro.payload or {}
    tiles = corpo.get("tiles") or {}
    qualidade = tiles.get("quality") or []
    medidos = [q for q in qualidade if q is not None]
    ruins = [q for q in medidos if q]
    problemas: dict[str, int] = {}
    for q in ruins:
        for p in q:
            problemas[p] = problemas.get(p, 0) + 1
    conjuntos = [c for c in (tiles.get("conformal_sets") or []) if c is not None]
    ambiguos = sum(1 for c in conjuntos if len(c) > 1)
    perc = corpo.get("percepcao") or {}
    rgbd = corpo.get("rgbd") or {}
    lim = []
    if not medidos:
        lim.append("o Rover não mediu a qualidade da captura neste quadro")
    elif ruins:
        lim.append(f"{len(ruins)} de {len(medidos)} recortes com problema de captura")
    if ambiguos:
        lim.append(f"{ambiguos} recortes com conjunto conformal de mais de uma classe")
    if rgbd and rgbd.get("sufficient") is False:
        lim.append("profundidade insuficiente: a escala dos recortes pode estar errada")
    if perc.get("reasons") and not perc.get("resolved"):
        lim.append("a percepção ativa achou o quadro incerto e não resolveu")
    modelo = corpo.get("model") or {}
    m.item("captura", "Qualidade da captura no Rover",
           origem={"sistema": "rover", "tabela": "edge_record", "id": registro.id,
                   "record_id": registro.record_id, "device_id": registro.device_id},
           versao_modelo=(f"{modelo.get('key')}@{modelo.get('version')}" if modelo.get("key")
                          else registro.model_version),
           dados={"recortes_medidos": len(medidos), "recortes_com_problema": len(ruins),
                  "problemas": problemas, "recortes_conformal_ambiguo": ambiguos,
                  "percepcao_motivos": list(perc.get("reasons") or []),
                  "percepcao_resolveu": perc.get("resolved"),
                  "profundidade_suficiente": rgbd.get("sufficient") if rgbd else None,
                  "categoria_no_rover": registro.type, "confianca_no_rover": _r(
                      registro.confidence)},
           limitacoes=lim)


def _historico(m: _Montagem, session: Session, tenant_id: str, caso: Caso, agora: datetime,
               plant_ref: str | None) -> None:
    desde = agora - timedelta(days=JANELA_HISTORICO_DIAS)
    rotulos = []
    if plant_ref:
        rotulos = session.scalars(select(PlantLabel).where(
            PlantLabel.tenant_id == tenant_id, PlantLabel.field_id == caso.field_id,
            PlantLabel.plant_ref == plant_ref).order_by(PlantLabel.labeled_at.desc())
            .limit(5)).all()
    contagem = session.execute(
        select(func.coalesce(Diagnosis.reviewed_label, Diagnosis.label), func.count())
        .where(Diagnosis.tenant_id == tenant_id, Diagnosis.field_id == caso.field_id,
               Diagnosis.created_at >= desde)
        .group_by(func.coalesce(Diagnosis.reviewed_label, Diagnosis.label))).all()
    anteriores = []
    if plant_ref or caso.observation_id:
        q = select(Parecer).where(Parecer.tenant_id == tenant_id,
                                  Parecer.field_id == caso.field_id)
        q = q.where(Parecer.plant_ref == plant_ref) if plant_ref else q.where(
            Parecer.observation_id == caso.observation_id)
        for p in session.scalars(q.order_by(Parecer.created_at.desc()).limit(3)).all():
            revs = session.scalars(select(RevisaoParecer).where(
                RevisaoParecer.parecer_id == p.id).order_by(RevisaoParecer.revisado_em)).all()
            anteriores.append({"parecer_id": p.id, "gerado_em": as_utc(p.created_at).isoformat(),
                               "revisoes": [{"decisao": r.decisao,
                                             "diagnostico_revisor": r.diagnostico_revisor,
                                             "revisado_em": as_utc(r.revisado_em).isoformat()}
                                            for r in revs]})
    lim = [f"diagnósticos dos últimos {JANELA_HISTORICO_DIAS} dias do talhão; safras "
           "anteriores só entram como fonte do repositório (histórico da propriedade)"]
    if plant_ref and not rotulos:
        lim.append("a planta não tem rótulo de campo do agrônomo")
    m.item("historico", "Histórico do talhão na plataforma",
           origem={"sistema": "plataforma", "tabelas": ["plant_label", "diagnosis", "parecer"],
                   "field_id": caso.field_id},
           dados={"rotulos_de_campo": [{"classe": r.label, "passada": r.mission_id,
                                        "incidencia_percent": _r(r.incidence_percent, 2),
                                        "rotulado_em": as_utc(r.labeled_at).isoformat()}
                                       for r in rotulos],
                  "diagnosticos_do_talhao": {str(k or "sem_classe"): int(n)
                                             for k, n in sorted(contagem, key=lambda x: str(x[0]))},
                  "janela_dias": JANELA_HISTORICO_DIAS, "pareceres_anteriores": anteriores},
           limitacoes=lim)


# ---------------------------------------------------------------------------------------------
# Itens que vêm da IA (fusão, lesões, evolução, gêmeo, clima)
# ---------------------------------------------------------------------------------------------


def _fusao(m: _Montagem, ia: FonteDaIA, field_id: str, plant_ref: str) -> dict | None:
    origem = {"sistema": "ia", "rota": f"/fields/{field_id}/plants", "plant_id": plant_ref}
    try:
        p = ia.planta(field_id, plant_ref)
    except IndisponivelError as exc:
        m.indisponivel("fusao_planta", "Fusão por planta", origem, str(exc))
        return None
    if p is None:
        m.indisponivel("fusao_planta", "Fusão por planta", origem,
                       "a fusão não tem esta planta (o Rover ainda não passou por ela?)")
        return None
    posteriores = sorted(((k, float(v)) for k, v in (p.get("posteriors") or {}).items()),
                         key=lambda kv: -kv[1])
    lim = []
    if not p.get("calibration_id"):
        lim.append("fusão com os valores de partida: sem calibração medida no campo")
    if int(p.get("n_frames") or 0) < 2:
        lim.append("planta vista em um quadro só")
    if int(p.get("n_needs_review") or 0):
        lim.append(f"{p['n_needs_review']} recortes pedem revisão")
    if int(p.get("n_tiles_out_of_scope") or 0):
        lim.append(f"{p['n_tiles_out_of_scope']} recortes fora do escopo do modelo")
    if p.get("status") == "revisar":
        lim.append("a fusão marcou a planta para revisão")
    lim.append("a posterior é a probabilidade estimada pela fusão, não a certeza da doença")
    return m.item(
        "fusao_planta", "Fusão por planta (todas as vistas)", origem=origem,
        versao_modelo=p.get("calibration_id") or "fusao:valores-de-partida",
        dados={"situacao": p.get("status"), "doenca_principal": p.get("primary_disease"),
               "posterior_principal": _r(p.get("primary_posterior")),
               "posteriores": {k: _r(v) for k, v in posteriores[:4]},
               "incidencia": _r(p.get("incidence")), "recortes": p.get("n_tiles"),
               "quadros": p.get("n_frames"), "cameras": p.get("n_cameras"),
               "vistas_efetivas": _r(p.get("effective_views"), 2),
               "passada": p.get("pass_id"), "rua": p.get("row_id"),
               "quando": p.get("time")},
        limitacoes=lim)


def _lesoes(m: _Montagem, ia: FonteDaIA, field_id: str, plant_ref: str) -> None:
    origem = {"sistema": "ia", "rota": f"/fields/{field_id}/plants/{plant_ref}/lesoes"}
    try:
        corpo = ia.lesoes(field_id, plant_ref)
    except IndisponivelError as exc:
        m.indisponivel("lesoes_3d", "Lesões no referencial da planta", origem, str(exc))
        return
    if not corpo:
        return
    trilhas = corpo.get("tracks") or []
    estados: dict[str, int] = {}
    por_doenca: dict[str, int] = {}
    face_indeterminada = sem_3d = 0
    for t in trilhas:
        estados[str(t.get("state"))] = estados.get(str(t.get("state")), 0) + 1
        por_doenca[str(t.get("disease"))] = por_doenca.get(str(t.get("disease")), 0) + 1
        face_indeterminada += t.get("face") in (None, "indeterminada")
        sem_3d += (t.get("position") or {}).get("canopy_depth_m") is None
    lim = []
    if trilhas and sem_3d == len(trilhas):
        lim.append("sem geometria 3D: só posição ao longo da rua e altura")
    if face_indeterminada:
        lim.append(f"{face_indeterminada} lesões com face da folha indeterminada")
    m.item("lesoes_3d", "Lesões no referencial da planta", origem=origem,
           dados={"trilhas": len(trilhas), "por_estado": estados, "por_doenca": por_doenca,
                  "passadas": corpo.get("passes") or []},
           limitacoes=lim)


def _evolucao(m: _Montagem, ia: FonteDaIA, field_id: str, plant_ref: str) -> None:
    origem = {"sistema": "ia", "rota": f"/fields/{field_id}/plants/{plant_ref}/evolution"}
    try:
        corpo = ia.evolucao(field_id, plant_ref)
    except IndisponivelError as exc:
        m.indisponivel("evolucao", "Evolução entre passadas", origem, str(exc))
        return
    if not corpo:
        return
    hist = corpo.get("history") or []
    m.item("evolucao", "Evolução entre passadas fechadas", origem=origem,
           dados={"passadas": [{"passada": h.get("pass_id"), "situacao": h.get("status"),
                                "doenca_principal": h.get("primary_disease"),
                                "incidencia": _r(h.get("incidence"))} for h in hist[-6:]],
                  "mudancas": [c.get("change") for c in (corpo.get("changes") or [])][-6:],
                  "audpc": _r(corpo.get("audpc"), 3), "audpc_unidade": corpo.get("audpc_unit")},
           limitacoes=(["uma passada só: sem tendência"] if len(hist) < 2 else [])
           + ["só passadas fechadas"])


def _gemeo(m: _Montagem, ia: FonteDaIA, field_id: str, plant_ref: str | None,
           doenca: str) -> None:
    origem = {"sistema": "ia", "rota": f"/fields/{field_id}/gemeo/previsao", "doenca": doenca}
    try:
        prev = ia.previsao(field_id, doenca, HORIZONTE_GEMEO_DIAS)
    except IndisponivelError as exc:
        m.indisponivel("gemeo", f"Gêmeo digital ({doenca})", origem, str(exc))
        return
    if not prev:
        m.indisponivel("gemeo", f"Gêmeo digital ({doenca})", origem,
                       "o gêmeo não tem o talhão (sem passadas assimiladas)")
        return
    da_planta = next((p for p in prev.get("plantas_detalhe") or []
                      if p.get("plant_id") == plant_ref), None) if plant_ref else None
    lim = []
    if not prev.get("parametros_ajustados"):
        lim.append(f"parâmetros da doença de {prev.get('origem_parametros') or 'literatura'}, "
                   "não ajustados às passadas deste talhão")
    lim.append(f"previsão por conjunto de {prev.get('membros')} membros: a faixa p10-p90 é a "
               "incerteza, não um erro máximo")
    if plant_ref and da_planta is None:
        lim.append(f"planta fora da lista do gêmeo: risco abaixo de {RISCO_MINIMO_GEMEO}")
    lim += [str(a) for a in prev.get("avisos") or []]
    planta = None if da_planta is None else {
        k: _r(da_planta.get(k)) for k in ("risco", "risco_p10", "risco_p90",
                                          "esporulando_agora", "latente_agora",
                                          "sinal_no_horizonte")}
    m.item("gemeo", f"Gêmeo digital ({doenca})", origem=origem,
           versao_modelo=f"gemeo:{prev.get('origem_parametros') or 'desconhecida'}",
           dados={"doenca": doenca, "data_base": prev.get("data_base"),
                  "horizonte": prev.get("horizonte"), "horizonte_dias": HORIZONTE_GEMEO_DIAS,
                  "membros": prev.get("membros"),
                  "parametros_ajustados": bool(prev.get("parametros_ajustados")),
                  "planta": planta,
                  "infectadas_no_horizonte_esperado": _r(
                      prev.get("infectadas_no_horizonte_esperado"), 2),
                  "infectadas_no_horizonte_p10_p90": prev.get("infectadas_no_horizonte_p10_p90"),
                  "janelas_de_infeccao": len(prev.get("janelas_de_infeccao") or []),
                  "focos_no_horizonte": prev.get("focos_no_horizonte")},
           limitacoes=lim)


def _clima(m: _Montagem, ia: FonteDaIA, field_id: str, data_caso: date) -> None:
    origem = {"sistema": "ia", "rota": f"/fields/{field_id}/clima"}
    try:
        corpo = ia.clima(field_id)
    except IndisponivelError as exc:
        m.indisponivel("clima", "Clima do talhão", origem, str(exc))
        return
    inicio = data_caso - timedelta(days=JANELA_CLIMA_DIAS)
    dias = [d for d in (corpo or {}).get("serie") or []
            if inicio.isoformat() <= str(d.get("data")) <= data_caso.isoformat()]
    usados = [d for d in dias if d.get("fonte") in FONTES_CLIMA_HISTORICO]
    fora = len(dias) - len(usados)
    if not usados:
        m.indisponivel("clima", "Clima do talhão", origem,
                       f"sem dia observado ou de reanálise nos {JANELA_CLIMA_DIAS} dias até o "
                       "caso: o parecer não fala de clima")
        return
    n = len(usados)
    lim = []
    if any(d.get("fonte") != "estacao" for d in usados):
        lim.append("parte dos dias é reanálise (Open-Meteo), não medida na fazenda")
    if not all(d.get("molhamento_medido") for d in usados):
        lim.append("molhamento foliar estimado (UR ≥ 90% ou chuva), sem sensor")
    if n < JANELA_CLIMA_DIAS:
        lim.append(f"{JANELA_CLIMA_DIAS - n} dias da janela sem dado")
    if fora:
        lim.append(f"{fora} dias de previsão ou climatologia deixados de fora")
    m.item("clima", f"Clima nos {JANELA_CLIMA_DIAS} dias até o caso", origem=origem,
           dados={"dias": n, "inicio": min(str(d["data"]) for d in usados),
                  "fim": max(str(d["data"]) for d in usados),
                  "t_media": _r(sum(float(d["t_media"]) for d in usados) / n, 1),
                  "ur_media": _r(sum(float(d["ur_media"]) for d in usados) / n, 1),
                  "chuva_mm": _r(sum(float(d["chuva_mm"]) for d in usados), 1),
                  "molhamento_h": _r(sum(float(d["molhamento_h"]) for d in usados), 1),
                  "por_fonte": {f: sum(1 for d in usados if d.get("fonte") == f)
                                for f in sorted({d.get("fonte") for d in usados})}},
           limitacoes=lim)


# ---------------------------------------------------------------------------------------------
# Regras determinísticas e hipóteses
# ---------------------------------------------------------------------------------------------


def _regras(m: _Montagem, session: Session, diags: list[Diagnosis]) -> None:
    aplicadas: list[dict[str, Any]] = []
    for it in m.itens:
        d = it["dados"]
        if it["tipo"] == "visual":
            conj = d.get("conjunto_conformal")
            if conj is not None and len(conj) != 1:
                aplicadas.append({"codigo": "hipotese_nao_unica", "evidencia": it["id"],
                                  "efeito": "o parecer lista as alternativas e pede revisão"})
            if (d.get("novidade") or 0) > 1.0:
                aplicadas.append({"codigo": "possivel_classe_nova", "evidencia": it["id"],
                                  "efeito": "a classe do modelo pode não ser a do problema"})
            if d.get("situacao") != DiagnosisStatus.AI_VALIDATED.value and d.get(
                    "situacao") != DiagnosisStatus.HUMAN_CONFIRMED.value:
                aplicadas.append({"codigo": "dupla_validacao_aberta", "evidencia": it["id"],
                                  "efeito": "diagnóstico vai para a fila do agrônomo"})
        if it["tipo"] == "captura" and d.get("recortes_com_problema"):
            aplicadas.append({"codigo": "reobservar_captura", "evidencia": it["id"],
                              "efeito": "recomenda-se nova vista antes de concluir"})
        if it["tipo"] == "fusao_planta" and d.get("situacao") == "revisar":
            aplicadas.append({"codigo": "fusao_pede_revisao", "evidencia": it["id"],
                              "efeito": "a planta entra na fila de revisão"})
    for diag in diags:
        for dec in session.scalars(select(Decision).where(
                Decision.diagnosis_id == diag.id).order_by(Decision.created_at)).all():
            aplicadas.append({"codigo": f"motor_de_decisao:{dec.reason_code}",
                              "resultado": dec.outcome.value, "versao_regra": dec.rule_version,
                              "decision_id": dec.id,
                              "efeito": "recomendação do motor de decisão (não é comando)"})
    m.item("regras", "Regras determinísticas da plataforma",
           origem={"sistema": "plataforma", "modulos": ["cerebro.dossie",
                                                        "services.decision_engine"]},
           dados={"aplicadas": aplicadas},
           limitacoes=["o Safety Engine não é chamado aqui: ele verifica a missão quando o "
                       "agrônomo autoriza, nunca o parecer"])


def hipoteses(itens: list[dict[str, Any]]) -> dict[str, Any]:
    """A hipótese principal e as alternativas, cada uma com as evidências que a sustentam.

    Principal: a da fusão por planta (junta todas as vistas) quando há; senão a do diagnóstico
    visual mais recente. Alternativas: o resto do conjunto conformal e as doenças com
    posterior da fusão ≥ :data:`POSTERIOR_ALTERNATIVA`.
    """
    principal = fonte = None
    alternativas: dict[str, list[str]] = {}
    for it in itens:
        if it["tipo"] == "fusao_planta" and it["disponivel"]:
            principal, fonte = it["dados"].get("doenca_principal"), it["id"]
            break
    if principal is None:
        for it in itens:
            if it["tipo"] == "visual":
                principal, fonte = it["dados"].get("classe"), it["id"]
                break
    for it in itens:
        d = it["dados"]
        if it["tipo"] == "visual":
            for c in d.get("conjunto_conformal") or []:
                if c != principal:
                    alternativas.setdefault(c, []).append(it["id"])
        if it["tipo"] == "fusao_planta" and it["disponivel"]:
            for c, p in (d.get("posteriores") or {}).items():
                if c != principal and p >= POSTERIOR_ALTERNATIVA:
                    alternativas.setdefault(c, []).append(it["id"])
    return {"principal": principal, "evidencia_principal": fonte,
            "principal_e_sadia": principal in HEALTHY_LABELS,
            "alternativas": [{"classe": c, "evidencias": sorted(set(ev))}
                             for c, ev in sorted(alternativas.items())],
            "nomes": {c: list(nomes_do_alvo(c)[1:]) for c in
                      [principal, *alternativas] if c}}


# ---------------------------------------------------------------------------------------------
# Montagem
# ---------------------------------------------------------------------------------------------


def montar(session: Session, tenant_id: str, campo: Field, caso: Caso, ia: FonteDaIA, *,
           agora: datetime) -> dict[str, Any]:
    """O dossiê do caso. Determinístico para o mesmo banco, a mesma IA e o mesmo ``agora``."""
    m = _Montagem()
    diags: list[Diagnosis] = []
    plant_ref = caso.plant_ref
    data_caso = agora.date()
    imagens: list[dict[str, Any]] = []
    if caso.tipo == "observacao":
        obs = session.get(Observation, caso.observation_id)
        plant_ref = plant_ref or (obs.plant_ref if obs is not None else None)
        diags = session.scalars(select(Diagnosis).where(
            Diagnosis.observation_id == caso.observation_id).order_by(
            Diagnosis.created_at.desc()).limit(1)).all()
        if obs is not None:
            data_caso = as_utc(obs.captured_at).date()
    identificacao = {"tipo": caso.tipo, "field_id": caso.field_id, "talhao": campo.name,
                     "cultura": campo.crop, "estagio": campo.crop_stage, "plant_ref": plant_ref,
                     "observation_id": caso.observation_id,
                     "data_do_caso": data_caso.isoformat()}
    m.item("caso", "Identificação do caso",
           origem={"sistema": "plataforma", "tabela": "field", "id": campo.id},
           dados=identificacao,
           limitacoes=["a cultura é a cadastrada no talhão; o estágio, quando informado, "
                       "é o do cadastro"])
    if caso.tipo == "planta" and plant_ref:
        diags = session.scalars(
            select(Diagnosis).join(Observation, Observation.id == Diagnosis.observation_id)
            .where(Diagnosis.tenant_id == tenant_id, Diagnosis.field_id == caso.field_id,
                   Observation.plant_ref == plant_ref)
            .order_by(Diagnosis.created_at.desc()).limit(3)).all()
    for diag in diags:
        _visual(m, session, diag)
        _captura(m, session, diag.observation_id)
        obs = session.get(Observation, diag.observation_id)
        if obs is not None and obs.image_asset_id:
            imagens.append({"observation_id": obs.id, "asset_id": obs.image_asset_id})
    if plant_ref:
        _fusao(m, ia, caso.field_id, plant_ref)
        _lesoes(m, ia, caso.field_id, plant_ref)
        _evolucao(m, ia, caso.field_id, plant_ref)
    _historico(m, session, tenant_id, caso, agora, plant_ref)
    hip = hipoteses(m.itens)
    if hip["principal"] and not hip["principal_e_sadia"]:
        _gemeo(m, ia, caso.field_id, plant_ref, hip["principal"])
    _clima(m, ia, caso.field_id, data_caso)
    _regras(m, session, diags)
    dossie = {
        "versao": VERSAO, "gerado_em": agora.isoformat(),
        "caso": identificacao,
        "itens": m.itens, "hipoteses": hipoteses(m.itens), "imagens": imagens,
    }
    return dossie


def sha256(objeto: Any) -> str:
    return hashlib.sha256(json.dumps(objeto, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":"), default=str).encode()).hexdigest()
