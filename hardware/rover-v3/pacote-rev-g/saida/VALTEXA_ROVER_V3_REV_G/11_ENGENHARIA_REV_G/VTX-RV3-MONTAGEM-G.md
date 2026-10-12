# Rover V3 — manual de montagem e posição das peças

> **VTX-RV3 · Revisão G · 11/10/2026**
> EMITIDO PARA COTAÇÃO E VALIDAÇÃO — NÃO LIBERADO PARA FABRICAÇÃO
>
> Documento **gerado** de `revisao-g/montagem.py` sobre a geometria de
> `chassi-gaiola/modelo.py`. Não editar à mão: a próxima geração sobrescreve.


## Para que serve este documento

Para montar o rover sem adivinhar. Ele responde três perguntas por peça: **onde** ela vai,
**contra o quê** ela encosta, e **como** ela prende. As duas primeiras são medidas no
modelo paramétrico; a terceira é decisão de projeto declarada.

A coluna "encosta em" é a mais útil na bancada: se a peça vizinha listada não estiver no
lugar quando você for montar, a ordem está errada — volte à seção de sequência.

Referencial: origem no solo, no centro do polígono das quatro rodas. **X** para a frente,
**Y** para a esquerda, **Z** para cima (ISO 8855). Todas as coordenadas em mm.


## Mapa de posições

55 códigos de peça fabricada. A coordenada é a caixa envolvente de UM exemplar — os demais são espelhados em X, em Y ou nos dois.


### Grupo Q — Quadro estrutural soldado

| item | nome | qt | X | Y | Z | encosta em | como prende |
|---|---|---|---|---|---|---|---|
| **Q-01** | Longarina | 4 | -521…521 | 268…298 | 250…280 | C-01, G-05, K-01, M-02, Q-02, Q-03, Q-04, Q-06 | TIG a2 contínuo nas travessas |
| **Q-06** | Tampa de extremidade | 8 | 521…523 | 268…298 | 250…280 | C-01, G-05, K-01, K-02, K-03, Q-01, Q-02, Q-04 | tampa de extremidade, TIG a2 em todo o contorno |
| **Q-02** | Travessa de extremidade | 4 | 493…523 | -268…268 | 250…280 | C-01, G-05, K-02, K-03, N-08, Q-01, Q-04, Q-05, Q-06, W-11 | TIG a2 contínuo nas longarinas |
| **Q-03** | Travessa da estação de roda | 4 | 335…365 | -268…268 | 250…280 | C-01, N-02, Q-01, Q-04, Q-05, W-11 | TIG a2 contínuo nas longarinas |
| **Q-04** | Montante entre anéis | 16 | -523…-493 | 268…298 | 280…310 | K-01, K-02, K-03, Q-01, Q-02, Q-03, Q-06 | TIG a2 contínuo nos dois anéis |
| **Q-05** | Bucha de compressão | 16 | 344…356 | 162…174 | 250…280 | C-01, Q-02, Q-03, W-11 | bucha soldada dentro do tubo, antes de fechar o anel |

### Grupo M — Mastros: base, haste e suportes de câmera

| item | nome | qt | X | Y | Z | encosta em | como prende |
|---|---|---|---|---|---|---|---|
| **M-02** | Chapa de reforço da base | 2 | -28…28 | 258…298 | 340…346 | K-01, M-01, M-10, Q-01 | reforço soldado no anel superior, antes da luva |
| **M-01** | Luva do mastro | 2 | -17…17 | 263…297 | 346…526 | K-01, M-02, M-10, M-20 | luva soldada no quadro, sobre o reforço M-02 |

### Grupo C — Chapa de fundo e nervuras

| item | nome | qt | X | Y | Z | encosta em | como prende |
|---|---|---|---|---|---|---|---|
| **C-01** | Chapa de fundo | 1 | -523…523 | -298…298 | 248…250 | B-01, C-02, E-01, E-02, K-01, K-02, K-03, N-03, N-04, N-05, N-06, Q-01, Q-02, Q-03, Q-05, Q-06, W-06, W-12, W-13 | M6 em porca-rebite no anel inferior · **10 N·m** |
| **C-02** | Nervura da chapa de fundo | 2 | 100…140 | -296…296 | 208…248 | C-01 | Ø4,8 na chapa + M6 no anel |

### Grupo W — Suspensão pneumática independente (4 cantos, soldados e usinados)

| item | nome | qt | X | Y | Z | encosta em | como prende |
|---|---|---|---|---|---|---|---|
| **W-01** | Braço longitudinal | 4 | 340…522 | 194…224 | 170…210 | W-02, W-03, W-04, W-07, W-08, W-09, W-10 | sobreposto na chapa W-02, filete a4 em cima e embaixo |
| **W-02** | Chapa de montagem do motor-roda | 4 | 290…412 | 224…234 | 38…210 | W-01, W-03, W-08 | recebe o braço W-01 e a tampa W-03; usinar DEPOIS de soldar |
| **W-03** | Tampa-gusset da ponta do braço | 4 | 334…340 | 194…224 | 170…210 | W-01, W-02 | tampa-gusset: fecha a ponta do tubo e amarra o braço à chapa, a4 |
| **W-04** | Alojamento da bucha do pivô | 4 | 483…517 | 190…228 | 173…207 | W-01, W-07 | atravessa o tubo do braço, filete a4 nas duas faces |
| **W-08** | Disco do prato do fole | 4 | 379…471 | 163…255 | 202…210 | W-01, W-02, W-09 | disco articulado no pino W-10, dentro do rasgo do braço |
| **W-09** | Orelha do prato do fole | 8 | 411…439 | 197…205 | 182…202 | W-01, W-08, W-10 | orelha soldada no disco W-08, em dispositivo |
| **W-10** | Pino do prato | 4 | 419…431 | 190…228 | 184…196 | W-01, W-09 | atravessa as paredes do braço e as orelhas; anel DIN 471 |
| **W-05** | Orelha da torre do pivô | 8 | 478…522 | 182…188 | 168…240 | W-06, W-07 | orelha soldada no berço W-06, filete a4 nos dois lados |
| **W-07** | Eixo do pivô | 4 | 490…510 | 179…239 | 180…200 | W-01, W-04, W-05 | passa pelas duas orelhas e pelas buchas; travado por anel DIN 471 |
| **W-06** | Berço do pivô | 4 | 476…522 | 156…262 | 240…248 | C-01, W-05, W-12 | M8×65 passante: berço do fole → bucha → chapa → berço do pivô · **25 N·m** |
| **W-11** | Berço do fole | 4 | 338…520 | 156…262 | 280…290 | Q-02, Q-03, Q-05, W-12 | M8×65 em X 508 e M8×50 em X 350, sobre buchas de compressão · **25 N·m** |
| **W-12** | Tubo do colar de vedação | 4 | 375…475 | 159…259 | 248…280 | C-01, W-06, W-11, W-13 | tubo soldado na flange W-13, filete a3 estanque |
| **W-13** | Flange do colar | 4 | 355…470 | 139…279 | 244…248 | C-01, W-12 | Ø4,8 na chapa de fundo, com junta NBR nas duas faces |

### Grupo G — Gaiola de proteção (2 módulos idênticos)

| item | nome | qt | X | Y | Z | encosta em | como prende |
|---|---|---|---|---|---|---|---|
| **G-01** | Trilho lateral | 4 | 32…522 | 278…298 | 377…397 | G-02, G-03, G-04, G-07, K-01, K-02, K-03, K-04, K-05 | TIG a2 nos trilhos transversais |
| **G-07** | Tampa do trilho | 8 | 30…32 | 278…298 | 377…397 | G-01, G-02, G-04, K-01, K-02, K-03, K-04, K-05 | tampa do trilho, TIG a2 no contorno |
| **G-02** | Trilho transversal | 4 | 503…523 | -278…278 | 377…397 | G-01, G-04, G-07, K-02, K-03, K-04, K-05, K-06, N-08 | TIG a2 nos trilhos laterais |
| **G-03** | Barra intermediária | 4 | 220…240 | -278…278 | 377…397 | G-01, G-06, K-04, K-05, N-01 | TIG a2 nos trilhos laterais |
| **G-04** | Montante da gaiola | 12 | 503…523 | 278…298 | 343…377 | G-01, G-02, G-05, G-07, K-01, K-02, K-03 | montante soldado no anel e na sapata |
| **G-05** | Sapata | 12 | 453…523 | 268…298 | 340…343 | G-04, K-01, K-02, K-03, Q-01, Q-02, Q-06 | M6 em porca-rebite no anel superior · **10 N·m** |
| **G-06** | Suporte do LiDAR | 1 | 215…345 | -55…55 | 398…403 | G-03, G-08, K-04 | M5×16 em porca-rebite, sobre 4 coxins G-08 · **5 N·m** |
| **G-08** | Coxim antivibração | 4 | 248…262 | -32…-18 | 403…413 | G-06 | M4 no suporte do LiDAR · **2 N·m** |

### Grupo K — Carenagens e tampas

| item | nome | qt | X | Y | Z | encosta em | como prende |
|---|---|---|---|---|---|---|---|
| **K-01** | Carenagem lateral (meia) | 4 | 0…523 | 298…300 | 250…397 | C-01, G-01, G-04, G-05, G-07, K-02, K-03, K-04, K-05, M-01, M-02, Q-01, Q-04, Q-06 | M5×12 em porca-rebite nas paredes externas · **5 N·m** |
| **K-02** | Carenagem frontal | 1 | 523…525 | -300…300 | 250…397 | C-01, G-01, G-02, G-04, G-05, G-07, K-01, K-04, N-08, Q-02, Q-04, Q-06 | M5×12 em porca-rebite nas paredes externas · **5 N·m** |
| **K-03** | Carenagem traseira | 1 | -525…-523 | -300…300 | 250…397 | C-01, G-01, G-02, G-04, G-05, G-07, K-01, K-05, Q-02, Q-04, Q-06 | M5×12 em porca-rebite nas paredes externas · **5 N·m** |
| **K-04** | Tampa superior dianteira | 1 | 30…525 | -300…300 | 397…398 | G-01, G-02, G-03, G-06, G-07, K-01, K-02, K-06 | M5×12 em porca-rebite no anel da gaiola · **5 N·m** |
| **K-05** | Tampa superior traseira | 1 | -525…-30 | -300…300 | 397…398 | E-10, E-11, G-01, G-02, G-03, G-07, K-01, K-03, K-06, N-01 | M5×12 em porca-rebite no anel da gaiola · **5 N·m** |
| **K-06** | Faixa central | 1 | -55…55 | -256…256 | 398…399 | G-02, K-04, K-05 | M5×12 em porca-rebite, por cima das duas tampas · **5 N·m** |

### Grupo M — Mastros: base, haste e suportes de câmera

| item | nome | qt | X | Y | Z | encosta em | como prende |
|---|---|---|---|---|---|---|---|
| **M-10** | Haste do mastro | 2 | -12…12 | 268…292 | 346…1782 | M-01, M-02, M-11, M-12, M-20 | M6×12 passante na luva, 2 por mastro · **10 N·m** |
| **M-11** | Bainha anti-galho | 6 | -14…14 | 266…294 | 536…960 | M-10, M-12 | bainha deslizada sobre a haste, sem fixador |
| **M-12** | Ponta cônica | 2 | -14…14 | 266…294 | 1782…1822 | M-10, M-11 | ponta cônica pressionada na bainha |
| **M-20** | Suporte da câmera | 6 | -45…45 | 297…303 | 415…485 | M-01, M-10, N-09 | parafuso U M6 na haste ou na luva · **8 N·m** |

### Grupo B — Retenção da bateria

| item | nome | qt | X | Y | Z | encosta em | como prende |
|---|---|---|---|---|---|---|---|
| **B-01** | Batente da bateria | 4 | 225…265 | -75…75 | 250…290 | C-01 | M6×20 na malha da chapa de fundo · **10 N·m** |

### Grupo E — Bandejas de eletrônica e E-STOP

| item | nome | qt | X | Y | Z | encosta em | como prende |
|---|---|---|---|---|---|---|---|
| **E-01** | Bandeja lateral | 2 | -190…190 | 210…264 | 250…252 | C-01 | M6×20 na malha da chapa de fundo · **10 N·m** |
| **E-02** | Bandeja de extremidade | 4 | 368…490 | 100…152 | 250…252 | C-01 | M6×20 na malha da chapa de fundo · **10 N·m** |
| **E-10** | Reforço do E-STOP | 1 | -500…-420 | -40…40 | 394…397 | E-11, K-05 | M5×16 na tampa traseira · **5 N·m** |
| **E-11** | Protetor do E-STOP | 3 | -485…-435 | 24…28 | 398…449 | E-10, K-05 | M5×16 na tampa traseira · **5 N·m** |

### Grupo N — Interfaces de sensores e sinalização

| item | nome | qt | X | Y | Z | encosta em | como prende |
|---|---|---|---|---|---|---|---|
| **N-01** | Suporte da antena GNSS | 1 | -405…-295 | -55…55 | 398…403 | G-03, K-05 | M5×16 em porca-rebite na tampa · **5 N·m** |
| **N-02** | Berço do IMU | 1 | 255…345 | -35…35 | 304…310 | N-03, Q-03 | M6×16, sobre espaçadores N-03 · **10 N·m** |
| **N-03** | Espaçador do berço | 4 | 272…284 | -31…-19 | 250…304 | C-01, N-02 | espaçador entre o berço e a chapa |
| **N-04** | Janela da câmera de raiz | 1 | 370…490 | -85…85 | 250…253 | C-01, N-07 | M4×12 em porca-rebite, com barras N-05 por cima · **2 N·m** |
| **N-05** | Barra de proteção da janela | 2 | 409…417 | -80…80 | 240…248 | C-01 | M4 sobre a janela de policarbonato · **2 N·m** |
| **N-06** | Aba do suporte da câmera de raiz | 2 | 395…485 | 92…95 | 250…289 | C-01, N-07 | aba soldada no suporte da câmera de raiz |
| **N-07** | Face inclinada da câmera de raiz | 1 | 399…480 | -95…95 | 254…292 | N-04, N-06 | M6×16 no conjunto da câmera de raiz · **10 N·m** |
| **N-08** | Reforço do farol | 2 | 521…523 | 120…180 | 341…376 | G-02, K-02, Q-02 | Ø4,8 na carenagem |
| **N-09** | Carenagem anti-galho da câmera | 6 | -25…45 | 303…337 | 425…475 | M-20 | M4×10 na carenagem da câmera · **2 N·m** |


## Sequência de montagem

Quinze etapas. A razão de cada uma estar nessa posição vem antes das instruções, de propósito: é a razão que diz o que acontece se alguém inverter duas etapas.


### 1. Quadro estrutural (Q)

Soldar o quadro completo com as buchas Q-05 JÁ DENTRO dos tubos. Depois de fechar o anel não há como pôr bucha nenhuma.

- Q-05 nas 16 posições de fixação da suspensão
- Q-06 nas pontas das longarinas

### 2. Base dos mastros (M-01, M-02)

Soldar antes de qualquer coisa chegar perto do quadro: o acesso para o maçarico desaparece quando a gaiola subir.

- Reforço M-02 primeiro, luva M-01 depois

### 3. Alívio de tensão e aplainamento do quadro

Com todo o aço e alumínio de solda do quadro já no lugar. Depois disto o quadro não solda mais.

- Verificar diagonal e planeza do anel inferior

### 4. Cantos de suspensão (W), nas quatro bancadas

Cada canto é um subconjunto independente. Soldar e usinar os quatro FORA do rover — a usinagem da chapa W-02 exige acesso de fresa dos dois lados.

- Ver a sequência detalhada de 12 passos na folha 33

### 5. Colares W-12 na chapa de fundo C-01

Antes de a chapa subir no quadro: a flange do colar fica na face de BAIXO e é rebitada por fora.

- Junta NBR nas duas faces de cada colar
- 4 colares, um por canto

### 6. Chapa de fundo C-01 e nervuras C-02

A chapa entra por baixo e é o que fecha o compartimento. As 16 posições de suspensão ficam sem parafuso ainda.

- Não apertar os M8 da suspensão nesta etapa

### 7. Berços do pivô W-06 e berços do fole W-11

Os quatro níveis de cada posição (berço do fole, bucha, chapa, berço do pivô) são apertados por UM parafuso M8×65. Montar os quatro níveis antes de apertar.

- Arruela de nylon entre o berço de aço e o alumínio
- Torque 25 N·m

### 8. Cantos de suspensão no rover

Pendurar cada canto pelo eixo W-07 nas orelhas W-05 já parafusadas. O braço fica solto até o fole entrar.

- Anel DIN 471 nas duas pontas do eixo

### 9. Foles W-10 e pratos W-08

Prato no pino W-09 primeiro, depois o fole: M12 inferior no prato e M12 superior no berço, com a porta de ar voltada para dentro.

- Não pressurizar ainda
- Cabo W-13 no mesmo aperto do prato

### 10. Motores-roda MPW86 nas chapas W-02

Sete M4×14 com trava química média. Engajamento máximo 4 mm — parafuso mais longo fura o motor por dentro.

- Torque 2,5 N·m
- Conferir a orientação dos 7 furos

### 11. Gaiola de proteção (G) e suporte do LiDAR

Dois módulos idênticos, parafusados nas sapatas G-05 do anel superior.

- O módulo traseiro é o dianteiro girado 180° em Z

### 12. Grupo pneumático (W-15) e bandeja W-16

Compressor, reservatório, secador e manifold na bandeja, dentro do compartimento. Linhas PU Ø6 até os quatro foles.

- Linha mais curta possível por canto
- Sensor de altura W-14 por canto

### 13. Parte B: mastros, bandejas, bateria e sensores

Tudo o que é interface. Só depois do ar funcionando: a altura muda o acesso.

- Ver folhas 17 a 22

### 14. Carenagens e tampas (K)

Último: são o que se tira para mexer em tudo o resto.

- Faixa central K-06 por cima das duas tampas

### 15. Enchimento, nivelamento e verificação

Ver folha 35. O rover não sai da bancada sem a verificação de folgas no curso completo.

- Nivelar nos quatro cantos
- Ensaio de estanqueidade de 12 h


## Torques de aperto

| Rosca | N·m | Onde |
|---|---|---|
| M4 inox A4-70 | 2.5 | motor-roda, janela de policarbonato, carenagem de câmera |
| M5 inox A4-70 | 5.0 | carenagens, tampas, suporte do LiDAR, E-STOP |
| M6 inox A4-70 | 10.0 | chapa de fundo, sapatas, bandejas, batentes, mastro |
| M8 inox A4-70 | 25.0 | suspensão: berço do fole, chapa e berço do pivô |
| M12 do fole | 40.0 | prato inferior e berço superior do fole |


Inox A4-70 lubrificado, a 70 % do escoamento. **O M8 da suspensão aperta quatro peças em
série** — berço do fole, bucha de compressão, chapa de fundo e berço do pivô — com duas
delas em alumínio. É a bucha de compressão que define o torque: sem ela, 25 N·m amassam o
tubo 30×30×2 e o aperto se perde na primeira semana de campo.


## Conferências de aceite

| O que medir | Critério | Por que importa |
|---|---|---|
| Bitola | 530 ± 1 mm, medida face a face das rodas | é a cota que paga a estabilidade desta revisão |
| Entre-eixos | 700 ± 1 mm | define a geometria do braço |
| Face de montagem do motor | planeza 0,1 mm, perpendicular 0,3 a A | sugestão 2.3 do fabricante — ver folha 29 |
| Alinhamento do braço | eixo do pivô paralelo a Y em 0,2/100 | desalinhamento força a bucha e come o curso |
| Vão livre nos quatro cantos | 150 ± 3 mm com o ar na pressão mínima | se um canto difere, o nivelamento nasce torto |
| Curso livre | girar cada braço de batente a batente, sem o fole | nenhuma interferência em todo o curso |
| Folga braço × chapa de fundo | ≥ 13 mm em compressão total | medida na estação da roda, que é a que mais sobe |
| Estanqueidade | queda ≤ 0,2 bar em 12 h com o sistema parado | acima disto o compressor cicla e a bateria paga |
| Ciclo do compressor | ≤ 15 % em regime | acima disto há vazamento — é alarme, não tolerância |

## O que não montar ainda

Três itens deste projeto não existem como componente escolhido, e improvisar qualquer um
deles na bancada custa a desmontagem:

1. **O fole W-15.** Nenhum modelo comercial escolhido (P-20). A interface está desenhada e
   aceita qualquer fole que feche a folha de requisitos da folha 07 — e aceita igualmente
   um cilindro pneumático de mesma área. Um fole fora de requisito muda curso, pressão e
   altura, e nenhum dos três se ajusta depois.
2. **A bucha autolubrificante do pivô** Ø23/Ø20 (P-21). O alojamento está em Ø23 H7.
3. **A bateria.** A altura máxima medida na zona central é
   87 mm, e a caixa estimada tem 130. Ver `VTX-RV3-ESPACO-G`.
