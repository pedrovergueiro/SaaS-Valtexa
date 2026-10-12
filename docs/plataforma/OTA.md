# OTA — atualização remota do Rover (brief, seção 24)

Pacotes de **runtime**, **Edge AI**, **modelo** e **configuração**, com hash, assinatura
Ed25519, versão, instalação lado a lado, verificação de saúde, troca atômica, confirmação
no boot, *rollback* automático e registro de cada passo dos dois lados.

## Plataforma (`saas/`)

| Rota | Quem | O que faz |
| --- | --- | --- |
| `POST /v1/platform/ota/packages?kind=&version=&model_version_id=` (corpo: `.tar`) | `platform:ota:manage` (Operações, IA & Dados, superadmin) | confere o `.tar` (só arquivos regulares, sem `..`/caminho absoluto/link, sem nome repetido), calcula o SHA-256 do pacote e de cada arquivo (manifesto), guarda no object storage. **Modelo: só versão em PRODUÇÃO no registry**, e o pacote precisa conter `<sha256>.onnx` com exatamente o hash que a versão manda ao robô (otimizado, se houver). Pacote não se reescreve (`kind`+`version` únicos) |
| `POST /v1/platform/ota/deployments` `{package_id, device_ids?, tenant_id?}` | idem | um destino por robô (por robô ou cliente inteiro); robô suspenso/aposentado fica de fora (409); modelo não liberado para o cliente → 403; destino aberto do mesmo pacote não duplica. Cada destino leva o **envelope assinado**: `{deployment_id, device_id, package_id, manifest, issued_at, expires_at}` + assinatura `VALTEXA-ED25519-OTA-V1` |
| `GET /v1/platform/ota/deployments?package_id=&device_id=&tenant_id=&state=` | `platform:fleet:read` | acompanhamento: estado, detalhe, histórico, bytes servidos |
| `POST /v1/platform/ota/deployments/{id}/cancel` | `platform:ota:manage` | só antes de o robô começar a instalar |
| `GET /v1/device/ota` | robô (assinado) | os destinos abertos dele, com o envelope |
| `GET /v1/device/ota/{id}/package?offset=&length=` | robô | um pedaço (até 8 MB) — download com retomada |
| `POST /v1/device/ota/{id}/status` `{state, detail, version_running}` | robô | `pendente → baixando → verificando → instalando → verificando_saude → aplicada`; ou `recusada`/`falhou`/`revertida`. Transição fora do protocolo → 409. Robô de outro cliente → 404 |

Banco: `ota_package` e `ota_deployment` (migração **0020**), só metadados. Auditoria:
`ota.package_published`, `ota.deployment_created`, `ota.<estado>` (ator = robô),
`ota.cancelada`.

**Chave**: `OTA_SIGNING_SECRET` (env), separada da das missões
(`COMMAND_SIGNING_SECRET`); em produção é obrigatória e diferente das outras
(`Settings.production_problems`). Sem ela (desenvolvimento) deriva da das missões com
prefixo próprio. A pública vai ao robô no provisionamento (`ota_public_key`). Domínio
separado: uma assinatura de missão não vale como de pacote (teste).

## Robô (`rover/valtexa_rover/runtime/ota.py` + `launcher.py`)

1. `GET /v1/device/ota`; para cada destino: assinatura (chave OTA do provisionamento),
   destinatário, validade, tipo; destino já processado é ignorado (anti-*replay*).
2. **Nada é instalado com missão em execução.**
3. Download em pedaços para `ota/staging/<id>.tar.part`, com `fsync`; caiu → retoma do
   byte em que parou, inclusive depois de reiniciar.
4. Confere tamanho e SHA-256 do pacote e **de cada arquivo** contra o manifesto (nada a
   mais, nada a menos, nenhum caminho fora do slot).
5. Instala **lado a lado** em `ota/slots/<tipo>/<versão>/`; o atual não é tocado.
6. Saúde: **modelo** — carrega no ONNX Runtime e infere uma imagem; **configuração** —
   valida (`rover.json`, chave desconhecida é erro); **runtime/Edge AI** — compila todo
   o código e importa o pacote, versão igual à do manifesto.
7. Troca atômica do ponteiro `ota/current.json` (guarda o anterior). Modelo: vai para a
   pasta de artefatos do Model Manager — **quem decide qual roda continua sendo a
   designação do registry**, e o hash é reconferido antes de carregar.
8. Runtime, Edge AI e configuração ficam **em teste**: o lançador (`python -m
   valtexa_rover.launcher`, roda antes do Runtime, da instalação de base) conta os boots;
   o Runtime, ao terminar o boot, confirma. Passou de `max_trial_boots` (2) sem confirmar
   → **volta sozinho** ao anterior (configuração: restaura `rover.json.anterior`).
9. Cada passo: evento local (`OTA_DOWNLOADED`, `OTA_INSTALLED`, `OTA_APPLIED`,
   `OTA_ROLLED_BACK`, `OTA_REJECTED`, `OTA_FAILED`, que sobem pela fila) e informe à
   plataforma; offline, o informe fica guardado e sai quando a rede volta.

## Testes

- `rover/tests/test_ota.py` (13): modelo instalado ao lado + registry decide; recusas
  (assinatura de outra chave, outro robô, vencido, bytes adulterados); download
  interrompido + reinício retoma (cada pedaço uma vez); modelo que não carrega → falhou
  e o anterior segue; configuração em teste confirmada no boot; configuração inválida
  não entra; runtime que não confirma volta sozinho; runtime que não compila ou com
  versão errada não é trocado; nada com missão em execução.
- `saas/tests/test_ota.py` (10): publicação (só PRODUÇÃO, hash do registry, caminho
  inseguro, papéis), destino assinado, estados, isolamento entre clientes, cancelamento;
  e o **`rover/` real contra a API**: modelo com queda no meio do download e reinício
  (cada byte servido uma vez), pacote adulterado no object storage (recusado), runtime
  que não sobe (revertida, vista na plataforma).
- `test_isolamento_openapi.py` ataca um destino OTA real da vítima.

## Limites (honesto)

- **Firmware** (seção 24, "quando aplicável") não tem tipo: depende do hardware.
- O pacote passa pelo `ObjectStore.put` (limite `MAX_ASSET_MB`, 64 MB): pacote maior
  precisa de envio em partes (*multipart*), pendente.
- Runtime/Edge AI: a saúde antes da troca é "compila e importa"; a prova de que o
  Runtime novo **funciona** é a confirmação no boot (A/B). O lançador precisa estar no
  `ExecStart` do systemd (não há imagem de sistema aqui).
- Não há tela no console para OTA (só API).
