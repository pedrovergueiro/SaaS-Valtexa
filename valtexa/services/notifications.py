"""Notificações (brief, seção 48): eventos de domínio → regras → canais.

O módulo é **desacoplado das telas**: nenhuma rota chama "mande um aviso". Quem
muda o estado publica um evento no *outbox* (``services/events.py``), na mesma
transação; o worker entrega o evento aos *handlers* registrados aqui; cada
*handler* é uma **regra** que decide o que avisar, a quem (pelas preferências) e
por quais canais. O console só lê a central.

Caminho de um aviso::

    evento (outbox) ──worker──▶ regra ──▶ destinatários (preferência) ──▶ Notification
                                                                            │
                                         worker (entregar_pendentes) ◀── NotificationDelivery
                                                  │
                                              canal (e-mail; WhatsApp/push/SMS: interface)

Garantias:

* **Idempotente.** O *outbox* entrega ao menos uma vez. Cada aviso tem uma
  ``dedup_key`` única por destinatário; reentregar o evento (ou dois workers
  pegarem o mesmo) não cria o segundo aviso — a checagem é feita antes e o banco
  confirma com a restrição única (``uq_notification_user_dedup``).
* **Entrega por worker, com novas tentativas.** O canal externo nunca roda dentro
  da requisição nem dentro da regra: a regra só grava a entrega ``pendente``;
  :func:`entregar_pendentes` envia, com espera exponencial e desistência após
  :data:`MAX_TENTATIVAS`.
* **Não finge** (seção 55). Sem ``SMTP_HOST`` a entrega por e-mail vira
  ``nao_enviado`` com o motivo — o aviso fica na central, e a tela mostra que o
  e-mail não saiu. WhatsApp, push e SMS têm a interface (:class:`Canal`) e estão
  marcados como **não implementados**: a preferência recusa escolhê-los.
"""

from __future__ import annotations

import contextlib
import logging
import smtplib
import ssl
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from typing import Protocol

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from valtexa.config import settings
from valtexa.models import (
    Device,
    Diagnosis,
    DiagnosisStatus,
    Field,
    Membership,
    Mission,
    Notification,
    NotificationDelivery,
    NotificationPreference,
    Observation,
    OutboxEvent,
    PlatformRole,
    Role,
    Tenant,
    User,
    as_utc,
)
from valtexa.services import events

logger = logging.getLogger(__name__)

CLIENTE = "cliente"
PLATAFORMA = "plataforma"

IN_APP = "in_app"
EMAIL = "email"

MAX_TENTATIVAS = 6
"""Depois disso a entrega fica ``desistiu``: o aviso continua na central."""

PRAZO_DA_TENTATIVA = timedelta(minutes=5)
"""Quanto tempo um worker segura uma entrega enquanto envia (posse por prazo)."""


# ---------------------------------------------------------------------------
# Catálogo de tipos de aviso
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Tipo:
    """Um tipo de aviso e o padrão dele (a terceira camada das preferências)."""

    kind: str
    audience: str
    label: str
    description: str
    default_roles: frozenset[str] | None
    """Papéis que recebem por padrão. ``None``: todo destinatário que a regra escolher
    (avisos dirigidos, como a resposta a um chamado que a pessoa abriu)."""
    default_channels: tuple[str, ...] = ()
    """Canais externos ligados por padrão. A central (``in_app``) vale sempre."""
    threshold: float | None = None
    threshold_unit: str | None = None


def _papeis(*papeis: Role | PlatformRole) -> frozenset[str]:
    return frozenset(p.value for p in papeis)


TIPOS: dict[str, Tipo] = {
    t.kind: t
    for t in (
        Tipo(
            "nova_infeccao", CLIENTE, "Nova infecção",
            "Doença ou praga detectada num talhão (uma vez por doença, talhão e missão/dia).",
            _papeis(Role.OWNER, Role.ADMIN, Role.AGRONOMIST), (EMAIL,),
        ),
        Tipo(
            "incidencia_alta", CLIENTE, "Incidência acima do limite",
            "Ao fim da missão, a incidência por planta passou do limite (%).",
            _papeis(Role.OWNER, Role.ADMIN, Role.AGRONOMIST), (EMAIL,),
            threshold=5.0, threshold_unit="%",
        ),
        Tipo(
            "missao_bloqueada", CLIENTE, "Missão bloqueada",
            "A camada de segurança recusou a missão (bateria, vento, geocerca...).",
            _papeis(Role.OWNER, Role.ADMIN, Role.OPERATOR),
        ),
        Tipo(
            "rover_offline", CLIENTE, "Robô sem comunicação",
            "Um robô da frota parou de falar com a plataforma.",
            _papeis(Role.OWNER, Role.ADMIN, Role.OPERATOR, Role.TECHNICIAN), (EMAIL,),
        ),
        Tipo(
            "atualizacao_falhou", CLIENTE, "Atualização falhou",
            "Uma atualização remota (OTA) falhou, foi revertida ou recusada pelo robô.",
            _papeis(Role.OWNER, Role.ADMIN, Role.TECHNICIAN),
        ),
        Tipo(
            "chamado_atualizado", CLIENTE, "Chamado de suporte",
            "Resposta, mudança de situação ou incidente ligado a um chamado que você abriu.",
            None, (EMAIL,),
        ),
        Tipo(
            "plataforma_chamado_novo", PLATAFORMA, "Chamado novo",
            "Um cliente abriu um chamado.",
            _papeis(PlatformRole.SUPERADMIN, PlatformRole.SUPORTE), (EMAIL,),
        ),
        Tipo(
            "plataforma_chamado_resposta", PLATAFORMA, "Cliente respondeu",
            "O cliente comentou num chamado (vai para o responsável, ou para o Suporte).",
            None,
        ),
        Tipo(
            "plataforma_atualizacao_falhou", PLATAFORMA, "Atualização falhou num robô",
            "Uma atualização remota (OTA) falhou, foi revertida ou recusada.",
            _papeis(PlatformRole.SUPERADMIN, PlatformRole.OPERACOES, PlatformRole.IA_DADOS),
        ),
        # Parte 7 — alertas de observabilidade (regras em services/alertas.py).
        Tipo(
            "alerta_robo", CLIENTE, "Alerta de robô",
            "Disco cheio, temperatura, sincronização parada, câmera ou modelo diferente do "
            "liberado num robô da frota (o robô sem comunicação tem aviso próprio).",
            _papeis(Role.OWNER, Role.ADMIN, Role.TECHNICIAN), (EMAIL,),
        ),
        Tipo(
            "plataforma_alerta", PLATAFORMA, "Alerta de observabilidade",
            "Um alerta disparou ou um crítico passou (API, IA, drift, worker, robô).",
            _papeis(PlatformRole.SUPERADMIN, PlatformRole.OPERACOES), (EMAIL,),
        ),
        # Parte 11 (rodada 3) — validação do Rover.
        Tipo(
            "plataforma_ensaio_regressao", PLATAFORMA, "Regressão em ensaio do Rover",
            "Um ensaio de validação que estava aprovado reprovou no mesmo robô.",
            _papeis(PlatformRole.SUPERADMIN, PlatformRole.OPERACOES), (EMAIL,),
        ),
    )
}


def tipos_de(audience: str) -> list[Tipo]:
    return [t for t in TIPOS.values() if t.audience == audience]


# ---------------------------------------------------------------------------
# Canais
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Resultado:
    status: str
    """``enviado``, ``nao_enviado`` (final, sem envio), ``erro`` (tenta de novo) ou
    ``recusado`` (o servidor recusou o destinatário: não adianta repetir)."""
    detail: str | None = None


class Canal(Protocol):
    """O que um canal externo precisa implementar. WhatsApp, push e SMS entram aqui."""

    nome: str
    rotulo: str
    implementado: bool

    def configurado(self) -> bool: ...

    def destino(self, user: User) -> str | None:
        """Para onde mandar (e-mail, telefone, token do aparelho)."""

    def enviar(self, destino: str, assunto: str, texto: str) -> Resultado: ...


class CanalEmail:
    nome = EMAIL
    rotulo = "E-mail"
    implementado = True

    def configurado(self) -> bool:
        return bool(settings.smtp_host)

    def destino(self, user: User) -> str | None:
        return user.email or None

    def enviar(self, destino: str, assunto: str, texto: str) -> Resultado:
        if not self.configurado():
            return Resultado(
                "nao_enviado",
                "SMTP não configurado (SMTP_HOST vazio): o aviso ficou só na central.",
            )
        mensagem = EmailMessage()
        mensagem["From"] = settings.smtp_from
        mensagem["To"] = destino
        mensagem["Subject"] = assunto
        mensagem.set_content(texto)
        try:
            classe = smtplib.SMTP_SSL if settings.smtp_ssl else smtplib.SMTP
            with classe(
                settings.smtp_host, settings.smtp_port, timeout=settings.smtp_timeout_seconds
            ) as smtp:
                if not settings.smtp_ssl and settings.smtp_starttls:
                    smtp.starttls(context=ssl.create_default_context())
                if settings.smtp_user:
                    smtp.login(settings.smtp_user, settings.smtp_password or "")
                smtp.send_message(mensagem)
        except smtplib.SMTPRecipientsRefused as exc:
            return Resultado("recusado", f"Destinatário recusado pelo servidor: {exc}")
        except (smtplib.SMTPException, OSError) as exc:
            return Resultado("erro", f"{type(exc).__name__}: {exc}")
        return Resultado("enviado")


@dataclass
class CanalNaoImplementado:
    """Canal previsto (seção 48) e ainda sem integração: existe para a interface."""

    nome: str
    rotulo: str
    implementado: bool = False

    def configurado(self) -> bool:
        return False

    def destino(self, user: User) -> str | None:
        return None  # telefone e token de aparelho ainda não existem no cadastro

    def enviar(self, destino: str, assunto: str, texto: str) -> Resultado:
        return Resultado("nao_enviado", f"Canal {self.rotulo} ainda não implementado.")


CANAIS: dict[str, Canal] = {
    EMAIL: CanalEmail(),
    "whatsapp": CanalNaoImplementado("whatsapp", "WhatsApp"),
    "push": CanalNaoImplementado("push", "Push no celular"),
    "sms": CanalNaoImplementado("sms", "SMS"),
}


def canais_disponiveis() -> list[dict]:
    """Para a tela de preferências: o que existe, o que funciona e o que está ligado."""
    saida = [{"name": IN_APP, "label": "Central do console", "implemented": True,
              "configured": True}]
    for canal in CANAIS.values():
        saida.append({"name": canal.nome, "label": canal.rotulo,
                      "implemented": canal.implementado, "configured": canal.configurado()})
    return saida


# ---------------------------------------------------------------------------
# Preferências
# ---------------------------------------------------------------------------


class PreferenceError(ValueError):
    """Preferência inválida. Vira 422 na API."""


@dataclass(frozen=True)
class Efetiva:
    kind: str
    enabled: bool
    channels: tuple[str, ...]
    threshold: float | None
    source: str
    """``pessoa``, ``papel`` ou ``padrao`` — de onde veio a regra que vale."""


def _escopo(tenant_id: str | None, user_id: str | None, role: str | None, kind: str) -> str:
    return f"{tenant_id or '-'}:{user_id or '-'}:{role or '-'}:{kind}"


def _padrao(tipo: Tipo, role: str | None) -> Efetiva:
    ligado = tipo.default_roles is None or (role is not None and role in tipo.default_roles)
    return Efetiva(tipo.kind, ligado, tipo.default_channels if ligado else (),
                   tipo.threshold, "padrao")


def _de_linha(linha: NotificationPreference, fonte: str, tipo: Tipo) -> Efetiva:
    limite = linha.threshold if linha.threshold is not None else tipo.threshold
    return Efetiva(linha.kind, linha.enabled, tuple(linha.channels or ()), limite, fonte)


@dataclass
class _Regras:
    """As preferências de um tipo num escopo, carregadas uma vez por aviso."""

    tipo: Tipo
    por_pessoa: dict[str, NotificationPreference] = field(default_factory=dict)
    por_papel: dict[str, NotificationPreference] = field(default_factory=dict)

    def para(self, user_id: str, role: str | None) -> Efetiva:
        if user_id in self.por_pessoa:
            return _de_linha(self.por_pessoa[user_id], "pessoa", self.tipo)
        if role is not None and role in self.por_papel:
            return _de_linha(self.por_papel[role], "papel", self.tipo)
        return _padrao(self.tipo, role)


def _carregar_regras(session: Session, tipo: Tipo, tenant_id: str | None) -> _Regras:
    regras = _Regras(tipo)
    linhas = session.scalars(select(NotificationPreference).where(
        NotificationPreference.kind == tipo.kind,
        NotificationPreference.tenant_id.is_(None) if tenant_id is None
        else NotificationPreference.tenant_id == tenant_id,
    ))
    for linha in linhas:
        if linha.user_id is not None:
            regras.por_pessoa[linha.user_id] = linha
        elif linha.role is not None:
            regras.por_papel[linha.role] = linha
    return regras


def _escopo_do_tipo(tipo: Tipo, tenant_id: str | None) -> str | None:
    """Preferência da equipe não depende de cliente: o escopo dela é sem cliente."""
    return None if tipo.audience == PLATAFORMA else tenant_id


def preferencias(session: Session, *, user_id: str, role: str | None, audience: str,
                 tenant_id: str | None) -> list[tuple[Tipo, Efetiva]]:
    """As preferências que valem para a pessoa, tipo a tipo, com a origem de cada uma."""
    return [
        (tipo, _carregar_regras(session, tipo, _escopo_do_tipo(tipo, tenant_id))
         .para(user_id, role))
        for tipo in tipos_de(audience)
    ]


def preferencias_do_papel(session: Session, *, role: str, audience: str,
                          tenant_id: str | None) -> list[tuple[Tipo, Efetiva]]:
    saida = []
    for tipo in tipos_de(audience):
        regras = _carregar_regras(session, tipo, _escopo_do_tipo(tipo, tenant_id))
        linha = regras.por_papel.get(role)
        saida.append((tipo, _de_linha(linha, "papel", tipo) if linha else _padrao(tipo, role)))
    return saida


def _valida(kind: str, audience: str, channels: Iterable[str],
            threshold: float | None) -> tuple[Tipo, list[str]]:
    tipo = TIPOS.get(kind)
    if tipo is None or tipo.audience != audience:
        raise PreferenceError(f"Tipo de aviso desconhecido aqui: {kind!r}.")
    escolhidos = []
    for nome in channels:
        if nome == IN_APP:
            continue  # a central vale sempre que o tipo está ligado
        canal = CANAIS.get(nome)
        if canal is None:
            raise PreferenceError(f"Canal desconhecido: {nome!r}.")
        if not canal.implementado:
            raise PreferenceError(f"O canal {canal.rotulo} ainda não está implementado.")
        if nome not in escolhidos:
            escolhidos.append(nome)
    if threshold is not None and tipo.threshold is None:
        raise PreferenceError(f"O aviso {tipo.label!r} não tem limite.")
    if threshold is not None and not 0 <= threshold <= 100:
        raise PreferenceError("O limite vai de 0 a 100 (%).")
    return tipo, escolhidos


def salvar_preferencia(
    session: Session, *, audience: str, tenant_id: str | None, user_id: str | None,
    role: str | None, kind: str, enabled: bool, channels: Iterable[str],
    threshold: float | None, by: User,
) -> NotificationPreference:
    """Grava (ou troca) a preferência da pessoa ou do papel. Não faz *commit*."""
    tipo, escolhidos = _valida(kind, audience, channels, threshold)
    escopo_tenant = _escopo_do_tipo(tipo, tenant_id)
    chave = _escopo(escopo_tenant, user_id, None if user_id else role, kind)
    linha = session.scalars(
        select(NotificationPreference).where(NotificationPreference.scope_key == chave)
    ).first()
    if linha is None:
        linha = NotificationPreference(
            scope_key=chave, tenant_id=escopo_tenant, user_id=user_id,
            role=None if user_id else role, kind=kind,
        )
        session.add(linha)
    linha.enabled = enabled
    linha.channels = escolhidos
    linha.threshold = threshold
    linha.updated_by = by.id
    return linha


def remover_preferencia(session: Session, *, audience: str, tenant_id: str | None,
                        user_id: str | None, role: str | None, kind: str) -> bool:
    """Volta ao padrão (do papel, ou do código). Devolve se havia algo a remover."""
    tipo = TIPOS.get(kind)
    if tipo is None or tipo.audience != audience:
        raise PreferenceError(f"Tipo de aviso desconhecido aqui: {kind!r}.")
    chave = _escopo(_escopo_do_tipo(tipo, tenant_id), user_id, None if user_id else role, kind)
    linha = session.scalars(
        select(NotificationPreference).where(NotificationPreference.scope_key == chave)
    ).first()
    if linha is None:
        return False
    session.delete(linha)
    return True


# ---------------------------------------------------------------------------
# Criar avisos (o núcleo que as regras chamam)
# ---------------------------------------------------------------------------


@dataclass
class Aviso:
    """O que uma regra quer avisar. Quem recebe sai das preferências."""

    kind: str
    tenant_id: str | None
    title: str
    body: str
    dedup: str
    severity: str = "info"
    subject_type: str | None = None
    subject_id: str | None = None
    link: str | None = None
    valor: float | None = None
    """Comparado ao limite da pessoa, quando o tipo tem limite."""
    para: list[str] | None = None
    """Destinatários dirigidos (ids de usuário). ``None``: todos os candidatos."""


def _candidatos(session: Session, aviso: Aviso, tipo: Tipo) -> list[tuple[User, str | None]]:
    """(pessoa, papel) de quem pode receber o aviso — nunca alguém de fora do escopo."""
    if tipo.audience == CLIENTE:
        if aviso.tenant_id is None:
            return []
        consulta = (
            select(User, Membership.role)
            .join(Membership, Membership.user_id == User.id)
            .where(Membership.tenant_id == aviso.tenant_id, User.is_active.is_(True))
        )
        linhas = [(u, r.value) for u, r in session.execute(consulta)]
    else:
        consulta = select(User).where(User.platform_role.is_not(None), User.is_active.is_(True))
        linhas = [(u, u.platform_role.value) for u in session.scalars(consulta)]
    if aviso.para is not None:
        alvo = set(aviso.para)
        linhas = [(u, r) for u, r in linhas if u.id in alvo]
    return linhas


def notificar(session: Session, aviso: Aviso, *, event_id: str | None = None) -> list[Notification]:
    """Cria o aviso para cada destinatário que o quer. Idempotente pela ``dedup``.

    Não faz *commit*: participa da transação de quem chamou (a entrega do evento).
    """
    tipo = TIPOS[aviso.kind]
    regras = _carregar_regras(session, tipo, _escopo_do_tipo(tipo, aviso.tenant_id))
    criados: list[Notification] = []
    agora = datetime.now(UTC)
    for user, role in _candidatos(session, aviso, tipo):
        efetiva = regras.para(user.id, role)
        if not efetiva.enabled:
            continue
        if efetiva.threshold is not None and aviso.valor is not None \
                and aviso.valor < efetiva.threshold:
            continue
        ja = session.scalar(select(Notification.id).where(
            Notification.user_id == user.id, Notification.dedup_key == aviso.dedup))
        if ja is not None:
            continue
        aviso_db = Notification(
            tenant_id=aviso.tenant_id, user_id=user.id, audience=tipo.audience,
            kind=aviso.kind, severity=aviso.severity, title=aviso.title[:200],
            body=aviso.body, subject_type=aviso.subject_type, subject_id=aviso.subject_id,
            link=aviso.link, event_id=event_id, dedup_key=aviso.dedup[:160], created_at=agora,
        )
        try:
            # Savepoint: dois workers com o mesmo evento — o segundo bate na
            # restrição única e segue, sem derrubar a entrega dos outros avisos.
            with session.begin_nested():
                session.add(aviso_db)
                session.flush()
        except IntegrityError:
            continue
        for nome in efetiva.channels:
            canal = CANAIS.get(nome)
            if canal is None:
                continue
            session.add(NotificationDelivery(
                notification_id=aviso_db.id, channel=nome, destination=canal.destino(user),
                status="pendente", attempts=0, next_attempt_at=agora,
            ))
        criados.append(aviso_db)
    return criados


# ---------------------------------------------------------------------------
# Entrega pelos canais externos (worker)
# ---------------------------------------------------------------------------


def _espera(tentativas: int) -> timedelta:
    return timedelta(seconds=min(60 * 2 ** max(tentativas - 1, 0), 3600))


def _texto(aviso: Notification) -> str:
    linhas = [aviso.title, "", aviso.body]
    if aviso.link and settings.console_url:
        linhas += ["", f"Abrir no console: {settings.console_url.rstrip('/')}{aviso.link}"]
    linhas += ["", "—", "ValTexa. Você recebe este aviso pelas suas preferências de "
               "notificação (Configurações > Notificações no console)."]
    return "\n".join(linhas)


def entregar_pendentes(session: Session, limite: int = 50,
                       agora: datetime | None = None) -> int:
    """Envia as entregas vencidas. Devolve quantas saíram de verdade (``enviado``).

    Cada entrega é reivindicada com *compare-and-set* (``attempts`` e ``status``
    lidos), que já empurra ``next_attempt_at`` para a frente: outro worker não a
    pega enquanto esta envia. Um processo que morra no meio devolve a entrega
    quando o prazo vence — o e-mail pode sair duas vezes nesse caso raro (entrega
    ao menos uma vez), nunca zero.
    """
    agora = agora or datetime.now(UTC)
    vencidas = list(session.scalars(
        select(NotificationDelivery)
        .where(NotificationDelivery.status.in_(("pendente", "falhou")),
               NotificationDelivery.next_attempt_at <= agora)
        .order_by(NotificationDelivery.next_attempt_at)
        .limit(limite)
    ))
    enviados = 0
    for entrega in vencidas:
        reivindicada = session.execute(
            update(NotificationDelivery)
            .where(NotificationDelivery.id == entrega.id,
                   NotificationDelivery.status == entrega.status,
                   NotificationDelivery.attempts == entrega.attempts)
            .values(attempts=entrega.attempts + 1, next_attempt_at=agora + PRAZO_DA_TENTATIVA)
            .execution_options(synchronize_session=False)
        )
        if reivindicada.rowcount != 1:
            session.rollback()
            continue
        session.commit()
        session.refresh(entrega)

        aviso = session.get(Notification, entrega.notification_id)
        canal = CANAIS.get(entrega.channel)
        if canal is None or aviso is None:
            resultado = Resultado("nao_enviado", "Canal ou aviso inexistente.")
        elif not entrega.destination:
            resultado = Resultado("nao_enviado", "A pessoa não tem destino para este canal.")
        else:
            try:
                resultado = canal.enviar(entrega.destination, f"[ValTexa] {aviso.title}",
                                         _texto(aviso))
            except Exception as exc:  # um canal com defeito não derruba o worker
                logger.exception("Canal %s falhou", entrega.channel)
                resultado = Resultado("erro", f"{type(exc).__name__}: {exc}")

        if resultado.status == "enviado":
            entrega.status, entrega.sent_at, entrega.last_error = "enviado", agora, None
            entrega.next_attempt_at = None
            enviados += 1
        elif resultado.status == "nao_enviado":
            entrega.status, entrega.last_error, entrega.next_attempt_at = (
                "nao_enviado", resultado.detail, None)
        elif resultado.status == "recusado" or entrega.attempts >= MAX_TENTATIVAS:
            entrega.status, entrega.last_error, entrega.next_attempt_at = (
                "desistiu", resultado.detail, None)
        else:
            entrega.status, entrega.last_error = "falhou", resultado.detail
            entrega.next_attempt_at = agora + _espera(entrega.attempts)
        session.commit()
    return enviados


# ---------------------------------------------------------------------------
# Central (leitura e marcação)
# ---------------------------------------------------------------------------


def _da_caixa(user_id: str, audience: str, tenant_id: str | None):
    condicoes = [Notification.user_id == user_id, Notification.audience == audience]
    if audience == CLIENTE:
        condicoes.append(Notification.tenant_id == tenant_id)
    return condicoes


def caixa(session: Session, *, user_id: str, audience: str, tenant_id: str | None,
          only_unread: bool = False, limit: int = 50) -> list[Notification]:
    consulta = select(Notification).where(*_da_caixa(user_id, audience, tenant_id))
    if only_unread:
        consulta = consulta.where(Notification.read_at.is_(None))
    consulta = consulta.order_by(Notification.created_at.desc(), Notification.id).limit(limit)
    return list(session.scalars(consulta))


def nao_lidas(session: Session, *, user_id: str, audience: str, tenant_id: str | None) -> int:
    return session.scalar(
        select(func.count()).select_from(Notification)
        .where(*_da_caixa(user_id, audience, tenant_id), Notification.read_at.is_(None))
    ) or 0


def da_pessoa(session: Session, notification_id: str, *, user_id: str, audience: str,
              tenant_id: str | None) -> Notification | None:
    """O aviso, se ele é desta pessoa nesta caixa; senão ``None`` (vira 404)."""
    aviso = session.get(Notification, notification_id)
    if aviso is None or aviso.user_id != user_id or aviso.audience != audience:
        return None
    if audience == CLIENTE and aviso.tenant_id != tenant_id:
        return None
    return aviso


def marcar_todas(session: Session, *, user_id: str, audience: str,
                 tenant_id: str | None) -> int:
    resultado = session.execute(
        update(Notification)
        .where(*_da_caixa(user_id, audience, tenant_id), Notification.read_at.is_(None))
        .values(read_at=datetime.now(UTC))
        .execution_options(synchronize_session=False)
    )
    return resultado.rowcount or 0


def entregas_de(session: Session, ids: list[str]) -> dict[str, list[NotificationDelivery]]:
    saida: dict[str, list[NotificationDelivery]] = {i: [] for i in ids}
    if not ids:
        return saida
    for entrega in session.scalars(select(NotificationDelivery).where(
            NotificationDelivery.notification_id.in_(ids))):
        saida[entrega.notification_id].append(entrega)
    return saida


# ---------------------------------------------------------------------------
# Regras: evento de domínio → aviso
# ---------------------------------------------------------------------------

Regra = Callable[[Session, OutboxEvent], list[Aviso]]
REGRAS: dict[str, list[Regra]] = {}


def regra(*nomes: str) -> Callable[[Regra], Regra]:
    """Registra uma regra para eventos e liga o *handler* do outbox (uma vez por nome)."""

    def registrar(funcao: Regra) -> Regra:
        for nome in nomes:
            if nome not in REGRAS:
                REGRAS[nome] = []
                events.subscribe(nome, _handler)
            REGRAS[nome].append(funcao)
        return funcao

    return registrar


def _handler(session: Session, event: OutboxEvent) -> None:
    for funcao in REGRAS.get(event.name, ()):
        for aviso in funcao(session, event):
            notificar(session, aviso, event_id=event.id)


def _nome_do_talhao(session: Session, field_id: str | None) -> str:
    talhao = session.get(Field, field_id) if field_id else None
    return talhao.name if talhao else "sem talhão"


@regra(events.DIAGNOSIS_CREATED)
def _nova_infeccao(session: Session, event: OutboxEvent) -> list[Aviso]:
    from valtexa.services.ai_pipeline import HEALTHY_LABELS  # só leitura da constante

    diag = session.get(Diagnosis, event.subject_id) if event.subject_id else None
    if diag is None or not diag.label or diag.label in HEALTHY_LABELS:
        return []
    if diag.status in (DiagnosisStatus.INCONCLUSIVE, DiagnosisStatus.HUMAN_REJECTED):
        return []
    obs = session.get(Observation, diag.observation_id)
    quando = (obs.mission_id if obs and obs.mission_id
              else (as_utc(obs.captured_at).date().isoformat() if obs else "?"))
    talhao = _nome_do_talhao(session, diag.field_id)
    revisar = diag.status is DiagnosisStatus.NEEDS_REVIEW
    confianca = f" (confiança {diag.confidence:.0%})" if diag.confidence is not None else ""
    corpo = f"A IA encontrou sinais de {diag.label} no talhão {talhao}{confianca}."
    if revisar:
        corpo += " O diagnóstico aguarda a revisão do agrônomo."
    if obs is not None and obs.plant_ref:
        corpo += f" Planta {obs.plant_ref}."
    return [Aviso(
        kind="nova_infeccao", tenant_id=diag.tenant_id,
        title=f"{diag.label} detectada no talhão {talhao}", body=corpo,
        dedup=f"nova_infeccao:{diag.field_id}:{diag.label}:{quando}", severity="aviso",
        subject_type="diagnosis", subject_id=diag.id,
        link=f"/missoes/{obs.mission_id}" if obs and obs.mission_id else "/revisao",
    )]


@regra(events.MISSION_COMPLETED)
def _incidencia_alta(session: Session, event: OutboxEvent) -> list[Aviso]:
    from valtexa.services import missao_resultado  # só leitura (plantas da missão)

    missao = session.get(Mission, event.subject_id) if event.subject_id else None
    if missao is None:
        return []
    resultado = missao_resultado.plantas_da_missao(session, missao.tenant_id, missao.id)
    incidencia = resultado["incidence"]
    if incidencia["ratio"] is None:
        return []  # missão sem plantas identificadas: não há incidência por planta
    valor = round(incidencia["ratio"] * 100, 1)
    baixo, alto = incidencia["interval_95"]
    por_doenca = ", ".join(f"{k}: {v}" for k, v in sorted(incidencia["by_label"].items()))
    talhao = _nome_do_talhao(session, missao.field_id)
    return [Aviso(
        kind="incidencia_alta", tenant_id=missao.tenant_id,
        title=f"Incidência de {valor:.1f}% no talhão {talhao}",
        body=(f"{incidencia['diseased']} de {resultado['plants_seen']} plantas com doença "
              f"confirmada na missão (IC 95%: {baixo * 100:.1f}% a {alto * 100:.1f}%)."
              + (f" Por doença: {por_doenca}." if por_doenca else "")),
        dedup=f"incidencia_alta:{missao.id}", severity="aviso", valor=valor,
        subject_type="mission", subject_id=missao.id, link=f"/missoes/{missao.id}",
    )]


@regra(events.SAFETY_BLOCKED)
def _missao_bloqueada(session: Session, event: OutboxEvent) -> list[Aviso]:
    missao = session.get(Mission, event.subject_id) if event.subject_id else None
    if missao is None:
        return []
    motivo = (event.payload or {}).get("reason") or "motivo não informado"
    talhao = _nome_do_talhao(session, missao.field_id)
    return [Aviso(
        kind="missao_bloqueada", tenant_id=missao.tenant_id,
        title=f"Missão bloqueada no talhão {talhao}",
        body=f"A camada de segurança não autorizou a missão: {motivo}",
        dedup=f"missao_bloqueada:{event.id}", severity="aviso",
        subject_type="mission", subject_id=missao.id, link=f"/missoes/{missao.id}",
    )]


@regra(events.DEVICE_OFFLINE)
def _rover_offline(session: Session, event: OutboxEvent) -> list[Aviso]:
    robo = session.get(Device, event.subject_id) if event.subject_id else None
    if robo is None:
        return []
    visto = (event.payload or {}).get("last_seen_at")
    if visto:
        with contextlib.suppress(ValueError):  # se não for data, fica o texto como veio
            visto = f"{as_utc(datetime.fromisoformat(visto)):%d/%m/%Y %H:%M} UTC"
    return [Aviso(
        kind="rover_offline", tenant_id=robo.tenant_id,
        title=f"{robo.name} ({robo.serial_number}) está sem comunicação",
        body=(f"Último contato: {visto}." if visto else "Sem contato registrado.")
        + " Se havia missão em andamento, o robô continua offline e sincroniza ao voltar.",
        dedup=f"rover_offline:{event.id}", severity="critico",
        subject_type="device", subject_id=robo.id, link=f"/frota/{robo.id}",
    )]


@regra(events.OTA_FAILED)
def _atualizacao_falhou(session: Session, event: OutboxEvent) -> list[Aviso]:
    robo = session.get(Device, event.subject_id) if event.subject_id else None
    if robo is None:
        return []
    dados = event.payload or {}
    estado = {"falhou": "falhou", "revertida": "foi revertida",
              "recusada": "foi recusada"}.get(dados.get("state"), "falhou")
    pacote = f"{dados.get('kind') or 'pacote'} {dados.get('version') or ''}".strip()
    corpo = f"A atualização {pacote} {estado} no robô {robo.name} ({robo.serial_number})."
    if dados.get("detail"):
        corpo += f" Detalhe do robô: {dados['detail']}"
    corpo += " O robô segue na versão anterior."
    tenant = session.get(Tenant, robo.tenant_id)
    chave = f"atualizacao_falhou:{dados.get('deployment_id') or event.id}"
    titulo = f"Atualização {estado} no robô {robo.name}"
    return [
        Aviso(kind="atualizacao_falhou", tenant_id=robo.tenant_id, title=titulo, body=corpo,
              dedup=chave, severity="aviso", subject_type="device", subject_id=robo.id,
              link=f"/frota/{robo.id}"),
        Aviso(kind="plataforma_atualizacao_falhou", tenant_id=robo.tenant_id,
              title=f"{titulo} ({tenant.name if tenant else 'cliente'})", body=corpo,
              dedup=f"plataforma:{chave}", severity="aviso", subject_type="device",
              subject_id=robo.id, link="/plataforma/atualizacoes"),
    ]


@regra(events.ENSAIO_REGRESSAO)
def _ensaio_regressao(session: Session, event: OutboxEvent) -> list[Aviso]:
    robo = session.get(Device, event.subject_id) if event.subject_id else None
    if robo is None:
        return []
    dados = event.payload or {}
    ensaio = dados.get("ensaio") or "ensaio"
    falhos = ", ".join(dados.get("criterios") or []) or "critérios"
    simulado = " (simulado)" if dados.get("simulado") else ""
    corpo = (f"O ensaio {ensaio}{simulado} do robô {robo.name} ({robo.serial_number}) estava "
             f"aprovado e reprovou agora em: {falhos}. O portão da fase volta a ficar fechado "
             "até um novo resultado aprovado.")
    return [Aviso(kind="plataforma_ensaio_regressao", tenant_id=robo.tenant_id,
                  title=f"Regressão no ensaio {ensaio} do robô {robo.name}", body=corpo,
                  dedup=f"ensaio_regressao:{dados.get('resultado_id') or event.id}",
                  severity="aviso", subject_type="device", subject_id=robo.id,
                  link=f"/plataforma/comando/{robo.id}")]


__all__ = [
    "CANAIS",
    "CLIENTE",
    "EMAIL",
    "IN_APP",
    "MAX_TENTATIVAS",
    "PLATAFORMA",
    "TIPOS",
    "Aviso",
    "Canal",
    "CanalEmail",
    "CanalNaoImplementado",
    "Efetiva",
    "PreferenceError",
    "Resultado",
    "Tipo",
    "caixa",
    "canais_disponiveis",
    "da_pessoa",
    "entregar_pendentes",
    "entregas_de",
    "marcar_todas",
    "nao_lidas",
    "notificar",
    "preferencias",
    "preferencias_do_papel",
    "regra",
    "remover_preferencia",
    "salvar_preferencia",
    "tipos_de",
]
