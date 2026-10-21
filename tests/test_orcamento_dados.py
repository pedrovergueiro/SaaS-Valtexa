"""Orçamento de dados por robô: o teto na missão assinada e o relatório de consumo."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select

from tests.helpers import provision, send_telemetry
from valtexa.models import AuditEntry, Device, Mission
from valtexa.models.enums import MissionKind, MissionState
from valtexa.services import edge_sync
from valtexa.services.mission_manager import mission_command_body

DADOS = {"dia": "2026-10-18", "usado_bytes": 1_500_000_000, "enviados_bytes": 1_400_000_000,
         "recebidos_bytes": 100_000_000, "teto_dia_bytes": 2_000_000_000, "fracao_usada": 0.75,
         "origem_do_teto": "rover.json", "prioridade_maxima_liberada": 4, "adiados": 812,
         "retidos": 3120, "tempestade": True,
         "por_classe": {"arquivos": 1_300_000_000, "registros": 150_000_000,
                        "inventada": 9, "telemetria": -5}}


def _registro(robo, rid: str, tipo: str, kind: str = "event", **payload) -> dict:
    corpo = {"id": rid, "kind": kind, "type": tipo, "device_id": robo.device_id,
             "occurred_at": datetime.now(UTC).isoformat(), "payload": payload}
    return {"id": rid, "kind": kind, "type": tipo,
            "sha256": edge_sync.canonical_sha256(corpo), "body": corpo}


def test_teto_vai_na_missao_assinada_e_e_auditado(client, admin_token, demo, session) -> None:
    robo = provision(client, admin_token, "ROVER_SCOUT_V1", "RV-DADOS-1", demo["farm_id"])
    url = f"/v1/devices/{robo.device_id}/orcamento-dados"
    r = client.put(url, json={"bytes_dia": 3_000_000_000, "bytes_missao": 800_000_000},
                   headers=admin_token)
    assert r.status_code == 200, r.text
    assert r.json()["teto"] == {"bytes_dia": 3_000_000_000, "bytes_missao": 800_000_000,
                                "origem": "plataforma", "efetivo_dia_bytes": 3_000_000_000}
    assert client.put(url, json={"bytes_dia": -1}, headers=admin_token).status_code == 422
    assert client.put(url, json={"teto": 1}, headers=admin_token).status_code == 422

    missao = Mission(tenant_id=demo["tenant_id"], kind=MissionKind.SCOUT,
                     state=MissionState.AUTHORIZED, farm_id=demo["farm_id"],
                     field_id=demo["field_id"], device_id=robo.device_id)
    session.add(missao)
    session.commit()
    assert mission_command_body(session, missao)["orcamento_dados"] == {
        "bytes_dia": 3_000_000_000, "bytes_missao": 800_000_000}
    trilha = session.scalars(select(AuditEntry).where(
        AuditEntry.action == "device.orcamento_dados")).all()
    assert trilha and trilha[-1].payload["depois"]["bytes_dia"] == 3_000_000_000

    # os dois nulos apagam: o robô volta ao rover.json (a missão não leva teto)
    assert client.put(url, json={}, headers=admin_token).json()["teto"]["origem"] == "rover.json"
    session.expire_all()
    assert mission_command_body(session, missao)["orcamento_dados"] is None


def test_operador_nao_muda_o_teto(client, admin_token, operator_token, demo) -> None:
    robo = provision(client, admin_token, "ROVER_SCOUT_V1", "RV-DADOS-2", demo["farm_id"])
    r = client.put(f"/v1/devices/{robo.device_id}/orcamento-dados", json={"bytes_dia": 1},
                   headers=operator_token)
    assert r.status_code == 403


def test_relatorio_junta_o_contado_no_rover_e_o_medido_aqui(client, admin_token, demo,
                                                            session) -> None:
    robo = provision(client, admin_token, "ROVER_SCOUT_V1", "RV-DADOS-3", demo["farm_id"])
    r = send_telemetry(robo, health={"dados": DADOS})
    assert r.status_code in (200, 202), r.text
    registros = [_registro(robo, "ev-1", "EVENT_STORM", estado="inicio", taxa_eventos=0.97),
                 _registro(robo, "ev-2", "DATA_BUDGET", nivel=0.8),
                 _registro(robo, "res-1", "NORMAL", kind="result")]
    r = robo.request("POST", "/v1/device/edge/records", json_body={"records": registros})
    assert r.status_code == 200 and len(r.json()["accepted"]) == 3

    rel = client.get(f"/v1/devices/{robo.device_id}/dados", headers=admin_token).json()
    contado = rel["contado_no_rover"]
    assert contado["usado_bytes"] == 1_500_000_000 and contado["tempestade"] is True
    # classe desconhecida e número negativo não passam da padronização
    assert contado["por_classe"] == {"registros": 150_000_000, "arquivos": 1_300_000_000}
    assert rel["fracao_hoje"] == 0.75 and rel["teto"]["origem"] == "rover.json"
    hoje = rel["medido_na_plataforma"][0]
    assert hoje["registros"] == 3 and hoje["eventos"] == 2 and hoje["registros_bytes"] > 0
    assert hoje["telemetria_amostras"] == 1
    assert {a["tipo"] for a in rel["avisos"]} == {"EVENT_STORM", "DATA_BUDGET"}

    linhas = client.get("/v1/dados/consumo", headers=admin_token).json()
    (linha,) = [x for x in linhas if x["device_id"] == robo.device_id]
    assert linha["tempestade"] and linha["retidos"] == 3120 and linha["avisos"] == 2
    assert linha["recebido_periodo_bytes"] == hoje["total_bytes"]


def test_upload_conta_bytes_e_deduplicado_nao(client, admin_token, demo, session) -> None:
    import hashlib

    robo = provision(client, admin_token, "ROVER_SCOUT_V1", "RV-DADOS-4", demo["farm_id"])
    dados = b"\xff\xd8" + b"x" * 5000 + b"\xff\xd9"
    sha = hashlib.sha256(dados).hexdigest()
    for i in (1, 2):  # o segundo é o mesmo arquivo: a plataforma já tem, não pede bytes
        aberto = robo.request("POST", "/v1/device/uploads", json_body={
            "upload_id": f"up-{i}", "sha256": sha, "size_bytes": len(dados),
            "content_type": "image/jpeg", "chunk_size": 8192, "role": "original"})
        assert aberto.status_code in (200, 201), aberto.text
        if aberto.json()["status"] != "complete":
            robo.request("PUT", f"/v1/device/uploads/up-{i}/chunks/0", content=dados,
                         headers={"Content-Type": "application/octet-stream"})
            assert robo.request("POST", f"/v1/device/uploads/up-{i}/complete",
                                json_body={"sha256": sha}).status_code == 200
    rel = client.get(f"/v1/devices/{robo.device_id}/dados", headers=admin_token).json()
    hoje = rel["medido_na_plataforma"][0]
    assert hoje["arquivos"] == 1 and hoje["arquivos_bytes"] == len(dados)
    assert hoje["arquivos_deduplicados"] == 1 and hoje["por_papel"] == {"original": len(dados)}


def test_dock_nao_tem_orcamento(client, admin_token, demo, session) -> None:
    """Só quem tem Starlink própria (Rover, drone) tem teto de dados."""
    dock = provision(client, admin_token, "DOCK_BASE_V1", "DOCK-DADOS-1", demo["farm_id"])
    r = client.put(f"/v1/devices/{dock.device_id}/orcamento-dados", json={"bytes_dia": 1},
                   headers=admin_token)
    assert r.status_code == 422
    assert session.get(Device, dock.device_id).orcamento_dados is None


def test_lote_de_registros_em_gzip(client, admin_token, demo, session) -> None:
    import gzip
    import json

    from valtexa.models import EdgeRecord

    robo = provision(client, admin_token, "ROVER_SCOUT_V1", "RV-DADOS-5", demo["farm_id"])
    lote = {"records": [_registro(robo, f"r-{i}", "NORMAL", kind="result", i=i)
                        for i in range(50)]}
    cru = json.dumps(lote).encode()
    comprimido = gzip.compress(cru, mtime=0)
    assert len(comprimido) < len(cru)
    r = robo.request("POST", "/v1/device/edge/records", content=comprimido,
                     headers={"Content-Type": "application/json", "Content-Encoding": "gzip"})
    assert r.status_code == 200, r.text
    assert len(r.json()["accepted"]) == 50
    assert session.scalar(select(func.count()).select_from(EdgeRecord).where(
        EdgeRecord.device_id == robo.device_id)) == 50

    # gzip quebrado: 400, sem passar da porta
    r = robo.request("POST", "/v1/device/edge/records", content=b"\x1f\x8bnao-e-gzip",
                     headers={"Content-Type": "application/json", "Content-Encoding": "gzip"})
    assert r.status_code == 400
    # bomba: abre para mais que o limite das rotas do dispositivo
    from valtexa.config import settings

    bomba = gzip.compress(b"0" * (settings.max_asset_bytes + 2 * 1024 * 1024))
    r = robo.request("POST", "/v1/device/edge/records", content=bomba,
                     headers={"Content-Type": "application/json", "Content-Encoding": "gzip"})
    assert r.status_code == 400
