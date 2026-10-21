# Enxame: Rover, drone e base trabalhando juntos (Nível 4)

O Nível 3 deu ao talhão um gêmeo digital: onde a doença está, onde vai estar, com que
incerteza. O Nível 4 faz os dispositivos agirem sobre isso **juntos**: quem olha onde, o que
cada um sabe do que os outros viram, e como a fazenda inteira recebe uma atualização sem
gastar a Starlink várias vezes.

> **O que é real e o que é simulado.** Todo o código tem teste. As medições abaixo são em
> **talhão sintético** (a verdade conhecida) e em alocação simulada; nenhuma foi feita em
> lavoura. O canal de observação do drone (o quanto ele vê da ferrugem pela copa) é
> **suposição de projeto**, não medida — está escrito onde é usado.

## 1. As seis peças e onde moram

| Peça | O que faz | Onde |
| --- | --- | --- |
| Priorização por incerteza e risco | valor da informação de olhar cada trecho de rua (Rover) ou bloco (drone), pela decisão tratar / não tratar | `ia/app/gemeo/prioridade.py`, `GET /fields/{id}/gemeo/prioridades` |
| Fusão entre dispositivos | o gêmeo assimila passadas de fontes diferentes, cada uma com o seu canal; evidência de drone ou agrônomo entra por planta | `ia/app/gemeo/epidemia.py` (`Canal`, `CANAIS`), `POST /fields/{id}/gemeo/observacoes` |
| Alocação dinâmica | tarefas × dispositivos disponíveis, por valor por segundo, com energia e deslocamento; horizonte rolante | `valtexa/services/enxame.py`, `/v1/fields/{id}/enxame/plano` |
| Coordenação | o plano versionado, a próxima missão de cada robô, as missões pelo fluxo de segurança de sempre | `valtexa/api/routers/enxame.py`, tabela `plano_enxame` (migração 0032) |
| Compartilhamento controlado | a política do que cada tipo de dispositivo recebe; as prioridades descem dentro da missão assinada | `valtexa/services/compartilhamento.py`, `mission_command_body` |
| Distribuição local de atualizações | a base guarda o pacote OTA pelo SHA-256 e serve os outros Rovers da fazenda | `base/valtexa_base/distribuicao.py` |

E no Rover, o uso das prioridades: `rover/valtexa_rover/runtime/prioridades.py` e a percepção
ativa (`runtime/percepcao.py`).

## 2. O fluxo

```
 passadas do Rover ─┐                     ┌─ voo do drone, rótulo do agrônomo
 (fusão por planta) │                     │  (POST /gemeo/observacoes: LLR por planta)
                    ▼                     ▼
              GÊMEO DIGITAL (VALTEXA-B): uma crença por planta, com o canal de cada fonte
                    │
                    ▼  GET /gemeo/prioridades?canal=rover|drone
         tarefas com valor da informação (trecho de rua, bloco)
                    │
                    ▼  POST /v1/fields/{id}/enxame/plano
   SaaS: frota DISPONÍVEL × tarefas → plano versionado (quem, o quê, em que ordem)
                    │
                    ▼  POST .../plano/{id}/missoes   (só cria em DRAFT)
   missão → authorize (camada de segurança) → dispatch (assinada; leva as prioridades)
                    │
                    ▼
   Rover: gasta a percepção ativa onde vale mais · sobe a evidência pura · volta ao gêmeo
```

## 3. Priorização: valor da informação

Olhar uma planta vale o quanto a observação **muda a decisão** sobre ela. ``D`` é a planta
infectada (latente ou esporulando), ``p = P(D)`` no dia da visita; a fonte só vê o que
esporula, com sensibilidade ``s`` e alarme falso ``a``. Com os números do produtor (custo de
tratar ``c``, perda por planta ``L``, eficácia ``e``) e a consequência ``(1 + R_i)`` — as
vizinhas que a planta infectaria até a visita seguinte, pelo núcleo de contágio ajustado:

```
VOI_i = L_i·e · ( E_y[ max(0, P(D|y) − t_i) ] − max(0, p − t_i) ),     t_i = c / (L_i·e)
```

É zero quando a decisão já está tomada (planta quase certamente sadia, ou tão provável que
se trata de qualquer jeito) e máxima perto do limiar. Sem os números do produtor, a
informação mútua em bits, pesada pela consequência.

**Medido** (`ia/training/mede_enxame.py --so priorizacao`, 3 sementes, inspeção de 15% e 30%
dos trechos de 20 m, valor realizado em reais contra não inspecionar):

| cenário | orçamento | valor da informação | varredura em ordem | sorteio | só risco | só incerteza |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| limiar ~11%, homogêneo | 15% | **64** | 53 | 45 | 13 | 13 |
| limiar ~11%, homogêneo | 30% | **120** | 98 | 74 | 33 | 38 |
| limiar ~11%, baixada 5× | 30% | **19** | 11 | 5 | 1 | 2 |
| limiar ~4%, homogêneo | 30% | **27** | 9 | 9 | 4 | 1 |

O valor da informação ganhou ou empatou com a melhor alternativa em todas as 24 combinações.
**Priorizar só pelo risco ou só pela incerteza é pior que varrer em ordem**: as duas mandam o
Rover às plantas cuja decisão já está tomada. O ganho absoluto é pequeno (2 a 4% da perda)
porque o gêmeo de campo médio superestima o risco e manda tratar quase tudo; com o gêmeo
calibrado no campo, a inspeção deve valer mais — a medir no piloto.

## 4. Fusão entre dispositivos (e o anti-eco)

Cada passada diz de onde veio (`fonte`: `rover`, `drone`, `agronomo`) e entra no filtro do
gêmeo com o canal daquela fonte: dada a planta, as fontes veem independentes, e a fusão é o
produto das verossimilhanças — uma fonte pior pesa menos sozinha, sem regra à parte. O canal
do Rover é ajustado ao talhão; os outros vêm da tabela `CANAIS` (o do agrônomo: 0,97 /
0,01; o do drone: 0,45 / 0,06, **suposição de projeto** — a copa esconde o terço inferior,
onde a ferrugem começa).

**Medido** (`mede_enxame.py --so fusao`, 3 sementes; Rover a cada 14 dias, drone a cada 7;
prevê a passada seguinte do Rover):

| | log-v (homogêneo) | AUC infectada oculta | log-v (baixada) | AUC | sensibilidade do Rover ajustada (verdade 0,85) |
| --- | ---: | ---: | ---: | ---: | ---: |
| só o Rover | 0,142 | 0,838 | 0,321 | 0,914 | 0,94–0,97 |
| Rover + drone, cada um com o seu canal | **0,152** | **0,861** | 0,333 | **0,927** | 0,89–0,96 |
| Rover + drone com o canal do Rover | 0,152 | 0,855 | 0,338 | 0,916 | **0,64–0,77** |

A fusão com o canal certo melhora a previsão e ordena melhor as plantas escondidas. A fusão
ingênua parece igual na verossimilhança, mas ordena pior e **estraga o canal do Rover**: para
explicar os sinais fracos do drone, o ajuste rebaixa a sensibilidade do Rover — e o erro
passa a contaminar tudo o que vem dele.

**Anti-eco** (a regra que impede a fusão de inventar certeza):

1. A evidência do Rover entra **só** pela fusão por planta. `POST /gemeo/observacoes` recusa
   `fonte=rover` (422): seria a mesma observação duas vezes.
2. O prior fundido desce para o dispositivo **só para decidir a bordo** (onde olhar de novo,
   o que subir primeiro), nunca como evidência. O que o Rover vê sobe puro — a razão de
   verossimilhança dos recortes —, com ou sem prioridade. Por isso a prioridade vai
   **relativa** (0 a 1 entre os trechos da missão) e marcada `uso`.

## 5. Alocação dinâmica

`valtexa/services/enxame.py`:

* **Agentes**: só os dispositivos **DISPONÍVEIS** da fazenda (`fleet_state`). Orçamento de
  tempo = autonomia × (bateria − 25% de reserva); sem leitura de bateria, conta meia carga.
* **Custo** de uma tarefa: deslocamento desde onde o robô está (ou de onde terminou a
  anterior) + percurso de trabalho (comprimento das ruas, ou área pela largura da faixa) na
  velocidade dele + sobrecarga de manobra.
* **Guloso por valor por segundo**, com as verificações pós-aplicação vencidas primeiro
  (obrigatórias). Quando drone e Rover cobririam as mesmas plantas, a segunda tarefa vale
  metade (`desconto_sobreposicao`).
* **Horizonte rolante**: o plano entrega a cada agente **a próxima missão** — o bloco de
  trechos contíguos da mesma rua que contém a primeira tarefa dele, num retângulo. Quando o
  robô termina, ou a frota muda, faz-se um plano novo com o estado novo. O plano guarda a
  impressão da frota (bateria de 5 em 5%, posição de ~10 m) e a leitura diz
  `desatualizado` quando ela muda ou o plano passa de 6 h.

**Medido** (`python scripts/mede_alocacao.py`, 5 sementes, 40 ruas × 10 trechos com o valor
concentrado em focos, 1 h de bateria útil por Rover, valor coberto):

| Rovers | enxame | varredura em ordem | mais valioso primeiro (sem pesar deslocamento) |
| ---: | ---: | ---: | ---: |
| 1 | **35,7%** | 6,2% | 27,1% (2,6× mais metros sem trabalho) |
| 2 | **56,2%** | 15,8% | 46,5% |
| 4 | **79,6%** | 36,2% | 62,9% |

## 5b. Restrições do talhão e calibração (rodada 4, Parte 3)

O plano usa o contexto do planejamento robótico (`valtexa/planejamento/robotico.py`,
`docs/PLANEJAMENTO.md`): inclinação medida do talhão contra o limite de cada Rover,
obstáculos intransponíveis da leitura de terreno da IA, o que resta do orçamento de dados da
Starlink de cada Rover, o valor mínimo por minuto de robô (do produtor; sem ele, não corta) e
o piso de vigilância (trecho esquecido há 14 dias ou mais ganha o menor valor positivo). As
premissas vão para `plano_do_enxame.entradas`.

## 6. As decisões de segurança (não mudar sem rever)

* **A missão continua uma por robô, autorizada pela camada de segurança e assinada pela
  plataforma.** O enxame não despacha: cria em `DRAFT`, e `authorize` e `dispatch` seguem o
  fluxo de sempre, com os papéis de sempre (`mission:create` para criar).
* **Aplicação não é alocada pelo enxame.** Sai da prescrição, com a aprovação do agrônomo.
* **Sobrevoo de observação do drone não vira missão.** A camada de segurança só aceita missão
  sem aplicação feita por Rover, e não existe regra de voo sem aplicação (vento, RTK, margem
  de energia estão escritos para a pulverização). O plano mostra o sobrevoo e quanto ele
  valeria; criar a missão é recusado com o motivo. **Liberar voo de observação é uma decisão
  de segurança a tomar**, com regra própria no `safety_engine` — não um ajuste de código.
* **Sem internet, a base não realoca.** Realocar é criar missão, e missão só a plataforma
  assina. Cada robô termina a que tem (política offline); o console da base arma as do cache.
* **O que nunca desce para dispositivo**: imagem, posterior por planta, os números do
  produtor, dado de outro talhão ou fazenda (`compartilhamento.POLITICA`).

## 7. Distribuição local de atualizações

A base guarda cada pacote OTA pelo SHA-256 do manifesto assinado, a partir dos bytes que ela
mesma baixou da nuvem para um Rover; fecha o pacote só se ele conferir. Os Rovers seguintes
da fazenda recebem da base — pelo rádio ou pela LAN da doca, e com a Starlink caída. O Rover
confere assinatura e hashes de novo; a base só serve a cada Rover os deployments que a
plataforma deu a ele; o disco tem teto (`"distribuicao": {"max_gb": 10}` no `base.json`) e
o usado há mais tempo sai primeiro. Ver `COMUNICACAO_FAZENDA.md` §19.

## 8. Rotas

| Rota | Papel | O quê |
| --- | --- | --- |
| `POST /v1/fields/{id}/enxame/plano` | `decision:read` | calcula e guarda o plano ativo (o anterior fica como `substituido`) |
| `GET /v1/fields/{id}/enxame/plano` | `decision:read` | o plano ativo, com `desatualizado` e o porquê |
| `POST /v1/fields/{id}/enxame/plano/{plano}/missoes` | `mission:create` | a próxima missão de cada robô, em `DRAFT`; plano substituído → 409 |

Na IA: `GET /fields/{id}/gemeo/prioridades` e `POST /fields/{id}/gemeo/observacoes`.

## 9. O que falta

* **Piloto**: o gêmeo calibrado em lavoura de café, e só então a medida de quanto a inspeção
  priorizada poupa de verdade.
* **Canal do drone medido**: voo sobre plantas rotuladas (a mesma calibração por planta do
  Rover) — até lá, a suposição de projeto.
* **Regra de segurança de voo de observação**, para o drone entrar na alocação de inspeção.
* **Pré-busca noturna** na base: baixar o pacote com a Starlink ociosa antes de o primeiro
  Rover pedir (precisa de uma rota da plataforma para a base baixar pacote dos robôs da
  fazenda dela).
* **Replanejamento automático** pelo worker ao fim de cada missão (hoje: sob demanda, com o
  aviso de desatualizado).
