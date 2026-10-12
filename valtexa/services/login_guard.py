"""Limitação de tentativas de login (brief, seção 36; risco aberto da auditoria).

Sem isto, o ``/v1/auth/login`` aceitava senha atrás de senha, sem limite. A regra:

* **por conta**: depois de ``login_max_failures_per_email`` falhas seguidas na
  janela (contadas desde o último acerto), novas tentativas são recusadas com
  429 até a janela passar — **antes** de conferir a senha, para que nem a senha
  certa sirva de oráculo durante o bloqueio;
* **por endereço**: ``login_max_failures_per_ip`` falhas na janela, em contas
  quaisquer, bloqueiam aquele IP — é o caso de quem testa uma senha comum em
  muitas contas.

Contado no banco, não em memória: com mais de um processo atrás do balanceador,
um contador por processo deixaria o atacante dividir as tentativas entre eles.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from valtexa import db
from valtexa.config import settings
from valtexa.models import LoginAttempt

LIMPEZA = timedelta(days=1)


def _recusa(segundos: int) -> HTTPException:
    minutos = max(1, round(segundos / 60))
    return HTTPException(
        status.HTTP_429_TOO_MANY_REQUESTS,
        f"Muitas tentativas de login sem sucesso. Tente de novo em {minutos} min "
        "ou peça a redefinição da senha a quem administra a conta.",
        headers={"Retry-After": str(segundos)},
    )


def verificar(session: Session, email: str, ip: str | None) -> None:
    """Recusa (429) se a conta ou o endereço passaram do limite de falhas."""
    agora = datetime.now(UTC)
    inicio = agora - timedelta(seconds=settings.login_window_seconds)

    ultimo_acerto = session.scalar(
        select(func.max(LoginAttempt.at)).where(
            LoginAttempt.email == email, LoginAttempt.success.is_(True)
        )
    )
    desde = inicio
    if ultimo_acerto is not None:
        acerto = ultimo_acerto if ultimo_acerto.tzinfo else ultimo_acerto.replace(tzinfo=UTC)
        desde = max(inicio, acerto)

    falhas_conta = session.scalars(
        select(LoginAttempt.at)
        .where(
            LoginAttempt.email == email,
            LoginAttempt.success.is_(False),
            LoginAttempt.at > desde,
        )
        .order_by(LoginAttempt.at)
    ).all()
    if len(falhas_conta) >= settings.login_max_failures_per_email:
        raise _recusa(_restante(falhas_conta[0], agora))

    if ip:
        falhas_ip = session.scalars(
            select(LoginAttempt.at)
            .where(
                LoginAttempt.ip == ip,
                LoginAttempt.success.is_(False),
                LoginAttempt.at > inicio,
            )
            .order_by(LoginAttempt.at)
        ).all()
        if len(falhas_ip) >= settings.login_max_failures_per_ip:
            raise _recusa(_restante(falhas_ip[0], agora))


def _restante(primeira: datetime, agora: datetime) -> int:
    primeira = primeira if primeira.tzinfo else primeira.replace(tzinfo=UTC)
    fim = primeira + timedelta(seconds=settings.login_window_seconds)
    return max(1, int((fim - agora).total_seconds()))


def registrar(email: str, ip: str | None, *, sucesso: bool) -> None:
    """Grava a tentativa numa transação própria.

    Própria porque a falha termina em exceção e *rollback*: gravada na sessão da
    requisição, a tentativa errada sumiria junto — e o limite nunca subiria.
    """
    with db.SessionLocal() as guarda:
        guarda.execute(
            delete(LoginAttempt).where(LoginAttempt.at < datetime.now(UTC) - LIMPEZA)
        )
        guarda.add(LoginAttempt(email=email, ip=ip, success=sucesso))
        guarda.commit()
