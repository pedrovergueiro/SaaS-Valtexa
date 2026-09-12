# Protocolo robô ↔ nuvem — v1.0

Contrato entre qualquer dispositivo da ValTexa e a plataforma. Um engenheiro
deve conseguir escrever o firmware lendo **só este documento** e o
`docs/*_INTEGRATION.md` do tipo de robô.

A referência executável é [`simulator/client.py`](../simulator/client.py). Onde
este documento e aquele código divergirem, o código está certo — e é bug do
documento.

---

## 1. Fundamentos

| | |
|---|---|
| Transporte | HTTPS, HTTP/1.1 |
| Formato | JSON (UTF-8); imagens em `multipart/form-data` |
| Prefixo | `/v1/device/**` |
| Assinatura | Ed25519 em **toda** requisição, exceto `/provision` e `/time` |
| Horários | ISO 8601 com fuso, sempre UTC |
| Coordenadas | WGS84, ordem `[longitude, latitude]` (GeoJSON) |
| Versão | cabeçalho `protocol_version` no provisionamento |

O robô **nunca pede autorização em tempo real para agir**. Ele recebe uma missão
assinada, com o polígono e as políticas dentro, e opera por ela. Se a nuvem
sumir, ele continua. É o que separa um sistema que funciona na lavoura de um que
só funciona com sinal.

---

## 2. Identidade

Cada dispositivo tem:

- `device_id` — atribuído pela plataforma no provisionamento;
- um **par de chaves Ed25519 gerado dentro do robô**, cuja privada nunca sai;
- `key_id` — nome público da credencial, vai no cabeçalho;
- a **chave pública da plataforma**, para verificar comandos recebidos.

Por que assimétrico nos dois sentidos, e não HMAC: um esquema simétrico
obrigaria a plataforma a guardar um segredo capaz de se passar pelo robô, e o
robô a guardar um segredo capaz de forjar uma missão. Ed25519 elimina os dois.
Detalhes em [`AUTHENTICATION.md`](AUTHENTICATION.md).

---

## 3. Provisionamento

Única rota de dispositivo **sem** assinatura — não teria como haver uma, já que
a credencial nasce aqui.

```http
POST /v1/device/provision
Content-Type: application/json

{
  "provisioning_token": "vtx_prov_...",
  "serial_number": "VTX-ROVER-0001",
  "public_key": "<64 caracteres hex — Ed25519 bruta>",
  "name": "Rover 01",
  "firmware_version": "1.0.0",
  "hardware_version": "rev-B",
  "protocol_version": "1.0"
}
```

```json
201 Created
{
  "device_id": "…", "tenant_id": "…", "key_id": "dk_…",
  "platform_public_key": "<64 hex>",
  "protocol_version": "1.0",
  "server_time": "2026-09-09T03:00:00+00:00"
}
```

O robô grava tudo em memória não volátil, junto com a própria chave privada.

**Erros:** `401` convite inválido ou vencido · `409` convite já usado, ou
protocolo do robô mais novo que o do servidor · `403` convite emitido para outro
número de série.

Reprovisionar **revoga as credenciais anteriores**: duas ativas significariam
duas cópias do robô podendo falar ao mesmo tempo.

---

## 4. Assinatura da requisição

### Cabeçalhos

| Cabeçalho | Conteúdo |
|---|---|
| `X-Valtexa-Key-Id` | `key_id` recebido no provisionamento |
| `X-Valtexa-Timestamp` | Unix em segundos, UTC |
| `X-Valtexa-Nonce` | 32 caracteres hex, aleatórios, **nunca repetidos** |
| `X-Valtexa-Signature` | assinatura Ed25519 em hex |

### Texto canônico

Sete linhas separadas por `\n`, exatamente nesta ordem:

```
VALTEXA-ED25519-REQUEST-V1
<MÉTODO EM MAIÚSCULAS>
<caminho, sem host e sem query>
<query string, ou vazio>
<timestamp>
<nonce>
<sha256 do corpo, em hex minúsculo>
```

O corpo vazio tem o sha256 de zero bytes
(`e3b0c442...b855`), não a string vazia.

Exemplo:

```
VALTEXA-ED25519-REQUEST-V1
POST
/v1/device/telemetry

1789012345
9f2c1a...e4
5a39a9...c1
```

Assine esses bytes UTF-8 com a chave privada e envie o resultado em hex.

**Multipart:** assine os bytes exatos do corpo montado, incluindo *boundaries*.
Monte a requisição primeiro, serialize, assine o resultado.

### O que o servidor verifica, nesta ordem

1. os quatro cabeçalhos estão presentes → senão `401`;
2. o `key_id` existe e não foi revogado → senão `401`;
3. o dispositivo não está suspenso nem aposentado → senão `403`;
4. o horário está dentro de `DEVICE_CLOCK_SKEW_SECONDS` (padrão 300 s) → senão `401`;
5. o nonce nunca foi usado por este dispositivo → senão `401`;
6. a assinatura confere → senão `401`.

A ordem é deliberada: conferir o nonce antes da assinatura permitiria a um
atacante queimar nonces alheios; conferir a assinatura antes do horário gastaria
criptografia com lixo.

**Relógio.** Se receber `401` mencionando janela de horário, chame
`GET /v1/device/time` (sem assinatura), ajuste e repita. Não é opcional: sem
relógio alinhado nada é aceito.

---

## 5. Sequência

O robô mantém **um único contador monotônico** para tudo que envia — telemetria,
eventos e observações. Ele nunca reinicia (persista entre reboots).

O servidor deduplica por `(device_id, sequence_number)`. Reenviar é seguro e
esperado: o que já entrou volta em `duplicated`, não em erro.

O servidor **não** recusa sequência menor que a última vista. Um lote preso
offline chega fora de ordem e é dado legítimo.

---

## 6. Rotas

### `GET /v1/device/time` — sem assinatura

```json
{"server_time": "...", "unix": 1789012345, "protocol_version": "1.0",
 "clock_skew_tolerance_seconds": 300}
```

### `POST /v1/device/telemetry`

```json
{
  "sync_id": null,
  "samples": [{
    "sequence_number": 1042,
    "recorded_at": "2026-09-09T03:00:00+00:00",
    "mission_id": "…",
    "lat": -22.4128, "lon": -45.4518, "alt_m": 2.1,
    "heading_deg": 91.4, "speed_ms": 1.2,
    "rtk_fix": "fixed", "hdop": 0.7,
    "battery_percent": 76.5, "battery_voltage_v": 48.2,
    "battery_current_a": 3.1, "temperature_c": 31.0,
    "energy_state": "normal", "mission_state": "running",
    "link_quality": 0.86,
    "motors": {"fl": {"rpm": 120}}, "sensors": {"wind_ms": 3.2},
    "faults": []
  }]
}
```

Máximo `MAX_TELEMETRY_BATCH` (500) por requisição. Resposta:
`{"accepted": n, "duplicated": n, "rejected": n, "errors": []}`.

Campos desconhecidos são ignorados; campos ausentes ficam nulos. Uma amostra sem
`sequence_number` é rejeitada **sem derrubar o lote**.

### `POST /v1/device/events`

```json
{"events": [{
  "sequence_number": 1043,
  "type": "low_battery",
  "severity": "warning",
  "occurred_at": "2026-09-09T03:01:00+00:00",
  "mission_id": "…",
  "payload": {"battery_percent": 18.0}
}]}
```

Vocabulário em [`EVENTS.md`](EVENTS.md). Severidade `critical` gera alerta na
plataforma.

### `POST /v1/device/sync`

Descarga do que ficou offline. Idempotente por `sync_id` **e** por sequência —
pode ser repetida à vontade, o que é o comportamento correto quando a conexão
cai no meio.

```json
{"sync_id": "sync-2026-09-09-01", "samples": [...], "events": [...]}
```

Limite: `MAX_SYNC_BATCH` (1000) registros somados.

### `POST /v1/device/observations` — `multipart/form-data`

Dois campos: `file` (JPEG/PNG/WebP) e `metadata` (JSON como texto).

```json
{
  "sequence_number": 1044,
  "mission_id": "…",
  "field_id": "…",
  "zone_id": "…",
  "captured_at": "2026-09-09T03:02:00+00:00",
  "lat": -22.4128, "lon": -45.4518, "alt_m": 1.2, "heading_deg": 91.0,
  "row_index": 42,
  "model_input_ok": true,
  "edge_summary": {"blur": 0.08, "leaf_fill": 0.81, "detections": []}
}
```

`model_input_ok` é o julgamento do robô sobre o enquadramento (folha preenchendo
o quadro). `false` manda a imagem direto para revisão humana.

`edge_summary` é o que o robô concluiu sozinho. Serve para priorizar o
processamento, **nunca para autorizar**.

Reenviar a mesma `sequence_number` devolve a observação existente, sem duplicar.
Limite por arquivo: `MAX_ASSET_MB` (64).

### `POST /v1/device/row-scans` — `multipart/form-data`

Uma passada por rua, para a cópia 3D do talhão: `metadata` (JSON) e,
opcionalmente, `file` com a nuvem de pontos em PLY binário. O formato completo,
com o layout do PLY, está em
[`ROVER_INTEGRATION.md`](ROVER_INTEGRATION.md#10-cópia-3d--uma-passada-por-rua).

Idempotente pela `sequence_number`. Recusada com `422` quando não traz planta nem
nuvem, quando o eixo não cruza o talhão, ou quando a nuvem foge do layout — a
mensagem diz o que está errado.

### `GET /v1/device/missions/current`

`204` quando não há nada a fazer. Senão:

```json
{
  "payload": {
    "algorithm": "VALTEXA-ED25519-COMMAND-V1",
    "command": "mission.execute",
    "device_id": "…",
    "sequence": 1,
    "nonce": "…",
    "issued_at": "...", "expires_at": "...",
    "protocol_version": "1.0",
    "body": {
      "mission_id": "…", "kind": "scout", "field_id": "…",
      "target_polygon": [[lon, lat], ...],
      "segments": [{"index": 0, "path": [[lon, lat], [lon, lat]]}],
      "plan": {"swath_m": 3.0, "segments": 12, "area_ha": 1.34},
      "energy_policy": {...},
      "offline_policy": {...},
      "application": null
    }
  },
  "signature": "<hex>",
  "key_id": "k1",
  "algorithm": "VALTEXA-ED25519-COMMAND-V1"
}
```

**Antes de tocar em qualquer atuador, o firmware precisa:**

1. verificar `signature` sobre o JSON canônico de `payload` (chaves ordenadas,
   separadores `,` e `:`, sem espaços) com a chave pública da plataforma;
2. conferir que `payload.device_id` é o seu;
3. conferir que `expires_at` ainda não passou;
4. conferir que `sequence` é maior que a do último comando aceito;
5. conferir que `nonce` não foi visto antes.

Falhou qualquer uma? **Descarte e reporte um evento.** Não execute e não peça
esclarecimento — um comando que não passa na verificação não é um comando.

O mesmo comando é devolvido a cada leitura, com a mesma assinatura e o mesmo
nonce. Rebuscar depois de uma queda de enlace é seguro.

### Ciclo da missão

| Rota | Quando |
|---|---|
| `POST /v1/device/missions/{id}/ack` | ao aceitar ou recusar |
| `POST /v1/device/missions/{id}/segments/complete` | ao concluir cada faixa |
| `POST /v1/device/missions/{id}/pause` | ao decidir voltar (energia, falha) |
| `POST /v1/device/missions/{id}/recharged` | recarga concluída |
| `POST /v1/device/missions/{id}/complete` | missão inteira concluída |

Recusar é informação valiosa: significa que a nuvem e o robô discordam sobre o
que é seguro, e isso precisa chegar a um humano.

```json
POST .../ack       {"mission_id": "…", "accepted": false, "reason": "polígono fora do mapa local"}
POST .../segments/complete  {"segment_index": 3, "lat": …, "lon": …, "battery_percent": 62.0}
POST .../pause     {"reason": "bateria em 19%", "lat": …, "lon": …, "battery_percent": 19.0}
```

Reportar por segmento, e não só no fim, é o que permite retomar de onde parou.

### Aplicação (só drone)

```json
POST /v1/device/applications/start
{"mission_id": "…", "started_at": "...", "tank_id": "…"}

POST /v1/device/applications/{id}/stop
{"stopped_at": "...", "amount_used_l": 4.2, "area_ha": 1.3,
 "track": [[lon, lat, vazao], ...], "stop_reason": "cobertura concluída"}
```

A trilha é o mapa de aplicação. A nuvem conta quantos pontos caíram fora do
polígono; qualquer valor acima de zero vira evento crítico. **Isso é auditoria
posterior, não controle** — quem impede a saída da área é o drone, em tempo
real.

### `POST /v1/device/session` (opcional)

Troca uma requisição assinada por um token curto, para poupar assinaturas em
enlace caro. Não substitui a assinatura em nada que mude o mundo físico.

---

## 7. Erros

| Código | Significado | O que o firmware faz |
|---|---|---|
| `400` | corpo malformado | corrigir; não repetir igual |
| `401` | assinatura, horário, nonce ou credencial | sincronizar relógio, nonce novo, uma tentativa |
| `403` | dispositivo suspenso, ou recurso de outro robô | **parar** e alertar; não insistir |
| `404` | missão/talhão inexistente | descartar a referência |
| `409` | conflito de estado (convite usado, missão encerrada) | reler o estado |
| `413` | lote ou arquivo grande demais | reduzir e reenviar |
| `422` | campo inválido | corrigir |
| `5xx` | falha do servidor | *backoff* exponencial, guardar em buffer |

**Nunca** repita um `403` em laço. **Sempre** guarde em buffer no `5xx` e em
falha de rede — perder dado por indisponibilidade é o erro mais caro do sistema.

Retentativa recomendada: 1 s, 2 s, 4 s, 8 s, 30 s, 60 s, depois a cada 60 s,
com jitter.

---

## 8. Contrato de segurança do firmware

Não negociáveis:

1. a chave privada nunca sai do dispositivo, em nenhum log;
2. nenhum comando é executado sem verificação de assinatura, destinatário,
   validade, sequência e nonce;
3. a decisão de retorno por energia é **local** e nunca espera resposta da nuvem;
4. a contenção no polígono é **local**, verificada a cada ponto;
5. na perda de enlace vale a política embarcada — ver [`OFFLINE_MODE.md`](OFFLINE_MODE.md);
6. parada de emergência é física e independente do software;
7. nenhum dado é descartado por falta de conexão.
