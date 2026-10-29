# Rover V4 — espaço interno e interferência entre peças

> **VTX-RV4 · Revisão H · 12/10/2026**
> EMITIDO PARA COTAÇÃO E VALIDAÇÃO — NÃO LIBERADO PARA FABRICAÇÃO
>
> Documento **gerado** de `revisao-h/espaco.py` sobre a geometria de
> `chassi-gaiola/modelo.py`. Não editar à mão: a próxima geração sobrescreve.


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


## Interferência entre peças

276 peças fornecidas, 37950 pares verificados.

**Encaixes previstos: 17**

| par | profundidade | razão |
|---|---|---|
| C-01 × W-12 | 2,0 mm | colar do fole atravessa a passagem Ø102 da chapa de fundo |
| M-01 × M-10 | 32,0 mm | haste do mastro dentro da luva |
| M-10 × M-11 | 32,0 mm | bainha anti-galho sobre a haste |
| M-10 × T-10 | 26,0 mm | adaptador da antena encaixado 40 mm no furo do topo da haste |
| M-11 × T-10 | 26,0 mm | adaptador da antena dentro do furo da haste, sob o último trecho da bainha |
| N-06 × N-07 | 3,0 mm | aba soldada na face inclinada da câmera de raiz |
| Q-02 × Q-05 | 12,0 mm | bucha de compressão dentro do tubo da travessa |
| Q-03 × Q-05 | 12,0 mm | bucha de compressão dentro do tubo da travessa |
| W-01 × W-04 | 30,0 mm | alojamento da bucha atravessa o tubo do braço |
| W-01 × W-07 | 20,0 mm | eixo do pivô atravessa o braço, dentro das buchas de W-04 |
| W-01 × W-08 | 8,0 mm | prato do fole alojado no rasgo da parede superior do braço |
| W-01 × W-09 | 8,0 mm | orelhas do prato alojadas DENTRO do tubo do braço, que é vazado |
| W-01 × W-10 | 12,0 mm | pino do prato atravessa as paredes do braço |
| W-02 × W-08 | 8,0 mm | prato e chapa do motor se cruzam na caixa, não no sólido |
| W-04 × W-07 | 20,0 mm | eixo do pivô dentro do alojamento da bucha |
| W-05 × W-07 | 6,0 mm | eixo do pivô atravessa as duas orelhas da torre |
| W-09 × W-10 | 8,0 mm | pino dentro das orelhas do prato |

**Defeitos: nenhum**



## Volume interno

| Grandeza | Valor |
|---|---|
| Caixa bruta do compartimento (1046 × 596 × 150) | 93,51 L |
| **Volume livre, descontada toda peça** | **76,68 L** |
| Maior altura livre contínua em qualquer ponto | 148 mm |

### Volume aproveitável por altura de componente

| Componente de até | Volume aproveitável |
|---|---|
| 30 mm | 76,68 L |
| 60 mm | 68,28 L |
| 90 mm | 65,83 L |
| 120 mm | 57,14 L |

### Área de piso por faixa de altura livre

| Faixa de altura livre | Área de piso |
|---|---|
| 0 a 20 mm | 34 cm² |
| 20 a 40 mm | 709 cm² |
| 40 a 60 mm | 483 cm² |
| 60 a 80 mm | 12 cm² |
| 80 a 100 mm | 239 cm² |
| 100 a 120 mm | 758 cm² |
| 120 a 140 mm | 455 cm² |
| 140 a 160 mm | 3467 cm² |


## Teto de altura por zona — para a folha de compra

É o jeito útil de entregar esta conferência: em vez de reprovar um componente estimado, dizer qual é o teto real da zona, para que a cota entre na folha de compra junto com a ficha técnica que falta.

| Zona | Altura máxima de componente | Área | Onde |
|---|---|---|---|
| Bateria · módulo +X | **147 mm** | 631 cm² | Rev K: entre o G-02 e a G-03, batentes B-01 nas faces X |
| Bateria · módulo −X | **147 mm** | 631 cm² | Idem, espelhado |
| Bandeja lateral esquerda | **88 mm** | 205 cm² | Rev K: livre (fusíveis, borneiras, cabos) |
| Bandeja lateral direita | **88 mm** | 205 cm² | Idem, espelhada |
| Faixa traseira (computação) | **127 mm** | 375 cm² | Rev K: Jetson e driver de pé, ao longo de Y |
| Baia dianteira | **89 mm** | 301 cm² | Rev K: BMS, sobre a E-02 dianteira direita |
| Faixa dianteira esquerda | **87 mm** | 167 cm² | Rev K: tubo do reservatório (1 de 2) |
| Faixa dianteira direita | **107 mm** | 167 cm² | Rev K: tubo do reservatório (2 de 2) |
| Bandeja dianteira esquerda | **145 mm** | 63 cm² | Entre a janela de raiz e o colar do fole |
| Bandeja traseira esquerda | **145 mm** | 63 cm² | Idem, traseira |
| Compressor (baia traseira) | **144 mm** | 301 cm² | Rev K: atrás, sobre a E-02 traseira direita |


## Cada componente cabe em algum lugar contíguo?

Varredura da grade inteira, nas duas orientações. É a pergunta certa — diferente de "a altura média da zona dá".

| Componente | L×W×H | origem do dado | veredito | posição |
|---|---|---|---|---|
| Módulo de bateria 8 células (+X) | 154×410×140 | ESTIMATIVA | **CABE** | X -211…-57 · Y -266…144 (livre 145 mm) |
| Módulo de bateria 8 células (−X) | 154×410×140 | ESTIMATIVA | **CABE** | X -211…-57 · Y -266…144 (livre 145 mm) |
| Jetson Orin NX + carrier (de pé) | 180×45×110 | ESTIMATIVA | **CABE** | X -91…89 · Y -258…-213 (livre 125 mm) |
| Driver dos motores (4 canais, de pé) | 200×55×120 | ESTIMATIVA | **CABE** | X -99…101 · Y -258…-203 (livre 125 mm) |
| BMS | 140×90×35 | ESTIMATIVA | **CABE** | X -43…47 · Y -266…-126 (livre 88 mm) |
| Conversor DC/DC 12 V | 110×50×40 | ESTIMATIVA | **CABE** | X -27…23 · Y -266…-156 (livre 88 mm) |
| Roteador / modem | 110×50×35 | ESTIMATIVA | **CABE** | X -27…23 · Y -266…-156 (livre 88 mm) |
| Compressor 12 V | 210×110×120 | FAIXA | **CABE** | X -107…103 · Y -258…-148 (livre 125 mm) |
| Reservatório: tubo Ø75 × 220 (≈1 L) | 220×75×75 | REQUISITO | **CABE** | X -35…40 · Y -266…-46 (livre 87 mm) |
| Reservatório: tubo Ø75 × 220 (≈1 L) | 220×75×75 | REQUISITO | **CABE** | X -35…40 · Y -266…-46 (livre 87 mm) |

Cuidado ao ler a tabela acima: ela olha **um componente por vez** e aceita qualquer lugar livre do compartimento. Vários componentes recebem a mesma posição, e a posição pode ficar fora da zona reservada para eles. A conferência que importa para o leiaute é a seguinte.



## Cada componente cabe na zona reservada para ele, junto com os vizinhos?

Planta do componente contra a planta da zona (nas duas orientações), altura contra o teto da zona e, por zona, a área somada contra a área disponível. Acrescentada em 15/10/2026.

| Zona | Componente | L×W×H | origem | veredito | motivo |
|---|---|---|---|---|---|
| Bateria · módulo +X | Módulo de bateria 8 células (+X) | 154×410×140 | ESTIMATIVA | **CABE** | — |
| Bateria · módulo +X | *soma da zona* | 631 cm² |  | **CABE** | área da zona 631 cm² |
| Bateria · módulo −X | Módulo de bateria 8 células (−X) | 154×410×140 | ESTIMATIVA | **CABE** | — |
| Bateria · módulo −X | *soma da zona* | 631 cm² |  | **CABE** | área da zona 631 cm² |
| Faixa traseira (computação) | Jetson Orin NX + carrier (de pé) | 180×45×110 | ESTIMATIVA | **CABE** | — |
| Faixa traseira (computação) | Driver dos motores (4 canais, de pé) | 200×55×120 | ESTIMATIVA | **CABE** | — |
| Faixa traseira (computação) | *soma da zona* | 191 cm² |  | **CABE** | área da zona 375 cm² |
| Baia dianteira | BMS | 140×90×35 | ESTIMATIVA | **CABE** | — |
| Baia dianteira | *soma da zona* | 126 cm² |  | **CABE** | área da zona 301 cm² |
| Faixa dianteira esquerda | Reservatório: tubo Ø75 × 220 (≈1 L) | 220×75×75 | REQUISITO | **CABE** | — |
| Faixa dianteira esquerda | *soma da zona* | 165 cm² |  | **CABE** | área da zona 167 cm² |
| Faixa dianteira direita | Reservatório: tubo Ø75 × 220 (≈1 L) | 220×75×75 | REQUISITO | **CABE** | — |
| Faixa dianteira direita | *soma da zona* | 165 cm² |  | **CABE** | área da zona 167 cm² |
| Bandeja dianteira esquerda | Conversor DC/DC 12 V | 110×50×40 | ESTIMATIVA | **CABE** | — |
| Bandeja dianteira esquerda | *soma da zona* | 55 cm² |  | **CABE** | área da zona 63 cm² |
| Bandeja traseira esquerda | Roteador / modem | 110×50×35 | ESTIMATIVA | **CABE** | — |
| Bandeja traseira esquerda | *soma da zona* | 55 cm² |  | **CABE** | área da zona 63 cm² |
| Compressor (baia traseira) | Compressor 12 V | 210×110×120 | FAIXA | **CABE** | — |
| Compressor (baia traseira) | *soma da zona* | 231 cm² |  | **CABE** | área da zona 301 cm² |

**0 de 9 zonas não comportam o que o projeto põe nelas.** Com as dimensões estimadas, o leiaute interno das bandejas e do grupo pneumático precisa ser refeito quando chegarem as fichas técnicas (P-05, P-13).



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
