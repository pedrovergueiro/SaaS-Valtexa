# Planejamento de apoio à decisão (brief 8.3)

> Rodada 4 — Parte 3 (19/10/2026), branch `claude/cerebro-agronomico`. Código em
> `saas/valtexa/planejamento/`, rotas em `saas/valtexa/api/routers/planejamento.py`, telas
> `saas/web/src/pages/Planejamento.tsx`, `PlanoDetail.tsx`, `PlanejamentoInsumos.tsx`,
> migração `0035`. Leia junto com `docs/CEREBRO.md` e `docs/SEGURANCA.md` (Princípio de Ouro).

## A regra

O agente **propõe**. Todo plano sai com:

* **premissas registradas** — cada número que entrou no cálculo, com o texto e a **origem**:
  `padrao` (valor da plataforma, **não medido**), `pedido` (quem pediu), `medido` (banco,
  telemetria, leitura de terreno), `cadastro` (produto, lote, talhão) ou `simulado`
  (simulação, não campo). O console marca `padrao` e `simulado` em amarelo e conta quantas
  há ("confira antes de aceitar");
* o **resultado** e o `sha256` de pedido + premissas + resultado — o plano é imutável; pedir
  de novo cria outro;
* **revisão humana** — `aceito`, `ajustar` ou `recusado` (os dois últimos com comentário),
  por quem tem a capacidade do tipo: fitossanitário `diagnosis:review` (agrônomo), robótico
  `mission:create`, insumos `product:manage`. A revisão confere o hash e vai para a
  auditoria (`planejamento.gerado`, `planejamento.revisado`).

**Aceitar não autoriza nada.** Nenhuma rota de planejamento cria missão, aprova prescrição
ou aplicação, muda limiar de modelo ou chama o Safety Engine — `tests/test_principio_de_ouro.py`.

## Fitossanitário — `POST /v1/fields/{id}/planejamento/fitossanitario`

| Parte | Como | De onde |
| --- | --- | --- |
| Fila de revisão | um item por planta (o diagnóstico não revisado mais recente na janela), `escore = risco × incerteza × impacto` | `risco` = 1 − P(sadia) do classificador, ou o risco do gêmeo para a planta se maior (as duas fontes ficam no item); `incerteza` = maior de (1 − margem top-2, 1 − 1/\|conjunto conformal\|, 1 se discordância/abstenção/inconclusivo); `impacto` = peso da classe, **1 para todas por padrão** (o agrônomo pode mandar `pesos_impacto`) |
| Histórico de sintomas | as plantas do topo da fila: situação por passada, incidência da primeira à última (tendência com limiar 0,05, premissa), lesões por estado (persistente, nova, não revista) e por doença | IA: `/plants/{p}/evolution`, `/plants/{p}/lesoes` |
| Regiões prioritárias | as 20 primeiras tarefas do gêmeo | IA: `/gemeo/prioridades` (o mesmo valor da informação que o enxame usa) |
| Alternativas de manejo | monitorar, confirmar em campo, inspeção dirigida, tratamento localizado, tratamento em área total — cada uma com quando faz sentido, a evidência, o que falta, o custo de errar e quem decide | fila, regiões, previsão do gêmeo (plantas acima do limiar de risco — 0,3, premissa que **só descreve** —, infectadas esperadas p10–p90, focos). **O plano não escolhe; nenhuma alternativa traz produto nem dose** |
| Rotação por modo de ação | produtos **elegíveis**: ativos, com modo de ação (`product.modo_de_acao`), registro MAPA, ingrediente, cultura do talhão autorizada e **fonte** (`product.fonte_documento_id`) que é bula ou registro MAPA **vigente, verificado, dentro da validade, não fictício** e que cita a cultura. O resto fica em `fora`, com o motivo. Sequência das aplicações concluídas do talhão (365 dias), o último grupo e quantas seguidas | `max_seguidas_mesmo_grupo` vem do pedido (da bula/do agrônomo); **sem ele, o plano mostra e não julga** ("repete o grupo da última aplicação") |

## Robótico — `POST /v1/fields/{id}/planejamento/robotico`

O alocador do enxame (`services/enxame.py`) inteiro — tarefas do gêmeo por canal,
verificações pós-aplicação obrigatórias, agentes disponíveis com orçamento de tempo da
bateria acima da reserva, guloso por valor por segundo, desconto de sobreposição — mais três
restrições (mudança **aditiva** no `alocar`: `restricao`, `bytes_da_tarefa`,
`orcamento_bytes`; sem elas, o mesmo plano de antes — teste):

| Restrição | Leitura | Efeito | Premissa |
| --- | --- | --- | --- |
| Inclinação | `field.relief` (a mesma do `_check_slope` do Safety Engine) | declividade máxima ≥ limite do Rover (`max_slope_deg`, padrão 15°) → o Rover não recebe tarefa no talhão ("o Safety Engine bloquearia"); abaixo → trabalho mais lento em `fator_declive × média/limite` | `fator_declive` 0,5, **não medido** (calibrar com a telemetria); sem relevo: "planejado como plano" |
| Obstáculos | `field.terrain` — a saída de `ia/app/obstacles.py` pela rota de `ia/app/terrain_api.py`, **lida, sem editar aqueles arquivos** | só intransponíveis e só com `resolution_ok`; centro do trecho dentro → fora para o Rover; trecho que encosta → soma meio perímetro do retângulo na velocidade dele. O drone sobrevoa | origem `medido` (heurística da IA) |
| Dados da Starlink | `services/orcamento_dados.relatorio` por Rover: teto do dia (plataforma ou `rover.json`) e o usado que o Rover contou | resta `teto × (1 − reserva) − usado`; cada tarefa custa `percurso × bytes_por_metro`; o que não cabe fica de fora, com o motivo | `bytes_por_metro` **88 000 B/m, SIMULADO** (`ROVER_RUNTIME.md` §27: ~0,95 GB de metadados em 10,8 km); `reserva_dados` 0,10 |

E as duas calibrações do 7.3, contra os dois modos de falha da alocação por incerteza
(`docs/AUDITORIA_RODADA4.md`):

| Calibração | Como | Premissa |
| --- | --- | --- |
| Contra **missões excessivas** em área pouco relevante | tarefa que vale menos que `valor_minimo_por_minuto` por minuto de trabalho do robô fica de fora, com o motivo (obrigatória nunca sai) | o número vem do produtor (custo de operar); **sem ele, não corta** — e a premissa diz que o plano gasta a bateria enquanto houver valor > 0 |
| Contra **regiões importantes esquecidas** | trecho nunca visto ou não visto há `piso_vigilancia_dias` (14) dias ganha o **menor valor positivo** do plano em vez de zero: usa o que sobra da bateria, perde para qualquer trecho que informe mais | 14 dias, padrão **não medido** (ajustar à epidemiologia: ferrugem tem latência de ~2–4 semanas — a confirmar com o agrônomo) |

**O plano do enxame usa as mesmas restrições.** `POST /v1/fields/{id}/enxame/plano` — o que
cria as missões em RASCUNHO — monta o mesmo contexto (`robotico.contexto`) e aloca com ele;
as premissas e o orçamento de dados de cada Rover ficam em `plano_do_enxame.entradas`. Sem
relevo, sem leitura de terreno, sem teto de dados e sem o valor mínimo do produtor, o plano é
o de antes (os testes do enxame não mudaram).

Saída: a rota de cada agente (passos, deslocamento, trabalho, tempo, bateria inicial → final
estimada, bytes), o plano **sem** as restrições ao lado e o que saiu por causa delas, o
orçamento de dados de cada Rover, os obstáculos lidos, a **próxima missão proposta** de cada
agente. Criar a missão (em RASCUNHO) continua sendo ação de uma pessoa, pelo plano do enxame
ou pela tela de missões.

## Insumos — `POST /v1/planejamento/insumos`

Por produto, das aplicações concluídas (`amount_used_l`) na janela (365 dias): blocos de H
dias (o horizonte, 30), bootstrap da média (2000 reamostragens, **semente fixa** — o mesmo
histórico dá o mesmo plano) e os quantis do próprio bloco (o próximo mês é um bloco, não a
média): cenários p10/p50/p90. Estoque = lotes não vencidos; comprometido = missões de
aplicação não encerradas com `authorized_quantity_l`; **possível reposição** quando
`estoque − comprometido` não cobre o p90. **Sem histórico** (menos de 3 aplicações ou de 2
blocos com consumo): "sem histórico suficiente para estimar", sem número. O café é sazonal:
com anos de histórico, `mesma_epoca` usa só os blocos da mesma época.

## Limites

* A IA dos testes é dublê (números inventados). "A verificar com o modelo real."
* O relevo é do talhão inteiro, não por trecho: a inclinação é igual para todas as tarefas
  do talhão.
* Os obstáculos são retângulos grosseiros (é o que a leitura de terreno entrega).
* `bytes_por_metro` padrão é simulado; o Rover não mede ainda bytes por metro — quando a
  telemetria da Parte 1 tiver dias reais, trocar pelo medido.
* O console foi conferido por `tsc`, `build` e `vitest`, **não no navegador**.

## Decisões do Pedro

* Os padrões não medidos: `fator_declive` (0,5), `reserva_dados` (10%), `limiar_risco` (0,3),
  `limiar_tendencia` (0,05).
* Quem cadastra o modo de ação e a fonte dos produtos (e se o limite de aplicações seguidas
  do mesmo grupo vira cadastro por produto em vez de pedido).
