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
    PlatformRole,
    Role,
    SupportMode,
    SupportSession,
    Tenant,
    UsedNonce,
    User,
    as_utc,
)
from valtexa.observability import contexto
from valtexa.security import rbac, signing, tokens
from valtexa.services import audit, sessions, support_sessions

UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Credencial ausente ou inválida.",
    headers={"WWW-Authenticate": "Bearer"},
)


@dataclass(frozen=True, slots=True)
class Principal:
    """Um usuário autenticado, já resolvido dentro de um tenant.

    Há três jeitos de chegar aqui, e ``can`` responde diferente em cada um:

    * **membro do cliente** — o papel da associação (``role``);
    * **sessão de suporte** (``support_session``) — a equipe da ValTexa dentro do
      cliente, às claras: leitura por padrão, escrita só no modo assistido;
    * **equipe em rota de plataforma** (``via_platform``) — sem associação, com o
      cliente só como contexto; vale apenas o papel de plataforma.
    """

    user: User
    tenant: Tenant
    role: Role
    session_id: str | None = None
    """A sessão por onde esta requisição entrou.

    Existe para a troca de senha poder derrubar as *outras* sessões sem
    derrubar a de quem está trocando.
    """
    platform_role: PlatformRole | None = None
    support_session: SupportSession | None = None
    via_platform: bool = False

    @property
    def user_id(self) -> str:
        return self.user.id

    @property
    def tenant_id(self) -> str:
        return self.tenant.id

    @property
    def is_support(self) -> bool:
        return self.support_session is not None

    def can(self, capability: str) -> bool:
        if self.support_session is not None:
            if self.support_session.mode is SupportMode.ASSISTIDO:
                return rbac.can(rbac.SUPPORT_ASSISTED_ROLE, capability)
            rbac.can(Role.VIEWER, capability)  # valida o nome da capacidade
            return capability in rbac.SUPPORT_READ_CAPABILITIES
        if self.via_platform:
            return rbac.platform_can(self.platform_role, capability)
        # Papel de plataforma não vale em rota de cliente: dentro de uma fazenda
        # vale o papel que se tem nela.
        return rbac.can(self.role, capability)

    @property
    def capabilities(self) -> frozenset[str]:
        """O que o console deve mostrar a esta pessoa neste contexto."""
        if self.support_session is not None:
            if self.support_session.mode is SupportMode.ASSISTIDO:
                return rbac.capabilities_of(rbac.SUPPORT_ASSISTED_ROLE)
            return frozenset(rbac.SUPPORT_READ_CAPABILITIES)
        if self.via_platform:
            return rbac.platform_capabilities_of(self.platform_role)
        return rbac.capabilities_for(self.role, platform_role=self.platform_role)


@dataclass(frozen=True, slots=True)
class PlatformCaller:
    """Alguém da equipe da ValTexa numa rota de plataforma sem cliente ativo."""

    user: User
    session_id: str | None

    @property
    def user_id(self) -> str:
        return self.user.id

    @property
    def platform_role(self) -> PlatformRole | None:
        return self.user.platform_role

    def can(self, capability: str) -> bool:
        return rbac.platform_can(self.user.platform_role, capability)


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

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

SUPPORT_REQUIRED = (
    "Você é da equipe da ValTexa e não é membro deste cliente. Para ver ou agir nos "
    "dados dele, abra uma sessão de suporte ('entrar como cliente'), com motivo e "
    "prazo: POST /v1/platform/support-sessions."
)


def current_user(
    session: Session = Depends(get_session),
    authorization: str | None = Header(default=None),
) -> User:
    """O usuário do token, sem exigir cliente ativo.

    Serve só às rotas que existem justamente para escolher o cliente — um
    agrônomo de cooperativa entra sem cliente definido e precisa ver a lista.
    Token de sessão de suporte não serve aqui: ele vale só dentro do cliente
    para o qual foi aberto.
    """
    claims = _claims_from(authorization, expected_kind="user")
    _recusa_token_de_suporte(claims)
    user = session.get(User, claims.subject_id)
    if user is None or not user.is_active:
        raise UNAUTHORIZED
    _exige_sessao_viva(session, claims)
    contexto.anotar(user_id=user.id)
    return user


def current_user_ou_suporte(
    session: Session = Depends(get_session),
    authorization: str | None = Header(default=None),
) -> User:
    """O usuário do token, **inclusive** o de sessão de suporte, sem cliente.

    Só para o que não toca dado de cliente nenhum — achar um endereço no mapa, saber
    qual satélite o console usa. A equipe que está dentro de um cliente desenhando o
    talhão dele precisa disso tanto quanto o produtor.
    """
    claims = _claims_from(authorization, expected_kind="user")
    user = session.get(User, claims.subject_id)
    if user is None or not user.is_active:
        raise UNAUTHORIZED
    _exige_sessao_viva(session, claims)
    contexto.anotar(user_id=user.id)
    return user


def current_principal(
    request: Request,
    session: Session = Depends(get_session),
    authorization: str | None = Header(default=None),
    x_tenant_id: str | None = Header(default=None),
) -> Principal:
    """Resolve o usuário e o tenant ativo a partir do token.

    A equipe da ValTexa **não** entra em cliente de que não é membro por esta
    porta: até a fase 2 entrava, como ``ADMIN``, sem motivo nem rastro de
    entrada — o acesso silencioso que o brief (seção 29) proíbe. Agora a porta é
    a sessão de suporte, que tem motivo, prazo, modo e auditoria.
    """
    return _resolve_principal(request, session, authorization, x_tenant_id, platform=False)


def current_principal_or_platform(
    request: Request,
    session: Session = Depends(get_session),
    authorization: str | None = Header(default=None),
    x_tenant_id: str | None = Header(default=None),
) -> Principal:
    """Como :func:`current_principal`, aceitando também a equipe sem associação.

    Só para rotas que descrevem quem chama (``/auth/me``): a equipe precisa
    saber as próprias capacidades com um cliente como contexto, sem ganhar com
    isso acesso ao dado dele.
    """
    return _resolve_principal(request, session, authorization, x_tenant_id, platform=True)


def _resolve_principal(
    request: Request,
    session: Session,
    authorization: str | None,
    x_tenant_id: str | None,
    *,
    platform: bool,
) -> Principal:
    claims = _claims_from(authorization, expected_kind="user")

    user = session.get(User, claims.subject_id)
    if user is None or not user.is_active:
        raise UNAUTHORIZED
    sessao_id = _exige_sessao_viva(session, claims)

    suporte_id = claims.extra.get("sup")
    if suporte_id:
        return _principal_de_suporte(
            request, session, user, sessao_id, suporte_id, x_tenant_id
        )

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
    if tenant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cliente não encontrado.")
    if not tenant.is_active and not user.is_platform_admin:
        # Cliente desativado deixa de operar — mas a equipe da ValTexa continua
        # entrando. É justamente depois do fim de um contrato que a trilha de
        # auditoria é mais procurada: apuração, disputa, prazo legal de guarda.
        # Trancá-la junto com a operação apagaria na prática o que a lei manda
        # guardar, sem apagar uma linha do banco.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cliente não encontrado.")

    membership = session.scalars(
        select(Membership).where(
            Membership.tenant_id == tenant_id, Membership.user_id == user.id
        )
    ).first()

    contexto.anotar(tenant_id=tenant_id, user_id=user.id)
    if membership is None:
        if user.platform_role is None:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, "Usuário não pertence a este cliente."
            )
        if not platform:
            raise HTTPException(status.HTTP_403_FORBIDDEN, SUPPORT_REQUIRED)
        return Principal(
            user=user,
            tenant=tenant,
            role=Role.VIEWER,
            session_id=sessao_id,
            platform_role=user.platform_role,
            via_platform=True,
        )

    return Principal(
        user=user,
        tenant=tenant,
        role=membership.role,
        session_id=sessao_id,
        platform_role=user.platform_role,
    )


def _principal_de_suporte(
    request: Request,
    session: Session,
    user: User,
    sessao_id: str,
    suporte_id: str,
    x_tenant_id: str | None,
    *,
    consulta: bool = False,
) -> Principal:
    """A equipe dentro de um cliente por uma sessão de suporte.

    Toda requisição — leitura inclusive — vira uma linha na auditoria do
    cliente, com o interno como ator, gravada numa transação própria: uma
    leitura não faz *commit*, e uma escrita recusada não pode levar o rastro
    junto no *rollback*.
    """
    suporte = session.get(SupportSession, suporte_id)
    if suporte is None or suporte.user_id != user.id:
        raise SESSAO_ENCERRADA
    if not suporte.is_open:
        support_sessions.encerrar_vencida(suporte_id)
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Sessão de suporte encerrada ou vencida. Abra outra, com novo motivo.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if x_tenant_id and x_tenant_id != suporte.tenant_id:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Esta sessão de suporte vale só para o cliente em que foi aberta.",
        )
    if not rbac.platform_can(user.platform_role, rbac.PLATFORM_SUPPORT_SESSION):
        # O papel foi retirado com a sessão aberta: ela deixa de valer agora.
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Seu papel de plataforma não permite mais esta sessão."
        )

    assistido = suporte.mode is SupportMode.ASSISTIDO and rbac.platform_can(
        user.platform_role, rbac.PLATFORM_SUPPORT_ASSIST
    )
    # ``consulta``: POST que não grava nada (encaixe de contorno, planejamento) vale
    # também no modo leitura — continua na auditoria como qualquer requisição.
    permitido = assistido or consulta or request.method in SAFE_METHODS
    support_sessions.registrar_requisicao(
        suporte_id,
        user=user,
        method=request.method,
        path=request.url.path,
        permitido=permitido,
    )
    if not permitido:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Sessão de suporte em modo leitura: nenhuma alteração é permitida. Para "
            "agir pelo cliente, ligue o modo assistido com um motivo "
            f"(POST /v1/platform/support-sessions/{suporte.id}/mode).",
        )

    tenant = session.get(Tenant, suporte.tenant_id)
    if tenant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cliente não encontrado.")
    session.info[audit.SUPPORT_SESSION_KEY] = suporte.id
    contexto.anotar(tenant_id=tenant.id, user_id=user.id, support_session_id=suporte.id)
    return Principal(
        user=user,
        tenant=tenant,
        role=rbac.SUPPORT_ASSISTED_ROLE if assistido else Role.VIEWER,
        session_id=sessao_id,
        platform_role=user.platform_role,
        support_session=suporte,
    )


def require(*capabilities: str) -> Callable[[Principal], Principal]:
    """Dependência que exige capacidades. Todas, não qualquer uma."""

    def dependency(principal: Principal = Depends(current_principal)) -> Principal:
        missing = [item for item in capabilities if not principal.can(item)]
        if missing:
            quem = (
                f"A sessão de suporte em modo {principal.support_session.mode.value!r}"
                if principal.support_session is not None
                else f"O papel {principal.role.value!r}"
            )
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"{quem} não permite: {', '.join(missing)}.",
            )
        return principal

    return dependency


def _equipe_do_token(session: Session, authorization: str | None) -> tuple[User, str]:
    """O usuário da equipe da ValTexa por trás do token, e a sessão dele."""
    claims = _claims_from(authorization, expected_kind="user")
    _recusa_token_de_suporte(claims)
    user = session.get(User, claims.subject_id)
    if user is None or not user.is_active:
        raise UNAUTHORIZED
    sessao_id = _exige_sessao_viva(session, claims)
    contexto.anotar(user_id=user.id)
    if user.platform_role is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Esta área é da equipe da ValTexa.")
    return user, sessao_id


def _exige_capacidades_de_plataforma(user: User, capabilities: tuple[str, ...]) -> None:
    faltam = [item for item in capabilities if not rbac.platform_can(user.platform_role, item)]
    if faltam:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"O papel de plataforma {user.platform_role.value!r} não permite: "
            f"{', '.join(faltam)}.",
        )


def require_platform(*capabilities: str) -> Callable[..., PlatformCaller]:
    """Rota de plataforma que não depende de cliente ativo (planos, sessões de suporte)."""

    def dependency(
        session: Session = Depends(get_session),
        authorization: str | None = Header(default=None),
    ) -> PlatformCaller:
        user, sessao_id = _equipe_do_token(session, authorization)
        _exige_capacidades_de_plataforma(user, capabilities)
        return PlatformCaller(user=user, session_id=sessao_id)

    return dependency


def require_platform_in_tenant(*capabilities: str) -> Callable[..., Principal]:
    """Rota de plataforma que trabalha **sobre** um cliente (importar coleta, relevo).

    É a fronteira entre o painel administrativo e o console do cliente. Não é
    checada por papel de cliente: o papel diz o que alguém pode na fazenda dele,
    e o dono da fazenda mais graduado do mundo não importa coleta nem mexe em
    dataset. É checada pelo **papel de plataforma**, capacidade a capacidade.

    O cliente vem de ``X-Tenant-Id`` (ou do token) e continua sendo filtrado —
    o administrador trabalha *dentro* de um cliente por vez, e é assim que a
    auditoria registra em nome de quem e sobre quem ele agiu. Não exige
    associação: quem importa uma coleta não é membro da fazenda.
    """

    def dependency(
        session: Session = Depends(get_session),
        authorization: str | None = Header(default=None),
        x_tenant_id: str | None = Header(default=None),
    ) -> Principal:
        user, sessao_id = _equipe_do_token(session, authorization)
        _exige_capacidades_de_plataforma(user, capabilities)
        claims = _claims_from(authorization, expected_kind="user")
        tenant_id = x_tenant_id or claims.tenant_id
        if not tenant_id:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "Nenhum cliente selecionado. Envie X-Tenant-Id.",
            )
        tenant = session.get(Tenant, tenant_id)
        if tenant is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Cliente não encontrado.")
        return Principal(
            user=user,
            tenant=tenant,
            role=Role.VIEWER,
            session_id=sessao_id,
            platform_role=user.platform_role,
            via_platform=True,
        )

    return dependency


def require_platform_ou_suporte(
    *capabilities: str, exige_cliente: bool = True
) -> Callable[..., Principal | PlatformCaller]:
    """A equipe pela porta da plataforma **ou de dentro de uma sessão de suporte**.

    Para as consultas da equipe que o editor de contorno faz dentro do cliente — encaixe
    de contorno pela IA e planejamento de rota. Elas não gravam nada; sem esta porta, a
    equipe que entrou no cliente (com motivo, prazo e auditoria) via o botão da IA
    recusar o próprio token. Na sessão de suporte, a requisição vai para a auditoria do
    cliente e vale só no cliente da sessão; em todos os casos o **papel de plataforma**
    precisa ter as capacidades.
    """
    na_plataforma = (require_platform_in_tenant(*capabilities) if exige_cliente
                     else require_platform(*capabilities))

    def dependency(
        request: Request,
        session: Session = Depends(get_session),
        authorization: str | None = Header(default=None),
        x_tenant_id: str | None = Header(default=None),
    ) -> Principal | PlatformCaller:
        claims = _claims_from(authorization, expected_kind="user")
        suporte_id = claims.extra.get("sup")
        if not suporte_id:
            if exige_cliente:
                return na_plataforma(session, authorization, x_tenant_id)
            return na_plataforma(session, authorization)
        user = session.get(User, claims.subject_id)
        if user is None or not user.is_active:
            raise UNAUTHORIZED
        sessao_id = _exige_sessao_viva(session, claims)
        principal = _principal_de_suporte(request, session, user, sessao_id, suporte_id,
                                          x_tenant_id, consulta=True)
        _exige_capacidades_de_plataforma(user, capabilities)
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
    contexto.anotar(tenant_id=device.tenant_id, device_id=device.id)
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


SESSAO_ENCERRADA = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Sessão encerrada. Entre de novo.",
    headers={"WWW-Authenticate": "Bearer"},
)


def _exige_sessao_viva(session: Session, claims: tokens.TokenClaims) -> str:
    """Confere no banco se a sessão deste token continua de pé.

    É o passo que transforma o token de *bearer* puro em credencial revogável.
    Sem ele, tudo o que a tela de sessões faria seria escrever numa tabela que
    ninguém lê — e "derrubar sessão" seria um botão que não derruba nada.

    Um token sem ``sid`` é recusado, e não tolerado: são os emitidos antes de a
    tabela existir, e aceitá-los manteria vivas justamente as sessões que não se
    consegue alcançar.
    """
    linha = sessions.viva(session, claims.extra.get("sid"))
    if linha is None:
        raise SESSAO_ENCERRADA
    sessions.marcar_presenca(session, linha)
    return linha.id


def _recusa_token_de_suporte(claims: tokens.TokenClaims) -> None:
    """Token de sessão de suporte vale dentro do cliente, e só lá."""
    if claims.extra.get("sup"):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Token de sessão de suporte vale só dentro do cliente. Use o seu login normal "
            "para as áreas da plataforma.",
        )


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
