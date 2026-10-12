"""Observabilidade e alertas (brief, seções 34 e 35).

* ``GET /metrics`` — formato Prometheus. **Protegido**: ``Authorization: Bearer
  <METRICS_TOKEN>`` (o do Prometheus, vindo do ambiente) ou o login de alguém da
  equipe com ``platform:observability:read``. Sem dado agronômico: contagens,
  latências, filas e saúde dos robôs (rotulados pelo id do cliente e pelo serial).
* ``/v1/platform/observability/**`` — o console interno:
  saúde por componente, API por rota, filas, IA (inferências, classes, *drift*),
  frota de todos os clientes, alertas e regras.
* ``/v1/observability/fleet``, ``/v1/observability/alerts`` e
  ``/v1/observability/alert-rules`` — o cliente vê
  **só o que é dele**: a saúde dos robôs dele, os alertas dos robôs dele e as regras
  de robô (com a versão própria, se o gestor ajustou). Nada da API, da IA ou de
  outro cliente.
"""

from __future__ import annotations

import hmac
from collections import Counter
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from valtexa.api.deps import (
    PlatformCaller,
    Principal,
    _equipe_do_token,
    _exige_capacidades_de_plataforma,
    require,
    require_platform,
)
from valtexa.config import settings
from valtexa.db import get_session
from valtexa.models import Alert, AlertRule, Tenant
from valtexa.observability import http as obs_http
from valtexa.observability.metricas import CONTENT_TYPE
from valtexa.schemas import (
    AiObservabilityOut,
    AlertAckIn,
    AlertRuleIn,
    AlertRuleOut,
    ApiStatsOut,
    ObsAlertOut,
    ObservabilityOverviewOut,
    RoverHealthOut,
)
from valtexa.security import rbac
from valtexa.services import alertas, observabilidade

router = APIRouter(tags=["observabilidade"])
metrics_router = APIRouter(tags=["observabilidade"])

ALERTA_NAO_ENCONTRADO = "Alerta não encontrado."

DRIFT_NOTA = (
    "Drift medido aqui é o da distribuição de classes previstas (saída do modelo), "
    "recente contra os 7 dias anteriores. O drift da entrada (imagens) exige a "
    "referência do treino, que vive com os pesos na VALTEXA-B: não medido."
)


# ---------------------------------------------------------------------------
# /metrics
# ---------------------------------------------------------------------------


def _autoriza_metrics(session: Session, authorization: str | None) -> None:
    esperado = settings.metrics_token
    if esperado and authorization and authorization.lower().startswith("bearer "):
        recebido = authorization.split(" ", 1)[1].strip()
        if hmac.compare_digest(recebido.encode(), esperado.encode()):
            return
    # Sem o token do Prometheus: só a equipe, logada, com a capacidade.
    user, _ = _equipe_do_token(session, authorization)
    _exige_capacidades_de_plataforma(user, (rbac.PLATFORM_OBSERVABILITY_READ,))


@metrics_router.get(
    "/metrics", summary="Métricas no formato do Prometheus (protegido)",
    response_class=Response,
    responses={200: {"content": {CONTENT_TYPE: {}}, "description": "Exposição 0.0.4"}},
)
def metrics(
    authorization: str | None = Header(default=None),
    session: Session = Depends(get_session),
) -> Response:
    """As do processo (HTTP desta réplica) e as do banco (filas, frota, IA, alertas).

    Com várias réplicas: raspe cada uma para as métricas HTTP e some no Prometheus
    (``sum by (route)``); as do banco são iguais em todas (ver
    ``deploy/observabilidade/prometheus.yml``).
    """
    _autoriza_metrics(session, authorization)
    texto = obs_http.REGISTRO.render(observabilidade.familias(session))
    return Response(content=texto, media_type=CONTENT_TYPE)


# ---------------------------------------------------------------------------
# Saída comum
# ---------------------------------------------------------------------------


def _nomes_de_cliente(session: Session, ids: set[str]) -> dict[str, str]:
    if not ids:
        return {}
    return dict(session.execute(select(Tenant.id, Tenant.name).where(Tenant.id.in_(ids))).all())


def _alert_out(a: Alert, nomes: dict[str, str] | None = None) -> ObsAlertOut:
    regra = alertas.REGRAS.get(a.kind)
    return ObsAlertOut(
        id=a.id, kind=a.kind, kind_label=regra.label if regra else a.kind, state=a.state,
        severity=a.severity, tenant_id=a.tenant_id,
        tenant_name=(nomes or {}).get(a.tenant_id) if a.tenant_id else None,
        subject_type=a.subject_type, subject_id=a.subject_id, subject_label=a.subject_label,
        message=a.message, value=a.value, threshold=a.threshold, fired_at=a.fired_at,
        last_seen_at=a.last_seen_at, acknowledged_at=a.acknowledged_at,
        acknowledged_label=a.acknowledged_label, ack_note=a.ack_note, resolved_at=a.resolved_at,
    )


def _consulta_alertas(state: str | None, kind: str | None, open_only: bool):
    consulta = select(Alert)
    if state:
        consulta = consulta.where(Alert.state == state)
    if kind:
        consulta = consulta.where(Alert.kind == kind)
    if open_only:
        consulta = consulta.where(Alert.state != "resolvido")
    return consulta


def _regra_out(kind: str, linha: AlertRule | None, padrao: AlertRule | None,
               fonte: str) -> AlertRuleOut:
    regra = alertas.REGRAS[kind]
    base = linha or padrao
    return AlertRuleOut(
        kind=kind, label=regra.label, description=regra.description, scope=regra.scope,
        unit=regra.unit, enabled=base.enabled if base else True,
        threshold=base.threshold if base else regra.threshold,
        window_minutes=base.window_minutes if base else regra.window_minutes,
        severity=base.severity if base else regra.severity,
        default_threshold=padrao.threshold if padrao else regra.threshold,
        source=fonte, updated_at=base.updated_at if base else None,
    )


def _regras(session: Session, tenant_id: str | None) -> list[AlertRuleOut]:
    alertas.sincronizar_catalogo(session)
    session.commit()
    linhas = {(r.tenant_id, r.kind): r for r in session.scalars(select(AlertRule))}
    saida = []
    for kind, regra in alertas.REGRAS.items():
        padrao = linhas.get((None, kind))
        if tenant_id is None:
            saida.append(_regra_out(kind, None, padrao, "padrao"))
        elif regra.scope == alertas.ROBO and kind not in alertas.SO_DA_EQUIPE:
            propria = linhas.get((tenant_id, kind))
            saida.append(_regra_out(kind, propria, padrao, "cliente" if propria else "padrao"))
    return saida


def _erro(exc: alertas.AlertError) -> HTTPException:
    return HTTPException(exc.status, str(exc))


def _abertos_por_robo(session: Session, tenant_id: str | None) -> Counter:
    consulta = select(Alert.subject_id, func.count()).where(
        Alert.subject_type == "device", Alert.state != "resolvido").group_by(Alert.subject_id)
    if tenant_id:
        consulta = consulta.where(Alert.tenant_id == tenant_id)
    return Counter(dict(session.execute(consulta).all()))


# ---------------------------------------------------------------------------
# Console da plataforma
# ---------------------------------------------------------------------------


@router.get("/platform/observability", response_model=ObservabilityOverviewOut,
            summary="Saúde por componente, API, filas, usuários e IA")
def platform_overview(
    minutes: int = Query(default=60, ge=1, le=24 * 60),
    _: PlatformCaller = Depends(require_platform(rbac.PLATFORM_OBSERVABILITY_READ)),
    session: Session = Depends(get_session),
) -> ObservabilityOverviewOut:
    agora = datetime.now(UTC)
    ia = observabilidade.estado_ia()
    abertos = session.scalar(
        select(func.count()).select_from(Alert).where(Alert.state != "resolvido")) or 0
    criticos = session.scalar(select(func.count()).select_from(Alert).where(
        Alert.state != "resolvido", Alert.severity == "critico")) or 0
    return ObservabilityOverviewOut(
        generated_at=agora,
        components=observabilidade.componentes(session, agora=agora, ia=ia),
        api=observabilidade.api(session, minutos=minutes, agora=agora),
        queues=observabilidade.filas(session, agora),
        users=observabilidade.usuarios_ativos(session, agora),
        ai_service=ia, alerts_open=abertos, alerts_critical=criticos,
    )


@router.get("/platform/observability/api", response_model=ApiStatsOut,
            summary="API por rota: requisições, erros e latência")
def platform_api_stats(
    minutes: int = Query(default=60, ge=1, le=7 * 24 * 60),
    _: PlatformCaller = Depends(require_platform(rbac.PLATFORM_OBSERVABILITY_READ)),
    session: Session = Depends(get_session),
) -> ApiStatsOut:
    return ApiStatsOut(**observabilidade.api(session, minutos=minutes))


@router.get("/platform/observability/fleet", response_model=list[RoverHealthOut],
            summary="Saúde dos robôs de todos os clientes")
def platform_fleet_health(
    tenant_id: str | None = Query(default=None, max_length=32),
    _: PlatformCaller = Depends(require_platform(rbac.PLATFORM_OBSERVABILITY_READ)),
    session: Session = Depends(get_session),
) -> list[RoverHealthOut]:
    abertos = _abertos_por_robo(session, tenant_id)
    return [RoverHealthOut(**r, open_alerts=abertos[r["device_id"]])
            for r in observabilidade.frota(session, tenant_id=tenant_id)]


@router.get("/platform/observability/ai", response_model=AiObservabilityOut,
            summary="IA: inferências, erros, latência, classes e drift por modelo")
def platform_ai_stats(
    hours: int = Query(default=24, ge=1, le=24 * 30),
    _: PlatformCaller = Depends(require_platform(rbac.PLATFORM_OBSERVABILITY_READ)),
    session: Session = Depends(get_session),
) -> AiObservabilityOut:
    return AiObservabilityOut(
        window_hours=hours, service=observabilidade.estado_ia(),
        cloud=observabilidade.ia_nuvem(session, hours),
        edge=observabilidade.ia_borda(session, hours),
        drift=observabilidade.drift(session, janela_horas=hours),
        drift_note=DRIFT_NOTA,
    )


@router.get("/platform/observability/alerts", response_model=list[ObsAlertOut],
            summary="Alertas")
def platform_alerts(
    state: str | None = Query(default=None, max_length=16),
    kind: str | None = Query(default=None, max_length=40),
    tenant_id: str | None = Query(default=None, max_length=32),
    open_only: bool = Query(default=False),
    limit: int = Query(default=200, ge=1, le=1000),
    _: PlatformCaller = Depends(require_platform(rbac.PLATFORM_OBSERVABILITY_READ)),
    session: Session = Depends(get_session),
) -> list[ObsAlertOut]:
    consulta = _consulta_alertas(state, kind, open_only)
    if tenant_id:
        consulta = consulta.where(Alert.tenant_id == tenant_id)
    linhas = list(session.scalars(consulta.order_by(Alert.fired_at.desc()).limit(limit)))
    nomes = _nomes_de_cliente(session, {a.tenant_id for a in linhas if a.tenant_id})
    return [_alert_out(a, nomes) for a in linhas]


@router.post("/platform/observability/alerts/{alert_id}/ack", response_model=ObsAlertOut,
             summary="Reconhece um alerta (alguém está cuidando)")
def platform_ack_alert(
    alert_id: str,
    payload: AlertAckIn,
    caller: PlatformCaller = Depends(require_platform(rbac.PLATFORM_ALERT_MANAGE)),
    session: Session = Depends(get_session),
) -> ObsAlertOut:
    alerta = session.get(Alert, alert_id)
    if alerta is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, ALERTA_NAO_ENCONTRADO)
    try:
        alertas.reconhecer(session, alerta, by=caller.user, note=payload.note,
                           quem=f"{caller.user.full_name} (equipe ValTexa)")
    except alertas.AlertError as exc:
        raise _erro(exc) from exc
    session.commit()
    return _alert_out(alerta, _nomes_de_cliente(session, {alerta.tenant_id} - {None}))


@router.get("/platform/observability/alert-rules", response_model=list[AlertRuleOut],
            summary="Regras de alerta (padrão da plataforma)")
def platform_alert_rules(
    _: PlatformCaller = Depends(require_platform(rbac.PLATFORM_OBSERVABILITY_READ)),
    session: Session = Depends(get_session),
) -> list[AlertRuleOut]:
    return _regras(session, None)


@router.put("/platform/observability/alert-rules/{kind}", response_model=AlertRuleOut,
            summary="Ajusta a regra padrão (limite, janela, severidade, ligada)")
def platform_update_alert_rule(
    kind: str,
    payload: AlertRuleIn,
    caller: PlatformCaller = Depends(require_platform(rbac.PLATFORM_ALERT_MANAGE)),
    session: Session = Depends(get_session),
) -> AlertRuleOut:
    alertas.sincronizar_catalogo(session)
    try:
        linha = alertas.salvar_regra(session, kind=kind, tenant_id=None, by=caller.user,
                                     **payload.model_dump(exclude_unset=True))
    except alertas.AlertError as exc:
        raise _erro(exc) from exc
    session.commit()
    return _regra_out(kind, None, linha, "padrao")


# ---------------------------------------------------------------------------
# Console do cliente: só os robôs dele
# ---------------------------------------------------------------------------


@router.get("/observability/fleet", response_model=list[RoverHealthOut],
            summary="Saúde dos robôs deste cliente")
def tenant_fleet_health(
    principal: Principal = Depends(require(rbac.DEVICE_READ)),
    session: Session = Depends(get_session),
) -> list[RoverHealthOut]:
    abertos = _abertos_por_robo(session, principal.tenant_id)
    return [RoverHealthOut(**r, open_alerts=abertos[r["device_id"]])
            for r in observabilidade.frota(session, tenant_id=principal.tenant_id)]


@router.get("/observability/alerts", response_model=list[ObsAlertOut],
            summary="Alertas dos robôs deste cliente")
def tenant_alerts(
    state: str | None = Query(default=None, max_length=16),
    kind: str | None = Query(default=None, max_length=40),
    open_only: bool = Query(default=False),
    limit: int = Query(default=200, ge=1, le=1000),
    principal: Principal = Depends(require(rbac.DEVICE_READ)),
    session: Session = Depends(get_session),
) -> list[ObsAlertOut]:
    consulta = _consulta_alertas(state, kind, open_only).where(
        Alert.tenant_id == principal.tenant_id)
    return [_alert_out(a) for a in
            session.scalars(consulta.order_by(Alert.fired_at.desc()).limit(limit))]


def _alerta_do_cliente(session: Session, alert_id: str, principal: Principal) -> Alert:
    alerta = session.get(Alert, alert_id)
    if alerta is None or alerta.tenant_id != principal.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, ALERTA_NAO_ENCONTRADO)
    return alerta


@router.post("/observability/alerts/{alert_id}/ack", response_model=ObsAlertOut,
             summary="Reconhece um alerta de robô deste cliente")
def tenant_ack_alert(
    alert_id: str,
    payload: AlertAckIn,
    principal: Principal = Depends(require(rbac.DEVICE_MANAGE)),
    session: Session = Depends(get_session),
) -> ObsAlertOut:
    alerta = _alerta_do_cliente(session, alert_id, principal)
    quem = (f"{principal.user.full_name} (equipe ValTexa)" if principal.is_support
            else principal.user.full_name)
    try:
        alertas.reconhecer(session, alerta, by=principal.user, note=payload.note, quem=quem)
    except alertas.AlertError as exc:
        raise _erro(exc) from exc
    session.commit()
    return _alert_out(alerta)


@router.get("/observability/alert-rules", response_model=list[AlertRuleOut],
            summary="Regras de alerta dos robôs (com a versão deste cliente, se houver)")
def tenant_alert_rules(
    principal: Principal = Depends(require(rbac.DEVICE_READ)),
    session: Session = Depends(get_session),
) -> list[AlertRuleOut]:
    return _regras(session, principal.tenant_id)


@router.put("/observability/alert-rules/{kind}", response_model=AlertRuleOut,
            summary="Ajusta uma regra de robô só para este cliente")
def tenant_update_alert_rule(
    kind: str,
    payload: AlertRuleIn,
    principal: Principal = Depends(require(rbac.DEVICE_MANAGE)),
    session: Session = Depends(get_session),
) -> AlertRuleOut:
    alertas.sincronizar_catalogo(session)
    try:
        linha = alertas.salvar_regra(session, kind=kind, tenant_id=principal.tenant_id,
                                     by=principal.user, **payload.model_dump(exclude_unset=True))
    except alertas.AlertError as exc:
        raise _erro(exc) from exc
    session.commit()
    padrao = session.scalars(select(AlertRule).where(
        AlertRule.tenant_id.is_(None), AlertRule.kind == kind)).first()
    return _regra_out(kind, linha, padrao, "cliente")


@router.delete("/observability/alert-rules/{kind}", status_code=status.HTTP_204_NO_CONTENT,
               summary="Volta a regra deste cliente para a padrão")
def tenant_reset_alert_rule(
    kind: str,
    principal: Principal = Depends(require(rbac.DEVICE_MANAGE)),
    session: Session = Depends(get_session),
) -> Response:
    if kind not in alertas.REGRAS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Regra desconhecida.")
    alertas.remover_regra_do_cliente(session, kind=kind, tenant_id=principal.tenant_id,
                                     by=principal.user)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


__all__ = ["metrics_router", "router"]
