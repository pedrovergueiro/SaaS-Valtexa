# Rover V3 — caderno do chassi e da gaiola (VTX-RV3-CG-E)

Desenhos de fabricação do chassi estrutural e da gaiola de proteção, para cotação com
fornecedores e validação pelo engenheiro mecânico. Base: `VTX-RV3-BASELINE-E` (Rev E) e o
datasheet do ElectroCraft MPW86.

## O que sai em `saida/`

| Arquivo | Para quê |
|---|---|
| `VTX-RV3-CG-E.pdf` | Caderno completo: 27 folhas A3 (Partes A, B e C) |
| `VTX-RV3-CG-E-A.pdf` | **Parte A** (01–16) — chassi e gaiola: é o que vai para o fornecedor cotar |
| `VTX-RV3-CG-E-B.pdf` | **Parte B** (17–22) — mastro, câmeras, bateria, eletrônica, E-STOP e sensores |
| `VTX-RV3-CG-E-C.pdf` | **Parte C** (23–27) — pendências, massa, solda/FEA e plano de validação |
| `VTX-RV3-CG-E.html` | Caderno completo no navegador (Ctrl+P gera o PDF de novo) |
| `dxf/` | Peças planas em 1:1, mm, para corte a laser — mandar junto com o PDF |
| `artefato.html` | Versão para publicar como página (sem o cabeçalho HTML) |

## Como regenerar

```
python gerar.py                # HTML + DXF + 4 PDFs (completo, A, B e C)
python gerar.py --so-completo  # só o PDF de 27 folhas
python gerar.py --sem-pdf      # só HTML e DXF
```

O PDF é impresso pelo Edge/Chrome em modo headless. As fontes ficam em cache em `fontes/`.

## Onde mudar o quê

- `modelo.py` — toda a geometria, em mm, no referencial ISO 8855 da baseline. Mudou uma
  cota? Mude aqui: vistas, cortes, listas de corte, massas e DXF saem daqui.
- `folhas.py` — composição das folhas 01 a 16 (Parte A) e a infraestrutura de layout.
- `folhas_b.py` — folhas 17 a 27 (Partes B e C).
- `desenho.py` — motor de desenho (projeções 1º diedro, cortes, isométricas, cotas, carimbo,
  simbologia de solda, rugosidade e tolerância geométrica).
- `estilo.css` — tipografia e traços (ISO 128).

## Antes de enviar

- Preencher o contato da ValTexa na folha 16 (ou à mão no PDF).
- Status: **emitido para cotação e validação**. A fabricação só começa depois do parecer
  assinado do engenheiro na folha 15. Ao revisar, subir a revisão no carimbo (`rev` em
  `folhas.py`) e descrever a mudança.
