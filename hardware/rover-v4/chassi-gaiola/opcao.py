"""Revisão e opção de material do caderno — o que muda entre a opção A (alumínio) e a B (aço).

A Rev I (13/10/2026) foi enviada para cotação em duas opções com a MESMA geometria:

* **A — alumínio**: chassi como na Rev H (Al 6061-T6 e 5052-H32, solda TIG);
* **B — aço carbono**: quadro Q, chapa de fundo C-01, nervuras C-02, gaiola G e base dos mastros
  (M-01, M-02) em aço — tubos SAE 1020, chapas A36, chapa de fundo SAE 1010, solda MAG.

Nas duas: o tubo W-12 e o flange W-13 do colar passam a aço A36, e sai a cota individual de
planeza 0,1 da face do motor (W-02) e das juntas do colar (W-13) — vale a ISO 2768-mK (classe K).

A Rev I existia só em PDF, editado sobre o caderno da Rev H. Esta fonte a reproduz e emite como
**Rev J**: a mesma geometria e os mesmos materiais da Rev I, mais as correções de cálculo de
15/10/2026 (`../revisao-h/VTX-RV4-CORRECOES-2026-10-15.md`). Os números calculados da Rev I
(envelope 21,2°, CG 314 mm) partiam da Rev H e ficaram superados — por isso a letra muda.

Rev K (28/10/2026): a opção B (aço) passou a ser a escolhida e é o padrão; a bateria vai em
dois módulos de 8 células. Ver ``../revisao-h/VTX-RV4-REV-K.md``.

Escolha da opção: variável de ambiente ``VTX_OPCAO`` = ``AC`` (padrão) ou ``AL``.

    set VTX_OPCAO=AC && python gerar.py      (Windows)
    VTX_OPCAO=AC python gerar.py             (bash)
"""
import os

OPCAO = os.environ.get('VTX_OPCAO', 'AC').strip().upper()   # Rev K: aço é o padrão (decisão de 28/10/2026)
if OPCAO not in ('AL', 'AC'):
    raise ValueError(f'VTX_OPCAO deve ser AL ou AC, não {OPCAO!r}')
ACO = OPCAO == 'AC'

REV = 'K'
DATA = '28/10/2026'
LETRA = 'B' if ACO else 'A'
NOME = 'opção B — chassi em aço carbono' if ACO else 'opção A — chassi em alumínio'
PASTA = 'opcao-B-aco-carbono' if ACO else 'opcao-A-aluminio'
DOC = f'VTX-RV4-CG-{REV}-{OPCAO}'
REV_DESC = f'Bateria em 2 módulos, pneumática realocada · opção {LETRA}, ' + ('aço' if ACO else 'alumínio')

# ------------------------------------------------------------ material por peça
# Na opção B vão para aço: quadro, chapa de fundo e nervuras, gaiola (menos o coxim de
# borracha) e a base dos mastros. Ficam em alumínio: carenagens K, haste M-10, grupo T,
# batentes B-01, bandejas E, berço W-11 e a Parte B.
_ACO_NA_OPCAO_B = ('Q-', 'C-01', 'C-02', 'G-01', 'G-02', 'G-03', 'G-04', 'G-05', 'G-06', 'G-07',
                   'M-01', 'M-02')
_ACO_NAS_DUAS = ('W-12', 'W-13')
_ALUMINIOS = ('6061', '5052')


def em_aco(item):
    """A peça é de aço nesta revisão e opção (só as que eram de alumínio na Rev H)?"""
    if item in _ACO_NAS_DUAS:
        return True
    return ACO and item.startswith(_ACO_NA_OPCAO_B)


def mat_fisico(item, mat):
    """Chave de densidade da peça (`modelo.RHO`)."""
    return 'aco' if mat in _ALUMINIOS and em_aco(item) else mat


def mat_exibido(item, mat_rev_h, desc):
    """Nome do material na lista de peças, no carimbo e no DXF."""
    if not mat_rev_h.startswith('Al ') or not em_aco(item):
        return mat_rev_h
    if item in _ACO_NAS_DUAS:
        return 'Aço A36'
    if item == 'C-01':
        return 'Aço SAE 1010'
    d = desc.lower()
    return 'Aço SAE 1020' if d.startswith(('tubo', 'barra')) else 'Aço A36'


# ------------------------------------------------------------------ textos
SOLDA = ('MAG, ER70S-6 (TIG ER70S-2 aceito). Filete contínuo a2 nos tubos, a3 nas peças W. Soldador '
         'qualificado para aço carbono (AWS D1.1 / ISO 9606-1).'
         if ACO else
         'TIG, ER5356 (ER4043 se for pintar). Filete contínuo a2 nos tubos, a3 nas peças W. Soldador '
         'qualificado para alumínio (AWS D1.2 / ISO 9606-2); aço do grupo W: processo e consumível a '
         'definir com o soldador.')
SOLDA_CURTA = 'MAG · ER70S-6' if ACO else 'TIG · ER5356'
PROC = 'MAG' if ACO else 'TIG'
QUALIFICACAO = ('Qualificação do soldador para aço carbono (ISO 9606-1).' if ACO
                else 'Qualificação do soldador para alumínio (ISO 9606-2).')

MATERIAIS_LISTA = (
    ['Tubos 30×30×2 e 20×20×1,5, luva Ø42×5 e barra Ø12: aço SAE 1020.',
     'Chapas 3, 5, 6, 8, 10 e cantoneira 40×40×4 do chassi: aço A36.',
     'Chapa de fundo 2 mm: aço SAE 1010.',
     'Carenagens e tampas (1,2 e 2): Al 5052-H32.',
     'Grupo W: aço e inox 304; berço W-11 em Al 6061-T6 (folhas 28 a 31).',
     'Fixadores: inox A4 (folha 13); rebites F-09 e F-35 em aço ou inox.']
    if ACO else
    ['Tubos 30×30×2 e 20×20×1,5: Al 6061-T6 (ASTM B221).',
     'Chapas 3, 5, 6, 8, 10: Al 6061-T6.',
     'Chapas 1,2 e 2: Al 5052-H32 (ASTM B209).',
     'Cantoneira 40×40×4, barra Ø12: Al 6061-T6.',
     'Grupo W: aço A36 / 1020 / 1045 e inox 304 (folhas 28 a 31).',
     'Fixadores: inox A4 (folha 13).'])

# acabamentos cotados no formulário (folha 16) e na folha 02
ACABAMENTOS = (
    [('A', 'natural, oleado'), ('B', 'zincagem eletrolítica'), ('C', 'pintura eletrostática'),
     ('D', 'zincagem a quente')]
    if ACO else
    [('A', 'natural'), ('B', 'anodização preta'), ('C', 'pintura eletrostática')])

# material no carimbo das folhas que mostram o chassi
MAT_QUADRO = 'Aço SAE 1020 · tubo 30×30×2' if ACO else 'Al 6061-T6 · tubo 30×30×2'
MAT_FOLHA_06 = 'Aço SAE 1020' if ACO else 'Al 6061-T6'
MAT_FOLHA_08 = ('C-01 Aço SAE 1010 e = 2 · C-02 Aço A36' if ACO
                else 'C-01 Al 5052-H32 e = 2 · C-02 Al 6061-T6')
MAT_FOLHA_09 = ('Aço SAE 1020 · tubo 20×20×1,5 · chapas A36' if ACO
                else 'Al 6061-T6 · tubo 20×20×1,5 · chapas 3 e 5')
MAT_FOLHA_11 = ('Al 5052-H32 · Aço A36 (G-05, G-06)' if ACO
                else 'Al 5052-H32 · Al 6061-T6 (G-05, G-06)')
MAT_FOLHA_12 = 'Aço SAE 1020 · tubo 20×20×1,5' if ACO else 'Al 6061-T6 · tubo 20×20×1,5'
MAT_FOLHA_17 = 'Aço SAE 1020 / A36' if ACO else 'Al 6061-T6'
MAT_FOLHA_31 = 'W-08/09/10/12/13 aço e inox · W-11 Al 6061'

# planeza: a Rev I tirou a cota individual de 0,1 (W-02 e W-13) — vale a geral
PLANEZA_GERAL = 'ISO 2768-K: 0,4 (faixa 100 a 300 mm)'
