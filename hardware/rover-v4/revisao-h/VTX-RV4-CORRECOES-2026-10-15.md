# VTX-RV4 · Correções de 15/10/2026 — Revisão H

> Revisão dos cálculos e documentos do Rover V4 feita para a tarefa #109 (requisitos funcionais e
> compatibilidade das peças). Nenhuma geometria, cota ou material foi alterado. Mudaram cálculos que
> usavam premissas erradas, contagens desatualizadas e textos que afirmavam mais do que o cálculo
> verificava.
>
> EMITIDO PARA COTAÇÃO E VALIDAÇÃO — NÃO LIBERADO PARA FABRICAÇÃO

## O que foi corrigido

| # | Onde | Como estava | Como está | Efeito |
|---|---|---|---|---|
| C-01 | `suspensao.roll()` | Rolagem, tombamento e envelope no CG da Rev F do V3 (126,5 kg, Z 285,9 mm), sem o mastro do V4 | CG do inventário do V4 (`centro_massa`, estado projeto: 121,1 kg, Z 336,2 mm), via `suspensao.cg_v4()`. Os foles continuam dimensionados na massa alta de `suspensao.massa()` | Tombamento 39,92° → **34,89°**; envelope 20,89° → **16,31°**. Passa os 16,2° da baseline por **0,1°** |
| C-02 | `suspensao.roll()`, SUSPENSÃO-H §1 | Comparação com o balancim da Rev F (19,57°) calculada em outro CG (294 mm) | Balancim rígido em bitola 470 recalculado **no mesmo CG**: 15,51° | A conclusão continua de pé (16,31° contra 15,51°); a vantagem é de 0,8°, não 1,3° |
| C-03 | SUSPENSÃO-H §7, REGISTRO-ALTERACOES, `modelo.py`, docstring de `suspensao.py` | 39,92° / 20,89° | 34,89° / 16,31°, com nota da correção | Documentos coerentes com o cálculo |
| C-04 | `suspensao.energia()`, SUSPENSÃO-H §8 | "1,5 % de uma bateria de 600 Wh por hora" | 0,20 % por hora da bateria de 5.376 Wh do projeto | A bateria citada não existia no projeto |
| C-05 | `modular.energia()`, MODULAR-H | Só os sensores (167 a 181 W) conferidos contra o conversor de 360 W: "o conversor não é o limite" | Barramento de 12 V inteiro (CABOS-H, ligação 5): sensores + Jetson até 40 W + compressor 180 W = **387 a 401 W** | **O conversor de 360 W não atende o pico** com o compressor ligado |
| C-06 | `modular.rede()`, MODULAR-H, folha 26 (`folhas_b.py`) | 10 portas (9 OAK-D + LiDAR); "12 portas cobrem 2 térmicas" | 12 portas: + ligação à Jetson + terminal satelital (CABOS-H, 13 e 14) | O switch de 12 portas **não sobra para térmica Ethernet** |
| C-07 | `dimensional.py`, CSV de componentes comprados | 8 OAK-D: "6 no mastro, 1 frontal, 1 inferior" | **9 OAK-D**: 6 no mastro, C7 frontal, C8 traseira, C9 de raiz | Lista de compra com a quantidade do V4 |
| C-08 | `sensores.py` | `qtd_base = 8` e posições do V3 | 9, com as posições do V4; nota de que o preço da BOM é de 8 un do V3 | Orçamento de energia com 9 câmeras |
| C-09 | `espaco.py`, ESPAÇO-H | "Cada componente cabe" — conferência de um componente por vez, em qualquer ponto do compartimento | Nova conferência `cabe_na_zona_designada()`: planta e altura na zona reservada e área somada por zona | **4 de 6 zonas não comportam o que o projeto põe nelas** (ver abaixo) |
| C-10 | `VTX-RV4-BOM-Mestra-Dimensional-RevH.csv` | K-02 descrita "com janela da câmera" | Regenerada do modelo: K-02 sem janela (a C7 fica sob o chassi) | O CSV estava desatualizado em relação ao modelo |
| C-11 | CENTRO-MASSA-H | Seção "Há uma divergência no pacote" | Seção "A divergência foi resolvida", com a tabela antes/agora | — |

## O que a nova conferência de espaço mostra (C-09)

Com as dimensões estimadas dos componentes:

| Zona | Problema |
|---|---|
| Bateria | caixa estimada com 130 mm de altura contra teto de 87 mm |
| Bandeja lateral esquerda | a zona tem 380 × 54 mm em planta; a Jetson com carrier (180 × 110) não entra |
| Bandeja lateral direita | idem; driver e BMS não entram, e a área somada (366 cm²) passa a da zona (205 cm²) |
| Grupo pneumático | teto de 37 mm na zona; compressor (120 mm) e reservatório (110 mm) não entram, e a área somada (561 cm²) passa a da zona (418 cm²) |

A tabela antiga dizia "CABE" para todos os eletrônicos porque achava, para cada um, um lugar livre em
algum ponto do compartimento — o mesmo lugar para vários deles e fora da zona reservada. O leiaute
interno precisa ser refeito quando chegarem as fichas técnicas (P-05, P-13, P-18).

## O que NÃO foi regenerado, e por quê

- **Caderno de 42 folhas (PDF) e pacote de cotação.** A cotação em andamento usa a **Rev I** (opções A e B,
  `ENVIO_COTACAO_REV_I/`), que foi produzida editando os PDFs da Rev H — a Rev I não existe na fonte. Rodar
  `gerar.py` e `gerar_pacote.py` agora emitiria de novo a Rev H e sobrescreveria o pacote. Na próxima
  emissão do caderno, a **folha 07** (envelope e tombamento) e a **folha 26** (portas do switch) saem
  corrigidas, porque a fonte já está corrigida.
- **Os PDFs de `revisao-h/pdf/`** foram regenerados (`python gerar_docs.py`).

## O que continua em aberto (não é erro, é decisão ou dado que falta)

- Quantidade de drivers: a BOM do V3 compra 4 Roboteq SBLG2360TS; `espaco.py` reserva lugar para 1 driver de
  4 canais. Depende da ficha do driver (canais por unidade) e decide o leiaute da bandeja direita.
- Limite de tensão dos drivers contra a bateria 16S carregada (cerca de 58,4 V) e a regeneração na frenagem.
- Variante de alimentação do relé de segurança Pilz PNOZ s4 contra os barramentos de 12 V e 48 V do projeto.
- Orçamento energético e autonomia: faltam 7 consumos (P-05).

## Adendo — onde a bateria cabe (fichas de fabricante, 15/10/2026)

A célula EVE LF105 mede 130,3 × 36,35 × 200,5 mm e pesa 1,98 kg (revendas NKON e Battery Junction). Com a
varredura de `espaco.cabe_em_pe`:

| Arranjo das 16 células | Planta × altura | Resultado |
|---|---|---|
| Deitadas, 2 camadas | até 5 por camada na zona de 490 × 370 | cabem só 10 sob o teto de 87 mm |
| De lado, 2 fileiras de 8 | 401 × 291 × ~140 mm (130,3 + barramentos) | **não cabe**: o melhor ponto tem 127 mm livres |
| De lado, limite | 401 × 291 × 90 mm | cabe em X −203…198, Y −162…129, com 127 mm livres |

Quem limita os 127 mm são os dois trilhos transversais centrais **G-02** (X ±30…50, Z 377). Acima deles há
147 mm até as tampas K-04/K-05. Elevar ou deslocar os G-02 em ~15 mm, ou tirá-los de cima da bateria, fecha o pack
de lado sem trocar a célula. É mudança de gaiola e depende da decisão do engenheiro.
