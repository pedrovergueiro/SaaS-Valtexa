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

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

**Por que os segredos precisam ser diferentes:** se fossem iguais, vazar a sessão
de um usuário passaria a permitir forjar uma missão assinada. A fronteira entre
"alguém entrou na conta" e "alguém mandou o drone pulverizar" desapareceria.

`/health` mostra a mesma lista em qualquer ambiente — use como alerta.

---

## Docker

```bash
export POSTGRES_PASSWORD=...
export SESSION_SECRET=...
export COMMAND_SIGNING_SECRET=...
export CORS_ORIGINS=https://app.valtexa.com.br
docker compose up -d --build
```

O `docker-compose.yml` sobe a plataforma e o Postgres. O serviço de inferência
(`VALTEXA-B`) fica **de fora de propósito**: ele precisa de GPU e de uma faixa de
Python diferente, então tem ciclo de vida próprio. Aponte `INFERENCE_URL`.

A imagem não carrega Keras nem TensorFlow. É o que a mantém em poucas centenas de
MB e permite escalar a API sem GPU.

---

## Banco

SQLite é o padrão e serve o desenvolvimento. **Não serve produção**: a ingestão
de telemetria escreve concorrentemente e o SQLite serializa — com poucos robôs a
escrita já vira gargalo.

```
DATABASE_URL=postgresql+psycopg://valtexa:senha@host:5432/valtexa
```

### Migrações

O esquema é criado por `create_all()`. **Antes do primeiro dado real em
produção, Alembic precisa entrar.**

```bash
pip install alembic
alembic init migrations
# em env.py: target_metadata = valtexa.models.Base.metadata
alembic revision --autogenerate -m "esquema inicial"
```

A partir daí, remova a chamada a `create_all()` do `lifespan` e rode
`alembic upgrade head` no deploy. Enquanto isso não existir, qualquer alteração
de coluna em produção é manual — e é a maior dívida técnica aberta do projeto.

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

Para S3/MinIO, implemente o protocolo `ObjectStore` em
[`valtexa/services/storage.py`](../valtexa/services/storage.py) e troque a
instância `store`. Nenhum código de domínio abre arquivo diretamente.

Em contêiner, **monte um volume**: sem isso as imagens somem no próximo deploy.

---

## O drenador de eventos

Em desenvolvimento, uma thread no processo da API drena o *outbox* a cada 5 s.
Simples, e mantém tudo num container só.

Em produção, com mais de uma réplica da API, todas drenariam a mesma fila. A
entrega é ao-menos-uma-vez e os handlers são idempotentes, então isso é correto —
mas é trabalho duplicado.

O caminho: mover para um worker separado. **Nada no código muda**, só onde ele
roda:

```python
# worker.py
from valtexa.db import session_scope
from valtexa.services import events

while True:
    with session_scope() as session:
        events.drain(session)
    time.sleep(5)
```

E remova o `threading.Thread` do `lifespan` da API.

---

## Escala

| Componente | Como cresce |
|---|---|
| API | horizontal, sem estado |
| Drenador | um worker; a fila é do banco |
| Postgres | vertical primeiro; particionar `telemetry_sample` depois |
| Armazenamento | S3 quando o disco local incomodar |
| Inferência | separado, com GPU; é o gargalo de custo |

O que cresce primeiro é `telemetry_sample`. Plano em
[`TELEMETRY.md`](TELEMETRY.md).

**Sessões colam nada.** Toda a autenticação é por token e assinatura, então o
balanceador não precisa de afinidade.

---

## Observabilidade

`/health` responde `200` enquanto o processo estiver de pé (*liveness*); o corpo
diz se o banco e a inferência estão acessíveis (*readiness*):

```json
{"status": "ok", "environment": "production", "protocol_version": "1.0",
 "database": "ok", "inference": "http://...", "pending_events": 3, "warnings": []}
```

O que vale alertar:

| Sinal | Por quê |
|---|---|
| `pending_events` crescendo | o drenador parou ou um handler quebrou |
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
- [ ] `STORAGE_DIR` em volume persistente
- [ ] `CORS_ORIGINS` com as origens reais
- [ ] TLS terminado antes da aplicação
- [ ] `INFERENCE_URL` apontando para o `VALTEXA-B`
- [ ] `/health` monitorado, com alerta em `pending_events` e `warnings`
- [ ] Alembic no lugar de `create_all()`
- [ ] catálogo de `device_model` conferido
- [ ] **nenhum dado de demonstração** (`seed_demo` só roda no simulador e nos testes)
