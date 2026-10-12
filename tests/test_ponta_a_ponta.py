"""Ponta a ponta da seção 44, automatizado, com o ``rover/`` de verdade (HAL simulada).

O roteiro está em ``simulator/ponta_a_ponta.py`` (o mesmo do ``python -m simulator
--rover-runtime``). Aqui ele roda contra o ``TestClient`` e cada um dos 31 critérios
da seção 58 tem de passar com a prova que o roteiro registra.
"""

from __future__ import annotations

import pytest

pytest.importorskip("valtexa_rover")

from simulator.ponta_a_ponta import executar
from tests.test_rover_integracao import ponte


def test_cliente_ao_relatorio_com_o_rover_real(client, session_factory, demo, tmp_path) -> None:
    res = executar(client, ponte(client), session_factory, tmp_path)
    for passo in sorted(res.passos, key=lambda p: int(p.nome.split()[0])):
        print(f"{'OK' if passo.ok else 'FALHA'} | {passo.nome} | {passo.prova}")
    nomes = [p.nome for p in res.passos]
    assert len(nomes) == 31, nomes
    assert sorted(int(n.split()[0]) for n in nomes) == list(range(1, 32))
    assert all(p.ok for p in res.passos)
    rel = res.dados["relatorio"]
    assert rel["comparison_with_previous"]["incidence_after"] < \
        rel["comparison_with_previous"]["incidence_before"]
