"""Fila de trabalhos pesados.

Existe por um motivo só: quem faz upload de 1.500 imagens fecha a aba. O que
acontece depois não pode depender de uma conexão HTTP aberta.

A fila é uma tabela, não Redis nem Celery. Para o volume do MVP — dezenas de
coletas por dia — uma tabela com ``SELECT ... LIMIT 1`` a cada ciclo do worker
resolve, e traz de graça duas coisas que a fila externa não dá: o trabalho
participa da mesma transação que criou a coleta (não existe trabalho apontando
para uma coleta que não chegou a existir), e a auditoria e o trabalho vivem no
mesmo banco. Quando o volume exigir, a interface aqui — ``enqueue``, ``claim``,
``finish``, ``fail`` — é a que um adaptador de broker precisa implementar.

**A posse é por prazo, não por flag.** ``claim`` grava ``locked_until``. Um
worker que morra no meio não deixa o trabalho preso: o prazo vence e outro
worker o reivindica. Uma flag booleana exigiria alguém para limpá-la, e esse
alguém nunca existe quando o processo é morto pelo orquestrador.
"""

from __future__ import annotations

import logging
import os
import socket
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from valtexa.models import JobKind, JobState, ProcessingJob, SubjectType, as_utc

logger = logging.getLogger(__name__)

LEASE_SECONDS = 300
"""Por quanto tempo um worker detém um trabalho antes de outro poder assumi-lo.

Generoso de propósito: um lote de 1.500 imagens leva mais que um ciclo, e o
worker renova o prazo a cada lote processado (ver :func:`renew`).
"""


def worker_id() -> str:
    """Quem está processando. Aparece no painel quando um trabalho trava."""
    return f"{socket.gethostname()}:{os.getpid()}"


def enqueue(
    session: Session,
    *,
    tenant_id: str,
    kind: JobKind,
    subject_type: SubjectType,
    subject_id: str,
    total: int = 0,
    payload: dict | None = None,
) -> ProcessingJob:
    """Põe um trabalho na fila. Não faz *commit*.

    Reenfileirar o mesmo assunto é idempotente enquanto houver um trabalho vivo:
    dois cliques em "iniciar processamento" não processam a coleta duas vezes.
    """
    vivo = session.scalars(
        select(ProcessingJob).where(
            ProcessingJob.subject_id == subject_id,
            ProcessingJob.kind == kind.value,
            ProcessingJob.state.in_([JobState.QUEUED.value, JobState.RUNNING.value]),
        )
    ).first()
    if vivo is not None:
        return vivo

    job = ProcessingJob(
        tenant_id=tenant_id,
        kind=kind.value,
        state=JobState.QUEUED.value,
        subject_type=subject_type.value,
        subject_id=subject_id,
        progress_total=total,
        payload=payload or {},
    )
    session.add(job)
    session.flush()
    return job


def claim(session: Session, kind: JobKind | None = None) -> ProcessingJob | None:
    """Reivindica o trabalho mais antigo que ninguém **mais** está executando.

    Três situações são aceitas, e a terceira é a que importa:

    * o trabalho está na fila;
    * está rodando e o prazo venceu — é como um worker morto devolve o que
      estava fazendo;
    * está rodando e **este mesmo worker** é o dono. Um lote de 1.500 imagens
      atravessa muitos ciclos, e o prazo existe para proteger de *outro*
      processo, não para impedir o dono de continuar. Sem esta condição, cada
      coleta avançaria um lote a cada ``LEASE_SECONDS`` — cinco minutos parada
      entre 25 imagens e as 25 seguintes.
    """
    agora = datetime.now(UTC)
    eu = worker_id()
    consulta = select(ProcessingJob).where(
        ProcessingJob.state.in_([JobState.QUEUED.value, JobState.RUNNING.value])
    )
    if kind is not None:
        consulta = consulta.where(ProcessingJob.kind == kind.value)

    consulta = consulta.order_by(ProcessingJob.created_at)
    if session.get_bind().dialect.name == "postgresql":
        consulta = consulta.with_for_update(skip_locked=True)
    for job in session.scalars(consulta):
        prazo = as_utc(job.locked_until)
        rodando = job.state == JobState.RUNNING.value
        preso_por_outro = rodando and prazo is not None and prazo > agora and job.locked_by != eu
        if preso_por_outro:
            continue

        # Continuar o próprio trabalho não é tentativa nova: contar como
        # tentativa faria um lote grande esgotar max_attempts só por ser grande.
        tentativas = job.attempts if (rodando and job.locked_by == eu) else job.attempts + 1

        # Compare-and-set: só reivindica se ninguém mexeu na linha desde a leitura.
        # Dois workers que leram o mesmo trabalho na fila não o executam os dois —
        # o segundo vê rowcount 0 e passa ao próximo (Parte 5, F18). No Postgres o
        # SELECT ainda pula as linhas travadas (FOR UPDATE SKIP LOCKED).
        condicoes = [
            ProcessingJob.id == job.id,
            ProcessingJob.state == job.state,
            ProcessingJob.attempts == job.attempts,
            ProcessingJob.locked_by.is_(None) if job.locked_by is None
            else ProcessingJob.locked_by == job.locked_by,
        ]
        resultado = session.execute(
            update(ProcessingJob)
            .where(*condicoes)
            .values(
                state=JobState.RUNNING.value,
                locked_by=eu,
                locked_until=agora + timedelta(seconds=LEASE_SECONDS),
                attempts=tentativas,
                started_at=job.started_at or agora,
            )
            .execution_options(synchronize_session=False)
        )
        if resultado.rowcount != 1:
            session.expire(job)
            continue
        session.refresh(job)
        return job
    return None


def renew(job: ProcessingJob, done: int | None = None) -> None:
    """Estende o prazo e atualiza o progresso. Chamado a cada lote."""
    job.locked_until = datetime.now(UTC) + timedelta(seconds=LEASE_SECONDS)
    if done is not None:
        job.progress_done = done


def finish(job: ProcessingJob) -> None:
    job.state = JobState.DONE.value
    job.finished_at = datetime.now(UTC)
    job.locked_until = None
    job.progress_done = job.progress_total


def fail(job: ProcessingJob, erro: str) -> None:
    """Marca a falha e decide se ainda cabe nova tentativa."""
    job.last_error = erro[:2000]
    job.locked_until = None
    if job.attempts >= job.max_attempts:
        job.state = JobState.FAILED.value
        job.finished_at = datetime.now(UTC)
        logger.error("Trabalho %s desistiu após %d tentativas: %s", job.id, job.attempts, erro)
    else:
        job.state = JobState.QUEUED.value
        logger.warning("Trabalho %s falhou (tentativa %d): %s", job.id, job.attempts, erro)


def requeue(job: ProcessingJob) -> ProcessingJob:
    """Devolve um trabalho falho para a fila, zerando as tentativas.

    É o botão "tentar de novo" do painel. Zerar as tentativas é intencional:
    quem clica está afirmando que a causa foi tratada.
    """
    job.state = JobState.QUEUED.value
    job.attempts = 0
    job.finished_at = None
    job.locked_until = None
    job.locked_by = None
    return job
