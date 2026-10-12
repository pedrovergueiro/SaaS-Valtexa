# Plano — SaaS ValTexa robusto: contas, IA, cadastros e fluxos

> 02/10/2026. **Plano, nada implementado.** Executar fase a fase (seção 8); cada fase
> fecha com testes verdes, um roteiro ponta a ponta no simulador e a documentação
> atualizada. Antes de começar, responder as decisões da seção 9.

---

## 0. Diagnóstico — por que hoje parece solto

**O que existe** (13 routers, ~127 rotas): contas (`Tenant`, `User`, `Membership`,
`UserSession`), fazendas/talhões/zonas, frota (`DeviceModel`, `Device`, credenciais,
tokens de provisionamento), missões (estados, segurança, comando assinado), percepção
(`Observation`, `Detection`, `Diagnosis`, `Decision`), agro (`Product`, lote, tanque,
`Application`, `Verification`), coletas/datasets/`ModelVersion` (admin), lavoura 3D,
auditoria/eventos, e o repasse das plantas da IA (plantas, mapa, prevalência, evolução).

**Os problemas:**

1. **Dois "admins" misturados.** `Role.ADMIN` é do cliente; a equipe ValTexa é
   `User.is_platform_admin` e usa o **mesmo console**, com 5 itens extras escondidos por
   capacidade. Não há console de plataforma.
2. **Uma flag só para a equipe**: não distingue suporte, operação de IA e comercial.
3. **Sem plano, limite ou uso.** `Tenant.contracted_service` é texto livre; nada limita
   talhões, dispositivos, quadros analisados ou modelos.
4. **IA sem governança.** O cliente escolhe o modelo por talhão entre tudo que a
   inferência lista; a plataforma não decide quais versões cada cliente usa, não vê a
   saúde da inferência, e a calibração da fusão (02/10/2026) não aparece no SaaS.
5. **Cadastros incompletos.** O talhão não tem espaçamento **entre plantas** (a fusão
   usa 2,5 m e 4 m fixos), nem fileiras; o usuário nasce com senha criada por outro (sem
   convite); o cliente não tem plano; o produto não alimenta a prescrição.
6. **Caminhos paralelos.** O `decision_engine` decide pela fração de observações, sem a
   fusão por planta, a incidência (`/fields/{id}/incidence`) ou a prescrição
   (`/fields/{id}/prescription`) do VALTEXA-B — essas duas nem têm rota no SaaS.
7. **Sem fluxo.** Telas soltas (Painel, Mapa, Missões, Frota, Talhões, Coletas, Lavoura
   3D, Aplicações, Insumos), sem primeiros passos, sem "próxima ação", sem a corrente
   talhão → passada → planta → prescrição → aplicação → verificação.

---

## 1. Contas e papéis: dois mundos separados

### 1.1 Plataforma (equipe ValTexa) — console próprio em `/plataforma`

`User.platform_role` (novo; migração: `is_platform_admin=true` → `superadmin`):

| Papel | Faz |
| --- | --- |
| `superadmin` | tudo, inclusive papéis de plataforma, planos e exclusões |
| `suporte` | lê qualquer cliente; **entra como cliente** com motivo e prazo; reenvia convite, redefine acesso |
| `ia_dados` | catálogo e liberação de modelos, calibração da fusão, coletas, datasets, treinos, validação de campo |
| `operacoes` | estoque e provisionamento de dispositivos, atribuição a clientes, missões assistidas, contorno/relevo |
| `comercial` | clientes, planos, limites, contratos, uso — **sem** dado agronômico |

Regras: equipe da plataforma **não** é membro do cliente; "entrar como cliente" abre
sessão de suporte com faixa visível no topo, motivo obrigatório, expiração (ex.: 2 h),
somente leitura por padrão, e grava auditoria nos dois lados (cliente e plataforma).

### 1.2 Cliente — o console de hoje, limpo

Papéis atuais mantidos, com o que cada um vê revisado:

| Papel | Foco |
| --- | --- |
| `owner` | tudo do cliente + plano e uso (leitura), equipe, faturas |
| `admin` (na tela: **gestor**) | equipe (menos o dono), fazendas, talhões, dispositivos, insumos |
| `agronomist` | diagnóstico, fila, rótulo de plantas, prescrição e aprovação (com nome e CREA), validação de campo, relatório técnico |
| `operator` | missões, frota, tanques |
| `technician` | dispositivos e manutenção |
| `auditor` / `viewer` | leitura |

"Papéis e permissões" em Configurações → Equipe: a matriz legível de quem pode o quê.

### 1.3 Só a plataforma

Criar/suspender cliente; plano e limites; catálogo e liberação de modelos; calibração da
fusão; coletas, datasets e treinos; estoque e provisionamento de hardware; auditoria
global; saúde da inferência; uso e custo por cliente; flags de recurso.

### 1.4 Só o cliente

Operar a própria fazenda: missões, aprovação de aplicação (agrônomo nomeado), rótulos
de campo, equipe própria, insumos, preços e economia da prescrição.

---

## 2. Planos, limites e uso

- **`Plan`**: nome; limites (fazendas, talhões, hectares, dispositivos, usuários,
  quadros analisados/mês, retenção de imagem em dias); culturas e modelos liberados;
  recursos (prescrição, lavoura 3D, validação de campo, API externa, relatórios).
- **`Subscription`**: cliente, plano, início/fim, estado (`teste`, `ativo`, `suspenso`,
  `cancelado`), sobreposições por cliente, `billing_customer_id` reservado.
- **`UsageCounter`** mensal por cliente: quadros analisados, missões, hectares varridos,
  armazenamento.
- **Aplicação**: dependências `require_feature()` e `check_quota()` nas rotas; resposta
  402/409 com mensagem em português; console mostra uso × limite e avisa a 80%.
- Plataforma: telas de planos, atribuição, sobreposição e relatório de uso.
- Cobrança por gateway fica fora desta rodada (decisão 6).

---

## 3. IA e modelos

### 3.1 Na plataforma

- **Catálogo unificado**: lê `/models` e `/models/choices` da inferência + artefatos de
  cada versão (conformal, cabeça, espécie, **calibração da fusão** com id e data);
  estado da versão: `em teste`, `liberada`, `obsoleta`, `bloqueada`.
- **Liberação**: padrão por cultura (global) e lista permitida + padrão **por cliente**;
  só versão `liberada` chega ao cliente.
- **Saúde da inferência**: no ar/fora, latência p50/p95 por modelo, erros, versão; alerta
  quando cai. Quadro não se perde: vai para `ProcessingJob` e reprocessa.
- **Calibração da fusão**: id, data, detecção e alarme falso medidos, nº de plantas;
  qual passada usou qual calibração; publicar nova (upload do `.fusion.json` ou job que
  roda `training.fit_fusion` no servidor de IA).
- **Pipeline de dados** (já começado em Coletas/Dataset): coleta → dataset congelado →
  treino (registra `ModelVersion` com métricas) → avaliação no teste de campo →
  **promoção com portão** (métrica mínima + aprovação) → liberação.
- **Validação de campo** por cliente piloto: fileiras de validação, rótulos, resultado do
  `fit_fusion evaluate`, antes × depois de recalibrar.

### 3.2 No cliente

- Seleção do modelo por talhão (existe, `AiModelCard`) **restrita ao liberado** para ele.
- **Ficha do modelo** em linguagem de produtor: o que detecta, culturas, limitações,
  desempenho medido no campo, data.
- Cada planta e passada mostra o modelo e a calibração que a julgaram (`calibration_id`
  já vem da IA).

### 3.3 Ligações SaaS ↔ IA que faltam

| O quê | Onde |
| --- | --- |
| `GET /v1/fields/{id}/incidence` (repasse) + histórico por passada | SaaS `plants.py` |
| `POST /v1/fields/{id}/prescription` com produto do cadastro e economia do cliente → **proposta de aplicação** ligada à aprovação do agrônomo e à missão de aplicação | SaaS `plants.py` + `agro` |
| `decision_engine` decide pelo status/posterior **por planta** (fusão); o atual vira reserva quando a IA não guarda talhões | SaaS `services/decision_engine.py` |
| Espaçamento real do talhão para a IA (`plant_spacing_m` no rover-frame) | VALTEXA-B `rover_api` + `plant_fusion` |
| Exportar o registro de recortes do talhão e importar rótulos por planta → job `fit_fusion evaluate` | VALTEXA-B (rotas novas) + SaaS (job) |

---

## 4. Cadastros completos

Todos com validação, auditoria, edição concorrente segura e estado vazio com a próxima ação.

**Cliente**

- **Fazenda**: nome, produtor (CPF/CNPJ), endereço, município/UF, CAR, coordenada,
  responsável técnico (agrônomo + CREA), contatos.
- **Talhão**: contorno (existe), cultura, variedade, plantio, espaçamento entre ruas
  (existe) **e entre plantas (novo)**, azimute das ruas (existe), nº estimado de ruas e
  plantas, irrigação, estágio (existe), modelo de IA (existe), **fileiras de validação**.
- **Equipe**: **convite por e-mail** com link de ativação e validade (no lugar da senha
  criada por outro), papel, desativar, sessões (existe); 2FA depois.
- **Dispositivos**: vincular por token (existe), apelido, talhões permitidos, manutenção.
- **Insumos**: produto com registro MAPA, culturas e alvos da bula, dose mín./máx.,
  carência, eficácia declarada, preço; lotes (existe); estoque.
- **Economia** por fazenda/talhão: perda por planta, custo operacional (a prescrição
  exige; hoje vem solta na requisição).
- **Notificações**: quem recebe o quê (nova infecção, incidência acima de X, missão
  bloqueada, dispositivo fora do ar) — e-mail e aviso no console na primeira versão.

**Plataforma**

- **Clientes** (criar/editar já existe): + plano, estado, responsável comercial,
  limites, histórico.
- **Usuários globais**: buscar, bloquear, reenviar convite, ver vínculos.
- **Dispositivos**: estoque, atribuição a cliente, firmware, manutenção/RMA.
- **Catálogos de referência**: culturas, doenças (nome em português, sintomas, fotos),
  produtos de referência da bula, unidades.
- **Planos**.

---

## 5. Fluxos ponta a ponta

Cada fluxo vira um roteiro automatizado (Playwright contra o simulador).

| # | Fluxo | Passos |
| --- | --- | --- |
| F1 | **Contratação** (plataforma) | cliente → plano → convite ao dono → dispositivos atribuídos → modelos liberados → checklist "pronto para operar" |
| F2 | **Primeiros passos** (cliente) | ativar conta → fazenda → talhão (contorno, cultura, espaçamentos) → modelo → vincular rover → equipe → primeira varredura; checklist persistente no Painel |
| F3 | **Varredura → diagnóstico** | planejar (rota pelo contorno) → autorizar (segurança) → executar → plantas e incidência ao vivo → fechar passada → **resumo da passada** (novas infecções, pioras, incidência com intervalo) → notificação |
| F4 | **Decisão → aplicação → verificação** | do resumo ou do mapa de plantas → prescrição (bula + economia) → proposta → aprovação do agrônomo → missão de aplicação (tanque, dose) → registro → verificação agendada → evolução/AUDPC; tudo numa **linha do tempo do talhão** |
| F5 | **Revisão do agrônomo** | fila (existe) → rótulo → vira dado de treino (com consentimento) |
| F6 | **Validação de campo (piloto)** | marcar fileiras → agrônomo rotula **todas** as plantas delas no celular (lista da fileira, status do sistema, sadia/doença) → CSV automático → job `evaluate` → relatório (sensibilidade, alarme falso, incidência real × estimada) → plataforma decide recalibrar → nova calibração vale nas próximas passadas |
| F7 | **Suporte** | cliente abre chamado com contexto (talhão, missão) → suporte vê e entra como cliente (assistido) → responde |
| F8 | **Relatórios** | por passada, talhão e fazenda: PDF e CSV (mapa de plantas, incidência, prescrição, aplicações, custos) |

---

## 6. Console: navegação

**Cliente**

- **Painel por papel**: agrônomo (fila, talhões que pioraram), operador (missões e
  frota), dono (resumo, custos, uso do plano).
- **Menu por tarefa**: Lavoura (fazendas, talhões, mapa, 3D) · Operação (missões, frota,
  aplicações) · Diagnóstico (plantas, fila, validação) · Insumos · Relatórios ·
  Configurações (equipe, notificações, plano).
- **Hierarquia navegável** Fazenda → Talhão → Passada → Planta, com trilha (breadcrumb);
  cada entidade liga às relacionadas (missão ↔ talhão ↔ passada ↔ prescrição ↔ aplicação
  ↔ verificação).
- Estado vazio sempre com a próxima ação ("Talhão sem contorno → Desenhar contorno").
- Central de notificações e busca global.

**Plataforma** (layout e cor diferentes, para ninguém confundir): Clientes · Planos e uso
· Dispositivos · IA (catálogo, liberação, calibração, saúde, validação) · Dados (coletas,
datasets, treinos) · Auditoria global · Suporte.

---

## 7. Robustez técnica (vale para todas as fases)

- **Isolamento entre clientes**: teste gerado do OpenAPI que tenta ler e escrever dado de
  outro cliente em toda rota.
- Erros padronizados (código, mensagem em português, campo); paginação, ordenação e
  filtro iguais em toda lista; `If-Match` em edição; `Idempotency-Key` em criação.
- Postgres fora de dev (o `/health` já avisa do SQLite), migrações versionadas, backup.
- Quadro para a IA por fila com nova tentativa (`ProcessingJob`), para não perder dado
  quando a inferência cai.
- `SESSION_SECRET` e `COMMAND_SIGNING_SECRET` obrigatórios e diferentes fora de dev.
- Logs com cliente, usuário e requisição; métricas; alertas.
- LGPD: exportar e apagar dados do cliente; consentimento para usar imagem em treino.
- Seeds com um usuário de cada papel (cliente e plataforma) para testes e demonstração.

---

## 8. Fases, em ordem

| Fase | Entrega | Prioridade | Tamanho | Depende |
| --- | --- | --- | --- | --- |
| 1 | **Contas**: `platform_role`, console `/plataforma`, entrar como cliente auditado, convites por e-mail, matriz de papéis, testes de isolamento | P0 | G | — |
| 2 | **Cadastros**: fazenda, talhão (espaçamento entre plantas, fileiras de validação), insumos com bula, economia, estados vazios | P0 | M | 1 |
| 3 | **IA conectada**: catálogo e liberação por cliente, saúde da inferência, repasse de incidência e prescrição, decisão pela fusão, espaçamento do talhão na IA (VALTEXA-B), calibração visível | P0 | G | 1, 2 |
| 4 | **Validação de campo (F6) + relatórios (F8)** — o que o piloto precisa | P0 | M | 2, 3 |
| 5 | **Fluxos guiados F1–F4**: primeiros passos, resumo da passada, linha do tempo, proposta → aprovação → aplicação → verificação | P1 | G | 2, 3 |
| 6 | **Planos, limites e uso** | P1 | M | 1 |
| 7 | **Suporte (F7), notificações, LGPD, observabilidade** | P2 | M | 1, 5 |

**Aceite de cada fase:** pytest e lint verdes, `npm run build` verde, roteiro do(s)
fluxo(s) da fase rodando contra o simulador com a IA de verdade, docs (`API.md`,
`AUTHENTICATION.md` e as do fluxo) atualizadas, e esta tabela marcada.

---

## 9. Decisões que precisam de resposta antes da fase 1

1. **Papéis de plataforma**: os cinco da seção 1.1 servem? Quem da equipe fica em cada?
2. **Planos**: quantos, nomes, limites, e o que entra em cada (prescrição? 3D? API?).
3. **Métricas do modelo para o cliente**: ele vê detecção e alarme falso, ou só a ficha
   em linguagem de produtor?
4. **Imagem do cliente no treino**: opt-in no contrato, ou escolha por cliente?
5. **Notificações**: só e-mail e aviso no console agora; WhatsApp depois?
6. **Cobrança**: gateway agora, ou só controle manual de plano e limite?
7. **Entrar como cliente**: o suporte só lê, ou pode agir em modo assistido?

---

## 10. Como executar

- Uma fase por vez, numa branch nova do SaaS; **sem commit automático** — quem commita é
  o Pedro.
- Cada fase começa relendo este plano e termina pelo aceite da seção 8.
- As fases 3 e 4 mexem também no VALTEXA-B (espaçamento do talhão, rótulos e `evaluate`
  pela API); os arquivos de terreno em andamento do VALTEXA-B ficam intocados.
