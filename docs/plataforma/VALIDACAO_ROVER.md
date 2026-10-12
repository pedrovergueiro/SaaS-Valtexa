# Validação do Rover V3 — ensaios automáticos, veredito e portões

> Rodada 3, Parte 11 (08/10/2026). A Parte 10 (que deveria ter criado este documento, o
> catálogo e os portões) **não estava na branch**; a base foi construída aqui junto com os
> testes automáticos. Guia de campo com as fases e o que comprar:
> <https://claude.ai/artifact/KiKdRqL7X6i9Cf73s4TdDn>.

**Tudo o que está aqui foi testado com a bancada SIMULADA. Nenhum ensaio rodou em
hardware ainda** — cada um diz no laudo (`observacao`) o que falta conferir na peça real.

## 1. Como funciona

```
console (aba Validação)  ──POST /v1/platform/rovers/{id}/ensaios──▶  plataforma
                                                                       │ valida limites (só apertar)
                                                                       │ assina o comando "ensaio" (Ed25519,
                                                                       │ sequência própria, validade 2 min)
robô  ◀──GET /v1/device/commands──────────────────────────────────────┘
  │ confere assinatura, destinatário, prazo e sequência (repetido/forjado = recusado)
  │ recusa se houver missão em curso ou outro ensaio rodando
  │ roda numa thread (o laço do Runtime segue: telemetria, comandos, controle remoto)
  ├─POST /v1/device/commands/{id}/progresso  (fração, etapa, parcial)  → "em execução"
  ├─(cancelar: comando assinado "ensaio_cancelar" → para no próximo ponto de checagem)
  └─POST /v1/device/commands/{id}/result  (laudo + AMOSTRAS BRUTAS)
                                                                       │ RECALCULA o veredito com as
                                                                       │ amostras e com os limites que ELA
                                                                       │ assinou (não os que voltaram)
                                                                       ▼
                                                    ensaio_resultado (status, critérios, medidas,
                                                    divergente, simulado, vale_portao)
                                                                       │
                                     portões por fase ◀────────────────┤
                                     aviso de regressão ◀──────────────┘ (aprovado → reprovado)
```

* **O veredito é do servidor.** O robô manda a prévia dele (`aprovado`) e as amostras; a
  plataforma refaz as contas (`saas/valtexa/services/ensaios.py`) com os parâmetros que
  ela mesma assinou. Divergência entre os dois fica marcada (`divergente`). Um teste
  (`test_veredito_e_do_servidor_nao_do_robo`) manda um laudo que diz "aprovado" com 40 mm
  de erro e ainda tenta trocar a distância da trena: o servidor reprova.
* **Limites do portão.** Cada ensaio tem limites padrão (tabela abaixo). O operador pode
  **apertar** (ex.: deriva ≤ 50 ms), nunca afrouxar (422). Parâmetros de medida (distância
  da trena, ponto conhecido, inclinação informada) são livres.
* **Simulado não abre portão.** Laudo com `simulado: true` (ou sem a marca) conta só com
  `?aceitar_simulado=true` (o simulador usa isso). No portão real aparece "só simulado".
* **Ensaio não move o robô.** Movimento só pela navegação e pelo MCU, via `/run/valtexa`.
  A parada de segurança não depende de rede, rádio nem nuvem — os ensaios de segurança
  medem só o caminho do software.
* **Prazo.** Ensaio em execução que fica sem notícia além da duração estimada + 15 min
  vira `falhou` ("sem notícia do robô dentro do prazo do ensaio").

## 2. Catálogo

| Ensaio | Fase | Mede | Aprova se (padrão do portão) | Para valer no portão |
|---|---|---|---|---|
| `calor` | 0 | N min de inferência contínua; vazão por janela; `tegrastats` (temperatura, clocks CPU/GPU) | perda de vazão (última × primeira janela) ≤ 10 %; queda de clock ≤ 20 % (throttling); `temp_max_c` opcional | `duracao_min` ≥ 120 e clocks do tegrastats lidos |
| `cameras` | 0 | 1–8 câmeras disparadas juntas (uma thread por câmera) | perda (falha + salto de índice) ≤ 0 %; p95 da deriva entre carimbos ≤ 100 ms; p95 da idade do GNSS na foto ≤ 200 ms | ≥ 6 câmeras juntas |
| `profundidade` | 0 | mediana da profundidade na ROI contra a trena | \|erro\| ≤ 20 mm; preenchimento ≥ 0,5 | uma por distância: 0,3 / 0,5 / 0,8 m (± 50 mm) |
| `gnss` | 0 | tempo até fix RTK; CEP50/CEP95/2DRMS; perda e retomada | fix ≤ 120 s; CEP95 ≤ 5 cm; viés ≤ 5 cm; ≥ 1 perda observada, todas retomadas em ≤ 60 s | com ponto conhecido (`lat_ref`/`lon_ref`) e `perda_s` > 0 |
| `imu` | 0 | parada: \|g\|, rolagem/arfagem, inclinação pela gravidade, giroscópio | \|g − 9,80665\| ≤ 0,1 m/s²; erro de inclinação ≤ 1,5°; eixos coerentes ≤ 1,5°; ruído ≤ 0,2 °/s; viés ≤ 0,5 °/s | — |
| `rede` | 0 | RTT, perda e vazão até a plataforma (canal assinado) | perda ≤ 5 %; p95 RTT ≤ 500 ms; subida e descida ≥ 256 kbit/s | — (base para a P13) |
| `energia` | 0 | bateria (BMS/MCU) | autonomia estimada ≥ 8 h | **fora do portão: aguarda protocolo do BMS/MCU** |
| `parada` | 1 | latência do PARAR até a navegação confirmar (`parado_em`) | 100 % confirmadas; p95 ≤ 500 ms | ≥ 5 tentativas |
| `homem_morto` | 1 | o `teleop.json` zera depois do `valid_until` | episódios ≥ pedido; atraso ≤ 1 s | — |
| `validacao_agronomica` | 5 | relatório Rover × agrônomo (validação de campo) | sensibilidade ≥ 0,80; alarme falso ≤ 0,15; concordância ≥ 0,80; ≥ 10 doentes e ≥ 10 sadias rotuladas (opcional: pelos limites do IC de Wilson, `usar_ic`) | — |

Fases 2, 3 e 4 não têm ensaio automático: o portão é o do guia, à mão. A **FASE ENLACE**
(Parte 13) está na seção 6.

## 3. Contrato com a navegação (`navegacao.json`)

Para o ensaio `parada`, a pilha de navegação escreve, depois de cada pedido em
`parar.json` (`{"reason", "at"}`):

```json
{"parado_em": "2026-10-08T14:03:12.481+00:00", "parada_ref": "<o at do parar.json>", "v_ms": 0.0}
```

* `parado_em` — ISO-8601 UTC, o instante em que as rodas **pararam** (não o instante em
  que leu o pedido);
* `parada_ref` — cópia do `at` do `parar.json` obedecido (assim o ensaio sabe que a
  confirmação é deste pedido);
* `v_ms` — opcional, velocidade medida (o ensaio com `exigir_movimento` espera o robô
  andar antes de pedir a parada).

`homem_morto`: o Runtime agora zera o `teleop.json` sozinho quando o ponto que está nele
vence sem outro (antes, se o servidor repetisse o mesmo ponto, o arquivo ficava com a
velocidade vencida até a navegação ler o `valid_until`). A navegação **continua obrigada**
a parar sozinha no `valid_until`.

## 4. Como rodar

* **Console**: Plataforma → Centro de comando → rover → **Validação**
  (`/plataforma/comando/<id>/validacao`): portões, ensaios em curso (progresso, cancelar),
  resultados (critério a critério, simulado e divergência marcados) e novo ensaio.
* **API**: `POST /v1/platform/rovers/{id}/ensaios` `{"ensaio": "gnss", "params": {...}}`;
  `POST .../ensaios/{command_id}/cancelar`; `GET .../ensaios`; `GET .../ensaios/{id}`;
  `GET .../portoes[?aceitar_simulado=true]`; `POST .../ensaios/validacao-agronomica`
  `{"field_id", "mission_id"}`; `GET /v1/platform/ensaios/catalogo`.
* **Simulador (FASE 0 inteira, veredito da plataforma)**: `cd saas && python -m simulator
  --fase0` → `laudo-fase0.md`.
* **Só o robô (prévia, sem plataforma)**: `cd rover && python -m valtexa_rover.sim fase0
  --saida laudo.md`.

## 5. O que falta no hardware (simulado/não testado)

| Ensaio | Falta conferir no Rover V3 |
|---|---|
| calor | formato do `tegrastats` do JetPack 6 (clocks `%@MHz`, `GR3D_FREQ x%@[MHz]`); vazão real do modelo de café na Orin NX |
| câmeras | 8 OAK-D Pro W PoE no mesmo switch; sincronia de hardware (PPS do ZED-F9P) não é medida, só os carimbos do Runtime |
| profundidade | `capture_depth()` da OAK-D (fila `depth` da StereoDepth alinhada à foto de 12 MP) |
| gnss | ZED-F9P com correção NTRIP/base; o tempo até fix depende da correção da fazenda |
| imu | IDs e escalas CAN do MTi-630 no MT Manager; giroscópio só com `gyro_id`/`gyro_escala_dps` no `hardware.json` (sem eles, a taxa vem da derivada dos ângulos) |
| parada | a navegação publicar `parado_em`/`parada_ref`; não mede freio nem MCU |
| homem_morto | a navegação parar no `valid_until` por conta própria |
| rede | o enlace da fazenda (4G, rádio, Wi-Fi) — ver a FASE ENLACE (§6) |
| energia | protocolo do BMS/MCU |

## 6. FASE ENLACE (Parte 13) — rádios, repetidoras, base, Starlink e relógio

Número **6** no banco (o portão aparece como "Fase ENLACE" no console), mas vem **logo
depois da Segurança**: o enlace da fazenda tem de estar provado antes de o Rover trabalhar
no cafezal. Pré-requisitos: base instalada, rádios no mastro, **levantamento de cobertura**
feito (`docs/COMUNICACAO_FAZENDA.md` §10) e o Rover com `"rede": {"modo": "base"}`.
Código: `rover/valtexa_rover/ensaios/enlace.py` (o robô mede) e
`saas/valtexa/services/ensaios.py` (a plataforma refaz as contas).

| Ensaio | Mede | Aprova se (padrão do portão) | Para valer no portão |
|---|---|---|---|
| `enlace_rssi` | num ponto do levantamento (`ponto`), por `duracao_s`: RSSI/SNR (quando o rádio expõe), RTT e perda de cada rádio com a base; posição RTK | no melhor rádio: RSSI p50 ≥ −85 dBm; SNR p50 ≥ 15 dB; perda média ≤ 10 %; RTT p95 ≤ 300 ms; posição `fixed`/`float` | o rádio expõe RSSI (adaptador SNMP/HTTP) — um laudo por ponto crítico (borda da zona morta, pé de cada repetidora) |
| `enlace_latencia` | ida e volta de P1 Rover → base → Rover **pelo rádio** (sem a nuvem) | p99 ≤ 500 ms; perda ≤ 1 % | ≥ 200 ecos |
| `enlace_troca` | um rádio "morre" no meio do tráfego: tempo até o lote (P2–P4) ir pelo outro e maior buraco de P1 | troca ≤ 5 s; interrupção de P1 ≤ 2 s | `modo: manual` — o técnico **desliga o rádio** (alimentação ou cabo) na janela; `modo: base` (a base silencia por software) serve de regressão |
| `enlace_starlink` | a Starlink cai e volta: uma sonda à nuvem a cada `sondas_s`, cada uma repetida até entrar (como a fila de sincronização) | nenhuma sonda perdida; tudo entra em ≤ 60 s depois que a Starlink volta | `modo: manual` — o técnico **tira o cabo** da Starlink por `queda_s` |
| `enlace_energia_base` | a base cai e volta: tempo sem enlace e as sondas guardadas | sem enlace ≤ 120 s; nenhuma sonda perdida; sondas entram em ≤ 60 s | `modo: manual` — o técnico **corta a energia** da base (conta o boot e o nobreak) |
| `enlace_travessia` | as últimas travessias de zona morta mapeada que as missões registraram (`travessias.jsonl`) | aviso ≥ 10 s antes de entrar; sincronizado ≤ 60 s depois de sair; duração ≤ 1,5 × prevista + 15 s | ao menos uma travessia real (missão que cruza a zona morta do mapa) |
| `relogio` | chrony no Rover e na base (`chronyc -c tracking`/`sources`) e o atraso contra a hora assinada da plataforma | os dois sincronizados, **fonte GNSS/PPS**, \|offset\| ≤ 10 ms; atraso ≤ 1 s | `exigir_gnss: true` |

* **Pedidos que mexem na base** (silenciar rádio, Starlink fora por software, reiniciar o
  serviço) só valem com `"ensaios_remotos": true` no `base.json` — ligue só durante a
  validação. Os modos manuais não precisam disso.
* O laudo do modo por software aprova (é a regressão do código), mas fica com
  `vale_portao = false` e a observação "feito por software… não vale para o portão".
* **Simulado / não testado em hardware**: todos rodaram só contra o emulador e UDP no
  `localhost` (`base/tests/test_ensaios_enlace.py`). No campo: RSSI/SNR dependem do rádio
  escolhido expor a leitura; o tempo de volta da base depende do boot do mini PC.

Rodar: `valtexa-rover ensaio enlace_latencia --param ecos=200` na Jetson (sem a
plataforma), ou pelo console (Validação → novo ensaio).
