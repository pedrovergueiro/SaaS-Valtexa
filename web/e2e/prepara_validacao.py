"""Banco de demonstração para ``validacao.mjs`` (Parte 11, rodada 3).

Rodar a partir de ``saas/``, com o mesmo ambiente que o uvicorn vai usar::

    DATABASE_URL=sqlite:////tmp/e2e.db STORAGE_DIR=/tmp/e2e-storage \\
        SIMULATED_INFERENCE=true python web/e2e/prepara_validacao.py

Cria o seed de demonstração, a conta chefe@valtexa.dev (superadmin) e roda a FASE 0
inteira do simulador (``simulator/fase0.py``: Rover Runtime de verdade, bancada
SIMULADA, cada ensaio assinado e com o veredito do servidor). Imprime o id do rover.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.getcwd())

from fastapi.testclient import TestClient
from valtexa_rover.hal.interfaces import HttpResponse

from simulator.fase0 import executar
from valtexa.db import migrate, session_scope
from valtexa.main import app
from valtexa.models import PlatformRole, User
from valtexa.security.passwords import hash_password
from valtexa.seed import seed_demo, sync_device_models
from valtexa.services import model_registry, plans

SENHA = "valtexa-demo-2026"


def ponte(client: TestClient):
    """A "rede" do robô: cada requisição assinada vai à API (como em test_rover_integracao)."""

    def enviar(method: str, path: str, body: bytes, headers: dict) -> HttpResponse:
        r = client.request(method, path, content=body, headers=headers)
        return HttpResponse(r.status_code, r.content, dict(r.headers))

    return enviar


def main() -> None:
    migrate()
    with session_scope() as sessao:
        sync_device_models(sessao)
        plans.sincronizar_catalogo(sessao)
        model_registry.sincronizar_catalogo(sessao)
        seed_demo(sessao)
        sessao.add(User(email="chefe@valtexa.dev", full_name="Chefe", platform_role=(
            PlatformRole.SUPERADMIN), password_hash=hash_password(SENHA)))
    cliente = TestClient(app)
    with tempfile.TemporaryDirectory() as pasta:
        res = executar(cliente, ponte(cliente), session_scope, Path(pasta))
    print(res.dados["rover_id"])


if __name__ == "__main__":
    main()
