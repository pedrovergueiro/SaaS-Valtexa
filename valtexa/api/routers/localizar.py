"""Achar a fazenda no mapa: busca por endereço e o satélite do console.

Qualquer pessoa logada (produtor desenhando o talhão dele, equipe cadastrando um
cliente) usa. Ver :mod:`valtexa.services.localizar`.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from valtexa.api.deps import current_user_ou_suporte
from valtexa.models import User
from valtexa.services import localizar

router = APIRouter(prefix="/mapa", tags=["mapa"])

POR_MINUTO = 30
"""Busca por pessoa por minuto: digitar e apagar não esgota a cota do geocodificador."""
_buscas: dict[str, deque[float]] = defaultdict(deque)


def _limite(user_id: str) -> None:
    agora = time.monotonic()
    fila = _buscas[user_id]
    while fila and agora - fila[0] > 60:
        fila.popleft()
    if len(fila) >= POR_MINUTO:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                            "Muitas buscas em um minuto. Espere um pouco.")
    fila.append(agora)


@router.get("/localizar", summary="Acha um lugar pelo endereço (fazenda, cidade, estrada)")
def busca(q: str = Query(min_length=3, max_length=localizar.MAX_TEXTO),
          user: User = Depends(current_user_ou_suporte)) -> dict[str, Any]:
    _limite(user.id)
    try:
        lugares, avisos = localizar.procura(q)
    except localizar.LocalizarIndisponivelError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
    return {"lugares": [lugar.as_dict() for lugar in lugares], "avisos": avisos}


@router.get("/satelite", summary="Qual satélite o console usa (Google quando ligado, se não Esri)")
def satelite(user: User = Depends(current_user_ou_suporte)) -> dict[str, Any]:
    return localizar.satelite()
