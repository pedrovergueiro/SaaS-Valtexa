"""Login, identidade e organização."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from valtexa.api.deps import Principal, current_principal, require
from valtexa.db import get_session
from valtexa.models import ActorType, Membership, Role, SubjectType, Tenant, User
from valtexa.schemas import (
    LoginRequest,
    MembershipOut,
    MeResponse,
    TenantCreate,
    TenantOut,
    TokenResponse,
    UserInvite,
    UserOut,
)
from valtexa.security import rbac, tokens
from valtexa.security.passwords import hash_password, needs_rehash, verify_password
from valtexa.services import audit

router = APIRouter(tags=["autenticação"])

BAD_CREDENTIALS = HTTPException(
    status.HTTP_401_UNAUTHORIZED, "E-mail ou senha incorretos."
)
"""Mensagem única para usuário inexistente e senha errada.

Distinguir os dois casos entregaria de graça uma lista de e-mails válidos.
"""


@router.post("/auth/login", response_model=TokenResponse, summary="Autentica um usuário")
def login(
    payload: LoginRequest, request: Request, session: Session = Depends(get_session)
) -> TokenResponse:
    """Troca e-mail e senha por um token de sessão."""
    user = session.scalars(select(User).where(User.email == payload.email.lower())).first()

    # A verificação roda mesmo sem usuário para que o tempo de resposta não
    # revele se o e-mail existe.
    stored = user.password_hash if user else _DUMMY_HASH
    valid = verify_password(payload.password, stored)
    if user is None or not valid or not user.is_active:
        raise BAD_CREDENTIALS

    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(payload.password)

    memberships = list(
        session.scalars(select(Membership).where(Membership.user_id == user.id))
    )
    tenant, role = _resolve_tenant(session, user, memberships, payload.tenant)

    user.last_login_at = datetime.now(UTC)
    audit.record(
        session,
        tenant_id=tenant.id if tenant else None,
        action="auth.login",
        subject_type=SubjectType.USER,
        subject_id=user.id,
        actor_type=ActorType.USER,
        actor_id=user.id,
        actor_label=user.email,
        ip=request.client.host if request.client else None,
    )
    session.commit()

    token, expires_at = tokens.issue(
        "user", user.id, tenant_id=tenant.id if tenant else None, role=role.value if role else None
    )
    return TokenResponse(
        access_token=token,
        expires_at=expires_at,
        tenant_id=tenant.id if tenant else None,
        role=role,
        capabilities=sorted(rbac.capabilities_of(role)) if role else [],
    )


@router.get("/auth/me", response_model=MeResponse, summary="Quem sou e o que posso")
def me(
    principal: Principal = Depends(current_principal),
    session: Session = Depends(get_session),
) -> MeResponse:
    """Identidade, papel e capacidades.

    O frontend usa ``capabilities`` para esconder o que o papel não permite —
    mas esconder é conveniência, não segurança: cada rota confere de novo.
    """
    rows = session.execute(
        select(Membership, Tenant)
        .join(Tenant, Tenant.id == Membership.tenant_id)
        .where(Membership.user_id == principal.user_id)
    ).all()

    return MeResponse(
        id=principal.user_id,
        email=principal.user.email,
        full_name=principal.user.full_name,
        is_platform_admin=principal.user.is_platform_admin,
        active_tenant_id=principal.tenant_id,
        role=principal.role,
        capabilities=sorted(rbac.capabilities_of(principal.role)),
        memberships=[
            MembershipOut(
                tenant_id=tenant.id,
                tenant_name=tenant.name,
                tenant_slug=tenant.slug,
                role=membership.role,
            )
            for membership, tenant in rows
        ],
    )


@router.get("/tenants/current", response_model=TenantOut, summary="Cliente ativo")
def current_tenant(principal: Principal = Depends(current_principal)) -> TenantOut:
    return _tenant_out(principal.tenant)


@router.post(
    "/tenants",
    response_model=TenantOut,
    status_code=status.HTTP_201_CREATED,
    summary="Cria um cliente",
)
def create_tenant(
    payload: TenantCreate,
    principal: Principal = Depends(current_principal),
    session: Session = Depends(get_session),
) -> TenantOut:
    """Só a equipe da ValTexa cria clientes."""
    if not principal.user.is_platform_admin:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Apenas a equipe da plataforma cria clientes."
        )

    tenant = Tenant(name=payload.name, slug=payload.slug, document=payload.document)
    session.add(tenant)
    audit.record(
        session,
        tenant_id=tenant.id,
        action="tenant.created",
        subject_type=SubjectType.USER,
        subject_id=tenant.id,
        actor_type=ActorType.USER,
        actor_id=principal.user_id,
        actor_label=principal.user.email,
    )
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"Já existe cliente com o apelido {payload.slug!r}."
        ) from exc
    return _tenant_out(tenant)


@router.post(
    "/users",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    summary="Adiciona um usuário ao cliente",
)
def invite_user(
    payload: UserInvite,
    principal: Principal = Depends(require(rbac.USER_MANAGE)),
    session: Session = Depends(get_session),
) -> UserOut:
    """Cria (ou reaproveita) o usuário e o associa ao cliente ativo.

    Um usuário já cadastrado em outro cliente não é duplicado: ganha uma
    associação a mais. É o caso do agrônomo que atende várias fazendas.
    """
    email = payload.email.lower()
    user = session.scalars(select(User).where(User.email == email)).first()
    if user is None:
        user = User(
            email=email,
            full_name=payload.full_name,
            password_hash=hash_password(payload.password),
        )
        session.add(user)
        session.flush()

    existing = session.scalars(
        select(Membership).where(
            Membership.tenant_id == principal.tenant_id, Membership.user_id == user.id
        )
    ).first()
    if existing is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Este usuário já pertence ao cliente ativo."
        )

    membership = Membership(
        tenant_id=principal.tenant_id, user_id=user.id, role=payload.role
    )
    session.add(membership)
    audit.record(
        session,
        tenant_id=principal.tenant_id,
        action="user.added",
        subject_type=SubjectType.USER,
        subject_id=user.id,
        actor_type=ActorType.USER,
        actor_id=principal.user_id,
        actor_label=principal.user.email,
        new_state=payload.role.value,
    )
    session.commit()
    return UserOut(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=payload.role,
        is_active=user.is_active,
    )


@router.get("/users", response_model=list[UserOut], summary="Usuários do cliente")
def list_users(
    principal: Principal = Depends(require(rbac.TENANT_READ)),
    session: Session = Depends(get_session),
) -> list[UserOut]:
    rows = session.execute(
        select(User, Membership)
        .join(Membership, Membership.user_id == User.id)
        .where(Membership.tenant_id == principal.tenant_id)
        .order_by(User.full_name)
    ).all()
    return [
        UserOut(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            role=membership.role,
            is_active=user.is_active,
        )
        for user, membership in rows
    ]


def _resolve_tenant(
    session: Session, user: User, memberships: list[Membership], slug: str | None
) -> tuple[Tenant | None, Role | None]:
    """Escolhe o cliente do login.

    Com um só, entra direto. Com vários e sem escolha explícita, a sessão nasce
    sem cliente e o frontend pergunta — adivinhar levaria alguém a operar na
    fazenda errada.
    """
    if slug:
        tenant = session.scalars(select(Tenant).where(Tenant.slug == slug)).first()
        if tenant is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Cliente não encontrado.")
        match = next((m for m in memberships if m.tenant_id == tenant.id), None)
        if match is None:
            if not user.is_platform_admin:
                raise HTTPException(
                    status.HTTP_403_FORBIDDEN, "Usuário não pertence a este cliente."
                )
            return tenant, Role.ADMIN
        return tenant, match.role

    if len(memberships) == 1:
        return session.get(Tenant, memberships[0].tenant_id), memberships[0].role
    return None, None


def _tenant_out(tenant: Tenant) -> TenantOut:
    return TenantOut(
        id=tenant.id,
        name=tenant.name,
        slug=tenant.slug,
        document=tenant.document,
        is_active=tenant.is_active,
        created_at=tenant.created_at,
    )


_DUMMY_HASH = hash_password("comparacao-em-tempo-constante")
"""Hash descartável, usado quando o e-mail não existe.

Sem ele, o login falharia mais rápido para e-mail inexistente do que para senha
errada, e a diferença de tempo enumeraria usuários.
"""
