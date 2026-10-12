"""Central de notificações e preferências (brief, seção 48).

Duas caixas com as mesmas operações:

* ``/notifications/**`` — console do cliente. A caixa é da **pessoa dentro do
  cliente ativo**: o agrônomo de cooperativa vê, em cada cliente, só os avisos
  daquele cliente. Aviso de outra pessoa ou de outro cliente é 404.
* ``/platform/notifications/**`` — console interno, para a equipe da ValTexa.

As rotas só leem e marcam. Quem **cria** aviso são as regras do
``services/notifications.py``, a partir dos eventos de domínio — nenhuma tela
manda aviso por conta própria.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from valtexa.api.deps import PlatformCaller, Principal, current_principal, require, require_platform
from valtexa.db import get_session
from valtexa.models import Notification, PlatformRole, Role
from valtexa.schemas import (
    NotificationChannelOut,
    NotificationCount,
    NotificationDeliveryOut,
    NotificationOut,
    NotificationPreferenceIn,
    NotificationPreferenceOut,
    NotificationPreferencesOut,
    NotificationReadAll,
    NotificationRolePreferenceIn,
)
from valtexa.security import rbac
from valtexa.services import notifications as avisos

router = APIRouter(tags=["notificações"])

NAO_ENCONTRADO = "Notificação não encontrada."


def _out(session: Session, linhas: list[Notification]) -> list[NotificationOut]:
    entregas = avisos.entregas_de(session, [n.id for n in linhas])
    return [
        NotificationOut(
            id=n.id, kind=n.kind, severity=n.severity, title=n.title, body=n.body, link=n.link,
            subject_type=n.subject_type, subject_id=n.subject_id, created_at=n.created_at,
            read_at=n.read_at,
            deliveries=[
                NotificationDeliveryOut(channel=e.channel, status=e.status, attempts=e.attempts,
                                        last_error=e.last_error, sent_at=e.sent_at)
                for e in entregas[n.id]
            ],
        )
        for n in linhas
    ]


def _preferencias_out(
    role: str | None, linhas: list[tuple[avisos.Tipo, avisos.Efetiva]]
) -> NotificationPreferencesOut:
    return NotificationPreferencesOut(
        role=role,
        channels=[NotificationChannelOut(**c) for c in avisos.canais_disponiveis()],
        preferences=[
            NotificationPreferenceOut(
                kind=tipo.kind, label=tipo.label, description=tipo.description,
                enabled=ef.enabled, channels=list(ef.channels), threshold=ef.threshold,
                threshold_unit=tipo.threshold_unit, source=ef.source,
            )
            for tipo, ef in linhas
        ],
    )


def _grava(session: Session, payload: NotificationPreferenceIn, *, audience: str,
           tenant_id: str | None, user_id: str | None, role: str | None, by) -> None:
    try:
        if payload.reset:
            avisos.remover_preferencia(session, audience=audience, tenant_id=tenant_id,
                                       user_id=user_id, role=role, kind=payload.kind)
        else:
            avisos.salvar_preferencia(
                session, audience=audience, tenant_id=tenant_id, user_id=user_id, role=role,
                kind=payload.kind, enabled=payload.enabled, channels=payload.channels,
                threshold=payload.threshold, by=by,
            )
    except avisos.PreferenceError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    session.commit()


# ---------------------------------------------------------------------------
# Console do cliente
# ---------------------------------------------------------------------------


@router.get("/notifications", response_model=list[NotificationOut],
            summary="Minhas notificações neste cliente")
def list_notifications(
    only_unread: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    principal: Principal = Depends(current_principal),
    session: Session = Depends(get_session),
) -> list[NotificationOut]:
    linhas = avisos.caixa(session, user_id=principal.user_id, audience=avisos.CLIENTE,
                          tenant_id=principal.tenant_id, only_unread=only_unread, limit=limit)
    return _out(session, linhas)


@router.get("/notifications/unread-count", response_model=NotificationCount,
            summary="Quantas não lidas (o número do sino)")
def unread_count(
    principal: Principal = Depends(current_principal),
    session: Session = Depends(get_session),
) -> NotificationCount:
    return NotificationCount(unread=avisos.nao_lidas(
        session, user_id=principal.user_id, audience=avisos.CLIENTE,
        tenant_id=principal.tenant_id))


@router.post("/notifications/{notification_id}/read", response_model=NotificationOut,
             summary="Marca uma notificação como lida")
def mark_read(
    notification_id: str,
    principal: Principal = Depends(current_principal),
    session: Session = Depends(get_session),
) -> NotificationOut:
    aviso = avisos.da_pessoa(session, notification_id, user_id=principal.user_id,
                             audience=avisos.CLIENTE, tenant_id=principal.tenant_id)
    if aviso is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NAO_ENCONTRADO)
    if aviso.read_at is None:
        aviso.read_at = datetime.now(UTC)
        session.commit()
    return _out(session, [aviso])[0]


@router.post("/notifications/read-all", response_model=NotificationReadAll,
             summary="Marca todas como lidas")
def mark_all_read(
    principal: Principal = Depends(current_principal),
    session: Session = Depends(get_session),
) -> NotificationReadAll:
    marcadas = avisos.marcar_todas(session, user_id=principal.user_id, audience=avisos.CLIENTE,
                                   tenant_id=principal.tenant_id)
    session.commit()
    return NotificationReadAll(marked=marcadas)


@router.get("/notifications/preferences", response_model=NotificationPreferencesOut,
            summary="O que eu recebo, por qual canal e a partir de qual limite")
def my_preferences(
    principal: Principal = Depends(current_principal),
    session: Session = Depends(get_session),
) -> NotificationPreferencesOut:
    papel = principal.role.value
    return _preferencias_out(papel, avisos.preferencias(
        session, user_id=principal.user_id, role=papel, audience=avisos.CLIENTE,
        tenant_id=principal.tenant_id))


@router.put("/notifications/preferences", response_model=NotificationPreferencesOut,
            summary="Muda a minha preferência de um tipo de aviso")
def set_my_preference(
    payload: NotificationPreferenceIn,
    principal: Principal = Depends(current_principal),
    session: Session = Depends(get_session),
) -> NotificationPreferencesOut:
    _grava(session, payload, audience=avisos.CLIENTE, tenant_id=principal.tenant_id,
           user_id=principal.user_id, role=None, by=principal.user)
    return my_preferences(principal, session)


def _papel_de_cliente(role: str) -> str:
    if role not in {r.value for r in Role}:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Papel desconhecido: {role!r}.")
    return role


@router.get("/notifications/role-preferences", response_model=NotificationPreferencesOut,
            summary="Quem recebe o quê, por papel, neste cliente (gestor)")
def role_preferences(
    role: str = Query(max_length=16),
    principal: Principal = Depends(require(rbac.USER_MANAGE)),
    session: Session = Depends(get_session),
) -> NotificationPreferencesOut:
    papel = _papel_de_cliente(role)
    return _preferencias_out(papel, avisos.preferencias_do_papel(
        session, role=papel, audience=avisos.CLIENTE, tenant_id=principal.tenant_id))


@router.put("/notifications/role-preferences", response_model=NotificationPreferencesOut,
            summary="Define o que um papel recebe neste cliente (gestor)")
def set_role_preference(
    payload: NotificationRolePreferenceIn,
    principal: Principal = Depends(require(rbac.USER_MANAGE)),
    session: Session = Depends(get_session),
) -> NotificationPreferencesOut:
    papel = _papel_de_cliente(payload.role)
    _grava(session, payload, audience=avisos.CLIENTE, tenant_id=principal.tenant_id,
           user_id=None, role=papel, by=principal.user)
    return _preferencias_out(papel, avisos.preferencias_do_papel(
        session, role=papel, audience=avisos.CLIENTE, tenant_id=principal.tenant_id))


# ---------------------------------------------------------------------------
# Console da plataforma (equipe ValTexa)
# ---------------------------------------------------------------------------


@router.get("/platform/notifications", response_model=list[NotificationOut],
            summary="Notificações da equipe")
def platform_notifications(
    only_unread: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    caller: PlatformCaller = Depends(require_platform()),
    session: Session = Depends(get_session),
) -> list[NotificationOut]:
    linhas = avisos.caixa(session, user_id=caller.user_id, audience=avisos.PLATAFORMA,
                          tenant_id=None, only_unread=only_unread, limit=limit)
    return _out(session, linhas)


@router.get("/platform/notifications/unread-count", response_model=NotificationCount,
            summary="Não lidas da equipe")
def platform_unread_count(
    caller: PlatformCaller = Depends(require_platform()),
    session: Session = Depends(get_session),
) -> NotificationCount:
    return NotificationCount(unread=avisos.nao_lidas(
        session, user_id=caller.user_id, audience=avisos.PLATAFORMA, tenant_id=None))


@router.post("/platform/notifications/{notification_id}/read", response_model=NotificationOut,
             summary="Marca como lida (equipe)")
def platform_mark_read(
    notification_id: str,
    caller: PlatformCaller = Depends(require_platform()),
    session: Session = Depends(get_session),
) -> NotificationOut:
    aviso = avisos.da_pessoa(session, notification_id, user_id=caller.user_id,
                             audience=avisos.PLATAFORMA, tenant_id=None)
    if aviso is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NAO_ENCONTRADO)
    if aviso.read_at is None:
        aviso.read_at = datetime.now(UTC)
        session.commit()
    return _out(session, [aviso])[0]


@router.post("/platform/notifications/read-all", response_model=NotificationReadAll,
             summary="Marca todas como lidas (equipe)")
def platform_mark_all_read(
    caller: PlatformCaller = Depends(require_platform()),
    session: Session = Depends(get_session),
) -> NotificationReadAll:
    marcadas = avisos.marcar_todas(session, user_id=caller.user_id,
                                   audience=avisos.PLATAFORMA, tenant_id=None)
    session.commit()
    return NotificationReadAll(marked=marcadas)


@router.get("/platform/notifications/preferences", response_model=NotificationPreferencesOut,
            summary="Preferências de aviso da equipe (as minhas)")
def platform_my_preferences(
    caller: PlatformCaller = Depends(require_platform()),
    session: Session = Depends(get_session),
) -> NotificationPreferencesOut:
    papel = caller.platform_role.value if caller.platform_role else None
    return _preferencias_out(papel, avisos.preferencias(
        session, user_id=caller.user_id, role=papel, audience=avisos.PLATAFORMA,
        tenant_id=None))


@router.put("/platform/notifications/preferences", response_model=NotificationPreferencesOut,
            summary="Muda a minha preferência (equipe)")
def platform_set_my_preference(
    payload: NotificationPreferenceIn,
    caller: PlatformCaller = Depends(require_platform()),
    session: Session = Depends(get_session),
) -> NotificationPreferencesOut:
    _grava(session, payload, audience=avisos.PLATAFORMA, tenant_id=None,
           user_id=caller.user_id, role=None, by=caller.user)
    return platform_my_preferences(caller, session)


def _papel_de_plataforma(role: str) -> str:
    if role not in {r.value for r in PlatformRole}:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Papel desconhecido: {role!r}.")
    return role


@router.get("/platform/notifications/role-preferences",
            response_model=NotificationPreferencesOut,
            summary="O que cada papel da equipe recebe (superadmin)")
def platform_role_preferences(
    role: str = Query(max_length=16),
    _: PlatformCaller = Depends(require_platform(rbac.PLATFORM_ROLE_MANAGE)),
    session: Session = Depends(get_session),
) -> NotificationPreferencesOut:
    papel = _papel_de_plataforma(role)
    return _preferencias_out(papel, avisos.preferencias_do_papel(
        session, role=papel, audience=avisos.PLATAFORMA, tenant_id=None))


@router.put("/platform/notifications/role-preferences",
            response_model=NotificationPreferencesOut,
            summary="Define o que um papel da equipe recebe (superadmin)")
def platform_set_role_preference(
    payload: NotificationRolePreferenceIn,
    caller: PlatformCaller = Depends(require_platform(rbac.PLATFORM_ROLE_MANAGE)),
    session: Session = Depends(get_session),
) -> NotificationPreferencesOut:
    papel = _papel_de_plataforma(payload.role)
    _grava(session, payload, audience=avisos.PLATAFORMA, tenant_id=None, user_id=None,
           role=papel, by=caller.user)
    return _preferencias_out(papel, avisos.preferencias_do_papel(
        session, role=papel, audience=avisos.PLATAFORMA, tenant_id=None))
