"""``/health`` público sem detalhe interno; ``/v1/platform/health`` completo, só equipe.

Antes o ``/health`` (sem autenticação) devolvia o endereço interno da IA e as
pendências de configuração por extenso, e o console do cliente mostrava isso numa
aba "Plataforma" (brief, seções 30 e 43).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from valtexa.config import settings
from valtexa.models import PlatformRole
from valtexa.services import saude

URL_INTERNA = "http://ia-interna.valtexa.local:8001"


@pytest.fixture
def ia_ligada(monkeypatch: pytest.MonkeyPatch) -> None:
    copia = settings.model_copy(
        update={
            "inference_enabled": True,
            "inference_url": URL_INTERNA,
            "inference_service_token": "",
        }
    )
    monkeypatch.setattr(saude, "settings", copia)


class TestHealthPublico:
    def test_responde_sem_login_e_mantem_os_campos(self, client: TestClient) -> None:
        corpo = client.get("/health").json()
        assert corpo["status"] == "ok"
        assert corpo["database"] == "ok"
        assert set(corpo) >= {
            "status",
            "environment",
            "protocol_version",
            "database",
            "inference",
            "pending_events",
            "warnings",
        }

    def test_nao_conta_o_endereco_da_ia_nem_o_que_falta_configurar(
        self, client: TestClient, ia_ligada: None
    ) -> None:
        corpo = client.get("/health").json()
        assert corpo["inference"] == "ligado"
        texto = str(corpo)
        assert URL_INTERNA not in texto
        assert "SESSION_SECRET" not in texto
        assert "INFERENCE_SERVICE_TOKEN" not in texto
        # O alerta "warnings não vazio" continua valendo para o monitoramento.
        assert corpo["warnings"]
        assert all("/v1/platform/health" in aviso for aviso in corpo["warnings"])


class TestHealthDaEquipe:
    def test_qualquer_papel_da_equipe_ve_o_detalhe(
        self, client: TestClient, equipe, ia_ligada: None
    ) -> None:
        for papel in PlatformRole:
            corpo = client.get("/v1/platform/health", headers=equipe(papel)).json()
            assert corpo["inference"] == URL_INTERNA
            assert any("INFERENCE_SERVICE_TOKEN" in aviso for aviso in corpo["warnings"])
        publico = client.get("/health").json()
        assert len(publico["warnings"]) == len(corpo["warnings"])

    def test_cliente_e_anonimo_nao_veem(
        self, client: TestClient, admin_token: dict, operator_token: dict
    ) -> None:
        assert client.get("/v1/platform/health", headers=admin_token).status_code == 403
        assert client.get("/v1/platform/health", headers=operator_token).status_code == 403
        assert client.get("/v1/platform/health").status_code == 401
