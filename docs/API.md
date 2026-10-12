# API — guia para o frontend

O contrato vivo é `/openapi.json`, e `/docs` é navegável. Este documento explica
o que a especificação não diz: o fluxo, o que cada rota significa no produto, e
onde o frontend precisa ter cuidado.

**Não existe rota privada de frontend.** A prova executável é
[`simulator/operator.py`](../simulator/operator.py): ele faz, por HTTP, tudo que
uma tela faria.

---

## Autenticação

```
POST /v1/auth/login   {"email": "...", "password": "...", "tenant": "slug?"}
```

```json
{"access_token": "...", "expires_at": "...", "tenant_id": "...",
 "role": "agronomist", "capabilities": ["mission:approve_application", ...]}
```

Em toda requisição seguinte:

```
Authorization: Bearer <access_token>
X-Tenant-Id: <tenant_id>
```

Um usuário com vários clientes e sem `tenant` no login recebe `tenant_id: null` —
a tela pergunta qual abrir e passa `X-Tenant-Id`.

`GET /v1/auth/me` devolve identidade, papel, capacidades e todas as associações —
e mais `platform_role`, `access` (`membro`, `plataforma` ou `suporte`) e, numa
sessão de suporte, `support_session` (mostre a faixa no topo enquanto existir).

Para a equipe da ValTexa, `/v1/auth/memberships` lista todos os clientes; os que
não são associação vêm com `access: "plataforma"` e papel `viewer`. Eles servem
às rotas de plataforma; abrir os dados do cliente exige sessão de suporte (ver
*Plataforma*, abaixo). Rota de cliente chamada sem isso responde `403` com a
orientação no `detail`.

### Sobre `capabilities`

Use para esconder o que o papel não permite. **Esconder é conveniência, não
segurança** — cada rota confere de novo, e um `403` é resposta legítima que a
interface precisa tratar, não um estado impossível.

---

## Rotas, por área

### Fazendas
```
GET  /v1/farms                       POST /v1/farms
GET  /v1/farms/{id}/fields           POST /v1/farms/{id}/fields
GET  /v1/fields                      # todos os talhões do cliente
GET  /v1/fields/{id}
GET  /v1/fields/{id}/zones           POST /v1/fields/{id}/zones
GET  /v1/fields/{id}/ai-models       PUT  /v1/fields/{id}/ai-model
```
`PATCH /v1/farms/{id}` altera em parte (auditado com o antes e o depois).
A fazenda tem a identificação da seção 5 do brief, toda opcional: `owner_name`
(produtor), `owner_document` (CPF ou CNPJ — conferido pelo dígito e guardado só
com dígitos), `city`, `state` (UF), `main_crop`, `car_code` (recibo do CAR,
`UF-1234567-<32 hex>`, aceito com pontos), `technical_lead` e `notes`. Texto
vazio apaga o campo; documento inválido → `422` com a mensagem em português.

**CPF/CNPJ mascarado** (decisão do Pedro, Parte 3): só quem tem `farm:manage` recebe
`owner_document` inteiro; os demais papéis recebem `***.***.***-12` (ou
`**.***.***/****-12`) e `owner_document_masked: true`. É na API, não na tela.
Leitura do completo pela equipe da ValTexa (sessão de suporte assistida) grava
`farm.owner_document_viewed` na trilha do cliente; a trilha de edição guarda o
documento mascarado.

A área (`area_ha`) do talhão é **derivada do polígono**, nunca informada: um número
digitado à mão divergiria do desenho, e é ele que manda na dose e na cerca.

`ai-models` são as versões do modelo que atendem a cultura do talhão — o
seletor, como o de modelos de um assistente: versão, desempenho no campo em
linguagem operacional (`field_performance`: alto, bom, limitado — sem o número,
que é métrica técnica e fica no registry), licença dos dados e ressalva. Só
aparecem versões em PRODUÇÃO do Model Registry liberadas para o cliente. `PUT ai-model` com `{"ai_model": "citrus-foliar-cc"}`
troca (exige `farm:manage`); `FieldOut.ai_model_in_use` diz qual vale agora.
Ver [AI_PIPELINE.md](AI_PIPELINE.md), seção 5.

### Frota
```
GET   /v1/device-models
POST  /v1/provisioning-tokens        # token em claro aparece UMA vez
GET   /v1/devices                    GET /v1/devices/{id}
PATCH /v1/devices/{id}/status
POST  /v1/devices/{id}/revoke-credentials
GET   /v1/devices/{id}/telemetry?minutes=60      # amostras cruas
GET   /v1/devices/{id}/telemetry/rollup?days=30  # agregado por minuto
GET   /v1/devices/{id}/events
```
A amostra crua só existe dentro de `TELEMETRY_RETENTION_DAYS`; para janelas mais
velhas, use `/rollup`.

`DeviceOut` traz o retrato de frota (Parte 3): `fleet_state` (disponivel,
em_missao, sincronizando, manutencao, offline, bloqueado, erro), `fleet_state_label`
e `fleet_state_reason` — derivados do protocolo, nunca digitados (ver
[DEVICE_PROTOCOL.md](DEVICE_PROTOCOL.md#estado-de-frota-derivado)); as versões que o
robô informou (`runtime_version`, `edge_ai_version`, `ai_model_key`,
`ai_model_version`, `dnaty_version`, `hardware_version`); a saúde
(`temperature_c`, `storage_*`, `link_quality`, `operating_hours`, `active_faults`,
`sync_pending`, `last_sync_at`, `last_maintenance_at`); e `model_status`
(conforme, divergente, fora_do_registry, sem_dado) com `designated_models`.
`PATCH .../status` com `maintenance` aceita `maintenance_note`; sair da
manutenção grava `last_maintenance_at`.

### Missões
```
GET  /v1/missions                    POST /v1/missions
GET  /v1/missions/{id}               GET  /v1/missions/{id}/segments
POST /v1/missions/{id}/approve       POST /v1/missions/{id}/authorize
POST /v1/missions/{id}/dispatch      POST /v1/missions/{id}/resume
POST /v1/missions/{id}/abort
PATCH /v1/missions/{id}/route        POST /v1/missions/{id}/replan
GET  /v1/missions/{id}/safety        POST /v1/missions/{id}/safety/preview
GET  /v1/missions/{id}/history       GET  /v1/missions/{id}/checkpoints
```
`history` é a linha do tempo da missão — cada transição, com quem e por quê —,
legível por quem opera, sem precisar da permissão de auditoria.

### Percepção
```
GET  /v1/observations                GET  /v1/observations/{id}/image
GET  /v1/diagnoses                   GET  /v1/review/queue
GET  /v1/diagnoses/{id}
POST /v1/diagnoses/{id}/review       POST /v1/diagnoses/{id}/decide
GET  /v1/decisions
GET  /v1/fields/{id}/plants          GET  /v1/fields/{id}/plants/map
GET  /v1/fields/{id}/plants/{plant_id}/evolution
GET  /v1/fields/{id}/prevalence
```
`DetectionOut.signals` traz o que a IA disse além do rótulo: o portão de
enquadramento (`in_scope`, `scene`), o conjunto conformal (`prediction_set`) e,
num quadro do rover, o resumo `frame` (recortes por zona da planta, fração por
classe, severidade da Sigatoka). A lista de observações não traz os sinais —
pesam num quadro —; busque `GET /v1/diagnoses/{id}` ao abrir uma.

As rotas de plantas leem a fusão por planta do serviço de inferência e
respondem **503** quando ele não guarda talhões: mostre como estado ("configure
FIELDS_DIR na inferência"), não como erro passageiro — repetir não resolve.
Ver [AI_PIPELINE.md](AI_PIPELINE.md), seção 7.

### Insumos e aplicação
```
GET/POST /v1/products                GET/POST /v1/products/{id}/batches
GET/POST /v1/tanks                   POST /v1/tanks/{id}/load
POST     /v1/tanks/{id}/empty
GET      /v1/applications            GET  /v1/verifications
POST     /v1/verifications/{id}/conclude
```

### Gêmeo digital e auditoria
```
GET /v1/fields/{id}/snapshot         GET /v1/fields/{id}/timeline
GET /v1/fields/{id}/anomalies
GET /v1/fields/{id}/scene            GET /v1/fields/{id}/row-scans
GET /v1/row-scans/{id}/pointcloud
GET /v1/audit                        GET /v1/events
```

### Painel, alertas e pessoas
```
GET    /v1/dashboard                 GET  /v1/alerts?days=7
GET    /v1/stream                    # SSE, ver *Tempo real*
GET    /v1/auth/memberships          # clientes a que a pessoa tem acesso
GET    /v1/users                     POST /v1/users
PATCH  /v1/users/{id}                DELETE /v1/users/{id}
```

### Talhão: configuração
```
PATCH  /v1/fields/{id}               # variedade, estágio, espaçamentos, nº de linhas,
                                     # fileiras de validação, observações (parcial)
```
`FieldCreate`/`FieldOut` têm `plant_spacing_m` (entre plantas, m), `row_count`,
`validation_rows` (números das linhas, a partir de 1, em ordem; não pode passar
de `row_count`) e `notes`. Contorno e modelo de IA têm rotas próprias.

### Plano, uso e consentimento (cliente)
```
GET    /v1/tenants/current/plan             # plano, limites efetivos e uso
GET    /v1/tenants/current/data-consent     # SIM/NÃO vigente e histórico
PUT    /v1/tenants/current/data-consent     # só o dono: {"allowed": true|false}
GET    /v1/tenants/current/support-sessions # quando a equipe da ValTexa entrou
```
Criar fazenda, talhão, robô (convite e provisionamento), usuário ou missão pode
responder **`409`** (limite do plano atingido, com a conta no `detail`: "Limite do
plano Essencial atingido: 1 de 1 fazendas…") ou **`402`** (assinatura suspensa,
cancelada ou vencida). Mostre o `detail` como está. `usage[].percent` serve para
avisar a partir de 80%.

### Plataforma (equipe da ValTexa)
Exigem papel de plataforma com a capacidade da rota (ver
[`AUTHENTICATION.md`](AUTHENTICATION.md#equipe-da-valtexa-papéis-de-plataforma-brief-seção-28)).
```
POST   /v1/platform/support-sessions           # entrar como cliente (motivo, prazo)
GET    /v1/platform/support-sessions           # todas, com filtro por cliente
POST   /v1/platform/support-sessions/{id}/mode # leitura ↔ assistido (com motivo)
POST   /v1/platform/support-sessions/{id}/end  # sair (aceita o token de suporte)
GET    /v1/platform/users                      # a equipe e os papéis (superadmin)
PUT    /v1/platform/users/{id}/platform-role   # dar/trocar/tirar papel (superadmin)
GET    /v1/platform/audit                      # auditoria de todos os clientes
GET    /v1/platform/me                         # papel e capacidades (monta o menu)
GET    /v1/platform/tenants                    # clientes: plano, uso, consentimento
GET    /v1/platform/accounts                   # usuários globais e vínculos
PUT    /v1/platform/accounts/{id}/active       # bloquear/desbloquear (superadmin)
GET    /v1/platform/health                     # o /health por extenso (qualquer papel)
GET    /v1/admin/plans                         POST /v1/admin/plans
PATCH  /v1/admin/plans/{id}
GET    /v1/admin/tenants/{id}/subscription     PUT /v1/admin/tenants/{id}/subscription
GET    /v1/admin/tenants/{id}/data-consent     PUT /v1/admin/tenants/{id}/data-consent
GET    /v1/platform/fleet?tenant_id=&fleet_state=&model_divergent=   # frota de todos
GET    /v1/platform/models                     POST /v1/platform/models   # registry
GET    /v1/platform/models/{id}                PATCH /v1/platform/models/{id}
POST   /v1/platform/models/{id}/transition     # {"to": "validacao", "reason": …}
GET    /v1/platform/model-releases             POST /v1/platform/model-releases
POST   /v1/platform/model-releases/{id}/revoke
GET    /v1/platform/ai-health?days=30          # saúde da IA (seção 34)
```

**Model Registry** (Parte 3): estados `treinamento → validacao → aprovado → staging
→ producao → descontinuado`. Transição fora do ciclo, sem motivo (ao reprovar ou
descontinuar), sem métricas (ao aprovar) ou sem artefato com hash (ao publicar) →
`409` com o motivo. Aprovar exige papel `ia_dados` ou `superadmin` **e** não ser
quem registrou → `403`. Publicar descontinua a versão anterior da mesma chave
(no máximo uma em produção). Métrica e artefato não mudam depois da aprovação:
registra-se versão nova. `release_scope = clientes` restringe a versão aos
clientes com liberação ativa. Capacidades: `platform:model:read` (todos os papéis
técnicos), `platform:model:manage` e `platform:model:release` (IA & Dados,
superadmin), `platform:fleet:read` (Operações, Suporte, IA & Dados, superadmin).
`POST /v1/admin/tenants` aceita `plan_code`; sem ele o cliente nasce no plano
`piloto` (sem limites) e a resposta traz o aviso. `TenantOut` traz `plan_code`,
`plan_name` e `subscription_status`. O antigo `contracted_service` (texto livre)
continua aceito por compatibilidade, mas quem limita é o plano.

### Sessões
```
GET    /v1/auth/sessions             # meus aparelhos conectados
DELETE /v1/auth/sessions/{id}        POST /v1/auth/logout   # um / todos
DELETE /v1/users/{id}/sessions       # desliga alguém do cliente, na hora
```
Derrubar corta o acesso **imediatamente**, e não quando o token vencer — ver
[`AUTHENTICATION.md`](AUTHENTICATION.md#revogação).
Alerta é **derivado do estado**, não uma caixa de entrada: some quando a causa é
resolvida — o robô voltou, a fila esvaziou. Não há "marcar como lido"; um alerta
que se dispensa sem resolver vira alerta ignorado.

Ninguém muda o próprio papel nem remove a si mesmo (`409`): é o caminho mais
curto para um cliente ficar sem administrador.

### Notificações e suporte (Parte 6)

Brief, seções 48 e 49. **Notificação** é a caixa de entrada da pessoa (lida/não
lida) — diferente do **alerta** acima, que é estado ao vivo.

```
GET  /v1/notifications?only_unread=&limit=      GET /v1/notifications/unread-count
POST /v1/notifications/{id}/read                POST /v1/notifications/read-all
GET  /v1/notifications/preferences              PUT /v1/notifications/preferences
GET  /v1/notifications/role-preferences?role=   PUT /v1/notifications/role-preferences   # user:manage
GET  /v1/platform/notifications ...             # as mesmas, para a equipe (qualquer papel)
GET|PUT /v1/platform/notifications/role-preferences                                      # platform:role:manage
```

A caixa do cliente é da **pessoa no cliente ativo**: aviso de outra pessoa ou de
outro cliente é `404`. Preferências em três camadas: a da pessoa, a do papel (o
gestor define para o cliente; o superadmin, para a equipe) e o padrão do código —
cada item diz de onde veio (`source`: `pessoa`, `papel`, `padrao`). Corpo do `PUT`:
`{kind, enabled, channels: ["email"], threshold, reset}`; a central do console vale
sempre que o tipo está ligado; `whatsapp`, `push` e `sms` existem na interface e são
recusados (`422`, "ainda não está implementado"). `threshold` só para
`incidencia_alta` (0–100 %).

Cada aviso traz `deliveries` com o estado **honesto** do e-mail: `enviado`,
`nao_enviado` (sem `SMTP_HOST`; `last_error` diz o motivo), `falhou` (o worker tenta
de novo com espera exponencial) ou `desistiu` (6 tentativas, ou destinatário
recusado pelo servidor). Configuração: `SMTP_HOST`, `SMTP_PORT` (587),
`SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_STARTTLS`, `SMTP_SSL`,
`CONSOLE_URL` (o link no e-mail).

```
GET  /v1/support/tickets?status=&open_only=     POST /v1/support/tickets     # support:ticket
GET  /v1/support/tickets/{id}                   # conversa + histórico, sem notas internas
POST /v1/support/tickets/{id}/comments          POST /v1/support/tickets/{id}/close
POST /v1/support/tickets/{id}/reopen            # {reason}, só resolvido/fechado
GET  /v1/platform/tickets?status=&priority=&tenant_id=&incident_id=&assignee_id=&open_only=
POST /v1/platform/tickets                       # em nome de um cliente (tenant_id)
GET  /v1/platform/tickets/{id}                  # com notas internas e sessões de suporte
PATCH /v1/platform/tickets/{id}                 # status, priority, assignee_id|unassign, incident_id|unlink_incident, note
POST /v1/platform/tickets/{id}/comments         # {body, internal}
GET  /v1/platform/support/assignees
GET|POST /v1/platform/incidents                 GET|PATCH /v1/platform/incidents/{id}
POST /v1/platform/incidents/{id}/tickets        # liga chamados
```

Capacidades: ler os chamados do cliente é `tenant:read` (todo o cliente acompanha);
abrir, comentar, fechar e reabrir é `support:ticket` (dono, gestor, agrônomo,
operador, técnico — não auditor nem leitor). Na plataforma: `platform:ticket:read`
(superadmin, Suporte, Operações, IA & Dados) e `platform:ticket:manage` (superadmin,
Suporte). Robô e missão do chamado precisam ser do próprio cliente (`404`). Status:
`aberto → em_atendimento → aguardando_cliente → resolvido → fechado`; atribuir
responsável a um chamado aberto o põe em atendimento; a resposta do cliente a um
chamado `aguardando_cliente` ou `resolvido` o devolve à fila. Tudo vai para o
histórico do chamado e para a auditoria (`ticket.*`, `incident.*`).

`POST /v1/platform/support-sessions` aceita `ticket_id` (do mesmo cliente, senão
`404`): a sessão nasce com `ticket_ref` = código do chamado, e o histórico do
chamado mostra ao cliente que a equipe entrou por causa dele.

### Observabilidade e alertas (Parte 7)

Brief, seções 34 e 35; o detalhe está em `docs/OBSERVABILIDADE.md` (raiz). Os
**alertas de observabilidade** têm estado próprio (`disparado → reconhecido →
resolvido`) e não são os alertas derivados do painel (`GET /v1/alerts`, acima).

```
GET  /metrics                                         # Prometheus: Bearer METRICS_TOKEN ou equipe (platform:observability:read)
GET  /v1/platform/observability?minutes=              # componentes, API, filas, usuários, IA, alertas abertos
GET  /v1/platform/observability/api?minutes=          # por rota (molde): requisições, 4xx, 5xx, p50/p95/máx.
GET  /v1/platform/observability/fleet?tenant_id=      # saúde de cada robô (todos os clientes)
GET  /v1/platform/observability/ai?hours=             # nuvem e borda por modelo, classes, drift
GET  /v1/platform/observability/alerts?state=&kind=&tenant_id=&open_only=
POST /v1/platform/observability/alerts/{id}/ack       # {note}; platform:alert:manage
GET  /v1/platform/observability/alert-rules           PUT /v1/platform/observability/alert-rules/{kind}
GET  /v1/observability/fleet                          # cliente: só os robôs dele (device:read)
GET  /v1/observability/alerts?state=&kind=&open_only= # cliente: só os alertas dos robôs dele
POST /v1/observability/alerts/{id}/ack                # device:manage
GET  /v1/observability/alert-rules                    # regras de robô, com a versão do cliente
PUT|DELETE /v1/observability/alert-rules/{kind}       # versão própria do cliente (device:manage)
```

Corpo da regra: `{enabled, threshold, window_minutes, severity}` (só o que vier muda;
regra sem limite recusa `threshold`, `%` vai de 0 a 100, distância de 0 a 1 → `422`).
Regra da plataforma por cliente → `403`. Toda resposta leva `X-Request-Id`; a de erro
500 traz também `request_id` no corpo. A telemetria do robô aceita `health` (saúde
padronizada; ver `docs/OBSERVABILIDADE.md` §4).

`rover_offline` não tem versão por cliente (o aviso dele é só da equipe): o `PUT` do
cliente dá `403`. Regra padrão desligada pela equipe vale também para quem tem cópia.
Reconhecer um alerta que o worker acabou de resolver dá `409`.

### Telas da Parte 8: mapa, relatório, linha do tempo, painel

Brief, seções 45, 46 e 47. Todas no escopo do cliente (`get_scoped`), cobertas pelo
teste de isolamento gerado do OpenAPI e por `tests/test_visao_operacional.py`.

```
GET  /v1/dashboard                                   # + overview: fazendas, talhões, hectares, ocorrências 7 d,
                                                     #   varreduras 30 d, sync por robô, saúde da frota e da IA
GET  /v1/missions/{id}/map                           # track (≤ 2000 posições, na ordem), planned_route, events
                                                     #   (resultados-evento da Edge AI com posição), plants (estado)
GET  /v1/missions/{id}/report | /plants | /comparison?baseline_id=   # (Parte 5) relatório, plantas, comparação
GET  /v1/fields/{id}/history?missions=30             # missão → ocorrências → prescrição → aprovação →
                                                     #   aplicação → verificação, do mais novo ao mais antigo
GET  /v1/edge/records?mission_id=&type=&kind=&limit=&offset=      # (Parte 4) registros da Edge AI
GET  /v1/edge/records/{id}/files/{upload_id}         # o arquivo (original, reduzida) de um registro
```

O relatório exportável (CSV com `;` e BOM, e impressão para PDF) é montado no console a
partir de `/report` e `/plants` — nada é recalculado. Pela tela da plataforma, agora:
`POST /v1/platform/ota/packages` (o `.tar` como corpo), `POST /v1/platform/ota/deployments`
e `POST /v1/platform/models/{id}/optimizations` (o relatório do `dnaty_pipeline.py`).

---

## Os quatro fluxos que a tela precisa acertar

### 1. Varredura

```
criar missão -> authorize -> dispatch -> acompanhar
```

`authorize` devolve o parecer completo, **inclusive as verificações que
passaram**. Quando bloqueia, mostre a lista inteira: o operador precisa ver tudo
que falta de uma vez, não descobrir um impedimento por tentativa.

`POST /v1/missions/{id}/safety/preview` roda as verificações **sem gravar nem
mudar estado** — ideal para validar enquanto o operador ainda monta a missão.

### 2. Fila do agrônomo

```
GET /v1/review/queue                      ordenada por novidade decrescente
GET /v1/review/queue?order=valor          o que mais ensina primeiro, com priority_reasons
GET /v1/observations/{id}/image           a foto
POST /v1/diagnoses/{id}/review            o veredito
```

O campo `label` da revisão é **texto livre validado**: pode ser um nome que não
existe no catálogo do modelo. É assim que uma doença nova entra no dataset
próprio, e a interface não deve limitar a um `select` das classes conhecidas.

Mostre sempre, lado a lado: o palpite da máquina, a confiança e a pontuação de
novidade. O agrônomo decide melhor sabendo o que a máquina respondeu e o quanto
ela estranhou.

### 3. Pulverização

```
criar (spray) -> approve (agrônomo) -> carregar tanque -> authorize -> dispatch
```

A ordem importa e a tela deve refletir isso. Erros esperados, que **não** são
bugs:

| Bloqueio | O que mostrar |
|---|---|
| `approval` | "aguardando aprovação do agrônomo" |
| `tank_content` | "o tanque está com outro produto" |
| `weather` | "sem leitura de vento — verifique a dock" |
| `rtk` | "o drone não tem correção RTK fixa" |

Ver [`SAFETY.md`](SAFETY.md) para a lista completa de códigos.

### 4. Gêmeo digital

```
GET /v1/fields/{id}/snapshot?days=7       retrato
GET /v1/fields/{id}/timeline?days=30      série diária
GET /v1/fields/{id}/anomalies             desvios estatísticos
GET /v1/fields/{id}/scene?at=&days=30     a cópia 3D
GET /v1/row-scans/{id}/pointcloud         a nuvem de pontos de uma rua (PLY)
```

`anomalies` merece destaque na interface: é a detecção que funciona quando a de
novidade falha, e cada item é um convite a inspeção presencial. Ver
[`AI_PIPELINE.md`](AI_PIPELINE.md) para o porquê.

`scene` é a cópia 3D montada rua a rua pelo rover. É pesada — uma entrada por
planta, em colunas (`plants.x[]`, `plants.y[]`, `plants.height[]`...) para
caber —, então o console só a busca de novo quando o stream traz
`row_scan.received`. Coordenadas em metros no plano do talhão (origem no centro
do limite, x leste, y norte). Cada marcador traz `category` (`pest`, `disease`,
`review`, `other`, `healthy`) e `plant`, o índice da planta fotografada. Ver
[`DIGITAL_TWIN.md`](DIGITAL_TWIN.md#cópia-3d).

---

## Convenções

| | |
|---|---|
| Horários | ISO 8601 com fuso, sempre UTC — converta para o fuso da fazenda na exibição |
| Coordenadas | `[longitude, latitude]`, ordem do GeoJSON |
| Polígonos | anel sem repetir o primeiro ponto no fim |
| Paginação | `limit` e `offset`; o teto de `limit` é aplicado no servidor |
| Erros | sempre `{"detail": "mensagem legível em português"}` |

| Código | Significado no produto |
|---|---|
| `400` | requisição malformada |
| `401` | token ausente, inválido ou vencido → voltar ao login |
| `403` | o papel não permite → esconder a ação, explicar |
| `404` | não existe **ou é de outro cliente** (indistinguível, de propósito) |
| `409` | conflito de estado → recarregar e mostrar o estado real |
| `413` | arquivo ou lote grande demais |
| `422` | campo inválido |
| `503` | dependência fora do ar |

---

## Tempo real

`GET /v1/stream` entrega os eventos de domínio do cliente por *Server-Sent
Events*:

```
retry: 3000

id: 7f3c…
event: mission.completed
data: {"id": "7f3c…", "name": "mission.completed", "subject_type": "mission",
       "subject_id": "…", "payload": {…}, "created_at": "2026-09-10T21:00:00+00:00"}
```

- **Conexão com prazo.** Depois de `timeout` (padrão 300 s) o servidor manda
  `event: stream.end` com `{"after": "<cursor>"}` e fecha; o cliente reconecta
  passando `after`. Uma conexão eterna sobreviveria a um token vencido e a um
  deploy.
- **Autorização por cabeçalho**, então `EventSource` não serve — ele não aceita
  cabeçalho. Leia com `fetch` e `ReadableStream`, como faz
  `web/src/lib/stream.ts`.
- `: keepalive` a cada 15 s impede que um proxy corte a conexão ociosa.

O evento é aviso, não dado: ao receber `mission.completed`, invalide a consulta
da missão e busque de novo. Assim, uma reconexão que perdeu um evento deixa a
tela no máximo desatualizada até o próximo *refetch* — nunca errada.

Onde o SSE não passa (alguns proxies corporativos), o *polling* resolve. Desde
que `/v1/stream` existe, esses intervalos deixaram de ser o mecanismo e passaram
a ser a rede embaixo dele — por isso são largos: encurtá-los seria pagar duas
vezes pelo mesmo dado.

| O quê | Intervalo | Por quê este |
|---|---|---|
| frota | 30 s | rede de segurança; o evento chega antes |
| painel e alertas | 60 s | idem |
| telemetria de um robô | 15 s | **é o mecanismo**, não a rede |
| gêmeo digital | sob demanda | — |

A telemetria é a exceção e vale dizer por quê: ela não vira evento de *outbox*.
Uma amostra por segundo por robô transformaria a tabela de eventos numa série
temporal e o fluxo ao vivo numa enxurrada que ninguém lê.

`GET /v1/events?pending_only=true` mostra a fila do *outbox* — útil numa tela de
operação: um evento parado com `last_error` preenchido é a primeira pista de que
uma integração quebrou.

---

## Gerando o cliente

```bash
uvicorn valtexa.main:app &
curl http://127.0.0.1:8000/openapi.json > openapi.json
npx openapi-typescript openapi.json -o src/api/schema.d.ts
```

Os esquemas de saída são achatados de propósito — o cliente recebe
identificadores e valores, nunca o objeto ORM serializado por reflexão. Assim,
adicionar uma coluna interna não vaza para a API por acidente.
