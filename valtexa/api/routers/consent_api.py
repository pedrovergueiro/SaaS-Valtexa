"""Consentimento de uso dos dados no treino: o cliente decide, a ValTexa registra termo.

Brief, seção 32: nunca automático; SIM/NÃO explícito; registrado com quem e quando;
só dado autorizado entra no pipeline. O padrão é NÃO.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from valtexa.api.deps import PlatformCaller, Principal, require, require_platform
from valtexa.db import get_session
from valtexa.models import DataConsent, Tenant
from valtexa.schemas import DataConsentIn, DataConsentOut, DataConsentPlatformIn, DataConsentStatus
from valtexa.security import rbac
from valtexa.services import consent

router = APIRouter(tags=["consentimento"])


@router.get(
    "/tenants/current/data-consent",
    response_model=DataConsentStatus,
    summary="Uso dos meus dados no treino: o que vale e o histórico",
)
def my_consent(
    principal: Principal = Depends(require(rbac.TENANT_READ)),
    session: Session = Depends(get_session),
) -> DataConsentStatus:
    return _status(session, principal.tenant_id)


@router.put(
    "/tenants/current/data-consent",
    response_model=DataConsentStatus,
    summary="Permitir (ou não) o uso dos meus dados para melhorar os modelos",
)
def set_my_consent(
    payload: DataConsentIn,
    principal: Principal = Depends(require(rbac.TENANT_MANAGE)),
    session: Session = Depends(get_session),
) -> DataConsentStatus:
    """Só o dono do cliente decide (``tenant:manage``). Vale a partir de agora;
    dizer NÃO retira do treino as amostras que ainda não foram usadas."""
    consent.registrar(
        session,
        tenant_id=principal.tenant_id,
        allowed=payload.allowed,
        actor=principal.user,
        source="cliente",
        notes=payload.notes,
    )
    session.commit()
    return _status(session, principal.tenant_id)


@router.get(
    "/admin/tenants/{tenant_id}/data-consent",
    response_model=DataConsentStatus,
    summary="Consentimento de um cliente",
)
def tenant_consent(
    tenant_id: str,
    _: PlatformCaller = Depends(require_platform(rbac.PLATFORM_TENANT_READ)),
    session: Session = Depends(get_session),
) -> DataConsentStatus:
    if session.get(Tenant, tenant_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cliente não encontrado.")
    return _status(session, tenant_id)


@router.put(
    "/admin/tenants/{tenant_id}/data-consent",
    response_model=DataConsentStatus,
    summary="Registra o consentimento de um cliente a partir de termo assinado",
)
def set_tenant_consent(
    tenant_id: str,
    payload: DataConsentPlatformIn,
    caller: PlatformCaller = Depends(require_platform(rbac.PLATFORM_TENANT_MANAGE)),
    session: Session = Depends(get_session),
) -> DataConsentStatus:
    if session.get(Tenant, tenant_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cliente não encontrado.")
    try:
        consent.registrar(
            session,
            tenant_id=tenant_id,
            allowed=payload.allowed,
            actor=caller.user,
            source="contrato",
            document_ref=payload.document_ref,
            notes=payload.notes,
        )
    except consent.ConsentError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    session.commit()
    return _status(session, tenant_id)


def _status(session: Session, tenant_id: str) -> DataConsentStatus:
    linhas = consent.historico(session, tenant_id)
    atual = linhas[0] if linhas else None
    return DataConsentStatus(
        tenant_id=tenant_id,
        allowed=bool(atual and atual.allowed),
        decided=atual is not None,
        current=_out(atual) if atual else None,
        history=[_out(linha) for linha in linhas],
    )


def _out(linha: DataConsent) -> DataConsentOut:
    return DataConsentOut(
        id=linha.id,
        allowed=linha.allowed,
        decided_at=linha.decided_at,
        decided_by_label=linha.decided_by_label,
        source=linha.source,
        document_ref=linha.document_ref,
        notes=linha.notes,
    )
