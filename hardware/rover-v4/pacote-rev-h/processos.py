"""Classificação de fabricação de cada item do VALTEXA ROVER V4 — Rev H.

Cada item recebe: processo primário, operações seguintes, acabamento e observação.
O que não está definido na baseline nem decorre da geometria aparece como 'A DEFINIR'.

Categorias de origem (usadas em todo o pacote):
  CONFIRMADO  valor presente na baseline Rev E ou no caderno VTX-RV4-CG-H
  DERIVADO    calculado a partir da geometria/valores confirmados
  PROPOSTA    escolha de engenharia deste pacote, sujeita a aprovação
  A DEFINIR   ausente — depende de engenheiro, fabricante ou ensaio
"""

import modelo as M

_BAINHA = M._faixas_bainha()
_BAINHA_TXT = ', '.join(f'{zb - za:.0f}' for za, zb in _BAINHA)
_BAINHA_TOTAL_M = 2 * sum(zb - za for za, zb in _BAINHA) / 1000.0
_HASTE_M = 2 * (M.Z_TOTAL - M.Z_REF_M[1]) / 1000.0


def _n(v):
    return M._n(v)


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
    # ---- W · suspensão pneumática independente (Rev H)
    # Grupo em AÇO na maior parte, e isso muda a cotação: eletrodo, pré-aquecimento e
    # tratamento superficial são outros. Ver folhas 28 a 31 do caderno.
    'W-01': (SERRA, ['Fresa: alojamento Ø34 e rasgo 24×34', 'Alargador Ø12 H7',
                     'Solda TIG/MIG com W-02, W-03 e W-04',
                     'Alargador Ø23 H7 APÓS a solda'],
             'Zincado ou pintado',
             'Tubo retangular 40×30×3 em aço 1020, 4 peças de 182 mm. O alargamento do '
             'alojamento da bucha é obrigatoriamente posterior à solda.'),
    'W-02': (LASER, ['Usinagem do Ø88 H8 e dos 7 furos Ø4,5 no PCD 95',
                     'Solda TIG/MIG com W-01 e W-03',
                     'Faceamento da face de montagem APÓS a solda'],
             'Ra 3,2 na face B · planeza 0,1',
             'Chapa 10 mm em aço A36. É a sugestão 2.4 do fabricante, implementada — a peça '
             'passou a ser de suspensão e cicla com o terreno. Planicidade admitida pelo '
             'motor A VALIDAR com a ElectroCraft (P-04).'),
    'W-03': (LASER, ['Solda TIG/MIG a4 em todo o contorno'], 'Zincado ou pintado',
             'Chapa 6 mm em aço A36. Tampa-gusset: fecha a ponta do tubo e amarra o braço '
             'à chapa W-02.'),
    'W-04': (TORNO, ['Pré-furo Ø22,7 com sobremetal', 'Solda TIG/MIG a4 atravessando o braço'],
             'Zincado ou pintado',
             'Barra Ø34 em aço 1045, 4 peças de 38 mm. Alojamento final Ø23 H7 alargado '
             'depois da solda, junto com W-01.'),
    'W-05': (LASER, ['Alargador Ø20 H7', 'Solda TIG/MIG a4 em W-06',
                     'Alargador final dos dois furos no mesmo passe'],
             'Zincado ou pintado',
             'Chapa 6 mm em aço A36, 8 peças. Coaxialidade 0,05 entre as duas orelhas do '
             'mesmo pivô — alargar as duas juntas.'),
    'W-06': (LASER, ['Solda TIG/MIG a4 com as duas orelhas W-05',
                     'Faceamento da face de assento APÓS a solda'],
             'Zincado ou pintado · isolar do alumínio',
             'Chapa 8 mm em aço A36. Encosta em chapa de alumínio: exige barreira galvânica '
             'e arruela de nylon nos parafusos.'),
    'W-07': (TORNO, ['Duas ranhuras DIN 471 para Ø20'], 'Ra 0,8 no diâmetro',
             'Barra Ø20 h7 em inox 304, 4 peças de 66 mm.'),
    'W-08': (TORNO, ['Faceamento da face de assento do fole', 'Rosca M12×1,75 passante',
                     'Solda TIG/MIG a4 com as duas orelhas W-09'],
             'Ra 1,6 na face de assento',
             'Disco Ø92×8 em aço A36. Articulado: é o que mantém o fole axial enquanto o '
             'braço gira 31°.'),
    'W-09': (LASER, ['Alargador Ø12 H7', 'Solda TIG/MIG a4 em W-08'], 'Zincado ou pintado',
             'Chapa 8 mm em aço A36, 8 peças.'),
    'W-10': (TORNO, ['Duas ranhuras DIN 471 para Ø12'], 'Ra 0,8 no diâmetro',
             'Barra Ø12 h7 em inox 304, 4 peças de 42 mm.'),
    'W-11': (LASER, ['Faceamento das duas faces', 'Rosca M12×1,75 passante'],
             'Anodização dura 15 µm',
             'Chapa 10 mm em Al 6061-T6. Viga biapoiada nas travessas do anel inferior.'),
    'W-12': (TORNO, ['Solda TIG a3 estanque com a flange W-13',
                     'Ensaio de bolha a 0,5 bar'],
             'Anodização dura 15 µm',
             'Tubo Ø100×3 em Al 6061-T6, 4 peças de 32 mm. O conjunto soldado com W-13 é '
             'peça de VEDAÇÃO: ensaio de estanqueidade antes de montar.'),
    'W-13': (LASER, ['Faceamento das duas faces de junta', 'Solda TIG a3 estanque em W-12'],
             'Anodização dura 15 µm · planeza 0,1 nas faces de junta',
             'Chapa 4 mm em Al 6061-T6. Círculo Ø140 CORTADO em |X| 470: o círculo inteiro '
             'encontraria o berço do pivô.'),
    'W-14': (COMPRA, [], '—',
             'Cabo de aço inox Ø4 × 112 mm com dois terminais de olhal. Limitador de '
             'extensão — define o fim de curso de distensão do fole.'),
    'W-18': (LASER, ['Dobra das abas'], 'Natural ou anodizado',
             'Chapa 2 mm em Al 5052-H32. Bandeja do grupo pneumático.'),
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
    'K-02': (LASER, [], '—', 'Carenagem frontal com 2 furos Ø20 dos faróis. NÃO tem janela de câmera: a frontal (C7) fica sob o chassi.'),
    'K-03': (LASER, [], '—', 'Carenagem traseira.'),
    'K-04': (LASER, [], '—', 'Tampa dianteira 1,2 mm, com furação do suporte do LiDAR.'),
    'K-05': (LASER, [], '—', 'Tampa traseira 1,2 mm, com recorte do E-STOP e furação da antena GNSS.'),
    'K-06': (LASER, [], '—', 'Faixa central 1,2 mm.'),
    # ---- M · mastros
    'M-01': (SERRA, ['Alargador Ø32 H8 no furo da haste', 'Furação Ø6,6 (2×) das travas',
                     'Furo Ø20 da saída lateral dos cabos', 'Solda TIG a4 no reforço'], '—',
             f'Tubo Ø{_n(M.D_LUVA)}×{_n(M.E_LUVA)} × {_n(M.L_LUVA)}. Furar as travas depois de soldada, com a '
             'haste montada. A saída lateral Ø20 (passa-cabo F-59) está no texto do caderno, não no modelo.'),
    'M-02': (LASER, ['Solda TIG a3 na longarina'], '—', 'Chapa 56×40×6 com furo central Ø6.'),
    'M-10': (SERRA, ['Furação Ø6,6 (travas) e Ø12 (entradas de cabo)'], '—',
             f'Tubo Ø{_n(M.D_MASTRO)}×{_n(M.E_MASTRO)} × {_n(M.Z_TOTAL - M.Z_REF_M[1])}. 2× Ø6,6 das travas e '
             'entradas de cabo Ø12, 30 mm abaixo de cada posto (3 de OAK-D; mais 2 se houver térmicas). '
             'A parede de 3 mm é o que fecha o requisito de 7,5 Hz com o mastro cheio (folha 36).'),
    'M-11': (SERRA, [], '—', f'Tubo UHMW-PE Ø{_n(M.D_BAINHA)}/Ø{_n(M.D_MASTRO)} em {len(_BAINHA)} trechos por '
             f'mastro ({_BAINHA_TXT} mm), parado 40 mm antes e depois de cada posto.'),
    'M-12': (PLAST, [], '—', f'Ponta cônica Ø{_n(M.D_BAINHA)}×40 em UHMW-PE, torneada. Sai quando a antena entra (T-10).'),
    # ---- T · interface modular de sensores VMS-60 (novo no V4)
    'T-01': (LASER, ['Fresa: canal semicircular do tubo', 'Serrilhar o canal',
                     'Anodizar'],
             'Ra 6,3 no canal · anodização dura 15 µm',
             'Chapa 12 em Al 6061-T6, 12 peças (2 metades × 6 postos de OAK-D; mais 8 se as 4 posições '
             'térmicas forem montadas). O canal '
             'é Ø32 ou Ø42 conforme a altura do posto. A serrilha é o que impede a '
             'braçadeira de escorregar sob vibração.'),
    'T-02': (LASER, ['Rosquear os 4 furos M5', 'Alargador Ø8 H7 e Ø6 H7', 'Alargador dos 7 furos de índice',
                     'Faceamento da face VMS', 'Prensagem dos dois pinos'],
             'Ra 1,6 nos alojamentos · planeza 0,05 na face VMS',
             'Chapa 10 em Al 6061-T6, 6 peças (mais 4 opcionais). Os 4 furos do padrão VMS são roscados M5 '
             '(macho Ø4,2): é neles que o adaptador se prende. A COTA CRÍTICA é a distância entre os dois '
             'alojamentos de pino: 26 ± 0,02. É ela, e não o diâmetro dos pinos, que '
             'determina a repetibilidade angular da interface.'),
    'T-03': (LASER, ['Alargador Ø8 H7 e Ø6 H7', 'Anodizar'],
             'Ra 1,6 nos alojamentos',
             'Chapa 6 em Al 6061-T6, 9 peças (uma por câmera). É a ÚNICA peça que muda '
             'quando o modelo de sensor muda. A furação do sensor é A VALIDAR (P-06).'),
    'T-04': (LASER, ['Alargador Ø8 H7 e Ø6 H7', 'Anodizar'], 'Ra 1,6 nos alojamentos',
             'Chapa 6 em Al 6061-T6, até 4 peças — OPCIONAL (módulo térmico removível). SEM furação de '
             'sensor: depende do modelo da câmera térmica (P-30), e a peça não sai da oficina sem ela. '
             'Os 4 furos Ø5,5 recebem parafusos M5 imperdíveis de aperto manual (folha 41).'),
    'T-10': (TORNO, ['Tornear Ø26 g6 × 60', 'Furo axial Ø10', 'Furo transversal Ø6,6 da trava'],
             'Anodização dura 15 µm',
             'Barra Ø26 em Al 6061-T6, até 2 peças — OPCIONAL (antena GNSS no topo do mastro). A interface '
             'da antena (rosca 5/8"-11 UNC) é A VALIDAR com o modelo escolhido (P-37): NÃO usinar antes.'),
    'T-05': (PLAST, ['Furar os 2 passantes de fixação'], '—',
             'UHMW-PE 6 mm, 6 peças (mais 4 opcionais). Protetor SACRIFICIAL: rompe antes do adaptador. '
             'Dimensionado pelo campo de visão da câmera, não por semelhança.'),
    'T-06': (LASER, ['Alargador Ø8 H7 e Ø6 H7'], 'Ra 1,6 nos alojamentos',
             'Chapa 4 em Al 6061-T6, 2 peças: berços das câmeras frontal e traseira, sob '
             'a chapa de fundo.'),
    'T-07': (LASER, ['Dobra das abas de rigidez'], 'Natural ou anodizado',
             f'Chapa {_n(M.E_BERCO_SAT)} em Al 5052-H32. Berço do terminal satelital — PROVISÃO: o envelope '
             'é requisito, nenhum terminal foi escolhido.'),
    'T-09': (LASER, ['Alargador Ø8 H7 e Ø6 H7'], 'Ra 1,6 nos alojamentos',
             'Chapa 10 em Al 6061-T6: berço VMS da câmera de raiz, dentro do '
             'compartimento, acima da janela de policarbonato.'),
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
}

# conjuntos soldados: (código do conjunto, nome, itens, processo, observação)
SOLDADOS = [
    ('VTX-RV4-SOLD-001', 'Quadro estrutural', ['Q-01', 'Q-02', 'Q-03', 'Q-04', 'Q-06', 'M-01', 'M-02'],
     'TIG · ER5356 · filete contínuo a2 nos tubos, a3/a4 na base do mastro',
     'Soldar em gabarito, sequência balanceada. Diagonais do quadro ≤ 2 mm de diferença.'),
    ('VTX-RV4-SOLD-002', 'Canto de suspensão — braço (4×)',
     ['W-01', 'W-02', 'W-03', 'W-04'],
     'MIG/MAG ou TIG · AWS ER70S-6 · filete a4',
     'AÇO, não alumínio: eletrodo e procedimento diferentes do resto do pacote. Soldar em '
     'dispositivo e SÓ DEPOIS usinar: faceamento da chapa W-02 e alargamento Ø23 H7 do '
     'alojamento da bucha. 2 conjuntos esquerdos + 2 direitos. Ver folhas 28, 29 e 33.'),
    ('VTX-RV4-SOLD-004', 'Canto de suspensão — torre do pivô (4×)', ['W-05', 'W-06'],
     'MIG/MAG ou TIG · AWS ER70S-6 · filete a4',
     'AÇO. Soldar as duas orelhas no berço em dispositivo e alargar os dois furos Ø20 H7 '
     'no mesmo passe: coaxialidade 0,05. Ver folha 30.'),
    ('VTX-RV4-SOLD-005', 'Canto de suspensão — prato do fole (4×)', ['W-08', 'W-09'],
     'MIG/MAG ou TIG · AWS ER70S-6 · filete a4',
     'AÇO. Eixo do pino paralelo à face do disco em 0,1. Ver folha 31.'),
    ('VTX-RV4-SOLD-006', 'Colar de vedação do fole (4×)', ['W-12', 'W-13'],
     'TIG · ER5356 · filete a3 ESTANQUE',
     'Alumínio. Peça de vedação: cordão contínuo e ensaio de bolha a 0,5 bar em água, sem '
     'bolha em 60 s, ANTES de montar. Ver folhas 31 e 35.'),
    ('VTX-RV4-SOLD-003', 'Módulo da gaiola (2×)', ['G-01', 'G-02', 'G-03', 'G-04', 'G-05', 'G-07'],
     'TIG · ER5356 · filete a2',
     'Os dois módulos são idênticos. Sapatas coplanares ≤ 0,5 mm; furar depois da solda.'),
]

# grupos de compra de matéria-prima (o que o fornecedor precisa comprar)
MATERIA_PRIMA = [
    ('Tubo quadrado 30×30×2', 'Al 6061-T6', 'ASTM B221', '2 barras de 6 m', 'CONFIRMADO'),
    ('Tubo quadrado 20×20×1,5', 'Al 6061-T6', 'ASTM B221', '2 barras de 6 m', 'CONFIRMADO'),
    (f'Tubo redondo Ø{_n(M.D_LUVA)}×{_n(M.E_LUVA)}', 'Al 6061-T6', 'ASTM B221', '0,4 m', 'DERIVADO'),
    (f'Tubo redondo Ø{_n(M.D_MASTRO)}×{_n(M.E_MASTRO)}', 'Al 6061-T6', 'ASTM B221',
     f'{_HASTE_M:.1f} m (2 hastes)'.replace('.', ','), 'DERIVADO'),
    ('Barra redonda Ø26 — OPCIONAL (T-10)', 'Al 6061-T6', '—', '0,15 m', 'DERIVADO'),
    ('Chapa 12 mm', 'Al 6061-T6', 'ASTM B209', 'retalho 200×300', 'DERIVADO'),
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
    (f'Tubo UHMW-PE Ø{_n(M.D_BAINHA)}/Ø{_n(M.D_MASTRO)}', 'UHMW-PE', '—',
     f'{_BAINHA_TOTAL_M:.1f} m ({2 * len(_BAINHA)} trechos)'.replace('.', ','), 'DERIVADO'),
    ('Chapa UHMW-PE 6 mm (T-05)', 'UHMW-PE', '—', 'retalho 300×200', 'DERIVADO'),
    ('Chapa 4 mm', 'Al 5052-H32', 'ASTM B209', 'retalho 300×260', 'DERIVADO'),
    # ---- aço, novo na Rev H (grupo W). É outra cadeia de compra e outro processo de solda.
    ('Tubo retangular 40×30×3', 'Aço 1020', 'ASTM A513', '1,0 m', 'DERIVADO'),
    ('Chapa 10 mm', 'Aço A36', 'ASTM A36', 'retalho 300×400', 'DERIVADO'),
    ('Chapa 8 mm', 'Aço A36', 'ASTM A36', 'retalho 250×350', 'DERIVADO'),
    ('Chapa 6 mm', 'Aço A36', 'ASTM A36', 'retalho 250×300', 'DERIVADO'),
    ('Barra redonda Ø34', 'Aço 1045', 'ASTM A108', '0,2 m', 'DERIVADO'),
    ('Barra redonda Ø20', 'Inox 304', 'ASTM A276', '0,3 m', 'DERIVADO'),
    ('Barra redonda Ø12', 'Inox 304', 'ASTM A276', '0,2 m', 'DERIVADO'),
    ('Tubo redondo Ø100×3', 'Al 6061-T6', 'ASTM B221', '0,2 m', 'DERIVADO'),
    ('Chapa 4 mm', 'Al 6061-T6', 'ASTM B209', 'retalho 300×300', 'DERIVADO'),
]

TRATAMENTOS = [
    ('A', 'Natural, desengraxado', 'Sem custo adicional', 'Protótipo'),
    ('B', 'Anodização preta ≥ 15 µm', 'Exige furos de dreno em cavidades fechadas',
     'Recomendado para campo'),
    ('C', 'Pintura eletrostática preta sobre conversão química', 'Mascarar faces de montagem e roscas',
     'Alternativa à anodização'),
    ('D', 'Zincagem a quente — SÓ para peça de aço (grupo W)',
     'Deforma peça soldada de parede fina; cotar com a ressalva', 'Aço do grupo W'),
]


# folhas do caderno VTX-RV4-CG-H onde cada item está desenhado
FOLHA = {}
for _k, _v in {
    '04, 06': ['Q-01', 'Q-02', 'Q-03', 'Q-04', 'Q-05', 'Q-06'],
    '08, 11': ['C-01'], '08': ['C-02'],
    '07, 28, 33': ['W-01'], '07, 29, 33': ['W-02'], '07, 28': ['W-03', 'W-04'],
    '07, 30': ['W-05', 'W-06', 'W-07'],
    '07, 31': ['W-08', 'W-09', 'W-10', 'W-11', 'W-12', 'W-13', 'W-14'],
    '07, 35': ['W-15', 'W-16', 'W-17'], '21, 35': ['W-18'],
    '09, 12': ['G-01', 'G-02', 'G-03', 'G-04'], '09, 11, 12': ['G-05'],
    '10, 11': ['G-06'], '11, 12': ['G-07'], '10': ['G-08'],
    '11': ['K-01', 'K-02', 'K-03', 'K-04', 'K-05', 'K-06'],
    '17': ['M-01', 'M-02'], '18, 36': ['M-10', 'M-11', 'M-12'],
    '19, 37': ['T-01', 'T-02', 'T-03', 'T-05'], '37, 41': ['T-04'], '18, 37': ['T-10'],
    '38, 40': ['T-06', 'T-07', 'T-09'],
    '20': ['B-01'], '21': ['E-01', 'E-02', 'E-10', 'E-11'],
    '22': ['N-01', 'N-02', 'N-03', 'N-04', 'N-05', 'N-06', 'N-07', 'N-08'],
}.items():
    for _i in _v:
        FOLHA[_i] = _k
