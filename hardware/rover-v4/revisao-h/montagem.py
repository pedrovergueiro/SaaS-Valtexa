"""Onde vai cada peça do Rover V4 — mapa de posições, vizinhanças e sequência.

Isto não é um texto escrito à mão sobre o modelo: é extraído DELE. A posição de cada peça
sai da geometria, e a lista de vizinhas sai de medir, peça contra peça, quais se encostam.
Se uma cota mudar no `modelo.py`, este manual muda junto — ou não gera.

O que é julgamento de engenharia está declarado como tal e separado: a SEQUÊNCIA de
montagem, os TORQUES e as CONFERÊNCIAS. Essas três coisas não se deduzem da geometria.

```
python montagem.py            # relatório completo
python montagem.py --item W-01
```

Unidades: mm, N·m.
"""

from __future__ import annotations

import pathlib
import sys
from collections import OrderedDict

AQUI = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent / 'chassi-gaiola'))
sys.path.insert(0, str(AQUI))

import modelo as M  # noqa: E402

FOLGA_CONTATO = 1.5
"""mm — duas peças são consideradas vizinhas quando suas caixas se aproximam disto.

Não é zero porque o modelo é paramétrico e algumas peças se encostam por construção
(solda) e outras por aperto (parafuso), com folgas nominais de montagem no meio.
"""


# ============================================================ posição de cada peça
def _quadrante(bb) -> str:
    """Em qual canto a peça está, pelo centro da caixa."""
    cx = (bb[0][0] + bb[0][1]) / 2
    cy = (bb[1][0] + bb[1][1]) / 2
    if abs(cx) < 30 and abs(cy) < 30:
        return 'centro'
    fr = 'dianteiro' if cx > 30 else ('traseiro' if cx < -30 else 'central')
    la = 'esquerdo' if cy > 30 else ('direito' if cy < -30 else '')
    return (fr + ' ' + la).strip()


def pecas() -> OrderedDict:
    """Todas as peças fornecidas, agrupadas por código, com posição de cada exemplar."""
    out: OrderedDict = OrderedDict()
    for p in M.conjunto('ABO'):
        if p.estilo == 'ref':
            continue
        bb = p.bbox()
        d = out.setdefault(p.item, dict(
            item=p.item, grupo=p.grupo, nome=M.ITENS[p.item]['nome'],
            desc=M.ITENS[p.item]['desc'], mat=M.ITENS[p.item]['mat'],
            qtd=0, massa=0.0, exemplares=[]))
        d['qtd'] += 1
        d['massa'] += p.massa()
        d['exemplares'].append(dict(
            x=(bb[0][0], bb[0][1]), y=(bb[1][0], bb[1][1]), z=(bb[2][0], bb[2][1]),
            centro=p.centro(), onde=_quadrante(bb)))
    return out


def _encostam(a, b) -> bool:
    for i in range(3):
        if a[i][0] - b[i][1] > FOLGA_CONTATO or b[i][0] - a[i][1] > FOLGA_CONTATO:
            return False
    return True


def vizinhancas() -> dict:
    """Para cada código, quais outros códigos encostam nele. Medido, não declarado."""
    ps = [p for p in M.conjunto('ABO') if p.estilo != 'ref']
    caixas = [(p.item, p.bbox()) for p in ps]
    viz: dict = {}
    for i, (ia, ba) in enumerate(caixas):
        s = viz.setdefault(ia, set())
        for j, (ib, bb) in enumerate(caixas):
            if i == j or ia == ib:
                continue
            if _encostam(ba, bb):
                s.add(ib)
    return {k: sorted(v) for k, v in viz.items()}


# ====================================================== união: como cada peça prende
# DECLARADO. A geometria diz onde a peça está e o que ela toca; não diz se ali é solda,
# parafuso ou rebite. Esta tabela é julgamento de projeto, e é o que a folha 13 classifica.
UNIAO = {
    'Q-01': ('solda', 'TIG a2 contínuo nas travessas', None),
    'Q-02': ('solda', 'TIG a2 contínuo nas longarinas', None),
    'Q-03': ('solda', 'TIG a2 contínuo nas longarinas', None),
    'Q-04': ('solda', 'TIG a2 contínuo nos dois anéis', None),
    'Q-05': ('solda', 'bucha soldada dentro do tubo, antes de fechar o anel', None),
    'Q-06': ('solda', 'tampa de extremidade, TIG a2 em todo o contorno', None),
    'C-01': ('parafuso', 'M6 em porca-rebite no anel inferior', 10.0),
    'C-02': ('rebite', 'Ø4,8 na chapa + M6 no anel', None),
    'W-01': ('solda', 'sobreposto na chapa W-02, filete a4 em cima e embaixo', None),
    'W-02': ('solda', 'recebe o braço W-01 e a tampa W-03; usinar DEPOIS de soldar', None),
    'W-03': ('solda', 'tampa-gusset: fecha a ponta do tubo e amarra o braço à chapa, a4', None),
    'W-04': ('solda', 'atravessa o tubo do braço, filete a4 nas duas faces', None),
    'W-05': ('solda', 'orelha soldada no berço W-06, filete a4 nos dois lados', None),
    'W-06': ('parafuso', 'M8×65 passante: berço do fole → bucha → chapa → berço do pivô', 25.0),
    'W-07': ('eixo', 'passa pelas duas orelhas e pelas buchas; travado por anel DIN 471', None),
    'W-08': ('eixo', 'disco articulado no pino W-10, dentro do rasgo do braço', None),
    'W-09': ('solda', 'orelha soldada no disco W-08, em dispositivo', None),
    'W-10': ('eixo', 'atravessa as paredes do braço e as orelhas; anel DIN 471', None),
    'W-11': ('parafuso', 'M8×65 em X 508 e M8×50 em X 350, sobre buchas de compressão', 25.0),
    'W-12': ('solda', 'tubo soldado na flange W-13, filete a3 estanque', None),
    'W-13': ('rebite', 'Ø4,8 na chapa de fundo, com junta NBR nas duas faces', None),
    'W-14': ('eixo', 'cabo entre o prato e o berço; limita a extensão', None),
    'W-18': ('parafuso', 'M6×20 na malha da chapa de fundo', 10.0),
    'G-01': ('solda', 'TIG a2 nos trilhos transversais', None),
    'G-02': ('solda', 'TIG a2 nos trilhos laterais', None),
    'G-03': ('solda', 'TIG a2 nos trilhos laterais', None),
    'G-04': ('solda', 'montante soldado no anel e na sapata', None),
    'G-05': ('parafuso', 'M6 em porca-rebite no anel superior', 10.0),
    'G-06': ('parafuso', 'M5×16 em porca-rebite, sobre 4 coxins G-08', 5.0),
    'G-07': ('solda', 'tampa do trilho, TIG a2 no contorno', None),
    'G-08': ('parafuso', 'M4 no suporte do LiDAR', 2.5),
    'K-01': ('parafuso', 'M5×12 em porca-rebite nas paredes externas', 5.0),
    'K-02': ('parafuso', 'M5×12 em porca-rebite nas paredes externas', 5.0),
    'K-03': ('parafuso', 'M5×12 em porca-rebite nas paredes externas', 5.0),
    'K-04': ('parafuso', 'M5×12 em porca-rebite no anel da gaiola', 5.0),
    'K-05': ('parafuso', 'M5×12 em porca-rebite no anel da gaiola', 5.0),
    'K-06': ('parafuso', 'M5×12 em porca-rebite, por cima das duas tampas', 5.0),
    'M-01': ('solda', 'luva soldada no quadro, sobre o reforço M-02', None),
    'M-02': ('solda', 'reforço soldado no anel superior, antes da luva', None),
    'M-10': ('parafuso', 'M6×12 passante na luva, 2 por mastro', 10.0),
    'M-11': ('encaixe', 'bainha deslizada sobre a haste, sem fixador', None),
    'M-12': ('encaixe', 'ponta cônica pressionada na bainha', None),
    'T-01': ('parafuso', 'braçadeira deslizante: 2 × M6×45, aperto define a altura', 12.0),
    'T-02': ('parafuso', 'M8 central no eixo do índice + pino Ø6 na posição de inclinação', 20.0),
    'T-03': ('parafuso', '4 × M5 sobre os pinos de referência Ø8 e anti-giro Ø6', 5.0),
    'T-04': ('parafuso', '4 × M5 IMPERDÍVEIS de aperto manual sobre os pinos Ø8 e Ø6 — módulo térmico removível; '
             'aperto manual firme, valor a definir no ensaio V-16', None),
    'T-05': ('parafuso', '2 × M4 no adaptador — peça sacrificial, troca sem ferramenta especial', 2.0),
    'T-10': ('parafuso', 'encaixa 40 mm no topo da haste e trava com 1 × M6 transversal; a antena rosqueia nele', 10.0),
    'T-06': ('parafuso', 'M5 em porca-rebite, sob a chapa de fundo', 5.0),
    'T-07': ('parafuso', 'M5 em porca-rebite na tampa traseira', 5.0),
    'T-09': ('parafuso', 'M5 em porca-rebite na chapa de fundo, dentro do compartimento', 5.0),
    'B-01': ('parafuso', 'M6×20 na malha da chapa de fundo', 10.0),
    'E-01': ('parafuso', 'M6×20 na malha da chapa de fundo', 10.0),
    'E-02': ('parafuso', 'M6×20 na malha da chapa de fundo', 10.0),
    'E-10': ('parafuso', 'M5×16 na tampa traseira', 5.0),
    'E-11': ('parafuso', 'M5×16 na tampa traseira', 5.0),
    'N-01': ('parafuso', 'M5×16 em porca-rebite na tampa', 5.0),
    'N-02': ('parafuso', 'M6×16, sobre espaçadores N-03', 10.0),
    'N-03': ('encaixe', 'espaçador entre o berço e a chapa', None),
    'N-04': ('parafuso', 'M4×12 em porca-rebite, com barras N-05 por cima', 2.0),
    'N-05': ('parafuso', 'M4 sobre a janela de policarbonato', 2.0),
    'N-06': ('solda', 'aba soldada no suporte da câmera de raiz', None),
    'N-07': ('parafuso', 'M6×16 no conjunto da câmera de raiz', 10.0),
    'N-08': ('rebite', 'Ø4,8 na carenagem', None),
}

# =============================================================== sequência
# DECLARADO. Ordem de montagem, e a razão de cada etapa estar onde está. A razão importa
# mais que a ordem: é ela que diz o que acontece se alguém inverter duas etapas.
SEQUENCIA = [
    ('1', 'Quadro estrutural (Q)',
     'Soldar o quadro completo com as buchas Q-05 JÁ DENTRO dos tubos. '
     'Depois de fechar o anel não há como pôr bucha nenhuma.',
     ['Q-05 nas 16 posições de fixação da suspensão', 'Q-06 nas pontas das longarinas']),
    ('2', 'Base dos mastros (M-01, M-02)',
     'Soldar antes de qualquer coisa chegar perto do quadro: o acesso para o maçarico '
     'desaparece quando a gaiola subir.',
     ['Reforço M-02 primeiro, luva M-01 depois']),
    ('3', 'Alívio de tensão e aplainamento do quadro',
     'Com todo o aço e alumínio de solda do quadro já no lugar. Depois disto o quadro '
     'não solda mais.',
     ['Verificar diagonal e planeza do anel inferior']),
    ('4', 'Cantos de suspensão (W), nas quatro bancadas',
     'Cada canto é um subconjunto independente. Soldar e usinar os quatro FORA do '
     'rover — a usinagem da chapa W-02 exige acesso de fresa dos dois lados.',
     ['Ver a sequência detalhada de 12 passos na folha 33']),
    ('5', 'Colares W-12 na chapa de fundo C-01',
     'Antes de a chapa subir no quadro: a flange do colar fica na face de BAIXO e '
     'é rebitada por fora.',
     ['Junta NBR nas duas faces de cada colar', '4 colares, um por canto']),
    ('6', 'Chapa de fundo C-01 e nervuras C-02',
     'A chapa entra por baixo e é o que fecha o compartimento. As 16 posições de '
     'suspensão ficam sem parafuso ainda.',
     ['Não apertar os M8 da suspensão nesta etapa']),
    ('7', 'Berços do pivô W-06 e berços do fole W-11',
     'Os quatro níveis de cada posição (berço do fole, bucha, chapa, berço do pivô) '
     'são apertados por UM parafuso M8×65. Montar os quatro níveis antes de apertar.',
     ['Arruela de nylon entre o berço de aço e o alumínio', 'Torque 25 N·m']),
    ('8', 'Cantos de suspensão no rover',
     'Pendurar cada canto pelo eixo W-07 nas orelhas W-05 já parafusadas. '
     'O braço fica solto até o fole entrar.',
     ['Anel DIN 471 nas duas pontas do eixo']),
    ('9', 'Foles W-10 e pratos W-08',
     'Prato no pino W-09 primeiro, depois o fole: M12 inferior no prato e M12 '
     'superior no berço, com a porta de ar voltada para dentro.',
     ['Não pressurizar ainda', 'Cabo W-13 no mesmo aperto do prato']),
    ('10', 'Motores-roda MPW86 nas chapas W-02',
     'Sete M4×14 com trava química média. Engajamento máximo 4 mm — parafuso mais '
     'longo fura o motor por dentro.',
     ['Torque 2,5 N·m', 'Conferir a orientação dos 7 furos']),
    ('11', 'Gaiola de proteção (G) e suporte do LiDAR',
     'Dois módulos idênticos, parafusados nas sapatas G-05 do anel superior.',
     ['O módulo traseiro é o dianteiro girado 180° em Z']),
    ('12', 'Grupo pneumático (W-15) e bandeja W-16',
     'Compressor, reservatório, secador e manifold na bandeja, dentro do '
     'compartimento. Linhas PU Ø6 até os quatro foles.',
     ['Linha mais curta possível por canto', 'Sensor de altura W-14 por canto']),
    ('12b', 'Postos de sensor VMS (grupo T)',
     'As braçadeiras T-01 entram no mastro ANTES da haste subir — depois de montada, '
     'passar uma braçadeira fechada por cima do mastro exige desmontar a ponta. Os pinos '
     'de referência são prensados no prato T-02 na bancada, nunca em campo.',
     ['Pino Ø8 h6 e Ø6 h6 prensados em T-02, na bancada',
      'Altura nominal 450 / 1000 / 1540 mm, conferida com gabarito',
      'Adaptador T-03 e protetor T-05 por último, já com o rover montado',
      'NUNCA afrouxar T-01 depois da calibração — ver folha 38']),
    ('13', 'Parte B: mastros, bandejas, bateria e sensores',
     'Tudo o que é interface. Só depois do ar funcionando: a altura muda o acesso.',
     ['Ver folhas 17 a 22']),
    ('14', 'Carenagens e tampas (K)',
     'Último: são o que se tira para mexer em tudo o resto.',
     ['Faixa central K-06 por cima das duas tampas']),
    ('15', 'Enchimento, nivelamento e verificação',
     'Ver folha 35. O rover não sai da bancada sem a verificação de folgas no '
     'curso completo.',
     ['Nivelar nos quatro cantos', 'Ensaio de estanqueidade de 12 h']),
]

TORQUES = [
    ('M4 inox A4-70', 2.5, 'motor-roda, janela de policarbonato, carenagem de câmera'),
    ('M5 inox A4-70', 5.0, 'carenagens, tampas, suporte do LiDAR, E-STOP'),
    ('M6 inox A4-70', 10.0, 'chapa de fundo, sapatas, bandejas, batentes, mastro'),
    ('M8 inox A4-70', 25.0, 'suspensão: berço do fole, chapa e berço do pivô'),
    ('M12 do fole', 40.0, 'prato inferior e berço superior do fole'),
]
"""N·m. Valores para inox A4-70 lubrificado, classe de aperto 70 % do escoamento.

O M8 da suspensão aperta QUATRO peças em série, duas delas em alumínio, e uma bucha de
compressão no meio. É a bucha que define o torque: sem ela o tubo 30×30×2 amassa.
"""

CONFERENCIAS = [
    ('Bitola', '530 ± 1 mm, medida face a face das rodas',
     'é a cota que paga a estabilidade desta revisão'),
    ('Entre-eixos', '700 ± 1 mm', 'define a geometria do braço'),
    ('Face de montagem do motor', 'perpendicular 0,3 a A; planeza ISO 2768-K',
     'sugestão 2.3 do fabricante — ver folha 29'),
    ('Alinhamento do braço', 'eixo do pivô paralelo a Y em 0,2/100',
     'desalinhamento força a bucha e come o curso'),
    ('Vão livre nos quatro cantos', '150 ± 3 mm com o ar na pressão mínima',
     'se um canto difere, o nivelamento nasce torto'),
    ('Curso livre', 'girar cada braço de batente a batente, sem o fole',
     'nenhuma interferência em todo o curso'),
    ('Folga braço × chapa de fundo', '≥ 13 mm em compressão total',
     'medida na estação da roda, que é a que mais sobe'),
    ('Repetibilidade do posto VMS', 'montar e desmontar o adaptador 3 ×, dispersão ≤ 0,1°',
     'é o que permite trocar câmera em campo sem recalibrar'),
    ('Altura dos postos de câmera', '450 / 1000 / 1540 ± 2 mm, com gabarito',
     'é a posição de calibração de fábrica; mudá-la exige recalibrar'),
    ('Estanqueidade', 'queda ≤ 0,2 bar em 12 h com o sistema parado',
     'acima disto o compressor cicla e a bateria paga'),
    ('Ciclo do compressor', '≤ 15 % em regime',
     'acima disto há vazamento — é alarme, não tolerância'),
]


# ================================================================= relatório
def mapa() -> list[dict]:
    """A tabela central: cada peça, onde vai, o que toca e como prende."""
    ps, vz = pecas(), vizinhancas()
    out = []
    for item, d in ps.items():
        u = UNIAO.get(item, ('—', '—', None))
        ex = d['exemplares'][0]
        out.append(dict(
            item=item, grupo=d['grupo'], nome=d['nome'], desc=d['desc'], mat=d['mat'],
            qtd=d['qtd'], massa=d['massa'],
            onde=', '.join(sorted({e['onde'] for e in d['exemplares']})),
            x=ex['x'], y=ex['y'], z=ex['z'],
            vizinhas=[v for v in vz.get(item, []) if v in ps],
            tipo_uniao=u[0], como=u[1], torque=u[2]))
    return out


def main(item: str | None = None) -> None:
    mp = mapa()
    if item:
        for d in mp:
            if d['item'] != item.upper():
                continue
            print(f'\n{d["item"]} · {d["nome"]}  ({d["qtd"]} un, {d["massa"]:.3f} kg)')
            print(f'  {d["desc"]} · {d["mat"]}')
            print(f'  onde: {d["onde"]}')
            print(f'  caixa de um exemplar: X {d["x"][0]:.1f}…{d["x"][1]:.1f} · '
                  f'Y {d["y"][0]:.1f}…{d["y"][1]:.1f} · Z {d["z"][0]:.1f}…{d["z"][1]:.1f}')
            print(f'  encosta em: {", ".join(d["vizinhas"]) or "nada"}')
            print(f'  união: {d["tipo_uniao"]} — {d["como"]}'
                  + (f' · {d["torque"]:.1f} N·m' if d['torque'] else ''))
        return

    print('=' * 110)
    print('VTX-RV4 Rev H · MANUAL DE POSIÇÃO — onde vai cada peça')
    print('=' * 110)
    print(f'{"item":6} {"qtd":>3} {"onde":22} {"X":>13} {"Y":>13} {"Z":>13}  encosta em')
    g = None
    for d in mp:
        if d['grupo'] != g:
            g = d['grupo']
            print(f'\n-- {g} · {M.GRUPOS[g]}')
        print(f'{d["item"]:6} {d["qtd"]:3d} {d["onde"][:22]:22} '
              f'{d["x"][0]:6.0f}…{d["x"][1]:<6.0f} {d["y"][0]:6.0f}…{d["y"][1]:<6.0f} '
              f'{d["z"][0]:6.0f}…{d["z"][1]:<6.0f}  {", ".join(d["vizinhas"])}')

    print('\n\nSEQUÊNCIA DE MONTAGEM')
    print('=' * 110)
    for (n, titulo, razao, notas) in SEQUENCIA:
        print(f'\n{n}. {titulo}')
        print(f'   {razao}')
        for nt in notas:
            print(f'   · {nt}')

    print('\n\nTORQUES')
    print('=' * 110)
    for (rosca, nm, onde) in TORQUES:
        print(f'  {rosca:18} {nm:5.1f} N·m   {onde}')

    print('\n\nCONFERÊNCIAS DE ACEITE')
    print('=' * 110)
    for (o, crit, por) in CONFERENCIAS:
        print(f'  {o:34} {crit}')
        print(f'  {"":34} por quê: {por}')


if __name__ == '__main__':
    import sys as _sys
    if hasattr(_sys.stdout, 'reconfigure'):          # o console do Windows é cp1252
        _sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    arg = None
    if '--item' in sys.argv:
        arg = sys.argv[sys.argv.index('--item') + 1]
    main(arg)
