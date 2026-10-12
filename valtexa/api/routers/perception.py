"""Observações, diagnósticos, fila do agrônomo e decisões.

A fila de revisão é o motor do dataset próprio. Tudo que a dupla validação não
fechou para aqui, e o rótulo que o agrônomo escreve **não precisa existir no
catálogo do modelo** — é exatamente assim que uma doença que a IA não conhecia
entra no treino da versão seguinte.
"""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from valtexa.api.arquivos import resposta_de_arquivo
from valtexa.api.deps import Principal, get_scoped, require, scoped
from valtexa.api.routers.edge_arquivos import link_de_download
from valtexa.db import get_session
from valtexa.models import (
    ActorType,
    Asset,
    Decision,
    Detection,
    Diagnosis,
    DiagnosisStatus,
    Observation,
    SubjectType,
)
from valtexa.schemas import (
    DecisionOut,
    DetectionOut,
    DiagnosisOut,
    DiagnosisReview,
    LinkDeArquivoOut,
    ObservationOut,
)
from valtexa.security import rbac
from valtexa.services import (
    audit,
    collections,
    dataset,
    decision_engine,
    events,
    review_priority,
    storage,
)

router = APIRouter(tags=["percepção"])


@router.get("/observations", response_model=list[ObservationOut], summary="Observações")
def list_observations(
    field_id: str | None = None,
    mission_id: str | None = None,
    zone_id: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = 200,
    principal: Principal = Depends(require(rbac.DIAGNOSIS_READ)),
    session: Session = Depends(get_session),
) -> list[ObservationOut]:
    """Observações, da mais recente à mais antiga.

    ``since``/``until`` recortam a janela — é o que a comparação antes/depois de
    um tratamento usa. Teto de 2 000 por página: o suficiente para pintar um
    talhão no mapa.
    """
    statement = scoped(
        select(Observation).order_by(Observation.captured_at.desc()).limit(min(limit, 2000)),
        Observation,
        principal,
    )
    if field_id:
        statement = statement.where(Observation.field_id == field_id)
    if mission_id:
        statement = statement.where(Observation.mission_id == mission_id)
    if zone_id:
        statement = statement.where(Observation.zone_id == zone_id)
    if since:
        statement = statement.where(Observation.captured_at >= since)
    if until:
        statement = statement.where(Observation.captured_at <= until)

    rows = list(session.scalars(statement))
    diagnoses = _diagnoses_for(session, [row.id for row in rows])
    return [_observation_out(row, diagnoses.get(row.id)) for row in rows]


@router.get(
    "/observations/{observation_id}/image",
    summary="A imagem de uma observação",
    response_class=Response,
)
def observation_image(
    observation_id: str,
    principal: Principal = Depends(require(rbac.DIAGNOSIS_READ)),
    session: Session = Depends(get_session),
) -> Response:
    """Devolve o arquivo, para o agrônomo olhar antes de diagnosticar.

    A imagem é servida por esta rota e não por URL direta do armazenamento
    porque o acesso precisa passar pelo escopo do cliente. O link assinado
    direto ao bucket existe em ``.../image/url`` (Parte 9): emitido só depois do
    mesmo escopo, curto (``S3_PRESIGN_SECONDS``) e preso à chave do objeto.
    """
    observation = get_scoped(session, Observation, observation_id, principal)
    if not observation.image_asset_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Observação sem imagem.")

    asset = get_scoped(session, Asset, observation.image_asset_id, principal)
    try:
        data = storage.store.read(asset.storage_key)
    except storage.UnknownAssetError as exc:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "Arquivo ausente no armazenamento."
        ) from exc
    return resposta_de_arquivo(data, asset.content_type, nome=f"observacao-{observation_id}")


@router.get(
    "/observations/{observation_id}/image/url",
    response_model=LinkDeArquivoOut,
    summary="Link de download da imagem: URL assinada e curta do object storage (com S3)",
)
def observation_image_url(
    observation_id: str,
    principal: Principal = Depends(require(rbac.DIAGNOSIS_READ)),
    session: Session = Depends(get_session),
) -> LinkDeArquivoOut:
    """O escopo do cliente é conferido antes de assinar (Parte 9, seção 38)."""
    observation = get_scoped(session, Observation, observation_id, principal)
    if not observation.image_asset_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Observação sem imagem.")
    asset = get_scoped(session, Asset, observation.image_asset_id, principal)
    return link_de_download(
        asset, f"/v1/observations/{observation_id}/image", f"observacao-{observation_id}"
    )


@router.get("/diagnoses", response_model=list[DiagnosisOut], summary="Diagnósticos")
def list_diagnoses(
    status_filter: DiagnosisStatus | None = None,
    field_id: str | None = None,
    limit: int = 100,
    principal: Principal = Depends(require(rbac.DIAGNOSIS_READ)),
    session: Session = Depends(get_session),
) -> list[DiagnosisOut]:
    statement = scoped(
        select(Diagnosis).order_by(Diagnosis.created_at.desc()).limit(min(limit, 500)),
        Diagnosis,
        principal,
    )
    if status_filter is not None:
        statement = statement.where(Diagnosis.status == status_filter)
    if field_id:
        statement = statement.where(Diagnosis.field_id == field_id)
    return [_diagnosis_out(session, row) for row in session.scalars(statement)]


@router.get("/diagnoses/{diagnosis_id}", response_model=DiagnosisOut, summary="Um diagnóstico")
def get_diagnosis(
    diagnosis_id: str,
    principal: Principal = Depends(require(rbac.DIAGNOSIS_READ)),
    session: Session = Depends(get_session),
) -> DiagnosisOut:
    """O diagnóstico com as análises e o que cada uma disse além do rótulo.

    A lista de observações não traz ``signals`` — num quadro do rover eles
    carregam os recortes por zona e as plantas, pesado demais para o mapa inteiro.
    O console busca aqui quando alguém abre uma observação.
    """
    return _diagnosis_out(session, get_scoped(session, Diagnosis, diagnosis_id, principal))


@router.get(
    "/review/queue",
    response_model=list[DiagnosisOut],
    summary="Fila do agrônomo",
)
def review_queue(
    limit: int = 50,
    order: Literal["novidade", "valor"] = Query(
        default="novidade",
        description=(
            "'novidade': o que mais destoa primeiro. 'valor': o que mais ensina ao próximo "
            "treino primeiro — fora do escopo, discordância, incerteza, classe rara —, com "
            "o motivo de cada item."
        ),
    ),
    principal: Principal = Depends(require(rbac.DIAGNOSIS_READ)),
    session: Session = Depends(get_session),
) -> list[DiagnosisOut]:
    """O que a máquina não conseguiu fechar sozinha.

    Ordenada por novidade decrescente: o que mais destoa do que os modelos
    conhecem aparece primeiro, porque é o material que mais ensina.

    A fila crescer não é falha — é o desenho. Enquanto não houver um segundo
    analisador de fato independente, **nada** é validado sozinho. Ver
    :func:`valtexa.services.ai_pipeline.default_analyzers`.
    """
    pending = (
        select(Diagnosis)
        .where(Diagnosis.status.in_([DiagnosisStatus.NEEDS_REVIEW, DiagnosisStatus.INCONCLUSIVE]))
        .where(Diagnosis.reviewed_at.is_(None))
    )
    if order == "valor":
        return _review_by_value(session, principal, pending, min(limit, 200))
    statement = scoped(
        pending.order_by(
            Diagnosis.novelty_score.desc().nullslast(), Diagnosis.created_at.desc()
        ).limit(min(limit, 200)),
        Diagnosis,
        principal,
    )
    return [_diagnosis_out(session, row) for row in session.scalars(statement)]


REVIEW_VALUE_WINDOW = 1000
"""Quantos pendentes, dos mais recentes, entram na ordenação por valor."""


def _review_by_value(session: Session, principal: Principal, pending, limit: int):
    """A fila ordenada pelo que mais ensina — ver :mod:`valtexa.services.review_priority`."""
    candidates = list(
        session.scalars(
            scoped(
                pending.order_by(Diagnosis.created_at.desc()).limit(REVIEW_VALUE_WINDOW),
                Diagnosis,
                principal,
            )
        )
    )
    reviewed = Counter(
        session.scalars(
            scoped(
                select(Diagnosis.reviewed_label).where(Diagnosis.reviewed_label.is_not(None)),
                Diagnosis,
                principal,
            )
        )
    )
    # Uma consulta para as análises primárias de todos, e não uma por item.
    ids = [row.primary_detection_id for row in candidates if row.primary_detection_id]
    query = select(Detection).where(Detection.id.in_(ids))
    primaries = {detection.id: detection for detection in session.scalars(query)} if ids else {}
    ranked = [
        (review_priority.priority(row, primaries.get(row.primary_detection_id), reviewed), row)
        for row in candidates
    ]
    ranked.sort(key=lambda item: item[0].score, reverse=True)
    out = []
    for prio, row in ranked[:limit]:
        item = _diagnosis_out(session, row)
        item.priority_score = prio.score
        item.priority_reasons = prio.reasons
        out.append(item)
    return out


@router.post(
    "/diagnoses/{diagnosis_id}/review",
    response_model=DiagnosisOut,
    summary="Veredito do agrônomo",
)
def review(
    diagnosis_id: str,
    payload: DiagnosisReview,
    principal: Principal = Depends(require(rbac.DIAGNOSIS_REVIEW)),
    session: Session = Depends(get_session),
) -> DiagnosisOut:
    """Grava o diagnóstico humano e refaz a decisão com base nele.

    O rótulo é livre: pode ser um nome que o modelo não conhece. É o caminho
    pelo qual uma doença nova entra no dataset próprio, e é a única correção
    possível para o modo de falha medido — um modelo respondendo com alta
    confiança sobre algo que nunca viu.
    """
    diagnosis = get_scoped(session, Diagnosis, diagnosis_id, principal)
    previous = diagnosis.status

    diagnosis.reviewed_label = payload.label
    diagnosis.reviewed_by = principal.user_id
    diagnosis.reviewed_at = datetime.now(UTC)
    diagnosis.review_notes = payload.notes
    diagnosis.status = (
        DiagnosisStatus.HUMAN_CONFIRMED if payload.confirmed else DiagnosisStatus.HUMAN_REJECTED
    )

    session.add(
        Detection(
            tenant_id=diagnosis.tenant_id,
            observation_id=diagnosis.observation_id,
            source="human",
            analyzer=f"agronomist:{principal.user_id}",
            label=payload.label,
            confidence=1.0,
        )
    )

    audit.record(
        session,
        tenant_id=principal.tenant_id,
        action="diagnosis.reviewed",
        subject_type=SubjectType.DIAGNOSIS,
        subject_id=diagnosis.id,
        actor_type=ActorType.USER,
        actor_id=principal.user_id,
        actor_label=principal.user.email,
        old_state=previous.value,
        new_state=diagnosis.status.value,
        reason=payload.notes,
        payload={"machine_label": diagnosis.label, "human_label": payload.label},
    )
    events.publish(
        session,
        events.DIAGNOSIS_REVIEWED,
        tenant_id=principal.tenant_id,
        subject_type=SubjectType.DIAGNOSIS,
        subject_id=diagnosis.id,
        payload={
            "label": payload.label,
            "machine_label": diagnosis.label,
            "agreed": payload.label == diagnosis.label,
        },
    )

    # O rótulo do agrônomo vira amostra do dataset proprietário. É o único
    # caminho pelo qual uma doença fora do catálogo entra no treino — e é por
    # isso que ele acontece aqui, na mesma transação do veredito: uma anotação
    # que se perdesse por falha depois do commit seria uma perda irrecuperável,
    # porque ninguém revisa a mesma imagem duas vezes.
    dataset.record_review(session, diagnosis, principal.user)

    # Se a imagem veio de uma coleta, o veredito fecha aquele arquivo. É assim
    # que uma coleta aérea — que nenhum modelo sabe analisar — chega a
    # "analisada": por decisão de gente, registrada com nome.
    collections.on_diagnosis_reviewed(session, diagnosis)

    # A revisão muda o insumo da decisão, então a decisão é refeita. A anterior
    # continua no banco: apagar apagaria o porquê da recomendação antiga.
    decision = decision_engine.evaluate(session, diagnosis)
    session.add(decision)
    session.commit()
    return _diagnosis_out(session, diagnosis)


@router.get("/decisions", response_model=list[DecisionOut], summary="Recomendações")
def list_decisions(
    field_id: str | None = None,
    outcome: str | None = None,
    limit: int = 100,
    principal: Principal = Depends(require(rbac.DECISION_READ)),
    session: Session = Depends(get_session),
) -> list[DecisionOut]:
    statement = scoped(
        select(Decision).order_by(Decision.created_at.desc()).limit(min(limit, 500)),
        Decision,
        principal,
    )
    if field_id:
        statement = statement.where(Decision.field_id == field_id)
    if outcome:
        statement = statement.where(Decision.outcome == outcome)
    return [_decision_out(row) for row in session.scalars(statement)]


@router.post(
    "/diagnoses/{diagnosis_id}/decide",
    response_model=DecisionOut,
    summary="Roda o motor de decisão",
)
def decide(
    diagnosis_id: str,
    principal: Principal = Depends(require(rbac.DECISION_READ)),
    session: Session = Depends(get_session),
) -> DecisionOut:
    """Avalia um diagnóstico e grava a recomendação.

    Recomendação, não ordem: mesmo ``APPLICATION_CANDIDATE`` ainda precisa da
    aprovação do agrônomo e do parecer da camada de segurança.
    """
    diagnosis = get_scoped(session, Diagnosis, diagnosis_id, principal)
    decision = decision_engine.evaluate(session, diagnosis)
    session.add(decision)
    events.publish(
        session,
        events.DECISION_CREATED,
        tenant_id=principal.tenant_id,
        subject_type=SubjectType.DECISION,
        subject_id=decision.id,
        payload={"outcome": decision.outcome.value, "reason": decision.reason_code},
    )
    session.commit()
    return _decision_out(decision)


def _diagnoses_for(session: Session, observation_ids: list[str]) -> dict[str, Diagnosis]:
    """Diagnóstico mais recente de cada observação, numa consulta só."""
    if not observation_ids:
        return {}
    rows = session.scalars(
        select(Diagnosis)
        .where(Diagnosis.observation_id.in_(observation_ids))
        .order_by(Diagnosis.created_at)
    )
    return {row.observation_id: row for row in rows}


def _observation_out(row: Observation, diagnosis: Diagnosis | None) -> ObservationOut:
    return ObservationOut(
        id=row.id,
        field_id=row.field_id,
        zone_id=row.zone_id,
        mission_id=row.mission_id,
        device_id=row.device_id,
        collection_id=row.collection_id,
        captured_at=row.captured_at,
        lat=row.lat,
        lon=row.lon,
        image_asset_id=row.image_asset_id,
        diagnosis_id=diagnosis.id if diagnosis else None,
        diagnosis_status=diagnosis.status if diagnosis else None,
        label=diagnosis.effective_label if diagnosis else None,
        confidence=diagnosis.confidence if diagnosis else None,
        novelty_score=diagnosis.novelty_score if diagnosis else None,
        severity=diagnosis.severity if diagnosis else None,
    )


def _diagnosis_out(session: Session, row: Diagnosis) -> DiagnosisOut:
    detections = session.scalars(
        select(Detection).where(Detection.observation_id == row.observation_id)
    )
    return DiagnosisOut(
        id=row.id,
        observation_id=row.observation_id,
        field_id=row.field_id,
        zone_id=row.zone_id,
        status=row.status,
        agreement=row.agreement.value,
        label=row.label,
        effective_label=row.effective_label,
        confidence=row.confidence,
        novelty_score=row.novelty_score,
        severity=row.severity,
        rationale=row.rationale,
        pipeline_version=row.pipeline_version,
        reviewed_by=row.reviewed_by,
        reviewed_at=row.reviewed_at,
        reviewed_label=row.reviewed_label,
        created_at=row.created_at,
        detections=[
            DetectionOut(
                id=item.id,
                source=str(item.source),
                analyzer=item.analyzer,
                model_key=item.model_key,
                label=item.label,
                confidence=item.confidence,
                novelty_score=item.novelty_score,
                abstained=item.abstained,
                probabilities=item.probabilities,
                latency_ms=item.latency_ms,
                error=item.error,
                signals=item.signals or {},
            )
            for item in detections
        ],
    )


def _decision_out(row: Decision) -> DecisionOut:
    return DecisionOut(
        id=row.id,
        diagnosis_id=row.diagnosis_id,
        field_id=row.field_id,
        zone_id=row.zone_id,
        outcome=row.outcome,
        reason_code=row.reason_code,
        rationale=row.rationale,
        rule_version=row.rule_version,
        recommended_product_id=row.recommended_product_id,
        recommended_rate_l_ha=row.recommended_rate_l_ha,
        affected_ratio=row.affected_ratio,
        sample_size=row.sample_size,
        mission_id=row.mission_id,
        inputs=row.inputs,
        created_at=row.created_at,
    )
