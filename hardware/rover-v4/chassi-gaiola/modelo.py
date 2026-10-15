"""Geometria paramétrica do chassi estrutural e da gaiola de proteção do VALTEXA Rover V4.

Base: VTX-RV4-BASELINE-E (Rev E, 18/09/2026). Unidades: mm e kg.
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
BITOLA = 530.0       # bitola                         CALC  (Rev H: era 470 — ver nota)
# A bitola subiu 60 mm na Rev H, e é essa cota que paga a suspensão independente.
#
# Até a Rev F o projeto recusava articulação em rolagem porque ela derruba o tombamento.
# Com quatro foles independentes a rolagem deixa de ser rígida por construção: a carroceria
# rola até o fim do curso, e o CG migra para fora. Com bitola 470 isso custava cerca de 4°
# de tombamento — o motivo pelo qual as Rev E/F ficaram no suporte rígido.
#
# O envelope externo W_EXT = 600 nunca foi usado inteiro: a roda ficava com a face externa em
# |Y| = 261, sobrando 39 mm de cada lado. Levando a bitola a 530 a face externa vai a 291,05
# (8,95 mm dentro da linha de 300) e a carenagem lateral não é afetada — ela começa em Z 250 e
# a roda termina em Z 200, não há sobreposição vertical nenhuma.
#
# O ganho: meia-bitola 235 -> 265 mm. O tombamento sobe o bastante para absorver a rolagem da
# suspensão e ainda sair na frente do arranjo rígido. Os números estão em
# ../revisao-h/suspensao.py (`roll`, `estabilidade`) e na folha 07.
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

# Interface do motor-roda (chapa W-02 da suspensão)
Y_FACE = 234.0           # face de montagem do MPW86 (|Y|); 265 − 26,05 − 5 = 233,95 → 234 (bitola 530,1)
Z_EIXO = D_RODA / 2      # centro da roda
E_PLACA = 10.0           # chapa de montagem (bruta; face usinada, final ≥ 9,5)
R_PLACA = 62.0           # raio inferior da chapa de montagem
D_BORE = 88.0            # furo central (passa o motor Ø86,5 máx.)

# Chapas que assentam sobre porca-rebite levam furo de folga para a cabeça dela; a arruela
# larga ISO 7093 aperta a chapa direto contra o tubo.
D_FOLGA_M6 = 13.0        # cabeça reduzida da porca-rebite M6 (Ø ≤ 12)
D_FOLGA_M5 = 11.0        # cabeça reduzida da porca-rebite M5 (Ø ≤ 10)

RHO = {'6061': 2.70e-6, '5052': 2.68e-6, 'borracha': 1.15e-6, 'inox': 7.95e-6,
       'uhmw': 0.95e-6, 'pc': 1.20e-6, 'aco': 7.85e-6, 'pu': 1.20e-6}

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
# Fixação da suspensão no anel inferior. Cada posição é UM parafuso que atravessa, de cima
# para baixo: berço do fole W-11 (Z 290) → bucha de compressão Q-05 dentro da travessa
# (280→250) → chapa de fundo C-01 (250→248) → e, na estação X_CANTO, o berço do pivô W-06
# (248→238). Um parafuso único amarra os quatro níveis; na estação XS termina em porca.
Y_FUROS_SUSP = (168.0, 250.0)
FUROS_SUSPENSAO = tuple((x, y) for x in (XS, X_CANTO) for y in Y_FUROS_SUSP)


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
            for (ax, ay) in FUROS_SUSPENSAO:
                ps.append(cilindro('Q-05', 'z', ANEL_INF[0], ANEL_INF[1], sx * ax, s * ay, 12.0, furo=8.5,
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
            for (ax, ay) in FUROS_SUSPENSAO:
                f.append((sx * ax, s * ay, 8.5, 'M8 → berço do fole / berço do pivô'))
    for sx in (1, -1):
        for y in (-225.0, -135.0, -45.0, 45.0, 135.0, 225.0):
            f.append((sx * X_NERV, y, 4.9, 'rebite Ø4,8 → nervura'))
    for x in (-470.0, -250.0, 250.0, 470.0):
        for y in (-120.0, 120.0):
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
                  + [(sx * 320.0, s * 220.0) for sx in (1, -1) for s in (1, -1)]
                  + [(sx * x, s * 25.0) for sx in (1, -1) for x in (278.0, 322.0) for s in (1, -1)]
                  + [(x, s * 125.0) for x in (400.0, 470.0) for s in (1, -1)])   # bandejas de extremidade
# A faixa |Y| 125 das bandejas de extremidade é imposta pela suspensão: o colar do fole
# ocupa |Y| 159…259 em X 375…475, e a janela da câmera de raiz ocupa |Y| ≤ 95 na dianteira.
# Sobra a faixa entre 100 e 152, e é onde a E-02 cabe. Ver ../revisao-h/espaco.py.


def chapa_fundo():
    # Quatro passagens Ø94 para os foles, uma por canto, vedadas pelo colar W-12.
    # É o único furo novo que a suspensão pneumática abre no compartimento, e ele não o
    # viola: o colar é canõ fechado no topo pelo berço W-11, com junta nas duas pontas.
    passagens = [(sx * X_FOLE, s * Y_FOLE, D_PASSAGEM) for sx in (1, -1) for s in (1, -1)]
    ps = [chapa('C-01', 'z', Z_QUADRO - E_CHAPA, Z_QUADRO, retangulo(-XQ, XQ, -YQ, YQ),
                [(x, y, d) for (x, y, d, _) in furos_chapa()] + passagens, mat='5052',
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


# ======================== suspensão pneumática independente (grupo W) =========
# DECISÃO DE ENGENHARIA, Rev H: quatro braços longitudinais independentes, um fole
# pneumático por canto, SEM barra estabilizadora. Substitui o suporte rígido (grupo S das
# Rev E/F) e o estudo de balancim longitudinal (grupo W da Rev F). As duas arquiteturas
# anteriores estão congeladas em ../versao-antiga/.
#
# O cálculo que sustenta cada número está em ../revisao-h/suspensao.py e sai impresso
# rodando `python suspensao.py`. Resumo do raciocínio:
#
# 1. ROLAGEM — a objeção que travava a suspensão a ar. Fole é mola macia, e rolagem macia
#    derruba o tombamento; foi por isso que as Rev E/F ficaram no suporte rígido. A Rev H
#    não resolve isso com rigidez, resolve com BITOLA: 470 -> 530 mm, dentro do mesmo
#    envelope externo de 600 que nunca era usado inteiro. E resolve com CURSO: com ±25 mm
#    em 530 de bitola a carroceria só consegue rolar 5,4° antes de bater no fim de curso,
#    então a rolagem é limitada pela geometria, não pela rigidez da mola. Resultado:
#    envelope de estabilidade 16,3° contra 15,5° do balancim rígido, no mesmo CG do V4
#    (inventário de centro_massa.py; até 15/10/2026 o texto dizia 20,9° contra 19,6°, com o
#    CG da Rev F). A suspensão macia fica mais estável que a rígida porque a bitola pagou
#    a conta — mas passa a baseline de 16,2° por apenas 0,1°.
#
# 2. SEM BARRA ESTABILIZADORA, e isso é resultado de cálculo. Com rigidez de roda de
#    ~2 N/mm, uma articulação de 60 mm num eixo já transfere quase toda a carga estática
#    da roda; qualquer barra com rigidez útil levanta roda em terreno torcido. Ver
#    `barra_estabilizadora` no módulo citado — o número está lá para quem quiser conferir.
#
# 3. QUATRO CIRCUITOS INDEPENDENTES, um por canto, sem interligação esquerda-direita.
#    Interligar os lados equaliza pressão e ZERA a rigidez de rolagem — o oposto do que se
#    precisa aqui. Interligação é o que se faz quando se quer articulação, e articulação
#    aqui já vem da independência dos braços.
#
# 4. BRAÇO HORIZONTAL (eixo do pivô na mesma cota do eixo do braço, Z 190). Não é
#    preferência de desenho: braço inclinado gera componente longitudinal no pivô a cada
#    curso e muda a relação de movimento ao longo dele. Horizontal, a relação é constante.
#
# 5. PIVÔ DIANTEIRO À FRENTE DA RODA E TRASEIRO ATRÁS (|X| 500, roda em |X| 350). A reação
#    de torque do motor-roda gira os braços dos dois eixos em sentidos opostos: dá
#    perturbação de ARFAGEM pura e zero de altura. Com os 20 N·m contínuos do MPW86 são
#    ~17 mm na roda, dentro da autoridade do nivelamento.
#
# O fole é COMPRADO e não tem ficha técnica no projeto. Por isso o que está desenhado aqui
# é a INTERFACE — prato, berço, colar, curso, altura instalada, área efetiva — como
# REQUISITO, e não um componente específico. Os pratos W-08 e o berço W-11 aceitam
# qualquer fole que caiba no envelope da folha 07, e aceitam igualmente um cilindro
# pneumático de mesma área, que é a alternativa qualificada. Nenhum desenho de usinagem
# depende de qual dos dois for escolhido.

# ---- braço e pivô
X_PIVO = 500.0            # estação do pivô (|X|)                 CALC (bucha Ø38 dentro de |X| 525)
Z_BRACO = 190.0           # eixo do braço e do pivô — horizontal  CRITÉRIO (ver nota 4)
BRACO = X_PIVO - XS       # 150 — braço efetivo pivô -> roda      CALC
H_BRACO, B_BRACO, E_BRACO = 40.0, 30.0, 3.0      # tubo retangular 40×30×3
X_BRACO = (XS - 10.0, X_PIVO + 22.0)             # 340 … 522 — extensão do tubo
Y_BRACO = (Y_FACE - E_PLACA - B_BRACO, Y_FACE - E_PLACA)       # 194 … 224
Z_BRACO_T = (Z_BRACO - H_BRACO / 2, Z_BRACO + H_BRACO / 2)     # 170 … 210
D_PIVO = 20.0             # eixo do pivô, h7                     CALC (flexão 26 MPa)
D_BUCHA, L_BUCHA = 34.0, 38.0       # alojamento da bucha (W-04), soldado atravessando o tubo
# 38 e não 44: com 44 o alojamento encostava nas orelhas da torre, que ficam em |Y| 188 e
# 230. Com 38 sobram 2 mm de folga de giro em cada lado — e é onde entra a arruela de
# encosto, se o ensaio mostrar que precisa.
D_ALOJ = 23.0             # alojamento H7 das duas buchas autolubrificantes Ø23/Ø20
E_ORELHA = 6.0            # orelhas da torre do pivô (W-05)     CALC (FS alto em 8)
Y_ORELHA = (Y_BRACO[0] - 6.0 - E_ORELHA, Y_BRACO[1] + 6.0)     # 182 e 230 (face interna)
E_BERCO_PIVO = 8.0
Z_BERCO_PIVO = (Z_QUADRO - E_CHAPA - E_BERCO_PIVO, Z_QUADRO - E_CHAPA)   # 238 … 248

# ---- fole e seu caminho de carga
MR_FOLE = 0.5                           # relação de movimento fole/roda   CRITÉRIO
R_FOLE = BRACO * MR_FOLE                # 75 — estação do fole no braço
X_FOLE = X_PIVO - R_FOLE                # 425
Y_FOLE = (Y_BRACO[0] + Y_BRACO[1]) / 2  # 209 — eixo do braço
D_FOLE = 88.0                           # Ø externo máximo do fole        REQUISITO
D_FOLE_EF = 66.0                        # Ø efetivo, área 3421 mm²        CALC
# A área sai da PRESSÃO DE PROJETO, não da estática. Com 2003 mm² (a primeira tentativa)
# a estática ficava confortável em 3,13 bar e a de projeto ia a 12,69 — acima de qualquer
# fole industrial pequeno. 3421 mm² põe a estática em 1,84 e a de projeto em 7,43, dentro
# do teto de 8. É o caso de carga raro que dimensiona, não o do dia a dia.
E_PRATO, D_PRATO = 8.0, 92.0            # prato articulado do fole (W-08)
D_PINO_PRATO = 12.0                     # pino do prato (W-09)
E_BERCO_FOLE = 10.0
Z_BERCO_FOLE = (ANEL_INF[1], ANEL_INF[1] + E_BERCO_FOLE)       # 280 … 290
H_FOLE = Z_BERCO_FOLE[0] - Z_BRACO_T[1]                        # 70 — altura instalada nominal
D_COLAR, E_COLAR, D_FLANGE_COLAR = 100.0, 3.0, 140.0           # colar de vedação (W-12)
D_PASSAGEM = 102.0                      # recorte da chapa de fundo para o fole
R_REBITE_COLAR = 60.0                   # círculo dos rebites da flange do colar
X_CORTE_FLANGE = 470.0                  # corte reto da flange, do lado do pivô (|X|)
# A flange do colar fica ABAIXO da chapa de fundo, e isso é geometria obrigatória, não
# escolha: acima dela o vão livre entre as travessas Q-03 (X 365) e Q-02 (X 493) é de
# 128 mm, e uma flange Ø140 colidiria com as duas. Por baixo não há nada.

# ---- curso
CURSO_TRABALHO = 25.0     # ± na roda, em qualquer altura selecionada   CRITÉRIO
AJUSTE_ALTURA = 30.0      # faixa de ajuste do vão livre: 150 -> 180    CRITÉRIO
CURSO_RODA = 2 * CURSO_TRABALHO + AJUSTE_ALTURA                # 80
CURSO_FOLE = CURSO_RODA * MR_FOLE                              # 40


def rolagem_max():
    """Rolagem máxima da carroceria, em graus — limitada pelo curso, não pela mola."""
    return math.degrees(math.atan(2 * CURSO_TRABALHO / BITOLA))


def furos_mpw():
    return [(90 + i * 360 / MPW_N_FUROS) for i in range(MPW_N_FUROS)]


def chapa_motor(xs, z_topo):
    """Perfil e furos da chapa de montagem do motor-roda, no plano X–Z.

    É a peça da sugestão 2.4 do fabricante, e na Rev H ela é em aço — não mais por
    preferência de material, mas porque passou a ser peça de suspensão: recebe a carga da
    roda a cada ondulação do terreno. Alumínio não tem limite de fadiga; aço tem.
    """
    # Disco completo em volta do cubo, e acima dele só o colo que recebe a sobreposição do
    # braço. A Rev F herdava daqui um retângulo cheio até o quadro, porque a chapa chegava
    # ao quadro; agora ela chega ao braço, 32 mm mais abaixo, e o resto era massa morta.
    x_colo = (XS - 10.0, XS + R_PLACA)
    z_ombro = Z_EIXO + R_PLACA * math.cos(math.asin((x_colo[0] - XS) / R_PLACA))
    perfil = [(xs + (x_colo[1] - XS), z_topo), (xs + (x_colo[0] - XS), z_topo),
              (xs + (x_colo[0] - XS), z_ombro)]
    for i in range(1, 48):
        t = math.pi - math.asin((x_colo[0] - XS) / R_PLACA) + \
            (math.pi + 2 * math.asin((x_colo[0] - XS) / R_PLACA)) * i / 48
        perfil.append((xs + R_PLACA * math.cos(t), Z_EIXO + R_PLACA * math.sin(t)))
    perfil.append((xs + R_PLACA, z_ombro))
    furos = [(xs, Z_EIXO, D_BORE)]
    for ang in furos_mpw():
        t = math.radians(ang)
        furos.append((xs + MPW_PCD / 2 * math.cos(t), Z_EIXO + MPW_PCD / 2 * math.sin(t), 4.5))
    return perfil, furos


def braco(sx, lado):
    """Um braço completo: W-01 a W-04 e W-08/W-09. Desenhado no lado +Y."""
    ps = []
    xp = sx * X_PIVO
    xr = sx * XS
    xb = tuple(sorted((sx * X_BRACO[0], sx * X_BRACO[1])))
    yb0, yb1 = Y_BRACO
    zb0, zb1 = Z_BRACO_T

    # W-01 — tubo do braço. O rasgo 24 × 34 na parede superior (alojamento do prato W-08)
    # é operação de usinagem cotada na folha 08; não entra no prisma, e por isso a massa
    # calculada fica ~19 g acima da real por braço.
    ps.append(tubo('W-01', 'x', xb[0], xb[1], yb0, yb1, zb0, zb1, E_BRACO, mat='aco'))

    # W-02 — chapa de montagem do motor-roda, sobreposta à parede externa do braço
    perfil, furos = chapa_motor(xr, zb1)
    p = chapa('W-02', 'y', Y_FACE - E_PLACA, Y_FACE, perfil, furos, mat='aco')
    p.curvo = True
    ps.append(p)

    # W-03 — tampa-gusset da ponta interna do braço. Faz duas coisas numa peça: FECHA o tubo
    # (água e poeira não entram) e amarra as paredes do braço à chapa W-02 na ponta da
    # sobreposição, que é onde o filete termina. A Rev H tinha aqui dois gussets soltos no
    # plano errado — não encostavam na chapa, e por isso não faziam nada.
    xc = sx * (X_BRACO[0] - 6.0)
    ps.append(chapa('W-03', 'x', min(xc, xc + sx * 6.0), max(xc, xc + sx * 6.0),
                    retangulo(yb0, yb1, zb0, zb1), mat='aco'))

    # W-04 — alojamento da bucha do pivô, soldado atravessando o tubo
    yc = (yb0 + yb1) / 2
    ps.append(cilindro('W-04', 'y', yc - L_BUCHA / 2, yc + L_BUCHA / 2, xp, Z_BRACO,
                       D_BUCHA, furo=D_ALOJ, mat='aco', estilo='solid'))

    # W-08 — prato articulado do fole: disco alojado no rasgo e duas orelhas até o pino
    xf = sx * X_FOLE
    ps.append(cilindro('W-08', 'z', zb1 - E_PRATO, zb1, xf, Y_FOLE, D_PRATO,
                       mat='aco', estilo='solid'))
    # As duas orelhas ficam DENTRO do tubo, entre as faces internas das paredes (|Y| 197 e
    # 221). Com elas em 189 e 221 a de fora passava 5 mm além da parede externa e encostava
    # na chapa W-02 — 1 mm de interpenetração, achado pela conferência de `espaco.py`.
    for yo in (Y_FOLE - 12.0, Y_FOLE + 4.0):
        perf = retangulo(xf - 14.0, xf + 14.0, Z_BRACO - 8.0, zb1 - E_PRATO)
        ps.append(chapa('W-09', 'y', yo, yo + 8.0, perf, [(xf, Z_BRACO, D_PINO_PRATO)], mat='aco'))

    # W-09 — pino do prato, atravessando as paredes do tubo e as duas orelhas
    ps.append(cilindro('W-10', 'y', yb0 - 4.0, yb1 + 4.0, xf, Z_BRACO, D_PINO_PRATO,
                       mat='inox', estilo='solid'))

    if lado < 0:
        ps = [espelha_y(q) for q in ps]
    for q in ps:
        q.grupo = 'W'
    return ps


def torre_pivo(sx, lado):
    """W-05 e W-06: as duas orelhas e o berço que levam o pivô ao anel inferior."""
    ps = []
    xp = sx * X_PIVO
    z_ber0, z_ber1 = Z_BERCO_PIVO
    perf = [(xp + 22.0, z_ber0), (xp + 22.0, Z_BRACO)]
    for i in range(1, 32):
        t = -math.pi * i / 32
        perf.append((xp + 22.0 * math.cos(t), Z_BRACO + 22.0 * math.sin(t)))
    perf += [(xp - 22.0, Z_BRACO), (xp - 22.0, z_ber0)]
    for y0 in Y_ORELHA:
        q = chapa('W-05', 'y', y0, y0 + E_ORELHA, perf, [(xp, Z_BRACO, D_PIVO)], mat='aco')
        q.curvo = True
        ps.append(q)
    # W-07 — eixo do pivô, atravessando as duas orelhas e as buchas do braço
    ps.append(cilindro('W-07', 'y', Y_ORELHA[0] - 3.0, Y_ORELHA[1] + E_ORELHA + 3.0,
                       xp, Z_BRACO, D_PIVO, mat='inox', estilo='solid'))
    fb = [(sx * X_CANTO, y, 8.5) for y in Y_FUROS_SUSP]
    ps.append(chapa('W-06', 'z', z_ber0, z_ber1,
                    retangulo(min(xp - sx * 24.0, xp + sx * 22.0), max(xp - sx * 24.0, xp + sx * 22.0),
                              Y_FUROS_SUSP[0] - 12.0, Y_FUROS_SUSP[1] + 12.0), fb, mat='aco'))
    if lado < 0:
        ps = [espelha_y(q) for q in ps]
    for q in ps:
        q.grupo = 'W'
    return ps


def berco_fole(sx, lado):
    """W-11 e W-12: o berço sobre o anel inferior e o colar que veda a passagem."""
    ps = []
    z0, z1 = Z_BERCO_FOLE
    xa, xb = tuple(sorted((sx * (XS - 12.0), sx * (X_CANTO + 12.0))))
    fb = [(sx * x, y, 8.5) for x in (XS, X_CANTO) for y in Y_FUROS_SUSP]
    fb += [(sx * X_FOLE, Y_FOLE, 14.0), (sx * (X_FOLE - 26.0), Y_FOLE, 12.0)]
    ps.append(chapa('W-11', 'z', z0, z1,
                    retangulo(xa, xb, Y_FUROS_SUSP[0] - 12.0, Y_FUROS_SUSP[1] + 12.0), fb))
    ps.append(cilindro('W-12', 'z', Z_QUADRO - E_CHAPA, z0, sx * X_FOLE, Y_FOLE, D_COLAR,
                       furo=D_COLAR - 2 * E_COLAR, estilo='solid'))
    # A flange é um CÍRCULO CORTADO, e o corte tem endereço: do lado do pivô ela encontraria
    # o berço W-06, que começa em |X| 476. Um Ø140 inteiro iria a 495. O corte reto em |X| 470
    # resolve sem mexer no diâmetro do colar, que é o que o fole precisa.
    x_corte = sx * X_CORTE_FLANGE
    perfil_flange = _clip(circulo(sx * X_FOLE, Y_FOLE, D_FLANGE_COLAR, 64), 0,
                          x_corte, 'le' if sx > 0 else 'ge')
    furos_flange = [(sx * X_FOLE, Y_FOLE, D_COLAR - 2 * E_COLAR)]
    for a in (0, 60, 120, 180, 240, 300):
        fx = sx * X_FOLE + sx * R_REBITE_COLAR * math.cos(math.radians(a))
        fy = Y_FOLE + R_REBITE_COLAR * math.sin(math.radians(a))
        if (fx <= x_corte - 7.0) if sx > 0 else (fx >= x_corte + 7.0):
            furos_flange.append((fx, fy, 4.9))
    q = chapa('W-13', 'z', Z_QUADRO - E_CHAPA - 4.0, Z_QUADRO - E_CHAPA,
                perfil_flange, furos_flange)
    q.curvo = True
    ps.append(q)
    if lado < 0:
        ps = [espelha_y(q) for q in ps]
    for q in ps:
        q.grupo = 'W'
    return ps


def fole_ref(sx, lado):
    """O fole W-10 em linha fantasma: é comprado, e o envelope é requisito, não cota."""
    ps = [cilindro('W-15', 'z', Z_BRACO_T[1], Z_BERCO_FOLE[0], sx * X_FOLE, Y_FOLE, D_FOLE)]
    if lado < 0:
        ps = [espelha_y(q) for q in ps]
    for q in ps:
        q.grupo = 'W'
    return ps


def suspensao():
    ps = []
    for sx in (1, -1):
        for lado in (1, -1):
            ps += braco(sx, lado) + torre_pivo(sx, lado) + berco_fole(sx, lado)
    return ps


def suspensao_ref():
    ps = []
    for sx in (1, -1):
        for lado in (1, -1):
            ps += fole_ref(sx, lado)
    return ps


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
K06 = (-55.0, 55.0, -250.0, 250.0)                      # faixa central (X, Y) — livre da luva do mastro
# Encolheu de 256 para 250 em |Y| no V4: a luva do mastro engrossou de Ø34 para Ø42 e
# passou a ocupar |Y| 255…297. Com 256 a faixa encostava nela.


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
        # berço do terminal satelital T-07 (V4): a tampa recebia a antena GNSS e o E-STOP, mas não
        # tinha os furos do T-07 — o berço não tinha onde ser parafusado nem por onde passar o cabo.
        fu += [(X_SAT + dx, dy, D_FOLGA_M5) for dx in (-95.0, 0.0, 95.0) for dy in (-105.0, 105.0)]
        fu.append((X_SAT, 0.0, 32.0))
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
Y_MASTRO = 276.0                 # eixo do mastro (baseline ±300; 276 para a luva Ø42 caber em 600)
E_REF_M = 6.0                    # chapa de reforço sob a luva
Z_REF_M = (Z_DECK, Z_DECK + E_REF_M)        # 340 → 346
D_LUVA, E_LUVA, L_LUVA = 42.0, 5.0, 180.0   # luva Ø42×5 (era Ø34×4,5 até o V3)
Z_LUVA = (Z_REF_M[1], Z_REF_M[1] + L_LUVA)  # 346 → 526
D_MASTRO, E_MASTRO = 32.0, 3.0              # haste Ø32×3 (V3: Ø25×2; V4 inicial: Ø32×2)
D_BAINHA = 36.0                             # bainha anti-galho (era Ø29)
# O mastro ENGROSSOU DUAS VEZES, e nenhuma foi por estética.
#
# 1) Ø25×2 -> Ø32×2. O tubo herdado da baseline dá 1ª frequência de flexão de 6,53 Hz
#    contra o requisito de 7,5 Hz da folha 25 (caso 6 do FEA, aberto desde a Rev E e nunca
#    verificado) — e contra uma excitação de terreno estimada em 5,60 Hz a 1,4 m/s. Razão
#    1,17: praticamente ressonância.
# 2) Ø32×2 -> Ø32×3. O Ø32×2 foi dimensionado para três câmeras por mastro. O mastro que
#    o projeto descreve tem MAIS: dois postos térmicos removíveis em alturas
#    intermediárias e a antena GNSS no topo. Com essa carga o Ø32×2 cai para 7,2 Hz (com
#    antena de 0,3 kg) — abaixo do requisito. O diâmetro externo fica em 32 porque ele
#    entra na luva Ø42×5 (furo 32) e a luva não pode crescer: já está a 297 mm do eixo do
#    rover e o envelope externo é 600. Só a parede aumenta. Ver ../revisao-h/mastro.py.
#
# A luva acompanha o 1º passo (Ø42×5) e o eixo recua para |Y| 276: a luva Ø42 em 280
# chegaria a 301, fora do envelope externo de 600.
CAMERAS_Z = (450.0, 1000.0, 1540.0)
# Cotas NOMINAIS de montagem, não mais cotas de furação: no V4 as câmeras vão em
# braçadeira deslizante (grupo T) e a altura é ajustável em todo o mastro. São a posição
# de entrega e a referência de calibração de fábrica. Ver ../revisao-h/modular.py.
# Posições NOMINAIS dos módulos térmicos removíveis, a meio caminho entre dois andares de
# OAK-D (ponto médio de 450/1000 e de 1000/1540). São opcionais — o mastro é dimensionado
# com eles montados, e sem eles só fica mais leve.
Z_TERMICA = (725.0, 1270.0)
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


# Adaptador de antena GNSS no topo do mastro (T-10). A antena do esboço do projeto fica
# no alto do mastro, com vista livre do céu; o V3 só previa a antena na tampa (N-01).
# É PROVISÃO: nenhuma antena foi escolhida. O envelope é o mesmo da N-01 (D_ANTENA ×
# H_ANTENA, A VALIDAR) e a interface é a rosca de 5/8"-11 UNC, que é o padrão de
# topografia GNSS — também A VALIDAR com o modelo escolhido.
L_ENCAIXE_ANTENA = 40.0       # quanto do adaptador entra no tubo
H_TOPO_ANTENA = 20.0          # quanto sai acima do topo do tubo
D_ENCAIXE_ANTENA = D_MASTRO - 2 * E_MASTRO       # encaixa no furo do tubo
D_CABO_ANTENA = 10.0          # furo axial para o cabo coaxial
Z_BASE_ANTENA = Z_TOTAL + H_TOPO_ANTENA          # 1802: plano de apoio da antena


def _faixas_bainha():
    """Trechos da bainha M-11: interrompida em TODO posto, e só nos postos acima da luva.

    A braçadeira aperta o tubo, não o plástico — por isso a bainha para 40 mm antes e
    começa 40 mm depois de cada posto, incluindo os dois térmicos.
    """
    zs = sorted(z for z in tuple(CAMERAS_Z) + tuple(Z_TERMICA) if z > Z_LUVA[1] + 50)
    pts = [Z_LUVA[1] + 10] + [v for z in zs for v in (z - 40, z + 40)] + [Z_TOTAL]
    return [(pts[i], pts[i + 1]) for i in range(0, len(pts), 2) if pts[i + 1] - pts[i] > 1.0]


def mastro(antena=()):
    """Haste, bainha e topo — fornecimento opcional (Parte B).

    `antena` lista os lados (+1 esquerdo, −1 direito) cujo topo recebe o adaptador T-10 da
    antena GNSS em vez da ponta cônica M-12. Vazio = configuração de entrega.
    """
    ps = []
    for sy in (1, -1):
        y = sy * Y_MASTRO
        ps.append(cilindro('M-10', 'z', Z_REF_M[1], Z_TOTAL, 0.0, y, D_MASTRO, furo=D_MASTRO - 2 * E_MASTRO,
                           estilo='solid'))
        for (za, zb) in _faixas_bainha():
            ps.append(cilindro('M-11', 'z', za, zb, 0.0, y, D_BAINHA, furo=D_MASTRO, mat='borracha',
                               estilo='solid'))
        if sy in antena:
            ps.append(cilindro('T-10', 'z', Z_TOTAL - L_ENCAIXE_ANTENA, Z_TOTAL + H_TOPO_ANTENA, 0.0, y,
                               D_ENCAIXE_ANTENA, furo=D_CABO_ANTENA, estilo='solid'))
            ps[-1].grupo = 'T'
        else:
            ps.append(cilindro('M-12', 'z', Z_TOTAL, Z_TOTAL + 40, 0.0, y, D_BAINHA, furo=None,
                               mat='borracha', estilo='solid'))
    return ps


def antena_mastro_ref(lado=1):
    """A antena GNSS sobre o adaptador T-10, em linha fantasma: envelope, não componente."""
    return [cilindro('R-06', 'z', Z_BASE_ANTENA, Z_BASE_ANTENA + H_ANTENA, 0.0, lado * Y_MASTRO, D_ANTENA)]


# ===================== sistema modular de sensores — interface VMS (grupo T) ==
# NOVO NO V4. Substitui a chapa M-20 do V3, que era furação fixa em cota fixa, com o
# padrão de furos da câmera marcado "(a validar)" no próprio código.
#
# O que torna um sensor modular não é poder desparafusá-lo. É poder **repô-lo no mesmo
# lugar**. Numa câmera, a matriz extrínseca — onde ela está e para onde aponta — é medida
# na calibração e usada pela fusão como constante. Se a troca de uma câmera desloca a
# próxima em 0,7°, a calibração morre junto com a peça trocada, e o técnico que trocou a
# câmera em campo acabou de degradar a navegação sem saber.
#
# Por isso a interface VMS-60 se apoia em PINO, não em parafuso:
#
#   * pino de referência Ø8 H7/h6 no centro  -> posição
#   * pino anti-giro Ø6 H7/h6 a 26 mm        -> orientação
#   * 4 parafusos M5 em 56 × 36              -> aperto, e só
#
# Folga do ajuste H7/h6 em Ø8: 0,022 mm no pior caso. Sobre os 26 mm entre os dois pinos
# dá 0,85 mrad = 0,049° de repetibilidade angular. Com parafuso em furo de folga Ø5,5
# seriam 0,5 mm sobre 26 mm = 19 mrad = 1,1°. A 10 m de distância a diferença é de 8,5 mm
# contra 190 mm. É esse fator de 22 que separa "removível" de "modular".
#
# Três camadas, e só a do meio é padrão:
#
#   1. POSIÇÃO   braçadeira T-01 — desliza e gira no mastro, trava por 2 × M6
#   2. INTERFACE prato T-02 — face VMS-60, inclinação indexada por pino em passo de 10°
#   3. ADAPTAÇÃO T-03 (OAK-D), T-04 (térmica), … — VMS-60 de um lado, o sensor do outro
#
# Trocar a câmera mexe só na camada 3: posição e ângulo ficam intactos e a extrínseca
# sobrevive. Mudar altura ou azimute mexe na camada 1 e **exige recalibração** — e o
# software tem de saber disso, o que é requisito de `modular.REQUISITOS_SOFTWARE`.
#
# O cálculo completo — repetibilidade, campo de visão, proteção, energia e banda — está em
# ../revisao-h/modular.py.

VMS_FUROS = (56.0, 36.0)      # retângulo dos 4 parafusos M5 do padrão VMS-60
VMS_PRATO = (72.0, 64.0)      # envelope do prato de interface
D_MACHO_M5 = 4.2              # furo para macho M5 (rosca) — a face fixa do VMS (prato T-02, berços T-06/T-09)
D_PASSAGEM_M5 = 5.5           # furo de passagem M5 — a face móvel (adaptadores T-03/T-04)
D_PINO_REF, D_PINO_GIRO = 8.0, 6.0
Z_PINO_GIRO = 26.0            # pino anti-giro acima do centro
E_PRATO_VMS, E_ADAPTADOR = 10.0, 6.0
E_BRACADEIRA = 12.0           # metade da braçadeira: chapa usinada
L_BRACADEIRA, H_BRACADEIRA = 60.0, 50.0
R_INDICE = 26.0               # raio do círculo de furos de índice de inclinação
PASSO_INDICE_DEG = 10.0
N_INDICE = 7                  # −30° a +30°
E_PROTETOR = 6.0              # protetor sacrificial em UHMW-PE
AVANCO_PROTETOR = 40.0        # quanto o protetor avança à frente da lente
ALTURA_PROTETOR = 40.0        # altura do protetor sobre o eixo óptico (campo livre: 34)
PROFUNDIDADE_PROTETOR = 46.0  # quanto o protetor se estende para fora do adaptador (em Y)
# Envelope que o módulo térmico removível PODE ocupar: dentro do prato (72 × 64) e sob a
# sobrancelha T-05 (46 de profundidade). É REQUISITO DERIVADO do que já está desenhado, não
# a dimensão de nenhuma câmera — nenhum modelo foi escolhido (P-30).
ENVELOPE_TERMICA = (VMS_PRATO[0], VMS_PRATO[1], PROFUNDIDADE_PROTETOR)

X_CAM_FRENTE = 509.0          # câmera frontal, sob o nariz do chassi
X_CAM_TRAS = -509.0           # câmera traseira, simétrica
Z_CAM_EXTREMIDADE = 210.0     # eixo óptico das câmeras de extremidade
# As duas câmeras de extremidade ficam SOB o chassi, não na carenagem, e a razão é que não
# havia lugar na carenagem: entre os dois anéis do quadro (Z 280…310) sobram 30 mm, e a
# face VMS tem 64. Na altura de 210 mm, com a chapa de fundo por cima e o vão livre por
# baixo, a lente fica recuada e protegida por construção — sem nenhuma grade à frente
# dela, que é o que o V4 exige. É também a posição que o documento técnico do V3 já
# chamava de "câmera frontal baixa", só que lá ela não existia no desenho.

# Provisão para terminal de comunicação por satélite. NÃO é um componente escolhido: é
# envelope e interface, como o fole da suspensão. Ver `modular.REQUISITOS_SATELITE`.
SAT_ENVELOPE = (220.0, 240.0, 40.0)   # L × W × H máximos que o berço aceita   REQUISITO
X_SAT, Z_SAT = -175.0, Z_TAMPA        # sobre a tampa traseira
# O envelope é 220 × 240, e não o que se gostaria, porque é o que sobra. O deck já tem o
# suporte do LiDAR (G-06, |X| 215…345), a antena GNSS (N-01, |X| 295…405), a faixa central
# K-06 (|X| ≤ 55) e o E-STOP (|X| 420…500). O único vão livre de ponta a ponta é
# X −290…−60, na tampa traseira.
#
# CONSEQUÊNCIA QUE PRECISA SER DITA: um terminal de ~300 × 260 mm — que é a classe do
# Starlink Mini — NÃO CABE nesta provisão. Caber exigiria deslocar o suporte do LiDAR ou
# a antena GNSS, que é decisão de projeto, não de desenho. A provisão desenhada aceita
# terminal de até 220 × 240 × 40. Ver `modular.REQUISITOS_SATELITE`.
E_BERCO_SAT = 4.0


def furos_vms(cx, cz, d_parafuso=D_PASSAGEM_M5):
    """Os furos do padrão VMS-60, no plano da face. Um só lugar define o padrão.

    `d_parafuso` é Ø5,5 (passagem) na face MÓVEL — adaptador — e Ø4,2 (macho M5) na face
    FIXA — prato T-02. O parafuso, imperdível ou de cabeça sextavada interna, rosqueia no
    prato: é assim que o módulo térmico sai à mão e a OAK-D sai com chave Allen.
    """
    f = [(cx + sx * VMS_FUROS[0] / 2, cz + sz * VMS_FUROS[1] / 2, d_parafuso)
         for sx in (1, -1) for sz in (1, -1)]
    f.append((cx, cz, D_PINO_REF))
    f.append((cx, cz + Z_PINO_GIRO, D_PINO_GIRO))
    return f


def posto_vms(cx, cz, sy, base='bracadeira', d_tubo=None, variante='oakd'):
    """Um posto de sensor completo: braçadeira (ou berço), prato VMS, adaptador e protetor.

    `cx`, `cz` são o centro da face VMS no plano do perfil; `sy` o lado (+1 esquerdo).

    `variante='oakd'`: câmera FIXA e calibrada — adaptador T-03, com a furação da OAK-D.
    `variante='termica'`: módulo REMOVÍVEL — adaptador T-04, com parafusos imperdíveis de
    aperto manual; a furação do sensor depende do modelo (P-30) e não é desenhada.
    """
    ps = []
    y_face = sy * (Y_MASTRO + (d_tubo or D_MASTRO) / 2)

    if base == 'bracadeira':
        d = d_tubo or D_MASTRO
        for lado in (1, -1):          # as duas metades
            y0 = sy * (Y_MASTRO + lado * d / 2)
            ya, yb = sorted((y0, y0 + lado * sy * E_BRACADEIRA))
            furos = [(cx + sx * 22.0, cz + 0.0, D_FOLGA_M6) for sx in (1, -1)]
            ps.append(chapa('T-01', 'y', ya, yb,
                            retangulo(cx - L_BRACADEIRA / 2, cx + L_BRACADEIRA / 2,
                                      cz - H_BRACADEIRA / 2, cz + H_BRACADEIRA / 2), furos))
        y_face = sy * (Y_MASTRO + d / 2 + E_BRACADEIRA)

    # T-02 — prato de interface VMS, com o círculo de furos de índice de inclinação
    idx = [(cx + R_INDICE * math.sin(math.radians(a)),
            cz + R_INDICE * math.cos(math.radians(a)), D_PINO_GIRO)
           for a in [(-(N_INDICE - 1) / 2 + i) * PASSO_INDICE_DEG for i in range(N_INDICE)]]
    ya, yb = sorted((y_face, y_face + sy * E_PRATO_VMS))
    ps.append(chapa('T-02', 'y', ya, yb,
                    ret_arred(cx - VMS_PRATO[0] / 2, cx + VMS_PRATO[0] / 2,
                              cz - VMS_PRATO[1] / 2, cz + VMS_PRATO[1] / 2, 8),
                    furos_vms(cx, cz, D_MACHO_M5) + idx + [(cx, cz - R_INDICE, 8.5)]))

    # T-03 — adaptador do sensor, a única peça que muda quando a câmera muda.
    # T-04 é o mesmo papel para o módulo térmico removível, sem furação de sensor.
    y2 = y_face + sy * E_PRATO_VMS
    ya, yb = sorted((y2, y2 + sy * E_ADAPTADOR))
    if variante == 'termica':
        furos_cam, item_adap = [], 'T-04'
    else:
        furos_cam = [(cx + sx * 25.0, cz + sz * 20.0, 3.4) for sx in (1, -1) for sz in (1, -1)]
        item_adap = 'T-03'
    ps.append(chapa(item_adap, 'y', ya, yb,
                    ret_arred(cx - VMS_PRATO[0] / 2, cx + VMS_PRATO[0] / 2,
                              cz - VMS_PRATO[1] / 2, cz + VMS_PRATO[1] / 2, 8),
                    furos_vms(cx, cz) + furos_cam))

    # T-05 — protetor sacrificial: sobrancelha acima da lente, fora do campo de visão.
    # Extrudado em Z, que é a espessura real da chapa: é assim que ele é cortado.
    y3 = y2 + sy * E_ADAPTADOR
    ya, yb = sorted((y3, y3 + sy * PROFUNDIDADE_PROTETOR))
    ps.append(chapa('T-05', 'z', cz + ALTURA_PROTETOR - E_PROTETOR, cz + ALTURA_PROTETOR,
                    ret_arred(cx - VMS_PRATO[0] / 2,
                              cx + VMS_PRATO[0] / 2 + AVANCO_PROTETOR, ya, yb, 8),
                    [(cx + sx * 25.0, (ya + yb) / 2, 4.5) for sx in (1, -1)],
                    mat='uhmw'))

    for q in ps:
        q.grupo = 'T'
    return ps


def suportes_camera():
    """Os seis postos de câmera dos mastros, em braçadeira deslizante.

    Substitui a M-20 do V3. A cota de CAMERAS_Z passa a ser posição de entrega: a
    braçadeira desliza em todo o mastro, da saída da luva ao topo.
    """
    ps = []
    for sy in (1, -1):
        for z in CAMERAS_Z:
            d = D_LUVA if z < Z_LUVA[1] else D_MASTRO
            ps += posto_vms(0.0, z, sy, base='bracadeira', d_tubo=d)
    return ps


def suportes_termicos():
    """Os quatro postos térmicos REMOVÍVEIS: dois por mastro, a meio caminho entre os andares.

    Mesma braçadeira T-01, mesmo prato T-02, mesma face VMS-60 e mesmo protetor T-05 dos
    postos de OAK-D. O que muda é o adaptador (T-04) e o fato de o módulo sair com a mão.
    Opcionais — mas o mastro é calculado com eles montados.
    """
    ps = []
    for sy in (1, -1):
        for z in Z_TERMICA:
            ps += posto_vms(0.0, z, sy, base='bracadeira', d_tubo=D_MASTRO, variante='termica')
    return ps


def mastro_completo(antena=(1,)):
    """O mastro como o projeto o descreve: 3 OAK-D + 2 térmicas removíveis + antena no topo.

    É a configuração de máxima carga, a que o cálculo do mastro verifica. Só as peças
    físicas; a antena, que não é peça fornecida, vem de `antena_mastro_ref`.
    """
    return mastro(antena) + base_mastro() + suportes_camera() + suportes_termicos()


def berco_vms_extremidade():
    """T-06: os berços das câmeras frontal e traseira, nas carenagens K-02 e K-03.

    No V3 a câmera frontal estava DECLARADA nos documentos e não existia no desenho: a
    K-02 tem 9 furos de porca-rebite e 2 de farol, e nada mais. A traseira não existia nem
    nos documentos. As duas agora têm berço, e o berço apresenta a mesma face VMS-60 dos
    postos do mastro — é o que permite trocar uma câmera de lugar sem adaptador novo.
    """
    ps = []
    for (sx, x) in ((1, X_CAM_FRENTE), (-1, X_CAM_TRAS)):
        # chapa vertical sob a chapa de fundo, face VMS voltada para fora
        x0, x1 = sorted((x, x + sx * 4.0))
        ps.append(chapa('T-06', 'x', x0, x1,
                        ret_arred(-VMS_PRATO[0] / 2, VMS_PRATO[0] / 2,
                                  Z_CAM_EXTREMIDADE - VMS_PRATO[1] / 2,
                                  Z_CAM_EXTREMIDADE + VMS_PRATO[1] / 2, 8),
                        [(sy * VMS_FUROS[0] / 2, Z_CAM_EXTREMIDADE + sz * VMS_FUROS[1] / 2, 5.5)
                         for sy in (1, -1) for sz in (1, -1)]
                        + [(0.0, Z_CAM_EXTREMIDADE, D_PINO_REF),
                           (0.0, Z_CAM_EXTREMIDADE + Z_PINO_GIRO, D_PINO_GIRO)]))
        xa, xb = sorted((x + sx * 4.0, x + sx * 4.0 + sx * E_ADAPTADOR))
        furos_cam = [(sy * 25.0, Z_CAM_EXTREMIDADE + sz * 20.0, 3.4)
                     for sy in (1, -1) for sz in (1, -1)]
        ps.append(chapa('T-03', 'x', xa, xb,
                        ret_arred(-VMS_PRATO[0] / 2, VMS_PRATO[0] / 2,
                                  Z_CAM_EXTREMIDADE - VMS_PRATO[1] / 2,
                                  Z_CAM_EXTREMIDADE + VMS_PRATO[1] / 2, 8),
                        [(sy * VMS_FUROS[0] / 2, Z_CAM_EXTREMIDADE + sz * VMS_FUROS[1] / 2, 5.5)
                         for sy in (1, -1) for sz in (1, -1)]
                        + [(0.0, Z_CAM_EXTREMIDADE, D_PINO_REF),
                           (0.0, Z_CAM_EXTREMIDADE + Z_PINO_GIRO, D_PINO_GIRO)] + furos_cam))
    for q in ps:
        q.grupo = 'T'
    return ps


def berco_raiz():
    """T-09: berço VMS da câmera de raiz, horizontal, sobre a janela N-04.

    A câmera de raiz olha para BAIXO, através da janela de policarbonato. Por isso a face
    VMS dela é horizontal e não inclinada como a chapa N-07 — e por isso ela fica DENTRO
    do compartimento, acima da janela: trocar a câmera não mexe na vedação da janela, que
    é o que separa o compartimento da lavoura.
    """
    cx = (JANELA_RAIZ[0] + JANELA_RAIZ[1]) / 2
    z0 = 298.0
    furos = [(cx + sx * VMS_FUROS[0] / 2, sz * VMS_FUROS[1] / 2, D_PASSAGEM_M5)
             for sx in (1, -1) for sz in (1, -1)]
    furos += [(cx, 0.0, D_PINO_REF), (cx, Z_PINO_GIRO, D_PINO_GIRO)]
    ps = [chapa('T-09', 'z', z0, z0 + E_PRATO_VMS,
                ret_arred(cx - VMS_PRATO[0] / 2, cx + VMS_PRATO[0] / 2,
                          -VMS_PRATO[1] / 2, VMS_PRATO[1] / 2, 8), furos)]
    furos_cam = [(cx + sx * 25.0, sz * 20.0, 3.4) for sx in (1, -1) for sz in (1, -1)]
    ps.append(chapa('T-03', 'z', z0 - E_ADAPTADOR, z0,
                    ret_arred(cx - VMS_PRATO[0] / 2, cx + VMS_PRATO[0] / 2,
                              -VMS_PRATO[1] / 2, VMS_PRATO[1] / 2, 8),
                    furos + furos_cam))
    for q in ps:
        q.grupo = 'T'
    return ps


def berco_satelite():
    """T-07: berço do terminal de comunicação por satélite — PROVISÃO, não componente.

    Nenhum terminal foi escolhido, e o V3 não tinha provisão nenhuma: a busca por
    "Starlink" em todo o projeto dava zero. O que entra aqui é o que entrou para o fole da
    suspensão — **a interface, com o envelope como requisito**. Qualquer terminal que
    caiba em `SAT_ENVELOPE` monta sem alterar desenho.

    O berço fica sobre a tampa dianteira, que é a superfície plana com vista livre ao céu
    e sem sombra de mastro. A massa e o consumo estão no orçamento de `modular`.
    """
    furos = [(X_SAT + dx, dy, D_FOLGA_M5)
             for dx in (-95.0, 0.0, 95.0) for dy in (-105.0, 105.0)]
    furos += [(X_SAT, 0.0, 32.0)]        # passagem do cabo, com passa-cabo
    ps = [chapa('T-07', 'z', Z_SAT, Z_SAT + E_BERCO_SAT,
                ret_arred(X_SAT - 115.0, X_SAT + 115.0, -125.0, 125.0, 12), furos,
                mat='5052')]
    for q in ps:
        q.grupo = 'T'
    return ps


def satelite_ref():
    """O terminal em linha fantasma: envelope de requisito, não peça fornecida."""
    l, w, h = SAT_ENVELOPE
    p = chapa('T-08', 'z', Z_SAT + E_BERCO_SAT, Z_SAT + E_BERCO_SAT + h,
              retangulo(X_SAT - l / 2, X_SAT + l / 2, -w / 2, w / 2), estilo='ref')
    p.grupo = 'T'
    return [p]


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
    # Rev H: a E-02 encolheu. Ela ia de |Y| 105 a 250 e colidia frontalmente com o colar
    # do fole (|Y| 159…259). A faixa que sobra é 100…152, entre a janela da câmera de raiz
    # (|Y| ≤ 95) e o colar. É perda real de área de bandeja, contabilizada em
    # ../revisao-h/espaco.py — e é o preço de ter suspensão.
    for sx in (1, -1):
        x0, x1 = sorted((sx * 368.0, sx * 490.0))
        for s in (1, -1):
            y0, y1 = sorted((s * 100.0, s * 152.0))
            ps.append(chapa('E-02', 'z', Z_QUADRO, Z_QUADRO + E_BANDEJA, retangulo(x0, x1, y0, y1),
                            [(sx * 400.0, s * 125.0, 7.0), (sx * 470.0, s * 125.0, 7.0)], mat='5052'))
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


# A carenagem anti-galho N-09 do V3 FOI RETIRADA no V4. Ela era um nariz de UHMW colado à
# chapa M-20, dimensionado por semelhança e não por campo de visão, e ocupava exatamente o
# lugar que o adaptador T-03 agora precisa. Quem faz o serviço dela é o protetor T-05 do
# posto VMS, que é sacrificial, substituível com dois parafusos e — isto é o que mudou —
# dimensionado a partir do campo de visão declarado da câmera, em `modular.protecao`.


def interfaces_sensores():
    return suporte_gnss() + berco_imu() + visao_raiz() + suporte_led()


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
    'W-01': dict(nome='Braço longitudinal', desc=f'Tubo ret. 40×30×3 × {_n(X_BRACO[1] - X_BRACO[0])}',
                 mat='Aço 1020', origem='NOVO'),
    'W-02': dict(nome='Chapa de montagem do motor-roda', desc='Chapa 124×148×10', mat='Aço A36',
                 origem='NOVO'),
    'W-03': dict(nome='Tampa-gusset da ponta do braço', desc='Chapa 40×40×6', mat='Aço A36',
                 origem='NOVO'),
    'W-04': dict(nome='Alojamento da bucha do pivô', desc='Barra Ø34, furo Ø23 H7 × 44', mat='Aço 1045',
                 origem='NOVO'),
    'W-05': dict(nome='Orelha da torre do pivô', desc='Chapa 44×70×6, furo Ø20 H7', mat='Aço A36',
                 origem='NOVO'),
    'W-06': dict(nome='Berço do pivô', desc='Chapa 46×106×8', mat='Aço A36', origem='NOVO'),
    'W-07': dict(nome='Eixo do pivô', desc='Barra Ø20 h7 × 66, 2 ran. anéis', mat='Inox 304', origem='NOVO'),
    'W-08': dict(nome='Disco do prato do fole', desc=f'Disco Ø{_n(D_PRATO)}×{_n(E_PRATO)}, M12 central',
                 mat='Aço A36', origem='NOVO'),
    'W-09': dict(nome='Orelha do prato do fole', desc='Chapa 28×26×8, furo Ø12 H7', mat='Aço A36',
                 origem='NOVO'),
    'W-10': dict(nome='Pino do prato', desc='Barra Ø12 h7 × 42', mat='Inox 304', origem='NOVO'),
    'W-11': dict(nome='Berço do fole', desc='Chapa 180×106×10', mat='Al 6061-T6', origem='NOVO'),
    'W-12': dict(nome='Tubo do colar de vedação', desc=f'Tubo Ø{_n(D_COLAR)}×{_n(E_COLAR)} × 32',
                 mat='Al 6061-T6', origem='NOVO'),
    'W-13': dict(nome='Flange do colar', desc=f'Chapa Ø{_n(D_FLANGE_COLAR)}×4, cortada em |X| 470',
                 mat='Al 6061-T6', origem='NOVO'),
    'W-14': dict(nome='Limitador de extensão', desc='Cabo Ø4 × 112 com dois terminais de olhal',
                 mat='Inox 304', origem='NOVO'),
    'W-15': dict(nome='Mola pneumática', desc=f'Ø{_n(D_FOLE)} ext., área ef. 3421 mm², curso 40',
                 mat='COMPRADO', origem='REQUISITO'),
    'W-16': dict(nome='Sensor de altura', desc='Curso ≥ 45 mm, saída analógica, IP67', mat='COMPRADO',
                 origem='REQUISITO'),
    'W-17': dict(nome='Grupo pneumático', desc='Compressor 12 V, reservatório 2 L, secador, manifold 4 vias',
                 mat='COMPRADO', origem='REQUISITO'),
    'W-18': dict(nome='Bandeja do grupo pneumático', desc='Chapa 300×180×2', mat='Al 5052-H32',
                 origem='NOVO'),
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
    'K-06': dict(nome='Faixa central', desc='Chapa 110×500×1,2', mat='Al 5052-H32', origem='NOVO'),
}

ITENS.update({
    'M-01': dict(nome='Luva do mastro', desc=f'Tubo Ø{_n(D_LUVA)}×{_n(E_LUVA)} × {_n(L_LUVA)}',
                 mat='Al 6061-T6', origem='NOVO'),
    'M-02': dict(nome='Chapa de reforço da base', desc='Chapa 56×40×6', mat='Al 6061-T6', origem='NOVO'),
    'M-10': dict(nome='Haste do mastro',
                 desc=f'Tubo Ø{_n(D_MASTRO)}×{_n(E_MASTRO)} × {_n(Z_TOTAL - Z_REF_M[1])}',
                 mat='Al 6061-T6', origem='NOVO'),
    'M-11': dict(nome='Bainha anti-galho', desc=f'Tubo Ø{_n(D_BAINHA)}/Ø{_n(D_MASTRO)}, 1 trecho por vão',
                 mat='UHMW-PE', origem='NOVO'),
    'M-12': dict(nome='Ponta cônica', desc=f'Ø{_n(D_BAINHA)} × 40', mat='UHMW-PE', origem='NOVO'),
    'T-01': dict(nome='Braçadeira do mastro (metade)', desc='Chapa 60×50×12, canal usinado',
                 mat='Al 6061-T6', origem='NOVO'),
    'T-02': dict(nome='Prato de interface VMS-60', desc='Chapa 72×64×10, 7 furos de índice',
                 mat='Al 6061-T6', origem='NOVO'),
    'T-03': dict(nome='Adaptador de sensor VMS-60', desc='Chapa 72×64×6', mat='Al 6061-T6',
                 origem='NOVO'),
    'T-04': dict(nome='Adaptador térmico removível VMS-60', desc='Chapa 72×64×6, sem furação de sensor',
                 mat='Al 6061-T6', origem='NOVO'),
    'T-10': dict(nome='Adaptador da antena GNSS no mastro',
                 desc=f'Barra Ø{_n(D_ENCAIXE_ANTENA)} × {_n(L_ENCAIXE_ANTENA + H_TOPO_ANTENA)}, '
                      f'furo Ø{_n(D_CABO_ANTENA)}, rosca 5/8"-11 UNC',
                 mat='Al 6061-T6', origem='NOVO'),
    'T-05': dict(nome='Protetor sacrificial da câmera', desc='UHMW-PE 112×46×6',
                 mat='UHMW-PE', origem='NOVO'),
    'T-06': dict(nome='Berço VMS de extremidade', desc='Chapa 72×64×4', mat='Al 6061-T6',
                 origem='NOVO'),
    'T-07': dict(nome='Berço do terminal satelital', desc='Chapa 280×240×4', mat='Al 5052-H32',
                 origem='NOVO'),
    'T-09': dict(nome='Berço VMS da câmera de raiz', desc='Chapa 72×64×10', mat='Al 6061-T6',
                 origem='NOVO'),
    'B-01': dict(nome='Batente da bateria', desc='Cantoneira 40×40×4 × 150', mat='Al 6061-T6', origem='NOVO'),
    'E-01': dict(nome='Bandeja lateral', desc='Chapa 380×54×2', mat='Al 5052-H32', origem='NOVO'),
    'E-02': dict(nome='Bandeja de extremidade', desc='Chapa 122×52×2', mat='Al 5052-H32', origem='NOVO'),
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
})

GRUPOS = {
    'Q': 'Quadro estrutural soldado',
    'C': 'Chapa de fundo e nervuras',
    'W': 'Suspensão pneumática independente (4 cantos, soldados e usinados)',
    'G': 'Gaiola de proteção (2 módulos idênticos)',
    'K': 'Carenagens e tampas',
    'M': 'Mastros: base e haste',
    'T': 'Interface modular de sensores VMS-60 (9 postos + 4 posições térmicas removíveis)',
    'B': 'Retenção da bateria',
    'E': 'Bandejas de eletrônica e E-STOP',
    'N': 'Interfaces de sensores e sinalização',
}


def conjunto_a():
    """Parte A — chassi, suspensão pneumática e gaiola (o que vai para cotação).

    **Suspensão: pneumática independente (grupo W).** Na Rev F este conjunto chamava
    ``suportes()`` — o suporte rígido — e a suspensão a ar existia só como estudo fora do
    conjunto, porque a arquitetura de balancim então proposta conflitava com o requisito de
    rolagem. A Rev H resolve o conflito (bitola 530 e rolagem limitada por curso) e a
    suspensão entra no conjunto: é ela que leva o motor-roda ao chassi, e não existe mais
    caminho alternativo. O grupo S foi retirado, não desativado.
    """
    return (quadro() + base_mastro() + chapa_fundo() + suspensao() + gaiola()
            + suporte_lidar() + carenagens())


def conjunto_b():
    """Parte B — interfaces: mastro, câmeras, bateria e eletrônica."""
    return (mastro() + suportes_camera() + berco_vms_extremidade() + berco_raiz()
            + berco_satelite() + retencao_bateria() + bandejas() + estop()
            + interfaces_sensores())


def conjunto_opcional():
    """O que o mastro COMPLETO acrescenta à entrega: 4 postos térmicos removíveis e o adaptador
    de antena T-10 nos dois mastros (os dois ficam com a provisão; a antena entra em um ou em ambos).
    O T-10 ocupa o lugar da ponta cônica M-12."""
    return suportes_termicos() + [p for p in mastro((1, -1)) if p.item == 'T-10']


def conjunto(parte='A'):
    """'A', 'B', 'AB' = a entrega · 'O' = só os opcionais · 'ABO' = o mastro completo, que é o
    que as conferências de interferência e de montagem têm de olhar."""
    if parte == 'A':
        return conjunto_a()
    if parte == 'B':
        return conjunto_b()
    if parte == 'O':
        return conjunto_opcional()
    base = conjunto_a() + conjunto_b()
    if parte == 'ABO':
        # o T-10 substitui a M-12, nos dois mastros
        base = [p for p in base if p.item != 'M-12']
        return base + conjunto_opcional()
    return base


def referencias():
    return (rodas() + suspensao_ref() + lidar_ref() + gnss_ref()
            + satelite_ref())


# ======================================================== fixadores (F)
def fixadores():
    n_m6_chapa = sum(1 for f in furos_chapa() if f[3].startswith('M6'))
    n_sapata = 2 * len([p for p in gaiola() if p.item == 'G-05'])
    n_m5_lat = 4 * len(X_FUROS_LAT) * len(Z_LINHAS_LAT)
    n_m5_fr = 2 * len(Y_FUROS_FR) * len(Z_LINHAS_LAT)
    n_m5_lidar = 4
    n_m5_tampa = sum(1 for f in (1, -1) for fu in furos_tampa(f) if fu[2] == D_FOLGA_M5) - n_m5_lidar
    n_rebite = sum(1 for f in furos_chapa() if f[2] == 4.9)
    n_m8 = 4 * len(FUROS_SUSPENSAO)
    n_m6 = n_m6_chapa + n_sapata
    n_m5 = n_m5_lat + n_m5_fr + n_m5_tampa
    return [
        ('F-01', 'Parafuso M8×65 ISO 4762', 'Inox A4-70', n_m8 // 2,
         'Estação X 508: berço do fole → bucha → chapa de fundo → berço do pivô'),
        ('F-02', 'Porca M8 autotravante DIN 985', 'Inox A4', n_m8, ''),
        ('F-03', 'Arruela lisa M8 ISO 7089', 'Inox A4', 2 * n_m8, ''),
        ('F-30', 'Parafuso M8×50 ISO 4762', 'Inox A4-70', n_m8 // 2,
         'Estação X 350: berço do fole → bucha → chapa de fundo'),
        ('F-04', 'Porca-rebite M6 passante, cabeça reduzida Ø ≤ 12', 'Inox A4', n_m6,
         f'{n_m6_chapa} no anel inferior (chapa) + {n_sapata} no anel superior (sapatas)'),
        ('F-05', 'Parafuso M6×16 ISO 7380', 'Inox A4-70', n_m6, ''),
        ('F-06', 'Porca-rebite M5 passante, cabeça reduzida Ø ≤ 10', 'Inox A4', n_m5 + n_m5_lidar,
         'Paredes externas dos tubos'),
        ('F-07', 'Parafuso M5×12 ISO 7380', 'Inox A4-70', n_m5, 'Cabeça baixa e lisa: não prende galho'),
        ('F-08', 'Parafuso M5×16 ISO 7380', 'Inox A4-70', n_m5_lidar, 'Suporte do LiDAR'),
        ('F-09', 'Rebite de repuxo Ø4,8×10', 'Alumínio', n_rebite, 'Nervuras C-02 → chapa C-01'),
        ('F-10', 'Parafuso M4×14 ISO 4762 + trava química média', 'Inox A4-70', 4 * MPW_N_FUROS,
         'MPW86 → chapa W-02 (engajamento 4 ≤ 5 mm)'),
        ('F-31', 'Bucha autolubrificante Ø23/Ø20 × 20, PTFE/bronze', 'Compósito', 8,
         'Duas por pivô, dentro do alojamento W-04'),
        ('F-32', 'Anel elástico externo Ø20 DIN 471', 'Inox', 8, 'Trava do eixo W-07'),
        ('F-33', 'Anel elástico externo Ø12 DIN 471', 'Inox', 8, 'Trava do pino W-09'),
        ('F-34', 'Junta de vedação Ø140/Ø94, NBR 2 mm', 'NBR', 8,
         'Duas por colar W-12: contra a chapa de fundo e contra o berço'),
        ('F-35', 'Rebite de repuxo Ø4,8×10 (flange do colar)', 'Alumínio', 24, 'Colar W-12 → chapa C-01'),
        ('F-36', 'Conexão engate rápido Ø6 × R1/8 + tubo PU Ø6', 'Latão/PU', 4, 'Uma por fole'),
        ('F-11', 'Passa-cabo de borracha para furo Ø32', 'EPDM', 4, 'Cabos dos motores'),
        ('F-12', 'Arruela larga M6 ISO 7093 (Ø18)', 'Inox A4', n_m6, 'Sobre furo de folga Ø13'),
        ('F-13', 'Arruela larga M5 ISO 7093 (Ø15)', 'Inox A4', n_m5 + n_m5_lidar, 'Sobre furo de folga Ø11'),
        ('F-20', 'Parafuso M6×45 ISO 4762 + porca autotravante', 'Inox A4-70', 12,
         'Braçadeira T-01: 2 por posto de mastro'),
        ('F-21', 'Parafuso M5×16 ISO 7380', 'Inox A4-70', 36,
         'Adaptador T-03 na face VMS-60: 4 por posto, 9 postos'),
        ('F-40', 'Pino cilíndrico Ø8 h6 × 16 ISO 2338', 'Inox 304', 9,
         'Pino de REFERÊNCIA da face VMS-60 — é ele que preserva a calibração'),
        ('F-41', 'Pino cilíndrico Ø6 h6 × 14 ISO 2338', 'Inox 304', 9,
         'Pino anti-giro da face VMS-60'),
        ('F-42', 'Pino cilíndrico Ø6 h6 × 20 ISO 2338', 'Inox 304', 6,
         'Pino de índice de inclinação, passo de 10°'),
        ('F-43', 'Parafuso M8×30 ISO 4762', 'Inox A4-70', 6, 'Eixo do índice do prato T-02'),
        ('F-44', 'Parafuso M4×12 + porca-rebite M4', 'Inox A4', 36,
         'Câmera no adaptador T-03 — furação conforme o modelo (P-06)'),
        ('F-45', 'Conector M12 fêmea de painel, 8 vias, codificação X', 'Inox/PBT', 9,
         'Um por posto de sensor: Ethernet + PoE no mesmo conector'),
        ('F-46', 'Passa-cabo de borracha para furo Ø32', 'EPDM', 1, 'Cabo do terminal satelital, no berço T-07'),
        ('F-59', 'Passa-cabo de borracha para furo Ø20', 'EPDM', 2,
         'Saída lateral da luva M-01, um por mastro (o Ø32 do V3 não cabia: a luva é Ø42)'),
        ('F-60', 'Passa-cabo de borracha para furo Ø12', 'EPDM', 6,
         'Entrada de cabo no tubo M-10, 30 mm abaixo de cada posto de OAK-D'),
        ('F-22', 'Parafuso M6×20 ISO 7380 + porca-rebite M6', 'Inox A4', 24,
         'Batentes B-01 e bandejas E-01/E-02 na malha da chapa'),
        ('F-23', 'Cinta de poliéster 25 mm com catraca, LC ≥ 250 daN', 'Poliéster', 2, 'Amarração da bateria'),
        ('F-24', 'Parafuso M6×12 passante (travamento da haste)', 'Inox A4-70', 4, 'Haste na luva'),
        ('F-25', 'Parafuso M5×16 + porca', 'Inox A4', 8, 'E-10 e E-11 na tampa traseira'),
        ('F-26', 'Parafuso M5×16 + porca-rebite M5', 'Inox A4', 4, 'Suporte da antena GNSS na tampa'),
        ('F-58', 'Parafuso M5×16 + porca-rebite M5', 'Inox A4', 6, 'Berço T-07 do terminal satelital na tampa'),
        ('F-27', 'Parafuso M6×16 ISO 7380', 'Inox A4', 12, 'Berço do IMU e suporte da câmera de raiz'),
        ('F-28', 'Parafuso M4×12 + porca-rebite M4', 'Inox A4', 6, 'Janela de policarbonato'),
        ('F-29', 'Parafuso M4×10', 'Inox A4', 20, 'Protetores T-05 (2 por peça), faróis e antena'),
        # --- OPCIONAL: módulos térmicos removíveis (4 posições) e antena GNSS no mastro
        ('F-50', 'Parafuso M6×45 ISO 4762 + porca autotravante', 'Inox A4-70', 8,
         'OPCIONAL · braçadeira T-01 dos 4 postos térmicos: 2 por posto'),
        ('F-51', 'Parafuso M5 imperdível com manípulo, aperto manual', 'Inox A4', 16,
         'OPCIONAL · módulo térmico na face VMS-60: 4 por posto. Modelo A COTAR'),
        ('F-52', 'Pino cilíndrico Ø8 h6 × 16 ISO 2338', 'Inox 304', 4,
         'OPCIONAL · pino de REFERÊNCIA dos postos térmicos'),
        ('F-53', 'Pino cilíndrico Ø6 h6 × 14 ISO 2338', 'Inox 304', 4,
         'OPCIONAL · pino anti-giro dos postos térmicos'),
        ('F-54', 'Pino cilíndrico Ø6 h6 × 20 ISO 2338', 'Inox 304', 4,
         'OPCIONAL · pino de índice de inclinação dos postos térmicos'),
        ('F-55', 'Parafuso M8×30 ISO 4762', 'Inox A4-70', 4, 'OPCIONAL · eixo do índice do prato T-02 térmico'),
        ('F-56', 'Parafuso M4×10', 'Inox A4', 8, 'OPCIONAL · protetores T-05 dos postos térmicos'),
        ('F-57', 'Parafuso M6×12 passante (travamento do adaptador de antena)', 'Inox A4-70', 2,
         'OPCIONAL · T-10 no topo do mastro: 1 por mastro com antena, aperto transversal'),
        ('F-61', 'Passa-cabo de borracha para furo Ø12', 'EPDM', 4,
         'OPCIONAL · entrada de cabo no tubo M-10, nos 4 postos térmicos'),
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
    ms = g['W'][0] + g['M'][0] + MASSA_FIXADORES
    mg = g['G'][0] + g['K'][0]
    novo = [
        ('Quadro estrutural', g['Q'][0], g['Q'][3], 'Q-01…Q-06'),
        ('Chapa de fundo', g['C'][0], g['C'][3], 'C-01, C-02'),
        ('Suspensão, base e fixadores', ms,
         (g['W'][0] * g['W'][3] + g['M'][0] * g['M'][3] + MASSA_FIXADORES * 300) / ms, 'W + M + F (F estim. 1,4)'),
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
