# VTX-RV4 · Rev K — bateria em 2 módulos e leiaute interno refeito (28/10/2026)

> EMITIDO PARA COTAÇÃO E VALIDAÇÃO — NÃO LIBERADO PARA FABRICAÇÃO

## Decisões dos sócios que a Rev K aplica

| # | Decisão | Origem |
|---|---|---|
| 1 | Motor-roda: **ainda em pesquisa** (A importado, B patinete, C servo nacional com redutor) | 28/10/2026 |
| 2 | Autonomia: **8 h por carga a 2 m/s** (57,6 km) | 28/10/2026 |
| 3 | Bateria: **2 módulos de 8 células**, um de cada lado dos trilhos G-02 | 28/10/2026 |
| 4 | Chassi: **aço (opção B)**, por resistência e custo — passa a ser o padrão | 28/10/2026 |

## O que mudou

| Onde | Rev J | Rev K |
|---|---|---|
| `opcao.py` | padrão alumínio (`VTX_OPCAO=AL`) | **padrão aço** (`VTX_OPCAO=AC`); revisão K, 28/10/2026 |
| Bateria (`modelo.py`, folha 20) | uma caixa estimada de 460 × 350 × 130 mm, que **não cabia** (127 mm livres sob os G-02) | **2 módulos de 154 × 410 × 140 mm**, em \|X\| 60…214, com 145–147 mm livres |
| Batentes B-01 | 4, em volta da caixa única | 4, **2 por módulo** (faces interna e externa); malha M6 refeita |
| Cinta F-23 | 2, sobre a caixa única | 2, **uma por módulo** |
| Compressor | zona com 37 mm de teto (não cabia) | **baia traseira**, X −490…−368, 144 mm livres |
| Reservatório 2 L | 300 × 110 × 110 (não cabia) | **2 tubos Ø75 × 220 mm** (~1 L cada) nas faixas dianteiras, X 241…317 |
| Jetson | bandeja lateral de 54 mm (não cabia) | **de pé** na faixa traseira, X −327…−252 |
| Driver dos motores | bandeja lateral (não cabia) | **de pé** na faixa traseira, ao lado da Jetson |
| BMS | bandeja lateral (não cabia) | **baia dianteira**, X 368…490 |
| Bandejas laterais E-01 | Jetson, driver, BMS | livres: fusíveis, borneiras e cabos |
| Autonomia | não calculada | `autonomia.py` (novo) |
| Folha 35 | tabela de zonas da Rev H | notas da Rev K |
| Folha 43 | registro da Rev J | + seção 6, Rev K |

## Resultado das verificações (opção B, aço)

| Verificação | Rev J | Rev K |
|---|---|---|
| Zonas que comportam o que o projeto põe nelas | 2 de 6 | **10 de 10** |
| Interferências entre peças | 0 | 0 |
| Defeitos de layout nas 43 folhas | 0 | 0 |
| Centro de massa lateral (Y) | −7 mm, bateria não bastava para equilibrar | **−0,3 mm** |
| Tombamento lateral em rampa | 34,8° | **35,4°** |
| Envelope de estabilidade | 16,8° | 16,8° |
| Pressão de projeto dos foles | 8,81 bar | 8,81 bar — **continua acima do teto de 8** |

## Autonomia — 8 h a 2 m/s (`autonomia.py`)

Aço, 176,8 kg com carga útil; bateria de 5.376 Wh, 4.301 Wh usáveis (reserva de 20 %). Eletrônica: 278 W.

| Terreno | Tração | Total | Horas | Energia para 8 h |
|---|---|---|---|---|
| Plano | 231 W | 509 W | **8,4 h** | 5,1 kWh |
| Morro leve (5°) | 317 W | 595 W | 7,2 h | 5,9 kWh |
| Morro de café (10°) | 515 W | 793 W | **5,4 h** | 7,9 kWh |

Coeficiente de rolamento (0,05) e rendimento da tração (75 %) são estimativas até a escolha do motor.
Decisão de 28/10 (caminho 1): manter a bateria e aceitar menos horas no morro, reduzir a velocidade ali ou
trocar um módulo no turno — os módulos saem sozinhos, soltando uma cinta.

## O que continua em aberto

1. **Foles na opção aço (8,81 bar > 8 bar).** Especificar fole de 10 bar ou de área efetiva ~19 % maior
   (volta a ~7,4 bar). Muda a cotação dos foles, não a geometria do chassi.
2. **Motor-roda** (decisão 1 em pesquisa): define torque, driver, massa e a interface W-02.
3. **Conversor de 12 V** de 360 W contra 387–401 W de pico: trocar por ≥ 500 W ou separar o compressor.
4. **Switch de 16 portas PoE** no lugar do de 8.
5. **Fichas técnicas** de Jetson com carrier, driver, BMS, conversor e módulos de bateria: as zonas da Rev K
   cabem com as dimensões estimadas; a ficha confirma.
6. **Análise estrutural** (8 casos da folha 25) e parecer do engenheiro.
