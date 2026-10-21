# ARQUIVADO — base da fazenda e rádio, no lado da plataforma

**Arquivado em 20/10/2026.** Nada aqui é importado pela plataforma, coletado pelo pytest
(`testpaths = ["tests"]`), lido pelo ruff (`exclude = [..., "archive"]`), compilado pelo
console (`web/` só compila `web/src`) nem copiado para a imagem Docker (o `Dockerfile` copia
`valtexa/`, `simulator/`, `migrations/` e `web/`).

## Por quê

Não existe mais base da fazenda nem rádio: cada Rover tem a própria Starlink e fala com a
plataforma por HTTPS direto. A base (VALTEXA-BASE) e a rede "via base" do Rover nunca rodaram
em hardware. Decisão do Pedro, 20/10/2026 ("não tem mais rádio, apenas Starlink, porque a
base não existe mais").

## O que saiu do produto

| Peça | Era | Para quê |
|---|---|---|
| `valtexa/services/estacao_base.py` | serviço | Retrato da base (`health.base`), lista de bases, "caminho" nuvem → base → rádio → Rover |
| `valtexa/services/chave_de_enlace.py` | serviço | Chave X25519 do rádio publicada pelo Rover e buscada pela base |
| `valtexa/services/cobertura_talhao.py` | serviço | Mapa de cobertura do rádio por talhão (levantamento da base), assinado na missão |
| `valtexa/api/routers/platform_rover_rotas_da_base.py` | 6 rotas em `platform_rover.py` | `GET /v1/platform/bases`, `GET /v1/platform/bases/{id}`, `GET /v1/platform/fields/{id}/cobertura`, `PUT /v1/device/enlace/chave`, `GET /v1/device/base/pares`, `PUT /v1/device/base/cobertura/{field_id}` |
| `valtexa/services/alertas_regras_da_base.py` | trecho de `alertas.py` | Regras `base_sem_contato`, `enlace_degradado`, `fila_base`, `repetidora_bateria` |
| `valtexa/services/saude_rover_base.py` | trecho de `saude_rover.py` | Padronização do `health.base` |
| `valtexa/services/ensaios_fase_enlace.py` | trecho de `ensaios.py` | FASE ENLACE (nº 6): contas dos ensaios `enlace_*` e o `relogio` antigo (Rover + base) |
| `tests/` | `tests/` | `test_base_fazenda`, `test_base_ota`, `test_chave_de_enlace`, `test_cobertura_talhao`, `test_estacao_base`, `test_ensaios_enlace_plataforma` e a versão anterior de `test_contrato_sistemas` |
| `web/src/platform/pages/Bases.tsx`, `web/src/lib/cobertura.ts`, `web/src/lib/enlace.ts` (+ testes) | console | Tela "Bases da fazenda", mapa de cobertura, cartão "Caminho" do centro de comando e a linha do caminho no HUD da pilotagem |

Também mudou, no produto:

- `mission_command_body` não leva mais `cobertura`;
- o painel do centro de comando não tem mais `caminho`;
- `compartilhamento.POLITICA` perdeu a classe `cobertura` e a entrada `gateway`;
- o catálogo de hardware perdeu o modelo `FARM_BASE_V1`;
- o ensaio `relogio` foi para a FASE 0, só com o lado do Rover;
- `requirements-dev.txt` não instala mais `../VALTEXA-BASE`;
- `web/src/api/schema.d.ts` foi regenerado do OpenAPI atual. Ele também estava desatualizado
  antes, sem as rotas das rodadas 4 e 5.

## O que FICOU (compatibilidade com o banco)

- Colunas `device.enlace_chave`, `device.enlace_chave_em` (migração 0030) e `field.cobertura`,
  `field.cobertura_em` (migração 0031). **Migração aplicada não se reescreve.** Ninguém lê nem
  escreve mais nelas; os modelos dizem LEGADO. Para apagar, crie uma migração nova, depois de
  confirmar que nenhum ambiente persistente precisa dos dados.
- O valor `gateway` de `DeviceKind`: pode haver dispositivo antigo com ele no banco.
- Linhas antigas de `alert_rule` dos 4 tipos da base: o worker só avalia o que está em
  `alertas.REGRAS`, então elas ficam sem efeito.

## Substituído por

HTTPS direto pela Starlink de cada Rover, com a fila offline-first e o orçamento de dados do
Runtime (`VALTEXA-ROVER`). O "caminho" do Rover é sempre direto.

## Como recuperar

1. Devolva os três serviços para `valtexa/services/`.
2. Recoloque, nos arquivos de origem, os trechos das rotas, dos alertas, da saúde e dos
   ensaios, e os imports.
3. Volte `"cobertura"` em `mission_command_body`, `"caminho"` no painel, a classe
   `cobertura` e a entrada `gateway` em `compartilhamento.POLITICA`, e o modelo
   `FARM_BASE_V1` em `services/hal.py`.
4. Devolva os testes para `tests/` e as peças do console para `web/src/`. Recoloque a rota
   `comando/bases` no `router.tsx` e `caminho` em `RoverPanel` (`platform/api.ts`), e
   regenere o `schema.d.ts`.
5. Recoloque `-e ../VALTEXA-BASE[dev]` no `requirements-dev.txt`.
6. Faça o mesmo no Rover (`VALTEXA-ROVER/archive/legacy/radio-fazenda/README.md`).

O estado exato antes do arquivamento está no snapshot
`C:\Users\pedro\valtexa_snapshots\2026-10-20_antes-da-consolidacao\VALTEXA-SAAS.tar.gz`.
