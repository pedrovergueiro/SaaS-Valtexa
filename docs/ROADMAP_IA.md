# Roadmap da IA — o que falta do plano "Níveis 1 a 5"

> 26/10/2026. Confronta o documento "VALTEXA AI — Diagnóstico Técnico do Ecossistema e Plano de
> Evolução" com o que existe no código e com o que foi **medido**. Arquitetura:
> [`ARCHITECTURE.md`](ARCHITECTURE.md); estado: [`ESTADO_ATUAL.md`](ESTADO_ATUAL.md).

## Duas correções ao documento

1. **Não existe mais a VALTEXA-BASE.** Cada Rover tem a própria Starlink; o rádio e a base foram
   arquivados em 20/10/2026. Onde o documento diz "a Base coordena / distribui / valida", o
   papel é da **plataforma**. A "estação meteorológica da Base" é a estação da fazenda
   (`POST /fields/{id}/clima`) ou o Open-Meteo.
2. **O `merge_priors` do dNATY não serve para prevalência**: ele funde estatísticas de
   operadores da busca de arquitetura e apaga o nível e o tamanho da amostra (medido em
   `ia/tests/test_dnaty_merge_priors.py`). O consenso federado usa contagens validadas
   (`services/federado.py`, `docs/FEDERADO.md`).

## Item a item

Legenda: **Feito** (código + testes) · **Feito, sem campo** (só simulação ou dado público) ·
**Medido, não adotado** · **Falta (software)** · **Depende de campo/hardware** · **Decisão sua**.

| Item do documento | Estado | Onde / o que falta |
|---|---|---|
| 5.1 Ciclo contínuo (adapta → portão → aprovação → procedência → rollback) | Feito, sem campo | `training/adapt_campo.py`, `app/inference/continual.py`. Roda na nuvem, não na Jetson (de propósito: a Jetson não tem dado de regressão nem agrônomo). Manifesto dos arquivos do modelo no registry e `adapt_campo pronto` (26/10, item 4) |
| 5.1 dNATY como motor de adaptação | Medido, não adotado | A cabeça do café não tem neurônio dormente; renascer 5% piorou (BRACOL 84,7→82,9). Produção segue NumPy |
| 5.2 Percepção ativa (vista extra, velocidade, luz) | Feito, sem campo | `runtime/percepcao.py`. OAK-D, luz e velocidade **nunca rodaram no hardware** |
| 5.3 Fusão 3D (RGB-D, geometria, lesão por passada) | Feito, sem campo | `edge_ai/rgbd.py`, `geometria.py`, `lesion_tracks`. Face da folha sempre "indeterminada" (como o documento pede) |
| 6.1 Grafo espaço-temporal + clima | Feito, sem campo | `app/gemeo/*`. Validação do clima e modo de observação (26/10, item 3) |
| 6.2 PINN de dispersão | Medido, não adotado | Erro do D −25/−1/+141%; o ajuste pelo solver erra ≤2% e é o que está em uso |
| 6.3 Prescrição variável | Feito, sem campo | Mapa de aplicação + Safety Engine (taxa entre mínimo e padrão da bula, PWM, aprovação) |
| 7.1 Consenso federado | Feito, sem campo | Contagens validadas, anti-eco, compatibilidade |
| 7.2 Drone → Rover | Feito até o rascunho | **Decisão sua:** regra de voo de observação (sem ela o sobrevoo não vira missão) |
| 7.3 Alocação por valor da informação | Feito, sem campo | VOI venceu varredura em 24/24 combinações (sintético) |
| 8.1–8.2 Copiloto e parecer | Feito | Dossiê de evidências, fontes versionadas, parecer determinístico; provedor de linguagem desligado. Parecer na fila do agrônomo (26/10, item 1) |
| 8.3 Planejamento fitossanitário, robótico e de insumos | Feito | Rotação de modo de ação, rotas, bateria; insumos com faixa p10–p90, estoque e o comprometido (`valtexa/planejamento/`) |
| 8.4 Princípio de Ouro | Feito | Testes de prova (tripwire) |
| 11.3 Calibração e cobertura conformal em produção | Feito (26/10, item 2) | Mede com o que o agrônomo confirma; só os casos da fila (viés dito) |

## O que fazer, em ordem

| # | Item | Por quê | Estado |
|---|---|---|---|
| 1 | Parecer na fila de revisão | Passo 3 do documento: o agrônomo revisa sem a explicação ao lado | **feito** |
| 2 | Cobertura conformal e calibração medidas com o que o agrônomo confirma | A garantia de 90% é da calibração; no campo ela pode cair (banana: 57%) e hoje ninguém vê | **feito** |
| 3 | Clima: dado inconsistente/desatualizado + modo de observação | Passo 2: o clima não deve mudar prescrição antes de ser comparado | **feito** |
| 4 | Ciclo contínuo: conferência antes do Rover | Passo 1: hoje são comandos soltos, e nada impede levar cabeça nova com conformal ou perfil da anterior | **feito** |

### O que cada item virou

1. **Parecer na fila.** `GET /v1/review/queue` traz, em cada item, o parecer mais recente da
   observação (hipótese, alternativas, a primeira afirmação, fontes e verificações em aberto);
   na tela da fila, o cartão "Parecer do cérebro agronômico" com o link e o botão "Pedir
   parecer". Continua apoio à decisão: não autoriza nada.
2. **IA contra o agrônomo.** `valtexa/services/calibracao_campo.py`, em
   `/v1/platform/ai-health` (`field_calibration`) e na aba Saúde da IA do console interno:
   acerto, cobertura do conjunto contra a **prometida** (a detecção passou a gravar
   `set_coverage`), calibração por faixa de confiança (ECE) e o que ficou fora do catálogo,
   com intervalo de Wilson e o estado `dentro` / `abaixo` / `poucos_dados`. **Viés:** só casos
   que foram à fila — piores que a média; a medida sem viés é a validação de campo.
3. **Clima e modo de observação.** Na IA: hora repetida e sensor travado saem do envio (com
   relatório); a série diz até quando há tempo **observado** e se está desatualizada (> 3
   dias). O gêmeo de cada (talhão, doença) começa em **observação**: o mapa de aplicação sai
   igual, mas com `estado: observacao`, a verificação `gemeo_ativo` reprovada e registrado
   como "sombra"; o modo entra no hash, e o Safety Engine tem a conferência
   `map_twin_active`. `GET /gemeo/avaliacao` pontua as previsões um passo à frente nas
   passadas que o ajuste não viu, contra a persistência e a prevalência; `POST /gemeo/modo`
   só ativa com 2 passadas e 50 plantas avaliadas e o gêmeo vencendo as duas (o agrônomo
   decide pela plataforma, com auditoria). Voltar à observação é sempre permitido.
4. **`adapt_campo pronto`.** Depois do `promove`, confere procedência, conformal e perfil da
   borda contra a cabeça instalada e diz o comando que falta; zero só quando pode ir ao
   `preparar-modelo`. O `promove` já tira o conformal da cabeça anterior.

### Feito depois (26/10)

5. **Tempo previsto contra o observado.** Cada mapa e cada prescrição do gêmeo gravam o tempo
   que usaram no horizonte (previsão ou climatologia) em `gemeo/<talhão>/tempo_previsto.jsonl`;
   quando o observado daqueles dias chega, `GET /gemeo/avaliacao` traz o erro absoluto médio
   (molhamento, temperatura, umidade, chuva) por fonte e por antecedência (1–3, 4–7, 8–16 dias).
6. **Tela do gêmeo no console** (`/talhoes/:id/gemeo`, botão "Previsão" no talhão): clima e
   atualidade, modo com o responsável e o botão do agrônomo (ativar só com avaliação
   favorável; voltar à observação sempre), as notas por passada contra as referências, o erro
   do tempo previsto e a previsão (focos, infectadas p10–p90, janelas de infecção).

Não sobra item de software deste documento; o que falta depende de campo, hardware ou decisão
(lista acima).

**Depende de campo, hardware ou decisão (não dá para fazer daqui):** piloto em talhão de café;
fotos na escala do Rover; tempo na Jetson e OAK-D; canal do drone medido; regra de voo de
observação; licença do dNATY; classe "não é folha" (precisa de captura própria); recalibrar o
conformal do café (GPU).

## Ensino pelo agrônomo (26/10)

O agrônomo ensina a IA com o porquê e a lesão marcada; a lição volta como treino, nos pareceres e
num painel. Ver [`ENSINO.md`](ENSINO.md).
