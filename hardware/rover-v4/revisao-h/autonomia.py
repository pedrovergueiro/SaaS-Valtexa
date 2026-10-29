"""VTX-RV4 Rev K · AUTONOMIA — a bateria do projeto atende 8 h por carga a 2 m/s?

Requisito definido em 28/10/2026: **8 h de trabalho por carga, percorrendo a 2 m/s**.

A conta soma o consumo da eletrônica (dos módulos `modular` e `sensores`) e o da tração, que
depende do terreno. Tudo que não vem de ficha técnica está marcado: a tração usa coeficiente de
rolamento e rendimento estimados, porque o motor-roda ainda não foi escolhido.

    python autonomia.py
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import modular as MD       # noqa: E402
import sensores as S       # noqa: E402
import suspensao as SU     # noqa: E402

G = 9.80665

HORAS_REQUISITO = 8.0
VELOCIDADE_MS = 2.0
CARGA_UTIL_KG = 25.0

C_ROLAMENTO = 0.05
"""ESTIMATIVA — pneu em terra batida de rua de café. Solo fofo ou molhado passa de 0,08."""

RENDIMENTO_TRACAO = 0.75
"""ESTIMATIVA — motor + driver, do eixo da bateria até a roda. Sem o motor escolhido (P-09)."""

RESERVA = 0.20
"""Critério da plataforma: o planejador de missão reserva 20 % (ENERGY_RESERVE_PERCENT)."""

W_LIDAR = 10.0
"""FAIXA — LiDAR da família Mid-360 (o modelo final depende do substituto do Mid-360)."""
W_REDE = 15.0
"""ESTIMATIVA — switch PoE e roteador, sem contar a energia PoE entregue às câmeras."""
CICLO_COMPRESSOR = 0.10
"""ESTIMATIVA — fração do tempo com o compressor da suspensão ligado (reposição de vazamento)."""
RENDIMENTO_DCDC = 0.90
"""ESTIMATIVA — conversor 48→12 V."""

TERRENOS = [
    ('Plano', 0.0, 'rua sem desnível'),
    ('Morro leve', 5.0, 'metade do tempo subindo 5°, metade descendo'),
    ('Morro de café', 10.0, 'metade do tempo subindo 10°, metade descendo'),
]
"""A descida não devolve energia nesta conta (regeneração não garantida pelo driver)."""


def eletronica_w() -> dict:
    e = MD.energia(0)
    sensores_12v = e['total_W']   # câmeras PoE com perdas + terminal satelital
    jetson = e['w_jetson_max']
    compressor = e['w_compressor'] * CICLO_COMPRESSOR
    no_12v = sensores_12v + jetson + compressor + W_LIDAR + W_REDE
    return dict(sensores=sensores_12v, jetson=jetson, compressor_medio=compressor, lidar=W_LIDAR, rede=W_REDE,
                no_12v=no_12v, da_bateria=no_12v / RENDIMENTO_DCDC)


def tracao_w(massa_kg: float, rampa_deg: float) -> float:
    """Potência média tirada da bateria pela tração, a VELOCIDADE_MS."""
    rolar = C_ROLAMENTO * massa_kg * G * VELOCIDADE_MS / RENDIMENTO_TRACAO
    if rampa_deg <= 0:
        return rolar
    th = math.radians(rampa_deg)
    subir = massa_kg * G * (math.sin(th) + C_ROLAMENTO * math.cos(th)) * VELOCIDADE_MS / RENDIMENTO_TRACAO
    descer = max(C_ROLAMENTO * math.cos(th) - math.sin(th), 0.0) * massa_kg * G * VELOCIDADE_MS / RENDIMENTO_TRACAO
    return (subir + descer) / 2


def autonomia() -> dict:
    massa = SU.massa()['massa'] + CARGA_UTIL_KG
    wh = S.BATERIA['wh']
    ele = eletronica_w()
    linhas = []
    for (nome, rampa, nota) in TERRENOS:
        tr = tracao_w(massa, rampa)
        total = ele['da_bateria'] + tr
        horas = wh * (1 - RESERVA) / total
        exigido = total * HORAS_REQUISITO / (1 - RESERVA)
        linhas.append(dict(terreno=nome, rampa=rampa, nota=nota, tracao_W=tr, total_W=total,
                           horas=horas, wh_para_8h=exigido, atende=horas >= HORAS_REQUISITO))
    return dict(massa_kg=massa, wh=wh, eletronica=ele, terrenos=linhas,
                km_por_carga=VELOCIDADE_MS * 3.6 * HORAS_REQUISITO)


def main() -> None:
    a = autonomia()
    e = a['eletronica']
    print('VTX-RV4 Rev K · AUTONOMIA')
    print(f'Requisito: {HORAS_REQUISITO:.0f} h por carga a {VELOCIDADE_MS:.1f} m/s '
          f'= {a["km_por_carga"]:.1f} km · massa com carga útil {a["massa_kg"]:.1f} kg')
    print(f'Bateria: {a["wh"]:.0f} Wh · usável com reserva de {RESERVA:.0%}: {a["wh"] * (1 - RESERVA):.0f} Wh')
    print(f'Eletrônica: {e["da_bateria"]:.0f} W da bateria (sensores e satélite {e["sensores"]:.0f}, '
          f'Jetson {e["jetson"]:.0f}, compressor médio {e["compressor_medio"]:.0f}, LiDAR {e["lidar"]:.0f}, '
          f'rede {e["rede"]:.0f})')
    for t in a['terrenos']:
        print(f'  {t["terreno"]:<15} tração {t["tracao_W"]:5.0f} W · total {t["total_W"]:5.0f} W · '
              f'{t["horas"]:4.1f} h · para 8 h: {t["wh_para_8h"]:5.0f} Wh · '
              f'{"ATENDE" if t["atende"] else "NAO ATENDE"}')
    print('Decisão de 28/10/2026 (caminho 1): manter a bateria de 16 células em 2 módulos e aceitar a autonomia '
          'menor no morro, ou reduzir a velocidade ali, ou trocar um módulo no turno.')


if __name__ == '__main__':
    main()
