"""Chamados e incidentes (brief, seção 49).

Regras que este módulo garante (as rotas só traduzem para HTTP):

* o chamado é **de um cliente**: robô e missão vinculados têm de ser dele — um id
  de outro cliente é "não encontrado", nunca um vínculo atravessando clientes;
* tudo o que muda vira **histórico** (:class:`TicketEvent`) e **auditoria**
  (``ticket.*`` / ``incident.*``), com quem e quando;
* comentário ``internal`` é da equipe e **não aparece** para o cliente — nem no
  histórico (a entrada correspondente também é interna);
* as notificações (``services/notifications.py``) saem de **eventos** publicados
  aqui na mesma transação, não de chamada direta: responder um chamado não
  depende de o e-mail funcionar.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from valtexa.models import (
    ActorType,
    Device,
    Incident,
    Mission,
    OutboxEvent,
    PlatformRole,
    SubjectType,
    SupportTicket,
    Tenant,
    TicketComment,
    TicketEvent,
    User,
)
from valtexa.models.support import (
    INCIDENT_SEVERITIES,
    INCIDENT_STATUSES,
    TICKET_OPEN_STATUSES,
    TICKET_PRIORITIES,
    TICKET_STATUSES,
)
from valtexa.security import rbac
from valtexa.services import audit, events
from valtexa.services import notifications as avisos

CLIENTE = "cliente"
PLATAFORMA = "plataforma"

STATUS_LABEL = {
    "aberto": "aberto",
    "em_atendimento": "em atendimento",
    "aguardando_cliente": "aguardando você",
    "resolvido": "resolvido",
    "fechado": "fechado",
}


class TicketError(ValueError):
    """Pedido inválido. ``status`` é o código HTTP que a rota devolve."""

    def __init__(self, mensagem: str, *, status: int = 422) -> None:
        super().__init__(mensagem)
        self.status = status


def rotulo(user: User, side: str) -> str:
    return f"{user.full_name} (equipe ValTexa)" if side == PLATAFORMA else user.full_name


def _agora() -> datetime:
    return datetime.now(UTC)


def _historico(session: Session, ticket: SupportTicket, *, by: User | None, side: str,
               kind: str, old: str | None = None, new: str | None = None,
               note: str | None = None, internal: bool = False) -> TicketEvent:
    linha = TicketEvent(
        tenant_id=ticket.tenant_id, ticket_id=ticket.id, at=_agora(),
        actor_id=by.id if by else None,
        actor_label=rotulo(by, side) if by else "Sistema", side=side, kind=kind,
        old_value=old, new_value=new, note=note, internal=internal,
    )
    session.add(linha)
    ticket.last_activity_at = linha.at
    return linha


def _audita(session: Session, ticket: SupportTicket, *, by: User, action: str,
            old: str | None = None, new: str | None = None, reason: str | None = None,
            payload: dict | None = None, so_equipe: bool = False) -> None:
    """``so_equipe``: a entrada vai para a trilha da plataforma (sem cliente), com o
    cliente no ``payload`` — a trilha do cliente (``/v1/audit``) não a mostra."""
    if so_equipe:
        payload = {"tenant_id": ticket.tenant_id, **(payload or {})}
    audit.record(
        session, tenant_id=None if so_equipe else ticket.tenant_id, action=action,
        subject_type=SubjectType.SUPPORT_TICKET, subject_id=ticket.id,
        actor_type=ActorType.USER, actor_id=by.id, actor_label=by.email,
        old_state=old, new_state=new, reason=reason,
        payload={"ticket": ticket.code, **(payload or {})},
    )


def _proximo_numero(session: Session, modelo) -> int:
    return (session.scalar(select(func.max(modelo.number))) or 0) + 1


def _com_numero(session: Session, linha, modelo) -> None:
    """Grava com o próximo número livre. Dois chamados ao mesmo tempo: o segundo
    bate na restrição única e tenta o seguinte (savepoint)."""
    for _ in range(10):
        linha.number = _proximo_numero(session, modelo)
        try:
            with session.begin_nested():
                session.add(linha)
                session.flush()
            return
        except IntegrityError:
            continue
    raise TicketError("Não foi possível numerar o chamado; tente de novo.", status=409)


def _vinculos(session: Session, tenant_id: str, device_id: str | None,
              mission_id: str | None) -> None:
    if device_id:
        robo = session.get(Device, device_id)
        if robo is None or robo.tenant_id != tenant_id:
            raise TicketError("Robô não encontrado.", status=404)
    if mission_id:
        missao = session.get(Mission, mission_id)
        if missao is None or missao.tenant_id != tenant_id:
            raise TicketError("Missão não encontrada.", status=404)


# ---------------------------------------------------------------------------
# Chamado
# ---------------------------------------------------------------------------


def abrir(session: Session, *, tenant: Tenant, by: User, side: str, title: str,
          description: str, priority: str = "normal", category: str | None = None,
          device_id: str | None = None, mission_id: str | None = None) -> SupportTicket:
    """Abre o chamado. Não faz *commit*."""
    if priority not in TICKET_PRIORITIES:
        raise TicketError(f"Prioridade inválida: {priority!r}.")
    titulo, texto = (title or "").strip(), (description or "").strip()
    if len(titulo) < 5 or len(texto) < 10:
        raise TicketError("Descreva o problema: título (5+) e descrição (10+ caracteres).")
    _vinculos(session, tenant.id, device_id, mission_id)
    ticket = SupportTicket(
        tenant_id=tenant.id, title=titulo, description=texto, status="aberto",
        priority=priority, category=(category or "").strip() or None, device_id=device_id,
        mission_id=mission_id, opened_by=by.id, opened_by_label=rotulo(by, side),
        opened_via=side, last_activity_at=_agora(),
    )
    _com_numero(session, ticket, SupportTicket)
    _historico(session, ticket, by=by, side=side, kind="aberto", new="aberto",
               note=f"Prioridade {priority}.")
    _audita(session, ticket, by=by, action="ticket.created", new="aberto",
            payload={"priority": priority, "via": side, "device_id": device_id,
                     "mission_id": mission_id})
    events.publish(session, events.TICKET_CREATED, tenant_id=tenant.id,
                   subject_type=SubjectType.SUPPORT_TICKET, subject_id=ticket.id,
                   payload={"via": side, "by": by.id})
    return ticket


def _muda_status(session: Session, ticket: SupportTicket, novo: str, *, by: User, side: str,
                 note: str | None = None, automatico: bool = False) -> None:
    if novo not in TICKET_STATUSES:
        raise TicketError(f"Status inválido: {novo!r}.")
    anterior = ticket.status
    if novo == anterior:
        return
    agora = _agora()
    ticket.status = novo
    if novo == "resolvido":
        ticket.resolved_at = agora
    if novo == "fechado":
        ticket.closed_at = agora
    if novo in TICKET_OPEN_STATUSES:
        ticket.resolved_at = ticket.closed_at = None
    _historico(session, ticket, by=by, side=side, kind="status", old=anterior, new=novo,
               note=note)
    _audita(session, ticket, by=by, action="ticket.status_changed", old=anterior, new=novo,
            reason=note)
    events.publish(session, events.TICKET_STATUS_CHANGED, tenant_id=ticket.tenant_id,
                   subject_type=SubjectType.SUPPORT_TICKET, subject_id=ticket.id,
                   payload={"old": anterior, "new": novo, "side": side, "by": by.id,
                            "auto": automatico})


def comentar(session: Session, ticket: SupportTicket, *, by: User, side: str, body: str,
             internal: bool = False) -> TicketComment:
    texto = (body or "").strip()
    if not texto:
        raise TicketError("O comentário está vazio.")
    if internal and side != PLATAFORMA:
        raise TicketError("Só a equipe da ValTexa escreve nota interna.", status=403)
    if ticket.status == "fechado":
        raise TicketError("Chamado fechado: reabra para comentar.", status=409)
    comentario = TicketComment(
        tenant_id=ticket.tenant_id, ticket_id=ticket.id, author_id=by.id,
        author_label=rotulo(by, side), side=side, body=texto, internal=internal,
        created_at=_agora(),
    )
    session.add(comentario)
    session.flush()
    _historico(session, ticket, by=by, side=side, kind="comentario",
               note="nota interna" if internal else None, internal=internal)
    # A nota interna fica só na trilha da equipe: na do cliente, ela revelaria
    # que existe (e quando foi escrita), o que o histórico já esconde.
    _audita(session, ticket, by=by, action="ticket.commented",
            payload={"comment_id": comentario.id, "internal": internal, "side": side},
            so_equipe=internal)
    if internal:
        return comentario
    if side == PLATAFORMA and ticket.first_response_at is None:
        ticket.first_response_at = comentario.created_at
    events.publish(session, events.TICKET_COMMENTED, tenant_id=ticket.tenant_id,
                   subject_type=SubjectType.SUPPORT_TICKET, subject_id=ticket.id,
                   payload={"comment_id": comentario.id, "side": side, "by": by.id})
    # A resposta do cliente devolve o chamado à fila da equipe.
    if side == CLIENTE and ticket.status in ("aguardando_cliente", "resolvido"):
        _muda_status(session, ticket, "em_atendimento", by=by, side=side,
                     note="O cliente respondeu.", automatico=True)
    return comentario


def fechar_pelo_cliente(session: Session, ticket: SupportTicket, *, by: User,
                        note: str | None = None) -> None:
    if ticket.status == "fechado":
        raise TicketError("O chamado já está fechado.", status=409)
    _muda_status(session, ticket, "fechado", by=by, side=CLIENTE,
                 note=note or "Fechado pelo cliente.")


def reabrir_pelo_cliente(session: Session, ticket: SupportTicket, *, by: User,
                         note: str) -> None:
    if ticket.status not in ("resolvido", "fechado"):
        raise TicketError("Só se reabre chamado resolvido ou fechado.", status=409)
    motivo = (note or "").strip()
    if len(motivo) < 5:
        raise TicketError("Diga por que reabrir (5+ caracteres).")
    _muda_status(session, ticket, "aberto", by=by, side=CLIENTE, note=motivo)


def _pode_atender(user: User) -> bool:
    return rbac.platform_can(user.platform_role, rbac.PLATFORM_TICKET_MANAGE)


def atualizar_pela_equipe(
    session: Session, ticket: SupportTicket, *, by: User, status: str | None = None,
    priority: str | None = None, assignee_id: str | None = None, unassign: bool = False,
    incident_id: str | None = None, unlink_incident: bool = False, note: str | None = None,
) -> None:
    """Status, prioridade, responsável e incidente — cada mudança no histórico."""
    if priority is not None and priority != ticket.priority:
        if priority not in TICKET_PRIORITIES:
            raise TicketError(f"Prioridade inválida: {priority!r}.")
        _historico(session, ticket, by=by, side=PLATAFORMA, kind="prioridade",
                   old=ticket.priority, new=priority, note=note)
        _audita(session, ticket, by=by, action="ticket.priority_changed",
                old=ticket.priority, new=priority, reason=note)
        ticket.priority = priority
    if unassign and ticket.assignee_id is not None:
        anterior = session.get(User, ticket.assignee_id)
        _historico(session, ticket, by=by, side=PLATAFORMA, kind="responsavel",
                   old=anterior.full_name if anterior else None, new=None)
        _audita(session, ticket, by=by, action="ticket.assigned", old=ticket.assignee_id)
        ticket.assignee_id = None
    elif assignee_id is not None and assignee_id != ticket.assignee_id:
        responsavel = session.get(User, assignee_id)
        if responsavel is None or not responsavel.is_active or not _pode_atender(responsavel):
            raise TicketError("Responsável precisa ser da equipe, com papel que atende "
                              "chamado (Suporte ou superadmin).")
        anterior = session.get(User, ticket.assignee_id) if ticket.assignee_id else None
        _historico(session, ticket, by=by, side=PLATAFORMA, kind="responsavel",
                   old=anterior.full_name if anterior else None, new=responsavel.full_name)
        _audita(session, ticket, by=by, action="ticket.assigned", old=ticket.assignee_id,
                new=assignee_id)
        ticket.assignee_id = assignee_id
        if ticket.status == "aberto" and status is None:
            status = "em_atendimento"
    if unlink_incident and ticket.incident_id is not None:
        incidente = session.get(Incident, ticket.incident_id)
        _historico(session, ticket, by=by, side=PLATAFORMA, kind="incidente",
                   old=incidente.code if incidente else None, new=None)
        _audita(session, ticket, by=by, action="ticket.incident_unlinked",
                old=ticket.incident_id)
        ticket.incident_id = None
    elif incident_id is not None and incident_id != ticket.incident_id:
        vincular(session, incidente_ou_erro(session, incident_id), [ticket], by=by)
    if status is not None:
        _muda_status(session, ticket, status, by=by, side=PLATAFORMA, note=note)


def comentarios(session: Session, ticket: SupportTicket, *,
                incluir_internos: bool) -> list[TicketComment]:
    consulta = select(TicketComment).where(TicketComment.ticket_id == ticket.id)
    if not incluir_internos:
        consulta = consulta.where(TicketComment.internal.is_(False))
    return list(session.scalars(consulta.order_by(TicketComment.created_at, TicketComment.id)))


def historico(session: Session, ticket: SupportTicket, *,
              incluir_internos: bool) -> list[TicketEvent]:
    consulta = select(TicketEvent).where(TicketEvent.ticket_id == ticket.id)
    if not incluir_internos:
        consulta = consulta.where(TicketEvent.internal.is_(False))
    return list(session.scalars(consulta.order_by(TicketEvent.at, TicketEvent.id)))


def registrar_sessao_de_suporte(session: Session, ticket: SupportTicket, *, by: User,
                                mode: str, expires_at: datetime) -> None:
    """A equipe entrou no cliente por causa deste chamado: o cliente vê no histórico."""
    _historico(session, ticket, by=by, side=PLATAFORMA, kind="sessao_suporte", new=mode,
               note=(f"A equipe da ValTexa entrou na sua conta para atender este chamado "
                     f"(modo {mode}, até {expires_at:%d/%m %H:%M} UTC). Tudo o que ela fizer "
                     f"fica na auditoria."))


# ---------------------------------------------------------------------------
# Incidente
# ---------------------------------------------------------------------------


def incidente_ou_erro(session: Session, incident_id: str) -> Incident:
    incidente = session.get(Incident, incident_id)
    if incidente is None:
        raise TicketError("Incidente não encontrado.", status=404)
    return incidente


def _audita_incidente(session: Session, incidente: Incident, *, by: User, action: str,
                      old: str | None = None, new: str | None = None,
                      payload: dict | None = None) -> None:
    audit.record(session, tenant_id=None, action=action, subject_type=SubjectType.INCIDENT,
                 subject_id=incidente.id, actor_type=ActorType.USER, actor_id=by.id,
                 actor_label=by.email, old_state=old, new_state=new,
                 payload={"incident": incidente.code, **(payload or {})})


def criar_incidente(session: Session, *, by: User, title: str, description: str = "",
                    severity: str = "media", public_note: str | None = None) -> Incident:
    if severity not in INCIDENT_SEVERITIES:
        raise TicketError(f"Severidade inválida: {severity!r}.")
    if len((title or "").strip()) < 5:
        raise TicketError("Dê um título ao incidente (5+ caracteres).")
    incidente = Incident(title=title.strip(), description=(description or "").strip(),
                         status="aberto", severity=severity,
                         public_note=(public_note or "").strip() or None,
                         started_at=_agora(), created_by=by.id)
    _com_numero(session, incidente, Incident)
    _audita_incidente(session, incidente, by=by, action="incident.created", new="aberto",
                      payload={"severity": severity})
    return incidente


def chamados_do_incidente(session: Session, incidente: Incident) -> list[SupportTicket]:
    return list(session.scalars(select(SupportTicket).where(
        SupportTicket.incident_id == incidente.id).order_by(SupportTicket.number)))


def vincular(session: Session, incidente: Incident, tickets: Iterable[SupportTicket], *,
             by: User) -> int:
    feitos = 0
    for ticket in tickets:
        if ticket.incident_id == incidente.id:
            continue
        anterior = session.get(Incident, ticket.incident_id) if ticket.incident_id else None
        ticket.incident_id = incidente.id
        _historico(session, ticket, by=by, side=PLATAFORMA, kind="incidente",
                   old=anterior.code if anterior else None, new=incidente.code,
                   note=f"Ligado ao incidente {incidente.code}: {incidente.title}")
        _audita(session, ticket, by=by, action="ticket.incident_linked",
                new=incidente.code, payload={"incident_id": incidente.id})
        feitos += 1
    return feitos


def atualizar_incidente(session: Session, incidente: Incident, *, by: User,
                        status: str | None = None, severity: str | None = None,
                        public_note: str | None = None, title: str | None = None) -> None:
    mudou_para_cliente = False
    if title is not None and title.strip() and title.strip() != incidente.title:
        incidente.title = title.strip()
    if severity is not None and severity != incidente.severity:
        if severity not in INCIDENT_SEVERITIES:
            raise TicketError(f"Severidade inválida: {severity!r}.")
        _audita_incidente(session, incidente, by=by, action="incident.severity_changed",
                          old=incidente.severity, new=severity)
        incidente.severity = severity
    if public_note is not None and (public_note.strip() or None) != incidente.public_note:
        incidente.public_note = public_note.strip() or None
        _audita_incidente(session, incidente, by=by, action="incident.note_changed")
        mudou_para_cliente = True
    anterior = incidente.status
    if status is not None and status != anterior:
        if status not in INCIDENT_STATUSES:
            raise TicketError(f"Status inválido: {status!r}.")
        incidente.status = status
        incidente.resolved_at = _agora() if status == "resolvido" else None
        _audita_incidente(session, incidente, by=by, action="incident.status_changed",
                          old=anterior, new=status)
        mudou_para_cliente = True
    if not mudou_para_cliente:
        return
    chamados = chamados_do_incidente(session, incidente)
    for ticket in chamados:
        _historico(session, ticket, by=by, side=PLATAFORMA, kind="incidente",
                   old=anterior if status and status != anterior else None,
                   new=incidente.status, note=incidente.public_note)
    events.publish(session, events.INCIDENT_UPDATED, tenant_id=None,
                   subject_type=SubjectType.INCIDENT, subject_id=incidente.id,
                   payload={"status": incidente.status, "tickets": [t.id for t in chamados]})


# ---------------------------------------------------------------------------
# Notificações (regras de aviso ligadas ao módulo da seção 48)
# ---------------------------------------------------------------------------


def _quem_atende(session: Session, ticket: SupportTicket) -> list[str]:
    """O responsável; sem responsável, todo o Suporte (e superadmin)."""
    if ticket.assignee_id:
        return [ticket.assignee_id]
    return list(session.scalars(select(User.id).where(
        User.platform_role.in_([PlatformRole.SUPORTE, PlatformRole.SUPERADMIN]),
        User.is_active.is_(True))))


def _para_o_cliente(ticket: SupportTicket, event: OutboxEvent, titulo: str,
                    corpo: str) -> avisos.Aviso | None:
    if ticket.opened_by is None or ticket.opened_via != CLIENTE:
        return None
    return avisos.Aviso(
        kind="chamado_atualizado", tenant_id=ticket.tenant_id, title=titulo, body=corpo,
        dedup=f"chamado:{event.id}:{ticket.id}", subject_type="support_ticket",
        subject_id=ticket.id, link=f"/suporte/{ticket.id}", para=[ticket.opened_by],
    )


def _para_a_equipe(session: Session, ticket: SupportTicket, event: OutboxEvent, kind: str,
                   titulo: str, corpo: str, *, para: list[str] | None) -> avisos.Aviso:
    return avisos.Aviso(
        kind=kind, tenant_id=ticket.tenant_id, title=titulo, body=corpo,
        dedup=f"plataforma:chamado:{event.id}", subject_type="support_ticket",
        subject_id=ticket.id, link=f"/plataforma/suporte/{ticket.id}", para=para,
        severity="critico" if ticket.priority == "urgente" else "info",
    )


def _ticket(session: Session, event: OutboxEvent) -> SupportTicket | None:
    return session.get(SupportTicket, event.subject_id) if event.subject_id else None


@avisos.regra(events.TICKET_CREATED)
def _aviso_chamado_novo(session: Session, event: OutboxEvent) -> list[avisos.Aviso]:
    ticket = _ticket(session, event)
    if ticket is None or (event.payload or {}).get("via") != CLIENTE:
        return []
    tenant = session.get(Tenant, ticket.tenant_id)
    return [_para_a_equipe(
        session, ticket, event, "plataforma_chamado_novo",
        f"{ticket.code} ({ticket.priority}): {ticket.title}",
        f"{tenant.name if tenant else 'Cliente'} — aberto por {ticket.opened_by_label}.\n\n"
        f"{ticket.description[:500]}", para=None)]


@avisos.regra(events.TICKET_COMMENTED)
def _aviso_comentario(session: Session, event: OutboxEvent) -> list[avisos.Aviso]:
    ticket = _ticket(session, event)
    dados = event.payload or {}
    comentario = session.get(TicketComment, dados.get("comment_id") or "")
    if ticket is None or comentario is None or comentario.internal:
        return []
    trecho = comentario.body[:500]
    if dados.get("side") == PLATAFORMA:
        aviso = _para_o_cliente(ticket, event, f"Resposta no chamado {ticket.code}",
                                f"{comentario.author_label}: {trecho}")
        return [aviso] if aviso else []
    return [_para_a_equipe(session, ticket, event, "plataforma_chamado_resposta",
                           f"Cliente respondeu no {ticket.code}: {ticket.title}",
                           f"{comentario.author_label}: {trecho}",
                           para=_quem_atende(session, ticket))]


@avisos.regra(events.TICKET_STATUS_CHANGED)
def _aviso_status(session: Session, event: OutboxEvent) -> list[avisos.Aviso]:
    ticket = _ticket(session, event)
    dados = event.payload or {}
    if ticket is None or dados.get("auto"):
        return []  # consequência de um comentário, que já gerou o aviso dele
    novo = STATUS_LABEL.get(dados.get("new"), dados.get("new"))
    if dados.get("side") == PLATAFORMA:
        aviso = _para_o_cliente(ticket, event, f"Chamado {ticket.code}: {novo}",
                                f"O chamado “{ticket.title}” agora está {novo}.")
        return [aviso] if aviso else []
    # Mudança do cliente (fechou, reabriu, respondeu): avisa quem atende.
    if not ticket.assignee_id and dados.get("new") != "aberto":
        return []
    return [_para_a_equipe(session, ticket, event, "plataforma_chamado_resposta",
                           f"{ticket.code}: o cliente deixou {novo}", ticket.title,
                           para=_quem_atende(session, ticket))]


@avisos.regra(events.INCIDENT_UPDATED)
def _aviso_incidente(session: Session, event: OutboxEvent) -> list[avisos.Aviso]:
    incidente = session.get(Incident, event.subject_id) if event.subject_id else None
    if incidente is None:
        return []
    saida = []
    for ticket_id in (event.payload or {}).get("tickets", []):
        ticket = session.get(SupportTicket, ticket_id)
        if ticket is None:
            continue
        estado = {"aberto": "aberto", "investigando": "em investigação",
                  "mitigado": "mitigado", "resolvido": "resolvido"}[incidente.status]
        aviso = _para_o_cliente(
            ticket, event, f"Chamado {ticket.code}: incidente {estado}",
            f"O problema ligado ao seu chamado ({incidente.title}) está {estado}."
            + (f" {incidente.public_note}" if incidente.public_note else ""))
        if aviso:
            saida.append(aviso)
    return saida


__all__ = [
    "CLIENTE",
    "PLATAFORMA",
    "TicketError",
    "abrir",
    "atualizar_incidente",
    "atualizar_pela_equipe",
    "chamados_do_incidente",
    "comentar",
    "comentarios",
    "criar_incidente",
    "fechar_pelo_cliente",
    "historico",
    "incidente_ou_erro",
    "reabrir_pelo_cliente",
    "registrar_sessao_de_suporte",
    "rotulo",
    "vincular",
]
