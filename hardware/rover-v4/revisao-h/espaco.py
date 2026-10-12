"""Espaço interno do Rover V4, medido — e conferência de interferência entre peças.

Duas perguntas, as duas respondidas por medição no modelo e não por declaração:

1. **as peças se batem?** Mede, par a par, se duas peças se interpenetram. O que nasce
   interpenetrado por projeto — bucha dentro do tubo, colar atravessando a chapa, pino
   atravessando a parede — está na lista :data:`ENCAIXES`, com a razão de cada um. Qualquer
   par fora dessa lista é defeito.

2. **o que cabe lá dentro?** Varre o compartimento numa grade e mede a altura livre célula
   por célula, descontando TODAS as peças. O número que sai não é o produto de três cotas
   externas: é o volume que sobra depois do anel inferior, do anel superior, dos montantes,
   dos quatro colares de fole, das nervuras e das bandejas.

A segunda pergunta tem história no projeto. Imagens conceituais afirmavam 95,6 L de volume
interno útil, calculados como 850 × 450 × 250 mm. Nenhuma das três cotas existe: o
compartimento tem 1046 de comprimento, 536 de largura livre e altura que varia de 30 a
147 mm conforme a posição. Este módulo mede.

```
python espaco.py
```

Unidades: mm, L.
"""

from __future__ import annotations

import pathlib
import sys

AQUI = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent / 'chassi-gaiola'))
sys.path.insert(0, str(AQUI))

import modelo as M  # noqa: E402

# ========================================================= encaixes por projeto
ENCAIXES = {
    ('Q-02', 'Q-05'): 'bucha de compressão dentro do tubo da travessa',
    ('Q-03', 'Q-05'): 'bucha de compressão dentro do tubo da travessa',
    ('M-01', 'M-10'): 'haste do mastro dentro da luva',
    ('M-10', 'M-11'): 'bainha anti-galho sobre a haste',
    ('M-10', 'T-10'): 'adaptador da antena encaixado 40 mm no furo do topo da haste',
    ('M-11', 'T-10'): 'adaptador da antena dentro do furo da haste, sob o último trecho da bainha',
    ('C-01', 'W-12'): 'colar do fole atravessa a passagem Ø102 da chapa de fundo',
    ('W-01', 'W-04'): 'alojamento da bucha atravessa o tubo do braço',
    ('W-01', 'W-08'): 'prato do fole alojado no rasgo da parede superior do braço',
    ('W-01', 'W-07'): 'eixo do pivô atravessa o braço, dentro das buchas de W-04',
    ('W-01', 'W-09'): 'orelhas do prato alojadas DENTRO do tubo do braço, que é vazado',
    ('W-01', 'W-10'): 'pino do prato atravessa as paredes do braço',
    ('W-02', 'W-08'): 'prato e chapa do motor se cruzam na caixa, não no sólido',
    ('W-04', 'W-07'): 'eixo do pivô dentro do alojamento da bucha',
    ('W-05', 'W-07'): 'eixo do pivô atravessa as duas orelhas da torre',
    ('W-09', 'W-10'): 'pino dentro das orelhas do prato',
    ('N-06', 'N-07'): 'aba soldada na face inclinada da câmera de raiz',
}
"""Pares que nascem interpenetrados por projeto, e por quê.

A conferência é feita por CAIXA ENVOLVENTE, que é conservadora: dois sólidos podem ter
caixas sobrepostas sem se tocar. Por isso a lista existe — e por isso ela traz a razão, e
não só o par: uma linha aqui é uma afirmação de projeto, e tem de poder ser contestada.
"""


def interferencias() -> dict:
    """Pares que se interpenetram, separados entre encaixe previsto e defeito."""
    ps = [p for p in M.conjunto('ABO') if p.estilo != 'ref']
    caixas = [(p.item, p.bbox()) for p in ps]
    achados: dict = {}
    for i, (ia, ba) in enumerate(caixas):
        for ib, bb in caixas[i + 1:]:
            if ia == ib:
                continue
            fundo = min(min(ba[k][1], bb[k][1]) - max(ba[k][0], bb[k][0]) for k in range(3))
            if fundo <= 0.5:
                continue
            ch = (ia, ib) if (ia, ib) in ENCAIXES or (ib, ia) not in ENCAIXES else (ib, ia)
            achados[ch] = max(achados.get(ch, 0.0), fundo)
    previstos = {k: (v, ENCAIXES[k]) for k, v in achados.items() if k in ENCAIXES}
    defeitos = {k: v for k, v in achados.items() if k not in ENCAIXES}
    return dict(previstos=previstos, defeitos=defeitos,
                pecas=len(ps), pares=len(caixas) * (len(caixas) - 1) // 2)


# ============================================================ volume interno
PASSO = 8.0
"""mm — lado da célula da grade. 8 mm dá ~9 800 células no piso do compartimento."""

Z_PISO = M.Z_QUADRO
"""Face superior da chapa de fundo: é onde o compartimento começa."""

Z_TETO = M.Z_PROT
"""Teto do corpo: nada do corpo passa desta cota, por requisito da baseline."""

ALTURAS_DE_INTERESSE = (30.0, 60.0, 90.0, 120.0)
"""Alturas de componente contra as quais o volume é classificado.

Não são arbitrárias: 30 cobre placa e conversor, 60 cobre a maioria dos módulos, 90 era a
altura que o projeto vinha usando como "a" altura do compartimento, e 120 cobre a caixa de
bateria estimada.
"""


def _ocupacao():
    """Para cada peça, a caixa em XY e o intervalo em Z, só do que invade o compartimento."""
    out = []
    for p in M.conjunto('ABO'):
        if p.estilo == 'ref':
            continue
        (x0, x1), (y0, y1), (z0, z1) = p.bbox()
        if z1 <= Z_PISO or z0 >= Z_TETO:
            continue
        out.append((x0, x1, y0, y1, max(z0, Z_PISO), min(z1, Z_TETO), p.item))
    return out


def volume_interno() -> dict:
    """Varre a grade e mede a altura livre célula por célula."""
    oc = _ocupacao()
    area_celula = PASSO ** 2
    livre_total = 0.0
    por_altura = {h: 0.0 for h in ALTURAS_DE_INTERESSE}
    maior_vao = 0.0
    hist: dict = {}
    nx = int(M.L_Q / PASSO)
    ny = int(M.W_Q / PASSO)
    for i in range(nx):
        xc = -M.XQ + (i + 0.5) * PASSO
        candidatos = [o for o in oc if o[0] <= xc <= o[1]]
        for j in range(ny):
            yc = -M.YQ + (j + 0.5) * PASSO
            blocos = [(o[4], o[5]) for o in candidatos if o[2] <= yc <= o[3]]
            blocos.sort()
            z = Z_PISO
            vaos = []
            for (a, b) in blocos:
                if a > z:
                    vaos.append(a - z)
                z = max(z, b)
            if z < Z_TETO:
                vaos.append(Z_TETO - z)
            soma = sum(vaos)
            livre_total += soma * area_celula
            vao = max(vaos) if vaos else 0.0
            maior_vao = max(maior_vao, vao)
            for h in ALTURAS_DE_INTERESSE:
                if vao >= h:
                    por_altura[h] += soma * area_celula
            faixa = int(vao // 20) * 20
            hist[faixa] = hist.get(faixa, 0.0) + area_celula
    return dict(
        passo=PASSO, z_piso=Z_PISO, z_teto=Z_TETO,
        volume_livre_L=livre_total / 1e6,
        por_altura_L={h: v / 1e6 for h, v in por_altura.items()},
        maior_vao_mm=maior_vao,
        area_por_vao_cm2={k: v / 100 for k, v in sorted(hist.items())},
        volume_bruto_L=M.L_Q * M.W_Q * (Z_TETO - Z_PISO) / 1e6,
    )


# ================================================= zonas e o que vai em cada
# DECLARADO: o que o projeto quer pôr em cada zona. As dimensões dos componentes são
# ESTIMATIVA — as fichas técnicas continuam pendentes (P-05/P-13), e é por isso que a
# coluna "origem" existe.
ZONAS = [
    ('Bateria', (-245.0, 245.0), (-185.0, 185.0), 'Centro do compartimento, entre os batentes B-01'),
    ('Bandeja lateral esquerda', (-190.0, 190.0), (210.0, 264.0), 'Sobre a chapa, ao lado da bateria'),
    ('Bandeja lateral direita', (-190.0, 190.0), (-264.0, -210.0), 'Idem, espelhada'),
    ('Bandeja dianteira esquerda', (368.0, 490.0), (100.0, 152.0), 'Entre a janela de raiz e o colar do fole'),
    ('Bandeja traseira esquerda', (-490.0, -368.0), (100.0, 152.0), 'Idem, traseira'),
    ('Grupo pneumático', (-340.0, -120.0), (-250.0, -60.0), 'Compressor, reservatório, secador e manifold'),
]

COMPONENTES = [
    # (nome, zona, L, W, H, origem)
    ('Bateria LiFePO4 estimada', 'Bateria', 460.0, 350.0, 130.0, 'ESTIMATIVA'),
    ('Jetson Orin NX + carrier', 'Bandeja lateral esquerda', 180.0, 110.0, 45.0, 'ESTIMATIVA'),
    ('Driver dos motores (4 canais)', 'Bandeja lateral direita', 200.0, 120.0, 55.0, 'ESTIMATIVA'),
    ('BMS', 'Bandeja lateral direita', 140.0, 90.0, 35.0, 'ESTIMATIVA'),
    ('Conversor DC/DC 12 V', 'Bandeja dianteira esquerda', 110.0, 50.0, 40.0, 'ESTIMATIVA'),
    ('Roteador / modem', 'Bandeja traseira esquerda', 110.0, 50.0, 35.0, 'ESTIMATIVA'),
    ('Compressor 12 V', 'Grupo pneumático', 210.0, 110.0, 120.0, 'FAIXA'),
    ('Reservatório 2 L', 'Grupo pneumático', 300.0, 110.0, 110.0, 'FAIXA'),
]


def _vao_na_zona(zx, zy) -> dict:
    """Maior altura livre contínua dentro de uma zona, e a mínima encontrada nela."""
    oc = _ocupacao()
    vaos = []
    i = zx[0] + PASSO / 2
    while i < zx[1]:
        j = zy[0] + PASSO / 2
        while j < zy[1]:
            blocos = sorted((o[4], o[5]) for o in oc
                            if o[0] <= i <= o[1] and o[2] <= j <= o[3])
            z, v = Z_PISO, []
            for (a, b) in blocos:
                if a > z:
                    v.append(a - z)
                z = max(z, b)
            if z < Z_TETO:
                v.append(Z_TETO - z)
            vaos.append(max(v) if v else 0.0)
            j += PASSO
        i += PASSO
    return dict(min=min(vaos), max=max(vaos), medio=sum(vaos) / len(vaos),
                area_cm2=(zx[1] - zx[0]) * (zy[1] - zy[0]) / 100)


def mapa_de_alturas() -> tuple[list[list[float]], int, int]:
    """Altura livre contínua em cada célula da grade. É a base das duas perguntas."""
    oc = _ocupacao()
    nx, ny = int(M.L_Q / PASSO), int(M.W_Q / PASSO)
    h = [[0.0] * ny for _ in range(nx)]
    for i in range(nx):
        xc = -M.XQ + (i + 0.5) * PASSO
        cand = [o for o in oc if o[0] <= xc <= o[1]]
        for j in range(ny):
            yc = -M.YQ + (j + 0.5) * PASSO
            blocos = sorted((o[4], o[5]) for o in cand if o[2] <= yc <= o[3])
            z, v = Z_PISO, []
            for (a, b) in blocos:
                if a > z:
                    v.append(a - z)
                z = max(z, b)
            if z < Z_TETO:
                v.append(Z_TETO - z)
            h[i][j] = max(v) if v else 0.0
    return h, nx, ny


def _min_deslizante(seq: list[float], k: int) -> list[float]:
    """Mínimo em janela de k, em O(n) — o truque de deque dos dois ponteiros."""
    from collections import deque
    dq: deque = deque()
    out = []
    for i, v in enumerate(seq):
        while dq and seq[dq[-1]] >= v:
            dq.pop()
        dq.append(i)
        while dq[0] <= i - k:
            dq.popleft()
        if i >= k - 1:
            out.append(seq[dq[0]])
    return out


def cabe_em_pe(comp_mm: float, larg_mm: float, alt_mm: float,
               mapa=None) -> dict:
    """Existe, em algum lugar do compartimento, uma área contígua onde este volume cabe?

    É a pergunta certa, e é diferente de "a altura média da zona dá". Um componente de
    130 mm numa zona cuja altura varia de 87 a 148 pode caber ou não — depende de onde os
    87 estão. Isto varre a grade inteira e responde com a posição, nas duas orientações.
    """
    if mapa is None:
        mapa = mapa_de_alturas()
    h, nx, ny = mapa
    melhor = None
    for (c, l) in ((comp_mm, larg_mm), (larg_mm, comp_mm)):
        ki, kj = max(int(round(c / PASSO)), 1), max(int(round(l / PASSO)), 1)
        if ki > nx or kj > ny:
            continue
        # mínimo em janela: primeiro ao longo de Y, depois ao longo de X
        por_linha = [_min_deslizante(h[i], kj) for i in range(nx)]
        nj = len(por_linha[0])
        for j in range(nj):
            coluna = [por_linha[i][j] for i in range(nx)]
            jan = _min_deslizante(coluna, ki)
            for i, vmin in enumerate(jan):
                if vmin >= alt_mm:
                    x0 = -M.XQ + i * PASSO
                    y0 = -M.YQ + j * PASSO
                    cand = dict(cabe=True, x=(x0, x0 + c), y=(y0, y0 + l),
                                altura_livre=vmin, orientacao='LxW' if c == comp_mm else 'girado')
                    if melhor is None or abs(cand['x'][0] + cand['x'][1]) < abs(melhor['x'][0] + melhor['x'][1]):
                        melhor = cand
    return melhor or dict(cabe=False, x=None, y=None, altura_livre=None, orientacao=None)


def requisitos_de_componente() -> list[dict]:
    """A altura máxima que cada zona aceita — para virar requisito de compra.

    É o jeito útil de entregar a conferência de espaço: em vez de reprovar um componente
    estimado, dizer qual é o teto real da zona. Assim a cota entra na folha de compra e a
    ficha técnica que faltar já chega com o critério ao lado.

    O teto não é o Z 400 do requisito de proteção da baseline: as barras G-03 da gaiola
    descem a Z 377 e cruzam o compartimento inteiro em |X| 230 e 330, e os trilhos G-01
    fazem o mesmo nas laterais. Quem manda é a peça mais baixa que passa por cima, e isso
    só aparece medindo.
    """
    out = []
    for (nome, zx, zy, nota) in ZONAS:
        v = _vao_na_zona(zx, zy)
        out.append(dict(zona=nome, altura_maxima=v['min'], altura_no_melhor_ponto=v['max'],
                        area_cm2=v['area_cm2'], nota=nota))
    return out


def zonas() -> list[dict]:
    out = []
    for (nome, zx, zy, nota) in ZONAS:
        v = _vao_na_zona(zx, zy)
        comps = [c for c in COMPONENTES if c[1] == nome]
        pior = max((c[4] for c in comps), default=0.0)
        out.append(dict(zona=nome, x=zx, y=zy, nota=nota, **v,
                        componentes=comps, altura_exigida=pior,
                        cabe=pior <= v['min'] if comps else None))
    return out


def main() -> None:
    print('=' * 92)
    print('VTX-RV4 Rev H · ESPAÇO INTERNO E INTERFERÊNCIAS')
    print('=' * 92)

    it = interferencias()
    print(f'\n1. Interferência entre peças  ({it["pecas"]} peças, {it["pares"]} pares)')
    print('-' * 92)
    print(f'  encaixes previstos: {len(it["previstos"])}')
    for (a, b), (fundo, razao) in sorted(it['previstos'].items()):
        print(f'    {a} × {b:6} {fundo:6.1f} mm   {razao}')
    if it['defeitos']:
        print(f'  DEFEITOS: {len(it["defeitos"])}')
        for (a, b), fundo in sorted(it['defeitos'].items()):
            print(f'    {a} × {b:6} {fundo:6.1f} mm   NAO PREVISTO')
    else:
        print('  defeitos: nenhum')

    v = volume_interno()
    print(f'\n2. Volume interno, medido na grade de {v["passo"]:.0f} mm')
    print('-' * 92)
    print(f'  caixa bruta do compartimento (1046 × 596 × {v["z_teto"] - v["z_piso"]:.0f})'
          f'                 {v["volume_bruto_L"]:7.2f} L')
    print(f'  volume LIVRE, descontada toda peça                             '
          f'{v["volume_livre_L"]:7.2f} L')
    print(f'  maior altura livre contínua em qualquer ponto                  '
          f'{v["maior_vao_mm"]:7.0f} mm')
    print('\n  volume aproveitável por altura de componente:')
    for h, vol in sorted(v['por_altura_L'].items()):
        print(f'    componente de até {h:3.0f} mm de altura                           {vol:7.2f} L')
    print('\n  área de piso por faixa de altura livre:')
    for faixa, a in v['area_por_vao_cm2'].items():
        print(f'    {faixa:3.0f} a {faixa + 20:3.0f} mm   {a:8.0f} cm²')

    print('\n3. Zonas e o que o projeto quer pôr nelas')
    print('-' * 92)
    for z in zonas():
        print(f'\n  {z["zona"]}   X {z["x"][0]:.0f}…{z["x"][1]:.0f} · Y {z["y"][0]:.0f}…{z["y"][1]:.0f}'
              f'  ({z["area_cm2"]:.0f} cm²)')
        print(f'    {z["nota"]}')
        print(f'    altura livre: mínima {z["min"]:.0f} · média {z["medio"]:.0f} · máxima {z["max"]:.0f} mm')
        for (nome, _, cl, cw, ch, origem) in z['componentes']:
            marca = 'CABE  ' if ch <= z['min'] else ('NAO CABE' if ch > z['max'] else 'SO EM PARTE DA ZONA')
            print(f'    {marca:20} {nome:34} {cl:.0f}×{cw:.0f}×{ch:.0f}  [{origem}]')

    print('\n4. Cada componente cabe em algum lugar contíguo? (varredura da grade inteira)')
    print('-' * 92)
    mp = mapa_de_alturas()
    for (nome, zona, cl, cw, ch, origem) in COMPONENTES:
        r = cabe_em_pe(cl, cw, ch, mp)
        if r['cabe']:
            print(f'  CABE      {nome:34} {cl:.0f}×{cw:.0f}×{ch:.0f}  em '
                  f'X {r["x"][0]:.0f}…{r["x"][1]:.0f} · Y {r["y"][0]:.0f}…{r["y"][1]:.0f} '
                  f'(livre {r["altura_livre"]:.0f} mm, {r["orientacao"]})')
        else:
            print(f'  NAO CABE  {nome:34} {cl:.0f}×{cw:.0f}×{ch:.0f}  '
                  f'nenhuma área contígua no compartimento  [{origem}]')

    print('\n5. Teto de altura de cada zona — para a folha de compra')
    print('-' * 92)
    print('  O teto NAO é o Z 400 do requisito de proteção: as barras G-03 da gaiola')
    print('  descem a Z 377 e atravessam o compartimento em |X| 230 e 330.')
    for r in requisitos_de_componente():
        print(f'    {r["zona"]:30} altura máxima {r["altura_maxima"]:5.0f} mm   '
              f'({r["area_cm2"]:.0f} cm²)')

    print('\n6. O que isto responde, e o que continua aberto')
    print('-' * 92)
    print('  RESPONDE: o volume interno real, a altura livre ponto a ponto, e se os')
    print('  componentes estimados cabem nas zonas onde o projeto os quer.')
    print('  CONTINUA ABERTO: as dimensões dos componentes. Todas as linhas da seção 3')
    print('  são ESTIMATIVA ou FAIXA — nenhuma é ficha técnica. Enquanto for assim, as')
    print('  bandejas E-01/E-02 e os adaptadores T-03 não são cotas de fabricação, são')
    print('  provisões. É a pendência P-05/P-13, e nenhuma conta deste módulo a fecha.')


if __name__ == '__main__':
    import sys as _sys
    if hasattr(_sys.stdout, 'reconfigure'):          # o console do Windows é cp1252
        _sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    main()
