# Integração da Dock / Base Autônoma

A dock parece o componente mais simples e carrega uma responsabilidade que
nenhum outro tem: **ela é a fonte do vento**, e sem leitura de vento a plataforma
bloqueia toda pulverização.

Referência executável: `SimulatedDock` em
[`simulator/devices.py`](../simulator/devices.py).

---

## 1. Capacidades

`DOCK_BASE_V1`:

```json
{
  "can_charge": true, "can_swap_battery": true, "can_refill": true,
  "has_rtk": true, "supports_offline_mission": false
}
```

A dock não recebe missão. Ela reporta e serve.

---

## 2. Por que o vento vem daqui

O safety engine **falha fechada**: sem leitura de vento, a missão de
pulverização é bloqueada com o código `weather`. Não é conservadorismo gratuito —
pulverizar sem saber o vento é exatamente como a deriva atinge a mata ciliar e a
lavoura do vizinho, e a responsabilidade seria da ValTexa.

A dock é a fonte esperada porque fica parada no talhão, alimentada, com o sensor
na altura certa. Um anemômetro no drone mede o próprio rotor.

```http
POST /v1/device/telemetry
{
  "samples": [{
    "sequence_number": 8821,
    "recorded_at": "2026-09-09T03:00:00+00:00",
    "sensors": {
      "wind_ms": 3.2,
      "wind_gust_ms": 5.1,
      "wind_direction_deg": 118,
      "temperature_c": 26.4,
      "humidity_percent": 62.0,
      "rain_mm_h": 0.0
    },
    "battery_percent": 100.0
  }]
}
```

A chave `wind_ms` é lida por
`safety_engine._wind_from_dock`. O restante é registrado e ainda não entra em
nenhuma regra.

**Cadência recomendada:** 1 amostra por minuto em repouso, 1 a cada 10 s quando
houver drone em missão. O safety engine usa a leitura **mais recente** da fazenda.

A dock precisa estar vinculada à mesma `farm_id` dos robôs. Uma dock sem fazenda
opera e reporta, mas o vento dela não vale para nenhuma missão.

---

## 3. Recarga e reabastecimento

A coreografia física ainda não está implementada. O que existe hoje:

```http
POST /v1/device/events
{"events": [{
  "sequence_number": 8822,
  "type": "battery_swapped",
  "severity": "info",
  "occurred_at": "...",
  "payload": {"device": "VTX-ROVER-0001", "battery_percent": 100}
}]}
```

Quem declara que pode retomar é o **robô**, não a dock:

```http
POST /v1/device/missions/{mission_id}/recharged
```

A dock não sabe qual missão o robô estava executando, e não deveria saber. Cada
dispositivo reporta o que ele mesmo observa.

---

## 4. Eventos

| `type` | Severidade | Quando |
|---|---|---|
| `dock_online` / `dock_offline` | info / warning | ciclo de energia |
| `device_docked` / `device_undocked` | info | robô entrou/saiu |
| `charging_started` / `charging_completed` | info | ciclo de carga |
| `battery_swapped` | info | troca concluída |
| `refill_started` / `refill_completed` | info | reabastecimento |
| `weather_alert` | warning | vento ou chuva acima do limite operacional |
| `fault_detected` | critical | falha de carregador, bomba ou sensor |

---

## 5. Checklist

- [ ] provisionada com `farm_id` da fazenda onde está instalada
- [ ] telemetria de vento contínua, com `wind_ms` em metros por segundo
- [ ] cadência aumentada quando há missão de pulverização em curso
- [ ] eventos de carga e reabastecimento reportados
- [ ] falha de sensor reportada como `critical` — sensor mudo é pior do que
      sensor ausente, porque a plataforma não distingue "sem vento" de
      "sem leitura" se o valor vier zerado

---

## 6. O que ainda depende de hardware

- coreografia de aproximação, acoplamento e troca de bateria
- medição de nível dos reservatórios da base
- reabastecimento automático de calda com verificação de produto
- fonte de vento redundante para o caso de falha do anemômetro
- energia própria (solar/gerador) e o que fazer quando a própria dock fica sem
