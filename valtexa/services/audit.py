"""Auditoria: quem fez o quê, quando, e por quê.

Toda transição relevante passa por :func:`record`. A entrada é adicionada à
**mesma sessão** que mudou o estado, então ou as duas coisas são gravadas ou
nenhuma — não existe estado alterado sem rastro, nem rastro de algo que não
aconteceu.

O que precisa de auditoria: mudança de estado de dispositivo, de missão, de
diagnóstico e de aplicação; toda avaliação de segurança; todo login e toda
rotação de credencial. A regra prática é a pergunta que a fiscalização faria —
"por que este produto foi aplicado neste talhão neste dia?" — e a resposta tem
que estar aqui, sem depender de log de aplicação.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from valtexa.models import ActorType, AuditEntry, SubjectType


def record(
    session: Session,
    *,
    action: str,
    subject_type: SubjectType,
    subject_id: str,
    actor_type: ActorType = ActorType.SYSTEM,
    actor_id: str | None = None,
    actor_label: str | None = None,
    tenant_id: str | None = None,
    old_state: str | None = None,
    new_state: str | None = None,
    reason: str | None = None,
    model_version: str | None = None,
    rule_version: str | None = None,
    ip: str | None = None,
    payload: dict | None = None,
) -> AuditEntry:
    """Anota uma ação. Não faz *commit* — quem chamou controla a transação."""
    entry = AuditEntry(
        tenant_id=tenant_id,
        actor_type=actor_type,
        actor_id=actor_id,
        actor_label=actor_label,
        action=action,
        subject_type=subject_type,
        subject_id=subject_id,
        old_state=old_state,
        new_state=new_state,
        reason=reason,
        model_version=model_version,
        rule_version=rule_version,
        ip=ip,
        payload=payload or {},
    )
    session.add(entry)
    return entry
