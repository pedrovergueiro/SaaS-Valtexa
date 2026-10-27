"""Emite os documentos da Rev H em Markdown, a partir dos módulos de cálculo.

Três documentos saem daqui, e nenhum deles é escrito à mão:

* `VTX-RV4-MONTAGEM-H.md` — onde vai cada peça, em que ordem, com que aperto;
* `VTX-RV4-USINAGEM-H.md` — o roteiro de operações, peça por peça;
* `VTX-RV4-ESPACO-H.md` — o espaço interno medido e a conferência de interferência;
* `VTX-RV4-MASTRO-H.md` — rigidez do mastro, vibração e a decisão de não isolar a câmera;
* `VTX-RV4-MODULAR-H.md` — a interface VMS-60: repetibilidade, proteção, energia e banda.

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
import re
import sys

AQUI = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent / 'chassi-gaiola'))
sys.path.insert(0, str(AQUI))

import modelo as M  # noqa: E402
import espaco as ES  # noqa: E402
import montagem as MO  # noqa: E402
import suspensao as SU  # noqa: E402
import usinagem as US  # noqa: E402
import mastro as MA  # noqa: E402
import modular as MD  # noqa: E402
import roteamento as RO  # noqa: E402
import centro_massa as CM  # noqa: E402

CABECALHO = """> **VTX-RV4 · Revisão H · 12/10/2026**
> EMITIDO PARA COTAÇÃO E VALIDAÇÃO — NÃO LIBERADO PARA FABRICAÇÃO
>
> Documento **gerado** de `revisao-h/{origem}` sobre a geometria de
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
    p = [f'# Rover V4 — manual de montagem e posição das peças\n',
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
   {alt:.0f} mm, e a caixa estimada tem 130. Ver `VTX-RV4-ESPACO-G`.
""".format(alt=ES.requisitos_de_componente()[0]['altura_maxima']))
    return '\n'.join(p)


# ============================================================ usinagem
def usinagem_md() -> str:
    p = [f'# Rover V4 — roteiro de usinagem\n',
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
    p = [f'# Rover V4 — espaço interno e interferência entre peças\n',
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
    p.append('\nCuidado ao ler a tabela acima: ela olha **um componente por vez** e aceita qualquer lugar livre do '
             'compartimento. Vários componentes recebem a mesma posição, e a posição pode ficar fora da zona '
             'reservada para eles. A conferência que importa para o leiaute é a seguinte.\n')

    p.append('\n\n## Cada componente cabe na zona reservada para ele, junto com os vizinhos?\n')
    p.append('Planta do componente contra a planta da zona (nas duas orientações), altura contra o teto da zona '
             'e, por zona, a área somada contra a área disponível. Acrescentada em 15/10/2026.\n')
    lz = []
    for z in ES.cabe_na_zona_designada():
        for c in z['componentes']:
            motivo = []
            if not c['planta_ok']:
                motivo.append(f'planta {c["l"]:.0f}×{c["w"]:.0f} > zona {z["planta_zona"][0]:.0f}×{z["planta_zona"][1]:.0f}')
            if not c['altura_ok']:
                motivo.append(f'altura {c["h"]:.0f} > teto {z["teto"]:.0f} mm')
            lz.append([z['zona'], c['componente'], f'{c["l"]:.0f}×{c["w"]:.0f}×{c["h"]:.0f}', c['origem'],
                       '**CABE**' if c['cabe'] else '**NÃO CABE**', '; '.join(motivo) or '—'])
        lz.append([z['zona'], '*soma da zona*', f'{z["area_componentes_cm2"]:.0f} cm²', '',
                   '**CABE**' if z['area_ok'] else '**NÃO CABE**',
                   f'área da zona {z["area_zona_cm2"]:.0f} cm²'])
    p.append(_tab(['Zona', 'Componente', 'L×W×H', 'origem', 'veredito', 'motivo'], lz))
    nao = [z['zona'] for z in ES.cabe_na_zona_designada() if not z['cabe']]
    p.append(f'\n**{len(nao)} de {len(ES.cabe_na_zona_designada())} zonas não comportam o que o projeto põe nelas.** '
             'Com as dimensões estimadas, o leiaute interno das bandejas e do grupo pneumático precisa ser refeito '
             'quando chegarem as fichas técnicas (P-05, P-13).\n')

    p.append("""

## O que isto responde e o que continua aberto

**Responde**: o volume interno real, a altura livre ponto a ponto, se cada componente estimado
cabe em algum lugar do compartimento e se cabe na zona que o projeto reservou para ele.

**Continua aberto**: as dimensões dos componentes. Toda linha da tabela acima é
ESTIMATIVA ou FAIXA de catálogo — nenhuma é ficha técnica de peça escolhida. Enquanto for
assim, as bandejas E-01/E-02 e os adaptadores T-03 **não são cotas de fabricação, são
provisões**. É a pendência P-05/P-13, e nenhuma conta deste documento a fecha.

### O achado que a Rev H produziu aqui

A bandeja de extremidade **E-02 encolheu**. Ela ia de |Y| 105 a 250 e colidia frontalmente
com o colar do fole, que ocupa |Y| 159…259. A faixa que sobra, entre a janela da câmera de
raiz (|Y| ≤ 95) e o colar, é de 100 a 152 mm. A bandeja perdeu mais da metade da área, e
isso é preço de ter suspensão — não erro de desenho.
""")
    return '\n'.join(p)


# ============================================================ mastro
def mastro_md() -> str:
    ex = MA.excitacao()
    vp = MA.veredito(caso='projeto')
    vc = MA.veredito(caso='cheio')
    ve = MA.veredito(caso='entrega')
    comp = MA.comparacao_secoes()
    adot = [c for c in comp if abs(c['d'] - M.D_MASTRO) < 0.1 and abs(c['parede'] - M.E_MASTRO) < 0.1][0]
    v3 = comp[0]
    v4i = comp[1]
    fr = MA.frequencia()
    rz = MA.frequencia_ritz()
    lim = MA.massa_antena_maxima()
    oc = MA.ocupacao_cabos()
    oc2 = MA.ocupacao_cabos(32.0, 2.0)
    t = MA.tensao_mastro()
    am = MD.antena_mastro()

    def ok(b):
        return 'atende' if b else '**não atende**'

    p = ['# Rover V4 — rigidez do mastro e vibração dos sensores\n',
         CABECALHO.format(origem='mastro.py'),
         f"""
## Resumo

O mastro adotado é **Ø{M._n(M.D_MASTRO)} × {M._n(M.E_MASTRO)}**, em alumínio 6061-T6, e a razão está
na tabela abaixo: o projeto descreve um mastro com **mais carga** do que o V4 inicial supôs.

| Estado do mastro | Ø25×2 (V3) | Ø32×2 (V4 inicial) | **Ø32×3 (adotado)** |
|---|---|---|---|
| Entrega: 3 OAK-D por mastro | {MA.frequencia(25, 2, caso='entrega')['freq_Hz']:.2f} Hz | {v4i['freq_entrega_Hz']:.2f} Hz | **{adot['freq_entrega_Hz']:.2f} Hz** |
| Cheio: + 2 térmicas removíveis por mastro | {MA.frequencia(25, 2, caso='cheio')['freq_Hz']:.2f} Hz | {v4i['freq_cheio_Hz']:.2f} Hz | **{adot['freq_cheio_Hz']:.2f} Hz** |
| **Projeto: + antena GNSS no topo ({MA.MASSA_ANTENA:.2f} kg, ESTIMATIVA)** | **{v3['freq_Hz']:.2f} Hz** | **{v4i['freq_Hz']:.2f} Hz** | **{adot['freq_Hz']:.2f} Hz** |
| Contra o requisito de {MA.REQUISITO_FREQ_HZ} Hz (caso de projeto) | {ok(v3['atende'])} | {ok(v4i['atende'])} | {ok(adot['atende'])} |

O requisito de {MA.REQUISITO_FREQ_HZ} Hz é o caso 6 do FEA — *"1ª frequência do mastro ≥ 7,5 Hz"* —,
aberto desde a Rev E e nunca verificado até o V4.

> **Correção a uma versão anterior deste documento.** Ela dava o Ø32×2 como aprovado. Estava
> errada em dois pontos. (1) O Ø32×2 foi calculado para três câmeras por mastro, e o projeto
> descreve cinco postos mais a antena: nessa carga ele dá {v4i['freq_Hz']:.2f} Hz, abaixo do requisito.
> (2) O próprio cálculo já reportava que a margem contra o terreno não fechava — e o texto
> não dizia. Está dito na seção seguinte.

## O que o mastro carrega

| Posto | Z nominal | Estado | Massa estimada do sensor |
|---|---|---|---|
| 3 × OAK-D por mastro | {', '.join(M._n(z) for z in M.CAMERAS_Z)} | fixas, calibradas | {MA.MASSA_OAKD:.2f} kg (ESTIMATIVA) |
| 2 × térmica por mastro | {', '.join(M._n(z) for z in M.Z_TERMICA)} | **removíveis** | {MA.MASSA_TERMICA:.2f} kg (ESTIMATIVA) |
| Antena GNSS no topo | {M._n(M.Z_BASE_ANTENA)} (base) | provisão T-10 | {MA.MASSA_ANTENA:.2f} kg (ESTIMATIVA) + T-10 {MA._massa_t10():.3f} kg |

Cada posto soma {MA._massa_posto():.3f} kg de estrutura VMS (braçadeira, prato, adaptador e protetor),
medidos na geometria do modelo. As massas dos **sensores** não vêm de ficha técnica — nenhum
modelo de térmica ou de antena foi escolhido, e a da OAK-D é pendência P-06.

## Por que a parede engrossa e o diâmetro não

O diâmetro externo fica em {M._n(M.D_MASTRO)} porque o tubo entra na luva Ø{M._n(M.D_LUVA)}×{M._n(M.E_LUVA)}
(furo {M._n(M.D_MASTRO)}), e a luva não pode crescer: já alcança |Y| {adot['alcance_luva']:.0f} e o envelope
externo é 600. Uma seção maior exigiria luva maior, e luva maior exigiria mexer na base do
mastro e na carenagem K-01.

| Seção | 1ª freq. (projeto) | Razão contra o terreno | Δ massa (2 mastros) | Cabe na luva? |
|---|---|---|---|---|"""]
    for c in comp:
        marca = ' ← **adotada**' if c is adot else ''
        p.append(f"| {c['nome']}{marca} | {c['freq_Hz']:.2f} Hz ({'atende' if c['atende'] else 'abaixo'}) | "
                 f"{c['razao']:.2f} | {c['delta_massa_total']:+.3f} kg | {'sim' if c['cabe'] else 'não'} |")
    p.append(f"""
Δ massa é medida contra o Ø32×3 adotado. **Contra o V3 (Ø25×2) o mastro novo pesa
{adot['delta_massa_total'] - v3['delta_massa_total']:+.2f} kg nos dois.**

## A margem contra o terreno NÃO fecha — e isso precisa ficar dito

Dois critérios, e o mastro adotado cumpre só um.

| | Valor | Critério | |
|---|---|---|---|
| 1ª frequência (projeto) | {vp['freq_mastro_Hz']:.2f} Hz | ≥ {MA.REQUISITO_FREQ_HZ} Hz | {ok(vp['atende_requisito'])} |
| Razão contra a excitação do terreno | {vp['razao']:.2f} | ≥ {MA.MARGEM_MINIMA:.1f} | {ok(vp['margem_ok'])} |

A excitação estimada do terreno é {ex['terreno_Hz']:.2f} Hz ({MA.VELOCIDADE_MS} m/s sobre ondas de
{MA.PASSO_IRREGULARIDADE_M} m — **critério de projeto, não medição**). Com razão {vp['razao']:.2f} o mastro
cheio **amplifica** essa excitação em {vp['amplificacao']:.2f}× (sem amortecimento, que é o lado
seguro). A margem de {MA.MARGEM_MINIMA:.1f} só fecha com marcha abaixo de
**{vp['velocidade_maxima_ms']:.2f} m/s**.

Rigidez sozinha não resolve: mesmo o Ø40×3, que nem cabe na luva, chega a razão
{[c for c in comp if c['d'] == 40][0]['razao']:.2f} — ainda abaixo de 2,0. O que decide é o **espectro real**,
ensaio V-12. Enquanto ele não rodar, as opções honestas são: (a) medir; (b) limitar a
marcha com o mastro cheio a ~{vp['velocidade_maxima_ms']:.1f} m/s; (c) aceitar a amplificação.
Não é decisão de desenho — é decisão sua, com o dado na mão. Pendência P-39.

A suspensão pneumática (frequência de canto {ex['suspensao_Hz']:.2f} Hz) atenua o terreno acima de
√2 vezes isso, ou {ex['suspensao_Hz'] * 2 ** 0.5:.1f} Hz — a {ex['terreno_Hz']:.1f} Hz ela já filtra. A razão acima é
contra o **chão**; o que chega ao mastro é menos. Quanto menos, é o que o V-12 mede.

## A antena: quanto o mastro aguenta

Nenhuma antena foi escolhida. O que se pode dizer, e que vira exigência de compra:

| Massa da antena | 1ª freq. | Razão | |
|---|---|---|---|""")
    for x in MA.sensibilidade_antena():
        p.append(f"| {x['massa_antena']:.2f} kg | {x['freq_Hz']:.2f} Hz | {x['razao']:.2f} | "
                 f"{'atende' if x['atende'] else '**abaixo do requisito**'} |")
    p.append(f"""
**Massa máxima da antena para manter {MA.REQUISITO_FREQ_HZ} Hz: {lim:.2f} kg** (sem o adaptador T-10, que
já está contado). Antena mais pesada: Ø32×4, que dá {[c for c in comp if c['d'] == 32 and c['parede'] == 4][0]['freq_Hz']:.2f} Hz,
ao custo do furo para os cabos (ver abaixo) — ou antena na tampa (N-01).

**Onde ela fica é decisão aberta (P-36).** Topo do mastro: céu livre, mas a antena sobe a
{am['z_topo_mm']:.0f} mm contra {am['z_tampa_mm']:.0f} mm na tampa, e uma inclinação de 10° do rover desloca a
antena {am['desloc_10graus_topo_mm']:.0f} mm contra {am['desloc_10graus_tampa_mm']:.0f} mm — a compensação por IMU deixa de ser
opcional. Sob galho de {MA.GALHO_N:.0f} N o topo flete {am['flecha_topo_mm']:.0f} mm. Ensaio V-17 decide com dado.

## Conferência do método

| | Valor |
|---|---|
| Rayleigh, um termo | {fr['freq_rayleigh_Hz']:.2f} Hz |
| Rayleigh-Ritz, 5 modos de viga | {rz:.2f} Hz |
| Diferença | {abs(fr['freq_rayleigh_Hz'] - rz) / rz * 100:.1f} % |
| **Valor adotado** = Rayleigh × {MA.FATOR_ENGASTE} | **{fr['freq_Hz']:.2f} Hz** |

O fator {MA.FATOR_ENGASTE} **não** corrige erro do método — o Ritz mostra que ele é menor que 1 %. Ele
cobre o que o modelo não tem: o engaste real (haste em luva, travada por 2 parafusos) não é
rígido. É **hipótese**, e quem a substitui é o ensaio V-12 com o mastro montado.

## Cabos dentro do tubo — o preço da parede grossa

| Seção | Furo | Ocupação por {oc['n_m12']} cabos M12 + 1 coaxial |
|---|---|---|
| Ø32×2 | Ø{oc2['furo_mm']:.0f} | {oc2['ocupacao'] * 100:.0f} % |
| **Ø32×3 (adotado)** | **Ø{oc['furo_mm']:.0f}** | **{oc['ocupacao'] * 100:.0f} %** (limite {oc['limite'] * 100:.0f} %) |

Com cabos de Ø{oc['d_cabo_mm']:.0f} mm — **ESTIMATIVA**; nenhum cabo foi escolhido. O Ø32×3 está no limite:
cabo mais grosso estoura. É a pendência P-40, e a saída é cabo mais fino ou canaleta externa.

## Deflexão e tensão

Sob galho de {MA.GALHO_N:.0f} N na ponta, seção adotada:

| Z | Flecha | Rotação | Erro a 10 m |
|---|---|---|---|""")
    for d in MA.deflexao():
        p.append(f"| {d['z']:.0f} | {d['flecha_mm']:.1f} mm | {d['rotacao_deg']:.2f}° | {d['erro_a_10m_mm']:.0f} mm |")
    p.append(f"""
Tensão na raiz {t['sigma_MPa']:.1f} MPa, fator de segurança {t['fs']:.2f}. {t['nota']}

## De onde vem a excitação

| Fonte | Frequência |
|---|---|
| Terreno a {MA.VELOCIDADE_MS} m/s, onda de {MA.PASSO_IRREGULARIDADE_M} m | {ex['terreno_Hz']:.2f} Hz |
| Suspensão pneumática (frequência de canto) | {ex['suspensao_Hz']:.2f} Hz |
| Rotação da roda | {ex['rotacao_da_roda_Hz']:.2f} Hz |

## Sensibilidade à massa da câmera

A massa da OAK-D é **estimativa** (P-06). No caso de projeto:

| Massa da OAK-D | Frequência | |
|---|---|---|""")
    for s in MA.sensibilidade():
        p.append(f"| {s['massa_camera']:.2f} kg | {s['freq_Hz']:.2f} Hz | "
                 f"{'atende' if s['atende'] else '**abaixo do requisito**'} |")
    p.append(f"""
**O resultado NÃO é robusto a ela**: com a OAK-D em 0,50 kg o mastro cheio sai do requisito. Hoje o
mastro passa por {(vp['freq_mastro_Hz'] - MA.REQUISITO_FREQ_HZ) / MA.REQUISITO_FREQ_HZ * 100:.0f} % — pouca folga para massas que ninguém mediu. Quando
as fichas técnicas chegarem, `python mastro.py` refaz tudo.

## Rigidez do mastro não é isolamento do sensor

O pedido do V4 manda diferenciar as duas coisas. A diferença não é de grau — é de sinal.

| | Enrijecer o mastro | Isolar a câmera |
|---|---|---|
| O que faz | sobe a frequência própria para longe da excitação | desacopla a câmera do mastro |
| Efeito na imagem | reduz a amplitude do movimento | reduz o borrão de alta frequência |
| Efeito na calibração | **nenhum** — a câmera segue solidária ao rover | **destrói** — a extrínseca passa a depender da aceleração |

{MA.PORQUE_NAO_ISOLAR_CAMERA}

### O único sensor isolado continua sendo o LiDAR

E isolar o LiDAR está certo, porque ele é o caso oposto: mede distância instantânea ponto
a ponto, não integra imagem no tempo, e a extrínseca dele precisa valer na média.

Os coxins G-08 já existem desde a Rev E. A conta de verificação:

| | Valor |
|---|---|
| 4 coxins a {MA.isolamento_lidar()['k_por_coxim_N_mm']:.0f} N/mm sob {MA.isolamento_lidar()['massa_isolada']:.2f} kg | {MA.isolamento_lidar()['freq_Hz']:.0f} Hz |
| Razão contra a excitação | {MA.isolamento_lidar()['razao']:.0f}× |
| Isola ou amplifica? | **{'isola' if MA.isolamento_lidar()['isola'] else 'amplifica'}** |

> Isolador só atenua acima de √2 vezes a própria frequência. Abaixo disso ele **amplifica**.
> A conta depende da massa do LiDAR, que é estimativa (P-11).

## O que continua aberto

- **massas reais**: OAK-D (P-06), térmica (P-30) e antena (P-37) — o mastro tem {(vp['freq_mastro_Hz'] - MA.REQUISITO_FREQ_HZ) / MA.REQUISITO_FREQ_HZ * 100:.0f} % de folga sobre o requisito;
- **espectro real de vibração em campo** (ensaio V-12) — hoje a excitação é critério, e a margem de 2,0 não fecha;
- **FEA do caso 6** — este cálculo é analítico (Rayleigh conferido por Ritz de 5 modos), não
  substitui o modelo de elementos finitos, e o engaste real entra como hipótese de {MA.FATOR_ENGASTE};
- **cabos** (P-40) — o furo do tubo está no limite de ocupação.
""")
    return '\n'.join(p)


# ============================================================ modular
def modular_md() -> str:
    rep = MD.repetibilidade()
    pr = MD.passa_sem_recalibrar()
    pt = MD.protecao()
    e = MD.energia()
    e0, e2 = MD.energia(0), MD.energia(2)
    n = MD.rede()
    n2, n4 = MD.rede(2), MD.rede(4)
    am = MD.antena_mastro()
    p = [f'# Rover V4 — interface modular de sensores VMS-60\n',
         CABECALHO.format(origem='modular.py'),
         f"""
## O que separa "removível" de "modular"

Removível é qualquer coisa com parafuso. **Modular é o que se pode repor no mesmo lugar.**

A fusão de dados usa a matriz extrínseca de cada câmera — onde ela está e para onde aponta,
no referencial do rover — como **constante**, medida uma vez na calibração. Se trocar uma
câmera desloca a próxima em 1°, a calibração morre junto com a peça trocada, e o técnico
que fez a troca na lavoura degradou a navegação sem ter como perceber.

Por isso a face VMS-60 se apoia em **pino**, não em parafuso.

| Interface | Erro angular | Deslocamento a 10 m |
|---|---|---|
| **Pino Ø{M.D_PINO_REF:.0f} H7/h6 + anti-giro a {M.Z_PINO_GIRO:.0f} mm** | **{rep['com_pino_deg']:.3f}°** | **{rep['erro_com_pino_a_10m_mm']:.1f} mm** |
| Só parafuso M5 em furo Ø5,5 | {rep['sem_pino_deg']:.2f}° | {rep['erro_sem_pino_a_10m_mm']:.0f} mm |

Fator **{rep['fator']:.0f}×**. O limite para trocar sem recalibrar é
{MD.TOLERANCIA_EXTRINSECA_DEG:.1f}° — da ordem do próprio ruído de profundidade estéreo a
10 m. Com pino passa com margem {pr['margem']:.1f}×; sem pino, **não passa**.

Dois pinos custam dois furos alargados e um minuto de prensa.

## As três camadas

| Camada | Peça | O que define | Mexer nela exige |
|---|---|---|---|
| 1 · posição | T-01 braçadeira | altura e azimute no mastro | **recalibrar** a extrínseca |
| 2 · interface | T-02 prato VMS | os pinos e a inclinação indexada | recalibrar só se mudar o índice |
| 3 · adaptação | T-03 adaptador | a furação daquele modelo de sensor | **nada** — é a troca de campo |

Trocar a câmera mexe só na camada 3. **Não tocar na braçadeira** é a regra que protege a
calibração.

A inclinação é indexada por pino em {M.N_INDICE} posições, passo de
{M.PASSO_INDICE_DEG:.0f}° — de −{(M.N_INDICE - 1) / 2 * M.PASSO_INDICE_DEG:.0f}° a
+{(M.N_INDICE - 1) / 2 * M.PASSO_INDICE_DEG:.0f}°. Índice por pino repete; aperto por
atrito não.

## Proteção sem nada na frente da lente

O requisito diz: proteger contra impacto **sem grade, aro ou defletor diante das lentes**.
A geometria concorda, e não dá margem:

Com {MD.FOV_H_DEG:.0f}° de campo horizontal, qualquer peça a {pt['avanco_mm']:.0f} mm à
frente da lente teria de estar a **{pt['lateral_necessaria_mm']:.0f} mm** do eixo para não
aparecer na imagem. O prato tem {pt['meia_largura_do_prato_mm']:.0f} mm de meia-largura.
**Lateralmente não cabe** — e é por isso que o projeto não tem grade nenhuma.

Verticalmente cabe: {pt['avanco_mm']:.0f} mm à frente exigem
{pt['vertical_necessaria_mm']:.0f} mm acima, e o protetor T-05 tem
{pt['altura_do_protetor_mm']:.0f}, com {pt['folga_vertical_mm']:.0f} mm de folga.

Daí a solução: **sobrancelha superior sacrificial**, e nada ao lado nem à frente.

| Ameaça | De onde vem a proteção |
|---|---|"""]
    for (a, b) in MD.PROTECAO_POR_ONDE:
        p.append(f'| {a} | {b} |')

    p.append(f"""

{MD.NOTA_IP}

## Matriz de compatibilidade do posto VMS-60

| Módulo | Classe | Massa | Consumo | Cabe no VMS? | O que falta |
|---|---|---|---|---|---|""")
    for c in MD.compatibilidade():
        m = f"{c['massa']:.2f} kg" if c['massa'] else '—'
        w = f"{c['w']:.1f} W" if c['w'] else '—'
        p.append(f"| {c['modulo']} | {c['classe']} | {m} | {w} | "
                 f"{'**sim**' if c['cabe_vms'] else 'não'} | {c['pendencia']} |")

    p.append(f"""

### As classes não são burocracia

| Classe | O que significa para o software |
|---|---|""")
    for k, vdesc in MD.CLASSES.items():
        p.append(f'| {MD.CLASSE_NOME[k]} | {vdesc} |')
    p.append("""
**A ausência de uma câmera de inspeção não pode impedir a inicialização nem a navegação.**
A ausência de LiDAR, GNSS ou IMU tem de impedir. É requisito de software, e a distinção
existe para que o rover continue trabalhando com uma câmera queimada em vez de parar na
lavoura.

## Energia e rede com nove câmeras""")
    p.append(f"""
| Grandeza | Sem térmica | 2 térmicas | **4 térmicas (todas as posições)** |
|---|---|---|---|
| {e['n_oakd']} × OAK-D a {e['w_por_oakd']:.2f} W (teto 802.3af classe 3) | {e0['w_oakd']:.1f} W | {e2['w_oakd']:.1f} W | {e['w_oakd']:.1f} W |
| Térmicas a {MD.W_TERMICA:.1f} W (FAIXA) | 0 W | {e2['w_termica']:.1f} W | {e['w_termica']:.1f} W |
| Terminal satelital (provisão) | {e0['w_satelite']:.0f} W | {e2['w_satelite']:.0f} W | {e['w_satelite']:.0f} W |
| **Total com {(1 - e['rendimento_poe']) * 100:.0f} % de perda de PoE** | **{e0['total_W']:.0f} W** | **{e2['total_W']:.0f} W** | **{e['total_W']:.0f} W** |
| Conversor de {e['capacidade_dcdc_W']:.0f} W, só os sensores | cabe, folga {e0['folga_W']:.0f} W | cabe, folga {e2['folga_W']:.0f} W | cabe, folga {e['folga_W']:.0f} W |
| + Jetson (até {e['w_jetson_max']:.0f} W) + compressor ({e['w_compressor']:.0f} W ao ligar) | **{e0['pico_barramento_12v_W']:.0f} W** | **{e2['pico_barramento_12v_W']:.0f} W** | **{e['pico_barramento_12v_W']:.0f} W** |
| Conversor de {e['capacidade_dcdc_W']:.0f} W, no pico do barramento | {'cabe' if e0['cabe_no_pico'] else '**não cabe**'}, {e0['folga_pico_W']:.0f} W | {'cabe' if e2['cabe_no_pico'] else '**não cabe**'}, {e2['folga_pico_W']:.0f} W | {'cabe' if e['cabe_no_pico'] else '**não cabe**'}, {e['folga_pico_W']:.0f} W |
| Portas Ethernet (OAK-D + LiDAR + Jetson + satélite + térmicas por Ethernet) | {n['portas_necessarias']} | {n2['portas_necessarias']} | {n4['portas_necessarias']} |
| Cabe em switch de {n['portas_do_switch']} portas? | **não** | **não** | **não** |
| Cabe em switch de {n['portas_com_12']} portas? | {'sim' if n['cabe_em_12'] else 'não'} | {'sim' if n2['cabe_em_12'] else 'não'} | **{'sim' if n4['cabe_em_12'] else 'não — exige 16 portas'}** |
| Banda agregada | {n['banda_total_Mbps']:.0f} Mbit/s | {n['banda_total_Mbps']:.0f} Mbit/s | {n['banda_total_Mbps']:.0f} Mbit/s |

**A 9ª câmera dói na rede, e o barramento de 12 V dói no pico.** São {n['portas_necessarias']} portas com o LiDAR, a
ligação à Jetson e o terminal satelital, e o switch PoE de 8 não atende. Trocar por um de 12 portas PoE+ é **item
novo de BOM**, não ajuste de desenho (P-31). O de 12 portas não sobra para nenhuma térmica por Ethernet; com
térmicas Ethernet, 16 portas.

Na energia, os sensores sozinhos cabem no conversor de {e['capacidade_dcdc_W']:.0f} W, mas ele também alimenta a Jetson e o
compressor da suspensão (CABOS-H, ligação 5). Com o compressor ligado o pico passa do conversor: conversor maior,
um segundo conversor só para a suspensão, ou o compressor travado durante a captura (P-17). Correção de
15/10/2026: até então esta seção conferia só os sensores contra o conversor e contava 10 portas, sem a ligação
à Jetson e sem o terminal satelital. Se a térmica escolhida for USB, ela entra pela Jetson e
não ocupa porta — o modelo ainda não existe (P-30). A banda é {n['ocupacao_uplink'] * 100:.0f} % de um uplink de 1 Gbit/s
com as OAK-D; as térmicas somam pouco a ela.

""")

    p.append(f"""## Módulo térmico removível — o que é e o que ainda não é

A ideia do projeto: a OAK-D é **fixa e calibrada**; a térmica é **módulo removível**, com
desconexão rápida. No V4 isso se resolve **sem criar interface nova**: o posto térmico usa a
mesma braçadeira T-01, o mesmo prato T-02 e a mesma face VMS-60 da OAK-D. Muda o adaptador
(**T-04**) e a forma de apertar.

| | OAK-D (fixa) | Térmica (removível) |
|---|---|---|
| Adaptador | T-03, com a furação da OAK-D | **T-04**, sem furação de sensor (modelo não escolhido) |
| 4 parafusos M5 da face | cabeça sextavada interna, com chave | **imperdíveis, de aperto manual**, sem ferramenta |
| Pinos de referência Ø{M.D_PINO_REF:.0f} / Ø{M.D_PINO_GIRO:.0f} | ficam no prato | **ficam no prato** — é o que faz o módulo voltar à mesma pose |
| Conector | M12 de painel, fixo no posto | **M12 de desconexão no cabo do módulo** |
| Posição | andar nominal, ajustável | a meio caminho entre dois andares ({', '.join(M._n(z) for z in M.Z_TERMICA)}), ajustável |
| Calibração ao trocar | verificação | verificação (mesmo procedimento, sem ferramenta) |

**Envelope que o módulo pode ocupar: {M._n(M.ENVELOPE_TERMICA[0])} × {M._n(M.ENVELOPE_TERMICA[1])} × {M._n(M.ENVELOPE_TERMICA[2])} mm.** Não é a dimensão de uma
câmera — é o que já está desenhado: o prato tem 72 × 64 e a sobrancelha T-05 se estende 46 mm.
Uma câmera maior pede protetor novo. E o módulo tem de **deixar livre o acesso às cabeças dos
4 parafusos**, senão não é removível à mão: se o corpo da câmera os cobrir, o T-04 ganha um
espaçador (P-38).

**O que não está fechado:** a repetibilidade com parafuso de aperto manual (ensaio V-16 — o V-10
mede só o parafuso de ferramenta), o modelo da câmera (P-30) e o torque de aperto manual que
o procedimento deve exigir. O número de {rep['com_pino_deg']:.3f}° vale para o pino; o que o aperto manual
faz à folga entre o pino e o furo é medição, não cálculo.

## A antena GNSS RTK: duas provisões, uma decisão aberta

O esboço do projeto põe a antena no **topo do mastro**. O V3 tinha desenhado a N-01 na tampa
traseira. O V4 deixa as duas provisões e **não decide** (P-36):

| | Topo do mastro (T-10) | Tampa traseira (N-01) |
|---|---|---|
| Altura do plano de apoio da antena | {M._n(am['z_topo_mm'])} mm | {M._n(am['z_tampa_mm'])} mm |
| Deslocamento da antena por 10° de inclinação do rover | {am['desloc_10graus_topo_mm']:.0f} mm | {am['desloc_10graus_tampa_mm']:.0f} mm |
| Custo no mastro | 1ª freq. {am['freq_sem_antena_Hz']:.2f} → {am['freq_com_antena_Hz']:.2f} Hz | nenhum |
| Massa máxima da antena | **{am['massa_antena_max_kg']:.2f} kg** | sem limite estrutural |
| Interface | rosca 5/8"-11 UNC (A VALIDAR) + furo Ø{M._n(M.D_CABO_ANTENA)} para o cabo | chapa 110×110×5, 4 × M5 |
| O que o software precisa | **compensação de inclinação por IMU, obrigatória** | recomendada |

Nenhum número de desempenho de GNSS está aqui: multicaminho, tempo para fixar e perdas de fix
dependem de ensaio (V-17).

""")

    p.append("""## O que o software tem de fazer""")
    p.append("""
| Requisito | O que significa |
|---|---|""")

    for (a, b) in MD.REQUISITOS_SOFTWARE:
        p.append(f'| {a} | {b} |')

    p.append("""

## Trocar um sensor em campo

| n | O que fazer | Por quê |
|---|---|---|""")
    for (a, b, c) in MD.PROCEDIMENTO_TROCA:
        p.append(f'| {a} | {b} | {c} |')
    p.append("""
**O passo 5 é o que importa:** não tocar na braçadeira T-01. É ela que define altura e
azimute, e é a única camada cuja alteração exige recalibrar.

### Trocar o módulo térmico (sem ferramenta)

| n | O que fazer | Por quê |
|---|---|---|""")
    for (a, b, c) in MD.PROCEDIMENTO_TROCA_TERMICA:
        p.append(f'| {a} | {b} | {c} |')
    p.append("""

## Ensaios que esta arquitetura exige

| Cód. | Ensaio | Aceite |
|---|---|---|""")
    for (a, b, c) in MD.PLANO_DE_ENSAIO:
        p.append(f'| {a} | {b} | {c} |')
    p.append("""
**Nenhum destes ensaios foi feito.** O V-10 é o que valida ou derruba o argumento do pino,
que é a base de toda esta arquitetura — enquanto ele não rodar, a repetibilidade calculada
é cálculo, não medição.

## Pendências

| Cód. | Assunto | Grau | O que falta |
|---|---|---|---|""")
    for (a, b, c, d) in MD.PENDENCIAS:
        p.append(f'| **{a}** | {b} | {c} | {d} |')
    return '\n'.join(p)


_PROTEGIDOS = re.compile(r'(?:fórmula|tabela|seção|item|tab\.) \d+\.\d+|802\.3\w*|\b\d+\.\d+\.\d+\b|[\w-]+\.(?:py|md|pdf|dxf|csv|html|stl)\b|`[^`]*`')


def _virgula(texto: str) -> str:
    """Decimal em português: 7.88 vira 7,88. Nomes de arquivo, código e normas ficam como estão."""
    guardados = []

    def guarda(m):
        guardados.append(m.group(0))
        return '\x00' + str(len(guardados) - 1) + '\x00'
    t = _PROTEGIDOS.sub(guarda, texto)
    t = re.sub(r'(?<=\d)\.(?=\d)', ',', t)
    return re.sub('\x00(\\d+)\x00', lambda m: guardados[int(m.group(1))], t)


# ============================================================ cabos
def cabos_md() -> str:
    ligs = RO.interligacoes()
    ps = RO.passagens()
    r = RO.resumo_para_bom()
    p = ['# Rover V4 — interligação e roteamento de cabos\n',
         CABECALHO.format(origem='roteamento.py'),
         f"""
## O que este documento é — e o que não é

É um **diagrama funcional de interligação**, as **regras de roteamento** propostas, o **inventário das
passagens pela estrutura** e **comprimentos ESTIMADOS** para cotar o cabo. **Não é um desenho de chicote**, e
não é possível fazê-lo ainda:

- a posição dos componentes dentro do compartimento **não está fechada** — a bateria estimada
  (460 × 350 × 130) não cabe, e as posições "onde cabe" de Jetson, driver e BMS se sobrepõem entre si
  (`python espaco.py`, seção 4);
- bitola, fusível, pinagem e conector de cada equipamento dependem de fichas técnicas que o projeto não tem
  (P-05, P-13);
- o **grau IP** de qualquer conexão só sai de ensaio (V-11) e **não é declarado**.

O desenho está na **folha 42** do caderno.

## Interligações

| # | De → para | Classe | Qtd | Meio | Passagem pela estrutura | Comprimento |
|---|---|---|---|---|---|---|"""]
    for i, n in enumerate(ligs, 1):
        comp = f'≥ {n["comp_m"]:.1f} m' if n['comp_m'] else '—'
        p.append(f'| {i} | {n["de"]} → {n["para"]} | {RO.CLASSES[n["classe"]]} | {n["qtd"]} | {n["meio"]} | '
                 f'{n["passagem"]} | {comp} |')
    p.append(f"""
Comprimentos **ESTIMADOS**: o trecho vertical vem da altura de cada posto no mastro; o percurso interno até
o switch é **suposição** de {RO.PERCURSO_INTERNO_MM:.0f} mm (a posição do switch não está fechada, P-31), com
folga de {(RO.FOLGA_CABO - 1) * 100:.0f} %. Servem para orçar o cabo, nunca para cortá-lo.

## Para a cotação do cabo

| Item | Quantidade | Comprimento total |
|---|---|---|
| M12 das OAK-D do mastro | {r['n_m12_oakd']} | {r['m_oakd']:.1f} m |
| M12 das câmeras de extremidade (C7, C8) e de raiz (C9) | {r['n_m12_extremidade']} | — |
| M12 das térmicas (opcional) | até {r['n_m12_termica_max']} | até {r['m_termica_max']:.1f} m |
| Coaxial da antena GNSS no mastro (opcional) | até {r['n_coax_max']} | {r['m_coax']:.1f} m cada |

## Passagens pela estrutura

| Onde | Quem passa | Estado | Nota |
|---|---|---|---|""")
    for q in ps:
        p.append(f'| {q["onde"]} | {q["quem"]} | **{q["estado"]}** | {q["nota"]} |')
    p.append("""
**O que isto revelou, e foi corrigido nesta revisão:** o berço do terminal de satélite (T-07) tinha o furo
de cabo e os 6 furos de fixação, mas a **tampa K-05 embaixo dele não tinha nenhum** — o berço não tinha onde
ser parafusado, nem por onde passar o cabo. Foram acrescentados à K-05, ao DXF e à lista de fixadores (F-58). E o
passa-cabo F-46 do V3 era para furo Ø32, que não cabe numa luva Ø42: agora são F-59 (Ø20, saída da luva) e F-60
(Ø12, entrada no tubo).

**O que continua aberto:** a entrada dos cabos das câmeras C7 e C8 no compartimento. Elas estão sob o chassi
(Z 210) e o compartimento começa em Z 250; não há furo na chapa de fundo nem passa-cabo previsto.

## Regras de roteamento — propostas

| Regra | O que diz |
|---|---|""")
    for (a, b) in RO.REGRAS:
        p.append(f'| {a} | {b} |')
    return '\n'.join(p)


# ============================================================ centro de massa
def _agrupa_inventario(itens):
    ac = {}
    for i in itens:
        a = ac.setdefault((i.nome, i.origem), [0.0, 0.0, 0.0, 0.0, 0])
        a[0] += i.kg
        a[1] += i.kg * i.x
        a[2] += i.kg * i.y
        a[3] += i.kg * i.z
        a[4] += 1
    rows = [(n, o, a[4], a[0], a[1] / a[0], a[2] / a[0], a[3] / a[0]) for (n, o), a in ac.items()]
    return sorted(rows, key=lambda r: -r[3])


def centro_massa_md() -> str:
    rc = CM.reconcilia()
    est = CM.todos()
    pr = [e for e in est if e['estado'] == 'projeto'][0]
    en = [e for e in est if e['estado'] == 'entrega'][0]
    ch = [e for e in est if e['estado'] == 'cheio'][0]
    vm = CM.vao_maximo('projeto')
    sens = CM.sensibilidades('projeto')
    cargas = CM.carga_util('projeto')
    c100 = CM.efeito_por_100g('entrega')
    eq = CM.equilibrio_lateral('projeto')
    curvas = CM.tabela_curvas('projeto')
    m_su, r_su = SU.massa(), SU.roll()
    zlim_min = CM.z_max_carga('projeto')
    zlim_max = CM.z_max_carga('projeto', elevacao_mm=M.AJUSTE_ALTURA)
    zcg_lim = CM.z_cg_max(pr['kg'], pr['y'], CM.ENVELOPE_BASELINE)
    v_op = MA.VELOCIDADE_MS
    m_cad = sum(i.kg for i in pr['itens'] if i.origem == 'CAD')
    m_bloco = [i.kg for i in pr['itens'] if i.nome == 'Bloco restante da baseline'][0]
    eq400 = c100[-1]['dz'] * en['kg'] / (M.Z_PROT - en['z'])
    y_grupo = -sum(i.kg * i.y for i in pr['itens'] if i.nome.startswith(('W-17a', 'W-17b'))) / pr['kg']

    def lin_estado(e, rotulo):
        return [rotulo, f"{e['kg']:.1f}", f"{e['x']:+.1f}", f"{e['y']:+.1f}", f"{e['z']:.0f}",
                f"{e['lateral']['tomba_deg']:.1f}°", f"{e['envelope_deg']:.1f}°",
                f"{e['rampa_subindo']['tomba_deg']:.1f}° / {e['rampa_descendo']['tomba_deg']:.1f}°",
                f"{e['a_lat']['a_g']:.2f}"]

    tab_estados = _tab(
        ['Estado', 'Massa kg', 'X mm', 'Y mm', 'Z mm', 'Tomb. lateral', 'Envelope', 'Rampa sobe / desce',
         'a lat. máx (g)'],
        [lin_estado(en, '**entrega** — 9 OAK-D, sem térmica'),
         lin_estado(ch, '**cheio** — + 4 térmicas'),
         lin_estado(pr, '**projeto** — + antena em um mastro'),
         lin_estado([e for e in est if e['estado'] == 'projeto2'][0], 'projeto, antena nos dois mastros'),
         lin_estado(vm, '**projeto, vão máximo** (+30 mm)')])

    tab_inv = _tab(['Item', 'Origem', 'Qtd', 'kg', 'X', 'Y', 'Z'],
                   [[n, o, q, f'{m:.2f}', f'{x:+.0f}', f'{y:+.0f}', f'{z:.0f}']
                    for (n, o, q, m, x, y, z) in _agrupa_inventario(pr['itens'])])

    tab_100 = _tab(['Altura Z', 'Sobe o CG', 'Muda o tombamento lateral (negativo = tomba antes)'],
                   [[f"{e['z']:.0f} mm", f"{e['dz']:+.2f} mm", f"{e['dlat']:+.3f}°"] for e in c100])

    tab_curva = _tab(['Raio da curva', f'a centrípeta a {v_op} m/s', 'Fator de segurança contra tombar',
                      'Velocidade com FS 2'],
                     [[f"{c['raio']:.0f} m", f"{v_op ** 2 / c['raio']:.2f} m/s² ({v_op ** 2 / c['raio'] / CM.G:.2f} g)",
                       f"{pr['a_lat']['a_ms2'] / (v_op ** 2 / c['raio']):.1f}", f"{c['v']:.1f} m/s"] for c in curvas])

    tab_carga = _tab(['Carga de 25 kg a Z', 'Massa kg', 'CG Z mm', 'Tomb. lateral', 'Envelope', 'Rampa sobe'],
                     [[f"{c['z_carga']:.0f} mm", f"{c['kg']:.1f}", f"{c['z']:.0f}", f"{c['lat']:.1f}°",
                       f"{c['env']:.1f}°", f"{c['rampa']:.1f}°"] for c in cargas])

    tab_y = _tab(['Quem desloca o CG para o lado', 'Momento kg·mm', 'Efeito no Y do CG'],
                 [[n, f'{mo:+.0f}', f'{dy:+.2f} mm'] for (n, mo, dy) in CM.contribuicao_y(pr['itens'])])

    tab_sens = _tab(['Se isto estiver errado', 'CG Z', 'CG Y', 'Tomb. lateral', 'Dentro de |Y| ≤ 15?'],
                    [[s['rotulo'], f"{s['z']:.0f} ({s['dz']:+.1f})", f"{s['y']:+.1f}",
                      f"{s['lat']:.1f}° ({s['dlat']:+.2f})", 'sim' if s['dentro'] else '**NÃO**'] for s in sens])

    tab_div = _tab(['', 'suspensao.py até 15/10/2026 (CG da Rev F ajustada)',
                    'suspensao.py agora', 'Este inventário (V4, estado projeto)'], [
        ['Massa da estabilidade', f"{m_su['massa']:.1f} kg", f"{r_su['massa']:.1f} kg", f"{pr['kg']:.1f} kg"],
        ['Altura do CG', f"{m_su['zcg']:.1f} mm", f"{r_su['zcg']:.1f} mm", f"{pr['z']:.1f} mm"],
        ['Tombamento lateral', '39,92°', f"{r_su['tombamento_deg']:.2f}° (sem a assimetria em Y)",
         f"{pr['lateral']['tomba_deg']:.2f}°"],
        ['Envelope (fórmula 6.1)', '20,89°', f"{r_su['envelope_deg']:.2f}°", f"{pr['envelope_deg']:.2f}°"]])

    z_min_txt = (f'{zlim_min:.0f} mm' if zlim_min else 'nenhuma altura')
    z_min_frase = (f'**abaixo de {zlim_min:.0f} mm**' if zlim_min else '**nenhuma altura serve**')
    z_max_frase = (f'**abaixo de {zlim_max:.0f} mm**' if zlim_max
                   else '**nenhuma altura serve, nem rente à chapa de fundo**')

    p = ['# Rover V4 — centro de massa e margem contra tombamento\n',
         CABECALHO.format(origem='centro_massa.py'),
         f"""
## Resposta

Com o mastro cheio e a antena em um mastro, o centro de massa fica a **{pr['z']:.0f} mm do solo**, **{abs(pr['x']):.0f} mm
atrás** e **{abs(pr['y']):.0f} mm à direita** do centro do entre-eixos, para **{pr['kg']:.0f} kg**. Pelo cálculo estático, o
rover só tomba de lado acima de **{pr['lateral']['tomba_deg']:.0f}° de rampa** ou de **{pr['a_lat']['a_g']:.2f} g** em curva; o envelope conservador de operação
(fórmula 6.1 da baseline) é **{pr['envelope_deg']:.1f}°**. **A margem é menor do que o pacote publicava**: o que mais a consome é o
vão máximo da suspensão, a carga útil acima de Z {z_min_txt} e o mastro cheio; o grupo pneumático de um lado só gasta
metade da folga lateral.

{tab_estados}

* **Tombamento lateral em rampa: {pr['lateral']['tomba_deg']:.1f}°** (rígido seria {pr['lateral']['rigido_deg']:.1f}°; a carroceria rola
  {pr['lateral']['rolagem_deg']:.1f}° sobre os foles até o curso acabar). Rampa longitudinal: {pr['rampa_subindo']['tomba_deg']:.1f}° subindo,
  {pr['rampa_descendo']['tomba_deg']:.1f}° descendo — o CG está {abs(pr['x']):.0f} mm atrás do centro, e isso piora a subida.
* **Envelope conservador (fórmula 6.1 da baseline, que inclui obstáculo de 60 mm e fator de segurança 1,3):
  {pr['envelope_deg']:.1f}°** no vão mínimo e **{vm['envelope_deg']:.1f}°** no vão máximo. A baseline Rev E publica
  {CM.ENVELOPE_BASELINE}°. O repositório não traz um mínimo exigido; comparo com esse valor porque é o único escrito.
* **Aceleração lateral que levanta as rodas: {pr['a_lat']['a_g']:.2f} g** ({pr['a_lat']['a_ms2']:.1f} m/s²). A {v_op} m/s, curva de 1 m de
  raio pede {v_op ** 2:.2f} m/s²: fator de segurança {pr['a_lat']['a_ms2'] / v_op ** 2:.1f}.
* **O que o mastro cheio custa:** da entrega ao projeto (térmicas e antena) o CG sobe {pr['z'] - en['z']:.0f} mm e o envelope cai
  {en['envelope_deg'] - pr['envelope_deg']:.1f}°. Até 15/10/2026 `suspensao.py` usava um CG ainda mais baixo ({m_su['zcg']:.0f} mm) — ver abaixo.

## A divergência com `suspensao.py` foi resolvida em 15/10/2026

Até 15/10/2026, `suspensao.py` calculava a rolagem e o envelope a partir da massa e do CG da **Rev F do V3**
({SU.MASSA_REV_F} kg, {SU.ZCG_REV_F} mm), trocando o grupo S pelo W — sem o mastro do V4. Dava 39,92° de tombamento e
20,89° de envelope, otimistas. Agora `suspensao.roll()` usa este inventário (`suspensao.cg_v4()`), e os foles continuam
dimensionados na massa alta de `suspensao.massa()` ({m_su['massa']:.1f} kg), que é o lado seguro para a pressão:

{tab_div}

A conclusão da arquitetura não mudou — a suspensão pneumática em bitola 530 continua mais estável que o balancim rígido
em 470 **no mesmo CG** —, mas a margem sobre os {CM.ENVELOPE_BASELINE}° da baseline ficou em décimos de grau. O documento
`VTX-RV4-SUSPENSAO-H` e o registro de alterações foram corrigidos; **a folha 07 do caderno e o documento técnico do pacote
ainda trazem os números antigos** até a próxima emissão do caderno.

## Como foi calculado

Soma de momentos de um inventário de massa, em ISO 8855 (X à frente, Y à esquerda, Z para cima), origem no centro do
entre-eixos e no solo. Cada linha traz a **origem** do número:

| Origem | Significa |
|---|---|
| CAD | massa e posição saem do modelo (densidade × volume): {m_cad:.2f} kg de peças fabricadas neste estado, mais 1,4 kg de fixadores estimados |
| DATASHEET | ficha de fabricante (motor-roda MPW86, 4,5 kg; o ZLTECH da compra recomendada **não publica** a massa) |
| BASELINE | tabela 5.1 da Rev E (bateria de 36,5 kg) |
| ZONA | posição = centro da zona que `espaco.py` reserva para o componente |
| FAIXA | massa de faixa de catálogo para a classe do componente (mola, sensor de altura, compressor), não de ficha |
| ESTIMATIVA | massa suposta, sem ficha (OAK-D 0,25 kg, térmica 0,20 kg, antena 0,30 kg) |
| DERIVADO | calculado do resto: o **bloco restante da baseline** |

A tabela 5.1 da baseline **não está no repositório com rótulos**, só a lista de números. Por isso o que a baseline
"mantém" ({rc['kg']:.2f} kg) entra aberto em três partes: os 4 motores-roda (18,0 kg, posição conhecida), a bateria (36,5 kg, no
centro dos batentes B-01) e um **bloco restante** de {m_bloco:.2f} kg cuja massa é conhecida e cuja posição
**não é**. O Z desse bloco é derivado do CG publicado da baseline (297 mm); X e Y são assumidos no centro.

**Conferência:** o inventário sem os acréscimos do V4 dá **{rc['kg']:.2f} kg e Z {rc['z']:.1f} mm**, igual ao consolidado do caderno
({rc['kg_caderno']:.2f} kg, {rc['z_caderno']:.1f} mm) — {'reproduz' if rc['ok'] else 'NÃO reproduz'}. A função de tombamento foi conferida contra
`suspensao.roll()`: com as mesmas entradas dá o mesmo resultado ({r_su['tombamento_deg']:.2f}°, rolagem {r_su['rolagem_deg']:.2f}°, envelope
{r_su['envelope_deg']:.2f}°).

## Inventário — estado "projeto"

{tab_inv}

Em linhas com várias unidades, X, Y e Z são o centroide delas.

**Não está contado** (sem massa no projeto): switch PoE de 12 portas, terminal de satélite, cabos M12 e coaxial, conectores,
lama e poeira acumuladas, o ar do reservatório. Cada 1 kg a 800 mm de altura sobe o CG cerca de {(800 - pr['z']) / (pr['kg'] + 1):.1f} mm.
A carga útil de 25 kg tem massa conhecida e posição desconhecida: está à parte, abaixo.

## Quanto custa cada 100 g

{tab_100}

100 g no topo do mastro (Z 1800) sobem o CG tanto quanto **{eq400:.1f} kg** postos no topo da proteção (Z {M.Z_PROT:.0f}). É por isso que a
antena e as térmicas, que parecem leves, aparecem no resultado.

## Em movimento

{tab_curva}

O raio é **cenário**, não requisito. Aceleração e frenagem: o rover levanta a frente ao acelerar a **{pr['a_arranque']['a_g']:.2f} g** e a
traseira ao frear a **{pr['a_frenagem']['a_g']:.2f} g**; abaixo disso, o limite é a aderência dos pneus e o torque dos motores, não o
tombamento. O cálculo é estático com a rolagem dos foles: **não inclui** a flexão do mastro, a deformação do pneu nem solo mole,
e mede a bitola no centro da roda ({M.BITOLA / 2:.0f} mm), não na borda externa do pneu, o que é conservador.

## Carga útil de 25 kg

A baseline fala em carga útil de 25 kg e **não diz onde ela fica**. Três alturas hipotéticas, centrada:

{tab_carga}

Para manter o envelope em {CM.ENVELOPE_BASELINE}°, a carga útil tem de ficar {z_min_frase} com o vão mínimo; com o
vão máximo, {z_max_frase}. O deck do quadro está a Z {M.Z_DECK:.0f} e o topo da proteção a Z {M.Z_PROT:.0f}: **a carga útil tem de ficar na altura do deck ou abaixo**,
ou o envelope cai abaixo do que a baseline publica.

## Assimetria lateral

A fórmula 6.1 da baseline já supõe que o CG pode estar até **{CM.E_Y_BASELINE:.0f} mm** fora do plano central. O inventário dá **{pr['y']:+.1f} mm**:
dentro, mas gastando metade da folga, e quase tudo vem de um único grupo.

{tab_y}

O grupo pneumático está na zona direita (Y de −250 a −60 em `espaco.py`). **A bateria sozinha não zera isso:** para anular o Y do
CG ela teria de andar {eq['bateria_precisa_mm']:+.1f} mm, e a folga entre os batentes B-01 e a caixa estimada é de, no máximo, ±{eq['folga_max_mm']:.1f} mm
(centros dos batentes, espessura não descontada). Resta centralizar o compressor e o reservatório, ou espelhar parte do grupo.
**Jetson (esquerda) e driver + BMS (direita) estão em bandejas opostas e as massas deles não constam do projeto** — se uma delas pesar
alguns quilos a mais que a outra, o Y do CG anda ±2 mm por quilo de diferença.

## O que muda se uma suposição estiver errada

{tab_sens}

A linha **LIMITE** não é previsão: é o pior caso geométrico (todo o bloco restante de 14,5 kg numa bandeja lateral). Mostra que a
premissa de 15 mm **pode ser violada** se as massas da eletrônica não forem balanceadas.

## O que fazer

1. **Pesar.** Rover montado, em quatro balanças (uma por roda), no plano: dá X e Y do CG com a precisão da balança. Z sai por
   inclinação: levantando o eixo dianteiro de um ângulo θ e lendo o acréscimo ΔR na carga do eixo traseiro, h = ΔR · L / (W · tan θ),
   com L o entre-eixos e W o peso. Isto é **ensaio proposto**; ele ainda não tem número no plano de validação (folha 26).
2. **Centralizar o grupo pneumático** (ou espelhar compressor e reservatório): tira {y_grupo:.1f} mm do desvio; o Y do CG iria de
   {pr['y']:+.1f} para cerca de {pr['y'] + y_grupo:+.1f} mm.
3. **Fixar a posição da carga útil**, na altura do deck ou abaixo: no máximo {z_min_txt} com o vão mínimo.
4. **Decidir se o envelope de {CM.ENVELOPE_BASELINE}° é requisito.** Com o mastro cheio e a suspensão no vão máximo ele não se mantém ({vm['envelope_deg']:.1f}°). Se for, a
   saída é limitar o vão máximo, reduzir massa no alto (térmicas e antena) ou alargar a bitola.
5. **Reancorar `suspensao.py`** no inventário do V4 (decisão do engenheiro; ver a divergência acima) e refazer o envelope da suspensão.
6. Qualquer sensor novo no mastro entra por `efeito_por_100g` antes de ser aprovado.

**Este documento é cálculo sobre massas estimadas e um bloco da baseline sem posição. Não é pesagem e não valida o
rover contra tombamento.** O CG do rover real só se conhece com ele montado e pesado.
"""]
    return '\n'.join(p)


def main() -> None:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    for nome, texto in (('VTX-RV4-MONTAGEM-H.md', montagem_md()),
                        ('VTX-RV4-USINAGEM-H.md', usinagem_md()),
                        ('VTX-RV4-ESPACO-H.md', espaco_md()),
                        ('VTX-RV4-MASTRO-H.md', mastro_md()),
                        ('VTX-RV4-MODULAR-H.md', modular_md()),
                        ('VTX-RV4-CABOS-H.md', cabos_md()),
                        ('VTX-RV4-CENTRO-MASSA-H.md', centro_massa_md())):
        texto = _virgula(texto)
        (AQUI / nome).write_text(texto, encoding='utf8')
        print(f'  {nome:34} {len(texto) / 1024:6.1f} KB')


if __name__ == '__main__':
    main()
