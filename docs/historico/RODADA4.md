# Rodada 4 — enxame heterogêneo e cérebro agronômico (18/10/2026)

Branch: **`claude/cerebro-agronomico`**, a partir do retrato local de 18/10/2026 (por cima de
`claude/base-fazenda`, 076918e). O retrato traz tudo o que o Pedro fez localmente desde a
rodada 3 (Níveis 2, 3 e 4, abaixo). Especificações: `docs/BRIEF_ENXAME_HETEROGENEO.md` (7.x)
e `docs/BRIEF_CEREBRO_AGRONOMICO.md` (8.x). As regras de `docs/CONTEXTO_NUVEM.md` continuam
valendo; esta página manda onde as duas divergirem.

## Pastas

| Pasta | Projeto local |
| --- | --- |
| `ia/` | VALTEXA-B — IA, fusão por planta, gêmeo digital, aprendizado contínuo |
| `saas/` | VALTEXA-SAAS — plataforma, console (`saas/web`) |
| `rover/` | VALTEXA-ROVER — Runtime do Rover (Edge AI, percepção ativa, sync) |
| `base/` | VALTEXA-BASE — **legado** (ver "Sem base" abaixo) |

## Decisões do Pedro que mudam o desenho

1. **Não existe mais base de comunicação na fazenda.** Cada Rover tem a **sua própria
   Starlink** e fala direto com a plataforma. Onde os briefs dizem "a Base" (verifica, funde,
   prioriza, distribui), quem faz é a **plataforma** (`saas/`). Não apague `base/` nem o
   código de enlace via base (`rover/valtexa_rover/enlace/`); deixe como legado/opcional,
   fora do caminho principal, e documente isso. Não crie funcionalidade nova que dependa da
   base nem de "rede local da fazenda".
2. **Cada Rover é um enlace medido (Starlink própria).** O volume enviado passa a ser
   requisito: tudo o que esta rodada fizer sobe pela Starlink do Rover e precisa caber num
   orçamento (ver "Orçamento de dados").
3. **Foco é CAFÉ** (ferrugem, cercosporiose, phoma, bicho-mineiro; Sul de Minas, relevo de
   morro). O exemplo de Sigatoka do 8.2 é ilustrativo; testes e exemplos em café.
4. **Princípio de Ouro (8.4) é regra dura**: o agente raciocina, explica e propõe; o agrônomo
   valida e autoriza; o Safety Engine determinístico (`saas/valtexa/services/safety_engine.py`)
   verifica e libera. Nenhum caminho de código do agente/copiloto pode: criar missão fora de
   RASCUNHO, aprovar/autorizar prescrição ou aplicação, mudar limiar de modelo, nem chamar o
   Safety Engine "em nome" do agrônomo. Isso precisa de **teste que prove** (varrer as rotas e
   serviços do agente e mostrar que nenhum escreve estado autorizado).
5. **Voo de observação do drone ainda não tem regra de segurança** (o `safety_engine` só
   aceita missão sem aplicação para ROVER). Criar essa regra é decisão do Pedro: implemente o
   desenho (o que a regra checaria), deixe **desligado** e marcado "aguarda decisão do Pedro";
   a coordenação drone → Rover funciona com o levantamento aéreo **importado** (arquivo/mapa),
   sem a plataforma comandar o voo.

## O que já existe (não refazer — auditar, reaproveitar, corrigir)

- **Nível 2** (IA + Rover): aprendizado contínuo da cabeça com portão de regressão
  (`ia/app/inference/continual.py`, `ia/training/adapt_campo.py`); tipos de atualização e
  procedência (`ia/app/inference/atualizacao.py`, copiado byte a byte em
  `rover/valtexa_rover/edge_ai/vendor/`); motor com plasticidade do dNATY medido e **não
  adotado** (`ia/training/motor_dnaty.py`, `ia/MODELS.md`); percepção ativa com conformal,
  régua de captura, reobservar, luz (`rover/valtexa_rover/runtime/percepcao.py`); geometria 3D
  por recorte (`rover/.../edge_ai/geometria.py`); lesões no referencial da planta
  (`ia/app/plant_fusion.py`, `GET /fields/{f}/plants/{p}/lesoes`). Doc: `docs/ROVER_RUNTIME.md`
  §23–26.
- **Nível 3** (gêmeo digital): `ia/app/gemeo/` (SEIR por planta em probabilidade, filtro
  Bayesiano com a razão da fusão, previsão, clima, prescrição por risco), `ia/app/gemeo_api.py`,
  `saas/valtexa/services/twin.py`.
- **Nível 4** (enxame): valor da informação e prioridades (`ia/app/gemeo/prioridade.py`,
  `GET /fields/{id}/gemeo/prioridades`), evidência do drone com canal próprio
  (`POST /fields/{id}/gemeo/observacoes`, `ia/app/gemeo/epidemia.py` `CANAIS`), alocação de
  missões na plataforma (`saas/valtexa/services/enxame.py`, `api/routers/enxame.py`,
  `saas/docs/ENXAME.md`), compartilhamento controlado (`services/compartilhamento.py`),
  prioridades na missão do Rover (`rover/.../runtime/prioridades.py`). Medido: VOI nunca
  perdeu em 24 combinações; alocação 1 Rover 35,7% vs varredura 6,2%. O 7.2 e o 7.3 do brief
  novo estão **em boa parte feitos**: comece auditando contra o brief e feche as lacunas.
- Prescrição: `ia/app/prescricao.py`, `ia/app/gemeo/prescricao_risco.py`; produtos/bula no
  SaaS (`saas/valtexa/models/agro.py`); `decision_engine.py`; clima (Open-Meteo) **desligado
  por padrão** (`clima_open_meteo=False`): a API não faz chamada externa por padrão.

## dNATY `merge_priors` (7.1) — ponto de partida da avaliação

`dnaty.core.memory.merge_priors` (pacote `dnaty` 2.2.1 no PyPI, BSL-1.1) funde **estatísticas
de sucesso dos operadores de mutação** da busca de arquitetura (`EpisodicMemory.to_prior()`:
`{operador: escore}`, normalizados e com média ponderada). **Não é** uma fusão de prevalência,
de evidência de doença nem de pesos de rede. Avalie com isso em mente e escreva a conclusão
em `docs/FEDERADO.md`:

- para o que ele serve aqui (ex.: aquecer a otimização de modelo da borda por dispositivo —
  se fizer sentido, medido);
- o que os Rovers devem compartilhar de fato para o cenário A/B/C (variedade, solo, estágio):
  provavelmente contagens validadas por estrato (Beta/Dirichlet) com fusão hierárquica e
  encolhimento — defina a matemática, as condições de compatibilidade (mesma taxonomia de
  classes, mesmo modelo/cabeça, mesmo protocolo de validação, janela de tempo), o
  anti-eco (não contar a mesma observação duas vezes — o gêmeo já tem regra disso) e como
  avaliar a atualização antes de distribuir;
- medir o tamanho real do que trafega (bytes por Rover por dia) — o brief exige.

## Orçamento de dados (novo requisito, por causa da Starlink no Rover)

Hoje (`rover/valtexa_rover/runtime/retention.py`, `sync.py`, `buffer.py`, `config.py`):

- NORMAL sobe como reduzida 320 px JPEG 60 (todas), mais metadados; DOENÇA/PRAGA/ANOMALIA
  sobe o ORIGINAL + sequência do buffer (3 antes + 3 depois a 1024 px); BAIXA_CONFIANÇA sobe
  original; vídeo ao vivo só sob pedido; percepção ativa guarda vistas das incertas;
- a fila envia por prioridade, em chunks, com retomada — **mas não há teto de bytes por dia
  nem por missão**. Um modelo que dispara evento demais (já visto em vídeo real: 511/511
  quadros) manda original + 6 quadros de contexto de cada quadro.

Faça: orçamento por Rover (bytes/dia e por missão, configurável no `rover.json` e pela
plataforma), contabilidade real do que subiu, ordem de corte por prioridade (comando,
segurança, telemetria e eventos críticos nunca cortam; o resto espera ou vira amostra),
detector de "tempestade de eventos" (taxa de evento anormal → limita originais, guarda o
resto no disco, alerta a plataforma), deduplicação por planta (vários quadros da mesma planta
→ só os k melhores originais), relatório de consumo no console. Tudo testado; números
simulados marcados como simulados.

## Cérebro agronômico (8.x) — regras

- **Fontes**: repositório de conhecimento versionado (cada documento com origem, versão, data
  de publicação, `verificado_em`, `valido_ate`, hash, licença). Regulatório (registro MAPA,
  bula, alvo, dose, intervalo de segurança) **vencido ou não verificado bloqueia** uso em
  recomendação operacional — o parecer diz isso. **Não invente** bula, registro, dose nem
  número de publicação: sem fonte real carregada, o repositório fica vazio e o parecer diz
  "sem fonte". Dados de exemplo só em teste, marcados como fictícios.
- **Sem chamada externa por padrão** (como a API da IA). O modelo de linguagem é um provedor
  plugável e **desligado por padrão**; sem ele, o parecer sai de um compositor
  **determinístico** a partir do dossiê de evidências estruturado. Com ele, o texto só pode
  usar o que está no dossiê/RAG, com citação de cada afirmação a uma evidência ou fonte; a
  validação de citações recusa o texto que afirma o que não está lá. Chave nunca no código.
- O parecer nunca transforma probabilidade em certeza: mostra a hipótese principal e as
  alternativas (conjunto conformal), a qualidade da evidência, a incerteza e o horizonte do
  gêmeo, e o que falta verificar antes de agir.
- Planejamento (8.3): apoio à decisão com premissas registradas e revisão humana. Reaproveite
  o alocador do enxame (rotas, bateria, distribuição) e as prioridades do gêmeo. Inclinação e
  obstáculos: os arquivos de terreno da IA são **intocáveis** (`ia/app/basemap.py`,
  `boundary.py`, `obstacles.py`, `terrain.py`, `terrain_api.py`) — pode **ler/chamar**, não
  editar. Rotação de ingredientes ativos: por modo de ação (FRAC) só a partir de dados
  cadastrados com fonte; insumos: previsão com intervalo a partir do histórico de aplicações.

## Coordenação

- **Não mexa** (o Pedro calibra localmente): `rover/valtexa_rover/edge_ai/` (exceto ler),
  `ia/training/fit_edge.py`, `ia/training/fit_fusion.py`, os limiares dos perfis. Em
  `ia/app/plant_fusion.py` e `ia/app/gemeo/` só mudança **aditiva**, com teste e registrada no
  PROGRESSO.
- Registre tudo em `docs/PROGRESSO.md` numa seção **Rodada 4**, por parte: feito, números
  reais das suítes, o que ficou simulado e por quê, decisões pendentes do Pedro, lista de
  arquivos (para a integração local).
