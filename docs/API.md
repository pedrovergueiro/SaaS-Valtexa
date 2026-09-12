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

`GET /v1/auth/me` devolve identidade, papel, capacidades e todas as associações.

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
```
A área (`area_ha`) é **derivada do polígono**, nunca informada: um número
digitado à mão divergiria do desenho, e é ele que manda na dose e na cerca.

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

### Missões
```
GET  /v1/missions                    POST /v1/missions
GET  /v1/missions/{id}               GET  /v1/missions/{id}/segments
POST /v1/missions/{id}/approve       POST /v1/missions/{id}/authorize
POST /v1/missions/{id}/dispatch      POST /v1/missions/{id}/resume
POST /v1/missions/{id}/abort
GET  /v1/missions/{id}/safety        POST /v1/missions/{id}/safety/preview
GET  /v1/missions/{id}/history       GET  /v1/missions/{id}/checkpoints
```
`history` é a linha do tempo da missão — cada transição, com quem e por quê —,
legível por quem opera, sem precisar da permissão de auditoria.

### Percepção
```
GET  /v1/observations                GET  /v1/observations/{id}/image
GET  /v1/diagnoses                   GET  /v1/review/queue
POST /v1/diagnoses/{id}/review       POST /v1/diagnoses/{id}/decide
GET  /v1/decisions
```

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
Alerta é **derivado do estado**, não uma caixa de entrada: some quando a causa é
resolvida — o robô voltou, a fila esvaziou. Não há "marcar como lido"; um alerta
que se dispensa sem resolver vira alerta ignorado.

Ninguém muda o próprio papel nem remove a si mesmo (`409`): é o caminho mais
curto para um cliente ficar sem administrador.

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

Onde o SSE não passa (alguns proxies corporativos), o *polling* resolve:

| O quê | Intervalo |
|---|---|
| lista de frota | 10 s |
| missão em execução | 5 s |
| fila do agrônomo | 60 s |
| gêmeo digital | sob demanda |

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
