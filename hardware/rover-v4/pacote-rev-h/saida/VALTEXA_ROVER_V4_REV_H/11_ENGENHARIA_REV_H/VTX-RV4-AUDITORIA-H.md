# VTX-RV4 · Auditoria dos documentos — Revisões F, G e H

**Data:** 11/10/2026 · **Base auditada:** Rev E (21/09/2026) e Rev F (11/10/2026)
**Condição:** EMITIDO PARA COTAÇÃO E VALIDAÇÃO — NÃO LIBERADO PARA FABRICAÇÃO

---

## 0.-1 · Auditoria de 12/10/2026 — o que o V4 de 11/10 trazia errado

Disparada por três observações: *"o mastro no desenho técnico está igual ao antigo"*, *"nem tem o espaço para a
antena RTK"* e um esboço de como a câmera e a térmica removível deveriam ser. A varredura que se seguiu achou
bem mais do que o mastro — e inclui erros **meus**, do relatório de 11/10, que precisam ficar registrados.

### Erros do relatório de 11/10

| # | O que o relatório disse | O que era verdade |
|---|---|---|
| 1 | "Mastro Ø32×2: 9,40 Hz, aprovado" | Valia para **3 câmeras por mastro**. Com as térmicas removíveis e a antena que o projeto descreve, o Ø32×2 dá **6,97 Hz** e reprova os 7,5 Hz. O adotado agora é **Ø32×3: 7,88 Hz** |
| 2 | "razão 1,67 contra a excitação" | O próprio `mastro.py` já imprimia **"INSUFICIENTE — precisa enrijecer"** (critério 2,0), e o documento não dizia. Com o mastro cheio a razão é **1,41**, e a margem só fecha abaixo de **0,98 m/s**. Continua aberta (P-39) |
| 3 | "pacote de 91 arquivos, V4 completo" | Sete documentos do pacote (técnico, fabricação, RFQ, pendências, auditoria, conceito, fornecedores) e a BOM eram **texto do V3**: suportes rígidos, mastro Ø25×2, placa M-20, carenagem N-09, "8 câmeras", "27 folhas" |
| 4 | "40 folhas, 0 falhas de geração" | "0 falhas" era de **geração**, não de legibilidade. Medido no navegador, havia **343 defeitos em 16 folhas** |
| 5 | "tubo Ø32×2 desenhado" | As folhas 17 e 18 e o catálogo (M-01, M-10, M-11, M-12) ainda diziam Ø34×4,5, Ø25×2 e Ø29 |

### O que a varredura achou

| # | Achado | Onde | Correção |
|---|---|---|---|
| A1 | `num()` apagava zero final: `num(220, 0)` dava "22" | `desenho.py` | Corrigido. Afetou **uma** cota nas folhas antigas — "286 N dos **31** N" na folha 07 (era 310) — e a folha 18 nova |
| A2 | Bitola 470 e "408 ± 1" digitados nas folhas 02, 03 e 05; o desenho já é 530 | `folhas.py` | Passam a vir de `BITOLA` e `Y_FACE`: 530 e 468 |
| A3 | Folha 02 (escopo) era a da Rev F: "suportes rígidos", grupo S, S-02 | `folhas.py` | Reescrita para o V4 |
| A4 | 343 defeitos de layout: texto dentro do carimbo (13, 30, 31, 32, 36, 37, 39, 40), rótulos sobre cotas, linhas cortando texto, selo de revisão estourando em **todas** as folhas, gráfico da folha 36 **preto** | várias | Novo `verifica_layout.py`, que **mede** cada folha no navegador. Hoje: 42 folhas, 0 defeitos |
| A5 | Cobertura vertical das OAK-D calculada com 110° (premissa do V3); o V4 usa 80° | folha 18 | Com 80° os três andares **não se sobrepõem** (faixas de ~80 mm sem cobertura). Decisão de projeto, não de desenho (P-35) |
| A6 | Folhas 23, 24, 26, 27 e 29 com S-01/S-02/S-03, "protótipo rígido", "Rev F" | `folhas_b.py` | Atualizadas; o plano de validação ganhou os ensaios V-10 a V-17 |
| A7 | Passa-cabo F-46 era Ø32 para uma luva Ø42 | `modelo.py` | F-59 (Ø20, luva) e F-60 (Ø12, tubo) |
| A8 | O berço do satélite T-07 tinha furos; a tampa K-05 embaixo dele **não tinha nenhum** | `modelo.py` | Acrescentados à K-05, ao DXF e à lista (F-58) |
| A9 | Câmeras C7 e C8 sob o chassi, sem passagem de cabo para o compartimento | — | **Pendência nova**, não resolvida |
| A10 | Totais da BOM de compras estavam congelados (a 9ª OAK-D e o tubo novo não entravam) | `bom_precos.py` | Calculados das linhas; linhas "a cotar" ficam fora do total e o total diz isso |
| A11 | 4 de 12 scripts de cálculo falhavam no console do Windows (`UnicodeEncodeError`) | `revisao-h/*.py` | `stdout` reconfigurado em UTF-8 em todos |
| A12 | `gerar_pacote.py` tinha uma cópia própria da conferência de interferência, com exceções do V3 (M-20, N-09) | `gerar_pacote.py` | Usa a de `espaco.py`, que cobre o mastro completo: 276 peças, 17 encaixes previstos, 0 defeitos |

### O que continua sem validação física

Nenhum dos ensaios V-07, V-09 e V-10 a V-17 foi feito. Nenhum caso de FEA foi rodado. Os números do mastro
(7,88 Hz, razão 1,41, massa máxima de antena 0,42 kg), da repetibilidade (0,048°) e da suspensão são **cálculo**
sobre massas **estimadas**: OAK-D 0,25 kg, térmica 0,20 kg e antena 0,30 kg não vêm de ficha técnica. O mastro
passa os 7,5 Hz por 5 %, e com a OAK-D em 0,50 kg deixa de passar.

---

## 0.0 · O que a Revisão H encontrou na Revisão F

A Rev F corrigiu o que a Rev E tinha de errado. A Rev H, ao implementar a suspensão, achou
quatro coisas erradas **na própria Rev F**. Registro primeiro, porque é o que importa para
quem for ler as duas:

| Cód. | Achado | Consequência |
|---|---|---|
| **G-01** | `ALTURA_AJUSTAVEL_MM = 50` era **incompatível com a geometria** do balancim que a Rev F propunha. Com o pivô do balancim fixo no chassi, mudar a pressão dos foles gira os dois balancins no mesmo sentido — isso é arfagem, não altura. | O principal ganho de produto que a Rev F atribuía à suspensão a ar não existia naquela arquitetura. A Rev H troca de arquitetura e o ganho passa a existir: vão livre 150 → 180 mm. |
| **G-02** | A perda de envelope por rolagem macia estava **superestimada**. A Rev F calculava a rolagem como se o fole fosse livre até o limite geométrico (8,5°), ignorando que o **fim de curso** a limita muito antes. | Era esse número inflado que condenava a suspensão independente. Com o batente no cálculo, a rolagem máxima é 5,39°, e a arquitetura deixa de ser inviável. |
| **G-03** | A **área do fole foi dimensionada pela pressão estática**, não pela de projeto. Com os 2003 mm² da primeira tentativa, a estática ficava confortável em 3,13 bar e a de projeto ia a **12,69 bar** — acima de qualquer fole industrial pequeno. | Área corrigida para 3421 mm². É o caso de carga raro que dimensiona o componente, não o do dia a dia. |
| **G-04** | A reação de torque do motor-roda estava calculada **ignorando a reação do estator**. Só a força de tração entrava na conta, o que superestima o efeito em 2,1×. | Corrigido: as duas se cancelam parcialmente e a alavanca efetiva é `Z_pivô − raio da roda` = 90 mm. Com o pivô na cota do eixo da roda o efeito seria zero — o vão livre de 150 mm é que proíbe. |

E dois achados de geometria, que a conferência automática de interferência da Rev H
produziu e que não existiam como verificação em nenhuma revisão anterior:

| Cód. | Achado | Correção |
|---|---|---|
| **G-05** | A bandeja de extremidade **E-02 colidia** com o colar do fole: ia de \|Y\| 105 a 250, e o colar ocupa 159…259. | Bandeja reduzida à faixa 100…152, entre a janela da câmera de raiz e o colar. Perda real de área, contabilizada. |
| **G-06** | O **alojamento da bucha do pivô encostava nas orelhas** da torre (44 mm de comprimento num vão de 42) e a **flange do colar invadia o berço do pivô**. | Bucha para 38 mm, com 2 mm de folga de giro por lado; flange cortada reta em \|X\| 470. |

Os seis achados têm o mesmo padrão: **ninguém tinha medido**. A Rev H acrescentou três
conferências automáticas que agora rodam a cada geração — interferência par a par
(`espaco.py`), folgas de suspensão (`suspensao.folgas`) e roteiro contra modelo
(`usinagem.confere`). Nenhuma delas existia antes.

---

## 0 · O achado que reordena tudo

**O CAD não é PDF.** `chassi-gaiola/modelo.py` é um modelo paramétrico de 1 200 linhas, em
mm, no referencial ISO 8855 da baseline, e dele saem as folhas do caderno, os DXF, as listas de
corte, as massas e os STL. O pedido de revisão previa o cenário "só há PDFs, produza
especificações de alteração"; não é o caso. **Geometria se altera aqui e o caderno
inteiro se refaz.**

E o segundo achado, que vem junto: **nenhum dos dois pacotes gerava.**

| Comando | Resultado antes da Rev F |
|---|---|
| `chassi-gaiola/gerar.py` | `KeyError: 'S'` na folha 02 |
| `pacote-rev-e/dados.itens()` | `KeyError: 'W-01'` |

Os PDFs em `saida/` são de 21/09. O código estava posterior a eles e quebrado nas duas
pontas. Qualquer alteração de engenharia estava bloqueada até isso ser resolvido — foi o
primeiro trabalho da Rev F, e está feito (ver D-01).

---

## 1 · Inventário dos documentos de entrada

| Arquivo | Rev | Conteúdo | Editável? |
|---|---|---|---|
| `modelo.py` | — | **toda a geometria**, materiais, listas de corte, massas, fixadores | **Sim — é a fonte** |
| `folhas.py` | — | folhas 01–16 (Parte A) + motor de layout | Sim |
| `folhas_b.py` | — | folhas 17–27 (Partes B e C) | Sim |
| `desenho.py` | — | projeções 1º diedro, cortes, cotas, carimbo, GD&T, solda | Sim |
| `VTX-RV4-CG-E-A.pdf` | E | Parte A (01–16) — chassi e gaiola, o que vai cotar | Gerado |
| `VTX-RV4-CG-E-B.pdf` | E | Parte B (17–22) — mastro, câmeras, bateria, eletrônica, E-STOP | Gerado |
| `VTX-RV4-CG-E-C.pdf` | E | Parte C (23–27) — pendências, massa, solda/FEA, validação | Gerado |
| `saida/dxf/*.dxf` | 0 | 26 peças planas 1:1 para laser | Gerado |
| `04_CAD/STL/*.stl` | E | 3 malhas (conjunto, gaiola, quadro) | Gerado |
| `pacote-rev-e/*.py` | — | BOM, custos, processos, RFQ, fornecedores, pendências | Sim |
| `VALTEXA-ROVER-V3-BOM-Links-Precos.xlsx` | — | **preços reais**, recebidos 21/09/2026 | Fonte externa |
| `05_BOM/*.csv/.xlsx` | E | BOM mecânica | Gerado |
| `10_CUSTOS/*.xlsx` | E | estrutura de custo | Gerado |

### Não localizados no repositório

| Procurado | Situação |
|---|---|
| **Imagem das alterações do fabricante** | **ausente.** As quatro sugestões foram tomadas do texto do pedido de revisão, não de documento do fabricante. Se houver imagem, anexá-la e reconferir. |
| `VTX-RV4-BASELINE-E` | **ausente como arquivo.** Existe por referência: `modelo.py` cita "Rev E, 18/09/2026", e as folhas comparam contra a tabela 5.1 dela (`BASELINE_MASSAS`, `TABELA_51`, `M_NOM`, `M_MIN`, `ZCG_NOM`). O caderno é auditável; a baseline, não. |
| Arquivos CAD de sistema (STEP, SolidWorks, Fusion) | **não existem.** O paramétrico é o CAD. STL são saída, não fonte. |
| Relatório de FEA | **não existe.** A folha 25 **especifica** os 8 casos de carga, condições de contorno, malha e critérios de aceite — mas nenhum foi rodado. |
| Datasheet do ElectroCraft MPW86 | não está no repositório; valores transcritos em `modelo.py` com marca `FONTE · datasheet 011121`. |
| Desenho dimensional da OAK-D Pro W PoE | **ausente** — já é a pendência 10 do caderno. Bloqueia fixar os envelopes dos módulos de sensor. |

---

## 2 · Divergências

Numeradas para rastreio. **D-01 a D-05 são novas desta auditoria**; D-06 e D-07 já
estavam registradas pelo próprio caderno e são repetidas aqui por completude — o crédito
é do caderno, não desta revisão.

### D-01 · CRÍTICA · Duas arquiteturas de suspensão coexistindo

Entre a emissão da Rev E e hoje, um estudo de **suspensão de balancim longitudinal**
(grupo `W`) entrou em `modelo.py` e ficou pela metade:

| | Grupo `S` — suporte rígido | Grupo `W` — balancim |
|---|---|---|
| Geometria no modelo | sim | sim |
| Desenhado em folha | **sim** (folha do suporte, com a planicidade 0,1) | **não, em nenhuma** |
| Entrada em `ITENS` (nome, material) | sim | **não** |
| Em `GRUPOS` | **tinha sido removido** | sim |
| Em `conjunto_a()` (massa, BOM, DXF) | **tinha sido removido** | sim |
| DXF | S-01, S-02, S-03 | **nenhum** |
| Cotado no pacote Rev E | sim (`metricas_solda`: 4 conjuntos) | não |
| Código de peça (`dados.SUB`) | `SUPORTE` | **não existe** |

**São alternativas, não complementares.** `W-02` ocupa exatamente o espaço de `S-02`
(X 288…412, Y 194…204), terminando em Z 180 — onde pega o balancim — em vez de Z 242,
onde `S-02` pega no quadro. Somar os dois contaria a chapa de montagem do motor duas
vezes.

**Ação da Rev F:** `conjunto_a()` voltou a chamar `suportes()`, `GRUPOS` recuperou `'S'`,
e o balancim passou a viver em `conjunto_w()`, íntegro e fora do conjunto cotado. Isso
devolve a regenerabilidade **sem escolher a arquitetura de suspensão** — a escolha é do
engenheiro mecânico, e as quatro sugestões do fabricante se referem ao desenho com `S`,
que é o que ele recebeu.

**RESOLVIDA em 11/10/2026, em duas etapas:**

1. A folha 02 impressa (recebida do fabricante) diz, no escopo: *"Suspensão: não nesta
   revisão — suportes rígidos"*, e lista `S` com 16 peças e 4,54 kg. A Rev E cotada é a
   rígida, e a restauração do grupo `S` devolveu 4,538 kg — dois gramas de arredondamento.
2. **O engenheiro mecânico decidiu, no mesmo dia: a suspensão é PNEUMÁTICA.** Ver
   `VTX-RV4-SUSPENSAO-AR-F.md`. O balancim do estudo W é aproveitado como estrutura que
   carrega os foles; os foles e seus suportes ainda não estão desenhados, e por isso o
   grupo continua fora de `conjunto_a()`.

**Consequência que afeta a cotação:** `S-01` (4 un) e `S-03` (8 un) existem para fixar o
suporte rígido ao quadro e **saem com a suspensão pneumática**. A folha 02 da Rev F foi
atualizada: cotar, **não fabricar** antes da liberação. `S-02` permanece — é a interface
do motor-roda, que não muda.

### D-02 · CRÍTICA · Massa dos 4 suportes do motor-roda fora da conta

Consequência de D-01, mas vale número próprio: enquanto `S` estava fora de
`conjunto_a()`, os **4,538 kg** dos suportes (S-01, S-02, S-03 × 4 conjuntos) não entravam
em `resumo_massas()`, `comparacao_baseline()` nem `envelope()`.

São **19 % da massa do conjunto A**, e com CG a Z 202 mm — abaixo dos 294 mm do conjunto.
O número publicado estava errado **nos dois sentidos**: massa de menos e CG de mais.

**Ação:** corrigido com D-01. O conjunto A passa de 24,076 kg (sem S, com W) a
**21,767 kg** (com S, sem W).

### D-03 · ALTA · A margem de massa da baseline está esgotada

Com a massa recalculada e os suportes dentro:

| | kg |
|---|---|
| Baseline, massa mínima declarada | 85,04 |
| Baseline, massa nominal | 97,80 |
| Delta do chassi real sobre a baseline | **+12,267** |
| Massa nominal recalculada | **110,07** |
| **Margem restante** | **0,49** |

**Sobram 490 gramas.** Isso não é consequência de nenhuma sugestão do fabricante — é o
estado do projeto em alumínio, hoje. E é o número que decide as sugestões 2.1 e 2.4, as
duas que pedem aço.

### D-04 · MÉDIA · `Z_cg` publicado não corresponde ao conjunto

`ZCG_NOM = 297,0 mm` vem da baseline. O conjunto recalculado dá **294,1 mm**. Diferença
pequena (2,9 mm) e sem efeito prático no tombamento (38,4° → 38,6°), mas o número
publicado deve passar a ser o calculado, com a fonte declarada.

### D-05 · MÉDIA · Erro de massa linear inflando o custo da estrutura

`custos.py` deduzia o R$/kg de referência de **0,218 kg/m** para o tubo Al 30×30×2. A
geometria não permite: (30² − 26²) mm² × 2,70 g/cm³ = **0,605 kg/m**.

O erro inflava o R$/kg em **2,78×** — R$ 38,23 em vez de R$ 13,78 — e com ele o preço de
referência de todo item precificado por massa. O custo da estrutura estava
**sobrestimado**.

**Ação:** corrigido, com a massa linear derivada da seção em vez de digitada.

### D-06 · já registrada pelo caderno · Massa oficial 85,04 × 82,49 kg

A baseline declara 85,04 kg de massa mínima; a tabela 5.1 dela soma 82,49 kg. **Faltam
2,55 kg não localizados.** Está na pendência 9 do caderno e nas folhas 24 e 27 — o
caderno é explícito sobre a divergência e parte da soma verificável. Repetido aqui porque
agora há um terceiro número (110,07 kg nominal recalculado) e um quarto (137,5 kg no caso
de carga 1 do FEA, que é massa operacional, não mínima). **Quatro números de massa em
circulação, e nenhum deles é oficial.**

### D-07 · já registrada pelo caderno · 6061-T6 soldado vale 110 MPa, não 240

A folha 25 declara a perda de ~40 % na zona afetada pelo calor e adota a condição "como
soldado" (≈110 MPa) para o protótipo, registrando que o ponto mais solicitado fica em
45 MPa. **O caderno está certo e foi honesto.** Consta aqui porque é o número que inverte
a leitura da sugestão do aço — ver o relatório, sugestão 2.1.

### D-08 · BAIXA · Referência a folha inexistente — **CORRIGIDA**

`modelo.py` citava "a arquitetura escolhida na folha 28". O caderno tem **27 folhas**
(16 + 11). A nota do balancim apontava para o vazio.

**Ação:** a nota foi reescrita na Rev F com a decisão da suspensão pneumática, e a
referência à folha 28 removida.

### D-09 · MÉDIA · Modelo alterado entre a impressão e o código — **RESOLVIDA**

O RESUMO POR GRUPO da folha 02 **impressa** não corresponde ao modelo:

| Grupo | Folha impressa | Modelo | Δ |
|---|---|---|---|
| K · carenagens | 4,81 kg | 4,597 kg | **−0,213 kg** |
| F · fixadores | 638 itens | 740 itens | **+102** |

As constantes de furação (`X_FUROS_LAT`, `Z_LINHAS_LAT`, `Y_FUROS_FR`) são **idênticas**
entre o modelo arquivado e o atual — logo a alteração é anterior a esta revisão,
ocorrida entre a impressão de 18/09 e o código de 21/09. O padrão é consistente com
colunas de furação acrescentadas às carenagens: mais furo tira massa da chapa e
acrescenta fixador.

**Ação:** nenhuma correção era necessária no modelo — a geometria está certa, o PDF é que
estava velho. A Rev F reemitida já sai com **740 e 4,60 kg**, verificado na tabela
renderizada. **A folha que o fabricante tem na mão está superada:** ele cotou 638
fixadores.

---

## 3 · Inconsistências menores, sem ação nesta revisão

| Item | Observação |
|---|---|
| `MPW_FOLGA = 5,0` | marcado "leitura do desenho, A VALIDAR" — continua a validar |
| `ZLTECH` sem interface | `faltam_do_motor('ZLTECH')` lista 9 campos não publicados; o suporte não pode ser desenhado para ele. A BOM, no entanto, **recomenda o ZLTECH** — divergência já registrada como CRÍTICA no `bom_precos.DIVERGENCIAS` |
| `MASSA_FIXADORES = 1,4 kg` | estimativa, não somada item a item; com 740 itens de fixador na lista, vale derivar |
| IP do ZLTECH | "IP65 no título e IP54 na tabela da mesma página" — a confirmar, já registrado |

---

## 4 · O que foi efetivamente alterado nesta auditoria

| Arquivo | Alteração | Efeito verificado |
|---|---|---|
| `chassi-gaiola/modelo.py` | `conjunto_a()` chama `suportes()`; novo `conjunto_w()`; `GRUPOS['S']` restaurado | `gerar.py` volta a rodar; 26 DXF **bit-a-bit idênticos** à Rev E |
| `pacote-rev-e/custos.py` | massa linear do tubo derivada da seção | `dados.itens()` volta a rodar: 45 códigos, 9 grupos |
| `arquivo-rev-e/` | Rev E congelada (21 MB: PDFs, DXF, BOM, STL, código como recebido) | — |

**Geometria não mudou.** Os 26 DXF saem idênticos byte a byte aos da Rev E, o que é a
prova de que a correção foi de contabilidade e de dicionário, não de desenho.

### Alterações de 11/10/2026 (tarde) — após a folha marcada e a decisão da suspensão

| Arquivo | Alteração |
|---|---|
| `folhas.py` | carimbo sobe para **Rev F**, doc `VTX-RV4-CG-H`, data 11/10/2026 |
| `folhas.py` · folha 02 | certificado por nível EN 10204; acabamento de 3 para 4 opções com nota de mascaramento da face; escopo com a suspensão pneumática e o aviso sobre S-01/S-03 |
| `folhas.py` · folha 13 | tabela das 5 classes de união |
| `modelo.py` | nota da suspensão reescrita com a decisão pneumática; referência à folha 28 removida |
| `revisao-f/suspensao_ar.py` | **novo** — dimensionamento, massa, CG, energia e rolagem |
| `revisao-f/materiais.py` | `comparacao_hibrida()` — alternativa C peça a peça |

**Emitido:** `VTX-RV4-CG-H.pdf` (3.036 KB), `-A` (2.050), `-B` (815), `-C` (349), 27
folhas, e os 26 DXF **ainda idênticos** à Rev E.

---

## 5 · Como regenerar

```
cd chassi-gaiola && python gerar.py          # HTML + 26 DXF + 4 PDFs
cd pacote-rev-e  && python gerar_pacote.py   # pacote de cotação completo
cd revisao-f     && python materiais.py      # comparação de materiais
                    python sugestoes.py      # análises 2.2, 2.3, 2.4
                    python sensores.py       # configurações e orçamento energético
```
