"""Gêmeo digital, auditoria e barramento de eventos."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from valtexa.api.arquivos import resposta_de_arquivo
from valtexa.api.deps import Principal, get_scoped, require
from valtexa.db import get_session
from valtexa.models import Asset, AuditEntry, Field, OutboxEvent, RowScan
from valtexa.schemas import (
    AnomalyOut,
    AuditOut,
    ClassCountOut,
    FieldSceneOut,
    FieldSnapshotOut,
    OutboxEventOut,
    RowScanOut,
    TimePointOut,
)
from valtexa.security import rbac
from valtexa.services import plans, scene, storage, twin, visao_operacional

router = APIRouter(tags=["gêmeo digital"])


@router.get(
    "/fields/{field_id}/scene",
    response_model=FieldSceneOut,
    summary="Cópia 3D do talhão",
)
def field_scene(
    field_id: str,
    at: datetime | None = Query(
        default=None, description="Estado da cópia neste instante. Sem ele, agora."
    ),
    days: int = Query(default=30, ge=1, le=365, description="Janela das observações."),
    principal: Principal = Depends(require(rbac.FARM_READ)),
    session: Session = Depends(get_session),
) -> FieldSceneOut:
    """A cópia 3D do talhão, montada rua a rua pelas passadas do rover.

    Cada rua mostra a passada mais recente que a cobriu; o que o rover ainda não
    percorreu fica vazio, e ``coverage_ratio`` diz quanto do talhão já tem
    cópia. As fotos diagnosticadas vêm como marcadores presos à planta
    fotografada, com a categoria — saudável, doença, praga, aguardando agrônomo
    ou outro achado.

    Quem não pode ler diagnóstico recebe a cópia sem os marcadores.
    """
    field_row = get_scoped(session, Field, field_id, principal)
    plans.exigir_recurso(session, principal.tenant_id, "lavoura_3d")
    data = scene.build(
        session,
        principal.tenant_id,
        field_row,
        at=at,
        days=days,
        include_diagnoses=principal.can(rbac.DIAGNOSIS_READ),
    )
    return FieldSceneOut.model_validate(data)


@router.get(
    "/fields/{field_id}/row-scans",
    response_model=list[RowScanOut],
    summary="Passadas do rover no talhão",
)
def row_scans(
    field_id: str,
    limit: int = Query(default=100, ge=1, le=1000),
    principal: Principal = Depends(require(rbac.FARM_READ)),
    session: Session = Depends(get_session),
) -> list[RowScanOut]:
    """As passadas, da mais recente à mais antiga."""
    get_scoped(session, Field, field_id, principal)
    plans.exigir_recurso(session, principal.tenant_id, "lavoura_3d")
    rows = session.scalars(
        select(RowScan)
        .where(RowScan.tenant_id == principal.tenant_id, RowScan.field_id == field_id)
        .order_by(RowScan.captured_at.desc())
        .limit(limit)
    )
    return [RowScanOut(**scene.scan_summary(row)) for row in rows]


@router.get(
    "/row-scans/{scan_id}/pointcloud",
    response_class=Response,
    summary="Nuvem de pontos de uma passada",
)
def row_scan_pointcloud(
    scan_id: str,
    principal: Principal = Depends(require(rbac.FARM_READ)),
    session: Session = Depends(get_session),
) -> Response:
    """O PLY que o rover enviou, sem conversão.

    Servido por aqui, e não por link direto ao armazenamento, pelo mesmo motivo
    da imagem: o acesso passa pelo escopo do cliente. O arquivo nunca muda
    depois de gravado, então o navegador pode guardá-lo.
    """
    scan_row = get_scoped(session, RowScan, scan_id, principal)
    plans.exigir_recurso(session, principal.tenant_id, "lavoura_3d")
    if not scan_row.pointcloud_asset_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Passada sem nuvem de pontos.")
    asset = get_scoped(session, Asset, scan_row.pointcloud_asset_id, principal)
    try:
        data = storage.store.read(asset.storage_key)
    except storage.UnknownAssetError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Arquivo ausente no armazenamento.") from exc
    return resposta_de_arquivo(data, asset.content_type, cache="private, max-age=86400",
                               nome=f"passada-{scan_id}.ply")


@router.get(
    "/fields/{field_id}/snapshot",
    response_model=FieldSnapshotOut,
    summary="Estado atual de um talhão",
)
def snapshot(
    field_id: str,
    days: int = Query(default=7, ge=1, le=90),
    principal: Principal = Depends(require(rbac.FARM_READ)),
    session: Session = Depends(get_session),
) -> FieldSnapshotOut:
    """Retrato do talhão na janela pedida."""
    get_scoped(session, Field, field_id, principal)
    data = twin.field_snapshot(session, principal.tenant_id, field_id, days=days)
    return FieldSnapshotOut(
        field_id=data.field_id,
        field_name=data.field_name,
        crop=data.crop,
        since=data.since,
        until=data.until,
        observations=data.observations,
        diagnosed=data.diagnosed,
        needs_review=data.needs_review,
        classes=[
            ClassCountOut(label=item.label, count=item.count, ratio=item.ratio)
            for item in data.classes
        ],
    )


@router.get(
    "/fields/{field_id}/timeline",
    response_model=list[TimePointOut],
    summary="Série temporal do talhão",
)
def timeline(
    field_id: str,
    days: int = Query(default=30, ge=1, le=365),
    principal: Principal = Depends(require(rbac.FARM_READ)),
    session: Session = Depends(get_session),
) -> list[TimePointOut]:
    """Evolução diária dos diagnósticos.

    É a informação que muda a decisão do produtor. Uma foto diz que há ferrugem;
    a série diz que a incidência saiu de 4% para 31% em nove dias.
    """
    get_scoped(session, Field, field_id, principal)
    points = twin.timeline(session, principal.tenant_id, field_id, days=days)
    return [TimePointOut(day=p.day, total=p.total, counts=p.counts) for p in points]


@router.get("/fields/{field_id}/history", summary="Linha do tempo do talhão (ciclo completo)")
def field_history(
    field_id: str,
    missions: int = Query(default=30, ge=1, le=200, description="Quantas missões, das mais novas."),
    principal: Principal = Depends(require(rbac.DIAGNOSIS_READ)),
    session: Session = Depends(get_session),
) -> list[dict]:
    """Missão → ocorrências → prescrição → aprovação → aplicação → verificação.

    Do mais recente ao mais antigo; cada passo traz os IDs que ligam um ao outro.
    """
    get_scoped(session, Field, field_id, principal)
    return visao_operacional.linha_do_tempo(session, principal.tenant_id, field_id,
                                            limite_missoes=missions)


@router.get(
    "/fields/{field_id}/anomalies",
    response_model=list[AnomalyOut],
    summary="Desvios estatísticos do talhão",
)
def anomalies(
    field_id: str,
    current_days: int = Query(default=7, ge=1, le=90),
    baseline_days: int = Query(default=30, ge=7, le=365),
    principal: Principal = Depends(require(rbac.FARM_READ)),
    session: Session = Depends(get_session),
) -> list[AnomalyOut]:
    """Compara a janela recente com a linha de base do próprio talhão.

    **É a detecção que funciona quando a de novidade falha.** Está medido em
    ``VALTEXA-B/MODELS.md``: diante de uma doença real fora do catálogo, os
    filtros de novidade e confiança interceptam 19% dos casos — o modelo
    responde com 0,88 de confiança média e o erro passa. Uma imagem por vez, não
    há como notar.

    O que o erro **não** consegue esconder é a estatística. Uma doença nova
    classificada consistentemente como "ferrugem comum" faz a ferrugem comum
    daquele talhão saltar de 5% para 40% de uma semana para a outra, e é
    exatamente isso que esta rota procura.

    O que ela não faz é dizer *o que* mudou. Ela diz que mudou e manda um
    agrônomo olhar — para o modo de falha que cobre, é o suficiente.
    """
    get_scoped(session, Field, field_id, principal)
    found = twin.anomalies(
        session,
        principal.tenant_id,
        field_id,
        current_days=current_days,
        baseline_days=baseline_days,
    )
    return [
        AnomalyOut(
            field_id=item.field_id,
            zone_id=item.zone_id,
            label=item.label,
            baseline_ratio=item.baseline_ratio,
            current_ratio=item.current_ratio,
            baseline_sample=item.baseline_sample,
            current_sample=item.current_sample,
            detail=item.detail,
        )
        for item in found
    ]


@router.get("/audit", response_model=list[AuditOut], summary="Trilha de auditoria")
def audit_log(
    subject_type: str | None = None,
    subject_id: str | None = None,
    action: str | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
    principal: Principal = Depends(require(rbac.AUDIT_READ)),
    session: Session = Depends(get_session),
) -> list[AuditOut]:
    """Quem fez o quê, quando e por quê.

    É a resposta à pergunta que a fiscalização faz: "por que este produto foi
    aplicado neste talhão neste dia?".
    """
    statement = (
        select(AuditEntry)
        .where(AuditEntry.tenant_id == principal.tenant_id)
        .order_by(AuditEntry.at.desc())
        .limit(limit)
    )
    if subject_type:
        statement = statement.where(AuditEntry.subject_type == subject_type)
    if subject_id:
        statement = statement.where(AuditEntry.subject_id == subject_id)
    if action:
        statement = statement.where(AuditEntry.action == action)

    return [
        AuditOut(
            id=row.id,
            at=row.at,
            actor_type=str(row.actor_type),
            actor_id=row.actor_id,
            actor_label=row.actor_label,
            action=row.action,
            subject_type=str(row.subject_type),
            subject_id=row.subject_id,
            old_state=row.old_state,
            new_state=row.new_state,
            reason=row.reason,
            rule_version=row.rule_version,
            model_version=row.model_version,
            payload=row.payload,
            tenant_id=row.tenant_id,
            support_session_id=row.support_session_id,
        )
        for row in session.scalars(statement)
    ]


@router.get("/events", response_model=list[OutboxEventOut], summary="Eventos de domínio")
def list_events(
    pending_only: bool = False,
    limit: int = Query(default=100, ge=1, le=1000),
    principal: Principal = Depends(require(rbac.AUDIT_READ)),
    session: Session = Depends(get_session),
) -> list[OutboxEventOut]:
    """Fila do *outbox*.

    Exposta para operação: um evento parado com ``last_error`` preenchido é a
    primeira pista de que uma integração quebrou.
    """
    statement = (
        select(OutboxEvent)
        .where(OutboxEvent.tenant_id == principal.tenant_id)
        .order_by(OutboxEvent.created_at.desc())
        .limit(limit)
    )
    if pending_only:
        statement = statement.where(OutboxEvent.delivered_at.is_(None))

    return [
        OutboxEventOut(
            id=row.id,
            name=row.name,
            subject_type=str(row.subject_type) if row.subject_type else None,
            subject_id=row.subject_id,
            payload=row.payload,
            created_at=row.created_at,
            delivered_at=row.delivered_at,
            attempts=row.attempts,
            last_error=row.last_error,
        )
        for row in session.scalars(statement)
    ]
