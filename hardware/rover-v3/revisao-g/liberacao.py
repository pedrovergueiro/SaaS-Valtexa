"""Prontidão para fabricação, grupo por grupo — e o registro da liberação.

Liberar para fabricação é o ato de maior consequência deste projeto: a partir dele
alguém corta metal e solda. Este módulo existe para que o ato seja **explícito,
rastreável e parcial** — porque o conjunto não está todo no mesmo estado de prontidão, e
liberar tudo junto esconderia isso.

**O que este módulo não faz:** preencher nome, CREA ou data de ninguém. Os campos de
aprovação do carimbo existem para serem escritos por quem assina, e o padrão do selo
continua sendo "não liberado" — esquecer de informar nunca produz um desenho liberado
por omissão.
"""

from __future__ import annotations

import pathlib
import sys

AQUI = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent / 'chassi-gaiola'))

# ============================================================ estado por grupo
# (grupo, desenhado, dxf, bom, tolerâncias, bloqueios)
PRONTIDAO = {
    'Q': dict(
        nome='Quadro estrutural soldado',
        desenhado=True, dxf='n/a (tubo)', bom=True, tolerancias=True,
        bloqueios=[
            ('MATERIAL EM ABERTO', 'alumínio 30×30×2 (Rev E) ou aço 1020 25×25×1,5 '
                                   '(sugestão 2.1). Fabricar em alumínio agora fecha a '
                                   'questão por fato consumado.'),
            ('FEA', 'casos 1 a 4 e 8 da folha 25 não rodados.'),
        ]),
    'C': dict(
        nome='Chapa de fundo e nervuras',
        desenhado=True, dxf=True, bom=True, tolerancias=True,
        bloqueios=[('FEA', 'a chapa trabalha como diafragma de torção — caso 4.')]),
    'W-01/W-02/W-03': dict(
        nome='Braço, chapa do motor-roda e tampa-gusset (12 un, aço)',
        desenhado=True, dxf=True, bom=True, tolerancias=True,
        bloqueios=[
            ('P-04 · ElectroCraft', 'planicidade admitida pelo motor não publicada; '
                                    '0,1 mm atual ou 0,2 proposto.'),
            ('P-22 · FADIGA', 'caso 9 do FEA, novo nesta revisão: as duas peças passaram '
                              'a ciclar com o terreno. É o caso que justifica o aço, e '
                              'não foi rodado.'),
        ]),
    'W-04…W-10': dict(
        nome='Pivô e articulação do prato (28 un, aço e inox)',
        desenhado=True, dxf=True, bom=True, tolerancias=True,
        bloqueios=[
            ('P-21 · BUCHA', 'bucha autolubrificante Ø23/Ø20 sem modelo escolhido; '
                             'pressão calculada 1,7 MPa, bem abaixo da faixa.'),
            ('P-22 · FADIGA', 'o pivô é o ponto de maior número de ciclos do rover.'),
        ]),
    'W-11/W-12/W-13': dict(
        nome='Berço do fole e colar de vedação (12 un, alumínio)',
        desenhado=True, dxf=True, bom=True, tolerancias=True,
        bloqueios=[
            ('ENSAIO DE ESTANQUEIDADE', 'o colar é o que impede a passagem do fole de '
                                        'abrir o compartimento. Ensaio de bancada antes '
                                        'de montar — ver folha 35.'),
        ]),
    'W-15 (fole)': dict(
        nome='Mola pneumática (4 un) — COMPRADA',
        desenhado='n/a (interface)', dxf='n/a', bom='requisito', tolerancias='n/a',
        bloqueios=[
            ('P-20 · MODELO COMERCIAL',
             'nenhum fole escolhido. A interface desenhada aceita qualquer um que feche '
             'a folha de requisitos, e aceita cilindro pneumático de mesma área. '
             'Nenhum desenho de usinagem depende da escolha — mas o rover não anda '
             'sem ela.'),
        ]),
    'G': dict(
        nome='Gaiola de proteção (2 módulos)',
        desenhado=True, dxf=True, bom=True, tolerancias=True,
        bloqueios=[]),
    'K': dict(
        nome='Carenagens e tampas',
        desenhado=True, dxf=True, bom=True, tolerancias=True,
        bloqueios=[]),
    'M': dict(
        nome='Base dos mastros',
        desenhado=True, dxf=True, bom=True, tolerancias=True,
        bloqueios=[('FEA · caso 6', '1ª frequência do mastro ≥ 7,5 Hz não verificada.')]),
    'F': dict(
        nome='Fixadores e porcas-rebite',
        desenhado='n/a', dxf='n/a', bom=True, tolerancias='n/a',
        bloqueios=[]),
    'W': dict(
        nome='Suspensão pneumática',
        desenhado=False, dxf=False, bom=False, tolerancias=False,
        bloqueios=[
            ('NÃO DESENHADA', 'foles, suportes W-18 e roteamento pneumático não existem '
                              'como geometria.'),
            ('P-13 · COMPONENTES', 'nenhum dos 9 itens tem modelo comercial escolhido; '
                                   'as massas são de faixa de catálogo.'),
            ('P-12 · FEA', 'os 8 casos foram escritos para suspensão rígida. Com o fole, '
                           'o apoio deixa de ser nos 4 furos Ø88 — precisam ser '
                           'reescritos antes de rodar.'),
            ('P-14 · ROLAGEM', 'rígida (proposta) ou pneumática: 25 % do envelope de '
                               'estabilidade depende disso.'),
        ]),
}

# Pendências que valem para o conjunto, não para um grupo.
TRANSVERSAIS = [
    ('P-02 · MASSA OFICIAL', 'CRÍTICA',
     'Quatro números em circulação (85,04 · 82,49 · 110,07 · 122,79 kg) e nenhum é '
     'oficial. A baseline declara 97,8 kg nominais; o chassi real em alumínio já está '
     'em 110,07, e com suspensão pneumática vai a 122,79 — 25 kg acima. Não é '
     'impeditivo de cortar metal, mas é impeditivo de declarar que o rover cumpre a '
     'baseline.'),
    ('P-07 · COTAÇÃO', 'ALTA',
     'Sem cotação não há decisão de material, e sem decisão de material o quadro não '
     'deveria ser cortado.'),
    ('P-03 · FEA', 'ALTA',
     'Nenhum dos 8 casos rodado. A folha 25 os especifica com condições de contorno, '
     'malha e critérios de aceite — falta executar.'),
]


def pronto_sem_ressalva() -> list[str]:
    """Grupos que uma assinatura cobre sem depender de mais nada."""
    return [g for g, d in PRONTIDAO.items() if not d['bloqueios']]


def pronto_com_ressalva() -> dict:
    """Grupos desenhados e cotáveis, mas com decisão ou verificação pendente."""
    return {g: d for g, d in PRONTIDAO.items()
            if d['bloqueios'] and d['desenhado'] is True}


def nao_liberavel() -> dict:
    """O que não se libera porque não existe desenho."""
    return {g: d for g, d in PRONTIDAO.items() if d['desenhado'] is False}


# ======================================================= registro da liberação
SELO_LIBERADO = 'LIBERADO PARA FABRICAÇÃO'
SELO_PARCIAL = 'LIBERAÇÃO PARCIAL · VER FOLHA 15'
SELO_PADRAO = 'EMITIDO PARA COTAÇÃO E VALIDAÇÃO · NÃO LIBERADO PARA FABRICAÇÃO'


def registro(nome: str, crea: str, data: str, escopo: str,
             ressalvas: list[str] | None = None) -> dict:
    """Monta os metadados de aprovação para o carimbo.

    Exige os quatro campos. Nenhum tem valor padrão, de propósito: um padrão aqui seria
    uma assinatura que ninguém deu.

    ``escopo`` é obrigatório porque o conjunto **não está todo no mesmo estado**. Uma
    liberação sem escopo seria lida como liberação de tudo, inclusive do que não tem
    desenho.
    """
    for campo, valor in (('nome', nome), ('crea', crea), ('data', data), ('escopo', escopo)):
        if not valor or not str(valor).strip():
            raise ValueError(
                f'{campo!r} é obrigatório: uma liberação para fabricação sem {campo} '
                'não é uma liberação, é um desenho com um carimbo escrito.')
    parcial = escopo.strip().lower() not in ('conjunto completo', 'total', 'tudo')
    return dict(
        selo=SELO_PARCIAL if parcial else SELO_LIBERADO,
        verificado=f'{nome} · CREA {crea}',
        aprovado=f'{data} · {escopo}',
        ressalvas=ressalvas or [],
        parcial=parcial,
    )


if __name__ == '__main__':
    print('VTX-RV3 Rev F · prontidão para fabricação')
    print()
    print('PRONTO, sem ressalva:')
    for g in pronto_sem_ressalva():
        print(f"    {g:10} {PRONTIDAO[g]['nome']}")
    print()
    print('DESENHADO, com decisão ou verificação pendente:')
    for g, d in pronto_com_ressalva().items():
        print(f"    {g:10} {d['nome']}")
        for titulo, por in d['bloqueios']:
            print(f"               · {titulo}: {por}")
    print()
    print('NÃO LIBERÁVEL (sem desenho):')
    for g, d in nao_liberavel().items():
        print(f"    {g:10} {d['nome']}")
        for titulo, por in d['bloqueios']:
            print(f"               · {titulo}: {por}")
    print()
    print('TRANSVERSAIS:')
    for cod, grav, texto in TRANSVERSAIS:
        print(f"    [{grav}] {cod}")
        print(f"               {texto}")
