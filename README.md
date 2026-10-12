# ValTexa — Plataforma Autônoma de Lavoura

Nuvem da ValTexa: frota, missões, percepção, decisão, segurança operacional e
gêmeo digital. É o backend do SaaS — **API-first**, sem nenhuma regra de negócio
morando na tela.

O sistema **funciona hoje, inteiro, sem hardware nenhum**. Um comando sobe a
plataforma, provisiona três robôs simulados e roda uma missão completa: coleta,
diagnóstico, recomendação, aprovação do agrônomo, autorização de segurança,
aplicação e verificação.

```bash
python -m venv .venv && .venv/Scripts/activate      # Linux/macOS: source .venv/bin/activate
pip install -r requirements-dev.txt
python -m simulator
```

---

## O princípio que organiza tudo

> **Nenhum resultado de IA comanda diretamente uma aplicação.**

```
PERCEPÇÃO → DIAGNÓSTICO → RECOMENDAÇÃO → VALIDAÇÃO
   → AUTORIZAÇÃO → EXECUÇÃO → VERIFICAÇÃO
```

Cada elo grava a sua própria linha e nenhum sobrescreve o anterior. A IA detecta
e recomenda; quem autoriza é uma pessoa com nome e papel, e quem libera a ação
física é uma camada de segurança determinística que relê tudo do banco e falha
fechada.

Isso não é excesso de cerimônia — é a resposta a um limite **medido** do nosso
próprio modelo, documentado em `Valtexa-B/MODELS.md`:

| Situação | O que o modelo faz |
|---|---|
| Doença **fora do catálogo** (cercosporiose retida do treino) | responde com **0,88 de confiança média**; 64% acima de 0,90 |
| Filtro de novidade (limiar 1,0) | intercepta **4%** |
| `MIN_CONFIDENCE = 0,70` | intercepta **17%** |
| Os dois juntos | **19%** |

Ou seja: **81% de uma doença desconhecida passaria como diagnóstico confiante e
errado.** Nenhuma arquitetura conserta isso no nível da imagem. O que a
plataforma faz é não deixar esse erro chegar sozinho a um bico aberto:

- **amostra mínima** — um diagnóstico isolado nunca vira aplicação; exige-se
  incidência sobre dezenas de observações vizinhas (erro pontual não se repete
  em escala, infestação sim);
- **dupla validação com independência medida** — concordância entre modelos
  correlacionados não conta como evidência;
- **anomalia no talhão** — `GET /v1/fields/{id}/anomalies` compara a semana com
  a linha de base. Uma doença nova classificada consistentemente como "ferrugem
  comum" é invisível quadro a quadro, mas faz a ferrugem comum daquele talhão
  saltar de 5% para 40%. **É a única detecção que funciona quando a de novidade
  falha.**
- **fila do agrônomo** — o rótulo que ele escreve não precisa existir no
  catálogo do modelo. É assim que uma doença nova entra no dataset próprio.

---

## Como a imagem chega: rover e coleta aérea

Duas portas de entrada, e elas não se confundem.

**O rover** entra pelo protocolo de dispositivo: assina cada requisição com
Ed25519, manda telemetria, observação e varredura 3D. É a frota da ValTexa, e o
caminho está pronto do lado da nuvem — falta o firmware.

**A imagem aérea** entra pelo painel administrativo. No MVP a ValTexa **não voa**:
quem voa é um operador terceirizado, manualmente, e entrega os arquivos. Alguém
da equipe importa o lote em *Importar Coleta*, e a partir daí o caminho é o
mesmo do rover — mesma fila, mesmo pipeline, mesma dupla validação, mesma fila do
agrônomo.

```
OPERADOR TERCEIRIZADO ──► arquivos ──► PAINEL ADMIN ──► fila ──► ValTexa-B ──► SaaS
ROVER ──► /v1/device/** ─────────────────────────────► fila ──► ValTexa-B ──► SaaS
```

O upload é em pedaços e retomável: uma coleta são centenas de arquivos e dezenas
de gigabytes, e não existe limite artificial — o teto é o do armazenamento
contratado. O administrador pode fechar a aba; o processamento é do worker.

### O que a plataforma recusa a responder

Nenhum modelo treinado hoje analisa imagem aérea. `aerial-canopy` existe no
catálogo do Valtexa-B e **não tem pesos** — está marcado como "precisa de
coleta". Uma coleta aérea nasce, por isso, com `model_key` nulo e o motivo por
extenso, que aparece no painel e na tela do cliente.

As imagens são guardadas, catalogadas e georreferenciadas, e vão inteiras para o
agrônomo. **Nenhuma passa por classificador.** Mandar foto de dossel ao modelo de
folha devolveria uma das classes de folha, com confiança alta, sobre uma imagem
onde nenhuma delas pode ser vista — o modo de falha medido em
`Valtexa-B/MODELS.md`.

E é assim que o `aerial-canopy` deixa de precisar de coleta: cada rótulo que o
agrônomo escreve vira amostra do dataset aéreo. O caminho do upload
administrativo **é** o caminho de formação do dataset do modelo que ainda não
existe. → `docs/COLLECTIONS.md`

### Não faz parte desta fase

Drone próprio, voo autônomo, planejamento de voo, transmissão automática e
pulverização aérea. Não há tela, não há rota disfarçada e não há dado simulando
que exista: `POST /v1/admin/drone-missions` responde **501**, e uma coleta com
origem `drone_owned` é recusada com **422**.

---

## O que existe

| Camada | Onde | Estado |
|---|---|---|
| Modelo de domínio (83 tabelas) | `valtexa/models/` | completo |
| Migrações | `migrations/` (Alembic, 0001–0031) | aplicadas no start |
| Autenticação, assinatura, RBAC | `valtexa/security/` | completo |
| Motor de decisão, safety engine, gêmeo digital e cópia 3D | `valtexa/services/` | completo |
| Coletas: upload em pedaços, fila, dataset | `valtexa/services/collections.py` | completo (ver *Coletas*) |
| Painel administrativo da ValTexa | `valtexa/api/routers/admin.py` | completo (cadastro de cliente, coletas, dataset, planejamento) |
| API HTTP, com SSE | `valtexa/api/` | completa |
| Worker: eventos, expiração, conectividade, retenção | `valtexa/worker.py` | completo |
| Console — o SaaS visual | `web/` | completo (ver *Console*) |
| Frota simulada (rover, drone, dock) | `simulator/` | completa |
| Frota: model registry, OTA assinada, sincronização do rover, enlace e estação-base | `valtexa/services/` | completo do lado da nuvem (ver *Frota e edge*) |
| Observabilidade, notificações, chamados de suporte, planos e consentimento | `valtexa/observability/`, `valtexa/services/` | completo |
| Produção: compose, Caddy, Prometheus, Grafana | `deploy/` | pronto, nunca implantado de verdade |
| Hardware do rover (chassi, desenhos, DXF) | `hardware/` | documentação de projeto |
| Testes (66 arquivos, ~850 funções de teste; rodam em SQLite e em Postgres) | `tests/` | completos |
| Firmware | — | **não construído** (ver `docs/*_INTEGRATION.md`) |
| Drone próprio, voo autônomo, pulverização aérea | — | **fase futura**, sem código (ver *Coletas*) |

### As contas da equipe da ValTexa

Quem opera a plataforma não é membro de fazenda nenhuma. O que o distingue é
`User.platform_role` — `superadmin`, `suporte`, `ia_dados`, `operacoes` ou
`comercial`, cada um com as suas capacidades (menor privilégio). Para ver ou agir
nos dados de um cliente, a equipe abre uma **sessão de suporte** ("entrar como
cliente"): motivo, prazo, somente leitura por padrão, escrita só em modo
assistido explícito, cada requisição na auditoria do cliente e saída registrada.
Não há acesso silencioso. → `docs/AUTHENTICATION.md`

As contas estão em `PLATFORM_TEAM`, em `valtexa/seed.py`, e nascem no start —
**mas só se `PLATFORM_ADMIN_PASSWORD` estiver no ambiente**:

```bash
PLATFORM_ADMIN_PASSWORD='uma-senha-longa' uvicorn valtexa.main:app
```

Sem a variável, nenhuma conta é criada e o log diz isso. É deliberado: uma senha
de administrador de plataforma com padrão no código seria a mesma em toda
instalação, e a primeira que alguém tentaria.

O seed é conservador — roda a cada start e **não** sobrescreve conta que já
existe, nem senha, nem nome. A única coisa que ele atualiza é dar o papel
`superadmin` a quem está na lista e ainda não tem papel de plataforma, que é o
que conserta uma conta criada antes de a pessoa entrar para a equipe. Os outros
papéis se dão pelo console (`PUT /v1/platform/users/{id}/platform-role`, só o
superadmin). Trocar a senha depois se faz pelo console.

### Planos, uso e consentimento

O cliente tem **plano** (`plan`, `subscription`, `usage_counter`): hectares,
fazendas, talhões, robôs, usuários e missões por mês são conferidos nas rotas que
os criam, com `409` e a conta em português; assinatura suspensa ou vencida dá
`402`. Todo cliente anterior aos planos foi para o `piloto` (sem limites), com o
texto antigo de `contracted_service` preservado. Os valores dos planos
`essencial`, `profissional` e `empresarial` são **provisórios** — decisão
comercial pendente.

Dado de cliente só entra em dataset de treino com **consentimento SIM** vigente
(`data_consent`, padrão NÃO), dado pelo dono no console ou registrado pela ValTexa
com o termo assinado.

### Frota e edge

O que a nuvem já oferece para um rover que ainda não existe em campo:

- **Model Registry** — só roda no robô o modelo publicado, com hash conferido;
- **OTA assinada** — publicação, alvo, acompanhamento, A/B e *rollback* (`docs/plataforma/OTA.md`);
- **Sincronização do rover** — chunks, retomada, prioridade e idempotência por
  `(dispositivo, sequência)` (`docs/plataforma/SYNC.md`);
- **Enlace e estação-base** — protocolo de enlace à prova de falha, malha com
  repetidoras e levantamento de cobertura (`docs/plataforma/COMUNICACAO_FAZENDA.md`);
- **Observabilidade** — métricas, regras e painéis em `deploy/observabilidade/`
  (`docs/plataforma/OBSERVABILIDADE.md`);
- **Produção** — compose com API, worker, IA, Postgres, Redis, MinIO, Prometheus e
  Caddy em `deploy/producao/`; segredos fracos ou repetidos são recusados
  (`docs/plataforma/DEPLOY.md`, `docs/plataforma/SEGURANCA.md`).

O andamento, com números, está em `docs/plataforma/PROGRESSO.md`.

### Três repositórios, um produto

| | O que faz | Python |
|---|---|---|
| **[SaaS-Valtexa](https://github.com/pedrovergueiro/SaaS-Valtexa)** (aqui) | plataforma, frota, missões, segurança, console | 3.11+ (roda em 3.14) |
| **[VALTEXA-ROVER](https://github.com/pedrovergueiro/VALTEXA-ROVER)** | runtime do computador embarcado: HAL, Edge AI (ONNX), missão offline-first, sincronização | 3.10 (Jetson Orin NX, JetPack 6) |
| **[Valtexa-B](https://github.com/pedrovergueiro/Valtexa-B)** | inferência: os modelos de doença foliar | 3.10–3.12 (limite do Keras) |

Estão separados de propósito. A plataforma consome a inferência por HTTP e não
carrega TensorFlow — é o que permite escalar a API sem GPU e prender a
versão de Python só onde o Keras exige. O rover não importa o código da nuvem:
os dois só se falam pelo protocolo de dispositivo. Os projetos de hardware
(rover V3 e V4) ficam em `hardware/`.

---

## Rodando

### Simulação completa (recomendado para conhecer o sistema)

```bash
python -m simulator
```

Sobe a plataforma num processo próprio, cria a fazenda de demonstração e executa
o roteiro inteiro — inclusive **três momentos em que o sistema recusa agir**, que
é onde está o valor. Ver `docs/SIMULATOR.md`.

```bash
python -m simulator.pomar                                  # bananal e pomar, IA simulada
python -m simulator.pomar --ia http://127.0.0.1:8001     --fotos <pasta de training.demo_photos> --manter       # com a IA do Valtexa-B
```

O rover entre bananeiras e laranjeiras, com as câmeras laterais do mastro, duas
passadas com uma semana entre elas; com a IA de verdade, as plantas, a evolução
de cada uma e a prevalência saem da fusão por planta do Valtexa-B.

### Plataforma para desenvolvimento

```bash
cp .env.example .env
uvicorn valtexa.main:app --reload
```

- documentação interativa: <http://127.0.0.1:8000/docs>
- contrato OpenAPI: <http://127.0.0.1:8000/openapi.json>
- saúde: <http://127.0.0.1:8000/health>

Para conectar aos modelos reais, suba o `Valtexa-B` em `:8000` e aponte
`INFERENCE_URL`.

### Console

```bash
cd web
npm install
npm run dev         # http://127.0.0.1:5173, com proxy de /v1 para :8000
```

Em produção a própria API serve o console compilado (`npm run build` gera
`web/dist`). Para abrir o console com dados, rode o simulador com `--keep` — o
passo a passo está em `docs/SIMULATOR.md`.

### Testes e qualidade

```bash
pytest                                            # em SQLite (a suíte completa leva minutos)
TEST_DATABASE_URL=postgresql+psycopg://... pytest # os mesmos, em Postgres
ruff check .                                      # PEP 8, importações, simplificações
cd web && npm run build                           # tipos do console e build
```

---

## Como as peças conversam

```
ROVER ─┐
DRONE ─┼─► /v1/device/**  (Ed25519, nonce, validade)
DOCK  ─┘         │
                 ▼
        INGESTÃO ──► TELEMETRIA · EVENTOS · OBSERVAÇÕES
                             │
                             ▼
                     PIPELINE DE IA  ──► Valtexa-B (HTTP)
                       IA A  +  IA B
                             │
                             ▼
                        DIAGNÓSTICO
                             │
                             ▼
                    MOTOR DE DECISÃO         ← regras versionadas
                             │
                             ▼
                  APROVAÇÃO DO AGRÔNOMO      ← pessoa, papel, assinatura
                             │
                             ▼
                       SAFETY ENGINE          ← independente, falha fechada
                             │
                             ▼
                    MISSÃO ASSINADA ──► robô verifica antes de agir
                             │
                             ▼
                        EXECUÇÃO ──► VERIFICAÇÃO ──► GÊMEO DIGITAL
```

Detalhes em `docs/ARCHITECTURE.md`.

---

## Decisões que valem explicar

**Assinatura assimétrica nos dois sentidos.** O robô gera o próprio par Ed25519
no primeiro boot e envia só a chave pública; a plataforma guarda só a pública.
Um dump do banco não permite se passar por nenhum robô. No sentido inverso, o
robô carrega apenas a chave pública da plataforma — um drone comprometido
continua incapaz de se autoconceder autorização para pulverizar.
→ `docs/AUTHENTICATION.md`

**O safety engine não importa o motor de decisão.** A dependência é
deliberadamente unilateral: se a regra agronômica ficar errada, a segurança
continua íntegra. Ele relê tudo do banco em vez de confiar no que recebe, e dado
ausente é bloqueio — sem leitura de vento, não pulveriza.
→ `docs/SAFETY.md`

**Aprovar aplicação é capacidade exclusiva do agrônomo.** Nem o dono da fazenda
tem. É o ponto exato em que software vira produto químico no ar, e o papel é
reconferido no momento da autorização — entre a assinatura e o voo, ele pode ter
sido revogado.

**Sincronização idempotente por `(dispositivo, sequência)`.** O servidor **não**
recusa sequência menor que a última vista: um lote preso offline chega fora de
ordem e é dado legítimo. O que ele faz é ignorar o que já gravou.
→ `docs/OFFLINE_MODE.md`

**Cobertura em segmentos.** Um rover que voltou para recarregar continua da faixa
seguinte. Sem isso o produto seria inviável acima de algumas dezenas de hectares.
→ `docs/MISSIONS.md`

**Camada de abstração de hardware.** O backend nunca pergunta "é o rover V1?";
pergunta "tem RTK? quantos tanques? qual a autonomia?". Trocar LiDAR, câmera,
GNSS ou fabricante — ou receber o robô de um parceiro — é cadastrar um
`device_model`, não alterar código. → `valtexa/services/hal.py`

**Eventos por *outbox* transacional.** O evento é gravado na mesma transação que
mudou o estado: ou os dois acontecem, ou nenhum. A entrega é ao-menos-uma-vez,
então todo handler é idempotente. → `docs/EVENTS.md`

---

## Documentação

| Arquivo | Para quem |
|---|---|
| `docs/ARCHITECTURE.md` | quem vai mexer no sistema |
| `docs/DEVICE_PROTOCOL.md` | **quem vai escrever firmware** |
| `docs/ROVER_INTEGRATION.md` | firmware do rover, rota a rota |
| `docs/DRONE_INTEGRATION.md` | firmware do drone, incluindo fail-safe |
| `docs/DOCK_INTEGRATION.md` | firmware da base |
| `docs/AUTHENTICATION.md` | segurança: chaves, rotação, revogação |
| `docs/API.md` | quem vai construir o frontend |
| `docs/TELEMETRY.md` | o que medir e com que frequência |
| `docs/MISSIONS.md` | máquina de estados e retomada |
| `docs/SAFETY.md` | todas as verificações e o que cada bloqueio significa |
| `docs/AI_PIPELINE.md` | dupla validação e os limites medidos |
| `docs/DIGITAL_TWIN.md` | a cópia 3D rua a rua, séries temporais e detecção de anomalia |
| `docs/OFFLINE_MODE.md` | o que o robô faz sem nuvem |
| `docs/EVENTS.md` | vocabulário de eventos |
| `docs/SIMULATOR.md` | como rodar e o que observar |
| `docs/DEPLOYMENT.md` | produção, migrações, escala |
| `docs/COLLECTIONS.md` | coletas aéreas e formação do dataset |
| `docs/plataforma/` | rodada de plataforma: arquitetura, auditoria, OTA, sincronização, enlace, observabilidade, segurança, deploy, ensaios |

---

## Console

O SaaS visual fica em `web/`: React 19, TypeScript, Vite, Tailwind, React Query,
Leaflet, Recharts e three.js. Ele consome exatamente as rotas de `/v1/**` — as mesmas que
os robôs e o simulador usam. Não há rota privada de frontend. Os tipos são
gerados do `openapi.json` (`npm run api:types`), então uma mudança de contrato
quebra o build do console, e não a tela em produção.

| Tela | Para quê |
|---|---|
| Painel | o que pede uma pessoa agora: alertas derivados do estado, frota, fila, volume aplicado |
| Mapa | talhões, frota e cada foto do rover sobre satélite, por janela de tempo |
| Missões | criar, aprovar, autorizar, despachar; o parecer da segurança verificação por verificação; a linha do tempo |
| Frota | provisionar robô; bateria, conectividade, telemetria e eventos |
| Fila do agrônomo | a foto, o palpite das duas análises, a novidade; por *novidade* ou por *valor para o treino*, com o motivo de cada item; o que o portão de enquadramento e o conjunto conformal disseram; diagnóstico em texto livre |
| Talhões | o gêmeo digital: observações no mapa, evolução, desvios, recomendações; desenho de talhão e zona; a versão do modelo de diagnóstico (campo ou comercial, com o acerto medido); as plantas vistas pelo rover e a prevalência estimada |
| Lavoura 3D | a cópia do talhão montada rua a rua pelo rover: cada planta medida, praga e doença presas à planta fotografada, a nuvem de pontos de cada rua, andar na rua, o estado em cada dia de passada |
| Aplicações | o comprovante de cada aplicação e o antes e depois da verificação |
| Insumos | produtos, lotes com validade, carga de tanque |
| Auditoria | quem fez o quê, quando e por quê |
| Configurações | pessoas e papéis; o estado da plataforma |

Tempo real por SSE (`/v1/stream`): cada evento de domínio invalida só as
consultas que afeta, e os incidentes — calda fora da área, falha de robô,
bloqueio de segurança — viram aviso na tela.

`GET /v1/auth/me` devolve `capabilities`; a interface usa a lista para esconder o
que o papel não permite. **Esconder é conveniência, não segurança** — cada rota
confere de novo, no servidor.

Tema claro e escuro, seguindo o sistema, e layout de celular com barra inferior:
o agrônomo revisa a fila no campo. O `VALTEXA FRONT` continua sendo o site
institucional; o console é outra aplicação.

---

## Limitações honestas

O que **não** está pronto, e por quê:

1. **O segundo analisador não conta como independente por padrão.** O
   `leaf-foliar-b` (outra arquitetura, mesmo dataset) foi medido: quando
   concorda com o primário, acerta 98,1%, e a discordância pega 60% dos erros —
   mas 40% dos erros são compartilhados, e 55% de uma doença nunca vista passa
   concordante. Com `SECONDARY_MODEL_INDEPENDENT=false`, o padrão, nada chega a
   `AI_VALIDATED` e tudo vai para a fila do agrônomo. Ligar é decisão sobre essa
   medida, de preferência repetida com imagens da própria frota.
   → `docs/AI_PIPELINE.md`
2. **A severidade é área no quadro, e fica fora da decisão.** A segmentação de
   lesão erra em média 7,6 pontos percentuais do quadro (correlação 0,89 com a
   máscara), mas mede lesão sobre a imagem, não sobre a folha, e ainda não foi
   comparada com a escala de um fitopatologista. O agrônomo vê o número; a regra
   de aplicação não o usa. → `docs/AI_PIPELINE.md`
3. **`SIMULATED_INFERENCE`** troca os modelos por analisadores falsos, para o
   simulador. É recusado em produção — um diagnóstico inventado chegando a um
   produtor seria pior do que não ter diagnóstico.
4. **SQLite é o padrão** e não aguenta a escrita concorrente da telemetria.
   Produção é Postgres; `/health` avisa. → `docs/DEPLOYMENT.md`
5. **Nada foi testado com hardware.** Tudo que existe roda contra o simulador, e o deploy de produção nunca foi feito de verdade. As
   lacunas que dependem de robô físico estão listadas em cada
   `docs/*_INTEGRATION.md`.
6. **A cópia 3D roda hoje sobre plantas simuladas.** O protocolo da passada, a
   composição rua a rua e o console estão prontos; falta o driver do LiDAR gerar
   o PLY e a segmentação embarcada que transforma a nuvem em plantas medidas — e
   comparar altura e copa com régua no campo. → `docs/ROVER_INTEGRATION.md`

---

## Conectando o primeiro robô de verdade

1. cadastre o modelo em `device_model` (ou use um dos três de referência);
2. gere o convite: `POST /v1/provisioning-tokens` com o número de série;
3. grave o convite no robô;
4. no primeiro boot, o robô gera o par de chaves e chama
   `POST /v1/device/provision`;
5. guarde `device_id`, `key_id`, a chave privada e a **chave pública da
   plataforma**;
6. assine cada requisição conforme `docs/DEVICE_PROTOCOL.md`.

A referência executável do cliente é `simulator/client.py` — o firmware
reproduz o que está ali. Passo a passo por tipo de robô em
`docs/ROVER_INTEGRATION.md` e `docs/DRONE_INTEGRATION.md`.
