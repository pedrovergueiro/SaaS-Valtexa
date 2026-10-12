# ValTexa — plataforma de agricultura robótica (cópia de trabalho na nuvem)

Rover + IA embarcada + IA na nuvem + SaaS, num repositório só (privado). Quem chega agora:
leia `docs/CONTEXTO_NUVEM.md` (regras) e `docs/BRIEF_PLATAFORMA.md` (a especificação), e
depois `docs/PROGRESSO.md` (o que foi feito, com números, e o que falta).

## O que é cada pasta

| Pasta | Produto | O que tem |
| --- | --- | --- |
| `rover/` | **VALTEXA ROVER RUNTIME** (computador embarcado) | HAL (interfaces + adapters simulados marcados), **Edge AI** (ONNX Runtime, pré-processamento do treino), Mission Manager (comando assinado), Model Manager (só modelo do registry, hash conferido), buffer circular, retenção, banco local offline-first, **Sync Engine** (chunks, retomada, prioridade), **OTA** (assinado, A/B, *rollback*), **simulador** (`valtexa_rover.sim`), serviço + systemd (`deploy/`). Python 3.11. Não importa `saas/` nem `ia/`. |
| `saas/` | **VALTEXA SAAS** (API + console) | FastAPI + SQLAlchemy + Alembic (multi-tenant, RBAC, auditoria), protocolo do dispositivo, missões, frota, **Model Registry** (com a etapa dNATY), **OTA** (publicação/alvo/acompanhamento), sincronização do Rover, ponte Edge AI → IA de nuvem, fusão por planta, relatório; console React em `saas/web`; simulador em `saas/simulator`. Python 3.11. |
| `ia/` | **VALTEXA AI PLATFORM** (VALTEXA-B) | inferência (Keras 3/torch e ONNX), fusão por planta calibrada, incidência, prescrição, treino, **pipeline dNATY** (`training/dnaty_pipeline.py`). Python 3.12. **Sem pesos aqui** (testes com dublê). |
| `docs/` | — | arquitetura, auditoria, verificação, aceite, Rover, sincronização, OTA, dNATY, estresse, observabilidade, **deploy**, **segurança** |
| `deploy/` | — | `producao/` (compose de produção) e `observabilidade/` (Prometheus, Grafana, regras) |

## Subir tudo (desenvolvimento)

`pip` do sistema é bloqueado (PEP 668): use `uv`.

```bash
# Rover
cd rover && uv venv -p 3.11 && uv pip install -e ".[dev]" && .venv/bin/pytest      # 102 testes

# SaaS (instala também o ../rover para a integração e o ponta a ponta)
cd saas && uv venv -p 3.11 && VIRTUAL_ENV=.venv uv pip install -r requirements-dev.txt
.venv/bin/pytest -o addopts="--strict-markers" -q                                  # ~12 min
.venv/bin/uvicorn valtexa.main:app --reload            # API em :8000 (SQLite, inferência simulada)
cd web && npm ci && npm run dev                        # console em :5173

# IA (torch do PyPI ou do índice CPU da PyTorch)
cd ia && uv venv -p 3.12 && VIRTUAL_ENV=.venv uv pip install -r requirements.txt -r requirements-dev.txt
VIRTUAL_ENV=.venv uv pip install --no-deps dnaty==2.2.1 scipy tqdm   # dNATY: BSL 1.1
KERAS_BACKEND=torch .venv/bin/pytest -q
```

Postgres: `TEST_DATABASE_URL=postgresql+psycopg://...` roda a suíte do SaaS no Postgres;
`DATABASE_URL=... alembic upgrade head` migra. A CI (`.github/workflows/ci.yml`) faz os
dois, mais o Rover, o console e a IA.

## Rodar o ponta a ponta

Do cadastro do cliente à auditoria, com o **`rover/` de verdade** sobre a HAL simulada
(os 31 critérios da seção 58 — ver `docs/ACEITE.md`):

```bash
cd saas
.venv/bin/python -m simulator --rover-runtime            # sobe a API (uvicorn) e roda tudo por HTTP
.venv/bin/pytest -q -s tests/test_ponta_a_ponta.py       # o mesmo roteiro contra o TestClient
```

Outros roteiros: `python -m simulator` (o simulador **legado**: drone, dock e cópia 3D);
`python -m valtexa_rover.sim --url ... --token ...` (o Rover simulado contra uma plataforma
no ar); `python -m valtexa_rover.sim.estresse --passos 50000` (estresse do Rover).

## O que é simulado (seção 55)

Hardware do Rover (câmeras, GPS, IMU, rede), o **modelo da Edge AI** no simulador
(`modelo_demo.onnx`, não agronômico), a **IA de nuvem** no SaaS em teste/simulação
(`SIMULATED_INFERENCE`), o drone que aplica. Cada resultado do Rover grava
`hardware.simulated`; o relatório da missão diz `simulated: true`.

## Produção

`deploy/producao/` (Parte 9): compose com API (réplicas) + console, worker, IA, Postgres,
Redis, MinIO (S3), Prometheus e Caddy (TLS); segredos como arquivo
(`gerar-segredos.sh`). Passo a passo em `docs/DEPLOY.md`; checklist, rotação de segredos
e testes de segurança em `docs/SEGURANCA.md`. Em produção a API e o worker **recusam
subir** com segredo vazio, padrão, curto, de exemplo ou repetido, sem Redis, com SQLite
ou com inferência simulada.

## O que ainda falta para o piloto

Tudo o que dava para fazer **em código, sem infra real**, está feito e testado (ver
`docs/ACEITE.md`: **30 OK, 1 PARCIAL, 0 FALTA** em 10/10/2026). O PARCIAL é o 25: a
aplicação é registrada pelo drone simulado.

O ponta a ponta já roda com os pesos reais do café, fotos reais e o serviço de IA de verdade
(`python -m simulator --rover-runtime --ia ... --modelo-real ... --folhas ...`). Nesse
roteiro estão ligadas a fusão calibrada, a incidência corrigida e a prescrição planta a
planta. Os **limiares do café são provisórios**: a acurácia só a coleta de campo mede.

O que falta depende de algo que não está aqui:

**Comunicação da fazenda (`docs/COMUNICACAO_FAZENDA.md` §15–§18)**

1. **Comprar e cotar:**
   * Starlink para a base;
   * mini PC da base com nobreak;
   * dois rádios de dados independentes (sub-GHz e 5 GHz em mastro), que exponham
     RSSI/SNR;
   * repetidoras solares;
   * o rádio de emergência ligado direto ao MCU.
2. **Levantamento de cobertura no talhão antes de cimentar o mastro**, depois a FASE
   ENLACE da validação em modo manual. Ajustar `banda_bps`, tempos e o custo da malha com a
   oscilação real da copa. O mapa sobe pela plataforma
   (`valtexa-base levantamento --publicar-talhao`) e vai assinado em cada missão; as
   chaves do rádio também já passam pela plataforma (§17).

**Protocolo do MCU de segurança e da navegação (Livox)**

O Runtime escreve `missao.json`, `controle.json`, `teleop.json`, `parar.json` e
`enlace.json` em `/run/valtexa`. A navegação precisa:
* ler esses arquivos;
* parar sozinha quando o `valid_until` do teleop passa;
* publicar `row_left`, `row_right`, `x_m` e `parado_em` no `navegacao.json`.

Sem isso o robô não anda sozinho com segurança.

**Depende do hardware (ainda não escolhido)**

4. Adapters da HAL (câmeras, GNSS RTK, IMU, controlador, acelerador/GPU/NPU) contra
   `rover/valtexa_rover/hal/interfaces.py`, e o **mapa de plantas de campo**
   (georreferência/odometria por linha) — hoje vem do simulador. Critério 21.
5. Computador embarcado: **LUKS**, ***secure boot***, imagem do sistema com
   `rover/deploy/valtexa-rover.service`.
6. **Drone**: não há runtime de drone nem OTA de firmware; a aplicação do ponta a ponta é
   do drone simulado. Critério 25.

**Depende de infra contratada (o código está pronto e testado contra substitutos)**

7. **Postgres** gerenciado (ou o do compose) com backup e restauração testada — a suíte
   completa passou no Postgres 16 local.
8. **Bucket S3** privado (ou MinIO com disco redundante), política mínima e `python -m
   valtexa.services.storage --ciclo-de-vida` — testado contra o `moto` por HTTP; **MinIO e
   AWS reais não foram usados**.
9. **Redis** — testado contra `redis-server` real local.
10. **Domínio + TLS** (Caddy no compose), **SMTP** (`SMTP_*`, `CONSOLE_URL`; sem ele o
   aviso fica só na central), **Alertmanager** ligado às regras de
   `deploy/observabilidade/` e Grafana. Os contêineres **não foram construídos nem
   subidos aqui** (sem daemon do Docker); o compose foi validado com `docker compose
   config` e o modo produção foi ensaiado sem Docker (duas réplicas, Postgres, Redis, S3).
11. Provedores de WhatsApp/push/SMS: só a interface (`services/notifications.py`).

**Depende de licença/contrato**

12. **Licença comercial do dNATY** (BSL 1.1) antes de servir cliente pagante com modelo
    otimizado por ele.
13. Política de retenção/expiração dos dados do cliente (o lifecycle não expira foto de
    cliente por padrão — `docs/DEPLOY.md` § 4).
14. **Imagem para a IA do contorno** (`BASEMAP_TILES` no VALTEXA-B): o ortomosaico do
    cliente ou um provedor que licencie **processamento**. A Esri (e o Google) licenciam
    exibir, não analisar: a demonstração local usa a Esri só para mostrar o fluxo.
15. **Google Maps** (opcional): ligar o faturamento no projeto do Google Cloud, ativar a
    Geocoding API e a Map Tiles API, e criar **duas** chaves restritas (servidor por IP;
    navegador por referenciador). Sem isso a busca usa o OpenStreetMap e o satélite, a Esri.
16. **Relevo** (`ELEVATION_URL`): uma fonte de DEM contratada (o público do OpenTopoData
    tem cota baixa). Sem ela o plano trata o talhão como plano e avisa.

**Lacunas de software conhecidas (pequenas, documentadas)**

- Rotação da chave de missão/OTA **sem reprovisionar** o robô (`docs/SEGURANCA.md` § 2).
- O console ainda baixa imagem pela rota da API, não pela URL assinada (só banda).
- Paginação dos registros da Edge AI no servidor (a tela mostra até 1000 por missão);
  histerese/silenciar alerta; camada da fusão calibrada no mapa.
