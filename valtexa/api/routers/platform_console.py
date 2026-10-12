"""O que o console interno (``/plataforma`` no ``saas/web``) consome — Fase 3.

Complementa :mod:`valtexa.api.routers.platform` (sessões de suporte, papéis,
auditoria) com as três leituras que as telas precisam e não existiam:

* ``GET /platform/me`` — quem é a pessoa da equipe e o que ela pode;
* ``GET /platform/tenants`` — clientes com plano, assinatura, uso e
  consentimento numa linha só (o comercial e o suporte trabalham por ela);
* ``GET /platform/accounts`` — **usuários globais**: qualquer conta, com os
  clientes a que pertence; e ``PUT .../active`` para bloquear (só superadmin);
* ``GET /platform/health`` — o diagnóstico completo do processo (endereço da IA,
  pendências de configuração), que saiu do ``/health`` público e da aba
  "Plataforma" do console do cliente.

Tudo atrás de :func:`~valtexa.api.deps.require_platform`: nenhum papel de cliente
passa, e o teste gerado do OpenAPI (``test_isolamento_openapi.py``) confere isso
rota a rota.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from valtexa.api.deps import (
    PlatformCaller,
    Principal,
    require_platform,
    require_platform_in_tenant,
)
from valtexa.api.routers.farms import _farm_out, _field_out
from valtexa.api.routers.plans_api import subscription_out
from valtexa.api.routers.platform import _out as support_out
from valtexa.db import get_session
from valtexa.models import (
    ActorType,
    Farm,
    Field,
    Membership,
    SubjectType,
    SupportSession,
    Tenant,
    User,
)
from valtexa.schemas import (
    AccountActiveUpdate,
    FarmOut,
    FieldOut,
    GlobalAccountMembership,
    GlobalAccountOut,
    HealthResponse,
    PlatformMeOut,
    PlatformTenantSummary,
    TenantConsentSummary,
)
from valtexa.security import rbac
from valtexa.services import audit, consent, saude, sessions

router = APIRouter(tags=["plataforma"])

ALERTA_PERCENTUAL = 80.0
"""A partir daqui o limite aparece como aviso (plano, seção 2)."""


@router.get("/platform/me", response_model=PlatformMeOut, summary="Quem sou na equipe ValTexa")
def platform_me(
    caller: PlatformCaller = Depends(require_platform()),
    session: Session = Depends(get_session),
) -> PlatformMeOut:
    """Papel de plataforma e capacidades — o console monta o menu a partir disto."""
    abertas = [
        linha
        for linha in session.scalars(
            select(SupportSession)
            .where(SupportSession.user_id == caller.user_id, SupportSession.ended_at.is_(None))
            .order_by(SupportSession.started_at.desc())
        )
        if linha.is_open
    ]
    return PlatformMeOut(
        id=caller.user_id,
        email=caller.user.email,
        full_name=caller.user.full_name,
        platform_role=caller.platform_role,
        capabilities=sorted(rbac.platform_capabilities_of(caller.platform_role)),
        open_support_sessions=[support_out(session, linha) for linha in abertas],
    )


@router.get(
    "/platform/health",
    response_model=HealthResponse,
    summary="Estado do processo, com o detalhe que o /health público esconde",
)
def platform_health(_: PlatformCaller = Depends(require_platform())) -> HealthResponse:
    """Qualquer papel da equipe: ambiente, banco, endereço da IA, eventos pendentes e
    a lista de pendências para produção, por extenso."""
    return saude.diagnostico()


@router.get(
    "/platform/tenants",
    response_model=list[PlatformTenantSummary],
    summary="Clientes com plano, assinatura, uso e consentimento",
)
def platform_tenants(
    q: str | None = Query(default=None, max_length=120, description="Parte do nome ou apelido."),
    caller: PlatformCaller = Depends(require_platform(rbac.PLATFORM_TENANT_READ)),
    session: Session = Depends(get_session),
) -> list[PlatformTenantSummary]:
    """Sem dado agronômico: cadastro, contrato e números de uso."""
    consulta = select(Tenant).order_by(Tenant.name)
    if q:
        termo = f"%{q.strip().lower()}%"
        consulta = consulta.where(
            or_(func.lower(Tenant.name).like(termo), func.lower(Tenant.slug).like(termo))
        )
    ve_uso = caller.can(rbac.PLATFORM_USAGE_READ)

    membros = dict(
        session.execute(
            select(Membership.tenant_id, func.count()).group_by(Membership.tenant_id)
        ).all()
    )
    sessoes_abertas: dict[str, int] = {}
    for linha in session.scalars(select(SupportSession).where(SupportSession.ended_at.is_(None))):
        if linha.is_open:
            sessoes_abertas[linha.tenant_id] = sessoes_abertas.get(linha.tenant_id, 0) + 1

    saida = []
    for tenant in session.scalars(consulta):
        assinatura = subscription_out(session, tenant.id)
        decisao = consent.vigente(session, tenant.id)
        uso = assinatura.usage if ve_uso else []
        saida.append(
            PlatformTenantSummary(
                id=tenant.id,
                name=tenant.name,
                slug=tenant.slug,
                document=tenant.document,
                is_active=tenant.is_active,
                city=tenant.city,
                state=tenant.state,
                created_at=tenant.created_at,
                plan_code=assinatura.plan.code if assinatura.plan else None,
                plan_name=assinatura.plan.name if assinatura.plan else None,
                subscription_status=assinatura.status,
                subscription_ends_at=assinatura.ends_at,
                usage=uso,
                warnings=[
                    item.label
                    for item in uso
                    if item.percent is not None and item.percent >= ALERTA_PERCENTUAL
                ],
                consent=TenantConsentSummary(
                    allowed=bool(decisao and decisao.allowed),
                    decided=decisao is not None,
                    decided_at=decisao.decided_at if decisao else None,
                    source=decisao.source if decisao else None,
                ),
                members=membros.get(tenant.id, 0),
                open_support_sessions=sessoes_abertas.get(tenant.id, 0),
            )
        )
    return saida


def _account_out(session: Session, user: User) -> GlobalAccountOut:
    vinculos = session.execute(
        select(Membership, Tenant)
        .join(Tenant, Tenant.id == Membership.tenant_id)
        .where(Membership.user_id == user.id)
        .order_by(Tenant.name)
    ).all()
    return GlobalAccountOut(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        is_active=user.is_active,
        platform_role=user.platform_role,
        last_login_at=user.last_login_at,
        created_at=user.created_at,
        memberships=[
            GlobalAccountMembership(tenant_id=t.id, tenant_name=t.name, role=m.role)
            for m, t in vinculos
        ],
    )


@router.get(
    "/platform/accounts",
    response_model=list[GlobalAccountOut],
    summary="Usuários globais: qualquer conta, com os clientes a que pertence",
)
def platform_accounts(
    q: str | None = Query(default=None, max_length=120, description="Parte do e-mail ou nome."),
    team_only: bool = Query(default=False, description="Só quem tem papel de plataforma."),
    limit: int = Query(default=100, ge=1, le=500),
    _: PlatformCaller = Depends(require_platform(rbac.PLATFORM_USER_READ)),
    session: Session = Depends(get_session),
) -> list[GlobalAccountOut]:
    consulta = select(User).order_by(User.email).limit(limit)
    if q:
        termo = f"%{q.strip().lower()}%"
        consulta = consulta.where(
            or_(func.lower(User.email).like(termo), func.lower(User.full_name).like(termo))
        )
    if team_only:
        consulta = consulta.where(User.platform_role.is_not(None))
    return [_account_out(session, user) for user in session.scalars(consulta)]


@router.put(
    "/platform/accounts/{user_id}/active",
    response_model=GlobalAccountOut,
    summary="Bloqueia ou desbloqueia uma conta",
)
def set_account_active(
    user_id: str,
    payload: AccountActiveUpdate,
    caller: PlatformCaller = Depends(require_platform(rbac.PLATFORM_ROLE_MANAGE)),
    session: Session = Depends(get_session),
) -> GlobalAccountOut:
    """Só superadmin. Bloquear derruba todas as sessões na hora; ninguém bloqueia a si mesmo.

    A conta não é apagada: o histórico dela na auditoria precisa continuar com nome.
    """
    if user_id == caller.user_id:
        raise HTTPException(status.HTTP_409_CONFLICT, "Não é possível bloquear a própria conta.")
    alvo = session.get(User, user_id)
    if alvo is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuário não encontrado.")
    if alvo.is_active == payload.is_active:
        return _account_out(session, alvo)

    alvo.is_active = payload.is_active
    caidas = 0
    if not payload.is_active:
        caidas = sessions.derrubar_todas(
            session,
            alvo.id,
            por=caller.user_id,
            motivo=f"Conta bloqueada por {caller.user.email}.",
            ator_label=caller.user.email,
        )
    audit.record(
        session,
        action="user.unblocked" if payload.is_active else "user.blocked",
        subject_type=SubjectType.USER,
        subject_id=alvo.id,
        actor_type=ActorType.USER,
        actor_id=caller.user_id,
        actor_label=caller.user.email,
        reason=payload.reason,
        payload={"alvo": alvo.email, "sessoes_encerradas": caidas},
    )
    session.commit()
    return _account_out(session, alvo)


# ---------------------------------------------------------------------------
# Cadastro do cliente em foco, para as ferramentas internas
# ---------------------------------------------------------------------------


def _exige_ferramenta(principal: Principal) -> None:
    """Importar coleta (IA & Dados) ou planejar cobertura (Operações): um dos dois."""
    if not (principal.can(rbac.COLLECTION_MANAGE) or principal.can(rbac.PLATFORM_FIELD_OPERATE)):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Exige importar coleta (collection:manage) ou operar talhão (platform:field:operate).",
        )


@router.get(
    "/admin/farms",
    response_model=list[FarmOut],
    summary="Fazendas do cliente em foco (ferramentas internas)",
)
def admin_farms(
    principal: Principal = Depends(require_platform_in_tenant()),
    session: Session = Depends(get_session),
) -> list[FarmOut]:
    """O cadastro que o formulário de coleta e o planejamento precisam — sem resultado
    agronômico. A lavoura por dentro continua exigindo sessão de suporte."""
    _exige_ferramenta(principal)
    fazendas = session.scalars(
        select(Farm).where(Farm.tenant_id == principal.tenant_id).order_by(Farm.name)
    ).all()
    contagem = dict(
        session.execute(
            select(Field.farm_id, func.count(Field.id))
            .where(Field.tenant_id == principal.tenant_id)
            .group_by(Field.farm_id)
        ).all()
    )
    # CPF/CNPJ do produtor é dado pessoal que importar coleta ou planejar cobertura
    # não usa: fora daqui. Quem precisa dele entra como cliente (sessão auditada).
    return [
        _farm_out(fazenda, contagem.get(fazenda.id, 0)).model_copy(
            update={"owner_document": None}
        )
        for fazenda in fazendas
    ]


@router.get(
    "/admin/fields",
    response_model=list[FieldOut],
    summary="Talhões do cliente em foco (ferramentas internas)",
)
def admin_fields(
    principal: Principal = Depends(require_platform_in_tenant()),
    session: Session = Depends(get_session),
) -> list[FieldOut]:
    _exige_ferramenta(principal)
    talhoes = session.scalars(
        select(Field).where(Field.tenant_id == principal.tenant_id).order_by(Field.name)
    )
    return [_field_out(talhao) for talhao in talhoes]
