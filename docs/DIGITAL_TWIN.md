# Gêmeo digital

O gêmeo tem duas camadas, e cada uma responde a uma pergunta que a lavoura
responderia mal sozinha:

- **a cópia 3D** — *como está cada rua*: o rover monta, passada a passada, uma
  cópia do talhão com cada planta medida, e as fotos com praga ou doença ficam
  presas à planta fotografada;
- **a série** — *o que mudou desde a última passada*: incidência por zona no
  tempo, e os desvios que nenhuma foto sozinha denuncia.

Código: [`valtexa/services/scene.py`](../valtexa/services/scene.py) (cópia 3D) e
[`valtexa/services/twin.py`](../valtexa/services/twin.py) (série e anomalias).

---

## Cópia 3D

```
rover anda pela rua ──► LiDAR/estéreo mede as linhas dos dois lados
                         │
                         ├─ plantas: posição, altura, copa, índice de verde
                         └─ nuvem de pontos da faixa (PLY)
                                        │
POST /v1/device/row-scans ──────────────┘   (uma passada por rua)
                                        │
GET /v1/fields/{id}/scene  ◄── a cópia: a passada mais nova de cada faixa
                                + fotos diagnosticadas presas às plantas
```

### Como a cópia é composta

Cada passada cobre uma faixa — o eixo percorrido mais o alcance do sensor para
cada lado (`reach_m`). A cópia é a sobreposição das faixas, **a mais recente por
cima**. Uma passada nova substitui o que havia na faixa dela, inclusive a
ausência: a planta que foi arrancada, acamou ou foi colhida some da cópia na
próxima passada, em vez de ficar congelada para sempre.

O que nenhuma passada cobriu **fica vazio**, e `coverage_ratio` diz quanto do
talhão já tem cópia. É deliberado: preencher o talhão com plantas prováveis
transformaria a cópia numa ilustração, e o produtor decidiria olhando para algo
que ninguém mediu.

`?at=` devolve a cópia como ela estava num instante — o console mostra isso como
"estado em", por dia de passada.

### Praga e doença na cópia

Cada foto diagnosticada vira um marcador preso à **planta fotografada** (a mais
próxima, até 60 cm), com a categoria que vale:

| Categoria | Quando |
|---|---|
| `pest` | rótulo de praga — do modelo (dano do bicho-mineiro) ou do agrônomo |
| `disease` | rótulo de doença validado pela IA ou confirmado |
| `review` | a dupla validação não fechou e o agrônomo ainda não olhou |
| `other` | achado do agrônomo fora das duas listas (deficiência, granizo) |
| `healthy` | foto sem sintoma |

A lista está em [`services/taxonomy.py`](../valtexa/services/taxonomy.py).
Enquanto a foto espera o agrônomo, a categoria é `review` mesmo que a máquina
tenha arriscado um rótulo — mostrar "doença" ali daria ao palpite recusado o
peso de um diagnóstico.

**Praga que nenhum modelo conhece chega pela fila.** A folha comida pela
lagarta-do-cartucho sai do modelo de milho como um palpite de doença com
novidade alta; vai para o agrônomo, que escreve `Spodoptera_frugiperda`, e é
esse rótulo que põe a praga na cópia. O simulador percorre exatamente esse
caminho.

**Nada é diagnosticado por vizinhança.** A planta ao lado de uma ferrugem não
ganha ferrugem na cópia. O que a cópia mostra de *todas* as plantas é o que o
sensor mediu em todas: altura, copa e o índice de verde, que acusa clorose e
lesão sem dizer a causa — e é por ele que uma reboleira aparece antes de alguém
fotografá-la.

### Rotas

```
POST /v1/device/row-scans            o rover envia uma passada (assinado)
GET  /v1/fields/{id}/scene?at=&days= a cópia do talhão
GET  /v1/fields/{id}/row-scans       as passadas, da mais recente
GET  /v1/row-scans/{id}/pointcloud   a nuvem de pontos da passada, sem conversão
```

O formato da passada e da nuvem está em
[`ROVER_INTEGRATION.md`](ROVER_INTEGRATION.md#10-cópia-3d--uma-passada-por-rua).
Cada passada publica `row_scan.received`; o console atualiza a cópia aberta
sem recarregar, rua a rua.

### O que a cópia não é

- **Não é fotogrametria.** As plantas no console são símbolos dimensionados pela
  medida de cada uma; a forma real está na nuvem de pontos, que o console abre
  por rua.
- **Não tem identidade de planta entre passadas** além da posição: com RTK, a
  mesma posição é a mesma planta. Sem RTK a composição ainda funciona, mas duas
  passadas podem desenhar a mesma planta a alguns centímetros uma da outra.
- **Não foi calibrada contra medição manual.** Altura e copa são as do sensor;
  comparar com régua no campo é o primeiro teste do hardware.

---

## Hierarquia

```
Tenant
 └── Farm
      └── Field (talhão: cultura, estágio, limite)
           ├── RowScan (uma passada por rua: plantas medidas + nuvem de pontos)
           └── Zone (unidade de manejo)
                └── Observation (ponto + instante + imagem)
                     ├── Detection   (palpite de cada analisador)
                     ├── Diagnosis   (resultado da dupla validação)
                     └── Decision    (recomendação)
                          └── Mission -> Application -> Verification
```

A **zona** é onde a aplicação localizada acontece. O motor de decisão recomenda
por zona, não pelo talhão inteiro — é isso que separa este produto de uma
pulverização em área total.

---

## Rotas

```
GET /v1/fields/{id}/snapshot?days=7      retrato da janela
GET /v1/fields/{id}/timeline?days=30     série diária
GET /v1/fields/{id}/anomalies            desvios estatísticos
```

### `snapshot`

```json
{"field_name": "Talhão A — Milho", "crop": "corn",
 "observations": 248, "diagnosed": 240, "needs_review": 31,
 "classes": [{"label": "Healthy", "count": 180, "ratio": 0.75},
             {"label": "Common_Rust", "count": 48, "ratio": 0.20}]}
```

`needs_review` é a fila do agrônomo naquele talhão. É um número operacional: é o
orçamento de tempo que alguém vai precisar gastar.

### `timeline`

Série diária por rótulo. **É a informação que muda a decisão do produtor.** Uma
foto diz que há ferrugem; a série diz que a incidência saiu de 4% para 31% em
nove dias — e as duas frases levam a decisões diferentes.

---

## `anomalies` — a detecção que funciona quando a novidade falha

Esta é a rota mais importante do módulo, e existe por causa de um número medido.

Em `VALTEXA-B/MODELS.md`: diante de uma doença real fora do catálogo, o modelo
respondeu com **0,88 de confiança média**, e os filtros de novidade e confiança
juntos interceptaram **19%** dos casos. **Uma imagem por vez, não há como
notar** — a resposta é confiante, plausível e errada.

O que o erro **não** consegue esconder é a estatística. Uma doença nova
classificada consistentemente como "ferrugem comum" faz a ferrugem comum daquele
talhão saltar de 5% para 40% de uma semana para a outra.

```json
[{"label": "Common_Rust",
  "baseline_ratio": 0.05, "current_ratio": 0.41,
  "baseline_sample": 210, "current_sample": 96,
  "detail": "Common_Rust: 5.0% → 41.0% em 7 dias. Vale uma inspeção presencial."}]
```

### Como decide

Compara a janela recente (padrão 7 dias) com a linha de base (30 dias
anteriores), por zona. Aponta quando:

- há amostra suficiente — `BASELINE_MIN_SAMPLE` (30) na base;
- a incidência atual passa de `ANOMALY_FLOOR` (10%);
- e cresceu `ANOMALY_RATIO` (3×), **ou** a classe não existia na base.

Os três critérios juntos, e não cada um isolado. Sem piso, 1% virando 3% viraria
alarme; sem amostra mínima, a variação normal de amostragem dispararia toda
semana; sem razão de crescimento, um talhão cronicamente afetado alarmaria para
sempre.

### O que ela não faz

**Não diz o que mudou.** Diz que mudou, e manda um agrônomo olhar.

Para o modo de falha que ela cobre — o modelo respondendo com confiança sobre
algo que nunca viu — isso é suficiente. Uma resposta errada e confiante numa
imagem é invisível; um talhão que muda de comportamento não é.

---

## Verificação pós-tratamento

```
Application -> Verification (agendada) -> segunda passada -> comparação
```

A regra central é negativa: **nada é declarado eficaz sem evidência**.

- a verificação nasce `PENDING` e respeita o intervalo de reentrada do produto
  (mandar o rover antes do prazo expõe o equipamento a resíduo);
- amostra insuficiente vira `INCONCLUSIVE`, **nunca `UNCHANGED`**. "Não mudou" é
  um resultado; "não sei" é a ausência dele, e confundir os dois inventaria
  eficácia onde não há medida;
- a eficácia é a redução relativa da incidência do alvo tratado na zona, entre a
  janela anterior e a posterior.

Declarar sucesso por padrão seria a forma mais rápida de queimar a confiança do
produtor, porque ele vai até o talhão e olha.

---

## Limitações

1. **Identidade de planta só por posição.** A cópia 3D prende cada foto à
   planta medida mais próxima, e com RTK a mesma posição é a mesma planta. Falta
   o rastreamento visual que reconheça a planta sem RTK; `Observation.plant_ref`
   continua nulo, e a série agrega por zona.
2. **A severidade é área no quadro.** O modelo de segmentação mede a fração da
   foto com lesão — aproxima a folha só quando ela preenche a imagem, e ainda
   não foi comparada com a escala de um fitopatologista. Por isso fica fora da
   série e da decisão.
3. **A anomalia não usa sazonalidade.** Ferrugem aumenta naturalmente em certos
   estágios; a linha de base é do próprio talhão nas semanas anteriores, o que
   absorve parte disso, mas não modela o ciclo da cultura.
4. **Não há dado de ambiente integrado.** Chuva, temperatura e molhamento foliar
   explicam boa parte da variação e ainda não entram na análise.
