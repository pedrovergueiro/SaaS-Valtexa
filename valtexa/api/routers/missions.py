"""Missões: criar, aprovar, autorizar, despachar, abortar.

A separação de responsabilidades está nas dependências de cada rota e é a
espinha do produto:

* criar uma missão — ``mission:create``;
* **aprovar uma pulverização** — ``mission:approve_application``, só o agrônomo;
* autorizar (rodar a segurança) — ``mission:dispatch``;
* despachar ao robô — ``mission:dispatch``;
* abortar — quase todo mundo, porque parar nunca pode depender de permissão rara.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from valtexa.api.deps import Principal, get_scoped, require, scoped
from valtexa.db import get_session
from valtexa.models import (
    ActorType,
    Device,
    Field,
    Mission,
    MissionKind,
    MissionSegment,
    MissionState,
    SafetyEvaluation,
    SegmentState,
    SubjectType,
)
from valtexa.schemas import (
    AbortRequest,
    MissionApproval,
    MissionCreate,
    MissionOut,
    MissionSegmentOut,
    SafetyCheckOut,
    SafetyEvaluationOut,
    SignedCommandOut,
)
from valtexa.security import rbac
from valtexa.services import audit, geo, mission_manager, safety_engine

router = APIRouter(tags=["missões"])


@router.get("/missions", response_model=list[MissionOut], summary="Lista missões")
def list_missions(
    state: MissionState | None = None,
    device_id: str | None = None,
    field_id: str | None = None,
    limit: int = 100,
    principal: Principal = Depends(require(rbac.MISSION_READ)),
    session: Session = Depends(get_session),
) -> list[MissionOut]:
    statement = scoped(
        select(Mission).order_by(Mission.created_at.desc()).limit(min(limit, 500)),
        Mission,
        principal,
    )
    if state is not None:
        statement = statement.where(Mission.state == state)
    if device_id is not None:
        statement = statement.where(Mission.device_id == device_id)
    if field_id is not None:
        statement = statement.where(Mission.field_id == field_id)
    return [_mission_out(session, row) for row in session.scalars(statement)]


@router.post(
    "/missions",
    response_model=MissionOut,
    status_code=status.HTTP_201_CREATED,
    summary="Cria uma missão",
)
def create_mission(
    payload: MissionCreate,
    principal: Principal = Depends(require(rbac.MISSION_CREATE)),
    session: Session = Depends(get_session),
) -> MissionOut:
    """Cria a missão em rascunho e planeja a cobertura.

    Nasce em ``DRAFT``, sem assinatura e sem valer nada no mundo físico. O
    caminho até o robô passa obrigatoriamente por aprovação (se for
    pulverização) e pela camada de segurança.
    """
    field_row = get_scoped(session, Field, payload.field_id, principal)
    device = get_scoped(session, Device, payload.device_id, principal)

    polygon = payload.target_polygon or field_row.boundary
    try:
        geo.as_points(polygon)
    except geo.InvalidPolygonError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc

    if payload.kind is MissionKind.SPRAY and not payload.product_id:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Missão de pulverização exige produto, lote, tanque e dose.",
        )

    mission = mission_manager.create_mission(
        session,
        tenant_id=principal.tenant_id,
        kind=payload.kind,
        field_row=field_row,
        device=device,
        target_polygon=polygon,
        created_by=principal.user_id,
        zone_id=payload.zone_id,
        plan=payload.plan,
        product_id=payload.product_id,
        product_batch_id=payload.product_batch_id,
        tank_id=payload.tank_id,
        authorized_rate_l_ha=payload.authorized_rate_l_ha,
        authorized_quantity_l=payload.authorized_quantity_l,
        decision_id=payload.decision_id,
    )
    session.commit()
    return _mission_out(session, mission)


@router.get("/missions/{mission_id}", response_model=MissionOut, summary="Uma missão")
def get_mission(
    mission_id: str,
    principal: Principal = Depends(require(rbac.MISSION_READ)),
    session: Session = Depends(get_session),
) -> MissionOut:
    return _mission_out(session, get_scoped(session, Mission, mission_id, principal))


@router.get(
    "/missions/{mission_id}/segments",
    response_model=list[MissionSegmentOut],
    summary="Segmentos da cobertura",
)
def list_segments(
    mission_id: str,
    principal: Principal = Depends(require(rbac.MISSION_READ)),
    session: Session = Depends(get_session),
) -> list[MissionSegmentOut]:
    get_scoped(session, Mission, mission_id, principal)
    rows = session.scalars(
        select(MissionSegment)
        .where(MissionSegment.mission_id == mission_id)
        .order_by(MissionSegment.index)
    )
    return [
        MissionSegmentOut(
            index=row.index,
            state=row.state.value,
            path=row.path,
            estimated_energy_percent=row.estimated_energy_percent,
        )
        for row in rows
    ]


@router.post(
    "/missions/{mission_id}/approve",
    response_model=MissionOut,
    summary="Aprovação do agrônomo para pulverizar",
)
def approve(
    mission_id: str,
    payload: MissionApproval,
    principal: Principal = Depends(require(rbac.MISSION_APPROVE_APPLICATION)),
    session: Session = Depends(get_session),
) -> MissionOut:
    """Registra quem assume a responsabilidade técnica pela aplicação.

    É o ponto em que uma recomendação de software vira produto químico no ar.
    Nenhum papel automático, nenhuma integração e nenhuma IA chega aqui — a
    capacidade é exclusiva do agrônomo, e o safety engine reconfere o papel na
    hora de autorizar, porque entre a assinatura e o voo o papel pode ter sido
    revogado.
    """
    mission = get_scoped(session, Mission, mission_id, principal)
    if mission.kind is not MissionKind.SPRAY:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Só missão de pulverização precisa de aprovação."
        )
    if not payload.confirm:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Confirmação explícita é obrigatória.")
    if mission.state in mission_manager.TERMINAL_STATES:
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"Missão já encerrada em {mission.state.value!r}."
        )

    mission.approved_by = principal.user_id
    mission.approved_at = datetime.now(UTC)
    audit.record(
        session,
        tenant_id=principal.tenant_id,
        action="mission.approved",
        subject_type=SubjectType.MISSION,
        subject_id=mission.id,
        actor_type=ActorType.USER,
        actor_id=principal.user_id,
        actor_label=principal.user.email,
        reason=payload.notes,
        payload={
            "product_id": mission.product_id,
            "rate_l_ha": mission.authorized_rate_l_ha,
            "role": principal.role.value,
        },
    )
    session.commit()
    return _mission_out(session, mission)


@router.post(
    "/missions/{mission_id}/authorize",
    response_model=SafetyEvaluationOut,
    summary="Roda a camada de segurança",
)
def authorize(
    mission_id: str,
    wind_ms: float | None = None,
    principal: Principal = Depends(require(rbac.MISSION_DISPATCH)),
    session: Session = Depends(get_session),
) -> SafetyEvaluationOut:
    """Submete a missão à camada de segurança.

    Devolve o parecer completo — inclusive as verificações que passaram. Quando
    bloqueia, o operador vê de uma vez tudo que falta, em vez de descobrir um
    impedimento por tentativa.
    """
    mission = get_scoped(session, Mission, mission_id, principal)
    mission_manager.authorize(session, mission, actor_id=principal.user_id, wind_ms=wind_ms)
    session.commit()

    evaluation = session.scalars(
        select(SafetyEvaluation)
        .where(
            SafetyEvaluation.subject_type == SubjectType.MISSION,
            SafetyEvaluation.subject_id == mission.id,
        )
        .order_by(SafetyEvaluation.created_at.desc())
        .limit(1)
    ).first()
    return _evaluation_out(evaluation)


@router.post(
    "/missions/{mission_id}/dispatch",
    response_model=SignedCommandOut,
    summary="Assina e despacha ao robô",
)
def dispatch(
    mission_id: str,
    principal: Principal = Depends(require(rbac.MISSION_DISPATCH)),
    session: Session = Depends(get_session),
) -> SignedCommandOut:
    """Emite o comando assinado.

    Devolvido aqui para inspeção e para o simulador; o robô o busca em
    ``GET /v1/device/missions/current``.
    """
    mission = get_scoped(session, Mission, mission_id, principal)
    try:
        envelope = mission_manager.dispatch(session, mission, actor_id=principal.user_id)
    except mission_manager.MissionNotAuthorizedError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    session.commit()
    return SignedCommandOut(**envelope)


@router.post(
    "/missions/{mission_id}/resume", response_model=SignedCommandOut, summary="Retoma do checkpoint"
)
def resume(
    mission_id: str,
    principal: Principal = Depends(require(rbac.MISSION_DISPATCH)),
    session: Session = Depends(get_session),
) -> SignedCommandOut:
    """Emite um comando novo com os segmentos que faltam."""
    mission = get_scoped(session, Mission, mission_id, principal)
    try:
        envelope = mission_manager.resume(session, mission, actor_id=principal.user_id)
    except mission_manager.MissionStateError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    session.commit()
    return SignedCommandOut(**envelope)


@router.post("/missions/{mission_id}/abort", response_model=MissionOut, summary="Aborta a missão")
def abort(
    mission_id: str,
    payload: AbortRequest,
    principal: Principal = Depends(require(rbac.MISSION_ABORT)),
    session: Session = Depends(get_session),
) -> MissionOut:
    """Interrompe a missão. Disponível a praticamente todos os papéis operacionais.

    Parar nunca deve depender de uma permissão rara: numa emergência, quem está
    perto do equipamento precisa conseguir agir.
    """
    mission = get_scoped(session, Mission, mission_id, principal)
    mission_manager.abort(
        session,
        mission,
        payload.reason,
        actor_type=ActorType.USER,
        actor_id=principal.user_id,
    )
    session.commit()
    return _mission_out(session, mission)


@router.get(
    "/missions/{mission_id}/safety",
    response_model=list[SafetyEvaluationOut],
    summary="Pareceres de segurança da missão",
)
def mission_safety(
    mission_id: str,
    principal: Principal = Depends(require(rbac.MISSION_READ)),
    session: Session = Depends(get_session),
) -> list[SafetyEvaluationOut]:
    """Histórico completo, não só o último.

    Ver que uma missão foi bloqueada três vezes antes de passar é informação
    operacional relevante — e é a primeira coisa que uma auditoria procura.
    """
    get_scoped(session, Mission, mission_id, principal)
    rows = session.scalars(
        select(SafetyEvaluation)
        .where(
            SafetyEvaluation.subject_type == SubjectType.MISSION,
            SafetyEvaluation.subject_id == mission_id,
        )
        .order_by(SafetyEvaluation.created_at.desc())
    )
    return [_evaluation_out(row) for row in rows]


@router.post(
    "/missions/{mission_id}/safety/preview",
    response_model=SafetyEvaluationOut,
    summary="Simula a avaliação sem mudar nada",
)
def preview_safety(
    mission_id: str,
    wind_ms: float | None = None,
    principal: Principal = Depends(require(rbac.MISSION_READ)),
    session: Session = Depends(get_session),
) -> SafetyEvaluationOut:
    """Roda as verificações sem gravar nem mudar o estado da missão.

    Serve para o operador ver o que falta enquanto ainda está montando a
    missão, sem sujar o histórico com bloqueios de rascunho.
    """
    mission = get_scoped(session, Mission, mission_id, principal)
    report = safety_engine.check_mission(session, mission, wind_ms=wind_ms)
    session.rollback()
    return SafetyEvaluationOut(
        id="preview",
        subject_type=SubjectType.MISSION.value,
        subject_id=mission.id,
        verdict=report.verdict,
        blocked_code=report.blocked_code,
        blocked_reason=report.blocked_reason,
        checks=[SafetyCheckOut(**check.as_dict()) for check in report.checks],
        engine_version=safety_engine.ENGINE_VERSION,
        created_at=datetime.now(UTC),
    )


def _evaluation_out(row: SafetyEvaluation | None) -> SafetyEvaluationOut:
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nenhum parecer de segurança registrado.")
    return SafetyEvaluationOut(
        id=row.id,
        subject_type=row.subject_type.value,
        subject_id=row.subject_id,
        verdict=row.verdict,
        blocked_code=row.blocked_code,
        blocked_reason=row.blocked_reason,
        checks=[SafetyCheckOut(**check) for check in row.checks],
        engine_version=row.engine_version,
        created_at=row.created_at,
    )


def _mission_out(session: Session, mission: Mission) -> MissionOut:
    total, done = session.execute(
        select(
            func.count(MissionSegment.id),
            func.sum(case((MissionSegment.state == SegmentState.DONE, 1), else_=0)),
        ).where(MissionSegment.mission_id == mission.id)
    ).one()
    return MissionOut(
        id=mission.id,
        kind=mission.kind,
        state=mission.state,
        farm_id=mission.farm_id,
        field_id=mission.field_id,
        zone_id=mission.zone_id,
        device_id=mission.device_id,
        target_polygon=mission.target_polygon,
        plan=mission.plan,
        product_id=mission.product_id,
        tank_id=mission.tank_id,
        authorized_rate_l_ha=mission.authorized_rate_l_ha,
        authorized_quantity_l=mission.authorized_quantity_l,
        created_by=mission.created_by,
        approved_by=mission.approved_by,
        authorized_at=mission.authorized_at,
        expires_at=mission.expires_at,
        safety_status=mission.safety_status,
        safety_reason=mission.safety_reason,
        energy_policy=mission.energy_policy,
        offline_policy=mission.offline_policy,
        segments_total=total or 0,
        segments_done=int(done or 0),
        created_at=mission.created_at,
    )

