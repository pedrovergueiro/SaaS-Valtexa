"""Worker de fundo: o que a plataforma faz sem ninguém pedir.

Quatro tarefas, em cadências diferentes:

* **entregar eventos** do *outbox* — a cada ciclo;
* **vencer missões** autorizadas que ninguém executou — a cada 30 s. Sem isto
  uma missão despachada para um robô que nunca a buscou ficaria "despachada"
  para sempre, e o dispositivo, preso a ela;
* **perceber que um robô sumiu** — a cada minuto. A conectividade só era
  reavaliada quando chegava telemetria, ou seja, nunca para o robô que parou de
  mandar; é exatamente esse que interessa;
* **retenção** — a cada 6 h, ver :mod:`valtexa.services.retention`.

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
from valtexa.config import settings
from valtexa.models import Connectivity, Device, DeviceStatus
from valtexa.services import events, ingestion, mission_manager, retention

logger = logging.getLogger(__name__)

TICK_SECONDS = 5.0
EXPIRY_EVERY = 30.0
CONNECTIVITY_EVERY = 60.0
RETENTION_EVERY = 6 * 3600.0


@dataclass
class TickReport:
    """O que um ciclo fez. Serve ao log e aos testes."""

    delivered: int = 0
    expired: int = 0
    went_offline: int = 0
    retention: retention.RetentionReport | None = None


@dataclass
class Worker:
    """Agenda as tarefas por cadência, sem depender de relógio de parede.

    ``time.monotonic`` e não ``datetime.now``: um ajuste de NTP no servidor não
    pode fazer a retenção rodar duas vezes nem deixar de rodar.
    """

    last_run: dict[str, float] = field(default_factory=dict)

    def due(self, job: str, every: float, now: float) -> bool:
        last = self.last_run.get(job)
        if last is None or now - last >= every:
            self.last_run[job] = now
            return True
        return False

    def tick(self, now: float | None = None) -> TickReport:
        moment = time.monotonic() if now is None else now
        report = TickReport()

        with db.SessionLocal() as session:
            report.delivered = events.drain(session)

        if self.due("expiry", EXPIRY_EVERY, moment):
            with db.session_scope() as session:
                report.expired = mission_manager.expire_stale(session)

        if self.due("connectivity", CONNECTIVITY_EVERY, moment):
            with db.session_scope() as session:
                report.went_offline = refresh_connectivity(session)

        if self.due("retention", RETENTION_EVERY, moment):
            with db.SessionLocal() as session:
                report.retention = retention.run(session)

        return report


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
            if report.delivered or report.expired or report.went_offline:
                logger.info(
                    "worker: %d evento(s), %d missão(ões) vencida(s), %d robô(s) offline",
                    report.delivered,
                    report.expired,
                    report.went_offline,
                )
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

    logging.basicConfig(
        level=settings.log_level, format="%(asctime)s %(levelname)-8s %(name)s: %(message)s"
    )

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
