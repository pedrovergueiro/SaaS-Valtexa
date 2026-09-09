# Arquitetura

## A regra que gera todas as outras

> Nenhum resultado de IA comanda diretamente uma aplicação.

A cadeia é longa porque cada elo responde a uma pergunta diferente, e misturá-los
é o que produz sistemas que aplicam defensivo no lugar errado:

| Elo | Pergunta | Quem responde |
|---|---|---|
| Percepção | o que foi visto? | rover/drone + armazenamento |
| Diagnóstico | o que é isso? | modelos, com dupla validação |
| Recomendação | o que isso justifica fazer? | motor de decisão (regras) |
| Validação | um humano concorda? | agrônomo |
| Autorização | é permitido fazer? | safety engine |
| Execução | fazer, dentro do autorizado | robô |
| Verificação | funcionou? | segunda passada do rover |

---

## Camadas

```
┌──────────────────────────────────────────────────────────────┐
│  API HTTP  (FastAPI)                                         │
│  /v1/**  pessoas · /v1/device/**  robôs                      │
├──────────────────────────────────────────────────────────────┤
│  Dependências: identidade, tenant, permissões                │
│  valtexa/api/deps.py                                         │
├──────────────────────────────────────────────────────────────┤
│  Serviços de domínio                                         │
│  ai_pipeline · decision_engine · safety_engine               │
│  mission_manager · ingestion · twin · verification           │
│  energy · geo · hal · storage · events · audit               │
├──────────────────────────────────────────────────────────────┤
│  Modelo (SQLAlchemy 2.0) — 29 tabelas                        │
├──────────────────────────────────────────────────────────────┤
│  Postgres (produção) · SQLite (piloto) · disco/S3            │
└──────────────────────────────────────────────────────────────┘
```

### Direções de dependência

Uma seta que não existe é tão importante quanto uma que existe:

```
api  ────────►  services  ────────►  models
                    │
                    ├── safety_engine  ─X─►  decision_engine     (nunca)
                    ├── decision_engine ───►  ai_pipeline (só constantes)
                    └── mission_manager ───►  safety_engine, energy, geo
```

**`safety_engine` não importa `decision_engine`.** Se a regra agronômica ficar
errada, a segurança continua íntegra. É a dependência unilateral que torna a
camada de segurança de fato independente, e não apenas um módulo separado.

---

## O esquema, por área

| Área | Tabelas |
|---|---|
| Clientes | `tenant`, `user`, `membership` |
| Geografia | `farm`, `field`, `zone` |
| Frota | `device_model`, `device`, `device_credential`, `provisioning_token` |
| Operação | `mission`, `mission_segment`, `mission_checkpoint`, `telemetry_sample`, `device_event` |
| Percepção | `asset`, `observation`, `detection`, `diagnosis`, `decision`, `safety_evaluation` |
| Insumos | `product`, `product_batch`, `tank`, `application`, `verification` |
| Plataforma | `audit_entry`, `outbox_event`, `used_nonce` |

### Decisões do modelo

**Chave primária UUID em texto, atribuída na construção.** Permite o robô criar
uma observação offline e sincronizar depois sem renumerar. E o identificador
existe antes do `flush`, o que importa porque quase toda escrita grava uma
entrada de auditoria apontando para a linha recém-criada.

**Tudo em UTC e ciente de fuso.** `as_utc()` normaliza o que volta do SQLite, que
não guarda o fuso — comparar um horário ingênuo com `datetime.now(UTC)` levantaria
`TypeError`, e seria numa checagem de expiração de comando.

**`tenant_id` em quase tudo, indexado.** É o eixo do isolamento, e o filtro é
aplicado na consulta (`deps.scoped`), nunca confiado ao parâmetro da URL.

**Nada é sobrescrito.** Reprocessar uma imagem com modelo novo cria um
`Diagnosis` novo; o antigo fica com a versão que o produziu. É o que permite
responder, meses depois, "por que o sistema mandou aplicar naquele talhão".

**Polígonos em JSON, não PostGIS.** Um talhão tem alguns quilômetros; nessa
escala a aproximação local erra centímetros, abaixo da precisão do RTK. Ganha-se
testar a cerca virtual sem banco e rodar o mesmo código no firmware. Quando o
volume exigir índice espacial, a coluna migra mantendo o contrato de leitura.

---

## Multi-tenant

```
Tenant ─┬─ Membership ── User      (um usuário, N clientes, papel por cliente)
        ├─ Farm ── Field ── Zone
        ├─ Device ── Tank
        ├─ Product ── ProductBatch
        └─ Mission · Observation · Diagnosis · Decision · Application
```

`DeviceModel` é a exceção: o catálogo de hardware é da ValTexa e serve a todos.

O armazenamento de objetos é prefixado por cliente. Endereçamento por conteúdo
puro faria dois clientes com o mesmo arquivo compartilharem os bytes — e atender
um pedido de exclusão de um apagaria o arquivo do outro.

Pedir um recurso de outro cliente devolve **404**, não 403: 403 confirmaria que o
identificador existe.

---

## Camada de abstração de hardware

O backend nunca pergunta *qual* robô é. Pergunta o que ele consegue fazer, e a
resposta vem de `device_model.capabilities`.

```
                 NUVEM VALTEXA
                       │
          camada de abstração (hal.py)
                       │
      ┌────────────────┼────────────────┐
   Rover V1        Drone V1          Dock V1
      │                │                │
   hardware         hardware         hardware
```

Consequências práticas: trocar LiDAR, câmera, GNSS, controladora ou fabricante do
motor é cadastrar um modelo; integrar o robô de um parceiro também. O
planejamento de cobertura lê `swath_m` do descritor, o safety engine lê
`has_spray`/`has_rtk`/`tank_count`, e a política de energia lê
`cruise_speed_ms`/`endurance_minutes`.

Capacidade não declarada é capacidade **ausente**. Um dispositivo que não declara
`has_spray` jamais recebe missão de pulverização, mesmo que fisicamente consiga.

---

## Eventos

*Outbox* transacional: o evento é gravado na **mesma transação** que mudou o
estado. Ou os dois acontecem, ou nenhum.

```
transação:  estado alterado  +  outbox_event
                                     │
                          drenador (thread ou worker)
                                     │
                                 handlers
```

Sem isso, um processo que morre entre "missão autorizada" e "avisar quem
interessa" deixaria o sistema num estado que ninguém observou. A entrega é
ao-menos-uma-vez, então **todo handler é idempotente** — um handler não
idempotente aqui vira aplicação duplicada no campo.

---

## Onde vive cada regra

| Regra | Arquivo |
|---|---|
| O que é dupla validação | `services/ai_pipeline.py::combine` |
| O que uma resposta justifica | `services/decision_engine.py::decide` |
| O que pode acontecer fisicamente | `services/safety_engine.py::check_mission` |
| Transições válidas de missão | `services/mission_manager.py::ALLOWED_TRANSITIONS` |
| Quem pode o quê | `security/rbac.py::ROLE_CAPABILITIES` |
| Cerca virtual e cobertura | `services/geo.py` |
| Quando voltar por energia | `services/energy.py` |
| O que fazer sem nuvem | `mission_manager.default_offline_policy` |

Nenhuma delas está em rota, em tela ou em consulta SQL espalhada.

---

## Escala

O que cresce primeiro é `telemetry_sample`: um rover a 1 Hz numa jornada de 4 h
produz ~14 mil linhas por missão.

Caminho previsto, em ordem: (1) particionar por mês; (2) agregar amostras antigas
em janelas de 1 min e descartar o cru após 90 dias; (3) mover a série para um
banco de série temporal, mantendo `device_event` no relacional — evento é o que
precisa sobreviver íntegro para a auditoria; telemetria é amostragem.

`observation`, `diagnosis` e `audit_entry` crescem em ritmo muito menor e ficam.
