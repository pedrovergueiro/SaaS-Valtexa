"""Consentimento do cliente para o uso dos dados dele no treino (brief, seção 32).

"Permitir utilização dos dados/imagens para melhoria dos modelos? SIM/NÃO."

* **Padrão NÃO.** Cliente sem decisão registrada não entra em dataset nenhum —
  inclusive quem já era cliente antes desta regra.
* Cada decisão é uma linha nova (:class:`~valtexa.models.DataConsent`), com quem
  e quando; o vigente é o mais recente. Nada é editado.
* Quem decide é o **dono** do cliente, no console (``source="cliente"``), ou a
  ValTexa registrando um termo assinado (``source="contrato"``, com o documento).
* Revogar tira do caminho do treino as amostras ainda não usadas e também as já
  incluídas: ficam ``EXCLUDED`` e não entram em corte novo. Os cortes já
  congelados guardam a lista de identificadores que tinham (é o que os torna
  reproduzíveis) — apagar o que um modelo já aprendeu é decisão pendente,
  registrada em docs/PROGRESSO.md.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from valtexa.models import (
    ActorType,
    DataConsent,
    DatasetSample,
    DatasetSampleState,
    SubjectType,
    User,
)
from valtexa.services import audit

logger = logging.getLogger(__name__)

ORIGENS = frozenset({"cliente", "contrato"})


class ConsentError(ValueError):
    """Registro de consentimento inválido. Vira 422 na API."""


def vigente(session: Session, tenant_id: str) -> DataConsent | None:
    """A decisão mais recente do cliente, ou ``None`` se nunca decidiu."""
    return session.scalars(
        select(DataConsent)
        .where(DataConsent.tenant_id == tenant_id)
        .order_by(DataConsent.decided_at.desc(), DataConsent.created_at.desc())
        .limit(1)
    ).first()


def permite_treino(session: Session, tenant_id: str) -> bool:
    """SIM explícito e vigente. Qualquer outra coisa — inclusive nada — é NÃO."""
    decisao = vigente(session, tenant_id)
    return bool(decisao and decisao.allowed)


def clientes_com_consentimento(session: Session, tenant_ids: set[str]) -> set[str]:
    """Dos clientes dados, os que hoje permitem uso em treino."""
    return {tenant_id for tenant_id in tenant_ids if permite_treino(session, tenant_id)}


def historico(session: Session, tenant_id: str) -> list[DataConsent]:
    return list(
        session.scalars(
            select(DataConsent)
            .where(DataConsent.tenant_id == tenant_id)
            .order_by(DataConsent.decided_at.desc(), DataConsent.created_at.desc())
        )
    )


def registrar(
    session: Session,
    *,
    tenant_id: str,
    allowed: bool,
    actor: User,
    source: str,
    document_ref: str | None = None,
    notes: str | None = None,
) -> DataConsent:
    """Grava a decisão, audita e, se for NÃO, retira as amostras do caminho do treino.

    Não faz *commit*.
    """
    if source not in ORIGENS:
        raise ConsentError(f"Origem do consentimento desconhecida: {source!r}.")
    if source == "contrato" and not (document_ref or "").strip():
        raise ConsentError(
            "Registro feito pela ValTexa precisa citar o termo ou contrato que o embasa."
        )

    anterior = vigente(session, tenant_id)
    agora = datetime.now(UTC)
    decisao = DataConsent(
        tenant_id=tenant_id,
        allowed=allowed,
        decided_at=agora,
        decided_by=actor.id,
        decided_by_label=actor.email,
        source=source,
        document_ref=(document_ref or "").strip() or None,
        notes=notes,
    )
    session.add(decisao)
    session.flush()

    retiradas = 0 if allowed else _retirar_amostras(session, tenant_id, agora)
    audit.record(
        session,
        tenant_id=tenant_id,
        action="consent.changed",
        subject_type=SubjectType.DATA_CONSENT,
        subject_id=decisao.id,
        actor_type=ActorType.USER,
        actor_id=actor.id,
        actor_label=actor.email,
        old_state=_rotulo(anterior.allowed) if anterior else "nao_decidido",
        new_state=_rotulo(allowed),
        reason=notes,
        payload={
            "source": source,
            "document_ref": decisao.document_ref,
            "amostras_retiradas": retiradas,
        },
    )
    return decisao


def _retirar_amostras(session: Session, tenant_id: str, quando: datetime) -> int:
    amostras = session.scalars(
        select(DatasetSample).where(
            DatasetSample.tenant_id == tenant_id,
            DatasetSample.state != DatasetSampleState.EXCLUDED,
        )
    ).all()
    marca = f"[consentimento revogado em {quando:%Y-%m-%d}]"
    for amostra in amostras:
        amostra.state = DatasetSampleState.EXCLUDED
        amostra.notes = f"{amostra.notes} {marca}".strip() if amostra.notes else marca
    if amostras:
        logger.info(
            "Consentimento revogado: %d amostra(s) do cliente %s fora do treino.",
            len(amostras),
            tenant_id,
        )
    return len(amostras)


def _rotulo(allowed: bool) -> str:
    return "sim" if allowed else "nao"
