"""Cérebro agronômico neuro-simbólico (brief 8.1 e 8.2). Ver ``docs/CEREBRO.md``.

O caminho de um parecer, do dado ao texto:

1. :mod:`~valtexa.cerebro.conhecimento` — o repositório de fontes versionadas (ingestão
   por arquivo, versões, regra do regulatório vencido ou não verificado);
2. :mod:`~valtexa.cerebro.rag` — a recuperação local (BM25 com filtros por cultura, alvo e
   tipo), sem chamada externa, com citação rastreável ao trecho;
3. :mod:`~valtexa.cerebro.dossie` — o dossiê de evidências do caso (planta ou observação):
   cada item com origem, versão do modelo e limitações;
4. :mod:`~valtexa.cerebro.parecer` — o compositor **determinístico** (o padrão) e as
   verificações que faltam antes de qualquer intervenção;
5. :mod:`~valtexa.cerebro.provedor` e :mod:`~valtexa.cerebro.validador` — o modelo de
   linguagem/visão plugável, **desligado por padrão**, e o validador que recusa o texto dele
   quando afirma sem citação, inventa número ou fala em certeza;
6. :mod:`~valtexa.cerebro.servico` — gerar, consultar e revisar, com auditoria.

**Princípio de Ouro** (8.4): nada daqui cria missão, aprova prescrição ou aplicação, muda
limiar de modelo ou chama o Safety Engine. O teste ``tests/test_cerebro_principio.py``
varre os módulos e as rotas para provar.
"""
