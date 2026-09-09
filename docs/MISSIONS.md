# Missões

A missão é o **único contrato de execução**. Um robô nunca recebe "vá até esta
coordenada e aplique": recebe uma missão fechada, com polígono autorizado,
produto, dose, validade e políticas de contingência.

Código: [`valtexa/services/mission_manager.py`](../valtexa/services/mission_manager.py).

---

## Tipos

| `kind` | Quem executa | O que faz |
|---|---|---|
| `scout` | rover | percorre e fotografa |
| `spray` | drone | aplica em área autorizada |
| `verify` | rover | volta ao mesmo ponto depois do tratamento |
| `transit` | qualquer | deslocamento sem trabalho |

---

## Máquina de estados

```
        DRAFT
          │  submit
          ▼
    PENDING_SAFETY ──────► BLOCKED ──┐
          │ aprovada          ▲       │ corrigido
          ▼                   └───────┘
     AUTHORIZED ──► DISPATCHED ──► RUNNING
                                     │
              ┌──────────────────────┼──────────────────┐
              ▼                      ▼                  ▼
     PAUSED_FOR_RECHARGE          PAUSED           COMPLETED
              │                      │
              └──► READY_TO_RESUME ──┘
                          │
                          └──► RUNNING

  ABORTED e EXPIRED são terminais e alcançáveis de quase todo estado.
```

As transições válidas estão em `ALLOWED_TRANSITIONS`; qualquer outra levanta
`MissionStateError` (`409` na API). Uma máquina explícita evita a classe de bug
mais cara aqui: um caminho de código que "conserta" o estado no meio de um
tratamento de erro e leva a missão a um estado que ninguém previu, com o robô no
ar.

`BLOCKED` **não é terminal**: corrigido o impedimento, a missão volta para
avaliação. Obrigar a recriar do zero faria o operador perder o histórico de por
que ela foi bloqueada.

---

## Ciclo completo

```
POST /v1/missions                     DRAFT + plano de cobertura
POST /v1/missions/{id}/approve        só agrônomo, só spray
POST /v1/missions/{id}/authorize      safety engine -> AUTHORIZED ou BLOCKED
POST /v1/missions/{id}/dispatch       assina -> DISPATCHED
POST /v1/missions/{id}/resume         do checkpoint -> RUNNING
POST /v1/missions/{id}/abort          -> ABORTED
```

Do lado do robô: `ack`, `segments/complete`, `pause`, `recharged`, `complete`.

---

## Planejamento de cobertura

A área é quebrada em faixas de vaivém (*boustrophedon*), uma por segmento.

```
┌─────────────────────┐
│ ──────────────────► │  segmento 0
│ ◄────────────────── │  segmento 1
│ ──────────────────► │  segmento 2
└─────────────────────┘
```

A largura vem, em ordem de precedência: do `plan.swath_m` que o operador pediu,
depois do descritor de capacidades do hardware. Uma constante aqui obrigaria a
alterar código para planejar com outra câmera.

Alternar o sentido não é estética: sem isso o robô voltaria vazio a cada passada.

**Limitação:** a varredura é leste-oeste e não se alinha às linhas de plantio.
Falta coletar o azimute da linha.

---

## Área padrão e a margem

Uma missão criada sem `target_polygon` cobre o talhão **menos a margem de
segurança** (`GEOFENCE_MARGIN_M`), não o talhão inteiro.

A distinção não é detalhe: a cerca virtual exige que a área da missão caiba
dentro do limite com folga. Uma missão sobre a borda exata do talhão seria
bloqueada por construção, sempre. A área operável é o miolo.

---

## Retomada

É o que torna o produto viável em área grande. Sem isso, um rover que voltou para
recarregar teria de refazer a lavoura inteira.

```
segmento concluído  ->  MissionCheckpoint {último, restantes, posição, bateria}
bateria baixa       ->  robô decide voltar  ->  PAUSED_FOR_RECHARGE
recarga             ->  READY_TO_RESUME
retomada            ->  comando NOVO, só com os segmentos que faltam
```

O checkpoint é gravado **a cada segmento**, não só na pausa: a pausa nem sempre é
ordenada — uma queda de energia ou de enlace no meio da faixa não avisa antes.

A retomada **renova a validade e assina de novo**. Reaproveitar a assinatura de
horas atrás contornaria o prazo de expiração, que é justamente o que impede
executar hoje uma autorização de ontem.

---

## Assinatura e validade

A assinatura só existe depois do parecer favorável de segurança. Missão bloqueada
não tem assinatura.

`expires_at` = autorização + `COMMAND_TTL_SECONDS` (padrão 30 min). Depois disso
`GET /v1/device/missions/current` devolve `204` — o servidor nem chega a entregar
um comando vencido — e o robô descarta se receber por outro caminho.

O envelope assinado é gravado byte a byte. O mesmo comando é devolvido a cada
leitura, com a mesma assinatura e o mesmo nonce: rebuscar depois de uma queda de
enlace é seguro, e não cria um segundo comando válido.

---

## Um robô, uma missão

`Device.active_mission_id` impede duas missões simultâneas no mesmo dispositivo.
O robô tem um corpo só, e duas autorizações seriam duas verdades diferentes sobre
onde ele pode estar.

O campo é liberado quando a missão termina — deixá-lo apontando para uma missão
encerrada travaria o dispositivo para sempre.

---

## Abortar

```
POST /v1/missions/{id}/abort   {"reason": "chuva chegando"}
```

Funciona de qualquer estado não terminal e **nunca falha por estado**. Está
disponível a praticamente todos os papéis operacionais: parar não pode depender
de permissão rara.

Abortar libera o dispositivo e registra o motivo na auditoria.
