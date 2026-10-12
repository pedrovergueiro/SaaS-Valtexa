"""Banco para ``suporte-e-avisos.mjs`` (Parte 6): notificações e chamados.

Rodar a partir de ``saas/``, com o mesmo ambiente que o uvicorn vai usar::

    DATABASE_URL=sqlite:////tmp/e2e6.db STORAGE_DIR=/tmp/e2e6-storage \\
        SIMULATED_INFERENCE=true python web/e2e/prepara_suporte_e_avisos.py /tmp/e2e6.json

Cliente de demonstração, uma conta de Suporte da equipe, um robô que caiu (o worker
gera o aviso "sem comunicação") e **sem SMTP** — o aviso tem de mostrar "não enviado".
Grava os IDs no JSON.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime, timedelta

sys.path.insert(0, os.getcwd())
sys.path.insert(0, os.path.join(os.getcwd(), "tests"))

from fastapi.testclient import TestClient

from tests.helpers import provision, send_telemetry
from valtexa import worker
from valtexa.db import migrate, session_scope
from valtexa.main import app
from valtexa.models import Connectivity, Device, PlatformRole, User
from valtexa.security.passwords import hash_password
from valtexa.seed import seed_demo, sync_device_models
from valtexa.services import events, model_registry, notifications, plans

SENHA = "valtexa-demo-2026"


def main(saida: str) -> None:
    migrate()
    with session_scope() as s:
        sync_device_models(s)
        plans.sincronizar_catalogo(s)
        model_registry.sincronizar_catalogo(s)
        demo = seed_demo(s)
        s.add(User(email="suporte.e2e@equipe.valtexa.dev", full_name="Sofia do Suporte",
                   password_hash=hash_password(SENHA), platform_role=PlatformRole.SUPORTE))
    http = TestClient(app)
    login = http.post("/v1/auth/login", json={"email": "admin@valtexa.dev", "password": SENHA})
    gestor = {"Authorization": f"Bearer {login.json()['access_token']}",
              "X-Tenant-Id": login.json()["tenant_id"]}
    robo = provision(http, gestor, "ROVER_SCOUT_V1", "E2E-ROVER-6", demo["farm_id"])
    send_telemetry(robo, battery_percent=88.0)
    with session_scope() as s:
        device = s.get(Device, robo.device_id)
        device.last_seen_at = datetime.now(UTC) - timedelta(minutes=30)
        device.connectivity = Connectivity.OK
    with session_scope() as s:
        assert worker.refresh_connectivity(s) == 1
    with session_scope() as s:
        events.drain(s)
    with session_scope() as s:
        notifications.entregar_pendentes(s)  # sem SMTP: fica "não enviado", com o motivo
    with open(saida, "w") as arquivo:
        json.dump({"senha": SENHA, "device_id": robo.device_id, "tenant_id": demo["tenant_id"]},
                  arquivo)


if __name__ == "__main__":
    main(sys.argv[1])
