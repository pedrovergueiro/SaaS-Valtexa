"""Folhas 17 a 25 — Parte B (interfaces) e Parte C (fechamento) do caderno VTX-RV3-CG-E.

Mesmas regras de layout da Parte A (ver cabeçalho de folhas.py): área útil X 25→413, Y 7→290;
legenda em X ≥ 235, Y ≥ 238; blocos de texto à direita de X 235 terminam antes de Y 238.
"""
import math

import modelo as M
from modelo import (quadro, base_mastro, mastro, suportes_camera, retencao_bateria, bandejas, estop,
                    chapa_fundo, gaiola, carenagens, bateria_ref, conjunto, ITENS, GRUPOS, consolidado,
                    TABELA_51, YQ, XQ, Z_QUADRO, Z_DECK, Z_G2, Z_TAMPA, Y_MASTRO, Z_REF_M, D_ESTOP,
                    CAMERAS_Z, Z_TOTAL, X_ESTOP, MALHA_MONTAGEM, BATERIA, E_CHAPA,
                    suporte_gnss, gnss_ref, berco_imu, visao_raiz, suporte_led, carenagem_cameras,
                    interfaces_sensores, lidar_ref, rodas, X_GNSS, Z_GNSS, D_ANTENA, H_ANTENA,
                    X_IMU, Z_IMU, JANELA_RAIZ, Y_LED, Z_LED, D_LED, Z_BASE_LIDAR, X_LIDAR)
from desenho import (Vista, desenha, desenha_corte, desenha_iso, cota_h, cota_v, cota_vista_h,
                     cota_vista_v, chamada, balao, linha_centro, cruz_centro, rotulo, num,
                     simbolo_solda, T)
from folhas import (Folha, tag, tabela, kg, lista_corte, recorta_caixa, solo, iso_no_retangulo,
                    _plano)

Z_LUVA = M.Z_LUVA
D = 8.0


def _lado(pecas, sinal=1):
    """Só as peças do lado +Y (ou −Y): nas vistas do mastro as duas se sobrepõem."""
    return [p for p in pecas if p.centro()[1] * sinal > 0]


# ======================================================================== F17
def f17():
    F = Folha(17, escala='1:2', material='Al 6061-T6 · tubo Ø34×4,5 · chapa 6')
    corpo = [p for p in quadro() + gaiola() if p.estilo == 'solid']
    B = _lado(base_mastro())
    haste = [p.como('ref') for p in recorta_caixa(_lado(mastro()), z=(300, 560)) if p.item == 'M-10']

    # --- vista de +X: alturas cotadas a partir do deck
    vf = Vista('frontal', 2, -31, 300)
    desenha(F.s, vf, [p.como('ctx') for p in recorta_caixa(corpo, y=(150, 320), z=(300, 560))] + B + haste)
    linha_centro(F.s, *vf.P((0, Y_MASTRO, 300)), *vf.P((0, Y_MASTRO, 566)))
    z_travas = (Z_LUVA[0] + 54, Z_LUVA[0] + 134)
    for z in z_travas:
        linha_centro(F.s, *vf.P((0, Y_MASTRO - 26, z)), *vf.P((0, Y_MASTRO + 26, z)))
    cota_vista_v(F.s, vf, (0, YQ, Z_REF_M[0]), (0, YQ, Z_REF_M[1]), 136)
    for i, z in enumerate(z_travas):
        cota_vista_v(F.s, vf, (0, Y_MASTRO, Z_DECK), (0, Y_MASTRO, z), 144 + i * D)
    cota_vista_v(F.s, vf, (0, YQ, Z_DECK), (0, YQ, Z_LUVA[1]), 160)
    cota_vista_h(F.s, vf, (0, Y_MASTRO, Z_DECK), (0, YQ, Z_DECK), 152)
    chamada(F.s, *vf.P((0, Y_MASTRO + 12, 550)), 174, 26, 'M-10 haste (ref.)', lado=1)
    chamada(F.s, *vf.P((0, Y_MASTRO + 17, 480)), 174, 48, ['M-01 luva do mastro', 'Ø34×4,5 × 180'], lado=1)
    chamada(F.s, *vf.P((0, Y_MASTRO + 17, z_travas[0])), 174, 88, ['2× Ø6,6 passante em X', 'F-24 M6×12'],
            lado=1)
    chamada(F.s, *vf.P((0, 268, 343)), 174, 126, ['M-02 reforço', 'chapa 56 × 40 × 6'], lado=1)
    rotulo(F.s, 86, 168, 'VISTA DE +X', '1:2', 'mastro esquerdo · quadro e gaiola em traço fino')

    # --- vista superior e simbologia de solda
    vs = Vista('superior', 2, 270, 185)
    desenha(F.s, vs, _lado(base_mastro()) + haste)
    cruz_centro(F.s, *vs.P((0, Y_MASTRO, 0)), 12)
    for z in z_travas:
        linha_centro(F.s, *vs.P((-26, Y_MASTRO, 0)), *vs.P((26, Y_MASTRO, 0)))
    cota_vista_h(F.s, vs, (-28, Y_MASTRO, 0), (28, Y_MASTRO, 0), 64)
    cota_vista_v(F.s, vs, (0, 258, 0), (0, YQ, 0), 248)
    rotulo(F.s, 270, 76, 'VISTA SUPERIOR', '1:2', 'luva Ø34 · furo Ø25 H8')
    simbolo_solda(F.s, *vf.P((0, 260, Z_REF_M[1])), 150, 160, a='a3', cauda='reforço–longarina', comp=20)
    simbolo_solda(F.s, *vf.P((0, Y_MASTRO + 17, Z_REF_M[1] + 3)), 150, 176, a='a4', cauda='luva–reforço',
                  comp=20)

    F.bloco(26, 190, 198, f'''
<h3>Base do mastro — o que é e onde fica</h3>
<ol class="notas">
<li>Conjunto soldado ao anel superior do quadro, no vão entre os dois módulos da gaiola (X −30 → +30), um de
cada lado: <b>X 0 · Y ±{num(Y_MASTRO)}</b> {tag('NOVO')}.</li>
<li>A baseline usa ±300; com a bainha Ø29 o tubo passaria da face do quadro, por isso ±280.</li>
<li>A haste entra 180 mm na luva e trava com 2 parafusos passantes na direção X: o balanço livre cai de 1.442
para {num(Z_TOTAL - Z_LUVA[1])} mm (folha 18).</li>
<li>Furo Ø6 no centro do reforço: dreno e passagem do cabo para dentro do quadro.</li>
<li>M-01 e M-02 são <b>parte do quadro soldado</b> (grupo M, folha 14); a haste e o resto do mastro são
Parte B, cotados à parte.</li>
<li>A luva termina em Z 526 — 126 mm acima do topo da gaiola. É a única peça do conjunto soldado fora do
envelope de 400 mm; o transporte tem de considerar isso (ou a haste sai e a luva fica).</li>
</ol>''')
    F.bloco(300, 20, 108, f'''
<h3>Verificação da base — preliminar</h3>
<p>Momento na base com a hipótese da baseline (50 N no topo do mastro): <b>72 N·m</b>.</p>
<ul>
<li>Solda circular luva → reforço, a4 em Ø34: W ≈ 3,6 × 10³ mm³ → <b>σ ≈ 20 MPa</b> {tag('CALC')}</li>
<li>Solda reforço → longarina, a3 em 56 × 40: <b>σ ≈ 28 MPa</b> {tag('CALC')}</li>
<li>Torção da longarina até as travessas: <b>τ ≈ 12 MPa</b>, giro ≈ 0,6°, que soma ~16 mm de deslocamento no
topo do mastro</li>
</ul>
<p class="mini">Contas de ordem de grandeza, com a ZTA do 6061-T6 a 110 MPa {tag('HIPÓTESE')}. Entram no FEA
como caso de carga 6 (folha 25), junto com a vibração do mastro.</p>
<h3>Montagem</h3>
<ol class="notas">
<li>Soldar M-02 na longarina, em gabarito, com o furo central na posição.</li>
<li>Soldar M-01 no reforço, aprumada (0,3 mm em 180).</li>
<li>Furar as travas em X depois da solda, com a haste montada.</li>
</ol>''', h=212)
    return F


# ======================================================================== F18
def f18():
    F = Folha(18, escala='1:10', material='Al 6061-T6 · tubo Ø25×2 · bainha UHMW-PE')
    pecas = mastro() + suportes_camera()
    ctx = [p.como('ctx') for p in conjunto('A') if p.estilo == 'solid']
    vf = Vista('frontal', 10, 60, 204.2)
    desenha(F.s, vf, ctx + pecas)
    for s in (1, -1):
        linha_centro(F.s, *vf.P((0, s * Y_MASTRO, Z_DECK)), *vf.P((0, s * Y_MASTRO, Z_TOTAL + 60)))
    xa = vf.P((0, Y_MASTRO, 0))[0]
    for i, z in enumerate((Z_DECK, Z_LUVA[1], CAMERAS_Z[0], CAMERAS_Z[1], CAMERAS_Z[2], Z_TOTAL)):
        cota_v(F.s, vf.P((0, 0, 0))[1], vf.P((0, 0, z))[1], 96 + i * D, xa, xa, valor=z)
    cota_vista_h(F.s, vf, (0, -Y_MASTRO, Z_TOTAL), (0, Y_MASTRO, Z_TOTAL), 20)
    chamada(F.s, *vf.P((0, Y_MASTRO, Z_TOTAL + 20)), 76, 30, 'M-12 ponta', lado=1)
    rotulo(F.s, 60, 216, 'ELEVAÇÃO DOS MASTROS', '1:10', 'vista de +X · chassi em traço fino')

    d_trab = 550.0 - Y_MASTRO
    meia = d_trab * math.tan(math.radians(55))

    # --- esquema da cobertura: seção transversal da rua, 1:20
    x0, yg, k = 170.0, 284.0, 1 / 20

    def PZ(dy, z):
        return (x0 + dy * k, yg - z * k)

    solo(F.s, 152, 212, yg)
    F.s.rect(*PZ(-290, 400), *PZ(20, 250), 'ctx')
    F.s.ln(*PZ(0, 250), *PZ(0, Z_TOTAL), 'vis')
    F.s.aneis([[PZ(270, 150), PZ(700, 150), PZ(700, 2400), PZ(270, 2400)]], 'ref')
    F.s.tx(*PZ(720, 2000), 'copa do café', T, a='start', c='tx sec')
    for z in CAMERAS_Z:
        c = PZ(0, z)
        F.s.circ(c[0], c[1], 0.9, 'arr')
        for sinal in (1, -1):
            F.s.ln(c[0], c[1], *PZ(d_trab, z + sinal * meia), 'raio')
        F.s.tx(c[0] - 2.2, c[1] + 1.2, num(z), T, a='end', c='tx sec')
    for z, txt in ((CAMERAS_Z[0] - meia, num(CAMERAS_Z[0] - meia, 0)),
                   (CAMERAS_Z[2] + meia, num(CAMERAS_Z[2] + meia, 0))):
        a = PZ(d_trab, z)
        F.s.ln(a[0] - 1.6, a[1], a[0] + 1.6, a[1], 'dim')
        F.s.tx(a[0] + 2.4, a[1] + 1.2, txt, T, a='start', c='tx sec')
    cota_h(F.s, *[PZ(v, 0)[0] for v in (0, d_trab)], yg - 3.5, yg, yg, valor=d_trab)
    rotulo(F.s, 186, 150, 'COBERTURA DAS CÂMERAS', '1:20', 'seção transversal da rua · FOV vertical 110°')

    cob = [[f'{i + 1}º andar', num(z), f'{num(z - meia, 0)} → {num(z + meia, 0)}']
           for i, z in enumerate(CAMERAS_Z)]
    F.bloco(144, 24, 88, f'''
<h3>Haste, bainha e cabos</h3>
<ol class="notas">
<li><b>M-10</b>: tubo Ø25×2, {num(Z_TOTAL - Z_REF_M[1])} mm, apoiado no reforço e travado na luva.</li>
<li><b>M-11</b>: bainha UHMW-PE Ø29/Ø25 em 3 segmentos, interrompida nos suportes — a braçadeira aperta o
tubo, não o plástico.</li>
<li><b>M-12</b>: ponta cônica no topo, colada e pinada.</li>
<li>Cabos das câmeras <b>por dentro do tubo</b>: entrada Ø12 com passa-cabo 30 mm abaixo de cada suporte,
saída lateral Ø20 na luva e descida pela face interna da longarina até a bandeja (folha 21).</li>
<li>A altura das braçadeiras é ajustável no tubo; as cotas ao lado são as de projeto.</li>
</ol>''')
    F.bloco(238, 24, 170, f'''
<h3>Alturas das câmeras e cobertura</h3>
<p>Distância de trabalho até a copa: <b>{num(d_trab)} mm</b> (entrelinha 3.500, copa 2.400, eixo do mastro em
Y {num(Y_MASTRO)}) {tag('CALC')}.</p>
''' + tabela(['Andar', 'Z (mm)', 'Cobertura vertical (mm)'], cob, 'compacta', col=[26, 24, 50]) + f'''
<p>Com FOV vertical de 110°, a cobertura vai de {num(CAMERAS_Z[0] - meia, 0)} a {num(CAMERAS_Z[2] + meia, 0)} mm,
com cerca de 28 % de sobreposição entre andares; GSD ≈ 0,26 mm/px — 4× melhor que o requisito de 1 mm.</p>
<p class="mini">A baseline usa 343 / 891 / 1.440 a 240 mm de distância. Aqui os andares sobem porque o primeiro
ficaria dentro da gaiola (topo em 400). Altura final confirmada na integração {tag('A VALIDAR')}.</p>''')
    F.bloco(238, 132, 170, f'''
<h3>Efeito da luva na dinâmica</h3>
<p>Com a luva de 180 mm, o balanço livre cai de 1.442 para <b>{num(Z_TOTAL - Z_LUVA[1])} mm</b>:</p>
<ul>
<li>1ª frequência ≈ 8,6 × (1442 / {num(Z_TOTAL - Z_LUVA[1])})² ≈ <b>11,2 Hz</b> {tag('ESTIMATIVA')} — 2,2×
acima dos 5 Hz do solo (a baseline pede ≥ 1,5×);</li>
<li>tensão no engaste, com 20 N no topo, cai de 37,4 para ≈ <b>33 MPa</b>.</li>
</ul>
<p class="mini">Escala de viga em balanço, <b>sem a massa da bainha e das carenagens</b> — é a mesma pendência
que a baseline declara em aberto. Confirmar no FEA (caso 6, folha 25) e no ensaio 7 (folha 26), com câmeras,
bainha e carenagens montadas.</p>''', h=104)
    return F


# ======================================================================== F19
def f19():
    F = Folha(19, escala='1:1', material='Al 6061-T6 · chapa 6')
    sup = [p for p in suportes_camera() if p.centro()[1] > 0 and p.bbox()[2][0] > CAMERAS_Z[2] - 40][0]
    P, (x0, y0, x1, y1), _ = _plano(F, sup, 60, 40, 1.0, dx_cota=10.0)
    z = CAMERAS_Z[2]
    cota_h(F.s, P(-15, z)[0], P(15, z)[0], y0 - 10, y0, y0, valor=30)
    cota_h(F.s, P(-22, z)[0], P(22, z)[0], y0 - 18, y0, y0, valor=44)
    cota_v(F.s, P(0, z + 15)[1], P(0, z - 15)[1], x1 + 10, x1, x1, valor=30)
    cota_v(F.s, P(0, z + 22)[1], P(0, z - 22)[1], x1 + 18, x1, x1, valor=44)
    chamada(F.s, *P(22, z + 22), 172, 44, ['4× Ø7 — parafusos U', 'F-20 (Ø25) ou F-21 (Ø34)'], lado=1)
    chamada(F.s, *P(-15, z - 15), 40, 126, ['4× Ø4,5 — interface', 'da câmera (a validar)'], lado=1)
    rotulo(F.s, (x0 + x1) / 2, y1 + 26, 'M-20 SUPORTE DA CÂMERA', '1:1',
           '6 peças iguais · chapa 6 · corte a laser')

    vs = Vista('superior', 1, 300, 350)
    pecas = _lado([p for p in mastro() + suportes_camera() if p.bbox()[2][0] <= z <= p.bbox()[2][1]])
    desenha_corte(F.s, vs, pecas, 'z', z)
    c = vs.P((0, Y_MASTRO, 0))
    cruz_centro(F.s, *c, 16)
    for s in (1, -1):
        a = math.radians(18)
        F.s.ln(c[0], c[1], c[0] + s * 42 * math.sin(a), c[1] - 42 * math.cos(a), 'cl')
    F.s.tx(300, 22, '± 18° de ajuste angular', T, c='tx sec')
    chamada(F.s, *vs.P((0, Y_MASTRO + 12.5, 0)), 358, 82, 'parafuso U em volta do tubo', lado=1)
    rotulo(F.s, 300, 102, 'MONTAGEM NO MASTRO', '1:1', f'corte horizontal em Z {num(z)}')

    pi = recorta_caixa(_lado(mastro() + suportes_camera()), z=(z - 130, z + 130))
    cam = iso_no_retangulo(pi, 40, 210, 190, 284, 1.1, az=-55, el=22)
    desenha_iso(F.s, cam, pi)
    for cod, p, (dx, dy) in (('M-10', (0, Y_MASTRO, z + 110), (-13, -2)),
                             ('M-11', (0, Y_MASTRO + 14, z - 110), (-13, 4)),
                             ('M-20', (0, Y_MASTRO + 18, z + 20), (14, -6))):
        a = cam.P(p)
        balao(F.s, a[0] + dx, a[1] + dy, cod, alvo=a)
    rotulo(F.s, 206, 212, 'MONTAGEM — ISOMÉTRICA', 'sem escala', 'trecho do mastro no 3º andar', a='start')

    F.bloco(26, 150, 188, '''
<h3>Notas do suporte de câmera</h3>
<ol class="notas">
<li>Uma peça plana por câmera — <b>6 no total</b> (3 andares × 2 lados), cortada a laser pelo arquivo
<b>dxf/M-20</b>.</li>
<li>Fixação por 2 parafusos U de inox: F-20 no tubo Ø25 (andares 2 e 3) e F-21 no Ø34 (1º andar, na altura da
luva).</li>
<li>Ajuste em três graus de liberdade antes do aperto: altura no tubo, giro em torno do mastro e ±18° de
inclinação.</li>
<li>Quebrar cantos vivos ≥ 0,5 e arredondar os 4 cantos externos R5 — o suporte fica na faixa dos galhos.</li>
</ol>''')
    F.bloco(236, 132, 172, f'''
<h3>Interface da câmera — pendência</h3>
<p>A furação Ø4,5 em 30 × 30 é <b>provisória</b> {tag('A VALIDAR')}. Depende de:</p>
<ul>
<li>desenho dimensional da OAK-D Pro W PoE (furação, rosca e posição do conector);</li>
<li>carenagem anti-galho das câmeras, que a baseline lista como 8 peças de UHMW-PE e ainda não tem desenho;</li>
<li>orientação do conector — o cabo tem de sair para baixo, em direção à entrada do tubo.</li>
</ul>
<p>Com esses dados muda só o DXF do M-20: a placa, os parafusos U e esta folha permanecem.</p>
<p class="mini">A câmera frontal e a da zona de raiz não usam este suporte — ficam na carenagem K-02 e sob a
chapa de fundo (folha 10).</p>''', h=100)
    return F


# ======================================================================== F20
def f20():
    F = Folha(20, escala='1:5', material='B-01 Al 6061-T6 · cantoneira 40×40×4')
    ctx = [p.como('ctx') for p in quadro() if p.estilo == 'solid']
    pecas = chapa_fundo() + retencao_bateria()
    # ox 131 e não 150: a 1:5 o rover ocupa 209 mm e, centrado em 150, a vista chegava a
    # x 255 — por cima do bloco de texto desta folha, que começa em x 236.
    vs = Vista('superior', 5, 131, 90)
    desenha(F.s, vs, ctx + pecas + bateria_ref())
    for (x, y) in MALHA_MONTAGEM:
        cruz_centro(F.s, *vs.P((x, y, Z_QUADRO)), 2.2)
    cota_vista_h(F.s, vs, (-BATERIA[0] / 2, 0, 0), (BATERIA[0] / 2, 0, 0), 158)
    cota_vista_h(F.s, vs, (-225, 0, 0), (225, 0, 0), 166, txt='450 (entre batentes)')
    cota_vista_v(F.s, vs, (0, -BATERIA[1] / 2, 0), (0, BATERIA[1] / 2, 0), 38)
    cota_vista_v(F.s, vs, (0, -165, 0), (0, 165, 0), 30, txt='330')
    chamada(F.s, *vs.P((170, 240, Z_QUADRO)), 262, 40, 'malha de montagem M6 (16 pontos)', lado=1)
    chamada(F.s, *vs.P((40, 185 + 16, Z_QUADRO + 40)), 262, 58, 'rasgo 26 × 6 para a cinta F-23', lado=1)
    chamada(F.s, *vs.P((245 + 16, 60, Z_QUADRO + 40)), 262, 80, ['B-01 batente (4×)',
                                                                 'cantoneira 40×40×4 × 150'], lado=1)
    chamada(F.s, *vs.P((BATERIA[0] / 2, -140, Z_QUADRO)), 262, 104, 'caixa da bateria (referência)', lado=1)
    rotulo(F.s, 150, 182, 'ZONA DA BATERIA — VISTA SUPERIOR', '1:5', 'caixa em linha fantasma')

    va = Vista('frontal', 5, 330, 200)
    desenha_corte(F.s, va, ctx + pecas + bateria_ref(), 'x', 250.0)
    F.s.ln(*va.P((0, -200, Z_QUADRO + BATERIA[2] + 6)), *va.P((0, 200, Z_QUADRO + BATERIA[2] + 6)), 'raio')
    chamada(F.s, *va.P((0, 120, Z_QUADRO + BATERIA[2] + 6)), 372, 112, ['F-23 cinta 25 mm', 'sobre a caixa'],
            lado=1)
    cota_vista_v(F.s, va, (0, YQ, Z_QUADRO), (0, YQ, Z_QUADRO + 40), 284, txt='40')
    rotulo(F.s, 330, 166, 'CORTE NA LINHA DOS BATENTES', '1:5', 'plano X 250')

    F.bloco(26, 196, 198, f'''
<h3>Retenção da bateria</h3>
<ol class="notas">
<li>A caixa apoia na chapa de fundo (Z {num(Z_QUADRO)}) e é travada lateralmente por 4 batentes B-01
aparafusados na malha de montagem — F-22 M6 em porca-rebite instalada na própria chapa.</li>
<li>Duas cintas F-23 passam pelos rasgos dos batentes e prendem a caixa por cima.</li>
<li>Carga de projeto da amarração: 36,5 kg × 3 g = <b>1.074 N</b> na vertical e 537 N na lateral
{tag('CALC')}.</li>
<li>Manutenção: soltando as 2 cintas, a caixa sai por cima com os módulos da gaiola removidos.</li>
<li>Não furar a chapa de fundo fora da malha — abaixo dela fica a zona de visão da câmera de raiz.</li>
</ol>''')
    F.bloco(236, 190, 172, f'''
<h3>Caixa da bateria — pendência</h3>
<p>Dimensões usadas aqui: <b>{num(BATERIA[0])} × {num(BATERIA[1])} × {num(BATERIA[2])} mm</b>
{tag('ESTIMATIVA')}. A caixa real das 16 células EVE LF100LA ainda não tem desenho {tag('A VALIDAR')}.</p>
<p>Quando existir, muda apenas a <b>posição dos batentes na malha</b>: chapa, quadro e esta folha continuam
válidos.</p>''', h=42)
    return F


# ======================================================================== F21
def f21():
    F = Folha(21, escala='1:5 · 1:1', material='E-01/E-02 Al 5052-H32 e = 2 · E-10/E-11 Al 6061-T6')
    ctx = [p.como('ctx') for p in quadro() if p.estilo == 'solid']
    pecas = chapa_fundo() + bandejas() + retencao_bateria()
    # Mesma correção da folha 20: a 1:5 o rover ocupa 209 mm e, centrado em 150, a
    # vista chegava a x 255 — por cima do bloco de texto, que começa em x 236.
    vs = Vista('superior', 5, 131, 90)
    desenha(F.s, vs, ctx + pecas + bateria_ref())
    for (x, y, d, _) in M.furos_chapa():
        if d >= 30:
            cruz_centro(F.s, *vs.P((x, y, Z_QUADRO)), 3.4)
    chamada(F.s, *vs.P((185, 237, Z_QUADRO)), 252, 34, 'E-01 (2×)', lado=1)
    chamada(F.s, *vs.P((430, 150, Z_QUADRO)), 252, 52, 'E-02 (4×)', lado=1)
    chamada(F.s, *vs.P((300, 80, Z_QUADRO)), 258, 68, ['4× Ø32 — cabos', 'dos motores'], lado=1)
    chamada(F.s, *vs.P((-460, 0, Z_QUADRO)), 258, 88, ['E-STOP acima,', 'na tampa traseira'], lado=1)
    rotulo(F.s, 131, 158, 'ZONAS DA ELETRÔNICA — VISTA SUPERIOR', '1:5', 'bateria em linha fantasma')

    ve = Vista('lateral', 1, 790, 474.0)
    tampa = [p.como('ctx') for p in recorta_caixa([p for p in carenagens() if p.item == 'K-05'],
                                                  x=(-520, -400))]
    desenha(F.s, ve, tampa + estop())
    cota_vista_v(F.s, ve, (X_ESTOP, 0, Z_TAMPA), (X_ESTOP, 0, Z_TAMPA + 55), 282, txt='55')
    cota_vista_h(F.s, ve, (X_ESTOP - 25, 0, Z_TAMPA), (X_ESTOP + 25, 0, Z_TAMPA), 88, txt='50')
    bx = ve.P((X_ESTOP, 0, Z_TAMPA))
    F.s.rect(bx[0] - 20, bx[1] - 12, bx[0] + 20, bx[1], 'ref')
    F.s.rect(bx[0] - 11, bx[1], bx[0] + 11, bx[1] + 18, 'ref')
    chamada(F.s, bx[0] + 18, bx[1] - 6, 368, 78, 'botão Ø22 IP65 (ref.)', lado=1)
    chamada(F.s, *ve.P((X_ESTOP + 25, 0, Z_TAMPA + 53)), 368, 20, ['E-11 protetor', 'barra 50×4 dobrada'],
            lado=1)
    chamada(F.s, *ve.P((X_ESTOP + 30, 0, Z_G2 - 1.5)), 368, 38, ['E-10 reforço 3 mm', 'sob a tampa'], lado=1)
    chamada(F.s, *ve.P((X_ESTOP, 0, Z_TAMPA)), 368, 58, [f'recorte Ø{num(D_ESTOP)}', 'na tampa e no E-10'],
            lado=1)
    rotulo(F.s, 330, 96, 'E-STOP — DETALHE', '1:1', f'botão Ø22 IP65 em X {num(X_ESTOP)}')

    F.bloco(26, 172, 198, '''
<h3>O que o chassi oferece para a eletrônica</h3>
<ol class="notas">
<li><b>Zonas livres</b> entre Z 250 e 340: duas faixas laterais de 380 × 54 ao lado da bateria e duas áreas de
extremidade de 120 × 500. Altura útil de 90 mm; acima do deck, mais 57 mm até a tampa.</li>
<li><b>Bandejas E-01 e E-02</b>: chapa de 2 mm com furos Ø5,5 para os componentes, fixadas na malha da chapa
de fundo (F-22).</li>
<li><b>Entradas de cabo</b>: 4 × Ø32 dos motores (chapa de fundo), 2 × Ø20 dos mastros (luvas) e 1 × Ø30 do
LiDAR (tampa dianteira), todas com passa-cabo.</li>
<li><b>Aterramento</b>: 2 pontos M6 identificados no anel inferior, com arruela dentada.</li>
<li><b>E-STOP</b>: botão Ø22 IP65 na tampa traseira, com reforço E-10 por baixo e protetor E-11 por cima,
acessível por cima e fora da linha dos galhos.</li>
</ol>
<p class="mini">O arranjo dos componentes (drives, BMS, DC/DC, Jetson, controlador de segurança, disjuntor e
conectores) é <b>pendência da integração elétrica</b> ''' + tag('A VALIDAR') + ''' — esta folha define espaço,
entradas e pontos de fixação, não a posição de cada caixa.</p>''')

    lc = lista_corte('B')
    linhas = []
    for g in ('M', 'B', 'E'):
        linhas.append(f'<tr class="grupo"><td colspan="5">{g} — {GRUPOS[g]}</td></tr>')
        for item, d in lc.items():
            if not item.startswith(g):
                continue
            it = ITENS[item]
            linhas.append([f'<b>{item}</b>', it['nome'], it['desc'], str(d['qtd']), kg(d['massa'], 2)])
    linhas.append(['', '', '<b>Subtotal M + B + E</b>', '',
                   f'<b>{kg(sum(d["massa"] for i, d in lc.items() if not i.startswith("N")), 2)}</b>'])
    F.bloco(236, 112, 172, '<h3>Lista de materiais — Parte B (M, B, E)</h3>' +
            tabela(['Item', 'Peça', 'Formato', 'Qtd', 'kg'], linhas, 'corte bom', col=[12, 32, 36, 8, 12]) +
            '<p class="mini">Cotar em separado da Parte A. Fixadores F-20 a F-29 na folha 13. '
            'Grupo N (interfaces de sensores) na folha 22.</p>', h=100)
    return F


# ======================================================================== F22
def f22():
    F = Folha(22, escala='1:1 · 1:2 · 1:5', material='Al 6061-T6 · Al 5052-H32 · PC · UHMW-PE')
    corpo = [p for p in quadro() + gaiola() + carenagens() if p.estilo == 'solid']

    # --- D1: antena GNSS sobre a tampa traseira
    v1 = Vista('lateral', 2, 245, 242)
    ctx1 = [p.como('ctx') for p in recorta_caixa(corpo, x=(-430.0, -270.0), z=(380.0, 400.0))]
    desenha(F.s, v1, ctx1 + suporte_gnss() + [p.como('ref') for p in gnss_ref()])
    linha_centro(F.s, *v1.P((X_GNSS, 0, 386)), *v1.P((X_GNSS, 0, 446)))
    cota_vista_v(F.s, v1, (X_GNSS, 0, Z_GNSS[0]), (X_GNSS, 0, Z_GNSS[1] + H_ANTENA), 30, txt='35')
    chamada(F.s, *v1.P((X_GNSS + 40, 0, Z_GNSS[1])), 112, 24, ['N-01 chapa 5', '110 × 110'], lado=1)
    chamada(F.s, *v1.P((X_GNSS, 0, Z_GNSS[1] + 20)), 112, 40, 'antena (referência)', lado=1)
    rotulo(F.s, 70, 62, 'D1 · ANTENA GNSS', '1:2', 'sobre a tampa traseira')

    # --- D2: berço do IMU
    v2 = Vista('lateral', 2, 30, 182)
    ctx2 = [p.como('ctx') for p in recorta_caixa([p for p in chapa_fundo() + quadro() if p.estilo == 'solid'],
                                                 x=(240.0, 360.0), z=(240.0, 320.0))]
    desenha(F.s, v2, ctx2 + berco_imu())
    cota_vista_v(F.s, v2, (X_IMU, 0, Z_QUADRO), (X_IMU, 0, Z_IMU), 143, txt='60')
    cota_vista_h(F.s, v2, (X_IMU - 45, 0, Z_IMU), (X_IMU + 45, 0, Z_IMU), 16, txt='90')
    chamada(F.s, *v2.P((X_IMU + 30, 0, Z_IMU)), 216, 26, ['N-02 berço, chapa 6', 'face usinada Z 310'],
            lado=1)
    chamada(F.s, *v2.P((X_IMU + 22, 0, Z_QUADRO + 27)), 216, 48, ['N-03 espaçador', 'Ø12 × 54 (4×)'], lado=1)
    rotulo(F.s, 180, 74, 'D2 · BERÇO DO IMU', '1:2', 'corte em Y 0')

    # --- D3: farol na carenagem frontal
    v3 = Vista('frontal', 2, 230, 213)
    ctx3 = [p.como('ctx') for p in recorta_caixa([p for p in carenagens() if p.item == 'K-02'],
                                                 y=(95.0, 205.0), z=(325.0, 395.0))]
    desenha(F.s, v3, ctx3 + [p for p in suporte_led() if p.centro()[1] > 0])
    cruz_centro(F.s, *v3.P((0, Y_LED, Z_LED)), 8)
    cota_vista_v(F.s, v3, (0, Y_LED, Z_DECK), (0, Y_LED, Z_LED), 275, txt=num(Z_LED - Z_DECK, 1))
    chamada(F.s, *v3.P((0, Y_LED + 10, Z_LED)), 336, 20, [f'Ø{num(D_LED)} — farol', 'reforço N-08 por dentro'],
            lado=1)
    rotulo(F.s, 305, 56, 'D3 · FAROL', '1:2', 'faixa livre Z 341 → 376')

    # --- D4: câmera de zona de raiz
    v4 = Vista('lateral', 2, -135, 260)
    pecas4 = recorta_caixa([p for p in chapa_fundo() + quadro() if p.estilo == 'solid'],
                           x=(340.0, 520.0), z=(225.0, 300.0))
    desenha_corte(F.s, v4, [p.como('ctx') for p in pecas4] + visao_raiz(), 'y', 0.0)
    c4 = v4.P((440.0, 0, Z_QUADRO + 28))
    for xb in (JANELA_RAIZ[0], JANELA_RAIZ[1]):
        b4 = v4.P((xb, 0, Z_QUADRO - E_CHAPA))
        dx, dy = b4[0] - c4[0], b4[1] - c4[1]
        n = math.hypot(dx, dy)
        F.s.ln(c4[0], c4[1], c4[0] + dx / n * 46, c4[1] + dy / n * 46, 'raio')
    F.s.tx(38, 94, 'campo útil limitado pela abertura', T, a='start', c='tx sec')
    cota_vista_h(F.s, v4, (JANELA_RAIZ[0], 0, Z_QUADRO), (JANELA_RAIZ[1], 0, Z_QUADRO), 104,
                 txt=num(JANELA_RAIZ[1] - JANELA_RAIZ[0]))
    chamada(F.s, *v4.P((440.0, 0, Z_QUADRO + 20)), 126, 112, ['N-07 face a 24°', 'chapa 3'], lado=1)
    chamada(F.s, *v4.P((400.0, 0, Z_QUADRO + 1.5)), 126, 128, ['N-04 janela PC 3', 'por dentro'], lado=1)
    chamada(F.s, *v4.P((413.0, 0, Z_QUADRO - E_CHAPA - 4)), 126, 144, ['N-05 barras Ø8', 'proteção (2×)'],
            lado=1)
    rotulo(F.s, 80, 168, 'D4 · CÂMERA DE ZONA DE RAIZ', '1:2', 'corte em Y 0')

    # --- D5: carenagem anti-galho da câmera
    v5 = Vista('superior', 2, 200, 292)
    p5 = [p for p in carenagem_cameras() + suportes_camera() + mastro()
          if p.centro()[1] > 0 and p.bbox()[2][0] <= CAMERAS_Z[2] <= p.bbox()[2][1]]
    desenha_corte(F.s, v5, p5, 'z', CAMERAS_Z[2])
    cota_vista_h(F.s, v5, (-25.0, 300, 0), (45.0, 300, 0), 116, txt='70')
    rotulo(F.s, 204, 166, 'D5 · CARENAGEM DA CÂMERA', '1:2', 'nariz para +X · UHMW-PE 3')

    # --- D6: onde fica cada interface
    pi = [p for p in conjunto('AB') if p.estilo == 'solid'] + [r.como('ref') for r in rodas()]
    cam = iso_no_retangulo(pi, 292, 72, 408, 144, 9.6, az=-128, el=26)
    desenha_iso(F.s, cam, pi)
    for cod, p, (dx, dy) in (('N-01', (X_GNSS, 0, 403), (-13, -5)), ('N-02', (X_IMU, 0, 310), (12, -9)),
                             ('N-04', (430, 0, 250), (-6, 13)), ('N-08', (XQ, Y_LED, Z_LED), (10, 9)),
                             ('N-09', (0, 320, CAMERAS_Z[1]), (-13, 0))):
        q = cam.P(p)
        balao(F.s, q[0] + dx, q[1] + dy, cod, alvo=q)
    rotulo(F.s, 350, 150, 'D6 · LOCALIZAÇÃO')

    F.bloco(26, 196, 198, f'''
<h3>O que cada interface resolve</h3>
<ol class="notas">
<li><b>N-01 · antena GNSS</b> {tag('NOVO')} — a baseline põe a antena em X 0 · Z 390, que fica <b>sob a tampa
de alumínio</b> e dentro da gaiola: sem visão de céu. Aqui ela sobe para fora, em X {num(X_GNSS)}, com o plano
de terra em Z {num(Z_GNSS[1], 1)}.</li>
<li><b>N-02/N-03 · berço do IMU</b> {tag('NOVO')} — face usinada em Z {num(Z_IMU)} (altura da baseline),
arestas alinhadas a X e Y, com 0,5° de tolerância angular. Offset ao CG: X +{num(X_IMU)} mm, a informar ao
software.</li>
<li><b>N-04 a N-07 · câmera de zona de raiz</b> {tag('NOVO')} — a baseline a coloca em Z 150, <b>abaixo do
chassi</b>, onde ela viraria o ponto mais baixo do rover. Aqui ela fica dentro, olhando o solo por uma janela
de policarbonato protegida por duas barras; nada desce abaixo da chapa.</li>
<li><b>N-08 · faróis</b> {tag('NOVO')} — Ø{num(D_LED)} na carenagem frontal, na única faixa livre entre o anel
superior do quadro (Z 340) e o trilho da gaiola (Z 377).</li>
<li><b>N-09 · carenagem anti-galho</b> {tag('BASE')} — desenhada a partir da descrição da baseline (caixa com
nariz). 6 peças no mastro; as 2 câmeras baixas já estão protegidas pela carenagem K-02 e pela janela N-04.</li>
</ol>''')
    lc = lista_corte('B')
    linhas = [[f'<b>{i}</b>', ITENS[i]['nome'], ITENS[i]['desc'], str(d['qtd']), kg(d['massa'], 2)]
              for i, d in lc.items() if i.startswith('N')]
    linhas.append(['', '', '<b>Subtotal do grupo N</b>', '',
                   f'<b>{kg(sum(d["massa"] for i, d in lc.items() if i.startswith("N")), 2)}</b>'])
    F.bloco(236, 156, 172, '<h3>Lista de materiais — grupo N</h3>' +
            tabela(['Item', 'Peça', 'Formato', 'Qtd', 'kg'], linhas, 'corte bom', col=[10, 30, 38, 8, 14]) +
            f'<p class="mini">Largura com as carenagens: <b>674 mm</b> {tag("CALC")}, dentro da folga de '
            f'237 mm. Sombra da antena no LiDAR ≈ 6° {tag("ESTIMATIVA")} — ensaio 1, folha 26.</p>', h=76)
    return F


# ======================================================================== F23
def f23():
    F = Folha(23, material='—')
    linhas = [
        ['1', 'Base dos mastros', 'Desenhada na folha 17; falta aprovar Y ±280 e a verificação da solda.',
         'Eng. mecânico', 'Parecer + caso 6 do FEA'],
        ['2', 'Suportes das câmeras', 'Placa e parafusos U definidos (folha 19); falta a furação da câmera.',
         'Integração de sensores', 'Desenho da OAK-D Pro W PoE'],
        ['3', 'Interface MPW86', 'Orientação dos 7 furos, folga da face, freio e encoder.',
         'Compras / ElectroCraft', 'Desenho 2D/3D do fabricante'],
        ['4', 'Suspensão', 'Decidir entre protótipo rígido e curso de 40 mm (refaz S-01…S-03).',
         'Eng. mecânico', 'Decisão registrada na revisão'],
        ['5', 'Caixa da bateria', 'Dimensões e furação das 16 células; posição dos batentes (folha 20).',
         'Eng. elétrica', 'Desenho da caixa'],
        ['6', 'Eletrônica e E-STOP', 'Arranjo dos componentes sobre as zonas e bandejas (folha 21).',
         'Eng. eletrônica', 'Layout aprovado sobre a folha 21'],
        ['7', 'Solda do 6061-T6', 'Definir a condição de cálculo: como soldado ou novo T6 (folha 25).',
         'Eng. mecânico', 'Folha 24 assinada'],
        ['8', 'FEA e fadiga', 'Rodar os 8 casos de carga da folha 25 com a geometria deste caderno.',
         'Eng. mecânico ou terceiro', 'Relatório com margem por caso'],
        ['9', 'Massa oficial', 'Resolver 85,04 × 82,49 kg e aceitar ou reduzir a massa (folha 24).',
         'Eng. + gestão', 'Número único na baseline Rev F'],
        ['10', 'Diagonais do quadro', 'Decidir se entram; opções e custo de massa na folha 25.',
         'Eng. mecânico', 'Decisão + FEA de torção'],
        ['11', 'Campo de visão do LiDAR', 'Confirmar o centro óptico do Mid-360 e a ausência de obstrução.',
         'Sensores', 'Ensaio 1 da folha 26'],
        ['12', 'Câmera frontal', 'Janela de 140 × 32 na K-02 e enquadramento.', 'Sensores',
         'Ensaio 2 da folha 26'],
        ['13', 'Vão livre', 'Definir a cota oficial e onde ela é medida (proposta na folha 26).',
         'Eng. mecânico', 'Valor único na baseline Rev F'],
        ['14', 'Freio do MPW86', 'Torque de retenção — pendência da própria baseline.', 'Compras',
         'Resposta da ElectroCraft'],
        ['15', 'Aderência do solo', 'μ real da lavoura, seco e úmido.', 'Eng. + campo',
         'Ensaio 5 da folha 26'],
        ['16', 'Câmera da zona de raiz', 'Desenhada na folha 22; falta confirmar o campo pela janela.',
         'Sensores', 'Ensaio 2 da folha 26'],
        ['17', 'Antena GNSS', 'Modelo, furação e centro de fase; medir a sombra no LiDAR.', 'Sensores',
         'Datasheet + ensaio 1 da folha 26'],
        ['18', 'IMU', 'Furação real do MTi-630 e offset ao CG declarado no software.', 'Sensores',
         'Desenho do fabricante'],
        ['19', 'Faróis', 'Modelo, potência e corrente (a baseline só dá a massa).', 'Eng. elétrica',
         'Componente escolhido'],
        ['20', 'Largura real 674 mm', 'Aceitar ou reduzir a carenagem das câmeras.', 'Eng. + gestão',
         'Número único na baseline Rev F'],
        ['21', 'Envelope de estabilidade', 'Refazer com o CG consolidado e publicar um valor só.',
         'Eng. mecânico', 'Folha 24 + baseline Rev F'],
        ['22', 'Escolha do motor-roda', 'MPW86 × ZLTECH: −R$ 21.165 e +16 kg, interfaces diferentes.',
         'Eng. + gestão', 'Decisão + folha 27'],
        ['23', 'Interface do motor escolhido', 'Desenho dimensional do fabricante (eixo ou flange).',
         'Compras', 'Desenho 2D/3D'],
        ['24', 'Freio do motor escolhido', 'No ZLTECH o freio EMB é opcional — pedir na cotação.',
         'Compras', 'Proposta com freio incluso'],
    ]
    F.bloco(26, 20, 382, '<h3>Plano de fechamento — o que falta para liberar a fabricação</h3>' +
            tabela(['#', 'Item', 'O que falta', 'Quem fecha', 'Critério de aceite'], linhas, 'compacta',
                   col=[4, 17, 42, 17, 20]), h=168)
    F.bloco(26, 194, 198, '''
<h3>Como usar este caderno agora</h3>
<ol class="notas">
<li><b>Cotar</b> — envie a Parte A (folhas 01 a 16) e a pasta <b>dxf/</b>. É geometria fechada, com tolerâncias,
soldas e acabamento definidos; nenhum dos itens acima muda o preço.</li>
<li><b>Validar</b> — o engenheiro mecânico trabalha na folha 15 (parecer), apoiado nas folhas 22 a 25.</li>
<li><b>Fabricar</b> — só depois de fechar os itens 1 a 10 e emitir a revisão 1 das folhas afetadas.</li>
</ol>
<p class="mini">Os itens 11 a 21 correm em paralelo com a cotação: são ensaios e confirmações que não mudam a
geometria do quadro nem da gaiola.</p>''')
    F.bloco(236, 194, 172, '''
<h3>O que muda a cada decisão</h3>
<ul>
<li><b>Suspensão</b>: refaz S-01 a S-03 e a folha 07; o quadro não muda.</li>
<li><b>Caixa da bateria</b>: muda só a posição dos batentes na malha (folha 20).</li>
<li><b>Furação da câmera</b>: muda só o DXF do M-20 (folha 19).</li>
<li><b>Novo T6 após a solda</b>: muda prazo, custo e a ordem de furação (folhas 02 e 24).</li>
<li><b>Diagonais</b>: mudam o quadro (folhas 04 e 06), a massa e o espaço da bateria.</li>
<li><b>LiDAR mais alto</b>: mudam G-06 e a tampa K-04 (folha 10).</li>
</ul>''', h=38)
    return F


# ======================================================================== F24
def f24():
    F = Folha(24, material='—')
    c = consolidado()
    nomes = {'A · Q': 'Parte A — quadro estrutural', 'A · M': 'Parte A — base dos mastros',
             'A · C': 'Parte A — chapa de fundo e nervuras', 'A · S': 'Parte A — suportes do motor-roda',
             'A · G': 'Parte A — gaiola de proteção', 'A · K': 'Parte A — carenagens e tampas',
             'B · M': 'Parte B — mastros, bainha e suportes', 'B · B': 'Parte B — retenção da bateria',
             'B · E': 'Parte B — bandejas e E-STOP', 'B · N': 'Parte B — interfaces de sensores',
             'Fixadores': 'Fixadores (estimativa)'}
    linhas = [['Tabela 5.1 da baseline — itens mantidos', kg(c['mantidos'][0], 2),
               num(round(c['mantidos'][1]))]]
    for n, m, z in c['novos']:
        linhas.append([nomes.get(n, n), kg(m, 2), num(round(z))])
    linhas.append(['<b>Massa mínima verificável</b>', f'<b>{kg(c["m_min"], 2)}</b>',
                   f'<b>{kg(c["zcg"], 1)}</b>'])
    F.bloco(26, 20, 188, '<h3>Massa consolidada — baseline + Parte A + Parte B</h3>' +
            tabela(['Parcela', 'kg', 'Z do CG (mm)'], linhas, 'compacta', col=[58, 20, 22]) +
            f'''<p class="mini">A tabela 5.1 da baseline soma {kg(sum(TABELA_51), 2)} kg, mas o texto declara
85,04 kg — faltam {kg(85.04 - sum(TABELA_51), 2)} kg não localizados. Aqui parte-se da soma verificável e
substituem-se os itens redesenhados (quadro, chapa, suportes, gaiola, mastro, bainha e ponta) pelos valores
calculados a partir da geometria deste caderno.</p>''', h=124)
    res = [
        ['Massa mínima (kg)', '85,04 declarada · 82,49 somada', f'<b>{kg(c["m_min"], 2)}</b>'],
        ['Δ sobre a baseline declarada', '—', f'+{kg(c["delta"], 2)} kg'],
        ['Margem de 15 % (12,76 kg)', '12,76 kg', f'{kg(c["margem"], 2)} kg restantes'],
        ['Massa máxima com 25 kg de carga', '≈ 126 kg', f'{kg(c["m_max"], 1)} kg'],
        ['CG — altura Z', '297 mm', f'{kg(c["zcg"], 1)} mm'],
        ['Largura externa', '600 mm', '600 mm (corpo) · 674 com carenagens'],
        ['Tombamento lateral estático', '38,3°', f'{kg(c["tomb"], 1)}°'],
        ['Envelope conservador (fórmula 6.1)', f'{kg(M.envelope_estabilidade(297.0), 1)}° para CG 297',
         f'{kg(M.envelope_estabilidade(c["zcg"]), 1)}°'],
        ['Torque por roda a 13°', '11,0 N·m', f'{kg(c["torque13"], 1)} N·m (limite 20)'],
    ]
    F.bloco(222, 20, 186, '<h3>Efeito nos números da baseline</h3>' +
            tabela(['Grandeza', 'Baseline', 'Consolidado'], res, 'compacta', col=[40, 30, 30]) +
            f'''<p class="mini">O CG sobe porque a Parte B acrescenta massa alta (mastros, bainha e câmeras);
o tombamento estático cai menos de 1°. Aplicando a fórmula da seção 6.1 da baseline com os parâmetros ali
publicados (e_y 15 · φ_c 3° · FS 1,3 · obstáculo 60 · dinâmica 2°), o envelope sai
{kg(M.envelope_estabilidade(297.0), 1)}° para o CG de 297 mm — a baseline publica 16,2°, que
<b>não conseguimos reproduzir</b> com esses parâmetros. O que decide é o delta: <b>−{kg(M.envelope_estabilidade(297.0) - M.envelope_estabilidade(c["zcg"]), 1)}°</b>
por causa do CG mais alto, e o limite continua sendo a aderência (13,0°).</p>''', h=112)
    red = [
        ['Chapa de fundo 2 → 1,5 mm', '−0,84', 'Exige nervura extra ou aceitar flecha maior'],
        ['Carenagens 2 → 1,5 mm', '−1,15', 'Muda o envelope: quadro passa a 1.047 × 597'],
        ['Tampas 1,2 → 1,0 mm', '−0,35', 'Sem impacto estrutural'],
        ['Aliviar S-01 e S-02 com rasgos', '−0,60', 'Só depois do FEA'],
        ['Bandejas 2 → 1,5 mm', '−0,25', 'Sem impacto'],
        ['Suprimir 1 barra G-03 por módulo', '−0,17', 'Perde apoio da tampa'],
    ]
    F.bloco(26, 152, 188, '<h3>Se for preciso reduzir massa</h3>' +
            tabela(['Ação', 'Δ kg', 'Consequência'], red, 'compacta', col=[40, 14, 46]) +
            '<p class="mini">Somadas, as quatro primeiras devolvem cerca de 2,9 kg. Reduzir ou re-baselinar a '
            'massa é decisão do engenheiro — as duas saídas são aceitáveis.</p>')
    F.bloco(222, 128, 186, f'''
<h3>Recomendação</h3>
<p>Adotar <b>{kg(c['m_min'], 1)} kg</b> como massa mínima oficial do V3 e refazer a margem de 15 % sobre ela
(nominal ≈ {kg(c['m_min'] * 1.15, 1)} kg). Autonomia, aclive e estabilidade da baseline devem ser reprocessados
com esse número: nenhuma conclusão muda — o limite continua sendo a aderência, a 13,0° — mas os valores
publicados passam a ser coerentes entre si.</p>
<p class="mini">Ainda não está contado: cabos e conectores das câmeras, a caixa real da bateria e a carenagem
anti-galho das câmeras — juntos, algo entre 1 e 2 kg.</p>''', h=104)
    return F


# ======================================================================== F25
def f25():
    F = Folha(25, material='—')
    solda = tabela(['Opção', 'Tensão adotada', 'Custo e prazo', 'Observação'], [
        ['<b>A</b> — como soldado', '≈ 110 MPa na ZTA', 'sem custo extra', 'Máximo deste caderno: 50 MPa'],
        ['<b>B</b> — novo tratamento T6', '276 MPa', 'forno, prazo e risco de distorção',
         'Exige reusinar as faces de montagem'],
    ], 'compacta', col=[24, 22, 26, 28])
    diag = tabela(['Opção', 'Δ massa', 'Observação'], [
        ['Diagonais no plano de cada anel', '+0,9 kg', 'Cabem; reduzem o vão útil da bateria'],
        ['Chapa de fundo 2 → 3 mm', '+1,7 kg', 'Mais simples; melhora o diafragma'],
        ['Vão entre anéis 30 → 60 mm com diagonais verticais', '+1,4 kg', 'Muda alturas, deck e CG'],
    ], 'compacta', col=[52, 16, 32])
    F.bloco(26, 20, 188, f'''
<h3>A · Condição de solda do 6061-T6</h3>
<p>Na zona afetada pelo calor o 6061-T6 perde cerca de 40 % da resistência. O cálculo precisa declarar em que
condição a estrutura é avaliada:</p>{solda}
<p><b>Recomendação:</b> opção <b>A</b> para o protótipo, com FEA e verificação de fadiga na ZTA. A geometria já
tem folga — o ponto mais solicitado (longarina entre estações de roda) fica em 45 MPa, 2,4× abaixo do limite
da ZTA.</p>
<h3>B · Diagonais do quadro</h3>
<p>O quadro desenhado <b>não tem diagonais</b>: a rigidez à torção vem dos dois anéis, dos 16 montantes e da
chapa de fundo trabalhando como diafragma. Se o FEA mostrar que falta rigidez:</p>{diag}
<p class="mini">As diagonais que aparecem nas imagens de apresentação não caberiam no vão de 30 mm entre os
anéis — é por isso que elas não existem no projeto.</p>
<h3>D · O que já foi verificado à mão</h3>
<p>A folha 15 cobre longarinas, suporte do motor-roda, parafusos M8, chapa de fundo, nervura, torque e
tombamento, com fator dinâmico 3. Serve para dimensionar, não para liberar: fadiga, torção global e
concentração nas soldas só saem no FEA.</p>''')
    casos = [
        ['1', 'Estático 1 g', 'm = 137,5 kg distribuída', 'σ e flecha de referência'],
        ['2', 'Vertical 3 g', 'impacto em buraco, 4 rodas', 'σ &lt; 110 MPa na ZTA'],
        ['3', 'Lateral 2 g', 'escorregamento contra obstáculo', 'σ e deslocamento'],
        ['4', 'Torção', '1 roda suspensa 100 mm', 'rigidez torcional e σ'],
        ['5', 'Tração e frenagem', '35 N·m por roda', 'σ nos suportes S'],
        ['6', 'Mastro', '50 N no topo + vibração de 5 Hz', 'σ na base · 1ª freq. ≥ 7,5 Hz'],
        ['7', 'Bateria', '36,5 kg × 3 g na amarração', 'σ nos batentes e na chapa'],
        ['8', 'Içamento', '2 pontos, 1,5 × massa', 'σ e definição dos pontos'],
    ]
    F.bloco(222, 20, 186, '<h3>C · Encargos para o FEA e a fadiga</h3>' +
            tabela(['#', 'Caso de carga', 'Descrição', 'Critério'], casos, 'compacta', col=[5, 22, 38, 35]) +
            '''
<p><b>Condições de contorno:</b> apoio nos 4 furos Ø88 das faces de montagem do MPW86; molas equivalentes ao
pneu (rigidez a medir) ou apoio fixo como simplificação conservadora.</p>
<p><b>Modelo:</b> casca para tubos e chapas, malha de 5 mm com refino de 2 mm em soldas e furos; soldas como
ligação rígida; 6061-T6 com ZTA de 25 mm em torno de cada cordão.</p>
<p><b>Critérios de aceite:</b> von Mises &lt; 110 MPa na ZTA e &lt; 180 MPa fora dela; flecha do quadro &lt;
L/500 no caso 1; fadiga pelo EN 1999-1-3 para 10⁶ ciclos na categoria de detalhe aplicável; 1ª frequência do
conjunto afastada 1,5× da excitação de 5 Hz.</p>
<p><b>Entregáveis:</b> relatório com margem por caso, mapa de tensões, lista de pontos críticos e recomendações
— que voltam para este caderno como revisão 1.</p>''', h=206)
    return F


# ======================================================================== F26
def f26():
    F = Folha(26, material='—')
    ensaios = [
        ['1', 'LiDAR e antena GNSS', 'Mid-360 no G-06 e antena no N-01; gravar nuvem de 360° e fixar RTK',
         'Sombra da antena ≤ 10° de azimute; RTK fixo em campo aberto', 'Sensores'],
        ['2', 'Câmeras frontal e de raiz', 'Frontal atrás da janela da K-02; de raiz pela janela N-04',
         'Janelas fora do quadro útil; solo enquadrado a 250 mm', 'Sensores'],
        ['3', 'Câmeras do mastro', 'Alvo padrão na linha do café, com os 3 andares montados',
         'Sobreposição ≥ 20 % entre andares; GSD ≤ 0,3 mm/px', 'Sensores'],
        ['4', 'Vão livre real', 'Medir do solo ao ponto mais baixo entre rodas, com carga máxima',
         'Registrar o valor e fixar a cota oficial', 'Eng. mecânico'],
        ['5', 'Aderência do solo', 'Tração em rampa na fazenda-piloto, solo seco e úmido',
         'μ medido; confirmar ou corrigir o aclive de 13°', 'Eng. + campo'],
        ['6', 'Freio', 'Retenção em rampa de 30° com massa máxima', 'Não desliza em 10 minutos', 'Eng.'],
        ['7', 'Vibração do mastro', 'Excitar o topo e medir com o IMU, câmeras montadas',
         '1ª frequência ≥ 7,5 Hz', 'Eng. mecânico'],
        ['8', 'Aperto e estanqueidade', 'Torquímetro em 100 % dos fixadores; jato de água na carenagem',
         'Torques da folha 13; sem entrada de água na eletrônica', 'Montagem'],
    ]
    F.bloco(26, 20, 382, '<h3>Plano de validação — bancada e campo</h3>' +
            tabela(['#', 'Ensaio', 'Como', 'Critério de aceite', 'Responsável'], ensaios, 'compacta',
                   col=[4, 18, 33, 30, 15]) +
            '''<p class="mini">Cada ensaio fecha uma linha da folha 23. O resultado entra na revisão 1 deste
caderno e na baseline Rev F.</p>''', h=128)
    vao = tabela(['Onde se mede', 'Altura (mm)'], [
        ['Sob o quadro, entre as rodas', '250'],
        ['Ponto mais baixo entre as rodas (nervuras C-02)', '208'],
        ['Na linha das rodas — corpo do MPW86', '57'],
        ['Na linha das rodas — suporte S-02', '38'],
    ], 'compacta', col=[70, 30])
    F.bloco(26, 156, 188, f'''
<h3>Vão livre — proposta de definição</h3>
<p>A baseline diz "vão livre 150 mm" sem dizer onde. Este caderno mede quatro coisas diferentes:</p>{vao}
<p><b>Proposta:</b> adotar <b>vão livre = 208 mm</b>, medido entre as rodas, e registrar 38 mm como altura
mínima na linha das rodas — assim ninguém lê 150 mm como altura disponível em toda a região.</p>''')
    F.bloco(222, 156, 186, '''
<h3>Ordem sugerida</h3>
<ol class="notas">
<li>Ensaios 1, 2 e 3 em bancada, com o chassi montado — fecham os sensores antes de ir a campo.</li>
<li>Ensaio 8 na primeira montagem completa e repetido após o primeiro dia de campo.</li>
<li>Ensaios 4, 5 e 6 na fazenda-piloto, no mesmo dia e no mesmo talhão.</li>
<li>Ensaio 7 depois de 4 e 5, com o mastro já submetido a vibração real.</li>
</ol>
<p class="mini">Os ensaios 5 e 6 são os dois que a própria baseline lista como bloqueadores de produção e que
nenhuma conta resolve.</p>''', h=76)
    return F


# ======================================================================== F27
def f27():
    F = Folha(27, escala='1:2', material='—')
    c = M.consolidado()
    i = M.impacto_motor('ZLTECH')
    novo = M.MOTORES['ZLTECH']

    # --- D1: o que a interface do motor define no chassi
    S = M.braco(1, 1)
    v1 = Vista('lateral', 5, -13, 79)
    desenha(F.s, v1, [p.como('ctx') for p in S] + M.mpw86_ref(M.XS, 1))
    linha_centro(F.s, *v1.P((M.XS - 120, 0, M.Z_EIXO)), *v1.P((M.XS + 120, 0, M.Z_EIXO)))
    cota_vista_v(F.s, v1, (M.XS, 0, 0), (M.XS, 0, M.Z_EIXO), 86, txt=num(M.Z_EIXO))
    cota_vista_v(F.s, v1, (M.XS, 0, 0), (M.XS, 0, M.Z_QUADRO), 94, txt=num(M.Z_QUADRO))
    solo(F.s, 30, 84, v1.P((0, 0, 0))[1])
    rotulo(F.s, 60, 96, 'D1 · O QUE DEPENDE DO MOTOR', '1:5',
           'suporte dianteiro · roda Ø200 em fantasma')

    # --- D2: as duas montagens, lado a lado
    def diagrama(cx, cy, titulo, sub, dy):
        F.s.tx(cx, cy - 34, titulo, T, peso=600)
        F.s.tx(cx, cy + dy, sub, T, c='tx sec')

    ca, cb = 172.0, 216.0
    cy = 52.0
    # (a) flange do MPW86, 1:2
    F.s.circ(ca, cy, M.MPW_FACE / 4, 'vis')
    F.s.circ(ca, cy, M.D_BORE / 4, 'vis')
    for ang in M.furos_mpw():
        t = math.radians(ang)
        F.s.circ(ca + M.MPW_PCD / 4 * math.cos(t), cy + M.MPW_PCD / 4 * math.sin(t), 1.1, 'vis')
    cruz_centro(F.s, ca, cy, M.MPW_FACE / 4 + 2)
    diagrama(ca, cy, 'MPW86 · FLANGE', '7 × M4 · PCD 95 · bore Ø88', 40)
    # (b) eixo do ZLTECH, 1:2
    F.s.circ(cb, cy, 10.0, 'vis')
    F.s.circ(cb, cy, 5.0, 'vis')
    cruz_centro(F.s, cb, cy, 12)
    F.s.tx(cb, cy + 22, 'Ø ?', T, peso=600)
    diagrama(cb, cy, 'ZLTECH · EIXO', '1 furo e porca', 47)
    rotulo(F.s, 194, 112, 'D2 · AS DUAS MONTAGENS', '1:2', 'mesma função, fabricação diferente')

    F.bloco(26, 130, 198, '''
<h3>Os dois motores, lado a lado</h3>
''' + tabela(['Característica', 'ElectroCraft MPW86', 'ZLTECH ZLLG80ASM800', 'Efeito da troca'], [
        ['Preço unitário', 'R$ 6.425,00', '<b>R$ 1.133,68</b>', 'R$ 1.028,22 acima de 200 peças'],
        ['4 motores', 'R$ 25.700,00', '<b>R$ 4.534,72</b>', f'<b>economia de R$ {num(i["economia"], 2)}</b>'],
        ['Torque contínuo / pico', '20 / 35 N·m', '20 / <b>60</b> N·m', 'pico 71 % maior'],
        ['Rotação', '—', '150 rpm (máx. 180)', '1,57 m/s com roda de 200'],
        ['Roda', 'Ø200 mm', 'Ø200 mm · PU', 'vão livre e bitola preservados'],
        ['Carga por roda', '227 kg', '150 kg', f'uso real: {num(i["carga_roda"], 1)} kg'],
        ['Massa por motor', '4,5 kg', '<b>8,5 kg</b>', f'<b>+{num(i["d_massa"], 1)} kg</b> no rover'],
        ['Acionamento', 'Redutor 20:1', 'Direto, sem redutor', 'menos manutenção'],
        ['Montagem', 'Flange: 7 × M4 no PCD 95', '<b>Por eixo, com porca</b>', 'simplifica a S-02'],
        ['Freio', 'De fábrica, por mola', 'Opcional (EMB)', '<b>pedir na cotação</b>'],
        ['Proteção', '—', 'IP65 no título · IP54 na tabela', 'divergência da própria página'],
        ['Garantia', '—', '3 meses a 1 ano', 'confirmar'],
    ], 'compacta', col=[22, 22, 26, 30]) + f'''
<p class="mini">Fonte dos dados e do preço do ZLTECH: página do fabricante (Shenzhen Zhongling) no
Alibaba, consultada em 21/09/2026 {tag('ESTIMATIVA')}. A BOM de compras usava R$ 2.215,34 por motor —
{num(4 * (2215.34 - 1133.68), 2)} a mais no conjunto.</p>''')

    F.bloco(236, 20, 172, '''
<h3>Impacto calculado da troca</h3>
''' + tabela(['Grandeza', 'Com MPW86', 'Com ZLTECH'], [
        ['Massa mínima', f'{num(c["m_min"], 2)} kg', f'<b>{num(i["m_min"], 2)} kg</b>'],
        ['CG — altura', f'{num(c["zcg"], 1)} mm', f'<b>{num(i["zcg"], 1)} mm</b>'],
        ['Tombamento estático', f'{num(c["tomb"], 1)}°', f'<b>{num(i["tomb"], 1)}°</b>'],
        ['Envelope (fórmula 6.1)', f'{num(M.envelope_estabilidade(c["zcg"]), 1)}°',
         f'<b>{num(i["envelope"], 1)}°</b>'],
        ['Torque por roda a 13°', f'{num(c["torque13"], 1)} N·m', f'{num(i["torque13"], 1)} N·m'],
        ['Carga por roda (máx.)', f'{num(c["m_max"] / 4, 1)} kg', f'{num(i["carga_roda"], 1)} kg'],
        ['Margem de 15 % restante', f'{num(c["margem"], 2)} kg', f'<b>{num(i["margem"], 2)} kg</b>'],
    ], 'compacta', col=[42, 29, 29]) + '''
<p><b>O motor pesado abaixa o CG.</b> Os 16 kg entram em Z 100, bem abaixo do centro de gravidade: a
estabilidade <i>melhora</i> — o tombamento sobe quase 3° e o envelope, 2,6°. Torque e carga por roda
seguem com folga larga.</p>
<p class="mini"><b>O preço é a massa.</b> O rover passa de 96,3 para 112,3 kg e estoura em 14,5 kg a
margem de 15 % da baseline. A autonomia em terreno plano cai na mesma proporção do aumento de massa:
de 27,5 h para cerca de 23,6 h, em primeira ordem. Isso precisa entrar na Rev F.</p>''', h=138)

    F.bloco(236, 164, 172, f'''
<h3>O que ainda falta — e o que já melhora</h3>
<p><b>Falta para desenhar o suporte:</b> diâmetro, comprimento e rosca do eixo; largura da roda;
distância da face de montagem ao centro; massa e comprimento da versão <b>com freio EMB</b>.
{tag('A VALIDAR')}</p>
<p><b>Já dá para dizer que simplifica:</b> com montagem por eixo, a chapa S-02 perde o bore Ø88
usinado e os 7 furos no PCD 95 — vira uma placa com um furo e porca. Menos usinagem, menos risco de
erro de furação, peça mais barata.</p>
<p><b>Peça ao fornecedor:</b> “desenho dimensional 2D/3D do ZLLG80ASM800 <b>com freio
eletromagnético</b>, informando diâmetro e comprimento do eixo, largura da roda e massa”.</p>
<p class="mini">O modelo já está parametrizado por motor: chegando o desenho, o suporte e as folhas 07
e 14 se refazem numa revisão. Até lá o caderno segue desenhado para o MPW86, a única interface
confirmada.</p>''', h=68)
    return F


FOLHAS_B = [f17, f18, f19, f20, f21, f22, f23, f24, f25, f26, f27]
