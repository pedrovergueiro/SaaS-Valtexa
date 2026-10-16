"""Folhas 17 a 25 — Parte B (interfaces) e Parte C (fechamento) do caderno VTX-RV4-CG-E.

Mesmas regras de layout da Parte A (ver cabeçalho de folhas.py): área útil X 25→413, Y 7→290;
legenda em X ≥ 235, Y ≥ 238; blocos de texto à direita de X 235 terminam antes de Y 238.
"""
import math

import modelo as M
from modelo import (quadro, base_mastro, mastro, suportes_camera, retencao_bateria, bandejas, estop,
                    chapa_fundo, gaiola, carenagens, bateria_ref, conjunto, ITENS, GRUPOS, consolidado,
                    TABELA_51, YQ, XQ, Z_QUADRO, Z_DECK, Z_G2, Z_TAMPA, Y_MASTRO, Z_REF_M, D_ESTOP,
                    CAMERAS_Z, Z_TOTAL, X_ESTOP, MALHA_MONTAGEM, BATERIA, E_CHAPA,
                    suporte_gnss, gnss_ref, berco_imu, visao_raiz, suporte_led,
                    interfaces_sensores, lidar_ref, rodas, X_GNSS, Z_GNSS, D_ANTENA, H_ANTENA,
                    X_IMU, Z_IMU, JANELA_RAIZ, Y_LED, Z_LED, D_LED, Z_BASE_LIDAR, X_LIDAR)
from desenho import (Vista, desenha, desenha_corte, desenha_iso, cota_h, cota_v, cota_vista_h,
                     cota_vista_v, chamada, balao, linha_centro, cruz_centro, rotulo, num, dec,
                     simbolo_solda, T)
from folhas import (esc, vista_no_retangulo, desenha_oculto, Folha, tag, tabela, kg, lista_corte, recorta_caixa, solo, iso_no_retangulo,
                    _plano)

Z_LUVA = M.Z_LUVA
D = 8.0


def _lado(pecas, sinal=1):
    """Só as peças do lado +Y (ou −Y): nas vistas do mastro as duas se sobrepõem."""
    return [p for p in pecas if p.centro()[1] * sinal > 0]


_MOD = None


def _modular():
    """O módulo de cálculo da interface modular, carregado uma vez."""
    global _MOD
    if _MOD is None:
        import importlib.util
        import pathlib as _pl
        cam = _pl.Path(__file__).resolve().parent.parent / 'revisao-h' / 'modular.py'
        esp = importlib.util.spec_from_file_location('modular_h', cam)
        mod = importlib.util.module_from_spec(esp)
        esp.loader.exec_module(mod)
        _MOD = mod
    return _MOD


_MAST = None


def _mastro():
    """O módulo de cálculo do mastro (frequência, margem, cabos), carregado uma vez."""
    global _MAST
    if _MAST is None:
        import importlib.util
        import pathlib as _pl
        cam = _pl.Path(__file__).resolve().parent.parent / 'revisao-h' / 'mastro.py'
        esp = importlib.util.spec_from_file_location('mastro_h', cam)
        mod = importlib.util.module_from_spec(esp)
        esp.loader.exec_module(mod)
        _MAST = mod
    return _MAST


# ======================================================================== F17
def f17():
    F = Folha(17, escala='1:2', material=f'{M.OP.MAT_FOLHA_17} · luva Ø{num(M.D_LUVA, 0)}×{num(M.E_LUVA, 0)} · chapa {num(M.E_REF_M, 0)}')
    MA = _mastro()
    m_base = MA.GALHO_N * (Z_TOTAL - M.Z_REF_M[1]) / 1000.0        # N·m
    k_m = m_base / 71.8                                              # a conta anterior: 50 N × 1436 mm
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
    chamada(F.s, *vf.P((0, Y_MASTRO + 17, 480)), 174, 48, ['M-01 luva do mastro', f'Ø{num(M.D_LUVA, 0)}×{num(M.E_LUVA, 0)} × {num(M.L_LUVA, 0)}'], lado=1)
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
    rotulo(F.s, 270, 76, 'VISTA SUPERIOR', '1:2', f'luva Ø{num(M.D_LUVA, 0)} · furo Ø{num(M.D_MASTRO, 0)} H8')
    simbolo_solda(F.s, *vf.P((0, 260, Z_REF_M[1])), 150, 160, a='a3', cauda='reforço–longarina', comp=20)
    simbolo_solda(F.s, *vf.P((0, Y_MASTRO + 17, Z_REF_M[1] + 3)), 150, 176, a='a4', cauda='luva–reforço',
                  comp=20)

    F.bloco(26, 190, 198, f'''
<h3>Base do mastro — o que é e onde fica</h3>
<ol class="notas">
<li>Conjunto soldado ao anel superior do quadro, no vão entre os dois módulos da gaiola (X −30 → +30), um de
cada lado: <b>X 0 · Y ±{num(Y_MASTRO)}</b> {tag('NOVO')}.</li>
<li>A baseline usa ±300. Com a luva Ø{num(M.D_LUVA, 0)} o eixo recua para ±{num(Y_MASTRO, 0)}: a luva alcança |Y| {num(MA.ALCANCE_LUVA_MAX, 0)} e o envelope externo é 600. {tag('CALC')}</li>
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
<p>Momento na base com o galho de projeto ({num(MA.GALHO_N, 0)} N no topo do mastro, braço de
{num(Z_TOTAL - M.Z_REF_M[1], 0)} mm): <b>{dec(m_base, 0)} N·m</b>.</p>
<ul>
<li>Solda circular luva → reforço, a4 em Ø{num(M.D_LUVA, 0)}: W ≈ 5,5 × 10³ mm³ → <b>σ ≈ {dec(13 * k_m, 0)} MPa</b> {tag('CALC')}</li>
<li>Solda reforço → longarina, a3 em 56 × 40: <b>σ ≈ {dec(28 * k_m, 0)} MPa</b> {tag('CALC')}</li>
<li>Torção da longarina até as travessas: <b>τ ≈ {dec(12 * k_m, 0)} MPa</b>, giro ≈ {dec(0.6 * k_m, 1)}°, que soma
~{dec(16 * k_m, 0)} mm de deslocamento no topo do mastro</li>
</ul>
<p class="mini">Contas de ordem de grandeza, com a ZTA do 6061-T6 a 110 MPa {tag('HIPÓTESE')}. São as contas da
versão anterior (50 N, 72 N·m) <b>escaladas por {dec(k_m, 2)}</b>, a razão dos momentos — a geometria das soldas não mudou.
Entram no FEA como caso de carga 6 (folha 25), junto com a vibração do mastro.</p>
<h3>Montagem</h3>
<ol class="notas">
<li>Soldar M-02 na longarina, em gabarito, com o furo central na posição.</li>
<li>Soldar M-01 no reforço, aprumada (0,3 mm em 180).</li>
<li>Furar as travas em X depois da solda, com a haste montada.</li>
</ol>''', h=212)
    return F


# ======================================================================== F18
def f18():
    MA, MD = _mastro(), _modular()
    F = Folha(18, escala='1:8',
              material=f'Al 6061-T6 · tubo Ø{num(M.D_MASTRO, 0)}×{num(M.E_MASTRO, 0)} · bainha UHMW-PE')
    ctx = [p.como('ctx') for p in conjunto('A') if p.estilo == 'solid']
    todos = ctx + M.mastro_completo((1,)) + M.antena_mastro_ref(1)
    vf = vista_no_retangulo(todos, 'frontal', 30, 24, 134, 262)
    desenha(F.s, vf, todos)
    for s_ in (1, -1):
        linha_centro(F.s, *vf.P((0, s_ * Y_MASTRO, Z_DECK)),
                     *vf.P((0, s_ * Y_MASTRO, M.Z_BASE_ANTENA + M.H_ANTENA + 30)))
    # o mastro da antena (+Y) fica de um lado; os rótulos vão para fora dele
    xa, xb = vf.P((0, Y_MASTRO, 0))[0], vf.P((0, -Y_MASTRO, 0))[0]
    dir_ = 1 if xa > xb else -1
    x_lab = xa + dir_ * 13
    anc = 'start' if dir_ == 1 else 'end'
    postos = [(M.Z_BASE_ANTENA, 'antena'), (M.CAMERAS_Z[2], 'OAK-D'), (M.Z_TERMICA[1], 'térmica'),
              (M.CAMERAS_Z[1], 'OAK-D'), (M.Z_TERMICA[0], 'térmica'), (M.CAMERAS_Z[0], 'OAK-D')]
    for z, nome in postos:
        y = vf.P((0, 0, z))[1]
        F.s.ln(xa + dir_ * 4, y, x_lab - dir_ * 1, y, 'dim')
        F.s.tx(x_lab, y + 1.2, f'Z {num(z, 0)} · {nome}', T, a=anc)
    # cadeia de cotas: do deck ao topo da antena, trecho a trecho
    x_d = x_lab + dir_ * (36 if dir_ == 1 else 36)
    zs = [Z_DECK, M.CAMERAS_Z[0], M.Z_TERMICA[0], M.CAMERAS_Z[1], M.Z_TERMICA[1], M.CAMERAS_Z[2], Z_TOTAL,
          M.Z_BASE_ANTENA + M.H_ANTENA]
    for a_, b_ in zip(zs[:-1], zs[1:]):
        cota_v(F.s, vf.P((0, 0, a_))[1], vf.P((0, 0, b_))[1], x_d, None, None, valor=b_ - a_)
    cota_v(F.s, vf.P((0, 0, Z_DECK))[1], vf.P((0, 0, zs[-1]))[1], x_d + dir_ * D, None, None,
           valor=zs[-1] - Z_DECK)
    cota_vista_h(F.s, vf, (0, -Y_MASTRO, zs[-1]), (0, Y_MASTRO, zs[-1]),
                 vf.P((0, 0, zs[-1]))[1] - 6)
    rotulo(F.s, (xa + xb) / 2, 276, 'ELEVAÇÃO DOS MASTROS', esc(vf),
           'vista de +X · chassi em traço fino · antena em linha tracejada')

    # ---- cobertura: seção transversal da rua, 1:20
    d_trab = 550.0 - Y_MASTRO
    fov_v = MD.FOV_V_DEG
    meia = d_trab * math.tan(math.radians(fov_v / 2))
    meia110 = d_trab * math.tan(math.radians(55))
    x0, yg, k = 226.0, 232.0, 1 / 20

    def PZ(dy, z):
        return (x0 + dy * k, yg - z * k)

    solo(F.s, 208, 270, yg)
    F.s.rect(*PZ(-290, 400), *PZ(20, 250), 'ctx')
    F.s.ln(*PZ(0, 250), *PZ(0, Z_TOTAL), 'vis')
    F.s.aneis([[PZ(270, 150), PZ(700, 150), PZ(700, 2400), PZ(270, 2400)]], 'ref')
    F.s.tx(*PZ(720, 2000), 'copa', T, a='start', c='tx sec')
    for z in M.CAMERAS_Z:
        c = PZ(0, z)
        F.s.circ(c[0], c[1], 0.9, 'arr')
        for sinal in (1, -1):
            F.s.ln(c[0], c[1], *PZ(d_trab, z + sinal * meia), 'raio')
    cota_h(F.s, *[PZ(v, 0)[0] for v in (0, d_trab)], yg - 3.5, yg, yg, valor=d_trab)
    rotulo(F.s, x0 + 12, 86, 'COBERTURA VERTICAL', '1:20', f'OAK-D · campo vertical {num(fov_v, 0)}°')

    cob = [[f'{i + 1}º', num(z), f'{num(z - meia, 0)} → {num(z + meia, 0)}',
            f'{num(z - meia110, 0)} → {num(z + meia110, 0)}'] for i, z in enumerate(M.CAMERAS_Z)]
    lacunas = [(M.CAMERAS_Z[i] + meia, M.CAMERAS_Z[i + 1] - meia) for i in range(2)]
    oc = MA.ocupacao_cabos()
    v = MA.veredito()
    F.bloco(208, 20, 98, f'''
<h3>Os postos de cada mastro</h3>
''' + tabela(['Posto', 'Z (mm)', 'Estado'], [
        ['Antena GNSS', f'{num(M.Z_BASE_ANTENA, 0)} base', 'provisão T-10'],
        ['OAK-D', num(M.CAMERAS_Z[2], 0), 'fixa, calibrada'],
        ['Térmica', num(M.Z_TERMICA[1], 0), '<b>removível</b>'],
        ['OAK-D', num(M.CAMERAS_Z[1], 0), 'fixa, calibrada'],
        ['Térmica', num(M.Z_TERMICA[0], 0), '<b>removível</b>'],
        ['OAK-D', num(M.CAMERAS_Z[0], 0), 'fixa, sobre a luva'],
    ], 'micro', col=[30, 28, 42]) + f'''
<p class="mini">Alturas <b>nominais</b>: a braçadeira desliza em todo o mastro (folha 19). Dois mastros:
6 OAK-D, até 4 térmicas e até 2 antenas. Térmica sai com a mão (folha 41).</p>''')
    F.bloco(312, 20, 96, f'''
<h3>Haste, bainha e cabos</h3>
<ol class="notas">
<li><b>M-10</b>: tubo Ø{num(M.D_MASTRO, 0)}×{num(M.E_MASTRO, 0)}, {num(Z_TOTAL - M.Z_REF_M[1], 0)} mm, apoiado no reforço e travado na luva.</li>
<li><b>M-11</b>: bainha Ø{num(M.D_BAINHA, 0)}/Ø{num(M.D_MASTRO, 0)} em {len(M._faixas_bainha())} trechos, parada 40 mm
antes e depois de cada posto — a braçadeira aperta o tubo, não o plástico.</li>
<li><b>M-12</b>: ponta cônica; <b>sai</b> quando a antena entra.</li>
<li><b>T-10</b>: adaptador da antena, Ø{num(M.D_ENCAIXE_ANTENA, 0)} × {num(M.L_ENCAIXE_ANTENA + M.H_TOPO_ANTENA, 0)},
entra {num(M.L_ENCAIXE_ANTENA, 0)} no tubo; furo Ø{num(M.D_CABO_ANTENA, 0)} para o cabo. Rosca {tag('A VALIDAR')}.</li>
<li>Cabos <b>por dentro do tubo</b>, entrada Ø12 com passa-cabo 30 mm abaixo de cada posto, saída lateral Ø20 na
luva. Ocupação do furo <b>{dec(oc['ocupacao'] * 100, 0)} %</b> (limite {dec(oc['limite'] * 100, 0)} %) com cabo de
Ø{num(oc['d_cabo_mm'], 0)} {tag('ESTIMATIVA')} — P-40.</li>
</ol>''')
    F.bloco(276, 138, 132, f'''
<h3>Cobertura vertical da copa</h3>
<p>Copa a <b>{num(d_trab)} mm</b> do eixo do mastro {tag('CALC')}. O campo vertical da OAK-D Pro W é o
divulgado, <b>{num(fov_v, 0)}°</b> {tag('A VALIDAR')} (P-35) — e não os 110° que o V3 tomava de premissa.</p>
''' + tabela(['Andar', 'Z (mm)', f'{num(fov_v, 0)}° (divulgado)', '110° (premissa V3)'], cob, 'micro',
             col=[14, 16, 35, 35]) + f'''
<p><b>Com {num(fov_v, 0)}° os três andares deixam faixas sem cobertura:</b> {num(lacunas[0][0], 0)} → {num(lacunas[0][1], 0)} mm e
{num(lacunas[1][0], 0)} → {num(lacunas[1][1], 0)} mm. Com 110° elas se sobrepunham. As térmicas <b>não</b> preenchem essa
faixa: são outro sensor. Se a cobertura contínua é requisito, é decisão de projeto — mais um andar, ou câmera
girada 90° — e não se resolve em desenho (P-35).</p>
<h3>Dinâmica do mastro cheio</h3>
<p>1ª frequência <b>{dec(v['freq_mastro_Hz'], 2)} Hz</b> (requisito {MA.REQUISITO_FREQ_HZ} Hz); a margem contra o terreno
<b>não fecha</b> a {MA.VELOCIDADE_MS} m/s (razão {dec(v['razao'], 2)}). Folha 36.</p>''')
    return F


# ======================================================================== F19
def f19():
    F = Folha(19, escala='1:1', material='T-01/T-02/T-03 Al 6061-T6 · T-05 UHMW-PE',
              tolerancia='ISO 2768-mK · pinos ISO 286 H7/h6')
    MD = _modular()
    z = CAMERAS_Z[2]
    posto = _lado([p for p in suportes_camera()
                   if abs(p.centro()[2] - z) < 60])

    # ---- vista da face VMS, de fora
    vp = vista_no_retangulo(posto, 'lateral_e', 40, 28, 134, 128)
    desenha(F.s, vp, posto)
    c = vp.P((0, Y_MASTRO, z))
    cruz_centro(F.s, c[0], c[1], 10)
    yb = vp.P((0, 0, z - M.VMS_PRATO[1] / 2))[1]
    a, b = vp.P((-M.VMS_FUROS[0] / 2, 0, 0)), vp.P((M.VMS_FUROS[0] / 2, 0, 0))
    cota_h(F.s, a[0], b[0], yb + 8, None, None, valor=M.VMS_FUROS[0])
    a, b = vp.P((-M.VMS_PRATO[0] / 2, 0, 0)), vp.P((M.VMS_PRATO[0] / 2, 0, 0))
    cota_h(F.s, a[0], b[0], yb + 16, None, None, valor=M.VMS_PRATO[0])
    xd = min(a[0], b[0]) - 8
    a, b = vp.P((0, 0, z - M.VMS_FUROS[1] / 2)), vp.P((0, 0, z + M.VMS_FUROS[1] / 2))
    cota_v(F.s, a[1], b[1], xd, None, None, valor=M.VMS_FUROS[1])
    a, b = vp.P((0, 0, z)), vp.P((0, 0, z + M.Z_PINO_GIRO))
    cota_v(F.s, a[1], b[1], xd - D, None, None, valor=M.Z_PINO_GIRO, lado_txt=-1)
    chamada(F.s, *vp.P((0, Y_MASTRO, z)), 144, 142,
            [f'Ø{num(M.D_PINO_REF, 0)} H7 — PINO DE REFERÊNCIA',
             'é ele que preserva a calibração'], lado=1)
    chamada(F.s, *vp.P((0, Y_MASTRO, z + M.Z_PINO_GIRO)), 144, 162,
            [f'Ø{num(M.D_PINO_GIRO, 0)} H7 — pino anti-giro'], lado=1)
    rotulo(F.s, 86, yb + 32, 'FACE VMS-60 — VISTA DE FORA', esc(vp),
           'o padrão que não muda quando o sensor muda')

    # ---- corte horizontal: as três camadas (T-05 fica ACIMA do plano de corte: vai tracejado)
    pecas = _lado([p for p in mastro() + suportes_camera()
                   if p.bbox()[2][0] <= z <= p.bbox()[2][1]])
    acima = _lado([p for p in suportes_camera() if p.item == 'T-05' and abs(p.centro()[2] - z) < 60])
    vs = vista_no_retangulo(pecas + acima, 'superior', 150, 30, 232, 98)
    desenha_corte(F.s, vs, pecas, 'z', z)
    desenha_oculto(F.s, vs, acima)
    cc = vs.P((0, Y_MASTRO, 0))
    cruz_centro(F.s, *cc, 14)
    for cod, p, (dx, dy) in (
            ('T-01', (0, Y_MASTRO + M.D_MASTRO / 2 + 6, 0), (-16, 10)),
            ('T-02', (0, Y_MASTRO + M.D_MASTRO / 2 + M.E_BRACADEIRA + 5, 0), (14, 8)),
            ('T-03', (0, Y_MASTRO + M.D_MASTRO / 2 + M.E_BRACADEIRA
                      + M.E_PRATO_VMS + 3, 0), (18, -2)),
            ('T-05', (30, Y_MASTRO + M.D_MASTRO / 2 + M.E_BRACADEIRA
                      + M.E_PRATO_VMS + M.E_ADAPTADOR + 20, 0), (16, -12))):
        q = vs.P(p)
        balao(F.s, q[0] + dx, q[1] + dy, cod, alvo=q)
    rotulo(F.s, 192, 112, f'AS TRÊS CAMADAS — CORTE EM Z {num(z)}', esc(vs),
           'posição · interface · adaptação')

    # ---- índice de inclinação
    cx, cy, k = 72.0, 228.0, 1.0
    F.s.circ(cx, cy, M.R_INDICE * k, 'cl')
    linha_centro(F.s, cx - 42, cy, cx + 42, cy)
    linha_centro(F.s, cx, cy - 42, cx, cy + 42)
    for i in range(M.N_INDICE):
        a_ = math.radians((-(M.N_INDICE - 1) / 2 + i) * M.PASSO_INDICE_DEG)
        px, py = cx + M.R_INDICE * k * math.sin(a_), cy - M.R_INDICE * k * math.cos(a_)
        F.s.circ(px, py, M.D_PINO_GIRO / 2 * k, 'vis')
    F.s.circ(cx, cy, 4.25 * k, 'vis')
    chamada(F.s, cx, cy - M.R_INDICE * k, 118, 202,
            [f'{M.N_INDICE} furos Ø{num(M.D_PINO_GIRO, 0)} H7, passo '
             f'{num(M.PASSO_INDICE_DEG, 0)}°',
             f'inclinação de −{num((M.N_INDICE - 1) / 2 * M.PASSO_INDICE_DEG, 0)}° a '
             f'+{num((M.N_INDICE - 1) / 2 * M.PASSO_INDICE_DEG, 0)}°'], lado=1)
    chamada(F.s, cx + 4.25, cy, 118, 246, ['M8 central — eixo do índice'], lado=1)
    rotulo(F.s, cx, 278, 'ÍNDICE DE INCLINAÇÃO', '1:1', 'repetível: é pino, não atrito')

    rep = MD.repetibilidade()
    pr = MD.passa_sem_recalibrar()
    pt = MD.protecao()
    F.bloco(236, 24, 172, f'''
<h3>Posto de sensor VMS-60</h3>
<p>Substitui a chapa M-20 do V3, que era furação fixa, em cota fixa, com o padrão da
câmera marcado "a validar" no próprio código. {tag('NOVO')}</p>
<p><b>O que separa removível de modular</b> é poder repor o sensor no MESMO lugar. A fusão
usa a matriz extrínseca de cada câmera como constante; se a troca desloca a próxima em 1°,
a calibração morre junto com a peça trocada — e quem trocou não tem como saber.</p>
{tabela(['Interface', 'Erro angular', 'A 10 m'], [
    [f'Pino Ø{num(M.D_PINO_REF, 0)} H7/h6 + anti-giro a {num(M.Z_PINO_GIRO, 0)} mm',
     f'<b>{dec(rep["com_pino_deg"], 3)}°</b>', f'<b>{dec(rep["erro_com_pino_a_10m_mm"], 1)} mm</b>'],
    ['Só parafuso M5 em furo Ø5,5', f'{dec(rep["sem_pino_deg"], 2)}°',
     f'{dec(rep["erro_sem_pino_a_10m_mm"], 0)} mm'],
], col=[52, 24, 24])}
<p>Fator <b>{dec(rep["fator"], 0)}×</b>. O limite para trocar sem recalibrar é
{dec(pr["limite_deg"], 1)}°: com pino passa com margem {dec(pr["margem"], 1)}×, sem pino não passa.
{tag('CALC')}</p>
<h3>As três camadas</h3>
{tabela(['Camada', 'Peça', 'O que define', 'Mexer nela exige'], [
    ['1 · posição', 'T-01 braçadeira', 'altura e azimute no mastro',
     '<b>recalibrar</b> a extrínseca'],
    ['2 · interface', 'T-02 prato VMS', 'os pinos e a inclinação indexada',
     'recalibrar só se mudar o índice'],
    ['3 · adaptação', 'T-03 adaptador', 'a furação daquele modelo de sensor',
     '<b>nada</b> — é a troca de campo'],
], col=[18, 20, 32, 30])}
<p>Trocar a câmera mexe só na camada 3. <b>Não tocar na braçadeira</b> é a regra que
protege a calibração, e é a primeira linha do procedimento da folha 40.</p>''')

    F.bloco(236, 150, 172, f'''
<h3>Proteção sem nada na frente da lente</h3>
<p>Com {dec(MD.FOV_H_DEG, 0)}° de campo horizontal {tag('A VALIDAR')}, qualquer peça a
{dec(pt["avanco_mm"], 0)} mm à frente da lente teria de estar a
<b>{dec(pt["lateral_necessaria_mm"], 0)} mm</b> do eixo para não aparecer na imagem. O prato
tem {dec(pt["meia_largura_do_prato_mm"], 0)} mm de meia-largura. <b>Lateralmente não cabe, e é
por isso que o projeto não tem grade, aro nem defletor.</b></p>
<p>Verticalmente cabe: {dec(pt["avanco_mm"], 0)} mm à frente exigem
{dec(pt["vertical_necessaria_mm"], 0)} mm acima, e o protetor T-05 tem
{dec(pt["altura_do_protetor_mm"], 0)} — {dec(pt["folga_vertical_mm"], 0)} mm de folga. Daí a
<b>sobrancelha</b>: protege de cima e do canto externo, e some do enquadramento.</p>
<ol class="notas">
<li>T-05 é <b>sacrificial</b>: UHMW-PE, 2 parafusos M4, troca em campo. Rompe antes do
adaptador — ensaio V-13.</li>
<li>A lente fica recuada {num(M.E_ADAPTADOR, 0)} mm atrás da face do adaptador.</li>
<li>Montagem <b>rígida</b>, sem coxim. Isolar a câmera trocaria borrão de movimento por
deriva de calibração — ver folha 39 e <code>revisao-h/mastro.py</code>.</li>
<li>O projeto <b>não declara grau IP</b> do posto: grau IP é resultado de ensaio em
conjunto fechado, não propriedade de conector. Ensaio V-11.</li>
</ol>''')
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
    F = Folha(21, escala='1:5 · 1:1', material='E-01/E-02 Al 5052 e2 · E-10/E-11 Al 6061')
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
    p5 = [p for p in suportes_camera() + mastro()
          if p.centro()[1] > 0 and p.bbox()[2][0] <= CAMERAS_Z[2] <= p.bbox()[2][1]]
    desenha_corte(F.s, v5, p5, 'z', CAMERAS_Z[2])
    cota_vista_h(F.s, v5, (-25.0, 300, 0), (45.0, 300, 0), 116, txt='70')
    rotulo(F.s, 190, 182, 'D5 · POSTO VMS, CORTE EM Z 1540', '1:2', 'sobrancelha T-05 · folha 19')

    # --- D6: onde fica cada interface
    pi = [p for p in conjunto('AB') if p.estilo == 'solid'] + [r.como('ref') for r in rodas()]
    cam = iso_no_retangulo(pi, 292, 72, 408, 144, 9.6, az=-128, el=26)
    desenha_iso(F.s, cam, pi)
    for cod, p, (dx, dy) in (('N-01', (X_GNSS, 0, 403), (-13, -5)), ('N-02', (X_IMU, 0, 310), (24, 2)),
                             ('N-04', (430, 0, 250), (-6, 13)), ('N-08', (XQ, Y_LED, Z_LED), (16, -4)),
                             ('T-05', (0, 330, CAMERAS_Z[1]), (-13, 0))):
        q = cam.P(p)
        balao(F.s, q[0] + dx, q[1] + dy, cod, alvo=q)
    rotulo(F.s, 350, 150, 'D6 · LOCALIZAÇÃO')

    F.bloco(26, 196, 198, f'''
<h3>O que cada interface resolve</h3>
<ol class="notas">
<li><b>N-01 · antena GNSS</b> {tag('NOVO')} — a baseline põe a antena em X 0 · Z 390, que fica <b>sob a tampa
de alumínio</b> e dentro da gaiola: sem visão de céu. Aqui ela sobe para fora, em X {num(X_GNSS)}, com o plano
de terra em Z {num(Z_GNSS[1], 1)}. <b>Alternativa:</b> a antena no topo do mastro (adaptador T-10, folha 18), como
no esboço do projeto — as duas têm provisão e a escolha é a pendência P-36.</li>
<li><b>N-02/N-03 · berço do IMU</b> {tag('NOVO')} — face usinada em Z {num(Z_IMU)} (altura da baseline),
arestas alinhadas a X e Y, com 0,5° de tolerância angular. Offset ao CG: X +{num(X_IMU)} mm, a informar ao
software.</li>
<li><b>N-04 a N-07 · câmera de zona de raiz</b> {tag('NOVO')} — a baseline a coloca em Z 150, <b>abaixo do
chassi</b>, onde ela viraria o ponto mais baixo do rover. Aqui ela fica dentro, olhando o solo por uma janela
de policarbonato protegida por duas barras; nada desce abaixo da chapa.</li>
<li><b>N-08 · faróis</b> {tag('NOVO')} — Ø{num(D_LED)} na carenagem frontal, na única faixa livre entre o anel
superior do quadro (Z 340) e o trilho da gaiola (Z 377).</li>
<li><b>T-05 · protetor sacrificial</b> {tag('NOVO')} — substitui a carenagem N-09 do V3, uma caixa com nariz
dimensionada por semelhança. A sobrancelha T-05 sai do campo de visão: 6 peças nos postos de OAK-D, mais 4 se os módulos
térmicos forem montados. As câmeras de extremidade ficam sob o chassi, protegidas pela chapa de fundo (folha 38).</li>
</ol>''')
    lc = lista_corte('B')
    linhas = [[f'<b>{i}</b>', ITENS[i]['nome'], ITENS[i]['desc'], str(d['qtd']), kg(d['massa'], 2)]
              for i, d in lc.items() if i.startswith('N')]
    linhas.append(['', '', '<b>Subtotal do grupo N</b>', '',
                   f'<b>{kg(sum(d["massa"] for i, d in lc.items() if i.startswith("N")), 2)}</b>'])
    F.bloco(236, 156, 172, '<h3>Lista de materiais — grupo N</h3>' +
            tabela(['Item', 'Peça', 'Formato', 'Qtd', 'kg'], linhas, 'corte bom', col=[10, 30, 38, 8, 14]) +
            f'<p class="mini">Largura do envelope: <b>{num(2 * M.envelope()[1][1], 0)} mm</b> {tag("CALC")} (o V3 chegava a '
            f'674 com as carenagens N-09). Sombra da antena no LiDAR ≈ 6° {tag("ESTIMATIVA")} — ensaio 1, folha 26.</p>', h=76)
    return F


# ======================================================================== F23
def f23():
    F = Folha(23, material='—')
    MA = _mastro()
    vp = MA.veredito()
    linhas = [
        ['1', 'Base dos mastros',
         f'Desenhada nas folhas 17 e 36: haste Ø{num(M.D_MASTRO, 0)}×{num(M.E_MASTRO, 0)}, luva '
         f'Ø{num(M.D_LUVA, 0)}×{num(M.E_LUVA, 0)}, eixo em Y ±{num(Y_MASTRO, 0)}. Falta aprovar a posição e a solda.',
         'Eng. mecânico', 'Parecer + caso 6 do FEA com o mastro cheio'],
        ['2', 'Postos de sensor',
         'Posto VMS-60 desenhado (folhas 19, 37, 41); falta a furação real da OAK-D (P-06) e da térmica (P-30).',
         'Integração de sensores', 'Desenho do fabricante da OAK-D e da térmica'],
        ['3', 'Interface MPW86', 'Orientação dos 7 furos, folga da face, freio e encoder.',
         'Compras / ElectroCraft', 'Desenho 2D/3D do fabricante'],
        ['4', 'Suspensão pneumática',
         'Desenhada (folhas 07, 28 a 31). Falta o modelo do fole W-15 (P-20), da bucha (P-21) e o FEA de fadiga (caso 9).',
         'Eng. mecânico', 'Fichas técnicas + FEA do caso 9'],
        ['5', 'Caixa da bateria', 'Dimensões e furação das 16 células; posição dos batentes (folha 20).',
         'Eng. elétrica', 'Desenho da caixa'],
        ['6', 'Eletrônica e E-STOP', 'Arranjo dos componentes sobre as zonas e bandejas (folha 21).',
         'Eng. eletrônica', 'Layout aprovado sobre a folha 21'],
        ['7', 'Solda do 6061-T6', 'Definir a condição de cálculo: como soldado ou novo T6 (folha 25).',
         'Eng. mecânico', 'Folha 25 assinada'],
        ['8', 'FEA e fadiga', 'Rodar os 9 casos de carga da folha 25 com a geometria deste caderno.',
         'Eng. mecânico ou terceiro', 'Relatório com margem por caso'],
        ['9', 'Massa oficial', 'Resolver 85,04 × 82,49 kg e aceitar ou reduzir a massa (folha 24).',
         'Eng. + gestão', 'Número único na baseline'],
        ['10', 'Diagonais do quadro', 'Decidir se entram; opções e custo de massa na folha 25.',
         'Eng. mecânico', 'Decisão + FEA de torção'],
        ['11', 'Campo de visão do LiDAR', 'Confirmar o centro óptico do Mid-360 e a ausência de obstrução.',
         'Sensores', 'Ensaio 1 da folha 26'],
        ['12', 'Câmeras de extremidade',
         f'Frontal e traseira (T-06) sob o chassi, Z {num(M.Z_CAM_EXTREMIDADE, 0)} (folha 38): confirmar o enquadramento.',
         'Sensores', 'Ensaio 2 da folha 26'],
        ['13', 'Vão livre', 'Definir a cota oficial e onde ela é medida (proposta na folha 26).',
         'Eng. mecânico', 'Valor único na baseline'],
        ['14', 'Freio do MPW86', 'Torque de retenção — pendência da própria baseline.', 'Compras',
         'Resposta da ElectroCraft'],
        ['15', 'Aderência do solo', 'μ real da lavoura, seco e úmido.', 'Eng. + campo',
         'Ensaio 5 da folha 26'],
        ['16', 'Câmera da zona de raiz', 'Desenhada na folha 22; falta confirmar o campo pela janela.',
         'Sensores', 'Ensaio 2 da folha 26'],
        ['17', 'Antena GNSS: onde e qual',
         f'Topo do mastro (T-10) ou tampa (N-01); massa até {dec(MA.massa_antena_maxima(), 2)} kg no mastro (P-36, P-37).',
         'Sensores + eng. mecânico', 'Ficha técnica + ensaio V-17'],
        ['18', 'IMU', 'Furação real do MTi-630 e offset ao CG declarado no software.', 'Sensores',
         'Desenho do fabricante'],
        ['19', 'Faróis', 'Modelo, potência e corrente (a baseline só dá a massa).', 'Eng. elétrica',
         'Componente escolhido'],
        ['20', 'Largura real',
         f'No V3 chegava a 674 mm com as carenagens N-09; no V4 o envelope é {num(2 * M.envelope()[1][1], 0)} mm '
         f'(luva do mastro em |Y| {num(MA.ALCANCE_LUVA_MAX, 0)}). Conferir no protótipo.',
         'Eng. + gestão', 'Medição do protótipo'],
        ['21', 'Envelope de estabilidade', 'Refazer com o CG consolidado, com o mastro cheio, e publicar um valor só.',
         'Eng. mecânico', 'Folha 24 + baseline'],
        ['22', 'Escolha do motor-roda', 'MPW86 × ZLTECH: −R$ 21.165 e +16 kg, interfaces diferentes.',
         'Eng. + gestão', 'Decisão + folha 27'],
        ['23', 'Interface do motor escolhido', 'Desenho dimensional do fabricante (eixo ou flange).',
         'Compras', 'Desenho 2D/3D'],
        ['24', 'Freio do motor escolhido', 'No ZLTECH o freio EMB é opcional — pedir na cotação.',
         'Compras', 'Proposta com freio incluso'],
        ['25', 'Módulo térmico removível',
         f'Modelo e interface (USB ou Ethernet); caber em {num(M.ENVELOPE_TERMICA[0], 0)}×{num(M.ENVELOPE_TERMICA[1], 0)}×'
         f'{num(M.ENVELOPE_TERMICA[2], 0)} e deixar livres os 4 parafusos (P-30, P-38).',
         'Sensores', 'Ficha técnica + ensaio V-16'],
        ['26', 'Switch PoE', 'Portas: 9 OAK-D + LiDAR + Jetson + satélite = 12; cada térmica Ethernet soma uma (16 com quatro) (P-31).',
         'Eng. elétrica', 'Componente escolhido'],
        ['27', 'Margem do mastro contra o terreno',
         f'Razão {dec(vp["razao"], 2)} contra {dec(vp["margem_minima"], 1)} a {MA.VELOCIDADE_MS} m/s com o mastro cheio: '
         f'medir o espectro ou limitar a marcha (P-39).',
         'Eng. mecânico', 'Ensaio V-12'],
        ['28', 'Cabos no tubo do mastro',
         f'Ocupação de {dec(MA.ocupacao_cabos()["ocupacao"] * 100, 0)} % com cabos de Ø{num(MA.D_CABO_M12_MM, 0)} estimados (P-40).',
         'Eng. elétrica', 'Cabo escolhido'],
        ['29', 'Terminal de satélite',
         f'Provisão {num(M.SAT_ENVELOPE[0], 0)}×{num(M.SAT_ENVELOPE[1], 0)}×{num(M.SAT_ENVELOPE[2], 0)}; um terminal '
         f'da classe do Starlink Mini (~300×260) não cabe (P-32).',
         'Gestão + eng. mecânico', 'Modelo escolhido'],
    ]
    F.bloco(26, 20, 382, '<h3>Plano de fechamento — o que falta para liberar a fabricação</h3>' +
            tabela(['#', 'Item', 'O que falta', 'Quem fecha', 'Critério de aceite'], linhas, 'micro',
                   col=[4, 17, 45, 15, 19]))
    F.bloco(26, 176, 198, '''
<h3>Como usar este caderno agora</h3>
<ol class="notas">
<li><b>Cotar</b> — envie a Parte A (folhas 01 a 16) e a pasta <b>dxf/</b>. É geometria fechada, com tolerâncias,
soldas e acabamento definidos; nenhum dos itens acima muda o preço.</li>
<li><b>Validar</b> — o engenheiro mecânico trabalha na folha 15 (parecer), apoiado nas folhas 22 a 25.</li>
<li><b>Fabricar</b> — só depois de fechar os itens 1 a 10 e emitir a revisão 1 das folhas afetadas.</li>
</ol>
<p class="mini">Os itens 11 a 29 correm em paralelo com a cotação: são ensaios e confirmações que não mudam a
geometria do quadro nem da gaiola.</p>''')
    F.bloco(236, 176, 172, '''
<h3>O que muda a cada decisão</h3>
<ul>
<li><b>Fole e bucha</b>: ficam como estão se fecharem a tabela da folha 07; senão muda só o prato W-08 e o berço W-11.</li>
<li><b>Caixa da bateria</b>: muda só a posição dos batentes (folha 20).</li>
<li><b>Furação da câmera</b>: muda só o adaptador T-03 ou T-04 (folhas 19 e 41) — braçadeira, prato e pinos permanecem.</li>
<li><b>Antena no mastro</b>: o adaptador T-10 já existe; antena acima do limite exige Ø32×4 (folha 36).</li>
<li><b>Novo T6 após a solda</b>: prazo, custo e ordem de furação (folhas 02 e 25).</li>
<li><b>Diagonais</b>: mudam o quadro (folhas 04 e 06), a massa e o espaço da bateria.</li>
</ul>''')
    return F


# ======================================================================== F24
def f24():
    F = Folha(24, material='—')
    c = consolidado()
    nomes = {'A · Q': 'Parte A — quadro estrutural', 'A · M': 'Parte A — base dos mastros',
             'A · C': 'Parte A — chapa de fundo e nervuras', 'A · W': 'Parte A — suspensão pneumática (grupo W)',
             'A · G': 'Parte A — gaiola de proteção', 'A · K': 'Parte A — carenagens e tampas',
             'B · M': 'Parte B — haste e bainha dos mastros', 'B · T': 'Parte B — interface modular VMS-60 (grupo T)',
             'B · B': 'Parte B — retenção da bateria',
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
        ['Largura externa', '600 mm', f'{num(2 * M.envelope()[1][1], 0)} mm (envelope; V3: 674 com as carenagens N-09)'],
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
        ['Bandejas 2 → 1,5 mm', '−0,25', 'Sem impacto'],
        ['Suprimir 1 barra G-03 por módulo', '−0,17', 'Perde apoio da tampa'],
    ]
    F.bloco(26, 152, 188, '<h3>Se for preciso reduzir massa</h3>' +
            tabela(['Ação', 'Δ kg', 'Consequência'], red, 'compacta', col=[40, 14, 46]) +
            '<p class="mini">Somadas, as três primeiras devolvem cerca de 2,3 kg. Reduzir ou re-baselinar a '
            'massa é decisão do engenheiro — as duas saídas são aceitáveis.</p>')
    F.bloco(222, 128, 186, f'''
<h3>Recomendação</h3>
<p>Adotar <b>{kg(c['m_min'], 1)} kg</b> como massa mínima oficial do rover e refazer a margem de 15 % sobre ela
(nominal ≈ {kg(c['m_min'] * 1.15, 1)} kg). Autonomia, aclive e estabilidade da baseline devem ser reprocessados
com esse número: nenhuma conclusão muda — o limite continua sendo a aderência, a 13,0° — mas os valores
publicados passam a ser coerentes entre si.</p>
<p class="mini">Ainda não está contado: cabos e conectores, a caixa real da bateria, as câmeras (OAK-D e
térmicas), a antena e o terminal de satélite — são massas estimadas ou sem modelo (P-06, P-30, P-32, P-37).
Os módulos térmicos e o adaptador de antena T-10 também ficam fora da massa da entrega.</p>''', h=104)
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
        ['5', 'Tração e frenagem', '35 N·m por roda', 'σ no braço W-01 e na chapa W-02'],
        ['6', 'Mastro cheio', f'galho de 80 N no topo, com 3 OAK-D + 2 térmicas + antena; terreno a 5,6 Hz',
         'σ na base · 1ª freq. ≥ 7,5 Hz (calculado: ver folha 36)'],
        ['7', 'Bateria', '36,5 kg × 3 g na amarração', 'σ nos batentes e na chapa'],
        ['8', 'Içamento', '2 pontos, 1,5 × massa', 'σ e definição dos pontos'],
        ['9', 'Fadiga do aço (grupo W)', 'ciclos do terreno no braço, na chapa W-02, nas orelhas e no pino',
         'categoria de detalhe de solda de aço; alumínio não tem limite de fadiga, o aço tem'],
    ]
    F.bloco(222, 20, 186, '<h3>C · Encargos para o FEA e a fadiga</h3>' +
            tabela(['#', 'Caso de carga', 'Descrição', 'Critério'], casos, 'compacta', col=[5, 22, 38, 35]) +
            '''
<p><b>Condições de contorno:</b> apoio nos 4 furos Ø88 das faces de montagem do MPW86; molas equivalentes ao
pneu (rigidez a medir) ou apoio fixo como simplificação conservadora.</p>
<p><b>Modelo:</b> casca para tubos e chapas, malha de 5 mm com refino de 2 mm em soldas e furos; soldas como
ligação rígida; 6061-T6 com ZTA de 25 mm em torno de cada cordão.</p>
<p><b>Critérios de aceite:</b> alumínio: von Mises &lt; 110 MPa na ZTA e &lt; 180 MPa fora dela; aço do grupo W: a
definir pelo engenheiro (A36, escoamento nominal 250 MPa) <b>A VALIDAR</b>; flecha do quadro &lt;
L/500 no caso 1; fadiga pelo EN 1999-1-3 para 10⁶ ciclos na categoria de detalhe aplicável; 1ª frequência do
conjunto afastada 1,5× da excitação de 5 Hz.</p>
<p><b>Entregáveis:</b> relatório com margem por caso, mapa de tensões, lista de pontos críticos e recomendações
— que voltam para este caderno como revisão 1.</p>''', h=206)
    return F


# ======================================================================== F26
def f26():
    F = Folha(26, material='—')
    ensaios = [
        ['1', 'LiDAR e antena GNSS', 'Mid-360 no G-06; antena no N-01 e depois no T-10; nuvem de 360° e RTK',
         'Sombra da antena ≤ 10° de azimute; RTK fixo em campo aberto (V-17 compara as duas posições)', 'Sensores'],
        ['2', 'Câmeras de extremidade e de raiz', 'C7 e C8 sob o chassi (T-06, Z 210); C9 pela janela N-04',
         'Lente sem obstrução pela chapa de fundo; solo enquadrado a 250 mm', 'Sensores'],
        ['3', 'Câmeras do mastro', 'Alvo padrão na linha do café, com os 3 andares montados',
         'Medir a lacuna vertical entre andares (80° de campo deixa faixas sem cobertura: P-35)', 'Sensores'],
        ['4', 'Vão livre real', 'Medir do solo ao ponto mais baixo entre rodas, com carga máxima',
         'Registrar o valor e fixar a cota oficial', 'Eng. mecânico'],
        ['5', 'Aderência do solo', 'Tração em rampa na fazenda-piloto, solo seco e úmido',
         'μ medido; confirmar ou corrigir o aclive de 13°', 'Eng. + campo'],
        ['6', 'Freio', 'Retenção em rampa de 30° com massa máxima', 'Não desliza em 10 minutos', 'Eng.'],
        ['7', 'Vibração do mastro', 'Excitar o topo e medir, com o mastro CHEIO (térmicas e antena) e em marcha',
         '1ª frequência ≥ 7,5 Hz e o espectro real contra o terreno (V-12, P-39)', 'Eng. mecânico'],
        ['8', 'Aperto e estanqueidade', 'Torquímetro em 100 % dos fixadores; jato de água na carenagem',
         'Torques da folha 13; sem entrada de água na eletrônica', 'Montagem'],
        ['9', 'Interface modular e módulo térmico', 'Ensaios V-10 a V-17 da folha 39: repetibilidade do pino, '
         'IP do posto, impacto de galho, troca em campo, módulo ausente, aperto manual, antena',
         'Repetibilidade < 0,1°; nenhum IP declarado sem ensaio', 'Sensores + eng.'],
    ]
    F.bloco(26, 20, 382, '<h3>Plano de validação — bancada e campo</h3>' +
            tabela(['#', 'Ensaio', 'Como', 'Critério de aceite', 'Responsável'], ensaios, 'compacta',
                   col=[4, 18, 33, 30, 15]) +
            '''<p class="mini">Cada ensaio fecha uma linha da folha 23. O resultado entra na revisão 1 deste
caderno e na baseline.</p>''', h=128)
    vao = tabela(['Onde se mede', 'Altura (mm)'], [
        ['Sob o quadro, entre as rodas', '250'],
        ['Ponto mais baixo entre as rodas (nervuras C-02)', '208'],
        ['Na linha das rodas — corpo do MPW86', '57'],
        ['Na linha das rodas — chapa W-02', '38'],
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
        ['Montagem', 'Flange: 7 × M4 no PCD 95', '<b>Por eixo, com porca</b>', 'simplifica a W-02'],
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
de 27,5 h para cerca de 23,6 h, em primeira ordem. Isso precisa entrar na baseline.</p>''', h=138)

    F.bloco(236, 164, 172, f'''
<h3>O que ainda falta — e o que já melhora</h3>
<p><b>Falta para desenhar o suporte:</b> diâmetro, comprimento e rosca do eixo; largura da roda;
distância da face de montagem ao centro; massa e comprimento da versão <b>com freio EMB</b>.
{tag('A VALIDAR')}</p>
<p><b>Já dá para dizer que simplifica:</b> com montagem por eixo, a chapa W-02 perde o bore Ø88
usinado e os 7 furos no PCD 95 — vira uma placa com um furo e porca. Menos usinagem, menos risco de
erro de furação, peça mais barata.</p>
<p><b>Peça ao fornecedor:</b> “desenho dimensional 2D/3D do ZLLG80ASM800 <b>com freio
eletromagnético</b>, informando diâmetro e comprimento do eixo, largura da roda e massa”.</p>
<p class="mini">O modelo já está parametrizado por motor: chegando o desenho, o suporte e as folhas 07
e 14 se refazem numa revisão. Até lá o caderno segue desenhado para o MPW86, a única interface
confirmada.</p>''', h=68)
    return F


FOLHAS_B = [f17, f18, f19, f20, f21, f22, f23, f24, f25, f26, f27]
