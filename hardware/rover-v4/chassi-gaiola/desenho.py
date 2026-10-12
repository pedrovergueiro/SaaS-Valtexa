"""Motor de desenho técnico em SVG: vistas ortográficas (1º diedro), cortes, isométricas,
cotas, chamadas e carimbo. Coordenadas de papel em mm (A3 paisagem, 420 × 297)."""
import math
from html import escape
from modelo import AXI, PLANO, area_poly

A3 = (420.0, 297.0)
# ABNT NBR 10068, formato A3: margem esquerda 25, demais 7; legenda com 178 de comprimento.
MOLDURA = (25.0, 7.0, 413.0, 290.0)
CARIMBO = (235.0, 238.0, 413.0, 290.0)
# ABNT NBR 8402 / ISO 3098: altura mínima de letra (maiúscula) 2,5 mm em A3.
# A família usada tem altura de maiúscula = 0,70 do corpo, então corpo 3,6 → maiúscula 2,52.
T = 3.6          # cotas, chamadas, notas
T_TIT = 5.0      # título de vista (maiúscula 3,5)
T_LEG = 2.6      # nomes de campo da legenda (maiúscula 1,8 — ISO 7200)


def f(v):
    s = f'{v:.2f}'.rstrip('0').rstrip('.')
    return '0' if s in ('-0', '') else s


def num(v, dec=2):
    """Texto de cota no padrão brasileiro (vírgula decimal, sem separador de milhar)."""
    if abs(v - round(v)) < 0.005:
        return str(int(round(v)))
    t = f'{v:.{dec}f}'
    if '.' in t:                      # só aparam-se zeros DEPOIS da vírgula: 220 não pode virar 22
        t = t.rstrip('0').rstrip('.')
    return t.replace('.', ',')


def dec(v, n=2):
    """Decimal em português, com casas FIXAS: 7,88 · 0,50 · 40,0. `num` apara zeros; este não."""
    return f'{v:.{n}f}'.replace('.', ',')


def milhar(v, dec=0):
    """Número para texto corrido: 1.050 / 5,54."""
    s = f'{v:,.{dec}f}'
    return s.replace(',', '§').replace('.', ',').replace('§', '.')


def dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def unit(a):
    n = math.sqrt(dot(a, a))
    return (a[0] / n, a[1] / n, a[2] / n)


class Svg:
    def __init__(self):
        self.b = []

    def raw(self, s):
        self.b.append(s)

    def ln(self, x1, y1, x2, y2, c='dim'):
        self.b.append(f'<line x1="{f(x1)}" y1="{f(y1)}" x2="{f(x2)}" y2="{f(y2)}" class="{c}"/>')

    def pl(self, pts, c='dim', fechar=False):
        tag = 'polygon' if fechar else 'polyline'
        self.b.append(f'<{tag} points="{" ".join(f"{f(x)},{f(y)}" for x, y in pts)}" class="{c}"/>')

    def aneis(self, rings, c, extra=''):
        d = ''.join('M' + 'L'.join(f'{f(x)},{f(y)}' for x, y in r) + 'Z' for r in rings if len(r) > 1)
        self.b.append(f'<path d="{d}" class="{c}" fill-rule="evenodd"{extra}/>')

    def circ(self, x, y, r, c='dim'):
        self.b.append(f'<circle cx="{f(x)}" cy="{f(y)}" r="{f(r)}" class="{c}"/>')

    def rect(self, x0, y0, x1, y1, c='dim'):
        self.b.append(f'<rect x="{f(min(x0, x1))}" y="{f(min(y0, y1))}" width="{f(abs(x1 - x0))}" '
                      f'height="{f(abs(y1 - y0))}" class="{c}"/>')

    def tx(self, x, y, s, t=2.5, a='middle', c='tx', rot=None, peso=None, extra=''):
        tr = f' transform="rotate({f(rot)} {f(x)} {f(y)})"' if rot else ''
        w = f' font-weight="{peso}"' if peso else ''
        self.b.append(f'<text x="{f(x)}" y="{f(y)}" font-size="{f(t)}" text-anchor="{a}" class="{c}"{w}{tr}{extra}>'
                      f'{escape(str(s))}</text>')

    def __str__(self):
        return '\n'.join(self.b)


# ================================================================== vistas
VISTAS = {  # direção do olhar, direita da tela, cima da tela
    'lateral': ((0, 1, 0), (1, 0, 0), (0, 0, 1)),      # vista lateral direita (observador em -Y)
    'lateral_e': ((0, -1, 0), (-1, 0, 0), (0, 0, 1)),  # vista lateral esquerda
    'superior': ((0, 0, -1), (1, 0, 0), (0, 1, 0)),
    'superior_inv': ((0, 0, -1), (-1, 0, 0), (0, -1, 0)),
    'inferior': ((0, 0, 1), (1, 0, 0), (0, -1, 0)),
    'frontal': ((-1, 0, 0), (0, 1, 0), (0, 0, 1)),     # olhando o rover de frente
    'traseira': ((1, 0, 0), (0, -1, 0), (0, 0, 1)),
}


class Vista:
    def __init__(self, tipo, escala, ox, oy):
        self.tipo = tipo
        self.d, self.r, self.up = VISTAS[tipo]
        self.escala = escala
        self.k = 1.0 / escala
        self.ox, self.oy = ox, oy

    def P(self, p):
        return (self.ox + dot(p, self.r) * self.k, self.oy - dot(p, self.up) * self.k)

    def dep(self, p):
        return dot(p, self.d)


def projeta(v, p):
    """Retorna (anéis em papel, linhas internas) da projeção do prisma na vista ortográfica."""
    i = AXI[p.eixo]
    if abs(v.d[i]) > 0.5:
        e = p.e0
        return [[v.P(p.mundo(a, b, e)) for a, b in anel] for anel in [p.perfil] + p.furos], []
    (x0, x1), (y0, y1), (z0, z1) = p.bbox()
    pts = [v.P((x, y, z)) for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)]
    X0, X1 = min(q[0] for q in pts), max(q[0] for q in pts)
    Y0, Y1 = min(q[1] for q in pts), max(q[1] for q in pts)
    linhas = []
    if not p.curvo:
        pa, pb = PLANO[p.eixo]
        kv = 0 if abs(v.d[AXI[pa]]) > 0.5 else 1
        ks = 1 - kv
        ds = v.d[AXI[(pa, pb)[kv]]]
        ccw = area_poly(p.perfil) > 0
        vals = set()
        per = p.perfil
        for j in range(len(per)):
            q0, q1 = per[j], per[(j + 1) % len(per)]
            ex, ey = q1[0] - q0[0], q1[1] - q0[1]
            n = (ey, -ex) if ccw else (-ey, ex)
            if n[kv] * ds < -1e-9:
                vals.add(round(q0[ks], 4))
                vals.add(round(q1[ks], 4))
        lo, hi = min(q[ks] for q in per), max(q[ks] for q in per)
        for val in vals:
            if lo + 1e-6 < val < hi - 1e-6:
                ab = [0.0, 0.0]
                ab[ks] = val
                ab[kv] = per[0][kv]
                linhas.append((v.P(p.mundo(ab[0], ab[1], p.e0)), v.P(p.mundo(ab[0], ab[1], p.e1))))
    return [[(X0, Y0), (X1, Y0), (X1, Y1), (X0, Y1)]], linhas


def desenha(svg, v, pecas, fantasma=True):
    corpo = [p for p in pecas if p.estilo in ('solid', 'ctx')]
    corpo.sort(key=lambda p: -v.dep(p.centro()))
    for p in corpo:
        aneis, linhas = projeta(v, p)
        c = 'ctx' if p.estilo == 'ctx' else 'vis'
        svg.aneis(aneis, c)
        for (a, b) in linhas:
            svg.ln(a[0], a[1], b[0], b[1], c + 'l')
    if fantasma:
        for p in pecas:
            if p.estilo == 'ref':
                aneis, _ = projeta(v, p)
                svg.aneis(aneis, 'ref')


def desenha_corte(svg, v, pecas, eixo, pos):
    s = v.d[AXI[eixo]]
    manter = 'ge' if s > 0 else 'le'
    restantes, regioes = [], []
    for p in pecas:
        c = p.recortado(eixo, pos, manter)
        if c is not None:
            restantes.append(c)
        if p.estilo in ('solid', 'oculto'):
            regioes += [(p.item, r) for r in p.secao(eixo, pos)]
    desenha(svg, v, restantes)
    # Peças vizinhas recebem hachuras diferentes (ângulo/espaçamento), como pede a ABNT NBR 12298.
    padroes = ('hach', 'hach2', 'hach3')
    for item, aneis in regioes:
        pts = [[v.P(q) for q in anel] for anel in aneis]
        xs = [q[0] for q in pts[0]]
        ys = [q[1] for q in pts[0]]
        fino = min(max(xs) - min(xs), max(ys) - min(ys)) < 1.4
        svg.aneis(pts, 'cheio' if fino else padroes[sum(map(ord, item)) % 3])


# ================================================================ isométrica
class Iso:
    def __init__(self, escala, ox, oy, az=-40.0, el=28.0):
        th, ph = math.radians(az), math.radians(el)
        c = (math.cos(ph) * math.cos(th), math.cos(ph) * math.sin(th), math.sin(ph))
        self.d = (-c[0], -c[1], -c[2])
        self.r = unit(cross(self.d, (0, 0, 1)))
        self.up = cross(self.r, self.d)
        self.k = 1.0 / escala
        self.ox, self.oy = ox, oy
        self.luz = unit((0.45, -0.25, 0.9))

    def P(self, p):
        return (self.ox + dot(p, self.r) * self.k, self.oy - dot(p, self.up) * self.k)

    def dep(self, p):
        return dot(p, self.d)


def _tom(n, luz, base=(255, 255, 255), amb=0.60):
    b = amb + (1 - amb) * max(0.0, dot(n, luz))
    return '#%02x%02x%02x' % tuple(int(min(255, c * b * (0.985 if i < 2 else 1))) for i, c in enumerate(base))


def _vec_plano(p, a, b):
    pa, pb = PLANO[p.eixo]
    w = [0.0, 0.0, 0.0]
    w[AXI[pa]] = a
    w[AXI[pb]] = b
    return tuple(w)


def _ordem(cam, pecas):
    """Ordenação topológica por eixo separador (pintor) — mais robusta que centroide."""
    n = len(pecas)
    bbs = [p.bbox() for p in pecas]
    scr = []
    for bb in bbs:
        pts = [cam.P((x, y, z)) for x in bb[0] for y in bb[1] for z in bb[2]]
        scr.append((min(q[0] for q in pts), min(q[1] for q in pts), max(q[0] for q in pts), max(q[1] for q in pts)))
    depois = [[] for _ in range(n)]   # i -> lista de j que devem ser desenhados depois de i
    grau = [0] * n
    for i in range(n):
        for j in range(i + 1, n):
            a, b = scr[i], scr[j]
            if a[2] <= b[0] + 1e-6 or b[2] <= a[0] + 1e-6 or a[3] <= b[1] + 1e-6 or b[3] <= a[1] + 1e-6:
                continue
            # Cada eixo em que as caixas se separam dá um veredito sobre quem fica na frente.
            # Se os vereditos divergem, nenhum raio atravessa as duas: as projeções não se
            # sobrepõem de fato e não há restrição (evita ciclos falsos com tubos longos).
            vereditos = set()
            for ax in range(3):
                dax = cam.d[ax]
                if abs(dax) < 1e-9:
                    continue
                gap1 = bbs[j][ax][0] - bbs[i][ax][1]   # j acima de i no eixo
                gap2 = bbs[i][ax][0] - bbs[j][ax][1]
                for gap, maior in ((gap1, j), (gap2, i)):
                    if gap >= -1e-6:
                        menor = i if maior == j else j
                        vereditos.add(maior if dax < 0 else menor)
            if len(vereditos) != 1:
                continue
            frente = vereditos.pop()
            tras = j if frente == i else i
            depois[tras].append(frente)
            grau[frente] += 1
    prof = [cam.dep(p.centro()) for p in pecas]
    import heapq
    fila = [(-prof[i], i) for i in range(n) if grau[i] == 0]
    heapq.heapify(fila)
    feito, ordem = [False] * n, []
    while len(ordem) < n:
        if not fila:
            resto = [i for i in range(n) if not feito[i]]
            k = max(resto, key=lambda i: prof[i])
            grau[k] = 0
            fila = [(-prof[k], k)]
        _, i = heapq.heappop(fila)
        if feito[i]:
            continue
        feito[i] = True
        ordem.append(pecas[i])
        for j in depois[i]:
            grau[j] -= 1
            if grau[j] == 0 and not feito[j]:
                heapq.heappush(fila, (-prof[j], j))
    return ordem


def desenha_iso(svg, cam, pecas):
    vis = [p for p in pecas if p.estilo in ('solid', 'ctx', 'ref')]
    for p in _ordem(cam, vis):
        _prisma_iso(svg, cam, p)


def _prisma_iso(svg, cam, p):
    ax = [0.0, 0.0, 0.0]
    ax[AXI[p.eixo]] = 1.0
    ax = tuple(ax)
    if p.estilo == 'ref':
        base, cl, amb = (236, 239, 242), 'isor', 0.78
    elif p.estilo == 'ctx':
        base, cl, amb = (246, 247, 248), 'isoc', 0.8
    else:
        base, cl, amb = (255, 255, 255), 'isov', 0.58
        if p.mat == '5052':
            base = (248, 250, 252)
        if p.mat == 'borracha':
            base, amb = (90, 96, 104), 0.7
    faces_furo, faces_lado, tampas = [], [], []
    aneis = [p.perfil] + p.furos
    for idx, anel in enumerate(aneis):
        if idx > 0 and len(anel) > 8:
            continue
        ccw = area_poly(anel) > 0
        for j in range(len(anel)):
            q0, q1 = anel[j], anel[(j + 1) % len(anel)]
            ex, ey = q1[0] - q0[0], q1[1] - q0[1]
            n2 = (ey, -ex) if ccw else (-ey, ex)
            if idx > 0:
                n2 = (-n2[0], -n2[1])
            nw = unit(_vec_plano(p, n2[0], n2[1])) if (n2[0] or n2[1]) else (0, 0, 1)
            if dot(nw, cam.d) >= -1e-9:
                continue
            pts = [p.mundo(q0[0], q0[1], p.e0), p.mundo(q1[0], q1[1], p.e0),
                   p.mundo(q1[0], q1[1], p.e1), p.mundo(q0[0], q0[1], p.e1)]
            (faces_furo if idx > 0 else faces_lado).append((nw, pts, j))
    for e, sgn in ((p.e0, -1), (p.e1, 1)):
        n = (ax[0] * sgn, ax[1] * sgn, ax[2] * sgn)
        if dot(n, cam.d) < 0:
            tampas.append((n, [[p.mundo(a, b, e) for a, b in anel] for anel in aneis]))
    for nw, pts, _ in faces_furo:
        cor = _tom(nw, cam.luz, base, amb - 0.12)
        svg.aneis([[cam.P(q) for q in pts]], cl, f' style="fill:{cor}"')
    if p.curvo:
        for nw, pts, _ in faces_lado:
            cor = _tom(nw, cam.luz, base, amb)
            svg.aneis([[cam.P(q) for q in pts]], 'isof', f' style="fill:{cor};stroke:{cor}"')
        vis = {j for _, _, j in faces_lado}
        per = p.perfil
        m = len(per)
        for j in vis:
            for viz, vert in (((j - 1) % m, j), ((j + 1) % m, (j + 1) % m)):
                if viz not in vis:
                    q = per[vert]
                    a, b = cam.P(p.mundo(q[0], q[1], p.e0)), cam.P(p.mundo(q[0], q[1], p.e1))
                    svg.ln(a[0], a[1], b[0], b[1], cl)
    else:
        for nw, pts, _ in faces_lado:
            cor = _tom(nw, cam.luz, base, amb)
            svg.aneis([[cam.P(q) for q in pts]], cl, f' style="fill:{cor}"')
    for n, an in tampas:
        cor = _tom(n, cam.luz, base, amb)
        svg.aneis([[cam.P(q) for q in anel] for anel in an], cl, f' style="fill:{cor}"')


# ==================================================================== cotas
def seta(svg, x, y, ang, c='arr'):
    L, H = 2.8, 0.55
    bx, by = x - L * math.cos(ang), y - L * math.sin(ang)
    px, py = -math.sin(ang) * H, math.cos(ang) * H
    svg.raw(f'<path class="{c}" d="M{f(x)},{f(y)}L{f(bx + px)},{f(by + py)}L{f(bx - px)},{f(by - py)}Z"/>')


def _larg_txt(txt, t):
    return len(txt) * t * 0.47


def cota_h(svg, x1, x2, y, ya=None, yb=None, txt=None, valor=None, t=T, desloc_txt=0.0, lado_txt=1):
    """Cota horizontal (NBR 10126). ya/yb: y (papel) dos pontos cotados, origem das linhas de chamada.
    Cota curta: setas por fora e texto ao lado (lado_txt = +1 à direita, −1 à esquerda)."""
    if x1 > x2:
        x1, x2, ya, yb = x2, x1, yb, ya
    for (x, yp) in ((x1, ya), (x2, yb)):
        if yp is not None:
            s = 1 if y > yp else -1
            svg.ln(x, yp + s * 1.0, x, y + s * 2.0, 'dim')
    svg.ln(x1, y, x2, y, 'dim')
    if txt is None:
        txt = num(valor)
    w = _larg_txt(txt, t)
    if x2 - x1 >= 8:
        seta(svg, x1, y, math.pi)
        seta(svg, x2, y, 0)
    else:
        seta(svg, x1, y, 0)
        seta(svg, x2, y, math.pi)
        svg.ln(x1 - 4.5, y, x1, y, 'dim')
        svg.ln(x2, y, x2 + 4.5, y, 'dim')
    if x2 - x1 >= w + 2:
        svg.tx((x1 + x2) / 2 + desloc_txt, y - 1.0, txt, t)
    elif lado_txt > 0:
        svg.tx(x2 + 5.0, y - 1.0, txt, t, a='start')
    else:
        svg.tx(x1 - 5.0, y - 1.0, txt, t, a='end')


def cota_v(svg, y1, y2, x, xa=None, xb=None, txt=None, valor=None, t=T, desloc_txt=0.0, lado_txt=1):
    """Cota vertical; texto girado, lido de baixo para cima (NBR 10126). Cota curta: texto por fora
    (lado_txt = +1 abaixo, −1 acima)."""
    if y1 > y2:
        y1, y2, xa, xb = y2, y1, xb, xa
    for (yv, xp) in ((y1, xa), (y2, xb)):
        if xp is not None:
            s = 1 if x > xp else -1
            svg.ln(xp + s * 1.0, yv, x + s * 2.0, yv, 'dim')
    svg.ln(x, y1, x, y2, 'dim')
    if txt is None:
        txt = num(valor)
    w = _larg_txt(txt, t)
    if y2 - y1 >= 8:
        seta(svg, x, y1, -math.pi / 2)
        seta(svg, x, y2, math.pi / 2)
    else:
        seta(svg, x, y1, math.pi / 2)
        seta(svg, x, y2, -math.pi / 2)
        svg.ln(x, y1 - 4.5, x, y1, 'dim')
        svg.ln(x, y2, x, y2 + 4.5, 'dim')
    if y2 - y1 >= w + 2:
        svg.tx(x - 1.0, (y1 + y2) / 2 + desloc_txt, txt, t, rot=-90)
    elif lado_txt > 0:
        svg.tx(x - 1.0, y2 + 5.0, txt, t, a='end', rot=-90)
    else:
        svg.tx(x - 1.0, y1 - 5.0, txt, t, a='start', rot=-90)


def cota_vista_h(svg, v, p1, p2, y, txt=None, **kw):
    """Cota horizontal entre dois pontos do mundo, na vista v."""
    a, b = v.P(p1), v.P(p2)
    val = abs(dot(p2, v.r) - dot(p1, v.r))
    cota_h(svg, a[0], b[0], y, a[1], b[1], txt=txt, valor=val, **kw)


def cota_vista_v(svg, v, p1, p2, x, txt=None, **kw):
    a, b = v.P(p1), v.P(p2)
    val = abs(dot(p2, v.up) - dot(p1, v.up))
    cota_v(svg, a[1], b[1], x, a[0], b[0], txt=txt, valor=val, **kw)


def chamada(svg, x0, y0, x1, y1, linhas, lado=1, ponta='ponto', t=T, larg=None):
    """Linha de chamada do ponto (x0,y0) até (x1,y1), com texto em uma ou mais linhas."""
    if isinstance(linhas, str):
        linhas = [linhas]
    if ponta == 'ponto':
        svg.circ(x0, y0, 0.45, 'arr')
    elif ponta == 'seta':
        seta(svg, x0, y0, math.atan2(y0 - y1, x0 - x1))
    svg.ln(x0, y0, x1, y1, 'dim')
    w = larg if larg is not None else max(_larg_txt(s, t) for s in linhas) + 1.5
    x2 = x1 + lado * w
    svg.ln(x1, y1, x2, y1, 'dim')
    a = 'start' if lado > 0 else 'end'
    xt = x1 + lado * 0.8
    for i, s in enumerate(linhas):
        svg.tx(xt, y1 - 1.0 + i * (t + 1.3), s, t, a=a)


def balao(svg, x, y, txt, alvo=None, r=None):
    if r is None:
        r = 3.6 if len(txt) <= 1 else (4.6 if len(txt) <= 3 else 5.9)
    t = T
    if alvo:
        ang = math.atan2(alvo[1] - y, alvo[0] - x)
        svg.ln(x + r * math.cos(ang), y + r * math.sin(ang), alvo[0], alvo[1], 'dim')
        svg.circ(alvo[0], alvo[1], 0.6, 'arr')
    svg.circ(x, y, r, 'balao')
    svg.tx(x, y + t * 0.35, txt, t, peso=600)


def linha_centro(svg, x1, y1, x2, y2):
    svg.ln(x1, y1, x2, y2, 'cl')


def cruz_centro(svg, x, y, r):
    linha_centro(svg, x - r - 2, y, x + r + 2, y)
    linha_centro(svg, x, y - r - 2, x, y + r + 2)


def plano_corte(svg, x1, y1, x2, y2, letra, ang_vista):
    """Traço do plano de corte (x1,y1)-(x2,y2); ang_vista = direção (rad) do olhar, em papel."""
    dx, dy = x2 - x1, y2 - y1
    L = math.hypot(dx, dy)
    ux, uy = dx / L, dy / L
    svg.ln(x1, y1, x2, y2, 'cl')
    for (x, y, s) in ((x1, y1, 1), (x2, y2, -1)):
        svg.ln(x - s * ux * 1, y - s * uy * 1, x + s * ux * 5, y + s * uy * 5, 'corte')
        ax, ay = x - s * ux * 1, y - s * uy * 1
        tx_, ty_ = ax + math.cos(ang_vista) * 5, ay + math.sin(ang_vista) * 5
        svg.ln(ax, ay, tx_, ty_, 'dimf')
        seta(svg, tx_ + math.cos(ang_vista) * 0.6, ty_ + math.sin(ang_vista) * 0.6, ang_vista)
        svg.tx(tx_ + math.cos(ang_vista) * 3.6 - s * ux * 3.2, ty_ + math.sin(ang_vista) * 3.6 + 1.8 - s * uy * 3.2,
               letra, T_TIT, peso=700)


def rotulo(svg, x, y, titulo, escala=None, sub=None, a='middle'):
    """Identificação da vista: título (5,0) sublinhado e, abaixo, escala e observação (3,6)."""
    svg.tx(x, y, titulo, T_TIT, peso=700, c='tx rot', a=a)
    w = _larg_txt(titulo, T_TIT) * 1.02
    x0 = x - w / 2 if a == 'middle' else (x if a == 'start' else x - w)
    svg.ln(x0, y + 1.4, x0 + w, y + 1.4, 'rotl')
    lin = []
    if escala:
        lin.append('SEM ESCALA' if escala.startswith('sem') else f'ESCALA {escala}')
    if sub:
        lin.append(sub)
    for i, l in enumerate(lin):
        svg.tx(x, y + 6.2 + i * 4.8, l, T, c='tx sec', a=a)


# =============================================================== folha/carimbo
def moldura(svg, meta):
    x0, y0, x1, y1 = MOLDURA
    svg.rect(0.0, 0.0, A3[0], A3[1], 'papel')
    svg.rect(x0, y0, x1, y1, 'moldura')
    # zonas: 8 colunas × 6 linhas
    ncol, nlin = 8, 6
    for i in range(ncol + 1):
        x = x0 + (x1 - x0) * i / ncol
        svg.ln(x, y0, x, y0 - 3, 'zona')
        svg.ln(x, y1, x, y1 + 3, 'zona')
        if i < ncol:
            xm = x + (x1 - x0) / ncol / 2
            svg.tx(xm, y0 - 2.0, str(i + 1), 3.0, c='tx sec')
            svg.tx(xm, y1 + 5.0, str(i + 1), 3.0, c='tx sec')
    for i in range(nlin + 1):
        y = y0 + (y1 - y0) * i / nlin
        svg.ln(x0, y, x0 - 3, y, 'zona')
        svg.ln(x1, y, x1 + 3, y, 'zona')
        if i < nlin:
            ym = y + (y1 - y0) / nlin / 2 + 0.8
            svg.tx(x0 - 5.5, ym + 0.4, 'ABCDEF'[i], 3.0, c='tx sec')
            svg.tx(x1 + 3.5, ym + 0.4, 'ABCDEF'[i], 3.0, c='tx sec')
    # marca de centro
    for (xa, ya, xb, yb) in ((A3[0] / 2, 0, A3[0] / 2, y0), (A3[0] / 2, y1, A3[0] / 2, A3[1]),
                             (0, A3[1] / 2, x0, A3[1] / 2), (x1, A3[1] / 2, A3[0], A3[1] / 2)):
        svg.ln(xa, ya, xb, yb, 'moldura')
    # selo de status
    # selo de status: faixa única no topo, à direita (conteúdo das folhas começa em Y ≥ 20)
    sx1, sy0 = x1 - 3, y0 + 2
    w = 131
    svg.rect(sx1 - w, sy0, sx1, sy0 + 8, 'selo')
    # O texto do selo vem do metadado, e não fixo no código: uma liberação para
    # fabricação é ato de pessoa, com nome e CREA, e tem de poder ser escrita — mas
    # só por quem a assina. O padrão continua sendo o não liberado, para que
    # esquecer de informar nunca produza um desenho liberado por omissão.
    svg.tx(sx1 - w / 2, sy0 + 5.5,
           meta.get('selo', 'EMITIDO PARA COTAÇÃO E VALIDAÇÃO · NÃO LIBERADO PARA FABRICAÇÃO'),
           T, peso=700, c='tx selotx')
    carimbo(svg, meta)


def simbolo_1diedro(svg, x, y, s=1.0):
    """Símbolo de projeção do 1º diedro (ISO 5456-2): tronco de cone + vista das bases à direita."""
    h1, h2, L = 2.2 * s, 4.4 * s, 6.0 * s
    svg.pl([(x, y - h1), (x + L, y - h2), (x + L, y + h2), (x, y + h1)], 'vism', fechar=True)
    linha_centro(svg, x - 1.2, y, x + L + 13 * s, y)
    cx = x + L + 7 * s
    svg.circ(cx, y, h2, 'vism')
    svg.circ(cx, y, h1, 'vism')
    linha_centro(svg, cx, y - h2 - 1.2, cx, y + h2 + 1.2)


def carimbo(svg, m):
    x0, y0, x1, y1 = CARIMBO
    r0 = y0 + 7
    r1, r2, r3 = r0 + 14, r0 + 25, r0 + 35
    svg.rect(x0, y0, x1, y1, 'carimbo')

    def cel(xa, ya, xb, yb, rotulo_, valor, t=T, peso=600, a='start'):
        svg.rect(xa, ya, xb, yb, 'celula')
        svg.tx(xa + 1.2, ya + 2.9, rotulo_, T_LEG, a='start', c='tx sec')
        if a == 'start':
            svg.tx(xa + 1.2, yb - 1.9, valor, t, a='start', peso=peso)
        else:
            svg.tx((xa + xb) / 2, yb - 1.9, valor, t, peso=peso)
    # faixa de revisão
    for (xa, xb) in ((x0, x0 + 12), (x0 + 12, x0 + 124), (x0 + 124, x0 + 146), (x0 + 146, x1)):
        svg.rect(xa, y0, xb, r0, 'celula')
    svg.tx(x0 + 1.0, y0 + 4.9, 'REV.', T_LEG, a='start', c='tx sec')
    svg.tx(x0 + 9.4, y0 + 5.2, m.get('rev', '0'), T, a='middle', peso=700)
    rev_desc = m.get('rev_desc', 'Emissão inicial — cotação e validação')
    # a célula tem 112 mm e a letra de 3,2 mm ocupa ~1,6 mm por caractere. Estourar a célula
    # passa por cima da data e do nome — e sai assim em TODAS as folhas, em silêncio.
    if len(rev_desc) * 1.6 > 108:
        raise ValueError(f'descrição da revisão longa demais para a célula do carimbo '
                         f'({len(rev_desc)} caracteres, máx. 67): {rev_desc!r}')
    svg.tx(x0 + 13.2, y0 + 5.2, rev_desc, 3.2, a='start')
    svg.tx(x0 + 135, y0 + 5.2, m.get('data', '19/09/2026'), 3.2)
    svg.tx(x0 + 147.2, y0 + 5.2, 'ValTexa Eng.', 3.2, a='start')
    # linha 1: marca + título
    svg.rect(x0, r0, x0 + 46, r1, 'celula')
    marca(svg, x0 + 2.6, r0 + 2.0, 0.86)
    svg.tx(x0 + 3.0, r0 + 12.3, 'ROVER V4 · ENGENHARIA', T_LEG, a='start', c='tx sec')
    svg.rect(x0 + 46, r0, x1, r1, 'celula')
    svg.tx(x0 + 48, r0 + 6.2, m['titulo'], T_TIT, a='start', peso=700)
    svg.tx(x0 + 48, r0 + 11.6, m.get('subtitulo', ''), 3.2, a='start', c='tx sec')
    # linha 2
    cel(x0, r1, x0 + 50, r2, 'Nº DO DOCUMENTO', m['numero'])
    cel(x0 + 50, r1, x0 + 72, r2, 'FOLHA', m['folha'], a='mid')
    cel(x0 + 72, r1, x0 + 98, r2, 'ESCALA', m.get('escala', '—'), a='mid')
    svg.rect(x0 + 98, r1, x0 + 130, r2, 'celula')
    svg.tx(x0 + 99.2, r1 + 2.9, '1º DIEDRO', T_LEG, a='start', c='tx sec')
    simbolo_1diedro(svg, x0 + 104, r1 + 7.2, 0.8)
    cel(x0 + 130, r1, x0 + 148, r2, 'UNIDADE', 'mm', a='mid')
    cel(x0 + 148, r1, x1, r2, 'FORMATO', 'A3', a='mid')
    # linha 3
    if len(m.get('material', '—')) * 1.55 > 70:
        raise ValueError(f'material longo demais para a célula do carimbo ({len(m["material"])} caracteres): '
                         f'{m["material"]!r}')
    cel(x0, r2, x0 + 72, r3, 'MATERIAL', m.get('material', '—'), 3.2, peso=500)
    cel(x0 + 72, r2, x0 + 148, r3, 'TOLERÂNCIA GERAL (SALVO INDICAÇÃO)',
        m.get('tolerancia', 'ISO 13920-BF · ISO 2768-mK'), 3.2, peso=500)
    cel(x0 + 148, r2, x1, r3, 'DATA', m.get('data', '19/09/2026'), 3.2, peso=500, a='mid')
    # linha 4: assinaturas
    cel(x0, r3, x0 + 60, y1, 'ELABORADO', 'ValTexa Engenharia', 3.2, peso=500)
    cel(x0 + 60, r3, x0 + 120, y1, 'VERIFICADO · ENG. MECÂNICO / CREA',
        m.get('verificado', ''), 3.2)
    cel(x0 + 120, r3, x1, y1, 'APROVADO PARA FABRICAÇÃO', m.get('aprovado', ''), 3.2)


def marca(svg, x, y, s=1.0):
    """Marca ValTexa desenhada (V em chevron + nome)."""
    svg.raw(f'<g transform="translate({f(x)} {f(y)}) scale({f(s)})">'
            '<path d="M0,0 L2.4,0 L4.6,4.6 L6.8,0 L9.2,0 L4.6,8.2 Z" class="marca"/>'
            '<path d="M5.9,0 L9.2,0 L7.6,2.9 Z" class="marca2"/>'
            '<text x="10.8" y="6.9" font-size="7" class="tx marcatx" font-weight="700" '
            'letter-spacing="0.35">VALTEXA</text></g>')


# ============================================== simbologia (ISO 1101, 1302, 2553)
def _simb_gdt(svg, cx, cy, simb):
    if simb == 'plan':
        svg.pl([(cx - 1.9, cy + 0.9), (cx + 0.9, cy + 0.9), (cx + 1.9, cy - 0.9), (cx - 0.9, cy - 0.9)], 'gdt', True)
    elif simb == 'perp':
        svg.ln(cx - 1.8, cy + 1.3, cx + 1.8, cy + 1.3, 'gdt')
        svg.ln(cx, cy + 1.3, cx, cy - 1.6, 'gdt')
    elif simb == 'par':
        svg.ln(cx - 1.6, cy + 1.3, cx - 0.2, cy - 1.5, 'gdt')
        svg.ln(cx + 0.2, cy + 1.3, cx + 1.6, cy - 1.5, 'gdt')
    elif simb == 'pos':
        svg.circ(cx, cy, 1.15, 'gdt')
        svg.ln(cx - 1.9, cy, cx + 1.9, cy, 'gdt')
        svg.ln(cx, cy - 1.9, cx, cy + 1.9, 'gdt')


def fcf(svg, x, y, simb, tol, datums=(), h=6.0):
    """Quadro de tolerância geométrica (ISO 1101). (x, y) = canto superior esquerdo. Devolve a largura."""
    ws = [h, max(11.0, _larg_txt(tol, T) + 3.5)] + [h] * len(datums)
    X = x
    for k, w in enumerate(ws):
        svg.rect(X, y, X + w, y + h, 'fcf')
        if k == 0:
            _simb_gdt(svg, X + w / 2, y + h / 2, simb)
        elif k == 1:
            svg.tx(X + w / 2, y + h / 2 + 1.25, tol, T)
        else:
            svg.tx(X + w / 2, y + h / 2 + 1.25, datums[k - 2], T, peso=600)
        X += w
    return X - x


def referencia(svg, x, y, letra, ang):
    """Símbolo de referência (datum): triângulo cheio na superfície (x, y), caixa na direção ang."""
    ux, uy = math.cos(ang), math.sin(ang)
    px, py = -uy, ux
    svg.raw(f'<path class="arr" d="M{f(x + px * 1.4)},{f(y + py * 1.4)}L{f(x - px * 1.4)},{f(y - py * 1.4)}'
            f'L{f(x + ux * 2.2)},{f(y + uy * 2.2)}Z"/>')
    ex, ey = x + ux * 6.5, y + uy * 6.5
    svg.ln(x + ux * 2.2, y + uy * 2.2, ex, ey, 'gdt')
    cx, cy = ex + ux * 3.0, ey + uy * 3.0
    svg.rect(cx - 3.0, cy - 3.0, cx + 3.0, cy + 3.0, 'fcf')
    svg.tx(cx, cy + 1.3, letra, T, peso=700)


def rugosidade(svg, x, y, txt='Ra 3,2', ang=0.0):
    """Símbolo de estado de superfície com remoção de material (ISO 1302), vértice em (x, y)."""
    svg.raw(f'<g transform="translate({f(x)} {f(y)}) rotate({f(math.degrees(ang))})">'
            '<path class="gdt" d="M-2.8,-4 L0,0 L6,-9.2 L15,-9.2"/>'
            '<path class="gdt" d="M-2.8,-4 L2.8,-4"/>'
            f'<text x="6.2" y="-10.3" font-size="{T}" class="tx">{txt}</text></g>')


def simbolo_solda(svg, xa, ya, xr, yr, a='a3', contorno=True, cauda=None, comp=26.0):
    """Seta até a junta (xa, ya); linha de referência a partir de (xr, yr) (ISO 2553, sistema A)."""
    seta(svg, xa, ya, math.atan2(ya - yr, xa - xr))
    svg.ln(xr, yr, xa, ya, 'gdt')
    svg.ln(xr, yr, xr + comp, yr, 'gdt')
    svg.ln(xr, yr + 1.3, xr + comp, yr + 1.3, 'hid')
    tx = xr + comp * 0.42
    svg.pl([(tx, yr), (tx, yr - 4.0), (tx + 4.0, yr)], 'gdt', True)
    svg.tx(tx - 1.2, yr - 1.0, a, T, a='end', peso=600)
    if contorno:
        svg.circ(xr, yr, 1.5, 'fcf')
    if cauda:
        svg.pl([(xr + comp, yr), (xr + comp + 3.0, yr - 2.6)], 'gdt')
        svg.pl([(xr + comp, yr), (xr + comp + 3.0, yr + 2.6)], 'gdt')
        svg.tx(xr + comp + 4.2, yr + 1.2, cauda, T, a='start')
