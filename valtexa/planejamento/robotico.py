"""Planejamento robótico (8.3): o alocador do enxame com terreno e o orçamento de dados.

Reaproveita :mod:`valtexa.services.enxame` inteiro — as tarefas do gêmeo
(``/gemeo/prioridades``: valor da informação por trecho, que já junta risco e incerteza), as
verificações pós-aplicação obrigatórias, os agentes disponíveis com o orçamento de tempo da
bateria acima da reserva, o guloso por valor por segundo com desconto de sobreposição — e
acrescenta três restrições, cada uma com a premissa registrada:

* **Inclinação** — do relevo medido do talhão (``field.relief``, a mesma leitura que o Safety
  Engine usa em ``_check_slope``). Declividade máxima no limite do Rover ou acima: o Rover não
  recebe tarefa no talhão (o Safety Engine bloquearia a missão). Abaixo: o trabalho fica mais
  lento na proporção ``fator_declive x declividade_média / limite`` (premissa **não medida**;
  calibrar com a telemetria). Sem relevo medido: planejado como plano, e o plano diz.
* **Obstáculos** — da leitura de terreno da IA (``field.terrain``: saída de
  ``ia/app/obstacles.py`` pela rota de ``ia/app/terrain_api.py``, lida aqui, **sem editar
  aqueles arquivos**). Só os intransponíveis e só com ``resolution_ok``. Trecho com o centro
  dentro do retângulo de um obstáculo: fora para o Rover; trecho que encosta: soma o desvio
  (meio perímetro do retângulo, na velocidade do Rover). O drone sobrevoa.
* **Orçamento de dados da Starlink de cada Rover** — o que resta hoje
  (``teto_dia x (1 - reserva) - usado``, do relatório de :mod:`services.orcamento_dados`) é
  teto de bytes do agente; cada tarefa custa ``percurso x bytes_por_metro``. O padrão de
  ``bytes_por_metro`` é **SIMULADO** (``VALTEXA-ROVER/docs/ROVER_RUNTIME.md`` §27: ~0,95 GB
  de metadados em 10,8 km no cenário normal) — o pedido deve trazer o medido do Rover quando houver.

E duas calibrações do 7.3 (contra os dois modos de falha da alocação por incerteza):

* **valor mínimo por minuto de robô** (``valor_minimo_por_minuto``, do produtor): a tarefa que
  vale menos que isso por minuto de trabalho fica de fora — o Rover não roda por décimos de
  bit em talhão sadio. Sem o número, não corta (e o plano diz);
* **piso de vigilância** (``piso_vigilancia_dias``): trecho nunca visto, ou não visto há
  esse tanto de dias, ganha o valor mínimo positivo do plano em vez de zero — compete pelo
  que sobra da bateria, perde para qualquer trecho que informe mais, mas não fica esquecido
  quando o gêmeo está "certo" de que ali é sadio.

O plano mostra o **antes e depois** (o mesmo alocador sem as restrições) e cada tarefa que
saiu, com o porquê. A **próxima missão** de cada agente é só proposta: criar a missão (em
RASCUNHO) é ação de uma pessoa, pelo fluxo de sempre; autorizar é do Safety Engine.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from valtexa.models import Device, Field
from valtexa.planejamento.premissas import Premissas
from valtexa.services import elevation, enxame, geo, orcamento_dados
from valtexa.services.hal import capabilities_of

VERSAO = "robotico-1"
BYTES_POR_METRO_SIMULADO = 88_000
"""~0,95 GB de metadados (resultados com probabilidade por recorte) em 10,8 km (0,3 m/s por
10 h): a estimativa SIMULADA do dia normal, ``VALTEXA-ROVER/docs/ROVER_RUNTIME.md`` §27.
Não medido."""


def obstaculos(campo: Field) -> tuple[list[dict[str, Any]], str]:
    """Os intransponíveis da leitura de terreno da IA, com o retângulo em lon/lat."""
    leitura = campo.terrain or {}
    if not leitura:
        return [], "terreno não lido: obstáculos desconhecidos"
    if not leitura.get("resolution_ok"):
        return [], "imagem sem resolução para ler obstáculos (resolution_ok falso)"
    saida = []
    for o in leitura.get("objects") or []:
        contorno = o.get("outline") or []
        if o.get("traversable") or len(contorno) < 3:
            continue
        saida.append({"tipo": o.get("kind") or "desconhecido", "contorno": contorno,
                      "caixa": geo.bounding_box(contorno),
                      "confianca": o.get("confidence")})
    return saida, "lido da imagem (heurística da IA)" if leitura.get("heuristic", True) \
        else "lido da imagem"


def _caixa_da_tarefa(t: enxame.Tarefa) -> tuple[float, float, float, float] | None:
    if t.poligono:
        return geo.bounding_box(t.poligono)
    if t.centro:
        return (t.centro[0], t.centro[1], t.centro[0], t.centro[1])
    return None


def _encosta(a: tuple[float, ...], b: tuple[float, ...]) -> bool:
    return not (a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or b[3] < a[1])


def _meio_perimetro_m(caixa: tuple[float, float, float, float]) -> float:
    x0, y0, x1, y1 = caixa
    return geo.haversine_m(x0, y0, x1, y0) + geo.haversine_m(x0, y0, x0, y1)


class Restricoes:
    """A função ``restricao(tarefa, agente)`` do alocador, com o terreno do talhão."""

    def __init__(self, campo: Field, dispositivos: dict[str, Device], *, fator_declive: float,
                 obstaculos_: list[dict[str, Any]],
                 valor_minimo_por_minuto: float | None = None) -> None:
        self.relevo = campo.relief or None
        self.dispositivos = dispositivos
        self.fator_declive = fator_declive
        self.obstaculos = obstaculos_
        self.valor_minimo_por_minuto = valor_minimo_por_minuto

    def limite_deg(self, a: enxame.Agente) -> float:
        d = self.dispositivos.get(a.device_id)
        cap = capabilities_of(d.capabilities if d else {})
        return cap.number("max_slope_deg", elevation.LIMITE_DE_TOMBAMENTO_PADRAO_DEG)

    def __call__(self, t: enxame.Tarefa, a: enxame.Agente) -> tuple[float, str | None]:
        if self.valor_minimo_por_minuto and not t.obrigatoria:
            por_minuto = t.valor / (enxame.tempo_de_trabalho_s(t, a) / 60.0)
            if por_minuto < self.valor_minimo_por_minuto:
                return 0.0, (f"vale {por_minuto:.3g} por minuto de robô, abaixo do mínimo de "
                             f"{self.valor_minimo_por_minuto:.3g}")
        if a.tipo != "rover":
            return 0.0, None
        extra = 0.0
        if self.relevo:
            limite = self.limite_deg(a)
            maxima = float(self.relevo.get("declividade_maxima_deg") or 0.0)
            media = float(self.relevo.get("declividade_media_deg") or 0.0)
            if maxima >= limite:
                return 0.0, (f"declividade máxima medida {maxima:.0f}° ≥ limite de {limite:.0f}° "
                             f"do Rover {a.nome}: o Safety Engine bloquearia a missão")
            extra += enxame.tempo_de_trabalho_s(t, a) * self.fator_declive * (media / limite)
        caixa = _caixa_da_tarefa(t)
        if caixa is not None:
            for o in self.obstaculos:
                if t.centro and geo.contains_point(o["contorno"], t.centro[0], t.centro[1],
                                                   include_boundary=True):
                    return 0.0, f"o centro do trecho cai dentro de {o['tipo']} (intransponível)"
                if _encosta(caixa, o["caixa"]):
                    extra += _meio_perimetro_m(o["caixa"]) / a.velocidade_ms
        return extra, None


def piso_de_vigilancia(tarefas: list[enxame.Tarefa], dias: int | None
                       ) -> tuple[list[enxame.Tarefa], list[str], float | None]:
    """Trecho de inspeção esquecido (nunca visto, ou há ``dias`` ou mais) com valor abaixo do
    piso sobe para o piso = o menor valor positivo entre as tarefas do gêmeo."""
    if dias is None:
        return tarefas, [], None
    positivos = [t.valor for t in tarefas if t.valor > 0 and t.origem == "gemeo"]
    if not positivos:
        return tarefas, [], None
    piso = min(positivos)
    saida, subiram = [], []
    for t in tarefas:
        esquecida = t.tipo == "inspecao" and t.origem == "gemeo" and (
            t.dias_sem_ver is None or t.dias_sem_ver >= dias)
        if esquecida and t.valor < piso:
            quando = ("nunca vista" if t.dias_sem_ver is None
                      else f"vista há {t.dias_sem_ver} dias")
            saida.append(replace(t, valor=piso,
                                 motivo=f"piso de vigilância: {quando}; {t.motivo}"))
            subiram.append(t.id)
        else:
            saida.append(t)
    return saida, subiram, piso


def percurso_m(t: enxame.Tarefa, a: enxame.Agente) -> float:
    if t.area_m2 and a.largura_m > 0:
        return max(t.comprimento_m, t.area_m2 / a.largura_m)
    return t.comprimento_m


def orcamentos_de_dados(session: Session, agentes: Sequence[enxame.Agente],
                        dispositivos: dict[str, Device], *, reserva: float, agora: datetime
                        ) -> tuple[dict[str, float], list[dict[str, Any]]]:
    """O que resta hoje a cada Rover, e de onde saiu cada número."""
    orcamento: dict[str, float] = {}
    detalhe = []
    for a in agentes:
        if a.tipo != "rover":
            continue
        rel = orcamento_dados.relatorio(session, dispositivos[a.device_id], agora=agora)
        teto = rel["teto"]["efetivo_dia_bytes"]
        contado = rel["contado_no_rover"] or {}
        usado = contado.get("usado_bytes")
        linha = {"device_id": a.device_id, "nome": a.nome, "teto_dia_bytes": teto,
                 "origem_do_teto": rel["teto"]["origem"], "usado_hoje_bytes": usado,
                 "contado_em": rel["contado_em"]}
        if not teto:
            linha["restante_bytes"] = None
            linha["nota"] = "sem teto conhecido (nem da plataforma nem relatado pelo Rover): " \
                            "sem restrição de dados para este Rover"
        else:
            restante = max(0.0, float(teto) * (1.0 - reserva) - float(usado or 0))
            orcamento[a.device_id] = restante
            linha["restante_bytes"] = round(restante)
            if usado is None:
                linha["nota"] = "o Rover ainda não relatou o consumo de hoje: contado como zero"
        detalhe.append(linha)
    return orcamento, detalhe


def rotas(plano: enxame.Plano, dispositivos: dict[str, Device],
          bytes_da_tarefa) -> list[dict[str, Any]]:
    """A sequência de cada agente, com deslocamento, trabalho, bateria ao fim e dados."""
    saida = []
    for at in plano.atribuicoes:
        a = at.agente
        cap = capabilities_of(dispositivos[a.device_id].capabilities)
        pos = a.posicao
        passos, desloc, trabalho = [], 0.0, 0.0
        for t in at.tarefas:
            d = enxame.distancia_m(pos, t.centro)
            w = percurso_m(t, a)
            desloc += d
            trabalho += w
            passos.append({"tarefa": t.id, "tipo": t.tipo, "ruas": list(t.ruas),
                           "deslocamento_m": round(d, 1), "trabalho_m": round(w, 1),
                           "valor": round(t.valor, 4)})
            pos = t.centro or pos
        autonomia_s = max(60.0, cap.endurance_minutes * 60.0)
        bat_ini = a.bateria if a.bateria is not None else enxame.BATERIA_DESCONHECIDA * 100.0
        saida.append({
            "device_id": a.device_id, "nome": a.nome, "tipo": a.tipo, "passos": passos,
            "deslocamento_m": round(desloc, 1), "trabalho_m": round(trabalho, 1),
            "tempo_s": round(at.tempo_s, 1),
            "bateria_inicial_pct": round(bat_ini, 1),
            "bateria_final_estimada_pct": round(bat_ini - at.tempo_s / autonomia_s * 100.0, 1),
            "bytes_estimados": round(sum(bytes_da_tarefa(t, a) for t in at.tarefas)),
        })
    return saida


@dataclass
class Contexto:
    """As restrições do talhão e da frota, prontas para o alocador — usadas pelo plano de apoio
    e pelo plano do enxame que cria as missões (o mesmo cálculo nos dois)."""

    premissas: Premissas
    restricao: Restricoes
    bytes_por_metro: float
    orcamento: dict[str, float]
    dados: list[dict[str, Any]]
    obstaculos: list[dict[str, Any]]
    dispositivos: dict[str, Device]
    desconto: float
    piso_dias: int | None

    def bytes_da_tarefa(self, t: enxame.Tarefa, a: enxame.Agente) -> float:
        return percurso_m(t, a) * self.bytes_por_metro if a.tipo == "rover" else 0.0

    def alocar(self, tarefas: list[enxame.Tarefa], agentes: Sequence[enxame.Agente]
               ) -> enxame.Plano:
        return enxame.alocar(tarefas, agentes, desconto_sobreposicao=self.desconto,
                             restricao=self.restricao, bytes_da_tarefa=self.bytes_da_tarefa,
                             orcamento_bytes=self.orcamento)


def contexto(session: Session, campo: Field, agentes: Sequence[enxame.Agente],
             pedido: dict[str, Any], agora: datetime) -> Contexto:
    pr = Premissas()
    fator = pr.valor("fator_declive", pedido.get("fator_declive"), 0.5,
                     "o trabalho fica mais lento na proporção fator x declividade média / "
                     "limite do Rover (não medido: calibrar com a telemetria)")
    bpm = pr.valor("bytes_por_metro", pedido.get("bytes_por_metro"), BYTES_POR_METRO_SIMULADO,
                   "bytes pela Starlink por metro de trabalho do Rover", "simulado")
    reserva = pr.valor("reserva_dados", pedido.get("reserva_dados"), 0.10,
                       "fração do teto do dia que o plano não usa (comando, telemetria, eventos "
                       "e o imprevisto)")
    desconto = pr.valor("desconto_sobreposicao", pedido.get("desconto_sobreposicao"),
                        enxame.DESCONTO_SOBREPOSICAO,
                        "a segunda tarefa nas mesmas plantas vale menos (enxame)")
    vmin = pr.valor("valor_minimo_por_minuto", pedido.get("valor_minimo_por_minuto"), None,
                    "valor mínimo por minuto de trabalho do robô (do custo de operar, do "
                    "produtor); sem ele, o plano não corta tarefa de valor baixo e gasta a "
                    "bateria enquanto houver valor > 0")
    piso_dias = pr.valor("piso_vigilancia_dias", pedido.get("piso_vigilancia_dias"), 14,
                         "trecho nunca visto ou não visto há N dias ganha o menor valor "
                         "positivo do plano (não medido: ajuste à epidemiologia do talhão)")
    pr.anota("reserva_bateria", "o orçamento de tempo é a autonomia vezes a bateria acima da "
             "reserva (enxame); sem leitura de bateria, meia carga", enxame.RESERVA_BATERIA,
             "padrao")
    dispositivos = {a.device_id: session.get(Device, a.device_id) for a in agentes}
    obst, origem_obst = obstaculos(campo)
    pr.anota("obstaculos", f"obstáculos intransponíveis: {origem_obst}", len(obst),
             "medido" if obst or (campo.terrain or {}).get("resolution_ok") else "padrao")
    if campo.relief:
        pr.anota("relevo", f"relevo medido (fonte {campo.relief.get('fonte')}): declividade "
                 "máxima e média do talhão inteiro, não por trecho",
                 {"maxima_deg": campo.relief.get("declividade_maxima_deg"),
                  "media_deg": campo.relief.get("declividade_media_deg")}, "medido")
    else:
        pr.anota("relevo", "relevo não medido: planejado como se o talhão fosse plano — confira "
                 "a declividade no local", None, "padrao")
    orcamento, dados = orcamentos_de_dados(session, agentes, dispositivos, reserva=reserva,
                                           agora=agora)
    return Contexto(pr, Restricoes(campo, dispositivos, fator_declive=fator, obstaculos_=obst,
                                   valor_minimo_por_minuto=vmin),
                    bpm, orcamento, dados, obst, dispositivos, desconto, piso_dias)


def planejar(session: Session, *, tenant_id: str, campo: Field,
             tarefas: list[enxame.Tarefa], agentes: list[enxame.Agente],
             fora: list[dict[str, Any]], pedido: dict[str, Any], agora: datetime,
             avisos_do_gemeo: list[str]) -> tuple[dict[str, Any], list[dict]]:
    ctx = contexto(session, campo, agentes, pedido, agora)
    tarefas, subiram, piso = piso_de_vigilancia(tarefas, ctx.piso_dias)
    base = enxame.alocar(tarefas, agentes, desconto_sobreposicao=ctx.desconto)
    plano = ctx.alocar(tarefas, agentes)
    na_base = {t.id for at in base.atribuicoes for t in at.tarefas}
    no_plano = {t.id for at in plano.atribuicoes for t in at.tarefas}
    motivos = {t.id: m for t, m in plano.nao_atribuidas}
    sairam = [{"tarefa": i, "motivo": motivos.get(i, "realocada")}
              for i in sorted(na_base - no_plano)]
    corpo = plano.to_dict()
    resultado = {
        "versao": VERSAO, "field_id": campo.id,
        "valor_alocado": corpo["valor_alocado"], "valor_disponivel": corpo["valor_disponivel"],
        "rotas": rotas(plano, ctx.dispositivos, ctx.bytes_da_tarefa),
        "nao_atribuidas": corpo["nao_atribuidas"],
        "sem_restricoes": {"valor_alocado": round(base.valor_total, 4),
                           "tarefas_alocadas": len(na_base)},
        "sairam_pelas_restricoes": sairam,
        "piso_de_vigilancia": {"dias": ctx.piso_dias, "valor": piso, "tarefas": subiram},
        "dados_starlink": ctx.dados,
        "obstaculos": [{"tipo": o["tipo"], "caixa": list(o["caixa"])} for o in ctx.obstaculos],
        "fora_da_frota": list(fora),
        "proximas_missoes_propostas": corpo["proximas_missoes"],
        "tarefas": corpo["tarefas"],
        "avisos": sorted(set(avisos_do_gemeo)),
        "nota": "Proposta. Criar a missão (em RASCUNHO) é ação de uma pessoa pelo plano do "
                "enxame (que usa as mesmas restrições) ou pela tela de missões; autorizar é do "
                "Safety Engine.",
    }
    return resultado, ctx.premissas.lista()
