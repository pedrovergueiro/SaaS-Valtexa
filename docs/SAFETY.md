# Camada de segurança

O `safety_engine` decide se algo **pode** acontecer no mundo físico. É o último
antes do hardware e o único cuja aprovação é obrigatória.

Código: [`valtexa/services/safety_engine.py`](../valtexa/services/safety_engine.py).
Testes: [`tests/test_safety.py`](../tests/test_safety.py) — um por bloqueio.

---

## Três propriedades estruturais

**1. Independente.** Não importa `decision_engine`. Se a regra agronômica ficar
errada, a segurança continua íntegra. A dependência é unilateral de propósito, e
isso é verificável: o `import` não existe.

**2. Relê tudo do banco.** Nenhum valor chega por parâmetro — nem o produto, nem
o polígono, nem quem aprovou. Um chamador comprometido não consegue mentir sobre
o que vai ser executado, porque não é ele quem conta.

**3. Falha fechada.** Dado ausente é bloqueio, não exceção. Sem leitura de vento,
não pulveriza. Sem leitura de bateria, não decola. Não é conservadorismo
gratuito: a alternativa é liberar "porque não deu para verificar", que é como
acidente acontece.

Uma quarta, de operação: **o parecer é gravado mesmo quando aprova.** Um
histórico só de bloqueios não permite auditar por que algo *passou*.

---

## Como usar

```http
POST /v1/missions/{id}/authorize          # avalia, grava e autoriza ou bloqueia
POST /v1/missions/{id}/safety/preview     # avalia sem mudar nada
GET  /v1/missions/{id}/safety             # histórico completo
```

O `preview` existe para o operador ver o que falta enquanto ainda monta a
missão, sem sujar o histórico com bloqueios de rascunho.

Todas as verificações rodam sempre, e o parecer traz a lista inteira — o
operador precisa ver tudo que falta de uma vez, não descobrir um impedimento por
tentativa.

---

## As verificações

### Sempre

| Código | Bloqueia quando |
|---|---|
| `mission_state` | a missão não está em `draft`, `pending_safety` ou `blocked` |
| `mission_not_expired` | a validade já passou |
| `device_exists` | o dispositivo não existe |
| `device_tenant` | o dispositivo é de outro cliente |
| `device_active` | o status não é `active` |
| `device_kind` | rover em missão de pulverização, ou drone em varredura |
| `device_capability` | o hardware não declara o que a missão exige |
| `device_free` | o robô já tem outra missão em curso |
| `battery` | bateria abaixo de `SAFETY_MIN_BATTERY_PERCENT`, **ou sem leitura** |
| `geometry_valid` | o polígono é degenerado ou tem coordenada impossível |
| `geofence` | a área da missão não cabe no talhão, com a margem |

### Só em pulverização

| Código | Bloqueia quando |
|---|---|
| `rtk` | a última telemetria não tem `rtk_fix: fixed`, ou não há telemetria |
| `approval` | não há aprovação humana registrada |
| `approver_role` | quem aprovou **não é mais** agrônomo |
| `product_present` | missão sem produto, ou produto de outro cliente |
| `product_active` | o produto está suspenso ou vencido |
| `product_registered` | falta o número de registro no MAPA |
| `product_crop` | a cultura do talhão não está entre as autorizadas |
| `rate_range` | a dose está fora da faixa de bula |
| `batch_valid` | lote inexistente, de outro produto, ou vencido |
| `tank_present` / `tank_device` | tanque ausente, de outro cliente, ou de outro robô |
| `tank_content` | o conteúdo do tanque **diverge** do produto/lote autorizados |
| `tank_volume` | volume insuficiente para a quantidade autorizada |
| `weather` | vento acima do limite, **ou sem leitura** |

---

## As três que mais importam

### `tank_content`

Impede a pior falha possível do sistema: **aplicar o produto errado numa área
autorizada para outro**. A missão declara o produto; o registro de carga
(`POST /v1/tanks/{id}/load`) declara o que está fisicamente dentro; a segurança
compara.

Sem esse elo, a plataforma não teria como saber o que há no drone — e
"provavelmente é o certo" não é uma resposta aceitável quando o resultado é
químico no ar.

### `approver_role`

O papel é reconferido **no momento da autorização**, não confiado ao momento em
que a aprovação foi registrada. Entre a assinatura do agrônomo e o voo, o papel
dele pode ter sido revogado — e uma autorização assinada por quem já não é
agrônomo não vale.

### `weather`

O único bloqueio que costuma incomodar num piloto: sem dock instalada, nenhuma
pulverização é autorizada. É intencional. A leitura vem da dock, que fica parada
no talhão — ver [`DOCK_INTEGRATION.md`](DOCK_INTEGRATION.md).

Um limite de bula (`Product.max_wind_ms`) **aperta** o limite global; nunca o
afrouxa.

---

## Cerca virtual

Duas semânticas de borda, deliberadamente diferentes:

| Pergunta | Regra na borda | Por quê |
|---|---|---|
| *onde o robô está* (`contains_point`) | borda = **fora** | na dúvida, o lado conservador |
| *se uma área cabe em outra* (`polygon_contains_polygon`) | borda = **dentro** | uma missão sobre a área permitida está contida nela |

Sem essa distinção, ou a cerca ficaria ambígua na borda (dependendo da ordem dos
vértices), ou toda missão que usa a área máxima disponível seria bloqueada por
construção.

A margem real vem de `GEOFENCE_MARGIN_M` (padrão 5 m), aplicada por
`geo.shrink()` **sempre para dentro**. Uma missão criada sem polígono explícito
já nasce sobre o talhão encolhido: a área operável é o miolo, não a borda exata.

O encolhimento é uma aproximação de *buffer* negativo em direção ao centroide —
exata em polígono regular, conservadora nos demais. O erro sempre **reduz** a
área permitida.

---

## Duas verificações, dois lugares

| | Nuvem | Robô |
|---|---|---|
| Quando | antes de assinar | a cada ponto, em tempo real |
| O que sabe | produto, lote, papel, histórico | posição real, nível de tanque, vento local |
| Vale sem enlace | não | **sim** |

A nuvem verifica o que só ela sabe; o robô verifica o que só ele sabe. Nenhuma
das duas substitui a outra, e a do robô é a que continua valendo quando a nuvem
sai do ar. Detalhes em [`DRONE_INTEGRATION.md`](DRONE_INTEGRATION.md), seção 9.

---

## Mudando uma regra

1. o código do teste (`safety_engine.CODIGO`) é **estável** — ele aparece no
   banco, na auditoria e na tela do operador; renomear quebra o histórico;
2. suba `ENGINE_VERSION`;
3. escreva o teste **antes**: `tests/test_safety.py` tem um por bloqueio;
4. um bloqueio novo pode parar operação em produção — combine antes, não depois.
