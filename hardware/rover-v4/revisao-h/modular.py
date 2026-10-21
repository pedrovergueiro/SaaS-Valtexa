"""Interface modular de sensores VMS-60 — repetibilidade, proteção, energia e banda.

O requisito do V4 é que a modularidade seja **real: mecânica, elétrica e lógica**, e não
uma placa com furos. Este módulo é o que sustenta a afirmação, ou a derruba.

---

## O que separa "removível" de "modular"

Removível é qualquer coisa com parafuso. Modular é o que se pode **repor no mesmo lugar**.

A fusão de dados usa a matriz extrínseca de cada câmera — posição e orientação em relação
ao referencial do rover — como **constante**, medida uma vez na calibração. Se trocar uma
câmera desloca a próxima em 1°, a calibração morre junto com a peça trocada, e o técnico
que trocou a câmera na lavoura degradou a navegação sem ter como saber.

É por isso que a face VMS-60 se apoia em **pino**, não em parafuso. A conta está em
:func:`repetibilidade`, e o fator é 22.

---

## O que este módulo calcula

* repetibilidade angular da interface, com pino e sem pino;
* envelope do protetor de impacto a partir do campo de visão — é o que permite proteger
  sem pôr nada na frente da lente;
* matriz de compatibilidade: o que pode entrar num posto VMS e o que não pode;
* orçamento de energia e de banda com 9 câmeras e as térmicas opcionais;
* o que o software tem de fazer para que a troca em campo seja segura.

```
python modular.py
```

Unidades: mm, kg, W, Mbit/s, graus.
"""

from __future__ import annotations

import math
import pathlib
import sys

AQUI = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent / 'chassi-gaiola'))
sys.path.insert(0, str(AQUI))

import modelo as M  # noqa: E402

# =================================================== repetibilidade da interface
# Ajustes ISO 286. Folga máxima = IT do furo + IT do eixo, no pior caso.
IT = {
    ('H7', 8.0): 0.015, ('h6', 8.0): 0.009,
    ('H7', 6.0): 0.012, ('h6', 6.0): 0.008,
}
D_FOLGA_PARAFUSO = {5.0: 0.5}
"""Folga radial de um M5 em furo Ø5,5: 0,25 mm de cada lado, 0,5 no diâmetro."""


def repetibilidade() -> dict:
    """Quanto a interface erra ao repor um sensor — com pino e sem pino.

    O braço é a distância entre o pino de referência e o pino anti-giro: é ele que
    converte folga linear em erro angular. Quanto maior o braço, melhor — e é por isso que
    o anti-giro fica a 26 mm, o máximo que o prato de 64 mm permite com material em volta.
    """
    braco = M.Z_PINO_GIRO
    folga_pino = IT[('H7', M.D_PINO_REF)] + IT[('h6', M.D_PINO_REF)]
    folga_giro = IT[('H7', M.D_PINO_GIRO)] + IT[('h6', M.D_PINO_GIRO)]
    ang_pino = (folga_pino + folga_giro) / 2 / braco            # rad
    ang_parafuso = D_FOLGA_PARAFUSO[5.0] / braco                # rad
    return dict(
        braco_mm=braco,
        folga_pino_ref_mm=folga_pino, folga_pino_giro_mm=folga_giro,
        com_pino_deg=math.degrees(ang_pino),
        com_pino_mrad=ang_pino * 1e3,
        sem_pino_deg=math.degrees(ang_parafuso),
        sem_pino_mrad=ang_parafuso * 1e3,
        fator=ang_parafuso / ang_pino,
        erro_com_pino_a_10m_mm=math.tan(ang_pino) * 10000,
        erro_sem_pino_a_10m_mm=math.tan(ang_parafuso) * 10000,
        desloc_linear_mm=folga_pino / 2,
    )


TOLERANCIA_EXTRINSECA_DEG = 0.1
"""Erro angular admitido numa troca sem recalibrar. CRITÉRIO DE PROJETO.

Vem do que a fusão tolera: a 10 m, 0,1° são 17 mm de erro lateral, que é da ordem do
próprio ruído de profundidade estéreo nessa distância. Acima disso a troca passa a exigir
recalibração, e aí o software tem de saber — ver `REQUISITOS_SOFTWARE`.
"""


def passa_sem_recalibrar() -> dict:
    r = repetibilidade()
    return dict(
        limite_deg=TOLERANCIA_EXTRINSECA_DEG,
        com_pino=r['com_pino_deg'] <= TOLERANCIA_EXTRINSECA_DEG,
        sem_pino=r['sem_pino_deg'] <= TOLERANCIA_EXTRINSECA_DEG,
        margem=TOLERANCIA_EXTRINSECA_DEG / r['com_pino_deg'])


# ======================================================== campo de visão e proteção
FOV_H_DEG = 128.0
FOV_V_DEG = 80.0
"""Campo de visão da OAK-D Pro W. **A VALIDAR** — o projeto não tem a ficha técnica
(pendência P-06). Os valores são os que a Luxonis divulga para a variante "W" (wide) e
estão aqui como PARÂMETRO: se mudarem, o protetor é redimensionado por esta mesma conta.
"""


def protecao(avanco: float = None) -> dict:
    """Até onde o protetor pode avançar sem entrar no campo de visão.

    Este é o cálculo que responde ao requisito "proteção contra impactos SEM grade, aro ou
    defletor diante da lente". A resposta é geométrica e não tem volta: com 128° de campo
    horizontal, qualquer coisa a 40 mm à frente da lente teria de estar a 82 mm de
    distância do eixo para não aparecer. Lateralmente isso não cabe no rover.

    Verticalmente cabe: 40 mm à frente exigem 34 mm acima, e o protetor tem 40.

    Daí a solução: **sobrancelha superior, e nada ao lado nem à frente.** A proteção
    lateral vem de onde já existe estrutura — o corpo da braçadeira, do lado de dentro — e
    a frontal vem de recuar a lente, não de cobri-la.
    """
    a = avanco if avanco is not None else M.AVANCO_PROTETOR
    lat = a * math.tan(math.radians(FOV_H_DEG / 2))
    vert = a * math.tan(math.radians(FOV_V_DEG / 2))
    return dict(
        avanco_mm=a,
        lateral_necessaria_mm=lat, vertical_necessaria_mm=vert,
        altura_do_protetor_mm=M.ALTURA_PROTETOR,
        vertical_ok=M.ALTURA_PROTETOR >= vert,
        lateral_possivel=lat <= M.VMS_PRATO[0] / 2,
        meia_largura_do_prato_mm=M.VMS_PRATO[0] / 2,
        folga_vertical_mm=M.ALTURA_PROTETOR - vert,
        veredito=('Sobrancelha superior: CABE. Proteção lateral e frontal por estrutura à '
                  'frente da lente: IMPOSSÍVEL com este campo de visão — e é por isso que '
                  'não há grade nenhuma no projeto.'))


PROTECAO_POR_ONDE = [
    ('Galho vindo de frente', 'lente recuada 6 mm atrás da face do adaptador + sobrancelha '
                              'T-05 avançando 40 mm acima do eixo óptico'),
    ('Galho vindo de cima', 'sobrancelha T-05, que é a peça sacrificial: 2 parafusos M4 e '
                            'troca em campo sem ferramenta especial'),
    ('Galho vindo de fora para dentro', 'o protetor envolve o canto externo superior; o '
                                        'lado de dentro é protegido pelo próprio mastro'),
    ('Pedra lançada pela roda', 'as câmeras de extremidade ficam SOB a chapa de fundo, '
                                'com a chapa por cima e 60 mm de recuo da borda'),
    ('Impacto no mastro inteiro', 'bainha anti-galho M-11 em UHMW-PE sobre o tubo, nos '
                                  'trechos entre câmeras'),
    ('Chuva e lavagem', 'conector M12 codificação X por posto; a vedação é do conector, '
                        'não de caixa — ver nota sobre IP'),
    ('Poeira e lama', 'nenhuma fenda horizontal voltada para cima no posto VMS; o prato '
                      'T-02 é inclinável e drena'),
    ('Vibração', 'montagem RÍGIDA por decisão de projeto — ver `mastro.py`'),
]

NOTA_IP = """\
O projeto NÃO declara grau de proteção IP para o posto de sensor, e isso é deliberado.

Grau IP é resultado de ENSAIO num conjunto fechado, não propriedade de um conector
isolado. O que o projeto pode afirmar é o que especifica: conector M12 com codificação X,
que é o padrão de Ethernet industrial e existe em versões classificadas por fabricante. O
grau do POSTO montado — conector, cabo, passa-cabo e carcaça da câmera juntos — só sai do
ensaio, e está na lista de ensaios como V-11.

Declarar "IP67" aqui sem o ensaio seria inventar classificação, que é exatamente o que o
pedido do V4 proíbe.
"""


# ============================================ matriz de compatibilidade do posto VMS
CLASSES = {
    'navegacao': 'Sensor de navegação — a ausência dele PARA o rover',
    'inspecao': 'Sensor de inspeção agrícola — a ausência degrada a missão, não a segurança',
    'comunicacao': 'Equipamento de comunicação — a ausência tira a telemetria',
}

CLASSE_NOME = {'navegacao': 'navegação', 'inspecao': 'inspeção', 'comunicacao': 'comunicação'}
"""Os identificadores ficam sem acento (são chaves de código); o texto mostrado leva o acento."""

# (módulo, classe, massa kg, W, interface, cabe no VMS-60?, o que falta)
CANDIDATOS = [
    ('OAK-D Pro W PoE (base)', 'inspecao', 0.25, 12.95,
     'Ethernet 100BASE-TX + PoE 802.3af classe 3', True,
     'desenho dimensional e furação reais (P-06); massa é ESTIMATIVA'),
    ('Câmera térmica radiométrica compacta', 'inspecao', 0.20, 3.0,
     'Ethernet ou USB — depende do modelo', True,
     'NENHUM MODELO ESCOLHIDO. Adaptador T-04 é requisito, não desenho'),
    ('Câmera RGB alternativa (GigE industrial)', 'inspecao', 0.30, 6.0,
     'Ethernet 1000BASE-T + PoE', True,
     'furação própria: exige adaptador novo, que é 1 peça de chapa 6'),
    ('Sensor multiespectral', 'inspecao', 0.35, 8.0, 'Ethernet ou serial', True,
     'modelo não escolhido; massa e consumo são FAIXA'),
    ('LiDAR Livox Mid-360', 'navegacao', 0.30, None, 'Ethernet', False,
     'NÃO vai em posto VMS: precisa de 360° livres e fica no alto da gaiola, em G-06 '
     'com coxins. É o único sensor que permanece ISOLADO — ver `mastro.py`'),
    ('Antena GNSS RTK', 'navegacao', None, None, 'coaxial', False,
     'NÃO vai em posto VMS: precisa de vista livre ao céu e plano de terra. Tem duas '
     'provisões — T-10, no topo do mastro (esboço do projeto), e N-01, na tampa (V3). '
     'A escolha é decisão aberta (P-36)'),
    ('IMU', 'navegacao', None, None, 'CAN', False,
     'NÃO vai em posto VMS: tem de ficar o mais perto possível do CG, não no alto '
     'do mastro — no mastro ela mediria a vibração do mastro, não o movimento do rover'),
    ('Terminal de comunicação por satélite', 'comunicacao', None, None, 'Ethernet', False,
     f'NÃO vai em posto VMS: berço próprio T-07 na tampa, envelope máximo '
     f'{M._n(M.SAT_ENVELOPE[0])} × {M._n(M.SAT_ENVELOPE[1])} × {M._n(M.SAT_ENVELOPE[2])}'),
]


def compatibilidade() -> list[dict]:
    """A matriz, com o critério de cada "não" explícito."""
    out = []
    for (nome, classe, massa, w, iface, cabe, falta) in CANDIDATOS:
        out.append(dict(modulo=nome, classe=CLASSE_NOME[classe], classe_desc=CLASSES[classe],
                        massa=massa, w=w, interface=iface, cabe_vms=cabe, pendencia=falta))
    return out


# ================================================= energia, banda e PoE
N_OAKD = 9
"""Nove câmeras no V4: 6 no mastro, 1 frontal baixa, 1 traseira baixa, 1 de raiz.

Era 8 no V3 — e das 8 declaradas, a frontal **não existia no desenho** (a carenagem K-02
tem 9 furos de porca-rebite e 2 de farol, e nada mais) e a traseira não existia nem nos
documentos. O V4 desenha as três de extremidade e acrescenta a traseira.
"""

N_TERMICA_POSICOES = 2 * len(M.Z_TERMICA)
"""Posições térmicas removíveis provisionadas: 2 por mastro, a meio caminho entre os
andares de OAK-D. O mastro é calculado com todas montadas. Quantas serão realmente
compradas é decisão comercial — o orçamento mostra 0, 2 e 4."""

N_TERMICA_MAX = N_TERMICA_POSICOES
"""Pior caso do orçamento: todas as posições ocupadas."""

W_OAKD = 12.95
"""W — TETO da classe 3 de 802.3af na carga, não consumo medido. Ver `sensores.MODULOS`."""

W_TERMICA = 3.0
"""W — FAIXA para módulo térmico compacto. Nenhum modelo escolhido."""

W_SATELITE = 30.0
"""W — FAIXA para terminal satelital compacto. É consumo significativo e entra no
orçamento mesmo sendo provisão: reservar energia é mais honesto que descobrir depois."""

MBPS_OAKD = 60.0

W_JETSON_MAX = 40.0
"""W — perfil de potência mais alto da Jetson Orin NX 16 GB (os perfis vão de 10 a 40 W).
FAIXA do fabricante, não medição; o perfil adotado está em aberto (ver componentes comprados)."""
"""Mbit/s por câmera, estimado para fluxo estéreo comprimido + profundidade.
ESTIMATIVA: a taxa real depende de resolução, taxa de quadros e codec, e o projeto não
tem essa configuração fechada."""

SWITCH_PORTAS = 8
SWITCH_UPLINK_MBPS = 1000.0
"""Switch PoE de 8 portas com uplink de 1 Gbit/s. É o que o orçamento do V3 previa
implicitamente com 8 câmeras — e é exatamente o que a 9ª câmera estoura."""


def energia(n_termicas: int = None) -> dict:
    """Orçamento elétrico com 9 câmeras, térmicas e provisão de satélite."""
    n_term = N_TERMICA_MAX if n_termicas is None else n_termicas
    sys.path.insert(0, str(AQUI))
    import sensores as S  # noqa: PLC0415

    dc = S.DCDC_12V
    base = N_OAKD * W_OAKD
    termicas = n_term * W_TERMICA
    sat = W_SATELITE
    # perdas de PoE: injeção, cabo e conversão no dispositivo
    rend_poe = 0.85
    total_sensores = (base + termicas) / rend_poe + sat
    # o mesmo conversor alimenta a Jetson, o compressor e as válvulas (CABOS-H, ligação 5)
    import suspensao as SU  # noqa: PLC0415
    jetson = W_JETSON_MAX
    compressor = SU.COMPRESSOR_W
    pico_12v = total_sensores + jetson + compressor
    return dict(
        n_oakd=N_OAKD, w_por_oakd=W_OAKD, w_oakd=base,
        n_termica=n_term, w_termica=termicas,
        w_satelite=sat, rendimento_poe=rend_poe,
        total_W=total_sensores,
        capacidade_dcdc_W=dc['w_max'],
        folga_W=dc['w_max'] - total_sensores,
        cabe=total_sensores <= dc['w_max'],
        w_jetson_max=jetson, w_compressor=compressor,
        pico_barramento_12v_W=pico_12v,
        folga_pico_W=dc['w_max'] - pico_12v,
        cabe_no_pico=pico_12v <= dc['w_max'],
        delta_vs_v3=(base - 8 * W_OAKD) / rend_poe + termicas / rend_poe + sat,
        nota=('Só os sensores cabem nos 360 W. Mas o conversor também alimenta a Jetson (até '
              f'{jetson:.0f} W) e o compressor da suspensão ({compressor:.0f} W quando liga): '
              f'no pico são {pico_12v:.0f} W. Conversor maior, um segundo conversor para a '
              'suspensão, ou o compressor travado durante a captura (P-17). Portas: ver `rede`.'))


SWITCH_12_PORTAS = 12


def rede(n_termicas: int = 0) -> dict:
    """Portas e banda: é aqui que a 9ª câmera dói, não na energia.

    `n_termicas` conta as térmicas que falam Ethernet. A interface de uma câmera térmica
    depende do modelo (P-30) — se for USB ela entra pela Jetson e não ocupa porta.
    """
    n = N_OAKD
    banda = n * MBPS_OAKD
    # +1 LiDAR, +1 ligação à Jetson, +1 terminal satelital (provisão) — CABOS-H, ligações 12 a 14
    portas = n + 1 + 1 + 1 + n_termicas
    return dict(
        n_cameras=n, n_termicas=n_termicas,
        portas_necessarias=portas,
        portas_com_12=SWITCH_12_PORTAS,
        cabe_em_12=portas <= SWITCH_12_PORTAS,
        portas_do_switch=SWITCH_PORTAS,
        portas_ok=portas <= SWITCH_PORTAS,
        banda_total_Mbps=banda, uplink_Mbps=SWITCH_UPLINK_MBPS,
        ocupacao_uplink=banda / SWITCH_UPLINK_MBPS,
        banda_ok=banda <= SWITCH_UPLINK_MBPS * 0.7,
        poe_total_W=n * W_OAKD,
        nota=('9 câmeras, o LiDAR, a ligação à Jetson e o terminal satelital somam 12 portas '
              'Ethernet, e o switch de 8 não serve. Um de 12 portas PoE+ atende sem térmicas '
              'Ethernet; cada térmica Ethernet pede mais uma porta (16 portas com duas ou mais). '
              'ESTE É UM ITEM NOVO DE BOM, não um ajuste de desenho.'))


# ======================================================== software e calibração
REQUISITOS_SOFTWARE = [
    ('Identificação do módulo', 'Cada posto VMS tem um identificador físico. O software lê '
     'o número de série da câmera na enumeração Ethernet e o associa ao POSTO, não ao '
     'equipamento — é o posto que tem calibração extrínseca, não a peça.'),
    ('Detecção de desconexão', 'Perda de enumeração por mais de 2 s = módulo ausente. '
     'O sistema registra, segue operando e marca os dados daquele posto como indisponíveis.'),
    ('Operação degradada', 'A ausência de qualquer câmera de INSPEÇÃO não impede a '
     'inicialização nem a navegação. A ausência de LiDAR, GNSS ou IMU — classe '
     'navegação — impede, e isso é projeto, não falha.'),
    ('Perfil por modelo', 'Cada modelo de sensor tem um perfil: driver, resolução, taxa, '
     'intrínsecos de fábrica e limites. Trocar o modelo num posto troca o perfil, '
     'não o código.'),
    ('Verificação de calibração após troca', 'Ao detectar número de série novo num posto '
     'conhecido, o sistema exige a verificação: alvo conhecido, erro de reprojeção '
     f'medido, aceite se abaixo do limite de {TOLERANCIA_EXTRINSECA_DEG}°. '
     'Com pino de referência o esperado é passar de primeira.'),
    ('Detecção de perda de referência', 'Se a braçadeira T-01 for afrouxada, a extrínseca '
     'muda e o pino não protege. O software NÃO tem como saber sozinho — por isso o '
     'procedimento de manutenção exige registro manual, e é a maior fragilidade desta '
     'arquitetura. Ver `pendencias`.'),
    ('Sincronização temporal', 'Todos os fluxos com carimbo de tempo da mesma base. '
     'Um módulo novo sem sincronização entra como fluxo isolado, não entra na fusão.'),
    ('Interface com o SaaS', 'Inventário de módulos por rover, com posto, modelo, número '
     'de série e data da última calibração. NOT_IMPLEMENTED no SaaS.'),
]

PROCEDIMENTO_TROCA = [
    ('1', 'Desligar o rover e travar o sistema de ar no vão mínimo', 'segurança'),
    ('2', 'Desconectar o M12 do posto', 'o conector é o único ponto elétrico'),
    ('3', 'Soltar os 4 parafusos M5 do adaptador T-03', 'chave Allen 3 mm'),
    ('4', 'Retirar o adaptador com a câmera', 'os pinos de referência FICAM no prato T-02'),
    ('5', 'NÃO tocar na braçadeira T-01', 'é o que preserva a calibração extrínseca'),
    ('6', 'Montar o adaptador novo nos pinos, apertar os 4 M5 a 5 N·m', 'cruzado'),
    ('7', 'Reconectar o M12 e ligar', 'o sistema detecta o número de série novo'),
    ('8', 'Rodar a verificação de calibração do posto', 'alvo conhecido, 2 minutos'),
    ('9', 'Registrar no inventário: posto, modelo, série, data', 'rastreabilidade'),
]

PROCEDIMENTO_TROCA_TERMICA = [
    ('1', 'Desligar o rover e travar o sistema de ar no vão mínimo', 'segurança'),
    ('2', 'Desconectar o M12 do módulo', 'o conector é o único ponto elétrico; o cabo fica no mastro'),
    ('3', 'Soltar os 4 parafusos imperdíveis M5 com a mão', 'sem ferramenta — é o que torna o módulo removível'),
    ('4', 'Retirar o módulo inteiro (adaptador T-04 + câmera + protetor T-05)',
     'os pinos de referência FICAM no prato T-02'),
    ('5', 'NÃO tocar na braçadeira T-01 nem no índice de inclinação', 'é o que preserva a posição calibrada'),
    ('6', 'Encaixar o módulo nos pinos e apertar os 4 parafusos com a mão, em cruz', 'aperto manual firme; '
     'torque a definir no ensaio V-16'),
    ('7', 'Reconectar o M12, ligar e confirmar o posto no inventário', 'o sistema lê o número de série'),
    ('8', 'Rodar a verificação de calibração do posto', 'alvo conhecido, 2 minutos'),
]

PLANO_DE_ENSAIO = [
    ('V-10', 'Repetibilidade da interface VMS', 'Montar e desmontar o mesmo adaptador 10 '
     'vezes, medindo a orientação com alvo a 5 m. Aceite: dispersão abaixo de 0,1°. '
     'É o ensaio que valida ou derruba o argumento do pino.'),
    ('V-11', 'Grau de proteção do posto montado', 'Jato e poeira conforme IEC 60529 no '
     'conjunto conector + cabo + câmera. Sem isto o projeto NÃO declara IP.'),
    ('V-12', 'Vibração do mastro em campo', 'Acelerômetro nos três andares, percurso de '
     '1 km em rua de café. Mede o espectro real e fecha a margem de frequência que hoje '
     'é critério, não medição.'),
    ('V-13', 'Impacto de galho no protetor', 'Carga lateral progressiva no protetor T-05 '
     'até a ruptura. Aceite: o protetor rompe antes do adaptador, e a câmera sobrevive.'),
    ('V-14', 'Troca em campo cronometrada', 'Técnico com ferramenta de campo troca uma '
     'câmera do andar alto. Aceite: abaixo de 10 minutos, sem recalibração.'),
    ('V-15', 'Operação com módulo ausente', 'Desconectar cada câmera de inspeção, uma por '
     'vez, com o rover em missão. Aceite: nenhuma interrupção de navegação.'),
    ('V-16', 'Repetibilidade do módulo térmico com parafuso de aperto manual', 'Como o V-10, '
     'mas com os 4 parafusos imperdíveis apertados à mão por três técnicos diferentes. '
     'Aceite: dispersão abaixo de 0,1°. Define também o aperto mínimo que o procedimento exige.'),
    ('V-17', 'Antena GNSS no topo do mastro', 'RTK em marcha na lavoura com a antena em T-10 e '
     'depois em N-01, mesma rota. Compara: tempo para fixar, perdas de fix, erro cruzado. É o '
     'que decide a pendência P-36 com dado, e não com preferência.'),
]

def _massa_antena_max():
    sys.path.insert(0, str(AQUI))
    import mastro as MA  # noqa: PLC0415
    return MA.massa_antena_maxima()


PENDENCIAS = [
    ('P-06', 'Desenho dimensional da OAK-D Pro W PoE', 'CRÍTICA',
     'Bloqueia a furação do adaptador T-03, que é a peça que define a modularidade. Os '
     '4 furos Ø3,4 desenhados são PROVISÃO — a furação real vem do fabricante. Sem ela, '
     'T-03 não é cota de fabricação.'),
    ('P-30', 'Modelo da câmera térmica', 'ALTA',
     'Nenhum escolhido. O adaptador T-04 existe como REQUISITO: uma chapa 72×64×6 com a '
     'face VMS-60 de um lado e a furação do modelo do outro. É 1 peça de corte a laser '
     'por modelo adotado.'),
    ('P-31', 'Switch PoE de 12 portas', 'ALTA',
     'A 9ª câmera estoura o switch de 8 portas. Item NOVO de BOM, não previsto no V3.'),
    ('P-32', 'Terminal de comunicação por satélite', 'MÉDIA',
     f'Provisão desenhada para até {M._n(M.SAT_ENVELOPE[0])} × {M._n(M.SAT_ENVELOPE[1])} × '
     f'{M._n(M.SAT_ENVELOPE[2])} mm. Um terminal da classe 300 × 260 — que é a do Starlink '
     'Mini — NÃO CABE sem deslocar o suporte do LiDAR ou a antena GNSS.'),
    ('P-33', 'Detecção de afrouxamento da braçadeira', 'MÉDIA',
     'O software detecta troca de módulo, mas não detecta que alguém mexeu na altura. '
     'É a fragilidade da arquitetura, e hoje só o procedimento cobre.'),
    ('P-34', 'Grau de proteção IP do posto', 'MÉDIA',
     'Não declarado, por não ter ensaio. Ensaio V-11.'),
    ('P-36', 'Onde fica a antena GNSS RTK: topo do mastro ou tampa', 'ALTA',
     'O esboço do projeto põe a antena no topo do mastro; o V3 desenhou N-01 na tampa. As duas '
     'têm provisão no V4 e nada foi decidido. No topo: céu livre, mas 1,83 m de braço de '
     'alavanca (compensação de inclinação por IMU é obrigatória) e a massa de ponta custa '
     'frequência do mastro. Na tampa: sem braço de alavanca, mas multicaminho do próprio rover. '
     'Ensaio V-17.'),
    ('P-37', 'Antena GNSS: modelo e massa', 'ALTA',
     'Nenhuma escolhida. O mastro cumpre 7,5 Hz com antena de até '
     f'{_massa_antena_max():.2f} kg (ver `mastro.py`). Antena mais pesada exige Ø32×4 ou outro '
     'conceito. A rosca de 5/8"-11 UNC é o padrão de topografia e está A VALIDAR com o modelo.'),
    ('P-38', 'Câmera térmica: cabe no envelope e deixa livre o acesso aos parafusos?', 'ALTA',
     f'O módulo removível tem de caber em {M._n(M.ENVELOPE_TERMICA[0])} × '
     f'{M._n(M.ENVELOPE_TERMICA[1])} × {M._n(M.ENVELOPE_TERMICA[2])} mm (prato e sobrancelha '
     'T-05) e deixar livre a cabeça dos 4 parafusos. Se a câmera escolhida cobrir os '
     'parafusos, o T-04 ganha um espaçador — é uma peça a mais, não um redesenho.'),
    ('P-39', 'Margem do mastro contra o terreno não fecha a 1,4 m/s', 'MÉDIA',
     'Com o mastro cheio a razão frequência/excitação é 1,41 contra o mínimo de 2,0; a '
     'margem só fecha abaixo de ~1,0 m/s. A excitação é critério, não medição. Ensaio V-12 '
     'decide: ou o espectro real é benigno, ou a velocidade com mastro cheio é limitada.'),
    ('P-40', 'Cabos dentro do tubo do mastro', 'MÉDIA',
     'Com a parede de 3 mm o furo do tubo é Ø26. Os 5 cabos M12 e o coaxial da antena de um '
     'mastro ocupam cerca de 40 % dele com cabos de Ø7 — que é ESTIMATIVA, nenhum cabo foi '
     'escolhido. Acima de Ø7 passa do limite de 40 %. Se passar: cabos de menor diâmetro, ou '
     'canaleta externa sob a bainha.'),
    ('P-41', 'Mastro em perfil T 30×30, como no esboço', 'MÉDIA',
     'O esboço do projeto desenha o mastro em perfil de alumínio T com T-nuts. O V4 manteve o tubo '
     'Ø32×3 com braçadeira porque a rigidez do tubo foi calculada e a de um perfil T não tem ficha '
     'técnica no projeto. Se o perfil for preferido por montagem, é preciso a ficha (momento de inércia) e um novo '
     'cálculo de frequência — o caso 6 do FEA não pode ser assumido.'),
    ('P-35', 'Campo de visão real da OAK-D Pro W', 'MÉDIA',
     f'{FOV_H_DEG:.0f}° × {FOV_V_DEG:.0f}° são os valores divulgados, não ficha técnica no '
     'projeto. O protetor T-05 é dimensionado por eles; se mudarem, redimensiona.'),
]


# ================================================ antena GNSS: topo do mastro × tampa
def antena_mastro() -> dict:
    """O que muda se a antena RTK for para o topo do mastro, como no esboço do projeto.

    Só geometria e o cálculo do mastro. Nada de desempenho de GNSS: isso é ensaio (V-17).
    """
    sys.path.insert(0, str(AQUI))
    import mastro as MA  # noqa: PLC0415

    z_topo = M.Z_BASE_ANTENA + M.H_ANTENA
    z_tampa = M.Z_GNSS[1] + M.H_ANTENA
    d = MA.deflexao()[-1]
    lim = MA.massa_antena_maxima()

    def desloc(h, graus):
        return h * math.tan(math.radians(graus))

    return dict(
        z_topo_mm=z_topo, z_tampa_mm=z_tampa, braco_extra_mm=z_topo - z_tampa,
        desloc_10graus_topo_mm=desloc(z_topo, 10), desloc_10graus_tampa_mm=desloc(z_tampa, 10),
        flecha_topo_mm=d['flecha_mm'], rotacao_topo_deg=d['rotacao_deg'],
        massa_antena_max_kg=lim, massa_antena_caso_kg=MA.MASSA_ANTENA,
        freq_com_antena_Hz=MA.frequencia()['freq_Hz'],
        freq_sem_antena_Hz=MA.frequencia(caso='cheio')['freq_Hz'])


# =================================================================== relatório
def main() -> None:
    print('=' * 88)
    print('VTX-RV4 Rev H · INTERFACE MODULAR DE SENSORES VMS-60')
    print('=' * 88)

    r = repetibilidade()
    pr = passa_sem_recalibrar()
    print('\n1. Repetibilidade — o número que justifica a arquitetura')
    print('-' * 60)
    print(f'  braço entre os dois pinos: {r["braco_mm"]:.0f} mm')
    print(f'  folga do pino Ø{M.D_PINO_REF:.0f} H7/h6: {r["folga_pino_ref_mm"]:.3f} mm')
    print(f'  COM pino:     {r["com_pino_deg"]:.3f}°  ({r["com_pino_mrad"]:.2f} mrad)  '
          f'-> {r["erro_com_pino_a_10m_mm"]:5.1f} mm a 10 m')
    print(f'  SEM pino (só parafuso M5 em furo Ø5,5): {r["sem_pino_deg"]:.2f}°  '
          f'({r["sem_pino_mrad"]:.1f} mrad)  -> {r["erro_sem_pino_a_10m_mm"]:5.0f} mm a 10 m')
    print(f'  fator: {r["fator"]:.0f}×')
    print(f'  limite para trocar sem recalibrar: {pr["limite_deg"]:.1f}°')
    print(f'    com pino: {"PASSA" if pr["com_pino"] else "NAO PASSA"}'
          f'  (margem {pr["margem"]:.1f}×)')
    print(f'    sem pino: {"PASSA" if pr["sem_pino"] else "NAO PASSA"}')

    p = protecao()
    print('\n2. Proteção sem nada na frente da lente')
    print('-' * 60)
    print(f'  campo de visão adotado: {FOV_H_DEG:.0f}° H × {FOV_V_DEG:.0f}° V  [A VALIDAR]')
    print(f'  protetor avança {p["avanco_mm"]:.0f} mm à frente da lente')
    print(f'  para ficar fora do campo precisaria de {p["lateral_necessaria_mm"]:.0f} mm '
          f'lateral e {p["vertical_necessaria_mm"]:.0f} mm vertical')
    print(f'  o prato tem {p["meia_largura_do_prato_mm"]:.0f} mm de meia-largura: '
          f'lateral {"CABE" if p["lateral_possivel"] else "NAO CABE"}')
    print(f'  o protetor tem {p["altura_do_protetor_mm"]:.0f} mm de altura: '
          f'vertical {"CABE" if p["vertical_ok"] else "NAO CABE"} '
          f'(folga {p["folga_vertical_mm"]:.0f} mm)')
    print(f'  {p["veredito"]}')
    print('\n  de onde vem a proteção, ameaça por ameaça:')
    for (ameaca, como) in PROTECAO_POR_ONDE:
        print(f'    {ameaca:36} {como}')
    print()
    for linha in NOTA_IP.strip().split('\n'):
        print('  ' + linha)

    print('\n3. Matriz de compatibilidade do posto VMS-60')
    print('-' * 60)
    for c in compatibilidade():
        marca = 'VMS ' if c['cabe_vms'] else 'NAO '
        w = f'{c["w"]:.1f} W' if c['w'] else '—'
        m = f'{c["massa"]:.2f} kg' if c['massa'] else '—'
        print(f'  {marca} {c["modulo"]:42} {m:>8} {w:>8}  [{c["classe"]}]')
        print(f'        {c["pendencia"]}')

    e = energia()
    print('\n4. Energia')
    print('-' * 60)
    print(f'  {e["n_oakd"]} × OAK-D a {e["w_por_oakd"]:.2f} W (teto 802.3af classe 3) = '
          f'{e["w_oakd"]:.1f} W')
    print(f'  {e["n_termica"]} × térmica a {W_TERMICA:.1f} W = {e["w_termica"]:.1f} W')
    print(f'  terminal satelital (provisão): {e["w_satelite"]:.0f} W')
    print(f'  com {(1 - e["rendimento_poe"]) * 100:.0f} % de perda de PoE: '
          f'TOTAL {e["total_W"]:.1f} W')
    print(f'  conversor DC/DC: {e["capacidade_dcdc_W"]:.0f} W -> folga {e["folga_W"]:.1f} W '
          f'({"CABE" if e["cabe"] else "NAO CABE"})')
    print(f'  acréscimo sobre o V3: +{e["delta_vs_v3"]:.1f} W')
    print(f'  {e["nota"]}')

    n = rede()
    print('\n5. Rede — onde a 9ª câmera realmente dói')
    print('-' * 60)
    print(f'  portas necessárias: {n["portas_necessarias"]} ({n["n_cameras"]} câmeras + LiDAR)')
    print(f'  switch previsto: {n["portas_do_switch"]} portas -> '
          f'{"OK" if n["portas_ok"] else "NAO SERVE"}')
    print(f'  banda: {n["banda_total_Mbps"]:.0f} Mbit/s em uplink de '
          f'{n["uplink_Mbps"]:.0f} ({n["ocupacao_uplink"] * 100:.0f} % de ocupação) -> '
          f'{"OK" if n["banda_ok"] else "APERTADO"}')
    print(f'  PoE total: {n["poe_total_W"]:.0f} W')
    print(f'  {n["nota"]}')

    print('\n6. O que o software tem de fazer')
    print('-' * 60)
    for (req, o_que) in REQUISITOS_SOFTWARE:
        print(f'  {req}')
        for linha in _quebra(o_que, 78):
            print(f'      {linha}')

    print('\n7. Trocar uma câmera em campo')
    print('-' * 60)
    for (n_, passo, nota) in PROCEDIMENTO_TROCA:
        print(f'  {n_}. {passo:58} ({nota})')

    print('\n8. Ensaios que esta arquitetura exige')
    print('-' * 60)
    for (cod, nome, desc) in PLANO_DE_ENSAIO:
        print(f'  {cod} · {nome}')
        for linha in _quebra(desc, 78):
            print(f'      {linha}')

    print('\n9. Pendências')
    print('-' * 60)
    for (cod, nome, grau, txt) in PENDENCIAS:
        print(f'  {cod} · {nome} · {grau}')
        for linha in _quebra(txt, 78):
            print(f'      {linha}')


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
