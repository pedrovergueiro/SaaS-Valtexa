# Rover V4 — interligação e roteamento de cabos

> **VTX-RV4 · Revisão H · 12/10/2026**
> EMITIDO PARA COTAÇÃO E VALIDAÇÃO — NÃO LIBERADO PARA FABRICAÇÃO
>
> Documento **gerado** de `revisao-h/roteamento.py` sobre a geometria de
> `chassi-gaiola/modelo.py`. Não editar à mão: a próxima geração sobrescreve.


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
|---|---|---|---|---|---|---|
| 1 | Bateria → BMS | Potência | 1 | cabo de potência | — | — |
| 2 | BMS → Driver dos motores | Potência | 1 | cabo de potência | — | — |
| 3 | Driver → 4 motores-roda MPW86 | Potência | 4 | potência + encoder, conduíte | passa-cabo Ø32 na chapa de fundo, (±300; ±80) | ≥ 1,0 m |
| 4 | Bateria / BMS → Conversor DC/DC 12 V | Potência | 1 | cabo de potência | — | — |
| 5 | DC/DC 12 V → Jetson, switch, compressor, válvulas, faróis | Potência | feixe | cabo 12 V | — | — |
| 6 | E-STOP (tampa traseira) → Driver e BMS | Segurança (E-STOP) | 1 laço | cabo de 2 vias, hardwired | furo Ø22,5 na tampa K-05 | — |
| 7 | 3 × OAK-D do mastro +Y → Switch PoE+ | Dados e PoE (Ethernet) | 3 | M12 X 8 vias, por dentro do tubo | entrada Ø12 no tubo, saída lateral Ø20 na luva | ≥ 2,3 m |
| 8 | 3 × OAK-D do mastro −Y → Switch PoE+ | Dados e PoE (Ethernet) | 3 | M12 X 8 vias, por dentro do tubo | idem, no mastro −Y | ≥ 2,3 m |
| 9 | Térmicas removíveis (0 a 4) → Switch PoE+ ou Jetson | Dados e PoE (Ethernet) | 0 a 4 | M12; Ethernet ou USB (P-30) | idem, nos postos H1 a H4 | ≥ 2,0 m |
| 10 | C7 frontal, C8 traseira → Switch PoE+ | Dados e PoE (Ethernet) | 2 | M12 X | SOB o chassi: passagem para o compartimento NÃO ESTÁ NO MODELO | ≥ 1,5 m |
| 11 | C9 câmera de raiz → Switch PoE+ | Dados e PoE (Ethernet) | 1 | M12 X | dentro do compartimento | ≥ 1,0 m |
| 12 | LiDAR Livox Mid-360 → Switch PoE+ | Dados e PoE (Ethernet) | 1 | cabo do fabricante | furo Ø30 em G-06 e K-04 | ≥ 1,2 m |
| 13 | Terminal de satélite (opcional) → Switch PoE+ | Dados e PoE (Ethernet) | 0 ou 1 | Ethernet | furo Ø32 em T-07 e em K-05 (acrescentado nesta revisão) | ≥ 1,5 m |
| 14 | Switch PoE+ → Jetson Orin NX | Dados e PoE (Ethernet) | 1 | Ethernet | — | — |
| 15 | Jetson → Roteador / modem | Dados e PoE (Ethernet) | 1 | Ethernet | — | — |
| 16 | Antena GNSS RTK → Receptor GNSS | Sinal (coaxial, CAN, analógico) | 1 ou 2 | coaxial | Ø10 em T-10 (topo do mastro) ou Ø20 em N-01/K-05 (tampa) | ≥ 2,6 m |
| 17 | IMU → Jetson | Sinal (coaxial, CAN, analógico) | 1 | CAN ou serial | — | — |
| 18 | 4 sensores de altura W-16 → Controlador da suspensão | Sinal (coaxial, CAN, analógico) | 4 | analógico blindado | pelo passa-cabo da roda | — |
| 19 | Compressor → Reservatório → secador → manifold | Pneumática | 1 | tubo PU | — | — |
| 20 | Manifold → 4 foles | Pneumática | 4 | tubo PU Ø6, engate F-36 | pelo colar W-12 de cada canto | — |

Comprimentos **ESTIMADOS**: o trecho vertical vem da altura de cada posto no mastro; o percurso interno até
o switch é **suposição** de 800 mm (a posição do switch não está fechada, P-31), com
folga de 15 %. Servem para orçar o cabo, nunca para cortá-lo.

## Para a cotação do cabo

| Item | Quantidade | Comprimento total |
|---|---|---|
| M12 das OAK-D do mastro | 6 | 10,1 m |
| M12 das câmeras de extremidade (C7, C8) e de raiz (C9) | 3 | — |
| M12 das térmicas (opcional) | até 4 | até 6,7 m |
| Coaxial da antena GNSS no mastro (opcional) | até 2 | 2,6 m cada |

## Passagens pela estrutura

| Onde | Quem passa | Estado | Nota |
|---|---|---|---|
| Tubo M-10 — entrada Ø12, 30 mm abaixo de cada posto | cabos dos 5 postos de cada mastro | **SÓ NO TEXTO** | furo transversal: o modelo extrudado não o representa; passa-cabo F-60/F-61 (Ø12) |
| Luva M-01 — saída lateral Ø20 | todos os cabos do mastro | **SÓ NO TEXTO** | passa-cabo F-59 (Ø20). O F-46 do V3 era Ø32 e não cabia numa luva Ø42: corrigido |
| Topo do mastro — furo Ø10 axial do T-10 | coaxial da antena | **MODELADA** |  |
| Chapa de fundo C-01 — passa-cabo Ø32 (×4) | cabos dos motores-roda | **MODELADA** | em (300; 80, 300; -80…) |
| Tampa K-04 e suporte G-06 — Ø30 | LiDAR | **MODELADA** |  |
| Tampa K-05 — Ø20 sob a N-01 | antena GNSS na tampa | **MODELADA** |  |
| Tampa K-05 — Ø32 e 6 furos M5 sob o T-07 | terminal de satélite | **MODELADA** | FALTAVA: o T-07 tinha o furo, a tampa não. Acrescentado ao modelo e ao DXF da K-05 nesta revisão |
| Tampa K-05 — Ø22,5 sob o E-STOP | botão de emergência | **MODELADA** |  |
| Sob o chassi → compartimento | câmeras de extremidade C7 e C8 (T-06) | **FALTA** | o T-06 está a Z 210, fora do compartimento (Z ≥ 250); não há furo na chapa de fundo nem passa-cabo previsto. PENDÊNCIA nova |
| Colar W-12 — linha de ar | 4 tubos PU para os foles | **SÓ NO TEXTO** | o colar é estanque (a3 + junta); a passagem do tubo não está desenhada |

**O que isto revelou, e foi corrigido nesta revisão:** o berço do terminal de satélite (T-07) tinha o furo
de cabo e os 6 furos de fixação, mas a **tampa K-05 embaixo dele não tinha nenhum** — o berço não tinha onde
ser parafusado, nem por onde passar o cabo. Foram acrescentados à K-05, ao DXF e à lista de fixadores (F-58). E o
passa-cabo F-46 do V3 era para furo Ø32, que não cabe numa luva Ø42: agora são F-59 (Ø20, saída da luva) e F-60
(Ø12, entrada no tubo).

**O que continua aberto:** a entrada dos cabos das câmeras C7 e C8 no compartimento. Elas estão sob o chassi
(Z 210) e o compartimento começa em Z 250; não há furo na chapa de fundo nem passa-cabo previsto.

## Regras de roteamento — propostas

| Regra | O que diz |
|---|---|
| Potência e dados em lados diferentes | Potência (driver, BMS, DC/DC) pelo lado −Y; dados e PoE pelo lado +Y. Quando precisarem se cruzar, cruzam a 90°, nunca em paralelo. A distância mínima entre os dois depende do fabricante do driver e não está nas fichas que o projeto tem. |
| Nada de potência no tubo do mastro | O tubo leva só PoE/Ethernet e coaxial. Potência no mastro só se um sensor pedir tensão própria — e nenhum pede, com PoE. |
| Alívio de tração em toda saída | Cada cabo que sai do tubo, da luva ou do módulo térmico tem passa-cabo e alívio de tração. O cabo do módulo térmico sai pelo lado da braçadeira, com laço, para que o módulo saia sem esticá-lo. |
| E-STOP é laço de segurança | Contato em série, fiado ao driver e ao BMS, independente da rede e do computador. Software nenhum participa do corte. |
| Conector sempre separável do lado do módulo | M12 em todo posto de sensor: o cabo fica no mastro e o conector é o único ponto elétrico a desfazer na troca. O grau IP desse conjunto NÃO é declarado (V-11). |
| Cabo de motor com laço | Os 80 mm de curso da roda movem o motor em relação ao passa-cabo. O trecho exposto leva conduíte e um laço de folga; sem ele, o primeiro ciclo de suspensão fadiga o cabo. |