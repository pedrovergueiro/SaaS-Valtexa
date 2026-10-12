"""Token de serviço que o SaaS manda à IA (pendência da Fase 2).

O lado da IA está em ``ia/tests/test_service_auth.py``. Aqui: o SaaS manda o token
em toda chamada quando configurado, e produção não sobe sem ele.
"""

from __future__ import annotations

import httpx
import pytest

from valtexa.config import Settings
from valtexa.services import ai_pipeline, plant_map


def test_sem_token_nao_manda_cabecalho() -> None:
    assert Settings(inference_service_token=None).inference_headers() == {}


def test_producao_exige_o_token() -> None:
    sem = Settings(inference_enabled=True, inference_service_token=None)
    com = Settings(inference_enabled=True, inference_service_token="k" * 8 + "Z9q" * 13)
    assert any("INFERENCE_SERVICE_TOKEN" in p for p in sem.production_problems())
    assert not any("INFERENCE_SERVICE_TOKEN" in p for p in com.production_problems())


def test_analisador_manda_o_token(monkeypatch: pytest.MonkeyPatch) -> None:
    vistos: list[dict] = []

    def ia(url: str, headers: dict | None = None, **_: object) -> httpx.Response:
        vistos.append(dict(headers or {}))
        corpo = {"predicted_class": "Healthy", "confidence": 0.9}
        return httpx.Response(200, json=corpo, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", ia)
    monkeypatch.setattr(
        ai_pipeline, "settings", Settings(inference_service_token="segredo-do-saas")
    )
    analisador = ai_pipeline.HttpModelAnalyzer(base_url="http://ia", model_key="m")
    analisador.analyze(b"x", "a.jpg", "coffee")
    assert vistos[0]["Authorization"] == "Bearer segredo-do-saas"
    assert vistos[0]["X-Training-Consent"] == "0"


def test_mapa_de_plantas_manda_o_token(monkeypatch: pytest.MonkeyPatch) -> None:
    vistos: list[dict] = []

    def ia(method: str, url: str, headers: dict | None = None, **_: object) -> httpx.Response:
        vistos.append(dict(headers or {}))
        return httpx.Response(200, json=[], request=httpx.Request(method, url))

    monkeypatch.setattr(httpx, "request", ia)
    monkeypatch.setattr(
        plant_map,
        "settings",
        Settings(
            inference_service_token="segredo-do-saas",
            simulated_inference=False,
            inference_enabled=True,
        ),
    )
    plant_map._request("GET", "/fields/x/plants")
    assert vistos[0]["Authorization"] == "Bearer segredo-do-saas"
