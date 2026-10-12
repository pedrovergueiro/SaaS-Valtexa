"""Plantas do talhão: a fusão por planta que o serviço de inferência mantém.

O rover vê a mesma planta em seis câmeras e vários quadros seguidos, e volta na
semana seguinte. Cada quadro que chega com a câmera (``ObservationIn.camera``)
vai ao ``/predict/rover-frame`` de VALTEXA-B junto com o talhão, a rua, o lado e
a posição — e lá a fusão por planta junta tudo num diagnóstico por **planta**,
com posterior por doença, incidência, histórico entre passadas e um mapa.

Este módulo só lê esse estado (e fecha a passada quando a missão termina). A
fonte é o serviço de inferência; aqui não há cópia, que envelheceria.
"""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import quote

import httpx

from valtexa.config import settings

logger = logging.getLogger(__name__)

EMPTY_MAP = {"type": "FeatureCollection", "features": []}


class PlantMapUnavailableError(RuntimeError):
    """O serviço de inferência não respondeu, ou não guarda talhões."""


class PlantMapRefusedError(PlantMapUnavailableError):
    """O serviço respondeu e recusou o pedido (409/422): mandar de novo não adianta."""


def _request(
    method: str, path: str, params: dict | None = None, json_body: dict | None = None
) -> Any | None:
    """Chama o serviço de inferência; ``None`` quando o talhão ainda não tem histórico."""
    if settings.simulated_inference or not settings.inference_enabled:
        raise PlantMapUnavailableError(
            "Sem serviço de inferência neste processo (inferência simulada ou desligada)."
        )
    url = f"{settings.inference_url.rstrip('/')}{path}"
    try:
        response = httpx.request(
            method,
            url,
            params=params,
            json=json_body,
            headers=settings.inference_headers(),
            timeout=settings.inference_timeout_seconds,
        )
    except httpx.HTTPError as exc:
        raise PlantMapUnavailableError(f"Serviço de inferência fora do ar: {exc}") from exc
    if response.status_code == 404:
        return None
    if response.status_code == 503:
        raise PlantMapUnavailableError(
            "O serviço de inferência não guarda talhões: configure FIELDS_DIR nele."
        )
    if response.status_code in (409, 422):
        try:
            detalhe = response.json().get("detail", "Recusado pela inferência.")
        except ValueError:
            detalhe = response.text[:200]
        raise PlantMapRefusedError(str(detalhe))
    try:
        response.raise_for_status()
        return response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise PlantMapUnavailableError(f"Resposta inválida da inferência: {exc}") from exc


def _seg(value: str) -> str:
    """Um segmento de caminho, codificado: nada do valor vira ``/`` ou ``..`` na URL.

    ``quote`` deixa o ponto passar (é caractere livre), e o cliente HTTP resolve
    ``..`` antes de mandar — por isso o ponto vai codificado também.
    """
    return quote(value, safe="").replace(".", "%2E")


def plants(field_id: str, pass_id: str | None = None) -> list[dict]:
    """O diagnóstico fundido de cada planta; vazio se o rover ainda não passou."""
    params = {"pass_id": pass_id} if pass_id else None
    return _request("GET", f"/fields/{_seg(field_id)}/plants", params) or []


def geojson(field_id: str, pass_id: str | None = None) -> dict:
    """O mapa do talhão, um ponto por planta."""
    params = {"pass_id": pass_id} if pass_id else None
    return _request("GET", f"/fields/{_seg(field_id)}/map", params) or dict(EMPTY_MAP)


def evolution(field_id: str, plant_id: str) -> dict | None:
    return _request("GET", f"/fields/{_seg(field_id)}/plants/{_seg(plant_id)}/evolution")


def prevalence(field_id: str, model_key: str) -> dict | None:
    return _request("GET", f"/fields/{_seg(field_id)}/prevalence", {"model": model_key})


def incidence(field_id: str, pass_id: str | None = None) -> dict | None:
    """Fração de plantas doentes, corrigida pela calibração da fusão, com intervalo."""
    params = {"pass_id": pass_id} if pass_id else None
    return _request("GET", f"/fields/{_seg(field_id)}/incidence", params)


def prescription(field_id: str, pedido: dict, formato: str = "json") -> dict | None:
    """Prescrição planta a planta (``app.prescricao`` de VALTEXA-B): onde tratar se paga."""
    return _request(
        "POST", f"/fields/{_seg(field_id)}/prescription", {"formato": formato}, json_body=pedido
    )


def ingest_edge_frame(field_id: str, model_key: str, frame: dict) -> dict:
    """Um quadro classificado no Rover entra na fusão por planta (``services.fusao_borda``)."""
    resposta = _request(
        "POST", f"/fields/{_seg(field_id)}/frames", {"model": model_key}, json_body=frame
    )
    if resposta is None:
        raise PlantMapRefusedError("A inferência não conhece a rota /fields/{id}/frames.")
    return resposta


def close_pass(field_id: str, pass_id: str) -> dict | None:
    """Consolida a passada: o que mudou em cada planta desde a anterior.

    Chamado no fim da missão, em melhor esforço — a missão está concluída de
    qualquer jeito; o que falta, se falhar, é só o comparativo entre passadas.
    """
    try:
        return _request("POST", f"/fields/{_seg(field_id)}/passes/{_seg(pass_id)}/close")
    except PlantMapUnavailableError as exc:
        logger.info("Passada %s do talhão %s não consolidada: %s", pass_id, field_id, exc)
        return None
