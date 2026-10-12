# Rover V4 — rigidez do mastro e vibração dos sensores

> **VTX-RV4 · Revisão H · 12/10/2026**
> EMITIDO PARA COTAÇÃO E VALIDAÇÃO — NÃO LIBERADO PARA FABRICAÇÃO
>
> Documento **gerado** de `revisao-h/mastro.py` sobre a geometria de
> `chassi-gaiola/modelo.py`. Não editar à mão: a próxima geração sobrescreve.


## Resumo

O mastro adotado é **Ø32 × 3**, em alumínio 6061-T6, e a razão está
na tabela abaixo: o projeto descreve um mastro com **mais carga** do que o V4 inicial supôs.

| Estado do mastro | Ø25×2 (V3) | Ø32×2 (V4 inicial) | **Ø32×3 (adotado)** |
|---|---|---|---|
| Entrega: 3 OAK-D por mastro | 6,31 Hz | 9,11 Hz | **10,08 Hz** |
| Cheio: + 2 térmicas removíveis por mastro | 5,74 Hz | 8,33 Hz | **9,29 Hz** |
| **Projeto: + antena GNSS no topo (0,30 kg, ESTIMATIVA)** | **4,77 Hz** | **6,97 Hz** | **7,88 Hz** |
| Contra o requisito de 7,5 Hz (caso de projeto) | **não atende** | **não atende** | atende |

O requisito de 7,5 Hz é o caso 6 do FEA — *"1ª frequência do mastro ≥ 7,5 Hz"* —,
aberto desde a Rev E e nunca verificado até o V4.

> **Correção a uma versão anterior deste documento.** Ela dava o Ø32×2 como aprovado. Estava
> errada em dois pontos. (1) O Ø32×2 foi calculado para três câmeras por mastro, e o projeto
> descreve cinco postos mais a antena: nessa carga ele dá 6,97 Hz, abaixo do requisito.
> (2) O próprio cálculo já reportava que a margem contra o terreno não fechava — e o texto
> não dizia. Está dito na seção seguinte.

## O que o mastro carrega

| Posto | Z nominal | Estado | Massa estimada do sensor |
|---|---|---|---|
| 3 × OAK-D por mastro | 450, 1000, 1540 | fixas, calibradas | 0,25 kg (ESTIMATIVA) |
| 2 × térmica por mastro | 725, 1270 | **removíveis** | 0,20 kg (ESTIMATIVA) |
| Antena GNSS no topo | 1802 (base) | provisão T-10 | 0,30 kg (ESTIMATIVA) + T-10 0,073 kg |

Cada posto soma 0,389 kg de estrutura VMS (braçadeira, prato, adaptador e protetor),
medidos na geometria do modelo. As massas dos **sensores** não vêm de ficha técnica — nenhum
modelo de térmica ou de antena foi escolhido, e a da OAK-D é pendência P-06.

## Por que a parede engrossa e o diâmetro não

O diâmetro externo fica em 32 porque o tubo entra na luva Ø42×5
(furo 32), e a luva não pode crescer: já alcança |Y| 297 e o envelope
externo é 600. Uma seção maior exigiria luva maior, e luva maior exigiria mexer na base do
mastro e na carenagem K-01.

| Seção | 1ª freq. (projeto) | Razão contra o terreno | Δ massa (2 mastros) | Cabe na luva? |
|---|---|---|---|---|
| Ø25 × 2 — V3, herdado da baseline | 4,77 Hz (abaixo) | 0,85 | -0,874 kg | sim |
| Ø32 × 2 — V4 inicial, dimensionado para 3 câmeras | 6,97 Hz (abaixo) | 1,24 | -0,575 kg | sim |
| Ø32 × 3 ← **adotada** | 7,88 Hz (atende) | 1,41 | +0,000 kg | sim |
| Ø32 × 4 | 8,43 Hz (atende) | 1,51 | +0,533 kg | sim |
| Ø35 × 2 | 7,98 Hz (atende) | 1,42 | -0,447 kg | não |
| Ø38 × 3 | 10,22 Hz (atende) | 1,83 | +0,384 kg | não |
| Ø40 × 3 | 11,03 Hz (atende) | 1,97 | +0,511 kg | não |

Δ massa é medida contra o Ø32×3 adotado. **Contra o V3 (Ø25×2) o mastro novo pesa
+0,87 kg nos dois.**

## A margem contra o terreno NÃO fecha — e isso precisa ficar dito

Dois critérios, e o mastro adotado cumpre só um.

| | Valor | Critério | |
|---|---|---|---|
| 1ª frequência (projeto) | 7,88 Hz | ≥ 7,5 Hz | atende |
| Razão contra a excitação do terreno | 1,41 | ≥ 2,0 | **não atende** |

A excitação estimada do terreno é 5,60 Hz (1,4 m/s sobre ondas de
0,25 m — **critério de projeto, não medição**). Com razão 1,41 o mastro
cheio **amplifica** essa excitação em 2,02× (sem amortecimento, que é o lado
seguro). A margem de 2,0 só fecha com marcha abaixo de
**0,98 m/s**.

Rigidez sozinha não resolve: mesmo o Ø40×3, que nem cabe na luva, chega a razão
1,97 — ainda abaixo de 2,0. O que decide é o **espectro real**,
ensaio V-12. Enquanto ele não rodar, as opções honestas são: (a) medir; (b) limitar a
marcha com o mastro cheio a ~1,0 m/s; (c) aceitar a amplificação.
Não é decisão de desenho — é decisão sua, com o dado na mão. Pendência P-39.

A suspensão pneumática (frequência de canto 1,95 Hz) atenua o terreno acima de
√2 vezes isso, ou 2,8 Hz — a 5,6 Hz ela já filtra. A razão acima é
contra o **chão**; o que chega ao mastro é menos. Quanto menos, é o que o V-12 mede.

## A antena: quanto o mastro aguenta

Nenhuma antena foi escolhida. O que se pode dizer, e que vira exigência de compra:

| Massa da antena | 1ª freq. | Razão | |
|---|---|---|---|
| 0,00 kg | 9,11 Hz | 1,63 | atende |
| 0,10 kg | 8,64 Hz | 1,54 | atende |
| 0,20 kg | 8,23 Hz | 1,47 | atende |
| 0,30 kg | 7,88 Hz | 1,41 | atende |
| 0,40 kg | 7,57 Hz | 1,35 | atende |
| 0,50 kg | 7,29 Hz | 1,30 | **abaixo do requisito** |
| 0,60 kg | 7,04 Hz | 1,26 | **abaixo do requisito** |

**Massa máxima da antena para manter 7,5 Hz: 0,42 kg** (sem o adaptador T-10, que
já está contado). Antena mais pesada: Ø32×4, que dá 8,43 Hz,
ao custo do furo para os cabos (ver abaixo) — ou antena na tampa (N-01).

**Onde ela fica é decisão aberta (P-36).** Topo do mastro: céu livre, mas a antena sobe a
1832 mm contra 433 mm na tampa, e uma inclinação de 10° do rover desloca a
antena 323 mm contra 76 mm — a compensação por IMU deixa de ser
opcional. Sob galho de 80 N o topo flete 26 mm. Ensaio V-17 decide com dado.

## Conferência do método

| | Valor |
|---|---|
| Rayleigh, um termo | 8,29 Hz |
| Rayleigh-Ritz, 5 modos de viga | 8,24 Hz |
| Diferença | 0,6 % |
| **Valor adotado** = Rayleigh × 0,95 | **7,88 Hz** |

O fator 0,95 **não** corrige erro do método — o Ritz mostra que ele é menor que 1 %. Ele
cobre o que o modelo não tem: o engaste real (haste em luva, travada por 2 parafusos) não é
rígido. É **hipótese**, e quem a substitui é o ensaio V-12 com o mastro montado.

## Cabos dentro do tubo — o preço da parede grossa

| Seção | Furo | Ocupação por 5 cabos M12 + 1 coaxial |
|---|---|---|
| Ø32×2 | Ø28 | 34 % |
| **Ø32×3 (adotado)** | **Ø26** | **40 %** (limite 40 %) |

Com cabos de Ø7 mm — **ESTIMATIVA**; nenhum cabo foi escolhido. O Ø32×3 está no limite:
cabo mais grosso estoura. É a pendência P-40, e a saída é cabo mais fino ou canaleta externa.

## Deflexão e tensão

Sob galho de 80 N na ponta, seção adotada:

| Z | Flecha | Rotação | Erro a 10 m |
|---|---|---|---|
| 725 | 0,9 mm | 0,53° | 92 mm |
| 1000 | 4,9 mm | 1,11° | 193 mm |
| 1270 | 11,2 mm | 1,51° | 263 mm |
| 1540 | 18,9 mm | 1,74° | 304 mm |
| 1782 | 26,4 mm | 1,81° | 315 mm |

Tensão na raiz 55,4 MPa, fator de segurança 4,34. O galho governa. Vento de 20 m/s não é o caso crítico deste mastro — a área projetada é pequena demais.

## De onde vem a excitação

| Fonte | Frequência |
|---|---|
| Terreno a 1,4 m/s, onda de 0,25 m | 5,60 Hz |
| Suspensão pneumática (frequência de canto) | 1,95 Hz |
| Rotação da roda | 2,23 Hz |

## Sensibilidade à massa da câmera

A massa da OAK-D é **estimativa** (P-06). No caso de projeto:

| Massa da OAK-D | Frequência | |
|---|---|---|
| 0,15 kg | 8,09 Hz | atende |
| 0,20 kg | 7,98 Hz | atende |
| 0,25 kg | 7,88 Hz | atende |
| 0,35 kg | 7,69 Hz | atende |
| 0,50 kg | 7,42 Hz | **abaixo do requisito** |

**O resultado NÃO é robusto a ela**: com a OAK-D em 0,50 kg o mastro cheio sai do requisito. Hoje o
mastro passa por 5 % — pouca folga para massas que ninguém mediu. Quando
as fichas técnicas chegarem, `python mastro.py` refaz tudo.

## Rigidez do mastro não é isolamento do sensor

O pedido do V4 manda diferenciar as duas coisas. A diferença não é de grau — é de sinal.

| | Enrijecer o mastro | Isolar a câmera |
|---|---|---|
| O que faz | sobe a frequência própria para longe da excitação | desacopla a câmera do mastro |
| Efeito na imagem | reduz a amplitude do movimento | reduz o borrão de alta frequência |
| Efeito na calibração | **nenhum** — a câmera segue solidária ao rover | **destrói** — a extrínseca passa a depender da aceleração |

Isolar a câmera resolveria o borrão e criaria um problema maior.

A fusão de dados da IA usa a matriz extrínseca de cada câmera — onde ela está e para onde
aponta, em relação ao referencial do rover. Essa matriz é medida uma vez, na calibração, e
tratada como **constante**. Num mount rígido ela é constante de verdade: a câmera
acompanha o rover.

Num mount isolado ela deixa de ser. A câmera passa a se mover em relação ao chassi em
função da aceleração instantânea, com amplitude de milímetros e defasagem de fase. A
reconstrução 3D passa a ter um erro que varia com o terreno e que **nenhuma calibração
estática corrige**, porque não é um offset — é uma função do movimento.

Entre uma imagem com algum borrão de movimento e uma nuvem de pontos com erro variável de
origem desconhecida, a primeira é recuperável (obturador mais rápido, ganho maior,
estabilização auxiliada por IMU) e a segunda não.

Por isso: **câmera rígida, mastro rígido o bastante, e o problema de vibração resolvido
onde ele nasce.**


### O único sensor isolado continua sendo o LiDAR

E isolar o LiDAR está certo, porque ele é o caso oposto: mede distância instantânea ponto
a ponto, não integra imagem no tempo, e a extrínseca dele precisa valer na média.

Os coxins G-08 já existem desde a Rev E. A conta de verificação:

| | Valor |
|---|---|
| 4 coxins a 120 N/mm sob 0,30 kg | 201 Hz |
| Razão contra a excitação | 36× |
| Isola ou amplifica? | **isola** |

> Isolador só atenua acima de √2 vezes a própria frequência. Abaixo disso ele **amplifica**.
> A conta depende da massa do LiDAR, que é estimativa (P-11).

## O que continua aberto

- **massas reais**: OAK-D (P-06), térmica (P-30) e antena (P-37) — o mastro tem 5 % de folga sobre o requisito;
- **espectro real de vibração em campo** (ensaio V-12) — hoje a excitação é critério, e a margem de 2,0 não fecha;
- **FEA do caso 6** — este cálculo é analítico (Rayleigh conferido por Ritz de 5 modos), não
  substitui o modelo de elementos finitos, e o engaste real entra como hipótese de 0,95;
- **cabos** (P-40) — o furo do tubo está no limite de ocupação.
