"""Roteiro de usinagem, peça por peça — o que a oficina precisa fazer e com que tolerância.

Separa o que é CORTE (laser, serra: sai pronto do DXF) do que é USINAGEM (torno, fresa,
alargador: exige operação, tolerância e referência). São coisas diferentes na cotação e na
bancada, e o projeto vinha misturando as duas numa coluna só de "processo".

De onde vem cada coisa:

* a **geometria** — diâmetro, posição, espessura, material — é extraída do `modelo.py`;
* as **tolerâncias, ajustes, acabamentos e referências** são DECLARADAS aqui, na tabela
  :data:`OPERACOES`. Tolerância é decisão de projeto, não propriedade da geometria, e não
  há como deduzi-la de um diâmetro nominal.

A conferência que o módulo faz: toda peça que tem operação declarada existe no modelo, e
toda peça do grupo W que o modelo tem aparece aqui. Se alguém acrescentar uma peça e
esquecer o roteiro, o módulo acusa.

```
python usinagem.py
python usinagem.py --item W-02
```
"""

from __future__ import annotations

import pathlib
import sys
from collections import OrderedDict

AQUI = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent / 'chassi-gaiola'))
sys.path.insert(0, str(AQUI))

import modelo as M  # noqa: E402

# =========================================================== roteiro declarado
# (item, [(n, operação, ferramenta, cota/tolerância, acabamento)])
OPERACOES = OrderedDict([
    ('W-01', [
        (1, 'Serrar o tubo no comprimento', 'serra de fita',
         f'{M.X_BRACO[1] - M.X_BRACO[0]:.0f} ± 0,5', '—'),
        (2, 'Furar as duas paredes laterais para o alojamento da bucha',
         'fresa de topo Ø16 + interpolação', f'2× Ø{M.D_BUCHA:.0f} H11, coaxiais em 0,2', 'Ra 12,5'),
        (3, 'Fresar o rasgo do prato na parede superior', 'fresa de topo Ø10',
         '24 × 34, centro em X 425 ± 0,3', 'Ra 6,3'),
        (4, 'Furar as duas paredes laterais para o pino do prato',
         'broca Ø11,8 + alargador', f'2× Ø{M.D_PINO_PRATO:.0f} H7, coaxiais em 0,05', 'Ra 1,6'),
        (5, 'SOLDAR o alojamento W-04, a chapa W-02 e a tampa W-03', 'TIG/MIG',
         'filete a4 contínuo; ver folha 33', '—'),
        (6, 'DEPOIS da solda: alargar o alojamento da bucha',
         'alargador de haste longa', f'Ø{M.D_ALOJ:.0f} H7 passante nas duas paredes', 'Ra 1,6'),
        (7, 'Conferir o paralelismo do eixo do pivô com a face da chapa',
         'desempeno + relógio', '0,2 em 100', '—'),
    ]),
    ('W-02', [
        (1, 'Cortar o contorno', 'laser (DXF 1:1)', 'contorno livre ± 0,3', '—'),
        (2, 'Furar o alojamento do motor', 'torno vertical ou fresa + interpolação',
         f'Ø{M.D_BORE:.0f} H8, concentricidade 0,1 ao datum C', 'Ra 3,2'),
        (3, 'Furar os 7 passantes do flange do motor', 'broca Ø4,5',
         f'7× Ø4,5 eq. esp. em PCD {M.MPW_PCD:.0f}, posição Ø0,2 (B, C)', 'Ra 12,5'),
        (4, 'SOLDAR o braço W-01 e a tampa W-03', 'TIG/MIG',
         'filete a4 em cima e embaixo da sobreposição', '—'),
        (5, 'DEPOIS da solda: faceamento da face de montagem (datum B)',
         'fresa de facear Ø63', f'planeza 0,1 · perpendicular 0,3 a A · e ≥ {M.E_PLACA - 0.5:.1f}',
         'Ra 3,2'),
        (6, 'Conferir a planicidade na face usinada', 'desempeno + relógio',
         'planeza 0,1 na área de contato Ø105,7', '—'),
    ]),
    ('W-03', [
        (1, 'Cortar o contorno', 'laser (DXF 1:1)', f'{M.B_BRACO:.0f} × {M.H_BRACO:.0f} ± 0,3', '—'),
        (2, 'SOLDAR na ponta do braço e na chapa W-02', 'TIG/MIG',
         'filete a4 em todo o contorno — é o que fecha o tubo', '—'),
    ]),
    ('W-04', [
        (1, 'Tornear o diâmetro externo e facear as duas pontas', 'torno',
         f'Ø{M.D_BUCHA:.0f} h11 × {M.L_BUCHA:.0f} ± 0,2', 'Ra 6,3'),
        (2, 'Furar e pré-alargar o alojamento', 'torno',
         f'Ø{M.D_ALOJ - 0.3:.1f} (sobremetal para alargar depois de soldar)', 'Ra 3,2'),
        (3, 'Chanfrar as duas bocas', 'torno', '1 × 45°', '—'),
    ]),
    ('W-05', [
        (1, 'Cortar o contorno', 'laser (DXF 1:1)', 'contorno ± 0,3', '—'),
        (2, 'Alargar o furo do eixo', 'broca Ø19,8 + alargador',
         f'Ø{M.D_PIVO:.0f} H7', 'Ra 1,6'),
        (3, 'SOLDAR no berço W-06, as duas orelhas no mesmo dispositivo', 'TIG/MIG',
         f'filete a4; distância entre faces internas {M.Y_ORELHA[1] - M.Y_ORELHA[0] - M.E_ORELHA:.0f} ± 0,2',
         '—'),
        (4, 'DEPOIS da solda: alargar os dois furos no mesmo passe',
         'alargador de haste longa', f'2× Ø{M.D_PIVO:.0f} H7 coaxiais em 0,05', 'Ra 1,6'),
    ]),
    ('W-06', [
        (1, 'Cortar o contorno e os 2 furos de fixação', 'laser (DXF 1:1)',
         '2× Ø8,5, posição ± 0,2', '—'),
        (2, 'SOLDAR as duas orelhas W-05', 'TIG/MIG', 'ver W-05 op. 3', '—'),
        (3, 'Facear a face de assento, DEPOIS da solda', 'fresa de facear',
         'planeza 0,15 na face que encosta na chapa de fundo', 'Ra 6,3'),
        (4, 'Zincar ou pintar o conjunto soldado', 'tratamento',
         'aço contra alumínio: isolar — arruela de nylon no parafuso', '—'),
    ]),
    ('W-07', [
        (1, 'Tornear o diâmetro do eixo', 'torno CNC',
         f'Ø{M.D_PIVO:.0f} h7 × 66 ± 0,2', 'Ra 0,8'),
        (2, 'Abrir as duas ranhuras de anel elástico', 'torno, bedame de 1,1',
         'DIN 471 para Ø20, distância entre ranhuras 58 ± 0,2', 'Ra 3,2'),
        (3, 'Chanfrar as duas pontas', 'torno', '1,5 × 20°', '—'),
    ]),
    ('W-08', [
        (1, 'Tornear o disco', 'torno', f'Ø{M.D_PRATO:.0f} h11 × {M.E_PRATO:.0f} ± 0,2', 'Ra 3,2'),
        (2, 'Facear a face de assento do fole', 'torno',
         'planeza 0,05 · perpendicular 0,1 ao eixo', 'Ra 1,6'),
        (3, 'Rosquear o furo central', 'torno + macho', 'M12 × 1,75, profundidade 8 passante',
         '—'),
        (4, 'SOLDAR as duas orelhas W-09, em dispositivo', 'TIG/MIG',
         f'filete a4; 2× Ø{M.D_PINO_PRATO:.0f} H7 coaxiais em 0,05 depois de soldar', 'Ra 1,6'),
    ]),
    ('W-09', [
        (1, 'Cortar o contorno e o furo do pino', 'laser (DXF 1:1)', '28 × 26 ± 0,3', '—'),
        (2, 'Alargar o furo do pino', 'alargador',
         f'Ø{M.D_PINO_PRATO:.0f} H7', 'Ra 1,6'),
        (3, 'SOLDAR no disco W-08, em dispositivo', 'TIG/MIG',
         'filete a4; eixo do pino paralelo à face do disco em 0,1', '—'),
    ]),
    ('W-10', [
        (1, 'Tornear o pino', 'torno CNC', f'Ø{M.D_PINO_PRATO:.0f} h7 × 42 ± 0,2', 'Ra 0,8'),
        (2, 'Abrir as duas ranhuras de anel elástico', 'torno, bedame de 1,0',
         'DIN 471 para Ø12, distância 36 ± 0,2', 'Ra 3,2'),
    ]),
    ('W-11', [
        (1, 'Cortar o contorno, os 4 furos de fixação e os 2 do fole',
         'laser (DXF 1:1)', '4× Ø8,5 ± 0,2 · Ø14 central ± 0,2 · Ø12 da porta de ar', '—'),
        (2, 'Facear as duas faces', 'fresa de facear',
         f'e = {M.E_BERCO_FOLE:.0f} ± 0,1 · paralelismo 0,1', 'Ra 3,2'),
        (3, 'Rosquear o furo central do fole', 'macho', 'M12 × 1,75 passante', '—'),
        (4, 'Rebarbar e anodizar', 'tratamento', 'anodização dura 15 µm', '—'),
    ]),
    ('W-13', [
        (1, 'Cortar a flange e os 6 rebites', 'laser (DXF 1:1)',
         'perfil de círculo cortado em |X| 470; 6× Ø4,9', '—'),
        (2, 'Facear as duas faces de junta', 'fresa',
         'planeza 0,1 nas duas faces que recebem junta NBR', 'Ra 3,2'),
        (3, 'SOLDAR no tubo W-12', 'TIG',
         'filete a3 estanque em todo o contorno — a junta tem de selar', '—'),
    ]),
    ('W-12', [
        (1, 'Tornear o tubo do colar', 'torno',
         f'Ø{M.D_COLAR:.0f} ext. × Ø{M.D_COLAR - 2 * M.E_COLAR:.0f} int. × '
         f'{M.Z_BERCO_FOLE[0] - (M.Z_QUADRO - M.E_CHAPA):.0f} ± 0,3', 'Ra 6,3'),
        (2, 'SOLDAR a flange W-13', 'TIG', 'ver W-13 op. 3', '—'),
        (3, 'Ensaio de estanqueidade do conjunto soldado', 'ar a 0,5 bar em água',
         'sem bolha em 60 s', '—'),
    ]),
    ('Q-05', [
        (1, 'Tornear a bucha de compressão', 'torno',
         f'Ø12 × {M.ANEL_INF[1] - M.ANEL_INF[0]:.0f} ± 0,1, furo Ø8,5', 'Ra 6,3'),
        (2, 'SOLDAR dentro do tubo ANTES de fechar o anel', 'TIG',
         'depois de fechar o anel não há acesso', '—'),
    ]),
    ('M-01', [
        (1, 'Serrar a luva no comprimento', 'serra de fita', '180 ± 0,5', '—'),
        (2, 'Alargar o furo da haste', 'alargador', 'Ø25 H8', 'Ra 3,2'),
        (3, 'Furar e rosquear os travamentos', 'fresa + macho', '2× M6 passante', '—'),
        (4, 'SOLDAR no quadro, sobre o reforço M-02', 'TIG',
         'perpendicular 0,5 em 180 ao plano do deck', '—'),
    ]),
    ('N-02', [
        (1, 'Cortar o contorno e os furos', 'laser (DXF 1:1)', 'contorno ± 0,3', '—'),
        (2, 'Facear a face de assento do IMU', 'fresa de facear',
         'planeza 0,05 · paralela ao plano do deck em 0,1', 'Ra 1,6'),
    ]),
])

AJUSTES = [
    ('Eixo do pivô W-07 na bucha autolubrificante', 'Ø20 h7 / bucha H7',
     'folga de 0,02 a 0,05 — o eixo gira'),
    ('Bucha autolubrificante no alojamento W-04', 'Ø23 H7 / bucha s6',
     'interferência leve: a bucha é prensada e não gira'),
    ('Eixo do pivô W-07 nas orelhas W-05', 'Ø20 H7',
     'ajuste deslizante: o eixo entra à mão e é travado por anel'),
    ('Pino W-09 nas orelhas do prato W-08', 'Ø12 h7 / H7',
     'folga mínima: o prato articula poucos graus'),
    ('Motor MPW86 no alojamento da chapa W-02', 'Ø88 H8 / motor Ø86,5 máx.',
     'folga de montagem; a centragem é pelo PCD, não pelo diâmetro'),
    ('Fole W-10 dentro do colar W-12', 'Ø88 máx. / Ø94 int.',
     '3 mm radiais: o fole dilata ao pressurizar'),
]

NOTAS = [
    'Toda cota sem tolerância indicada segue ISO 2768-mK; conjuntos soldados, ISO 13920-BF.',
    'As operações marcadas DEPOIS DA SOLDA são obrigatoriamente posteriores: a solda '
    'distorce, e usinar antes joga a tolerância fora.',
    'Os DXF em saida/dxf são 1:1 e já traçam contorno e furos. Eles NÃO carregam '
    'tolerância — a tolerância está nesta tabela e nas folhas 28 a 31.',
    'Aço contra alumínio em qualquer interface: isolar. É o item de corrosão galvânica de '
    'materiais.py, e nesta revisão ele aparece em W-06 e nos parafusos M8 da suspensão.',
    'Nenhuma peça deve ser usinada antes de a massa oficial ser fechada (P-02) e de o '
    'caso 9 do FEA rodar (P-22). Esta tabela é para COTAR.',
]


# ================================================================ conferência
def geometria(item: str) -> dict:
    """O que o modelo sabe da peça: espessura, material, furos reais."""
    ps = [p for p in M.conjunto('AB') if p.item == item]
    if not ps:
        return {}
    p = ps[0]
    furos = sorted({round(d, 1) for (_, _, d) in p.circulos})
    (x0, x1), (y0, y1), (z0, z1) = p.bbox()
    return dict(item=item, qtd=len(ps), mat=M.ITENS[item]['mat'],
                desc=M.ITENS[item]['desc'], espessura=p.comprimento(),
                eixo=p.eixo, curvo=p.curvo, furos=furos,
                caixa=((x0, x1), (y0, y1), (z0, z1)), massa=sum(q.massa() for q in ps))


def confere() -> dict:
    """Roteiro sem peça, e peça do grupo W sem roteiro."""
    no_modelo = {p.item for p in M.conjunto('AB') if p.estilo != 'ref'}
    sem_peca = [i for i in OPERACOES if i not in no_modelo]
    do_w = {i for i in no_modelo if i.startswith('W-')}
    sem_roteiro = sorted(do_w - set(OPERACOES))
    return dict(sem_peca=sem_peca, sem_roteiro=sem_roteiro)


def resumo() -> list[dict]:
    """Quantas operações de cada natureza, por peça — é o que a cotação precisa."""
    out = []
    for item, ops in OPERACOES.items():
        g = geometria(item)
        if not g:
            continue
        corte = sum(1 for o in ops if 'laser' in o[2] or 'serra' in o[2])
        solda = sum(1 for o in ops if 'SOLDAR' in o[1])
        usin = len(ops) - corte - solda
        out.append(dict(item=item, nome=M.ITENS[item]['nome'], qtd=g['qtd'], mat=g['mat'],
                        total=len(ops), corte=corte, usinagem=usin, solda=solda,
                        ops_por_conjunto=len(ops) * g['qtd']))
    return out


def main(item: str | None = None) -> None:
    c = confere()
    if item:
        it = item.upper()
        g = geometria(it)
        print(f'\n{it} · {M.ITENS[it]["nome"]}   {g.get("qtd", 0)} un · {g.get("mat", "?")}')
        print(f'  {g.get("desc", "")}')
        if g:
            print(f'  espessura/comprimento usinado: {g["espessura"]:.1f} mm · '
                  f'furos no modelo: {", ".join(f"Ø{d:g}" for d in g["furos"]) or "nenhum"}')
        print()
        for (n, op, fer, cota, acab) in OPERACOES.get(it, []):
            print(f'  {n}. {op}')
            print(f'     ferramenta: {fer}')
            print(f'     cota/tolerância: {cota}')
            print(f'     acabamento: {acab}')
        return

    print('=' * 104)
    print('VTX-RV3 Rev G · ROTEIRO DE USINAGEM')
    print('=' * 104)
    print(f'\n{"item":7} {"qtd":>3} {"material":16} {"ops":>4} {"corte":>6} {"usin":>5} '
          f'{"solda":>6} {"ops/conj":>9}  nome')
    for r in resumo():
        print(f'{r["item"]:7} {r["qtd"]:3d} {r["mat"]:16} {r["total"]:4d} {r["corte"]:6d} '
              f'{r["usinagem"]:5d} {r["solda"]:6d} {r["ops_por_conjunto"]:9d}  {r["nome"]}')

    print('\n\nROTEIRO DETALHADO')
    print('=' * 104)
    for it, ops in OPERACOES.items():
        g = geometria(it)
        if not g:
            continue
        print(f'\n{it} · {M.ITENS[it]["nome"]}  ({g["qtd"]} un, {g["mat"]}, '
              f'e/L {g["espessura"]:.1f} mm)')
        for (n, op, fer, cota, acab) in ops:
            marca = '  SOLDA ' if 'SOLDAR' in op else ('  corte ' if ('laser' in fer or 'serra' in fer)
                                                       else '  USINAR')
            print(f'{marca} {n}. {op}')
            print(f'          {fer}  |  {cota}  |  {acab}')

    print('\n\nAJUSTES E FOLGAS')
    print('=' * 104)
    for (o, aj, por) in AJUSTES:
        print(f'  {o:48} {aj:28} {por}')

    print('\n\nNOTAS GERAIS')
    print('=' * 104)
    for n in NOTAS:
        print(f'  · {n}')

    print('\n\nCONFERÊNCIA')
    print('=' * 104)
    print(f'  roteiro para peça que não existe no modelo: {c["sem_peca"] or "nenhuma"}')
    print(f'  peça do grupo W sem roteiro declarado:      {c["sem_roteiro"] or "nenhuma"}')


if __name__ == '__main__':
    arg = None
    if '--item' in sys.argv:
        arg = sys.argv[sys.argv.index('--item') + 1]
    main(arg)
