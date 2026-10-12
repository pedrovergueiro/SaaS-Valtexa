"""Extrai do modelo paramétrico a lista de itens fabricados, com dimensões e processo.

Fonte única: ../chassi-gaiola/modelo.py (geometria do caderno VTX-RV3-CG-G).
"""
import pathlib
import sys

AQUI = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent / 'chassi-gaiola'))

import modelo as M                      # noqa: E402
from folhas import lista_corte          # noqa: E402
from processos import (PROC, FOLHA, LASER, SERRA, BARRA, TORNO, FRESA, COMPRA,  # noqa: E402
                       PLAST, DOBRA)

SUB = {'Q': 'QUADRO', 'C': 'CHAPA', 'W': 'SUSPENS', 'G': 'GAIOLA', 'K': 'CAREN',
       'M': 'MASTRO', 'B': 'BATERIA', 'E': 'ELETR', 'N': 'SENSOR'}
MAT = {'6061': 'Al 6061-T6', '5052': 'Al 5052-H32', 'borracha': 'NBR 60 Shore A',
       'uhmw': 'UHMW-PE', 'pc': 'Policarbonato', 'aco': 'Aço A36 / 1020',
       'inox': 'Inox 304', 'pu': 'Poliuretano 90 Sh A'}
PARTE = {'A': 'Parte A — chassi e gaiola', 'B': 'Parte B — interfaces'}


def codigo(item):
    return f'VTX-RV3-{SUB[item[0]]}-{item}-REV-G'


# peças planas cujo plano é inclinado no espaço: o envelope do perfil não dá a espessura
PLANA = {'N-07': (140.0, 87.0, 3.0)}


def _planas(p):
    """Dimensões da peça plana (maior × menor) e espessura, em mm."""
    if p.item in PLANA:
        return PLANA[p.item]
    a = max(q[0] for q in p.perfil) - min(q[0] for q in p.perfil)
    b = max(q[1] for q in p.perfil) - min(q[1] for q in p.perfil)
    d = sorted((a, b, p.comprimento()))
    return d[2], d[1], d[0]


def itens():
    """Lista de dicionários, um por código de peça fabricada."""
    out = []
    for parte in ('A', 'B'):
        for item, d in lista_corte(parte).items():
            p = d['pecas'][0]
            it = M.ITENS[item]
            proc, ops, acab, obs = PROC[item]
            a, b, e = _planas(p)
            comps = sorted(d['comps'].items())
            if proc in (SERRA, BARRA):
                dim = ' · '.join(f'{M._n(c)} mm × {q}' for c, q in comps)
                esp = it['desc']
            else:
                dim = f'{M._n(a)} × {M._n(b)}'
                esp = f'{M._n(e)} mm'
            out.append(dict(
                parte=PARTE[parte], grupo=item[0], item=item, codigo=codigo(item),
                nome=it['nome'], desc=it['desc'], material=MAT.get(p.mat, p.mat),
                qtd=d['qtd'], massa=d['massa'], unit=d['unit'], processo=proc, ops=ops,
                acabamento=acab, obs=obs, dim=dim, esp=esp, origem=it['origem'],
                furos=len(p.circulos), comps=comps, folha=FOLHA.get(item, '-')))
    return out


def por_processo(proc):
    return [i for i in itens() if i['processo'] == proc]


def com_operacao(chave):
    return [i for i in itens() if any(chave.lower() in o.lower() for o in i['ops'])]


def resumo_material():
    """Massa total por material e por grupo, para a BOM e os cenários."""
    por_mat, por_grupo = {}, {}
    for i in itens():
        por_mat[i['material']] = por_mat.get(i['material'], 0.0) + i['massa']
        por_grupo[i['grupo']] = por_grupo.get(i['grupo'], 0.0) + i['massa']
    return por_mat, por_grupo


def tubos():
    """Comprimento total por perfil de tubo/barra, em metros."""
    tot = {}
    for i in itens():
        if i['processo'] not in (SERRA, BARRA):
            continue
        for c, q in i['comps']:
            tot[i['desc']] = tot.get(i['desc'], 0.0) + c * q / 1000.0
    return tot


def area_chapa():
    """Área bruta por espessura e material (retângulo envolvente × quantidade), em m²."""
    tot = {}
    for i in itens():
        if i['processo'] not in (LASER, FRESA):
            continue
        p = [x for x in lista_corte('A' if i['parte'].startswith('Parte A') else 'B')[i['item']]['pecas']][0]
        a, b, e = _planas(p)
        chave = (i['material'], M._n(e))
        tot[chave] = tot.get(chave, 0.0) + (a * b * i['qtd']) / 1e6
    return tot


# ---------------------------------------------------- métricas de cotação
def _perimetro(pts):
    import math as _m
    return sum(_m.dist(pts[i], pts[(i + 1) % len(pts)]) for i in range(len(pts)))


def metricas_corte():
    """Metros de corte a laser, número de furos e área superficial — como o fornecedor cota."""
    from processos import LASER, FRESA
    corte = furos = area = 0.0
    n_furos = 0
    for parte in ('A', 'B'):
        for item, d in lista_corte(parte).items():
            proc = PROC[item][0]
            if proc not in (LASER, FRESA):
                continue
            p = d['pecas'][0]
            q = d['qtd']
            corte += _perimetro(p.perfil) * q
            for anel in p.furos:
                furos += _perimetro(anel) * q
            n_furos += len(p.furos) * q
            a, b, e = _planas(p)
            area += (2 * abs(_area(p.perfil)) + _perimetro(p.perfil) * e) * q
    return dict(corte_m=(corte + furos) / 1000.0, contorno_m=corte / 1000.0, furos_m=furos / 1000.0,
                n_furos=n_furos, area_m2=area / 1e6)


def _area(pts):
    s = 0.0
    for i in range(len(pts)):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % len(pts)]
        s += x1 * y2 - x2 * y1
    return s / 2.0


def metricas_solda():
    """Comprimento estimado de cordão, por conjunto soldado (DERIVADO da topologia)."""
    q = 4 * 30.0                      # perímetro do tubo 30×30
    g = 4 * 20.0                      # perímetro do tubo 20×20
    juntas = [
        ('Quadro · montantes nos anéis', 16 * 2, q, 'a2'),
        ('Quadro · travessas nas longarinas', 8 * 2, q, 'a2'),
        ('Quadro · tampas de extremidade', 8, q, 'a2'),
        ('Quadro · base dos mastros', 2, 192.0 + 107.0, 'a3/a4'),
        ('Suportes · nervuras e placa (4 conjuntos)', 4 * 3, 190.0, 'a3'),
        ('Gaiola · montantes e trilhos (2 módulos)', 2 * 10, g, 'a2'),
        ('Gaiola · sapatas nos montantes', 12, 200.0, 'a3'),
    ]
    tot = sum(n * c for (_, n, c, _) in juntas) / 1000.0
    return juntas, tot
