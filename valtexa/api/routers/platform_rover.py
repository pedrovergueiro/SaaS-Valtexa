"""Centro de comando do Rover (equipe ValTexa) e o lado do robô do mesmo canal.

Equipe (``/platform/rovers/...``): painel, comandos assinados, controle remoto, modelo
fixado. Ler exige ``platform:fleet:read``; mandar, ``platform:rover:control``.

Robô (``/device/commands``, ``/device/teleop``): busca o que executar, devolve o
resultado e busca o ponto do controle remoto. Funciona também com o robô em manutenção:
é justamente quando o técnico testa peça por peça.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from valtexa.api.deps import DeviceCaller, PlatformCaller, current_device, require_platform
from valtexa.api.middleware import RAW_BODY_KEY
from valtexa.api.routers.fleet import device_snapshot
from valtexa.db import get_session
from valtexa.models import ActorType, Device, DeviceCommand, ModelVersion, SubjectType
from valtexa.models import Field as Talhao
from valtexa.models.enums import DeviceKind
from valtexa.security import rbac
from valtexa.services import (
    audit,
    chave_de_enlace,
    cobertura_talhao,
    comando_rover,
    estacao_base,
    video_ao_vivo,
)

router = APIRouter(tags=["centro de comando"])

LER = require_platform(rbac.PLATFORM_FLEET_READ)
MANDAR = require_platform(rbac.PLATFORM_ROVER_CONTROL)


class ComandoIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str = Field(description="diagnostico, foto, modo, parar, config, "
                                  "recarregar_modelos, reiniciar")
    params: dict[str, Any] = Field(default_factory=dict)


class TeleopIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    v: float = Field(allow_inf_nan=False, description="m/s; positivo = para a frente.")
    w: float = Field(allow_inf_nan=False, description="rad/s; positivo = para a esquerda.")


class ModeloIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_key: str | None = Field(default=None, max_length=64,
                                  description="Nulo volta à escolha do talhão.")
    version: str | None = Field(default=None, max_length=32)


class VideoIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cameras: list[str] = Field(min_length=1, max_length=video_ao_vivo.MAX_CAMERAS)
    fps: float = Field(default=4.0, allow_inf_nan=False)
    lado: int = Field(default=640, description="Lado maior da imagem, em px.")


class ChaveDeEnlaceIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nome: str = Field(min_length=1, max_length=64)
    enlace_pub: str = Field(min_length=64, max_length=64)
    assinatura: str = Field(min_length=128, max_length=128)


class ResultadoIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: bool
    result: dict[str, Any] | None = None
    error: str | None = Field(default=None, max_length=4000)


def _rover(session: Session, device_id: str) -> Device:
    robo = session.get(Device, device_id)
    if robo is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Rover não encontrado.")
    return robo


# ---------------------------------------------------------------------------
# Equipe
# ---------------------------------------------------------------------------


@router.get("/platform/bases", summary="Bases da fazenda: internet, filas, rádios, Rovers")
def lista_bases(tenant_id: str | None = None, caller: PlatformCaller = Depends(LER),
                session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    return [{**estacao_base.resumo(b), "talhoes": cobertura_talhao.talhoes_da_base(session, b)}
            for b in estacao_base.bases(session, tenant_id)]


@router.get("/platform/bases/{device_id}", summary="Uma base da fazenda")
def uma_base(device_id: str, caller: PlatformCaller = Depends(LER),
             session: Session = Depends(get_session)) -> dict[str, Any]:
    base = next((b for b in estacao_base.bases(session) if b.id == device_id), None)
    if base is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Base não encontrada.")
    return {**estacao_base.resumo(base),
            "talhoes": cobertura_talhao.talhoes_da_base(session, base)}


@router.get("/platform/fields/{field_id}/cobertura",
            summary="O mapa de cobertura do rádio de um talhão (o último levantamento da base)")
def cobertura_do_talhao(field_id: str, caller: PlatformCaller = Depends(LER),
                        session: Session = Depends(get_session)) -> dict[str, Any]:
    talhao = session.get(Talhao, field_id)
    if talhao is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Talhão não encontrado.")
    return {"field_id": talhao.id, "name": talhao.name, "mapa": talhao.cobertura,
            "cobertura_em": talhao.cobertura_em.isoformat() if talhao.cobertura_em else None}


@router.post("/platform/rovers/{device_id}/video",
             summary="Liga ou renova o vídeo ao vivo (vence em segundos sem renovar)")
def assiste(payload: VideoIn, device_id: str, caller: PlatformCaller = Depends(LER),
            session: Session = Depends(get_session)) -> dict[str, Any]:
    robo = _rover(session, device_id)
    try:
        pedido, novo = video_ao_vivo.pedir(robo.id, payload.cameras, payload.fps,
                                           payload.lado, user_id=caller.user.id)
    except video_ao_vivo.VideoInvalidoError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    if novo:  # quem viu as câmeras da fazenda, e quando, fica na trilha do cliente
        audit.record(session, action="rover.video.assistir", subject_type=SubjectType.DEVICE,
                     subject_id=robo.id, actor_type=ActorType.USER, actor_id=caller.user.id,
                     tenant_id=robo.tenant_id, reason=", ".join(pedido["cameras"]))
        session.commit()
    return pedido


@router.delete("/platform/rovers/{device_id}/video", status_code=status.HTTP_204_NO_CONTENT,
               summary="Desliga o vídeo ao vivo")
def para_de_assistir(device_id: str, caller: PlatformCaller = Depends(LER),
                     session: Session = Depends(get_session)) -> Response:
    video_ao_vivo.parar(_rover(session, device_id).id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/platform/rovers/{device_id}/video/{camera_id}", response_model=None,
            summary="O último quadro ao vivo de uma câmera (JPEG)",
            responses={204: {"description": "Sem quadro recente desta câmera."}})
def quadro_ao_vivo(device_id: str, camera_id: str, caller: PlatformCaller = Depends(LER),
                   session: Session = Depends(get_session)) -> Response:
    robo = _rover(session, device_id)
    achado = video_ao_vivo.quadro(robo.id, camera_id)
    if achado is None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    jpeg, meta = achado
    return Response(jpeg, media_type="image/jpeg", headers={
        "Cache-Control": "no-store",
        "X-Capturado-Em": meta.get("capturado_em") or "",
        "X-Recebido-Em": meta.get("recebido_em") or "",
        "X-Seq": str(meta.get("seq") if meta.get("seq") is not None else "")})


@router.get("/platform/rovers/{device_id}/painel", summary="Tudo de um rover numa resposta")
def painel(device_id: str, caller: PlatformCaller = Depends(LER),
           session: Session = Depends(get_session)) -> dict[str, Any]:
    robo = _rover(session, device_id)
    corpo = comando_rover.painel(session, robo, device_snapshot(session, robo))
    session.commit()  # comandos vencidos viram "expirado" ao olhar
    return corpo


@router.post("/platform/rovers/{device_id}/comandos", status_code=status.HTTP_201_CREATED,
             summary="Manda um comando assinado ao rover")
def manda(payload: ComandoIn, device_id: str, caller: PlatformCaller = Depends(MANDAR),
          session: Session = Depends(get_session)) -> dict[str, Any]:
    robo = _rover(session, device_id)
    try:
        comando = comando_rover.cria(session, robo, payload.kind, payload.params,
                                     user_id=caller.user.id)
    except comando_rover.ComandoInvalidoError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    session.commit()
    return {"id": comando.id, "kind": comando.kind, "state": comando.state,
            "sequence": comando.sequence, "expires_at": comando.expires_at.isoformat()}


@router.get("/platform/rovers/{device_id}/comandos", summary="Comandos recentes e respostas")
def comandos(device_id: str, caller: PlatformCaller = Depends(LER),
             session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    robo = _rover(session, device_id)
    saida = comando_rover.comandos_recentes(session, robo, limite=100)
    session.commit()
    return saida


@router.post("/platform/rovers/{device_id}/comandos/{command_id}/cancelar",
             summary="Cancela um comando ainda não entregue")
def cancela(device_id: str, command_id: str, caller: PlatformCaller = Depends(MANDAR),
            session: Session = Depends(get_session)) -> dict[str, str]:
    comando = session.get(DeviceCommand, command_id)
    if comando is None or comando.device_id != device_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Comando não encontrado.")
    try:
        comando_rover.cancela(session, comando)
    except comando_rover.ComandoInvalidoError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    session.commit()
    return {"id": comando.id, "state": comando.state}


@router.post("/platform/rovers/{device_id}/teleop",
             summary="Controle remoto: renova o ponto de ajuste (vale 1 s)")
def teleop(payload: TeleopIn, device_id: str, caller: PlatformCaller = Depends(MANDAR),
           session: Session = Depends(get_session)) -> dict[str, Any]:
    robo = _rover(session, device_id)
    try:
        estado = comando_rover.teleop(session, robo, payload.v, payload.w, user_id=caller.user.id)
    except comando_rover.TeleopRecusadoError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    session.commit()
    return estado


@router.post("/platform/rovers/{device_id}/teleop/parar", summary="Controle remoto: pare")
def teleop_parar(device_id: str, caller: PlatformCaller = Depends(MANDAR),
                 session: Session = Depends(get_session)) -> dict[str, Any]:
    robo = _rover(session, device_id)
    estado = comando_rover.teleop_para(session, robo, user_id=caller.user.id)
    session.commit()
    return estado


@router.get("/platform/rovers/{device_id}/modelos",
            summary="Versões do registry que podem ser fixadas neste rover")
def modelos(device_id: str, caller: PlatformCaller = Depends(LER),
            session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    _rover(session, device_id)
    return [{"model_key": m.model_key, "version": m.version, "name": m.name,
             "state": m.state.value, "crops": m.crops or [], "platform": m.platform.value,
             "optimized": bool(m.optimized_artifact_sha256)}
            for m in session.scalars(select(ModelVersion).order_by(
                ModelVersion.model_key, ModelVersion.version))
            if m.original_artifact_sha256 or m.optimized_artifact_sha256]


@router.put("/platform/rovers/{device_id}/modelo",
            summary="Fixa (ou solta) o modelo de IA deste rover")
def fixa_modelo(payload: ModeloIn, device_id: str, caller: PlatformCaller = Depends(MANDAR),
                session: Session = Depends(get_session)) -> dict[str, Any]:
    robo = _rover(session, device_id)
    try:
        comando_rover.fixa_modelo(session, robo, payload.model_key, payload.version,
                                  user_id=caller.user.id)
        # O robô busca as designações de novo agora, sem esperar a próxima missão.
        comando_rover.cria(session, robo, "recarregar_modelos", {}, user_id=caller.user.id)
    except comando_rover.ComandoInvalidoError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    session.commit()
    return {"pinned_model": ({"model_key": robo.pinned_model_key,
                              "version": robo.pinned_model_version}
                             if robo.pinned_model_key else None)}


# ---------------------------------------------------------------------------
# Robô
# ---------------------------------------------------------------------------


@router.get("/device/commands", summary="Comandos assinados que o robô deve executar")
def device_commands(response: Response, caller: DeviceCaller = Depends(current_device),
                    session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    saida = comando_rover.pendentes(session, caller.device)
    session.commit()
    video = video_ao_vivo.cabecalho(caller.device.id)
    if video:  # alguém assiste: o robô fica sabendo na consulta que já faz
        response.headers[video_ao_vivo.CABECALHO] = video
    return saida


@router.put("/device/enlace/chave",
            summary="O robô publica a chave do rádio da fazenda (assinada pela identidade dele)")
def device_enlace_chave(payload: ChaveDeEnlaceIn, caller: DeviceCaller = Depends(current_device),
                        session: Session = Depends(get_session)) -> dict[str, Any]:
    try:
        salvo = chave_de_enlace.publica(session, caller.device, caller.credential,
                                        payload.model_dump())
    except chave_de_enlace.ChaveInvalidaError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    session.commit()
    return salvo


@router.get("/device/base/pares",
            summary="A base da fazenda busca as chaves de rádio dos robôs que ela atende")
def device_base_pares(caller: DeviceCaller = Depends(current_device),
                      session: Session = Depends(get_session)) -> dict[str, Any]:
    if caller.device.model is None or caller.device.model.kind != DeviceKind.GATEWAY:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Só a base da fazenda busca as chaves.")
    return chave_de_enlace.pares_da_base(session, caller.device)


@router.put("/device/base/cobertura/{field_id}",
            summary="A base manda o mapa de cobertura do rádio de um talhão (levantamento)")
def device_base_cobertura(field_id: str, payload: dict[str, Any],
                          caller: DeviceCaller = Depends(current_device),
                          session: Session = Depends(get_session)) -> dict[str, Any]:
    if caller.device.model is None or caller.device.model.kind != DeviceKind.GATEWAY:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Só a base da fazenda manda cobertura.")
    talhao = session.get(Talhao, field_id)
    try:
        if talhao is None:
            raise LookupError
        mapa = cobertura_talhao.guarda(session, caller.device, talhao, payload)
    except LookupError as exc:  # 404 também para talhão de outro cliente: não dá pista
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Talhão não encontrado.") from exc
    except cobertura_talhao.CoberturaInvalidaError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    session.commit()
    return {"field_id": talhao.id, "contagem": mapa["contagem"],
            "zonas_mortas": len(mapa["zonas_mortas"])}


@router.post("/device/video/{camera_id}", summary="O robô manda um quadro ao vivo (JPEG)",
             responses={404: {"description": "Ninguém assiste esta câmera: pare de mandar."}})
def device_video(camera_id: str, request: Request,
                 x_capturado_em: str | None = Header(default=None),
                 x_seq: int | None = Header(default=None),
                 caller: DeviceCaller = Depends(current_device)) -> dict[str, Any]:
    corpo = request.scope.get(RAW_BODY_KEY) or b""
    try:
        pedido = video_ao_vivo.recebe(caller.device.id, camera_id, corpo,
                                      capturado_em=x_capturado_em, seq=x_seq)
    except video_ao_vivo.VideoInvalidoError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    if pedido is None:  # 404, não 409: resposta a quem não deve não dá pista de estado
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ninguém assiste esta câmera.")
    return {k: pedido[k] for k in ("cameras", "fps", "lado", "ate")}


@router.post("/device/commands/{command_id}/result", summary="O robô devolve o resultado")
def device_command_result(payload: ResultadoIn, command_id: str,
                          caller: DeviceCaller = Depends(current_device),
                          session: Session = Depends(get_session)) -> dict[str, str]:
    if len(str(payload.result or "")) > comando_rover.MAX_RESULT_BYTES:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "Resultado grande demais.")
    try:
        comando = comando_rover.resultado(session, caller.device, command_id, ok=payload.ok,
                                          result=payload.result, error=payload.error)
    except KeyError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Comando não encontrado.") from exc
    session.commit()
    return {"id": comando.id, "state": comando.state}


@router.get("/device/teleop", summary="Ponto de ajuste do controle remoto, assinado",
            response_model=None,
            responses={204: {"description": "Sem controle remoto ativo: pare."}})
def device_teleop(caller: DeviceCaller = Depends(current_device)) -> Response | dict:
    envelope = comando_rover.teleop_envelope(caller.device)
    if envelope is None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    return envelope

