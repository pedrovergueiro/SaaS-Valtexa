"""Planejamento de apoio à decisão (8.3): fitossanitário, robótico e de insumos.

Ver ``valtexa/planejamento/`` e ``docs/PLANEJAMENTO.md``. Permissões:

* pedir plano — ``planejamento:generate`` (dono, gestor, agrônomo, operador);
* ler — ``decision:read``;
* revisar — fitossanitário ``diagnosis:review`` (agrônomo), robótico ``mission:create``,
  insumos ``product:manage``.

Nenhuma destas rotas cria missão, aprova prescrição ou aplicação, muda limiar de modelo ou
chama o Safety Engine (Princípio de Ouro; ``tests/test_principio_de_ouro.py``).
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from pydantic import Field as Campo
from sqlalchemy import select
from sqlalchemy.orm import Session

from valtexa.api.deps import Principal, get_scoped, require
from valtexa.db import get_session
from valtexa.models import AuditEntry, Farm, Field, SubjectType, as_utc, utcnow
from valtexa.models.planejamento import PlanoDeApoio, RevisaoPlanoDeApoio
from valtexa.planejamento import fitossanitario, insumos, robotico, servico
from valtexa.security import rbac
from valtexa.services import enxame

router = APIRouter(tags=["planejamento"])

DOENCA = r"^[A-Za-z][A-Za-z_]{0,63}$"
REVISAO_POR_TIPO = {"fitossanitario": rbac.DIAGNOSIS_REVIEW, "robotico": rbac.MISSION_CREATE,
                    "insumos": rbac.PRODUCT_MANAGE}


def fonte_da_ia() -> fitossanitario.FonteDaIA:
    """As leituras da IA (o teste troca por um dublê)."""
    return fitossanitario.FonteDaIAPadrao()


class FitossanitarioIn(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    doenca: str | None = Campo(default=None, pattern=DOENCA)
    janela_dias: int | None = Campo(default=None, ge=1, le=365)
    pesos_impacto: dict[str, float] | None = Campo(default=None, max_length=50)
    limite_fila: int | None = Campo(default=None, ge=1, le=500)
    plantas_com_historico: int | None = Campo(default=None, ge=0, le=50)
    limiar_tendencia: float | None = Campo(default=None, ge=0, le=1)
    limiar_risco: float | None = Campo(default=None, gt=0, le=1)
    horizonte_dias: int | None = Campo(default=None, ge=1, le=60)
    janela_rotacao_dias: int | None = Campo(default=None, ge=1, le=1825)
    max_seguidas_mesmo_grupo: int | None = Campo(default=None, ge=1, le=20)


class RoboticoIn(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    doenca: str = Campo(default="Rust", pattern=DOENCA)
    dias_ate_visita: int = Campo(default=1, ge=1, le=30)
    segmento_m: float = Campo(default=20.0, gt=1, le=500)
    max_tarefas: int = Campo(default=300, ge=1, le=5000)
    fator_declive: float | None = Campo(default=None, ge=0, le=5)
    bytes_por_metro: float | None = Campo(default=None, ge=0, le=1e9)
    reserva_dados: float | None = Campo(default=None, ge=0, lt=1)
    desconto_sobreposicao: float | None = Campo(default=None, ge=0, le=1)
    valor_minimo_por_minuto: float | None = Campo(default=None, gt=0)
    piso_vigilancia_dias: int | None = Campo(default=None, ge=1, le=365)


class InsumosIn(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    farm_id: str | None = Campo(default=None, max_length=32)
    horizonte_dias: int | None = Campo(default=None, ge=7, le=365)
    janela_dias: int | None = Campo(default=None, ge=30, le=1825)
    mesma_epoca: bool | None = None
    reamostragens: int | None = Campo(default=None, ge=100, le=20000)
    min_aplicacoes: int | None = Campo(default=None, ge=1, le=100)
    min_blocos: int | None = Campo(default=None, ge=2, le=100)


class RevisaoIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decisao: Literal["aceito", "recusado", "ajustar"]
    comentario: str | None = Campo(default=None, max_length=4000)


def _sem_nulos(pedido: BaseModel) -> dict[str, Any]:
    return {k: v for k, v in pedido.model_dump().items() if v is not None}


@router.post("/fields/{field_id}/planejamento/fitossanitario",
             status_code=status.HTTP_201_CREATED,
             summary="Plano fitossanitário: fila de revisão, histórico, regiões, alternativas, "
                     "rotação")
def plano_fitossanitario(
    field_id: str,
    pedido: FitossanitarioIn,
    principal: Principal = Depends(require(rbac.PLANEJAMENTO_GENERATE)),
    session: Session = Depends(get_session),
    ia: fitossanitario.FonteDaIA = Depends(fonte_da_ia),
) -> dict[str, Any]:
    campo = get_scoped(session, Field, field_id, principal)
    corpo = _sem_nulos(pedido)
    resultado, premissas = fitossanitario.planejar(session, tenant_id=principal.tenant_id,
                                                   campo=campo, ia=ia, pedido=corpo,
                                                   agora=utcnow())
    p = servico.guardar(session, tenant_id=principal.tenant_id, tipo="fitossanitario",
                        farm_id=campo.farm_id, field_id=campo.id,
                        versao=fitossanitario.VERSAO, pedido=corpo, premissas=premissas,
                        resultado=resultado, ator_id=principal.user_id)
    session.commit()
    return servico.detalhe(p, [])


@router.post("/fields/{field_id}/planejamento/robotico", status_code=status.HTTP_201_CREATED,
             summary="Plano robótico: rotas, bateria, inclinação, obstáculos e dados")
def plano_robotico(
    field_id: str,
    pedido: RoboticoIn,
    principal: Principal = Depends(require(rbac.PLANEJAMENTO_GENERATE)),
    session: Session = Depends(get_session),
    ia: fitossanitario.FonteDaIA = Depends(fonte_da_ia),
) -> dict[str, Any]:
    campo = get_scoped(session, Field, field_id, principal)
    agora = utcnow()
    agentes, fora = enxame.agentes_da_fazenda(session, tenant_id=principal.tenant_id,
                                              farm_id=campo.farm_id, now=agora)
    tarefas = enxame.tarefas_de_verificacao(session, tenant_id=principal.tenant_id,
                                            field_row=campo, now=agora)
    avisos: list[str] = []
    params = {"doenca": pedido.doenca, "dias_ate_visita": pedido.dias_ate_visita,
              "segmento_m": pedido.segmento_m, "max_tarefas": pedido.max_tarefas,
              "com_plantas": True}
    for canal in sorted({a.tipo for a in agentes}):
        corpo_ia, motivo = fitossanitario.le(ia.prioridades, campo.id, {**params,
                                                                         "canal": canal})
        if motivo:
            avisos.append(f"prioridades do gêmeo ({canal}): {motivo}")
            continue
        tarefas += enxame.tarefas_do_gemeo(corpo_ia, campo.id)
        avisos += corpo_ia.get("avisos", [])
    corpo = _sem_nulos(pedido)
    resultado, premissas = robotico.planejar(session, tenant_id=principal.tenant_id,
                                             campo=campo, tarefas=tarefas, agentes=agentes,
                                             fora=fora, pedido=corpo, agora=agora,
                                             avisos_do_gemeo=avisos)
    p = servico.guardar(session, tenant_id=principal.tenant_id, tipo="robotico",
                        farm_id=campo.farm_id, field_id=campo.id, versao=robotico.VERSAO,
                        pedido=corpo, premissas=premissas, resultado=resultado,
                        ator_id=principal.user_id)
    session.commit()
    return servico.detalhe(p, [])


@router.post("/planejamento/insumos", status_code=status.HTTP_201_CREATED,
             summary="Plano de insumos: demanda com intervalo e possível reposição")
def plano_insumos(
    pedido: InsumosIn,
    principal: Principal = Depends(require(rbac.PLANEJAMENTO_GENERATE)),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    if pedido.farm_id is not None:
        get_scoped(session, Farm, pedido.farm_id, principal)
    corpo = _sem_nulos(pedido)
    resultado, premissas = insumos.planejar(session, tenant_id=principal.tenant_id,
                                            farm_id=pedido.farm_id,
                                            pedido={k: v for k, v in corpo.items()
                                                    if k != "farm_id"}, agora=utcnow())
    p = servico.guardar(session, tenant_id=principal.tenant_id, tipo="insumos",
                        farm_id=pedido.farm_id, field_id=None, versao=insumos.VERSAO,
                        pedido=corpo, premissas=premissas, resultado=resultado,
                        ator_id=principal.user_id)
    session.commit()
    return servico.detalhe(p, [])


@router.get("/planejamento", summary="Planos de apoio do cliente (mais novos primeiro)")
def lista_planos(
    tipo: Literal["fitossanitario", "robotico", "insumos"] | None = None,
    field_id: str | None = Query(default=None, max_length=32),
    limite: int = Query(default=50, ge=1, le=200),
    principal: Principal = Depends(require(rbac.DECISION_READ)),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    q = select(PlanoDeApoio).where(PlanoDeApoio.tenant_id == principal.tenant_id)
    if tipo:
        q = q.where(PlanoDeApoio.tipo == tipo)
    if field_id:
        q = q.where(PlanoDeApoio.field_id == field_id)
    q = q.order_by(PlanoDeApoio.created_at.desc(), PlanoDeApoio.id).limit(limite)
    return [servico.resumo(p) for p in session.scalars(q)]


def _revisoes(session: Session, plano_id: str) -> list[RevisaoPlanoDeApoio]:
    return list(session.scalars(select(RevisaoPlanoDeApoio).where(
        RevisaoPlanoDeApoio.plano_id == plano_id).order_by(RevisaoPlanoDeApoio.revisado_em)))


@router.get("/planejamento/{plano_apoio_id}", summary="Um plano: premissas, resultado, revisões")
def detalhe_plano(
    plano_apoio_id: str,
    principal: Principal = Depends(require(rbac.DECISION_READ)),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    p = get_scoped(session, PlanoDeApoio, plano_apoio_id, principal)
    return servico.detalhe(p, _revisoes(session, p.id))


@router.get("/planejamento/{plano_apoio_id}/auditoria", summary="Trilha de auditoria do plano")
def auditoria_plano(
    plano_apoio_id: str,
    principal: Principal = Depends(require(rbac.DECISION_READ)),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    p = get_scoped(session, PlanoDeApoio, plano_apoio_id, principal)
    entradas = session.scalars(select(AuditEntry).where(
        AuditEntry.tenant_id == principal.tenant_id,
        AuditEntry.subject_type == SubjectType.PLANEJAMENTO,
        AuditEntry.subject_id == p.id).order_by(AuditEntry.at))
    return [{"id": e.id, "acao": e.action, "ator_id": e.actor_id,
             "quando": as_utc(e.at).isoformat(), "de": e.old_state, "para": e.new_state,
             "motivo": e.reason, "dados": e.payload} for e in entradas]


@router.post("/planejamento/{plano_apoio_id}/revisao", status_code=status.HTTP_201_CREATED,
             summary="A pessoa responsável revisa o plano (não autoriza nada)")
def revisa_plano(
    plano_apoio_id: str,
    pedido: RevisaoIn,
    principal: Principal = Depends(require(rbac.DECISION_READ)),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    p = get_scoped(session, PlanoDeApoio, plano_apoio_id, principal)
    exigida = REVISAO_POR_TIPO[p.tipo]
    if not principal.can(exigida):
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            f"Revisar plano {p.tipo} exige {exigida}.")
    try:
        servico.revisar(session, p, revisor_id=principal.user_id, papel=principal.role.value,
                        decisao=pedido.decisao, comentario=pedido.comentario, agora=utcnow())
    except servico.RevisaoInvalidaError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    session.commit()
    return servico.detalhe(p, _revisoes(session, p.id))
