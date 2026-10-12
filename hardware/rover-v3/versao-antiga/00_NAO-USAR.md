# Revisões superadas — não usar para fabricar nem para cotar

O que vale é a **Revisão G**, em `../chassi-gaiola`, `../revisao-g` e `../pacote-rev-g`.
Comece por `../00_LEIA-ME.md`.

Esta pasta existe por um motivo só: **revisão de engenharia não se apaga.** Quando alguém
perguntar daqui a seis meses por que a bitola é 530 e não 470, ou por que a suspensão não é
balancim, a resposta tem de estar verificável — não apenas resumida por quem decidiu.

| Pasta | O que é | Por que foi superada |
|---|---|---|
| `rev-e/` | Revisão E, 18/09/2026 — a baseline original | nenhum dos dois pacotes gerava; ver a auditoria da Rev F |
| `rev-f/` | Revisão F, 11/10/2026 — completa: CAD, cálculos e pacote | a suspensão a ar ficou como estudo fora do conjunto, e o balancim proposto não ajustava o vão livre; ver `../revisao-g/VTX-RV3-AUDITORIA-G.md`, §0.0 |

## Cada revisão arquivada é autossuficiente

`rev-f/` contém o próprio `chassi-gaiola/` congelado, e não um ponteiro para o atual. Os
módulos de cálculo de `rev-f/revisao-f/` importam dele, e por isso ainda rodam e ainda
reproduzem os números que a Rev F publicou — inclusive os que a Rev G corrigiu.

## O que a Rev G corrigiu na Rev F

Quatro erros de cálculo e dois de geometria, listados em
`../revisao-g/VTX-RV3-AUDITORIA-G.md`, seção 0.0. O resumo:

- `ALTURA_AJUSTAVEL_MM = 50` era incompatível com a geometria do balancim;
- a perda de envelope por rolagem macia estava superestimada (o fim de curso não entrava);
- a área do fole foi dimensionada pela pressão estática, não pela de projeto;
- a reação de torque ignorava a reação do estator;
- a bandeja E-02 colidia com o colar do fole;
- o alojamento da bucha encostava nas orelhas da torre.

Os seis têm o mesmo padrão: **ninguém tinha medido.** A Rev G acrescentou três conferências
automáticas que rodam a cada geração, e que não existiam em revisão nenhuma antes dela.
