"""Rotas da sincronização do Rover Runtime (brief, seções 18, 38, 39 e 52).

Do robô (assinadas, como todo ``/v1/device/**``):

* ``POST /v1/device/edge/records`` — resultados da Edge AI e eventos, em lote;
* ``POST /v1/device/uploads`` — abre (ou reabre) um upload e diz o que já chegou;
* ``PUT /v1/device/uploads/{upload_id}/chunks/{index}`` — um pedaço, corpo bruto;
* ``GET /v1/device/uploads/{upload_id}`` — estado do upload;
* ``POST /v1/device/uploads/{upload_id}/complete`` — confere o hash e guarda.

Do cliente: ``GET /v1/edge/records`` — o que os robôs dele sincronizaram, com os
arquivos de cada registro.

O contrato e o lado do robô estão em ``docs/SYNC.md``; a regra de cada passo,
em :mod:`valtexa.services.edge_sync`.
"""

from __future__ import annotations

import logging
import math
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from valtexa.api.deps import DeviceCaller, Principal, current_device, require, scoped
from valtexa.api.middleware import RAW_BODY_KEY
from valtexa.config import settings
from valtexa.db import get_session
from valtexa.models import EdgeRecord, EdgeUpload
from valtexa.schemas import (
    ChunkOut,
    EdgeFileOut,
    EdgeRecordBatch,
    EdgeRecordOut,
    EdgeRecordsOut,
    UploadCompleteIn,
    UploadOpenIn,
    UploadStateOut,
)
from valtexa.security import rbac
from valtexa.services import coordenacao, edge_sync, missao_resultado

logger = logging.getLogger(__name__)
router = APIRouter(tags=["sincronização do rover"])


class LimiteDoRobo:
    """Balde de fichas por robô nas rotas de sincronização (F18, seções 36 e 51).

    Um robô com defeito (laço sem backoff) ou uma credencial vazada não pode tomar
    a API dos outros. O balde mora em :mod:`valtexa.services.coordenacao`: no Redis
    (``REDIS_URL``) ele é um só para todas as réplicas; sem Redis, por processo.
    """

    def __call__(self, caller: DeviceCaller = Depends(current_device)) -> DeviceCaller:
        por_minuto = settings.device_rate_per_minute
        espera = coordenacao.coordenacao.consumir(f"robo:{caller.device_id}", por_minuto)
        if espera is not None:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                f"Limite de {por_minuto} requisições/min por robô.",
                headers={"Retry-After": str(max(1, math.ceil(espera)))},
            )
        return caller

    def limpar(self) -> None:
        coordenacao.coordenacao.limpar()


limite_do_robo = LimiteDoRobo()


@router.post(
    "/device/edge/records", response_model=EdgeRecordsOut,
    summary="Resultados da Edge AI e eventos do robô (idempotente por ID e hash)",
)
def post_records(
    payload: EdgeRecordBatch,
    caller: DeviceCaller = Depends(limite_do_robo),
    session: Session = Depends(get_session),
) -> EdgeRecordsOut:
    if len(payload.records) > settings.max_sync_batch:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"Lote de {len(payload.records)} registros excede {settings.max_sync_batch}.",
        )
    brutos = [r.model_dump() for r in payload.records]
    for tentativa in range(2):
        resultado = edge_sync.ingest_records(session, caller.device, brutos)
        _contato(caller, payload.remaining)
        try:
            session.commit()
            break
        except IntegrityError:
            # Outra requisição gravou um destes IDs agora: na segunda passada eles
            # aparecem como duplicados (ou conflito, se o hash for outro).
            session.rollback()
            if tentativa:
                raise
    _encaminhar(session, caller, resultado.accepted)
    return EdgeRecordsOut(
        accepted=resultado.accepted,
        duplicated=resultado.duplicated,
        conflicts=resultado.conflicts,
        rejected=resultado.rejected,
    )


@router.post(
    "/device/uploads", response_model=UploadStateOut,
    summary="Abre ou retoma um upload em chunks (diz quais chunks já chegaram)",
)
def open_upload(
    payload: UploadOpenIn,
    caller: DeviceCaller = Depends(limite_do_robo),
    session: Session = Depends(get_session),
) -> UploadStateOut:
    for tentativa in range(2):
        try:
            upload = _ou_http(lambda: edge_sync.open_upload(session, caller.device,
                                                            payload.model_dump()))
            _contato(caller, None)
            session.commit()
            break
        except IntegrityError:
            session.rollback()
            if tentativa:
                raise
    return _estado(upload)


@router.get(
    "/device/uploads/{upload_id}", response_model=UploadStateOut, summary="Estado de um upload"
)
def get_upload(
    upload_id: str,
    caller: DeviceCaller = Depends(limite_do_robo),
    session: Session = Depends(get_session),
) -> UploadStateOut:
    return _estado(_ou_http(lambda: edge_sync.find_upload(session, caller.device, upload_id)))


@router.put(
    "/device/uploads/{upload_id}/chunks/{index}", response_model=ChunkOut,
    summary="Envia um chunk (corpo bruto; idempotente: reenviar o mesmo índice sobrescreve)",
)
def put_chunk(
    upload_id: str,
    index: int,
    request: Request,
    x_chunk_sha256: str | None = Header(default=None),
    caller: DeviceCaller = Depends(limite_do_robo),
    session: Session = Depends(get_session),
) -> ChunkOut:
    corpo = request.scope.get(RAW_BODY_KEY)
    if corpo is None:  # pragma: no cover - o middleware cobre todo /v1/device
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Corpo do chunk ausente.")
    upload = _ou_http(lambda: edge_sync.find_upload(session, caller.device, upload_id))
    recebidos = _ou_http(lambda: edge_sync.put_chunk(upload, index, corpo, x_chunk_sha256))
    _contato(caller, None)
    session.commit()
    return ChunkOut(received=recebidos, total_chunks=upload.total_chunks)


@router.post(
    "/device/uploads/{upload_id}/complete", response_model=UploadStateOut,
    summary="Fecha o upload: confere o SHA-256 do arquivo inteiro e guarda no object storage",
)
def complete_upload(
    upload_id: str,
    payload: UploadCompleteIn,
    caller: DeviceCaller = Depends(limite_do_robo),
    session: Session = Depends(get_session),
) -> UploadStateOut:
    upload = _ou_http(lambda: edge_sync.find_upload(session, caller.device, upload_id))
    if payload.sha256 != upload.sha256:
        raise HTTPException(status.HTTP_409_CONFLICT, "Hash diferente do declarado na abertura.")
    # Duas réplicas montando o mesmo arquivo (o robô reenviou o complete antes da
    # resposta) leriam e apagariam o staging uma da outra: um só monta.
    with coordenacao.coordenacao.trava(f"upload:{upload.id}", ttl_segundos=300) as minha:
        if not minha:
            raise HTTPException(
                status.HTTP_409_CONFLICT, "Upload sendo montado por outra requisição.",
                headers={"Retry-After": "2"},
            )
        upload = _ou_http(lambda: edge_sync.complete_upload(session, caller.device, upload))
        _contato(caller, None)
        session.commit()
    if upload.record_id:
        _encaminhar(session, caller, [upload.record_id])
    return _estado(upload)


def _encaminhar(session: Session, caller: DeviceCaller, record_ids: list[str]) -> None:
    """Ponte Edge AI → IA de nuvem, numa transação à parte.

    O robô já recebeu a confirmação do que enviou (commit acima): uma falha na
    IA de nuvem não pode fazê-lo reenviar. O que não encaminhar agora é
    reencaminhado quando a outra peça (registro ou arquivo) chegar, ou pela
    varredura do worker (``missao_resultado.varrer``).
    """
    try:
        if missao_resultado.encaminhar_pendentes(session, caller.device, record_ids):
            session.commit()
    except Exception:  # a sincronização já foi confirmada; registra e segue
        session.rollback()
        logger.exception("ponte Edge AI → nuvem falhou para %s", record_ids[:5])


@router.get(
    "/edge/records", response_model=list[EdgeRecordOut],
    summary="O que os robôs do cliente sincronizaram (resultados, eventos e arquivos)",
)
def list_records(
    mission_id: str | None = None,
    field_id: str | None = None,
    kind: str | None = Query(default=None, pattern="^(result|event)$"),
    type: str | None = Query(default=None, max_length=64),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    principal: Principal = Depends(require(rbac.DIAGNOSIS_READ)),
    session: Session = Depends(get_session),
) -> list[EdgeRecordOut]:
    consulta = scoped(select(EdgeRecord), EdgeRecord, principal)
    for coluna, valor in ((EdgeRecord.mission_id, mission_id), (EdgeRecord.field_id, field_id),
                          (EdgeRecord.kind, kind), (EdgeRecord.type, type)):
        if valor is not None:
            consulta = consulta.where(coluna == valor)
    linhas = list(session.scalars(
        consulta.order_by(EdgeRecord.occurred_at, EdgeRecord.id).limit(limit).offset(offset)
    ))
    arquivos: dict[tuple[str, str], list[EdgeUpload]] = {}
    if linhas:
        uploads = session.scalars(
            scoped(select(EdgeUpload), EdgeUpload, principal).where(
                EdgeUpload.record_id.in_([linha.record_id for linha in linhas]),
                EdgeUpload.status == "complete",
            )
        )
        for up in uploads:
            arquivos.setdefault((up.device_id, up.record_id), []).append(up)
    return [
        EdgeRecordOut(
            id=linha.id, record_id=linha.record_id, device_id=linha.device_id, kind=linha.kind,
            type=linha.type, mission_id=linha.mission_id, field_id=linha.field_id,
            occurred_at=linha.occurred_at, received_at=linha.received_at,
            severity=linha.severity, label=linha.label, confidence=linha.confidence,
            model_key=linha.model_key, model_version=linha.model_version, lat=linha.lat,
            lon=linha.lon, payload=linha.payload,
            files=[
                EdgeFileOut(upload_id=up.upload_id, role=up.role, sha256=up.sha256,
                            size_bytes=up.size_bytes, content_type=up.content_type,
                            status=up.status, asset_id=up.asset_id)
                for up in sorted(arquivos.get((linha.device_id, linha.record_id), []),
                                 key=lambda u: u.role or "")
            ],
        )
        for linha in linhas
    ]


def _estado(upload: EdgeUpload) -> UploadStateOut:
    return UploadStateOut(
        upload_id=upload.upload_id, status=upload.status, sha256=upload.sha256,
        size_bytes=upload.size_bytes, chunk_size=upload.chunk_size,
        total_chunks=upload.total_chunks, received_chunks=edge_sync.received_chunks(upload),
        asset_id=upload.asset_id, deduplicated=upload.deduplicated,
    )


def _contato(caller: DeviceCaller, remaining: int | None) -> None:
    """Sincronizar é contato (frota). ``remaining`` conta como no ``/sync``."""
    agora = datetime.now(UTC)
    caller.device.last_seen_at = agora
    if remaining is not None:
        caller.device.sync_pending = remaining
        if remaining == 0:
            caller.device.last_sync_at = agora


def _ou_http(funcao):
    try:
        return funcao()
    except edge_sync.EdgeSyncError as exc:
        raise HTTPException(exc.status_code, exc.detail) from exc
