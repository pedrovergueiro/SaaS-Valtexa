# Documentação — índice

**Comece por aqui:**

| Documento | Para quê |
|---|---|
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | **A arquitetura oficial** do sistema inteiro (IA, plataforma, Rover): fluxos, limites, contratos, comandos |
| [`COMPONENTS.md`](COMPONENTS.md) | Cada componente: onde está, o que faz, estado (ativo, experimental, legado, arquivado) |
| [`DECISIONS.md`](DECISIONS.md) | Decisões e o motivo de cada uma; decisões pendentes |
| [`ESTADO_ATUAL.md`](ESTADO_ATUAL.md) | O que está medido, o que é simulação, o que falta provar |
| [`CLEANUP_REPORT.md`](CLEANUP_REPORT.md) | O que a consolidação de 20/10/2026 removeu, arquivou e mudou |

## Por assunto (documentos atuais)

| Documento | Assunto |
|---|---|
| `DEVICE_PROTOCOL.md` | Protocolo dispositivo ⇄ plataforma (assinatura, erros) — **para quem escreve firmware** |
| `ROVER_INTEGRATION.md` | Integração rota a rota do rover **simulado** (Scout, `simulator/devices.py`). O Runtime real está em `VALTEXA-ROVER/docs/ROVER_RUNTIME.md` |
| `DRONE_INTEGRATION.md`, `DOCK_INTEGRATION.md` | Drone e dock (a "base autônoma" do drone — **não** é a base da fazenda arquivada) |
| `AUTHENTICATION.md` | Chaves, rotação, revogação |
| `API.md` | Guia da API para o frontend |
| `TELEMETRY.md`, `EVENTS.md`, `MISSIONS.md`, `OFFLINE_MODE.md` | Telemetria, eventos, máquina de estados da missão, operação sem nuvem |
| `SAFETY.md` | Safety Engine: cada verificação e cada bloqueio |
| `AI_PIPELINE.md` | Dupla validação e os limites medidos |
| `DIGITAL_TWIN.md` | O gêmeo **do SaaS** (cópia 3D e série temporal). O gêmeo epidemiológico está no VALTEXA-B |
| `ENXAME.md` | Quem olha onde (Rovers, drone) |
| `COLLECTIONS.md` | Coletas aéreas e dataset |
| `SIMULATOR.md` | Como rodar a simulação e o que observar |
| `DEPLOYMENT.md` | O que a plataforma exige para subir em produção (segredos, migrações, escala) |
| `plataforma/DEPLOY.md` | O deploy de produção em si (compose, Caddy, Postgres, Redis, MinIO) |
| `plataforma/SEGURANCA.md`, `plataforma/OBSERVABILIDADE.md`, `plataforma/OTA.md` | Segurança e segredos; métricas e alertas; atualização remota |
| `plataforma/VALIDACAO_ROVER.md`, `plataforma/ESTRESSE.md` | Ensaios e portões de validação do Rover; números de estresse |
| `plataforma/CEREBRO.md`, `plataforma/PLANEJAMENTO.md`, `plataforma/FEDERADO.md`, `plataforma/DNATY.md` | Cérebro agronômico; planejamento de apoio; consenso federado; etapa dNATY |

Em outros repositórios: `VALTEXA-ROVER/docs/ROVER_RUNTIME.md` e `SYNC.md` (Runtime e
sincronização); `VALTEXA-B/README.md` e `MODELS.md` (IA, modelos, números medidos).

Alguns documentos por assunto foram escritos antes das rodadas da plataforma (set/2026) e
podem estar defasados em detalhes. Quando divergirem, **o código e os testes valem**, e
este índice e o `ARCHITECTURE.md` são a referência.

## Histórico (não é referência atual)

[`historico/`](historico/README.md): auditorias, verificações, progresso, rodadas, briefs,
critérios de aceite e versões antigas da arquitetura. Ficam para consulta e para entender
decisões. Os caminhos citados neles são do monorepo da nuvem (`rover/`, `saas/`, `ia/`).
