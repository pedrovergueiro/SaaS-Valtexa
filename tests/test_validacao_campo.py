"""Validação de campo: o agrônomo anota as plantas do Rover, e o Rover é medido."""

from __future__ import annotations

import pytest

from valtexa.models import (
    Device,
    DeviceKind,
    DeviceModel,
    DeviceStatus,
    Field,
    Mission,
    MissionKind,
    MissionState,
)
from valtexa.services import plant_map

DA_IA = [
    {"plant_id": "L03-P0001", "row_id": "L03", "x_along_m": 1.0, "status": "doente",
     "primary_disease": "Rust", "primary_posterior": 0.97},
    {"plant_id": "L03-P0002", "row_id": "L03", "x_along_m": 2.0, "status": "sadia",
     "primary_disease": "Rust", "primary_posterior": 0.02},
    {"plant_id": "L03-P0003", "row_id": "L03", "x_along_m": 3.0, "status": "suspeita",
     "primary_disease": "Cercospora_Leaf_Spot", "primary_posterior": 0.3},
    {"plant_id": "L03-P0004", "row_id": "L03", "x_along_m": 4.0, "status": "sadia",
     "primary_disease": None, "primary_posterior": 0.01},
    {"plant_id": "L07-P0001", "row_id": "L07", "x_along_m": 1.0, "status": "sadia",
     "primary_disease": None, "primary_posterior": 0.0},
]


@pytest.fixture
def passada(session_factory, demo, monkeypatch) -> tuple[str, str]:
    monkeypatch.setattr(plant_map, "plants", lambda field_id, pass_id=None: DA_IA)
    with session_factory() as s:
        campo = s.get(Field, demo["field_id"])
        campo.validation_rows = [3]
        modelo = s.query(DeviceModel).first()
        robo = Device(tenant_id=demo["tenant_id"], serial_number="RV3-9", name="Rover",
                      kind=DeviceKind.ROVER, device_model_id=modelo.id, farm_id=demo["farm_id"],
                      status=DeviceStatus.ACTIVE)
        s.add(robo)
        s.flush()
        missao = Mission(tenant_id=demo["tenant_id"], kind=MissionKind.SCOUT,
                         state=MissionState.COMPLETED, farm_id=demo["farm_id"],
                         field_id=campo.id, device_id=robo.id)
        s.add(missao)
        s.commit()
        return campo.id, missao.id


def test_anota_mede_e_exporta(client, admin_token, agronomist_token, passada) -> None:
    field_id, mission_id = passada
    url = f"/v1/fields/{field_id}/validacao/{mission_id}"
    lista = client.get(url, headers=admin_token).json()
    assert [p["in_validation_row"] for p in lista["plants"]] == [True] * 4 + [False]

    for planta, rotulo in (("L03-P0001", "Rust"), ("L03-P0002", "Rust"),
                           ("L03-P0003", "sadia"), ("L03-P0004", "Healthy")):
        r = client.put(f"{url}/{planta}", json={"label": rotulo, "incidence_percent": 10},
                       headers=agronomist_token)
        assert r.status_code == 200, r.text
    assert client.put(f"{url}/L03-P0001", json={"label": "Rust, mas pouca"},
                      headers=agronomist_token).status_code == 422  # vírgula quebraria o CSV
    assert client.put(f"{url}/L03-P0001", json={"label": "Rust"},
                      headers=admin_token).status_code == 403  # anotar é do agrônomo

    rel = client.get(f"{url}/relatorio", headers=admin_token).json()
    assert (rel["diseased"], rel["detected"], rel["right_disease"]) == (2, 1, 1)
    assert (rel["healthy"], rel["false_alarms"]) == (2, 1)
    assert rel["missed"] == ["L03-P0002"] and rel["false_alarm_plants"] == ["L03-P0003"]
    assert rel["sensitivity"] == 0.5 and rel["sensitivity_ci95"][0] < 0.5 < rel[
        "sensitivity_ci95"][1]

    csv = client.get(f"/v1/fields/{field_id}/validacao.csv", headers=admin_token).text
    linhas = csv.strip().splitlines()
    assert linhas[0] == "field_id,plant_id,label,pass_id" and len(linhas) == 5
    assert f"{field_id},L03-P0003,Healthy,{mission_id}" in linhas

    assert client.delete(f"{url}/L03-P0004", headers=agronomist_token).status_code == 204
    assert client.get(url, headers=admin_token).json()["labeled"] == 3


def test_missao_de_outro_talhao_e_ia_fora(client, admin_token, passada, monkeypatch) -> None:
    field_id, _ = passada
    assert client.get(f"/v1/fields/{field_id}/validacao/nao-existe",
                      headers=admin_token).status_code == 404

    def fora(*_a, **_k):
        raise plant_map.PlantMapUnavailableError("IA fora do ar")

    monkeypatch.setattr(plant_map, "plants", fora)
    assert client.get(f"/v1/fields/{field_id}/validacao/{passada[1]}",
                      headers=admin_token).status_code == 503


def test_exporta_originais_da_missao(frota, store, tmp_path, monkeypatch) -> None:
    """Os originais saem com o nome que o registro da IA usa (record_id), e só com consentimento."""
    import sys
    from datetime import UTC, datetime
    from pathlib import Path

    from valtexa.models import Asset, AssetKind, EdgeRecord, EdgeUpload
    from valtexa.services import consent

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    import exporta_originais

    s, robo = frota["session"], frota["device"]
    missao = Mission(tenant_id=frota["tenant"].id, kind=MissionKind.SCOUT,
                     state=MissionState.COMPLETED, farm_id=frota["farm"].id,
                     field_id=frota["field"].id, device_id=robo.id)
    s.add(missao)
    s.flush()
    agora = datetime(2026, 10, 7, tzinfo=UTC)
    for rid, com_original in (("r-1", True), ("r-2", False)):
        s.add(EdgeRecord(tenant_id=robo.tenant_id, device_id=robo.id, record_id=rid,
                         kind="result", type="NORMAL", sha256="0" * 64, mission_id=missao.id,
                         occurred_at=agora, received_at=agora, payload={}))
        if com_original:
            obj = store.put(b"jpeg-de-12-mp", "image/jpeg", "edge")
            asset = Asset(tenant_id=robo.tenant_id, kind=AssetKind.IMAGE,
                          content_type="image/jpeg", size_bytes=obj.size_bytes,
                          sha256=obj.sha256, storage_key=obj.key)
            s.add(asset)
            s.flush()
            s.add(EdgeUpload(tenant_id=robo.tenant_id, device_id=robo.id, upload_id="u-1",
                             sha256=obj.sha256, size_bytes=obj.size_bytes,
                             content_type="image/jpeg", chunk_size=1, total_chunks=1,
                             status="complete", record_id=rid, role="original",
                             asset_id=asset.id))
    s.commit()

    monkeypatch.setattr(consent, "permite_treino", lambda *_: False)
    with pytest.raises(SystemExit, match="autorizou"):
        exporta_originais.exporta(s, missao.id, tmp_path / "x")
    monkeypatch.setattr(consent, "permite_treino", lambda *_: True)
    assert exporta_originais.exporta(s, missao.id, tmp_path / "o") == {
        "exportados": 1, "sem_original": 1}
    assert (tmp_path / "o" / "r-1.jpg").read_bytes() == b"jpeg-de-12-mp"
