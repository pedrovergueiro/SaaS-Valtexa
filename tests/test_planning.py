"""Cobertura alinhada às linhas de plantio e configuração do segundo analisador."""

from __future__ import annotations

import math

import pytest
from fastapi.testclient import TestClient
from helpers import provision, send_telemetry

from valtexa.config import Settings
from valtexa.services import ai_pipeline, geo

# ~308 m leste-oeste por ~222 m norte-sul, perto de Itajubá.
CAMPO = [[-45.4530, -22.4120], [-45.4500, -22.4120], [-45.4500, -22.4140], [-45.4530, -22.4140]]


def _bearing(start: list, end: list) -> float:
    """Rumo do segmento, em graus a partir do norte, reduzido a [0, 180)."""
    east = (end[0] - start[0]) * math.cos(math.radians(start[1]))
    north = end[1] - start[1]
    return math.degrees(math.atan2(east, north)) % 180.0


def _angle_gap(a: float, b: float) -> float:
    gap = abs(a - b) % 180.0
    return min(gap, 180.0 - gap)


@pytest.mark.parametrize("azimute", [0.0, 30.0, 45.0, 90.0, 135.0])
def test_passadas_seguem_as_linhas(azimute: float) -> None:
    """O rover anda entre as linhas; atravessá-las passaria por cima das plantas."""
    for leg in geo.boustrophedon(CAMPO, 20.0, azimuth_deg=azimute):
        assert _angle_gap(_bearing(leg[0], leg[1]), azimute) < 0.5


@pytest.mark.parametrize("azimute", [0.0, 45.0, 90.0])
def test_passadas_ficam_dentro_do_talhao(azimute: float) -> None:
    for leg in geo.boustrophedon(CAMPO, 20.0, azimuth_deg=azimute):
        middle = ((leg[0][0] + leg[1][0]) / 2, (leg[0][1] + leg[1][1]) / 2)
        assert geo.contains_point(CAMPO, *middle)


def test_numero_de_passadas_acompanha_a_largura_atravessada() -> None:
    """Linhas leste-oeste atravessam os 222 m norte-sul; norte-sul, os 308 m."""
    assert 10 <= len(geo.boustrophedon(CAMPO, 20.0, azimuth_deg=90.0)) <= 12
    assert 14 <= len(geo.boustrophedon(CAMPO, 20.0, azimuth_deg=0.0)) <= 16


def test_o_padrao_continua_leste_oeste() -> None:
    assert geo.boustrophedon(CAMPO, 20.0) == geo.boustrophedon(CAMPO, 20.0, azimuth_deg=90.0)


def test_a_missao_usa_a_orientacao_do_talhao(
    client: TestClient, demo: dict, admin_token: dict, operator_token: dict
) -> None:
    field_row = client.post(
        f"/v1/farms/{demo['farm_id']}/fields",
        json={"name": "Linhas N-S", "crop": "corn", "boundary": CAMPO, "row_azimuth_deg": 0.0},
        headers=admin_token,
    ).json()
    assert field_row["row_azimuth_deg"] == 0.0

    rover = provision(client, admin_token, "ROVER_SCOUT_V1", "P-ROVER-1", demo["farm_id"])
    send_telemetry(rover, battery_percent=95.0)
    mission = client.post(
        "/v1/missions",
        json={"kind": "scout", "field_id": field_row["id"], "device_id": rover.device_id},
        headers=operator_token,
    ).json()
    assert mission["plan"]["row_azimuth_deg"] == 0.0

    segments = client.get(f"/v1/missions/{mission['id']}/segments", headers=operator_token).json()
    for segment in segments:
        assert _angle_gap(_bearing(segment["path"][0], segment["path"][1]), 0.0) < 0.5


class TestSecondaryAnalyzer:
    def test_sem_modelo_para_a_cultura_se_declara_ausente(self) -> None:
        """Nunca cai no modelo primário: seria uma segunda opinião dada pelo mesmo."""
        analyzer = ai_pipeline.HttpModelAnalyzer(
            name="cloud-secondary",
            crop_models={"corn": "leaf-foliar-b"},
            base_url="http://127.0.0.1:9",
        )
        result = analyzer.analyze(b"x", "x.jpg", "coffee")
        assert not result.usable
        assert "secundário" in result.error

    def test_configuracao_monta_o_par(self, monkeypatch: pytest.MonkeyPatch) -> None:
        base = {"simulated_inference": False, "inference_enabled": True}
        monkeypatch.setattr(
            ai_pipeline, "settings", Settings(**base, secondary_models="corn:leaf-foliar-b")
        )
        names = [analyzer.name for analyzer in ai_pipeline.default_analyzers()]
        assert names == ["cloud-primary", "dependent:cloud-secondary"]

        monkeypatch.setattr(
            ai_pipeline,
            "settings",
            Settings(
                **base, secondary_models="corn:leaf-foliar-b", secondary_model_independent=True
            ),
        )
        names = [analyzer.name for analyzer in ai_pipeline.default_analyzers()]
        assert names == ["cloud-primary", "cloud-secondary"]

    def test_sem_segundo_modelo_fica_um_analisador(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            ai_pipeline, "settings", Settings(simulated_inference=False, inference_enabled=True)
        )
        assert [a.name for a in ai_pipeline.default_analyzers()] == ["cloud-primary"]

    def test_mapa_de_culturas_ignora_lixo(self) -> None:
        settings = Settings(secondary_models="corn:a, Cafe:b, sem-dois-pontos, :c")
        mapping = settings.secondary_model_map
        assert mapping == {"corn": "a", "cafe": "b"}

    def test_par_dependente_nao_valida(self) -> None:
        """Concordância com o modelo marcado como dependente não vira AI_VALIDATED."""
        outcome = ai_pipeline.combine(
            [
                ai_pipeline.Analysis(analyzer="cloud-primary", label="Blight", confidence=0.95),
                ai_pipeline.Analysis(
                    analyzer="dependent:cloud-secondary", label="Blight", confidence=0.94
                ),
            ]
        )
        assert not outcome.independent_pair
        assert outcome.status is ai_pipeline.DiagnosisStatus.NEEDS_REVIEW


class TestSeveridade:
    """Área lesionada: medida, não opinião — não passa pelo combinador."""

    def test_vem_do_primeiro_analisador_que_mediu(self) -> None:
        analyses = [
            ai_pipeline.Analysis(analyzer="a", label="Blight", confidence=0.9),
            ai_pipeline.Analysis(analyzer="b", label="Blight", confidence=0.9, severity=0.18),
            ai_pipeline.Analysis(analyzer="c", label="Blight", confidence=0.9, severity=0.2),
        ]
        assert ai_pipeline.measured_severity(analyses) == pytest.approx(0.18)

    def test_analisador_com_erro_nao_conta(self) -> None:
        failed = ai_pipeline.Analysis(
            analyzer="a", label=None, confidence=None, severity=0.5, error="Timeout"
        )
        assert ai_pipeline.measured_severity([failed]) is None

    def test_simulado_mede_zero_em_folha_sadia(self) -> None:
        image = b"folha" + ai_pipeline.SIMULATION_MARKER + b"Healthy:0.4"
        analysis = ai_pipeline.SimulatedAnalyzer(name="sim-a").analyze(image, "f.png", "corn")
        assert analysis.severity == 0.0

    def test_simulados_respondem_a_mesma_severidade(self) -> None:
        """É medida da imagem: dois analisadores não podem discordar dela."""
        image = b"folha" + ai_pipeline.SIMULATION_MARKER + b"Common_Rust:0.4"
        first = ai_pipeline.SimulatedAnalyzer(name="sim-a").analyze(image, "f.png", "corn")
        second = ai_pipeline.SimulatedAnalyzer(name="sim-b", bias=-0.02).analyze(
            image, "f.png", "corn"
        )
        assert first.severity == second.severity
        assert 0.03 <= first.severity <= 0.35
