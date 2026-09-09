# Integração do Drone Action

O drone é o único dispositivo que **age sobre a lavoura**. Aplicação é a única
operação irreversível do sistema: uma vez que a calda saiu do bico, nenhuma
correção de software a traz de volta. Todo o resto deste documento decorre disso.

Leia junto com [`DEVICE_PROTOCOL.md`](DEVICE_PROTOCOL.md) e
[`SAFETY.md`](SAFETY.md). Referência executável: `SimulatedDrone` em
[`simulator/devices.py`](../simulator/devices.py).

---

## 1. Capacidades

`DRONE_ACTION_V1`:

```json
{
  "has_rtk": true, "has_camera_rgb": true, "can_fly": true, "has_spray": true,
  "tank_count": 2, "tank_capacity_l": 10.0, "swath_m": 4.0,
  "cruise_speed_ms": 6.0, "max_speed_ms": 12.0,
  "battery_wh": 900, "endurance_minutes": 18, "max_payload_kg": 20.0,
  "supports_offline_mission": true
}
```

Sem `has_spray`, sem `tank_count ≥ 1` **e sem `has_rtk`**, a plataforma recusa
missão de pulverização. RTK é obrigatório e não negociável: sem correção o erro
de posição é de metros, e aplicar defensivo com esse erro é aplicar na área do
vizinho.

---

## 2. O que chega ao drone

Nunca "vá até esta coordenada e aplique". Sempre uma **missão fechada e
assinada**:

```json
{
  "mission_id": "…",
  "kind": "spray",
  "target_polygon": [[lon, lat], ...],
  "segments": [{"index": 0, "path": [[lon, lat], [lon, lat]]}],
  "plan": {"swath_m": 4.0, "area_ha": 1.34},
  "energy_policy": {...},
  "offline_policy": {...},
  "application": {
    "product_id": "…", "batch_id": "…", "tank_id": "…",
    "rate_l_ha": 0.75, "max_quantity_l": 6.0
  }
}
```

`target_polygon` é a **fronteira física** da missão. `max_quantity_l` é um teto,
não uma meta: o que sobrar de área fica para outra missão, com outra autorização.

Antes de armar qualquer atuador, verifique — nesta ordem — assinatura,
`device_id`, `expires_at`, `sequence` e `nonce`. Qualquer falha: descarte,
reporte evento, **não execute**.

---

## 3. Verificações locais antes de decolar

A nuvem já rodou o safety engine. O drone verifica de novo, com o que só ele
sabe:

| Verificar | Se falhar |
|---|---|
| tanque instalado é o `tank_id` da missão | recusar via `ack` |
| leitura de nível ≥ `max_quantity_l` | recusar |
| RTK em `fixed` | recusar |
| bateria acima de `abort_below_percent + margem de ida` | recusar |
| `target_polygon` dentro do mapa local | recusar |
| vento medido a bordo dentro do limite | recusar |

```json
POST /v1/device/missions/{id}/ack
{"mission_id": "…", "accepted": false, "reason": "RTK em float"}
```

A recusa é gravada e aparece para um humano. **Discordância entre a nuvem e o
robô sobre o que é seguro nunca some num log** — é o sinal mais valioso que o
sistema pode receber.

---

## 4. Aplicando

```
POST /v1/device/applications/start   {"mission_id": …, "started_at": …, "tank_id": …}

para cada ponto do percurso:
    se NÃO contains_point(target_polygon, posição):   fechar o bico
    se volume_usado >= max_quantity_l:                fechar o bico, encerrar
    se vento > limite:                                fechar o bico, pausar
    se RTK perdeu fix:                                fechar o bico, pausar
    senão:                                            aplicar; registrar na trilha

POST /v1/device/applications/{id}/stop
{"stopped_at": …, "amount_used_l": …, "area_ha": …,
 "track": [[lon, lat, vazao], ...], "stop_reason": "…"}
```

A verificação de contenção roda **a cada ponto, no drone**. A nuvem conta os
pontos fora depois e gera evento crítico se houver algum — mas isso é auditoria:
quem impede a saída é o firmware, em tempo real, e é o que continua valendo com
a nuvem fora do ar.

A trilha é o mapa de aplicação, e vira comprovante para o produtor e prova para a
fiscalização. Registre o que **realmente** saiu, não o planejado.

---

## 5. Energia

Um drone tem ~18 minutos de autonomia; a margem para erro é de segundos.

```json
{"reserve_percent": 20.0, "emergency_percent": 10.0,
 "estimated_return_percent": 18.7, "abort_below_percent": 38.7}
```

| Bateria | Ação |
|---|---|
| ≤ `abort_below_percent` | **fechar o bico**, encerrar aplicação, voltar |
| ≤ `emergency_percent` | pousar onde estiver, em segurança |

Fechar o bico vem antes de voltar. Um drone que retorna aplicando fora do
polígono é pior do que um drone que aborta a missão.

`estimated_return_percent` é calculado pela nuvem a partir do ponto mais distante
da área, com 30% de margem para vento contrário e desvio. Se a medição a bordo
discordar, **prevalece a mais conservadora**.

---

## 6. Perda de enlace — política agressiva

```json
{"grace_seconds": 30, "on_link_loss": "pause",
 "stop_application": true, "after_grace": "return_to_base"}
```

Diferente do rover, que continua. O drone **fecha o bico imediatamente** e pausa;
passados 30 segundos sem enlace, volta à base.

A razão é simples: aplicação é irreversível. É a última coisa que se deixa
seguir às cegas.

```
enlace caiu:
    fechar bico agora
    manter posição (ou hover seguro)
    contar grace_seconds
    ainda sem enlace → return_to_base
    perdeu RTK também → pousar
```

Ao reconectar: `POST /v1/device/sync` com tudo que ficou acumulado, e um evento
`communication_lost` com a duração.

---

## 7. Eventos

| `type` | Severidade | Quando |
|---|---|---|
| `takeoff` / `landed` | info | ciclo normal |
| `application_started` / `application_stopped` | info | acompanham as rotas de aplicação |
| `application_blocked_geofence` | **critical** | tentou aplicar fora do polígono |
| `tank_mismatch` | critical | conteúdo diverge do autorizado |
| `low_battery` / `return_to_base` | warning | política de energia |
| `emergency_return` | critical | abaixo do limiar de emergência |
| `rtk_lost` | warning | perda de correção |
| `wind_exceeded` | warning | vento acima do limite |
| `communication_lost` | warning | ao reconectar |
| `emergency_stop` | critical | parada de emergência |

---

## 8. ACK, NACK e tempo limite

| Situação | Firmware |
|---|---|
| comando válido | `ack` com `accepted: true`, executar |
| assinatura inválida | descartar, evento `critical`, **não** responder ack |
| destinatário errado | descartar, evento `critical` |
| comando expirado | descartar em silêncio; buscar de novo depois |
| sequência retrógrada | descartar (repetição) |
| pré-condição local falhou | `ack` com `accepted: false` e motivo |
| sem resposta da nuvem | *backoff*; a missão em memória continua valendo até `expires_at` |

Nunca peça esclarecimento sobre um comando que não passou na verificação. Um
comando que não verifica não é um comando.

---

## 9. Fail-safe — a hierarquia

Em ordem de precedência. A de cima sempre vence:

1. **parada de emergência física** — corta atuadores, independente do software;
2. **contenção geográfica** — fora do polígono, bico fechado, sem exceção;
3. **energia** — reserva de retorno é intocável;
4. **integridade do comando** — sem assinatura válida, nada acontece;
5. **enlace** — sem nuvem, aplicação para;
6. **plano da missão** — o que fazer quando tudo acima está satisfeito.

Nenhuma regra de nível mais baixo pode contornar uma de nível mais alto. Se o
plano da missão exigir passar por um ponto fora do polígono, o ponto é pulado —
não é o polígono que cede.

---

## 10. Checklist

- [ ] chave privada gerada e mantida no dispositivo
- [ ] assinatura verificada antes de armar qualquer atuador
- [ ] pré-condições locais checadas; recusa reportada com motivo
- [ ] contenção no polígono verificada **a cada ponto**
- [ ] teto de volume respeitado como teto
- [ ] bico fecha antes de retornar, sempre
- [ ] enlace caiu → bico fecha em menos de 1 s
- [ ] trilha registra o que saiu de verdade
- [ ] parada de emergência independente do software
- [ ] nenhum dado descartado por falta de conexão

---

## 11. O que ainda depende de hardware

- calibração de vazão: a plataforma acredita no `amount_used_l` reportado
- deriva por vento: modelada apenas como limite de decolagem, não em tempo real
- sensor de nível de tanque: hoje a nuvem debita o volume aplicado do registro
  de carga, o que diverge se a medição real diferir
- troca automática de bateria pela dock: o evento existe, a coreografia não
- verificação cruzada entre o vento a bordo e o da dock
