"""Planos, limites e uso (brief, seção 31).

O que este módulo responde:

* **qual é o limite** de um cliente: o do plano, com as sobreposições da
  assinatura dele (:func:`limites_efetivos`);
* **quanto ele usa**: estoque contado nas tabelas (fazendas, talhões, hectares,
  robôs, usuários, armazenamento) e fluxo no :class:`UsageCounter` (missões no
  mês) (:func:`uso`);
* **se pode criar mais um** (:func:`exigir`), com a mensagem em português que o
  console mostra como está.

Cliente **sem assinatura** não tem limite — é o legado de antes dos planos e o
estado de quem foi criado direto no banco. A migração 0011 dá a todo cliente
existente o plano ``piloto`` (sem limites), preservando o texto antigo de
``contracted_service`` na observação da assinatura; cliente novo nasce com o
plano escolhido no cadastro, ou com o ``piloto`` e um aviso.

Cobrança fica fora desta rodada (decisão registrada em docs/CONTEXTO_NUVEM.md):
``billing_customer_id`` está reservado, e o preço do plano é só referência.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from valtexa.models import (
    ActorType,
    Asset,
    Device,
    DeviceStatus,
    Farm,
    Field,
    Membership,
    Plan,
    SubjectType,
    Subscription,
    SubscriptionStatus,
    Tenant,
    UsageCounter,
    User,
    as_utc,
)
from valtexa.services import audit

PLANO_PADRAO = "piloto"

LIMITES: dict[str, tuple[str, str]] = {
    # recurso: (coluna do plano, rótulo no plural para a mensagem)
    "farms": ("max_farms", "fazendas"),
    "fields": ("max_fields", "talhões"),
    "hectares": ("max_hectares", "hectares"),
    "devices": ("max_devices", "robôs"),
    "users": ("max_users", "usuários"),
    "missions_month": ("max_missions_per_month", "missões neste mês"),
    "storage_gb": ("max_storage_gb", "GB de armazenamento"),
}
"""Os recursos limitáveis, ligados à coluna do plano que os limita."""

COLUNAS_DE_LIMITE = frozenset(coluna for coluna, _ in LIMITES.values()) | {"retention_days"}

CATALOGO_INICIAL: list[dict] = [
    {
        "code": "piloto",
        "name": "Piloto",
        "description": (
            "Clientes do piloto e anteriores aos planos. Sem limites: é o que mantém "
            "funcionando quem já operava antes da migração 0011."
        ),
        "features": ["prescricao", "lavoura_3d", "validacao_campo", "relatorios"],
    },
    # Valores PROVISÓRIOS, para o sistema ter o que aplicar e testar. Os números
    # e os nomes são decisão comercial do Pedro (docs/historico/PLANO_SAAS.md, seção 9, item 2):
    # trocar é editar o plano pelo console ou pela API, sem migração.
    {
        "code": "essencial",
        "name": "Essencial",
        "description": "Monitoramento com um rover. Valores provisórios, a definir.",
        "max_hectares": 100.0,
        "max_farms": 1,
        "max_fields": 5,
        "max_devices": 1,
        "max_users": 3,
        "max_missions_per_month": 30,
        "max_storage_gb": 50.0,
        "retention_days": 30,
        "features": ["relatorios"],
    },
    {
        "code": "profissional",
        "name": "Profissional",
        "description": "Monitoramento e prescrição. Valores provisórios, a definir.",
        "max_hectares": 1000.0,
        "max_farms": 5,
        "max_fields": 50,
        "max_devices": 5,
        "max_users": 15,
        "max_missions_per_month": 300,
        "max_storage_gb": 500.0,
        "retention_days": 90,
        "features": ["prescricao", "relatorios", "validacao_campo"],
    },
    {
        "code": "empresarial",
        "name": "Empresarial",
        "description": "Operação grande, sob contrato. Valores provisórios, a definir.",
        "max_hectares": None,
        "max_farms": None,
        "max_fields": None,
        "max_devices": 50,
        "max_users": None,
        "max_missions_per_month": None,
        "max_storage_gb": 5000.0,
        "retention_days": 365,
        "features": ["prescricao", "lavoura_3d", "validacao_campo", "relatorios"],
    },
]


class PlanError(Exception):
    """Pedido recusado pelo plano. Carrega o status HTTP e a mensagem em português."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def sincronizar_catalogo(session: Session) -> int:
    """Cria os planos do catálogo inicial que ainda não existem. Não altera os que existem.

    Roda no start, como o catálogo de hardware: um plano que o comercial editou
    pelo console não pode voltar ao valor do código a cada reinício.
    """
    existentes = set(session.scalars(select(Plan.code)))
    criados = 0
    for item in CATALOGO_INICIAL:
        if item["code"] in existentes:
            continue
        session.add(Plan(**item))
        criados += 1
    if criados:
        session.commit()
    return criados


def plano_por_codigo(session: Session, code: str) -> Plan | None:
    return session.scalars(select(Plan).where(Plan.code == code)).first()


def assinatura(session: Session, tenant_id: str) -> Subscription | None:
    return session.scalars(
        select(Subscription).where(Subscription.tenant_id == tenant_id)
    ).first()


def limites_efetivos(sub: Subscription | None) -> dict[str, float | int | None]:
    """Coluna de limite → valor, já com as sobreposições do cliente. ``None`` = sem limite."""
    if sub is None:
        return dict.fromkeys(COLUNAS_DE_LIMITE)
    plano = sub.plan
    efetivos = {coluna: getattr(plano, coluna) for coluna in COLUNAS_DE_LIMITE}
    for coluna, valor in (sub.overrides or {}).items():
        if coluna in COLUNAS_DE_LIMITE:
            efetivos[coluna] = valor
    return efetivos


def periodo(agora: datetime | None = None) -> str:
    agora = agora or datetime.now(UTC)
    return f"{agora.year:04d}-{agora.month:02d}"


def uso(session: Session, tenant_id: str) -> dict[str, float]:
    """O que o cliente usa agora, por recurso limitável."""
    fazendas = session.scalar(select(func.count()).where(Farm.tenant_id == tenant_id)) or 0
    talhoes = session.scalar(select(func.count()).where(Field.tenant_id == tenant_id)) or 0
    hectares = (
        session.scalar(
            select(func.coalesce(func.sum(Field.area_ha), 0.0)).where(
                Field.tenant_id == tenant_id
            )
        )
        or 0.0
    )
    robos = (
        session.scalar(
            select(func.count()).where(
                Device.tenant_id == tenant_id, Device.status != DeviceStatus.RETIRED
            )
        )
        or 0
    )
    usuarios = (
        session.scalar(select(func.count()).where(Membership.tenant_id == tenant_id)) or 0
    )
    bytes_ = (
        session.scalar(
            select(func.coalesce(func.sum(Asset.size_bytes), 0)).where(
                Asset.tenant_id == tenant_id
            )
        )
        or 0
    )
    missoes = _contador(session, tenant_id, "missions", periodo())
    return {
        "farms": float(fazendas),
        "fields": float(talhoes),
        "hectares": round(float(hectares), 4),
        "devices": float(robos),
        "users": float(usuarios),
        "missions_month": float(missoes),
        "storage_gb": round(float(bytes_) / 1024**3, 4),
    }


def exigir(session: Session, tenant_id: str, recurso: str, acrescimo: float = 1) -> None:
    """Recusa a criação se ela passar do limite do plano, ou se a assinatura não vale.

    Levanta :class:`PlanError` com 402 (assinatura suspensa, cancelada ou vencida)
    ou 409 (limite atingido). Sem assinatura, não há limite.
    """
    if recurso not in LIMITES:
        raise ValueError(f"Recurso sem limite conhecido: {recurso!r}")
    sub = assinatura(session, tenant_id)
    if sub is None:
        return
    _exige_assinatura_valida(sub)

    coluna, rotulo = LIMITES[recurso]
    limite = limites_efetivos(sub)[coluna]
    if limite is None:
        return
    atual = uso(session, tenant_id)[recurso]
    if atual + acrescimo > float(limite) + 1e-9:
        raise PlanError(
            409,
            f"Limite do plano {sub.plan.name} atingido: {_fmt(atual)} de {_fmt(limite)} "
            f"{rotulo}"
            + (f" (este pedido somaria {_fmt(acrescimo)})" if acrescimo != 1 else "")
            + ". Para ampliar, fale com a ValTexa.",
        )


RECURSOS = frozenset({"prescricao", "lavoura_3d", "validacao_campo", "relatorios", "api_externa"})
"""Os recursos que um plano liga ou desliga (``Plan.features``)."""


def exigir_recurso(session: Session, tenant_id: str, recurso: str) -> None:
    """Recusa o uso de um recurso que o plano do cliente não inclui (402).

    Sem assinatura, não há restrição — o mesmo critério dos limites. Assinatura
    suspensa não bloqueia recurso de leitura: quem está suspenso continua
    consultando o que já tem; o bloqueio é de criação (:func:`exigir`).
    """
    if recurso not in RECURSOS:
        raise ValueError(f"Recurso desconhecido: {recurso!r}")
    sub = assinatura(session, tenant_id)
    if sub is None:
        return
    if recurso not in (sub.plan.features or []):
        raise PlanError(
            402,
            f"O recurso {ROTULO_DE_RECURSO[recurso]} não faz parte do plano {sub.plan.name}. "
            "Para incluí-lo, fale com a ValTexa.",
        )


ROTULO_DE_RECURSO = {
    "prescricao": "prescrição",
    "lavoura_3d": "lavoura 3D",
    "validacao_campo": "validação de campo",
    "relatorios": "relatórios",
    "api_externa": "API externa",
}


def _exige_assinatura_valida(sub: Subscription) -> None:
    if sub.status in {SubscriptionStatus.SUSPENSA, SubscriptionStatus.CANCELADA}:
        raise PlanError(
            402,
            f"Assinatura {sub.status.value}: criar fazenda, talhão, robô, usuário ou "
            "missão está bloqueado. O que já existe continua disponível para consulta. "
            "Fale com a ValTexa.",
        )
    fim = as_utc(sub.ends_at)
    if fim is not None and fim <= datetime.now(UTC):
        raise PlanError(
            402,
            f"A assinatura venceu em {fim:%d/%m/%Y}: criação bloqueada até a renovação. "
            "Fale com a ValTexa.",
        )


def registrar_missao(session: Session, tenant_id: str) -> None:
    """Soma uma missão ao uso do mês. Não faz *commit*."""
    _somar(session, tenant_id, "missions", 1)


def _contador(session: Session, tenant_id: str, metric: str, period: str) -> float:
    linha = session.scalars(
        select(UsageCounter).where(
            UsageCounter.tenant_id == tenant_id,
            UsageCounter.period == period,
            UsageCounter.metric == metric,
        )
    ).first()
    return linha.value if linha else 0.0


def _somar(session: Session, tenant_id: str, metric: str, valor: float) -> None:
    mes = periodo()
    linha = session.scalars(
        select(UsageCounter).where(
            UsageCounter.tenant_id == tenant_id,
            UsageCounter.period == mes,
            UsageCounter.metric == metric,
        )
    ).first()
    if linha is None:
        # Duas criações simultâneas da primeira linha do mês esbarram na
        # restrição única e uma delas falha no commit — a requisição é recusada,
        # não contada em dobro. Acontece uma vez por cliente por mês.
        linha = UsageCounter(tenant_id=tenant_id, period=mes, metric=metric, value=0)
        session.add(linha)
    linha.value = (linha.value or 0) + valor


def assinar(
    session: Session,
    tenant: Tenant,
    plano: Plan,
    *,
    actor: User | None,
    status: SubscriptionStatus = SubscriptionStatus.ATIVA,
    ends_at: datetime | None = None,
    overrides: dict | None = None,
    notes: str | None = None,
    billing_customer_id: str | None = None,
) -> Subscription:
    """Cria ou troca a assinatura do cliente, com o antes e o depois na auditoria."""
    if not plano.is_active:
        raise PlanError(409, f"O plano {plano.name} está inativo e não aceita assinatura nova.")
    desconhecidas = set(overrides or {}) - COLUNAS_DE_LIMITE
    if desconhecidas:
        raise PlanError(
            422, f"Sobreposição de limite desconhecida: {', '.join(sorted(desconhecidas))}."
        )

    sub = assinatura(session, tenant.id)
    antes = _resumo(sub)
    if sub is None:
        sub = Subscription(
            tenant_id=tenant.id,
            plan_id=plano.id,
            status=status,
            started_at=datetime.now(UTC),
        )
        session.add(sub)
    sub.plan_id = plano.id
    sub.plan = plano
    sub.status = status
    sub.ends_at = ends_at
    sub.overrides = dict(overrides or {})
    if notes is not None:
        sub.notes = notes
    if billing_customer_id is not None:
        sub.billing_customer_id = billing_customer_id
    session.flush()

    audit.record(
        session,
        tenant_id=tenant.id,
        action="plan.changed",
        subject_type=SubjectType.SUBSCRIPTION,
        subject_id=sub.id,
        actor_type=ActorType.USER if actor else ActorType.SYSTEM,
        actor_id=actor.id if actor else None,
        actor_label=actor.email if actor else None,
        old_state=antes["plano"] if antes else None,
        new_state=plano.code,
        payload={"antes": antes, "depois": _resumo(sub)},
    )
    return sub


def _resumo(sub: Subscription | None) -> dict | None:
    if sub is None:
        return None
    return {
        "plano": sub.plan.code if sub.plan else None,
        "status": sub.status.value,
        "ends_at": sub.ends_at.isoformat() if sub.ends_at else None,
        "overrides": dict(sub.overrides or {}),
    }


def _fmt(valor: float | int) -> str:
    numero = float(valor)
    return str(int(numero)) if numero.is_integer() else f"{numero:.2f}".replace(".", ",")
