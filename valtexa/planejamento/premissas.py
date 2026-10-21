"""As premissas de um plano: o que foi suposto, com que valor e de onde veio."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

ORIGENS = ("padrao", "pedido", "medido", "cadastro", "simulado")
"""* ``padrao`` — valor padrão da plataforma, **não medido**: ajuste antes de confiar;
* ``pedido`` — veio de quem pediu o plano;
* ``medido`` — lido do banco ou do Rover (telemetria, histórico);
* ``cadastro`` — do cadastro (produto, talhão, dispositivo);
* ``simulado`` — saiu de uma simulação (``VALTEXA-ROVER/docs/ROVER_RUNTIME.md``), não de campo."""


@dataclass
class Premissas:
    itens: list[dict[str, Any]] = field(default_factory=list)

    def anota(self, codigo: str, texto: str, valor: Any = None, origem: str = "padrao") -> Any:
        if origem not in ORIGENS:
            raise ValueError(f"origem de premissa desconhecida: {origem!r}")
        self.itens = [p for p in self.itens if p["codigo"] != codigo]
        self.itens.append({"codigo": codigo, "texto": texto, "valor": valor, "origem": origem})
        return valor

    def valor(self, codigo: str, pedido: Any, padrao: Any, texto: str,
              origem_padrao: str = "padrao") -> Any:
        """O valor do pedido, se veio; senão o padrão — e anota de onde saiu."""
        if pedido is not None:
            return self.anota(codigo, texto, pedido, "pedido")
        return self.anota(codigo, texto, padrao, origem_padrao)

    def lista(self) -> list[dict[str, Any]]:
        return sorted(self.itens, key=lambda p: p["codigo"])
