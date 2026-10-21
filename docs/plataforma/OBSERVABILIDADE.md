# Observabilidade e alertas (Parte 7 — brief, seções 34 e 35)

> O que a plataforma mede, de onde vem cada número, como os alertas funcionam e o que
> **não** é medido. Exemplo de Prometheus/Grafana: [`deploy/observabilidade/`](../../deploy/observabilidade/).

## 1. Visão geral

```
                ┌──────────── SaaS (API) ─────────────┐
 requisição ──▶ │ ObservabilidadeMiddleware            │──▶ X-Request-Id, log JSON
                │  ├─ métricas do processo (/metrics)  │
                │  └─ JanelaApi ──descarga 30 s──▶ api_request_stat (banco)
                └──────────────────────────────────────┘
 robô ──telemetria (health)──▶ device.health ──┐
 IA de nuvem ──▶ detection ─────────────────────┼──▶ services/observabilidade.py
 Edge AI ──▶ edge_record ───────────────────────┘        │
                                                        ├──▶ GET /metrics (Prometheus)
                                                        ├──▶ /v1/platform/observability/** (equipe)
                                                        ├──▶ /v1/observability/** (cliente: só os robôs dele)
                                                        └──▶ worker: services/alertas.py (a cada 60 s)
                                                                 │ alert.fired / alert.resolved (outbox)
                                                                 ▼
                                                    notificações da Parte 6 (central + e-mail)
 IA (VALTEXA-B) ──▶ GET /metrics (inferência por modelo, HTTP por rota)
```

Três princípios, de ponta a ponta:

1. **`None` não é zero.** O que não foi medido (GPU sem adapter, CPU na primeira
   leitura, robô que não manda `health`) não vira 0 % — some da exposição do
   Prometheus e aparece como "não medido" na tela.
2. **Simulação dita.** O robô lista em `health.simulated` as partes da HAL que são
   simulação; a tela mostra. A IA simulada (`SIMULATED_INFERENCE`) aparece como
   `simulado` no estado do serviço e `sim-1` nos modelos.
3. **Cardinalidade limitada.** Rota é sempre o **molde** (`/v1/fields/{field_id}`), nunca o
   caminho com id; caminho inexistente vira `nao_mapeada` (ou o `/{path}` do console).

## 2. SaaS

### 2.1 Requisições

`valtexa/observability/http.py` — *middleware* ASGI puro, o mais externo da pilha:

| Métrica (`/metrics`) | Tipo | Rótulos |
| --- | --- | --- |
| `valtexa_http_requests_total` | counter | `method`, `route`, `status` |
| `valtexa_http_request_duration_seconds` | histogram (5 ms a 10 s) | `method`, `route` |
| `valtexa_http_server_errors_total` | counter (5xx e exceção não tratada) | `method`, `route` |
| `valtexa_http_requests_in_progress` | gauge | — |
| `valtexa_process_start_time_seconds` | gauge | — |

São **desta réplica** (some no Prometheus). Para o console e para os alertas — que não
podem depender de qual réplica responde nem de um Prometheus —, cada réplica acumula
por **minuto × método × rota × classe de status** (`JanelaApi`) e descarrega **deltas** em
`api_request_stat` a cada `METRICS_FLUSH_SECONDS` (30 s) e ao parar. Se o banco falhar,
os dados voltam para a janela. A estatística por minuto é apagada depois de
`API_METRICS_RETENTION_DAYS` (7) pelo worker. p50/p95 são aproximados pelos baldes do
histograma (interpolação igual à do `histogram_quantile`).

### 2.2 Logs estruturados e `request_id`

- Toda resposta leva `X-Request-Id` (o do balanceador é reaproveitado se tiver 8–64
  caracteres seguros; senão um novo). A resposta 500 também traz `request_id` no JSON.
- `LOG_FORMAT=json`: uma linha JSON por registro, com `ts`, `level`, `logger`, `msg`,
  `request_id`, `tenant_id`, `user_id`, `device_id`, `support_session_id` (quando
  houver — preenchidos pelas dependências de autenticação) e os campos do *access log*
  (`method`, `route`, `status`, `duration_ms`). `LOG_FORMAT=texto` (padrão) mantém o
  formato antigo com `[req=...]` no fim.
- `/health` e `/metrics` saem em DEBUG (são raspados a cada poucos segundos).

### 2.3 Filas, usuários e frota (do banco, na hora)

`services/observabilidade.py`:

| O quê | Métrica | Fonte |
| --- | --- | --- |
| Trabalhos por tipo e estado; mais antigo na fila; falhas em 24 h | `valtexa_jobs`, `valtexa_jobs_oldest_queued_seconds`, `valtexa_jobs_failed_24h` | `processing_job` |
| Eventos de domínio pendentes, com erro, idade do mais antigo | `valtexa_outbox_pending`, `valtexa_outbox_with_error`, `valtexa_outbox_oldest_pending_seconds` | `outbox_event` |
| Entregas de aviso por estado | `valtexa_notification_deliveries{status}` | `notification_delivery` |
| Usuários ativos (15 min / 24 h) | `valtexa_active_users{window}` | `user_session.last_seen_at` |
| Alertas abertos | `valtexa_alerts_open{kind,state}` | `alert` |

### 2.4 `/metrics`

Na raiz da API (onde o Prometheus procura). **Protegido**: `Authorization: Bearer
<METRICS_TOKEN>` (variável de ambiente; comparação em tempo constante) **ou** o login de
alguém da equipe com `platform:observability:read`. Cliente → 403; sem nada → 401. Está
no teste de isolamento gerado do OpenAPI (classe "plataforma"). A saída passa no
`promtool check metrics` (Prometheus 2.54.1) sem aviso.

**Custo.** As famílias do banco ficam 15 s em cache na réplica (`FAMILIAS_CACHE_SEGUNDOS`).
Contagens, erros, classes e o *drift* saem de `GROUP BY` no banco (não linha a linha); o
p95 da IA usa as 5.000 latências mais recentes de cada modelo.

## 3. IA

### 3.1 No serviço de IA (`ia/app/metrics.py`)

Medido em `CornDiseaseModel.predict_images` — a porta por onde passam `/predict`,
`/predict/batch`, `/predict/rover-frame` e a fusão por planta (sem tocar em
`plant_fusion.py` nem `fields_api.py`):

| Métrica | Tipo | Rótulos |
| --- | --- | --- |
| `valtexa_ia_inferences_total` | counter (imagens) | `model` |
| `valtexa_ia_inference_calls_total` | counter (chamadas/lotes) | `model` |
| `valtexa_ia_inference_errors_total` | counter | `model`, `error` (`modelo_ausente`, `imagem_invalida`, `classe_desconhecida`, `falha`) |
| `valtexa_ia_inference_duration_seconds` | histogram (por imagem) | `model` |
| `valtexa_ia_predictions_total` | counter | `model`, `label` |
| `valtexa_ia_model_loaded` | gauge | `model` |
| `valtexa_ia_http_requests_total` / `_duration_seconds` | counter / histogram | `method`, `route`, `status` |

`GET /metrics` exige o `SERVICE_TOKEN` (o mesmo middleware de toda rota da IA). **A
verificar com o modelo real**: aqui os testes usam o dublê do `tests/conftest.py`.

### 3.2 Na plataforma (o que ficou gravado)

- **Nuvem** — `detection` (fonte `cloud_primary`/`cloud_secondary`): inferências, erros,
  abstenções, latência média e p95, classes, por modelo e versão.
- **Borda** — `edge_record` (`kind = result`): resultados da Edge AI que subiram, por
  modelo, com as classes.
- **Drift** — da **distribuição de classes previstas** (a saída), não da entrada: últimas
  24 h (configurável na regra) contra os 7 dias anteriores, por fonte e modelo, pela
  **distância de variação total** (0 a 1: a fração da massa que mudou de classe). Exige
  30 previsões recentes e 100 na base; abaixo disso, `distance = null` com o motivo.
  O drift de entrada (imagens) **não é medido**: precisa da referência do treino, que
  vive com os pesos na VALTEXA-B.
- **Modelo divergente** — o robô roda um modelo diferente do liberado pelo registry
  (`model_registry.situacao_do_modelo`: `divergente` ou `fora_do_registry`).

Atenção: drift de classes alto pode ser **a lavoura** (um surto real muda a distribuição)
— o alerta pede para conferir com o agrônomo, não para trocar o modelo.

## 4. Robôs

O Health Monitor do `rover/` (`runtime/health.py`) manda `health` em cada amostra de
telemetria. A HAL ganhou `SystemMonitor` (opcional):

| Campo | De onde vem no robô | Real ou simulado |
| --- | --- | --- |
| `cpu_percent`, `memory_*`, `load_1m` | `LinuxSystemMonitor` (`/proc/stat`, `/proc/meminfo`, `/proc/loadavg`) | **real** em qualquer Linux; CPU entre duas leituras (a primeira é `None`) |
| `accelerator.percent`, `.memory_used_bytes`, `.temperature_c` | adapter do fabricante (NVML, tegrastats, SDK da NPU) | **interface**: sem o adapter sai `None`; `SimulatedSystemMonitor` (marcado) nos testes e no simulador |
| `accelerator.name`, `.providers` | `AiAccelerator` da HAL (ONNX Runtime) | real |
| `disk_percent` | `StorageDevice.usage()` | real (`LocalDiskStorage`) |
| `temperature_c`, `battery_percent` | `Sensors` | simulado até haver o sensor |
| `cameras[]` (`id`, `ok`, `detail`) | falhas `camera:<id>` do Core | real (o que a câmera da HAL fez) |
| `sensors` (`gps`, `imu`, `ambiente`) | falhas `gps`/`sensors`; IMU `nao_monitorado` | real quanto ao que a HAL reporta |
| `network.online` | `Network.is_online()` | real |
| `sync` (`pending`, `failed`, `oldest_pending_s`, `blocked`, `last_ok_at`) | `SyncEngine.saude()` | real |
| `edge_ai` (`fps`, `latency_ms`, `model_loaded`) | motor da Edge AI (só leitura) | real |
| `simulated[]` | `Hardware.describe()` | — |

Na plataforma, `services/saude_rover.py` guarda em `device.health` **só os campos
conhecidos**, com tipo e faixa conferidos (300 % de memória vira `None`, não 100 %),
câmeras limitadas a 16. Robô sem `health` (firmware anterior) segue funcionando com a
telemetria básica. Versões (runtime, Edge AI, modelo, firmware) vêm do anúncio de versões
que já existia. Métricas: `valtexa_rover_up`, `_cpu_percent`, `_memory_percent`,
`_accelerator_percent`, `_disk_percent`, `_temperature_celsius`, `_battery_percent`,
`_cameras_ok`, `_sync_pending`, `_last_seen_seconds` (rótulos `tenant` = id do cliente,
`device` = serial).

## 5. Alertas

`services/alertas.py`, avaliados pelo worker a cada `ALERTS_EVERY_SECONDS` (60).

| Regra | Escopo | Padrão | Severidade | Dispara quando |
| --- | --- | --- | --- | --- |
| `rover_offline` | robô | 30 min | crítico | robô ativo sem contato há X min (nunca visto não conta) |
| `disco_rover` | robô | 90 % | aviso | disco local acima de Y % |
| `temperatura_rover` | robô | 75 °C | crítico | temperatura interna acima do limite |
| `sync_parada` | robô | 30 min | aviso | robô **conectado** com registros esperando há X min, ou fila travada (sem rede é offline-first, não alerta) |
| `camera_rover` | robô | — | aviso | alguma câmera falhou na última leitura |
| `modelo_divergente` | robô | — | aviso | modelo diferente do liberado / fora do registry |
| `api_erros` | plataforma | 5 % em 5 min | crítico | 5xx acima de Y % com 20+ requisições na janela |
| `ia_fora` | plataforma | 20 % em 15 min | crítico | `/health` da IA não responde, ou Y % das inferências da janela com erro (10+) |
| `drift_classes` | plataforma | 0,25 em 24 h | aviso | distância de variação total acima do limite |
| `eventos_parados` | plataforma | 10 min | crítico | evento de domínio sem entrega há X min (worker parado?) |

- **Estado**: `disparado` → (`reconhecido`) → `resolvido`. Resolve **sozinho** quando a
  condição passa (ou a regra é desligada). Uma nova violação abre um alerta novo; o
  histórico fica.
- **Um aberto por assunto**: `alert.open_key` é único (vira nulo ao resolver). Conferido
  com 4 workers em paralelo no Postgres 16: 50 robôs com disco cheio → 50 alertas e 50
  eventos, nenhum duplicado.
- **Regras configuráveis**: a padrão (`tenant_id` nulo) pela equipe com
  `platform:alert:manage` (superadmin, operações, IA & dados); as **de robô** também por
  cliente — o gestor/técnico (`device:manage`) põe um limite só para os robôs dele, e
  "voltar ao padrão" apaga a versão dele. Toda mudança é auditada (`alert_rule.updated`,
  `alert_rule.reset`); reconhecer também (`alert.acknowledged`).
- **Entrega**: disparar publica `alert.fired` no *outbox* (mesma transação); a regra de
  aviso cria `alerta_robo` para o cliente dono do robô (padrão: dono, gestor, técnico,
  com e-mail) e `plataforma_alerta` para a equipe (padrão: superadmin e operações). O
  robô sem comunicação **não** repete aviso para o cliente — ele já recebe
  `rover_offline` da Parte 6. `alert.resolved` só avisa quando o alerta era crítico.
  Tudo passa pelas preferências, pela idempotência e pelo "sem SMTP não finge" da Parte 6.

## 6. Telas

- **Plataforma** → "Observabilidade" (`/plataforma/observabilidade`,
  `platform:observability:read`): semáforo por componente (banco, API, worker, IA, frota,
  alertas), números da API e filas; abas API por rota, Robôs (todos os clientes), IA
  (modelos e drift), Alertas (reconhecer) e Regras (editar).
- **Cliente** → "Saúde da frota" (`/observabilidade`, `device:read`): os robôs dele, os
  alertas deles e as regras de robô (com a versão própria). Nada da API, da IA nem de
  outro cliente.
  A versão própria **não** alcança `rover_offline` (o aviso dele é só da equipe; o
  cliente controla os próprios avisos nas preferências) e **perde para a equipe**: regra
  padrão desligada vale para todos, com ou sem cópia do cliente (verificação na Parte 8).

## 7. Configuração

| Variável | Padrão | Para quê |
| --- | --- | --- |
| `METRICS_TOKEN` | vazio | Token do Prometheus em `/metrics` (sem ele, só a equipe logada lê) |
| `LOG_FORMAT` | `texto` | `json` para uma linha JSON por registro |
| `METRICS_FLUSH_SECONDS` | 30 | Descarga da estatística por minuto da API |
| `API_METRICS_RETENTION_DAYS` | 7 | Guarda da estatística por minuto |
| `ALERTS_EVERY_SECONDS` | 60 | Cadência da avaliação das regras |
| IA: `SERVICE_TOKEN` | — | Também protege o `/metrics` da IA |

## 8. Testes e números (Parte 7)

- SaaS: `tests/test_observabilidade.py` (29: formato, molde da rota, janela e descarga,
  banco fora, 500 com `request_id`, log JSON com cliente e usuário, `/metrics` protegido,
  saúde padronizada, cada regra disparando e resolvendo, regra própria do cliente,
  notificações, isolamento, concorrência do catálogo, cache do `/metrics`);
  `test_isolamento_openapi.py` com
  alerta e regra reais da vítima.
- IA: `tests/test_metrics.py` (5). Rover: `tests/test_saude.py` (7).
- Console: `src/lib/observability.test.ts` (8); navegador `e2e/observabilidade.mjs` (10
  passos, sem erro de JS).

## 9. O que não foi feito ou não foi verificado

- Prometheus e Grafana **não** rodaram contra um ambiente real (não há um aqui): a
  configuração passou no `promtool`, a exposição também.
- GPU/NPU: só a interface; sem o hardware definido, nenhum adapter real.
- Drift de entrada (imagens) não medido; drift de classes é da saída.
- "Silenciar" alerta por um período e "dono" atribuído não existem: há o reconhecer (quem
  e nota). Sem agregação de alertas repetidos de um mesmo robô que oscila no limite
  (histerese) — se incomodar em campo, entra.
- A IA não grava as próprias métricas em banco: o histórico delas é o do Prometheus.
- Os alertas da plataforma dependem do worker; se o worker para, o alerta
  `eventos_parados` não sai **dele** — por isso as regras do Prometheus
  (`deploy/observabilidade/regras.yml`) são a segunda linha.
