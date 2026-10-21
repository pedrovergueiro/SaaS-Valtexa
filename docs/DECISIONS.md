# Registro de decisões

> Para a equipe não reimplementar o que já foi descartado, nem desfazer o que foi decidido,
> sem conhecer o motivo. Formato: data · decisão · por quê · consequência. As mais novas
> primeiro. Decisões anteriores à consolidação estão espalhadas em `docs/historico/` e no
> `VALTEXA-B/MODELS.md` (lições medidas); as principais estão resumidas aqui.

## 20/10/2026 — Consolidação

**D-01 · Não existe mais base da fazenda nem rádio; cada Rover tem a própria Starlink.**
Decisão do Pedro (hardware). A pilha de rádio (VALTEXA-BASE, `enlace/` e `rede_base.py` no
Rover, rotas/serviços/tela da base no SaaS, ensaios da FASE ENLACE) foi **arquivada** em
`archive/legacy/radio-fazenda/` nos dois repositórios. A base nunca rodou em hardware. O que
servia à Starlink ficou: a conferência do relógio (`hal/relogio.py`, ensaio `relogio` na FASE
0). Colunas do banco ficam (migrações aplicadas não se reescrevem). Um `hardware.json` com
`"rede": {"modo": "base"}` agora falha no boot com mensagem clara.

**D-02 · Duas "fusões por planta" ficam, com papéis diferentes.** A **calibrada** (IA,
`app/plant_fusion.py`) é a **fonte oficial** do diagnóstico por planta, da incidência, da
prescrição e do gêmeo. A **operacional** (SaaS, `missao_resultado.plantas_da_missao`) é o
"estado da missão": doente/suspeita/revisar/sadia a partir do que a nuvem já confirmou;
alimenta o motor de decisão, os avisos e o relatório. Unificar mudaria o comportamento do
motor de decisão — fica para quando houver dado de campo e revisão do Pedro.

**D-03 · Experimentos ficam onde estão, marcados no inventário.** `robustez_captura`,
`motor_dnaty`, `dnaty_pipeline`, `pinn_dispersao` e os `mede_*` são CLIs documentados no
`MODELS.md` (comando `python -m training.<nome>`); mover quebraria comandos citados e os
números reproduzíveis. O estado de cada um está em `COMPONENTS.md`.

**D-04 · Documentação: uma fonte por assunto.** Arquitetura oficial em
`VALTEXA-SAAS/docs/ARCHITECTURE.md` (o sistema inteiro). Documentos de processo da nuvem
(auditorias, verificações, progresso, rodadas, briefs, aceite, a "arquitetura alvo da Fase 1")
foram para `docs/historico/`. A documentação do Rover mora no repositório do Rover
(`docs/ROVER_RUNTIME.md`, `docs/SYNC.md`).

**D-05 · Testes da IA começam com uma pasta de modelos vazia.** O `models/` do repositório
tem pesos e calibrações de produção (Git LFS); testes que esperavam "sem calibração"
falhavam conforme a máquina. Um fixture automático (`tests/conftest.py`) isola cada teste.

**D-06 · O recibo assinado das respostas do dispositivo fica, sem consumidor.** Foi criado
contra base adulterada; com a base arquivada ninguém o pede. É um controle de integridade
opcional e sem custo — a missão da consolidação proíbe tirar controle de segurança só para
simplificar.

## Decisões anteriores que continuam valendo (resumo)

| Data | Decisão | Por quê | Onde |
|---|---|---|---|
| set/2026 | Nenhum resultado de IA comanda aplicação; aprovação humana e autorização determinística separadas | 81% de uma doença desconhecida passaria como diagnóstico confiante e errado (medido) | `docs/SAFETY.md`, `README.md`, `tests/test_principio_de_ouro.py` |
| set/2026 | IA, plataforma e Rover separados, só HTTP | Escalar a API sem GPU; prender a versão de Python só onde o Keras exige; o Rover não depende da nuvem | `ARCHITECTURE.md` |
| 01/10 | `ROVER_TTA` desligado por padrão | Melhora o recorte mas piora a planta (fusão calibrada em passada única) | `VALTEXA-B/MODELS.md` |
| 01/10 | Recalibrar conformal sempre com `base_thresholds` | Alargar o conjunto derrubava a detecção por planta (a fusão divide a evidência pelo tamanho do conjunto) | `VALTEXA-B/MODELS.md` |
| 02/10 | Café usa SigLIP 2 + cabeça, não a CNN sozinha | CNN: 6,5% no conjunto externo; cabeça: 80,1% | `VALTEXA-B/MODELS.md` |
| 02/10 | `ROVER_SPECIES_CHECK=false` | A checagem de espécie recusava 49% dos recortes de citros em campo | `VALTEXA-B/MODELS.md` |
| 07/10 | Regra de evidência no Rover, não contagem de recortes | O modelo dá ≥ 0,99 de doença em recortes sadios; a contagem disparava em 33–66% dos quadros sadios | `VALTEXA-ROVER/docs/ROVER_RUNTIME.md` |
| 15–18/10 | Aprendizado contínuo só com portão de não-regressão e aprovador com nome; Rover recusa cabeça sem procedência | Rodadas ingênuas pioravam o café (0,968 → 0,813) | `VALTEXA-B/README.md`, `MODELS.md` |
| 16/10 | `robustez_captura` não vai para produção | A cauda em folhas sadias dobrou e o Rover piorou (FA 103 → 163/900) | `MODELS.md` |
| 18/10 | Motor dNATY desligado | Igual ao NumPy na cabeça do café; o renascimento puro piorou | `MODELS.md` |
| 19/10 | Limiar de novidade da cabeça = 1,2 | Em 1,0 marcava 15/48 folhas legítimas; a novidade pega cena fora do domínio, não erro confiante em folha | `MODELS.md` |
| 19/10 | PINN da dispersão não adotada | Erro de D de −25% a +141%; o ajuste direto do solver erra ≤ 2% | `MODELS.md` |
| 17/10 | Enxame só cria rascunho; sobrevoo do drone não vira missão | Falta a regra de voo de observação (decisão pendente) | `docs/ENXAME.md`, `services/regra_voo_observacao.py` |
| 10/10 | Imagem Esri só em demonstração local | A Esri não licencia processamento em produção | `VALTEXA-B/README.md` |

## Decisões pendentes (precisam do Pedro)

1. Regra de voo de observação do drone (ligar `regra_voo_observacao` no Safety Engine).
2. Licença comercial do dNATY (a cabeça do café foi treinada com ele) — ou retreinar sem.
3. Unificar ou não as duas fusões por planta (D-02), depois do piloto.
4. Apagar ou não as colunas legadas da base (`device.enlace_chave*`, `field.cobertura*`) com
   uma migração nova.
5. Versionar a pasta VALTEXA-BASE em algum repositório (hoje ela não tem git).
