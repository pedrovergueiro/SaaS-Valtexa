"""Login, identidade e organização."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from valtexa.api.deps import (
    PlatformCaller,
    Principal,
    current_principal,
    current_principal_or_platform,
    current_user,
    require,
    require_platform,
)
from valtexa.db import get_session
from valtexa.models import (
    ActorType,
    Membership,
    Role,
    SubjectType,
    SupportSession,
    Tenant,
    User,
    UserSession,
)
from valtexa.schemas import (
    LoginRequest,
    MembershipOut,
    MeResponse,
    Message,
    PasswordChange,
    PasswordReset,
    SessionOut,
    SessionRevoked,
    SupportSessionOut,
    TenantCreate,
    TenantOut,
    TokenResponse,
    UserInvite,
    UserOut,
    UserUpdate,
)
from valtexa.security import rbac
from valtexa.security.passwords import hash_password, needs_rehash, verify_password
from valtexa.services import audit, login_guard, plans, sessions

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
    """Troca e-mail e senha por um token de sessão.

    Falhas seguidas bloqueiam a conta (e o endereço) por um tempo — ver
    :mod:`valtexa.services.login_guard`.
    """
    email = payload.email.lower()
    ip = request.client.host if request.client else None
    login_guard.verificar(session, email, ip)
    user = session.scalars(select(User).where(User.email == email)).first()

    # A verificação roda mesmo sem usuário para que o tempo de resposta não
    # revele se o e-mail existe.
    stored = user.password_hash if user else _DUMMY_HASH
    valid = verify_password(payload.password, stored)
    if user is None or not valid or not user.is_active:
        login_guard.registrar(email, ip, sucesso=False)
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

    # A sessão nasce antes do commit porque o token carrega o id dela: é esse
    # vínculo que torna o token revogável mais tarde.
    token, _linha = sessions.abrir(
        session,
        user_id=user.id,
        tenant_id=tenant.id if tenant else None,
        user_agent=request.headers.get("user-agent"),
        ip_address=request.client.host if request.client else None,
        role=role.value if role else None,
    )
    expires_at = _linha.expires_at
    session.commit()
    login_guard.registrar(email, ip, sucesso=True)

    return TokenResponse(
        access_token=token,
        expires_at=expires_at,
        tenant_id=tenant.id if tenant else None,
        role=role,
        capabilities=sorted(
            rbac.capabilities_of(role)
            if role
            else rbac.platform_capabilities_of(user.platform_role)
        ),
    )


@router.get("/auth/me", response_model=MeResponse, summary="Quem sou e o que posso")
def me(
    principal: Principal = Depends(current_principal_or_platform),
    session: Session = Depends(get_session),
) -> MeResponse:
    """Identidade, papel e capacidades.

    O frontend usa ``capabilities`` para esconder o que o papel não permite —
    mas esconder é conveniência, não segurança: cada rota confere de novo.

    Numa sessão de suporte, ``support_session`` traz quem entrou, por quê, em
    que modo e até quando: é o conteúdo da faixa que o console mostra no topo.
    """
    rows = session.execute(
        select(Membership, Tenant)
        .join(Tenant, Tenant.id == Membership.tenant_id)
        .where(Membership.user_id == principal.user_id)
    ).all()

    if principal.support_session is not None:
        acesso = "suporte"
    elif principal.via_platform:
        acesso = "plataforma"
    else:
        acesso = "membro"
    return MeResponse(
        id=principal.user_id,
        email=principal.user.email,
        full_name=principal.user.full_name,
        is_platform_admin=principal.user.is_platform_admin,
        platform_role=principal.user.platform_role,
        active_tenant_id=principal.tenant_id,
        role=principal.role,
        access=acesso,
        capabilities=sorted(principal.capabilities),
        memberships=[
            MembershipOut(
                tenant_id=tenant.id,
                tenant_name=tenant.name,
                tenant_slug=tenant.slug,
                role=membership.role,
            )
            for membership, tenant in rows
        ],
        support_session=(
            support_session_out(principal.support_session, principal.tenant, principal.user)
            if principal.support_session is not None
            else None
        ),
    )


def support_session_out(
    linha: SupportSession, tenant: Tenant | None = None, user: User | None = None
) -> SupportSessionOut:
    return SupportSessionOut(
        id=linha.id,
        tenant_id=linha.tenant_id,
        tenant_name=tenant.name if tenant else None,
        user_id=linha.user_id,
        user_email=user.email if user else None,
        reason=linha.reason,
        ticket_ref=linha.ticket_ref,
        ticket_id=linha.ticket_id,
        mode=linha.mode,
        assisted_reason=linha.assisted_reason,
        started_at=linha.started_at,
        expires_at=linha.expires_at,
        ended_at=linha.ended_at,
        ended_reason=linha.ended_reason,
        request_count=linha.request_count,
        is_open=linha.is_open,
    )


@router.get(
    "/auth/memberships",
    response_model=list[MembershipOut],
    summary="Clientes a que o usuário tem acesso",
)
def list_memberships(
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> list[MembershipOut]:
    """Não exige cliente ativo: é a rota que o console usa para escolher um.

    Para a equipe da ValTexa devolve **todos** os clientes ativos, e não só
    aqueles em que há associação. Sem isso, quem administra a plataforma e não é
    membro de fazenda nenhuma — que é o caso normal — fazia login, caía na tela
    de escolher cliente e não via nenhum para escolher: trancado para fora do
    próprio sistema.

    Esses vêm com ``access="plataforma"`` e papel ``viewer`` — o mesmo que
    ``/auth/me`` devolve para eles —, e **não** dão acesso ao dado do cliente:
    servem às rotas de plataforma (importar coleta, relevo). Ver a lavoura exige
    sessão de suporte. Até a fase 2 a lista dizia ``admin`` e a API concedia
    escrita total, sem rastro de entrada.
    """
    rows = session.execute(
        select(Membership, Tenant)
        .join(Tenant, Tenant.id == Membership.tenant_id)
        .where(Membership.user_id == user.id, Tenant.is_active)
        .order_by(Tenant.name)
    ).all()
    saida = [
        MembershipOut(
            tenant_id=tenant.id,
            tenant_name=tenant.name,
            tenant_slug=tenant.slug,
            role=membership.role,
        )
        for membership, tenant in rows
    ]
    if not user.is_platform_admin:
        return saida

    ja_listados = {item.tenant_id for item in saida}
    outros = session.scalars(
        select(Tenant).where(Tenant.is_active).order_by(Tenant.name)
    ).all()
    saida.extend(
        MembershipOut(
            tenant_id=tenant.id,
            tenant_name=tenant.name,
            tenant_slug=tenant.slug,
            role=Role.VIEWER,
            access="plataforma",
        )
        for tenant in outros
        if tenant.id not in ja_listados
    )
    saida.sort(key=lambda item: item.tenant_name)
    return saida


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
    principal: PlatformCaller = Depends(require_platform(rbac.PLATFORM_TENANT_MANAGE)),
    session: Session = Depends(get_session),
) -> TenantOut:
    """Só a equipe da ValTexa cria clientes (superadmin ou comercial)."""

    if session.scalars(select(Tenant).where(Tenant.slug == payload.slug)).first():
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"Já existe cliente com o apelido {payload.slug!r}."
        )
    tenant = Tenant(name=payload.name, slug=payload.slug, document=payload.document)
    session.add(tenant)
    session.flush()
    padrao = plans.plano_por_codigo(session, plans.PLANO_PADRAO)
    if padrao is not None:
        plans.assinar(session, tenant, padrao, actor=principal.user)
    audit.record(
        session,
        tenant_id=tenant.id,
        action="tenant.created",
        subject_type=SubjectType.TENANT,
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
    "/auth/password",
    response_model=Message,
    summary="Troca a própria senha",
)
def change_password(
    payload: PasswordChange,
    principal: Principal = Depends(current_principal),
    session: Session = Depends(get_session),
) -> Message:
    """Troca a senha de quem está autenticado, conferindo a atual.

    **Trocar a senha derruba as outras sessões.** É o motivo pelo qual se troca
    a senha às pressas: alguém entrou, e trocar a senha sem cortar o acesso que
    já está aberto não resolveria nada.

    A sessão de quem está trocando sobrevive, de propósito. Ser deslogado pelo
    próprio ato de se proteger é o tipo de atrito que faz as pessoas não
    trocarem a senha.
    """
    if not verify_password(payload.current_password, principal.user.password_hash):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "A senha atual não confere.")

    principal.user.password_hash = hash_password(payload.new_password)
    caidas = sessions.derrubar_todas(
        session,
        principal.user_id,
        por=principal.user_id,
        motivo="Senha trocada pelo próprio usuário.",
        ator_label=principal.user.email,
        exceto=principal.session_id,
    )
    audit.record(
        session,
        tenant_id=principal.tenant_id,
        action="user.password_changed",
        subject_type=SubjectType.USER,
        subject_id=principal.user_id,
        actor_type=ActorType.USER,
        actor_id=principal.user_id,
        actor_label=principal.user.email,
        reason="Troca da própria senha.",
    )
    session.commit()
    if caidas:
        quantas = (
            "1 sessão em outro aparelho foi encerrada"
            if caidas == 1
            else f"{caidas} sessões em outros aparelhos foram encerradas"
        )
        return Message(detail=f"Senha trocada. {quantas}.")
    return Message(detail="Senha trocada. Não havia outra sessão aberta.")


@router.post(
    "/users/{user_id}/password",
    response_model=Message,
    summary="Redefine a senha de um usuário do cliente",
)
def reset_password(
    user_id: str,
    payload: PasswordReset,
    principal: Principal = Depends(require(rbac.USER_MANAGE)),
    session: Session = Depends(get_session),
) -> Message:
    """Redefine a senha de quem perdeu o acesso.

    É o caminho de recuperação desta plataforma. Não há envio de e-mail e, por
    isso, não há link de redefinição — quem administra o cliente define a senha
    nova e a entrega por outro canal.

    **Todas** as sessões do alvo caem, sem exceção: aqui quem redefine é outra
    pessoa, e o caso típico é alguém que perdeu o acesso ou foi desligado. Uma
    sessão preservada seria exatamente a que se quer cortar.

    Só alcança quem é **membro do cliente ativo**. Um administrador de fazenda
    não redefine a senha de alguém de outro cliente, nem a de quem é da equipe
    da ValTexa: quem enxerga todos os clientes não pode ter a senha trocada por
    um deles.
    """
    membership = session.scalars(
        select(Membership).where(
            Membership.tenant_id == principal.tenant_id, Membership.user_id == user_id
        )
    ).first()
    if membership is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuário não pertence a este cliente.")

    alvo = session.get(User, user_id)
    if alvo is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuário não encontrado.")
    if alvo.is_platform_admin and not principal.user.is_platform_admin:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Esta conta é da equipe da ValTexa e não é redefinida de dentro de um cliente.",
        )

    alvo.password_hash = hash_password(payload.new_password)
    audit.record(
        session,
        tenant_id=principal.tenant_id,
        action="user.password_reset",
        subject_type=SubjectType.USER,
        subject_id=alvo.id,
        actor_type=ActorType.USER,
        actor_id=principal.user_id,
        actor_label=principal.user.email,
        reason=f"Senha redefinida por {principal.user.email}.",
        payload={"alvo": alvo.email},
    )
    caidas = sessions.derrubar_todas(
        session,
        alvo.id,
        por=principal.user_id,
        motivo=f"Senha redefinida por {principal.user.email}.",
        ator_label=principal.user.email,
    )
    session.commit()
    if caidas:
        return Message(
            detail=f"Senha de {alvo.email} redefinida e {caidas} sessão(ões) encerrada(s)."
        )
    return Message(detail=f"Senha de {alvo.email} redefinida.")


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
    _so_dono_mexe_em_dono(principal, payload.role)
    user = session.scalars(select(User).where(User.email == email)).first()
    if user is not None and session.scalars(
        select(Membership).where(
            Membership.tenant_id == principal.tenant_id, Membership.user_id == user.id
        )
    ).first():
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Este usuário já pertence ao cliente ativo."
        )
    plans.exigir(session, principal.tenant_id, "users")
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


@router.patch("/users/{user_id}", response_model=UserOut, summary="Muda o papel de um usuário")
def update_user(
    user_id: str,
    payload: UserUpdate,
    principal: Principal = Depends(require(rbac.USER_MANAGE)),
    session: Session = Depends(get_session),
) -> UserOut:
    """Muda o papel dentro do cliente ativo.

    Ninguém muda o próprio papel: um administrador que se rebaixasse por engano
    trancaria o cliente para fora da gestão de usuários.
    """
    membership = _membership_or_404(session, principal.tenant_id, user_id)
    if user_id == principal.user_id:
        raise HTTPException(status.HTTP_409_CONFLICT, "Não é possível mudar o próprio papel.")
    _so_dono_mexe_em_dono(principal, membership.role, payload.role)

    previous = membership.role
    membership.role = payload.role
    audit.record(
        session,
        tenant_id=principal.tenant_id,
        action="user.role_changed",
        subject_type=SubjectType.USER,
        subject_id=user_id,
        actor_type=ActorType.USER,
        actor_id=principal.user_id,
        actor_label=principal.user.email,
        old_state=previous.value,
        new_state=payload.role.value,
    )
    session.commit()
    user = session.get(User, user_id)
    return UserOut(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=membership.role,
        is_active=user.is_active,
    )


@router.delete(
    "/users/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove o usuário do cliente ativo",
)
def remove_user(
    user_id: str,
    principal: Principal = Depends(require(rbac.USER_MANAGE)),
    session: Session = Depends(get_session),
) -> None:
    """Tira o acesso a este cliente.

    A conta continua existindo — a mesma pessoa pode atender outros clientes — e
    o histórico dela na auditoria fica intacto.
    """
    membership = _membership_or_404(session, principal.tenant_id, user_id)
    if user_id == principal.user_id:
        raise HTTPException(status.HTTP_409_CONFLICT, "Não é possível remover a si mesmo.")
    _so_dono_mexe_em_dono(principal, membership.role)
    session.delete(membership)
    audit.record(
        session,
        tenant_id=principal.tenant_id,
        action="user.removed",
        subject_type=SubjectType.USER,
        subject_id=user_id,
        actor_type=ActorType.USER,
        actor_id=principal.user_id,
        actor_label=principal.user.email,
        old_state=membership.role.value,
    )
    session.commit()


def _so_dono_mexe_em_dono(principal: Principal, *papeis: Role) -> None:
    """Só o dono dá, muda ou tira o papel de dono.

    Sem esta regra, o gestor (``admin``) — que tem ``user:manage`` — criava um
    dono novo, e o dono tem ``tenant:manage``, que o gestor não tem: escalada de
    privilégio por convite. Vale também para a equipe da ValTexa em modo
    assistido, que age como gestor.
    """
    if Role.OWNER in papeis and principal.role is not Role.OWNER:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Só o dono do cliente pode dar, mudar ou retirar o papel de dono.",
        )


def _membership_or_404(session: Session, tenant_id: str, user_id: str) -> Membership:
    membership = session.scalars(
        select(Membership).where(Membership.tenant_id == tenant_id, Membership.user_id == user_id)
    ).first()
    if membership is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuário não pertence a este cliente.")
    return membership


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
            # A equipe entra com o cliente só como contexto das rotas de
            # plataforma, sem papel nele: ver o dado exige sessão de suporte.
            return tenant, None
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


# ---------------------------------------------------------------------------
# Sessões
# ---------------------------------------------------------------------------


def _sessao_out(linha: UserSession, atual: str | None) -> SessionOut:
    return SessionOut(
        id=linha.id,
        created_at=linha.created_at,
        last_seen_at=linha.last_seen_at,
        expires_at=linha.expires_at,
        user_agent=linha.user_agent,
        ip_address=linha.ip_address,
        current=linha.id == atual,
    )


@router.get(
    "/auth/sessions",
    response_model=list[SessionOut],
    summary="Meus aparelhos conectados",
)
def list_my_sessions(
    principal: Principal = Depends(current_principal),
    session: Session = Depends(get_session),
) -> list[SessionOut]:
    """As sessões abertas de quem está autenticado.

    A pergunta que isto responde é "tem mais alguém dentro da minha conta?" —
    e ela não tinha resposta possível antes, porque não havia onde olhar.
    """
    return [
        _sessao_out(linha, principal.session_id)
        for linha in sessions.abertas(session, principal.user_id)
    ]


@router.delete(
    "/auth/sessions/{session_id}",
    response_model=SessionRevoked,
    summary="Desconecta um aparelho meu",
)
def revoke_my_session(
    session_id: str,
    principal: Principal = Depends(current_principal),
    session: Session = Depends(get_session),
) -> SessionRevoked:
    """Derruba uma sessão própria — inclusive a atual, que é o logout.

    Só alcança sessão de quem pede. Derrubar a de outra pessoa é a rota de
    administrador, logo abaixo, e exige ``user:manage``: encerrar a sessão de
    alguém é ato administrativo e precisa deixar o nome de quem encerrou.
    """
    linha = session.get(UserSession, session_id)
    if linha is None or linha.user_id != principal.user_id:
        # 404 e não 403: dizer "existe, mas não é sua" entregaria a existência
        # de sessões alheias a quem ficasse adivinhando identificadores.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sessão não encontrada.")

    propria = linha.id == principal.session_id
    caiu = sessions.derrubar(
        session,
        linha,
        por=principal.user_id,
        motivo="Saiu desta sessão." if propria else "Desconectou um aparelho próprio.",
        ator_label=principal.user.email,
    )
    session.commit()
    if not caiu:
        return SessionRevoked(revoked=0, detail="Esta sessão já estava encerrada.")
    return SessionRevoked(
        revoked=1,
        detail="Você saiu desta sessão." if propria else "Aparelho desconectado.",
    )


@router.post(
    "/auth/logout",
    response_model=SessionRevoked,
    summary="Sair de todos os aparelhos",
)
def logout_everywhere(
    principal: Principal = Depends(current_principal),
    session: Session = Depends(get_session),
) -> SessionRevoked:
    """Derruba todas as sessões próprias, esta inclusive.

    É o botão de quem perdeu o celular: não adianta derrubar uma a uma quando
    não se sabe quais existem.
    """
    caidas = sessions.derrubar_todas(
        session,
        principal.user_id,
        por=principal.user_id,
        motivo="Saiu de todos os aparelhos.",
        ator_label=principal.user.email,
    )
    session.commit()
    return SessionRevoked(
        revoked=caidas,
        detail=f"{caidas} sessão(ões) encerrada(s). Entre de novo para continuar.",
    )


@router.delete(
    "/users/{user_id}/sessions",
    response_model=SessionRevoked,
    summary="Desconecta um usuário do cliente",
)
def revoke_user_sessions(
    user_id: str,
    principal: Principal = Depends(require(rbac.USER_MANAGE)),
    session: Session = Depends(get_session),
) -> SessionRevoked:
    """Corta o acesso de alguém agora, sem esperar o token vencer.

    É o que faltava para um desligamento valer na hora. Antes, tirar a pessoa
    do cliente deixava de pé o token que ela já tinha no navegador, por até doze
    horas — e doze horas é tempo de sobra para levar embora o que se quiser.

    Como a redefinição de senha, só alcança membro do cliente ativo, e não
    alcança a equipe da ValTexa de dentro de um cliente.
    """
    membership = session.scalars(
        select(Membership).where(
            Membership.tenant_id == principal.tenant_id, Membership.user_id == user_id
        )
    ).first()
    if membership is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuário não pertence a este cliente.")

    alvo = session.get(User, user_id)
    if alvo is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuário não encontrado.")
    if alvo.is_platform_admin and not principal.user.is_platform_admin:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Esta conta é da equipe da ValTexa e não é desconectada de dentro de um cliente.",
        )

    caidas = sessions.derrubar_todas(
        session,
        alvo.id,
        por=principal.user_id,
        motivo=f"Desconectado por {principal.user.email}.",
        ator_label=principal.user.email,
    )
    session.commit()
    return SessionRevoked(
        revoked=caidas, detail=f"{caidas} sessão(ões) de {alvo.email} encerrada(s)."
    )
