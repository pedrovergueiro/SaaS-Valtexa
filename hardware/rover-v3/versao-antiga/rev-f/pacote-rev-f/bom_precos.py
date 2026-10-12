"""Preços de compra — extraídos de VALTEXA-ROVER-V3-BOM-Links-Precos.xlsx (recebido em 21/09/2026).

Fonte: planilha da ValTexa com links de compra. Os valores são de produto, sem imposto de importação.
Nada aqui foi estimado por este pacote: é transcrição da planilha, com a conciliação contra o
projeto mecânico do caderno VTX-RV3-CG-F ao lado.
"""

FONTE = 'VALTEXA-ROVER-V3-BOM-Links-Precos.xlsx · 21/09/2026'

# (categoria, item, fornecedor, qtd, unit R$, total R$, origem, escolhido na "Compra Recomendada")
BOM = [
    ('TRAÇÃO', 'Motor-roda 48V AGV 8" ZLTECH ZLLG80ASM800', 'AliExpress / ZLTECH', 4, 2215.34, 8861.36,
     'IMPORTADO', True),
    ('TRAÇÃO', 'Motor-roda ElectroCraft MPW86 com freio', 'ElectroCraft (Contact Sales)', 4, 6425.00,
     25700.00, 'IMPORTADO', False),
    ('TRAÇÃO', 'Driver BLDC Roboteq SBLG2360TS', 'Roboteq', 4, 3366.70, 13466.80, 'IMPORTADO', True),
    ('ENERGIA', 'Célula LiFePO4 EVE 3,2 V 105 Ah', 'Buyers Energy (BR)', 16, 582.00, 9312.00,
     'NACIONAL', True),
    ('ENERGIA', 'Célula LiFePO4 100 Ah (alternativa)', 'Mercado Livre', 16, 399.00, 6384.00,
     'NACIONAL', False),
    ('ENERGIA', 'BMS Daly Smart 16S 100 A com CAN', 'Amazon BR', 1, 747.21, 747.21, 'NACIONAL', True),
    ('ENERGIA', 'Conversor DC/DC 48→12 V 30 A', 'Mercado Livre', 1, 399.94, 399.94, 'NACIONAL', True),
    ('ENERGIA', 'Carregador LiFePO4 48 V 30 A', 'SuperBat / Litime', 1, 1189.00, 1189.00, 'NACIONAL', True),
    ('ENERGIA', 'Contator DC TE Kilovac LEV200', 'DigiKey', 1, 771.00, 771.00, 'IMPORTADO', True),
    ('ENERGIA', 'Fusíveis, disjuntor DC e pré-carga', 'Mercado Elétrico', 1, 617.00, 617.00,
     'NACIONAL', True),
    ('SENSORES', 'LiDAR Livox Mid-360 (importação direta)', 'mylidarstore', 1, 4626.00, 4626.00,
     'IMPORTADO', True),
    ('SENSORES', 'LiDAR Mid-360 no importador BR (não recomendado)', 'Loja do Jangão', 1, 19830.12,
     19830.12, 'NACIONAL', False),
    ('SENSORES', 'Câmera OAK-D Pro W PoE', 'Luxonis', 8, 3490.06, 27920.48, 'IMPORTADO', True),
    ('SENSORES', 'GNSS RTK ZED-F9P + antena (kit)', 'ArduSimple', 1, 1181.60, 1181.60, 'IMPORTADO', True),
    ('SENSORES', 'IMU Xsens MTi-630 (CAN)', 'DigiKey', 1, 5134.86, 5134.86, 'IMPORTADO', True),
    ('SENSORES', 'Par de rádios RTK RFD900x', 'IR-Lock', 1, 1434.06, 1434.06, 'IMPORTADO', True),
    ('SENSORES', 'E-STOP remoto sem fio industrial', 'a cotar', 1, 1799.00, 1799.00, 'IMPORTADO', True),
    ('COMPUTAÇÃO', 'Jetson Orin NX 16 GB (módulo)', 'Loja do Jangão (BR)', 1, 9899.00, 9899.00,
     'NACIONAL', True),
    ('COMPUTAÇÃO', 'SSD NVMe 1 TB', 'Mercado Livre / Kabum', 1, 450.00, 450.00, 'NACIONAL', True),
    ('COMPUTAÇÃO', 'Relé de segurança Pilz PNOZ s4', 'Logic Control', 1, 1870.96, 1870.96,
     'IMPORTADO', True),
    ('ESTRUTURA', 'Tubo alumínio quadrado 30×30×2 (barra 6 m)', 'Mercado Livre', 6, 50.00, 300.00,
     'NACIONAL', True),
    ('ESTRUTURA', 'Tubo alumínio redondo Ø25×2 (3 m)', 'Mercado Livre', 3, 45.00, 135.00,
     'NACIONAL', True),
    ('ESTRUTURA', 'Chapa alumínio 3 mm (0,6 m²)', 'Mercado Livre', 1, 280.00, 280.00, 'NACIONAL', True),
    ('ESTRUTURA', 'Tarugo UHMW-PE', 'Mercado Livre', 1, 270.01, 270.01, 'NACIONAL', True),
    ('ESTRUTURA', 'Parafusos e fixadores inox', 'Mercado Livre', 1, 300.00, 300.00, 'NACIONAL', True),
    ('ESTRUTURA', 'Serviço de corte laser + dobra', 'metalúrgica regional (a cotar)', 1, 800.00, 800.00,
     'NACIONAL', True),
    ('ESTRUTURA', 'Serviço de impressão 3D (carenagens)', 'serviço regional (a cotar)', 1, 500.00, 500.00,
     'NACIONAL', True),
    ('ELÉTRICA', 'Cabo flexível 10 mm² (25 m)', 'Casa do Eletricista', 25, 10.40, 260.00, 'NACIONAL', True),
    ('ELÉTRICA', 'Cabo CAN/Ethernet blindado (20 m)', 'Mercado Livre', 20, 12.00, 240.00, 'NACIONAL', True),
    ('ELÉTRICA', 'Conectores Anderson SB50 (kit)', 'Mercado Livre', 1, 180.00, 180.00, 'NACIONAL', True),
    ('ELÉTRICA', 'Conectores M12 industriais (kit)', 'Mercado Livre', 1, 400.00, 400.00, 'NACIONAL', True),
    ('ELÉTRICA', 'Gabinete IP65 policarbonato', 'Mercado Livre', 1, 400.00, 400.00, 'NACIONAL', True),
    ('ELÉTRICA', 'Iluminação LED 12 V (conjunto)', 'Mercado Livre', 1, 250.00, 250.00, 'NACIONAL', True),
]

TOTAIS = {
    'nacional': 26929.16,
    'importado_produto': 67066.12,
    'produtos': 93995.28,
    'importado_com_imposto': 134132.24,
    'geral_posto_pouso_alegre': 161061.40,
    'multiplicador_importacao': 2.0,
}

CENARIOS = [
    ('MÍNIMO (alternativas baratas: VESC, BMI088, célula 100 Ah)', 53069.54, 83249.29),
    ('PROVÁVEL (configuração recomendada da planilha)', 93995.28, 161061.40),
    ('MÁXIMO (ElectroCraft com freio, reComputer, Jetson kit)', 130907.32, 228153.20),
]

POR_CATEGORIA = [
    ('SENSORES', 42096.00, 44.8), ('TRAÇÃO', 22328.16, 23.8), ('ENERGIA', 13036.15, 13.9),
    ('COMPUTAÇÃO', 12219.96, 13.0), ('ESTRUTURA', 2585.01, 2.8), ('ELÉTRICA', 1730.00, 1.8),
]

# ---------------------------------------------------------------- conciliação
# (gravidade, assunto, o que a BOM de compras diz, o que o projeto mecânico exige, consequência)
DIVERGENCIAS = [
    ('CRÍTICA', 'Motor-roda',
     'Recomenda ZLTECH ZLLG80ASM800 a R$ 2.215/un; a página do fabricante mostra R$ 1.133,68 '
     '(R$ 1.028,22 acima de 200 peças) — a BOM paga R$ 4.326,64 a mais no conjunto',
     'Todo o suporte S-01/S-02/S-03, a furação Ø88 + 7 × M4 no PCD 95, a face Ø105,7, a bitola de 470 e '
     'o vão livre foram dimensionados para o MPW86',
     'Economiza R$ 21.165 com o preço real, mas invalida a folha 07 e a interface do chassi. '
     'A montagem é por eixo (não flange): a S-02 perde o bore Ø88 e os 7 furos. Ver folha 27.'),
    ('CRÍTICA', 'Freio',
     'O freio eletromagnético (EMB) do ZLTECH é opcional de fábrica e não está pedido na planilha; '
     'o relé Pilz PNOZ s4 cobre a lógica de parada, não o freio',
     'A baseline exige freio aplicado por mola, com 15 a 30 N·m por roda para segurar em rampa de 30°',
     'Sem freio mecânico, o rover não pode estacionar em declive. É requisito de segurança, não de conforto.'),
    ('ALTA', 'Estrutura — cobertura errada, não valor errado',
     'R$ 2.585 no total, com 4 linhas de material e 2 de serviço',
     'Material completo (8 perfis + 11 espessuras) custa cerca de R$ 1.176 pela própria base de preço '
     'da BOM — mesma ordem de grandeza do que ela já reserva',
     'A BOM compra 6 barras de tubo 30×30 onde bastam 2, e esse excesso mascara a falta dos outros '
     'perfis e chapas. Corrigir a lista quase não muda o total do material.'),
    ('CRÍTICA', 'Serviços de fabricação não cotados',
     'Apenas "corte laser + dobra R$ 800" e "impressão 3D R$ 500"',
     '52,9 m de corte a laser (433 furos) · 13,6 m de cordão TIG · 24 peças usinadas · 4,66 m² de '
     'tratamento de superfície · 176 porcas-rebite · 3 gabaritos · inspeção dimensional',
     'É aqui que está o buraco do orçamento, não no material. Pedir preço por metro de corte e por '
     'metro de cordão deixa as propostas comparáveis.'),

    ('MÉDIA', 'Carenagens por impressão 3D',
     'Linha de R$ 500 para "impressão 3D das carenagens"',
     'As carenagens K-01 a K-06 são chapa de alumínio 5052 (2 e 1,2 mm), cortadas a laser',
     'Ou a linha se refere às carenagens anti-galho N-09 (UHMW-PE), ou há divergência de conceito.'),
    ('MÉDIA', 'Célula de bateria',
     'Célula EVE 105 Ah (R$ 582/un)', 'Baseline usa EVE LF100LA, 100 Ah, 36,5 kg no conjunto',
     'Muda massa e dimensão da caixa — que já é pendência. Reconferir o CG depois de definir.'),
    ('BAIXA', 'Compra de tubo 30×30×2',
     '6 barras de 6 m (36 m) por R$ 50 a barra', 'O projeto consome 8,94 m — 2 barras bastam',
     'Sobra de 27 m. Verificar também o preço: R$ 50 por barra de 6 m de alumínio está abaixo da '
     'ordem de grandeza do mercado (a própria planilha cota um tarugo de UHMW-PE por R$ 270).'),
    ('BAIXA', 'E-STOP',
     'E-STOP remoto sem fio (R$ 1.799) + relé Pilz', 'O caderno desenha o botão Ø22 físico na tampa '
     'traseira (E-10/E-11), que a baseline exige',
     'Os dois se somam: o botão físico é requisito da baseline, o remoto é adicional.'),
]


def faltantes(dados):
    """Material e serviços que o projeto exige e a BOM de compras não cobre."""
    tub = dados.tubos()
    area = dados.area_chapa()
    cobertos_perfil = ('Tubo quadrado 30×30×2', 'Tubo Ø25×2 × 1436')
    linhas = []
    for k, v in sorted(tub.items()):
        if k in cobertos_perfil:
            linhas.append(['Perfil', k, f'{v:.2f} m'.replace('.', ','), 'coberto',
                           'Conferir quantidade: a BOM compra bem mais que o necessário'])
        else:
            linhas.append(['Perfil', k, f'{v:.2f} m'.replace('.', ','), 'FALTA', ''])
    for (m, e), v in sorted(area.items()):
        estado = 'coberto' if (m == 'Al 6061-T6' and e == '3') else 'FALTA'
        linhas.append(['Chapa', f'{m} · {e} mm', f'{v:.3f} m²'.replace('.', ','), estado, ''])
    for serv, obs in (
            ('Usinagem da face de montagem do MPW86 (4 peças)', 'Ra 3,2 · planicidade 0,1 · após solda'),
            ('Usinagem de buchas Q-05 e espaçadores N-03 (20 peças)', 'Torno'),
            ('Soldagem TIG — quadro', 'ER5356, filete a2, em gabarito'),
            ('Soldagem TIG — 4 suportes do motor-roda', 'Filete a3'),
            ('Soldagem TIG — 2 módulos da gaiola', 'Filete a2'),
            ('Gabaritos de soldagem', 'Custo único'),
            ('Tratamento de superfície (anodização ou pintura)', '3 opções no pacote'),
            ('Instalação de 176 porcas-rebite', 'Depois do acabamento'),
            ('Inspeção dimensional das 9 cotas críticas', 'Entregável obrigatório'),
            ('Fixadores: 740 peças em 23 códigos inox A4', 'A BOM tem uma linha única de R$ 300')):
        linhas.append(['Serviço/insumo', serv, '1 conjunto', 'FALTA', obs])
    return linhas
