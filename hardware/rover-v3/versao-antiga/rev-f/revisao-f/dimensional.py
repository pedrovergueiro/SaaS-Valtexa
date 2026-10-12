"""Levantamento dimensional completo do Rover V3 — peça por peça.

Extrai do modelo paramétrico tudo o que define cada peça fabricada: dimensões,
espessura, furos com coordenadas, posição de montagem, material, massa, processo,
folha de origem e estado de validação. Sai em CSV, para a BOM mestra, e em texto,
para conferência.

**Nada aqui é digitado.** Toda dimensão vem de `chassi-gaiola/modelo.py`, que é o
mesmo arquivo que gera as 27 folhas e os 26 DXF. Um número digitado neste módulo
divergiria do desenho na primeira alteração de cota, e a divergência passaria sem
ninguém ver — que é exatamente o modo de falha que esta revisão encontrou na Rev E.

## Sistema de coordenadas

O da baseline, ISO 8855, preservado sem transformação: origem no solo, no centro do
polígono das quatro rodas; **X** para a frente, **Y** para a esquerda, **Z** para cima.
Unidades em mm e kg.

Não há conversão a documentar porque não há duas convenções no projeto — o modelo, as
folhas e os DXF usam a mesma.

## Classificação de confiança

| | Significado |
|---|---|
| **A** | dimensão confirmada em documento (baseline ou datasheet) |
| **B** | calculada a partir de geometria, com dados suficientes |
| **C** | proposta nesta revisão, aguardando validação |
| **D** | depende de ficha técnica que o projeto não tem |
| **E** | depende de decisão de projeto ainda não tomada |
| **F** | depende de ensaio ou aprovação |
"""

from __future__ import annotations

import csv
import math
import pathlib
import sys

AQUI = pathlib.Path(__file__).resolve().parent
RAIZ = AQUI.parent
sys.path.insert(0, str(RAIZ / 'chassi-gaiola'))
sys.path.insert(0, str(RAIZ / 'pacote-rev-f'))

import modelo as M  # noqa: E402
from folhas import lista_corte  # noqa: E402
from processos import FOLHA, PROC  # noqa: E402

SAIDA = AQUI / 'dimensional'

# ------------------------------------------------- origem → nível de confiança
# `ITENS[...]['origem']` do modelo diz de onde veio a peça; aqui vira o nível que a
# Fase 30 do pedido de dimensionamento usa.
CONFIANCA_POR_ORIGEM = {
    'BASE': 'A',   # veio da baseline Rev E
    'NOVO': 'B',   # geometria desta linha de projeto, calculada
}

# Pendências por peça: o que impede chamá-la de totalmente dimensionada.
PENDENCIAS = {
    'S-01': ('E', 'Material em aberto (Al × aço, sugestão 2.1). Substituída se a '
                  'suspensão pneumática for adiante.'),
    'S-02': ('D', 'Planicidade admitida pelo MPW86 não publicada (P-04). Material em '
                  'aberto (sugestão 2.4). Fadiga a verificar se a suspensão for ao ar.'),
    'S-03': ('E', 'Substituída se a suspensão pneumática for adiante.'),
    'Q-01': ('E', 'Material em aberto: Al 6061-T6 30×30×2 ou aço 1020 25×25×1,5.'),
    'Q-02': ('E', 'Material em aberto, idem Q-01.'),
    'Q-03': ('E', 'Material em aberto, idem Q-01.'),
    'Q-04': ('E', 'Material em aberto, idem Q-01.'),
    'M-20': ('D', 'Interface da câmera depende do desenho dimensional da OAK-D Pro W '
                  'PoE (P-06). Furação de montagem não confirmada.'),
    'N-09': ('D', 'Geometria depende do envelope real da OAK-D (P-06).'),
    'N-01': ('D', 'Furação depende do desenho da antena GNSS.'),
    'N-02': ('D', 'Furação real do MTi-630 não confirmada (pendência 18 do caderno).'),
    'G-06': ('D', 'Centro óptico do Mid-360 a confirmar (pendência 11 do caderno).'),
    'B-01': ('D', 'Caixa da bateria tem envelope estimado (460×350×130); o real depende '
                  'do arranjo das 16 células EVE e dos componentes.'),
}


def _dim_peca(p) -> dict:
    """Comprimento, largura e espessura de uma peça, da maior para a menor."""
    a = max(q[0] for q in p.perfil) - min(q[0] for q in p.perfil)
    b = max(q[1] for q in p.perfil) - min(q[1] for q in p.perfil)
    d = sorted((a, b, p.comprimento()), reverse=True)
    return dict(L=d[0], W=d[1], E=d[2])


def _furos(p) -> list[dict]:
    """Furos redondos com centro no plano do perfil e diâmetro."""
    return [dict(a=round(c[0], 2), b=round(c[1], 2), d=round(c[2], 2)) for c in p.circulos]


def pecas() -> list[dict]:
    """Todas as peças fabricadas, com dimensão, posição, massa e estado."""
    out = []
    for parte in ('A', 'B'):
        for item, d in lista_corte(parte).items():
            p = d['pecas'][0]
            it = M.ITENS[item]
            proc, ops, acab, obs = PROC.get(item, ('—', [], '—', ''))
            dm = _dim_peca(p)
            cx, cy, cz = p.centroide()
            bb = p.bbox()
            comps = sorted(d['comps'].items())
            nivel, pend = PENDENCIAS.get(
                item, (CONFIANCA_POR_ORIGEM.get(it['origem'], 'B'), ''))
            out.append(dict(
                codigo=item, nome=it['nome'], subconjunto=item[0],
                grupo_nome=M.GRUPOS.get(item[0], '—'),
                qtd=d['qtd'], descricao=it['desc'], material=p.mat,
                L=round(dm['L'], 1), W=round(dm['W'], 1), E=round(dm['E'], 2),
                x=round(cx, 1), y=round(cy, 1), z=round(cz, 1),
                bbox_x=f'{bb[0][0]:.0f}…{bb[0][1]:.0f}',
                bbox_y=f'{bb[1][0]:.0f}…{bb[1][1]:.0f}',
                bbox_z=f'{bb[2][0]:.0f}…{bb[2][1]:.0f}',
                eixo=p.eixo, n_furos=len(p.circulos), furos=_furos(p),
                cortes='; '.join(f'{M._n(c)}×{q}' for c, q in comps) if comps else '—',
                massa_un=round(d['unit'], 4), massa_tot=round(d['massa'], 3),
                processo=proc, operacoes='; '.join(ops), acabamento=acab,
                folha=FOLHA.get(item, '—'), origem=it['origem'],
                confianca=nivel, pendencia=pend, obs=obs, parte=parte,
            ))
    return out


# ================================================= pontos notáveis do veículo
def referenciais() -> list[tuple[str, str, str, str]]:
    """Coordenadas dos pontos de referência pedidos na Fase 2.

    Todos derivados do modelo. Onde o projeto não define o ponto, o campo diz isso em
    vez de trazer um número.
    """
    c = M.comparacao_baseline()
    r = [
        ('Origem (ISO 8855)', '0', '0', '0 — solo, centro do polígono das 4 rodas'),
        ('Centro geométrico do chassi', '0', '0', f'{(M.Z_QUADRO + M.Z_DECK) / 2:.0f}'),
        ('Eixo das rodas dianteiras', f'+{M.XS:.0f}', f'±{M.BITOLA / 2:.0f}',
         f'{M.Z_EIXO:.0f}'),
        ('Eixo das rodas traseiras', f'−{M.XS:.0f}', f'±{M.BITOLA / 2:.0f}',
         f'{M.Z_EIXO:.0f}'),
        ('Face de montagem do motor', f'±{M.XS:.0f}', f'±{M.Y_FACE:.0f}',
         f'{M.Z_EIXO:.0f} (datum B)'),
        ('Furo Ø88 da face', f'±{M.XS:.0f}', f'±{M.Y_FACE:.0f}', f'{M.Z_EIXO:.0f}'),
        ('Chapa de fundo (face inferior)', '0', '0', f'{M.Z_QUADRO - M.E_CHAPA:.0f}'),
        ('Anel inferior do quadro', '0', '0', f'{M.ANEL_INF[0]:.0f}…{M.ANEL_INF[1]:.0f}'),
        ('Anel superior do quadro', '0', '0', f'{M.ANEL_SUP[0]:.0f}…{M.ANEL_SUP[1]:.0f}'),
        ('Deck (topo do quadro)', '0', '0', f'{M.Z_DECK:.0f}'),
        ('Topo da proteção do corpo', '0', '0', f'{M.Z_PROT:.0f}'),
        ('Topo das tampas', '0', '0', f'{M.Z_TAMPA:.1f}'),
        ('Faixa central (ponto mais alto do corpo)', '0', '0', f'{M.Z_FAIXA:.1f}'),
        ('Anel da gaiola', '0', f'±{M.YG_C:.0f}', f'{M.Z_G1:.0f}…{M.Z_G2:.0f}'),
        ('Centro de gravidade (calculado)', '≈0', '≈0', f"{c['zcg_novo']:.1f}"),
        ('Topo do mastro', '0', '—', f'{M.Z_TOTAL:.0f}'),
    ]
    return r


def envelope_consolidado() -> list[dict]:
    """Fase 3: dimensão citada no pedido × o que o modelo calcula."""
    env = M.envelope()
    c = M.comparacao_baseline()
    linhas = [
        ('Comprimento externo (com carenagens)', 1050.0, M.L_EXT, 'modelo · L_EXT'),
        ('Largura externa (com carenagens)', 600.0, M.W_EXT, 'modelo · W_EXT'),
        ('Comprimento do quadro', 1046.0, M.L_Q, 'modelo · L_Q = L_EXT − 2×2'),
        ('Largura do quadro', 596.0, M.W_Q, 'modelo · W_Q'),
        ('Entre-eixos', 700.0, M.ENTRE_EIXOS, 'modelo · ENTRE_EIXOS'),
        ('Bitola', 470.0, M.BITOLA, 'modelo · BITOLA'),
        ('Diâmetro da roda', 200.0, M.D_RODA, 'FONTE · datasheet MPW86'),
        ('Centro da roda (Z)', 100.0, M.Z_EIXO, 'modelo · D_RODA/2'),
        ('Deck inferior (Z)', 250.0, M.Z_QUADRO, 'modelo · Z_QUADRO'),
        ('Deck superior (Z)', 340.0, M.Z_DECK, 'modelo · Z_DECK'),
        ('Topo do corpo (Z)', 400.0, M.Z_PROT, 'modelo · Z_PROT'),
        ('Altura total (topo do mastro)', None, M.Z_TOTAL, 'modelo · Z_TOTAL'),
        ('Vão livre', 150.0, M.VAO_LIVRE, 'modelo · VAO_LIVRE'),
    ]
    out = []
    for nome, citado, calc, fonte in linhas:
        if citado is None:
            sit = 'sem valor citado'
        elif abs(calc - citado) < 0.6:
            sit = 'confere'
        else:
            sit = f'DIVERGE ({calc - citado:+.1f} mm)'
        out.append(dict(dimensao=nome, citado=citado, calculado=calc,
                        fonte=fonte, situacao=sit))

    # Envelope real das peças fornecidas, que é o que o modelo mede.
    out.append(dict(
        dimensao='Envelope medido das peças (X)', citado=None,
        calculado=round(env[0][1] - env[0][0], 1),
        fonte='modelo · envelope() sobre todas as peças',
        situacao='calculado'))
    out.append(dict(
        dimensao='Envelope medido das peças (Y)', citado=None,
        calculado=round(env[1][1] - env[1][0], 1),
        fonte='modelo · envelope()', situacao='calculado'))
    out.append(dict(
        dimensao='Envelope medido das peças (Z)', citado=None,
        calculado=round(env[2][1] - env[2][0], 1),
        fonte='modelo · envelope()', situacao='calculado'))
    out.append(dict(
        dimensao='Massa nominal recalculada', citado=97.8,
        calculado=round(c['m_nom_novo'], 2),
        fonte='modelo · comparacao_baseline()',
        situacao=f"DIVERGE ({c['m_nom_novo'] - 97.8:+.2f} kg) — pendência P-02"))
    return out


# ================================================================ plano de corte
BARRA_COMERCIAL_MM = 6000.0
"""Barra de 6 m — o que `processos.MATERIA_PRIMA` declara para os dois perfis."""

PERDA_SERRA_MM = 3.0
"""Espessura de corte da serra. CRITÉRIO DE FABRICAÇÃO, a confirmar com o fornecedor."""


def plano_de_corte() -> dict:
    """Fase 4: aproveitamento de barra comercial por perfil, com perda de serra.

    Algoritmo first-fit decreasing: ordena as peças da maior para a menor e põe cada
    uma na primeira barra onde couber. Não é o ótimo — o ótimo é NP-difícil e não vale
    para 6 tipos de corte —, mas é o que o serralheiro faz na prática, e é limite
    superior do número de barras.
    """
    por_perfil: dict[str, list[float]] = {}
    for parte in ('A', 'B'):
        for item, d in lista_corte(parte).items():
            desc = M.ITENS[item]['desc']
            if not desc.startswith(('Tubo', 'Barra', 'Cantoneira')):
                continue
            for comp, qtd in d['comps'].items():
                por_perfil.setdefault(desc, []).extend([comp] * qtd)

    resultado = {}
    for perfil, pecas_mm in por_perfil.items():
        pecas_mm = sorted(pecas_mm, reverse=True)
        barras: list[float] = []     # espaço livre em cada barra
        for c in pecas_mm:
            need = c + PERDA_SERRA_MM
            for i, livre in enumerate(barras):
                if livre >= need:
                    barras[i] -= need
                    break
            else:
                barras.append(BARRA_COMERCIAL_MM - need)
        usado = sum(pecas_mm)
        total = len(barras) * BARRA_COMERCIAL_MM
        resultado[perfil] = dict(
            n_pecas=len(pecas_mm), metros_uteis=usado / 1000.0,
            barras=len(barras), metros_comprados=total / 1000.0,
            aproveitamento=usado / total if total else 0.0,
            sobra_m=(total - usado) / 1000.0,
            maior=max(pecas_mm), menor=min(pecas_mm))
    return resultado


# ====================================================== componentes comprados
# O que o rover leva e NÃO é fabricado. Dimensões físicas: o projeto tem muito poucas.
# Cada campo ausente vira pendência de ficha técnica (nível D), e não um número.
COMPRADOS = [
    # (código, nome, qtd, grupo, massa kg, L, W, H mm, posição, origem da massa)
    ('X-MOT', 'Motor-roda (MPW86 ou ZLTECH — a decidir)', 4, 'TRAÇÃO', 4.5,
     None, None, 86.5, f'±{M.XS:.0f}, ±{M.BITOLA / 2:.0f}, {M.Z_EIXO:.0f}',
     'FONTE massa e Ø do MPW86 (datasheet 011121); L e W não aplicáveis a motor-roda. '
     'ZLTECH: 9 campos de interface não publicados (P-09)'),
    ('X-RODA', 'Roda Ø200 (integrada ao motor-roda)', 4, 'TRAÇÃO', None,
     None, 52.1, 200.0, 'idem motor',
     'FONTE largura e Ø (datasheet). Massa inclusa no motor; raio efetivo sob carga '
     'NÃO publicado — afeta odometria'),
    ('X-DRV', 'Driver BLDC Roboteq SBLG2360TS', 4, 'TRAÇÃO', None, None, None, None,
     'bandeja E-01', 'PENDENTE ficha técnica: dimensões, massa, dissipação'),
    ('X-BAT', 'Bateria 16S LiFePO4 (16× EVE 105 Ah)', 1, 'ENERGIA', 36.5,
     460.0, 350.0, 130.0, f'sobre C-01, retida por B-01',
     'massa: BASELINE tab. 5.1. Caixa 460×350×130 é ESTIMATIVA — o arranjo real das '
     '16 células, barramentos e BMS não está documentado (P-18)'),
    ('X-BMS', 'BMS Daly Smart 16S 100 A com CAN', 1, 'ENERGIA', None,
     None, None, None, 'bandeja', 'PENDENTE ficha técnica'),
    ('X-DCDC', 'Conversor DC/DC 48→12 V 30 A', 1, 'ENERGIA', None, None, None, None,
     'bandeja', 'PENDENTE ficha técnica. Potência 360 W: FONTE (BOM)'),
    ('X-CONT', 'Contator DC TE Kilovac LEV200', 1, 'ENERGIA', None, None, None, None,
     'bandeja', 'PENDENTE ficha técnica'),
    ('X-CAM', 'Câmera OAK-D Pro W PoE', 8, 'SENSORES', None, None, None, None,
     '6 nos mastros (3 níveis × 2 lados), 1 frontal, 1 inferior',
     'PENDENTE desenho dimensional (P-06) — bloqueia M-20 e N-09. '
     'Potência: TETO de 12,95 W pela classe 3 de 802.3af, não medição'),
    ('X-LIDAR', 'LiDAR Livox Mid-360', 1, 'SENSORES', None, None, None, None,
     'suporte G-06, sobre a gaiola',
     'PENDENTE dimensões, massa e centro óptico (pendência 11 do caderno)'),
    ('X-GNSS', 'GNSS RTK ZED-F9P + antena', 1, 'SENSORES', None, None, None, None,
     'antena no suporte N-01, na tampa', 'PENDENTE ficha técnica'),
    ('X-IMU', 'IMU Xsens MTi-630 (CAN)', 1, 'SENSORES', None, None, None, None,
     'berço N-02, próximo ao CG',
     'PENDENTE furação real e offset ao CG (pendência 18 do caderno)'),
    ('X-RADIO', 'Par de rádios RFD900x', 1, 'SENSORES', None, None, None, None,
     'bandeja + base', 'PENDENTE ficha técnica'),
    ('X-ESTOP', 'E-STOP sem fio + relé Pilz PNOZ s4', 1, 'SENSORES', None,
     None, None, None, 'botoeira no reforço E-10, tampa traseira',
     'Botão Ø22 IP65: FONTE (caderno). Receptor e relé: PENDENTE'),
    ('X-CPU', 'Jetson Orin NX 16 GB + SSD NVMe 1 TB', 1, 'COMPUTAÇÃO', None,
     None, None, None, 'bandeja E-01',
     'PENDENTE dimensões e perfil de potência adotado (10 a 40 W muda o orçamento '
     'energético e a dissipação dentro de carenagem fechada)'),
]
"""Componentes comprados, com o que o projeto realmente sabe.

``None`` em massa ou dimensão é **pendência de ficha técnica**, não zero. O rover não
pode ser montado sem esses números — eles definem o envelope das bandejas, a furação
dos suportes e a massa real —, e inventá-los produziria uma montagem que não fecha no
primeiro parafuso.
"""


def comprados() -> list[dict]:
    out = []
    for (cod, nome, qtd, grupo, massa, L, W, H, pos, origem) in COMPRADOS:
        faltam = [r for r, v in (('massa', massa), ('L', L), ('W', W), ('H', H))
                  if v is None]
        out.append(dict(
            codigo=cod, nome=nome, qtd=qtd, grupo=grupo,
            massa_un=massa, massa_tot=(massa * qtd if massa is not None else None),
            L=L, W=W, H=H, posicao=pos, origem=origem,
            confianca='D' if faltam else 'A',
            faltam=', '.join(faltam) or '—'))
    return out


# ===================================================================== saídas
COLUNAS = [
    ('codigo', 'Código'), ('nome', 'Nome'), ('grupo_nome', 'Função / subconjunto'),
    ('subconjunto', 'Grupo'), ('qtd', 'Qtd total'), ('descricao', 'Perfil / formato'),
    ('L', 'Comprimento mm'), ('W', 'Largura mm'), ('E', 'Espessura mm'),
    ('x', 'Pos X mm'), ('y', 'Pos Y mm'), ('z', 'Pos Z mm'),
    ('bbox_x', 'Envelope X'), ('bbox_y', 'Envelope Y'), ('bbox_z', 'Envelope Z'),
    ('eixo', 'Orientação (eixo)'), ('n_furos', 'Furos'), ('cortes', 'Cortes mm × qtd'),
    ('material', 'Material'), ('massa_un', 'Massa un kg'), ('massa_tot', 'Massa tot kg'),
    ('processo', 'Processo'), ('operacoes', 'Operações'), ('acabamento', 'Acabamento'),
    ('folha', 'Folha'), ('origem', 'Origem da dimensão'), ('confianca', 'Confiança'),
    ('pendencia', 'Pendência'), ('obs', 'Observações'),
]


def exporta_csv() -> dict[str, pathlib.Path]:
    SAIDA.mkdir(exist_ok=True)
    gerados = {}

    # 1 · BOM mestra
    p = SAIDA / 'VTX-RV3-BOM-Mestra-Dimensional-RevF.csv'
    with p.open('w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f, delimiter=';')
        w.writerow([rot for _, rot in COLUNAS])
        for linha in pecas():
            w.writerow([linha[k] for k, _ in COLUNAS])
    gerados['BOM mestra'] = p

    # 2 · tabela de furos, um por linha
    p = SAIDA / 'VTX-RV3-Tabela-de-Furos-RevF.csv'
    with p.open('w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f, delimiter=';')
        w.writerow(['Código', 'Peça', 'Furo nº', 'a mm', 'b mm', 'Ø mm',
                    'Plano do perfil', 'Folha'])
        for linha in pecas():
            plano = {'x': 'YZ', 'y': 'XZ', 'z': 'XY'}.get(linha['eixo'], '—')
            for i, fu in enumerate(linha['furos'], 1):
                w.writerow([linha['codigo'], linha['nome'], i, fu['a'], fu['b'], fu['d'],
                            plano, linha['folha']])
    gerados['Tabela de furos'] = p

    # 3 · coordenadas dos pontos notáveis
    p = SAIDA / 'VTX-RV3-Referenciais-RevF.csv'
    with p.open('w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f, delimiter=';')
        w.writerow(['Ponto', 'X mm', 'Y mm', 'Z mm'])
        w.writerows(referenciais())
    gerados['Referenciais'] = p

    # 4 · envelope consolidado
    p = SAIDA / 'VTX-RV3-Envelope-Consolidado-RevF.csv'
    with p.open('w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f, delimiter=';')
        w.writerow(['Dimensão', 'Valor citado', 'Valor calculado', 'Fonte', 'Situação'])
        for d in envelope_consolidado():
            w.writerow([d['dimensao'], d['citado'] if d['citado'] is not None else '',
                        d['calculado'], d['fonte'], d['situacao']])
    gerados['Envelope consolidado'] = p

    # 5 · fixadores
    p = SAIDA / 'VTX-RV3-Fixadores-RevF.csv'
    with p.open('w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f, delimiter=';')
        w.writerow(['Código', 'Descrição', 'Material', 'Qtd', 'Aplicação'])
        for linha in M.fixadores():
            w.writerow(list(linha))
    gerados['Fixadores'] = p

    # 6 · plano de corte
    p = SAIDA / 'VTX-RV3-Plano-de-Corte-RevF.csv'
    with p.open('w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f, delimiter=';')
        w.writerow(['Perfil', 'Peças', 'Metros úteis', 'Barras de 6 m',
                    'Metros comprados', 'Aproveitamento', 'Sobra m',
                    'Maior corte mm', 'Menor corte mm'])
        for perfil, d in sorted(plano_de_corte().items()):
            w.writerow([perfil, d['n_pecas'], f"{d['metros_uteis']:.2f}", d['barras'],
                        f"{d['metros_comprados']:.1f}", f"{d['aproveitamento']:.1%}",
                        f"{d['sobra_m']:.2f}", f"{d['maior']:.0f}", f"{d['menor']:.0f}"])
    gerados['Plano de corte'] = p

    # 7 · componentes comprados
    p = SAIDA / 'VTX-RV3-Componentes-Comprados-RevF.csv'
    with p.open('w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f, delimiter=';')
        w.writerow(['Código', 'Componente', 'Qtd', 'Grupo', 'Massa un kg',
                    'Massa tot kg', 'L mm', 'W mm', 'H mm', 'Posição',
                    'Confiança', 'Dados que faltam', 'Origem'])
        for c in comprados():
            w.writerow([c['codigo'], c['nome'], c['qtd'], c['grupo'],
                        c['massa_un'] if c['massa_un'] is not None else '',
                        c['massa_tot'] if c['massa_tot'] is not None else '',
                        c['L'] or '', c['W'] or '', c['H'] or '', c['posicao'],
                        c['confianca'], c['faltam'], c['origem']])
    gerados['Componentes comprados'] = p

    return gerados


def resumo_confianca() -> dict[str, int]:
    r: dict[str, int] = {}
    for linha in pecas():
        r[linha['confianca']] = r.get(linha['confianca'], 0) + 1
    return dict(sorted(r.items()))


if __name__ == '__main__':
    ps = pecas()
    print('VTX-RV3 Rev F · levantamento dimensional')
    print()
    print(f'  peças fabricadas catalogadas: {len(ps)} códigos, '
          f'{sum(p["qtd"] for p in ps)} peças')
    print(f'  furos cotados: {sum(p["n_furos"] * p["qtd"] for p in ps)}')
    print(f'  massa das peças fabricadas: {sum(p["massa_tot"] for p in ps):.3f} kg')
    print(f'  fixadores: {sum(x[3] for x in M.fixadores())} itens')
    print()
    print('  confiança das dimensões:')
    rot = {'A': 'confirmada em documento', 'B': 'calculada da geometria',
           'C': 'proposta nesta revisão', 'D': 'depende de ficha técnica',
           'E': 'depende de decisão de projeto', 'F': 'depende de ensaio'}
    for n, q in resumo_confianca().items():
        print(f'      {n} · {rot[n]:32} {q:3} códigos')
    print()
    print('  envelope — citado × calculado:')
    for d in envelope_consolidado():
        if d['situacao'] not in ('confere',):
            print(f"      {d['dimensao']:42} {d['situacao']}")
    print()
    print('  plano de corte:')
    for perfil, d in sorted(plano_de_corte().items()):
        print(f"      {perfil:28} {d['n_pecas']:3} peças · {d['metros_uteis']:6.2f} m úteis · "
              f"{d['barras']} barra(s) · {d['aproveitamento']:5.1%}")
    print()
    cs = comprados()
    com_massa = [c for c in cs if c['massa_un'] is not None]
    print(f'  componentes comprados: {len(cs)} códigos, {sum(c["qtd"] for c in cs)} unidades')
    print(f'      com massa conhecida: {len(com_massa)} de {len(cs)}'
          f' ({sum(c["massa_tot"] for c in com_massa):.1f} kg)')
    print(f'      pendentes de ficha técnica: {sum(1 for c in cs if c["confianca"] == "D")}')
    for c in cs:
        if c['confianca'] == 'D':
            print(f"      {c['codigo']:8} {c['nome'][:44]:44} falta: {c['faltam']}")
    print()
    print('  arquivos gerados:')
    for nome, p in exporta_csv().items():
        print(f'      {nome:22} {p.name}  ({p.stat().st_size / 1024:.1f} KB)')
