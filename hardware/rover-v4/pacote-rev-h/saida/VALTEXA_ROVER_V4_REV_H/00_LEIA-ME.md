# VALTEXA ROVER V4 — Rev H · pacote de engenharia e fabricação

Emitido em 12/10/2026 · **para cotação e validação — não liberado para fabricação**

> Este pacote **substitui** o de 11/10/2026. Aquele carregava, nos documentos 01, 02, 06, 07, 08, 09 e 10,
> texto herdado do V3 (suportes rígidos, mastro Ø25×2, placa M-20, carenagem N-09, oito câmeras). Foi
> reescrito e conferido contra o modelo.

## O que é cada pasta

| Pasta | Conteúdo | Para quem |
|---|---|---|
| `01_DOCUMENTO_TECNICO` | Memorial: arquitetura, dimensões, massa, mastro, suspensão, interfaces, divergências | Engenheiro mecânico |
| `02_PACOTE_ORCAMENTO` | Listas por processo, matéria-prima, inspeção e cenários 1/3/15 | Empresas de fabricação |
| `03_DESENHOS_TECNICOS` | Caderno de 42 folhas A3, completo, por parte (A a E) e por assunto | Todos |
| `04_CAD` | DXF 1:1 (produção) e STL (visualização) | Corte a laser, engenharia |
| `05_BOM` | Lista de materiais mecânica completa, com os opcionais separados | Compras |
| `06_FORNECEDORES` | Pesquisa de fornecedores em Pouso Alegre e região (alumínio; aço NÃO levantado) | Compras |
| `07_RFQ` | Formulário de solicitação de orçamento | Enviar às empresas |
| `08_PENDENCIAS` | Pendências de engenharia e auditoria do pacote | Engenheiro + gestão |
| `09_CONCEITO_BASES` | Conceito da base de recarga e do poste (NÃO é baseline) | Produto + engenharia |
| `10_CUSTOS` | Estrutura de custo: quantidades, preços em branco; itens novos do V4 a cotar | Compras |
| `11_ENGENHARIA_REV_H` | Mastro, modular, suspensão, usinagem, montagem, espaço, cabos, auditoria, liberação | Engenheiro mecânico |

## Regra de leitura

Todo valor carrega uma etiqueta: **CONFIRMADO** (baseline, ficha de fabricante ou caderno), **DERIVADO**
(calculado), **PROPOSTA** (escolha deste pacote, a aprovar) e **A DEFINIR** (ausente). Nada foi preenchido por
estimativa silenciosa.

## Avisos importantes

1. **Os preços de compra são os do V3** (planilha de 21/09/2026). Itens que o V4 acrescentou ou mudou entram
   como **A COTAR**, sem preço, e **não** entram nos totais. O total verdadeiro é maior que o mostrado.
2. O CAD Rev B (`VALTEXA-ROVER-V3-RevB-CAD.step`) está **superado** — não usar.
3. Base de recarga e poste **não existem na baseline**: a pasta 09 é conceito para discussão.
4. A fabricação depende do parecer do engenheiro mecânico (folha 15) e do fechamento das pendências. A
   liberação de 11/10/2026 é sobre a **Rev F do V3**, não sobre este V4: o campo de aprovação está vazio.
5. Nada aqui é validação física. Os cálculos do mastro, da repetibilidade e da suspensão são cálculos; os ensaios
   V-10 a V-17 não foram feitos.

## Como regenerar

```
cd hardware/rover-v4/chassi-gaiola && python gerar.py                  # caderno + DXF
cd ../chassi-gaiola && python verifica_layout.py                      # mede o layout de cada folha
cd ../revisao-h && python relatorios.py && python gerar_docs.py       # documentos de engenharia
cd ../pacote-rev-h && python gerar_pacote.py                          # este pacote
```
