"""Enxame do talhão: o plano de quem olha onde, e a próxima missão de cada robô.

Ver ``valtexa/services/enxame.py`` (o alocador) e ``docs/ENXAME.md``.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Path, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from valtexa.api.deps import Principal, get_scoped, require
from valtexa.db import get_session
from valtexa.models import Field as Talhao
from valtexa.models import utcnow
from valtexa.models.enxame import PlanoDoEnxame
from valtexa.planejamento import robotico
from valtexa.security import rbac
from valtexa.services import enxame, plant_map

router = APIRouter(tags=["enxame"])

DOENCA = r"^[A-Za-z][A-Za-z_]{0,63}$"


class PlanoIn(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    doenca: str = Field(default="Rust", pattern=DOENCA)
    dias_ate_visita: int = Field(default=1, ge=1, le=30)
    segmento_m: float = Field(default=20.0, gt=1, le=500)
    custo_tratar: float | None = Field(default=None, gt=0)
    perda_planta: float | None = Field(default=None, gt=0)
    eficacia: float | None = Field(default=None, gt=0, le=1)
    max_tarefas: int = Field(default=300, ge=1, le=5000)
    desconto_sobreposicao: float = Field(default=enxame.DESCONTO_SOBREPOSICAO, ge=0, le=1)
    valor_minimo_por_minuto: float | None = Field(default=None, gt=0)
    piso_vigilancia_dias: int | None = Field(default=None, ge=1, le=365)


class MissoesIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_ids: list[str] | None = Field(
        default=None, description="Só estes; nulo = a próxima missão de todos do plano.")


def _ia(chamada, *args) -> Any:
    try:
        corpo = chamada(*args)
    except plant_map.PlantMapRefusedError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc
    except plant_map.PlantMapUnavailableError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    if corpo is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "O rover ainda não passou por este talhão.")
    return corpo


def _ativo(session: Session, field_row: Talhao) -> PlanoDoEnxame | None:
    return session.scalars(select(PlanoDoEnxame).where(
        PlanoDoEnxame.tenant_id == field_row.tenant_id, PlanoDoEnxame.field_id == field_row.id,
        PlanoDoEnxame.estado == "ativo").order_by(PlanoDoEnxame.versao.desc())).first()


@router.post("/fields/{field_id}/enxame/plano", summary="Calcula o plano do enxame do talhão")
def criar_plano(
    field_id: str,
    pedido: PlanoIn,
    principal: Principal = Depends(require(rbac.DECISION_READ)),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Lê a frota disponível da fazenda e as prioridades do gêmeo, aloca, e guarda como o
    plano ativo do talhão (o anterior fica na história). Não cria missão: isso é
    ``POST .../plano/{id}/missoes``."""
    field_row = get_scoped(session, Talhao, field_id, principal)
    economia = [pedido.custo_tratar, pedido.perda_planta, pedido.eficacia]
    if any(v is not None for v in economia) and not all(v is not None for v in economia):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            "custo_tratar, perda_planta e eficacia vão juntos.")
    agentes, fora = enxame.agentes_da_fazenda(session, tenant_id=principal.tenant_id,
                                              farm_id=field_row.farm_id)
    tarefas = enxame.tarefas_de_verificacao(session, tenant_id=principal.tenant_id,
                                            field_row=field_row)
    params: dict[str, Any] = {"doenca": pedido.doenca, "dias_ate_visita": pedido.dias_ate_visita,
                              "segmento_m": pedido.segmento_m, "max_tarefas": pedido.max_tarefas,
                              "com_plantas": True}
    if pedido.custo_tratar is not None:
        params |= {"custo_tratar": pedido.custo_tratar, "perda_planta": pedido.perda_planta,
                   "eficacia": pedido.eficacia}
    avisos: list[str] = []
    for canal in sorted({a.tipo for a in agentes}):
        corpo = _ia(plant_map.prioridades_gemeo, field_id, {**params, "canal": canal})
        tarefas += enxame.tarefas_do_gemeo(corpo, field_id)
        avisos += corpo.get("avisos", [])
    # As mesmas restrições do plano robótico (8.3): inclinação, obstáculos, dados da Starlink
    # de cada Rover, valor mínimo por minuto e piso de vigilância — com as premissas guardadas.
    ctx = robotico.contexto(session, field_row, agentes,
                            {"desconto_sobreposicao": pedido.desconto_sobreposicao,
                             "valor_minimo_por_minuto": pedido.valor_minimo_por_minuto,
                             "piso_vigilancia_dias": pedido.piso_vigilancia_dias},
                            utcnow())
    tarefas, _, _ = robotico.piso_de_vigilancia(tarefas, ctx.piso_dias)
    row = enxame.planejar(
        session, tenant_id=principal.tenant_id, field_row=field_row, tarefas=tarefas,
        agentes=agentes, fora=fora, actor_id=principal.user.id,
        desconto_sobreposicao=pedido.desconto_sobreposicao, alocador=ctx.alocar,
        entradas={"pedido": pedido.model_dump(), "avisos_do_gemeo": sorted(set(avisos)),
                  "premissas": ctx.premissas.lista(), "dados_starlink": ctx.dados})
    session.commit()
    return {**enxame.situacao_do_plano(session, row, tenant_id=principal.tenant_id),
            "avisos_do_gemeo": sorted(set(avisos))}


@router.get("/fields/{field_id}/enxame/plano", summary="O plano ativo do enxame do talhão")
def ver_plano(
    field_id: str,
    principal: Principal = Depends(require(rbac.DECISION_READ)),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Com ``desatualizado`` e o porquê: a frota mudou, ou o plano envelheceu."""
    field_row = get_scoped(session, Talhao, field_id, principal)
    row = _ativo(session, field_row)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sem plano do enxame para este talhão.")
    return enxame.situacao_do_plano(session, row, tenant_id=principal.tenant_id)


@router.post("/fields/{field_id}/enxame/plano/{plano_id}/missoes",
             summary="Cria, em rascunho, a próxima missão de cada robô do plano")
def criar_missoes(
    field_id: str,
    pedido: MissoesIn,
    plano_id: str = Path(min_length=1, max_length=32),
    principal: Principal = Depends(require(rbac.MISSION_CREATE)),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Missões em ``DRAFT``: autorizar (camada de segurança) e despachar (assinatura) seguem
    o fluxo de sempre. Recusa plano substituído (409) e o de outro talhão (404)."""
    field_row = get_scoped(session, Talhao, field_id, principal)
    row = get_scoped(session, PlanoDoEnxame, plano_id, principal)
    if row.field_id != field_row.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "PlanoDoEnxame não encontrado.")
    if row.estado != "ativo":
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Este plano foi substituído por um mais novo: use o ativo.")
    resultado = enxame.criar_missoes(session, row, field_row=field_row,
                                     device_ids=pedido.device_ids, actor_id=principal.user.id)
    session.commit()
    return {"plano_id": row.id, "versao": row.versao, "missoes": resultado}
