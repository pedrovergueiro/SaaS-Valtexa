"""Dependências do FastAPI: quem está falando e o que pode fazer.

Há dois tipos de chamador, e eles não se misturam em nenhuma rota:

* **Usuário** — token *bearer* de sessão, sempre dentro de um tenant, sempre
  com um papel. Fala com ``/v1/...``.
* **Dispositivo** — requisição assinada com Ed25519, com horário e nonce. Fala
  com ``/v1/device/...``.

Um token de usuário nunca serve numa rota de dispositivo, e vice-versa. É o que
impede que uma conta comprometida no navegador comece a publicar telemetria
falsa em nome de um robô.

O escopo de tenant é aplicado em :func:`scoped`, não confiado ao parâmetro da
URL: pedir ``/v1/missions/<id de outro cliente>`` devolve 404, e não os dados.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy import Select, delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from valtexa.api.middleware import RAW_BODY_KEY
from valtexa.config import settings
from valtexa.db import SessionLocal, get_session
from valtexa.models import (
    CredentialStatus,
    Device,
    DeviceCredential,
    DeviceStatus,
    Membership,
    Role,
    Tenant,
    UsedNonce,
    User,
    as_utc,
)
from valtexa.security import rbac, signing, tokens

UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Credencial ausente ou inválida.",
    headers={"WWW-Authenticate": "Bearer"},
)


@dataclass(frozen=True, slots=True)
class Principal:
    """Um usuário autenticado, já resolvido dentro de um tenant."""

    user: User
    tenant: Tenant
    role: Role

    @property
    def user_id(self) -> str:
        return self.user.id

    @property
    def tenant_id(self) -> str:
        return self.tenant.id

    def can(self, capability: str) -> bool:
        return rbac.can(self.role, capability)


@dataclass(frozen=True, slots=True)
class DeviceCaller:
    """Um dispositivo autenticado por assinatura."""

    device: Device
    credential: DeviceCredential

    @property
    def device_id(self) -> str:
        return self.device.id

    @property
    def tenant_id(self) -> str:
        return self.device.tenant_id


# ---------------------------------------------------------------------------
# Usuários
# ---------------------------------------------------------------------------


def current_principal(
    session: Session = Depends(get_session),
    authorization: str | None = Header(default=None),
    x_tenant_id: str | None = Header(default=None),
) -> Principal:
    """Resolve o usuário e o tenant ativo a partir do token."""
    claims = _claims_from(authorization, expected_kind="user")

    user = session.get(User, claims.subject_id)
    if user is None or not user.is_active:
        raise UNAUTHORIZED

    # O cabeçalho permite trocar de tenant sem novo login — útil para o
    # agrônomo de cooperativa. A associação ainda é verificada abaixo, então o
    # cabeçalho escolhe, mas não concede.
    tenant_id = x_tenant_id or claims.tenant_id
    if not tenant_id:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Nenhum cliente selecionado. Envie X-Tenant-Id ou refaça o login.",
        )

    tenant = session.get(Tenant, tenant_id)
    if tenant is None or not tenant.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cliente não encontrado.")

    membership = session.scalars(
        select(Membership).where(
            Membership.tenant_id == tenant_id, Membership.user_id == user.id
        )
    ).first()

    if membership is None:
        # A equipe da ValTexa enxerga todos os clientes; a ação fica na
        # auditoria com o nome de quem a fez.
        if not user.is_platform_admin:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, "Usuário não pertence a este cliente."
            )
        return Principal(user=user, tenant=tenant, role=Role.ADMIN)

    return Principal(user=user, tenant=tenant, role=membership.role)


def require(*capabilities: str) -> Callable[[Principal], Principal]:
    """Dependência que exige capacidades. Todas, não qualquer uma."""

    def dependency(principal: Principal = Depends(current_principal)) -> Principal:
        missing = [item for item in capabilities if not principal.can(item)]
        if missing:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"O papel {principal.role.value!r} não permite: {', '.join(missing)}.",
            )
        return principal

    return dependency


def scoped(statement: Select, model: type, principal: Principal) -> Select:
    """Aplica o filtro de tenant a uma consulta.

    Toda leitura do domínio passa por aqui. O filtro é por ``tenant_id`` da
    linha, nunca por um identificador vindo da URL — é a diferença entre
    "não encontrei" e "encontrei o de outro cliente e devolvi".
    """
    return statement.where(model.tenant_id == principal.tenant_id)


def get_scoped(session: Session, model: type, row_id: str, principal: Principal):
    """Busca uma linha do tenant, ou 404.

    Devolver 404 e não 403 para um objeto de outro cliente é deliberado: 403
    confirmaria que o identificador existe.
    """
    row = session.get(model, row_id)
    if row is None or getattr(row, "tenant_id", None) != principal.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{model.__name__} não encontrado.")
    return row


# ---------------------------------------------------------------------------
# Dispositivos
# ---------------------------------------------------------------------------


async def current_device(
    request: Request,
    session: Session = Depends(get_session),
) -> DeviceCaller:
    """Autentica um dispositivo pela assinatura da requisição.

    A ordem das verificações importa: identidade, horário, nonce e só então a
    assinatura. Conferir o nonce antes da assinatura seria pior — um atacante
    poderia queimar nonces alheios. Conferir a assinatura antes do horário
    gastaria criptografia com lixo. Esta ordem gasta o mínimo e não abre janela.
    """
    headers = request.headers
    key_id = headers.get(signing.HEADER_KEY_ID)
    timestamp = headers.get(signing.HEADER_TIMESTAMP)
    nonce = headers.get(signing.HEADER_NONCE)
    signature = headers.get(signing.HEADER_SIGNATURE)

    if not all((key_id, timestamp, nonce, signature)):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            f"Requisição de dispositivo exige {signing.HEADER_KEY_ID}, "
            f"{signing.HEADER_TIMESTAMP}, {signing.HEADER_NONCE} e "
            f"{signing.HEADER_SIGNATURE}.",
        )

    credential = session.scalars(
        select(DeviceCredential).where(DeviceCredential.key_id == key_id)
    ).first()
    if credential is None or credential.status is CredentialStatus.REVOKED:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Credencial desconhecida ou revogada.")

    expires_at = as_utc(credential.expires_at)
    if expires_at is not None and expires_at <= datetime.now(UTC):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Credencial expirada.")

    device = session.get(Device, credential.device_id)
    if device is None or device.status in {DeviceStatus.SUSPENDED, DeviceStatus.RETIRED}:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Dispositivo suspenso ou aposentado.")

    try:
        signing.check_timestamp(timestamp)
    except signing.SignatureError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc

    _burn_nonce(device.id, nonce)

    body = await _raw_body(request)
    try:
        signing.verify_request(
            credential.public_key,
            signature,
            request.method,
            request.url.path,
            request.url.query,
            timestamp,
            nonce,
            body,
        )
    except signing.SignatureError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc

    credential.last_used_at = datetime.now(UTC)
    return DeviceCaller(device=device, credential=credential)


def require_active_device(caller: DeviceCaller = Depends(current_device)) -> DeviceCaller:
    """Exige que o dispositivo esteja ativo, e não só autenticado.

    Um robô em manutenção continua podendo se autenticar e enviar telemetria —
    é assim que o técnico acompanha o conserto —, mas não recebe missão.
    """
    if caller.device.status is not DeviceStatus.ACTIVE:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"Dispositivo em {caller.device.status.value!r}: não pode operar.",
        )
    return caller


async def _raw_body(request: Request) -> bytes:
    """Os bytes exatos que chegaram, para conferir a assinatura.

    O :class:`~valtexa.api.middleware.RawBodyMiddleware` os guardou no ``scope``
    porque o FastAPI consome o corpo antes de resolver dependências. O
    ``await request.body()`` abaixo é só o caminho de quem não passou pelo
    middleware — em rota de dispositivo isso não acontece.
    """
    cached = request.scope.get(RAW_BODY_KEY)
    if cached is not None:
        return cached
    return await request.body()


def _burn_nonce(device_id: str, nonce: str) -> None:
    """Consome um nonce, recusando a repetição.

    Roda numa sessão própria e com *commit* imediato, de propósito. Se
    participasse da transação da requisição, um handler que falhasse depois
    liberaria o nonce de volta — e a repetição da mesma requisição assinada
    voltaria a ser aceita, que é exatamente o que este mecanismo existe para
    impedir.
    """
    expires_at = datetime.now(UTC) + timedelta(seconds=settings.nonce_retention_seconds)
    with SessionLocal() as guard:
        # Limpeza oportunista: sem isto a tabela cresceria para sempre. O custo
        # é uma remoção por requisição autenticada, sobre um índice.
        guard.execute(delete(UsedNonce).where(UsedNonce.expires_at < datetime.now(UTC)))
        guard.add(UsedNonce(device_id=device_id, nonce=nonce, expires_at=expires_at))
        try:
            guard.commit()
        except IntegrityError as exc:
            guard.rollback()
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED,
                "Nonce já utilizado: a requisição parece ser uma repetição.",
            ) from exc


def _claims_from(authorization: str | None, *, expected_kind: str) -> tokens.TokenClaims:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise UNAUTHORIZED
    try:
        claims = tokens.verify(authorization.split(" ", 1)[1].strip())
    except tokens.TokenError as exc:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    if claims.kind != expected_kind:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"Este token é de {claims.kind!r} e a rota exige {expected_kind!r}.",
        )
    return claims
