# Comunicação da fazenda: base, rádios e protocolo de enlace

Rodada 3, Partes 12–14. **P12**: projeto, protocolo de enlace, base da fazenda, emulador de
rádio e testes de caos (§1–§9). **P13** (enlace à prova de falha): verificação hostil da P12
(§6, §8), **malha com repetidoras** (§10), **levantamento de cobertura** (§11), **missão
ciente do enlace** (§12), **relógio por GNSS** (§13), **ensaio de 24 h simulado** (§14),
**procedimento de campo** (§15). **P14**: a base no SaaS e o ponta a ponta com a frota.

> **O que é real e o que é simulado.** Real e testado (em processo e por UDP no
> `localhost`): o protocolo inteiro (quadros, criptografia, ACK seletivo, retransmissão,
> fragmentação, filas persistentes, agendador, múltiplos enlaces), a base como proxy das
> rotas `/device` e o Runtime do Rover falando com a plataforma de verdade (uvicorn) através
> da base e do emulador. **Simulado / não testado em hardware**: todo rádio. Os rádios
> entram como interfaces IP (ponte Ethernet) e o comportamento deles vem do emulador
> (`enlace/emulador.py`); a leitura de RSSI/SNR por SNMP/HTTP tem adaptador escrito e
> testado só contra um falso. **Nenhum número de alcance, vazão de rádio ou upload da
> Starlink deste documento foi medido** — onde importa, está escrito "a medir".

## 1. Topologia

```
                 internet (Starlink)
 Nuvem ValTexa  ◀════════════════════▶  BASE DA FAZENDA (mini PC Ubuntu, nobreak)
 (plataforma)       HTTPS /v1/device       │  valtexa-base: proxy assinado, filas, console LAN
                                           │
          ┌────────────────────────────────┼─────────────────────────────┐
          │ enlace A: sub-GHz longo alcance │ enlace B: 5 GHz / 2,4 GHz    │ enlace C: 4G
          │ (sem visada, baixa vazão)       │ (alta vazão, mastro, malha)  │ (se houver sinal)
          │                                 │   ▲ repetidoras solares      │
          ▼                                 ▼   │ opcionais nos morros     ▼
        ROVER V3 (Jetson Orin NX) — valtexa-rover com transporte "via base"
          │
          └── rádio de PARADA DE EMERGÊNCIA próprio ──▶ MCU de segurança (contato seguro)
              (não passa pelo software nem pelos enlaces de dados)

 POSTE DE RECARGA ── Wi-Fi rápido ou cabo ── LAN da base   (volume grande, à noite)
```

* **Nuvem ⇄ base**: HTTPS comum pela Starlink. A base fala com a plataforma exatamente as
  rotas `/v1/device/**` que o Rover falaria; as requisições continuam **assinadas pelo
  Rover** (Ed25519, `saas/docs/DEVICE_PROTOCOL.md`) — a base só repassa.
* **Base ⇄ Rover**: dois ou mais enlaces de rádio **simultâneos**, cada um visto pelo
  software como uma interface IP com saúde medida. O protocolo de enlace
  (`rover/valtexa_rover/enlace/`) roda por cima de UDP em todos eles ao mesmo tempo.
* **Repetidoras**: rádios em mastro com painel solar nos pontos altos; para o software são
  transparentes (o rádio faz a ponte/malha), aparecem só como RTT e perda maiores.
* **Parada de emergência**: rádio dedicado, ligado direto ao MCU de segurança. O botão na
  mão do operador abre o circuito de segurança do robô sem passar pela Jetson, pela base,
  pela nuvem nem pelos enlaces de dados. O "PARAR" do console e da nuvem é uma camada a
  mais (software), nunca a única.

## 2. Volumes por classe de dado (a conta)

Premissas (do Rover V3 e do Runtime atual; as que mudarem mudam a conta):
8 câmeras OAK-D Pro W; foto parada de 12 MP em JPEG ≈ 3,0–4,0 MB; resultado da Edge AI
por quadro ≈ 2–4 KB de JSON; reduzida de evento ≈ 30 KB; telemetria a cada 5 s ≈ 600 B;
batimento do enlace 2/s por enlace ≈ 100 B com cabeçalhos; teleop a 4 Hz.

| Classe | Conta | Taxa |
|---|---|---|
| **P0 segurança e batimento** | 2 enlaces × 2 batimentos/s × ~100 B × 8 bit, mais ACKs | **≈ 3–5 kbit/s** |
| **P1 comandos e teleop** | teleop 4 Hz × (pedido ~450 B + ponto assinado ~700 B) × 8 bit ≈ 37 kbit/s; comandos esporádicos | **≈ 40 kbit/s** só com teleop ativo; ~1 kbit/s sem |
| **P2 telemetria** | 600 B / 5 s × 8 bit ≈ 1 kbit/s (+ eventos de saúde) | **≈ 1–2 kbit/s** |
| P0+P1+P2 | soma acima | **< 50 kbit/s** — cabe num rádio sub-GHz |
| **P3 resultados e eventos** | 8 câm. × 0,5 quadro/s = 4 resultados/s × 3 KB = 96 kbit/s; reduzidas ~0,5/s × 30 KB = 120 kbit/s; + cabeçalhos | **≈ 0,3 Mbit/s** |
| Vídeo leve de teleoperação (P13) | H.264 720p, 10–15 qps | **1–3 Mbit/s** — só no enlace de alta vazão |
| **P4 originais de eventos** | 0,25–0,5 evento/s × 3 MB × 8 bit | **≈ 6–12 Mbit/s** |
| **P4 modo coleta** | 8 câm. × 0,5 quadro/s × 3,75 MB × 8 bit | **≈ 120 Mbit/s** |

Consequências:

* 8 h de coleta = 120 Mbit/s × 28.800 s ≈ **432 GB/dia**. Nenhum rádio de campo leva isso
  em tempo real; vai pelo **poste de recarga** (Wi-Fi 6 ou cabo de 1–2,5 GbE): a
  ~500 Mbit/s efetivos, ≈ 2 h de doca.
* **Upload da Starlink: a medir** (varia por plano, céu e horário; não usamos número de
  catálogo). A pergunta que a medida responde: 432 GB em 10 h de madrugada pedem
  ~96 Mbit/s sustentados. Se o upload medido não chegar a isso, o modo coleta precisa de
  seleção (só o que a validação pede) ou de transporte físico do disco.
* Em operação normal (sem coleta), o que sobe em tempo real é P0–P3 (< 0,4 Mbit/s); os
  originais de evento vão pelo enlace de alta vazão quando houver sobra, senão pela doca.

## 3. Princípio

**Rádio para o tempo real; volume grande pelo poste de recarga, e sobe à noite.**

* P0–P2 têm de passar em qualquer enlace vivo, inclusive o mais lento (sub-GHz).
* P3 passa pelo melhor enlace; se só o sub-GHz estiver vivo, P3 vai devagar e acumula
  (nada se perde: a fila do Rover é persistente e só esvazia com o aceite da plataforma).
* P4 só usa a sobra de banda. Na doca, a sobra é a LAN inteira.

## 4. Redundância (obrigatória)

1. **Dois enlaces de dados independentes, no mínimo**, em faixas e físicas diferentes:
   * **sub-GHz de longo alcance sem visada** (difração em morro e penetração na copa
     são melhores em frequência baixa) — carrega P0–P2 sozinho;
   * **5 GHz ou 2,4 GHz de alta vazão** em mastro, com **malha** e **repetidoras
     solares** nos morros — carrega P3, vídeo e sobra de P4.
2. **4G** como terceiro enlace quando houver cobertura no talhão (no Sul de Minas, muitas
   vezes não há no fundo do vale: medir).
3. **Parada de emergência em rádio próprio**, ligado direto ao MCU (contato seguro,
   desenergiza o acionamento). Não depende do software nem de enlace de dados; o MCU
   deve parar também na **perda** do sinal do rádio de emergência (homem-morto do
   próprio rádio). O protocolo do MCU ainda não está definido — esta é uma exigência para
   ele.

## 5. Equipamento por função (sem preço: "a cotar")

| Função | Tipo de equipamento | Observações | Preço |
|---|---|---|---|
| Internet da base | Starlink (kit padrão ou empresarial) + roteador | upload **a medir**; nobreak | a cotar |
| Computador da base | mini PC x86 com Ubuntu Server, 2+ portas Ethernet, SSD | roda `valtexa-base` | a cotar |
| Enlace A (sub-GHz) | rádio industrial **Ethernet/IP** de 900 MHz FHSS (faixas ISM 902–907,5 e 915–928 MHz no Brasil — **conferir homologação Anatel**), antena omni na base e no robô | vazão baixa (centenas de kbit/s, **a medir**), alcance sem visada | a cotar |
| Enlace B (alta vazão) | rádio outdoor 5 GHz (PtMP ou malha 802.11ac/ax) ou 2,4 GHz em malha; setorial no mastro, omni/painel no robô | precisa de visada ou repetidora | a cotar |
| Repetidora | o mesmo rádio do enlace B (ou A) + painel solar + bateria + controlador de carga, em mastro | sem computador: ponte/malha do rádio | a cotar |
| Enlace C (4G) | roteador 4G industrial com SIM de dados, antena externa | só onde houver cobertura | a cotar |
| Parada de emergência | controle remoto de segurança industrial (categoria/PL certificados) com receptor ligado ao circuito de segurança do MCU | independente de tudo acima | a cotar |
| Poste de recarga | ponto de acesso Wi-Fi 6 outdoor ou conector com cabo Ethernet na doca | volume grande | a cotar |

Quase todos esses rádios são **pontes Ethernet/IP**: o software não fala o protocolo do
rádio, fala UDP por uma interface IP. Cada enlace é uma interface (ou um IP de destino
diferente) e a saúde de cada um é **medida** pelo próprio protocolo (RTT, perda, vazão);
RSSI/SNR entram quando o rádio expõe (SNMP ou HTTP; adaptador em
`base/valtexa_base/radios.py`, **não testado em hardware**).

## 6. Protocolo de enlace (`rover/valtexa_rover/enlace/`)

Biblioteca Python pura, sem hardware, compartilhada pelo Rover e pela base (a base
depende do pacote `valtexa-rover`). Roda por UDP em **todos os enlaces ao mesmo tempo**.

| Módulo | O quê |
|---|---|
| `quadro.py` | pacote no fio: `"VX"`, versão, tipo, sessão (8 B), contador (8 B), corpo, **CRC32**; registros `FRAG`, `ACK`, `BAT` |
| `cripto.py` | chave X25519 do enlace (nasce no nó, 0600), pública **assinada pela identidade Ed25519**; aperto de mão em 2 pacotes (estilo Noise KK); ChaCha20-Poly1305; anti-replay |
| `fila.py` | filas persistentes em SQLite WAL (`saida`, `entrada`, `vistos`), limites e disco cheio |
| `saude.py` | RTT, perda, vazão, RSSI/SNR; vivo/morto com histerese; melhor enlace com histerese |
| `no.py` | o nó: ARQ com ACK seletivo, fragmentação, prioridades, redundância, agendador, *slots* |
| `rpc.py` | HTTP sobre o enlace: `RedeViaBase` (HAL de rede do Rover), `atende`/`responde` (base), `Executor` |
| `transferencia.py` | arquivo grande retomável em pedaços com SHA-256 |
| `politica.py` | perda de enlace no Rover → `/run/valtexa/enlace.json` e a política |
| `emulador.py` | rádio **emulado** (em processo e relé UDP) |
| `bancada.py` | Rover + base em relógio virtual (testes de caos, relatório de latência) |

### 6.1 Quadros e entrega confiável

* Cada mensagem tem um id de 16 bytes, prioridade P0–P4 e canal (pedido HTTP, resposta,
  controle, arquivo). Vira pedaços (`FRAG`) do tamanho da menor MTU (padrão 1200 B por
  pacote; os rádios-ponte aceitam 1500).
* **Número de sequência**: o contador do pacote, por sessão e sentido (é também o nonce).
* **ACK seletivo**: o receptor manda, por mensagem, a base cumulativa (todos os pedaços
  abaixo chegaram) + mapa de 64 bits; o ACK pega carona no próximo pacote de dados.
* **Retransmissão com recuo**: cada pedaço tem temporizador (RTO do enlace pelo RFC 6298,
  mínimo 150 ms), recuo de 1,5× até 4× o RTO (o balde de fichas já cadencia; no rádio a
  perda é sobretudo aleatória). P0/P1: no máximo 0,5 s entre tentativas, por enlace.
* **Deduplicação**: mensagem inteira entra na `entrada` e no `vistos` na **mesma
  transação**; repetida (retransmissão, duplicação do rádio, cópia redundante, reenvio
  depois de reinício) só é confirmada de novo. O emissor só apaga quando ouve "entregue
  inteira".
* Receptor reiniciou no meio de uma mensagem (os pedaços estavam em memória): o emissor
  vê tudo confirmado e nenhum "entregue" e, depois de `max(2 s, 4×RTO)`, reenvia a
  mensagem inteira.

### 6.2 Criptografia por salto

* Chave estática X25519 só do enlace, por nó; a do Rover vai para a base **assinada pela
  identidade Ed25519 provisionada** (`valtexa-rover enlace-chave` → `valtexa-base
  adicionar-rover`, que confere a assinatura contra a pública Ed25519 que a plataforma
  conhece). Nada de chave no código ou no repositório.
* Aperto de mão `HS1`/`HS2` com efêmeras novas a cada vez (sigilo futuro), HKDF-SHA256
  sobre `DH(e,e) ‖ DH(e,s) ‖ DH(s,e) ‖ DH(s,s)`, uma chave por sentido; ChaCha20-Poly1305
  com o cabeçalho como dado associado.
* **Nonce nunca reutilizado**: contador de 64 bits por sessão e sentido; sessão nova =
  chaves novas (troca a cada hora ou depois de queda longa).
* **Anti-replay**: janela de 1024 contadores; o respondedor só passa a usar a sessão nova
  depois do primeiro pacote válido nela (um `HS1` repetido não derruba a sessão em uso);
  o aviso `REINICIAR` (não autenticado) só vale com o enlace calado há 2 batimentos.
* **Fim a fim continua valendo**: os pedidos do Rover seguem assinados com Ed25519 (a
  base não tem a chave e mudar um byte invalida a assinatura) e as respostas com comando,
  missão e teleop seguem assinadas pela plataforma — **a base não consegue forjar
  comando** (teste: `base/tests/test_base.py::test_repassa_a_nuvem_byte_a_byte...`).
* **Recibo assinado** (P13): o "200 aceito" de um registro, pedaço de upload ou resultado
  faz o Rover apagar o dado da fila — uma base com defeito ou adulterada que fingisse o
  aceite causaria perda. Agora todo pedido que muda estado vai com `X-Valtexa-Recibo: 1` e a
  plataforma assina `nonce do pedido | status | sha256 do corpo`; sem recibo válido, o 2xx é
  "sem rede" e o dado fica (`saas/docs/DEVICE_PROTOCOL.md` §4; testes
  `test_base_adulterada_nao_faz_o_rover_apagar_o_que_nao_chegou`,
  `saas/tests/test_recibo_dispositivo.py`).

### 6.3 Prioridades e agendador

| Classe | O quê | Como sai |
|---|---|---|
| **P0** | segurança (PARAR da base) e batimento | por **todos** os enlaces vivos; pode estourar o balde |
| **P1** | comandos, missão, teleop | por **todos** os enlaces vivos (redundante, deduplicado no receptor) |
| **P2** | telemetria | pelo melhor enlace |
| **P3** | resultados e eventos, reduzidas | pelo melhor enlace, intercalado 1:3 com P2 |
| **P4** | originais em lote, OTA | pelo melhor enlace, **só com a sobra** |

Orçamento por enlace: balde de fichas a **90 % do `banda_bps`** configurado (folga para o
buffer do rádio não encher e o P1 não esperar atrás de P4). Ordem em cada pacote: ACKs,
batimento, P0, P1, P2/P3 e, só se nada de P0–P3 estiver elegível naquele enlace, P4. Sem
nenhum enlace vivo, P0/P1 tentam por todos os que têm sessão.

### 6.4 Filas persistentes e disco cheio

SQLite em WAL, `synchronous=FULL` em produção (o commit sobrevive à queda de energia;
os testes usam `NORMAL`, que sobrevive ao `kill -9`). Limites (`fila.Limites`): P4 com
teto próprio (padrão 384 MB); P2+P3+P4 com teto conjunto (512 MB), em que P2/P3 tiram P4
da fila **só se isso bastar** (o original continua no disco do Rover); P0/P1 com reserva
própria (32 MB); com menos de 256 MB livres no disco só P0/P1 entram. **Nunca se apaga
P0–P3 já aceito**: o novo é recusado (`FilaCheiaError`) e quem chamou guarda — no Rover, o
dado continua na fila de sincronização, que só esvazia com o aceite da plataforma.

### 6.5 Teleop e validade

* Teleop é um **slot** "só o último vale": cada ponto novo substitui o anterior ainda não
  entregue, não vai para o disco e morre na validade (1 s); o receptor descarta o vencido
  e o mais velho que o último aplicado (sequência por slot, reservada em blocos de 1000 no
  disco para crescer depois de um reinício). O ponto continua assinado pela plataforma com
  `valid_until`, conferido pelo Runtime, e a navegação para sozinha quando ele passa.
* Toda mensagem com validade leva o tempo que resta em cada pedaço; vencida na fila não
  sai, vencida na chegada não entra; a base não repassa pedido vencido e não devolve
  resposta vencida. Comando com validade vencida é recusado (pelo enlace e, de novo, pelo
  Runtime, que confere o `expires_at` assinado).
* **Relógio errado** (P13): cada nó confere validade **no próprio relógio** (a base usava o
  `prazo` em hora do Rover: com o Rover 10 min atrasado, tudo "vencia" na base), numa
  "parede estável" (hora do início + monotônico — o chrony acertando a hora não estica nem
  encurta o que está na fila). O Runtime confere `expires_at` contra
  `max(relógio do robô, piso)`, em que o **piso** é o `issued_at` assinado mais novo já
  visto + o tempo monotônico desde então (`PisoDaPlataforma`): um ponto de teleop retido
  por uma base com defeito é recusado mesmo com o relógio do Rover atrasado.

### 6.6 Vários enlaces ao mesmo tempo

* Saúde por enlace: RTT (eco do batimento, descontado o tempo parado do outro lado),
  perda (quantos pacotes o outro lado diz que recebeu), vazão confirmada, RSSI/SNR
  quando o rádio expõe. Batimento a cada 0,5 s por enlace.
* **Vivo → morto** depois de 3 s sem pacote válido; **morto → vivo** só com 3 pacotes
  espaçados em 1 s (uma rajada não religa).
* **Melhor enlace** para o lote = vazão útil / (1 + RTT); troca só se o outro for 1,5×
  melhor por 2 s seguidos (histerese) — ou na hora, se for 4× melhor ou se o atual morrer.
* **Calado = suspeito** (P13): enlace sem pacote há 1 s (2 batimentos) já não leva o lote,
  se outro estiver falando — a troca do lote cai de ~3 s para ~1 s, sem declarar o enlace
  morto (isso continua em 3 s). **Estabilidade**: o enlace que voltou só puxa o lote de novo
  depois de vivo 5 s × (1 + quedas no último minuto), até 30 s — o rádio que oscila com a
  copa ao longo da rua não faz o lote pular (40 min de cafezal simulado: 253 → 7 trocas).

### 6.7 Perda de enlace no Rover (`/run/valtexa/enlace.json`)

A cada 0,5 s o Rover escreve (atômico) a saúde de cada enlace, `algum_vivo`,
`sem_enlace_desde`, o melhor enlace, se a base tem internet e a **ação**:

* sem enlace por mais de `tolerancia_s` (2 s): **teleop zera** sempre;
* missão autônoma só continua se a missão permitir
  (`politica_enlace.continuar_sem_enlace` no corpo assinado; padrão **não**) — senão o
  modo vai a `pausado` e **volta sozinho** a `autonomo` quando um enlace religar;
* em modo manual, `pausado`.

**Parar nunca depende do enlace**: a política só reduz movimento quando o rádio cai; a
parada de emergência é o rádio próprio ligado ao MCU. O Runtime não comanda motor:
escreve arquivos que a navegação e o MCU leem.

### 6.8 HTTP sobre o enlace (`RedeViaBase`)

A HAL `Network` do Rover ganhou o transporte "via base": o `DeviceClient` assina como
sempre e `RedeViaBase.send` leva método, caminho, cabeçalhos e corpo numa mensagem do
enlace, com a prioridade da rota (§6.3; os pedaços de upload de `tier = original` vão em
P4), e espera a resposta no prazo da classe (P1 4 s, teleop 1 s, P2 15 s, P3 30 s, P4
120 s). Sem enlace vivo, sem resposta no prazo ou com a base sem internet, levanta
`NetworkUnavailableError` — o que a sincronização já trata (o item fica, sem gastar
tentativa). `is_online()` = algum rádio vivo **e** a base com internet (o batimento da
base diz `"nuvem"`): com a Starlink caída a sincronização fica parada — um
`ROVER_OFFLINE`, não um par de eventos a cada passo — e volta sozinha quando a base avisa.
**O protocolo com a plataforma não mudou.**

Ligar no robô (`hardware.json`, exemplo em `rover/deploy/hardware.rover-v3.fazenda.json.exemplo`):
`"rede": {"modo": "base", "base_pub": "...", "enlaces": [{"nome", "bind", "destino",
"banda_bps", "mtu"}]}`. O 4G precisa alcançar a base pela internet: **a definir** (IPv6
da Starlink ou um relé na nuvem — a Starlink costuma estar atrás de CGNAT em IPv4).

### 6.9 Transferência retomável

`EnviaArquivos`/`RecebeArquivos`: manifesto (SHA-256 do arquivo e de cada pedaço de 64 KB)
e pedaços como mensagens próprias, numa janela de 8; progresso em SQLite dos dois lados;
cada pedaço é conferido, escrito no lugar com `fsync` e marcado. Depois de matar os dois
processos no meio, cada pedaço foi enfileirado **uma vez** e escrito **uma vez**
(`test_matar_e_reiniciar_os_processos_no_meio_da_transferencia`). Uso na P12: logs, laudos e
pacotes entre base e Rover; os originais para a plataforma continuam no protocolo de upload
em pedaços da plataforma (`docs/SYNC.md`), que já é retomável, levado em P4.

## 7. Base da fazenda (`base/`, pacote `valtexa_base`)

| Arquivo | O quê |
|---|---|
| `servico.py` | `BaseDaFazenda`: nó respondedor (um par por Rover), proxy, manutenção; `ConfigDaBase` (`base.json` + `hardware.json` + `pares.json`, com a assinatura de cada Rover conferida) |
| `nuvem.py` | `ClienteNuvem` (HTTPS, uma tentativa por pedido vivo), `EstadoDaInternet` (sonda `/health`), `Encaminhador` (fila por prioridade, trabalhador reservado a P0/P1, P4 só com a sobra e `uplink_p4_bps`) |
| `custodia.py` | cópia dos pedidos idempotentes enquanto a assinatura vale (240 s < 300 s da plataforma) |
| `missoes.py` | cache dos envelopes de missão assinados; armar para iniciar sem internet (vale uma vez) |
| `console.py`, `console.html` | console e API na LAN (estado, **PARAR para todos**, missões, métricas Prometheus) |
| `radios.py` | RSSI/SNR por SNMP (`snmpget`) ou HTTP/JSON — **não testado em hardware** |
| `watchdog.py` | `sd_notify` (`READY=1`, `WATCHDOG=1`) |
| `cli.py` | `valtexa-base servico`, `chave`, `adicionar-rover` |
| `deploy/` | `instalar.sh` (Ubuntu), `valtexa-base.service` (`Type=notify`, `WatchdogSec=30`), `base.json.exemplo`, `hardware.json.exemplo` |

* **Proxy**: só `/v1/device/**` passa (o resto, `403`). Pedido repassado como chegou; a
  resposta volta com a validade que sobrou. A base nunca repete um pedido vivo (o nonce
  só vale uma vez na plataforma): quem repete é o Rover, com assinatura nova.
* **Sem internet**: a base continua aceitando tudo do rádio; responde `503` com
  `X-Valtexa-Base: sem-internet` na hora; guarda em custódia o idempotente (registros,
  telemetria em lote, abertura e pedaços de upload — mesma rota e corpo = uma linha) e
  entrega quando a Starlink volta, se a assinatura ainda vale. Avisa os Rovers no
  batimento (`"nuvem": false`) e eles param de sincronizar até ela voltar: na prática a
  custódia pega o que estava no ar no momento da queda. Queda mais longa: a fila do Rover é
  a fonte da verdade (a custódia só adianta a chegada).
* **Console local** (sem internet): estado de cada Rover e enlace, filas, custódia; PARAR
  para todos (P0 por todos os enlaces vivos; sem senha — parar é o lado seguro — mas com
  `X-Valtexa-Console: 1` contra página de fora); armar missão do cache (token do console
  lido de arquivo; sem arquivo, desligado). O Rover confere assinatura e validade da
  missão do cache como de qualquer outra; vencida não arma.
* **Saúde**: `/metricas` (internet, custódia, uplink por prioridade, cada enlace: vivo,
  RTT, perda, vazão, quedas, RSSI); watchdog do systemd.

## 8. Testes e números (rádio EMULADO)

| Suíte | O quê |
|---|---|
| `rover/tests/test_enlace.py` (13) | CRC pega cada bit trocado; registros; aperto de mão; replay e nonce; adulteração; par desconhecido; chave assinada; filas: reabrir, deduplicar, validade, limites, disco cheio |
| `rover/tests/test_enlace_caos.py` (8) | 30 % de perda nos dois enlaces (400 mensagens); rajadas Gilbert-Elliott + reordenação + duplicação + corrupção; quedas de 5–60 s com troca de enlace; queda total (comando vencido nunca aplicado; volta sozinho); **matar e reiniciar os dois nós no meio de uma transferência de 3 MB**; latência de P1 sob carga de P4; P4 só com a sobra; teleop só o último |
| `rover/tests/test_enlace_rover.py` (8) | RPC por UDP com 2 relés emulados (assinatura confere do outro lado), base sem internet, PARAR da base, política de perda de enlace (pausa e volta, missão que permite, queda curta), montagem pelo `hardware.json` |
| `base/tests/test_base.py` (12) | proxy byte a byte, só `/device`, sem internet + custódia, janela da assinatura, comando não espera upload, console (PARAR para 2 Rovers, métricas), missão do cache, rádios falsos, watchdog, cadastro conferido |
| `base/tests/test_base_processo.py` (1) | base como processo, **`kill -9` duas vezes** e Rover reiniciado no meio de 150 registros + 150 pedaços: nada perdido |
| `saas/tests/test_base_fazenda.py` (1) | **ponta a ponta**: Runtime real ⇄ 2 rádios emulados (15 % de perda) ⇄ base ⇄ plataforma no uvicorn, com a Starlink e depois os dois rádios caindo no meio da missão |

Números medidos nesta execução (rádio **emulado**; servem para comparar versões do
protocolo, não para prometer desempenho em campo):

| Medida | Valor |
|---|---|
| P1 a cada 250 ms sob carga contínua de P4, 30 % de perda nos dois enlaces (250 kbit/s + 20 Mbit/s), 120 s | **p50 20 ms, p95 250 ms, p99 380 ms, máx. 620 ms; 0 perdido** (473 comandos) |
| P3 no mesmo cenário | p50 170 ms, p95 750 ms, p99 2,3 s; 0 perdido |
| RPC P1 completo (pedido → base → resposta) por UDP, 2 relés com 20 % de perda | p50 ≈ 29 ms, p95 ≈ 0,5 s |
| Volta depois do `kill -9` da base (processo novo + aperto de mão + RPC) | 2,0 s e 3,1 s; reinício do lado do Rover: 1,4 s |
| Ponta a ponta com a plataforma | 299 pedidos pela base; 1 em custódia na queda da Starlink (o que estava no ar), entregue; 30 resultados, 3 eventos de imagem e 3 originais em pedaços na plataforma, uma vez cada; 1 `ROVER_OFFLINE` por queda |

## 9. O que falta medir (ver também §18)

* **No campo** (o que a P13 deixou pronto para medir, mas não mediu — não há hardware
  aqui): alcance, vazão e perda de cada rádio no relevo do Sul de Minas, upload da
  Starlink de dia e de madrugada (ajustar `banda_bps`, MTU e tempos); escolher e cotar os
  rádios; RSSI/SNR com os OIDs reais; MCU com o rádio de emergência; vídeo leve de
  teleoperação; poste de recarga; 4G até a base.
* **P14 — a base no SaaS**: a base como dispositivo da plataforma (identidade própria,
  cadastro das chaves de enlace pela plataforma em vez do `pares.json` à mão, estado da
  base no console da nuvem), `politica_enlace` na criação da missão, custódia longa (a
  plataforma aceitar um repasse atestado pela base além dos 300 s), frota com vários
  Rovers numa base.

## 10. Malha com repetidoras (P13)

`rover/valtexa_rover/enlace/malha.py` + modo `valtexa-base repetidora`
(`base/valtexa_base/repetidora.py`). Liga com `"malha": {"ativa": true, ...}` na base e no
Rover — **tudo ou nada por fazenda**.

```
Rover ──salto──▶ repetidora ──salto──▶ repetidora ──salto──▶ base
  │  cada salto: o protocolo da P12 inteiro (cripto por salto, ARQ, fila persistente, P0–P4)
  └─ fim a fim: a origem guarda a cópia até o destino confirmar; caminho morre no meio →
     reenvia por outro; o destino deduplica pelo id
```

* **Repetidora** = nó solar (computador pequeno, SD industrial/eMMC, rádio, painel, bateria,
  controlador de carga) que **guarda e encaminha**: sem próximo salto, a mensagem fica no
  disco dela; reiniciou, continua. Não fala com a nuvem.
* **Rota pela qualidade medida** (vetor de distâncias): custo de um enlace =
  `(0,01 s + RTT/2 + 9600/banda) / (1 − perda)` (o tempo esperado para levar 1200 B; perda
  multiplica, como o ETX); rota = soma + 30 ms por salto. Anúncio no batimento (0,5 s), com
  **reverso envenenado** e teto de 8 saltos; anúncio velho (> 3 s) não vale.
* **Troca de rota**: na hora se o próximo salto morreu/calou (vizinho calado há 1 s custa
  +2 s) ou se a nova custa < 50 %; senão só < 80 % por 2 s (histerese). Medido no emulador:
  **~1,1 s** do instante físico da queda até a rota trocar.
* **P0/P1 por duas rotas** (próximos saltos diferentes) na origem; no meio do caminho, uma
  só (duplicar a cada salto multiplicaria as cópias). Laço cortado: cada repetidora lembra
  `(id, tentativa)` que já passou.
* **Confirmação fim a fim autenticada**: HMAC com o DH estático das pontas (Rover ⇄ base) —
  uma repetidora comprometida não consegue fazer a origem apagar a cópia; ela pode
  descartar (negar serviço), não fingir entrega. Os dados continuam assinados fim a fim
  (Ed25519) e o recibo da plataforma vale também aqui.
* **Bateria fraca** (`bateria` no `repetidora.json`): abaixo de 40 % a repetidora anuncia
  custo maior (até 2 s; abaixo de 15 %, 5 s) — as rotas saem dela antes que ela apague.
* Testes: `rover/tests/test_malha.py` (15, emulador: 3 saltos nos dois sentidos, qualidade
  contra número de saltos, repetidora morrendo no meio da missão, guarda-e-encaminha com
  reinício, histerese, bateria, P0/P1 por duas rotas, teleop, RPC, laço, ack forjado, P4) e
  `base/tests/test_repetidora.py` (UDP real: o Runtime fala com a nuvem por uma repetidora;
  ela cai e a outra assume).

## 11. Levantamento de cobertura (P13)

* **Registro** (`enlace/levantamento.py`): `"levantamento": {"ativo": true}` no
  `hardware.json` (Rover) e no `base.json` (base). A cada 1 s, uma linha JSON por vizinho e
  rádio: RTT, perda, vazão, RSSI/SNR (quando o rádio expõe) **com a posição RTK** (sem
  `fixed`/`float`, não grava). A base grava a visão dela com a posição que o Rover manda no
  batimento.
* **Análise** (`valtexa-base levantamento --entrada rover.jsonl base.jsonl --saida pasta
  --base-pos=-21.75,-45.25`): `cobertura.json` (o mapa que vai para o Rover),
  `grade.csv` (por célula de 10 m e por enlace), `relatorio.md`, `relatorio.json` e
  `mapa.svg`. Classe da célula: boa (≥ 80 % das amostras boas), morta (< 50 % vivas) ou
  marginal; zona morta = células mortas ligadas.
* **Onde pôr repetidora — guloso sobre os dados medidos** (sem os arquivos de terreno da
  IA): (1) **alcance demonstrado** da base — a maior distância até onde todas as faixas de
  25 m tiveram ≥ 90 % de enlace bom; a repetidora recebe 0,8 × isso; (2) candidatas =
  células onde o Rover teve enlace **bom com a base** (a repetidora ali alcança a base; o
  mastro é mais alto que a antena do Rover); (3) ganho = tempo que o Rover passou nas
  células mortas a até R da candidata; (4) escolhe a de maior ganho (empate: a mais perto do
  que cobre), marca e repete; depois da primeira, valem também candidatas "em cadeia"
  (confiança menor). Cada sugestão vem com a explicação. **É sugestão para medir no
  ponto**, não a resposta.
* No perfil simulado de cafezal (`enlace/cafezal.py`: ruas de 3,5 m, copa, morro fazendo
  sombra a leste): a análise acha a zona morta atrás do morro (81 células, 8.100 m²),
  alcance demonstrado 200 m, sugere 1 repetidora na beira do morro cobrindo 100 % do tempo
  morto; com ela "instalada", o novo levantamento não tem zona morta
  (`base/tests/test_levantamento.py`).

## 12. Missão ciente do enlace e política de perda de enlace por missão (P13)

* `enlace/travessia.py` (`"cobertura": "/etc/valtexa/cobertura.json"` no `hardware.json`):
  com o mapa e a rota assinada da missão (`segments[].path`, `[lon, lat]`), o Rover olha
  20 s à frente. Zona morta adiante → **antecipa a sincronização** (o laço do Runtime roda
  um passo grande de sync), manda à base um **aviso de travessia** (zona, duração prevista,
  hora de saída — o console mostra "em travessia"; o PARAR do console passa a valer a
  travessia + 60 s), **registra** em `travessias.jsonl` (prevista × real, fila na entrada,
  tempo até sincronizar) e, **ao voltar**, sincroniza tudo já.
* **Política por missão** (`PoliticaDaMissao`, no corpo assinado):
  * `politica_enlace` explícita: `continuar_sem_enlace` (padrão não),
    `atravessar_zonas_mapeadas` (padrão sim), `travessia_max_s` (120), `tolerancia_s`,
    `voltar_apos_s` (pausado há tanto tempo → `enlace.json` pede à navegação o retorno ao
    último ponto com enlace), `fechar_aplicacao`;
  * sem ela, derivada do `offline_policy` que a plataforma já assina: **pulverização nunca
    atravessa às cegas** (pausa, `fechar_aplicacao: true`, retorno depois da graça);
    varredura atravessa zona **mapeada** até `min(120, grace_seconds)` e pausa na perda
    **inesperada** (como na P12);
  * a perda dentro de zona mapeada e dentro da duração prevista × 1,5 + 15 s é esperada
    (`acao: "travessia_planejada"`); passou disso, é inesperada (pausa).
* O Runtime **não move** o robô: `enlace.json` ganhou `politica`, `travessia`,
  `fechar_aplicacao` e `retorno` — a navegação e o MCU obedecem. **Parar não depende disto.**
* Testes (`rover/tests/test_travessia.py`, rádio do perfil de cafezal): atravessa ~225 s de
  sombra sem pausar e sem perder P2/P3, aviso ≥ 10 s antes; pulverização pausa, fecha a
  aplicação e pede o retorno; perda fora do mapa pausa; travessia que passa do teto pausa.

## 13. Relógio: chrony com GNSS (P13)

* **Rover**: `rover/deploy/chrony/valtexa-gnss.conf` — NMEA do ZED-F9P pelo `gpsd` (SHM 0)
  travando o **PPS** (TIMEPULSE num GPIO, `/dev/pps0`), NTP da base pelo rádio como reserva,
  `makestep 1.0 3` (o Jetson não tem bateria de RTC). **Base**:
  `base/deploy/chrony-base.conf` — GNSS próprio (o da estação RTK) + NTP pela Starlink de
  reserva; serve hora aos Rovers e repetidoras pela LAN dos rádios.
* O ensaio `relogio` (§6 do `VALIDACAO_ROVER.md`) lê `chronyc -c tracking`/`sources` nos
  dois lados: sincronizado, fonte GNSS/PPS, |offset| ≤ 10 ms, e o atraso contra a hora
  assinada da plataforma ≤ 1 s. **Não testado em hardware** (formato do chrony 4.x).

## 14. Ensaio de 24 h SIMULADO (P13)

`python -m valtexa_rover.enlace.ensaio24h --saida relatorio.json` (~14 min de máquina;
`--curto` 2 h, `--minimo` 40 min — este roda na suíte). **Tudo simulado**: relógio virtual,
rádios emulados, perfil de cafezal. Rover ⇄ base (sub-GHz + alta vazão, qualidade do perfil
na posição do Rover a cada segundo: oscila ao longo da rua, some na sombra do morro), Rover
⇄ repetidora no topo do morro, repetidora ⇄ base. Dia: Rover na doca à noite, nas ruas das
06h às 18h a 0,8 m/s; **Starlink cai** 01:00–01:45 e 15:10–15:40 (chuva, que também soma
5 % de perda na alta vazão); **base sem energia** 13:00–13:04; **repetidora morre**
10:00–10:50. Tráfego em escala reduzida: P0 a cada 10 s, P1 a cada 1 s, P2 a cada 5 s, P3 a
cada 1 s, P4 de 200 KB a cada minuto; P2/P3 vão até a "nuvem" como a sincronização do
Runtime (guardados no Rover até o aceite). Relatório completo:
[`docs/ensaios/enlace-24h-simulado.json`](ensaios/enlace-24h-simulado.json).

Números desta execução (24 h simuladas em 14 min de máquina; determinístico, semente 13):

| Medida | Valor |
|---|---|
| **Zero perda de P0 a P3** | **sim**: 59.711 registros P2/P3 criados, **59.711 aceitos pela "nuvem" uma vez cada** (28 cópias repetidas absorvidas pela deduplicação da plataforma), 0 pendentes no Rover; P4: 720/720 originais de 200 KB |
| P0/P1 que não chegaram na validade | 1.380, **todos sem caminho** (rádio do próximo salto morto de fato: Rover na sombra com a repetidora apagada); 0 com caminho degradado; **0 com caminho bom**. Comando vencido nunca é aplicado; quem pediu repete com assinatura nova |
| Disponibilidade no enlace (entregue no prazo da classe) | P0 (2 s): **98,5 %** · P1 (2 s): **97,0 %** · P2 (15 s): **98,4 %** · P3 (60 s): **97,4 %** — o que falta é a repetidora morta com o Rover na sombra (6 travessias de ~230 s sem caminho nenhum) e os 4 min da base sem energia; **com caminho, P1 chegou no prazo em 100 % das vezes** (41.163 de 41.163; 12 chegaram depois de 2 s, máx. 3,65 s) |
| Latência de P1 (base → Rover, 41.175 comandos) | **p50 50 ms, p95 150 ms, p99 300 ms**, máx. 3,65 s (resolução do relógio do ensaio: 50 ms) |
| Tempo de troca de **rota** (do instante físico em que o rádio do próximo salto morre até a rota trocar) | **1,05 s** (p50 = p95 = máx., 22 trocas medidas; 7 quedas sem alternativa) |
| Tempo de troca de **enlace** com a base (alta vazão morre → o lote vai pelo sub-GHz) | **p50 0,9 s, p95 1,0 s, máx. 1,05 s** (347 trocas) |
| Interrupção de P1 nas trocas | **nenhum episódio** fora da repetidora morta (P0/P1 vão por todos os rádios e por duas rotas) |
| Starlink fora (45 min de noite, 30 min de chuva) | nada perdido: o Rover guardou e a base disse "sem internet"; tudo entrou na volta |
| Base sem energia (4 min) | voltou do disco, enlaces refeitos sozinhos, nada perdido |

**Achado para o campo**: com o rádio de alta vazão oscilando com a copa ao longo das ruas,
o "melhor enlace" do lote mudou 2.002 vezes em 24 h (uma a cada ~21 s de operação), mesmo
com a regra de estabilidade (no perfil de 40 min, que passa mais tempo na sombra, a regra
levou de 253 para 7 trocas; o dia de 24 h não foi rodado sem ela). Cada troca custa ~1 s de lote
parado, sem perda. No campo: medir a oscilação real (o levantamento mostra por rua) e, se
for assim, subir `estabilidade_s` ou baixar o `banda_bps` do rádio de alta vazão nas ruas
marginais.

## 15. Procedimento de campo

**Antes de instalar** (levantamento):

1. Base provisória (tripé + rádios + mini PC no nobreak), no lugar candidato do mastro.
2. Rover com `"levantamento": {"ativo": true}` e RTK fixo percorrendo **todas** as ruas
   (missão de varredura comum, devagar), de dia, sem chuva — e de novo num dia de chuva se
   der; base com `levantamento` ligado também.
3. `valtexa-base levantamento --entrada ... --base-pos=lat,lon`: ver `relatorio.md` e
   `mapa.svg`. Zona morta grande → testar outro lugar de mastro antes de cimentar.
4. Para cada repetidora sugerida: levar o rádio ao ponto (ou ao topo de morro mais
   próximo), refazer o levantamento das ruas da zona morta. Só então fixar.
5. Instalar de vez; refazer o levantamento completo; copiar o `cobertura.json` final para
   cada Rover (`"cobertura"` no `hardware.json`).

**Mastro e antenas**: a base no ponto mais alto com energia e Starlink com céu limpo
(Starlink longe de árvore e do próprio mastro); antenas do sub-GHz e da alta vazão
separadas verticalmente (≥ 1 m) para não se ofuscarem; setorial da alta vazão apontada para
o talhão; aterramento e para-raios no mastro; cabos com pingadeira.

**Repetidoras**: no topo do morro que faz sombra (onde a análise apontou), painel voltado
ao norte com inclinação ≈ latitude + 10°, bateria para ≥ 3 dias sem sol, controlador de
carga com leitura de bateria ligada ao `bateria` do `repetidora.json`; caixa ventilada à
sombra; `chrony` com o NTP da base.

**Validação**: FASE ENLACE (`docs/VALIDACAO_ROVER.md` §6) com o técnico desligando de
verdade um rádio, a Starlink e a energia da base (modo manual).

**Rotina de manutenção**:

* diária (automática): o console da base mostra cada Rover, enlace, RTT, perda, quedas,
  custódia e travessias; `/metricas` no Prometheus; alarme quando um enlace fica degradado;
* semanal: olhar `estado.json` de cada repetidora (bateria, rotas, fila); conferir que o
  ensaio `relogio` passa;
* mensal: limpar painel solar e conferir a bateria (tensão em repouso); refazer o
  `enlace_rssi` nos pontos críticos e comparar com o levantamento (antena desalinhada,
  conector oxidado, árvore crescendo na visada aparecem aqui);
* depois de chuva forte/raio: conferir os rádios (a malha já terá desviado; o console diz
  qual vizinho sumiu);
* safra nova (copa maior): refazer o levantamento das ruas marginais.

## 16. A base na plataforma (P14, 10/10/2026)

* **Dispositivo da plataforma:** a base é o modelo `FARM_BASE_V1` (tipo `gateway`), com a
  identidade Ed25519 dela criada no primeiro boot:
  `valtexa-base provisionar --url ... --serial ... --identidade .../identity.json`.
  O token de uso único vai pela entrada padrão e só por HTTPS, como no Rover.
* **Retrato assinado** (`valtexa_base/plataforma.py`):
  * vai a cada `plataforma.intervalo_s` (30 s) em `POST /v1/device/telemetry`, no campo
    `health.base`;
  * leva: internet/Starlink, fila do uplink por prioridade, custódia, cada Rover com cada
    rádio (estado, RTT, perda, vazão, RSSI/SNR), repetidoras e disco;
  * sem internet não entra em fila: o próximo substitui o anterior. Os dados dos Rovers
    seguem o caminho deles.
* **Plataforma:**
  * a saúde é padronizada com teto e faixa (`services/saude_rover._base`);
  * `services/estacao_base.py` calcula o **caminho** de cada Rover (nuvem ⇄ base ⇄ rádios ⇄
    Rover) pelo retrato mais novo, de até 5 min, que o cita; sem isso, `direto`;
  * rotas `GET /v1/platform/bases` e `/v1/platform/bases/{id}`;
  * o painel do centro de comando traz `caminho`.
* **Alarmes** (`services/alertas.py`), no sistema de alertas e avisos que já existe:

  | Alarme | Quando dispara |
  |---|---|
  | `base_sem_contato` | 5 min sem contato: Starlink fora ou base sem energia. Substitui o `rover_offline` para a base |
  | `enlace_degradado` | Rover sem nenhum rádio, ou perda ≥ 30% no melhor rádio. Zona morta mapeada não conta |
  | `fila_base` | mais de 50 pedidos P0–P3 esperando a Starlink |
  | `repetidora_bateria` | repetidora abaixo de 20% de bateria ou sem responder |

* **Console:**
  * cartão **Caminho** no centro de comando (trechos com cor e cada rádio com a medida);
  * tela **Bases da fazenda** (`/plataforma/comando/bases`): Starlink, fila (urgentes e
    lote), custódia, disco, Rovers e rádios, repetidoras.
* **OTA da base:**
  * é o mesmo `OtaManager` do Rover, generalizado (`pacote="valtexa_base"`,
    `tipos=("runtime",)`): assinatura, download retomável, instalação lado a lado, teste
    de boot e volta sozinha;
  * a unidade systemd sobe pelo `valtexa_rover.launcher`;
  * a base procura atualização a cada 5 min com internet e reinicia para subir na versão
    nova;
  * pacote do Rover ou de configuração destinado à base é recusado.
* **Testes:**
  * `saas/tests/test_estacao_base.py` (5);
  * `saas/tests/test_base_ota.py` (2);
  * `base/tests/test_plataforma.py` (2);
  * o ponta a ponta `saas/tests/test_base_fazenda.py`, que agora provisiona a base e
    confere o caminho no painel enquanto o Rover trabalha pela base;
  * `web/src/lib/enlace.test.ts` (4).

## 17. Chaves do rádio e mapa de cobertura pela plataforma (10/10/2026)

Nada mais é copiado à mão para o robô ou para a base.

**Chaves do rádio** (`services/chave_de_enlace.py`):

1. O Rover publica a pública X25519 do enlace, assinada pela Ed25519 dele:
   `valtexa-rover enlace-chave --publicar URL` → `PUT /v1/device/enlace/chave`. A
   plataforma confere a assinatura com a chave que **ela** cadastrou no provisionamento:
   ninguém publica chave em nome de outro robô. Trocar a chave fica na auditoria.
2. A base busca as chaves dos robôs da fazenda dela (`GET /v1/device/base/pares`, só
   dispositivo `gateway`; outro recebe 403) a cada 5 min e **confere cada assinatura de
   novo** antes de usar. Chave nova ou trocada → reescreve o `pares.json` e reinicia o
   serviço para valer. Chave com assinatura falsa é descartada; as outras seguem.
3. A plataforma nunca vê chave privada.

**Mapa de cobertura** (`services/cobertura_talhao.py`):

1. Depois de andar o Rover com o registrador ligado:
   `valtexa-base levantamento --entrada ... --saida ... --publicar-talhao <field_id>
   --config base.json`. A base manda o mapa assinado por ela
   (`PUT /v1/device/base/cobertura/{field_id}`): grade, zonas mortas e repetidoras
   sugeridas. O `por_enlace` (pesado) fica na base. Sem internet na hora, os arquivos
   locais já foram escritos e o mesmo comando publica depois.
2. A plataforma confere o formato e guarda no talhão (migração `0031`). Talhão de outro
   cliente ou de outra fazenda recebe a mesma resposta de talhão que não existe (404).
   Fica na auditoria (`field.cobertura`).
3. **Toda missão nova do talhão leva o mapa assinado** (`mission_command_body`, campo
   `cobertura`): só a grade e as zonas mortas.
4. O Rover troca o mapa da travessia quando o da missão muda
   (`ServicoDeEnlace.cobertura_da_missao`). Sem mapa na missão, volta ao `cobertura.json`
   local, se houver. Mapa malformado não derruba nada: fica o anterior e o log diz.
5. Console: em **Bases da fazenda**, cada talhão que a base atende aparece com o
   levantamento (ou "sem levantamento"). O mapa mostra:
   * a grade boa/marginal/morta, com o norte para cima e a escala;
   * as zonas mortas e a área de cada uma;
   * as repetidoras sugeridas, com quanto do tempo sem rádio cada uma cobre.

**Provas:**

* `saas/tests/test_chave_de_enlace.py` (3) e `test_cobertura_talhao.py` (3, inclusive
  isolamento e formato inválido);
* `saas/tests/test_contrato_sistemas.py`: o relatório da análise **real** da base passa
  na validação da plataforma, e o que vai na missão o Rover lê com as mesmas zonas mortas;
* `base/tests/test_plataforma.py`: chaves conferidas e mapa publicado assinado;
* `rover/tests/test_travessia.py`: o mapa da missão chega, a política passa a usar, troca
  no levantamento novo, malformado é ignorado;
* `web/src/lib/cobertura.test.ts` (3).

## 18. O que ainda falta

* **Missão:** `politica_enlace` escolhida na criação da missão. A plataforma já assina o
  `offline_policy`, e o Rover já lê a política.
* **Custódia longa:** a plataforma aceitar um repasse atestado pela base além dos 300 s.
* **Frota:** vários Rovers numa base com o mapa de cobertura compartilhado. A base já
  atende vários Rovers; o que falta é o mapa.
* **A medir no campo (§9):**
  * alcance, vazão e perda de cada rádio no relevo;
  * upload da Starlink;
  * RSSI/SNR com os OIDs reais;
  * o rádio de emergência no MCU.
