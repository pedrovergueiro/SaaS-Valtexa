"""Sessões de usuário: abrir, conferir, derrubar.

O token de sessão é *bearer* — quem o tem, é. Isso o torna prático e o torna
perigoso pela mesma razão: nada nele pode ser desdito depois de emitido. Este
módulo dá ao servidor a última palavra, guardando uma linha por sessão aberta e
conferindo-a a cada requisição.

O custo é uma consulta por chamada autenticada. É o preço de poder responder
"esta sessão acabou **agora**" em vez de "acaba em algumas horas" — e algumas
horas é tempo demais quando o motivo é um notebook roubado ou alguém demitido.

Nada aqui guarda o token. A linha guarda o bastante para a pessoa se reconhecer
na lista e decidir o que derrubar; guardar o token seria fazer uma segunda cópia
da credencial e deixá-la no banco esperando vazamento.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from valtexa.models import ActorType, SubjectType, UserSession
from valtexa.security import tokens
from valtexa.services import audit

INTERVALO_DE_PRESENCA = timedelta(minutes=5)
"""Quanto tempo se deixa passar antes de reescrever ``last_seen_at``.

Atualizar a cada requisição transformaria toda leitura numa escrita — e, com o
SQLite do piloto, cada escrita disputa o mesmo arquivo com a ingestão de
telemetria. O que a pessoa precisa ler na lista é "hoje de manhã", não "há três
segundos", então cinco minutos de imprecisão não custam nada e cortam quase
todas as escritas.
"""


def abrir(
    session: Session,
    *,
    user_id: str,
    tenant_id: str | None,
    user_agent: str | None = None,
    ip_address: str | None = None,
    ttl_seconds: int | None = None,
    **extra: object,
) -> tuple[str, UserSession]:
    """Abre uma sessão e emite o token que aponta para ela.

    A linha nasce antes do token porque o token precisa carregar o ``sid``: sem
    ele, a verificação não teria o que procurar e a revogação não teria alvo.
    """
    linha = UserSession(
        user_id=user_id,
        tenant_id=tenant_id,
        # Preenchido logo abaixo com a expiração que o emissor decidir; a
        # alternativa seria repetir aqui a regra de TTL que já mora em `tokens`.
        expires_at=datetime.now(UTC),
        last_seen_at=datetime.now(UTC),
        user_agent=(user_agent or "")[:300] or None,
        ip_address=(ip_address or "")[:64] or None,
    )
    session.add(linha)
    session.flush()  # precisa do id para pôr no token

    token, expires_at = tokens.issue(
        "user", user_id, tenant_id, ttl_seconds=ttl_seconds, sid=linha.id, **extra
    )
    linha.expires_at = expires_at
    return token, linha


def viva(session: Session, sessao_id: str | None) -> UserSession | None:
    """Devolve a sessão se ela ainda vale; ``None`` se foi derrubada ou venceu.

    Um token sem ``sid`` devolve ``None``: são os tokens emitidos antes desta
    tabela existir, e tratá-los como válidos manteria de pé exatamente as
    sessões que não se consegue derrubar.
    """
    if not sessao_id:
        return None
    linha = session.get(UserSession, sessao_id)
    if linha is None or not linha.is_active:
        return None
    return linha


def marcar_presenca(session: Session, linha: UserSession) -> None:
    """Anota que a sessão foi usada, sem escrever a cada requisição."""
    agora = datetime.now(UTC)
    visto = linha.last_seen_at
    if visto is not None and visto.tzinfo is None:
        visto = visto.replace(tzinfo=UTC)
    if visto is None or agora - visto >= INTERVALO_DE_PRESENCA:
        linha.last_seen_at = agora


def abertas(session: Session, user_id: str) -> list[UserSession]:
    """As sessões vivas de uma pessoa, da mais recente para a mais antiga."""
    linhas = session.scalars(
        select(UserSession)
        .where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
        .order_by(UserSession.created_at.desc())
    ).all()
    return [linha for linha in linhas if linha.is_active]


def derrubar(
    session: Session,
    linha: UserSession,
    *,
    por: str | None,
    motivo: str,
    ator_label: str | None = None,
) -> bool:
    """Revoga uma sessão. Devolve falso se ela já estava fora.

    Idempotente de propósito: derrubar duas vezes não é erro, e a segunda vez
    não deve reescrever quem derrubou nem quando — a primeira é que conta.
    """
    if linha.revoked_at is not None:
        return False
    linha.revoked_at = datetime.now(UTC)
    linha.revoked_by = por
    linha.revoked_reason = motivo[:200]
    audit.record(
        session,
        tenant_id=linha.tenant_id,
        action="session.revoked",
        subject_type=SubjectType.USER,
        subject_id=linha.user_id,
        actor_type=ActorType.USER if por else ActorType.SYSTEM,
        actor_id=por,
        actor_label=ator_label,
        reason=motivo,
        payload={
            "session_id": linha.id,
            "user_agent": linha.user_agent,
            "ip_address": linha.ip_address,
        },
    )
    return True


def derrubar_todas(
    session: Session,
    user_id: str,
    *,
    por: str | None,
    motivo: str,
    ator_label: str | None = None,
    exceto: str | None = None,
) -> int:
    """Derruba todas as sessões de uma pessoa. Devolve quantas caíram.

    ``exceto`` existe para a troca de senha: derrubar as outras é o ponto, mas
    derrubar também a de quem está trocando faria a pessoa ser deslogada pelo
    próprio ato de se proteger — e o resultado prático seria ninguém trocar
    senha.
    """
    caidas = 0
    for linha in abertas(session, user_id):
        if exceto and linha.id == exceto:
            continue
        if derrubar(session, linha, por=por, motivo=motivo, ator_label=ator_label):
            caidas += 1
    return caidas
