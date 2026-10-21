# Inventário de componentes

> Estado de 20/10/2026, depois da consolidação. Arquitetura: [`ARCHITECTURE.md`](ARCHITECTURE.md).

## Legenda de estado

| Estado | Significa |
|---|---|
| **ATIVO** | usado pelo produto, por um pipeline oficial ou por uma integração real |
| **ATIVO · justificado** | parece duplicado, mas existe de propósito (ver a observação) |
| **CLI** | ferramenta de linha de comando oficial (treino, medição, operação) |
| **MEDIÇÃO** | benchmark que fundamenta um número documentado (`MODELS.md`, docs) |
| **EXPERIMENTAL** | prova de conceito, não adotada em produção |
| **PENDENTE** | desenhado, desligado, à espera de uma decisão humana |
| **EM ANDAMENTO** | trabalho não terminado de alguém — **não mexer** |
| **LEGADO · compat.** | não é mais usado, mas fica por compatibilidade (banco, contratos) |
| **ARQUIVADO** | fora do produto, guardado em `archive/` com instruções de recuperação |

---

## VALTEXA-B (IA)

### API de inferência (`app/`)

| Componente | Responsabilidade | Estado | Testes |
|---|---|---|---|
| `main.py` | Rotas `/health`, `/models`, `/predict*`, `/review*`, `/models/{key}/continuo`; registra os roteadores | ATIVO | `test_api.py` |
| `config.py`, `keras_backend.py`, `onnx_runtime.py`, `service_auth.py`, `metrics.py` | Configuração, backend Keras 3/torch, ONNX, chave de serviço, métricas | ATIVO | `test_onnx_runtime`, `test_service_auth`, `test_metrics` |
| `registry.py`, `model.py` | Catálogo dos modelos e execução das previsões (TTA, conformal, qualidade, novidade, cabeça) | ATIVO | `test_registry`, `test_model_choices`, `test_tta` |
| `framing.py` | Portão de enquadramento SigLIP 2 ("cena vencedora é folha" no café) | ATIVO | `test_framing` |
| `inference/heads.py` | Cabeça sobre o embedding SigLIP (café: 0,964 isolado, 0,801 externo) | ATIVO | `test_heads` |
| `inference/conformal.py`, `quality.py`, `novelty.py`, `preprocess.py`, `explain.py` | Conjunto conformal, qualidade, novidade, pré-processamento (copiado para o Rover), atenção | ATIVO | `test_conformal`, `test_quality`, `test_novelty`, `test_preprocess`, `test_explain` |
| `inference/novidade_cabeca.py` | Novidade no embedding da cabeça (fonte da cópia do Rover; ajuste em `training/fit_novidade_cabeca.py`) | ATIVO | `test_vendor` (Rover) |
| `inference/prior_shift.py` | Prevalência por EM (`/fields/{id}/prevalence`) | ATIVO · justificado | `test_prior_shift` — o EM é marcado **não confiável** na resposta; a incidência por planta (`plant_fusion`) é a fonte oficial. `DriftMonitor` só é usado em teste (experimental) |
| `inference/continual.py`, `inference/atualizacao.py` | Aprendizado contínuo da cabeça (replay, portão, procedência) | ATIVO | `test_continual`, `test_atualizacao` |
| `rover.py`, `rover_api.py` | Quadro do Rover → recortes de 150 mm, `/predict/rover-frame` | ATIVO | `test_rover`, `test_rover_api` |
| `plant_fusion.py`, `fields_api.py` | **Fusão por planta (oficial)**, incidência, lesões, mapa, `/fields/*` | ATIVO | `test_plant_fusion`, `test_fields_api`, `test_edge_frames`, `test_lesoes` |
| `prescricao.py`, `aplicacao_localizada.py` | Prescrição por planta e mapa de aplicação de taxa variável | ATIVO | `test_prescricao`, `test_aplicacao_localizada` |
| `gemeo/*`, `gemeo_api.py` | Gêmeo epidemiológico (SEIR por planta, núcleo, clima, vento, previsão, prioridades VOI, levantamento aéreo) | ATIVO | `test_gemeo*`, `test_dispersao` |
| `review.py`, `active_learning.py` | Fila de revisão do agrônomo e a ordem dela | ATIVO | `test_review_priority`, `test_active_learning` |
| `severity.py`, `sigatoka_severity.py` | Severidade (área lesionada) e severidade da sigatoka no rover | ATIVO | `test_severity`, `test_sigatoka_severity` |
| `encaixe_carreador.py`, `contorno_api.py` | Encaixe do contorno nos carreadores e direção das ruas (FFT) | ATIVO | `test_encaixe_carreador` |
| `basemap.py`, `boundary.py`, `obstacles.py`, `terrain.py`, `terrain_api.py` | Terreno: imagem de satélite, contorno, obstáculos | **EM ANDAMENTO** | `test_terrain*`, `test_boundary`, `test_obstacles` — trabalho de terreno em curso; os 5 avisos de lint do repositório estão aqui |

### Treino e medição (`training/`, todos `python -m training.<nome>`)

| Componente | Estado | Observação |
|---|---|---|
| `prepare_dataset`, `dataset`, `dedupe_dataset`, `train`, `model_def`, `evaluate`, `export_onnx`, `metrics` | CLI | Pipeline oficial de treino |
| `fit_conformal`, `fit_quality`, `fit_novelty`, `fit_framing`, `fit_heads`, `fit_prior`, `fit_fusion`, `fit_edge`, `fit_novidade_cabeca` | CLI | Calibrações instaladas ao lado dos pesos |
| `train_severity`, `lesion_tiles`, `background` | CLI | Severidade e aumento de dados |
| `import_bracol`, `import_campo`, `import_plantseg`, `import_maize_in_field`, `download_public`, `demo_photos` | CLI | Importação de datasets e fotos de demonstração |
| `adapt_campo` | CLI | Aprendizado contínuo no campo (`memoria/adapta/promove/reverte/...`) |
| `mede_continuo`, `mede_gemeo`, `mede_dispersao`, `mede_enxame` | MEDIÇÃO | Fundamentam os números do `MODELS.md` |
| `audit_attention` | MEDIÇÃO | Auditoria de atenção |
| `robustez_captura` | EXPERIMENTAL | 3 tentativas, nenhuma em produção (a cauda em folhas sadias piorou o Rover); fica porque `adapt_campo` o usa como tipo de rodada |
| `motor_dnaty` | EXPERIMENTAL | Motor dNATY do aprendizado contínuo: medido e **não adotado** (desligado por padrão em `adapt_campo --motor`) |
| `dnaty_pipeline` | EXPERIMENTAL | Etapa dNATY do registry; dNATY tem licença **não comercial** |
| `pinn_dispersao` | EXPERIMENTAL | PINN da dispersão: **falhou** (erro de D até +141%); o ajuste direto do solver é o adotado |

---

## VALTEXA-SAAS (plataforma)

### Núcleo e API

| Componente | Responsabilidade | Estado |
|---|---|---|
| `valtexa/main.py`, `config.py`, `db.py`, `worker.py`, `seed.py` | App, configuração, banco, worker (eventos, alertas, retenção, fusão da borda) | ATIVO |
| `valtexa/models/` (25 arquivos), `migrations/` (0001–0035) | Modelo de domínio e migrações (**nunca reescrever migração aplicada**) | ATIVO |
| `valtexa/security/` (`rbac`, `signing`, `tokens`, `passwords`) | Papéis, assinatura Ed25519, tokens, senhas | ATIVO |
| `valtexa/api/` (`deps`, `middleware`, 34 roteadores) | HTTP; o middleware inclui o recibo assinado opcional (sem consumidor desde 20/10, mantido como controle) | ATIVO |
| `valtexa/observability/` + `services/observabilidade.py` | Middleware/métricas/logs (pacote) e o painel que lê banco + métricas (serviço) | ATIVO · justificado: camadas diferentes |

### Serviços (`valtexa/services/`)

| Grupo | Componentes | Estado | Observação |
|---|---|---|---|
| Missão e segurança | `mission_manager`, `planner`, `safety_engine`, `verification`, `hal` (capacidades), `energy`, `geo`, `elevation` | ATIVO | `planner` = rota/energia/postes; `mission_manager` = estados |
| Percepção e decisão | `ai_pipeline`, `decision_engine`, `review_priority`, `taxonomy`, `dataset`, `collections`, `collection_ingest`, `ingestion`, `storage` | ATIVO | Coleta aérea e observações do dispositivo |
| Ponte com a IA | `plant_map`, `fusao_borda`, `aplicacao_localizada`, `localizar` | ATIVO | Leem/escrevem a fusão oficial da IA |
| Resultado da missão | `missao_resultado`, `visao_operacional` | ATIVO · justificado | `plantas_da_missao` é o "estado da missão", não a fusão oficial |
| Gêmeo do SaaS | `twin` (série temporal por zona), `scene` + `pointcloud` (cópia 3D rua a rua) | ATIVO · justificado | Nome igual ao gêmeo da IA, coisa diferente |
| Enxame e planejamento | `enxame`, `compartilhamento`, `fleet_state`, `valtexa/planejamento/*` | ATIVO | Só rascunhos; nada vira aplicação sozinho |
| Cérebro agronômico | `valtexa/cerebro/*` | ATIVO | RAG + dossiê + parecer determinístico; LLM desligado |
| Frota e edge | `edge_sync`, `model_registry`, `ota`, `comando_rover`, `video_ao_vivo`, `saude_rover`, `orcamento_dados`, `coordenacao`, `ensaios`, `validacao_campo`, `federado`, `dnaty` | ATIVO | `dnaty` e `federado`: avaliação; dNATY não comercial |
| Contas e operação | `plans`, `consent`, `sessions`, `support_sessions`, `support_tickets`, `login_guard`, `notifications`, `alertas`, `events`, `jobs`, `audit`, `documentos`, `retention`, `saude` | ATIVO | — |
| Voo de observação do drone | `regra_voo_observacao` | **PENDENTE** | Desenhada e desligada; teste prova que o Safety Engine não a alcança. Decisão do Pedro |

### Outros

| Componente | Estado | Observação |
|---|---|---|
| `web/` (console React/TS) | ATIVO | `pages/` (cliente), `platform/` (console da equipe), `pages/admin/` (ferramentas administrativas: coletas, datasets, clientes, editor de contorno, planejador de missão) |
| `simulator/` | ATIVO | `python -m simulator`, `simulator.pomar`, `ponta_a_ponta`, `fase0` |
| `scripts/exporta_originais.py`, `scripts/mede_alocacao.py` | CLI / MEDIÇÃO | Validação de campo; número do enxame |
| `deploy/producao`, `deploy/observabilidade` | ATIVO | Pronto, **nunca implantado de verdade** |
| `hardware/rover-v3`, `hardware/rover-v4` | Documentação de projeto | CAD, BOM e desenhos (fora do lint) |
| `Field.cobertura*`, `Device.enlace_chave*`, `DeviceKind.GATEWAY` | LEGADO · compat. | Colunas/valor do banco da base arquivada |
| `archive/legacy/radio-fazenda/` | ARQUIVADO | Base, rádio, tela Bases — ver o README dali |

---

## VALTEXA-ROVER (runtime embarcado)

| Componente | Responsabilidade | Estado |
|---|---|---|
| `runtime/core.py`, `mission.py`, `store.py`, `buffer.py`, `retention.py`, `events.py`, `logs.py` | Laço do robô, missão offline-first, banco local, buffer circular, retenção | ATIVO |
| `runtime/sync.py`, `client.py`, `orcamento.py` | Sincronização com a plataforma e orçamento de dados da Starlink | ATIVO |
| `runtime/model_manager.py`, `ota.py`, `health.py`, `comandos.py`, `video.py`, `prioridades.py` | Modelos/OTA, saúde, comandos assinados, vídeo ao vivo, prioridades da missão | ATIVO |
| `runtime/percepcao.py` | Percepção ativa (vistas extras na dúvida, reobservação, luz, velocidade) | ATIVO |
| `edge_ai/engine.py`, `perfil.py`, `rgbd.py`, `geometria.py` | Edge AI: recortes, regra de evidência, RGB-D, geometria da folha | ATIVO |
| `edge_ai/vendor/*` | Cópias byte a byte do VALTEXA-B | ATIVO · justificado (conferido por `test_vendor.py`; funções não usadas no Rover ficam para manter a cópia idêntica) |
| `hal/interfaces.py`, `local.py`, `simulated.py`, `rover_v3.py`, `lente.py`, `diagnostico.py`, `relogio.py` | HAL; Rover V3 (OAK-D, ZED-F9P, Xsens, navegação por arquivo); relógio (chrony/GNSS) | ATIVO (`rover_v3` **nunca rodou no hardware**) |
| `ensaios/*` | Ensaios de validação (câmeras, GNSS, IMU, rede, relógio, segurança...) | ATIVO |
| `sim/*` | Hardware e nuvem simulados, estresse, orçamento simulado | ATIVO (simulação) |
| `cli.py`, `launcher.py` | `valtexa-rover` e o lançador do systemd | ATIVO |
| `deploy/` | Jetson: instalador, systemd, udev, CAN, chrony | ATIVO |
| `archive/legacy/radio-fazenda/` | `enlace/`, `hal/rede_base.py`, ensaios `enlace_*` | ARQUIVADO |

## VALTEXA-BASE

Inteira **ARQUIVADA** (20/10/2026). Não é repositório git — ver o README dela.
