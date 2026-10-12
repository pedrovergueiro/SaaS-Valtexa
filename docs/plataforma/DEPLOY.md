# Deploy de produção (Parte 9 — brief, seções 36, 37, 38, 51 e 57)

> Como colocar a ValTexa no ar para o piloto. O que **está em código e testado** e o que é
> **passo de deploy** (depende de infra contratada) está separado em cada seção. Segurança
> e rotação de segredos: [`SEGURANCA.md`](SEGURANCA.md). Métricas e alertas:
> [`OBSERVABILIDADE.md`](OBSERVABILIDADE.md).

## 1. O desenho

```
            internet
               │ 443 (TLS, Let's Encrypt)
         ┌─────▼─────┐
         │   Caddy   │  HSTS · /metrics bloqueado · corpo ≤ 80 MB
         └─────┬─────┘
     round-robin (DNS do Docker, "api")
      ┌────────┴────────┐
 ┌────▼────┐       ┌────▼────┐        ┌──────────┐
 │ API #1  │  ...  │ API #N  │        │  worker  │  (um; python -m valtexa.worker)
 │+console │       │+console │        └────┬─────┘
 └──┬──┬──┬┘       └──┬──┬──┬┘             │
    │  │  └───────────┼──┼──┼──────────────┤
    │  │   Redis ◀────┘  │  │  limite de taxa dos robôs, travas, "uma vez por ciclo"
    │  └── S3/MinIO ◀────┘  │  imagens, nuvens de pontos, OTA, chunks em _staging/
    └───── Postgres ◀───────┘  metadados, filas (jobs, outbox), auditoria
                 IA (VALTEXA-B) ◀── API (token de serviço)     Prometheus ──▶ API, IA
```

- **API**: FastAPI + console React (o `web/dist` vai dentro da imagem e é servido em `/`).
  Sem estado local: qualquer réplica atende qualquer requisição, inclusive o chunk 3 de
  um upload cujo chunk 2 foi para outra réplica (o *staging* está no bucket).
- **Worker**: entrega de eventos e avisos, coletas, vencimento de missões, robô sumido,
  retenção, alertas. Um processo. Dois por engano não duplicam as tarefas periódicas (a
  marca fica no Redis); filas de trabalho já eram disputadas no banco (`SELECT … FOR
  UPDATE SKIP LOCKED`/`locked_by`).
- **IA**: serviço próprio (`ia/`), na rede interna, atrás do `SERVICE_TOKEN`.
- **Postgres** (metadados), **S3/MinIO** (objetos), **Redis** (coordenação), **Prometheus**.

## 2. O que está em código (e onde está o teste)

| Peça | Código | Prova |
| --- | --- | --- |
| Object storage S3: objetos por hash e prefixo do cliente, multipart (> 8 MB, partes de 8 MB, aborta se uma falhar), etiqueta `categoria` | `saas/valtexa/services/storage.py` (`S3ObjectStore`) | `tests/test_producao_s3.py` (S3 por HTTP: `moto` em modo servidor + `boto3` real) |
| *Staging* de chunks compartilhado entre réplicas (Rover e coletas) | `storage.S3ChunkStaging`, usado por `edge_sync` e `collections` quando `STORAGE_BACKEND=s3` | upload que troca de réplica no meio; >1000 chunks (listagem paginada); coleta em pedaços |
| URL assinada (SigV4, curta) para o cliente baixar imagem | `GET /v1/observations/{id}/image/url`, `GET /v1/edge/records/{id}/files/{upload_id}/url` | verificador SigV4 independente: válida, adulterada para outro objeto (inválida), vencida, outro cliente (404) |
| Lifecycle por categoria | `storage.politica_de_ciclo_de_vida` + `python -m valtexa.services.storage --ciclo-de-vida` | política gravada e relida do bucket |
| Limite de taxa e travas entre réplicas | `saas/valtexa/services/coordenacao.py` (memória / Redis com Lua) | `tests/test_coordenacao.py` (memória, `fakeredis` e **`redis-server` real**): limite somado entre duas réplicas, concorrência, trava vencida, worker duplo, 429 pela API |
| Segredos: produção recusa vazios, padrão, curtos, de exemplo ou iguais entre si; leitura por arquivo | `config.Settings.secret_problems`, `recusar_se_inadequado` (API e worker), `SECRETS_DIR` | `tests/test_segredos.py` |
| Banco: migrações no Postgres | `saas/migrations` (0001–0025) | do zero até 0025, `downgrade -1`, `upgrade head` no Postgres 16; suíte completa no Postgres |
| Compose de produção | `deploy/producao/` | `docker compose config` válido; o `Settings` lido com os segredos gerados dá **zero** pendências (§ 6) |

## 3. Passo a passo (um host com Docker)

```bash
cd deploy/producao
./gerar-segredos.sh                              # ./segredos/* (fora do Git), valores de 64 caracteres
cp -r /caminho/dos/pesos/* modelos/              # pesos da IA: NÃO estão no repositório
export DOMINIO=app.suaempresa.com.br             # DNS apontando para o host (Caddy tira o certificado)
docker compose up -d db redis minio              # infraestrutura
docker compose --profile preparar run --rm armazenamento   # cria o bucket e grava o lifecycle
docker compose up -d --build                     # API (2 réplicas), worker, IA, Prometheus, proxy
docker compose logs -f api | grep -i pendência   # nada: em produção, pendência = não sobe
```

Primeiro acesso: a equipe ValTexa entra com o e-mail de `PLATFORM_TEAM` (`saas/valtexa/seed.py`)
e a senha de `segredos/platform_admin_password`; troque-a no console. O cliente é criado
pelo console da plataforma (papel Comercial), como no ponta a ponta.

Robôs: o Rover é provisionado contra `https://$DOMINIO` (token de provisionamento gerado
no console) e grava a chave pública da plataforma e a de OTA — ver `docs/ROVER_RUNTIME.md`
e `rover/deploy/`.

### Variáveis que importam (além dos segredos)

| Variável | Produção | Por quê |
| --- | --- | --- |
| `ENVIRONMENT` | `production` | liga as travas de subida |
| `STORAGE_BACKEND`, `S3_BUCKET`, `S3_ENDPOINT_URL`, `S3_ADDRESSING_STYLE` | `s3`, bucket, endpoint (vazio = AWS), `path` no MinIO | § 2 |
| `S3_PRESIGN_SECONDS` | 300 (30–3600) | validade da URL assinada |
| `S3_STAGING_DAYS`, `S3_INFREQUENT_AFTER_DAYS`, `S3_ARCHIVE_AFTER_DAYS`, `S3_LOGS_EXPIRE_DAYS` | 3 / 30 / 365 / vazio | lifecycle (§ 4) |
| `EVENT_WORKER_IN_API` | `false` | o worker é um processo à parte |
| `LOG_FORMAT` | `json` | agregador de logs |
| `INFERENCE_URL` | `http://ia:8000` | IA na rede interna |
| `CORS_ORIGINS`, `CONSOLE_URL` | `https://$DOMINIO` | sem `*` |
| `SMTP_*` | do provedor | sem SMTP, o aviso fica só na central ("não enviado") |

## 4. Armazenamento (seção 38)

- **Chave** = `{prefixo}/{cliente}/{aa}/{bb}/{sha256}{ext}`: nada de nome vindo de fora,
  reenvio não duplica, apagar os dados de um cliente é apagar um prefixo.
- **Banco só com metadados** (seção 37): `asset` guarda chave, hash, tamanho, tipo.
- **Lifecycle por categoria** (etiqueta `categoria` gravada em cada objeto):

  | Categoria | Regra padrão |
  | --- | --- |
  | `_staging/` (chunks de upload) | expira em 3 dias (o worker já apaga o upload abandonado em 72 h; isto é a rede de segurança) |
  | multipart incompleto | abortado em 1 dia |
  | `imagem`, `nuvem_pontos` | STANDARD_IA em 30 d, GLACIER_IR em 365 d — **sem expiração**: apagar foto de cliente é decisão de contrato |
  | `log` | expira em `S3_LOGS_EXPIRE_DAYS` se definido; senão, nunca |
  | `ota` | nada (o pacote precisa existir enquanto houver robô nele) |

  No **MinIO** sem camada remota, transição de classe não existe: o compose desliga as
  duas transições (`S3_INFREQUENT_AFTER_DAYS=` e `S3_ARCHIVE_AFTER_DAYS=` vazios).
- **Download pelo cliente**: a rota antiga (`/image`, `/files/...`) continua servindo os
  bytes pela API; a nova `.../url` devolve uma URL assinada de 5 min **depois** do escopo
  do cliente conferido. Com disco local, ela devolve a própria rota (`direct: false`). O
  console ainda usa a rota antiga — trocar é uma melhoria de banda, não de segurança.
- **CORS do bucket**: para o navegador abrir a URL assinada direto num `<img>` não precisa
  CORS; para `fetch` precisa liberar `GET` para `https://$DOMINIO`.
- **Migrar do disco para o S3**: as chaves são as mesmas — copiar `STORAGE_DIR/` para
  `s3://bucket/valtexa/` (`aws s3 sync`/`mc mirror`) e trocar `STORAGE_BACKEND`.

## 5. Banco (seção 37)

- **Migrações** rodam na subida da API (`lifespan` → `alembic upgrade head`), protegidas
  pelo lock do Alembic. Antes de um deploy com migração: `pg_dump`.
- **Índice em tabela grande com a aplicação no ar**: a 0025 cria índices; num banco já
  grande, crie antes à mão `CREATE INDEX CONCURRENTLY ix_… ON …` com o mesmo nome — a
  migração usa `if_not_exists` e passa direto.
- **Backup**: `pg_dump -Fc` diário + WAL (ou o PITR do Postgres gerenciado). Restauração
  testada: `pg_restore -d valtexa_novo arquivo.dump` e `alembic current` deve dizer a head.
- **Pool**: cada réplica abre o pool do SQLAlchemy; some réplicas × pool < `max_connections`
  (ou use PgBouncer em modo transação).

## 6. Como foi verificado aqui (sem infra real)

- Suíte completa do SaaS no **Postgres 16** local (`TEST_DATABASE_URL`), migrações do zero
  até a 0025 e ida e volta.
- S3 contra o `moto` em modo servidor (HTTP real, `boto3` real). **MinIO não pôde ser
  baixado nesta sessão** (bloqueado pela rede); a AWS real também não foi usada.
- Redis contra `redis-server` 7.0 real e `fakeredis`.
- **Ensaio de produção sem Docker** (o daemon não roda nesta sessão): `ENVIRONMENT=production`,
  segredos de `deploy/producao/gerar-segredos.sh` lidos por arquivo, Postgres 16,
  `redis-server` com senha, S3 do `moto`, **duas réplicas** da API (uvicorn) e o worker —
  números em `docs/PROGRESSO.md` (Parte 9).
- `docker compose config` do `deploy/producao/` válido. **As imagens não foram construídas
  nem os contêineres subidos aqui** (sem daemon do Docker).

## 7. O que é passo de deploy (fora do código)

1. Contratar: Postgres gerenciado (ou o do compose com backup), bucket S3 (ou MinIO com
   disco redundante), Redis (ou o do compose), domínio + DNS, SMTP.
2. Copiar os **pesos** da IA para `deploy/producao/modelos/` (e registrar no Model Registry).
3. Política de bucket: bloquear acesso público; a credencial da plataforma só com
   `s3:GetObject/PutObject/DeleteObject/ListBucket/PutLifecycleConfiguration` no bucket.
4. Ligar o Prometheus ao Alertmanager (regras em `deploy/observabilidade/regras.yml`);
   Grafana pelo compose de `deploy/observabilidade/`.
5. Backups (Postgres e bucket — versionamento do bucket ou réplica noutra região).
6. Robôs: imagem do sistema com `rover/deploy/valtexa-rover.service`, LUKS e *secure boot*
   (dependem do computador embarcado escolhido).

## 8. Troubleshooting

| Sintoma | Causa provável |
| --- | --- |
| API não sobe: `Configuração inadequada para produção` | a lista diz qual segredo/variável; ver `SEGURANCA.md` § 2 |
| Robô recebe 429 com `Retry-After` | limite por robô (`DEVICE_RATE_PER_MINUTE`, padrão 1200/min, somado entre réplicas) |
| `complete` do upload devolve 409 "sendo montado" | outra réplica está montando o mesmo arquivo; o Rover tenta de novo |
| 413 em `/v1/device/...` | corpo acima de `MAX_ASSET_MB` + 1 MB (antes da autenticação) |
| Upload de coleta "rejected: não é uma imagem" | o conteúdo não é JPEG/PNG/WebP/TIFF, seja qual for a extensão |
| Lifecycle recusado pelo MinIO | transição de classe sem camada remota: deixe `S3_*_AFTER_DAYS` vazios |
