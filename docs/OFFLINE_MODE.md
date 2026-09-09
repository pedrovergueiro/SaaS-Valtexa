# Modo offline

A lavoura tem sombra de sinal. Um sistema que só funciona com 4G não funciona.

O princípio: **o robô já tem tudo que precisa quando a missão começa**. Ele não
pede autorização em tempo real; recebe uma missão assinada, com o polígono e as
políticas dentro, e opera por ela.

---

## Estados de enlace

| Estado | Quando | Onde |
|---|---|---|
| `ok` | contato há menos de 1 min | `Device.connectivity` |
| `degraded` | entre 1 e 5 min | idem |
| `offline` | mais de 5 min | idem; publica `device.offline` |

O robô mantém a própria noção, que é a que vale para decidir.

---

## Política embarcada

Vai na missão, em `offline_policy`:

```json
{"grace_seconds": 300, "on_link_loss": "continue",
 "stop_application": false, "after_grace": "continue"}
```

| Missão | `grace` | Ao perder o enlace | Depois da carência |
|---|---|---|---|
| `scout` | 300 s | continuar | continuar |
| `spray` | 30 s | **pausar e fechar o bico** | voltar à base |

A diferença é a assimetria de risco. O rover não aplica nada: operar sem nuvem é
seguro. Aplicação é a única ação irreversível do sistema, e é a última que se
deixa seguir às cegas.

Ações possíveis: `continue`, `pause`, `return_to_base`, `land`, `abort`.

---

## O que o robô decide sozinho

Sempre, com ou sem enlace:

1. **retorno por energia** — política em `energy_policy`, avaliada a bordo;
2. **contenção no polígono** — verificada a cada ponto;
3. **parada por falha** — sensor, motor, RTK;
4. **pouso de emergência** — abaixo de `emergency_percent`.

Nenhuma delas espera resposta. Um drone com 12% de bateria e sem sinal esperando
a nuvem responder cai.

A nuvem **acompanha**: recebe a telemetria e usa para saber se a política está
calibrada — um robô que sempre volta com 45% está desperdiçando missão; um que
volta com 8% está com a reserva mal dimensionada.

---

## Buffer e sincronização

Enquanto offline, o robô acumula em memória não volátil: telemetria, eventos e
imagens. **Nada é descartado por falta de conexão** — é o erro mais caro do
sistema.

```
POST /v1/device/sync
{"sync_id": "sync-2026-09-09-01", "samples": [...], "events": [...]}
```

Resposta: `{"accepted": n, "duplicated": n, "rejected": n, "errors": []}`.

### Idempotência

Chave: `(device_id, sequence_number)`. O robô mantém **um contador monotônico
para tudo** — telemetria, eventos e observações — que nunca reinicia.

Reenviar o mesmo lote é seguro e **esperado**: a conexão cai no meio da descarga,
e reenviar é o comportamento correto do firmware. O que já entrou volta em
`duplicated`, não em erro.

### Por que a sequência retrógrada é aceita

O servidor **não** recusa sequência menor que a marca d'água.

Um lote preso offline chega fora de ordem, e é dado legítimo. Recusar jogaria
fora exatamente o que a sincronização existe para recuperar. A marca d'água
`Device.last_sequence_number` só sobe, e serve para observabilidade — não para
rejeitar.

### Conflitos

Não há: os registros do robô são **imutáveis depois de aceitos**. Telemetria e
evento são fatos com horário, não estado mutável, então não existe "quem ganha".

O que pode divergir é o estado da **missão** — o robô achando que está em
execução e a nuvem tendo abortado. Nesse caso vale a nuvem: o robô descobre no
próximo `GET /v1/device/missions/current`, que devolve `204`, e para.

---

## Capacidade

`supports_offline_mission` no descritor do modelo. Um dispositivo que não declara
não recebe missão longa. Hoje: rover e drone sim, dock não (ela não sai do lugar).

---

## O que ainda falta

- **compressão do lote de sincronização** — 4 h de telemetria a 1 Hz são ~14 mil
  amostras;
- **prioridade na descarga**: eventos críticos deveriam subir antes da telemetria
  de rotina;
- **limite de buffer**: o que descartar quando a memória do robô encher. Hoje é
  decisão do firmware, sem orientação da plataforma;
- **atualização de política sem missão nova**: hoje a política só chega junto com
  a missão.
