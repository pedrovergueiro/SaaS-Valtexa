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

SUPPORT_SESSION_KEY = "support_session_id"
"""Chave em ``Session.info`` com a sessão de suporte da requisição, quando há."""


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
    """Anota uma ação. Não faz *commit* — quem chamou controla a transação.

    Dentro de uma sessão de suporte, a dependência de autenticação marca a
    sessão do banco (``session.info["support_session_id"]``); toda entrada
    gravada nessa requisição sai ligada a ela, sem que cada rota precise saber
    que quem age é a equipe da ValTexa.
    """
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
        support_session_id=session.info.get(SUPPORT_SESSION_KEY),
    )
    session.add(entry)
    return entry


def record_ai_diagnosis(session: Session, diagnosis, *, pipeline_version: str) -> AuditEntry:
    """Anota um diagnóstico emitido por modelo, sem intervenção humana.

    Existe porque a tabela ``diagnosis`` responde "qual é o diagnóstico" e esta
    trilha responde outra pergunta: **o que a IA decidiu sozinha, quando, e com
    qual versão de modelo**. São perguntas diferentes, e a segunda é a que a
    fiscalização faz depois de uma aplicação — a linha do diagnóstico pode ter
    sido revista pelo agrônomo desde então, e a revisão sobrescreve o rótulo.

    O ator é :attr:`ActorType.AI`, e não ``SYSTEM``: o relógio que expira uma
    missão e um modelo que classifica uma folha não se auditam igual.
    """
    return record(
        session,
        tenant_id=diagnosis.tenant_id,
        action="diagnosis.emitted",
        subject_type=SubjectType.DIAGNOSIS,
        subject_id=diagnosis.id,
        actor_type=ActorType.AI,
        actor_label=pipeline_version,
        new_state=diagnosis.status.value,
        model_version=pipeline_version,
        reason=diagnosis.rationale,
        payload={
            "label": diagnosis.label,
            "confidence": diagnosis.confidence,
            "agreement": diagnosis.agreement.value if diagnosis.agreement else None,
            "novelty_score": diagnosis.novelty_score,
            "severity": diagnosis.severity,
            "observation_id": diagnosis.observation_id,
            "field_id": diagnosis.field_id,
        },
    )
