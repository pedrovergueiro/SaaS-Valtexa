"""Interligação e roteamento de cabos — o que liga a quê, por onde passa e quanto de cabo isso pede.

O pedido do V4 inclui "organizar cabos e conectores". Este módulo organiza o que o projeto
SABE e diz com todas as letras o que ele não sabe.

**O que sabe:** quais sensores e equipamentos existem, quantos cabos cada um pede (vem de
`modular.py`), em que ponto da estrutura cada cabo atravessa (vem de `modelo.py`) e a altura
de cada posto no mastro, de onde se tira o comprimento do trecho vertical.

**O que NÃO sabe, e por isso este módulo não fecha um chicote:**

* a posição dos componentes dentro do compartimento. `espaco.py` mostra que a bateria
  estimada nem cabe, e que as posições "onde cabe" de Jetson, driver e BMS se sobrepõem
  entre si (cada uma é calculada sozinha). Sem posição, não há rota;
* bitola, fusível, pinagem e conector de cada equipamento — dependem das fichas técnicas
  (P-05, P-13) que o projeto ainda não tem;
* o grau IP de qualquer conexão: é resultado de ensaio (V-11), nunca de especificação.

O que sai daqui, portanto, é um **diagrama funcional de interligação**, as **regras de
roteamento** propostas, o **inventário de passagens pela estrutura** (as que existem, as que
só estavam no texto e as que faltavam) e **comprimentos ESTIMADOS** para cotar o cabo — não
um desenho de chicote.

```
python roteamento.py
```
"""

from __future__ import annotations

import pathlib
import sys

AQUI = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent / 'chassi-gaiola'))
sys.path.insert(0, str(AQUI))

import modelo as M  # noqa: E402

# =========================================================== classes de cabo
CLASSES = {
    'pot': 'Potência',
    'dad': 'Dados e PoE (Ethernet)',
    'sin': 'Sinal (coaxial, CAN, analógico)',
    'seg': 'Segurança (E-STOP)',
    'pne': 'Pneumática',
}

PERCURSO_INTERNO_MM = 800.0
"""mm — ESTIMATIVA. Quanto cabo vai da saída da luva até o switch. A posição do switch não
está fechada (P-31), então este número é suposição: o centro do compartimento a partir da
bandeja lateral, mais folga de acomodação. Só serve para orçar o cabo, nunca para cortá-lo."""

FOLGA_CABO = 1.15
"""Fator sobre o comprimento medido: curvas, alívio de tração, laço de articulação."""

PERCURSO_MOTOR_EXPOSTO_MM = 250.0
"""mm — ESTIMATIVA. Do passa-cabo Ø32 da chapa de fundo até o motor-roda, por fora, sob o
quadro. Inclui o laço que absorve os 80 mm de curso da roda."""


def comprimento_posto(z: float) -> float:
    """Metros de cabo de um posto do mastro até o switch: vertical até o deck + percurso interno."""
    return (max(z - M.Z_DECK, 0.0) + PERCURSO_INTERNO_MM) * FOLGA_CABO / 1000.0


def comprimento_motor(lado_oposto: bool) -> float:
    """Driver na bandeja direita → passa-cabo Ø32 (±300, ±80) → motor. `lado_oposto`: motor da esquerda."""
    dx = 300.0
    dy = (M.W_Q / 2 - 60.0 - 80.0) + (160.0 if lado_oposto else 0.0)
    return (dx + dy + PERCURSO_MOTOR_EXPOSTO_MM) * FOLGA_CABO / 1000.0


# =========================================================== a lista de interligação
def interligacoes() -> list[dict]:
    """Uma linha por grupo de cabos: de, para, classe, quantidade, meio, passagem, comprimento."""
    z = M.CAMERAS_Z
    th = M.Z_TERMICA
    lista = []

    def add(de, para, classe, qtd, meio, passagem, comp=None, nota=''):
        lista.append(dict(de=de, para=para, classe=classe, qtd=qtd, meio=meio,
                          passagem=passagem, comp_m=comp, nota=nota))

    add('Bateria', 'BMS', 'pot', '1', 'cabo de potência', '—', None, 'bitola: ficha da bateria (P-05)')
    add('BMS', 'Driver dos motores', 'pot', '1', 'cabo de potência', '—', None, 'fusível: a definir')
    add('Driver', '4 motores-roda MPW86', 'pot', '4', 'potência + encoder, conduíte',
        'passa-cabo Ø32 na chapa de fundo, (±300; ±80)',
        max(comprimento_motor(False), comprimento_motor(True)),
        'laço para os 80 mm de curso da roda; comprimento = o maior dos quatro')
    add('Bateria / BMS', 'Conversor DC/DC 12 V', 'pot', '1', 'cabo de potência', '—')
    add('DC/DC 12 V', 'Jetson, switch, compressor, válvulas, faróis', 'pot', 'feixe', 'cabo 12 V', '—',
        None, 'faróis N-08 pela carenagem K-02')
    add('E-STOP (tampa traseira)', 'Driver e BMS', 'seg', '1 laço', 'cabo de 2 vias, hardwired',
        'furo Ø22,5 na tampa K-05', None, 'nunca por rede — corta a potência por contato')
    cam_l = ', '.join(f'{comprimento_posto(v):.1f}' for v in z)
    add('3 × OAK-D do mastro +Y', 'Switch PoE+', 'dad', '3', 'M12 X 8 vias, por dentro do tubo',
        'entrada Ø12 no tubo, saída lateral Ø20 na luva', max(comprimento_posto(v) for v in z),
        f'por posto: {cam_l} m (Z {", ".join(f"{v:.0f}" for v in z)})')
    add('3 × OAK-D do mastro −Y', 'Switch PoE+', 'dad', '3', 'M12 X 8 vias, por dentro do tubo',
        'idem, no mastro −Y', max(comprimento_posto(v) for v in z), 'o switch fica do lado +Y: cruzamento a 90°')
    add('Térmicas removíveis (0 a 4)', 'Switch PoE+ ou Jetson', 'dad', '0 a 4', 'M12; Ethernet ou USB (P-30)',
        'idem, nos postos H1 a H4', max(comprimento_posto(v) for v in th),
        f'por posto: {", ".join(f"{comprimento_posto(v):.1f}" for v in th)} m (Z {", ".join(f"{v:.0f}" for v in th)})')
    add('C7 frontal, C8 traseira', 'Switch PoE+', 'dad', '2', 'M12 X',
        'SOB o chassi: passagem para o compartimento NÃO ESTÁ NO MODELO', 1.5,
        'T-06 a Z 210, fora do compartimento; a entrada do cabo é pendência')
    add('C9 câmera de raiz', 'Switch PoE+', 'dad', '1', 'M12 X', 'dentro do compartimento', 1.0)
    add('LiDAR Livox Mid-360', 'Switch PoE+', 'dad', '1', 'cabo do fabricante', 'furo Ø30 em G-06 e K-04', 1.2)
    add('Terminal de satélite (opcional)', 'Switch PoE+', 'dad', '0 ou 1', 'Ethernet',
        'furo Ø32 em T-07 e em K-05 (acrescentado nesta revisão)', 1.5)
    add('Switch PoE+', 'Jetson Orin NX', 'dad', '1', 'Ethernet', '—')
    add('Jetson', 'Roteador / modem', 'dad', '1', 'Ethernet', '—')
    add('Antena GNSS RTK', 'Receptor GNSS', 'sin', '1 ou 2', 'coaxial',
        'Ø10 em T-10 (topo do mastro) ou Ø20 em N-01/K-05 (tampa)',
        (M.Z_BASE_ANTENA - M.Z_DECK + PERCURSO_INTERNO_MM) * FOLGA_CABO / 1000.0,
        'no mastro o coaxial sobe 1,5 m: perda no cabo conta no orçamento do RTK (P-36)')
    add('IMU', 'Jetson', 'sin', '1', 'CAN ou serial', '—', None, 'berço N-02, perto do CG')
    add('4 sensores de altura W-16', 'Controlador da suspensão', 'sin', '4', 'analógico blindado',
        'pelo passa-cabo da roda', None)
    add('Compressor', 'Reservatório → secador → manifold', 'pne', '1', 'tubo PU', '—')
    add('Manifold', '4 foles', 'pne', '4', 'tubo PU Ø6, engate F-36', 'pelo colar W-12 de cada canto',
        None, 'comprimento depende da posição do manifold')
    return lista


def resumo_para_bom() -> dict:
    """Quantidades de cabo para a cotação — todas ESTIMATIVA, e é isso que a BOM diz."""
    z = list(M.CAMERAS_Z)
    th = list(M.Z_TERMICA)
    m12_oakd = sum(comprimento_posto(v) for v in z) * 2
    m12_term = sum(comprimento_posto(v) for v in th) * 2
    coax = comprimento_posto(M.Z_BASE_ANTENA - 0.0)
    return dict(n_m12_oakd=6, n_m12_extremidade=3, n_m12_termica_max=4,
                m_oakd=m12_oakd, m_termica_max=m12_term, m_coax=coax,
                n_coax_max=2)


# =========================================================== passagens pela estrutura
def passagens() -> list[dict]:
    """O inventário de furos de passagem: o que o modelo tem, o que só o texto dizia, o que faltava."""
    tem_g06 = any(abs(c[2] - 30) < 0.1 for p in M.suporte_lidar() for c in p.circulos)
    k05 = [p for p in M.carenagens() if p.item == 'K-05'][0]
    k04 = [p for p in M.carenagens() if p.item == 'K-04'][0]
    tem_k04_lidar = any(abs(c[2] - 30) < 0.1 and abs(c[0] - M.X_LIDAR) < 0.1 for c in k04.circulos)
    tem_k05_gnss = any(abs(c[2] - 20) < 0.1 and abs(c[0] - M.X_GNSS) < 0.1 for c in k05.circulos)
    tem_k05_sat = any(abs(c[2] - 32) < 0.1 and abs(c[0] - M.X_SAT) < 0.1 for c in k05.circulos)
    tem_k05_estop = any(abs(c[0] - M.X_ESTOP) < 0.1 and abs(c[2] - M.D_ESTOP) < 1.0 for c in k05.circulos)
    graom = [f for f in M.furos_chapa() if abs(f[2] - 32) < 0.1]
    t07 = [p for p in M.berco_satelite()][0]
    tem_t07 = any(abs(c[2] - 32) < 0.1 for c in t07.circulos)
    n = lambda b: 'MODELADA' if b else 'FALTA'
    return [
        dict(onde='Tubo M-10 — entrada Ø12, 30 mm abaixo de cada posto', quem='cabos dos 5 postos de cada mastro',
             estado='SÓ NO TEXTO', nota='furo transversal: o modelo extrudado não o representa; passa-cabo F-60/F-61 (Ø12)'),
        dict(onde='Luva M-01 — saída lateral Ø20', quem='todos os cabos do mastro',
             estado='SÓ NO TEXTO', nota='passa-cabo F-59 (Ø20). O F-46 do V3 era Ø32 e não cabia numa luva Ø42: corrigido'),
        dict(onde='Topo do mastro — furo Ø10 axial do T-10', quem='coaxial da antena',
             estado=n(any(abs(c[2] - M.D_CABO_ANTENA) < 0.1 for p in M.mastro((1,)) if p.item == 'T-10'
                          for c in p.circulos)), nota=''),
        dict(onde='Chapa de fundo C-01 — passa-cabo Ø32 (×4)', quem='cabos dos motores-roda',
             estado=n(len(graom) == 4), nota=f'em ({", ".join(f"{f[0]:.0f}; {f[1]:.0f}" for f in graom[:2])}…)'),
        dict(onde='Tampa K-04 e suporte G-06 — Ø30', quem='LiDAR', estado=n(tem_g06 and tem_k04_lidar), nota=''),
        dict(onde='Tampa K-05 — Ø20 sob a N-01', quem='antena GNSS na tampa', estado=n(tem_k05_gnss), nota=''),
        dict(onde='Tampa K-05 — Ø32 e 6 furos M5 sob o T-07', quem='terminal de satélite',
             estado=n(tem_k05_sat and tem_t07),
             nota='FALTAVA: o T-07 tinha o furo, a tampa não. Acrescentado ao modelo e ao DXF da K-05 nesta revisão'),
        dict(onde='Tampa K-05 — Ø22,5 sob o E-STOP', quem='botão de emergência', estado=n(tem_k05_estop), nota=''),
        dict(onde='Sob o chassi → compartimento', quem='câmeras de extremidade C7 e C8 (T-06)',
             estado='FALTA', nota='o T-06 está a Z 210, fora do compartimento (Z ≥ 250); não há furo na chapa de fundo '
                                  'nem passa-cabo previsto. PENDÊNCIA nova'),
        dict(onde='Colar W-12 — linha de ar', quem='4 tubos PU para os foles', estado='SÓ NO TEXTO',
             nota='o colar é estanque (a3 + junta); a passagem do tubo não está desenhada'),
    ]


# =========================================================== regras propostas
REGRAS = [
    ('Potência e dados em lados diferentes', 'Potência (driver, BMS, DC/DC) pelo lado −Y; dados e PoE pelo lado +Y. '
     'Quando precisarem se cruzar, cruzam a 90°, nunca em paralelo. A distância mínima entre os dois '
     'depende do fabricante do driver e não está nas fichas que o projeto tem.'),
    ('Nada de potência no tubo do mastro', 'O tubo leva só PoE/Ethernet e coaxial. Potência no mastro só se um '
     'sensor pedir tensão própria — e nenhum pede, com PoE.'),
    ('Alívio de tração em toda saída', 'Cada cabo que sai do tubo, da luva ou do módulo térmico tem passa-cabo '
     'e alívio de tração. O cabo do módulo térmico sai pelo lado da braçadeira, com laço, para que o '
     'módulo saia sem esticá-lo.'),
    ('E-STOP é laço de segurança', 'Contato em série, fiado ao driver e ao BMS, independente da rede e do '
     'computador. Software nenhum participa do corte.'),
    ('Conector sempre separável do lado do módulo', 'M12 em todo posto de sensor: o cabo fica no mastro e o '
     'conector é o único ponto elétrico a desfazer na troca. O grau IP desse conjunto NÃO é declarado (V-11).'),
    ('Cabo de motor com laço', 'Os 80 mm de curso da roda movem o motor em relação ao passa-cabo. O trecho '
     'exposto leva conduíte e um laço de folga; sem ele, o primeiro ciclo de suspensão fadiga o cabo.'),
]


def main() -> None:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    print('=' * 100)
    print('VTX-RV4 Rev H · INTERLIGAÇÃO E ROTEAMENTO DE CABOS')
    print('=' * 100)
    print('\n1. Interligações (comprimentos ESTIMADOS — percurso interno suposto: '
          f'{PERCURSO_INTERNO_MM:.0f} mm, folga {FOLGA_CABO:.2f}×)')
    print('-' * 100)
    for i, n in enumerate(interligacoes(), 1):
        comp = f'{n["comp_m"]:.1f} m' if n['comp_m'] else '—'
        print(f'  {i:2}. [{n["classe"]}] {n["de"]} → {n["para"]}  ×{n["qtd"]}  ({n["meio"]})  {comp}')
        print(f'        passagem: {n["passagem"]}' + (f'  · {n["nota"]}' if n['nota'] else ''))
    print('\n2. Passagens pela estrutura')
    print('-' * 100)
    for p in passagens():
        print(f'  [{p["estado"]:11}] {p["onde"]} — {p["quem"]}')
        if p['nota']:
            print(f'                {p["nota"]}')
    r = resumo_para_bom()
    print('\n3. Para a cotação do cabo (ESTIMATIVA)')
    print('-' * 100)
    print(f'  M12 das OAK-D do mastro: {r["n_m12_oakd"]} cabos, {r["m_oakd"]:.1f} m no total')
    print(f'  M12 das câmeras de extremidade e de raiz: {r["n_m12_extremidade"]}')
    print(f'  M12 das térmicas (até {r["n_m12_termica_max"]}): até {r["m_termica_max"]:.1f} m no total')
    print(f'  coaxial da antena no mastro: {r["m_coax"]:.1f} m cada, até {r["n_coax_max"]}')
    print('\n4. Regras de roteamento propostas')
    print('-' * 100)
    for (a, b) in REGRAS:
        print(f'  · {a}: {b}')
    print('\n5. O que este módulo NÃO resolve')
    print('-' * 100)
    print('  posição dos componentes no compartimento (espaco.py: a bateria estimada não cabe e os')
    print('  componentes se sobrepõem entre si); bitola, fusível, pinagem e conector de cada equipamento')
    print('  (fichas P-05, P-13); grau IP (ensaio V-11). Sem isso não há chicote, só interligação.')


if __name__ == '__main__':
    main()
