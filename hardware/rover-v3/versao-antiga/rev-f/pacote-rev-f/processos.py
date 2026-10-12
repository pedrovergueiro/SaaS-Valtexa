"""Classificação de fabricação de cada item do VALTEXA ROVER V3 — Rev E.

Cada item recebe: processo primário, operações seguintes, acabamento e observação.
O que não está definido na Rev E nem decorre da geometria aparece como 'A DEFINIR'.

Categorias de origem (usadas em todo o pacote):
  CONFIRMADO  valor presente na baseline Rev E ou no caderno VTX-RV3-CG-F
  DERIVADO    calculado a partir da geometria/valores confirmados
  PROPOSTA    escolha de engenharia deste pacote, sujeita a aprovação
  A DEFINIR   ausente — depende de engenheiro, fabricante ou ensaio
"""

# --------------------------------------------------------------- processos
LASER = 'Corte a laser / CNC'
SERRA = 'Corte de tubo (serra)'
BARRA = 'Corte de barra/perfil'
TORNO = 'Usinagem (torno)'
FRESA = 'Usinagem (fresa)'
DOBRA = 'Dobra'
COMPRA = 'Componente comercial'
PLAST = 'Usinagem de plástico'

# item: (processo primário, operações seguintes, acabamento, observação)
PROC = {
    # ---- Q · quadro estrutural soldado
    'Q-01': (SERRA, ['Solda TIG no gabarito'], 'Conforme acabamento do conjunto',
             'Corte a 90°, sem rebarba. 4 peças de 1.042 mm.'),
    'Q-02': (SERRA, ['Solda TIG'], '—', 'Corte a 90°. 4 peças de 536 mm.'),
    'Q-03': (SERRA, ['Solda TIG'], '—', 'Corte a 90°. 4 peças de 536 mm.'),
    'Q-04': (SERRA, ['Solda TIG'], '—', '16 peças de 30 mm entre os anéis.'),
    'Q-05': (TORNO, ['Furo Ø8,5 passante'], '—',
             'Bucha de compressão: barra Ø12, 30 mm. Torneada ou serrada + furada.'),
    'Q-06': (LASER, ['Solda TIG nas pontas dos tubos'], '—', 'Tampa 30×30 em chapa 2 mm.'),
    # ---- C · chapa de fundo
    'C-01': (LASER, ['Instalação de porcas-rebite'], 'Conforme opção A/B/C da folha 02',
             'Chapa 1.046×596×2 (5052-H32) com 104 furos e 1 abertura 70×120.'),
    'C-02': (BARRA, ['Furação Ø6,6 e Ø4,9'], '—',
             'Cantoneira 40×40×4 comercial, cortada em 592 mm.'),
    # ---- S · suporte do motor-roda (4 conjuntos soldados)
    'S-01': (LASER, ['Solda TIG a3 com S-02 e S-03'], '—', 'Chapa 6 mm.'),
    'S-02': (LASER, ['Solda TIG', 'Usinagem da face de montagem após solda'], 'Ra 3,2 na face B',
             'Chapa 10 mm. Furo Ø88 e 7 furos Ø4,5 no PCD 95 — furação conforme interface do MPW86 '
             '(A VALIDAR com a ElectroCraft).'),
    'S-03': (LASER, ['Solda TIG a3'], '—', 'Nervura em chapa 8 mm, 2 por suporte.'),
    # ---- G · gaiola de proteção
    'G-01': (SERRA, ['Solda TIG a2'], '—', 'Tubo 20×20×1,5 — 4 peças de 490 mm.'),
    'G-02': (SERRA, ['Solda TIG a2'], '—', '4 peças de 556 mm.'),
    'G-03': (SERRA, ['Solda TIG a2'], '—', '4 peças de 556 mm.'),
    'G-04': (SERRA, ['Solda TIG a2'], '—', '12 montantes de 34 mm.'),
    'G-05': (LASER, ['Solda TIG a3 no montante', 'Furação após solda, com gabarito'], '—',
             'Sapata 70×30×3. Furar depois de soldada, pelo gabarito tirado do quadro.'),
    'G-06': (LASER, ['Instalação dos coxins'], '—', 'Suporte do LiDAR, chapa 5 mm.'),
    'G-07': (LASER, ['Solda TIG'], '—', 'Tampa 20×20 em chapa 1,5 mm.'),
    'G-08': (COMPRA, [], '—', 'Coxim antivibração Ø15×10 M4, NBR 60 Shore A.'),
    # ---- K · carenagens e tampas
    'K-01': (LASER, [], 'Conforme opção A/B/C', 'Chapa 2 mm (5052-H32). 4 peças (2 E + 2 D espelhadas).'),
    'K-02': (LASER, [], '—', 'Carenagem frontal com janela da câmera (140×32) e 2 furos Ø20 dos faróis.'),
    'K-03': (LASER, [], '—', 'Carenagem traseira.'),
    'K-04': (LASER, [], '—', 'Tampa dianteira 1,2 mm, com furação do suporte do LiDAR.'),
    'K-05': (LASER, [], '—', 'Tampa traseira 1,2 mm, com recorte do E-STOP e furação da antena GNSS.'),
    'K-06': (LASER, [], '—', 'Faixa central 1,2 mm.'),
    # ---- M · mastros
    'M-01': (SERRA, ['Furação Ø6,6 (2×)', 'Solda TIG a4 no reforço'], '—',
             'Tubo Ø34×4,5 × 180. Furar as travas depois de soldada, com a haste montada.'),
    'M-02': (LASER, ['Solda TIG a3 na longarina'], '—', 'Chapa 56×40×6 com furo central Ø6.'),
    'M-10': (SERRA, ['Furação Ø6,6 e Ø12'], '—',
             'Tubo Ø25×2 × 1.436. Furos das travas e das entradas de cabo.'),
    'M-11': (SERRA, [], '—', 'Tubo UHMW-PE Ø29/Ø25 em 3 segmentos por lado (202, 424 e 460 mm).'),
    'M-12': (PLAST, [], '—', 'Ponta cônica Ø29×40 em UHMW-PE, torneada.'),
    'M-20': (LASER, ['Quebra de cantos R5'], '—', 'Suporte de câmera 90×70×6, 6 peças iguais.'),
    # ---- B · retenção da bateria
    'B-01': (BARRA, ['Rasgo 26×6 (laser ou fresa)', 'Furação Ø6,6'], '—',
             'Cantoneira 40×40×4 × 150, 4 peças.'),
    # ---- E · eletrônica e E-STOP
    'E-01': (LASER, [], '—', 'Bandeja lateral 380×54×2 (5052-H32).'),
    'E-02': (LASER, [], '—', 'Bandeja de extremidade 120×145×2 — 4 peças.'),
    'E-10': (LASER, [], '—', 'Reforço do E-STOP, chapa 3 mm com recorte Ø22,5.'),
    'E-11': (LASER, ['2 dobras a 90°'], '—',
             'Barra 50×4 dobrada em U. Raio e sequência de dobra: A DEFINIR PELO FABRICANTE.'),
    # ---- N · interfaces de sensores e sinalização
    'N-01': (LASER, [], '—', 'Suporte da antena GNSS, chapa 5 mm.'),
    'N-02': (LASER, ['Fresamento da face de montagem'], 'Face plana e alinhada a X/Y (0,5°)',
             'Berço do IMU: a face define o alinhamento do sensor com o referencial do veículo.'),
    'N-03': (TORNO, [], '—', 'Espaçador Ø12 com furo Ø6,6, 54 mm — 4 peças.'),
    'N-04': (FRESA, ['Quebra de arestas'], 'Polido nas bordas',
             'Policarbonato 3 mm. Fresa CNC ou serra — laser não é recomendado em PC (queima a borda).'),
    'N-05': (BARRA, ['Furação das pontas'], '—',
             'Barra Ø8 × 160. Fixação por parafuso ou solda: A DEFINIR PELO ENGENHEIRO.'),
    'N-06': (LASER, ['1 dobra a 90° (A VALIDAR)'], '—',
             'Aba do suporte da câmera de raiz. Pode ser cortada inteira ou cortada + dobrada.'),
    'N-07': (LASER, [], '—', 'Face inclinada (≈24°) da câmera de raiz, chapa 3 mm.'),
    'N-08': (LASER, [], '—', 'Reforço do farol, chapa 2 mm com furo Ø20.'),
    'N-09': (PLAST, ['Conformação da caixa'], '—',
             'Carenagem anti-galho em UHMW-PE 3 mm. Processo (fresagem de bloco, dobra a quente ou '
             'termoformagem): A DEFINIR COM O FABRICANTE.'),
}

# conjuntos soldados: (código do conjunto, nome, itens, processo, observação)
SOLDADOS = [
    ('VTX-RV3-SOLD-001', 'Quadro estrutural', ['Q-01', 'Q-02', 'Q-03', 'Q-04', 'Q-06', 'M-01', 'M-02'],
     'TIG · ER5356 · filete contínuo a2 nos tubos, a3/a4 na base do mastro',
     'Soldar em gabarito, sequência balanceada. Diagonais do quadro ≤ 2 mm de diferença.'),
    ('VTX-RV3-SOLD-002', 'Suporte do motor-roda (4×)', ['S-01', 'S-02', 'S-03'],
     'TIG · ER5356 · filete a3',
     'Soldar e depois usinar a face de montagem. 2 conjuntos esquerdos + 2 direitos (espelhados).'),
    ('VTX-RV3-SOLD-003', 'Módulo da gaiola (2×)', ['G-01', 'G-02', 'G-03', 'G-04', 'G-05', 'G-07'],
     'TIG · ER5356 · filete a2',
     'Os dois módulos são idênticos. Sapatas coplanares ≤ 0,5 mm; furar depois da solda.'),
]

# grupos de compra de matéria-prima (o que o fornecedor precisa comprar)
MATERIA_PRIMA = [
    ('Tubo quadrado 30×30×2', 'Al 6061-T6', 'ASTM B221', '2 barras de 6 m', 'CONFIRMADO'),
    ('Tubo quadrado 20×20×1,5', 'Al 6061-T6', 'ASTM B221', '2 barras de 6 m', 'CONFIRMADO'),
    ('Tubo redondo Ø34×4,5', 'Al 6061-T6', 'ASTM B221', '0,4 m', 'CONFIRMADO'),
    ('Tubo redondo Ø25×2', 'Al 6061-T6', 'ASTM B221', '3,0 m', 'CONFIRMADO'),
    ('Tubo redondo Ø12 (furo Ø6,6)', 'Al 6061-T6', '—', '0,3 m', 'CONFIRMADO'),
    ('Barra redonda Ø12', 'Al 6061-T6', '—', '0,5 m', 'CONFIRMADO'),
    ('Barra redonda Ø8', 'Al 6061-T6', '—', '0,4 m', 'CONFIRMADO'),
    ('Cantoneira 40×40×4', 'Al 6061-T6', '—', '1,8 m', 'CONFIRMADO'),
    ('Barra chata 50×4', 'Al 6061-T6', '—', '0,3 m', 'CONFIRMADO'),
    ('Chapa 10 mm', 'Al 6061-T6', 'ASTM B209', 'retalho 260×430', 'DERIVADO'),
    ('Chapa 8 mm', 'Al 6061-T6', 'ASTM B209', 'retalho 200×400', 'DERIVADO'),
    ('Chapa 6 mm', 'Al 6061-T6', 'ASTM B209', 'retalho 400×600', 'DERIVADO'),
    ('Chapa 5 mm', 'Al 6061-T6', 'ASTM B209', 'retalho 150×250', 'DERIVADO'),
    ('Chapa 3 mm', 'Al 6061-T6', 'ASTM B209', 'retalho 300×400', 'DERIVADO'),
    ('Chapa 2 mm', 'Al 6061-T6', 'ASTM B209', 'retalho 120×120', 'DERIVADO'),
    ('Chapa 2 mm', 'Al 5052-H32', 'ASTM B209', '≈ 1,05 × 1,30 m', 'CONFIRMADO'),
    ('Chapa 1,5 mm', 'Al 6061-T6', 'ASTM B209', 'retalho 100×100', 'DERIVADO'),
    ('Chapa 1,2 mm', 'Al 5052-H32', 'ASTM B209', '≈ 1,00 × 0,60 m', 'CONFIRMADO'),
    ('Chapa de policarbonato 3 mm', 'PC', '—', 'retalho 200×200', 'PROPOSTA'),
    ('Tubo UHMW-PE Ø29/Ø25', 'UHMW-PE', '—', '3,0 m', 'CONFIRMADO'),
    ('Bloco/chapa UHMW-PE 3 mm', 'UHMW-PE', '—', 'a definir pelo processo da N-09', 'A DEFINIR'),
]

TRATAMENTOS = [
    ('A', 'Natural, desengraxado', 'Sem custo adicional', 'Protótipo'),
    ('B', 'Anodização preta ≥ 15 µm', 'Exige furos de dreno em cavidades fechadas',
     'Recomendado para campo'),
    ('C', 'Pintura eletrostática preta sobre conversão química', 'Mascarar faces de montagem e roscas',
     'Alternativa à anodização'),
]


# folhas do caderno VTX-RV3-CG-F onde cada item está desenhado
FOLHA = {}
for _k, _v in {
    '04, 06': ['Q-01', 'Q-02', 'Q-03', 'Q-04', 'Q-05', 'Q-06'],
    '08, 11': ['C-01'], '08': ['C-02'], '07, 11': ['S-01', 'S-02', 'S-03'],
    '09, 12': ['G-01', 'G-02', 'G-03', 'G-04'], '09, 11, 12': ['G-05'],
    '10, 11': ['G-06'], '11, 12': ['G-07'], '10': ['G-08'],
    '11': ['K-01', 'K-02', 'K-03', 'K-04', 'K-05', 'K-06'],
    '17': ['M-01', 'M-02'], '18': ['M-10', 'M-11', 'M-12'], '19': ['M-20'],
    '20': ['B-01'], '21': ['E-01', 'E-02', 'E-10', 'E-11'],
    '22': ['N-01', 'N-02', 'N-03', 'N-04', 'N-05', 'N-06', 'N-07', 'N-08', 'N-09'],
}.items():
    for _i in _v:
        FOLHA[_i] = _k
