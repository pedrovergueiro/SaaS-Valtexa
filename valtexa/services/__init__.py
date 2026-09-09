"""Serviços de domínio.

Cada módulo tem uma responsabilidade e uma direção de dependência declarada. A
mais importante: :mod:`safety_engine` não importa :mod:`decision_engine`. A
segurança precisa continuar íntegra se a regra agronômica estiver errada, então
a dependência é deliberadamente unilateral.
"""
