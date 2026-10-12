"""Console interno da ValTexa: papéis da equipe e "entrar como cliente".

Brief, seções 28 e 29. Cada rota daqui exige uma **capacidade de plataforma**
(:mod:`valtexa.security.rbac`), não "ser da equipe": o comercial não abre
sessão de suporte, o suporte não muda plano, e só o superadmin dá papel de
plataforma.

A sessão de suporte é o único jeito de a equipe ver ou agir nos dados de um
cliente de que não é membro. Ela nasce aqui (``POST /platform/support-sessions``)
e devolve um token próprio, que vale só naquele cliente, só até o prazo, e em
modo leitura até alguém ligar o modo assistido com um motivo.
"""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from valtexa.api.deps import (
    PlatformCaller,
    Principal,
    _claims_from,
    _exige_sessao_viva,
    require,
    require_platform,
)
from valtexa.api.routers.auth import support_session_out
from valtexa.db import get_session
from valtexa.models import (
    ActorType,
    AuditEntry,
    SubjectType,
    SupportMode,
    SupportSession,
    SupportTicket,
    Tenant,
    User,
)
from valtexa.schemas import (
    AuditOut,
    PlatformRoleUpdate,
    PlatformUserOut,
    SupportModeChange,
    SupportSessionEnd,
    SupportSessionOut,
    SupportSessionStart,
    SupportSessionStarted,
)
from valtexa.security import rbac
from valtexa.services import audit, sessions, support_sessions

router = APIRouter(tags=["plataforma"])


# ---------------------------------------------------------------------------
# Sessões de suporte
# ---------------------------------------------------------------------------


@router.post(
    "/platform/support-sessions",
    response_model=SupportSessionStarted,
    status_code=status.HTTP_201_CREATED,
    summary="Entra como cliente (sessão de suporte)",
)
def start_support_session(
    payload: SupportSessionStart,
    request: Request,
    caller: PlatformCaller = Depends(require_platform(rbac.PLATFORM_SUPPORT_SESSION)),
    session: Session = Depends(get_session),
) -> SupportSessionStarted:
    """Abre a sessão e devolve o token dela.

    Motivo obrigatório, prazo de 5 min a 8 h (padrão 2 h), **somente leitura por
    padrão**. ``assisted_reason`` abre já com escrita — e exige a capacidade de
    modo assistido. Entrar fica na auditoria do cliente; cada requisição feita
    com o token também.
    """
    tenant = session.get(Tenant, payload.tenant_id)
    if tenant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cliente não encontrado.")
    chamado = None
    if payload.ticket_id:
        chamado = session.get(SupportTicket, payload.ticket_id)
        if chamado is None or chamado.tenant_id != tenant.id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Chamado não encontrado neste cliente.")
    if payload.assisted_reason is not None and not caller.can(rbac.PLATFORM_SUPPORT_ASSIST):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Seu papel de plataforma não permite o modo assistido."
        )
    try:
        token, suporte = support_sessions.abrir(
            session,
            user=caller.user,
            tenant=tenant,
            reason=payload.reason,
            duration=timedelta(minutes=payload.duration_minutes),
            ticket_ref=payload.ticket_ref,
            ticket=chamado,
            assisted_reason=payload.assisted_reason,
            user_agent=request.headers.get("user-agent"),
            ip_address=request.client.host if request.client else None,
        )
    except support_sessions.SupportSessionError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    session.commit()
    return SupportSessionStarted(
        access_token=token,
        expires_at=suporte.expires_at,
        tenant_id=tenant.id,
        session=support_session_out(suporte, tenant, caller.user),
    )


@router.get(
    "/platform/support-sessions",
    response_model=list[SupportSessionOut],
    summary="Sessões de suporte (todas as da equipe)",
)
def list_support_sessions(
    tenant_id: str | None = Query(default=None),
    only_open: bool = Query(default=False),
    limit: int = Query(default=100, ge=1, le=500),
    _: PlatformCaller = Depends(require_platform(rbac.PLATFORM_AUDIT_READ)),
    session: Session = Depends(get_session),
) -> list[SupportSessionOut]:
    consulta = select(SupportSession).order_by(SupportSession.started_at.desc()).limit(limit)
    if tenant_id:
        consulta = consulta.where(SupportSession.tenant_id == tenant_id)
    if only_open:
        consulta = consulta.where(SupportSession.ended_at.is_(None))
    linhas = [linha for linha in session.scalars(consulta) if linha.is_open or not only_open]
    return [_out(session, linha) for linha in linhas]


def _dono_da_sessao(
    session: Session = Depends(get_session),
    authorization: str | None = Header(default=None),
) -> User:
    """Quem está pedindo — com o token normal **ou** com o da própria sessão de suporte.

    Sair da sessão e mudar o modo precisam funcionar com o token de suporte em
    modo leitura (é ele que o console tem na mão), e esse token não passa pelas
    rotas comuns de plataforma.
    """
    claims = _claims_from(authorization, expected_kind="user")
    user = session.get(User, claims.subject_id)
    if user is None or not user.is_active or user.platform_role is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Esta área é da equipe da ValTexa.")
    _exige_sessao_viva(session, claims)
    return user


def _sessao_do_pedido(session: Session, suporte_id: str, user: User) -> SupportSession:
    suporte = session.get(SupportSession, suporte_id)
    if suporte is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sessão de suporte não encontrada.")
    if suporte.user_id != user.id and not rbac.platform_can(
        user.platform_role, rbac.PLATFORM_ROLE_MANAGE
    ):
        # 404, não 403: a sessão de outra pessoa da equipe não é da conta de quem pede.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sessão de suporte não encontrada.")
    return suporte


@router.post(
    "/platform/support-sessions/{support_session_id}/mode",
    response_model=SupportSessionOut,
    summary="Liga ou desliga a escrita (modo assistido)",
)
def change_support_mode(
    support_session_id: str,
    payload: SupportModeChange,
    user: User = Depends(_dono_da_sessao),
    session: Session = Depends(get_session),
) -> SupportSessionOut:
    """O modo assistido é explícito e tem motivo próprio; voltar à leitura também fica na trilha."""
    suporte = _sessao_do_pedido(session, support_session_id, user)
    if suporte.user_id != user.id:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Só quem abriu a sessão de suporte muda o modo dela."
        )
    if payload.mode is SupportMode.ASSISTIDO and not rbac.platform_can(
        user.platform_role, rbac.PLATFORM_SUPPORT_ASSIST
    ):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Seu papel de plataforma não permite o modo assistido."
        )
    try:
        support_sessions.mudar_modo(
            session, suporte, user=user, mode=payload.mode, reason=payload.reason
        )
    except support_sessions.SupportSessionError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    session.commit()
    return _out(session, suporte)


@router.post(
    "/platform/support-sessions/{support_session_id}/end",
    response_model=SupportSessionOut,
    summary="Sai do cliente (encerra a sessão de suporte)",
)
def end_support_session(
    support_session_id: str,
    payload: SupportSessionEnd | None = None,
    user: User = Depends(_dono_da_sessao),
    session: Session = Depends(get_session),
) -> SupportSessionOut:
    """Registra a saída e derruba o token na hora. O superadmin encerra a de qualquer um."""
    suporte = _sessao_do_pedido(session, support_session_id, user)
    motivo = (payload.reason if payload else "saiu") or "saiu"
    if suporte.user_id != user.id:
        motivo = f"encerrada por {user.email}: {motivo}"
    support_sessions.encerrar(session, suporte, por=user, motivo=motivo)
    session.commit()
    return _out(session, suporte)


def _out(session: Session, linha: SupportSession) -> SupportSessionOut:
    return support_session_out(
        linha, session.get(Tenant, linha.tenant_id), session.get(User, linha.user_id)
    )


@router.get(
    "/tenants/current/support-sessions",
    response_model=list[SupportSessionOut],
    summary="Quando a equipe da ValTexa entrou neste cliente",
)
def my_tenant_support_sessions(
    principal: Principal = Depends(require(rbac.AUDIT_READ)),
    session: Session = Depends(get_session),
) -> list[SupportSessionOut]:
    """O outro lado da sessão de suporte: o cliente vê quem entrou, por quê e quanto agiu."""
    linhas = session.scalars(
        select(SupportSession)
        .where(SupportSession.tenant_id == principal.tenant_id)
        .order_by(SupportSession.started_at.desc())
        .limit(200)
    ).all()
    return [_out(session, linha) for linha in linhas]


# ---------------------------------------------------------------------------
# Papéis da equipe
# ---------------------------------------------------------------------------


@router.get(
    "/platform/users",
    response_model=list[PlatformUserOut],
    summary="A equipe da ValTexa e seus papéis",
)
def list_platform_users(
    _: PlatformCaller = Depends(require_platform(rbac.PLATFORM_ROLE_MANAGE)),
    session: Session = Depends(get_session),
) -> list[PlatformUserOut]:
    linhas = session.scalars(
        select(User).where(User.platform_role.is_not(None)).order_by(User.email)
    ).all()
    return [_user_out(linha) for linha in linhas]


@router.put(
    "/platform/users/{user_id}/platform-role",
    response_model=PlatformUserOut,
    summary="Dá, troca ou tira o papel de plataforma de alguém",
)
def set_platform_role(
    user_id: str,
    payload: PlatformRoleUpdate,
    caller: PlatformCaller = Depends(require_platform(rbac.PLATFORM_ROLE_MANAGE)),
    session: Session = Depends(get_session),
) -> PlatformUserOut:
    """Só o superadmin. Ninguém muda o próprio papel — evita trancar a plataforma por engano.

    Tirar ou trocar o papel derruba as sessões abertas da pessoa: um papel
    retirado precisa valer agora, não quando o token vencer.
    """
    if user_id == caller.user_id:
        raise HTTPException(status.HTTP_409_CONFLICT, "Não é possível mudar o próprio papel.")
    alvo = session.get(User, user_id)
    if alvo is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuário não encontrado.")
    anterior = alvo.platform_role
    if anterior == payload.platform_role:
        return _user_out(alvo)
    alvo.platform_role = payload.platform_role
    audit.record(
        session,
        action="platform.role_changed",
        subject_type=SubjectType.USER,
        subject_id=alvo.id,
        actor_type=ActorType.USER,
        actor_id=caller.user_id,
        actor_label=caller.user.email,
        old_state=anterior.value if anterior else None,
        new_state=payload.platform_role.value if payload.platform_role else None,
        payload={"alvo": alvo.email},
    )
    if anterior is not None:
        sessions.derrubar_todas(
            session,
            alvo.id,
            por=caller.user_id,
            motivo="Papel de plataforma alterado.",
            ator_label=caller.user.email,
        )
    session.commit()
    return _user_out(alvo)


def _user_out(user: User) -> PlatformUserOut:
    return PlatformUserOut(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        platform_role=user.platform_role,
        is_active=user.is_active,
    )


# ---------------------------------------------------------------------------
# Auditoria global
# ---------------------------------------------------------------------------


@router.get(
    "/platform/audit",
    response_model=list[AuditOut],
    summary="Auditoria de todos os clientes",
)
def platform_audit(
    tenant_id: str | None = Query(default=None),
    action: str | None = Query(default=None, description="Prefixo: 'support.', 'plan.'"),
    support_session_id: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    _: PlatformCaller = Depends(require_platform(rbac.PLATFORM_AUDIT_READ)),
    session: Session = Depends(get_session),
) -> list[AuditOut]:
    consulta = select(AuditEntry).order_by(AuditEntry.at.desc()).limit(limit)
    if tenant_id:
        consulta = consulta.where(AuditEntry.tenant_id == tenant_id)
    if action:
        consulta = consulta.where(AuditEntry.action.startswith(action))
    if support_session_id:
        consulta = consulta.where(AuditEntry.support_session_id == support_session_id)
    return [
        AuditOut(
            id=row.id,
            at=row.at,
            actor_type=str(row.actor_type),
            actor_id=row.actor_id,
            actor_label=row.actor_label,
            action=row.action,
            subject_type=str(row.subject_type),
            subject_id=row.subject_id,
            old_state=row.old_state,
            new_state=row.new_state,
            reason=row.reason,
            rule_version=row.rule_version,
            model_version=row.model_version,
            payload=row.payload or {},
            tenant_id=row.tenant_id,
            support_session_id=row.support_session_id,
        )
        for row in session.scalars(consulta)
    ]
