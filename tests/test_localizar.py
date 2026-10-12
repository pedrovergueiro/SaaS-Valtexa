"""Achar a fazenda pelo endereço: Google quando ligado (com o mapa do Google), se não
OpenStreetMap; Google que recusa cai no OpenStreetMap; sem rede nenhuma, nada é inventado."""

from __future__ import annotations

import httpx
import pytest

from valtexa.config import settings
from valtexa.services import localizar


class Resposta:
    def __init__(self, corpo, status: int = 200) -> None:
        self._corpo, self.status_code = corpo, status

    def json(self):
        return self._corpo

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("erro", request=None, response=None)  # type: ignore[arg-type]


OSM = [{"display_name": "Três Pontas, Minas Gerais, Brasil", "lat": "-21.3667",
        "lon": "-45.5122", "type": "town",
        "boundingbox": ["-21.40", "-21.33", "-45.55", "-45.47"]}]
GOOGLE = {"status": "OK", "results": [{
    "formatted_address": "Três Pontas - MG, Brasil", "types": ["locality"],
    "geometry": {"location": {"lat": -21.367, "lng": -45.512},
                 "viewport": {"southwest": {"lat": -21.40, "lng": -45.55},
                              "northeast": {"lat": -21.33, "lng": -45.47}}}}]}


def _config(monkeypatch, **mudancas) -> None:
    atual = localizar.settings
    monkeypatch.setattr(localizar, "settings", atual.model_copy(update=mudancas))


@pytest.fixture(autouse=True)
def _limpo(monkeypatch):
    localizar.limpa_cache()
    monkeypatch.setattr(localizar.time, "sleep", lambda _s: None)
    monkeypatch.setattr(localizar, "settings", settings.model_copy(update={
        "google_maps_api_key": None, "google_maps_tiles_key": None,
        "geocoder_osm_url": "https://osm.teste"}))
    yield
    localizar.limpa_cache()


def test_sem_google_usa_o_openstreetmap_identificado(monkeypatch) -> None:
    pedidos = []

    def get(url, params=None, headers=None, timeout=None):
        pedidos.append((url, params, headers))
        return Resposta(OSM)

    monkeypatch.setattr(localizar.httpx, "get", get)
    lugares, avisos = localizar.procura("Três Pontas MG")
    assert avisos == [] and lugares[0].fonte == "osm"
    assert lugares[0].lat == pytest.approx(-21.3667)
    assert lugares[0].caixa == (-21.40, -45.55, -21.33, -45.47)  # sul, oeste, norte, leste
    url, params, cab = pedidos[0]
    assert url == "https://osm.teste/search" and params["countrycodes"] == "br"
    assert cab["User-Agent"].startswith("ValTexa")  # política de uso do Nominatim
    localizar.procura("três pontas  mg")  # a mesma busca: vem do cache
    assert len(pedidos) == 1


def test_google_so_com_o_mapa_do_google(monkeypatch) -> None:
    usados = []

    def get(url, params=None, headers=None, timeout=None):
        usados.append(url)
        return Resposta(GOOGLE if "googleapis" in url else OSM)

    monkeypatch.setattr(localizar.httpx, "get", get)
    _config(monkeypatch, google_maps_api_key="servidor")
    localizar.procura("Três Pontas")  # sem a chave dos tiles: não usa o Google
    assert usados == ["https://osm.teste/search"]
    _config(monkeypatch, google_maps_tiles_key="navegador")
    lugares, _ = localizar.procura("Três Pontas MG")
    assert lugares[0].fonte == "google" and lugares[0].lon == pytest.approx(-45.512)
    assert usados[-1] == localizar.GOOGLE_GEOCODE


def test_google_recusando_cai_no_openstreetmap_e_avisa(monkeypatch) -> None:
    def get(url, params=None, headers=None, timeout=None):
        if "googleapis" in url:
            return Resposta({"status": "REQUEST_DENIED",
                             "error_message": "You must enable Billing"})
        return Resposta(OSM)

    monkeypatch.setattr(localizar.httpx, "get", get)
    _config(monkeypatch, google_maps_api_key="s")
    _config(monkeypatch, google_maps_tiles_key="n")
    lugares, avisos = localizar.procura("Três Pontas")
    assert lugares[0].fonte == "osm" and "REQUEST_DENIED" in avisos[0]


def test_sem_rede_nenhuma_e_erro_nao_lista_vazia(monkeypatch) -> None:
    def get(*_a, **_k):
        raise httpx.ConnectError("sem rede")

    monkeypatch.setattr(localizar.httpx, "get", get)
    with pytest.raises(localizar.LocalizarIndisponivelError):
        localizar.procura("Três Pontas")
    _config(monkeypatch, geocoder_osm_url="")
    with pytest.raises(localizar.LocalizarIndisponivelError, match="Coordenadas"):
        localizar.procura("Três Pontas")


def test_satelite_do_google_ou_esri(monkeypatch) -> None:
    assert localizar.satelite() == {"provedor": "esri"}
    _config(monkeypatch, google_maps_tiles_key="navegador")
    chamadas = []

    def post(url, params=None, json=None, timeout=None):
        chamadas.append(json)
        return Resposta({"session": "abc", "expiry": "9999999999", "tileWidth": 256})

    monkeypatch.setattr(localizar.httpx, "post", post)
    s = localizar.satelite()
    assert s["provedor"] == "google" and s["sessao"] == "abc" and s["chave"] == "navegador"
    localizar.satelite()
    assert len(chamadas) == 1 and chamadas[0]["mapType"] == "satellite"  # sessão guardada

    localizar.limpa_cache()
    monkeypatch.setattr(localizar.httpx, "post", lambda *a, **k: Resposta(
        {"error": {"message": "Map Tiles API has not been used"}}, 403))
    s = localizar.satelite()
    assert s["provedor"] == "esri" and "Map Tiles" in s["aviso"]


def test_rota_exige_login_e_limita(client, admin_token, monkeypatch) -> None:
    monkeypatch.setattr(localizar.httpx, "get", lambda *a, **k: Resposta(OSM))
    assert client.get("/v1/mapa/localizar", params={"q": "Três Pontas"}).status_code == 401
    r = client.get("/v1/mapa/localizar", params={"q": "Três Pontas"}, headers=admin_token)
    assert r.status_code == 200 and r.json()["lugares"][0]["fonte"] == "osm"
    assert client.get("/v1/mapa/localizar", params={"q": "ab"},
                      headers=admin_token).status_code == 422
    assert client.get("/v1/mapa/satelite", headers=admin_token).json() == {"provedor": "esri"}
    from valtexa.api.routers import localizar as rota

    monkeypatch.setattr(rota, "POR_MINUTO", 2)
    rota._buscas.clear()
    codigos = [client.get("/v1/mapa/localizar", params={"q": f"lugar {i}"},
                          headers=admin_token).status_code for i in range(3)]
    assert codigos == [200, 200, 429]


def test_equipe_em_sessao_de_suporte_tambem_busca(client, platform_token, demo,
                                                 monkeypatch) -> None:
    """Dentro do cliente (desenhando o talhão dele) a equipe usa a mesma busca."""
    monkeypatch.setattr(localizar.httpx, "get", lambda *a, **k: Resposta(OSM))
    suporte = client.post("/v1/platform/support-sessions", json={
        "tenant_id": demo["tenant_id"], "reason": "Achar a fazenda do cliente"},
        headers=platform_token)
    token = {"Authorization": f"Bearer {suporte.json()['access_token']}"}
    r = client.get("/v1/mapa/localizar", params={"q": "Três Pontas"}, headers=token)
    assert r.status_code == 200, r.text
    assert client.get("/v1/mapa/satelite", headers=token).status_code == 200
