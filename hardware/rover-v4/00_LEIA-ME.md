# ValTexa Rover **V4** — engenharia mecânica

**Revisão atual: K** (28/10/2026) · padrão: **opção B, aço** · EMITIDO PARA COTAÇÃO E VALIDAÇÃO — **NÃO
LIBERADO PARA FABRICAÇÃO**

## Rev K — bateria em 2 módulos e leiaute interno refeito (28/10/2026)

Aplica as decisões dos sócios de 28/10: chassi em **aço** (agora o padrão), autonomia de **8 h a 2 m/s** e a
**bateria dividida em 2 módulos de 8 células**, um de cada lado dos trilhos G-02 — o pack inteiro não cabia
(127 mm livres para ~140). Compressor, reservatório, Jetson, driver e BMS ganharam zonas onde cabem; as 10 zonas
de `revisao-h/espaco.py` passam. Novo `revisao-h/autonomia.py`: 8,4 h no plano e 5,4 h em morro de 10°.
Detalhes e pendências em **`revisao-h/VTX-RV4-REV-K.md`** e na folha 43.

| Comando | Gera |
|---|---|
| `python gerar.py` (em `chassi-gaiola/`) | caderno da opção B, aço (padrão) em `saida/opcao-B-aco-carbono/` |
| `VTX_OPCAO=AL python gerar.py` | caderno da opção A, alumínio |
| `python autonomia.py` (em `revisao-h/`) | conta de autonomia para 8 h a 2 m/s |

## Rev J — a Rev I na fonte (16/10/2026)

A **Rev I** (13/10/2026) foi enviada para cotação em duas opções, mas só existia em PDF (`ENVIO_COTACAO_REV_I/`,
fora do repositório), editado sobre o caderno da Rev H. A **Rev J** a traz para o modelo paramétrico — mesma
geometria, mesmos materiais — e soma as correções de cálculo de 15/10. Como os números calculados mudaram, a
letra mudou. O registro completo está na **folha 43** de cada caderno.

| | Opção A — alumínio | Opção B — aço carbono |
|---|---|---|
| Caderno | `chassi-gaiola/saida/opcao-A-aluminio/VTX-RV4-CG-J-AL.pdf` | `chassi-gaiola/saida/opcao-B-aco-carbono/VTX-RV4-CG-J-AC.pdf` |
| Chassi (Q, C, G, base M) | Al 6061-T6 / 5052-H32, TIG ER5356 | aço SAE 1020 / A36 / SAE 1010, MAG ER70S-6 |
| Parte A | 31,61 kg | 55,72 kg |
| Pressão de projeto do fole (teto 8 bar) | 7,41 bar | **8,81 bar — acima do teto** |
| Envelope de estabilidade (baseline 16,2°) | 16,4° | 16,8° |

Nas duas: **W-12 e W-13 em aço A36**, e **sem a cota individual de planeza 0,1** na face do motor (W-02) e nas juntas
do colar (W-13) — vale a ISO 2768-mK. Tudo o que muda entre as opções está em `chassi-gaiola/opcao.py`.

```
cd chassi-gaiola
set VTX_OPCAO=AL && python gerar.py     # opção A (padrão)   — no bash: VTX_OPCAO=AL python gerar.py
set VTX_OPCAO=AC && python gerar.py     # opção B
```

Os documentos de `revisao-h/` são gerados na opção A (padrão); rode-os com `VTX_OPCAO=AC` para a B. O pacote de
cotação em `pacote-rev-h/` continua sendo o da Rev H e não foi reemitido.

> O **V3** está preservado, inteiro e intocado, em `../rover-v3`. Nada lá foi sobrescrito.
> Um backup das fontes do V4 **antes** da correção de 12/10/2026 está em `_historico/`.

---

## O que mudou em 12/10/2026

O V4 emitido em 11/10 tinha o mastro, o escopo, a lista de materiais e sete documentos do pacote ainda com **texto do
V3**. Esta correção traz tudo para o que está desenhado. O relato completo — inclusive os erros do relatório de 11/10 —
está em `revisao-h/VTX-RV4-AUDITORIA-H.md`, §0.-1.

| Área | Como estava | Como está |
|---|---|---|
| **Mastro** | Ø32 × 2, dimensionado para 3 câmeras | **Ø32 × 3**, dimensionado para 3 OAK-D + 2 térmicas removíveis + antena no topo: 7,88 Hz contra 7,5 de requisito |
| **Térmicas** | só o adaptador T-04 como requisito | posições **H1–H4**, módulo **removível à mão** (4 parafusos M5 imperdíveis sobre os mesmos pinos) — folha 41 |
| **Antena GNSS RTK** | só na tampa (N-01) | **também no topo do mastro** (adaptador T-10, até 0,42 kg) — a escolha é decisão aberta (P-36) |
| **Cabos** | só texto | interligação funcional, passagens e comprimentos ESTIMADOS — folha 42 e `VTX-RV4-CABOS-H` |
| **Caderno** | 40 folhas, 343 defeitos de layout | **42 folhas, 0 defeitos medidos** no navegador (`verifica_layout.py`) |
| **Pacote de cotação** | 7 documentos com texto do V3 | reescritos e conferidos contra o modelo |

### O que o cálculo do mastro diz — e o que ele NÃO diz

| | Valor |
|---|---|
| 1ª frequência, mastro cheio | **7,88 Hz** (requisito 7,5 Hz: passa por 5 %) |
| Razão contra o terreno | **1,41** (margem de 2,0): **NÃO fecha** a 1,4 m/s; só abaixo de 0,98 m/s |
| Antena máxima para manter 7,5 Hz | **0,42 kg** |
| Cabos no furo do tubo | 40 % do furo (limite 40 %), com cabo de Ø7 estimado |

São **cálculos sobre massas estimadas** (OAK-D 0,25 kg, térmica 0,20 kg, antena 0,30 kg). Nenhum ensaio foi feito; a
OAK-D em 0,50 kg já tira o mastro do requisito. O que fecha a conta é o ensaio V-12 (espectro do mastro em marcha) e a
massa real dos sensores.

## Correções de 15/10/2026

Revisão dos cálculos para a tarefa de requisitos e compatibilidade das peças. Nenhuma geometria mudou; o detalhe
está em `revisao-h/VTX-RV4-CORRECOES-2026-10-15.md`. O que muda a leitura do projeto:

- **Estabilidade:** com o CG real do V4 (336 mm, mastro cheio) o envelope é **16,3°**, não 20,9° — passa os 16,2° da
  baseline por 0,1°. A suspensão pneumática continua mais estável que o balancim no mesmo CG.
- **Barramento de 12 V:** sensores + Jetson + compressor chegam a **387–401 W** contra o conversor de 360 W.
- **Rede:** contando a ligação à Jetson e o satélite, são **12 portas**; o switch de 12 não sobra para térmica Ethernet.
- **Espaço:** **4 de 6 zonas** internas não comportam os componentes estimados que o projeto põe nelas.
- **BOM:** 9 OAK-D (não 8).

O caderno de 42 folhas não foi reemitido: a cotação em andamento usa a Rev I, que existe só em PDF.

## Por que V4, e por que a revisão continua em H

O **número de versão** mudou porque a arquitetura de sensores mudou: a interface deixou de ser uma chapa furada e passou
a ser um sistema modular com pino de referência. A **letra de revisão** continua em H, em vez de recomeçar em A, porque o
hardware é contínuo: chassi, suspensão pneumática, gaiola e carenagens são os mesmos da Rev G do V3. Toda referência a
Rev E, F e G neste caderno aponta para o histórico do V3.

## Os números que resumem o V4

**0,048° contra 1,10°** — a repetibilidade da interface com pino de referência contra a mesma interface só com parafuso.
A 10 m: 8,5 mm contra 192 mm. É esse fator de 23 que separa "removível" de "modular". É **cálculo**: o ensaio V-10 é o que
o valida ou derruba.

**6,53 Hz → 7,88 Hz** — o mastro herdado do V3 estava a 1,17× da excitação do terreno (quase ressonância); o de hoje
passa o requisito, mas **não fecha a margem** — ver acima.

---

## O que há aqui

| Pasta | O que é |
|---|---|
| **`chassi-gaiola/`** | **o CAD.** Modelo paramétrico — dele saem as 43 folhas, os 37 DXF, as listas de corte e as massas, por opção de material |
| **`revisao-h/`** | cálculos e documentos, em `.py` e `.md`, com os PDFs em `revisao-h/pdf/` |
| **`pacote-rev-h/`** | gerador do pacote de cotação |
| **`_historico/`** | fontes do V4 antes da correção de 12/10/2026 |
| `../rover-v3/` | o V3 completo, congelado |

## Para enviar à empresa que vai fabricar

```
pacote-rev-h/saida/VALTEXA_ROVER_V4_REV_H/
```

| Pasta | Conteúdo |
|---|---|
| `03_DESENHOS_TECNICOS/SENSORES_MODULARES/` | mastro completo, VMS-60, nove postos, troca em campo, módulo térmico |
| `03_DESENHOS_TECNICOS/MASTROS/` e `CABOS/` | base e haste, rigidez; interligação e passagens |
| `03_DESENHOS_TECNICOS/SUSPENSAO_USINAGEM/` | folhas 07 e 28 a 31 — as peças de usinagem da suspensão |
| `03_DESENHOS_TECNICOS/MONTAGEM/` | folhas 32 a 35 — posição, sequência, torques, regulagem |
| `04_CAD/` | DXF 1:1 e STL (conjunto de entrega, conjunto completo, mastro) |
| `05_BOM/` | lista de materiais mecânica, com os opcionais separados |
| `10_CUSTOS/` | quantidades fechadas; **preços do V3** e itens novos do V4 **a cotar** (fora dos totais) |
| `11_ENGENHARIA_REV_H/` | os 11 documentos de engenharia desta revisão |

## Para o engenheiro mecânico

| Documento | Assunto |
|---|---|
| `revisao-h/pdf/VTX-RV4-LIBERACAO-H.pdf` | **o escopo aprovado é a Rev F do V3** — leia antes de liberar |
| `revisao-h/pdf/VTX-RV4-AUDITORIA-H.pdf` | o que a auditoria de 12/10 encontrou, e os erros do relatório anterior |
| `revisao-h/pdf/VTX-RV4-MASTRO-H.pdf` | a rigidez do mastro cheio, a margem que não fecha, a massa máxima de antena |
| `revisao-h/pdf/VTX-RV4-MODULAR-H.pdf` | a interface VMS-60, o módulo térmico, a antena, energia e banda |
| `revisao-h/pdf/VTX-RV4-CABOS-H.pdf` | interligação, passagens (as que faltam) e comprimentos |
| `revisao-h/pdf/VTX-RV4-SUSPENSAO-H.pdf` | a suspensão pneumática, inalterada desde a Rev G |
| `revisao-h/pdf/VTX-RV4-REGISTRO-ALTERACOES-H.pdf` | histórico V3 → V4, item a item |

## Para a oficina

| Documento | Assunto |
|---|---|
| `revisao-h/pdf/VTX-RV4-USINAGEM-H.pdf` | roteiro de operações peça por peça |
| `revisao-h/pdf/VTX-RV4-MONTAGEM-H.pdf` | posição de cada peça, sequência, torques, aceite |

---

## Regenerar tudo

```
cd chassi-gaiola && python gerar.py            # 43 folhas: HTML + 37 DXF + 6 PDFs (VTX_OPCAO=AL ou AC)
cd chassi-gaiola && python verifica_layout.py  # MEDE o layout de cada folha no navegador (0 defeitos = passa)
cd revisao-h     && python relatorios.py       # os 6 documentos gerados do modelo
cd revisao-h     && python gerar_docs.py       # PDF de todos os documentos
cd pacote-rev-h  && python gerar_pacote.py     # pacote de cotação completo
```

Os cálculos rodam sozinhos (no console do Windows também):

```
cd revisao-h
python mastro.py        # rigidez do mastro cheio, margem, massa máxima de antena, cabos
python modular.py       # interface VMS-60, térmicas, antena, energia, banda
python roteamento.py    # interligação, passagens, comprimentos estimados   NOVO
python suspensao.py     # suspensão pneumática
python espaco.py        # espaço interno e interferência entre peças (mastro completo)
python montagem.py      # mapa de posições, sequência, torques  (--item T-02)
python usinagem.py      # roteiro de usinagem                   (--item T-04)
python dimensional.py   # levantamento dimensional e 7 CSVs
```

## Onde mudar o quê

- **cota, material ou geometria** → `chassi-gaiola/modelo.py`
- **composição das folhas** → `folhas.py` (01–16), `folhas_b.py` (17–27), `folhas_w.py` (28–35), `folhas_t.py` (36–42)
- **padrão VMS-60** → `VMS_FUROS`, `VMS_PRATO`, `D_PINO_REF` em `modelo.py`. Um lugar só
- **seção do mastro** → `D_MASTRO`, `E_MASTRO` em `modelo.py`; refazer `python mastro.py`
- **posições térmicas** → `Z_TERMICA` em `modelo.py`
- **sequência de montagem e torques** → `revisao-h/montagem.py`
- **tolerância e roteiro de usinagem** → `revisao-h/usinagem.py`

## Estado em uma linha

O V4 resolve a modularidade, mas **o mastro cheio passa os 7,5 Hz por 5 % sobre massas que ninguém mediu e não fecha a
margem contra o terreno**. A estabilidade lateral passa a baseline por 0,1°, o conversor de 12 V não atende o pico
e o leiaute interno não comporta os componentes estimados (correções de 15/10/2026). Continua faltando o FEA (9 casos, nenhum rodado), a massa oficial, o modelo do fole, a ficha
da OAK-D, o modelo da térmica e da antena, a passagem de cabo das câmeras C7 e C8, e um switch de 12 portas que a 9ª câmera
obriga. **Este pacote é para cotar, não para fabricar.**
