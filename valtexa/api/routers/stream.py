"""Fluxo de eventos ao vivo para o console, por *Server-Sent Events*.

O console já sabia ouvir isto: ``web/src/lib/stream.ts`` reconecta, recua
exponencialmente e transforma evento crítico em aviso na tela. O que faltava era
o outro lado — a rota não existia, então a cada tentativa o console levava um
404 e voltava a consultar de quinze em quinze segundos. Este módulo é a metade
que faltava, e por isso segue o contrato que o cliente já espera (``after``,
``timeout``, ``created_at``, ``stream.end``) em vez de inventar o seu.

Quinze segundos é muito tempo olhando uma tela que diz "em curso" para uma
máquina que já parou na lavoura, e é tempo demais para uma parada de emergência.

**O que isto é, com precisão:** o servidor consulta o *outbox* — a mesma tabela
onde toda mudança de estado já era gravada, na transação que a causou — e empurra
o que for novo. Não há notificação do banco para a aplicação; há uma consulta por
índice, feita uma vez por conexão em vez de uma vez por tela aberta. A diferença
que importa para quem usa é a latência; a que importa para o servidor é não
repetir o dashboard inteiro a cada ciclo.

**Escala:** uma conexão por aba. Com muitos clientes por réplica, o caminho é
trocar a consulta por ``LISTEN/NOTIFY`` no Postgres sem mexer neste contrato.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from valtexa.api.deps import Principal, require
from valtexa.config import settings
from valtexa.db import session_scope
from valtexa.models import OutboxEvent
from valtexa.security import rbac

logger = logging.getLogger(__name__)

router = APIRouter(tags=["tempo real"])

RECONEXAO_MS = 3000
"""Quanto o cliente espera antes de reconectar, em milissegundos.

Vai no quadro ``retry:``, que é campo de protocolo SSE — o navegador o guarda e
o aplica sozinho. Três segundos é o que ``docs/API.md`` promete, e o contrato
escrito é o que vale: um cliente que já leu a documentação não deve descobrir
outro número no fio.
"""

BATIMENTO_S = 15
"""Intervalo do comentário de keep-alive, em segundos.

Quinze porque é o menor dos tempos de ociosidade que proxies costumam impor.
Uma conexão derrubada em silêncio é pior do que não ter conexão, porque a tela
continua parecendo ao vivo.
"""

_conectados = 0
"""Conexões abertas nesta réplica.

Um inteiro de módulo basta porque só o *event loop* mexe nele, e o *event loop*
é um só por processo — não há corrida a proteger. Com mais de uma réplica, cada
uma conta as suas, que é o que o limite quer medir: quantas conexões **este**
processo aguenta.
"""


def _sse(evento: str, dados: dict, *, ident: str | None = None) -> str:
    """Formata um quadro SSE."""
    linhas = []
    if ident:
        linhas.append(f"id: {ident}")
    linhas.append(f"event: {evento}")
    linhas.append(f"data: {json.dumps(dados, default=str, ensure_ascii=False)}")
    return "\n".join(linhas) + "\n\n"


def _novos(tenant_id: str, depois: datetime, limite: int = 200) -> list[dict]:
    """Eventos do cliente gravados depois de ``depois``.

    Sessão própria, aberta e fechada a cada ciclo, e não uma presa à conexão: uma
    sessão de minutos seguraria uma transação de minutos, e no Postgres isso
    atrapalha o ``VACUUM`` da tabela inteira.
    """
    with session_scope() as sessao:
        linhas = sessao.scalars(
            select(OutboxEvent)
            .where(OutboxEvent.tenant_id == tenant_id, OutboxEvent.created_at > depois)
            .order_by(OutboxEvent.created_at)
            .limit(limite)
        ).all()
        return [
            {
                "id": linha.id,
                "name": linha.name,
                "subject_type": str(linha.subject_type) if linha.subject_type else None,
                "subject_id": linha.subject_id,
                "payload": linha.payload,
                # `created_at` e não `at`: é o nome que o console lê para saber
                # de onde retomar na reconexão.
                "created_at": linha.created_at.isoformat(),
            }
            for linha in linhas
        ]


async def _fluxo(tenant_id: str, depois: datetime, duracao_s: int) -> AsyncIterator[str]:
    global _conectados
    _conectados += 1
    limite = datetime.now(UTC) + timedelta(seconds=duracao_s)
    try:
        # `retry` diz ao cliente quanto esperar antes de voltar. Vai primeiro e
        # uma vez só: é campo de protocolo, não evento, e o cliente o guarda.
        yield f"retry: {RECONEXAO_MS}\n\n"

        ultimo_batimento = datetime.now(UTC)
        while datetime.now(UTC) < limite:
            # Consulta direta, e não `asyncio.to_thread`: a busca é por índice e
            # custa cerca de um milissegundo, enquanto o pool de threads padrão
            # do asyncio tem uma dúzia de lugares. Com duzentas conexões pedindo
            # uma thread por segundo, elas disputariam essas doze — cada uma
            # segurando uma conexão do banco enquanto espera — e o resultado
            # seria pior que o milissegundo de loop bloqueado que se queria
            # evitar.
            eventos = _novos(tenant_id, depois)
            for evento in eventos:
                depois = datetime.fromisoformat(evento["created_at"])
                yield _sse(evento["name"], evento, ident=evento["id"])

            agora = datetime.now(UTC)
            if not eventos and (agora - ultimo_batimento).total_seconds() >= BATIMENTO_S:
                # Comentário SSE: atravessa proxy sem virar evento na aplicação.
                # É o que impede um balanceador de derrubar a conexão por
                # ociosidade — e uma conexão derrubada em silêncio é pior do que
                # não ter conexão, porque a tela continua parecendo ao vivo.
                ultimo_batimento = agora
                yield ": keepalive\n\n"

            await asyncio.sleep(settings.stream_poll_seconds)

        # Fim de turno. O `after` vai junto para que a reconexão comece
        # exatamente onde esta parou: sem ele, o console teria que escolher entre
        # repetir eventos e perder os do intervalo entre fechar e abrir.
        yield _sse("stream.end", {"after": depois.isoformat(), "reason": "limite de duração"})
    finally:
        _conectados -= 1


@router.get(
    "/stream",
    summary="Eventos ao vivo do cliente (SSE)",
    response_class=StreamingResponse,
)
async def stream(
    after: datetime | None = Query(
        default=None,
        description=(
            "Só eventos posteriores a este instante. O console manda aqui o "
            "horário do último evento que já mostrou, e é o que evita repetir a "
            "tela inteira ao reconectar."
        ),
    ),
    timeout: int = Query(
        default=0,
        ge=0,
        description=(
            "Quantos segundos manter a conexão antes de pedir reconexão. Zero "
            "usa o padrão do servidor. Limitado por STREAM_MAX_SECONDS: o "
            "cliente pede, o servidor decide."
        ),
    ),
    principal: Principal = Depends(require(rbac.TENANT_READ)),
) -> StreamingResponse:
    """Abre um fluxo de eventos do cliente em que o usuário está.

    O escopo é o tenant do token, e não um parâmetro: um cliente não recebe nem
    de raspão o evento de outro. É a mesma regra do resto da plataforma, e num
    fluxo aberto ela importa ainda mais — aqui o servidor fala sem ser
    perguntado, então o filtro errado vaza continuamente em vez de uma vez.
    """
    if _conectados >= settings.stream_max_clients:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Muitas conexões ao vivo abertas neste servidor. Tente de novo em instantes.",
        )

    depois = after or datetime.now(UTC)
    if depois.tzinfo is None:
        depois = depois.replace(tzinfo=UTC)
    duracao = min(timeout or settings.stream_max_seconds, settings.stream_max_seconds)

    return StreamingResponse(
        _fluxo(principal.tenant_id, depois, duracao),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            # Sem isto, o nginx em frente segura os quadros num buffer e entrega
            # tudo junto no fim — o que transforma tempo real em lote.
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
