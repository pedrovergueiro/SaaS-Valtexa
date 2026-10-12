"""Geometria paramétrica do chassi estrutural e da gaiola de proteção do VALTEXA Rover V3.

Base: VTX-RV3-BASELINE-E (Rev E, 18/09/2026). Unidades: mm e kg.
Referencial ISO 8855, o mesmo da baseline: origem no solo, no centro do polígono
das 4 rodas; X para a frente, Y para a esquerda, Z para cima.

Tudo o que aparece nos desenhos, nas listas de corte, nas massas e nos DXF sai daqui.
Mudou uma cota? Mude aqui e rode `python gerar.py` de novo.
"""
import math

# ------------------------------------------------------------------ baseline
L_EXT = 1050.0       # comprimento externo            CALC  (envelope externo, com carenagens)
W_EXT = 600.0        # largura externa                CALC  (envelope externo, com carenagens)
ENTRE_EIXOS = 700.0  # entre-eixos                    CRITÉRIO PROPOSTO
BITOLA = 470.0       # bitola                         CALC
D_RODA = 200.0       # diâmetro da roda               FONTE (ElectroCraft)
VAO_LIVRE = 150.0    # vão livre                      CRITÉRIO PROPOSTO / VALIDAÇÃO EXPERIMENTAL
Z_QUADRO = 250.0     # face inferior do quadro        CALC
Z_DECK = 340.0       # topo do quadro (deck)          CALC
Z_PROT = 400.0       # topo da proteção do corpo      CALC  (nada do corpo passa desta cota)
Z_TOTAL = 1782.0     # topo do mastro de sensores     CALC

# ------------------------------------------ MPW86 (datasheet ElectroCraft 011121)
MPW_LARG_RODA = 52.1     # largura da banda da roda                FONTE
MPW_FACE = 105.7         # diâmetro da face de montagem            FONTE
MPW_PCD = 95.0           # círculo de furação                      FONTE
MPW_N_FUROS = 7          # furos M4x0,7-6H passantes, eq. espaçados FONTE
MPW_D_MOTOR = 86.5       # diâmetro máximo do motor                FONTE
MPW_L_MOTOR = 112.5      # comprimento máx. do motor, sem freio/encoder (X61V) FONTE
MPW_FOLGA = 5.0          # face de montagem -> face interna da roda  leitura do desenho, A VALIDAR
MPW_ROSCA_MAX = 5.0      # engajamento máximo do parafuso M4         FONTE

# ============================ catálogo de motores-roda (interface do suporte S) ===
# Campo None = dado não publicado pelo fabricante. Sem ele o suporte não pode ser desenhado.
MOTORES = {
    'MPW86': dict(
        nome='ElectroCraft MPW86-185V48-1000-S020',
        d_roda=200.0, larg_roda=52.1, face=105.7, pcd=95.0, n_furos=7, d_furo=4.5,
        d_motor=86.5, l_motor=112.5, folga=5.0, rosca_max=5.0,
        massa=4.5, torque_cont=20.0, torque_pico=35.0, carga_roda=227.0, rpm=None,
        freio='De fábrica, aplicado por mola — torque não publicado (RFQ)',
        preco_brl=6425.00, origem='FONTE · datasheet 011121',
        interface='Flange: 7 furos M4×0,7 no PCD 95, face Ø105,7'),
    'ZLTECH': dict(
        nome='ZLTECH ZLLG80ASM800 V1.0 (Shenzhen Zhongling)',
        d_roda=200.0, larg_roda=None, face=None, pcd=None, n_furos=None, d_furo=None,
        d_motor=None, l_motor=None, folga=None, rosca_max=None,
        massa=8.5, torque_cont=20.0, torque_pico=60.0, carga_roda=150.0, rpm=150.0,
        rpm_max=180.0, corrente=8.5, corrente_max=25.0, potencia=800.0, eficiencia=0.80,
        freio='Eletromagnético (EMB) — opcional de fábrica, pedir na cotação',
        preco_brl=1133.68, preco_200=1028.22, garantia='3 meses a 1 ano',
        ip='IP65 no título e IP54 na tabela da mesma página — confirmar',
        origem='PESQUISA · página do fabricante no Alibaba, 21/09/2026',
        montagem='Montagem por eixo (single shaft / dual shaft), fixado por porca',
        interface='Diâmetro, comprimento e rosca do eixo NÃO publicados'),
}
MOTOR = 'MPW86'          # motor cuja interface está desenhada no caderno


def motor(qual=None):
    return MOTORES[qual or MOTOR]


def faltam_do_motor(qual):
    """Campos de interface que o fabricante não publicou — impedem desenhar o suporte."""
    m = MOTORES[qual]
    rotulos = {'larg_roda': 'largura da roda', 'face': 'diâmetro da face de montagem',
               'pcd': 'círculo de furação (PCD)', 'n_furos': 'número de furos',
               'd_furo': 'diâmetro/rosca dos furos', 'd_motor': 'diâmetro do corpo do motor',
               'l_motor': 'comprimento do motor', 'folga': 'folga face de montagem → roda',
               'rosca_max': 'engajamento máximo do parafuso'}
    return [v for k, v in rotulos.items() if m.get(k) is None]


# ------------------------------------------------------ escolhas deste caderno
TQ, EQ = 30.0, 2.0       # tubo do quadro 30x30x2 (baseline)
TG, EG = 20.0, 1.5       # tubo da gaiola 20x20x1,5 (topologia do CAD Rev B)
E_CAREN = 2.0            # carenagens laterais, frontal e traseira (por fora do quadro)
E_TAMPA = 1.2            # tampas superiores
E_CHAPA = 2.0            # chapa de fundo
E_SAPATA = 3.0

# Envelope externo = quadro + carenagens: 1046 + 2 × 2 = 1050 e 596 + 2 × 2 = 600 (baseline).
L_Q = L_EXT - 2 * E_CAREN            # 1046 — comprimento do quadro
W_Q = W_EXT - 2 * E_CAREN            # 596  — largura do quadro
XQ, YQ = L_Q / 2, W_Q / 2            # 523, 298 — faces externas do quadro
Y_LONG = (YQ - TQ, YQ)               # 268..298 — longarinas
Y_C = YQ - TQ / 2                    # 283 — linha de centro das longarinas
X_CANTO = XQ - TQ / 2                # 508 — linha de centro das travessas de extremidade
ANEL_INF = (Z_QUADRO, Z_QUADRO + TQ)  # 250..280
ANEL_SUP = (Z_DECK - TQ, Z_DECK)      # 310..340
XS = ENTRE_EIXOS / 2                 # 350 — estação das rodas

# Gaiola: anel superior termina 3 mm abaixo de Z_PROT; tampas (1,2) e faixa central (1,2) ficam ≤ 400.
Z_G2 = 397.0                         # topo do anel da gaiola
Z_G1 = Z_G2 - TG                     # 377 — face inferior do anel
Z_G0 = Z_DECK + E_SAPATA             # 343 — pé dos montantes
Z_TAMPA = Z_G2 + E_TAMPA             # 398,2 — face superior das tampas
Z_FAIXA = Z_TAMPA + E_TAMPA          # 399,4 — face superior da faixa central (ponto mais alto do corpo)
YG = (YQ - TG, YQ)                   # 278..298 — trilhos laterais da gaiola
YG_C = YQ - TG / 2                   # 288
X_MOD = 30.0                         # meia-folga livre entre os módulos (zona do mastro)

# Suporte do motor-roda
Y_FACE = 204.0           # face de montagem do MPW86 (|Y|); 235 − 26,05 − 5 = 203,95 → 204 (bitola 470,1)
Z_EIXO = D_RODA / 2      # centro da roda
E_FLANGE = 6.0           # chapa superior do suporte
E_PLACA = 10.0           # chapa de montagem (bruta; face usinada, final ≥ 9,5)
E_NERV_S = 8.0           # nervuras do suporte
R_PLACA = 62.0           # raio inferior da chapa de montagem
D_BORE = 88.0            # furo central (passa o motor Ø86,5 máx.)

# Chapas que assentam sobre porca-rebite levam furo de folga para a cabeça dela; a arruela
# larga ISO 7093 aperta a chapa direto contra o tubo.
D_FOLGA_M6 = 13.0        # cabeça reduzida da porca-rebite M6 (Ø ≤ 12)
D_FOLGA_M5 = 11.0        # cabeça reduzida da porca-rebite M5 (Ø ≤ 10)

RHO = {'6061': 2.70e-6, '5052': 2.68e-6, 'borracha': 1.15e-6, 'inox': 7.95e-6,
       'uhmw': 0.95e-6, 'pc': 1.20e-6}

AXI = {'x': 0, 'y': 1, 'z': 2}
PLANO = {'x': ('y', 'z'), 'y': ('x', 'z'), 'z': ('x', 'y')}


# ================================================================ primitivas
def area_poly(pts):
    s = 0.0
    for i in range(len(pts)):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % len(pts)]
        s += x1 * y2 - x2 * y1
    return s / 2


def centro_poly(pts):
    a = area_poly(pts)
    if abs(a) < 1e-9:
        return (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))
    cx = cy = 0.0
    for i in range(len(pts)):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % len(pts)]
        c = x1 * y2 - x2 * y1
        cx += (x1 + x2) * c
        cy += (y1 + y2) * c
    return (cx / (6 * a), cy / (6 * a))


def circulo(cx, cy, d, n=64):
    r = d / 2
    return [(cx + r * math.cos(2 * math.pi * i / n), cy + r * math.sin(2 * math.pi * i / n)) for i in range(n)]


def retangulo(a0, a1, b0, b1):
    return [(a0, b0), (a1, b0), (a1, b1), (a0, b1)]


def ret_arred(a0, a1, b0, b1, r, n=8):
    """Retângulo com os quatro cantos arredondados (raio r)."""
    if r <= 0:
        return retangulo(a0, a1, b0, b1)
    pts = []
    for (cx, cy, ang0) in ((a1 - r, b0 + r, -90), (a1 - r, b1 - r, 0), (a0 + r, b1 - r, 90), (a0 + r, b0 + r, 180)):
        for i in range(n + 1):
            t = math.radians(ang0 + 90 * i / n)
            pts.append((cx + r * math.cos(t), cy + r * math.sin(t)))
    return pts


class Prisma:
    """Perfil 2D (com furos) extrudado ao longo de um eixo do mundo.

    Serve para tudo: tubos (perfil quadrado com furo quadrado), chapas, nervuras,
    rodas de referência (círculo). `circulos` guarda os furos redondos para cotagem.
    """

    def __init__(self, item, eixo, e0, e1, perfil, furos=(), mat='6061', estilo='solid',
                 circulos=(), curvo=False, grupo=None):
        self.item = item
        self.eixo = eixo
        self.e0, self.e1 = min(e0, e1), max(e0, e1)
        self.perfil = [tuple(p) for p in perfil]
        self.furos = [[tuple(p) for p in f] for f in furos]
        self.mat = mat
        self.estilo = estilo          # solid | ctx (contexto) | ref (não fornecido)
        self.circulos = list(circulos)  # (a, b, d) no plano do perfil
        self.curvo = curvo
        self.grupo = grupo or item.split('-')[0]
        self.desloc = (0.0, 0.0, 0.0)

    # ---- coordenadas
    def mundo(self, a, b, e):
        pa, pb = PLANO[self.eixo]
        p = [0.0, 0.0, 0.0]
        p[AXI[pa]] = a
        p[AXI[pb]] = b
        p[AXI[self.eixo]] = e
        return (p[0] + self.desloc[0], p[1] + self.desloc[1], p[2] + self.desloc[2])

    def bbox(self):
        pa, pb = PLANO[self.eixo]
        r = [None, None, None]
        r[AXI[pa]] = (min(p[0] for p in self.perfil), max(p[0] for p in self.perfil))
        r[AXI[pb]] = (min(p[1] for p in self.perfil), max(p[1] for p in self.perfil))
        r[AXI[self.eixo]] = (self.e0, self.e1)
        return [(lo + self.desloc[i], hi + self.desloc[i]) for i, (lo, hi) in enumerate(r)]

    def centro(self):
        (x0, x1), (y0, y1), (z0, z1) = self.bbox()
        return ((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2)

    def centroide(self):
        """Centroide real (considera os furos) — usado no cálculo de CG."""
        a_out = abs(area_poly(self.perfil))
        ca = centro_poly(self.perfil)
        sa, sx, sy = a_out, ca[0] * a_out, ca[1] * a_out
        for f in self.furos:
            af = abs(area_poly(f))
            cf = centro_poly(f)
            sa -= af
            sx -= cf[0] * af
            sy -= cf[1] * af
        return self.mundo(sx / sa, sy / sa, (self.e0 + self.e1) / 2)

    def area(self):
        return abs(area_poly(self.perfil)) - sum(abs(area_poly(f)) for f in self.furos)

    def comprimento(self):
        return self.e1 - self.e0

    def volume(self):
        return self.area() * self.comprimento()

    def massa(self):
        return self.volume() * RHO.get(self.mat, 0)

    def movido(self, dx=0.0, dy=0.0, dz=0.0):
        c = Prisma(self.item, self.eixo, self.e0, self.e1, self.perfil, self.furos, self.mat,
                   self.estilo, self.circulos, self.curvo, self.grupo)
        c.desloc = (self.desloc[0] + dx, self.desloc[1] + dy, self.desloc[2] + dz)
        return c

    def como(self, estilo):
        c = self.movido()
        c.estilo = estilo
        return c

    # ---- corte por plano perpendicular a um eixo do mundo
    def recortado(self, eixo, pos, manter):
        """Parte do prisma do lado `manter` ('ge' ou 'le') do plano eixo=pos."""
        pos_l = pos - self.desloc[AXI[eixo]]
        if eixo == self.eixo:
            e0, e1 = self.e0, self.e1
            if manter == 'ge':
                e0 = max(e0, pos_l)
            else:
                e1 = min(e1, pos_l)
            if e1 - e0 <= 1e-6:
                return None
            c = self.movido()
            c.e0, c.e1 = e0, e1
            return c
        pa, pb = PLANO[self.eixo]
        k = 0 if eixo == pa else 1
        fora = _clip(self.perfil, k, pos_l, manter)
        if len(fora) < 3 or abs(area_poly(fora)) < 1e-6:
            return None
        furos = []
        for f in self.furos:
            cf = _clip(f, k, pos_l, manter)
            if len(cf) >= 3 and abs(area_poly(cf)) > 1e-6:
                furos.append(cf)
        c = self.movido()
        c.perfil, c.furos = fora, furos
        c.circulos = [ci for ci in self.circulos
                      if (ci[k] >= pos_l if manter == 'ge' else ci[k] <= pos_l)]
        return c

    def secao(self, eixo, pos):
        """Regiões cortadas pelo plano eixo=pos, como anéis de pontos do mundo."""
        pos_l = pos - self.desloc[AXI[eixo]]
        if eixo == self.eixo:
            if not (self.e0 < pos_l < self.e1):
                return []
            return [[[self.mundo(a, b, pos_l) for a, b in anel] for anel in [self.perfil] + self.furos]]
        pa, pb = PLANO[self.eixo]
        k = 0 if eixo == pa else 1
        ts = []
        for anel in [self.perfil] + self.furos:
            for i in range(len(anel)):
                p, q = anel[i], anel[(i + 1) % len(anel)]
                if (p[k] - pos_l) * (q[k] - pos_l) < 0:
                    t = (pos_l - p[k]) / (q[k] - p[k])
                    ts.append(p[1 - k] + t * (q[1 - k] - p[1 - k]))
        ts.sort()
        regs = []
        for i in range(0, len(ts) - 1, 2):
            o0, o1 = ts[i], ts[i + 1]
            if o1 - o0 < 1e-6:
                continue
            pts2 = []
            for (o, e) in ((o0, self.e0), (o1, self.e0), (o1, self.e1), (o0, self.e1)):
                ab = [0, 0]
                ab[k] = pos_l
                ab[1 - k] = o
                pts2.append(self.mundo(ab[0], ab[1], e))
            regs.append([pts2])
        return regs


def _clip(poly, k, pos, manter):
    """Sutherland-Hodgman contra o semiplano coord[k] >= pos (ou <=)."""
    def dentro(p):
        return p[k] >= pos - 1e-9 if manter == 'ge' else p[k] <= pos + 1e-9
    out = []
    n = len(poly)
    for i in range(n):
        p, q = poly[i], poly[(i + 1) % n]
        ip, iq = dentro(p), dentro(q)
        if ip:
            out.append(p)
        if ip != iq:
            t = (pos - p[k]) / (q[k] - p[k])
            out.append((p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1])))
    return out


def tubo(item, eixo, e0, e1, a0, a1, b0, b1, parede, mat='6061', estilo='solid'):
    return Prisma(item, eixo, e0, e1, retangulo(a0, a1, b0, b1),
                  [retangulo(a0 + parede, a1 - parede, b0 + parede, b1 - parede)], mat, estilo)


def chapa(item, eixo, e0, e1, perfil, furos_circ=(), mat='6061', estilo='solid', furos_poly=()):
    """furos_circ: [(a, b, d)] no plano do perfil."""
    furos = [circulo(a, b, d, 32 if d < 20 else 64) for (a, b, d) in furos_circ] + list(furos_poly)
    return Prisma(item, eixo, e0, e1, perfil, furos, mat, estilo, circulos=list(furos_circ))


def cilindro(item, eixo, e0, e1, ca, cb, d, furo=None, mat='6061', estilo='ref'):
    furos = [circulo(ca, cb, furo, 48)] if furo else []
    circs = [(ca, cb, d)] + ([(ca, cb, furo)] if furo else [])
    return Prisma(item, eixo, e0, e1, circulo(ca, cb, d, 72), furos, mat, estilo, circs, curvo=True)


def espelha_y(p):
    """Espelha um prisma em Y (lado direito a partir do esquerdo)."""
    if p.eixo == 'y':
        c = Prisma(p.item, 'y', -p.e1, -p.e0, p.perfil, p.furos, p.mat, p.estilo, p.circulos, p.curvo, p.grupo)
    else:
        k = 0 if PLANO[p.eixo][0] == 'y' else 1

        def m(pts):
            r = [(q[0], -q[1]) if k == 1 else (-q[0], q[1]) for q in pts]
            return r[::-1]
        circs = [((-c[0], c[1], c[2]) if k == 0 else (c[0], -c[1], c[2])) for c in p.circulos]
        c = Prisma(p.item, p.eixo, p.e0, p.e1, m(p.perfil), [m(f) for f in p.furos], p.mat, p.estilo,
                   circs, p.curvo, p.grupo)
    c.desloc = p.desloc
    return c


def _n(v):
    """Número para descrições: 1046, 1,5."""
    return str(int(round(v))) if abs(v - round(v)) < 1e-6 else f'{v:.1f}'.replace('.', ',')


# ============================================================ quadro (Q)
X_MONTANTES = (-X_CANTO, -XS, -XS / 2, 0.0, XS / 2, XS, X_CANTO)   # −508 … 508
E_TAMPA_Q = 2.0
# furos de fixação dos suportes do motor-roda (por estação): (dx, |y|)
FUROS_SUPORTE = ((-45.0, Y_C), (45.0, Y_C), (0.0, 240.0), (0.0, 130.0))


def quadro():
    ps = []
    xl = XQ - E_TAMPA_Q
    yi = YQ - TQ
    for (z0, z1) in (ANEL_INF, ANEL_SUP):
        for s in (1, -1):
            y0, y1 = sorted((s * Y_LONG[0], s * Y_LONG[1]))
            ps.append(tubo('Q-01', 'x', -xl, xl, y0, y1, z0, z1, EQ))
            for sx in (1, -1):
                x0, x1 = sorted((sx * xl, sx * XQ))
                ps.append(chapa('Q-06', 'x', x0, x1, retangulo(y0, y1, z0, z1)))
        for sx in (1, -1):
            x0, x1 = sorted((sx * (XQ - TQ), sx * XQ))
            ps.append(tubo('Q-02', 'y', -yi, yi, x0, x1, z0, z1, EQ))
            x0, x1 = sorted((sx * (XS - TQ / 2), sx * (XS + TQ / 2)))
            ps.append(tubo('Q-03', 'y', -yi, yi, x0, x1, z0, z1, EQ))
    for xc in X_MONTANTES:
        for s in (1, -1):
            y0, y1 = sorted((s * Y_LONG[0], s * Y_LONG[1]))
            ps.append(tubo('Q-04', 'z', ANEL_INF[1], ANEL_SUP[0], xc - TQ / 2, xc + TQ / 2, y0, y1, EQ))
    for xc in (-X_CANTO, X_CANTO):
        ps.append(tubo('Q-04', 'z', ANEL_INF[1], ANEL_SUP[0], xc - TQ / 2, xc + TQ / 2, -TQ / 2, TQ / 2, EQ))
    for sx in (1, -1):
        for s in (1, -1):
            for (dx, ay) in FUROS_SUPORTE:
                ps.append(cilindro('Q-05', 'z', ANEL_INF[0], ANEL_INF[1], sx * XS + dx, s * ay, 12.0, furo=8.5,
                                   estilo='oculto'))
    return ps


# ================================================== chapa de fundo e nervuras (C)
X_NERV = 120.0


def furos_chapa():
    """Lista (x, y, d, função) de todos os furos da chapa de fundo."""
    f = []
    for s in (1, -1):
        for x in (-X_CANTO, -200.0, -100.0, 0.0, 100.0, 200.0, X_CANTO):
            f.append((x, s * Y_C, D_FOLGA_M6, 'M6 → porca-rebite no anel inferior'))
    for sx in (1, -1):
        for y in (-100.0, 100.0):
            f.append((sx * X_CANTO, y, D_FOLGA_M6, 'M6 → porca-rebite no anel inferior'))
        f.append((sx * XS, 0.0, D_FOLGA_M6, 'M6 → porca-rebite no anel inferior'))
        for s in (1, -1):
            f.append((sx * X_NERV, s * Y_C, D_FOLGA_M6, 'M6 → fixação da nervura (porca-rebite)'))
    for sx in (1, -1):
        for s in (1, -1):
            for (dx, ay) in FUROS_SUPORTE:
                f.append((sx * XS + dx, s * ay, 8.5, 'M8 → suporte do motor-roda'))
    for sx in (1, -1):
        for y in (-225.0, -135.0, -45.0, 45.0, 135.0, 225.0):
            f.append((sx * X_NERV, y, 4.9, 'rebite Ø4,8 → nervura'))
    for x in (-430.0, -250.0, 250.0, 430.0):
        for y in (-200.0, 200.0):
            f.append((x, y, 10.0, 'dreno'))
    for sx in (1, -1):
        for s in (1, -1):
            f.append((sx * 300.0, s * 80.0, 32.0, 'passa-cabo do motor (grommet)'))
    for (x, y) in MALHA_MONTAGEM:
        f.append((x, y, 9.0, 'malha de montagem (porca-rebite M6 na chapa)'))
    for x in (JANELA_RAIZ[0] - 13, (JANELA_RAIZ[0] + JANELA_RAIZ[1]) / 2, JANELA_RAIZ[1] + 13):
        for y in (-72.0, 72.0):
            f.append((x, y, 6.5, 'M4 → janela da câmera de raiz (porca-rebite)'))
    return f


# Pontos de fixação para berço da bateria, bandejas de eletrônica e futuros suportes.
MALHA_MONTAGEM = ([(sx * 245.0, s * 40.0) for sx in (1, -1) for s in (1, -1)]        # batentes X da bateria
                  + [(sx * 40.0, s * 185.0) for sx in (1, -1) for s in (1, -1)]      # batentes Y da bateria
                  + [(sx * 170.0, s * 240.0) for sx in (1, -1) for s in (1, -1)]     # bandejas laterais
                  + [(sx * 390.0, s * 220.0) for sx in (1, -1) for s in (1, -1)]
                  + [(sx * x, s * 25.0) for sx in (1, -1) for x in (278.0, 322.0) for s in (1, -1)]
                  + [(x, s * 93.0) for x in (400.0, 480.0) for s in (1, -1)])    # bandejas de extremidade


def chapa_fundo():
    ps = [chapa('C-01', 'z', Z_QUADRO - E_CHAPA, Z_QUADRO, retangulo(-XQ, XQ, -YQ, YQ),
                [(x, y, d) for (x, y, d, _) in furos_chapa()], mat='5052',
                furos_poly=[ret_arred(*JANELA_RAIZ, 10)])]
    z_top = Z_QUADRO - E_CHAPA
    for sx in (1, -1):
        a = X_NERV - 20
        perfil = [(a, z_top - 40), (a + 4, z_top - 40), (a + 4, z_top - 4), (a + 40, z_top - 4), (a + 40, z_top),
                  (a, z_top)]
        if sx < 0:
            perfil = [(-p[0], p[1]) for p in perfil][::-1]
        ps.append(Prisma('C-02', 'y', -(YQ - 2), YQ - 2, perfil))
    return ps


# ================================================ suporte do motor-roda (S)
def furos_mpw():
    return [(90 + i * 360 / MPW_N_FUROS) for i in range(MPW_N_FUROS)]


def suporte(xs, lado):
    """Suporte soldado, lado esquerdo (+Y); espelhado quando lado = −1."""
    ps = []
    zf1 = Z_QUADRO - E_CHAPA          # 248: face inferior da chapa de fundo
    zf0 = zf1 - E_FLANGE              # 242
    fl = [(xs + dx, ay, 8.5) for (dx, ay) in FUROS_SUPORTE]
    ps.append(chapa('S-01', 'z', zf0, zf1, retangulo(xs - 70, xs + 70, 110.0, YQ), fl))
    perfil = [(xs + R_PLACA, zf0), (xs - R_PLACA, zf0), (xs - R_PLACA, Z_EIXO)]
    for i in range(1, 32):
        t = math.pi + math.pi * i / 32
        perfil.append((xs + R_PLACA * math.cos(t), Z_EIXO + R_PLACA * math.sin(t)))
    perfil.append((xs + R_PLACA, Z_EIXO))
    furos = [(xs, Z_EIXO, D_BORE)]
    for ang in furos_mpw():
        t = math.radians(ang)
        furos.append((xs + MPW_PCD / 2 * math.cos(t), Z_EIXO + MPW_PCD / 2 * math.sin(t), 4.5))
    p = chapa('S-02', 'y', Y_FACE - E_PLACA, Y_FACE, perfil, furos)
    p.curvo = True
    ps.append(p)
    yi = Y_FACE - E_PLACA
    nerv = [(yi, zf0), (110.0, zf0), (110.0, zf0 - 12), (yi - 30, 150.0), (yi, 150.0)]
    for x0 in (xs - R_PLACA, xs + R_PLACA - E_NERV_S):
        ps.append(Prisma('S-03', 'x', x0, x0 + E_NERV_S, nerv))
    if lado < 0:
        ps = [espelha_y(q) for q in ps]
    return ps


def suportes():
    ps = []
    for xs in (XS, -XS):
        for lado in (1, -1):
            ps += suporte(xs, lado)
    return ps


# ================== suspensão: balancim longitudinal + molas pneumáticas (W)
# DECISÃO DE ENGENHARIA, 11/10/2026: a suspensão do V3 é PNEUMÁTICA, sobre o balancim
# longitudinal já modelado aqui. O dimensionamento, a massa, o efeito no CG e o consumo
# estão em ../revisao-f/suspensao_ar.py; a geometria dos foles e dos seus suportes ainda
# NÃO está desenhada, e por isso este grupo continua fora de `conjunto_a()`.
#
# Um balancim por lado, articulado em ARFAGEM e rígido em ROLAGEM. A articulação em
# rolagem (eixo oscilante, mola macia) derruba o tombamento de 37,7° para 20,1° —
# inaceitável em lavoura de café. A articulação em arfagem mantém o braço lateral de
# 235 mm intacto e ainda garante as quatro rodas no solo, o que elimina a condição de
# margem ZERO do apoio em três rodas.
#
# A restrição de rolagem VALE PARA O AR TAMBÉM, e com mais força: fole é mais macio que
# mola de aço. A arquitetura mantém a rolagem rígida pela barra de equalização de braços
# cruzados (W-08/W-09), que ganha função nova — acoplar os dois lados para que o fole de
# um não afunde sem o outro. Ver `comparacao_rolagem` no módulo citado: com rolagem
# macia o envelope de estabilidade cai de 19,6° para 14,7°.
#
# (A referência anterior a uma "folha 28" apontava para folha inexistente: o caderno
# tem 27. Corrigido na Rev F.)
Z_PIVO = 150.0            # altura do eixo do balancim              CRITÉRIO PROPOSTO
CURSO = 35.0              # curso vertical por roda (± na ponta)    CRITÉRIO PROPOSTO
H_BAL, B_BAL, E_BAL = 60.0, 40.0, 4.0     # balancim: tubo retangular 60×40×4
X_BAL = 330.0             # meio-comprimento do tubo do balancim
Y_BAL = (Y_FACE - E_PLACA - B_BAL, Y_FACE - E_PLACA)      # 154 … 194
Z_BAL = (Z_PIVO - H_BAL / 2, Z_PIVO + H_BAL / 2)          # 120 … 180
D_PIVO = 25.0             # eixo do pivô (h7)                       CRITÉRIO PROPOSTO
D_CUBO, E_CUBO = 48.0, 5.0                # cubo soldado no balancim
E_TORRE, X_TORRE = 8.0, 95.0              # torre do pivô: chapa 8, cabe entre as nervuras C-02
E_BERCO = 6.0                             # chapa de reforço do berço
X_BATENTE = 250.0         # batentes de fim de curso
X_BARRA, Z_BARRA = 220.0, 215.0           # barra de equalização
D_BARRA, E_BARRA = 30.0, 3.0
Y_BARRA = 140.0           # mancais da barra, por dentro dos balancins
X_BIELA = 110.0           # avanço dos braços da barra (cruzados: +X num lado, −X no outro)
E_BRACO = 8.0


def giro_max():
    """Giro do balancim no batente, em graus."""
    return math.degrees(math.atan(CURSO / XS))


def flange_motor(xs):
    """Perfil da flange W-02 (plano X–Z): interface do MPW86 na ponta do balancim."""
    perfil = [(xs + R_PLACA, Z_BAL[1]), (xs - R_PLACA, Z_BAL[1]), (xs - R_PLACA, Z_EIXO)]
    for i in range(1, 32):
        t = math.pi + math.pi * i / 32
        perfil.append((xs + R_PLACA * math.cos(t), Z_EIXO + R_PLACA * math.sin(t)))
    perfil.append((xs + R_PLACA, Z_EIXO))
    furos = [(xs, Z_EIXO, D_BORE)]
    for ang in furos_mpw():
        t = math.radians(ang)
        furos.append((xs + MPW_PCD / 2 * math.cos(t), Z_EIXO + MPW_PCD / 2 * math.sin(t), 4.5))
    return perfil, furos


def balancim(lado):
    """Balancim de um lado (+Y); espelhado quando lado = −1."""
    ps = []
    yb0, yb1 = Y_BAL
    zb0, zb1 = Z_BAL
    # W-01 — viga do balancim
    ps.append(tubo('W-01', 'x', -X_BAL, X_BAL, yb0, yb1, zb0, zb1, E_BAL))
    # W-06 — cubo do pivô, soldado atravessando a viga
    ps.append(cilindro('W-06', 'y', yb0 - E_CUBO, yb1 + E_CUBO, 0.0, Z_PIVO, D_CUBO,
                       furo=D_PIVO + 1.0, estilo='solid'))
    for xs in (XS, -XS):
        # W-02 — flange de montagem do motor-roda
        perfil, furos = flange_motor(xs)
        p = chapa('W-02', 'y', Y_FACE - E_PLACA, Y_FACE, perfil, furos)
        p.curvo = True
        ps.append(p)
        # W-03 — chapa de fechamento da ponta (gusset de torção sobre o tubo)
        x0 = xs - R_PLACA if xs > 0 else xs - R_PLACA
        ps.append(chapa('W-03', 'z', zb1, zb1 + E_BERCO,
                        retangulo(min(xs - R_PLACA, xs + R_PLACA), max(xs - R_PLACA, xs + R_PLACA),
                                  yb0, Y_FACE)))
    if lado < 0:
        ps = [espelha_y(q) for q in ps]
    for q in ps:
        q.grupo = 'W'
    return ps


def torre_pivo(lado):
    """Torre W-04 e berço W-05: ligam o pivô do balancim ao chassi."""
    ps = []
    zf = Z_QUADRO - E_CHAPA                       # 248 — face inferior da chapa de fundo
    perfil = [(-X_TORRE, zf), (X_TORRE, zf), (40.0, Z_BAL[0]), (-40.0, Z_BAL[0])]
    furos = [(0.0, Z_PIVO, D_PIVO)] + [(sx * 70.0, zf - 12.0, D_FOLGA_M6) for sx in (1, -1)]
    for y0 in (Y_BAL[0] - 2 - E_TORRE, Y_BAL[1] + 2):
        ps.append(chapa('W-04', 'y', y0, y0 + E_TORRE, perfil, furos))
    # W-05 — chapa de reforço do berço, entre as nervuras C-02
    fb = [(sx * 70.0, sy, D_FOLGA_M6) for sx in (1, -1) for sy in (Y_BAL[0] - 14, Y_BAL[1] + 14)]
    fb += [(sx * X_BATENTE, (Y_BAL[0] + Y_BAL[1]) / 2, D_FOLGA_M6) for sx in (1, -1)]
    ps.append(chapa('W-05', 'z', zf - E_BERCO, zf,
                    retangulo(-X_TORRE, X_TORRE, Y_BAL[0] - 22, Y_BAL[1] + 22), fb))
    # W-07 — batentes de fim de curso, acima e abaixo da viga
    yc = (Y_BAL[0] + Y_BAL[1]) / 2
    for sx in (1, -1):
        ps.append(cilindro('W-07', 'z', Z_BAL[1] + CURSO * X_BATENTE / XS, zf - E_BERCO,
                           sx * X_BATENTE, yc, 40.0, mat='borracha', estilo='solid'))
    if lado < 0:
        ps = [espelha_y(q) for q in ps]
    for q in ps:
        q.grupo = 'W'
    return ps


def barra_equalizacao():
    """W-08/W-09: barra de torção com braços CRUZADOS — trava a arfagem, libera a torção.

    Braço do lado +Y aponta para +X e braço do lado −Y aponta para −X. Assim os dois
    balancins girando no mesmo sentido (arfagem) torcem a barra, e girando em sentidos
    opostos (torção do terreno) apenas a fazem rodar nos mancais, sem resistência.
    """
    ps = [cilindro('W-08', 'y', -Y_BARRA, Y_BARRA, X_BARRA, Z_BARRA, D_BARRA,
                   furo=D_BARRA - 2 * E_BARRA, estilo='solid')]
    for lado in (1, -1):
        y0 = lado * (Y_BARRA - E_BRACO) if lado > 0 else lado * Y_BARRA
        xa, xb = sorted((X_BARRA, X_BARRA + lado * X_BIELA))
        perfil = [(X_BARRA - 22, Z_BARRA + 22), (X_BARRA + lado * X_BIELA - 14 * lado, Z_BAL[1] + 26),
                  (X_BARRA + lado * X_BIELA + 14 * lado, Z_BAL[1] + 26), (X_BARRA + 22, Z_BARRA - 22)]
        ps.append(chapa('W-09', 'y', min(y0, y0 + E_BRACO), max(y0, y0 + E_BRACO), perfil,
                        [(X_BARRA + lado * X_BIELA, Z_BAL[1] + 26, 8.5)]))
    for q in ps:
        q.grupo = 'W'
    return ps


def suspensao():
    ps = []
    for lado in (1, -1):
        ps += balancim(lado) + torre_pivo(lado)
    return ps + barra_equalizacao()

def mpw86_ref(xs, lado):
    """MPW86 em linha fantasma (não faz parte do fornecimento)."""
    yc = BITOLA / 2
    ps = [
        cilindro('R-01', 'y', yc - MPW_LARG_RODA / 2, yc + MPW_LARG_RODA / 2, xs, Z_EIXO, D_RODA),
        cilindro('R-01', 'y', Y_FACE, Y_FACE + MPW_FOLGA, xs, Z_EIXO, MPW_FACE),
        cilindro('R-01', 'y', Y_FACE - MPW_L_MOTOR, Y_FACE, xs, Z_EIXO, MPW_D_MOTOR),
    ]
    if lado < 0:
        ps = [espelha_y(q) for q in ps]
    for q in ps:
        q.grupo = 'R'
    return ps


def rodas():
    ps = []
    for xs in (XS, -XS):
        for lado in (1, -1):
            ps += mpw86_ref(xs, lado)
    return ps


# ======================================================= gaiola (G)
# Os dois módulos são a MESMA peça soldada: o traseiro é o dianteiro girado 180° em torno de Z.
X_POSTES = ((XQ - TG, XQ), (X_MOD, X_MOD + TG), (270.0, 290.0))    # (503..523) (30..50) (270..290)
X_BARRAS = ((220.0, 240.0), (320.0, 340.0))                       # barras G-03 (centros 230 e 330)
SAPATAS = {  # montante -> (x0, x1, furos x)
    (XQ - TG, XQ): (XQ - 70, XQ, (XQ - 58, XQ - 35)),              # 453..523 · 465, 488
    (X_MOD, X_MOD + TG): (X_MOD, X_MOD + 70, (62.0, 88.0)),         # 30..100
    (270.0, 290.0): (245.0, 315.0, (257.0, 303.0)),
}
X_LIDAR = 280.0


def gaiola():
    ps = []
    yo, yi = YG[1], YG[0]
    for f in (1, -1):
        def X(a, b):
            return tuple(sorted((f * a, f * b)))
        for s in (1, -1):
            y0, y1 = sorted((s * yi, s * yo))
            x0, x1 = X(X_MOD + EG, XQ - EG)
            ps.append(tubo('G-01', 'x', x0, x1, y0, y1, Z_G1, Z_G2, EG))
            for (a, b) in ((X_MOD, X_MOD + EG), (XQ - EG, XQ)):
                xa, xb = X(a, b)
                ps.append(chapa('G-07', 'x', xa, xb, retangulo(y0, y1, Z_G1, Z_G2)))
        for (a, b) in ((XQ - TG, XQ), (X_MOD, X_MOD + TG)):
            x0, x1 = X(a, b)
            ps.append(tubo('G-02', 'y', -yi, yi, x0, x1, Z_G1, Z_G2, EG))
        for (a, b) in X_BARRAS:
            x0, x1 = X(a, b)
            ps.append(tubo('G-03', 'y', -yi, yi, x0, x1, Z_G1, Z_G2, EG))
        for (a, b) in X_POSTES:
            x0, x1 = X(a, b)
            sa, sb, fx = SAPATAS[(a, b)]
            xs0, xs1 = X(sa, sb)
            for s in (1, -1):
                y0, y1 = sorted((s * yi, s * yo))
                ps.append(tubo('G-04', 'z', Z_G0, Z_G1, x0, x1, y0, y1, EG))
                ys0, ys1 = sorted((s * Y_LONG[0], s * Y_LONG[1]))
                ps.append(chapa('G-05', 'z', Z_DECK, Z_G0, retangulo(xs0, xs1, ys0, ys1),
                                [(f * x, s * Y_C, D_FOLGA_M6) for x in fx]))
    return ps


def suporte_lidar():
    z0 = Z_TAMPA
    furos = [(x, y, 5.5) for x in (230.0, 330.0) for y in (-40.0, 40.0)]
    furos += [(X_LIDAR + dx, dy, 4.5) for dx in (-25.0, 25.0) for dy in (-25.0, 25.0)]
    furos += [(X_LIDAR, 0.0, 30.0)]
    ps = [chapa('G-06', 'z', z0, z0 + 5, retangulo(215.0, 345.0, -55.0, 55.0), furos)]
    for dx in (-25.0, 25.0):
        for dy in (-25.0, 25.0):
            ps.append(cilindro('G-08', 'z', z0 + 5, z0 + 15, X_LIDAR + dx, dy, 15.0, mat='borracha', estilo='solid'))
    return ps


Z_BASE_LIDAR = Z_TAMPA + 5 + 10       # 413,2


def lidar_ref():
    return [cilindro('R-02', 'z', Z_BASE_LIDAR, Z_BASE_LIDAR + 65, X_LIDAR, 0.0, 65.0)]


# ============================================== carenagens e tampas (K)
Z_LINHAS_LAT = (sum(ANEL_INF) / 2, sum(ANEL_SUP) / 2, (Z_G1 + Z_G2) / 2)   # 265, 325, 387
X_FUROS_LAT = (40.0, 150.0, 240.0, 360.0, 450.0)       # carenagem lateral: colunas de porca-rebite (|X|)
X_FUROS_TAMPA_LAT = (95.0, 195.0, 300.0, 405.0, 495.0)  # tampas sobre os trilhos laterais (|X|)
Y_FUROS_TAMPA_FR = (-250.0, -100.0, 100.0, 250.0)       # tampas sobre o trilho transversal da ponta
Y_FUROS_TAMPA_IN = (-230.0, -150.0, 0.0, 150.0, 230.0)  # tampas sobre o trilho transversal interno
Y_FUROS_FR = (-200.0, 0.0, 200.0)                       # carenagens frontal e traseira
JANELA_CAM = (-70.0, 70.0, 344.0, 376.0)                # janela da câmera de navegação (Y, Z)
K06 = (-55.0, 55.0, -256.0, 256.0)                      # faixa central (X, Y) — livre da luva do mastro


def furos_tampa(f):
    """Furos da tampa superior do módulo f (+1 dianteiro, −1 traseiro): (x, y, d)."""
    fu = []
    for x in X_FUROS_TAMPA_LAT:
        for s in (1, -1):
            fu.append((f * x, s * YG_C, D_FOLGA_M5))
    for y in Y_FUROS_TAMPA_FR:
        fu.append((f * (XQ - TG / 2), y, D_FOLGA_M5))
    for y in Y_FUROS_TAMPA_IN:
        fu.append((f * (X_MOD + TG / 2), y, D_FOLGA_M5))
    for (a, b) in X_BARRAS:
        for y in (-200.0, 200.0):
            fu.append((f * (a + b) / 2, y, D_FOLGA_M5))
    if f > 0:
        for x in (230.0, 330.0):
            for y in (-40.0, 40.0):
                fu.append((x, y, D_FOLGA_M5))
        fu.append((X_LIDAR, 0.0, 30.0))
    else:
        for dx in (-45.0, 45.0):
            for dy in (-45.0, 45.0):
                fu.append((X_GNSS + dx, dy, D_FOLGA_M5))
        fu.append((X_GNSS, 0.0, 20.0))
    return fu


def carenagens():
    ps = []
    yo = YQ
    for f in (1, -1):
        x0, x1 = sorted((0.0, f * XQ))
        furos = [(f * x, z, D_FOLGA_M5) for x in X_FUROS_LAT for z in Z_LINHAS_LAT]
        esq = chapa('K-01', 'y', yo, yo + E_CAREN, retangulo(x0, x1, Z_QUADRO, Z_G2), furos, mat='5052')
        ps.append(esq)
        ps.append(espelha_y(esq))
    furos_fr = [(y, z, D_FOLGA_M5) for y in Y_FUROS_FR for z in Z_LINHAS_LAT]
    furos_led = [(sy * Y_LED, Z_LED, D_LED) for sy in (1, -1)]
    jan = ret_arred(JANELA_CAM[0], JANELA_CAM[1], JANELA_CAM[2], JANELA_CAM[3], 5)
    ye = W_EXT / 2
    ps.append(chapa('K-02', 'x', XQ, XQ + E_CAREN, retangulo(-ye, ye, Z_QUADRO, Z_G2), furos_fr + furos_led,
                    mat='5052', furos_poly=[jan]))
    ps.append(chapa('K-03', 'x', -XQ - E_CAREN, -XQ, retangulo(-ye, ye, Z_QUADRO, Z_G2), furos_fr, mat='5052'))
    for f, item in ((1, 'K-04'), (-1, 'K-05')):
        x0, x1 = sorted((f * X_MOD, f * L_EXT / 2))
        fu = furos_tampa(f)
        if f < 0:   # recorte e fixação do E-STOP
            fu += [(X_ESTOP, Y_ESTOP, D_ESTOP)] + [(X_ESTOP + sx * 30, Y_ESTOP + s * 30, 5.5)
                                                   for sx in (1, -1) for s in (1, -1)]
        ps.append(chapa(item, 'z', Z_G2, Z_TAMPA, retangulo(x0, x1, -ye, ye), fu, mat='5052'))
    fc = [(x, y, 5.5) for x in (-(X_MOD + TG / 2), X_MOD + TG / 2) for y in (-150.0, 0.0, 150.0)]
    ps.append(chapa('K-06', 'z', Z_TAMPA, Z_FAIXA, retangulo(*K06), fc, mat='5052'))
    return ps


# ====================================== PARTE B — mastro, bateria, eletrônica
# --- base do mastro: soldada no quadro, na zona livre entre os módulos da gaiola ---
Y_MASTRO = 280.0                 # eixo do mastro (baseline: ±300; aqui ±280 para a luva caber em 600)
E_REF_M = 6.0                    # chapa de reforço sob a luva
Z_REF_M = (Z_DECK, Z_DECK + E_REF_M)        # 340 → 346
D_LUVA, E_LUVA, L_LUVA = 34.0, 4.5, 180.0   # luva Ø34×4,5
Z_LUVA = (Z_REF_M[1], Z_REF_M[1] + L_LUVA)  # 346 → 526
D_MASTRO, E_MASTRO = 25.0, 2.0              # haste (baseline)
D_BAINHA = 29.0                             # bainha anti-galho (baseline)
CAMERAS_Z = (450.0, 1000.0, 1540.0)         # andares das câmeras laterais (ver folha 18)
Z_TRAVA = (Z_LUVA[0] + 54, Z_LUVA[0] + 134)  # parafusos de travamento da haste


def base_mastro():
    """M-01 luva, M-02 chapa de reforço, M-03 nervuras — soldadas ao anel superior."""
    ps = []
    for sy in (1, -1):
        y = sy * Y_MASTRO
        ps.append(chapa('M-02', 'z', Z_REF_M[0], Z_REF_M[1], retangulo(-28.0, 28.0, *sorted((sy * 258.0, sy * YQ))),
                        [(0.0, y, 6.0)]))
        ps.append(cilindro('M-01', 'z', Z_LUVA[0], Z_LUVA[1], 0.0, y, D_LUVA, furo=D_MASTRO, estilo='solid'))
    return ps


def mastro():
    """Haste, bainha e ponta — fornecimento opcional (Parte B)."""
    ps = []
    for sy in (1, -1):
        y = sy * Y_MASTRO
        ps.append(cilindro('M-10', 'z', Z_REF_M[1], Z_TOTAL, 0.0, y, D_MASTRO, furo=D_MASTRO - 2 * E_MASTRO,
                           estilo='solid'))
        faixas = [(Z_LUVA[1] + 10, CAMERAS_Z[1] - 40), (CAMERAS_Z[1] + 40, CAMERAS_Z[2] - 40),
                  (CAMERAS_Z[2] + 40, Z_TOTAL)]
        for (za, zb) in faixas:
            ps.append(cilindro('M-11', 'z', za, zb, 0.0, y, D_BAINHA, furo=D_MASTRO, mat='borracha',
                               estilo='solid'))
        ps.append(cilindro('M-12', 'z', Z_TOTAL, Z_TOTAL + 40, 0.0, y, D_BAINHA, furo=None, mat='borracha',
                           estilo='solid'))
    return ps


E_SUP_CAM = 6.0


def suportes_camera():
    """M-20: placa do suporte da câmera, presa ao mastro por 2 parafusos U (6 conjuntos)."""
    ps = []
    for sy in (1, -1):
        for z in CAMERAS_Z:
            d = D_LUVA if z < Z_LUVA[1] else D_MASTRO
            y0 = sy * (Y_MASTRO + d / 2)
            y1 = y0 + sy * E_SUP_CAM
            furos = [(sx * 22.0, z + sz * 22.0, 7.0) for sx in (1, -1) for sz in (1, -1)]      # parafusos U
            furos += [(sx * 15.0, z + sz * 15.0, 4.5) for sx in (1, -1) for sz in (1, -1)]     # câmera (a validar)
            ps.append(chapa('M-20', 'y', min(y0, y1), max(y0, y1), retangulo(-45.0, 45.0, z - 35, z + 35), furos))
    return ps


def mastro_ref():
    return [cilindro('R-03', 'z', Z_REF_M[1], Z_TOTAL, 0.0, s * Y_MASTRO, D_BAINHA) for s in (1, -1)]


# --- bateria: zona, batentes e amarração ---
BATERIA = (460.0, 350.0, 130.0)   # caixa estimada (A VALIDAR): comprimento × largura × altura
Z_BATERIA = (Z_QUADRO, Z_QUADRO + BATERIA[2])


def bateria_ref():
    return [chapa('R-04', 'z', Z_BATERIA[0], Z_BATERIA[1],
                  retangulo(-BATERIA[0] / 2, BATERIA[0] / 2, -BATERIA[1] / 2, BATERIA[1] / 2), estilo='ref')]


def retencao_bateria():
    """B-01: batente em cantoneira 40×40×4 com rasgo para a cinta (4×)."""
    ps = []
    for sx in (1, -1):
        perfil = [(sx * 245 - sx * 20, Z_QUADRO), (sx * 245 - sx * 20, Z_QUADRO + 4),
                  (sx * 245 + sx * 16, Z_QUADRO + 4), (sx * 245 + sx * 16, Z_QUADRO + 40),
                  (sx * 245 + sx * 20, Z_QUADRO + 40), (sx * 245 + sx * 20, Z_QUADRO)]
        if sx < 0:
            perfil = perfil[::-1]
        ps.append(Prisma('B-01', 'y', -75.0, 75.0, perfil))
    for sy in (1, -1):
        perfil = [(sy * 185 - sy * 20, Z_QUADRO), (sy * 185 - sy * 20, Z_QUADRO + 4),
                  (sy * 185 + sy * 16, Z_QUADRO + 4), (sy * 185 + sy * 16, Z_QUADRO + 40),
                  (sy * 185 + sy * 20, Z_QUADRO + 40), (sy * 185 + sy * 20, Z_QUADRO)]
        if sy < 0:
            perfil = perfil[::-1]
        ps.append(Prisma('B-01', 'x', -75.0, 75.0, perfil))
    return ps


# --- eletrônica: bandejas, E-STOP e aterramento ---
E_BANDEJA = 2.0
X_ESTOP, Y_ESTOP = -460.0, 0.0
D_ESTOP = 22.5


def bandejas():
    """E-01 bandejas laterais (ao lado da bateria) e E-02 bandejas de extremidade."""
    ps = []
    for sy in (1, -1):
        y0, y1 = sorted((sy * 210.0, sy * 264.0))
        ps.append(chapa('E-01', 'z', Z_QUADRO, Z_QUADRO + E_BANDEJA, retangulo(-190.0, 190.0, y0, y1),
                        [(sx * 170.0, sy * 240.0, 7.0) for sx in (1, -1)]
                        + [(sx * 100.0, sy * 232.0, 5.5) for sx in (1, -1)], mat='5052'))
    for sx in (1, -1):
        x0, x1 = sorted((sx * 368.0, sx * 488.0))
        for s in (1, -1):
            y0, y1 = sorted((s * 105.0, s * 250.0))
            ps.append(chapa('E-02', 'z', Z_QUADRO, Z_QUADRO + E_BANDEJA, retangulo(x0, x1, y0, y1),
                            [(sx * 390.0, s * 220.0, 7.0), (sx * 430.0, s * 120.0, 5.5)], mat='5052'))
    return ps


def estop():
    """E-10 reforço e E-11 protetor do botão de emergência, na tampa traseira."""
    ps = [chapa('E-10', 'z', Z_G2 - 3, Z_G2, retangulo(X_ESTOP - 40, X_ESTOP + 40, Y_ESTOP - 40, Y_ESTOP + 40),
                [(X_ESTOP, Y_ESTOP, D_ESTOP)] + [(X_ESTOP + sx * 30, Y_ESTOP + s * 30, 5.5)
                                                 for sx in (1, -1) for s in (1, -1)])]
    # protetor: barra 50×4 dobrada em U (2 pernas + travessa), aparafusada na tampa
    for sy in (1, -1):
        ps.append(Prisma('E-11', 'y', sy * 26 - 2, sy * 26 + 2,
                         [(X_ESTOP - 25, Z_TAMPA), (X_ESTOP + 25, Z_TAMPA),
                          (X_ESTOP + 25, Z_TAMPA + 51), (X_ESTOP - 25, Z_TAMPA + 51)]))
    ps.append(Prisma('E-11', 'y', -28.0, 28.0, [(X_ESTOP - 25, Z_TAMPA + 51), (X_ESTOP + 25, Z_TAMPA + 51),
                                                (X_ESTOP + 25, Z_TAMPA + 55), (X_ESTOP - 25, Z_TAMPA + 55)]))
    return ps


# =============== interfaces de sensores e sinalização (N) — folha 22 ======
X_GNSS = -350.0                          # antena GNSS sobre a tampa traseira (baseline: X 0 · Z 390)
Z_GNSS = (Z_TAMPA, Z_TAMPA + 5.0)        # chapa do suporte: 398,2 -> 403,2
D_ANTENA, H_ANTENA = 70.0, 30.0          # envelope da antena (A VALIDAR com o modelo escolhido)
X_IMU, Z_IMU, E_IMU = 300.0, 310.0, 6.0  # face de montagem do IMU (altura da baseline)
JANELA_RAIZ = (395.0, 465.0, -60.0, 60.0)   # abertura da câmera de raiz (vão entre travessas)
E_JANELA = 3.0                           # policarbonato
Y_LED, Z_LED, D_LED = 150.0, 358.5, 20.0    # faróis na carenagem frontal (faixa Z 341→376)
E_CAREN_CAM = 3.0                        # carenagem anti-galho das câmeras (UHMW-PE)


def suporte_gnss():
    """N-01: chapa do suporte da antena GNSS, aparafusada sobre a tampa traseira."""
    furos = [(X_GNSS + dx, dy, D_FOLGA_M5) for dx in (-45.0, 45.0) for dy in (-45.0, 45.0)]
    furos += [(X_GNSS + dx, dy, 4.5) for dx in (-25.0, 25.0) for dy in (-25.0, 25.0)]
    furos += [(X_GNSS, 0.0, 20.0)]
    return [chapa('N-01', 'z', Z_GNSS[0], Z_GNSS[1],
                  ret_arred(X_GNSS - 55, X_GNSS + 55, -55.0, 55.0, 6), furos)]


def gnss_ref():
    return [cilindro('R-05', 'z', Z_GNSS[1], Z_GNSS[1] + H_ANTENA, X_GNSS, 0.0, D_ANTENA)]


def berco_imu():
    """N-02 berço do IMU (face usinada em Z 310) sobre 4 espaçadores N-03."""
    z0 = Z_IMU - E_IMU
    furos = [(X_IMU + dx, dy, 6.6) for dx in (-22.0, 22.0) for dy in (-25.0, 25.0)]
    furos += [(X_IMU + dx, dy, 3.4) for dx in (-20.0, 20.0) for dy in (-15.0, 15.0)]
    furos += [(X_IMU, 0.0, 10.0)]
    ps = [chapa('N-02', 'z', z0, Z_IMU, retangulo(X_IMU - 45, X_IMU + 45, -35.0, 35.0), furos)]
    for dx in (-22.0, 22.0):
        for dy in (-25.0, 25.0):
            ps.append(cilindro('N-03', 'z', Z_QUADRO, z0, X_IMU + dx, dy, 12.0, furo=6.6, estilo='solid'))
    return ps


def visao_raiz():
    """N-04 janela, N-05 barras de proteção e N-06/N-07 suporte da câmera de zona de raiz."""
    x0, x1, y0, y1 = JANELA_RAIZ
    furos = [(x, y, 4.5) for x in (x0 - 13, (x0 + x1) / 2, x1 + 13) for y in (-72.0, 72.0)]
    ps = [chapa('N-04', 'z', Z_QUADRO, Z_QUADRO + E_JANELA,
                ret_arred(x0 - 25, x1 + 25, y0 - 25, y1 + 25, 8), furos, mat='pc')]
    for x in (x0 + 18, x1 - 18):
        ps.append(cilindro('N-05', 'y', y0 - 20, y1 + 20, x, Z_QUADRO - E_CHAPA - 4.0, 8.0, estilo='solid'))
    zb = Z_QUADRO + E_JANELA + 1.0
    for sy in (1, -1):
        perfil = [(395.0, Z_QUADRO), (485.0, Z_QUADRO), (485.0, zb + 35.0), (480.0, zb + 35.0),
                  (480.0, zb), (400.0, zb)]
        if sy < 0:
            perfil = perfil[::-1]
        ps.append(Prisma('N-06', 'y', min(sy * 92.0, sy * 95.0), max(sy * 92.0, sy * 95.0), perfil))
    ps.append(Prisma('N-07', 'y', -95.0, 95.0,
                     [(400.0, zb), (480.0, zb + 35.0), (478.8, zb + 37.75), (398.8, zb + 2.75)]))
    return ps


def suporte_led():
    """N-08: anel de apoio dos faróis, por dentro da carenagem frontal."""
    ps = []
    for sy in (1, -1):
        c = sy * Y_LED
        furos = [(c, Z_LED, D_LED)]
        furos += [(c + dy, Z_LED + dz, 4.5) for dy in (-22.0, 22.0) for dz in (-13.0, 13.0)]
        ps.append(chapa('N-08', 'x', XQ - 2.0, XQ, retangulo(c - 30.0, c + 30.0, Z_LED - 17.5, Z_LED + 17.5),
                        furos, mat='5052'))
    return ps


def carenagem_cameras():
    """N-09: carenagem anti-galho das câmeras do mastro (6x), UHMW-PE de 3 mm, nariz voltado para +X."""
    ps = []
    for sy in (1, -1):
        for z in CAMERAS_Z:
            d = D_LUVA if z < Z_LUVA[1] else D_MASTRO
            f0 = sy * (Y_MASTRO + d / 2 + E_SUP_CAM)
            ya, yb = sorted((f0, f0 + sy * 34.0))
            ym = (ya + yb) / 2
            e = E_CAREN_CAM
            ext = [(-25.0, ya), (25.0, ya), (45.0, ym), (25.0, yb), (-25.0, yb)]
            ins = [(-22.0, ya + e), (22.0, ya + e), (39.0, ym), (22.0, yb - e), (-22.0, yb - e)]
            ps.append(Prisma('N-09', 'z', z - 25.0, z + 25.0, ext, [ins], mat='uhmw', estilo='solid'))
    return ps


def interfaces_sensores():
    return suporte_gnss() + berco_imu() + visao_raiz() + suporte_led() + carenagem_cameras()


# ================================================================== catálogo
ITENS = {
    'Q-01': dict(nome='Longarina', desc='Tubo quadrado 30×30×2', mat='Al 6061-T6', origem='BASE'),
    'Q-02': dict(nome='Travessa de extremidade', desc='Tubo quadrado 30×30×2', mat='Al 6061-T6', origem='NOVO'),
    'Q-03': dict(nome='Travessa da estação de roda', desc='Tubo quadrado 30×30×2', mat='Al 6061-T6', origem='NOVO'),
    'Q-04': dict(nome='Montante entre anéis', desc='Tubo quadrado 30×30×2', mat='Al 6061-T6', origem='NOVO'),
    'Q-05': dict(nome='Bucha de compressão', desc='Barra Ø12, furo Ø8,5', mat='Al 6061-T6', origem='NOVO'),
    'Q-06': dict(nome='Tampa de extremidade', desc='Chapa 30×30×2', mat='Al 6061-T6', origem='NOVO'),
    'C-01': dict(nome='Chapa de fundo', desc=f'Chapa {_n(L_Q)}×{_n(W_Q)}×2', mat='Al 5052-H32', origem='NOVO'),
    'C-02': dict(nome='Nervura da chapa de fundo', desc=f'Cantoneira 40×40×4 × {_n(2 * (YQ - 2))}',
                 mat='Al 6061-T6', origem='NOVO'),
    'S-01': dict(nome='Chapa superior do suporte', desc=f'Chapa 140×{_n(YQ - 110)}×6', mat='Al 6061-T6',
                 origem='NOVO'),
    'S-02': dict(nome='Chapa de montagem do MPW86', desc='Chapa 124×204×10', mat='Al 6061-T6', origem='NOVO'),
    'S-03': dict(nome='Nervura do suporte', desc='Chapa 84×92×8', mat='Al 6061-T6', origem='NOVO'),
    'G-01': dict(nome='Trilho lateral', desc='Tubo quadrado 20×20×1,5', mat='Al 6061-T6', origem='NOVO'),
    'G-02': dict(nome='Trilho transversal', desc='Tubo quadrado 20×20×1,5', mat='Al 6061-T6', origem='NOVO'),
    'G-03': dict(nome='Barra intermediária', desc='Tubo quadrado 20×20×1,5', mat='Al 6061-T6', origem='NOVO'),
    'G-04': dict(nome='Montante da gaiola', desc='Tubo quadrado 20×20×1,5', mat='Al 6061-T6', origem='NOVO'),
    'G-05': dict(nome='Sapata', desc='Chapa 70×30×3', mat='Al 6061-T6', origem='NOVO'),
    'G-06': dict(nome='Suporte do LiDAR', desc='Chapa 130×110×5', mat='Al 6061-T6', origem='NOVO'),
    'G-07': dict(nome='Tampa do trilho', desc='Chapa 20×20×1,5', mat='Al 6061-T6', origem='NOVO'),
    'G-08': dict(nome='Coxim antivibração', desc='Borracha Ø15×10, M4', mat='NBR 60 Shore A', origem='NOVO'),
    'K-01': dict(nome='Carenagem lateral (meia)', desc=f'Chapa {_n(XQ)}×{_n(Z_G2 - Z_QUADRO)}×2',
                 mat='Al 5052-H32', origem='NOVO'),
    'K-02': dict(nome='Carenagem frontal', desc=f'Chapa {_n(W_EXT)}×{_n(Z_G2 - Z_QUADRO)}×2', mat='Al 5052-H32',
                 origem='NOVO'),
    'K-03': dict(nome='Carenagem traseira', desc=f'Chapa {_n(W_EXT)}×{_n(Z_G2 - Z_QUADRO)}×2', mat='Al 5052-H32',
                 origem='NOVO'),
    'K-04': dict(nome='Tampa superior dianteira', desc=f'Chapa {_n(L_EXT / 2 - X_MOD)}×{_n(W_EXT)}×1,2',
                 mat='Al 5052-H32', origem='NOVO'),
    'K-05': dict(nome='Tampa superior traseira', desc=f'Chapa {_n(L_EXT / 2 - X_MOD)}×{_n(W_EXT)}×1,2',
                 mat='Al 5052-H32', origem='NOVO'),
    'K-06': dict(nome='Faixa central', desc='Chapa 110×512×1,2', mat='Al 5052-H32', origem='NOVO'),
}

ITENS.update({
    'M-01': dict(nome='Luva do mastro', desc='Tubo Ø34×4,5 × 180', mat='Al 6061-T6', origem='NOVO'),
    'M-02': dict(nome='Chapa de reforço da base', desc='Chapa 56×40×6', mat='Al 6061-T6', origem='NOVO'),
    'M-10': dict(nome='Haste do mastro', desc='Tubo Ø25×2 × 1436', mat='Al 6061-T6', origem='BASE'),
    'M-11': dict(nome='Bainha anti-galho', desc='Tubo Ø29/Ø25', mat='UHMW-PE', origem='BASE'),
    'M-12': dict(nome='Ponta cônica', desc='Ø29 × 40', mat='UHMW-PE', origem='BASE'),
    'M-20': dict(nome='Suporte da câmera', desc='Chapa 90×70×6', mat='Al 6061-T6', origem='NOVO'),
    'B-01': dict(nome='Batente da bateria', desc='Cantoneira 40×40×4 × 150', mat='Al 6061-T6', origem='NOVO'),
    'E-01': dict(nome='Bandeja lateral', desc='Chapa 380×54×2', mat='Al 5052-H32', origem='NOVO'),
    'E-02': dict(nome='Bandeja de extremidade', desc='Chapa 145×120×2', mat='Al 5052-H32', origem='NOVO'),
    'E-10': dict(nome='Reforço do E-STOP', desc='Chapa 80×80×3', mat='Al 6061-T6', origem='NOVO'),
    'E-11': dict(nome='Protetor do E-STOP', desc='Barra 50×4', mat='Al 6061-T6', origem='NOVO'),
    'N-01': dict(nome='Suporte da antena GNSS', desc='Chapa 110×110×5', mat='Al 6061-T6', origem='NOVO'),
    'N-02': dict(nome='Berço do IMU', desc='Chapa 90×70×6, face usinada', mat='Al 6061-T6', origem='NOVO'),
    'N-03': dict(nome='Espaçador do berço', desc='Tubo Ø12, furo Ø6,6 × 54', mat='Al 6061-T6', origem='NOVO'),
    'N-04': dict(nome='Janela da câmera de raiz', desc='Policarbonato 120×170×3', mat='PC', origem='NOVO'),
    'N-05': dict(nome='Barra de proteção da janela', desc='Barra Ø8 × 160', mat='Al 6061-T6', origem='NOVO'),
    'N-06': dict(nome='Aba do suporte da câmera de raiz', desc='Chapa 90×39×3', mat='Al 6061-T6', origem='NOVO'),
    'N-07': dict(nome='Face inclinada da câmera de raiz', desc='Chapa 140×87×3', mat='Al 6061-T6', origem='NOVO'),
    'N-08': dict(nome='Reforço do farol', desc='Chapa 60×35×2', mat='Al 5052-H32', origem='NOVO'),
    'N-09': dict(nome='Carenagem anti-galho da câmera', desc='UHMW-PE 3, caixa 50×34 + nariz 20',
                 mat='UHMW-PE', origem='BASE'),
})

GRUPOS = {
    'Q': 'Quadro estrutural soldado',
    'C': 'Chapa de fundo e nervuras',
    'S': 'Suportes do motor-roda (2 E + 2 D, soldados e usinados)',
    'G': 'Gaiola de proteção (2 módulos idênticos)',
    'K': 'Carenagens e tampas',
    'M': 'Mastros: base, haste e suportes de câmera',
    'B': 'Retenção da bateria',
    'E': 'Bandejas de eletrônica e E-STOP',
    'N': 'Interfaces de sensores e sinalização',
}


def conjunto_a():
    """Parte A — chassi e gaiola (o que vai para cotação agora).

    **Suspensão: rígida (grupo S).** É a arquitetura desenhada nas folhas, cotada
    no pacote Rev E e sobre a qual o fabricante fez os quatro comentários que a
    Rev F responde. O estudo de balancim (grupo W) existe em :func:`suspensao` e
    está fora deste conjunto de propósito — ver a nota no topo daquela função e o
    item D-01 da auditoria da Rev F.

    Entre a Rev E emitida e a Rev F, este conjunto chamava ``suspensao()`` no
    lugar de ``suportes()``. Como ``GRUPOS`` e ``ITENS`` nunca acompanharam, nem
    o caderno nem o pacote de orçamento geravam — ``KeyError: 'S'`` numa ponta e
    ``KeyError: 'W-01'`` na outra. Trocar de volta é o que devolve a
    regenerabilidade sem escolher a arquitetura de suspensão no lugar do
    engenheiro.
    """
    return (quadro() + base_mastro() + chapa_fundo() + suportes() + gaiola()
            + suporte_lidar() + carenagens())


def conjunto_w():
    """O estudo de suspensão de balancim, isolado.

    Separado de :func:`conjunto_a` porque é alternativa, e não acréscimo: W-02
    ocupa exatamente o espaço de S-02 (X 288…412, Y 194…204), só terminando em
    Z 180 — onde pega o balancim — em vez de Z 242, onde S-02 pega no quadro.
    Somar os dois contaria a chapa de montagem do motor duas vezes.
    """
    return suspensao()


def conjunto_b():
    """Parte B — interfaces: mastro, câmeras, bateria e eletrônica."""
    return (mastro() + suportes_camera() + retencao_bateria() + bandejas() + estop()
            + interfaces_sensores())


def conjunto(parte='A'):
    return conjunto_a() if parte == 'A' else (conjunto_b() if parte == 'B' else conjunto_a() + conjunto_b())


def referencias():
    return rodas() + lidar_ref() + gnss_ref()


# ======================================================== fixadores (F)
def fixadores():
    n_m6_chapa = sum(1 for f in furos_chapa() if f[3].startswith('M6'))
    n_sapata = 2 * len([p for p in gaiola() if p.item == 'G-05'])
    n_m5_lat = 4 * len(X_FUROS_LAT) * len(Z_LINHAS_LAT)
    n_m5_fr = 2 * len(Y_FUROS_FR) * len(Z_LINHAS_LAT)
    n_m5_lidar = 4
    n_m5_tampa = sum(1 for f in (1, -1) for fu in furos_tampa(f) if fu[2] == D_FOLGA_M5) - n_m5_lidar
    n_rebite = sum(1 for f in furos_chapa() if f[2] == 4.9)
    n_m8 = 4 * len(FUROS_SUPORTE)
    n_m6 = n_m6_chapa + n_sapata
    n_m5 = n_m5_lat + n_m5_fr + n_m5_tampa
    return [
        ('F-01', 'Parafuso M8×55 ISO 4762', 'Inox A4-70', n_m8, 'Suporte → quadro, através da chapa e da bucha'),
        ('F-02', 'Porca M8 autotravante DIN 985', 'Inox A4', n_m8, ''),
        ('F-03', 'Arruela lisa M8 ISO 7089', 'Inox A4', 2 * n_m8, ''),
        ('F-04', 'Porca-rebite M6 passante, cabeça reduzida Ø ≤ 12', 'Inox A4', n_m6,
         f'{n_m6_chapa} no anel inferior (chapa) + {n_sapata} no anel superior (sapatas)'),
        ('F-05', 'Parafuso M6×16 ISO 7380', 'Inox A4-70', n_m6, ''),
        ('F-06', 'Porca-rebite M5 passante, cabeça reduzida Ø ≤ 10', 'Inox A4', n_m5 + n_m5_lidar,
         'Paredes externas dos tubos'),
        ('F-07', 'Parafuso M5×12 ISO 7380', 'Inox A4-70', n_m5, 'Cabeça baixa e lisa: não prende galho'),
        ('F-08', 'Parafuso M5×16 ISO 7380', 'Inox A4-70', n_m5_lidar, 'Suporte do LiDAR'),
        ('F-09', 'Rebite de repuxo Ø4,8×10', 'Alumínio', n_rebite, 'Nervuras C-02 → chapa C-01'),
        ('F-10', 'Parafuso M4×14 ISO 4762 + trava química média', 'Inox A4-70', 4 * MPW_N_FUROS,
         'MPW86 → suporte (engajamento 4 ≤ 5 mm)'),
        ('F-11', 'Passa-cabo de borracha para furo Ø32', 'EPDM', 4, 'Cabos dos motores'),
        ('F-12', 'Arruela larga M6 ISO 7093 (Ø18)', 'Inox A4', n_m6, 'Sobre furo de folga Ø13'),
        ('F-13', 'Arruela larga M5 ISO 7093 (Ø15)', 'Inox A4', n_m5 + n_m5_lidar, 'Sobre furo de folga Ø11'),
        ('F-20', 'Parafuso U M6 para tubo Ø25 (com 2 porcas)', 'Inox A4', 8, 'Suportes M-20 na haste'),
        ('F-21', 'Parafuso U M6 para tubo Ø34 (com 2 porcas)', 'Inox A4', 4, 'Suportes M-20 na luva'),
        ('F-22', 'Parafuso M6×20 ISO 7380 + porca-rebite M6', 'Inox A4', 24,
         'Batentes B-01 e bandejas E-01/E-02 na malha da chapa'),
        ('F-23', 'Cinta de poliéster 25 mm com catraca, LC ≥ 250 daN', 'Poliéster', 2, 'Amarração da bateria'),
        ('F-24', 'Parafuso M6×12 passante (travamento da haste)', 'Inox A4-70', 4, 'Haste na luva'),
        ('F-25', 'Parafuso M5×16 + porca', 'Inox A4', 8, 'E-10 e E-11 na tampa traseira'),
        ('F-26', 'Parafuso M5×16 + porca-rebite M5', 'Inox A4', 4, 'Suporte da antena GNSS na tampa'),
        ('F-27', 'Parafuso M6×16 ISO 7380', 'Inox A4', 12, 'Berço do IMU e suporte da câmera de raiz'),
        ('F-28', 'Parafuso M4×12 + porca-rebite M4', 'Inox A4', 6, 'Janela de policarbonato'),
        ('F-29', 'Parafuso M4×10', 'Inox A4', 20, 'Carenagens N-09, faróis e antena'),
    ]


MASSA_FIXADORES = 1.4  # ESTIMATIVA (kg) — parafusos, porcas-rebite, rebites


# ================================================ massas e comparação baseline
BASELINE_MASSAS = [  # (componente, kg, Z mm) — tabela 5.1 da baseline Rev E
    ('Quadro estrutural', 2.1, 250), ('Chapa de fundo', 1.3, 252), ('Suportes e fixadores', 2.5, 295),
    ('Gaiola de proteção (base)', 5.0, 370),
]
M_NOM, ZCG_NOM, M_MIN = 97.8, 297.0, 85.04


def resumo_massas(parte='A'):
    por_grupo = {}
    for p in conjunto(parte):
        if p.estilo == 'ref':
            continue
        m, c = p.massa(), p.centroide()
        a = por_grupo.setdefault(p.grupo, [0.0, 0.0, 0.0, 0.0])
        a[0] += m
        a[1] += m * c[0]
        a[2] += m * c[1]
        a[3] += m * c[2]
    return {g: (m, mx / m, my / m, mz / m) for g, (m, mx, my, mz) in por_grupo.items()}


def comparacao_baseline():
    g = resumo_massas()
    ms = g['S'][0] + g['M'][0] + MASSA_FIXADORES
    mg = g['G'][0] + g['K'][0]
    novo = [
        ('Quadro estrutural', g['Q'][0], g['Q'][3], 'Q-01…Q-06'),
        ('Chapa de fundo', g['C'][0], g['C'][3], 'C-01, C-02'),
        ('Suportes e fixadores', ms,
         (g['S'][0] * g['S'][3] + g['M'][0] * g['M'][3] + MASSA_FIXADORES * 300) / ms, 'S + M + F (F estim. 1,4)'),
        ('Gaiola de proteção (base)', mg, (g['G'][0] * g['G'][3] + g['K'][0] * g['K'][3]) / mg, 'G + K'),
    ]
    linhas = []
    dm = dmz = 0.0
    for (nome, mb, zb), (_, mn, zn, itens) in zip(BASELINE_MASSAS, novo):
        linhas.append((nome, mb, zb, mn, zn, itens))
        dm += mn - mb
        dmz += mn * zn - mb * zb
    m_nom_novo = M_NOM + dm
    z_novo = (M_NOM * ZCG_NOM + dmz) / m_nom_novo
    return dict(linhas=linhas, dm=dm, m_min_novo=M_MIN + dm, m_nom_novo=m_nom_novo, zcg_novo=z_novo,
                margem_rest=M_NOM - (M_MIN + dm),
                tomb_base=math.degrees(math.atan((BITOLA / 2) / ZCG_NOM)),
                tomb_novo=math.degrees(math.atan((BITOLA / 2) / z_novo)))


# soma da tabela 5.1 completa da baseline (conferência)
TABELA_51 = [2.1, 1.3, 2.5, 5.0, 18.0, 1.5, 36.5, 3.0, 1.5, 3.0, 1.2, 0.4, 0.265, 0.30, 0.05, 0.40, 0.40, 1.0,
             1.10, 0.37, 1.13, 0.40, 0.455, 0.617, 0.005]


def envelope_estabilidade(zcg, e_y=15.0, phi_c=3.0, fs=1.3, h_obs=60.0, dphi=2.0):
    """Envelope conservador da seção 6.1 da baseline, com os parâmetros ali publicados."""
    ssf = (BITOLA / 2 - e_y - zcg * math.sin(math.radians(phi_c))) / zcg
    return math.degrees(math.atan(ssf / fs) - math.asin(h_obs / BITOLA) - math.radians(dphi))


def envelope():
    """Caixa envolvente de todas as peças fornecidas (conferência contra a baseline)."""
    xs, ys, zs = [], [], []
    for p in conjunto():
        if p.estilo == 'ref':
            continue
        bb = p.bbox()
        xs += bb[0]
        ys += bb[1]
        zs += bb[2]
    return (min(xs), max(xs)), (min(ys), max(ys)), (min(zs), max(zs))


if __name__ == '__main__':
    for g, v in resumo_massas().items():
        print(g, [round(x, 3) for x in v])
    c = comparacao_baseline()
    for l in c['linhas']:
        print(l)
    print({k: round(v, 3) for k, v in c.items() if k != 'linhas'})
    print('envelope', envelope())
    print('soma tabela 5.1:', round(sum(TABELA_51), 3))
    for f in fixadores():
        print(f)


# ============================ massa consolidada (baseline + Parte A + Parte B)
# Itens da tabela 5.1 que este caderno redesenha (kg, Z mm): estrutura + mastro e seus suportes.
REDESENHADOS = [('Quadro estrutural', 2.1, 250), ('Chapa de fundo', 1.3, 252),
                ('Suportes e fixadores', 2.5, 295), ('Gaiola de proteção (base)', 5.0, 370),
                ('Mastro bilateral', 1.13, 1061), ('Suportes do mastro', 0.40, 700),
                ('Bainha anti-galho', 0.455, 1061), ('Ponta cônica', 0.005, 1802),
                ('Carenagem anti-galho das câmeras', 0.617, 700)]


def impacto_motor(qual):
    """Efeito de trocar o motor-roda: massa, CG, estabilidade, torque e carga por roda."""
    base = consolidado()
    atual, novo = MOTORES[MOTOR], MOTORES[qual]
    d_massa = 4 * (novo['massa'] - atual['massa'])
    m = base['m_min'] + d_massa
    z = (base['m_min'] * base['zcg'] + d_massa * Z_EIXO) / m
    m_max = base['m_max'] + d_massa
    return dict(
        motor=novo, d_massa=d_massa, m_min=m, zcg=z, m_max=m_max,
        tomb=math.degrees(math.atan((BITOLA / 2) / z)),
        envelope=envelope_estabilidade(z),
        torque13=11.0 * m_max / 126.0,
        carga_roda=m_max / 4,
        folga_carga=novo['carga_roda'] - m_max / 4,
        folga_torque=novo['torque_cont'] - 11.0 * m_max / 126.0,
        margem=M_NOM - m,
        preco_4=4 * novo['preco_brl'],
        economia=4 * (atual['preco_brl'] - novo['preco_brl']))


def consolidado():
    """Massa e CG somando: tabela 5.1 (itens mantidos) + Parte A + Parte B + fixadores."""
    mantidos_m = sum(TABELA_51) - sum(m for _, m, _ in REDESENHADOS)
    # CG dos mantidos: do nominal da baseline, tirando os redesenhados
    m_red = sum(m for _, m, _ in REDESENHADOS)
    mz_red = sum(m * z for _, m, z in REDESENHADOS)
    mz_mantidos = M_NOM * ZCG_NOM - mz_red - (M_NOM - M_MIN) * ZCG_NOM  # sem a margem de 15 %
    z_mantidos = mz_mantidos / mantidos_m
    novos = []
    for parte in ('A', 'B'):
        for g, (m, _, _, z) in resumo_massas(parte).items():
            novos.append((f'{parte} · {g}', m, z))
    novos.append(('Fixadores', MASSA_FIXADORES, 300.0))
    m_tot = mantidos_m + sum(m for _, m, _ in novos)
    z_tot = (mz_mantidos + sum(m * z for _, m, z in novos)) / m_tot
    m_max = 126.0 + (m_tot - M_MIN)
    return dict(mantidos=(mantidos_m, z_mantidos), novos=novos, m_min=m_tot, zcg=z_tot, m_max=m_max,
                delta=m_tot - M_MIN, margem=M_NOM - m_tot,
                tomb=math.degrees(math.atan((BITOLA / 2) / z_tot)),
                torque13=11.0 * m_max / 126.0)
