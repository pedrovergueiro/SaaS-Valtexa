# Arquitetura da ValTexa (documento oficial)

> **Fonte única** da arquitetura do sistema inteiro — IA, plataforma e Rover. Atualizado na
> consolidação de 20/10/2026. Versões anteriores ficam em `docs/historico/` (só referência).
> Inventário peça a peça: [`COMPONENTS.md`](COMPONENTS.md). Por que as coisas são como são:
> [`DECISIONS.md`](DECISIONS.md). O que mudou na limpeza: [`CLEANUP_REPORT.md`](CLEANUP_REPORT.md).
> Estado do produto (o que está medido, o que é simulação): [`ESTADO_ATUAL.md`](ESTADO_ATUAL.md).

## 1. Os projetos

| Pasta (espaço de trabalho) | Repositório | O que é | Python |
|---|---|---|---|
| `VALTEXA-B` | `mugmt/VALTEXA-B` (origin) | **IA**: API de inferência, fusão por planta, gêmeo digital, treino | 3.10–3.12 (roda no WSL, 3.12) |
| `VALTEXA-SAAS` | `pedrovergueiro/SaaS-Valtexa` | **Plataforma**: API multi-tenant, frota, missões, decisão, Safety Engine, console web, simulador | 3.11+ (roda em 3.14) |
| `VALTEXA-ROVER` | `pedrovergueiro/VALTEXA-ROVER` | **Runtime embarcado** do Rover (Jetson): HAL, Edge AI, missão offline-first, sincronização | 3.10 (JetPack 6) |
| `VALTEXA-BASE` | — (sem git) | **ARQUIVADO** em 20/10/2026: a antiga base da fazenda (rádio) | — |
| `VALTEXA FRONT`, `VALTEXA-GESTAO` | outros repositórios | Site institucional e app de gestão interna — **fora** do produto descrito aqui | — |

Os três ativos são separados de propósito e **só se falam por HTTP**:

- a plataforma consome a IA por HTTP e não carrega Keras/torch (escala a API sem GPU);
- o Rover não importa código da nuvem; o que ele precisa da IA está **copiado byte a byte**
  em `VALTEXA-ROVER/valtexa_rover/edge_ai/vendor/` (conferido por `tests/test_vendor.py`);
- o Rover fala com a plataforma pelo **protocolo de dispositivo** (`/v1/device/**`, pedidos
  assinados com Ed25519 pela identidade do robô), por HTTPS direto pela **Starlink do
  próprio Rover**. Não há base nem rádio na fazenda.

## 2. O princípio que organiza tudo

> **Nenhum resultado de IA comanda diretamente uma aplicação.**

```
PERCEPÇÃO → DIAGNÓSTICO → RECOMENDAÇÃO → VALIDAÇÃO → AUTORIZAÇÃO → EXECUÇÃO → VERIFICAÇÃO
```

| Elo | Onde mora (implementação oficial) | Quem responde |
|---|---|---|
| Percepção | Rover: `runtime/core.py`, `edge_ai/engine.py`, `runtime/percepcao.py` · SaaS: `services/edge_sync.py`, `services/ingestion.py`, `services/collections.py` | o Rover (e a coleta aérea importada) |
| Diagnóstico | IA: `app/model.py` (por imagem), `app/plant_fusion.py` (por planta) · SaaS: `services/ai_pipeline.py` (dupla validação da observação), `services/fusao_borda.py` + `services/plant_map.py` (ponte para a fusão da IA) | modelos + fusão calibrada |
| Recomendação | SaaS: `services/decision_engine.py` (regras determinísticas) · IA: `app/prescricao.py`, `app/gemeo/prescricao_risco.py`, `app/aplicacao_localizada.py` | regras, nunca o modelo |
| Validação | SaaS: aprovação do agrônomo (`api/routers/agro.py`, `missions.py`) · IA: fila de revisão `app/review.py` | uma **pessoa** com nome e papel |
| Autorização | SaaS: `services/safety_engine.py` | camada **determinística**, que relê tudo do banco e falha fechada |
| Execução | SaaS: `services/mission_manager.py` (máquina de estados, missão assinada) → Rover/drone | o dispositivo, só com missão assinada |
| Verificação | SaaS: `services/verification.py` | nada é "eficaz" sem segunda passada |

A separação é **imposta por teste**: `VALTEXA-SAAS/tests/test_principio_de_ouro.py` varre o
código. A aprovação agronômica e a autorização do Safety Engine são etapas **separadas**.
Uma sessão de suporte da equipe não pode aprovar aplicação.

## 3. Fluxos de dados

### 3.1 Missão de inspeção (o caminho principal)

```
SaaS planner/mission_manager ──missão assinada──▶ Rover runtime/mission
                                                   │ captura (HAL: OAK-D, GNSS, IMU)
                                                   ▼
                                       Edge AI (edge_ai/engine.py):
                                       recortes de 150 mm → CNN ONNX ou SigLIP+cabeça (café)
                                       → regra de evidência (.edge.json) → evento? dúvida?
                                       → percepção ativa (vistas extras na dúvida)
                                                   │ fila offline-first (runtime/sync.py)
                                                   ▼  /v1/device/edge/records, /uploads
SaaS edge_sync ──▶ fusao_borda (geometria da rua/metro) ──▶ IA POST /fields/{id}/frames
                                                              │
                                     IA plant_fusion: posterior por planta, incidência,
                                     lesões entre passadas ──▶ GET /fields/{id}/...
SaaS plant_map / missao_resultado ◀──────────────────────────┘
   → decision_engine → recomendação → agrônomo aprova → safety_engine autoriza
   → missão de aplicação (mapa de aplicação localizada, PWM por bico) → verificação
```

Os eventos com original (foto inteira) também passam pela **IA de nuvem** (dupla validação,
`ai_pipeline`), porque a Edge AI só prioriza.

### 3.2 Coleta aérea importada

`collections` (upload em pedaços) → `collection_ingest` (worker) → `ai_pipeline` → diagnóstico →
fila do agrônomo. O drone **não** é comandado pela plataforma: o levantamento aéreo chega como
arquivo (`POST /v1/fields/{id}/gemeo/levantamento-aereo`). A regra de segurança do voo de
observação está desenhada e desligada (`services/regra_voo_observacao.py`, decisão pendente).

### 3.3 Gêmeo digital e onde olhar

- **IA** `app/gemeo/`: SEIR **por planta**, em probabilidade, atualizado por Bayes com a razão de
  verossimilhança da fusão, contágio por um núcleo espacial em O(N), clima (Open-Meteo,
  desligado por padrão), vento e dispersão, previsão por ensemble, prescrição por risco e
  prioridades por **valor da informação** (`/fields/{id}/gemeo/prioridades`).
- **SaaS** `services/enxame.py` decide **quem** olha (Rovers/drone, energia, deslocamento) e só
  cria **rascunhos**. As prioridades descem na missão assinada (`services/compartilhamento.py`)
  só para decidir a bordo, nunca como evidência (anti-eco).
- **Atenção ao nome**: o SaaS também tem um "gêmeo" (`services/twin.py` = série temporal por
  zona; `services/scene.py` = cópia 3D rua a rua). São coisas diferentes do gêmeo
  epidemiológico da IA — ver `COMPONENTS.md`.

### 3.4 Aprendizado com o campo

Dúvidas e eventos do Rover → fila de revisão (IA `app/review.py`, ordem por
`app/active_learning.py`) e validação de campo (SaaS `services/validacao_campo.py`, rótulo
por planta, exporta CSV) → `training/import_campo.py` → `training/adapt_campo.py`
(retreino da cabeça com replay e **portão** de não-regressão) → `promove --aprovador`
(grava a procedência) → registry/OTA → o Rover recusa cabeça sem procedência válida.

## 4. Limites de responsabilidade (implementação oficial)

| Responsabilidade | Fonte oficial | Consumidores | Observação |
|---|---|---|---|
| Classificar imagem/recorte | IA `app/model.py` + `app/registry.py` | IA API; Rover via `vendor/` | Rover roda o mesmo pré-processamento (cópia) |
| Portão de enquadramento | IA `app/framing.py` (SigLIP 2) | IA API, `fit_*` | — |
| Diagnóstico **por planta** (oficial) | IA `app/plant_fusion.py` | SaaS `plant_map`, `fusao_borda`, gêmeo, prescrição | **calibrada**; a fonte para incidência e prescrição |
| Estado da missão por planta | SaaS `services/missao_resultado.plantas_da_missao` | `decision_engine`, avisos, relatório | regra simples sobre diagnósticos já confirmados; **não** é a fusão oficial (decisão de 20/10/2026, ver DECISIONS) |
| Recomendação | SaaS `services/decision_engine.py` | missões | regras versionadas, nunca emite comando físico |
| Autorização física | SaaS `services/safety_engine.py` | `mission_manager` | independente de `decision_engine` |
| Planejamento de cobertura (rota, energia, postes) | SaaS `services/planner.py` | missões | determinístico |
| Ciclo de vida da missão | SaaS `services/mission_manager.py` | rotas, worker | máquina de estados explícita |
| Quem olha onde | SaaS `services/enxame.py` | `planejamento/robotico.py` reaproveita | só rascunho |
| Planos de apoio (fitossanitário, robótico, insumos) | SaaS `valtexa/planejamento/` | console | propõe, não age |
| Parecer agronômico | SaaS `valtexa/cerebro/` | console | determinístico; LLM desligado por padrão |
| Sincronização robô → nuvem | Rover `runtime/sync.py` ↔ SaaS `services/edge_sync.py` | — | contrato em `VALTEXA-ROVER/docs/SYNC.md` |
| Orçamento de dados (Starlink) | Rover `runtime/orcamento.py` ↔ SaaS `services/orcamento_dados.py` | — | teto assinado na missão |
| Modelos no robô | SaaS `services/model_registry.py`, `services/ota.py` ↔ Rover `runtime/model_manager.py`, `runtime/ota.py` | — | hash conferido; procedência para cabeças do aprendizado contínuo |

## 5. Contratos entre os sistemas

- **Dispositivo ⇄ plataforma**: `/v1/device/**`, assinado (Ed25519) com nonce; missões e
  comandos descem em envelope assinado pela plataforma. Referência: `docs/DEVICE_PROTOCOL.md`
  e `VALTEXA-ROVER/docs/SYNC.md`. **Teste de contrato**: `tests/test_contrato_sistemas.py` lê
  o código do Rover e confere que toda rota que ele chama existe no OpenAPI da plataforma.
- **Plataforma ⇄ IA**: HTTP, autenticado por chave de serviço (`app/service_auth.py`). Rotas
  principais: `/predict`, `/predict/batch`, `/predict/rover-frame`, `/fields/{id}/frames`,
  `/fields/{id}/plants|map|incidence|prescription|prevalence`, `/fields/{id}/gemeo/*`,
  `/encaixe-carreador`. Tabela completa no README do VALTEXA-B.
- **Artefatos de modelo** (registry/OTA → Rover): `<pesos>.onnx`, `.edge.json` (perfil e
  regra de evidência), `.categories.json`, `.edge-fusion.json`, `.head.npz` + encoder SigLIP
  (café), `.head.provenance.json` (aprendizado contínuo), `.novidade.npz`, `.quality.json`,
  `.conformal.json`. Inventário em `VALTEXA-B/models/README.md` e `SHA256SUMS`.
- **Console ⇄ API**: o console só usa `/v1/**`; os tipos são gerados do OpenAPI
  (`web/src/api/schema.d.ts`, `npm run api:types`).

## 6. Segurança e controle de acesso

- Multi-tenant com papéis do cliente e papéis da **plataforma** separados (`security/rbac.py`);
  "entrar como cliente" é sessão de suporte **auditada**.
- Assinatura: pedidos do dispositivo (Ed25519 do robô), comandos e missões (chave da
  plataforma), OTA assinada (`security/signing.py`).
- Safety Engine falha fechado; Princípio de Ouro testado; aprovação de aplicação recusada
  para sessão de suporte.
- Produção recusa subir com segredo padrão ou repetido (`Settings.production_problems()`).

## 7. Como executar cada projeto

| Projeto | Instalar | Testar | Rodar |
|---|---|---|---|
| IA (VALTEXA-B) | WSL: venv em `/home/pedro/valtexa/.venv` (`requirements*.txt`); no Windows o App Control bloqueia a DLL do ONNX | WSL: `pytest` (859 passam) + `ruff check .` (ruff **0.6.9**, fixado) | `uvicorn app.main:app --port 8001` (CPU: `CUDA_VISIBLE_DEVICES=""`) |
| Plataforma (VALTEXA-SAAS) | `python -m venv .venv` + `pip install -r requirements-dev.txt` (instala o Rover em modo editável) | `pytest` (~20 min) + `ruff check .`; `cd web && npm test && npm run build` | `python -m simulator` (tudo simulado) ou `uvicorn valtexa.main:app --reload` + `npm run dev` |
| Rover (VALTEXA-ROVER) | `uv venv -p 3.10 && uv pip install -e ".[dev]"` | `pytest` + `ruff check .` (também pelo venv do SaaS) | `valtexa-rover servico ...` (systemd na Jetson) |

## 8. O que é simulação

Todo o caminho roda **sem hardware**: Rover simulado (`valtexa_rover.sim`), frota simulada
(`simulator/`), IA real ou simulada. **Nada rodou no Rover real**, não houve piloto de campo
e os números de café vêm de folhas montadas em mosaico. Detalhes em
[`ESTADO_ATUAL.md`](ESTADO_ATUAL.md).
