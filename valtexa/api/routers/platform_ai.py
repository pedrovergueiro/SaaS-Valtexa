"""AI Platform, Model Registry e frota no console interno (brief, seções 8, 9, 25, 34).

* ``/platform/models`` — o registry: listar, ver com histórico, registrar,
  corrigir e mover no ciclo de vida (TREINAMENTO → … → DESCONTINUADO);
* ``/platform/model-releases`` — liberação de um modelo para um cliente;
* ``/platform/fleet`` — todos os robôs de todos os clientes, com filtro por
  cliente, estado e "modelo diferente do designado" (Operações);
* ``/platform/ai-health`` — saúde da IA com o que existe de dado real. O que não
  tem fonte aqui (drift, incidentes, FPS) vem em ``no_data`` com o motivo —
  nunca um número inventado.

Tudo atrás de :func:`~valtexa.api.deps.require_platform`; o teste gerado do
OpenAPI confere que nenhum papel de cliente alcança estas rotas. Métricas
técnicas (precision, FLOPs, artefatos) só saem daqui: o produtor vê a versão em
linguagem operacional em ``/fields/{id}/ai-models``.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from valtexa.api.deps import PlatformCaller, require_platform
from valtexa.api.routers.fleet import device_snapshot
from valtexa.db import get_session
from valtexa.models import (
    AuditEntry,
    Detection,
    Device,
    ModelOptimization,
    ModelRelease,
    ModelVersion,
    ModelVersionState,
    SubjectType,
    Tenant,
    User,
)
from valtexa.schemas import (
    AiHealthModelOut,
    AiHealthOut,
    FleetDeviceOut,
    ModelOptimizationIn,
    ModelOptimizationOut,
    ModelReleaseIn,
    ModelReleaseOut,
    ModelTransitionIn,
    ModelTransitionOut,
    ModelVersionCreate,
    ModelVersionDetailOut,
    ModelVersionOut,
    ModelVersionUpdate,
)
from valtexa.security import rbac
from valtexa.services import calibracao_campo, dnaty, model_registry

router = APIRouter(tags=["plataforma: IA e frota"])


def model_version_out(linha: ModelVersion) -> ModelVersionOut:
    return ModelVersionOut(
        id=linha.id,
        model_key=linha.model_key,
        version=linha.version,
        name=linha.name,
        state=linha.state,
        state_label=model_registry.ROTULOS[linha.state],
        platform=linha.platform,
        crop=linha.crop,
        crops=list(linha.crops or []),
        problem=linha.problem,
        architecture=linha.architecture,
        dataset_version_id=linha.dataset_version_id,
        dataset_ref=linha.dataset_ref,
        trained_at=linha.trained_at,
        metrics=linha.metrics or {},
        size_bytes=linha.size_bytes,
        flops=linha.flops,
        latency_ms=linha.latency_ms,
        memory_mb=linha.memory_mb,
        target_hardware=linha.target_hardware,
        original_artifact_uri=linha.original_artifact_uri,
        original_artifact_sha256=linha.original_artifact_sha256,
        optimized_artifact_uri=linha.optimized_artifact_uri,
        optimized_artifact_sha256=linha.optimized_artifact_sha256,
        optimized_size_bytes=linha.optimized_size_bytes,
        extras_manifest_sha256=linha.extras_manifest_sha256,
        dnaty_version=linha.dnaty_version,
        variant=linha.variant,
        recommended=linha.recommended,
        license=linha.license,
        caveat=linha.caveat,
        release_scope=linha.release_scope,
        notes=linha.notes,
        registered_by=linha.registered_by,
        approved_by=linha.approved_by,
        approved_at=linha.approved_at,
        promoted_at=linha.promoted_at,
        retired_at=linha.retired_at,
        next_states=[
            e for e in ModelVersionState if e in model_registry.TRANSICOES[linha.state]
        ],
    )


def _versao(session: Session, model_version_id: str) -> ModelVersion:
    linha = session.get(ModelVersion, model_version_id)
    if linha is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Versão de modelo não encontrada.")
    return linha


def _erro(exc: model_registry.RegistryError) -> HTTPException:
    codigo = status.HTTP_403_FORBIDDEN if exc.proibido else status.HTTP_409_CONFLICT
    return HTTPException(codigo, str(exc))


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


@router.get(
    "/platform/models", response_model=list[ModelVersionOut], summary="Model Registry"
)
def list_models(
    state: ModelVersionState | None = None,
    model_key: str | None = None,
    _: PlatformCaller = Depends(require_platform(rbac.PLATFORM_MODEL_READ)),
    session: Session = Depends(get_session),
) -> list[ModelVersionOut]:
    consulta = select(ModelVersion).order_by(
        ModelVersion.model_key, ModelVersion.created_at.desc()
    )
    if state is not None:
        consulta = consulta.where(ModelVersion.state == state)
    if model_key:
        consulta = consulta.where(ModelVersion.model_key == model_key)
    return [model_version_out(linha) for linha in session.scalars(consulta)]


@router.get(
    "/platform/models/{model_version_id}",
    response_model=ModelVersionDetailOut,
    summary="Uma versão do registry, com o histórico",
)
def get_model(
    model_version_id: str,
    _: PlatformCaller = Depends(require_platform(rbac.PLATFORM_MODEL_READ)),
    session: Session = Depends(get_session),
) -> ModelVersionDetailOut:
    linha = _versao(session, model_version_id)
    trilha = session.scalars(
        select(AuditEntry)
        .where(
            AuditEntry.subject_type == SubjectType.MODEL_VERSION,
            AuditEntry.subject_id == linha.id,
        )
        .order_by(AuditEntry.at)
    )
    liberados = session.scalars(
        select(Tenant.name)
        .join(ModelRelease, ModelRelease.tenant_id == Tenant.id)
        .where(ModelRelease.model_key == linha.model_key, ModelRelease.revoked_at.is_(None))
        .order_by(Tenant.name)
    )
    return ModelVersionDetailOut(
        **model_version_out(linha).model_dump(),
        history=[
            ModelTransitionOut(
                at=entrada.at,
                actor_label=entrada.actor_label,
                action=entrada.action,
                from_state=entrada.old_state,
                to_state=entrada.new_state,
                reason=entrada.reason,
            )
            for entrada in trilha
        ],
        released_to=list(liberados),
    )


@router.post(
    "/platform/models",
    response_model=ModelVersionOut,
    status_code=status.HTTP_201_CREATED,
    summary="Registra uma versão de modelo (entra em TREINAMENTO)",
)
def create_model(
    payload: ModelVersionCreate,
    caller: PlatformCaller = Depends(require_platform(rbac.PLATFORM_MODEL_MANAGE)),
    session: Session = Depends(get_session),
) -> ModelVersionOut:
    try:
        linha = model_registry.registrar(session, payload.model_dump(), actor=caller.user)
    except model_registry.RegistryError as exc:
        raise _erro(exc) from exc
    session.commit()
    return model_version_out(linha)


@router.patch(
    "/platform/models/{model_version_id}",
    response_model=ModelVersionOut,
    summary="Corrige uma versão (dados técnicos só até a aprovação)",
)
def update_model(
    model_version_id: str,
    payload: ModelVersionUpdate,
    caller: PlatformCaller = Depends(require_platform(rbac.PLATFORM_MODEL_MANAGE)),
    session: Session = Depends(get_session),
) -> ModelVersionOut:
    linha = _versao(session, model_version_id)
    mudancas = payload.model_dump(exclude_unset=True)
    if mudancas:
        try:
            model_registry.editar(session, linha, mudancas, actor=caller.user)
        except model_registry.RegistryError as exc:
            raise _erro(exc) from exc
        session.commit()
    return model_version_out(linha)


@router.post(
    "/platform/models/{model_version_id}/transition",
    response_model=list[ModelVersionOut],
    summary="Move a versão no ciclo de vida",
)
def transition_model(
    model_version_id: str,
    payload: ModelTransitionIn,
    caller: PlatformCaller = Depends(require_platform(rbac.PLATFORM_MODEL_MANAGE)),
    session: Session = Depends(get_session),
) -> list[ModelVersionOut]:
    """Devolve as versões afetadas: a movida e, ao publicar, a que saiu de PRODUÇÃO.

    Aprovar exige papel IA & Dados (ou superadmin) e não ser quem registrou: 403.
    Transição fora do ciclo, sem motivo quando exige, sem métrica ou sem
    artefato com hash: 409 com o motivo.
    """
    linha = _versao(session, model_version_id)
    try:
        afetadas = model_registry.transicionar(
            session, linha, payload.to, actor=caller.user, reason=payload.reason
        )
    except model_registry.RegistryError as exc:
        raise _erro(exc) from exc
    session.commit()
    return [model_version_out(v) for v in afetadas]


# ---------------------------------------------------------------------------
# Etapa de otimização (dNATY, seção 23)
# ---------------------------------------------------------------------------


def _optimization_out(linha: ModelVersion, rodada: ModelOptimization) -> ModelOptimizationOut:
    return ModelOptimizationOut(
        id=rodada.id,
        model_version_id=rodada.model_version_id,
        created_at=rodada.created_at,
        tool=rodada.tool,
        tool_version=rodada.tool_version,
        dnaty_version=rodada.dnaty_version,
        parameters=rodada.parameters,
        original_sha256=rodada.original_sha256,
        original_benchmark=rodada.original_benchmark,
        optimized_artifact_uri=rodada.optimized_artifact_uri,
        optimized_sha256=rodada.optimized_sha256,
        optimized_size_bytes=rodada.optimized_size_bytes,
        optimized_benchmark=rodada.optimized_benchmark,
        criterion=rodada.criterion,
        comparison=rodada.comparison,
        accepted=rodada.accepted,
        reasons=rodada.reasons,
        license_note=rodada.license_note,
        applied=rodada.accepted
        and rodada.optimized_sha256 == linha.optimized_artifact_sha256,
    )


@router.get(
    "/platform/models/{model_version_id}/optimizations",
    response_model=list[ModelOptimizationOut],
    summary="Rodadas de otimização (original e otimizado) de uma versão",
)
def list_optimizations(
    model_version_id: str,
    _: PlatformCaller = Depends(require_platform(rbac.PLATFORM_MODEL_READ)),
    session: Session = Depends(get_session),
) -> list[ModelOptimizationOut]:
    linha = _versao(session, model_version_id)
    rodadas = session.scalars(
        select(ModelOptimization)
        .where(ModelOptimization.model_version_id == linha.id)
        .order_by(ModelOptimization.created_at.desc())
    )
    return [_optimization_out(linha, r) for r in rodadas]


@router.post(
    "/platform/models/{model_version_id}/optimizations",
    response_model=ModelOptimizationOut,
    status_code=status.HTTP_201_CREATED,
    summary="Registra uma rodada de otimização (o registry decide se aceita)",
)
def create_optimization(
    model_version_id: str,
    payload: ModelOptimizationIn,
    caller: PlatformCaller = Depends(require_platform(rbac.PLATFORM_MODEL_MANAGE)),
    session: Session = Depends(get_session),
) -> ModelOptimizationOut:
    """Recusada também é gravada (201, ``accepted: false`` e os motivos).

    Só antes da aprovação (TREINAMENTO/VALIDAÇÃO); benchmark de outro artefato,
    otimizado igual ao original ou critério inválido: 409.
    """
    linha = _versao(session, model_version_id)
    if not payload.otimizado.artifact_uri:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Informe otimizado.artifact_uri: onde o artefato otimizado vive.")
    try:
        rodada = dnaty.registrar_otimizacao(session, linha, payload.model_dump(),
                                            actor=caller.user)
    except model_registry.RegistryError as exc:
        raise _erro(exc) from exc
    session.commit()
    return _optimization_out(linha, rodada)


# ---------------------------------------------------------------------------
# Liberação por cliente
# ---------------------------------------------------------------------------


def _release_out(session: Session, linha: ModelRelease) -> ModelReleaseOut:
    tenant = session.get(Tenant, linha.tenant_id)
    quem = session.get(User, linha.released_by) if linha.released_by else None
    return ModelReleaseOut(
        id=linha.id,
        tenant_id=linha.tenant_id,
        tenant_name=tenant.name if tenant else "",
        model_key=linha.model_key,
        reason=linha.reason,
        released_by_label=quem.email if quem else None,
        created_at=linha.created_at,
        revoked_at=linha.revoked_at,
    )


@router.get(
    "/platform/model-releases",
    response_model=list[ModelReleaseOut],
    summary="Modelos liberados por cliente",
)
def list_releases(
    tenant_id: str | None = None,
    include_revoked: bool = False,
    _: PlatformCaller = Depends(require_platform(rbac.PLATFORM_MODEL_READ)),
    session: Session = Depends(get_session),
) -> list[ModelReleaseOut]:
    consulta = select(ModelRelease).order_by(ModelRelease.created_at.desc())
    if tenant_id:
        consulta = consulta.where(ModelRelease.tenant_id == tenant_id)
    if not include_revoked:
        consulta = consulta.where(ModelRelease.revoked_at.is_(None))
    return [_release_out(session, linha) for linha in session.scalars(consulta)]


@router.post(
    "/platform/model-releases",
    response_model=ModelReleaseOut,
    status_code=status.HTTP_201_CREATED,
    summary="Libera um modelo para um cliente",
)
def create_release(
    payload: ModelReleaseIn,
    caller: PlatformCaller = Depends(require_platform(rbac.PLATFORM_MODEL_RELEASE)),
    session: Session = Depends(get_session),
) -> ModelReleaseOut:
    """Idempotente: liberar de novo o que já está liberado devolve a mesma liberação."""
    if session.get(Tenant, payload.tenant_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cliente não encontrado.")
    try:
        linha = model_registry.liberar(
            session, payload.tenant_id, payload.model_key, actor=caller.user,
            reason=payload.reason,
        )
    except model_registry.RegistryError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    session.commit()
    return _release_out(session, linha)


@router.post(
    "/platform/model-releases/{release_id}/revoke",
    response_model=ModelReleaseOut,
    summary="Revoga a liberação (fica no histórico)",
)
def revoke_release(
    release_id: str,
    caller: PlatformCaller = Depends(require_platform(rbac.PLATFORM_MODEL_RELEASE)),
    session: Session = Depends(get_session),
) -> ModelReleaseOut:
    linha = session.get(ModelRelease, release_id)
    if linha is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Liberação não encontrada.")
    model_registry.revogar(session, linha, actor=caller.user, reason=None)
    session.commit()
    return _release_out(session, linha)


# ---------------------------------------------------------------------------
# Frota de todos os clientes (Operações)
# ---------------------------------------------------------------------------


@router.get(
    "/platform/fleet",
    response_model=list[FleetDeviceOut],
    summary="Frota de todos os clientes",
)
def platform_fleet(
    tenant_id: str | None = None,
    fleet_state: str | None = Query(default=None, description="Ex.: offline, erro."),
    model_divergent: bool = Query(
        default=False,
        description="Só robôs cujo modelo informado não é o designado pelo registry.",
    ),
    _: PlatformCaller = Depends(require_platform(rbac.PLATFORM_FLEET_READ)),
    session: Session = Depends(get_session),
) -> list[FleetDeviceOut]:
    """Retrato de frota de cada robô, com o cliente dono. Sem lavoura, sem imagem."""
    consulta = (
        select(Device, Tenant.name)
        .join(Tenant, Tenant.id == Device.tenant_id)
        .options(selectinload(Device.credentials), selectinload(Device.model))
        .order_by(Tenant.name, Device.name)
    )
    if tenant_id:
        consulta = consulta.where(Device.tenant_id == tenant_id)
    agora = datetime.now(UTC)
    cache: dict = {}
    saida = []
    for device, nome in session.execute(consulta).all():
        retrato = device_snapshot(session, device, agora, cache=cache)
        if fleet_state and retrato["fleet_state"] != fleet_state:
            continue
        if model_divergent and retrato["model_status"] not in {"divergente", "fora_do_registry"}:
            continue
        saida.append(FleetDeviceOut(**retrato, tenant_id=device.tenant_id, tenant_name=nome))
    return saida


# ---------------------------------------------------------------------------
# Saúde da IA (seção 34)
# ---------------------------------------------------------------------------

SEM_DADO = {
    "drift": (
        "O drift da distribuição de classes (saída do modelo) está em "
        "/v1/platform/observability/ai, com alerta. O da entrada (imagens) não é medido: "
        "exige a referência do treino, que vive com os pesos na VALTEXA-B."
    ),
    "incidentes": "Não há registro de incidente de IA na plataforma ainda.",
    "fps": "O robô ainda não informa FPS da IA embarcada (vem com o Rover Runtime, Parte 4).",
    "performance_em_producao": (
        "Nenhum diagnóstico confirmado pelo agrônomo na janela: sem rótulo humano não há "
        "acerto nem cobertura em produção para medir."
    ),
}


def _p95(valores: list[float]) -> float | None:
    if not valores:
        return None
    ordenados = sorted(valores)
    return round(ordenados[min(len(ordenados) - 1, int(0.95 * len(ordenados)))], 2)


@router.get("/platform/ai-health", response_model=AiHealthOut, summary="Saúde da IA")
def ai_health(
    days: int = Query(default=30, ge=1, le=365),
    _: PlatformCaller = Depends(require_platform(rbac.PLATFORM_MODEL_READ)),
    session: Session = Depends(get_session),
) -> AiHealthOut:
    """Medido nas detecções gravadas e no que os robôs informaram — nada estimado.

    Detecções do analisador simulado (``model_version = sim-1``) aparecem marcadas
    como ``simulated``: sem os pesos aqui, é isso que roda nos testes e na demo.
    """
    desde = datetime.now(UTC) - timedelta(days=days)
    grupos: dict[tuple, dict] = defaultdict(
        lambda: {"n": 0, "erros": 0, "abst": 0, "lat": [], "labels": Counter(), "ultimo": None}
    )
    linhas = session.execute(
        select(
            Detection.model_key,
            Detection.model_version,
            Detection.error,
            Detection.abstained,
            Detection.latency_ms,
            Detection.label,
            Detection.created_at,
        ).where(Detection.created_at >= desde)
    )
    for chave, versao, erro, absteve, latencia, rotulo, quando in linhas:
        g = grupos[(chave, versao)]
        g["n"] += 1
        g["erros"] += 1 if erro else 0
        g["abst"] += 1 if absteve else 0
        if latencia is not None:
            g["lat"].append(float(latencia))
        if rotulo:
            g["labels"][rotulo] += 1
        if g["ultimo"] is None or quando > g["ultimo"]:
            g["ultimo"] = quando
    modelos = [
        AiHealthModelOut(
            model_key=chave,
            model_version=versao,
            simulated=versao == "sim-1" or (chave or "").startswith("simulated-"),
            inferences=g["n"],
            errors=g["erros"],
            error_rate=round(g["erros"] / g["n"], 4) if g["n"] else None,
            abstentions=g["abst"],
            latency_ms_avg=round(sum(g["lat"]) / len(g["lat"]), 2) if g["lat"] else None,
            latency_ms_p95=_p95(g["lat"]),
            labels=dict(g["labels"].most_common(12)),
            last_at=g["ultimo"],
        )
        for (chave, versao), g in sorted(grupos.items(), key=lambda kv: -kv[1]["n"])
    ]

    ativos = session.scalars(
        select(ModelVersion)
        .where(ModelVersion.state == ModelVersionState.PRODUCAO)
        .order_by(ModelVersion.model_key)
    ).all()
    descontinuadas = {
        f"{m.model_key}@{m.version}"
        for m in session.scalars(
            select(ModelVersion).where(ModelVersion.state == ModelVersionState.DESCONTINUADO)
        )
    }
    contagem: Counter = Counter()
    desatualizadas: set[str] = set()
    cache: dict = {}
    for device in session.scalars(
        select(Device).options(selectinload(Device.credentials), selectinload(Device.model))
    ):
        retrato = device_snapshot(session, device, cache=cache)
        contagem[retrato["model_status"]] += 1
        etiqueta = f"{device.ai_model_key}@{device.ai_model_version}"
        if etiqueta in descontinuadas:
            desatualizadas.add(etiqueta)

    calibracao = calibracao_campo.medir(session, desde=desde)
    sem_dado = dict(SEM_DADO)
    if calibracao:
        sem_dado.pop("performance_em_producao")
    return AiHealthOut(
        window_days=days,
        active_models=[model_version_out(m) for m in ativos],
        models=modelos,
        rovers_reporting=contagem["conforme"] + contagem["divergente"]
        + contagem["fora_do_registry"],
        rovers_divergent=contagem["divergente"],
        rovers_outside_registry=contagem["fora_do_registry"],
        rovers_without_data=contagem["sem_dado"],
        outdated_in_use=sorted(desatualizadas),
        no_data=sem_dado,
        field_calibration=calibracao,
    )
