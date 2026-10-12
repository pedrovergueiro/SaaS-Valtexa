"""DOCUMENTO 6 — Pesquisa de fornecedores · Pouso Alegre e região.

Todo dado desta lista veio de página pública ou de busca na web, em 21/09/2026, e está marcado como
PESQUISA: precisa ser confirmado com a empresa antes de qualquer pedido. Nada foi inventado —
campo sem informação pública aparece como 'não publicado'.
"""
from relatorio import Doc, cat

NP = '<i>não publicado</i>'

# (empresa, cidade/UF, serviços, o que pode fabricar do Rover, atende Pouso Alegre?, site, contato, fonte)
FAB = [
    ('AGMATEC', 'Ribeirão Preto / SP',
     'Corte a laser de chapa e de tubo, corte e dobra, caldeiraria, rebarbação, pintura eletrostática',
     'Todas as peças planas (chapa até 16 mm em alumínio), corte de tubos, dobra da E-11/N-06 e pintura',
     'Sim — a empresa mantém página de atendimento a Pouso Alegre',
     'agmatec.com', 'Telefone/WhatsApp 16 99619-0914',
     'Página da empresa, consultada em 21/09/2026'),
    ('JOMAFER Corte a Laser', 'não publicado na página consultada',
     'Corte a laser e estamparia em chapa',
     'Peças planas em chapa; confirmar se corta alumínio e espessuras',
     'Página específica para Pouso Alegre', 'jomafercortealaser.com.br', NP,
     'Resultado de busca, 21/09/2026 — não confirmado'),
    ('BCN Ferragens / FAG Corte a Laser', 'Pouso Alegre / MG',
     'Corte a laser, corte plasma, calandra e serviços de metalurgia',
     'Peças planas; confirmar alumínio e tolerância de ±0,2 mm',
     'Sim — empresa local', NP, 'Telefone/WhatsApp (35) 99213-0310 (fonte: diretório Click&Disk)',
     'Diretório comercial, 21/09/2026 — confirmar diretamente'),
    ('Master Mag Usinagem de Precisão', 'Santa Rita do Sapucaí / MG',
     'Usinagem de precisão em torno e centro CNC (fundada em 2019)',
     'Q-05 (buchas), N-03 (espaçadores), face usinada da S-02 e do berço N-02',
     'A confirmar — ~90 km de Pouso Alegre', 'mastermag.ind.br', NP,
     'Resultado de busca, 21/09/2026 — não confirmado'),
]

MATERIAL = [
    ('KL Alumínios', 'Minas Gerais',
     'Distribuição de chapas e blocos em ligas 6061, 7075 e 5052',
     'Chapas 6061-T6 (3 a 10 mm) e 5052-H32 (1,2 e 2 mm)', 'klaluminios.com.br', NP),
    ('PlastMetal', 'Minas Gerais',
     'Chapas e barras de alumínio; liga 6061 sob encomenda; perfis e tubos',
     'Barras Ø8 e Ø12, chapas 6061-T6', 'plastmetal.com.br', NP),
    ('Alumiplast', 'não publicado na página consultada',
     'Distribuição de tubos, vergalhões e chapas de alumínio (desde 1984)',
     'Tubos Ø25×2 e Ø34×4,5, vergalhões', 'alumiplast.com.br', NP),
    ('Tubos Gerais', 'não publicado na página consultada',
     'Tubos, chapas, curvas e discos', 'Tubos quadrados 30×30×2 e 20×20×1,5', 'tubosgerais.com.br', NP),
]

COMPONENTES = [
    ('Motor-roda + driver', 'ElectroCraft MPW86-185V48-1000-S020 · CPP-A24V80',
     'EUA — comprar via representante/importação', 'RFQ obrigatório: freio, furação e prazo'),
    ('LiDAR 3D', 'Livox Mid-360', 'Importação / revenda nacional', 'Confirmar centro óptico e suporte'),
    ('Câmeras', 'Luxonis OAK-D Pro W PoE (8 un.)', 'Importação / revenda', 'Pedir desenho dimensional'),
    ('GNSS RTK', 'u-blox ZED-F9P + antena', 'Revenda nacional de módulos', 'Definir antena e centro de fase'),
    ('IMU', 'Xsens MTi-630', 'Importação / representante', 'Preço e prazo não levantados'),
    ('Computador', 'NVIDIA Jetson Orin NX 16 GB', 'Revenda nacional', 'Confirmar kit de desenvolvimento'),
    ('Células de bateria', 'EVE LF100LA × 16', 'Importação / integrador de baterias',
     'Caixa e BMS ainda não definidos'),
    ('Fixadores inox A4', 'ISO 4762 / 7380 / 985 / 7093 + porcas-rebite', 'Distribuidor regional',
     '740 peças em 23 códigos — ver BOM'),
]


def build():
    d = Doc('Pesquisa de Fornecedores — Pouso Alegre e região',
            'Levantamento inicial de empresas para corte, dobra, usinagem, soldagem e material, '
            'com prioridade geográfica no Sul de Minas.',
            'VTX-RV3-FORN-E', status='PESQUISA DE MERCADO — DADOS A CONFIRMAR')

    d.alerta('<b>Como esta lista foi feita e o que ela não é.</b> Os dados vêm de páginas públicas e de '
             'busca na web feita em 21/09/2026, e estão marcados como '
             f'{cat("PESQUISA")}. Nenhum telefone, e-mail ou endereço foi inventado: onde não havia '
             'informação pública, está escrito “não publicado”. A ferramenta de busca disponível tem '
             'cobertura fraca para comércio local brasileiro, então <b>esta lista não é um levantamento '
             'completo do parque industrial do Sul de Minas</b> — ela é um ponto de partida.')

    d.h1('Como completar o levantamento')
    d.lista([
        '<b>FIEMG Regional Sul de Minas</b> e <b>Sindicato das Indústrias Metalúrgicas</b>: pedir a lista de '
        'associados com corte a laser, usinagem e caldeiraria.',
        '<b>ACIPA</b> (Associação Comercial e Empresarial de Pouso Alegre): cadastro de indústrias locais.',
        '<b>Google Maps</b>: buscar “corte a laser”, “usinagem CNC”, “caldeiraria” e “serralheria de '
        'alumínio” num raio de 100 km de Pouso Alegre (alcança Itajubá, Santa Rita do Sapucaí, Itapeva, '
        'Congonhal, Borda da Mata e Extrema).',
        '<b>Polo tecnológico de Santa Rita do Sapucaí</b>: várias empresas de usinagem e mecânica de '
        'precisão atendem a indústria eletrônica local.',
        'Visitar 2 ou 3 fornecedores antes de fechar: para protótipo, a capacidade de conversar sobre o '
        'desenho vale mais que o preço.',
    ], ordenada=True)

    d.h1('Fabricação — corte, dobra, usinagem e solda')
    d.tabela(['Empresa', 'Cidade / UF', 'Serviços', 'O que pode fabricar do Rover', 'Atende Pouso Alegre?',
              'Site e contato publicado'],
             [[a, b, c, e, f, f'{g}<br>{h}<br><small>{i}</small>'] for (a, b, c, e, f, g, h, i) in FAB],
             [13, 11, 22, 24, 12, 18], 'compacta')
    d.nota('Não foi possível confirmar, com fonte pública, nenhuma <b>caldeiraria com soldador qualificado '
           'para alumínio</b> (AWS D1.2 / ISO 9606-2) na região. Esse é o ponto mais crítico da cadeia: '
           'a estrutura é soldada em 6061-T6 e a qualificação do soldador é requisito do pacote.')

    d.h1('Matéria-prima — alumínio')
    d.tabela(['Empresa', 'Região', 'Produtos', 'O que atende no projeto', 'Site', 'Contato publicado'],
             [[a, b, c, e, f, g] for (a, b, c, e, f, g) in MATERIAL], [16, 14, 24, 24, 12, 10], 'compacta')

    d.h1('Componentes comprados (não mecânicos)')
    d.tabela(['Item', 'Especificação da Rev E', 'Canal de compra', 'Observação'],
             [[a, b, c, e] for (a, b, c, e) in COMPONENTES], [16, 30, 26, 28], 'compacta')
    d.p(f'Nenhum preço foi levantado para estes itens. {cat("A DEFINIR")} Os arquivos de BOM de compras e '
        'preços citados no escopo do trabalho não foram localizados no projeto.')

    d.h1('Roteiro de contato')
    d.tabela(['Etapa', 'O que enviar', 'O que perguntar'], [
        ['1 · Triagem por telefone/WhatsApp', 'Resumo do projeto em 3 linhas',
         'Trabalha com alumínio? Faz peça sob desenho? Aceita lote de 1 conjunto?'],
        ['2 · Envio do pacote', 'Parte A do caderno + DXF + RFQ',
         'Prazo para responder, dúvidas de interpretação do desenho'],
        ['3 · Avaliação', 'Planilha comparativa das propostas',
         'Preço, prazo, tolerância garantida, qualificação do soldador, frete'],
        ['4 · Visita', 'Lista de verificação de capacidade',
         'Máquinas, gabaritos, inspeção dimensional, experiência com alumínio'],
    ], [22, 32, 46], 'compacta')

    d.h1('Planilha de controle')
    d.p('A versão em planilha desta lista está em <b>06_FORNECEDORES/Fornecedores-Pouso-Alegre-e-Regiao.xlsx</b>, '
        'com colunas para registrar contato feito, proposta recebida, prazo e preço.')
    return d


def planilha(destino):
    """Gera a planilha de controle de fornecedores."""
    cab = ['Empresa', 'Cidade/UF', 'Categoria', 'Serviços', 'O que pode fabricar', 'Atende Pouso Alegre?',
           'Site', 'Contato publicado', 'Fonte do dado', 'Status do contato', 'Data do contato',
           'Proposta recebida', 'Prazo informado', 'Preço informado (R$)', 'Observações']
    linhas = []
    for (a, b, c, e, f, g, h, i) in FAB:
        linhas.append([a, b, 'Fabricação', c, e, f, g, h.replace('<i>', '').replace('</i>', ''), i,
                       'A contatar', '', '', '', '', ''])
    for (a, b, c, e, f, g) in MATERIAL:
        linhas.append([a, b, 'Matéria-prima', c, e, 'A confirmar', f,
                       g.replace('<i>', '').replace('</i>', ''), 'Busca web 21/09/2026',
                       'A contatar', '', '', '', '', ''])
    for (a, b, c, e) in COMPONENTES:
        linhas.append([b, '—', 'Componente comprado', a, a, 'A confirmar', '', '', 'Baseline Rev E',
                       'A contatar', '', '', '', '', e])
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment
        wb = Workbook()
        ws = wb.active
        ws.title = 'Fornecedores'
        ws.append(cab)
        for l in linhas:
            ws.append(l)
        for c in ws[1]:
            c.font = Font(bold=True, color='FFFFFF')
            c.fill = PatternFill('solid', fgColor='1F6B3A')
            c.alignment = Alignment(wrap_text=True)
        for i, w in enumerate([26, 20, 20, 40, 40, 24, 24, 28, 30, 16, 14, 16, 16, 18, 40], 1):
            ws.column_dimensions[ws.cell(1, i).column_letter].width = w
        ws.freeze_panes = 'A2'
        ws.auto_filter.ref = ws.dimensions
        destino.parent.mkdir(parents=True, exist_ok=True)
        wb.save(destino)
        return destino
    except ImportError:
        return None
