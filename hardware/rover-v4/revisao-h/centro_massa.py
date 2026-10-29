"""Centro de massa do Rover V4 e margem contra tombamento.

O que este módulo é: um inventário de massa com posição (X, Y, Z) e a ORIGEM de cada
número, somado em três estados do mastro, mais a geometria de tombamento daí tirada.

O que ele NÃO é: pesagem. O projeto tem a massa mínima declarada e a posição de poucos
componentes. Cada linha do inventário carrega uma etiqueta, e o relatório mostra quanto do
resultado depende do que não foi medido:

    CAD         massa e posição saem do modelo paramétrico (densidade × volume)
    DATASHEET   massa de ficha de fabricante (só o motor-roda MPW86)
    BASELINE    massa da tabela 5.1 da baseline Rev E (bateria 36,5 kg, bloco restante)
    ZONA        posição = centro da zona que espaco.py reserva para o componente
    ESTIMATIVA  massa suposta, sem ficha (OAK-D, térmica, antena, grupo pneumático)
    DERIVADO    calculado a partir do que está acima

A tabela 5.1 da baseline NÃO está no repositório com rótulos — só a lista de números. Por
isso os itens "mantidos" entram como DOIS itens conhecidos (4 motores-roda de 18,0 kg e a
bateria de 36,5 kg) mais um BLOCO RESTANTE de massa conhecida e posição desconhecida. O Z do
bloco é derivado do CG publicado da baseline (297 mm), de modo que a soma reproduz o
consolidado do caderno (108,43 kg, Z 314,3 mm) — isso é conferido em `reconcilia()`.

Eixos: ISO 8855 (X à frente, Y à esquerda, Z para cima), origem no centro do entre-eixos,
no solo. Unidades: kg e mm.
"""
from __future__ import annotations

import math
import pathlib
import sys
from dataclasses import dataclass

AQUI = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent / 'chassi-gaiola'))
sys.path.insert(0, str(AQUI))

import modelo as M          # noqa: E402
import suspensao as SU      # noqa: E402
import mastro as MA         # noqa: E402
import espaco as ES         # noqa: E402

G = 9.80665

MASSA_MOTOR = 4.5
"""kg — MPW86, ficha 011121. O ZLTECH da compra recomendada NÃO publica massa (P-09)."""

N_MOTORES = 4
MASSA_BATERIA = 36.5
"""kg — tabela 5.1 da baseline Rev E (16 células LiFePO4)."""

H_BATERIA = 140.0
"""mm — altura dos módulos (Rev K: 16 células EVE LF105 de pé, 130,3 mm + barramento). ESTIMATIVA."""

Z_BASE_BATERIA = 250.0
"""mm — face superior da chapa de fundo C-01."""

MASSA_CARGA_UTIL = 25.0
"""kg — carga útil da baseline. A POSIÇÃO dela não é conhecida: só cenários (`carga_util`)."""

E_Y_BASELINE = 15.0
"""mm — deslocamento lateral do CG que a fórmula 6.1 da baseline já supõe."""

ENVELOPE_BASELINE = 16.2
"""graus — envelope conservador PUBLICADO na baseline Rev E (fórmula 6.1). O repositório não traz um
mínimo EXIGIDO; este valor é o ponto de comparação, não um critério de aceite."""


@dataclass
class Item:
    nome: str
    kg: float
    x: float
    y: float
    z: float
    origem: str
    grupo: str = ''
    nota: str = ''


# ============================================================ inventário
def _grupos_cad(pecas) -> list[Item]:
    """Peças do modelo agrupadas por grupo (Q, C, W, ...), com o CG de cada grupo."""
    ac: dict[str, list[float]] = {}
    for p in pecas:
        if p.estilo == 'ref':
            continue
        m, c = p.massa(), p.centroide()
        a = ac.setdefault(p.grupo, [0.0, 0.0, 0.0, 0.0])
        a[0] += m
        a[1] += m * c[0]
        a[2] += m * c[1]
        a[3] += m * c[2]
    nomes = {'Q': 'quadro', 'C': 'chapa de fundo', 'W': 'suspensão (aço e alumínio)',
             'G': 'gaiola', 'K': 'carenagens e tampas', 'M': 'mastros (tubos, luvas, bainha)',
             'T': 'interface VMS-60', 'B': 'retenção da bateria', 'E': 'bandejas e E-STOP',
             'N': 'interfaces de sensores'}
    return [Item(f'CAD · {g} {nomes.get(g, g)}', m, mx / m, my / m, mz / m, 'CAD', 'estrutura')
            for g, (m, mx, my, mz) in sorted(ac.items())]


def _pecas_do_estado(estado: str):
    """Peças fabricadas de cada estado do mastro.

    entrega  : 9 OAK-D, sem térmicas, sem antena no mastro (a antena fica na tampa, N-01)
    cheio    : + 4 térmicas removíveis
    projeto  : + antena no topo de UM mastro (+Y) — o pior caso lateral
    projeto2 : + antena no topo dos DOIS mastros — simétrico, mais alto
    """
    ps = M.conjunto('AB')
    if estado == 'entrega':
        return ps
    ps = ps + M.suportes_termicos()
    if estado == 'cheio':
        return ps
    lados = (1,) if estado == 'projeto' else (1, -1)
    # o T-10 ocupa o lugar da ponta cônica M-12, só nos mastros que levam antena
    ps = [p for p in ps if not (p.item == 'M-12' and (1 if p.centroide()[1] > 0 else -1) in lados)]
    t10 = [p for p in M.mastro((1, -1)) if p.item == 'T-10'
           and (1 if p.centroide()[1] > 0 else -1) in lados]
    return ps + t10


def _posicoes_oakd() -> list[tuple[float, float, float]]:
    """Os nove adaptadores T-03 — a câmera fica na face externa; o erro é de dezenas de mm."""
    return [p.centroide() for p in M.conjunto('AB') if p.item == 'T-03']


def _centro_zona(nome: str) -> tuple[float, float]:
    for (n, zx, zy, _) in ES.ZONAS:
        if n == nome:
            return (zx[0] + zx[1]) / 2, (zy[0] + zy[1]) / 2
    raise KeyError(nome)


def inventario(estado: str = 'entrega') -> list[Item]:
    """Todos os itens do rover naquele estado. A soma reproduz `consolidado()` quando
    se tiram os acréscimos do V4 (conferido em `reconcilia`)."""
    c = M.consolidado()
    m_mant, z_mant = c['mantidos']
    out: list[Item] = []

    # ---- o que a baseline mantém, aberto no que se sabe
    xs, ys = M.XS, M.BITOLA / 2
    for sx in (1, -1):
        for sy in (1, -1):
            out.append(Item('Motor-roda', MASSA_MOTOR, sx * xs, sy * ys, M.Z_EIXO, 'DATASHEET', 'motor',
                            'MPW86; a massa do ZLTECH escolhido não é publicada'))
    z_bat = Z_BASE_BATERIA + H_BATERIA / 2
    for sx in (1, -1):   # Rev K: dois módulos de 8 células, simétricos em X
        out.append(Item('Bateria 16S LiFePO4 · módulo', MASSA_BATERIA / 2, sx * M.X_MODULO, 0.0, z_bat,
                        'BASELINE', 'bateria',
                        'massa da baseline dividida em 2 módulos; posição = centro do módulo entre os '
                        'batentes B-01; altura estimada'))
    m_resto = m_mant - N_MOTORES * MASSA_MOTOR - MASSA_BATERIA
    z_resto = (m_mant * z_mant - N_MOTORES * MASSA_MOTOR * M.Z_EIXO - MASSA_BATERIA * z_bat) / m_resto
    out.append(Item('Bloco restante da baseline', m_resto, 0.0, 0.0, z_resto, 'DERIVADO', 'resto',
                    'massa da tabela 5.1 sem rótulos; Z derivado do CG publicado; X e Y NÃO conhecidos '
                    '(centro assumido)'))

    # ---- fabricado
    out += _grupos_cad(_pecas_do_estado(estado))
    out.append(Item('Fixadores', M.MASSA_FIXADORES, 0.0, 0.0, 300.0, 'ESTIMATIVA', 'estrutura',
                    'estimativa do caderno; sem posição'))

    # ---- acréscimos do V4 (não estão na baseline)
    for (x, y, z) in _posicoes_oakd():
        out.append(Item('OAK-D Pro W', MA.MASSA_OAKD, x, y, z, 'ESTIMATIVA', 'sensor',
                        'massa suposta (mastro.py), sem ficha; posição = adaptador T-03'))
    if estado != 'entrega':
        for p in M.suportes_termicos():
            if p.item == 'T-04':
                x, y, z = p.centroide()
                out.append(Item('Câmera térmica removível', MA.MASSA_TERMICA, x, y, z, 'ESTIMATIVA', 'sensor',
                                'massa suposta, sem modelo escolhido'))
    if estado == 'projeto':
        out.append(Item('Antena GNSS no mastro', MA.MASSA_ANTENA, 0.0, M.Y_MASTRO, M.Z_BASE_ANTENA,
                        'ESTIMATIVA', 'sensor', 'massa suposta; a antena de N-01 continua no bloco da '
                        'baseline (conservador)'))
    if estado == 'projeto2':
        for sy in (1, -1):
            out.append(Item('Antena GNSS no mastro', MA.MASSA_ANTENA, 0.0, sy * M.Y_MASTRO, M.Z_BASE_ANTENA,
                            'ESTIMATIVA', 'sensor', 'massa suposta'))

    # ---- grupo pneumático (comprado; faixa de catálogo, não ficha)
    # Rev K: o grupo saiu da zona única. Reservatório em 2 tubos nas faixas dianteiras; o resto
    # (compressor, secador, manifold, linhas) na baia traseira.
    zx, zy = _centro_zona('Compressor (baia traseira)')
    tubos = [_centro_zona('Faixa dianteira esquerda'), _centro_zona('Faixa dianteira direita')]
    for (cod, nome, qtd, kg, z, orig) in SU.COMPRADOS:
        if 'eservat' in nome:
            for (tx, ty) in tubos:
                out.append(Item(f'{cod} {nome} (tubo)', kg * qtd / 2, tx, ty, z, orig, 'pneumático',
                                'Rev K: metade em cada faixa dianteira (espaco.py)'))
            continue
        if cod in ('W-15', 'W-16'):
            for sx in (1, -1):
                for sy in (1, -1):
                    out.append(Item(f'{cod} {nome}', kg, sx * M.X_FOLE, sy * M.Y_FOLE, z, orig, 'pneumático',
                                    'junto a cada fole'))
        else:
            for _ in range(qtd):
                out.append(Item(f'{cod} {nome}', kg, zx, zy, z, 'ZONA', 'pneumático',
                                'centro da baia traseira do compressor (espaco.py, Rev K)'))
    return out


def soma(itens: list[Item]) -> dict:
    m = sum(i.kg for i in itens)
    return dict(kg=m, x=sum(i.kg * i.x for i in itens) / m, y=sum(i.kg * i.y for i in itens) / m,
                z=sum(i.kg * i.z for i in itens) / m)


def reconcilia() -> dict:
    """O inventário SEM os acréscimos do V4 tem de reproduzir o consolidado do caderno."""
    c = M.consolidado()
    base = [i for i in inventario('entrega') if i.grupo not in ('sensor', 'pneumático')]
    s = soma(base)
    return dict(kg=s['kg'], z=s['z'], kg_caderno=c['m_min'], z_caderno=c['zcg'],
                ok=abs(s['kg'] - c['m_min']) < 0.01 and abs(s['z'] - c['zcg']) < 0.1)


# ============================================================ tombamento
def _k_rigidez(massa: float, braco_mm: float) -> float:
    """N·m/rad dos quatro foles em torno de um eixo à distância `braco_mm` (como suspensao.roll)."""
    k_roda = SU.fole(massa)['k_roda_N_mm'] * 1e3
    return 4 * k_roda * (braco_mm / 1e3) ** 2


def _teto_rad(braco_mm: float) -> float:
    return math.atan(2 * M.CURSO_TRABALHO / (2 * braco_mm))


def tomba_em_rampa(massa, z, braco, meia, alpha0=35.0) -> dict:
    """Ângulo de rampa em que o CG passa sobre a linha de contato, com a carroceria rolando
    sobre os foles até o curso acabar. Mesma iteração de `suspensao.roll`.

    `braco` é a distância das rodas ao eixo de rolagem (dá a rigidez dos foles e o teto de curso);
    `meia` é a distância HORIZONTAL do CG à linha de contato que tomba. As duas só coincidem com
    o CG centrado: com o CG deslocado, `meia = braco - |y|` (lateral) ou `braco ± x` (longitudinal,
    e aí a direção importa: subir gira em torno do eixo traseiro, descer em torno do dianteiro)."""
    k = _k_rigidez(massa, braco)
    teto = _teto_rad(braco)
    alpha, phi = math.radians(alpha0), 0.0
    for _ in range(80):
        mom = massa * G * math.sin(alpha) * z / 1e3
        phi = min(mom / k, teto)
        alpha = math.atan((meia - z * math.sin(phi)) / (z * math.cos(phi)))
    return dict(tomba_deg=math.degrees(alpha), rolagem_deg=math.degrees(phi),
                limitada_por_curso=phi >= teto - 1e-12,
                rigido_deg=math.degrees(math.atan(meia / z)), z_efetivo=z * math.cos(phi))


def a_lateral_max(massa, z, braco, meia) -> dict:
    """Aceleração (curva em plano; ou arranque/frenagem, com `braco` e `meia` longitudinais) que
    levanta as rodas do lado interno, com a rolagem dos foles."""
    k = _k_rigidez(massa, braco)
    teto = _teto_rad(braco)
    a = G * meia / z
    phi = 0.0
    for _ in range(80):
        phi = min(massa * a * z / 1e3 / k, teto)
        a = G * (meia - z * math.sin(phi)) / (z * math.cos(phi))
    return dict(a_ms2=a, a_g=a / G, rolagem_deg=math.degrees(phi), rigido_g=meia / z)


def v_max_curva(a_ms2: float, raio_m: float, fs: float = 2.0) -> float:
    """Velocidade em que a aceleração centrípeta é a/fs. O raio é CENÁRIO, não requisito."""
    return math.sqrt(a_ms2 / fs * raio_m)


# ============================================================ resultados
ESTADOS = [('entrega', '9 OAK-D (6 no mastro), sem térmicas, antena na tampa'),
           ('cheio', '+ 4 térmicas removíveis'),
           ('projeto', '+ antena no topo de UM mastro'),
           ('projeto2', '+ antena no topo dos DOIS mastros')]


def analisa(estado: str, itens: list[Item] | None = None, elevacao_mm: float = 0.0) -> dict:
    """`elevacao_mm`: sobe a carroceria (tudo menos os motores-roda) — o modelo está desenhado no
    vão MÍNIMO de 150 mm e a suspensão sobe até 150 + 30 mm."""
    itens = itens if itens is not None else inventario(estado)
    if elevacao_mm:
        itens = [Item(i.nome, i.kg, i.x, i.y, i.z + (0.0 if i.grupo == 'motor' else elevacao_mm),
                      i.origem, i.grupo, i.nota) for i in itens]
    s = soma(itens)
    m, x, y, z = s['kg'], s['x'], s['y'], s['z']
    meia = M.BITOLA / 2
    lat = tomba_em_rampa(m, z, meia, meia - abs(y))
    lat0 = tomba_em_rampa(m, z, meia, meia)
    pit_sobe = tomba_em_rampa(m, z, M.XS, M.XS + x)    # subindo: gira em torno do eixo traseiro
    pit_desce = tomba_em_rampa(m, z, M.XS, M.XS - x)   # descendo: em torno do eixo dianteiro
    a_lat = a_lateral_max(m, z, meia, meia - abs(y))
    a_arranque = a_lateral_max(m, z, M.XS, M.XS + x)   # acelerar: levanta a frente, gira no eixo traseiro
    a_frenagem = a_lateral_max(m, z, M.XS, M.XS - x)   # frear: levanta a traseira, gira no eixo dianteiro
    env = M.envelope_estabilidade(lat['z_efetivo'], e_y=max(E_Y_BASELINE, abs(y)),
                                  phi_c=3.0 + lat['rolagem_deg'])
    return dict(estado=estado, kg=m, x=x, y=y, z=z, lateral=lat, lateral_sem_assimetria=lat0,
                rampa_subindo=pit_sobe, rampa_descendo=pit_desce, a_lat=a_lat,
                a_arranque=a_arranque, a_frenagem=a_frenagem,
                envelope_deg=env, e_y_usado=max(E_Y_BASELINE, abs(y)),
                dentro_da_premissa_ey=abs(y) <= E_Y_BASELINE, itens=itens)


def todos() -> list[dict]:
    return [analisa(e) for e, _ in ESTADOS]


def vao_maximo(estado: str = 'projeto') -> dict:
    """O mesmo estado com a suspensão no vão máximo (carroceria +AJUSTE_ALTURA)."""
    return analisa(estado, elevacao_mm=M.AJUSTE_ALTURA)


def contribuicao_y(itens: list[Item], n: int = 6) -> list[tuple[str, float, float]]:
    """Quem empurra o CG para o lado: (nome, momento kg·mm, efeito em mm no Y do CG)."""
    m = sum(i.kg for i in itens)
    ac: dict[str, float] = {}
    for i in itens:
        ac[i.nome] = ac.get(i.nome, 0.0) + i.kg * i.y
    return sorted(((k, v, v / m) for k, v in ac.items() if abs(v) > 1e-6),
                  key=lambda t: -abs(t[1]))[:n]


def sensibilidades(estado: str = 'projeto') -> list[dict]:
    """Uma entrada de cada vez: quanto o resultado se mexe se o que é suposição estiver errado."""
    base = analisa(estado)

    def com(f) -> dict:
        it = [Item(i.nome, i.kg, i.x, i.y, i.z, i.origem, i.grupo, i.nota) for i in inventario(estado)]
        f(it)
        return analisa(estado, it)

    out = []

    def linha(rotulo, f):
        r = com(f)
        out.append(dict(rotulo=rotulo, z=r['z'], y=r['y'], x=r['x'], kg=r['kg'],
                        dz=r['z'] - base['z'], dy=r['y'] - base['y'], dx=r['x'] - base['x'],
                        lat=r['lateral']['tomba_deg'], dlat=r['lateral']['tomba_deg'] - base['lateral']['tomba_deg'],
                        env=r['envelope_deg'], dentro=r['dentro_da_premissa_ey']))

    def escala(nome_inicio, k):
        def f(it):
            for i in it:
                if i.nome.startswith(nome_inicio):
                    i.kg *= k
        return f

    linha('OAK-D com 0,50 kg (era 0,25)', escala('OAK-D', 2.0))
    linha('OAK-D com 0,15 kg', escala('OAK-D', 0.6))
    linha('térmica com 0,40 kg (era 0,20)', escala('Câmera térmica', 2.0))
    linha('antena com 0,42 kg (limite do mastro)', escala('Antena', 0.42 / MA.MASSA_ANTENA))

    def resto_alto(it):
        for i in it:
            if i.nome == 'Bloco restante da baseline':
                i.z += 40.0
    linha('bloco restante da baseline 40 mm mais alto', resto_alto)

    def resto_baixo(it):
        for i in it:
            if i.nome == 'Bloco restante da baseline':
                i.z -= 40.0
    linha('bloco restante da baseline 40 mm mais baixo', resto_baixo)

    def bateria_alta(it):
        for i in it:
            if i.nome.startswith('Bateria'):
                i.z += 20.0
    linha('caixa da bateria 40 mm mais alta (centro +20)', bateria_alta)

    def grupo_pneu_x2(it):
        for i in it:
            if i.grupo == 'pneumático':
                i.kg *= 1.5
    linha('grupo pneumático 50 % mais pesado', grupo_pneu_x2)

    def resto_um_lado(it):
        for i in it:
            if i.nome == 'Bloco restante da baseline':
                i.y = 100.0
    linha('bloco restante (14,5 kg) com o centro 100 mm para um lado', resto_um_lado)

    def resto_lado_max(it):
        for i in it:
            if i.nome == 'Bloco restante da baseline':
                i.y = 237.0
    linha('LIMITE: bloco restante inteiro na bandeja lateral (Y 237)', resto_lado_max)

    def bateria_fora(it):
        for i in it:
            if i.nome.startswith('Bateria'):
                i.y = 18.5
    linha('bateria encostada num batente (Y +18,5)', bateria_fora)

    def motor_pesado(it):
        for i in it:
            if i.nome == 'Motor-roda':
                i.kg = 6.0
    linha('motor-roda de 6,0 kg (massa do ZLTECH não é publicada)', motor_pesado)
    return out


def carga_util(estado: str = 'projeto') -> list[dict]:
    """A carga útil de 25 kg tem massa conhecida e posição desconhecida: três alturas hipotéticas."""
    out = []
    for z in (350.0, 500.0, 700.0):
        it = inventario(estado) + [Item('Carga útil (hipótese)', MASSA_CARGA_UTIL, 0.0, 0.0, z, 'ESTIMATIVA',
                                        'carga', 'posição suposta: centrada, a esta altura')]
        r = analisa(estado, it)
        out.append(dict(z_carga=z, kg=r['kg'], z=r['z'], lat=r['lateral']['tomba_deg'],
                        env=r['envelope_deg'], a_lat_g=r['a_lat']['a_g'],
                        rampa=r['rampa_subindo']['tomba_deg']))
    return out


def z_max_carga(estado: str = 'projeto', env_min: float = ENVELOPE_BASELINE,
                elevacao_mm: float = 0.0) -> float | None:
    """Maior altura (com o vão mínimo) em que a carga útil de 25 kg, centrada, ainda deixa o envelope
    em `env_min`. None se nem a carga rente à chapa de fundo (Z 250) mantém; 1000 se qualquer altura serve."""
    def env(z: float) -> float:
        it = inventario(estado) + [Item('Carga útil', MASSA_CARGA_UTIL, 0.0, 0.0, z, 'ESTIMATIVA', 'carga')]
        return analisa(estado, it, elevacao_mm)['envelope_deg']
    lo, hi = 250.0, 1000.0
    if env(lo) < env_min:
        return None
    if env(hi) >= env_min:
        return hi
    for _ in range(50):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if env(mid) >= env_min else (lo, mid)
    return lo


def z_cg_max(massa: float, y: float, env_min: float = ENVELOPE_BASELINE) -> float:
    """Maior altura de CG, para esta massa e este desvio lateral, que ainda dá `env_min` de envelope."""
    lo, hi = 250.0, 700.0
    for _ in range(60):
        mid = (lo + hi) / 2
        lat = tomba_em_rampa(massa, mid, M.BITOLA / 2, M.BITOLA / 2 - abs(y))
        env = M.envelope_estabilidade(lat['z_efetivo'], e_y=max(E_Y_BASELINE, abs(y)),
                                      phi_c=3.0 + lat['rolagem_deg'])
        lo, hi = (mid, hi) if env >= env_min else (lo, mid)
    return lo


def efeito_por_100g(estado: str = 'entrega') -> list[dict]:
    """Quanto 100 g custam em cada altura — mostra por que o topo do mastro pesa tanto."""
    b = analisa(estado)
    out = []
    for z in (300.0, 700.0, 1200.0, 1800.0):
        it = inventario(estado) + [Item('+100 g', 0.1, 0.0, 0.0, z, 'ESTIMATIVA')]
        r = analisa(estado, it)
        out.append(dict(z=z, dz=r['z'] - b['z'],
                        dlat=r['lateral']['tomba_deg'] - b['lateral']['tomba_deg']))
    return out


def equilibrio_lateral(estado: str = 'projeto') -> dict:
    """Quanto a bateria teria de andar em Y para zerar o Y do CG, e quanto ela pode andar."""
    r = analisa(estado)
    folga = (2 * 193.5 - 350.0) / 2        # centros dos batentes B-01 menos a largura estimada da caixa
    precisa = -r['y'] * r['kg'] / MASSA_BATERIA
    return dict(y_cg=r['y'], bateria_precisa_mm=precisa, folga_max_mm=folga,
                basta=abs(precisa) <= folga)


def tabela_curvas(estado: str = 'projeto') -> list[dict]:
    r = analisa(estado)
    out = []
    for raio in (1.0, 2.0, 3.0, 5.0):
        out.append(dict(raio=raio, v=v_max_curva(r['a_lat']['a_ms2'], raio, 2.0),
                        v_sem_fs=v_max_curva(r['a_lat']['a_ms2'], raio, 1.0)))
    return out


# ============================================================ saída no console
def main() -> None:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    rc = reconcilia()
    print('=' * 92)
    print('VTX-RV4 Rev H · CENTRO DE MASSA E TOMBAMENTO')
    print('=' * 92)
    print(f"\nConferência: inventário sem os acréscimos do V4 = {rc['kg']:.2f} kg, Z {rc['z']:.1f} mm"
          f" | caderno = {rc['kg_caderno']:.2f} kg, Z {rc['z_caderno']:.1f} mm"
          f" -> {'REPRODUZ' if rc['ok'] else 'NÃO REPRODUZ'}")
    print('\nCG por estado (X para frente, Y para a esquerda, mm contados do centro do entre-eixos):')
    print(f"  {'estado':10} {'massa kg':>9} {'X':>7} {'Y':>7} {'Z':>7}  {'lat. rampa':>10} {'envelope':>9}"
          f" {'a lat. g':>9}  {'rampa sobe':>10}")
    for r in todos():
        print(f"  {r['estado']:10} {r['kg']:9.2f} {r['x']:7.1f} {r['y']:7.2f} {r['z']:7.1f}"
              f"  {r['lateral']['tomba_deg']:9.2f}° {r['envelope_deg']:8.2f}° {r['a_lat']['a_g']:9.3f}"
              f"  {r['rampa_subindo']['tomba_deg']:9.2f}°")
    r = analisa('projeto')
    print('\nProjeto (mastro cheio, antena em um mastro):')
    print(f"  tombamento lateral em rampa: {r['lateral']['tomba_deg']:.2f}° "
          f"(rolagem {r['lateral']['rolagem_deg']:.2f}°, "
          f"{'limitada pelo curso' if r['lateral']['limitada_por_curso'] else 'pelo fole'}); "
          f"rígido seria {r['lateral']['rigido_deg']:.2f}°")
    print(f"  Y do CG {r['y']:+.2f} mm — premissa da fórmula 6.1 da baseline: |Y| ≤ {E_Y_BASELINE:.0f} mm "
          f"-> {'DENTRO' if r['dentro_da_premissa_ey'] else 'FORA'}")
    print('  maiores momentos laterais (kg·mm, efeito no Y do CG):')
    for n, mo, dy in contribuicao_y(r['itens']):
        print(f'     {n:40} {mo:10.0f}  {dy:+7.2f} mm')
    print('\nSensibilidade (estado projeto), um item de cada vez:')
    for s in sensibilidades('projeto'):
        print(f"  {s['rotulo']:62} Z {s['z']:6.1f} ({s['dz']:+5.1f})  Y {s['y']:+6.1f}"
              f"  lat {s['lat']:5.2f}° ({s['dlat']:+5.2f})  {'' if s['dentro'] else 'FORA de e_y'}")
    print('\nCarga útil de 25 kg (posição hipotética):')
    for c in carga_util():
        print(f"  a Z {c['z_carga']:4.0f}: {c['kg']:.1f} kg · CG Z {c['z']:.1f} · lateral {c['lat']:.2f}° · "
              f"a lat. {c['a_lat_g']:.3f} g")
    print('\n100 g, por altura (estado entrega):')
    for e in efeito_por_100g():
        print(f"  Z {e['z']:5.0f}: CG {e['dz']:+.3f} mm · tombamento {e['dlat']:+.4f}°")
    v = vao_maximo('projeto')
    print(f"\nVão máximo (+{M.AJUSTE_ALTURA:.0f} mm), estado projeto: CG Z {v['z']:.1f} · lateral "
          f"{v['lateral']['tomba_deg']:.2f}° · envelope {v['envelope_deg']:.2f}° · a lat. {v['a_lat']['a_g']:.3f} g")
    eq = equilibrio_lateral()
    print(f"\nEquilíbrio lateral: para zerar Y a bateria andaria {eq['bateria_precisa_mm']:+.1f} mm; "
          f"cabe até ±{eq['folga_max_mm']:.1f} mm -> {'BASTA' if eq['basta'] else 'NÃO BASTA'}")


if __name__ == '__main__':
    main()
