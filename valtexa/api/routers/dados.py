"""Orçamento de dados dos robôs (Starlink própria): o teto e o relatório de consumo.

Ver ``valtexa/services/orcamento_dados.py`` e ``VALTEXA-ROVER/docs/ROVER_RUNTIME.md``
(orçamento de dados).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from valtexa.api.deps import Principal, get_scoped, require
from valtexa.db import get_session
from valtexa.models import Device
from valtexa.security import rbac
from valtexa.services import orcamento_dados

router = APIRouter(tags=["dados"])


class OrcamentoIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bytes_dia: int | None = Field(default=None, ge=0, le=orcamento_dados.MAX_BYTES_DIA,
                                  description="Teto do dia da fazenda; 0 = sem teto.")
    bytes_missao: int | None = Field(default=None, ge=0, le=orcamento_dados.MAX_BYTES_DIA,
                                     description="Teto por missão; 0 = sem teto.")


@router.get("/dados/consumo", summary="Consumo de dados de cada robô do cliente")
def consumo_do_cliente(
    dias: int = Query(default=7, ge=1, le=90),
    principal: Principal = Depends(require(rbac.DEVICE_READ)),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    return orcamento_dados.resumo_do_cliente(session, principal.tenant_id, dias=dias)


@router.get("/devices/{device_id}/dados", summary="Consumo de dados de um robô")
def consumo_do_robo(
    device_id: str,
    dias: int = Query(default=7, ge=1, le=90),
    principal: Principal = Depends(require(rbac.DEVICE_READ)),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """O que o Rover contou (Starlink, subida e descida) e o que a plataforma recebeu, por
    dia da fazenda, com os avisos de tempestade de eventos e de teto."""
    device = get_scoped(session, Device, device_id, principal)
    return orcamento_dados.relatorio(session, device, dias=dias)


@router.put("/devices/{device_id}/orcamento-dados", summary="Teto de dados do robô")
def define_orcamento(
    device_id: str,
    pedido: OrcamentoIn,
    principal: Principal = Depends(require(rbac.DEVICE_MANAGE)),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Vale a partir da próxima missão (desce assinado dentro dela). Os dois nulos apagam o
    teto da plataforma: o robô volta ao do ``rover.json``."""
    device = get_scoped(session, Device, device_id, principal)
    try:
        orcamento_dados.definir(session, device, bytes_dia=pedido.bytes_dia,
                                bytes_missao=pedido.bytes_missao, actor_id=principal.user_id)
    except orcamento_dados.OrcamentoInvalidoError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    session.commit()
    return orcamento_dados.relatorio(session, device, dias=1)
