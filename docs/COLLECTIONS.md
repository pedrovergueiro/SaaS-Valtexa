# Coletas: como uma imagem entra na plataforma

O caminho de entrada do MVP. O voo é de um operador terceirizado, os arquivos
chegam pela mão de alguém, e quem os registra é a equipe da ValTexa pelo painel
administrativo.

A ValTexa **não controla drone** nesta fase. Não há planejamento de voo, não há
navegação, não há transmissão automática — e não há tela fingindo que há.

```
CLIENTE                      contrata
   │
OPERADOR TERCEIRIZADO        voa, manual
   │   entrega os arquivos
   ▼
PAINEL ADMIN VALTEXA         Importar Coleta
   │   cliente · propriedade · talhão · data · origem · tipo
   ▼
UPLOAD EM PEDAÇOS            retomável, sem teto artificial
   │
   ▼
FILA (processing_job)        o administrador pode fechar a aba
   │
   ▼
WORKER                       lotes de 25 arquivos
   │
   ├── há modelo treinado ──► VALTEXA-B ──► diagnóstico ──► fila do agrônomo quando não fecha
   │
   └── não há ─────────────► NO_MODEL: guardado, catalogado, direto para o agrônomo
   │
   ▼
AGRÔNOMO                     rotula; o rótulo pode ser inédito
   │
   ├──► dataset proprietário (amostra CANDIDATE)
   │
   ▼
PUBLICAÇÃO                   alguém da ValTexa decide que está pronto
   │
   ▼
CLIENTE                      vê data, talhão, imagens e o que se concluiu
```

---

## Estados

| Estado | Significa |
|---|---|
| `draft` | criada no painel, sem arquivo |
| `uploading` | recebendo bytes |
| `upload_completed` | recebimento encerrado |
| `processing_queued` | trabalho na fila |
| `ai_processing` | worker processando |
| `review_required` | há arquivo esperando o agrônomo |
| `analyzed` | tudo resolvido, automático ou por gente |
| `available_to_client` | publicada |
| `failed` | nenhum arquivo chegou inteiro |

Por arquivo: `registered → uploading → stored → processing → analyzed`, com
saídas em `needs_review`, `no_model`, `failed` e `rejected`.

---

## Upload: por que em pedaços

Uma coleta aérea de um talhão são centenas de arquivos e dezenas de gigabytes.
Numa requisição só isso falha por tempo limite, por memória no servidor e por
qualquer oscilação da internet da fazenda — e falha depois de horas, do começo.

O protocolo tem três passos e nenhum estado escondido:

```
POST /v1/admin/collections/{id}/files
     { "files": [{ "filename": "...", "size_bytes": 12345678, "sha256": "..." }] }
  → declara o que virá. O total passa a ser conhecido: a barra não mente.

PUT  /v1/admin/collections/{id}/files/{file_id}/chunk?offset=N
     corpo: bytes crus
  → 200 com received_bytes
  → 409 com o cabeçalho X-Received-Bytes quando o deslocamento não bate

POST /v1/admin/collections/{id}/complete
  → fecha o recebimento e enfileira
```

**O pedaço só é aceito onde o arquivo parou.** Reenviar o mesmo pedaço é seguro
— a rede cai justamente entre o servidor gravar e o cliente receber a
confirmação. Qualquer outro deslocamento é recusado com 409, e o cabeçalho diz
de onde continuar. Isso dispensa tabela de partes e torna impossível um arquivo
"completo" com um buraco no meio.

**Não há limite de tamanho de coleta.** O único teto é `MAX_CHUNK_BYTES`
(32 MB), que limita **um pedaço**, para segurar a memória de uma requisição. Um
arquivo de 8 GB sobe em pedaços de 4 MB sem encostar nele. O teto real é o do
armazenamento contratado.

**`MAX_ASSET_MB` vale para o arquivo já montado.** O padrão é 64 MB; ortomosaico
passa disso com folga. Suba antes de importar um.

### O que quebra com várias réplicas

Os pedaços se acumulam em disco, em `UPLOAD_STAGING_DIR` (padrão
`STORAGE_DIR/_upload`). É o **único** estado do upload que não vive no banco nem
no bucket. Com mais de uma réplica da API e sem volume compartilhado, um arquivo
que troque de réplica no meio do envio responde 409 para sempre e nunca fecha.

Duas saídas: um volume compartilhado, ou uma réplica só atendendo a rota de
upload. Com `STORAGE_BACKEND=s3` e `UPLOAD_STAGING_DIR` vazio, `/health` acusa
a pendência.

---

## Qual modelo analisa a coleta

Resolvido **na criação**, não na fila. Quem está subindo 1.500 fotos descobre no
formulário que nenhum modelo treinado as analisa — não meia hora depois.

A escolha é por **cultura + plataforma de captura**, e a plataforma vem do tipo
declarado:

| Tipo declarado | Plataforma |
|---|---|
| Imagem aérea, ortomosaico | `aerial` |
| Imagem de solo | `ground` |

O catálogo que a plataforma conhece espelha `VALTEXA-B/app/registry.py`
(`GET /v1/admin/models/catalog`):

| Modelo | Culturas | Captura | Treinado |
|---|---|---|---|
| `leaf-foliar` | milho | solo | sim |
| `coffee-foliar` | café | solo | sim |
| `rover-understory` | milho | solo | **não** — em quarentena |
| `aerial-canopy` | milho | aérea | **não** — precisa de coleta |

**Hoje nenhuma imagem aérea tem modelo.** A coleta nasce com `model_key = null` e
um `no_model_reason` por extenso, que vai inteiro para o painel e para a tela do
cliente.

E há dois graus de "não tem":

* **milho aéreo** tem modelo no catálogo, sem pesos — a recusa cita
  `aerial-canopy` e diz que ele precisa de coleta. É o conjunto que o upload
  administrativo vai encher;
* **café aéreo** não tem nem isso. `aerial-canopy` é de milho, e a recusa lista o
  que de fato está treinado em vez de apontar um vizinho que não serve. A
  lavoura da demonstração é café: é este o caso que se vê rodando.

### Por que não mandar a foto aérea para o modelo de folha

Porque a resposta viria com confiança alta e estaria errada, sem nada no
resultado denunciando. Podridão de colmo e sintoma radicular são **fisicamente
invisíveis** numa foto de dossel; uma planta ocupa poucos pixels. O modelo de
café responderia uma das cinco classes de folha de café sobre uma imagem onde
nenhuma delas pode ser vista. É o modo de falha medido em `VALTEXA-B/MODELS.md`:
diante de uma doença fora do catálogo, o modelo respondeu com **0,88 de
confiança média** e os filtros interceptaram 19%.

O que a plataforma faz em vez disso: guarda, cataloga, georreferencia e manda
para o agrônomo, com o motivo escrito. `CollectionFileState.NO_MODEL` não é erro
nem pendência de código — é o estado honesto de uma imagem que nenhum modelo
treinado sabe responder.

**E é assim que o `aerial-canopy` deixa de precisar de coleta.** Cada rótulo que
um agrônomo escreve sobre uma dessas imagens vira amostra do dataset aéreo. O
caminho do upload administrativo *é* o caminho de formação do dataset do modelo
que ainda não existe.

---

## Dataset proprietário

```
revisão do agrônomo
      │
      ▼
DatasetSample (CANDIDATE)      rótulo, quem, quando, o que a máquina dizia
      │   acumula
      ▼
DatasetVersion                 corte congelado: a lista exata de amostras
      │
      ▼
treino no VALTEXA-B            fora desta plataforma
      │
      ▼
ModelVersion                   aponta de volta para o corte que a treinou
```

**Não se treina a cada correção.** Uma anotação entra no conjunto; o treino roda
sobre um corte fechado por alguém, com data e contagem por rótulo. É o mesmo
princípio que impede um diagnóstico isolado de virar aplicação.

**O corte guarda a lista, não um filtro.** Amostras podem ser excluídas depois;
um corte definido por consulta mudaria de conteúdo com o tempo e dois treinos
com o mesmo nome deixariam de ser comparáveis.

**O rótulo é livre.** Restringir ao catálogo do classificador fecharia o único
caminho pelo qual uma doença nova entra no dataset.

O conjunto é escolhido por cultura + plataforma: `coffee-foliar` quando existe
modelo, `corn-aerial` quando não existe. O `tenant_id` viaja na amostra para
rastreabilidade e para atender pedido de exclusão — mas não separa conjuntos: a
soma dos clientes é o que dá volume.

---

## Quem pode o quê

| | Cliente | Equipe ValTexa |
|---|---|---|
| Ver coletas publicadas | sim | sim |
| Ver coleta em upload/fila | **não** (404) | sim |
| Criar coleta, subir arquivo | não (403) | sim |
| Publicar para o cliente | não | sim |
| Dataset e cortes | agrônomo lê | sim |
| Fila de processamento | não | sim |

A fronteira **não vem de papel**. Nenhum `OWNER`, por mais dono que seja da
fazenda, importa coleta. Quem pode é `User.is_platform_admin`, e a checagem é
`require_platform_admin` — ver `valtexa/api/deps.py`. O tenant ativo continua
valendo e continua sendo filtrado: a equipe da ValTexa trabalha *dentro* de um
cliente por vez, e a auditoria registra em nome de quem e sobre quem.

Uma coleta não publicada responde **404** ao cliente, não 403: confirmar que ela
existe já contaria que há trabalho em curso sobre o talhão dele antes de a
ValTexa ter o que dizer.

---

## Fase futura

`CollectionSource.DRONE_OWNED` existe no vocabulário e **é recusado na criação**
(422). Aceitá-lo hoje registraria no banco que um drone da ValTexa voou — não
voou.

`POST /v1/admin/drone-missions` responde **501** com o caminho implementado no
corpo. A rota existe para a integração futura ter um lugar combinado e para quem
procurar por ela hoje receber uma recusa, em vez de encontrar uma tela que finge
funcionar.

Nada de pulverização aérea, tanque, bico ou vazão entrou nesta fase.
