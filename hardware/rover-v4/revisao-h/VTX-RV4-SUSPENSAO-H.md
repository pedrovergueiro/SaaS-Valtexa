# Rover V4 — suspensão pneumática independente

> **VTX-RV4 · Revisão H · 11/10/2026**
> EMITIDO PARA COTAÇÃO E VALIDAÇÃO — NÃO LIBERADO PARA FABRICAÇÃO
>
> Cálculo completo em `revisao-h/suspensao.py`. Rodando `python suspensao.py` saem todos os
> números deste documento, na mesma ordem.

---

## O que mudou, em uma frase

Quatro braços longitudinais independentes, um fole pneumático por canto, **sem barra
estabilizadora**, e a bitola subindo de 470 para 530 mm. A suspensão a ar entra no conjunto
fornecido — não é mais estudo paralelo.

---

## 1. A objeção que travava a suspensão a ar, e como ela caiu

As Revisões E e F recusaram a articulação em rolagem, e a razão estava escrita no próprio
modelo:

> *A articulação em rolagem (eixo oscilante, mola macia) derruba o tombamento de 37,7° para
> 20,1° — inaceitável em lavoura de café.*

Fole é mola macia. Pela mesma lógica, suspensão a ar com quatro cantos independentes cai na
condição recusada. A Rev F tentou contornar com **balancim longitudinal**: arfagem
pneumática, rolagem rígida por construção, porque o pivô do balancim é fixo no chassi.

A proposta era boa e tinha dois furos que a Rev F não fechou:

**Primeiro — ela não ajusta o vão livre.** Com o pivô fixo, mudar a pressão dos foles gira
os dois balancins no mesmo sentido, e isso é arfagem, não altura. O
`ALTURA_AJUSTAVEL_MM = 50` declarado no módulo da Rev F era incompatível com a própria
geometria daquele módulo. É erro da Rev F, e está registrado como tal na auditoria.

**Segundo — massa.** O balancim somava 6,85 kg de estrutura só para articular, antes dos
foles.

### A saída não é rigidez — é bitola e curso

A Rev H não tenta fazer o fole ser rígido em rolagem. Ela ataca os dois termos que
realmente determinam o tombamento:

**Bitola.** De 470 para 530 mm. Os 60 mm estavam sobrando: o envelope externo de 600 mm
nunca era usado inteiro — a face externa da roda ficava em |Y| 261, com 39 mm livres de cada
lado. Com 530, a face vai a 291,05, ainda 8,95 mm dentro da linha de 300. **E a carenagem
lateral não é afetada**: ela começa em Z 250 e a roda termina em Z 200. Não há sobreposição
vertical nenhuma — nunca houve.

**Curso.** A rolagem da carroceria não é limitada pela rigidez do fole; é limitada pelo
**fim de curso**. Com ±25 mm de curso em 530 mm de bitola, a carroceria rola **5,39° e nada
mais**: depois disso o fole do lado interno chega ao batente e a rigidez de rolagem passa a
ser a do batente, que é uma ordem de grandeza maior.

A Rev F calculava a rolagem como se o fole fosse livre até o limite geométrico, e por isso
achava 8,5° e perdia 4,9° de envelope. Com o batente no cálculo e a bitola em 530, o
resultado inverte.

### O resultado

Todos os arranjos no **mesmo CG**, o do inventário do V4 (`centro_massa.py`, estado projeto: 121,1 kg,
Z 336,2 mm, mastro cheio):

| Arranjo | Bitola | Tombamento | Envelope de estabilidade |
|---|---|---|---|
| Balancim da Rev F, rolagem rígida | 470 | 34,95° | 15,51° |
| Esta suspensão, se a bitola fosse 470 | 470 | 30,82° | 11,72° |
| **Rev H — como desenhada** | **530** | **34,89°** | **16,31°** |

**A suspensão macia fica mais estável que a rígida.** Não há mágica: 60 mm de bitola valem
mais que 5,4° de rolagem, e os 60 mm estavam disponíveis de graça. A linha do meio da tabela
é a que mostra de onde vem o ganho — sem a bitola, esta arquitetura perderia 3,8° de
envelope contra o balancim.

**Correção de 15/10/2026.** Esta tabela mostrava 39,92° / 20,89° para a Rev H e 39,44° / 19,57°
para o balancim. Os números da Rev H vinham do CG da Rev F do V3 (285,9 mm), sem o mastro do V4;
os do balancim, do CG da Rev F (294 mm). A conclusão continua de pé, mas a margem encolheu: o
envelope passa os **16,2° da baseline por apenas 0,1°**, e qualquer massa a mais no alto do mastro
o derruba abaixo do requisito.

---

## 2. Não há barra estabilizadora, e isso é cálculo

Uma barra estabilizadora troca rigidez de rolagem por transferência de carga em terreno
torcido. O limite é levantar roda: quando a transferência iguala a carga estática, a roda
descarrega e o rover passa a apoiar em três — exatamente a condição de margem ZERO que a
baseline já apontava e que a suspensão independente existe para eliminar.

Com rigidez de roda de **4,77 N/mm**, numa articulação de 60 mm num eixo:

| | Valor |
|---|---|
| Carga estática por roda | 310 N |
| Transferência dos foles sozinhos | 286 N |
| Sobra antes de descarregar a roda | 24 N |
| **Teto de rigidez para a barra** | **114 N·m/rad** |

114 N·m/rad é rigidez desprezível — não muda nada que valha a massa de uma barra, de dois
mancais e de duas bieletas. **Não há barra no projeto.**

Pela mesma razão, **os quatro circuitos de ar são independentes**, sem interligação
esquerda-direita. Interligar os lados equaliza pressão e zera a rigidez de rolagem: é o que
se faz quando se quer articulação, e articulação aqui já vem da independência dos braços.

### E a articulação, então?

Quem limita a articulação é o curso, não a carga:

> A roda bate no batente a **50 mm** de degrau, e só descarregaria a **130 mm**.

Isso é bom. Batente é peça, roda no ar é condição.

---

## 3. Geometria

| Parâmetro | Valor | Origem |
|---|---|---|
| Estação do pivô | \|X\| 500 mm | CALC — bucha Ø34 dentro de \|X\| 525 |
| Estação da roda | \|X\| 350 mm | entre-eixos 700, inalterado |
| Eixo do braço e do pivô | Z 190 mm | CRITÉRIO — horizontal |
| Braço efetivo (pivô → roda) | 150 mm | CALC |
| Estação do fole no braço | 75 mm do pivô | CRITÉRIO |
| Relação de movimento fole/roda | 0,500 | CALC |
| Curso de trabalho na roda | ± 25 mm | CRITÉRIO |
| Ajuste de vão livre | 150 → 180 mm | CRITÉRIO |
| Curso total na roda | 80 mm | CALC |
| Curso no fole | 40 mm | CALC |
| Giro do braço, batente a batente | 30,9° | CALC |
| Recuo da roda no curso | 5,4 mm | CALC |

### Por que o braço é horizontal

Não é preferência de desenho. Braço inclinado gera componente longitudinal de carga no pivô
a cada curso, e faz a relação de movimento variar ao longo dele — o fole vê carga diferente
em cada altura, e o controle de nível passa a brigar com a própria geometria. Horizontal, a
relação é constante e o pivô só vê carga vertical e longitudinal de tração.

### Por que o pivô dianteiro fica à frente da roda e o traseiro atrás

Para que a reação de torque do motor-roda gire os braços dos dois eixos em sentidos
opostos. O resultado é **arfagem pura e zero de altura**: a frente desce o que a traseira
sobe. Se os quatro pivôs ficassem do mesmo lado, a perturbação seria de altura, e o
nivelamento brigaria com o acelerador.

---

## 4. O fole

**O fole é comprado e não tem ficha técnica no projeto.** O que está desenhado é a
*interface* — prato, berço, colar, curso e altura — como requisito. Qualquer fole que feche
a tabela abaixo monta sem alterar desenho de usinagem nenhum, e um cilindro pneumático de
mesma área também fecha. É a pendência **P-20**.

| Requisito | Valor |
|---|---|
| Área efetiva | 3421 mm² ± 10 % |
| Ø externo máximo | 88 mm |
| Altura instalada (mín · nom · máx) | 57,5 · 70,0 · 97,5 mm |
| Curso útil | 40 mm |
| Pressão de trabalho (carga estática) | 1,81 bar |
| Pressão de projeto a suportar | 7,34 bar · admissível ≥ 8 bar |
| Batente interno de compressão | integrado, ≥ 4,5 kN |
| Fixação inferior · superior | M12 central · M12 central + porta R1/8 |
| Temperatura | −10 a +70 °C |
| Proteção | resistente a UV, ozônio e abrasão por poeira |

### A área saiu da pressão de projeto, não da estática

Esta foi a correção mais importante do dimensionamento. A primeira tentativa usou 2003 mm²
(Ø50,5 efetivo): a pressão estática ficava confortável em 3,13 bar e a de projeto ia a
**12,69 bar** — acima de qualquer fole industrial pequeno. Com 3421 mm² a estática cai para
1,81 e a de projeto para 7,34, dentro do teto de 8. **É o caso de carga raro que dimensiona
o componente, não o do dia a dia.**

### O fole nunca vê a carga de projeto

| | Valor |
|---|---|
| Carga estática na roda | 310 N |
| Carga de projeto na roda (3,0 × 1,35) | 1256 N |
| Rigidez na roda | 4,77 N/mm |
| Força na roda ao fim do curso de compressão | 429 N — **34 %** da de projeto |
| Absorvido pelo batente | 826 N |

A rigidez é baixa e o curso acaba antes. Por isso o **batente de compressão é requisito do
componente comprado** (integrado ao fole), e não peça de desenho. O de extensão é peça: o
cabo W-14, que limita a distensão no fim do curso.

Frequência de canto resultante: **1,95 Hz**. É faixa de veículo utilitário, apropriada para
um rover a 1,4 m/s em lavoura.

---

## 5. Tensões — as peças aguentam com folga

| Peça | Verificação | Valor | Fator de segurança |
|---|---|---|---|
| W-01 braço | flexão, seção fechada | 23,1 MPa | **9,07** |
| W-01 braço | flexão na seção do rasgo do prato | 44,8 MPa | **4,69** |
| W-01 ↔ W-02 | solda, 72 mm de sobreposição | — | **6,6** |
| W-07 eixo do pivô | corte e flexão | 2,2 / 21,1 MPa | **10,2** |
| W-05 orelha da torre | flexão | 17,9 MPa | **14,0** |
| W-10 pino do prato | corte em 4 planos | 5,6 MPa | **22,4** |
| W-11 berço do fole | flexão, vão 158 mm | 56,0 MPa | **4,29** |
| Bucha autolubrificante | pressão de contato | 1,7 MPa | limite 80 MPa |

Fatores de segurança altos não são desperdício aqui: as seções são as mínimas comerciais
disponíveis, e a peça que governa é a **fadiga**, não o escoamento — e fadiga não aparece
nesta tabela.

### Por que aço, e não alumínio

W-01, W-02, W-03, W-04, W-05, W-06, W-08 e W-09 são de aço. Não é preferência de material:

1. **Alumínio não tem limite de fadiga.** Aço carbono tem: abaixo dele não acumula dano.
   Alumínio acumula sempre, sem patamar. Para peças que veem uma ondulação de terreno a
   cada metro de lavoura, isso deixa de ser acadêmico.
2. **Alumínio soldado perde na ZTA.** O 6061-T6 cai a 110 MPa na zona afetada; o aço não
   perde. O fator de segurança do braço cairia de **9,07** para **4,75** só pela troca — e
   perderia o limite de fadiga, que não se recupera com espessura.
3. **É a sugestão 2.4 do fabricante**, que pedia a chapa do motor em aço. Ela está
   implementada nesta revisão, e com um argumento que a Rev F ainda não tinha: na Rev H a
   peça passou a ser de suspensão.

O custo é massa: **6,49 kg**. Se o engenheiro decidir alumínio, o número está calculado e a
decisão fica registrada com ele ao lado. O caso 9 do FEA (**P-22**, novo nesta revisão) é o
que confirma ou derruba esta escolha.

---

## 6. Reação de torque — o número que corrigiu a si mesmo

Numa roda com motor no cubo, a suspensão recebe **duas** coisas do acionamento: a força de
tração no contato e a reação de torque no estator. Elas giram o braço em **sentidos
opostos**. Em torno do pivô, a tração tem braço `Z_pivô` (190 mm) e a reação de torque tem
braço `raio da roda` (100 mm). O que sobra é a diferença: **90 mm**.

Com o pivô na cota do eixo da roda a diferença seria ZERO — antiesquat perfeito, o
acionamento não mexeria na suspensão. O vão livre de 150 mm proíbe o pivô a Z 100, e os
90 mm são o preço do vão livre.

| Condição | Torque | Tração | Δcarga na roda | Deslocamento |
|---|---|---|---|---|
| Rolamento em solo solto | 3,1 N·m | 0,10 g | 19 N | **3,9 mm** |
| Contínuo do motor | 20,0 N·m | 0,65 g | 120 N | 25,2 mm — bate no batente |
| Pico do motor | 35,0 N·m | 1,13 g | 210 N | 44,1 mm — bate no batente |

No ponto de operação real é desprezível. No contínuo do motor — que é condição de rampa
forte a 0,65 g de esforço trator, não de cruzeiro — consome o curso de trabalho. Bater no
batente em tração máxima é comportamento normal de suspensão. Ensaio **V-07**.

---

## 7. Massa — e ela é o problema desta revisão

| | kg | Z (mm) |
|---|---|---|
| Grupo W, estrutura desenhada | 13,258 | 205,5 |
| Grupo pneumático, comprado (FAIXA de catálogo) | 7,730 | 260,7 |
| Sai: grupo S da Rev F | −4,538 | 201,9 |
| **Líquido** | **+16,45** | — |

| | Antes (Rev F) | Depois (Rev H) |
|---|---|---|
| Massa | 110,07 kg | **126,52 kg** |
| Z do CG | 294,1 mm | **285,9 mm** |
| Margem contra a baseline de 97,8 kg | −12,27 kg | **−28,72 kg** |

**O CG desceu 8,2 mm** — o sistema todo fica abaixo dele — e é parte do que explica o
tombamento melhor. Mas a massa subiu 16,45 kg sobre uma baseline que já estava 12,27 kg
excedida.

### Isto é um problema de projeto, não deste documento

A massa oficial do rover é a **pendência P-02**, e continua aberta: quatro números circulam
(85,04 / 82,49 / 97,8 / 110,07 kg). Este dimensionamento foi feito na mais alta e a
sensibilidade está calculada — e o resultado é tranquilizador: **tombamento e envelope não
mudam com a massa**, porque a rolagem é limitada por curso, não por rigidez. O que muda com
a massa é a pressão do fole, e ela tem margem dos dois lados:

| Massa (kg) | p estática | p projeto | k roda | freq | tombamento | envelope |
|---|---|---|---|---|---|---|
| 85,04 | 1,22 bar | 4,94 bar | 3,76 N/mm | 2,12 Hz | 34,89° | 16,31° |
| 97,80 | 1,40 | 5,68 | 4,07 | 2,05 | 34,89° | 16,31° |
| 110,07 | 1,58 | 6,39 | 4,37 | 2,01 | 34,89° | 16,31° |
| **126,52** | **1,81** | **7,34** | **4,77** | **1,95** | **34,89°** | **16,31°** |
| 130,00 | 1,86 | 7,55 | 4,85 | 1,94 | 34,89° | 16,31° |

Em toda a faixa a pressão estática fica entre 1 e 3 bar (o fole mantém a forma) e a de
projeto fica abaixo de 8. **A suspensão não depende de fechar P-02 para ser cotada.** A
estrutura do rover, sim.

---

## 8. Energia

**10,8 W médios** — compressor 9,0 (180 W a 5 % de ciclo) + solenoides 0,32 + controle 1,5.
Cerca de 0,2 % por hora da bateria de 5.376 Wh (16S LiFePO4, 105 Ah). Não é problema de energia, é de pico: os 180 W do compressor dividem o conversor de 360 W com os sensores e a Jetson (ver `modular.energia`).

Uma subida completa dos quatro cantos consome 1,53 L normais de ar.

### Requisitos do controle de nível

| Requisito | O que significa |
|---|---|
| Quatro circuitos independentes | um solenoide e um sensor de altura por canto |
| Nivelamento | manter a carroceria horizontal; é o que preserva o tombamento |
| Monitoramento de ciclo do compressor | ciclo acima de 15 % = vazamento; é alarme, não tolerância |
| Modo de falha | perda de pressão **desce** para o vão mínimo e trava; nunca sobe sozinho |
| Limite de velocidade por altura | vão acima de 165 mm restringe velocidade |
| Interface com o SaaS | telemetria de altura e pressão por canto — `NOT_IMPLEMENTED` |

---

## 9. O que a suspensão custou em espaço

O compartimento tem **76,8 L livres**, medidos célula por célula numa grade de 8 mm,
descontada toda peça do modelo. Ver `VTX-RV4-ESPACO-G`.

O custo concreto: a bandeja de extremidade **E-02 encolheu**. Ela ia de |Y| 105 a 250 e
colidia frontalmente com o colar do fole (|Y| 159…259). A faixa que sobra, entre a janela da
câmera de raiz e o colar, é de 100 a 152 mm — menos da metade da área original. Isso é
preço de ter suspensão, não erro de desenho.

Quatro passagens Ø102 foram abertas na chapa de fundo, uma por canto, vedadas pelo colar
W-12 + W-13: um canudo fechado no topo pelo berço W-11, com junta nas duas pontas. **É a
única abertura nova no compartimento, e ela não o viola** — mas tem ensaio de estanqueidade
obrigatório antes de montar (folha 35).

---

## 10. Pendências que esta revisão abre ou mantém

| Cód. | Assunto | Grau | Situação |
|---|---|---|---|
| **P-02** | Massa oficial | CRÍTICA | aberta desde a Rev E; dimensionado na massa alta, com sensibilidade calculada |
| **P-20** | Fole: modelo comercial | ALTA | nenhum escolhido; interface desenhada como requisito |
| **P-22** | Fadiga do braço e da chapa W-02 | ALTA | caso 9 do FEA, **novo nesta revisão**; é o caso que justifica o aço |
| **P-21** | Bucha autolubrificante do pivô | MÉDIA | alojamento Ø23 H7 desenhado; modelo a escolher |
| **P-23** | Reação de torque | MÉDIA | calculada e aceitável; depende do torque real do motor. Ensaio V-07 |
| **P-04** | Planicidade da face do motor | MÉDIA | a ElectroCraft não publicou; herdada da Rev F |
| **P-05/P-13** | Fichas técnicas dos componentes | ALTA | 13 de 14 ausentes; bandejas continuam provisões |

---

## 11. O que este documento NÃO autoriza

Nenhuma peça desta revisão deve ser usinada antes de:

1. a **massa oficial** ser fechada (P-02) — ela não muda a suspensão, mas muda a estrutura;
2. o **caso 9 do FEA** rodar (P-22) — é o que confirma a escolha do aço e o
   dimensionamento do braço à fadiga;
3. um **fole** ser escolhido (P-20) — a interface não depende dele, mas o rover depende.

Este pacote é para **cotar**. Nenhum campo de aprovação foi preenchido, e a liberação para
fabricação continua pendente das verificações aplicáveis — ver `VTX-RV4-LIBERACAO-G`.
