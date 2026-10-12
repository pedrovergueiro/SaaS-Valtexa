"""Observabilidade da plataforma (brief, seções 34 e 35): o que medir e de onde.

Três fontes, uma para cada parte da arquitetura:

* **SaaS** — a API (latência por rota, taxa de erro, volume) vem do *middleware*
  (``observability/http.py``), descarregada por minuto em ``api_request_stat``;
  filas (trabalhos, eventos do *outbox*, entregas de aviso) e usuários ativos vêm
  do banco, na hora;
* **IA** — inferências gravadas: ``detection`` (IA de nuvem: contagem, erros,
  latência, distribuição de classes por modelo) e ``edge_record`` (resultados da
  Edge AI que subiram). O *drift* medido aqui é o **da distribuição de classes**
  (a saída do modelo), não o da entrada — esse exige a referência do treino, que
  vive com os pesos;
* **Rovers** — a saúde padronizada de cada robô (``services/saude_rover.py``).

Tudo isto alimenta três consumidores: ``/metrics`` (Prometheus), o painel
``/v1/platform/observability`` e as regras de alerta (``services/alertas.py``).
"""

from __future__ import annotations

import logging
import threading
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import case, delete, func, select
from sqlalchemy.orm import Session

from valtexa import db
from valtexa.config import settings
from valtexa.models import (
    Alert,
    ApiRequestStat,
    Detection,
    Device,
    DeviceStatus,
    EdgeRecord,
    NotificationDelivery,
    OutboxEvent,
    ProcessingJob,
    Tenant,
    UserSession,
    as_utc,
)
from valtexa.models.enums import DetectionSource, JobState
from valtexa.observability import http as obs_http
from valtexa.observability.metricas import Familia, quantil_dos_baldes
from valtexa.services import saude_rover

logger = logging.getLogger(__name__)

SIMULADOS = ("sim-1",)
"""Versões de modelo do analisador simulado (testes e demonstração)."""


def _agora(agora: datetime | None) -> datetime:
    return agora or datetime.now(UTC)


# ---------------------------------------------------------------------------
# API: descarga da janela por minuto e leitura agregada
# ---------------------------------------------------------------------------


def descarregar(session: Session, janela: obs_http.JanelaApi | None = None,
                instancia: str | None = None) -> int:
    """Grava no banco o que a janela acumulou desde a última descarga. Faz *commit*.

    Se o banco falhar, os dados voltam para a janela (a próxima descarga tenta de
    novo) — perder um minuto de estatística por um soluço do banco seria esconder
    justamente o minuto em que algo deu errado.
    """
    janela = janela or obs_http.JANELA
    dados = janela.retirar()
    if not dados:
        return 0
    quem = instancia or obs_http.instancia()
    n = len(obs_http.LIMITES_MS) + 1
    try:
        for (minuto, method, route, classe), v in dados.items():
            session.add(ApiRequestStat(
                minute=minuto, instance=quem, method=method, route=route, status_class=classe,
                requests=int(v[0]), errors=int(v[1]), duration_ms_sum=float(v[2]),
                duration_ms_max=float(v[3]), buckets=[int(x) for x in v[4:4 + n]],
            ))
        session.commit()
    except Exception:
        session.rollback()
        janela.devolver(dados)
        raise
    return len(dados)


def descarregar_periodicamente(stop: threading.Event, intervalo: float | None = None) -> None:
    """Laço da thread da API: descarrega a cada ``METRICS_FLUSH_SECONDS`` e ao parar."""
    intervalo = intervalo or settings.metrics_flush_seconds
    while True:
        parar = stop.wait(intervalo)
        try:
            with db.SessionLocal() as session:
                descarregar(session)
        except Exception:
            logger.exception("Falha ao descarregar as métricas da API; tento de novo.")
        if parar:
            return


def limpar_estatisticas(session: Session, dias: int | None = None,
                        agora: datetime | None = None) -> int:
    """Apaga estatística por minuto mais velha que ``API_METRICS_RETENTION_DAYS``."""
    limite = _agora(agora) - timedelta(days=dias or settings.api_metrics_retention_days)
    resultado = session.execute(delete(ApiRequestStat).where(ApiRequestStat.minute < limite))
    session.commit()
    return resultado.rowcount or 0


@dataclass
class _Acumulado:
    requests: int = 0
    errors: int = 0
    client_errors: int = 0
    soma_ms: float = 0.0
    max_ms: float = 0.0
    baldes: list[int] | None = None

    def soma(self, linha: ApiRequestStat) -> None:
        self.requests += linha.requests
        self.errors += linha.errors
        if linha.status_class == "4xx":
            self.client_errors += linha.requests
        self.soma_ms += linha.duration_ms_sum
        self.max_ms = max(self.max_ms, linha.duration_ms_max)
        b = list(linha.buckets or [])
        if self.baldes is None:
            self.baldes = b
        else:
            self.baldes = [x + y for x, y in zip(self.baldes, b, strict=False)]

    def saida(self) -> dict:
        baldes = self.baldes or []
        return {
            "requests": self.requests,
            "server_errors": self.errors,
            "client_errors": self.client_errors,
            "error_rate": round(self.errors / self.requests, 4) if self.requests else None,
            "latency_ms_avg": round(self.soma_ms / self.requests, 1) if self.requests else None,
            "latency_ms_p50": _q(baldes, 0.5),
            "latency_ms_p95": _q(baldes, 0.95),
            "latency_ms_max": round(self.max_ms, 1) if self.requests else None,
        }


def _q(baldes: list[int], q: float) -> float | None:
    valor = quantil_dos_baldes(obs_http.LIMITES_MS, baldes, q)
    return None if valor is None else round(valor, 1)


def api(session: Session, minutos: int = 60, agora: datetime | None = None,
        incluir_pendente: bool = True) -> dict:
    """Totais e por rota na janela. ``incluir_pendente`` soma o que esta réplica ainda
    não descarregou (o painel mostra o minuto corrente sem esperar a descarga)."""
    desde = _agora(agora).replace(second=0, microsecond=0) - timedelta(minutes=minutos)
    linhas = list(session.scalars(select(ApiRequestStat).where(ApiRequestStat.minute >= desde)))
    if incluir_pendente:
        n = len(obs_http.LIMITES_MS) + 1
        with obs_http.JANELA._trava:  # leitura sem retirar
            pendentes = list(obs_http.JANELA._dados.items())
        for (minuto, method, route, classe), v in pendentes:
            if minuto >= desde:
                linhas.append(ApiRequestStat(
                    minute=minuto, instance="", method=method, route=route,
                    status_class=classe, requests=int(v[0]), errors=int(v[1]),
                    duration_ms_sum=float(v[2]), duration_ms_max=float(v[3]),
                    buckets=[int(x) for x in v[4:4 + n]]))
    total = _Acumulado()
    por_rota: dict[tuple[str, str], _Acumulado] = defaultdict(_Acumulado)
    for linha in linhas:
        total.soma(linha)
        por_rota[(linha.method, linha.route)].soma(linha)
    rotas = [{"method": m, "route": r, **a.saida()} for (m, r), a in por_rota.items()]
    rotas.sort(key=lambda x: (-(x["server_errors"]), -(x["latency_ms_p95"] or 0),
                              -x["requests"]))
    return {"window_minutes": minutos, **total.saida(), "routes": rotas}


# ---------------------------------------------------------------------------
# Filas e usuários
# ---------------------------------------------------------------------------


def filas(session: Session, agora: datetime | None = None) -> dict:
    agora = _agora(agora)
    jobs = Counter()
    for kind, state, n in session.execute(
        select(ProcessingJob.kind, ProcessingJob.state, func.count())
        .group_by(ProcessingJob.kind, ProcessingJob.state)
    ):
        jobs[(kind, state)] = n
    mais_antigo = session.scalar(
        select(func.min(ProcessingJob.created_at))
        .where(ProcessingJob.state == JobState.QUEUED.value)
    )
    falhas_24h = session.scalar(
        select(func.count()).select_from(ProcessingJob)
        .where(ProcessingJob.state == JobState.FAILED.value,
               ProcessingJob.updated_at >= agora - timedelta(hours=24))
    ) or 0
    pendentes = session.scalar(
        select(func.count()).select_from(OutboxEvent).where(OutboxEvent.delivered_at.is_(None))
    ) or 0
    com_erro = session.scalar(
        select(func.count()).select_from(OutboxEvent)
        .where(OutboxEvent.delivered_at.is_(None), OutboxEvent.last_error.is_not(None))
    ) or 0
    evento_antigo = session.scalar(
        select(func.min(OutboxEvent.created_at)).where(OutboxEvent.delivered_at.is_(None))
    )
    entregas = dict(session.execute(
        select(NotificationDelivery.status, func.count()).group_by(NotificationDelivery.status)
    ).all())

    def idade(quando: datetime | None) -> float | None:
        quando = as_utc(quando)
        return None if quando is None else round(max(0.0, (agora - quando).total_seconds()), 1)

    return {
        "jobs": [{"kind": k, "state": s, "count": n} for (k, s), n in sorted(jobs.items())],
        "jobs_queued": sum(n for (_, s), n in jobs.items() if s == JobState.QUEUED.value),
        "jobs_running": sum(n for (_, s), n in jobs.items() if s == JobState.RUNNING.value),
        "jobs_oldest_queued_s": idade(mais_antigo),
        "jobs_failed_24h": falhas_24h,
        "outbox_pending": pendentes,
        "outbox_with_error": com_erro,
        "outbox_oldest_pending_s": idade(evento_antigo),
        "deliveries": entregas,
    }


def usuarios_ativos(session: Session, agora: datetime | None = None) -> dict:
    """Pessoas distintas com sessão usada nos últimos 15 min e nas últimas 24 h."""
    agora = _agora(agora)

    def desde(delta: timedelta) -> int:
        return session.scalar(
            select(func.count(func.distinct(UserSession.user_id)))
            .where(UserSession.last_seen_at >= agora - delta)
        ) or 0

    return {"active_15m": desde(timedelta(minutes=15)), "active_24h": desde(timedelta(hours=24))}


# ---------------------------------------------------------------------------
# IA: inferências, erros, latência, distribuição de classes e drift
# ---------------------------------------------------------------------------


LATENCIAS_P95 = 5000


def _p95(valores: list[float]) -> float | None:
    if not valores:
        return None
    ordenados = sorted(valores)
    return round(ordenados[min(len(ordenados) - 1, int(0.95 * len(ordenados)))], 1)


def ia_nuvem(session: Session, horas: int = 24, agora: datetime | None = None,
             tenant_id: str | None = None) -> list[dict]:
    """Por modelo: inferências, erros, abstenções, latência e distribuição de classes.

    Contagens e classes saem agregadas do banco; a latência p95 usa as
    :data:`LATENCIAS_P95` mais recentes de cada modelo (amostra recente, não a janela
    inteira — o suficiente para o p95 e barato com milhões de linhas).
    """
    desde = _agora(agora) - timedelta(hours=horas)
    filtros = [Detection.created_at >= desde,
               Detection.source.in_([DetectionSource.CLOUD_PRIMARY,
                                     DetectionSource.CLOUD_SECONDARY])]
    if tenant_id:
        filtros.append(Detection.tenant_id == tenant_id)
    chave = (func.coalesce(Detection.model_key, "?"), func.coalesce(Detection.model_version, "?"))
    erro = case((Detection.error.is_not(None), 1), else_=0)
    absteve = case((Detection.abstained.is_(True), 1), else_=0)
    grupos: dict[tuple, dict] = {}
    for k, v, n, erros, abst, media in session.execute(
        select(*chave, func.count(), func.sum(erro), func.sum(absteve),
               func.avg(Detection.latency_ms))
        .where(*filtros).group_by(*chave)
    ):
        grupos[(k, v)] = {"n": n, "erros": int(erros or 0), "abst": int(abst or 0),
                          "media": None if media is None else round(float(media), 1),
                          "classes": Counter()}
    for k, v, rotulo, n in session.execute(
        select(*chave, Detection.label, func.count())
        .where(*filtros, Detection.error.is_(None), Detection.label.is_not(None))
        .group_by(*chave, Detection.label)
    ):
        if (k, v) in grupos:
            grupos[(k, v)]["classes"][rotulo] += n
    saida = []
    for (k, v), g in sorted(grupos.items(), key=lambda kv: -kv[1]["n"]):
        latencias = [float(x) for x in session.scalars(
            select(Detection.latency_ms).where(
                *filtros, func.coalesce(Detection.model_key, "?") == k,
                func.coalesce(Detection.model_version, "?") == v,
                Detection.latency_ms.is_not(None))
            .order_by(Detection.created_at.desc()).limit(LATENCIAS_P95))]
        saida.append({
            "source": "nuvem", "model_key": k, "model_version": v,
            "simulated": v in SIMULADOS or k.startswith("simulated-"),
            "inferences": g["n"], "errors": g["erros"],
            "error_rate": round(g["erros"] / g["n"], 4) if g["n"] else None,
            "abstentions": g["abst"], "latency_ms_avg": g["media"],
            "latency_ms_p95": _p95(latencias),
            "classes": dict(g["classes"].most_common(20)),
        })
    return saida


def ia_borda(session: Session, horas: int = 24, agora: datetime | None = None,
             tenant_id: str | None = None) -> list[dict]:
    """Resultados da Edge AI que já subiram, por modelo (contagem e classes)."""
    desde = _agora(agora) - timedelta(hours=horas)
    filtros = [EdgeRecord.occurred_at >= desde, EdgeRecord.kind == "result"]
    if tenant_id:
        filtros.append(EdgeRecord.tenant_id == tenant_id)
    grupos: dict[tuple, Counter] = defaultdict(Counter)
    for chave, versao, rotulo, n in session.execute(
        select(EdgeRecord.model_key, EdgeRecord.model_version, EdgeRecord.label, func.count())
        .where(*filtros)
        .group_by(EdgeRecord.model_key, EdgeRecord.model_version, EdgeRecord.label)
    ):
        grupos[(chave or "?", versao or "?")][rotulo or "?"] += n
    return [
        {"source": "borda", "model_key": k, "model_version": v,
         "inferences": sum(c.values()), "classes": dict(c.most_common(20))}
        for (k, v), c in sorted(grupos.items(), key=lambda kv: -sum(kv[1].values()))
    ]


DRIFT_MIN_RECENTE = 30
DRIFT_MIN_BASE = 100


def distancia_de_variacao(a: Counter | dict, b: Counter | dict) -> float | None:
    """Distância de variação total entre duas distribuições de classes (0 a 1).

    É a fração da massa que mudou de classe: 0,25 quer dizer que um quarto das
    previsões "migrou". Fácil de explicar a quem decide, e sem o infinito do KL
    quando uma classe some.
    """
    na, nb = sum(a.values()), sum(b.values())
    if not na or not nb:
        return None
    classes = set(a) | set(b)
    return round(0.5 * sum(abs(a.get(c, 0) / na - b.get(c, 0) / nb) for c in classes), 4)


def drift(session: Session, *, janela_horas: int = 24, base_dias: int = 7,
          agora: datetime | None = None) -> list[dict]:
    """Por fonte e modelo: distribuição recente contra a base anterior, e a distância.

    Recente = últimas ``janela_horas``; base = os ``base_dias`` antes disso. Sem
    amostra suficiente (``DRIFT_MIN_RECENTE`` / ``DRIFT_MIN_BASE``) a distância sai
    ``None`` com o motivo — pouca amostra dá distância grande por acaso.
    """
    agora = _agora(agora)
    corte = agora - timedelta(hours=janela_horas)
    inicio = corte - timedelta(days=base_dias)
    nuvem = (Detection.created_at, Detection.model_key, Detection.label, (
        Detection.error.is_(None), Detection.label.is_not(None),
        Detection.source.in_([DetectionSource.CLOUD_PRIMARY, DetectionSource.CLOUD_SECONDARY])))
    borda = (EdgeRecord.occurred_at, EdgeRecord.model_key, EdgeRecord.label, (
        EdgeRecord.kind == "result", EdgeRecord.label.is_not(None)))
    saida = []
    for fonte, (quando, chave_col, rotulo_col, filtros) in (("nuvem", nuvem), ("borda", borda)):
        # Contagem no banco (GROUP BY), não linha a linha: roda a cada minuto no worker
        # e a cada raspagem do Prometheus, sobre oito dias de previsões.
        def contar(*periodo, chave_col=chave_col, rotulo_col=rotulo_col, filtros=filtros):
            linhas = session.execute(
                select(chave_col, rotulo_col, func.count())
                .where(*filtros, *periodo).group_by(chave_col, rotulo_col))
            saida_: dict[str, Counter] = defaultdict(Counter)
            for chave, rotulo, n in linhas:
                saida_[chave or "?"][rotulo] += n
            return saida_

        recente = contar(quando >= corte)
        base = contar(quando >= inicio, quando < corte)
        for chave in sorted(set(recente) | set(base)):
            r, b = recente[chave], base[chave]
            motivo = None
            if sum(r.values()) < DRIFT_MIN_RECENTE:
                motivo = f"menos de {DRIFT_MIN_RECENTE} previsões recentes"
            elif sum(b.values()) < DRIFT_MIN_BASE:
                motivo = f"menos de {DRIFT_MIN_BASE} previsões na base"
            saida.append({
                "source": fonte, "model_key": chave,
                "recent": sum(r.values()), "baseline": sum(b.values()),
                "distance": None if motivo else distancia_de_variacao(r, b),
                "reason": motivo,
                "recent_classes": dict(r.most_common(10)),
                "baseline_classes": dict(b.most_common(10)),
            })
    return saida


# ---------------------------------------------------------------------------
# Serviço de IA (VALTEXA-B): está no ar?
# ---------------------------------------------------------------------------

_IA_CACHE: dict[str, object] = {}
IA_CACHE_SEGUNDOS = 30.0


def estado_ia(*, forcar: bool = False, cliente: httpx.Client | None = None) -> dict:
    """``GET {INFERENCE_URL}/health`` com prazo curto, guardado por 30 s.

    ``desligado`` quando a plataforma roda sem IA (``INFERENCE_ENABLED=false``) — não
    é "fora": ninguém espera resposta. ``simulado`` com ``SIMULATED_INFERENCE``.
    """
    if not settings.inference_enabled:
        return {"status": "desligado", "detail": "INFERENCE_ENABLED=false", "checked_at": None}
    if settings.simulated_inference:
        return {"status": "simulado", "detail": "SIMULATED_INFERENCE ligado: sem serviço real.",
                "checked_at": None}
    agora = time.monotonic()
    if not forcar and _IA_CACHE and agora - float(_IA_CACHE["em"]) < IA_CACHE_SEGUNDOS:
        return dict(_IA_CACHE["estado"])  # type: ignore[arg-type]
    url = settings.inference_url.rstrip("/") + "/health"
    try:
        dono = cliente is None
        cliente = cliente or httpx.Client(timeout=3.0)
        try:
            resposta = cliente.get(url, headers=settings.inference_headers())
        finally:
            if dono:
                cliente.close()
        if resposta.status_code == 200:
            estado = {"status": "ok", "detail": None}
        else:
            estado = {"status": "fora", "detail": f"HTTP {resposta.status_code}"}
    except httpx.HTTPError as exc:
        estado = {"status": "fora", "detail": f"{type(exc).__name__}: {exc}"[:200]}
    estado["checked_at"] = datetime.now(UTC).isoformat()
    _IA_CACHE.update({"em": agora, "estado": estado})
    return dict(estado)


# ---------------------------------------------------------------------------
# Frota
# ---------------------------------------------------------------------------


def frota(session: Session, *, tenant_id: str | None = None,
          agora: datetime | None = None) -> list[dict]:
    agora = _agora(agora)
    consulta = (select(Device, Tenant.name).join(Tenant, Tenant.id == Device.tenant_id)
                .where(Device.status != DeviceStatus.RETIRED)
                .order_by(Tenant.name, Device.name))
    if tenant_id:
        consulta = consulta.where(Device.tenant_id == tenant_id)
    return [
        {"device_id": d.id, "name": d.name, "serial_number": d.serial_number,
         "tenant_id": d.tenant_id, "tenant_name": nome, "status": d.status.value,
         **saude_rover.retrato(d, agora)}
        for d, nome in session.execute(consulta)
    ]


# ---------------------------------------------------------------------------
# Componentes: um semáforo por parte da arquitetura
# ---------------------------------------------------------------------------


def componentes(session: Session, *, agora: datetime | None = None,
                ia: dict | None = None) -> list[dict]:
    """Banco, API, worker/eventos, IA, frota e alertas: ``ok``, ``atencao`` ou ``falha``."""
    agora = _agora(agora)
    saida = []
    try:
        session.execute(select(1))
        saida.append({"component": "banco", "status": "ok", "detail": None})
    except Exception as exc:
        saida.append({"component": "banco", "status": "falha", "detail": type(exc).__name__})
        return saida

    janela = api(session, minutos=5, agora=agora)
    taxa = janela["error_rate"]
    saida.append({
        "component": "api",
        "status": "falha" if taxa is not None and taxa >= 0.05 and janela["requests"] >= 20
        else "atencao" if taxa else "ok",
        "detail": f"{janela['requests']} requisições em 5 min, "
                  f"{janela['server_errors']} com erro 5xx",
    })
    f = filas(session, agora)
    idade = f["outbox_oldest_pending_s"] or 0
    saida.append({
        "component": "worker",
        "status": "falha" if idade > 600 else "atencao" if idade > 120 or f["outbox_with_error"]
        else "ok",
        "detail": f"{f['outbox_pending']} evento(s) pendente(s)"
        + (f", o mais antigo há {idade:.0f} s" if idade else "")
        + f"; {f['jobs_queued']} trabalho(s) na fila",
    })
    ia = ia if ia is not None else estado_ia()
    saida.append({
        "component": "ia",
        "status": {"ok": "ok", "fora": "falha"}.get(ia["status"], "atencao"),
        "detail": ia["status"] + (f" — {ia['detail']}" if ia.get("detail") else ""),
    })
    robos = frota(session, agora=agora)
    offline = sum(1 for r in robos if r["connectivity"] == "offline")
    saida.append({
        "component": "frota",
        "status": "atencao" if offline else "ok",
        "detail": f"{len(robos)} robô(s), {offline} sem comunicação",
    })
    abertos = session.scalar(
        select(func.count()).select_from(Alert).where(Alert.state != "resolvido")) or 0
    criticos = session.scalar(
        select(func.count()).select_from(Alert)
        .where(Alert.state == "disparado", Alert.severity == "critico")) or 0
    saida.append({
        "component": "alertas",
        "status": "falha" if criticos else "atencao" if abertos else "ok",
        "detail": f"{abertos} aberto(s), {criticos} crítico(s) sem reconhecimento",
    })
    return saida


# ---------------------------------------------------------------------------
# /metrics: as famílias que vêm do banco
# ---------------------------------------------------------------------------


FAMILIAS_CACHE_SEGUNDOS = 15.0
_FAMILIAS_CACHE: dict[str, object] = {}


def familias(session: Session, agora: datetime | None = None, *,
             cache: bool = True) -> list[Familia]:
    """Fotografia do banco no formato do Prometheus (igual em toda réplica).

    Guardada por :data:`FAMILIAS_CACHE_SEGUNDOS` na réplica: dois Prometheus (ou um
    com várias réplicas atrás do balanceador) não refazem as consultas a cada
    raspagem.
    """
    momento = time.monotonic()
    if cache and agora is None and _FAMILIAS_CACHE and \
            momento - float(_FAMILIAS_CACHE["em"]) < FAMILIAS_CACHE_SEGUNDOS:
        return list(_FAMILIAS_CACHE["valor"])  # type: ignore[call-overload]
    saida = _familias(session, _agora(agora))
    if agora is None:
        _FAMILIAS_CACHE.update({"em": momento, "valor": saida})
    return list(saida)


def _familias(session: Session, agora: datetime) -> list[Familia]:
    saida: list[Familia] = []

    f = filas(session, agora)
    jobs = Familia("valtexa_jobs", "gauge", "Trabalhos na fila, por tipo e estado.")
    for linha in f["jobs"]:
        jobs.add(linha["count"], kind=linha["kind"], state=linha["state"])
    saida.append(jobs)
    simples = (
        ("valtexa_jobs_oldest_queued_seconds", "Idade do trabalho mais antigo na fila.",
         f["jobs_oldest_queued_s"] or 0),
        ("valtexa_jobs_failed_24h", "Trabalhos que falharam nas últimas 24 h.",
         f["jobs_failed_24h"]),
        ("valtexa_outbox_pending", "Eventos de domínio ainda não entregues.",
         f["outbox_pending"]),
        ("valtexa_outbox_with_error", "Eventos pendentes cuja entrega já falhou.",
         f["outbox_with_error"]),
        ("valtexa_outbox_oldest_pending_seconds", "Idade do evento pendente mais antigo.",
         f["outbox_oldest_pending_s"] or 0),
    )
    for nome, ajuda, valor in simples:
        fam = Familia(nome, "gauge", ajuda)
        fam.add(valor)
        saida.append(fam)
    entregas = Familia("valtexa_notification_deliveries", "gauge",
                       "Entregas de aviso por canal externo, por estado.")
    for estado, n in sorted(f["deliveries"].items()):
        entregas.add(n, status=estado)
    saida.append(entregas)

    u = usuarios_ativos(session, agora)
    ativos = Familia("valtexa_active_users", "gauge", "Pessoas com sessão usada na janela.")
    ativos.add(u["active_15m"], window="15m")
    ativos.add(u["active_24h"], window="24h")
    saida.append(ativos)

    nomes = {
        "conectado": Familia("valtexa_rover_up", "gauge",
                             "1 se o robô falou com a plataforma recentemente."),
        "cpu": Familia("valtexa_rover_cpu_percent", "gauge", "CPU do computador embarcado."),
        "mem": Familia("valtexa_rover_memory_percent", "gauge", "Memória em uso (%)."),
        "acel": Familia("valtexa_rover_accelerator_percent", "gauge", "GPU/NPU em uso (%)."),
        "disco": Familia("valtexa_rover_disk_percent", "gauge", "Disco local em uso (%)."),
        "temp": Familia("valtexa_rover_temperature_celsius", "gauge", "Temperatura interna."),
        "bat": Familia("valtexa_rover_battery_percent", "gauge", "Bateria (%)."),
        "cam": Familia("valtexa_rover_cameras_ok", "gauge", "Câmeras respondendo."),
        "fila": Familia("valtexa_rover_sync_pending", "gauge",
                        "Registros que o robô ainda tem para subir."),
        "visto": Familia("valtexa_rover_last_seen_seconds", "gauge",
                         "Segundos desde o último contato."),
    }
    for r in frota(session, agora=agora):
        rot = {"tenant": r["tenant_id"], "device": r["serial_number"]}
        nomes["conectado"].add(0 if r["connectivity"] == "offline" else 1, **rot)
        nomes["cpu"].add(r["cpu_percent"], **rot)
        nomes["mem"].add(r["memory_percent"], **rot)
        nomes["acel"].add(r["accelerator_percent"], **rot)
        nomes["disco"].add(r["disk_percent"], **rot)
        nomes["temp"].add(r["temperature_c"], **rot)
        nomes["bat"].add(r["battery_percent"], **rot)
        if r["cameras_total"]:
            nomes["cam"].add(r["cameras_ok"], **rot)
        nomes["fila"].add(r["sync_pending"], **rot)
        if r["offline_minutes"] is not None:
            nomes["visto"].add(r["offline_minutes"] * 60, **rot)
    saida += list(nomes.values())

    inf = Familia("valtexa_ai_inferences_24h", "gauge",
                  "Inferências da IA de nuvem gravadas nas últimas 24 h, por modelo.")
    err = Familia("valtexa_ai_errors_24h", "gauge", "Inferências com erro nas últimas 24 h.")
    lat = Familia("valtexa_ai_latency_p95_seconds_24h", "gauge",
                  "Latência p95 da IA de nuvem nas últimas 24 h (segundos).")
    cls = Familia("valtexa_ai_predictions_24h", "gauge",
                  "Previsões por classe nas últimas 24 h (nuvem e borda).")
    for m in ia_nuvem(session, 24, agora):
        rot = {"source": "nuvem", "model": m["model_key"], "version": m["model_version"]}
        inf.add(m["inferences"], **rot)
        err.add(m["errors"], **rot)
        lat.add(None if m["latency_ms_p95"] is None else m["latency_ms_p95"] / 1000, **rot)
        for classe, n in m["classes"].items():
            cls.add(n, **rot, label=classe)
    for m in ia_borda(session, 24, agora):
        rot = {"source": "borda", "model": m["model_key"], "version": m["model_version"]}
        inf.add(m["inferences"], **rot)
        for classe, n in m["classes"].items():
            cls.add(n, **rot, label=classe)
    dri = Familia("valtexa_ai_class_drift", "gauge",
                  "Distância de variação total entre a distribuição de classes recente e a "
                  "base (0 a 1).")
    for d in drift(session, agora=agora):
        dri.add(d["distance"], source=d["source"], model=d["model_key"])
    saida += [inf, err, lat, cls, dri]

    alertas = Familia("valtexa_alerts_open", "gauge", "Alertas abertos por tipo e estado.")
    for kind, state, n in session.execute(
        select(Alert.kind, Alert.state, func.count()).where(Alert.state != "resolvido")
        .group_by(Alert.kind, Alert.state)
    ):
        alertas.add(n, kind=kind, state=state)
    saida.append(alertas)
    return saida


__all__ = [
    "api",
    "componentes",
    "descarregar",
    "descarregar_periodicamente",
    "distancia_de_variacao",
    "drift",
    "estado_ia",
    "familias",
    "filas",
    "frota",
    "ia_borda",
    "ia_nuvem",
    "limpar_estatisticas",
    "usuarios_ativos",
]
