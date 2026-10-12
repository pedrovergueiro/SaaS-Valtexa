# Verificação da Parte 1 (feita no início da Parte 2)

> 02/10/2026, sobre `b1bbb6a` (último commit da Parte 1). Regra seguida: não confiar
> no texto do `PROGRESSO.md` — rodar tudo e conferir no código.

## Nota sobre a ordem das sessões

A Parte 2 começou às 20:00 UTC e a branch `claude/plataforma` **ainda não existia no
remoto**. A Parte 1 estava rodando em outra sessão e subiu os commits entre 19:50 e
20:51 UTC. Nesse intervalo esta sessão chegou a refazer a Fase 2 por conta própria.
Esse trabalho **não foi enviado** (ficou só numa branch local), para não disputar a
branch nem sobrescrever a Parte 1. A Parte 2 só começou depois de a branch ficar 30 min
sem commits, e partiu de `b1bbb6a`.

## 1. Suítes (números reais desta execução)

| Suíte | Comando | Antes (`b1bbb6a`) | Depois (esta verificação) |
| --- | --- | --- | --- |
| SaaS | `cd saas && pytest` | **564 passed** (6 min 28 s) | **567 passed** (6 min 03 s): +2 recursos do plano, +1 consentimento chegando à IA |
| SaaS lint | `ruff check .` | limpo | limpo |
| Console | `npm ci && npm run build` | verde | verde (sem mudança no `web/` neste bloco) |
| Console testes | `npx vitest run` | **14 passed** | 14 passed |
| IA | `KERAS_BACKEND=torch pytest` (Python 3.12) | **703 passed** | **720 passed**: +17 do cabeçalho de consentimento |
| IA lint | `ruff check .` | 5 erros, todos em `app/boundary.py`, `app/terrain.py` e `tests/test_terrain_api.py` (intocáveis) | os mesmos 5 |

A IA não foi alterada na Parte 1. Os 703 foram medidos nesta sessão sobre o mesmo
código do `ia/`.

## 2. Migrações Alembic

Num SQLite novo (`/tmp/.../novo.db`):

- `upgrade head` do zero: chega a **0013**, com 45 tabelas;
- `downgrade -1`: volta a **0012**, e as colunas novas do talhão (`plant_spacing_m`,
  `row_count`, `validation_rows`, `notes`) saem;
- desce uma a uma até a 0009 (0012 → 0011 → 0010 → 0009) e sobe de novo até a head
  sem erro.

Além disso, `tests/test_migrations.py` e `tests/test_planos.py::test_migracao_*` passam
dentro da suíte (ida, volta e conversão dos dados). **Não verificado em Postgres**: não
há `TEST_DATABASE_URL` nesta nuvem.

## 3. Conferência no código, item a item

| O `PROGRESSO.md` diz | Conferido em | Resultado |
| --- | --- | --- |
| Equipe sem associação não lê nem escreve em cliente sem sessão de suporte | `api/deps.py::_resolve_principal`: sem associação → 403 `SUPPORT_REQUIRED`. O único caminho alternativo (`current_principal_or_platform`) é usado **só** em `/auth/me` | ✅ |
| Sessão de suporte: motivo, prazo, leitura por padrão, assistido explícito, toda requisição auditada | `_principal_de_suporte`: token com `sup`, o `X-Tenant-Id` precisa ser o da sessão, método não seguro → 403 fora do modo assistido. `support_sessions.registrar_requisicao` grava `support.request`/`support.request_denied` numa transação própria, inclusive as recusas. Entrada, troca de modo e saída geram auditoria; a saída derruba o token | ✅ |
| Rotas de plataforma exigem capacidade | `require_platform(...)` em todas as rotas de `/v1/platform/**` e `/v1/admin/**`. A matriz `PLATFORM_ROLE_CAPABILITIES` está em `security/rbac.py` | ✅ |
| Isolamento entre clientes nas rotas novas | `tests/test_isolamento_openapi.py` classifica **todas** as operações do OpenAPI (rota sem classe reprova) e ataca cada rota de cliente com os ids de outro cliente. `/v1/tenants/current/support-sessions` filtra por `principal.tenant_id` | ✅ |
| Consentimento bloqueia o dataset | `dataset.record_review` usa `consent.permite_treino`; `freeze_version` usa `clientes_com_consentimento`, uma segunda barreira para quem revogou | ✅ no SaaS, **com uma lacuna na IA** (abaixo) |
| Limites do plano aplicados | `plans.exigir` em criar fazenda, talhão + hectares (também ao redesenhar o contorno), convite e provisionamento de robô, usuário e missão (contador mensal). Assinatura suspensa, cancelada ou vencida → 402 | ✅ para limites; **lacuna em recursos** (abaixo) |

## 4. O que estava errado ou faltando, e o que foi corrigido

### 4.1 Recursos do plano gravados e não aplicados

`Plan.features` (`prescricao`, `lavoura_3d`, `validacao_campo`, `relatorios`) era gravado
e mostrado, mas **nenhuma rota o conferia**. Um cliente no plano `essencial` (só
`relatorios`) abria a lavoura 3D normalmente. A Parte 1 já anotava isso como pendência.

**Correção:** `plans.exigir_recurso()` (402, com mensagem em português; sem assinatura,
sem restrição, o mesmo critério dos limites), aplicada às três rotas da cópia 3D:
`/fields/{id}/scene`, `/fields/{id}/row-scans` e `/row-scans/{id}/pointcloud`. Prescrição,
validação de campo e relatórios ainda não têm rota no SaaS; a função fica pronta para elas.
Testes: `tests/test_planos.py::TestRecursos` (2).

### 4.2 Imagem de cliente sem consentimento entrava no treino pela IA

O consentimento barrava o dataset do SaaS, mas a IA (`ia/app/review.py`) tem a própria
fila de revisão. Com `REVIEW_DIR` ligado no servidor de IA, **todo** `/predict` e
`/predict/rover-frame` marcado para revisão era gravado em disco, e essa fila vira dataset
por `training.prepare_dataset`. O SaaS não dizia à IA se o cliente tinha consentido, então
quadro de cliente com NÃO podia entrar no treino por esse caminho (brief, seção 32).

**Correção:**

- IA: novo cabeçalho `X-Training-Consent` em `/predict`, `/predict/batch` e
  `/predict/rover-frame`. Com `0` (ou qualquer valor que não seja um SIM claro), a imagem
  é diagnosticada normalmente e **não** vai para a fila de revisão. Ausente, vale a
  configuração do servidor, que é o uso local com imagem do próprio operador
  (`app/review.py::consent_allows`). Nenhum arquivo de terreno foi tocado.
- SaaS: `HttpModelAnalyzer` manda o cabeçalho em **toda** chamada (`1` só com SIM vigente
  em `consent.permite_treino`), tanto no quadro do robô (`device_protocol._analyses`)
  quanto na ingestão de coleta (`collection_ingest._analisar`). O padrão do parâmetro é
  NÃO.
- Testes: IA `tests/test_training_consent.py` (14), `test_rover_api.py` (+2) e
  `test_novelty.py` (+1); SaaS `test_ia_banana_citros.py::TestConsentimentoChegaNaIa` (o
  robô manda o quadro sem decisão → `0`, depois de registrado SIM → `1`).

### 4.3 O que não é defeito, mas fica anotado

- O `PROGRESSO.md` da Parte 1 diz "409 com a conta em português" para limite atingido e
  402 para assinatura inválida. Confere com o código (`plans.exigir`).
- A auditoria grava uma linha por requisição feita na sessão de suporte, leitura
  inclusive. É o que o brief pede. Se o volume pesar, agregar na F18.
- Riscos ainda abertos e não tratados neste bloco: a IA continua sem autenticação
  SaaS→IA, o login não limita tentativas e a fila de trabalhos não usa `SKIP LOCKED`
  (ver `docs/AUDITORIA.md`).

---

# Verificação da Parte 2 (segunda execução, 03/10/2026)

> 03/10/2026, sobre `efa0d1b`. O agendamento disparou a "Parte 2" de novo, e ela
> **já tinha sido feita** por outra execução entre 01:43 e 02:01 UTC. Esta execução
> não refez nada: conferiu o que a Parte 2 registrou, corrigiu o que achou e fechou
> pendências da própria Parte 2 (console do cliente e cadastro da fazenda).

## 1. Suítes

| Suíte | Comando | Antes (`efa0d1b`) | Depois |
| --- | --- | --- | --- |
| SaaS | `cd saas && pytest` | **596 passed** (6 min 02 s) — bate com o `PROGRESSO.md` | **620 passed** (5 min 04 s): +4 saúde, +20 fazenda |
| SaaS lint | `ruff check .` | limpo | limpo |
| Console | `npm ci && npm run build` | verde | verde |
| Console testes | `npx vitest run` | **42 passed** (4 arquivos) | **58 passed** (6 arquivos) |
| IA | `KERAS_BACKEND=torch pytest` (Python 3.12) | **732 passed** (2 min 03 s) | sem mudança no `ia/` |
| IA lint | `ruff check .` | 5 erros: 2 em `app/boundary.py`, 1 em `app/terrain.py`, 2 em `tests/test_terrain_api.py` (intocáveis) | os mesmos 5 |

Nota de ambiente: o `pyproject.toml` do SaaS já põe `-q` em `addopts`; somado a um
`-q` na linha de comando, o pytest some com a linha de total. Para contar, rodei com
`-o addopts="--strict-markers" -q`.

## 2. Migrações

SQLite novo: `upgrade head` do zero chega à **0014** (46 tabelas), `downgrade -1` volta
à 0013 e sobe de novo sem erro. Depois desta execução a head é a **0015** (fazenda
completa), com teste de ida e volta em `tests/test_fazenda_completa.py`. Postgres
continua não verificado (sem `TEST_DATABASE_URL` aqui).

## 3. Conferência no código

| O `PROGRESSO.md` da Parte 2 diz | Conferido em | Resultado |
| --- | --- | --- |
| Token de suporte não vale nas rotas de plataforma | `deps._recusa_token_de_suporte` em `_equipe_do_token` | ✅ |
| `/platform/me`, `/platform/tenants`, `/platform/accounts` atrás de `require_platform` | `api/routers/platform_console.py`; o teste gerado do OpenAPI classifica cada rota pela dependência | ✅ |
| Bloquear conta derruba as sessões e audita com motivo | `set_account_active` → `sessions.derrubar_todas` + `audit.record(user.blocked)` | ✅ |
| Limite de login por conta e por IP, contado no banco, antes de conferir a senha | `services/login_guard.py` (transação própria para a falha não sumir no rollback) | ✅ |
| Console `/plataforma` com layout e cor próprios, menu por capacidade, `/admin/*` redirecionado | `web/src/platform/PlatformShell.tsx`, `router.tsx` | ✅ |
| "O grupo ValTexa saiu do menu do cliente" | `layout/AppShell.tsx` não tem mais item de plataforma | ✅ no menu, **mas** havia sobra em Configurações (abaixo) |

## 4. O que estava errado e foi corrigido

### 4.1 Informação interna no console do cliente e no `/health` público

Configurações do cliente tinha uma aba **"Plataforma"** que mostrava o `/health`:
ambiente, banco, **endereço interno da IA** e **as pendências de configuração por
extenso** ("SESSION_SECRET ainda é o padrão de desenvolvimento"). É infraestrutura e
informação interna, que a seção 30 do brief manda não mostrar ao cliente. E o
`/health` não tem autenticação: qualquer um na internet lia a mesma coisa (seção 43).

**Correção:**
- `services/saude.py`: o `/health` público mantém os mesmos campos (o monitoramento
  não muda), mas sem detalhe: `database` só `ok`/`erro`, `inference` só
  `ligado`/`desligado` e cada pendência como linha genérica ("Pendência de
  configuração 1 de 6…"). O alerta "`warnings` não vazio" continua valendo.
- `GET /v1/platform/health` (qualquer papel da equipe) devolve o diagnóstico completo.
- A aba saiu do console do cliente; virou **"Saúde do sistema"** no console da
  plataforma (`/plataforma/saude`), visível para todo papel de plataforma.
- Testes: `tests/test_saude.py` (4) e o menu em `platform/console.test.ts`.

### 4.2 Pendências da Parte 2 que ficaram fechadas aqui

- **Console do cliente, Configurações** (as rotas já existiam, faltava a tela):
  "Meu plano" (situação, uso × limite com aviso a 80 % e a 100 %, funcionalidades
  incluídas, estado vazio "Sem plano contratado"), "Dados no treino" (SIM/NÃO
  explícito, só o dono decide, histórico com quem e quando, aviso do efeito de
  trocar para NÃO) e "Acessos da ValTexa" (cada entrada da equipe: quem, quando,
  motivo, chamado, modo, nº de ações, situação). `components/AccountPanels.tsx`,
  `lib/account.ts` (+9 testes).
- **Fazenda completa** (seção 5): produtor, CPF/CNPJ (dígito verificador conferido no
  servidor e na tela, guardado só com dígitos), município, UF, cultura principal,
  recibo do CAR (formato conferido), responsável técnico e observações. Migração
  **0015**; `services/documentos.py`; `PATCH /v1/farms/{id}` audita antes e depois.
  No console: bloco opcional em "Nova fazenda", e cada fazenda mostra "cadastro
  incompleto: …" com o botão **Completar cadastro**. Testes: SaaS
  `tests/test_fazenda_completa.py` (19), console `lib/farmRegistry.test.ts` (7).
- **Navegador**: `web/e2e/conta-e-fazenda.mjs` (8 passos, contra a API real servindo o
  build, banco novo com o seed): todos ok.

---

# Verificação da Parte 3 (feita no início da Parte 4)

> 04/10/2026, ~01h15 UTC, sobre `d484d00` (último commit da Parte 3, de 03/10 19:52
> UTC — mais de 5 h antes; a Parte 3 já tinha terminado, sem disputa pela branch).

## 1. Suítes (números reais desta execução)

| Suíte | Comando | Resultado |
| --- | --- | --- |
| SaaS | `pytest -o addopts="--strict-markers" -q` (Python 3.11) | **685 passed** (7 min 44 s), igual ao que o PROGRESSO diz. 1 aviso: `StarletteDeprecationWarning` do `fastapi.testclient` (biblioteca, não nosso) |
| SaaS lint | `ruff check .` | limpo |
| Console | `npm ci && npm run build` | verde (1,65 s) |
| Console testes | `npx vitest run` | **67 passed** (7 arquivos) |
| IA | `KERAS_BACKEND=torch pytest` (Python 3.12) | **732 passed** (2 min 27 s) |
| IA lint | `ruff check .` | os mesmos 5 erros dos arquivos de terreno (intocáveis) |

Nota de ambiente: o índice `download.pytorch.org` está bloqueado nesta nuvem; o torch
veio do PyPI.

## 2. Migrações

Num SQLite novo: `alembic upgrade head` do zero até **0017**, `downgrade -1` (0017 →
0016) e `upgrade head` de novo — sem erro. Postgres continua não verificado.

## 3. Conferência no código

| O que o PROGRESSO diz | Onde está | Confere? |
| --- | --- | --- |
| CPF/CNPJ mascarado na API para quem não tem `farm:manage` | `api/routers/farms.py` (`_documento_completo`, `_farm_out`), `services/documentos.mascarar_cpf_cnpj`; trilha guarda mascarado (`_sem_documento`); leitura completa pela equipe auditada (`farm.owner_document_viewed`) | sim |
| Estados da frota derivados do protocolo | `services/fleet_state.py`: função pura, precedência BLOQUEADO → MANUTENÇÃO → OFFLINE → ERRO → EM MISSÃO → SINCRONIZANDO → DISPONÍVEL; ninguém grava o estado | sim |
| Transições do registry com aprovação por outra pessoa | `services/model_registry.transicionar`: aprovar exige `ia_dados`/`superadmin` e recusa `registered_by == actor` (403); aprovar exige métrica; publicar exige hash e descontinua a anterior | sim |
| Liberação por cliente | `chaves_liberadas` + `liberado` + `disponiveis` (só PRODUÇÃO e liberada); talhão só escolhe entre as disponíveis | sim |
| Rover sem modelo fora do registry | `GET /v1/device/models` só monta resposta a partir de `designados()` → `resolve_model` (registry, PRODUÇÃO, liberada); sem hash → `artifact_sha256` nulo; frota marca `fora_do_registry` | sim, **do lado do servidor**. O lado do robô (conferir o hash antes de carregar e recusar o resto) não existia: é o Model Manager do pacote `rover/`, feito nesta Parte 4 |

## 4. O que estava errado

Nada a corrigir nos itens da Parte 3. O que faltava para a Parte 4 (o robô que consome
`/v1/device/models`, e rotas de upload) é escopo da própria Parte 4.

---

# Verificação da Parte 4 (feita no início da Parte 5)

> 04/10/2026, sobre `5e2373a` (último commit da Parte 4, 5 h antes: a Parte 4 já tinha
> terminado). Regra: rodar tudo e conferir no código, não no texto.

## 1. Suítes (números reais desta execução)

| Suíte | Comando | Resultado |
| --- | --- | --- |
| SaaS | `cd saas && pytest -o addopts="--strict-markers" -q` (3.11) | **700 passed** (8 min 02 s) — o mesmo número da Parte 4 |
| SaaS lint | `ruff check .` | limpo |
| Rover | `cd rover && pytest` (3.11) | **75 passed** (6,4 s) → **76** com o teste de regressão abaixo |
| Rover lint | `ruff check .` | limpo |
| IA | `KERAS_BACKEND=torch pytest -q` (3.12) | **732 passed** (4 min 05 s) |

Nota de ambiente: `download.pytorch.org` continua bloqueado; o torch veio do PyPI.

## 2. Migrações

SQLite novo: `upgrade head` do zero até **0018**, `downgrade -1` (→ 0017) e `upgrade head`
de novo — sem erro. (No fim da Parte 5: do zero até **0021**, `downgrade -1` → 0020,
`downgrade 0018` e `upgrade head` de novo — sem erro.) Postgres continua não verificado.

## 3. Conferência no código

| O que o PROGRESSO diz | Onde está | Confere? |
| --- | --- | --- |
| `rover/` não importa `saas/` nem `ia/` | `grep` em `rover/valtexa_rover`: nenhum `import valtexa`/`app`; só `valtexa_rover.*`; `test_vendor.py` compara os SHA-256 da cópia do `ia/` | sim |
| missão continua offline e sobrevive a reinício | `runtime/core.py` (laço não depende de rede; `boot` → `MISSION_RESUMED`), `runtime/store.py` (WAL + `synchronous=FULL`, arquivo atômico antes do *commit*, `recover`) | sim |
| buffer circular | `runtime/buffer.py` (N antes/M depois, `max_duration_s`, por câmera, eventos sobrepostos) | sim |
| retenção reduz volume de fato | `runtime/retention.py` + `test_retention.py` (bytes reais: 6,04 GB → 565 MB) | sim |
| upload retoma de onde caiu | `runtime/sync.py` (`received_chunks` + `chunks_done` gravado a cada chunk); `test_queda_em_70_por_cento_retoma_de_70` | sim — **com um defeito**, abaixo |
| reenvio não duplica | servidor: `edge_sync.ingest_records` (ID + hash) e `open_upload` (dedup por hash do cliente) | sim |
| isolamento por cliente nas rotas do robô | `edge_sync.find_upload`/`open_upload` filtram por `device_id` do robô autenticado; `test_isolamento_openapi.py` ataca upload real da vítima | sim |

## 4. O que estava errado e foi corrigido

**Backoff que não sobrevivia a reinício** (`rover/valtexa_rover/runtime/store.py`). O
`next_attempt_at` da fila é gravado no relógio **monotônico**, que recomeça do zero a cada
boot. Um item em *backoff* gravado com 90.000 s de *uptime* ficava preso ~25 h depois de
um reinício (a fila parecia travada). Correção: o `recover()` do boot zera a espera dos
pendentes (o reinício é um bom momento para tentar de novo). Teste novo
`test_backoff_nao_prende_a_fila_depois_do_reinicio` — **falha sem a correção, passa com
ela** (conferido revertendo o arquivo).

Nada mais a corrigir nos itens da Parte 4. Os defeitos que o ponta a ponta e o estresse
acharam depois estão em `docs/PROGRESSO.md` (Parte 5, "Correções").

---

# Verificação da Parte 6 (feita no início da Parte 7)

> 05/10/2026, sobre `81c5f6d` (último commit da Parte 6, às 20:03 UTC de 04/10 — mais de
> 4 h antes: a Parte 6 já tinha terminado). Regra: rodar tudo e conferir no código.

## 1. Suítes (números reais desta execução)

| Suíte | Comando | Antes (`81c5f6d`) | Depois das correções |
| --- | --- | --- | --- |
| SaaS | `cd saas && pytest -o addopts="--strict-markers" -q` (3.11, SQLite) | **751 passed** (9 min 04 s) | 751 + 1 asserção nova no `test_chamados.py` (mesmo número de testes) |
| SaaS lint | `ruff check .` | limpo | limpo |
| Rover | `cd rover && pytest` (3.11) | **95 passed** (21,7 s) | 95 |
| Rover lint | `ruff check .` | limpo | limpo |
| Console | `npm ci && npm run build` / `npx vitest run` | verde / **84 passed** | verde / 84 |
| IA | `KERAS_BACKEND=torch pytest -q` (3.12) | **738 passed, 1 failed, 1 skipped** (2 min 36 s) | **740 passed** com o `dnaty` instalado (o *skip* era a falta dele) |

A falha da IA não era da Parte 6 (que não tocou no `ia/`): ver 4.2.

## 2. Migrações

- **SQLite** novo: `upgrade head` do zero até **0023**, `downgrade -1` (→ 0022) e `upgrade
  head` de novo, sem erro.
- **Postgres 16** local (`/usr/lib/postgresql/16`, porta 5433): o mesmo roteiro, sem erro.

## 3. Conferência no código

| O que o PROGRESSO diz | Onde está | Confere? |
| --- | --- | --- |
| Notificações desacopladas das telas | `services/notifications.py`: nenhuma rota cria aviso; as regras são *handlers* do *outbox* (`events.subscribe`), o worker entrega o evento e depois `entregar_pendentes` | sim |
| Idempotentes | `notificar`: checagem por `(user_id, dedup_key)` + restrição única `uq_notification_user_dedup` + *savepoint* (dois workers com o mesmo evento: o segundo segue) | sim |
| E-mail sem SMTP não finge | `CanalEmail.enviar` devolve `nao_enviado` com o motivo quando `SMTP_HOST` está vazio; WhatsApp/push/SMS são `CanalNaoImplementado` e a preferência recusa escolhê-los | sim |
| Isolamento das notificações | `_candidatos` só pega membros do cliente do aviso (ou a equipe, para avisos da plataforma); `da_pessoa`/`_da_caixa` filtram por destinatário, público e cliente | sim |
| Chamado: isolamento e vínculos | `support_tickets._vinculos` (robô e missão do próprio cliente, senão 404); rotas do cliente usam `get_scoped` | sim |
| Comentário interno não vaza | conversa e histórico filtram `internal` para o cliente; nota interna não publica evento (nem aviso) | **não totalmente** — vazava pela trilha de auditoria (4.1) |
| Auditoria | `_audita` em abrir, status, prioridade, responsável, incidente e comentário; incidente em `_audita_incidente` | sim |

## 4. O que estava errado e foi corrigido

### 4.1 A nota interna aparecia na auditoria do cliente

`comentar(..., internal=True)` gravava `ticket.commented` **com o `tenant_id` do cliente**,
`payload.internal = true` e o e-mail de quem escreveu. O gestor e o auditor do cliente leem
essa trilha em `GET /v1/audit`: viam que existia uma nota interna, quando e de quem — o
que a conversa e o histórico do chamado escondem. Correção (`services/support_tickets.py`):
a entrada da nota interna vai para a trilha **da plataforma** (`tenant_id` nulo, com o
cliente no `payload`). Asserção nova em `test_chamado_completo_do_cliente_a_equipe` —
**falha sem a correção, passa com ela** (conferido revertendo o arquivo).

Ressalva que fica: a nota interna ainda atualiza `last_activity_at` do chamado (o cliente
vê "última atividade" mudar). É o que a fila da equipe usa; deixado como está.

### 4.2 dNATY: modelo idêntico passava como "otimizado" (teste instável)

`test_igual_ao_original_e_recusado_por_falta_de_ganho` falhou em 2 de 3 rodadas. Medindo:
a memória da **primeira** sessão do ONNX Runtime inclui a inicialização da biblioteca
(8,8 MB contra 0 na segunda) e a latência de um MLP minúsculo oscila ±25 % — os dois
viravam "ganho" e o critério aceitava o mesmo modelo como otimizado. É defeito do
critério, não só do teste: um modelo real pequeno sofreria o mesmo. Correção, no
`ia/training/dnaty_pipeline.py` **e** na cópia que o registry usa para recalcular
(`saas/valtexa/services/dnaty.py`): `ruido_latencia_ms` (0,5) e `ruido_memoria_mb` (16) —
diferença menor que isso não conta como ganho nem como perda; configuráveis (zero volta
ao comportamento estrito). Testes novos nos dois lados. Depois: 5 de 5 rodadas verdes.

# Verificação da Parte 7 (feita no início da Parte 8)

> 05/10/2026, sobre `b2ca4f5` (último commit da Parte 7, às 01:19 UTC — 4 h antes do
> início desta parte, às 05:18 UTC: a Parte 7 já tinha terminado). Regra: rodar tudo e
> conferir no código.

## 1. Suítes (números reais desta execução)

| Suíte | Comando | Antes (`b2ca4f5`) | Depois das correções |
| --- | --- | --- | --- |
| SaaS | `cd saas && pytest -q` (3.11, SQLite) | **781 passed**, 0 falhas | 781 + **3 testes novos** em `test_observabilidade.py` (32 no arquivo; com `test_notificacoes.py`: 53 passed) |
| SaaS lint | `ruff check valtexa tests` | limpo | limpo |
| Rover | `cd rover && pytest` (3.11) | **102 passed** | 102 (sem mudança no `rover/`) |
| Console | `npm run build` / `npx vitest run` | verde / **92 passed** (12 arquivos) | idem (sem mudança no `web/` neste bloco) |
| IA | `KERAS_BACKEND=torch pytest` (3.12, com `dnaty`) | **746 passed**, 0 falhas, 0 *skip* | 746 (sem mudança no `ia/`) |

## 2. Migrações

- **SQLite** novo: do zero até **0024** (24 migrações), `downgrade -1` → 0023 (conferido
  no banco: `api_request_stat`, `alert_rule`, `alert`, `device.health` e
  `device.health_reported_at` somem) e `upgrade head` de novo, sem erro.
- **Postgres 16** local: o mesmo roteiro, conferido em `information_schema` (0 tabelas e
  0 colunas da 0024 depois do *downgrade*), sem erro.

## 3. Conferência no código

| O que o PROGRESSO diz | Onde está | Confere? |
| --- | --- | --- |
| `/metrics` protegido | `api/routers/observabilidade.py`: `METRICS_TOKEN` por `hmac.compare_digest`; token vazio não aceita nada (cai no login da equipe com `platform:observability:read`) | sim |
| Sem dado de outro cliente nas métricas | rótulos só com id do cliente e serial do robô; rota pelo **molde** (`observability/http.py`), nunca com id no caminho | sim |
| Rotas do cliente isoladas | frota, alertas e regras filtram `principal.tenant_id`; reconhecer alerta de outro cliente → 404; regra da plataforma → 403 | sim |
| Estados disparado → reconhecido → resolvido | `_reconcilia` e `reconhecer` em `services/alertas.py` | **não totalmente** (4.1) |
| Sem disparo duplicado | restrição única em `alert.open_key` + `begin_nested`/`IntegrityError`; só o disparo novo publica evento; *dedup* por alerta no aviso | sim |
| Regra própria do cliente vale só para ele | `efetiva_para` | sim, mas **calava a equipe** (4.2) e **ignorava a equipe desligar a padrão** (4.3) |
| Tela | `Observability.tsx` (cliente e plataforma) consome as rotas acima | sim |

## 4. O que estava errado e foi corrigido

A conferência do código foi feita com um agente de leitura, que escreveu um teste de
reprodução para cada achado; os três abaixo viraram testes em `test_observabilidade.py`
— **os 3 falham sem a correção e passam com ela** (conferido com `git stash` só dos dois
arquivos corrigidos).

### 4.1 Reconhecer enquanto o worker resolvia deixava um alerta aberto para sempre

A rota lia o alerta "disparado"; o worker o resolvia (`open_key` nulo, `resolved_at`);
a rota gravava `state="reconhecido"` por cima. O worker só olha alertas com `open_key`,
então ele nunca mais fechava — e contava como aberto no painel, no `/metrics` e na frota.
Correção: `reconhecer` faz um `UPDATE` condicional (`state = 'disparado' AND open_key IS
NOT NULL`) e responde **409** se nada mudou. Teste:
`test_reconhecer_enquanto_o_worker_resolve_nao_deixa_alerta_eterno`.

### 4.2 O cliente desligar `rover_offline` calava o aviso da equipe

O aviso de robô offline é só da equipe (o cliente já recebe o `rover_offline` da Parte 6),
mas a regra efetiva do cliente decidia se o alerta existia. Correção: `rover_offline` não
tem versão por cliente (`SO_DA_EQUIPE`): o `PUT` do cliente dá 403, ela some da lista do
cliente e uma cópia antiga é ignorada. Teste:
`test_cliente_nao_cala_o_aviso_de_robo_offline_da_equipe`.

### 4.3 A equipe desligar a regra padrão não valia para quem tinha cópia própria

A cópia do cliente copiava `enabled=True` da padrão e passava a valer sozinha. Correção:
padrão desligada pela equipe vale para todos. Teste:
`test_equipe_desligar_a_padrao_vale_tambem_para_a_copia_do_cliente`.

### 4.4 Menores

- `ia_erros` e `drift` tratavam **limite 0** como 100 % e 1 (`or`), embora a validação
  aceite 0: agora `None` cai no padrão e 0 vale 0.
- A lista de robôs era consultada a cada regra (`setdefault` avalia o argumento): agora
  uma vez por avaliação.

### 4.5 O que fica (decisão, não defeito)

- O cliente **desligar** outra regra de robô (disco, temperatura...) também tira o alerta
  da equipe sobre aquele robô: o alerta é um só por assunto. Documentado em
  `docs/OBSERVABILIDADE.md`; separar "alerta do cliente" de "alerta da equipe" fica para
  quando houver pedido.
- Mudança posterior de **limite/severidade/janela** da padrão não alcança quem já tem cópia
  (a cópia é a versão própria dele); só o desligar alcança.
- Sem histerese: disco oscilando 95/89/95 abre três alertas e manda três avisos (já estava
  na lista do PROGRESSO).

# Verificação da Parte 8 (feita no início da Parte 9)

> 05/10/2026, ~10h UTC, sobre `38fde9c` (último commit da Parte 8, 4 h antes — a Parte 8
> não estava mais rodando). Ambientes novos (`uv`), Postgres 16.14 local.

## 1. Suítes

| Suíte | Resultado sobre `38fde9c` |
| --- | --- |
| SaaS — `pytest` no SQLite | **790 passed** (11 min 43 s) |
| SaaS — `pytest` **completa no Postgres 16** (`TEST_DATABASE_URL`) | **790 passed** (17 min 19 s) — primeira vez que a suíte inteira roda no Postgres (Partes 7 e 8 rodaram só os módulos tocados) |
| SaaS — `ruff check .` | limpo |
| Rover — `pytest` | 102 passed |
| IA — `KERAS_BACKEND=torch pytest` (3.12, com `dnaty`) | 746 passed |
| Console — `npm run build` / `npx vitest run` | verde / 112 passed |
| Migrações (SQLite e Postgres 16) | do zero até 0024, `downgrade -1`, `upgrade head`: ok. **Mas `alembic check` acusa drift** (§ 3.3) |
| Navegador — `web/e2e/telas-e-mapa.mjs` num banco novo | **falhou no passo 3** na primeira execução (§ 3.2); 13 de 13 depois da correção do roteiro |

## 2. Conferência no código

| A Parte 8 diz | Conferido em | Resultado |
| --- | --- | --- |
| As telas consomem o backend real | `MissionReportPage`, `MissionCompare`, `FieldHistory`, `MissionLayersMap`, `Dashboard` usam só `@/api/queries` (React Query sobre o cliente gerado do OpenAPI); nenhum dado de exemplo ou *mock* em `src/pages`/`src/components` | ✅ |
| Escopo do cliente nas 3 rotas novas | `GET /missions/{id}/map`: `get_scoped(Mission)` e consultas por `mission.tenant_id`; `GET /fields/{id}/history`: `get_scoped(Field)` e tudo filtrado por `principal.tenant_id`; `GET /edge/records/{id}/files/{upload_id}`: `get_scoped(EdgeRecord)`, upload por `scoped(...)` e `get_scoped(Asset)`. As três estão no `test_isolamento_openapi.py` | ✅ |
| CSV do relatório | `web/src/lib/reportExport.ts`: `;`, BOM, aspas — **sem neutralizar fórmula** (§ 3.1) | ❌ corrigido |
| Painel com dados reais | `services/visao_operacional.painel`: tudo por `tenant_id`, agregação no banco | ✅ |

## 3. Defeitos achados e corrigidos

### 3.1 Injeção de fórmula no CSV do relatório

`csvCell` só tratava `;`, aspas e quebra de linha. O nome da fazenda e do talhão é
digitado pelo cliente; `=HYPERLINK(...)`, `+...`, `-...`, `@...` viravam fórmula ao abrir
no Excel (CSV injection). Correção: texto que começa com `= + - @ \t \r` ganha `'` na
frente; número (inclusive negativo com vírgula, como as coordenadas) não é tocado. Teste:
`reportExport.test.ts` ("neutraliza fórmula...") — falha sem a correção.

### 3.2 Corrida no roteiro de navegador

O subtítulo "0 registro(s) sincronizado(s)" aparece **enquanto a lista carrega**; o
roteiro esperava esse texto e contava as linhas antes da tabela existir ("filtro por
categoria: 2 de 1"). Era o roteiro, não a tela: agora espera a contagem real
(`[1-9]\d* registro(s)`). 13 de 13 passos, sem erro de JavaScript, duas vezes (no começo
e no fim da Parte 9, a segunda com os cabeçalhos de segurança novos).

### 3.3 Índices dos modelos que as migrações nunca criaram

`alembic check` contra um banco migrado do zero: `ix_alert_created_at`,
`ix_alert_rule_created_at` (Parte 7) e `ix_user_session_created_at` (Parte 2) existem nos
modelos (`Timestamped.created_at, index=True`) e **não** nas migrações. Os testes usam
`create_all` (têm o índice); produção usa Alembic (não tinha). `test_migrations.py` só
comparava colunas. Correção: migração **0025** (os três + `ix_edge_record_tenant_kind_time`
e `ix_mission_field_kind`, pedidos pela lista da Parte 8) e teste novo
`test_migracoes_criam_os_indices_dos_modelos` (compara índices). SQLite e Postgres: do
zero até 0025, `downgrade -1`, `upgrade head`; `alembic check` sem índice faltando (resta
só o ruído conhecido de `Enum` não nativo × `VARCHAR`, sem efeito).

---

# Verificação da Parte 10 (feita no início da Parte 11, rodada 3)

> 08/10/2026, ~00h45 UTC, branch `claude/base-fazenda` sobre `b733032` (a base da rodada
> 3, de 07/10 16h35 BRT). Regra: rodar tudo e conferir no código, não no texto.

## 1. A Parte 10 não está na branch

`git fetch` + `git log`: o último commit de `claude/base-fazenda` é a base `b733032`
(nenhuma outra branch tem trabalho posterior da rodada 3). Não existem
`docs/VALIDACAO_ROVER.md`, seção "Rodada 3" no `PROGRESSO.md`, comando `ensaio` no
Runtime (`runtime/comandos.py` só tem `diagnostico`, `foto`, `modo`, `parar`, `config`,
`recarregar_modelos`, `reiniciar`), catálogo de ensaios, portões por fase, nem aba
Validação no console. O último commit tinha 5 h quando esta parte começou (regra dos 30
min: a P10 não estava rodando). Os quatro itens a conferir ("ensaio assinado e recusa
repetição", "portão não aprova com teste faltando", "resultado calculado no servidor",
"tela no backend real e isolado") **não tinham o que conferir** — foram construídos nesta
parte e cada um tem teste próprio (seção 3).

## 2. Suítes de base (antes de qualquer mudança)

| Suíte | Comando | Resultado |
|---|---|---|
| SaaS | `cd saas && pytest` | verde (todos os testes passaram, ~15 min) |
| SaaS lint | `ruff check .` | limpo |
| Console | `npx vitest run` / `npm run build` | **118 passed** (18 arquivos) / build ok |
| Rover | `cd rover && pytest` | **154 passed, 3 skipped, 1 FALHOU**: `test_lente.py::test_sem_distorcao_nao_muda_a_foto` |
| Rover lint | `ruff check .` | **3 erros** (RUF043 em `test_edge_cabeca.py`, 2× RUF046 em `test_lente.py`) |
| IA | — | ver seção 4 |

### Defeito pré-existente corrigido: remapeamento NumPy da lente zerava a borda

`hal/lente.py::_remap_bilinear` (o caminho sem OpenCV, que é o desta máquina) marcava
como "fora da foto" todo pixel com `x0 = largura − 1` ou `y0 = altura − 1`: com uma lente
sem distorção (mapa identidade) a **última coluna e a última linha saíam pretas** (erro
254). Na Jetson, com `cv2`, o caminho é outro — mas sem OpenCV (bancada, CI) toda foto
corrigida perdia a borda. Correção: "dentro" passa a ser `0 ≤ x ≤ largura − 1`, o par
vizinho é recuado para dentro e o peso vai todo ao pixel da borda. O teste existente
volta a passar; ruff dos testes corrigido (`round()` já devolve `int`; regex com `\.`).

## 3. O que a P10 deveria ter entregado, conferido no que foi construído aqui

| Exigência | Onde | Teste que prova |
|---|---|---|
| `ensaio` assinado e recusa repetição/forjado | `rover/valtexa_rover/runtime/comandos.py` (mesmo `verify_command` com sequência própria) | `rover/tests/test_ensaio_comando.py::test_ensaio_repetido_ou_forjado_e_recusado` |
| portão não aprova com teste faltando | `saas/valtexa/services/ensaios.py::portoes` | `saas/tests/test_ensaios_plataforma.py::test_portao_da_fase1_so_abre_com_tudo_aprovado` (faltando → fechado; 3 tentativas não valem; só abre com os dois) |
| resultado calculado no servidor | `ensaios.registra_do_robo` recalcula com as amostras e os parâmetros assinados | `test_veredito_e_do_servidor_nao_do_robo` (robô diz "aprovado" com 40 mm de erro e troca a distância → reprovado, `divergente`), `test_robo_que_omite_tentativas_nao_aprova_a_parada`, `test_laudo_sem_marca_de_simulacao_conta_como_simulado` |
| tela no backend real e isolado | `saas/web/src/platform/pages/Validation.tsx` → rotas `/v1/platform/...` com `require_platform` | `test_isolamento_openapi.py` classifica as 9 rotas novas e ataca as de plataforma com os 7 papéis de cliente (403) e as do robô com outro robô (404); `test_outro_robo_nao_mexe_no_ensaio` |

## 4. IA

Não foi alterada nesta parte (nenhum arquivo em `ia/`). O índice CPU do PyTorch
(`download.pytorch.org`) é recusado pela política de rede deste ambiente; instalada pelo
PyPI (torch 2.11 com CUDA, roda em CPU), Python 3.12: **757 passed, 1 skipped**; `ruff`:
os 5 erros conhecidos (`app/boundary.py`, `app/terrain.py`, `tests/test_terrain_api.py`).

## 5. Suítes no fim da Parte 11

| Suíte | Resultado |
|---|---|
| SaaS `pytest` | **932 passed, 3 skipped** (14 min) · `ruff` limpo |
| Console | `vitest` **122 passed** (19 arquivos) · `build` ok · roteiro `e2e/validacao.mjs` 7/7 |
| Rover `pytest` | **184 passed, 3 skipped** · `ruff` limpo |
| IA `pytest` | 757 passed, 1 skipped (não alterada) |
| `python -m simulator --fase0` | 12/12 passos, contra o uvicorn por HTTP |
| Migração 0029 | SQLite do zero → head, `downgrade -1`, `upgrade head`; `alembic check` só com o ruído conhecido de `Enum` |

---

# Verificação da Parte 12 (feita no início da Parte 13, rodada 3)

> 09/10/2026, ~20h40 UTC, branch `claude/base-fazenda` sobre `9d8e5fd` (último commit da
> P12, 3 h 47 min antes: a P12 não estava rodando). Postura: **revisor hostil** — cada
> item da lista do Pedro virou um ataque com teste; o que passou ficou registrado, o que
> quebrou foi corrigido com teste. Rádio **emulado**, relógio virtual.

## 1. Suítes de base (antes de qualquer mudança)

| Suíte | Resultado |
|---|---|
| Rover `pytest` | **214 passed, 3 skipped** · `ruff` limpo |
| Base `pytest` | **13 passed** · `ruff` limpo (numa das 7 rodadas desta parte, `test_sem_internet_a_base_continua_aceitando_e_guarda_o_idempotente` falhou uma vez — UDP real com 10 % de perda e prazos de parede; nas outras 6, e com o código da P12 puro 3×, passou: registrado como sensível a tempo, não como defeito do protocolo) |
| SaaS `pytest` | verde (sem falha), contagem como na P12 |

## 2. Ataques e falhas procurados

| Item | Resultado | Teste (`rover/tests/test_enlace_verificacao.py`, salvo indicação) |
|---|---|---|
| Replay entre sessões | **resistiu**: na mesma sessão a janela anti-replay recusa; depois da troca de chave a sessão de duas trocas atrás sai da memória; com a base reiniciada nada decifra | `test_replay_entre_sessoes_e_depois_de_reiniciar_nao_entrega_nada` |
| Nonce repetido depois de reiniciar | **resistiu**: sessão nunca é persistida; cada reinício faz aperto de mão com efêmeras novas (chaves novas); nenhum par (sessão, contador) repetido em 3 reinícios dos dois lados | `test_nonce_nunca_se_repete_mesmo_reiniciando_os_dois_lados` |
| Fila sem limite | **2 furos corrigidos**: (a) `_ultimo_aviso` (limite de taxa do `REINICIAR`, por origem) crescia com pacote de lixo de muitas origens — 10.000 origens = 10.000 entradas para sempre → teto de 4096 e poda; (b) a tabela `entrada` guardava para sempre a resposta que ninguém consumiu (quem pediu desistiu) → limpeza das vencidas a cada 10 min. `saida` já tinha teto; `vistos` é podado (7 dias) | `test_pacote_forjado_de_muitas_origens_nao_enche_a_memoria`, `test_entrada_vencida_que_ninguem_consumiu_e_limpa` |
| Disco cheio de verdade | **furo corrigido**: só havia o teste do "disco quase cheio" pela conta de espaço livre; com o SQLite respondendo `SQLITE_FULL` o `sqlite3.OperationalError` subia do `passo()` (no Executor, contado e engolido; na bancada, derrubava) e **o PARAR da base não chegava ao Rover com o disco do Rover cheio**. Agora: no receptor, P0/P1 são entregues da memória e P2–P4 não são confirmados (o emissor guarda e reenvia quando houver espaço, uma vez só); no emissor, P0/P1 seguem da memória e P2–P4 levantam `DiscoCheioError` (subclasse de `FilaCheiaError`, que o chamador já trata); a sequência do slot de teleop não trava | `test_disco_cheio_no_receptor_parar_passa_e_o_resto_espera_sem_perder`, `test_disco_cheio_no_emissor_p0_p1_vao_da_memoria_e_o_resto_e_recusado` (disco cheio simulado com `PRAGMA max_page_count`) |
| **Relógio do Rover errado** (validade de comando) | **defeito grave corrigido**: a base comparava o `prazo` do pedido — **hora de parede do Rover** — com a hora dela. Rover 10 min atrasado (sem GNSS ainda, RTC errado) = **todo pedido "vencido" na base: comunicação morta**; adiantado = pedido morto repassado. Agora a validade viaja só como tempo restante (já era assim nos pedaços) e cada nó usa o próprio relógio (`Chegada.expira`, `rpc.resta_s`) | `test_relogio_do_rover_errado_nao_derruba_nem_estica_a_validade[-600/+600]` |
| Passo do relógio do sistema | **corrigido**: o chrony acertando a hora 1 h para trás esticava em 1 h a validade do que estava na fila. O nó usa uma "parede estável" (hora do início + monotônico) para toda validade | `test_passo_do_relogio_do_sistema_nao_estica_a_validade_na_fila` |
| Teleop vencido aplicado | **furo fechado**: o Runtime conferia `expires_at` (hora da plataforma) contra o relógio do robô; com o robô atrasado X s, um ponto retido por uma base com defeito/hostil valia X s a mais. Novo `PisoDaPlataforma`: cada envelope de assinatura válida prova que a hora da plataforma é ≥ `issued_at` + o monotônico desde então; a validade é conferida contra `max(relógio, piso)`. Forjado não empurra o piso. Robô **adiantado** só recusa o que valia (lado seguro) — o ensaio `relogio` confere contra o GNSS | `test_teleop_atrasado_pela_base_e_recusado_mesmo_com_o_relogio_do_rover_atrasado`, `test_piso_ignora_envelope_sem_assinatura_valida` |
| Deduplicação que esquece depois de reiniciar | **resistiu**: `vistos` é SQLite gravado na mesma transação que a `entrada`; teleop: a sequência do Runtime (`last_teleop_sequence`) é persistente e o ponto vence em 1 s. Ressalva registrada: `vistos` guarda 7 dias — mensagem entregue cujo "entregue" se perdeu e que fica mais de 7 dias na fila do emissor seria entregue de novo (a plataforma deduplica por id de registro) | `test_enlace.py::test_fila_sobrevive_a_reabrir_e_deduplica`, `test_enlace_caos.py::test_matar_e_reiniciar_os_processos_no_meio_da_transferencia` |
| Slot velho | **corrigido**: o ponto de teleop mais velho que o último aplicado era descartado **sem confirmar**, e o emissor o reenviava até vencer (banda gasta no enlace lento) | `test_slot_velho_e_confirmado_para_o_emissor_parar_de_reenviar` |
| P4 matando P1 de fome | **resistiu** também só com o sub-GHz vivo (250 kbit/s, 10 % de perda, P4 sem parar): P1 a cada 250 ms, 60 s, **p50 80 ms, p95 270 ms, p99 430 ms, máx. 540 ms, 0 perdido** | `test_p4_nao_mata_p1_de_fome_so_com_o_enlace_lento` |
| **Base forjando ou alterando comando** | comando/missão/teleop: **resistiu** (envelope assinado pela plataforma; teste da P12). Mas a **resposta de aceite não era assinada**: uma base com defeito ou adulterada podia responder "200 aceito" a `/edge/records`, `/sync`, pedaços de upload — e o Rover **apagaria da fila o que nunca chegou**. Corrigido com **recibo assinado** pela plataforma (`nonce do pedido | status | sha256 do corpo`, prefixo próprio), pedido pelo Rover com `X-Valtexa-Recibo`; sem recibo válido, 2xx que muda estado = "sem rede" | `base/tests/test_base.py::test_base_adulterada_nao_faz_o_rover_apagar_o_que_nao_chegou` (troca o corpo; reaproveita o recibo de outro pedido; responde sozinha), `saas/tests/test_recibo_dispositivo.py`, `saas/tests/test_base_fazenda.py` (ponta a ponta: todo aceite com recibo conferido, nenhum recusado) |

Também corrigido na bancada: os perfis `SUBGHZ`/`ALTA` eram objetos globais e
`replace()` copia a lista `quedas` por referência — um teste que acrescentava queda
contaminava os seguintes (achado porque um teste novo "perdeu" 234 comandos). A bancada
agora copia os modelos.

## 3. Compatibilidade

* Validade: o campo `prazo` continua no cabeçalho do pedido (informativo); base nova com
  Rover antigo funciona (a validade do enlace já viajava como tempo restante).
* Recibo: **Rover desta parte exige plataforma desta parte** quando fala pela base (o 2xx
  sem recibo vira "sem rede" — o dado fica, nada se perde, mas não sincroniza).
  `hardware.json` `rede.exige_recibo: false` para falar com uma plataforma anterior.
  Rede HTTPS direta (sem base) não muda.

## 4. Suítes no fim da Parte 13

| Suíte | Resultado |
|---|---|
| Rover `pytest` | **251 passed, 3 skipped** · `ruff` limpo |
| Base `pytest` | **32 passed** · `ruff` limpo |
| SaaS `pytest` | **945 passed, 3 skipped** (13 min 44 s) · `ruff` limpo. Na primeira rodada completa, **2 falhas** em `test_simulador_fase0.py`: o piso da hora da plataforma (desta parte) usava o monotônico do Runtime, que na bancada simulada anda depressa — o piso ia para o futuro e o comando do ensaio seguinte "vencia". Corrigido (o piso usa o tempo que passou de verdade) e a suíte inteira rodada de novo |
| Console | `vitest` **123 passed** · `build` ok |
| IA (não alterada) | **757 passed, 1 skipped** (Python 3.12) · `ruff`: os 5 erros conhecidos |
| Ensaio de 24 h SIMULADO | zero perda de P0 a P3 (`docs/ensaios/enlace-24h-simulado.json`) |
