# Consenso federado (brief 7.1) — avaliação do `merge_priors` e o que os Rovers compartilham

> Rodada 4 — Parte 3 (19/10/2026), branch `claude/cerebro-agronomico`. Código em
> `saas/valtexa/services/federado.py` e `saas/valtexa/api/routers/federado.py`; testes
> `saas/tests/test_federado.py` (13) e `ia/tests/test_dnaty_merge_priors.py` (3). A Parte 1
> não chegou a fazer o 7.1 (`docs/AUDITORIA_RODADA4.md`: "FALTA"); esta parte fecha a
> **fusão, a compatibilidade, o anti-eco, a avaliação e a medida de bytes**. A **descida ao
> Rover e o uso do prior na fusão por planta** ficam para decisão do Pedro (abaixo).

## 1. O `merge_priors` do dNATY (2.2.1, BSL-1.1) — para que serve aqui

O que ele faz (lido no pacote instalado e medido em `ia/tests/test_dnaty_merge_priors.py`):
cada prior `{operador: escore}` é **centrado na média e dividido pelo maior módulo**; o
consenso é a média (ponderada, se quiser) dos normalizados; `n_experiences` só é somado.

| Medido | Resultado |
| --- | --- |
| Prevalência 2% × 20% de ferrugem | os dois viram **o mesmo** prior (`Rust −1, Healthy +1`): **o nível some** |
| 10 plantas × 10 000 plantas | **pesam igual**; com sinais opostos, empatam em 0 |
| Escores de operadores de mutação de dois dispositivos | o operador que ajudou nos dois fica na frente (`merged_from = 2`) — é para isso que ele existe |

**Conclusão:** `merge_priors` **não serve** para fundir prevalência, evidência de doença nem
pesos de rede — devolveria um número com cara de estatística e sem significado. Serve para o
que foi feito: **aquecer a busca de arquitetura** (o `fit_heads` do treino, que usa o dNATY)
com o que funcionou em outros dispositivos/tarefas. Na ValTexa isso só faria sentido se cada
Rover rodasse busca de arquitetura na borda — não roda (a cabeça é treinada na máquina do
Pedro e adaptada pelo aprendizado contínuo com portão de regressão). **Não foi adotado**;
fica anotado como possibilidade para o treino (lá, com a licença BSL-1.1 resolvida).

## 2. O que os Rovers compartilham de fato

**Contagens validadas por estrato.** Para cada talhão (origem), estrato = (variedade, solo,
estágio) e classe da taxonomia do modelo: `x` positivas de `n` plantas **conferidas pelo
agrônomo** (diagnóstico `human_confirmed`/`human_rejected`, com o rótulo efetivo dele), com o
protocolo que as produziu. Nada de imagem, nada de peso.

* **Sem base na fazenda** (`docs/RODADA4.md`): as observações já sobem pela Starlink de cada
  Rover e são conferidas na plataforma — então as contagens **são montadas na plataforma**, e
  o custo de subida delas é **zero**. A representação de um talhão/Rover por dia existe
  (`federado.carga`) e foi medida para o caso em que um Rover a montasse.
* **Solo** não está no cadastro do talhão: entra como `"?"` (decisão do Pedro: acrescentar).

### Compatibilidade (`federado.compativel`)

Entra só a contagem com **a mesma taxonomia de classes** (sha256 da lista), **o mesmo modelo
e a mesma cabeça** (versão), **o mesmo protocolo de validação** (`agronomo`), **dentro da
janela** e coerente (não vazia, positivas ⊆ observações). O resto é recusado com o motivo —
nunca convertido. Exemplo testado: a contagem de uma cabeça antiga sai como "modelo ou cabeça
diferente".

### Anti-eco (dois)

1. **A mesma observação não conta duas vezes** (`federado.sem_eco`): cada contagem carrega os
   ids das observações; a repetida (dois Rovers na mesma planta, reenvio) é descartada.
2. **O prior que volta ao talhão não contém o dado dele** (deixa-um-de-fora por origem): o
   dado do talhão entra nele como evidência local, uma vez só — a mesma regra do gêmeo. Teste:
   trocar o dado do próprio talhão por 100% de ferrugem **não muda** o prior que ele recebe.

### A fusão (`federado.prior_para`) — Beta-binomial hierárquica com encolhimento

Por classe, sem o talhão de destino:

* `p` = média agregada, com meia planta de cada lado (Jeffreys: zero positivos não vira
  `Beta(0, ·)`);
* `ρ` = correlação intra-estrato pelo método dos momentos da Beta-binomial
  (`S = Σ nₛ (pₛ − p)²`, `ρ = (S − p(1−p)(k−1)) / (p(1−p)(N − Σnₛ²/N))`);
  `κ = (1 − ρ)/ρ`, limitado a `[2, força máxima]` — estratos iguais (`ρ ≤ 0`) juntam tudo;
  estratos muito diferentes ficam cada um com o seu;
* prior do estrato `s` para o talhão `F`:
  `Beta(κ p + xₛ, κ (1 − p) + nₛ − xₛ)` com `xₛ, nₛ` dos **outros** talhões do estrato; a
  força total (`α + β`) é encolhida a **200 plantas** (premissa, não medida): o prior
  compartilhado nunca afoga o dado local.

### Avaliação antes de distribuir (`federado.avaliar`)

Deixa-um-talhão-de-fora: a log-verossimilhança preditiva (Beta-binomial) do dado de cada
talhão sob o prior fundido **sem ele**, contra o prior de referência (padrão: uniforme fraco
`Beta(1, 1)`; o pedido pode mandar o do treino, `<modelo>.prior.json`). **Distribui só se a
média não piora.** Testado nos dois sentidos: estratos diferentes e referência fraca →
distribui (ganho > 0); estratos iguais e referência que já é a verdade, forte → **não**
distribui ("o prior fundido prevê pior que a referência").

## 3. Bytes (medidos, corpo sintético — `federado.tamanho`)

| O quê | JSON | gzip |
| --- | ---: | ---: |
| Carga de um talhão/Rover num dia: 1 estrato × 5 classes | 576 B | 279 B |
| Carga com 3 estratos × 5 classes | 1 232 B | 343 B |
| Prior distribuível para um talhão (5 classes, com κ, média geral e contagens) | 1 202 B | 330 B |

"Poucos kilobytes" se confirma **para esta representação**: menos de 1,3 kB por talhão por
dia, contra o teto padrão de 2 GB/dia da Starlink do Rover. (O que pesa na Starlink são as
imagens e os resultados por recorte — `docs/ROVER_RUNTIME.md` §27.)

## 4. API

`GET /v1/fields/{id}/federado/prior` (`decision:read`, só leitura): o prior de cada classe
para o estrato do talhão, sem o dado dele; a avaliação; as contagens recusadas e por quê;
quantas observações o anti-eco descartou; os bytes; as premissas. **Só do próprio cliente**.
Calcula na hora; não grava nem distribui. Teste com 4 talhões simulados e um outro cliente
com 90% de ferrugem, que **não entra**.

## 5. O que falta (honesto) e as decisões do Pedro

| Passo do brief | Situação |
| --- | --- |
| 1–2. Coleta e validação | **OK** (observações sobem; o agrônomo confere) |
| 3. Representação compatível | **OK** (contagens por estrato com protocolo) |
| 4. Envio | **OK por construção**: já está na plataforma (custo zero de subida) |
| 5. Integridade, versão, origem, compatibilidade | **OK** (origem e integridade pelo protocolo do dispositivo; compatibilidade aqui) |
| 6. Fusão | **OK** (Beta-binomial hierárquica com encolhimento e anti-eco) |
| 7. Avaliação antes de distribuir | **OK** (deixa-um-talhão-de-fora contra a referência) |
| 8. Distribuição aos autorizados | **NÃO**: o prior não desce na missão assinada |
| 9. Verificação no dispositivo antes do uso | **NÃO**: o Rover não usa prior hoje |

Decisões:

* **Quem consome o prior fundido.** O lugar natural é a **fusão por planta da IA** (o
  `<modelo>.prior.json` de prevalência que ela usa para a correção de prior), por talhão — e
  `ia/app/plant_fusion.py` só aceita mudança aditiva com teste e está sendo calibrado pelo
  Pedro. Por isso o prior é calculado e exposto, e **não** ligado. Descer ao Rover só faz
  sentido se a Edge AI passar a usar prior por estrato (hoje não usa).
* **Entre clientes**: compartilhar contagens entre clientes pede consentimento próprio (o de
  treino não cobre esse uso) — hoje é só dentro do cliente.
* **Solo no cadastro do talhão**, e a **força máxima** (200 plantas) do prior.
* `merge_priors`: adotar no treino (busca de arquitetura) depende da licença BSL-1.1.
