"""Diagnóstico do processo: a versão pública (``/health``) e a da equipe.

O ``/health`` não pede autenticação — é o que o balanceador e o ``HEALTHCHECK``
do Docker consultam. Por isso ele não pode contar o que só a equipe deve saber:
o endereço interno da IA e a lista de pendências de configuração ("SESSION_SECRET
ainda é o padrão") são, para quem está de fora, um mapa de ataque. E o console
do cliente mostrava tudo isso numa aba "Plataforma" (brief, seção 30: o cliente
não vê infraestrutura nem informação interna).

A regra: o ``/health`` diz **se** está bom (banco ok/erro, inferência ligada ou
não, quantas pendências) e o ``/v1/platform/health`` diz **o quê**, para a
equipe da ValTexa.
"""

from __future__ import annotations

from sqlalchemy import func, select, text

from valtexa.config import settings
from valtexa.db import session_scope
from valtexa.models import OutboxEvent
from valtexa.models.fleet import PROTOCOL_VERSION
from valtexa.schemas import HealthResponse


def diagnostico() -> HealthResponse:
    """Tudo o que o processo sabe de si mesmo. Nunca levanta exceção."""
    database = "ok"
    pending = 0
    try:
        with session_scope() as session:
            session.execute(text("SELECT 1"))
            pending = (
                session.scalar(
                    select(func.count(OutboxEvent.id)).where(OutboxEvent.delivered_at.is_(None))
                )
                or 0
            )
    except Exception as exc:  # health nunca deve levantar; um erro aqui vira o texto abaixo
        database = f"erro: {type(exc).__name__}"

    return HealthResponse(
        status="ok",
        environment=settings.environment,
        protocol_version=PROTOCOL_VERSION,
        database=database,
        inference=settings.inference_url if settings.inference_enabled else "desligado",
        pending_events=pending,
        warnings=settings.production_problems(),
    )


def publico(completo: HealthResponse) -> HealthResponse:
    """A mesma resposta sem o que serve de mapa para quem está de fora.

    Os campos continuam os mesmos (o contrato do monitoramento não muda): o banco
    vira só ``ok``/``erro``, a inferência só ``ligado``/``desligado`` e cada
    pendência de configuração vira uma linha genérica — o alerta "``warnings``
    não vazio" continua funcionando, e o detalhe fica em ``/v1/platform/health``.
    """
    pendencias = len(completo.warnings)
    return completo.model_copy(
        update={
            "database": "ok" if completo.database == "ok" else "erro",
            "inference": "desligado" if completo.inference == "desligado" else "ligado",
            "warnings": [
                f"Pendência de configuração {i + 1} de {pendencias}: detalhes para a "
                "equipe ValTexa em /v1/platform/health."
                for i in range(pendencias)
            ],
        }
    )
