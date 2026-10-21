"""Recepção do que o Rover Runtime sincroniza: registros e arquivos em chunks.

Brief, seções 18, 38 e 52. O contrato completo, com os dois lados, está em
``VALTEXA-ROVER/docs/SYNC.md``. O que este módulo garante:

* **idempotência por ID e hash** — um registro é ``(robô, record_id)`` com o
  SHA-256 do JSON canônico do corpo (chaves ordenadas, separadores ``,`` e
  ``:``, UTF-8 sem escape). Mesmo ID e mesmo hash: ``duplicated``, nada muda.
  Mesmo ID e outro hash: ``conflicts``, nada muda. Hash que não confere com o
  corpo: ``rejected``;
* **retomada de upload** — os chunks recebidos ficam na área de *staging*; quem
  reabre o upload recebe a lista do que já chegou e manda só o resto. O
  arquivo só vira objeto depois que o SHA-256 do todo confere;
* **reenvio de arquivo não duplica** — o mesmo hash no mesmo cliente reaproveita
  o :class:`~valtexa.models.Asset` que já existe (o objeto também é endereçado
  por hash), sem pedir um byte;
* **isolamento** — tudo é por robô autenticado e pelo cliente dele; talhão ou
  missão de outro cliente no corpo é ignorado (fica nulo), nunca vinculado;
* **banco só com metadados** — os bytes vão para o armazenamento de objetos.

Corrida entre duas requisições com o mesmo ID (o robô reenviou antes da
resposta chegar): a restrição única do banco recusa a segunda no *commit*; a
rota desfaz e processa o lote de novo, e aí o ID aparece como ``duplicated``.

O *staging* (:class:`ChunkStaging`) é uma interface. :class:`LocalChunkStaging`
(disco, sob ``STORAGE_DIR/_uploads``) é a implementação de desenvolvimento e de
um servidor único; com ``STORAGE_BACKEND=s3`` os chunks vão para o bucket
(:class:`~valtexa.services.storage.S3ChunkStaging`), e qualquer réplica recebe
qualquer chunk e monta o arquivo — ver ``VALTEXA-ROVER/docs/SYNC.md`` e
``docs/plataforma/DEPLOY.md``.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from valtexa.config import settings
from valtexa.models import (
    Asset,
    AssetKind,
    Device,
    EdgeRecord,
    EdgeUpload,
    Field,
    Mission,
)
from valtexa.services import plans, storage

MAX_CHUNK_BYTES = 8 * 1024 * 1024
MIN_CHUNK_BYTES = 1024
MAX_CHUNKS = 100_000
KINDS = {"result", "event"}
CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp", "application/json",
                 "application/octet-stream"}


class EdgeSyncError(Exception):
    """Pedido recusado. Carrega o status HTTP e a mensagem em português."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def canonical_sha256(body: object) -> str:
    bruto = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(bruto.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Staging dos chunks
# ---------------------------------------------------------------------------


class ChunkStaging(Protocol):
    def put(self, upload_pk: str, index: int, data: bytes) -> None: ...

    def received(self, upload_pk: str) -> set[int]: ...

    def assemble(self, upload_pk: str, total: int) -> bytes: ...

    def clear(self, upload_pk: str) -> None: ...


class LocalChunkStaging:
    """Chunks em disco, um arquivo por chunk, escritos de forma atômica.

    A lista do que chegou sai do disco, não do banco: dois PUTs simultâneos não
    disputam a mesma linha, e um chunk só "chegou" depois do ``rename``.
    """

    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root or Path(settings.storage_dir) / "_uploads")

    def _dir(self, upload_pk: str) -> Path:
        limpo = "".join(c for c in upload_pk if c.isalnum())
        return self.root / limpo[:2] / limpo

    def put(self, upload_pk: str, index: int, data: bytes) -> None:
        pasta = self._dir(upload_pk)
        pasta.mkdir(parents=True, exist_ok=True)
        destino = pasta / f"{index:06d}.chunk"
        temporario = pasta / f"{index:06d}.part"
        with open(temporario, "wb") as fh:
            fh.write(data)
        os.replace(temporario, destino)

    def received(self, upload_pk: str) -> set[int]:
        pasta = self._dir(upload_pk)
        if not pasta.exists():
            return set()
        return {int(p.stem) for p in pasta.glob("*.chunk")}

    def assemble(self, upload_pk: str, total: int) -> bytes:
        pasta = self._dir(upload_pk)
        return b"".join((pasta / f"{i:06d}.chunk").read_bytes() for i in range(total))

    def clear(self, upload_pk: str) -> None:
        shutil.rmtree(self._dir(upload_pk), ignore_errors=True)


def _construir_staging() -> ChunkStaging:
    """Com S3, os chunks vão para o bucket (compartilhado pelas réplicas); senão, disco."""
    if isinstance(storage.store, storage.S3ObjectStore):
        return storage.S3ChunkStaging(storage.store, area="edge")
    return LocalChunkStaging()


staging: ChunkStaging = _construir_staging()
"""Instância do processo. Os testes a apontam para ``tmp_path``."""


# ---------------------------------------------------------------------------
# Registros
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class RecordsResult:
    accepted: list[str] = field(default_factory=list)
    duplicated: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    rejected: list[dict] = field(default_factory=list)


def ingest_records(session: Session, device: Device, records: list[dict]) -> RecordsResult:
    """Grava os registros novos; classifica os demais. Não faz *commit*."""
    saida = RecordsResult()
    agora = datetime.now(UTC)
    vistos: dict[str, str] = {}
    for bruto in records:
        rid = str(bruto.get("id") or "")
        corpo = bruto.get("body")
        erro = _valida_registro(device, rid, bruto, corpo)
        if erro:
            saida.rejected.append({"id": rid, "error": erro})
            continue
        sha = bruto["sha256"]
        existente_sha = vistos.get(rid) or session.scalar(
            select(EdgeRecord.sha256).where(
                EdgeRecord.device_id == device.id, EdgeRecord.record_id == rid
            )
        )
        if existente_sha is not None:
            (saida.duplicated if existente_sha == sha else saida.conflicts).append(rid)
            continue
        session.add(_linha(session, device, rid, bruto, corpo, agora))
        vistos[rid] = sha
        saida.accepted.append(rid)
    return saida


def _valida_registro(device: Device, rid: str, bruto: dict, corpo) -> str | None:
    if not rid or len(rid) > 64:
        return "id ausente ou com mais de 64 caracteres"
    if bruto.get("kind") not in KINDS:
        return f"kind deve ser um de {sorted(KINDS)}"
    if not isinstance(corpo, dict):
        return "body deve ser um objeto"
    sha = str(bruto.get("sha256") or "")
    if len(sha) != 64:
        return "sha256 ausente"
    if canonical_sha256(corpo) != sha:
        return "sha256 não confere com o corpo (JSON canônico)"
    if corpo.get("id") not in (None, rid):
        return "o id do corpo difere do id do registro"
    if corpo.get("device_id") not in (None, device.id):
        return "registro de outro robô"
    if not bruto.get("type") or len(str(bruto["type"])) > 64:
        return "type ausente ou longo demais"
    return None


def _linha(session: Session, device: Device, rid: str, bruto: dict, corpo: dict,
           agora: datetime) -> EdgeRecord:
    resultado = corpo.get("result") or {}
    modelo = corpo.get("model") or {}
    posicao = corpo.get("position") or {}
    payload = corpo.get("payload") or {}
    return EdgeRecord(
        tenant_id=device.tenant_id,
        device_id=device.id,
        record_id=rid,
        kind=bruto["kind"],
        type=str(bruto["type"]),
        sha256=bruto["sha256"],
        mission_id=_missao(session, device, corpo.get("mission_id")),
        field_id=_talhao(session, device, corpo.get("field_id") or payload.get("field_id")),
        occurred_at=_quando(corpo.get("occurred_at"), agora),
        received_at=agora,
        severity=corpo.get("severity"),
        label=_texto(resultado.get("label") or payload.get("label"), 120),
        confidence=_numero(resultado.get("confidence", payload.get("confidence"))),
        model_key=_texto(modelo.get("key") or payload.get("model_key"), 64),
        model_version=_texto(modelo.get("version") or payload.get("model_version"), 64),
        lat=_numero(posicao.get("lat", payload.get("lat"))),
        lon=_numero(posicao.get("lon", payload.get("lon"))),
        payload=corpo,
    )


def _missao(session: Session, device: Device, mission_id) -> str | None:
    if not mission_id:
        return None
    missao = session.get(Mission, str(mission_id))
    return missao.id if missao is not None and missao.device_id == device.id else None


def _talhao(session: Session, device: Device, field_id) -> str | None:
    if not field_id:
        return None
    talhao = session.get(Field, str(field_id))
    return talhao.id if talhao is not None and talhao.tenant_id == device.tenant_id else None


def _quando(valor, padrao: datetime) -> datetime:
    try:
        dt = datetime.fromisoformat(str(valor))
    except (TypeError, ValueError):
        return padrao
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _numero(valor) -> float | None:
    try:
        return None if valor is None else float(valor)
    except (TypeError, ValueError):
        return None


def _texto(valor, limite: int) -> str | None:
    return None if valor is None else str(valor)[:limite]


# ---------------------------------------------------------------------------
# Uploads
# ---------------------------------------------------------------------------


def open_upload(session: Session, device: Device, dados: dict) -> EdgeUpload:
    """Abre o upload, reabre o que já existe ou o fecha na hora se o hash já está guardado."""
    existente = session.scalars(
        select(EdgeUpload).where(
            EdgeUpload.device_id == device.id, EdgeUpload.upload_id == dados["upload_id"]
        )
    ).first()
    if existente is not None:
        if existente.sha256 != dados["sha256"] or existente.size_bytes != dados["size_bytes"]:
            raise EdgeSyncError(
                409, "Este upload_id já existe com outro conteúdo (hash ou tamanho)."
            )
        return existente

    if dados["content_type"] not in CONTENT_TYPES:
        raise EdgeSyncError(415, f"Tipo {dados['content_type']!r} não aceito.")
    if dados["size_bytes"] > settings.max_asset_bytes:
        raise EdgeSyncError(
            413, f"Arquivo de {dados['size_bytes']} bytes excede {settings.max_asset_mb} MB."
        )
    tamanho_chunk = int(dados["chunk_size"])
    total = max(1, math.ceil(dados["size_bytes"] / tamanho_chunk))
    if total > MAX_CHUNKS:
        raise EdgeSyncError(422, f"Mais de {MAX_CHUNKS} chunks: aumente o chunk_size.")

    asset = _asset(session, device.tenant_id, dados["sha256"])
    upload = EdgeUpload(
        tenant_id=device.tenant_id,
        device_id=device.id,
        upload_id=dados["upload_id"],
        sha256=dados["sha256"],
        size_bytes=dados["size_bytes"],
        content_type=dados["content_type"],
        chunk_size=tamanho_chunk,
        total_chunks=total,
        status="receiving",
        record_id=dados.get("record_id"),
        role=dados.get("role"),
        tier=dados.get("tier"),
        priority=dados.get("priority"),
    )
    if asset is not None:
        # Reenvio do mesmo arquivo: já está guardado, não pede um byte.
        upload.status = "complete"
        upload.asset_id = asset.id
        upload.deduplicated = True
        upload.completed_at = datetime.now(UTC)
    else:
        plans.exigir(session, device.tenant_id, "storage_gb", dados["size_bytes"] / 1024**3)
    session.add(upload)
    session.flush()
    return upload


def received_chunks(upload: EdgeUpload) -> list[int]:
    if upload.status == "complete":
        return list(range(upload.total_chunks))
    return sorted(staging.received(upload.id))


def put_chunk(upload: EdgeUpload, index: int, data: bytes, declared_sha256: str | None) -> int:
    if upload.status == "complete":
        return upload.total_chunks
    if not 0 <= index < upload.total_chunks:
        raise EdgeSyncError(422, f"Chunk {index} fora de 0..{upload.total_chunks - 1}.")
    esperado = (
        upload.size_bytes - upload.chunk_size * (upload.total_chunks - 1)
        if index == upload.total_chunks - 1
        else upload.chunk_size
    )
    if len(data) != esperado:
        raise EdgeSyncError(422, f"Chunk {index} com {len(data)} bytes; esperado {esperado}.")
    if declared_sha256 and hashlib.sha256(data).hexdigest() != declared_sha256.lower():
        raise EdgeSyncError(422, f"Chunk {index}: hash não confere com o cabeçalho.")
    staging.put(upload.id, index, data)
    return len(staging.received(upload.id))


def complete_upload(session: Session, device: Device, upload: EdgeUpload) -> EdgeUpload:
    if upload.status == "complete":
        return upload
    faltam = sorted(set(range(upload.total_chunks)) - staging.received(upload.id))
    if faltam:
        raise EdgeSyncError(
            409, f"Faltam {len(faltam)} chunk(s): {faltam[:20]}{'…' if len(faltam) > 20 else ''}."
        )
    dados = staging.assemble(upload.id, upload.total_chunks)
    if len(dados) != upload.size_bytes or hashlib.sha256(dados).hexdigest() != upload.sha256:
        staging.clear(upload.id)
        raise EdgeSyncError(
            422, "O arquivo montado não confere com o hash declarado: chunks descartados, "
            "reenvie o arquivo."
        )
    asset = _asset(session, device.tenant_id, upload.sha256)
    if asset is None:
        guardado = storage.store.put(dados, upload.content_type, namespace=device.tenant_id)
        try:
            # Savepoint: outro robô do mesmo cliente pode estar guardando o mesmo
            # arquivo agora (achado no estresse da Parte 5). Perdeu a corrida →
            # o asset dele vale, e este upload fica deduplicado.
            with session.begin_nested():
                asset = Asset(
                    tenant_id=device.tenant_id,
                    kind=AssetKind.IMAGE if upload.content_type.startswith("image/")
                    else AssetKind.LOG,
                    content_type=guardado.content_type,
                    size_bytes=guardado.size_bytes,
                    sha256=guardado.sha256,
                    storage_key=guardado.key,
                    device_id=device.id,
                    meta={"edge_upload_id": upload.upload_id, "record_id": upload.record_id,
                          "role": upload.role},
                )
                session.add(asset)
                session.flush()
        except IntegrityError:
            asset = _asset(session, device.tenant_id, upload.sha256)
            upload.deduplicated = True
    else:
        upload.deduplicated = True
    upload.asset_id = asset.id
    upload.status = "complete"
    upload.completed_at = datetime.now(UTC)
    staging.clear(upload.id)
    return upload


def _asset(session: Session, tenant_id: str, sha256: str) -> Asset | None:
    return session.scalars(
        select(Asset).where(Asset.tenant_id == tenant_id, Asset.sha256 == sha256)
    ).first()


def find_upload(session: Session, device: Device, upload_id: str) -> EdgeUpload:
    upload = session.scalars(
        select(EdgeUpload).where(
            EdgeUpload.device_id == device.id, EdgeUpload.upload_id == upload_id
        )
    ).first()
    if upload is None:
        raise EdgeSyncError(404, "Upload não encontrado para este robô.")
    return upload


def limpar_abandonados(session: Session, *, agora: datetime | None = None,
                       ttl_horas: float | None = None) -> int:
    """Apaga uploads que pararam de receber chunks há mais de ``ttl_horas`` (F18).

    O *staging* dos chunks ocupa disco (ou bucket) e nunca mais seria lido. A linha
    sai junto: se o robô voltar depois, reabre o upload do zero (o ID é o mesmo, o
    progresso dele zera — o protocolo já trata isso). Upload completo não é tocado.
    """
    agora = agora or datetime.now(UTC)
    limite = agora - timedelta(hours=ttl_horas if ttl_horas is not None
                               else settings.upload_ttl_hours)
    velhos = list(session.scalars(select(EdgeUpload).where(
        EdgeUpload.status == "receiving", EdgeUpload.updated_at < limite)))
    for upload in velhos:
        staging.clear(upload.id)
        session.delete(upload)
    return len(velhos)
