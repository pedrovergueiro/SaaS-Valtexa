# Rover V4 — roteiro de usinagem

> **VTX-RV4 · Revisão H · 12/10/2026**
> EMITIDO PARA COTAÇÃO E VALIDAÇÃO — NÃO LIBERADO PARA FABRICAÇÃO
>
> Documento **gerado** de `revisao-h/usinagem.py` sobre a geometria de
> `chassi-gaiola/modelo.py`. Não editar à mão: a próxima geração sobrescreve.


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


## Resumo por peça

| item | nome | qt | material | ops | corte | usinagem | solda | ops × qt |
|---|---|---|---|---|---|---|---|---|
| **W-01** | Braço longitudinal | 4 | Aço 1020 | 7 | 1 | 5 | 1 | 28 |
| **W-02** | Chapa de montagem do motor-roda | 4 | Aço A36 | 6 | 1 | 4 | 1 | 24 |
| **W-03** | Tampa-gusset da ponta do braço | 4 | Aço A36 | 2 | 1 | 0 | 1 | 8 |
| **W-04** | Alojamento da bucha do pivô | 4 | Aço 1045 | 3 | 0 | 3 | 0 | 12 |
| **W-05** | Orelha da torre do pivô | 8 | Aço A36 | 4 | 1 | 2 | 1 | 32 |
| **W-06** | Berço do pivô | 4 | Aço A36 | 4 | 1 | 2 | 1 | 16 |
| **W-07** | Eixo do pivô | 4 | Inox 304 | 3 | 0 | 3 | 0 | 12 |
| **W-08** | Disco do prato do fole | 4 | Aço A36 | 4 | 0 | 3 | 1 | 16 |
| **W-09** | Orelha do prato do fole | 8 | Aço A36 | 3 | 1 | 1 | 1 | 24 |
| **W-10** | Pino do prato | 4 | Inox 304 | 2 | 0 | 2 | 0 | 8 |
| **W-11** | Berço do fole | 4 | Al 6061-T6 | 4 | 1 | 3 | 0 | 16 |
| **W-13** | Flange do colar | 4 | Aço A36 | 3 | 1 | 1 | 1 | 12 |
| **W-12** | Tubo do colar de vedação | 4 | Aço A36 | 3 | 0 | 2 | 1 | 12 |
| **Q-05** | Bucha de compressão | 16 | Aço SAE 1020 | 2 | 0 | 1 | 1 | 32 |
| **M-01** | Luva do mastro | 2 | Aço SAE 1020 | 4 | 1 | 2 | 1 | 8 |
| **T-01** | Braçadeira do mastro (metade) | 20 | Al 6061-T6 | 4 | 1 | 3 | 0 | 80 |
| **T-02** | Prato de interface VMS-60 | 10 | Al 6061-T6 | 7 | 1 | 6 | 0 | 70 |
| **T-03** | Adaptador de sensor VMS-60 | 9 | Al 6061-T6 | 3 | 1 | 2 | 0 | 27 |
| **T-04** | Adaptador térmico removível VMS-60 | 4 | Al 6061-T6 | 4 | 1 | 3 | 0 | 16 |
| **T-05** | Protetor sacrificial da câmera | 10 | UHMW-PE | 2 | 1 | 1 | 0 | 20 |
| **T-06** | Berço VMS de extremidade | 2 | Al 6061-T6 | 2 | 1 | 1 | 0 | 4 |
| **T-07** | Berço do terminal satelital | 1 | Al 5052-H32 | 2 | 1 | 1 | 0 | 2 |
| **T-09** | Berço VMS da câmera de raiz | 1 | Al 6061-T6 | 2 | 1 | 1 | 0 | 2 |
| **T-10** | Adaptador da antena GNSS no mastro | 2 | Al 6061-T6 | 6 | 1 | 5 | 0 | 12 |
| **N-02** | Berço do IMU | 1 | Al 6061-T6 | 2 | 1 | 1 | 0 | 2 |


## Roteiro detalhado


### W-01 — Braço longitudinal

4 un · Aço 1020 · Tubo ret. 40×30×3 × 182

| op | operação | ferramenta | cota / tolerância | acabamento |
|---|---|---|---|---|
| corte 1 | Serrar o tubo no comprimento | serra de fita | 182 ± 0,5 | — |
| **USINAR** 2 | Furar as duas paredes laterais para o alojamento da bucha | fresa de topo Ø16 + interpolação | 2× Ø34 H11, coaxiais em 0,2 | Ra 12,5 |
| **USINAR** 3 | Fresar o rasgo do prato na parede superior | fresa de topo Ø10 | 24 × 34, centro em X 425 ± 0,3 | Ra 6,3 |
| **USINAR** 4 | Furar as duas paredes laterais para o pino do prato | broca Ø11,8 + alargador | 2× Ø12 H7, coaxiais em 0,05 | Ra 1,6 |
| **SOLDA** 5 | SOLDAR o alojamento W-04, a chapa W-02 e a tampa W-03 | TIG/MIG | filete a4 contínuo; ver folha 33 | — |
| **USINAR** 6 | DEPOIS da solda: alargar o alojamento da bucha | alargador de haste longa | Ø23 H7 passante nas duas paredes | Ra 1,6 |
| **USINAR** 7 | Conferir o paralelismo do eixo do pivô com a face da chapa | desempeno + relógio | 0,2 em 100 | — |

### W-02 — Chapa de montagem do motor-roda

4 un · Aço A36 · Chapa 124×148×10

| op | operação | ferramenta | cota / tolerância | acabamento |
|---|---|---|---|---|
| corte 1 | Cortar o contorno | laser (DXF 1:1) | contorno livre ± 0,3 | — |
| **USINAR** 2 | Furar o alojamento do motor | torno vertical ou fresa + interpolação | Ø88 H8, concentricidade 0,1 ao datum C | Ra 3,2 |
| **USINAR** 3 | Furar os 7 passantes do flange do motor | broca Ø4,5 | 7× Ø4,5 eq. esp. em PCD 95, posição Ø0,2 (B, C) | Ra 12,5 |
| **SOLDA** 4 | SOLDAR o braço W-01 e a tampa W-03 | TIG/MIG | filete a4 em cima e embaixo da sobreposição | — |
| **USINAR** 5 | DEPOIS da solda: faceamento da face de montagem (datum B) | fresa de facear Ø63 | perpendicular 0,3 a A · planeza ISO 2768-K · e ≥ 9,5 | Ra 3,2 |
| **USINAR** 6 | Conferir a planicidade na face usinada | desempeno + relógio | planeza pela ISO 2768-K (0,4) na área de contato Ø105,7 — a cota de 0,1 saiu na Rev I | — |

### W-03 — Tampa-gusset da ponta do braço

4 un · Aço A36 · Chapa 40×40×6

| op | operação | ferramenta | cota / tolerância | acabamento |
|---|---|---|---|---|
| corte 1 | Cortar o contorno | laser (DXF 1:1) | 30 × 40 ± 0,3 | — |
| **SOLDA** 2 | SOLDAR na ponta do braço e na chapa W-02 | TIG/MIG | filete a4 em todo o contorno — é o que fecha o tubo | — |

### W-04 — Alojamento da bucha do pivô

4 un · Aço 1045 · Barra Ø34, furo Ø23 H7 × 44

| op | operação | ferramenta | cota / tolerância | acabamento |
|---|---|---|---|---|
| **USINAR** 1 | Tornear o diâmetro externo e facear as duas pontas | torno | Ø34 h11 × 38 ± 0,2 | Ra 6,3 |
| **USINAR** 2 | Furar e pré-alargar o alojamento | torno | Ø22,7 (sobremetal para alargar depois de soldar) | Ra 3,2 |
| **USINAR** 3 | Chanfrar as duas bocas | torno | 1 × 45° | — |

### W-05 — Orelha da torre do pivô

8 un · Aço A36 · Chapa 44×70×6, furo Ø20 H7

| op | operação | ferramenta | cota / tolerância | acabamento |
|---|---|---|---|---|
| corte 1 | Cortar o contorno | laser (DXF 1:1) | contorno ± 0,3 | — |
| **USINAR** 2 | Alargar o furo do eixo | broca Ø19,8 + alargador | Ø20 H7 | Ra 1,6 |
| **SOLDA** 3 | SOLDAR no berço W-06, as duas orelhas no mesmo dispositivo | TIG/MIG | filete a4; distância entre faces internas 42 ± 0,2 | — |
| **USINAR** 4 | DEPOIS da solda: alargar os dois furos no mesmo passe | alargador de haste longa | 2× Ø20 H7 coaxiais em 0,05 | Ra 1,6 |

### W-06 — Berço do pivô

4 un · Aço A36 · Chapa 46×106×8

| op | operação | ferramenta | cota / tolerância | acabamento |
|---|---|---|---|---|
| corte 1 | Cortar o contorno e os 2 furos de fixação | laser (DXF 1:1) | 2× Ø8,5, posição ± 0,2 | — |
| **SOLDA** 2 | SOLDAR as duas orelhas W-05 | TIG/MIG | ver W-05 op. 3 | — |
| **USINAR** 3 | Facear a face de assento, DEPOIS da solda | fresa de facear | planeza 0,15 na face que encosta na chapa de fundo | Ra 6,3 |
| **USINAR** 4 | Zincar ou pintar o conjunto soldado | tratamento | aço contra alumínio: isolar — arruela de nylon no parafuso | — |

### W-07 — Eixo do pivô

4 un · Inox 304 · Barra Ø20 h7 × 66, 2 ran. anéis

| op | operação | ferramenta | cota / tolerância | acabamento |
|---|---|---|---|---|
| **USINAR** 1 | Tornear o diâmetro do eixo | torno CNC | Ø20 h7 × 66 ± 0,2 | Ra 0,8 |
| **USINAR** 2 | Abrir as duas ranhuras de anel elástico | torno, bedame de 1,1 | DIN 471 para Ø20, distância entre ranhuras 58 ± 0,2 | Ra 3,2 |
| **USINAR** 3 | Chanfrar as duas pontas | torno | 1,5 × 20° | — |

### W-08 — Disco do prato do fole

4 un · Aço A36 · Disco Ø92×8, M12 central

| op | operação | ferramenta | cota / tolerância | acabamento |
|---|---|---|---|---|
| **USINAR** 1 | Tornear o disco | torno | Ø92 h11 × 8 ± 0,2 | Ra 3,2 |
| **USINAR** 2 | Facear a face de assento do fole | torno | planeza 0,05 · perpendicular 0,1 ao eixo | Ra 1,6 |
| **USINAR** 3 | Rosquear o furo central | torno + macho | M12 × 1,75, profundidade 8 passante | — |
| **SOLDA** 4 | SOLDAR as duas orelhas W-09, em dispositivo | TIG/MIG | filete a4; 2× Ø12 H7 coaxiais em 0,05 depois de soldar | Ra 1,6 |

### W-09 — Orelha do prato do fole

8 un · Aço A36 · Chapa 28×26×8, furo Ø12 H7

| op | operação | ferramenta | cota / tolerância | acabamento |
|---|---|---|---|---|
| corte 1 | Cortar o contorno e o furo do pino | laser (DXF 1:1) | 28 × 26 ± 0,3 | — |
| **USINAR** 2 | Alargar o furo do pino | alargador | Ø12 H7 | Ra 1,6 |
| **SOLDA** 3 | SOLDAR no disco W-08, em dispositivo | TIG/MIG | filete a4; eixo do pino paralelo à face do disco em 0,1 | — |

### W-10 — Pino do prato

4 un · Inox 304 · Barra Ø12 h7 × 42

| op | operação | ferramenta | cota / tolerância | acabamento |
|---|---|---|---|---|
| **USINAR** 1 | Tornear o pino | torno CNC | Ø12 h7 × 42 ± 0,2 | Ra 0,8 |
| **USINAR** 2 | Abrir as duas ranhuras de anel elástico | torno, bedame de 1,0 | DIN 471 para Ø12, distância 36 ± 0,2 | Ra 3,2 |

### W-11 — Berço do fole

4 un · Al 6061-T6 · Chapa 180×106×10

| op | operação | ferramenta | cota / tolerância | acabamento |
|---|---|---|---|---|
| corte 1 | Cortar o contorno, os 4 furos de fixação e os 2 do fole | laser (DXF 1:1) | 4× Ø8,5 ± 0,2 · Ø14 central ± 0,2 · Ø12 da porta de ar | — |
| **USINAR** 2 | Facear as duas faces | fresa de facear | e = 10 ± 0,1 · paralelismo 0,1 | Ra 3,2 |
| **USINAR** 3 | Rosquear o furo central do fole | macho | M12 × 1,75 passante | — |
| **USINAR** 4 | Rebarbar e anodizar | tratamento | anodização dura 15 µm | — |

### W-13 — Flange do colar

4 un · Aço A36 · Chapa Ø140×4, cortada em |X| 470

| op | operação | ferramenta | cota / tolerância | acabamento |
|---|---|---|---|---|
| corte 1 | Cortar a flange e os 6 rebites | laser (DXF 1:1) | perfil de círculo cortado em |X| 470; 6× Ø4,9 | — |
| **USINAR** 2 | Facear as duas faces de junta | fresa | planeza pela ISO 2768-K nas duas faces que recebem junta NBR (0,1 saiu na Rev I) | Ra 3,2 |
| **SOLDA** 3 | SOLDAR no tubo W-12 (os dois em aço A36 desde a Rev I) | MAG/TIG | filete a3 estanque em todo o contorno — a junta tem de selar | — |

### W-12 — Tubo do colar de vedação

4 un · Aço A36 · Tubo Ø100×3 × 32

| op | operação | ferramenta | cota / tolerância | acabamento |
|---|---|---|---|---|
| **USINAR** 1 | Tornear o tubo do colar | torno | Ø100 ext. × Ø94 int. × 32 ± 0,3 | Ra 6,3 |
| **SOLDA** 2 | SOLDAR a flange W-13 | TIG | ver W-13 op. 3 | — |
| **USINAR** 3 | Ensaio de estanqueidade do conjunto soldado | ar a 0,5 bar em água | sem bolha em 60 s | — |

### Q-05 — Bucha de compressão

16 un · Aço SAE 1020 · Barra Ø12, furo Ø8,5

| op | operação | ferramenta | cota / tolerância | acabamento |
|---|---|---|---|---|
| **USINAR** 1 | Tornear a bucha de compressão | torno | Ø12 × 30 ± 0,1, furo Ø8,5 | Ra 6,3 |
| **SOLDA** 2 | SOLDAR dentro do tubo ANTES de fechar o anel | TIG | depois de fechar o anel não há acesso | — |

### M-01 — Luva do mastro

2 un · Aço SAE 1020 · Tubo Ø42×5 × 180

| op | operação | ferramenta | cota / tolerância | acabamento |
|---|---|---|---|---|
| corte 1 | Serrar a luva no comprimento | serra de fita | 180 ± 0,5 | — |
| **USINAR** 2 | Alargar o furo da haste | alargador | Ø32 H8 | Ra 3,2 |
| **USINAR** 3 | Furar e rosquear os travamentos | fresa + macho | 2× M6 passante | — |
| **SOLDA** 4 | SOLDAR no quadro, sobre o reforço M-02 | TIG | perpendicular 0,5 em 180 ao plano do deck | — |

### T-01 — Braçadeira do mastro (metade)

20 un · Al 6061-T6 · Chapa 60×50×12, canal usinado

| op | operação | ferramenta | cota / tolerância | acabamento |
|---|---|---|---|---|
| corte 1 | Cortar o contorno e os 2 furos de aperto | laser (DXF 1:1) | 60 × 50 ± 0,3 · 2× Ø6,6 | — |
| **USINAR** 2 | Fresar o canal semicircular do tubo | fresa de topo + interpolação | R16 ou R21 conforme o posto, ± 0,1 | Ra 6,3 |
| **USINAR** 3 | Serrilhar o canal | fresa de serrilha ou jato | serrilha axial: é o que impede a braçadeira de escorregar sob vibração | Rz 25 |
| **USINAR** 4 | Anodizar | tratamento | anodização dura 15 µm | — |

### T-02 — Prato de interface VMS-60

10 un · Al 6061-T6 · Chapa 72×64×10, 7 furos de índice

| op | operação | ferramenta | cota / tolerância | acabamento |
|---|---|---|---|---|
| corte 1 | Cortar o contorno e todos os furos | laser (DXF 1:1) | 4× Ø4,2 (furo de macho M5) em 56 × 36 · 7× Ø6 de índice em R26 · Ø8,5 central | — |
| **USINAR** 1,5 | Rosquear os 4 furos M5 | macho M5 + calibre passa/não-passa | M5-6H passante nos 10 mm do prato — é a rosca que prende o adaptador | — |
| **USINAR** 2 | Alargar o alojamento do pino de referência | alargador | Ø8 H7 — é a cota que define a repetibilidade da interface | Ra 1,6 |
| **USINAR** 3 | Alargar o alojamento do pino anti-giro | alargador | Ø6 H7, a 26 ± 0,02 do pino de referência | Ra 1,6 |
| **USINAR** 4 | Alargar os 7 furos de índice | alargador em divisor | 7× Ø6 H7 em R26, passo 10° ± 0,05° | Ra 1,6 |
| **USINAR** 5 | Facear a face VMS | fresa de facear | planeza 0,05 — é a face de referência da câmera | Ra 1,6 |
| **USINAR** 6 | Prensar os dois pinos | prensa | H7/s6, pinos ISO 2338 em inox | — |

### T-03 — Adaptador de sensor VMS-60

9 un · Al 6061-T6 · Chapa 72×64×6

| op | operação | ferramenta | cota / tolerância | acabamento |
|---|---|---|---|---|
| corte 1 | Cortar o contorno, a face VMS e a furação do sensor | laser (DXF 1:1) | 4× Ø5,5 em 56 × 36 · Ø8 H7 · Ø6 H7 · furação do modelo | — |
| **USINAR** 2 | Alargar os dois alojamentos de pino | alargador | Ø8 H7 e Ø6 H7 | Ra 1,6 |
| **USINAR** 3 | Anodizar | tratamento | anodização dura 15 µm | — |

### T-04 — Adaptador térmico removível VMS-60

4 un · Al 6061-T6 · Chapa 72×64×6, sem furação de sensor

| op | operação | ferramenta | cota / tolerância | acabamento |
|---|---|---|---|---|
| corte 1 | Cortar o contorno, a face VMS e os alojamentos de pino | laser (DXF 1:1) | 4× Ø5,5 em 56 × 36 · Ø8 H7 · Ø6 H7 | — |
| **USINAR** 2 | Alargar os dois alojamentos de pino | alargador | Ø8 H7 e Ø6 H7 | Ra 1,6 |
| **USINAR** 3 | Furação do SENSOR | — | A DEFINIR com o modelo da câmera térmica (P-30): a peça NÃO sai da oficina sem ela | — |
| **USINAR** 4 | Anodizar | tratamento | anodização dura 15 µm | — |

### T-05 — Protetor sacrificial da câmera

10 un · UHMW-PE · UHMW-PE 112×46×6

| op | operação | ferramenta | cota / tolerância | acabamento |
|---|---|---|---|---|
| corte 1 | Cortar o contorno | fresa ou laser de plástico | ± 0,5 — peça sacrificial | — |
| **USINAR** 2 | Furar os 2 passantes de fixação | broca Ø4,5 | ± 0,3 | — |

### T-06 — Berço VMS de extremidade

2 un · Al 6061-T6 · Chapa 72×64×4

| op | operação | ferramenta | cota / tolerância | acabamento |
|---|---|---|---|---|
| corte 1 | Cortar o contorno e a face VMS | laser (DXF 1:1) | idem T-03 | — |
| **USINAR** 2 | Alargar os dois alojamentos de pino | alargador | Ø8 H7 e Ø6 H7 | Ra 1,6 |

### T-07 — Berço do terminal satelital

1 un · Al 5052-H32 · Chapa 280×240×4

| op | operação | ferramenta | cota / tolerância | acabamento |
|---|---|---|---|---|
| corte 1 | Cortar o contorno e os furos | laser (DXF 1:1) | 6× Ø5,5 · Ø32 de passa-cabo | — |
| **USINAR** 2 | Dobrar as abas de rigidez | dobradeira | 15 mm a 90°, 2 lados | — |

### T-09 — Berço VMS da câmera de raiz

1 un · Al 6061-T6 · Chapa 72×64×10

| op | operação | ferramenta | cota / tolerância | acabamento |
|---|---|---|---|---|
| corte 1 | Cortar o contorno e a face VMS | laser (DXF 1:1) | idem T-03 | — |
| **USINAR** 2 | Alargar os dois alojamentos de pino | alargador | Ø8 H7 e Ø6 H7 | Ra 1,6 |

### T-10 — Adaptador da antena GNSS no mastro

2 un · Al 6061-T6 · Barra Ø26 × 60, furo Ø10, rosca 5/8"-11 UNC

| op | operação | ferramenta | cota / tolerância | acabamento |
|---|---|---|---|---|
| corte 1 | Serrar a barra | serra de fita | Ø30 × 64 (sobremetal) | — |
| **USINAR** 2 | Tornear o encaixe | torno CNC | Ø26 g6 × 40 — entra no furo do tubo | Ra 1,6 |
| **USINAR** 3 | Furar o centro para o cabo | broca | Ø10 passante, rebarbar as duas bocas | Ra 3,2 |
| **USINAR** 4 | Furar a trava transversal | broca Ø6,6 | 1× Ø6,6 a 20 mm da face inferior (F-57) | — |
| **USINAR** 5 | Interface da antena | — | rosca 5/8"-11 UNC é A VALIDAR com o modelo escolhido (P-37): NÃO usinar antes | — |
| **USINAR** 6 | Anodizar | tratamento | anodização dura 15 µm | — |

### N-02 — Berço do IMU

1 un · Al 6061-T6 · Chapa 90×70×6, face usinada

| op | operação | ferramenta | cota / tolerância | acabamento |
|---|---|---|---|---|
| corte 1 | Cortar o contorno e os furos | laser (DXF 1:1) | contorno ± 0,3 | — |
| **USINAR** 2 | Facear a face de assento do IMU | fresa de facear | planeza 0,05 · paralela ao plano do deck em 0,1 | Ra 1,6 |


## Ajustes e folgas

| Interface | Ajuste | O que ele garante |
|---|---|---|
| Eixo do pivô W-07 na bucha autolubrificante | Ø20 h7 / bucha H7 | folga de 0,02 a 0,05 — o eixo gira |
| Bucha autolubrificante no alojamento W-04 | Ø23 H7 / bucha s6 | interferência leve: a bucha é prensada e não gira |
| Eixo do pivô W-07 nas orelhas W-05 | Ø20 H7 | ajuste deslizante: o eixo entra à mão e é travado por anel |
| Pino W-09 nas orelhas do prato W-08 | Ø12 h7 / H7 | folga mínima: o prato articula poucos graus |
| Pino de referência no prato T-02 | Ø8 H7 / s6 | interferência: o pino fica no prato e nunca sai |
| Pino de referência no adaptador T-03 | Ø8 H7 / h6 | folga 0,024 mm: entra à mão e dá 0,048° de repetibilidade |
| Pino anti-giro no adaptador | Ø6 H7 / h6 | idem, a 26 mm — é o braço angular |
| Pino de índice de inclinação | Ø6 H7 / h6 | passo de 10°, 7 posições |
| Motor MPW86 no alojamento da chapa W-02 | Ø88 H8 / motor Ø86,5 máx. | folga de montagem; a centragem é pelo PCD, não pelo diâmetro |
| Fole W-10 dentro do colar W-12 | Ø88 máx. / Ø94 int. | 3 mm radiais: o fole dilata ao pressurizar |


## Notas gerais

- Toda cota sem tolerância indicada segue ISO 2768-mK; conjuntos soldados, ISO 13920-BF.
- As operações marcadas DEPOIS DA SOLDA são obrigatoriamente posteriores: a solda distorce, e usinar antes joga a tolerância fora.
- Os DXF em saida/dxf são 1:1 e já traçam contorno e furos. Eles NÃO carregam tolerância — a tolerância está nesta tabela e nas folhas 28 a 31.
- Aço contra alumínio em qualquer interface: isolar. É o item de corrosão galvânica de materiais.py, e nesta revisão ele aparece em W-06 e nos parafusos M8 da suspensão.
- Nenhuma peça deve ser usinada antes de a massa oficial ser fechada (P-02) e de o caso 9 do FEA rodar (P-22). Esta tabela é para COTAR.


## Conferência automática

- roteiro declarado para peça que não existe no modelo: **nenhuma**
- peça do grupo W sem roteiro declarado: **nenhuma**