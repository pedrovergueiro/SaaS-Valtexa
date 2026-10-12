# Autenticação e chaves

Dois tipos de chamador, que **não se misturam em nenhuma rota**:

| | Pessoas | Robôs |
|---|---|---|
| Rotas | `/v1/**` | `/v1/device/**` |
| Credencial | token de sessão (bearer) | assinatura Ed25519 por requisição |
| Escopo | tenant + papel | dispositivo |

Um token de usuário numa rota de dispositivo devolve `403`, e vice-versa. É o
que impede que uma conta comprometida no navegador comece a publicar telemetria
falsa em nome de um robô.

---

## Pessoas

### Senha

`hashlib.scrypt` da biblioteca padrão, N=2^15, r=8, p=1 (recomendação
interativa do RFC 7914). Sem bcrypt nem argon2: scrypt é memory-hard, está no
CPython desde a 3.6 e não traz dependência binária para instalar em campo.

Formato: `scrypt$N$r$p$salt_hex$hash_hex`. Os parâmetros vão junto para que uma
linha antiga continue verificável depois de endurecermos os custos —
`needs_rehash()` diz quando regravar, e o login regrava sozinho.

Hash malformado devolve `False` em vez de levantar: um registro corrompido não
pode virar erro 500 na tela de login.

**Login não revela se o e-mail existe.** A verificação roda mesmo sem usuário,
contra um hash descartável, para que o tempo de resposta não enumere contas; e a
mensagem é a mesma nos dois casos.

**Tentativas limitadas** (`services/login_guard.py`, tabela `login_attempt`).
Depois de `LOGIN_MAX_FAILURES_PER_EMAIL` (padrão 5) falhas seguidas numa conta em
`LOGIN_WINDOW_SECONDS` (padrão 900), o login dela devolve **429** com
`Retry-After` até a janela passar. Durante o bloqueio, nem a senha certa entra,
para que o 429 não vire oráculo. Um acerto zera a contagem. Um mesmo IP com
`LOGIN_MAX_FAILURES_PER_IP` (padrão 30) falhas em contas quaisquer também é
bloqueado. E-mail inexistente é limitado igual ao existente. A contagem fica no
banco, e não na memória do processo, para valer com várias réplicas.

### Token de serviço SaaS → IA

A IA (`ia/`) exige `Authorization: Bearer <SERVICE_TOKEN>` em toda rota, menos
`/health` e a documentação, quando `SERVICE_TOKEN` está definido
(`ia/app/service_auth.py`, comparação em tempo constante). O SaaS manda
`INFERENCE_SERVICE_TOKEN` em toda chamada (`Settings.inference_headers()`):
diagnóstico, mapa de plantas e encaixe de contorno. Em produção o SaaS **não
sobe** sem o token. Junto vai `X-Training-Consent: 0|1`, o consentimento do
cliente para o treino (brief, seção 32). Com `0`, a IA não põe a imagem na fila
de revisão.

### Token de sessão

`<payload_b64url>.<assinatura_b64url>`, HMAC-SHA256 sobre o payload. Equivale a
um JWT `HS256` sem o cabeçalho negociável — o algoritmo não é negociado no token
justamente para eliminar a classe de ataque em que o cliente declara `alg: none`.

Validade padrão: 12 h (`USER_SESSION_TTL_SECONDS`).

O token é *bearer*: quem o tem, é. Por isso nada nele autoriza uma ação física —
a missão que o robô executa é assinada à parte, com Ed25519.

### Revogação

O token carrega o `sid` de uma linha em `user_session`, e **toda requisição
autenticada confere essa linha**. É o que separa este token de um papel assinado:
sem a tabela, ele valeria até vencer e nada no servidor poderia desdizê-lo — e
doze horas é pouco para atrapalhar um invasor e muito para um notebook roubado.

O custo é uma consulta por chamada. É o preço de poder responder "esta sessão
acabou **agora**" em vez de "acaba em algumas horas".

| Ação | Rota | O que derruba |
| --- | --- | --- |
| Ver os aparelhos conectados | `GET /v1/auth/sessions` | — |
| Sair de um aparelho | `DELETE /v1/auth/sessions/{id}` | só aquele; a própria sessão é o logout |
| Sair de todos | `POST /v1/auth/logout` | todas as suas, esta inclusive |
| Desligar alguém do cliente | `DELETE /v1/users/{id}/sessions` | todas as daquela pessoa |
| Trocar a própria senha | `POST /v1/auth/password` | as **outras**, não a sua |
| Redefinir a senha de outro | `POST /v1/users/{id}/password` | todas as do alvo |

Trocar a senha preserva a sessão de quem está trocando, de propósito: ser
deslogado pelo próprio ato de se proteger é o tipo de atrito que faz as pessoas
não trocarem a senha. A redefinição por administrador não preserva nenhuma — ali
quem age é outra pessoa, e o caso típico é alguém que perdeu o acesso ou foi
desligado.

A linha **não guarda o token**. Guarda o bastante para a pessoa se reconhecer na
lista ("Chrome no Windows, ontem à noite") e decidir o que derrubar; um token
guardado ali seria uma segunda cópia da credencial esperando vazamento.

Todo encerramento vira `session.revoked` na trilha, com quem derrubou e por quê.

**Tokens sem `sid` são recusados.** São os emitidos antes desta tabela existir, e
aceitá-los manteria vivas justamente as sessões que não se consegue alcançar.
Aplicar a migração `0007` desloga todo mundo uma vez.

### Tenant ativo

O token carrega o tenant escolhido no login. `X-Tenant-Id` permite trocar sem
novo login — útil para o agrônomo de cooperativa. O cabeçalho **escolhe, mas não
concede**: a associação é verificada a cada requisição.

Com várias associações e sem escolha explícita, a sessão nasce sem tenant e o
frontend pergunta. Adivinhar levaria alguém a operar na fazenda errada.

### Equipe da ValTexa: papéis de plataforma (brief, seção 28)

Quem opera a plataforma tem `User.platform_role` — um de cinco papéis, cada um
com as suas capacidades ([`rbac.PLATFORM_ROLE_CAPABILITIES`](../valtexa/security/rbac.py)):

| Papel | Pode |
|---|---|
| `superadmin` | tudo, inclusive dar e tirar papel de plataforma (`platform:role:manage`) |
| `suporte` | ler clientes, planos e uso; **entrar como cliente** (sessão de suporte) e ligar o modo assistido; auditoria global |
| `ia_dados` | coletas, fila de processamento, datasets, catálogo de modelos |
| `operacoes` | relevo, contorno e planejamento de cobertura; catálogo de modelos |
| `comercial` | criar e editar cliente, planos, assinatura e uso; registrar consentimento por termo — **sem** dado agronômico |

A migração 0010 levou quem tinha a antiga marca `is_platform_admin` para
`superadmin` e removeu a coluna. `User.is_platform_admin` continua existindo no
código como propriedade derivada ("tem algum papel de plataforma") e no
`/v1/auth/me`, por compatibilidade; **não concede nada** por si.

As rotas de plataforma (`/v1/admin/**`, `/v1/platform/**`) exigem a capacidade
específica de cada uma, com `require_platform(...)` (sem cliente) ou
`require_platform_in_tenant(...)` (trabalhando *sobre* um cliente indicado em
`X-Tenant-Id`, sem ser membro dele). Papel de cliente nenhum — nem o dono — passa
por elas. Papel de plataforma não vale nas rotas de cliente.

### Entrar como cliente: sessão de suporte (brief, seção 29)

**Não existe mais acesso silencioso.** Até a fase 2, a equipe entrava em qualquer
cliente como `admin`, com escrita total, sem motivo nem registro de entrada.
Agora, sem ser membro, as rotas de cliente respondem `403` com a orientação de
abrir uma sessão de suporte:

```
POST /v1/platform/support-sessions
{"tenant_id": "...", "reason": "Cliente relatou missão travada",
 "duration_minutes": 120, "ticket_ref": "CH-123"}
→ {"access_token": "...", "expires_at": "...", "session": {...}}
```

- **motivo obrigatório** (10+ caracteres) e **prazo** de 5 min a 8 h (padrão 2 h);
- o token devolvido vale **só naquele cliente** (outro `X-Tenant-Id` → 403) e não
  vale nas rotas de plataforma (403);
- **somente leitura por padrão**: qualquer método que não seja `GET/HEAD/OPTIONS`
  dá `403`, mesmo em rota que não exija capacidade;
- **modo assistido** (escrita) só explícito, com motivo próprio:
  `POST /v1/platform/support-sessions/{id}/mode {"mode": "assistido", "reason": "..."}`
  (ou `assisted_reason` na abertura). Nele a equipe age como **gestor** (`admin`)
  do cliente — sem aprovar aplicação (exclusivo do agrônomo) e sem mexer em dono
  ou cadastro;
- **toda requisição** vira linha na auditoria do cliente (`support.request` ou
  `support.request_denied`), com o interno como ator e `support_session_id`;
  toda escrita feita na sessão sai com o mesmo `support_session_id`;
- **saída registrada**: `POST /v1/platform/support-sessions/{id}/end` (aceita o
  próprio token de suporte) grava `support.session_ended` e derruba o token na
  hora; sessão vencida é encerrada como `expirou` no primeiro uso depois do prazo;
- o cliente vê quem entrou, por quê e quanto agiu em
  `GET /v1/tenants/current/support-sessions` (quem tem `audit:read`), e a
  `/v1/auth/me` da sessão traz `support_session` — o conteúdo da faixa no topo.

Implementação: [`deps._principal_de_suporte`](../valtexa/api/deps.py) e
[`services/support_sessions.py`](../valtexa/services/support_sessions.py).

---

## Robôs

### Por que assimétrico nos dois sentidos

**Robô → nuvem.** O dispositivo gera o próprio par Ed25519 no primeiro boot e
envia só a chave pública. A privada nunca sai do hardware. Consequência: um dump
do banco da ValTexa não contém nada capaz de se passar por um robô.

Um esquema HMAC não teria essa propriedade — para conferir a assinatura, o
servidor precisaria guardar o segredo em forma recuperável, e quem lesse a tabela
passaria a falar pelo robô.

**Nuvem → robô.** Mesma razão espelhada. Se o robô pudesse *verificar* uma missão
com um segredo compartilhado, também poderia *forjar* uma. Com Ed25519 ele
carrega só a chave pública da plataforma: um drone comprometido continua incapaz
de se autoconceder autorização para pulverizar.

Essa é a fronteira que o sistema inteiro existe para proteger.

### Provisionamento

```
técnico gera convite  →  grava no robô  →  robô troca por identidade permanente
```

O convite (`vtx_prov_…`) é de **uso único**, tem validade e pode ser amarrado a
um número de série. Só o hash fica guardado: o valor em claro aparece uma única
vez, na resposta. Perder significa gerar outro — um convite recuperável do banco
seria um convite vazado.

Reprovisionar **revoga** as credenciais anteriores. Duas ativas significariam
duas cópias do robô podendo falar ao mesmo tempo.

### Assinatura da requisição

Formato completo em [`DEVICE_PROTOCOL.md`](DEVICE_PROTOCOL.md), seção 4. Cobre
método, caminho, query, horário, nonce e sha256 do corpo — mudar qualquer um
invalida.

Ordem de verificação no servidor: cabeçalhos → credencial → dispositivo ativo →
horário → nonce → assinatura. Conferir o nonce antes da assinatura permitiria a
um atacante queimar nonces alheios; conferir a assinatura antes do horário
gastaria criptografia com lixo.

### Antirreplay

Duas travas que só funcionam juntas:

- **janela de horário** (`DEVICE_CLOCK_SKEW_SECONDS`, padrão 300 s) — uma
  requisição capturada hoje não vale amanhã;
- **nonce único por dispositivo** (`used_nonce`) — não vale duas vezes dentro da
  janela.

O nonce é consumido numa transação própria, com *commit* imediato. Se
participasse da transação da requisição, um handler que falhasse depois liberaria
o nonce de volta — e a repetição voltaria a ser aceita, que é exatamente o que o
mecanismo existe para impedir. A unicidade é garantida por restrição do banco,
não por uma checagem em Python que duas requisições simultâneas driblariam.

Linhas vencidas são removidas oportunisticamente a cada requisição autenticada.

### Comandos assinados

Todo comando enviado ao robô carrega quatro campos de controle, e cada um fecha
um ataque diferente:

| Campo | Impede |
|---|---|
| `device_id` | reencaminhar a outro robô o comando de um vizinho |
| `sequence` | reordenar comandos |
| `nonce` | repetir |
| `expires_at` | executar amanhã uma missão autorizada hoje |

O envelope é gravado byte a byte em `mission.command_payload`. Reassinar a cada
leitura criaria dois comandos válidos para a mesma missão, e o nonce deixaria de
significar alguma coisa.

**Missão bloqueada não tem assinatura.** A assinatura só existe depois do parecer
favorável, então nem por engano um comando dela é aceito.

---

## Chaves da plataforma

`COMMAND_SIGNING_SECRET` deriva o par Ed25519 por SHA-256 — o ambiente de
desenvolvimento funciona sem cerimônia de geração de chave.

Em produção, `Settings.production_problems()` exige que o segredo padrão seja
trocado **e** que seja diferente de `SESSION_SECRET`. Se fossem iguais, vazar a
sessão de um usuário passaria a permitir forjar uma missão assinada — a fronteira
entre "alguém entrou na conta" e "alguém mandou o drone pulverizar"
desapareceria.

Trocar o segredo troca o par de chaves e **invalida todo comando em trânsito**.
É o efeito desejado de uma rotação de emergência: os robôs param de aceitar
comandos até serem reprovisionados com a chave pública nova.

---

## Revogação

```http
POST /v1/devices/{id}/revoke-credentials
```

Resposta a robô roubado, perdido ou com comportamento anômalo. A partir daí toda
requisição assinada com essas chaves é recusada e o dispositivo fica `suspended`.
Voltar a operar exige provisionamento novo, presencial.

Suspender é diferente de revogar: um robô suspenso continua se autenticando e
enviando telemetria — o técnico precisa disso para diagnosticar — mas não recebe
mais missão.

---

## Papéis

Capacidades nomeadas, não hierarquia numérica. Um `OWNER` não "vale mais" que um
`AGRONOMIST`: podem coisas diferentes.

| Capacidade | Quem tem |
|---|---|
| `mission:approve_application` | **só** o agrônomo |
| `diagnosis:review` | só o agrônomo |
| `mission:dispatch` | owner, admin, operador |
| `device:provision` / `device:manage` | owner, admin, técnico |
| `mission:abort` | todos os papéis operacionais |
| `audit:read` | owner, admin, auditor |
| leitura | todos |

Duas escolhas com razão:

- **aprovar aplicação é exclusivo do agrônomo**, nem o dono da fazenda tem. É o
  ponto em que software vira produto químico no ar, e a responsabilidade é
  técnica e tem nome;
- **abortar é de quase todos.** Parar nunca deve depender de permissão rara:
  numa emergência, quem está perto do equipamento precisa conseguir agir.

Tabela: [`valtexa/security/rbac.py`](../valtexa/security/rbac.py). Nenhuma rota
decide permissão por conta própria.

**Só o dono dá, muda ou retira o papel de dono** (`403` para os demais). Antes, o
gestor — que tem `user:manage` — podia criar um dono, e o dono tem
`tenant:manage`, que o gestor não tem: escalada de privilégio por convite.

`GET /v1/auth/me` devolve as capacidades para o frontend esconder o que não cabe.
**Esconder é conveniência, não segurança** — cada rota confere de novo.

### Como isso é testado

`tests/test_isolamento_openapi.py` gera a lista de rotas de `app.openapi()`,
classifica cada operação pelo tipo de chamador e ataca todas: outro cliente (com
todos os papéis) não lê nem altera dado do cliente-vítima, nenhum papel de cliente
alcança rota de plataforma, robô de um cliente não alcança o outro, e sessão de
suporte em leitura não escreve em rota nenhuma. Rota nova sem classe reconhecida
faz o teste falhar.
