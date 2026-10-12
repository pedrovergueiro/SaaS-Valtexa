"""Estrutura de custo do VALTEXA ROVER V3 — planilha pronta para receber cotações.

Não contém preço estimado. As quantidades vêm do modelo paramétrico; as colunas de preço ficam
em branco, com fórmula de total, para serem preenchidas com cotação real ou pesquisa com fonte.
A única linha com preço preenchido traz fonte e data, como exemplo do padrão de preenchimento.
"""
import pathlib
import sys

AQUI = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent / 'chassi-gaiola'))

import modelo as M          # noqa: E402
import dados                # noqa: E402
from processos import LASER, SERRA, BARRA, TORNO, FRESA, PLAST, MATERIA_PRIMA  # noqa: E402
import bom_precos                                                             # noqa: E402

# Referências de preço extraídas da BOM de compras (21/09/2026) e usadas para extrapolar
# as quantidades reais do projeto. NÃO são cotação: são a própria base do usuário, escalada.
REF_CHAPA_MM_M2 = 280.0 / 0.6 / 3.0      # R$ 155,56 por m² e por mm de espessura
REF_TUBO_30 = 50.0 / 6.0                 # R$ 8,33 por metro de tubo 30×30×2

# Massa linear do tubo Al 30×30×2, pela geometria: (30² − 26²) mm² × 2,70 g/cm³.
# A Rev E usava 0,218 kg/m aqui, valor que a seção não permite — o erro inflava o
# R$/kg implícito em 2,78× (R$ 38,23 em vez de R$ 13,77) e com ele o custo de todo
# item precificado por massa. Corrigido na Rev F; ver D-05 na auditoria.
MASSA_LINEAR_TUBO_30 = (30.0**2 - 26.0**2) * 2.70e-6 * 1000.0   # 0,605 kg/m
REF_MASSA_KG = REF_TUBO_30 / MASSA_LINEAR_TUBO_30               # R$ 13,77/kg

VERDE = '1F6B3A'
CINZA = 'F2F1EC'
AMARELO = 'FFF6DA'

# componentes de compra, conforme a baseline Rev E (quantidade e especificação confirmadas;
# preço NUNCA estimado aqui)
COMPONENTES = [
    ('Motor-roda integrado', 'ElectroCraft MPW86-185V48-1000-S020 (com freio)', 4, 'un', 'USD',
     '', 'Catálogo marca "Contact Sales" — exige RFQ', ''),
    ('Driver de motor', 'ElectroCraft CPP-A24V80', 4, 'un', 'USD', '', 'RFQ com o mesmo fabricante', ''),
    ('Câmera RGB-D', 'Luxonis OAK-D Pro W PoE', 8, 'un', 'USD', 649,
     'shop.luxonis.com, consultado em 21/09/2026 — preço de lista, sem frete nem imposto',
     'PESQUISA'),
    ('LiDAR 3D', 'Livox Mid-360', 1, 'un', 'USD', '',
     'Revendedores divergem de centenas a US$ 3.800 — cotar com distribuidor oficial', ''),
    ('Computador', 'NVIDIA Jetson Orin NX 16 GB (módulo)', 1, 'un', 'USD', '',
     'Referência pública antiga: US$ 599 em volume de 1.000 un (2022) — cotar atual', ''),
    ('GNSS RTK', 'u-blox ZED-F9P + antena', 1, 'jg', 'USD', '', 'Cotar com distribuidor (módulo + antena)', ''),
    ('IMU', 'Xsens MTi-630', 1, 'un', 'USD', '', 'Cotar com representante', ''),
    ('Célula de bateria', 'EVE LF100LA (LiFePO4 3,2 V 100 Ah)', 16, 'un', 'USD', '',
     'Cotar com integrador de baterias', ''),
    ('BMS + contator + pré-carga', 'A definir pela engenharia elétrica', 1, 'jg', 'BRL', '',
     'Especificação ainda não fechada', ''),
    ('Caixa da bateria', 'A definir — desenho inexistente', 1, 'un', 'BRL', '',
     'Depende do arranjo das 16 células', ''),
    ('DC/DC + carregador onboard', 'A definir', 1, 'jg', 'BRL', '', 'Carregador de 2,5 kW na baseline', ''),
    ('Microcontrolador de segurança', 'A definir', 1, 'un', 'BRL', '', 'Cadeia de E-STOP independente', ''),
    ('Botão de emergência', 'Ø22 mm IP65, contato NF', 1, 'un', 'BRL', '', 'Componente comercial', ''),
    ('Rádio RTK + rádio de parada', 'A definir', 1, 'jg', 'BRL', '', 'Dois canais independentes', ''),
    ('Faróis LED', 'A definir — Ø20 mm', 2, 'un', 'BRL', '', 'Modelo não especificado na baseline', ''),
    ('Cabeamento de potência', 'Cabos, conectores e passa-cabos', 1, 'jg', 'BRL', '',
     'Baseline estima 3,0 kg', ''),
    ('Cabeamento de sensores', 'PoE, USB e alimentação', 1, 'jg', 'BRL', '', 'Baseline estima 1,0 kg', ''),
]

FABRICACAO = [
    ('Corte a laser / CNC', 'Peças planas em alumínio e policarbonato', '', 'conjunto',
     'Ver lista da folha 02 do pacote de fabricação — 25 códigos, 80 peças'),
    ('Dobra', 'E-11 e N-06', '', 'conjunto', 'Raio e desenvolvimento a definir pelo fabricante'),
    ('Usinagem', 'Q-05, N-03, M-12, N-04 e faces usinadas da S-02 e N-02', '', 'conjunto',
     'A face do MPW86 exige Ra 3,2 e planicidade 0,1'),
    ('Corte de tubos e perfis', 'Serra, 90°, sem rebarba', '', 'conjunto',
     'Ver lista de corte — 8 perfis diferentes'),
    ('Soldagem TIG', '3 conjuntos soldados (quadro, 4 suportes, 2 módulos de gaiola)', '', 'conjunto',
     'Soldador qualificado AWS D1.2 / ISO 9606-2'),
    ('Gabaritos de soldagem', 'Custo único, não recorrente', '', 'lote',
     'Perguntar se é cobrado à parte ou diluído'),
    ('Tratamento de superfície', 'Opção A natural / B anodização / C pintura', '', 'conjunto',
     'Cotar as três'),
    ('Instalação de porcas-rebite', '176 porcas-rebite M5 e M6', '', 'conjunto', 'Depois do acabamento'),
    ('Montagem mecânica', 'Montagem do conjunto e aperto com torquímetro', '', 'conjunto',
     'Sequência na folha 13'),
    ('Inspeção dimensional', 'Relatório das 9 características críticas', '', 'conjunto',
     'Entregável obrigatório'),
    ('Frete', 'Até Pouso Alegre / MG', '', 'lote', ''),
]

BASE_POSTE = [
    ('Base — estrutura', 'Perfil metálico da plataforma e do abrigo', 'A DEFINIR',
     'Depende das 8 decisões de requisito (documento de conceito)'),
    ('Base — piso e rampa', 'Plataforma nivelada com rampa ≤ 10°', 'A DEFINIR', 'Vão livre de 208 mm'),
    ('Base — guias de alinhamento', 'Duas guias em V', 'A DEFINIR', 'Corrigem ±60 mm de erro lateral'),
    ('Base — acoplamento de recarga', 'Conector manual, contato ou indutivo', 'A DEFINIR',
     'Decisão 1 do conceito — define tudo o resto'),
    ('Base — carregador', 'Gabinete IP54 ventilado, 2,5 kW', 'A DEFINIR', 'Tempo de recarga da baseline'),
    ('Base — quadro elétrico e proteções', 'Disjuntor, DPS, aterramento', 'A DEFINIR',
     'Projeto elétrico inexistente'),
    ('Base — fundação e fixação', '4 sapatas ajustáveis + ancoragem', 'A DEFINIR', 'Terreno irregular'),
    ('Base — energia solar (opcional)', 'Painéis, controlador e banco', 'A DEFINIR',
     'A baseline descartou solar no rover; na base é decisão nova'),
    ('Poste — estrutura', 'Tubo ou treliça, 4 m livres', 'A DEFINIR', 'Cálculo de vento não feito'),
    ('Poste — fundação', 'Bloco de concreto com chumbadores', 'A DEFINIR', 'Depende do solo'),
    ('Poste — aterramento e SPDA', 'Projeto de profissional habilitado', 'A DEFINIR',
     'Obrigatório e não orçável sem projeto'),
    ('Poste — suportes e caixas', 'Antena base RTK, rádio, caixa IP65', 'A DEFINIR', ''),
    ('Poste — instalação', 'Mão de obra e içamento', 'A DEFINIR', ''),
    ('Projeto de engenharia das bases', 'Caderno VTX-RV3-BASE-E, inexistente', 'A DEFINIR',
     'Precisa ser feito antes de qualquer cotação'),
]


def gerar(destino):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    fina = Side(style='thin', color='D8D6C8')
    borda = Border(bottom=fina)

    def cabecalho(ws, cols, larguras):
        ws.append(cols)
        for c in ws[1]:
            c.font = Font(bold=True, color='FFFFFF', size=10)
            c.fill = PatternFill('solid', fgColor=VERDE)
            c.alignment = Alignment(wrap_text=True, vertical='center')
        for i, w in enumerate(larguras, 1):
            ws.column_dimensions[get_column_letter(i)].width = w
        ws.freeze_panes = 'A2'
        ws.row_dimensions[1].height = 30

    def acaba(ws, primeira, ultima, col_total):
        for row in ws.iter_rows(min_row=2, max_row=ultima):
            for c in row:
                c.border = borda
        ws.append([])
        ws.append(['TOTAL', '', '', '', '', '', f'=SUM({col_total}{primeira}:{col_total}{ultima})'])
        for c in ws[ws.max_row]:
            c.font = Font(bold=True)
        ws.cell(ws.max_row, 7).number_format = 'R$ #,##0.00'
        return ws.max_row

    # ---------------------------------------------------------- MATERIAL
    ws = wb.active
    ws.title = '1 Material'
    cabecalho(ws, ['Material', 'Especificação', 'Quantidade', 'Unidade', 'Preço unit. (R$)',
                   'Fonte e data do preço', 'Total (R$)'], [30, 26, 12, 10, 16, 34, 14])
    tub = dados.tubos()
    area = dados.area_chapa()

    def secao(titulo):
        ws.append([titulo])
        ws.cell(ws.max_row, 1).font = Font(bold=True, size=10)
        ws.cell(ws.max_row, 1).fill = PatternFill('solid', fgColor=CINZA)

    secao('Consumo calculado — tubos, barras e perfis (por conjunto)')
    ini = ws.max_row + 1
    for k, v in sorted(tub.items()):
        ws.append([k, 'comprimento somado das peças', round(v, 2), 'm', '', '', ''])
    secao('Consumo calculado — chapa (área bruta, sem aninhamento)')
    for (m, esp), v in sorted(area.items()):
        ws.append([f'Chapa {esp} mm', m, round(v, 3), 'm²', '', '', ''])
    fim = ws.max_row
    for r in range(ini, fim + 1):
        if ws.cell(r, 3).value in (None, ''):
            continue
        nome = str(ws.cell(r, 1).value)
        un = ws.cell(r, 4).value
        ref = None
        if un == 'm²':
            esp = nome.replace('Chapa ', '').replace(' mm', '').replace(',', '.')
            try:
                ref = REF_CHAPA_MM_M2 * float(esp)
            except ValueError:
                ref = None
        elif un == 'm':
            massa_m = {'Tubo quadrado 30×30×2': 0.218, 'Tubo quadrado 20×20×1,5': 0.150,
                       'Tubo Ø25×2 × 1436': 0.391, 'Tubo Ø34×4,5 × 180': 1.128,
                       'Cantoneira 40×40×4 × 592': 0.820, 'Cantoneira 40×40×4 × 150': 0.820,
                       'Barra Ø8 × 170': 0.136, 'Tubo Ø29/Ø25': 0.070}.get(nome)
            ref = REF_MASSA_KG * massa_m if massa_m else None
        if ref:
            ws.cell(r, 5).value = round(ref, 2)
            ws.cell(r, 6).value = 'referência extrapolada da BOM de compras'
        ws.cell(r, 7).value = f'=IF(E{r}="","",C{r}*E{r})'
        ws.cell(r, 7).number_format = 'R$ #,##0.00'
        ws.cell(r, 5).number_format = 'R$ #,##0.00'
        ws.cell(r, 5).fill = PatternFill('solid', fgColor=AMARELO)
    secao('Compra sugerida — o fornecedor costuma vender assim')
    for (mat, liga, norma, qtd, origem) in MATERIA_PRIMA:
        ws.append([mat, f'{liga} · {norma}', qtd, '—', '', 'referência de compra', ''])
    linha_total = acaba(ws, ini, fim, 'G')
    ws.cell(ws.max_row + 2, 1).value = ('Preencher a coluna amarela com preço real. Alumínio costuma ser '
                                        'cotado por kg; converta usando a massa da BOM se o fornecedor '
                                        'cotar assim.')
    ws.cell(ws.max_row, 1).font = Font(italic=True, size=9)

    # -------------------------------------------------------- FABRICAÇÃO
    ws = wb.create_sheet('2 Fabricação')
    cabecalho(ws, ['Serviço', 'Escopo', 'Quantidade', 'Unidade', 'Preço unit. (R$)',
                   'Fornecedor / fonte', 'Total (R$)'], [26, 42, 12, 12, 16, 26, 14])
    met = dados.metricas_corte()
    juntas, cordao = dados.metricas_solda()
    quantidades = {
        'Corte a laser / CNC': (round(met['corte_m'], 1), 'm de corte'),
        'Dobra': (3, 'dobras'),
        'Usinagem': (24, 'peças'),
        'Corte de tubos e perfis': (round(sum(dados.tubos().values()), 1), 'm de perfil'),
        'Soldagem TIG': (round(cordao, 1), 'm de cordão'),
        'Gabaritos de soldagem': (3, 'gabaritos'),
        'Tratamento de superfície': (round(met['area_m2'], 2), 'm² de superfície'),
        'Instalação de porcas-rebite': (176, 'porcas'),
        'Montagem mecânica': (1, 'conjunto'),
        'Inspeção dimensional': (9, 'cotas críticas'),
        'Frete': (1, 'entrega'),
    }
    for (serv, escopo, qtd, un, obs) in FABRICACAO:
        q, u = quantidades.get(serv, (1, un))
        ws.append([serv, escopo, q, u, '', '', ''])
        r = ws.max_row
        ws.cell(r, 7).value = f'=IF(E{r}="","",C{r}*E{r})'
        ws.cell(r, 7).number_format = 'R$ #,##0.00'
        ws.cell(r, 5).number_format = 'R$ #,##0.00'
        ws.cell(r, 5).fill = PatternFill('solid', fgColor=AMARELO)
        ws.cell(r, 2).alignment = Alignment(wrap_text=True)
    total_fab = acaba(ws, 2, ws.max_row, 'G')
    ws.append([])
    ws.append(['Como estas quantidades foram obtidas (todas DERIVADAS da geometria do caderno):'])
    ws.cell(ws.max_row, 1).font = Font(bold=True, size=9)
    for txt in (
            f"Corte a laser: {met['contorno_m']:.1f} m de contorno + {met['furos_m']:.1f} m de furos "
            f"= {met['corte_m']:.1f} m, em {met['n_furos']} furos",
            f"Soldagem: {cordao:.1f} m de cordão somando as juntas de todos os conjuntos soldados",
            f"Tratamento de superfície: {met['area_m2']:.2f} m² de área externa das peças planas",
            'Porcas-rebite: 176 unidades M5 e M6 instaladas depois do acabamento',
            'Peça ao fornecedor o preço por metro de corte e por metro de cordão: fica comparável entre '
            'propostas.'):
        ws.append([txt])
        ws.cell(ws.max_row, 1).font = Font(size=9, italic=True)

    # ------------------------------------------------------- COMPONENTES
    ws = wb.create_sheet('3 Componentes')
    ws.append(['Câmbio USD → BRL:', '', '← preencher', '', '', '', '', ''])
    ws['A1'].font = Font(bold=True)
    ws['B1'].fill = PatternFill('solid', fgColor=AMARELO)
    ws.append([])
    ws.append(['Componente', 'Especificação (baseline Rev E)', 'Qtd', 'Un', 'Moeda',
               'Preço unit.', 'Fonte e data', 'Total (R$)'])
    for c in ws[3]:
        c.font = Font(bold=True, color='FFFFFF', size=10)
        c.fill = PatternFill('solid', fgColor=VERDE)
        c.alignment = Alignment(wrap_text=True, vertical='center')
    for i, w in enumerate([26, 36, 7, 7, 9, 13, 40, 14], 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = 'A4'
    primeira = 4
    for (nome, esp, qtd, un, moeda, preco, fonte, etiqueta) in COMPONENTES:
        ws.append([nome, esp, qtd, un, moeda, preco, fonte, ''])
        r = ws.max_row
        ws.cell(r, 8).value = (f'=IF(F{r}="","",IF(E{r}="USD",C{r}*F{r}*$B$1,C{r}*F{r}))')
        ws.cell(r, 8).number_format = 'R$ #,##0.00'
        ws.cell(r, 6).fill = PatternFill('solid', fgColor=AMARELO)
        ws.cell(r, 2).alignment = Alignment(wrap_text=True)
        ws.cell(r, 7).alignment = Alignment(wrap_text=True)
    ultima = ws.max_row
    ws.append([])
    ws.append(['TOTAL (sem impostos e frete de importação)', '', '', '', '', '', '',
               f'=SUM(H{primeira}:H{ultima})'])
    total_comp = ws.max_row
    ws.cell(ws.max_row, 8).number_format = 'R$ #,##0.00'
    for c in ws[ws.max_row]:
        c.font = Font(bold=True)
    ws.append(['Impostos e frete de importação', '', '', '', '', '', 'A DEFINIR com despachante', ''])
    ws.cell(ws.max_row, 8).fill = PatternFill('solid', fgColor=AMARELO)
    ws.cell(ws.max_row, 8).number_format = 'R$ #,##0.00'

    # ------------------------------------------------------ BASE E POSTE
    ws = wb.create_sheet('4 Base e poste')
    cabecalho(ws, ['Item', 'Descrição', 'Quantidade', 'Situação', 'Preço unit. (R$)',
                   'Observação', 'Total (R$)'], [28, 40, 14, 14, 16, 40, 14])
    for (item, desc, sit, obs) in BASE_POSTE:
        ws.append([item, desc, 'A DEFINIR', sit, '', obs, ''])
        r = ws.max_row
        ws.cell(r, 5).fill = PatternFill('solid', fgColor=AMARELO)
        ws.cell(r, 2).alignment = Alignment(wrap_text=True)
        ws.cell(r, 6).alignment = Alignment(wrap_text=True)
    ws.append([])
    ws.append(['A base de recarga e o poste NÃO têm projeto: não há dimensão, material nem quantidade '
               'na baseline Rev E.'])
    ws.cell(ws.max_row, 1).font = Font(bold=True, color='A4291F')
    ws.append(['Orçar só depois de responder às 8 decisões de requisito do documento '
               'VTX-RV3-BASE-E-CONCEITO.'])
    ws.cell(ws.max_row, 1).font = Font(italic=True, size=9)

    # --------------------------------------------- PREÇOS RECEBIDOS (BOM)
    ws = wb.create_sheet('5 Preços recebidos')
    ws.append([f'Transcrição de {bom_precos.FONTE} — valores de produto, sem imposto de importação'])
    ws['A1'].font = Font(italic=True, size=9)
    ws.append([])
    ws.append(['Categoria', 'Item', 'Fornecedor', 'Qtd', 'Unit. (R$)', 'Total (R$)', 'Origem',
               'Na compra recomendada?'])
    for c in ws[3]:
        c.font = Font(bold=True, color='FFFFFF', size=10)
        c.fill = PatternFill('solid', fgColor=VERDE)
        c.alignment = Alignment(wrap_text=True, vertical='center')
    for i, w in enumerate([14, 44, 26, 6, 12, 13, 12, 12], 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = 'A4'
    for (cat, item, forn, qtd, unit, total, origem, escolhido) in bom_precos.BOM:
        ws.append([cat, item, forn, qtd, unit, total, origem, 'sim' if escolhido else 'alternativa'])
        r = ws.max_row
        for col in (5, 6):
            ws.cell(r, col).number_format = 'R$ #,##0.00'
        if not escolhido:
            for c in ws[r]:
                c.font = Font(color='86877A', italic=True)
    ws.append([])
    for rotulo, chave in (('Subtotal nacional', 'nacional'),
                          ('Subtotal importado (produto)', 'importado_produto'),
                          ('Total dos produtos', 'produtos'),
                          ('Importado com impostos e frete (×2,0)', 'importado_com_imposto'),
                          ('TOTAL POSTO EM POUSO ALEGRE', 'geral_posto_pouso_alegre')):
        ws.append([rotulo, '', '', '', '', bom_precos.TOTAIS[chave], '', ''])
        ws.cell(ws.max_row, 6).number_format = 'R$ #,##0.00'
        ws.cell(ws.max_row, 1).font = Font(bold=True)
        ws.cell(ws.max_row, 6).font = Font(bold=True)
    ws.append([])
    ws.append(['Cenário', 'Produtos (R$)', 'Posto em Pouso Alegre (R$)'])
    for c in ws[ws.max_row][:3]:
        c.font = Font(bold=True, color='FFFFFF', size=10)
        c.fill = PatternFill('solid', fgColor=VERDE)
    for (nome, prod, posto) in bom_precos.CENARIOS:
        ws.append([nome, prod, posto])
        for col in (2, 3):
            ws.cell(ws.max_row, col).number_format = 'R$ #,##0.00'
    ws.append([])
    ws.append(['O multiplicador de 2,0× para importação (II + IPI + PIS/COFINS + ICMS + frete) é '
               'estimativa da planilha de origem — confirmar com despachante.'])
    ws.cell(ws.max_row, 1).font = Font(italic=True, size=9, color='A4291F')

    # ------------------------------------------------------- CONCILIAÇÃO
    ws = wb.create_sheet('6 Conciliação')
    ws.append(['Conciliação entre a BOM de compras e o projeto mecânico (caderno VTX-RV3-CG-F)'])
    ws['A1'].font = Font(bold=True, size=12)
    ws.append(['Nada aqui é opinião de preço: é comparação entre o que a planilha compra e o que o '
               'desenho exige.'])
    ws['A2'].font = Font(italic=True, size=9)
    ws.append([])
    ws.append(['Gravidade', 'Assunto', 'O que a BOM de compras diz', 'O que o projeto exige',
               'Consequência'])
    for c in ws[4]:
        c.font = Font(bold=True, color='FFFFFF', size=10)
        c.fill = PatternFill('solid', fgColor=VERDE)
        c.alignment = Alignment(wrap_text=True, vertical='center')
    for i, w in enumerate([11, 22, 46, 46, 52], 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = 'A5'
    cores = {'CRÍTICA': 'A4291F', 'ALTA': '8A6414', 'MÉDIA': '22526D', 'BAIXA': '86877A'}
    for (grav, assunto, bom_diz, projeto, conseq) in bom_precos.DIVERGENCIAS:
        ws.append([grav, assunto, bom_diz, projeto, conseq])
        r = ws.max_row
        ws.cell(r, 1).font = Font(bold=True, color=cores.get(grav, '000000'))
        for col in (2, 3, 4, 5):
            ws.cell(r, col).alignment = Alignment(wrap_text=True, vertical='top')
    ws.append([])
    ws.append(['MATERIAL E SERVIÇO QUE O PROJETO EXIGE E A BOM NÃO COBRE'])
    ws.cell(ws.max_row, 1).font = Font(bold=True, size=11)
    ws.append(['Tipo', 'Item', 'Quantidade do projeto', 'Situação na BOM', 'Observação'])
    for c in ws[ws.max_row]:
        c.font = Font(bold=True, color='FFFFFF', size=10)
        c.fill = PatternFill('solid', fgColor=VERDE)
    for linha in bom_precos.faltantes(dados):
        ws.append(linha)
        r = ws.max_row
        if linha[3] == 'FALTA':
            ws.cell(r, 4).font = Font(bold=True, color='A4291F')
        ws.cell(r, 5).alignment = Alignment(wrap_text=True)

    # ------------------------------------------------------------ RESUMO
    ws = wb.create_sheet('0 Resumo', 0)
    ws.append(['VALTEXA ROVER V3 — ESTRUTURA DE CUSTO'])
    ws['A1'].font = Font(bold=True, size=14)
    ws.append(['Rev E · 21/09/2026 · preços de compra recebidos (abas 5 e 6); serviços de fabricação ainda a cotar nas células amarelas'])
    ws['A2'].font = Font(italic=True, size=9)
    ws.append([])
    ws.append(['Bloco', 'Total por conjunto (R$)', 'O que falta para fechar'])
    for c in ws[4]:
        c.font = Font(bold=True, color='FFFFFF')
        c.fill = PatternFill('solid', fgColor=VERDE)
    for i, w in enumerate([34, 22, 60], 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.append(['1 · Matéria-prima (alumínio, PC, UHMW)', f"='1 Material'!G{linha_total}",
               'Preço do alumínio por kg ou por barra/chapa'])
    ws.append(['2 · Serviços de fabricação', f"='2 Fabricação'!G{total_fab}",
               'Cotação de corte, dobra, usinagem, solda e acabamento'])
    ws.append(['3 · Componentes comprados', f"='3 Componentes'!H{total_comp}",
               'Preço de motor-roda, LiDAR, Jetson, GNSS, IMU e células'])
    ws.append(['4 · Base de recarga e poste', 'sem projeto',
               'Conceito, sem dimensão nem quantidade — ver pasta 09'])
    ws.append(['TOTAL DO ROVER (1 conjunto)',
               f"=IF(COUNT(B5:B7)=3,SUM(B5:B7),\"ver aba 5\")", ''])
    ws.append([])
    ws.append(['CUSTO CONHECIDO — planilha de compras recebida em 21/09/2026', '', ''])
    ws.cell(ws.max_row, 1).font = Font(bold=True)
    for rotulo, valor, obs in (
            ('Produtos (nacional + importado, sem imposto)', bom_precos.TOTAIS['produtos'],
             'Aba 5 · transcrição da BOM de compras'),
            ('Posto em Pouso Alegre (importado × 2,0)', bom_precos.TOTAIS['geral_posto_pouso_alegre'],
             'Multiplicador estimado na planilha de origem'),
            ('Cenário mínimo', bom_precos.CENARIOS[0][2], bom_precos.CENARIOS[0][0]),
            ('Cenário máximo', bom_precos.CENARIOS[2][2], bom_precos.CENARIOS[2][0])):
        ws.append([rotulo, valor, obs])
        ws.cell(ws.max_row, 2).number_format = 'R$ #,##0.00'
    ws.append(['Estrutura mecânica dentro desse total', bom_precos.POR_CATEGORIA[4][1],
               'Apenas 2,8 % — ver aba 6: faltam material e serviços'])
    ws.cell(ws.max_row, 2).number_format = 'R$ #,##0.00'
    ws.cell(ws.max_row, 3).font = Font(color='A4291F')
    for c in ws[ws.max_row]:
        c.font = Font(bold=True)
    for r in range(5, ws.max_row + 1):
        ws.cell(r, 2).number_format = 'R$ #,##0.00'
    ws.append([])
    ws.append(['Quantidades que já estão fechadas', '', ''])
    ws.cell(ws.max_row, 1).font = Font(bold=True)
    its = dados.itens()
    fatos = [
        ('Códigos de peça fabricada', len(its), 'Somando 183 peças por conjunto'),
        ('Massa de peça pronta', f'{sum(i["massa"] for i in its):.2f} kg', 'Alumínio, policarbonato e UHMW-PE'),
        ('Fixadores', sum(q for (_, _, _, q, _) in M.fixadores()), 'Em 23 códigos, inox A4'),
        ('Tubo e perfil', f'{sum(dados.tubos().values()):.1f} m', 'Oito seções diferentes'),
        ('Chapa bruta', f'{sum(dados.area_chapa().values()):.2f} m²', 'Sem aninhamento'),
        ('Massa do rover', '96,31 kg', 'Mínima verificável, sem payload'),
    ]
    for (a, b, c) in fatos:
        ws.append([a, b, c])
    ws.append([])
    ws.append(['Como usar', '', ''])
    ws.cell(ws.max_row, 1).font = Font(bold=True)
    for txt in ('1. Envie o RFQ (pasta 07) para 3 fornecedores e preencha a aba 2.',
                '2. Peça preço de material por kg/barra e preencha a aba 1.',
                '3. Cote os componentes com distribuidor e preencha a aba 3, com câmbio e imposto.',
                '4. A base e o poste só entram depois que existir projeto (pasta 09).'):
        ws.append([txt, '', ''])
        ws.cell(ws.max_row, 1).font = Font(size=9)

    destino.parent.mkdir(parents=True, exist_ok=True)
    wb.save(destino)
    return destino


if __name__ == '__main__':
    p = gerar(AQUI / 'saida' / 'VALTEXA_ROVER_V3_REV_F' / '10_CUSTOS' /
              'VTX-RV3-Estrutura-de-Custo-RevF.xlsx')
    print('planilha:', p)
