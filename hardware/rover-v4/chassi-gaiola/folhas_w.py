"""Folhas 28 a 35: desenhos de usinagem do grupo W e manual de montagem.

Duas coisas diferentes, e é por isso que estão em folhas separadas:

* **28 a 31 — usinagem.** Uma folha por subconjunto, com as vistas em escala, as cotas
  funcionais cotadas no desenho e o ROTEIRO DE OPERAÇÕES ao lado. A tolerância não está
  nos DXF (DXF não carrega tolerância); está aqui e em ``revisao-h/usinagem.py``, de onde
  estas folhas a leem.
* **32 a 35 — montagem.** Onde vai cada peça, em que ordem, com que aperto e o que
  conferir depois. A tabela de posições é extraída do modelo em
  ``revisao-h/montagem.py``: ninguém digita coordenada aqui.

Nenhum número desta folha é digitado duas vezes. Se uma cota mudar no ``modelo.py``, estas
folhas mudam junto — ou não geram.
"""
import math

import modelo as M
from folhas import (D, Folha, _sus, baloes_sem_colisao, desenha_oculto, esc, iso_no_retangulo,
                    recorta_caixa, so, tabela, tag, vista_no_retangulo)
from desenho import (Iso, Vista, balao, chamada, cota_h, cota_v, cruz_centro, desenha,
                     desenha_corte, desenha_iso, fcf, linha_centro, num, dec, referencia,
                     rotulo, rugosidade, seta, simbolo_solda, T)

# ------------------------------------------------------------------ utilidades
_MONT = None
_USIN = None


def _mod(nome):
    """Carrega um módulo de ../revisao-h por caminho, uma vez."""
    import importlib.util
    import pathlib
    cam = pathlib.Path(__file__).resolve().parent.parent / 'revisao-h' / f'{nome}.py'
    esp = importlib.util.spec_from_file_location(f'{nome}_g', cam)
    mod = importlib.util.module_from_spec(esp)
    esp.loader.exec_module(mod)
    return mod


def _mont():
    global _MONT
    if _MONT is None:
        _MONT = _mod('montagem')
    return _MONT


def _usin():
    global _USIN
    if _USIN is None:
        _USIN = _mod('usinagem')
    return _USIN


def _canto():
    """O canto dianteiro esquerdo da suspensão, peça por peça."""
    return M.braco(1, 1) + M.torre_pivo(1, 1) + M.berco_fole(1, 1)


def _tab_ops(itens, cls=''):
    """A tabela de operações, lida do roteiro — corte, usinagem e solda separados."""
    U = _usin()
    linhas = []
    for it in itens:
        ops = U.OPERACOES.get(it)
        if not ops:
            continue
        g = U.geometria(it)
        linhas.append(f'<tr class="grupo"><td colspan="4">{it} — {M.ITENS[it]["nome"]} · '
                      f'{g["qtd"]} un · {g["mat"]}</td></tr>')
        for (n, op, fer, cota, acab) in ops:
            natureza = ('SOLDA' if 'SOLDAR' in op
                        else ('corte' if ('laser' in fer or 'serra' in fer) else 'USINAR'))
            linhas.append([f'<b>{natureza}</b> {n}', op, cota, acab])
    return tabela(['op', 'operação', 'cota / tolerância', 'acabamento'], linhas, cls,
                  col=[13, 42, 31, 14])


def _cotas_furos(F, v, peca, z_ref=None, so_maiores=0.0):
    """Marca o centro de cada furo redondo da peça na vista."""
    for (a, b, d) in peca.circulos:
        if d < so_maiores:
            continue
        p = peca.mundo(a, b, (peca.e0 + peca.e1) / 2)
        cruz_centro(F.s, *v.P(p), max(d * v.k / 2 + 1.5, 2.0))


# ---------------------------------------------------------------- layout comum
# Zona de desenho à esquerda, bloco de texto à direita. As duas não se tocam, e é o
# `vista_no_retangulo` que garante isso: nenhuma vista é posicionada à mão.
DES = (28.0, 20.0, 248.0, 232.0)      # zona de desenho
TXT_X, TXT_Y, TXT_W = 254.0, 20.0, 156.0


# ======================================================================== F28
def f28():
    F = Folha(28, escala='—', material='W-01 Aço 1020 · tubo ret. 40×30×3',
              tolerancia='ISO 2768-mK · soldado ISO 13920-BF')
    canto = _canto()
    braco = so(canto, 'W-01')[0]
    bucha = so(canto, 'W-04')
    oculto = so(canto, 'W-08', 'W-09', 'W-10')
    conj = so(canto, 'W-01', 'W-02', 'W-03', 'W-04', 'W-08', 'W-09', 'W-10')

    # ---- vista lateral do tubo
    vl = vista_no_retangulo([braco] + bucha, 'lateral_e', 30, 34, 246, 86)
    desenha(F.s, vl, [braco] + bucha)
    desenha_oculto(F.s, vl, oculto)
    k = vl.k
    a, b = vl.P((M.X_BRACO[0], 0, 0)), vl.P((M.X_BRACO[1], 0, 0))
    cota_h(F.s, a[0], b[0], 102, None, None, valor=M.X_BRACO[1] - M.X_BRACO[0])
    a, b = vl.P((M.X_BRACO[1], 0, 0)), vl.P((M.X_PIVO, 0, 0))
    cota_h(F.s, a[0], b[0], 94, None, None, valor=M.X_BRACO[1] - M.X_PIVO)
    a, b = vl.P((M.X_BRACO[1], 0, 0)), vl.P((M.X_FOLE, 0, 0))
    cota_h(F.s, a[0], b[0], 26, None, None, valor=M.X_BRACO[1] - M.X_FOLE)
    xd = min(vl.P((M.X_BRACO[0], 0, 0))[0], vl.P((M.X_BRACO[1], 0, 0))[0]) - 8
    a, b = vl.P((0, 0, M.Z_BRACO_T[0])), vl.P((0, 0, M.Z_BRACO_T[1]))
    cota_v(F.s, a[1], b[1], xd, None, None, valor=M.H_BRACO)
    linha_centro(F.s, *vl.P((M.X_PIVO, 0, M.Z_BRACO - 34)), *vl.P((M.X_PIVO, 0, M.Z_BRACO + 34)))
    linha_centro(F.s, *vl.P((M.X_FOLE, 0, M.Z_BRACO - 34)), *vl.P((M.X_FOLE, 0, M.Z_BRACO + 34)))
    linha_centro(F.s, *vl.P((M.X_BRACO[0] - 12, 0, M.Z_BRACO)), *vl.P((M.X_BRACO[1] + 12, 0, M.Z_BRACO)))
    chamada(F.s, *vl.P((M.X_PIVO, 0, M.Z_BRACO + M.D_BUCHA / 2)), 162, 38,
            [f'2× Ø{num(M.D_BUCHA, 0)} H11 nas duas paredes',
             'coaxiais em 0,2 · alojamento de W-04'], lado=1)
    chamada(F.s, *vl.P((M.X_FOLE, 0, M.Z_BRACO_T[1])), 96, 31,
            ['rasgo 24 × 34 na parede superior', 'alojamento do disco W-08'], lado=-1)
    chamada(F.s, *vl.P((M.X_FOLE, 0, M.Z_BRACO)), 190, 113,
            [f'2× Ø{num(M.D_PINO_PRATO, 0)} H7 nas duas paredes',
             'coaxiais em 0,05 · pino W-10'], lado=1)
    referencia(F.s, *vl.P((M.X_BRACO[1], 0, M.Z_BRACO)), 'D', 0.0)
    rotulo(F.s, 138, 120, 'W-01 · VISTA LATERAL', esc(vl), 'face D = ponta externa do tubo')

    # ---- seção transversal do tubo, 2:1
    k2, cx, cy = 2.0, 74.0, 170.0
    F.s.rect(cx - M.B_BRACO / 2 * k2, cy - M.H_BRACO / 2 * k2,
             cx + M.B_BRACO / 2 * k2, cy + M.H_BRACO / 2 * k2, 'vis')
    F.s.rect(cx - (M.B_BRACO / 2 - M.E_BRACO) * k2, cy - (M.H_BRACO / 2 - M.E_BRACO) * k2,
             cx + (M.B_BRACO / 2 - M.E_BRACO) * k2, cy + (M.H_BRACO / 2 - M.E_BRACO) * k2, 'vis')
    cota_h(F.s, cx - M.B_BRACO / 2 * k2, cx + M.B_BRACO / 2 * k2,
           cy + M.H_BRACO / 2 * k2 + 10, None, None, valor=M.B_BRACO)
    cota_v(F.s, cy - M.H_BRACO / 2 * k2, cy + M.H_BRACO / 2 * k2,
           cx - M.B_BRACO / 2 * k2 - 10, None, None, valor=M.H_BRACO)
    chamada(F.s, cx + M.B_BRACO / 2 * k2, cy, 118, 150, [f'parede {num(M.E_BRACO, 0)}'], lado=1)
    rugosidade(F.s, cx - 24, cy - 48, 'Ra 12,5')
    rotulo(F.s, cx, 234, 'SEÇÃO DO TUBO', '2:1')

    # ---- isométrica do subconjunto soldado
    cam = iso_no_retangulo(conj, 136, 142, 248, 212, 2.4, az=-128, el=22)
    desenha_iso(F.s, cam, conj)
    for cod, p, (dx, dy) in (('W-01', (450.0, M.Y_BRACO[0], M.Z_BRACO_T[0]), (4, 6)),
                             ('W-02', (M.XS - 30, M.Y_FACE, 120.0), (-10, 4)),
                             ('W-03', (M.X_BRACO[0] - 3, M.Y_BRACO[1], M.Z_BRACO), (-9, -4)),
                             ('W-04', (M.X_PIVO, M.Y_BRACO[1] + 4, M.Z_BRACO), (8, -5)),
                             ('W-08', (M.X_FOLE, M.Y_FOLE, M.Z_BRACO_T[1]), (0, -8))):
        q = cam.P(p)
        balao(F.s, q[0] + dx, q[1] + dy, cod, alvo=q)
    rotulo(F.s, 192, 220, 'SUBCONJUNTO SOLDADO DO BRAÇO', '1:2,4', '4 un: 2 E + 2 D')

    br = _sus().braco_tensoes()
    F.bloco(TXT_X, TXT_Y, TXT_W, f'''
<h3>W-01 · braço longitudinal</h3>
<p>Quatro braços: dois esquerdos e dois direitos. O desenho é do dianteiro esquerdo. <b>O
tubo é de aço</b> — não é preferência de material: o braço cicla a cada ondulação do
terreno, e alumínio não tem limite de fadiga.</p>
{_tab_ops(['W-01', 'W-03', 'W-04'])}
<h3>A ordem importa</h3>
<p>O alojamento da bucha é <b>pré-furado</b> antes de soldar e <b>alargado depois</b>.
Soldar W-04 atravessando o tubo distorce as duas paredes; alargar antes joga a
coaxialidade fora, e é ela que define se o braço gira livre ou come o curso em atrito.</p>
<ol class="notas">
<li>O rasgo 24 × 34 abre a parede superior numa seção que recebe
{num(br["sigma_rasgo_MPa"], 1)} MPa de projeto, com fator de segurança
{dec(br["fs_rasgo"], 2)} contra o escoamento do 1020. {tag('CALC')}</li>
<li>Sobreposição na chapa W-02: {num(br["sobreposicao_mm"], 0)} mm, filete a4 em cima e
embaixo. Fator de segurança da solda {dec(br["fs_solda"], 1)}. {tag('CALC')}</li>
<li>Esmerilhar o pé do cordão nas duas pontas da sobreposição. É requisito de fadiga, não
de acabamento — o pé do filete é onde a trinca nasce. {tag('A VALIDAR')}, caso 9 do FEA.</li>
<li>Não pintar por dentro: a tampa W-03 fecha a ponta e o tubo trabalha selado.</li>
</ol>''')
    return F


# ======================================================================== F29
def f29():
    F = Folha(29, escala='—', material='W-02 Aço A36 · chapa 10',
              tolerancia='ISO 2768-mK · soldado ISO 13920-BF')
    canto = _canto()
    chapa_m = so(canto, 'W-02')[0]

    # ---- vista da face
    vp = vista_no_retangulo([chapa_m], 'lateral_e', 48, 26, 150, 190)
    desenha(F.s, vp, [chapa_m])
    c = vp.P((M.XS, M.Y_FACE, M.Z_EIXO))
    cruz_centro(F.s, c[0], c[1], 26 * vp.k * 2)
    F.s.circ(c[0], c[1], M.MPW_PCD / 2 * vp.k, 'cl')
    a, b = vp.P((M.XS - M.R_PLACA, 0, 0)), vp.P((M.XS + M.R_PLACA, 0, 0))
    cota_h(F.s, a[0], b[0], 197, None, None, valor=2 * M.R_PLACA)
    xd = min(a[0], b[0]) - 8
    a, b = vp.P((0, 0, M.Z_EIXO - M.R_PLACA)), vp.P((0, 0, M.Z_BRACO_T[1]))
    cota_v(F.s, a[1], b[1], xd, None, None, valor=M.Z_BRACO_T[1] - M.Z_EIXO + M.R_PLACA)
    a, b = vp.P((0, 0, M.Z_EIXO)), vp.P((0, 0, M.Z_BRACO_T[1]))
    cota_v(F.s, a[1], b[1], xd - D, None, None,
           valor=M.Z_BRACO_T[1] - M.Z_EIXO, lado_txt=-1)
    ang = math.radians(42)
    chamada(F.s, c[0] + M.D_BORE / 2 * vp.k * math.cos(ang),
            c[1] - M.D_BORE / 2 * vp.k * math.sin(ang), 60, 29,
            [f'Ø{num(M.D_BORE, 0)} H8 passante',
             'corpo do motor (Ø86,5 máx.)'], ponta='seta', lado=1)
    fcf(F.s, 60, 38, 'conc', 'Ø0,1', ('C',))
    t0 = math.radians(90 + 360 / M.MPW_N_FUROS)
    chamada(F.s, c[0] - M.MPW_PCD / 2 * vp.k * math.cos(t0),
            c[1] - M.MPW_PCD / 2 * vp.k * math.sin(t0), 34, 236,
            [f'{M.MPW_N_FUROS}× Ø4,5 eq. esp.',
             f'sobre Ø{num(M.MPW_PCD, 0)} (MPW86)'], ponta='seta', lado=1)
    fcf(F.s, 34, 252, 'pos', 'Ø0,2', ('B', 'C'))
    referencia(F.s, c[0] + M.R_PLACA * vp.k - 2, c[1], 'C', 0.0)
    rotulo(F.s, 99, 212, 'W-02 · VISTA DA FACE DE MONTAGEM (DE +Y)', esc(vp))

    # ---- corte no eixo do cubo
    meia = recorta_caixa(canto + [p.como('ref') for p in M.mpw86_ref(M.XS, 1)],
                         y=(150.0, 320.0))
    va = vista_no_retangulo(meia, 'frontal', 158, 26, 246, 190)
    desenha_corte(F.s, va, meia, 'x', M.XS)
    face = va.P((0, M.Y_FACE, M.Z_EIXO + 60))
    F.s.ln(face[0], face[1], 228, face[1], 'gdt')
    seta(F.s, face[0], face[1], 0.0)
    fcf(F.s, 228, face[1] - 6, 'plan', '0,1')
    fcf(F.s, 228, face[1], 'perp', '0,3', ('A',))
    referencia(F.s, *va.P((0, M.Y_FACE, M.Z_EIXO)), 'B', 0.0)
    fr = va.P((0, M.Y_FACE, M.Z_EIXO - 36))
    F.s.ln(fr[0], fr[1], 224, fr[1] + 8, 'gdt')
    F.s.ln(224, fr[1] + 8, 242, fr[1] + 8, 'gdt')
    rugosidade(F.s, 228, fr[1] + 8, 'Ra 3,2')
    a, b = va.P((0, M.Y_FACE - M.E_PLACA, 0)), va.P((0, M.Y_FACE, 0))
    cota_h(F.s, a[0], b[0], 197, None, None, valor=M.E_PLACA)
    simbolo_solda(F.s, *va.P((0, M.Y_BRACO[1], M.Z_BRACO_T[1])), 176, 176, a='a4',
                  cauda='em cima e embaixo', comp=24)
    rotulo(F.s, 199, 214, 'CORTE NO EIXO DO CUBO', esc(va), 'o braço chega por dentro')

    br = _sus().braco_tensoes()
    F.bloco(TXT_X, TXT_Y, TXT_W, f'''
<h3>W-02 · chapa de montagem do motor-roda</h3>
<p>Era a <b>S-02</b> até a Rev F. Mudou de nome porque mudou de função: não é mais só a
interface do motor, é peça de suspensão — a carga da roda entra por ela. A sugestão 2.4 do
fabricante, que pedia esta peça em aço, está <b>implementada</b> nesta revisão
{tag('NOVO')}, e por uma razão que a Rev F ainda não tinha: fadiga.</p>
{_tab_ops(['W-02'])}
<h3>As três referências</h3>
{tabela(['Datum', 'O que é', 'Para que serve'], [
    ['A', 'face de assento do berço do pivô, em Z 248',
     'orienta o conjunto no rover; dela se mede a perpendicularidade da face do motor'],
    ['B', f'face de montagem do motor, em |Y| {num(M.Y_FACE, 0)}',
     'é a face usinada: planeza 0,1 e perpendicular 0,3 a A'],
    ['C', f'eixo do alojamento Ø{num(M.D_BORE, 0)} H8',
     'referência de posição dos 7 furos do flange'],
], col=[12, 42, 46])}
<h3>Planicidade 0,1 — por que fica, e o que falta</h3>
<p>O fabricante sugeriu revisar os 0,1 mm {tag('A VALIDAR')}. A planicidade fica em 0,1, e a
razão é o aço: numa face de alumínio apertada por 7 parafusos M4 que saem e voltam a cada
manutenção, especificar 0,1 é inútil — a face amassa na terceira desmontagem. Em A36 a face
se mantém, e aí a cota passa a significar algo. <b>O que ainda falta é a resposta da
ElectroCraft</b>: a planicidade que o motor realmente exige não está publicada (P-04).</p>
<ol class="notas">
<li>Faceamento SEMPRE depois de soldar o braço. A solda distorce a chapa, e o que importa
é a planeza da peça pronta, não a da chapa cortada.</li>
<li>Espessura final após faceamento ≥ {num(M.E_PLACA - 0.5, 1)} mm. Abaixo disso, refugar:
o engajamento dos M4 é de 4 mm contra os 5 mm máximos do motor, e não há folga.</li>
<li>Momento de projeto no pé da solda: {num(br["momento_Nmm"], 0)} N·mm; fator de segurança
da solda {dec(br["fs_solda"], 1)}. {tag('CALC')}</li>
<li>Em alumínio soldado (ZTA 110 MPa) o fator de segurança do braço cairia de
{dec(br["fs_fechada"], 2)} para {dec(br["se_fosse_aluminio_fs"], 2)} — e perderia o limite de
fadiga, que é o que não se recupera com espessura. {tag('CALC')}</li>
</ol>''')
    return F


# ======================================================================== F30
def f30():
    F = Folha(30, escala='—', material='W-04/05/06 Aço · W-07 Inox 304',
              tolerancia='ISO 2768-mK · soldado ISO 13920-BF')
    canto = _canto()
    torre = so(canto, 'W-05', 'W-06', 'W-07')

    # ---- vista lateral da torre
    vl = vista_no_retangulo(torre + so(canto, 'W-04'), 'lateral_e', 32, 26, 134, 120)
    desenha(F.s, vl, torre + so(canto, 'W-04'))
    a, b = vl.P((M.X_PIVO - 24.0, 0, 0)), vl.P((M.X_PIVO + 22.0, 0, 0))
    cota_h(F.s, a[0], b[0], 126, None, None, valor=46)
    xd = min(a[0], b[0]) - 8
    a, b = vl.P((0, 0, M.Z_BRACO)), vl.P((0, 0, M.Z_BERCO_PIVO[1]))
    cota_v(F.s, a[1], b[1], xd, None, None, valor=M.Z_BERCO_PIVO[1] - M.Z_BRACO)
    a, b = vl.P((0, 0, M.Z_BERCO_PIVO[0])), vl.P((0, 0, M.Z_BERCO_PIVO[1]))
    cota_v(F.s, a[1], b[1], xd - D, None, None, valor=M.E_BERCO_PIVO, lado_txt=-1)
    linha_centro(F.s, *vl.P((M.X_PIVO, 0, M.Z_BRACO - 36)), *vl.P((M.X_PIVO, 0, M.Z_BRACO + 36)))
    chamada(F.s, *vl.P((M.X_PIVO, 0, M.Z_BRACO)), 36, 168,
            [f'Ø{num(M.D_PIVO, 0)} H7 nas duas orelhas',
             'coaxiais em 0,05 · eixo W-07'], lado=1)
    referencia(F.s, *vl.P((M.X_PIVO, 0, M.Z_BERCO_PIVO[1])), 'A', -math.pi / 2)
    rotulo(F.s, 83, 142, 'TORRE DO PIVÔ · VISTA DE +Y', esc(vl), 'referência A = face de assento')

    # ---- vista de +X
    ctx = [p.como('ctx') for p in so(canto, 'W-01', 'W-04')]
    vf = vista_no_retangulo(ctx + torre, 'frontal', 146, 26, 246, 120)
    desenha(F.s, vf, ctx + torre)
    a, b = vf.P((0, M.Y_ORELHA[0] + M.E_ORELHA, 0)), vf.P((0, M.Y_ORELHA[1], 0))
    cota_h(F.s, a[0], b[0], 126, None, None,
           valor=M.Y_ORELHA[1] - M.Y_ORELHA[0] - M.E_ORELHA)
    a, b = vf.P((0, M.Y_FUROS_SUSP[0], 0)), vf.P((0, M.Y_FUROS_SUSP[1], 0))
    cota_h(F.s, a[0], b[0], 133, None, None, valor=M.Y_FUROS_SUSP[1] - M.Y_FUROS_SUSP[0])
    for y in M.Y_FUROS_SUSP:
        cruz_centro(F.s, *vf.P((M.X_CANTO, y, M.Z_BERCO_PIVO[1])), 3.0)
    chamada(F.s, *vf.P((M.X_CANTO, M.Y_FUROS_SUSP[1], M.Z_BERCO_PIVO[1])), 182, 170,
            ['2× Ø8,5 · M8×65 passante', 'atravessa 4 níveis — folha 33'], lado=1)
    chamada(F.s, *vf.P((0, M.Y_BRACO[1], M.Z_BRACO)), 182, 186,
            [f'folga de giro '
             f'{num((M.Y_ORELHA[1] - M.Y_ORELHA[0] - M.E_ORELHA - M.L_BUCHA) / 2, 0)} mm',
             'por lado, entre bucha e orelha'], lado=1)
    rotulo(F.s, 196, 148, 'VISTA DE +X', esc(vf), 'o braço em linha de contexto')

    # ---- eixo W-07, 1:1
    y0, L, d, x0 = 198.0, 66.0, M.D_PIVO, 48.0
    F.s.rect(x0, y0 - d / 2, x0 + L, y0 + d / 2, 'vis')
    for xr in (x0 + 4.0, x0 + L - 4.0):
        F.s.rect(xr - 0.55, y0 - d / 2, xr + 0.55, y0 - d / 2 + 1.2, 'vis')
        F.s.rect(xr - 0.55, y0 + d / 2 - 1.2, xr + 0.55, y0 + d / 2, 'vis')
    linha_centro(F.s, x0 - 6, y0, x0 + L + 6, y0)
    cota_h(F.s, x0, x0 + L, y0 + 24, None, None, valor=L)
    cota_h(F.s, x0 + 4.0, x0 + L - 4.0, y0 + 16, None, None, valor=L - 8)
    cota_v(F.s, y0 - d / 2, y0 + d / 2, x0 - 10, None, None, valor=d, lado_txt=-1)
    chamada(F.s, x0 + 4.0, y0 - d / 2, 96, 176, ['2× ranhura DIN 471 Ø20'], lado=1)
    rugosidade(F.s, x0 + L / 2, y0 - d / 2 - 5, 'Ra 0,8')
    rotulo(F.s, x0 + L / 2, 232, 'W-07 · EIXO DO PIVÔ', '1:1', 'inox 304 · Ø20 h7')

    pv = _sus().pivo()
    F.bloco(TXT_X, TXT_Y, TXT_W, f'''
<h3>Torre do pivô — o conjunto que pendura o braço no chassi</h3>
<p>Uma torre por canto: duas orelhas W-05 soldadas num berço W-06, tudo em aço, parafusado
por baixo da chapa de fundo. O eixo W-07 atravessa as orelhas e as duas buchas
autolubrificantes alojadas em W-04, dentro do braço.</p>
{_tab_ops(['W-04', 'W-05', 'W-06', 'W-07'], 'micro')}
<h3>Carga no pivô, e por que ele é pequeno</h3>
<p>O pivô carrega menos do que parece: o fole fica a {num(M.R_FOLE, 0)} mm dele e a roda a
{num(M.BRACO, 0)} mm, então o fole leva a maior parte da carga direto ao chassi. O que
sobra para o pivô é a diferença.</p>
{tabela(['Componente da carga', 'Valor de projeto'], [
    ['Vertical', f'{num(pv["f_vertical_N"], 0)} N'],
    ['Longitudinal (torque de pico sobre o raio da roda)', f'{num(pv["f_longitudinal_N"], 0)} N'],
    ['Lateral', f'{num(pv["f_lateral_N"], 0)} N'],
    ['<b>Resultante</b>', f'<b>{num(pv["resultante_N"], 0)} N</b>'],
    ['Eixo Ø20: corte · flexão',
     f'{dec(pv["tau_pino_MPa"], 1)} · {dec(pv["sigma_pino_MPa"], 1)} MPa (FS {dec(pv["fs_pino"], 1)})'],
    ['Pressão na bucha', f'{dec(pv["pressao_bucha_MPa"], 1)} de {num(pv["limite_bucha_MPa"], 0)} MPa'],
    ['Orelha W-05', f'{dec(pv["sigma_orelha_MPa"], 1)} MPa (FS {dec(pv["fs_orelha"], 1)})'],
], 'micro', col=[58, 42])}
<ol class="notas">
<li>Os dois furos Ø{num(M.D_PIVO, 0)} H7 são alargados <b>no mesmo passe</b>, depois de
soldar. Coaxialidade 0,05 — desalinhamento aqui força a bucha e come o curso em atrito.</li>
<li>Aço contra alumínio: o berço W-06 encosta na chapa de fundo em 5052 e no anel em 6061.
<b>Isolar</b> — arruela de nylon sob a cabeça e sob a porca, berço zincado ou pintado.</li>
<li>A bucha autolubrificante Ø23/Ø20 é COMPRADA e não tem modelo escolhido
{tag('A VALIDAR')} — pendência P-21. O alojamento está desenhado para Ø23 H7.</li>
</ol>''')
    return F


# ======================================================================== F31
def f31():
    F = Folha(31, escala='—', material='W-08/09/10 Aço e inox · W-11/12/13 Al 6061-T6',
              tolerancia='ISO 2768-mK · soldado ISO 13920-BF')
    canto = _canto()
    fole = [p.como('ref') for p in M.fole_ref(1, 1)]
    pecas = so(canto, 'W-01', 'W-08', 'W-09', 'W-10', 'W-11', 'W-12', 'W-13') + fole
    pecas += [p.como('ctx') for p in so(M.chapa_fundo(), 'C-01')]
    meia = recorta_caixa(pecas, y=(120.0, 300.0))

    # ---- corte vertical no eixo do fole
    va = vista_no_retangulo(meia, 'frontal', 36, 26, 184, 148)
    desenha_corte(F.s, va, meia, 'x', M.X_FOLE)
    xd = va.P((0, 300.0, 0))[0] + 10
    a, b = va.P((0, 0, M.Z_BRACO_T[1])), va.P((0, 0, M.Z_BERCO_FOLE[0]))
    cota_v(F.s, a[1], b[1], xd, None, None, valor=M.H_FOLE)
    a, b = va.P((0, 0, M.Z_QUADRO - M.E_CHAPA)), va.P((0, 0, M.Z_BERCO_FOLE[0]))
    cota_v(F.s, a[1], b[1], xd + D, None, None,
           valor=M.Z_BERCO_FOLE[0] - M.Z_QUADRO + M.E_CHAPA, lado_txt=-1)
    a, b = va.P((0, M.Y_FOLE - M.D_COLAR / 2, 0)), va.P((0, M.Y_FOLE + M.D_COLAR / 2, 0))
    cota_h(F.s, a[0], b[0], 158, None, None, valor=M.D_COLAR)
    linha_centro(F.s, *va.P((0, M.Y_FOLE, M.Z_BRACO - 30)),
                 *va.P((0, M.Y_FOLE, M.Z_BERCO_FOLE[1] + 12)))
    q = va.P((M.X_FOLE, M.Y_FOLE, 242.0))
    balao(F.s, q[0], q[1], 'W-15')
    baloes_sem_colisao(F, [
        ('W-11', va.P((M.X_FOLE, M.Y_FOLE - 50, M.Z_BERCO_FOLE[1]))),
        ('W-12', va.P((M.X_FOLE, M.Y_FOLE + M.D_COLAR / 2, 266.0))),
        ('W-13', va.P((M.X_FOLE, M.Y_FOLE + 55, M.Z_QUADRO - M.E_CHAPA - 2))),
        ('W-08', va.P((M.X_FOLE, M.Y_FOLE + 28, M.Z_BRACO_T[1] - 4)))], (30.0, 24.0, 190.0, 152.0))
    chamada(F.s, *va.P((0, M.Y_FOLE + M.D_PASSAGEM / 2, M.Z_QUADRO - 1)), 190, 96,
            [f'passagem Ø{num(M.D_PASSAGEM, 0)} na chapa C-01',
             'junta NBR nas duas faces do colar'], lado=1)
    rotulo(F.s, 110, 166, 'INTERFACE DO FOLE · CORTE EM X 425', esc(va),
           'meia seção; o colar fecha o compartimento')

    # ---- disco do prato, em planta
    cx, cy, kp = 110.0, 206.0, 1.0
    F.s.circ(cx, cy, M.D_PRATO / 2 * kp, 'vis')
    F.s.circ(cx, cy, 6.0 * kp, 'vis')
    linha_centro(F.s, cx - M.D_PRATO / 2 * kp - 6, cy, cx + M.D_PRATO / 2 * kp + 6, cy)
    linha_centro(F.s, cx, cy - M.D_PRATO / 2 * kp - 6, cx, cy + M.D_PRATO / 2 * kp + 6)
    for s in (1, -1):
        F.s.rect(cx - 14.0 * kp, cy + s * 4.0 * kp, cx + 14.0 * kp, cy + s * 12.0 * kp, 'hid')
    cota_h(F.s, cx - M.D_PRATO / 2 * kp, cx + M.D_PRATO / 2 * kp,
           cy + M.D_PRATO / 2 * kp + 12, None, None, valor=M.D_PRATO)
    cota_v(F.s, cy - 12.0 * kp, cy + 12.0 * kp, cx - M.D_PRATO / 2 * kp - 10,
           None, None, valor=24, lado_txt=-1)
    chamada(F.s, cx + 6.0 * kp, cy, 180, 206, ['M12 × 1,75 passante',
                                               'fixação inferior do fole'], lado=1)
    rugosidade(F.s, cx, cy - M.D_PRATO / 2 * kp - 7, 'Ra 1,6')
    rotulo(F.s, cx, 278, 'W-08 + W-09 · PRATO ARTICULADO', '1:1',
           'orelhas em tracejado (W-09, 2 un)')

    pr = _sus().pratos()
    fl = _sus().fole()
    bt = _sus().batentes()
    F.bloco(TXT_X, TXT_Y, TXT_W, f'''
<h3>Interface do fole — seis peças e um componente comprado</h3>
<p>A peça comprada é o fole (W-15). Tudo o mais nesta folha existe para que ele se apoie,
se articule e não abra o compartimento. <b>Nenhum desenho desta folha depende de qual fole
for escolhido</b> — eles atendem ao envelope da folha 07, e atendem igualmente a um
cilindro pneumático de mesma área.</p>
{_tab_ops(['W-08', 'W-09', 'W-10', 'W-11', 'W-12', 'W-13'], 'micro')}
<h3>Por que o prato é articulado</h3>
<p>O braço gira {dec(_sus().geometria()["giro_total_deg"], 1)}° de batente a batente. Um prato
rígido inclinaria o fole nesse mesmo ângulo, e fole não aceita isso — trabalha em
cisalhamento e rasga na dobra. O prato sobre o pino W-10 <b>fica horizontal</b> enquanto o
braço gira. O pino articula só em torno de Y, que é o único grau necessário: braço
longitudinal não muda câmber.</p>
{tabela(['Verificação', 'Valor', 'FS'], [
    ['Força de projeto no fole', f'{num(pr["f_fole_projeto_N"], 0)} N', '—'],
    ['Pino W-10 em corte (4 planos)', f'{dec(pr["tau_pino_MPa"], 1)} MPa', f'{dec(pr["fs_pino"], 1)}'],
    ['Esmagamento na parede do braço', f'{dec(pr["esmagamento_parede_MPa"], 1)} MPa',
     f'{dec(pr["fs_esmagamento"], 1)}'],
    [f'Berço W-11 em flexão, vão {num(pr["berco_vao_mm"], 0)}',
     f'{dec(pr["berco_sigma_MPa"], 1)} MPa', f'{dec(pr["berco_fs"], 2)}'],
], 'micro', col=[54, 26, 20])}
<ol class="notas">
<li>A flange W-13 é um círculo <b>cortado reto em |X| 470</b>. Não é economia de material:
o círculo inteiro Ø{num(M.D_FLANGE_COLAR, 0)} encontraria o berço do pivô, que começa em
|X| {num(M.X_PIVO - 24, 0)}. {tag('CALC')}</li>
<li>Folga radial fole–colar: {num((M.D_COLAR - 2 * M.E_COLAR - M.D_FOLE) / 2, 0)} mm; o fole dilata. {tag('CALC')}</li>
<li>O fole não vê a carga de projeto: ao fim do curso está em {num(bt["forca_ao_fim_do_curso_N"], 0)} N
({dec(bt["fracao_da_projeto"] * 100, 0)} %); o resto vai ao batente interno — <b>requisito de compra</b>. {tag('CALC')}</li>
</ol>''')
    return F


# ======================================================================== F32
def f32():
    """Mapa de posições, em duas colunas de A3, repartidas pela ALTURA que cada uma tem.

    A tabela tem 62 códigos e não cabe num bloco só — e `.folha` tem `overflow: hidden`,
    então o que não cabe desaparece sem aviso. A coluna da esquerda vai até o pé da folha
    (X < 235); a da direita termina em Y 236, onde começa o carimbo. As linhas são
    repartidas por altura estimada, e não por grupo: da primeira vez a repartição era por
    grupo e a coluna da direita entrava no carimbo, com 112 linhas de texto sobre ele.
    """
    F = Folha(32, escala='—', material='—')
    MO = _mont()
    mapa = MO.mapa()
    ordem = ('Q', 'C', 'W', 'M', 'T', 'G', 'K', 'B', 'E', 'N')

    todas = []
    atual = None
    for g in ordem:
        for d in mapa:
            if d['grupo'] != g:
                continue
            if g != atual:
                atual = g
                todas.append(('g', f'<tr class="grupo"><td colspan="6">{g} — {M.GRUPOS[g]}</td></tr>', 3.4))
            viz = ', '.join(d['vizinhas']) or '—'
            como = d['como'] + (f' · {dec(d["torque"], 0)} N·m' if d['torque'] else '')
            linhas_ = max(math.ceil(len(viz) / 30), math.ceil(len(como) / 30), math.ceil(len(d['nome']) / 26), 1)
            todas.append(('l', [
                f'<b>{d["item"]}</b>', d['nome'], str(d['qtd']),
                f'X {dec(d["x"][0], 0)}…{dec(d["x"][1], 0)} · Y {dec(d["y"][0], 0)}…{dec(d["y"][1], 0)}'
                f' · Z {dec(d["z"][0], 0)}…{dec(d["z"][1], 0)}', viz, como],
                2.9 * linhas_ + 0.7))

    cab = ['item', 'nome', 'qt', 'posição (caixa)', 'encosta em', 'como prende']
    cols = [8, 17, 3, 27, 22, 23]
    orcamento = (270.0 - 28.0, 236.0 - 20.0 - 26.0)          # esquerda: até o pé; direita: até o carimbo, com o texto
    cols_lin = ([], [])
    gasto, k = 0.0, 0
    for tipo, conteudo, h in todas:
        if k == 0 and gasto + h > orcamento[0]:
            k, gasto = 1, 0.0
        gasto += h
        cols_lin[k].append(conteudo)

    F.bloco(26, 18, 196, f'''
<h3>Onde vai cada peça</h3>
<p class="mini">Caixa envolvente de UM exemplar, no referencial do rover: origem no solo, no
centro do polígono das rodas; <b>X</b> para a frente, <b>Y</b> para a esquerda, <b>Z</b>
para cima. Os demais exemplares são espelhados. "Encosta em" foi <b>medida</b> peça contra
peça no modelo.</p>
{tabela(cab, cols_lin[0], cls='nano', col=cols)}''')

    F.bloco(226, 18, 184, f'''
{tabela(cab, cols_lin[1], cls='nano', col=cols)}
<p class="mini"><b>Como ler:</b> a caixa diz <b>onde</b> está a peça; "encosta em" diz se você a montou
no lugar certo — se a vizinha não estiver lá, a ordem está errada (folha 34). {len(mapa)} códigos,
gerados de <code>revisao-h/montagem.py</code>; <code>python montagem.py --item W-01</code> dá
uma peça só. A versão paginada é <code>VTX-RV4-MONTAGEM-H.pdf</code>.</p>''')
    return F


# ======================================================================== F33
def f33():
    F = Folha(33, escala='1:2', material='—')
    canto = _canto()
    fole = [p.como('ref') for p in M.fole_ref(1, 1)]
    explode = []
    desloc = {'W-02': (-60, 0, -40), 'W-03': (-110, 0, 0), 'W-04': (0, 70, 0),
              'W-05': (0, 0, 60), 'W-06': (0, 0, 110), 'W-07': (0, 120, 0),
              'W-08': (0, 0, -70), 'W-09': (0, 60, -70), 'W-10': (0, 110, -40),
              'W-11': (0, 0, 70), 'W-12': (0, 0, 40), 'W-13': (0, 0, 30)}
    for p in canto + fole:
        dx, dy, dz = desloc.get(p.item, (0, 0, 0))
        explode.append(p.movido(dx, dy, dz))
    cam = iso_no_retangulo(explode, 26, 22, 172, 180, 2.0, az=-128, el=20)
    desenha_iso(F.s, cam, explode)
    for p in explode:
        pass
    vistos, alvos = set(), []
    for p in explode:
        if p.item in vistos:
            continue
        vistos.add(p.item)
        bb = p.bbox()
        alvos.append((p.item, cam.P(((bb[0][0] + bb[0][1]) / 2, bb[1][1], (bb[2][0] + bb[2][1]) / 2))))
    baloes_sem_colisao(F, alvos, (26.0, 22.0, 176.0, 182.0))
    rotulo(F.s, 99, 188, 'CANTO DE SUSPENSÃO · EXPLODIDA', '1:2',
           'dianteiro esquerdo; os outros três espelhados')

    MO = _mont()
    passos = [
        ('1', 'Cortar e pré-furar W-01, W-02, W-03', 'bancada',
         'o alojamento Ø34 e os furos Ø12 ficam com sobremetal'),
        ('2', 'Tornear W-04 com sobremetal no alojamento', 'torno',
         'Ø22,7 — o alargamento final é depois da solda'),
        ('3', 'Montar W-01 + W-02 + W-03 em dispositivo', 'dispositivo',
         'a sobreposição do braço na chapa define a bitola: 72 mm, aferir'),
        ('4', 'Soldar: braço na chapa (a4 em cima e embaixo), tampa no contorno', 'TIG/MIG',
         'esmerilhar o pé do cordão nas duas pontas — requisito de fadiga'),
        ('5', 'Soldar W-04 atravessando o braço', 'TIG/MIG',
         'a4 nas duas faces; é o que distorce as paredes, e por isso vem antes do alargador'),
        ('6', 'Alargar o alojamento Ø23 H7 e facear a chapa W-02', 'fresa + alargador',
         'nesta ordem: o alargador referencia a chapa já faceada'),
        ('7', 'Prensar as duas buchas autolubrificantes em W-04', 'prensa',
         'interferência leve; a bucha não gira, o eixo gira'),
        ('8', 'Soldar W-05 + W-06 em dispositivo, alargar Ø20 H7 no mesmo passe', 'TIG + alargador',
         'coaxialidade 0,05 entre as duas orelhas'),
        ('9', 'Soldar W-12 + W-13 e ensaiar estanqueidade', 'TIG + bolha',
         '0,5 bar em água, sem bolha em 60 s'),
        ('10', 'Soldar W-09 em W-08 e alargar Ø12 H7', 'TIG + alargador',
         'eixo do pino paralelo à face do disco em 0,1'),
        ('11', 'Tratar superficialmente: aço zincado/pintado, alumínio anodizado',
         'tratamento', 'antes de montar — aço contra alumínio precisa de barreira'),
        ('12', 'Montar o canto: eixo W-07, anéis, prato, fole e cabo W-14', 'montagem',
         'o rover não recebe o canto antes do item 7 da folha 34'),
    ]
    F.bloco(178, 20, 232, f'''
<h3>Sequência do canto de suspensão — 12 passos</h3>
<p>Os quatro cantos são montados <b>fora do rover</b>, em bancada. Não é conveniência: a
usinagem da chapa W-02 precisa de acesso de fresa dos dois lados, e o alargamento do
alojamento da bucha precisa de haste passando pelas duas paredes do braço.</p>
{tabela(['n', 'operação', 'onde', 'o que não pode dar errado'], passos, col=[5, 38, 16, 41])}
<h3>A regra que organiza tudo isso</h3>
<p><b>Solda primeiro, tolerância depois.</b> Toda operação de alargador, faceamento e
alargamento desta folha vem DEPOIS de todo cordão de solda que a afeta. Solda distorce; se
a tolerância foi feita antes, ela se perdeu e ninguém vai notar até o eixo não entrar.</p>
<h3>Conferências do canto, antes de ir para o rover</h3>
{tabela(['O que medir', 'Critério'], [
    ['Sobreposição braço × chapa', '72 mm'],
    ['Coaxialidade do alojamento da bucha', '0,05 entre as duas paredes'],
    ['Planeza da face de montagem do motor', '0,1 na área Ø105,7'],
    ['Perpendicularidade da face ao datum A', '0,3'],
    ['Espessura da chapa após faceamento', f'≥ {num(M.E_PLACA - 0.5, 1)} mm'],
    ['Giro livre do braço no eixo, sem fole', 'de batente a batente, sem ponto duro'],
    ['Estanqueidade do colar', 'sem bolha a 0,5 bar em 60 s'],
], col=[58, 42])}
<p class="mini">Torques: {', '.join(f'{r} {dec(n, 0)} N·m' for (r, n, _) in MO.TORQUES)}.</p>''')
    return F


# ======================================================================== F34
def f34():
    F = Folha(34, escala='—', material='—')
    MO = _mont()
    seq = [[n, titulo, razao, '<br>'.join('· ' + x for x in notas)]
           for (n, titulo, razao, notas) in MO.SEQUENCIA]
    F.bloco(28, 20, 180, f'''
<h3>Sequência geral de montagem — do quadro nu ao rover pronto</h3>
<p>Quinze etapas. A coluna do meio é a que importa: <b>por que</b> a etapa está nessa
posição. Quem inverte duas etapas sem ler essa coluna descobre o motivo desmontando.</p>
{tabela(['n', 'etapa', 'por que aqui', 'cuidados'], seq, cls='micro', col=[4, 24, 42, 30])}''')
    F.bloco(216, 20, 194, f'''
<h3>Torques de aperto</h3>
{tabela(['Rosca', 'N·m', 'Onde'],
        [[r, f'{dec(n, 1)}', o] for (r, n, o) in MO.TORQUES], col=[26, 12, 62])}
<p class="mini">Inox A4-70 lubrificado, 70 % do escoamento. <b>O M8 da suspensão aperta
quatro peças em série</b> — berço do fole, bucha de compressão, chapa de fundo e berço do
pivô — e é a bucha que define o torque. Sem ela, 25 N·m amassam o tubo 30×30×2.</p>

<h3>Conferências de aceite</h3>
{tabela(['O que', 'Critério', 'Por que'],
        [[o, c, p] for (o, c, p) in MO.CONFERENCIAS], col=[26, 38, 36])}

<h3>O que NÃO montar ainda</h3>
<p>Três coisas deste projeto não existem e não devem ser improvisadas na montagem:</p>
<ol class="notas">
<li><b>O fole W-15 não tem modelo escolhido</b> {tag('A VALIDAR')}. A interface está
desenhada e aceita qualquer um que feche a folha de requisitos da folha 07. Montar com um
fole fora de requisito muda o curso, a pressão e a altura — e nenhum dos três é ajustável
depois.</li>
<li><b>A bucha autolubrificante do pivô</b> {tag('A VALIDAR')} — pendência P-21.</li>
<li><b>A bateria</b>: a altura máxima da zona central é
{num(_mod('espaco').requisitos_de_componente()[0]["altura_maxima"], 0)} mm, medida, e a
caixa estimada tem 130. Ver folha 35 e <code>revisao-h/espaco.py</code>.</li>
</ol>
<p class="mini">Gerado de <code>revisao-h/montagem.py</code>. A sequência e os torques são
decisão de projeto declarada lá; as coordenadas e as vizinhanças da folha 32 são extraídas
do modelo.</p>''')
    return F


# ======================================================================== F35
def f35():
    F = Folha(35, escala='—', material='—')
    SU = _sus()
    ES = _mod('espaco')
    fl, g = SU.fole(), SU.geometria()
    vol = ES.volume_interno()

    # ---- diagrama de curso do braço, no referencial da carroceria
    k = 0.26
    xr0, yr0 = 36.0, 42.0
    xp0 = xr0 + M.BRACO * k
    F.s.tx(30, 24, 'CURSO DO BRAÇO E AJUSTE DE ALTURA', 4.2, a='start', c='tx tit')
    F.s.tx(30, 29, 'o pivô está parado e a roda sobe e desce', 2.4, a='start', c='tx sec')
    for (nome, dz, cor) in (('compressão total', -M.CURSO_TRABALHO, 'ref'),
                            ('vão 150 — desenhada', 0.0, 'vis'),
                            ('vão 180 — alta', M.AJUSTE_ALTURA, 'hid'),
                            ('extensão total, vão 180',
                             M.AJUSTE_ALTURA + M.CURSO_TRABALHO, 'ref')):
        yr = yr0 + dz * k
        xr = xr0 + (M.BRACO - math.sqrt(max(M.BRACO ** 2 - dz ** 2, 0.0))) * k
        F.s.ln(xr, yr, xp0, yr0, cor)
        F.s.circ(xr, yr, 1.1, cor)
        ang = math.degrees(math.asin(min(abs(dz) / M.BRACO, 1.0))) * (-1 if dz >= 0 else 1)
        F.s.tx(xp0 + 4, yr + 1.0, f'{nome}   ({ang:+.1f}°)', 2.5, a='start', c='tx sec')
    F.s.circ(xp0, yr0, 1.4, 'arrv')
    F.s.tx(xp0, yr0 - 5, 'pivô', 2.4, c='tx sec')
    cota_v(F.s, yr0 - M.CURSO_TRABALHO * k,
           yr0 + (M.AJUSTE_ALTURA + M.CURSO_TRABALHO) * k, 30.0, None, None,
           valor=M.CURSO_RODA, lado_txt=-1)

    # diagrama de pressão × altura
    x0, y0, w, h = 34.0, 150.0, 140.0, 86.0
    F.s.rect(x0, y0 - h, x0 + w, y0, 'hid0')
    for i in range(5):
        yy = y0 - h * i / 4
        F.s.ln(x0, yy, x0 + w, yy, 'hid0')
        F.s.tx(x0 - 2, yy + 1, f'{i * 2}', 2.4, a='end', c='tx sec')
    F.s.tx(x0 - 2, y0 - h - 5, 'bar', 2.4, a='end', c='tx sec')
    pontos = [('estática', fl['p_estatica_bar'], 'vis'),
              ('dinâmica', fl['p_dinamica_bar'], 'hid'),
              ('projeto', fl['p_projeto_bar'], 'hid'),
              ('teto do componente', SU.PRESSAO_MAXIMA_BAR, 'ref')]
    for i, (nome, p, cor) in enumerate(pontos):
        xx = x0 + w * (i + 0.5) / len(pontos)
        hh = h * min(p / 8.0, 1.0)
        F.s.rect(xx - 9, y0 - hh, xx + 9, y0, cor)
        F.s.tx(xx, y0 - hh - 3, f'{dec(p, 2)}', 2.5, peso=700)
        F.s.tx(xx, y0 + 5, nome, 2.3, c='tx sec')
    rotulo(F.s, x0 + w / 2, y0 + 14, 'PRESSÃO DO FOLE POR CONDIÇÃO DE CARGA', None,
           f'área efetiva {num(fl["area_mm2"], 0)} mm²')

    F.bloco(28, 174, 146, f'''
<h3>Enchimento e nivelamento, na ordem</h3>
<ol class="notas">
<li><b>Ensaio seco primeiro.</b> Girar cada braço de batente a batente SEM o fole montado.
Nenhum ponto duro, nenhuma interferência. Se houver, para aqui.</li>
<li>Montar os quatro foles. Não pressurizar.</li>
<li>Encher devagar até {dec(fl["p_estatica_bar"], 2)} bar, um canto por vez, com o rover
apoiado em cavaletes e as rodas no ar.</li>
<li>Baixar nos pneus. Conferir o vão livre nos quatro cantos:
{num(g["vao_min"], 0)} ± 3 mm.</li>
<li>Calibrar os quatro sensores de altura W-16 nas duas extremidades do curso.</li>
<li>Subir à altura máxima ({num(g["vao_max"], 0)} mm) e conferir folga do cabo W-14 —
ele é o limitador de extensão, e tem de ficar esticado ali e só ali.</li>
<li>Ensaio de estanqueidade: {num(12, 0)} h parado, queda ≤ 0,2 bar.</li>
<li>Ensaio de ciclo: percurso de 1 km em terreno irregular; ciclo do compressor ≤ 15 %.</li>
</ol>''')

    F.bloco(182, 20, 228, f'''
<h3>Regulagem, verificação e o que o espaço interno realmente dá</h3>
{tabela(['Grandeza do sistema de ar', 'Valor', 'Origem'], [
    ['Pressão de trabalho (carga estática)', f'{dec(fl["p_estatica_bar"], 2)} bar', tag('CALC')],
    ['Pressão na condição dinâmica', f'{dec(fl["p_dinamica_bar"], 2)} bar', tag('CALC')],
    ['Pressão na condição de projeto', f'{dec(fl["p_projeto_bar"], 2)} bar', tag('CALC')],
    ['Teto exigido do componente', f'{dec(SU.PRESSAO_MAXIMA_BAR, 0)} bar', tag('NOVO')],
    ['Rigidez na roda', f'{dec(fl["k_roda_N_mm"], 2)} N/mm', tag('CALC')],
    ['Frequência de canto', f'{dec(fl["freq_Hz"], 2)} Hz', tag('CALC')],
    ['Vão livre ajustável', f'{num(g["vao_min"], 0)} → {num(g["vao_max"], 0)} mm', tag('NOVO')],
    ['Consumo médio do sistema', f'{dec(SU.energia()["total_W"], 1)} W', tag('CALC')],
    ['Ar por subida completa dos 4 cantos',
     f'{dec(SU.energia()["ar_por_subida_L_normal"], 2)} L normais', tag('CALC')],
], col=[48, 30, 22])}
<h3>Requisitos do controle de nível</h3>
{tabela(['Requisito', 'O que significa'],
        [[a, b] for (a, b) in SU.REQUISITOS_CONTROLE], col=[36, 64])}
<h3>Espaço interno — medido, não estimado</h3>
<p>O compartimento tem <b>{dec(vol["volume_livre_L"], 1)} L livres</b>, descontada toda peça do
modelo. Esse número não é o produto de três cotas externas: a altura livre varia de ponto a
ponto, porque as barras G-03 da gaiola descem a Z 377 e atravessam o rover em |X| 230 e 330.</p>
{tabela(['Zona', 'Altura máxima de componente', 'Área'],
        [[r['zona'], f'{num(r["altura_maxima"], 0)} mm', f'{num(r["area_cm2"], 0)} cm²']
         for r in ES.requisitos_de_componente()], col=[46, 30, 24])}
<ol class="notas">
<li>A <b>bateria estimada de 130 mm não cabe</b>: o teto da zona central é
{num(ES.requisitos_de_componente()[0]["altura_maxima"], 0)} mm. Como a ficha técnica da
bateria é pendência (P-05), isto vira <b>requisito de compra</b>: altura ≤ 125 mm. {tag('CALC')}</li>
<li>Todos os outros componentes estimados cabem — a varredura está em
<code>revisao-h/espaco.py</code>, seção 4, com a posição onde cada um entra.</li>
<li>A bandeja E-02 encolheu nesta revisão: ia de |Y| 105 a 250 e colidia com o colar do
fole. A faixa que sobra é 100 a 152. É perda real de área, e é o preço de ter
suspensão. {tag('NOVO')}</li>
<li>Modo de falha do sistema de ar: perda de pressão <b>desce</b> para o vão mínimo e
trava. Nunca sobe sozinho. É requisito de controle, não de hardware.</li>
</ol>''')
    return F


FOLHAS_W = [f28, f29, f30, f31, f32, f33, f34, f35]
