# Estresse (brief, seção 42) — números reais

Três níveis, todos com o **Rover Runtime de verdade** (Edge AI pelo ONNX Runtime, banco
local, buffer, retenção, Sync Engine) e invariantes conferidas no fim de cada um: **cada
registro do robô chegou uma vez**, **todo original de evento chegou** (hash), a missão
contou **cada quadro uma vez**, a fila zerou. Máquina: a VM desta nuvem (4 vCPU),
compartilhada com outras execuções — os tempos são conservadores.

## 1. Rover contra o dublê de nuvem (`python -m valtexa_rover.sim.estresse`)

O que dá errado de propósito, ao mesmo tempo: rede que cai 60 de cada 150 passos; rajadas
de `503`×6 + `429` + `500` a cada 400 passos; a rede cai no meio do que estiver enviando
(chunks) a cada 97 passos; reinício do robô a cada 700 passos; uma câmera fora 10 de cada
500 capturas; e, com `--cota-mb`, disco pequeno (a retenção precisa liberar espaço).

| Execução | Quadros | Resultado |
| --- | --- | --- |
| `--passos 1500` (2 câmeras) | **2.970** | 30 falhas de câmera, 2 reinícios, 600 passos sem rede, 32 respostas 5xx/429 injetadas; **3.286 registros locais = 3.286 na nuvem**; 3.078 arquivos; **18/18 originais de evento** entregues; 0 itens `FALHOU`; 30,2 s de missão (≈100 quadros/s) e 0,9 s de sincronização final |
| `--passos 50000 --cota-mb 400` | **99.000** (1.000 capturas com a câmera fora) | 604 eventos, **71 reinícios**, 19.980 passos sem rede, 1.000 respostas 5xx/429 injetadas, 640 limpezas por disco cheio; **110.106 registros locais = 110.106 na nuvem** (nenhum perdido nem duplicado); 86.787 arquivos na nuvem; fila zerada (sincronização final em 4,0 s). 15.815 itens `FALHOU` = reduzidas NORMAL **descartadas pela retenção** sob pressão de disco ("descartada por falta de espaço"), como a política manda. 58 min (28,5 quadros/s médio em CPU compartilhada). **Ressalva**: nesta execução a conferência "todo original de evento chegou" contou 0 — ela lia o banco local, cujas linhas de arquivo já enviado a limpeza apaga. Corrigida para ler o que a nuvem recebeu (abaixo); a execução de 100 mil não foi repetida |
| `--passos 3000 --cota-mb 2` (após a correção da conferência) | **5.940** | 47 limpezas por disco cheio; 6.646 registros = 6.646 na nuvem; **38 de 38 originais de evento na nuvem**; 0 `FALHOU` |

**Achado de desempenho.** A primeira tentativa dos 100.000 quadros (código antigo, cota de
400 MB) chegou a **39.862 quadros em ~37 min (≈18 quadros/s)**, com 17.694 itens na fila:
com cota, o `LocalDiskStorage.usage()` percorria a pasta inteira a cada leitura de saúde.
Corrigido (medida em cache de 10 s, por `scandir`; a limpeza mede na hora) e a execução
recomeçou do zero.

Testes em tamanho de CI: `rover/tests/test_estresse.py` (400 passos com tudo acima; 300
passos com disco de 1,5 MB, que força `STORAGE_PRESSURE` e confere que **nenhum original
de evento não enviado foi apagado**).

## 2. Seis Rovers de dois clientes em paralelo contra a API (`saas/tests/test_estresse_frota.py`)

Seis `rover/` reais (3 por cliente), cada um numa thread, 60 passos × 2 câmeras, cada um
com a rede caindo numa janela diferente, sincronizando **ao mesmo tempo** contra a API
real (SQLite). Resultado: **1.014 registros e 864 arquivos**, cada robô com exatamente os
seus registros e arquivos no servidor, nenhum duplicado; cada cliente lê só os registros
dos próprios robôs; 28,8 s.

Esse teste achou **duas corridas reais** no servidor, corrigidas: dois envios simultâneos
do mesmo conteúdo disputavam o mesmo `.part` no `LocalObjectStore` (agora o temporário
tem nome único) e a mesma linha de `asset` (agora com *savepoint*: quem perde a corrida
fica deduplicado).

## 3. Volume (Parte 4, `rover/tests/test_retention.py`)

10.000 quadros 1280×960 com 2 % de eventos: enviar tudo seria **6,04 GB**; com a política
padrão, **565 MB (9,4 %)**; com NORMAL só em metadados, **385 MB (6,4 %)**.

## Outros cenários da seção 42 e onde estão

| Cenário | Onde |
| --- | --- |
| modelo inválido (hash diferente, arquivo que não carrega) | `rover/tests/test_model_manager.py`, `test_ota.py::test_modelo_que_nao_carrega_*` |
| atualização interrompida e assinatura inválida | `rover/tests/test_ota.py`, `saas/tests/test_ota.py` (com o `rover/` real) |
| backend indisponível (`503`, `429`, `500`) e `403` | estresse acima; `rover/tests/test_sync.py` |
| robô reiniciado e missão interrompida | estresse acima; `test_runtime.py`; ponta a ponta (passo 15) |
| upload retomado do ponto em que caiu | `test_sync.py::test_queda_em_70_por_cento_retoma_de_70`, `saas/tests/test_rover_integracao.py` |

## O que não foi medido

Postgres sob carga concorrente (o estresse de frota roda em SQLite; a suíte inteira roda
no Postgres, mas sequencial), várias réplicas da API, rede real (latência/perda de pacote)
e hardware embarcado (Jetson etc.).
