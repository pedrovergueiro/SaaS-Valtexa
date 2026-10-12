"""Sessões de suporte: a equipe da ValTexa entrando num cliente, às claras.

Brief, seção 29 — "entrar como cliente" só para autorizados, registrando usuário
interno, cliente, horário, motivo, ações, sessão e saída. **Nunca acesso
silencioso.** As regras que este módulo implementa:

* motivo obrigatório e prazo (padrão 2 h, teto 8 h);
* **somente leitura por padrão**; escrita só no modo assistido, ligado
  explicitamente com um motivo próprio, também auditado;
* toda requisição feita com a sessão vira linha na auditoria **do cliente**,
  com o interno como ator — o cliente vê o que a equipe fez;
* a saída é registrada (``saiu``, ``expirou`` ou encerrada por outra pessoa), e
  derruba o token na hora.

O token da sessão é um token de usuário comum com ``sup=<id>``, apontando para
uma :class:`~valtexa.models.UserSession` própria com validade igual ao prazo.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import update
from sqlalchemy.orm import Session

from valtexa import db
from valtexa.models import (
    ActorType,
    SubjectType,
    SupportMode,
    SupportSession,
    Tenant,
    User,
    UserSession,
)
from valtexa.services import audit, sessions

PRAZO_PADRAO = timedelta(hours=2)
PRAZO_MAXIMO = timedelta(hours=8)
PRAZO_MINIMO = timedelta(minutes=5)


class SupportSessionError(ValueError):
    """Pedido de sessão de suporte inválido. Vira 4xx na API."""


def _rotulo(user: User) -> str:
    return f"{user.email} (equipe ValTexa)"


def abrir(
    session: Session,
    *,
    user: User,
    tenant: Tenant,
    reason: str,
    duration: timedelta | None = None,
    ticket_ref: str | None = None,
    ticket=None,
    assisted_reason: str | None = None,
    user_agent: str | None = None,
    ip_address: str | None = None,
) -> tuple[str, SupportSession]:
    """Abre a sessão e emite o token dela. Não faz *commit*.

    ``assisted_reason`` preenchido abre já em modo assistido — explícito, com o
    motivo da escrita separado do motivo da entrada.

    ``ticket`` (um :class:`~valtexa.models.SupportTicket` do **mesmo** cliente) liga a
    sessão ao chamado que a motivou: a referência vira o código do chamado, e o
    histórico do chamado mostra ao cliente que a equipe entrou por causa dele.
    """
    if ticket is not None and ticket.tenant_id != tenant.id:
        raise SupportSessionError("O chamado é de outro cliente.")
    if ticket is not None and not (ticket_ref or "").strip():
        ticket_ref = ticket.code
    motivo = (reason or "").strip()
    if len(motivo) < 10:
        raise SupportSessionError(
            "Descreva o motivo da entrada (pelo menos 10 caracteres): ele fica na "
            "auditoria do cliente."
        )
    prazo = duration or PRAZO_PADRAO
    if prazo < PRAZO_MINIMO or prazo > PRAZO_MAXIMO:
        raise SupportSessionError("O prazo da sessão de suporte vai de 5 minutos a 8 horas.")
    assistido = (assisted_reason or "").strip()
    if assisted_reason is not None and len(assistido) < 10:
        raise SupportSessionError(
            "O modo assistido libera escrita no cliente: descreva o motivo (10+ caracteres)."
        )

    agora = datetime.now(UTC)
    suporte = SupportSession(
        user_id=user.id,
        tenant_id=tenant.id,
        reason=motivo,
        ticket_ref=(ticket_ref or "").strip() or None,
        ticket_id=ticket.id if ticket is not None else None,
        mode=SupportMode.ASSISTIDO if assistido else SupportMode.LEITURA,
        assisted_reason=assistido or None,
        assisted_at=agora if assistido else None,
        started_at=agora,
        expires_at=agora + prazo,
        request_count=0,
    )
    session.add(suporte)
    session.flush()

    token, linha = sessions.abrir(
        session,
        user_id=user.id,
        tenant_id=tenant.id,
        user_agent=user_agent,
        ip_address=ip_address,
        ttl_seconds=int(prazo.total_seconds()),
        sup=suporte.id,
    )
    suporte.user_session_id = linha.id

    entrada = audit.record(
        session,
        tenant_id=tenant.id,
        action="support.session_started",
        subject_type=SubjectType.SUPPORT_SESSION,
        subject_id=suporte.id,
        actor_type=ActorType.USER,
        actor_id=user.id,
        actor_label=_rotulo(user),
        new_state=suporte.mode.value,
        reason=motivo,
        ip=ip_address,
        payload={
            "platform_role": user.platform_role.value if user.platform_role else None,
            "expires_at": suporte.expires_at.isoformat(),
            "ticket_ref": suporte.ticket_ref,
            "ticket_id": suporte.ticket_id,
            "assisted_reason": suporte.assisted_reason,
        },
    )
    if ticket is not None:
        from valtexa.services import support_tickets

        support_tickets.registrar_sessao_de_suporte(
            session, ticket, by=user, mode=suporte.mode.value, expires_at=suporte.expires_at)
    # A entrada sai ligada à própria sessão, como as que virão depois.
    entrada.support_session_id = suporte.id
    return token, suporte


def mudar_modo(
    session: Session, suporte: SupportSession, *, user: User, mode: SupportMode, reason: str
) -> SupportSession:
    """Liga ou desliga a escrita. Ligar exige motivo; as duas coisas ficam na trilha."""
    if not suporte.is_open:
        raise SupportSessionError("Esta sessão de suporte já foi encerrada.")
    motivo = (reason or "").strip()
    if mode is SupportMode.ASSISTIDO and len(motivo) < 10:
        raise SupportSessionError(
            "O modo assistido libera escrita no cliente: descreva o motivo (10+ caracteres)."
        )
    anterior = suporte.mode
    suporte.mode = mode
    if mode is SupportMode.ASSISTIDO:
        suporte.assisted_reason = motivo
        suporte.assisted_at = datetime.now(UTC)
    entrada = audit.record(
        session,
        tenant_id=suporte.tenant_id,
        action="support.mode_changed",
        subject_type=SubjectType.SUPPORT_SESSION,
        subject_id=suporte.id,
        actor_type=ActorType.USER,
        actor_id=user.id,
        actor_label=_rotulo(user),
        old_state=anterior.value,
        new_state=mode.value,
        reason=motivo or None,
    )
    entrada.support_session_id = suporte.id
    return suporte


def encerrar(
    session: Session, suporte: SupportSession, *, por: User | None, motivo: str
) -> bool:
    """Registra a saída e derruba o token. Idempotente: a primeira saída é a que conta."""
    if suporte.ended_at is not None:
        return False
    agora = datetime.now(UTC)
    suporte.ended_at = agora
    suporte.ended_reason = motivo[:200]
    if suporte.user_session_id:
        linha = session.get(UserSession, suporte.user_session_id)
        if linha is not None:
            sessions.derrubar(
                session,
                linha,
                por=por.id if por else None,
                motivo=f"Sessão de suporte encerrada: {motivo}",
                ator_label=_rotulo(por) if por else None,
            )
    entrada = audit.record(
        session,
        tenant_id=suporte.tenant_id,
        action="support.session_ended",
        subject_type=SubjectType.SUPPORT_SESSION,
        subject_id=suporte.id,
        actor_type=ActorType.USER if por else ActorType.SYSTEM,
        actor_id=por.id if por else None,
        actor_label=_rotulo(por) if por else None,
        reason=motivo,
        payload={
            "interno": suporte.user_id,
            "requisicoes": suporte.request_count,
            "duracao_s": int((agora - _utc(suporte.started_at)).total_seconds()),
        },
    )
    entrada.support_session_id = suporte.id
    return True


def encerrar_vencida(suporte_id: str) -> None:
    """Fecha, numa transação própria, a sessão que venceu sem ninguém sair dela."""
    with db.SessionLocal() as guarda:
        suporte = guarda.get(SupportSession, suporte_id)
        if suporte is None or suporte.ended_at is not None:
            return
        encerrar(guarda, suporte, por=None, motivo="expirou")
        guarda.commit()


def registrar_requisicao(
    suporte_id: str, *, user: User, method: str, path: str, permitido: bool
) -> None:
    """Uma linha na auditoria do cliente para cada requisição feita na sessão.

    Transação própria: a leitura não faz *commit*, e uma escrita recusada não
    pode levar o rastro embora no *rollback*. Gravar a recusa também é o ponto —
    "tentou alterar e foi impedido" é exatamente o que o cliente quer saber.
    """
    with db.SessionLocal() as guarda:
        suporte = guarda.get(SupportSession, suporte_id)
        if suporte is None:
            return
        guarda.execute(
            update(SupportSession)
            .where(SupportSession.id == suporte_id)
            .values(request_count=SupportSession.request_count + 1)
        )
        guarda.info[audit.SUPPORT_SESSION_KEY] = suporte_id
        audit.record(
            guarda,
            tenant_id=suporte.tenant_id,
            action="support.request" if permitido else "support.request_denied",
            subject_type=SubjectType.SUPPORT_SESSION,
            subject_id=suporte_id,
            actor_type=ActorType.USER,
            actor_id=user.id,
            actor_label=_rotulo(user),
            new_state=suporte.mode.value,
            payload={"method": method, "path": path[:300]},
        )
        guarda.commit()


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value
