# Implantação

## O que a plataforma exige para ser produção

`Settings.production_problems()` lista o que falta, e com
`ENVIRONMENT=production` o `lifespan` **recusa subir** enquanto a lista não
estiver vazia. Falhar no start é melhor do que descobrir depois que o sistema
está assinando comandos com um segredo público.

| Impedimento | Correção |
|---|---|
| `SESSION_SECRET` no padrão | gerar um novo |
| `COMMAND_SIGNING_SECRET` no padrão | gerar um novo |
| os dois iguais | **precisam ser diferentes** |
| SQLite | migrar para Postgres |
| `CORS_ORIGINS` com `*` | listar as origens |
| `SIMULATED_INFERENCE` ligado | desligar |
| IA ligada sem `INFERENCE_SERVICE_TOKEN` | gerar um token e configurar o **mesmo** valor em `SERVICE_TOKEN` no servidor de IA (`ia/`) |

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

**Por que os segredos precisam ser diferentes:** se fossem iguais, vazar a sessão
de um usuário passaria a permitir forjar uma missão assinada. A fronteira entre
"alguém entrou na conta" e "alguém mandou o drone pulverizar" desapareceria.

`/health` diz **quantas** pendências há em qualquer ambiente — use como alerta. O
texto de cada uma (e o endereço da IA) só aparece para a equipe, em
`/v1/platform/health` e na tela "Saúde do sistema" do console `/plataforma`: o
`/health` não tem autenticação, e "SESSION_SECRET ainda é o padrão" é mapa de ataque.

---

## Docker

```bash
export POSTGRES_PASSWORD=...
export SESSION_SECRET=...
export COMMAND_SIGNING_SECRET=...
export CORS_ORIGINS=https://app.valtexa.com.br
docker compose up -d --build
```

O `docker-compose.yml` sobe dois serviços da mesma imagem, mais o Postgres:

| Serviço | O que roda |
|---|---|
| `api` | a API e o console, na porta 8080; aplica as migrações ao subir |
| `worker` | `python -m valtexa.worker` — eventos, expiração, conectividade, retenção |
| `db` | Postgres 16 |

A imagem é construída em dois estágios: o primeiro, com Node, compila o console;
o segundo, só com Python, recebe o `web/dist` pronto. Node não vai para
produção.

O serviço de inferência (`VALTEXA-B`) fica **de fora de propósito**: ele precisa
de GPU e de uma faixa de Python diferente, então tem ciclo de vida próprio.
Aponte `INFERENCE_URL`.

A imagem não carrega Keras nem TensorFlow. É o que a mantém em poucas centenas de
MB e permite escalar a API sem GPU.

---

## O console

A API serve o console no mesmo endereço. `/` e qualquer caminho fora de `/v1`,
`/docs` e `/health` devolvem o `index.html`, e o roteamento acontece no
navegador. Um `/v1/...` inexistente continua respondendo `404` em JSON: o
*fallback* do SPA nunca mascara erro de API.

Mesma origem significa console sem CORS. `SERVE_WEB=false` desliga o console na
API — para servi-lo por CDN, por exemplo; nesse caso `CORS_ORIGINS` precisa
listar a origem dele.

Em desenvolvimento, o Vite serve com recarga e faz *proxy* de `/v1` para a API:

```bash
cd web && npm install && npm run dev      # http://127.0.0.1:5173
```

---

## Banco

SQLite é o padrão e serve o desenvolvimento. **Não serve produção**: a ingestão
de telemetria escreve concorrentemente e o SQLite serializa — com poucos robôs a
escrita já vira gargalo.

```
DATABASE_URL=postgresql+psycopg://valtexa:senha@host:5432/valtexa
```

A suíte de testes roda nos dois: `TEST_DATABASE_URL=postgresql+psycopg://...
pytest`.

### Migrações

O esquema é versionado com Alembic, em `migrations/`. **A API aplica
`alembic upgrade head` ao subir**: um deploy com migração nova não pede passo
manual, e uma migração que falha impede o processo de subir em vez de deixá-lo
rodar contra um esquema pela metade.

Um banco criado antes do Alembic, pelo antigo `create_all()`, é reconhecido — tem
as tabelas e não tem `alembic_version`. Ele é marcado na revisão base (`0001`) e
segue dali, sem recriar nada.

Mudou um modelo? Gere a revisão e **leia antes de commitar**:

```bash
alembic revision --autogenerate -m "o que mudou"
alembic upgrade head
```

O *autogenerate* não enxerga tudo — uma renomeação vira remoção mais criação, e
os dados se perdem. No SQLite, as migrações rodam em modo *batch* (a tabela é
recriada), porque o SQLite não altera coluna; o `env.py` desliga as chaves
estrangeiras durante a cópia e as religa depois.

`create_all()` só existe nos testes.

Uma escolha ajuda aqui: os `enum` são gravados como `VARCHAR` sem `CHECK`. Um
rótulo novo no vocabulário **não** exige migração — e o vocabulário do domínio
ainda vai crescer.

---

## Armazenamento de objetos

Padrão: disco local em `STORAGE_DIR`, com chave prefixada por cliente e derivada
do `sha256` do conteúdo.

O prefixo por cliente existe para que atender um pedido de exclusão de um cliente
não apague o arquivo de outro que enviou bytes idênticos. Custa duplicar
conteúdo repetido entre clientes, e devolve a possibilidade de apagar.

Para S3 ou compatível (MinIO, Cloudflare R2):

```
STORAGE_BACKEND=s3
S3_BUCKET=valtexa-assets
S3_PREFIX=valtexa             # opcional
S3_ENDPOINT_URL=https://...   # só para MinIO/R2; vazio usa a AWS
S3_REGION=sa-east-1
```

As credenciais seguem a cadeia padrão do `boto3` — variáveis `AWS_*`, perfil ou
papel da instância —, nunca num `.env` versionado. A chave é derivada do mesmo
jeito nos dois armazenamentos (cliente + `sha256`). Nenhum código de domínio
abre arquivo diretamente: tudo passa por
[`valtexa/services/storage.py`](../valtexa/services/storage.py).

Com disco local em contêiner, **monte um volume**: sem isso as imagens somem no
próximo deploy.

---

## O worker

`python -m valtexa.worker` roda um laço de 5 s:

| Tarefa | A cada | Por quê |
|---|---|---|
| drenar o *outbox* | 5 s | entrega os eventos de domínio aos handlers |
| expirar missões vencidas | 30 s | missão fora da validade não pode seguir para o robô |
| recalcular a conectividade | 60 s | robô sem contato vira `offline` mesmo que ninguém consulte |
| retenção | 6 h | agrega telemetria antiga, apaga nonces vencidos e eventos entregues |

`--once` roda um ciclo e sai — serve para cron e para depurar.

Em desenvolvimento, o mesmo worker roda numa thread dentro da API, para tudo
caber num processo. Em produção, use `EVENT_WORKER_IN_API=false` na API e o
serviço `worker` à parte, como no `docker-compose.yml`. Com várias réplicas da
API drenando a mesma fila, a entrega continua correta — é ao-menos-uma-vez e os
handlers são idempotentes —, mas é trabalho em dobro.

---

## Escala

| Componente | Como cresce |
|---|---|
| API | horizontal, sem estado |
| Worker | um processo; a fila é do banco |
| Postgres | vertical primeiro; particionar `telemetry_sample` depois |
| Armazenamento | `STORAGE_BACKEND=s3` quando o disco local incomodar |
| Inferência | separado, com GPU; é o gargalo de custo |

O que cresce primeiro é `telemetry_sample`. A retenção já agrega o que passa de
`TELEMETRY_RETENTION_DAYS`; o resto do plano está em
[`TELEMETRY.md`](TELEMETRY.md).

**Sessões não colam em nada.** Toda a autenticação é por token e assinatura,
então o balanceador não precisa de afinidade. O `/v1/stream` (SSE) é uma conexão
longa, mas sem estado no servidor: o cliente reconecta com o cursor `after` em
qualquer réplica.

---

## Observabilidade

`/health` responde `200` enquanto o processo estiver de pé (*liveness*); o corpo
diz se o banco e a inferência estão acessíveis (*readiness*), sem detalhe interno
(`database` só `ok`/`erro`, `inference` só `ligado`/`desligado`, cada pendência
como linha genérica):

```json
{"status": "ok", "environment": "production", "protocol_version": "1.0",
 "database": "ok", "inference": "ligado", "pending_events": 3, "warnings": []}
```

O mesmo diagnóstico por extenso (URL da IA, tipo do erro do banco, texto das
pendências) fica em `GET /v1/platform/health`, para qualquer papel da equipe.

O que vale alertar:

| Sinal | Por quê |
|---|---|
| `pending_events` crescendo | o worker parou ou um handler quebrou |
| `warnings` não vazio | configuração inadequada |
| dispositivos em `offline` | frota sem contato |
| `application.out_of_bounds` | **incidente**: calda fora da área autorizada |
| `safety.blocked` recorrente | algo sistematicamente errado no cadastro |

Os logs são estruturados por módulo. Em produção, `LOG_LEVEL=INFO`; `DEBUG`
inclui o corpo das requisições e **não deve ir para produção**.

---

## Segurança operacional

- **TLS obrigatório.** A assinatura garante integridade e autenticidade, não
  confidencialidade: sem TLS, a telemetria e as imagens trafegam em claro.
- **Rotação de credencial de robô:** `POST /v1/devices/{id}/revoke-credentials`
  e reprovisionamento presencial. Não há rotação remota — de propósito: um
  caminho remoto para trocar a chave de um robô é um caminho remoto para
  sequestrá-lo.
- **Backup:** o banco e o armazenamento juntos. O `sha256` de cada `Asset`
  permite verificar a integridade de uma restauração.
- **`audit_entry` nunca é removido.** Auditoria que pode ser alterada não é
  auditoria.

---

## Checklist de primeiro deploy

- [ ] `ENVIRONMENT=production`
- [ ] segredos gerados, diferentes entre si, num gerenciador de segredos
- [ ] Postgres, com backup automático testado (restaurar, não só gerar)
- [ ] `STORAGE_DIR` em volume persistente, ou `STORAGE_BACKEND=s3`
- [ ] `CORS_ORIGINS` com as origens reais
- [ ] TLS terminado antes da aplicação
- [ ] `INFERENCE_URL` apontando para o `VALTEXA-B`
- [ ] `INFERENCE_SERVICE_TOKEN` (SaaS) = `SERVICE_TOKEN` (IA): sem ele a IA fica aberta
- [ ] `EVENT_WORKER_IN_API=false` na API e o `worker` no ar
- [ ] `/health` monitorado, com alerta em `pending_events` e `warnings`
- [ ] depois do deploy, `alembic current` igual a `alembic heads`
- [ ] catálogo de `device_model` conferido
- [ ] **nenhum dado de demonstração** (`seed_demo` só roda no simulador e nos testes)
