"""Suporte: chamados e incidentes (brief, seção 49).

* ``/support/tickets/**`` — o cliente abre e acompanha os chamados **dele**. Lê
  quem tem ``tenant:read`` (todo o cliente acompanha); abre, comenta, fecha e
  reabre quem tem ``support:ticket``. Nota interna da equipe não aparece aqui.
* ``/platform/tickets/**`` e ``/platform/incidents/**`` — a equipe vê todos os
  chamados de todos os clientes, atende (status, prioridade, responsável, nota
  interna) e agrupa chamados num incidente.

Toda mudança fica no histórico do chamado e na auditoria; os avisos saem pelos
eventos (``services/support_tickets.py`` → ``services/notifications.py``).
"""

from __future__ import annotations

from collections import Counter

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from valtexa.api.deps import PlatformCaller, Principal, get_scoped, require, require_platform
from valtexa.api.routers.auth import support_session_out
from valtexa.db import get_session
from valtexa.models import (
    Device,
    Incident,
    SupportSession,
    SupportTicket,
    Tenant,
    User,
)
from valtexa.models.support import TICKET_OPEN_STATUSES
from valtexa.schemas import (
    IncidentBrief,
    IncidentCreate,
    IncidentDetailOut,
    IncidentLink,
    IncidentOut,
    IncidentUpdate,
    PlatformTicketCommentIn,
    PlatformTicketCreate,
    TicketAssigneeOut,
    TicketClose,
    TicketCommentIn,
    TicketCommentOut,
    TicketCreate,
    TicketDetailOut,
    TicketEventOut,
    TicketOut,
    TicketReopen,
    TicketUpdate,
)
from valtexa.security import rbac
from valtexa.services import support_tickets as chamados

router = APIRouter(tags=["suporte"])

CHAMADO_NAO_ENCONTRADO = "Chamado não encontrado."


def _erro(exc: chamados.TicketError) -> HTTPException:
    return HTTPException(exc.status, str(exc))


def _ticket_out(session: Session, t: SupportTicket, *, com_cliente: bool = False) -> dict:
    robo = session.get(Device, t.device_id) if t.device_id else None
    incidente = session.get(Incident, t.incident_id) if t.incident_id else None
    responsavel = session.get(User, t.assignee_id) if t.assignee_id else None
    tenant = session.get(Tenant, t.tenant_id) if com_cliente else None
    return {
        "id": t.id, "code": t.code, "tenant_id": t.tenant_id,
        "tenant_name": tenant.name if tenant else None, "title": t.title,
        "description": t.description, "status": t.status, "priority": t.priority,
        "category": t.category,
        "device_id": t.device_id,
        "device_label": f"{robo.name} ({robo.serial_number})" if robo else None,
        "mission_id": t.mission_id,
        "incident": IncidentBrief(id=incidente.id, code=incidente.code, title=incidente.title,
                                  status=incidente.status, public_note=incidente.public_note)
        if incidente else None,
        "opened_by_label": t.opened_by_label, "opened_via": t.opened_via,
        "assignee_id": t.assignee_id,
        "assignee_label": chamados.rotulo(responsavel, chamados.PLATAFORMA) if responsavel
        else None,
        "created_at": t.created_at, "last_activity_at": t.last_activity_at,
        "first_response_at": t.first_response_at, "resolved_at": t.resolved_at,
        "closed_at": t.closed_at,
    }


def _detalhe(session: Session, t: SupportTicket, *, equipe: bool) -> TicketDetailOut:
    sessoes = []
    if equipe:
        for linha in session.scalars(select(SupportSession).where(
                SupportSession.ticket_id == t.id).order_by(SupportSession.started_at)):
            sessoes.append(support_session_out(linha, None, session.get(User, linha.user_id)))
    return TicketDetailOut(
        **_ticket_out(session, t, com_cliente=equipe),
        comments=[TicketCommentOut(id=c.id, author_label=c.author_label, side=c.side,
                                   body=c.body, internal=c.internal, created_at=c.created_at)
                  for c in chamados.comentarios(session, t, incluir_internos=equipe)],
        history=[TicketEventOut(at=e.at, actor_label=e.actor_label, side=e.side, kind=e.kind,
                                old_value=e.old_value, new_value=e.new_value, note=e.note,
                                internal=e.internal)
                 for e in chamados.historico(session, t, incluir_internos=equipe)],
        support_sessions=sessoes,
    )


def _filtra(consulta, status_: str | None, open_only: bool):
    if status_:
        consulta = consulta.where(SupportTicket.status == status_)
    if open_only:
        consulta = consulta.where(SupportTicket.status.in_(TICKET_OPEN_STATUSES))
    return consulta


# ---------------------------------------------------------------------------
# Console do cliente
# ---------------------------------------------------------------------------


@router.get("/support/tickets", response_model=list[TicketOut],
            summary="Chamados deste cliente")
def list_tickets(
    status_: str | None = Query(default=None, alias="status", max_length=24),
    open_only: bool = Query(default=False),
    limit: int = Query(default=100, ge=1, le=500),
    principal: Principal = Depends(require(rbac.TENANT_READ)),
    session: Session = Depends(get_session),
) -> list[TicketOut]:
    consulta = _filtra(select(SupportTicket).where(
        SupportTicket.tenant_id == principal.tenant_id), status_, open_only)
    linhas = session.scalars(consulta.order_by(SupportTicket.last_activity_at.desc())
                             .limit(limit))
    return [TicketOut(**_ticket_out(session, t)) for t in linhas]


@router.post("/support/tickets", response_model=TicketDetailOut,
             status_code=status.HTTP_201_CREATED, summary="Abre um chamado")
def open_ticket(
    payload: TicketCreate,
    principal: Principal = Depends(require(rbac.SUPPORT_TICKET)),
    session: Session = Depends(get_session),
) -> TicketDetailOut:
    # Na sessão de suporte (modo assistido) quem abre é a equipe, com o nome dela.
    lado = chamados.PLATAFORMA if principal.is_support else chamados.CLIENTE
    try:
        ticket = chamados.abrir(
            session, tenant=principal.tenant, by=principal.user, side=lado,
            title=payload.title, description=payload.description, priority=payload.priority,
            category=payload.category, device_id=payload.device_id,
            mission_id=payload.mission_id,
        )
    except chamados.TicketError as exc:
        raise _erro(exc) from exc
    session.commit()
    return _detalhe(session, ticket, equipe=False)


@router.get("/support/tickets/{ticket_id}", response_model=TicketDetailOut,
            summary="Um chamado, com a conversa e o histórico (sem notas internas)")
def get_ticket(
    ticket_id: str,
    principal: Principal = Depends(require(rbac.TENANT_READ)),
    session: Session = Depends(get_session),
) -> TicketDetailOut:
    ticket = get_scoped(session, SupportTicket, ticket_id, principal)
    return _detalhe(session, ticket, equipe=False)


@router.post("/support/tickets/{ticket_id}/comments", response_model=TicketDetailOut,
             summary="Comenta no chamado")
def comment_ticket(
    ticket_id: str,
    payload: TicketCommentIn,
    principal: Principal = Depends(require(rbac.SUPPORT_TICKET)),
    session: Session = Depends(get_session),
) -> TicketDetailOut:
    ticket = get_scoped(session, SupportTicket, ticket_id, principal)
    # Na sessão de suporte (modo assistido) quem escreve é a equipe, com o nome dela.
    lado = chamados.PLATAFORMA if principal.is_support else chamados.CLIENTE
    try:
        chamados.comentar(session, ticket, by=principal.user, side=lado, body=payload.body)
    except chamados.TicketError as exc:
        raise _erro(exc) from exc
    session.commit()
    return _detalhe(session, ticket, equipe=False)


@router.post("/support/tickets/{ticket_id}/close", response_model=TicketDetailOut,
             summary="Fecha o chamado (o problema foi resolvido)")
def close_ticket(
    ticket_id: str,
    payload: TicketClose,
    principal: Principal = Depends(require(rbac.SUPPORT_TICKET)),
    session: Session = Depends(get_session),
) -> TicketDetailOut:
    ticket = get_scoped(session, SupportTicket, ticket_id, principal)
    try:
        chamados.fechar_pelo_cliente(session, ticket, by=principal.user, note=payload.reason)
    except chamados.TicketError as exc:
        raise _erro(exc) from exc
    session.commit()
    return _detalhe(session, ticket, equipe=False)


@router.post("/support/tickets/{ticket_id}/reopen", response_model=TicketDetailOut,
             summary="Reabre um chamado resolvido ou fechado")
def reopen_ticket(
    ticket_id: str,
    payload: TicketReopen,
    principal: Principal = Depends(require(rbac.SUPPORT_TICKET)),
    session: Session = Depends(get_session),
) -> TicketDetailOut:
    ticket = get_scoped(session, SupportTicket, ticket_id, principal)
    try:
        chamados.reabrir_pelo_cliente(session, ticket, by=principal.user, note=payload.reason)
    except chamados.TicketError as exc:
        raise _erro(exc) from exc
    session.commit()
    return _detalhe(session, ticket, equipe=False)


# ---------------------------------------------------------------------------
# Console da plataforma: chamados
# ---------------------------------------------------------------------------


def _chamado_da_equipe(session: Session, ticket_id: str) -> SupportTicket:
    ticket = session.get(SupportTicket, ticket_id)
    if ticket is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, CHAMADO_NAO_ENCONTRADO)
    return ticket


@router.get("/platform/tickets", response_model=list[TicketOut],
            summary="Chamados de todos os clientes")
def platform_list_tickets(
    status_: str | None = Query(default=None, alias="status", max_length=24),
    open_only: bool = Query(default=False),
    priority: str | None = Query(default=None, max_length=16),
    tenant_id: str | None = Query(default=None, max_length=32),
    incident_id: str | None = Query(default=None, max_length=32),
    assignee_id: str | None = Query(default=None, max_length=32),
    limit: int = Query(default=200, ge=1, le=1000),
    _: PlatformCaller = Depends(require_platform(rbac.PLATFORM_TICKET_READ)),
    session: Session = Depends(get_session),
) -> list[TicketOut]:
    consulta = _filtra(select(SupportTicket), status_, open_only)
    for coluna, valor in ((SupportTicket.priority, priority),
                          (SupportTicket.tenant_id, tenant_id),
                          (SupportTicket.incident_id, incident_id),
                          (SupportTicket.assignee_id, assignee_id)):
        if valor:
            consulta = consulta.where(coluna == valor)
    linhas = session.scalars(consulta.order_by(SupportTicket.last_activity_at.desc())
                             .limit(limit))
    return [TicketOut(**_ticket_out(session, t, com_cliente=True)) for t in linhas]


@router.post("/platform/tickets", response_model=TicketDetailOut,
             status_code=status.HTTP_201_CREATED,
             summary="Abre um chamado em nome de um cliente (telefone, e-mail)")
def platform_open_ticket(
    payload: PlatformTicketCreate,
    caller: PlatformCaller = Depends(require_platform(rbac.PLATFORM_TICKET_MANAGE)),
    session: Session = Depends(get_session),
) -> TicketDetailOut:
    tenant = session.get(Tenant, payload.tenant_id)
    if tenant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cliente não encontrado.")
    try:
        ticket = chamados.abrir(
            session, tenant=tenant, by=caller.user, side=chamados.PLATAFORMA,
            title=payload.title, description=payload.description, priority=payload.priority,
            category=payload.category, device_id=payload.device_id,
            mission_id=payload.mission_id,
        )
    except chamados.TicketError as exc:
        raise _erro(exc) from exc
    session.commit()
    return _detalhe(session, ticket, equipe=True)


@router.get("/platform/tickets/{ticket_id}", response_model=TicketDetailOut,
            summary="Um chamado, com notas internas e sessões de suporte")
def platform_get_ticket(
    ticket_id: str,
    _: PlatformCaller = Depends(require_platform(rbac.PLATFORM_TICKET_READ)),
    session: Session = Depends(get_session),
) -> TicketDetailOut:
    return _detalhe(session, _chamado_da_equipe(session, ticket_id), equipe=True)


@router.patch("/platform/tickets/{ticket_id}", response_model=TicketDetailOut,
              summary="Atende: status, prioridade, responsável, incidente")
def platform_update_ticket(
    ticket_id: str,
    payload: TicketUpdate,
    caller: PlatformCaller = Depends(require_platform(rbac.PLATFORM_TICKET_MANAGE)),
    session: Session = Depends(get_session),
) -> TicketDetailOut:
    ticket = _chamado_da_equipe(session, ticket_id)
    try:
        chamados.atualizar_pela_equipe(
            session, ticket, by=caller.user, status=payload.status, priority=payload.priority,
            assignee_id=payload.assignee_id, unassign=payload.unassign,
            incident_id=payload.incident_id, unlink_incident=payload.unlink_incident,
            note=payload.note,
        )
    except chamados.TicketError as exc:
        raise _erro(exc) from exc
    session.commit()
    return _detalhe(session, ticket, equipe=True)


@router.post("/platform/tickets/{ticket_id}/comments", response_model=TicketDetailOut,
             summary="Responde ao cliente (ou escreve nota interna)")
def platform_comment_ticket(
    ticket_id: str,
    payload: PlatformTicketCommentIn,
    caller: PlatformCaller = Depends(require_platform(rbac.PLATFORM_TICKET_MANAGE)),
    session: Session = Depends(get_session),
) -> TicketDetailOut:
    ticket = _chamado_da_equipe(session, ticket_id)
    try:
        chamados.comentar(session, ticket, by=caller.user, side=chamados.PLATAFORMA,
                          body=payload.body, internal=payload.internal)
    except chamados.TicketError as exc:
        raise _erro(exc) from exc
    session.commit()
    return _detalhe(session, ticket, equipe=True)


@router.get("/platform/support/assignees", response_model=list[TicketAssigneeOut],
            summary="Quem da equipe pode ser responsável por chamado")
def ticket_assignees(
    _: PlatformCaller = Depends(require_platform(rbac.PLATFORM_TICKET_READ)),
    session: Session = Depends(get_session),
) -> list[TicketAssigneeOut]:
    linhas = session.scalars(select(User).where(
        User.platform_role.is_not(None), User.is_active.is_(True)).order_by(User.full_name))
    return [TicketAssigneeOut(id=u.id, full_name=u.full_name, platform_role=u.platform_role.value)
            for u in linhas if rbac.platform_can(u.platform_role, rbac.PLATFORM_TICKET_MANAGE)]


# ---------------------------------------------------------------------------
# Console da plataforma: incidentes
# ---------------------------------------------------------------------------


def _incidente_out(session: Session, inc: Incident) -> dict:
    tickets = chamados.chamados_do_incidente(session, inc)
    return {
        "id": inc.id, "code": inc.code, "title": inc.title, "description": inc.description,
        "status": inc.status, "severity": inc.severity, "public_note": inc.public_note,
        "started_at": inc.started_at, "resolved_at": inc.resolved_at, "ticket_count": len(tickets),
        "tenant_count": len(Counter(t.tenant_id for t in tickets)),
    }


def _incidente_detalhe(session: Session, inc: Incident) -> IncidentDetailOut:
    return IncidentDetailOut(
        **_incidente_out(session, inc),
        tickets=[TicketOut(**_ticket_out(session, t, com_cliente=True))
                 for t in chamados.chamados_do_incidente(session, inc)],
    )


def _chamados_por_id(session: Session, ids: list[str]) -> list[SupportTicket]:
    saida = []
    for ticket_id in dict.fromkeys(ids):
        saida.append(_chamado_da_equipe(session, ticket_id))
    return saida


@router.get("/platform/incidents", response_model=list[IncidentOut], summary="Incidentes")
def list_incidents(
    open_only: bool = Query(default=False),
    _: PlatformCaller = Depends(require_platform(rbac.PLATFORM_TICKET_READ)),
    session: Session = Depends(get_session),
) -> list[IncidentOut]:
    consulta = select(Incident).order_by(Incident.started_at.desc())
    if open_only:
        consulta = consulta.where(Incident.status != "resolvido")
    return [IncidentOut(**_incidente_out(session, i)) for i in session.scalars(consulta)]


@router.post("/platform/incidents", response_model=IncidentDetailOut,
             status_code=status.HTTP_201_CREATED,
             summary="Abre um incidente (e liga chamados a ele)")
def create_incident(
    payload: IncidentCreate,
    caller: PlatformCaller = Depends(require_platform(rbac.PLATFORM_TICKET_MANAGE)),
    session: Session = Depends(get_session),
) -> IncidentDetailOut:
    try:
        tickets = _chamados_por_id(session, payload.ticket_ids)
        incidente = chamados.criar_incidente(
            session, by=caller.user, title=payload.title, description=payload.description,
            severity=payload.severity, public_note=payload.public_note)
        chamados.vincular(session, incidente, tickets, by=caller.user)
    except chamados.TicketError as exc:
        raise _erro(exc) from exc
    session.commit()
    return _incidente_detalhe(session, incidente)


@router.get("/platform/incidents/{incident_id}", response_model=IncidentDetailOut,
            summary="Um incidente e os chamados ligados")
def get_incident(
    incident_id: str,
    _: PlatformCaller = Depends(require_platform(rbac.PLATFORM_TICKET_READ)),
    session: Session = Depends(get_session),
) -> IncidentDetailOut:
    try:
        return _incidente_detalhe(session, chamados.incidente_ou_erro(session, incident_id))
    except chamados.TicketError as exc:
        raise _erro(exc) from exc


@router.patch("/platform/incidents/{incident_id}", response_model=IncidentDetailOut,
              summary="Muda status, severidade ou a nota que os clientes leem")
def update_incident(
    incident_id: str,
    payload: IncidentUpdate,
    caller: PlatformCaller = Depends(require_platform(rbac.PLATFORM_TICKET_MANAGE)),
    session: Session = Depends(get_session),
) -> IncidentDetailOut:
    try:
        incidente = chamados.incidente_ou_erro(session, incident_id)
        chamados.atualizar_incidente(session, incidente, by=caller.user, status=payload.status,
                                     severity=payload.severity, title=payload.title,
                                     public_note=payload.public_note)
    except chamados.TicketError as exc:
        raise _erro(exc) from exc
    session.commit()
    return _incidente_detalhe(session, incidente)


@router.post("/platform/incidents/{incident_id}/tickets", response_model=IncidentDetailOut,
             summary="Liga chamados ao incidente")
def link_incident_tickets(
    incident_id: str,
    payload: IncidentLink,
    caller: PlatformCaller = Depends(require_platform(rbac.PLATFORM_TICKET_MANAGE)),
    session: Session = Depends(get_session),
) -> IncidentDetailOut:
    try:
        incidente = chamados.incidente_ou_erro(session, incident_id)
        chamados.vincular(session, incidente, _chamados_por_id(session, payload.ticket_ids),
                          by=caller.user)
    except chamados.TicketError as exc:
        raise _erro(exc) from exc
    session.commit()
    return _incidente_detalhe(session, incidente)
