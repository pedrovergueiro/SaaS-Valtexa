# Rover V4 — interface modular de sensores VMS-60

> **VTX-RV4 · Revisão H · 12/10/2026**
> EMITIDO PARA COTAÇÃO E VALIDAÇÃO — NÃO LIBERADO PARA FABRICAÇÃO
>
> Documento **gerado** de `revisao-h/modular.py` sobre a geometria de
> `chassi-gaiola/modelo.py`. Não editar à mão: a próxima geração sobrescreve.


## O que separa "removível" de "modular"

Removível é qualquer coisa com parafuso. **Modular é o que se pode repor no mesmo lugar.**

A fusão de dados usa a matriz extrínseca de cada câmera — onde ela está e para onde aponta,
no referencial do rover — como **constante**, medida uma vez na calibração. Se trocar uma
câmera desloca a próxima em 1°, a calibração morre junto com a peça trocada, e o técnico
que fez a troca na lavoura degradou a navegação sem ter como perceber.

Por isso a face VMS-60 se apoia em **pino**, não em parafuso.

| Interface | Erro angular | Deslocamento a 10 m |
|---|---|---|
| **Pino Ø8 H7/h6 + anti-giro a 26 mm** | **0,048°** | **8,5 mm** |
| Só parafuso M5 em furo Ø5,5 | 1,10° | 192 mm |

Fator **23×**. O limite para trocar sem recalibrar é
0,1° — da ordem do próprio ruído de profundidade estéreo a
10 m. Com pino passa com margem 2,1×; sem pino, **não passa**.

Dois pinos custam dois furos alargados e um minuto de prensa.

## As três camadas

| Camada | Peça | O que define | Mexer nela exige |
|---|---|---|---|
| 1 · posição | T-01 braçadeira | altura e azimute no mastro | **recalibrar** a extrínseca |
| 2 · interface | T-02 prato VMS | os pinos e a inclinação indexada | recalibrar só se mudar o índice |
| 3 · adaptação | T-03 adaptador | a furação daquele modelo de sensor | **nada** — é a troca de campo |

Trocar a câmera mexe só na camada 3. **Não tocar na braçadeira** é a regra que protege a
calibração.

A inclinação é indexada por pino em 7 posições, passo de
10° — de −30° a
+30°. Índice por pino repete; aperto por
atrito não.

## Proteção sem nada na frente da lente

O requisito diz: proteger contra impacto **sem grade, aro ou defletor diante das lentes**.
A geometria concorda, e não dá margem:

Com 128° de campo horizontal, qualquer peça a 40 mm à
frente da lente teria de estar a **82 mm** do eixo para não
aparecer na imagem. O prato tem 36 mm de meia-largura.
**Lateralmente não cabe** — e é por isso que o projeto não tem grade nenhuma.

Verticalmente cabe: 40 mm à frente exigem
34 mm acima, e o protetor T-05 tem
40, com 6 mm de folga.

Daí a solução: **sobrancelha superior sacrificial**, e nada ao lado nem à frente.

| Ameaça | De onde vem a proteção |
|---|---|
| Galho vindo de frente | lente recuada 6 mm atrás da face do adaptador + sobrancelha T-05 avançando 40 mm acima do eixo óptico |
| Galho vindo de cima | sobrancelha T-05, que é a peça sacrificial: 2 parafusos M4 e troca em campo sem ferramenta especial |
| Galho vindo de fora para dentro | o protetor envolve o canto externo superior; o lado de dentro é protegido pelo próprio mastro |
| Pedra lançada pela roda | as câmeras de extremidade ficam SOB a chapa de fundo, com a chapa por cima e 60 mm de recuo da borda |
| Impacto no mastro inteiro | bainha anti-galho M-11 em UHMW-PE sobre o tubo, nos trechos entre câmeras |
| Chuva e lavagem | conector M12 codificação X por posto; a vedação é do conector, não de caixa — ver nota sobre IP |
| Poeira e lama | nenhuma fenda horizontal voltada para cima no posto VMS; o prato T-02 é inclinável e drena |
| Vibração | montagem RÍGIDA por decisão de projeto — ver `mastro.py` |


O projeto NÃO declara grau de proteção IP para o posto de sensor, e isso é deliberado.

Grau IP é resultado de ENSAIO num conjunto fechado, não propriedade de um conector
isolado. O que o projeto pode afirmar é o que especifica: conector M12 com codificação X,
que é o padrão de Ethernet industrial e existe em versões classificadas por fabricante. O
grau do POSTO montado — conector, cabo, passa-cabo e carcaça da câmera juntos — só sai do
ensaio, e está na lista de ensaios como V-11.

Declarar "IP67" aqui sem o ensaio seria inventar classificação, que é exatamente o que o
pedido do V4 proíbe.


## Matriz de compatibilidade do posto VMS-60

| Módulo | Classe | Massa | Consumo | Cabe no VMS? | O que falta |
|---|---|---|---|---|---|
| OAK-D Pro W PoE (base) | inspeção | 0,25 kg | 12,9 W | **sim** | desenho dimensional e furação reais (P-06); massa é ESTIMATIVA |
| Câmera térmica radiométrica compacta | inspeção | 0,20 kg | 3,0 W | **sim** | NENHUM MODELO ESCOLHIDO. Adaptador T-04 é requisito, não desenho |
| Câmera RGB alternativa (GigE industrial) | inspeção | 0,30 kg | 6,0 W | **sim** | furação própria: exige adaptador novo, que é 1 peça de chapa 6 |
| Sensor multiespectral | inspeção | 0,35 kg | 8,0 W | **sim** | modelo não escolhido; massa e consumo são FAIXA |
| LiDAR Livox Mid-360 | navegação | 0,30 kg | — | não | NÃO vai em posto VMS: precisa de 360° livres e fica no alto da gaiola, em G-06 com coxins. É o único sensor que permanece ISOLADO — ver `mastro.py` |
| Antena GNSS RTK | navegação | — | — | não | NÃO vai em posto VMS: precisa de vista livre ao céu e plano de terra. Tem duas provisões — T-10, no topo do mastro (esboço do projeto), e N-01, na tampa (V3). A escolha é decisão aberta (P-36) |
| IMU | navegação | — | — | não | NÃO vai em posto VMS: tem de ficar o mais perto possível do CG, não no alto do mastro — no mastro ela mediria a vibração do mastro, não o movimento do rover |
| Terminal de comunicação por satélite | comunicação | — | — | não | NÃO vai em posto VMS: berço próprio T-07 na tampa, envelope máximo 220 × 240 × 40 |


### As classes não são burocracia

| Classe | O que significa para o software |
|---|---|
| navegação | Sensor de navegação — a ausência dele PARA o rover |
| inspeção | Sensor de inspeção agrícola — a ausência degrada a missão, não a segurança |
| comunicação | Equipamento de comunicação — a ausência tira a telemetria |

**A ausência de uma câmera de inspeção não pode impedir a inicialização nem a navegação.**
A ausência de LiDAR, GNSS ou IMU tem de impedir. É requisito de software, e a distinção
existe para que o rover continue trabalhando com uma câmera queimada em vez de parar na
lavoura.

## Energia e rede com nove câmeras

| Grandeza | Sem térmica | 2 térmicas | **4 térmicas (todas as posições)** |
|---|---|---|---|
| 9 × OAK-D a 12,95 W (teto 802.3af classe 3) | 116,5 W | 116,5 W | 116,5 W |
| Térmicas a 3,0 W (FAIXA) | 0 W | 6,0 W | 12,0 W |
| Terminal satelital (provisão) | 30 W | 30 W | 30 W |
| **Total com 15 % de perda de PoE** | **167 W** | **174 W** | **181 W** |
| Conversor de 360 W | cabe, folga 193 W | cabe, folga 186 W | cabe, folga 179 W |
| Portas Ethernet (OAK-D + LiDAR + térmicas por Ethernet) | 10 | 12 | 14 |
| Cabe em switch de 8 portas? | **não** | **não** | **não** |
| Cabe em switch de 12 portas? | sim | sim | **não — exige 16 portas** |
| Banda agregada | 540 Mbit/s | 540 Mbit/s | 540 Mbit/s |

**A 9ª câmera não dói na energia — dói na rede.** São 10 portas com o LiDAR, e o switch PoE
de 8 não atende. Trocar por um de 12 portas PoE+ é **item novo de BOM**, não ajuste de
desenho (P-31). O de 12 portas cobre até **2 térmicas por Ethernet**; as 4 posições
cheias, por Ethernet, exigem 16 portas. Se a térmica escolhida for USB, ela entra pela Jetson e
não ocupa porta — o modelo ainda não existe (P-30). A banda é 54 % de um uplink de 1 Gbit/s
com as OAK-D; as térmicas somam pouco a ela.


## Módulo térmico removível — o que é e o que ainda não é

A ideia do projeto: a OAK-D é **fixa e calibrada**; a térmica é **módulo removível**, com
desconexão rápida. No V4 isso se resolve **sem criar interface nova**: o posto térmico usa a
mesma braçadeira T-01, o mesmo prato T-02 e a mesma face VMS-60 da OAK-D. Muda o adaptador
(**T-04**) e a forma de apertar.

| | OAK-D (fixa) | Térmica (removível) |
|---|---|---|
| Adaptador | T-03, com a furação da OAK-D | **T-04**, sem furação de sensor (modelo não escolhido) |
| 4 parafusos M5 da face | cabeça sextavada interna, com chave | **imperdíveis, de aperto manual**, sem ferramenta |
| Pinos de referência Ø8 / Ø6 | ficam no prato | **ficam no prato** — é o que faz o módulo voltar à mesma pose |
| Conector | M12 de painel, fixo no posto | **M12 de desconexão no cabo do módulo** |
| Posição | andar nominal, ajustável | a meio caminho entre dois andares (725, 1270), ajustável |
| Calibração ao trocar | verificação | verificação (mesmo procedimento, sem ferramenta) |

**Envelope que o módulo pode ocupar: 72 × 64 × 46 mm.** Não é a dimensão de uma
câmera — é o que já está desenhado: o prato tem 72 × 64 e a sobrancelha T-05 se estende 46 mm.
Uma câmera maior pede protetor novo. E o módulo tem de **deixar livre o acesso às cabeças dos
4 parafusos**, senão não é removível à mão: se o corpo da câmera os cobrir, o T-04 ganha um
espaçador (P-38).

**O que não está fechado:** a repetibilidade com parafuso de aperto manual (ensaio V-16 — o V-10
mede só o parafuso de ferramenta), o modelo da câmera (P-30) e o torque de aperto manual que
o procedimento deve exigir. O número de 0,048° vale para o pino; o que o aperto manual
faz à folga entre o pino e o furo é medição, não cálculo.

## A antena GNSS RTK: duas provisões, uma decisão aberta

O esboço do projeto põe a antena no **topo do mastro**. O V3 tinha desenhado a N-01 na tampa
traseira. O V4 deixa as duas provisões e **não decide** (P-36):

| | Topo do mastro (T-10) | Tampa traseira (N-01) |
|---|---|---|
| Altura do plano de apoio da antena | 1832 mm | 433,2 mm |
| Deslocamento da antena por 10° de inclinação do rover | 323 mm | 76 mm |
| Custo no mastro | 1ª freq. 9,29 → 7,88 Hz | nenhum |
| Massa máxima da antena | **0,42 kg** | sem limite estrutural |
| Interface | rosca 5/8"-11 UNC (A VALIDAR) + furo Ø10 para o cabo | chapa 110×110×5, 4 × M5 |
| O que o software precisa | **compensação de inclinação por IMU, obrigatória** | recomendada |

Nenhum número de desempenho de GNSS está aqui: multicaminho, tempo para fixar e perdas de fix
dependem de ensaio (V-17).


## O que o software tem de fazer

| Requisito | O que significa |
|---|---|
| Identificação do módulo | Cada posto VMS tem um identificador físico. O software lê o número de série da câmera na enumeração Ethernet e o associa ao POSTO, não ao equipamento — é o posto que tem calibração extrínseca, não a peça. |
| Detecção de desconexão | Perda de enumeração por mais de 2 s = módulo ausente. O sistema registra, segue operando e marca os dados daquele posto como indisponíveis. |
| Operação degradada | A ausência de qualquer câmera de INSPEÇÃO não impede a inicialização nem a navegação. A ausência de LiDAR, GNSS ou IMU — classe navegação — impede, e isso é projeto, não falha. |
| Perfil por modelo | Cada modelo de sensor tem um perfil: driver, resolução, taxa, intrínsecos de fábrica e limites. Trocar o modelo num posto troca o perfil, não o código. |
| Verificação de calibração após troca | Ao detectar número de série novo num posto conhecido, o sistema exige a verificação: alvo conhecido, erro de reprojeção medido, aceite se abaixo do limite de 0,1°. Com pino de referência o esperado é passar de primeira. |
| Detecção de perda de referência | Se a braçadeira T-01 for afrouxada, a extrínseca muda e o pino não protege. O software NÃO tem como saber sozinho — por isso o procedimento de manutenção exige registro manual, e é a maior fragilidade desta arquitetura. Ver `pendencias`. |
| Sincronização temporal | Todos os fluxos com carimbo de tempo da mesma base. Um módulo novo sem sincronização entra como fluxo isolado, não entra na fusão. |
| Interface com o SaaS | Inventário de módulos por rover, com posto, modelo, número de série e data da última calibração. NOT_IMPLEMENTED no SaaS. |


## Trocar um sensor em campo

| n | O que fazer | Por quê |
|---|---|---|
| 1 | Desligar o rover e travar o sistema de ar no vão mínimo | segurança |
| 2 | Desconectar o M12 do posto | o conector é o único ponto elétrico |
| 3 | Soltar os 4 parafusos M5 do adaptador T-03 | chave Allen 3 mm |
| 4 | Retirar o adaptador com a câmera | os pinos de referência FICAM no prato T-02 |
| 5 | NÃO tocar na braçadeira T-01 | é o que preserva a calibração extrínseca |
| 6 | Montar o adaptador novo nos pinos, apertar os 4 M5 a 5 N·m | cruzado |
| 7 | Reconectar o M12 e ligar | o sistema detecta o número de série novo |
| 8 | Rodar a verificação de calibração do posto | alvo conhecido, 2 minutos |
| 9 | Registrar no inventário: posto, modelo, série, data | rastreabilidade |

**O passo 5 é o que importa:** não tocar na braçadeira T-01. É ela que define altura e
azimute, e é a única camada cuja alteração exige recalibrar.

### Trocar o módulo térmico (sem ferramenta)

| n | O que fazer | Por quê |
|---|---|---|
| 1 | Desligar o rover e travar o sistema de ar no vão mínimo | segurança |
| 2 | Desconectar o M12 do módulo | o conector é o único ponto elétrico; o cabo fica no mastro |
| 3 | Soltar os 4 parafusos imperdíveis M5 com a mão | sem ferramenta — é o que torna o módulo removível |
| 4 | Retirar o módulo inteiro (adaptador T-04 + câmera + protetor T-05) | os pinos de referência FICAM no prato T-02 |
| 5 | NÃO tocar na braçadeira T-01 nem no índice de inclinação | é o que preserva a posição calibrada |
| 6 | Encaixar o módulo nos pinos e apertar os 4 parafusos com a mão, em cruz | aperto manual firme; torque a definir no ensaio V-16 |
| 7 | Reconectar o M12, ligar e confirmar o posto no inventário | o sistema lê o número de série |
| 8 | Rodar a verificação de calibração do posto | alvo conhecido, 2 minutos |


## Ensaios que esta arquitetura exige

| Cód. | Ensaio | Aceite |
|---|---|---|
| V-10 | Repetibilidade da interface VMS | Montar e desmontar o mesmo adaptador 10 vezes, medindo a orientação com alvo a 5 m. Aceite: dispersão abaixo de 0,1°. É o ensaio que valida ou derruba o argumento do pino. |
| V-11 | Grau de proteção do posto montado | Jato e poeira conforme IEC 60529 no conjunto conector + cabo + câmera. Sem isto o projeto NÃO declara IP. |
| V-12 | Vibração do mastro em campo | Acelerômetro nos três andares, percurso de 1 km em rua de café. Mede o espectro real e fecha a margem de frequência que hoje é critério, não medição. |
| V-13 | Impacto de galho no protetor | Carga lateral progressiva no protetor T-05 até a ruptura. Aceite: o protetor rompe antes do adaptador, e a câmera sobrevive. |
| V-14 | Troca em campo cronometrada | Técnico com ferramenta de campo troca uma câmera do andar alto. Aceite: abaixo de 10 minutos, sem recalibração. |
| V-15 | Operação com módulo ausente | Desconectar cada câmera de inspeção, uma por vez, com o rover em missão. Aceite: nenhuma interrupção de navegação. |
| V-16 | Repetibilidade do módulo térmico com parafuso de aperto manual | Como o V-10, mas com os 4 parafusos imperdíveis apertados à mão por três técnicos diferentes. Aceite: dispersão abaixo de 0,1°. Define também o aperto mínimo que o procedimento exige. |
| V-17 | Antena GNSS no topo do mastro | RTK em marcha na lavoura com a antena em T-10 e depois em N-01, mesma rota. Compara: tempo para fixar, perdas de fix, erro cruzado. É o que decide a pendência P-36 com dado, e não com preferência. |

**Nenhum destes ensaios foi feito.** O V-10 é o que valida ou derruba o argumento do pino,
que é a base de toda esta arquitetura — enquanto ele não rodar, a repetibilidade calculada
é cálculo, não medição.

## Pendências

| Cód. | Assunto | Grau | O que falta |
|---|---|---|---|
| **P-06** | Desenho dimensional da OAK-D Pro W PoE | CRÍTICA | Bloqueia a furação do adaptador T-03, que é a peça que define a modularidade. Os 4 furos Ø3,4 desenhados são PROVISÃO — a furação real vem do fabricante. Sem ela, T-03 não é cota de fabricação. |
| **P-30** | Modelo da câmera térmica | ALTA | Nenhum escolhido. O adaptador T-04 existe como REQUISITO: uma chapa 72×64×6 com a face VMS-60 de um lado e a furação do modelo do outro. É 1 peça de corte a laser por modelo adotado. |
| **P-31** | Switch PoE de 12 portas | ALTA | A 9ª câmera estoura o switch de 8 portas. Item NOVO de BOM, não previsto no V3. |
| **P-32** | Terminal de comunicação por satélite | MÉDIA | Provisão desenhada para até 220 × 240 × 40 mm. Um terminal da classe 300 × 260 — que é a do Starlink Mini — NÃO CABE sem deslocar o suporte do LiDAR ou a antena GNSS. |
| **P-33** | Detecção de afrouxamento da braçadeira | MÉDIA | O software detecta troca de módulo, mas não detecta que alguém mexeu na altura. É a fragilidade da arquitetura, e hoje só o procedimento cobre. |
| **P-34** | Grau de proteção IP do posto | MÉDIA | Não declarado, por não ter ensaio. Ensaio V-11. |
| **P-36** | Onde fica a antena GNSS RTK: topo do mastro ou tampa | ALTA | O esboço do projeto põe a antena no topo do mastro; o V3 desenhou N-01 na tampa. As duas têm provisão no V4 e nada foi decidido. No topo: céu livre, mas 1,83 m de braço de alavanca (compensação de inclinação por IMU é obrigatória) e a massa de ponta custa frequência do mastro. Na tampa: sem braço de alavanca, mas multicaminho do próprio rover. Ensaio V-17. |
| **P-37** | Antena GNSS: modelo e massa | ALTA | Nenhuma escolhida. O mastro cumpre 7,5 Hz com antena de até 0,42 kg (ver `mastro.py`). Antena mais pesada exige Ø32×4 ou outro conceito. A rosca de 5/8"-11 UNC é o padrão de topografia e está A VALIDAR com o modelo. |
| **P-38** | Câmera térmica: cabe no envelope e deixa livre o acesso aos parafusos? | ALTA | O módulo removível tem de caber em 72 × 64 × 46 mm (prato e sobrancelha T-05) e deixar livre a cabeça dos 4 parafusos. Se a câmera escolhida cobrir os parafusos, o T-04 ganha um espaçador — é uma peça a mais, não um redesenho. |
| **P-39** | Margem do mastro contra o terreno não fecha a 1,4 m/s | MÉDIA | Com o mastro cheio a razão frequência/excitação é 1,41 contra o mínimo de 2,0; a margem só fecha abaixo de ~1,0 m/s. A excitação é critério, não medição. Ensaio V-12 decide: ou o espectro real é benigno, ou a velocidade com mastro cheio é limitada. |
| **P-40** | Cabos dentro do tubo do mastro | MÉDIA | Com a parede de 3 mm o furo do tubo é Ø26. Os 5 cabos M12 e o coaxial da antena de um mastro ocupam cerca de 40 % dele com cabos de Ø7 — que é ESTIMATIVA, nenhum cabo foi escolhido. Acima de Ø7 passa do limite de 40 %. Se passar: cabos de menor diâmetro, ou canaleta externa sob a bainha. |
| **P-41** | Mastro em perfil T 30×30, como no esboço | MÉDIA | O esboço do projeto desenha o mastro em perfil de alumínio T com T-nuts. O V4 manteve o tubo Ø32×3 com braçadeira porque a rigidez do tubo foi calculada e a de um perfil T não tem ficha técnica no projeto. Se o perfil for preferido por montagem, é preciso a ficha (momento de inércia) e um novo cálculo de frequência — o caso 6 do FEA não pode ser assumido. |
| **P-35** | Campo de visão real da OAK-D Pro W | MÉDIA | 128° × 80° são os valores divulgados, não ficha técnica no projeto. O protetor T-05 é dimensionado por eles; se mudarem, redimensiona. |