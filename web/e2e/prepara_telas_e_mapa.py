"""Banco para ``telas-e-mapa.mjs`` (Parte 8): o ponta a ponta inteiro e os arquivos que a
equipe vai subir pela tela.

Rodar a partir de ``saas/``, com o mesmo ambiente que o uvicorn vai usar::

    DATABASE_URL=sqlite:////tmp/e2e8.db STORAGE_DIR=/tmp/e2e8-storage \\
        SIMULATED_INFERENCE=true python web/e2e/prepara_telas_e_mapa.py /tmp/e2e8.json

Roda ``simulator/ponta_a_ponta.py`` (cliente, rover/ real, duas varreduras, prescrição,
aplicação), registra uma versão de modelo em TREINAMENTO para a rodada dNATY e grava em
disco o ``.tar`` de configuração e o relatório do ``dnaty_pipeline.py`` que o roteiro
sobe **pela tela** (antes da Parte 8, só pela API). Os IDs vão para o JSON.
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
from tests.test_dnaty_registry import HASH_A, relatorio
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
    assert all(p.ok for p in res.passos), [p for p in res.passos if not p.ok]

    ia = http.post("/v1/auth/login", json={"email": "ia1.e2e@equipe.valtexa.dev",
                                           "password": SENHA}).json()
    ia_h = {"Authorization": f"Bearer {ia['access_token']}"}
    versao = http.post("/v1/platform/models", headers=ia_h, json={
        "model_key": "coffee-foliar", "version": "9.9.8-e2e", "platform": "ground",
        "crops": ["coffee"], "metrics": {"f1": 0.91},
        "original_artifact_uri": "s3://modelos/original.onnx",
        "original_artifact_sha256": HASH_A})
    assert versao.status_code == 201, versao.text

    pasta = Path(saida).parent
    rel = relatorio(aceito=True)
    rel["original"] = {"path": "/treino/coffee/original.onnx",
                       "benchmark": rel["original"]["benchmark"]}
    rel["otimizado"] = {"path": "/treino/coffee/original.otimizado.onnx",
                        "benchmark": rel["otimizado"]["benchmark"]}  # sem URI: a tela pede
    caminho_rel = pasta / "e2e8-dnaty.json"
    caminho_rel.write_text(json.dumps(rel, ensure_ascii=False, indent=2), encoding="utf-8")

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        dados = b'{"sync": {"chunk_size": 32768}}'
        info = tarfile.TarInfo("rover.json")
        info.size = len(dados)
        tar.addfile(info, io.BytesIO(dados))
    caminho_tar = pasta / "e2e8-config.tar"
    caminho_tar.write_bytes(buf.getvalue())

    d = res.dados
    Path(saida).write_text(json.dumps({
        "missao1": d["missao1"], "missao2": d["missao2"], "field_id": d["field_id"],
        "rover_id": d["rover_id"], "model_version_id": versao.json()["id"], "senha": SENHA,
        "tar": str(caminho_tar), "relatorio_dnaty": str(caminho_rel),
    }))
    print("pronto:", saida)


if __name__ == "__main__":
    main(sys.argv[1])
