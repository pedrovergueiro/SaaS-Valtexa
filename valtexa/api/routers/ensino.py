"""O agrônomo ensinando a IA: vocabulário, lições do talhão e o painel do que ela aprendeu.

A lição em si nasce na fila (``POST /diagnoses/{id}/review`` com ``explicacao`` e ``lesoes``)
e na revisão do parecer (``POST /pareceres/{id}/revisao`` discordando). Aqui fica o que se
lê. A exportação do corte para o treino é da equipe (``/admin/datasets/.../export``).
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from pydantic import Field as PydField
from sqlalchemy import select
from sqlalchemy.orm import Session

from valtexa.api.deps import Principal, get_scoped, require, scoped
from valtexa.db import get_session
from valtexa.models import DatasetSample, Field, LicaoAgronomo, RegraAgronomo, utcnow
from valtexa.security import rbac
from valtexa.services import ensino, plant_map

router = APIRouter(tags=["ensino"])


@router.get("/ensino/vocabulario", summary="Sintomas sugeridos, terços e faces")
def vocabulario(
    rotulo: str | None = Query(default=None, max_length=120),
    _: Principal = Depends(require(rbac.DIAGNOSIS_READ)),
) -> dict[str, Any]:
    """Sugestão, não lista fechada: o agrônomo escreve o que viu."""
    return ensino.vocabulario(rotulo)


@router.get("/ensino/painel", summary="O que a IA aprendeu com você")
def painel(
    de: Literal["mim", "todos"] = Query(default="mim",
                                         description="As minhas lições ou as do cliente todo."),
    principal: Principal = Depends(require(rbac.DIAGNOSIS_READ)),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    corpo = ensino.painel(session, principal.tenant_id,
                          principal.user_id if de == "mim" else None)
    if de == "mim":
        corpo["confiabilidade"] = ensino.confiabilidade(session).get(
            principal.user_id, {"pares": 0, "concordancias": 0, "indice": None})
    return corpo


@router.get("/fields/{field_id}/licoes", summary="As lições do talhão, das mais recentes")
def licoes_do_talhao(
    field_id: str,
    limite: int = Query(default=100, ge=1, le=500),
    principal: Principal = Depends(require(rbac.DIAGNOSIS_READ)),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    get_scoped(session, Field, field_id, principal)
    linhas = session.scalars(scoped(
        select(LicaoAgronomo).where(LicaoAgronomo.field_id == field_id)
        .order_by(LicaoAgronomo.created_at.desc()).limit(limite), LicaoAgronomo, principal))
    return [ensino.resumo(x) for x in linhas]


# ---------------------------------------------------------------------------------------------
# Segunda opinião entre os agrônomos do cliente
# ---------------------------------------------------------------------------------------------


class OpiniaoIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rotulo: str = PydField(pattern=r"^[A-Za-z][A-Za-z0-9_]{0,63}$")
    comentario: str | None = PydField(default=None, max_length=2000)


@router.get("/ensino/segunda-opiniao", summary="Lições de colegas à espera da sua opinião")
def segunda_opiniao(
    limite: int = Query(default=50, ge=1, le=200),
    principal: Principal = Depends(require(rbac.DIAGNOSIS_REVIEW)),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    """As em disputa primeiro. Só as do seu cliente, e nunca as suas."""
    return ensino.pendentes_de_opiniao(session, revisor_id=principal.user_id,
                                       tenant_id=principal.tenant_id, limite=limite)


@router.post("/ensino/segunda-opiniao/{amostra_id}", status_code=status.HTTP_201_CREATED,
             summary="Você confirma ou corrige a lição de um colega")
def opinar(
    amostra_id: str,
    pedido: OpiniaoIn,
    principal: Principal = Depends(require(rbac.DIAGNOSIS_REVIEW)),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    amostra = session.get(DatasetSample, amostra_id)
    if amostra is None or amostra.tenant_id != principal.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Amostra não encontrada.")
    try:
        op = ensino.opinar(session, amostra=amostra, revisor=principal.user, origem="cliente",
                           rotulo=pedido.rotulo, comentario=pedido.comentario)
    except ensino.OpiniaoInvalidaError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    session.commit()
    return {"id": op.id, "concorda": op.concorda, "rotulo": op.rotulo}


# ---------------------------------------------------------------------------------------------
# Regras do agrônomo
# ---------------------------------------------------------------------------------------------


class RegraIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cultura: str = PydField(min_length=1, max_length=64)
    doenca: str = PydField(pattern=r"^[A-Za-z][A-Za-z0-9_]{0,63}$")
    texto: str = PydField(min_length=5, max_length=1000,
                          description="A regra nas suas palavras: 'bicho-mineiro sobe na seca'.")
    condicao: dict[str, Any] = PydField(
        description="{variavel: chuva_mm|molhamento_h|ur_media|t_media, janela_dias, operador: "
        "< ou >, valor} ou {variavel: mes, meses: [6, 7, 8]}.")
    efeito: Literal["aumenta", "diminui"]


def _regra_out(r: RegraAgronomo) -> dict[str, Any]:
    medida = r.medida or {}
    return {"id": r.id, "autor": r.autor_rotulo, "cultura": r.cultura, "doenca": r.doenca,
            "texto": r.texto, "condicao": r.condicao,
            "condicao_texto": ensino.descreve_condicao(r.condicao), "efeito": r.efeito,
            "ativa": r.ativa, "medida": medida,
            "veredito_texto": ensino.VEREDITOS.get(medida.get("veredito") or "nao_medida")}


@router.get("/ensino/regras", summary="As regras dos agrônomos do cliente, com a medida")
def regras(
    principal: Principal = Depends(require(rbac.DIAGNOSIS_READ)),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    linhas = session.scalars(scoped(select(RegraAgronomo).order_by(
        RegraAgronomo.created_at.desc()), RegraAgronomo, principal))
    return [_regra_out(r) for r in linhas]


@router.post("/ensino/regras", status_code=status.HTTP_201_CREATED,
             summary="Escreve uma regra que a plataforma vai medir no histórico")
def cria_regra(
    pedido: RegraIn,
    principal: Principal = Depends(require(rbac.DIAGNOSIS_REVIEW)),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    try:
        condicao = ensino.valida_condicao(pedido.condicao)
    except ensino.RegraInvalidaError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    r = RegraAgronomo(tenant_id=principal.tenant_id, autor_id=principal.user_id,
                      autor_rotulo=principal.user.full_name or principal.user.email,
                      cultura=pedido.cultura.strip().lower(), doenca=pedido.doenca,
                      texto=pedido.texto.strip(), condicao=condicao, efeito=pedido.efeito)
    session.add(r)
    session.commit()
    return _regra_out(r)


def _serie_do_talhao(field_id: str) -> dict[str, dict] | None:
    """A série dia a dia do talhão na inferência; fora do ar ou sem série, ``None``."""
    try:
        corpo = plant_map.clima(field_id, dias=True)
    except (plant_map.PlantMapUnavailableError, plant_map.PlantMapRefusedError):
        return None
    return {d["data"]: d for d in (corpo or {}).get("serie") or []} or None


@router.post("/ensino/regras/{regra_id}/medir", summary="Mede a regra no histórico do cliente")
def mede_regra(
    regra_id: str,
    principal: Principal = Depends(require(rbac.DIAGNOSIS_REVIEW)),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Com e sem a condição, a doença aparece mais? Teste de duas proporções nas observações
    com diagnóstico de confiança. Sem casos suficientes, diz que não dá para medir."""
    r = get_scoped(session, RegraAgronomo, regra_id, principal)
    r.medida = {**ensino.medir_regra(session, r, _serie_do_talhao),
                "medida_em": utcnow().isoformat()}
    session.commit()
    return _regra_out(r)


@router.post("/ensino/regras/{regra_id}/ativa", summary="Liga ou desliga a regra nos pareceres")
def ativa_regra(
    regra_id: str,
    ativa: bool = Query(),
    principal: Principal = Depends(require(rbac.DIAGNOSIS_REVIEW)),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    r = get_scoped(session, RegraAgronomo, regra_id, principal)
    r.ativa = ativa
    session.commit()
    return _regra_out(r)
