"""Frota: catálogo de hardware, provisionamento e ciclo de vida dos robôs."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from valtexa.api.deps import Principal, get_scoped, require, scoped
from valtexa.db import get_session
from valtexa.models import (
    ActorType,
    CredentialStatus,
    Device,
    DeviceCredential,
    DeviceKind,
    DeviceModel,
    DeviceStatus,
    Farm,
    ProvisioningToken,
    SubjectType,
    Tank,
    as_utc,
)
from valtexa.models.fleet import PROTOCOL_VERSION
from valtexa.schemas import (
    DeviceModelOut,
    DeviceOut,
    DeviceProvisionRequest,
    DeviceProvisionResponse,
    DeviceStatusUpdate,
    Message,
    ProvisioningTokenCreate,
    ProvisioningTokenOut,
)
from valtexa.security import rbac, signing
from valtexa.services import audit, events, fleet_state, model_registry, plans
from valtexa.services.hal import Capabilities, capabilities_of

router = APIRouter(tags=["frota"])


@router.get("/device-models", response_model=list[DeviceModelOut], summary="Catálogo de hardware")
def list_models(
    _: Principal = Depends(require(rbac.DEVICE_READ)),
    session: Session = Depends(get_session),
) -> list[DeviceModelOut]:
    """Modelos suportados e o que cada um consegue fazer.

    É a camada de abstração de hardware exposta: quem integra um robô novo
    cadastra um modelo aqui, e o resto da plataforma passa a operá-lo sem
    alteração de código.
    """
    rows = session.scalars(
        select(DeviceModel).where(DeviceModel.is_active).order_by(DeviceModel.code)
    )
    return [
        DeviceModelOut(
            id=row.id,
            code=row.code,
            kind=row.kind,
            name=row.name,
            manufacturer=row.manufacturer,
            protocol_version=row.protocol_version,
            capabilities=row.capabilities,
        )
        for row in rows
    ]


@router.post(
    "/provisioning-tokens",
    response_model=ProvisioningTokenOut,
    status_code=status.HTTP_201_CREATED,
    summary="Gera um convite para um robô entrar na frota",
)
def create_provisioning_token(
    payload: ProvisioningTokenCreate,
    principal: Principal = Depends(require(rbac.DEVICE_PROVISION)),
    session: Session = Depends(get_session),
) -> ProvisioningTokenOut:
    """Cria um convite de uso único.

    O token em claro é devolvido **uma única vez**: só o hash fica guardado.
    Perder significa gerar outro, que é o comportamento correto — um convite
    recuperável do banco seria um convite vazado.
    """
    model = session.scalars(
        select(DeviceModel).where(DeviceModel.code == payload.device_model_code)
    ).first()
    if model is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, f"Modelo {payload.device_model_code!r} não existe."
        )
    if payload.farm_id:
        get_scoped(session, Farm, payload.farm_id, principal)
    # Conferido aqui, para o convite não nascer inútil, e de novo no
    # provisionamento, que é quando o robô passa a existir: entre um e outro
    # pode ter entrado outro robô.
    plans.exigir(session, principal.tenant_id, "devices")

    token = signing.new_provisioning_token()
    row = ProvisioningToken(
        tenant_id=principal.tenant_id,
        token_hash=signing.hash_token(token),
        device_model_id=model.id,
        farm_id=payload.farm_id,
        serial_number=payload.serial_number,
        expires_at=datetime.now(UTC) + timedelta(hours=payload.ttl_hours),
        created_by=principal.user_id,
    )
    session.add(row)
    audit.record(
        session,
        tenant_id=principal.tenant_id,
        action="device.provisioning_token_created",
        subject_type=SubjectType.DEVICE,
        subject_id=row.id,
        actor_type=ActorType.USER,
        actor_id=principal.user_id,
        actor_label=principal.user.email,
        payload={"model": model.code, "serial_number": payload.serial_number},
    )
    session.commit()
    return ProvisioningTokenOut(
        id=row.id,
        token=token,
        expires_at=row.expires_at,
        device_model_code=model.code,
        serial_number=row.serial_number,
    )


@router.post(
    "/device/provision",
    response_model=DeviceProvisionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Registro do robô (chamado pelo próprio robô)",
    tags=["protocolo do dispositivo"],
)
def provision(
    payload: DeviceProvisionRequest, session: Session = Depends(get_session)
) -> DeviceProvisionResponse:
    """Troca um convite de uso único por uma identidade permanente.

    É a **única** rota de dispositivo sem assinatura — não teria como haver uma,
    já que a credencial nasce aqui. Tudo o mais é verificado: o convite precisa
    existir, não ter sido usado, não estar vencido e, quando amarrado a um
    número de série, corresponder ao robô que está falando.

    A chave privada não trafega. O robô a gera no primeiro boot e envia só a
    pública.
    """
    token = session.scalars(
        select(ProvisioningToken).where(
            ProvisioningToken.token_hash == signing.hash_token(payload.provisioning_token)
        )
    ).first()
    if token is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Convite de provisionamento inválido.")
    if token.used_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Convite já utilizado.")

    expires_at = as_utc(token.expires_at)
    if expires_at is not None and expires_at <= datetime.now(UTC):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Convite expirado.")
    if token.serial_number and token.serial_number != payload.serial_number:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Este convite foi emitido para outro número de série.",
        )

    model = session.get(DeviceModel, token.device_model_id)
    if model is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Modelo do convite não existe mais.")
    if payload.protocol_version > model.protocol_version:
        # Falhar aqui é melhor do que descobrir a incompatibilidade em voo.
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Protocolo {payload.protocol_version} é mais novo que o suportado "
            f"({model.protocol_version}). Atualize o servidor antes do robô.",
        )

    device = session.scalars(
        select(Device).where(Device.serial_number == payload.serial_number)
    ).first()
    if device is None:
        plans.exigir(session, token.tenant_id, "devices")
        device = Device(
            tenant_id=token.tenant_id,
            serial_number=payload.serial_number,
            name=_nome_do_robo(session, token.tenant_id, payload.name, model.name,
                               payload.serial_number),
            kind=model.kind,
            device_model_id=model.id,
            farm_id=token.farm_id,
        )
        session.add(device)
        session.flush()
        _create_default_tanks(session, device, capabilities_of(model.capabilities))
    elif device.tenant_id != token.tenant_id:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Número de série já registrado para outro cliente."
        )

    # Reprovisionar revoga o que existia: duas credenciais ativas significariam
    # duas cópias do robô podendo falar ao mesmo tempo.
    for previous in device.credentials:
        if previous.status is not CredentialStatus.REVOKED:
            previous.status = CredentialStatus.REVOKED
            previous.revoked_at = datetime.now(UTC)

    credential = DeviceCredential(
        device_id=device.id, key_id=signing.new_key_id(), public_key=payload.public_key
    )
    session.add(credential)

    device.status = DeviceStatus.ACTIVE
    device.firmware_version = payload.firmware_version
    device.hardware_version = payload.hardware_version
    device.protocol_version = payload.protocol_version
    token.used_at = datetime.now(UTC)
    token.device_id = device.id

    audit.record(
        session,
        tenant_id=device.tenant_id,
        action="device.provisioned",
        subject_type=SubjectType.DEVICE,
        subject_id=device.id,
        actor_type=ActorType.DEVICE,
        actor_id=device.id,
        actor_label=device.serial_number,
        new_state=DeviceStatus.ACTIVE.value,
        payload={"key_id": credential.key_id, "firmware": payload.firmware_version},
    )
    events.publish(
        session,
        events.DEVICE_PROVISIONED,
        tenant_id=device.tenant_id,
        subject_type=SubjectType.DEVICE,
        subject_id=device.id,
    )
    session.commit()

    return DeviceProvisionResponse(
        device_id=device.id,
        tenant_id=device.tenant_id,
        key_id=credential.key_id,
        platform_public_key=signing.platform_public_key(),
        ota_public_key=signing.ota_public_key(),
        protocol_version=PROTOCOL_VERSION,
        server_time=datetime.now(UTC),
    )


@router.get("/devices", response_model=list[DeviceOut], summary="Frota do cliente")
def list_devices(
    kind: DeviceKind | None = None,
    farm_id: str | None = None,
    principal: Principal = Depends(require(rbac.DEVICE_READ)),
    session: Session = Depends(get_session),
) -> list[DeviceOut]:
    statement = scoped(select(Device).order_by(Device.name), Device, principal)
    if kind is not None:
        statement = statement.where(Device.kind == kind)
    if farm_id is not None:
        statement = statement.where(Device.farm_id == farm_id)
    statement = statement.options(selectinload(Device.credentials), selectinload(Device.model))
    cache: dict = {}
    return [
        DeviceOut(**device_snapshot(session, row, cache=cache))
        for row in session.scalars(statement)
    ]


@router.get("/devices/{device_id}", response_model=DeviceOut, summary="Um dispositivo")
def get_device(
    device_id: str,
    principal: Principal = Depends(require(rbac.DEVICE_READ)),
    session: Session = Depends(get_session),
) -> DeviceOut:
    return _device_out(session, get_scoped(session, Device, device_id, principal))


@router.patch(
    "/devices/{device_id}/status", response_model=DeviceOut, summary="Muda o estado de um robô"
)
def update_status(
    device_id: str,
    payload: DeviceStatusUpdate,
    principal: Principal = Depends(require(rbac.DEVICE_MANAGE)),
    session: Session = Depends(get_session),
) -> DeviceOut:
    """Coloca em manutenção, suspende ou aposenta.

    Suspender é a resposta operacional a um robô com comportamento estranho: ele
    continua se autenticando e enviando telemetria — o técnico precisa disso
    para diagnosticar — mas não recebe mais missão.
    """
    device = get_scoped(session, Device, device_id, principal)
    previous = device.status
    device.status = payload.status
    if payload.status is DeviceStatus.MAINTENANCE:
        device.maintenance_note = payload.maintenance_note or payload.reason
    elif previous is DeviceStatus.MAINTENANCE:
        # Saiu da oficina: é esta a data que a frota mostra como última manutenção.
        device.last_maintenance_at = datetime.now(UTC)
        device.maintenance_note = None

    audit.record(
        session,
        tenant_id=principal.tenant_id,
        action="device.status_changed",
        subject_type=SubjectType.DEVICE,
        subject_id=device.id,
        actor_type=ActorType.USER,
        actor_id=principal.user_id,
        actor_label=principal.user.email,
        old_state=previous.value,
        new_state=payload.status.value,
        reason=payload.reason,
    )
    session.commit()
    return _device_out(session, device)


@router.post(
    "/devices/{device_id}/revoke-credentials",
    response_model=Message,
    summary="Revoga as credenciais de um robô",
)
def revoke_credentials(
    device_id: str,
    principal: Principal = Depends(require(rbac.DEVICE_MANAGE)),
    session: Session = Depends(get_session),
) -> Message:
    """Corta o acesso imediatamente — a resposta a um robô roubado ou perdido.

    A partir daqui toda requisição assinada com essas chaves é recusada. Voltar
    a operar exige provisionamento novo, presencial.
    """
    device = get_scoped(session, Device, device_id, principal)
    revoked = 0
    for credential in device.credentials:
        if credential.status is not CredentialStatus.REVOKED:
            credential.status = CredentialStatus.REVOKED
            credential.revoked_at = datetime.now(UTC)
            revoked += 1

    device.status = DeviceStatus.SUSPENDED
    audit.record(
        session,
        tenant_id=principal.tenant_id,
        action="device.credentials_revoked",
        subject_type=SubjectType.DEVICE,
        subject_id=device.id,
        actor_type=ActorType.USER,
        actor_id=principal.user_id,
        actor_label=principal.user.email,
        new_state=DeviceStatus.SUSPENDED.value,
        payload={"revoked": revoked},
    )
    session.commit()
    return Message(
        detail=(
            f"{revoked} credencial(is) revogada(s). O dispositivo foi suspenso e "
            f"precisa ser reprovisionado presencialmente."
        )
    )


def _create_default_tanks(session: Session, device: Device, capabilities: Capabilities) -> None:
    """Cria os tanques declarados pelo modelo.

    Vêm vazios: um tanque nasce sem conteúdo, e é o registro de carga que
    autoriza o safety engine a liberar uma aplicação.
    """
    capacity = capabilities.number("tank_capacity_l", 10.0)
    for index in range(capabilities.tank_count):
        session.add(
            Tank(
                tenant_id=device.tenant_id,
                device_id=device.id,
                index=index,
                capacity_l=capacity,
            )
        )


def device_snapshot(
    session: Session, device: Device, now: datetime | None = None, *, cache: dict | None = None
) -> dict:
    """O retrato de frota de um robô: estado derivado, versões, saúde e o modelo.

    Usado pela frota do cliente e pela de Operações; o estado vem de
    :func:`valtexa.services.fleet_state.derive` e a conformidade do modelo, do
    registry — nada aqui é digitado por alguém.
    """
    situacao = fleet_state.derive(device, now)
    etiquetas = {
        d.etiqueta
        for d in model_registry.designados(session, device, cache=cache)
        if d.etiqueta
    }
    return {
        "id": device.id,
        "serial_number": device.serial_number,
        "name": device.name,
        "kind": device.kind,
        "status": device.status,
        "model_code": device.model.code if device.model else "",
        "farm_id": device.farm_id,
        "firmware_version": device.firmware_version,
        "protocol_version": device.protocol_version,
        "connectivity": situacao.connectivity,
        "battery_percent": device.battery_percent,
        "last_seen_at": device.last_seen_at,
        "last_lat": device.last_lat,
        "last_lon": device.last_lon,
        "active_mission_id": device.active_mission_id,
        "capabilities": device.capabilities,
        "fleet_state": situacao.state.value,
        "fleet_state_label": fleet_state.ROTULOS[situacao.state],
        "fleet_state_reason": situacao.reason,
        "hardware_version": device.hardware_version,
        "runtime_version": device.runtime_version,
        "edge_ai_version": device.edge_ai_version,
        "ai_model_key": device.ai_model_key,
        "ai_model_version": device.ai_model_version,
        "dnaty_version": device.dnaty_version,
        "versions_reported_at": device.versions_reported_at,
        "temperature_c": device.temperature_c,
        "storage_total_bytes": device.storage_total_bytes,
        "storage_free_bytes": device.storage_free_bytes,
        "link_quality": device.link_quality,
        "operating_hours": device.operating_hours,
        "active_faults": list(device.active_faults or []),
        "sync_pending": device.sync_pending,
        "last_sync_at": device.last_sync_at,
        "last_maintenance_at": device.last_maintenance_at,
        "maintenance_note": device.maintenance_note,
        "model_status": model_registry.situacao_do_modelo(session, device, etiquetas),
        "designated_models": sorted(etiquetas),
    }


def _device_out(session: Session, device: Device) -> DeviceOut:
    return DeviceOut(**device_snapshot(session, device))


def _nome_do_robo(session: Session, tenant_id: str, pedido: str | None, modelo: str,
                  serial: str) -> str:
    """Nome livre no cliente (``uq_device_tenant_name``).

    O nome automático era "modelo + 4 últimos dígitos do número de série": dois robôs
    com séries terminadas igual (ROV-A-0007 e ROV-B-0007) davam 500 no provisionamento
    do segundo (achado no ensaio de produção da Parte 9). Agora: os 4 dígitos; se já
    existir, a série inteira; se ainda existir, um sufixo. Nome **pedido** que já
    existe é 409 — quem pediu escolhe outro.
    """

    def livre(nome: str) -> bool:
        return session.scalar(select(Device.id).where(
            Device.tenant_id == tenant_id, Device.name == nome)) is None

    if pedido:
        if not livre(pedido):
            raise HTTPException(status.HTTP_409_CONFLICT,
                                f"Já existe um robô chamado {pedido!r} neste cliente.")
        return pedido
    for nome in (f"{modelo} {serial[-4:]}", f"{modelo} {serial}"):
        if livre(nome):
            return nome
    n = 2
    while not livre(f"{modelo} {serial} ({n})"):
        n += 1
    return f"{modelo} {serial} ({n})"
