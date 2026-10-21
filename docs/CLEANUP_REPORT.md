# Relatório da consolidação — 20/10/2026

> Auditoria global, limpeza e consolidação dos projetos da ValTexa. Nada foi commitado:
> as mudanças estão na árvore de trabalho de cada repositório, para revisão.
> **Reversão**: snapshot completo de antes em
> `C:\Users\pedro\valtexa_snapshots\2026-10-20_antes-da-consolidacao\` (um `.tar.gz` por
> repositório, sem `.venv`, `node_modules`, `.git` e sem `data/`, `downloads/` e `models/` da
> IA; mais `*.diff-HEAD.patch`, `*.status.txt` e `*.HEAD.txt` de cada repositório e os
> resultados dos testes em `testes/`).

## 1. O que foi auditado

| Pasta | Git | Estado antes | Escopo |
|---|---|---|---|
| `VALTEXA-B` | `feat/keras3-torch-e-qualidade-de-dataset` @ 170feaf | 14 modificados, 28 não rastreados (rodadas 4–5) | auditado |
| `VALTEXA-SAAS` | `master` @ ccdb1c3 | 32 modificados, 54 não rastreados (rodadas 4–5) | auditado |
| `VALTEXA-ROVER` | `main` @ ece8c65 | 26 modificados, 16 não rastreados | auditado |
| `VALTEXA-BASE` | **sem git** | — | auditado → arquivado |
| `VALTEXA FRONT`, `VALTEXA-GESTAO` | limpos | — | inventariados; produtos à parte, fora do escopo |

O trabalho local não commitado das rodadas 4 e 5 foi tratado como **trabalho válido** e
preservado (ele é testado e está no snapshot).

Ferramentas da auditoria: grafo de importação estático de cada repositório (quem importa
quem, produção × teste), `vulture` filtrado (sem decorators de rota, validadores e callbacks)
com conferência textual de cada candidato em código, testes, docs, web e scripts, varredura
de links quebrados em todos os `.md`, e leitura dos módulos suspeitos de duplicação.

## 2. Principais achados

1. **Quase não havia código morto.** O lint passava e quase nenhum módulo estava órfão: o que
   parecia órfão eram CLIs, rotas registradas, regras desligadas de propósito ou experimentos
   documentados. Cinco itens eram mortos de fato (seção 3).
2. **A pilha de rádio/base** (≈ 7 mil linhas em três repositórios) tinha perdido a função com
   a Starlink em cada Rover. **Arquivada**, por decisão do Pedro (seção 4).
3. **Documentação concorrente**: três "arquiteturas" (`docs/ARCHITECTURE.md` de set/2026,
   `docs/plataforma/ARQUITETURA.md` "alvo Fase 1", o README do monorepo), documentos de
   processo da nuvem misturados com documentação viva, documentação do Rover dentro do SaaS e
   READMEs com caminhos do antigo monorepo (`../docs/...`, `cd base`, `../rover`).
4. **Duplicação real, mas justificada**: duas "fusões por planta" (calibrada na IA, operacional
   no SaaS) e três coisas chamadas de "gêmeo". Ficaram, com papéis documentados (seção 5).
5. **Testes frágeis na IA**: 7 testes falhavam conforme o conteúdo de `models/` da máquina.
6. **Bug de compatibilidade**: um teste do Rover usava `datetime.UTC`, que não existe no
   Python 3.10 da Jetson.
7. **Tipos do console desatualizados**: `web/src/api/schema.d.ts` não tinha as rotas das
   rodadas 4 e 5.
8. **Ambiente inconsistente**: a IA fixa `ruff==0.6.9`; SaaS e Rover aceitam `ruff>=0.6` (o
   venv do SaaS tem a 0.16.6, que acusa 55 avisos a mais na IA). README do SaaS citava
   migrações até 0031 (são 0035) e números de teste antigos.

## 3. Código morto removido

| Repositório | Item | Prova |
|---|---|---|
| SaaS | classe `schemas.ErrorResponse` | sem referência em código, testes, web, docs |
| SaaS | exceção `security.passwords.InvalidHashError` | definida, nunca levantada nem capturada |
| SaaS | função `services.twin.zones_of` (+ import `Zone`) | sem chamador |
| IA | função `app.gemeo.prioridade.selecionar` (+ import `Sequence`) | sem chamador |
| Rover | função `runtime.events.load_record` (+ import `json`) | sem chamador |

Candidatos que **não** eram mortos (falsos positivos conferidos): os `_cmd_*` do Rover
(despachados por `getattr`), `dispatch` do middleware, `on_epoch_end` (callback do Keras), as
funções de `edge_ai/vendor/` (cópias idênticas de propósito), `regra_voo_observacao`
(desenho desligado à espera de decisão), `DriftMonitor` (experimental, testado).

## 4. Arquivado — rádio da fazenda e base

| Repositório | Para onde | O quê |
|---|---|---|
| Rover | `archive/legacy/radio-fazenda/` | `enlace/` (17 módulos), `hal/rede_base.py`, `ensaios/enlace.py`, 7 arquivos de teste + 1 teste de `test_video.py`, `hardware.rover-v3.fazenda.json.exemplo` |
| SaaS | `archive/legacy/radio-fazenda/` | serviços `estacao_base`, `chave_de_enlace`, `cobertura_talhao`; 6 rotas; 4 regras de alerta; `health.base`; FASE ENLACE dos ensaios; 6 arquivos de teste; tela Bases, `lib/cobertura`, `lib/enlace` (+ testes); o JSON do ensaio de 24 h |
| BASE | a própria pasta, marcada **ARQUIVADO** no README | o software da base inteiro; `docs/COMUNICACAO_FAZENDA.md` foi para lá |

Cada arquivo tem um README com origem, motivo, substituto, dependências e **como
recuperar**. O código arquivado está fora do pacote, do pytest, do ruff, do build do
console e da imagem Docker.

**Mudanças no produto por causa do arquivamento**:

- Rover: o relógio (chrony/GNSS) ficou como `hal/relogio.py`, e o ensaio `relogio` só do Rover
  foi para a FASE 0, com 4 testes novos. A bancada simulada ganhou uma leitura de chrony
  (`chrony_de_bancada`, com defeito injetável) e a FASE 0 ganhou a etapa "relógio" — sem
  isso o portão da FASE 0 do simulador ficava fechado;
- Rover: `hardware.json` com `rede.modo` diferente de "direto" falha no boot com mensagem;
- Rover: a CLI perdeu `enlace-chave`, e o laço do serviço perdeu o serviço de enlace;
- SaaS: a missão perdeu `cobertura`, e o painel perdeu `caminho`;
- SaaS: `compartilhamento.POLITICA` perdeu a classe `cobertura` e a entrada `gateway`;
- SaaS: o catálogo de hardware perdeu `FARM_BASE_V1`;
- SaaS: o `relogio` foi para a FASE 0 também no catálogo, com um teste novo que prova que a
  conta é a mesma dos dois lados;
- SaaS: `test_contrato_sistemas` passou a conferir só o Rover; `test_recibo_dispositivo`
  confere a assinatura sozinho; o teste do orçamento usa a dock no lugar da base;
- SaaS: `requirements-dev.txt` não instala mais a BASE.

**Ficou por compatibilidade**: colunas `device.enlace_chave*` e `field.cobertura*` (migrações
0030/0031 já aplicadas), o valor `gateway` de `DeviceKind`, o recibo assinado do middleware
(controle de integridade, agora sem consumidor).

## 5. Duplicações: consolidadas ou justificadas

| O quê | Decisão |
|---|---|
| Fusão por planta: IA `plant_fusion` × SaaS `plantas_da_missao` | **Justificada** e documentada: a da IA é a oficial; a do SaaS é o "estado da missão". Unificar muda o motor de decisão → decisão pendente (D-02) |
| "Gêmeo": IA `app/gemeo/` × SaaS `twin` × SaaS `scene` | **Justificada**: epidemia por planta × série temporal por zona × cópia 3D. Documentado em `ARCHITECTURE.md` §3.3 e `COMPONENTS.md` |
| Planejadores: `planner` × `mission_manager` × `enxame` × `planejamento/robotico` | **Não é duplicação**: cobertura/energia × estados × quem olha × plano de apoio que **reaproveita** o enxame |
| Observabilidade: pacote `observability/` × serviço `observabilidade` | **Não é duplicação**: middleware/métricas × painel |
| `docker-compose.yml` (raiz) × `deploy/producao/docker-compose.yml` | **Justificada**: ensaio local × produção (comentário corrigido) |
| `DEPLOYMENT.md` × `plataforma/DEPLOY.md` | Complementares: exigências de produção × o deploy em si (índice explica) |
| Pré-processamento, cabeça, conformal, qualidade, novidade no Rover | **Justificada**: cópia byte a byte do VALTEXA-B em `vendor/`, conferida por teste |
| Três arquiteturas | **Consolidada**: uma oficial (`docs/ARCHITECTURE.md`), as outras em `docs/historico/` |

## 6. Documentação

**Criados**:

- `VALTEXA-SAAS/docs/README.md` (índice), `ARCHITECTURE.md` (o sistema inteiro),
  `COMPONENTS.md`, `DECISIONS.md`, `ESTADO_ATUAL.md` e este relatório;
- `docs/historico/README.md`;
- os READMEs dos dois arquivos.

**Movidos**:

- para `docs/historico/`: auditorias, verificação, progresso, rodada 4, briefs, aceite, plano
  do SaaS, a arquitetura de set/2026, a arquitetura alvo da Fase 1, o README e a CI do
  monorepo;
- para o Rover: `ROVER_RUNTIME.md` e `SYNC.md`, que ganharam as seções 19 e 20 marcadas
  ARQUIVADO;
- para a Base: `COMUNICACAO_FAZENDA.md`.

**Corrigidos**:

- os READMEs do Rover e da Base (caminhos do monorepo) e o do SaaS (migrações 0035,
  números de teste, frota e edge, tabela de documentos);
- o README da IA ganhou o apontamento para a documentação do sistema e o comando de
  teste oficial;
- os caminhos de documentos citados em docstrings (12 arquivos);
- os links quebrados nos documentos vivos (os do histórico ficam como estavam, e o índice
  avisa).

## 7. Outras correções

- IA `tests/conftest.py`: fixture automático `_models_dir_isolado` (cada teste começa com a
  pasta de modelos vazia) — as 7 falhas preexistentes sumiram.
- Rover `tests/test_inspecao_adaptativa.py`: `datetime.UTC` → `valtexa_rover._compat.UTC`
  (a suíte não coletava no Python 3.10).
- SaaS `web/src/api/schema.d.ts` regenerado do OpenAPI atual.
- `pyproject.toml` do Rover e do SaaS: `archive` fora do lint.

## 8. Testes

| Projeto | Antes | Depois | Observação |
|---|---|---|---|
| IA (WSL, Py 3.12) | 852 ✓, 5 pulados, **7 falhas** | **859 ✓, 5 pulados, 0 falhas** | as 7 falhas eram de isolamento (pasta `models/`) |
| SaaS (Py 3.14) | 1.111 ✓, 9 pulados | **1.085 ✓, 9 pulados, 0 falhas**; ruff limpo | − 27 casos (os arquivos de teste da base e 3 casos do contrato que conferiam a base), + 1 novo (a conta do relógio igual nos dois lados); o simulador da FASE 0 ganhou a etapa do relógio |
| Console web | 160 ✓ (registro anterior) | 153 ✓, `tsc` ok, build ok | − 7 testes das libs arquivadas |
| Rover (Windows, Py 3.14) | 366 ✓, 3 pulados | **303 ✓, 3 pulados** | − 67 testes arquivados + 4 novos do relógio |
| Rover (WSL, **Py 3.10** = Jetson) | não coletava (bug de `UTC`) | **294 ✓, 12 pulados** | — |
| BASE | 40 ✓, 1 pulado | arquivada | — |
| ruff | IA: 5 avisos (terreno em andamento); SaaS, Rover, BASE: limpos | iguais | o terreno é trabalho em andamento, fora dos limites |
| Simulador ponta a ponta (`python -m simulator`) | — | completo | missão retomada do checkpoint, 2 bloqueios do Safety Engine, decisão "observar", verificação agendada |

## 9. Pendente (decisão humana ou fora do alcance desta limpeza)

1. **Commitar** — nada foi commitado. Sugestão: um commit por repositório para as rodadas
   4–5 (que já estavam locais) e outro para a consolidação.
2. Versionar a pasta `VALTEXA-BASE` (não tem git) ou aceitar que ela viva só no snapshot.
3. Colunas legadas da base: apagar com migração nova ou manter.
4. Fusões por planta (D-02), regra de voo do drone, licença do dNATY.
5. Alinhar o `ruff` dos três projetos (fixar a mesma versão) — mudança de versão fica
   separada da limpeza, como pede a missão.
6. O terreno (`basemap`, `boundary`, `obstacles`, `terrain`, `terrain_api`) segue em
   andamento e não foi tocado.
7. Os documentos por assunto mais antigos (set/2026) não foram reescritos; podem estar
   defasados em detalhes — o índice avisa.
