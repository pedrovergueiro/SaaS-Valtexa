# Rover V4 — centro de massa e margem contra tombamento

> **VTX-RV4 · Revisão H · 12/10/2026**
> EMITIDO PARA COTAÇÃO E VALIDAÇÃO — NÃO LIBERADO PARA FABRICAÇÃO
>
> Documento **gerado** de `revisao-h/centro_massa.py` sobre a geometria de
> `chassi-gaiola/modelo.py`. Não editar à mão: a próxima geração sobrescreve.


## Resposta

Com o mastro cheio e a antena em um mastro, o centro de massa fica a **335 mm do solo**, **10 mm
atrás** e **7 mm à direita** do centro do entre-eixos, para **122 kg**. Pelo cálculo estático, o
rover só tomba de lado acima de **34° de rampa** ou de **0,68 g** em curva; o envelope conservador de operação
(fórmula 6.1 da baseline) é **16,4°**. **A margem é menor do que o pacote publicava**: o que mais a consome é o
vão máximo da suspensão, a carga útil acima de Z 348 mm e o mastro cheio; o grupo pneumático de um lado só gasta
metade da folga lateral.

| Estado | Massa kg | X mm | Y mm | Z mm | Tomb. lateral | Envelope | Rampa sobe / desce | a lat. máx (g) |
|---|---|---|---|---|---|---|---|---|
| **entrega** — 9 OAK-D, sem térmica | 119,6 | -10,1 | -8,0 | 318 | 35,6° | 17,8° | 45,0° / 46,7° | 0,72 |
| **cheio** — + 4 térmicas | 121,9 | -9,9 | -7,8 | 332 | 34,4° | 16,7° | 43,7° / 45,5° | 0,68 |
| **projeto** — + antena em um mastro | 122,2 | -9,8 | -7,1 | 335 | 34,1° | 16,4° | 43,4° / 45,1° | 0,68 |
| projeto, antena nos dois mastros | 122,6 | -9,8 | -7,8 | 339 | 33,7° | 16,1° | 43,0° / 44,8° | 0,67 |
| **projeto, vão máximo** (+30 mm) | 122,2 | -9,8 | -7,1 | 361 | 31,9° | 14,4° | 41,1° / 42,9° | 0,62 |

* **Tombamento lateral em rampa: 34,1°** (rígido seria 37,6°; a carroceria rola
  5,4° sobre os foles até o curso acabar). Rampa longitudinal: 43,4° subindo,
  45,1° descendo — o CG está 10 mm atrás do centro, e isso piora a subida.
* **Envelope conservador (fórmula 6.1 da baseline, que inclui obstáculo de 60 mm e fator de segurança 1,3):
  16,4°** no vão mínimo e **14,4°** no vão máximo. A baseline Rev E publica
  16,2°. O repositório não traz um mínimo exigido; comparo com esse valor porque é o único escrito.
* **Aceleração lateral que levanta as rodas: 0,68 g** (6,6 m/s²). A 1,4 m/s, curva de 1 m de
  raio pede 1,96 m/s²: fator de segurança 3,4.
* **O que o mastro cheio custa:** da entrega ao projeto (térmicas e antena) o CG sobe 17 mm e o envelope cai
  1,4°. Até 15/10/2026 `suspensao.py` usava um CG ainda mais baixo (286 mm) — ver abaixo.

## A divergência com `suspensao.py` foi resolvida em 15/10/2026

Até 15/10/2026, `suspensao.py` calculava a rolagem e o envelope a partir da massa e do CG da **Rev F do V3**
(110,07 kg, 294,1 mm), trocando o grupo S pelo W — sem o mastro do V4. Dava 39,92° de tombamento e
20,89° de envelope, otimistas. Agora `suspensao.roll()` usa este inventário (`suspensao.cg_v4()`), e os foles continuam
dimensionados na massa alta de `suspensao.massa()` (127,7 kg), que é o lado seguro para a pressão:

|  | suspensao.py até 15/10/2026 (CG da Rev F ajustada) | suspensao.py agora | Este inventário (V4, estado projeto) |
|---|---|---|---|
| Massa da estabilidade | 127,7 kg | 122,2 kg | 122,2 kg |
| Altura do CG | 285,7 mm | 335,5 mm | 335,5 mm |
| Tombamento lateral | 39,92° | 34,96° (sem a assimetria em Y) | 34,13° |
| Envelope (fórmula 6.1) | 20,89° | 16,37° | 16,37° |

A conclusão da arquitetura não mudou — a suspensão pneumática em bitola 530 continua mais estável que o balancim rígido
em 470 **no mesmo CG** —, mas a margem sobre os 16,2° da baseline ficou em décimos de grau. O documento
`VTX-RV4-SUSPENSAO-H` e o registro de alterações foram corrigidos; **a folha 07 do caderno e o documento técnico do pacote
ainda trazem os números antigos** até a próxima emissão do caderno.

## Como foi calculado

Soma de momentos de um inventário de massa, em ISO 8855 (X à frente, Y à esquerda, Z para cima), origem no centro do
entre-eixos e no solo. Cada linha traz a **origem** do número:

| Origem | Significa |
|---|---|
| CAD | massa e posição saem do modelo (densidade × volume): 40,78 kg de peças fabricadas neste estado, mais 1,4 kg de fixadores estimados |
| DATASHEET | ficha de fabricante (motor-roda MPW86, 4,5 kg; o ZLTECH da compra recomendada **não publica** a massa) |
| BASELINE | tabela 5.1 da Rev E (bateria de 36,5 kg) |
| ZONA | posição = centro da zona que `espaco.py` reserva para o componente |
| FAIXA | massa de faixa de catálogo para a classe do componente (mola, sensor de altura, compressor), não de ficha |
| ESTIMATIVA | massa suposta, sem ficha (OAK-D 0,25 kg, térmica 0,20 kg, antena 0,30 kg) |
| DERIVADO | calculado do resto: o **bloco restante da baseline** |

A tabela 5.1 da baseline **não está no repositório com rótulos**, só a lista de números. Por isso o que a baseline
"mantém" (109,58 kg) entra aberto em três partes: os 4 motores-roda (18,0 kg, posição conhecida), a bateria (36,5 kg, no
centro dos batentes B-01) e um **bloco restante** de 14,48 kg cuja massa é conhecida e cuja posição
**não é**. O Z desse bloco é derivado do CG publicado da baseline (297 mm); X e Y são assumidos no centro.

**Conferência:** o inventário sem os acréscimos do V4 dá **109,58 kg e Z 313,7 mm**, igual ao consolidado do caderno
(109,58 kg, 313,7 mm) — reproduz. A função de tombamento foi conferida contra
`suspensao.roll()`: com as mesmas entradas dá o mesmo resultado (34,96°, rolagem 5,39°, envelope
16,37°).

## Inventário — estado "projeto"

| Item | Origem | Qtd | kg | X | Y | Z |
|---|---|---|---|---|---|---|
| Bateria 16S LiFePO4 | BASELINE | 1 | 36,50 | +0 | +0 | 315 |
| Motor-roda | DATASHEET | 4 | 18,00 | +0 | +0 | 100 |
| Bloco restante da baseline | DERIVADO | 1 | 14,48 | +0 | +0 | 422 |
| CAD · W suspensão (aço e alumínio) | CAD | 1 | 14,40 | +4 | -0 | 208 |
| CAD · Q quadro | CAD | 1 | 5,52 | -0 | +0 | 295 |
| CAD · T interface VMS-60 | CAD | 1 | 4,99 | -4 | +4 | 875 |
| CAD · K carenagens e tampas | CAD | 1 | 4,59 | -3 | -0 | 357 |
| CAD · C chapa de fundo | CAD | 1 | 4,04 | -5 | +0 | 246 |
| CAD · M mastros (tubos, luvas, bainha) | CAD | 1 | 3,26 | +0 | -4 | 964 |
| CAD · G gaiola | CAD | 1 | 2,42 | +22 | +0 | 383 |
| OAK-D Pro W | ESTIMATIVA | 9 | 2,25 | +48 | -0 | 744 |
| W-17a Compressor 12 V, 100 % ciclo, ~35 L/min | ZONA | 1 | 2,20 | -230 | -155 | 268 |
| W-17b Reservatório 2 L, alumínio | ZONA | 1 | 1,60 | -230 | -155 | 272 |
| Fixadores | ESTIMATIVA | 1 | 1,40 | +0 | +0 | 300 |
| W-15 Mola pneumática | FAIXA | 4 | 1,20 | +0 | +0 | 245 |
| Câmera térmica removível | ESTIMATIVA | 4 | 0,80 | +0 | +0 | 997 |
| W-17c Válvula solenoide 3/2, 12 V | ZONA | 4 | 0,72 | -230 | -155 | 266 |
| W-17e Linhas PU Ø6, conexões e manifold | ZONA | 1 | 0,70 | -230 | -155 | 258 |
| CAD · N interfaces de sensores | CAD | 1 | 0,57 | +196 | +0 | 311 |
| CAD · B retenção da bateria | CAD | 1 | 0,49 | +0 | +0 | 261 |
| CAD · E bandejas e E-STOP | CAD | 1 | 0,49 | -126 | -0 | 297 |
| W-16 Sensor de altura | FAIXA | 4 | 0,36 | +0 | +0 | 205 |
| W-17d Secador / filtro coalescente | ZONA | 1 | 0,35 | -230 | -155 | 268 |
| Antena GNSS no mastro | ESTIMATIVA | 1 | 0,30 | +0 | +276 | 1802 |
| W-17f Controlador de nível + chicote | ZONA | 1 | 0,30 | -230 | -155 | 270 |
| W-18 Bandeja do grupo pneumático | ZONA | 1 | 0,30 | -230 | -155 | 253 |

Em linhas com várias unidades, X, Y e Z são o centroide delas.

**Não está contado** (sem massa no projeto): switch PoE de 12 portas, terminal de satélite, cabos M12 e coaxial, conectores,
lama e poeira acumuladas, o ar do reservatório. Cada 1 kg a 800 mm de altura sobe o CG cerca de 3,8 mm.
A carga útil de 25 kg tem massa conhecida e posição desconhecida: está à parte, abaixo.

## Quanto custa cada 100 g

| Altura Z | Sobe o CG | Muda o tombamento lateral (negativo = tomba antes) |
|---|---|---|
| 300 mm | -0,02 mm | +0,002° |
| 700 mm | +0,32 mm | -0,030° |
| 1200 mm | +0,74 mm | -0,070° |
| 1800 mm | +1,24 mm | -0,118° |

100 g no topo do mastro (Z 1800) sobem o CG tanto quanto **1,8 kg** postos no topo da proteção (Z 400). É por isso que a
antena e as térmicas, que parecem leves, aparecem no resultado.

## Em movimento

| Raio da curva | a centrípeta a 1,4 m/s | Fator de segurança contra tombar | Velocidade com FS 2 |
|---|---|---|---|
| 1 m | 1,96 m/s² (0,20 g) | 3,4 | 1,8 m/s |
| 2 m | 0,98 m/s² (0,10 g) | 6,8 | 2,6 m/s |
| 3 m | 0,65 m/s² (0,07 g) | 10,2 | 3,2 m/s |
| 5 m | 0,39 m/s² (0,04 g) | 17,0 | 4,1 m/s |

O raio é **cenário**, não requisito. Aceleração e frenagem: o rover levanta a frente ao acelerar a **0,95 g** e a
traseira ao frear a **1,00 g**; abaixo disso, o limite é a aderência dos pneus e o torque dos motores, não o
tombamento. O cálculo é estático com a rolagem dos foles: **não inclui** a flexão do mastro, a deformação do pneu nem solo mole,
e mede a bitola no centro da roda (265 mm), não na borda externa do pneu, o que é conservador.

## Carga útil de 25 kg

A baseline fala em carga útil de 25 kg e **não diz onde ela fica**. Três alturas hipotéticas, centrada:

| Carga de 25 kg a Z | Massa kg | CG Z mm | Tomb. lateral | Envelope | Rampa sobe |
|---|---|---|---|---|---|
| 350 mm | 147,2 | 338 | 34,1° | 16,2° | 43,3° |
| 500 mm | 147,2 | 363 | 31,9° | 14,2° | 41,1° |
| 700 mm | 147,2 | 397 | 29,3° | 12,0° | 38,3° |

Para manter o envelope em 16,2°, a carga útil tem de ficar **abaixo de 348 mm** com o vão mínimo; com o
vão máximo, **nenhuma altura serve, nem rente à chapa de fundo**. O deck do quadro está a Z 340 e o topo da proteção a Z 400: **a carga útil tem de ficar na altura do deck ou abaixo**,
ou o envelope cai abaixo do que a baseline publica.

## Assimetria lateral

A fórmula 6.1 da baseline já supõe que o CG pode estar até **15 mm** fora do plano central. O inventário dá **-7,1 mm**:
dentro, mas gastando metade da folga, e quase tudo vem de um único grupo.

| Quem desloca o CG para o lado | Momento kg·mm | Efeito no Y do CG |
|---|---|---|
| W-17a Compressor 12 V, 100 % ciclo, ~35 L/min | -341 | -2,79 mm |
| W-17b Reservatório 2 L, alumínio | -248 | -2,03 mm |
| W-17c Válvula solenoide 3/2, 12 V | -112 | -0,91 mm |
| W-17e Linhas PU Ø6, conexões e manifold | -108 | -0,89 mm |
| Antena GNSS no mastro | +83 | +0,68 mm |
| W-17d Secador / filtro coalescente | -54 | -0,44 mm |

O grupo pneumático está na zona direita (Y de −250 a −60 em `espaco.py`). **A bateria sozinha não zera isso:** para anular o Y do
CG ela teria de andar +23,7 mm, e a folga entre os batentes B-01 e a caixa estimada é de, no máximo, ±18,5 mm
(centros dos batentes, espessura não descontada). Resta centralizar o compressor e o reservatório, ou espelhar parte do grupo.
**Jetson (esquerda) e driver + BMS (direita) estão em bandejas opostas e as massas deles não constam do projeto** — se uma delas pesar
alguns quilos a mais que a outra, o Y do CG anda ±2 mm por quilo de diferença.

## O que muda se uma suposição estiver errada

| Se isto estiver errado | CG Z | CG Y | Tomb. lateral | Dentro de |Y| ≤ 15? |
|---|---|---|---|---|
| OAK-D com 0,50 kg (era 0,25) | 343 (+7,4) | -7,0 | 33,5° (-0,64) | sim |
| OAK-D com 0,15 kg | 332 (-3,0) | -7,1 | 34,4° (+0,27) | sim |
| térmica com 0,40 kg (era 0,20) | 340 (+4,3) | -7,0 | 33,8° (-0,38) | sim |
| antena com 0,42 kg (limite do mastro) | 337 (+1,4) | -6,8 | 34,0° (-0,10) | sim |
| bloco restante da baseline 40 mm mais alto | 340 (+4,7) | -7,1 | 33,7° (-0,42) | sim |
| bloco restante da baseline 40 mm mais baixo | 331 (-4,7) | -7,1 | 34,6° (+0,43) | sim |
| caixa da bateria 40 mm mais alta (centro +20) | 341 (+6,0) | -7,1 | 33,6° (-0,53) | sim |
| grupo pneumático 50 % mais pesado | 333 (-2,3) | -10,7 | 33,9° (-0,22) | sim |
| bloco restante (14,5 kg) com o centro 100 mm para um lado | 335 (+0,0) | +4,8 | 34,4° (+0,27) | sim |
| LIMITE: bloco restante inteiro na bandeja lateral (Y 237) | 335 (+0,0) | +21,0 | 32,5° (-1,67) | **NÃO** |
| bateria encostada num batente (Y +18,5) | 335 (+0,0) | -1,6 | 34,8° (+0,64) | sim |
| motor-roda de 6,0 kg (massa do ZLTECH não é publicada) | 324 (-11,0) | -6,8 | 35,2° (+1,06) | sim |

A linha **LIMITE** não é previsão: é o pior caso geométrico (todo o bloco restante de 14,5 kg numa bandeja lateral). Mostra que a
premissa de 15 mm **pode ser violada** se as massas da eletrônica não forem balanceadas.

## O que fazer

1. **Pesar.** Rover montado, em quatro balanças (uma por roda), no plano: dá X e Y do CG com a precisão da balança. Z sai por
   inclinação: levantando o eixo dianteiro de um ângulo θ e lendo o acréscimo ΔR na carga do eixo traseiro, h = ΔR · L / (W · tan θ),
   com L o entre-eixos e W o peso. Isto é **ensaio proposto**; ele ainda não tem número no plano de validação (folha 26).
2. **Centralizar o grupo pneumático** (ou espelhar compressor e reservatório): tira 4,8 mm do desvio; o Y do CG iria de
   -7,1 para cerca de -2,3 mm.
3. **Fixar a posição da carga útil**, na altura do deck ou abaixo: no máximo 348 mm com o vão mínimo.
4. **Decidir se o envelope de 16,2° é requisito.** Com o mastro cheio e a suspensão no vão máximo ele não se mantém (14,4°). Se for, a
   saída é limitar o vão máximo, reduzir massa no alto (térmicas e antena) ou alargar a bitola.
5. **Reancorar `suspensao.py`** no inventário do V4 (decisão do engenheiro; ver a divergência acima) e refazer o envelope da suspensão.
6. Qualquer sensor novo no mastro entra por `efeito_por_100g` antes de ser aprovado.

**Este documento é cálculo sobre massas estimadas e um bloco da baseline sem posição. Não é pesagem e não valida o
rover contra tombamento.** O CG do rover real só se conhece com ele montado e pesado.
