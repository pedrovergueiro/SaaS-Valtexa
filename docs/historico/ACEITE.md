# Critérios de aceite (brief, seção 58) — estado em 10/10/2026

> **19/10/2026 (rodada 4)**: os critérios dos briefs 7.x e 8.x e do orçamento de dados estão
> em [Rodada 4](#rodada-4--enxame-heterogêneo-7x-cérebro-agronômico-8x-e-orçamento-de-dados-19102026).

> **10/10/2026 (rodada 3, local):**
> * **Pesos reais:** os 31 critérios rodaram também com o modelo real do café, fotos de
>   folha reais e o serviço `ia/` de verdade: **31 de 31**, mais 21b, 22b e 23b (fusão
>   calibrada, incidência corrigida e prescrição planta a planta). O roteiro e os números
>   estão em "Ponta a ponta com pesos reais", abaixo.
> * **Novos critérios:** validação de cada peça e comunicação da fazenda, na seção "Rodada 3".

> **Parte 9**: os 31 critérios rodaram de novo sobre o código final — `python -m simulator
> --rover-runtime` (uvicorn + Rover Runtime pela HAL de rede): **31 de 31 OK**, com os
> mesmos números abaixo; e `tests/test_ponta_a_ponta.py` dentro das suítes completas (**888 passed, 3 skipped** no SQLite
> e os mesmos 888 no **Postgres 16**). Nenhum critério mudou de estado: os 8 PARCIAIS dependem de pesos reais,
> hardware ou do serviço de IA ligado — nada disso dá para fechar em código aqui. O que a
> Parte 9 acrescentou por baixo dos critérios 13, 18, 19, 29 e 31 (S3 com *staging*
> compartilhado, Redis, segredos, hardening) está na tabela "Outros testes" ao fim.

**Como provar tudo de uma vez:**

```bash
cd saas
.venv/bin/pytest -q -s -o addopts="--strict-markers" tests/test_ponta_a_ponta.py   # ~50 s
# ou, com servidor HTTP de verdade (uvicorn) e o Rover falando HTTPS pela HAL de rede:
.venv/bin/python -m simulator --rover-runtime
```

O roteiro (`saas/simulator/ponta_a_ponta.py`) faz tudo **pela API**, como o cliente e a
equipe fariam, com o **`rover/` de verdade** (Core, Mission Manager, Model Manager, Edge AI
pelo ONNX Runtime, banco local, buffer, retenção, Sync Engine) sobre a **HAL simulada**. O
banco só é tocado para criar as contas da equipe ValTexa. A última execução (dos dois jeitos)
passou nos 31 itens; as provas abaixo são a saída real dela.

**Legenda.** **OK** — funciona e está testado de ponta a ponta. **PARCIAL** — o caminho
existe e roda, mas depende de algo que não está aqui (peso real, hardware, tela) — dito em
cada linha. **FALTA** — não existe. **O que é simulado no roteiro**: o hardware do Rover
(câmeras, GPS, rede), o **modelo da Edge AI** (`modelo_demo.onnx`, 282 bytes, não
agronômico), a **IA de nuvem** (`SimulatedAnalyzer`, que lê o "chão de verdade" que a câmera
simulada anexa ao JPEG), o **drone** que aplica (cliente do protocolo) e o efeito do
tratamento (as plantas tratadas aparecem sadias na passada seguinte).

| # | Critério | Estado | Prova (teste/comando) e números da última execução |
| --- | --- | --- | --- |
| 1 | Criar cliente | **OK** | `POST /v1/admin/tenants` pelo papel Comercial (cliente + plano + fazenda + talhão numa transação). `test_ponta_a_ponta.py` passo 1; `test_cadastro.py` |
| 2 | Usuário | **OK** | gestor, agrônomo e operador criados pelo Suporte em **modo assistido** (auditado) via `POST /v1/users`; cada um entra com a própria senha. Passo 2; `test_plataforma_e_suporte.py` |
| 3 | Fazenda | **OK** | criada no cadastro; `POST /v1/farms` também (`test_estresse_frota.py`). Passo 3 |
| 4 | Talhão | **OK** | com contorno, cultura e linhas. Passo 4; `test_talhao_completo.py` |
| 5 | Configurar espaçamento | **OK** | `PATCH /v1/fields/{id}`: 3,5 m entre linhas e 0,7 m entre plantas — o mesmo espaçamento do campo simulado que o Rover percorre. Passo 5 |
| 6 | Criar missão | **OK** | missão de varredura criada, **parecer de segurança** (bateria vinda da telemetria do Rover, geocerca), comando **assinado** e despachado. Passo 6 |
| 7 | Associar Rover | **OK** | o Rover entrou na frota pelo provisionamento (par Ed25519 gerado nele) e é o destinatário do comando. Passo 7 |
| 8 | Executar missão no simulador | **OK** | o Mission Manager do `rover/` confere assinatura, destinatário, validade, sequência e nonce, aceita e confirma (`ack`) à plataforma. Passo 8 |
| 9 | Simular captura | **OK** (simulação, por definição) | 140 quadros de 2 câmeras de cena (cada câmera fotografa a planta mais próxima do GPS). Passo 9 |
| 10 | Edge AI real | **OK** | O mesmo roteiro com os **pesos reais do café**. `python -m simulator --rover-runtime --ia ... --modelo-real coffee_foliar.onnx --folhas ...`: `coffee_foliar.onnx` com cabeça e torre do SigLIP 2, publicado no registry pelo SHA-256 e conferido pelo Model Manager, roda no ONNX Runtime do `rover/` sobre fotos de folha reais do BRACOL separado, que o modelo não viu (`valtexa_rover.sim.folhas`). Passo 10, execução de 10/10/2026. O roteiro de CI segue com o modelo de demonstração. |
| 11 | Classificar imagens | **OK** | Pesos reais: 140 quadros → 109 NORMAL, 27 POSSÍVEL DOENÇA e 4 POSSÍVEL PRAGA. Por quadro: planta sadia 15% de evento (alarme falso); ferrugem e bicho-mineiro 65%, com metade das folhas doentes. **Os limiares do café são provisórios**: a acurácia só a coleta de campo mede. Passo 11 |
| 12 | Criar evento | **OK** | 8 `IMAGE_EVENT_DETECTED` (com ID e hash), mais `MISSION_*`, `ROVER_OFFLINE/ONLINE`, `UPLOAD_*`. Passo 12 |
| 13 | Preservar imagem importante | **OK** | 8 originais guardados para 8 eventos + contexto do buffer circular. Passo 13; `rover/tests/test_buffer.py`, `test_retention.py` |
| 14 | Não enviar tudo | **OK** | 140 quadros → 8 originais + 132 reduzidas (2,95 MB guardados). Em volume: 10.000 quadros, 6,04 GB → 565 MB (9,4 %) (`test_retention.py`) |
| 15 | Simular perda de internet | **OK** (simulação) | 30 passos sem rede, com **reinício do robô no meio**. Passo 15 |
| 16 | Continuar offline | **OK** | 66 itens na fila durante a queda; a missão não parou. Passo 16 |
| 17 | Recuperar conexão | **OK** | rede de volta: `ROVER_ONLINE`, a fila volta a andar. Passo 17 |
| 18 | Sincronizar | **OK** | fila do Rover zerada; registros idempotentes, arquivos em chunks com retomada. Passo 18; `test_rover_integracao.py` |
| 19 | Processar na plataforma | **OK** | 151 registros em `GET /v1/edge/records`; cada evento com original vira observação (ponte Edge AI → nuvem, `edge_record.observation_id`). Passo 19 |
| 20 | Gerar resultado | **OK** | Com o **serviço `ia/` de verdade** (WSL, `INFERENCE_URL`): 12 eventos viraram observação + diagnóstico (7 Healthy, 3 Rust, 1 Leaf_Miner_Damage, 1 Phoma). Com um analisador só não há par independente: o diagnóstico espera o agrônomo (dupla validação); no roteiro, a revisão é simulada e está dita. Passo 20 |
| 21 | Associar à planta/região | **OK** | Pesos reais: as **4 de 4** plantas doentes achadas (doente, suspeita ou revisar), com 16 de 44 sadias longe de doente em alarme. Todos os quadros do Rover entram na **fusão calibrada do `ia/`** (passo 21b: 98 fundidos, 42 duplicados recusados). Ressalva: no simulador o robô anda sobre a linha e cada quadro é uma folha, então a fusão pelo GNSS conta 72 plantas onde há 54. O mapa de plantas de campo e a acurácia vêm da coleta. Passos 21 e 21b |
| 22 | Incidência | **OK** | 4/54 plantas = 7,4 % (IC 95 % de Wilson: 2,9 %–17,6 %), por planta e por doença (`GET /v1/missions/{id}/plants`). Passo 22 |
| 23 | Prescrição | **OK** | Motor de decisão + missão de pulverização (passo 23). **Prescrição planta a planta do `ia/` ligada ao SaaS** (`POST /v1/fields/{id}/plants/prescription`, passo 23b), sobre a fusão calibrada: tratar 40 de 72 plantas, 80% do ganho de pulverizar tudo por 56% do custo, com o aviso de que o alcance de contágio é o padrão do módulo. Recomendação: nada é aplicado sem o agrônomo. Passos 23 e 23b |
| 24 | Aprovar | **OK** | a pulverização é **bloqueada** sem a aprovação do agrônomo e liberada depois dela (tanque carregado, vento da dock, RTK, produto registrado). Passo 24 |
| 25 | Registrar aplicação | **PARCIAL** | aplicação aberta e fechada pelo protocolo assinado, com rastro dentro do polígono, `application.completed` na auditoria — **pelo drone simulado** (não há runtime de drone nem hardware). Passo 25 |
| 26 | Nova missão | **OK** | segunda varredura, mesmo Rover, comando assinado com **sequência por robô** (defeito corrigido nesta parte). Passo 26 |
| 27 | Comparar resultados | **OK** | incidência 7,4 % → 1,9 %; recuperadas L1-P006, L1-P007, L2-P012; persistente L3-P004 (`GET /v1/missions/{id}/comparison`). Passo 27 |
| 28 | Relatório | **OK** (API) | `GET /v1/missions/{id}/report`: fazenda, talhão, Rover, data, duração, área, imagens processadas, eventos, ocorrências, incidência, recomendações, prescrição, histórico, comparação com a anterior e a marca `simulated`. Sem PDF nem tela ainda. Passo 28 |
| 29 | Tudo no SaaS | **OK** | Parte 8: o console do cliente mostra tudo o que a API tem. **Relatório da missão** (`/missoes/:id/relatorio`): resumo, plantas (54), **registros da Edge AI** com filtro por categoria/planta/“só com imagem” e a **imagem original** (`GET /v1/edge/records/{id}/files/{upload_id}`), recomendações, prescrição, comparação; **CSV** e **impressão/PDF**. **Comparação entre missões** (`/missoes/comparar`), **linha do tempo do talhão** (`/talhoes/:id/historico`: missão → ocorrências → prescrição → aprovação → aplicação → verificação), **mapa por missão** (estado/doença por planta, calor, eventos, rota, pragas, comparação; umidade/falhas/produtividade só como interface, sem dado) e **painel** da seção 45 (área, varreduras, ocorrências, IA 24 h, saúde da frota, sincronização por robô). Prova: `web/e2e/telas-e-mapa.mjs` sobre o ponta a ponta (`prepara_telas_e_mapa.py`), API servindo o build: **13 de 13 passos, 0 erro de JS** (as telas novas do cliente: 10 passos); `tests/test_visao_operacional.py` (6) e o isolamento gerado do OpenAPI; vitest `mapLayers`, `edgeRecords`, `reportExport`, `fieldHistory` |
| 30 | Tudo no console interno | **OK** | Parte 8: **publicar pacote OTA** (tipo; versão do registry em PRODUÇÃO com o nome do artefato que o `.tar` precisa conter; arquivo), **destinar** (robôs escolhidos ou o cliente inteiro) e acompanhar por robô; **registrar rodada dNATY** a partir do relatório do `dnaty_pipeline.py` (a tela recusa antes o que o registry recusaria e pede a URI do otimizado; o veredito é o recalculado). Prova: mesmo roteiro, passos 11–13 (pacote `cfg-e2e8` publicado e destinado → “Pendente”; rodada aceita → “É o otimizado atual”); vitest `platformForms` |
| 31 | Auditar as ações | **OK** | 60 entradas na trilha do cliente nesta execução (provisionamento, edição do talhão, missão, aprovação, aplicação, sessão de suporte...); OTA, registry e otimização auditados na trilha da equipe. Passo 31; `test_acesso_e_trilha.py` |

**Resumo: 30 OK, 1 PARCIAL, 0 FALTA.** O PARCIAL é o 25: a aplicação é registrada pelo
protocolo assinado, mas pelo drone simulado, porque não há runtime de drone nem hardware.
Os critérios 10, 11, 20, 21 e 23 passaram a OK em 10/10/2026 com o roteiro rodando com os
pesos reais, as fotos reais e o serviço de IA de verdade (seção abaixo). A acurácia em
campo não é critério de aceite do software: é a validação agronômica (FASE 5 do
`VALIDACAO_ROVER.md`).

**Atualização de 07/10/2026 (grupo 1, local):** os modelos reais de banana e citros rodam
na Edge AI com o perfil calibrado (`fit_edge`; regra por evidência — fora da amostra,
banana 99/125 plantas doentes priorizadas com 5,3% dos quadros sadios, citros 33/33 com
6,0%), testados com os pesos reais (`VALTEXA_MODELOS_REAIS`); todos os resultados do
Rover vão à fusão por planta calibrada (`services/fusao_borda.py` → `POST
/fields/{id}/frames`), com a linha da navegação ou do GPS; a prescrição por planta está
ligada (`POST /v1/fields/{id}/plants/prescription`). Os critérios 10, 11, 21 e 23 seguem
PARCIAIS até o roteiro de ponta a ponta rodar com o serviço de IA real e os pesos reais.

## Ponta a ponta com pesos reais (10/10/2026)

```bash
# no WSL: o serviço ia/ com FIELDS_DIR, só CPU
MODELS_DIR=/home/pedro/valtexa/models FIELDS_DIR=... uvicorn app.main:app --port 8001
# no SaaS:
python -m simulator --rover-runtime --ia http://127.0.0.1:8001     --modelo-real <modelos>/coffee_foliar.onnx --folhas <BRACOL separado>/
```

Resultado: 31 de 31 OK + 21b, 22b e 23b, em ~7 min de CPU. As provas estão nas linhas 10,
11, 20, 21 e 23 acima.

**Simulado:** o robô andando, a rede, a montagem do quadro (uma folha por quadro), a
revisão do agrônomo e o drone.

**Achado:** um quadro montado com várias fotos põe a emenda entre elas dentro de cada
recorte, e a IA lê a emenda como lesão: P(sadia) cai de 0,95 para até 0,06. Por isso a
câmera de folhas monta um recorte por quadro (`docs/SIMULATOR.md`).

## Rodada 3 — validação de cada peça e comunicação da fazenda

| # | Critério | Estado | Prova |
| --- | --- | --- | --- |
| R1 | Catálogo de ensaios por peça, com portão por fase e veredito no servidor | **OK** | `saas/tests/test_ensaios_plataforma.py`, `test_ensaios_enlace_plataforma.py`; aba Validação (`web/e2e/validacao.mjs`) |
| R2 | Ensaios automáticos no Rover pelo comando assinado `ensaio` | **OK** (bancada simulada) | `rover/tests/test_ensaios.py`, `test_ensaio_comando.py`; `python -m simulator --fase0` |
| R3 | Base da fazenda: proxy assinado, guarda e reenvia sem Starlink, uplink por prioridade | **OK** (rádio emulado) | `base/tests/`; `saas/tests/test_base_fazenda.py` |
| R4 | Enlace que não cai: vários rádios, malha, troca sozinha, zero perda de P0–P3 | **OK** (emulado) | `rover/tests/test_enlace*.py`, `test_malha.py`; ensaio de 24 h simulado (`docs/ensaios/enlace-24h-simulado.json`) |
| R5 | Base como dispositivo: identidade, retrato, caminho no centro de comando, alarmes | **OK** | `saas/tests/test_estacao_base.py`; `test_base_fazenda.py` confere o caminho com o Rover trabalhando pela base |
| R6 | OTA da base | **OK** | `saas/tests/test_base_ota.py` (instala, sobe pelo lançador, confirma; recusa pacote errado) |
| R7 | Cadastro das chaves de enlace e mapa de cobertura pela plataforma | **OK** (rádio emulado) | `saas/tests/test_chave_de_enlace.py`, `test_cobertura_talhao.py`, `test_contrato_sistemas.py` (base → plataforma → Rover); `base/tests/test_plataforma.py`; `rover/tests/test_travessia.py` (`COMUNICACAO_FAZENDA.md` §17) |
| R8 | Estação de pilotagem: vídeo ao vivo + controle de videogame/teclado, homem-morto e PARAR | **OK** (câmeras simuladas) | `rover/tests/test_video.py`, `saas/tests/test_video_ao_vivo.py`, `test_base_fazenda.py` (vídeo pela base); roteiro de navegador com controle simulado (ROVER_RUNTIME §21) |
| R9 | Contrato entre Rover, base e plataforma (rotas, cabeçalhos, prioridade no enlace) | **OK** | `saas/tests/test_contrato_sistemas.py` |

Nada da rodada 3 rodou em hardware: rádios, Starlink, OAK-D, RTK e Jetson só em emulador ou
bancada simulada.

## Rodada 4 — enxame heterogêneo (7.x), cérebro agronômico (8.x) e orçamento de dados (19/10/2026)

> Verificação final da rodada, branch `claude/cerebro-agronomico`, Parte 3. Régua: os dois
> briefs (`docs/BRIEF_ENXAME_HETEROGENEO.md`, `docs/BRIEF_CEREBRO_AGRONOMICO.md`) lidos com
> `docs/RODADA4.md`. **OK** = feito e provado por teste (ou número medido); **PARCIAL** = existe
> e é testado, mas não fecha o item; **NÃO** = não feito. Nada rodou com modelo real (os pesos
> não estão aqui) nem em hardware: a IA dos testes é dublê e os números de Starlink são
> simulados, marcados como tal. Suítes da verificação final: ver `docs/PROGRESSO.md`
> (Rodada 4 — Parte 3).

### 7.1 — Fusão federada de priores (`docs/FEDERADO.md`)

| # | Critério | Estado | Evidência |
| --- | --- | --- | --- |
| 7.1a | `merge_priors` do dNATY avaliado, conclusão escrita | **OK** | `ia/tests/test_dnaty_merge_priors.py` (3): 2% e 20% viram o mesmo prior; 10 e 10 000 plantas pesam igual; serve para operadores de mutação. Não adotado |
| 7.1b | Representação compartilhada + compatibilidade (taxonomia, modelo/cabeça, validação, janela) | **OK** | `saas/tests/test_federado.py::test_compatibilidade_recusa_com_motivo` (6 casos); a cabeça antiga é recusada na API |
| 7.1c | Fusão matemática definida (hierárquica, encolhimento) | **OK** | Beta-binomial com κ por momentos e teto de força (200): `test_encolhimento_segue_a_heterogeneidade_dos_estratos`, `test_prior_do_estrato_puxa_para_o_estrato_e_a_forca_tem_teto` |
| 7.1d | Anti-eco | **OK** | por observação (`test_a_mesma_observacao_conta_uma_vez`) e por origem — o próprio dado não volta (`test_o_prior_que_volta_ao_talhao_nao_tem_o_dado_dele`) |
| 7.1e | Avaliar antes de distribuir | **OK** | deixa-um-talhão-de-fora: distribui com ganho (> 0) e recusa contra referência forte (`test_avaliacao_antes_de_distribuir`) |
| 7.1f | Distribuir aos autorizados e verificar no dispositivo | **NÃO** | o prior é calculado e exposto (`GET /v1/fields/{id}/federado/prior`), não desce na missão; quem consome (fusão por planta da IA) é decisão do Pedro |
| 7.1g | Bytes reais medidos | **OK** | carga de um talhão/dia 576 B JSON / 279 B gzip (1 estrato × 5 classes); 1 232 / 343 B com 3 estratos; prior de 5 classes 1 202 / 330 B (medido no corpo sintético) |
| | **7.1 no todo** | **PARCIAL** | falta a descida e o consumo (7.1f) |

### 7.2 — Coordenação drone → Rover

| # | Critério | Estado | Evidência |
| --- | --- | --- | --- |
| 7.2.1 | Mapeamento aéreo → regiões suspeitas | **OK** (canal suposto) | levantamento **importado** em GeoJSON (cobertura + regiões suspeitas): `POST /v1/fields/{id}/gemeo/levantamento-aereo` → IA `POST /fields/{id}/gemeo/levantamento` → LLR por planta no canal `drone` (dentro da região: ln(s/a); coberta e fora: ln((1−s)/(1−a)); fora da cobertura: nada) → muda as prioridades do gêmeo. `ia/tests/test_gemeo_levantamento.py` (2), `saas/tests/test_levantamento_aereo.py` (3). O canal do drone (0,45/0,06) é **suposição de projeto**, dita na resposta |
| 7.2.2 | Priorização com histórico, incidência, incerteza, disponibilidade, bateria | **OK** | VOI ganhou ou empatou em 24/24 combinações (`saas/docs/ENXAME.md` §3); disponibilidade e bateria no alocador (`saas/tests/test_enxame.py`, 9) |
| 7.2.2b | … e condições de acesso (inclinação, obstáculos) | **OK** | o plano robótico do 8.3 **e o plano do enxame que cria a missão** usam as mesmas restrições (`test_planejamento.py`: inclinação acima do limite tira o Rover, declive custa tempo, mata tira o trecho; `test_plano_do_enxame_usa_as_mesmas_restricoes`) |
| 7.2.3 | Missão ao Rover mais adequado | **OK** | guloso valor/s com deslocamento: 35,7% do valor coberto com 1 Rover contra 6,2% da varredura (`scripts/mede_alocacao.py`); missão em RASCUNHO |
| 7.2.4 | Revisão e decisão pelo agrônomo | **OK** | parecer + revisão (`test_cerebro_parecer.py`), fila de revisão do plano fitossanitário (`test_planejamento.py`) |
| 7.2.5 | Execução controlada | **OK** | `saas/tests/test_principio_de_ouro.py` (16) |
| 7.2.6 | Regra de segurança do voo de observação (desenhada, desligada) | **OK** (desligada, aguarda o Pedro) | `saas/valtexa/services/regra_voo_observacao.py`: vento, GNSS, energia, altura (premissa a confirmar na regulação), piloto em linha de visada, janela diurna, sem aplicação, geometria; `tests/test_regra_voo_observacao.py` (3): cada verificação segura, ninguém importa a regra e o Safety Engine continua bloqueando o voo |
| | **7.2 no todo** | **OK** (com ressalva) | o voo não é comandado pela plataforma (decisão do Pedro); o canal do drone é suposição até a calibração com plantas rotuladas |

### 7.3 — Alocação baseada em incerteza

| # | Critério | Estado | Evidência |
| --- | --- | --- | --- |
| 7.3a | `f(risco, incerteza, impacto, custo, disponibilidade)` | **OK** | VOI (`ia/app/gemeo/prioridade.py`) + alocador; números acima |
| 7.3b | Calibrada contra missões excessivas em áreas pouco relevantes | **OK** | valor mínimo por minuto de robô, do produtor: `test_planejamento.py::test_valor_minimo_por_minuto_evita_missao_excessiva`. Sem o número do produtor, não corta (premissa dita) |
| 7.3c | Calibrada contra regiões importantes esquecidas | **OK** | piso de vigilância (14 dias, não medido): `test_piso_de_vigilancia_nao_deixa_trecho_esquecido` — trecho de valor zero visto há 30 dias entra com a bateria que sobra |
| | **7.3 no todo** | **OK** (com ressalva) | as calibrações valem no plano de apoio e no plano do enxame; os dois limiares (valor por minuto, 14 dias) são premissas não medidas e o benchmark dos dois modos de falha não foi rodado |

### Orçamento de dados (Starlink de cada Rover)

| # | Critério | Estado | Evidência |
| --- | --- | --- | --- |
| D1 | Teto por Rover (dia e missão), no `rover.json` e pela plataforma (assinado na missão) | **OK** | `rover/tests/test_orcamento.py` (23), `saas/tests/test_orcamento_dados.py` (6) |
| D2 | Contabilidade do que subiu (Rover × plataforma) | **OK** | os mesmos; vídeo ao vivo e pedido que cai no meio contados (verificação hostil da Parte 2) |
| D3 | Corte por prioridade (comando, segurança, telemetria, eventos críticos nunca cortam) | **OK** | `test_orcamento.py`; prioridade 1 nunca retida |
| D4 | Tempestade de eventos | **OK** | `test_orcamento.py` (histerese, `EVENT_STORM`) |
| D5 | Deduplicação por planta (k melhores originais) | **OK** | `test_orcamento.py` |
| D6 | Relatório de consumo no console | **OK** | cartão "Dados pela Starlink"; `web/src/lib/dados.test.ts` (5) |
| D7 | Números simulados marcados | **OK** | `docs/ROVER_RUNTIME.md` §27: ~54 GB/dia gerados → ~2 GB/dia com o teto (SIMULADO) |
| D8 | Orçamento como restrição do planejamento | **OK** | `test_planejamento.py::test_robotico_orcamento_de_dados_da_starlink` (resta 900 000 B de 1 MB com 10% de reserva; tarefas além disso ficam de fora, com motivo) |
| | **Orçamento no todo** | **OK** (simulado) | consumo real da Starlink não medido em hardware |

### 8.1 — Copiloto fitossanitário neuro-simbólico (`docs/CEREBRO.md`)

| # | Critério | Estado | Evidência |
| --- | --- | --- | --- |
| 8.1a | Repositório de conhecimento versionado e rastreável | **OK** | `test_cerebro_conhecimento.py` (22): versão imutável, hash, trechos com citação conferível |
| 8.1b | Regulatório vencido/não verificado bloqueia uso operacional | **OK** | `test_cerebro_conhecimento.py`, `test_cerebro_parecer.py`; e a situação **de hoje** na leitura do parecer (`test_cerebro_hostil.py::test_fonte_que_venceu_depois_do_parecer_aparece_na_leitura`) |
| 8.1c | RAG local, sem chamada externa | **OK** | BM25 em memória; provedor desligado por padrão (`test_provedor_desligado_por_padrao_nao_chama_nada`) |
| 8.1d | Modelo de linguagem/visão com citação validada | **PARCIAL** | interface e validador prontos, testados com dublê (inclusive injeção pelo documento — `test_cerebro_hostil.py`); nenhum provedor real (decisão do Pedro) |
| 8.1e | Fontes oficiais (bulas, MAPA, Embrapa, escalas) | **NÃO** | repositório nasce vazio de propósito: nada inventado; ingestão pronta (`python -m valtexa.cerebro.ingestao`) |
| 8.1f | Histórico do talhão, gêmeo, visuais, clima e regras no dossiê | **OK** | `test_cerebro_parecer.py` (com a IA dublê: "a verificar com o modelo real") |
| | **8.1 no todo** | **PARCIAL** | falta conteúdo real e provedor — decisões do Pedro |

### 8.2 — Parecer

| # | Critério | Estado | Evidência |
| --- | --- | --- | --- |
| 8.2a | Hipótese principal e alternativas, qualidade da evidência, incerteza e horizonte do gêmeo | **OK** | `test_cerebro_parecer.py` (24) |
| 8.2b | O que verificar antes de agir (diagnóstico, cultura, registro, alvo, dose, restrições, carência, ambiente) — nunca "ok" | **OK** | idem; `test_toda_afirmacao_e_toda_verificacao_tem_citacao` |
| 8.2c | Não transforma probabilidade em certeza; não recomenda dose | **OK** | validador (certeza, recomendação operacional); texto livre que parece instrução é omitido (`test_cerebro_hostil.py`, 9) |
| | **8.2 no todo** | **OK** | |

### 8.3 — Planejamento (`docs/PLANEJAMENTO.md`)

| # | Critério | Estado | Evidência |
| --- | --- | --- | --- |
| 8.3a | Fila de casos para revisão (risco × incerteza × impacto) | **OK** | `test_planejamento.py::test_fila_risco_x_incerteza_x_impacto` |
| 8.3b | Comparar o histórico de sintomas (lesões persistentes/novas) | **OK** | `test_historico_regioes_e_alternativas` |
| 8.3c | Regiões prioritárias | **OK** | idem (do gêmeo) |
| 8.3d | Alternativas de manejo | **OK** | idem (5 alternativas, sem produto nem dose) |
| 8.3e | Rotação por modo de ação só com produto cadastrado com fonte e registro vigente | **OK** | `test_rotacao_so_com_produto_com_fonte_vigente` (vencida, não verificada, fictícia, sem fonte, sem modo: fora, com motivo) |
| 8.3f | Rotas de menor custo, bateria, distribuição entre dispositivos | **OK** | `test_robotico_reaproveita_o_enxame_e_registra_premissas` |
| 8.3g | Inclinação e obstáculos (módulos de terreno lidos, não editados) | **OK** | `test_robotico_inclinacao_*`, `test_robotico_obstaculo_*`; contrato `ia/tests/test_contrato_planejamento.py` (2) |
| 8.3h | Orçamento de dados da Starlink como restrição | **OK** | `test_robotico_orcamento_de_dados_da_starlink` |
| 8.3i | Insumos: demanda pelo histórico, cenários com intervalo, reposição; sem histórico, não estima | **OK** | `test_insumos_*` (bootstrap determinístico, p10 ≤ p50 ≤ p90) |
| 8.3j | Premissas registradas e revisão humana | **OK** | origem de cada premissa; revisão por tipo com hash (`test_revisao_por_tipo_e_hash`) |
| 8.3k | API + tela no console | **OK** | 7 rotas; `/talhoes/:id/planejamento`, `/planejamento/:id`, `/planejamento/insumos`; `planejamento.test.ts` (5). **Não vista no navegador** |
| | **8.3 no todo** | **OK** | com a IA dublê |

### 8.4 — Princípio de Ouro (`docs/SEGURANCA.md` §6)

| # | Critério | Estado | Evidência |
| --- | --- | --- | --- |
| 8.4a | Nenhuma rota/serviço do agente escreve estado autorizado | **OK** | `test_principio_de_ouro.py`: varredura AST + todas as 24 rotas do copiloto, planejamento, enxame e federado com a foto do banco; fio de disparo para rota nova; mutação conferida |
| 8.4b | Autorização só por humano com papel de agrônomo, reconferida | **OK** | `test_so_o_papel_de_agronomo_aprova_aplicacao`, `test_aprovar_exige_usuario_humano_agronomo`, `test_safety_engine_reconfere_o_papel_do_aprovador` |
| 8.4c | Safety Engine determinístico como único caminho de liberação | **OK** | `test_autorizado_so_por_authorize_depois_do_safety_engine`, `test_fio_de_disparo_dos_campos_de_liberacao`, `test_safety_engine_e_deterministico`, `test_liberacao_bloqueada_*`, `test_missao_de_inspecao_*` |
| | **8.4 no todo** | **OK** | |

## Outros testes que sustentam a tabela

| Assunto | Teste |
| --- | --- |
| Estresse do Rover (rede intermitente, 503/429, reinícios, câmera fora, disco cheio) | `rover/tests/test_estresse.py`; números grandes em `docs/ESTRESSE.md` |
| 6 Rovers de 2 clientes em paralelo contra a API (uploads simultâneos, isolamento) | `saas/tests/test_estresse_frota.py` |
| OTA (assinatura inválida, atualização interrompida, rollback) | `rover/tests/test_ota.py`, `saas/tests/test_ota.py` |
| dNATY (benchmark original × otimizado, critério de aceite) | `ia/tests/test_dnaty_pipeline.py`, `saas/tests/test_dnaty_registry.py` |
| Isolamento entre clientes em todas as rotas (gerado do OpenAPI) | `saas/tests/test_isolamento_openapi.py` |
| **Parte 9** — object storage S3 por HTTP (`moto` servidor + `boto3`): multipart, *staging* de chunks no bucket com troca de réplica no meio do upload, coleta em pedaços, lifecycle por categoria, URL assinada (válida / adulterada / vencida / outro cliente) | `saas/tests/test_producao_s3.py` |
| **Parte 9** — limite de taxa e travas entre réplicas (memória, `fakeredis`, `redis-server` real) | `saas/tests/test_coordenacao.py` |
| **Parte 9** — segredos de produção (vazio, padrão, curto, de exemplo, repetidos; leitura por arquivo; API e worker recusam subir) | `saas/tests/test_segredos.py` |
| **Parte 9** — seção 43: upload (tipo pelos bytes, tamanho, caminho), corpo grande antes da autenticação, arquivo servido inerte, replay/assinatura/relógio/credencial revogada do Rover, sessão vencida no servidor | `saas/tests/test_seguranca_parte9.py`; mapa completo em `docs/SEGURANCA.md` § 3 |
| **Parte 9** — índices das migrações = índices dos modelos (Postgres e SQLite) | `saas/tests/test_migrations.py` |
| **Parte 9** — ensaio de produção sem Docker: `ENVIRONMENT=production`, segredos por arquivo, Postgres 16, Redis com senha, S3, **2 réplicas** + 2 workers: 10 de 10 passos (upload alternando réplicas, URL assinada, limite somado, 413) | roteiro em `docs/PROGRESSO.md` (Parte 9) |
