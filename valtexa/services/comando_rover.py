"""Centro de comando do Rover: comandos remotos, controle remoto, modelo fixado, painel.

Tudo que a equipe manda ao robô sai **assinado** com a chave da plataforma — o mesmo
envelope da missão (destinatário, sequência, nonce, validade) — e o robô confere antes de
obedecer (``valtexa_rover.runtime.comandos``). Comando e controle remoto têm sequências
**próprias** (o robô guarda uma para cada), para não disputarem com a da missão.

**Controle remoto (teleoperação).** O console renova o ponto de ajuste (velocidade e giro)
várias vezes por segundo enquanto o operador segura o comando; cada um vale 1 s. O robô
busca o ponto, confere a assinatura e passa à navegação; sem ponto válido, a navegação
para — o homem-morto. Limites: 0,5 m/s e 1,0 rad/s, e só em modo ``manual``. Pela
internet a latência é de centenas de milissegundos: serve para posicionar devagar, não
para dirigir em velocidade — para isso, o rádio local do rover.

**Modelo fixado.** A equipe pode fixar uma versão do registry num robô (teste em campo de
uma versão em homologação, comparação entre versões). O fixado vale nos talhões da
cultura dele e sobrepõe a escolha do talhão; só versão com artefato e hash.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from valtexa.models import (
    ActorType,
    Device,
    DeviceCommand,
    EdgeRecord,
    Mission,
    ModelVersion,
    SubjectType,
    TelemetrySample,
)
from valtexa.models.base import as_utc
from valtexa.models.comando import KINDS
from valtexa.security import signing
from valtexa.services import audit, ensaios

COMMAND_TTL = timedelta(minutes=2)
TELEOP_VALIDITY = timedelta(seconds=1)
TELEOP_MAX_V = 0.5
TELEOP_MAX_W = 1.0
MODOS = ("autonomo", "manual", "pausado", "parado")
PECAS = ("cameras", "gnss", "imu", "acelerador", "sistema", "disco", "navegacao", "lente")
MAX_RESULT_BYTES = 2_000_000


class ComandoInvalidoError(ValueError):
    """Tipo ou parâmetros que o robô não executaria."""


class TeleopRecusadoError(RuntimeError):
    """Controle remoto fora do modo manual ou acima dos limites."""


def _agora() -> datetime:
    return datetime.now(UTC)


# ---------------------------------------------------------------------------
# Comandos
# ---------------------------------------------------------------------------


def valida(kind: str, params: dict) -> dict:
    """Confere o pedido antes de assinar: o robô recusaria de qualquer jeito."""
    if kind not in KINDS:
        raise ComandoInvalidoError(f"Comando {kind!r}: use {', '.join(KINDS)}.")
    params = dict(params or {})
    if kind == "modo" and params.get("modo") not in MODOS:
        raise ComandoInvalidoError(f"modo: use {', '.join(MODOS)}.")
    if kind == "diagnostico":
        pecas = params.get("pecas")
        if pecas is not None:
            if not isinstance(pecas, list) or not pecas:
                raise ComandoInvalidoError("pecas: lista de peças, ou omita para todas.")
            desconhecidas = [p for p in pecas if p not in PECAS and not str(p).startswith(
                "camera:")]
            if desconhecidas:
                raise ComandoInvalidoError(f"peças desconhecidas: {desconhecidas}")
    if kind == "foto" and not params.get("camera_id"):
        raise ComandoInvalidoError("foto: diga a câmera (camera_id).")
    if kind == "config" and (not isinstance(params.get("rover_json"), dict)
                             or not params["rover_json"]):
        raise ComandoInvalidoError("config: rover_json com as seções a trocar.")
    if kind == "parar":
        params.setdefault("motivo", "parada pelo centro de comando")
    if kind == "ensaio":
        try:
            completos = ensaios.valida_pedido(str(params.get("ensaio") or ""),
                                              params.get("params"))
        except ensaios.EnsaioInvalidoError as exc:
            raise ComandoInvalidoError(str(exc)) from exc
        params = {"ensaio": params["ensaio"], "params": completos}
    if kind == "ensaio_cancelar" and not params.get("command_id"):
        raise ComandoInvalidoError("ensaio_cancelar: diga o comando do ensaio (command_id).")
    return params


def cria(session: Session, device: Device, kind: str, params: dict | None, *,
         user_id: str | None) -> DeviceCommand:
    params = valida(kind, params or {})
    sequencia = (session.scalar(select(func.max(DeviceCommand.sequence)).where(
        DeviceCommand.device_id == device.id)) or 0) + 1
    comando_id = uuid.uuid4().hex
    envelope = signing.command_envelope(
        command=f"device.{kind}", device_id=device.id,
        body={"command_id": comando_id, "kind": kind, "params": params},
        sequence=sequencia, ttl_seconds=int(COMMAND_TTL.total_seconds()))
    assinado = signing.sign_command(envelope)
    comando = DeviceCommand(id=comando_id, tenant_id=device.tenant_id, device_id=device.id,
                            kind=kind, params=params, state="pendente", sequence=sequencia,
                            envelope=assinado.as_dict(),
                            expires_at=datetime.fromisoformat(envelope["expires_at"]),
                            created_by=user_id)
    session.add(comando)
    audit.record(session, action=f"rover.command.{kind}", subject_type=SubjectType.DEVICE,
                 subject_id=device.id, actor_type=ActorType.USER, actor_id=user_id,
                 tenant_id=device.tenant_id, new_state="pendente",
                 reason=str(params)[:500])
    session.flush()
    return comando


def _expira(session: Session, device: Device, agora: datetime) -> None:
    for c in session.scalars(select(DeviceCommand).where(
            DeviceCommand.device_id == device.id,
            DeviceCommand.state.in_(("pendente", "entregue", "em_execucao")))):
        if c.state == "em_execucao":
            # Ensaio rodando: vale a duração estimada + folga, contada da entrega.
            prazo = as_utc(c.delivered_at or c.created_at) + ensaios.prazo_de_execucao(
                str((c.params or {}).get("ensaio")), (c.params or {}).get("params") or {})
            if prazo <= agora:
                c.state, c.finished_at = "falhou", agora
                c.error = "sem notícia do robô dentro do prazo do ensaio"
        elif as_utc(c.expires_at) <= agora:
            c.state, c.finished_at = "expirado", agora


def pendentes(session: Session, device: Device) -> list[dict]:
    """O que o robô deve executar agora (marca como entregue)."""
    agora = _agora()
    _expira(session, device, agora)
    saida = []
    for c in session.scalars(select(DeviceCommand).where(
            DeviceCommand.device_id == device.id, DeviceCommand.state == "pendente")
            .order_by(DeviceCommand.sequence)):
        c.state, c.delivered_at = "entregue", agora
        saida.append(c.envelope)
    session.flush()
    return saida


def resultado(session: Session, device: Device, command_id: str, *, ok: bool,
              result: dict | None, error: str | None) -> DeviceCommand:
    comando = session.get(DeviceCommand, command_id)
    if comando is None or comando.device_id != device.id:
        raise KeyError(command_id)
    if comando.state not in ("pendente", "entregue", "em_execucao"):
        return comando  # reenvio do robô depois de já registrado: idempotente
    agora = _agora()
    comando.state = "concluido" if ok else "falhou"
    comando.finished_at = agora
    comando.result = result
    comando.error = None if error is None else str(error)[:4000]
    if comando.kind == "ensaio":
        ensaios.registra_do_robo(session, comando, ok=ok, laudo=result, erro=error)
    if ok and comando.kind == "modo":
        device.control_mode = comando.params.get("modo")
    if ok and comando.kind == "parar":
        device.control_mode = "parado"
        device.teleop_v, device.teleop_w, device.teleop_until = 0.0, 0.0, agora
    session.flush()
    return comando


def cancela(session: Session, comando: DeviceCommand) -> None:
    if comando.state != "pendente":
        raise ComandoInvalidoError("Só comando ainda não entregue pode ser cancelado.")
    comando.state, comando.finished_at = "cancelado", _agora()


def progresso(session: Session, device: Device, command_id: str, *, fracao: float,
              etapa: str, parcial: dict | None) -> DeviceCommand:
    """O robô conta o andamento de um ensaio: o comando passa a "em execução"."""
    comando = session.get(DeviceCommand, command_id)
    if comando is None or comando.device_id != device.id or comando.kind != "ensaio":
        raise KeyError(command_id)
    if comando.state in ("entregue", "em_execucao"):
        comando.state = "em_execucao"
        comando.progress = {"fracao": max(0.0, min(1.0, float(fracao))), "etapa": etapa[:200],
                            "parcial": parcial, "at": _agora().isoformat()}
        session.flush()
    return comando


def cancela_ensaio(session: Session, device: Device, comando: DeviceCommand, *,
                   user_id: str | None) -> dict:
    """Ensaio ainda na fila: cancela aqui. Já no robô: manda ``ensaio_cancelar`` assinado."""
    if comando.kind != "ensaio":
        raise ComandoInvalidoError("Este comando não é um ensaio.")
    if comando.state == "pendente":
        cancela(session, comando)
        return {"id": comando.id, "state": comando.state}
    if comando.state not in ("entregue", "em_execucao"):
        raise ComandoInvalidoError(f"O ensaio já terminou ({comando.state}).")
    pedido = cria(session, device, "ensaio_cancelar", {"command_id": comando.id},
                  user_id=user_id)
    return {"id": comando.id, "state": comando.state, "cancel_command_id": pedido.id}


# ---------------------------------------------------------------------------
# Controle remoto
# ---------------------------------------------------------------------------


def teleop(session: Session, device: Device, v: float, w: float, *, user_id: str | None) -> dict:
    if device.control_mode != "manual":
        raise TeleopRecusadoError(
            "Controle remoto só em modo manual: mande o comando 'modo' = manual e espere o "
            "robô confirmar.")
    if abs(v) > TELEOP_MAX_V or abs(w) > TELEOP_MAX_W:
        raise TeleopRecusadoError(
            f"Limites do controle remoto: {TELEOP_MAX_V} m/s e {TELEOP_MAX_W} rad/s.")
    agora = _agora()
    device.teleop_v, device.teleop_w = float(v), float(w)
    device.teleop_until = agora + TELEOP_VALIDITY
    device.teleop_seq = (device.teleop_seq or 0) + 1
    device.teleop_by = user_id
    session.flush()
    return estado_teleop(device, agora)


def teleop_para(session: Session, device: Device, *, user_id: str | None) -> dict:
    """Zera o ponto (o robô recebe um "pare" explícito, além do homem-morto)."""
    agora = _agora()
    device.teleop_v, device.teleop_w = 0.0, 0.0
    device.teleop_until = agora + TELEOP_VALIDITY
    device.teleop_seq = (device.teleop_seq or 0) + 1
    device.teleop_by = user_id
    session.flush()
    return estado_teleop(device, agora)


def estado_teleop(device: Device, agora: datetime | None = None) -> dict:
    agora = agora or _agora()
    ate = as_utc(device.teleop_until)
    return {"v": device.teleop_v, "w": device.teleop_w, "seq": device.teleop_seq,
            "valid_until": ate.isoformat() if ate else None,
            "active": bool(ate and ate > agora)}


def teleop_envelope(device: Device) -> dict | None:
    """O ponto de ajuste assinado para o robô, ou ``None`` se vencido (homem-morto)."""
    agora = _agora()
    ate = as_utc(device.teleop_until)
    if not ate or ate <= agora:
        return None
    envelope = signing.command_envelope(
        command="device.teleop", device_id=device.id,
        body={"v": device.teleop_v or 0.0, "w": device.teleop_w or 0.0,
              "valid_until": ate.isoformat()},
        sequence=device.teleop_seq or 0,
        ttl_seconds=max(1, int((ate - agora).total_seconds()) + 1))
    return signing.sign_command(envelope).as_dict()


# ---------------------------------------------------------------------------
# Modelo fixado
# ---------------------------------------------------------------------------


def fixa_modelo(session: Session, device: Device, model_key: str | None, version: str | None,
                *, user_id: str | None) -> ModelVersion | None:
    antes = (f"{device.pinned_model_key}@{device.pinned_model_version}"
             if device.pinned_model_key else "talhão")
    if not model_key:
        device.pinned_model_key = device.pinned_model_version = None
        linha = None
    else:
        linha = session.scalars(select(ModelVersion).where(
            ModelVersion.model_key == model_key, ModelVersion.version == version)).first()
        if linha is None:
            raise ComandoInvalidoError(f"Versão {model_key}@{version} não está no registry.")
        if not (linha.original_artifact_sha256 or linha.optimized_artifact_sha256):
            raise ComandoInvalidoError(
                "Versão sem artefato com hash: o robô não carregaria (registre o artefato).")
        device.pinned_model_key, device.pinned_model_version = model_key, version
    audit.record(session, action="rover.model_pinned", subject_type=SubjectType.DEVICE,
                 subject_id=device.id, actor_type=ActorType.USER, actor_id=user_id,
                 tenant_id=device.tenant_id, old_state=antes,
                 new_state=f"{model_key}@{version}" if model_key else "talhão")
    session.flush()
    return linha


# ---------------------------------------------------------------------------
# Painel
# ---------------------------------------------------------------------------


def comandos_recentes(session: Session, device: Device, limite: int = 30) -> list[dict]:
    _expira(session, device, _agora())
    return [{
        "id": c.id, "kind": c.kind, "params": c.params, "state": c.state,
        "sequence": c.sequence, "created_at": _iso(c.created_at),
        "delivered_at": _iso(c.delivered_at), "finished_at": _iso(c.finished_at),
        "result": _sem_amostras(c), "error": c.error, "progress": c.progress,
    } for c in session.scalars(select(DeviceCommand).where(DeviceCommand.device_id == device.id)
                               .order_by(DeviceCommand.created_at.desc()).limit(limite))]


def painel(session: Session, device: Device, snapshot: dict) -> dict:
    """Tudo de um rover numa resposta: estado, peças, IA, missão, comandos, telemetria."""
    from valtexa.services import model_registry

    agora = _agora()
    desde = agora - timedelta(hours=2)
    serie = [{"t": _iso(t.recorded_at), "battery_percent": t.battery_percent,
              "temperature_c": t.temperature_c, "speed_ms": t.speed_ms,
              "link_quality": t.link_quality, "rtk_fix": str(t.rtk_fix.value if hasattr(
                  t.rtk_fix, "value") else t.rtk_fix)}
             for t in session.scalars(select(TelemetrySample).where(
                 TelemetrySample.device_id == device.id, TelemetrySample.recorded_at >= desde)
                 .order_by(TelemetrySample.recorded_at))]
    missao = session.get(Mission, device.active_mission_id) if device.active_mission_id else None
    resultados = [{
        "record_id": r.record_id, "type": r.type, "label": r.label, "confidence": r.confidence,
        "occurred_at": _iso(r.occurred_at),
        "camera_id": ((r.payload or {}).get("frame") or {}).get("camera_id"),
        "evidence": ((r.payload or {}).get("result") or {}).get("evidence"),
    } for r in session.scalars(select(EdgeRecord).where(
        EdgeRecord.device_id == device.id, EdgeRecord.kind == "result")
        .order_by(EdgeRecord.occurred_at.desc()).limit(12))]
    designados = [{"field_id": d.field_id, "field_name": d.field_name, "crop": d.crop,
                   "model": d.etiqueta, "reason": d.reason}
                  for d in model_registry.designados(session, device)]
    return {
        "device": snapshot,
        "health": device.health,
        "health_reported_at": _iso(device.health_reported_at),
        "control_mode": device.control_mode,
        "teleop": estado_teleop(device, agora),
        "teleop_limits": {"v_ms": TELEOP_MAX_V, "w_rad_s": TELEOP_MAX_W,
                          "validity_s": TELEOP_VALIDITY.total_seconds()},
        "pinned_model": ({"model_key": device.pinned_model_key,
                          "version": device.pinned_model_version}
                         if device.pinned_model_key else None),
        "designated": designados,
        "mission": None if missao is None else {
            "id": missao.id, "state": missao.state.value, "kind": missao.kind.value,
            "field_id": missao.field_id, "started_at": _iso(missao.started_at)},
        "commands": comandos_recentes(session, device),
        "recent_results": resultados,
        "telemetry": serie,
        "parts": PECAS,
    }


def _sem_amostras(c: DeviceCommand) -> dict | None:
    """O painel é buscado a cada 2 s: o laudo do ensaio vai sem as amostras brutas."""
    if c.kind == "ensaio" and isinstance(c.result, dict):
        return {k: v for k, v in c.result.items() if k != "amostras"}
    return c.result


def _iso(valor: datetime | None) -> str | None:
    return as_utc(valor).isoformat() if valor else None
