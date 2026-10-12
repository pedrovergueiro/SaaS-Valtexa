"""Planos e assinaturas: o catálogo (plataforma) e o "meu plano" (cliente).

O catálogo e a assinatura de cada cliente são da equipe comercial
(``platform:plan:manage``); o suporte lê. O cliente lê o próprio plano e o uso
dele — o dono vê quanto falta para o limite, ninguém do cliente muda o plano.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from valtexa.api.deps import PlatformCaller, Principal, require, require_platform
from valtexa.db import get_session
from valtexa.models import ActorType, Plan, SubjectType, Tenant
from valtexa.schemas import (
    BillingPlanCreate,
    BillingPlanOut,
    BillingPlanUpdate,
    SubscriptionOut,
    SubscriptionUpdate,
    UsageItem,
)
from valtexa.security import rbac
from valtexa.services import audit, plans

router = APIRouter(tags=["planos"])


@router.get("/admin/plans", response_model=list[BillingPlanOut], summary="Catálogo de planos")
def list_plans(
    _: PlatformCaller = Depends(require_platform(rbac.PLATFORM_PLAN_READ)),
    session: Session = Depends(get_session),
) -> list[BillingPlanOut]:
    return [_plano_out(p) for p in session.scalars(select(Plan).order_by(Plan.code))]


@router.post(
    "/admin/plans",
    response_model=BillingPlanOut,
    status_code=status.HTTP_201_CREATED,
    summary="Cria um plano",
)
def create_plan(
    payload: BillingPlanCreate,
    caller: PlatformCaller = Depends(require_platform(rbac.PLATFORM_PLAN_MANAGE)),
    session: Session = Depends(get_session),
) -> BillingPlanOut:
    plano = Plan(**payload.model_dump(), is_active=True)
    session.add(plano)
    _auditar_plano(session, caller, plano, "plan.created", payload.model_dump())
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"Já existe plano com o código {payload.code!r}."
        ) from exc
    return _plano_out(plano)


@router.patch(
    "/admin/plans/{plan_id}", response_model=BillingPlanOut, summary="Altera um plano"
)
def update_plan(
    plan_id: str,
    payload: BillingPlanUpdate,
    caller: PlatformCaller = Depends(require_platform(rbac.PLATFORM_PLAN_MANAGE)),
    session: Session = Depends(get_session),
) -> BillingPlanOut:
    """Muda o plano para **todos** os clientes nele — por isso o antes e o depois na trilha."""
    plano = session.get(Plan, plan_id)
    if plano is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Plano não encontrado.")
    mudancas = payload.model_dump(exclude_unset=True)
    antes = {campo: getattr(plano, campo) for campo in mudancas}
    for campo, valor in mudancas.items():
        setattr(plano, campo, valor)
    _auditar_plano(session, caller, plano, "plan.updated", {"antes": antes, "depois": mudancas})
    session.commit()
    return _plano_out(plano)


@router.get(
    "/admin/tenants/{tenant_id}/subscription",
    response_model=SubscriptionOut,
    summary="Plano, limites e uso de um cliente",
)
def get_tenant_subscription(
    tenant_id: str,
    _: PlatformCaller = Depends(require_platform(rbac.PLATFORM_USAGE_READ)),
    session: Session = Depends(get_session),
) -> SubscriptionOut:
    tenant = session.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cliente não encontrado.")
    return subscription_out(session, tenant.id)


@router.put(
    "/admin/tenants/{tenant_id}/subscription",
    response_model=SubscriptionOut,
    summary="Define o plano de um cliente",
)
def set_tenant_subscription(
    tenant_id: str,
    payload: SubscriptionUpdate,
    caller: PlatformCaller = Depends(require_platform(rbac.PLATFORM_PLAN_MANAGE)),
    session: Session = Depends(get_session),
) -> SubscriptionOut:
    """Cria ou troca a assinatura. O que já existe no cliente não é apagado por ficar acima
    de um limite novo: o limite vale para a próxima criação."""
    tenant = session.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cliente não encontrado.")
    plano = plans.plano_por_codigo(session, payload.plan_code)
    if plano is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Plano {payload.plan_code!r} não existe.")
    plans.assinar(
        session,
        tenant,
        plano,
        actor=caller.user,
        status=payload.status,
        ends_at=payload.ends_at,
        overrides=payload.overrides,
        notes=payload.notes,
        billing_customer_id=payload.billing_customer_id,
    )
    session.commit()
    return subscription_out(session, tenant.id)


@router.get(
    "/tenants/current/plan",
    response_model=SubscriptionOut,
    summary="Meu plano, meus limites e meu uso",
)
def my_plan(
    principal: Principal = Depends(require(rbac.TENANT_READ)),
    session: Session = Depends(get_session),
) -> SubscriptionOut:
    return subscription_out(session, principal.tenant_id)


def subscription_out(session: Session, tenant_id: str) -> SubscriptionOut:
    sub = plans.assinatura(session, tenant_id)
    limites = plans.limites_efetivos(sub)
    usado = plans.uso(session, tenant_id)
    itens = []
    for recurso, (coluna, rotulo) in plans.LIMITES.items():
        limite = limites[coluna]
        itens.append(
            UsageItem(
                resource=recurso,
                label=rotulo,
                used=usado[recurso],
                limit=limite,
                percent=(
                    round(100 * usado[recurso] / float(limite), 1)
                    if limite not in (None, 0)
                    else None
                ),
            )
        )
    return SubscriptionOut(
        tenant_id=tenant_id,
        has_subscription=sub is not None,
        plan=_plano_out(sub.plan) if sub else None,
        status=sub.status if sub else None,
        started_at=sub.started_at if sub else None,
        ends_at=sub.ends_at if sub else None,
        overrides=dict(sub.overrides or {}) if sub else {},
        notes=sub.notes if sub else None,
        effective_limits=limites,
        usage=itens,
    )


def _plano_out(plano: Plan) -> BillingPlanOut:
    return BillingPlanOut(
        id=plano.id,
        code=plano.code,
        name=plano.name,
        description=plano.description,
        is_active=plano.is_active,
        features=list(plano.features or []),
        price_cents=plano.price_cents,
        max_hectares=plano.max_hectares,
        max_farms=plano.max_farms,
        max_fields=plano.max_fields,
        max_devices=plano.max_devices,
        max_users=plano.max_users,
        max_missions_per_month=plano.max_missions_per_month,
        max_storage_gb=plano.max_storage_gb,
        retention_days=plano.retention_days,
    )


def _auditar_plano(
    session: Session, caller: PlatformCaller, plano: Plan, acao: str, payload: dict
) -> None:
    audit.record(
        session,
        action=acao,
        subject_type=SubjectType.PLAN,
        subject_id=plano.id,
        actor_type=ActorType.USER,
        actor_id=caller.user_id,
        actor_label=caller.user.email,
        new_state=plano.code,
        payload=dict(payload),
    )
