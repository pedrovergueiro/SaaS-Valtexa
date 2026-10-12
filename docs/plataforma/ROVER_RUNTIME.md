# VALTEXA ROVER RUNTIME (`rover/`)

O software que roda no computador embarcado do Rover (brief, seções 11, 12, 14–17, 20–22,
40, 53 e 54). Pacote Python próprio, **separado** da plataforma (`saas/`) e da IA de nuvem
(`ia/`): não importa nenhum dos dois, instala-se sozinho e roda sem internet.

> **O que é real e o que é simulado (seção 55).** Real e testado: Edge AI pelo ONNX
> Runtime, banco local transacional, buffer circular, retenção, fila de sincronização,
> Model Manager com hash, missão assinada, telemetria/saúde. **Simulado e marcado como
> simulação**: câmera (pasta de imagens), GPS (trajetória), IMU, sensores, controlador e a
> rede que cai e volta (`hal/simulated.py`; todo adapter diz `simulated=True`, e cada
> resultado grava `hardware.simulated`). **Sem pesos reais**: os testes geram um modelo
> ONNX minúsculo (média RGB → 3x4 → softmax). Desempenho do modelo real: a verificar.

## 1. Instalar e testar

```bash
cd rover
uv venv -p 3.11 && uv pip install -e ".[dev]"
.venv/bin/pytest            # 95 testes, ~25 s (inclui estresse em tamanho de CI)
.venv/bin/ruff check .
```

Dependências de execução: `numpy`, `pillow`, `onnxruntime`, `cryptography` (Ed25519 — a
stdlib não tem). Rede é `urllib` e o banco é `sqlite3`, ambos da stdlib. `onnx` só nos
testes (para gerar o modelo minúsculo).

## 2. Mapa do pacote

| Seção do brief | Módulo | O que faz |
| --- | --- | --- |
| 20, 53 HAL | `hal/interfaces.py` | contratos: `Camera`, `Gps`, `Imu`, `Sensors`, `StorageDevice`, `Network`, `AiAccelerator`, `Controller`; `Hardware` junta os adapters |
| | `hal/local.py` | adapters **reais** genéricos: disco local (com cota), HTTPS (`urllib`), *providers* do ONNX Runtime |
| | `hal/simulated.py` | adapters **SIMULADOS**: `FolderCamera`, `TrajectoryGps`, `SimulatedImu`, `SimulatedSensors`, `FlakyNetwork`, `SimulatedController` |
| 11, 14, 22 Edge AI | `edge_ai/engine.py` | pré-processamento → ONNX → softmax → rótulo → categoria (NORMAL / POSSÍVEL PRAGA / POSSÍVEL DOENÇA / ANOMALIA) + baixa confiança |
| | `edge_ai/vendor/` | `preprocess.py` e `onnx_runtime.py` **copiados byte a byte** do `ia/`; `tests/test_vendor.py` compara os SHA-256 |
| 21 Configuration | `config.py` | `rover.json`; chave desconhecida é erro |
| 21 Core | `runtime/core.py` | o laço quadro a quadro e o ciclo de vida (boot, missão, conclusão) |
| 21 Mission Manager | `runtime/mission.py` | missão no banco local; conferência do comando assinado |
| 21, 22 Model Manager | `runtime/model_manager.py` | só modelo do registry, hash conferido antes de carregar |
| 40 Event Engine | `runtime/events.py` | eventos com ID e hash, direto na fila |
| 12 Local Storage | `runtime/store.py` | SQLite WAL + `synchronous=FULL`; arquivos por hash, atômicos |
| 15 Buffer circular | `runtime/buffer.py` | N antes + evento + M depois, por câmera |
| 13, 16, 17 Retenção | `runtime/retention.py` | decide o nível de cada quadro; limpa o que já subiu |
| 18, 19, 52 Sync | `runtime/sync.py` | fila priorizada, chunks, retomada, *backoff* — ver `docs/SYNC.md` |
| 21 Telemetry, Health | `runtime/health.py` | horímetro, disco, temperatura, FPS/latência, falhas ativas |
| 21 Logging | `runtime/logs.py` | JSON por linha, arquivo rotativo |
| — | `runtime/client.py` | identidade do robô e requisições assinadas (Ed25519) |
| 24 OTA Manager | `runtime/ota.py`, `launcher.py` | pacote assinado (Ed25519), download com retomada, hash por arquivo, instalação lado a lado, saúde, troca atômica, confirmação no boot (A/B) e *rollback* — ver `docs/OTA.md` |
| 41 Simulador | `sim/` | o **mesmo** Runtime sobre a HAL simulada: campo com espaçamento, câmera de cena, rede que cai, reinício; `sim/estresse.py`; `sim/nuvem.py` (dublê) |
| — | `cli.py` | `valtexa-rover config-padrao | validar-config | status | servico` |
| Fazenda (P12) | `enlace/`, `hal/rede_base.py` | rede "via base": protocolo de enlace por rádio (multi-enlace, criptografia por salto, filas persistentes) — ver §19 e `docs/COMUNICACAO_FAZENDA.md` |

**Ainda fora:** Security do disco (cifra — LUKS/dm-crypt no sistema operacional, fora do
pacote) e *secure boot* (dependem do computador embarcado escolhido); runtime de drone.

## 3. O pipeline de cada quadro (seção 14)

```
câmera → captura → pré-processamento → Edge AI → categoria → decisão de retenção
       → disco (arquivo atômico) → transação: resultado + arquivos + evento + contexto
         do buffer + itens da fila + progresso da missão → (fila) → sincronização
```

1. **Captura** pela HAL. Câmera que falha vira falha ativa (`camera:<id>`) e um
   `HARDWARE_FAULT` (um só, não um por quadro); a missão segue com as outras câmeras.
2. **Edge AI**: o pré-processamento é o do treino (sem EXIF, *resize* bilinear do
   TensorFlow reimplementado em NumPy, escala para `[-1, 1]`). Inferência pelo ONNX Runtime
   com os *providers* do acelerador. Categoria pelo `<modelo>.categories.json` (recomendado)
   ou pelo nome do rótulo.
   * **Com o perfil `<modelo>.edge.json`** (o caso dos modelos reais, gerado por
     `python -m training.fit_edge fit` em VALTEXA-B): o quadro é cortado em **recortes de
     150 mm** no tamanho físico, pela distância medida (mediana da profundidade da OAK-D)
     e pelo campo de visão — o modelo foi treinado com folha enchendo o recorte, e uma
     lesão de Sigatoka some num quadro de 1 m reduzido a 224 px. O quadro vira evento pela
     **evidência** (`evidence` do perfil): cada recorte vira a log-razão de
     verossimilhança da faixa da sua probabilidade, por doença; o escore é a maior, entre
     as doenças, da média nos recortes com o desconto de correlação da fusão; evento
     acima de `event_evidence`, `baixa_confianca` acima de `near_miss_evidence` (original
     guardado para validação); confiança média abaixo de `anomaly_mean_confidence_below`
     → ANOMALIA. Contar recortes acima de um limiar não serve: o modelo põe ≥ 0,99 de
     doença em pedaço de folha sadia (na banana, 33% dos quadros sadios virariam evento).
     Tabelas e limiares medidos por validação cruzada por planta (seção 14).
   * Sem perfil (modelo minúsculo dos testes, demonstração): o quadro inteiro, com
     `anomaly_below` (0,30) e `low_confidence_below` (0,60).
3. **Retenção** (seções 16 e 17): NORMAL → imagem reduzida (320 px, JPEG 60) ou só
   metadados; PRAGA/DOENÇA/ANOMALIA → original + sequência do buffer; baixa confiança →
   original (nunca rebaixa a categoria). `normal_sample_every` guarda 1 a cada N normais em
   original para validação.
4. **Gravação**: o arquivo vai ao disco antes (`.part` + `fsync` + `rename`); depois, uma
   transação só grava tudo o que o quadro produziu. Queda entre os dois deixa um arquivo
   órfão, que o boot apaga. Nunca fica linha sem arquivo.
5. **Sincronização** no mesmo laço, limitada por passo (`sync_requests_per_step`), ou numa
   thread (`RoverCore.sync_forever`).

### Metadados de cada resultado (seção 16)

`id`, `device_id`, `mission_id`, `field_id`, `occurred_at`, `frame` (câmera, índice,
dimensões), `position` (lat, lon, altitude, fix, HDOP, rumo), `region` (planta/região, por
um `region_resolver` plugável — sem mapa de plantas no robô ainda, vem nulo),
`navigation` (linha de cada lado e metro ao longo dela, se a navegação publica — seção
14), `tiles` (com perfil: caixas, altura no chão e zona de cada recorte, distância,
altura e lado da câmera, campo de visão e as **probabilidades de cada recorte** — o quadro
normal sobe reduzido e a nuvem funde por planta a partir delas, seção 15), `imu`,
`sensors`, `model` (chave, versão, **SHA-256**, original/otimizado, **versão do dNATY**,
hardware-alvo), `hardware` (versão, acelerador, *providers*, **`simulated`**), `result`
(categoria, rótulo, confiança, top-3, motivo, latência), `retention` (nível, validade,
prioridade), `event_id`, `files` (papel, hash, tamanho), versões do Runtime e da Edge AI.
O resultado **é** o `AI_RESULT_CREATED` da seção 40 (um registro `kind=result`).

### Buffer circular (seção 15)

`buffer.pre_frames`, `post_frames`, `max_duration_s`, `max_side` (resolução do contexto),
`jpeg_quality`, `priority`. Por câmera; quadro mais distante do evento que
`max_duration_s` não entra; eventos sobrepostos compartilham quadros; o fim da missão fecha
as sequências abertas. Os quadros de contexto são gravados com papel `contexto-3` …
`contexto+3`, ligados ao ID do evento.

### Volume (seção 13) — medido em teste

`tests/test_retention.py`, com bytes reais (JPEG 1280x960 com textura, reduzidas e
contexto pela mesma função do Runtime, registros de uma missão real do Runtime):

| 10.000 quadros, 200 eventos (2 %) | Volume |
| --- | --- |
| Enviar tudo em resolução máxima | **6,04 GB** |
| Com a política padrão (NORMAL reduzida + eventos originais + 6 quadros de contexto) | **565 MB (9,4 %)** |
| Com NORMAL só em metadados | **385 MB (6,4 %)** |

Pipeline inteiro (200 quadros 640x480, 4 eventos, Edge AI de verdade sobre o modelo
minúsculo): 18,9 MB de originais → **1,89 MB** guardados (10,0 %).

## 4. Offline-first e reinício (seção 12)

- Sem rede, nada muda no laço: captura, IA, resultados, posição e eventos vão para o banco
  local; a fila cresce; a telemetria acumula.
- O Model Manager guarda a última designação do registry: offline, o robô usa o modelo que
  já tem **depois de reconferir o hash do arquivo**.
- Reinício no meio da missão: o boot apaga `.part`/órfãos, devolve à fila o que estava
  "ENVIANDO" (o progresso por chunk está gravado), recarrega o modelo e emite
  `MISSION_RESUMED`; o Core continua do último quadro gravado. Teste:
  `test_reinicio_no_meio_da_missao_continua_sem_perder_nem_duplicar` e, contra o SaaS,
  `saas/tests/test_rover_integracao.py`.
- Disco cheio: a retenção apaga primeiro o que já subiu e venceu, depois o que já subiu,
  depois as reduzidas NORMAL que não subiram (o resultado continua e sobe sem imagem).
  **Original de evento que não subiu nunca é apagado.** Gera `STORAGE_PRESSURE`.

## 5. Modelos no Rover (seções 9 e 22)

1. `GET /v1/device/models` (SaaS) diz, por talhão, a versão em PRODUÇÃO do registry com o
   SHA-256 do artefato (o otimizado pelo dNATY quando houver).
2. O artefato chega por um `ArtifactSource` — hoje `FolderArtifactSource` (pasta com
   `<sha256>.onnx` + `.labels.json`; em campo, a área de *staging* do OTA ou um pendrive de
   serviço). Nada é confiável por estar na pasta.
3. Antes de carregar, o SHA-256 **do arquivo** é comparado ao do registry. Diferente →
   `MODEL_REJECTED` (crítico) e não carrega. Designação sem hash → não carrega. Arquivo sem
   designação → nunca carrega. **Missão não começa sem modelo do registry.**
4. As versões (runtime, Edge AI, modelo, dNATY, hardware) vão em `POST /v1/device/session`
   quando mudam — é daí que a frota mostra conforme/divergente/fora do registry.

## 6. Missão

`RoverCore.accept_cloud_mission()` busca `GET /v1/device/missions/current` e só aceita
depois das cinco conferências do protocolo (assinatura Ed25519 com a chave pública da
plataforma, destinatário, validade, sequência e nonce — `mission.verify_command`). Para
operação sem nuvem e para o simulador, `start_mission(mission_id, field_id)`.

## 7. Plugar hardware real (adapters)

O Runtime só conhece as interfaces de `hal/interfaces.py`. Para o hardware definitivo,
escreve-se um adapter por dispositivo e monta-se o `Hardware` no programa de
inicialização do robô — nada acima da HAL muda.

```python
from valtexa_rover.hal.interfaces import DeviceInfo, Frame, HardwareUnavailableError

class CameraGigE:                       # exemplo: câmera industrial
    def __init__(self, camera_id: str, serial: str, clock): ...
    def capture(self) -> Frame:
        # dispara, recebe o buffer, codifica em JPEG (qualidade alta) e devolve Frame
        # com captured_at em UTC. Timeout/cabo solto → raise HardwareUnavailableError.
        ...
    def describe(self) -> DeviceInfo:
        return DeviceInfo("camera", "GigE <modelo>", simulated=False, detail={...})

hardware = Hardware(
    cameras=[CameraGigE("cam-0", "...", clock), ...],
    gps=GnssRtk("/dev/ttyACM0"),        # NMEA/UBX → GpsFix (fix: none/gps/float/fixed)
    imu=ImuSpi(...), sensors=SensoresCan(...),
    storage=LocalDiskStorage("/var/lib/valtexa-rover", quota_bytes=...),
    network=HttpNetwork("https://api.valtexa..."),
    accelerator=OnnxCpuAccelerator(prefer=["TensorrtExecutionProvider",
                                           "CUDAExecutionProvider", "CPUExecutionProvider"],
                                   name="Jetson Orin"),
    controller=ControladorCan(...), hardware_version="Rover Edge V1",
)
core = RoverCore(hardware, "/var/lib/valtexa-rover", DeviceIdentity.load(".../identity.json"),
                 config=RuntimeConfig.load("/etc/valtexa/rover.json"),
                 artifact_source=FolderArtifactSource("/var/lib/valtexa-rover/ota"))
core.boot()
```

Contrato de todo adapter: falha é `HardwareUnavailableError` (nunca `None` silencioso),
horário em UTC, coordenadas WGS84, `describe()` honesto (`simulated=False` só para
hardware de verdade). Para um acelerador novo (NPU), basta o *provider* do ONNX Runtime do
fabricante aparecer em `providers()`.

A identidade (`identity.json`, 0600) nasce no provisionamento: o robô gera o par Ed25519
(`runtime.client.generate_keypair`) e manda só a pública para `POST /v1/device/provision`.
A chave privada nunca aparece em log (`repr` a esconde).

## 8. Configuração (`rover.json`)

`valtexa-rover config-padrao` imprime tudo com os padrões; `valtexa-rover validar-config`
confere. Exemplo — NORMAL só em metadados, buffer maior, chunk de 1 MB:

```json
{
  "retencao": {"rules": {"NORMAL": {"tier": "METADADOS", "retention_days": 3}},
               "normal_sample_every": 200},
  "buffer": {"pre_frames": 5, "post_frames": 5, "max_side": 1280},
  "sync": {"chunk_size": 1048576}
}
```

## 9. Troubleshooting

- `valtexa-rover status --dados <pasta>` — missão, modelo ativo, fila por status e
  prioridade, telemetria não enviada, se a sincronização está bloqueada.
- `sync_blocked: true` — a nuvem respondeu `403` (robô suspenso, credencial revogada). O
  Runtime **para de insistir** (protocolo, seção 7); resolver na plataforma e limpar a
  chave `sync_blocked` do banco local.
- Itens `FALHOU` na fila: `last_error` diz o motivo (HTTP 4xx definitivo, conflito de
  hash, arquivo removido pela retenção).
- Logs em `<dados>/logs/rover.log` (JSON por linha).

## 10. OTA (Parte 5)

Ver `docs/OTA.md`. Resumo: `GET /v1/device/ota` → envelope assinado com a **chave OTA**
(vem no provisionamento, `identity.ota_public_key`) → download em pedaços com retomada →
hash do pacote e de cada arquivo → instalação lado a lado em `ota/slots/` → saúde →
ponteiro `ota/current.json` trocado de forma atômica → runtime/Edge AI/configuração ficam
em teste até o próximo boot confirmar; o lançador volta sozinho se não confirmar. Nada é
instalado com missão em execução. Modelo: vai para a pasta de artefatos do Model Manager
— quem decide qual roda continua sendo o registry.

## 11. Simulador (Parte 5, seção 41)

`valtexa_rover.sim` monta o **mesmo** `RoverCore` (Edge AI, missão, sync, OTA) sobre a HAL
simulada. Não existe um "robô de mentira" separado: o que muda é só o adapter.

```bash
# contra uma plataforma no ar (protocolo real, HTTPS):
python -m valtexa_rover.sim --url http://127.0.0.1:8000 --token vtx_prov_... \
    --dados /tmp/rover-sim --passos 120 --sem-rede 30-60
# o ponta a ponta inteiro, com a plataforma subindo sozinha:
cd ../saas && python -m simulator --rover-runtime
```

- `CampoSimulado.gerar(lon, lat, linhas, plantas_por_linha, espacamento_linhas_m,
  espacamento_plantas_m, doentes={...})` — o talhão e o "chão de verdade";
- `CameraDeCena` — fotografa a planta mais próxima do GPS (verde/vermelho/azul com ruído);
  opcionalmente anexa `VTXSIM:<rótulo>` ao fim do JPEG para o analisador **simulado** da
  nuvem (a Edge AI não lê a marca);
- `PlanoDeRede(sem_rede=[(início, fim)])`, `RoverSimulado.reiniciar()`, câmera
  indisponível por janela, `ControladorDeRota` (diz quando a rota acabou);
- `region_resolver` = o mapa de plantas do campo: cada resultado diz a planta (`region`);
- o modelo é `sim/modelo_demo.onnx` (282 bytes, SHA-256 `f29e7554…`), **não agronômico**.

O simulador antigo do `saas/simulator` (`python -m simulator` sem opção) continua como
**legado**: ele encena drone, dock e cópia 3D com um cliente próprio do protocolo
(`simulator/client.py`), que não é o `rover/`. O caminho do Rover é o `--rover-runtime`.

## 12. Implantar (Parte 5, F19)

`valtexa-rover servico --dados ... --identidade ... --config ... --hal modulo:funcao
--url https://...` é o Runtime em serviço: boot (recupera disco, retoma missão, confirma
OTA), pergunta por missão assinada a cada `--busca-missao` s, laço de captura, conclui
quando o controlador diz `route_done`, informa `ack`/`complete` à plataforma, OTA fora de
missão, SIGTERM fecha o quadro em curso. `--hal` é a função do integrador que monta a
`Hardware` real (`funcao(dados, url, clock) -> Hardware`); para homologação sem hardware,
`valtexa_rover.sim:hal_de_demonstracao` (SIMULADO).

Arquivos em `rover/deploy/`: `valtexa-rover.service` (systemd, com o lançador A/B do OTA,
`ProtectSystem=strict`, escrita só em `/var/lib/valtexa-rover` e `/etc/valtexa`),
`rover.json.exemplo` (todos os padrões, validado), `rover.env.exemplo` (URL e HAL; sem
segredo). Instale o pacote **sem** `-e`: o `PYTHONPATH` do slot do OTA precisa vencer o
`site-packages`.

## 13. Estresse (Parte 5, seção 42)

`python -m valtexa_rover.sim.estresse --passos N [--cota-mb M]` — missão longa com rede
intermitente, rajadas de 503/429, reinícios, câmera fora, queda no meio de arquivo e disco
pequeno; confere no fim que cada registro chegou **uma vez**, que todo original de evento
chegou, que a missão contou cada quadro uma vez e que a fila zerou. Números em
`docs/ESTRESSE.md`.

## 14. Rover V3 (Jetson Orin NX) — instalar no hardware

Adapters em `valtexa_rover/hal/rover_v3.py`, montados pelo `hardware.json`
(`deploy/hardware.rover-v3.json.exemplo`):

| Peça (BOM rev E) | Adapter | Estado |
|---|---|---|
| Jetson Orin NX 16 GB | `JetsonAccelerator` (TensorRT → CUDA → CPU), `JetsonSystemMonitor` (`tegrastats`) | testado com saída real do `tegrastats`; providers só na Jetson |
| 6 × OAK-D Pro W PoE (laterais) | `OakDCamera` (`depthai` 2.x, foto parada 12 MP + profundidade alinhada) | **não rodou numa OAK-D**; SDK falso nos testes |
| u-blox ZED-F9P | `NmeaGnss` (GGA/RMC, RTK fixo/flutuante, fix velho recusado) | testado com sentenças NMEA reais |
| Xsens MTi-630 (CAN) | `XsensCanImu` (`python-can`, IDs e escalas no `hardware.json`) | decodificação testada; **IDs a conferir no MT Manager** |
| Livox Mid-360 + navegação | `NavegacaoPorArquivo` (`/run/valtexa`) | testado com o laço do serviço |
| MCU de segurança + motores | — | protocolo não definido; o Runtime não comanda movimento |

**Instalar** (JetPack 6, Python 3.10 — o pacote roda em 3.10+; conferido em 3.10.20):

```
sudo deploy/jetson/instalar.sh --ort-wheel onnxruntime_gpu-<versão>-cp310-cp310-linux_aarch64.whl
```

O ONNX Runtime com CUDA/TensorRT para Jetson vem da NVIDIA (Jetson AI Lab / Jetson Zoo),
não do PyPI: o instalador põe as dependências uma a uma e o pacote com `--no-deps`, para o
`onnxruntime` de CPU do PyPI não sobrescrever o da NVIDIA (um teste confere a lista contra o
`pyproject.toml`). Ele cria o usuário `valtexa`, o venv em `/opt/valtexa/venv`, a
configuração em `/etc/valtexa` (sem sobrescrever a existente), a unidade systemd com o
complemento `rover-v3.conf` (grupos `video render dialout`, `/run/valtexa`, cache do
TensorRT), o `can0` pelo systemd-networkd (500 kbit/s) e o nome fixo `/dev/valtexa-gnss`
para o ZED-F9P (regra udev). Com TensorRT, o último lote de recortes de cada quadro é
completado até `tile_batch`: uma forma só, um motor compilado só.

**Primeira montagem**, nesta ordem:

1. `valtexa-rover diagnostico --dados /var/lib/valtexa-rover --salvar /tmp/diag` — lê cada
   peça uma vez (câmeras com distância medida, GNSS, IMU, acelerador, disco, navegação) e
   diz qual falhou, sem identidade nem rede. Os quadros salvos servem para conferir
   foco, exposição e o lado de cada câmera.
2. `valtexa-rover provisionar --url ... --serial ... --identidade .../identity.json` — a
   chave Ed25519 nasce no robô; o token de uso único vem pela entrada padrão (ou
   `VALTEXA_TOKEN_PROVISIONAMENTO`), nunca na linha de comando; só por HTTPS; não
   sobrescreve uma identidade existente.
3. `valtexa-rover preparar-modelo banana_foliar.onnx --dados /var/lib/valtexa-rover` —
   carrega o modelo e o perfil `.edge.json` **neste** acelerador, mede um quadro sintético
   de 12 MP e copia `<sha256>.onnx` + rótulos + categorias + perfil para a área de staging
   do OTA. Sem perfil, recusa (`--sem-perfil` para forçar). Designe na plataforma o SHA-256
   impresso para o talhão.
4. `systemctl enable --now valtexa-rover`.

**Navegação.** A pilha de navegação (fora deste pacote) e o Runtime trocam três arquivos
JSON em `/run/valtexa` (o diretório é do serviço; a navegação entra no grupo `valtexa`):
`missao.json` (Runtime → navegação: a missão assinada com a rota, ou `{"id": null}`),
`navegacao.json` (navegação → Runtime: `{"mission_id", "route_done", "row_left",
"row_right", "x_m"}`) e `parar.json` (pedido de parada com motivo). `route_done` de outra
missão é ignorado; `row_left`/`row_right`/`x_m` vão em cada resultado e dão à fusão por
planta a linha e a posição exatas. Sem a navegação, a missão não termina sozinha — o
operador pode escrever `{"route_done": true}` no `navegacao.json`.

**Café (a cultura do produto).** O perfil do café pede a **cabeça sobre a torre de visão**
(bloco `head` do `.edge.json`): cada recorte passa pela torre do SigLIP 2 em ONNX
(`<sha>.encoder.onnx`, 355 MB, conferida pelo SHA-256) e pela cabeça
(`<sha>.head.npz`); a CNN sozinha acerta 6,5% no café. Para preparar:
`valtexa-rover preparar-modelo coffee_foliar.onnx --encoder framing_vision.onnx --dados ...`
— copia os seis arquivos para o staging (modelo, rótulos, categorias, perfil, cabeça e
torre). Medido em CPU de PC: ~9,8 s por quadro (70 recortes); na Jetson, a torre vai para
a GPU e o tempo precisa ser medido na bancada antes de definir a cadência das câmeras.
Limiares do café: provisórios (calibrados em mosaico de folhas; ver `MODELS.md` de
VALTEXA-B, "Café no Rover") — a primeira coleta no Sul de Minas recalibra.

**Modelos reais e limiares medidos.** `banana_foliar.onnx` e `citrus_foliar.onnx`
(MobileNetV2, 9,5 MB, entrada 224 × 224) com o perfil calibrado por `training.fit_edge`
em VALTEXA-B: plantas de três fotos (uma por andar de câmera), validação cruzada por
planta, orçamento de 5% de quadros sadios virando evento. Números em `MODELS.md` de
VALTEXA-B (seção "Edge AI do Rover"). Limite: fotos de folha agrupadas, não o Rover no
pomar — a validação de campo deve remedir com o registro do Rover.

**Correção da lente.** A `OakDCamera` lê a calibração de fábrica de cada câmera
(`readCalibration()` do depthai: Brown-Conrady ou fisheye Kannala-Brandt) e desfaz a
distorção antes de recortar (`hal/lente.py`; `cv2.remap` com o OpenCV do extra `rover-v3`,
NumPy sem ele). A foto sai pinhole com o mesmo fx, e o campo de visão efetivo
(`2·atan(W/2fx)`) vai em cada quadro (`hfov_deg`) para a IA embarcada e para a nuvem — o
tamanho do recorte em mm usa esse número, não o do perfil. `hardware.json`:
`"corrigir_lente": false` desliga; `"resolucao"` escolhe o modo do sensor. O diagnóstico
mostra, por câmera, "corrigida" ou "sem correção" (calibração ilegível).

**O que falta conferir no hardware** (não dá para testar sem ele): a fila de foto parada
e o alinhamento da profundidade da OAK-D; os IDs/escalas CAN da Xsens instalada; o
pinmux do CAN da placa-base (`mttcan`); a latência real por quadro na Orin com TensorRT
(medida aqui só em CPU de PC); o lado e a altura de cada câmera no `hardware.json`.

## 15. Fusão por planta na nuvem

Cada resultado com `tiles` vai, pelo worker do SaaS (`services/fusao_borda.py`, a cada
30 s), para `POST /fields/{id}/frames` de VALTEXA-B: as probabilidades de todos os
recortes entram na fusão por planta com a calibração medida para recortes da borda
(`<pesos>.edge-fusion.json`, `training.fit_edge fusao` — sem TTA e sem o portão de
enquadramento, que só a nuvem tem). Por isso a incidência e a prescrição contam também
as plantas **sadias**, não só os eventos que subiram em original.

A linha e o metro de cada quadro vêm da navegação (`navigation`) ou, sem ela, do GNSS
projetado no talhão (`row_azimuth_deg`, `row_spacing_m`; linhas `G1`, `G2`, ... a partir
do lado esquerdo do azimute, supondo o Rover no meio da rua). Quadro sem geometria fica
`sem_geometria` com o motivo — nada inventa posição. Cada resultado vai uma vez
(`edge_record.fusion_status`; a IA recusa o mesmo `frame_id`), e a passada da missão só é
fechada depois que os resultados chegaram (o `frames_done` do `MISSION_COMPLETED`, ou 6 h
sem resultado novo). O relatório da missão traz `calibrated_fusion` (incidência da IA e
quantos resultados entraram). Rotas: `GET /v1/fields/{id}/plants/incidence` e
`POST /v1/fields/{id}/plants/prescription` (recomendação planta a planta; recurso
`prescricao` do plano; nada é aplicado sem aprovação).

## 16. Centro de comando

Console → **Plataforma → Centro de comando** (`/plataforma/comando/<rover>`), permissão
`platform:rover:control` (só operações da plataforma). Uma tela por robô: modo, PARAR,
controle remoto, teste de cada peça, foto de cada câmera, modelo de IA, configuração,
telemetria das últimas 2 h e registro dos comandos. Rotas em `api/routers/platform_rover.py`:

| Rota | O quê |
|---|---|
| `GET /v1/platform/rovers/{id}/painel` | tudo do robô numa resposta (o console busca a cada 2 s) |
| `POST /v1/platform/rovers/{id}/comandos` | `diagnostico`, `foto`, `modo`, `parar`, `config`, `recarregar_modelos`, `reiniciar` |
| `POST .../comandos/{cid}/cancelar` | cancela um pendente |
| `POST .../teleop`, `POST .../teleop/parar` | controle remoto (só em modo `manual`; 409 fora dele) |
| `GET .../modelos`, `PUT .../modelo` | fixa um modelo no robô (ou solta) |
| `GET /v1/device/commands`, `POST /v1/device/commands/{cid}/result`, `GET /v1/device/teleop` | lado do robô |

**Assinatura.** Cada comando sai assinado como a missão (envelope Ed25519, validade de
2 min, sequência própria por robô); o Runtime (`runtime/comandos.py`) confere assinatura,
prazo e sequência (`last_remote_command_sequence`, separada da das missões) antes de
executar, e devolve o resultado. Comando forjado ou repetido é recusado e registrado.

**Controle remoto.** O console manda o ponto de ajuste a cada 250 ms; cada um vale 1 s
(homem-morto) e é limitado a 0,5 m/s e 1,0 rad/s. O Runtime busca `/device/teleop` a cada
volta do laço e escreve `/run/valtexa/teleop.json` (`{"v", "w", "valid_until", "seq"}`);
sem ponto válido (204 ou rede caída), escreve zero. **A navegação tem de parar sozinha
quando `valid_until` passa** — o Runtime não comanda motor.

**Modo.** `modo` escreve `/run/valtexa/controle.json` (`{"modo": "autonomo"|"manual"|
"pausado"|"parado", "at"}`); `parar` também escreve `parar.json` com o motivo. Quem move o robô é a
pilha de navegação e o MCU de segurança, que precisam ler esses arquivos (protocolo do MCU
ainda não definido).

**Configuração.** `config` mescla o JSON no `rover.json`, valida, grava de forma atômica
(guarda `rover.json.anterior`) e reinicia o serviço (código de saída 75; o systemd sobe de
novo). Predefinições no console: **coleta** (`retencao.normal_sample_every = 1`, guarda
toda foto em original — para validação e treino) e **normal**.

**Modelo fixado.** Um modelo fixado no robô vale para os talhões da mesma cultura, acima da
designação do talhão; soltar volta à designação. `recarregar_modelos` força a busca.

## 17. Validação de campo (rótulo do agrônomo → recalibração e treino)

1. Missão em modo coleta sobre fileiras de pés numerados.
2. O agrônomo anota cada pé (`PUT /v1/fields/{id}/validacao/{missão}/{pé}`: `sadia`,
   `ferrugem`, ... com a incidência em %; permissão de revisão de diagnóstico).
3. `GET .../validacao/{missão}/relatorio`: robô contra agrônomo (positivo do robô =
   `suspeita`/`doente`/`revisar`), com intervalo de Wilson.
4. `GET /v1/fields/{id}/validacao.csv` → `rotulos.csv` (`field_id,plant_id,label,pass_id`).
5. Recalibrar em VALTEXA-B com o registro do campo (`FIELDS_TILE_LOG=true`):
   `python -m training.fit_edge fit --model coffee-foliar --frames <registro>.jsonl --labels rotulos.csv`
   e `python -m training.fit_fusion fit --model coffee-foliar --frames <registro>.jsonl --labels rotulos.csv --fields-dir fields`.
6. Treino: `python scripts/exporta_originais.py --mission <missão> --dest originais/`
   (só registros com consentimento de treino) e
   `python -m training.import_campo --labels rotulos.csv --registro <registro>.jsonl --originais originais/ --out data/coffee-campo`
   — recortes de pés sadios entram como `Healthy`; os de pés doentes vão para `_revisar`
   (nem todo recorte de um pé doente tem lesão).

Guia de validação do robô inteiro (fases, critérios, o que comprar):
https://claude.ai/artifact/KiKdRqL7X6i9Cf73s4TdDn

## 18. Ensaios automáticos (Parte 11, rodada 3)

Pacote `valtexa_rover/ensaios/` — guia completo, critérios e portões em
[`docs/VALIDACAO_ROVER.md`](VALIDACAO_ROVER.md).

| Arquivo | O quê |
|---|---|
| `ensaios/base.py` | `Param` (tipo, faixa, obrigatório), `Contexto` (hardware, relógio, fontes, progresso, cancelamento), `rodar()` → laudo padrão (`status`, `criterios`, `medidas`, `amostras`, `simulado`) |
| `ensaios/{calor,cameras,profundidade,gnss,imu,seguranca,rede,energia}.py` | um ensaio por peça; cada um diz em `hardware_real` o que falta conferir no robô |
| `ensaios/estatistica.py` | percentis, CEP50/CEP95/2DRMS, inclinação pela gravidade — refeitas na plataforma |
| `ensaios/__init__.py` | `CATALOGO`, `fontes_do_runtime(core)` (carga = modelo ativo, térmica = tegrastats, rede = canal assinado, energia = sensores) e `ExecutorDeEnsaios` (thread, um por vez) |
| `ensaios/simulado.py` | bancada **SIMULADA** com injeção de falha (câmera que perde/pula/atrasa, profundidade com viés, GNSS lento/ruidoso/com perdas, IMU com eixos trocados, navegação lenta/surda, Jetson que esquenta, rede que perde) e `RelogioDeBancada` |
| `ensaios/fase0.py` | a FASE 0 em ordem e o laudo em Markdown |

**Comando `ensaio`** (`runtime/comandos.py`): o mesmo canal assinado do centro de comando
(sequência própria, repetido/forjado recusado). Não executa na hora: inicia a thread,
manda `POST /v1/device/commands/<id>/progresso` (no máximo a cada 2 s) e, no fim, o laudo
pelo `result` de sempre — sem rede, o laudo fica guardado e vai na próxima busca.
Recusado com missão em curso ou outro ensaio rodando; `config` e `reiniciar` também
esperam o ensaio acabar, e o serviço não aceita missão com ensaio em curso. `ensaio_cancelar` `{"command_id"}` para no próximo ponto.

**HAL** (mudanças compatíveis): `ImuReading.gyro_dps` opcional (Xsens com `gyro_id` e
`gyro_escala_dps` no `hardware.json`, a conferir no MT Manager);
`parse_tegrastats` devolve também `cpu_freq_mhz`, `gpu_freq_mhz` e `temperaturas_c`
(`JetsonSystemMonitor.ultima_tegrastats()`); `NavegacaoPorArquivo.stop()` devolve o pedido
(`{"reason", "at"}`) — a navegação confirma com `parado_em` + `parada_ref` no
`navegacao.json`; o Runtime zera o `teleop.json` quando o ponto vence sem outro.

**Rodar sem plataforma**: `python -m valtexa_rover.sim fase0 --saida laudo.md` (bancada
simulada). **Com a plataforma**: `cd saas && python -m simulator --fase0`.

## 19. Comunicação da fazenda: rede "via base" (Parte 12, rodada 3)

Projeto completo, volumes e equipamento: [`docs/COMUNICACAO_FAZENDA.md`](COMUNICACAO_FAZENDA.md).
Na fazenda, o Rover não fala HTTPS direto com a nuvem: fala com a **base** (mini PC com
Starlink) por **dois ou mais rádios ao mesmo tempo**, e a base repassa à plataforma.

| Arquivo | O quê |
|---|---|
| `enlace/` | o protocolo (o mesmo código roda na base): quadros com CRC, X25519 + ChaCha20-Poly1305 por salto, filas SQLite WAL, ACK seletivo, P0–P4, redundância de P0/P1, slots de teleop, emulador de rádio |
| `hal/rede_base.py` | `ServicoDeEnlace`: nó do enlace + thread + `RedeViaBase` (a HAL `Network`) + política de perda de enlace + PARAR vindo da base |
| `deploy/hardware.rover-v3.fazenda.json.exemplo` | o bloco `"rede": {"modo": "base", ...}` |

* **Sem mudar o protocolo com a plataforma**: o `DeviceClient` assina como sempre; a
  `RedeViaBase` leva o pedido pelo enlace com a prioridade da rota e devolve a resposta.
  Sem enlace, sem resposta no prazo ou base sem internet → `NetworkUnavailableError`, que
  a sincronização já trata (o item fica na fila do Rover). Offline-first (§4) vale igual.
* **`/run/valtexa/enlace.json`**: a cada 0,5 s, a saúde de cada enlace e a ação da
  política. Sem enlace por mais de 2 s: teleop zera; missão autônoma só continua com
  `politica_enlace.continuar_sem_enlace` no corpo assinado (senão `pausado`, e volta a
  `autonomo` sozinho quando o rádio religa). **A navegação deve ler este arquivo.**
* **PARAR da base** (console local, difusão a todos): canal de controle P0 → `controle.json`
  `parado` + `parar.json` com o motivo + teleop zero. Iniciar nunca vem por aqui: missão só
  com a assinatura da plataforma (a base pode servir, sem internet, um envelope assinado
  que ela guardou — o Runtime confere assinatura, validade e sequência como sempre).
* **Chave do enlace**: `valtexa-rover enlace-chave --identidade ... --chave
  /var/lib/valtexa-rover/enlace.key` cria a chave X25519 **no robô** e imprime a pública
  assinada pela identidade; a base cadastra com `valtexa-base adicionar-rover`.
* **Parar nunca depende do enlace**: a parada de emergência é o rádio próprio ligado ao
  MCU; o Runtime não comanda motor.

**Simulado / não testado em hardware**: os rádios (só emulador e UDP no `localhost`);
números de vazão, alcance e upload da Starlink: a medir (P13).

## 20. Enlace à prova de falha (Parte 13, rodada 3)

Detalhes e números: [`docs/COMUNICACAO_FAZENDA.md`](COMUNICACAO_FAZENDA.md) §10–§15.

| Arquivo | O quê |
|---|---|
| `enlace/malha.py` | malha com repetidoras: vários saltos, rota pela qualidade medida, troca sozinha, cópia fim a fim até a confirmação (HMAC das pontas); mesma cara do nó para o RPC e a política |
| `enlace/levantamento.py` | registro da cobertura (RTT, perda, vazão, RSSI/SNR + posição RTK) e o `MapaDeCobertura` (zona morta à frente na rota) |
| `enlace/travessia.py` | missão ciente do enlace: antecipa a sincronização, avisa a base, registra a travessia, sincroniza na volta |
| `enlace/politica.py` | `PoliticaDaMissao` (`politica_enlace` ou o `offline_policy` assinado), travessia planejada, `fechar_aplicacao`, `retorno` |
| `enlace/relogio.py` | chrony com GNSS: leitura e conferência; `deploy/chrony/valtexa-gnss.conf` |
| `enlace/cafezal.py`, `bancada_malha.py`, `ensaio24h.py` | perfil SIMULADO de cafezal em morro, bancada da malha e o ensaio de 24 h acelerado |
| `ensaios/enlace.py` | FASE ENLACE: `enlace_rssi`, `enlace_latencia`, `enlace_troca`, `enlace_starlink`, `enlace_energia_base`, `enlace_travessia`, `relogio` |
| `runtime/mission.py` | `PisoDaPlataforma`: validade conferida contra `max(relógio, issued_at assinado + monotônico)` |

* **`hardware.json` (`rede`)**: `"malha": {"ativa": true, "vizinhos": {"rep-x": {"pub",
  "destinos"}}}`, `"levantamento": {"ativo": true}`, `"cobertura": "/etc/valtexa/
  cobertura.json"`, `"travessia": {"antecedencia_s": 20}`, `"exige_recibo"` (padrão `true`;
  `false` só para falar com plataforma anterior à P13), `"plataforma_pub"` (opcional; o
  Runtime liga a da identidade).
* **`/run/valtexa/enlace.json`** ganhou `politica` (origem, travessia, teto),
  `travessia` (estado, esperada, quanto ainda cabe), `fechar_aplicacao` (a aplicação tem de
  fechar) e `retorno` (`{lat, lon}` do último ponto com enlace, quando a missão pede o
  retorno). **A navegação/MCU obedecem; o Runtime não move nada.**
* **Laço do serviço**: passa a posição do GNSS ao enlace (vai no batimento — a base
  registra a cobertura do lado dela) e, quando a travessia pede, roda um passo grande de
  sincronização (antes da zona morta e na volta).
* **Respostas com recibo**: pela base, um 2xx que muda estado só vale com o recibo assinado
  pela plataforma (senão "sem rede": o dado fica na fila).

**Simulado / não testado em hardware**: rádios, repetidoras, PPS/chrony, RSSI/SNR —
só emulador, UDP no `localhost` e saídas gravadas do `chronyc`.

## 21. Estação de pilotagem e vídeo ao vivo

Na estação de pilotagem do centro de comando, o vídeo das câmeras, o **controle de
videogame**, o teclado e o joystick da tela ficam no mesmo lugar, com o painel de voo (HUD)
sobre a imagem. O HUD mostra:

* modo e fonte do comando;
* velocidade pedida e enviada, e marcha;
* bateria e RTK;
* idade do quadro e quadros por segundo;
* o caminho nuvem → base → rádio.

**Controle de videogame** (Gamepad API do navegador, mapeamento "standard"):

| Comando | Função |
|---|---|
| Analógico esquerdo | Acelera |
| Analógico direito | Vira |
| **LB ou RB segurado** | Homem-morto: soltou, o ponto vai a zero |
| **B** | **PARAR** (comando assinado) |
| ↑ / ↓ | Marcha |
| X / Y | Trocam a câmera |

O analógico tem zona morta com reescala e curva fina perto do centro
(`web/src/lib/pilotagem.ts`).

**Teclado:** W A S D ou setas (segurar a tecla é o homem-morto), espaço = PARAR, Q/E =
marcha.

Qualquer que seja a fonte, cada ponto vale 1 s no servidor e só vale em modo Manual.

**Vídeo, de ponta a ponta:**

1. A estação pede as câmeras, a taxa e o tamanho: `POST /v1/platform/rovers/{id}/video`.
   O pedido vence em 12 s; a tela renova a cada 5 s. Começar a assistir fica na auditoria
   do cliente.
2. O Runtime fica sabendo pelo cabeçalho `X-Valtexa-Video` da consulta de comandos que
   ele já faz, sem consulta a mais.
3. O `TransmissorDeVideo` (`runtime/video.py`) manda `POST /v1/device/video/{camera}`
   (JPEG assinado):
   * **em missão**, usa o último quadro que o laço já capturou e não chama a câmera;
   * **fora de missão**, usa a prévia da OAK-D (`capture_preview`, saída de vídeo separada
     da foto de 12 MP);
   * **com ensaio em curso**, não captura.
4. A **qualidade é adaptativa**: quadro que demora mais que o intervalo faz o próximo sair
   menor (de 240 px a 1280 px). O laço nunca morre: um erro vira `ultimo_erro` e segue.
5. Pela base da fazenda, cada câmera é um slot "só o último vale" em P3, com prazo de 3 s:
   quadro velho cai no caminho, nunca passa na frente de comando ou teleop, nunca
   enfileira.
6. A plataforma guarda **só o último quadro** de cada câmera por 15 s, na coordenação
   compartilhada (Redis com várias réplicas). A estação busca o último e mostra a idade.

**Contrato entre os sistemas** (`saas/tests/test_contrato_sistemas.py`): o teste lê o
código do Rover e da base e confere que toda rota que eles chamam existe no OpenAPI da
plataforma com o mesmo método. Confere também os cabeçalhos combinados e a prioridade de
cada rota no enlace.

**Provas:**

* `rover/tests/test_video.py` (10 testes, inclusive a prévia da OAK-D com SDK falso);
* `saas/tests/test_video_ao_vivo.py` (5);
* `saas/tests/test_base_fazenda.py`: vídeo pela base, rádio com 15% de perda e Rover em
  missão;
* `web/src/lib/pilotagem.test.ts` (7);
* roteiro de navegador com **controle de videogame simulado** (Edge):
  * vídeo a 222 ms de idade e 4,3 quadros/s;
  * sem LB/RB o Rover não anda; com RB, `teleop` ativo no servidor; soltou, parou;
  * B mandou PARAR e o Rover confirmou "parado".

**Não testado em hardware:** a prévia na OAK-D real e o vídeo pelos rádios reais. A banda
do sub-GHz limita a qualidade: a adaptação desce até 240 px.

## 22. Modelo pronto no boot e mapa do rádio na missão

**Pré-carga do modelo** (`runtime/core.py`, `precarrega_modelo`):

* no boot sem missão, o Runtime já carrega o modelo do último talhão (`last_field_id`) ou
  o designado ao robô. A primeira missão não espera e o painel não mostra
  "Erro: model_missing" com o robô parado;
* `model_missing` só vira falha quando uma missão roda sem modelo, ou quando um modelo
  designado não carrega (`modelo_indisponivel`);
* "já carregado" confere também o hash do perfil (`.edge.json`) e da cabeça (`.head.npz`).
  Um perfil recalibrado com o mesmo ONNX agora recarrega; antes ficava o velho na memória;
* o comando `recarregar_modelos` com o robô parado já deixa o modelo novo pronto.

**Mapa de cobertura na missão** (`hal/rede_base.py`, `cobertura_da_missao`):

* o mapa vem no campo `cobertura` da missão assinada;
* a travessia troca de mapa quando o levantamento muda;
* sem mapa na missão, vale o `cobertura.json` local, se houver;
* malformado: fica o anterior (COMUNICACAO_FAZENDA §17).

**Provas:** `rover/tests/test_precarga.py` (4), `test_model_manager.py` e
`test_travessia.py`.
