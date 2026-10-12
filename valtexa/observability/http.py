"""Medição de toda requisição HTTP: latência por rota, status, erros e ``request_id``.

Um *middleware* ASGI puro (não ``BaseHTTPMiddleware``): não toca no corpo, não
atrasa *streaming* e vê a exceção que escapa da rota. Para cada requisição:

1. abre o contexto de log com o ``request_id`` (o do balanceador, se sensato) e o
   devolve no cabeçalho ``X-Request-Id``;
2. mede a duração e registra, por **molde de rota** (``/v1/missions/{mission_id}``)
   — o caminho com id explodiria a cardinalidade —, nas métricas do processo
   (Prometheus) e na :class:`JanelaApi` (por minuto, descarregada no banco);
3. escreve uma linha de *access log* estruturada com cliente, usuário e status.

Exceção não tratada conta como 500 aqui e segue para o tratador do FastAPI (que
fica do lado de fora deste *middleware* e responde o JSON com o código de erro).
"""

from __future__ import annotations

import logging
import os
import socket
import threading
from collections.abc import Awaitable, Callable, MutableMapping
from datetime import UTC, datetime
from time import perf_counter
from typing import Any

from starlette.datastructures import MutableHeaders

from valtexa.observability import contexto
from valtexa.observability.metricas import Registro

logger = logging.getLogger("valtexa.http")

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]

REQUEST_ID_KEY = "valtexa.request_id"
"""Onde o ``request_id`` fica no ``scope`` (o tratador de erro do FastAPI o lê de lá)."""

SEM_ROTA = "nao_mapeada"
"""Molde das requisições que não casaram com rota nenhuma (404 de caminho)."""

LIMITES_MS: tuple[float, ...] = (5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000)

SILENCIOSAS = frozenset({"/health", "/metrics"})
"""Rotas raspadas a cada poucos segundos: o *access log* delas vai em DEBUG."""


def instancia() -> str:
    """Quem mediu (esta réplica). Aparece nas linhas descarregadas no banco."""
    return f"{socket.gethostname()}:{os.getpid()}"[:64]


REGISTRO = Registro()
REQUISICOES = REGISTRO.contador(
    "valtexa_http_requests_total", "Requisições HTTP atendidas por esta réplica.",
    ("method", "route", "status"),
)
DURACAO = REGISTRO.histograma(
    "valtexa_http_request_duration_seconds", "Duração das requisições HTTP (segundos).",
    ("method", "route"),
)
ERROS = REGISTRO.contador(
    "valtexa_http_server_errors_total", "Respostas 5xx (inclui exceção não tratada).",
    ("method", "route"),
)
EM_ANDAMENTO = REGISTRO.medidor(
    "valtexa_http_requests_in_progress", "Requisições sendo atendidas agora."
)
INICIO = REGISTRO.medidor(
    "valtexa_process_start_time_seconds", "Quando este processo subiu (epoch, segundos)."
)
INICIO.set(datetime.now(UTC).timestamp())


class JanelaApi:
    """Acumula por (minuto, método, rota, classe de status) até a próxima descarga.

    Guardar só deltas mantém a memória limitada (≈ rotas vezes status vezes minutos desde a
    última descarga) e torna a descarga idempotente por construção: o que saiu
    daqui não volta a sair.
    """

    def __init__(self) -> None:
        self._dados: dict[tuple[datetime, str, str, str], list[float]] = {}
        self._trava = threading.Lock()

    def registrar(self, method: str, route: str, status: int, duracao_ms: float,
                  quando: datetime | None = None) -> None:
        minuto = (quando or datetime.now(UTC)).replace(second=0, microsecond=0)
        chave = (minuto, method, route, f"{status // 100}xx")
        with self._trava:
            d = self._dados.setdefault(chave, [0, 0, 0.0, 0.0] + [0] * (len(LIMITES_MS) + 1))
            d[0] += 1
            d[1] += 1 if status >= 500 else 0
            d[2] += duracao_ms
            d[3] = max(d[3], duracao_ms)
            for i, limite in enumerate(LIMITES_MS):
                if duracao_ms <= limite:
                    d[4 + i] += 1
                    break
            else:
                d[4 + len(LIMITES_MS)] += 1

    def retirar(self) -> dict[tuple[datetime, str, str, str], list[float]]:
        with self._trava:
            dados, self._dados = self._dados, {}
        return dados

    def devolver(self, dados: dict[tuple[datetime, str, str, str], list[float]]) -> None:
        """Põe de volta o que não conseguiu ser gravado (o banco estava fora)."""
        with self._trava:
            for chave, v in dados.items():
                d = self._dados.setdefault(chave, [0, 0, 0.0, 0.0] + [0] * (len(LIMITES_MS) + 1))
                d[0] += v[0]
                d[1] += v[1]
                d[2] += v[2]
                d[3] = max(d[3], v[3])
                for i in range(4, len(d)):
                    d[i] += v[i]

    def __len__(self) -> int:
        return len(self._dados)


JANELA = JanelaApi()


def molde_da_rota(scope: Scope) -> str:
    """``/v1/fields/{field_id}`` — o molde completo, com o prefixo do roteador.

    O FastAPI guarda na rota o caminho **relativo ao roteador** (``/fields/{field_id}``)
    e o prefixo com que foi incluído fica fora dela. O prefixo é estático, então sai
    do caminho real: tira-se o pedaço que a rota casou (o molde preenchido com os
    parâmetros) e o que sobra na frente é o prefixo.
    """
    rota = scope.get("route")
    molde = getattr(rota, "path_format", None) or getattr(rota, "path", None)
    if not molde:
        return SEM_ROTA
    molde = str(molde)
    caminho = str(scope.get("path", ""))
    try:
        concreto = molde.format(**dict(scope.get("path_params") or {}))
    except (KeyError, IndexError, ValueError):
        concreto = None
    if concreto and caminho.endswith(concreto):
        return (caminho[: len(caminho) - len(concreto)] + molde)[:200]
    return molde[:200]


class ObservabilidadeMiddleware:
    def __init__(self, app: Callable) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        recebido = None
        for nome, valor in scope.get("headers") or ():
            if nome == b"x-request-id":
                recebido = valor.decode("latin-1")
                break
        request_id = contexto.novo_request_id(recebido)
        scope[REQUEST_ID_KEY] = request_id
        token = contexto.abrir(request_id)
        status = {"code": 500}

        async def enviar(message: Message) -> None:
            if message["type"] == "http.response.start":
                status["code"] = int(message["status"])
                MutableHeaders(scope=message).append("X-Request-Id", request_id)
            await send(message)

        inicio = perf_counter()
        EM_ANDAMENTO.inc()
        try:
            await self.app(scope, receive, enviar)
        except Exception:
            status["code"] = 500
            raise
        finally:
            EM_ANDAMENTO.inc(-1)
            duracao = perf_counter() - inicio
            self._registra(scope, status["code"], duracao)
            contexto.fechar(token)

    @staticmethod
    def _registra(scope: Scope, status: int, duracao_s: float) -> None:
        method = str(scope.get("method", "GET"))[:8]
        rota = molde_da_rota(scope)
        REQUISICOES.inc(method=method, route=rota, status=str(status))
        DURACAO.observe(duracao_s, method=method, route=rota)
        if status >= 500:
            ERROS.inc(method=method, route=rota)
        JANELA.registrar(method, rota, status, duracao_s * 1000)
        caminho = str(scope.get("path", ""))
        nivel = logging.DEBUG if caminho in SILENCIOSAS and status < 500 else logging.INFO
        if status >= 500:
            nivel = logging.WARNING
        logger.log(
            nivel, "%s %s -> %d (%.1f ms)", method, caminho, status, duracao_s * 1000,
            extra={"campos": {"method": method, "route": rota, "status": status,
                              "duration_ms": round(duracao_s * 1000, 2)}},
        )


__all__ = [
    "DURACAO",
    "ERROS",
    "JANELA",
    "LIMITES_MS",
    "REGISTRO",
    "REQUEST_ID_KEY",
    "REQUISICOES",
    "SEM_ROTA",
    "JanelaApi",
    "ObservabilidadeMiddleware",
    "instancia",
    "molde_da_rota",
]
