"""Arquitetura modular de sensores — um rover, quatro configurações.

Responde às seções 6, 7 e 14 do pedido de revisão: a mesma plataforma mecânica
recebendo conjuntos diferentes de instrumentos, sem reprojetar o veículo.

**Sobre os consumos.** O projeto Rev E não tem tabela de consumo — nem no caderno do
chassi, nem no documento técnico, nem na BOM. O documento técnico chega a ressalvar que
"capacidades operacionais (autonomia, aclive, cobertura por hora) são da baseline Rev E
e não foram verificadas". Então aqui:

* o que vem da BOM ou do datasheet, com página, entra como ``FONTE``;
* o que vem da norma de alimentação (PoE) entra como ``TETO`` — serve para dimensionar
  switch e fonte, que é como se dimensiona instalação PoE, e **não** é consumo medido;
* o que não existe entra como ``None``, aparece em :func:`pendencias_de_fabricante` e
  **impede** o orçamento energético de fechar. Um ``None`` propagando até a conta é
  melhor do que um número inventado que fecha a planilha e mente.

Unidades: V, A, W, Wh, kg, Mbit/s.
"""

from __future__ import annotations

# ============================================================== energia disponível
# Da BOM de compras de 21/09/2026, conciliada no pacote Rev E.
BATERIA = dict(
    quimica='LiFePO4', celulas=16, v_celula=3.2, ah=105.0,
    v_nominal=16 * 3.2, wh=16 * 3.2 * 105.0,
    massa=36.5,                      # tabela 5.1 da baseline
    fonte='BOM 21/09/2026 · 16× célula EVE 3,2 V 105 Ah (Buyers Energy) + BMS Daly 16S',
)

DCDC_12V = dict(v_saida=12.0, a_max=30.0, w_max=360.0,
                fonte='BOM 21/09/2026 · conversor 48→12 V 30 A')

PROFUNDIDADE_UTIL = 0.80
"""Fração da energia da bateria que se usa de verdade.

LiFePO4 aceita descarga profunda, mas o plano de missão da plataforma reserva margem
(ver ``reserve_percent`` no planejador do SaaS) e o BMS corta antes do zero. 80 % é
CRITÉRIO DE PROJETO, não medição.
"""


# ================================================================ catálogo de módulos
# campo None = dado que o projeto não tem. Ver `pendencias_de_fabricante`.
def _s(**kw):
    base = dict(v=None, a=None, w=None, massa=None, interface=None, mbps=None,
                onde=None, fov=None, origem=None, calibracao=None, limites=None)
    base.update(kw)
    return base


MODULOS = {
    # ----------------------------------------------------- configuração-base (Vision)
    'OAKD': _s(
        nome='Câmera OAK-D Pro W PoE', qtd_base=8, v=48.0, w=12.95,
        interface='Ethernet 100BASE-TX com PoE 802.3af (alimentação e dados no mesmo cabo)',
        mbps=None, massa=None,
        onde='3 no mastro esquerdo, 3 no direito (três níveis, visão bilateral), '
             '1 frontal, 1 inferior voltada ao solo e à raiz',
        origem='FONTE (quantidade e preço) · BOM 21/09/2026 · 8 un a R$ 3.490,06. '
               'TETO (potência) · classe 3 de 802.3af, 12,95 W na carga — não é consumo '
               'medido. PENDENTE: consumo típico, massa e taxa de dados por fluxo.',
        calibracao='Intrínseca de fábrica; extrínseca (posição e orientação de cada uma '
                   'em relação ao referencial do rover) a levantar na montagem e a '
                   'regravar após qualquer troca — ver `interfaces_mecanica`.',
        limites='Profundidade estéreo degrada em folhagem homogênea e sob sol direto '
                'de meio-dia. Não mede temperatura nem reflectância espectral.'),
    'LIDAR': _s(
        nome='LiDAR Livox Mid-360', qtd_base=1, v=None, w=None,
        interface='Ethernet', massa=None,
        onde='Suporte G-06, sobre a gaiola, com coxins antivibração G-08',
        fov='360° × 59° (declarado pelo fabricante; centro óptico a confirmar — '
            'pendência 11 do caderno)',
        origem='FONTE (quantidade e preço) · BOM 21/09/2026. PENDENTE: tensão, consumo, '
               'massa e taxa de dados.',
        calibracao='Extrínseca LiDAR↔câmeras e LiDAR↔IMU. Sem ela não há reconstrução '
                   '3D georreferenciada.',
        limites='Não enxerga através de folhagem densa; retorno fraco em superfície '
                'molhada e escura.'),
    'GNSS': _s(
        nome='GNSS RTK u-blox ZED-F9P + antena', qtd_base=1, v=None, w=None,
        interface='USB ou UART', massa=None,
        onde='Antena no suporte N-01, na tampa superior; receptor na bandeja de eletrônica',
        origem='FONTE (quantidade e preço) · BOM 21/09/2026 · kit ArduSimple. '
               'PENDENTE: consumo do conjunto receptor + antena ativa.',
        calibracao='Offset antena→referencial do rover, e offset antena→CG declarado no '
                   'software (a mesma pendência 18 que o caderno levanta para o IMU).',
        limites='RTK exige correção por rádio (RFD900x) e linha de visada ao céu. '
                'Sob copa fechada de café, degrada para flutuante ou perde fixo — é por '
                'isso que a odometria visual e o LiDAR não são redundância luxuosa.'),
    'IMU': _s(
        nome='IMU Xsens MTi-630', qtd_base=1, v=None, w=None,
        interface='CAN', massa=None,
        onde='Berço N-02, o mais próximo possível do CG',
        origem='FONTE (quantidade e preço) · BOM 21/09/2026 · DigiKey. '
               'PENDENTE: consumo, massa e furação real (pendência 18 do caderno).',
        calibracao='Alinhamento dos eixos ao referencial ISO 8855 da baseline e offset '
                   'ao CG. Erro de offset aqui vira erro de odometria que cresce com a '
                   'distância.',
        limites='Deriva livre sem GNSS ou odometria para corrigir.'),
    'COMPUTA': _s(
        nome='NVIDIA Jetson Orin NX 16 GB + SSD NVMe 1 TB', qtd_base=1, v=None, w=None,
        interface='PCIe, Ethernet, CAN, USB',
        onde='Bandeja de eletrônica E-01',
        origem='FONTE (quantidade e preço) · BOM 21/09/2026. PENDENTE: modo de potência '
               'adotado — o Orin NX tem perfis de 10 W a 40 W, e a escolha muda o '
               'orçamento energético e a dissipação dentro de um chassi fechado.',
        limites='Oito fluxos de câmera mais LiDAR mais inferência não cabem no perfil de '
                '10 W. Dimensionar pelo perfil que o pipeline realmente exigir, medido.'),
    'RADIO': _s(
        nome='Par de rádios RFD900x (correção RTK e telemetria)', qtd_base=1,
        v=None, w=None, interface='UART',
        onde='Um no rover, um na base',
        origem='FONTE (quantidade e preço) · BOM 21/09/2026 · IR-Lock. PENDENTE: consumo '
               'em transmissão contínua.'),
    'ESTOP': _s(
        nome='E-STOP remoto sem fio industrial + relé de segurança Pilz PNOZ s4',
        qtd_base=1, v=None, w=None,
        onde='Receptor na bandeja E-01; botoeira no reforço E-10, na tampa traseira',
        origem='FONTE (quantidade e preço) · BOM 21/09/2026. PENDENTE: consumo do '
               'receptor em vigília — é carga permanente, conta na autonomia.',
        limites='É função de segurança: não compartilha alimentação nem barramento de '
                'dados com a percepção.'),

    # --------------------------------------------------------- módulos complementares
    'TERMICA': _s(
        nome='Câmera térmica radiométrica (módulo Hydro) — A ESPECIFICAR',
        qtd_base=0, qtd_hydro=1,
        onde='Posição única, a definir, com cobertura útil e relação espacial '
             'calibrável com as câmeras existentes. **Não** uma por ponto de visão: '
             'oito térmicas seriam oito calibrações e oito fluxos para um ganho que '
             'ninguém mediu ainda.',
        origem='NÃO ESPECIFICADA. Nenhum modelo escolhido, nenhuma cotação. Requisitos '
               'a levantar antes de cotar — ver `REQUISITOS_TERMICA`.',
        calibracao='Radiométrica (a térmica precisa de referência de temperatura para '
                   'medir, não só para ver) e extrínseca contra a OAK-D vizinha.',
        limites='**Imagem térmica não mede umidade do solo.** Mede temperatura de '
                'superfície, que responde a estresse hídrico junto com vento, radiação '
                'e umidade do ar. Diagnóstico exige os três, e ainda assim é hipótese.'),
    'MULTIESP': _s(
        nome='Câmera multiespectral (módulo Spectral) — A ESPECIFICAR',
        qtd_base=0, qtd_spectral=1,
        onde='A definir, com georreferenciamento e sincronização com o GNSS',
        origem='NÃO ESPECIFICADA. Nenhum modelo escolhido, nenhuma cotação.',
        calibracao='Radiométrica com painel de referência a cada sessão, e extrínseca.',
        limites='**Índice espectral não identifica doença sozinho.** Mais bandas não '
                'garantem mais precisão: o ganho tem de ser medido por aplicação, '
                'contra o que as câmeras RGB já entregam.'),
}


def pendencias_de_fabricante() -> list[dict]:
    """O que falta perguntar, item por item, antes de fechar qualquer orçamento.

    Esta é a lista que vai junto com a RFQ. Ela existe porque o orçamento energético
    **não fecha** sem ela, e é melhor entregar a lista do que uma planilha que fecha
    com números inventados.
    """
    out = []
    for chave, m in MODULOS.items():
        faltam = [campo for campo in ('v', 'w', 'massa', 'mbps')
                  if m.get(campo) is None]
        if faltam:
            out.append(dict(modulo=chave, nome=m['nome'], faltam=faltam,
                            origem=m.get('origem')))
    return out


# ================================================================= configurações
CONFIGURACOES = {
    'VISION': dict(
        nome='VALTEXA Vision — configuração-base',
        proposito='Inspeção visual, localização espacial e reconstrução tridimensional.',
        modulos=['OAKD', 'LIDAR', 'GNSS', 'IMU', 'COMPUTA', 'RADIO', 'ESTOP'],
        status='DESENHADA na Rev E (folhas 17 a 22). Posições e alturas das 8 OAK-D '
               'cotadas no caderno.'),
    'HYDRO': dict(
        nome='VALTEXA Hydro — extensão térmica',
        proposito='Acrescenta informação térmica para investigar estresse hídrico. '
                  'Extensão da base, não substituição: as 8 OAK-D continuam.',
        modulos=['OAKD', 'LIDAR', 'GNSS', 'IMU', 'COMPUTA', 'RADIO', 'ESTOP', 'TERMICA'],
        status='PROPOSTA. Nenhum sensor especificado; arquitetura de interface definida '
               'abaixo. Depende de `REQUISITOS_TERMICA`.'),
    'SPECTRAL': dict(
        nome='VALTEXA Spectral — extensão multiespectral',
        proposito='Informação espectral adicional, quando contribuir para a aplicação.',
        modulos=['OAKD', 'LIDAR', 'GNSS', 'IMU', 'COMPUTA', 'RADIO', 'ESTOP', 'MULTIESP'],
        status='PROPOSTA. Nenhum sensor especificado.'),
    'RESEARCH': dict(
        nome='VALTEXA Research — experimental',
        proposito='Acomoda instrumento novo sob análise caso a caso.',
        modulos=['OAKD', 'LIDAR', 'GNSS', 'IMU', 'COMPUTA', 'RADIO', 'ESTOP'],
        status='ARQUITETURA SOMENTE. Cada instrumento novo exige justificativa técnica, '
               'interface definida, orçamento energético, estratégia de processamento e '
               'plano de validação — nesta ordem, antes de comprar.'),
}

REQUISITOS_TERMICA = [
    ('Dados radiométricos', 'Obrigatório. Sem radiometria mede-se contraste, não '
                            'temperatura — e contraste não serve para comparar duas '
                            'inspeções separadas por semanas.'),
    ('Resolução', 'A definir pela menor feição que precisa ser resolvida à distância '
                  'de trabalho do mastro. Requisito a derivar da aplicação, não a copiar '
                  'de catálogo.'),
    ('Campo de visão', 'Compatível com a OAK-D vizinha, para que os dois quadros se '
                       'registrem sem extrapolação.'),
    ('Interface', 'Ethernet ou USB3. O chassi já tem rede PoE para as câmeras — '
                  'aproveitar reduz cabo e conector novos.'),
    ('Temperatura de operação', 'A do rover em campo, ao sol, dentro de carenagem '
                                'fechada. Pior caso do envelope, não o ambiente.'),
    ('Proteção ambiental', 'IP equivalente ao resto do conjunto.'),
    ('Sincronização', 'Trigger ou timestamp comum com as câmeras e o GNSS. Sem isso não '
                      'há fusão: há duas coleções de imagens da mesma lavoura.'),
    ('Massa e posição', 'Entra no orçamento de massa e muda o CG — e, se for no mastro, '
                        'muda muito (ver `efeito_no_cg`).'),
    ('Consumo', 'Contra o que sobrar do orçamento energético da configuração Vision.'),
]

SENSORES_AMBIENTAIS = """\
Para investigar estresse hídrico, a térmica sozinha não basta, e vale dizer por quê: a
temperatura da folha depende de transpiração, vento, radiação e umidade do ar ao mesmo
tempo. Sem as outras três, uma folha quente pode ser uma folha com sede ou uma folha ao
sol sem vento.

Complementos a avaliar, cada um com justificativa própria:

* **temperatura e umidade do ar a bordo** — barato, leve, e é o que permite calcular
  índices normalizados em vez de comparar temperatura absoluta entre dias diferentes;
* **umidade do solo de estação fixa na propriedade** — a plataforma já tem para onde
  mandar: o SaaS registra dock e fazenda, e a camada de segurança já lê vento de dock.
  Dado de estação não é dado do rover, e não deve ser apresentado como se fosse.

**O que não fazer:** apresentar temperatura de superfície como umidade do solo, ou
derivar diagnóstico de doença de um mapa térmico. A plataforma já separa detecção
visual, hipótese e classificação confirmada — a térmica entra como mais uma evidência
nessa cadeia, não como veredito.
"""


# ============================================================ orçamento energético
def orcamento(config: str) -> dict:
    """Soma o consumo de uma configuração. Devolve ``fecha=False`` se faltar dado.

    Não há caminho que preencha um ``None`` com estimativa: o resultado é a lista do que
    falta. É o que o pedido de revisão determina, e é o que impede uma autonomia
    publicada em cima de números que ninguém conferiu.
    """
    c = CONFIGURACOES[config]
    linhas, faltando = [], []
    total_w = 0.0
    for chave in c['modulos']:
        m = MODULOS[chave]
        qtd = m.get(f'qtd_{config.lower()}', m.get('qtd_base', 0)) or m.get('qtd_base', 0)
        w = m.get('w')
        if w is None:
            faltando.append(f"{chave} · {m['nome']}")
        else:
            total_w += w * qtd
        linhas.append(dict(modulo=chave, nome=m['nome'], qtd=qtd, w_unit=w,
                           w_total=(w * qtd if w is not None else None),
                           interface=m.get('interface'), onde=m.get('onde'),
                           origem=m.get('origem')))
    return dict(config=config, nome=c['nome'], linhas=linhas,
                w_conhecido=total_w, faltando=faltando, fecha=not faltando,
                wh_bateria=BATERIA['wh'], wh_util=BATERIA['wh'] * PROFUNDIDADE_UTIL,
                horas_se_fechasse=(BATERIA['wh'] * PROFUNDIDADE_UTIL / total_w
                                   if total_w and not faltando else None))


# ================================================================== interfaces
INTERFACE_MECANICA = """\
Pontos padronizados, para que um módulo novo não exija quadro novo.

**Malha de montagem.** A chapa de fundo C-01 já tem uma malha de porcas-rebite M6 (ver
`furos_chapa` no modelo: "malha de montagem"). É o padrão a estender aos módulos: passo
da malha a fixar na Rev F, e qualquer bandeja ou berço novo se fixa nela, sem furar o
quadro.

**Envelope por posição.** Três posições de módulo, com limite declarado:

| Posição | Envelope máximo | Massa máxima | Por que o limite |
|---|---|---|---|
| Bandeja de eletrônica (E-01/E-02) | a fixar na Rev F | a fixar | espaço interno e dissipação |
| Topo da gaiola (como o G-06 do LiDAR) | a fixar | **baixa** | tudo aqui está a Z ≈ 397 e sobe o CG |
| Mastro, nos três níveis | a fixar | **a mais baixa das três** | braço de alavanca: ver `efeito_no_cg` |

Os três envelopes estão em branco de propósito: fixá-los exige o desenho dimensional da
OAK-D Pro W PoE, que é a pendência 10 do caderno. Chutar um envelope agora é desenhar
interface para um sensor imaginário.

**Requisitos comuns a toda interface de módulo:**

* orientação definida por **pino de referência**, não só pelo parafuso — um módulo que
  volta girado 1° da manutenção invalida a calibração extrínseca em silêncio;
* acesso ao fixador sem remover outro módulo (requisito de manutenção, seção 16);
* proteção anti-galho no padrão do N-09, em UHMW-PE, para o que avança do envelope;
* coxim antivibração no padrão do G-08 onde houver óptica;
* vedação no padrão das tampas, quando o módulo abre o envelope fechado.
"""

INTERFACE_ELETRICA = """\
**Barramento PoE é o caminho principal.** As 8 OAK-D já são PoE: alimentação e dados no
mesmo cabo. Um módulo novo que fale PoE entra sem cabo novo, sem conector novo e sem
tocar na distribuição — e é por isso que `REQUISITOS_TERMICA` pede Ethernet.

**Tensões disponíveis**, da BOM Rev E:

| Barramento | Origem | Teto |
|---|---|---|
| 51,2 V nominal (16S LiFePO4) | bateria | tração e PoE |
| 12 V | conversor DC/DC 30 A | **360 W** (limite de placa) |

**O que falta, e é bloqueante:** não há tabela de consumo no projeto, então não há como
dizer quanto do 360 W do barramento de 12 V já está comprometido. Enquanto esse número
não existir, nenhum módulo novo pode ser aprovado eletricamente — ver
`pendencias_de_fabricante`.

**Requisitos de projeto para a Rev F:**

* proteção individual por módulo (fusível ou disjuntor), para que um sensor em curto não
  derrube a percepção inteira;
* monitoramento de consumo por ramo, porque autonomia medida vale mais que autonomia
  calculada — e porque é o único jeito de saber se um módulo novo cabe antes de a
  bateria acabar no meio da lavoura;
* **o E-STOP não compartilha** alimentação nem barramento com a percepção. É função de
  segurança: o relé Pilz PNOZ s4 existe para agir quando o resto falhou.
"""

INTERFACE_DADOS = """\
**Protocolos que o projeto realmente usa**, pela BOM: Ethernet (OAK-D PoE e LiDAR), CAN
(IMU Xsens MTi-630 e BMS Daly), UART (GNSS e rádio RFD900x). Um módulo novo deve falar
um destes três. Propor outro exige justificar por que vale o conversor e o driver.

**Sincronização temporal** é o requisito que separa fusão de colecionismo. Sem relógio
comum, oito câmeras e um LiDAR produzem nove registros do mesmo talhão que não se
sobrepõem. O que a plataforma precisa definir na Rev F:

* fonte de tempo (PPS do GNSS é a escolha natural, já que o receptor está a bordo);
* como cada módulo recebe esse tempo (PTP sobre Ethernet, trigger por hardware, ou
  timestamp de software — nesta ordem de preferência e de custo);
* qual erro de sincronização é tolerável. **Derivar da aplicação:** a 1 m/s, 10 ms de
  erro são 10 mm de deslocamento — tolerável para mapear uma falha de plantio,
  intolerável para registrar duas câmeras na mesma folha.

**Identificação do sensor.** Cada módulo precisa reportar modelo, número de série e
versão de firmware, e isso tem de chegar ao SaaS junto com a missão — ver
`FICHA_DE_INTEGRACAO` e a seção de integração do relatório. É o que permite responder
"com que sensor esta imagem foi feita", e sem resposta a comparação entre inspeções de
épocas diferentes não se sustenta.

**Tratamento de erro:** módulo que não responde é missão com configuração degradada, não
missão normal. O SaaS tem de registrar a degradação, e não apresentar o resultado como
se o sensor estivesse lá.
"""

FICHA_DE_INTEGRACAO = [
    'Identificador do módulo (código ValTexa)',
    'Função e o que ele acrescenta que os outros não dão',
    'Massa',
    'Dimensões e envelope ocupado',
    'Consumo (típico e de pico), com a fonte do número',
    'Local de montagem e orientação, com o pino de referência',
    'Campo de visão e distância de trabalho',
    'Interface elétrica (barramento, tensão, proteção)',
    'Interface de dados (protocolo, taxa, porta)',
    'Procedimento de calibração, e o que invalida a calibração',
    'Limitações declaradas — o que ele NÃO mede',
    'Requisitos de validação antes de entrar em produção',
]


# ============================================================ efeito no CG e massa
def efeito_no_cg(massa_kg: float, z_mm: float, m_atual: float = None,
                 z_atual: float = None) -> dict:
    """Quanto um módulo novo mexe no CG e no ângulo de tombamento.

    Existe porque módulo no mastro é o caso que engana: 300 g a 1,7 m pesam no
    tombamento como vários quilos na chapa de fundo, e o requisito crítico desta
    plataforma em lavoura de café é justamente o tombamento.
    """
    import math
    import pathlib
    import sys
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / 'chassi-gaiola'))
    import modelo as M

    c = M.comparacao_baseline()
    m0 = m_atual if m_atual is not None else c['m_nom_novo']
    z0 = z_atual if z_atual is not None else c['zcg_novo']

    m1 = m0 + massa_kg
    z1 = (m0 * z0 + massa_kg * z_mm) / m1
    return dict(
        massa_antes=m0, z_antes=z0, massa_depois=m1, z_depois=z1,
        dz=z1 - z0,
        tomb_antes=math.degrees(math.atan((M.BITOLA / 2) / z0)),
        tomb_depois=math.degrees(math.atan((M.BITOLA / 2) / z1)),
        envelope_antes=M.envelope_estabilidade(z0),
        envelope_depois=M.envelope_estabilidade(z1),
    )


Z_POSICOES = {
    'chapa de fundo (C-01)': 248.0,
    'bandeja de eletrônica (E-01)': 300.0,
    'topo da gaiola (G-06)': 397.0,
    'mastro · nível 1': 700.0,
    'mastro · nível 2': 1200.0,
    'mastro · nível 3 / topo': 1782.0,
}
"""Cotas Z das posições de montagem, do modelo. O nível 3 é ``Z_TOTAL`` da baseline."""


if __name__ == '__main__':
    import sys as _sys
    if hasattr(_sys.stdout, 'reconfigure'):          # o console do Windows é cp1252
        _sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    print('VTX-RV4 Rev F · arquitetura modular de sensores')
    print()
    print(f"Bateria: {BATERIA['wh']:.0f} Wh ({BATERIA['v_nominal']:.1f} V × "
          f"{BATERIA['ah']:.0f} Ah) · útil a {PROFUNDIDADE_UTIL:.0%}: "
          f"{BATERIA['wh'] * PROFUNDIDADE_UTIL:.0f} Wh")
    print(f"Barramento 12 V: teto de {DCDC_12V['w_max']:.0f} W")
    print()
    for chave in CONFIGURACOES:
        o = orcamento(chave)
        print(f"{o['nome']}")
        print(f"    {CONFIGURACOES[chave]['status']}")
        print(f"    consumo com dado disponível: {o['w_conhecido']:.1f} W")
        if o['fecha']:
            print(f"    autonomia: {o['horas_se_fechasse']:.1f} h")
        else:
            print(f"    NÃO FECHA — faltam {len(o['faltando'])} consumos:")
            for f in o['faltando']:
                print(f"        {f}")
        print()
    print('Pendências de fabricante (vão com a RFQ):')
    for p in pendencias_de_fabricante():
        print(f"    {p['modulo']:9} {p['nome'][:50]:50} faltam: {', '.join(p['faltam'])}")
    print()
    print('Efeito de 300 g de módulo novo, por posição de montagem:')
    for nome, z in Z_POSICOES.items():
        e = efeito_no_cg(0.3, z)
        print(f"    {nome:32} Z {z:6.0f} mm  ΔZ_cg {e['dz']:+5.2f} mm  "
              f"tombamento {e['tomb_depois']:.2f}°  envelope {e['envelope_depois']:.2f}°")
