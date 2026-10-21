"""Orçamento de dados por robô: o teto da Starlink de cada Rover e o relatório de consumo.

Desde a rodada 4 cada Rover tem a sua Starlink e fala direto com a plataforma
(``docs/historico/RODADA4.md``). O volume que ele manda é custo e é limite. Duas fontes,
lado a lado, de propósito:

* **o que o Rover contou** (``device.health["dados"]``, a saúde que sobe na telemetria, e o
  ``dados`` do ``MISSION_COMPLETED``): tudo o que trafegou pela Starlink, subida e descida,
  com a sobrecarga de cabeçalho estimada — é o número que se compara com a fatura;
* **o que a plataforma recebeu** (:func:`medido_na_plataforma`): os bytes dos arquivos que
  chegaram inteiros (``edge_upload``), o tamanho do JSON dos registros (``edge_record``) e a
  contagem de amostras de telemetria — sem cabeçalho, sem descida, sem o que se perdeu.

A diferença entre as duas é informação (retransmissão, descida, OTA), não erro.

O teto (:func:`definir`) vive em ``device.orcamento_dados`` e desce **dentro da missão
assinada** (``mission_command_body``): o Rover só aceita teto que veio assinado pela
plataforma, e ele vale por cima do ``rover.json``. Sem teto da plataforma, vale o do robô.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import String, cast, func, select
from sqlalchemy.orm import Session

from valtexa.models import ActorType, Device, DeviceKind, SubjectType
from valtexa.models.edge import EdgeRecord, EdgeUpload
from valtexa.models.operations import TelemetrySample
from valtexa.services import audit

MAX_BYTES_DIA = 1_000_000_000_000
"""1 TB/dia: acima disto é erro de digitação, não plano de Starlink."""
FUSO_FAZENDA = timedelta(hours=-3)


class OrcamentoInvalidoError(ValueError):
    pass


def definir(session: Session, device: Device, *, bytes_dia: int | None,
            bytes_missao: int | None, actor_id: str | None) -> dict[str, Any] | None:
    """Grava (ou apaga, com os dois nulos) o teto do robô. Vale a partir da próxima missão."""
    if device.kind not in (DeviceKind.ROVER, DeviceKind.DRONE):
        raise OrcamentoInvalidoError("Só Rover e drone têm orçamento de dados próprio.")
    novo: dict[str, Any] = {}
    for nome, valor in (("bytes_dia", bytes_dia), ("bytes_missao", bytes_missao)):
        if valor is None:
            continue
        if isinstance(valor, bool) or not isinstance(valor, int) or not 0 <= valor <= MAX_BYTES_DIA:
            raise OrcamentoInvalidoError(f"{nome}: inteiro entre 0 e {MAX_BYTES_DIA}.")
        novo[nome] = valor
    anterior = device.orcamento_dados
    device.orcamento_dados = novo or None
    audit.record(session, tenant_id=device.tenant_id, action="device.orcamento_dados",
                 subject_type=SubjectType.DEVICE, subject_id=device.id,
                 actor_type=ActorType.USER if actor_id else ActorType.SYSTEM, actor_id=actor_id,
                 payload={"antes": anterior, "depois": device.orcamento_dados})
    return device.orcamento_dados


def _dia_local(quando: datetime) -> date:
    if quando.tzinfo is None:
        quando = quando.replace(tzinfo=UTC)
    return (quando.astimezone(UTC) + FUSO_FAZENDA).date()


def medido_na_plataforma(session: Session, device: Device, *, dias: int = 7,
                         agora: datetime | None = None) -> list[dict[str, Any]]:
    """O que chegou à plataforma por dia da fazenda (mais recente primeiro)."""
    agora = agora or datetime.now(UTC)
    inicio = agora - timedelta(days=dias)
    por_dia: dict[date, dict[str, Any]] = {}

    def dia(d: date) -> dict[str, Any]:
        return por_dia.setdefault(d, {
            "dia": d.isoformat(), "arquivos_bytes": 0, "arquivos": 0,
            "arquivos_deduplicados": 0, "registros_bytes": 0, "registros": 0, "eventos": 0,
            "telemetria_amostras": 0, "por_papel": {}})

    for up in session.scalars(select(EdgeUpload).where(
            EdgeUpload.device_id == device.id, EdgeUpload.status == "complete",
            EdgeUpload.completed_at >= inicio)):
        linha = dia(_dia_local(up.completed_at))
        if up.deduplicated:
            # já estava guardado: na abertura não pede um byte; na conclusão, subiu igual
            linha["arquivos_deduplicados"] += 1
            continue
        linha["arquivos"] += 1
        linha["arquivos_bytes"] += int(up.size_bytes)
        papel = (up.role or "outro").rstrip("+-0123456789")
        linha["por_papel"][papel] = linha["por_papel"].get(papel, 0) + int(up.size_bytes)

    tamanho = func.length(cast(EdgeRecord.payload, String))
    for recebido, kind, n_bytes in session.execute(
            select(EdgeRecord.received_at, EdgeRecord.kind, tamanho).where(
                EdgeRecord.device_id == device.id, EdgeRecord.received_at >= inicio)):
        linha = dia(_dia_local(recebido))
        linha["registros"] += 1
        linha["registros_bytes"] += int(n_bytes or 0)
        if kind == "event":
            linha["eventos"] += 1

    for (recebido,) in session.execute(select(TelemetrySample.received_at).where(
            TelemetrySample.device_id == device.id, TelemetrySample.received_at >= inicio)):
        dia(_dia_local(recebido))["telemetria_amostras"] += 1

    for linha in por_dia.values():
        linha["total_bytes"] = linha["arquivos_bytes"] + linha["registros_bytes"]
    return sorted(por_dia.values(), key=lambda d: d["dia"], reverse=True)


def eventos_de_dados(session: Session, device: Device, *, dias: int = 7,
                     agora: datetime | None = None) -> list[dict[str, Any]]:
    """Os avisos do Rover: tempestade de eventos e teto do dia cruzado (80% e 100%)."""
    agora = agora or datetime.now(UTC)
    linhas = session.scalars(select(EdgeRecord).where(
        EdgeRecord.device_id == device.id, EdgeRecord.kind == "event",
        EdgeRecord.type.in_(("EVENT_STORM", "DATA_BUDGET")),
        EdgeRecord.occurred_at >= agora - timedelta(days=dias),
    ).order_by(EdgeRecord.occurred_at.desc()).limit(200))
    return [{"tipo": r.type, "em": r.occurred_at.isoformat(), "severidade": r.severity,
             "missao": r.mission_id, "dados": (r.payload or {}).get("payload") or {}}
            for r in linhas]


def relatorio(session: Session, device: Device, *, dias: int = 7,
              agora: datetime | None = None) -> dict[str, Any]:
    """O consumo do robô: teto, o que ele contou, o que a plataforma recebeu, os avisos."""
    contado = (device.health or {}).get("dados")
    medido = medido_na_plataforma(session, device, dias=dias, agora=agora)
    teto = device.orcamento_dados or {}
    teto_dia = teto.get("bytes_dia") or (contado or {}).get("teto_dia_bytes")
    hoje = medido[0] if medido else None
    return {
        "device_id": device.id, "nome": device.name,
        "teto": {"bytes_dia": teto.get("bytes_dia"), "bytes_missao": teto.get("bytes_missao"),
                 "origem": "plataforma" if teto else "rover.json",
                 "efetivo_dia_bytes": teto_dia},
        "contado_no_rover": contado,
        "contado_em": device.health_reported_at.isoformat()
        if device.health_reported_at else None,
        "medido_na_plataforma": medido,
        "fracao_hoje": round(contado["usado_bytes"] / teto_dia, 4)
        if contado and contado.get("usado_bytes") is not None and teto_dia else None,
        "recebido_hoje_bytes": hoje["total_bytes"] if hoje else 0,
        "avisos": eventos_de_dados(session, device, dias=dias, agora=agora),
        "nota": ("contado_no_rover é o que trafegou pela Starlink (subida e descida, com "
                 "cabeçalho estimado); medido_na_plataforma é o que chegou inteiro aqui."),
    }


def resumo_do_cliente(session: Session, tenant_id: str, *, dias: int = 7,
                      agora: datetime | None = None) -> list[dict[str, Any]]:
    """Uma linha por Rover/drone do cliente: o dia de hoje e a soma do período."""
    saida = []
    for d in session.scalars(select(Device).where(
            Device.tenant_id == tenant_id,
            Device.kind.in_([DeviceKind.ROVER, DeviceKind.DRONE])).order_by(Device.name)):
        rel = relatorio(session, d, dias=dias, agora=agora)
        contado = rel["contado_no_rover"] or {}
        saida.append({
            "device_id": d.id, "nome": d.name, "teto_dia_bytes": rel["teto"]["efetivo_dia_bytes"],
            "origem_do_teto": rel["teto"]["origem"],
            "usado_hoje_bytes": contado.get("usado_bytes"),
            "fracao_hoje": rel["fracao_hoje"], "tempestade": bool(contado.get("tempestade")),
            "adiados": contado.get("adiados"), "retidos": contado.get("retidos"),
            "recebido_periodo_bytes": sum(m["total_bytes"] for m in rel["medido_na_plataforma"]),
            "avisos": len(rel["avisos"]),
        })
    return saida
