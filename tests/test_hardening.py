"""Hardening (F18, seções 36, 43 e 51): disputa entre workers, limite por robô,
uploads abandonados e a varredura da ponte Edge AI → nuvem."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select

from tests.helpers import provision
from valtexa.api.routers import edge_sync as rota_edge
from valtexa.config import settings
from valtexa.models import EdgeUpload, JobKind, ProcessingJob, SubjectType
from valtexa.services import edge_sync, jobs


def test_dois_workers_nao_pegam_o_mesmo_trabalho(session_factory, demo, monkeypatch) -> None:
    with session_factory() as s:
        job = jobs.enqueue(s, tenant_id=demo["tenant_id"], kind=JobKind.COLLECTION_INGEST,
                           subject_type=SubjectType.COLLECTION, subject_id="coleta-x")
        s.commit()
        job_id = job.id
    a, b = session_factory(), session_factory()
    try:
        # B leu a fila (o trabalho ainda estava QUEUED) ...
        assert b.get(ProcessingJob, job_id).state == "queued"
        # ... e A reivindicou e confirmou antes de B.
        monkeypatch.setattr(jobs, "worker_id", lambda: "worker-A")
        assert jobs.claim(a).id == job_id
        a.commit()
        monkeypatch.setattr(jobs, "worker_id", lambda: "worker-B")
        assert jobs.claim(b) is None, "B não pode executar o que A já pegou"
        b.commit()
    finally:
        a.close()
        b.close()
    with session_factory() as s:
        linha = s.get(ProcessingJob, job_id)
        assert (linha.locked_by, linha.attempts) == ("worker-A", 1)


def test_limite_por_robo_devolve_429_com_retry_after(
    client: TestClient, admin_token, demo, monkeypatch
) -> None:
    robo = provision(client, admin_token, "ROVER_SCOUT_V1", "LIM-1", demo["farm_id"])
    outro = provision(client, admin_token, "ROVER_SCOUT_V1", "LIM-2", demo["farm_id"])
    # As configurações são congeladas: troca-se o objeto que a rota lê.
    rota_edge.limite_do_robo.limpar()
    monkeypatch.setattr(rota_edge, "settings", settings.model_copy(
        update={"device_rate_per_minute": 10}))
    codigos = [robo.request("GET", "/v1/device/uploads/nao-existe").status_code
               for _ in range(12)]
    assert codigos[:10] == [404] * 10 and codigos[10:] == [429, 429]
    r = robo.request("GET", "/v1/device/uploads/nao-existe")
    assert r.status_code == 429 and int(r.headers["retry-after"]) >= 1
    # O balde é por robô: o outro continua sendo atendido.
    assert outro.request("GET", "/v1/device/uploads/nao-existe").status_code == 404
    rota_edge.limite_do_robo.limpar()


def test_upload_abandonado_e_limpo_e_o_completo_nao(
    client: TestClient, admin_token, demo, session_factory
) -> None:
    robo = provision(client, admin_token, "ROVER_SCOUT_V1", "TTL-1", demo["farm_id"])
    aberto = robo.request("POST", "/v1/device/uploads", json_body={
        "upload_id": "velho", "sha256": "a" * 64, "size_bytes": 5000,
        "content_type": "image/jpeg", "chunk_size": 4096})
    assert aberto.status_code == 200
    robo.request("PUT", "/v1/device/uploads/velho/chunks/0", content=b"x" * 4096)
    with session_factory() as s:
        linha = s.scalars(select(EdgeUpload).where(EdgeUpload.upload_id == "velho")).one()
        assert edge_sync.staging.received(linha.id) == {0}
        pk = linha.id
        # ainda dentro do prazo: fica
        assert edge_sync.limpar_abandonados(s) == 0
        removidos = edge_sync.limpar_abandonados(
            s, agora=datetime.now(UTC) + timedelta(hours=settings.upload_ttl_hours + 1))
        s.commit()
        assert removidos == 1
        assert edge_sync.staging.received(pk) == set()
    # O robô que volta depois reabre do zero.
    de_novo = robo.request("POST", "/v1/device/uploads", json_body={
        "upload_id": "velho", "sha256": "a" * 64, "size_bytes": 5000,
        "content_type": "image/jpeg", "chunk_size": 4096})
    assert de_novo.status_code == 200 and de_novo.json()["received_chunks"] == []
