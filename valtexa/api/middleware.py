"""Buffer do corpo bruto, para a verificação de assinatura.

O problema, que é sutil e caro de descobrir tarde: a assinatura do dispositivo
cobre o corpo da requisição, então a dependência de autenticação precisa dos
bytes **exatos** que chegaram. Só que o FastAPI consome o corpo antes de
resolver as dependências — ele precisa dele para construir os parâmetros da
rota. Quando a dependência é chamada, o fluxo já acabou, e um segundo
``await request.body()`` levanta ``RuntimeError: Stream consumed``.

Ler o corpo num ``BaseHTTPMiddleware`` não resolve: consumiria o fluxo original
e a rota receberia um corpo vazio. A solução correta é no nível do ASGI —
acumular as mensagens e entregar um ``receive`` novo que as reproduz.

O buffer é aplicado **apenas** ao prefixo do dispositivo. Segurar em memória o
corpo de toda requisição custaria caro num upload de imagem sem nenhum ganho:
nenhuma outra rota verifica assinatura.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]

RAW_BODY_KEY = "valtexa.raw_body"
"""Chave no ``scope`` onde o corpo bruto fica disponível para a dependência."""


class RawBodyMiddleware:
    """Middleware ASGI que preserva o corpo original das rotas de dispositivo."""

    def __init__(self, app: Callable, prefixes: tuple[str, ...] = ("/v1/device",)) -> None:
        self.app = app
        self.prefixes = prefixes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not self._should_buffer(scope):
            await self.app(scope, receive, send)
            return

        chunks: list[bytes] = []
        while True:
            message = await receive()
            if message["type"] != "http.request":
                # Cliente desconectou no meio do envio; nada a reproduzir.
                await self.app(scope, receive, send)
                return
            chunks.append(message.get("body", b""))
            if not message.get("more_body", False):
                break

        body = b"".join(chunks)
        scope[RAW_BODY_KEY] = body
        await self.app(scope, _replay(body), send)

    def _should_buffer(self, scope: Scope) -> bool:
        path = scope.get("path", "")
        return any(path.startswith(prefix) for prefix in self.prefixes)


def _replay(body: bytes) -> Receive:
    """Devolve um ``receive`` que entrega o corpo guardado uma vez.

    Depois disso responde ``http.disconnect``, que é o que o protocolo ASGI
    espera quando não há mais nada a ler — devolver o corpo repetidamente faria
    um parser mal-comportado entrar em laço.
    """
    delivered = False

    async def receive() -> Message:
        nonlocal delivered
        if not delivered:
            delivered = True
            return {"type": "http.request", "body": body, "more_body": False}
        return {"type": "http.disconnect"}

    return receive
