"""Cópia 3D: a passada do rover por uma rua e a cópia do talhão composta delas.

O que precisa valer:

* a nuvem de pontos fora do contrato é recusada com o motivo, não aceita torta;
* cada rua percorrida entra na cópia, e reenviar a mesma passada não duplica;
* a passada mais nova substitui a faixa que cobriu — inclusive a planta que
  sumiu —, e o "estado em" devolve a cópia como ela era;
* a foto diagnosticada fica presa à planta fotografada, com a categoria que
  vale: a praga que o modelo não conhece aparece como praga depois que o
  agrônomo a rotula.
"""

from __future__ import annotations

import json
import math
from collections import Counter
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from helpers import DeviceSession, provision, send_telemetry, upload_observation

from simulator.plants import Focus, SimulatedCrop
from valtexa.models import DiagnosisStatus
from valtexa.seed import DEMO_FIELD_BOUNDARY
from valtexa.services import pointcloud
from valtexa.services.taxonomy import Category, categorize

EIXO = [[-45.4525, -22.4129], [-45.4512, -22.4129]]
"""Uma rua leste-oeste de ~134 m, no meio do talhão de demonstração."""

VIZINHA = [[lon, lat + 3.0 / 111_320] for lon, lat in EIXO]
"""A rua 3 m ao norte."""

ZONA = [
    [-45.4525, -22.4124],
    [-45.4512, -22.4124],
    [-45.4512, -22.4133],
    [-45.4525, -22.4133],
]


def _lonlat(origin: list[float], x: float, y: float) -> tuple[float, float]:
    """Metros a partir da origem da passada, de volta para graus."""
    return (
        origin[0] + x / (111_320 * math.cos(math.radians(origin[1]))),
        origin[1] + y / 111_320,
    )


def _enviar(
    device: DeviceSession,
    field_id: str,
    plants: list[list[float]],
    *,
    cloud: bytes | None = None,
    path: list[list[float]] = EIXO,
    captured_at: datetime | None = None,
    sequence: int | None = None,
):
    metadata = {
        "sequence_number": sequence if sequence is not None else device.next_sequence(),
        "field_id": field_id,
        "captured_at": (captured_at or datetime.now(UTC)).isoformat(),
        "origin_lon": path[0][0],
        "origin_lat": path[0][1],
        "path": path,
        "reach_m": 1.5,
        "plants": plants,
    }
    kwargs: dict = {"data": {"metadata": json.dumps(metadata)}}
    if cloud is not None:
        kwargs["files"] = {"file": ("rua.ply", cloud, "application/x-ply")}
    return device.request("POST", "/v1/device/row-scans", **kwargs)


def _cena(client: TestClient, field_id: str, headers: dict, **params) -> dict:
    response = client.get(f"/v1/fields/{field_id}/scene", params=params, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


NUVEM = pointcloud.encode(
    [(0.0, 0.0, 0.0, 110, 86, 62), (1.0, 0.25, 1.3, 56, 128, 44), (2.0, -0.25, 0.9, 60, 120, 40)]
)


# --- o arquivo ----------------------------------------------------------------


class TestNuvemDePontos:
    def test_ida_e_volta(self) -> None:
        info = pointcloud.inspect(NUVEM)
        assert info.points == 3
        assert info.minimum == pytest.approx((0.0, -0.25, 0.0))
        assert info.maximum == pytest.approx((2.0, 0.25, 1.3))

    @pytest.mark.parametrize(
        ("data", "motivo"),
        [
            (b"isto nao e ply", "Não é um PLY"),
            (NUVEM.replace(b"binary_little_endian", b"ascii", 1), "Formato"),
            (
                NUVEM.replace(
                    b"property float x\nproperty float y", b"property float y\nproperty float x"
                ),
                "nesta ordem",
            ),
            (NUVEM[:-4], "Corpo com"),
            (pointcloud.encode([(math.nan, 0.0, 0.0, 0, 0, 0)]), "Coordenada"),
            (pointcloud.encode([(50_000.0, 0.0, 0.0, 0, 0, 0)]), "Coordenada"),
            (pointcloud.encode([]), "vazia"),
        ],
    )
    def test_recusa_o_que_foge_do_contrato(self, data: bytes, motivo: str) -> None:
        with pytest.raises(pointcloud.PointCloudError, match=motivo):
            pointcloud.inspect(data)

    def test_teto_de_pontos(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(pointcloud, "MAX_POINTS", 2)
        with pytest.raises(pointcloud.PointCloudError, match="grade de voxels"):
            pointcloud.inspect(NUVEM)


# --- a passada ------------------------------------------------------------------


class TestPassada:
    def test_rua_percorrida_entra_na_copia(
        self, client: TestClient, demo: dict, admin_token: dict, operator_token: dict
    ) -> None:
        rover = provision(client, admin_token, "ROVER_SCOUT_V1", "R3D-1", demo["farm_id"])
        plants = [[1.0, 0.25, 1.3, 0.6, 0.8], [1.3, 0.25, 1.2, 0.6, 0.75], [1.0, -0.25, 1.4, 0.6]]

        response = _enviar(rover, demo["field_id"], plants, cloud=NUVEM)
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["plant_count"] == 3
        assert body["point_count"] == 3
        assert body["has_pointcloud"] is True
        assert body["length_m"] == pytest.approx(134, abs=2)

        cena = _cena(client, demo["field_id"], operator_token)
        assert len(cena["scans"]) == 1
        assert len(cena["plants"]["x"]) == 3
        assert cena["plants"]["greenness"][2] is None
        assert 0 < cena["coverage_ratio"] < 0.2
        assert cena["scans"][0]["visible_plants"] == 3

        # A nuvem volta byte a byte, pelo escopo do cliente.
        nuvem = client.get(f"/v1/row-scans/{body['id']}/pointcloud", headers=operator_token)
        assert nuvem.status_code == 200
        assert nuvem.content == NUVEM

    def test_reenvio_da_mesma_passada_nao_duplica(
        self, client: TestClient, demo: dict, admin_token: dict, operator_token: dict
    ) -> None:
        rover = provision(client, admin_token, "ROVER_SCOUT_V1", "R3D-2", demo["farm_id"])
        plants = [[1.0, 0.25, 1.3, 0.6, 0.8]]
        first = _enviar(rover, demo["field_id"], plants, sequence=40)
        again = _enviar(rover, demo["field_id"], plants, sequence=40)
        assert first.status_code == again.status_code == 201
        assert first.json()["id"] == again.json()["id"]
        assert len(_cena(client, demo["field_id"], operator_token)["scans"]) == 1

    def test_passada_nova_substitui_a_faixa_e_o_estado_em_volta_no_tempo(
        self, client: TestClient, demo: dict, admin_token: dict, operator_token: dict
    ) -> None:
        rover = provision(client, admin_token, "ROVER_SCOUT_V1", "R3D-3", demo["farm_id"])
        antes = datetime.now(UTC) - timedelta(days=2)
        _enviar(
            rover,
            demo["field_id"],
            [[1.0, 0.25, 1.1, 0.5, 0.8], [1.3, 0.25, 1.1, 0.5, 0.8], [1.6, 0.25, 1.1, 0.5, 0.8]],
            captured_at=antes,
        )
        # A planta do meio sumiu. As outras cresceram.
        _enviar(rover, demo["field_id"], [[1.0, 0.25, 1.4, 0.6, 0.8], [1.6, 0.25, 1.4, 0.6, 0.8]])

        agora = _cena(client, demo["field_id"], operator_token)
        assert len(agora["plants"]["x"]) == 2
        assert agora["plants"]["height"] == [1.4, 1.4]
        assert [scan["visible_plants"] for scan in agora["scans"]] == [2, 0]
        assert [day["scans"] for day in agora["passes"]] == [1, 1]

        ontem = (datetime.now(UTC) - timedelta(days=1)).isoformat()
        passado = _cena(client, demo["field_id"], operator_token, at=ontem)
        assert len(passado["plants"]["x"]) == 3
        assert passado["live"] is False
        assert passado["devices"] == []

    def test_ruas_vizinhas_se_somam(
        self, client: TestClient, demo: dict, admin_token: dict, operator_token: dict
    ) -> None:
        rover = provision(client, admin_token, "ROVER_SCOUT_V1", "R3D-4", demo["farm_id"])
        _enviar(rover, demo["field_id"], [[5.0, 0.25, 1.3, 0.6, 0.8]])
        uma = _cena(client, demo["field_id"], operator_token)
        _enviar(rover, demo["field_id"], [[5.0, 0.25, 1.3, 0.6, 0.8]], path=VIZINHA)
        duas = _cena(client, demo["field_id"], operator_token)

        assert len(duas["plants"]["x"]) == 2
        assert duas["scanned_area_m2"] == pytest.approx(2 * uma["scanned_area_m2"], rel=0.05)

    def test_foto_fica_presa_a_planta_e_a_praga_aparece_depois_do_agronomo(
        self,
        client: TestClient,
        demo: dict,
        admin_token: dict,
        operator_token: dict,
        agronomist_token: dict,
    ) -> None:
        rover = provision(client, admin_token, "ROVER_SCOUT_V1", "R3D-5", demo["farm_id"])
        _enviar(
            rover,
            demo["field_id"],
            [[10.0, 0.25, 1.35, 0.6, 0.8], [40.0, -0.25, 1.05, 0.5, 0.52]],
        )

        lon, lat = _lonlat(EIXO[0], 10.0, 0.25)
        ferrugem = upload_observation(
            rover, demo["field_id"], label="Common_Rust", novelty=0.3, lon=lon, lat=lat
        ).json()
        lon, lat = _lonlat(EIXO[0], 40.0, -0.25)
        lagarta = upload_observation(
            rover, demo["field_id"], label="Blight", novelty=1.6, lon=lon, lat=lat
        ).json()
        assert lagarta["diagnosis_status"] == "needs_review"

        cena = _cena(client, demo["field_id"], operator_token)
        marcadores = {item["observation_id"]: item for item in cena["markers"]}
        rust = marcadores[ferrugem["id"]]
        assert rust["plant"] is not None
        assert rust["z"] == 1.35
        assert rust["scan"] == 0
        esperado = "disease" if ferrugem["diagnosis_status"] == "ai_validated" else "review"
        assert rust["category"] == esperado
        assert marcadores[lagarta["id"]]["category"] == "review"
        assert cena["scans"][0]["markers"] == dict(Counter([esperado, "review"]))

        revisao = client.post(
            f"/v1/diagnoses/{lagarta['diagnosis_id']}/review",
            json={"label": "Spodoptera_frugiperda", "confirmed": True},
            headers=agronomist_token,
        )
        assert revisao.status_code == 200, revisao.text

        cena = _cena(client, demo["field_id"], operator_token)
        praga = next(item for item in cena["markers"] if item["observation_id"] == lagarta["id"])
        assert praga["category"] == "pest"
        assert praga["label"] == "Spodoptera_frugiperda"
        assert praga["z"] == 1.05
        assert cena["counts"]["pest"] == 1

    def test_varredura_em_andamento_mostra_as_ruas_que_faltam(
        self, client: TestClient, demo: dict, admin_token: dict, operator_token: dict
    ) -> None:
        rover = provision(client, admin_token, "ROVER_SCOUT_V1", "R3D-6", demo["farm_id"])
        send_telemetry(rover, battery_percent=95.0, lat=-22.4140, lon=-45.4515)
        mission = client.post(
            "/v1/missions",
            json={
                "kind": "scout",
                "field_id": demo["field_id"],
                "device_id": rover.device_id,
                "zone_id": demo["zone_id"],
                "target_polygon": ZONA,
                "plan": {"swath_m": 25.0},
            },
            headers=operator_token,
        )
        assert mission.status_code == 201, mission.text
        mission_id = mission.json()["id"]
        authorized = client.post(f"/v1/missions/{mission_id}/authorize", headers=operator_token)
        assert authorized.json()["verdict"] == "safe_to_execute", authorized.text
        assert (
            client.post(f"/v1/missions/{mission_id}/dispatch", headers=operator_token).status_code
            == 200
        )

        cena = _cena(client, demo["field_id"], operator_token)
        [andamento] = cena["missions"]
        assert andamento["segments"] == mission.json()["plan"]["segments"]
        assert andamento["done"] == 0
        assert len(andamento["pending"]) == andamento["segments"]
        assert [device["id"] for device in cena["devices"]] == [rover.device_id]


class TestRecusas:
    def test_passada_fora_do_talhao(
        self, client: TestClient, demo: dict, admin_token: dict
    ) -> None:
        rover = provision(client, admin_token, "ROVER_SCOUT_V1", "R3D-7", demo["farm_id"])
        longe = [[-45.40, -22.40], [-45.39, -22.40]]
        response = _enviar(rover, demo["field_id"], [[1.0, 0.0, 1.0, 0.5]], path=longe)
        assert response.status_code == 422
        assert "não cruza o talhão" in response.text

    def test_passada_vazia(self, client: TestClient, demo: dict, admin_token: dict) -> None:
        rover = provision(client, admin_token, "ROVER_SCOUT_V1", "R3D-8", demo["farm_id"])
        response = _enviar(rover, demo["field_id"], [])
        assert response.status_code == 422

    def test_nuvem_invalida(self, client: TestClient, demo: dict, admin_token: dict) -> None:
        rover = provision(client, admin_token, "ROVER_SCOUT_V1", "R3D-9", demo["farm_id"])
        response = _enviar(rover, demo["field_id"], [], cloud=b"lixo")
        assert response.status_code == 422
        assert "Nuvem de pontos recusada" in response.text

    @pytest.mark.parametrize(
        "planta",
        [
            [1.0, 0.0, 12.0, 0.5],
            [1.0, 0.0, 1.0],
            [1.0, 0.0, 1.0, 0.5, 1.7],
            [9_000.0, 0.0, 1.0, 0.5],
        ],
    )
    def test_planta_implausivel(
        self, client: TestClient, demo: dict, admin_token: dict, planta: list[float]
    ) -> None:
        rover = provision(client, admin_token, "ROVER_SCOUT_V1", "R3D-10", demo["farm_id"])
        assert _enviar(rover, demo["field_id"], [planta]).status_code == 422

    def test_passada_sem_nuvem_nao_tem_arquivo(
        self, client: TestClient, demo: dict, admin_token: dict, operator_token: dict
    ) -> None:
        rover = provision(client, admin_token, "ROVER_SCOUT_V1", "R3D-11", demo["farm_id"])
        scan = _enviar(rover, demo["field_id"], [[1.0, 0.25, 1.3, 0.6]]).json()
        assert scan["has_pointcloud"] is False
        response = client.get(f"/v1/row-scans/{scan['id']}/pointcloud", headers=operator_token)
        assert response.status_code == 404

    def test_talhao_sem_passada_tem_copia_vazia(
        self, client: TestClient, demo: dict, operator_token: dict
    ) -> None:
        cena = _cena(client, demo["field_id"], operator_token)
        assert cena["scans"] == []
        assert cena["plants"]["x"] == []
        assert cena["coverage_ratio"] == 0.0
        assert len(cena["boundary"]) == 4


# --- categorias ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("label", "status", "categoria"),
    [
        ("Healthy", DiagnosisStatus.AI_VALIDATED, Category.HEALTHY),
        ("Common_Rust", DiagnosisStatus.AI_VALIDATED, Category.DISEASE),
        ("Common_Rust", DiagnosisStatus.NEEDS_REVIEW, Category.REVIEW),
        ("Spodoptera_frugiperda", DiagnosisStatus.HUMAN_CONFIRMED, Category.PEST),
        ("Leaf_Miner_Damage", DiagnosisStatus.AI_VALIDATED, Category.PEST),
        ("Deficiência de magnésio", DiagnosisStatus.HUMAN_CONFIRMED, Category.OTHER),
        (None, None, Category.REVIEW),
    ],
)
def test_categoria(label: str | None, status: DiagnosisStatus | None, categoria: Category) -> None:
    assert categorize(label, status) is categoria


# --- a lavoura simulada ---------------------------------------------------------


class TestLavouraSimulada:
    def test_a_mesma_rua_ve_as_mesmas_plantas(self) -> None:
        crop = SimulatedCrop(boundary=DEMO_FIELD_BOUNDARY)
        plants, cloud = crop.scan(EIXO, 1.5)
        again, _ = crop.scan(EIXO, 1.5)
        assert plants == again
        # 134 m, seis linhas a 0,5 m, uma planta a cada 0,3 m, ~4% de falha.
        assert 2_300 < len(plants) < 2_900
        assert pointcloud.inspect(cloud).points > 20 * len(plants)

    def test_ruas_vizinhas_nao_repetem_planta(self) -> None:
        crop = SimulatedCrop(boundary=DEMO_FIELD_BOUNDARY)
        a = {(round(x, 2), round(y, 2)) for x, y, *_ in crop.plants_along(EIXO, 1.5)}
        b = {(round(x, 2), round(y, 2)) for x, y, *_ in crop.plants_along(VIZINHA, 1.5)}
        assert a and b
        assert not a & b

    def test_reboleira_deixa_a_planta_mais_baixa_e_menos_verde(self) -> None:
        centro = _lonlat(EIXO[0], 60.0, 0.0)
        crop = SimulatedCrop(
            boundary=DEMO_FIELD_BOUNDARY,
            foci=[
                Focus(
                    lon=centro[0],
                    lat=centro[1],
                    radius_m=10.0,
                    drawn="Common_Rust",
                    model_label="Common_Rust",
                    stunting=0.3,
                    yellowing=0.4,
                )
            ],
        )
        plants = crop.plants_along(EIXO, 1.5)
        dentro = [p for p in plants if p[5] > 0.6]
        fora = [p for p in plants if p[5] == 0]
        assert dentro and fora

        def media(rows: list, index: int) -> float:
            return sum(row[index] for row in rows) / len(rows)

        assert media(dentro, 2) < 0.85 * media(fora, 2)
        assert media(dentro, 4) < media(fora, 4) - 0.2
