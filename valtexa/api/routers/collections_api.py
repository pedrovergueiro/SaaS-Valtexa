"""Coletas, do lado do cliente.

O produtor não precisa saber que alguém da ValTexa subiu os arquivos na mão, nem
que uma fila processou o lote, nem qual modelo respondeu. Para ele a coleta é
uma data, um talhão e um resultado.

Por isso estas rotas mostram **apenas** coletas publicadas
(``AVAILABLE_TO_CLIENT``). Uma coleta em upload, em fila ou com metade dos
arquivos com erro não é informação do cliente: é operação da ValTexa, e vive no
painel administrativo.

O que o cliente **vê** sem rodeio é o que a plataforma não conseguiu responder.
``no_model_reason`` vai inteiro para a tela: se aquelas imagens aéreas não
passaram por modelo nenhum, o produtor lê isso com todas as letras, em vez de
receber uma classificação inventada.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from valtexa.api.deps import Principal, require, scoped
from valtexa.db import get_session
from valtexa.models import (
    Collection,
    CollectionFile,
    CollectionState,
    Diagnosis,
    Farm,
    Field,
)
from valtexa.schemas import CollectionFileOut, CollectionOut
from valtexa.security import rbac
from valtexa.services import collections

router = APIRouter(tags=["coletas"])


@router.get("/collections", response_model=list[CollectionOut], summary="Coletas do talhão")
def list_collections(
    field_id: str | None = None,
    limit: int = Query(default=50, le=200),
    principal: Principal = Depends(require(rbac.COLLECTION_READ)),
    session: Session = Depends(get_session),
) -> list[CollectionOut]:
    """As coletas publicadas do cliente, da mais recente para a mais antiga."""
    consulta = scoped(select(Collection), Collection, principal).where(
        Collection.state == CollectionState.AVAILABLE_TO_CLIENT
    )
    if field_id:
        consulta = consulta.where(Collection.field_id == field_id)
    linhas = session.scalars(consulta.order_by(Collection.collected_on.desc()).limit(limit))
    return [_out(session, linha) for linha in linhas]


@router.get("/collections/{collection_id}", response_model=CollectionOut, summary="Uma coleta")
def get_collection(
    collection_id: str,
    principal: Principal = Depends(require(rbac.COLLECTION_READ)),
    session: Session = Depends(get_session),
) -> CollectionOut:
    return _out(session, _publicada(session, collection_id, principal))


@router.get(
    "/collections/{collection_id}/files",
    response_model=list[CollectionFileOut],
    summary="Imagens da coleta",
)
def list_files(
    collection_id: str,
    limit: int = Query(default=200, le=1000),
    principal: Principal = Depends(require(rbac.COLLECTION_READ)),
    session: Session = Depends(get_session),
) -> list[CollectionFileOut]:
    """As imagens e o que se concluiu de cada uma.

    Os bytes vêm por ``GET /v1/assets/{id}``, como qualquer outra imagem da
    plataforma — a autorização é a mesma e o cliente não ganha caminho novo.
    """
    coleta = _publicada(session, collection_id, principal)
    linhas = session.scalars(
        select(CollectionFile)
        .where(CollectionFile.collection_id == coleta.id)
        .order_by(CollectionFile.created_at)
        .limit(limit)
    )
    return [_file_out(session, linha) for linha in linhas]


def _publicada(session: Session, collection_id: str, principal: Principal) -> Collection:
    """A coleta, se for do cliente **e** já tiver sido publicada.

    Uma coleta ainda em processamento responde 404, e não 403: confirmar que ela
    existe já contaria ao cliente que há trabalho em curso sobre o talhão dele
    antes de a ValTexa ter o que dizer.
    """
    coleta = session.get(Collection, collection_id)
    if (
        coleta is None
        or coleta.tenant_id != principal.tenant_id
        or not coleta.is_visible_to_client
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Coleta não encontrada.")
    return coleta


def _out(session: Session, coleta: Collection) -> CollectionOut:
    farm = session.get(Farm, coleta.farm_id)
    field = session.get(Field, coleta.field_id)
    return CollectionOut(
        id=coleta.id,
        code=coleta.code,
        tenant_id=coleta.tenant_id,
        farm_id=coleta.farm_id,
        farm_name=farm.name if farm else None,
        field_id=coleta.field_id,
        field_name=field.name if field else None,
        crop=field.crop if field else None,
        collected_on=coleta.collected_on,
        source=coleta.source,
        kind=coleta.kind,
        platform=coleta.platform,
        state=coleta.state,
        operator_name=coleta.operator_name,
        notes=coleta.notes,
        model_key=coleta.model_key,
        no_model_reason=coleta.no_model_reason,
        progress=collections.progress(coleta),
        created_at=coleta.created_at,
        upload_completed_at=coleta.upload_completed_at,
        processing_finished_at=coleta.processing_finished_at,
        released_at=coleta.released_at,
    )


def _file_out(session: Session, arquivo: CollectionFile) -> CollectionFileOut:
    diagnostico = None
    if arquivo.observation_id:
        diagnostico = session.scalars(
            select(Diagnosis)
            .where(Diagnosis.observation_id == arquivo.observation_id)
            .order_by(Diagnosis.created_at.desc())
            .limit(1)
        ).first()
    return CollectionFileOut(
        id=arquivo.id,
        filename=arquivo.filename,
        content_type=arquivo.content_type,
        size_bytes=arquivo.size_bytes,
        received_bytes=arquivo.received_bytes,
        state=arquivo.state,
        sha256=arquivo.sha256,
        error=arquivo.error,
        captured_at=arquivo.captured_at,
        lat=arquivo.lat,
        lon=arquivo.lon,
        asset_id=arquivo.asset_id,
        observation_id=arquivo.observation_id,
        diagnosis_id=diagnostico.id if diagnostico else None,
        label=diagnostico.label if diagnostico else None,
        reviewed_label=diagnostico.reviewed_label if diagnostico else None,
        confidence=diagnostico.confidence if diagnostico else None,
    )
