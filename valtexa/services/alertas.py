"""Alertas (brief, seção 35): regras configuráveis, avaliadas pelo worker, com estado.

Ciclo de um alerta::

    regra (limite, janela) ──worker──▶ violação? ──sim, sem alerta aberto──▶ DISPARADO
                                          │                                    │ alguém vê
                                          │                                    ▼
                                          └──não, com alerta aberto──▶ RESOLVIDO ◀── RECONHECIDO

* **Uma regra por tipo**, com padrão no código (:data:`REGRAS`) e linha no banco
  (``alert_rule``) que a equipe ajusta: limite, janela, severidade, ligada. Regras
  **de robô** aceitam versão por cliente (o gestor muda o limite de disco dos robôs
  dele); regras **da plataforma** (API, IA, *drift*, eventos) não.
* **Um alerta aberto por (tipo, assunto)**: ``open_key`` único no banco — dois
  workers avaliando ao mesmo tempo não disparam duas vezes. A violação que continua
  só atualiza valor e ``last_seen_at``; a que passa **resolve** sozinha.
* **Entrega pelas notificações** (Parte 6): disparar publica ``alert.fired`` no
  *outbox*, na mesma transação; a regra de aviso daqui decide quem recebe — o
  cliente dono do robô (``alerta_robo``) e a equipe (``plataforma_alerta``). O robô
  sem comunicação o cliente **já** recebe pelo aviso ``rover_offline`` (Parte 6):
  o alerta não repete esse aviso para ele.
* Nada é inventado: regra cujo dado não existe (robô que não manda CPU, IA
  desligada) simplesmente não dispara — e a tela diz "não medido".
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from valtexa.models import (
    ActorType,
    Alert,
    AlertRule,
    Detection,
    Device,
    DeviceStatus,
    OutboxEvent,
    SubjectType,
    Tenant,
    User,
    as_utc,
)
from valtexa.models.enums import DetectionSource, DeviceKind
from valtexa.services import audit, events, model_registry, observabilidade, saude_rover
from valtexa.services import notifications as avisos

logger = logging.getLogger(__name__)

ROBO = "robo"
PLATAFORMA = "plataforma"
SO_DA_EQUIPE = frozenset({"rover_offline"})
"""Regras de robô sem versão por cliente: o aviso delas vai só para a equipe."""


@dataclass(frozen=True)
class Violacao:
    subject_type: str
    subject_id: str
    label: str
    tenant_id: str | None
    value: float | None
    message: str


@dataclass(frozen=True)
class Efetiva:
    """A regra que vale (a do cliente, se houver; senão a padrão)."""

    rule: AlertRule
    threshold: float | None
    window_minutes: int | None
    severity: str


Avaliador = Callable[[Session, "RegraDef", Efetiva | None, datetime, dict], Iterator[Violacao]]


@dataclass(frozen=True)
class RegraDef:
    kind: str
    scope: str
    label: str
    description: str
    threshold: float | None
    unit: str | None
    window_minutes: int | None
    severity: str
    avaliar: Avaliador


# ---------------------------------------------------------------------------
# Avaliadores — robôs
# ---------------------------------------------------------------------------


def _robos(session: Session, tenant_id: str | None = None) -> list[Device]:
    consulta = select(Device).where(Device.status == DeviceStatus.ACTIVE)
    if tenant_id:
        consulta = consulta.where(Device.tenant_id == tenant_id)
    return list(session.scalars(consulta.order_by(Device.id)))


def _rotulo(d: Device) -> str:
    return f"{d.name} ({d.serial_number})"


def _por_robo(session: Session, regra: RegraDef, ctx: dict,
              medir: Callable[[Device, Efetiva, datetime], tuple[float | None, str] | None],
              agora: datetime) -> Iterator[Violacao]:
    """Para cada robô ativo, com a regra efetiva do cliente dele."""
    if "robos" not in ctx:
        ctx["robos"] = _robos(session)
    for d in ctx["robos"]:
        efetiva = efetiva_para(session, regra.kind, d.tenant_id, ctx)
        if efetiva is None:
            continue
        medida = medir(d, efetiva, agora)
        if medida is not None:
            valor, mensagem = medida
            yield Violacao("device", d.id, _rotulo(d), d.tenant_id, valor, mensagem)


def _offline(session, regra, _e, agora, ctx):
    def medir(d: Device, e: Efetiva, agora: datetime):
        if d.model is not None and d.model.kind == DeviceKind.GATEWAY:
            return None  # a base tem a regra dela (base_sem_contato), com o prazo dela
        visto = as_utc(d.last_seen_at)
        if visto is None:
            return None  # nunca falou: provisionado e ainda não ligado — não é queda
        minutos = (agora - visto).total_seconds() / 60
        if minutos < (e.threshold or 0):
            return None
        return round(minutos, 1), (f"Sem comunicação há {minutos:.0f} min "
                                   f"(último contato {visto:%d/%m %H:%M} UTC).")
    return _por_robo(session, regra, ctx, medir, agora)


def _disco(session, regra, _e, agora, ctx):
    def medir(d: Device, e: Efetiva, _agora):
        pct = saude_rover.disco_percentual(d)
        if pct is None or pct < (e.threshold or 0):
            return None
        return pct, f"Disco local em {pct:.1f}% (limite {e.threshold:.0f}%)."
    return _por_robo(session, regra, ctx, medir, agora)


def _temperatura(session, regra, _e, agora, ctx):
    def medir(d: Device, e: Efetiva, _agora):
        temp = (d.health or {}).get("temperature_c")
        temp = temp if temp is not None else d.temperature_c
        if temp is None or temp < (e.threshold or 0):
            return None
        return temp, f"Temperatura interna de {temp:.1f} °C (limite {e.threshold:.0f} °C)."
    return _por_robo(session, regra, ctx, medir, agora)


def _sync_parada(session, regra, _e, agora, ctx):
    """Fila do robô parada: tem pendência, está falando com a plataforma e não esvazia."""
    def medir(d: Device, e: Efetiva, agora: datetime):
        saude = (d.health or {}).get("sync") or {}
        if saude.get("blocked"):
            return None, "Sincronização travada pelo robô (precisa de intervenção)."
        pendente = max(d.sync_pending or 0, saude.get("pending") or 0)
        if pendente <= 0 or d.connectivity.value == "offline":
            return None  # sem rede é offline-first, não fila parada
        idade = saude.get("oldest_pending_s")
        if idade is None:
            ultimo = as_utc(d.last_sync_at)
            if ultimo is None:
                return None
            idade = (agora - ultimo).total_seconds()
        minutos = idade / 60
        if minutos < (e.threshold or 0):
            return None
        return round(minutos, 1), (f"{pendente} registro(s) esperando há {minutos:.0f} min "
                                   "com o robô conectado.")
    return _por_robo(session, regra, ctx, medir, agora)


def _camera(session, regra, _e, agora, ctx):
    def medir(d: Device, _e: Efetiva, _agora):
        cameras = (d.health or {}).get("cameras") or []
        ruins = [c for c in cameras if not c.get("ok")]
        if not ruins:
            return None
        nomes = ", ".join(f"{c['id']}" + (f" ({c['detail']})" if c.get("detail") else "")
                          for c in ruins)
        return float(len(ruins)), f"Câmera sem responder: {nomes}."
    return _por_robo(session, regra, ctx, medir, agora)


def _modelo_divergente(session, regra, _e, agora, ctx):
    cache: dict = {}

    def medir(d: Device, _e: Efetiva, _agora):
        etiquetas = {x.etiqueta for x in model_registry.designados(session, d, cache=cache)
                     if x.etiqueta}
        situacao = model_registry.situacao_do_modelo(session, d, etiquetas)
        if situacao not in ("divergente", "fora_do_registry"):
            return None
        roda = f"{d.ai_model_key}@{d.ai_model_version}"
        liberado = ", ".join(sorted(etiquetas)) or "nenhum"
        texto = ("fora do registry" if situacao == "fora_do_registry"
                 else f"diferente do liberado ({liberado})")
        return None, f"O robô roda {roda}, {texto}."
    return _por_robo(session, regra, ctx, medir, agora)


# ---------------------------------------------------------------------------
# Avaliadores — plataforma
# ---------------------------------------------------------------------------

API_MIN_REQUISICOES = 20
"""Abaixo disso a taxa de erro não diz nada (2 erros em 3 requisições = 67 %)."""


# ---------------------------------------------------------------------------
# Avaliadores — base da fazenda (services/estacao_base.py)
# ---------------------------------------------------------------------------


def _por_base(session: Session, regra: RegraDef, ctx: dict,
              medir: Callable[[Device, dict, Efetiva, datetime], tuple[float | None, str] | None],
              agora: datetime) -> Iterator[Violacao]:
    """Para cada base ativa (``gateway``), com o retrato que ela mandou."""
    from valtexa.services import estacao_base

    if "bases" not in ctx:
        ctx["bases"] = estacao_base.bases(session)
    for d in ctx["bases"]:
        efetiva = efetiva_para(session, regra.kind, d.tenant_id, ctx)
        if efetiva is None:
            continue
        medida = medir(d, estacao_base.retrato(d), efetiva, agora)
        if medida is not None:
            valor, mensagem = medida
            yield Violacao("device", d.id, _rotulo(d), d.tenant_id, valor, mensagem)


def _base_sem_contato(session, regra, _e, agora, ctx):
    """A base só fala com a nuvem pela Starlink: calada é internet fora ou base sem energia."""
    def medir(d: Device, _r: dict, e: Efetiva, agora: datetime):
        visto = as_utc(d.last_seen_at)
        if visto is None:
            return None
        minutos = (agora - visto).total_seconds() / 60
        if minutos < (e.threshold or 0):
            return None
        return round(minutos, 1), (f"Base sem contato há {minutos:.0f} min: Starlink fora ou "
                                   "base sem energia. Os Rovers guardam tudo na fila deles.")
    return _por_base(session, regra, ctx, medir, agora)


def _enlace_degradado(session, regra, _e, agora, ctx):
    def medir(_d: Device, r: dict, e: Efetiva, _agora):
        ruins = []
        for rover in r.get("rovers") or []:
            if rover.get("em_travessia"):
                continue  # zona morta mapeada: o Rover avisou e sincroniza na volta
            if not rover.get("vivo"):
                ruins.append(f"{rover['serial']} sem nenhum rádio")
                continue
            vivos = [x for x in rover.get("enlaces") or [] if x.get("estado") != "morto"]
            perda = min((x.get("perda") or 0.0 for x in vivos), default=1.0)
            if perda >= (e.threshold or 1.0):
                ruins.append(f"{rover['serial']} com {perda:.0%} de perda no melhor rádio")
        if not ruins:
            return None
        return float(len(ruins)), "Enlace com o Rover: " + "; ".join(ruins) + "."
    return _por_base(session, regra, ctx, medir, agora)


def _fila_da_base(session, regra, _e, agora, ctx):
    def medir(_d: Device, r: dict, e: Efetiva, _agora):
        fila = r.get("uplink") or {}
        urgentes = sum(fila.get(f"P{i}") or 0 for i in (0, 1, 2, 3))
        if urgentes < (e.threshold or 0):
            return None
        return float(urgentes), (f"{urgentes} pedido(s) de comando, telemetria ou evento "
                                 "esperando a Starlink na base.")
    return _por_base(session, regra, ctx, medir, agora)


def _repetidora_bateria(session, regra, _e, agora, ctx):
    def medir(_d: Device, r: dict, e: Efetiva, _agora):
        fracas = [x for x in r.get("repetidoras") or []
                  if x.get("bateria_pct") is not None and x["bateria_pct"] < (e.threshold or 0)]
        mortas = [x for x in r.get("repetidoras") or [] if not x.get("vivo")]
        if not fracas and not mortas:
            return None
        partes = [f"{x['nome']} com {x['bateria_pct']:.0f}% de bateria" for x in fracas]
        partes += [f"{x['nome']} sem responder" for x in mortas]
        return float(len(partes)), "Repetidora: " + "; ".join(partes) + "."
    return _por_base(session, regra, ctx, medir, agora)


def _api_erros(session, regra, e, agora, _ctx):
    janela = observabilidade.api(session, minutos=e.window_minutes or 5, agora=agora)
    if janela["requests"] < API_MIN_REQUISICOES or janela["error_rate"] is None:
        return
    pct = janela["error_rate"] * 100
    if pct >= (e.threshold or 0):
        piores = ", ".join(f"{r['method']} {r['route']}" for r in janela["routes"][:3]
                           if r["server_errors"])
        yield Violacao("componente", "api", "API da plataforma", None, round(pct, 2),
                       f"{pct:.1f}% de respostas 5xx em {e.window_minutes} min "
                       f"({janela['server_errors']} de {janela['requests']}). Rotas: {piores}.")


IA_MIN_INFERENCIAS = 10


def _ia_fora(session, regra, e, agora, ctx):
    estado = ctx.get("ia") or observabilidade.estado_ia()
    if estado["status"] == "fora":
        yield Violacao("componente", "ia", "Serviço de IA", None, None,
                       f"O serviço de IA não responde ao /health: {estado.get('detail')}.")
        return
    if estado["status"] != "ok":
        return  # desligado ou simulado: nada a alertar
    desde = agora - timedelta(minutes=e.window_minutes or 15)
    linhas = session.execute(select(Detection.error).where(
        Detection.created_at >= desde,
        Detection.source.in_([DetectionSource.CLOUD_PRIMARY, DetectionSource.CLOUD_SECONDARY]),
    )).all()
    if len(linhas) < IA_MIN_INFERENCIAS:
        return
    erros = sum(1 for (erro,) in linhas if erro)
    pct = 100 * erros / len(linhas)
    if pct >= (100 if e.threshold is None else e.threshold):
        yield Violacao("componente", "ia", "Serviço de IA", None, round(pct, 2),
                       f"{pct:.0f}% das inferências com erro em {e.window_minutes} min "
                       f"({erros} de {len(linhas)}).")


def _drift(session, regra, e, agora, _ctx):
    horas = max(1, (e.window_minutes or 1440) // 60)
    for d in observabilidade.drift(session, janela_horas=horas, agora=agora):
        if d["distance"] is None or d["distance"] < (1 if e.threshold is None else e.threshold):
            continue
        yield Violacao(
            "modelo", f"{d['source']}:{d['model_key']}"[:64],
            f"{d['model_key']} ({d['source']})", None, d["distance"],
            f"A distribuição de classes das últimas {horas} h mudou "
            f"{d['distance']:.0%} em relação aos 7 dias anteriores "
            f"({d['recent']} previsões recentes, {d['baseline']} na base). "
            "Pode ser a lavoura (surto) ou o modelo: confira com o agrônomo.")


def _eventos_parados(session, regra, e, agora, _ctx):
    f = observabilidade.filas(session, agora)
    idade = f["outbox_oldest_pending_s"]
    if idade is None or idade / 60 < (e.threshold or 0):
        return
    yield Violacao("componente", "worker", "Worker de eventos", None, round(idade / 60, 1),
                   f"{f['outbox_pending']} evento(s) sem entrega; o mais antigo há "
                   f"{idade / 60:.0f} min. Avisos, verificação e retenção dependem dele.")


REGRAS: dict[str, RegraDef] = {
    r.kind: r
    for r in (
        RegraDef("rover_offline", ROBO, "Robô sem comunicação",
                 "Robô ativo sem falar com a plataforma há mais de X minutos.",
                 30.0, "min", None, "critico", _offline),
        RegraDef("disco_rover", ROBO, "Disco do robô cheio",
                 "Uso do disco local acima de Y%.", 90.0, "%", None, "aviso", _disco),
        RegraDef("temperatura_rover", ROBO, "Temperatura do robô",
                 "Temperatura interna acima do limite.", 75.0, "°C", None, "critico",
                 _temperatura),
        RegraDef("sync_parada", ROBO, "Sincronização parada",
                 "Robô conectado com registros esperando há mais de X minutos.",
                 30.0, "min", None, "aviso", _sync_parada),
        RegraDef("camera_rover", ROBO, "Câmera sem responder",
                 "Alguma câmera do robô falhou na última leitura de saúde.",
                 None, None, None, "aviso", _camera),
        RegraDef("modelo_divergente", ROBO, "Modelo diferente do liberado",
                 "O robô roda um modelo que não é o liberado pelo registry.",
                 None, None, None, "aviso", _modelo_divergente),
        RegraDef("base_sem_contato", ROBO, "Base da fazenda sem contato",
                 "A base não fala com a plataforma há mais de X minutos (Starlink fora ou "
                 "base sem energia).", 5.0, "min", None, "critico", _base_sem_contato),
        RegraDef("enlace_degradado", ROBO, "Enlace com o Rover degradado",
                 "Rover sem nenhum rádio com a base, ou perda acima de Y no melhor rádio "
                 "(fora de zona morta mapeada).", 0.3, "fração", None, "aviso",
                 _enlace_degradado),
        RegraDef("fila_base", ROBO, "Fila da base crescendo",
                 "Mais de X pedidos P0-P3 esperando a Starlink na base.", 50.0, "pedidos",
                 None, "aviso", _fila_da_base),
        RegraDef("repetidora_bateria", ROBO, "Repetidora com bateria fraca",
                 "Repetidora da malha abaixo de Y% de bateria ou sem responder.", 20.0, "%",
                 None, "aviso", _repetidora_bateria),
        RegraDef("api_erros", PLATAFORMA, "Taxa de erro da API",
                 f"Respostas 5xx acima de Y% na janela (com {API_MIN_REQUISICOES}+ "
                 "requisições).", 5.0, "%", 5, "critico", _api_erros),
        RegraDef("ia_fora", PLATAFORMA, "IA fora do ar",
                 "O serviço de IA não responde, ou Y% das inferências da janela falharam.",
                 20.0, "%", 15, "critico", _ia_fora),
        RegraDef("drift_classes", PLATAFORMA, "Drift da distribuição de classes",
                 "A distribuição de classes recente (janela) se afastou da base dos 7 dias "
                 "anteriores mais que o limite (distância de variação total, 0 a 1).",
                 0.25, "distância", 24 * 60, "aviso", _drift),
        RegraDef("eventos_parados", PLATAFORMA, "Fila de eventos parada",
                 "Evento de domínio sem entrega há mais de X minutos (worker parado?).",
                 10.0, "min", None, "critico", _eventos_parados),
    )
}


# ---------------------------------------------------------------------------
# Regras no banco
# ---------------------------------------------------------------------------


class AlertError(ValueError):
    def __init__(self, mensagem: str, *, status: int = 422) -> None:
        super().__init__(mensagem)
        self.status = status


def _chave(tenant_id: str | None, kind: str) -> str:
    return f"{tenant_id or '-'}:{kind}"


def sincronizar_catalogo(session: Session) -> int:
    """Cria a linha padrão de cada regra que ainda não existe. Não muda as existentes."""
    existentes = set(session.scalars(select(AlertRule.kind).where(AlertRule.tenant_id.is_(None))))
    novas = 0
    for regra in REGRAS.values():
        if regra.kind in existentes:
            continue
        try:
            # Dois workers (ou o worker e uma rota) num banco novo: o segundo bate na
            # restrição única e segue — a regra já existe, que é o que se queria.
            with session.begin_nested():
                session.add(AlertRule(
                    scope_key=_chave(None, regra.kind), tenant_id=None, kind=regra.kind,
                    enabled=True, threshold=regra.threshold,
                    window_minutes=regra.window_minutes, severity=regra.severity))
                session.flush()
        except IntegrityError:
            continue
        novas += 1
    return novas


def _regras_do_banco(session: Session, ctx: dict) -> dict[tuple[str | None, str], AlertRule]:
    if "regras" not in ctx:
        ctx["regras"] = {(r.tenant_id, r.kind): r for r in session.scalars(select(AlertRule))}
    return ctx["regras"]


def efetiva_para(session: Session, kind: str, tenant_id: str | None,
                 ctx: dict | None = None) -> Efetiva | None:
    """A regra que vale para o cliente (ou a da plataforma). ``None`` se desligada."""
    ctx = ctx if ctx is not None else {}
    regras = _regras_do_banco(session, ctx)
    padrao = regras.get((None, kind))
    if padrao is not None and not padrao.enabled:
        return None  # a equipe desligou a regra: vale para todos, inclusive cópias de cliente
    propria = regras.get((tenant_id, kind)) if tenant_id and kind not in SO_DA_EQUIPE else None
    linha = propria or padrao
    if linha is None or not linha.enabled:
        return None
    return Efetiva(linha, linha.threshold, linha.window_minutes, linha.severity)


def _valida(regra: RegraDef, threshold: float | None, window_minutes: int | None,
            severity: str | None) -> None:
    if threshold is not None:
        if regra.threshold is None:
            raise AlertError(f"A regra {regra.label!r} não tem limite.")
        if threshold < 0 or (regra.unit == "%" and threshold > 100) or \
                (regra.unit == "distância" and threshold > 1):
            raise AlertError("Limite fora da faixa da regra.")
    if window_minutes is not None:
        if regra.window_minutes is None:
            raise AlertError(f"A regra {regra.label!r} não tem janela.")
        if not 1 <= window_minutes <= 30 * 24 * 60:
            raise AlertError("Janela de 1 minuto a 30 dias.")
    if severity is not None and severity not in ("aviso", "critico"):
        raise AlertError("Severidade é 'aviso' ou 'critico'.")


def salvar_regra(session: Session, *, kind: str, tenant_id: str | None, by: User,
                 enabled: bool | None = None, threshold: float | None = None,
                 window_minutes: int | None = None, severity: str | None = None) -> AlertRule:
    """Ajusta a regra padrão (``tenant_id=None``) ou cria/ajusta a do cliente. Auditado."""
    regra = REGRAS.get(kind)
    if regra is None:
        raise AlertError(f"Regra desconhecida: {kind!r}.", status=404)
    if tenant_id is not None and regra.scope != ROBO:
        raise AlertError("Só regras de robô têm versão por cliente.", status=403)
    if tenant_id is not None and kind in SO_DA_EQUIPE:
        raise AlertError("Esta regra é da equipe ValTexa (é ela quem recebe o aviso); o "
                         "cliente controla os próprios avisos nas preferências.", status=403)
    _valida(regra, threshold, window_minutes, severity)
    linha = session.scalars(select(AlertRule).where(
        AlertRule.scope_key == _chave(tenant_id, kind))).first()
    antes = None
    if linha is None:
        padrao = session.scalars(select(AlertRule).where(
            AlertRule.scope_key == _chave(None, kind))).first()
        linha = AlertRule(
            scope_key=_chave(tenant_id, kind), tenant_id=tenant_id, kind=kind,
            enabled=padrao.enabled if padrao else True,
            threshold=padrao.threshold if padrao else regra.threshold,
            window_minutes=padrao.window_minutes if padrao else regra.window_minutes,
            severity=padrao.severity if padrao else regra.severity,
        )
        session.add(linha)
    else:
        antes = _descreve(linha)
    if enabled is not None:
        linha.enabled = enabled
    if threshold is not None:
        linha.threshold = threshold
    if window_minutes is not None:
        linha.window_minutes = window_minutes
    if severity is not None:
        linha.severity = severity
    linha.updated_by = by.id
    session.flush()
    audit.record(session, tenant_id=tenant_id, action="alert_rule.updated",
                 subject_type=SubjectType.ALERT_RULE, subject_id=linha.id,
                 actor_type=ActorType.USER, actor_id=by.id, actor_label=by.email,
                 old_state=antes, new_state=_descreve(linha), payload={"kind": kind})
    return linha


def remover_regra_do_cliente(session: Session, *, kind: str, tenant_id: str, by: User) -> bool:
    """Volta o cliente para a regra padrão. Auditado."""
    linha = session.scalars(select(AlertRule).where(
        AlertRule.scope_key == _chave(tenant_id, kind))).first()
    if linha is None:
        return False
    audit.record(session, tenant_id=tenant_id, action="alert_rule.reset",
                 subject_type=SubjectType.ALERT_RULE, subject_id=linha.id,
                 actor_type=ActorType.USER, actor_id=by.id, actor_label=by.email,
                 old_state=_descreve(linha), payload={"kind": kind})
    session.delete(linha)
    return True


def _descreve(linha: AlertRule) -> str:
    return (f"{'ligada' if linha.enabled else 'desligada'}; limite={linha.threshold}; "
            f"janela={linha.window_minutes}; {linha.severity}")


# ---------------------------------------------------------------------------
# Avaliação (worker)
# ---------------------------------------------------------------------------


@dataclass
class Relatorio:
    disparados: int = 0
    atualizados: int = 0
    resolvidos: int = 0
    erros: int = 0


def _open_key(kind: str, v: Violacao) -> str:
    return f"{kind}:{v.subject_type}:{v.subject_id}"[:160]


def avaliar(session: Session, agora: datetime | None = None, *,
            ia: dict | None = None) -> Relatorio:
    """Avalia todas as regras e reconcilia os alertas abertos. Faz *commit* por regra.

    Uma regra com defeito não impede as outras (vira ``erros`` e log).
    """
    agora = agora or datetime.now(UTC)
    rel = Relatorio()
    ctx: dict = {"ia": ia} if ia is not None else {}
    session.expire_all()  # avalia o banco de agora, não o que a sessão leu antes
    sincronizar_catalogo(session)
    session.commit()
    for regra in REGRAS.values():
        try:
            padrao = efetiva_para(session, regra.kind, None, ctx)
            if regra.scope == PLATAFORMA and padrao is None:
                violacoes: list[Violacao] = []
            else:
                violacoes = list(regra.avaliar(session, regra, padrao, agora, ctx))
            _reconcilia(session, regra, violacoes, agora, ctx, rel)
            session.commit()
        except Exception:
            session.rollback()
            rel.erros += 1
            logger.exception("Falha ao avaliar a regra de alerta %s", regra.kind)
    return rel


def _reconcilia(session: Session, regra: RegraDef, violacoes: list[Violacao],
                agora: datetime, ctx: dict, rel: Relatorio) -> None:
    abertos = {a.open_key: a for a in session.scalars(select(Alert).where(
        Alert.kind == regra.kind, Alert.open_key.is_not(None)))}
    vistos = set()
    for v in violacoes:
        chave = _open_key(regra.kind, v)
        efetiva = efetiva_para(session, regra.kind, v.tenant_id, ctx)
        if efetiva is None:
            continue  # desligada para este cliente: o alerta aberto (se houver) resolve
        vistos.add(chave)
        alerta = abertos.get(chave)
        if alerta is not None:
            alerta.value, alerta.message, alerta.last_seen_at = v.value, v.message, agora
            alerta.subject_label = v.label[:200]
            rel.atualizados += 1
            continue
        alerta = Alert(
            kind=regra.kind, rule_id=efetiva.rule.id, tenant_id=v.tenant_id,
            subject_type=v.subject_type, subject_id=v.subject_id, subject_label=v.label[:200],
            open_key=chave, state="disparado", severity=efetiva.severity, message=v.message,
            value=v.value, threshold=efetiva.threshold, fired_at=agora, last_seen_at=agora,
        )
        try:
            with session.begin_nested():  # outro worker já abriu: segue
                session.add(alerta)
                session.flush()
        except IntegrityError:
            continue
        events.publish(session, events.ALERT_FIRED, tenant_id=v.tenant_id,
                       subject_type=SubjectType.ALERT, subject_id=alerta.id,
                       payload={"kind": regra.kind, "severity": alerta.severity})
        rel.disparados += 1
    for chave, alerta in abertos.items():
        if chave in vistos:
            continue
        alerta.state, alerta.resolved_at, alerta.open_key = "resolvido", agora, None
        events.publish(session, events.ALERT_RESOLVED, tenant_id=alerta.tenant_id,
                       subject_type=SubjectType.ALERT, subject_id=alerta.id,
                       payload={"kind": regra.kind, "severity": alerta.severity})
        rel.resolvidos += 1


def reconhecer(session: Session, alerta: Alert, *, by: User, note: str | None,
               quem: str) -> Alert:
    """Alguém viu e está cuidando. Não silencia a regra: a condição ainda pode resolver."""
    if alerta.state == "resolvido":
        raise AlertError("Alerta já resolvido.", status=409)
    if alerta.state == "reconhecido":
        return alerta
    nota = (note or "").strip()[:2000] or None
    # Condicional no banco: o worker pode ter resolvido o alerta entre a leitura da rota
    # e esta escrita; gravar "reconhecido" por cima deixaria um alerta aberto para sempre.
    mudou = session.execute(
        update(Alert)
        .where(Alert.id == alerta.id, Alert.state == "disparado", Alert.open_key.is_not(None))
        .values(state="reconhecido", acknowledged_at=datetime.now(UTC), acknowledged_by=by.id,
                acknowledged_label=quem[:200], ack_note=nota)
        .execution_options(synchronize_session=False)
    ).rowcount
    session.refresh(alerta)
    if not mudou:
        if alerta.state == "reconhecido":
            return alerta
        raise AlertError("Alerta já resolvido.", status=409)
    audit.record(session, tenant_id=alerta.tenant_id, action="alert.acknowledged",
                 subject_type=SubjectType.ALERT, subject_id=alerta.id,
                 actor_type=ActorType.USER, actor_id=by.id, actor_label=by.email,
                 old_state="disparado", new_state="reconhecido", reason=alerta.ack_note,
                 payload={"kind": alerta.kind})
    return alerta


# ---------------------------------------------------------------------------
# Notificações: alerta → aviso (módulo da Parte 6)
# ---------------------------------------------------------------------------

AVISO_CLIENTE = "alerta_robo"
AVISO_EQUIPE = "plataforma_alerta"
"""Os dois tipos de aviso estão no catálogo de ``services/notifications.py``."""



def _alerta_do_evento(session: Session, event: OutboxEvent) -> Alert | None:
    return session.get(Alert, event.subject_id) if event.subject_id else None


@avisos.regra(events.ALERT_FIRED)
def _aviso_disparado(session: Session, event: OutboxEvent) -> list[avisos.Aviso]:
    alerta = _alerta_do_evento(session, event)
    if alerta is None:
        return []
    regra = REGRAS.get(alerta.kind)
    titulo = f"{regra.label if regra else alerta.kind}: {alerta.subject_label}"
    gravidade = "critico" if alerta.severity == "critico" else "aviso"
    saida = []
    if alerta.tenant_id and alerta.kind != "rover_offline":
        saida.append(avisos.Aviso(
            kind=AVISO_CLIENTE, tenant_id=alerta.tenant_id, title=titulo, body=alerta.message,
            dedup=f"alerta:{alerta.id}:disparado", severity=gravidade, subject_type="alert",
            subject_id=alerta.id, link="/observabilidade"))
    cliente = session.get(Tenant, alerta.tenant_id) if alerta.tenant_id else None
    saida.append(avisos.Aviso(
        kind=AVISO_EQUIPE, tenant_id=alerta.tenant_id,
        title=titulo + (f" — {cliente.name}" if cliente else ""), body=alerta.message,
        dedup=f"plataforma:alerta:{alerta.id}:disparado", severity=gravidade,
        subject_type="alert", subject_id=alerta.id, link="/plataforma/observabilidade"))
    return saida


@avisos.regra(events.ALERT_RESOLVED)
def _aviso_resolvido(session: Session, event: OutboxEvent) -> list[avisos.Aviso]:
    """Só o crítico avisa que passou: o aviso resolvido de cada disco a 91 % seria ruído."""
    alerta = _alerta_do_evento(session, event)
    if alerta is None or alerta.severity != "critico":
        return []
    regra = REGRAS.get(alerta.kind)
    titulo = f"Resolvido — {regra.label if regra else alerta.kind}: {alerta.subject_label}"
    duracao = (as_utc(alerta.resolved_at) - as_utc(alerta.fired_at)).total_seconds() / 60
    corpo = f"A condição passou depois de {duracao:.0f} min."
    saida = [avisos.Aviso(
        kind=AVISO_EQUIPE, tenant_id=alerta.tenant_id, title=titulo, body=corpo,
        dedup=f"plataforma:alerta:{alerta.id}:resolvido", subject_type="alert",
        subject_id=alerta.id, link="/plataforma/observabilidade")]
    if alerta.tenant_id and alerta.kind != "rover_offline":
        saida.append(avisos.Aviso(
            kind=AVISO_CLIENTE, tenant_id=alerta.tenant_id, title=titulo, body=corpo,
            dedup=f"alerta:{alerta.id}:resolvido", subject_type="alert", subject_id=alerta.id,
            link="/observabilidade"))
    return saida


__all__ = [
    "AVISO_CLIENTE",
    "AVISO_EQUIPE",
    "PLATAFORMA",
    "REGRAS",
    "ROBO",
    "AlertError",
    "Relatorio",
    "avaliar",
    "efetiva_para",
    "reconhecer",
    "remover_regra_do_cliente",
    "salvar_regra",
    "sincronizar_catalogo",
]
