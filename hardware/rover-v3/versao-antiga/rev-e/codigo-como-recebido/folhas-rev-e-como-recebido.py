"""Composição das 16 folhas A3 do caderno VTX-RV3-CG-E.

Regras de layout (ABNT NBR 10068 / 8402 / 10126): área útil X 25→413, Y 7→290; legenda em
X ≥ 235, Y ≥ 238; selo de status em X ≥ 296, Y ≤ 17. Letras de 3,6 (maiúscula 2,5), títulos de vista
5,0. Primeira linha de cota a ≥ 8 mm da peça e as seguintes a cada 8 mm.
"""
import math
from collections import Counter, OrderedDict

import modelo as M
from modelo import (quadro, chapa_fundo, suportes, suporte, gaiola, suporte_lidar, carenagens, rodas,
                    mpw86_ref, lidar_ref, mastro_ref, conjunto, fixadores, furos_chapa, ITENS,
                    GRUPOS, comparacao_baseline, TABELA_51, XS, XQ, YQ, Y_C, YG_C, Y_FACE, Z_EIXO,
                    Z_QUADRO, Z_DECK, Z_PROT, Z_G0, Z_G1, Z_G2, Z_TAMPA, Z_FAIXA, Z_BASE_LIDAR, L_Q, W_Q,
                    L_EXT, W_EXT, X_CANTO, X_MOD, TG, TQ)
from desenho import (Svg, Vista, Iso, projeta, desenha, desenha_corte, desenha_iso, cota_h, cota_v,
                     cota_vista_h, cota_vista_v, chamada, balao, linha_centro, cruz_centro, plano_corte,
                     rotulo, num, milhar, seta, f, fcf, referencia, rugosidade, simbolo_solda, T)

DOC = 'VTX-RV3-CG-E'
DATA = '19/09/2026'
TOTAL = 27
D = 8.0          # espaçamento entre linhas de cota

TITULOS = OrderedDict([
    (1, ('Capa e índice', 'Caderno de desenhos para cotação e validação')),
    (2, ('Escopo e requisitos de fabricação', 'Materiais, processos, tolerâncias, acabamento, inspeção')),
    (3, ('Conjunto geral', 'Rover V3 completo · posição do chassi e da gaiola')),
    (4, ('Quadro estrutural — vistas', 'Conjunto soldado Q-01 a Q-06')),
    (5, ('Chassi — cortes e detalhes', 'Quadro, chapa de fundo, suportes, MPW86 (ref.)')),
    (6, ('Quadro estrutural — corte e solda', 'Lista de corte, plano de corte das barras, soldagem')),
    (7, ('Suporte do motor-roda', 'Conjunto soldado S-01 a S-03 · 2 E + 2 D')),
    (8, ('Chapa de fundo e nervuras', 'Itens C-01 e C-02')),
    (9, ('Gaiola de proteção — vistas', 'Dois módulos idênticos · G-01 a G-08')),
    (10, ('Gaiola — cortes e detalhes', 'Fixações, suporte do LiDAR, campo de visão')),
    (11, ('Carenagens, tampas e chapas', 'Peças planas para corte a laser')),
    (12, ('Gaiola — corte e solda', 'Lista de corte, plano de corte das barras, montagem')),
    (13, ('Conjunto — explodida e montagem', 'Sequência de montagem e fixadores')),
    (14, ('Lista de materiais e massas', 'Comparação com a baseline Rev E')),
    (15, ('Validação — engenheiro mecânico', 'Verificações, inconsistências, pendências, parecer')),
    (16, ('Solicitação de orçamento', 'Formulário de proposta para o fornecedor')),
    (17, ('Mastro — base no quadro', 'Luva M-01, reforço M-02, solda e verificação')),
    (18, ('Mastro — haste, alturas e cabos', 'Elevação, andares das câmeras, bainha e passagem de cabos')),
    (19, ('Suporte da câmera M-20', 'Peça plana, montagem no mastro e interface da câmera')),
    (20, ('Bateria — zona e retenção', 'Batentes B-01, cintas e malha de montagem')),
    (21, ('Eletrônica e E-STOP', 'Zonas, bandejas, entradas de cabo e aterramento')),
    (22, ('Interfaces de sensores e sinalização', 'Antena GNSS, IMU, câmera de raiz, faróis e carenagens')),
    (23, ('Plano de fechamento', 'Pendências, responsáveis e critérios de aceite')),
    (24, ('Massa, CG e envelope consolidados', 'Baseline + Parte A + Parte B · opções de redução')),
    (25, ('Solda do 6061-T6, diagonais e encargos de FEA', 'Condição de cálculo, casos de carga e aceite')),
    (26, ('Plano de validação', 'Ensaios de bancada e de campo · definição do vão livre')),
    (27, ('Motor-roda — MPW86 × ZLTECH', 'Comparação, impacto na massa e no CG, e o que falta para migrar')),
])


# ============================================================ infraestrutura
class Folha:
    def __init__(self, n, escala='—', material='—', tolerancia=None):
        self.n = n
        titulo, sub = TITULOS[n]
        self.s = Svg()
        self.blocos = []
        self.defs = []
        self.meta = dict(titulo=titulo.upper(), subtitulo=sub, escala=escala, material=material, data=DATA,
                         rev='0')
        if tolerancia:
            self.meta['tolerancia'] = tolerancia

    def bloco(self, x, y, w, html, h=None, cls=''):
        self.blocos.append((x, y, w, h, html, cls))

    def recorte(self, ident, x0, y0, x1, y1):
        self.defs.append(f'<clipPath id="{ident}"><rect x="{f(x0)}" y="{f(y0)}" width="{f(x1 - x0)}" '
                         f'height="{f(y1 - y0)}"/></clipPath>')

    def render(self):
        from desenho import moldura
        self.meta['numero'] = f'{DOC}-{self.n:02d}'
        self.meta['folha'] = f'{self.n:02d}/{TOTAL:02d}'
        base = Svg()
        moldura(base, self.meta)
        svg = (f'<svg class="desenho" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 420 297" '
               f'width="420mm" height="297mm" role="img" aria-label="Folha {self.n}: {TITULOS[self.n][0]}">'
               f'<defs>{"".join(self.defs)}</defs>{base}{self.s}</svg>')
        bl = []
        for (x, y, w, h, html, cls) in self.blocos:
            hh = f';height:{f(h)}mm' if h else ''
            bl.append(f'<div class="bl {cls}" style="left:{f(x)}mm;top:{f(y)}mm;width:{f(w)}mm{hh}">{html}</div>')
        return (f'<section class="folha" id="f{self.n:02d}" data-titulo="{TITULOS[self.n][0]}">'
                f'{svg}{"".join(bl)}</section>')


TAGS = {'FONTE': 'fonte', 'BASE': 'base', 'CALC': 'calc', 'NOVO': 'novo', 'A VALIDAR': 'val',
        'HIPÓTESE': 'hip', 'ESTIMATIVA': 'est'}


def tag(t):
    return f'<span class="tag t-{TAGS[t]}">{t}</span>'


def tabela(cab, linhas, cls='', col=None):
    h = [f'<table class="tab {cls}">']
    if col:
        h.append('<colgroup>' + ''.join(f'<col style="width:{c}%">' for c in col) + '</colgroup>')
    h.append('<thead><tr>' + ''.join(f'<th>{c}</th>' for c in cab) + '</tr></thead><tbody>')
    for l in linhas:
        if isinstance(l, str):
            h.append(l)
        else:
            h.append('<tr>' + ''.join(f'<td>{c}</td>' for c in l) + '</tr>')
    h.append('</tbody></table>')
    return ''.join(h)


def kg(v, d=2):
    return milhar(v, d)


def so(pecas, *itens):
    return [p for p in pecas if p.item in itens or p.grupo in itens]


def desenha_oculto(svg, v, pecas):
    for p in pecas:
        aneis, _ = projeta(v, p)
        svg.aneis(aneis, 'hid')


def iso_no_retangulo(pecas, x0, y0, x1, y1, escala, az=-40.0, el=28.0):
    def extensao(cam):
        xs, ys = [], []
        for p in pecas:
            if p.estilo not in ('solid', 'ctx', 'ref'):
                continue
            bb = p.bbox()
            for x in bb[0]:
                for y in bb[1]:
                        for z in bb[2]:
                            q = cam.P((x, y, z))
                            xs.append(q[0])
                            ys.append(q[1])
        return xs, ys
    xs, ys = extensao(Iso(1.0, 0, 0, az, el))
    escala = max(escala, (max(xs) - min(xs)) / (x1 - x0), (max(ys) - min(ys)) / (y1 - y0))
    cam = Iso(escala, 0, 0, az, el)
    xs, ys = extensao(cam)
    cam.ox = (x0 + x1) / 2 - (min(xs) + max(xs)) / 2
    cam.oy = (y0 + y1) / 2 - (min(ys) + max(ys)) / 2
    return cam


def recorta_caixa(pecas, x=None, y=None, z=None):
    out = []
    for p in pecas:
        q = p
        for eixo, lim in (('x', x), ('y', y), ('z', z)):
            if lim is None or q is None:
                continue
            q = q.recortado(eixo, lim[0], 'ge')
            if q is not None:
                q = q.recortado(eixo, lim[1], 'le')
        if q is not None:
            out.append(q)
    return out


def triedro(svg, x, y, cam, L=10):
    o = cam.P((0, 0, 0))
    for nome, v in (('X', (1, 0, 0)), ('Y', (0, 1, 0)), ('Z', (0, 0, 1))):
        q = cam.P(v)
        dx, dy = q[0] - o[0], q[1] - o[1]
        n = math.hypot(dx, dy)
        dx, dy = dx / n * L, dy / n * L
        svg.ln(x, y, x + dx, y + dy, 'eixo')
        seta(svg, x + dx, y + dy, math.atan2(dy, dx), 'arrv')
        svg.tx(x + dx * 1.35, y + dy * 1.35 + 1.3, nome, T, peso=700, c='tx eixotx')
    svg.circ(x, y, 0.8, 'arrv')


def solo(svg, x0, x1, y):
    svg.ln(x0, y, x1, y, 'solo')
    i = x0
    while i < x1 - 1:
        svg.ln(i, y + 1.8, i + 1.8, y, 'hid0')
        i += 2.6


def explodido(dz_c=-120.0, dz_s=-240.0, dz_g=190.0, dz_t=330.0, dy_k=230.0, dx_k=230.0, rodas_ref=True,
              dz_n=-60.0):
    """Peças afastadas por grupo, na lógica da montagem."""
    lado = (lambda p: 1 if p.bbox()[1][0] + p.bbox()[1][1] > 0 else -1)
    ex = [p for p in quadro() if p.estilo == 'solid']
    for p in chapa_fundo():
        ex.append(p.movido(dz=dz_c + (dz_n if p.item == 'C-02' else 0)))
    for p in suportes():
        ex.append(p.movido(dz=dz_s, dy=90 * lado(p)))
    if rodas_ref:
        for p in rodas():
            ex.append(p.como('ref').movido(dz=dz_s, dy=90 * lado(p)))
    for p in gaiola() + suporte_lidar():
        ex.append(p.movido(dz=dz_g + (140 if p.item in ('G-06', 'G-08') else 0)))
    for p in carenagens():
        if p.item == 'K-01':
            ex.append(p.movido(dy=dy_k * lado(p)))
        elif p.item == 'K-02':
            ex.append(p.movido(dx=dx_k))
        elif p.item == 'K-03':
            ex.append(p.movido(dx=-dx_k))
        else:
            ex.append(p.movido(dz=dz_t))
    return ex


def plano_barras(svg, x0, y0, larg, pecas, barra=6000.0, kerf=3.0):
    """Plano de corte, primeira-que-cabe decrescente. pecas: [(item, comprimento)]."""
    barras = []
    for it, c in sorted(pecas, key=lambda t: -t[1]):
        for b in barras:
            if b['uso'] + c + kerf <= barra:
                b['p'].append((it, c))
                b['uso'] += c + kerf
                break
        else:
            barras.append({'p': [(it, c)], 'uso': c + kerf})
    k = larg / barra
    h = 7.0
    for i, b in enumerate(barras):
        y = y0 + i * 19
        svg.rect(x0, y, x0 + larg, y + h, 'barra0')
        x = x0
        corridas = []
        for it, c in b['p']:
            if corridas and corridas[-1][0] == it and abs(corridas[-1][1] - c) < 1e-6:
                corridas[-1][2] += 1
            else:
                corridas.append([it, c, 1])
        abaixo = 0
        for it, c, n in corridas:
            x_ini = x
            for _ in range(n):
                svg.rect(x, y, x + c * k, y + h, 'barra')
                x += (c + kerf) * k
            w = x - x_ini
            txt = f'{n}× {it} · {num(c)}' if n > 1 else f'{it} · {num(c)}'
            if w > len(txt) * T * 0.47 + 2:
                svg.tx(x_ini + w / 2, y + h / 2 + 1.3, txt, T)
            else:
                svg.tx(x_ini + w / 2 if abaixo == 0 else x_ini, y + h + 4.6, txt, T, c='tx sec',
                       a='middle' if abaixo == 0 else 'start')
                abaixo += 1
        svg.tx(x0 - 2, y + h / 2 + 1.3, f'Barra {i + 1}', T, a='end', peso=600)
        svg.tx(x0 + larg + 2, y + h / 2 + 1.3, f'sobra {milhar(barra - b["uso"])}', T, a='start', c='tx sec')
    cota_h(svg, x0, x0 + larg, y0 - 5, y0, y0, txt=f'{milhar(barra)} (barra comercial)')
    return len(barras)


# ========================================================== dados de apoio
def lista_corte(parte='A'):
    grupos = OrderedDict()
    for p in conjunto(parte):
        if p.estilo == 'ref':
            continue
        grupos.setdefault(p.item, []).append(p)
    out = OrderedDict()
    for item, ps in grupos.items():
        comp = Counter(round(p.comprimento(), 1) for p in ps)
        out[item] = dict(qtd=len(ps), comps=comp, massa=sum(p.massa() for p in ps), unit=ps[0].massa(), pecas=ps)
    return out


def verificacoes():
    c = comparacao_baseline()
    g = 9.81
    m_max = 126.0 + c['dm']
    FD, FL = 3.0, 0.5
    I_t = (30 ** 4 - 26 ** 4) / 12
    W_t = I_t / 15
    P = m_max * g * FD / 2
    s1 = P * 700 / 8 / (2 * W_t)
    q0 = m_max * g / 2 / 700
    d1 = 5 * q0 * 700 ** 4 / (384 * 69000 * 2 * I_t)
    Fv = m_max * g / 4 * FD
    Fl = FL * Fv
    e = M.BITOLA / 2 - (Y_FACE - M.E_PLACA / 2)
    M2 = Fl * 150 + Fv * e
    Ap, yp = 124 * 10, Y_FACE - 5
    Ag, yg = 2 * 8 * 30, Y_FACE - 10 - 15
    yb = (Ap * yp + Ag * yg) / (Ap + Ag)
    I2 = 124 * 10 ** 3 / 12 + Ap * (yp - yb) ** 2 + 2 * 8 * 30 ** 3 / 12 + Ag * (yg - yb) ** 2
    c2 = max(Y_FACE - yb, yb - (Y_FACE - 10 - 30))
    s2 = M2 / (I2 / c2)
    M3 = Fl * (Z_QUADRO - M.E_CHAPA) + Fv * e
    T3 = M3 / (Y_C - 130)
    p4 = 36.5 * g / (460 * 350) * FD
    L4 = 200.0
    s4 = (p4 * L4 ** 2 / 8) / (M.E_CHAPA ** 2 / 6)
    d4 = 5 * p4 * L4 ** 4 / (384 * 69300 * M.E_CHAPA ** 3 / 12)
    P5 = 36.5 * g * FD / 2
    M5 = (P5 / 2) * (Y_C - 350 / 4)
    s5 = M5 / (44700 / 28.8)
    t6 = 11.0 * m_max / 126.0
    return dict(m_max=m_max, s1=s1, d1=d1, s2=s2, Fv=Fv, e=e, T3=T3, s4=s4, d4=d4, s5=s5, t6=t6, c=c)


# ======================================================================== F01
def f01():
    F = Folha(1)
    pecas = conjunto() + [r.como('ref') for r in rodas()]
    cam = iso_no_retangulo(pecas, 214, 24, 408, 166, 5.9)
    desenha_iso(F.s, cam, pecas)
    triedro(F.s, 226, 180, cam)
    F.s.tx(240, 186, 'Referencial ISO 8855 (o da baseline)', T, a='start', c='tx sec')
    info = tabela(['Campo', 'Valor'], [
        ['Documento', f'<b>{DOC}</b> · {TOTAL} folhas A3 em 3 partes'],
        ['Revisão · data', f'0 — emissão inicial · {DATA}'],
        ['Base de cálculo', 'VTX-RV3-BASELINE-E (Rev E)'],
        ['Motor-roda', 'ElectroCraft MPW86 (datasheet 011121)'],
        ['Normas de desenho', 'ABNT NBR 10068, 10067, 8402, 10126, 12298'],
        ['Arquivos', 'Este PDF + pasta <b>dxf/</b> (peças planas 1:1)'],
        ['Parte A · 01–16', 'Chassi e gaiola — <b>pronto para cotar</b>'],
        ['Parte B · 17–22', 'Interfaces: mastro, câmeras, bateria, eletrônica, sensores'],
        ['Parte C · 23–27', 'Fechamento: pendências, massa, solda/FEA, validação, motor'],
    ], 'info', col=[34, 66])
    F.bloco(30, 24, 176, f'''
<p class="sobre">VALTEXA · ROVER V3 · CADERNO DE DESENHOS</p>
<h1 class="capa">Chassi estrutural<br>e gaiola de proteção</h1>
<p class="lead">Para o <b>fornecedor</b> cotar a fabricação e para o <b>engenheiro mecânico</b> validar o
projeto antes do corte do material.</p>
<div class="status"><b>Emitido para cotação e validação.</b> A fabricação começa só depois do parecer assinado
do engenheiro na folha 15.</div>
{info}''')
    tit = list(TITULOS.items())
    meio = 13
    idx = []
    for i in range(meio):
        a = tit[i]
        b = tit[i + meio] if i + meio < len(tit) else None
        idx.append([f'<b>{a[0]:02d}</b>', a[1][0]] + ([f'<b>{b[0]:02d}</b>', b[1][0]] if b else ['', '']))
    F.bloco(30, 158, 176, '<h3>Índice das folhas</h3>' +
            tabela(['Fl.', 'Título', 'Fl.', 'Título'], idx, 'indice', col=[7, 43, 7, 43]))
    F.bloco(214, 196, 194, '<h3>Etiquetas de origem dos valores</h3><div class="legenda">'
            f'<p>{tag("FONTE")}<span>ficha de fabricante</span></p>'
            f'<p>{tag("BASE")}<span>valor da baseline Rev E</span></p>'
            f'<p>{tag("CALC")}<span>calculado neste caderno</span></p>'
            f'<p>{tag("NOVO")}<span>proposto aqui, sujeito a aprovação</span></p>'
            f'<p>{tag("A VALIDAR")}<span>depende de fabricante ou ensaio</span></p>'
            '</div>')
    return F


# ======================================================================== F02
def f02():
    F = Folha(2)
    crit = [
        ['Entre-eixos (centros Ø88, mesmo lado)', '700 ± 1', tag('BASE')],
        ['Faces de montagem E–D (bitola 470)', '408 ± 1', tag('NOVO')],
        ['Centro Ø88 abaixo do quadro', '150 ± 0,5', tag('NOVO')],
        ['Diagonais dos 4 centros de roda', 'Δ ≤ 2', tag('NOVO')],
        ['Face de montagem ⊥ a A', '0,3', tag('NOVO')],
        ['Face de montagem // eixo X', '0,3', tag('NOVO')],
        ['Planicidade da face de montagem', '0,1', tag('NOVO')],
        ['Planicidade do anel superior', '1,5', tag('NOVO')],
        [f'Diagonais do quadro {num(L_Q)} × {num(W_Q)}', 'Δ ≤ 2', tag('NOVO')],
        ['Posição de furos a laser', '± 0,2', tag('NOVO')],
    ]
    F.bloco(30, 24, 118, '''
<h3>1 · Objeto do fornecimento</h3>
<p><b>1 conjunto</b> (protótipo):</p>
<ul>
<li><b>Q</b> — quadro soldado, tubo 30×30×2;</li>
<li><b>C</b> — chapa de fundo e 2 nervuras;</li>
<li><b>S</b> — 4 suportes do motor-roda (2 E, 2 D), soldados e usinados;</li>
<li><b>G</b> — gaiola: 2 módulos idênticos, tubo 20×20×1,5;</li>
<li><b>K</b> — 6 carenagens e 3 tampas;</li>
<li><b>M</b> — base dos mastros (luva e reforço), soldada ao quadro;</li>
<li><b>F</b> — fixadores inox e porcas-rebite instaladas.</li>
</ul>
<p>Cotar também o preço unitário para 3 conjuntos.</p>
<p><b>Parte B</b> (folhas 17 a 22) — haste do mastro, suportes de câmera, batentes da bateria, bandejas e
proteção do E-STOP: cotar em separado, lista na folha 21.</p>
<h3>2 · Fora do fornecimento</h3>
<p>Motores MPW86, bateria, eletrônica, sensores, cabeamento. Suspensão: não nesta revisão — suportes
rígidos.</p>
<h3>3 · Materiais</h3>
<ul>
<li>Tubos 30×30×2 e 20×20×1,5: Al 6061-T6 (ASTM B221).</li>
<li>Chapas 3, 5, 6, 8, 10: Al 6061-T6.</li>
<li>Chapas 1,2 e 2: Al 5052-H32 (ASTM B209).</li>
<li>Cantoneira 40×40×4, barra Ø12: Al 6061-T6.</li>
<li>Fixadores: inox A4 (folha 13).</li>
</ul>
<p>Enviar certificado de material.</p>''')
    F.bloco(154, 24, 118, '''
<h3>4 · Processos</h3>
<ul>
<li><b>Tubos:</b> serra, 90°, sem rebarba (planos de corte nas folhas 06 e 12).</li>
<li><b>Chapas:</b> laser/CNC pelos DXF da pasta <b>dxf/</b>.</li>
<li><b>Solda:</b> TIG, ER5356 (ER4043 se for pintar). Filete contínuo a2 nos tubos, a3 nos suportes.
Soldador qualificado para alumínio (AWS D1.2 / ISO 9606-2).</li>
<li><b>Gabarito:</b> quadro e módulos soldados em gabarito, sequência balanceada.</li>
<li><b>Suportes:</b> soldar, depois usinar a face B (Ra 3,2; final ≥ 9,5).</li>
<li><b>Porcas-rebite:</b> depois da solda e do acabamento.</li>
<li><b>Arestas:</b> quebrar cantos vivos ≥ 0,5; cantos externos de carenagens e tampas R3.</li>
</ul>
<h3>6 · Acabamento — cotar as 3 opções</h3>
<ul>
<li><b>A</b> natural, desengraxado.</li>
<li><b>B</b> anodização preta ≥ 15 µm (furos de dreno Ø4 em cavidades fechadas, posição a informar).</li>
<li><b>C</b> pintura eletrostática preta sobre conversão química.</li>
</ul>''')
    F.bloco(278, 24, 130, '''
<h3>5 · Tolerâncias</h3>
<p>Gerais: <b>ISO 13920-BF</b> (soldados) e <b>ISO 2768-mK</b> (corte e usinagem). Críticas (medir e
registrar):</p>
''' + tabela(['Característica', 'Valor', 'Origem'], crit, 'crit', col=[60, 20, 20]) + '''
<h3>7 · Inspeção e entrega</h3>
<ul>
<li>Relatório dimensional das críticas.</li>
<li>Inspeção visual das soldas (ISO 5817-C) e fotos.</li>
<li>Peças identificadas pelo código do item.</li>
</ul>
<h3>8 · Alterações</h3>
<p>Não alterar a geometria sem consulta. Alternativas mais baratas: propor com preço.</p>''')
    lc = lista_corte()
    resumo = []
    proc = {'Q': 'tubo + TIG', 'C': 'laser + rebite', 'S': 'laser + TIG + usinagem', 'G': 'tubo + TIG + laser',
            'K': 'laser', 'M': 'tubo + laser + TIG'}
    for g in ('Q', 'C', 'S', 'G', 'K', 'M'):
        itens = [i for i in lc if i.startswith(g)]
        resumo.append([f'<b>{g}</b>', GRUPOS[g], str(sum(lc[i]['qtd'] for i in itens)),
                       kg(sum(lc[i]['massa'] for i in itens), 2), proc[g]])
    resumo.append(['<b>F</b>', 'Fixadores e porcas-rebite', str(sum(q for (_, _, _, q, _) in fixadores())), '≈ 1,4',
                   'compra'])
    F.bloco(30, 196, 196, '<h3>Resumo por grupo</h3>' +
            tabela(['Grupo', 'Conjunto', 'Peças', 'kg', 'Processo'], resumo, 'compacta', col=[10, 42, 10, 11, 27]))
    return F


# ======================================================================== F03
def f03():
    F = Folha(3, escala='1:20', material='ver folha 14')
    pecas = conjunto()
    refs = rodas() + lidar_ref() + mastro_ref()
    vl = Vista('lateral', 20, 128, 140)
    vf = Vista('frontal', 20, 58, 140)
    vs = Vista('superior', 20, 128, 198)
    for v in (vl, vf):
        desenha(F.s, v, pecas + refs)
    desenha(F.s, vs, pecas + rodas() + lidar_ref())
    y0 = vl.P((0, 0, 0))[1]
    for v, x0, x1 in ((vl, 96, 162), (vf, 38, 78)):
        solo(F.s, x0, x1, y0)
    for xc in (-XS, XS):
        linha_centro(F.s, *vl.P((xc, 0, -20)), *vl.P((xc, 0, 222)))
    a, b = vl.P((-XS, 0, 0)), vl.P((XS, 0, 0))
    cota_h(F.s, a[0], b[0], y0 + 9, None, None, valor=700)
    a, b = vl.P((-L_EXT / 2, -300, Z_QUADRO)), vl.P((L_EXT / 2, -300, Z_QUADRO))
    cota_h(F.s, a[0], b[0], y0 + 17, a[1], b[1], valor=L_EXT)
    xr = vl.P((L_EXT / 2, 0, 0))[0]
    for i, z in enumerate((Z_EIXO, Z_QUADRO, Z_DECK, Z_PROT, M.Z_TOTAL)):
        a = vl.P((L_EXT / 2 if z < 1000 else 0, 0, z))
        cota_v(F.s, y0, a[1], xr + 8 + i * D, None, a[0], valor=z)
    cota_vista_h(F.s, vf, (0, -W_EXT / 2, 0), (0, W_EXT / 2, 0), y0 + 9)
    cota_vista_h(F.s, vf, (0, -235, 0), (0, 235, 0), y0 + 17)
    F.s.tx(vl.P((0, 0, 1100))[0] + 2.5, vl.P((0, 0, 1100))[1], 'mastro (ref.)', T, a='start', c='tx sec')
    rotulo(F.s, vl.P((0, 0, 0))[0], y0 + 29, 'VISTA LATERAL DIREITA', '1:20')
    rotulo(F.s, vf.P((0, 0, 0))[0], y0 + 29, 'VISTA FRONTAL', '1:20')
    cota_vista_v(F.s, vs, (-L_EXT / 2, -W_EXT / 2, 0), (-L_EXT / 2, W_EXT / 2, 0), vs.P((-L_EXT / 2, 0, 0))[0] - 8)
    rotulo(F.s, vs.P((0, 0, 0))[0], vs.P((0, -300, 0))[1] + 11, 'VISTA SUPERIOR', '1:20')
    # isométrica sem a carenagem lateral direita
    pi = [p for p in conjunto() if not (p.item == 'K-01' and p.bbox()[1][0] < 0)] + [r.como('ref') for r in rodas()]
    cam = iso_no_retangulo(pi, 214, 30, 406, 160, 8.6)
    desenha_iso(F.s, cam, pi)
    alvos = [('Q', (-150, -W_Q / 2, 325), (-8, -24), 'Quadro'),
             ('C', (-470, -W_Q / 2, 249), (-22, 12), 'Chapa de fundo'),
             ('S', (-XS, -Y_FACE, 175), (-14, 30), 'Suporte'),
             ('G', (160, -W_Q / 2, 390), (8, -24), 'Gaiola'),
             ('K', (L_EXT / 2, 120, 300), (26, 14), 'Carenagem'),
             ('R', (XS, -261, 100), (20, 24), 'MPW86 (ref.)')]
    for cod, p, (dx, dy), txt in alvos:
        a = cam.P(p)
        bx, by = a[0] + dx, a[1] + dy
        balao(F.s, bx, by, cod, alvo=a)
        F.s.tx(bx, by + (9.4 if dy >= 0 else -6.4), txt, T, c='tx sec')
    rotulo(F.s, 310, 172, 'ISOMÉTRICA', 'sem escala', 'carenagem lateral direita omitida')
    base = [
        ['Envelope externo C × L', f'{milhar(L_EXT)} × {num(W_EXT)}', tag('BASE')],
        ['Quadro + carenagens de 2', f'{milhar(L_Q)} × {num(W_Q)} + 2 × 2', tag('CALC')],
        ['Entre-eixos / bitola', '700 / 470', tag('BASE')],
        ['Face inferior / deck', 'Z 250 / Z 340', tag('BASE')],
        ['Topo do corpo', f'Z {num(Z_FAIXA, 1)} ≤ 400', tag('BASE')],
        ['Vão livre (entre rodas)', '150 (menor: Z 208)', tag('A VALIDAR')],
    ]
    F.bloco(214, 190, 194, '<h3>Números de partida (baseline Rev E)</h3>' +
            tabela(['Grandeza', 'Valor (mm)', 'Origem'], base, 'compacta', col=[46, 34, 20]))
    return F


# ======================================================================== F04
def f04():
    F = Folha(4, escala='1:5', material='Al 6061-T6 · tubo 30×30×2')
    Q = quadro()
    vl = Vista('lateral', 5, 283, 130)
    vf = Vista('frontal', 5, 92, 130)
    vs = Vista('superior', 5, 283, 172)
    for v in (vl, vf, vs):
        desenha(F.s, v, Q)
    top = vl.P((0, 0, Z_DECK))[1]
    # ---- lateral: montantes a partir do centro (simétrico)
    linha_centro(F.s, *vl.P((0, 0, 236)), *vl.P((0, 0, 346)))
    for i, xc in enumerate((XS / 2, XS, X_CANTO)):
        for sx in (1, -1):
            linha_centro(F.s, *vl.P((sx * xc, 0, 240)), *vl.P((sx * xc, 0, 346)))
        a, b = vl.P((0, 0, 346)), vl.P((xc, 0, 346))
        cota_h(F.s, a[0], b[0], top - 8 - i * D, a[1], b[1], valor=xc)
    a, b = vl.P((-XQ, 0, Z_DECK)), vl.P((XQ, 0, Z_DECK))
    cota_h(F.s, a[0], b[0], top - 8 - 3 * D, a[1], b[1], valor=L_Q)
    F.s.tx(vl.P((0, 0, 0))[0] - 3, top - 12, 'simétrico', T, a='end', c='tx sec')
    rotulo(F.s, 283, 92, 'VISTA LATERAL DIREITA', '1:5')
    balao(F.s, 340, 96, 'Q-04', alvo=vl.P((XS / 2, -YQ, 295)))
    balao(F.s, 402, 94, 'Q-06', alvo=vl.P((XQ - 1, -YQ, 265)))
    # ---- frontal
    xd = vf.P((0, YQ, 0))[0]
    for (z0, z1) in ((250, 280), (280, 310), (310, 340)):
        cota_vista_v(F.s, vf, (0, YQ, z0), (0, YQ, z1), xd + 8)
    cota_vista_v(F.s, vf, (0, YQ, 250), (0, YQ, 340), xd + 16)
    cota_vista_h(F.s, vf, (0, -YQ, 250), (0, YQ, 250), vf.P((0, 0, 250))[1] + 9)
    cota_vista_h(F.s, vf, (0, -YQ, 340), (0, -YQ + TQ, 340), top - 8, lado_txt=1)
    linha_centro(F.s, *vf.P((0, 0, 236)), *vf.P((0, 0, 354)))
    rotulo(F.s, 92, 104, 'VISTA FRONTAL', '1:5', 'traseira: simétrica')
    # ---- superior
    for xc in (-XS, XS):
        linha_centro(F.s, *vs.P((xc, YQ + 12, 0)), *vs.P((xc, -YQ - 6, 0)))
    linha_centro(F.s, *vs.P((0, YQ + 6, 0)), *vs.P((0, -YQ - 6, 0)))
    linha_centro(F.s, *vs.P((-XQ - 8, 0, 0)), *vs.P((XQ + 8, 0, 0)))
    a, b = vs.P((-XS, YQ + 12, 0)), vs.P((XS, YQ + 12, 0))
    cota_h(F.s, a[0], b[0], a[1] - 5, None, None, txt='700 (entre-eixos)')
    x_esq = vs.P((-XQ, 0, 0))[0]
    cota_vista_v(F.s, vs, (-XQ, -YQ + TQ, 0), (-XQ, YQ - TQ, 0), x_esq - 8)
    cota_vista_v(F.s, vs, (-XQ, -YQ, 0), (-XQ, YQ, 0), x_esq - 16)
    rotulo(F.s, x_esq, vs.P((0, -YQ, 0))[1] + 11, 'VISTA SUPERIOR', '1:5', a='start')
    balao(F.s, 402, 122, 'Q-01', alvo=vs.P((440, Y_C, 0)))
    balao(F.s, 402, 168, 'Q-02', alvo=vs.P((X_CANTO, 60, 0)))
    balao(F.s, 402, 214, 'Q-03', alvo=vs.P((XS, -150, 0)))
    # ---- seção típica 1:1
    x0, y0 = 50, 134
    F.s.rect(x0, y0, x0 + 30, y0 + 30, 'hach')
    F.s.rect(x0 + 2, y0 + 2, x0 + 28, y0 + 28, 'vazio')
    cota_h(F.s, x0, x0 + 30, y0 - 8, y0, y0, valor=30)
    cota_v(F.s, y0, y0 + 30, x0 - 8, x0, x0, valor=30)
    chamada(F.s, x0 + 29, y0 + 16, x0 + 40, y0 + 8, 'e = 2', ponta='seta')
    rotulo(F.s, x0 + 15, y0 + 42, 'SEÇÃO TÍPICA', '1:1', 'Q-01 a Q-04')
    F.bloco(30, 202, 124, f'''
<h3>Notas do quadro</h3>
<ol class="notas">
<li>Tubo 30×30×2, Al 6061-T6; cortes retos a 90°. Filete contínuo a2, todo o contorno (TIG, ER5356).</li>
<li>Anéis Z 250→280 e Z 310→340, ligados por 16 montantes Q-04 de 30.</li>
<li>Quadro {num(L_Q)} × {num(W_Q)}: com as carenagens de 2, o envelope é {milhar(L_EXT)} × {num(W_EXT)}.</li>
<li>Buchas Q-05 e porcas-rebite: folhas 05 e 08.</li>
</ol>''')
    return F


# ======================================================================== F05
def f05():
    F = Folha(5, escala='1:5 · 1:1 · 1:20', material='ver lista de materiais')
    pecas = quadro() + chapa_fundo() + suportes()
    refs = rodas()
    vb = Vista('lateral', 5, 166, 110)
    desenha_corte(F.s, vb, pecas + refs, 'y', 0.0)
    y0 = vb.P((0, 0, 0))[1]
    solo(F.s, 56, 276, y0)
    for xc in (-XS, XS):
        cruz_centro(F.s, *vb.P((xc, 0, Z_EIXO)), 20)
    a, b = vb.P((-XS, 0, 0)), vb.P((XS, 0, 0))
    cota_h(F.s, a[0], b[0], y0 + 9, None, None, txt='700 (entre-eixos)')
    xl = vb.P((-XQ, 0, 0))[0]
    for i, z in enumerate((Z_EIXO, Z_QUADRO, Z_DECK)):
        a = vb.P((-XQ, 0, z))
        cota_v(F.s, y0, a[1], xl - 8 - i * D, None, a[0], valor=z)
    chamada(F.s, *vb.P((-M.X_NERV, 0, 215)), 120, 127, 'C-02 (seção)', lado=-1)
    chamada(F.s, *vb.P((40, 0, 249)), 176, 127, 'C-01 e = 2', lado=1)
    rotulo(F.s, 166, 139, 'CORTE B-B', '1:5', 'plano Y 0, visto de −Y')
    va = Vista('frontal', 5, 346, 110)
    desenha_corte(F.s, va, pecas + refs, 'x', XS)
    solo(F.s, 282, 410, y0)
    for s in (1, -1):
        cruz_centro(F.s, *va.P((XS, s * 235, Z_EIXO)), 20)
    cota_vista_h(F.s, va, (0, -235, 100), (0, 235, 100), y0 + 9, txt='470 (bitola)')
    cota_vista_h(F.s, va, (0, -Y_FACE, 30), (0, Y_FACE, 30), y0 + 17, txt='408 ± 1')
    cota_vista_h(F.s, va, (0, -YQ, Z_DECK), (0, YQ, Z_DECK), va.P((0, 0, Z_DECK))[1] - 9)
    a, b = va.P((0, -YQ, 100)), va.P((0, -YQ, Z_QUADRO))
    cota_v(F.s, a[1], b[1], va.P((0, -YQ, 0))[0] - 8, None, b[0], txt='150 ± 0,5')
    rotulo(F.s, 346, 139, 'CORTE A-A', '1:5', 'plano X +350, visto de +X')
    # ---- planta-chave 1:20
    vk = Vista('superior', 20, 64, 174)
    desenha(F.s, vk, quadro() + chapa_fundo())
    a, b = vk.P((-XQ - 40, 0, 0)), vk.P((XQ + 40, 0, 0))
    plano_corte(F.s, a[0], a[1], b[0], b[1], 'B', -math.pi / 2)
    a, b = vk.P((XS, -YQ - 30, 0)), vk.P((XS, YQ + 30, 0))
    plano_corte(F.s, a[0], a[1], b[0], b[1], 'A', math.pi)
    e = vk.P((XS + 45, Y_C, 0))
    F.s.circ(e[0], e[1], 2.6, 'marcador')
    F.s.tx(e[0] + 3.4, e[1] - 3.0, 'E', 5.0, peso=700)
    rotulo(F.s, 64, 208, 'PLANTA-CHAVE', '1:20')
    # ---- detalhe E 1:1
    wx0, wy0, wx1, wy1 = 112, 160, 154, 224
    F.recorte('cpE', wx0, wy0, wx1, wy1)
    vE = Vista('frontal', 1, wx0 - (Y_C - 21), wy0 + 293)
    sv = Svg()
    desenha_corte(sv, vE, pecas, 'x', XS + 45)
    F.s.raw(f'<g clip-path="url(#cpE)">{sv}</g>')
    F.s.rect(wx0, wy0, wx1, wy1, 'janela')

    def P(y, z):
        return vE.P((XS + 45, y, z))
    yc = Y_C
    for (ya, yb, za, zb) in ((yc - 6.5, yc + 6.5, 232.4, 240.4), (yc - 8, yc + 8, 240.4, 242.0),
                             (yc - 4, yc + 4, 240.4, 292.0), (yc - 8, yc + 8, 280.0, 281.6),
                             (yc - 6.5, yc + 6.5, 281.6, 289.6)):
        a, b = P(ya, za), P(yb, zb)
        F.s.rect(a[0], a[1], b[0], b[1], 'vis')
    linha_centro(F.s, *P(yc, 228), *P(yc, 295))
    chamada(F.s, *P(yc + 6.5, 236), 160, 220, ['F-01 M8×55', 'F-02, F-03'], lado=1)
    chamada(F.s, *P(yc - 5, 262), 160, 196, 'Q-05 bucha', lado=1)
    chamada(F.s, *P(yc + 12, 245), 160, 208, 'S-01 + C-01', lado=1)
    chamada(F.s, *P(yc + 13.5, 276), 160, 172, 'Q-01', lado=1)
    rotulo(F.s, 133, 234, 'DETALHE E', '1:1')
    # ---- detalhe D (iso do canto)
    canto = recorta_caixa([p for p in quadro() if p.estilo == 'solid'], x=(XQ - 112, XQ + 1), y=(150, YQ + 1))
    camD = iso_no_retangulo(canto, 36, 218, 94, 256, 2.6)
    desenha_iso(F.s, camD, canto)
    rotulo(F.s, 65, 266, 'DETALHE D', 'sem escala', 'canto dianteiro esquerdo')
    niveis = [
        ['38', 'Ponto mais baixo do suporte S-02', tag('NOVO')],
        ['100', 'Eixo das rodas', tag('FONTE')],
        ['150', 'Vão livre de projeto', tag('BASE')],
        ['208', 'Nervuras C-02 (mais baixo entre rodas)', tag('NOVO')],
        ['242 → 248', 'Chapa superior do suporte S-01', tag('NOVO')],
        ['248 → 250', 'Chapa de fundo (apoio da bateria)', tag('NOVO')],
        ['250 → 280', 'Anel inferior do quadro', tag('BASE')],
        ['310 → 340', 'Anel superior (deck Z 340)', tag('BASE')],
        [f'{num(Z_G0)} → {num(Z_G1)}', 'Montantes da gaiola', tag('NOVO')],
        [f'{num(Z_G1)} → {num(Z_G2)}', 'Anel da gaiola', tag('NOVO')],
        [f'{num(Z_G2)} → {num(Z_FAIXA, 1)}', 'Tampas + faixa central (≤ 400)', tag('BASE')],
        [num(Z_BASE_LIDAR, 1), 'Base do LiDAR (sobre coxins)', tag('NOVO')],
    ]
    F.bloco(240, 150, 168, '<h3>Níveis Z (mm, a partir do solo)</h3>' +
            tabela(['Z', 'Elemento', 'Origem'], niveis, 'compacta', col=[21, 60, 19]))
    return F


# ======================================================================== F06
def f06():
    F = Folha(6, escala='sem escala', material='Al 6061-T6')
    Q = [p for p in quadro() if p.estilo == 'solid']
    cam = iso_no_retangulo(Q, 36, 30, 226, 142, 6.2)
    desenha_iso(F.s, cam, Q)
    alvos = [('Q-01', (-200, -YQ, 340), (-14, 20)), ('Q-02', (X_CANTO, 0, 340), (22, -14)),
             ('Q-03', (-XS, 100, 340), (-16, -16)), ('Q-04', (XS / 2, -YQ, 295), (8, 24)),
             ('Q-06', (XQ, -Y_C, 325), (24, 8))]
    for cod, p, (dx, dy) in alvos:
        a = cam.P(p)
        balao(F.s, a[0] + dx, a[1] + dy, cod, alvo=a)
    rotulo(F.s, 130, 156, 'QUADRO — ISOMÉTRICA', 'sem escala', 'buchas Q-05 dentro do anel inferior')
    lc = lista_corte()
    linhas, pecas_tubo = [], []
    for item in ('Q-01', 'Q-02', 'Q-03', 'Q-04', 'Q-05', 'Q-06'):
        d = lc[item]
        it = ITENS[item]
        if item in ('Q-01', 'Q-02', 'Q-03', 'Q-04'):
            for c, n in d['comps'].items():
                pecas_tubo += [(item, c)] * n
        linhas.append([f'<b>{item}</b>', it['nome'], ', '.join(num(c) for c in d['comps']), str(d['qtd']),
                       kg(d['massa'], 2)])
    massa_q = sum(lc[i]['massa'] for i in ('Q-01', 'Q-02', 'Q-03', 'Q-04', 'Q-05', 'Q-06'))
    linhas.append(['', '<b>Total do quadro</b>', '', '', f'<b>{kg(massa_q, 2)}</b>'])
    total = sum(c for _, c in pecas_tubo)
    F.bloco(240, 24, 168, '<h3>Lista de corte — quadro</h3>' + tabela(
        ['Item', 'Peça', 'Corte (mm)', 'Qtd', 'kg'], linhas, 'corte', col=[12, 46, 17, 10, 15]) +
        f'<p class="mini">Tubo 30×30×2: {milhar(total / 1000, 2)} m de peças. Q-01 = {num(L_Q)} − 2 × 2 (tampas '
        f'Q-06). Massas {tag("CALC")}, ρ = 2,70 g/cm³.</p>')
    F.bloco(240, 114, 168, '<h3>Plano de corte — tubo 30×30×2</h3>', h=10)
    nb = plano_barras(F.s, 262, 136, 128, pecas_tubo)
    F.s.tx(240.5, 136 + nb * 19 + 6, f'{nb} barras de 6 m, serra de 3 mm.', T, a='start', c='tx sec')
    # junta em T (seção esquemática) com o símbolo de solda
    F.s.rect(36, 196, 72, 205, 'hach')
    F.s.rect(49, 178, 59, 196, 'hach2')
    for (xa, sgn) in ((49, -1), (59, 1)):
        F.s.pl([(xa, 196), (xa + sgn * 2.6, 196), (xa, 193.4)], 'cheio', True)
    simbolo_solda(F.s, 46.6, 194.6, 76, 182, a='a2', cauda='TIG · ER5356', comp=44)
    rotulo(F.s, 104, 218, 'SÍMBOLO DE SOLDA', 'sem escala', 'ISO 2553 · filete a2, todo o contorno')
    F.bloco(30, 234, 198, '''
<h3>Sequência de soldagem</h3>
<ol class="notas">
<li>Anéis no gabarito; pontear em cruz; conferir diagonais.</li>
<li>Montantes com calço de 30; conferir paralelismo e soldar.</li>
<li>Tampas Q-06 e buchas Q-05; facear; medir antes do acabamento.</li>
</ol>''')
    F.bloco(240, 186, 168, '''
<h3>Juntas</h3>
<p>Topo e T entre tubos 30×30, cortes retos, filete nos 4 lados. Na ZTA o 6061-T6 perde ~40 % da resistência:
o engenheiro decide se aceita como soldado (folha 15).</p>''')
    return F


# ======================================================================== F07
def f07():
    F = Folha(7, escala='1:2', material='Al 6061-T6 · chapas 6, 8 e 10',
              tolerancia='ISO 13920-BF · ISO 2768-mK')
    S = suporte(XS, 1)
    ref = mpw86_ref(XS, 1)
    # ---- vista da face de montagem (principal)
    vp = Vista('lateral_e', 2, 280, 160)
    desenha(F.s, vp, S + ref)
    c = vp.P((XS, Y_FACE, Z_EIXO))
    cruz_centro(F.s, c[0], c[1], 22)
    F.s.circ(c[0], c[1], M.MPW_PCD / 2 * 0.5, 'cl')
    a, b = vp.P((XS - 70, YQ, 248)), vp.P((XS + 70, YQ, 248))
    cota_h(F.s, a[0], b[0], 21, a[1], b[1], valor=140)
    a, b = vp.P((XS - 62, Y_FACE, 100)), vp.P((XS + 62, Y_FACE, 100))
    cota_h(F.s, a[0], b[0], 160, a[1], b[1], valor=124)
    xr = vp.P((XS - 70, 0, 0))[0] + 8
    a, b = vp.P((XS - 62, Y_FACE, 100)), vp.P((XS - 62, Y_FACE, 242))
    cota_v(F.s, a[1], b[1], xr, c[0] + 24, b[0], valor=142)
    cota_v(F.s, vp.P((0, 0, 242))[1], vp.P((0, 0, 248))[1], xr, a[0], a[0], valor=6, lado_txt=-1)
    plano_corte(F.s, *vp.P((XS, Y_FACE, 254)), *vp.P((XS, Y_FACE, 30)), 'A', 0.0)
    ang = math.radians(35)
    r = M.D_BORE / 2 * 0.5
    chamada(F.s, c[0] + r * math.cos(ang), c[1] + r * math.sin(ang), 146, 132, ['Ø88 +0,5/0', 'passante'],
            ponta='seta')
    fcf(F.s, 146, 140, 'pos', 'Ø0,3', ('B',))
    t0 = math.radians(90 + 360 / 7)
    hx, hy = vp.P((XS + 47.5 * math.cos(t0), Y_FACE, Z_EIXO + 47.5 * math.sin(t0)))
    chamada(F.s, hx, hy, 66, 70, ['7× Ø4,5 eq. esp.', 'sobre Ø95 (MPW86)'], ponta='seta', lado=-1)
    fcf(F.s, 32, 80, 'pos', 'Ø0,2', ('B', 'C'))
    rb = vp.P((XS + 62 * math.cos(math.radians(-60)), Y_FACE, Z_EIXO + 62 * math.sin(math.radians(-60))))
    chamada(F.s, rb[0], rb[1], 64, 146, 'R62', ponta='seta', lado=-1)
    referencia(F.s, c[0] + 22.6, c[1], 'C', 0.0)
    F.s.tx(30, 32, '← frente (+X)', T, a='start', c='tx sec')
    rotulo(F.s, 105, 170, 'VISTA DA FACE (DE +Y)', '1:2')
    # ---- vista de +X
    vf = Vista('frontal', 2, 130, 160)
    desenha(F.s, vf, S)
    a, b = vf.P((0, 110, 248)), vf.P((0, YQ, 248))
    cota_h(F.s, a[0], b[0], 21, a[1], b[1], valor=YQ - 110)
    a, b = vf.P((0, 110, 242)), vf.P((0, Y_FACE - 10, 242))
    cota_h(F.s, a[0], b[0], 29, None, b[1], valor=Y_FACE - 10 - 110)
    a, b = vf.P((0, Y_FACE, 248)), vf.P((0, YQ, 248))
    cota_h(F.s, a[0], b[0], 29, a[1], b[1], valor=YQ - Y_FACE)
    a, b = vf.P((0, Y_FACE - 40, 150)), vf.P((0, Y_FACE - 10, 150))
    cota_h(F.s, a[0], b[0], 96, a[1], b[1], valor=30)
    a, b = vf.P((0, Y_FACE - 10, 150)), vf.P((0, Y_FACE, 150))
    cota_h(F.s, a[0], b[0], 104, a[1], b[1], txt='10')
    xg = vf.P((0, 110, 0))[0]
    a, b = vf.P((0, 110, 150)), vf.P((0, 110, 242))
    cota_v(F.s, a[1], b[1], xg - 8, a[0] + 27, b[0], valor=92)
    a, b = vf.P((0, 110, 230)), vf.P((0, 110, 242))
    cota_v(F.s, a[1], b[1], xg - 16, b[0], b[0], valor=12, lado_txt=-1)
    face = vf.P((0, Y_FACE, 200))
    F.s.ln(face[0], face[1], 250, face[1], 'gdt')
    seta(F.s, face[0], face[1], math.pi)
    fcf(F.s, 250, face[1] - 6, 'plan', '0,1')
    fcf(F.s, 250, face[1], 'perp', '0,3', ('A',))
    referencia(F.s, *vf.P((0, Y_FACE, 104)), 'B', 0.0)
    fr = vf.P((0, Y_FACE, 160))
    F.s.ln(fr[0], fr[1], 248, fr[1] + 10, 'gdt')
    seta(F.s, fr[0], fr[1], math.atan2(-10, fr[0] - 248))
    F.s.ln(248, fr[1] + 10, 266, fr[1] + 10, 'gdt')
    rugosidade(F.s, 252, fr[1] + 10, 'Ra 3,2')
    chamada(F.s, *vf.P((0, 150, 196)), 200, 116, 'S-03', lado=-1)
    rotulo(F.s, 232, 172, 'VISTA DE +X', '1:2', 'face B em Y 204')
    # ---- corte A-A
    va = Vista('frontal', 2, 245, 160)
    desenha_corte(F.s, va, S + ref, 'x', XS)
    simbolo_solda(F.s, *va.P((0, 150, 242)), 302, 29, a='a3', cauda='todas as juntas', comp=30)
    referencia(F.s, *va.P((0, 290, 248)), 'A', -math.pi / 2)
    rotulo(F.s, 347, 172, 'CORTE A-A', '1:2', 'plano X = eixo do Ø88')
    # ---- vista superior (abaixo da principal)
    vs = Vista('superior_inv', 2, 280, 128)
    desenha(F.s, vs, so(S, 'S-01'))
    desenha_oculto(F.s, vs, so(S, 'S-02', 'S-03'))
    for (dx, ay) in M.FUROS_SUPORTE:
        cruz_centro(F.s, *vs.P((XS + dx, ay, 248)), 2.1)
    a, b = vs.P((XS - 45, Y_C, 0)), vs.P((XS + 45, Y_C, 0))
    cota_h(F.s, a[0], b[0], 284, a[1], b[1], valor=90)
    xr2 = vs.P((XS - 70, 0, 0))[0]
    for i, ay in enumerate((Y_C, 240, 130)):
        a, b = vs.P((XS - 70, YQ, 0)), vs.P((XS, ay, 0))
        cota_v(F.s, a[1], b[1], xr2 + 8 + i * D, a[0], b[0], valor=YQ - ay, lado_txt=-1)
    chamada(F.s, *vs.P((XS + 45, Y_C, 0)), 62, 258, ['4× Ø8,5', 'passante'], lado=-1)
    rotulo(F.s, 47, 200, 'VISTA SUPERIOR', '1:2', 'S-02 e S-03 ocultos')
    # ---- isométrica
    pi = S + [r.como('ref') for r in ref]
    cam = iso_no_retangulo(pi, 336, 190, 406, 234, 3.9, az=-130, el=24)
    desenha_iso(F.s, cam, pi)
    for cod, p, (dx, dy) in (('S-01', (XS, 250, 248), (-12, 2)), ('S-02', (XS - 30, 199, 180), (-14, 8)),
                             ('S-03', (XS + 58, 150, 190), (12, -4))):
        a = cam.P(p)
        balao(F.s, a[0] + dx, a[1] + dy, cod, alvo=a)
    F.bloco(174, 186, 156, f'''
<h3>Notas do suporte</h3>
<ol class="notas">
<li>Dianteiro esquerdo desenhado; direitos espelhados (2 E + 2 D).</li>
<li>Soldar S-02 e S-03 em S-01 (a3); depois usinar a face B.</li>
<li>A = topo de S-01 · B = face de montagem · C = eixo do Ø88.</li>
<li>{tag("A VALIDAR")} com a ElectroCraft: orientação dos 7 furos, folga face–roda, motor com freio.</li>
</ol>''')
    return F


# ======================================================================== F08
def f08():
    F = Folha(8, escala='1:5 · 1:1', material='C-01 Al 5052-H32 e = 2 · C-02 Al 6061-T6')
    C = chapa_fundo()
    vs = Vista('superior', 5, 150, 104)
    desenha(F.s, vs, so(C, 'C-01'))
    desenha_oculto(F.s, vs, so(C, 'C-02'))
    for (x, y, d, fn) in furos_chapa():
        if d >= 10:
            cruz_centro(F.s, *vs.P((x, y, 250)), d / 10)
    linha_centro(F.s, *vs.P((0, YQ + 8, 0)), *vs.P((0, -YQ - 8, 0)))
    linha_centro(F.s, *vs.P((-XQ - 8, 0, 0)), *vs.P((XQ + 8, 0, 0)))
    cota_vista_h(F.s, vs, (-XQ, YQ, 0), (XQ, YQ, 0), vs.P((0, YQ, 0))[1] - 9)
    cota_vista_v(F.s, vs, (-XQ, -YQ, 0), (-XQ, YQ, 0), vs.P((-XQ, 0, 0))[0] - 8)
    tipos = OrderedDict()
    for (x, y, d, fn) in furos_chapa():
        tipos.setdefault((d, fn), []).append((x, y))
    letra = {k: 'ABCDEFGH'[i] for i, k in enumerate(tipos)}
    alvo_de = {'A': (X_CANTO, Y_C), 'B': (M.X_NERV, Y_C), 'C': (XS + 45, Y_C), 'D': (M.X_NERV, 135.0),
               'E': (430.0, 200.0), 'F': (300.0, 80.0), 'G': (-245.0, -40.0),
               'H': (M.JANELA_RAIZ[0] - 13, -72.0)}
    pos = {'A': (-12, 12), 'B': (12, 12), 'C': (-12, 12), 'D': (13, 6), 'E': (-12, 12), 'F': (-13, 10),
           'G': (-13, 10), 'H': (12, 12)}
    for k in tipos:
        L = letra[k]
        a = vs.P((*alvo_de[L], 250))
        dx, dy = pos[L]
        balao(F.s, a[0] + dx, a[1] + dy, L, alvo=a)
    chamada(F.s, *vs.P((430.0, -60.0, 250)), 150, 162,
            ['abertura 70 × 120 —', 'câmera de raiz (folha 22)'], lado=-1)
    rotulo(F.s, 150, 176, 'C-01 — VISTA SUPERIOR', '1:5', 'nervuras C-02 tracejadas, sob a chapa')
    linhas = []
    for k, pts in tipos.items():
        d, fn = k
        pares = sorted({(abs(p[0]), abs(p[1])) for p in pts})
        coord = ' · '.join(f'(±{num(x)}; ±{num(y)})'.replace('±0;', '0;').replace('±0)', '0)') for x, y in pares)
        linhas.append([f'<b>{letra[k]}</b>', f'Ø{num(d)}', str(len(pts)), coord])
    F.bloco(262, 24, 146, '<h3>Furos da C-01 (X; Y a partir do centro)</h3>' +
            tabela(['Tipo', 'Ø', 'Qtd', 'Coordenadas'], linhas, 'furos', col=[11, 13, 10, 66]) +
            '<p class="mini">A: porca-rebite M6 no anel · B: ponta da nervura · C: M8 do suporte · D: rebite · '
            'E: dreno · F: passa-cabo · G: malha de montagem (folhas 20 a 22) · H: janela da câmera de raiz. '
            'Ø13 = folga para a cabeça da porca-rebite; Ø9 = porca-rebite M6 instalada na própria chapa.</p>')
    # nervura C-02
    yn = M.YQ - 2
    y0n, xc = 240, 100
    x0n, x1n = xc - yn * 0.2, xc + yn * 0.2
    F.s.rect(x0n, y0n - 4, x1n, y0n + 4, 'vis')
    F.s.ln(x0n, y0n - 3.2, x1n, y0n - 3.2, 'visl')
    for y in (-Y_C, Y_C):
        F.s.circ(xc + y * 0.2, y0n, 6.6 * 0.1, 'vism')
    for y in (-225, -135, -45, 45, 135, 225):
        F.s.circ(xc + y * 0.2, y0n, 4.9 * 0.1, 'vism')
    cota_h(F.s, x0n, x1n, y0n + 12, y0n + 4, y0n + 4, valor=2 * yn)
    cota_h(F.s, xc - Y_C * 0.2, xc + Y_C * 0.2, y0n - 12, y0n, y0n, valor=2 * Y_C, desloc_txt=-22)
    for i, y in enumerate((45, 135, 225)):
        cota_h(F.s, xc, xc + y * 0.2, y0n - 20 - i * D, y0n if i == 0 else None, y0n, valor=y)
    linha_centro(F.s, xc, y0n - 42, xc, y0n + 6)
    rotulo(F.s, xc, 266, 'C-02 NERVURA', '1:5', '2 peças · 2× Ø6,6 + 6× Ø4,9')
    # corte na fixação da nervura
    wx0, wy0, wx1, wy1 = 174, 194, 232, 234
    F.recorte('cpN', wx0, wy0, wx1, wy1)
    vN = Vista('lateral', 1, wx0 - 92, wy0 + 258)
    sv = Svg()
    desenha_corte(sv, vN, quadro() + C, 'y', Y_C)
    F.s.raw(f'<g clip-path="url(#cpN)">{sv}</g>')

    def pN(x, z):
        return vN.P((x, Y_C, z))
    X = M.X_NERV
    for (xa, xb, za, zb) in ((X - 4.5, X + 4.5, 252, 264), (X - 6, X + 6, 249.4, 250),
                             (X - 3, X + 3, 228.4, 262.4), (X - 9, X + 9, 242.4, 244),
                             (X - 5.25, X + 5.25, 239.1, 242.4)):
        a, b = pN(xa, za), pN(xb, zb)
        F.s.rect(a[0], a[1], b[0], b[1], 'vis')
    linha_centro(F.s, *pN(X, 236), *pN(X, 266))
    F.s.rect(wx0, wy0, wx1, wy1, 'janela')
    rotulo(F.s, 203, 246, 'CORTE NA NERVURA', '1:1')
    F.bloco(262, 150, 146, f'''
<h3>Notas</h3>
<ol class="notas">
<li>C-01 por baixo do anel inferior: M6 + arruela larga F-12 em porca-rebite F-04.</li>
<li>Furos C: suporte, chapa e anel no mesmo aperto M8.</li>
<li>C-02 rebitada (6 × F-09) e aparafusada nas pontas.</li>
<li>Fixação da bateria {tag("A VALIDAR")}.</li>
</ol>''')
    return F


# ======================================================================== F09
def f09():
    F = Folha(9, escala='1:5', material='Al 6061-T6 · tubo 20×20×1,5 · chapas 3 e 5')
    G = gaiola() + suporte_lidar()
    ctx = [p.como('ctx') for p in quadro() if p.estilo == 'solid']
    oy = 70 + Z_G2 * 0.2
    vl = Vista('lateral', 5, 283, oy)
    vf = Vista('frontal', 5, 92, oy)
    vs = Vista('superior', 5, 283, 172)
    desenha(F.s, vl, G)
    desenha(F.s, vf, ctx + G)
    desenha(F.s, vs, G)
    # lateral
    top = vl.P((0, 0, Z_G2))[1]
    y1 = top - 8
    a, b = vl.P((X_MOD, 0, Z_G2)), vl.P((XQ, 0, Z_G2))
    cota_h(F.s, a[0], b[0], y1, a[1], b[1], valor=XQ - X_MOD, desloc_txt=-26)
    a, b = vl.P((-XQ, 0, Z_G2)), vl.P((-X_MOD, 0, Z_G2))
    cota_h(F.s, a[0], b[0], y1, a[1], b[1], valor=XQ - X_MOD)
    a, b = vl.P((-X_MOD, 0, Z_G2)), vl.P((X_MOD, 0, Z_G2))
    cota_h(F.s, a[0], b[0], y1, None, None, valor=2 * X_MOD, lado_txt=-1)
    linha_centro(F.s, *vl.P((0, 0, 332)), *vl.P((0, 0, Z_G2 + 90)))
    for i, xc in enumerate((X_MOD + TG / 2, 280.0, XQ - TG / 2)):
        linha_centro(F.s, *vl.P((xc, 0, 334)), *vl.P((xc, 0, Z_G2 + 10)))
        a, b = vl.P((0, 0, Z_G2 + 10)), vl.P((xc, 0, Z_G2 + 10))
        cota_h(F.s, a[0], b[0], y1 - (i + 1) * D, None, b[1], valor=xc)
    F.s.tx(vl.P((0, 0, 0))[0] - 3, y1 - D - 1, 'montantes', T, a='end', c='tx sec')
    rotulo(F.s, 283, 94, 'VISTA LATERAL DIREITA', '1:5', 'sapatas assentam no deck, Z 340')
    balao(F.s, 206, 96, 'G-04', alvo=vl.P((-280, -YQ, 360)))
    # frontal
    cota_vista_h(F.s, vf, (0, -YQ, Z_G2), (0, YQ, Z_G2), y1)
    cota_vista_h(F.s, vf, (0, -YQ + TG, Z_G2), (0, YQ - TG, Z_G2), y1 - D)
    xd = vf.P((0, YQ, 0))[0]
    a, b = vf.P((0, YQ, Z_G1)), vf.P((0, YQ, Z_G2))
    cota_v(F.s, a[1], b[1], xd + 8, a[0], b[0], valor=TG, lado_txt=-1)
    a, b = vf.P((0, YQ, Z_DECK)), vf.P((0, YQ, Z_G2))
    cota_v(F.s, a[1], b[1], xd + 16, a[0], b[0], valor=Z_G2 - Z_DECK)
    rotulo(F.s, 92, 116, 'VISTA FRONTAL', '1:5', 'quadro em traço fino')
    # superior
    for xc in (40, 280, 513, -40, -280, -513):
        linha_centro(F.s, *vs.P((xc, YQ + 6, 0)), *vs.P((xc, -YQ - 6, 0)))
    linha_centro(F.s, *vs.P((0, YQ + 6, 0)), *vs.P((0, -YQ - 6, 0)))
    linha_centro(F.s, *vs.P((-XQ - 8, 0, 0)), *vs.P((XQ + 8, 0, 0)))
    x_esq = vs.P((-XQ, 0, 0))[0]
    cota_vista_v(F.s, vs, (-XQ, -YQ + TG, 0), (-XQ, YQ - TG, 0), x_esq - 8)
    cota_vista_v(F.s, vs, (-XQ, -YQ, 0), (-XQ, YQ, 0), x_esq - 16)
    zc = vs.P((0, 150, 0))
    F.s.tx(zc[0] + 1.3, zc[1], 'zona livre do mastro', T, c='tx sec', rot=-90)
    rotulo(F.s, x_esq, vs.P((0, -YQ, 0))[1] + 11, 'VISTA SUPERIOR', '1:5', a='start')
    for cod, p, (x, y) in (('G-01', (160, YG_C, Z_G2), (402, 122)), ('G-02', (513, 150, Z_G2), (402, 146)),
                           ('G-03', (330, -150, Z_G2), (402, 170)), ('G-06', (330, 40, Z_TAMPA + 5), (402, 194)),
                           ('G-05', (480, -275, 342), (402, 218))):
        balao(F.s, x, y, cod, alvo=vs.P(p))
    posic = tabela(['Elemento', 'X (mm)'], [
        ['Módulos', f'±{num(X_MOD)} → ±{num(XQ)}'],
        ['Montantes G-04', '±40 · ±280 · ±513'],
        ['Barras G-03', '±230 · ±330'],
        ['Suporte LiDAR', '+280'],
    ], 'compacta', col=[48, 52])
    F.bloco(30, 132, 124, f'''
<h3>Notas da gaiola</h3>
<ol class="notas">
<li>Dois módulos <b>idênticos</b> {tag("NOVO")}: o traseiro é o dianteiro girado 180°.</li>
<li>Vão X −30 → +30 livre para os mastros; coberto pela faixa K-06.</li>
<li>Sapata G-05 (e = 3, 2 × Ø13): M6 + F-12 em porca-rebite no deck.</li>
</ol>
<h3>Posições</h3>{posic}''')
    return F


# ======================================================================== F10
def f10():
    F = Folha(10, escala='1:5 · 1:1', material='ver lista de materiais')
    tudo = gaiola() + suporte_lidar() + carenagens()
    ctx = [p.como('ctx') for p in quadro() if p.estilo == 'solid']
    zt = Z_BASE_LIDAR + 65
    vd = Vista('frontal', 5, 100, 40 + zt * 0.2)
    desenha_corte(F.s, vd, ctx + tudo + lidar_ref(), 'x', 280.0)
    cota_vista_h(F.s, vd, (0, -W_EXT / 2, Z_QUADRO), (0, W_EXT / 2, Z_QUADRO), vd.P((0, 0, Z_QUADRO))[1] + 9)
    xr = vd.P((0, W_EXT / 2, 0))[0]
    for i, z1 in enumerate((Z_G2, Z_BASE_LIDAR)):
        a, b = vd.P((0, W_EXT / 2, Z_DECK)), vd.P((0, 60, z1))
        cota_v(F.s, a[1], b[1], xr + 8 + i * D, a[0], b[0], txt=num(z1 - Z_DECK, 1))
    chamada(F.s, *vd.P((0, W_EXT / 2 - 1, 300)), xr + 20, 104, 'K-01', lado=1)
    chamada(F.s, *vd.P((0, 200, Z_G2 + 0.6)), 176, 44, 'K-04', lado=1)
    chamada(F.s, *vd.P((0, 25, Z_TAMPA + 10)), 124, 30, 'G-08', lado=1)
    chamada(F.s, *vd.P((0, -45, Z_TAMPA + 2.5)), 80, 30, 'G-06', lado=-1)
    chamada(F.s, *vd.P((0, -288, 360)), 30, 44, 'G-04', lado=1)
    rotulo(F.s, 100, 114, 'CORTE D-D', '1:5', 'plano X 280, visto de +X')
    # detalhe F — sapata
    xh = XQ - 35
    wx0, wy0, wx1, wy1 = 34, 136, 80, 170
    F.recorte('cpF', wx0, wy0, wx1, wy1)
    vF = Vista('frontal', 1, wx0 - (Y_C - 23), wy0 + 352)
    sv = Svg()
    desenha_corte(sv, vF, quadro() + gaiola(), 'x', xh)
    F.s.raw(f'<g clip-path="url(#cpF)">{sv}</g>')

    def pF(y, z):
        return vF.P((xh, y, z))
    yc = Y_C
    for (ya, yb, za, zb) in ((yc - 4.5, yc + 4.5, 327, 340), (yc - 6, yc + 6, 340, 340.6), (yc - 3, yc + 3, 328.6, 344.6),
                             (yc - 9, yc + 9, 343, 344.6), (yc - 5.25, yc + 5.25, 344.6, 347.9)):
        a, b = pF(ya, za), pF(yb, zb)
        F.s.rect(a[0], a[1], b[0], b[1], 'vis')
    linha_centro(F.s, *pF(yc, 322), *pF(yc, 351))
    F.s.rect(wx0, wy0, wx1, wy1, 'janela')
    chamada(F.s, *pF(yc + 5.25, 346.5), 86, 140, 'F-05 + F-12', lado=1)
    chamada(F.s, *pF(yc + 14, 341.5), 86, 152, 'G-05 (Ø13)', lado=1)
    chamada(F.s, *pF(yc - 2, 332), 86, 164, 'F-04', lado=1)
    rotulo(F.s, 57, 182, 'DETALHE F', '1:1', f'sapata, X {num(xh)}')
    # detalhe G — carenagem no trilho
    wx0, wy0, wx1, wy1 = 144, 136, 184, 172
    F.recorte('cpG', wx0, wy0, wx1, wy1)
    zg = (Z_G1 + Z_G2) / 2
    vG = Vista('frontal', 1, wx0 - (YQ - 26), wy0 + zg + 18)
    sv = Svg()
    desenha_corte(sv, vG, gaiola() + carenagens(), 'x', 150.0)
    F.s.raw(f'<g clip-path="url(#cpG)">{sv}</g>')

    def pG(y, z):
        return vG.P((150, y, z))
    yo = YQ
    for (ya, yb, za, zb) in ((yo - 13, yo, zg - 3.5, zg + 3.5), (yo, yo + 0.5, zg - 5, zg + 5),
                             (yo + 3.2 - 12, yo + 3.2, zg - 2.5, zg + 2.5),
                             (yo + 2, yo + 3.2, zg - 7.5, zg + 7.5), (yo + 3.2, yo + 5.95, zg - 4.75, zg + 4.75)):
        a, b = pG(ya, za), pG(yb, zb)
        F.s.rect(a[0], a[1], b[0], b[1], 'vis')
    linha_centro(F.s, *pG(yo - 16, zg), *pG(yo + 9, zg))
    F.s.rect(wx0, wy0, wx1, wy1, 'janela')
    chamada(F.s, *pG(yo + 5.9, zg + 3), 190, 140, 'F-07 + F-13', lado=1)
    chamada(F.s, *pG(yo + 1, zg - 9), 190, 152, 'K-01 (Ø11)', lado=1)
    chamada(F.s, *pG(yo - 10, zg - 3.5), 190, 164, 'F-06', lado=1)
    rotulo(F.s, 164, 182, 'DETALHE G', '1:1', 'carenagem, X 150')
    # campo de visão do LiDAR (esquemático)
    x0, y0, k = 324, 100, 0.2

    def PL(y, z):
        return (x0 + y * k, y0 - (z - 380) * k * 2.2)
    F.s.ln(*PL(-W_EXT / 2, Z_TAMPA), *PL(W_EXT / 2, Z_TAMPA), 'vism')
    for s in (1, -1):
        F.s.rect(*PL(s * (YQ - TG), Z_G1), *PL(s * YQ, Z_G2), 'vis')
    lz = Z_TAMPA + (W_EXT / 2) * math.tan(math.radians(7))
    F.s.rect(*PL(-32.5, Z_BASE_LIDAR), *PL(32.5, Z_BASE_LIDAR + 65), 'ref')
    for s in (1, -1):
        F.s.ln(*PL(0, lz), *PL(s * 370, lz - 370 * math.tan(math.radians(7))), 'raio')
    F.s.circ(*PL(0, lz), 0.7, 'arr')
    chamada(F.s, *PL(W_EXT / 2, Z_TAMPA), 404, 116, ['borda da tampa', f'Z {num(Z_TAMPA, 1)}'], lado=-1)
    chamada(F.s, *PL(0, lz), 350, 44, ['centro óptico', f'Z ≥ {num(lz, 1)}'], lado=1)
    F.s.tx(PL(250, 425)[0], PL(250, 425)[1] - 3, '−7°', T, peso=600)
    rotulo(F.s, 324, 136, 'CAMPO DE VISÃO DO LiDAR', 'sem escala', 'altura exagerada 2,2×')
    F.bloco(240, 158, 168, f'''
<h3>LiDAR e campo de visão</h3>
<p>Na baseline o LiDAR fica em Z 370, dentro da gaiola: o feixe de −7° bateria na proteção. Aqui ele vai sobre
o suporte G-06 e 4 coxins, com base em <b>Z {num(Z_BASE_LIDAR, 1)}</b> {tag("NOVO")}. O centro óptico precisa ficar
≥ {num(lz - Z_BASE_LIDAR, 1)} mm acima da base {tag("A VALIDAR")}.</p>''')
    F.bloco(30, 196, 198, f'''
<h3>Câmera frontal e mastros</h3>
<p><b>Câmera de navegação</b> (baseline X 500, Z 380): o trilho da gaiola ocupa Z {num(Z_G1)} → {num(Z_G2)}.
Proposta: vê pela janela 140 × 32 da K-02, centro Z 360 {tag("A VALIDAR")}.</p>
<p><b>Mastros</b> (baseline Y ±300): com a bainha Ø29, eixo em |Y| ≤ 285,5. Fixação no quadro: fora desta
revisão.</p>''')
    return F


# ======================================================================== F11
def _plano(F, p, x0, y0, k, ia=0, ib=1, cotas=True, dx_cota=8.0):
    """Peça plana na vista normal à espessura; canto superior esquerdo do contorno em (x0, y0)."""
    A = [q[ia] for q in p.perfil]
    B = [q[ib] for q in p.perfil]
    amin, amax, bmin, bmax = min(A), max(A), min(B), max(B)

    def P(a, b):
        return (x0 + (a - amin) * k, y0 + (bmax - b) * k)
    F.s.aneis([[P(q[ia], q[ib]) for q in r] for r in [p.perfil] + p.furos], 'vis')
    for (ca, cb, d) in p.circulos:
        c = P((ca, cb)[ia], (ca, cb)[ib])
        if d * k >= 3:
            cruz_centro(F.s, c[0], c[1], d * k / 2)
    x1, y1 = x0 + (amax - amin) * k, y0 + (bmax - bmin) * k
    if cotas:
        cota_h(F.s, x0, x1, y1 + dx_cota, y1, y1, valor=amax - amin)
        cota_v(F.s, y0, y1, x0 - dx_cota, x0, x0, valor=bmax - bmin)
    return P, (x0, y0, x1, y1), (amin, amax, bmin, bmax)


def f11():
    F = Folha(11, escala='1:5 · 1:10 · 1:2', material='Al 5052-H32 · Al 6061-T6 (G-05, G-06)')
    K = carenagens()
    G = gaiola() + suporte_lidar()
    s = F.s
    # K-01 (meia dianteira esquerda), plano (x, z)
    k01 = [p for p in K if p.item == 'K-01' and p.bbox()[0][0] >= 0 and p.bbox()[1][0] > 0][0]
    P, (x0, y0, x1, y1), (amin, _, bmin, _) = _plano(F, k01, 44, 70, 0.2)
    for i, x in enumerate(M.X_FUROS_LAT):
        b = P(x, Z_G2)
        cota_h(s, x0, b[0], y0 - 8 - (4 - i) * D, y0, y0, valor=x - amin)
    for i, z in enumerate(M.Z_LINHAS_LAT):
        a, b = P(XQ, Z_QUADRO), P(XQ, z)
        cota_v(s, a[1], b[1], x1 + 8 + i * D, a[0], b[0], valor=z - Z_QUADRO)
    rotulo(s, (x0 + x1) / 2, y1 + 22, 'K-01 CARENAGEM LATERAL', '1:5', '4× · 15 × Ø11 · e = 2')
    # K-02 frontal, plano (y, z)
    k02 = [p for p in K if p.item == 'K-02'][0]
    P2, (u0, v0, u1, v1), _ = _plano(F, k02, 200, 70, 0.2)
    a, b = P2(-70, 376), P2(70, 376)
    cota_h(s, a[0], b[0], v0 - 8, v0, v0, valor=140)
    ya, yb = P2(70, 344), P2(70, 376)
    cota_v(s, P2(0, Z_QUADRO)[1], ya[1], u1 + 8, u1, u1, valor=344 - Z_QUADRO)
    cota_v(s, ya[1], yb[1], u1 + 8, None, u1, valor=32, lado_txt=-1)
    chamada(s, *P2(-70, 352), 188, 52, ['janela da', 'câmera · R5'], lado=-1)
    rotulo(s, (u0 + u1) / 2, v1 + 22, 'K-02 CARENAGEM FRONTAL', '1:5', 'K-03: igual, sem janela · 9 × Ø11')
    # G-06 1:2 (canto superior direito)
    g06 = [p for p in G if p.item == 'G-06'][0]
    _plano(F, g06, 344, 30, 0.5)
    rotulo(s, 376.5, 108, 'G-06', '1:2', 'e = 5')
    # linha 2 — tampas 1:10
    k04 = [p for p in K if p.item == 'K-04'][0]
    k05 = [p for p in K if p.item == 'K-05'][0]
    k06 = [p for p in K if p.item == 'K-06'][0]
    _plano(F, k04, 44, 138, 0.1)
    rotulo(s, 44 + 24.75, 222, 'K-04', '1:10', f'{len(k04.circulos) - 1}× Ø11 + Ø30')
    _plano(F, k05, 114, 138, 0.1)
    rotulo(s, 114 + 24.75, 222, 'K-05', '1:10', f'{len(k05.circulos)}× Ø11')
    _plano(F, k06, 184, 142, 0.1)
    rotulo(s, 189.5, 222, 'K-06', '1:10', '6× Ø5,5')
    # G-05 sapatas 1:2
    sap = OrderedDict()
    for p in gaiola():
        if p.item == 'G-05' and p.bbox()[0][0] > 0 and p.bbox()[1][0] > 0:
            sap[round(p.bbox()[0][0])] = p
    nomes = {30: 'interna', 245: 'meio', 453: 'canto'}
    for i, (xk, p) in enumerate(sorted(sap.items())):
        yy = 134 + i * 34
        _plano(F, p, 222, yy, 0.5, dx_cota=6)
        xs_f = sorted(c[0] for c in p.circulos)
        am = p.bbox()[0][0]
        s.tx(262, yy + 5, f'G-05 {nomes[xk]}', T, a='start', peso=700)
        s.tx(262, yy + 10.5, f'Ø13 em {num(xs_f[0] - am)} e {num(xs_f[1] - am)}', T, a='start', c='tx sec')
    F.bloco(300, 130, 108, f'''
<h3>Notas de corte</h3>
<ol class="notas">
<li>Cada peça sai do DXF de mesmo nome (<b>dxf/</b>, 1:1, mm).</li>
<li>Ø11 e Ø13: folga para a cabeça da porca-rebite.</li>
<li>Cantos externos R3; sem rebarba.</li>
<li>K-01: 4 iguais (a direita é a mesma virada).</li>
</ol>''')
    return F


# ======================================================================== F12
def f12():
    F = Folha(12, escala='sem escala', material='Al 6061-T6 · tubo 20×20×1,5')
    G = gaiola() + suporte_lidar()
    ex = [p.movido(dx=90 if p.bbox()[0][0] > 0 else -90) for p in G]
    cam = iso_no_retangulo(ex, 36, 30, 226, 146, 5.9)
    desenha_iso(F.s, cam, ex)
    alvos = [('G-01', (250 + 90, -YG_C, Z_G2), (-4, 24)), ('G-02', (513 + 90, 0, Z_G2), (22, 12)),
             ('G-03', (230 + 90, 150, Z_G2), (6, -20)), ('G-04', (-280 - 90, -YG_C, 360), (-8, 24)),
             ('G-05', (-40 - 90, -Y_C, 341.5), (-22, 14)), ('G-06', (330 + 90, 40, Z_TAMPA + 5), (16, -14)),
             ('G-07', (-31 - 90, YG_C, 387), (-12, -20)), ('G-08', (305 + 90, -25, Z_TAMPA + 10), (22, -2))]
    for cod, p, (dx, dy) in alvos:
        a = cam.P(p)
        balao(F.s, a[0] + dx, a[1] + dy, cod, alvo=a)
    rotulo(F.s, 131, 158, 'MÓDULOS DA GAIOLA', 'sem escala', 'afastados para leitura')
    lc = lista_corte()
    linhas, pecas_tubo = [], []
    for item in ('G-01', 'G-02', 'G-03', 'G-04', 'G-05', 'G-06', 'G-07', 'G-08'):
        d = lc[item]
        it = ITENS[item]
        if item in ('G-01', 'G-02', 'G-03', 'G-04'):
            comp = ', '.join(num(c, 1) for c in d['comps'])
            for c, n in d['comps'].items():
                pecas_tubo += [(item, c)] * n
        else:
            comp = it['desc'].replace('Chapa ', '').replace('Borracha ', '')
        linhas.append([f'<b>{item}</b>', it['nome'], comp, str(d['qtd']), kg(d['massa'], 2)])
    mg = sum(lc[i]['massa'] for i in ('G-01', 'G-02', 'G-03', 'G-04', 'G-05', 'G-06', 'G-07', 'G-08'))
    linhas.append(['', '<b>Total da gaiola</b>', '', '', f'<b>{kg(mg, 2)}</b>'])
    total = sum(c for _, c in pecas_tubo)
    F.bloco(240, 24, 168, '<h3>Lista de corte — gaiola</h3>' + tabela(
        ['Item', 'Peça', 'Corte / formato', 'Qtd', 'kg'], linhas, 'corte', col=[12, 38, 25, 10, 15]) +
        f'<p class="mini">Tubo 20×20×1,5: {milhar(total / 1000, 2)} m de peças.</p>')
    F.bloco(240, 128, 168, '<h3>Plano de corte — tubo 20×20×1,5</h3>', h=10)
    nb = plano_barras(F.s, 262, 150, 128, pecas_tubo)
    F.s.tx(240.5, 150 + nb * 19 + 6, f'{nb} barras de 6 m, serra de 3 mm.', T, a='start', c='tx sec')
    F.bloco(30, 170, 198, '''
<h3>Montagem de cada módulo</h3>
<ol class="notas">
<li>Anel (2 × G-01, 2 × G-02, 2 × G-03) no gabarito; pontas de G-01 com G-07.</li>
<li>Sapatas G-05 soldadas nos 6 montantes G-04 (34 mm).</li>
<li>Montantes no anel, módulo invertido sobre mesa plana: sapatas coplanares ≤ 0,5.</li>
<li>Furar as sapatas depois da solda, com gabarito tirado do quadro.</li>
<li>O mesmo gabarito serve aos dois módulos (são idênticos).</li>
</ol>''')
    F.bloco(240, 196, 168, f'''
<h3>Módulos idênticos</h3>
<p>Uma peça só, fabricada 2 vezes: o traseiro é o dianteiro girado 180°. O vão central fica livre para os
mastros {tag("NOVO")}.</p>''')
    return F


# ======================================================================== F13
def f13():
    F = Folha(13, escala='sem escala', material='—')
    ex = explodido(dz_n=-80)
    cam = iso_no_retangulo(ex, 34, 26, 268, 222, 7.9)
    desenha_iso(F.s, cam, ex)
    zt = Z_TAMPA + 330
    alvos = [('Q', (-420, -YQ, 300), (-22, -4)), ('C-01', (440, 150, 138), (20, 14)),
             ('C-02', (M.X_NERV, -200, 50), (-8, 22)), ('S', (-XS, -290, 40), (-20, 10)),
             ('G', (-XS, -YQ, 570), (-20, -6)), ('K-01', (-300, -530, 330), (-18, 12)),
             ('K-02', (XQ + 232, 150, 330), (18, -6)), ('K-03', (-XQ - 232, 0, 330), (-12, -18)),
             ('K-04', (400, -200, zt), (18, -10)), ('K-05', (-400, 200, zt), (-6, -18)),
             ('K-06', (0, 0, zt + 1.2), (6, -20)), ('G-06', (330, -40, Z_TAMPA + 5 + 330), (20, -8)),
             ('R', (XS, -351, -130), (20, 10))]
    for cod, p, (dx, dy) in alvos:
        a = cam.P(p)
        balao(F.s, a[0] + dx, a[1] + dy, cod, alvo=a)
    rotulo(F.s, 150, 240, 'VISTA EXPLODIDA', 'sem escala', 'MPW86 (R) como referência')
    fx = fixadores()
    linhas = [[f'<b>{c}</b>', d, str(q)] for (c, d, m, q, o) in fx]
    F.bloco(276, 24, 132, '<h3>Sequência de montagem</h3><ol class="notas">'
            '<li>Quadro acabado, com porcas-rebite.</li>'
            '<li>Chapa C-01 + nervuras, por baixo (M6).</li>'
            '<li>Suportes S (M8); medir entre-eixos, bitola, diagonais; apertar (20 N·m).</li>'
            '<li>MPW86 com F-10 (2,5 N·m, trava).</li>'
            '<li>Módulos G no deck (M6).</li>'
            '<li>Carenagens K-01 a K-03 (M5, 3 N·m).</li>'
            '<li>Tampas K-04, K-05, K-06; G-06 com coxins.</li>'
            '<li>Parte B (folhas 17 a 22): batentes, bandejas, hastes dos mastros, E-STOP e interfaces de sensores.</li>'
            '</ol>'
            '<h3>Fixadores (inox A4)</h3>' + tabela(['Item', 'Descrição', 'Qtd'], linhas, 'compacta fix',
                                                   col=[15, 70, 15]) +
            '<p class="mini">F-01 a F-13: Parte A. F-20 a F-29: Parte B (folhas 17 a 22).</p>', h=240)
    return F


# ======================================================================== F14
def f14():
    F = Folha(14, material='—')
    lc = lista_corte()
    linhas = []
    for g in ('Q', 'C', 'S', 'G', 'K', 'M'):
        sub = 0.0
        linhas.append(f'<tr class="grupo"><td colspan="5">{g} — {GRUPOS[g]}</td></tr>')
        for item, d in lc.items():
            if not item.startswith(g):
                continue
            it = ITENS[item]
            linhas.append([f'<b>{item}</b>', it['nome'], it['desc'], str(d['qtd']), kg(d['massa'], 2)])
            sub += d['massa']
        linhas.append(['', '', 'subtotal', '', f'<b>{kg(sub, 2)}</b>'])
    F.bloco(30, 24, 198, '<h3>Lista de materiais — peças fabricadas</h3>' +
            tabela(['Item', 'Peça', 'Formato', 'Qtd', 'kg'], linhas, 'corte bom', col=[12, 37, 33, 8, 10]))
    c = comparacao_baseline()
    comp = []
    for (nome, mb, zb, mn, zn, itens) in c['linhas']:
        comp.append([nome, kg(mb, 1), kg(mn, 2), f'{"+" if mn >= mb else ""}{kg(mn - mb, 2)}'])
    comp.append(['<b>Total</b>', kg(sum(l[1] for l in c['linhas']), 1), kg(sum(l[3] for l in c['linhas']), 2),
                 f'<b>+{kg(c["dm"], 2)}</b>'])
    res = [
        ['Massa mínima', '85,04', f'<b>{kg(c["m_min_novo"], 2)}</b>'],
        ['Margem de 15 % restante (kg)', '12,76', f'<b>{kg(c["margem_rest"], 2)}</b>'],
        ['CG — Z nominal (mm)', '297', kg(c['zcg_novo'], 1)],
        ['Tombamento estático', f'{kg(c["tomb_base"], 1)}°', f'{kg(c["tomb_novo"], 1)}°'],
    ]
    F.bloco(236, 24, 172, '<h3>Comparação com a baseline (kg)</h3>' +
            tabela(['Item da tabela 5.1', 'Base', 'Calc.', 'Δ'], comp, 'compacta', col=[46, 16, 18, 20]) +
            tabela(['Grandeza', 'Baseline', 'Agora'], res, 'compacta', col=[52, 22, 26]) +
            f'<p class="mini">Estrutura +{kg(c["dm"], 1)} kg: a margem de 15 % fica quase toda consumida. O CG desce '
            'e o tombamento melhora. A linha de suportes inclui a base dos mastros (M-01, M-02).</p>'
            '<p class="mini">Esta coluna parte da massa <b>declarada</b> na baseline (85,04 kg). A folha 24 '
            'parte da <b>soma</b> da tabela 5.1 (82,49 kg) e inclui a Parte B, chegando a 96,51 kg: a diferença '
            'de 2,55 kg é a inconsistência da própria baseline, não um erro de conta. Adotar um único número é '
            'o item 9 da folha 23.</p>')
    mats = [
        ['Tubo 30×30×2', '2 barras de 6 m'], ['Tubo 20×20×1,5', '2 barras de 6 m'],
        ['Cantoneira 40×40×4', '1,2 m'], ['Barra redonda Ø12', '0,5 m'],
        ['Chapas 6061-T6: 3, 5, 6, 8, 10', 'retalhos'],
        ['Chapa 5052-H32 2 mm', '≈ 1,05 × 1,3 m'], ['Chapa 5052-H32 1,2 mm', '≈ 1,0 × 0,6 m'],
    ]
    F.bloco(236, 150, 172, '<h3>Matéria-prima</h3>' +
            tabela(['Material', 'Compra'], mats, 'compacta', col=[62, 38]))
    return F


# ======================================================================== F15
def f15():
    F = Folha(15, material='—')
    v = verificacoes()
    c = v['c']
    ver = [
        ['1', 'Longarinas, vão 700', f'σ = {kg(v["s1"], 0)} MPa · δ = {kg(v["d1"], 2)} mm', 'OK'],
        ['2', 'Suporte, fim da nervura', f'σ = {kg(v["s2"], 0)} MPa', 'OK'],
        ['3', 'Parafusos M8 do suporte', f'T = {milhar(v["T3"], 0)} N (prova 16 kN)', 'OK'],
        ['4', 'Chapa entre nervuras', f'σ = {kg(v["s4"], 0)} MPa · δ = {kg(v["d4"], 1)} mm', 'Atenção'],
        ['5', 'Nervura C-02', f'σ = {kg(v["s5"], 0)} MPa', 'OK'],
        ['6', 'Torque a 13°', f'{kg(v["t6"], 1)} N·m < 20', 'OK'],
        ['7', 'Tombamento estático', f'{kg(c["tomb_base"], 1)}° → {kg(c["tomb_novo"], 1)}°', 'Melhora'],
        ['8', 'Base do mastro (50 N)', '72,1 N·m', 'Pendente'],
    ]
    F.bloco(30, 24, 196, '<h3>A · Verificações preliminares</h3>' +
            tabela(['#', 'O quê', 'Resultado', 'Situação'], ver, 'compacta', col=[6, 40, 38, 16]) +
            f'<p class="mini">{tag("HIPÓTESE")} m = {kg(v["m_max"], 1)} kg, fator dinâmico 3, lateral 0,5 N. '
            '6061-T6: 276 MPa; ZTA ≈ 110 MPa. Fadiga não verificada: pedir FEA.</p>')
    pend = [
        ['<b>Bloqueia</b>', 'Aprovar a estrutura deste caderno.'],
        ['<b>Bloqueia</b>', 'ElectroCraft: face de montagem, furos, motor com freio.'],
        ['<b>Bloqueia</b>', 'Suspensão: rígido agora ou reabrir o suporte.'],
        ['<b>Bloqueia</b>', f'Massa: +{kg(c["dm"], 1)} kg; margem restante {kg(c["margem_rest"], 1)} kg.'],
        ['<b>Bloqueia</b>', 'Solda no 6061-T6: como soldado ou novo T6.'],
        ['Integração', 'Base do mastro · E-STOP · bateria · eletrônica.'],
        ['Integração', 'O que o vão livre de 150 mede (entre rodas: Z 208).'],
    ]
    F.bloco(30, 104, 196, '<h3>C · Pendências</h3>' + tabela(['Tipo', 'Pendência'], pend, 'compacta', col=[20, 80]))
    inc = [
        ['Imagem da gaiola', 'Altura "1.050" é o comprimento; a gaiola vai de Z 340 a 400.'],
        ['Infográfico "REV E"', 'Massas da Rev D (83,96 / 96,6 / ~125).'],
        ['Imagens do chassi', 'Diagonais não cabem em 30 mm entre anéis.'],
        ['CAD Rev B', 'Quadro 1000 × 570, gaiola 610 de largura.'],
        ['Baseline, tab. 5.1', f'Soma {kg(sum(TABELA_51), 2)} kg, não 85,04.'],
        ['Baseline, quadro', f'2,1 kg = 3,5 m de tubo; o real: {kg(c["linhas"][0][3], 2)} kg.'],
        ['Baseline, chapa', '1,3 kg ≈ 0,8 mm: não apoia a bateria.'],
        ['Baseline, LiDAR', 'Z 370 fica abaixo da gaiola (folha 10).'],
        ['Desenho da gaiola', 'Tubo 30×30×2 e 6,8 kg; o projeto usa 20×20×1,5 e 2,42 kg.'],
        ['Baseline, GNSS', 'Antena em Z 390 fica sob a tampa de alumínio (folha 22).'],
        ['Baseline, câm. raiz', 'Z 150 põe a câmera abaixo do chassi (folha 22).'],
    ]
    F.bloco(236, 24, 172, '<h3>B · Inconsistências</h3>' +
            tabela(['Onde', 'O que foi encontrado'], inc, 'compacta', col=[32, 68]))
    chk = ['Geometria × baseline', 'Quadro: topologia e perfis', 'Suporte e interface MPW86',
           'Chapa de fundo e nervuras', 'Gaiola, carenagens, tampas', 'Tolerâncias (folha 02)',
           'Solda, ZTA, acabamento', 'Massa e CG (folha 14)']
    F.bloco(236, 100, 172, '<h3>D · Parecer</h3><ul class="check">' +
            ''.join(f'<li><span class="box"></span>{x}</li>' for x in chk) + '</ul>'
            '<div class="parecer"><span><span class="box"></span>Aprovado</span>'
            '<span><span class="box"></span>Com ressalvas</span>'
            '<span><span class="box"></span>Reprovado</span></div>'
            '<div class="assin"><div>Nome</div><div>CREA</div><div>Data</div><div>Assinatura</div></div>', h=86)
    return F


# ======================================================================== F16
def f16():
    F = Folha(16, material='—')
    itens = [
        ('Q', 'Quadro estrutural soldado, com buchas', '1'),
        ('C', 'Chapa de fundo + 2 nervuras', '1'),
        ('S', 'Suporte do motor-roda, soldado e usinado', '4'),
        ('G', 'Gaiola: 2 módulos idênticos + suporte LiDAR', '1'),
        ('M', 'Base dos mastros: 2 luvas + 2 reforços, soldados ao quadro', '1 jg'),
        ('K', '6 carenagens + 3 tampas', '1 jg'),
        ('F', 'Fixadores + porcas-rebite instaladas', '1 jg'),
        ('B', 'Parte B (folhas 17–22): mastros, suportes, bandejas, E-STOP e interfaces de sensores', '1 jg'),
        ('—', 'Acabamento A — natural', '1'),
        ('—', 'Acabamento B — anodização preta', '1'),
        ('—', 'Acabamento C — pintura eletrostática', '1'),
        ('—', 'Relatório dimensional e certificados', '1'),
        ('—', 'Embalagem e frete', '1'),
    ]
    linhas = [[str(i + 1), g, b, c, '', '', ''] for i, (g, b, c) in enumerate(itens)]
    linhas.append(['', '', '<b>Total de 1 conjunto</b>', '', '', '', ''])
    linhas.append(['', '', '<b>Preço unitário para 3 conjuntos</b>', '3', '', '', ''])
    F.bloco(30, 24, 246, '<h3>Proposta — preencher pelo fornecedor</h3>' +
            tabela(['#', 'Gr.', 'Escopo', 'Qtd', 'Unit. (R$)', 'Total (R$)', 'Prazo (d)'], linhas, 'rfq',
                   col=[5, 7, 44, 8, 13, 12, 11]))
    F.bloco(284, 24, 124, '''
<h3>De / para</h3>
<div class="campos">
<div><span>Solicitante</span>ValTexa — Rover V3</div>
<div><span>Contato ValTexa</span>&nbsp;</div>
<div><span>Fornecedor</span>&nbsp;</div>
<div><span>Contato do fornecedor</span>&nbsp;</div>
<div><span>Responder até</span>&nbsp;</div>
</div>
<h3>Documentos</h3>
<p><b>Parte A</b> — folhas 01 a 16 e a pasta <b>dxf/</b>: é o objeto da cotação.<br>
<b>Parte B</b> — folhas 17 a 22: linha <b>B</b> da tabela, cotar em separado.<br>
<b>Parte C</b> — folhas 23 a 27: informativo, não entra no preço.</p>''')
    F.bloco(30, 176, 196, '''
<h3>Informe na proposta</h3>
<ol class="notas">
<li>Validade, pagamento, impostos e frete.</li>
<li>Prazo a partir do pedido (liberação: folha 15).</li>
<li>Qualificação do soldador para alumínio.</li>
<li>Desvios e alternativas que reduzam custo.</li>
</ol>''')
    F.bloco(284, 146, 124, '''
<h3>Aceite do fornecedor</h3>
<div class="assin v"><div>Empresa / CNPJ</div><div>Responsável</div><div>Data e assinatura</div></div>''', h=80)
    return F


FOLHAS = [f01, f02, f03, f04, f05, f06, f07, f08, f09, f10, f11, f12, f13, f14, f15, f16]
