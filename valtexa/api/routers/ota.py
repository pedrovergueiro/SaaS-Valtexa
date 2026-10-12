"""Atualização remota (OTA) do Rover — brief, seção 24.

Equipe (``platform:ota:manage``; leitura com ``platform:fleet:read``):

* ``POST /v1/platform/ota/packages?kind=&version=&model_version_id=`` — publica um
  pacote (corpo: o ``.tar``). Modelo só se a versão estiver em PRODUÇÃO no registry;
* ``GET /v1/platform/ota/packages`` — pacotes publicados;
* ``POST /v1/platform/ota/deployments`` — destina a robôs ou a um cliente inteiro;
* ``GET /v1/platform/ota/deployments`` — acompanhamento (estado e histórico por robô);
* ``POST /v1/platform/ota/deployments/{id}/cancel`` — antes de o robô instalar.

Robô (assinadas, como todo ``/v1/device/**``):

* ``GET /v1/device/ota`` — atualizações pendentes, cada uma com o envelope assinado;
* ``GET /v1/device/ota/{id}/package?offset=&length=`` — um pedaço do pacote (retomada);
* ``POST /v1/device/ota/{id}/status`` — o robô informa cada passo.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from valtexa.api.deps import DeviceCaller, PlatformCaller, current_device, require_platform
from valtexa.db import get_session
from valtexa.models import Device, OtaDeployment, OtaPackage, Tenant
from valtexa.schemas import (
    OtaDeploymentIn,
    OtaDeploymentOut,
    OtaDeviceItemOut,
    OtaPackageOut,
    OtaStatusIn,
)
from valtexa.security import rbac
from valtexa.services import ota, storage

router = APIRouter(tags=["atualização remota (OTA)"])


def _http(exc: ota.OtaError) -> HTTPException:
    return HTTPException(exc.status, str(exc))


def _pacote_out(p: OtaPackage) -> OtaPackageOut:
    return OtaPackageOut(id=p.id, kind=p.kind, version=p.version, sha256=p.sha256,
                         size_bytes=p.size_bytes, manifest=p.manifest,
                         model_version_id=p.model_version_id, notes=p.notes,
                         created_at=p.created_at)


def _destino_out(session: Session, d: OtaDeployment) -> OtaDeploymentOut:
    robo = session.get(Device, d.device_id)
    cliente = session.get(Tenant, d.tenant_id)
    pacote = session.get(OtaPackage, d.package_id)
    return OtaDeploymentOut(
        id=d.id, package_id=d.package_id, kind=pacote.kind, version=pacote.version,
        device_id=d.device_id, device_serial=robo.serial_number if robo else "",
        tenant_id=d.tenant_id, tenant_name=cliente.name if cliente else "",
        state=d.state, detail=d.detail, history=d.history, bytes_served=d.bytes_served,
        size_bytes=pacote.size_bytes, created_at=d.created_at, finished_at=d.finished_at,
    )


# ---------------------------------------------------------------------------
# Equipe
# ---------------------------------------------------------------------------


@router.post("/platform/ota/packages", response_model=OtaPackageOut,
             status_code=status.HTTP_201_CREATED, summary="Publica um pacote OTA (.tar)")
async def publish_package(
    request: Request,
    kind: str = Query(...),
    version: str = Query(..., min_length=1, max_length=64),
    model_version_id: str | None = Query(default=None),
    notes: str | None = Query(default=None, max_length=1000),
    caller: PlatformCaller = Depends(require_platform(rbac.PLATFORM_OTA_MANAGE)),
    session: Session = Depends(get_session),
) -> OtaPackageOut:
    dados = await request.body()
    try:
        pacote = ota.publicar_pacote(session, dados, kind=kind, version=version,
                                     actor=caller.user, model_version_id=model_version_id,
                                     notes=notes)
    except ota.OtaError as exc:
        raise _http(exc) from exc
    except storage.AssetTooLargeError as exc:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, str(exc)) from exc
    session.commit()
    return _pacote_out(pacote)


@router.get("/platform/ota/packages", response_model=list[OtaPackageOut],
            summary="Pacotes OTA publicados")
def list_packages(
    kind: str | None = None,
    _: PlatformCaller = Depends(require_platform(rbac.PLATFORM_FLEET_READ)),
    session: Session = Depends(get_session),
) -> list[OtaPackageOut]:
    consulta = select(OtaPackage).order_by(OtaPackage.created_at.desc())
    if kind:
        consulta = consulta.where(OtaPackage.kind == kind)
    return [_pacote_out(p) for p in session.scalars(consulta)]


@router.post("/platform/ota/deployments", response_model=list[OtaDeploymentOut],
             status_code=status.HTTP_201_CREATED,
             summary="Destina um pacote a robôs ou a um cliente")
def create_deployments(
    payload: OtaDeploymentIn,
    caller: PlatformCaller = Depends(require_platform(rbac.PLATFORM_OTA_MANAGE)),
    session: Session = Depends(get_session),
) -> list[OtaDeploymentOut]:
    pacote = session.get(OtaPackage, payload.package_id)
    if pacote is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pacote não encontrado.")
    try:
        criados = ota.destinar(session, pacote, actor=caller.user,
                               device_ids=payload.device_ids, tenant_id=payload.tenant_id)
    except ota.OtaError as exc:
        raise _http(exc) from exc
    session.commit()
    return [_destino_out(session, d) for d in criados]


@router.get("/platform/ota/deployments", response_model=list[OtaDeploymentOut],
            summary="Acompanhamento das atualizações")
def list_deployments(
    package_id: str | None = None,
    device_id: str | None = None,
    tenant_id: str | None = None,
    state: str | None = None,
    _: PlatformCaller = Depends(require_platform(rbac.PLATFORM_FLEET_READ)),
    session: Session = Depends(get_session),
) -> list[OtaDeploymentOut]:
    consulta = select(OtaDeployment).order_by(OtaDeployment.created_at.desc())
    for coluna, valor in ((OtaDeployment.package_id, package_id),
                          (OtaDeployment.device_id, device_id),
                          (OtaDeployment.tenant_id, tenant_id),
                          (OtaDeployment.state, state)):
        if valor:
            consulta = consulta.where(coluna == valor)
    return [_destino_out(session, d) for d in session.scalars(consulta.limit(1000))]


@router.post("/platform/ota/deployments/{deployment_id}/cancel",
             response_model=OtaDeploymentOut, summary="Cancela antes da instalação")
def cancel_deployment(
    deployment_id: str,
    caller: PlatformCaller = Depends(require_platform(rbac.PLATFORM_OTA_MANAGE)),
    session: Session = Depends(get_session),
) -> OtaDeploymentOut:
    destino = session.get(OtaDeployment, deployment_id)
    if destino is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Atualização não encontrada.")
    try:
        ota.cancelar(session, destino, actor=caller.user)
    except ota.OtaError as exc:
        raise _http(exc) from exc
    session.commit()
    return _destino_out(session, destino)


# ---------------------------------------------------------------------------
# Robô
# ---------------------------------------------------------------------------


@router.get("/device/ota", response_model=list[OtaDeviceItemOut],
            summary="Atualizações pendentes deste robô")
def device_pending(
    caller: DeviceCaller = Depends(current_device),
    session: Session = Depends(get_session),
) -> list[OtaDeviceItemOut]:
    return [OtaDeviceItemOut(deployment_id=d.id, state=d.state, envelope=d.envelope)
            for d in ota.pendentes_do_robo(session, caller.device)]


@router.get("/device/ota/{deployment_id}/package", summary="Um pedaço do pacote",
            response_class=Response)
def device_package(
    deployment_id: str,
    offset: int = Query(0, ge=0),
    length: int = Query(1024 * 1024, gt=0),
    caller: DeviceCaller = Depends(current_device),
    session: Session = Depends(get_session),
) -> Response:
    try:
        destino = ota.destino_do_robo(session, caller.device, deployment_id)
        dados = ota.trecho(session, destino, offset, length)
    except ota.OtaError as exc:
        raise _http(exc) from exc
    session.commit()
    pacote = session.get(OtaPackage, destino.package_id)
    return Response(dados, media_type="application/octet-stream",
                    headers={"X-Total-Size": str(pacote.size_bytes)})


@router.post("/device/ota/{deployment_id}/status", response_model=OtaDeviceItemOut,
             summary="O robô informa um passo da atualização")
def device_status(
    deployment_id: str,
    payload: OtaStatusIn,
    caller: DeviceCaller = Depends(current_device),
    session: Session = Depends(get_session),
) -> OtaDeviceItemOut:
    try:
        destino = ota.destino_do_robo(session, caller.device, deployment_id)
        ota.informar(session, caller.device, destino, payload.state, payload.detail,
                     payload.version_running)
    except ota.OtaError as exc:
        raise _http(exc) from exc
    session.commit()
    return OtaDeviceItemOut(deployment_id=destino.id, state=destino.state,
                            envelope=destino.envelope)
