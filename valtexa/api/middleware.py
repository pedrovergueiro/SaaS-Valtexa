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

**Teto** (Parte 9, seção 43): o buffer acontece *antes* da autenticação — sem
limite, qualquer um mandava gigabytes a ``/v1/device/...`` e a réplica estourava
a memória. Acima de ``max_body_bytes`` a resposta é 413, sem ler o resto.

:class:`CabecalhosDeSeguranca` põe em toda resposta os cabeçalhos que impedem o
navegador de adivinhar tipo de arquivo e de embutir a API num ``<iframe>``.

:class:`ReciboDoDispositivo` (Parte 13) assina a resposta das rotas do dispositivo que
**mudam estado** quando o robô pede (``X-Valtexa-Recibo: 1``): um intermediário não
consegue fingir um "aceito" e fazer o robô apagar o que ainda não chegou. Foi feito para a
base da fazenda; com a base arquivada (20/10/2026, cada Rover fala direto pela Starlink) não
há hoje quem peça o recibo — o controle fica, opcional e sem custo quando não pedido.
"""

from __future__ import annotations

import hashlib
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

    def __init__(self, app: Callable, prefixes: tuple[str, ...] = ("/v1/device",),
                 max_body_bytes: int | None = None) -> None:
        self.app = app
        self.prefixes = prefixes
        if max_body_bytes is None:
            from valtexa.config import settings

            # O maior corpo legítimo é um arquivo inteiro em multipart (observação,
            # nuvem de pontos): o limite do arquivo mais 1 MB de cabeçalhos e metadados.
            max_body_bytes = settings.max_asset_bytes + 1024 * 1024
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not self._should_buffer(scope):
            await self.app(scope, receive, send)
            return

        declarado = dict(scope.get("headers") or []).get(b"content-length")
        if declarado is not None and declarado.isdigit() and \
                int(declarado) > self.max_body_bytes:
            await _grande_demais(send, self.max_body_bytes)
            return

        chunks: list[bytes] = []
        recebido = 0
        while True:
            message = await receive()
            if message["type"] != "http.request":
                # Cliente desconectou no meio do envio; nada a reproduzir.
                await self.app(scope, receive, send)
                return
            pedaco = message.get("body", b"")
            recebido += len(pedaco)
            if recebido > self.max_body_bytes:
                # Content-Length ausente ou mentiroso: para de ler aqui.
                await _grande_demais(send, self.max_body_bytes)
                return
            chunks.append(pedaco)
            if not message.get("more_body", False):
                break

        body = b"".join(chunks)
        scope[RAW_BODY_KEY] = body
        cabecalhos = list(scope.get("headers") or [])
        if dict(cabecalhos).get(b"content-encoding", b"").lower() == b"gzip":
            # O robô comprime o lote (Starlink medida, rodada 4). A assinatura confere os bytes
            # que trafegaram (RAW_BODY_KEY, comprimidos); a rota recebe o JSON descomprimido.
            aberto = _descomprime(body, self.max_body_bytes)
            if aberto is None:
                await _gzip_invalido(send)
                return
            scope["headers"] = [(k, v) for k, v in cabecalhos
                                if k not in (b"content-encoding", b"content-length")] + [
                (b"content-length", str(len(aberto)).encode())]
            body = aberto
        await self.app(scope, _replay(body), send)

    def _should_buffer(self, scope: Scope) -> bool:
        path = scope.get("path", "")
        return any(path.startswith(prefix) for prefix in self.prefixes)


def _descomprime(body: bytes, limite: int) -> bytes | None:
    """gzip com teto no tamanho aberto (bomba de descompressão não passa). ``None``: inválido."""
    import zlib

    d = zlib.decompressobj(16 + zlib.MAX_WBITS)
    try:
        aberto = d.decompress(body, limite + 1)
    except zlib.error:
        return None
    if len(aberto) > limite or d.unconsumed_tail or not d.eof:
        return None
    return aberto


async def _gzip_invalido(send: Send) -> None:
    corpo = b'{"detail":"Corpo gzip inv\xc3\xa1lido ou grande demais depois de aberto."}'
    await send({"type": "http.response.start", "status": 400,
                "headers": [(b"content-type", b"application/json"),
                            (b"content-length", str(len(corpo)).encode())]})
    await send({"type": "http.response.body", "body": corpo})


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


async def _grande_demais(send: Send, limite: int) -> None:
    mb = limite // (1024 * 1024)
    corpo = (
        f'{{"detail":"Corpo maior que o limite de {mb} MB para rotas do dispositivo."}}'
    ).encode()
    await send({"type": "http.response.start", "status": 413,
                "headers": [(b"content-type", b"application/json"),
                            (b"content-length", str(len(corpo)).encode()),
                            (b"connection", b"close")]})
    await send({"type": "http.response.body", "body": corpo})


CABECALHOS_DE_SEGURANCA = (
    # O navegador respeita o Content-Type declarado: nada de "adivinhar" que uma
    # imagem enviada por um robô é HTML.
    (b"x-content-type-options", b"nosniff"),
    # A API e o console não são embutidos em <iframe> de outro site (clickjacking).
    (b"x-frame-options", b"DENY"),
    (b"referrer-policy", b"strict-origin-when-cross-origin"),
)


class CabecalhosDeSeguranca:
    """Acrescenta :data:`CABECALHOS_DE_SEGURANCA` a toda resposta HTTP que não os tenha.

    HSTS fica no proxy TLS (``docs/DEPLOY.md``): só ele sabe se a conexão é HTTPS.
    """

    def __init__(self, app: Callable) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def enviar(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers") or [])
                presentes = {nome.lower() for nome, _ in headers}
                headers.extend(h for h in CABECALHOS_DE_SEGURANCA if h[0] not in presentes)
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, enviar)


RECIBO_ALGORITMO = "VALTEXA-ED25519-RECIBO-V1"
RECIBO_PEDIDO = b"x-valtexa-recibo"
RECIBO_CABECALHO = b"x-valtexa-recibo-assinatura"


def texto_do_recibo(nonce: str, status: int, corpo: bytes) -> bytes:
    """O que a plataforma assina: o nonce **deste** pedido, o status e o hash do corpo.

    Prefixo próprio: uma assinatura de recibo nunca vale como assinatura de comando.
    """
    return (f"{RECIBO_ALGORITMO}\n{nonce}\n{int(status)}\n"
            f"{hashlib.sha256(corpo).hexdigest()}").encode()


class ReciboDoDispositivo:
    """Recibo assinado (chave da plataforma) das respostas a ``POST``/``PUT``/``PATCH``/
    ``DELETE`` em ``/v1/device/**``, só quando o pedido traz ``X-Valtexa-Recibo``.

    O recibo amarra a resposta ao ``X-Valtexa-Nonce`` do pedido (único, assinado pelo robô):
    um intermediário (era a base da fazenda) não fabrica um "200 aceito" nem reaproveita o
    recibo de outro pedido. ``GET`` não precisa: o que importa nele (missão, comando,
    teleop) já vem em envelope assinado. Resposta sem pedido de recibo: nada muda.
    """

    def __init__(self, app: Callable, prefixo: str = "/v1/device/") -> None:
        self.app = app
        self.prefixo = prefixo

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (scope["type"] != "http" or scope.get("method") in ("GET", "HEAD", "OPTIONS")
                or not scope.get("path", "").startswith(self.prefixo)):
            await self.app(scope, receive, send)
            return
        cab = dict(scope.get("headers") or [])
        nonce = cab.get(b"x-valtexa-nonce")
        if RECIBO_PEDIDO not in cab or not nonce:
            await self.app(scope, receive, send)
            return
        inicio: Message | None = None
        partes: list[bytes] = []

        async def enviar(message: Message) -> None:
            nonlocal inicio
            if message["type"] == "http.response.start":
                inicio = message
                return
            if message["type"] != "http.response.body" or inicio is None:
                await send(message)
                return
            partes.append(message.get("body", b""))
            if message.get("more_body", False):
                return
            from valtexa.security import signing

            corpo = b"".join(partes)
            assinatura = signing.platform_private_key().sign(
                texto_do_recibo(nonce.decode("latin-1"), inicio["status"], corpo)).hex()
            headers = [(n, v) for n, v in (inicio.get("headers") or [])
                       if n.lower() != RECIBO_CABECALHO]
            headers.append((RECIBO_CABECALHO, assinatura.encode()))
            await send({**inicio, "headers": headers})
            await send({"type": "http.response.body", "body": corpo, "more_body": False})

        await self.app(scope, receive, enviar)
