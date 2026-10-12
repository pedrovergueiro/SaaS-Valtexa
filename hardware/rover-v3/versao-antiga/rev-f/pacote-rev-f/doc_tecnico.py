"""DOCUMENTO 1 — VALTEXA ROVER V3 · Documento Técnico de Engenharia Mecânica · Rev E."""
import sys
import pathlib

AQUI = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent / 'chassi-gaiola'))

import modelo as M                      # noqa: E402
from folhas import lista_corte          # noqa: E402
from relatorio import Doc, cat          # noqa: E402


def n(v, d=0):
    return M._n(v) if d == 0 else f'{v:.{d}f}'.replace('.', ',')


def build():
    c = M.consolidado()
    d = Doc('Documento Técnico de Engenharia Mecânica',
            'Arquitetura mecânica do ROVER V3 para avaliação de engenharia, fabricação, corte CNC, '
            'usinagem, soldagem e montagem.',
            'VTX-RV3-DT-E')

    # ---------------------------------------------------------------- 1
    d.h1('Controle de revisão')
    d.tabela(['Revisão', 'Data', 'Descrição', 'Responsável'], [
        ['B', '—', 'CAD preliminar (1.000 × 570 mm) — <b>superado</b>', 'ValTexa'],
        ['D', '—', 'Massas 83,96 / 96,6 kg — usada nos infográficos de apresentação', 'ValTexa'],
        ['E', '18/09/2026', 'Baseline técnica VTX-RV3-BASELINE-E', 'ValTexa'],
        ['E', '19/09/2026', 'Caderno de desenhos VTX-RV3-CG-F (27 folhas A3)', 'ValTexa Engenharia'],
        ['E', '21/09/2026', 'Este pacote de engenharia e orçamento', 'ValTexa Engenharia'],
    ], [10, 14, 58, 18])
    d.nota('Este documento não substitui CAD detalhado, FEA nem ensaio físico. Ele consolida a geometria '
           'verificável da Rev E para que um engenheiro mecânico possa validar e um fornecedor possa cotar.')

    # ---------------------------------------------------------------- 2
    d.h1('Objetivo')
    d.p('Definir a arquitetura mecânica do <b>VALTEXA ROVER V3</b> — geometria, materiais, espessuras, '
        'interfaces, fixações e massas — em nível suficiente para: (a) validação estrutural por engenheiro '
        'mecânico habilitado; (b) cotação de fabricação por empresas de corte, dobra, usinagem e soldagem.')
    d.p('Toda dimensão deste documento carrega uma etiqueta de origem. Nada foi arredondado para parecer '
        'definitivo, e nenhum valor ausente foi preenchido por estimativa silenciosa.')

    # ---------------------------------------------------------------- 3
    d.h1('Aplicação')
    d.p('Rover elétrico 4×4 de tração independente para <b>inspeção de cafezais mecanizados</b> '
        f'(entrelinha de projeto 3.500 mm, copa de projeto 2.400 mm) {cat("CONFIRMADO")}. Percorre a rua '
        'entre as linhas coletando imagens em três alturas por lado, além de LiDAR 3D, GNSS RTK e IMU.')
    d.p('O documento cobre apenas a <b>estrutura mecânica</b>: quadro, chapa de fundo, suportes do motor-roda, '
        'gaiola de proteção, carenagens, mastros, suportes de câmera e interfaces de sensores. Motores, '
        'bateria, eletrônica e sensores são <b>itens de compra</b> e aparecem aqui só pelas suas interfaces.')
    d.alerta('Capacidades operacionais (autonomia, aclive, cobertura por hora) são da baseline Rev E e não '
             'foram reverificadas neste pacote. O limite operacional declarado pela baseline é a <b>aderência '
             'do solo (13,0° em solo firme)</b>, não o tombamento.')

    # ---------------------------------------------------------------- 4
    d.h1('Documentos de referência')
    d.tabela(['Documento', 'Conteúdo', 'Situação'], [
        ['VTX-RV3-BASELINE-E', 'Baseline técnica Rev E (18/09/2026)', f'{cat("CONFIRMADO")} fonte oficial'],
        ['VTX-RV3-CG-F', 'Caderno de desenhos, 27 folhas A3 + 26 DXF',
         f'{cat("CONFIRMADO")} geometria deste pacote'],
        ['Datasheet ElectroCraft MPW86', 'Motor-roda 185V48-1000-S020', f'{cat("CONFIRMADO")} interface'],
        ['VALTEXA-ROVER-V3-RevB-CAD.step', 'CAD preliminar 1.000 × 570', f'{cat("A DEFINIR")} <b>superado</b>'],
        ['VALTEXA-ROVER-V3-BOM-Links-Precos.xlsx', 'Preços de compra, links e cenários (21/09/2026)',
         f'{cat("PESQUISA")} recebida — ver pasta 10_CUSTOS'],
        ['Página do fabricante ZLTECH (Alibaba)', 'Motor-roda ZLLG80ASM800: ficha e preço',
         f'{cat("PESQUISA")} consultada em 21/09/2026'],
        ['BOM de compras Rev E (.docx)', 'Versões em texto da lista de compras',
         f'{cat("A DEFINIR")} <b>não localizadas</b> no projeto'],
    ], [26, 44, 30])
    d.alerta('A planilha <b>VALTEXA-ROVER-V3-BOM-Links-Precos.xlsx</b> foi recebida em 21/09/2026 e está '
             'transcrita e conciliada na pasta <b>10_CUSTOS</b>. Os dois arquivos <b>.docx</b> citados no '
             'escopo continuam ausentes. A BOM <b>mecânica</b> deste pacote segue montada a partir da '
             'geometria do caderno; preço de serviço de fabricação continua como COTAÇÃO NECESSÁRIA.')

    # ---------------------------------------------------------------- 5
    d.h1('Divergências encontradas entre documentos')
    d.p('Nenhuma divergência foi corrigida em silêncio. A coluna “adotado” indica o valor usado nos desenhos '
        'e o motivo.')
    div = [
        ['Massa mínima', 'Rev E, texto: 85,04 kg', 'Rev E, tabela 5.1: soma 82,49 kg',
         f'{n(c["m_min"], 2)} kg recalculado', 'Diferença de 2,55 kg não localizada na própria baseline'],
        ['Massa do quadro', 'Rev E: 2,1 kg', 'Geometria: 5,52 kg', '5,52 kg',
         '2,1 kg equivalem a 3,5 m de tubo 30×30×2; o quadro tem 9,2 m'],
        ['Chapa de fundo', 'Rev E: 1,3 kg', 'Geometria (2 mm): 3,24 kg', '3,24 kg',
         '1,3 kg em 1.046×596 daria ≈ 0,8 mm — não suporta a bateria de 36,5 kg'],
        ['Eixo do mastro', 'Rev E: Y ±300', 'Caderno: Y ±280', 'Y ±280',
         'Com bainha Ø29 em ±300 o tubo ultrapassa a face do quadro'],
        ['Andares das câmeras', 'Rev E: 343 / 891 / 1.440', 'Caderno: 450 / 1.000 / 1.540',
         '450 / 1.000 / 1.540', 'O 1º andar em 343 fica dentro da gaiola (topo em 400)'],
        ['LiDAR', 'Rev E: Z 370', 'Caderno: base em Z 413,2', 'Z 413,2',
         'Em 370 o feixe de −7° é obstruído pela própria gaiola'],
        ['Antena GNSS', 'Rev E: X 0 · Z 390', 'Caderno: X −350 · Z 403,2', 'X −350 · Z 403,2',
         'Em Z 390 a antena fica sob a tampa de alumínio, sem visão de céu'],
        ['Câmera de zona de raiz', 'Rev E: Z 150', 'Caderno: dentro, olhando por janela', 'Dentro do chassi',
         'Em Z 150 seria o ponto mais baixo do rover, exposto a pedra e raiz'],
        ['Vão livre', 'Rev E: 150 mm (sem dizer onde)', 'Caderno: 208 mm entre rodas', '208 mm',
         'Na linha das rodas o ponto mais baixo é 38 mm (suporte S-02)'],
        ['Envelope de estabilidade', 'Rev E: 16,2°',
         f'Fórmula 6.1 da própria Rev E: {n(M.envelope_estabilidade(297.0), 1)}°',
         f'{n(M.envelope_estabilidade(c["zcg"]), 1)}° para o CG atual',
         'Não foi possível reproduzir 16,2° com os parâmetros publicados'],
        ['Largura externa', 'Rev E: 600 mm', 'Com carenagens das câmeras: 674 mm', '600 (corpo) / 674 (total)',
         'As carenagens do mastro projetam 37 mm por lado'],
        ['Gaiola (desenho de apresentação)', 'Imagem: tubo 30×30×2, 6,8 kg, altura 1.050',
         'Projeto: tubo 20×20×1,5, 2,42 kg, Z 340→400', 'Projeto',
         'A imagem usa o comprimento como se fosse altura e o perfil do quadro'],
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
    d.tabela(['Item', 'Documento A', 'Documento B', 'Adotado', 'Impacto / recomendação'],
             div, [13, 21, 21, 18, 27], 'compacta')
    d.p(f'Recomendação: publicar uma <b>Rev F</b> da baseline com um único valor para massa, vão livre, '
        f'largura e envelope. {cat("PROPOSTA")}')

    d.quebra()
    # ---------------------------------------------------------------- 6
    d.h1('Arquitetura mecânica')
    d.tabela(['Subsistema', 'Função', 'Composição', 'Massa (kg)'], [
        ['Q · quadro estrutural', 'Estrutura primária soldada; recebe todas as cargas',
         'Tubo 30×30×2 em 2 anéis (Z 250 e 310→340) ligados por 16 montantes', n(5.52, 2)],
        ['C · chapa de fundo', 'Fecha o quadro por baixo, apoia a bateria, trabalha como diafragma',
         'Chapa 5052-H32 2 mm + 2 nervuras de cantoneira', n(4.21, 2)],
        ['S · suportes do motor-roda', 'Interface entre o quadro e os 4 MPW86',
         '4 conjuntos soldados de 3 chapas (6, 10 e 8 mm)', n(4.54, 2)],
        ['G · gaiola de proteção', 'Protege sensores e eletrônica; apoia tampas e LiDAR',
         '2 módulos idênticos de tubo 20×20×1,5 (Z 343→397)', n(2.42, 2)],
        ['K · carenagens e tampas', 'Fecha as laterais e o topo',
         '6 carenagens 2 mm + 3 tampas 1,2 mm', n(4.60, 2)],
        ['M · mastros', 'Sustenta as 6 câmeras laterais',
         '2 luvas soldadas + 2 hastes Ø25×2 + bainha + 6 suportes', n(0.48 + 2.20, 2)],
        ['B · retenção da bateria', 'Trava a caixa de 36,5 kg', '4 batentes de cantoneira + 2 cintas',
         n(0.49, 2)],
        ['E · eletrônica e E-STOP', 'Bandejas e proteção do botão de emergência',
         '6 bandejas 2 mm + reforço e protetor do E-STOP', n(0.72, 2)],
        ['N · interfaces de sensores', 'Antena GNSS, IMU, câmera de raiz, faróis, carenagens anti-galho',
         '9 itens em alumínio, policarbonato e UHMW-PE', n(0.74, 2)],
    ], [17, 24, 42, 17])

    # ---------------------------------------------------------------- 7
    d.h1('Dimensões gerais')
    dim = [
        ['Comprimento externo', n(M.L_EXT), 'CONFIRMADO', 'Com as carenagens'],
        ['Largura externa (corpo)', n(M.W_EXT), 'CONFIRMADO', 'Com as carenagens laterais'],
        ['Largura total com carenagens das câmeras', '674', 'DERIVADO', 'Na altura dos mastros'],
        ['Altura do corpo (topo da gaiola)', n(M.Z_PROT), 'CONFIRMADO', 'Faixa central em 399,4'],
        ['Altura total com mastros', n(M.Z_TOTAL), 'CONFIRMADO', 'Ponta cônica até 1.822'],
        ['Entre-eixos', n(M.ENTRE_EIXOS), 'CONFIRMADO', 'Centros dos furos Ø88'],
        ['Bitola', n(M.BITOLA), 'CONFIRMADO', 'Centro a centro das rodas'],
        ['Diâmetro da roda', n(M.D_RODA), 'CONFIRMADO', 'ElectroCraft MPW86'],
        ['Altura do quadro (face inferior)', n(M.Z_QUADRO), 'CONFIRMADO', '—'],
        ['Altura do deck (topo do quadro)', n(M.Z_DECK), 'CONFIRMADO', 'Face de apoio da gaiola'],
        ['Quadro soldado', f'{n(M.L_Q)} × {n(M.W_Q)}', 'DERIVADO', 'Envelope − 2 × 2 mm de carenagem'],
        ['Vão livre entre as rodas', '208', 'DERIVADO', 'Ponto mais baixo: nervuras C-02'],
        ['Vão livre na linha das rodas', '38', 'DERIVADO', 'Ponto mais baixo: suporte S-02'],
        ['Vão livre declarado na baseline', '150', 'CONFIRMADO', 'Sem indicação de onde é medido'],
        ['Topo da luva do mastro', n(M.Z_LUVA[1]), 'DERIVADO', '126 mm acima da gaiola'],
        ['Andares das câmeras', ' / '.join(n(z) for z in M.CAMERAS_Z), 'PROPOSTA', 'Baseline: 343/891/1.440'],
        ['Eixo dos mastros', f'X 0 · Y ±{n(M.Y_MASTRO)}', 'PROPOSTA', 'Baseline: ±300'],
        ['Base do LiDAR', n(M.Z_BASE_LIDAR, 1), 'PROPOSTA', 'Baseline: 370'],
        ['Plano de terra da antena GNSS', n(M.Z_GNSS[1], 1), 'PROPOSTA', 'Baseline: 390'],
        ['Face de montagem do IMU', n(M.Z_IMU), 'CONFIRMADO', 'Altura da baseline, posição X +300'],
    ]
    d.tabela(['Dimensão', 'Valor (mm)', 'Origem', 'Observação'],
             [[a, f'<span class="num">{b}</span>', cat(c_), obs] for a, b, c_, obs in dim], [34, 14, 16, 36])

    # ---------------------------------------------------------------- 8
    d.h1('Massa e centro de gravidade')
    linhas = [['Tabela 5.1 da baseline — itens mantidos', n(c['mantidos'][0], 2), n(round(c['mantidos'][1]))]]
    nomes = {'A · Q': 'Parte A — quadro', 'A · M': 'Parte A — base dos mastros',
             'A · C': 'Parte A — chapa de fundo', 'A · S': 'Parte A — suportes do motor-roda',
             'A · G': 'Parte A — gaiola', 'A · K': 'Parte A — carenagens e tampas',
             'B · M': 'Parte B — mastros e suportes', 'B · B': 'Parte B — retenção da bateria',
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
    d.nota('Os valores desta seção são recálculos a partir da geometria, não cálculos estruturais novos. '
           'Verificação de tensões, fadiga e rigidez: folha 25 do caderno (encargos de FEA).')

    d.quebra()
    # ---------------------------------------------------------------- 9
    d.h1('Quadro estrutural (Q)')
    d.p('Dois anéis retangulares de tubo 30×30×2 — inferior em Z 250→280 e superior em Z 310→340 — ligados '
        f'por 16 montantes de 30 mm. Quadro soldado de {n(M.L_Q)} × {n(M.W_Q)} mm. {cat("CONFIRMADO")}')
    d.lista([
        'Material: <b>Al 6061-T6</b> (ASTM B221). Solda TIG com ER5356, filete contínuo a2.',
        'Sem diagonais: a rigidez à torção vem dos dois anéis, dos montantes e da chapa de fundo como '
        'diafragma. As diagonais das imagens de apresentação não cabem no vão de 30 mm entre os anéis.',
        '16 buchas de compressão Q-05 (barra Ø12 com furo Ø8,5) nos pontos de aperto M8 dos suportes, para '
        'a parede do tubo não colapsar.',
        'Tampas Q-06 (chapa 2 mm) fecham as pontas dos tubos.',
        'Tolerâncias gerais <b>ISO 13920-BF</b> (soldados) e <b>ISO 2768-mK</b> (corte e usinagem); '
        'diagonais do quadro com diferença ≤ 2 mm.',
    ])
    d.h2('Base dos mastros (M-01 e M-02), soldada ao quadro')
    d.p('Luva Ø34×4,5 × 180 mm sobre reforço de chapa 6 mm, soldada ao anel superior no vão entre os módulos '
        f'da gaiola, em X 0 · Y ±{n(M.Y_MASTRO)}. {cat("PROPOSTA")} Momento de projeto na base: 72 N·m '
        '(hipótese da baseline: 50 N no topo).')

    # --------------------------------------------------------------- 10
    d.h1('Chapa de fundo e nervuras (C)')
    d.p(f'Chapa 5052-H32 de 2 mm, {n(M.L_Q)} × {n(M.W_Q)}, aparafusada por baixo do anel inferior em 48 '
        'pontos M6 (porca-rebite). Duas nervuras de cantoneira 40×40×4 a ±240 mm do centro.')
    furos = {}
    for (x, y, dia, fn) in M.furos_chapa():
        furos.setdefault((dia, fn), 0)
        furos[(dia, fn)] += 1
    d.tabela(['Ø (mm)', 'Qtd', 'Função'],
             [[f'<span class="num">{n(k[0], 1)}</span>', f'<span class="num">{v}</span>', k[1]]
              for k, v in sorted(furos.items())], [14, 12, 74], 'compacta',
             titulo='Furação da chapa de fundo')
    d.p('Mais a abertura de <b>70 × 120 mm</b> da câmera de zona de raiz, fechada por janela de '
        f'policarbonato de 3 mm montada por dentro. {cat("PROPOSTA")}')

    # --------------------------------------------------------------- 11
    d.h1('Suportes do motor-roda (S)')
    d.p('Quatro conjuntos soldados (2 esquerdos + 2 direitos espelhados), cada um com chapa superior de 6 mm, '
        'chapa de montagem de 10 mm e 2 nervuras de 8 mm. A face de montagem é usinada <b>depois</b> da '
        'solda, com rugosidade Ra 3,2.')
    d.tabela(['Interface', 'Valor', 'Origem'], [
        ['Face de montagem do MPW86', f'Ø{n(M.MPW_FACE, 1)}', cat('CONFIRMADO')],
        ['Círculo de furos (PCD)', f'Ø{n(M.MPW_PCD)} · {M.MPW_N_FUROS} furos M4', cat('CONFIRMADO')],
        ['Furo central (bore)', f'Ø{n(M.D_BORE)}', cat('DERIVADO')],
        ['Distância face E–D', '408 ± 1', cat('DERIVADO')],
        ['Centro do eixo abaixo do quadro', '150 ± 0,5', cat('DERIVADO')],
        ['Orientação dos 7 furos e folga face–roda', 'A VALIDAR com a ElectroCraft', cat('A DEFINIR')],
    ], [40, 40, 20])

    # --------------------------------------------------------------- 12
    d.h1('Gaiola de proteção (G)')
    d.p('Dois módulos <b>idênticos</b> de tubo 20×20×1,5 (o traseiro é o dianteiro girado 180°), aparafusados '
        'ao deck por 12 sapatas de chapa 3 mm. Anel em Z 377→397, montantes de 34 mm, vão central livre de '
        '60 mm para os mastros.')
    d.lista([
        'Fixação ao quadro: M6 em porca-rebite no anel superior, 12 pontos.',
        'Suporte do LiDAR G-06 (chapa 5 mm) sobre 4 coxins de borracha, base em Z 413,2.',
        'Tampas superiores K-04/K-05 (1,2 mm) e faixa central K-06 apoiam nos trilhos.',
        'As sapatas são furadas <b>depois</b> da solda, com gabarito tirado do quadro.',
    ])

    # --------------------------------------------------------------- 13
    d.h1('Mastros e suportes de câmera (M)')
    d.tabela(['Item', 'Descrição', 'Valor', 'Origem'], [
        ['Haste M-10', 'Tubo Al 6061-T6', 'Ø25 × 2 mm · 1.436 mm', cat('CONFIRMADO')],
        ['Luva M-01', 'Tubo soldado ao quadro', 'Ø34 × 4,5 mm · 180 mm', cat('PROPOSTA')],
        ['Travamento', 'Parafusos passantes em X', '2 × M6 por mastro', cat('PROPOSTA')],
        ['Balanço livre', 'Do topo da luva à ponta', f'{n(M.Z_TOTAL - M.Z_LUVA[1])} mm', cat('DERIVADO')],
        ['1ª frequência estimada', 'Viga em balanço, sem bainha/carenagem', '≈ 11,2 Hz', cat('DERIVADO')],
        ['Bainha M-11', 'Anti-galho, 3 segmentos por lado', 'UHMW-PE Ø29/Ø25', cat('CONFIRMADO')],
        ['Ponta M-12', 'Cônica, colada e pinada', 'Ø29 × 40 mm', cat('CONFIRMADO')],
        ['Suporte M-20', 'Placa da câmera, 2 parafusos U', 'Chapa 90 × 70 × 6', cat('PROPOSTA')],
        ['Carenagem N-09', 'Caixa com nariz, desvia galhos', 'UHMW-PE 3 mm, 6 peças', cat('PROPOSTA')],
    ], [16, 36, 30, 18])

    # --------------------------------------------------------------- 14
    d.h1('Câmeras')
    cams = [
        ['1 e 2', 'Esquerdo e direito', f'{n(M.CAMERAS_Z[0])}', 'Perpendicular à copa (±Y)',
         'Tronco e frutos baixos', cat('PROPOSTA')],
        ['3 e 4', 'Esquerdo e direito', f'{n(M.CAMERAS_Z[1])}', 'Perpendicular à copa (±Y)',
         'Folhagem principal', cat('PROPOSTA')],
        ['5 e 6', 'Esquerdo e direito', f'{n(M.CAMERAS_Z[2])}', 'Perpendicular à copa (±Y)',
         'Parte alta da copa', cat('PROPOSTA')],
        ['7', 'Frontal (carenagem K-02)', '≈ 360', 'Para a frente (+X)',
         'Navegação e detecção de obstáculo', cat('CONFIRMADO')],
        ['8', 'Inferior (chapa de fundo)', '≈ 275', 'Para baixo e à frente (≈ 24°)',
         'Zona de raiz e solo', cat('PROPOSTA')],
    ]
    d.tabela(['Câmera', 'Posição', 'Z (mm)', 'Orientação', 'Função', 'Origem'], cams, [10, 22, 10, 22, 24, 12])
    d.p('Distância de trabalho lateral até a copa: <b>270 mm</b>; cobertura vertical de 64 a 1.926 mm com '
        f'~28 % de sobreposição; GSD ≈ 0,26 mm/px. {cat("DERIVADO")} Modelo: Luxonis OAK-D Pro W PoE '
        f'{cat("CONFIRMADO")}. Furação de interface da câmera: {cat("A DEFINIR")}')

    # --------------------------------------------------------------- 15
    d.h1('Sensores e interfaces de sinalização')
    d.tabela(['Sensor', 'Modelo', 'Interface mecânica', 'Origem'], [
        ['LiDAR 3D', 'Livox Mid-360', 'Suporte G-06 (chapa 5) sobre 4 coxins; base Z 413,2', cat('PROPOSTA')],
        ['GNSS RTK', 'u-blox ZED-F9P + antena', 'Suporte N-01 (chapa 5) sobre a tampa traseira, X −350',
         cat('PROPOSTA')],
        ['IMU', 'Xsens MTi-630', 'Berço N-02 com face usinada em Z 310, alinhado a X/Y (0,5°)',
         cat('PROPOSTA')],
        ['Câmeras', '8 × OAK-D Pro W PoE', '6 no mastro (M-20), 1 na K-02, 1 no suporte N-06/N-07',
         cat('PROPOSTA')],
        ['Faróis', 'A definir', '2 furos Ø20 na carenagem frontal + reforço N-08', cat('A DEFINIR')],
        ['E-STOP', 'Botão Ø22 IP65', 'Recorte na tampa traseira + reforço E-10 e protetor E-11',
         cat('PROPOSTA')],
    ], [14, 22, 46, 18])
    d.nota('Furações de interface dos sensores (padrão de furos, rosca e centro de fase) dependem do '
           'datasheet de cada fabricante e estão marcadas como A DEFINIR nas folhas 19 e 22 do caderno.')

    # --------------------------------------------------------------- 16
    d.h1('Rodas, motorização e bateria')
    d.tabela(['Item', 'Dado', 'Origem'], [
        ['Motor-roda', 'ElectroCraft MPW86-185V48-1000-S020 (motor + redutor 20:1 + roda 200 mm + freio)',
         cat('CONFIRMADO')],
        ['Torque contínuo / pico', '20 N·m / 35 N·m por roda', cat('CONFIRMADO')],
        ['Carga máxima por roda', '227 kg', cat('CONFIRMADO')],
        ['Torque de retenção do freio', 'Não publicado — RFQ com a ElectroCraft', cat('A DEFINIR')],
        ['Suspensão', 'Suportes rígidos nesta revisão; curso de 40 mm proposto pela baseline',
         cat('A DEFINIR')],
        ['Bateria', 'LiFePO4 48 V 100 Ah (16 × EVE LF100LA), 36,5 kg', cat('CONFIRMADO')],
        ['Caixa da bateria', '460 × 350 × 130 mm (estimativa) — desenho real inexistente', cat('A DEFINIR')],
        ['Retenção', '4 batentes B-01 na malha de montagem + 2 cintas de poliéster', cat('PROPOSTA')],
        ['Carga de amarração', '36,5 kg × 3 g = 1.074 N vertical / 537 N lateral', cat('DERIVADO')],
    ], [22, 60, 18])

    # --------------------------------------------------------------- 17
    d.h1('Interfaces entre subsistemas')
    d.tabela(['Interface', 'Como é feita', 'Fixadores', 'Origem'], [
        ['Quadro ↔ motores', 'Suporte S soldado e usinado; 4 parafusos M8 por suporte, com buchas Q-05',
         'F-01/F-02/F-03', cat('PROPOSTA')],
        ['Quadro ↔ chapa de fundo', 'Chapa aparafusada por baixo em 48 pontos M6 (porca-rebite)',
         'F-04/F-05/F-12', cat('PROPOSTA')],
        ['Quadro ↔ gaiola', '12 sapatas G-05 aparafusadas no deck (M6)', 'F-04/F-05', cat('PROPOSTA')],
        ['Quadro ↔ mastros', 'Luva M-01 soldada ao anel superior; haste travada por 2 M6 passantes',
         'F-24', cat('PROPOSTA')],
        ['Mastro ↔ câmeras', 'Placa M-20 presa por 2 parafusos U; ajuste em altura, giro e ±18°',
         'F-20/F-21', cat('PROPOSTA')],
        ['Quadro ↔ bateria', 'Batentes B-01 na malha de montagem (24 pontos M6) + 2 cintas',
         'F-22/F-23', cat('PROPOSTA')],
        ['Quadro ↔ eletrônica', 'Bandejas E-01/E-02 na mesma malha; 4 passa-cabos Ø32', 'F-22', cat('PROPOSTA')],
        ['Gaiola ↔ LiDAR', 'Suporte G-06 sobre 4 coxins antivibração M4', 'F-10/G-08', cat('PROPOSTA')],
        ['Tampa ↔ antena GNSS', 'Suporte N-01 aparafusado na tampa traseira (4 × M5)', 'F-26', cat('PROPOSTA')],
        ['Chapa ↔ IMU', 'Berço N-02 sobre 4 espaçadores N-03, face usinada em Z 310', 'F-27',
         cat('PROPOSTA')],
        ['Chapa ↔ câmera de raiz', 'Suporte N-06/N-07 sobre a abertura, janela N-04 por dentro',
         'F-27/F-28', cat('PROPOSTA')],
        ['Carenagem ↔ faróis', '2 furos Ø20 com reforço N-08 por dentro', 'F-29', cat('A DEFINIR')],
    ], [20, 48, 14, 18])

    d.nota('“PROPOSTA” nesta tabela significa: a interface está desenhada, cotada e coerente com a geometria, '
           'mas ainda não foi validada por engenheiro mecânico nem confirmada com o fabricante do componente.')
    return d
