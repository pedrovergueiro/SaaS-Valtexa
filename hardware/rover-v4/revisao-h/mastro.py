"""Rigidez do mastro e vibração dos sensores — a conta que decide se isola ou enrijece.

O pedido do V4 manda **diferenciar a rigidez do mastro do isolamento de vibração dos
sensores**. Esta é a diferença, e ela não é de grau — é de sinal:

* **enrijecer o mastro** sobe a frequência própria para longe da excitação do terreno. A
  câmera continua solidária ao rover, e a calibração extrínseca continua válida;
* **isolar a câmera** desacopla a câmera do mastro. Atenua vibração de alta frequência, e
  em troca **a câmera passa a se mover em relação ao rover**. Para fusão de dados isso é
  veneno: a matriz extrínseca deixa de ser constante e passa a depender da aceleração.

Num rover de inspeção, o dado é a imagem georreferenciada. Mover a câmera para suavizar a
imagem e destruir a georreferência é trocar um problema por outro pior. Por isso a regra
desta revisão:

> **Câmera: montagem RÍGIDA. LiDAR: isolado. A vibração das câmeras se resolve na
> rigidez do mastro, não no coxim.**

E o LiDAR é isolado porque é outro caso: ele mede distância instantânea ponto a ponto, não
integra uma imagem no tempo, e sua extrínseca só precisa valer na média. Os coxins G-08 já
estão no projeto desde a Rev E e continuam.

O que este módulo faz é provar que a rigidez do mastro basta — ou dizer de quanto ela
precisa aumentar.

```
python mastro.py
```

Unidades: mm, kg, N, Hz, graus.
"""

from __future__ import annotations

import math
import pathlib
import sys

AQUI = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent / 'chassi-gaiola'))
sys.path.insert(0, str(AQUI))

import modelo as M  # noqa: E402

G = 9.80665

# ============================================================ material e seção
E_AL = 68900.0
"""MPa — módulo de elasticidade do 6061-T6. Independe da têmpera; a solda não o altera."""

RHO_AL = 2.70e-6   # kg/mm³
RHO_UHMW = 0.95e-6

# ---- massas dos sensores
MASSA_OAKD = 0.25
"""kg — ESTIMATIVA. A Luxonis não publica a massa da OAK-D Pro W PoE no material que o
projeto tem (pendência P-06). 0,25 kg é faixa para uma câmera estéreo em carcaça de
alumínio deste tamanho. `sensibilidade` mostra o efeito de errar este número."""

MASSA_TERMICA = 0.20
"""kg — ESTIMATIVA, mesma situação. Módulo térmico compacto com lente de germânio."""

MASSA_VMS = 0.42
"""kg — massa do posto VMS completo (braçadeira + prato + adaptador + protetor), calculada
da geometria em `modelo.postos_vms`. Confirmada por `_massa_posto`."""

MASSA_ANTENA = 0.30
"""kg — ESTIMATIVA. Nenhuma antena GNSS foi escolhida (pendência P-05). Antenas de
RTK para robótica vão de algumas centenas de gramas para cima; 0,30 kg é o caso de
cálculo, e `massa_antena_maxima` diz quanto o mastro AGUENTA — que é o número que vale
ir às compras com, no lugar deste."""

MASSA_CONE = math.pi / 4 * M.D_BAINHA ** 2 * 40.0 * RHO_UHMW
"""kg — a ponta cônica M-12, geometria do modelo. Sai quando a antena entra."""


def _massa_posto() -> float:
    """Massa real de um posto VMS, medida na geometria do modelo."""
    try:
        ps = [p for p in M.suportes_camera() if p.grupo == 'T']
    except AttributeError:
        return MASSA_VMS
    if not ps:
        return MASSA_VMS
    return sum(p.massa() for p in ps) / 6.0


def _massa_t10() -> float:
    """Massa do adaptador de antena T-10 (um), medida na geometria do modelo."""
    ps = [p for p in M.mastro((1,)) if p.item == 'T-10']
    return ps[0].massa() if ps else 0.0


def secao_mastro(d_ext: float = None, parede: float = None) -> dict:
    """Propriedades da seção do tubo do mastro."""
    d = d_ext if d_ext is not None else M.D_MASTRO
    t = parede if parede is not None else M.E_MASTRO
    di = d - 2 * t
    i = math.pi * (d ** 4 - di ** 4) / 64
    a = math.pi * (d ** 2 - di ** 2) / 4
    return dict(d_ext=d, parede=t, d_int=di, I=i, A=a, W=i / (d / 2),
                massa_linear=a * RHO_AL, EI=E_AL * i)


# ============================================================ modelo dinâmico
def _bainha_massa_linear() -> float:
    """A bainha anti-galho não é estrutural, mas pesa e desce a frequência."""
    a = math.pi * (M.D_BAINHA ** 2 - M.D_MASTRO ** 2) / 4
    return a * RHO_UHMW


FATOR_ENGASTE = 0.95
"""HIPÓTESE — redução de 5 % na frequência pelo engaste não ser rígido (haste em luva
travada por 2 parafusos, com folga de montagem). Não é medido. Quem o substitui é o
ensaio V-12, com acelerômetro no mastro montado. Não confundir com o erro do Rayleigh,
que `frequencia_ritz` mostra ser menor que 1 %."""

CASOS = {
    'entrega': 'configuração de entrega: 3 OAK-D por mastro, ponta cônica',
    'cheio': '3 OAK-D + 2 térmicas removíveis por mastro, ponta cônica',
    'projeto': '3 OAK-D + 2 térmicas removíveis + antena GNSS no topo — O CASO DE PROJETO',
}
"""Os três estados do mastro. O mastro é DIMENSIONADO pelo último: é o que o projeto
descreve, e é o que a estrutura tem de aguentar sem redesenho quando os módulos opcionais
forem montados. Os dois primeiros só mostram quanto cada opcional custa na frequência."""


def cargas_caso(caso: str = 'projeto', massa_antena: float = None):
    """Lista de (Z, massa) dos postos e a massa de ponta, para um dos `CASOS`."""
    post = _massa_posto()
    c = [(z, MASSA_OAKD + post) for z in M.CAMERAS_Z]
    if caso in ('cheio', 'projeto'):
        c += [(z, MASSA_TERMICA + post) for z in M.Z_TERMICA]
    ponta = MASSA_CONE
    if caso == 'projeto':
        ponta = (MASSA_ANTENA if massa_antena is None else massa_antena) + _massa_t10()
    return c, ponta


def frequencia(d_ext: float = None, parede: float = None,
               massa_cam: float = None, alturas=None, cargas=None,
               massa_ponta: float = None, caso: str = 'projeto',
               massa_antena: float = None) -> dict:
    """1ª frequência de flexão do mastro, por Rayleigh com massas concentradas.

    Modelo: viga em balanço engastada no topo da luva M-01 (Z 526), com os sensores como
    massas concentradas nas cotas de montagem e a massa de ponta (cone ou antena) no
    topo. A forma suposta é a estática do balanço sob peso próprio, que é o padrão do
    método e dá erro de poucos por cento para baixo.

    Rayleigh dá um limite SUPERIOR da frequência. Para um requisito do tipo "a primeira
    frequência tem de estar ACIMA de X", isso é o lado errado do conservadorismo — por
    isso o resultado sai multiplicado por `FATOR_ENGASTE`. `frequencia_ritz` confere o
    método: com 5 modos de viga, a diferença para o Rayleigh de um termo é de até 0,6 % —
    então o fator NÃO corrige erro do método. Ele cobre o que o modelo não tem: o engaste
    real (haste dentro da luva, travada por 2 parafusos) não é rígido.

    Sem argumentos de carga vale o `caso` (padrão: o de projeto, mastro cheio com
    antena). `massa_cam` e `alturas` mantêm o uso antigo — uma câmera igual em cada cota.
    """
    s = secao_mastro(d_ext, parede)
    if cargas is None and (massa_cam is not None or alturas is not None):
        m_cam = massa_cam if massa_cam is not None else MASSA_OAKD + _massa_posto()
        cargas = [(z, m_cam) for z in (alturas if alturas is not None else M.CAMERAS_Z)]
        if massa_ponta is None:
            massa_ponta = 0.0
    elif cargas is None:
        cargas, ponta_caso = cargas_caso(caso, massa_antena)
        if massa_ponta is None:
            massa_ponta = ponta_caso
    cargas = list(cargas)
    if massa_ponta:
        cargas = cargas + [(M.Z_TOTAL, massa_ponta)]

    z0 = M.Z_LUVA[1]                      # engaste: topo da luva
    ltot = M.Z_TOTAL - z0
    mu = s['massa_linear'] + _bainha_massa_linear()

    def phi(x):
        """Forma suposta: flecha estática do balanço sob carga distribuída, normalizada."""
        return (x ** 2) * (6 * ltot ** 2 - 4 * ltot * x + x ** 2) / (3 * ltot ** 4)

    # energia potencial ~ integral EI (phi'')²; energia cinética ~ integral mu phi² + m_i phi_i²
    n = 400
    h = ltot / n
    num = den = 0.0
    for i in range(n + 1):
        x = i * h
        w = 1.0 if 0 < i < n else 0.5
        d2 = (12 * ltot ** 2 - 24 * ltot * x + 12 * x ** 2) / (3 * ltot ** 4)
        num += w * s['EI'] * d2 ** 2 * h
        den += w * mu * phi(x) ** 2 * h
    for (z, m_i) in cargas:
        x = z - z0
        if x <= 0:
            continue
        den += m_i * phi(x) ** 2

    w2 = num / den                       # rad²/s², com num em N·mm e den em kg·mm²
    f = math.sqrt(w2 * 1e3) / (2 * math.pi)   # N·mm/(kg·mm²) = 1e3 · 1/s²

    return dict(secao=s, caso=caso, cargas=tuple(cargas),
                alturas=tuple(z for z, _ in cargas),
                comprimento_livre=ltot, massa_linear_total=mu,
                massa_sensores=sum(m_i for z, m_i in cargas if z > z0),
                freq_Hz=f * FATOR_ENGASTE, freq_rayleigh_Hz=f)


def frequencia_ritz(d_ext: float = None, parede: float = None, caso: str = 'projeto',
                    massa_antena: float = None, n_modos: int = 5) -> float:
    """1ª frequência por Rayleigh-Ritz com os `n_modos` primeiros modos do balanço uniforme.

    É a conferência de `frequencia`: a base de Ritz inclui as massas pontuais exatamente, e
    a rigidez é diagonal nessa base — então o problema se resolve por iteração inversa sem
    biblioteca de álgebra linear. Devolve Hz, SEM `FATOR_ENGASTE`.
    """
    s = secao_mastro(d_ext, parede)
    z0 = M.Z_LUVA[1]
    ltot = M.Z_TOTAL - z0
    mu = s['massa_linear'] + _bainha_massa_linear()
    cargas, ponta = cargas_caso(caso, massa_antena)
    cargas = list(cargas) + [(M.Z_TOTAL, ponta)]

    bs = []                                  # raízes de 1 + cos(bL) cosh(bL) = 0
    for k in range(n_modos):
        x = (k + 0.5) * math.pi
        for _ in range(80):
            g = 1 + math.cos(x) * math.cosh(x)
            dg = -math.sin(x) * math.cosh(x) + math.cos(x) * math.sinh(x)
            x -= g / dg
        bs.append(x / ltot)

    def fi(b, x):
        bl = b * ltot
        sg = (math.sinh(bl) - math.sin(bl)) / (math.cosh(bl) + math.cos(bl))
        return math.cosh(b * x) - math.cos(b * x) - sg * (math.sinh(b * x) - math.sin(b * x))

    n = 800
    h = ltot / n
    xs = [i * h for i in range(n + 1)]
    wq = [0.5 if i in (0, n) else 1.0 for i in range(n + 1)]
    ph = [[fi(b, x) for x in xs] for b in bs]
    mm = [[mu * h * sum(wq[i] * ph[a][i] * ph[c][i] for i in range(n + 1))
           for c in range(n_modos)] for a in range(n_modos)]
    kd = [s['EI'] * bs[a] ** 4 * h * sum(wq[i] * ph[a][i] ** 2 for i in range(n + 1))
          for a in range(n_modos)]
    for (z, m) in cargas:
        x = z - z0
        if x <= 0:
            continue
        v = [fi(b, x) for b in bs]
        for a in range(n_modos):
            for c in range(n_modos):
                mm[a][c] += m * v[a] * v[c]

    q = [1.0] + [0.0] * (n_modos - 1)       # iteração inversa: K x = M q
    lam = 0.0
    for _ in range(200):
        mq = [sum(mm[a][c] * q[c] for c in range(n_modos)) for a in range(n_modos)]
        x_ = [mq[a] / kd[a] for a in range(n_modos)]
        nrm = math.sqrt(sum(v * v for v in x_))
        q = [v / nrm for v in x_]
        mq = [sum(mm[a][c] * q[c] for c in range(n_modos)) for a in range(n_modos)]
        lam = sum(kd[a] * q[a] * q[a] for a in range(n_modos)) / sum(q[a] * mq[a] for a in range(n_modos))
    return math.sqrt(lam * 1e3) / (2 * math.pi)


def massa_antena_maxima(d_ext: float = None, parede: float = None,
                        requisito_Hz: float = None) -> float:
    """Maior massa de antena (kg) com que o mastro cheio ainda cumpre o requisito de
    frequência. É a conta que vira exigência de compra: "antena com até X kg"."""
    req = REQUISITO_FREQ_HZ if requisito_Hz is None else requisito_Hz
    lo, hi = 0.0, 3.0
    if frequencia(d_ext, parede, caso='projeto', massa_antena=lo)['freq_Hz'] < req:
        return 0.0
    for _ in range(40):
        mid = (lo + hi) / 2
        if frequencia(d_ext, parede, caso='projeto', massa_antena=mid)['freq_Hz'] >= req:
            lo = mid
        else:
            hi = mid
    return lo


# ======================================================== deflexão e apontamento
VENTO_PA = 250.0
"""Pa — pressão dinâmica de projeto. 250 Pa ≈ 20 m/s (72 km/h). CRITÉRIO DE PROJETO:
não é condição de operação, é a rajada que o mastro tem de aguentar sem dano."""

GALHO_N = 80.0
"""N — carga lateral de um galho de café varrendo o mastro em marcha.
CRITÉRIO DE PROJETO. É o caso que define o apontamento, não o vento."""


def deflexao(forca_N: float = None, d_ext=None, parede=None) -> list[dict]:
    """Flecha e rotação em cada cota de câmera, sob carga lateral na ponta.

    O número que importa não é a flecha — é a **rotação**. Uma câmera que translada 10 mm
    continua enxergando quase a mesma coisa; uma que gira 1° erra 175 mm a 10 m.
    """
    s = secao_mastro(d_ext, parede)
    f = forca_N if forca_N is not None else GALHO_N
    z0 = M.Z_LUVA[1]
    ltot = M.Z_TOTAL - z0
    out = []
    for z in sorted(list(M.CAMERAS_Z) + list(M.Z_TERMICA)) + [M.Z_TOTAL]:
        x = z - z0
        if x <= 0:
            continue
        flecha = f * x ** 2 * (3 * ltot - x) / (6 * s['EI'])
        rot = f * x * (2 * ltot - x) / (2 * s['EI'])          # rad
        out.append(dict(z=z, flecha_mm=flecha, rotacao_deg=math.degrees(rot),
                        erro_a_10m_mm=math.tan(rot) * 10000.0))
    return out


def tensao_mastro(d_ext=None, parede=None) -> dict:
    """Tensão na raiz do mastro e verificação contra o escoamento."""
    s = secao_mastro(d_ext, parede)
    ltot = M.Z_TOTAL - M.Z_LUVA[1]
    # vento sobre a área projetada do mastro + das câmeras
    area_mastro = M.D_BAINHA * ltot * 1e-6                     # m²
    area_cam = (len(M.CAMERAS_Z) + len(M.Z_TERMICA)) * 0.09 * 0.07   # m², envelope ESTIMADO
    f_vento = VENTO_PA * (area_mastro + area_cam)
    m_vento = f_vento * (ltot / 2) * 1e3 / 1e3 * 0 + f_vento * (ltot * 0.6)
    m_galho = GALHO_N * ltot
    pior = max(m_vento, m_galho)
    return dict(forca_vento_N=f_vento, momento_vento_Nmm=m_vento,
                momento_galho_Nmm=m_galho, momento_projeto_Nmm=pior,
                sigma_MPa=pior / s['W'], W=s['W'],
                fs=240.0 / (pior / s['W']),
                nota='O galho governa. Vento de 20 m/s não é o caso crítico deste mastro — '
                     'a área projetada é pequena demais.')


# ============================================================ excitação do terreno
VELOCIDADE_MS = 1.4
"""m/s — velocidade de trabalho na lavoura. FONTE: baseline."""

PASSO_IRREGULARIDADE_M = 0.25
"""m — comprimento de onda típico das irregularidades de solo em rua de café.
CRITÉRIO DE PROJETO, a confirmar no ensaio V-12."""


def excitacao() -> dict:
    """De onde vem a vibração, e em que frequência."""
    f_terreno = VELOCIDADE_MS / PASSO_IRREGULARIDADE_M
    sys.path.insert(0, str(AQUI))
    import suspensao as S  # noqa: PLC0415
    f_susp = S.fole()['freq_Hz']
    n_rodas = 4
    f_roda = VELOCIDADE_MS / (math.pi * M.D_RODA / 1000.0)
    return dict(
        terreno_Hz=f_terreno, suspensao_Hz=f_susp, rotacao_da_roda_Hz=f_roda,
        maior_Hz=max(f_terreno, f_susp, f_roda),
        nota='A suspensão pneumática FILTRA o terreno acima da própria frequência de '
             f'{f_susp:.2f} Hz. O que chega ao mastro é o que passa por ela.')


REQUISITO_FREQ_HZ = 7.5
"""Hz — requisito da folha 25, caso 6 do FEA: 1ª frequência do mastro ≥ 7,5 Hz.
Herdado da Rev E e nunca verificado até esta revisão."""

MARGEM_MINIMA = 2.0
"""Razão mínima entre a frequência do mastro e a maior excitação.

CRITÉRIO DE PROJETO, e vale separar de um critério parecido que NÃO se aplica aqui.

Para um **isolador** a regra é √2: abaixo disso ele amplifica em vez de atenuar, e na
prática se pede 3 ou mais. Para uma **estrutura** a conta é outra — não se quer atenuação,
quer-se só ficar fora da ressonância. Fator 2 põe a excitação a meio caminho do pico e dá
folga para o erro das massas, que aqui é grande: a massa da OAK-D é estimativa.

Exigir 3 de um mastro em balanço de 1,26 m levaria a tubo de Ø50, e seria sobre-projetar
contra um número de excitação que é critério, não medição. O caminho certo para fechar a
margem é **medir** o espectro em campo (ensaio V-12), não engrossar o tubo às cegas.
"""


def amplificacao(razao: float) -> float:
    """Fator de amplificação dinâmica de um sistema sem amortecimento, `razao` = f_mastro /
    f_excitação. Sem amortecimento é o lado seguro: o mastro real amortece algo, e o
    quanto é pendência de ensaio (V-12)."""
    return 1.0 / abs(1.0 - 1.0 / razao ** 2)


def velocidade_maxima_ms(freq_mastro_Hz: float, margem: float = None) -> float:
    """Velocidade de marcha abaixo da qual a razão frequência/excitação fecha a margem."""
    m = MARGEM_MINIMA if margem is None else margem
    return freq_mastro_Hz / m * PASSO_IRREGULARIDADE_M


def veredito(d_ext=None, parede=None, caso: str = 'projeto') -> dict:
    """O mastro cumpre o requisito? E a margem contra o terreno fecha?

    São DUAS perguntas, e responder só a primeira foi o erro da primeira versão deste
    módulo: o Ø32×2 passava nos 7,5 Hz e não fechava a margem de 2,0 contra o terreno, e
    mesmo assim foi apresentado como aprovado. Aqui as duas saem separadas.
    """
    f = frequencia(d_ext, parede, caso=caso)
    ex = excitacao()
    razao = f['freq_Hz'] / ex['maior_Hz']
    return dict(
        caso=caso,
        freq_mastro_Hz=f['freq_Hz'], excitacao_Hz=ex['maior_Hz'], razao=razao,
        amplificacao=amplificacao(razao),
        atende_requisito=f['freq_Hz'] >= REQUISITO_FREQ_HZ,
        margem_ok=razao >= MARGEM_MINIMA,
        velocidade_maxima_ms=velocidade_maxima_ms(f['freq_Hz']),
        requisito_Hz=REQUISITO_FREQ_HZ, margem_minima=MARGEM_MINIMA)


ALTERNATIVAS = [
    # (descrição, Ø externo, parede)
    ('Ø25 × 2 — V3, herdado da baseline', 25.0, 2.0),
    ('Ø32 × 2 — V4 inicial, dimensionado para 3 câmeras', 32.0, 2.0),
    ('Ø32 × 3', 32.0, 3.0),
    ('Ø32 × 4', 32.0, 4.0),
    ('Ø35 × 2', 35.0, 2.0),
    ('Ø38 × 3', 38.0, 3.0),
    ('Ø40 × 3', 40.0, 3.0),
]

ALCANCE_LUVA_MAX = 297.0
"""mm — o maior |Y| que uma luva pode alcançar: é o que a Ø42×5 alcança em |Y| 276, já
verificado contra a carenagem K-01 e contra o envelope externo de 600."""


def comparacao_secoes() -> list[dict]:
    """O que cada seção de tubo entrega — frequência nos três casos, massa e rotação.

    `cabe` responde se a seção entra na luva Ø42×5 (furo 32) SEM mexer no chassi. Uma
    seção maior exigiria luva maior, e a luva já está no limite do envelope: é por isso
    que a parede engrossa e o diâmetro externo não.
    """
    out = []
    ltot = M.Z_TOTAL - M.Z_LUVA[1]
    base = secao_mastro(M.D_MASTRO, M.E_MASTRO)['massa_linear']
    for (nome, d, t) in ALTERNATIVAS:
        f = frequencia(d, t, caso='projeto')
        s = f['secao']
        defl = deflexao(d_ext=d, parede=t)
        alta = [x for x in defl if abs(x['z'] - M.CAMERAS_Z[2]) < 1][0]
        topo = defl[-1]
        luva_d = d + 2 * M.E_LUVA
        out.append(dict(
            nome=nome, d=d, parede=t, I=s['I'], freq_Hz=f['freq_Hz'],
            freq_entrega_Hz=frequencia(d, t, caso='entrega')['freq_Hz'],
            freq_cheio_Hz=frequencia(d, t, caso='cheio')['freq_Hz'],
            razao=f['freq_Hz'] / excitacao()['maior_Hz'],
            massa_por_mastro=s['massa_linear'] * ltot,
            delta_massa_total=2 * (s['massa_linear'] - base) * ltot,
            rotacao_camera_alta_deg=alta['rotacao_deg'],
            erro_a_10m_mm=alta['erro_a_10m_mm'],
            flecha_topo_mm=topo['flecha_mm'],
            sigma_MPa=tensao_mastro(d, t)['sigma_MPa'],
            cabe=d <= M.D_MASTRO + 1e-9,
            alcance_luva=M.Y_MASTRO + luva_d / 2,
            atende=f['freq_Hz'] >= REQUISITO_FREQ_HZ))
    return out


def sensibilidade() -> list[dict]:
    """E se a massa da OAK-D não for 0,25 kg? É estimativa, e pesa na frequência."""
    out = []
    for m in (0.15, 0.20, 0.25, 0.35, 0.50):
        post = _massa_posto()
        cs, ponta = cargas_caso('projeto')
        cs = [(z, (m + post) if abs(mi - (MASSA_OAKD + post)) < 1e-9 else mi) for z, mi in cs]
        f = frequencia(cargas=cs, massa_ponta=ponta)
        out.append(dict(massa_camera=m, massa_posto=post,
                        freq_Hz=f['freq_Hz'], atende=f['freq_Hz'] >= REQUISITO_FREQ_HZ))
    return out


def sensibilidade_antena() -> list[dict]:
    """E a massa da antena, que ainda nem foi escolhida?"""
    out = []
    for m in (0.0, 0.10, 0.20, 0.30, 0.40, 0.50, 0.60):
        f = frequencia(caso='projeto', massa_antena=m)['freq_Hz']
        out.append(dict(massa_antena=m, freq_Hz=f, atende=f >= REQUISITO_FREQ_HZ,
                        razao=f / excitacao()['maior_Hz']))
    return out


# ================================================= cabos dentro do tubo
D_CABO_M12_MM = 7.0
"""mm — ESTIMATIVA. Diâmetro externo de um cabo Ethernet blindado com conector M12 codificação X.
Varia por fabricante (de 6 a 8 mm é a faixa usual); nenhum cabo foi escolhido (P-40)."""

D_COAX_MM = 5.0
"""mm — ESTIMATIVA, cabo coaxial da antena GNSS."""

OCUPACAO_MAX = 0.40
"""Fração do furo que um chicote pode ocupar — regra de passagem de cabos, CRITÉRIO DE PROJETO."""


def ocupacao_cabos(d_ext: float = None, parede: float = None, d_cabo: float = None) -> dict:
    """Quanto do furo do tubo os cabos de UM mastro ocupam, no ponto mais cheio (a base).

    Passam por dentro do tubo: 1 cabo por posto (3 OAK-D + 2 térmicos) + o coaxial da
    antena. No ponto mais cheio, logo acima da saída lateral da luva, estão todos. É o
    preço da parede mais grossa: o furo encolhe de Ø28 para Ø26.
    """
    d_ext = M.D_MASTRO if d_ext is None else d_ext
    parede = M.E_MASTRO if parede is None else parede
    dc = D_CABO_M12_MM if d_cabo is None else d_cabo
    furo = d_ext - 2 * parede
    n_m12 = len(M.CAMERAS_Z) + len(M.Z_TERMICA)
    area_cabos = n_m12 * math.pi / 4 * dc ** 2 + math.pi / 4 * D_COAX_MM ** 2
    area_furo = math.pi / 4 * furo ** 2
    return dict(furo_mm=furo, n_m12=n_m12, n_coax=1, d_cabo_mm=dc,
                ocupacao=area_cabos / area_furo, limite=OCUPACAO_MAX,
                ok=area_cabos / area_furo <= OCUPACAO_MAX)


# =============================================================== isolamento
def isolamento_lidar() -> dict:
    """Os coxins G-08 do LiDAR: o único isolamento que o projeto tem, e por quê.

    O LiDAR é o caso em que isolar está certo: ele mede distância ponto a ponto, não
    integra imagem no tempo, e sua extrínseca precisa valer na média, não a cada instante.
    Câmera é o contrário.
    """
    ex = excitacao()
    # 4 coxins NBR Ø15×10 sob o suporte G-06; rigidez de faixa para elastômero 60 Sh A
    k_coxim = 120.0                      # N/mm, FAIXA de catálogo
    massa = 0.30                         # kg, ESTIMATIVA — Mid-360 sem ficha técnica
    k = 4 * k_coxim * 1e3
    f = math.sqrt(k / massa) / (2 * math.pi)
    return dict(k_por_coxim_N_mm=k_coxim, n=4, massa_isolada=massa, freq_Hz=f,
                razao=f / ex['maior_Hz'],
                isola=f > ex['maior_Hz'] * math.sqrt(2),
                nota='Isolador só atenua ACIMA de √2 vezes a própria frequência. Abaixo '
                     'disso ele AMPLIFICA. É a conta que decide se o coxim ajuda ou '
                     'atrapalha, e ela depende da massa do LiDAR — que é estimativa '
                     '(P-11).')


PORQUE_NAO_ISOLAR_CAMERA = """\
Isolar a câmera resolveria o borrão e criaria um problema maior.

A fusão de dados da IA usa a matriz extrínseca de cada câmera — onde ela está e para onde
aponta, em relação ao referencial do rover. Essa matriz é medida uma vez, na calibração, e
tratada como **constante**. Num mount rígido ela é constante de verdade: a câmera
acompanha o rover.

Num mount isolado ela deixa de ser. A câmera passa a se mover em relação ao chassi em
função da aceleração instantânea, com amplitude de milímetros e defasagem de fase. A
reconstrução 3D passa a ter um erro que varia com o terreno e que **nenhuma calibração
estática corrige**, porque não é um offset — é uma função do movimento.

Entre uma imagem com algum borrão de movimento e uma nuvem de pontos com erro variável de
origem desconhecida, a primeira é recuperável (obturador mais rápido, ganho maior,
estabilização auxiliada por IMU) e a segunda não.

Por isso: **câmera rígida, mastro rígido o bastante, e o problema de vibração resolvido
onde ele nasce.**
"""


# =============================================================== relatório
def main() -> None:
    if hasattr(sys.stdout, 'reconfigure'):          # console do Windows é cp1252
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    print('=' * 86)
    print('VTX-RV4 Rev H · RIGIDEZ DO MASTRO E VIBRAÇÃO DOS SENSORES')
    print('=' * 86)

    s = secao_mastro()
    f = frequencia()
    print(f'\n1. Mastro adotado — Ø{M._n(M.D_MASTRO)} × {M._n(M.E_MASTRO)}')
    print('-' * 50)
    print(f'  engaste no topo da luva M-01, Z {M.Z_LUVA[1]:.0f}; '
          f'comprimento livre {f["comprimento_livre"]:.0f} mm')
    print(f'  I = {s["I"]:.0f} mm⁴ · EI = {s["EI"] / 1e6:.0f} N·m²')
    print(f'  massa linear {s["massa_linear"] * 1e3:.3f} g/mm + bainha '
          f'{_bainha_massa_linear() * 1e3:.3f} g/mm')
    print(f'  OAK-D {MASSA_OAKD:.2f} kg · térmica {MASSA_TERMICA:.2f} kg (ambas ESTIMATIVA) '
          f'+ posto VMS {_massa_posto():.3f} kg (geometria)')
    print(f'  antena {MASSA_ANTENA:.2f} kg (ESTIMATIVA) + adaptador T-10 {_massa_t10():.3f} kg')

    ex = excitacao()
    print('\n2. De onde vem a excitação')
    print('-' * 50)
    print(f'  terreno a {VELOCIDADE_MS} m/s com onda de {PASSO_IRREGULARIDADE_M} m: '
          f'{ex["terreno_Hz"]:.2f} Hz')
    print(f'  suspensão pneumática (frequência de canto):          {ex["suspensao_Hz"]:.2f} Hz')
    print(f'  rotação da roda:                                      {ex["rotacao_da_roda_Hz"]:.2f} Hz')
    print(f'  maior: {ex["maior_Hz"]:.2f} Hz')
    print(f'  {ex["nota"]}')

    print('\n3. Veredito, nos três estados do mastro')
    print('-' * 50)
    for caso, desc in CASOS.items():
        v = veredito(caso=caso)
        print(f'  [{caso}] {desc}')
        print(f'      {v["freq_mastro_Hz"]:.2f} Hz contra requisito {v["requisito_Hz"]:.1f} Hz: '
              f'{"ATENDE" if v["atende_requisito"] else "NÃO ATENDE"}')
        print(f'      razão {v["razao"]:.2f} contra margem {v["margem_minima"]:.1f}: '
              f'{"OK" if v["margem_ok"] else "NÃO FECHA"} · amplificação {v["amplificacao"]:.2f}× · '
              f'a margem fecha até {v["velocidade_maxima_ms"]:.2f} m/s')
    print(f'  massa máxima de antena para manter {REQUISITO_FREQ_HZ} Hz: '
          f'{massa_antena_maxima():.2f} kg')
    fr = frequencia()
    rz = frequencia_ritz()
    print(f'  conferência do método (caso de projeto): Rayleigh {fr["freq_rayleigh_Hz"]:.2f} Hz · '
          f'Ritz 5 modos {rz:.2f} Hz · diferença {abs(fr["freq_rayleigh_Hz"] - rz) / rz * 100:.1f} %')
    print(f'  valor adotado = Rayleigh × {FATOR_ENGASTE} (engaste real não é rígido — HIPÓTESE): '
          f'{fr["freq_Hz"]:.2f} Hz')

    print('\n4. Seções de tubo, no caso de projeto (mastro cheio + antena)')
    print('-' * 50)
    print(f'  {"seção":50} {"f Hz":>6} {"entr.":>6} {"razão":>6} {"Δmassa":>8} {"cabe":>5}')
    for c in comparacao_secoes():
        marca = ''
        if abs(c['d'] - M.D_MASTRO) < 0.1 and abs(c['parede'] - M.E_MASTRO) < 0.1:
            marca = '  <- ADOTADA'
        elif not c['atende']:
            marca = '  <- abaixo do requisito'
        elif not c['cabe']:
            marca = f'  <- não cabe na luva Ø{M._n(M.D_LUVA)}'
        print(f'  {c["nome"]:50} {c["freq_Hz"]:6.2f} {c["freq_entrega_Hz"]:6.2f} {c["razao"]:6.2f} '
              f'{c["delta_massa_total"]:+8.3f} {"sim" if c["cabe"] else "não":>5}{marca}')

    print(f'\n5. Deflexão sob galho de {GALHO_N:.0f} N na ponta (seção adotada)')
    print('-' * 50)
    for d in deflexao():
        print(f'  Z {d["z"]:6.0f}   flecha {d["flecha_mm"]:7.2f} mm   '
              f'rotação {d["rotacao_deg"]:6.3f}°   erro a 10 m {d["erro_a_10m_mm"]:7.0f} mm')
    t = tensao_mastro()
    print(f'  tensão na raiz {t["sigma_MPa"]:.1f} MPa · FS {t["fs"]:.2f} · {t["nota"]}')

    print('\n6. Sensibilidade à massa da câmera (ESTIMATIVA, pendência P-06) — caso de projeto')
    print('-' * 50)
    for x in sensibilidade():
        print(f'  câmera {x["massa_camera"]:.2f} kg + posto {x["massa_posto"]:.3f} kg '
              f'-> {x["freq_Hz"]:5.2f} Hz'
              f'{"" if x["atende"] else "   <- abaixo do requisito"}')

    print('\n7. Sensibilidade à massa da antena (ainda não escolhida)')
    print('-' * 50)
    for x in sensibilidade_antena():
        print(f'  antena {x["massa_antena"]:.2f} kg -> {x["freq_Hz"]:5.2f} Hz · razão {x["razao"]:.2f}'
              f'{"" if x["atende"] else "   <- abaixo do requisito"}')

    print('\n8. Cabos dentro do tubo (diâmetros ESTIMADOS, P-40)')
    print('-' * 50)
    for (nome, d, t) in (('Ø32×2', 32.0, 2.0), ('Ø32×3 adotado', M.D_MASTRO, M.E_MASTRO)):
        o = ocupacao_cabos(d, t)
        print(f'  {nome:16} furo Ø{o["furo_mm"]:.0f} · {o["n_m12"]} cabos M12 de Ø{o["d_cabo_mm"]:.0f} + '
              f'1 coaxial -> ocupa {o["ocupacao"] * 100:.0f} % (limite {o["limite"] * 100:.0f} %): '
              f'{"OK" if o["ok"] else "ACIMA — risco"}')

    il = isolamento_lidar()
    print('\n9. Isolamento: só o LiDAR')
    print('-' * 50)
    print(f'  4 coxins G-08 a {il["k_por_coxim_N_mm"]:.0f} N/mm sob {il["massa_isolada"]:.2f} kg '
          f'-> {il["freq_Hz"]:.1f} Hz')
    print(f'  razão contra a excitação: {il["razao"]:.1f} · '
          f'{"ISOLA" if il["isola"] else "NAO ISOLA — amplificaria"}')
    print(f'  {il["nota"]}')
    print()
    for linha in PORQUE_NAO_ISOLAR_CAMERA.strip().split('\n'):
        print('  ' + linha)


if __name__ == '__main__':
    main()
