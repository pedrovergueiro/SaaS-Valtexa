# dNATY — etapa de otimização do Model Registry (brief, seção 23)

```
MODELO TREINADO → VALIDAÇÃO → BENCHMARK → dNATY → MODELO OTIMIZADO → NOVO BENCHMARK →
VALIDAÇÃO → APROVAÇÃO → PUBLICAÇÃO → ROVER
```

> **Licença.** O pacote `dnaty` (PyPI, 2.2.1) é **BSL 1.1**: uso não comercial liberado;
> **uso comercial pede licença própria do autor**. Antes de publicar para cliente pagante um
> modelo otimizado pelo dNATY, a ValTexa precisa dessa licença. A nota vai gravada em cada
> rodada feita com ele (`model_optimization.license_note`).

## Quem faz o quê

| Passo | Onde | O que faz |
| --- | --- | --- |
| benchmark do original, otimização, benchmark do otimizado | `ia/training/dnaty_pipeline.py` (AI Platform) | mede os dois `.onnx` pelo **ONNX Runtime** (o mesmo do robô), no mesmo conjunto de validação: precisão, recall, F1 (macro), recall por classe, acurácia, latência p50/p95 (uma amostra por vez), FPS, memória residente, tamanho, FLOPs (2·MACs de MatMul/Gemm/Conv, pelo grafo); `map` fica nulo (os modelos de hoje são de classificação) |
| veredito | `saas/valtexa/services/dnaty.py` | **recalcula** com o critério de aceite (o "aceito" do relatório é ignorado) e grava a rodada |
| registro | `POST /v1/platform/models/{id}/optimizations` (IA & Dados / superadmin), `GET` idem | toda rodada fica em `model_optimization` (migração 0019), aceita ou não, com os dois benchmarks, o critério, a comparação e os motivos |
| aprovação | `services/model_registry.transicionar` | versão com artefato otimizado **só é aprovada** se houver rodada aceita daquele SHA-256 |
| robô | `GET /v1/device/models` | recebe o otimizado (com `dnaty_version`) quando existe; senão o original |

O original **nunca** é substituído: `original_artifact_*` e `optimized_artifact_*` ficam
separados na versão; o pipeline aborta se o otimizador mexer no arquivo original.

## Critério de aceite (configurável por rodada)

| Campo | Padrão | Significado |
| --- | --- | --- |
| `max_queda_f1` | 0,01 | F1 macro pode cair até 1 p.p. |
| `max_queda_precisao` / `max_queda_recall` | 0,02 | idem, precisão e recall médios |
| `max_queda_recall_por_classe` | 0,03 | **nenhuma doença** pode perder mais que isso de recall |
| `latencia_max_relativa` | 1,10 | não pode ficar mais de 10 % mais lento |
| `ganho_minimo` | 0,10 | precisa ganhar ≥ 10 % em ao menos uma métrica de eficiência |
| `ganhos_validos` | latência p50, memória, tamanho, FLOPs | de onde o ganho pode vir |

**Não aceita só porque ficou menor**: um otimizado menor que perde uma classe é recusado
pelo recall por classe; um menor e mais lento, pela latência; um igual ao original, por
falta de ganho. `ganho_minimo` ≤ 0 é recusado (409).

## Otimizadores

- `DnatyOtimizador` — `dnaty.compress` sobre o `torch.nn.Module` treinado + dados de
  treino, exporta ONNX. **Roda aqui de verdade** (teste `test_dnaty_de_verdade_*`, busca
  curtíssima). Instalação: `pip install --no-deps dnaty==2.2.1 scipy tqdm` (as
  dependências declaradas puxam o torchvision; ver `ia/requirements-training.txt`).
  Observação medida: numa busca curta (2 gerações, população 4) sobre um MLP pequeno o
  dNATY devolveu a mesma arquitetura (FLOPs −0 %) — exatamente o caso que o critério
  recusa por falta de ganho.
- `QuantizacaoDinamicaOnnx` — INT8 dinâmico do ONNX Runtime, para modelo que só existe em
  ONNX. **Não é dNATY**: grava `dnaty_version` nulo.

## Uso

```bash
cd ia
python -m training.dnaty_pipeline --original models/leaf.onnx --validacao val.npz \
    --otimizador quantizacao --saida relatorio.json
# relatorio.json → acrescentar original.artifact_uri e otimizado.artifact_uri → POST no registry
```

## O que falta (honesto)

- **Sem pesos reais aqui**: os números de um modelo de verdade (EfficientNet etc.) estão
  "a verificar com o modelo real". Os testes usam grafos ONNX pequenos e um MLP torch.
- O dNATY otimiza o `nn.Module`; para os modelos Keras 3 (backend torch) do `ia/`, a ponte
  Keras → `nn.Module` para o `compress_cnn` não foi testada (sem pesos).
- A medida de latência é na máquina que roda o benchmark; a do hardware-alvo (Jetson etc.)
  depende de rodar o mesmo pipeline nele.
- O envio do relatório ao registry é manual (JSON + `POST`); não há botão no console.
