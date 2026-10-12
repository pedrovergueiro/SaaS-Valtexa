"""DOCUMENTOS 5, 6 e 8 — pendências de engenharia, auditoria do pacote e conceito das bases."""
import dados
import modelo as M
from relatorio import Doc, cat


def n(v, d=0):
    return M._n(v) if d == 0 else f'{v:.{d}f}'.replace('.', ',')


# ============================================================ PENDÊNCIAS
PEND = [
    # (#, tema, o que falta, quem fecha, critério de aceite, bloqueia)
    ('Estrutura', 'Validação estrutural do conjunto', 'FEA dos 8 casos de carga da folha 25, com fadiga',
     'Engenheiro mecânico', 'Relatório com margem por caso', 'Fabricação'),
    ('Estrutura', 'Condição de cálculo da solda 6061-T6', 'Decidir: como soldado (110 MPa na ZTA) ou novo T6',
     'Engenheiro mecânico', 'Folha 25 assinada', 'Fabricação'),
    ('Estrutura', 'Diagonais do quadro', 'Decidir se entram; 3 opções com custo de massa na folha 25',
     'Engenheiro mecânico', 'Decisão + FEA de torção', 'Fabricação'),
    ('Estrutura', 'Suspensão', 'Protótipo rígido ou curso de 40 mm (refaz S-01…S-03)',
     'Engenheiro mecânico', 'Decisão registrada na revisão', 'Fabricação'),
    ('Estrutura', 'Massa oficial', 'Resolver 85,04 × 82,49 kg e adotar um único número',
     'Engenharia + gestão', 'Baseline Rev F', 'Publicação'),
    ('Estrutura', 'Envelope de estabilidade', 'Refazer com o CG consolidado; 16,2° não reproduz',
     'Engenheiro mecânico', 'Valor único na Rev F', 'Publicação'),
    ('Estrutura', 'Vão livre oficial', 'Definir onde é medido (208 entre rodas × 38 na linha das rodas)',
     'Engenheiro mecânico', 'Valor único na Rev F', 'Publicação'),
    ('Estrutura', 'Largura oficial', 'Aceitar 674 mm com carenagens ou reduzir a N-09',
     'Engenharia + gestão', 'Valor único na Rev F', 'Publicação'),
    ('Interface', 'Escolha do motor-roda', 'Decidir entre MPW86 (R$ 6.425/un) e ZLTECH '
     '(R$ 1.133,68/un): economia de R$ 21.165, mas +16 kg e interface diferente',
     'Engenharia + gestão', 'Decisão registrada + folha 27', 'Desenho do suporte S'),
    ('Interface', 'Interface do motor escolhido', 'MPW86: orientação dos 7 furos e folga face–roda. '
     'ZLTECH: diâmetro, comprimento e rosca do eixo, largura da roda, massa com freio',
     'Compras / fabricante', 'Desenho dimensional 2D/3D', 'Corte da S-02'),
    ('Interface', 'Freio mecânico', 'No ZLTECH o freio EMB é opcional e não foi pedido na BOM de compras',
     'Compras', 'Cotação com "freio eletromagnético" explícito', 'Operação em rampa'),
    ('Interface', 'Torque de retenção do freio', 'Valor não publicado no catálogo',
     'Compras / ElectroCraft', 'Resposta formal (RFQ)', 'Operação em rampa'),
    ('Interface', 'Caixa da bateria', 'Dimensões e furação reais das 16 células EVE LF100LA',
     'Engenharia elétrica', 'Desenho da caixa', 'Posição dos batentes'),
    ('Interface', 'Furação das câmeras', 'Padrão de furos da OAK-D Pro W PoE e do conector',
     'Integração de sensores', 'Desenho do fabricante', 'DXF da M-20'),
    ('Interface', 'Antena GNSS', 'Modelo, furação, centro de fase e sombra no LiDAR',
     'Integração de sensores', 'Datasheet + ensaio 1', 'DXF da N-01'),
    ('Interface', 'IMU', 'Furação real do MTi-630 e offset ao CG no software',
     'Integração de sensores', 'Desenho do fabricante', 'DXF da N-02'),
    ('Interface', 'Faróis', 'Modelo, potência e corrente (a baseline só dá a massa)',
     'Engenharia elétrica', 'Componente escolhido', 'Furo Ø20 da K-02'),
    ('Interface', 'Arranjo da eletrônica', 'Posição de drives, BMS, DC/DC, Jetson, disjuntor e conectores',
     'Engenharia eletrônica', 'Layout aprovado sobre a folha 21', 'Furação das bandejas'),
    ('Fabricação', 'Raio e desenvolvimento de dobra', 'E-11 e N-06 dependem da ferramenta do fabricante',
     'Fabricante + engenharia', 'Proposta com raio informado', 'Corte dessas 2 peças'),
    ('Fabricação', 'Processo da carenagem N-09', 'Fresagem de bloco, dobra a quente ou termoformagem',
     'Fabricante + engenharia', 'Processo definido com amostra', 'Fabricação da N-09'),
    ('Fabricação', 'Fixação das barras N-05', 'Aparafusadas ou soldadas sob a chapa de fundo',
     'Engenheiro mecânico', 'Detalhe na revisão 1', 'Fabricação da N-05'),
    ('Fabricação', 'Tolerâncias funcionais não declaradas', 'Ajustes de furos, folgas de montagem',
     'Engenheiro mecânico', 'Tabela de tolerâncias na revisão 1', 'Inspeção'),
    ('Comercial', 'BOM de compras em .docx', 'O .xlsx foi recebido; as duas versões .docx seguem ausentes',
     'ValTexa', 'Arquivos entregues ou declarados obsoletos', 'Conferência cruzada'),
    ('Comercial', 'Preços de fabricação', 'Nenhuma cotação de serviço: corte, dobra, usinagem, solda, '
     'acabamento e montagem',
     'Compras', '3 propostas por metro de corte e de cordão', 'Decisão de compra'),
    ('Campo', 'Aderência do solo (μ)', 'Nenhuma medição no talhão da ValTexa',
     'Engenharia + campo', 'Ensaio 5 da folha 26', 'Operação autônoma'),
    ('Campo', 'Altura de obstáculos na rua', 'Raízes, pedras e sulcos não levantados',
     'Engenharia + campo', 'Levantamento em fazenda-piloto', 'Definição de roda/vão'),
    ('Campo', 'Campo de visão do LiDAR e das câmeras', 'Confirmar ausência de obstrução',
     'Integração de sensores', 'Ensaios 1 a 3 da folha 26', 'Liberação de operação'),
    ('Bases', 'Base de recarga e poste', 'Nenhuma dimensão oficial na Rev E',
     'Engenharia + produto', 'Requisitos aprovados (ver conceito)', 'Projeto das bases'),
]


def pendencias():
    d = Doc('Pendências de Engenharia',
            'Tudo que ainda precisa de definição, com responsável, critério de aceite e o que cada item '
            'bloqueia.', 'VTX-RV3-PEND-E', status='CONTROLE DE PENDÊNCIAS')
    d.h1('Resumo')
    por_tema = {}
    for p in PEND:
        por_tema[p[0]] = por_tema.get(p[0], 0) + 1
    d.tabela(['Tema', 'Pendências', 'Natureza'],
             [[k, f'<span class="num">{v}</span>',
               {'Estrutura': 'Cálculo e decisão de projeto',
                'Interface': 'Depende de datasheet de terceiro',
                'Fabricação': 'Depende do fabricante escolhido',
                'Comercial': 'Depende de cotação',
                'Campo': 'Depende de ensaio',
                'Bases': 'Escopo ainda não iniciado'}[k]] for k, v in por_tema.items()], [24, 16, 60])
    d.p(f'Total: <b>{len(PEND)} pendências</b>. Nenhuma delas impede a <b>cotação</b> da Parte A — todas '
        'impedem, em graus diferentes, a <b>liberação para fabricação</b> ou a publicação de números '
        'definitivos.')

    d.h1('Lista completa')
    d.tabela(['Tema', 'Pendência', 'O que falta', 'Quem fecha', 'Critério de aceite', 'Bloqueia'],
             [[p[0], p[1], p[2], p[3], p[4], p[5]] for p in PEND],
             [10, 17, 27, 15, 17, 14], 'compacta')

    d.h1('Sequência recomendada')
    d.fluxo(['Enviar RFQ da Parte A (não depende de nenhuma pendência)',
             'Fechar datasheets: MPW86, OAK-D, antena GNSS, IMU, caixa da bateria',
             'Rodar o FEA com os 8 casos de carga',
             'Decidir solda, diagonais e suspensão',
             'Emitir revisão 1 do caderno com as decisões',
             'Ensaios de campo (μ, obstáculos, freio)',
             'Publicar baseline Rev F com números únicos',
             'Liberar fabricação'])
    return d


# ============================================================= AUDITORIA
def auditoria(res):
    d = Doc('Auditoria do Pacote de Fabricação',
            'Conferência de coerência entre modelo, desenhos, DXF, BOM e documentos — antes do envio.',
            'VTX-RV3-AUD-E', status='RELATÓRIO DE AUDITORIA')

    d.h1('Verificações automáticas')
    d.p('Rodadas sobre o modelo paramétrico e os arquivos gerados, a cada emissão do pacote.')
    d.tabela(['#', 'Verificação', 'Resultado', 'Situação'],
             [[str(i + 1), v[0], v[1], v[2]] for i, v in enumerate(res['auto'])], [5, 42, 33, 20])

    d.h1('Cobertura: cada peça tem desenho e arquivo?')
    d.tabela(['Situação', 'Códigos', 'Observação'], res['cobertura'], [22, 48, 30], 'compacta')

    d.h1('Itens que dependem de terceiros')
    d.tabela(['Categoria', 'Quantos', 'Consequência'], [
        ['Aprovados para cotação', f'<span class="num">{res["aprovados"]}</span>',
         'Geometria fechada, material e espessura definidos'],
        ['Incompletos (falta dado de fabricante)', f'<span class="num">{res["incompletos"]}</span>',
         'Cotáveis, mas o desenho pode mudar depois do datasheet'],
        ['Conflitantes entre documentos', f'<span class="num">{res["conflitos"]}</span>',
         'Registrados na seção de divergências do documento técnico'],
        ['Dependem do engenheiro mecânico', f'<span class="num">{res["engenheiro"]}</span>',
         'FEA, solda, diagonais, suspensão, tolerâncias'],
        ['Dependem de cotação', f'<span class="num">{res["cotacao"]}</span>',
         'Todo valor monetário do pacote'],
    ], [38, 12, 50])

    d.h1('O que este pacote não contém')
    d.lista([
        '<b>Validação estrutural</b>: não há FEA, fadiga nem ensaio. As verificações da folha 15 são de '
        'dimensionamento, não de liberação.',
        '<b>Preços</b>: nenhum valor monetário foi estimado.',
        '<b>Projeto elétrico e eletrônico</b>: o pacote define espaço, entradas de cabo e pontos de '
        'fixação, não o arranjo dos componentes.',
        '<b>Bases de recarga e postes</b>: não existem na Rev E. O que há é um <b>conceito</b> separado, '
        'para iniciar a discussão de requisitos.',
        '<b>Modelo CAD paramétrico</b>: o modelo é geométrico (Python), exportado em DXF 2D e malha 3D. '
        'Um CAD nativo (SolidWorks/Fusion/Onshape) ainda precisa ser criado pelo engenheiro.',
    ])

    d.h1('Recomendação de envio')
    d.tabela(['Destinatário', 'O que enviar', 'O que pedir'], [
        ['Engenheiro mecânico', 'Caderno completo (27 folhas) + este pacote',
         'Parecer da folha 15, FEA dos 8 casos e decisão sobre solda/diagonais/suspensão'],
        ['Corte a laser / CNC', 'Parte A + DXF + listas de corte', 'Preço e prazo para 1, 3 e 15 conjuntos'],
        ['Dobra', 'Desenhos da E-11 e N-06', 'Raio, desenvolvimento e preço'],
        ['Usinagem', 'Folhas 07, 22 + DXF da S-02 e N-02', 'Preço da face usinada e das peças de torno'],
        ['Caldeiraria / solda', 'Folhas 04, 06, 07, 09, 12 + lista de conjuntos soldados',
         'Preço com gabarito e qualificação do soldador'],
        ['Fornecedor de material', 'Lista de matéria-prima', 'Preço, prazo e certificado'],
    ], [20, 38, 42], 'compacta')
    return d


# ====================================================== CONCEITO DAS BASES
def conceito_bases():
    d = Doc('Base de Recarga e Poste — Conceito',
            'Proposta inicial de requisitos e arquitetura mecânica. Nenhuma dimensão aqui pertence à '
            'baseline Rev E.', 'VTX-RV3-BASE-E-CONCEITO', status='CONCEITO PARA VALIDAÇÃO DE ENGENHARIA')

    d.alerta('<b>Atenção:</b> a baseline Rev E <b>não define</b> base de recarga nem poste — não há uma '
             'única dimensão oficial sobre esses itens. Tudo neste documento é '
             f'{cat("PROPOSTA")} e existe para iniciar a discussão de requisitos. Não enviar para '
             'fabricação.')

    d.h1('O que a Rev E fornece como ponto de partida')
    d.tabela(['Dado', 'Valor', 'Origem'], [
        ['Envelope do rover (corpo)', f'{n(M.L_EXT)} × {n(M.W_EXT)} × {n(M.Z_PROT)} mm', cat('CONFIRMADO')],
        ['Largura com carenagens das câmeras', '674 mm', cat('DERIVADO')],
        ['Altura total com mastros', f'{n(M.Z_TOTAL)} mm (1.822 com a ponta)', cat('CONFIRMADO')],
        ['Massa máxima', f'{n(M.consolidado()["m_max"], 1)} kg', cat('DERIVADO')],
        ['Bateria', 'LiFePO4 48 V · 100 Ah · 5.120 Wh', cat('CONFIRMADO')],
        ['Tempo de recarga estimado', '≈ 1,8 h com carregador de 2,5 kW', cat('CONFIRMADO')],
        ['Vão livre / diâmetro da roda', '208 mm / 200 mm', cat('DERIVADO')],
        ['Fontes de energia do rover', 'Somente bateria — sem painel solar embarcado', cat('CONFIRMADO')],
    ], [34, 40, 26])

    d.h1('Requisitos que precisam ser decididos antes de desenhar')
    d.tabela(['#', 'Decisão', 'Opções', 'Impacto'], [
        ['1', 'Tipo de acoplamento de recarga', 'Conector manual · contatos deslizantes · indutivo',
         'Define toda a geometria da interface e a precisão de docking exigida'],
        ['2', 'Precisão de aproximação do rover', 'RTK + fiducial · guia mecânica em V · batente',
         'Guia mecânica reduz exigência de software, mas exige estrutura'],
        ['3', 'Abrigo', 'Aberto · cobertura simples · fechado com porta',
         'Custo, proteção contra chuva/sol e ventilação do carregador'],
        ['4', 'Energia da base', 'Rede 220 V · solar + banco · híbrido',
         'A baseline descartou solar no rover; na base é uma decisão nova'],
        ['5', 'Fixação no solo', 'Sapata de concreto · estacas · patolas ajustáveis',
         'Terreno de lavoura é irregular e tem declive'],
        ['6', 'Número de rovers por base', '1 · 2 · N',
         'Define área, potência instalada e lógica de fila'],
        ['7', 'Poste: finalidade', 'Antena base RTK · rede/comunicação · iluminação · câmera de vigia',
         'A finalidade define altura, seção e fundação'],
        ['8', 'Mobilidade', 'Fixa · rebocável · contêiner',
         'Base rebocável muda completamente a estrutura'],
    ], [5, 24, 33, 38], 'compacta')

    d.h1('Conceito A — base de recarga (proposta para discussão)')
    d.p('Premissa: <b>uma vaga</b>, rover entrando de frente, conector manual no protótipo e evolução para '
        f'contato automático. {cat("PROPOSTA")}')
    d.tabela(['Elemento', 'Proposta', 'Justificativa'], [
        ['Área útil da vaga', '1.400 × 1.000 mm', 'Envelope 1.050 × 674 + 175 mm de folga por lado'],
        ['Piso', 'Plataforma plana nivelada, com rampa de entrada ≤ 10°',
         'Vão livre de 208 mm e roda de 200 mm; rampa suave evita raspar o suporte S-02'],
        ['Guia de alinhamento', 'Duas guias em V convergentes, altura 150 mm',
         'Corrige ±60 mm de erro lateral sem depender só do RTK'],
        ['Batente de fim de curso', 'Barra transversal com amortecedor, altura 120 mm',
         'Para na posição de recarga sem tocar a carenagem frontal'],
        ['Altura livre do abrigo', '≥ 2.100 mm', 'O rover tem 1.822 mm com a ponta do mastro'],
        ['Estrutura', 'Perfil de aço galvanizado ou alumínio estrutural',
         'A definir conforme custo e exposição ao tempo'],
        ['Carregador', 'Gabinete IP54 ventilado, 2,5 kW', 'Tempo de recarga da baseline'],
        ['Fixação', '4 sapatas ajustáveis + ancoragem química', 'Terreno irregular e com declive'],
    ], [22, 30, 48])
    d.nota('Nenhuma dessas medidas foi verificada contra manobra real do rover, raio de giro ou precisão de '
           'posicionamento — são pontos de partida para o engenheiro dimensionar.')

    d.h1('Conceito B — poste (proposta para discussão)')
    d.p('Premissa: poste para <b>antena base RTK</b> e rádio, que é a função de poste que a arquitetura da '
        f'baseline realmente exige (GNSS RTK com base própria). {cat("PROPOSTA")}')
    d.tabela(['Elemento', 'Proposta', 'Justificativa'], [
        ['Altura livre da antena', '4.000 mm acima do solo',
         'Acima da copa de projeto (2.400 mm) para horizonte limpo'],
        ['Seção', 'Tubo de aço galvanizado Ø88,9 × 3,0 mm ou treliça leve',
         'A definir por cálculo de vento — não feito'],
        ['Fundação', 'Bloco de concreto com chumbadores, ou base parafusada',
         'Depende do solo e do regime de vento da região'],
        ['Passagem de cabos', 'Interno, com caixa de passagem IP65 na base',
         'Protege cabo de antena e alimentação'],
        ['Aterramento e SPDA', 'A DEFINIR POR PROFISSIONAL HABILITADO',
         'Estrutura metálica alta em área aberta exige projeto específico'],
        ['Interface com equipamentos', 'Suporte de antena + caixa de rádio + painel solar opcional',
         'Mesma família de suportes usada no rover'],
    ], [22, 30, 48])
    d.alerta('Cálculo de vento, fundação, aterramento e SPDA <b>não foram feitos</b> e exigem profissional '
             'habilitado com ART. Este conceito não substitui projeto estrutural de poste.')

    d.h1('Próximo passo')
    d.lista([
        'Responder às 8 decisões da tabela de requisitos.',
        'Com as respostas, produzir um caderno específico (VTX-RV3-BASE-E) no mesmo padrão do rover.',
        'Só então cotar estrutura, abrigo, carregador e fundação.',
    ], ordenada=True)
    return d
