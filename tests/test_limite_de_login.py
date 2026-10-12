"""Limitação de tentativas de login (pendência da Fase 2, risco aberto da auditoria)."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from tests.conftest import DEMO_PASSWORD
from valtexa.config import settings
from valtexa.models import LoginAttempt


def _tenta(client: TestClient, email: str, senha: str):
    return client.post("/v1/auth/login", json={"email": email, "password": senha})


class TestLimiteDeLogin:
    def test_bloqueia_a_conta_depois_das_falhas_seguidas(self, client: TestClient) -> None:
        for _ in range(settings.login_max_failures_per_email):
            assert _tenta(client, "admin@valtexa.dev", "senha-errada-1234").status_code == 401

        bloqueado = _tenta(client, "admin@valtexa.dev", "senha-errada-1234")
        assert bloqueado.status_code == 429
        assert int(bloqueado.headers["Retry-After"]) > 0
        assert "Tente de novo" in bloqueado.json()["detail"]

    def test_durante_o_bloqueio_nem_a_senha_certa_entra(self, client: TestClient) -> None:
        """Senão o bloqueio viraria um oráculo: 429 para errada, 200 para certa."""
        for _ in range(settings.login_max_failures_per_email):
            _tenta(client, "admin@valtexa.dev", "senha-errada-1234")
        assert _tenta(client, "admin@valtexa.dev", DEMO_PASSWORD).status_code == 429

    def test_outra_conta_nao_e_afetada(self, client: TestClient) -> None:
        for _ in range(settings.login_max_failures_per_email):
            _tenta(client, "admin@valtexa.dev", "senha-errada-1234")
        assert _tenta(client, "agronomo@valtexa.dev", DEMO_PASSWORD).status_code == 200

    def test_acerto_zera_a_contagem(self, client: TestClient) -> None:
        for _ in range(settings.login_max_failures_per_email - 1):
            _tenta(client, "admin@valtexa.dev", "senha-errada-1234")
        assert _tenta(client, "admin@valtexa.dev", DEMO_PASSWORD).status_code == 200
        assert _tenta(client, "admin@valtexa.dev", "senha-errada-1234").status_code == 401

    def test_email_inexistente_e_limitado_igual(self, client: TestClient) -> None:
        """Tratar diferente entregaria quais contas existem."""
        for _ in range(settings.login_max_failures_per_email):
            assert _tenta(client, "ninguem@x.dev", "senha-errada-1234").status_code == 401
        assert _tenta(client, "ninguem@x.dev", "senha-errada-1234").status_code == 429

    def test_muitas_contas_do_mesmo_endereco(self, client: TestClient, monkeypatch) -> None:
        from valtexa.services import login_guard

        monkeypatch.setattr(
            login_guard, "settings", settings.model_copy(update={"login_max_failures_per_ip": 3})
        )
        for indice in range(3):
            _tenta(client, f"alvo{indice}@x.dev", "senha-comum-123456")
        assert _tenta(client, "admin@valtexa.dev", DEMO_PASSWORD).status_code == 429

    def test_as_tentativas_ficam_gravadas(self, client: TestClient, session: Session) -> None:
        _tenta(client, "admin@valtexa.dev", "senha-errada-1234")
        _tenta(client, "admin@valtexa.dev", DEMO_PASSWORD)
        linhas = session.scalars(
            select(LoginAttempt).where(LoginAttempt.email == "admin@valtexa.dev")
        ).all()
        assert [linha.success for linha in linhas] == [False, True]
