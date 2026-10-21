"""Resultados do Rover → fusão por planta da IA (``services.fusao_borda``)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from valtexa.models import (
    Device,
    EdgeRecord,
    Field,
    Mission,
    MissionKind,
    MissionState,
)
from valtexa.services import fusao_borda, geo, plant_map

LON0, LAT0 = -47.0, -22.9
LABELS = ["Healthy", "Sigatoka"]
AGORA = datetime(2026, 10, 7, 12, 0, tzinfo=UTC)


def _graus(e: float, n: float) -> list[float]:
    return list(geo.from_local((e, n), LON0, LAT0))


def talhao(**extra) -> Field:
    """100 m x 100 m, linhas norte-sul a cada 4 m; a primeira a 2 m da borda oeste."""
    cantos = [_graus(-50, -50), _graus(50, -50), _graus(50, 50), _graus(-50, 50)]
    return Field(name="T", crop="banana", boundary=cantos, row_azimuth_deg=0.0,
                 row_spacing_m=4.0, **extra)


def corpo(lado: str | None = "left", rumo: float | None = 0.0, nav: dict | None = None,
          e: float = -46.0, n: float = 10.0) -> dict:
    lon, lat = _graus(e, n)
    return {
        "frame": {"camera_id": "esq-1000", "width": 1600, "height": 1200},
        "position": {"lat": lat, "lon": lon, "heading_deg": rumo},
        "navigation": nav,
        "tiles": {"tile_mm": 150.0, "distance_mm": 270.0, "hfov_deg": 127.0,
                  "camera_height_mm": 1000.0, "side": lado, "labels": LABELS,
                  "boxes": [[0, 0, 220, 220], [600, 0, 820, 220]],
                  "heights_mm": [1100.0, 1100.0], "zones": [["folhas_baixas"], []],
                  "probabilities": [[0.9, 0.1], [0.2, 0.8]]},
    }


class TestGeometria:
    def test_navegacao_vence(self) -> None:
        g = fusao_borda.geometria(talhao(), corpo(nav={"row_left": "L07", "x_m": 33.5}))
        assert g == {"row_id": "L07", "side": "left", "x_m": 33.5, "fonte": "navegacao"}

    def test_gnss_a_favor_do_azimute(self) -> None:
        esq = fusao_borda.geometria(talhao(), corpo("left", 0.0))
        dir_ = fusao_borda.geometria(talhao(), corpo("right", 0.0))
        assert (esq["row_id"], esq["side"]) == ("G1", "left")  # oeste do Rover na rua 1-2
        assert (dir_["row_id"], dir_["side"]) == ("G2", "right")
        assert esq["x_m"] == pytest.approx(10.0, abs=0.01) and esq["fonte"] == "gnss"

    def test_gnss_contra_o_azimute_troca_o_lado(self) -> None:
        esq = fusao_borda.geometria(talhao(), corpo("left", 180.0))
        assert (esq["row_id"], esq["side"]) == ("G2", "right")  # a esquerda agora é o leste
        dir_ = fusao_borda.geometria(talhao(), corpo("right", 181.0))
        assert (dir_["row_id"], dir_["side"]) == ("G1", "left")
        assert esq["x_m"] == pytest.approx(10.0, abs=0.01)  # mesmo eixo nas duas passadas

    def test_mesma_planta_nas_duas_direcoes_cai_na_mesma_linha(self) -> None:
        ida = fusao_borda.geometria(talhao(), corpo("left", 0.0, e=-42.0))  # rua 2-3
        volta = fusao_borda.geometria(talhao(), corpo("right", 180.0, e=-42.0))
        assert ida["row_id"] == volta["row_id"] == "G2"

    @pytest.mark.parametrize(("campo", "motivo"), [
        ({"lado": None}, "lado"),
        ({"rumo": None}, "rumo"),
    ])
    def test_sem_geometria_explica(self, campo, motivo) -> None:
        with pytest.raises(fusao_borda.SemGeometriaError, match=motivo):
            fusao_borda.geometria(talhao(), corpo(**campo))

    def test_talhao_sem_azimute(self) -> None:
        sem = talhao()
        sem.row_azimuth_deg = None
        with pytest.raises(fusao_borda.SemGeometriaError, match="azimute"):
            fusao_borda.geometria(sem, corpo())


def test_quadro_no_formato_da_ia() -> None:
    registro = EdgeRecord(record_id="r-1", mission_id="m-1", occurred_at=AGORA,
                          payload=corpo(nav={"row_left": "L03", "x_m": 12.5}))
    q = fusao_borda.quadro(talhao(), registro)
    assert q["frame_id"] == "r-1" and q["pass_id"] == "m-1" and q["row_id"] == "L03"
    assert q["image_width_px"] == 1600 and q["hfov_deg"] == 127.0
    assert q["tiles"][1]["predicted_class"] == "Sigatoka"
    assert q["tiles"][1]["probabilities"] == {"Healthy": 0.2, "Sigatoka": 0.8}
    assert q["tiles"][0]["zones"] == ["folhas_baixas"]
    assert q["plant_spacing_m"] is None  # sem espaçamento no cadastro: o padrão da cultura
    cafezal = talhao(plant_spacing_m=0.6)
    assert fusao_borda.quadro(cafezal, registro)["plant_spacing_m"] == 0.6

    so_top = corpo()
    del so_top["tiles"]["probabilities"]
    with pytest.raises(ValueError, match="probabilidades"):
        fusao_borda.quadro(talhao(), EdgeRecord(record_id="r", mission_id="m",
                                                occurred_at=AGORA, payload=so_top))


def test_geometria_3d_do_recorte_vai_e_o_conformal_nao() -> None:
    """Nível 2, 5.3: a lesão no referencial da planta precisa do ponto 3D de cada recorte. O
    conjunto conformal da borda fica: a fusão da borda foi calibrada sem ele."""
    payload = corpo(nav={"row_left": "L03", "x_m": 12.5})
    g = {"centro_mm": [10.0, 200.0, 320.0], "inclinacao_graus": 25.0, "face": "indeterminada"}
    payload["tiles"]["geometria"] = [g, None]
    payload["tiles"]["conformal_sets"] = [["Healthy", "Sigatoka"], ["Sigatoka"]]
    registro = EdgeRecord(record_id="r-1", mission_id="m-1", occurred_at=AGORA, payload=payload)
    q = fusao_borda.quadro(talhao(), registro)
    assert q["tiles"][0]["geometria"] == g and "geometria" not in q["tiles"][1]
    assert all("prediction_set" not in t for t in q["tiles"])
    payload["tiles"]["geometria"] = [g]  # tamanho errado: ignorada, o quadro segue
    assert all("geometria" not in t for t in fusao_borda.quadro(talhao(), registro)["tiles"])


# ---------------------------------------------------------------------------
# Worker
# ---------------------------------------------------------------------------


@pytest.fixture
def missao(frota) -> Mission:
    session, campo = frota["session"], frota["field"]
    campo.row_azimuth_deg, campo.row_spacing_m = 0.0, 4.0
    m = Mission(tenant_id=frota["tenant"].id, kind=MissionKind.SCOUT,
                state=MissionState.RUNNING, farm_id=frota["farm"].id, field_id=campo.id,
                device_id=frota["device"].id)
    session.add(m)
    session.commit()
    return m


def _resultado(session: Session, m: Mission, rid: str, **extra) -> EdgeRecord:
    r = EdgeRecord(tenant_id=m.tenant_id, device_id=m.device_id, record_id=rid, kind="result",
                   type="NORMAL", sha256="0" * 64, mission_id=m.id, field_id=m.field_id,
                   occurred_at=AGORA, received_at=AGORA, model_key="banana-foliar",
                   payload=corpo(nav={"row_left": "L03", "x_m": 12.5}), **extra)
    session.add(r)
    session.commit()
    return r


def test_varrer_manda_marca_e_para_quando_a_ia_cai(session, missao, monkeypatch) -> None:
    for i in range(4):
        _resultado(session, missao, f"r-{i}")
    sem_lado = _resultado(session, missao, "r-sem-lado")
    sem_lado.payload = {**sem_lado.payload, "tiles": {**sem_lado.payload["tiles"], "side": None}}
    session.commit()
    enviados, respostas = [], iter([
        {"duplicated": False, "plants": ["L03-P0001"], "calibration": "cal-1"},
        {"duplicated": True, "plants": [], "calibration": None},
        plant_map.PlantMapRefusedError("passada 'm' já foi fechada"),
        plant_map.PlantMapUnavailableError("fora do ar"),
    ])

    def ingerir(field_id, model_key, frame):
        enviados.append(frame["frame_id"])
        r = next(respostas)
        if isinstance(r, Exception):
            raise r
        return r

    monkeypatch.setattr(plant_map, "ingest_edge_frame", ingerir)
    assert fusao_borda.varrer(session, agora=AGORA) == 3
    estado = {r.record_id: (r.fusion_status, r.fusion_detail) for r in session.scalars(
        select(EdgeRecord).where(EdgeRecord.mission_id == missao.id))}
    assert estado["r-0"] == ("ok", "cal-1") and estado["r-1"] == ("duplicado", None)
    assert estado["r-2"][0] == "recusado" and "fechada" in estado["r-2"][1]
    assert estado["r-3"] == (None, None)  # IA fora do ar: fica para o próximo ciclo
    assert enviados == ["r-0", "r-1", "r-2", "r-3"]
    assert fusao_borda.resumo(session, missao.id) == {"ok": 1, "duplicado": 1, "recusado": 1,
                                                      "pendente": 2}

    monkeypatch.setattr(plant_map, "ingest_edge_frame",
                        lambda *a: {"duplicated": False, "plants": [], "calibration": None})
    assert fusao_borda.varrer(session, agora=AGORA) == 2
    session.refresh(sem_lado)
    assert sem_lado.fusion_status == "sem_geometria" and "lado" in sem_lado.fusion_detail


def test_passada_fecha_quando_todos_chegaram(session, missao, monkeypatch) -> None:
    fechadas = []

    def pedir(metodo, caminho, *a, **k):
        fechadas.append(caminho)
        return {"plants": [], "changes": []}

    monkeypatch.setattr(plant_map, "_request", pedir)
    _resultado(session, missao, "r-0", fusion_status="ok")
    _resultado(session, missao, "r-1")  # pendente
    missao.state = MissionState.COMPLETED
    session.add(EdgeRecord(tenant_id=missao.tenant_id, device_id=missao.device_id,
                           record_id="ev-1", kind="event", type="MISSION_COMPLETED",
                           sha256="1" * 64, mission_id=missao.id, occurred_at=AGORA,
                           received_at=AGORA, payload={"payload": {"frames_done": 3}}))
    session.commit()
    assert fusao_borda.fechar_passadas(session, agora=AGORA) == 0  # um pendente

    session.scalars(select(EdgeRecord).where(EdgeRecord.record_id == "r-1")).one() \
        .fusion_status = "ok"
    session.commit()
    assert fusao_borda.fechar_passadas(session, agora=AGORA) == 0  # 2 de 3 quadros
    # Sem o terceiro, fecha depois do silêncio.
    tarde = AGORA + fusao_borda.FECHA_SEM_EVENTO + timedelta(minutes=1)
    assert fusao_borda.fechar_passadas(session, agora=tarde) == 1
    assert fechadas == [f"/fields/{missao.field_id}/passes/{missao.id}/close"]
    session.refresh(missao)
    assert missao.fusion_closed_at is not None
    assert fusao_borda.fechar_passadas(session, agora=tarde) == 0  # uma vez só


def test_conclusao_do_runtime_nao_fecha_na_hora(session, missao) -> None:
    robo = session.get(Device, missao.device_id)
    robo.runtime_version = None
    session.commit()
    assert not fusao_borda.fecha_pelo_worker(session, missao)
    robo.runtime_version = "0.1.0"
    session.commit()
    assert fusao_borda.fecha_pelo_worker(session, missao)


# ---------------------------------------------------------------------------
# Rotas: incidência e prescrição por planta
# ---------------------------------------------------------------------------


def test_prescricao_por_planta_pela_plataforma(client, admin_token, demo, session_factory,
                                               monkeypatch) -> None:
    from valtexa.models import Plan, Tenant
    from valtexa.services import plans

    pedidos = []

    def prescrever(field_id, pedido, formato="json"):
        pedidos.append((field_id, pedido, formato))
        if pedido.get("doenca") == "proibida":
            raise plant_map.PlantMapRefusedError("carência maior que os dias até a colheita")
        return {"tratar": ["L03-P0001"], "resumo": "trata 1 planta"}

    monkeypatch.setattr(plant_map, "prescription", prescrever)
    monkeypatch.setattr(plant_map, "incidence", lambda f, p=None: {"incidence": 0.1})
    url = f"/v1/fields/{demo['field_id']}/plants"
    pedido = {"doenca": "Sigatoka", "produto": {}, "economia": {"perda_por_planta": 30}}

    r = client.post(f"{url}/prescription", json=pedido, headers=admin_token)
    assert r.status_code == 200, r.text
    assert r.json()["tratar"] == ["L03-P0001"] and pedidos[0][0] == demo["field_id"]
    assert client.get(f"{url}/incidence", headers=admin_token).json() == {"incidence": 0.1}

    r = client.post(f"{url}/prescription", json={**pedido, "doenca": "proibida"},
                    headers=admin_token)
    assert r.status_code == 422 and "carência" in r.json()["detail"]

    with session_factory() as s:  # plano sem o recurso: 402
        plano = s.scalars(select(Plan).where(Plan.code == "essencial")).one()
        plans.assinar(s, s.get(Tenant, demo["tenant_id"]), plano, actor=None)
        s.commit()
    r = client.post(f"{url}/prescription", json=pedido, headers=admin_token)
    assert r.status_code == 402
    assert client.post("/v1/fields/outro/plants/prescription", json=pedido,
                       headers=admin_token).status_code == 404
