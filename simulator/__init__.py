"""Frota simulada.

Existe para que a plataforma possa ser exercitada — e testada — antes de haver
qualquer hardware. Quando o rover e o drone físicos chegarem, eles substituem
:mod:`simulator.devices` implementando o mesmo protocolo; a nuvem não muda.

``simulator.client`` é a referência executável do protocolo: quem escrever o
firmware reproduz o que está lá.
"""
