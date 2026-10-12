# Arquivo da Revisão E — como recebida, antes da Rev F

Cópia congelada em 11/10/2026, antes de qualquer alteração para a Revisão F.

## Por que este arquivo existe

`hardware/` não está sob controle de versão (era `?? hardware/` no `git status`).
Sem este arquivo, não haveria como voltar à Rev E nem comparar a Rev F com ela.

## O que está aqui

| Conteúdo | Observação |
|---|---|
| `VALTEXA_ROVER_V3_REV_E/` | pacote completo de cotação, 10 pastas, como emitido |
| `VTX-RV3-CG-E*.pdf` | caderno de 27 folhas (completo, A, B, C) |
| `dxf-chassi-gaiola/` | 27 DXF de corte a laser |
| `modelo-rev-e-como-recebido.py` | o modelo paramétrico no estado em que estava |
| `folhas-*-como-recebido.py` | a composição das folhas no mesmo estado |

## Atenção: o código arquivado NÃO gera estes PDFs

Os PDFs são de 21/09/2026. O código salvo aqui é posterior e **não roda**:

- `python gerar.py` → `KeyError: 'S'` na folha 02
- `dados.itens()` → `KeyError: 'W-01'`

A causa está registrada em `../revisao-f/VTX-RV3-AUDITORIA-F.md`. Em resumo: um
estudo de suspensão de balancim (grupo W) foi iniciado no modelo depois de os
PDFs serem emitidos e ficou pela metade, deslocando o grupo S (suporte rígido)
sem substituí-lo nos demais arquivos.

Os PDFs, DXF e BOM aqui são a **Rev E válida**. O código aqui é só o registro
de como o modelo estava quando a Rev F começou.
