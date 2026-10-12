"""Achar a fazenda do cliente pelo endereço: o primeiro passo do cadastro do talhão.

Coordenada colada (decimal, graus-minutos-segundos, link do Google Maps) o console lê
sozinho, sem rede. Texto — "Fazenda Santa Rita, Três Pontas MG", "Carmo de Minas" — vem
para cá e passa pelo geocodificador:

1. **Google** (Geocoding API), quando há ``GOOGLE_MAPS_API_KEY`` **e** o satélite do
   Google está ligado no console (``GOOGLE_MAPS_TILES_KEY``). Os termos do Google só
   permitem mostrar o resultado da Geocoding API sobre um mapa do Google — por isso um
   sem o outro não liga o Google aqui.
2. **OpenStreetMap** (Nominatim) no resto: livre, com atribuição, no máximo uma
   consulta por segundo e identificação de quem pergunta (a política de uso deles). O
   resultado fica em memória por 10 minutos — a mesma busca repetida não sai de novo.

Google que recusa (faturamento desligado, cota estourada) não derruba a busca: cai no
OpenStreetMap e o aviso diz por quê.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import asdict, dataclass

import httpx

from valtexa.config import settings

logger = logging.getLogger(__name__)

GOOGLE_GEOCODE = "https://maps.googleapis.com/maps/api/geocode/json"
GOOGLE_TILES_SESSAO = "https://tile.googleapis.com/v1/createSession"
CACHE_S = 600.0
MAX_TEXTO = 200


class LocalizarIndisponivelError(RuntimeError):
    """Nenhum geocodificador respondeu (ou nenhum está ligado)."""


@dataclass(frozen=True, slots=True)
class Lugar:
    nome: str
    lat: float
    lon: float
    tipo: str | None
    fonte: str
    """``google`` ou ``osm`` — o console precisa saber (mapa do Google para o Google)."""
    caixa: tuple[float, float, float, float] | None = None
    """Sul, oeste, norte, leste: o console enquadra a cidade inteira, não um ponto."""

    def as_dict(self) -> dict:
        return asdict(self)


_trava = threading.Lock()
_ultima_osm = 0.0
_cache: dict[str, tuple[float, list[Lugar], list[str]]] = {}


def google_ligado() -> bool:
    return bool(settings.google_maps_api_key and settings.google_maps_tiles_key)


def procura(texto: str, limite: int = 5) -> tuple[list[Lugar], list[str]]:
    """Os lugares que batem com o texto (os melhores primeiro) e os avisos."""
    texto = " ".join(texto.split())[:MAX_TEXTO]
    if len(texto) < 3:
        return [], ["Digite ao menos 3 letras."]
    chave = f"{limite}|{texto.casefold()}"
    agora = time.monotonic()
    guardado = _cache.get(chave)
    if guardado and agora - guardado[0] < CACHE_S:
        return guardado[1], guardado[2]

    avisos: list[str] = []
    lugares: list[Lugar] | None = None
    if google_ligado():
        try:
            lugares = _google(texto, limite)
        except LocalizarIndisponivelError as exc:
            avisos.append(f"Google não respondeu ({exc}); usei o OpenStreetMap.")
    if lugares is None:
        if not settings.geocoder_osm_url:
            raise LocalizarIndisponivelError(
                "Nenhum geocodificador ligado: configure GOOGLE_MAPS_API_KEY e "
                "GOOGLE_MAPS_TILES_KEY, ou GEOCODER_OSM_URL. Coordenadas funcionam sem isso.")
        lugares = _osm(texto, limite)
    if len(_cache) > 500:
        _cache.clear()
    _cache[chave] = (agora, lugares, avisos)
    return lugares, avisos


def _google(texto: str, limite: int) -> list[Lugar]:
    try:
        r = httpx.get(GOOGLE_GEOCODE, params={
            "address": texto, "region": "br", "language": "pt-BR",
            "key": settings.google_maps_api_key,
        }, timeout=settings.geocoder_timeout_seconds)
        corpo = r.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise LocalizarIndisponivelError(type(exc).__name__) from exc
    estado = corpo.get("status")
    if estado == "ZERO_RESULTS":
        return []
    if estado != "OK":
        logger.warning("Geocoding do Google recusou: %s %s", estado, corpo.get("error_message"))
        raise LocalizarIndisponivelError(str(estado))
    saida = []
    for item in corpo.get("results", [])[:limite]:
        loc = (item.get("geometry") or {}).get("location") or {}
        vp = (item.get("geometry") or {}).get("viewport") or {}
        caixa = None
        if vp.get("southwest") and vp.get("northeast"):
            caixa = (vp["southwest"]["lat"], vp["southwest"]["lng"],
                     vp["northeast"]["lat"], vp["northeast"]["lng"])
        saida.append(Lugar(nome=item.get("formatted_address") or texto,
                           lat=float(loc["lat"]), lon=float(loc["lng"]),
                           tipo=(item.get("types") or [None])[0], fonte="google", caixa=caixa))
    return saida


def _osm(texto: str, limite: int) -> list[Lugar]:
    global _ultima_osm
    with _trava:  # política do Nominatim: no máximo 1 consulta por segundo
        espera = 1.0 - (time.monotonic() - _ultima_osm)
        if espera > 0:
            time.sleep(espera)
        _ultima_osm = time.monotonic()
        try:
            r = httpx.get(f"{settings.geocoder_osm_url.rstrip('/')}/search", params={
                "q": texto, "format": "jsonv2", "limit": limite, "countrycodes": "br",
                "accept-language": "pt-BR",
            }, headers={"User-Agent": settings.geocoder_user_agent},
                timeout=settings.geocoder_timeout_seconds)
            r.raise_for_status()
            itens = r.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise LocalizarIndisponivelError(f"OpenStreetMap: {type(exc).__name__}") from exc
    saida = []
    for item in itens[:limite]:
        bb = item.get("boundingbox")
        caixa = None
        if bb and len(bb) == 4:  # [sul, norte, oeste, leste]
            caixa = (float(bb[0]), float(bb[2]), float(bb[1]), float(bb[3]))
        saida.append(Lugar(nome=item.get("display_name") or texto, lat=float(item["lat"]),
                           lon=float(item["lon"]), tipo=item.get("type") or item.get("category"),
                           fonte="osm", caixa=caixa))
    return saida


_sessao: dict | None = None


def satelite() -> dict:
    """O satélite que o console usa: o do Google (Map Tiles API) quando ligado, se não o
    da Esri. A sessão do Google vale ~2 semanas; fica guardada até um dia antes de vencer.

    A chave dos tiles vai para o navegador (é como a Map Tiles API funciona): por isso é
    uma chave **separada**, restrita por referenciador e só à Map Tiles API.
    """
    global _sessao
    if not settings.google_maps_tiles_key:
        return {"provedor": "esri"}
    agora = time.time()
    if _sessao and _sessao["vence"] - 86_400 > agora:
        return _sessao["dados"]
    try:
        r = httpx.post(GOOGLE_TILES_SESSAO, params={"key": settings.google_maps_tiles_key},
                       json={"mapType": "satellite", "language": "pt-BR", "region": "BR"},
                       timeout=settings.geocoder_timeout_seconds)
        corpo = r.json()
        if r.status_code != 200 or "session" not in corpo:
            raise ValueError((corpo.get("error") or {}).get("message") or r.status_code)
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("Map Tiles do Google indisponível: %s", exc)
        return {"provedor": "esri", "aviso": f"Satélite do Google indisponível ({exc})."}
    dados = {"provedor": "google", "sessao": corpo["session"],
             "chave": settings.google_maps_tiles_key,
             "url": "https://tile.googleapis.com/v1/2dtiles/{z}/{x}/{y}",
             "tile_px": corpo.get("tileWidth", 256)}
    _sessao = {"dados": dados, "vence": float(corpo.get("expiry") or agora + 86_400 * 13)}
    return dados


def limpa_cache() -> None:
    """Para os testes."""
    global _sessao, _ultima_osm
    _cache.clear()
    _sessao = None
    _ultima_osm = 0.0
