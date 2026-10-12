# Observabilidade — Prometheus e Grafana (exemplo)

Exemplo de como raspar e visualizar as métricas da plataforma (Parte 7, brief seção 35).
**Sem segredo no repositório**: os tokens entram por arquivo, criados no deploy.
Detalhes do que é medido: [`docs/OBSERVABILIDADE.md`](../../docs/plataforma/OBSERVABILIDADE.md).

| Arquivo | O que é |
| --- | --- |
| `prometheus.yml` | Dois *jobs*: `valtexa-saas` (`/metrics` da API, com `METRICS_TOKEN`) e `valtexa-ia` (`/metrics` da IA, com o `SERVICE_TOKEN`). |
| `regras.yml` | Alertas do Prometheus — a **segunda linha**: API ou IA fora do ar, 5xx, p95, eventos parados, alerta crítico sem dono, erro de inferência, *drift*. A primeira linha são os alertas da própria plataforma (console + e-mail). |
| `grafana/` | *Provisioning* da fonte de dados e o painel "ValTexa — visão geral" (16 gráficos: API, filas, usuários, alertas, frota, IA). |
| `docker-compose.yml` | Prometheus + Grafana presos em `127.0.0.1` (atrás de um proxy com TLS em produção). |

## Subir

```bash
cd deploy/observabilidade
mkdir -p segredos                       # está no .gitignore
printf '%s' "$METRICS_TOKEN" > segredos/metrics_token   # o mesmo METRICS_TOKEN da API
printf '%s' "$SERVICE_TOKEN" > segredos/ia_token        # o SERVICE_TOKEN da IA
# edite os targets de prometheus.yml (endereço da API e da IA)
GRAFANA_ADMIN_PASSWORD='...' docker compose up -d
```

Na API: defina `METRICS_TOKEN` (gere com `python -c "import secrets;print(secrets.token_urlsafe(32))"`)
e, para logs estruturados, `LOG_FORMAT=json`. Na IA: o `SERVICE_TOKEN` já protege
o `/metrics` como toda rota.

## Várias réplicas

* As métricas **HTTP** (`valtexa_http_*`) são de cada réplica: some com `sum by (route)`.
* As métricas **do banco** (`valtexa_outbox_*`, `valtexa_jobs*`, `valtexa_rover_*`,
  `valtexa_ai_*`, `valtexa_alerts_open`, `valtexa_active_users`) saem iguais em todas as
  réplicas — o painel e as regras usam `max by (...)` nelas.
* Cada réplica também grava a estatística por minuto no banco (`api_request_stat`):
  é o que o console e os alertas da plataforma usam, sem depender do Prometheus.

## O que foi validado aqui

`promtool check config` e `promtool check rules` (Prometheus 2.54.1) passam; as 20
consultas do painel foram conferidas pelo mesmo `promtool` (como regras de gravação).
O `/metrics` real da API e da IA passa no `promtool check metrics` (ver
`docs/OBSERVABILIDADE.md`). **Não** foi testado com um Prometheus/Grafana rodando contra
um ambiente real — não há um nesta nuvem.
