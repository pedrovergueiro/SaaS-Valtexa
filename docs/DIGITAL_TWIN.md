# Gêmeo digital

O gêmeo aqui **não é um modelo 3D**. É a resposta a duas perguntas que a lavoura
responderia mal sozinha:

- *o que existe onde* — cada observação amarrada a um ponto e a um instante;
- *o que mudou desde a última passada* — a série temporal.

Código: [`valtexa/services/twin.py`](../valtexa/services/twin.py).

---

## Hierarquia

```
Tenant
 └── Farm
      └── Field (talhão: cultura, estágio, limite)
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

1. **Não há identidade de planta.** `Observation.plant_ref` existe no esquema e
   fica nulo — falta o rastreamento visual que reconheça a mesma planta entre
   passadas. Hoje a agregação é por zona.
2. **Não há severidade.** Os modelos classificam, não quantificam. A série mede
   *quantas plantas* mostram sintoma, não *quanto* de cada folha está afetado.
3. **A anomalia não usa sazonalidade.** Ferrugem aumenta naturalmente em certos
   estágios; a linha de base é do próprio talhão nas semanas anteriores, o que
   absorve parte disso, mas não modela o ciclo da cultura.
4. **Não há dado de ambiente integrado.** Chuva, temperatura e molhamento foliar
   explicam boa parte da variação e ainda não entram na análise.
