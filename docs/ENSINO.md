# O agrônomo ensinando a IA

> 26/10/2026. A ideia: o agrônomo deixa a IA especialista passando a ela o que sabe. Cada
> diagnóstico dele é uma **lição** — o quê, por quê e onde — que volta como treino, como
> evidência nos pareceres e como medida do quanto a IA aprendeu.

## O caminho de uma lição

```
Fila do agrônomo (ou discordância num parecer)
   │  rótulo + por quê (sintomas, terço, face, texto) + lesões marcadas na foto
   ▼
licao_agronomo ───────────────┬──────────────────────────┬─────────────────────────────┐
   │                          │                          │                             │
   ▼                          ▼                          ▼                             ▼
amostra do dataset      próximos pareceres do      painel "o que a IA          (LGPD: apagável
(com consentimento)     talhão citam a lição,      aprendeu com você"           pelo id)
   │                    com o nome e a data
   ▼
corte congelado → zip (imagens + manifesto com lesões e porquê)
   │
   ▼  VALTEXA-B: training.import_licoes
<Classe>/foto inteira + um recorte por lesão; campo.csv (grupo = planta)
   │
   ▼  training.adapt_campo adapta → portão de regressão → promove (aprovador) → pronto
cabeça nova no Rover (manifesto conferido, procedência)
```

## Onde cada parte vive

| Parte | Onde |
|---|---|
| A lição | `valtexa/models/ensino.py` (`licao_agronomo`, migração 0037), `valtexa/services/ensino.py` |
| Na fila | `POST /v1/diagnoses/{id}/review` com `explicacao` e `lesoes`; tela da fila: painel "Por quê?" e a foto onde se arrasta para marcar a lesão (`components/MarcadorDeLesoes.tsx`) |
| No parecer | `POST /v1/pareceres/{id}/revisao` discordando com `diagnostico_revisor` (vira lição); com `registrar_diagnostico`, vale como o veredito da fila naquela observação |
| Nos pareceres seguintes | item `licoes` do dossiê (`cerebro/dossie.py`), seção "O que o agrônomo ensinou" do parecer |
| O painel | `GET /v1/ensino/painel?de=mim\|todos`, página `/ensino` ("O que a IA aprendeu") |
| Vocabulário | `GET /v1/ensino/vocabulario?rotulo=` — sugestão de sintomas por classe; ele escreve o que viu |
| Exportação | `GET /v1/admin/datasets/{id}/versions/{versão}/export` (equipe; auditado) |
| Na IA | `python -m training.import_licoes --zip corte.zip --out data/coffee-licoes --classes ...` |

## Regras que protegem a IA do ensino

- **Ensinar não treina sozinho.** A lição vira amostra; o treino roda sobre um corte congelado,
  com o portão de regressão (a IA não pode esquecer o que sabia) e a aprovação nominal.
- **Consentimento.** Só amostra de cliente que autorizou o uso em treino entra no corte (conferido
  ao revisar e ao congelar). A lição continua valendo para os pareceres do próprio cliente.
- **O texto dele é dado, não instrução.** No parecer, o porquê entra atribuído ao autor e com a
  data; texto com cara de ordem, dose ou certeza é omitido, e número dentro do texto dele fica
  no dossiê (é afirmação dele, não evidência medida).
- **Classe nova não entra pelo ciclo contínuo.** O `import_licoes` põe em `_novas/<classe>/` e o
  painel mostra quantos exemplos já há (alvo: 30 por classe); a classe nova entra num treino da
  cabeça (`training.fit_heads`), com teste separado por planta.
- **Imutável.** Corrigir é ensinar de novo; a anterior fica, com autor e data.

## O que o painel mede

Lições, quantas com o porquê, lesões marcadas, onde a IA mais erra com ele (o par "a IA dizia →
você disse"), o acerto da IA mês a mês nos casos dele e as classes novas com o quanto falta.
**Viés:** os casos da fila são os que a IA não fechou sozinha — o acerto ali é pior que o da
lavoura; vale como tendência.

## Consenso antes do treino (27/10)

Cada lição pode receber uma **segunda opinião** — de outro agrônomo do cliente (aba "Segunda
opinião" da página do ensino, `GET/POST /v1/ensino/segunda-opiniao`) ou do agrônomo da equipe
ValTexa (`/v1/admin/datasets/{id}/segunda-opiniao`). Quem rotulou não opina na própria lição.
Ao congelar o corte, a equipe escolhe a política (`politica` em `POST /admin/datasets/{id}/versions`):

| Política | O que entra |
|---|---|
| `consenso` (padrão no console) | só o que uma segunda opinião confirmou |
| `confiabilidade` | confirmado, ou de agrônomo que concorda com os colegas ≥ 80% em ≥ 10 pares |
| `um` | o rótulo de um agrônomo basta (a regra antiga) |

Amostra **em disputa** (alguém discordou) nunca entra, em nenhuma política; a que fica fora continua
candidata. O corte guarda o `criterio` (a política e quantas ficaram fora, por motivo). A
**confiabilidade** de cada agrônomo — (concordâncias + 1) / (pares + 2) — aparece só para ele (no
painel) e para a equipe; não é mostrada ao cliente (ver o Termo, cláusula 7.2).

## Regras do agrônomo (27/10)

Aba "Regras": ele escreve o que sabe ("bicho-mineiro sobe na seca") e a condição que dá para medir —
`chuva_mm`, `molhamento_h`, `ur_media` ou `t_media` numa janela de dias, ou os meses do ano — e se
ela aumenta ou diminui a doença (`/v1/ensino/regras`). **Medir no histórico**
(`POST /v1/ensino/regras/{id}/medir`) compara a taxa da doença com e sem a condição nas observações
de diagnóstico confiável do cliente (teste de duas proporções; 20 casos de cada lado e 5 com a
doença, no mínimo): `sustentada`, `contrariada`, `nao_mostrada` ou `poucos_dados`. O clima vem da
série do talhão na IA. O parecer cita a regra **sempre com o veredito** (seção "Regras dos
agrônomos"); desligada, sai dos pareceres.

## O termo de contribuição

Minuta em Word: `Termo_Contribuicao_Conhecimento_Agronomico_ValTexa.docx` (ValTexa, cliente e
agrônomo). Titularidade (dados do cliente ficam do cliente; conhecimento e autoria ficam do
agrônomo; modelos são da ValTexa), licença de uso das lições, atribuição do nome, LGPD, revogação
(com o limite técnico de "desaprender" um modelo já treinado), consenso e responsabilidades.
**Precisa de revisão de advogado antes de assinar.**

## Ainda não feito

- Pseudônimo automático nos pareceres (cláusula 6.2 do termo): hoje é feito pela equipe, à mão.
- Retreinar os modelos sem os dados revogados é do ciclo de treino (cláusula 8.3), não automático.
