"""Emite os documentos da Rev G em Markdown, a partir dos módulos de cálculo.

Três documentos saem daqui, e nenhum deles é escrito à mão:

* `VTX-RV3-MONTAGEM-G.md` — onde vai cada peça, em que ordem, com que aperto;
* `VTX-RV3-USINAGEM-G.md` — o roteiro de operações, peça por peça;
* `VTX-RV3-ESPACO-G.md` — o espaço interno medido e a conferência de interferência.

A razão de serem gerados: são os documentos que mais se descolam do projeto quando
escritos à mão. Uma cota muda no `modelo.py`, o desenho acompanha porque é paramétrico, e
o texto fica para trás. Gerando, isso não acontece — e se o módulo de cálculo quebrar, o
documento não sai, que é o comportamento certo.

O que NÃO é gerado: o documento da suspensão, a auditoria, o registro de alterações e a
liberação. Esses são argumento de engenharia, e argumento não se extrai de geometria.

```
python relatorios.py           # escreve os três .md
python gerar_docs.py           # converte todos os .md desta pasta em PDF
```
"""

from __future__ import annotations

import pathlib
import sys

AQUI = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent / 'chassi-gaiola'))
sys.path.insert(0, str(AQUI))

import modelo as M  # noqa: E402
import espaco as ES  # noqa: E402
import montagem as MO  # noqa: E402
import suspensao as SU  # noqa: E402
import usinagem as US  # noqa: E402

CABECALHO = """> **VTX-RV3 · Revisão G · 11/10/2026**
> EMITIDO PARA COTAÇÃO E VALIDAÇÃO — NÃO LIBERADO PARA FABRICAÇÃO
>
> Documento **gerado** de `revisao-g/{origem}` sobre a geometria de
> `chassi-gaiola/modelo.py`. Não editar à mão: a próxima geração sobrescreve.
"""


def _tab(cab, linhas):
    out = ['| ' + ' | '.join(cab) + ' |',
           '|' + '|'.join(['---'] * len(cab)) + '|']
    for ln in linhas:
        out.append('| ' + ' | '.join(str(c) for c in ln) + ' |')
    return '\n'.join(out)


# ============================================================ montagem
def montagem_md() -> str:
    mapa = MO.mapa()
    p = [f'# Rover V3 — manual de montagem e posição das peças\n',
         CABECALHO.format(origem='montagem.py'),
         """
## Para que serve este documento

Para montar o rover sem adivinhar. Ele responde três perguntas por peça: **onde** ela vai,
**contra o quê** ela encosta, e **como** ela prende. As duas primeiras são medidas no
modelo paramétrico; a terceira é decisão de projeto declarada.

A coluna "encosta em" é a mais útil na bancada: se a peça vizinha listada não estiver no
lugar quando você for montar, a ordem está errada — volte à seção de sequência.

Referencial: origem no solo, no centro do polígono das quatro rodas. **X** para a frente,
**Y** para a esquerda, **Z** para cima (ISO 8855). Todas as coordenadas em mm.
"""]

    p.append('\n## Mapa de posições\n')
    p.append(f'{len(mapa)} códigos de peça fabricada. A coordenada é a caixa envolvente de '
             'UM exemplar — os demais são espelhados em X, em Y ou nos dois.\n')
    grupo = None
    for d in mapa:
        if d['grupo'] != grupo:
            grupo = d['grupo']
            p.append(f'\n### Grupo {grupo} — {M.GRUPOS[grupo]}\n')
            p.append(_tab(['item', 'nome', 'qt', 'X', 'Y', 'Z', 'encosta em', 'como prende'], []))
        linha = [f'**{d["item"]}**', d['nome'], d['qtd'],
                 f'{d["x"][0]:.0f}…{d["x"][1]:.0f}',
                 f'{d["y"][0]:.0f}…{d["y"][1]:.0f}',
                 f'{d["z"][0]:.0f}…{d["z"][1]:.0f}',
                 ', '.join(d['vizinhas']) or '—',
                 d['como'] + (f' · **{d["torque"]:.0f} N·m**' if d['torque'] else '')]
        p.append('| ' + ' | '.join(str(c) for c in linha) + ' |')

    p.append('\n\n## Sequência de montagem\n')
    p.append('Quinze etapas. A razão de cada uma estar nessa posição vem antes das '
             'instruções, de propósito: é a razão que diz o que acontece se alguém '
             'inverter duas etapas.\n')
    for (n, titulo, razao, notas) in MO.SEQUENCIA:
        p.append(f'\n### {n}. {titulo}\n')
        p.append(f'{razao}\n')
        for nt in notas:
            p.append(f'- {nt}')

    p.append('\n\n## Torques de aperto\n')
    p.append(_tab(['Rosca', 'N·m', 'Onde'],
                  [[r, f'{n:.1f}', o] for (r, n, o) in MO.TORQUES]))
    p.append(f'\n{MO.TORQUES.__doc__ or ""}\n' if False else '')
    p.append("""
Inox A4-70 lubrificado, a 70 % do escoamento. **O M8 da suspensão aperta quatro peças em
série** — berço do fole, bucha de compressão, chapa de fundo e berço do pivô — com duas
delas em alumínio. É a bucha de compressão que define o torque: sem ela, 25 N·m amassam o
tubo 30×30×2 e o aperto se perde na primeira semana de campo.
""")

    p.append('\n## Conferências de aceite\n')
    p.append(_tab(['O que medir', 'Critério', 'Por que importa'],
                  [[o, c, por] for (o, c, por) in MO.CONFERENCIAS]))

    p.append("""
## O que não montar ainda

Três itens deste projeto não existem como componente escolhido, e improvisar qualquer um
deles na bancada custa a desmontagem:

1. **O fole W-15.** Nenhum modelo comercial escolhido (P-20). A interface está desenhada e
   aceita qualquer fole que feche a folha de requisitos da folha 07 — e aceita igualmente
   um cilindro pneumático de mesma área. Um fole fora de requisito muda curso, pressão e
   altura, e nenhum dos três se ajusta depois.
2. **A bucha autolubrificante do pivô** Ø23/Ø20 (P-21). O alojamento está em Ø23 H7.
3. **A bateria.** A altura máxima medida na zona central é
   {alt:.0f} mm, e a caixa estimada tem 130. Ver `VTX-RV3-ESPACO-G`.
""".format(alt=ES.requisitos_de_componente()[0]['altura_maxima']))
    return '\n'.join(p)


# ============================================================ usinagem
def usinagem_md() -> str:
    p = [f'# Rover V3 — roteiro de usinagem\n',
         CABECALHO.format(origem='usinagem.py'),
         """
## Corte e usinagem não são a mesma coisa

Este documento separa as duas, porque elas custam diferente e porque a oficina as faz em
máquinas diferentes:

- **corte** — laser ou serra. Sai pronto do DXF 1:1 em `saida/dxf`, sem tolerância a
  controlar além do contorno;
- **usinagem** — torno, fresa, alargador. Exige operação, referência, tolerância e
  acabamento, e nada disso está no DXF.

**DXF não carrega tolerância.** Quem cortar pelo DXF e usinar sem ler esta tabela e as
folhas 28 a 31 produz peça fora de especificação em todos os furos de ajuste.

## A regra que organiza o roteiro

**Solda primeiro, tolerância depois.** Toda operação marcada *DEPOIS DA SOLDA* é
obrigatoriamente posterior: a solda distorce, e uma tolerância feita antes dela se perdeu
sem que ninguém perceba — até o eixo não entrar.
"""]

    p.append('\n## Resumo por peça\n')
    p.append(_tab(['item', 'nome', 'qt', 'material', 'ops', 'corte', 'usinagem', 'solda',
                   'ops × qt'],
                  [[f'**{r["item"]}**', r['nome'], r['qtd'], r['mat'], r['total'],
                    r['corte'], r['usinagem'], r['solda'], r['ops_por_conjunto']]
                   for r in US.resumo()]))

    p.append('\n\n## Roteiro detalhado\n')
    for it, ops in US.OPERACOES.items():
        g = US.geometria(it)
        if not g:
            continue
        p.append(f'\n### {it} — {M.ITENS[it]["nome"]}\n')
        p.append(f'{g["qtd"]} un · {g["mat"]} · {M.ITENS[it]["desc"]}\n')
        linhas = []
        for (n, op, fer, cota, acab) in ops:
            nat = ('**SOLDA**' if 'SOLDAR' in op
                   else ('corte' if ('laser' in fer or 'serra' in fer) else '**USINAR**'))
            linhas.append([f'{nat} {n}', op, fer, cota, acab])
        p.append(_tab(['op', 'operação', 'ferramenta', 'cota / tolerância', 'acabamento'],
                      linhas))

    p.append('\n\n## Ajustes e folgas\n')
    p.append(_tab(['Interface', 'Ajuste', 'O que ele garante'],
                  [[o, a, por] for (o, a, por) in US.AJUSTES]))

    p.append('\n\n## Notas gerais\n')
    for n in US.NOTAS:
        p.append(f'- {n}')

    c = US.confere()
    p.append('\n\n## Conferência automática\n')
    p.append(f'- roteiro declarado para peça que não existe no modelo: '
             f'**{c["sem_peca"] or "nenhuma"}**')
    p.append(f'- peça do grupo W sem roteiro declarado: '
             f'**{c["sem_roteiro"] or "nenhuma"}**')
    return '\n'.join(p)


# ============================================================ espaço
def espaco_md() -> str:
    it = ES.interferencias()
    v = ES.volume_interno()
    mp = ES.mapa_de_alturas()
    p = [f'# Rover V3 — espaço interno e interferência entre peças\n',
         CABECALHO.format(origem='espaco.py'),
         """
## Duas perguntas, as duas medidas

**As peças se batem?** Mede-se, par a par, se duas caixas envolventes se interpenetram.
O que nasce interpenetrado por projeto — bucha dentro do tubo, colar atravessando a chapa,
pino atravessando a parede — está na lista de encaixes previstos, cada um com a razão.
Qualquer par fora dessa lista é defeito.

**O que cabe lá dentro?** Varre-se o compartimento numa grade de 8 mm e mede-se a altura
livre célula por célula, descontando TODAS as peças do modelo.

### Por que isso precisou ser medido

Imagens conceituais em circulação afirmavam **95,6 L** de volume interno útil, calculados
como 850 × 450 × 250 mm. Nenhuma das três cotas existe no projeto: o compartimento tem
1046 de comprimento, 536 de largura livre e altura que **varia de ponto a ponto**, porque
as barras G-03 da gaiola descem a Z 377 e atravessam o rover em |X| 230 e 330.

O número real, medido, é o da seção seguinte.
"""]
    p.append(f'\n## Interferência entre peças\n')
    p.append(f'{it["pecas"]} peças fornecidas, {it["pares"]} pares verificados.\n')
    p.append(f'**Encaixes previstos: {len(it["previstos"])}**\n')
    p.append(_tab(['par', 'profundidade', 'razão'],
                  [[f'{a} × {b}', f'{f:.1f} mm', r]
                   for (a, b), (f, r) in sorted(it['previstos'].items())]))
    p.append(f'\n**Defeitos: {len(it["defeitos"]) or "nenhum"}**\n')
    if it['defeitos']:
        p.append(_tab(['par', 'profundidade'],
                      [[f'{a} × {b}', f'{f:.1f} mm'] for (a, b), f in sorted(it['defeitos'].items())]))

    p.append('\n\n## Volume interno\n')
    p.append(_tab(['Grandeza', 'Valor'], [
        [f'Caixa bruta do compartimento (1046 × 596 × {v["z_teto"] - v["z_piso"]:.0f})',
         f'{v["volume_bruto_L"]:.2f} L'],
        ['**Volume livre, descontada toda peça**', f'**{v["volume_livre_L"]:.2f} L**'],
        ['Maior altura livre contínua em qualquer ponto', f'{v["maior_vao_mm"]:.0f} mm'],
    ]))
    p.append('\n### Volume aproveitável por altura de componente\n')
    p.append(_tab(['Componente de até', 'Volume aproveitável'],
                  [[f'{h:.0f} mm', f'{vol:.2f} L'] for h, vol in sorted(v['por_altura_L'].items())]))
    p.append('\n### Área de piso por faixa de altura livre\n')
    p.append(_tab(['Faixa de altura livre', 'Área de piso'],
                  [[f'{k:.0f} a {k + 20:.0f} mm', f'{a:.0f} cm²']
                   for k, a in v['area_por_vao_cm2'].items()]))

    p.append('\n\n## Teto de altura por zona — para a folha de compra\n')
    p.append('É o jeito útil de entregar esta conferência: em vez de reprovar um componente '
             'estimado, dizer qual é o teto real da zona, para que a cota entre na folha de '
             'compra junto com a ficha técnica que falta.\n')
    p.append(_tab(['Zona', 'Altura máxima de componente', 'Área', 'Onde'],
                  [[r['zona'], f'**{r["altura_maxima"]:.0f} mm**', f'{r["area_cm2"]:.0f} cm²',
                    r['nota']] for r in ES.requisitos_de_componente()]))

    p.append('\n\n## Cada componente cabe em algum lugar contíguo?\n')
    p.append('Varredura da grade inteira, nas duas orientações. É a pergunta certa — '
             'diferente de "a altura média da zona dá".\n')
    linhas = []
    for (nome, zona, cl, cw, ch, origem) in ES.COMPONENTES:
        r = ES.cabe_em_pe(cl, cw, ch, mp)
        if r['cabe']:
            onde = (f'X {r["x"][0]:.0f}…{r["x"][1]:.0f} · Y {r["y"][0]:.0f}…{r["y"][1]:.0f} '
                    f'(livre {r["altura_livre"]:.0f} mm)')
            linhas.append([nome, f'{cl:.0f}×{cw:.0f}×{ch:.0f}', origem, '**CABE**', onde])
        else:
            linhas.append([nome, f'{cl:.0f}×{cw:.0f}×{ch:.0f}', origem, '**NÃO CABE**',
                           'nenhuma área contígua no compartimento'])
    p.append(_tab(['Componente', 'L×W×H', 'origem do dado', 'veredito', 'posição'], linhas))

    p.append("""

## O que isto responde e o que continua aberto

**Responde**: o volume interno real, a altura livre ponto a ponto, e se os componentes
estimados cabem onde o projeto os quer.

**Continua aberto**: as dimensões dos componentes. Toda linha da tabela acima é
ESTIMATIVA ou FAIXA de catálogo — nenhuma é ficha técnica de peça escolhida. Enquanto for
assim, as bandejas E-01/E-02 e os suportes M-20 **não são cotas de fabricação, são
provisões**. É a pendência P-05/P-13, e nenhuma conta deste documento a fecha.

### O achado que a Rev G produziu aqui

A bandeja de extremidade **E-02 encolheu**. Ela ia de |Y| 105 a 250 e colidia frontalmente
com o colar do fole, que ocupa |Y| 159…259. A faixa que sobra, entre a janela da câmera de
raiz (|Y| ≤ 95) e o colar, é de 100 a 152 mm. A bandeja perdeu mais da metade da área, e
isso é preço de ter suspensão — não erro de desenho.
""")
    return '\n'.join(p)


def main() -> None:
    for nome, texto in (('VTX-RV3-MONTAGEM-G.md', montagem_md()),
                        ('VTX-RV3-USINAGEM-G.md', usinagem_md()),
                        ('VTX-RV3-ESPACO-G.md', espaco_md())):
        (AQUI / nome).write_text(texto, encoding='utf8')
        print(f'  {nome:34} {len(texto) / 1024:6.1f} KB')


if __name__ == '__main__':
    main()
