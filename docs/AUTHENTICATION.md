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

### Token de sessão

`<payload_b64url>.<assinatura_b64url>`, HMAC-SHA256 sobre o payload. Equivale a
um JWT `HS256` sem o cabeçalho negociável — o algoritmo não é negociado no token
justamente para eliminar a classe de ataque em que o cliente declara `alg: none`.

Validade padrão: 12 h (`USER_SESSION_TTL_SECONDS`).

O token é *bearer*: quem o tem, é. Por isso nada nele autoriza uma ação física —
a missão que o robô executa é assinada à parte, com Ed25519.

### Tenant ativo

O token carrega o tenant escolhido no login. `X-Tenant-Id` permite trocar sem
novo login — útil para o agrônomo de cooperativa. O cabeçalho **escolhe, mas não
concede**: a associação é verificada a cada requisição.

Com várias associações e sem escolha explícita, a sessão nasce sem tenant e o
frontend pergunta. Adivinhar levaria alguém a operar na fazenda errada.

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

`GET /v1/auth/me` devolve as capacidades para o frontend esconder o que não cabe.
**Esconder é conveniência, não segurança** — cada rota confere de novo.
