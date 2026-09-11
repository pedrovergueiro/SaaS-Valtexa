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
próprio modelo, documentado em `VALTEXA-B/MODELS.md`:

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

## O que existe

| Camada | Onde | Estado |
|---|---|---|
| Modelo de domínio (30 tabelas) | `valtexa/models/` | completo |
| Migrações | `migrations/` (Alembic) | aplicadas no start |
| Autenticação, assinatura, RBAC | `valtexa/security/` | completo |
| Motor de decisão, safety engine, gêmeo digital | `valtexa/services/` | completo |
| API HTTP, com SSE | `valtexa/api/` | completa |
| Worker: eventos, expiração, conectividade, retenção | `valtexa/worker.py` | completo |
| Console — o SaaS visual | `web/` | completo (ver *Console*) |
| Frota simulada (rover, drone, dock) | `simulator/` | completa |
| Testes (188, em SQLite e Postgres) | `tests/` | completos |
| Firmware | — | **não construído** (ver `docs/*_INTEGRATION.md`) |

### Dois repositórios, um produto

| | O que faz | Python |
|---|---|---|
| **VALTEXA-SAAS** (aqui) | plataforma, frota, missões, segurança | 3.11+ (roda em 3.14) |
| **VALTEXA-B** | inferência: os modelos de doença foliar | 3.10–3.12 (limite do Keras) |

Estão separados de propósito. A plataforma consome a inferência por HTTP e não
carrega TensorFlow — é o que permite escalar a API sem GPU e prender a
versão de Python só onde o Keras exige.

---

## Rodando

### Simulação completa (recomendado para conhecer o sistema)

```bash
python -m simulator
```

Sobe a plataforma num processo próprio, cria a fazenda de demonstração e executa
o roteiro inteiro — inclusive **três momentos em que o sistema recusa agir**, que
é onde está o valor. Ver `docs/SIMULATOR.md`.

### Plataforma para desenvolvimento

```bash
cp .env.example .env
uvicorn valtexa.main:app --reload
```

- documentação interativa: <http://127.0.0.1:8000/docs>
- contrato OpenAPI: <http://127.0.0.1:8000/openapi.json>
- saúde: <http://127.0.0.1:8000/health>

Para conectar aos modelos reais, suba o `VALTEXA-B` em `:8000` e aponte
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
pytest                                            # 188 testes, em SQLite
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
                     PIPELINE DE IA  ──► VALTEXA-B (HTTP)
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
| `docs/DIGITAL_TWIN.md` | séries temporais e detecção de anomalia |
| `docs/OFFLINE_MODE.md` | o que o robô faz sem nuvem |
| `docs/EVENTS.md` | vocabulário de eventos |
| `docs/SIMULATOR.md` | como rodar e o que observar |
| `docs/DEPLOYMENT.md` | produção, migrações, escala |

---

## Console

O SaaS visual fica em `web/`: React 19, TypeScript, Vite, Tailwind, React Query,
Leaflet e Recharts. Ele consome exatamente as rotas de `/v1/**` — as mesmas que
os robôs e o simulador usam. Não há rota privada de frontend. Os tipos são
gerados do `openapi.json` (`npm run api:types`), então uma mudança de contrato
quebra o build do console, e não a tela em produção.

| Tela | Para quê |
|---|---|
| Painel | o que pede uma pessoa agora: alertas derivados do estado, frota, fila, volume aplicado |
| Mapa | talhões, frota e cada foto do rover sobre satélite, por janela de tempo |
| Missões | criar, aprovar, autorizar, despachar; o parecer da segurança verificação por verificação; a linha do tempo |
| Frota | provisionar robô; bateria, conectividade, telemetria e eventos |
| Fila do agrônomo | a foto, o palpite das duas análises, a novidade; diagnóstico em texto livre |
| Talhões | o gêmeo digital: observações no mapa, evolução, desvios, recomendações; desenho de talhão e zona |
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
5. **Nada foi testado com hardware.** Tudo que existe roda contra o simulador. As
   lacunas que dependem de robô físico estão listadas em cada
   `docs/*_INTEGRATION.md`.

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
