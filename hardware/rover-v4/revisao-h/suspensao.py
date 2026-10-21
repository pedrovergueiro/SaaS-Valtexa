"""Suspensão pneumática independente do Rover V4 — dimensionamento completo, Rev H.

Quatro braços longitudinais, um fole por canto, sem barra estabilizadora.

---

## Por que esta arquitetura, e não o balancim da Rev F

A Rev F propôs balancim longitudinal com fole na arfagem e rolagem rígida. A razão era
sólida: fole é mola macia, e rolagem macia derruba o tombamento. O balancim entrega
rolagem rígida por construção, porque o pivô é fixo no chassi.

Mas o balancim tem dois custos que a Rev F não fechou:

* **não ajusta o vão livre.** Com o pivô fixo, mudar a pressão dos foles gira os dois
  balancins no mesmo sentido — isso é arfagem, não altura. O `ALTURA_AJUSTAVEL_MM = 50`
  declarado no módulo da Rev F era incompatível com a própria geometria dele. É um erro
  da Rev F, e está registrado como tal na auditoria;
* **massa.** O balancim somava 6,85 kg de estrutura só para articular, além dos foles.

A Rev H troca a maciez de rolagem por BITOLA. Com bitola 530 em vez de 470 — dentro do
mesmo envelope externo de 600, que nunca era usado inteiro — e com a rolagem limitada pelo
curso (±25 mm em 530 de bitola dão 5,40° e nada mais, porque depois disso bate o fim de
curso), o envelope de estabilidade sai em 16,3° contra 15,5° do balancim rígido, os dois
no CG do inventário do V4 (121,1 kg, Z 336 mm, mastro cheio).

**A suspensão macia fica mais estável que a rígida.** Não por mágica: porque 60 mm de
bitola valem mais que 5° de rolagem, e os 60 mm estavam sobrando no envelope. A margem
sobre os 16,2° da baseline, porém, é de só 0,1° — ver `centro_massa.py`.

(Até 15/10/2026 este módulo publicava 20,9° contra 19,6°: o cálculo usava o CG da Rev F do
V3, 50 mm mais baixo, sem o mastro do V4.)

---

## O que este módulo faz

Cada função devolve números e imprime o que verificou. Rodando o módulo sai o relatório
inteiro, na ordem em que um memorial de cálculo se lê:

```
python suspensao.py
```

Unidades: mm, kg, N, bar, L, W, graus. Toda geometria vem de
`../chassi-gaiola/modelo.py` — nenhuma cota é redigitada aqui.
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

# ==================================================================== massa
# A massa oficial é a pendência nº 1 do projeto, e continua sendo. O que este módulo faz é
# não esconder isso atrás de um número só: dimensiona na massa alta e mostra a sensibilidade.
MASSA_REV_F = 110.07
"""kg — massa nominal da Rev F, da qual a Rev H parte. Ver auditoria, item D-03."""

ZCG_REV_F = 294.1
"""mm — CG vertical correspondente, mesma fonte."""

MASSA_BASELINE = M.M_NOM          # 97,8 kg declarados na baseline Rev E
MASSA_MINIMA = M.M_MIN            # 85,04 kg, melhor caso da baseline

FATOR_DINAMICO = 3.0
"""Impacto em buraco, 4 rodas. O mesmo da folha 15 e do caso 2 do FEA."""

TRANSFERENCIA = 1.35
"""Quanto a roda mais carregada recebe acima da média, em frenagem ou rampa.

CRITÉRIO DE PROJETO. Com braços independentes a transferência longitudinal não é limitada
por geometria nenhuma — é 1,35 por estimativa conservadora para entre-eixos 700 com CG a
294, e o número exato sai do caso 5 do FEA.
"""

# Grupo pneumático comprado. Massas de FAIXA de catálogo para a classe do componente, não
# de ficha técnica de peça específica. Serve para dizer se cabe, não para cotar.
COMPRADOS = [
    # (item, descrição, qtd, kg unit., Z mm, origem)
    ('W-15', 'Mola pneumática', 4, 0.30, 245.0, 'FAIXA'),
    ('W-16', 'Sensor de altura', 4, 0.09, 205.0, 'FAIXA'),
    ('W-17a', 'Compressor 12 V, 100 % ciclo, ~35 L/min', 1, 2.20, 268.0, 'FAIXA'),
    ('W-17b', 'Reservatório 2 L, alumínio', 1, 1.60, 272.0, 'FAIXA'),
    ('W-17c', 'Válvula solenoide 3/2, 12 V', 4, 0.18, 266.0, 'FAIXA'),
    ('W-17d', 'Secador / filtro coalescente', 1, 0.35, 268.0, 'FAIXA'),
    ('W-17e', 'Linhas PU Ø6, conexões e manifold', 1, 0.70, 258.0, 'ESTIMATIVA'),
    ('W-17f', 'Controlador de nível + chicote', 1, 0.30, 270.0, 'ESTIMATIVA'),
    ('W-18', 'Bandeja do grupo pneumático', 1, 0.30, 253.0, 'ESTIMATIVA'),
]


def massa() -> dict:
    """Massa da Rev H: sai o grupo S da Rev F, entram o grupo W e o grupo pneumático."""
    w = [p for p in M.suspensao()]
    m_w = sum(p.massa() for p in w)
    z_w = sum(p.massa() * p.centroide()[2] for p in w) / m_w

    m_s, z_s = 4.538, 201.95       # grupo S da Rev F, medido no modelo arquivado
    m_c = sum(q * kg for (_, _, q, kg, _, _) in COMPRADOS)
    z_c = sum(q * kg * z for (_, _, q, kg, z, _) in COMPRADOS) / m_c

    m = MASSA_REV_F - m_s + m_w + m_c
    mz = MASSA_REV_F * ZCG_REV_F - m_s * z_s + m_w * z_w + m_c * z_c
    return dict(
        m_w=m_w, z_w=z_w, m_s=m_s, z_s=z_s, m_c=m_c, z_c=z_c,
        massa=m, zcg=mz / m, delta=m - MASSA_REV_F, delta_z=mz / m - ZCG_REV_F,
        margem_baseline=MASSA_BASELINE - m,
        alternativa_aluminio=_massa_em_aluminio(m_w),
    )


def _massa_em_aluminio(m_w_aco: float) -> dict:
    """E se o grupo W fosse todo em alumínio?

    Está aqui porque é a pergunta que a massa provoca, e a resposta não é livre: as peças
    de aço do grupo W são as que ciclam a cada ondulação do terreno. Alumínio **não tem
    limite de fadiga** — acumula dano indefinidamente, sem patamar. Aço carbono tem. Num
    braço de suspensão isso deixa de ser acadêmico.

    A troca economiza massa real. Ela só não é de graça, e a decisão é do engenheiro.
    """
    em_aco = [p for p in M.suspensao() if p.mat == 'aco']
    m_aco = sum(p.massa() for p in em_aco)
    m_al = m_aco * M.RHO['6061'] / M.RHO['aco']
    return dict(massa_das_pecas_em_aco=m_aco, se_fossem_aluminio=m_al,
                economia=m_aco - m_al, grupo_w_em_aluminio=m_w_aco - (m_aco - m_al))


def carga_por_roda(massa_kg: float | None = None) -> dict:
    """Carga estática, dinâmica e de projeto em cada roda."""
    m = massa_kg if massa_kg is not None else massa()['massa']
    est = m * G / 4
    return dict(massa=m, estatica_N=est, estatica_kgf=m / 4,
                dinamica_N=est * FATOR_DINAMICO,
                projeto_N=est * FATOR_DINAMICO * TRANSFERENCIA)


# ================================================================ geometria
def geometria() -> dict:
    """A cinemática do braço, conferida contra o modelo.

    Relação de movimento: com o braço HORIZONTAL ela é constante ao longo do curso, e é
    exatamente a razão dos raios. Essa é a razão de projeto para o braço horizontal — com
    braço inclinado a relação varia e o fole vê carga diferente em cada altura.
    """
    braco = M.BRACO
    r = M.R_FOLE
    mr = r / braco
    assert abs(mr - M.MR_FOLE) < 1e-9, 'MR_FOLE do modelo não fecha com a geometria'

    # giro do braço em cada extremo do curso
    giro_curso = math.degrees(math.asin(M.CURSO_TRABALHO / braco))
    giro_total = math.degrees(math.asin((M.CURSO_RODA / 2) / braco)) * 2

    # recuo longitudinal da roda no curso (o braço descreve arco)
    recuo = braco * (1 - math.cos(math.radians(giro_total / 2)))

    return dict(
        x_pivo=M.X_PIVO, x_roda=M.XS, x_fole=M.X_FOLE, z_braco=M.Z_BRACO,
        braco=braco, r_fole=r, mr=mr,
        curso_roda=M.CURSO_RODA, curso_fole=M.CURSO_FOLE,
        curso_trabalho=M.CURSO_TRABALHO, ajuste=M.AJUSTE_ALTURA,
        giro_curso_deg=giro_curso, giro_total_deg=giro_total, recuo_mm=recuo,
        vao_min=M.VAO_LIVRE, vao_max=M.VAO_LIVRE + M.AJUSTE_ALTURA,
        rolagem_max_deg=M.rolagem_max(),
    )


# ===================================================================== fole
PRESSAO_MAXIMA_BAR = 8.0
"""Teto de trabalho que o fole comprado tem de suportar. REQUISITO de compra."""

PRESSAO_MINIMA_FORMA_BAR = 1.0
"""Abaixo disto um fole convoluto trabalha enrugado: rigidez imprevisível e desgaste na
dobra. É o critério que descarta as bitolas grandes, e é contraintuitivo — o rover é leve,
então fole folgado fica *mole demais* para funcionar como mola."""

N_POLITROPICO = 1.38
"""Expoente para o ar em compressão rápida. 1,0 seria isotérmico (compressor acompanhando),
1,4 adiabático. 1,38 é o usual para suspensão pneumática em frequência de suspensão."""


def area_fole() -> float:
    """mm² — área efetiva do fole, do Ø efetivo que o modelo declara como requisito."""
    return math.pi * (M.D_FOLE_EF / 2) ** 2


def fole(massa_kg: float | None = None) -> dict:
    """Pressões, rigidez e frequência do fole na geometria desenhada."""
    c = carga_por_roda(massa_kg)
    g = geometria()
    a_mm2 = area_fole()
    a_m2 = a_mm2 * 1e-6

    f_est = c['estatica_N'] / g['mr']
    f_din = c['dinamica_N'] / g['mr']
    f_proj = c['projeto_N'] / g['mr']

    p_est = f_est / a_m2 / 1e5
    h = M.H_FOLE
    v_m3 = a_mm2 * h * 1e-9
    p_abs = (p_est + 1.013) * 1e5

    k_fole = N_POLITROPICO * p_abs * a_m2 ** 2 / v_m3          # N/m
    k_roda = k_fole * g['mr'] ** 2
    m_canto = c['estatica_N'] / G
    freq = math.sqrt(k_roda / m_canto) / (2 * math.pi)

    # banda de altura instalada, do batente de compressão ao de extensão
    h_min = h - M.CURSO_TRABALHO * g['mr']
    h_max = h + (M.CURSO_TRABALHO + M.AJUSTE_ALTURA) * g['mr']

    return dict(
        area_mm2=a_mm2, d_efetivo=M.D_FOLE_EF, d_externo_max=M.D_FOLE,
        f_estatica_N=f_est, f_dinamica_N=f_din, f_projeto_N=f_proj,
        p_estatica_bar=p_est, p_dinamica_bar=f_din / a_m2 / 1e5,
        p_projeto_bar=f_proj / a_m2 / 1e5,
        h_nominal=h, h_min=h_min, h_max=h_max, curso=h_max - h_min,
        razao_curso_altura=(h_max - h_min) / h_max,
        volume_L=v_m3 * 1e3,
        k_fole_N_mm=k_fole / 1e3, k_roda_N_mm=k_roda / 1e3,
        freq_Hz=freq, flecha_estatica_mm=c['estatica_N'] / (k_roda / 1e3),
        forma_ok=p_est >= PRESSAO_MINIMA_FORMA_BAR,
        teto_ok=f_proj / a_m2 / 1e5 <= PRESSAO_MAXIMA_BAR,
    )


def requisitos_fole() -> list[tuple]:
    """A folha de requisitos do fole: é COMPRADO e não tem ficha técnica no projeto.

    O que está desenhado é a interface — prato W-08, berço W-11, colar W-12, curso e
    altura. Qualquer fole que feche esta tabela monta sem alterar desenho de usinagem
    nenhum. Um cilindro pneumático de mesma área também fecha, e é a alternativa
    qualificada.
    """
    f = fole()
    return [
        ('Área efetiva', f'{f["area_mm2"]:.0f} mm² ± 10 %', 'define a pressão de trabalho'),
        ('Ø externo máximo', f'{M.D_FOLE:.0f} mm',
         f'folga ao anel inferior e à roda — ver `folgas`'),
        ('Altura instalada nominal', f'{f["h_nominal"]:.1f} mm', 'vão livre 150, carga estática'),
        ('Altura mínima (compressão)', f'{f["h_min"]:.1f} mm', 'fim de curso de compressão'),
        ('Altura máxima (extensão)', f'{f["h_max"]:.1f} mm', 'fim de curso, vão livre 180'),
        ('Curso útil', f'{f["curso"]:.0f} mm', f'razão curso/altura {f["razao_curso_altura"]:.2f}'),
        ('Pressão de trabalho', f'{f["p_estatica_bar"]:.2f} bar', 'carga estática'),
        ('Pressão máxima admissível', f'≥ {PRESSAO_MAXIMA_BAR:.0f} bar',
         f'projeto exige {f["p_projeto_bar"]:.2f} bar'),
        ('Batente interno de compressão', 'integrado, ≥ 4,5 kN',
         'substitui batente externo — ver `batentes`'),
        ('Fixação inferior', 'M12 central ou 4 × M8 em PCD 50', 'prato W-08'),
        ('Fixação superior', 'M12 central + porta de ar R1/8', 'berço W-11'),
        ('Temperatura', '−10 a +70 °C', 'lavoura'),
        ('Proteção', 'resistente a UV, ozônio e abrasão por poeira', 'lavoura de café'),
    ]


# ========================================================= folgas e colisões
def folgas() -> list[dict]:
    """Toda folga que a suspensão cria, medida na geometria do modelo.

    Não é conferência de desenho: cada linha é uma distância calculada entre duas peças
    reais do modelo, com o critério de aceitação ao lado. É o que responde "confirma os
    espaços".
    """
    out = []

    def add(o, a, b, crit, nota='', tipo='verificacao'):
        out.append(dict(o_que=o, valor=a, criterio=b, ok=crit, nota=nota, tipo=tipo))

    # --- fole × roda. O ponto crítico não é o topo da roda (Z 200) e sim o ponto da roda
    # mais próximo do prato: a roda é cilindro Ø200 em |X| 350, e o fole fica em |X| 425.
    dx = M.X_FOLE - M.XS                                  # 75
    r_roda = M.D_RODA / 2
    x_borda = M.X_FOLE - M.D_FOLE / 2                     # borda interna do fole, 391
    dx_borda = abs(x_borda - M.XS)                        # 41
    z_roda_na_borda = M.Z_EIXO + math.sqrt(max(r_roda ** 2 - dx_borda ** 2, 0.0))
    z_prato = M.Z_BRACO_T[1] - M.E_PRATO
    add('Fole × roda (vertical, na borda interna do fole)',
        z_prato - z_roda_na_borda, '≥ 5 mm', z_prato - z_roda_na_borda >= 5.0,
        f'roda sobe a Z {z_roda_na_borda:.1f} em X {x_borda:.0f}; prato em Z {z_prato:.0f}')

    # --- fole × travessas do anel inferior
    folga_q03 = (M.X_FOLE - M.D_FOLE / 2) - (M.XS + M.TQ / 2)
    folga_q02 = (M.XQ - M.TQ) - (M.X_FOLE + M.D_FOLE / 2)
    add('Fole × travessa Q-03 (X 365)', folga_q03, '≥ 10 mm', folga_q03 >= 10.0)
    add('Fole × travessa Q-02 (X 493)', folga_q02, '≥ 10 mm', folga_q02 >= 10.0)

    # --- roda × envelope externo
    y_roda_ext = M.BITOLA / 2 + M.MPW_LARG_RODA / 2
    add('Face externa da roda × envelope W_EXT/2', M.W_EXT / 2 - y_roda_ext, '≥ 5 mm',
        M.W_EXT / 2 - y_roda_ext >= 5.0,
        f'roda em |Y| {y_roda_ext:.2f}; linha do envelope em {M.W_EXT / 2:.0f}')

    # --- roda × carenagem lateral: não há sobreposição vertical nenhuma
    add('Topo da roda × base da carenagem lateral', M.Z_QUADRO - (M.Z_EIXO + r_roda),
        '≥ 0 mm (sem sobreposição)', M.Z_QUADRO - (M.Z_EIXO + r_roda) >= 0,
        'a carenagem começa em Z 250 e a roda termina em Z 200')

    # --- braço × solo, nas três condições
    z_baixo = M.Z_BRACO_T[0]
    add('Vão livre do braço, altura mínima e sem curso', z_baixo, '≥ 150 mm', z_baixo >= 150.0)
    add('Vão livre do braço, altura mínima e compressão total',
        z_baixo - M.CURSO_TRABALHO, '≥ 120 mm', z_baixo - M.CURSO_TRABALHO >= 120.0,
        'condição transitória: só ocorre com o vão no mínimo e impacto de 3×')
    add('Vão livre do braço, altura máxima e compressão total',
        z_baixo + M.AJUSTE_ALTURA - M.CURSO_TRABALHO, '≥ 150 mm',
        z_baixo + M.AJUSTE_ALTURA - M.CURSO_TRABALHO >= 150.0)

    # --- braço × chapa de fundo, no curso de compressão
    livre = (M.Z_QUADRO - M.E_CHAPA) - M.Z_BRACO_T[1]
    add('Topo do braço × chapa de fundo (estático)', livre, '≥ 30 mm', livre >= 30.0,
        'o braço gira em torno do pivô: a ponta sobe, a raiz não')
    # A seção que mais sobe é a mais distante do pivô: a da estação da roda, que sobe o
    # curso inteiro. A chapa de fundo é solidária ao chassi, então a folga que importa é a
    # do braço contra ela ao fim do curso de compressão.
    folga_compressao = (M.Z_QUADRO - M.E_CHAPA) - (M.Z_BRACO_T[1] + M.CURSO_TRABALHO)
    add('Topo do braço na estação da roda × chapa de fundo, em compressão total',
        folga_compressao, '≥ 5 mm', folga_compressao >= 5.0,
        'a chapa desce com o chassi; a folga que importa é a do braço contra ela')

    # --- berço do fole × anel superior
    add('Berço do fole (topo Z 290) × anel superior (base Z 310)',
        M.ANEL_SUP[0] - M.Z_BERCO_FOLE[1], '≥ 15 mm',
        M.ANEL_SUP[0] - M.Z_BERCO_FOLE[1] >= 15.0,
        'o berço fica no vão entre os anéis e não invade o compartimento acima de Z 310')

    # --- torre do pivô × roda: separação em X (em Y as duas se cruzam, e é por isso que
    # a folga tem de ser medida em X, não em Y)
    y_orelha_ext = M.Y_ORELHA[1] + M.E_ORELHA
    y_roda_int = M.BITOLA / 2 - M.MPW_LARG_RODA / 2
    x_torre_min = M.X_PIVO - 34.0
    x_roda_max = M.XS + M.D_RODA / 2
    if y_orelha_ext > y_roda_int:
        add('Torre do pivô × roda (separação em X, pois em Y se cruzam)',
            x_torre_min - x_roda_max, '≥ 10 mm', x_torre_min - x_roda_max >= 10.0,
            f'orelha externa em |Y| {y_orelha_ext:.0f} contra face interna da roda em '
            f'{y_roda_int:.2f}: cruzam em Y, separadas em X')
    else:
        add('Torre do pivô × roda (folga em Y)', y_roda_int - y_orelha_ext, '≥ 2 mm',
            y_roda_int - y_orelha_ext >= 2.0,
            f'orelha externa em |Y| {y_orelha_ext:.0f}, face interna da roda em '
            f'{y_roda_int:.2f} — não se cruzam em Y')

    # --- flange do colar × travessas do anel inferior (a razão de ela ficar por baixo)
    f_flange = (M.XQ - M.TQ) - (M.X_FOLE + M.D_FLANGE_COLAR / 2)
    add('Flange do colar ACIMA da chapa colidiria com a travessa Q-02', f_flange,
        'seria preciso ≥ 5 mm', True,
        'registro do motivo da decisão de projeto: por isso a flange ficou em Z 242…246, '
        'por BAIXO da chapa de fundo, onde não há nada', 'registro')
    add('Colar Ø100 × travessa Q-03 (X 365)',
        (M.X_FOLE - M.D_COLAR / 2) - (M.XS + M.TQ / 2), '≥ 5 mm',
        (M.X_FOLE - M.D_COLAR / 2) - (M.XS + M.TQ / 2) >= 5.0)
    add('Fole Ø88 dentro do colar (folga radial)', (M.D_COLAR - 2 * M.E_COLAR - M.D_FOLE) / 2,
        '≥ 2 mm', (M.D_COLAR - 2 * M.E_COLAR - M.D_FOLE) / 2 >= 2.0)
    add('Prato Ø92 × colar (o prato passa por baixo, não dentro)',
        (M.Z_QUADRO - M.E_CHAPA - 4.0) - (M.Z_BRACO_T[1] + M.CURSO_TRABALHO),
        '≥ 5 mm', (M.Z_QUADRO - M.E_CHAPA - 4.0) - (M.Z_BRACO_T[1] + M.CURSO_TRABALHO) >= 5.0,
        'em compressão total o prato sobe a Z 222,5 e a flange do colar está em Z 242')

    # --- passagem do fole × malha de montagem da chapa de fundo
    pior = min(math.hypot(abs(x) - M.X_FOLE, abs(y) - M.Y_FOLE) for (x, y) in M.MALHA_MONTAGEM)
    add(f'Passagem Ø{M.D_PASSAGEM:.0f} do fole × ponto mais próximo da malha de montagem',
        pior - M.D_PASSAGEM / 2, '≥ 8 mm', pior - M.D_PASSAGEM / 2 >= 8.0,
        'conferido contra todos os pontos da malha')

    # --- envelope geral contra a baseline
    (x0, x1), (y0, y1), (z0, z1) = M.envelope()
    add('Envelope externo em X', x1 - x0, f'= {M.L_EXT:.0f} mm', abs((x1 - x0) - M.L_EXT) < 0.6)
    add('Envelope externo em Y', y1 - y0, f'= {M.W_EXT:.0f} mm', abs((y1 - y0) - M.W_EXT) < 0.6)
    return out


# =============================================== rolagem, tombamento, envelope
def cg_v4(estado: str = 'projeto') -> dict:
    """Massa e CG do inventário do V4 (`centro_massa`), para os cálculos de estabilidade."""
    import centro_massa as CM  # noqa: PLC0415 — import tardio: centro_massa importa este módulo
    s = CM.soma(CM.inventario(estado))
    return dict(massa=s['kg'], zcg=s['z'], estado=estado)


def roll(massa_kg: float | None = None) -> dict:
    """Rolagem, tombamento e envelope de estabilidade — o cálculo que decide a arquitetura.

    O ponto que inverte a conclusão da Rev F: **a rolagem é limitada pelo CURSO, não pela
    rigidez do fole.** Com ±25 mm de curso em 530 mm de bitola, a carroceria não consegue
    rolar mais de 5,40°: depois disso o fole do lado interno chega ao batente e a rigidez
    de rolagem passa a ser a do batente, que é uma ordem de grandeza maior.

    A Rev F calculava a rolagem como se o fole fosse livre até o limite — e por isso achava
    8,5° e perdia 4,9° de envelope. Com o batente no cálculo, e com a bitola de 530, o
    resultado vira o contrário.
    """
    # A massa e o CG da estabilidade vêm do inventário do V4 (centro_massa, estado 'projeto':
    # mastro cheio, térmicas e antena), somado peça a peça. `massa()` parte da Rev F do V3 e
    # não tem o mastro do V4: o CG dela fica 50 mm mais baixo e o tombamento sai otimista.
    # `massa()` continua dimensionando os foles, porque ali a massa maior é o lado seguro.
    cg = cg_v4()
    mm = massa_kg if massa_kg is not None else cg['massa']
    zcg = cg['zcg']
    f = fole(mm)
    meia = M.BITOLA / 2

    # rigidez de rolagem dos quatro foles (eixo de rolagem no solo: braço longitudinal puro)
    k_roda = f['k_roda_N_mm'] * 1e3                       # N/m
    k_roll = 4 * k_roda * (meia / 1e3) ** 2               # N·m/rad

    # rolagem de equilíbrio numa rampa, iterada até convergir, com o teto do curso
    phi_teto = math.radians(M.rolagem_max())
    alpha = math.radians(35.0)
    for _ in range(60):
        mom = mm * G * math.sin(alpha) * zcg / 1e3
        phi = min(mom / k_roll, phi_teto)
        z_ef = zcg * math.cos(phi)
        desloc = zcg * math.sin(phi)
        alpha = math.atan((meia - desloc) / z_ef)
    phi_deg = math.degrees(phi)
    limitado = phi >= phi_teto - 1e-12

    tomb_rigido = math.degrees(math.atan(meia / zcg))
    tomb = math.degrees(alpha)

    env = M.envelope_estabilidade(zcg * math.cos(phi), phi_c=3.0 + phi_deg)
    env_rigido = M.envelope_estabilidade(zcg)

    # a mesma conta na bitola antiga, para mostrar de onde vem o ganho
    bit = M.BITOLA
    try:
        M.BITOLA = 470.0
        k_roll_470 = 4 * k_roda * (470.0 / 2 / 1e3) ** 2
        a470 = math.radians(35.0)
        phi470_teto = math.radians(math.degrees(math.atan(2 * M.CURSO_TRABALHO / 470.0)))
        for _ in range(60):
            mom = mm * G * math.sin(a470) * zcg / 1e3
            p470 = min(mom / k_roll_470, phi470_teto)
            a470 = math.atan((235.0 - zcg * math.sin(p470)) / (zcg * math.cos(p470)))
        env_470 = M.envelope_estabilidade(zcg * math.cos(p470), phi_c=3.0 + math.degrees(p470))
        tomb_470 = math.degrees(a470)
        # o balancim da Rev F (rolagem rígida, bitola 470) no MESMO CG: é a comparação justa.
        # Os 19,57° da Rev F foram calculados no CG da Rev F (294 mm) e não servem de régua.
        bal_env = M.envelope_estabilidade(zcg)
        bal_tomb = math.degrees(math.atan(235.0 / zcg))
    finally:
        M.BITOLA = bit

    return dict(
        massa=mm, zcg=zcg, bitola=M.BITOLA, meia_bitola=meia,
        k_roda_N_mm=f['k_roda_N_mm'], k_roll_Nm_rad=k_roll,
        rolagem_deg=phi_deg, limitada_por_curso=limitado, teto_curso_deg=M.rolagem_max(),
        deslocamento_cg_mm=zcg * math.sin(phi),
        tombamento_deg=tomb, tombamento_se_rigido_deg=tomb_rigido,
        envelope_deg=env, envelope_se_rigido_deg=env_rigido,
        bitola_470_tombamento=tomb_470, bitola_470_envelope=env_470,
        rev_f_envelope=19.57, rev_f_tombamento=39.44,
        balancim_470_tombamento=bal_tomb, balancim_470_envelope=bal_env,
    )


def barra_estabilizadora(massa_kg: float | None = None) -> dict:
    """Por que NÃO há barra estabilizadora. É cálculo, não omissão.

    Uma barra estabilizadora troca rigidez de rolagem por transferência de carga em terreno
    torcido. O limite é levantar roda: quando a transferência iguala a carga estática, a
    roda descarrega e o rover passa a apoiar em três — exatamente a condição de margem ZERO
    que a baseline já apontava e que a suspensão independente existe para eliminar.
    """
    c = carga_por_roda(massa_kg)
    f = fole(massa_kg)
    k_roda = f['k_roda_N_mm']
    art = 60.0                                   # degrau de articulação de projeto, mm

    # com os foles sozinhos, uma roda 60 mm acima da outra no mesmo eixo
    transf_fole = k_roda * art / 2 * 2           # as duas rodas do eixo se afastam ±30
    sobra = c['estatica_N'] - transf_fole
    k_barra_max = max(sobra, 0.0) * (M.BITOLA / 1e3) / (art / M.BITOLA)

    return dict(
        articulacao_mm=art, k_roda_N_mm=k_roda,
        carga_estatica_N=c['estatica_N'],
        transferencia_dos_foles_N=transf_fole,
        sobra_antes_de_levantar_N=sobra,
        k_barra_maxima_Nm_rad=k_barra_max,
        veredito=('Qualquer barra com rigidez útil levanta roda: os foles sozinhos já '
                  f'transferem {transf_fole:.0f} N dos {c["estatica_N"]:.0f} N estáticos '
                  f'numa articulação de {art:.0f} mm. Teto para a barra: '
                  f'{k_barra_max:.0f} N·m/rad, que é rigidez desprezível. '
                  'NÃO HÁ BARRA NO PROJETO.'),
    )


def articulacao(massa_kg: float | None = None) -> dict:
    """Quanto de terreno torcido a suspensão aceita sem descarregar roda."""
    c = carga_por_roda(massa_kg)
    k = fole(massa_kg)['k_roda_N_mm']
    # a roda descarrega quando k·Δ/2 iguala a carga estática
    limite = 2 * c['estatica_N'] / k
    return dict(k_roda_N_mm=k, carga_estatica_N=c['estatica_N'],
                degrau_ate_descarregar_mm=limite,
                degrau_dentro_do_curso_mm=2 * M.CURSO_TRABALHO,
                veredito=('O curso acaba antes da carga: a roda bate no batente a '
                          f'{2 * M.CURSO_TRABALHO:.0f} mm de degrau e só descarregaria a '
                          f'{limite:.0f} mm. Quem limita a articulação é o curso, '
                          'e isso é bom — batente é peça, roda no ar é condição.'))


# ======================================================== tensões nas peças
SIGMA = {
    'aco_a36': 250.0, 'aco_1020': 210.0, 'aco_1045': 310.0,
    'al_6061': 240.0, 'al_6061_zta': 110.0, 'inox_304': 215.0,
}
"""MPa — limites de escoamento usados. Alumínio soldado cai para a ZTA (110 MPa), aço não.

É o dado que inverte a comparação de materiais, e está em `materiais.py`.
"""


def braco_tensoes(massa_kg: float | None = None) -> dict:
    """W-01: flexão, flexão lateral, torção, rasgo do prato e solda na chapa."""
    c = carga_por_roda(massa_kg)
    g = geometria()
    f_roda = c['projeto_N']
    f_fole = f_roda / g['mr']
    r_pivo = f_fole - f_roda                           # reação vertical no pivô

    h, b, e = M.H_BRACO, M.B_BRACO, M.E_BRACO
    # flexão no plano vertical: máximo na estação do fole
    mz = r_pivo * g['r_fole']
    i_h = (b * h ** 3 - (b - 2 * e) * (h - 2 * e) ** 3) / 12
    w_h = i_h / (h / 2)
    sigma = mz / w_h

    # seção aberta no rasgo do prato (parede superior removida em 34 mm)
    a_alma = 2 * e * h
    a_flange = (b - 2 * e) * e
    y_bar = (a_alma * h / 2 + a_flange * e / 2) / (a_alma + a_flange)
    i_u = (2 * (e * h ** 3 / 12 + e * h * (h / 2 - y_bar) ** 2)
           + ((b - 2 * e) * e ** 3 / 12 + a_flange * (y_bar - e / 2) ** 2))
    w_u = i_u / (h - y_bar)
    sigma_rasgo = mz / w_u

    # flexão lateral e torção por força lateral na roda
    f_lat = 0.5 * c['estatica_N'] * FATOR_DINAMICO
    i_v = (h * b ** 3 - (h - 2 * e) * (b - 2 * e) ** 3) / 12
    sigma_lat = f_lat * g['braco'] / (i_v / (b / 2))
    a_m = (b - e) * (h - e)
    tau = f_lat * M.Z_EIXO / (2 * a_m * e)

    # solda do braço na chapa W-02: dois cordões ao longo da sobreposição
    lap = (M.XS + M.R_PLACA) - M.X_BRACO[0]
    garganta = 4.0
    braco_couple = h
    forca_cordao = (f_roda * math.hypot(M.XS - (M.X_BRACO[0] + lap / 2), M.Z_BRACO - M.Z_EIXO)
                    / braco_couple)
    cap_cordao = lap * garganta * 0.707 * 95.0

    return dict(
        secao=f'{b:.0f}×{h:.0f}×{e:.0f}', momento_Nmm=mz,
        w_fechada_mm3=w_h, sigma_MPa=sigma, fs_fechada=SIGMA['aco_1020'] / sigma,
        w_rasgo_mm3=w_u, sigma_rasgo_MPa=sigma_rasgo,
        fs_rasgo=SIGMA['aco_1020'] / sigma_rasgo,
        sigma_lateral_MPa=sigma_lat, tau_torcao_MPa=tau,
        sobreposicao_mm=lap, forca_por_cordao_N=forca_cordao,
        capacidade_por_cordao_N=cap_cordao, fs_solda=cap_cordao / forca_cordao,
        se_fosse_aluminio_fs=SIGMA['al_6061_zta'] / sigma,
    )


def pivo(massa_kg: float | None = None) -> dict:
    """W-07, W-04 e W-05: eixo, alojamento da bucha e orelhas."""
    c = carga_por_roda(massa_kg)
    g = geometria()
    f_roda = c['projeto_N']
    f_vert = f_roda / g['mr'] - f_roda
    # longitudinal: reação de tração no pior caso (torque de pico sobre o raio da roda)
    m_mot = M.motor()
    f_long = (m_mot['torque_pico'] or 35.0) * 1e3 / (M.D_RODA / 2)
    f_lat = 0.5 * c['estatica_N'] * FATOR_DINAMICO
    res = math.hypot(math.hypot(f_vert, f_long), f_lat)

    a_pino = math.pi * M.D_PIVO ** 2 / 4
    tau = res / (2 * a_pino)
    vao = (M.Y_ORELHA[1] + M.E_ORELHA / 2) - (M.Y_ORELHA[0] + M.E_ORELHA / 2)
    mflex = res * vao / 4
    w_pino = math.pi * M.D_PIVO ** 3 / 32
    sigma = mflex / w_pino

    # mancal: duas buchas autolubrificantes Ø20 × 20
    p_bucha = res / (2 * M.D_PIVO * 20.0)
    # orelha: cantiléver do berço (Z 238) até o eixo (Z 190)
    bracoc = M.Z_BERCO_PIVO[0] - M.Z_BRACO
    m_orelha = res * bracoc / 2
    w_orelha = M.E_ORELHA * 44.0 ** 2 / 6
    sigma_orelha = m_orelha / w_orelha

    return dict(
        f_vertical_N=f_vert, f_longitudinal_N=f_long, f_lateral_N=f_lat, resultante_N=res,
        d_pino=M.D_PIVO, tau_pino_MPa=tau, sigma_pino_MPa=sigma,
        fs_pino=SIGMA['inox_304'] / max(sigma, tau * math.sqrt(3)),
        vao_orelhas_mm=vao,
        pressao_bucha_MPa=p_bucha, limite_bucha_MPa=80.0, bucha_ok=p_bucha <= 80.0,
        sigma_orelha_MPa=sigma_orelha, fs_orelha=SIGMA['aco_a36'] / sigma_orelha,
    )


def pratos(massa_kg: float | None = None) -> dict:
    """W-08, W-09 e os dois berços W-06 e W-11."""
    c = carga_por_roda(massa_kg)
    g = geometria()
    f_fole = c['projeto_N'] / g['mr']

    # pino do prato: 4 planos de corte (duas orelhas contra as duas paredes do tubo)
    a_pino = math.pi * M.D_PINO_PRATO ** 2 / 4
    tau_pino = f_fole / (4 * a_pino)
    esmag = f_fole / 2 / (M.D_PINO_PRATO * M.E_BRACO)

    # berço do fole W-11: viga biapoiada nas duas travessas, carga na estação do fole
    a = M.X_FOLE - M.XS
    b = M.X_CANTO - M.X_FOLE
    vao = a + b
    m_berco = f_fole * a * b / vao
    larg = (M.Y_FUROS_SUSP[1] + 12.0) - (M.Y_FUROS_SUSP[0] - 12.0)
    w_berco = larg * M.E_BERCO_FOLE ** 2 / 6
    sigma_berco = m_berco / w_berco

    # reações nos parafusos M8
    r_canto = f_fole * a / vao
    r_roda = f_fole * b / vao

    return dict(
        f_fole_projeto_N=f_fole,
        tau_pino_MPa=tau_pino, fs_pino=SIGMA['inox_304'] / (tau_pino * math.sqrt(3)),
        esmagamento_parede_MPa=esmag, fs_esmagamento=SIGMA['aco_1020'] / esmag,
        berco_vao_mm=vao, berco_momento_Nmm=m_berco, berco_w_mm3=w_berco,
        berco_sigma_MPa=sigma_berco, berco_fs=SIGMA['al_6061'] / sigma_berco,
        reacao_por_parafuso_canto_N=r_canto / 2, reacao_por_parafuso_roda_N=r_roda / 2,
        capacidade_m8_a4_N=8000.0,
    )


def batentes(massa_kg: float | None = None) -> dict:
    """Quem absorve o impacto de projeto: o fole até o batente, o batente depois dele.

    O resultado que importa: o fole NUNCA vê a carga de projeto. A rigidez dele é baixa, e
    o curso acaba antes. Por isso o batente de compressão é requisito do componente
    comprado (integrado ao fole) e o de extensão é peça — o cabo W-13.
    """
    c = carga_por_roda(massa_kg)
    f = fole(massa_kg)
    k = f['k_roda_N_mm']
    # força na roda quando o curso de compressão acaba
    f_no_batente = c['estatica_N'] + k * M.CURSO_TRABALHO
    resto = c['projeto_N'] - f_no_batente
    return dict(
        carga_estatica_N=c['estatica_N'], carga_projeto_N=c['projeto_N'],
        k_roda_N_mm=k, curso_compressao_mm=M.CURSO_TRABALHO,
        forca_ao_fim_do_curso_N=f_no_batente,
        fracao_da_projeto=f_no_batente / c['projeto_N'],
        absorvido_pelo_batente_N=resto,
        batente_no_fole_N=resto / f['k_roda_N_mm'] * 0 + resto / geometria()['mr'],
        cabo_extensao_mm=f['h_max'] + M.E_PRATO,
        nota=('O fole só chega a '
              f'{f_no_batente / c["projeto_N"] * 100:.0f} % da carga de projeto antes do fim '
              'do curso. O batente interno do fole absorve o resto — e é por isso que ele '
              'é requisito de compra, não peça de desenho.'),
    )


COEF_ROLAMENTO = 0.10
"""Coeficiente de resistência ao rolamento em solo agrícola solto. FAIXA de literatura.

É o que define o ponto de operação real — e o ponto de operação real é o que importa aqui,
não o limite do motor.
"""


def alavanca_antiesquat() -> float:
    """mm — o braço de alavanca que sobra para a reação de torque.

    O resultado que governa a geometria do pivô, e vale escrever por extenso:

    Numa roda com motor no cubo, a suspensão recebe DUAS coisas do acionamento — a força de
    tração no contato e a reação de torque no estator, que é a mesma força multiplicada
    pelo raio da roda. Elas giram o braço em sentidos OPOSTOS. Em torno do pivô, a força de
    tração tem braço `Z_BRACO` (a altura do pivô sobre o solo) e a reação de torque tem
    braço `D_RODA/2`. O que sobra é a diferença.

    Com o pivô na cota do eixo da roda a diferença é ZERO: antiesquat perfeito, o
    acionamento não mexe na suspensão. O vão livre de 150 mm proíbe o pivô a Z 100, então
    sobram 90 mm — e esses 90 mm são o preço do vão livre, não um descuido de projeto.
    """
    return M.Z_BRACO - M.D_RODA / 2


def reacao_de_torque() -> dict:
    """A perturbação que o acionamento causa na altura, por condição de operação.

    Com o pivô dianteiro à frente da roda e o traseiro atrás, um mesmo torque gira os
    braços dos dois eixos em sentidos opostos. O resultado é ARFAGEM pura: a frente desce o
    que a traseira sobe, e a altura média não muda. Se os quatro pivôs ficassem do mesmo
    lado, a perturbação seria de altura e o nivelamento brigaria com o acelerador.
    """
    m = M.motor()
    k = fole()['k_roda_N_mm']
    alav = alavanca_antiesquat()
    mg = massa()['massa'] * G

    # ponto de operação real: vencer o rolamento em solo solto, nível
    t_oper = COEF_ROLAMENTO * mg / 4 * (M.D_RODA / 2) / 1e3

    casos = [('rolamento em solo solto', t_oper),
             ('contínuo do motor', m['torque_cont']),
             ('pico do motor', m['torque_pico'])]
    out = {}
    for rotulo, t_nm in casos:
        if not t_nm:
            continue
        f = t_nm * 1e3 / (M.D_RODA / 2)        # força longitudinal no contato
        mom = f * alav                         # o que sobra depois do cancelamento
        df = mom / M.BRACO                     # força vertical equivalente na roda
        d = df / k
        out[rotulo] = dict(
            torque_Nm=t_nm, forca_longitudinal_N=f, tracao_total_g=4 * f / mg,
            alavanca_mm=alav, momento_Nmm=mom, delta_carga_N=df, deslocamento_mm=d,
            dentro_do_curso=abs(d) <= M.CURSO_TRABALHO)
    out['alavanca_mm'] = alav
    out['nota'] = ('Arfagem pura, zero de altura: frente e traseira se movem em sentidos '
                   'opostos. No ponto de operação é desprezível. No contínuo do motor — que '
                   'é condição de rampa forte, não de cruzeiro — consome o curso de '
                   'trabalho, e no pico bate no batente. Bater no batente em tração máxima '
                   'é comportamento normal de suspensão. Ensaio V-07.')
    return out


# ================================================================== energia
COMPRESSOR_W = 180.0
"""Potência do compressor 12 V em operação. FAIXA de catálogo, a confirmar."""

CICLO_TRABALHO = 0.05
"""Fração do tempo com o compressor ligado, em regime.

CRITÉRIO DE PROJETO. Sistema estanque só repressuriza por vazamento e por mudança de
altura. 5 % é conservador para um sistema novo; um sistema com vazamento chega a 30 %, e é
por isso que o monitoramento de ciclo entra como requisito.
"""


def _wh_bateria() -> float:
    """Energia nominal da bateria do projeto, da mesma fonte que o orçamento elétrico."""
    import sensores as S  # noqa: PLC0415
    return S.BATERIA['wh']


def energia() -> dict:
    """O que a suspensão tira da bateria."""
    medio = COMPRESSOR_W * CICLO_TRABALHO
    solenoides = 4 * 4.0 * 0.02
    controle = 1.5
    total = medio + solenoides + controle
    # volume de ar para uma subida completa dos quatro foles
    dv = area_fole() * M.CURSO_FOLE * 4 * 1e-6          # litros a pressão de trabalho
    p = fole()['p_estatica_bar']
    return dict(compressor_medio_W=medio, solenoides_W=solenoides, controle_W=controle,
                total_W=total,
                ar_por_subida_L_normal=dv * (p + 1.013) / 1.013,
                circuitos=4,
                nota=('Não é o problema: ' + f'{100 * total / _wh_bateria():.2f}'.replace('.', ',')
                      + ' % por hora da bateria de ' + f'{_wh_bateria():,.0f}'.replace(',', '.')
                      + ' Wh.'))


REQUISITOS_CONTROLE = [
    ('Quatro circuitos independentes', 'um solenoide e um sensor de altura por canto'),
    ('Nivelamento', 'manter a carroceria horizontal; é o que preserva o tombamento'),
    ('Monitoramento de ciclo do compressor', 'ciclo acima de 15 % = vazamento; alarme'),
    ('Modo de falha', 'perda de pressão desce para o vão mínimo e trava; não sobe sozinho'),
    ('Limite de velocidade por altura', 'vão acima de 165 mm restringe velocidade'),
    ('Interface com o SaaS', 'telemetria de altura e pressão por canto; NOT_IMPLEMENTED'),
]


# =============================================================== pendências
PENDENCIAS = [
    ('P-02', 'Massa oficial', 'CRÍTICA',
     'Quatro números circulam no projeto: 85,04 / 82,49 / 97,8 / 110,07 kg. Este módulo '
     'dimensiona na mais alta e mostra a sensibilidade em `sensibilidade`. A massa oficial '
     'não é dado deste módulo — é decisão de projeto, e continua aberta.'),
    ('P-20', 'Fole: modelo comercial', 'ALTA',
     'Nenhum modelo escolhido. `requisitos_fole` é a folha de compra; a interface '
     'desenhada aceita qualquer fole que a feche, e aceita cilindro pneumático de mesma '
     'área. Nenhum desenho de usinagem depende da escolha.'),
    ('P-21', 'Bucha autolubrificante do pivô', 'MÉDIA',
     'Alojamento Ø23 H7 desenhado para duas buchas Ø23/Ø20 × 20. Modelo a escolher; '
     'pressão calculada em `pivo` está abaixo de 80 MPa, que é faixa de bucha PTFE/bronze.'),
    ('P-22', 'Fadiga do braço e da chapa W-02', 'ALTA',
     'Caso 9 do FEA, novo nesta revisão: as duas peças passaram a ciclar com o terreno. '
     'Em aço há limite de fadiga; em alumínio não há. É a razão do aço, e é o que a '
     'alternativa em alumínio de `massa` custa.'),
    ('P-23', 'Reação de torque', 'MÉDIA',
     'Calculada em `reacao_de_torque` e dentro da autoridade do nivelamento, mas o número '
     'depende do torque real do motor escolhido. Ensaio V-07.'),
    ('P-04', 'Planicidade da face do motor', 'MÉDIA',
     'A ElectroCraft não publica a planicidade exigida na face de montagem. A sugestão 2.3 '
     'do fabricante continua pendente da resposta dele.'),
]


def sensibilidade() -> list[dict]:
    """O que muda se a massa oficial for outra. É a resposta honesta à pendência P-02."""
    out = []
    for mm in (MASSA_MINIMA, 97.8, 110.07, massa()['massa'], 130.0):
        f = fole(mm)
        r = roll(mm)
        out.append(dict(massa=mm, p_estatica_bar=f['p_estatica_bar'],
                        p_projeto_bar=f['p_projeto_bar'], k_roda=f['k_roda_N_mm'],
                        freq_Hz=f['freq_Hz'], rolagem_deg=r['rolagem_deg'],
                        tombamento_deg=r['tombamento_deg'], envelope_deg=r['envelope_deg'],
                        forma_ok=f['forma_ok'], teto_ok=f['teto_ok']))
    return out


# =================================================================== relatório
def _tab(titulo, linhas):
    print(f'\n{titulo}')
    print('-' * len(titulo))
    for ln in linhas:
        print('  ' + ln)


def main() -> None:
    print('=' * 78)
    print('VTX-RV4 Rev H · SUSPENSÃO PNEUMÁTICA INDEPENDENTE · dimensionamento')
    print('=' * 78)

    m = massa()
    c = carga_por_roda()
    _tab('1. Massa', [
        f'grupo W (estrutura desenhada)      {m["m_w"]:7.3f} kg  @ Z {m["z_w"]:6.1f}',
        f'grupo pneumático (comprado)        {m["m_c"]:7.3f} kg  @ Z {m["z_c"]:6.1f}',
        f'sai: grupo S da Rev F              {-m["m_s"]:7.3f} kg  @ Z {m["z_s"]:6.1f}',
        f'massa  {MASSA_REV_F:.2f} -> {m["massa"]:.2f} kg   ({m["delta"]:+.2f})',
        f'Z_cg   {ZCG_REV_F:.1f} -> {m["zcg"]:.1f} mm      ({m["delta_z"]:+.1f})',
        f'margem contra a baseline de {MASSA_BASELINE:.1f} kg: {m["margem_baseline"]:+.2f} kg',
        '',
        f'alternativa: as peças em aço somam {m["alternativa_aluminio"]["massa_das_pecas_em_aco"]:.2f} kg;',
        f'  em alumínio seriam {m["alternativa_aluminio"]["se_fossem_aluminio"]:.2f} kg '
        f'({m["alternativa_aluminio"]["economia"]:.2f} kg de economia)',
        '  custo: alumínio não tem limite de fadiga. Decisão do engenheiro — ver P-22.',
    ])
    _tab('2. Carga por roda', [
        f'estática  {c["estatica_kgf"]:5.1f} kgf  ({c["estatica_N"]:6.1f} N)',
        f'dinâmica  {c["dinamica_N"]:6.1f} N   (fator {FATOR_DINAMICO})',
        f'projeto   {c["projeto_N"]:6.1f} N   (× transferência {TRANSFERENCIA})',
    ])

    g = geometria()
    _tab('3. Geometria do braço', [
        f'pivô |X| {g["x_pivo"]:.0f} · roda |X| {g["x_roda"]:.0f} · fole |X| {g["x_fole"]:.0f}'
        f' · eixo do braço Z {g["z_braco"]:.0f}',
        f'braço {g["braco"]:.0f} mm · fole a {g["r_fole"]:.0f} mm do pivô · relação {g["mr"]:.3f}',
        f'curso na roda {g["curso_roda"]:.0f} mm = ajuste {g["ajuste"]:.0f} + '
        f'trabalho ±{g["curso_trabalho"]:.0f}',
        f'curso no fole {g["curso_fole"]:.0f} mm · giro do braço {g["giro_total_deg"]:.1f}°'
        f' · recuo da roda {g["recuo_mm"]:.1f} mm',
        f'vão livre ajustável {g["vao_min"]:.0f} -> {g["vao_max"]:.0f} mm',
        f'rolagem máxima possível {g["rolagem_max_deg"]:.2f}° (limitada pelo curso)',
    ])

    f = fole()
    _tab('4. Fole', [
        f'área efetiva {f["area_mm2"]:.0f} mm² (Ø{f["d_efetivo"]:.1f} ef., Ø{f["d_externo_max"]:.0f} ext. máx.)',
        f'força no fole: estática {f["f_estatica_N"]:.0f} N · projeto {f["f_projeto_N"]:.0f} N',
        f'pressão: estática {f["p_estatica_bar"]:.2f} bar · dinâmica {f["p_dinamica_bar"]:.2f}'
        f' · projeto {f["p_projeto_bar"]:.2f} (teto {PRESSAO_MAXIMA_BAR:.0f})',
        f'  mantém a forma (>= {PRESSAO_MINIMA_FORMA_BAR:.0f} bar): '
        f'{"SIM" if f["forma_ok"] else "NAO"} · dentro do teto: {"SIM" if f["teto_ok"] else "NAO"}',
        f'altura instalada {f["h_min"]:.1f} … {f["h_nominal"]:.1f} … {f["h_max"]:.1f} mm'
        f'  (curso {f["curso"]:.0f}, razão {f["razao_curso_altura"]:.2f})',
        f'rigidez {f["k_fole_N_mm"]:.1f} N/mm no fole = {f["k_roda_N_mm"]:.2f} N/mm na roda',
        f'frequência de canto {f["freq_Hz"]:.2f} Hz',
    ])

    _tab('5. Requisitos do fole (folha de compra)',
         [f'{a:34} {b:28} {c_}' for (a, b, c_) in requisitos_fole()])

    print('\n6. Folgas e colisões')
    print('-' * 20)
    fal = 0
    for ln in folgas():
        v = ln['valor']
        if ln['tipo'] == 'registro':
            marca = 'nota'
        else:
            marca = 'OK  ' if ln['ok'] else 'FALHA'
            fal += 0 if ln['ok'] else 1
        print(f'  {marca} {ln["o_que"]:58} {v:8.2f}  {ln["criterio"]}')
        if ln['nota']:
            print(f'        {ln["nota"]}')
    print(f'  --> {fal} falha(s)')

    r = roll()
    _tab('7. Rolagem, tombamento e envelope', [
        f'rigidez de roda {r["k_roda_N_mm"]:.2f} N/mm · rigidez de rolagem '
        f'{r["k_roll_Nm_rad"]:.0f} N·m/rad',
        f'rolagem no limite {r["rolagem_deg"]:.2f}°'
        f'{"  (LIMITADA PELO CURSO)" if r["limitada_por_curso"] else ""}'
        f' · CG migra {r["deslocamento_cg_mm"]:.1f} mm',
        f'tombamento  {r["tombamento_deg"]:.2f}°   (seria {r["tombamento_se_rigido_deg"]:.2f}° '
        'com rolagem perfeitamente rígida)',
        f'envelope    {r["envelope_deg"]:.2f}°   (seria {r["envelope_se_rigido_deg"]:.2f}°)',
        '',
        f'de onde vem o ganho — mesma suspensão, bitola 470:',
        f'  tombamento {r["bitola_470_tombamento"]:.2f}° · envelope {r["bitola_470_envelope"]:.2f}°',
        f'contra o balancim da Rev F (rolagem rígida, bitola 470) no MESMO CG:',
        f'  tombamento {r["balancim_470_tombamento"]:.2f}° · envelope {r["balancim_470_envelope"]:.2f}°',
        f'  (a Rev F publicou {r["rev_f_tombamento"]:.2f}° / {r["rev_f_envelope"]:.2f}° no CG dela, 294 mm)',
    ])

    b = barra_estabilizadora()
    _tab('8. Barra estabilizadora', [
        f'carga estática por roda      {b["carga_estatica_N"]:.0f} N',
        f'transferência dos foles em {b["articulacao_mm"]:.0f} mm de articulação  '
        f'{b["transferencia_dos_foles_N"]:.0f} N',
        f'sobra antes de levantar roda {b["sobra_antes_de_levantar_N"]:.0f} N',
        f'teto de rigidez para a barra {b["k_barra_maxima_Nm_rad"]:.0f} N·m/rad',
        b['veredito'],
    ])

    a = articulacao()
    _tab('9. Articulação', [a['veredito']])

    br = braco_tensoes()
    _tab('10. Braço W-01', [
        f'seção {br["secao"]} · momento de projeto {br["momento_Nmm"]:.0f} N·mm',
        f'flexão  {br["sigma_MPa"]:5.1f} MPa  FS {br["fs_fechada"]:.2f}  (aço 1020)',
        f'  na seção do rasgo do prato {br["sigma_rasgo_MPa"]:5.1f} MPa  FS {br["fs_rasgo"]:.2f}',
        f'flexão lateral {br["sigma_lateral_MPa"]:5.1f} MPa · torção {br["tau_torcao_MPa"]:4.1f} MPa',
        f'solda na chapa W-02: {br["sobreposicao_mm"]:.0f} mm de sobreposição, '
        f'FS {br["fs_solda"]:.1f}',
        f'se o braço fosse alumínio soldado (ZTA 110 MPa): FS {br["se_fosse_aluminio_fs"]:.2f}',
    ])

    pv = pivo()
    _tab('11. Pivô W-04/W-05/W-07', [
        f'carga: vertical {pv["f_vertical_N"]:.0f} N · longitudinal {pv["f_longitudinal_N"]:.0f} N'
        f' · lateral {pv["f_lateral_N"]:.0f} N -> resultante {pv["resultante_N"]:.0f} N',
        f'eixo Ø{pv["d_pino"]:.0f}: corte {pv["tau_pino_MPa"]:.1f} MPa · flexão '
        f'{pv["sigma_pino_MPa"]:.1f} MPa · FS {pv["fs_pino"]:.1f}',
        f'bucha: {pv["pressao_bucha_MPa"]:.1f} MPa contra limite {pv["limite_bucha_MPa"]:.0f} '
        f'-> {"OK" if pv["bucha_ok"] else "FALHA"}',
        f'orelha W-05: {pv["sigma_orelha_MPa"]:.1f} MPa · FS {pv["fs_orelha"]:.1f}',
    ])

    pr = pratos()
    _tab('12. Prato, pino e berços', [
        f'força de projeto no fole {pr["f_fole_projeto_N"]:.0f} N',
        f'pino W-09 Ø{M.D_PINO_PRATO:.0f}: corte {pr["tau_pino_MPa"]:.1f} MPa FS {pr["fs_pino"]:.1f}'
        f' · esmagamento na parede {pr["esmagamento_parede_MPa"]:.1f} MPa FS '
        f'{pr["fs_esmagamento"]:.1f}',
        f'berço do fole W-11: vão {pr["berco_vao_mm"]:.0f} mm, '
        f'{pr["berco_sigma_MPa"]:.1f} MPa, FS {pr["berco_fs"]:.2f}',
        f'parafusos M8: {pr["reacao_por_parafuso_canto_N"]:.0f} N (X 508) e '
        f'{pr["reacao_por_parafuso_roda_N"]:.0f} N (X 350), capacidade '
        f'{pr["capacidade_m8_a4_N"]:.0f} N',
    ])

    bt = batentes()
    _tab('13. Batentes', [
        f'ao fim do curso de compressão a roda vê {bt["forca_ao_fim_do_curso_N"]:.0f} N, '
        f'{bt["fracao_da_projeto"] * 100:.0f} % da carga de projeto',
        f'o batente absorve os {bt["absorvido_pelo_batente_N"]:.0f} N restantes',
        f'cabo de extensão W-13: {bt["cabo_extensao_mm"]:.0f} mm entre olhais',
        bt['nota'],
    ])

    rt = reacao_de_torque()
    _tab('14. Reação de torque do motor-roda', [
        f'alavanca que sobra após o cancelamento: Z do pivô {M.Z_BRACO:.0f} − raio da roda '
        f'{M.D_RODA / 2:.0f} = {rt["alavanca_mm"]:.0f} mm',
        f'(se o pivô pudesse ficar em Z {M.D_RODA / 2:.0f} a perturbação seria ZERO; '
        'o vão livre de 150 proíbe)', '',
    ] + [f'{k:26} {v["torque_Nm"]:5.1f} N·m ({v["tracao_total_g"]:.2f} g) -> '
         f'{v["delta_carga_N"]:5.0f} N, {v["deslocamento_mm"]:5.1f} mm  '
         f'{"dentro do curso" if v["dentro_do_curso"] else "BATE NO BATENTE"}'
         for k, v in rt.items() if isinstance(v, dict)] + ['', rt['nota']])

    e = energia()
    _tab('15. Energia e controle', [
        f'{e["total_W"]:.1f} W médios (compressor {e["compressor_medio_W"]:.0f} + '
        f'solenoides {e["solenoides_W"]:.2f} + controle {e["controle_W"]:.1f})',
        f'ar por subida completa: {e["ar_por_subida_L_normal"]:.2f} L normais',
        e['nota'],
    ] + [f'req · {a}: {b}' for (a, b) in REQUISITOS_CONTROLE])

    print('\n16. Sensibilidade à massa (pendência P-02)')
    print('-' * 42)
    print(f'  {"massa":>7} {"p est":>7} {"p proj":>7} {"k roda":>7} {"freq":>6} '
          f'{"rolag":>6} {"tomb":>6} {"envel":>6}')
    for s in sensibilidade():
        print(f'  {s["massa"]:7.2f} {s["p_estatica_bar"]:7.2f} {s["p_projeto_bar"]:7.2f} '
              f'{s["k_roda"]:7.2f} {s["freq_Hz"]:6.2f} {s["rolagem_deg"]:6.2f} '
              f'{s["tombamento_deg"]:6.2f} {s["envelope_deg"]:6.2f}'
              f'{"" if s["forma_ok"] and s["teto_ok"] else "   <- fora de faixa"}')

    print('\n17. Pendências')
    print('-' * 14)
    for (cod, nome, grau, txt) in PENDENCIAS:
        print(f'  {cod} · {nome} · {grau}')
        for linha in _quebra(txt, 72):
            print(f'       {linha}')


def _quebra(txt, n):
    palavras, linha, out = txt.split(), '', []
    for p in palavras:
        if len(linha) + len(p) + 1 > n:
            out.append(linha)
            linha = p
        else:
            linha = (linha + ' ' + p).strip()
    if linha:
        out.append(linha)
    return out


if __name__ == '__main__':
    import sys as _sys
    if hasattr(_sys.stdout, 'reconfigure'):          # o console do Windows é cp1252
        _sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    main()
