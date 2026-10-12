"""Arquivos dos registros da Edge AI, para a tela do cliente (Parte 8, seção 47).

A lista dos registros é ``GET /v1/edge/records`` (``edge_sync.py``, que também guarda a
ponte Edge AI → nuvem e não é tocado aqui). Esta rota só **serve** um arquivo que já
subiu — o original, a reduzida ou o contexto — pelo escopo do cliente, como a imagem
da observação: a foto da lavoura não tem URL pública. ``.../url`` (Parte 9) devolve, com
S3, uma URL **assinada e curta** emitida depois do mesmo escopo.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from valtexa.api.arquivos import resposta_de_arquivo
from valtexa.api.deps import Principal, get_scoped, require, scoped
from valtexa.config import settings
from valtexa.db import get_session
from valtexa.models import Asset, EdgeRecord, EdgeUpload
from valtexa.schemas import LinkDeArquivoOut
from valtexa.security import rbac
from valtexa.services import storage

router = APIRouter(tags=["sincronização da Edge AI"])


@router.get(
    "/edge/records/{record_pk}/files/{upload_id}",
    summary="Um arquivo (original, reduzida, contexto) de um registro da Edge AI",
    response_class=Response,
)
def record_file(
    record_pk: str,
    upload_id: str,
    principal: Principal = Depends(require(rbac.DIAGNOSIS_READ)),
    session: Session = Depends(get_session),
) -> Response:
    up, asset = _arquivo(session, principal, record_pk, upload_id)
    try:
        dados = storage.store.read(asset.storage_key)
    except storage.UnknownAssetError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            "Arquivo ausente no armazenamento.") from exc
    return resposta_de_arquivo(dados, asset.content_type or up.content_type,
                               cache="private, max-age=3600", nome=upload_id)


@router.get(
    "/edge/records/{record_pk}/files/{upload_id}/url", response_model=LinkDeArquivoOut,
    summary="Link de download do arquivo: URL assinada e curta do object storage (com S3)",
)
def record_file_url(
    record_pk: str,
    upload_id: str,
    principal: Principal = Depends(require(rbac.DIAGNOSIS_READ)),
    session: Session = Depends(get_session),
) -> LinkDeArquivoOut:
    """Escopo do cliente primeiro; só então a URL assinada (Parte 9, seção 38).

    A assinatura cobre a chave do objeto: trocar o caminho na URL para o objeto de
    outro cliente invalida a assinatura. Sem S3, devolve a rota da API.
    """
    _, asset = _arquivo(session, principal, record_pk, upload_id)
    return link_de_download(
        asset, f"/v1/edge/records/{record_pk}/files/{upload_id}", f"{upload_id}"
    )


def _arquivo(session: Session, principal: Principal, record_pk: str,
             upload_id: str) -> tuple[EdgeUpload, Asset]:
    linha = get_scoped(session, EdgeRecord, record_pk, principal)
    up = session.scalars(scoped(select(EdgeUpload), EdgeUpload, principal).where(
        EdgeUpload.device_id == linha.device_id, EdgeUpload.record_id == linha.record_id,
        EdgeUpload.upload_id == upload_id)).first()
    if up is None or up.status != "complete" or not up.asset_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Arquivo não sincronizado.")
    return up, get_scoped(session, Asset, up.asset_id, principal)


def link_de_download(asset: Asset, rota_da_api: str, nome: str) -> LinkDeArquivoOut:
    """URL assinada quando o armazenamento tem uma; senão, a rota autenticada da API."""
    segundos = settings.s3_presign_seconds
    url = storage.store.url_assinada(asset.storage_key, segundos, filename=nome)
    if url is None:
        return LinkDeArquivoOut(url=rota_da_api, direct=False, expires_in=None)
    return LinkDeArquivoOut(url=url, direct=True, expires_in=segundos)
