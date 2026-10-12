"""Banco para ``observabilidade.mjs`` (Parte 7): saúde dos robôs e alertas.

Rodar a partir de ``saas/``, com o mesmo ambiente que o uvicorn vai usar::

    DATABASE_URL=sqlite:////tmp/e2e7.db STORAGE_DIR=/tmp/e2e7-storage \\
        SIMULATED_INFERENCE=true python web/e2e/prepara_observabilidade.py /tmp/e2e7.json

Cliente de demonstração com dois robôs: um saudável e um com disco a 96 % e uma
câmera fora (saúde mandada pela telemetria, como o Rover Runtime manda); as regras
avaliadas uma vez (alertas disparados, avisos criados); uma conta de Operações.
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.getcwd())
sys.path.insert(0, os.path.join(os.getcwd(), "tests"))

from fastapi.testclient import TestClient

from tests.helpers import provision, send_telemetry
from valtexa.db import migrate, session_scope
from valtexa.main import app
from valtexa.models import PlatformRole, User
from valtexa.security.passwords import hash_password
from valtexa.seed import seed_demo, sync_device_models
from valtexa.services import alertas, events, model_registry, plans

SENHA = "valtexa-demo-2026"


def main(saida: str) -> None:
    migrate()
    with session_scope() as s:
        sync_device_models(s)
        plans.sincronizar_catalogo(s)
        model_registry.sincronizar_catalogo(s)
        alertas.sincronizar_catalogo(s)
        demo = seed_demo(s)
        s.add(User(email="operacoes.e2e@equipe.valtexa.dev", full_name="Otávio de Operações",
                   password_hash=hash_password(SENHA), platform_role=PlatformRole.OPERACOES))
    http = TestClient(app)
    login = http.post("/v1/auth/login", json={"email": "admin@valtexa.dev", "password": SENHA})
    gestor = {"Authorization": f"Bearer {login.json()['access_token']}",
              "X-Tenant-Id": login.json()["tenant_id"]}
    bom = provision(http, gestor, "ROVER_SCOUT_V1", "E2E-SAUDAVEL", demo["farm_id"])
    send_telemetry(bom, battery_percent=91.0, health={
        "cpu_percent": 22.0, "memory_percent": 41.0, "disk_percent": 35.0, "temperature_c": 38.0,
        "accelerator": {"name": "CPU (ONNX Runtime)", "percent": None},
        "cameras": [{"id": "cam-0", "ok": True}, {"id": "cam-1", "ok": True}],
        "sensors": {"gps": "ok", "imu": "nao_monitorado", "ambiente": "ok"},
        "sync": {"pending": 0, "blocked": False}, "network": {"online": True},
        "simulated": ["camera", "sensores", "sistema"]})
    ruim = provision(http, gestor, "ROVER_SCOUT_V1", "E2E-DISCO-CHEIO", demo["farm_id"])
    send_telemetry(ruim, battery_percent=64.0, health={
        "cpu_percent": 87.0, "memory_percent": 72.0, "disk_percent": 96.0, "temperature_c": 49.0,
        "cameras": [{"id": "cam-0", "ok": True}, {"id": "cam-1", "ok": False,
                                                    "detail": "sem quadro há 40 s"}],
        "sensors": {"gps": "ok", "imu": "nao_monitorado", "ambiente": "ok"},
        "sync": {"pending": 3, "blocked": False}, "network": {"online": True},
        "simulated": ["camera", "sensores", "sistema"]})
    with session_scope() as s:
        rel = alertas.avaliar(s)
        assert rel.disparados >= 2, rel
    with session_scope() as s:
        events.drain(s)
    with open(saida, "w") as arquivo:
        json.dump({"senha": SENHA, "tenant_id": demo["tenant_id"]}, arquivo)


if __name__ == "__main__":
    main(sys.argv[1])
