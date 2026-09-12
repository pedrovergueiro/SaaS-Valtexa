# Eventos

Dois vocabulários diferentes, que é fácil confundir:

| | Eventos de domínio | Eventos de dispositivo |
|---|---|---|
| Origem | a plataforma | o robô |
| Tabela | `outbox_event` | `device_event` |
| Nome | `mission.authorized` | `low_battery` |
| Para quê | acionar handlers, integrações | registrar o que aconteceu em campo |

---

## Eventos de domínio — *outbox* transacional

O evento é gravado na **mesma transação** que mudou o estado. Ou os dois
acontecem, ou nenhum.

```
transação:  estado alterado  +  outbox_event
                                     │
                          drenador (thread ou worker)
                                     │
                                 handlers
```

Sem isso, um processo que morre entre "missão autorizada" e "avisar quem
interessa" deixaria o sistema num estado que ninguém observou — e a verificação
pós-tratamento nunca seria agendada.

**A entrega é ao-menos-uma-vez.** Um processo que morre entre entregar e marcar
como entregue vai entregar de novo. Todo handler precisa ser idempotente — um
handler não idempotente aqui vira aplicação duplicada no campo.

### Vocabulário

| Nome | Quando |
|---|---|
| `observation.created` | imagem recebida e armazenada |
| `diagnosis.created` | pipeline concluído |
| `diagnosis.validated` | duas análises independentes concordaram |
| `diagnosis.needs_review` | foi para a fila do agrônomo |
| `diagnosis.reviewed` | agrônomo deu o veredito |
| `novelty.detected` | novidade acima do limiar |
| `decision.created` | motor de decisão emitiu recomendação |
| `safety.approved` / `safety.blocked` | parecer da camada de segurança |
| `mission.created` / `.authorized` / `.dispatched` | ciclo da missão |
| `mission.started` / `.paused` / `.resumed` | execução |
| `mission.completed` / `.aborted` | fim |
| `mission.expired` | a validade venceu antes de a execução começar (worker) |
| `application.started` / `.completed` | bico aberto e fechado |
| `application.out_of_bounds` | **ponto da trilha fora do polígono** |
| `verification.scheduled` / `.completed` | verificação pós-tratamento |
| `device.provisioned` | robô entrou na frota |
| `device.offline` | passou de 5 min sem contato |
| `device.fault` | evento crítico do dispositivo |
| `row_scan.received` | o rover enviou uma passada por rua; a cópia 3D mudou |

Um nome novo entra em `valtexa/services/events.py` **e aqui**, nunca só na
chamada.

### Escrevendo um handler

```python
from valtexa.services import events

@events.on(events.APPLICATION_COMPLETED)
def agendar_inspecao(session, event):
    # Idempotente: a entrega é ao-menos-uma-vez.
    if ja_existe(session, event.subject_id):
        return
    ...
```

Um handler que levanta não impede a entrega dos demais nem faz o lote voltar para
a fila: o erro fica em `last_error` e o evento é tentado de novo, até
`MAX_ATTEMPTS` (8). Depois disso ele para de ser tentado e fica visível como
falha — repetir para sempre um evento quebrado transformaria a fila num laço
infinito que atrasa todos os outros.

### Operando

```
GET /v1/events?pending_only=true
```

Um evento parado com `last_error` preenchido é a primeira pista de que uma
integração quebrou. Quem drena é o worker (`python -m valtexa.worker`), a cada
5 s — numa thread da API em desenvolvimento, num processo à parte em produção.
Ver [`DEPLOYMENT.md`](DEPLOYMENT.md).

O console recebe os mesmos eventos por SSE em `GET /v1/stream` — ver
[`API.md`](API.md#tempo-real).

---

## Eventos de dispositivo

O que o robô relata. Diferente da telemetria: telemetria é amostragem contínua e
descartável em agregação; **evento é o que precisa sobreviver íntegro para a
auditoria**.

```json
POST /v1/device/events
{"events": [{
  "sequence_number": 1043,
  "type": "low_battery",
  "severity": "warning",
  "occurred_at": "2026-09-09T03:01:00+00:00",
  "mission_id": "…",
  "payload": {"battery_percent": 18.0}
}]}
```

### Vocabulário sugerido

| `type` | Severidade | Origem |
|---|---|---|
| `mission_started` / `_paused` / `_resumed` / `_completed` | info | rover, drone |
| `low_battery` | warning | rover, drone |
| `return_to_base` | warning | rover, drone |
| `emergency_return` | critical | drone |
| `obstacle_detected` | warning | rover |
| `rtk_lost` | warning | rover, drone |
| `communication_lost` | warning | todos |
| `emergency_stop` | critical | todos |
| `application_started` / `_stopped` | info | drone |
| `application_blocked_geofence` | **critical** | drone |
| `tank_mismatch` | critical | drone |
| `wind_exceeded` | warning | drone, dock |
| `takeoff` / `landed` | info | drone |
| `device_docked` / `_undocked` | info | dock |
| `battery_swapped` | info | dock |
| `charging_started` / `_completed` | info | dock |
| `refill_started` / `_completed` | info | dock |
| `fault_detected` | critical | todos |

Severidade `critical` publica automaticamente `device.fault` no barramento de
domínio.

Tipos fora desta lista são aceitos e gravados — o campo é livre de propósito, um
robô novo pode ter estados que não previmos. Mas um tipo que interessa ao resto
do sistema precisa entrar aqui **e** ganhar um handler.

---

## Retenção

| Tabela | Política |
|---|---|
| `outbox_event` | o worker remove os entregues com mais de 30 dias |
| nonces de requisição | o worker remove os vencidos (`NONCE_RETENTION_SECONDS`) |
| `device_event` | mantido; é registro operacional |
| `audit_entry` | **nunca removido** |
| `telemetry_sample` | agregada por minuto depois de `TELEMETRY_RETENTION_DAYS` — ver [`TELEMETRY.md`](TELEMETRY.md) |
