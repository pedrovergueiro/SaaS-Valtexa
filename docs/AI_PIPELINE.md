# Pipeline de IA e os limites medidos

Este é o documento mais importante do repositório para quem for confiar no
sistema. Ele descreve o que a IA faz, e — com números — o que ela **não** faz.

Código: [`valtexa/services/ai_pipeline.py`](../valtexa/services/ai_pipeline.py).

---

## 1. O limite, medido

Em `VALTEXA-B`, um modelo de 3 classes (`Blight`, `Common_Rust`, `Healthy`) foi
treinado com `Gray_Leaf_Spot` **retida** — 2.015 imagens de uma doença real de
milho que ele nunca viu. O modelo era competente: acurácia 0,9531 e macro-F1
0,9414 nas classes que conhecia.

Diante de 400 imagens da doença retida:

```
o que ele respondeu:
   Common_Rust    186 (46%)   confiança média 0,890
   Blight         174 (44%)   confiança média 0,890
   Healthy         40 (10%)   confiança média 0,795

64% com confiança acima de 0,90

interceptado:
   novidade (limiar 1,0)   →   4%
   MIN_CONFIDENCE (0,70)   →  17%
   os dois juntos          →  19%
```

**81% passaria como diagnóstico confiante e errado.**

O contraste que explica o mecanismo: uma deficiência de magnésio (clorose
internerval, padrão de mosaico) foi interceptada em **75%** dos casos. Ela é
*visualmente* diferente de tudo que o modelo aprendeu. A cercosporiose é
exatamente o vocabulário dele — mancha escura em folha de milho. Ela não parece
estranha; parece uma das gavetas que ele já tem.

### O que isso significa

**A detecção de novidade não é rede de segurança para doença nova.** Ela serve
para o que é visualmente estranho: colmo no lugar de folha, deficiência
nutricional, foto ruim, enquadramento errado. Não serve para uma patologia
foliar ainda não catalogada.

Existe sinal, mas é fraco: score médio 0,65 na doença nova contra 0,55 no dado
conhecido. As distribuições se sobrepõem quase inteiramente — a 0,8 pega 16% e
já marca 3,7% da lavoura boa. Não há limiar que resolva.

Toda a arquitetura em volta existe por causa desse número.

---

## 2. As quatro barreiras construídas em cima disso

| Barreira | Onde | O que cobre |
|---|---|---|
| Amostra mínima | `decision_engine.MIN_SAMPLE` + incidência | erro pontual não vira ação |
| Independência medida | `combine()` exige par independente para validar | concordância correlacionada não vale |
| Anomalia no talhão | `services/twin.anomalies` | **o que a novidade não pega** |
| Fila do agrônomo | `/v1/review/queue` | rótulo novo entra no dataset |

A terceira é a que realmente responde ao limite acima. Uma doença nova
classificada consistentemente como "ferrugem comum" é invisível quadro a
quadro — mas faz a ferrugem comum daquele talhão sair de 5% para 40% de uma
semana para a outra. Ela não olha a imagem, olha a distribuição. Ver
[`DIGITAL_TWIN.md`](DIGITAL_TWIN.md).

---

## 3. Dupla validação

Uma observação passa por *N* analisadores e vira um `Diagnosis`.

```
imagem ──┬──► IA A ──┐
         └──► IA B ──┴──► combine() ──► Diagnosis
```

### As regras, na ordem em que decidem

1. menos de duas análises úteis → `NEEDS_REVIEW` (uma opinião só nunca valida);
2. qualquer uma abaixo de `MIN_CONFIDENCE` → `INCONCLUSIVE`;
3. rótulos diferentes → `NEEDS_REVIEW` (a discordância é o sinal);
4. novidade acima do limiar → `NEEDS_REVIEW`, **mesmo com as duas concordando**;
5. concordância frágil (confianças distantes) → `NEEDS_REVIEW`;
6. par não independente → `NEEDS_REVIEW` (concordância correlacionada não valida);
7. resto → `AI_VALIDATED`.

Duas notas sobre o desenho:

- **um analisador que falhou nunca conta como concordância.** Erro de rede não
  pode virar "os dois concordaram";
- **a confiança reportada é a menor do par.** Validar por consenso e depois
  reportar o número mais otimista apagaria justamente a dúvida que a segunda
  análise existe para revelar.

### Severidade — medida, não votada

O serviço de inferência devolve, junto com a classe, a fração do quadro marcada
como lesão por um modelo de segmentação (`VALTEXA-B`, `MODELS.md#severidade`).
Ela vai para `Diagnosis.severity` sem passar pelo combinador: é medida de área,
não opinião sobre o rótulo, e os dois analisadores a recebem do mesmo modelo.

No teste que o modelo nunca viu, o erro médio é de 7,6 pontos percentuais do
quadro, com correlação 0,89 com a máscara; nas folhas saudáveis, a lesão falsa
média foi 0,01%. Duas ressalvas mantêm o número **fora da regra de decisão**: é
área no quadro, não na folha (aproxima a folha só quando ela preenche a
imagem), e ainda não foi comparada com a escala diagramática de um
fitopatologista. Até lá, é informação para o agrônomo — o console mostra a área
lesionada na fila e na foto da observação.

### `AI_VALIDATED` não é autorização

É só o estado em que duas análises independentes chegaram à mesma resposta com
confiança suficiente. O que pode virar ação é decidido depois, por regra
determinística; o que pode acontecer fisicamente, depois ainda, pelo safety
engine.

---

## 4. Independência — medida

Duas cópias correlacionadas do mesmo modelo **concordariam com a mesma resposta
errada** e produziriam uma falsa sensação de validação. Por isso cada analisador
declara `independent`, e um par sem independência **nunca** chega a
`AI_VALIDATED`: a concordância vai para a fila do agrônomo, com o motivo
"concordância correlacionada não valida". O motor de decisão confere de novo
(`NOT_INDEPENDENT`) antes de qualquer recomendação de aplicação.

Convenção: um analisador cujo nome começa com `dependent:` (TTA, outro recorte,
outra resolução do mesmo peso, ou um segundo modelo não declarado independente)
não conta para independência.

### O segundo modelo

`VALTEXA-B` treinou o `leaf-foliar-b`: mesmas classes, mesmo dataset, outra
arquitetura (EfficientNetV2B0, contra a MobileNetV2 do primário). Arquitetura
diferente não prova independência — os dois aprendem dos mesmos rótulos,
inclusive dos contraditórios. Então ela foi medida, em 11/09/2026.

**Par de produção** — 4 classes, 1.978 imagens de teste que nenhum dos dois viu:

| | |
|---|---:|
| acurácia do primário (A) | 95,4% |
| acurácia do segundo (B) | 95,3% |
| discordam | 5,2% |
| acurácia quando concordam | **98,1%** |
| erros de A que a discordância pega | **60%** |
| erros de A em que B erra igual | 36 de 90 (40%) |

**Doença retida** — par de 3 classes treinado sem cercosporiose, diante de 400
imagens dela:

| O que intercepta | Fração |
|---|---:|
| confiança baixa em algum dos dois | 26,5% |
| novidade (A) | 3,5% |
| discordância entre A e B | 32,0% |
| **os três juntos** | **45,0%** |

Os dois erram diferente diante do que nunca viram: A dividiu a cercosporiose
entre ferrugem (186) e helmintosporiose (174); B puxou para helmintosporiose
(267). É o que faz da discordância o maior sinal isolado. Na medição da seção 1,
o modelo sozinho interceptava 19%.

### O que isso decide

O par **não** é independente no sentido forte: 40% dos erros do primário são
compartilhados, e 55% de uma doença nunca vista ainda passam pelos três filtros
como diagnóstico concordante. Mas também não é cópia: quando concordam, o erro
cai de 4,6% para 1,9%, e a discordância pega 60% dos erros.

Por isso a configuração padrão continua conservadora, e cada passo é explícito:

| Configuração | Efeito |
|---|---|
| `SECONDARY_MODELS=` (vazio) | um analisador; tudo vai para o agrônomo |
| `SECONDARY_MODELS=corn:leaf-foliar-b` | par; concordância e discordância aparecem no console, mas tudo continua indo para o agrônomo |
| + `SECONDARY_MODEL_INDEPENDENT=true` | a concordância entre A e B valida sozinha (`AI_VALIDATED`) |

Recomendação: o segundo passo já; o terceiro só depois de repetir esta medição
num conjunto de teste capturado pela própria frota. Os números acima são de
dataset público — e a proteção contra a doença nova que passa concordante não é o
par: é a anomalia no talhão (seção 2).

---

## 5. Cultura → versão do modelo

Cada cultura tem uma ou mais **versões** no **Model Registry** (tabela
`model_version`, `valtexa/services/model_registry.py`; até a Parte 2 era um espelho
no código, `ai_pipeline.CATALOGO`, que virou a semente do registry), com o acerto
no teste de campo e a licença dos dados de treino. Só atendem versões em
**PRODUÇÃO** e, quando a versão tem `release_scope = clientes`, só para os clientes
com liberação ativa. As chaves são as mesmas que a IA (VALTEXA-B) conhece:

| Cultura | Versão | Variante | Campo | Dados de treino |
|---|---|---|---|---|
| banana | `banana-foliar` | campo (recomendada) | 82,9% | CC BY + PlantSeg CC BY-NC |
| banana | `banana-foliar-cc` | comercial | 59,2% | só CC BY |
| citros | `citrus-foliar` | campo (recomendada) | 96,9% | CC BY + PlantSeg CC BY-NC |
| citros | `citrus-foliar-cc` | comercial | 69,5% | só CC BY |

"Campo" é o recorte de lesão do PlantSeg na escala do rover, que o modelo nunca
viu (VALTEXA-B/MODELS.md). A variante comercial existe porque o PlantSeg é não
comercial; ela erra mais no campo, e o seletor mostra isso ao lado.

A versão usada numa análise sai, nesta ordem:

1. a escolhida no talhão (`PUT /v1/fields/{id}/ai-model`, `farm:manage`,
   auditado como `field.ai_model_changed`);
2. `PRIMARY_MODELS` (ex.: `banana:banana-foliar-cc,citrus:citrus-foliar-cc`),
   para trocar a versão de todos os talhões de uma cultura sem mexer em cada um;
3. a recomendada entre as versões em produção liberadas para o cliente.

`GET /v1/fields/{id}/ai-models` lista as versões para o seletor, com a que está
em uso marcada. Uma versão de outra cultura é recusada com 422.

O acerto de campo é métrica técnica: fica em `metrics` no registry, só para a
equipe. O seletor do produtor mostra o mesmo número dito em linguagem operacional
(`field_performance`: alto ≥ 90%, bom ≥ 75%, limitado abaixo).

Uma cultura fora do catálogo **não** cai num modelo padrão: o pipeline recusa a
análise. Classificar folha de soja com o modelo de milho devolveria uma das
quatro classes de milho, com confiança alta, e nada no resultado denunciaria o
erro.

---

## 6. Enquadramento

Os modelos foram treinados com **folha preenchendo o quadro**. Imagem aérea de
dossel produz resposta confiante e errada — medido: 94% "Rust" a 0,93 de
confiança, com apenas 9% interceptado.

O robô informa `model_input_ok` na observação. `false` manda direto para revisão
humana, sem alimentar um diagnóstico que nasceria errado.

Do lado da inferência, um **portão de enquadramento** (SigLIP 2, zero-shot)
julga cada imagem antes do modelo. O que ele diz vai para `Detection.signals`:

| Sinal | O que faz aqui |
|---|---|
| `in_scope: false`, `scene` | não é folha (pseudocaule, tronco, fruto): `NEEDS_REVIEW` **sem rótulo** — o modelo foliar daria uma doença de folha para qualquer coisa |
| `prediction_set` com mais de uma classe | o conjunto conformal não separa as classes: `NEEDS_REVIEW` |
| `prediction_set` vazio | nada do treino é plausível: `NEEDS_REVIEW` |

O agrônomo vê a cena e o conjunto na fila; nomear o que não é folha é de onde
sai o dataset de pseudocaule.

---

## 7. O quadro do rover e as plantas do talhão

Com `camera` no metadado da observação (`camera_height_mm`, `distance_mm`,
`side`, `x_m`, `camera_id`), a imagem não é foto de folha: é o quadro inteiro
da câmera lateral. O SaaS o manda ao `/predict/rover-frame` do VALTEXA-B, que o
corta em recortes de 150 mm na escala física e classifica cada um, sabendo a
altura e a zona da planta (pseudocaule, folhas baixas; saia, copa).

O quadro vira **uma análise**:

- rótulo: a doença mais frequente entre os recortes que o portão aceitou — uma
  lesão num recorte já é achado —, ou `Healthy`;
- `probabilities`: a **fração de recortes** de cada classe, não a confiança do
  modelo (a fila diz "recortes divididos", não "margem");
- quadro todo fora do escopo: sem rótulo, para o agrônomo;
- 25% ou mais dos recortes estranhos ao modelo (`FRAME_REVIEW_SHARE`): para o
  agrônomo, o equivalente da novidade alta numa foto só.

Com `row_index`, `side` e `x_m`, o quadro também alimenta a **fusão por
planta** no serviço de inferência: cada planta junta as câmeras e os quadros em
que apareceu num posterior por doença, com incidência e situação (`sadia`,
`suspeita`, `doente`, `revisar`). A passada é a missão; ao concluí-la, o SaaS
fecha a passada (`close_pass`) e a planta ganha o comparativo com a anterior
(`nova_infeccao`, `piora`, `melhora`...) e a AUDPC. O quadro leva
`captured_at`: um lote sincronizado depois de o enlace cair chega horas depois,
e o histórico da planta tem de ser datado pela foto.

```http
GET /v1/fields/{id}/plants                        # uma entrada por planta
GET /v1/fields/{id}/plants/map                    # GeoJSON, um ponto por planta
GET /v1/fields/{id}/plants/{plant_id}/evolution   # passadas, mudanças, AUDPC
GET /v1/fields/{id}/prevalence                    # prevalência estimada x a do treino
```

O SaaS não guarda cópia: lê da inferência, com o escopo do cliente conferido
aqui. Sem inferência (ou com ela sem `FIELDS_DIR`), as rotas respondem 503 —
estado, não falha passageira. A inferência roda **antes** de qualquer escrita
no banco: são segundos de HTTP, e uma transação aberta durante eles prenderia a
linha do robô e a telemetria dele.

A severidade da Sigatoka (escala de Stover-Gauhl, DSI) vem no resumo do quadro
com `scale_validated: false`: a escala ainda não foi validada por agrônomo, e o
console diz isso ao lado do número.

---

## 8. Da máquina ao agrônomo, e de volta ao dataset

```http
GET  /v1/review/queue?order=novidade      # o que mais destoa primeiro (padrão)
GET  /v1/review/queue?order=valor         # o que mais ensina primeiro, com o motivo
GET  /v1/observations/{id}/image          # a foto
GET  /v1/diagnoses/{id}                   # o diagnóstico com os sinais de cada análise
POST /v1/diagnoses/{id}/review            # o veredito
```

Com `order=valor`, cada item volta com `priority_score` e `priority_reasons`
(`services/review_priority.py`): fora do escopo, discordância, incerteza,
conjunto conformal ambíguo, novidade e classe rara entre as que o agrônomo já
rotulou. É a ordem por incerteza do aprendizado ativo — no simulador, a mesma
acurácia com 30% menos rótulos que a ordem aleatória.

```json
{"label": "Gray_Leaf_Spot", "confirmed": true, "notes": "Cercosporiose."}
```

**O rótulo não precisa existir no catálogo do modelo.** É assim que uma doença
que a IA não conhecia entra no dataset próprio — e é a única correção real para
o modo de falha da seção 1.

A revisão grava uma `Detection` de origem `human`, muda o status para
`HUMAN_CONFIRMED` e **refaz a decisão** com o rótulo humano. A decisão anterior
continua no banco: apagar apagaria o porquê da recomendação antiga.

---

## 9. Versionamento

`PIPELINE_VERSION` sobe a cada mudança na regra de combinação e fica gravado em
cada diagnóstico. `Detection` guarda `model_key` e `model_version`.

Reprocessar cria linhas novas; as antigas permanecem com a versão que as
produziu. É o que permite comparar o comportamento entre versões em cima de dados
reais, em vez de acreditar na métrica de validação.

---

## 10. `SIMULATED_INFERENCE`

Substitui os modelos por analisadores falsos e determinísticos, que leem a
resposta esperada de uma marca anexada ao fim do arquivo de imagem. É o que
permite o fluxo ponta a ponta rodar sem GPU, sem rede e sem os 90 MB de pesos.

É **recusado em produção** por `Settings.production_problems()`: um diagnóstico
inventado chegando a um produtor seria pior do que não ter diagnóstico nenhum.
