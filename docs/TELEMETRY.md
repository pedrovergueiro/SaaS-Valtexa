# Telemetria

O que medir, com que frequência, e o que a plataforma faz com isso.

Modelo: `TelemetrySample` em
[`valtexa/models/operations.py`](../valtexa/models/operations.py).

---

## Campos

### Posição
| Campo | Unidade | Nota |
|---|---|---|
| `lat`, `lon` | graus WGS84 | |
| `alt_m` | metros | relativo ao solo, para drone |
| `heading_deg` | graus | 0 = norte |
| `speed_ms` | m/s | |
| `rtk_fix` | `none`/`single`/`float`/`fixed` | **`fixed` é exigido para aplicar** |
| `hdop` | — | diluição de precisão horizontal |

### Energia
| Campo | Unidade |
|---|---|
| `battery_percent` | 0–100 |
| `battery_voltage_v` | volts |
| `battery_current_a` | ampères (negativo carregando) |
| `temperature_c` | °C |
| `energy_state` | `normal`/`low_battery`/`return_to_base`/`emergency_return`/`landed` |

### Estado e sensores
| Campo | Conteúdo |
|---|---|
| `mission_state` | o que o robô acha que está fazendo |
| `link_quality` | 0–1 |
| `motors` | livre: `{"fl": {"rpm": 120, "temp_c": 44}}` |
| `sensors` | livre: `{"wind_ms": 3.2, "tank_level_l": 7.4}` |
| `faults` | lista de códigos ativos |

`motors` e `sensors` são JSON livre de propósito: cada modelo de hardware tem
grandezas próprias, e engessar o esquema forçaria uma migração a cada robô novo.

**Uma chave é lida por regra:** `sensors.wind_ms`, pelo safety engine, para
liberar ou bloquear pulverização. As demais são registradas e ainda não entram em
nenhuma decisão.

---

## Cadência

| Situação | Frequência |
|---|---|
| Rover em missão | 1 Hz |
| Rover parado | 0,1 Hz |
| Drone em voo | 2–5 Hz |
| Drone em aplicação | 5 Hz |
| Dock em repouso | 1/min |
| Dock com drone em missão | 1/10 s |

Envie em lotes, não uma amostra por requisição: cada requisição carrega uma
assinatura Ed25519 e um nonce. Teto por requisição: `MAX_TELEMETRY_BATCH` (500).

Sugestão de lote: acumular 10–30 s de amostras, ou 50 amostras, o que vier
primeiro.

---

## Dois horários

| Campo | De quem | Para quê |
|---|---|---|
| `recorded_at` | relógio do robô | quando aconteceu |
| `received_at` | relógio do servidor | quando chegou |

A diferença mede o atraso da sincronização. Num lote descarregado depois de 3 h
offline, ela é de horas — e isso é informação, não erro.

O robô precisa do relógio sincronizado de qualquer forma: a assinatura depende de
um horário dentro da janela de tolerância. `GET /v1/device/time` é o caminho de
volta para um robô perdido no tempo.

---

## Idempotência

Chave: `(device_id, sequence_number)`. Reenviar não duplica. Ver
[`OFFLINE_MODE.md`](OFFLINE_MODE.md).

Uma amostra sem `sequence_number` é **rejeitada sem derrubar o lote**: a resposta
traz `accepted`, `duplicated`, `rejected` e a lista de erros, e o que estava bom
entrou.

Uma amostra citando uma missão que não é do robô tem o vínculo ignorado com
aviso no log, mas é aceita — um identificador alheio contaminaria o histórico do
vizinho, e recusar o lote inteiro perderia dado bom por causa de um campo.

---

## Reflexo no dispositivo

Cada lote atualiza `Device`: `last_seen_at`, posição, bateria, conectividade,
marca d'água de sequência.

Isso duplica a telemetria de propósito. A tela de frota precisa de **uma leitura
por dispositivo**, não de um `MAX()` sobre milhões de amostras — e a diferença
aparece já com poucos robôs em operação.

---

## Volume e retenção

Um rover a 1 Hz numa jornada de 4 h: **~14 mil amostras por missão**. Cinco robôs,
cinco dias por semana: ~1,8 milhão por mês.

Caminho previsto, em ordem:

1. particionar `telemetry_sample` por mês;
2. agregar amostras com mais de 90 dias em janelas de 1 minuto (média, mínimo,
   máximo) e descartar o cru;
3. mover a série para um banco de série temporal, mantendo `device_event` no
   relacional.

A separação da etapa 3 é o ponto: **evento é o que precisa sobreviver íntegro
para a auditoria; telemetria é amostragem.** Agregar telemetria antiga é
aceitável; agregar evento não.

Nada disso está implementado. Com SQLite, a ingestão concorrente serializa muito
antes de o volume virar problema — ver [`DEPLOYMENT.md`](DEPLOYMENT.md).
