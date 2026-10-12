# VTX-RV4 · Registro de alterações das Revisões F, G e H

**Data:** 11/10/2026 · **Anteriores:** Rev E (21/09/2026) e Rev F (11/10/2026)
**Arquivo das anteriores:** `../versao-antiga/rev-e/` e `../versao-antiga/rev-f/`
**Condição:** EMITIDO PARA COTAÇÃO E VALIDAÇÃO — NÃO LIBERADO PARA FABRICAÇÃO
**Liberação aprovada em 11/10/2026** (engenheiro da UNIFEI), escopo **Parte A completa** —
selo **ainda não aplicado**: faltam nome e CREA. Ver `VTX-RV4-LIBERACAO-H.md`.

Nenhum campo de aprovação foi preenchido. Nenhuma assinatura foi criada. O mecanismo de
liberação está pronto e com guarda: `LIBERACAO = None` mantém as 42 folhas em "não
liberado", e `LIBERACAO` incompleta levanta erro — esquecer de informar nunca libera por
omissão.

> **Atenção ao escopo da liberação.** A aprovação de 11/10 cobria a **Parte A da Rev F**,
> cuja suspensão era o suporte rígido (grupo S). A Rev H **retirou o grupo S** e pôs a
> suspensão pneumática no lugar. O escopo aprovado não cobre mais o que está desenhado —
> a liberação precisa ser reemitida sobre a Rev H. Ver `VTX-RV4-LIBERACAO-H.md`, §0.

---

## 00 · Correção de 12/10/2026 — o mastro completo, a antena, a térmica removível e os cabos

**Pedido:** o mastro nos desenhos técnicos estava igual ao do V3; não havia espaço para a antena RTK; e um esboço
de como a OAK-D (fixa e calibrada) e a câmera térmica (removível) deveriam ser. A auditoria que veio junto está em
`VTX-RV4-AUDITORIA-H.md`, §0.-1 — inclusive os erros do relatório de 11/10.

| Área | Antes (11/10) | Agora (12/10) | Por quê |
|---|---|---|---|
| **Mastro** | Ø32 × 2, dimensionado para 3 OAK-D | **Ø32 × 3**, dimensionado para 3 OAK-D + 2 térmicas + antena | com a carga completa o Ø32×2 dá 6,97 Hz (< 7,5); o Ø32×3, 7,88 Hz. O Ø externo fica: a luva não pode crescer |
| **Posições térmicas** | nenhuma | **H1–H4**, 2 por mastro, nominais em Z 725 e 1.270 | o esboço intercala as térmicas entre as OAK-D |
| **Módulo térmico removível** | só o adaptador T-04 como requisito | **T-04 + 4 parafusos M5 imperdíveis de aperto manual** sobre os mesmos pinos; folha 41 | removível à mão, volta à mesma pose; repetibilidade com aperto manual é o ensaio V-16 |
| **Antena GNSS** | só N-01, na tampa | **N-01 e T-10** (adaptador no topo do mastro, Ø26×60) | o esboço põe a antena no topo; a escolha é a pendência P-36 |
| **Prato T-02** | 4 furos Ø5,5 | 4 furos **M5 roscados** | é onde o parafuso do adaptador rosqueia |
| **Cabos** | só texto | `roteamento.py`, folha 42, `VTX-RV4-CABOS-H` | interligação funcional, passagens, comprimentos ESTIMADOS |
| **Caderno** | 40 folhas | **42** (acrescentadas 41 e 42) | |

**O mastro, em números** (`python revisao-h/mastro.py`): 1ª frequência do mastro cheio **7,88 Hz** contra 7,5 de
requisito (5 % de folga); razão contra o terreno **1,41** contra 2,0 de margem — **não fecha** a 1,4 m/s, só abaixo
de 0,98 m/s; massa máxima de antena para manter 7,5 Hz: **0,42 kg**; cabos no furo do tubo: 40 % (limite 40 %, com
cabo estimado em Ø7).

**O que isto NÃO é:** validação. É cálculo sobre massas estimadas. O ensaio V-12 (espectro do mastro em marcha) e a
medição das massas reais é que dizem se o mastro serve.

**Pendências novas:** P-36 antena (topo do mastro ou tampa), P-37 modelo e massa da antena, P-38 a térmica cabe nos
72×64×46 deixando os parafusos livres, P-39 margem contra o terreno, P-40 cabos no tubo, P-41 perfil T 30×30 do esboço
× tubo redondo. Novos ensaios: V-16 e V-17.

---

## 0 · ValTexa Rover **V4** — o que mudou em relação ao V3

O número de versão mudou porque a arquitetura de sensores mudou. **O chassi, a suspensão,
a gaiola e as carenagens são os mesmos da Rev G do V3, sem uma cota alterada** — e é por
isso que a letra de revisão continua em H em vez de recomeçar em A: o registro de
engenharia é contínuo. O V3 inteiro está preservado em `../../rover-v3`.

| Área | V3 (Rev G) | V4 (Rev H) | Por quê |
|---|---|---|---|
| **Interface de sensores** | chapa M-20, furação fixa em cota fixa, padrão da câmera marcado "a validar" no código | **grupo T — interface VMS-60**: braçadeira deslizante, prato com pinos de referência, adaptador por modelo | a troca tinha de preservar a calibração extrínseca, e parafuso em furo de folga erra 1,10° — pino erra 0,048° |
| **Câmeras** | 8 declaradas; a frontal **não existia no desenho** e a traseira não existia em lugar nenhum | **9 postos**, todos desenhados e todos com a mesma face VMS-60 | decisão de 11/10; a frontal e a traseira passam a existir |
| **Mastro** | tubo Ø25 × 2 | **Ø32 × 2**, luva Ø42 × 5, eixo em \|Y\| 276 | 1ª frequência era **6,53 Hz** contra requisito de 7,5 e excitação de 5,60 — razão 1,16, quase ressonância. Agora 9,40 Hz |
| **Vibração dos sensores** | não calculada | **câmera rígida, LiDAR isolado**, com a conta de cada um | isolar câmera troca borrão por deriva de calibração |
| **Proteção contra impacto** | carenagem N-09, dimensionada por semelhança | **protetor T-05 sacrificial**, dimensionado pelo campo de visão | com 128° de campo, nada pode ficar à frente da lente — só acima |
| **Térmicas** | não previstas | **adaptador T-04 como requisito**: 1 peça de chapa 6 por modelo | modularidade real exige que o módulo novo não mexa no resto |
| **Satélite** | zero ocorrências no projeto inteiro | **berço T-07**, envelope 220 × 240 × 40 como requisito | não havia provisão nenhuma; agora há, com o número honesto do que cabe |
| **Caderno** | 35 folhas | **40 folhas** (Parte E nova) | mastro, usinagem VMS, postos, troca em campo e provisões |
| **Massa da estrutura A+B** | 34,2 kg | **37,5 kg** | +3,35 kg do grupo T e +0,30 kg do mastro mais grosso |
| **Energia dos sensores** | 8 × 12,95 W | **174 W** com 9 câmeras, 2 térmicas e provisão satelital | cabe no conversor de 360 W |
| **Rede** | switch PoE de 8 portas | **10 portas necessárias** — item novo de BOM | é aqui que a 9ª câmera dói, não na energia |

### Pendências que o V4 abre

| Cód. | Assunto | Grau |
|---|---|---|
| **P-30** | Modelo da câmera térmica — nenhum escolhido | ALTA |
| **P-31** | Switch PoE de 12 portas — item novo de BOM | ALTA |
| **P-32** | Terminal satelital: um de ~300 × 260 mm não cabe na provisão | MÉDIA |
| **P-33** | Software não detecta afrouxamento da braçadeira | MÉDIA |
| **P-34** | Grau IP do posto de sensor — sem ensaio, não declarado | MÉDIA |
| **P-35** | Campo de visão real da OAK-D — o protetor depende dele | MÉDIA |

### Pendências que o V4 fecha

| Cód. | Assunto | Como |
|---|---|---|
| **Caso 6 do FEA** | 1ª frequência do mastro | verificado analiticamente: Ø25 reprovava, Ø32 passa. O FEA ainda tem de confirmar |
| **8ª câmera inexistente** | declarada nos documentos, ausente no desenho | frontal e traseira desenhadas, ambas com interface VMS |

---

## 0b · Revisão H — o que mudou em relação à Rev F

| Área | Rev F | Rev H | Por quê |
|---|---|---|---|
| **Suspensão** | suporte rígido (grupo S) no conjunto; balancim pneumático como estudo isolado fora dele | **quatro braços longitudinais independentes, um fole por canto** (grupo W), dentro do conjunto | o balancim não ajustava o vão livre e pesava 6,85 kg só para articular — ver auditoria G-01 |
| **Bitola** | 470 mm | **530 mm** | é a cota que paga a rolagem macia; os 60 mm sobravam no envelope de 600, nunca usado inteiro |
| **Barra estabilizadora** | prevista no estudo (W-08/W-09 da Rev F) | **não existe** | cálculo: com 4,77 N/mm de rigidez de roda, qualquer barra útil levanta roda em articulação de 60 mm |
| **Grupo S** | 3 itens, 4,538 kg, alumínio | **retirado** | S-02 virou W-02 e mudou de função; S-01 e S-03 existiam para fixar o suporte rígido |
| **Material da chapa do motor** | Al 6061-T6 10 mm, com o aço "proposto" (sugestão 2.4) | **aço A36 10 mm** | a peça passou a ser de suspensão e cicla com o terreno; alumínio não tem limite de fadiga. **Sugestão 2.4 implementada** |
| **Caderno** | 27 folhas | **35 folhas** | Parte D nova: 4 folhas de usinagem do grupo W + 4 de montagem |
| **Manual de montagem** | não havia | **folhas 32 a 35 + `VTX-RV4-MONTAGEM-G`** | gerado do modelo: posição, vizinhança, sequência, torque e aceite |
| **Roteiro de usinagem** | coluna "processo" na BOM | **folhas 28 a 31 + `VTX-RV4-USINAGEM-G`** | corte e usinagem separados, com tolerância, referência e acabamento por operação |
| **Conferência de espaço** | não havia | **`VTX-RV4-ESPACO-G`** | volume interno medido em grade de 8 mm: 76,8 L livres, e o teto de altura de cada zona |
| **Conferência de interferência** | não havia | automática, par a par | achou E-02 × colar, bucha × orelha e flange × berço — ver auditoria G-05 e G-06 |
| **Massa** | 110,07 kg @ Z 294,1 | **126,52 kg @ Z 285,9** | +16,45 kg de suspensão; o CG desceu 8,2 mm |
| **Tombamento / envelope** | 39,44° / 19,57° (balancim) | **39,92° / 20,89°** | a bitola compensa a rolagem macia com sobra |

### Pendências que a Rev H abre

| Cód. | Assunto | Grau |
|---|---|---|
| **P-20** | Fole: nenhum modelo comercial escolhido | ALTA |
| **P-21** | Bucha autolubrificante do pivô Ø23/Ø20 | MÉDIA |
| **P-22** | Fadiga do braço W-01 e da chapa W-02 — caso 9 do FEA, novo | ALTA |
| **P-23** | Reação de torque: depende do torque real do motor escolhido | MÉDIA |

### Pendências que a Rev H fecha

| Cód. | Assunto | Como |
|---|---|---|
| **P-14** | Rolagem: rígida ou pneumática | resolvida por bitola e curso, com os três arranjos comparados numericamente |
| **Sugestão 2.4** | Chapa do motor-roda em aço | implementada, com o argumento de fadiga que faltava |

---

## 1 · Situação de cada item

Classificação conforme a seção 21 do pedido de revisão.

| # | Item | Situação original | Alteração | Arquivos alterados | Situação |
|---|---|---|---|---|---|
| A-01 | Regenerabilidade do caderno | `gerar.py` quebrava com `KeyError: 'S'` | `conjunto_a()` chama `suportes()`; `GRUPOS['S']` restaurado; balancim isolado em `conjunto_w()` | `modelo.py` | **IMPLEMENTADO E VERIFICADO** — 26 DXF bit-a-bit idênticos |
| A-02 | Regenerabilidade do pacote | `dados.itens()` quebrava com `KeyError: 'W-01'` | consequência de A-01 | `modelo.py` | **IMPLEMENTADO E VERIFICADO** — 45 códigos, 9 grupos |
| A-03 | Massa dos 4 suportes | 4,538 kg fora de `resumo_massas()` | entram com A-01 | `modelo.py` | **IMPLEMENTADO E VERIFICADO** |
| A-04 | Massa linear do tubo no custo | 0,218 kg/m (geometria dá 0,605) | derivada da seção | `custos.py` | **IMPLEMENTADO E VERIFICADO** |
| A-05 | Arquivo da Rev E | não havia; `hardware/` fora do git | 21 MB congelados | `arquivo-rev-e/` | **IMPLEMENTADO E VERIFICADO** |
| **2.1** | **Estrutura de aço** | quadro Al 6061-T6 30×30×2 | aço 1020 25×25×1,5 calculado e comparado | `revisao-f/materiais.py` | **PROPOSTO, AGUARDANDO VALIDAÇÃO** + DEPENDENTE DE CÁLCULO ESTRUTURAL |
| **2.2** | **Fixações aparafusadas** | **já aparafusadas** (F-05/F-07 em porca-rebite) | classificação em 5 classes de união; proposta de eliminar F-09 | `revisao-f/sugestoes.py` | **JÁ IMPLEMENTADO** na Rev E — ação é documental |
| **2.3** | **Planicidade 0,1 mm** | `plan 0,1` na face de S-02 | proposta 0,2 mm, com o argumento de proporção | `revisao-f/sugestoes.py` | **PROPOSTO** + **DEPENDENTE DE FABRICANTE** (ElectroCraft) |
| **2.4** | **Flange da roda em aço** | S-02 em Al 6061-T6, 10 mm | identificada a peça; aço A36 8 mm calculado | `revisao-f/sugestoes.py` | **PROPOSTO, AGUARDANDO VALIDAÇÃO** |
| 6.1 | Configuração **Vision** | 8 OAK-D desenhadas nas folhas 17–22 | catalogada; consumo não fecha | `revisao-f/sensores.py` | **IMPLEMENTADO PARCIALMENTE** — desenhada, não orçada energeticamente |
| 6.2 | Configuração **Hydro** | não existia | arquitetura e requisitos definidos | `revisao-f/sensores.py` | **PROPOSTO** + DEPENDENTE DE FABRICANTE (sensor não especificado) |
| 6.3 | Configuração **Spectral** | não existia | arquitetura definida | `revisao-f/sensores.py` | **PROPOSTO** + DEPENDENTE DE FABRICANTE |
| 6.4 | Configuração **Research** | não existia | só arquitetura, por decisão | `revisao-f/sensores.py` | **PROPOSTO** |
| 7 | Interfaces mecânica/elétrica/dados | não existiam | especificadas; envelopes em branco | `revisao-f/sensores.py` | **IMPLEMENTADO PARCIALMENTE** — bloqueado pela pendência 10 |
| 14 | Orçamento energético | não existia em nenhum documento | estrutura pronta; **não fecha** | `revisao-f/sensores.py` | **DEPENDENTE DE FABRICANTE** — faltam 7 consumos |
| 4 | Massa e CG | 97,8 kg @ 297 mm (baseline) | 110,07 kg @ 294,1 mm (recalculado) | `modelo.py` | **IMPLEMENTADO E VERIFICADO** (cálculo) |
| 5 | Soldas, rigidez, fadiga | 8 casos especificados na folha 25 | nenhum rodado | — | **DEPENDENTE DE CÁLCULO ESTRUTURAL** |
| 15 | Lista de materiais | BOM Rev E | regenera; S volta à BOM | `custos.py` | **IMPLEMENTADO PARCIALMENTE** — falta a BOM da alternativa em aço |
| 16 | Plano de manutenção | implícito nos desenhos | classes de união dão a base | `revisao-f/sugestoes.py` | **IMPLEMENTADO PARCIALMENTE** |
| 18 | Plano de validação | folha 26 da Rev E | preservado; nada executado | — | **NÃO IMPLEMENTADO** (é plano, não execução) |
| **S-AR** | **Suspensão pneumática** | não existia; folha 02 dizia "não nesta revisão" | **decisão do eng. mecânico 11/10**: dimensionada e calculada, **não desenhada** | `revisao-f/suspensao_ar.py`, `modelo.py`, folha 02 | **PROPOSTO, AGUARDANDO VALIDAÇÃO** + DEPENDENTE DE CÁLCULO ESTRUTURAL |
| M-1 | Certificado de material | "enviar certificado", sem nível | EN 10204: 3.1 só para S-02, 2.2 no resto | folha 02 | **IMPLEMENTADO** (documental) |
| M-3 | Acabamento | 3 opções | 4 opções; pré-tratamentos separados; face mascarada | folha 02 | **IMPLEMENTADO** (documental) + P-11 |
| 2.2b | Classes de união no desenho | não existiam | tabela das 5 classes | folha 13 | **IMPLEMENTADO E VERIFICADO** |
| D-09 | Folha impressa × modelo | 638 fixadores, K 4,81 kg | reemitido: 740, K 4,60 kg | folha 02 | **RESOLVIDA na reemissão** |
| 17 | Emissão da Rev F | carimbo em E | **Rev F emitida**: 27 folhas, 4 PDFs | `folhas.py` | **IMPLEMENTADO E VERIFICADO** |
| **LIB** | **Mecanismo de liberação** | selo e assinaturas fixos no código | parametrizados, com guarda contra liberação por omissão | `desenho.py`, `folhas.py`, `revisao-f/liberacao.py` | **IMPLEMENTADO E VERIFICADO** — selo muda de ponta a ponta na prova |
| **ESC** | **Escopo liberado** | — | **Parte A completa**, incluindo S-01/S-03: protótipo de suportes rígidos | folha 02 | **DECIDIDO 11/10** — pneumática vira evolução |

---

## 2 · Resumo das quatro sugestões do fabricante

### 2.1 · Estrutura em aço com fechamento de alumínio

**Perfil equivalente:** aço SAE 1020 **25×25×1,5** (NBR 6591).

| | Al 6061-T6 30×30×2 | Aço 1020 25×25×1,5 |
|---|---|---|
| Rigidez EI | 2,03 × 10⁹ N·mm² | 2,67 × 10⁹ — **132 %** |
| Resistência, condição soldada | 216 N·m (ZTA a 110 MPa) | 219 N·m — **101 %** |
| Massa linear | 0,605 kg/m | 1,107 kg/m |
| Massa do quadro (8,94 m) | 5,516 kg | 10,003 kg — **+4,486 kg** |
| Matéria-prima do tubo | R$ 74,47 | R$ 27,26 … 47,70 |

**Economia:** R$ 27 a R$ 47 em matéria-prima. A estrutura inteira custa R$ 2.585 e o
rover R$ 94.000 — a economia é de **0,03 a 0,05 % do custo do rover**.

**O argumento real a favor do aço não é o preço do quilo:** é não perder resistência na
solda. Em 6061-T6, a ZTA cai para ~110 MPa (folha 25); em aço 1020, não há essa perda.
Comparado pela liga virgem, a troca não traz resistência nenhuma; comparado como a
estrutura vai estar — soldada, sem tratamento térmico pós-solda —, o aço tem quase o
dobro da tensão utilizável. **Esse é o mérito técnico da sugestão, e ele é real.**

**O impedimento é massa, não custo:** +4,486 kg contra uma margem de **0,490 kg** (D-03).

**Recomendação:** não decidir material antes de resolver a pendência 9 (massa oficial). A
margem esgotada não é consequência do aço — é o estado do projeto em alumínio.

**Pendências:** cotação dos dois perfis; diferencial de mão de obra de solda Al/aço
(pode ser maior que a economia de matéria-prima e inverter a conta); revestimento
anticorrosivo do aço, sem cotação; FEA de torção da folha 25; isolamento galvânico
aço↔alumínio nas interfaces de chapa.

### 2.2 · Fixações aparafusadas nas tampas

**JÁ IMPLEMENTADO na Rev E.** De 740 itens de fixador, **728 (98,4 %) são removíveis**.
Carenagens e tampas saem com M5×12 ISO 7380 (F-07) em porca-rebite M5 (F-06); a chapa de
fundo com M6×16 (F-05) em porca-rebite M6 (F-04). Cabeça ISO 7380 é baixa e lisa — o
caderno já justifica: "não prende galho".

O único rebite permanente é **F-09** (Ø4,8×10, 12 unidades), que une as nervuras C-02 à
chapa de fundo C-01 — subconjunto interno, embaixo do rover, que não é tampa de
manutenção.

**A leitura do fabricante era defensável:** a lista mostra "Rebite de repuxo" sem dizer
onde ele está. A ação da Rev F é **documental** — classificar as uniões em 5 classes e
publicar a tabela, para que "o que preciso soltar para abrir isto?" se responda no
desenho.

**Única mudança física proposta:** passar F-09 a parafuso M5 em porca-rebite, para que
não exista rebite nenhum no projeto e a dúvida não se repita. Custa 12 parafusos.

| Classe | Itens |
|---|---|
| 1 · União estrutural permanente | 12 |
| 2 · União estrutural desmontável | 98 |
| 3 · Fixação de tampa | 182 |
| 4 · Fixação de carenagem | 416 |
| 5 · Fixação de módulo de sensor | 32 |

### 2.3 · Planicidade de 0,1 mm

**Superfície:** face Y = 204 (datum B) de **S-02**, chapa de montagem do MPW86, 10 mm,
que recebe a flange Ø105,7 do motor por 7 parafusos M4 no PCD 95.
**Classificação:** superfície de montagem de motor-roda — a mais crítica das cinco
categorias do pedido.

**O argumento não é "0,1 é difícil".** É que o mesmo desenho aceita **0,3 mm de
perpendicularidade** na mesma face. Normalizando cada tolerância pela base em que atua:

| Característica | Tolerância | Base | Inclinação |
|---|---|---|---|
| Planicidade | 0,1 mm | 95 mm (PCD) | 0,105 % |
| Perpendicularidade | 0,3 mm | 124 mm (altura útil) | 0,242 % |

A planicidade está **2,3× mais apertada** que a perpendicularidade — e perpendicularidade
é o que desalinha a roda, enquanto planicidade se fecha com o aperto dos 7 parafusos
contra uma chapa de 10 mm.

**Proposta: 0,2 mm**, mantendo perp 0,3 e Ra 3,2. A razão cai para 1,1× — proporcional.
Escolhido 0,2 e não 0,15 ou 0,25 porque é onde o processo muda de categoria: a 0,1 exige
alívio de tensões antes do faceamento, duas passadas e inspeção individual com relógio;
a 0,2, uma passada em fresadora comum e inspeção com régua e calibre de folga.

**DEPENDENTE DE FABRICANTE.** O datasheet 011121 publica a interface mas **não publica a
planicidade exigida da contrapeça**. Perguntar à ElectroCraft: *qual a planicidade e a
rugosidade máximas admitidas na superfície de montagem, e qual o torque dos 7 parafusos
M4 com engajamento de 4 a 5 mm?* A segunda importa tanto quanto a primeira — é o aperto
que fecha o erro de planicidade.

### 2.4 · Flange ou placa de interface em aço

**São duas peças, e só uma é da ValTexa:**

| Peça | O que é | Ação |
|---|---|---|
| Flange integrada ao MPW86 | face Ø105,7, 7 furos M4×0,7-6H no PCD 95 | **NÃO ALTERAR** — é componente do motor |
| **S-02** · chapa de montagem | chapa 124×204×10, furo central Ø88, 7 furos Ø4,5 no PCD 95 | **é esta a peça da sugestão** |

**Classificação:** placa de montagem (interface mecânica), não flange integrada. Peça
independente, soldada a duas nervuras S-03, com a face usinada. Fabricável em aço sem
tocar no motor.

**Espessura equivalente em aço A36** (critério: W × tensão admissível soldada):

| Espessura | Resistência | Rigidez | Massa |
|---|---|---|---|
| 5 mm | 57 % | 36 % | 145 % |
| 6 mm | 82 % | 63 % | 174 % |
| **8 mm** | **145 %** | **148 %** | 233 % |
| 10 mm | 227 % | 290 % | 291 % |

**Aço A36 de 8 mm** é a espessura comercial mínima que atende: 4 × 1,096 kg = 4,384 kg
contra 1,885 kg em alumínio → **+2,499 kg**.

**O ganho não é resistência nominal** (6061-T6 virgem 240 MPa × A36 250 MPa são quase
iguais). São três outros:

1. **não perde na solda** — S-02 é soldada; em aço a tensão utilizável é 2,3× a do
   alumínio na condição soldada;
2. **mantém a face usinada sob aperto repetido** — 7 parafusos M4, e o motor sai e volta
   em manutenção; alumínio amassa sob a cabeça a cada ciclo. **É o que liga esta sugestão
   à 2.3:** não serve especificar planicidade numa face que se deforma na terceira
   desmontagem;
3. **usina melhor para tolerância apertada** — alumínio empasta e forma aresta postiça.

**Mesmo impedimento da 2.1:** +2,499 kg contra margem de 0,490 kg.

---

## 3 · Arquitetura de sensores

| Configuração | Módulos | Situação |
|---|---|---|
| **Vision** (base) | 8 OAK-D Pro W PoE, LiDAR Mid-360, GNSS ZED-F9P, IMU MTi-630, Jetson Orin NX, RFD900x, E-STOP | **desenhada** (folhas 17–22); orçamento energético **não fecha** |
| **Hydro** | Vision + 1 câmera térmica radiométrica | arquitetura e requisitos definidos; sensor **não especificado** |
| **Spectral** | Vision + 1 multiespectral | arquitetura definida; sensor **não especificado** |
| **Research** | Vision + instrumento sob análise | só arquitetura |

**Decisões de arquitetura registradas:**

* **uma** térmica, não oito. Oito seriam oito calibrações e oito fluxos para um ganho que
  ninguém mediu;
* térmica e multiespectral **não** entram na base — são extensões;
* **PoE é o caminho principal.** As 8 OAK-D já são PoE: módulo novo que fale PoE entra
  sem cabo, conector ou distribuição nova;
* **E-STOP não compartilha** alimentação nem barramento com a percepção;
* **orientação por pino de referência**, não só por parafuso: módulo que volta girado 1°
  da manutenção invalida a calibração extrínseca em silêncio.

**Energia disponível** (da BOM, 21/09/2026): bateria 16S LiFePO4 105 Ah = **5.376 Wh**,
úteis a 80 % = **4.301 Wh**. Barramento 12 V limitado a **360 W**.

**O orçamento energético NÃO FECHA.** Consumo conhecido: 103,6 W (as 8 câmeras, pelo teto
normativo de PoE 802.3af — teto, não medição). **Faltam 7 consumos:** LiDAR, GNSS, IMU,
Jetson, rádio, E-STOP e, nas extensões, o sensor novo. Nenhum documento da Rev E traz
tabela de consumo, e o documento técnico ressalva que as capacidades operacionais da
baseline não foram verificadas.

Nada foi estimado para fechar a conta. A lista do que pedir está em
`sensores.pendencias_de_fabricante()` e vai com a RFQ.

**Limitações declaradas, para não virarem promessa:**

* imagem térmica **não mede umidade do solo** — mede temperatura de superfície, que
  responde a transpiração, vento, radiação e umidade do ar ao mesmo tempo;
* índice espectral **não identifica doença sozinho**; mais bandas não garantem mais
  precisão — o ganho tem de ser medido por aplicação, contra o que o RGB já entrega.

---

## 4 · O que ainda não foi feito, e por quê

| Entregável do pedido | Situação |
|---|---|
| Arquivos CAD de sistema modificados | não existem CAD de sistema; o paramétrico **é** o CAD e foi alterado |
| DXF atualizados | regenerados e **idênticos** à Rev E — a correção não mexeu em geometria. Novos DXF só saem depois da decisão de material |
| BOM da alternativa em aço | não montada: depende da decisão de perfil, e perfil não decidido não vira BOM |
| Revisão de massa e CG das alternativas | **feita** para A e B; falta a híbrida C peça a peça |
| Soldas, rigidez, fadiga | **nenhum cálculo rodado.** Os 8 casos da folha 25 continuam especificados e não executados |
| Relatório de comparação de custos | parcial: matéria-prima calculada; solda, usinagem e revestimento **sem cotação** |
| Desenhos da Rev F | **não emitidos.** O carimbo continua em E, de propósito: subir a revisão sem decisão de material produziria um caderno que descreve um rover que ninguém escolheu |
| Envelopes dos módulos de sensor | em branco — bloqueados pela pendência 10 (desenho dimensional da OAK-D) |

---

## 5 · Pendências, em ordem de bloqueio

| # | Pendência | Bloqueia | Responsável |
|---|---|---|---|
| **P-01** | Decidir suspensão: rígida (S) ou balancim (W) | **tudo** — as 4 sugestões se referem ao desenho com S | Eng. mecânico |
| **P-02** | Massa oficial: 85,04 × 82,49 × 110,07 × 137,5 kg | decisão de material (2.1 e 2.4) | Eng. mecânico + ValTexa |
| **P-03** | FEA, 8 casos da folha 25 | liberação para fabricação | Eng. mecânico |
| **P-04** | Planicidade e torque admitidos pelo MPW86 | aprovar 0,2 mm | ElectroCraft |
| **P-05** | Consumo dos 7 componentes | qualquer módulo novo | Fabricantes |
| **P-06** | Desenho dimensional da OAK-D Pro W PoE | envelopes dos módulos | Luxonis |
| **P-07** | Cotação: perfis, solda Al/aço, revestimento | comparação de custo | Fornecedores |
| **P-08** | Imagem das alterações do fabricante | conferir se as 4 sugestões foram lidas certo | ValTexa |
| **P-09** | Interface do ZLTECH (9 campos) | a BOM recomenda esse motor e o suporte não pode ser desenhado para ele | ZLTECH |
| **P-10** | Nível de certificado por peça (M-1) | fechar a RFQ | Eng. + ValTexa |
| **P-11** | Mascarar ou não a face de montagem na pintura (M-3) | desenho de acabamento | Eng. mecânico |
| **P-12** | **Os 8 casos do FEA foram escritos para suspensão rígida** — com o fole, as condições de contorno mudam | **rodar o FEA** | Eng. mecânico |
| **P-13** | Escolher os 9 componentes pneumáticos e levantar massa real | massa final | ValTexa + fornecedores |
| **P-14** | Rolagem: rígida (proposta) ou pneumática | geometria da suspensão | Eng. mecânico |
| **P-15** | Fadiga da S-02 com carga cíclica | material da S-02 | Eng. mecânico |
| **P-16** | Desenhar foles, suportes W-18 e roteamento pneumático | fabricação da suspensão | Eng. + projetista |
| **P-17** | Travar ou não as válvulas durante a captura | requisito de software | Eng. + ValTexa |

---

## 6 · Reclassificação após 11/10/2026

| # | Antes | Agora |
|---|---|---|
| P-01 | suspensão rígida × balancim · **bloqueia tudo** | **RESOLVIDA** — folha 02 fecha a Rev E em rígida; engenharia decidiu **pneumática** para o V3 |
| P-08 | imagem do fabricante ausente | **RESOLVIDA** — folha 02 marcada recebida |
| D-08 | referência à folha 28 inexistente | **CORRIGIDA** |
| D-09 | folha impressa × modelo (638 × 740) | **RESOLVIDA na reemissão** |
| **P-02** | massa oficial · ALTA | **CRÍTICA** — com suspensão pneumática o rover vai a **122,79 kg**, contra baseline de 97,8 |
| P-03 | FEA, 8 casos | **agravada por P-12**: os casos precisam ser **reescritos** antes de rodar |

## 7 · Massa, consolidada

| Configuração | Massa | Δ baseline (97,8) | Z_cg | Tombamento |
|---|---|---|---|---|
| Baseline Rev E declarada | 97,80 kg | — | 297,0 | 38,4° |
| **Alumínio, como está** | **110,07 kg** | +12,27 | 294,1 | 38,6° |
| + aço no quadro (2.1) | 114,56 kg | +16,76 | — | — |
| + aço na S-02 (2.4) | 112,57 kg | +14,77 | — | — |
| + híbrida C completa | 117,20 kg | +19,40 | — | — |
| **+ suspensão pneumática** | **122,79 kg** | **+24,99** | **285,7** | **39,4°** |
| + pneumática **e** híbrida C | ~129,9 kg | +32,1 | — | — |

**A suspensão pneumática é a única das alternativas que melhora a estabilidade** — baixa
o CG em 8,4 mm porque o sistema fica abaixo dele. Todas aumentam a massa, e a margem da
baseline é de 490 g.
