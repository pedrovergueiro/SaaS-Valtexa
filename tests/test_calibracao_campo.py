"""A IA contra o agrônomo em produção: acerto, cobertura conformal e calibração."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from tests.helpers import provision, upload_observation
from valtexa.models import Detection, Diagnosis, DiagnosisStatus, PlatformRole
from valtexa.services import calibracao_campo as cc

CLASSES = {"Rust": 0.0, "Cercospora": 0.0, "Healthy": 0.0}


def _det(label: str, confidence: float, conjunto: list[str] | None, prometida=0.9,
         classes=CLASSES) -> SimpleNamespace:
    sinais = {} if conjunto is None else {"prediction_set": conjunto}
    if conjunto is not None and prometida is not None:
        sinais["set_coverage"] = prometida
    return SimpleNamespace(label=label, confidence=confidence, probabilities=dict(classes),
                           signals=sinais, model_key="coffee-foliar", model_version="1")


def test_cobertura_dentro_da_promessa() -> None:
    # 36 de 40 com a verdade no conjunto (90%): o IC contém 0,9.
    casos = [("Rust", _det("Rust", 0.95, ["Rust"]))] * 36 + [
        ("Cercospora", _det("Rust", 0.8, ["Rust"]))] * 4
    b = cc._bloco("coffee-foliar", "1", casos)
    assert b["cobertura"]["k"] == 36 and b["cobertura"]["n"] == 40
    assert b["cobertura"]["prometida"] == 0.9 and b["cobertura"]["estado"] == "dentro"
    assert b["acerto"]["taxa"] == 0.9 and b["fora_do_catalogo"] == 0


def test_cobertura_abaixo_da_promessa_e_detectada() -> None:
    # 20 de 40 (50%) para 90% prometidos: a garantia quebrou no campo.
    casos = [("Rust", _det("Rust", 0.9, ["Rust"]))] * 20 + [
        ("Cercospora", _det("Rust", 0.9, ["Rust"]))] * 20
    b = cc._bloco("coffee-foliar", "1", casos)
    assert b["cobertura"]["estado"] == "abaixo"
    assert b["por_classe"]["Cercospora"]["cobertura"]["taxa"] == 0.0


def test_poucos_casos_nao_concluem() -> None:
    casos = [("Cercospora", _det("Rust", 0.9, ["Rust"]))] * 10
    assert cc._bloco("k", "1", casos)["cobertura"]["estado"] == "poucos_dados"


def test_sem_promessa_gravada_nao_compara() -> None:
    casos = [("Rust", _det("Rust", 0.9, ["Rust"], prometida=None))] * 40
    b = cc._bloco("k", "1", casos)
    assert b["cobertura"]["prometida"] is None and b["cobertura"]["estado"] == "sem_promessa"


def test_classe_fora_do_catalogo_sai_da_cobertura() -> None:
    casos = [("Cigarrinha", _det("Rust", 0.99, ["Rust"]))] * 5 + [
        ("Rust", _det("Rust", 0.99, ["Rust"]))] * 5
    b = cc._bloco("k", "1", casos)
    assert b["fora_do_catalogo"] == 5 and b["cobertura"]["n"] == 5 and b["acerto"]["n"] == 5


def test_calibracao_por_faixa_e_ece() -> None:
    # Confiança 0,95 com metade de acerto: excesso de confiança de 0,45.
    casos = [("Rust", _det("Rust", 0.95, None))] * 10 + [
        ("Healthy", _det("Rust", 0.95, None))] * 10
    b = cc._bloco("k", "1", casos)
    [alta] = [f for f in b["calibracao"]["faixas"] if f["n"]]
    assert (alta["de"], alta["confianca_media"], alta["acerto"]) == (0.9, 0.95, 0.5)
    assert b["calibracao"]["ece"] == 0.45
    assert b["cobertura"]["n"] == 0  # sem conjunto, não há cobertura a medir


def test_wilson() -> None:
    assert cc.wilson(0, 0) is None
    lo, hi = cc.wilson(9, 10)
    assert lo < 0.9 < hi


def test_saude_da_ia_mede_contra_o_agronomo(client: TestClient, admin_token: dict, demo: dict,
                                             equipe, session: Session) -> None:
    rover = provision(client, admin_token, "ROVER_SCOUT_V1", "CAL-1", demo["farm_id"])
    for _ in range(3):
        assert upload_observation(rover, demo["field_id"], label="Rust").status_code in (200, 201)
    ia = equipe(PlatformRole.IA_DADOS)
    antes = client.get("/v1/platform/ai-health", headers=ia).json()
    assert antes["field_calibration"] == [] and "performance_em_producao" in antes["no_data"]

    diagnosticos = session.scalars(select(Diagnosis)).all()
    for i, diag in enumerate(diagnosticos):
        det = session.get(Detection, diag.primary_detection_id)
        det.label, det.confidence = "Rust", 0.9
        det.probabilities = dict(CLASSES)
        det.signals = {**(det.signals or {}), "prediction_set": ["Rust"], "set_coverage": 0.9}
        diag.status = DiagnosisStatus.HUMAN_CONFIRMED
        diag.reviewed_label = "Rust" if i else "Imagem_sem_condicao"  # a foto ruim não conta
        diag.reviewed_at = datetime.now(UTC)
    session.commit()

    depois = client.get("/v1/platform/ai-health", headers=ia).json()
    [bloco] = depois["field_calibration"]
    assert bloco["revisados"] == len(diagnosticos) - 1
    assert bloco["cobertura"]["taxa"] == 1.0 and bloco["cobertura"]["estado"] == "poucos_dados"
    assert "performance_em_producao" not in depois["no_data"]
