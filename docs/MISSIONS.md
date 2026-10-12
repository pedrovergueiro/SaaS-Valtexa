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

As faixas seguem as linhas de plantio: a direção vem de `row_azimuth_deg` do
talhão (0 = norte-sul, 90 = leste-oeste). Sem azimute cadastrado, a varredura é
leste-oeste. Não é detalhe: atravessar as linhas pisoteia a cultura e obriga o
rover a passar por cima de cada fileira.

---

## Corrigir a rota

O planejador conhece a geometria do talhão e o que a leitura de imagem viu. Não
conhece que aquela cabeceira atola em maio, nem que o portão do fundo está
trancado desde a safra passada. Quem conhece é quem opera — e, até a rota se
tornar editável, esse conhecimento não tinha por onde entrar: a validação humana
era aprovar ou recusar, nunca corrigir.

Dois caminhos, porque são duas situações:

| | Rota | Quando |
| --- | --- | --- |
| Desenhar | `PATCH /v1/missions/{id}/route` | a premissa está certa e um pedaço específico não serve |
| Recalcular | `POST /v1/missions/{id}/replan` | mudou uma premissa (faixa, azimute, folga) — ou a leitura de terreno chegou depois |

O segundo uso do replanejamento é o mais comum e o menos óbvio: a missão nasce
antes de alguém rodar o encaixe de contorno, então a rota original não contorna
nada. **Replanejar sem parâmetro nenhum ainda faz trabalho** — é o que faz a mata
entrar na conta.

O operador manda só o percurso. Metros, energia e segmentos são derivados no
servidor: aceitar a metragem do cliente abriria a porta para o número na tela
discordar do que o robô vai cumprir.

### O que a edição não permite

Uma rota que saia da área da missão, ou que atravesse obstáculo intransponível,
é recusada com o número da passada. Sem isso, editar à mão seria o caminho para
furar a cerca virtual pela porta da frente — bastaria desenhar uma passada por
cima da mata. O operador conhece o terreno melhor que o planejador; não conhece
melhor que o limite do talhão, que é contrato, nem que a mata, que é física.

A rota só se mexe em `DRAFT`, `PENDING_SAFETY` e `BLOCKED` (`EDITABLE_STATES`).
A partir de `AUTHORIZED`, a assinatura cobre um percurso específico: trocá-lo por
baixo faria o robô executar o que ninguém aprovou e que a assinatura não
descreve. Para mudar depois disso, aborta-se e cria-se outra — o custo é um
registro a mais na trilha, e é exatamente o registro que se quer ter.

`BLOCKED` é editável porque corrigir a rota é *o* jeito de destravar uma missão
barrada por área; obrigar a recriar perderia o parecer que explicou o bloqueio.

Toda troca vira `mission.route_updated` na trilha, com o resumo sha256 da rota
antes e depois. Guardar só a rota nova diria que a missão *tem* tal percurso, não
que ela *passou* por outro — e a pergunta de uma apuração é a segunda.

---

## Relevo

O planejamento trata o talhão como plano **até alguém configurar
`ELEVATION_URL`**. A diferença aparece em três lugares que custam dinheiro ou
equipamento: a conta de autonomia (subir consome muito mais), o ângulo de
tombamento, e a direção das passadas — curva de nível é mais segura e mais barata
que subir e descer a encosta.

`POST /v1/admin/fields/{id}/relief` mede e grava em `field.relief`. Sem fonte
configurada responde **501**, e não zeros: um zero seria lido como "terreno
plano" e entraria no plano com a autoridade de uma medição.

O relevo tem coluna própria, e não vive dentro de `terrain`, porque as duas
medições envelhecem em ritmos incomparáveis — a cobertura do solo muda a cada
safra, a encosta não muda nunca. Uma releitura de imagem não o derruba; um
contorno novo, sim, porque aí o pedaço de chão medido é outro.

Medido o relevo, a camada de segurança **barra** missão cuja declividade máxima
passe do limite do modelo (`capabilities.max_slope_deg`, ou 15° quando o
descritor de hardware não declara). Sem relevo medido ela passa, e o parecer diz
em letras que não foi medido: transformar "não medi" em "não pode" travaria toda
missão de toda instalação que ainda não ligou um DEM.

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
