"""Validação do Rover: ensaios automáticos, resultados com veredito do servidor e portões.

Equipe (``/platform/...``): catálogo, mandar e cancelar ensaio (comando assinado
``ensaio``), histórico, portões por fase e a FASE 5 a partir da validação de campo. Ler
exige ``platform:fleet:read``; mandar, ``platform:rover:control``.

Robô (``/device/...``): progresso do ensaio em curso e o eco do ensaio de rede.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from valtexa.api.deps import (
    DeviceCaller,
    PlatformCaller,
    _raw_body,
    current_device,
    require_platform,
)
from valtexa.db import get_session
from valtexa.models import ActorType, Device, DeviceCommand, EnsaioResultado, Mission, SubjectType
from valtexa.models import Field as Talhao
from valtexa.security import rbac
from valtexa.services import audit, comando_rover, ensaios, plant_map, validacao_campo

router = APIRouter(tags=["validação do rover"])

LER = require_platform(rbac.PLATFORM_FLEET_READ)
MANDAR = require_platform(rbac.PLATFORM_ROVER_CONTROL)
ECO_MAX_BYTES = 20 * 1024 * 1024


class EnsaioIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ensaio: str = Field(max_length=32, description="calor, cameras, profundidade, gnss, imu, "
                                                   "rede, energia, parada, homem_morto")
    params: dict[str, Any] = Field(default_factory=dict)


class ValidacaoAgronomicaIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field_id: str = Field(max_length=32)
    mission_id: str = Field(max_length=32)
    params: dict[str, Any] = Field(default_factory=dict,
                                   description="Limites mais rígidos que o portão, se quiser.")


class ProgressoIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fracao: float = Field(ge=0, le=1, allow_inf_nan=False)
    etapa: str = Field(default="", max_length=200)
    parcial: dict[str, Any] | None = None


def _rover(session: Session, device_id: str) -> Device:
    robo = session.get(Device, device_id)
    if robo is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Rover não encontrado.")
    return robo


# ---------------------------------------------------------------------------
# Equipe
# ---------------------------------------------------------------------------


@router.get("/platform/ensaios/catalogo", summary="Ensaios, limites do portão e fases")
def catalogo(caller: PlatformCaller = Depends(LER)) -> dict[str, Any]:
    return {"ensaios": ensaios.catalogo(), "fases": ensaios.FASES,
            "cameras_no_portao": ensaios.CAMERAS_NO_PORTAO,
            "distancias_do_portao_mm": list(ensaios.DISTANCIAS_DO_PORTAO_MM)}


@router.post("/platform/rovers/{device_id}/ensaios", status_code=status.HTTP_201_CREATED,
             summary="Manda um ensaio ao rover (comando assinado)")
def manda_ensaio(payload: EnsaioIn, device_id: str, caller: PlatformCaller = Depends(MANDAR),
                 session: Session = Depends(get_session)) -> dict[str, Any]:
    robo = _rover(session, device_id)
    try:
        comando = comando_rover.cria(session, robo, "ensaio",
                                     {"ensaio": payload.ensaio, "params": payload.params},
                                     user_id=caller.user.id)
    except comando_rover.ComandoInvalidoError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    session.commit()
    return {"id": comando.id, "kind": comando.kind, "state": comando.state,
            "params": comando.params, "expires_at": comando.expires_at.isoformat()}


@router.post("/platform/rovers/{device_id}/ensaios/{command_id}/cancelar",
             summary="Cancela um ensaio (na fila ou já rodando no robô)")
def cancela_ensaio(device_id: str, command_id: str, caller: PlatformCaller = Depends(MANDAR),
                   session: Session = Depends(get_session)) -> dict[str, Any]:
    robo = _rover(session, device_id)
    comando = session.get(DeviceCommand, command_id)
    if comando is None or comando.device_id != robo.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ensaio não encontrado.")
    try:
        saida = comando_rover.cancela_ensaio(session, robo, comando, user_id=caller.user.id)
    except comando_rover.ComandoInvalidoError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    session.commit()
    return saida


@router.get("/platform/rovers/{device_id}/ensaios", summary="Resultados dos ensaios do rover")
def resultados(device_id: str, caller: PlatformCaller = Depends(LER),
               session: Session = Depends(get_session)) -> dict[str, Any]:
    robo = _rover(session, device_id)
    em_curso = [c for c in comando_rover.comandos_recentes(session, robo, limite=50)
                if c["kind"] == "ensaio" and c["state"] in ("pendente", "entregue",
                                                             "em_execucao")]
    session.commit()  # comandos vencidos viram "expirado"/"falhou" ao olhar
    return {"resultados": ensaios.historico(session, robo), "em_curso": em_curso}


@router.get("/platform/rovers/{device_id}/ensaios/{resultado_id}",
            summary="Um resultado, com a prévia que o robô mandou")
def resultado(device_id: str, resultado_id: str, caller: PlatformCaller = Depends(LER),
              session: Session = Depends(get_session)) -> dict[str, Any]:
    linha = session.get(EnsaioResultado, resultado_id)
    if linha is None or linha.device_id != device_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Resultado não encontrado.")
    return ensaios.como_dict(linha, com_laudo=True)


@router.get("/platform/rovers/{device_id}/portoes", summary="Portões de cada fase")
def portoes(device_id: str,
            aceitar_simulado: bool = Query(default=False,
                                           description="Conta resultado simulado (simulador)."),
            caller: PlatformCaller = Depends(LER),
            session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    return ensaios.portoes(session, _rover(session, device_id),
                           aceitar_simulado=aceitar_simulado)


@router.post("/platform/rovers/{device_id}/ensaios/validacao-agronomica",
             status_code=status.HTTP_201_CREATED,
             summary="FASE 5: resultado a partir do relatório Rover contra agrônomo")
def validacao_agronomica(payload: ValidacaoAgronomicaIn, device_id: str,
                         caller: PlatformCaller = Depends(MANDAR),
                         session: Session = Depends(get_session)) -> dict[str, Any]:
    robo = _rover(session, device_id)
    talhao = session.get(Talhao, payload.field_id)
    missao = session.get(Mission, payload.mission_id)
    if (talhao is None or talhao.tenant_id != robo.tenant_id or missao is None
            or missao.field_id != talhao.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            "Talhão ou missão não encontrado no cliente deste rover.")
    if missao.device_id != robo.id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            "Esta missão foi feita por outro rover.")
    try:
        relatorio = validacao_campo.relatorio(session, talhao, missao.id)
    except plant_map.PlantMapUnavailableError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    try:
        linha = ensaios.registra_validacao_agronomica(session, robo, relatorio, payload.params,
                                                      user_id=caller.user.id)
    except ensaios.EnsaioInvalidoError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    audit.record(session, action="rover.ensaio.validacao_agronomica",
                 subject_type=SubjectType.DEVICE, subject_id=robo.id,
                 actor_type=ActorType.USER, actor_id=caller.user.id, tenant_id=robo.tenant_id,
                 new_state=linha.status, reason=f"talhão {talhao.id}, missão {missao.id}")
    session.commit()
    return ensaios.como_dict(linha)


# ---------------------------------------------------------------------------
# Robô
# ---------------------------------------------------------------------------


@router.post("/device/commands/{command_id}/progresso",
             summary="O robô conta o andamento do ensaio")
def device_progresso(payload: ProgressoIn, command_id: str,
                     caller: DeviceCaller = Depends(current_device),
                     session: Session = Depends(get_session)) -> dict[str, str]:
    if len(str(payload.parcial or "")) > 20_000:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "Parcial grande demais.")
    try:
        comando = comando_rover.progresso(session, caller.device, command_id,
                                          fracao=payload.fracao, etapa=payload.etapa,
                                          parcial=payload.parcial)
    except KeyError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ensaio não encontrado.") from exc
    session.commit()
    return {"id": comando.id, "state": comando.state}


@router.get("/device/ensaio/eco", summary="Ensaio de rede: ida e volta (e descida)",
            response_class=Response)
def device_eco(bytes_: int = Query(default=0, alias="bytes", ge=0, le=ECO_MAX_BYTES),
               caller: DeviceCaller = Depends(current_device)) -> Response:
    return Response(content=b"\0" * bytes_, media_type="application/octet-stream")


@router.post("/device/ensaio/eco", summary="Ensaio de rede: subida (descarta o corpo)")
async def device_eco_subida(request: Request,
                            caller: DeviceCaller = Depends(current_device)) -> dict[str, int]:
    corpo = await _raw_body(request)
    if len(corpo) > ECO_MAX_BYTES:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "Carga grande demais.")
    return {"recebidos": len(corpo)}
