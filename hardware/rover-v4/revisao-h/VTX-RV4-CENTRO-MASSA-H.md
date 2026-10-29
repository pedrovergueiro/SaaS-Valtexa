# Rover V4 — centro de massa e margem contra tombamento

> **VTX-RV4 · Revisão H · 12/10/2026**
> EMITIDO PARA COTAÇÃO E VALIDAÇÃO — NÃO LIBERADO PARA FABRICAÇÃO
>
> Documento **gerado** de `revisao-h/centro_massa.py` sobre a geometria de
> `chassi-gaiola/modelo.py`. Não editar à mão: a próxima geração sobrescreve.


## Resposta

Com o mastro cheio e a antena em um mastro, o centro de massa fica a **330 mm do solo**, **8 mm
atrás** e **0 mm à direita** do centro do entre-eixos, para **146 kg**. Pelo cálculo estático, o
rover só tomba de lado acima de **35° de rampa** ou de **0,71 g** em curva; o envelope conservador de operação
(fórmula 6.1 da baseline) é **16,8°**. **A margem é menor do que o pacote publicava**: o que mais a consome é o
vão máximo da suspensão, a carga útil acima de Z 382 mm e o mastro cheio; o grupo pneumático de um lado só gasta
metade da folga lateral.

| Estado | Massa kg | X mm | Y mm | Z mm | Tomb. lateral | Envelope | Rampa sobe / desce | a lat. máx (g) |
|---|---|---|---|---|---|---|---|---|
| **entrega** — 9 OAK-D, sem térmica | 143,7 | -8,6 | -0,9 | 316 | 36,7° | 18,0° | 45,4° / 46,9° | 0,75 |
| **cheio** — + 4 térmicas | 146,0 | -8,5 | -0,9 | 327 | 35,7° | 17,1° | 44,3° / 45,8° | 0,72 |
| **projeto** — + antena em um mastro | 146,3 | -8,5 | -0,3 | 330 | 35,4° | 16,8° | 44,0° / 45,5° | 0,71 |
| projeto, antena nos dois mastros | 146,7 | -8,5 | -0,9 | 333 | 35,1° | 16,5° | 43,7° / 45,2° | 0,70 |
| **projeto, vão máximo** (+30 mm) | 146,3 | -8,5 | -0,3 | 356 | 33,1° | 14,8° | 41,6° / 43,1° | 0,65 |

* **Tombamento lateral em rampa: 35,4°** (rígido seria 38,7°; a carroceria rola
  5,4° sobre os foles até o curso acabar). Rampa longitudinal: 44,0° subindo,
  45,5° descendo — o CG está 8 mm atrás do centro, e isso piora a subida.
* **Envelope conservador (fórmula 6.1 da baseline, que inclui obstáculo de 60 mm e fator de segurança 1,3):
  16,8°** no vão mínimo e **14,8°** no vão máximo. A baseline Rev E publica
  16,2°. O repositório não traz um mínimo exigido; comparo com esse valor porque é o único escrito.
* **Aceleração lateral que levanta as rodas: 0,71 g** (7,0 m/s²). A 1,4 m/s, curva de 1 m de
  raio pede 1,96 m/s²: fator de segurança 3,6.
* **O que o mastro cheio custa:** da entrega ao projeto (térmicas e antena) o CG sobe 14 mm e o envelope cai
  1,2°. Até 15/10/2026 `suspensao.py` usava um CG ainda mais baixo (288 mm) — ver abaixo.

## A divergência com `suspensao.py` foi resolvida em 15/10/2026

Até 15/10/2026, `suspensao.py` calculava a rolagem e o envelope a partir da massa e do CG da **Rev F do V3**
(110,07 kg, 294,1 mm), trocando o grupo S pelo W — sem o mastro do V4. Dava 39,92° de tombamento e
20,89° de envelope, otimistas. Agora `suspensao.roll()` usa este inventário (`suspensao.cg_v4()`), e os foles continuam
dimensionados na massa alta de `suspensao.massa()` (151,8 kg), que é o lado seguro para a pressão:

|  | suspensao.py até 15/10/2026 (CG da Rev F ajustada) | suspensao.py agora | Este inventário (V4, estado projeto) |
|---|---|---|---|
| Massa da estabilidade | 151,8 kg | 146,3 kg | 146,3 kg |
| Altura do CG | 288,3 mm | 330,0 mm | 330,0 mm |
| Tombamento lateral | 39,92° | 35,46° (sem a assimetria em Y) | 35,42° |
| Envelope (fórmula 6.1) | 20,89° | 16,82° | 16,82° |

A conclusão da arquitetura não mudou — a suspensão pneumática em bitola 530 continua mais estável que o balancim rígido
em 470 **no mesmo CG** —, mas a margem sobre os 16,2° da baseline ficou em décimos de grau. O documento
`VTX-RV4-SUSPENSAO-H` e o registro de alterações foram corrigidos; **a folha 07 do caderno e o documento técnico do pacote
ainda trazem os números antigos** até a próxima emissão do caderno.

## Como foi calculado

Soma de momentos de um inventário de massa, em ISO 8855 (X à frente, Y à esquerda, Z para cima), origem no centro do
entre-eixos e no solo. Cada linha traz a **origem** do número:

| Origem | Significa |
|---|---|
| CAD | massa e posição saem do modelo (densidade × volume): 64,88 kg de peças fabricadas neste estado, mais 1,4 kg de fixadores estimados |
| DATASHEET | ficha de fabricante (motor-roda MPW86, 4,5 kg; o ZLTECH da compra recomendada **não publica** a massa) |
| BASELINE | tabela 5.1 da Rev E (bateria de 36,5 kg) |
| ZONA | posição = centro da zona que `espaco.py` reserva para o componente |
| FAIXA | massa de faixa de catálogo para a classe do componente (mola, sensor de altura, compressor), não de ficha |
| ESTIMATIVA | massa suposta, sem ficha (OAK-D 0,25 kg, térmica 0,20 kg, antena 0,30 kg) |
| DERIVADO | calculado do resto: o **bloco restante da baseline** |

A tabela 5.1 da baseline **não está no repositório com rótulos**, só a lista de números. Por isso o que a baseline
"mantém" (133,68 kg) entra aberto em três partes: os 4 motores-roda (18,0 kg, posição conhecida), a bateria (36,5 kg, no
centro dos batentes B-01) e um **bloco restante** de 14,48 kg cuja massa é conhecida e cuja posição
**não é**. O Z desse bloco é derivado do CG publicado da baseline (297 mm); X e Y são assumidos no centro.

**Conferência:** o inventário sem os acréscimos do V4 dá **133,68 kg e Z 311,7 mm**, igual ao consolidado do caderno
(133,68 kg, 311,7 mm) — reproduz. A função de tombamento foi conferida contra
`suspensao.roll()`: com as mesmas entradas dá o mesmo resultado (35,46°, rolagem 5,39°, envelope
16,82°).

## Inventário — estado "projeto"

| Item | Origem | Qtd | kg | X | Y | Z |
|---|---|---|---|---|---|---|
| Bateria 16S LiFePO4 · módulo | BASELINE | 2 | 36,50 | +0 | +0 | 320 |
| Motor-roda | DATASHEET | 4 | 18,00 | +0 | +0 | 100 |
| CAD · Q quadro | CAD | 1 | 16,04 | -0 | +0 | 295 |
| Bloco restante da baseline | DERIVADO | 1 | 14,48 | +0 | +0 | 410 |
| CAD · W suspensão (aço e alumínio) | CAD | 1 | 14,40 | +4 | -0 | 208 |
| CAD · C chapa de fundo | CAD | 1 | 11,81 | -5 | +0 | 246 |
| CAD · G gaiola | CAD | 1 | 7,03 | +21 | +0 | 383 |
| CAD · T interface VMS-60 | CAD | 1 | 4,99 | -4 | +4 | 875 |
| CAD · K carenagens e tampas | CAD | 1 | 4,59 | -3 | -0 | 357 |
| CAD · M mastros (tubos, luvas, bainha) | CAD | 1 | 4,48 | +0 | -3 | 818 |
| OAK-D Pro W | ESTIMATIVA | 9 | 2,25 | +48 | -0 | 744 |
| W-17a Compressor 12 V, 100 % ciclo, ~35 L/min | ZONA | 1 | 2,20 | -429 | -28 | 268 |
| W-17b Reservatório 2 L, alumínio (tubo) | FAIXA | 2 | 1,60 | +279 | +0 | 272 |
| Fixadores | ESTIMATIVA | 1 | 1,40 | +0 | +0 | 300 |
| W-15 Mola pneumática | FAIXA | 4 | 1,20 | +0 | +0 | 245 |
| Câmera térmica removível | ESTIMATIVA | 4 | 0,80 | +0 | +0 | 997 |
| W-17c Válvula solenoide 3/2, 12 V | ZONA | 4 | 0,72 | -429 | -28 | 266 |
| W-17e Linhas PU Ø6, conexões e manifold | ZONA | 1 | 0,70 | -429 | -28 | 258 |
| CAD · N interfaces de sensores | CAD | 1 | 0,57 | +196 | +0 | 311 |
| CAD · E bandejas e E-STOP | CAD | 1 | 0,49 | -126 | -0 | 297 |
| CAD · B retenção da bateria | CAD | 1 | 0,48 | +0 | +0 | 262 |
| W-16 Sensor de altura | FAIXA | 4 | 0,36 | +0 | +0 | 205 |
| W-17d Secador / filtro coalescente | ZONA | 1 | 0,35 | -429 | -28 | 268 |
| Antena GNSS no mastro | ESTIMATIVA | 1 | 0,30 | +0 | +276 | 1802 |
| W-17f Controlador de nível + chicote | ZONA | 1 | 0,30 | -429 | -28 | 270 |
| W-18 Bandeja do grupo pneumático | ZONA | 1 | 0,30 | -429 | -28 | 253 |

Em linhas com várias unidades, X, Y e Z são o centroide delas.

**Não está contado** (sem massa no projeto): switch PoE de 12 portas, terminal de satélite, cabos M12 e coaxial, conectores,
lama e poeira acumuladas, o ar do reservatório. Cada 1 kg a 800 mm de altura sobe o CG cerca de 3,2 mm.
A carga útil de 25 kg tem massa conhecida e posição desconhecida: está à parte, abaixo.

## Quanto custa cada 100 g

| Altura Z | Sobe o CG | Muda o tombamento lateral (negativo = tomba antes) |
|---|---|---|
| 300 mm | -0,01 mm | +0,001° |
| 700 mm | +0,27 mm | -0,026° |
| 1200 mm | +0,62 mm | -0,060° |
| 1800 mm | +1,03 mm | -0,101° |

100 g no topo do mastro (Z 1800) sobem o CG tanto quanto **1,8 kg** postos no topo da proteção (Z 400). É por isso que a
antena e as térmicas, que parecem leves, aparecem no resultado.

## Em movimento

| Raio da curva | a centrípeta a 1,4 m/s | Fator de segurança contra tombar | Velocidade com FS 2 |
|---|---|---|---|
| 1 m | 1,96 m/s² (0,20 g) | 3,6 | 1,9 m/s |
| 2 m | 0,98 m/s² (0,10 g) | 7,1 | 2,6 m/s |
| 3 m | 0,65 m/s² (0,07 g) | 10,7 | 3,2 m/s |
| 5 m | 0,39 m/s² (0,04 g) | 17,8 | 4,2 m/s |

O raio é **cenário**, não requisito. Aceleração e frenagem: o rover levanta a frente ao acelerar a **0,97 g** e a
traseira ao frear a **1,02 g**; abaixo disso, o limite é a aderência dos pneus e o torque dos motores, não o
tombamento. O cálculo é estático com a rolagem dos foles: **não inclui** a flexão do mastro, a deformação do pneu nem solo mole,
e mede a bitola no centro da roda (265 mm), não na borda externa do pneu, o que é conservador.

## Carga útil de 25 kg

A baseline fala em carga útil de 25 kg e **não diz onde ela fica**. Três alturas hipotéticas, centrada:

| Carga de 25 kg a Z | Massa kg | CG Z mm | Tomb. lateral | Envelope | Rampa sobe |
|---|---|---|---|---|---|
| 350 mm | 171,3 | 333 | 35,2° | 16,6° | 43,9° |
| 500 mm | 171,3 | 355 | 33,2° | 14,9° | 41,9° |
| 700 mm | 171,3 | 384 | 30,9° | 12,8° | 39,5° |

Para manter o envelope em 16,2°, a carga útil tem de ficar **abaixo de 382 mm** com o vão mínimo; com o
vão máximo, **nenhuma altura serve, nem rente à chapa de fundo**. O deck do quadro está a Z 340 e o topo da proteção a Z 400: **a carga útil tem de ficar na altura do deck ou abaixo**,
ou o envelope cai abaixo do que a baseline publica.

## Assimetria lateral

A fórmula 6.1 da baseline já supõe que o CG pode estar até **15 mm** fora do plano central. O inventário dá **-0,3 mm**:
dentro, mas gastando metade da folga, e quase tudo vem de um único grupo.

| Quem desloca o CG para o lado | Momento kg·mm | Efeito no Y do CG |
|---|---|---|
| Antena GNSS no mastro | +83 | +0,57 mm |
| W-17a Compressor 12 V, 100 % ciclo, ~35 L/min | -63 | -0,43 mm |
| W-17c Válvula solenoide 3/2, 12 V | -21 | -0,14 mm |
| CAD · T interface VMS-60 | +20 | +0,14 mm |
| W-17e Linhas PU Ø6, conexões e manifold | -20 | -0,14 mm |
| CAD · M mastros (tubos, luvas, bainha) | -13 | -0,09 mm |

O grupo pneumático está na zona direita (Y de −250 a −60 em `espaco.py`). **A bateria sozinha não zera isso:** para anular o Y do
CG ela teria de andar +1,1 mm, e a folga entre os batentes B-01 e a caixa estimada é de, no máximo, ±18,5 mm
(centros dos batentes, espessura não descontada). Resta centralizar o compressor e o reservatório, ou espelhar parte do grupo.
**Jetson (esquerda) e driver + BMS (direita) estão em bandejas opostas e as massas deles não constam do projeto** — se uma delas pesar
alguns quilos a mais que a outra, o Y do CG anda ±2 mm por quilo de diferença.

## O que muda se uma suposição estiver errada

| Se isto estiver errado | CG Z | CG Y | Tomb. lateral | Dentro de |Y| ≤ 15? |
|---|---|---|---|---|
| OAK-D com 0,50 kg (era 0,25) | 336 (+6,3) | -0,3 | 34,9° (-0,57) | sim |
| OAK-D com 0,15 kg | 327 (-2,6) | -0,3 | 35,7° (+0,24) | sim |
| térmica com 0,40 kg (era 0,20) | 334 (+3,6) | -0,3 | 35,1° (-0,33) | sim |
| antena com 0,42 kg (limite do mastro) | 331 (+1,2) | -0,0 | 35,3° (-0,09) | sim |
| bloco restante da baseline 40 mm mais alto | 334 (+4,0) | -0,3 | 35,1° (-0,36) | sim |
| bloco restante da baseline 40 mm mais baixo | 326 (-4,0) | -0,3 | 35,8° (+0,37) | sim |
| caixa da bateria 40 mm mais alta (centro +20) | 335 (+5,0) | -0,3 | 35,0° (-0,46) | sim |
| grupo pneumático 50 % mais pesado | 328 (-1,8) | -0,7 | 35,5° (+0,12) | sim |
| bloco restante (14,5 kg) com o centro 100 mm para um lado | 330 (+0,0) | +9,6 | 34,3° (-1,10) | sim |
| LIMITE: bloco restante inteiro na bandeja lateral (Y 237) | 330 (+0,0) | +23,2 | 32,7° (-2,74) | **NÃO** |
| bateria encostada num batente (Y +18,5) | 330 (+0,0) | +4,3 | 35,0° (-0,47) | sim |
| motor-roda de 6,0 kg (massa do ZLTECH não é publicada) | 321 (-9,1) | -0,3 | 36,3° (+0,86) | sim |

A linha **LIMITE** não é previsão: é o pior caso geométrico (todo o bloco restante de 14,5 kg numa bandeja lateral). Mostra que a
premissa de 15 mm **pode ser violada** se as massas da eletrônica não forem balanceadas.

## O que fazer

1. **Pesar.** Rover montado, em quatro balanças (uma por roda), no plano: dá X e Y do CG com a precisão da balança. Z sai por
   inclinação: levantando o eixo dianteiro de um ângulo θ e lendo o acréscimo ΔR na carga do eixo traseiro, h = ΔR · L / (W · tan θ),
   com L o entre-eixos e W o peso. Isto é **ensaio proposto**; ele ainda não tem número no plano de validação (folha 26).
2. **Centralizar o grupo pneumático** (ou espelhar compressor e reservatório): tira 0,4 mm do desvio; o Y do CG iria de
   -0,3 para cerca de +0,2 mm.
3. **Fixar a posição da carga útil**, na altura do deck ou abaixo: no máximo 382 mm com o vão mínimo.
4. **Decidir se o envelope de 16,2° é requisito.** Com o mastro cheio e a suspensão no vão máximo ele não se mantém (14,8°). Se for, a
   saída é limitar o vão máximo, reduzir massa no alto (térmicas e antena) ou alargar a bitola.
5. **Reancorar `suspensao.py`** no inventário do V4 (decisão do engenheiro; ver a divergência acima) e refazer o envelope da suspensão.
6. Qualquer sensor novo no mastro entra por `efeito_por_100g` antes de ser aprovado.

**Este documento é cálculo sobre massas estimadas e um bloco da baseline sem posição. Não é pesagem e não valida o
rover contra tombamento.** O CG do rover real só se conhece com ele montado e pesado.
