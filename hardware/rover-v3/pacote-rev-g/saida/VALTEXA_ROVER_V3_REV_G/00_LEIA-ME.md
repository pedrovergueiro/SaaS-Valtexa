# VALTEXA ROVER V3 — Rev E · pacote de engenharia e fabricação

Emitido em 21/09/2026 · **para cotação e validação — não liberado para fabricação**

## O que é cada pasta

| Pasta | Conteúdo | Para quem |
|---|---|---|
| `01_DOCUMENTO_TECNICO` | Memorial: arquitetura, dimensões, massa, interfaces, divergências | Engenheiro mecânico |
| `02_PACOTE_ORCAMENTO` | Listas por processo, matéria-prima, inspeção e cenários 1/3/15 | Empresas de fabricação |
| `03_DESENHOS_TECNICOS` | Caderno de 27 folhas A3, completo e fatiado por assunto | Todos |
| `04_CAD` | DXF 1:1 (produção) e STL (visualização) | Corte a laser, engenharia |
| `05_BOM` | Lista de materiais mecânica completa (CSV/XLSX) | Compras |
| `06_FORNECEDORES` | Pesquisa de fornecedores em Pouso Alegre e região | Compras |
| `07_RFQ` | Formulário de solicitação de orçamento | Enviar às empresas |
| `08_PENDENCIAS` | Pendências de engenharia e auditoria do pacote | Engenheiro + gestão |
| `09_CONCEITO_BASES` | Conceito da base de recarga e do poste (NÃO é Rev E) | Produto + engenharia |
| `10_CUSTOS` | Estrutura de custo: quantidades fechadas, preços em branco para cotação | Compras |

## Regra de leitura

Todo valor carrega uma etiqueta: **CONFIRMADO** (baseline Rev E ou caderno), **DERIVADO** (calculado),
**PROPOSTA** (escolha deste pacote, a aprovar) e **A DEFINIR** (ausente). Nada foi preenchido por estimativa
silenciosa.

## Avisos importantes

1. Os arquivos de BOM de compras e preços citados no escopo original não foram localizados no projeto.
   A BOM mecânica aqui foi montada a partir da geometria; **nenhum preço foi estimado**.
2. O CAD Rev B (`VALTEXA-ROVER-V3-RevB-CAD.step`) está **superado** (1.000 × 570 mm) — não usar.
3. Base de recarga e poste **não existem na Rev E**: a pasta 09 é conceito para discussão.
4. A fabricação depende do parecer do engenheiro mecânico (folha 15) e do fechamento das pendências.

## Como regenerar

```
cd hardware/rover-v3/chassi-gaiola && python gerar.py        # caderno + DXF
cd ../pacote-rev-e && python gerar_pacote.py                 # este pacote
```
