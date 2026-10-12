# Progresso — branch `claude/plataforma`

> **Rodada 3** (branch `claude/base-fazenda`): a **Parte 13** (enlace à prova de falha:
> verificação hostil, malha com repetidoras, levantamento de cobertura, missão ciente do
> enlace, ensaio de 24 h, FASE ENLACE), a Parte 12 (comunicação da fazenda: base, protocolo
> de enlace, emulador e caos — `docs/COMUNICACAO_FAZENDA.md`) e a Parte 11 (testes
> automáticos no Rover, ensaios, portões e aba Validação) estão logo abaixo; a Parte 10 não
> chegou à branch.

> **Comece por aqui.** A **Parte 9** (05/10/2026) fechou a segunda rodada: **produção em
> código** — object storage S3 (com *staging* de chunks compartilhado entre réplicas),
> Redis (limite de taxa e travas), segredos recusados em produção quando fracos ou
> repetidos, migração 0025 (índices que faltavam no banco migrado), `deploy/producao/`
> (compose com API + console, worker, IA, Postgres, Redis, MinIO, Prometheus e Caddy),
> **hardening** da seção 43 e a **verificação final da rodada** (31 critérios de novo,
> suíte completa no Postgres). Docs novos: `docs/DEPLOY.md` e `docs/SEGURANCA.md`.
> As Partes 6 (notificações e chamados), 7 (observabilidade e alertas) e 8 (telas, mapa e
> painel) estão abaixo, cada uma com os números reais. A **lista de todos os arquivos
> alterados nas Partes 6–9** (para integrar localmente) está em
> [§ Arquivos das Partes 6–9](#arquivos-das-partes-69). O que falta para o piloto está no
> `README.md` da raiz. Leia antes `docs/CONTEXTO_NUVEM.md`.

## Rodada 3 — Parte 16 (10/10/2026, local) — do endereço do cliente à rota do rover

O cadastro do talhão, numa tela só (`/talhoes/{id}/contorno`, que a equipe abre pela sessão
de suporte "entrar como cliente"):

1. **Achar a lavoura:** endereço, cidade, nome da fazenda, coordenada, graus-minutos-segundos
   ou link do Google Maps. Coordenada e link são lidos no console, sem rede
   (`web/src/lib/localizar.ts`). Endereço vai a `GET /v1/mapa/localizar`
   (`valtexa/services/localizar.py`):
   * Google (Geocoding API), quando as duas chaves estão ligadas;
   * se não, OpenStreetMap (Nominatim: 1 consulta/s, identificação, cache de 10 min).
   * Google que recusa cai no OpenStreetMap e avisa.
2. **Satélite:** o do Google (Map Tiles API, com os créditos e o logotipo que a política
   exige) quando ligado; se não, o da Esri (`GET /v1/mapa/satelite`).
3. **Desenhar** por cima, sem precisão (clique, colar, ou o "Novo talhão", que agora também
   tem a busca e, para a equipe, segue direto para o editor com `?ajustar=1`).
4. **"Ajustar com IA e calcular rota"**, num botão:
   * **encaixe nos carreadores** (VALTEXA-B, `app/encaixe_carreador.py` + rota
     `POST /encaixe-carreador`, arquivos novos; o WIP de terreno não foi tocado). Cada
     lado do desenho encosta na estrada de terra (crista de solo claro e avermelhado) ou na
     borda em degrau mais nítida da faixa; os cantos saem da interseção dos lados; lado sem
     nada nítido fica como desenhado. O SaaS chama esta rota e cai no encaixe radial antigo
     se a IA não a tiver (404);
   * **ruas pelo espectro do miolo do talhão**: direção e espaçamento das linhas, mesmo a
     ~1 m/px, onde o detector por frequência não resolve;
   * **rota** com o desenho ainda não salvo (`PlanRequest.boundary/terrain`): passadas no
     sentido das ruas, desvio dos bloqueios lidos, tempo, energia, cargas e postes.
5. **Conferir e salvar.**

**Achados e correções:**
* O encaixe radial, num cafezal real (Três Pontas, Esri a 1,1 m/px), **vazava para o
  talhão vizinho** (+171% de área) e virava círculo com tolerância menor: café dos dois
  lados do carreador tem a mesma cor. O encaixe nos carreadores acertou os 4 lados.
* As rotas de IA de terreno e de planejamento **recusavam a sessão de suporte**, que é
  justamente como a equipe entra no cliente para desenhar: o botão "Ajustar com IA" do
  editor nunca funcionava para ela. Agora valem dentro da sessão
  (`deps.require_platform_ou_suporte`): o papel de plataforma é conferido, a sessão vale só
  no cliente dela e cada chamada vai para a auditoria do cliente. São consultas, por isso
  valem até no modo leitura; salvar continua exigindo o assistido.
* A busca e o satélite aceitam qualquer pessoa logada, inclusive em sessão de suporte
  (`deps.current_user_ou_suporte`), e não tocam dado de cliente.
* "Novo talhão" abria em Milho; agora abre em Café.

**Números:** SaaS completo **973 ✓, 9 skip**, `ruff` limpo; VALTEXA-B `tests/test_encaixe_carreador.py` **7 ✓** (+ os 54 de terreno
existentes, intactos); SaaS `test_localizar.py` (7), `test_boundary_api.py` (+2),
`test_planner.py` (+1), isolamento ok; console **144 ✓** (`localizar.test.ts`, 7),
`tsc`/`build` ok. Navegador (Edge): entrar como cliente → "Três Pontas MG" → link do
Google Maps → desenho torto → encaixe nos 4 carreadores, ruas a 3,9 m e 109°, rota de 166
passadas, 8,5 ha, ~10 h, 1 poste; nenhum erro de página.

**Não feito / depende de fora:**
* A chave do Google enviada ainda **não funciona**: o projeto está sem faturamento e sem a
  Map Tiles API. Com isso ligado, a busca e o satélite passam ao Google sem mudar código.
* Obstáculos e área operável continuam exigindo ortomosaico de 3 a 10 cm/px (a leitura de
  terreno existente diz isso); no satélite só o contorno e as ruas.
* Imagem licenciada para a IA em produção (README, itens 14–16).

## Rodada 3 — Parte 15 (10/10/2026, local) — pilotagem, vídeo, chaves e mapa pela plataforma

### O que foi feito

| Bloco | O quê |
|---|---|
| Estação de pilotagem | Vídeo ao vivo, controle de videogame, teclado e joystick da tela no mesmo lugar, com HUD (ROVER_RUNTIME §21); homem-morto em LB/RB e B = PARAR |
| Vídeo ao vivo | `services/video_ao_vivo.py` (só o último quadro, 15 s); `runtime/video.py` com qualidade adaptativa (240–1280 px); prévia da OAK-D; slot "só o último vale" em P3 pela base |
| Modelo pronto no boot | `precarrega_modelo`; `model_missing` só com missão sem modelo; perfil e cabeça no "já carregado" (ROVER_RUNTIME §22) |
| Chaves do rádio pela plataforma | `PUT /v1/device/enlace/chave` (robô) e `GET /v1/device/base/pares` (base, conferindo cada assinatura); migração `0030` |
| Mapa de cobertura pela plataforma | `valtexa-base levantamento --publicar-talhao`; `PUT /v1/device/base/cobertura/{field_id}`; guardado no talhão (migração `0031`); vai assinado em toda missão; o Rover troca o mapa da travessia; mapa no console em **Bases da fazenda** (COMUNICACAO_FAZENDA §17) |
| Contrato entre os sistemas | `tests/test_contrato_sistemas.py`: rotas, cabeçalhos, prioridade no enlace, assinatura da chave e o mapa da análise da base até o Rover |
| ACEITE | R7, R8 e R9 **OK** |

### Números (10/10/2026, Windows, Python 3.14)

| Suíte | Resultado |
|---|---|
| SaaS `pytest` | **972 coletados: 963 ✓, 9 skip** (Postgres, Redis e S3 reais); `ruff` limpo |
| Rover `pytest` | **269 ✓, 3 skip**; `ruff` limpo |
| Base `pytest` | **35 ✓, 1 skip** (watchdog do systemd, só Linux); `ruff` limpo |
| Console `vitest` / `tsc` / `build` | **137 ✓** / limpo / ok |

### O que falta

* `politica_enlace` escolhida na criação da missão.
* Custódia longa.
* O que é de campo (COMUNICACAO_FAZENDA §18, README).

## Rodada 3 — Parte 14 (10/10/2026, feita localmente) — base na plataforma e pesos reais

A rotina da nuvem foi cancelada antes de rodar. A P14 foi feita no PC do Pedro, sobre a
rodada 3 integrada da branch `claude/base-fazenda` (`076918e`), com a junção em três vias
em `scratchpad/integra_nuvem3.py`:
* 93 arquivos novos e 26 atualizados;
* 1 conflito resolvido à mão: `simulator/__main__.py`, que agora tem o `--fase0` da nuvem e
  o modo de pesos reais local;
* pacote novo `VALTEXA-BASE` (pasta irmã), também em `requirements-dev`.

### O que foi feito

| Bloco | O quê |
|---|---|
| Integração no Windows | Testes que só valiam no Linux: o `chmod 0600` passa a ser conferido só fora do Windows, o watchdog do systemd é pulado sem `AF_UNIX`, e o kill -9 virou `proc.kill()`. Corrida no teste do console da base: o Rover via a base antes de a base ver o Rover |
| Base na plataforma | Modelo `FARM_BASE_V1` (`gateway`); `valtexa-base provisionar`; retrato assinado (`valtexa_base/plataforma.py`) em `health.base`, padronizado (`saude_rover._base`); `services/estacao_base.py` (lista, detalhe e **caminho** do Rover); rotas `/v1/platform/bases[/{id}]`; `caminho` no painel |
| Alarmes | `base_sem_contato`, `enlace_degradado`, `fila_base`, `repetidora_bateria`; a base sai do `rover_offline` |
| Console | cartão **Caminho** no centro de comando; tela **Bases da fazenda** (`/plataforma/comando/bases`); `lib/enlace.ts` |
| OTA da base | `OtaManager` generalizado (`pacote`, `tipos`); `ota_da_base`; unidade systemd pelo `valtexa_rover.launcher` |
| Ponta a ponta com pesos reais | `python -m simulator --rover-runtime --ia URL --modelo-real X.onnx --folhas DIR`; `valtexa_rover/sim/folhas.py` (câmera de folhas reais e instalação do modelo no formato do OTA); passos extras 21b, 22b e 23b. **31/31 + 3** com o café real e o `ia/` de verdade |
| Docs | ACEITE (30 OK, 1 PARCIAL, critérios da rodada 3), README (o que falta para o piloto), COMUNICACAO_FAZENDA §16–§17, SIMULATOR |

### Números (10/10/2026, Windows, Python 3.14)

| Suíte | Resultado |
|---|---|
| SaaS `pytest` | **955 coletados: 946 ✓, 9 skip** (Postgres, Redis e S3 reais); `ruff` limpo |
| Rover `pytest` | **257 ✓**; `ruff` limpo |
| Base `pytest` | **33 ✓, 1 skip** (watchdog do systemd, só Linux); `ruff` limpo |
| Console `vitest` / `tsc` / `build` | **127 ✓** / limpo / ok |
| Ponta a ponta simulado (`tests/test_ponta_a_ponta.py`) | 31/31 |
| Ponta a ponta com **pesos reais** (café, BRACOL separado, `ia/` no WSL) | **31/31 + 21b, 22b, 23b**, duas vezes, antes e depois da integração, com os mesmos números |
| Ponta a ponta pela base (`tests/test_base_fazenda.py`) | ok, com o caminho no painel |

### Arquivos da P14 local

* **SaaS:**
  * novos: `valtexa/services/estacao_base.py`, `tests/test_estacao_base.py`,
    `tests/test_base_ota.py`, `web/src/lib/enlace.ts`, `web/src/lib/enlace.test.ts`,
    `web/src/platform/pages/Bases.tsx`;
  * alterados: `valtexa/services/hal.py`, `saude_rover.py`, `comando_rover.py`,
    `alertas.py`; `valtexa/api/routers/platform_rover.py`;
    `simulator/__main__.py`, `ponta_a_ponta.py`; `tests/test_base_fazenda.py`;
    `requirements-dev.txt`; `web/src/platform/api.ts`, `pages/CommandCenter.tsx`,
    `router.tsx`;
  * docs: `docs/SIMULATOR.md`, `docs/plataforma/ACEITE.md`, `README.md`,
    `COMUNICACAO_FAZENDA.md`, `PROGRESSO.md`.
* **Rover:**
  * novos: `valtexa_rover/sim/folhas.py`, `tests/test_sim_folhas.py`;
  * alterados: `valtexa_rover/runtime/ota.py`, `tests/test_enlace.py`.
* **Base:**
  * novos: `valtexa_base/plataforma.py`, `tests/test_plataforma.py`;
  * alterados: `servico.py`, `cli.py`, `deploy/valtexa-base.service`,
    `deploy/base.json.exemplo`, `deploy/instalar.sh`, `tests/test_base.py`,
    `tests/test_base_processo.py`.

### O que falta

* ~~Cadastro das chaves de enlace e do mapa de cobertura pela plataforma.~~ Feito na P15.
* `politica_enlace` na criação da missão.
* Custódia longa.
* O que é de campo (COMUNICACAO_FAZENDA §17, README).

## Rodada 3 — Parte 13 (09/10/2026, ~20h40–01h UTC) — enlace à prova de falha

**Branch:** `claude/base-fazenda` (sobre `9d8e5fd`, a P12 completa; ela não estava rodando).
Projeto e números: [`docs/COMUNICACAO_FAZENDA.md`](COMUNICACAO_FAZENDA.md) §6, §10–§16;
verificação: [`docs/VERIFICACAO.md`](VERIFICACAO.md) ("Parte 12"); validação:
[`docs/VALIDACAO_ROVER.md`](VALIDACAO_ROVER.md) §6; Runtime:
[`docs/ROVER_RUNTIME.md`](ROVER_RUNTIME.md) §20.

### O que foi feito

| Bloco | O quê |
|---|---|
| 1. Verificação hostil da P12 | **8 defeitos corrigidos com teste**: a base conferia a validade com a **hora do Rover** (Rover atrasado = comunicação morta); passo do relógio esticava validade na fila (agora "parede estável"); **disco cheio** derrubava o laço e segurava o PARAR (P0/P1 agora seguem da memória, P2–P4 esperam sem perder); memória sem teto (avisos por origem) e `entrada` sem limpeza; slot velho não confirmado; teleop retido valia com o relógio do Rover atrasado (**piso assinado da hora da plataforma**); **base podia fingir "200 aceito"** e o Rover apagaria o que não chegou (**recibo assinado pela plataforma**, `X-Valtexa-Recibo`). Resistiram (com teste): replay entre sessões, nonce depois de reiniciar, deduplicação depois de reiniciar, P4 matando P1 de fome (só o sub-GHz: p99 430 ms) |
| 2. Malha com repetidoras | `enlace/malha.py`: vários saltos, **rota pela qualidade medida** (RTT, perda, banda; reverso envenenado; histerese), **troca sozinha** em ~1 s quando um nó morre, guarda-e-encaminha, **cópia fim a fim até a confirmação** (HMAC das pontas: repetidora não forja "chegou"), P0/P1 por duas rotas, laço cortado; modo **`valtexa-base repetidora`** (bateria fraca anuncia custo maior; `estado.json`; unidade systemd; `instalar.sh --repetidora`); base e Rover com `"malha"` |
| 3. Levantamento de cobertura | registro no Rover e na base (RTT, perda, vazão, RSSI/SNR + posição RTK); **`valtexa-base levantamento`**: grade por enlace, zonas mortas, alcance demonstrado, **sugestão gulosa de repetidora explicada**, `cobertura.json`, CSV, MD, SVG — sem os arquivos de terreno da IA |
| 4. Missão ciente do enlace | `enlace/travessia.py`: zona morta à frente na rota assinada → antecipa a sync, avisa a base (o PARAR do console passa a valer a travessia), registra `travessias.jsonl`, sincroniza na volta; **`PoliticaDaMissao`** (`politica_enlace` ou o `offline_policy` que a plataforma já assina: pulverização não atravessa às cegas, fecha a aplicação, pede o retorno ao último ponto com enlace) |
| 5. Ensaio de 24 h | `enlace/ensaio24h.py` (perfil SIMULADO de cafezal em morro, `enlace/cafezal.py`): rádio oscilando ao longo da rua, Starlink caindo à noite e na chuva, base sem energia, repetidora morrendo. Achados → **enlace calado há 1 s desvia o lote** e **enlace que oscila só volta depois de estável** (253 → 7 trocas em 40 min); vizinho calado custa caro na malha (troca de rota 3,25 s → 1,05 s) |
| 6. FASE ENLACE na validação | 7 ensaios no Rover (`ensaios/enlace.py`, comando `ensaio`): `enlace_rssi`, `enlace_latencia`, `enlace_troca`, `enlace_starlink`, `enlace_energia_base`, `enlace_travessia`, `relogio`; base atende eco/relógio e, só com `ensaios_remotos`, silencia rádio / tira a Starlink / reinicia; catálogo da plataforma (fase 6, mostrada como **ENLACE**, veredito refeito no servidor, só modo manual vale no portão); **chrony com GNSS** (`rover/deploy/chrony/`, `base/deploy/chrony-base.conf`, `enlace/relogio.py`) |
| 7. Docs | COMUNICACAO_FAZENDA (números simulados, **procedimento de campo**: levantamento antes de instalar, mastro, repetidoras, validação, rotina de manutenção), VALIDACAO_ROVER §6, ROVER_RUNTIME §20, DEVICE_PROTOCOL (recibo), VERIFICACAO |

### Números reais (esta execução)

| Suíte | Antes (P12) | Depois |
|---|---|---|
| Rover `pytest` | 214 ✓, 3 skip | **251 ✓, 3 skip** (+37: `test_enlace_verificacao.py` 14, `test_malha.py` 15, `test_travessia.py` 6, `test_ensaio24h.py` 1, `test_relogio.py` 2; `test_ensaios.py` atualizado) · `ruff` limpo |
| Base `pytest` | 13 ✓ | **32 ✓** (+19: `test_repetidora.py` 4, `test_levantamento.py` 6, `test_ensaios_enlace.py` 8, `test_base.py` +1 base adulterada) · `ruff` limpo |
| SaaS `pytest` | 933 ✓, 3 skip | **945 ✓, 3 skip** (13 min 44 s; +12: `test_recibo_dispositivo.py` 2, `test_ensaios_enlace_plataforma.py` 10; `test_base_fazenda.py` confere os recibos) · `ruff` limpo |
| Console `vitest` / `build` | 122 / ok | **123 ✓** / ok (`rotuloFase`) |
| IA `pytest` (não alterada) | 757 ✓, 1 skip | **757 ✓, 1 skip** (Python 3.12) · `ruff`: só os 5 erros conhecidos dos arquivos intocáveis |

**Ensaio de 24 h SIMULADO** (`python -m valtexa_rover.enlace.ensaio24h`, 14 min de máquina;
relatório em `docs/ensaios/enlace-24h-simulado.json`):

* **zero perda de P0 a P3**: 59.711 registros P2/P3, **59.711 aceitos uma vez** (28
  repetidos absorvidos pela deduplicação), 0 pendentes; P4 720/720; P0/P1 não entregues
  1.380, **todos sem caminho** (Rover na sombra com a repetidora apagada), 0 com caminho bom;
* disponibilidade no prazo: P0 98,5 %, P1 97,0 %, P2 98,4 %, P3 97,4 % (o que falta é a
  repetidora morta com o Rover na sombra e a base sem energia; **com caminho, P1 no prazo
  em 100 %**);
* **latência de P1: p50 50 ms, p95 150 ms, p99 300 ms** (resolução 50 ms), máx. 3,65 s;
* **troca de rota 1,05 s** (do instante físico da queda); **troca de enlace p50 0,9 s, máx.
  1,05 s**; nenhuma interrupção de P1 nas trocas (P0/P1 por todos os rádios e duas rotas).

Outras medidas (emulador): 3 saltos sem perda nos dois sentidos; repetidora morre no meio
da missão → rota troca em < 5 s (teste), 0 perdido, 0 repetido; RPC P1 pelo rádio no UDP
real com 10 % de perda: p99 < 600 ms (`enlace_latencia`); troca de enlace por software no UDP
real < 5 s com P1 sem buraco > 2 s; Starlink fora 6 s → 0 sonda perdida.

### Achados desta parte (corrigidos)

Os 8 da verificação (acima e em `VERIFICACAO.md`), mais: perfis do emulador contaminados
entre testes (lista de quedas compartilhada); lote pulando de enlace com o rádio que oscila;
troca de rota esperando os 3 s da morte; laço com P0/P1 duplicados a cada salto (agora só
na origem); o **piso da hora** usava o monotônico do Runtime — na bancada simulada ele anda
depressa e o simulador da FASE 0 da plataforma quebrou (2 testes; pego pela suíte
completa e corrigido: o piso usa o tempo que passou de verdade).

### O que é simulado / não testado em hardware

Todos os rádios e repetidoras (emulador e UDP no `localhost`); o perfil de cafezal (modelo
de brinquedo: espaço livre + copa periódica + sombra do morro — **não é medida**); RSSI/SNR
(adaptador só contra falsos); PPS/chrony (saídas gravadas do `chronyc` 4.x); leitura da
bateria da repetidora; o ensaio de 24 h inteiro. Nenhum número deste bloco é promessa de
campo: servem para comparar versões e dizer o que o campo tem de bater.

### O que falta para a P14

1. **Campo** (Pedro): levantamento de verdade (§15 do COMUNICACAO_FAZENDA) antes de
   cimentar o mastro; escolher os rádios (que exponham RSSI/SNR); rodar a FASE ENLACE em
   modo manual; ajustar `banda_bps`, `estabilidade_s` e o custo da malha com a oscilação
   real da copa.
2. A base e as repetidoras como dispositivos da plataforma (identidade, cadastro de chaves
   e de repetidoras pela plataforma, estado e alarmes no console da nuvem — bateria fraca,
   enlace degradado, travessias).
3. `politica_enlace` e o `cobertura.json` na criação da missão (o Rover já lê os dois).
4. Custódia longa atestada pela base; frota com vários Rovers e mapa compartilhado.
5. A navegação/MCU obedecer `fechar_aplicacao` e `retorno` do `enlace.json`.
6. Compatibilidade: o Rover desta parte **exige** a plataforma desta parte quando fala
   pela base (recibo); `exige_recibo: false` só na transição.

### Arquivos alterados (para integrar localmente)

* rover (novos): `valtexa_rover/enlace/` `malha.py`, `bancada_malha.py`, `levantamento.py`,
  `travessia.py`, `cafezal.py`, `ensaio24h.py`, `relogio.py`; `valtexa_rover/ensaios/enlace.py`;
  `deploy/chrony/valtexa-gnss.conf`; testes `test_enlace_verificacao.py`, `test_malha.py`,
  `test_travessia.py`, `test_ensaio24h.py`, `test_relogio.py`. Alterados: `enlace/no.py`,
  `fila.py`, `rpc.py`, `politica.py`, `saude.py`, `bancada.py`, `transporte.py`;
  `hal/rede_base.py`; `runtime/mission.py`, `core.py`, `comandos.py`; `ensaios/__init__.py`;
  `cli.py`; `tests/test_ensaios.py`.
* base (novos): `valtexa_base/repetidora.py`, `levantamento.py`; `deploy/repetidora.json.exemplo`,
  `valtexa-repetidora.service`, `chrony-base.conf`; testes `test_repetidora.py`,
  `test_levantamento.py`, `test_ensaios_enlace.py`. Alterados: `servico.py`, `nuvem.py`,
  `console.py`, `cli.py`, `deploy/instalar.sh`, `tests/conftest.py`, `tests/test_base.py`.
* saas: `valtexa/api/middleware.py` (`ReciboDoDispositivo`), `valtexa/main.py`,
  `valtexa/services/ensaios.py` (FASE ENLACE), `docs/DEVICE_PROTOCOL.md`; testes
  `test_recibo_dispositivo.py`, `test_ensaios_enlace_plataforma.py` (novos),
  `test_base_fazenda.py`, `test_ensaios_plataforma.py`. **Nenhuma migração** (a fase 6 usa
  as colunas que já existem).
* console: `src/lib/validacao.ts`, `src/lib/validacao.test.ts`,
  `src/platform/pages/Validation.tsx`.
* docs: `COMUNICACAO_FAZENDA.md`, `VALIDACAO_ROVER.md`, `ROVER_RUNTIME.md`, `VERIFICACAO.md`,
  `PROGRESSO.md`, `docs/ensaios/enlace-24h-simulado.json` (novo).

Não tocados: `rover/valtexa_rover/edge_ai/`, `ia/` (inclusive `plant_fusion.py`,
`fit_edge.py`, `fit_fusion.py` e os arquivos de terreno), limiares dos perfis, `main`,
`claude/plataforma`. Nenhum segredo no código (chaves de enlace nascem no nó; o token do
console e a comunidade SNMP ficam em arquivo).

## Rodada 3 — Parte 12 (09/10/2026) — comunicação da fazenda: base e protocolo

**Branch:** `claude/base-fazenda`. Projeto e números: [`docs/COMUNICACAO_FAZENDA.md`](COMUNICACAO_FAZENDA.md);
no Runtime: [`docs/ROVER_RUNTIME.md` §19](ROVER_RUNTIME.md).

### O que foi feito

| Bloco | O quê |
|---|---|
| Projeto | `docs/COMUNICACAO_FAZENDA.md`: topologia Nuvem ⇄ Starlink ⇄ base ⇄ rádios ⇄ Rover (repetidoras), volumes por classe com a conta (P0–P2 < 50 kbit/s, P3 ≈ 0,3 Mbit/s, vídeo 1–3, originais 6–12, coleta ≈ 120 Mbit/s ≈ 432 GB/dia), upload da Starlink **a medir**, rádio para tempo real e volume pelo poste de recarga, redundância (sub-GHz + 5/2,4 GHz em malha, 4G, E-stop em rádio próprio no MCU), equipamento por função com preço **a cotar** |
| Protocolo | `rover/valtexa_rover/enlace/`: quadros com CRC32, sequência, ACK seletivo, retransmissão com recuo, deduplicação; fragmentação e transferência retomável em pedaços com SHA-256; P0–P4 com agendador por orçamento de banda (P0/P1 estritos, P4 só com a sobra); filas SQLite WAL nas duas pontas com limites e disco cheio (P0–P3 nunca caem por P4); X25519 + ChaCha20-Poly1305 por salto (chave do enlace assinada pela identidade Ed25519; nonce = contador, nunca reutilizado; anti-replay de 1024); teleop em *slot* "só o último vale"; validade em toda mensagem; vários enlaces ao mesmo tempo (saúde RTT/perda/vazão/RSSI, P0/P1 redundantes, lote pelo melhor com histerese, batimento 2/s) |
| Rover | `hal/rede_base.py`: `RedeViaBase` é a HAL `Network` "via base" (`hardware.json` `rede.modo = "base"`), **sem mudar o protocolo com a plataforma**; política de perda de enlace → `/run/valtexa/enlace.json` (teleop zera; missão só continua se `politica_enlace.continuar_sem_enlace`; pausa e volta sozinha); PARAR vindo da base; `valtexa-rover enlace-chave`; serviço liga a política (`cli.py`) |
| Base | pacote novo `base/` (`valtexa_base`): proxy das rotas `/v1/device/**` (assinadas pelo Rover; só esse prefixo passa, sem `..`), moldagem do uplink (trabalhador reservado a P0/P1, P4 com a sobra e teto opcional), custódia curta dos idempotentes quando a Starlink cai (dentro da janela da assinatura), cache de missões assinadas (armar no console e iniciar sem internet), console e API na LAN (estado, **PARAR para todos**, missões, métricas Prometheus), RSSI/SNR por SNMP/HTTP (**não testado em hardware**), watchdog (`sd_notify`) e `deploy/` (`instalar.sh`, unidade systemd, exemplos) |
| Emulador | `enlace/emulador.py`: banda, atraso, variação, perda, rajada (Gilbert-Elliott), reordenação, duplicação, corrupção, quedas programadas e intermitente — em processo (relógio virtual) e relé UDP (`python -m valtexa_rover.enlace.emulador`) |
| Caos e integração | ver "Números" |

### Números reais (esta execução)

| Suíte | Antes | Depois |
|---|---|---|
| Rover `pytest` | 184 ✓, 3 skip | **214 ✓**, 3 skip (+30: `test_enlace.py` 13, `test_enlace_caos.py` 8, `test_enlace_rover.py` 9) |
| Rover `ruff` | limpo | limpo |
| Base `pytest` (novo) | — | **13 ✓** (`test_base.py` 12, `test_base_processo.py` 1 com `kill -9`) |
| Console da base no Chromium (desktop e 390 px) | — | sem erro de JavaScript, sem rolagem horizontal; PARAR e armar respondem |
| Base `ruff` | — | limpo |
| SaaS `pytest` | 932 ✓, 3 skip | **933 ✓, 3 skip** (15 min 43 s; +1: `test_base_fazenda.py`, uvicorn — rodado de novo sozinho depois da última correção do `is_online`: ✓) |
| SaaS `ruff` | limpo | limpo |
| Console `vitest` / `build` (não alterado) | 122 / ok | **122 ✓** / ok |
| IA `pytest` (não alterada) | 757 ✓, 1 skip | **757 ✓, 1 skip** (Python 3.12); `ruff`: só os 5 erros conhecidos dos arquivos intocáveis |

Medidas (rádio **EMULADO**, para comparar versões do protocolo, não promessa de campo):

* P1 a cada 250 ms sob carga contínua de P4, **30 % de perda nos dois enlaces**
  (250 kbit/s + 20 Mbit/s), 120 s: **p50 20 ms, p95 250 ms, p99 380 ms, máx. 620 ms,
  0 perdido** (473 comandos); P3 no mesmo cenário p50 170 ms, p95 750 ms, p99 2,3 s,
  0 perdido.
* RPC P1 completo pela base (UDP, 2 relés com 20 % de perda): p50 ≈ 29 ms, p95 ≈ 0,5 s.
* `kill -9` na base no meio de 150 registros + 150 pedaços: volta em 2,0 s e 3,1 s
  (reinício do Rover: 1,4 s); nada perdido.
* Ponta a ponta com a plataforma no uvicorn: 299 pedidos pela base, Starlink e depois os
  dois rádios caindo no meio da missão; 1 pedido em custódia (o que estava no ar), entregue;
  30 resultados, 3 eventos de imagem e 3 originais em pedaços, uma vez cada; um
  `ROVER_OFFLINE` por queda.

### Achados dos testes (corrigidos)

* recuo exponencial dobrando sem limite deixava o último pedaço de um lote esperando
  segundos com perda aleatória → recuo 1,5× até 4× o RTO;
* o balde a 100 % da banda enchia o buffer do rádio e o P1 esperava atrás do P4 → 90 %;
* com 20 % de perda, o aperto de mão perdido esperava 2 s para repetir → 0,5 s, crescendo;
* o primeiro enlace a ligar ficava "melhor" mesmo com outro 8× mais rápido → troca
  imediata quando a diferença passa de 4×;
* a fila tirava P4 para caber P2/P3 e depois recusava assim mesmo → só tira se resolver;
* `vistos` (deduplicação) não era podado → poda a cada 10 min (retém 7 dias);
* o filtro "só `/v1/device`" da base deixaria passar `..` → recusado;
* com a base sem internet o rádio seguia vivo, `is_online()` dizia sim e cada passo do sync
  gerava um par `ROVER_ONLINE`/`ROVER_OFFLINE` → `is_online()` = rádio vivo **e** base com
  internet (pelo batimento).

### O que é simulado / não testado em hardware

Todos os rádios (só o emulador e UDP no `localhost`); leitura de RSSI/SNR por SNMP/HTTP
(só contra falsos; OIDs e campos dependem do modelo escolhido); `SO_BINDTODEVICE`;
alcance, vazão, perda e upload da Starlink (**a medir**); o 4G alcançar a base (IPv6 da
Starlink ou relé — a definir); o rádio de emergência no MCU (protocolo do MCU ainda não
definido). A navegação ainda precisa ler `enlace.json` e `controle.json`.

### O que falta para a P13 (enlace à prova de falha)

1. **Medir em campo** cada rádio no relevo (alcance, vazão, perda por hora do dia, RSSI) e
   o upload da Starlink de dia e de madrugada; ajustar `banda_bps`, MTU, `t_morto_s`,
   tolerância da política; escolher e cotar os rádios (§5 do doc).
2. Vídeo leve de teleoperação (1–3 Mbit/s) só no enlace de alta vazão, com descarte de
   quadro velho (mesma ideia do *slot*).
3. Poste de recarga: descarga em lote pela LAN (P4 com a LAN inteira) e subida à noite.
4. 4G até a base (IPv6 ou relé na nuvem) e o enlace 4G no `hardware.json`.
5. RSSI/SNR com os OIDs reais; alarme de enlace degradado no console da base.
6. P14: a base como dispositivo da plataforma (identidade, cadastro de chaves de enlace,
   estado no console da nuvem), `politica_enlace` na criação da missão, custódia longa
   atestada pela base.

### Arquivos alterados (para integrar localmente)

* rover (novos): `valtexa_rover/enlace/` (`__init__`, `quadro`, `cripto`, `fila`, `saude`,
  `no`, `rpc`, `transferencia`, `politica`, `emulador`, `transporte`, `bancada`),
  `valtexa_rover/hal/rede_base.py`, `deploy/hardware.rover-v3.fazenda.json.exemplo`,
  testes `test_enlace.py`, `test_enlace_caos.py`, `test_enlace_rover.py`;
  alterados: `valtexa_rover/hal/rover_v3.py` (rede pelo `hardware.json`),
  `valtexa_rover/cli.py` (`enlace-chave`; o serviço liga a política).
* base (novo pacote): `base/pyproject.toml`, `README.md`, `.gitignore`,
  `valtexa_base/` (`__init__`, `__main__`, `cli`, `servico`, `nuvem`, `custodia`,
  `missoes`, `console`, `console.html`, `radios`, `watchdog`), `deploy/` (`instalar.sh`,
  `valtexa-base.service`, `base.json.exemplo`, `hardware.json.exemplo`), `tests/`
  (`conftest.py`, `test_base.py`, `test_base_processo.py`).
* saas: `tests/test_base_fazenda.py` (novo). Nenhuma migração (a plataforma não mudou).
* docs: `docs/COMUNICACAO_FAZENDA.md` (novo), `docs/ROVER_RUNTIME.md` (§2 e §19),
  `docs/PROGRESSO.md`.

Não tocados: `rover/valtexa_rover/edge_ai/`, `ia/` (inclusive `plant_fusion.py`,
`fit_edge.py`, `fit_fusion.py` e os arquivos de terreno), limiares dos perfis, `main`,
`claude/plataforma`.

## Rodada 3 — Parte 11 (08/10/2026, ~00h45–02h UTC) — testes automáticos no Rover

**Branch:** `claude/base-fazenda`. Guia: [`docs/VALIDACAO_ROVER.md`](VALIDACAO_ROVER.md).
Verificação: [`docs/VERIFICACAO.md`](VERIFICACAO.md) (seção "Parte 10").

**Achado da preparação:** a **Parte 10 não está na branch** (nem em outra): não havia
`docs/VALIDACAO_ROVER.md`, comando `ensaio`, catálogo, portões nem aba Validação; o
último commit era a base de 07/10 (`b733032`), 5 h antes. Esta parte construiu essa base
junto com os testes automáticos.

### O que foi feito

| Bloco | O quê |
|---|---|
| Verificação | suítes de base; **defeito pré-existente** corrigido: `hal/lente.py` (remapeamento NumPy zerava a última linha/coluna — `test_lente` falhava); ruff dos testes do rover limpo |
| Ensaios no Rover | `rover/valtexa_rover/ensaios/`: **calor** (vazão por janela + tegrastats: temperatura, clocks, throttling), **câmeras** (1–8 juntas: perda, salto de índice, deriva entre carimbos, idade do GNSS), **profundidade** (trena + ROI, mediana), **GNSS** (tempo até fix RTK, CEP50/CEP95/2DRMS sobre ponto conhecido, perda e retomada), **IMU** (\|g\|, inclinação, eixos coerentes pela gravidade, ruído/viés do giroscópio), **parada** (latência até `parado_em`), **homem-morto** (`teleop.json` zera após `valid_until`), **rede** (RTT, perda, vazão pelo canal assinado), **energia** (interface pronta, "aguarda protocolo do BMS/MCU"); parâmetros validados, progresso, cancelamento |
| Bancada simulada | `ensaios/simulado.py`: injeção de falha em cada peça; `RelogioDeBancada` (hora real, esperas virtuais) |
| Comando `ensaio` | `runtime/comandos.py`: `ensaio` e `ensaio_cancelar` assinados (sequência própria; repetido/forjado recusado), thread, progresso, laudo guardado sem rede; recusa com missão em curso; `config`/`reiniciar` esperam o ensaio; **`teleop.json` zera quando o ponto vence sem outro** |
| HAL | `ImuReading.gyro_dps` (opcional; Xsens com `gyro_id`), `parse_tegrastats` com clocks e todas as temperaturas, `NavegacaoPorArquivo.stop()` devolve o pedido; contrato `parado_em`/`parada_ref`/`v_ms` no `navegacao.json` |
| Plataforma | `services/ensaios.py` (catálogo com limites do portão — só apertar; **veredito recalculado no servidor** com as amostras e os parâmetros assinados; `divergente`; simulado não abre portão real; portões por fase; profundidade por distância 0,3/0,5/0,8 m), `api/routers/ensaios_api.py` (9 rotas), progresso e prazo de execução no comando, **migração 0029** (`device_command.progress`, tabela `ensaio_resultado`) |
| FASE 5 | `POST .../ensaios/validacao-agronomica`: o relatório Rover × agrônomo (`validacao_campo.relatorio`) vira resultado: sensibilidade, alarme falso, concordância com IC de Wilson (critério pelo ponto ou, com `usar_ic`, pelo limite do IC) |
| Regressão | evento `ensaio.regressao` (aprovado → reprovado no mesmo robô, mesma distância, mesmo "simulado") → aviso `plataforma_ensaio_regressao` (superadmin e Operações, e-mail por padrão) |
| Simulador | `python -m simulator --fase0` (saas: Rover Runtime real + bancada simulada, cada ensaio assinado, veredito do servidor, portão, `laudo-fase0.md`) e `python -m valtexa_rover.sim fase0` (só o robô); `valtexa-rover ensaio <nome> --param k=v` na Jetson, sem plataforma |
| Console | aba **Validação** (`/plataforma/comando/<id>/validacao`, link no centro de comando): portões, em curso (progresso, cancelar), resultados (critérios, simulado, divergência), novo ensaio (aviso de limite frouxo) |

### Números reais (esta execução)

| Suíte | Antes | Depois |
|---|---|---|
| Rover `pytest` | 154 ✓, 3 skip, **1 falha** (`test_lente`) | **184 ✓**, 3 skip (+30: `test_ensaios.py` 22, `test_ensaio_comando.py` 8) |
| Rover `ruff` | 3 erros | limpo |
| SaaS `pytest` | verde (sem falha; contagem não registrada) | **932 ✓, 3 skip** (14 min; +24 novos: `test_ensaios_plataforma.py` 22, `test_simulador_fase0.py` 2; o `rover/` instalado no venv do saas, então `test_rover_integracao`/`test_ponta_a_ponta` rodam) |
| SaaS `ruff` | limpo | limpo |
| Console `vitest` | 118 | **122** (+4 `validacao.test.ts`) |
| Console `build` | ok | ok |
| Roteiro de navegador `e2e/validacao.mjs` | — | **7/7 passos**, sem erro de JavaScript (Chromium; banco de `e2e/prepara_validacao.py`) |
| IA `pytest` (não alterada) | — | **757 ✓, 1 skip** (Python 3.12, torch do PyPI; o índice CPU do PyTorch é bloqueado pela rede); `ruff`: os 5 erros conhecidos dos arquivos intocáveis |
| `python -m simulator --fase0` (uvicorn, HTTP de verdade) | — | 12/12 passos OK; portão FASE 0 aberto aceitando simulado, real fechado; RTT p95 até a API local 11,75 ms (a única medida real) |
| Migração | — | SQLite do zero até 0029, `downgrade -1`, `upgrade head`; `alembic check` só com o ruído conhecido de `Enum` × `VARCHAR` |

### O que é simulado / não testado em hardware

Todos os ensaios rodaram só na bancada simulada. Cada um diz no laudo o que falta (tabela
em `docs/VALIDACAO_ROVER.md` §5): formato do `tegrastats` do JetPack 6; 8 OAK-D no switch e
`capture_depth()` da OAK-D (**não rodou numa OAK-D**); ZED-F9P com correção; IDs/escalas
CAN do MTi e o giroscópio (`gyro_id`); a navegação publicar `parado_em`/`parada_ref`; o
enlace da fazenda; o BMS/MCU (energia "aguarda protocolo"). A sincronia de hardware (PPS)
não é medida — só os carimbos do Runtime.

### O que falta / próximo

1. **Pedro**: conferir no MT Manager os IDs CAN do MTi-630 e configurar `gyro_id` +
   `gyro_escala_dps`; rodar `valtexa-rover ensaio imu|gnss|cameras|profundidade` na
   bancada real e comparar com o simulado.
2. **Navegação**: publicar `parado_em`, `parada_ref` e `v_ms` no `navegacao.json` (sem
   isso o ensaio `parada` reprova por falta de confirmação — é o comportamento certo).
3. **P13 (enlace)**: o ensaio `rede` é a linha de base (RTT, perda, vazão pelo canal
   assinado); perda de enlace no meio do ensaio já é coberta (laudo guardado e reenviado).
4. **Console**: os tipos de `src/api/schema.d.ts` **não** foram regenerados (o
   `openapi-typescript` local reescreve o arquivo inteiro, 14 mil linhas de diferença de
   formato); os tipos da Validação estão em `src/lib/validacao.ts`.
5. **IA**: não foi tocada (757 ✓ nesta execução).

### Arquivos alterados (para integrar localmente)

* rover: `valtexa_rover/ensaios/` (novo: `__init__`, `base`, `estatistica`, `calor`,
  `cameras`, `profundidade`, `gnss`, `imu`, `seguranca`, `rede`, `energia`, `simulado`,
  `fase0`), `runtime/comandos.py`, `hal/interfaces.py`, `hal/rover_v3.py`,
  `hal/lente.py`, `cli.py` (`valtexa-rover ensaio`; o serviço não aceita missão com
  ensaio em curso), `sim/__main__.py`; testes `test_ensaios.py`,
  `test_ensaio_comando.py` (novos), `test_lente.py`, `test_edge_cabeca.py`.
* saas: `valtexa/services/ensaios.py`, `valtexa/api/routers/ensaios_api.py`,
  `valtexa/models/ensaio.py`, `migrations/versions/0029_ensaios.py` (novos),
  `valtexa/models/comando.py`, `valtexa/models/__init__.py`,
  `valtexa/services/comando_rover.py`, `valtexa/services/events.py`,
  `valtexa/services/notifications.py`, `valtexa/main.py`, `simulator/fase0.py` (novo),
  `simulator/__main__.py`; testes `test_ensaios_plataforma.py`,
  `test_simulador_fase0.py` (novos), `test_isolamento_openapi.py` (id `resultado_id`).
* console: `src/lib/validacao.ts`, `src/lib/validacao.test.ts`,
  `src/platform/pages/Validation.tsx` (novos), `src/platform/api.ts`, `src/lib/comando.ts`,
  `src/platform/pages/CommandCenter.tsx`, `src/router.tsx`; roteiro `e2e/validacao.mjs` e
  `e2e/prepara_validacao.py` (novos).
* docs: `docs/VALIDACAO_ROVER.md` (novo), `docs/ROVER_RUNTIME.md` (§18),
  `docs/VERIFICACAO.md`, `docs/PROGRESSO.md`.

Não tocados: `rover/valtexa_rover/edge_ai/`, `ia/` (inclusive `plant_fusion.py`,
`fit_edge.py`, `fit_fusion.py` e os arquivos de terreno), limiares dos perfis.

## Parte 9 (05/10/2026, ~09h50–13h UTC) — produção, hardening e verificação final

### Números reais (execução completa, no fim da parte)

| Suíte | Início (`38fde9c`) | Fim |
| --- | --- | --- |
| SaaS — `pytest` no SQLite (3.11) | **790 passed** (11 min 43 s) | **888 passed, 3 skipped**, 0 falhas (11 min 17 s): +17 `test_producao_s3.py`, +24 `test_coordenacao.py` (1 skip), +38 `test_segredos.py` (2 skips), +21 `test_seguranca_parte9.py`, +1 `test_migrations.py` (índices); −2 porque dois testes antigos de configuração viraram parâmetros do `test_segredos.py` |
| SaaS — `pytest` **completa no Postgres 16.14** (`TEST_DATABASE_URL`) | **790 passed** (17 min 19 s) — primeira vez inteira | **888 passed, 3 skipped**, 0 falhas (16 min 12 s): o mesmo resultado do SQLite |
| SaaS — `ruff check .` | limpo | limpo |
| Migrações | SQLite e Postgres até **0024**; `alembic check` acusava 3 índices faltando | **0025**: SQLite e Postgres do zero até a head, `downgrade -1`, `upgrade head`; `alembic check` sem índice faltando |
| Rover — `pytest` (3.11) | 102 passed | 102 passed (nenhuma linha do `rover/` mudou) |
| IA — `KERAS_BACKEND=torch pytest` (3.12, com `dnaty`) | 746 passed | 746 passed (nenhuma linha do `ia/` mudou) |
| Console — `npm run build` / `npx vitest run` | verde / 112 passed | verde / **113 passed** (+1 injeção de fórmula no CSV) |
| Ponta a ponta — `python -m simulator --rover-runtime` (uvicorn + Rover real) | — | **31 de 31 OK** |
| Ponta a ponta — `tests/test_ponta_a_ponta.py` | — | **31 de 31 OK** (dentro das suítes) |
| Navegador — `web/e2e/telas-e-mapa.mjs` (banco novo, API servindo o build) | falhou no passo 3 (corrida do roteiro) | **13 de 13 passos, 0 erro de JS**, duas vezes (antes e depois do hardening) |
| Ensaio de produção sem Docker (2 réplicas + 2 workers, Postgres, Redis com senha, S3) | — | **10 de 10 passos** (`deploy/producao/ensaio.py`) |
| `docker compose config` de `deploy/producao/` | — | válido (9 serviços). **Imagens não construídas, contêineres não subidos**: não há daemon do Docker nesta sessão |

### Feito

1. **Verificação da Parte 8** (`docs/VERIFICACAO.md`): suítes, migrações nos dois bancos,
   roteiro de navegador e conferência no código de que as telas consomem o backend real e
   isolado por cliente (só `@/api/queries`, nenhum dado de exemplo; `get_scoped` nas três
   rotas novas). **Três defeitos corrigidos**: injeção de fórmula no CSV do relatório,
   corrida no roteiro de navegador e três índices que os modelos declaram e as migrações
   nunca criaram (migração **0025** + teste que compara índices, não só colunas).
2. **Object storage S3** (seção 38), `services/storage.py`:
   - `S3ObjectStore` com **multipart** no objeto grande (partes de 8 MB, aborta o upload
     inteiro se uma parte falhar — senão o bucket cobra partes órfãs), etiqueta
     `categoria` em cada objeto e **URL GET pré-assinada** (SigV4, 300 s);
   - **`S3ChunkStaging`**: os chunks de upload (do Rover e das coletas) viram objetos em
     `_staging/`, então **qualquer réplica recebe qualquer chunk** e qualquer uma monta o
     arquivo. Era *a* pendência que impedia mais de uma réplica da API. O `complete` é
     protegido por trava (duas réplicas não montam o mesmo upload: 409 + `Retry-After`);
   - **lifecycle por categoria** (`politica_de_ciclo_de_vida` +
     `python -m valtexa.services.storage --ciclo-de-vida`): chunk esquecido expira em 3
     dias, multipart incompleto aborta em 1 dia, imagem e nuvem de pontos vão para
     STANDARD_IA/GLACIER_IR **sem expirar**, log expira só se configurado;
   - rotas `.../url` (imagem da observação e arquivo da Edge AI) emitem a URL assinada
     **depois** do escopo do cliente; com disco local devolvem a rota da API. O disco
     local continua sendo a implementação de desenvolvimento, intacta.
3. **Redis** (seção 51), `services/coordenacao.py` (novo): limite de taxa por robô, travas
   e "uma vez por ciclo" atrás de uma interface — `CoordenacaoEmMemoria` (dev/teste) e
   `CoordenacaoRedis` (produção, com scripts Lua atômicos e o relógio do servidor Redis).
   Ligados em: limite das rotas de sincronização (antes multiplicava por réplica), o
   `complete` do upload e as tarefas periódicas do worker (dois workers não duplicam
   retenção nem alertas).
4. **Segredos** (seção 36): `SESSION_SECRET`, `COMMAND_SIGNING_SECRET`, `OTA_SIGNING_SECRET`
   e `INFERENCE_SERVICE_TOKEN` — vazios, padrão, com menos de 32 caracteres, com cara de
   exemplo ou **iguais entre si** impedem a subida da **API e do worker** em produção (e
   `METRICS_TOKEN` igual a qualquer um deles também). Leitura por **arquivo**
   (`SECRETS_DIR`, padrão `/run/secrets`). Rotação de cada um documentada em
   `docs/SEGURANCA.md` § 2, com o que ela quebra (a de missão/OTA exige reprovisionar).
5. **Postgres**: a suíte **completa** rodou no Postgres 16 (não só os módulos tocados),
   duas vezes — no começo e no fim da parte.
6. **Deploy**: `deploy/producao/` (compose de 9 serviços, `Caddyfile`, `prometheus.yml`,
   `gerar-segredos.sh`, `ensaio.py`), `docs/DEPLOY.md` (desenho, passo a passo, tabela do
   que está em código × passo de deploy, troubleshooting) e `docs/SEGURANCA.md` (checklist
   de 14 itens, rotação, mapa dos testes da seção 43).
7. **Hardening** (seção 43), com teste que falha sem a correção:
   - **corpo sem teto antes da autenticação**: qualquer um mandava gigabytes a
     `/v1/device/*` e a réplica guardava tudo em memória para conferir a assinatura →
     413 acima de `MAX_ASSET_MB` + 1 MB, pelo `Content-Length` ou parando de ler;
   - **tipo do arquivo pelos bytes**: HTML com nome `.jpg` entrava como imagem (na coleta
     e na observação do robô); agora vale a assinatura do formato e é ela que se guarda;
   - **arquivo servido inerte**: `CSP: sandbox`, `nosniff` e `attachment` fora da lista de
     tipos — inclusive para arquivo gravado antes desta parte; `nosniff` e
     `X-Frame-Options: DENY` em toda resposta;
   - **nome do robô**: dois robôs com número de série terminado igual davam **500** no
     provisionamento do segundo (colisão em `uq_device_tenant_name`) — achado no ensaio de
     produção, não nos testes;
   - bateria nova: replay da mesma requisição, corpo trocado depois de assinar, gravação
     fora da janela de relógio, chave de um robô com assinatura de outro, credencial
     revogada cortando sync/chunk/complete, sessão vencida no servidor com token válido,
     URL assinada adulterada para o objeto de outro cliente.
8. **Verificação final da rodada**: `docs/ACEITE.md` (os 31 critérios conferidos de novo,
   com os testes da Parte 9 na tabela de apoio), `README.md` da raiz (o que falta para o
   piloto, agrupado por dependência: pesos, hardware, infra, licença) e esta seção.

### Simulado, pendente ou com ressalva — e por quê

- **MinIO e AWS reais não foram usados**: o binário do MinIO está bloqueado pela rede
  desta sessão. O S3 foi exercitado contra o **`moto` em modo servidor** (HTTP de verdade,
  `boto3` de verdade, SigV4, multipart, etiquetas, listagem paginada, lifecycle). O que o
  `moto` não confere — a assinatura das URLs pré-assinadas — é conferido por um
  **verificador SigV4 independente** escrito da especificação da AWS
  (`tests/test_producao_s3.py::assinatura_valida`): URL válida passa, URL com a chave
  trocada para o objeto de outro cliente não, validade esticada não, vencida não.
- **Docker não roda nesta sessão** (sem daemon): o compose foi validado com
  `docker compose config` e as imagens **não** foram construídas. Em vez disso, o modo
  produção foi **ensaiado sem Docker** (`deploy/producao/ensaio.py`): `ENVIRONMENT=production`,
  segredos lidos dos arquivos de `gerar-segredos.sh`, Postgres 16, `redis-server` com
  senha, S3, **duas réplicas** da API e **dois** workers — 10 de 10 passos, incluindo
  upload alternando réplicas, URL assinada, limite somado e 413.
- **Transição de classe no MinIO**: o MinIO sem camada remota recusa
  `STANDARD_IA`/`GLACIER_IR`; o compose desliga as duas (`S3_*_AFTER_DAYS` vazios) e
  `docs/DEPLOY.md` diz para reativá-las na AWS.
- **Console ainda baixa imagem pela rota da API**, não pela URL assinada: é economia de
  banda, não de segurança (a rota continua no escopo do cliente).
- **Rotação da chave de missão/OTA exige reprovisionar** o robô (ele guarda uma chave só).
  `COMMAND_SIGNING_KEY_ID` existe na plataforma; o robô aceitar duas chaves é trabalho
  futuro — registrado em `docs/SEGURANCA.md`.
- **Índices em tabela grande**: a 0025 cria índices sem `CONCURRENTLY` (o Alembic roda em
  transação). Num banco já grande, criar à mão antes do deploy, com o mesmo nome — a
  migração usa `if_not_exists`. Está no `DEPLOY.md`.
- Nada do que o prompt pediu para não tocar foi tocado: `ai_pipeline.py`, `plant_map.py`,
  `decision_engine.py`, a ponte Edge AI → nuvem, `ia/app/plant_fusion.py`,
  `ia/app/fields_api.py`, `rover/valtexa_rover/edge_ai/` e os limiares da Edge AI
  (confira com `git diff 38fde9c..HEAD --name-only`: nenhum deles aparece).
- Do que ficou da lista da Parte 8: paginação dos registros da Edge AI no servidor,
  histerese/silenciar alerta e a camada da fusão calibrada no mapa.

<a id="arquivos-das-partes-69"></a>
## Arquivos das Partes 6–9 (para integrar localmente)

Da Parte 5 (`98977bc`) até o fim da Parte 9. Gere o diff de qualquer trecho com
`git diff 98977bc..HEAD -- <caminho>`; os commits são pequenos e com mensagem em
português (`git log --oneline 98977bc..HEAD`).

### SaaS — código (51)

| Arquivo | 6 | 7 | 8 | 9 |
| --- | :-: | :-: | :-: | :-: |
| `saas/valtexa/api/arquivos.py` | · | · | · | A |
| `saas/valtexa/api/deps.py` | · | M | · | · |
| `saas/valtexa/api/middleware.py` | · | · | · | M |
| `saas/valtexa/api/routers/auth.py` | M | · | · | · |
| `saas/valtexa/api/routers/console.py` | · | · | M | · |
| `saas/valtexa/api/routers/device_protocol.py` | · | · | · | M |
| `saas/valtexa/api/routers/edge_arquivos.py` | · | · | A | M |
| `saas/valtexa/api/routers/edge_sync.py` | · | · | · | M |
| `saas/valtexa/api/routers/fleet.py` | · | · | · | M |
| `saas/valtexa/api/routers/missions.py` | · | · | M | · |
| `saas/valtexa/api/routers/notifications.py` | A | · | · | · |
| `saas/valtexa/api/routers/observabilidade.py` | · | A | M | · |
| `saas/valtexa/api/routers/perception.py` | · | · | · | M |
| `saas/valtexa/api/routers/platform.py` | M | · | · | · |
| `saas/valtexa/api/routers/platform_ai.py` | · | M | · | · |
| `saas/valtexa/api/routers/support.py` | A | · | · | · |
| `saas/valtexa/api/routers/twin.py` | · | · | M | M |
| `saas/valtexa/config.py` | M | M | · | M |
| `saas/valtexa/main.py` | M | M | M | M |
| `saas/valtexa/models/__init__.py` | M | M | · | · |
| `saas/valtexa/models/edge.py` | · | · | · | M |
| `saas/valtexa/models/enums.py` | M | M | · | · |
| `saas/valtexa/models/fleet.py` | · | M | · | · |
| `saas/valtexa/models/notifications.py` | A | · | · | · |
| `saas/valtexa/models/observability.py` | · | A | · | · |
| `saas/valtexa/models/operations.py` | · | · | · | M |
| `saas/valtexa/models/support.py` | A | · | · | · |
| `saas/valtexa/models/tenancy.py` | M | · | · | · |
| `saas/valtexa/observability/__init__.py` | · | A | · | · |
| `saas/valtexa/observability/contexto.py` | · | A | · | · |
| `saas/valtexa/observability/http.py` | · | A | · | · |
| `saas/valtexa/observability/logs.py` | · | A | · | · |
| `saas/valtexa/observability/metricas.py` | · | A | · | · |
| `saas/valtexa/schemas.py` | M | M | M | M |
| `saas/valtexa/security/rbac.py` | M | M | · | · |
| `saas/valtexa/services/alertas.py` | · | A | M | · |
| `saas/valtexa/services/collections.py` | · | · | · | M |
| `saas/valtexa/services/coordenacao.py` | · | · | · | A |
| `saas/valtexa/services/dnaty.py` | · | M | · | · |
| `saas/valtexa/services/edge_sync.py` | · | · | · | M |
| `saas/valtexa/services/events.py` | M | M | · | · |
| `saas/valtexa/services/ingestion.py` | · | M | · | · |
| `saas/valtexa/services/notifications.py` | A | M | · | · |
| `saas/valtexa/services/observabilidade.py` | · | A | · | · |
| `saas/valtexa/services/ota.py` | M | · | · | · |
| `saas/valtexa/services/saude_rover.py` | · | A | · | · |
| `saas/valtexa/services/storage.py` | · | · | · | M |
| `saas/valtexa/services/support_sessions.py` | M | · | · | · |
| `saas/valtexa/services/support_tickets.py` | A | M | · | · |
| `saas/valtexa/services/visao_operacional.py` | · | · | A | · |
| `saas/valtexa/worker.py` | M | M | · | M |

### SaaS — migrações (4)

| Arquivo | 6 | 7 | 8 | 9 |
| --- | :-: | :-: | :-: | :-: |
| `saas/migrations/versions/0022_notificacoes.py` | A | · | · | · |
| `saas/migrations/versions/0023_suporte_chamados.py` | A | · | · | · |
| `saas/migrations/versions/0024_observabilidade.py` | · | A | · | · |
| `saas/migrations/versions/0025_indices_de_producao.py` | · | · | · | A |

### SaaS — testes (14)

| Arquivo | 6 | 7 | 8 | 9 |
| --- | :-: | :-: | :-: | :-: |
| `saas/tests/conftest.py` | · | · | · | M |
| `saas/tests/test_chamados.py` | A | M | · | · |
| `saas/tests/test_coordenacao.py` | · | · | · | A |
| `saas/tests/test_dnaty_registry.py` | · | M | · | · |
| `saas/tests/test_isolamento_openapi.py` | M | M | M | · |
| `saas/tests/test_migrations.py` | · | · | · | M |
| `saas/tests/test_notificacoes.py` | A | · | · | · |
| `saas/tests/test_observabilidade.py` | · | A | M | · |
| `saas/tests/test_producao_s3.py` | · | · | · | A |
| `saas/tests/test_segredos.py` | · | · | · | A |
| `saas/tests/test_seguranca_parte9.py` | · | · | · | A |
| `saas/tests/test_storage.py` | · | · | · | M |
| `saas/tests/test_token_de_servico.py` | · | · | · | M |
| `saas/tests/test_visao_operacional.py` | · | · | A | · |

### Console (web) (59)

| Arquivo | 6 | 7 | 8 | 9 |
| --- | :-: | :-: | :-: | :-: |
| `saas/web/e2e/observabilidade.mjs` | · | A | · | · |
| `saas/web/e2e/prepara_observabilidade.py` | · | A | · | · |
| `saas/web/e2e/prepara_suporte_e_avisos.py` | A | · | · | · |
| `saas/web/e2e/prepara_telas_e_mapa.py` | · | · | A | · |
| `saas/web/e2e/suporte-e-avisos.mjs` | A | · | · | · |
| `saas/web/e2e/telas-e-mapa.mjs` | · | · | A | M |
| `saas/web/openapi.json` | M | · | M | M |
| `saas/web/src/api/client.ts` | · | · | M | · |
| `saas/web/src/api/queries.ts` | · | · | M | · |
| `saas/web/src/api/schema.d.ts` | M | M | M | M |
| `saas/web/src/api/support.ts` | A | · | · | · |
| `saas/web/src/api/types.ts` | M | · | · | · |
| `saas/web/src/app.css` | · | · | M | · |
| `saas/web/src/components/MissionLayersMap.tsx` | · | · | A | · |
| `saas/web/src/components/NotificationBell.tsx` | A | · | · | · |
| `saas/web/src/components/NotificationCenter.tsx` | A | · | · | · |
| `saas/web/src/components/Observability.tsx` | · | A | · | · |
| `saas/web/src/components/TicketThread.tsx` | A | · | · | · |
| `saas/web/src/layout/AppShell.tsx` | M | M | · | · |
| `saas/web/src/lib/edgeRecords.test.ts` | · | · | A | · |
| `saas/web/src/lib/edgeRecords.ts` | · | · | A | · |
| `saas/web/src/lib/fieldHistory.test.ts` | · | · | A | · |
| `saas/web/src/lib/fieldHistory.ts` | · | · | A | · |
| `saas/web/src/lib/mapLayers.test.ts` | · | · | A | · |
| `saas/web/src/lib/mapLayers.ts` | · | · | A | · |
| `saas/web/src/lib/missionReport.ts` | · | · | M | · |
| `saas/web/src/lib/notifications.test.ts` | A | · | · | · |
| `saas/web/src/lib/notifications.ts` | A | · | · | · |
| `saas/web/src/lib/observability.test.ts` | · | A | · | · |
| `saas/web/src/lib/observability.ts` | · | A | · | · |
| `saas/web/src/lib/platformForms.test.ts` | · | · | A | · |
| `saas/web/src/lib/platformForms.ts` | · | · | A | · |
| `saas/web/src/lib/reportExport.test.ts` | · | · | A | M |
| `saas/web/src/lib/reportExport.ts` | · | · | A | M |
| `saas/web/src/lib/support.test.ts` | A | · | · | · |
| `saas/web/src/lib/support.ts` | A | · | · | · |
| `saas/web/src/pages/Dashboard.tsx` | · | · | M | · |
| `saas/web/src/pages/FieldDetail.tsx` | · | · | M | · |
| `saas/web/src/pages/FieldHistory.tsx` | · | · | A | · |
| `saas/web/src/pages/MapPage.tsx` | · | · | M | · |
| `saas/web/src/pages/MissionCompare.tsx` | · | · | A | · |
| `saas/web/src/pages/MissionDetail.tsx` | · | · | M | · |
| `saas/web/src/pages/MissionReportPage.tsx` | · | · | A | · |
| `saas/web/src/pages/Missions.tsx` | · | · | M | · |
| `saas/web/src/pages/Notifications.tsx` | A | · | · | · |
| `saas/web/src/pages/Observability.tsx` | · | A | · | · |
| `saas/web/src/pages/Support.tsx` | A | · | · | · |
| `saas/web/src/pages/SupportTicket.tsx` | A | · | · | · |
| `saas/web/src/platform/EnterAsClient.tsx` | M | · | · | · |
| `saas/web/src/platform/PlatformShell.tsx` | M | M | · | · |
| `saas/web/src/platform/api.ts` | · | · | M | · |
| `saas/web/src/platform/console.test.ts` | M | · | · | · |
| `saas/web/src/platform/pages/Ai.tsx` | · | · | M | · |
| `saas/web/src/platform/pages/Notifications.tsx` | A | · | · | · |
| `saas/web/src/platform/pages/Observability.tsx` | · | A | · | · |
| `saas/web/src/platform/pages/Ota.tsx` | · | · | M | · |
| `saas/web/src/platform/pages/Support.tsx` | A | · | · | · |
| `saas/web/src/platform/pages/SupportTicket.tsx` | A | · | · | · |
| `saas/web/src/router.tsx` | M | M | M | · |

### SaaS — outros (6)

| Arquivo | 6 | 7 | 8 | 9 |
| --- | :-: | :-: | :-: | :-: |
| `saas/.env.example` | M | M | · | M |
| `saas/docker-compose.yml` | · | · | · | M |
| `saas/docs/API.md` | M | M | M | · |
| `saas/docs/EVENTS.md` | M | M | · | · |
| `saas/requirements-dev.txt` | · | · | · | M |
| `saas/requirements.txt` | · | · | · | M |

### Rover (9)

| Arquivo | 6 | 7 | 8 | 9 |
| --- | :-: | :-: | :-: | :-: |
| `rover/tests/test_saude.py` | · | A | · | · |
| `rover/valtexa_rover/hal/__init__.py` | · | M | · | · |
| `rover/valtexa_rover/hal/interfaces.py` | · | M | · | · |
| `rover/valtexa_rover/hal/local.py` | · | M | · | · |
| `rover/valtexa_rover/hal/simulated.py` | · | M | · | · |
| `rover/valtexa_rover/runtime/core.py` | · | M | · | · |
| `rover/valtexa_rover/runtime/health.py` | · | M | · | · |
| `rover/valtexa_rover/runtime/sync.py` | · | M | · | · |
| `rover/valtexa_rover/sim/__init__.py` | · | M | · | · |

### IA (7)

| Arquivo | 6 | 7 | 8 | 9 |
| --- | :-: | :-: | :-: | :-: |
| `ia/.env.example` | · | M | · | · |
| `ia/app/main.py` | · | M | · | · |
| `ia/app/metrics.py` | · | A | · | · |
| `ia/app/model.py` | · | M | · | · |
| `ia/tests/test_dnaty_pipeline.py` | · | M | · | · |
| `ia/tests/test_metrics.py` | · | A | · | · |
| `ia/training/dnaty_pipeline.py` | · | M | · | · |

### Deploy (14)

| Arquivo | 6 | 7 | 8 | 9 |
| --- | :-: | :-: | :-: | :-: |
| `deploy/observabilidade/.gitignore` | · | A | · | · |
| `deploy/observabilidade/README.md` | · | A | · | · |
| `deploy/observabilidade/docker-compose.yml` | · | A | · | · |
| `deploy/observabilidade/grafana/dashboards/valtexa-visao-geral.json` | · | A | · | · |
| `deploy/observabilidade/grafana/provisioning/dashboards/valtexa.yml` | · | A | · | · |
| `deploy/observabilidade/grafana/provisioning/datasources/prometheus.yml` | · | A | · | · |
| `deploy/observabilidade/prometheus.yml` | · | A | · | · |
| `deploy/observabilidade/regras.yml` | · | A | · | · |
| `deploy/producao/.gitignore` | · | · | · | A |
| `deploy/producao/Caddyfile` | · | · | · | A |
| `deploy/producao/docker-compose.yml` | · | · | · | A |
| `deploy/producao/ensaio.py` | · | · | · | A |
| `deploy/producao/gerar-segredos.sh` | · | · | · | A |
| `deploy/producao/prometheus.yml` | · | · | · | A |

### Docs (8)

| Arquivo | 6 | 7 | 8 | 9 |
| --- | :-: | :-: | :-: | :-: |
| `docs/ACEITE.md` | · | · | M | · |
| `docs/ARQUITETURA.md` | M | M | · | · |
| `docs/DEPLOY.md` | · | · | · | A |
| `docs/OBSERVABILIDADE.md` | · | A | M | · |
| `docs/PROGRESSO.md` | M | M | M | · |
| `docs/SEGURANCA.md` | · | · | · | A |
| `docs/SYNC.md` | · | · | · | M |
| `docs/VERIFICACAO.md` | · | M | M | M |

### Raiz (1)

| Arquivo | 6 | 7 | 8 | 9 |
| --- | :-: | :-: | :-: | :-: |
| `README.md` | M | M | · | M |

**Total: 173 arquivos.** `A` = criado nessa parte, `M` = alterado, `·` = não tocado.


## Parte 8 (05/10/2026, ~05h20–06h30 UTC) — telas, mapa e painel

### Números reais

| Suíte | Início (`b2ca4f5`) | Fim |
| --- | --- | --- |
| SaaS — `pytest` no SQLite (3.11) | **781 passed** (0 falhas) | **790 passed**, 0 falhas (sobre `8aff7f3`): +3 `test_observabilidade.py` (defeitos da Parte 7), +6 `test_visao_operacional.py`; `test_isolamento_openapi.py` cobre as 3 rotas novas |
| SaaS — Postgres 16 (`TEST_DATABASE_URL`), módulos tocados | — | **44 passed** (1 min 20 s): visão operacional, isolamento gerado do OpenAPI, observabilidade |
| SaaS — `ruff check .` | limpo | limpo |
| Migrações (SQLite e Postgres 16) | do zero até 0024, `downgrade -1`, `upgrade head`: ok | **sem migração nova** nesta parte |
| Rover — `pytest` (3.11) | 102 passed | 102 (sem mudança no `rover/`) |
| IA — `KERAS_BACKEND=torch pytest` (3.12, com `dnaty`) | 746 passed | 746 (sem mudança no `ia/`) |
| Console — `npm run build` / `npx vitest run` | verde / 92 passed (12 arquivos) | **verde / 112 passed** (17 arquivos: +`mapLayers`, `edgeRecords`, `reportExport`, `fieldHistory`, `platformForms`) |
| Navegador (Playwright 1.63, Chromium, API servindo o build, banco novo) | — | `web/e2e/telas-e-mapa.mjs`: **13 de 13 passos, 0 erro de JS** (10 s). No log do servidor, só os dois `503` já esperados do mapa de plantas do `ia/` (serviço de IA fora daqui), chamados pela tela do talhão que já existia |

### Feito

1. **Verificação da Parte 7** (`docs/VERIFICACAO.md`): suítes, migrações nos dois bancos e
   o código de métricas, alertas e tela. Três defeitos corrigidos, cada um com teste que
   falha sem a correção: reconhecer enquanto o worker resolvia deixava o alerta aberto
   para sempre (agora `UPDATE` condicional → 409); o cliente desligar `rover_offline`
   calava a equipe (regra só da equipe); a equipe desligar a padrão não valia para quem
   tinha cópia. Mais: limite 0 tratado como 100 %.
2. **API** (`services/visao_operacional.py`, novo; nenhuma linha em `ai_pipeline.py`,
   `plant_map.py`, `decision_engine.py`, na ponte nem no `ia/`/`rover/`):
   - `GET /v1/missions/{id}/map` — rota percorrida (posições dos quadros, ≤ 2000),
     rota planejada, eventos da Edge AI com posição e se o original subiu, plantas com
     estado (consome `missao_resultado.plantas_da_missao`, só leitura);
   - `GET /v1/fields/{id}/history` — o ciclo do talhão, com a varredura de origem da
     prescrição (decisão → diagnóstico → observação → missão);
   - `GET /v1/edge/records/{id}/files/{upload_id}` — o arquivo do registro, pelo escopo
     do cliente (roteador novo `edge_arquivos.py`; `edge_sync.py` intocado);
   - `/v1/dashboard` ganha `overview` (seção 45).
3. **Console do cliente**: relatório da missão (`/missoes/:id/relatorio`), comparação
   (`/missoes/comparar`), linha do tempo (`/talhoes/:id/historico`), Mapa → **Por
   missão** (`components/MissionLayersMap.tsx` + `lib/mapLayers.ts`), painel ampliado;
   atalhos a partir da missão, do talhão e da lista de missões.
4. **Console da plataforma**: Atualizações (OTA) com **Publicar pacote** e **Destinar**;
   detalhe do modelo com **Registrar rodada** (dNATY).
5. **Roteiro de navegador** `web/e2e/telas-e-mapa.mjs` + `prepara_telas_e_mapa.py`;
   tipos do OpenAPI regenerados (`web/openapi.json`, `src/api/schema.d.ts`).
6. Docs: `ACEITE.md` (29 e 30 → OK; resumo 23 OK / 8 PARCIAL), `VERIFICACAO.md`,
   `OBSERVABILIDADE.md`, `saas/docs/API.md`.

### Simulado, pendente ou com ressalva — e por quê

- **Mapa de camadas**: estado, doença e calor vêm da **fusão operacional** da missão
  (`/missions/{id}/plants`, posições médias dos quadros). A fusão **calibrada** do `ia/`
  (`/fields/{id}/plants/map`) não é usada nesta tela: o serviço de IA não roda aqui
  (503) e `plant_map.py` está com o Pedro. Quando estiver ligado, vira uma camada a mais.
- **Umidade, falhas de plantio e produtividade**: só a interface (camada declarada,
  desligada, com o motivo). Não há sensor, mapa de plantas de campo nem dado de colheita.
- **Pragas** = eventos `POSSIVEL_PRAGA` da Edge AI (sem confirmação da nuvem) — a camada
  diz isso.
- **PDF** é a impressão do navegador (CSS de impressão conferido no Playwright); não há
  gerador de PDF no servidor.
- **Registros da Edge AI** na tela: até 1000 por missão (o limite da rota), 100 por vez
  na tabela; missão maior pede paginação no servidor (a rota já aceita `offset`).
- **OTA de modelo** pela tela depende de haver versão em PRODUÇÃO com artefato e do `.tar`
  montado com `{sha}.onnx` — a tela diz o nome; montar o `.tar` no navegador não foi feito.
- O cliente **desligar** outra regra de robô também tira o alerta da equipe (alerta é um
  só por assunto) — decisão registrada em `VERIFICACAO.md`.

### O que a PARTE 9 (produção e verificação final) deve fazer, em ordem

1. **Verificação da Parte 8**: suítes, `telas-e-mapa.mjs` de novo num banco novo, e
   conferir no código o escopo das 3 rotas novas e a montagem do CSV.
2. **Object storage** (seção 38): `storage.py` hoje é disco local (`STORAGE_DIR`); ligar
   S3/MinIO por interface já existente (`put/open/read`), com URL de leitura só pela API
   (as rotas de imagem e de arquivo da Edge AI já passam pelo escopo do cliente),
   *staging* de chunks do `edge_sync` fora do disco da réplica, teste com MinIO local.
3. **Redis** (seção 51): o que hoje é memória por processo — limitador de taxa do
   `edge_sync`, cache de 15 s do `/metrics`, cache do estado da IA, fluxo ao vivo
   (`/v1/stream`) entre réplicas — passa a Redis, com o modo sem Redis para dev.
4. **Segredos**: chaves de assinatura de missão e OTA, `JWT_SECRET`, `METRICS_TOKEN`,
   `SERVICE_TOKEN`, SMTP — de arquivo/variável para gerenciador de segredos (interface +
   arquivo montado), rotação documentada; varrer o repositório (nenhum segredo no código).
5. **Postgres em produção**: a suíte **completa** no Postgres (só módulos tocados foram
   rodados nas Partes 7 e 8), índices das consultas novas (`edge_record` por
   `tenant_id, kind, occurred_at`; `mission` por `field_id, kind`), `pg_dump`/restauração
   e migração com a aplicação no ar.
6. **Verificação final**: os 31 critérios do `ACEITE.md` de novo (ponta a ponta + todos os
   roteiros de navegador), `docker compose` subindo API, worker, IA, Postgres, Redis,
   MinIO, Prometheus e Grafana, e o `README.md` da raiz com o que falta para o piloto.
7. Do que ficou: histerese/silenciar alerta; paginação dos registros da Edge AI no
   servidor; camada da fusão calibrada no mapa quando o serviço de IA estiver ligado.

---

## Parte 7 (05/10/2026, ~00h20–02h UTC) — observabilidade e alertas

### Números reais

| Suíte | Início (`81c5f6d`) | Fim |
| --- | --- | --- |
| SaaS — `pytest` no SQLite (3.11) | 751 passed (9 min 04 s) | **781 passed** (8 min 35 s, sobre `ee807e5`), 0 falhas: +29 `test_observabilidade.py`; `test_isolamento_openapi.py` com alerta e regra reais da vítima; +1 asserção no `test_chamados.py`, +1 `test_dnaty_registry.py` |
| SaaS — Postgres 16 local (`TEST_DATABASE_URL`), módulos tocados | — | **85 passed** (1 min 55 s): migrações, observabilidade, isolamento gerado do OpenAPI, chamados, notificações, dNATY, worker; depois da agregação no banco, observabilidade + isolamento de novo: **35 passed** |
| SaaS — `ruff check .` | limpo | limpo |
| Rover — `pytest` (3.11) | 95 passed | **102 passed** (+7 `test_saude.py`) |
| IA — `KERAS_BACKEND=torch pytest` (3.12) | 738 passed, **1 failed**, 1 skipped | **746 passed** (+5 `test_metrics.py`, +1 ruído do dNATY; o *skip* era a falta do `dnaty`) |
| Console — `npm run build` / `npx vitest run` | verde / 84 passed | **verde / 92 passed** (+8 `lib/observability`) |
| Navegador (Playwright, Chromium, API servindo o build) | — | `web/e2e/observabilidade.mjs`: **10 de 10 passos**, sem erro de JS |
| `promtool` (Prometheus 2.54.1) | — | `check config` e `check rules` ok; as 20 consultas do painel do Grafana ok; `check metrics` ok na exposição real da API e da IA |

Migração **0024** (tabelas `api_request_stat`, `alert_rule`, `alert`; colunas anuláveis
`device.health` e `device.health_reported_at`). SQLite e **Postgres 16**: do zero até a
head, `downgrade -1` (as tabelas e colunas somem) e `upgrade head`, sem erro. Nada
existente muda de valor.

Concorrência no Postgres (roteiro avulso, `/var/tmp/conc.py`): 4 workers avaliando os
alertas ao mesmo tempo, 50 robôs com disco cheio → **50 alertas e 50 eventos**, nenhum
duplicado — depois da correção do catálogo (abaixo), que esse roteiro achou.

### Feito

1. **Verificação da Parte 6** (`docs/VERIFICACAO.md`): suítes, migrações (SQLite e
   Postgres) e o código de notificações e chamados. Dois defeitos corrigidos, com teste
   que falha sem a correção: a **nota interna do chamado aparecia na auditoria do
   cliente** (`/v1/audit`); e o critério do **dNATY aceitava um modelo idêntico** como
   otimizado (ruído de memória e latência contado como ganho — o teste da IA falhava em
   2 de 3 rodadas).
2. **SaaS** (`saas/valtexa/observability/`, `services/observabilidade.py`):
   - *middleware* ASGI que mede toda requisição pelo **molde** da rota (latência em
     histograma, status, 5xx) e põe `X-Request-Id` em toda resposta;
   - **logs estruturados** (`LOG_FORMAT=json`) com `request_id`, cliente, usuário, robô e
     sessão de suporte (as dependências de autenticação preenchem o contexto);
   - estatística **por minuto** gravada no banco por cada réplica (`api_request_stat`),
     para o console e os alertas não dependerem de qual réplica respondeu;
   - filas (trabalhos, eventos do *outbox*, entregas de aviso), usuários ativos;
   - **`/metrics`** no formato do Prometheus, protegido (`METRICS_TOKEN` ou equipe com
     `platform:observability:read`), no teste de isolamento gerado do OpenAPI.
3. **IA** (`ia/app/metrics.py`): por modelo, imagens, chamadas, erros por tipo, tempo por
   imagem e **classes previstas**, medidos em `predict_images` (sem tocar em
   `plant_fusion.py`/`fields_api.py`); HTTP por rota; `/metrics` atrás do `SERVICE_TOKEN`.
   Na plataforma: inferências da nuvem (`detection`) e da borda (`edge_record`) por modelo
   e o **drift da distribuição de classes** (recente × 7 dias anteriores).
4. **Rovers**: a HAL ganhou `SystemMonitor` — `LinuxSystemMonitor` real (`/proc`) e
   `SimulatedSystemMonitor` marcado; o Health Monitor manda `health` padronizado em cada
   amostra (CPU, memória, acelerador, disco, temperatura, bateria, **cada câmera**,
   GPS/IMU/sensores, rede, **fila de sincronização** com a idade do mais antigo, Edge AI e
   o que é simulado). A plataforma guarda só os campos conhecidos (`saude_rover.py`).
5. **Alertas** (`services/alertas.py`): 10 regras — robô offline há X min, disco > Y %,
   temperatura, sincronização parada, câmera, modelo divergente do liberado, taxa de erro
   da API, IA fora, drift de classes, eventos parados — avaliadas pelo worker a cada
   60 s; estado **disparado → reconhecido → resolvido** (resolve sozinho); um aberto por
   assunto (restrição única); regra padrão editável pela equipe e **versão própria do
   cliente** nas de robô; tudo auditado; entregues pelas **notificações da Parte 6**
   (`alerta_robo`, `plataforma_alerta`), com preferências, idempotência e "sem SMTP não
   finge".
6. **Telas**: "Observabilidade" no console da plataforma (componentes, API por rota,
   robôs de todos os clientes, IA e drift, alertas, regras) e "Saúde da frota" no do
   cliente (só os robôs e alertas dele, regra própria). Conferidas no navegador.
7. **`deploy/observabilidade/`**: `prometheus.yml` (tokens por arquivo), `regras.yml`
   (segunda linha: a plataforma fora do ar), Grafana (*provisioning* + painel de 16
   gráficos) e `docker-compose.yml` — sem segredo.
8. Docs: `docs/OBSERVABILIDADE.md` (novo), `docs/VERIFICACAO.md`, `docs/ARQUITETURA.md`
   (componente G), `saas/docs/API.md`, `saas/docs/EVENTS.md`, `.env.example` (SaaS e IA).

### Defeitos achados nesta parte

| Onde | Defeito | Como apareceu | Correção |
| --- | --- | --- | --- |
| `services/support_tickets.py` (Parte 6) | nota interna visível na auditoria do cliente | conferência no código | auditoria da nota interna vai para a trilha da plataforma |
| `ia/training/dnaty_pipeline.py` + `saas/.../dnaty.py` | modelo idêntico aceito como otimizado | teste instável da IA (2 de 3) | piso de ruído de latência e memória no critério |
| `services/alertas.py` | dois workers num banco novo: `UniqueViolation` no catálogo derrubava a avaliação | 4 workers em paralelo no Postgres | *savepoint* por regra |
| `observability/http.py` | rota sem o prefixo `/v1` (o FastAPI 0.142 guarda o caminho relativo ao roteador) | teste do molde | molde reconstruído com o prefixo do caminho real |
| `ia/app/metrics.py` | `_ms` no nome da métrica (fora da convenção) | `promtool check metrics` | unidade base: `..._duration_seconds` |
| `services/observabilidade.py` | *drift* e IA lidos linha a linha (8 dias) a cada minuto e a cada raspagem | revisão do próprio código (seção 51) | `GROUP BY` no banco, p95 por amostra recente, cache de 15 s no `/metrics` |

### Simulado, pendente ou com ressalva — e por quê

- **Prometheus/Grafana** não rodaram contra um ambiente real (não há um aqui); a
  configuração e a exposição passaram no `promtool`.
- **GPU/NPU**: só a interface — sem hardware definido não há adapter real; sai "não
  medido". Temperatura e bateria seguem simuladas até haver sensor.
- **Drift** é o da **saída** (classes previstas); o da entrada precisa da referência do
  treino (VALTEXA-B). Drift alto pode ser surto real na lavoura.
- **Inferência real** não roda aqui: as métricas da IA foram provadas com o dublê.
- Sem "silenciar por X horas" nem dono atribuído (há reconhecer com nota); sem histerese
  para robô oscilando no limite.
- A suíte completa no Postgres não foi rodada nesta parte (só os módulos tocados).

### O que a PARTE 8 deve fazer, em ordem

1. **Mapa de incidência** (seções 45 e 46): camada no `MapPage` e no talhão com as
   plantas de `GET /v1/fields/{id}/plants/map` (estado por planta, coordenadas), cor por
   incidência/doença, filtro por missão e data, legenda; clique abre a **evolução da
   planta** (`GET /v1/fields/{id}/plants/{plant_id}/evolution`, sem tela hoje); comparação
   antes/depois da aplicação (`GET /v1/missions/{id}/comparison`) desenhada no mapa.
2. **Telas que hoje só existem na API** (levantadas pelo OpenAPI × `web/src`):
   - plataforma: **planos** (`GET/POST/PATCH /v1/admin/plans`), **assinatura de um
     cliente** (`GET/PUT /v1/admin/tenants/{id}/subscription`) e **registro de
     consentimento por termo** (`GET/PUT /v1/admin/tenants/{id}/data-consent`) — conferir
     o que a tela de Clientes já cobre e completar; **relevo do talhão**
     (`POST /v1/admin/fields/{id}/relief`); **missão de drone**
     (`POST /v1/admin/drone-missions`); lista de versões de modelo
     (`GET /v1/admin/models/versions`);
   - cliente: **registros da Edge AI** (`GET /v1/edge/records`), **prévia de segurança
     da missão** (`POST /v1/missions/{id}/safety/preview`) antes de autorizar, e **derrubar
     as sessões de um usuário** (`DELETE /v1/users/{id}/sessions`) em Configurações.
3. Observabilidade, o que ficou: silenciar alerta por período e dono; histerese; o
   Grafana contra um ambiente real; a suíte completa no Postgres; correlação
   requisição ↔ evento ↔ aviso (o `request_id` no `outbox_event`).
4. Ainda da lista da Parte 6: trilha de auditoria completa da seção 50 com teste gerado
   (login, plano, entrar como cliente, missão, modelo, OTA, prescrição, aprovação,
   aplicação, exclusão de dados); aviso de depreciação do `httpx` no `TestClient`.

---

## Parte 6 (04/10/2026, ~19h–22h UTC) — notificações e suporte

### Números reais

| Suíte | Início (`98977bc`) | Fim |
| --- | --- | --- |
| SaaS — `pytest` no SQLite (3.11) | 722 passed (8 min 51 s) | **751 passed** (9 min 40 s), 0 falhas: +21 `test_notificacoes.py`, +8 `test_chamados.py`; `test_isolamento_openapi.py` com aviso e chamado reais da vítima |
| SaaS — Postgres 16 local (`TEST_DATABASE_URL`), módulos tocados | — | **99 passed** (2 min 37 s): migrações, notificações, chamados, isolamento gerado do OpenAPI, plataforma e suporte, OTA, worker |
| SaaS — `ruff check .` | limpo | limpo |
| Rover — `pytest` (3.11) | 95 passed | **95 passed** (sem mudança no `rover/`) |
| Console — `npm run build` / `npx vitest run` | verde / 74 passed | **verde / 84 passed** (+5 `lib/notifications`, +5 `lib/support`; 4 testes do menu da plataforma atualizados para o grupo "Atendimento") |
| Navegador (Playwright, Chromium, API servindo o build, worker na API) | — | `web/e2e/suporte-e-avisos.mjs`: **8 de 8 passos**, sem erro de JS |
| IA — `KERAS_BACKEND=torch pytest` | 739/740 (Pedro / Parte 5) | **não rodada nesta parte**: nada no `ia/` mudou |

Migrações: **0022** (notificações) e **0023** (chamados, incidentes e `support_session.ticket_id`).
No **Postgres 16**: `upgrade head` → `downgrade 0021` (as tabelas novas somem) → `upgrade head`,
sem erro; no SQLite, `test_migrations.py` (esquema migrado = modelos, ida e volta). Nada
existente muda de valor: só tabelas novas e uma coluna anulável.

### Feito

1. **F48 — Notificações** (`saas/valtexa/services/notifications.py`, `models/notifications.py`,
   `api/routers/notifications.py`). Desacoplado das telas: **evento de domínio (outbox) →
   regra → preferência → aviso → canal**. As regras são os primeiros *handlers* do outbox
   (ele drenava sem ninguém ouvir):
   - `diagnosis.created` → **nova infecção** (uma vez por doença, talhão e missão/dia — não
     um aviso por foto); `mission.completed` → **incidência acima do limite** (incidência
     por planta da missão, limite por pessoa, padrão 5 %); `safety.blocked` → **missão
     bloqueada**; `device.offline` → **robô sem comunicação**; `ota.failed` (evento novo,
     publicado pelo `services/ota.py` quando o robô informa `falhou`/`revertida`/`recusada`)
     → **atualização falhou**, para o cliente e para a equipe.
   - **Preferências** em três camadas: a da pessoa > a do papel no cliente (o gestor
     define; na equipe, o superadmin) > o padrão do código; cada linha diz a origem.
   - **Idempotente**: `dedup_key` única por pessoa (restrição no banco + checagem antes +
     *savepoint*); reentregar o evento ou dois workers com o mesmo evento não duplicam
     (testado, inclusive no Postgres).
   - **Canais**: central do console (sempre) e **e-mail por SMTP** configurável
     (`SMTP_*`, `CONSOLE_URL`), entregue pelo **worker** com novas tentativas (espera
     exponencial, 6 tentativas, `desistiu`; destinatário recusado não repete). **Sem SMTP,
     a entrega fica `nao_enviado` com o motivo**, e a tela mostra isso. WhatsApp, push e
     SMS: só a interface (`Canal`), marcados como não implementados; a preferência os recusa.
   - Rotas da central no cliente (`/v1/notifications/**`, caixa da pessoa no cliente ativo)
     e na plataforma (`/v1/platform/notifications/**`).
2. **F49 — Suporte** (`services/support_tickets.py`, `models/support.py`,
   `api/routers/support.py`). Chamado (`CH-00001`) com status, prioridade, categoria,
   **vínculo com cliente, robô e missão** (do próprio cliente, senão 404), responsável na
   equipe, comentários **visíveis ou internos** (o cliente não vê a nota interna nem a
   entrada dela no histórico), **histórico** de toda mudança e **auditoria** (`ticket.*`).
   **Incidente** (`INC-0001`) agrupa chamados de vários clientes, com nota pública que
   chega a cada cliente pelo chamado. O cliente abre, comenta, fecha e reabre os dele; a
   equipe vê todos, atende, abre em nome do cliente. **"Entrar como cliente" referencia o
   chamado** (`ticket_id`): a sessão nasce com o código do chamado e o histórico do
   chamado mostra ao cliente que a equipe entrou. Avisos ligados ao item 1 (chamado novo
   → Suporte; resposta da equipe → quem abriu; resposta do cliente → responsável;
   incidente atualizado → cada cliente afetado). Capacidades novas: `support:ticket`
   (cliente, menos auditor e leitor), `platform:ticket:read` e `platform:ticket:manage`.
3. **Isolamento**: o teste gerado do OpenAPI ganhou um aviso real e um chamado real da
   vítima (com nota interna e incidente); a foto do estado da vítima passou a incluir as
   tabelas de aviso e preferência (têm `tenant_id` anulável, fora de `TenantScoped`). O
   atacante com 3 papéis bate em todas as rotas novas: 404/403, nada muda; nenhum papel de
   cliente alcança `/v1/platform/tickets|incidents|notifications`; sessão de suporte em
   leitura não marca aviso como lido nem comenta.
4. **Telas** (`saas/web`): sino com não lidas nos dois consoles; **central** (avisos por
   dia, estado do e-mail, minhas preferências, por papel para gestor/superadmin);
   **Suporte** do cliente (lista, abrir com robô e missão, conversa, histórico, fechar e
   reabrir) e da plataforma (fila por prioridade e espera, agrupar em incidente,
   incidentes com nota pública, detalhe com atendimento, nota interna e "Entrar como
   cliente" ligado ao chamado). Conferidas no navegador (8 de 8).
5. Docs: `saas/docs/API.md` (seção nova), `saas/docs/EVENTS.md` (eventos novos e a tabela
   de regras), `docs/ARQUITETURA.md`, `README.md` (item 9 do piloto), `.env.example`.

### Defeitos achados nesta parte

| Onde | Defeito | Como apareceu | Correção |
| --- | --- | --- | --- |
| `web/components/TicketThread.tsx` | o texto digitado enquanto o comentário anterior era enviado sumia quando o envio terminava | roteiro de navegador | limpa ao enviar e devolve o texto se falhar |
| aviso de robô offline | "Último contato" saía em ISO cru | captura de tela | data legível (`dd/mm/aaaa hh:mm UTC`) |

### Simulado, pendente ou com ressalva — e por quê

- **E-mail** foi provado com um servidor SMTP mínimo, de verdade, na porta local (o
  `smtplib` fala o protocolo inteiro); com um provedor real (STARTTLS, autenticação)
  **não foi testado** aqui — sem credencial. Falta configurar `SMTP_*` em produção.
- **WhatsApp, push, SMS**: interface só; não há telefone nem token de aparelho no cadastro.
- **Incidência acima de X** usa a incidência **por planta** da missão (fusão operacional
  do SaaS, `missao_resultado.plantas_da_missao`, só leitura). Missão sem plantas
  identificadas (sem Edge AI) não gera esse aviso. Quando a fusão calibrada do `ia/` for
  ligada, a regra deve ler dela.
- **Nova infecção** depende de `diagnosis.created`: com a IA de nuvem simulada nos testes,
  os rótulos são os do `SimulatedAnalyzer`.
- **"Robô offline"**: um aviso por queda (cada `device.offline`); sem agregação de
  quedas repetidas do mesmo robô num intervalo curto — se incomodar em campo, agrupar.
- Chamado aberto **pela equipe em nome do cliente** não tem "solicitante" do cliente:
  quem acompanha vê na lista, mas ninguém do cliente é avisado das respostas.
- Sem **SLA** formal (prazo por prioridade) nem fechamento automático de `resolvido`
  parado; a fila mostra "sem resposta há N min".
- Avisos e entregas não são apagados (sem retenção); com volume, entra na retenção.
- A suíte completa no Postgres **não** foi rodada nesta parte (só os módulos tocados).

### O que a PARTE 7 (observabilidade e alertas, seção 35) deve fazer, em ordem

1. **Métricas do SaaS**: middleware que mede latência e erro por rota (p50/p95, 4xx/5xx),
   jobs (fila, idade do mais antigo, falhas), eventos do outbox (pendentes, com
   `last_error`, idade), entregas de aviso (`falhou`/`desistiu`), usuários ativos; expor
   em `/metrics` (formato Prometheus, protegido) e num painel no console interno.
2. **Métricas da IA** (seção 34/35): inferências, latência, taxa de erro, distribuição de
   classes e *drift* por modelo e cliente, a partir do que o SaaS já grava (diagnósticos,
   registros da Edge AI); Rovers com modelos diferentes do liberado.
3. **Métricas do Rover**: CPU, GPU/NPU, memória, disco, temperatura, bateria, câmeras,
   sensores, conectividade, versão e atraso de sincronização — a telemetria e o `health`
   do `rover/` já trazem parte; padronizar, guardar agregado e mostrar na frota.
4. **Alertas** sobre as métricas: regras com limiar e janela (ex.: 5xx > 2 % em 5 min,
   outbox parado, fila de sincronização de um robô crescendo, disco do robô > 90 %,
   temperatura, drift), com estado (disparado/resolvido), silenciar e dono — e **entregar
   pelo módulo de notificações desta parte** (tipos novos de aviso para a equipe e para o
   cliente), sem duplicar o mecanismo.
5. **Logs estruturados** (JSON, com `request_id`, cliente, robô, sessão de suporte) e
   correlação requisição ↔ evento ↔ aviso; trilha de auditoria completa da seção 50
   (conferir que login, plano, entrar como cliente, missão, modelo, OTA, prescrição,
   aprovação, aplicação e exclusão de dados estão todos lá — teste gerado).
6. Rodar a **suíte completa no Postgres** e a CI no GitHub; limpar o aviso de
   depreciação do `httpx` no `TestClient`.

---

## Parte 5 (04/10/2026, ~07h–09h UTC)

### Números reais

| Suíte | Início (`5e2373a`) | Fim |
| --- | --- | --- |
| SaaS — `pytest` no SQLite (3.11) | 700 passed (8 min 02 s) | **722 passed** (9 min 07 s): +7 dNATY, +10 OTA, +1 ponta a ponta, +1 estresse de frota, +3 hardening |
| SaaS — `pytest` no **Postgres 16** (`TEST_DATABASE_URL`) | nunca rodado | **722 passed** (10 min 37 s) — primeira vez no Postgres |
| SaaS — `ruff check .` | limpo | limpo |
| Rover — `pytest` (3.11) | 75 passed (6,4 s) | **95 passed** (22,6 s): +13 OTA, +2 simulador, +2 estresse, +2 serviço, +1 regressão |
| Rover — `ruff check .` | limpo | limpo |
| IA — `KERAS_BACKEND=torch pytest` (3.12) | 732 passed (4 min 05 s) | **740 passed** (4 min 20 s): +8 `test_dnaty_pipeline.py`, com o `dnaty` 2.2.1 de verdade |
| Console — `npm run build` / `npx vitest run` | verde / 67 passed | **verde / 74 passed** (+4 resultado da missão, +3 OTA) |
| Navegador (Playwright, API servindo o build, banco do ponta a ponta) | — | `web/e2e/resultado-e-ota.mjs`: **4 de 4 passos**, sem erro de JS |

Migrações: SQLite e **Postgres 16** — do zero até a head (**0021**), `downgrade -1`,
`downgrade 0018`/`0016` e `upgrade head` de novo, sem erro (Postgres local nesta nuvem,
`/usr/lib/postgresql/16`).

Ponta a ponta (`tests/test_ponta_a_ponta.py` e `python -m simulator --rover-runtime`,
este com uvicorn e o Rover falando HTTP pela HAL de rede): **31 de 31 passos** — 140
quadros de 2 câmeras, 8 eventos, 8 originais + 132 reduzidas (2,95 MB), 30 passos sem
rede com reinício no meio, 151 registros sincronizados, as 4 plantas doentes achadas
(exatamente as da verdade simulada), incidência 4/54 = 7,4 % (IC 95 % 2,9–17,6 %),
"candidata a aplicação" com 5,6 % de 54 plantas com Rust, aplicação, nova missão:
incidência 7,4 % → 1,9 %, 3 plantas recuperadas.

Estresse (detalhes em `docs/ESTRESSE.md`): 1.500 passos (2.970 quadros) com 600 passos sem rede, 32 respostas 5xx injetadas e 2 reinícios: 3.286 registros, todos na nuvem uma vez só, 18 de 18 originais de evento entregues, fila zerada (≈100 quadros/s); 6 Rovers de 2 clientes em paralelo contra a API: 1.014 registros e 864 arquivos, nada perdido nem duplicado, isolamento conferido (28,8 s). **100.000 quadros-alvo** (`--passos 50000 --cota-mb 400`): 99.000 quadros, 71 reinícios, 19.980 passos sem rede, 1.000 respostas 5xx/429, 640 limpezas por disco cheio — **110.106 registros = 110.106 na nuvem**, fila zerada, 58 min. A conferência de originais de evento dessa execução não valeu (lia linhas que a limpeza apaga); corrigida e reconferida em 3.000 passos com disco de 2 MB: 38 de 38.

### Feito

1. **Verificação da Parte 4** (`docs/VERIFICACAO.md`): suítes, migrações e os sete itens
   conferidos no código. Um defeito real: o *backoff* da fila do Rover ficava no relógio
   monotônico e prendia a fila por horas depois de um reinício — corrigido, com teste que
   falha sem a correção.
2. **F12 dNATY** (`docs/DNATY.md`): `ia/training/dnaty_pipeline.py` mede original e
   otimizado pelo ONNX Runtime (precisão, recall, F1, recall por classe, latência p50/p95,
   FPS, memória, tamanho, FLOPs) e compara com um **critério de aceite configurável** que
   não aceita "só porque ficou menor"; `DnatyOtimizador` usa o **`dnaty` 2.2.1 de
   verdade** (testado) e `QuantizacaoDinamicaOnnx` (INT8, não é dNATY). No SaaS:
   `model_optimization` (migração 0019), `POST/GET /v1/platform/models/{id}/optimizations`
   — o registry **recalcula** o veredito, guarda toda rodada, leva o otimizado só se
   aceito, mantém o original separado, e **não aprova** versão com otimizado sem rodada
   aceita daquele hash. Licença BSL 1.1 anotada em cada rodada.
3. **F13 OTA** (`docs/OTA.md`): no SaaS, `ota_package`/`ota_deployment` (migração 0020),
   publicação (`.tar` conferido; **modelo só em PRODUÇÃO** e com o hash do registry),
   destino por robô ou cliente com **envelope assinado** (Ed25519, chave OTA própria,
   `OTA_SIGNING_SECRET`, obrigatória em produção; domínio separado do das missões),
   download em pedaços, estados informados pelo robô, cancelamento, auditoria. No
   `rover/`: `OtaManager` (assinatura, destinatário, validade, anti-*replay*, download com
   retomada, hash por arquivo, instalação lado a lado, saúde por tipo, ponteiro atômico,
   confirmação no boot) e `launcher.py` (A/B: volta sozinho se o novo não confirmar).
   Nada instala com missão em execução.
4. **F14 Simulador único** (`docs/ROVER_RUNTIME.md` §11): `valtexa_rover.sim` monta o
   **mesmo** `RoverCore` sobre a HAL simulada (campo com espaçamento, câmera de cena,
   plano de rede, reinício, câmera fora, controlador de rota, modelo de demonstração);
   `python -m valtexa_rover.sim --url ... --token ...` contra uma plataforma no ar;
   `python -m simulator --rover-runtime` no `saas/`. O simulador antigo ficou como
   **legado** (drone, dock, cópia 3D). O Core passou a informar `ack`/`complete` da
   missão à plataforma (fila local, sai quando há rede).
5. **F15–F17 Testes**: `rover/tests/test_estresse.py`, `saas/tests/test_estresse_frota.py`
   (6 Rovers de 2 clientes em threads contra a API), `python -m valtexa_rover.sim.estresse`
   (números grandes) e o **ponta a ponta** (`saas/simulator/ponta_a_ponta.py`, os 31
   critérios — `docs/ACEITE.md`). Para fechar a cadeia: **ponte Edge AI → IA de nuvem**
   (o evento com original vira observação + diagnóstico + decisão; migração 0021),
   **fusão operacional por planta** e incidência com Wilson
   (`GET /v1/missions/{id}/plants`), **relatório** (`/report`, seção 47) e
   **comparação** (`/comparison`); o motor de decisão usa a incidência **por planta**
   quando o diagnóstico vem da Edge AI.
6. **F18 Hardening**: `claim` de trabalho com *compare-and-set* (e `FOR UPDATE SKIP
   LOCKED` no Postgres), **limite de taxa por robô** nas rotas de sincronização (429 +
   `Retry-After`), **TTL** de upload abandonado, varredura da ponte no worker,
   `OTA_SIGNING_SECRET` nas pendências de produção; teste de isolamento gerado do OpenAPI
   cobre as rotas novas (ataca um destino OTA real da vítima).
7. **F19 Deploy**: `.github/workflows/ci.yml` (Rover; SaaS com **Postgres** e migrações
   ida e volta; console; IA com dNATY), `valtexa-rover servico` (o laço do robô) e
   `rover/deploy/` (unidade systemd com o lançador A/B e menor privilégio,
   `rover.json.exemplo`, `rover.env.exemplo`).
8. **Console**: cartão "Resultado da missão" (incidência por planta, ocorrências,
   recomendações, prescrição, comparação, marca de simulação); console interno com
   **Atualizações (OTA)** e as **rodadas de otimização** no detalhe do modelo; tipos do
   OpenAPI regenerados.
9. Docs: `ACEITE.md`, `OTA.md`, `DNATY.md`, `ESTRESSE.md`, `ROVER_RUNTIME.md` (§10–13),
   `SYNC.md` (§6), `ARQUITETURA.md`, `VERIFICACAO.md`, `README.md` da raiz.

### Correções achadas pelos testes novos (defeitos reais, não de teste)

| Onde | Defeito | Como apareceu | Correção |
| --- | --- | --- | --- |
| `rover/runtime/store.py` | *backoff* no relógio monotônico prendia a fila por horas depois de reinício | verificação da Parte 4 | o boot zera a espera dos pendentes |
| `saas/services/mission_manager.py` | `sequence` do comando numerada **por missão**; o robô (protocolo) exige maior que a do último aceito → **a 2ª missão de um robô era recusada para sempre** | ponta a ponta (passo 26) | sequência por robô (máxima emitida + 1) |
| `saas/services/storage.py` | dois envios simultâneos do mesmo conteúdo disputavam o mesmo `.part` (`FileNotFoundError`) | estresse com 6 robôs | temporário com nome único |
| `saas/services/edge_sync.py`, `device_protocol.py` | corrida no `asset` (mesmo cliente, mesmo hash) → `IntegrityError` (500) | estresse com 6 robôs | *savepoint*; quem perde fica deduplicado |
| `saas/migrations/0017` | `model_version.state` era `varchar(10)`; "descontinuado" não cabe → **migração quebrava no Postgres** | primeira migração num Postgres de verdade | a 0017 alarga a coluna antes de gravar |
| `saas/services/decision_engine.py` | com a Edge AI filtrando, a incidência contava só o que subiu (75 % contra 7,4 % das plantas) | ponta a ponta (passo 23) | incidência por planta para diagnóstico vindo da Edge AI |
| `saas/services/jobs.py` | dois workers podiam reivindicar o mesmo trabalho | revisão (F18) | *compare-and-set* + `SKIP LOCKED` |
| `rover/hal/local.py` | com cota, o disco era medido inteiro a cada leitura de saúde (~18 quadros/s com 40 mil quadros na missão) | estresse longo | medida em cache de 10 s, por `scandir`; a limpeza mede na hora |

### Simulado, pendente ou com ressalva — e por quê

- **Sem pesos reais** (Edge AI, IA de nuvem, dNATY sobre modelo real): critérios 10, 11
  e 20 ficam PARCIAIS. O modelo do simulador é `modelo_demo.onnx` (não agronômico); a IA
  de nuvem no ponta a ponta é o `SimulatedAnalyzer` (lê a marca `VTXSIM:` que a câmera
  simulada anexa ao JPEG). Os limiares da Edge AI precisam de calibração.
- **Fusão por planta**: o ponta a ponta usa a fusão **operacional** do SaaS (regra simples
  sobre Edge AI + diagnóstico da nuvem). A fusão **calibrada** e a **prescrição por planta**
  do `ia/` não estão ligadas ao SaaS (exigem o serviço de IA com pesos e `FIELDS_DIR`). O
  mapa de plantas vem do simulador; em campo é preciso georreferência/odometria por linha.
- **Drone** é cliente do protocolo, sem runtime nem hardware (critério 25 PARCIAL).
- **Telas**: o console ganhou o resultado da missão, OTA e otimizações, mas **não foram
  conferidos no navegador** nesta parte (só `tsc` + build + vitest); publicar OTA e
  registrar rodada de otimização continuam só pela API; não há tela para os registros
  brutos da Edge AI.
- **Infra**: *staging* de chunks compartilhado entre réplicas (o *multipart* do S3 exige
  partes de 5 MB — o caminho é um objeto por chunk), limite de taxa compartilhado (Redis),
  pacote OTA acima de 64 MB (`MAX_ASSET_MB`), cifra do disco e *secure boot* do robô,
  firmware OTA. A CI foi escrita e o YAML validado, mas **não rodou no GitHub** daqui.
- O `ack`/`complete` da missão pelo Rover não tem teste de reenvio após queda longa além
  do ponta a ponta (a fila é a mesma das outras chamadas, `mission_reports`).
- O `rover/` **não informa segmentos concluídos** (`/missions/{id}/segments/complete`): a
  tela da missão mostra "0 de N faixas" numa varredura concluída. Falta ligar o
  Mission Manager às faixas do plano (o comando assinado já as traz).
- **Desempenho do disco com cota** (corrigido no fim): medir a pasta a cada leitura de
  saúde derrubava a missão de ~100 para ~18 quadros/s com dezenas de milhares de arquivos
  (visto no estresse longo); agora a medida vale 10 s e a limpeza mede na hora.

### O que a PRÓXIMA rodada deve fazer, em ordem

1. Trazer os **pesos reais**: exportar ONNX + `categories.json`, registrar no registry com
   hash, rodar a etapa dNATY com o critério de aceite, publicar por OTA a um Rover de
   bancada; calibrar limiares.
2. Ligar o **serviço de IA** ao SaaS (fusão calibrada e prescrição por planta do `ia/`) e
   substituir a fusão operacional onde houver o serviço.
3. **Hardware**: adapters reais da HAL, mapa de plantas de campo, imagem do sistema do
   robô com `deploy/` e cifra do disco.
4. Infra de produção: Postgres gerenciado, S3 com *staging* por objeto, Redis para o
   limite, observabilidade; rodar a CI no GitHub.
5. Telas restantes (registros da Edge AI, publicar OTA/otimização pelo console) e conferir
   tudo no navegador (Playwright, como na Parte 3).

---

## Parte 4 (04/10/2026, ~01h–04h UTC)

### Números reais

| Suíte | Início (`d484d00`) | Fim |
| --- | --- | --- |
| SaaS — `pytest -o addopts="--strict-markers" -q` (3.11) | 685 passed (7 min 44 s) | **700 passed** (7 min 08 s): +14 `test_edge_sync.py`, +1 integração rover ↔ SaaS |
| SaaS — `ruff check .` | limpo | limpo |
| Rover — `cd rover && pytest` (3.11) | — (não existia) | **75 passed** (6,6 s) |
| Rover — `ruff check .` | — | limpo |
| Console — `npm ci && npm run build` / `npx vitest run` | verde / 67 passed | **não mexi no `web/`** (verde / 67 no início) |
| IA — `KERAS_BACKEND=torch pytest` (3.12) | 732 passed (2 min 27 s) | **não mexi no `ia/`** (só copiei dois arquivos dele) |

Migrações: do zero até a head (**0018**) e `downgrade -1` → 0017 → `upgrade` de novo, num
SQLite novo; `test_migrations.py` confere que o esquema migrado é o dos modelos. Postgres
continua não verificado.

**Volume (seção 13), medido em teste** (`rover/tests/test_retention.py`, bytes reais):
10.000 quadros com 2 % de eventos — enviar tudo: **6,04 GB**; com a política padrão:
**565 MB (9,4 %)**; com NORMAL só em metadados: **385 MB (6,4 %)**. Pipeline inteiro
(200 quadros, Edge AI de verdade): 18,9 MB → **1,89 MB** guardados (10,0 %).

### Feito

1. **Verificação da Parte 3** (`docs/VERIFICACAO.md`): suítes, migrações e os cinco itens
   conferidos no código. Nada a corrigir.
2. **Pacote `rover/`** na raiz (pyproject próprio, Python 3.11, depende só de numpy,
   pillow, onnxruntime e cryptography; não importa `saas/` nem `ia/` — há teste que
   confere). Detalhes em `docs/ROVER_RUNTIME.md`:
   - **HAL** (seções 20, 53): interfaces de câmera, GPS, IMU, sensores, armazenamento,
     rede, acelerador de IA e controlador; adapters reais genéricos (disco, HTTPS,
     *providers* do ONNX Runtime) e **simulados marcados** (câmera de pasta, GPS de
     trajetória com perda de sinal, rede que cai e volta / cai depois de N requisições);
   - **Edge AI** (seções 11, 14, 22): pré-processamento e runtime ONNX **copiados byte a
     byte** do `ia/` (teste compara os SHA-256), inferência, softmax, categorias NORMAL /
     POSSÍVEL PRAGA / POSSÍVEL DOENÇA / ANOMALIA e baixa confiança; metadados da seção 16
     em cada resultado (modelo, versão, SHA-256, dNATY, hardware, `simulated`);
   - **Rover Runtime** (seções 21, 54): Core, Mission Manager (com as cinco conferências
     do comando assinado), Model Manager (só modelo do registry, hash conferido antes de
     carregar, `MODEL_REJECTED` se não confere, missão não começa sem modelo), Event
     Engine (eventos da seção 40 com ID e hash), Telemetry e Health Monitor (horímetro,
     disco, temperatura, FPS/latência, falhas ativas), Configuration (`rover.json`, chave
     desconhecida é erro), Logging (JSON), CLI de serviço;
   - **Offline-first** (seção 12): SQLite WAL + `synchronous=FULL`, cada quadro numa
     transação, arquivo atômico antes do *commit*, boot que limpa órfãos e retoma a
     missão (`MISSION_RESUMED`). Testado: missão inteira sem rede; reinício no meio sem
     perder nem duplicar; queda dentro da transação não deixa quadro pela metade;
   - **Buffer circular** (seção 15) por câmera: antes/evento/depois, duração máxima,
     resolução e prioridade configuráveis; eventos sobrepostos;
   - **Retenção e três níveis** (seções 16, 17): por categoria, configurável no
     `rover.json`; amostra de validação 1 a cada N; limpeza que nunca apaga original de
     evento não enviado;
   - **Sync Engine** (seções 18, 19, 52): fila persistente com ID, hash, tamanho, chunks,
     progresso, prioridade, status, tentativas; *backoff* exponencial com *jitter*; `403`
     para tudo; **queda em 70 % retoma de 70 %** (com reinício no meio; cada chunk enviado
     exatamente uma vez); reenvio não duplica; `remaining` para a frota.
3. **SaaS** (seções 38, 39, 52): migração **0018** (`edge_record`, `edge_upload`),
   `POST /v1/device/edge/records` (idempotente por ID e hash; conflito e hash errado
   recusados), `POST/GET /v1/device/uploads`, `PUT .../chunks/{i}`, `POST .../complete`
   (retomada, conferência do hash do todo, dedup por hash, cota de armazenamento do
   plano, `ChunkStaging` como interface), `GET /v1/edge/records` para o cliente. Banco só
   com metadados; bytes no `ObjectStore`. 14 testes em `test_edge_sync.py`; o teste de
   isolamento gerado do OpenAPI ataca um upload real da vítima.
4. **Integração** (`saas/tests/test_rover_integracao.py`): o `rover/` com HAL simulada
   aceita a missão **assinada e despachada** pela plataforma, carrega o modelo designado
   pelo registry com hash conferido, perde a rede, continua, reinicia, volta, cai no meio
   de um arquivo, volta e sincroniza tudo — e um reenvio forçado não cria linha nova.
5. Docs: `docs/ROVER_RUNTIME.md`, `docs/SYNC.md`, `rover/README.md`,
   `saas/docs/DEVICE_PROTOCOL.md` (rotas novas), `docs/ARQUITETURA.md` (componentes C/D).

### Simulado, pendente ou com ressalva — e por quê

- **Sem pesos reais.** A Edge AI roda de verdade (ONNX Runtime), mas sobre um modelo
  minúsculo gerado no teste (média RGB → 3x4 → softmax). Os limiares de ANOMALIA (0,30) e
  baixa confiança (0,60) e o mapa rótulo → categoria **precisam ser calibrados com o
  modelo real**; o pacote do modelo deve trazer `<modelo>.categories.json`.
- **Hardware simulado**: câmera, GPS, IMU, sensores, controlador e a rede intermitente
  são simulação (marcada em cada resultado). Os adapters reais dependem da escolha do
  hardware (como plugar: `docs/ROVER_RUNTIME.md`, seção 7).
- No integração, o artefato do modelo foi posto na versão em PRODUÇÃO **direto no banco**
  (o ciclo de aprovação do registry tem testes próprios). O robô não baixa o artefato pela
  `artifact_uri`: ele chega por `ArtifactSource` (pasta) — o download assinado é do OTA.
- `region` (planta/região) vem nulo: não há mapa de plantas no robô ainda (o
  `region_resolver` é plugável).
- O *staging* de chunks é local (`LocalChunkStaging`): serve a um servidor só. Com vários
  servidores, implementar `ChunkStaging` sobre o *multipart upload* do S3. Não há limpeza
  de uploads abandonados (TTL) ainda.
- Os registros da Edge AI ficam em `edge_record` e ainda **não alimentam** a fusão por
  planta, a incidência nem o console (só `GET /v1/edge/records`). O caminho de hoje para a
  IA de nuvem continua o `POST /v1/device/observations`.
- O `saas/requirements-dev.txt` passou a instalar `-e ../rover[dev]` (para o teste de
  integração). A imagem Docker da plataforma não muda (usa só `requirements.txt`).

### O que a PARTE 5 deve fazer, em ordem

1. **dNATY** (seção 23): benchmark original × otimizado gravado no registry (campos já
   existem), comparação de precisão/recall/F1/latência/FPS/memória/tamanho, os dois
   artefatos separados; licença BSL 1.1 anotada. O robô já informa `dnaty_version` e o
   tipo do artefato em cada resultado.
2. **OTA** (seção 24): pacote assinado (Ed25519 da plataforma) com hash e versão, para
   modelo, Runtime e configuração; confirmação, *rollback* automático se o novo não sobe,
   logs. Entra como `ArtifactSource` do Model Manager e como gerenciador próprio no Core.
3. **Simulador único** (seção 41): `saas/simulator/` passa a montar o `rover/` com a HAL
   simulada — o mesmo Edge AI e o mesmo Sync Engine do robô real — no lugar do cliente
   próprio de hoje.
4. **Estresse** (seção 42): centenas de milhares de quadros, vários robôs e clientes,
   uploads simultâneos, rede intermitente, disco cheio, câmera indisponível, modelo
   inválido, OTA interrompido, backend fora, robô reiniciado — sem corromper a missão.
5. **Ponta a ponta** (seção 44): ligar `edge_record` à fusão por planta, incidência e
   prescrição (o evento da Edge AI vira observação/diagnóstico na nuvem), console
   mostrando ocorrências e arquivos; relatório da missão.
6. **Hardening** (seções 36, 43, 51): `ChunkStaging` sobre S3 multipart, TTL de uploads
   abandonados, `FOR UPDATE SKIP LOCKED` nos jobs, Postgres na CI, cifra do disco do robô,
   limite de taxa por dispositivo nas rotas de upload.
7. **Deploy** (seção 57): imagem do Rover (systemd/contêiner) com `rover.json`, identidade
   e diretório de dados; CI rodando `rover/`, `saas/` (com a integração), `ia/` e o
   console.

---

## Parte 3 (03/10/2026, ~19h–20h UTC)

### Números reais

| Suíte | Início (`32619e3`) | Fim |
| --- | --- | --- |
| SaaS — `pytest -o addopts="--strict-markers" -q` | 620 passed (5 min 59 s) | **685 passed** (6 min 59 s) |
| SaaS — `ruff check .` | limpo | limpo |
| Console — `npm ci && npm run build` | verde | verde |
| Console — `npx vitest run` | 58 passed (6 arquivos) | **67 passed** (7 arquivos) |
| IA — `ia/` | 732 passed (Parte 2) | **não mexi no `ia/`**; não rodei de novo |
| Navegador (Playwright, API real servindo o build) | — | `web/e2e/frota-e-ia.mjs`: **6 de 6 passos ok** |

Migrações: do zero até a head (**0017**) num SQLite novo, ida e volta de 0016 e
0017 com dado (os estados antigos de `model_version` vão para os novos e voltam)
— em teste (`test_frota.py`, `test_model_registry.py`, `test_migrations.py`).
Postgres continua não verificado (sem `TEST_DATABASE_URL` aqui).

### Feito

1. **CPF/CNPJ mascarado na API** (decisão do Pedro). Quem tem `farm:manage` recebe
   o documento inteiro; os demais papéis recebem `***.***.***-12` (ou
   `**.***.***/****-12`) e `owner_document_masked: true` — o operador nunca recebe o
   número, mesmo que a tela quisesse. Leitura do completo pela equipe da ValTexa
   (sessão de suporte **assistida**, que age como gestor) grava
   `farm.owner_document_viewed` na trilha do cliente, ligada à sessão de suporte; em
   modo leitura o suporte vê mascarado. A trilha de edição (`farm.updated`) passou a
   guardar o documento mascarado: ela não se apaga, e o documento vive na fazenda
   (o teste da Parte 2 que esperava o número inteiro na trilha foi ajustado a isso).
   `services/documentos.mascarar_cpf_cnpj`, `api/routers/farms.py`; 9 testes novos em
   `test_fazenda_completa.py`.
2. **F6 — Frota** (seções 22, 25, 26):
   - `services/fleet_state.py`: os sete estados **derivados**, função pura com
     `now` injetável, precedência documentada (suspenso/aposentado/sem credencial →
     BLOQUEADO; manutenção → MANUTENÇÃO; sem contato > 5 min → OFFLINE; falha na
     última telemetria → ERRO; missão ativa → EM MISSÃO; `remaining > 0` no último
     `/sync` → SINCRONIZANDO; senão DISPONÍVEL), com o motivo em português;
   - protocolo: `POST /v1/device/session` aceita as versões (runtime, Edge AI,
     modelo, dNATY, firmware, hardware) — campo ausente não apaga, troca auditada
     como `device.versions_reported` com ator = dispositivo; telemetria ganhou
     `storage_total_bytes`, `storage_free_bytes`, `operating_hours` (horímetro só
     sobe) e as falhas da amostra mais recente viram `active_faults`; `/sync` ganhou
     `remaining`; lote antigo (sequência abaixo da marca d'água) não volta o retrato;
   - `DeviceOut` com estado, motivo, versões, saúde, última sincronização, última
     manutenção (gravada ao sair de MANUTENÇÃO, com `maintenance_note`) e
     `model_status` (conforme/divergente/fora_do_registry/sem_dado) contra os
     modelos que o registry designa ao robô;
   - `GET /v1/platform/fleet` (Operações, Suporte, IA & Dados, superadmin): todos os
     robôs com o cliente dono, filtro por cliente, estado e "modelo diferente do
     designado"; comercial → 403;
   - migração **0016**; 32 testes em `tests/test_frota.py` (inclui dois rovers na
     mesma fazenda, cada um com a sua missão despachada).
3. **F7 — AI Platform e Model Registry** (seções 8, 9, 10, 22, 34):
   - `model_version` (já existia, sem uso) ganhou os campos da seção 9: nome,
     culturas, problema, arquitetura, dataset (FK ou referência externa), data de
     treino, métricas, tamanho, FLOPs, latência, memória, hardware-alvo, artefato
     **original e otimizado separados** (URI + SHA-256 cada), versão do dNATY,
     variante, recomendada, licença, ressalva, escopo de liberação, quem registrou,
     quem aprovou e quando, data de publicação; estados TREINAMENTO → VALIDAÇÃO →
     APROVADO → STAGING → PRODUÇÃO → DESCONTINUADO (os antigos são migrados);
   - `services/model_registry.py`: transições válidas (com volta para reprovação e
     saída para DESCONTINUADO), motivo obrigatório ao reprovar/descontinuar,
     **aprovação só por `ia_dados`/`superadmin` e nunca por quem registrou** (403),
     aprovar exige métrica, publicar exige artefato com hash e **descontinua a
     anterior da mesma chave** (no máximo uma em PRODUÇÃO), descontinuar a única
     versão que um talhão escolheu é recusado (409), métrica e artefato congelam
     depois da aprovação; tudo auditado (`model_version.registered`, `.transition`,
     `.updated`);
   - liberação por cliente (`model_release`, migração **0017**): versão com
     `release_scope = clientes` só atende os clientes liberados; liberar é
     idempotente, revogar guarda histórico; o talhão só escolhe entre as versões em
     PRODUÇÃO liberadas para o cliente (422 fora disso);
   - **o catálogo duplicado em `ai_pipeline.py` saiu**: virou `CATALOGO_INICIAL` do
     registry (cadastrado no start da API, no seed e no simulador; só cria o que
     falta, nunca desfaz o que a equipe mudou) e `resolve_model` lê o registry. As
     chaves continuam as que a IA conhece (`banana-foliar`, `citrus-foliar-cc`...),
     então o que a IA devolve segue compatível;
   - `GET /v1/device/models`: o robô pergunta o que deve rodar e só recebe versão
     em PRODUÇÃO do registry, com o hash do artefato (otimizado quando houver);
   - produtor vê linguagem operacional: `GET /v1/fields/{id}/ai-models` perdeu
     `field_accuracy` (número técnico) e ganhou `field_performance` (alto/bom/
     limitado), `name` e `version`; métrica, FLOPs, hash e dataset só em
     `/v1/platform/models` (`platform:model:read`);
   - `GET /v1/platform/ai-health`: modelos ativos, inferências por modelo/versão,
     taxa de erro, abstenções, latência média e p95, distribuição de rótulos (tudo
     medido nas detecções gravadas, com **simulação marcada**), robôs informando,
     divergentes, fora do registry, sem dado, versões descontinuadas em uso; e
     `no_data` com o motivo para drift, incidentes, FPS e performance em produção;
   - 26 testes em `tests/test_model_registry.py`; os testes antigos do catálogo
     (`test_ia_banana_citros.py`, `test_decision_and_pipeline.py`) passaram a ler o
     registry pela fixture `registry`; o teste de isolamento/escalada gerado do
     OpenAPI cobre as rotas novas sozinho (só ganhou os ids de mentira
     `model_version_id` e `release_id`).
4. **Console** (`saas/web`):
   - cliente: Frota com o estado de cada robô e o motivo, resumo por estado, modelo
     em uso e conformidade; no detalhe do robô, o cartão "Frota" com versões, saúde
     e "sem dado" onde o robô ainda não informou; seletor de modelo do talhão com
     versão e desempenho operacional;
   - plataforma: **Frota** (`/plataforma/frota`) e **IA e modelos**
     (`/plataforma/ia`: registry agrupado por modelo, detalhe com todos os campos,
     histórico e botões de transição com motivo; liberação por cliente; saúde da
     IA) — no menu pela capacidade;
   - `lib/fleet.ts` com 8 testes; teste do menu atualizado (Operações incluída).
5. Docs: `saas/docs/DEVICE_PROTOCOL.md` (sessão com versões, `/device/models`,
   `remaining`, estado derivado), `saas/docs/API.md` (frota, registry, CPF
   mascarado), `saas/docs/AI_PIPELINE.md` (resolução pelo registry).

### Simulado, pendente ou com ressalva — e por quê

- **Pesos não estão aqui.** As 8 versões do catálogo inicial entram no registry
  com versão provisória `1.0.0` e **sem artefato, hash, FLOPs, latência nem
  memória** — o console mostra "sem dado", e `GET /v1/device/models` devolve hash
  nulo (o robô não carrega nada). A equipe de IA preenche com o modelo real
  (registrando versão nova, que passa pelo ciclo). As acurácias de campo vieram do
  `VALTEXA-B/MODELS.md` via o espelho antigo.
- **Inferência real não rodou**: a saúde da IA nos testes e na demo mostra o
  analisador simulado, marcado como `simulated`.
- **Drift, incidentes, FPS e precisão em produção** aparecem como "sem dado" com o
  motivo: não há fonte para eles na plataforma ainda (drift precisa da distribuição
  do treino, que vive com os pesos; FPS vem com o Rover Runtime da Parte 4).
- **Horas de operação** são o horímetro que o robô informa; a plataforma não
  estima por conta própria. Sem horímetro, "sem dado".
- `designados()` resolve o modelo talhão a talhão; com cache por (cliente,
  fazenda) dentro de uma requisição. Para milhares de robôs vale materializar
  (F18).
- Manutenção pela equipe de Operações (sem sessão de suporte) não foi feita: hoje
  pôr em manutenção é do cliente (`device:manage`) ou do suporte assistido. Decidir
  com o Pedro se Operações ganha uma rota própria, como a "missão assistida".
- O roteiro de navegador fica fora do `npm test` (Playwright não é dependência);
  o banco dele sai de `web/e2e/prepara_frota_e_ia.py`. Nesta nuvem:
  `CHROMIUM_PATH=/opt/pw-browsers/chromium-1194/chrome-linux/chrome`.

### O que a PARTE 4 deve fazer, em ordem

1. **Pacote `rover/`** (separado, sem importar `saas/`), com testes próprios:
   - **Edge AI** reaproveitando `ia/app/inference` + `onnx_runtime` (sem tocar nos
     arquivos de terreno), com o dublê do modelo nos testes e a anotação "a
     verificar com o modelo real";
   - **Rover Runtime**: Mission Manager, Model Manager (pergunta
     `GET /v1/device/models`, confere o SHA-256 antes de carregar, nunca carrega
     modelo fora do registry, informa as versões em `POST /v1/device/session`),
     Health Monitor (temperatura, armazenamento, horímetro, falhas → telemetria),
     Configuration Manager, Logging;
   - **HAL** com adapters simulados, marcados como simulação;
   - **offline-first**: a missão continua sem rede; armazenamento local;
   - **buffer circular** (antes/evento/depois, configurável) e **política de
     retenção** NORMAL/PRAGA/DOENÇA/ANOMALIA (seções 15–17);
   - **Sync Engine** com fila persistente, hash, chunks, retomada do ponto em que
     parou, prioridade da seção 19 e o `remaining` do `/sync` (já aceito pelo
     servidor) para a frota mostrar SINCRONIZANDO.
2. **Rotas de upload do robô no SaaS**, idempotentes por hash (chunk + manifesto),
   com a cota de armazenamento do plano aplicada.
3. Depois (F12–F19): benchmark dNATY original × otimizado gravado no registry
   (campos já existem: artefato otimizado, `dnaty_version`, métricas); OTA assinado
   com rollback; simulador com o mesmo Edge AI e protocolo; estresse, ponta a
   ponta, hardening (`FOR UPDATE SKIP LOCKED`), Postgres na CI.
4. Pendências do console/cliente que continuam: convite por e-mail com aceite;
   repasse de incidência e prescrição da IA; rota de Operações para missão e
   manutenção assistidas (decidir com o Pedro).

---

## Parte 2 — segunda execução (03/10/2026, ~11h UTC)

O agendamento disparou a Parte 2 de novo, e ela já estava feita (commits de 01:43 a
02:01 UTC). Esta execução **não refez** nada: verificou, corrigiu e fechou pendências.

### Números reais

| Suíte | Início (`efa0d1b`) | Fim (`b1f2707`) |
| --- | --- | --- |
| SaaS — `pytest` | 596 passed (6 min 02 s) | **620 passed** (5 min 04 s) |
| SaaS — `ruff check .` | limpo | limpo |
| Console — `npm ci && npm run build` | verde | verde |
| Console — `npx vitest run` | 42 passed (4 arquivos) | **58 passed** (6 arquivos) |
| IA — `KERAS_BACKEND=torch pytest` (3.12) | 732 passed (2 min 03 s) | sem mudança no `ia/` |
| IA — `ruff check .` | os 5 erros dos arquivos de terreno | os mesmos 5 |
| Navegador (Playwright, API real servindo o build) | — | `web/e2e/conta-e-fazenda.mjs`: 8 de 8 passos ok |

Nota: o `-q` do `addopts` somado a outro `-q` esconde a linha de total; rode com
`-o addopts="--strict-markers" -q` para contar. Migrações: do zero até a head (**0015**)
num SQLite novo, `downgrade -1` e de volta, sem erro. Postgres não verificado.

### Feito
1. **Corrigido:** Configurações do cliente tinha uma aba "Plataforma" com o endereço
   interno da IA e as pendências de configuração por extenso, e o `/health` sem
   autenticação expunha o mesmo a qualquer um (seções 30 e 43). Agora o `/health` diz
   só *se* está bom (mesmos campos, sem detalhe); o detalhe vai para
   `GET /v1/platform/health` e para a tela **Saúde do sistema** em `/plataforma/saude`.
2. **Configurações do cliente** (rotas já existiam): *Meu plano* (uso × limite, aviso a
   80 % e a 100 %, funcionalidades, estado vazio), *Dados no treino* (SIM/NÃO explícito,
   só o dono, histórico com quem e quando) e *Acessos da ValTexa* (cada entrada da
   equipe com motivo, chamado, modo, ações e situação).
3. **Fazenda completa** (seção 5): produtor, CPF/CNPJ com dígito verificador (servidor e
   tela), município, UF, cultura principal, recibo do CAR, responsável técnico e
   observações — migração **0015**, `PATCH` auditado com antes/depois, "cadastro
   incompleto: …" com o botão **Completar cadastro**. O CPF/CNPJ não sai pelas
   ferramentas internas (`/v1/admin/farms`).

### Ressalvas e decisões para o Pedro
- O CPF/CNPJ do produtor aparece para **todo papel do cliente** (operador inclusive),
  como o resto do cadastro da fazenda. Se a LGPD pedir menos, mascarar para quem não
  tem `farm:manage`.
- Inferência real continua não rodando (pesos fora do repositório): SaaS com
  `SIMULATED_INFERENCE`, IA com o dublê do `tests/conftest.py`.
- O roteiro de navegador precisa de `CHROMIUM_PATH=/opt/pw-browsers/chromium` nesta
  nuvem (o Playwright do npm pede outra versão do navegador). Fora do `npm test`.

## Parte 2 (02–03/10/2026)

### Números reais (última execução desta sessão)

| Suíte | Fim da Parte 1 | Fim da Parte 2 |
| --- | --- | --- |
| SaaS — `cd saas && pytest` | 564 passed | **596 passed** (6 min 01 s) |
| SaaS — `ruff check .` | limpo | **limpo** |
| Console — `npm ci && npm run build` | verde | **verde** |
| Console — `npx vitest run` | 14 passed | **42 passed** (4 arquivos) |
| IA — `KERAS_BACKEND=torch pytest` (Python 3.12) | 703 passed | **732 passed** |
| IA — `ruff check .` | 5 erros (terreno, intocáveis) | os mesmos 5 |
| Navegador (Playwright, contra a API real) | — | `web/e2e/console-plataforma.mjs` (8 passos) e `web/e2e/cadastro-talhao.mjs` (4 passos): todos ok |

Os roteiros de navegador rodam contra a API servindo o build, num SQLite novo com
o seed de demonstração. Não fazem parte do `npm test`, porque o Playwright não é
dependência do console (ver o cabeçalho dos arquivos).

### O que foi feito

1. **Verificação da Parte 1** (`docs/VERIFICACAO.md`). Rodei as suítes e as
   migrações (do zero até 0013, de volta até 0009 e de novo até a head) e conferi o
   código item a item. Duas lacunas reais foram corrigidas:
   - os recursos do plano eram gravados e não valiam: agora `lavoura_3d` fora do
     plano → 402 nas rotas 3D;
   - com `REVIEW_DIR` ligado, a IA punha quadro de cliente **sem consentimento** na
     fila que vira dataset. Agora o SaaS manda `X-Training-Consent: 0|1` em toda
     chamada e a IA respeita.
2. **Pendências da Fase 2**:
   - limite de tentativas de login por conta e por IP, contado no banco (migração
     **0014**, 429 com `Retry-After`; nem a senha certa entra durante o bloqueio);
   - token de serviço SaaS→IA (`SERVICE_TOKEN` na IA, `INFERENCE_SERVICE_TOKEN` no
     SaaS; produção não sobe sem ele). A IA deixou de ser aberta.
3. **Fase 3 — console interno `/plataforma`** (`saas/web/src/platform/`):
   - layout e cor próprios (índigo, faixa no topo "ValTexa · equipe interna");
   - menu pelo papel de plataforma: Clientes (plano, assinatura, uso × limite com
     aviso a 80%, consentimento, pessoas, sessões abertas), Cadastro e contrato,
     Usuários globais (busca, vínculos, papel de plataforma, bloqueio com motivo),
     Auditoria global (trilha com filtro e "Entradas em clientes") e as
     ferramentas internas (gerar missão, importar coleta, coletas, dataset);
   - **Entrar como cliente**: motivo obrigatório, chamado, prazo, leitura por padrão
     e assistido explícito com motivo próprio. A **faixa** aparece no topo de toda
     tela do cliente com cliente, modo, minutos restantes e motivo, e dela se liga
     ou desliga o assistido e se **sai**. Ao sair, a pessoa volta ao console da
     plataforma. Suporte vencido derruba só o suporte, não o login da equipe;
   - o grupo "ValTexa" saiu do menu do cliente, `/admin/*` redireciona para
     `/plataforma/*`, e equipe sem sessão de suporte que cai no console do cliente
     é levada ao da plataforma;
   - backend novo, com testes: `/v1/platform/me`, `/v1/platform/tenants`,
     `/v1/platform/accounts` (+ `PUT .../active`), `/v1/admin/farms` e
     `/v1/admin/fields` (cadastro do cliente em foco para as ferramentas, sem
     resultado agronômico), capacidade nova `platform:user:read`. Todas entram
     sozinhas no teste de escalada gerado do OpenAPI.
4. **Fase 5 (parte) — cadastros do cliente**:
   - talhão com espaçamento entre linhas e entre plantas, número de linhas,
     fileiras de validação (aceita "3-5, 20" e recusa linha além do total) e
     observações, na criação e num cartão "Cadastro do talhão" com edição;
   - estados vazios com a próxima ação: sem fazenda → cadastrar; fazenda sem talhão
     → desenhar o primeiro; talhão incompleto → o que falta e o botão que resolve.

### Simulado, incompleto ou com ressalva — e por quê

- **Inferência real não rodou** em nenhum teste: os pesos não estão no repositório.
  O SaaS usa `SIMULATED_INFERENCE`, e a IA usa o dublê de `ia/tests/conftest.py`.
  Nada desta parte depende do modelo real.
- **Gerar missão** no console da plataforma lê o talhão pela rota de plataforma, mas
  **criar** a missão é escrita no cliente: para quem não é membro, ela exige sessão
  de suporte em modo assistido. O servidor recusa com a mensagem que diz isso.
  Decidir com o Pedro se Operações ganha uma rota de "missão assistida" própria.
- **Fazenda** não ganhou campos novos (produtor, CPF/CNPJ, CAR, responsável
  técnico): o prompt pedia os do talhão. **Feito na segunda execução** (migração 0015).
- O seed de demonstração não assina plano para a "Fazenda Demonstração" (a
  migração 0011 assina o `piloto` só para clientes que já existiam). O console
  mostra "Sem plano", que é o comportamento correto para cliente sem assinatura.
- **Não rodei em Postgres** (não há `TEST_DATABASE_URL` aqui): as migrações
  0010–0014 foram verificadas só em SQLite.
- Os roteiros Playwright ficam fora do `npm test`. Pendente: ligá-los na CI com o
  backend subindo junto.
- A branch local `backup/parte1-duplicada` (não enviada) guarda a Fase 2 que esta
  sessão refez enquanto a Parte 1 ainda rodava em outra sessão. Pode ser descartada.

## O que a PARTE 3 deve fazer, em ordem (brief, seção 60)

1. **F6 — Frota**: estados da seção 25 (DISPONÍVEL, EM MISSÃO, SINCRONIZANDO,
   MANUTENÇÃO, OFFLINE, BLOQUEADO, ERRO) derivados do protocolo; versões de runtime,
   Edge AI, modelo e dNATY por dispositivo; horas de operação, última sincronização;
   tela de frota no console da plataforma (Operações) e no do cliente.
2. **F7 — AI Platform e Model Registry**: `model_version` com os campos da seção 9 e
   os estados TREINAMENTO → VALIDAÇÃO → APROVADO → STAGING → PRODUÇÃO →
   DESCONTINUADO, com transições auditadas e aprovação; original × otimizado;
   liberação por cliente; o catálogo duplicado em `ai_pipeline.py` passa a ler o
   registry; a tela "IA" no console da plataforma (seção 34: saúde da IA).
3. **F8–F11 — pacote `rover/`** (separado, sem importar `saas/`): Edge AI
   reaproveitando `ia/app/inference` + `onnx_runtime`; Rover Runtime (Mission
   Manager, Model Manager, Health, Config); HAL com adapters simulados e marcados
   como simulação; **offline-first** (a missão continua sem rede); armazenamento
   local; **buffer circular** (antes/evento/depois, configurável); política de
   retenção NORMAL/PRAGA/DOENÇA/ANOMALIA; **Sync Engine** com fila, hash, chunks,
   retomada do ponto em que parou e prioridade da seção 19. As rotas novas de upload
   do robô no SaaS, idempotentes por hash.
4. **F12 — dNATY**: benchmark original × otimizado (precisão, recall, F1, latência,
   memória, tamanho) gravado no registry. Licença BSL 1.1: uso comercial pede
   licença própria.
5. **F13 — OTA**: pacote assinado (hash + assinatura), versionamento, confirmação,
   rollback automático e logs, para runtime, Edge AI, modelos e configuração.
6. **F14 — simulador** com o mesmo Edge AI e o mesmo protocolo do `rover/` (o
   simulador atual vira adapters `sim/` do pacote).
7. **F15–F19**: testes unitários e integrados do `rover/`; estresse da seção 42
   (milhares de imagens, vários robôs, conexão intermitente, storage cheio, backend
   fora); ponta a ponta da seção 44 (cliente → … → relatório) contra o simulador;
   hardening da seção 43 (sessões, upload, storage, endpoints do robô;
   `FOR UPDATE SKIP LOCKED` na fila); deploy (Postgres na CI, `TEST_DATABASE_URL`,
   object storage, segredos).
8. Ainda da Fase 5 e do console do cliente: convite por e-mail com aceite (hoje
   associa conta existente direto); repasse de incidência e prescrição da IA;
   "missão assistida" para Operações (decidir com o Pedro). Já feitos na segunda
   execução da Parte 2: campos da fazenda, Meu plano, consentimento e acessos da
   ValTexa em Configurações.

---

## Parte 1 (02/10/2026) — registro original

> O texto abaixo é o da Parte 1, mantido como estava. A lista "O que a PARTE 2
> deve fazer" foi atendida nos itens 1, 2 (parte), 3 e 4 (parte), conforme acima.

## Números reais (execução desta sessão)

| Suíte | Antes (main) | Agora (esta branch) |
| --- | --- | --- |
| SaaS — `cd saas && python -m pytest` (SQLite) | 484 passed (3 min 41 s) | **564 passed** (5 min 06 s) |
| SaaS — `ruff check .` | limpo | **limpo** |
| Console — `npm ci && npm run build` | verde | **verde** (com `schema.d.ts` regenerado do OpenAPI novo) |
| Console — `npx vitest run` | 14 passed | **14 passed** |
| IA — `KERAS_BACKEND=torch python -m pytest` (Python 3.12) | 703 passed (6 min 23 s) | sem mudança no `ia/` nesta parte |
| IA — `ruff check .` | 5 erros, todos nos arquivos de terreno intocáveis | idem |

Ambiente: o `pytest` puro em `saas/` falhava na coleta (faltava `pythonpath`);
corrigido no `pyproject.toml`. A IA exige Python ≥ 3.12 (`numpy==2.5.3`); o
índice CPU do PyTorch está bloqueado na rede desta nuvem, o torch veio do PyPI.
**Não rodei a suíte em Postgres** (sem `TEST_DATABASE_URL` aqui): as migrações
0010–0013 foram verificadas só em SQLite (ida, volta e dados).

## O que foi feito

### 1. Fase 0 — auditoria: `docs/AUDITORIA.md`
Os 10 itens da seção 66, sobre o código: arquitetura atual (mermaid), stack, as
128 operações do OpenAPI por tipo de chamador, o que funciona, o que é simulado,
11 problemas críticos (o mais grave: acesso silencioso da equipe como `admin` em
qualquer cliente — corrigido nesta parte), o que separar e o plano.

### 2. Fase 1 — arquitetura alvo: `docs/ARQUITETURA.md`
Componentes A–G mapeados para pastas reais (`saas/`, `ia/`, e o pacote novo
`rover/` para Rover Runtime + Edge AI, com a estrutura proposta), contratos
Rover↔Backend, SaaS↔Backend, AI Platform↔Backend e Fleet↔Rover, modelo de dados
alvo (seção 37), armazenamento, eventos (seção 40, com os nomes do brief como
alias dos atuais), idempotência (seção 52) e a migração F0–F19.

### 3. Fase 2 — backend, banco, autenticação e multi-tenancy (`saas/`)

| Item | O que existe agora | Arquivos |
| --- | --- | --- |
| a) papéis de plataforma | `User.platform_role` (superadmin, suporte, ia_dados, operacoes, comercial); migração **0010** leva `is_platform_admin=true` → `superadmin` e remove a coluna (a propriedade `is_platform_admin` continua, derivada); capacidades por papel (`PLATFORM_ROLE_CAPABILITIES`); toda rota `/v1/admin/**` exige a capacidade dela; `/v1/platform/users` e `PUT .../platform-role` (só superadmin; derruba as sessões de quem perde papel) | `models/enums.py`, `models/tenancy.py`, `security/rbac.py`, `api/deps.py` (`require_platform`, `require_platform_in_tenant`), `api/routers/admin.py`, `api/routers/platform.py`, `migrations/versions/0010_*` |
| b) entrar como cliente | `SupportSession`: motivo obrigatório, prazo 5 min–8 h, **leitura por padrão** (todo método não seguro → 403), modo assistido explícito com motivo (age como gestor, sem aprovar aplicação), **toda requisição auditada** no cliente (`support.request`/`support.request_denied`) com o interno, escrita leva `audit_entry.support_session_id`, saída registrada (`saiu`/`expirou`/encerrada por), token derrubado na hora; o cliente vê as sessões em `/v1/tenants/current/support-sessions`; `/auth/me` traz `support_session` para a faixa. **Equipe sem associação não lê nem escreve em cliente sem sessão de suporte** (fim do acesso silencioso). Só o dono dá/muda/tira papel de dono | `services/support_sessions.py`, `api/deps.py`, `api/routers/platform.py`, `api/routers/auth.py`, `services/audit.py`, `models/platform_.py` |
| c) planos | `Plan`, `Subscription`, `UsageCounter`; migração **0011** cria o plano `piloto` (sem limites) e assina todo cliente existente nele, copiando `contracted_service` para `subscription.notes` (a coluna antiga fica); catálogo inicial `essencial`/`profissional`/`empresarial` com **valores provisórios**; limites verificados em criar fazenda, talhão (e hectares, também ao redesenhar contorno), convite **e** provisionamento de robô, usuário e missão (contador mensal): `409` com a conta em português, `402` para assinatura suspensa/cancelada/vencida; rotas `/v1/admin/plans`, `/v1/admin/tenants/{id}/subscription`, `/v1/tenants/current/plan`; cadastro de cliente aceita `plan_code` | `models/commercial.py`, `services/plans.py`, `api/routers/plans_api.py`, `farms.py`, `fleet.py`, `missions.py`, `auth.py`, `admin.py`, `main.py`, `migrations/versions/0011_*` |
| d) consentimento | `DataConsent` (histórico, padrão NÃO, quem/quando/origem); dono decide em `PUT /v1/tenants/current/data-consent`; ValTexa registra termo em `PUT /v1/admin/tenants/{id}/data-consent` (exige documento); `dataset.record_review` **e** `freeze_version` só aceitam amostra de cliente com SIM vigente; revogar exclui as amostras (`EXCLUDED`, com nota) — migração **0012** | `services/consent.py`, `services/dataset.py`, `api/routers/consent_api.py` |
| e) talhão | `plant_spacing_m`, `row_count`, `validation_rows`, `notes` (migração **0013**); `PATCH /v1/fields/{id}` parcial e auditado; fileira validada contra o nº de linhas | `models/farm.py`, `schemas.py`, `api/routers/farms.py` |
| f) isolamento e escalada | `tests/test_isolamento_openapi.py`: classifica **todas** as 147 operações de `app.openapi()` (rota sem classe reprova); outro cliente com 3 papéis ataca toda rota de cliente com os ids da vítima (267 chamadas: 124×404, 59×403, 1×422; nenhum 2xx com id da vítima) e o estado da vítima em toda tabela com `tenant_id` fica idêntico; robô de outro cliente não alcança a vítima; os 7 papéis de cliente batem em toda rota de plataforma → 403; sessão de suporte em leitura → 403 em toda escrita | `tests/test_isolamento_openapi.py` |

Testes novos: `test_plataforma_e_suporte.py` (39), `test_planos.py`,
`test_consentimento.py`, `test_talhao_completo.py`, `test_isolamento_openapi.py`.
Testes antigos ajustados à regra nova (a equipe lê a trilha de cliente pela
auditoria da plataforma; onboarding completo informa `plan_code`; a fixture do
dataset registra consentimento): `test_cadastro.py`, `test_edicao_de_rota.py`,
`test_collections.py`.

Docs atualizadas: `saas/docs/AUTHENTICATION.md`, `saas/docs/API.md`,
`saas/README.md`, `docs/AUDITORIA.md`.

## O que ficou incompleto, simulado ou com ressalva — e por quê

1. **Console sem as telas novas.** A API mudou; o console (`saas/web`) compila com
   os tipos regenerados, mas **não tem** telas de sessão de suporte (abrir, faixa,
   modo, sair), planos e uso, consentimento nem papéis de plataforma. **Efeito
   visível:** a equipe da ValTexa que abria páginas de cliente sem ser membro
   agora recebe 403 com a orientação de abrir sessão de suporte — é a regra do
   brief, mas a tela para isso é da Parte 2. As páginas `admin/*` continuam
   funcionando (rotas de plataforma).
2. **Inferência real não roda aqui**: pesos fora do repositório; toda a suíte usa
   `SIMULATED_INFERENCE` e o dublê do `ia/tests/conftest.py`. Nada desta parte
   depende de modelo.
3. **Planos**: valores de `essencial`/`profissional`/`empresarial` provisórios
   (decisão comercial do Pedro); **armazenamento** e **retenção** são medidos e
   mostrados, não aplicados (upload e worker de retenção são F10/F11);
   `features` do plano é guardado e não é conferido em rota nenhuma ainda; convite
   de robô pendente não conta contra o limite (conferido de novo no
   provisionamento); `tenant.contracted_service` continua na tabela (sai quando o
   console parar de usá-lo).
4. **Consentimento**: revogar exclui amostras de cortes futuros, mas os cortes já
   congelados guardam a lista de ids (reprodutibilidade) e modelos já treinados
   não "desaprendem" — decisão de LGPD pendente para o Pedro.
5. **Auditoria da sessão de suporte grava toda requisição**, leitura inclusive
   (uma linha por chamada) — é o que o brief pede ("ações"); se o volume
   incomodar, agregar por minuto na F18.
6. **Riscos ainda abertos** (da auditoria): IA sem autenticação entre SaaS e IA;
   login sem limitação de tentativas; convite que associa conta existente sem
   aceite; SQLite padrão; inferência síncrona na requisição do robô; resíduo
   duplicado na raiz (`app/`, `tests/`, `pyproject.toml` = cópia de
   `ia/app/active_learning.py`) — não removido sem o Pedro confirmar.
7. A demo (`equipe@valtexa.dev`) continua **membro** do cliente de demonstração
   (é a conta dos testes); a equipe real (`PLATFORM_TEAM`) não tem associação.

## O que a PARTE 2 deve fazer, em ordem

1. **F3 — console interno `/plataforma`** (`saas/web`): entrar como cliente
   (motivo, prazo, ticket), **faixa** visível com modo e prazo, ligar/desligar
   assistido, sair; papéis da equipe (superadmin); planos e uso por cliente;
   registro de consentimento por termo; auditoria global e sessões de suporte.
   No console do cliente: tratar o 403 "abra sessão de suporte" para a equipe.
   Testes vitest dos componentes novos.
2. **F4 — console do cliente**: "Meu plano" (uso × limite, aviso a 80%),
   consentimento SIM/NÃO em Configurações (só o dono), "quando a ValTexa
   entrou" (sessões de suporte), talhão com os campos novos (espaçamento entre
   plantas, linhas, fileiras de validação, observações).
3. **Hardening rápido (F18 adiantado)**: limitação de tentativas no
   `/v1/auth/login`; token de serviço SaaS→IA (`AI_SERVICE_TOKEN`, opcional até
   ligar em produção) nas rotas do `ia/`; convite por e-mail com aceite no lugar
   de associar conta existente direto.
4. **F5 — fluxo agrícola**: repasse de `/fields/{id}/incidence` e
   `/fields/{id}/prescription` da IA; mandar `plant_spacing_m`/`row_spacing_m` do
   talhão no `/predict/rover-frame` (VALTEXA-B, `rover_api` + `plant_fusion` —
   sem tocar nos arquivos de terreno); `plant_region`; prescrição → aprovação →
   aplicação → verificação → relatório, sem apagar histórico.
5. **F6 — Fleet**: estados da seção 25 e versões (runtime, modelo, dNATY) no
   dispositivo.
6. **F7 — Model Registry** com estados TREINAMENTO→…→DESCONTINUADO, aprovação,
   original × otimizado; liberação por cliente.
7. **F8–F11 — pacote `rover/`** (Edge AI reusando `ia/app/inference` +
   `onnx_runtime`, Runtime, HAL com adapters simulados marcados, storage local,
   buffer circular, política de retenção, Sync Engine com prioridade/chunks/hash) e
   as rotas novas de upload do robô.
8. Depois: Idempotency-Key nas criações do console, cota de armazenamento e
   retenção por plano aplicadas, remoção de `contracted_service`, suíte em
   Postgres, limpeza do resíduo na raiz (com o Pedro).
