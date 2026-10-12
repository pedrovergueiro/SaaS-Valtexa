# Simulador

Uma temporada inteira em dois minutos, sem hardware nenhum.

```bash
python -m simulator
```

Sobe a plataforma num processo próprio, cria a fazenda de demonstração, provisiona
três robôs e roda o fluxo completo. Não precisa de servidor no ar, nem de banco
configurado, nem de GPU.

```bash
python -m simulator --url http://homolog.valtexa.local   # ambiente já no ar
python -m simulator --keep                               # não apaga o banco ao terminar
```

---

## Por que ele existe

Três razões, em ordem de importância:

1. **Provar a arquitetura antes do hardware.** Se o fluxo ponta a ponta não roda
   contra robôs simulados, ele não vai rodar contra robôs de verdade — só que
   descobrir isso com hardware custa meses.
2. **Ser a referência executável do protocolo.**
   [`simulator/client.py`](../simulator/client.py) é o cliente de verdade, não
   uma imitação. Quem escrever o firmware reproduz o que está ali.
3. **Provar que não existe rota privada de frontend.**
   [`simulator/operator.py`](../simulator/operator.py) faz, por HTTP, tudo que
   uma tela faria.

---

## O que o roteiro percorre

```
1. Provisionamento     três robôs geram o próprio par de chaves
                       convite reutilizado é RECUSADO

2. Varredura           missão planejada, aprovada pela segurança, assinada
                       rover verifica a assinatura antes de aceitar

3. Recarga e retomada  bateria acaba no meio -> volta -> recarrega
                       retoma SÓ com os segmentos que faltam
                       perde o enlace -> acumula -> sincroniza
                       reenvia o mesmo lote -> nada duplica

4. Diagnóstico         imagens viram diagnósticos
                       novidade separa material para o agrônomo
                       agrônomo rotula uma classe FORA do catálogo

5. Cópia 3D           o rover percorre TODAS as ruas da zona, na faixa do LiDAR
                       cada rua vira passada: plantas medidas + nuvem PLY
                       fotografa mais onde o sensor vê sintoma
                       lagarta-do-cartucho: o modelo não conhece -> fila
                       o agrônomo rotula a praga -> ela aparece na cópia

6. Pulverização        BLOQUEADA sem aprovação do agrônomo
                       operador tenta aprovar -> 403
                       BLOQUEADA com o tanque errado
                       agrônomo aprova, tanque correto -> liberada

7. Aplicação           cerca virtual bloqueia pontos fora do polígono
                       teto de volume respeitado como teto

8. Gêmeo digital       retrato do talhão, verificação agendada, auditoria
```

A lavoura do roteiro está em [`simulator/plants.py`](../simulator/plants.py):
**cafezal formado** (ruas a 3,5 m, uma planta a cada 0,7 m, porte de 2,2 m,
falhas de plantio) com duas reboleiras — ferrugem, que o `coffee-foliar`
reconhece, e bicho-mineiro, que sai do modelo como mancha foliar qualquer. As
plantas dentro de uma reboleira ficam mais baixas e menos verdes, e a nuvem de
pontos carrega a lesão ou a folha minada. Duas passadas pela mesma rua enxergam
as mesmas plantas.

O contorno do talhão é o de uma propriedade real de 5 alqueires mineiros
(24,2 ha), traçado sobre foto aérea: polígono irregular, com a mata entrando
pelo leste. Não é retângulo de propósito — foi um talhão côncavo que revelou um
defeito no geofence que um retângulo escondia (ver `tests/test_safety.py`,
`TestTalhaoConcavo`).

**Os bloqueios são o ponto.** Um simulador que só mostra o caminho feliz não
prova nada: o valor da plataforma está exatamente no que ela recusa fazer.

---

## Como está montado

| Arquivo | O que é |
|---|---|
| `simulator/client.py` | cliente assinado do protocolo — o SDK do firmware |
| `simulator/operator.py` | cliente do lado humano |
| `simulator/devices.py` | rover, drone e dock simulados |
| `simulator/plants.py` | a lavoura que o sensor 3D do rover enxerga |
| `simulator/leaf.py` | as folhas das fotos, com lesão ou dano de praga |
| `simulator/scenario.py` | o roteiro |
| `simulator/pomar.py` | bananal e pomar, com a IA simulada ou a do VALTEXA-B |
| `simulator/__main__.py` | sobe a plataforma e executa |

### O que os dispositivos simulados reproduzem

Não é animação: são as decisões que o firmware precisa tomar **sozinho**.

- o rover mede a própria energia e decide voltar **sem perguntar à nuvem**;
- o drone verifica a assinatura e a cerca virtual antes de abrir o bico, e fecha
  por conta própria se a trilha sair da área;
- a dock informa o vento — sem ele, a pulverização é bloqueada.

Quando o hardware existir, ele substitui `simulator/devices.py`. A nuvem não
muda.

---

## `SIMULATED_INFERENCE`

O simulador liga essa opção, que substitui os modelos por analisadores falsos e
determinísticos.

O truque: o rover monta imagens PNG válidas com uma marca anexada ao fim do
arquivo (`VTXSIM:<rótulo>:<novidade>`). PNG ignora bytes depois do bloco `IEND`,
então a etiqueta viaja junto sem corromper o arquivo, e o `SimulatedAnalyzer` a
lê para saber o que responder. A confiança vem do hash da imagem — mesma imagem,
mesma resposta, como num modelo de verdade. A severidade também: zero em folha
sadia, entre 3% e 35% nas demais, e a mesma para os dois analisadores, porque é
medida da imagem, não opinião sobre ela.

A imagem em si é uma folha desenhada por
[`simulator/leaf.py`](../simulator/leaf.py), com o sinal típico do rótulo —
pústulas alaranjadas de ferrugem, manchas de centro claro e halo amarelado da
cercosporiose, lesões escuras de Phoma, galerias irregulares do bicho-mineiro —
e clorose entre as nervuras quando a novidade é alta. Existe para quem abre a
fila do agrônomo no console: é ilustração, não dado de treino.

É andaime de simulação e está **recusado em produção** por
`Settings.production_problems()`: um diagnóstico inventado chegando a um produtor
seria pior do que não ter diagnóstico nenhum.

Para rodar contra os modelos reais, suba o `VALTEXA-B` e use
`--url` apontando para uma plataforma com `INFERENCE_ENABLED=true`.

---

## Vendo o resultado no console

```bash
python -m simulator --keep                 # deixa o banco em .simulacao/
cd web && npm install && npm run build && cd ..
DATABASE_URL=sqlite:///.simulacao/simulacao.db STORAGE_DIR=.simulacao/storage \
  SIMULATED_INFERENCE=true INFERENCE_ENABLED=false uvicorn valtexa.main:app
```

Abra <http://127.0.0.1:8000> e entre com uma das contas abaixo. O banco guarda o
que o roteiro produziu: a cópia 3D da zona em *Lavoura 3D*, com as duas
reboleiras; a fila do agrônomo; a aplicação com a trilha; a verificação
agendada; a auditoria.

`--keep` também não limpa ao começar. Para rodar de novo do zero, apague
`.simulacao/` antes.

---

## Bananal e pomar, com a IA de verdade

```bash
python -m simulator.pomar                      # IA simulada
python -m simulator.pomar --ia http://127.0.0.1:8001 --fotos <pasta> --manter
```

O rover entre bananeiras (3 ruas × 6 plantas, espaçamento de 2,5 m) e
laranjeiras (3 × 5, 4 m), com as câmeras laterais nos andares do mastro do
Rover V3 (450, 1000 e 1540 mm; na bananeira só as duas de cima, que veem folha).
Duas passadas com uma semana entre elas: na primeira, uma reboleira de cinco
plantas; na segunda ela cresceu para doze, e no canto oposto aparece uma planta
com outra doença (Fusariose no bananal, Greening no pomar). Cada passada é uma
missão de varredura de verdade — autorizada, assinada, concluída —, e concluí-la
fecha a passada na fusão por planta.

**IA simulada:** exercita o fluxo e o console (sinais do quadro, fila por
valor, seletor de versão). Plantas e prevalência respondem 503: quem as calcula
é o serviço de inferência.

**IA de verdade:** o VALTEXA-B no ar com `FIELDS_DIR`, e fotos reais em
`<pasta>/<cultura>/<Classe>/`, montadas por `python -m training.demo_photos`
no VALTEXA-B — a doença vem do teste de campo (recortes do PlantSeg que o
modelo nunca viu), a folha sadia do dataset de treino. Com `--manter`, a
plataforma fica no ar para abrir o console.

Rodada de 28/09/2026, inferência em CPU (~2 s por quadro):

| | Quadros | Situação da planta certa | Doença certa nas doentes |
|---|---|---|---|
| Pomar (`citrus-foliar`) | 90 | 15 de 15 | 12 de 12 |
| Bananal (`banana-foliar`) | 72 | 12 de 18 | 9 de 12 |

**Não é medida** — são 33 plantas, e a folha sadia o modelo já viu; a medida
está no MODELS.md do VALTEXA-B. O que a rodada mostra é o caminho inteiro
funcionando, e dois comportamentos que valem ver no console:

- no bananal, o erro é a confusão Cordana↔Sigatoka já conhecida — e a
  prevalência estimada a denuncia sozinha: Cordana em 27% no talhão contra 2% no
  treino;
- no pomar, a planta que a reboleira alcançou na segunda passada sai como
  `nova_infeccao` na evolução.

A distância declarada nos quadros com foto real é 51 mm, para o corte de 150 mm
pegar três quartos da foto (ver `DISTANCIA_FOTO_REAL_MM` em
`simulator/pomar.py`): a 75 mm, cortando meia foto, os quadros acertavam 71% no
bananal e 67% no pomar, contra 83% e 100% a 51 mm.

---

## Ponta a ponta do café com pesos reais

O roteiro dos 31 critérios (`--rover-runtime`) roda também com os componentes de
verdade no lugar dos dublês:

```bash
python -m simulator --rover-runtime --ia http://127.0.0.1:8001 \
    --modelo-real <modelos>/coffee_foliar.onnx --folhas <pasta>/
```

- **Edge AI:** o `.onnx` com os arquivos ao lado (perfil, cabeça e torre do SigLIP 2)
  é instalado no formato do OTA, publicado no registry pelo SHA-256 e carregado pelo
  Rover Runtime (`valtexa_rover.sim.folhas.instalar_modelo`).
- **Imagem:** cada quadro é uma foto de folha de `<pasta>/<Classe>/`
  (`Healthy`, `Rust`, `Leaf_Miner_Damage`), sorteada pela condição da planta.
  Use fotos que o modelo não viu (o BRACOL separado). Planta doente mostra folha
  doente com 50% de chance (`valtexa_rover.sim.folhas.CameraDeFolhas`).
- **IA de nuvem:** o VALTEXA-B no ar com `FIELDS_DIR`. Com um analisador só não há par
  independente: nada vira "doente" sem o agrônomo. O roteiro marca a revisão
  como simulada e conta como achada a planta que o Rover pôs em doente, suspeita
  ou revisar.
- **Passos extras:**
  - 21b: os recortes de todo quadro na fusão calibrada do `ia/`;
  - 22b: a incidência corrigida;
  - 23b: a prescrição planta a planta.

**Execução de 10/10/2026** (café, CPU, ~7 min): **31 de 31 + 21b, 22b e 23b**.

| Passo | Resultado |
|---|---|
| Classificação no Rover | 140 quadros: 109 normais, 27 possível doença, 4 possível praga |
| Envio | 31 originais subiram; 109 só reduzidos |
| IA de nuvem | 12 eventos analisados (7 sadios, 3 ferrugem, 1 bicho-mineiro, 1 phoma) |
| Plantas | as 4 doentes achadas; 16 de 44 sadias com alarme |
| Fusão calibrada | 98 quadros fundidos e 42 duplicados recusados; incidência corrigida 31,7% (IC95 13,5–47,0%) contra 7,4% de verdade |
| Prescrição planta a planta | tratar 40 de 72 plantas; 80% do ganho de pulverizar tudo por 56% do custo |

**Os números não são medida de acurácia.**
- **Quadro:** aqui um quadro é uma folha; no campo são ~70 recortes, e o perfil foi
  calibrado para isso. Por isso o alarme por planta sobe.
- **Posição:** o robô simulado anda em cima da linha de plantas, e a fusão pelo GNSS
  supõe o meio da rua. As duas câmeras caem em linhas vizinhas e as plantas viram 72.

A conexão de ponta a ponta está provada; a acurácia só a coleta de campo mede.

**Achado deste modo:** um quadro montado com várias fotos põe a emenda entre elas
dentro de cada recorte (o perfil sobrepõe 25%), e a IA lê a emenda como lesão.
- Folhas sadias soltas: P(sadia) entre 0,95 e 0,96.
- As mesmas montadas em 4 × 3: P(sadia) entre 0,06 e 0,95.

Por isso a câmera monta um recorte por quadro.

---

## O mesmo fluxo, em CI

[`tests/test_end_to_end.py`](../tests/test_end_to_end.py) percorre a mesma cadeia
pelo `TestClient`, sem servidor, em segundos. É a versão que roda em cada commit;
o `python -m simulator` é a versão que se mostra para uma pessoa.

---

## Credenciais da demonstração

| E-mail | Papel |
|---|---|
| `admin@valtexa.dev` | admin |
| `agronomo@valtexa.dev` | agrônomo |
| `operador@valtexa.dev` | operador |
| `equipe@valtexa.dev` | **equipe ValTexa** — é a única conta que abre o painel administrativo e importa coleta |

Senha: `valtexa-demo-2026`. Cliente `fazenda-demo`, Sítio Boa Vista: um talhão
de café de 24,2 ha no Sul de Minas. O contorno vem de foto aérea real; a âncora
das coordenadas é aproximada e põe o desenho em região de café, para o mapa de
satélite do console mostrar cafezal. Mover para a propriedade exata é trocar
duas constantes em `valtexa/seed.py`.

São dados de demonstração e **não devem existir em produção**. `seed_demo()` só é
chamado pelo simulador e pelos testes.

---

## O que o simulador ainda não faz

- vento e chuva variando ao longo da missão;
- falha de hardware no meio da execução (motor, sensor, câmera);
- dois robôs operando ao mesmo tempo no mesmo talhão;
- a coreografia física de acoplamento e troca de bateria na dock;
- deriva de posição — o rover simulado navega perfeitamente, o que é justamente
  o que a margem da cerca virtual existe para cobrir no mundo real;
- medir de verdade: as plantas da cópia 3D vêm de uma grade com ruído, e a nuvem
  de pontos é desenhada, não medida por LiDAR nenhum. Serve para exercitar o
  protocolo e o console, não para avaliar sensor.
