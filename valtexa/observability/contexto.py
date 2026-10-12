"""Contexto da requisição para os logs: id da requisição, cliente, usuário, robô.

O *middleware* HTTP abre o contexto (com o ``request_id``) e as dependências de
autenticação o completam quando descobrem quem chama. O valor guardado na
``ContextVar`` é um **dicionário mutável**, e não valores soltos, por causa de um
detalhe do FastAPI: dependência e rota síncronas rodam numa *threadpool* com uma
**cópia** do contexto — um ``ContextVar.set`` lá dentro não voltaria para o
*middleware*, mas a mutação do mesmo dicionário volta.
"""

from __future__ import annotations

import re
import uuid
from contextvars import ContextVar, Token

CAMPOS = ("request_id", "tenant_id", "user_id", "device_id", "support_session_id")

_contexto: ContextVar[dict[str, str] | None] = ContextVar("valtexa_contexto", default=None)

_ID_ACEITO = re.compile(r"^[A-Za-z0-9._-]{8,64}$")


def novo_request_id(recebido: str | None = None) -> str:
    """Reaproveita o ``X-Request-Id`` do balanceador se ele for sensato; senão gera um.

    Sensato = 8 a 64 caracteres seguros. Qualquer outra coisa é ignorada: o valor
    vai para o log e para o cabeçalho de resposta, e não pode carregar quebra de
    linha nem texto arbitrário de quem chama.
    """
    if recebido and _ID_ACEITO.match(recebido):
        return recebido
    return uuid.uuid4().hex


def abrir(request_id: str) -> Token:
    return _contexto.set({"request_id": request_id})


def fechar(token: Token) -> None:
    _contexto.reset(token)


def anotar(**campos: str | None) -> None:
    """Acrescenta ao contexto corrente (fora de requisição, não faz nada)."""
    atual = _contexto.get()
    if atual is None:
        return
    for chave, valor in campos.items():
        if chave not in CAMPOS:
            raise ValueError(f"Campo de contexto desconhecido: {chave!r}")
        if valor:
            atual[chave] = str(valor)


def atual() -> dict[str, str]:
    return dict(_contexto.get() or {})


__all__ = ["CAMPOS", "abrir", "anotar", "atual", "fechar", "novo_request_id"]
