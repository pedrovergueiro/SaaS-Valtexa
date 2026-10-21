"""Mede a alocação do enxame contra o que se faria sem ela, com o mesmo tempo de bateria.

    python scripts/mede_alocacao.py --sementes 0 1 2 3 4

Talhão sintético de 40 ruas x 10 trechos de 20 m (3,5 m entre ruas), com o valor dos
trechos concentrado em focos (a doença anda em reboleira: poucos trechos valem muito);
Rovers V3 (1 m/s) saindo de pontos diferentes, cada um com um orçamento de tempo. Políticas:

* **enxame** — :func:`valtexa.services.enxame.alocar` (guloso por valor por segundo, com o
  deslocamento);
* **varredura** — cada Rover pega as ruas dele em ordem (o talhão dividido em faixas), até
  acabar o tempo: o que se faz hoje;
* **mais valioso primeiro** — a lista por valor, ao Rover livre mais perto, sem pesar o
  deslocamento.

Mede o valor coberto (fração do total) e os metros andados sem trabalho. Só mede.
"""

from __future__ import annotations

import argparse
import math
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from valtexa.services import enxame

ORIGEM = (-45.86, -21.90)
M_POR_GRAU_LAT = 111_320.0


def ponto(x_m: float, y_m: float) -> tuple[float, float]:
    lon = ORIGEM[0] + x_m / (M_POR_GRAU_LAT * math.cos(math.radians(ORIGEM[1])))
    return lon, ORIGEM[1] + y_m / M_POR_GRAU_LAT


def talhao(semente: int, ruas: int = 40, trechos: int = 10, focos: int = 4):
    rng = random.Random(semente)
    centros = [(rng.uniform(0, trechos * 20), rng.uniform(0, ruas * 3.5)) for _ in range(focos)]
    tarefas = []
    for r in range(ruas):
        for k in range(trechos):
            x, y = k * 20 + 10, r * 3.5
            valor = sum(math.exp(-math.hypot(x - cx, y - cy) / 15) for cx, cy in centros)
            valor = valor * rng.uniform(0.5, 1.5) + 0.01
            tarefas.append(enxame.Tarefa(
                id=f"G{r + 1}-{k}", tipo="inspecao", valor=valor, centro=ponto(x, y),
                poligono=None, comprimento_m=20.0, ruas=(f"G{r + 1}",), x_inicio_m=k * 20.0,
                x_fim_m=k * 20.0 + 19.3))
    return tarefas


def _agentes(n: int, orcamento_s: float, ruas: int) -> list[enxame.Agente]:
    return [enxame.Agente(f"R{i + 1}", f"R{i + 1}", "rover", 1.0, 3.0, orcamento_s,
                          ponto(0.0, (i + 0.5) * ruas * 3.5 / n)) for i in range(n)]


def _simula(ordem_por_agente: dict[str, list[enxame.Tarefa]], agentes) -> tuple[float, float]:
    """Executa cada fila na ordem, até o orçamento: valor coberto e metros sem trabalho."""
    valor, vazio = 0.0, 0.0
    for a in agentes:
        tempo, pos = 0.0, a.posicao
        for t in ordem_por_agente.get(a.device_id, []):
            d = enxame.distancia_m(pos, t.centro)
            c = d / a.velocidade_ms + enxame.tempo_de_trabalho_s(t, a)
            if tempo + c > a.orcamento_s:
                break
            tempo += c
            vazio += d
            valor += t.valor
            pos = t.centro
    return valor, vazio


def varredura(tarefas, agentes, ruas: int):
    faixa = math.ceil(ruas / len(agentes))
    fila = {a.device_id: [] for a in agentes}
    for t in sorted(tarefas, key=lambda t: (int(t.ruas[0][1:]), t.x_inicio_m)):
        rua = int(t.ruas[0][1:]) - 1
        a = agentes[min(rua // faixa, len(agentes) - 1)]
        fila[a.device_id].append(t)
    # Vaivém: a rua par vai, a ímpar volta.
    for a in agentes:
        por_rua: dict[str, list] = {}
        for t in fila[a.device_id]:
            por_rua.setdefault(t.ruas[0], []).append(t)
        fila[a.device_id] = [t for i, (_, ts) in enumerate(sorted(
            por_rua.items(), key=lambda kv: int(kv[0][1:])))
            for t in (ts if i % 2 == 0 else ts[::-1])]
    return fila


def mais_valioso(tarefas, agentes):
    fila = {a.device_id: [] for a in agentes}
    fim = {a.device_id: a.posicao for a in agentes}
    for t in sorted(tarefas, key=lambda t: -t.valor):
        a = min(agentes, key=lambda a: enxame.distancia_m(fim[a.device_id], t.centro))
        fila[a.device_id].append(t)
        fim[a.device_id] = t.centro
    return fila


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--sementes", type=int, nargs="+", default=[0, 1, 2, 3, 4])
    ap.add_argument("--rovers", type=int, nargs="+", default=[1, 2, 4])
    ap.add_argument("--horas", type=float, default=1.0)
    args = ap.parse_args()
    ruas = 40
    print(f"talhão {ruas} ruas x 10 trechos de 20 m; {args.horas:g} h de bateria útil por Rover")
    for n in args.rovers:
        fracoes: dict[str, list[float]] = {"enxame": [], "varredura": [], "mais_valioso": []}
        vazios: dict[str, list[float]] = {k: [] for k in fracoes}
        for s in args.sementes:
            tarefas = talhao(s, ruas)
            total = sum(t.valor for t in tarefas)
            agentes = _agentes(n, args.horas * 3600, ruas)
            plano = enxame.alocar(tarefas, agentes)
            filas = {"enxame": {at.agente.device_id: at.tarefas for at in plano.atribuicoes},
                     "varredura": varredura(tarefas, agentes, ruas),
                     "mais_valioso": mais_valioso(tarefas, agentes)}
            for nome, fila in filas.items():
                v, d = _simula(fila, agentes)
                fracoes[nome].append(v / total)
                vazios[nome].append(d)
        linha = "  ".join(
            f"{k} {100 * sum(v) / len(v):5.1f}% (vazio {sum(vazios[k]) / len(v):5.0f} m)"
            for k, v in fracoes.items())
        print(f"{n} Rover(s): valor coberto  {linha}")


if __name__ == "__main__":
    main()
