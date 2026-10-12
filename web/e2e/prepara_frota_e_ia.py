"""Banco de demonstração para ``frota-e-ia.mjs`` (Parte 3).

Rodar a partir de ``saas/``, com o mesmo ambiente que o uvicorn vai usar::

    DATABASE_URL=sqlite:////tmp/e2e.db STORAGE_DIR=/tmp/e2e-storage \\
        SIMULATED_INFERENCE=true python web/e2e/prepara_frota_e_ia.py

Cria o seed de demonstração, as contas ia@, operacoes@ e chefe@valtexa.dev e dois
rovers que falam o protocolo de verdade (sessão com versões e telemetria): o
E2E-R1 com o modelo designado e o E2E-R2 com outro modelo e uma falha de câmera.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.getcwd())

from fastapi.testclient import TestClient

from tests.helpers import provision, send_telemetry
from valtexa.db import migrate, session_scope
from valtexa.main import app
from valtexa.models import PlatformRole, User
from valtexa.security.passwords import hash_password
from valtexa.seed import seed_demo, sync_device_models
from valtexa.services import model_registry, plans

SENHA = "valtexa-demo-2026"
EQUIPE = {
    "ia@valtexa.dev": PlatformRole.IA_DADOS,
    "operacoes@valtexa.dev": PlatformRole.OPERACOES,
    "chefe@valtexa.dev": PlatformRole.SUPERADMIN,
}


def main() -> None:
    migrate()
    with session_scope() as sessao:
        sync_device_models(sessao)
        plans.sincronizar_catalogo(sessao)
        model_registry.sincronizar_catalogo(sessao)
        demo = seed_demo(sessao)
        for email, papel in EQUIPE.items():
            sessao.add(
                User(
                    email=email,
                    full_name=email,
                    password_hash=hash_password(SENHA),
                    platform_role=papel,
                )
            )

    cliente = TestClient(app)
    login = cliente.post(
        "/v1/auth/login", json={"email": "admin@valtexa.dev", "password": SENHA}
    ).json()
    admin = {"Authorization": f"Bearer {login['access_token']}", "X-Tenant-Id": login["tenant_id"]}

    r1 = provision(cliente, admin, "ROVER_SCOUT_V1", "E2E-R1", demo["farm_id"])
    r1.request(
        "POST",
        "/v1/device/session",
        json_body={
            "runtime_version": "0.4.0",
            "edge_ai_version": "0.2.1",
            "model_key": "coffee-foliar",
            "model_version": "1.0.0",
            "dnaty_version": "2.2.1",
        },
    )
    send_telemetry(
        r1,
        battery_percent=82.0,
        temperature_c=39.5,
        storage_total_bytes=64_000_000_000,
        storage_free_bytes=9_000_000_000,
        operating_hours=212.4,
    )

    r2 = provision(cliente, admin, "ROVER_SCOUT_V1", "E2E-R2", demo["farm_id"])
    r2.request(
        "POST",
        "/v1/device/session",
        json_body={"model_key": "leaf-foliar", "model_version": "1.0.0"},
    )
    send_telemetry(
        r2, battery_percent=55.0, faults=[{"code": "CAM_LATERAL", "message": "sem imagem"}]
    )
    print("pronto:", demo["tenant_id"])


if __name__ == "__main__":
    main()
