"""Worker de fundo: o que a plataforma faz sem ninguém pedir.

Quatro tarefas, em cadências diferentes:

* **entregar eventos** do *outbox* — a cada ciclo; é nessa entrega que as regras
  de notificação criam os avisos (``services/notifications.py``);
* **enviar avisos** pelos canais externos (e-mail), com novas tentativas — a cada
  ciclo;
* **processar coletas** — a cada ciclo. É o que permite ao administrador fechar
  a aba depois de subir 1.500 imagens: a análise acontece aqui, em lotes, e o
  painel acompanha pelo progresso do trabalho;
* **vencer missões** autorizadas que ninguém executou — a cada 30 s. Sem isto
  uma missão despachada para um robô que nunca a buscou ficaria "despachada"
  para sempre, e o dispositivo, preso a ela;
* **perceber que um robô sumiu** — a cada minuto. A conectividade só era
  reavaliada quando chegava telemetria, ou seja, nunca para o robô que parou de
  mandar; é exatamente esse que interessa;
* **retenção** — a cada 6 h, ver :mod:`valtexa.services.retention` (e a
  estatística da API por minuto mais velha que ``API_METRICS_RETENTION_DAYS``);
* **alertas** — a cada ``ALERTS_EVERY_SECONDS`` (60 s), as regras de
  :mod:`valtexa.services.alertas`: dispara, atualiza e resolve, e o aviso sai pelas
  notificações no ciclo seguinte.

Em desenvolvimento roda como thread dentro da API (``EVENT_WORKER_IN_API=true``).
Em produção, com várias réplicas da API, rode um processo só::

    python -m valtexa.worker

e desligue a thread. Nada no código muda — só onde ele roda.
"""

from __future__ import annotations

import argparse
import logging
import signal
import threading
import time
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from valtexa import db
from valtexa.config import recusar_se_inadequado, settings
from valtexa.models import Collection, Connectivity, Device, DeviceStatus, JobKind
from valtexa.observability import logs
from valtexa.services import (
    alertas,
    collection_ingest,
    coordenacao,
    edge_sync,
    events,
    fusao_borda,
    ingestion,
    jobs,
    missao_resultado,
    mission_manager,
    notifications,
    observabilidade,
    retention,
    support_tickets,  # noqa: F401 — registra as regras de aviso dos chamados
)

logger = logging.getLogger(__name__)

TICK_SECONDS = 5.0
EXPIRY_EVERY = 30.0
CONNECTIVITY_EVERY = 60.0
FUSION_EVERY = 30.0
RETENTION_EVERY = 6 * 3600.0


@dataclass
class TickReport:
    """O que um ciclo fez. Serve ao log e aos testes."""

    delivered: int = 0
    files_processed: int = 0
    expired: int = 0
    went_offline: int = 0
    retention: retention.RetentionReport | None = None
    abandoned_uploads: int = 0
    forwarded_to_cloud: int = 0
    fused_from_edge: int = 0
    passes_closed: int = 0
    notifications_sent: int = 0
    alerts: alertas.Relatorio | None = None
    api_stats_purged: int = 0


@dataclass
class Worker:
    """Agenda as tarefas por cadência, sem depender de relógio de parede.

    ``time.monotonic`` e não ``datetime.now``: um ajuste de NTP no servidor não
    pode fazer a retenção rodar duas vezes nem deixar de rodar.
    """

    last_run: dict[str, float] = field(default_factory=dict)

    def due(self, job: str, every: float, now: float) -> bool:
        """Venceu a cadência **deste** processo e nenhum outro worker rodou neste ciclo.

        Com dois workers (por engano ou durante um deploy), a marca compartilhada de
        :mod:`~valtexa.services.coordenacao` (Redis em produção) deixa um só rodar a
        retenção, os alertas e o resto das tarefas periódicas a cada intervalo.
        """
        last = self.last_run.get(job)
        if last is None or now - last >= every:
            self.last_run[job] = now
            return coordenacao.coordenacao.uma_vez(f"worker:{job}", every * 0.9, now)
        return False

    def tick(self, now: float | None = None) -> TickReport:
        moment = time.monotonic() if now is None else now
        report = TickReport()

        with db.SessionLocal() as session:
            report.delivered = events.drain(session)

        # Depois dos eventos: o aviso criado neste ciclo já sai por e-mail neste ciclo.
        with db.SessionLocal() as session:
            report.notifications_sent = notifications.entregar_pendentes(session)

        with db.session_scope() as session:
            report.files_processed = process_collections(session)

        if self.due("expiry", EXPIRY_EVERY, moment):
            with db.session_scope() as session:
                report.expired = mission_manager.expire_stale(session)

        if self.due("connectivity", CONNECTIVITY_EVERY, moment):
            with db.session_scope() as session:
                report.went_offline = refresh_connectivity(session)

        if self.due("uploads", RETENTION_EVERY, moment):
            with db.session_scope() as session:
                report.abandoned_uploads = edge_sync.limpar_abandonados(session)
            # Eventos da Edge AI cujo original já subiu mas a IA de nuvem falhou na hora.
            with db.session_scope() as session:
                report.forwarded_to_cloud = missao_resultado.varrer(session)

        if self.due("fusion", FUSION_EVERY, moment):
            # Resultados do Rover → fusão por planta da IA; depois, as passadas prontas.
            with db.session_scope() as session:
                report.fused_from_edge = fusao_borda.varrer(session)
            with db.session_scope() as session:
                report.passes_closed = fusao_borda.fechar_passadas(session)

        if self.due("retention", RETENTION_EVERY, moment):
            with db.SessionLocal() as session:
                report.retention = retention.run(session)
            with db.SessionLocal() as session:
                report.api_stats_purged = observabilidade.limpar_estatisticas(session)

        if self.due("alerts", settings.alerts_every_seconds, moment):
            with db.SessionLocal() as session:
                report.alerts = alertas.avaliar(session)

        return report


def process_collections(session: Session) -> int:
    """Avança um trabalho de coleta. Devolve quantos arquivos processou.

    Um trabalho por ciclo, um lote por trabalho. Dois efeitos: nenhuma coleta
    monopoliza o worker enquanto outra espera, e o progresso de cada uma anda de
    forma visível no painel em vez de saltar de 0% a 100%.
    """
    job = jobs.claim(session, JobKind.COLLECTION_INGEST)
    if job is None:
        return 0
    # A concessão vale a partir de agora, não do fim do lote: sem o commit, outro
    # worker não a veria durante os minutos de inferência e pegaria o mesmo
    # trabalho — e o banco ficaria com a linha presa esse tempo todo.
    session.commit()

    coleta = session.get(Collection, job.subject_id)
    if coleta is None:
        jobs.fail(job, "A coleta não existe mais.")
        return 0

    try:
        report = collection_ingest.process_batch(session, coleta)
    except Exception as exc:  # a falha vira estado do trabalho, não derruba o worker
        logger.exception("Falha ao processar a coleta %s", coleta.code)
        jobs.fail(job, f"{type(exc).__name__}: {exc}")
        return 0

    if report.finished:
        jobs.finish(job)
    else:
        jobs.renew(job, done=coleta.files_processed)
    return report.processed


def refresh_connectivity(session: Session) -> int:
    """Reavalia o enlace de todos os robôs ativos. Devolve quantos caíram agora."""
    went_offline = 0
    for device in session.scalars(select(Device).where(Device.status == DeviceStatus.ACTIVE)):
        before = device.connectivity
        ingestion.refresh_connectivity(session, device)
        if before is not Connectivity.OFFLINE and device.connectivity is Connectivity.OFFLINE:
            went_offline += 1
    return went_offline


def run_forever(stop: threading.Event, interval: float = TICK_SECONDS) -> None:
    """Laço principal. Nenhuma exceção escapa.

    Uma thread que morre em silêncio pararia a entrega de eventos sem sinal
    nenhum, e o sistema pareceria saudável enquanto a verificação pós-tratamento
    nunca fosse agendada.
    """
    worker = Worker()
    while not stop.is_set():
        try:
            report = worker.tick()
            if report.delivered or report.files_processed or report.expired or report.went_offline:
                logger.info(
                    "worker: %d evento(s), %d arquivo(s) de coleta, %d missão(ões) "
                    "vencida(s), %d robô(s) offline",
                    report.delivered,
                    report.files_processed,
                    report.expired,
                    report.went_offline,
                )
            if report.alerts and (report.alerts.disparados or report.alerts.resolvidos):
                logger.info("worker: alertas %s", report.alerts)
            if report.retention and report.retention.samples_rolled_up:
                logger.info("worker: retenção %s", report.retention)
        except Exception:
            logger.exception("Falha num ciclo do worker; seguindo para o próximo.")
        stop.wait(interval)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="valtexa.worker", description=__doc__.split("\n")[0])
    parser.add_argument("--once", action="store_true", help="Roda um ciclo e sai.")
    parser.add_argument("--interval", type=float, default=TICK_SECONDS)
    args = parser.parse_args(argv)

    logs.configurar(settings.log_level, settings.log_format)
    recusar_se_inadequado(settings, logger)

    if args.once:
        report = Worker().tick()
        logger.info("ciclo único: %s", report)
        return 0

    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    logger.info("worker iniciado (ciclo de %.1fs)", args.interval)
    run_forever(stop, args.interval)
    logger.info("worker encerrado")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
