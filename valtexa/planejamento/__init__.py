"""Planejamento de apoio à decisão (brief 8.3): fitossanitário, robótico e de insumos.

O agente **propõe**: cada plano sai com as **premissas registradas** (todo número que não
foi medido diz de onde veio: ``padrao``, ``pedido``, ``medido``, ``cadastro`` ou
``simulado``), o resultado e o ``sha256``, e espera a **revisão humana** (aceito, recusado,
ajustar). Nenhum plano cria missão, aprova prescrição ou aplicação, ou muda limiar de modelo
— quem age é a pessoa, pelos fluxos de sempre, e quem libera é o Safety Engine
(Princípio de Ouro; ``tests/test_principio_de_ouro.py`` prova varrendo o código e o banco).

* :mod:`.fitossanitario` — fila de casos para revisão (risco x incerteza x impacto),
  comparação do histórico de sintomas (lesões persistentes e novas), regiões prioritárias
  do gêmeo, alternativas de manejo e rotação de ingredientes ativos por modo de ação **só**
  com produto cadastrado com fonte e registro vigente;
* :mod:`.robotico` — o alocador do enxame com inclinação, obstáculos e o orçamento de dados
  da Starlink de cada Rover como restrições;
* :mod:`.insumos` — demanda a partir do histórico de aplicações, em cenários com intervalo
  (bootstrap por blocos), e a possível reposição. Sem histórico, diz que não dá.
"""
