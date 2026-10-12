"""DOCUMENTO 1 — VALTEXA ROVER V4 · Documento Técnico de Engenharia Mecânica · Rev H.

Reescrito em 12/10/2026. A versão anterior descrevia a Rev E do V3 — suportes rígidos, três
câmeras por lado, "8 × OAK-D", placa M-20, carenagem N-09, mastro Ø25×2 — e saiu no pacote do
V4 como se fosse o V4. Este módulo não traz número digitado que exista no modelo: tudo o que
tem cota vem de `chassi-gaiola/modelo.py` ou dos módulos de cálculo de `revisao-h/`.
"""
import importlib.util
import pathlib
import sys

AQUI = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent / 'chassi-gaiola'))

import modelo as M                      # noqa: E402
from folhas import lista_corte, TOTAL, DATA, REV, _sus   # noqa: E402
from relatorio import Doc, cat          # noqa: E402


def _carrega(nome, arq):
    cam = AQUI.parent / 'revisao-h' / arq
    esp = importlib.util.spec_from_file_location(nome, cam)
    mod = importlib.util.module_from_spec(esp)
    esp.loader.exec_module(mod)
    return mod


def n(v, d=0):
    return M._n(v) if d == 0 else f'{v:.{d}f}'.replace('.', ',')


def divergencias(c, MA):
    """As divergências entre documentos que o caderno resolveu, com o valor ADOTADO e o motivo."""
    return [
        ['Massa mínima', 'Rev E, texto: 85,04 kg', 'Rev E, tabela 5.1: soma 82,49 kg',
         f'{n(c["m_min"], 2)} kg recalculado', 'Diferença de 2,55 kg não localizada na própria baseline'],
        ['Bitola', 'Rev E: 470 mm', 'V4: 530 mm', '530 mm',
         'A suspensão pneumática é macia, e rolagem macia derruba o tombamento: a bitola paga a conta '
         '(folha 07)'],
        ['Suspensão', 'Rev E e F: suportes rígidos', 'V4: pneumática independente (grupo W)',
         'Pneumática', 'Decidida pela engenharia em 11/10/2026; desenhada e calculada nas folhas 07 e 28 a 35'],
        ['Eixo do mastro', 'Rev E: Y ±300', f'V4: Y ±{n(M.Y_MASTRO)}', f'Y ±{n(M.Y_MASTRO)}',
         f'A luva Ø{n(M.D_LUVA)} em ±300 passaria do envelope de 600'],
        ['Seção do mastro', 'Rev E: tubo Ø25×2', f'V4: tubo Ø{n(M.D_MASTRO)}×{n(M.E_MASTRO)}',
         f'Ø{n(M.D_MASTRO)}×{n(M.E_MASTRO)}',
         f'Ø25×2 dá {n(MA.frequencia(25, 2, caso="entrega")["freq_Hz"], 2)} Hz contra o requisito de 7,5 Hz; '
         'com térmicas e antena o Ø32×2 também reprova (folha 36)'],
        ['Andares das câmeras', 'Rev E: 343 / 891 / 1.440', f'V4: {" / ".join(n(z) for z in M.CAMERAS_Z)} nominais',
         ' / '.join(n(z) for z in M.CAMERAS_Z), 'O 1º andar em 343 fica dentro da gaiola (topo em 400); '
         'a braçadeira desliza e as cotas são posição de entrega'],
        ['Câmeras', 'Rev E: 8 × OAK-D, a frontal na K-02', 'V4: 9 postos, todos desenhados',
         '9 OAK-D + posições térmicas',
         'A frontal estava declarada e não existia no desenho; a traseira não existia'],
        ['Interface de sensor', 'Rev E: chapa M-20 com furação fixa', 'V4: posto VMS-60 com pino de referência',
         'VMS-60', 'Pino Ø8 H7/h6 repete 0,048°; parafuso em furo de folga erra 1,10° (folha 19)'],
        ['LiDAR', 'Rev E: Z 370', 'Caderno: base em Z 413,2', 'Z 413,2',
         'Em 370 o feixe de −7° é obstruído pela própria gaiola'],
        ['Antena GNSS', 'Rev E: X 0 · Z 390', f'V4: tampa X {n(M.X_GNSS)} ou topo do mastro (T-10)',
         'duas provisões', 'Em Z 390 a antena fica sob a tampa de alumínio; a escolha entre as duas é a pendência P-36'],
        ['Câmera de zona de raiz', 'Rev E: Z 150', 'Caderno: dentro, olhando por janela', 'Dentro do chassi',
         'Em Z 150 seria o ponto mais baixo do rover, exposto a pedra e raiz'],
        ['Vão livre', 'Rev E: 150 mm (sem dizer onde)', 'V4: 150 a 180 mm, ajustável', '150 → 180',
         'Na linha das rodas o ponto mais baixo é 38 mm (chapa W-02)'],
        ['Envelope de estabilidade', 'Rev E: 16,2°',
         f'Fórmula 6.1 da própria Rev E: {n(M.envelope_estabilidade(297.0), 1)}°',
         f'{n(M.envelope_estabilidade(c["zcg"]), 1)}° para o CG atual',
         'Não foi possível reproduzir 16,2° com os parâmetros publicados'],
        ['Largura externa', 'Rev E: 600 mm; o V3 chegava a 674 com as carenagens N-09',
         f'V4: {n(2 * M.envelope()[1][1])} mm', f'{n(2 * M.envelope()[1][1])} mm',
         'A carenagem N-09 foi retirada; a luva do mastro alcança |Y| 297'],
        ['CAD Rev B', 'STEP: 1.000 × 570', 'Rev E: 1.050 × 600', 'Rev E',
         'O STEP disponível é de revisão anterior — não usar para fabricação'],
        ['Motor-roda', 'Rev E e caderno: ElectroCraft MPW86',
         'BOM de compras: ZLTECH ZLLG80ASM800 (R$ 1.133,68 na página do fabricante)',
         'MPW86 nos desenhos', 'Interface do ZLTECH é por eixo e não foi publicada — ver folha 27'],
        ['Preço do motor', 'BOM de compras: R$ 2.215,34/un', 'Página do fabricante: R$ 1.133,68/un',
         'R$ 1.133,68', 'A BOM paga R$ 4.326,64 a mais nos quatro motores'],
        ['Freio', 'Baseline: freio por mola, 15 a 30 N·m/roda', 'ZLTECH: EMB opcional, não pedido na BOM',
         'Pendência', 'Sem freio o rover não estaciona em rampa de 30°'],
    ]


def build():
    c = M.consolidado()
    MA = _carrega('mastro_dt', 'mastro.py')
    MD = _carrega('modular_dt', 'modular.py')
    SU = _sus()
    g, fl, rl = SU.geometria(), SU.fole(), SU.roll()
    v = MA.veredito()
    d = Doc('Documento Técnico de Engenharia Mecânica',
            'Arquitetura mecânica do ROVER V4 para avaliação de engenharia, fabricação, corte CNC, '
            'usinagem, soldagem e montagem.',
            'VTX-RV4-DT-H')

    # ---------------------------------------------------------------- 1
    d.h1('Controle de revisão')
    d.tabela(['Revisão', 'Data', 'Descrição', 'Responsável'], [
        ['B', '—', 'CAD preliminar (1.000 × 570 mm) — <b>superado</b>', 'ValTexa'],
        ['D', '—', 'Massas 83,96 / 96,6 kg — usada nos infográficos de apresentação', 'ValTexa'],
        ['E', '18/09/2026', 'Baseline técnica VTX-RV4-BASELINE-E', 'ValTexa'],
        ['E', '21/09/2026', 'Primeiro caderno de desenhos (27 folhas A3) e pacote de engenharia', 'ValTexa Engenharia'],
        ['F', '11/10/2026', 'V3: marcações do fabricante incorporadas; suportes rígidos; liberação da Parte A '
                           'pelo engenheiro da UNIFEI, <b>sobre esta revisão</b>', 'ValTexa Engenharia'],
        ['G', '11/10/2026', 'V3: suspensão pneumática independente; bitola 470 → 530; desenhos de usinagem do '
                           'grupo W e manual de montagem', 'ValTexa Engenharia'],
        ['H', '11/10/2026', 'V4: sistema modular de sensores (grupo T, VMS-60), nove câmeras, módulo de satélite',
         'ValTexa Engenharia'],
        ['H', f'{DATA}', f'V4: mastro Ø{n(M.D_MASTRO)}×{n(M.E_MASTRO)} dimensionado para a carga completa (térmicas '
                         'removíveis e antena no topo); varredura dos textos herdados do V3; verificador de layout; '
                         'interligação de cabos', 'ValTexa Engenharia'],
    ], [10, 14, 58, 18])
    d.alerta('<b>A liberação do engenheiro (11/10/2026) é sobre a Rev F do V3</b> e não cobre a suspensão '
             'pneumática, o mastro nem o sistema modular de sensores deste V4. O campo de aprovação do caderno '
             'continua <b>vazio</b> — ver VTX-RV4-LIBERACAO-H.')
    d.nota('Este documento não substitui CAD detalhado, FEA nem ensaio físico. Ele consolida a geometria '
           'verificável da Rev H para que um engenheiro mecânico possa validar e um fornecedor possa cotar.')

    # ---------------------------------------------------------------- 2
    d.h1('Objetivo')
    d.p('Definir a arquitetura mecânica do <b>VALTEXA ROVER V4</b> — geometria, materiais, espessuras, '
        'interfaces, fixações e massas — em nível suficiente para: (a) validação estrutural por engenheiro '
        'mecânico habilitado; (b) cotação de fabricação por empresas de corte, dobra, usinagem e soldagem.')
    d.p('Toda dimensão deste documento carrega uma etiqueta de origem. Nada foi arredondado para parecer '
        'definitivo, e nenhum valor ausente foi preenchido por estimativa silenciosa.')

    # ---------------------------------------------------------------- 3
    d.h1('Aplicação')
    d.p('Rover elétrico 4×4 de tração independente para <b>inspeção de cafezais mecanizados</b> '
        f'(entrelinha de projeto 3.500 mm, copa de projeto 2.400 mm) {cat("CONFIRMADO")}. Percorre a rua '
        'entre as linhas coletando imagens em três andares por lado, com a opção de módulos térmicos '
        'removíveis, além de LiDAR 3D, GNSS RTK e IMU.')
    d.p('O documento cobre apenas a <b>estrutura mecânica</b>: quadro, chapa de fundo, suspensão pneumática, '
        'gaiola de proteção, carenagens, mastros e a interface modular de sensores. Motores, bateria, '
        'eletrônica e sensores são <b>itens de compra</b> e aparecem aqui só pelas suas interfaces.')
    d.alerta('Capacidades operacionais (autonomia, aclive, cobertura por hora) são da baseline Rev E e não '
             'foram reverificadas neste pacote. O limite operacional declarado pela baseline é a <b>aderência '
             'do solo (13,0° em solo firme)</b>, não o tombamento.')

    # ---------------------------------------------------------------- 4
    d.h1('Documentos de referência')
    d.tabela(['Documento', 'Conteúdo', 'Situação'], [
        ['VTX-RV4-BASELINE-E', 'Baseline técnica Rev E (18/09/2026)', f'{cat("CONFIRMADO")} fonte oficial'],
        ['VTX-RV4-CG-H', f'Caderno de desenhos, {TOTAL} folhas A3 + DXF 1:1',
         f'{cat("CONFIRMADO")} geometria deste pacote'],
        ['VTX-RV4-*-H (11_ENGENHARIA_REV_H)', 'Mastro, modular, suspensão, usinagem, montagem, espaço, cabos, '
         'auditoria e liberação', f'{cat("CONFIRMADO")} gerados do modelo'],
        ['Datasheet ElectroCraft MPW86', 'Motor-roda 185V48-1000-S020', f'{cat("CONFIRMADO")} interface'],
        ['VALTEXA-ROVER-V3-BOM-Links-Precos.xlsx', 'Preços de compra, links e cenários (21/09/2026)',
         f'{cat("PESQUISA")} recebida — ver pasta 10_CUSTOS; preços do V3, <b>não do V4</b>'],
        ['Página do fabricante ZLTECH (Alibaba)', 'Motor-roda ZLLG80ASM800: ficha e preço',
         f'{cat("PESQUISA")} consultada em 21/09/2026'],
        ['VALTEXA-ROVER-V3-RevB-CAD.step', 'CAD preliminar 1.000 × 570', f'{cat("A DEFINIR")} <b>superado</b>'],
    ], [26, 44, 30])
    d.alerta('As imagens conceituais geradas por inteligência artificial em conversas anteriores <b>não são '
             'fonte válida de cota de fabricação</b>: foram usadas como intenção de projeto (folha 41) e nada '
             'mais. Toda cota vem do modelo paramétrico.')

    # ---------------------------------------------------------------- 5
    d.h1('Divergências encontradas entre documentos')
    d.p('Nenhuma divergência foi corrigida em silêncio. A coluna “adotado” indica o valor usado nos desenhos '
        'e o motivo.')
    div = divergencias(c, MA)
    d.tabela(['Item', 'Documento A', 'Documento B', 'Adotado', 'Impacto / recomendação'],
             div, [13, 21, 21, 18, 27], 'compacta')
    d.p(f'{len(div)} divergências registradas. Recomendação: publicar uma baseline nova com um único valor '
        f'para massa, vão livre, largura e envelope. {cat("PROPOSTA")}')

    d.quebra()
    # ---------------------------------------------------------------- 6
    d.h1('Arquitetura mecânica')
    ma = M.resumo_massas('A')
    mb = M.resumo_massas('B')
    d.tabela(['Subsistema', 'Função', 'Composição', 'Massa (kg)'], [
        ['Q · quadro estrutural', 'Estrutura primária soldada; recebe todas as cargas',
         'Tubo 30×30×2 em 2 anéis (Z 250 e 310→340) ligados por 16 montantes', n(ma['Q'][0], 2)],
        ['C · chapa de fundo', 'Fecha o quadro por baixo, apoia a bateria, trabalha como diafragma',
         'Chapa 5052-H32 2 mm + 2 nervuras de cantoneira', n(ma['C'][0], 2)],
        ['W · suspensão pneumática', 'Liga cada motor-roda ao quadro; um fole por canto, sem barra estabilizadora',
         'Braço longitudinal soldado em aço, torre do pivô, prato articulado e berço do fole, em 4 cantos',
         n(ma['W'][0], 2)],
        ['G · gaiola de proteção', 'Protege sensores e eletrônica; apoia tampas e LiDAR',
         '2 módulos idênticos de tubo 20×20×1,5 (Z 343→397)', n(ma['G'][0], 2)],
        ['K · carenagens e tampas', 'Fecha as laterais e o topo',
         '6 carenagens 2 mm + 3 tampas 1,2 mm', n(ma['K'][0], 2)],
        ['M · mastros', 'Sustenta as câmeras laterais e, no topo, a antena',
         f'2 luvas Ø{n(M.D_LUVA)}×{n(M.E_LUVA)} soldadas + 2 hastes Ø{n(M.D_MASTRO)}×{n(M.E_MASTRO)} + bainha',
         n(ma['M'][0] + mb['M'][0], 2)],
        ['T · interface modular VMS-60', 'Posto de sensor com pino de referência: 9 postos e 4 posições térmicas',
         'Braçadeira, prato, adaptador e protetor por posto; berços de extremidade, de raiz e de satélite',
         n(mb['T'][0], 2)],
        ['B · retenção da bateria', 'Trava a caixa de 36,5 kg', '4 batentes de cantoneira + 2 cintas',
         n(mb['B'][0], 2)],
        ['E · eletrônica e E-STOP', 'Bandejas e proteção do botão de emergência',
         '6 bandejas 2 mm + reforço e protetor do E-STOP', n(mb['E'][0], 2)],
        ['N · interfaces de sensores', 'Antena GNSS, IMU, câmera de raiz e faróis',
         'Itens em alumínio e policarbonato', n(mb['N'][0], 2)],
    ], [17, 24, 42, 17])
    d.nota('Massas de peça fabricada, calculadas da geometria. Os módulos opcionais (4 postos térmicos e o '
           'adaptador de antena T-10) não entram nesta tabela.')

    # ---------------------------------------------------------------- 7
    d.h1('Dimensões gerais')
    dim = [
        ['Comprimento externo', n(M.L_EXT), 'CONFIRMADO', 'Com as carenagens'],
        ['Largura externa', n(2 * M.envelope()[1][1]), 'DERIVADO', 'Envelope: a luva do mastro alcança |Y| 297'],
        ['Altura do corpo (topo da gaiola)', n(M.Z_PROT), 'CONFIRMADO', 'Faixa central em 399,4'],
        ['Topo do tubo do mastro', n(M.Z_TOTAL), 'DERIVADO', 'Antena no topo: 1.832 (provisão T-10)'],
        ['Entre-eixos', n(M.ENTRE_EIXOS), 'CONFIRMADO', 'Centros dos furos Ø88'],
        ['Bitola', n(M.BITOLA), 'DERIVADO', 'Centro a centro das rodas; era 470 na Rev E'],
        ['Diâmetro da roda', n(M.D_RODA), 'CONFIRMADO', 'ElectroCraft MPW86'],
        ['Altura do quadro (face inferior)', n(M.Z_QUADRO), 'CONFIRMADO', '—'],
        ['Altura do deck (topo do quadro)', n(M.Z_DECK), 'CONFIRMADO', 'Face de apoio da gaiola'],
        ['Quadro soldado', f'{n(M.L_Q)} × {n(M.W_Q)}', 'DERIVADO', 'Envelope − 2 × 2 mm de carenagem'],
        ['Vão livre entre as rodas', '208', 'DERIVADO', 'Ponto mais baixo: nervuras C-02'],
        ['Vão livre na linha das rodas', '38', 'DERIVADO', 'Ponto mais baixo: chapa W-02'],
        ['Vão livre de projeto', f'{n(g["vao_min"])} → {n(g["vao_max"])}', 'PROPOSTA', 'Ajustável pelo ar'],
        ['Topo da luva do mastro', n(M.Z_LUVA[1]), 'DERIVADO', '126 mm acima da gaiola'],
        ['Andares das OAK-D (nominais)', ' / '.join(n(z) for z in M.CAMERAS_Z), 'PROPOSTA',
         'A braçadeira desliza; baseline: 343/891/1.440'],
        ['Posições térmicas (nominais)', ' / '.join(n(z) for z in M.Z_TERMICA), 'PROPOSTA', 'Opcionais, por mastro'],
        ['Eixo dos mastros', f'X 0 · Y ±{n(M.Y_MASTRO)}', 'PROPOSTA', 'Baseline: ±300'],
        ['Base do LiDAR', n(M.Z_BASE_LIDAR, 1), 'PROPOSTA', 'Baseline: 370'],
        ['Plano de terra da antena na tampa', n(M.Z_GNSS[1], 1), 'PROPOSTA', 'Baseline: 390'],
        ['Face de montagem do IMU', n(M.Z_IMU), 'CONFIRMADO', 'Altura da baseline, posição X +300'],
    ]
    d.tabela(['Dimensão', 'Valor (mm)', 'Origem', 'Observação'],
             [[a, f'<span class="num">{b}</span>', cat(c_), obs] for a, b, c_, obs in dim], [34, 14, 16, 36])

    # ---------------------------------------------------------------- 8
    d.h1('Massa e centro de gravidade')
    linhas = [['Tabela 5.1 da baseline — itens mantidos', n(c['mantidos'][0], 2), n(round(c['mantidos'][1]))]]
    nomes = {'A · Q': 'Parte A — quadro', 'A · M': 'Parte A — base dos mastros',
             'A · C': 'Parte A — chapa de fundo', 'A · W': 'Parte A — suspensão pneumática',
             'A · G': 'Parte A — gaiola', 'A · K': 'Parte A — carenagens e tampas',
             'B · M': 'Parte B — haste e bainha dos mastros', 'B · T': 'Parte B — interface VMS-60',
             'B · B': 'Parte B — retenção da bateria',
             'B · E': 'Parte B — bandejas e E-STOP', 'B · N': 'Parte B — interfaces de sensores',
             'Fixadores': 'Fixadores (estimativa)'}
    for nome, m, z in c['novos']:
        linhas.append([nomes.get(nome, nome), n(m, 2), n(round(z))])
    linhas.append('<tr class="total"><td>Massa mínima verificável</td>'
                  f'<td class="num">{n(c["m_min"], 2)}</td><td class="num">{n(c["zcg"], 1)}</td></tr>')
    d.tabela(['Parcela', 'kg', 'Z do CG (mm)'], linhas, [58, 20, 22])
    d.tabela(['Grandeza', 'Baseline Rev E', 'Este pacote', 'Origem'], [
        ['Massa mínima', '85,04 declarada · 82,49 somada', f'<b>{n(c["m_min"], 2)} kg</b>', cat('DERIVADO')],
        ['Margem de crescimento de 15 %', '12,76 kg', f'{n(c["margem"], 2)} kg restantes', cat('DERIVADO')],
        ['Massa máxima (payload 25 kg)', '≈ 126 kg', f'{n(c["m_max"], 1)} kg', cat('DERIVADO')],
        ['CG — altura Z', '297 mm', f'{n(c["zcg"], 1)} mm', cat('DERIVADO')],
        ['Tombamento lateral estático', '38,3°', f'{n(c["tomb"], 1)}°', cat('DERIVADO')],
        ['Envelope conservador (fórmula 6.1)', '16,2°', f'{n(M.envelope_estabilidade(c["zcg"]), 1)}°',
         cat('DERIVADO')],
        ['Torque por roda a 13°', '11,0 N·m', f'{n(c["torque13"], 1)} N·m (limite 20)', cat('DERIVADO')],
    ], [30, 26, 26, 18])
    d.alerta(f'A massa mínima verificável <b>passa da baseline em {n(c["delta"], 2)} kg</b> e consome toda a margem '
             f'de 15 % ({n(c["margem"], 2)} kg restantes — negativo). O aço da suspensão é a maior parcela. '
             'É decisão de engenharia e de gestão: reduzir massa ou refazer a baseline (folha 24).')
    d.nota('Os valores desta seção são recálculos a partir da geometria, não cálculos estruturais novos. '
           'Não incluem câmeras, antena, terminal de satélite nem cabos: são massas estimadas ou sem modelo. '
           'Verificação de tensões, fadiga e rigidez: folha 25 do caderno (encargos de FEA).')

    # ---------------------------------------------------------------- 9
    d.quebra()
    d.h1('Quadro estrutural (Q)')
    d.p('Dois anéis retangulares de tubo 30×30×2 — inferior em Z 250→280 e superior em Z 310→340 — ligados '
        f'por 16 montantes de 30 mm. Quadro soldado de {n(M.L_Q)} × {n(M.W_Q)} mm. {cat("CONFIRMADO")}')
    d.lista([
        'Material: <b>Al 6061-T6</b> (ASTM B221). Solda TIG com ER5356, filete contínuo a2.',
        'Sem diagonais: a rigidez à torção vem dos dois anéis, dos montantes e da chapa de fundo como '
        'diafragma. As diagonais das imagens de apresentação não cabem no vão de 30 mm entre os anéis.',
        '16 buchas de compressão Q-05 (barra Ø12 com furo Ø8,5) nos pontos de aperto M8 da suspensão, para '
        'a parede do tubo não colapsar.',
        'Tampas Q-06 (chapa 2 mm) fecham as pontas dos tubos.',
        'Tolerâncias gerais <b>ISO 13920-BF</b> (soldados) e <b>ISO 2768-mK</b> (corte e usinagem); '
        'diagonais do quadro com diferença ≤ 2 mm.',
    ])
    d.h2('Base dos mastros (M-01 e M-02), soldada ao quadro')
    d.p(f'Luva Ø{n(M.D_LUVA)}×{n(M.E_LUVA)} × {n(M.L_LUVA)} mm sobre reforço de chapa {n(M.E_REF_M)} mm, soldada ao '
        f'anel superior no vão entre os módulos da gaiola, em X 0 · Y ±{n(M.Y_MASTRO)}. {cat("PROPOSTA")} '
        f'Momento de projeto na base: {n(MA.GALHO_N * (M.Z_TOTAL - M.Z_REF_M[1]) / 1000, 0)} N·m '
        f'(galho de projeto de {n(MA.GALHO_N)} N no topo). As soldas estão <b>escaladas</b> da conta anterior, '
        'não recalculadas — entram no caso 6 do FEA.')

    # --------------------------------------------------------------- 10
    d.h1('Chapa de fundo e nervuras (C)')
    d.p(f'Chapa 5052-H32 de 2 mm, {n(M.L_Q)} × {n(M.W_Q)}, aparafusada por baixo do anel inferior em 48 '
        'pontos M6 (porca-rebite). Duas nervuras de cantoneira 40×40×4.')
    furos = {}
    for (x, y, dia, fn) in M.furos_chapa():
        furos.setdefault((dia, fn), 0)
        furos[(dia, fn)] += 1
    d.tabela(['Ø (mm)', 'Qtd', 'Função'],
             [[f'<span class="num">{n(k[0], 1)}</span>', f'<span class="num">{v}</span>', k[1]]
              for k, v in sorted(furos.items())], [14, 12, 74], 'compacta',
             titulo='Furação da chapa de fundo')
    d.p('Mais a abertura de <b>70 × 120 mm</b> da câmera de zona de raiz, fechada por janela de '
        f'policarbonato de 3 mm montada por dentro, e os 4 colares de vedação dos foles (W-12/W-13). '
        f'{cat("PROPOSTA")}')

    # --------------------------------------------------------------- 11
    d.h1('Suspensão pneumática independente (W)')
    d.p('Quatro cantos independentes, um fole por canto, <b>sem barra estabilizadora</b> — descartada por '
        f'cálculo: com rigidez de roda de {n(fl["k_roda_N_mm"], 2)} N/mm os foles sozinhos já transferem '
        f'{n(SU.barra_estabilizadora()["transferencia_dos_foles_N"])} N dos '
        f'{n(SU.barra_estabilizadora()["carga_estatica_N"])} N estáticos numa articulação de 60 mm. '
        'A maior parte do grupo é <b>aço</b>, porque a peça cicla com o terreno e o alumínio não tem limite de fadiga.')
    d.tabela(['Grandeza', 'Valor', 'Origem'], [
        ['Braço efetivo (pivô → roda)', f'{n(g["braco"])} mm', cat('DERIVADO')],
        ['Estação do fole no braço', f'{n(g["r_fole"])} mm', cat('DERIVADO')],
        ['Curso de trabalho na roda', f'± {n(g["curso_trabalho"])} mm', cat('PROPOSTA')],
        ['Ajuste de vão livre', f'{n(g["vao_min"])} → {n(g["vao_max"])} mm', cat('PROPOSTA')],
        ['Curso total na roda / no fole', f'{n(g["curso_roda"])} / {n(g["curso_fole"])} mm', cat('DERIVADO')],
        ['Giro do braço, batente a batente', f'{n(g["giro_total_deg"], 1)}°', cat('DERIVADO')],
        ['Rolagem máxima da carroceria', f'{n(g["rolagem_max_deg"], 2)}°', cat('DERIVADO')],
        ['Tombamento / envelope de estabilidade', f'{n(rl["tombamento_deg"], 2)}° / {n(rl["envelope_deg"], 2)}°',
         cat('DERIVADO')],
        ['Área efetiva do fole (requisito)', f'{n(fl["area_mm2"])} mm² ± 10 %', cat('A DEFINIR')],
        ['Pressão de trabalho / de projeto', f'{n(fl["p_estatica_bar"], 2)} / {n(fl["p_projeto_bar"], 2)} bar',
         cat('DERIVADO')],
    ], [40, 40, 20])
    d.alerta('<b>O fole é comprado e nenhum modelo foi escolhido</b> (P-20). O que está desenhado é a interface: '
             'prato W-08, berço W-11, colar W-12, curso e altura. O caso 9 do FEA (fadiga do aço) não foi rodado.')

    # --------------------------------------------------------------- 12
    d.h1('Gaiola de proteção (G)')
    d.p('Dois módulos <b>idênticos</b> de tubo 20×20×1,5 (o traseiro é o dianteiro girado 180°), aparafusados '
        'ao deck por 12 sapatas de chapa 3 mm. Anel em Z 377→397, montantes de 34 mm, vão central livre para os '
        'mastros.')
    d.lista([
        'Fixação ao quadro: M6 em porca-rebite no anel superior, 12 pontos.',
        f'Suporte do LiDAR G-06 (chapa 5 mm) sobre 4 coxins de borracha, base em Z {n(M.Z_BASE_LIDAR, 1)}. '
        'É o único sensor isolado do projeto.',
        'Tampas superiores K-04/K-05 (1,2 mm) e faixa central K-06 apoiam nos trilhos.',
        'As sapatas são furadas <b>depois</b> da solda, com gabarito tirado do quadro.',
    ])

    # --------------------------------------------------------------- 13
    d.h1('Mastros (M)')
    d.tabela(['Item', 'Descrição', 'Valor', 'Origem'], [
        ['Haste M-10', 'Tubo Al 6061-T6', f'Ø{n(M.D_MASTRO)} × {n(M.E_MASTRO)} mm · {n(M.Z_TOTAL - M.Z_REF_M[1])} mm',
         cat('PROPOSTA')],
        ['Luva M-01', 'Tubo soldado ao quadro', f'Ø{n(M.D_LUVA)} × {n(M.E_LUVA)} mm · {n(M.L_LUVA)} mm', cat('PROPOSTA')],
        ['Travamento', 'Parafusos passantes em X', '2 × M6 por mastro', cat('PROPOSTA')],
        ['Balanço livre', 'Do topo da luva à ponta', f'{n(M.Z_TOTAL - M.Z_LUVA[1])} mm', cat('DERIVADO')],
        ['Bainha M-11', 'Anti-galho, interrompida em cada posto',
         f'UHMW-PE Ø{n(M.D_BAINHA)}/Ø{n(M.D_MASTRO)}, {len(M._faixas_bainha())} trechos por mastro', cat('PROPOSTA')],
        ['Ponta M-12', 'Cônica, colada e pinada; sai quando a antena entra', f'Ø{n(M.D_BAINHA)} × 40 mm', cat('PROPOSTA')],
        ['Adaptador T-10', 'Topo do mastro, para a antena GNSS (opcional)',
         f'Ø{n(M.D_ENCAIXE_ANTENA)} × {n(M.L_ENCAIXE_ANTENA + M.H_TOPO_ANTENA)}, furo Ø{n(M.D_CABO_ANTENA)}', cat('PROPOSTA')],
    ], [16, 36, 30, 18])
    d.h2('Rigidez — a conta que obrigou a engrossar o tubo duas vezes')
    d.p(f'O caso 6 do FEA exige 1ª frequência ≥ {n(MA.REQUISITO_FREQ_HZ, 1)} Hz e estava aberto desde a Rev E. '
        f'Com o mastro cheio — 3 OAK-D, 2 térmicas removíveis por mastro e antena de {n(MA.MASSA_ANTENA, 2)} kg '
        f'no topo — o Ø25×2 dá {n(MA.frequencia(25, 2)["freq_Hz"], 2)} Hz, o Ø32×2 dá '
        f'{n(MA.frequencia(32, 2)["freq_Hz"], 2)} Hz e o <b>Ø{n(M.D_MASTRO)}×{n(M.E_MASTRO)} adotado dá '
        f'{n(v["freq_mastro_Hz"], 2)} Hz</b>. {cat("DERIVADO")}')
    d.alerta(f'<b>A margem contra o terreno NÃO fecha:</b> razão {n(v["razao"], 2)} contra o mínimo de '
             f'{n(MA.MARGEM_MINIMA, 1)} a {n(MA.VELOCIDADE_MS, 1)} m/s. Só fecha abaixo de '
             f'{n(v["velocidade_maxima_ms"], 2)} m/s. A excitação é critério, não medição: o ensaio V-12 decide '
             f'(P-39). O mastro cumpre o requisito de {n(MA.REQUISITO_FREQ_HZ, 1)} Hz com folga de só '
             f'{n((v["freq_mastro_Hz"] - MA.REQUISITO_FREQ_HZ) / MA.REQUISITO_FREQ_HZ * 100, 0)} % — sobre massas '
             'que ninguém mediu (OAK-D, térmica e antena são estimativas).')

    # --------------------------------------------------------------- 14
    d.h1('Câmeras e a interface modular VMS-60')
    rep = MD.repetibilidade()
    d.p('Todo posto de sensor apresenta a <b>mesma face VMS-60</b>: dois pinos de referência (Ø8 H7/h6 no centro e '
        f'Ø6 H7/h6 a {n(M.Z_PINO_GIRO)} mm) e quatro parafusos M5 em {n(M.VMS_FUROS[0])} × {n(M.VMS_FUROS[1])}. '
        f'Repetibilidade angular de <b>{n(rep["com_pino_deg"], 3)}°</b> com pino contra '
        f'{n(rep["sem_pino_deg"], 2)}° só com parafuso — fator {n(rep["fator"])}. {cat("DERIVADO")} É cálculo: '
        'o ensaio V-10 é o que valida ou derruba o argumento.')
    cams = [
        ['C1 a C6', 'Mastros, 3 andares por lado', ' / '.join(n(z) for z in M.CAMERAS_Z),
         'Perpendicular à copa (±Y)', 'Inspeção', cat('PROPOSTA')],
        ['H1 a H4', 'Mastros, entre os andares (térmica removível)', ' / '.join(n(z) for z in M.Z_TERMICA),
         'Perpendicular à copa (±Y)', 'Inspeção (opcional)', cat('PROPOSTA')],
        ['C7 e C8', 'Sob o nariz e sob a traseira do chassi', n(M.Z_CAM_EXTREMIDADE), 'Frente e trás',
         'Navegação', cat('PROPOSTA')],
        ['C9', 'Dentro do chassi, sobre a janela de raiz', '298', 'Para baixo', 'Zona de raiz', cat('PROPOSTA')],
    ]
    d.tabela(['Posto', 'Posição', 'Z (mm)', 'Orientação', 'Classe', 'Origem'], cams, [10, 28, 14, 20, 16, 12])
    pt = MD.protecao()
    d.p(f'Distância de trabalho lateral até a copa: <b>{n(550 - M.Y_MASTRO)} mm</b>. O campo vertical da OAK-D Pro W '
        f'é o divulgado, {n(MD.FOV_V_DEG)}° {cat("A DEFINIR")} — <b>não os 110° do V3</b>: com {n(MD.FOV_V_DEG)}° os '
        'três andares deixam faixas sem cobertura entre si (folha 18, P-35). Modelo: Luxonis OAK-D Pro W PoE. '
        f'Furação de interface da câmera: {cat("A DEFINIR")} (P-06).')
    d.p(f'<b>Proteção sem nada na frente da lente:</b> com {n(MD.FOV_H_DEG)}° de campo, qualquer peça a '
        f'{n(pt["avanco_mm"])} mm da lente teria de estar a {n(pt["lateral_necessaria_mm"])} mm do eixo para não '
        'aparecer na imagem — não cabe. Vale a sobrancelha superior sacrificial T-05. Não há grade, aro nem defletor.')
    d.p('<b>Câmera rígida, LiDAR isolado.</b> Isolar a câmera trocaria borrão de movimento por deriva de '
        'calibração extrínseca, que nenhum pós-processamento corrige.')

    # --------------------------------------------------------------- 15
    d.h1('Sensores e interfaces de sinalização')
    d.tabela(['Sensor', 'Modelo', 'Interface mecânica', 'Origem'], [
        ['LiDAR 3D', 'Livox Mid-360', f'Suporte G-06 (chapa 5) sobre 4 coxins; base Z {n(M.Z_BASE_LIDAR, 1)}',
         cat('PROPOSTA')],
        ['GNSS RTK', 'u-blox ZED-F9P + antena',
         f'Duas provisões: N-01 na tampa traseira (X {n(M.X_GNSS)}) ou T-10 no topo do mastro — decisão aberta (P-36)',
         cat('PROPOSTA')],
        ['IMU', 'Xsens MTi-630', 'Berço N-02 com face usinada em Z 310, alinhado a X/Y (0,5°)', cat('PROPOSTA')],
        ['Câmeras de inspeção', '6 × OAK-D Pro W PoE no mastro + 1 de raiz', 'Posto VMS-60', cat('PROPOSTA')],
        ['Câmeras de navegação', '2 × OAK-D Pro W PoE (frontal e traseira)', 'Berço T-06 sob o chassi, Z 210',
         cat('PROPOSTA')],
        ['Térmicas', 'Nenhum modelo escolhido (P-30)', 'Posto VMS-60 com adaptador T-04 — requisito, não desenho',
         cat('A DEFINIR')],
        ['Terminal de satélite', 'Nenhum escolhido (P-32)',
         f'Berço T-07; envelope {n(M.SAT_ENVELOPE[0])} × {n(M.SAT_ENVELOPE[1])} × {n(M.SAT_ENVELOPE[2])} — '
         'um terminal da classe do Starlink Mini NÃO cabe', cat('A DEFINIR')],
        ['Faróis', 'A definir', '2 furos Ø20 na carenagem frontal + reforço N-08', cat('A DEFINIR')],
        ['E-STOP', 'Botão Ø22 IP65', 'Recorte na tampa traseira + reforço E-10 e protetor E-11', cat('PROPOSTA')],
    ], [14, 22, 46, 18])
    d.nota('Furações de interface dos sensores (padrão de furos, rosca e centro de fase) dependem do '
           'datasheet de cada fabricante e estão marcadas como A DEFINIR nas folhas 19, 22 e 37. O projeto '
           '<b>não declara grau IP</b> de nenhum posto: grau IP é resultado de ensaio (V-11).')

    # --------------------------------------------------------------- 16
    d.h1('Rodas, motorização e bateria')
    d.tabela(['Item', 'Dado', 'Origem'], [
        ['Motor-roda', 'ElectroCraft MPW86-185V48-1000-S020 (motor + redutor 20:1 + roda 200 mm + freio)',
         cat('CONFIRMADO')],
        ['Torque contínuo / pico', '20 N·m / 35 N·m por roda', cat('CONFIRMADO')],
        ['Carga máxima por roda', '227 kg', cat('CONFIRMADO')],
        ['Torque de retenção do freio', 'Não publicado — RFQ com a ElectroCraft', cat('A DEFINIR')],
        ['Bateria', 'LiFePO4 48 V 100 Ah (16 × EVE LF100LA), 36,5 kg', cat('CONFIRMADO')],
        ['Caixa da bateria', '460 × 350 × 130 mm (estimativa) — <b>não cabe</b> no compartimento medido '
                             '(ver espaco.py); desenho real inexistente', cat('A DEFINIR')],
        ['Retenção', '4 batentes B-01 na malha de montagem + 2 cintas de poliéster', cat('PROPOSTA')],
        ['Carga de amarração', '36,5 kg × 3 g = 1.074 N vertical / 537 N lateral', cat('DERIVADO')],
    ], [22, 60, 18])

    # --------------------------------------------------------------- 17
    d.h1('Interfaces entre subsistemas')
    d.tabela(['Interface', 'Como é feita', 'Fixadores', 'Origem'], [
        ['Quadro ↔ suspensão', 'Berços W-06 e W-11 no anel inferior: um M8 amarra quatro níveis, com buchas Q-05',
         'F-01/F-02/F-03/F-30', cat('PROPOSTA')],
        ['Suspensão ↔ motor-roda', 'Chapa W-02 usinada depois da solda; 7 × M4 com trava química', 'F-10',
         cat('PROPOSTA')],
        ['Quadro ↔ chapa de fundo', 'Chapa aparafusada por baixo em 48 pontos M6 (porca-rebite)',
         'F-04/F-05/F-12', cat('PROPOSTA')],
        ['Quadro ↔ gaiola', '12 sapatas G-05 aparafusadas no deck (M6)', 'F-04/F-05', cat('PROPOSTA')],
        ['Quadro ↔ mastros', 'Luva M-01 soldada ao anel superior; haste travada por 2 M6 passantes',
         'F-24', cat('PROPOSTA')],
        ['Mastro ↔ sensores', 'Braçadeira T-01 (2 × M6) + prato T-02 + adaptador T-03/T-04 sobre pinos',
         'F-20/F-21/F-40/F-41/F-42', cat('PROPOSTA')],
        ['Quadro ↔ bateria', 'Batentes B-01 na malha de montagem (24 pontos M6) + 2 cintas',
         'F-22/F-23', cat('PROPOSTA')],
        ['Quadro ↔ eletrônica', 'Bandejas E-01/E-02 na mesma malha; 4 passa-cabos Ø32 para os motores',
         'F-22', cat('PROPOSTA')],
        ['Gaiola ↔ LiDAR', 'Suporte G-06 sobre 4 coxins antivibração M4', 'F-10/G-08', cat('PROPOSTA')],
        ['Tampa ↔ antena GNSS', 'Suporte N-01 aparafusado na tampa traseira (4 × M5)', 'F-26', cat('PROPOSTA')],
        ['Tampa ↔ terminal de satélite', 'Berço T-07 na tampa traseira (6 × M5) — furos acrescentados à K-05 nesta '
                                         'revisão', 'F-58', cat('PROPOSTA')],
        ['Chapa ↔ IMU', 'Berço N-02 sobre 4 espaçadores N-03, face usinada em Z 310', 'F-27', cat('PROPOSTA')],
        ['Chapa ↔ câmera de raiz', 'Berço T-09 dentro do compartimento, sobre a janela N-04', 'F-27/F-28',
         cat('PROPOSTA')],
        ['Carenagem ↔ faróis', '2 furos Ø20 com reforço N-08 por dentro', 'F-29', cat('A DEFINIR')],
    ], [20, 48, 14, 18])
    d.nota('“PROPOSTA” nesta tabela significa: a interface está desenhada, cotada e coerente com a geometria, '
           'mas ainda não foi validada por engenheiro mecânico nem confirmada com o fabricante do componente.')
    return d
