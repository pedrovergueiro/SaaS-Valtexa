# VTX-RV3 · Liberação para fabricação — Revisão F

**Aprovação:** engenheiro da UNIFEI, informada em 11/10/2026
**Escopo decidido:** **Parte A completa** — grupos Q, C, S (incluindo S-01 e S-03), G, K, M, F
**Situação do documento:** mecanismo pronto · **selo ainda não aplicado**

---

## 1 · O que falta para o selo mudar

Dois campos, e nenhum deles eu posso preencher:

| Campo | Para quê |
|---|---|
| **Nome do engenheiro** | vai em `VERIFICADO · ENG. MECÂNICO / CREA`, no carimbo das 27 folhas |
| **CREA** | o registro profissional é o que dá valor à assinatura |

Com os dois, a liberação é um comando:

```python
# em chassi-gaiola/folhas.py
LIBERACAO = dict(nome='...', crea='...', data='11/10/2026',
                 escopo='Parte A completa (grupos Q, C, S, G, K, M, F)')
```

e `python gerar.py` reemite as 27 folhas com **LIBERADO PARA FABRICAÇÃO** no selo e os
campos preenchidos no carimbo.

**Por que não preenchi com um nome genérico:** o pedido de revisão determina, textualmente,
*"não invente uma assinatura ou uma aprovação profissional"* e *"não altere os campos de
aprovação para indicar uma liberação inexistente"*. Um carimbo com nome inventado num
desenho que vai para o chão de fábrica não é formalidade — é o documento que responde
"quem respondeu por isto" quando alguma coisa falha.

O mecanismo tem guarda: `LIBERACAO` incompleta levanta erro, e `LIBERACAO = None` mantém
o selo de não liberado nas 27 folhas. **Esquecer de informar nunca libera por omissão.**

---

## 2 · O que o escopo escolhido significa

**O protótipo é de suportes rígidos.** As 12 peças S-01 (4) e S-03 (8) entram na
fabricação.

Isso **não cancela a suspensão pneumática** — põe a máquina andando antes de ela existir
em desenho. Quando a pneumática entrar, essas 12 peças são substituídas; S-02 permanece,
porque é a interface do motor-roda e não muda.

A folha 02 foi reescrita para dizer exatamente isso, no lugar do aviso anterior de "não
fabricar".

---

## 3 · O que a assinatura está assumindo

Esta é a parte que o engenheiro precisa ler antes de assinar. Nenhum destes itens impede
cortar metal; todos ficam sob a responsabilidade de quem libera.

### 3.1 · Nenhum FEA foi rodado

A folha 25 especifica **8 casos de carga** com condições de contorno, malha e critérios
de aceite — e nenhum foi executado. A folha 15 cobre, à mão, longarinas, suporte do
motor-roda, parafusos M8, chapa de fundo, nervura, torque e tombamento, com fator
dinâmico 3. O próprio caderno diz que isso *"serve para dimensionar, não para liberar"*.

| Caso | O que ficaria sem verificação |
|---|---|
| 1 · Estático 1 g | flecha de referência do quadro (critério L/500) |
| 2 · Vertical 3 g | σ < 110 MPa na ZTA em impacto de buraco |
| 3 · Lateral 2 g | escorregamento contra obstáculo |
| 4 · **Torção** | rigidez torcional — **o quadro não tem diagonais**; a rigidez vem dos dois anéis, dos 16 montantes e da chapa de fundo como diafragma |
| 5 · Tração e frenagem | σ nos suportes S, 35 N·m por roda |
| 6 · Mastro | 1ª frequência ≥ 7,5 Hz, com 8 câmeras a até 1,78 m |
| 7 · Bateria | 36,5 kg × 3 g na amarração |
| 8 · Içamento | pontos de levantamento, não definidos |

O caso 4 é o que eu destacaria: a folha 25 lista três alternativas de reforço (diagonais,
chapa de fundo 2→3 mm, vão entre anéis 30→60) **se o FEA mostrar que falta rigidez** — e
sem o FEA não se sabe se falta.

### 3.2 · Material do quadro em aberto, e fabricar fecha a questão

A sugestão 2.1 do fabricante (aço 1020 25×25×1,5) está calculada: **132 % da rigidez,
101 % da resistência soldada, +4,49 kg, economia de R$ 27 a 47 em matéria-prima**.

Fabricar o quadro em alumínio agora **encerra a discussão por fato consumado**. Pode ser
exatamente a intenção — protótipo em alumínio, série em aço —, mas é decisão, e fica
registrada aqui como tal.

### 3.3 · Planicidade da S-02 sem confirmação do fabricante do motor

O desenho especifica **0,1 mm**; a Rev F propõe **0,2 mm**, pelo argumento de que a
planicidade está 2,3× mais apertada que a perpendicularidade na mesma face. **O datasheet
do MPW86 não publica a planicidade admitida pela contrapeça** (P-04).

Liberando hoje, fabrica-se com **0,1 mm** — o valor atual do desenho. É o lado seguro, e
custa alívio de tensões antes do faceamento e inspeção individual nas 4 peças.

### 3.4 · Massa 12 % acima da baseline

| | kg |
|---|---|
| Baseline declarada | 97,80 |
| **Parte A como será fabricada** | **110,07** |
| Diferença | **+12,27** |

Quatro números de massa circulam no projeto (85,04 · 82,49 · 110,07 · 122,79) e nenhum é
oficial (P-02). O rover vai pesar o que pesa; o que não se pode é afirmar que cumpre a
baseline.

---

## 4 · Prontidão, grupo por grupo

| Grupo | Peças | kg | Estado |
|---|---|---|---|
| **G** gaiola | 49 | 2,42 | pronto, **sem ressalva** |
| **K** carenagens e tampas | 9 | 4,60 | pronto, **sem ressalva** |
| **F** fixadores | 740 | ≈1,4 | pronto, **sem ressalva** |
| **Q** quadro | 52 | 5,52 | desenhado · material em aberto · FEA 1-4, 8 |
| **C** chapa de fundo | 3 | 4,21 | desenhado · FEA caso 4 (diafragma) |
| **S-02** chapa do motor | 4 | 1,89 | desenhado · P-04 planicidade · material · fadiga |
| **S-01/S-03** | 12 | 2,65 | desenhado · **substituídas quando a pneumática entrar** |
| **M** base dos mastros | 4 | 0,48 | desenhado · FEA caso 6 |
| W suspensão pneumática | — | — | **sem desenho — fora desta liberação** |

Reproduzir: `python revisao-f/liberacao.py`

---

## 5 · O que não é liberado, e não poderia ser

**A suspensão pneumática não tem desenho.** Não há geometria de fole, de suporte W-18 nem
de roteamento pneumático; nenhum dos 9 componentes tem modelo comercial escolhido, e as
massas são de faixa de catálogo. Não é questão de aprovação — não há o que fabricar.

E há um ponto que a liberação do chassi rígido **não resolve e não deve esconder**: os 8
casos do FEA foram escritos para suspensão rígida. Quando a pneumática entrar, o apoio
deixa de ser nos 4 furos Ø88 e passa a ser a rigidez do fole — **os casos precisam ser
reescritos** (P-12), não reaproveitados.

---

## 6 · Depois de aplicar o selo

| Ação | Quando |
|---|---|
| Reemitir as 27 folhas e os 4 PDFs | imediato, `python gerar.py` |
| Regerar o pacote de cotação | `python gerar_pacote.py` |
| Enviar DXF + PDF ao fornecedor | os 26 DXF estão prontos e inalterados desde a Rev E |
| Registrar a decisão de acabamento | 4 opções na folha 02; a C foi a marcada pelo fabricante |
| Fechar o nível de certificado | 3.1 para S-02, 2.2 no resto (proposta da Rev F) |
