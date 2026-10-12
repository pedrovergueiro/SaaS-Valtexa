"""DOCUMENTO 2 — Pacote de fabricação · e DOCUMENTO 7 — RFQ (solicitação de orçamento)."""
import dados
import modelo as M
from folhas import TOTAL
from processos import (PROC, SOLDADOS, MATERIA_PRIMA, TRATAMENTOS,
                       LASER, SERRA, BARRA, TORNO, FRESA, COMPRA, PLAST)
from relatorio import Doc, cat

CEN = [('Protótipo', 1), ('Pré-série', 3), ('Pequena série', 15)]


def n(v, d=0):
    return M._n(v) if d == 0 else f'{v:.{d}f}'.replace('.', ',')


def _linhas_processo(lista, cols):
    out = []
    for i in lista:
        ops = ' · '.join(i['ops']) if i['ops'] else '—'
        base = dict(cod=i['codigo'], item=i['item'], nome=i['nome'], qtd=str(i['qtd']),
                    mat=i['material'], esp=i['esp'], dim=i['dim'], ops=ops, obs=i['obs'],
                    massa=n(i['massa'], 2), furos=str(i['furos']) if i['furos'] else '—',
                    folha=i['folha'])
        out.append([base[c] for c in cols])
    return out


# ============================================================ DOCUMENTO 2
def build():
    its = dados.itens()
    d = Doc('Pacote de Fabricação',
            'Listas por processo, matéria-prima, soldagem, acabamento e cenários de quantidade — '
            'para cotação por empresas de corte, dobra, usinagem e caldeiraria.',
            'VTX-RV4-PF-H', status='PARA COTAÇÃO — NÃO LIBERADO PARA FABRICAÇÃO')

    d.h1('Como usar este pacote')
    d.p('Este documento é a <b>lista de trabalho</b>. A geometria está no caderno de desenhos '
        f'<b>VTX-RV4-CG-H</b> ({TOTAL} folhas A3) e nos arquivos <b>DXF 1:1</b> que acompanham o envio. '
        'Cada peça abaixo aponta a folha onde está desenhada.')
    d.lista([
        '<b>Parte A</b> (folhas 01–16): chassi, suspensão pneumática e gaiola. É o que se cota primeiro.',
        '<b>Parte B</b> (folhas 17–22): mastros, interface modular de sensores VMS-60, bateria, eletrônica e '
        'sensores. Cotar em separado.',
        '<b>Parte C</b> (folhas 23–27): pendências, massa, encargos de FEA e plano de validação. '
        'Não entra no preço — é contexto de engenharia.',
        '<b>Parte D</b> (folhas 28–35): usinagem do grupo W e manual de montagem — é com elas que se cota a usinagem.',
        '<b>Parte E</b> (folhas 36–42): mastro, interface modular, módulos térmicos removíveis, antena e cabos. '
        'Os módulos térmicos e o adaptador de antena T-10 são <b>opcionais</b>: cotar à parte.',
    ])
    d.alerta('Status: <b>emitido para cotação</b>. A fabricação só começa após o parecer assinado do '
             'engenheiro mecânico (folha 15 do caderno) e o fechamento dos itens 1 a 10 da folha 23.')

    d.h2('Normas e tolerâncias gerais')
    d.tabela(['Assunto', 'Norma / critério', 'Origem'], [
        ['Tolerâncias de conjunto soldado', 'ISO 13920-BF', cat('CONFIRMADO')],
        ['Tolerâncias de corte e usinagem', 'ISO 2768-mK', cat('CONFIRMADO')],
        ['Qualidade da solda', 'ISO 5817 nível C (inspeção visual 100 %)', cat('CONFIRMADO')],
        ['Qualificação do soldador (alumínio)', 'AWS D1.2 ou ISO 9606-2', cat('CONFIRMADO')],
        ['Desenho técnico', 'ABNT NBR 10068 / 10067 / 8402 / 10126 / 12298', cat('CONFIRMADO')],
        ['Posição de furos a laser', '± 0,2 mm', cat('PROPOSTA')],
        ['Diagonais do quadro e dos centros de roda', 'Δ ≤ 2 mm', cat('PROPOSTA')],
        ['Planicidade da face de montagem do motor', '0,1 mm · Ra 3,2', cat('PROPOSTA')],
    ], [30, 52, 18])

    # ---------------------------------------------------------- A · laser
    d.quebra()
    laser = [i for i in its if i['processo'] == LASER]
    d.h1('Corte a laser / CNC')
    d.p(f'{len(laser)} códigos · {sum(i["qtd"] for i in laser)} peças. Todas as peças têm DXF 1:1 na pasta '
        '<b>04_CAD/DXF/</b>, com camadas CORTE, FUROS e GRAVAR-NAO (identificação da peça).')
    d.tabela(['Código', 'Peça', 'Folha', 'Qtd', 'Material', 'Esp.', 'Dimensões (mm)', 'Furos',
              'Operações seguintes'],
             _linhas_processo(laser, ['cod', 'nome', 'folha', 'qtd', 'mat', 'esp', 'dim', 'furos', 'ops']),
             [20, 17, 6, 5, 11, 6, 12, 5, 18], 'compacta')
    d.nota('“Furos” conta apenas os furos circulares do DXF; recortes poligonais (janelas, rasgos) estão no '
           'próprio arquivo. Espelhamentos: W-02, W-03, W-05, W-06, W-09, W-11, W-13 (2 E + 2 D), K-01, M-02, '
           'E-01, E-02, N-06 e N-08 usam a mesma peça virada.')

    # ---------------------------------------------------------- B · dobra
    d.h1('Dobra')
    dobra = dados.com_operacao('dobra')
    linhas = [[i['codigo'], i['nome'], i['folha'], str(i['qtd']), i['material'], i['esp'],
               '2 × 90°' if i['item'] == 'E-11' else '1 × 90°',
               'A DEFINIR PELO FABRICANTE', 'A DEFINIR PELO FABRICANTE'] for i in dobra]
    d.tabela(['Código', 'Peça', 'Folha', 'Qtd', 'Material', 'Esp.', 'Ângulo', 'Raio de dobra',
              'Comp. desenvolvido'], linhas, [20, 16, 6, 5, 11, 6, 8, 14, 14], 'compacta')
    d.p(f'Apenas {len(dobra)} códigos têm dobra. {cat("A DEFINIR")} O raio interno, o desenvolvimento e a '
        'sequência dependem da ferramenta do fabricante — informar na proposta, que o desenho é ajustado.')
    d.nota('As carenagens e tampas (K-01 a K-06) são <b>chapas planas aparafusadas</b>, sem dobra: foi uma '
           'escolha de projeto para simplificar a fabricação e permitir desmontagem.')

    # ------------------------------------------------------- C · usinagem
    d.h1('Usinagem')
    usin = [i for i in its if i['processo'] in (TORNO, FRESA, PLAST)] + \
           [i for i in its if any('usinagem' in o.lower() or 'fresamento' in o.lower() for o in i['ops'])]
    vistos, lista = set(), []
    for i in usin:
        if i['item'] not in vistos:
            vistos.add(i['item'])
            lista.append(i)
    linhas = []
    for i in lista:
        tol = {'W-02': 'Ø88 H8 · planicidade 0,1 · Ra 3,2 na face de montagem (folha 29)',
               'W-04': 'Alojamento Ø23 H7 alargado depois da solda (folha 28)',
               'W-07': 'Ø20 h7 · Ra 0,8 · 2 ranhuras DIN 471',
               'T-02': 'Pinos Ø8/Ø6 H7 a 26 ± 0,02 · 4 × M5 roscados (folha 37)',
               'T-03': 'Pinos Ø8/Ø6 H7 · furação do sensor A VALIDAR (P-06)',
               'T-04': 'Pinos Ø8/Ø6 H7 · SEM furação de sensor (P-30)',
               'T-10': 'Ø26 g6 · Ø10 passante · rosca da antena A VALIDAR (P-37)',
               'N-02': 'Face plana, alinhada a X/Y em 0,5°',
               'Q-05': 'Furo Ø8,5 H12 · comprimento 30 ± 0,2',
               'N-03': 'Furo Ø6,6 · comprimento 54 ± 0,2',
               'M-12': 'A DEFINIR PELO ENGENHEIRO',
               'N-04': 'Bordas polidas, sem trinca'}.get(i['item'], 'A DEFINIR PELO ENGENHEIRO')
        linhas.append([i['codigo'], i['nome'], i['folha'], str(i['qtd']), i['material'], i['dim'],
                       i['processo'], tol])
    d.tabela(['Código', 'Peça', 'Folha', 'Qtd', 'Material', 'Dimensões (mm)', 'Processo',
              'Tolerância / acabamento'], linhas, [19, 16, 6, 5, 11, 11, 13, 19], 'compacta')
    d.alerta('<b>W-02 é a peça crítica do conjunto</b>: a face de montagem do motor-roda é usinada depois da '
             'solda, e o paralelismo entre as quatro faces define o alinhamento das rodas. Em aço A36, porque '
             'a peça cicla com o terreno. A furação de interface (Ø88 H8 + 7 × Ø4,5 no PCD 95) precisa ser '
             'confirmada com a ElectroCraft antes do corte (P-04).')

    # ------------------------------------------------------ D · soldagem
    d.quebra()
    d.h1('Soldagem')
    d.p('<b>Alumínio:</b> TIG (GTAW) com arame ER5356 (ER4043 se a peça for pintada). Filete contínuo. '
        'Soldador qualificado para alumínio (AWS D1.2 / ISO 9606-2). <b>Aço (grupo W):</b> MIG/MAG ou TIG com '
        'ER70S-6 — outro procedimento e outro consumível; qualificação do soldador para aço a confirmar '
        f'{cat("A DEFINIR")}. Inspeção visual 100 % conforme ISO 5817 nível C nos dois.')
    for cod, nome, itens_s, proc, obs in SOLDADOS:
        d.h3(f'{cod} · {nome}')
        linhas = []
        for it in itens_s:
            i = next((x for x in its if x['item'] == it), None)
            if i:
                linhas.append([i['item'], i['nome'], str(i['qtd']), i['material'], i['esp']])
        d.tabela(['Item', 'Peça', 'Qtd', 'Material', 'Seção / esp.'], linhas, [10, 34, 8, 24, 24], 'compacta')
        d.p(f'<b>Processo:</b> {proc}<br><b>Observação:</b> {obs}')
    d.p(f'Comprimento total de cordão: {cat("A DEFINIR")} — depende da sequência adotada pelo fabricante. '
        'O caderno indica a garganta (a2, a3, a4) em cada junta; a extensão é medida no gabarito.')

    # -------------------------------------------------- E · tubos/perfis
    d.h1('Tubos, barras e perfis — lista de corte')
    tub = [i for i in its if i['processo'] in (SERRA, BARRA)]
    linhas = []
    for i in tub:
        cortes = ' · '.join(f'{n(c)} × {q}' for c, q in i['comps'])
        linhas.append([i['codigo'], i['nome'], i['folha'], i['desc'], i['material'], cortes,
                       str(i['qtd']), n(i['massa'], 2)])
    d.tabela(['Código', 'Peça', 'Folha', 'Perfil', 'Material', 'Cortes (mm × qtd)', 'Qtd', 'kg'],
             linhas, [19, 15, 6, 16, 11, 19, 6, 8], 'compacta')
    d.h2('Consumo por perfil')
    d.tabela(['Perfil', 'Comprimento total (m)', 'Barras de 6 m', 'Observação'],
             [[k, f'<span class="num">{n(v, 2)}</span>', f'<span class="num">{int(v // 6) + 1}</span>',
               'Serra de 3 mm considerada no plano de corte (folhas 06 e 12)']
              for k, v in sorted(dados.tubos().items())], [34, 18, 14, 34])

    # ---------------------------------------------------- F · matéria-prima
    d.h1('Matéria-prima a adquirir')
    d.tabela(['Material', 'Liga / especificação', 'Norma', 'Quantidade (1 conjunto)', 'Origem'],
             [[a, b, c, e, cat(f)] for a, b, c, e, f in MATERIA_PRIMA], [26, 18, 14, 26, 16], 'compacta')
    d.h2('Área bruta de chapa')
    d.tabela(['Material', 'Espessura (mm)', 'Área bruta (m²)'],
             [[k[0], f'<span class="num">{k[1]}</span>', f'<span class="num">{n(v, 3)}</span>']
              for k, v in sorted(dados.area_chapa().items())], [40, 25, 35], 'compacta')
    d.nota('Área do retângulo envolvente de cada peça, sem aninhamento. O aproveitamento real depende do '
           'nesting do fornecedor — se ele informar o aproveitamento, o custo de material cai.')

    # -------------------------------------------------------- G · acabamento
    d.h1('Acabamento — cotar as quatro opções')
    d.tabela(['Opção', 'Tratamento', 'Cuidado na execução', 'Uso'],
             [[a, b, c, e] for a, b, c, e in TRATAMENTOS], [8, 34, 38, 20])
    d.p('Quebrar cantos vivos ≥ 0,5 mm em todas as peças; cantos externos de carenagens e tampas com R3. '
        'Mascarar faces de montagem, roscas, os alojamentos de pino e a face usinada da W-02. O grupo W é de '
        'aço: zincado ou pintado, e isolado do alumínio (folha 30).')

    # ----------------------------------------------------------- H · fluxo
    d.h1('Fluxo de fabricação')
    d.fluxo(['Recebimento e conferência de material (certificados)',
             'Corte a laser / CNC das chapas', 'Corte de tubos e perfis (serra)',
             'Dobra (E-11, N-06)', 'Usinagem prévia (Q-05, N-03, M-12)',
             'Soldagem em gabarito (quadro, suportes, módulos da gaiola)',
             'Usinagem do grupo W (folhas 28 a 31): alojamento da bucha e face da W-02 DEPOIS da solda',
             'Usinagem pós-solda (berço N-02) e furação com gabarito (sapatas G-05, travas M-01)',
             'Tratamento de superfície (opção A, B ou C)',
             'Instalação de porcas-rebite', 'Inspeção dimensional das cotas críticas',
             'Montagem, identificação e embalagem'])
    d.nota('As porcas-rebite são instaladas <b>depois</b> do tratamento de superfície. A furação das sapatas '
           'e das travas do mastro é feita depois da solda, com gabarito tirado do próprio quadro.')

    # -------------------------------------------------------- I · inspeção
    d.h1('Inspeção e entrega')
    d.tabela(['Característica', 'Valor', 'Método'], [
        ['Entre-eixos (centros Ø88, mesmo lado)', '700 ± 1', 'Paquímetro / traçador'],
        [f'Faces de montagem E–D (bitola {M._n(M.BITOLA)})', f'{M._n(2 * M.Y_FACE)} ± 1', 'Paquímetro'],
        ['Coaxialidade dos furos Ø20 H7 das orelhas do pivô', '0,05', 'Mandril calibrado'],
        ['Alojamento Ø23 H7 da bucha, depois da solda', 'H7 · coaxial em 0,2', 'Calibre passa/não passa'],
        ['Estanqueidade do colar W-12 + W-13', '0,5 bar, sem bolha em 60 s', 'Ensaio em água'],
        ['Cota entre os pinos do prato T-02', '26 ± 0,02', 'Máquina de medir ou relógio'],
        ['Centro Ø88 abaixo do quadro', '150 ± 0,5', 'Altímetro'],
        ['Diagonais dos 4 centros de roda', 'Δ ≤ 2', 'Trena / laser'],
        ['Diagonais do quadro', 'Δ ≤ 2', 'Trena'],
        ['Planicidade do anel superior', '1,5', 'Régua / relógio'],
        ['Planicidade da face de montagem', '0,1', 'Relógio comparador'],
        ['Coplanaridade das sapatas da gaiola', '≤ 0,5', 'Mesa plana'],
        ['Rugosidade da face de montagem', 'Ra 3,2', 'Rugosímetro ou padrão de comparação'],
    ], [42, 20, 38], 'compacta')
    d.p('Entregar: relatório dimensional das características acima, fotos das soldas, certificados de '
        'material e peças identificadas pelo código.')

    # ------------------------------------------------------- J · cenários
    d.quebra()
    d.h1('Cenários de quantidade')
    pm, pg = dados.resumo_material()
    massa = sum(pm.values())
    linhas = []
    for nome, q in CEN:
        linhas.append([f'<b>{nome}</b>', f'<span class="num">{q}</span>',
                       f'<span class="num">{sum(i["qtd"] for i in its) * q}</span>',
                       f'<span class="num">{n(massa * q, 1)}</span>',
                       f'<span class="num">{n(sum(dados.tubos().values()) * q, 1)}</span>',
                       f'<span class="num">{n(sum(dados.area_chapa().values()) * q, 2)}</span>'])
    d.tabela(['Cenário', 'Conjuntos', 'Peças fabricadas', 'Massa de peça pronta (kg)',
              'Tubo e perfil (m)', 'Chapa bruta (m²)'], linhas, [20, 12, 17, 19, 16, 16])
    d.p('Para cada cenário, cotar separadamente: <b>material</b>, <b>corte</b>, <b>dobra</b>, '
        '<b>usinagem</b>, <b>soldagem</b>, <b>acabamento</b>, <b>montagem</b>, <b>frete</b> e '
        '<b>ferramental/gabarito</b> (custo único, se houver).')
    linhas = []
    for grupo in ('Material', 'Corte laser/CNC', 'Dobra', 'Usinagem', 'Soldagem', 'Acabamento',
                  'Montagem e inspeção', 'Gabaritos (custo único)', 'Frete até Pouso Alegre/MG'):
        linhas.append([grupo] + ['<span class="vazio">COTAÇÃO NECESSÁRIA</span>'] * 3)
    d.tabela(['Rubrica', 'Protótipo (1)', 'Pré-série (3)', 'Pequena série (15)'], linhas, [28, 24, 24, 24])
    mc = dados.metricas_corte()
    d.alerta('Os preços de <b>componentes</b> vieram da BOM de compras recebida em 21/09/2026 '
             '(pasta 10_CUSTOS) e são <b>os do V3</b>: itens que mudaram no V4 estão marcados A COTAR. Os preços de '
             '<b>fabricação</b> — corte, dobra, usinagem, solda, acabamento e montagem — continuam sem cotação: '
             'é o que esta tabela pede. Quantidades de referência, calculadas do modelo: '
             f'{n(mc["corte_m"], 1)} m de corte a laser em {mc["n_furos"]:.0f} furos e '
             f'{n(mc["area_m2"], 2)} m² de superfície das peças planas. O cordão de solda depende da sequência '
             'do fabricante e não foi estimado.')

    # ------------------------------------------------------- K · o que enviar
    d.h1('O que acompanha esta solicitação')
    d.tabela(['Arquivo', 'Conteúdo'], [
        ['VTX-RV4-CG-H-A.pdf', 'Caderno Parte A — chassi, suspensão e gaiola (16 folhas A3)'],
        ['VTX-RV4-CG-H-B.pdf', 'Caderno Parte B — mastro, sensores, bateria e eletrônica (6 folhas A3)'],
        ['VTX-RV4-CG-H-D.pdf', 'Caderno Parte D — usinagem do grupo W e montagem (8 folhas A3)'],
        ['VTX-RV4-CG-H-E.pdf', 'Caderno Parte E — mastro, VMS-60, térmicas, antena e cabos (7 folhas A3)'],
        ['VTX-RV4-CG-H.pdf', f'Caderno completo ({TOTAL} folhas A3), inclusive contexto de engenharia'],
        ['04_CAD/DXF/', 'DXF 1:1 das peças planas, em mm, com a lista no LEIA-ME.txt da pasta'],
        ['04_CAD/STL/', 'Malhas 3D do conjunto e das peças, para visualização e conferência'],
        ['05_BOM/', 'Lista de materiais mecânica completa (CSV/XLSX)'],
        ['Este documento', 'Listas por processo, matéria-prima, inspeção e cenários'],
    ], [30, 70])
    return d


# ============================================================ DOCUMENTO 7
def rfq():
    d = Doc('Solicitação de Orçamento (RFQ)',
            'Formulário de proposta — fabricação do chassi, gaiola e interfaces do VALTEXA ROVER V4.',
            'VTX-RV4-RFQ-H', status='SOLICITAÇÃO DE PROPOSTA')

    d.h1('Identificação')
    d.tabela(['Campo', 'Conteúdo'], [
        ['Solicitante', 'ValTexa — Rover V4'],
        ['Cidade', 'Pouso Alegre / MG'],
        ['Contato ValTexa', '<span class="vazio">&nbsp;</span>'],
        ['Fornecedor', '<span class="vazio">&nbsp;</span>'],
        ['Contato do fornecedor', '<span class="vazio">&nbsp;</span>'],
        ['Data de envio', '<span class="vazio">&nbsp;</span>'],
        ['Responder até', '<span class="vazio">&nbsp;</span>'],
    ], [28, 72])

    d.h1('Objeto')
    d.p('Fabricação do <b>chassi estrutural, gaiola de proteção e interfaces</b> do rover agrícola '
        f'VALTEXA ROVER V4, conforme o caderno de desenhos <b>VTX-RV4-CG-H</b> ({TOTAL} folhas A3), os arquivos '
        'DXF 1:1 e o pacote de fabricação <b>VTX-RV4-PF-H</b>.')
    d.tabela(['#', 'Escopo', 'Qtd', 'Preço unit. (R$)', 'Preço total (R$)', 'Prazo (dias)'], [
        ['1', 'Parte A — chassi, suspensão pneumática (grupo W, em aço) e gaiola (folhas 01–16 e 28–31)',
         '1 conjunto', '', '', ''],
        ['2', 'Parte B — mastros, interface VMS-60, bandejas e interfaces (folhas 17–22 e 36–38)', '1 jogo',
         '', '', ''],
        ['3', 'OPCIONAL — 4 postos térmicos removíveis e 2 adaptadores de antena T-10 (folhas 37 e 41)', '1 jogo',
         '', '', ''],
        ['4', 'Acabamento A — natural', '1', '', '', ''],
        ['5', 'Acabamento B — anodização preta ≥ 15 µm (peças de alumínio)', '1', '', '', ''],
        ['6', 'Acabamento C — pintura eletrostática; D — zincagem (só aço)', '1', '', '', ''],
        ['7', 'Gabaritos de soldagem (custo único)', '1', '', '', ''],
        ['8', 'Relatório dimensional e certificados de material', '1', '', '', ''],
        ['9', 'Embalagem e frete até Pouso Alegre/MG', '1', '', '', ''],
        '<tr class="total"><td colspan="3">Total — 1 conjunto (protótipo)</td><td></td><td></td><td></td></tr>',
        '<tr class="total"><td colspan="3">Preço unitário para 3 conjuntos</td><td></td><td></td><td></td></tr>',
        '<tr class="total"><td colspan="3">Preço unitário para 15 conjuntos</td><td></td><td></td><td></td></tr>',
    ], [5, 43, 12, 14, 14, 12])

    d.h1('Informações que a proposta deve trazer')
    d.lista([
        'Preço unitário e do lote, para 1, 3 e 15 conjuntos.',
        'Prazo de entrega contado a partir do pedido.',
        'Material efetivamente utilizado (liga e norma) e origem do certificado.',
        'Processos executados internamente e o que é subcontratado.',
        'Acabamento: quem executa e onde.',
        'Tolerâncias que a empresa consegue garantir (em especial a face usinada, Ra 3,2 e planicidade 0,1).',
        'Qualificação do soldador para alumínio (AWS D1.2 / ISO 9606-2) e para aço, no grupo W.',
        'Capacidade mensal e quantidade mínima de pedido.',
        'Frete, impostos, condições de pagamento e validade da proposta.',
        'Desvios de projeto que reduzam custo — <b>sempre com preço comparativo</b>.',
    ], ordenada=True)

    d.h1('Condições')
    d.lista([
        'Não alterar geometria, material ou espessura sem consulta prévia por escrito.',
        'Dúvida de interpretação de desenho: perguntar antes de cortar.',
        'Peças identificadas pelo código (ex.: VTX-RV4-QUADRO-Q-01-REV-H).',
        'A ValTexa fornece os arquivos DXF; o fornecedor confirma que consegue abri-los e usá-los.',
        'Este pacote está <b>emitido para cotação</b> — a ordem de fabricação depende de validação '
        'estrutural por engenheiro mecânico.',
    ])

    d.h1('Preenchimento pelo fornecedor')
    d.campos([('Razão social', ''), ('CNPJ', ''), ('Cidade / UF', ''), ('Responsável técnico', ''),
              ('Telefone', ''), ('E-mail', ''), ('Validade da proposta', ''),
              ('Prazo de entrega (protótipo)', ''), ('Condições de pagamento', '')])
    d.assinatura(['Pelo fornecedor', 'Pela ValTexa'])
    return d
