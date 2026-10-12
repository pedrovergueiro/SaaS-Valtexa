"""Etapa de otimização (dNATY) no registry — brief, seção 23.

Os benchmarks aqui são números montados no teste (o relatório real sai de
``ia/training/dnaty_pipeline.py``, testado no ``ia/`` com ONNX Runtime e com o
pacote ``dnaty`` 2.2.1 de verdade). O que se confere é o registry: recalcula o
veredito, guarda toda rodada, só leva o otimizado aceito, mantém o original
separado e não aprova otimizado sem benchmark aceito.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select

from tests.helpers import DeviceSession, provision
from tests.test_model_registry import HASH_A, _mover, _versao, chefe, ia  # noqa: F401
from valtexa.models import AuditEntry, ModelOptimization

HASH_O = "c" * 64


def benchmark(sha: str, **extra) -> dict:
    base = {
        "sha256": sha, "size_bytes": 80_000_000, "amostras": 2000,
        "accuracy": 0.93, "precision": 0.92, "recall": 0.91, "f1": 0.915,
        "por_classe": [{"class_name": "Rust", "recall": 0.95},
                       {"class_name": "Phoma", "recall": 0.88}],
        "latency_ms_p50": 40.0, "latency_ms_p95": 55.0, "fps": 25.0, "memory_mb": 300.0,
        "flops": 8_000_000_000, "hardware": "x86_64", "providers": ["CPUExecutionProvider"],
    }
    return {**base, **extra}


def relatorio(otimizado: dict | None = None, **extra) -> dict:
    return {
        "tool": "dnaty", "tool_version": "2.2.1", "dnaty_version": "2.2.1",
        "parametros": {"target_flops": 0.5},
        "original": {"artifact_uri": "s3://modelos/coffee/2.0.0/original.onnx",
                     "benchmark": benchmark(HASH_A)},
        "otimizado": {"artifact_uri": "s3://modelos/coffee/2.0.0/dnaty.onnx",
                      "benchmark": otimizado or benchmark(
                          HASH_O, size_bytes=30_000_000, latency_ms_p50=22.0, fps=45.0,
                          f1=0.912, precision=0.918, recall=0.906, flops=3_900_000_000,
                          por_classe=[{"class_name": "Rust", "recall": 0.95},
                                      {"class_name": "Phoma", "recall": 0.87}])},
        **extra,
    }


def otimizar(client: TestClient, headers: dict, vid: str, corpo: dict | None = None):
    return client.post(f"/v1/platform/models/{vid}/optimizations",
                       json=corpo or relatorio(), headers=headers)


def test_rodada_aceita_leva_o_otimizado_e_mantem_o_original(client, ia) -> None:  # noqa: F811
    vid = _versao(client, ia, metrics={"f1": 0.915},
                  original_artifact_uri="s3://modelos/coffee/2.0.0/original.onnx",
                  original_artifact_sha256=HASH_A)["id"]
    r = otimizar(client, ia, vid)
    assert r.status_code == 201, r.text
    rodada = r.json()
    assert rodada["accepted"] and rodada["applied"] and rodada["reasons"] == []
    assert "BSL 1.1" in rodada["license_note"]
    assert rodada["comparison"]["ganhos"]["size_bytes"] > 0.6
    v = client.get(f"/v1/platform/models/{vid}", headers=ia).json()
    assert v["original_artifact_sha256"] == HASH_A  # original separado e intocado
    assert v["optimized_artifact_sha256"] == HASH_O
    assert v["optimized_size_bytes"] == 30_000_000
    assert v["dnaty_version"] == "2.2.1"
    assert v["metrics"]["benchmark"]["original"]["f1"] == 0.915
    assert v["metrics"]["benchmark"]["otimizado"]["latency_ms_p50"] == 22.0


def test_menor_mas_pior_e_recusado_e_fica_no_historico(client, ia, session_factory) -> None:  # noqa: F811
    vid = _versao(client, ia, metrics={"f1": 0.915}, original_artifact_sha256=HASH_A,
                  original_artifact_uri="s3://x/original.onnx")["id"]
    pior = benchmark(HASH_O, size_bytes=10_000_000, latency_ms_p50=15.0, f1=0.90,
                     por_classe=[{"class_name": "Rust", "recall": 0.95},
                                 {"class_name": "Phoma", "recall": 0.70}])
    # O relatório diz "aceito": o registry não acredita, recalcula.
    r = otimizar(client, ia, vid, relatorio(pior, aceito=True))
    assert r.status_code == 201
    corpo = r.json()
    assert corpo["accepted"] is False and corpo["applied"] is False
    assert any("Recall de Phoma" in m for m in corpo["reasons"])
    assert any("F1 caiu" in m for m in corpo["reasons"])
    v = client.get(f"/v1/platform/models/{vid}", headers=ia).json()
    assert v["optimized_artifact_sha256"] is None
    lista = client.get(f"/v1/platform/models/{vid}/optimizations", headers=ia).json()
    assert len(lista) == 1 and lista[0]["accepted"] is False
    with session_factory() as s:
        trilha = s.scalars(select(AuditEntry).where(
            AuditEntry.action == "model_version.optimization")).all()
        assert len(trilha) == 1 and trilha[0].payload["accepted"] is False


def test_sem_ganho_e_recusado_e_criterio_e_configuravel(client, ia) -> None:  # noqa: F811
    vid = _versao(client, ia, metrics={"f1": 0.915}, original_artifact_sha256=HASH_A,
                  original_artifact_uri="s3://x/original.onnx")["id"]
    quase_igual = benchmark(HASH_O, size_bytes=76_000_000)  # 5 % menor e só
    r = otimizar(client, ia, vid, relatorio(quase_igual)).json()
    assert not r["accepted"] and any("Sem ganho" in m for m in r["reasons"])
    frouxo = relatorio(quase_igual, criterio={"ganho_minimo": 0.04})
    assert otimizar(client, ia, vid, frouxo).json()["accepted"]
    ruim = relatorio(quase_igual, criterio={"ganho_minimo": 0})
    assert otimizar(client, ia, vid, ruim).status_code == 409
    estranho = relatorio(quase_igual, criterio={"aceita_tudo": True})
    assert otimizar(client, ia, vid, estranho).status_code == 409


def test_benchmark_de_outro_artefato_e_estado_errado(client, ia, chefe) -> None:  # noqa: F811
    vid = _versao(client, ia, metrics={"f1": 0.9}, original_artifact_sha256="d" * 64,
                  original_artifact_uri="s3://x/o.onnx")["id"]
    r = otimizar(client, ia, vid)
    assert r.status_code == 409 and "outro artefato" in r.json()["detail"]
    mesmo = relatorio(benchmark(HASH_A))
    vid2 = _versao(client, ia, version="2.0.1", metrics={"f1": 0.9})["id"]
    assert otimizar(client, ia, vid2, mesmo).status_code == 409
    # versão sem original: o relatório preenche (com a URI)
    assert otimizar(client, ia, vid2).json()["accepted"]
    v = client.get(f"/v1/platform/models/{vid2}", headers=ia).json()
    assert v["original_artifact_sha256"] == HASH_A
    # depois da aprovação, não entra rodada nova
    assert _mover(client, ia, vid2, "validacao").status_code == 200
    assert _mover(client, chefe, vid2, "aprovado").status_code == 200
    assert otimizar(client, ia, vid2).status_code == 409


def test_otimizado_sem_benchmark_aceito_nao_e_aprovado(client, ia, chefe) -> None:  # noqa: F811
    vid = _versao(client, ia, metrics={"f1": 0.9}, original_artifact_sha256=HASH_A,
                  original_artifact_uri="s3://x/o.onnx",
                  optimized_artifact_uri="s3://x/dnaty.onnx",
                  optimized_artifact_sha256=HASH_O, dnaty_version="2.2.1")["id"]
    assert _mover(client, ia, vid, "validacao").status_code == 200
    r = _mover(client, chefe, vid, "aprovado")
    assert r.status_code == 409 and "benchmark aceito" in r.json()["detail"]
    assert otimizar(client, ia, vid).json()["accepted"]
    assert _mover(client, chefe, vid, "aprovado").status_code == 200


def test_comercial_nao_registra_otimizacao(client, ia, equipe) -> None:  # noqa: F811
    from valtexa.models import PlatformRole

    vid = _versao(client, ia, metrics={"f1": 0.9}, original_artifact_sha256=HASH_A,
                  original_artifact_uri="s3://x/o.onnx")["id"]
    comercial = equipe(PlatformRole.COMERCIAL)
    assert otimizar(client, comercial, vid).status_code == 403


def test_robo_recebe_o_otimizado_aceito(client, ia, chefe, admin_token, demo,  # noqa: F811
                                        session_factory) -> None:
    rover: DeviceSession = provision(client, admin_token, "ROVER_SCOUT_V1", "OPT-R1",
                                     demo["farm_id"])
    vid = _versao(client, ia, metrics={"f1": 0.915}, original_artifact_sha256=HASH_A,
                  original_artifact_uri="s3://x/original.onnx")["id"]
    assert otimizar(client, ia, vid).json()["accepted"]
    for quem, para in ((ia, "validacao"), (chefe, "aprovado"), (ia, "staging"),
                       (ia, "producao")):
        assert _mover(client, quem, vid, para).status_code == 200
    item = rover.request("GET", "/v1/device/models").json()[0]
    assert (item["artifact_kind"], item["artifact_sha256"]) == ("otimizado", HASH_O)
    with session_factory() as s:
        assert s.scalar(select(ModelOptimization.accepted)) is True


def test_registry_nao_conta_ruido_de_medicao_como_ganho() -> None:
    """O registry recalcula o veredito com a mesma regra do ``ia/``: o mesmo modelo
    medido duas vezes (latência oscilando, memória da primeira sessão maior) não
    pode passar como "otimizado"."""
    from valtexa.services.dnaty import CriterioDeAceite, avaliar

    base = {"accuracy": 0.9, "precision": 0.9, "recall": 0.9, "f1": 0.9,
            "latency_ms_p50": 0.05, "memory_mb": 8.8, "size_bytes": 1000, "flops": 1000,
            "por_classe": [{"class_name": "A", "recall": 0.9}]}
    mesmo = {**base, "latency_ms_p50": 0.04, "memory_mb": 0.0}
    v = avaliar(base, mesmo, CriterioDeAceite())
    assert not v["aceito"] and max(v["ganhos"].values()) == 0
    assert avaliar(base, mesmo, CriterioDeAceite.from_dict(
        {"ruido_latencia_ms": 0, "ruido_memoria_mb": 0}))["aceito"]
