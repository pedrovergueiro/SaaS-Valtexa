"""Contrato HTTP da plataforma.

Os modelos de saída são achatados de propósito: o cliente recebe identificadores
e valores, nunca o objeto ORM serializado por reflexão. Assim, adicionar uma
coluna interna não vaza para a API por acidente.

O contrato é o mesmo para o frontend e para os robôs. Quando o SaaS visual for
construído, ele consome exatamente estes esquemas — nenhuma rota nova, nenhuma
regra que só exista na tela.
"""

from __future__ import annotations

import math
from datetime import date, datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints, field_validator

from valtexa.models.base import as_utc
from valtexa.models.enums import (
    ApplicationState,
    CapturePlatform,
    CollectionFileState,
    CollectionKind,
    CollectionSource,
    CollectionState,
    Connectivity,
    DatasetSampleState,
    DecisionOutcome,
    DeviceKind,
    DeviceStatus,
    DiagnosisStatus,
    MissionKind,
    MissionState,
    ModelVersionState,
    PlatformRole,
    ReleaseScope,
    Role,
    RtkFix,
    SafetyVerdict,
    SubscriptionStatus,
    SupportMode,
    VerificationConclusion,
)
from valtexa.services import documentos

# ``model_`` é namespace protegido do Pydantic; o domínio usa "modelo" o tempo
# todo, então o namespace fica liberado nos esquemas que precisam.
ALLOW_MODEL_PREFIX = ConfigDict(protected_namespaces=())


class ApiModel(BaseModel):
    """Base de todos os esquemas: horário sempre em UTC, com o fuso explícito.

    O SQLite devolve o horário sem fuso. Serializado assim, o navegador o leria
    como hora *local* — e o console mostraria quatro horas de diferença em
    Sorriso, justamente no carimbo de uma aplicação de defensivo. Na entrada, a
    mesma regra vale para o robô: horário sem fuso é UTC, como diz o protocolo.

    NaN e infinito são recusados na entrada. O ``json.loads`` do metadado do
    robô os aceita, e um ``x_m`` NaN embaralharia a associação por planta (toda
    comparação com NaN é falsa); na saída o ``JSONResponse`` já os recusa.
    """

    model_config = ConfigDict(allow_inf_nan=False)

    @field_validator("*", mode="after")
    @classmethod
    def _utc(cls, value: object) -> object:
        if isinstance(value, datetime):
            return as_utc(value)
        return value

Polygon = Annotated[
    list[list[float]],
    Field(
        min_length=3,
        description="Anel [[lon, lat], ...] em WGS84, sem repetir o primeiro ponto no fim.",
    ),
]
Slug = Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9-]{1,62}$")]
Name = Annotated[str, StringConstraints(min_length=1, max_length=160, strip_whitespace=True)]


class Message(ApiModel):
    """Resposta simples de confirmação."""

    detail: str


class ErrorResponse(ApiModel):
    detail: str


# ---------------------------------------------------------------------------
# Autenticação e organização
# ---------------------------------------------------------------------------


class LoginRequest(ApiModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=256)
    tenant: Slug | None = Field(
        default=None,
        description="Cliente a abrir. Opcional quando o usuário pertence a um só.",
    )


class TokenResponse(ApiModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
    tenant_id: str | None
    role: Role | None
    capabilities: list[str]


class MembershipOut(ApiModel):
    tenant_id: str
    tenant_name: str
    tenant_slug: str
    role: Role
    access: Literal["membro", "plataforma"] = Field(
        default="membro",
        description=(
            "'plataforma': a pessoa é da equipe da ValTexa e não é membro. O cliente "
            "aparece para as rotas de plataforma; os dados dele só por sessão de suporte."
        ),
    )


class SupportSessionOut(ApiModel):
    id: str
    tenant_id: str
    tenant_name: str | None = None
    user_id: str
    user_email: str | None = None
    reason: str
    ticket_ref: str | None
    ticket_id: str | None = None
    mode: SupportMode
    assisted_reason: str | None
    started_at: datetime
    expires_at: datetime
    ended_at: datetime | None
    ended_reason: str | None
    request_count: int
    is_open: bool


class MeResponse(ApiModel):
    id: str
    email: str
    full_name: str
    is_platform_admin: bool
    platform_role: PlatformRole | None = None
    active_tenant_id: str
    role: Role
    access: Literal["membro", "plataforma", "suporte"] = "membro"
    capabilities: list[str]
    memberships: list[MembershipOut]
    support_session: SupportSessionOut | None = Field(
        default=None,
        description="Presente quando o acesso é por sessão de suporte: é a faixa no topo.",
    )


class SupportSessionStart(ApiModel):
    tenant_id: str
    reason: str = Field(min_length=10, max_length=2000, description="Por que entrar. Obrigatório.")
    duration_minutes: int = Field(default=120, ge=5, le=480)
    ticket_ref: str | None = Field(default=None, max_length=80)
    ticket_id: str | None = Field(
        default=None, max_length=32,
        description="Chamado do mesmo cliente que motiva a entrada (aparece no histórico dele).",
    )
    assisted_reason: str | None = Field(
        default=None,
        max_length=2000,
        description="Preencha só para abrir já com escrita (modo assistido), com o motivo.",
    )


class SupportSessionStarted(ApiModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
    tenant_id: str
    session: SupportSessionOut


class SupportModeChange(ApiModel):
    mode: SupportMode
    reason: str = Field(default="", max_length=2000)


class SupportSessionEnd(ApiModel):
    reason: str = Field(default="saiu", max_length=200)


class PlatformRoleUpdate(ApiModel):
    platform_role: PlatformRole | None


class PlatformUserOut(ApiModel):
    id: str
    email: str
    full_name: str
    platform_role: PlatformRole | None
    is_active: bool


class TenantContact(ApiModel):
    """Contato, endereço e contrato de um cliente.

    Tudo opcional: o cadastro nasce numa ligação, com o nome e o telefone, e se
    completa depois. Campo obrigatório aqui faria quem atende inventar um
    endereço para conseguir salvar, e endereço inventado é pior que vazio —
    parece preenchido, e ninguém volta para conferir.
    """

    contact_name: str | None = Field(default=None, max_length=160)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=40)
    address: str | None = Field(default=None, max_length=255)
    city: str | None = Field(default=None, max_length=120)
    state: str | None = Field(default=None, min_length=2, max_length=2)
    postal_code: str | None = Field(default=None, max_length=16)
    contracted_service: str | None = Field(
        default=None,
        max_length=120,
        description=(
            "Legado (antes dos planos): operação contratada em texto livre. O que limita "
            "o cliente agora é o plano (``/v1/admin/tenants/{id}/subscription``); este "
            "texto foi copiado para a observação da assinatura na migração 0011."
        ),
    )
    notes: str | None = Field(default=None, max_length=1000)


class TenantCreate(TenantContact):
    name: Name
    slug: Slug
    document: str | None = Field(default=None, max_length=32, description="CNPJ ou CPF.")


class TenantUpdate(TenantContact):
    """Alteração de cadastro. O apelido não muda: ele é a identidade pública."""

    name: Name | None = None
    document: str | None = Field(default=None, max_length=32)
    is_active: bool | None = None


class TenantOut(TenantContact):
    id: str
    name: str
    slug: str
    document: str | None
    is_active: bool
    created_at: datetime
    farms: int = Field(default=0, description="Quantas propriedades o cliente tem.")
    fields: int = Field(default=0, description="Quantos talhões, somados.")
    area_ha: float | None = Field(
        default=None, description="Área somada dos talhões desenhados."
    )
    plan_code: str | None = Field(default=None, description="Plano da assinatura vigente.")
    plan_name: str | None = None
    subscription_status: SubscriptionStatus | None = None


class OnboardFarm(ApiModel):
    """A propriedade que nasce junto com o cliente."""

    name: Name
    center_lat: float = Field(ge=-90, le=90)
    center_lon: float = Field(ge=-180, le=180)
    area_ha: float | None = Field(default=None, gt=0)
    timezone: str = Field(default="America/Sao_Paulo", max_length=64)


class OnboardField(ApiModel):
    """O primeiro talhão. O contorno pode vir vazio e ser desenhado depois."""

    name: Name
    crop: str = Field(max_length=64, description="'coffee', 'corn', 'soy'.")
    variety: str | None = Field(default=None, max_length=120)
    row_spacing_m: float | None = Field(default=None, gt=0)
    plant_spacing_m: float | None = Field(default=None, gt=0, le=50)
    row_count: int | None = Field(default=None, ge=1, le=100_000)
    boundary: list[list[float]] = Field(
        default_factory=list,
        description=(
            "Polígono [[lon, lat], ...]. Vazio é válido: o contorno costuma vir "
            "depois, no editor, com a imagem de satélite na frente."
        ),
    )


class OnboardIn(ApiModel):
    """Cadastro de cliente em uma etapa: cliente, propriedade e primeiro talhão.

    As três coisas vêm juntas porque é assim que a informação chega — numa
    ligação com o produtor, não em três visitas ao sistema. Propriedade e talhão
    são opcionais: dá para cadastrar só o cliente e voltar depois.
    """

    tenant: TenantCreate
    plan_code: str | None = Field(
        default=None,
        description="Plano do cliente. Sem ele, o cliente nasce no 'piloto' (sem limites).",
    )
    farm: OnboardFarm | None = None
    field: OnboardField | None = None


class OnboardOut(ApiModel):
    tenant: TenantOut
    farm_id: str | None = None
    field_id: str | None = None
    warnings: list[str] = Field(default_factory=list)


class PasswordChange(ApiModel):
    """Troca da própria senha. Exige a atual.

    Exigir a senha atual não protege contra quem já roubou a sessão — esse já
    entrou. Protege contra o outro caso, que é o comum: a estação destravada na
    sala da fazenda, com a sessão de alguém aberta. Sem a senha atual, trocar a
    senha alheia seria questão de passar por perto.
    """

    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=8, max_length=256)


class PasswordReset(ApiModel):
    """Redefinição feita por um administrador, para quem perdeu o acesso.

    É o caminho de recuperação desta plataforma: não há envio de e-mail, então
    não há link de redefinição. Alguém com ``user:manage`` no cliente define uma
    senha nova e a entrega por outro canal — e a ação fica na auditoria, com o
    nome de quem redefiniu e de quem teve a senha trocada.
    """

    new_password: str = Field(min_length=8, max_length=256)


class RouteEdit(ApiModel):
    """A rota que o operador desenhou, passada a passada.

    Só o percurso. Distância, tempo e energia saem da geometria no servidor —
    aceitá-los do cliente abriria a porta para o número na tela discordar do
    número que o robô vai cumprir.
    """

    legs: list[list[list[float]]] = Field(
        min_length=1,
        description=(
            "Passadas, cada uma com ao menos dois pontos [lon, lat]. A ordem "
            "das passadas é a ordem de execução."
        ),
    )
    reason: str | None = Field(
        default=None,
        max_length=300,
        description="Por que a rota foi corrigida. Vai para a trilha de auditoria.",
    )


class RouteReplan(ApiModel):
    """Premissas novas para o planejador refazer a rota.

    Tudo opcional: o que não vier fica como estava. Um replanejamento sem
    campo nenhum ainda faz trabalho — é como se pede ao sistema para aplicar
    uma leitura de terreno que chegou depois de a missão ter sido criada.
    """

    swath_m: float | None = Field(default=None, gt=0.1, le=60.0)
    row_azimuth_deg: float | None = Field(default=None, ge=0.0, lt=360.0)
    obstacle_margin_m: float | None = Field(
        default=None,
        ge=0.0,
        le=50.0,
        description="Folga a deixar em volta de cada obstáculo intransponível.",
    )


class SessionOut(ApiModel):
    """Uma sessão aberta, como a pessoa a vê na lista.

    Nada aqui é o token — só o bastante para alguém se reconhecer ("Chrome no
    Windows, ontem à noite, deste IP") e decidir o que derrubar. Devolver o
    token seria espalhar a credencial por mais um lugar.
    """

    id: str
    created_at: datetime
    last_seen_at: datetime | None = None
    expires_at: datetime
    user_agent: str | None = None
    ip_address: str | None = None
    current: bool = Field(
        default=False,
        description="Verdadeiro para a sessão que está fazendo esta requisição.",
    )


class SessionRevoked(ApiModel):
    revoked: int = Field(description="Quantas sessões foram encerradas.")
    detail: str


class UserInvite(ApiModel):
    email: EmailStr
    full_name: Name
    password: str = Field(min_length=8, max_length=256)
    role: Role


class UserOut(ApiModel):
    id: str
    email: str
    full_name: str
    role: Role
    is_active: bool


# ---------------------------------------------------------------------------
# Geografia
# ---------------------------------------------------------------------------


class FarmRegistry(ApiModel):
    """Identificação da propriedade (brief, seção 5): produtor, documento, localização,
    cultura, CAR e responsável técnico. Tudo opcional — fazenda antiga continua válida.

    CPF/CNPJ e CAR são conferidos e guardados normalizados (ver
    :mod:`valtexa.services.documentos`); texto vazio vale como "sem valor".
    """

    owner_name: str | None = Field(
        default=None, max_length=160, description="Proprietário ou produtor responsável."
    )
    owner_document: str | None = Field(
        default=None,
        max_length=32,
        description="CPF ou CNPJ do proprietário; aceita com pontuação, guarda só dígitos.",
    )
    city: str | None = Field(default=None, max_length=120, description="Município.")
    state: str | None = Field(default=None, max_length=2, description="UF, duas letras.")
    main_crop: str | None = Field(
        default=None, max_length=64, description="Cultura principal da propriedade."
    )
    car_code: str | None = Field(
        default=None,
        max_length=64,
        description="Recibo do CAR (UF-1234567-<32 hex>); aceita com pontos.",
    )
    technical_lead: str | None = Field(
        default=None,
        max_length=160,
        description="Responsável técnico (agrônomo), com o registro no conselho se houver.",
    )
    notes: str | None = Field(default=None, max_length=4000)

    @field_validator(
        "owner_name",
        "owner_document",
        "city",
        "state",
        "main_crop",
        "car_code",
        "technical_lead",
        "notes",
        mode="before",
    )
    @classmethod
    def _vazio_e_nulo(cls, value: object) -> object:
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value

    @field_validator("owner_document")
    @classmethod
    def _documento(cls, value: str | None) -> str | None:
        return None if value is None else documentos.normalizar_cpf_cnpj(value)

    @field_validator("car_code")
    @classmethod
    def _car(cls, value: str | None) -> str | None:
        return None if value is None else documentos.normalizar_car(value)

    @field_validator("state")
    @classmethod
    def _uf(cls, value: str | None) -> str | None:
        return None if value is None else documentos.normalizar_uf(value)


class FarmCreate(FarmRegistry):
    name: Name
    center_lat: float = Field(ge=-90, le=90)
    center_lon: float = Field(ge=-180, le=180)
    base_lat: float | None = Field(default=None, ge=-90, le=90)
    base_lon: float | None = Field(default=None, ge=-180, le=180)
    timezone: str = "America/Sao_Paulo"
    area_ha: float | None = Field(default=None, gt=0)


class FarmUpdate(FarmRegistry):
    """Alteração de uma propriedade já cadastrada.

    Tudo opcional: o que não vier não é tocado. É o que permite corrigir só a
    coordenada de uma fazenda que foi cadastrada no lugar errado sem reenviar o
    resto do cadastro.
    """

    name: Name | None = None
    center_lat: float | None = Field(default=None, ge=-90, le=90)
    center_lon: float | None = Field(default=None, ge=-180, le=180)
    base_lat: float | None = Field(default=None, ge=-90, le=90)
    base_lon: float | None = Field(default=None, ge=-180, le=180)
    timezone: str | None = Field(default=None, max_length=64)
    area_ha: float | None = Field(default=None, gt=0)


class FarmOut(ApiModel):
    id: str
    name: str
    timezone: str
    center_lat: float
    center_lon: float
    base_lat: float | None
    base_lon: float | None
    area_ha: float | None
    owner_name: str | None = None
    owner_document: str | None = Field(
        default=None,
        description=(
            "CPF/CNPJ só com dígitos para quem tem farm:manage; mascarado "
            "(***.***.***-12) para os demais papéis."
        ),
    )
    owner_document_masked: bool = Field(
        default=False, description="Se owner_document veio mascarado nesta resposta."
    )
    city: str | None = None
    state: str | None = None
    main_crop: str | None = None
    car_code: str | None = None
    technical_lead: str | None = None
    notes: str | None = None
    fields: int = Field(description="Quantos talhões cadastrados.")


class FieldCreate(ApiModel):
    name: Name
    crop: Annotated[str, StringConstraints(min_length=2, max_length=64)]
    boundary: Polygon
    variety: str | None = None
    ai_model: str | None = Field(
        default=None,
        max_length=64,
        description=(
            "Versão do modelo de diagnóstico para este talhão, ex.: 'banana-foliar-cc'. "
            "Nulo: a recomendada da cultura. Ver GET /v1/fields/{id}/ai-models."
        ),
    )
    crop_stage: str | None = None
    planted_on: date | None = None
    row_spacing_m: float | None = Field(default=None, gt=0)
    row_azimuth_deg: float | None = Field(
        default=None,
        ge=0,
        lt=180,
        description="Direção das linhas, graus a partir do norte. 0 = N-S, 90 = L-O.",
    )
    plant_spacing_m: float | None = Field(
        default=None, gt=0, le=50, description="Espaçamento entre plantas na linha, em metros."
    )
    row_count: int | None = Field(default=None, ge=1, le=100_000)
    validation_rows: list[int] = Field(
        default_factory=list,
        max_length=500,
        description="Números das linhas (a partir de 1) usadas como fileiras de validação.",
    )
    notes: str | None = Field(default=None, max_length=4000)

    @field_validator("validation_rows")
    @classmethod
    def _fileiras(cls, value: list[int]) -> list[int]:
        return _fileiras_validas(value)


def _fileiras_validas(value: list[int] | None) -> list[int] | None:
    """Fileira é número de linha a partir de 1, sem repetição; devolve em ordem."""
    if value is None:
        return None
    if any(numero < 1 for numero in value):
        raise ValueError("Fileira de validação é o número da linha, a partir de 1.")
    if len(set(value)) != len(value):
        raise ValueError("Fileira de validação repetida.")
    return sorted(value)


class FieldUpdate(ApiModel):
    """Configuração agronômica do talhão. Só o que vier é alterado.

    O contorno tem rota própria (``PATCH /fields/{id}/boundary``), porque mexe em
    área, cerca virtual e leitura de terreno; e o modelo de IA também
    (``PUT /fields/{id}/ai-model``).
    """

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    name: Name | None = None
    variety: str | None = Field(default=None, max_length=120)
    crop_stage: str | None = Field(default=None, max_length=64)
    planted_on: date | None = None
    row_spacing_m: float | None = Field(default=None, gt=0, le=50)
    row_azimuth_deg: float | None = Field(default=None, ge=0, lt=180)
    plant_spacing_m: float | None = Field(default=None, gt=0, le=50)
    row_count: int | None = Field(default=None, ge=1, le=100_000)
    validation_rows: list[int] | None = Field(default=None, max_length=500)
    notes: str | None = Field(default=None, max_length=4000)

    @field_validator("validation_rows")
    @classmethod
    def _fileiras(cls, value: list[int] | None) -> list[int] | None:
        return _fileiras_validas(value)


class ReliefOut(ApiModel):
    """O relevo medido de uma área.

    Em graus, e não em porcentagem: o limite que importa — o ângulo de
    tombamento do rover — vem em graus no datasheet do fabricante, e converter
    na fronteira evita a classe de erro em que 30% vira 30°.
    """

    amostras: int
    altitude_min_m: float
    altitude_max_m: float
    desnivel_m: float
    declividade_media_deg: float
    declividade_maxima_deg: float
    azimute_da_encosta_deg: float | None = Field(
        default=None,
        description=(
            "Para onde o terreno cai, em graus do norte. Nulo em terreno plano. "
            "As passadas em curva de nível correm a 90° disto."
        ),
    )
    fonte: str = Field(description="Qual serviço de elevação respondeu.")
    azimute_em_curva_de_nivel_deg: float | None = Field(
        default=None,
        description="A direção de passada que corta a encosta em vez de subi-la.",
    )
    avisos: list[str] = Field(default_factory=list)


class TerrainObjectOut(ApiModel):
    """Uma coisa localizada dentro do talhão, em coordenadas do mapa."""

    kind: str = Field(
        description="mata, carreador, solo_exposto ou desconhecido. Palpite, não medição."
    )
    center: list[float] = Field(description="[lon, lat] do centro do agrupamento.")
    outline: list[list[float]] = Field(
        description=(
            "Retângulo [lon, lat] em volta do objeto. Grosseiro de propósito: a "
            "leitura é em blocos, e um contorno fino sugeriria precisão que não existe."
        )
    )
    area_ha: float
    traversable: bool = Field(
        description="Se o rover passa por cima (carreador, solo) ou tem que contornar."
    )
    confidence: float
    blocks: int


class TerrainOut(ApiModel):
    """O talhão repartido pela leitura de imagem: quanto opera e o que atrapalha.

    ``resolution_ok`` falso zera o resto. É deliberado: numa imagem em que a rua
    de plantio não se resolve, nada é lavoura para o classificador, e o número
    que sairia — "75% de obstáculo" num cafezal inteiro — encolheria a área
    operável pela metade sem ninguém desconfiar.
    """

    resolution_ok: bool
    description: str
    crop_fraction: float
    obstacle_fraction: float
    path_fraction: float
    operable_area_ha: float | None = Field(
        default=None,
        description=(
            "Lavoura mais caminho, aplicado à área do contorno. É o número que o "
            "planejamento deve usar no lugar da área bruta."
        ),
    )
    row_spacing_px: float | None = None
    cover_fractions: dict[str, float] = Field(default_factory=dict)
    objects: list[TerrainObjectOut] = Field(default_factory=list)
    heuristic: bool = Field(
        default=True,
        description=(
            "Sempre verdadeiro por enquanto: a classe de cada objeto é regra de cor "
            "e textura, não modelo treinado. Quem confirma é o agrônomo."
        ),
    )


class FieldOut(ApiModel):
    id: str
    farm_id: str
    name: str
    crop: str
    variety: str | None
    ai_model: str | None = Field(
        default=None, description="Versão escolhida para o talhão; nulo é a recomendada."
    )
    ai_model_in_use: str | None = Field(
        default=None,
        description="A versão que de fato atende a imagem de solo deste talhão; nulo sem modelo.",
    )
    crop_stage: str | None
    planted_on: date | None
    row_spacing_m: float | None
    row_azimuth_deg: float | None = None
    plant_spacing_m: float | None = None
    row_count: int | None = None
    validation_rows: list[int] = Field(default_factory=list)
    notes: str | None = None
    area_ha: float | None
    boundary: list[list[float]]
    terrain: TerrainOut | None = Field(
        default=None, description="Última leitura de imagem deste talhão, quando houver."
    )
    terrain_read_at: datetime | None = Field(
        default=None,
        description="Quando a leitura foi feita. Leitura velha descreve lavoura que já mudou.",
    )
    relief: ReliefOut | None = Field(
        default=None,
        description=(
            "O relevo medido deste talhão. Nulo quando nunca foi medido — e "
            "então o planejamento trata o talhão como plano, o que os avisos "
            "do plano declaram."
        ),
    )
    relief_read_at: datetime | None = None


class ZoneCreate(ApiModel):
    name: Name
    boundary: Polygon


class ZoneOut(ApiModel):
    id: str
    field_id: str
    name: str
    area_ha: float | None
    boundary: list[list[float]]


# ---------------------------------------------------------------------------
# Frota
# ---------------------------------------------------------------------------


class DeviceModelOut(ApiModel):
    id: str
    code: str
    kind: DeviceKind
    name: str
    manufacturer: str | None
    protocol_version: str
    capabilities: dict


class ProvisioningTokenCreate(ApiModel):
    device_model_code: str
    farm_id: str | None = None
    serial_number: str | None = Field(
        default=None,
        description="Amarra o convite a um número de série. Recomendado em produção.",
    )
    ttl_hours: int = Field(default=72, ge=1, le=720)


class ProvisioningTokenOut(ApiModel):
    """O token em claro aparece **uma única vez**, nesta resposta."""

    id: str
    token: str
    expires_at: datetime
    device_model_code: str
    serial_number: str | None


class DeviceProvisionRequest(ApiModel):
    """O que o robô envia no primeiro contato."""

    model_config = ALLOW_MODEL_PREFIX

    provisioning_token: str
    serial_number: Annotated[str, StringConstraints(min_length=3, max_length=64)]
    public_key: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")] = Field(
        description="Ed25519 bruta em hexadecimal, gerada dentro do robô."
    )
    name: str | None = None
    firmware_version: str | None = None
    hardware_version: str | None = None
    protocol_version: str = "1.0"


class DeviceProvisionResponse(ApiModel):
    """O que o robô guarda para o resto da vida."""

    device_id: str
    tenant_id: str
    key_id: str
    platform_public_key: str = Field(
        description="Usada pelo robô para verificar as missões que a nuvem assina."
    )
    ota_public_key: str = Field(
        description="Usada pelo robô para verificar os pacotes de atualização (OTA)."
    )
    protocol_version: str
    server_time: datetime


class DeviceOut(ApiModel):
    model_config = ALLOW_MODEL_PREFIX

    id: str
    serial_number: str
    name: str
    kind: DeviceKind
    status: DeviceStatus
    model_code: str
    farm_id: str | None
    firmware_version: str | None
    protocol_version: str | None
    connectivity: Connectivity
    battery_percent: float | None
    last_seen_at: datetime | None
    last_lat: float | None
    last_lon: float | None
    active_mission_id: str | None
    capabilities: dict
    fleet_state: str = Field(
        description=(
            "disponivel, em_missao, sincronizando, manutencao, offline, bloqueado ou "
            "erro — derivado do protocolo (contato, missão, /sync, falhas), nunca digitado."
        )
    )
    fleet_state_label: str
    fleet_state_reason: str
    hardware_version: str | None = None
    runtime_version: str | None = None
    edge_ai_version: str | None = None
    ai_model_key: str | None = None
    ai_model_version: str | None = None
    dnaty_version: str | None = None
    versions_reported_at: datetime | None = None
    temperature_c: float | None = None
    storage_total_bytes: int | None = None
    storage_free_bytes: int | None = None
    link_quality: float | None = None
    operating_hours: float | None = None
    active_faults: list[Any] = Field(default_factory=list)
    sync_pending: int = 0
    last_sync_at: datetime | None = None
    last_maintenance_at: datetime | None = None
    maintenance_note: str | None = None
    model_status: str = Field(
        default="sem_dado",
        description=(
            "conforme (o modelo informado é um dos designados), divergente (é outro "
            "do registry), fora_do_registry (não existe no registry) ou sem_dado."
        ),
    )
    designated_models: list[str] = Field(
        default_factory=list,
        description="Modelos que o registry designa a este robô, como 'chave@versão'.",
    )


class FleetDeviceOut(DeviceOut):
    """Um robô na visão de Operações: o mesmo retrato, com o cliente dono."""

    tenant_id: str
    tenant_name: str


class DeviceStatusUpdate(ApiModel):
    status: DeviceStatus
    reason: str | None = None
    maintenance_note: str | None = Field(
        default=None,
        max_length=500,
        description="O que está sendo feito, ao pôr em manutenção. Aparece na frota.",
    )


# ---------------------------------------------------------------------------
# Protocolo do dispositivo
# ---------------------------------------------------------------------------


class TelemetryIn(ApiModel):
    """Uma amostra. Os campos são todos opcionais salvo a sequência."""

    sequence_number: int = Field(ge=0)
    recorded_at: datetime | None = None
    mission_id: str | None = None
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)
    alt_m: float | None = None
    heading_deg: float | None = None
    speed_ms: float | None = None
    rtk_fix: RtkFix | None = None
    hdop: float | None = None
    battery_percent: float | None = Field(default=None, ge=0, le=100)
    battery_voltage_v: float | None = None
    battery_current_a: float | None = None
    temperature_c: float | None = None
    energy_state: str | None = None
    mission_state: str | None = None
    link_quality: float | None = None
    storage_total_bytes: int | None = Field(
        default=None, ge=0, description="Capacidade do armazenamento local do robô."
    )
    storage_free_bytes: int | None = Field(
        default=None, ge=0, description="Espaço livre no armazenamento local."
    )
    operating_hours: float | None = Field(
        default=None, ge=0, description="Horímetro do robô (horas de operação acumuladas)."
    )
    motors: dict = Field(default_factory=dict)
    sensors: dict = Field(default_factory=dict)
    health: dict | None = Field(
        default=None,
        description=(
            "Saúde padronizada do robô (Rover Runtime, Parte 7): cpu_percent, "
            "memory_percent, accelerator, disk_percent, cameras, sensors, network, sync, "
            "edge_ai, simulated. Campos desconhecidos são ignorados; ausente = não medido."
        ),
    )
    faults: list[Any] = Field(
        default_factory=list,
        description=(
            "Falhas ativas no instante da amostra. A amostra mais recente define o "
            "estado ERRO da frota; uma amostra com a lista vazia o encerra."
        ),
    )


class DeviceEventIn(ApiModel):
    sequence_number: int = Field(ge=0)
    type: Annotated[str, StringConstraints(min_length=2, max_length=64)]
    occurred_at: datetime | None = None
    severity: str = "info"
    mission_id: str | None = None
    payload: dict = Field(default_factory=dict)


class TelemetryBatch(ApiModel):
    sync_id: str | None = Field(
        default=None, description="Identificador do lote, para rastrear a sincronização offline."
    )
    samples: list[TelemetryIn] = Field(min_length=1)


class EventBatch(ApiModel):
    sync_id: str | None = None
    events: list[DeviceEventIn] = Field(min_length=1)


class SyncBatch(ApiModel):
    """Descarga de um robô que ficou offline."""

    sync_id: str
    samples: list[TelemetryIn] = Field(default_factory=list)
    events: list[DeviceEventIn] = Field(default_factory=list)
    remaining: int | None = Field(
        default=None,
        ge=0,
        description=(
            "Quantos registros ainda ficaram no robô depois deste lote. Maior que zero "
            "deixa o robô SINCRONIZANDO na frota; zero (ou ausente) encerra a descarga."
        ),
    )


class DeviceSessionIn(ApiModel):
    """O que o robô informa ao abrir a sessão: o software que está rodando.

    Brief, seção 22: o robô sabe exatamente o modelo em uso e o registra. Todos os
    campos são opcionais (um firmware antigo abre sessão sem corpo); um campo
    ausente não apaga o valor anterior.
    """

    model_config = ALLOW_MODEL_PREFIX

    firmware_version: str | None = Field(default=None, max_length=32)
    hardware_version: str | None = Field(default=None, max_length=32)
    runtime_version: str | None = Field(default=None, max_length=32)
    edge_ai_version: str | None = Field(default=None, max_length=32)
    model_key: str | None = Field(default=None, max_length=64)
    model_version: str | None = Field(default=None, max_length=32)
    dnaty_version: str | None = Field(default=None, max_length=32)


class IngestOut(ApiModel):
    accepted: int
    duplicated: int = Field(description="Já conhecidos. Reenvio é esperado, não é erro.")
    rejected: int
    errors: list[str] = Field(default_factory=list)


class RoverCameraIn(ApiModel):
    """A câmera lateral do rover no instante do quadro.

    Com ela, a imagem não é tratada como uma foto de folha: o serviço de
    inferência corta o quadro em recortes de 150 mm na escala física, sabe a
    altura de cada um e em que zona da planta ele está (pseudocaule, folhas
    baixas, saia, copa). Com ``side`` e ``x_m`` também, alimenta a fusão por
    planta do talhão.
    """

    camera_height_mm: float = Field(gt=0, le=3000, description="Altura da câmera no mastro.")
    distance_mm: float = Field(
        gt=50, le=5000, description="Distância até a planta: mediana da profundidade da OAK-D."
    )
    side: Literal["left", "right"] | None = Field(
        default=None, description="Lado do rover em que a câmera está."
    )
    x_m: float | None = Field(
        default=None, description="Posição do rover ao longo da rua (odometria), em metros."
    )
    camera_id: str | None = Field(default=None, max_length=64)


class ObservationIn(ApiModel):
    """Metadados de uma imagem. A imagem vai no campo ``file`` do multipart."""

    sequence_number: int | None = None
    mission_id: str | None = None
    field_id: str
    zone_id: str | None = None
    captured_at: datetime
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    alt_m: float | None = None
    heading_deg: float | None = None
    row_index: int | None = None
    model_input_ok: bool | None = None
    edge_summary: dict = Field(default_factory=dict)
    camera: RoverCameraIn | None = Field(
        default=None,
        description=(
            "Presente quando a imagem é um quadro inteiro de câmera lateral do rover, e "
            "não uma foto de folha. Ver RoverCameraIn."
        ),
    )


class ObservationOut(ApiModel):
    id: str
    field_id: str
    zone_id: str | None
    mission_id: str | None
    device_id: str | None = Field(
        default=None, description="Nulo quando a imagem veio de coleta, não de um robô da frota."
    )
    collection_id: str | None = None
    captured_at: datetime
    lat: float
    lon: float
    image_asset_id: str | None
    diagnosis_id: str | None = None
    diagnosis_status: DiagnosisStatus | None = None
    label: str | None = None
    confidence: float | None = None
    novelty_score: float | None = None
    severity: float | None = Field(
        default=None, description="Fração do quadro com lesão, quando medida."
    )
    signals: dict = Field(
        default_factory=dict,
        description=(
            "O que a IA disse além do rótulo (análise primária): veredito do portão "
            "de enquadramento, conjunto conformal e, num quadro do rover, os recortes "
            "por zona da planta, as plantas do talhão e a severidade da Sigatoka."
        ),
    )


class SignedCommandOut(ApiModel):
    """O envelope assinado que o robô verifica antes de agir."""

    payload: dict
    signature: str
    key_id: str
    algorithm: str


class MissionAck(ApiModel):
    """Confirmação de recebimento pelo robô."""

    mission_id: str
    accepted: bool
    reason: str | None = Field(
        default=None, description="Por que recusou. Obrigatório quando accepted=false."
    )


class SegmentComplete(ApiModel):
    segment_index: int = Field(ge=0)
    lat: float | None = None
    lon: float | None = None
    battery_percent: float | None = None


class MissionPause(ApiModel):
    reason: str = Field(max_length=120)
    lat: float | None = None
    lon: float | None = None
    battery_percent: float | None = None


# ---------------------------------------------------------------------------
# Missões
# ---------------------------------------------------------------------------


class MissionCreate(ApiModel):
    kind: MissionKind
    field_id: str
    device_id: str
    zone_id: str | None = None
    target_polygon: Polygon | None = Field(
        default=None, description="Sem polígono, a missão cobre o talhão inteiro."
    )
    plan: dict = Field(default_factory=dict)
    # Só para pulverização:
    product_id: str | None = None
    product_batch_id: str | None = None
    tank_id: str | None = None
    authorized_rate_l_ha: float | None = Field(default=None, gt=0)
    authorized_quantity_l: float | None = Field(default=None, gt=0)
    decision_id: str | None = None


class MissionSegmentOut(ApiModel):
    index: int
    state: str
    path: list[list[float]]
    estimated_energy_percent: float | None


class MissionOut(ApiModel):
    id: str
    kind: MissionKind
    state: MissionState
    farm_id: str
    field_id: str
    zone_id: str | None
    device_id: str
    target_polygon: list[list[float]]
    plan: dict
    product_id: str | None
    tank_id: str | None
    authorized_rate_l_ha: float | None
    authorized_quantity_l: float | None
    created_by: str | None
    approved_by: str | None
    approved_at: datetime | None = None
    product_batch_id: str | None = None
    decision_id: str | None = None
    dispatched_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    abort_reason: str | None = None
    authorized_at: datetime | None
    expires_at: datetime | None
    safety_status: SafetyVerdict | None
    safety_reason: str | None
    energy_policy: dict
    offline_policy: dict
    segments_total: int
    segments_done: int
    created_at: datetime


class MissionApproval(ApiModel):
    """Assinatura do agrônomo. Sem isto nenhuma pulverização é autorizada."""

    confirm: bool = Field(
        description="Precisa ser verdadeiro. Existe para evitar clique acidental."
    )
    notes: str | None = None


class AbortRequest(ApiModel):
    reason: str = Field(min_length=3, max_length=500)


class SafetyCheckOut(ApiModel):
    code: str
    passed: bool
    detail: str


class SafetyEvaluationOut(ApiModel):
    id: str
    subject_type: str
    subject_id: str
    verdict: SafetyVerdict
    blocked_code: str | None
    blocked_reason: str | None
    checks: list[SafetyCheckOut]
    engine_version: str
    created_at: datetime


# ---------------------------------------------------------------------------
# Percepção
# ---------------------------------------------------------------------------


class DetectionOut(ApiModel):
    model_config = ALLOW_MODEL_PREFIX

    id: str
    source: str
    analyzer: str
    model_key: str | None
    label: str | None
    confidence: float | None
    novelty_score: float | None
    abstained: bool
    probabilities: dict
    latency_ms: float | None
    error: str | None
    signals: dict = Field(
        default_factory=dict,
        description="Portão de enquadramento, conjunto conformal e resumo do quadro do rover.",
    )


class DiagnosisOut(ApiModel):
    id: str
    observation_id: str
    field_id: str
    zone_id: str | None
    status: DiagnosisStatus
    agreement: str
    label: str | None
    effective_label: str | None
    confidence: float | None
    novelty_score: float | None
    severity: float | None = Field(
        default=None,
        description=(
            "Fração do quadro com lesão, em [0, 1]. Aproxima a severidade da folha "
            "quando ela preenche o quadro. Informação para o agrônomo: não entra na "
            "regra de decisão."
        ),
    )
    rationale: str | None
    pipeline_version: str
    reviewed_by: str | None
    reviewed_at: datetime | None
    reviewed_label: str | None
    created_at: datetime
    detections: list[DetectionOut] = Field(default_factory=list)
    priority_score: float | None = Field(
        default=None, description="Com order=valor na fila: quanto este item ensina."
    )
    priority_reasons: list[str] = Field(
        default_factory=list,
        description="Com order=valor: por que o item está onde está, ex.: 'classe rara: Cordana'.",
    )


class DiagnosisReview(ApiModel):
    """O veredito do agrônomo."""

    label: Annotated[str, StringConstraints(pattern=r"^[A-Za-z][A-Za-z0-9_]{0,63}$")] = Field(
        description=(
            "A classe correta. Pode ser um nome que ainda não existe no catálogo "
            "do modelo — é assim que uma doença nova entra no dataset próprio."
        ),
        examples=["Gray_Leaf_Spot", "Cigarrinha"],
    )
    confirmed: bool = Field(
        default=True,
        description=(
            "Verdadeiro registra o diagnóstico do agrônomo — concorde ou não com a IA; "
            "corrigir o rótulo é confirmar com o rótulo certo. Falso descarta a imagem "
            "como sem condição de diagnóstico."
        ),
    )
    notes: str | None = None


class DecisionOut(ApiModel):
    id: str
    diagnosis_id: str | None
    field_id: str
    zone_id: str | None
    outcome: DecisionOutcome
    reason_code: str
    rationale: str
    rule_version: str
    recommended_product_id: str | None
    recommended_rate_l_ha: float | None
    affected_ratio: float | None
    sample_size: int | None
    mission_id: str | None
    inputs: dict
    created_at: datetime


# ---------------------------------------------------------------------------
# Insumos e aplicação
# ---------------------------------------------------------------------------


class ProductCreate(ApiModel):
    name: Name
    manufacturer: str | None = None
    active_ingredient: str | None = None
    registration_number: str | None = None
    allowed_crops: list[str] = Field(default_factory=list)
    authorized_targets: list[str] = Field(default_factory=list)
    default_rate_l_ha: float | None = Field(default=None, gt=0)
    min_rate_l_ha: float | None = Field(default=None, gt=0)
    max_rate_l_ha: float | None = Field(default=None, gt=0)
    reentry_interval_h: float | None = Field(default=None, ge=0)
    preharvest_interval_days: int | None = Field(default=None, ge=0)
    max_wind_ms: float | None = Field(default=None, gt=0)


class ProductOut(ProductCreate):
    id: str
    status: str


class BatchCreate(ApiModel):
    code: Annotated[str, StringConstraints(min_length=1, max_length=64)]
    expires_on: date | None = None
    quantity_l: float | None = Field(default=None, gt=0)


class BatchOut(ApiModel):
    id: str
    product_id: str
    code: str
    expires_on: date | None
    quantity_l: float | None


class TankCreate(ApiModel):
    device_id: str
    index: int = Field(ge=0)
    capacity_l: float = Field(gt=0)
    label: str | None = None


class TankLoad(ApiModel):
    """Carga de um tanque. É o registro que o safety engine confere."""

    product_id: str
    batch_id: str
    volume_l: float = Field(gt=0)


class TankOut(ApiModel):
    id: str
    device_id: str
    index: int
    label: str | None
    capacity_l: float
    current_level_l: float
    status: str
    loaded_product_id: str | None
    loaded_batch_id: str | None
    loaded_at: datetime | None


class ApplicationStart(ApiModel):
    """Reportado pelo drone quando abre o bico."""

    mission_id: str
    started_at: datetime
    tank_id: str | None = None


class ApplicationStop(ApiModel):
    stopped_at: datetime
    amount_used_l: float = Field(ge=0)
    area_ha: float | None = Field(default=None, ge=0)
    track: list[list[float]] = Field(
        default_factory=list, description="[[lon, lat, vazão], ...] — o mapa de aplicação."
    )
    stop_reason: str | None = None


class ApplicationOut(ApiModel):
    id: str
    mission_id: str
    device_id: str
    field_id: str
    zone_id: str | None
    product_id: str | None
    state: ApplicationState
    started_at: datetime
    stopped_at: datetime | None
    amount_used_l: float | None
    area_ha: float | None
    mean_rate_l_ha: float | None
    outside_polygon_points: int
    verified: bool


class VerificationOut(ApiModel):
    model_config = ALLOW_MODEL_PREFIX

    id: str
    application_id: str
    field_id: str
    zone_id: str | None
    scheduled_for: datetime | None
    before_ratio: float | None
    after_ratio: float | None
    before_sample: int | None
    after_sample: int | None
    effectiveness: float | None
    conclusion: VerificationConclusion
    notes: str | None


# ---------------------------------------------------------------------------
# Gêmeo digital, auditoria e eventos
# ---------------------------------------------------------------------------


class ClassCountOut(ApiModel):
    label: str
    count: int
    ratio: float


class FieldSnapshotOut(ApiModel):
    field_id: str
    field_name: str
    crop: str
    since: datetime
    until: datetime
    observations: int
    diagnosed: int
    needs_review: int
    classes: list[ClassCountOut]


class TimePointOut(ApiModel):
    day: date
    total: int
    counts: dict[str, int]


class AnomalyOut(ApiModel):
    field_id: str
    zone_id: str | None
    label: str
    baseline_ratio: float
    current_ratio: float
    baseline_sample: int
    current_sample: int
    detail: str


# --- cópia 3D -------------------------------------------------------------------

MAX_PLANTS_PER_SCAN = 30_000
"""Plantas por passada. Uma rua de 300 m com seis linhas à vista tem ~9 000."""


class RowScanIn(ApiModel):
    """Metadados de uma passada. A nuvem de pontos, quando houver, vai no ``file``.

    Posições em metros no plano local com origem em ``origin_lon``/``origin_lat``:
    x para leste, y para norte, z para cima — o mesmo plano da nuvem de pontos.
    """

    sequence_number: int = Field(description="Sequência do robô; reenviar a mesma é seguro.")
    mission_id: str | None = None
    field_id: str
    segment_index: int | None = None
    row_index: int | None = None
    started_at: datetime | None = None
    captured_at: datetime = Field(description="Fim da passada.")
    sensor: str = Field(default="lidar", pattern="^(lidar|stereo|camera)$")
    origin_lat: float = Field(ge=-90, le=90)
    origin_lon: float = Field(ge=-180, le=180)
    origin_alt_m: float | None = None
    path: list[list[float]] = Field(
        min_length=2, max_length=5_000, description="Eixo percorrido, [[lon, lat], ...]."
    )
    reach_m: float = Field(
        gt=0, le=10, description="Alcance lateral do sensor a partir do eixo, em metros."
    )
    plants: list[list[float]] = Field(
        default_factory=list,
        max_length=MAX_PLANTS_PER_SCAN,
        description=(
            "Uma entrada por planta: [x, y, altura_m, copa_m] ou [x, y, altura_m, "
            "copa_m, verde], com verde em [0, 1] (índice de excesso de verde do RGB "
            "da planta)."
        ),
    )

    @field_validator("path")
    @classmethod
    def _check_path(cls, value: list[list[float]]) -> list[list[float]]:
        for point in value:
            if len(point) < 2 or not (-180 <= point[0] <= 180 and -90 <= point[1] <= 90):
                raise ValueError(f"Ponto do eixo inválido: {point!r}. Esperado [lon, lat].")
        return value

    @field_validator("plants")
    @classmethod
    def _check_plants(cls, value: list[list[float]]) -> list[list[float]]:
        for plant in value:
            if len(plant) not in (4, 5) or not all(math.isfinite(item) for item in plant):
                raise ValueError(
                    f"Planta inválida: {plant!r}. Esperado [x, y, altura, copa(, verde)]."
                )
            x, y, height, canopy = plant[:4]
            if abs(x) > 2_000 or abs(y) > 2_000:
                raise ValueError(f"Planta a mais de 2 km da origem da passada: {plant!r}.")
            if not 0 <= height <= 8 or not 0 <= canopy <= 6:
                raise ValueError(f"Altura ou copa fora do plausível: {plant!r}.")
            if len(plant) == 5 and not 0 <= plant[4] <= 1:
                raise ValueError(f"Índice de verde fora de [0, 1]: {plant!r}.")
        return value


class RowScanOut(ApiModel):
    id: str
    field_id: str
    mission_id: str | None
    device_id: str
    sequence_number: int
    segment_index: int | None
    row_index: int | None
    captured_at: datetime
    sensor: str
    reach_m: float
    length_m: float
    plant_count: int
    mean_height_m: float | None
    max_height_m: float | None
    point_count: int | None
    has_pointcloud: bool


class SceneZoneOut(ApiModel):
    id: str
    name: str
    boundary: list[list[float]]


class SceneScanOut(ApiModel):
    """Uma rua na cópia: onde o rover passou, quando, e o que mediu."""

    id: str
    captured_at: datetime
    device_id: str
    device_name: str | None
    mission_id: str | None
    segment_index: int | None
    row_index: int | None
    sensor: str
    reach_m: float
    length_m: float
    origin: list[float] = Field(description="Origem da passada no plano do talhão, [x, y].")
    path: list[list[float]]
    plant_count: int
    visible_plants: int = Field(
        description=(
            "Quantas plantas desta passada estão na cópia — as outras foram "
            "cobertas por uma passada mais nova."
        )
    )
    mean_height_m: float | None
    max_height_m: float | None
    point_count: int | None
    has_pointcloud: bool
    markers: dict[str, int] = Field(description="Observações nesta rua, por categoria.")


class ScenePlantsOut(ApiModel):
    """Plantas da cópia em colunas. Cada índice é uma planta."""

    x: list[float]
    y: list[float]
    height: list[float]
    canopy: list[float]
    greenness: list[float | None]
    scan: list[int] = Field(description="Índice em ``scans`` da passada que mediu a planta.")


class SceneMarkerOut(ApiModel):
    """Uma foto diagnosticada, presa à planta fotografada."""

    observation_id: str
    diagnosis_id: str | None
    x: float
    y: float
    z: float
    label: str | None
    category: str = Field(description="healthy, disease, pest, review ou other.")
    status: DiagnosisStatus | None
    confidence: float | None
    novelty_score: float | None
    severity: float | None
    captured_at: datetime
    plant: int | None = Field(
        description="Índice da planta em ``plants``, quando há uma a até 60 cm."
    )
    scan: int | None


class SceneDeviceOut(ApiModel):
    id: str
    name: str
    kind: DeviceKind
    x: float
    y: float
    battery_percent: float | None
    last_seen_at: datetime | None
    active_mission_id: str | None


class SceneMissionOut(ApiModel):
    """Uma varredura em andamento: as ruas que faltam aparecem na cópia."""

    mission_id: str
    state: MissionState
    segments: int
    done: int
    pending: list[list[list[float]]]


class ScenePassOut(ApiModel):
    day: date
    scans: int


class FieldSceneOut(ApiModel):
    """A cópia 3D do talhão.

    Coordenadas em metros no plano local do talhão: origem no centro do limite,
    x para leste, y para norte, z para cima.
    """

    field_id: str
    field_name: str
    crop: str
    crop_stage: str | None
    row_azimuth_deg: float | None
    row_spacing_m: float | None
    origin_lon: float
    origin_lat: float
    at: datetime
    since: datetime
    live: bool
    boundary: list[list[float]]
    zones: list[SceneZoneOut]
    field_area_m2: float
    scanned_area_m2: float
    coverage_ratio: float
    scans: list[SceneScanOut]
    plants: ScenePlantsOut
    markers: list[SceneMarkerOut]
    counts: dict[str, int]
    devices: list[SceneDeviceOut]
    missions: list[SceneMissionOut]
    passes: list[ScenePassOut]


class AuditOut(ApiModel):
    model_config = ALLOW_MODEL_PREFIX

    id: str
    at: datetime
    actor_type: str
    actor_id: str | None
    actor_label: str | None
    action: str
    subject_type: str
    subject_id: str
    old_state: str | None
    new_state: str | None
    reason: str | None
    rule_version: str | None
    model_version: str | None
    payload: dict
    tenant_id: str | None = None
    support_session_id: str | None = Field(
        default=None,
        description="Ação da equipe da ValTexa numa sessão de suporte ('entrar como cliente').",
    )


class OutboxEventOut(ApiModel):
    id: str
    name: str
    subject_type: str | None
    subject_id: str | None
    payload: dict
    created_at: datetime
    delivered_at: datetime | None
    attempts: int
    last_error: str | None


class HealthResponse(ApiModel):
    status: str
    environment: str
    protocol_version: str
    database: str
    inference: str
    pending_events: int
    warnings: list[str] = Field(
        default_factory=list, description="O que impede este processo de ser produção."
    )


class UserUpdate(ApiModel):
    role: Role


# ---------------------------------------------------------------------------
# Console
# ---------------------------------------------------------------------------


class TelemetryOut(ApiModel):
    sequence_number: int
    recorded_at: datetime
    received_at: datetime
    mission_id: str | None
    lat: float | None
    lon: float | None
    alt_m: float | None
    heading_deg: float | None
    speed_ms: float | None
    rtk_fix: str
    battery_percent: float | None
    battery_voltage_v: float | None
    temperature_c: float | None
    energy_state: str
    mission_state: str | None
    link_quality: float | None
    sensors: dict
    faults: list[Any]


class TelemetryRollupOut(ApiModel):
    bucket_start: datetime
    bucket_seconds: int
    samples: int
    battery_min: float | None
    battery_avg: float | None
    battery_max: float | None
    speed_avg_ms: float | None
    link_quality_avg: float | None
    rtk_fixed_ratio: float | None
    last_lat: float | None
    last_lon: float | None


class DeviceEventOut(ApiModel):
    id: str
    device_id: str
    mission_id: str | None
    type: str
    severity: str
    sequence_number: int
    occurred_at: datetime
    received_at: datetime
    payload: dict


class MissionHistoryOut(ApiModel):
    at: datetime
    action: str
    old_state: str | None
    new_state: str | None
    reason: str | None
    actor_type: str
    actor: str | None


class CheckpointOut(ApiModel):
    created_at: datetime
    last_completed_segment: int
    remaining_segments: int
    battery_percent: float | None
    reason: str | None
    lat: float | None
    lon: float | None


class AlertOut(ApiModel):
    """Um alerta derivado do estado do sistema. Some quando a causa é resolvida."""

    id: str
    kind: str
    severity: str = Field(description="'critical', 'warning' ou 'info'.")
    title: str
    detail: str
    subject_type: str | None
    subject_id: str | None
    at: datetime


class DeviceSummary(ApiModel):
    total: int
    active: int
    online: int
    offline: int
    low_battery: int
    by_kind: dict[str, int]


class ApplicationSummary(ApiModel):
    count: int
    liters: float
    area_ha: float


class MissionBrief(ApiModel):
    id: str
    kind: MissionKind
    state: MissionState
    device_id: str
    device_name: str | None
    field_id: str
    field_name: str | None
    created_at: datetime
    segments_total: int
    segments_done: int


class SyncStatusOut(ApiModel):
    device_id: str
    name: str
    serial_number: str
    online: bool
    last_seen_at: str | None
    last_sync_at: str | None
    last_record_received_at: str | None
    queue_pending: int | None = Field(description="Itens na fila do robô (último contato).")
    queue_oldest_s: float | None
    uploads_incomplete: int = Field(description="Arquivos que começaram a subir e não fecharam.")
    open_alerts: int


class EdgeModelUseOut(ApiModel):
    model_config = ALLOW_MODEL_PREFIX

    model_key: str | None
    model_version: str | None
    results_24h: int


class DashboardAiOut(ApiModel):
    cloud_service: str = Field(description="ok, fora, simulado ou desligado.")
    cloud_inferences_24h: int
    cloud_errors_24h: int
    edge_results_24h: int
    edge_models: list[EdgeModelUseOut]


class DashboardOverviewOut(ApiModel):
    """Os números da seção 45 que vão além da frota e da fila (Parte 8)."""

    farms: int
    fields: int
    hectares: float
    occurrences_7d: int = Field(description="Resultados da Edge AI que são evento, 7 dias.")
    occurrences_by_category_7d: dict[str, int]
    scouts_completed_30d: int
    hectares_scouted_30d: float
    sync: list[SyncStatusOut]
    fleet_health: dict[str, int] = Field(description="ok, com_alerta, offline, inativo.")
    ai_health: DashboardAiOut


class DashboardOut(ApiModel):
    generated_at: datetime
    devices: DeviceSummary
    missions_by_state: dict[str, int]
    review_queue: int
    observations_7d: int
    labels_7d: dict[str, int]
    applications_30d: ApplicationSummary
    verifications_pending: int
    alert_counts: dict[str, int]
    alerts: list[AlertOut]
    recent_missions: list[MissionBrief]
    overview: DashboardOverviewOut | None = None


# ---------------------------------------------------------------------------
# Coletas
# ---------------------------------------------------------------------------


class CollectionCreate(ApiModel):
    """O formulário "Importar Coleta" do painel administrativo."""

    field_id: str
    collected_on: date = Field(description="Data do voo/percurso, não a do upload.")
    source: CollectionSource = CollectionSource.DRONE_THIRD_PARTY
    kind: CollectionKind = CollectionKind.AERIAL_IMAGE
    operator_name: str | None = Field(
        default=None, max_length=160, description="Empresa ou piloto que fez o voo."
    )
    notes: str | None = Field(default=None, max_length=2000)


class CollectionFileDeclare(ApiModel):
    """Um arquivo que virá. Declarado antes de qualquer byte."""

    filename: Annotated[str, StringConstraints(min_length=1, max_length=255)]
    size_bytes: int = Field(gt=0, description="Sem teto artificial: o limite é o do storage.")
    content_type: str | None = None
    sha256: str | None = Field(default=None, min_length=64, max_length=64)
    captured_at: datetime | None = None
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)
    alt_m: float | None = None


class CollectionFilesDeclare(ApiModel):
    files: list[CollectionFileDeclare] = Field(min_length=1)


class CollectionFileOut(ApiModel):
    id: str
    filename: str
    content_type: str
    size_bytes: int
    received_bytes: int
    state: CollectionFileState
    sha256: str | None = None
    error: str | None = None
    captured_at: datetime | None = None
    lat: float | None = None
    lon: float | None = None
    asset_id: str | None = None
    observation_id: str | None = None
    diagnosis_id: str | None = None
    label: str | None = None
    reviewed_label: str | None = None
    confidence: float | None = None


class CollectionProgress(ApiModel):
    """O que a barra de progresso do painel mostra."""

    files: int
    bytes_total: int
    bytes_received: int
    stored: int
    processed: int
    analyzed: int
    needs_review: int
    no_model: int
    failed: int
    upload_percent: float
    processing_percent: float


class CollectionOut(ApiModel):
    model_config = ALLOW_MODEL_PREFIX

    id: str
    code: str
    tenant_id: str
    farm_id: str
    farm_name: str | None = None
    field_id: str
    field_name: str | None = None
    crop: str | None = None
    collected_on: date
    source: CollectionSource
    kind: CollectionKind
    platform: CapturePlatform
    state: CollectionState
    operator_name: str | None = None
    notes: str | None = None
    model_key: str | None = Field(
        default=None, description="Modelo que atende a coleta. Nulo: nenhum treinado atende."
    )
    no_model_reason: str | None = Field(
        default=None,
        description=(
            "Por que nenhum modelo atende. Não é erro: a imagem fica guardada e "
            "vai para a fila do agrônomo."
        ),
    )
    progress: CollectionProgress
    created_at: datetime
    upload_completed_at: datetime | None = None
    processing_finished_at: datetime | None = None
    released_at: datetime | None = None


class ChunkAccepted(ApiModel):
    """Resposta de um pedaço aceito. ``received_bytes`` é de onde continuar."""

    file_id: str
    received_bytes: int
    size_bytes: int
    state: CollectionFileState
    complete: bool


class JobOut(ApiModel):
    id: str
    kind: str
    state: str
    subject_type: str
    subject_id: str
    attempts: int
    max_attempts: int
    progress_done: int
    progress_total: int
    last_error: str | None = None
    locked_by: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None


# ---------------------------------------------------------------------------
# Dataset proprietário
# ---------------------------------------------------------------------------


class DatasetOut(ApiModel):
    id: str
    key: str
    name: str
    crop: str
    platform: CapturePlatform
    samples: int
    candidates: int
    disagreements: int
    sem_modelo: int = Field(
        description="Amostras em que a máquina não opinou — o dataset de um modelo que não existe."
    )
    labels: dict[str, int]
    versions: int


class DatasetSampleOut(ApiModel):
    id: str
    dataset_id: str
    tenant_id: str
    asset_id: str
    label: str
    machine_label: str | None = None
    machine_confidence: float | None = None
    disagreed: bool
    reviewer_label: str | None = None
    reviewed_at: datetime | None = None
    state: DatasetSampleState
    collection_id: str | None = None


class DatasetVersionCreate(ApiModel):
    version: Annotated[str, StringConstraints(min_length=1, max_length=32)]
    notes: str | None = Field(default=None, max_length=2000)


class DatasetVersionOut(ApiModel):
    id: str
    dataset_id: str
    version: str
    sample_count: int
    label_counts: dict[str, int]
    notes: str | None = None
    frozen_at: datetime | None = None


class ModelVersionOut(ApiModel):
    model_config = ALLOW_MODEL_PREFIX

    id: str
    model_key: str
    version: str
    name: str | None = None
    state: ModelVersionState
    state_label: str = ""
    platform: CapturePlatform
    crop: str | None = None
    crops: list[str] = Field(default_factory=list)
    problem: str | None = None
    architecture: str | None = None
    dataset_version_id: str | None = None
    dataset_ref: str | None = None
    trained_at: datetime | None = None
    metrics: dict[str, Any]
    size_bytes: int | None = None
    flops: int | None = None
    latency_ms: float | None = None
    memory_mb: float | None = None
    target_hardware: str | None = None
    original_artifact_uri: str | None = None
    original_artifact_sha256: str | None = None
    optimized_artifact_uri: str | None = None
    optimized_artifact_sha256: str | None = None
    optimized_size_bytes: int | None = None
    dnaty_version: str | None = None
    variant: str = "padrão"
    recommended: bool = True
    license: str | None = None
    caveat: str | None = None
    release_scope: ReleaseScope = ReleaseScope.TODOS
    notes: str | None = None
    registered_by: str | None = None
    approved_by: str | None = None
    approved_at: datetime | None = None
    promoted_at: datetime | None = Field(
        default=None, description="Data de publicação (entrada em PRODUÇÃO)."
    )
    retired_at: datetime | None = None
    next_states: list[ModelVersionState] = Field(
        default_factory=list, description="Para onde esta versão pode ir daqui."
    )


_SHA256 = r"^[0-9a-f]{64}$"


class ModelVersionCreate(ApiModel):
    """Registro de uma versão nova. Entra em TREINAMENTO, com quem registrou."""

    model_config = ALLOW_MODEL_PREFIX

    model_key: Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9-]{1,63}$")]
    version: Annotated[str, StringConstraints(min_length=1, max_length=32)]
    name: str | None = Field(default=None, max_length=160)
    platform: CapturePlatform
    crops: list[Annotated[str, StringConstraints(min_length=1, max_length=64)]] = Field(
        min_length=1
    )
    problem: str | None = Field(default=None, max_length=160)
    architecture: str | None = Field(default=None, max_length=120)
    dataset_version_id: str | None = None
    dataset_ref: str | None = Field(default=None, max_length=255)
    trained_at: datetime | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)
    size_bytes: int | None = Field(default=None, ge=0)
    flops: int | None = Field(default=None, ge=0)
    latency_ms: float | None = Field(default=None, ge=0)
    memory_mb: float | None = Field(default=None, ge=0)
    target_hardware: str | None = Field(default=None, max_length=120)
    original_artifact_uri: str | None = Field(default=None, max_length=512)
    original_artifact_sha256: str | None = Field(default=None, pattern=_SHA256)
    optimized_artifact_uri: str | None = Field(default=None, max_length=512)
    optimized_artifact_sha256: str | None = Field(default=None, pattern=_SHA256)
    optimized_size_bytes: int | None = Field(default=None, ge=0)
    dnaty_version: str | None = Field(default=None, max_length=32)
    variant: str = Field(default="padrão", max_length=32)
    recommended: bool = True
    license: str | None = Field(default=None, max_length=255)
    caveat: str | None = None
    release_scope: ReleaseScope = ReleaseScope.TODOS
    notes: str | None = None


class ModelVersionUpdate(ApiModel):
    """Correção de uma versão. Métricas e artefatos só até a aprovação."""

    model_config = ALLOW_MODEL_PREFIX

    name: str | None = Field(default=None, max_length=160)
    crops: list[Annotated[str, StringConstraints(min_length=1, max_length=64)]] | None = None
    problem: str | None = Field(default=None, max_length=160)
    architecture: str | None = Field(default=None, max_length=120)
    dataset_ref: str | None = Field(default=None, max_length=255)
    trained_at: datetime | None = None
    metrics: dict[str, Any] | None = None
    size_bytes: int | None = Field(default=None, ge=0)
    flops: int | None = Field(default=None, ge=0)
    latency_ms: float | None = Field(default=None, ge=0)
    memory_mb: float | None = Field(default=None, ge=0)
    target_hardware: str | None = Field(default=None, max_length=120)
    original_artifact_uri: str | None = Field(default=None, max_length=512)
    original_artifact_sha256: str | None = Field(default=None, pattern=_SHA256)
    optimized_artifact_uri: str | None = Field(default=None, max_length=512)
    optimized_artifact_sha256: str | None = Field(default=None, pattern=_SHA256)
    optimized_size_bytes: int | None = Field(default=None, ge=0)
    dnaty_version: str | None = Field(default=None, max_length=32)
    license: str | None = Field(default=None, max_length=255)
    caveat: str | None = None
    release_scope: ReleaseScope | None = None
    notes: str | None = None


class OptimizationArtifactIn(ApiModel):
    """Um lado do relatório: onde o artefato vive e o benchmark dele."""

    artifact_uri: str | None = Field(default=None, max_length=512)
    benchmark: dict[str, Any]


class ModelOptimizationIn(ApiModel):
    """O relatório de ``ia/training/dnaty_pipeline.py`` (os campos que o registry usa).

    O veredito do relatório é ignorado: o registry recalcula com ``criterio``
    (ou o padrão) a partir dos números.
    """

    tool: str = Field(max_length=64)
    tool_version: str | None = Field(default=None, max_length=32)
    dnaty_version: str | None = Field(default=None, max_length=32)
    parametros: dict[str, Any] = Field(default_factory=dict)
    criterio: dict[str, Any] | None = None
    original: OptimizationArtifactIn
    otimizado: OptimizationArtifactIn


class ModelOptimizationOut(ApiModel):
    id: str
    model_version_id: str
    created_at: datetime
    tool: str
    tool_version: str | None
    dnaty_version: str | None
    parameters: dict[str, Any]
    original_sha256: str
    original_benchmark: dict[str, Any]
    optimized_artifact_uri: str
    optimized_sha256: str
    optimized_size_bytes: int | None
    optimized_benchmark: dict[str, Any]
    criterion: dict[str, Any]
    comparison: dict[str, Any]
    accepted: bool
    reasons: list[str]
    license_note: str | None
    applied: bool = Field(description="Se é a rodada que deu o otimizado atual da versão.")


class ModelTransitionIn(ApiModel):
    to: ModelVersionState
    reason: str | None = Field(default=None, max_length=1000)


class ModelTransitionOut(ApiModel):
    """Uma linha do histórico de uma versão (vem da auditoria)."""

    at: datetime
    actor_label: str | None
    action: str
    from_state: str | None
    to_state: str | None
    reason: str | None


class ModelVersionDetailOut(ModelVersionOut):
    history: list[ModelTransitionOut] = Field(default_factory=list)
    released_to: list[str] = Field(
        default_factory=list, description="Clientes com liberação ativa desta linha de modelo."
    )


class ModelReleaseIn(ApiModel):
    model_config = ALLOW_MODEL_PREFIX

    tenant_id: str
    model_key: str = Field(max_length=64)
    reason: str | None = Field(default=None, max_length=1000)


class ModelReleaseOut(ApiModel):
    model_config = ALLOW_MODEL_PREFIX

    id: str
    tenant_id: str
    tenant_name: str
    model_key: str
    reason: str | None
    released_by_label: str | None
    created_at: datetime
    revoked_at: datetime | None


class DesignatedModelOut(ApiModel):
    """O que o robô deve rodar num talhão. Só versão em PRODUÇÃO do registry."""

    model_config = ALLOW_MODEL_PREFIX

    field_id: str
    field_name: str
    crop: str
    model_key: str | None
    version: str | None
    state: ModelVersionState | None
    artifact_uri: str | None = Field(
        description="Otimizado quando houver; senão o original. Nulo: o registry ainda não tem."
    )
    artifact_sha256: str | None = Field(
        description="O robô confere este hash antes de carregar. Nulo = não carregue."
    )
    artifact_kind: str | None = Field(description="otimizado, original ou nulo.")
    dnaty_version: str | None
    target_hardware: str | None
    reason: str | None = Field(description="Por que não há modelo para o talhão, quando não há.")


class AiHealthModelOut(ApiModel):
    """Inferências de um modelo, medidas nas detecções gravadas."""

    model_config = ALLOW_MODEL_PREFIX

    model_key: str | None
    model_version: str | None
    simulated: bool = Field(description="Saída do analisador simulado, não de modelo real.")
    inferences: int
    errors: int
    error_rate: float | None
    abstentions: int
    latency_ms_avg: float | None
    latency_ms_p95: float | None
    labels: dict[str, int]
    last_at: datetime | None


class AiHealthOut(ApiModel):
    """Saúde da IA (brief, seção 34). O que não tem dado vem em ``no_data``, nunca inventado."""

    window_days: int
    active_models: list[ModelVersionOut]
    models: list[AiHealthModelOut]
    rovers_reporting: int
    rovers_divergent: int
    rovers_outside_registry: int
    rovers_without_data: int
    outdated_in_use: list[str] = Field(
        description="Versões descontinuadas que algum robô ainda diz rodar ('chave@versão')."
    )
    no_data: dict[str, str] = Field(
        description="Indicador → por que não há dado (drift, incidentes, FPS...)."
    )


class CatalogModelOut(ApiModel):
    """Uma entrada do catálogo de VALTEXA-B, como a plataforma a conhece."""

    model_config = ALLOW_MODEL_PREFIX

    key: str
    crops: list[str]
    platform: CapturePlatform
    trained: bool = Field(description="Falso: existe o nome, não existem os pesos.")
    caveat: str | None = None


# ---------------------------------------------------------------------------
# Planejamento de cobertura
# ---------------------------------------------------------------------------


class PlanRequest(ApiModel):
    """O que o painel pergunta ao planejar um talhão."""

    device_model_code: str = Field(
        default="ROVER_V3", description="Modelo cujo perfil de autonomia será usado."
    )
    row_azimuth_deg: float = Field(
        default=90.0,
        ge=0.0,
        lt=360.0,
        description=(
            "Direção das linhas de plantio, em graus a partir do norte. O rover anda "
            "ao longo delas; atravessar passaria por cima das plantas."
        ),
    )
    swath_m: float | None = Field(
        default=None, gt=0, description="Largura útil da passada. Vazio usa a do modelo."
    )
    start_battery_percent: float = Field(default=100.0, gt=0, le=100)
    reserve_percent: float | None = Field(
        default=None, ge=0, lt=100, description="Reserva intocável. Vazio usa a do sistema."
    )
    boundary: Polygon | None = Field(
        default=None,
        description=(
            "Rascunho: planeja este contorno em vez do salvo. É o editor mostrando a "
            "rota enquanto a pessoa ainda desenha — planejar não grava nada."
        ),
    )
    terrain: TerrainOut | None = Field(
        default=None,
        description="Rascunho: a leitura de imagem do encaixe que ainda não foi salva.",
    )
    speed_ms: float | None = Field(default=None, gt=0, description="Sobrepõe a do modelo.")
    obstacle_margin_m: float = Field(
        default=2.0,
        ge=0,
        le=50,
        description=(
            "Folga entre a passada e a borda de um obstáculo. O contorno de um "
            "obstáculo lido por imagem é o retângulo de um bloco da grade, e "
            "raspá-lo é entrar nele."
        ),
    )


class ChargePostOut(ApiModel):
    """Um ponto do percurso onde falta energia para continuar."""

    ordem: int
    lat: float
    lon: float
    metros_no_percurso: float
    bateria_na_chegada_percent: float
    minutos_de_recarga: float
    area_coberta_ha: float
    motivo: str


class PlanOut(ApiModel):
    """O plano de cobertura de um talhão."""

    field_id: str
    field_name: str | None = None
    device_model_code: str
    area_ha: float
    swath_m: float
    azimute_deg: float
    velocidade_ms: float = Field(
        description="Velocidade de cruzeiro usada no cálculo do tempo, em m/s."
    )
    passadas: int
    metros_de_linha: float
    metros_de_manobra: float
    metros_totais: float
    minutos_dirigindo: float
    minutos_de_manobra: float
    minutos_de_recarga: float
    minutos_totais: float
    horas_totais: float
    wh_totais: float
    ha_por_hora: float
    cargas: int
    postes: list[ChargePostOut]
    rota: list[list[list[float]]] = Field(
        default_factory=list, description="Passadas em [[lat, lon], ...], para desenhar no mapa."
    )
    perfil_medido: bool = Field(
        description="Falso: o consumo veio do datasheet, não de missão medida em campo."
    )
    terrain: TerrainOut | None = Field(
        default=None,
        description=(
            "A leitura de imagem gravada neste talhão, quando houver. O console a "
            "desenha sobre a rota para quem valida a missão ver o que está no caminho."
        ),
    )
    operable_area_ha: float | None = Field(
        default=None,
        description=(
            "Área que é lavoura ou caminho, segundo a leitura de imagem. Menor que "
            "``area_ha`` quando há obstáculo dentro do contorno."
        ),
    )
    area_contornada_ha: float = Field(
        default=0.0,
        description=(
            "Área dos obstáculos que a rota contorna. A rota desvia deles: as "
            "passadas que os atravessariam foram partidas em duas."
        ),
    )
    relief: ReliefOut | None = Field(
        default=None,
        description=(
            "O relevo gravado neste talhão, quando há. Nulo quando não há fonte "
            "de elevação configurada — e então a rota foi planejada como se o "
            "talhão fosse plano, o que os avisos declaram."
        ),
    )
    avoided: int = Field(
        default=0, description="Quantos obstáculos a rota contornou."
    )
    avisos: list[str]


class BoundaryRefineIn(ApiModel):
    """O contorno que o produtor desenhou a mão, para a IA encaixar."""

    polygon: Polygon
    tolerance: float = Field(
        default=0.35,
        gt=0.0,
        le=1.0,
        description=(
            "Quanto o contorno pode se afastar do traço, como fração do raio. "
            "Baixo trava perto do desenho; alto corrige mão trêmula."
        ),
    )
    vertices: int = Field(default=48, ge=8, le=360)


class RowsOut(ApiModel):
    """O que a imagem disse sobre as linhas de plantio dentro do contorno."""

    detected: bool
    azimuth_deg: float | None = None
    spacing_m: float | None = None
    strength: float
    description: str


class BoundaryRefineOut(ApiModel):
    """O contorno encaixado, com o que é preciso para confiar nele ou não."""

    polygon: list[list[float]]
    area_ha: float
    area_change: float = Field(description="Variação em relação ao que foi desenhado.")
    confidence: float = Field(description="Fração das direções com borda nítida.")
    hit_limit: float = Field(description="Fração que parou na tolerância, não numa borda.")
    meters_per_pixel: float
    rows: RowsOut | None = None
    terrain: TerrainOut | None = Field(
        default=None, description="Cobertura e obstáculos lidos dentro do contorno."
    )
    notes: list[str] = Field(default_factory=list)
    method: str = Field(
        default="radial",
        description=(
            "``carreador``: cada lado encostou na estrada de terra (talhão de café). "
            "``radial``: o encaixe antigo, para IA que ainda não tem o outro."
        ),
    )


class FieldAiModelUpdate(ApiModel):
    """Troca a versão do modelo de diagnóstico do talhão."""

    ai_model: str | None = Field(
        default=None,
        max_length=64,
        description="Chave da versão (ex.: 'citrus-foliar-cc'); nulo volta à recomendada.",
    )


class AiModelChoiceOut(ApiModel):
    """Uma versão do modelo que atende a cultura do talhão — o que o seletor mostra."""

    key: str
    name: str | None = None
    version: str
    variant: str
    recommended: bool
    license: str
    field_performance: str | None = Field(
        default=None,
        description=(
            "Desempenho no campo em linguagem operacional (alto, bom, limitado). A métrica "
            "técnica fica no registry, só para a equipe (brief, seção 10)."
        ),
    )
    caveat: str | None = None
    selected: bool = Field(description="Se é a versão em uso neste talhão.")


class FieldBoundaryUpdate(ApiModel):
    """Novo contorno de um talhão que já existe."""

    boundary: Polygon
    row_azimuth_deg: float | None = Field(
        default=None,
        ge=0,
        lt=180,
        description="Direção das linhas, quando a leitura da imagem a descobriu.",
    )
    terrain: TerrainOut | None = Field(
        default=None,
        description=(
            "A leitura de terreno que veio junto com o encaixe do contorno. Ela é "
            "gravada com o contorno porque é dele que vale: um terreno lido sobre "
            "outro polígono descreve outro pedaço de chão."
        ),
    )


# ---------------------------------------------------------------------------
# Planos, assinatura e uso (brief, seção 31)
# ---------------------------------------------------------------------------


class BillingPlanLimits(ApiModel):
    """Limites de um plano. Nulo é **sem limite**."""

    max_hectares: float | None = Field(default=None, ge=0)
    max_farms: int | None = Field(default=None, ge=0)
    max_fields: int | None = Field(default=None, ge=0)
    max_devices: int | None = Field(default=None, ge=0)
    max_users: int | None = Field(default=None, ge=0)
    max_missions_per_month: int | None = Field(default=None, ge=0)
    max_storage_gb: float | None = Field(default=None, ge=0)
    retention_days: int | None = Field(default=None, ge=1)


class BillingPlanCreate(BillingPlanLimits):
    code: Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9-]{1,38}$")]
    name: Name
    description: str | None = Field(default=None, max_length=2000)
    features: list[str] = Field(default_factory=list)
    price_cents: int | None = Field(default=None, ge=0)


class BillingPlanUpdate(ApiModel):
    """Alteração parcial: só o que vier é mudado. Mande ``null`` para tirar um limite."""

    model_config = ConfigDict(extra="forbid")

    name: Name | None = None
    description: str | None = None
    is_active: bool | None = None
    features: list[str] | None = None
    price_cents: int | None = None
    max_hectares: float | None = None
    max_farms: int | None = None
    max_fields: int | None = None
    max_devices: int | None = None
    max_users: int | None = None
    max_missions_per_month: int | None = None
    max_storage_gb: float | None = None
    retention_days: int | None = None


class BillingPlanOut(BillingPlanLimits):
    id: str
    code: str
    name: str
    description: str | None
    is_active: bool
    features: list[str]
    price_cents: int | None


class SubscriptionUpdate(ApiModel):
    plan_code: str
    status: SubscriptionStatus = SubscriptionStatus.ATIVA
    ends_at: datetime | None = None
    overrides: dict[str, float | int | None] = Field(
        default_factory=dict,
        description="Limites só deste cliente, com o nome da coluna do plano: {'max_fields': 12}.",
    )
    notes: str | None = Field(default=None, max_length=4000)
    billing_customer_id: str | None = Field(default=None, max_length=120)


class UsageItem(ApiModel):
    resource: str
    label: str
    used: float
    limit: float | None
    percent: float | None = Field(
        default=None, description="Uso sobre o limite, em %. O console avisa a partir de 80."
    )


class SubscriptionOut(ApiModel):
    tenant_id: str
    has_subscription: bool
    plan: BillingPlanOut | None
    status: SubscriptionStatus | None
    started_at: datetime | None
    ends_at: datetime | None
    overrides: dict
    notes: str | None
    effective_limits: dict[str, float | int | None]
    usage: list[UsageItem]


# ---------------------------------------------------------------------------
# Consentimento de uso dos dados no treino (brief, seção 32)
# ---------------------------------------------------------------------------


class DataConsentIn(ApiModel):
    """A pergunta do console: "Permitir utilização dos dados/imagens para melhoria dos
    modelos?" — SIM (``true``) ou NÃO (``false``)."""

    allowed: bool
    notes: str | None = Field(default=None, max_length=2000)


class DataConsentPlatformIn(DataConsentIn):
    """Registro feito pela ValTexa a partir de termo ou contrato assinado."""

    document_ref: str = Field(min_length=3, max_length=200)


class DataConsentOut(ApiModel):
    id: str
    allowed: bool
    decided_at: datetime
    decided_by_label: str
    source: str
    document_ref: str | None
    notes: str | None


class DataConsentStatus(ApiModel):
    tenant_id: str
    allowed: bool = Field(
        description="O que vale agora. Sem decisão registrada, é falso (NÃO)."
    )
    decided: bool
    current: DataConsentOut | None
    history: list[DataConsentOut]


# ---------------------------------------------------------------------------
# Console interno: o que as telas de /plataforma consomem (brief, seções 28 e 29)
# ---------------------------------------------------------------------------


class PlatformMeOut(ApiModel):
    """Quem é a pessoa da equipe e o que ela pode no console interno."""

    id: str
    email: str
    full_name: str
    platform_role: PlatformRole
    capabilities: list[str]
    open_support_sessions: list[SupportSessionOut] = Field(
        default_factory=list,
        description="Sessões de suporte desta pessoa ainda abertas (para retomar ou sair).",
    )


class TenantConsentSummary(ApiModel):
    allowed: bool
    decided: bool
    decided_at: datetime | None
    source: str | None


class PlatformTenantSummary(ApiModel):
    """A linha da lista de clientes: cadastro, plano, assinatura, uso e consentimento."""

    id: str
    name: str
    slug: str
    document: str | None
    is_active: bool
    city: str | None
    state: str | None
    created_at: datetime
    plan_code: str | None
    plan_name: str | None
    subscription_status: SubscriptionStatus | None
    subscription_ends_at: datetime | None
    usage: list[UsageItem] = Field(
        default_factory=list, description="Vazio para quem não tem platform:usage:read."
    )
    warnings: list[str] = Field(
        default_factory=list, description="Rótulos dos limites com uso de 80% ou mais."
    )
    consent: TenantConsentSummary
    members: int
    open_support_sessions: int


class GlobalAccountMembership(ApiModel):
    tenant_id: str
    tenant_name: str
    role: Role


class GlobalAccountOut(ApiModel):
    id: str
    email: str
    full_name: str
    is_active: bool
    platform_role: PlatformRole | None
    last_login_at: datetime | None
    created_at: datetime
    memberships: list[GlobalAccountMembership]


class AccountActiveUpdate(ApiModel):
    is_active: bool
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=5, max_length=500)]


# ---------------------------------------------------------------------------
# Sincronização do Rover Runtime (Parte 4): registros e uploads em chunks
# ---------------------------------------------------------------------------


class EdgeRecordIn(ApiModel):
    """Um resultado da Edge AI ou um evento do robô, com o hash do corpo."""

    id: str = Field(min_length=1, max_length=64, description="ID gerado no robô (UUID).")
    kind: str = Field(description="result | event")
    type: str = Field(min_length=1, max_length=64)
    sha256: str = Field(min_length=64, max_length=64,
                        description="SHA-256 do JSON canônico de body (ver docs/SYNC.md).")
    body: dict[str, Any]


class EdgeRecordBatch(ApiModel):
    records: list[EdgeRecordIn] = Field(min_length=1)
    remaining: int | None = Field(
        default=None, ge=0,
        description="Itens que ainda esperam no robô; > 0 deixa a frota em SINCRONIZANDO.",
    )


class EdgeRecordsOut(ApiModel):
    accepted: list[str]
    duplicated: list[str] = Field(description="Mesmo ID e mesmo hash: já estava aqui.")
    conflicts: list[str] = Field(description="Mesmo ID com outro hash: recusado.")
    rejected: list[dict[str, str]]


class UploadOpenIn(ApiModel):
    upload_id: str = Field(min_length=1, max_length=80)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size_bytes: int = Field(ge=1)
    content_type: str = Field(max_length=64)
    chunk_size: int = Field(ge=1024, le=8 * 1024 * 1024)
    record_id: str | None = Field(default=None, max_length=64)
    role: str | None = Field(default=None, max_length=32)
    tier: str | None = Field(default=None, max_length=16)
    priority: int | None = Field(default=None, ge=1, le=6)


class UploadStateOut(ApiModel):
    upload_id: str
    status: str = Field(description="receiving | complete")
    sha256: str
    size_bytes: int
    chunk_size: int
    total_chunks: int
    received_chunks: list[int]
    asset_id: str | None = None
    deduplicated: bool = False


class UploadCompleteIn(ApiModel):
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class ChunkOut(ApiModel):
    received: int
    total_chunks: int


class EdgeFileOut(ApiModel):
    upload_id: str
    role: str | None
    sha256: str
    size_bytes: int
    content_type: str
    status: str
    asset_id: str | None


class LinkDeArquivoOut(ApiModel):
    """Onde baixar um arquivo do cliente (seção 38).

    ``direct=true``: URL assinada do object storage, válida por ``expires_in`` segundos,
    emitida só depois do escopo do cliente conferido. ``direct=false`` (disco local):
    ``url`` é a própria rota da API, que exige o login.
    """

    url: str
    direct: bool
    expires_in: int | None


class EdgeRecordOut(ApiModel):
    id: str
    record_id: str
    device_id: str
    kind: str
    type: str
    mission_id: str | None
    field_id: str | None
    occurred_at: datetime
    received_at: datetime
    severity: str | None
    label: str | None
    confidence: float | None
    model_key: str | None
    model_version: str | None
    lat: float | None
    lon: float | None
    payload: dict[str, Any]
    files: list[EdgeFileOut] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# OTA (seção 24)
# ---------------------------------------------------------------------------


class OtaPackageOut(ApiModel):
    model_config = ALLOW_MODEL_PREFIX

    id: str
    kind: str
    version: str
    sha256: str
    size_bytes: int
    manifest: dict[str, Any]
    model_version_id: str | None
    notes: str | None
    created_at: datetime


class OtaDeploymentIn(ApiModel):
    package_id: str
    device_ids: list[str] | None = Field(default=None, max_length=1000)
    tenant_id: str | None = None


class OtaDeploymentOut(ApiModel):
    id: str
    package_id: str
    kind: str
    version: str
    device_id: str
    device_serial: str
    tenant_id: str
    tenant_name: str
    state: str
    detail: str | None
    history: list[dict[str, Any]]
    bytes_served: int
    size_bytes: int
    created_at: datetime
    finished_at: datetime | None


class OtaDeviceItemOut(ApiModel):
    deployment_id: str
    state: str
    envelope: dict[str, Any] = Field(
        description="payload (pacote, manifesto, robô, validade) + assinatura Ed25519 OTA."
    )


class OtaStatusIn(ApiModel):
    state: str = Field(max_length=24)
    detail: str | None = Field(default=None, max_length=2000)
    version_running: str | None = Field(default=None, max_length=64)


# ---------------------------------------------------------------------------
# Notificações (Parte 6, seção 48)
# ---------------------------------------------------------------------------


class NotificationDeliveryOut(ApiModel):
    channel: str
    status: str = Field(
        description="pendente, enviado, nao_enviado (sem SMTP ou canal não implementado), "
        "falhou (vai tentar de novo) ou desistiu."
    )
    attempts: int
    last_error: str | None
    sent_at: datetime | None


class NotificationOut(ApiModel):
    id: str
    kind: str
    severity: str
    title: str
    body: str
    link: str | None
    subject_type: str | None
    subject_id: str | None
    created_at: datetime
    read_at: datetime | None
    deliveries: list[NotificationDeliveryOut]


class NotificationCount(ApiModel):
    unread: int


class NotificationReadAll(ApiModel):
    marked: int


class NotificationChannelOut(ApiModel):
    name: str
    label: str
    implemented: bool
    configured: bool


class NotificationPreferenceOut(ApiModel):
    kind: str
    label: str
    description: str
    enabled: bool
    channels: list[str]
    threshold: float | None
    threshold_unit: str | None
    source: str = Field(description="pessoa, papel ou padrao: de onde veio a regra que vale.")


class NotificationPreferencesOut(ApiModel):
    role: str | None
    channels: list[NotificationChannelOut]
    preferences: list[NotificationPreferenceOut]


class NotificationPreferenceIn(ApiModel):
    kind: str = Field(max_length=40)
    enabled: bool = True
    channels: list[str] = Field(
        default_factory=list, max_length=8,
        description="Canais externos ('email'). A central do console vale sempre.",
    )
    threshold: float | None = Field(default=None, ge=0, le=100)
    reset: bool = Field(
        default=False, description="true: apaga a preferência e volta ao padrão."
    )


class NotificationRolePreferenceIn(NotificationPreferenceIn):
    role: str = Field(max_length=16)


# ---------------------------------------------------------------------------
# Suporte: chamados e incidentes (Parte 6, seção 49)
# ---------------------------------------------------------------------------


class IncidentBrief(ApiModel):
    id: str
    code: str
    title: str
    status: str
    public_note: str | None


class TicketOut(ApiModel):
    id: str
    code: str
    tenant_id: str
    tenant_name: str | None = None
    title: str
    description: str
    status: str
    priority: str
    category: str | None
    device_id: str | None
    device_label: str | None
    mission_id: str | None
    incident: IncidentBrief | None
    opened_by_label: str
    opened_via: str
    assignee_id: str | None
    assignee_label: str | None
    created_at: datetime
    last_activity_at: datetime
    first_response_at: datetime | None
    resolved_at: datetime | None
    closed_at: datetime | None


class TicketCommentOut(ApiModel):
    id: str
    author_label: str
    side: str
    body: str
    internal: bool
    created_at: datetime


class TicketEventOut(ApiModel):
    at: datetime
    actor_label: str
    side: str
    kind: str
    old_value: str | None
    new_value: str | None
    note: str | None
    internal: bool


class TicketDetailOut(TicketOut):
    comments: list[TicketCommentOut]
    history: list[TicketEventOut]
    support_sessions: list[SupportSessionOut] = Field(
        default_factory=list,
        description="Sessões 'entrar como cliente' abertas por causa deste chamado.",
    )


class TicketCreate(ApiModel):
    title: str = Field(min_length=5, max_length=200)
    description: str = Field(min_length=10, max_length=10000)
    priority: Literal["baixa", "normal", "alta", "urgente"] = "normal"
    category: str | None = Field(default=None, max_length=40)
    device_id: str | None = Field(default=None, max_length=32)
    mission_id: str | None = Field(default=None, max_length=32)


class PlatformTicketCreate(TicketCreate):
    tenant_id: str = Field(max_length=32)


class TicketCommentIn(ApiModel):
    body: str = Field(min_length=1, max_length=10000)


class PlatformTicketCommentIn(TicketCommentIn):
    internal: bool = Field(default=False, description="Nota da equipe: o cliente não vê.")


class TicketReopen(ApiModel):
    reason: str = Field(min_length=5, max_length=2000)


class TicketClose(ApiModel):
    reason: str | None = Field(default=None, max_length=2000)


class TicketUpdate(ApiModel):
    status: Literal[
        "aberto", "em_atendimento", "aguardando_cliente", "resolvido", "fechado"
    ] | None = None
    priority: Literal["baixa", "normal", "alta", "urgente"] | None = None
    assignee_id: str | None = Field(default=None, max_length=32)
    unassign: bool = False
    incident_id: str | None = Field(default=None, max_length=32)
    unlink_incident: bool = False
    note: str | None = Field(default=None, max_length=2000)


class TicketAssigneeOut(ApiModel):
    id: str
    full_name: str
    platform_role: str


class IncidentOut(ApiModel):
    id: str
    code: str
    title: str
    description: str
    status: str
    severity: str
    public_note: str | None
    started_at: datetime
    resolved_at: datetime | None
    ticket_count: int
    tenant_count: int


class IncidentDetailOut(IncidentOut):
    tickets: list[TicketOut]


class IncidentCreate(ApiModel):
    title: str = Field(min_length=5, max_length=200)
    description: str = Field(default="", max_length=10000)
    severity: Literal["baixa", "media", "alta", "critica"] = "media"
    public_note: str | None = Field(default=None, max_length=4000)
    ticket_ids: list[str] = Field(default_factory=list, max_length=500)


class IncidentUpdate(ApiModel):
    title: str | None = Field(default=None, max_length=200)
    status: Literal["aberto", "investigando", "mitigado", "resolvido"] | None = None
    severity: Literal["baixa", "media", "alta", "critica"] | None = None
    public_note: str | None = Field(default=None, max_length=4000)


class IncidentLink(ApiModel):
    ticket_ids: list[str] = Field(min_length=1, max_length=500)


# ---------------------------------------------------------------------------
# Observabilidade e alertas (Parte 7, seções 34 e 35)
# ---------------------------------------------------------------------------


class ObsComponentOut(ApiModel):
    component: str = Field(description="banco, api, worker, ia, frota, alertas")
    status: str = Field(description="ok, atencao ou falha")
    detail: str | None = None


class ApiRouteStatOut(ApiModel):
    method: str
    route: str = Field(description="Molde da rota (com {parâmetros}), não o caminho com id.")
    requests: int
    server_errors: int
    client_errors: int
    error_rate: float | None
    latency_ms_avg: float | None
    latency_ms_p50: float | None = Field(description="Aproximado pelos baldes do histograma.")
    latency_ms_p95: float | None
    latency_ms_max: float | None


class ApiStatsOut(ApiModel):
    window_minutes: int
    requests: int
    server_errors: int
    client_errors: int
    error_rate: float | None
    latency_ms_avg: float | None
    latency_ms_p50: float | None
    latency_ms_p95: float | None
    latency_ms_max: float | None
    routes: list[ApiRouteStatOut]


class JobCountOut(ApiModel):
    kind: str
    state: str
    count: int


class QueuesOut(ApiModel):
    jobs: list[JobCountOut]
    jobs_queued: int
    jobs_running: int
    jobs_oldest_queued_s: float | None
    jobs_failed_24h: int
    outbox_pending: int
    outbox_with_error: int
    outbox_oldest_pending_s: float | None
    deliveries: dict[str, int] = Field(description="Entregas de aviso por estado.")


class ActiveUsersOut(ApiModel):
    active_15m: int
    active_24h: int


class AiServiceOut(ApiModel):
    status: str = Field(description="ok, fora, desligado ou simulado")
    detail: str | None = None
    checked_at: str | None = None


class ObservabilityOverviewOut(ApiModel):
    generated_at: datetime
    components: list[ObsComponentOut]
    api: ApiStatsOut
    queues: QueuesOut
    users: ActiveUsersOut
    ai_service: AiServiceOut
    alerts_open: int
    alerts_critical: int


class RoverCameraOut(ApiModel):
    id: str
    ok: bool
    detail: str | None = None


class RoverHealthOut(ApiModel):
    """Saúde de um robô. ``None`` = o robô não mediu (não é zero)."""

    device_id: str
    name: str
    serial_number: str
    tenant_id: str
    tenant_name: str | None = None
    status: str
    cpu_percent: float | None
    memory_percent: float | None
    accelerator_percent: float | None
    accelerator_name: str | None
    disk_percent: float | None
    temperature_c: float | None
    battery_percent: float | None
    cameras_total: int
    cameras_ok: int
    cameras: list[RoverCameraOut]
    sensors: dict[str, str | None]
    connectivity: str
    last_seen_at: datetime | None
    offline_minutes: float | None
    sync_pending: int
    sync_oldest_pending_s: float | None
    sync_blocked: bool
    last_sync_at: datetime | None
    edge_ai: dict
    versions: dict[str, str | None]
    faults: list[Any]
    health_reported_at: datetime | None
    simulated: list[str] = Field(description="Partes da HAL que são simulação.")
    open_alerts: int = 0


class AiModelStatOut(ApiModel):
    source: str = Field(description="nuvem ou borda")
    model_key: str
    model_version: str
    simulated: bool = False
    inferences: int
    errors: int | None = None
    error_rate: float | None = None
    abstentions: int | None = None
    latency_ms_avg: float | None = None
    latency_ms_p95: float | None = None
    classes: dict[str, int]


class AiDriftOut(ApiModel):
    source: str
    model_key: str
    recent: int
    baseline: int
    distance: float | None = Field(
        description="Distância de variação total (0 a 1) entre a distribuição de classes "
                    "recente e a base. Nulo se a amostra não basta (ver reason)."
    )
    reason: str | None
    recent_classes: dict[str, int]
    baseline_classes: dict[str, int]


class AiObservabilityOut(ApiModel):
    window_hours: int
    service: AiServiceOut
    cloud: list[AiModelStatOut]
    edge: list[AiModelStatOut]
    drift: list[AiDriftOut]
    drift_note: str


class ObsAlertOut(ApiModel):
    id: str
    kind: str
    kind_label: str
    state: str = Field(description="disparado, reconhecido ou resolvido")
    severity: str
    tenant_id: str | None
    tenant_name: str | None = None
    subject_type: str
    subject_id: str
    subject_label: str
    message: str
    value: float | None
    threshold: float | None
    fired_at: datetime
    last_seen_at: datetime
    acknowledged_at: datetime | None
    acknowledged_label: str | None
    ack_note: str | None
    resolved_at: datetime | None


class AlertAckIn(ApiModel):
    note: str | None = Field(default=None, max_length=2000)


class AlertRuleOut(ApiModel):
    kind: str
    label: str
    description: str
    scope: str = Field(description="robo (aceita versão por cliente) ou plataforma")
    unit: str | None
    enabled: bool
    threshold: float | None
    window_minutes: int | None
    severity: str
    default_threshold: float | None
    source: str = Field(description="padrao (regra da plataforma) ou cliente (versão própria)")
    updated_at: datetime | None


class AlertRuleIn(ApiModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    enabled: bool | None = None
    threshold: float | None = None
    window_minutes: int | None = None
    severity: str | None = None
