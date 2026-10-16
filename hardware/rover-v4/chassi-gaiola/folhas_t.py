"""Folhas 36 a 40: o que o V4 acrescentou — mastro, usinagem VMS e módulos de sensor.

A folha 19 mostra o posto de sensor montado. Estas cinco respondem o resto do pedido do
V4: por que o mastro engrossou, como se usina a interface, onde estão as nove câmeras, como
se troca uma em campo e o que a provisão de satélite realmente aceita.

Nenhum número é digitado aqui: tudo vem de `revisao-h/mastro.py` e `revisao-h/modular.py`.
"""
import math

import modelo as M
from folhas import (D, Folha, desenha_oculto, esc, iso_no_retangulo, recorta_caixa,
                    so, tabela, tag, vista_no_retangulo)
from folhas_b import _modular
from desenho import (Vista, balao, chamada, cota_h, cota_v, cruz_centro, desenha,
                     desenha_iso, linha_centro, num, dec, rotulo, T)

_MAST = None


def _mastro_mod():
    global _MAST
    if _MAST is None:
        import importlib.util
        import pathlib
        cam = pathlib.Path(__file__).resolve().parent.parent / 'revisao-h' / 'mastro.py'
        esp = importlib.util.spec_from_file_location('mastro_h', cam)
        mod = importlib.util.module_from_spec(esp)
        esp.loader.exec_module(mod)
        _MAST = mod
    return _MAST


TXT_X, TXT_W = 232.0, 178.0


# ======================================================================== F36
def f36():
    MA = _mastro_mod()
    F = Folha(36, escala='—',
              material=f'M-10 Al 6061-T6 · tubo Ø{num(M.D_MASTRO, 0)}×{num(M.E_MASTRO, 0)}')
    ex = MA.excitacao()
    comp = MA.comparacao_secoes()
    adot = [c for c in comp if abs(c['d'] - M.D_MASTRO) < 0.1 and abs(c['parede'] - M.E_MASTRO) < 0.1][0]
    v3, v4i = comp[0], comp[1]
    vp = MA.veredito(caso='projeto')
    lim = MA.massa_antena_maxima()
    oc = MA.ocupacao_cabos()

    # ---- gráfico: 1ª frequência por seção, nos três estados do mastro
    x0, y0, w, h = 42.0, 112.0, 158.0, 78.0
    fmax = 12.0
    F.s.rect(x0, y0 - h, x0 + w, y0, 'hid0')
    for i in range(0, int(fmax) + 1, 2):
        yy = y0 - h * i / fmax
        F.s.ln(x0, yy, x0 + w, yy, 'hid0')
        F.s.tx(x0 - 2, yy + 1, f'{i}', 2.6, a='end', c='tx sec')
    F.s.tx(x0 - 2, y0 - h - 3, 'Hz', 2.6, a='end', c='tx sec')
    for (val, cor, rot) in ((MA.REQUISITO_FREQ_HZ, 'cl', f'requisito {dec(MA.REQUISITO_FREQ_HZ, 1)} Hz'),
                            (ex['maior_Hz'], 'ref', f'terreno {dec(ex["maior_Hz"], 1)} Hz')):
        yy = y0 - h * val / fmax
        F.s.ln(x0, yy, x0 + w, yy, cor)
        F.s.tx(x0 + w + 2, yy + 1, rot, 2.6, a='start', c='tx sec')
    n = len(comp)
    for i, c in enumerate(comp):
        xc = x0 + w * (i + 0.5) / n
        for j, (cls, chave) in enumerate((('bar1', 'freq_entrega_Hz'), ('bar2', 'freq_cheio_Hz'),
                                          ('bar3', 'freq_Hz'))):
            xb = xc + (j - 1) * 6.2
            hh = h * min(c[chave] / fmax, 1.0)
            extra = ' adot' if (c is adot and cls == 'bar3') else ''
            F.s.rect(xb - 3.0, y0 - hh, xb + 3.0, y0, cls + extra)
        F.s.tx(xc + 6.2, y0 - h * min(c['freq_Hz'] / fmax, 1.0) - 1.6, dec(c['freq_Hz'], 1), 2.6, peso=700)
        F.s.tx(xc, y0 + 5, f'Ø{num(c["d"], 0)}×{num(c["parede"], 0)}', 2.6, c='tx sec')
        if not c['cabe']:
            F.s.tx(xc, y0 + 9, 'não cabe na luva', 2.2, c='tx sec')
        if c is adot:
            F.s.rect(xc - 10.0, y0 - h - 1, xc + 10.0, y0 + 11, 'barra-adot')
    # legenda
    for j, (cls, txt) in enumerate((('bar1', 'entrega: 3 OAK-D por mastro'),
                                    ('bar2', '+ 2 térmicas por mastro'),
                                    ('bar3', 'PROJETO: + antena no topo'))):
        xl = x0 + j * 56
        F.s.rect(xl, y0 - h - 12, xl + 4, y0 - h - 8, cls)
        F.s.tx(xl + 6, y0 - h - 8.4, txt, 2.7, a='start', c='tx sec')
    rotulo(F.s, x0 + w / 2, y0 + 22, '1ª FREQUÊNCIA DE FLEXÃO POR SEÇÃO DE TUBO', None,
           'três estados do mastro · seção adotada tracejada')

    # ---- o mastro com as massas que a conta usa (lado +Y, da luva ao topo)
    cargas, ponta = MA.cargas_caso('projeto')
    pe = recorta_caixa([p for p in M.mastro_completo((1,)) if p.centro()[1] > 0
                        and (p.centro()[2] > M.Z_LUVA[0] - 2)], y=(0.0, 400.0))
    vl = vista_no_retangulo(pe + M.antena_mastro_ref(1), 'lateral_e', 40, 142, 100, 270)
    desenha(F.s, vl, pe + M.antena_mastro_ref(1))
    for z, m_ in sorted(cargas, key=lambda t: t[0]):
        if z <= M.Z_LUVA[1]:
            continue
        q = vl.P((0, M.Y_MASTRO, z))
        F.s.tx(q[0] + 13, q[1] + 1, f'{dec(m_, 2)} kg', 2.7, a='start', c='tx sec')
    q = vl.P((0, M.Y_MASTRO, M.Z_BASE_ANTENA + M.H_ANTENA))
    F.s.tx(q[0] + 13, q[1] + 1, f'{dec(ponta, 2)} kg · antena + T-10', 2.7, a='start', c='tx sec')
    a, b = vl.P((0, 0, M.Z_LUVA[1])), vl.P((0, 0, M.Z_TOTAL))
    cota_v(F.s, a[1], b[1], 34, None, None, valor=M.Z_TOTAL - M.Z_LUVA[1], lado_txt=-1)
    rotulo(F.s, 76, 278, 'MASSAS DA CONTA', esc(vl), 'engaste no topo da luva · mastro +Y')

    # ---- bloco 1: por que a parede engrossou
    F.bloco(TXT_X, 22, TXT_W, f'''
<h3>Por que o tubo engrossou — duas vezes</h3>
<p><b>1ª vez, Ø25×2 → Ø32×2:</b> o caso 6 do FEA — "1ª frequência do mastro ≥ {dec(MA.REQUISITO_FREQ_HZ, 1)} Hz" —
estava aberto desde a Rev E e nunca fora verificado. O Ø25×2 dá
{dec(MA.frequencia(25, 2, caso='entrega')['freq_Hz'], 2)} Hz com 3 câmeras. <b>2ª vez, Ø32×2 → Ø32×3:</b> o Ø32×2
foi calculado para três câmeras por mastro, e o projeto descreve cinco postos e a antena.</p>
{tabela(['1ª frequência', 'Ø25×2 (V3)', 'Ø32×2', 'Ø32×3'], [
    ['Entrega (3 OAK-D)', f'{dec(MA.frequencia(25, 2, caso="entrega")["freq_Hz"], 2)} Hz',
     f'{dec(v4i["freq_entrega_Hz"], 2)} Hz', f'<b>{dec(adot["freq_entrega_Hz"], 2)} Hz</b>'],
    ['Cheio (+ 2 térmicas)', f'{dec(MA.frequencia(25, 2, caso="cheio")["freq_Hz"], 2)} Hz',
     f'{dec(v4i["freq_cheio_Hz"], 2)} Hz', f'<b>{dec(adot["freq_cheio_Hz"], 2)} Hz</b>'],
    ['<b>Projeto (+ antena)</b>', f'<b>{dec(v3["freq_Hz"], 2)} Hz</b>', f'<b>{dec(v4i["freq_Hz"], 2)} Hz</b>',
     f'<b>{dec(adot["freq_Hz"], 2)} Hz</b>'],
    [f'Contra {dec(MA.REQUISITO_FREQ_HZ, 1)} Hz', '<b>reprova</b>', '<b>reprova</b>',
     'passa' if adot['atende'] else '<b>reprova</b>'],
    ['Δ de massa, 2 mastros', f'{dec(v3["delta_massa_total"] - adot["delta_massa_total"], 2)} kg',
     f'{dec(v4i["delta_massa_total"] - adot["delta_massa_total"], 2)} kg', 'referência'],
], 'micro', col=[34, 22, 22, 22])}
<p>O diâmetro externo fica em {num(M.D_MASTRO, 0)}: o tubo entra na luva Ø{num(M.D_LUVA, 0)}×{num(M.E_LUVA, 0)}, que já alcança
|Y| {num(adot['alcance_luva'], 0)} de um envelope de 600. Só a parede cresce — e leva o furo do tubo a Ø{num(oc['furo_mm'], 0)},
com {dec(oc['ocupacao'] * 100, 0)} % ocupados pelos cabos {tag('ESTIMATIVA')} (limite {dec(oc['limite'] * 100, 0)} %, P-40). {tag('CALC')}</p>''')

    # ---- bloco 2: a margem não fecha
    F.bloco(TXT_X, 124, TXT_W, f'''
<h3>A margem contra o terreno NÃO fecha</h3>
{tabela(['Critério', 'Valor', 'Resultado'], [
    [f'1ª frequência ≥ {dec(MA.REQUISITO_FREQ_HZ, 1)} Hz', f'{dec(vp["freq_mastro_Hz"], 2)} Hz',
     '<b>passa</b> (folga de ' + dec((vp['freq_mastro_Hz'] - MA.REQUISITO_FREQ_HZ) / MA.REQUISITO_FREQ_HZ * 100, 0) + ' %)'],
    [f'Razão contra o terreno ≥ {dec(MA.MARGEM_MINIMA, 1)}', f'{dec(vp["razao"], 2)} ({dec(ex["terreno_Hz"], 1)} Hz)',
     '<b>não passa</b>'],
], 'micro', col=[42, 30, 28])}
<p>A {dec(MA.VELOCIDADE_MS, 1)} m/s o mastro cheio amplifica o terreno {dec(vp['amplificacao'], 1)}×. A margem só fecha abaixo de
<b>{dec(vp['velocidade_maxima_ms'], 2)} m/s</b>. Nem o Ø40×3, que não cabe na luva, fecha
({dec([c for c in comp if c['d'] == 40][0]['razao'], 2)}). O terreno de {dec(ex['terreno_Hz'], 1)} Hz é {tag('A VALIDAR')} — critério,
não medição. O ensaio V-12 decide: medir, ou limitar a marcha com o mastro cheio (P-39).</p>
<p><b>Antena:</b> o mastro cheio cumpre {dec(MA.REQUISITO_FREQ_HZ, 1)} Hz com antena de até <b>{dec(lim, 2)} kg</b>
{tag('CALC')}; acima disso, Ø32×4 ({dec([c for c in comp if c['d'] == 32 and c['parede'] == 4][0]['freq_Hz'], 2)} Hz) estoura o furo dos cabos,
ou a antena volta para a tampa (P-36, P-37). A massa da OAK-D é {tag('A VALIDAR')}: a {dec(0.5, 2)} kg o mastro sai do
requisito.</p>''')

    # ---- bloco 3: rigidez ≠ isolamento (à esquerda, sob o gráfico, ao lado da elevação)
    F.bloco(112, 154, 118, f'''
<h3>Rigidez do mastro ≠ isolamento do sensor</h3>
{tabela(['', 'Enrijecer', 'Isolar a câmera'], [
    ['Faz', 'sobe a frequência própria', 'desacopla a câmera'],
    ['Imagem', 'menos amplitude', 'menos borrão'],
    ['Calibração', '<b>intacta</b>', '<b>destruída</b>'],
], 'micro', col=[24, 38, 38])}
<p>A fusão trata a extrínseca como constante; num mount isolado ela passa a depender da aceleração, e
o erro não é um offset que a calibração corrija. Entre imagem com borrão e nuvem de pontos com erro de
origem desconhecida, a primeira é recuperável.</p>
<p><b>Câmera rígida. O único sensor isolado é o LiDAR</b>, nos coxins G-08 desde a Rev E: ele mede distância
instantânea e não integra imagem no tempo.</p>
<p class="mini">O fator {dec(MA.FATOR_ENGASTE, 2)} sobre o Rayleigh é <b>hipótese</b> do engaste (haste em luva, 2 parafusos);
o Ritz de 5 modos confere o método em {dec(abs(MA.frequencia()['freq_rayleigh_Hz'] - MA.frequencia_ritz()) / MA.frequencia_ritz() * 100, 1)} %.
Tensão na raiz sob {dec(MA.GALHO_N, 0)} N: {dec(MA.tensao_mastro()['sigma_MPa'], 0)} MPa, FS {dec(MA.tensao_mastro()['fs'], 2)}.</p>''')
    return F


# ======================================================================== F37
def f37():
    F = Folha(37, escala='1:1', material='Al 6061-T6 · pinos Inox 304',
              tolerancia='ISO 2768-mK · pinos ISO 286')
    MD = _modular()
    from folhas_w import _tab_ops
    rep = MD.repetibilidade()
    hw, hh = M.VMS_PRATO[0] / 2, M.VMS_PRATO[1] / 2

    def prato(cx, cy, d_furo, camera, titulo, sub, anot):
        F.s.rect(cx - hw, cy - hh, cx + hw, cy + hh, 'vis')
        for sx in (1, -1):
            for sz in (1, -1):
                F.s.circ(cx + sx * M.VMS_FUROS[0] / 2, cy + sz * M.VMS_FUROS[1] / 2, d_furo / 2, 'vis')
                if camera:
                    F.s.circ(cx + sx * 25.0, cy + sz * 20.0, 1.7, 'hid')
        F.s.circ(cx, cy, M.D_PINO_REF / 2, 'vis')
        F.s.circ(cx, cy - M.Z_PINO_GIRO, M.D_PINO_GIRO / 2, 'vis')
        linha_centro(F.s, cx - hw - 6, cy, cx + hw + 6, cy)
        linha_centro(F.s, cx, cy - hh - 6, cx, cy + hh + 6)
        cota_h(F.s, cx - M.VMS_FUROS[0] / 2, cx + M.VMS_FUROS[0] / 2, cy + hh + 9, None, None,
               valor=M.VMS_FUROS[0])
        cota_h(F.s, cx - hw, cx + hw, cy + hh + 17, None, None, valor=M.VMS_PRATO[0])
        cota_v(F.s, cy - M.VMS_FUROS[1] / 2, cy + M.VMS_FUROS[1] / 2, cx - hw - 9, None, None,
               valor=M.VMS_FUROS[1])
        cota_v(F.s, cy - M.Z_PINO_GIRO, cy, cx - hw - 17, None, None, valor=M.Z_PINO_GIRO, lado_txt=-1)
        rotulo(F.s, cx, cy + hh + 30, titulo, '1:1', sub)
        return anot

    prato(70.0, 52.0, M.D_MACHO_M5, False, 'T-02 · PRATO VMS-60',
          f'Ø{num(M.D_PINO_REF, 0)} H7 central · Ø{num(M.D_PINO_GIRO, 0)} H7 a {num(M.Z_PINO_GIRO, 0)} · 4× M5 roscados', None)
    prato(170.0, 52.0, M.D_PASSAGEM_M5, True, 'T-03 · ADAPTADOR OAK-D', 'furação do sensor tracejada (P-06)', None)
    prato(70.0, 166.0, M.D_PASSAGEM_M5, False, 'T-04 · ADAPTADOR TÉRMICO', 'sem furação de sensor (P-30)', None)

    # ---- T-10, adaptador da antena, em corte 1:1
    cx, yt = 170.0, 140.0
    L = M.L_ENCAIXE_ANTENA + M.H_TOPO_ANTENA
    d, di = M.D_ENCAIXE_ANTENA, M.D_CABO_ANTENA
    F.s.rect(cx - d / 2, yt, cx + d / 2, yt + L, 'vis')
    F.s.rect(cx - di / 2, yt, cx + di / 2, yt + L, 'hid')
    linha_centro(F.s, cx, yt - 6, cx, yt + L + 6)
    y_tubo = yt + M.H_TOPO_ANTENA
    F.s.ln(cx - d / 2 - 8, y_tubo, cx + d / 2 + 8, y_tubo, 'cl')
    F.s.tx(cx + d / 2 + 10, y_tubo + 1.2, 'topo do tubo M-10', T, a='start', c='tx sec')
    cota_h(F.s, cx - d / 2, cx + d / 2, yt + L + 10, None, None, valor=d)
    cota_h(F.s, cx - di / 2, cx + di / 2, yt - 6, None, None, valor=di)
    cota_v(F.s, yt, yt + L, cx - d / 2 - 12, None, None, valor=L)
    cota_v(F.s, y_tubo, yt + L, cx + d / 2 + 6, None, None, valor=M.L_ENCAIXE_ANTENA)
    cota_v(F.s, yt, y_tubo, cx + d / 2 + 6, None, None, valor=M.H_TOPO_ANTENA, lado_txt=-1)
    chamada(F.s, cx, yt + 2, 200, 192, ['interface da antena', 'rosca 5/8"-11 UNC', 'A VALIDAR (P-37)'], lado=1)
    rotulo(F.s, cx, yt + L + 28, 'T-10 · ADAPTADOR DA ANTENA', '1:1', 'corte · sai no lugar da ponta M-12')

    # ---- a tabela de operações, à direita
    F.bloco(TXT_X, 22, TXT_W, '<h3>Roteiro de usinagem</h3>' +
            _tab_ops(['T-01', 'T-02', 'T-03', 'T-04', 'T-10'], 'micro'))

    # ---- embaixo, à esquerda: os ajustes e a ordem (a conta do pino está na folha 19)
    F.bloco(30, 240, 200, f'''
<h3>Ajustes e ordem</h3>
{tabela(['Interface', 'Ajuste'], [
    [f'Pino Ø{num(M.D_PINO_REF, 0)} no prato T-02', 'H7 / s6 — fica no prato'],
    [f'Pino Ø{num(M.D_PINO_REF, 0)} no adaptador', 'H7 / h6 — folga 0,024'],
    [f'Anti-giro Ø{num(M.D_PINO_GIRO, 0)}', 'H7 / h6, braço angular'],
    ['Índice de inclinação', f'H7 / h6 · {M.N_INDICE} posições, {num(M.PASSO_INDICE_DEG, 0)}°'],
], 'micro', col=[40, 60])}
<p class="mini">Os dois alojamentos de pino do T-02 são alargados <b>no mesmo setup</b>, a
{num(M.Z_PINO_GIRO, 0)} ± 0,02: é essa cota, e não o diâmetro, que dá a repetibilidade angular. Pinos
ISO 2338 são <b>comprados</b> (F-40 a F-42). O furo do sensor nos adaptadores é {tag('A VALIDAR')}: os 4 furos
Ø3,4 do T-03 são provisão (P-06). T-10 só se usina com a antena escolhida (P-37).</p>''')
    return F


# ======================================================================== F38
def f38():
    F = Folha(38, escala='1:8', material='—')
    MD = _modular()
    todo = M.conjunto('ABO') + M.referencias() + M.antena_mastro_ref(1)
    cam = iso_no_retangulo(todo, 26, 20, 206, 196, 7.0, az=-128, el=20)
    desenha_iso(F.s, cam, todo)
    postos = [('C1', (0, M.Y_MASTRO, M.CAMERAS_Z[0])),
              ('C2', (0, M.Y_MASTRO, M.CAMERAS_Z[1])),
              ('C3', (0, M.Y_MASTRO, M.CAMERAS_Z[2])),
              ('C4', (0, -M.Y_MASTRO, M.CAMERAS_Z[0])),
              ('C5', (0, -M.Y_MASTRO, M.CAMERAS_Z[1])),
              ('C6', (0, -M.Y_MASTRO, M.CAMERAS_Z[2])),
              ('C7', (M.X_CAM_FRENTE, 0, M.Z_CAM_EXTREMIDADE)),
              ('C8', (M.X_CAM_TRAS, 0, M.Z_CAM_EXTREMIDADE)),
              ('C9', (430.0, 0, 298.0)),
              ('H1', (0, M.Y_MASTRO, M.Z_TERMICA[0])),
              ('H2', (0, M.Y_MASTRO, M.Z_TERMICA[1])),
              ('H3', (0, -M.Y_MASTRO, M.Z_TERMICA[0])),
              ('H4', (0, -M.Y_MASTRO, M.Z_TERMICA[1])),
              ('A', (0, M.Y_MASTRO, M.Z_BASE_ANTENA + M.H_ANTENA))]
    for (nome, p) in postos:
        q = cam.P(p)
        balao(F.s, q[0] + (12 if nome[0] in 'CA' else -12), q[1] - 5, nome, alvo=q)
    rotulo(F.s, 116, 204, 'OS NOVE POSTOS DE SENSOR E AS POSIÇÕES OPCIONAIS', '1:8',
           'todos com a mesma face VMS-60')

    linhas = [[f'<b>{n}</b>', o, f'{dec(z, 0)}', c, aj] for (n, o, z, c, aj) in [
        ('C1 / C4', 'mastro, 1º andar', M.CAMERAS_Z[0], 'inspeção', 'altura e inclinação'),
        ('C2 / C5', 'mastro, 2º andar', M.CAMERAS_Z[1], 'inspeção', 'altura e inclinação'),
        ('C3 / C6', 'mastro, 3º andar', M.CAMERAS_Z[2], 'inspeção', 'altura e inclinação'),
        ('C7 / C8', 'sob o nariz e sob a traseira do chassi', M.Z_CAM_EXTREMIDADE, 'navegação', 'inclinação'),
        ('C9', 'sobre a janela de raiz, olhando para baixo', 298.0, 'inspeção', 'fixa'),
        ('H1 / H3', 'mastro, entre o 1º e o 2º andar · térmica removível', M.Z_TERMICA[0], 'inspeção', 'altura e inclinação'),
        ('H2 / H4', 'mastro, entre o 2º e o 3º andar · térmica removível', M.Z_TERMICA[1], 'inspeção', 'altura e inclinação'),
        ('A', 'topo do mastro +Y · antena GNSS (provisão T-10)', M.Z_BASE_ANTENA, 'navegação', 'rosca A VALIDAR'),
    ]]
    F.bloco(26, 214, 204, f'''
<h3>Postos e posições</h3>
{tabela(['Posto', 'Onde', 'Z', 'Classe', 'Ajuste'], linhas, 'micro', col=[12, 46, 9, 14, 19])}
<p class="mini">C7, C8 e C9 são as três que o V3 não tinha de verdade. As posições H e A são opcionais: o mastro é
calculado com elas montadas (folha 36), e as térmicas saem à mão (folha 41). {tag('NOVO')}</p>''')

    e0, e2, e4 = MD.energia(0), MD.energia(2), MD.energia()
    n0, n2, n4 = MD.rede(0), MD.rede(2), MD.rede(4)
    F.bloco(TXT_X, 22, TXT_W, f'''
<h3>Classes de sensor, e por que elas importam</h3>
{tabela(['Classe', 'O que significa para o software'],
        [[MD.CLASSE_NOME[k], v] for k, v in MD.CLASSES.items()], 'micro', col=[22, 78])}
<p>A ausência de uma câmera de inspeção <b>não pode impedir a inicialização nem a navegação</b>; a de LiDAR,
GNSS ou IMU tem de impedir. É requisito de software, não de hardware.</p>

<h3>Matriz de compatibilidade do posto VMS-60</h3>
{tabela(['Módulo', 'VMS?', 'Por quê'],
        [[c['modulo'], '<b>sim</b>' if c['cabe_vms'] else 'não',
          c['pendencia']] for c in MD.compatibilidade()], 'micro', col=[28, 8, 64])}

<h3>Energia e rede com nove câmeras</h3>
{tabela(['Grandeza', 'sem térmica', '2 térmicas', '4 térmicas'], [
    [f'{e4["n_oakd"]} × OAK-D a {dec(e4["w_por_oakd"], 2)} W (teto 802.3af cl. 3)',
     f'{dec(e0["w_oakd"], 1)} W', f'{dec(e2["w_oakd"], 1)} W', f'{dec(e4["w_oakd"], 1)} W'],
    [f'térmicas a {dec(MD.W_TERMICA, 1)} W (FAIXA) + satélite {dec(e4["w_satelite"], 0)} W (provisão)',
     f'{dec(e0["w_termica"] + e0["w_satelite"], 0)} W', f'{dec(e2["w_termica"] + e2["w_satelite"], 0)} W',
     f'{dec(e4["w_termica"] + e4["w_satelite"], 0)} W'],
    [f'<b>Total com perdas de PoE</b> (conversor de {dec(e4["capacidade_dcdc_W"], 0)} W: cabe)',
     f'<b>{dec(e0["total_W"], 0)} W</b>', f'<b>{dec(e2["total_W"], 0)} W</b>', f'<b>{dec(e4["total_W"], 0)} W</b>'],
    ['Portas Ethernet (OAK-D + LiDAR + térmicas)', f'{n0["portas_necessarias"]}', f'{n2["portas_necessarias"]}',
     f'{n4["portas_necessarias"]}'],
    ['Cabe em 8 portas? / em 12?', 'não / sim', 'não / sim', 'não / <b>não</b>'],
], 'micro', col=[52, 16, 16, 16])}
<p><b>A 9ª câmera não dói na energia, dói na rede.</b> São 10 portas com o LiDAR: switch PoE+ de 12 portas é <b>item
novo de BOM</b> (P-31), e cobre até 2 térmicas por Ethernet. As 4 posições cheias exigem 16 portas — ou térmica USB
pela Jetson, que depende do modelo (P-30). Banda: {dec(n0["banda_total_Mbps"], 0)} Mbit/s, {dec(n0["ocupacao_uplink"] * 100, 0)} %
de um uplink de 1 Gbit/s. {tag('CALC')}</p>''')
    return F


# ======================================================================== F39
def f39():
    F = Folha(39, escala='—', material='—')
    MD = _modular()
    F.bloco(26, 22, 190, f'''
<h3>Trocar um sensor em campo</h3>
<p>Nove passos, chave Allen de 3 mm e nada mais — o <b>módulo térmico</b> é mais curto: sai com a mão (folha 41). O passo 5 é o que importa.</p>
{tabela(['n', 'O que fazer', 'Por quê'],
        [[a, b, c] for (a, b, c) in MD.PROCEDIMENTO_TROCA], 'micro', col=[6, 58, 36])}
<p><b>Passo 5 — não tocar na braçadeira T-01.</b> É ela que define altura e azimute, e é a
única camada cuja alteração exige recalibrar a extrínseca. O adaptador sai e volta sobre
os pinos; a braçadeira fica onde está.</p>
<h3>Proteção, ameaça por ameaça</h3>
{tabela(['Ameaça', 'De onde vem a proteção'],
        [[a, b] for (a, b) in MD.PROTECAO_POR_ONDE], 'micro', col=[32, 68])}''')

    F.bloco(TXT_X, 22, TXT_W, f'''
<h3>O que o software tem de fazer</h3>
{tabela(['Requisito', 'O que significa'],
        [[a, b] for (a, b) in MD.REQUISITOS_SOFTWARE], 'micro', col=[30, 70])}
<p class="mini">O inventário de módulos por rover — posto, modelo, número de série, data
da última calibração — é interface com o SaaS e está como
<code>NOT_IMPLEMENTED</code>.</p>

<h3>Ensaios que esta arquitetura exige</h3>
{tabela(['Cód.', 'Ensaio', 'Aceite'],
        [[a, b, c] for (a, b, c) in MD.PLANO_DE_ENSAIO], 'micro', col=[8, 26, 66])}
<p><b>Nenhum destes ensaios foi feito.</b> O V-10 é o que valida ou derruba o argumento do
pino, que é a base de toda esta arquitetura — enquanto ele não rodar, a repetibilidade de
{dec(MD.repetibilidade()["com_pino_deg"], 3)}° é cálculo, não medição. {tag('A VALIDAR')}</p>''')
    return F


# ======================================================================== F40
def f40():
    F = Folha(40, escala='1:5', material='T-07 Al 5052-H32 · chapa 4')
    MD = _modular()
    tampa = [p.como('ctx') for p in M.carenagens() if p.item in ('K-04', 'K-05', 'K-06')]
    sat = M.berco_satelite() + [p for p in M.satelite_ref()]
    outros = M.suporte_gnss() + M.suporte_lidar() + M.estop()
    vs = vista_no_retangulo(tampa + sat + outros, 'superior', 28, 24, 214, 170)
    desenha(F.s, vs, tampa + outros + sat)
    for cod, p, (dx, dy) in (('T-07', (M.X_SAT, 0, M.Z_SAT), (0, 0)),
                             ('G-06', (M.X_LIDAR, 0, M.Z_TAMPA), (0, -12)),
                             ('N-01', (M.X_GNSS, 0, M.Z_TAMPA), (0, 12)),
                             ('K-06', (0, 200, M.Z_TAMPA), (14, 0))):
        q = vs.P(p)
        balao(F.s, q[0] + dx, q[1] + dy, cod, alvo=q if (dx or dy) else None)
    a, b = vs.P((M.X_SAT - M.SAT_ENVELOPE[0] / 2, 0, 0)), vs.P((M.X_SAT + M.SAT_ENVELOPE[0] / 2, 0, 0))
    cota_h(F.s, a[0], b[0], 180, None, None, valor=M.SAT_ENVELOPE[0])
    a, b = vs.P((0, -M.SAT_ENVELOPE[1] / 2, 0)), vs.P((0, M.SAT_ENVELOPE[1] / 2, 0))
    cota_v(F.s, a[1], b[1], 30, None, None, valor=M.SAT_ENVELOPE[1], lado_txt=-1)
    rotulo(F.s, 120, 196, 'DECK — O QUE JÁ OCUPA E O QUE SOBRA', esc(vs),
           'vista superior, tampas em contexto')

    F.bloco(26, 214, 196, f'''
<h3>Provisão de comunicação por satélite — e o que ela não resolve</h3>
<p>O V3 <b>não tinha provisão nenhuma</b>: a busca por "Starlink" em todo o projeto dava
zero ocorrências — nem suporte, nem massa, nem consumo. O V4 abre a provisão, e abre com o
número honesto do que cabe. {tag('NOVO')}</p>
{tabela(['Requisito do terminal', 'Valor'], [
    ['Envelope máximo (L × W × H)',
     f'<b>{num(M.SAT_ENVELOPE[0], 0)} × {num(M.SAT_ENVELOPE[1], 0)} × '
     f'{num(M.SAT_ENVELOPE[2], 0)} mm</b>'],
    ['Fixação', f'6 × M5 em porca-rebite, malha {num(190, 0)} × {num(210, 0)}'],
    ['Passagem de cabo', 'Ø32 central, com passa-cabo'],
    ['Consumo reservado no orçamento', f'{dec(MD.W_SATELITE, 0)} W'],
    ['Interface', 'Ethernet — porta no switch PoE+ de 12 portas (P-31)'],
], 'micro', col=[46, 54])}
<p><b>Um terminal de ~300 × 260 mm — que é a classe do Starlink Mini — NÃO CABE nesta
provisão.</b> O deck já tem o suporte do LiDAR em |X| 215…345, a antena GNSS em 295…405, a
faixa central em |X| ≤ 55 e o E-STOP em 420…500. O único vão contínuo é X −290…−60, e ele
dá {num(M.SAT_ENVELOPE[0], 0)} mm. Caber exigiria deslocar o LiDAR ou o GNSS — decisão de
projeto, não de desenho. Pendência <b>P-32</b>.</p>''')

    F.bloco(TXT_X, 22, TXT_W, f'''
<h3>Pendências que o V4 abre</h3>
{tabela(['Cód.', 'Assunto', 'Grau', 'O que falta'],
        [[a, b, c, d_] for (a, b, c, d_) in MD.PENDENCIAS], 'micro', col=[8, 24, 11, 57])}
<h3>Acima da linha de proteção Z 400</h3>
<p>A baseline exige que nada do corpo passe de Z {num(M.Z_PROT, 0)}. Três coisas passam, e
as três são antena ou sensor que precisa ver:</p>
{tabela(['Item', 'Topo', 'Por quê'], [
    ['N-01 · suporte da antena GNSS', f'Z {num(M.Z_GNSS[1], 1)}',
     'já no V3; a antena precisa de vista livre ao céu'],
    ['G-06 · suporte do LiDAR', f'Z {num(M.Z_BASE_LIDAR, 1)}',
     'já no V3; 360° de varredura'],
    ['T-07 · berço do terminal satelital',
     f'Z {num(M.Z_SAT + M.E_BERCO_SAT, 1)}', f'novo no V4; +{num(M.E_BERCO_SAT + 2, 0)} mm'],
], 'micro', col=[40, 16, 44])}
<p class="mini">É exceção deliberada e já existente, não descuido: pôr antena abaixo da
linha de proteção é anular a antena. O que está acima de Z 400 é tudo removível e
sacrificável; a estrutura do corpo continua abaixo.</p>''')
    return F



# ======================================================================== F41
def f41():
    MD, MA = _modular(), _mastro_mod()
    F = Folha(41, escala='sem escala', material='T-04 Al 6061-T6 · parafusos inox A4',
              tolerancia='ISO 2768-mK · pinos ISO 286 H7/h6')
    z = M.Z_TERMICA[1]
    post = [p for p in M.suportes_termicos() if p.centro()[1] > 0 and abs(p.centro()[2] - z) < 60]
    desloc = {'T-01': 0.0, 'T-02': 24.0, 'T-04': 70.0, 'T-05': 70.0}
    movidos = []
    for p in post:
        movidos.append(p.movido(0, desloc[p.item], 36.0 if p.item == 'T-05' else 0.0))
    ctx = [p.como('ctx') for p in recorta_caixa([q for q in M.mastro() if q.centro()[1] > 0],
                                                z=(z - 80, z + 80), y=(0.0, 400.0))]
    y_t02 = [p for p in movidos if p.item == 'T-02'][0].bbox()[1]
    y_t04 = [p for p in movidos if p.item == 'T-04'][0].bbox()[1]
    # pinos: ficam no prato e entram no adaptador (linha tracejada: são parafusaria, não peça do modelo)
    pinos = [M.cilindro('F-40', 'y', y_t02[1] - 6, y_t04[0] + 8, 0.0, z, M.D_PINO_REF, estilo='ref'),
             M.cilindro('F-41', 'y', y_t02[1] - 6, y_t04[0] + 8, 0.0, z + M.Z_PINO_GIRO, M.D_PINO_GIRO, estilo='ref')]
    # os 4 parafusos imperdíveis, no ar à frente do adaptador: cabeça serrilhada Ø12, haste Ø5
    y_cam = y_t04[1] + 26.0                       # a câmera vem depois do adaptador
    y_par = y_cam + 62.0
    parafusos = []
    for sx in (1, -1):
        for sz in (1, -1):
            cx_, cz_ = sx * M.VMS_FUROS[0] / 2, z + sz * M.VMS_FUROS[1] / 2
            parafusos.append(M.cilindro('F-51', 'y', y_par, y_par + 8, cx_, cz_, 12.0, estilo='solid'))
            parafusos.append(M.cilindro('F-51', 'y', y_par - 34, y_par, cx_, cz_, M.D_PASSAGEM_M5 - 0.5, estilo='ref'))
    l, a_, p_ = M.ENVELOPE_TERMICA
    envelope = [M.chapa('R-07', 'y', y_cam, y_cam + p_,
                        M.retangulo(-l / 2, l / 2, z - a_ / 2, z + a_ / 2), estilo='ref')]
    todo = movidos + ctx + pinos + parafusos + envelope
    cam = iso_no_retangulo(todo, 30, 26, 232, 162, 1.0, az=-118, el=22)
    desenha_iso(F.s, cam, todo)
    # o cabo, saindo do corpo da câmera para o conector M12 (traço do cabo; o conector é peça comprada)
    pts = [cam.P(p) for p in ((0.0, y_cam + 8, z - a_ / 2), (-10.0, y_cam - 12, z - a_ / 2 - 24),
                              (-34.0, y_t02[0] - 6, z - a_ / 2 - 46), (-44.0, y_t02[0] - 24, z - a_ / 2 - 62))]
    F.s.pl(pts, 'vism')
    q = cam.P((-44.0, y_t02[0] - 24, z - a_ / 2 - 62))
    F.s.rect(q[0] - 3.5, q[1] - 1.8, q[0] + 3.5, q[1] + 1.8, 'vis')
    for cod, p, (dx, dy) in (('1', (0.0, y_t02[0] - 28, z + 6), (-16, 0)),
                             ('2', (0.0, (y_t02[0] + y_t02[1]) / 2, z - 30), (-16, 8)),
                             ('3', (0.0, y_t02[1] + 2, z), (16, 8)),
                             ('4', (30.0, (y_t04[0] + y_t04[1]) / 2, z - 28), (-16, 10)),
                             ('5', (0.0, y_cam + p_ / 2, z), (22, 10)),
                             ('6', (20.0, y_t04[1] + 18, z + M.ALTURA_PROTETOR + 36), (16, -6)),
                             ('7', (M.VMS_FUROS[0] / 2, y_par + 4, z + M.VMS_FUROS[1] / 2), (16, -6)),
                             ('8', (-44.0, y_t02[0] - 24, z - a_ / 2 - 62), (-18, -6))):
        qq = cam.P(p)
        balao(F.s, qq[0] + dx, qq[1] + dy, cod, alvo=qq)
    rotulo(F.s, 131, 184, 'POSTO TÉRMICO REMOVÍVEL — EXPLODIDA', 'sem escala',
           'o mastro ao fundo; o módulo sai para fora, em um bloco')

    leg = [['1', 'T-01 braçadeira', 'fica', 'posição: altura e azimute'],
           ['2', 'T-02 prato VMS-60', 'fica', 'índice de inclinação, 7 posições'],
           ['3', 'pinos Ø8 H7 · Ø6 H7', 'ficam no prato', 'repõem a mesma pose'],
           ['4', 'T-04 adaptador', '<b>sai</b>', 'sem furação de sensor (P-30)'],
           ['5', 'câmera térmica', '<b>sai</b>', f'cabe em {num(l, 0)}×{num(a_, 0)}×{num(p_, 0)}'],
           ['6', 'T-05 sobrancelha', '<b>sai</b>', '2 × M4, sacrificial'],
           ['7', '4 × M5 imperdíveis', '<b>aperto manual</b>', 'rosqueiam em T-02'],
           ['8', 'cabo com conector M12', '<b>desconecta antes</b>', 'IP não declarado']]
    F.bloco(30, 202, 200, '<h3>O que fica e o que sai</h3>' +
            tabela(['#', 'Peça', 'Estado', 'Nota'], leg, 'micro', col=[5, 33, 25, 37]))

    F.bloco(30, 262, 200, f'''
<p class="mini"><b>Conceito.</b> Esta folha mostra a <b>ideia</b>, e a ideia só fica cota de fabricação quando o
modelo da térmica existir: o T-04 não tem furação de sensor {tag('A VALIDAR')}, e o corpo da câmera tem de deixar
livre a cabeça dos 4 parafusos (P-38). Nada aqui é validado por desenho ou renderização — o ensaio V-16 mede
a repetibilidade com aperto manual.</p>''')

    # ---- direita: o esboço do projeto, item a item
    esb = [
        ['OAK-D <b>fixa e calibrada</b>, parafusos permanentes',
         'Posto fixo: T-03 + 4 × M5 de cabeça sextavada interna, com chave. Pinos no prato. A troca exige a '
         'verificação de calibração (folha 39).'],
        ['Térmica <b>módulo removível</b>, encaixe rápido, manípulo',
         'T-04 + 4 × M5 <b>imperdíveis</b>, de aperto manual, nos <b>mesmos</b> pinos. Sai sem ferramenta e '
         'volta à mesma pose.'],
        ['Conector M12 de desconexão rápida, cabo blindado',
         'M12 no cabo do módulo, desconectado ANTES de soltar os parafusos. Grau IP <b>não declarado</b>: '
         'só o ensaio V-11 o dá.'],
        ['"Direcionamento manual e travamento"',
         f'Inclinação por índice de {num(M.PASSO_INDICE_DEG, 0)}°, de −{num((M.N_INDICE - 1) / 2 * M.PASSO_INDICE_DEG, 0)}° a '
         f'+{num((M.N_INDICE - 1) / 2 * M.PASSO_INDICE_DEG, 0)}°, com pino; azimute pela braçadeira, travada por 2 × M6.'],
        ['Lente com proteção', 'Sobrancelha T-05 acima; <b>nada</b> diante nem ao lado da lente (campo de visão).'],
        ['Mastro em perfil T 30×30 com T-nuts',
         f'<b>Mantido o tubo Ø{num(M.D_MASTRO, 0)}×{num(M.E_MASTRO, 0)} com braçadeira</b>: a rigidez dele foi CALCULADA '
         '(folha 36); a de um perfil T não tem ficha técnica no projeto (P-41).'],
    ]
    F.bloco(244, 22, 164, '<h3>O esboço do projeto, item a item</h3>' +
            tabela(['O esboço pede', 'O V4 faz'], esb, 'compacta', col=[34, 66]) + f'''
<p class="mini">O esboço foi usado como <b>intenção</b> — é imagem conceitual, sem cotas, e não é fonte de
dimensão de fabricação. Tudo que tem número aqui vem do modelo do caderno.</p>''')
    F.bloco(244, 128, 164, f'''
<h3>Como o módulo sai</h3>
{tabela(['n', 'O que fazer', 'Por quê'],
        [[a, b, c] for (a, b, c) in MD.PROCEDIMENTO_TROCA_TERMICA], 'micro', col=[5, 56, 39])}
<h3>O que ainda não está fechado</h3>
<ul>
<li><b>P-30</b> — modelo da câmera térmica: sem ele, T-04 é blank.</li>
<li><b>P-38</b> — cabe nos {num(l, 0)}×{num(a_, 0)}×{num(p_, 0)} e deixa os parafusos livres?</li>
<li><b>V-16</b> — repetibilidade com aperto manual; hoje só o parafuso de ferramenta tem número
({dec(MD.repetibilidade()["com_pino_deg"], 3)}°, cálculo).</li>
<li><b>P-41</b> — perfil T 30×30: precisaria de ficha e de novo cálculo.</li>
</ul>''')
    return F


# ======================================================================== F42
_ROT = None


def _roteamento():
    global _ROT
    if _ROT is None:
        import importlib.util
        import pathlib
        cam = pathlib.Path(__file__).resolve().parent.parent / 'revisao-h' / 'roteamento.py'
        esp = importlib.util.spec_from_file_location('roteamento_h', cam)
        mod = importlib.util.module_from_spec(esp)
        esp.loader.exec_module(mod)
        _ROT = mod
    return _ROT


def f42():
    RO = _roteamento()
    F = Folha(42, escala='sem escala', material='—')
    s = F.s

    def caixa(x0, y0, x1, y1, titulo, sub=None, opc=False, sz=2.9):
        s.rect(x0, y0, x1, y1, 'caixa-opc' if opc else 'caixa')
        if sub:
            s.tx((x0 + x1) / 2, y0 + 4.2, titulo, sz, peso=600)
            for i, t in enumerate(sub):
                s.tx((x0 + x1) / 2, y0 + 8.0 + i * 3.4, t, 2.4, c='tx sec')
        else:
            s.tx((x0 + x1) / 2, (y0 + y1) / 2 + 1.0, titulo, sz, peso=600)

    def lig(pts, cls, rot=None, rx=None, ry=None):
        s.pl(pts, cls)
        if rot:
            s.tx(rx, ry, rot, 2.4, c='tx sec')

    # ---- o compartimento, tracejado: o que está dentro dele e o que fica de fora
    s.rect(104, 26, 232, 148, 'quadro-comp')
    s.tx(106, 24.2, 'COMPARTIMENTO', 2.4, a='start', c='tx sec')
    # ---- mastros e deck (fora, à esquerda)
    caixa(32, 28, 88, 60, 'MASTRO +Y', ['3 × OAK-D', '0 a 2 térmicas', 'antena GNSS (opc.)'])
    caixa(32, 64, 88, 96, 'MASTRO −Y', ['3 × OAK-D', '0 a 2 térmicas', 'antena GNSS (opc.)'])
    caixa(32, 102, 88, 114, 'LiDAR Mid-360')
    caixa(32, 118, 88, 130, 'Antena N-01 · sat. T-07', opc=True, sz=2.5)
    caixa(32, 134, 88, 146, 'E-STOP')
    # ---- dentro do compartimento
    caixa(112, 36, 162, 52, 'Switch PoE+', ['12 portas (P-31)'])
    caixa(176, 36, 226, 52, 'Jetson Orin NX')
    caixa(112, 60, 162, 76, 'Receptor GNSS', ['+ IMU'])
    caixa(176, 60, 226, 76, 'Roteador / modem')
    caixa(112, 84, 162, 98, 'C9 · câmera de raiz', opc=False, sz=2.5)
    caixa(112, 106, 138, 120, 'Bateria')
    caixa(142, 106, 166, 120, 'BMS')
    caixa(172, 106, 226, 120, 'Driver motores')
    caixa(112, 126, 156, 140, 'DC/DC 12 V')
    caixa(162, 126, 226, 140, 'Grupo pneumático', sz=2.7)
    # ---- fora, à direita
    caixa(244, 36, 296, 56, 'C7 · C8', ['sob o chassi', 'frontal e traseira'])
    caixa(244, 106, 296, 120, '4 × motor-roda')
    caixa(244, 126, 296, 140, '4 × fole + sensor', opc=False, sz=2.6)

    # ---- dados (azul): barramento em x = 96
    lig([(88, 44), (96, 44), (96, 100), (88, 100)], 'cb-dad')
    lig([(88, 80), (96, 80)], 'cb-dad')
    lig([(88, 108), (96, 108)], 'cb-dad')
    lig([(96, 44), (112, 44)], 'cb-dad', '3+3 M12 PoE', 98, 41)
    lig([(162, 40), (176, 40)], 'cb-dad')
    lig([(201, 52), (201, 60)], 'cb-dad')
    lig([(244, 46), (238, 46), (238, 31), (137, 31), (137, 36)], 'cb-dad', '2 M12', 236, 29)
    lig([(137, 84), (137, 80), (104, 80)], 'cb-dad')          # C9 → barramento (pela esquerda)
    # ---- coaxial e sinal (verde)
    lig([(88, 124), (100, 124), (100, 68), (112, 68)], 'cb-sin', 'coaxial', 90, 121)
    lig([(162, 72), (169, 72), (169, 46), (176, 46)], 'cb-sin', 'IMU', 163, 70)
    # ---- potência (vermelho)
    lig([(138, 113), (142, 113)], 'cb-pot')
    lig([(166, 113), (172, 113)], 'cb-pot')
    lig([(226, 113), (244, 113)], 'cb-pot', '4 cabos', 229, 110)
    lig([(125, 120), (125, 126)], 'cb-pot')
    lig([(156, 133), (162, 133)], 'cb-pot')
    # ---- segurança (laranja, tracejado)
    lig([(88, 140), (98, 140), (98, 144), (229, 144), (229, 116), (226, 116)], 'cb-seg', 'laço NF', 90, 138)
    # ---- pneumática (roxo, tracejado)
    lig([(226, 133), (244, 133)], 'cb-pne', '4 tubos Ø6', 227, 130)

    # legenda das classes
    for i, (cls, nome) in enumerate((('cb-pot', 'potência'), ('cb-dad', 'dados · PoE'),
                                     ('cb-sin', 'sinal · coaxial'), ('cb-seg', 'segurança'),
                                     ('cb-pne', 'pneumática'))):
        x = 34 + i * 52
        s.pl([(x, 152.5), (x + 9, 152.5)], cls)
        s.tx(x + 11, 153.8, nome, 2.6, a='start', c='tx sec')
    rotulo(s, 357, 184, 'INTERLIGAÇÃO FUNCIONAL', 'sem escala',
           'o que liga a quê; não é chicote')

    # ---- a lista de interligação
    linhas = []
    for i, n in enumerate(RO.interligacoes(), 1):
        comp = f'≥ {dec(n["comp_m"], 1)} m' if n['comp_m'] else '—'
        linhas.append([str(i), f'{n["de"]} → {n["para"]}', RO.CLASSES[n['classe']].split(' ')[0],
                       n['qtd'], n['meio'], n['passagem'], comp])
    F.bloco(30, 158, 266, '<h3>Lista de interligação — comprimentos ESTIMADOS</h3>' +
            tabela(['#', 'Ligação', 'Classe', 'Qtd', 'Meio', 'Passagem pela estrutura', 'Cabo'], linhas, 'nano',
                   col=[3, 31, 8, 5, 17, 29, 7]))

    # ---- direita: regras
    F.bloco(304, 24, 104, '<h3>Regras de roteamento — propostas</h3><ol class="notas">' +
            ''.join(f'<li><b>{a}.</b> {b}</li>' for (a, b) in RO.REGRAS) + '</ol>')

    # ---- passagens
    ps = RO.passagens()
    cor = {'MODELADA': 'modelada', 'FALTA': '<b>FALTA</b>', 'SÓ NO TEXTO': 'só no texto'}
    F.bloco(30, 240, 200, '<h3>Passagens pela estrutura</h3>' +
            tabela(['Onde', 'Quem passa', 'Estado'],
                   [[p['onde'], p['quem'], cor[p['estado']]] for p in ps], 'nano', col=[52, 33, 15]))
    return F



# ======================================================================== F43
def _rev_h_mod(nome):
    """Carrega um módulo de ../revisao-h com o mesmo modelo deste caderno."""
    import sys
    import pathlib
    pasta = pathlib.Path(__file__).resolve().parent.parent / 'revisao-h'
    if str(pasta) not in sys.path:
        sys.path.insert(0, str(pasta))
    import importlib
    return importlib.import_module(nome)


# Valores que a Rev I PUBLICOU (folha 43 dela, 13/10/2026). Ficam aqui só para comparação:
# partiam do CG e do envelope da Rev H, que a correção de 15/10 mostrou otimistas.
REV_I_PUBLICADA = {
    'AL': dict(cg=313.2, tomb=40.2, env=21.3, p_fole=7.4),
    'AC': dict(cg=311.3, tomb=40.4, env=21.5, p_fole=8.8),
}


def f43():
    OP = M.OP
    F = Folha(43, escala='sem escala', material='—')
    SU = _rev_h_mod('suspensao')
    CM = _rev_h_mod('centro_massa')
    MD = _rev_h_mod('modular')

    # ---- massa por grupo: Rev H (alumínio, W-12/W-13 em Al) contra esta revisão e opção
    linhas, tot_h, tot_j = [], 0.0, 0.0
    for g in ('Q', 'C', 'W', 'G', 'M', 'K'):
        pecas = [p for p in M.conjunto('A') if p.grupo == g and p.estilo != 'ref']
        mh = sum(M.massa_rev_h(p) for p in pecas)
        mj = sum(p.massa() for p in pecas)
        tot_h += mh
        tot_j += mj
        d = mj - mh
        linhas.append([f'<b>{g}</b>', M.GRUPOS[g], dec(mh, 2), dec(mj, 2),
                       ('+' + dec(d, 2)) if d > 0.005 else '—'])
    linhas.append(['', '<b>Parte A, total</b>', f'<b>{dec(tot_h, 2)}</b>', f'<b>{dec(tot_j, 2)}</b>',
                   f'<b>+{dec(tot_j - tot_h, 2)}</b>'])

    # ---- grandezas recalculadas pela fonte corrigida
    pr = CM.analisa('projeto')
    rl = SU.roll()
    fl = SU.fole(SU.massa()['massa'])
    en = MD.energia(0)
    pub = REV_I_PUBLICADA[OP.OPCAO]
    grand = [
        ['Massa do inventário, mastro cheio', '—', f'{dec(pr["kg"], 1)} kg'],
        ['Altura do CG, Z', f'{dec(pub["cg"], 1)} mm', f'{dec(pr["z"], 1)} mm'],
        ['Tombamento lateral', f'{dec(pub["tomb"], 1)}°', f'{dec(pr["lateral"]["tomba_deg"], 1)}°'],
        ['Envelope de estabilidade (fórmula 6.1)', f'{dec(pub["env"], 1)}°',
         f'<b>{dec(pr["envelope_deg"], 1)}°</b> (baseline {dec(CM.ENVELOPE_BASELINE, 1)}°)'],
        ['Pressão de projeto do fole (teto 8 bar)', f'{dec(pub["p_fole"], 1)} bar',
         f'<b>{dec(fl["p_projeto_bar"], 2)} bar</b>' + (' — ACIMA do teto' if fl['p_projeto_bar'] > 8.0 else '')],
        ['Pico do barramento de 12 V (conversor 360 W)', '—',
         f'{dec(en["pico_barramento_12v_W"], 0)} W'],
    ]

    pedidos = [
        ['1', 'Chassi de alumínio para aço carbono',
         ('<b>Opção B</b>: quadro Q, chapa de fundo C-01, nervuras C-02, gaiola G e base dos mastros M-01/M-02 em '
          'aço (tubos SAE 1020, chapas A36, chapa de fundo SAE 1010), mesma geometria. Solda MAG ER70S-6.')
         if OP.ACO else
         '<b>Opção A</b>: chassi mantido em alumínio, como na Rev H, para cotação comparativa com a opção B.'],
        ['2', 'Parafuso em vez de rebite em cima e nos lados',
         'Já estava na Rev H; confirmado. Rebite só por baixo da chapa de fundo (F-09 e F-35).'],
        ['3', 'Tirar a planicidade de 0,1',
         'Feito: retirada a cota individual de planeza da face do motor (W-02) e das juntas do colar (W-13). '
         'Vale a ISO 2768-mK, planeza classe K. Ficam a perpendicular 0,3 a A e o Ra 3,2.'],
        ['4', 'Flanges da roda em aço',
         'W-02 já era aço A36. Passam de Al 6061-T6 para aço A36 o flange W-13 e o tubo W-12, soldados entre si.'],
    ]

    atencao = []
    if OP.ACO:
        atencao += [
            f'<b>Fole.</b> Com o chassi em aço a pressão de projeto vai a {dec(fl["p_projeto_bar"], 2)} bar, '
            'acima do teto de 8 bar da folha 07: rever a área efetiva ou a pressão admissível antes de comprar.',
            '<b>Aço contra alumínio.</b> Carenagens K, haste M-10, grupo T, batentes B-01, bandejas E e berço W-11 '
            'seguem em alumínio: barreira com arruela de nylon e pintura (folhas 07, 30, 33 e 34).',
            '<b>Rebites F-09 e F-35</b> sobre aço: de aço ou inox, nunca de alumínio.',
            '<b>Espessuras.</b> 30×30×1,5, 20×20×1,2 e chapa de 1,5 devolvem cerca de 7 kg, com FEA novo.',
        ]
    else:
        atencao += [
            '<b>Aço contra alumínio.</b> O flange W-13, agora em aço, assenta na chapa de fundo de alumínio: a junta '
            'NBR das duas faces faz a barreira; entregar o flange zincado ou pintado.',
        ]
    atencao += [
        '<b>Estabilidade.</b> Os números da Rev I partiam do CG da Rev H. Com o CG do inventário do V4 o envelope '
        f'fica em {dec(pr["envelope_deg"], 1)}°, contra {dec(CM.ENVELOPE_BASELINE, 1)}° da baseline.',
        '<b>Planeza do motor.</b> Sem cota própria até a resposta da ElectroCraft (P-04).',
        '<b>Liberação.</b> O selo continua NÃO LIBERADO: falta o parecer do engenheiro (folha 15).',
    ]

    F.bloco(26, 22, 190, f"""
<h3>1 · Por que Rev J</h3>
<p>A <b>Rev I</b> (13/10/2026) foi enviada para cotação em duas opções de material, mas só existia em PDF,
editado sobre o caderno da Rev H. A <b>Rev J</b> traz a Rev I para o modelo paramétrico — mesma geometria,
mesmos materiais — e soma as <b>correções de cálculo de 15/10/2026</b>
(<code>revisao-h/VTX-RV4-CORRECOES-2026-10-15.md</code>). Como os números calculados mudaram, a letra muda.
{tag('REV J')}</p>
<p>Este caderno: <b>{OP.DOC}</b> — {OP.NOME}.</p>
<h3>2 · Pedidos da Rev I</h3>
{tabela(['#', 'Pedido', 'Situação'], pedidos, 'micro', col=[5, 28, 67])}
<h3>3 · Massa da Parte A em relação à Rev H (kg)</h3>
{tabela(['Gr.', 'Conjunto', 'Rev H', f'Rev J {OP.LETRA}', 'Δ'], linhas, 'micro', col=[7, 45, 16, 16, 16])}""")
    F.bloco(222, 22, 188, f"""
<h3>4 · Grandezas: o que a Rev I publicou e o que a fonte calcula</h3>
{tabela(['Grandeza', 'Rev I publicada', 'Rev J (fonte corrigida)'], grand, 'micro', col=[46, 22, 32])}
<p class="mini">Rev J: inventário de <code>centro_massa.py</code> (estado projeto), rolagem limitada por curso de
<code>suspensao.py</code>, energia de <code>modular.py</code>. Nada digitado.</p>
<h3>5 · O que pede atenção</h3>
<ol class="notas">{''.join(f'<li>{a}</li>' for a in atencao)}</ol>
<h3>6 · Folhas com conteúdo alterado</h3>
<p class="mini">Em todas: revisão J, data {OP.DATA}, documento e NN/43. Conteúdo: 01, 02, 04, 06 a 09, 11, 12,
14 a 17, 24, 25, 27, 29 a 31, 33 a 35 e esta, 43. Materiais e massas saem do modelo; os DXF trazem o material
no nome.</p>""")
    return F


FOLHAS_T = [f36, f37, f38, f39, f40, f41, f42, f43]
