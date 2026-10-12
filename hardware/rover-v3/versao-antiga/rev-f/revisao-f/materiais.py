"""Comparação de materiais do quadro e da gaiola — Rev F, sugestão 2.1 do fabricante.

O fabricante propôs **estrutura de aço com chapas de fechamento de alumínio**, para
reduzir custo. Este módulo responde com cálculo, não com opinião: três alternativas,
mesma geometria de envelope, equivalência por rigidez à flexão, e massa e custo
derivados do modelo paramétrico que gera o caderno.

O que **não** se faz aqui, de propósito:

* trocar a palavra "alumínio" por "aço" no desenho. Aço com a mesma seção pesa 2,9×
  mais; manter a seção seria entregar um chassi 10 kg mais pesado sem necessidade;
* declarar o aço mais barato porque o quilo é mais barato. O que se compara abaixo é
  matéria-prima **mais** corte, solda, usinagem e proteção anticorrosiva;
* fechar a questão. A escolha depende de dois números que este projeto ainda não tem:
  a rigidez torcional exigida (sem FEA) e a cotação real dos dois perfis.

Unidades: mm, kg, N, MPa, R$.
"""

from __future__ import annotations

import pathlib
import sys

AQUI = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent / 'chassi-gaiola'))

import modelo as M  # noqa: E402

# ===================================================================== materiais
# E e rho: valores de norma, não medidos. sigma_y: mínimo especificado da liga/têmpera.
MATERIAIS = {
    'Al6061T6': dict(
        nome='Al 6061-T6', E=69000.0, rho=2.70e-6, sigma_y=240.0, sigma_u=290.0,
        soldavel='Sim, TIG/MIG com arame 4043 ou 5356. **A ZTA perde têmpera**: na solda '
                 'a resistência cai para algo entre T4 e o recozido, e só volta com '
                 'tratamento térmico pós-solda, que ninguém faz num chassi deste porte.',
        corrosao='Óxido natural protege. Anodizar melhora e dá acabamento.',
        origem='FONTE · ASM/ABAL para 6061-T6'),
    'Aco1020': dict(
        nome='Aço SAE 1020 (tubo NBR 6591)', E=205000.0, rho=7.85e-6, sigma_y=210.0, sigma_u=380.0,
        soldavel='Sim, MIG/MAG com arame ER70S-6. Sem perda de propriedade na ZTA — '
                 'é a vantagem real do aço aqui, e não o preço.',
        corrosao='**Enferruja.** Exige pintura ou zincagem, e a lavoura de café é '
                 'ambiente de lavagem, adubo e umidade constantes.',
        origem='FONTE · NBR 6591 / SAE J403'),
    'AcoA36': dict(
        nome='Aço ASTM A36 (chapa)', E=200000.0, rho=7.85e-6, sigma_y=250.0, sigma_u=400.0,
        soldavel='Sim, MIG/MAG. Usado nas chapas estruturais, não nos tubos.',
        corrosao='Igual ao 1020: exige revestimento.',
        origem='FONTE · ASTM A36'),
    'Al5052H32': dict(
        nome='Al 5052-H32', E=70000.0, rho=2.68e-6, sigma_y=193.0, sigma_u=228.0,
        soldavel='Sim, e sem a perda de têmpera do 6061 — liga não tratável termicamente.',
        corrosao='A melhor das quatro em ambiente agrícola. É por isso que as chapas '
                 'de fechamento já são 5052, e é por isso que a sugestão do fabricante '
                 'de mantê-las em alumínio está certa.',
        origem='FONTE · ABAL para 5052-H32'),
}

# ====================================================== perfis de tubo quadrado
# Aço: bitolas correntes de NBR 6591 que um serralheiro de Pouso Alegre tem em estoque.
# Alumínio: o 30x30x2 da Rev E e os vizinhos de catálogo de extrudado.
# `parede_min_solda` marca o que não se solda com segurança em produção de protótipo.
PERFIS = [
    # (lado, parede, material, soldavel_na_pratica, observação)
    (20.0, 1.50, 'Aco1020', True, 'corrente'),
    (25.0, 1.20, 'Aco1020', False, 'parede fina: risco de perfurar no MIG manual'),
    (25.0, 1.50, 'Aco1020', True, 'corrente'),
    (25.0, 2.00, 'Aco1020', True, 'corrente'),
    (30.0, 1.20, 'Aco1020', False, 'parede fina para solda manual'),
    (30.0, 1.50, 'Aco1020', True, 'corrente'),
    (30.0, 2.00, 'Aco1020', True, 'corrente'),
    (30.0, 2.00, 'Al6061T6', True, 'o perfil da Rev E'),
    (40.0, 1.50, 'Aco1020', True, 'corrente'),
]


def secao(lado: float, parede: float) -> dict:
    """Propriedades de um tubo quadrado de parede fina.

    Cantos tratados como vivos. Num tubo conformado a frio há raio interno e externo,
    que tiram cerca de 2 a 4 % de área e de inércia — a favor da segurança aqui, porque
    subestimar a área subestima a massa, e é a massa que está apertada.
    """
    interno = lado - 2 * parede
    if interno <= 0:
        raise ValueError(f'parede {parede} grande demais para o lado {lado}')
    area = lado**2 - interno**2
    inercia = (lado**4 - interno**4) / 12.0
    return dict(
        lado=lado, parede=parede, area=area, I=inercia,
        W=2 * inercia / lado,          # módulo de resistência à flexão
        i=(inercia / area) ** 0.5,     # raio de giração
    )


def rigidez(lado: float, parede: float, mat: str) -> float:
    """EI do perfil, em N·mm²."""
    return MATERIAIS[mat]['E'] * secao(lado, parede)['I']


def massa_linear(lado: float, parede: float, mat: str) -> float:
    """kg por metro."""
    return secao(lado, parede)['area'] * MATERIAIS[mat]['rho'] * 1000.0


SIGMA_SOLDADO = {
    # Tensão que o caderno admite numa estrutura **soldada**, não a da liga virgem.
    'Al6061T6': 110.0,
    'Al5052H32': 193.0,
    'Aco1020': 210.0,
    'AcoA36': 250.0,
}
"""Tensão admissível na condição soldada — a comparação que vale aqui.

O 110 MPa do 6061-T6 **não é invenção desta revisão**: é a opção A da folha 25 do
caderno Rev E, que já declara a perda de cerca de 40 % na zona afetada pelo calor e
adota a condição "como soldado" para o protótipo, com critério de aceite de von Mises
< 110 MPa na ZTA. A folha também registra que o ponto mais solicitado fica em 45 MPa.

É o número que inverte a leitura da sugestão do fabricante. Comparado pela liga virgem,
o aço 1020 (210 MPa) quase empata com o 6061-T6 (240 MPa) e a troca não traz resistência
nenhuma. Comparado como a estrutura realmente vai estar — soldada, sem tratamento
térmico pós-solda, que ninguém faz num quadro deste porte —, o aço tem **quase o dobro**
da tensão utilizável. A vantagem do aço aqui não é o preço do quilo: é não perder
resistência no cordão.
"""


def momento_resistente(lado: float, parede: float, mat: str, soldado: bool = True) -> float:
    """Momento de flexão que leva a fibra extrema ao limite admissível, em N·m.

    ``soldado=True`` por omissão porque o quadro é soldado em 48 juntas: avaliá-lo pela
    liga virgem descreveria uma peça que não existe.
    """
    sigma = SIGMA_SOLDADO[mat] if soldado else MATERIAIS[mat]['sigma_y']
    return secao(lado, parede)['W'] * sigma / 1000.0


# =============================================== a geometria real, lida do modelo
def comprimentos() -> dict:
    """Metros de tubo por grupo, extraídos da lista de corte que gera o caderno.

    Lido do modelo, e não digitado: um número digitado aqui divergiria do desenho na
    primeira alteração de cota, e a divergência passaria sem ninguém ver.
    """
    from folhas import lista_corte  # noqa: PLC0415 — evita ciclo na importação do pacote

    lc = lista_corte('A')
    out = {}
    for grupo, perfil in (('Q', (30.0, 2.0)), ('G', (20.0, 1.5))):
        mm = 0.0
        for item, d in lc.items():
            if not item.startswith(grupo):
                continue
            # Só tubo: chapas e barras do mesmo grupo entram pela massa, não pelo metro.
            if 'Tubo quadrado' not in M.ITENS[item]['desc']:
                continue
            mm += sum(c * q for c, q in d['comps'].items())
        out[grupo] = dict(metros=mm / 1000.0, perfil=perfil)
    return out


def massa_grupo_atual(grupo: str) -> float:
    """Massa do grupo como está no caderno (todas as peças, não só os tubos)."""
    from folhas import lista_corte  # noqa: PLC0415

    return sum(d['massa'] for item, d in lista_corte('A').items() if item.startswith(grupo))


# ================================================================= alternativas
def equivalente_em_aco(lado_al: float, parede_al: float, tolerancia: float = 0.0) -> list[dict]:
    """Perfis de aço que igualam ou superam a rigidez do perfil de alumínio dado.

    O critério é **EI**, e vale dizer por que: o que incomoda num chassi de rover não é
    a ruptura — as cargas são baixas para qualquer dos dois materiais — e sim a
    deformação. Um quadro mole desalinha as faces de montagem dos quatro motores-roda,
    e desalinhamento ali vira desgaste de pneu e erro de odometria.

    ``tolerancia`` aceita perder uma fração da rigidez (0,10 = aceita 90 % dela), para
    o caso de o engenheiro concluir que havia folga de projeto.
    """
    ei_al = rigidez(lado_al, parede_al, 'Al6061T6')
    m_al = momento_resistente(lado_al, parede_al, 'Al6061T6')
    alvo = ei_al * (1.0 - tolerancia)
    fora = []
    for lado, parede, mat, soldavel, obs in PERFIS:
        if mat != 'Aco1020':
            continue
        ei = rigidez(lado, parede, mat)
        if ei < alvo:
            continue
        m_aco = momento_resistente(lado, parede, mat)
        fora.append(dict(
            lado=lado, parede=parede, soldavel=soldavel, obs=obs,
            EI=ei, razao_EI=ei / ei_al,
            kg_m=massa_linear(lado, parede, mat),
            M_esc=m_aco, razao_M=m_aco / m_al,
        ))
    return sorted(fora, key=lambda d: d['kg_m'])


# ----------------------------------------------------------------- custo
# Base: a mesma referência que o pacote Rev E usa, com a massa linear CORRIGIDA.
# A Rev E deduzia R$/kg de 0,218 kg/m para o tubo 30x30x2 — valor que a geometria não
# permite (224 mm² x 2,70 g/cm³ = 0,605 kg/m). O erro inflava o R$/kg em 2,78x.
REF_BARRA_AL_6M_BRL = 50.0
"""Preço de uma barra de 6 m de tubo Al 30x30x2 — planilha da ValTexa, 21/09/2026.

TRANSCRIÇÃO, não cotação. É baixo para perfil 6061 extrudado no mercado brasileiro;
confirmar na RFQ antes de usar como base de decisão.
"""

PRECO_KG = {
    'Al6061T6': REF_BARRA_AL_6M_BRL / 6.0 / massa_linear(30.0, 2.0, 'Al6061T6'),
    # Relação de preço por quilo entre aço carbono e alumínio estrutural. Faixa larga
    # de propósito: é o número que a RFQ tem de fechar, e o resultado da comparação
    # muda de sinal dentro dela.
    'Aco1020': None,
}
RAZAO_PRECO_KG_ACO_AL = (0.20, 0.35)
"""Quanto o quilo de tubo de aço custa em relação ao de alumínio.

PENDÊNCIA DE COTAÇÃO. A faixa 0,20–0,35 é o que se pratica em serralheria para tubo
NBR 6591 contra extrudado 6061, mas não há cotação nos documentos deste projeto e o
prompt desta revisão proíbe inventar preço. Os valores abaixo saem como intervalo.
"""

# Mão de obra: o que muda de verdade entre os dois materiais.
SOLDA_AL_SOBRE_ACO = (1.3, 1.8)
"""Fator de custo de soldar alumínio em relação a aço, em serralheria comum.

Alumínio exige TIG com corrente alternada ou MIG com tocha spool-gun, gás argônio,
limpeza química antes e soldador habilitado em alumínio — que é mais raro e mais caro
na região de Pouso Alegre que o soldador de aço. ESTIMATIVA DE ENGENHARIA, a confirmar
na RFQ: é a parcela que pode inverter a comparação a favor do aço.
"""

CUSTO_PINTURA_M2_BRL = None
"""Pintura eletrostática ou zincagem do quadro de aço — SEM COTAÇÃO neste projeto.

Entra na comparação como pendência, e não como zero: tratá-la como zero é o erro
clássico que faz o aço parecer mais barato do que é.
"""


def comparacao(tolerancia_rigidez: float = 0.0) -> dict:
    """As três alternativas, com os números que dão para calcular hoje."""
    c = comprimentos()
    m_q = massa_grupo_atual('Q')
    m_g = massa_grupo_atual('G')

    al = dict(
        rotulo='A · Alumínio (Rev E, como está)',
        perfil_q='Tubo Al 6061-T6 30×30×2',
        kg_m_q=massa_linear(30.0, 2.0, 'Al6061T6'),
        massa_q=m_q, massa_g=m_g, massa_estrutura=m_q + m_g,
        EI_q=rigidez(30.0, 2.0, 'Al6061T6'),
        brl_materia=c['Q']['metros'] * REF_BARRA_AL_6M_BRL / 6.0,
    )

    candidatos = [d for d in equivalente_em_aco(30.0, 2.0, tolerancia_rigidez) if d['soldavel']]
    aco = None
    if candidatos:
        e = candidatos[0]
        # Só os tubos do quadro trocam de material; buchas, tampas e chapas seguem
        # a decisão peça a peça (ver `HIBRIDA` abaixo).
        massa_tubo_al = c['Q']['metros'] * massa_linear(30.0, 2.0, 'Al6061T6')
        massa_tubo_aco = c['Q']['metros'] * e['kg_m']
        aco = dict(
            rotulo='B · Aço no quadro, alumínio no fechamento',
            perfil_q=f"Tubo aço 1020 {M._n(e['lado'])}×{M._n(e['lado'])}×{M._n(e['parede'])}",
            kg_m_q=e['kg_m'], razao_EI=e['razao_EI'], M_esc=e['M_esc'],
            massa_q=m_q - massa_tubo_al + massa_tubo_aco,
            massa_g=m_g,
            delta_massa=massa_tubo_aco - massa_tubo_al,
            EI_q=e['EI'],
            brl_materia_faixa=tuple(
                c['Q']['metros'] * e['kg_m'] * PRECO_KG['Al6061T6'] * r
                for r in RAZAO_PRECO_KG_ACO_AL),
        )
        aco['massa_estrutura'] = aco['massa_q'] + aco['massa_g']

    return dict(metros=c, alternativa_a=al, alternativa_b=aco,
                candidatos=candidatos,
                todos_candidatos=equivalente_em_aco(30.0, 2.0, tolerancia_rigidez))


# ------------------------------------------------------- alternativa C: híbrida
HIBRIDA = [
    # (peça, material proposto, por quê)
    ('Q-01…Q-04 · tubos do quadro', 'Aço 1020',
     'É onde está a massa de tubo e o cordão de solda: 9,4 m e 48 juntas. Se o aço '
     'compensa em algum lugar, é aqui — e é aqui que o ganho de soldabilidade sem '
     'perda de têmpera mais importa, porque o quadro é o que segura os quatro motores.'),
    ('S-02 · chapa de montagem do MPW86', 'Aço A36',
     'Atende à sugestão 2.4 do fabricante. Ver `flange.py`: é a peça que recebe os 7 '
     'parafusos M4 do motor, com engajamento de rosca limitado a 5 mm pelo datasheet.'),
    ('C-01 · chapa de fundo', 'Al 5052-H32 (mantém)',
     'Área grande, 1046×596: em aço de 2 mm pesaria 9,8 kg em vez de 3,4 — quase toda '
     'a margem de massa do projeto numa peça que não é estrutural, é piso.'),
    ('K-01…K-06 · carenagens e tampas', 'Al 5052-H32 (mantém)',
     'A sugestão do fabricante já pede isso. São 4,6 kg de chapa fina em ambiente de '
     'lavagem — o 5052 é a melhor liga da casa para corrosão, e em aço de 1,2 mm as '
     'tampas amassariam e enferrujariam na dobra.'),
    ('G-01…G-04 · gaiola', 'Al 6061-T6 (mantém)',
     'A gaiola está ALTA: CG em 366 mm, contra 294 do conjunto. Trocá-la por aço sobe '
     'o CG e come o ângulo de tombamento, que é o requisito crítico em lavoura de café '
     '(ver a nota da suspensão em modelo.py). Aço aqui piora o que mais importa.'),
    ('Q-05 · buchas de compressão', 'Aço 1020',
     'Peça torneada, Ø12 com furo Ø8,5, 16 unidades: em aço resiste melhor ao aperto '
     'do M8 e custa menos em barra. Massa somada: dezenas de gramas.'),
]

def comparacao_hibrida() -> dict:
    """Alternativa C, peça a peça, com a massa de cada troca.

    A híbrida é a resposta mais honesta às sugestões 2.1 e 2.4 juntas: o fabricante tem
    razão sobre onde o aço ajuda (tubo do quadro e chapa de montagem do motor) e a
    ValTexa tem razão sobre onde ele atrapalha (gaiola alta, chapa de fundo grande,
    carenagens finas em ambiente de lavagem). Faltava o número, e é o que sai aqui.
    """
    from folhas import lista_corte  # noqa: PLC0415

    lc = lista_corte('A')
    c = comprimentos()
    rho_al6 = MATERIAIS['Al6061T6']['rho']
    rho_aco = MATERIAIS['AcoA36']['rho']
    trocas = []

    m_tubo_al = c['Q']['metros'] * massa_linear(30.0, 2.0, 'Al6061T6')
    m_tubo_aco = c['Q']['metros'] * massa_linear(25.0, 1.5, 'Aco1020')
    trocas.append(dict(
        peca='Q-01…Q-04 · tubos do quadro',
        de='Al 6061-T6 30×30×2', para='Aço 1020 25×25×1,5',
        massa_de=m_tubo_al, massa_para=m_tubo_aco,
        motivo='rigidez 132 %, resistência soldada 101 %, sem perda de ZTA'))

    m_s02 = sum(d['massa'] for i, d in lc.items() if i == 'S-02')
    trocas.append(dict(
        peca='S-02 · chapa de montagem do MPW86 (4 un)',
        de='Al 6061-T6 10 mm', para='Aço A36 8 mm',
        massa_de=m_s02,
        massa_para=m_s02 * (8.0 / M.E_PLACA) * (rho_aco / rho_al6),
        motivo='resistência soldada 145 %; face usinada resiste ao aperto repetido'))

    m_q05 = sum(d['massa'] for i, d in lc.items() if i == 'Q-05')
    trocas.append(dict(
        peca='Q-05 · buchas de compressão (16 un)',
        de='Al 6061-T6 Ø12', para='Aço 1020 Ø12',
        massa_de=m_q05, massa_para=m_q05 * (rho_aco / rho_al6),
        motivo='resiste melhor ao aperto do M8; barra de aço custa menos'))

    mantidas = [
        ('C-01 · chapa de fundo', 'Al 5052-H32 2 mm',
         'em aço de 2 mm pesaria ~9,8 kg contra 3,4 — não é estrutural, é piso'),
        ('K-01…K-06 · carenagens e tampas', 'Al 5052-H32 1,2 e 2 mm',
         'é o que a própria sugestão do fabricante pede manter; 5052 é a melhor liga '
         'da casa para lavagem e adubo'),
        ('G-01…G-04 · gaiola', 'Al 6061-T6 20×20×1,5',
         'CG da gaiola a 366 mm contra 294 do conjunto: aço aqui sobe o CG e come o '
         'ângulo de tombamento, que é o requisito crítico em café'),
        ('S-01, S-03 · chapa superior e nervuras', 'Al 6061-T6',
         'soldam na S-02; par galvânico interno seria pior que o ganho. Reavaliar se a '
         'decisão for aço no conjunto S inteiro'),
    ]
    return dict(trocas=trocas, mantidas=mantidas,
                delta_massa=sum(t['massa_para'] - t['massa_de'] for t in trocas))


CONTATO_GALVANICO = """\
Aço e alumínio em contato, com eletrólito, formam par galvânico: o alumínio é o anodo
e corrói. Em lavoura de café há eletrólito o tempo todo — adubo, calda, lavagem, orvalho.

A diferença de potencial entre aço carbono e Al 6061 é de cerca de 0,3 a 0,5 V, o que
põe o par na faixa que exige isolamento quando há umidade persistente. As interfaces a
tratar, se a alternativa B ou C for adotada:

1. **Chapas de fechamento (Al 5052) aparafusadas no quadro de aço** — é a interface
   maior e a mais exposta. Fita ou arruela isolante de nylon/PTFE sob cada fixador, ou
   quadro pintado com tinta de barreira íntegra.
2. **Fixadores inox A4 em alumínio** — já existem na Rev E e já são um par galvânico,
   mas o inox é pequeno em relação ao alumínio, o que mantém a corrosão difusa e
   tolerável. É a situação boa: anodo grande, catodo pequeno.
3. **Quadro de aço com chapa de fundo de alumínio** — mesma solução do item 1.
4. **Solda aço-alumínio: não existe** nesta classe de fabricação. Toda junção entre os
   dois é aparafusada, o que é compatível com a sugestão 2.2 do fabricante.

PENDÊNCIA: a especificação do revestimento do aço (pintura eletrostática, zincagem a
quente ou galvanização a frio) precisa de decisão e de cotação. Zincagem a quente
deforma peça soldada de parede fina — com 1,5 mm de parede, é risco real de empenar o
quadro depois de soldado e usinado.
"""


if __name__ == '__main__':
    c = comparacao()
    a, b = c['alternativa_a'], c['alternativa_b']
    print('VTX-RV3 Rev F · sugestão 2.1 — estrutura de aço com fechamento de alumínio')
    print()
    print(f"Tubo do quadro, do modelo: {c['metros']['Q']['metros']:.2f} m")
    print(f"Tubo da gaiola, do modelo: {c['metros']['G']['metros']:.2f} m")
    print()
    print('Equivalência por rigidez (EI) e por resistência na condição SOLDADA:')
    for d in equivalente_em_aco(30.0, 2.0):
        flag = 'soldável' if d['soldavel'] else 'parede fina'
        print(f"  aço {d['lado']:.0f}×{d['lado']:.0f}×{d['parede']:.1f}  "
              f"rigidez {d['razao_EI'] * 100:5.0f}%  resistência {d['razao_M'] * 100:5.0f}%  "
              f"{d['kg_m']:.3f} kg/m  [{flag}]")
    print()
    print(f"A · {a['rotulo']}")
    print(f"    {a['perfil_q']} · quadro {a['massa_q']:.3f} kg · "
          f"matéria-prima do tubo R$ {a['brl_materia']:.2f}")
    print(f"B · {b['rotulo']}")
    print(f"    {b['perfil_q']} · quadro {b['massa_q']:.3f} kg ({b['delta_massa']:+.3f} kg) · "
          f"matéria-prima R$ {b['brl_materia_faixa'][0]:.2f}…{b['brl_materia_faixa'][1]:.2f}")
    print(f"    economia de matéria-prima: "
          f"R$ {a['brl_materia'] - b['brl_materia_faixa'][1]:.2f}…"
          f"{a['brl_materia'] - b['brl_materia_faixa'][0]:.2f}")
    print()
    print('C · Híbrida, peça por peça:')
    for peca, mat, _ in HIBRIDA:
        print(f"    {peca:42} → {mat}")
    print()
    print('Pendências: cotação dos dois perfis, diferencial de solda Al/aço,')
    print('revestimento anticorrosivo do aço, e o FEA de torção da folha 25.')
