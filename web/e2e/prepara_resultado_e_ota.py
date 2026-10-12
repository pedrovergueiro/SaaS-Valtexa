"""Banco para ``resultado-e-ota.mjs`` (Parte 5): o ponta a ponta inteiro, mais OTA e dNATY.

Rodar a partir de ``saas/``, com o mesmo ambiente que o uvicorn vai usar::

    DATABASE_URL=sqlite:////tmp/e2e5.db STORAGE_DIR=/tmp/e2e5-storage \\
        SIMULATED_INFERENCE=true python web/e2e/prepara_resultado_e_ota.py /tmp/e2e5.json

Roda ``simulator/ponta_a_ponta.py`` (cliente, rover/ real, duas missões, aplicação),
publica um pacote OTA de configuração e o destina ao Rover (o Rover simulado aplica), e
registra uma rodada de otimização recusada num modelo. Grava os IDs no JSON.
"""

from __future__ import annotations

import io
import json
import os
import sys
import tarfile
import tempfile
from pathlib import Path

sys.path.insert(0, os.getcwd())
sys.path.insert(0, os.path.join(os.getcwd(), "tests"))  # os testes importam "helpers"

from fastapi.testclient import TestClient

from simulator.ponta_a_ponta import SENHA, executar
from tests.test_rover_integracao import ponte
from valtexa.db import migrate, session_scope
from valtexa.main import app
from valtexa.seed import seed_demo, sync_device_models
from valtexa.services import model_registry, plans


def main(saida: str) -> None:
    migrate()
    with session_scope() as s:
        sync_device_models(s)
        plans.sincronizar_catalogo(s)
        model_registry.sincronizar_catalogo(s)
        seed_demo(s)
    http = TestClient(app)
    with tempfile.TemporaryDirectory() as pasta:
        res = executar(http, ponte(http), session_scope, Path(pasta))
    assert all(p.ok for p in res.passos)
    login = http.post("/v1/auth/login", json={"email": "ops.e2e@equipe.valtexa.dev",
                                              "password": SENHA}).json()
    ops = {"Authorization": f"Bearer {login['access_token']}"}
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        dados = b'{"sync": {"chunk_size": 65536}}'
        info = tarfile.TarInfo("rover.json")
        info.size = len(dados)
        tar.addfile(info, io.BytesIO(dados))
    pacote = http.post("/v1/platform/ota/packages", params={"kind": "config", "version": "cfg-e2e"},
                       content=buf.getvalue(), headers={**ops, "Content-Type": "application/x-tar"})
    assert pacote.status_code == 201, pacote.text
    destino = http.post("/v1/platform/ota/deployments", headers=ops, json={
        "package_id": pacote.json()["id"], "device_ids": [res.dados["rover_id"]]})
    assert destino.status_code == 201, destino.text
    ia = http.post("/v1/auth/login", json={"email": "ia1.e2e@equipe.valtexa.dev",
                                           "password": SENHA}).json()
    ia_h = {"Authorization": f"Bearer {ia['access_token']}"}
    from tests.test_dnaty_registry import benchmark, relatorio

    versao = http.post("/v1/platform/models", headers=ia_h, json={
        "model_key": "coffee-foliar", "version": "9.9.9-e2e", "platform": "ground",
        "crops": ["coffee"], "metrics": {"f1": 0.91},
        "original_artifact_uri": "s3://modelos/original.onnx",
        "original_artifact_sha256": "a" * 64}).json()
    pior = benchmark("c" * 64, size_bytes=20_000_000, latency_ms_p50=15.0, f1=0.88,
                     por_classe=[{"class_name": "Rust", "recall": 0.95},
                                 {"class_name": "Phoma", "recall": 0.70}])
    http.post(f"/v1/platform/models/{versao['id']}/optimizations", headers=ia_h,
              json=relatorio(pior))
    http.post(f"/v1/platform/models/{versao['id']}/optimizations", headers=ia_h,
              json=relatorio())
    Path(saida).write_text(json.dumps({"missao2": res.dados["missao2"],
                                       "model_version_id": versao["id"], "senha": SENHA}))
    print("pronto:", saida)


if __name__ == "__main__":
    main(sys.argv[1])
