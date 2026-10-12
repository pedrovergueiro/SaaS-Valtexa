# Critérios de aceite (brief, seção 58) — estado em 10/10/2026

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
