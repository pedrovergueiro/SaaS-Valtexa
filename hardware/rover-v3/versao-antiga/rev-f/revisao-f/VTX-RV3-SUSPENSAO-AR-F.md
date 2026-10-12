# VTX-RV3 · Suspensão pneumática — dimensionamento e consequências

**Decisão:** engenheiro mecânico da ValTexa, 11/10/2026 — a suspensão do Rover V3 é
**pneumática**.
**Situação:** DIMENSIONADA E CALCULADA · **NÃO DESENHADA** · NÃO LIBERADA PARA FABRICAÇÃO

> **O primeiro protótipo é de suportes rígidos.** A liberação de 11/10 cobre a Parte A
> completa, incluindo S-01 e S-03 — ver `VTX-RV3-LIBERACAO-F.md`. Isso não cancela a
> suspensão pneumática: põe a máquina andando antes de ela existir em desenho. Quando
> entrar, as 12 peças S-01/S-03 são substituídas e S-02 permanece.
**Cálculo reproduzível:** `python revisao-f/suspensao_ar.py`

---

## 1 · O que a decisão substitui

Havia duas arquiteturas em disputa no projeto, e a decisão resolve as duas:

| | Antes | Agora |
|---|---|---|
| Rev E, folha 02 | "Suspensão: não nesta revisão — suportes rígidos" | **superado** |
| Estudo W em `modelo.py` | balancim longitudinal, mola de aço, nunca desenhado | **aproveitado** como base |

A suspensão pneumática **usa o balancim do estudo W** e troca o apoio rígido por mola
pneumática. O trabalho do estudo W não se perde — ele vira a estrutura que carrega os
foles.

---

## 2 · A restrição que a decisão precisa respeitar

`modelo.py` registrava, desde antes desta revisão:

> *A articulação em rolagem (eixo oscilante, mola macia) derruba o tombamento de 37,7°
> para 20,1° — inaceitável em lavoura de café.*

**Fole é mais macio que mola de aço.** Se a maciez for aplicada em rolagem, a suspensão
pneumática cai na condição que o projeto já havia rejeitado — e cai mais fundo.

### A arquitetura separa os dois eixos

| Eixo | Comportamento | Como |
|---|---|---|
| **Arfagem** (pitch) | **pneumático** | mola Ø50 em cada ponta do balancim |
| **Rolagem** (roll) | **rígido** | barra de equalização de braços cruzados (W-08/W-09), que ganha função nova: acoplar os lados para que um fole não afunde sem o outro |

**Isto é escolha desta revisão, não instrução recebida.** A decisão que chegou foi
"suspensão a ar"; separar os eixos é a interpretação que preserva a conclusão que o
projeto já tinha. Se a intenção for rolagem pneumática também, os números estão no §6 e a
decisão é do engenheiro — com o dado na frente.

---

## 3 · Dimensionamento do fole

Carga por roda, com a massa recalculada de 110,07 kg:

| Condição | Valor |
|---|---|
| Estática | 27,5 kgf = **270 N** |
| Dinâmica (fator 3, caso 2 do FEA) | **810 N** |
| Projeto (× 1,35 de transferência longitudinal) | **1.093 N** |

### A escolha é contraintuitiva

| Bitola | Pressão estática | Pressão de projeto | Veredito |
|---|---|---|---|
| Ø40 | 2,15 bar | **8,70 bar** | acima do teto de 8 bar |
| **Ø50** | **1,37 bar** | **5,57 bar** | **SERVE** |
| Ø60 | 0,95 bar | 3,87 bar | estática baixa: fole enrugado |
| Ø70 | 0,70 bar | 2,84 bar | estática baixa |
| Ø80 | 0,54 bar | 2,17 bar | estática baixa |

**Ø80 seria a escolha intuitiva** — mais robusto, mais capacidade. Com esta carga ele
opera a **0,54 bar**: folgado demais para funcionar como mola. Fole abaixo de ~1 bar
trabalha enrugado, não tem rigidez previsível, desgasta na dobra e mascara o controle de
altura.

**O rover é leve, e isso inverte o dimensionamento habitual de suspensão pneumática.**
Ø50 é a única bitola corrente que fecha os dois critérios.

* Curso total: **70 mm** (2 × os 35 mm do estudo W)
* Faixa de ajuste de altura: **50 mm** dentro do curso

---

## 4 · Massa — e é aqui que dói

| | kg | Z (mm) |
|---|---|---|
| **Entra** · componentes pneumáticos (9 itens) | +8,98 | 247 |
| **Entra** · balancim W (já modelado) | +6,85 | 169 |
| **Sai** · S-01 (4 un) e S-03 (8 un) | −2,65 | 230 |
| **LÍQUIDO** | **+12,72** | — |

### Efeito global

| | Antes | Depois | Δ |
|---|---|---|---|
| Massa nominal | 110,07 kg | **122,79 kg** | **+12,72** |
| Z do CG | 294,1 mm | **285,7 mm** | **−8,4** |
| Tombamento geométrico | 38,63° | **39,44°** | **+0,81 — melhora** |
| Envelope de estabilidade | 18,82° | **19,57°** | **+0,75 — melhora** |
| Margem vs baseline (97,8 kg) | +0,49 kg | **−24,99 kg** | — |

**A estabilidade melhora.** Não é intuitivo e vale explicar: o sistema pneumático fica
baixo (Z 247) e o balancim mais baixo ainda (Z 169), os dois bem abaixo do CG de 294 mm.
Acrescentar massa embaixo **baixa** o centro de gravidade.

**O problema é só um, e é o de sempre neste projeto: a massa.** O rover passa a 122,79 kg
contra uma baseline de 97,8 — **25 kg acima**.

---

## 5 · Energia — não é o problema

| | |
|---|---|
| Compressor, pico | 180 W |
| Ciclo de trabalho em regime | 5 % |
| Compressor, médio | 9,0 W |
| Solenoides + controle | 1,8 W |
| **Total médio** | **10,8 W** |
| Fração da bateria útil (4.301 Wh) por hora | **0,25 %** |

Eu esperava que a energia fosse objeção. Não é: 10,8 W médios são desprezíveis contra os
5.376 Wh da bateria.

**A ressalva é de pico, não de média.** Os 180 W do compressor concorrem com a tração no
barramento de 12 V, que tem teto de 360 W — e o consumo já comprometido desse barramento
**não está levantado** (P-05). Dimensionar contando o compressor ligado junto com o pior
caso de tração.

---

## 6 · Rolagem: os dois números, para a decisão

| | Tombamento | Envelope de estabilidade |
|---|---|---|
| **Rígida** (proposta) | **39,44°** | **19,57°** |
| Macia (se adotada) | 34,32° | **14,70°** |
| Perda | 5,12° | **4,87° — 25 % do envelope** |

Com rolagem macia, a carroceria inclina 8,5° no limite do curso e o CG desloca 42 mm para
fora.

**Nota de honestidade sobre o cálculo:** a perda que encontro (5,12°) é **menor** que a
da nota original do projeto (37,7° → 20,1°, 17,6°). A razão é geométrica e favorável ao
ar: o curso do fole é limitado a ±35 mm, enquanto um eixo oscilante tem curso muito
maior. **Suspensão pneumática com curso curto perde menos em rolagem que o eixo oscilante
que o projeto rejeitou.** Ainda assim, 25 % do envelope é perda grande, e a recomendação
de manter a rolagem rígida se sustenta.

---

## 7 · Consequência que afeta a cotação agora

**S-01 e S-03 saem com a suspensão pneumática.** São 12 peças (4 chapas de 6 mm e
8 nervuras de 8 mm) que existem para fixar o suporte rígido ao quadro.

A folha 02 da Rev F foi atualizada com o aviso: **cotar, mas não fabricar** antes da
liberação da suspensão. Fabricá-las agora é produzir peça que a decisão já descartou.

**S-02 permanece.** É a interface do motor-roda — furo Ø88 e os 7 furos M4 no PCD 95 —
e essa interface não muda com a suspensão. Deixa de soldar em S-01/S-03 e passa a soldar
no balancim: mesma peça, outra montagem.

### E a sugestão 2.4 do fabricante fica mais forte

Com suspensão pneumática, S-02 passa de peça de montagem a **peça de suspensão**: ela
recebe a carga da roda e a entrega ao balancim, com o fole no caminho. O carregamento
muda de estático para **cíclico**, e isso muda a conta:

* em 6061-T6 soldado, a ZTA vale 110 MPa e a categoria de detalhe de fadiga do
  EN 1999-1-3 para junta soldada em alumínio é baixa;
* **alumínio não tem limite de fadiga** — acumula dano indefinidamente. Aço carbono tem.

Num componente que agora cicla a cada ondulação do terreno, a diferença deixa de ser
acadêmica. **S-02 em aço passa de "proposto" a "recomendado"**, e o caso 5 do FEA passa a
exigir verificação de fadiga.

---

## 8 · Lista de componentes

Nenhum modelo comercial foi escolhido. As massas são de **faixa de catálogo** para a
classe do componente, não de datasheet. Esta lista **não serve para cotar** — serve para
responder se cabe.

| Código | Descrição | Qtd | kg/un | Z | Origem |
|---|---|---|---|---|---|
| W-10 | Mola pneumática Ø50, curso 70, 1 dobra | 4 | 0,30 | 150 | FAIXA |
| W-11 | Compressor 12 V, 100 % ciclo, ~35 L/min | 1 | 2,20 | 300 | FAIXA |
| W-12 | Reservatório 2 L, alumínio | 1 | 1,60 | 290 | FAIXA |
| W-13 | Válvula solenoide 3/2, 12 V | 4 | 0,18 | 300 | FAIXA |
| W-14 | Sensor de altura | 2 | 0,09 | 200 | FAIXA |
| W-15 | Secador / filtro coalescente | 1 | 0,35 | 295 | FAIXA |
| W-16 | Linhas PU Ø6, conexões, manifold | 1 | 0,70 | 280 | ESTIMATIVA |
| W-17 | Controlador de nível + chicote | 1 | 0,30 | 300 | ESTIMATIVA |
| W-18 | Suporte do fole, superior e inferior (chapa 6) | 8 | 0,16 | 170 | ESTIMATIVA |

---

## 9 · Ganhos

1. **Vão livre ajustável.** Os 150 mm da baseline são um compromisso — alto para
   transpor, baixo para o CG. Com ar deixa de ser: sobe no carreador, desce na linha.
2. **Isolamento de vibração para a óptica.** São 8 OAK-D e 1 LiDAR; o caderno já
   especifica coxins no LiDAR (G-08) e 1ª frequência ≥ 7,5 Hz no mastro. O fole filtra a
   excitação **na origem**, antes de chegar ao mastro de 1,78 m. **Provavelmente o maior
   ganho técnico**, e mensurável: borrão de movimento e ruído de nuvem de pontos.
3. **Nivelamento.** Chassi nivelado mantém o mastro na vertical, preserva o campo das
   câmeras laterais e simplifica a extrínseca. Hoje a inclinação do terreno entra direto
   na pose de cada câmera.
4. **Quatro rodas no solo** com controle de carga por roda.

---

## 10 · Requisitos de controle

| Requisito | Por quê |
|---|---|
| Nivelamento automático | parado e em marcha, sem o operador |
| Duas alturas selecionáveis | "transporte" (alta) e "inspeção" (baixa, CG mínimo) |
| **Monitoramento de ciclo do compressor** | ciclo acima do esperado **é vazamento** — o modo de falha mais comum e o mais fácil de pegar cedo. A plataforma já tem para onde mandar: `device.fault` na trilha |
| **Modo de falha seguro** | perda de pressão apoia em **batente mecânico**, não deixa a carroceria no chão. Batente é requisito |
| **Altura na telemetria** | a altura muda a geometria de captura. Sem registrá-la, duas inspeções na mesma linha não são comparáveis. O SaaS já aceita campo livre em `sensors` |
| Travamento durante a captura | fole livre isola vibração; fole travado dá referência geométrica estável. **Objetivos opostos** — escolha de aplicação |

---

## 11 · Riscos e pendências novas

| # | Pendência | Situação |
|---|---|---|
| **P-12** | **Os 8 casos de carga do FEA foram escritos para suspensão rígida.** As condições de contorno mudam: o apoio deixa de ser nos 4 furos Ø88 e passa a ser a rigidez do fole. **Precisam ser reescritos antes de rodar** | bloqueante |
| **P-13** | Escolher modelo comercial dos 9 componentes e levantar massa real | bloqueia a massa final |
| **P-14** | Decidir rolagem: rígida (proposta) ou pneumática | §6 |
| **P-15** | Fadiga da S-02 com carregamento cíclico | reforça a sugestão 2.4 |
| **P-16** | Desenhar foles, suportes W-18 e roteamento pneumático | nada disso existe |
| **P-17** | Travar ou não as válvulas durante a captura | §10 |
| P-05 | Consumo comprometido do barramento 12 V | agora com o pico de 180 W do compressor |
| **P-02** | **Massa oficial** | de bloqueante a **crítica**: 122,79 kg contra baseline de 97,8 |
