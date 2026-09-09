# Integração do Rover Scout

Como o firmware do rover conversa com a plataforma. Leia junto com
[`DEVICE_PROTOCOL.md`](DEVICE_PROTOCOL.md), que tem o formato da assinatura e o
tratamento de erros.

Referência executável: [`simulator/devices.py`](../simulator/devices.py),
classe `SimulatedRover`.

---

## 1. O que o rover faz

Percorre o talhão em vaivém, fotografa a lavoura em close (folha preenchendo o
quadro) e sobe as imagens. **Não aplica nada.** É deliberado: separar quem
observa de quem age é o que permite tratar cada um com um nível de risco
diferente.

Quando a energia acaba no meio, ele volta à base, recarrega e **continua da faixa
seguinte**. Refazer a lavoura inteira tornaria o produto inviável acima de
algumas dezenas de hectares.

---

## 2. Capacidades declaradas

`ROVER_SCOUT_V1` em `valtexa/services/hal.py`:

```json
{
  "has_rtk": true, "has_camera_rgb": true, "has_lidar": true,
  "can_fly": false, "has_spray": false,
  "swath_m": 3.0, "cruise_speed_ms": 1.2, "max_speed_ms": 2.0,
  "battery_wh": 1200, "endurance_minutes": 240,
  "camera_gsd_mm_at_1m": 0.35,
  "supports_offline_mission": true
}
```

`swath_m` define quantas passadas o plano vai ter. Uma câmera mais aberta cobre
mais por passada — cadastre um modelo novo, não mude o código.

---

## 3. Primeiro boot

```
1. gerar par Ed25519 e gravar a privada em armazenamento protegido
2. GET  /v1/device/time            → alinhar o relógio
3. POST /v1/device/provision       → convite + número de série + chave pública
4. gravar device_id, key_id, platform_public_key
5. apagar o convite: ele não serve mais
```

Sem relógio alinhado, nada é aceito.

---

## 4. Laço principal

```
enquanto ligado:
    telemetria a 1 Hz  (buffer quando offline)
    a cada 5 s: GET /v1/device/missions/current

    ao receber missão:
        verificar assinatura, destinatário, validade, sequência, nonce
        se falhar  → descartar + evento; NÃO executar
        se passar  → POST .../ack {accepted: true}
                     executar segmento a segmento
```

### Executando um segmento

```
para cada waypoint do segmento:
    checar energia    → política embarcada
    checar posição    → dentro do target_polygon
    mover
    telemetria

fotografar N pontos ao longo da faixa
POST /v1/device/observations   (uma por imagem)
POST /v1/device/missions/{id}/segments/complete
```

Reportar por segmento é o que grava o checkpoint. Sem isso não há retomada — e a
pausa nem sempre é ordenada: uma queda de energia ou de enlace no meio da faixa
não avisa antes.

---

## 5. Energia — decisão local

A missão traz `energy_policy`:

```json
{"reserve_percent": 20.0, "emergency_percent": 10.0,
 "estimated_return_percent": 12.4, "abort_below_percent": 32.4}
```

O firmware aplica, **sem consultar a nuvem**:

| Bateria | Estado | Ação |
|---|---|---|
| > `abort_below + 10` | `normal` | continuar |
| ≤ `abort_below + 10` | `low_battery` | continuar, avisar |
| ≤ `abort_below` | `return_to_base` | terminar a faixa atual e voltar |
| ≤ `emergency_percent` | `emergency_return` | parar onde está e voltar |

Referência: `EnergyPolicy.state_for` em
[`valtexa/services/energy.py`](../valtexa/services/energy.py).

Ao decidir voltar:

```
POST /v1/device/events   {"type": "return_to_base", "severity": "warning", ...}
navegar até a base
POST /v1/device/missions/{id}/pause   {"reason": "...", "battery_percent": ...}
```

A nuvem **registra**; não autoriza. Uma decisão de retorno que dependesse de
resposta deixaria um robô sem sinal esperando até a bateria acabar.

Depois da recarga:

```
POST /v1/device/missions/{id}/recharged
GET  /v1/device/missions/current      → comando novo, só com os segmentos que faltam
```

---

## 6. Sem enlace

`offline_policy` de missão de varredura:

```json
{"grace_seconds": 300, "on_link_loss": "continue",
 "stop_application": false, "after_grace": "continue"}
```

O rover **continua**. Ele não aplica nada, então operar sem nuvem é seguro — e a
lavoura tem sombra de sinal.

Enquanto offline: acumular telemetria, eventos e imagens em memória não volátil.
Ao reconectar:

```
POST /v1/device/sync   {"sync_id": "...", "samples": [...], "events": [...]}
```

Repetir o mesmo `sync_id` é seguro. Nunca descarte dado por falta de conexão.

---

## 7. Imagem — o que o modelo espera

Os modelos foram treinados com **folha preenchendo o quadro**. Imagem aérea de
dossel produz resposta confiante e errada; está medido em `VALTEXA-B/MODELS.md`.

Antes de subir, avalie e informe em `model_input_ok`:

- a folha ocupa a maior parte do quadro?
- há borrão de movimento?
- a exposição é utilizável?

`model_input_ok: false` manda a imagem direto para revisão humana em vez de
alimentar um diagnóstico que nasceria errado. **Enviar mesmo assim é o certo** —
o descarte é decisão da nuvem, não do robô.

Sugestões: JPEG qualidade ≥ 85, lado maior ≥ 1024 px, uma imagem a cada 2–5 m de
percurso. `edge_summary` pode trazer o que o robô calculou (nitidez, preenchimento,
detecções locais) — serve para priorizar, nunca para autorizar.

---

## 8. Eventos que o rover reporta

| `type` | Severidade | Quando |
|---|---|---|
| `mission_started` / `mission_completed` | info | ciclo normal |
| `mission_paused` / `mission_resumed` | info | pausa e retomada |
| `low_battery` | warning | ao entrar em `low_battery` |
| `return_to_base` | warning | decisão local de retorno |
| `obstacle_detected` | warning | desvio ou parada |
| `rtk_lost` | warning | perda de correção |
| `communication_lost` | warning | ao reconectar, com a duração |
| `emergency_stop` | critical | parada de emergência |
| `fault_detected` | critical | falha de motor, sensor ou armazenamento |

---

## 9. Checklist de conformidade

- [ ] par de chaves gerado no dispositivo; privada nunca sai nem aparece em log
- [ ] relógio sincronizado antes de assinar
- [ ] contador de sequência único e persistente entre reboots
- [ ] nonce nunca repetido
- [ ] assinatura verificada antes de executar qualquer comando
- [ ] `device_id`, `expires_at`, `sequence` e `nonce` conferidos
- [ ] decisão de energia local, sem esperar a nuvem
- [ ] checkpoint reportado a cada segmento
- [ ] buffer offline persistente; sincronização idempotente
- [ ] nenhum dado descartado por falta de conexão
- [ ] parada de emergência física, independente do software

---

## 10. O que ainda depende de hardware

- calibração real de consumo (`drain_per_meter`) — hoje é estimativa
- detecção e desvio de obstáculo: a plataforma só recebe o evento
- contagem de linha de plantio (`row_index`) — o campo existe e fica nulo
- alinhamento do plano às linhas reais: falta coletar o azimute da linha
- captura 3D: `pointcloud_asset_id` existe no esquema e não há produtor
