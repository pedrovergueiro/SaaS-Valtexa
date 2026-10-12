# VALTEXA Rover V3 — engenharia mecânica

> ## ⚠ Esta é a versão anterior
>
> O que vale hoje é o **ValTexa Rover V4**, em `../rover-v4`. O V3 fica aqui inteiro e
> intocado, porque é dele que o V4 parte: chassi, suspensão pneumática, gaiola e
> carenagens são os mesmos, sem uma cota alterada.
>
> O que o V4 mudou: a interface de sensores (de chapa furada para o sistema modular
> VMS-60), o mastro (Ø25 → Ø32, porque o Ø25 estava quase em ressonância com o terreno),
> o número de câmeras (8 declaradas → 9 desenhadas) e a provisão de comunicação por
> satélite, que aqui não existia.
>
> Ver `../rover-v4/revisao-h/VTX-RV4-REGISTRO-ALTERACOES-H.md`, seção 0.

**Revisão atual: G** (11/10/2026) · EMITIDO PARA COTAÇÃO E VALIDAÇÃO — **NÃO LIBERADO PARA
FABRICAÇÃO**

> A liberação informada em 11/10/2026 cobria a **Parte A da Rev F**, com o suporte rígido.
> A Rev G retirou aquele grupo e pôs a suspensão pneumática no lugar: **o escopo aprovado
> não cobre mais o que está desenhado.** A liberação precisa ser reemitida sobre a Rev G, e
> faltam para isso o caso 9 do FEA (fadiga) e a escolha do fole. Ver
> `revisao-g/VTX-RV3-LIBERACAO-G.md`, §0.

---

## O que mudou na Revisão G

A suspensão a ar **entrou no conjunto fornecido**. Quatro braços longitudinais
independentes, um fole por canto, sem barra estabilizadora, e a bitola subindo de 470 para
530 mm — que é a cota que paga a rolagem macia e estava sobrando no envelope de 600.

| | Rev F | Rev G |
|---|---|---|
| Suspensão | suporte rígido; balancim a ar como estudo fora do conjunto | **pneumática independente, 4 cantos, no conjunto** |
| Bitola | 470 mm | **530 mm** |
| Tombamento / envelope | 39,44° / 19,57° | **39,92° / 20,89°** |
| Caderno | 27 folhas | **35 folhas** (Parte D: usinagem + montagem) |
| Massa | 110,07 kg @ Z 294,1 | **126,52 kg @ Z 285,9** |
| Manual de montagem | não havia | **folhas 32–35 + documento** |
| Roteiro de usinagem | coluna na BOM | **folhas 28–31 + documento** |
| Conferência de interferência e espaço | não havia | **automática, a cada geração** |

A suspensão macia ficou **mais estável** que a rígida. Não é mágica: 60 mm de bitola valem
mais que 5,4° de rolagem, e a rolagem é limitada pelo fim de curso, não pela mola. O
cálculo inteiro está em `revisao-g/suspensao.py`.

---

## O que há aqui

| Pasta | O que é |
|---|---|
| **`chassi-gaiola/`** | **o CAD.** Modelo paramétrico em Python — dele saem as 35 folhas, os 30 DXF, as listas de corte e as massas |
| **`revisao-g/`** | cálculos e documentos desta revisão, em `.py` e `.md`, com os PDFs em `revisao-g/pdf/` |
| **`pacote-rev-g/`** | gerador do pacote de cotação: documento técnico, BOM, custos, RFQ, fornecedores, pendências |
| `versao-antiga/` | Rev E e Rev F inteiras, congeladas. **Não é mais o que vale** — está aqui porque revisão de engenharia não se apaga |

## Para enviar à empresa que vai fabricar

```
pacote-rev-g/saida/VALTEXA_ROVER_V3_REV_G/
```

Onze pastas numeradas. As que mais importam para quem vai cortar e usinar:

| Pasta | Conteúdo |
|---|---|
| `03_DESENHOS_TECNICOS/SUSPENSAO_USINAGEM/` | folhas 07 e 28 a 31 — as peças de usinagem, com tolerância, referência e acabamento |
| `03_DESENHOS_TECNICOS/MONTAGEM/` | folhas 32 a 35 — onde vai cada peça, sequência, torques e regulagem |
| `04_CAD/DXF/` | 30 arquivos 1:1 para corte a laser. **DXF não carrega tolerância** — ler o `LEIA-ME.txt` da pasta |
| `05_BOM/` | 85 linhas, com material, processo, massa e folha de cada item |
| `11_ENGENHARIA_REV_G/` | os 8 documentos desta revisão, em PDF e em Markdown |

## Para o engenheiro mecânico

| Documento | Assunto |
|---|---|
| `revisao-g/pdf/VTX-RV3-LIBERACAO-G.pdf` | **o que a assinatura assume, e por que o escopo da Rev F não serve** — leia antes de liberar |
| `revisao-g/pdf/VTX-RV3-SUSPENSAO-G.pdf` | a decisão da suspensão: geometria, fole, rolagem, tensões, massa |
| `revisao-g/pdf/VTX-RV3-AUDITORIA-G.pdf` | o que estava errado na Rev E e na **própria Rev F** (seção 0.0) |
| `revisao-g/pdf/VTX-RV3-ESPACO-G.pdf` | o espaço interno medido e a conferência de interferência |
| `revisao-g/pdf/VTX-RV3-REGISTRO-ALTERACOES-G.pdf` | histórico, situação item a item, pendências |

## Para a oficina

| Documento | Assunto |
|---|---|
| `revisao-g/pdf/VTX-RV3-USINAGEM-G.pdf` | roteiro de operações peça por peça, com ajustes e folgas |
| `revisao-g/pdf/VTX-RV3-MONTAGEM-G.pdf` | posição de cada peça, sequência, torques, aceite |

---

## Regenerar tudo

```
cd chassi-gaiola && python gerar.py          # 35 folhas: HTML + 30 DXF + 5 PDFs
cd revisao-g     && python relatorios.py     # os 3 documentos gerados do modelo
cd revisao-g     && python gerar_docs.py     # PDF de todos os documentos
cd pacote-rev-g  && python gerar_pacote.py   # pacote de cotação completo
```

Os cálculos rodam sozinhos e imprimem o resultado:

```
cd revisao-g
python suspensao.py     # suspensão: geometria, fole, rolagem, tensões, massa, folgas
python espaco.py        # espaço interno medido e interferência entre peças
python montagem.py      # mapa de posições, sequência, torques  (--item W-01)
python usinagem.py      # roteiro de usinagem                   (--item W-02)
python dimensional.py   # levantamento dimensional e 7 CSVs
python materiais.py     # alumínio × aço × híbrida (sugestão 2.1)
python sugestoes.py     # fixações, planicidade, chapa em aço (2.2, 2.3, 2.4)
python sensores.py      # Vision / Hydro / Spectral / Research
python liberacao.py     # prontidão para fabricação, grupo a grupo
```

## Onde mudar o quê

- **cota, material ou geometria** → `chassi-gaiola/modelo.py`. Tudo o mais é derivado
- **composição das folhas** → `folhas.py` (01–16), `folhas_b.py` (17–27), `folhas_w.py` (28–35)
- **sequência de montagem, torques, aceite** → `revisao-g/montagem.py`
- **tolerância e roteiro de usinagem** → `revisao-g/usinagem.py`
- **liberar para fabricação** → `LIBERACAO` em `chassi-gaiola/folhas.py`. Enquanto for
  `None`, as 35 folhas saem como não liberadas; incompleta, levanta erro

## Estado em uma linha

126,52 kg contra os 97,8 declarados na baseline — a massa é a pendência nº 1 e não é da
suspensão, é anterior a ela. Nenhum dos 9 casos de FEA foi rodado, e o caso 9 (fadiga do
braço) é o que decide se o grupo W fica em aço. Nenhum fole comercial foi escolhido.
**Este pacote é para cotar, não para fabricar.**
