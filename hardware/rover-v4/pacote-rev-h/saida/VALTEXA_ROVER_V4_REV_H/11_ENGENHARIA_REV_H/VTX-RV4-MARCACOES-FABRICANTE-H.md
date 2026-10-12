# VTX-RV4 · Marcações do fabricante na folha 02 — conferência

**Documento de entrada:** fotografia da folha **VTX-RV4-CG-E-02**
("ESCOPO E REQUISITOS DE FABRICAÇÃO", rev 0, 18/09/2026, A3), impressa e marcada em
caneta marca-texto amarela pelo fabricante. Recebida em 11/10/2026.

Fecha a pendência **P-08**, que estava aberta por falta deste documento.

> **Situação na Revisão H.** Das quatro sugestões do fabricante, a **2.4** (chapa do
> motor-roda em aço) saiu do papel: a peça é fabricada em aço A36 nesta revisão, e por um
> motivo que a Rev F ainda não tinha — ela passou a ser peça de suspensão e cicla com o
> terreno. As outras três seguem como estavam: 2.1 em aberto (material do quadro), 2.2 já
> implementada desde a Rev E, 2.3 pendente da resposta da ElectroCraft (P-04).

---

## 1 · O que está marcado em amarelo

São **quatro** marcações, e elas **não são** as quatro sugestões do texto. São os pontos
da folha sobre os quais o fabricante tem ressalva, custo ou resposta.

| # | Seção da folha | Trecho marcado | Tratado? |
|---|---|---|---|
| **M-1** | 3 · Materiais | "Enviar certificado de material" | **não estava** — tratado agora, §3 |
| **M-2** | 5 · Tolerâncias | linha "Planicidade da face de montagem · **0,1** · NOVO" | **sim** — sugestão 2.3 |
| **M-3** | 6 · Acabamento | opção **C**: "pintura eletrostática (preta sobre conversão química)" | **não estava** — tratado agora, §4 |
| **M-4** | 8 · Alterações | "Não altere a geometria sem consulta. Alternativas mais baratas: proponha com preço." | é a **instrução da ValTexa** que gerou as 4 sugestões |

### Leitura

**M-4 explica as outras.** A folha 02 pede, por escrito, que o fabricante proponha
alternativas mais baratas com preço. As quatro sugestões que chegaram (aço, parafusos,
planicidade, flange) são a **resposta a esse pedido** — e não reclamações avulsas. Vale
registrar porque muda o tom: o fornecedor fez o que a folha mandou.

**M-2 confirma que a sugestão 2.3 foi lida certo.** O fabricante marcou exatamente a
linha da planicidade de 0,1 mm, e ela é da face de montagem do motor-roda — a peça
**S-02**, como a Rev F identificou. Nenhuma correção a fazer na análise.

**M-1 e M-3 não estavam tratados** na primeira entrega da Rev F, porque não havia como
saber que ele os havia destacado. Estão abaixo.

---

## 2 · O que a folha 02 resolve sozinha: a pendência P-01

A seção **2 · FORA DO FORNECIMENTO** da folha impressa diz, textualmente:

> *Suspensão: não nesta revisão — suportes rígidos*

E o **RESUMO POR GRUPO** da mesma folha lista:

| GRUPO | CONJUNTO | PEÇAS | KG | PROCESSO |
|---|---|---|---|---|
| S | Suportes do motor-roda (4), soldados | **16** | **4,54** | laser + TIG + usinagem |

**Isto fecha P-01**, que estava classificada como "bloqueia tudo". A Rev E declara, no
escopo de fornecimento assinado, que a suspensão não faz parte desta revisão e que os
suportes são rígidos. O estudo de balancim (grupo W) é, portanto, **fase futura** — não
uma arquitetura concorrente em aberto.

**E confirma a correção A-01 da Rev F por número:** a restauração do grupo `S` devolveu
**16 peças e 4,538 kg**, contra **16 peças e 4,54 kg** impressos na folha. A diferença é
de 2 gramas, de arredondamento. A conta voltou a ser a que o fornecedor recebeu.

### Reclassificação de P-01

| Antes | Agora |
|---|---|
| P-01 · Decidir suspensão: rígida ou balancim · **bloqueia tudo** | P-01 · **RESOLVIDA.** A folha 02 fecha a Rev E em suportes rígidos; e no mesmo dia o engenheiro mecânico decidiu a arquitetura definitiva: **suspensão pneumática** (ver `VTX-RV4-SUSPENSAO-AR-F.md`) |

**Atenção para quem for cotar:** com a suspensão pneumática, **S-01 e S-03 saem** — são
as peças que fixam o suporte rígido ao quadro. A folha 02 da Rev F traz o aviso: cotar,
não fabricar antes da liberação. S-02 permanece.

Fica uma pendência menor no lugar: **o estudo W em `modelo.py` não tem desenho, item,
material nem DXF**. Enquanto for fase futura, tudo bem — mas quem abrir o modelo precisa
saber disso, e por isso está no cabeçalho de `conjunto_w()`.

---

## 3 · M-1 · Certificado de material

**O que a folha pede:** "Enviar certificado de material" (seção 3, Materiais).

**O que o fabricante está sinalizando:** certificado tem custo e prazo, e ele quer que
isso esteja na cotação — ou que a ValTexa diga de que tipo precisa, porque há três
níveis muito diferentes de preço.

**Análise.** A folha pede certificado sem dizer qual. Em material metálico, "certificado"
pode ser qualquer um destes, pela EN 10204:

| Tipo | O que é | Custo e prazo |
|---|---|---|
| **2.1** | declaração de conformidade do fornecedor, sem resultado de ensaio | incluso, imediato |
| **2.2** | declaração com resultados de ensaio **não específico** (da corrida, genérico) | baixo, imediato |
| **3.1** | certificado com ensaio **da corrida fornecida**, validado pelo fabricante do material | custo real, prazo de dias |
| **3.2** | 3.1 mais validação por inspetor independente | caro, prazo de semanas |

**Proposta para a Rev F:** especificar **EN 10204 tipo 2.2** para tubo e chapa de
alumínio, e **tipo 3.1 apenas para a chapa S-02** (10 mm, a que recebe o motor-roda).

Justificativa: é a única peça do conjunto cujo material entra diretamente num caminho de
carga com risco de perda total — se a chapa que segura a roda tiver composição errada, o
sintoma aparece em campo, com o rover tombado. Para o resto, 2.2 dá rastreabilidade
suficiente a protótipo, e exigir 3.1 em 45 códigos é pagar certificado de produção numa
unidade.

**Pendência:** confirmar com o engenheiro se 3.1 deve se estender ao tubo do quadro.
Se a alternativa em aço for adotada, **3.1 para o tubo passa a ser recomendável** — aço
de procedência incerta varia muito mais em composição que extrudado de alumínio.

---

## 4 · M-3 · Acabamento: a opção C marcada

**O que a folha oferece** (seção 6 · ACABAMENTO — COTAR AS 3 OPÇÕES):

* **A** — natural, desengraxado
* **B** — anodização (25 µm, fosco)
* **C** — **pintura eletrostática (preta, sobre conversão química)** ← marcada

**O que a marcação significa:** o fabricante indicou a opção C. É a leitura mais provável
de um marca-texto numa lista de três — e é coerente com as outras sugestões dele, porque
**pintura eletrostática é o acabamento do aço**, não o do alumínio.

Ou seja: as quatro sugestões e esta marcação contam a mesma história. Ele está propondo
um conjunto coerente — estrutura de aço, pintada, com tampas aparafusadas de alumínio.

**O que isto resolve na análise da Rev F.** A primeira entrega listava "revestimento
anticorrosivo do aço — sem cotação" como pendência aberta. A marcação a reduz: a folha
02 **já manda cotar as três opções**, e C é justamente o revestimento que a alternativa
em aço exigiria. O custo da pintura, portanto, **já vai estar na cotação** — não é um
custo escondido que apareceria depois.

**O que ainda não resolve.** Conversão química sobre alumínio e sobre aço são processos
diferentes (cromatização/Alodine contra fosfatização), com preços diferentes. Se o
conjunto for híbrido, são **dois** pré-tratamentos na mesma linha, e isso precisa estar
explícito na RFQ ou o fornecedor cota um só.

**Proposta para a Rev F — a seção 6 passa a pedir quatro opções:**

| Opção | Alumínio | Aço | Observação |
|---|---|---|---|
| A | natural, desengraxado | — | só viável em alumínio |
| B | anodização 25 µm fosco | — | melhor resistência em lavoura; não se aplica a aço |
| C | pintura eletrostática sobre conversão química | pintura eletrostática sobre fosfatização | **a marcada** — cotar os dois pré-tratamentos separadamente |
| **D** (nova) | — | zincagem a quente | **atenção:** deforma peça soldada de parede fina. Com 1,5 mm no tubo, risco real de empenar o quadro depois de soldado e usinado. Cotar, mas com a ressalva no RFQ |

**Interação com a tolerância.** Pintura eletrostática deposita camada. Na **face de
montagem do motor-roda** isso importa: a planicidade especificada (0,1 hoje, 0,2
proposto) vale para a superfície **acabada**, não para a usinada. Duas saídas, e a
escolha é de engenharia:

1. **mascarar a face** na pintura e deixá-la em metal nu — exige vedação na montagem do
   motor para não corroer na interface;
2. **usinar depois de pintar** — descarta a pintura justamente onde ela protegeria.

A Rev F propõe a opção 1, com a face mascarada e a instrução no desenho. **Isto é novo e
precisa de decisão** — é o tipo de detalhe que, não resolvido no desenho, vira
improviso no chão de fábrica.

---

## 5 · Divergências novas: o modelo mudou depois da impressão

Comparando o RESUMO POR GRUPO impresso contra o modelo de hoje:

| Grupo | Folha 02 impressa | Modelo hoje | Δ |
|---|---|---|---|
| Q | 52 pç · 5,53 kg | 52 pç · 5,516 kg | −0,014 kg |
| C | 3 pç · 4,27 kg | 3 pç · 4,215 kg | −0,055 kg |
| S | 16 pç · **4,54 kg** | 16 pç · **4,538 kg** | −0,002 kg ✔ |
| G | 48 pç · 2,42 kg | **49 pç** · 2,424 kg | **+1 peça** |
| K | 9 pç · **4,81 kg** | 9 pç · **4,597 kg** | **−0,213 kg** |
| F | **638 pç** | **740 pç** | **+102 itens** |

### D-09 · MÉDIA · Carenagens e fixadores alterados após a emissão

K perdeu 213 g e F ganhou 102 itens. O padrão é consistente com **colunas de furação
acrescentadas às carenagens** depois de a folha ser impressa: mais furo tira massa da
chapa e adiciona fixador. Hoje são 5 colunas × 3 linhas × 4 faces nas laterais, mais
3 × 3 × 2 na frente e atrás — 78 pontos M5, que viram 234 itens de BOM (porca-rebite +
parafuso + arruela).

**Consequência prática:** a folha 02 que o fabricante tem na mão **já não corresponde** ao
modelo. Ele cotou 638 fixadores e 4,81 kg de carenagem; o projeto atual tem 740 e
4,597 kg. A diferença é pequena em dinheiro, mas a folha reemitida precisa sair com os
números novos, ou a cotação chega errada.

**Ação:** registrado. Os números corretos saem automaticamente na reemissão, porque vêm
do modelo.

### Nota sobre G

+1 peça em G sem mudança de massa: provavelmente o coxim antivibração G-08 (0,008 kg)
passou a ser contado na lista de corte. Sem efeito prático.

---

## 6 · Situação das pendências, atualizada

| # | Pendência | Antes | Agora |
|---|---|---|---|
| P-01 | Suspensão rígida × balancim | bloqueia tudo | **RESOLVIDA** pela seção 2 da folha 02 |
| P-08 | Imagem das alterações do fabricante | ausente | **RESOLVIDA** — este documento |
| P-02 | Massa oficial (4 números) | aberta | **aberta — agora é a nº 1** |
| P-03 | FEA, 8 casos da folha 25 | aberta | aberta |
| P-04 | Planicidade e torque do MPW86 | aberta | aberta — confirmada como pertinente por M-2 |
| P-05 | Consumo de 7 componentes | aberta | aberta |
| P-06 | Desenho dimensional da OAK-D | aberta | aberta |
| P-07 | Cotação | aberta | **reduzida** — a pintura já está na folha como opção a cotar (M-3) |
| P-09 | Interface do ZLTECH | aberta | aberta |
| **P-10** | Nível de certificado de material por peça | — | **nova** (M-1) |
| **P-11** | Mascarar ou não a face de montagem na pintura | — | **nova** (M-3) |
