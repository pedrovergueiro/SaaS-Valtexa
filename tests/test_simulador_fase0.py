"""FASE 0 automática com o ``rover/`` de verdade e a bancada SIMULADA de ensaios.

O roteiro está em ``simulator/fase0.py`` (o mesmo do ``python -m simulator --fase0``):
cada ensaio sai assinado pela plataforma, roda numa thread do Runtime, o laudo volta com
as amostras e o veredito é **recalculado no servidor**; o portão da FASE 0 abre aceitando
simulação e continua fechado para o portão real.
"""

from __future__ import annotations

import pytest

pytest.importorskip("valtexa_rover")

from simulator.fase0 import executar
from tests.test_rover_integracao import ponte


def test_fase0_inteira_com_veredito_do_servidor(client, session_factory, tmp_path) -> None:
    res = executar(client, ponte(client), session_factory, tmp_path)
    for passo in res.passos:
        print(f"{'OK' if passo.ok else 'FALHA'} | {passo.nome} | {passo.prova}")
    assert all(p.ok for p in res.passos)
    linhas = {x["rotulo"]: x for x in res.dados["linhas"]}
    assert len(linhas) == 9
    assert linhas["bateria e energia"]["status"] == "nao_avaliado"
    assert all(x["simulado"] and not x["divergente"] for x in linhas.values())
    # O GNSS foi medido contra o ponto conhecido, com perda e retomada: vale para o portão.
    gnss = linhas["GNSS RTK"]
    assert gnss["vale_portao"] and gnss["medidas"]["perdas"] == 1
    # A rede é a única medida real: a ida e volta até a API de verdade.
    assert linhas["rede até a plataforma"]["medidas"]["perda_pct"] == 0
    assert res.dados["portao_simulado"]["aprovado"] is True
    real = res.dados["portao_real"]
    assert real["aprovado"] is False
    assert {i["situacao"] for i in real["itens"]} == {"so_simulado"}
    md = res.dados["markdown"]
    assert "SIMULADO / não testado em hardware" in md and "calculado na plataforma" in md


def test_fase0_com_falha_injetada_reprova_no_servidor(client, session_factory,
                                                       tmp_path) -> None:
    res = executar(client, ponte(client), session_factory, tmp_path,
                   falhas={"camera:2": {"falha_em": [3]}, "termica": {
                       "aquece_c_por_min": 1, "throttle_c": 80, "temp_teto_c": 95}})
    linhas = {x["rotulo"]: x for x in res.dados["linhas"]}
    assert linhas["câmeras (8 juntas)"]["status"] == "reprovado"
    assert linhas["calor (2 h)"]["status"] == "reprovado"  # 45 °C + 1 °C/min passa de 80
    portao = res.dados["portao_simulado"]
    assert portao["aprovado"] is False
    assert set(portao["faltam"]) == {"calor", "cameras"}
