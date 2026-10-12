"""Telas da Parte 8 pelo lado da API: mapa da missão, linha do tempo, arquivo da Edge AI, painel.

O que se prova:

1. o mapa da missão traz a rota na ordem dos quadros, só os resultados que são
   evento como ponto, e as plantas com posição e estado; rota longa é reduzida;
2. a linha do tempo do talhão liga varredura → ocorrências → prescrição (com a
   varredura de origem) → aprovação → aplicação → verificação, do mais novo ao mais velho;
3. o arquivo original de um registro da Edge AI sai pela API, no escopo do cliente;
4. o painel ganha fazendas, talhões, hectares, ocorrências, sincronização por robô,
   saúde da frota e da IA — tudo do cliente, nada de outro;
5. outro cliente não alcança nenhuma das rotas novas.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from tests.helpers import provision
from tests.test_isolamento_openapi import atacante  # noqa: F401 - fixture
from valtexa.models import (
    Agreement,
    Application,
    ApplicationState,
    Asset,
    AssetKind,
    Decision,
    DecisionOutcome,
    Diagnosis,
    DiagnosisStatus,
    EdgeRecord,
    EdgeUpload,
    Field,
    Mission,
    MissionKind,
    MissionState,
    Observation,
    Verification,
    VerificationConclusion,
)
from valtexa.services import storage, visao_operacional

JPEG = b"\xff\xd8\xff\xe0" + b"original-da-planta" * 20


@pytest.fixture
def cenario(client: TestClient, admin_token: dict, demo: dict, session: Session) -> dict:
    """Uma varredura com 6 quadros em 3 plantas (uma com evento), a prescrição que nasceu
    dela, a aplicação e a verificação — direto no banco, sem passar pela ponte."""
    robo = provision(client, admin_token, "ROVER_SCOUT_V1", "MAPA-001", demo["farm_id"])
    t0 = datetime.now(UTC) - timedelta(days=2)
    base = {"tenant_id": demo["tenant_id"], "farm_id": demo["farm_id"],
            "field_id": demo["field_id"], "device_id": robo.device_id}
    varredura = Mission(kind=MissionKind.SCOUT, state=MissionState.COMPLETED, **base,
                        created_at=t0,
                        waypoints=[[-45.80, -21.90], [-45.79, -21.90]],
                        started_at=t0, finished_at=t0 + timedelta(minutes=30))
    session.add(varredura)
    session.flush()
    registros = []
    for i, (planta, tipo) in enumerate([("L1-P001", "NORMAL"), ("L1-P001", "NORMAL"),
                                        ("L1-P002", "POSSIVEL_DOENCA"), ("L1-P002", "NORMAL"),
                                        ("L1-P003", "NORMAL"), ("L1-P003", "NORMAL")]):
        r = EdgeRecord(tenant_id=demo["tenant_id"], device_id=robo.device_id,
                       record_id=f"res-{i}", kind="result", type=tipo, sha256="0" * 64,
                       mission_id=varredura.id, field_id=demo["field_id"],
                       occurred_at=t0 + timedelta(seconds=10 * i), received_at=t0,
                       label="Rust" if tipo != "NORMAL" else None, confidence=0.9,
                       model_key="banana_rover", model_version="1.0",
                       lat=-21.9 + i * 1e-5, lon=-45.8 + i * 1e-5,
                       payload={"region": {"plant_id": planta, "row": 1},
                                "frame": {"camera_id": "cam-0"}})
        session.add(r)
        registros.append(r)
    session.add(EdgeRecord(tenant_id=demo["tenant_id"], device_id=robo.device_id,
                           record_id="ev-sem-posicao", kind="event", type="MISSION_STARTED",
                           sha256="0" * 64, mission_id=varredura.id, occurred_at=t0,
                           received_at=t0, payload={}))
    guardado = storage.store.put(JPEG, "image/jpeg", namespace=demo["tenant_id"])
    asset = Asset(tenant_id=demo["tenant_id"], kind=AssetKind.IMAGE, content_type="image/jpeg",
                  size_bytes=len(JPEG), sha256=hashlib.sha256(JPEG).hexdigest(),
                  storage_key=guardado.key, device_id=robo.device_id)
    session.add(asset)
    session.flush()
    session.add(EdgeUpload(tenant_id=demo["tenant_id"], device_id=robo.device_id,
                           upload_id="up-original-2", sha256=asset.sha256,
                           size_bytes=len(JPEG), content_type="image/jpeg", chunk_size=4096,
                           total_chunks=1, status="complete", record_id="res-2",
                           role="original", asset_id=asset.id))

    # a nuvem confirmou a doença: observação → diagnóstico → decisão → prescrição
    obs = Observation(tenant_id=demo["tenant_id"], farm_id=demo["farm_id"],
                      field_id=demo["field_id"],
                      mission_id=varredura.id, device_id=robo.device_id, captured_at=t0,
                      lat=-21.9, lon=-45.8)
    session.add(obs)
    session.flush()
    registros[2].observation_id = obs.id
    diag = Diagnosis(tenant_id=demo["tenant_id"], observation_id=obs.id, label="Rust",
                     field_id=demo["field_id"], status=DiagnosisStatus.AI_VALIDATED,
                     agreement=Agreement.AGREE, confidence=0.94, pipeline_version="teste")
    session.add(diag)
    session.flush()
    decisao = Decision(tenant_id=demo["tenant_id"], diagnosis_id=diag.id,
                       field_id=demo["field_id"], outcome=DecisionOutcome.APPLICATION_CANDIDATE,
                       reason_code="teste", rationale="teste", rule_version="teste")
    session.add(decisao)
    session.flush()
    pulverizacao = Mission(kind=MissionKind.SPRAY, state=MissionState.COMPLETED, **base,
                           decision_id=decisao.id, authorized_rate_l_ha=120.0,
                           authorized_quantity_l=30.0, created_at=t0 + timedelta(hours=1),
                           approved_at=t0 + timedelta(hours=2),
                           started_at=t0 + timedelta(hours=3))
    session.add(pulverizacao)
    session.flush()
    aplicacao = Application(tenant_id=demo["tenant_id"], mission_id=pulverizacao.id,
                            device_id=robo.device_id, field_id=demo["field_id"],
                            state=ApplicationState.COMPLETED,
                            started_at=t0 + timedelta(hours=3),
                            stopped_at=t0 + timedelta(hours=3, minutes=20), amount_used_l=28.0,
                            area_ha=0.25)
    session.add(aplicacao)
    session.flush()
    session.add(Verification(tenant_id=demo["tenant_id"], application_id=aplicacao.id,
                             field_id=demo["field_id"], before_ratio=0.33, after_ratio=0.0,
                             conclusion=VerificationConclusion.IMPROVED))
    session.commit()
    return {"robo": robo, "varredura": varredura.id, "pulverizacao": pulverizacao.id,
            "aplicacao": aplicacao.id, "registro_original": registros[2].id,
            "decisao": decisao.id}


def test_mapa_da_missao(client: TestClient, admin_token: dict, cenario: dict) -> None:
    r = client.get(f"/v1/missions/{cenario['varredura']}/map", headers=admin_token)
    assert r.status_code == 200, r.text
    mapa = r.json()
    assert mapa["track_points_total"] == 6 and len(mapa["track"]) == 6
    assert mapa["track"][0] == [pytest.approx(-45.8), pytest.approx(-21.9)]
    assert mapa["planned_route"] == [[-45.80, -21.90], [-45.79, -21.90]]
    # só o resultado que é evento vira ponto (o evento sem posição fica fora)
    assert [(e["type"], e["plant_id"], e["has_original"]) for e in mapa["events"]] == [
        ("POSSIVEL_DOENCA", "L1-P002", True)]
    plantas = {p["plant_id"]: p for p in mapa["plants"]}
    assert set(plantas) == {"L1-P001", "L1-P002", "L1-P003"}
    assert plantas["L1-P002"]["status"] == "doente" and plantas["L1-P002"]["label"] == "Rust"
    assert plantas["L1-P001"]["status"] == "sadia" and plantas["L1-P001"]["lat"] is not None
    assert mapa["incidence"]["diseased"] == 1 and mapa["plants_seen"] == 3


def test_rota_longa_e_reduzida_mantendo_o_fim() -> None:
    pontos = [[i, i] for i in range(4501)]
    menor = visao_operacional._decimar(pontos, 2000)
    assert len(menor) <= 2001 and menor[0] == [0, 0] and menor[-1] == [4500, 4500]
    assert visao_operacional._decimar(pontos[:10], 2000) == pontos[:10]


def test_linha_do_tempo_do_talhao(client: TestClient, admin_token: dict, demo: dict,
                                  cenario: dict) -> None:
    r = client.get(f"/v1/fields/{demo['field_id']}/history", headers=admin_token)
    assert r.status_code == 200, r.text
    passos = r.json()
    etapas = [p["stage"] for p in passos]
    assert etapas == ["verificacao", "aplicacao", "aprovacao", "prescricao",
                      "ocorrencias", "missao"], etapas
    por = {p["stage"]: p for p in passos}
    assert por["prescricao"]["origin_mission_id"] == cenario["varredura"]
    assert por["prescricao"]["decision_id"] == cenario["decisao"]
    assert por["aprovacao"]["origin_mission_id"] == cenario["varredura"]
    assert por["aplicacao"]["mission_id"] == cenario["pulverizacao"]
    assert por["aplicacao"]["amount_used_l"] == 28.0
    assert por["verificacao"]["application_id"] == cenario["aplicacao"]
    assert por["verificacao"]["conclusion"] == "improved"
    assert por["ocorrencias"]["diseased"] == 1 and por["ocorrencias"]["plants_seen"] == 3


def test_arquivo_original_do_registro(client: TestClient, admin_token: dict,
                                      cenario: dict) -> None:
    url = f"/v1/edge/records/{cenario['registro_original']}/files/up-original-2"
    r = client.get(url, headers=admin_token)
    assert r.status_code == 200 and r.content == JPEG
    assert r.headers["content-type"] == "image/jpeg"
    assert client.get(f"/v1/edge/records/{cenario['registro_original']}/files/outro",
                      headers=admin_token).status_code == 404
    assert client.get(url).status_code == 401


def test_painel_com_os_numeros_da_secao_45(client: TestClient, admin_token: dict,
                                          demo: dict, cenario: dict, session: Session) -> None:
    r = client.get("/v1/dashboard", headers=admin_token)
    assert r.status_code == 200, r.text
    v = r.json()["overview"]
    area = sum(f.area_ha or 0 for f in session.scalars(
        select(Field).where(Field.tenant_id == demo["tenant_id"])))
    assert v["fields"] >= 1 and v["farms"] >= 1
    assert v["hectares"] == pytest.approx(round(area, 2))
    assert v["occurrences_7d"] == 1 and v["occurrences_by_category_7d"] == {"POSSIVEL_DOENCA": 1}
    assert v["scouts_completed_30d"] == 1
    robo = next(s for s in v["sync"] if s["serial_number"] == "MAPA-001")
    assert robo["last_record_received_at"] is not None and robo["uploads_incomplete"] == 0
    assert sum(v["fleet_health"].values()) == len(v["sync"])
    assert v["ai_health"]["edge_results_24h"] == 0  # os quadros do cenário são de anteontem
    assert v["ai_health"]["cloud_service"] in {"ok", "fora", "simulado", "desligado"}


def test_outro_cliente_nao_alcanca_as_rotas_novas(client: TestClient, demo: dict,
                                                 cenario: dict, atacante: dict) -> None:  # noqa: F811
    for token in atacante["tokens"].values():
        for url in (f"/v1/missions/{cenario['varredura']}/map",
                    f"/v1/fields/{demo['field_id']}/history",
                    f"/v1/edge/records/{cenario['registro_original']}/files/up-original-2"):
            assert client.get(url, headers=token).status_code in (403, 404), url
        painel = client.get("/v1/dashboard", headers=token).json()["overview"]
        assert painel["occurrences_7d"] == 0
        assert all(s["serial_number"] != "MAPA-001" for s in painel["sync"])
