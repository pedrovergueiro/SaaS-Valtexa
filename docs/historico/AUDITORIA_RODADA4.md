# Auditoria da Rodada 4 — Parte 1: o Nível 4 contra o brief 7.x

> Revisão hostil, feita em 18/10/2026 na branch `claude/cerebro-agronomico`, antes de mudar
> qualquer linha. Régua: `docs/BRIEF_ENXAME_HETEROGENEO.md` (7.1, 7.2, 7.3) lido com
> `docs/RODADA4.md` — **não há mais base na fazenda**, cada Rover tem a sua Starlink, e o
> volume enviado virou requisito. Onde o brief diz "a Base", leia "a plataforma".
>
> Legenda: **COBRE** (feito e testado), **PARCIAL** (existe, mas não fecha o item), **FALTA**,
> **BASE** (depende da base, que agora é legado — precisa ir para a plataforma ou sair do
> caminho principal).

## Suítes antes de mudar (números reais desta sessão)

| Suíte | Comando | Resultado |
| --- | --- | --- |
| IA | `KERAS_BACKEND=torch pytest` (Python 3.12, `dnaty` 2.2.1) | ver `docs/PROGRESSO.md` (Rodada 4 — Parte 1): 1 falha **pré-existente** em `test_conformal.py::TestInThePrediction::test_is_null_without_calibration` — o retrato local trouxe `ia/models/*.conformal.json` reais, e o teste supõe a pasta sem calibração |
| SaaS | `pytest` | ver PROGRESSO |
| Rover | `pytest` | **333 passed, 3 skipped** |
| Console | `npx vitest run` / `npm run build` | **144 passed** (23 arquivos) / build ok |

## 7.1 — Fusão federada de priores

| Passo do brief | Situação | Achado |
| --- | --- | --- |
| 1. Cada Rover coleta | COBRE | resultados da Edge AI com os recortes (`tiles`) sobem para a fusão por planta (`ROVER_RUNTIME.md` §15). |
| 2. Observações validadas | PARCIAL | há régua de captura, conformal e percepção ativa por quadro (§26), e o rótulo do agrônomo (`PlantLabel`). **Não existe** a regra "esta observação entra numa estatística compartilhável": nada separa o que é válido para fusão entre talhões (mesmo modelo, mesma cabeça, mesmo perfil, captura dentro da régua). |
| 3. Estatísticas/priores compatíveis com um protocolo | **FALTA** | não há representação compartilhada definida. O único "prior" que existe é o `<modelo>.prior.json` (prevalência fixa por cultura, do treino) e o prior fundido do **enxame** (prioridades da missão — outra coisa: é decisão, não estatística). |
| 4. Envio "à Base pela rede local" | BASE → plataforma | não há base. O envio é pela Starlink do Rover direto à plataforma, e **conta no orçamento de dados** (ver abaixo). |
| 5. Verificar integridade, versão, origem, compatibilidade | **FALTA** | o protocolo do dispositivo já autentica a origem (assinatura do robô) e o `sha256` do JSON canônico de cada registro (`edge_sync._valida_registro`); falta a checagem **de compatibilidade estatística** (taxonomia, cabeça, perfil, protocolo de validação, janela). |
| 6. Mecanismo de fusão | **FALTA** | `dnaty.core.memory.merge_priors` existe no pacote, mas **funde estatísticas de operadores de mutação** (`{operador: escore}`, centrados na média e escalados ao máximo) — não serve para prevalência: apaga o nível (2% e 20% viram a mesma forma) e ignora o tamanho da amostra. Ver `docs/FEDERADO.md`. |
| 7. Avaliar antes de distribuir | **FALTA** | o padrão do projeto existe para a cabeça (portão de regressão do aprendizado contínuo, §24) e não para priores. |
| 8. Distribuir aos autorizados | PARCIAL | a política de compartilhamento (`compartilhamento.POLITICA`) e o envelope assinado (missão, comando, OTA) existem; não há classe "prior por estrato" na política nem rota de distribuição. |
| 9. Rover verifica antes de usar | PARCIAL | o Rover confere assinatura de missão/comando/OTA e a procedência da cabeça (`_confere_procedencia`); nada para prior. |
| Anti-eco | PARCIAL | a regra do gêmeo (o Rover só entra pela fusão; o prior desce para decidir, nunca como evidência) cobre o **talhão**. Entre talhões, **falta**: um prior de estrato que volte ao talhão que o alimentou conta o dado dele duas vezes (uma como prior, outra como evidência local). |
| "Poucos kilobytes" | não medido | o brief pede medir; ninguém mediu. |

**Veredito 7.1:** nada feito além das peças de transporte e assinatura. É o maior buraco da
Parte 1, e o risco principal é de **conceito**: tratar `merge_priors` como fusão de
prevalência daria um número com cara de estatística e sem significado.

## 7.2 — Coordenação drone → Rover

| Etapa | Situação | Achado |
| --- | --- | --- |
| 1. Mapeamento aéreo (vigor, estrutura do dossel) | **FALTA** a importação | `POST /fields/{id}/gemeo/observacoes` aceita evidência **por planta e por doença** (LLR) com o canal `drone` (0,45 / 0,06, suposição). Ninguém produz essa LLR: não há como **importar o levantamento** (grade/GeoJSON de NDVI, altura do dossel, falhas) e transformá-lo em evidência. O vigor não é específico de doença — exige um **canal próprio** (`drone_vigor`), mais fraco e declarado como suposição. |
| 2. Priorização: histórico do talhão | PARCIAL | o gêmeo assimila todas as passadas (o histórico entra no estado); `Tarefa.dias_sem_ver` é calculado e **não pesa** em nada. |
| — incidência anterior | PARCIAL | entra só pelo estado do gêmeo; incidência de safras anteriores (sem passada do Rover) não tem entrada. |
| — incerteza | COBRE | VOI / informação mútua (`ia/app/gemeo/prioridade.py`). |
| — disponibilidade | COBRE | só `DISPONIVEL` (`fleet_state`). |
| — condições de acesso | **FALTA** | o custo da tarefa é distância + percurso + manobra; declividade, trecho intransitável e obstáculos não entram. Os arquivos de terreno da IA podem ser lidos/chamados, não editados. |
| — bateria | COBRE | autonomia × (bateria − 25%). |
| 3. Missão ao Rover mais adequado | COBRE | guloso por valor/s com custo de deslocamento; missão em `DRAFT` (`criar_missoes`). |
| 4. Revisão e decisão | COBRE | o resultado vai à fusão e ao agrônomo (`validacao_campo`, fila de revisão); nada autoriza sem humano. |
| 5. Execução controlada | COBRE | aplicação só sai da prescrição aprovada e do `safety_engine` (RTK fixo, produto, tanque, aprovador). |
| Voo de observação do drone | **FALTA (decisão do Pedro)** | o `safety_engine` só aceita missão sem aplicação feita por Rover; o plano mostra o sobrevoo e recusa criar. A regra fica **desenhada e desligada** nesta parte. |

## 7.3 — Alocação por incerteza

| Item | Situação | Achado |
| --- | --- | --- |
| `f(risco, incerteza, impacto, custo, disponibilidade)` | COBRE | VOI junta risco × incerteza × impacto (contágio, números do produtor); custo e disponibilidade no alocador. |
| Calibrada contra **missões excessivas** em áreas pouco relevantes | **FALTA** | o guloso gasta **toda** a bateria enquanto houver tarefa com valor > 0: não existe valor mínimo por minuto de robô (o custo de operar não entra). Em talhão sadio, manda o Rover rodar por décimos de bit. |
| Calibrada contra **regiões importantes esquecidas** | **FALTA** | VOI ≈ 0 onde o gêmeo está "certo" de que está sadio. Se o gêmeo erra (foco novo fora do alcance do núcleo de contágio, entrada por vizinho), o trecho nunca é revisto: não há piso de vigilância por tempo sem ver. |
| Benchmark | PARCIAL | `mede_enxame.py` (VOI vs. alternativas) e `mede_alocacao.py` (valor coberto) medem o ganho, não os dois modos de falha acima. |

## O que depende da base (legado) e o destino

| Peça | Onde | Destino nesta rodada |
| --- | --- | --- |
| Distribuição local de OTA pela base | `base/valtexa_base/distribuicao.py`, `ENXAME.md` §7 | **fora do caminho principal**. Cada Rover baixa da plataforma pela sua Starlink; o custo disso entra no orçamento de dados (o pacote é por SHA-256: o Rover não baixa duas vezes o mesmo). Doc reescrita. |
| "Sem internet, a base não realoca / o console da base arma as do cache" | `enxame.py` (docstring), `ENXAME.md` §6 | o caminho é: sem Starlink, o Rover termina a missão que tem (política offline, já existe) e nada é realocado. Texto corrigido. |
| Rede "via base" do Rover | `rover/valtexa_rover/hal/rede_base.py`, `enlace/` | já é **opcional** (`hardware.json` `rede.modo = "base"`); o padrão é `HttpNetwork` direto. Mantido como legado documentado. |
| Pré-busca noturna na base | `ENXAME.md` §9 | obsoleta: sai da lista. |
| Fusão de priores "na Base" (7.1) | brief | vai para a plataforma (`saas/valtexa/services/federado.py`). |

## Orçamento de dados (requisito novo, não estava no brief 7.x)

| Item | Situação |
| --- | --- |
| Teto de bytes por dia / por missão | **FALTA** — a fila envia tudo o que estiver pronto. |
| Contabilidade do que subiu | PARCIAL — `SyncReport.bytes_sent` conta só os chunks de arquivo de um passo, sem persistir, sem registros, telemetria nem cabeçalhos. |
| Ordem de corte | PARCIAL — a fila respeita prioridade, mas nunca **corta**: com rede, tudo sobe. |
| Tempestade de eventos | **FALTA** — o caso real (511/511 quadros em evento) manda original + 6 quadros de contexto de cada quadro. |
| Deduplicação por planta | **FALTA** — cada quadro da mesma planta, em cada câmera, sobe o seu original. |
| Relatório no console | **FALTA**. |

## Ordem do trabalho desta parte

1. Orçamento de dados no Rover (corte, tempestade, deduplicação, contabilidade) e na
   plataforma (configuração assinada na missão, relatório, console), com a estimativa
   de volume em três cenários.
2. 7.1 de verdade: estatística por estrato, fusão hierárquica com encolhimento, checagens,
   anti-eco por "deixa o talhão de fora", avaliação, distribuição assinada, verificação no
   Rover; bytes medidos; `merge_priors` avaliado.
3. 7.2/7.3: importação do levantamento aéreo com canal próprio, custo de acesso, valor
   mínimo por minuto e piso de vigilância, benchmark dos dois modos de falha; regra de voo de
   observação desenhada e desligada.
