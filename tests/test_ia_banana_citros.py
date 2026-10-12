"""Banana e citros no SaaS: versões do modelo, portão, conformal e o quadro do rover."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from tests.helpers import provision
from tests.test_planning import CAMPO
from valtexa.config import Settings
from valtexa.models import CapturePlatform, DiagnosisStatus
from valtexa.services import ai_pipeline
from valtexa.services.taxonomy import Category, categorize

GROUND = CapturePlatform.GROUND


class TestCatalogo:
    """A resolução lê o Model Registry (antes, um espelho do catálogo no código)."""

    def test_banana_e_citros_tem_modelo(self, registry) -> None:
        assert ai_pipeline.resolve_model(registry, "banana", GROUND) == "banana-foliar"
        assert ai_pipeline.resolve_model(registry, "Limão", GROUND) == "citrus-foliar"
        assert ai_pipeline.resolve_model(registry, "laranja", GROUND) == "citrus-foliar"

    def test_a_escolha_do_talhao_vale(self, registry) -> None:
        escolhido = ai_pipeline.resolve_model(registry, "banana", GROUND, "banana-foliar-cc")
        assert escolhido == "banana-foliar-cc"

    def test_versao_de_outra_cultura_e_recusada(self, registry) -> None:
        with pytest.raises(ai_pipeline.NoModelForCaptureError, match="banana-foliar-cc"):
            ai_pipeline.resolve_model(registry, "banana", GROUND, "citrus-foliar")

    def test_primary_models_troca_a_versao_da_cultura(self, registry, monkeypatch) -> None:
        monkeypatch.setattr(
            ai_pipeline, "settings", Settings(primary_models="banana:banana-foliar-cc")
        )
        assert ai_pipeline.resolve_model(registry, "banana", GROUND) == "banana-foliar-cc"

    def test_a_recomendada_vem_primeiro(self, registry) -> None:
        keys = [m.model_key for m in ai_pipeline.versions_for_crop(registry, "citros", GROUND)]
        assert keys == ["citrus-foliar", "citrus-foliar-cc"]


class TestTaxonomia:
    @pytest.mark.parametrize("label", ["Sigatoka", "Fusarium_Wilt", "Canker", "Greening"])
    def test_doencas_novas(self, label: str) -> None:
        assert categorize(label, DiagnosisStatus.AI_VALIDATED) is Category.DISEASE

    @pytest.mark.parametrize("label", ["Leafminer", "Mites"])
    def test_pragas_de_citros(self, label: str) -> None:
        assert categorize(label, DiagnosisStatus.AI_VALIDATED) is Category.PEST

    def test_enrolamento_nao_e_doenca(self) -> None:
        """É sintoma — pulgão, ácaro, vírus ou nutrição. Quem nomeia a causa é o agrônomo."""
        assert categorize("Curl_Leaf", DiagnosisStatus.AI_VALIDATED) is Category.OTHER


def _analysis(**kwargs) -> ai_pipeline.Analysis:
    base = {"analyzer": "cloud-primary", "label": "Sigatoka", "confidence": 0.95}
    return ai_pipeline.Analysis(**{**base, **kwargs})


class TestSinaisNaDuplaValidacao:
    def test_o_que_nao_e_folha_vai_ao_agronomo_sem_rotulo(self) -> None:
        """O modelo diria Fusariose; o portão diz que é pseudocaule."""
        outcome = ai_pipeline.combine(
            [
                _analysis(label="Fusarium_Wilt", in_scope=False, scene="pseudocaule"),
                _analysis(analyzer="cloud-secondary", label="Fusarium_Wilt"),
            ]
        )
        assert outcome.status is DiagnosisStatus.NEEDS_REVIEW
        assert outcome.label is None
        assert "pseudocaule" in outcome.rationale

    def test_conjunto_conformal_ambiguo_nao_valida(self) -> None:
        outcome = ai_pipeline.combine(
            [
                _analysis(prediction_set=("Sigatoka", "Cordana")),
                _analysis(analyzer="cloud-secondary", prediction_set=("Sigatoka",)),
            ]
        )
        assert outcome.status is DiagnosisStatus.NEEDS_REVIEW
        assert "conformal" in outcome.rationale

    def test_sinais_vao_para_a_deteccao(self) -> None:
        signals = _analysis(
            in_scope=True, scene="folha_banana", prediction_set=("Sigatoka",)
        ).signals
        assert signals == {
            "in_scope": True,
            "scene": "folha_banana",
            "prediction_set": ["Sigatoka"],
        }


def _tile(label: str, confidence: float = 0.9, **extra) -> dict:
    return {"predicted_class": label, "confidence": confidence, "in_scope": True, **extra}


class TestQuadroDoRover:
    def test_o_rotulo_e_a_doenca_mais_frequente(self) -> None:
        body = {
            "model_key": "banana-foliar",
            "tiles": [_tile("Healthy")] * 6 + [_tile("Sigatoka", 0.8), _tile("Sigatoka", 0.9)],
            "tiles_analyzed": 8,
        }
        analysis = ai_pipeline.frame_analysis("cloud-primary", body, "banana-foliar", 12.0)

        assert analysis.label == "Sigatoka"
        assert analysis.confidence == pytest.approx(0.85)
        assert analysis.probabilities["Healthy"] == pytest.approx(0.75)
        assert analysis.frame["tiles_in_scope"] == 8

    def test_quadro_todo_fora_do_escopo_nao_tem_rotulo(self) -> None:
        body = {"tiles": [_tile("Fusarium_Wilt", in_scope=False, scene="pseudocaule")] * 3}
        analysis = ai_pipeline.frame_analysis("cloud-primary", body, "banana-foliar", 1.0)

        assert analysis.in_scope is False and analysis.scene == "pseudocaule"
        assert analysis.label is None

    def test_quadro_estranho_ao_modelo_vai_ao_agronomo(self) -> None:
        body = {"tiles": [_tile("Sigatoka", needs_review=True)] * 2 + [_tile("Sigatoka")] * 2}
        analysis = ai_pipeline.frame_analysis("cloud-primary", body, "banana-foliar", 1.0)
        outcome = ai_pipeline.combine([analysis, _analysis(analyzer="cloud-secondary")])

        assert outcome.status is DiagnosisStatus.NEEDS_REVIEW
        assert "destoam" in outcome.rationale

    def test_consulta_leva_a_pose_so_quando_completa(self) -> None:
        frame = ai_pipeline.RoverFrame(camera_height_mm=1000, distance_mm=270, field_id="T1")
        assert "field_id" not in frame.query("banana-foliar"), "sem rua, lado e posição, sem fusão"

        full = ai_pipeline.RoverFrame(
            camera_height_mm=1000,
            distance_mm=270,
            side="left",
            x_m=12.0,
            field_id="T1",
            row_id="3",
            pass_id="M1",
        )
        assert full.query("banana-foliar")["field_id"] == "T1"


@pytest.fixture
def banana_field(client: TestClient, demo: dict, admin_token: dict) -> dict:
    response = client.post(
        f"/v1/farms/{demo['farm_id']}/fields",
        json={"name": "Bananal", "crop": "banana", "boundary": CAMPO},
        headers=admin_token,
    )
    assert response.status_code == 201, response.text
    return response.json()


class TestVersaoPorTalhao:
    def test_talhao_novo_usa_a_recomendada(self, banana_field: dict) -> None:
        assert banana_field["ai_model"] is None
        assert banana_field["ai_model_in_use"] == "banana-foliar"

    def test_lista_as_versoes_para_o_seletor(
        self, client: TestClient, banana_field: dict, admin_token: dict
    ) -> None:
        choices = client.get(
            f"/v1/fields/{banana_field['id']}/ai-models", headers=admin_token
        ).json()

        assert [c["key"] for c in choices] == ["banana-foliar", "banana-foliar-cc"]
        assert choices[0]["selected"] and choices[0]["recommended"]
        assert choices[1]["license"] == "CC BY 4.0"

    def test_troca_para_a_comercial(
        self, client: TestClient, banana_field: dict, admin_token: dict
    ) -> None:
        response = client.put(
            f"/v1/fields/{banana_field['id']}/ai-model",
            json={"ai_model": "banana-foliar-cc"},
            headers=admin_token,
        )
        assert response.status_code == 200
        assert response.json()["ai_model_in_use"] == "banana-foliar-cc"

    def test_recusa_versao_de_outra_cultura(
        self, client: TestClient, banana_field: dict, admin_token: dict
    ) -> None:
        response = client.put(
            f"/v1/fields/{banana_field['id']}/ai-model",
            json={"ai_model": "citrus-foliar"},
            headers=admin_token,
        )
        assert response.status_code == 422
        assert "banana-foliar" in response.json()["detail"]

    def test_quem_so_le_nao_troca(
        self, client: TestClient, banana_field: dict, agronomist_token: dict
    ) -> None:
        response = client.put(
            f"/v1/fields/{banana_field['id']}/ai-model",
            json={"ai_model": "banana-foliar-cc"},
            headers=agronomist_token,
        )
        assert response.status_code == 403


class TestQuadroDoRoverPelaApi:
    """O rover manda o quadro com a câmera; a nuvem chama o /predict/rover-frame."""

    def test_quadro_vira_diagnostico_com_os_recortes(
        self,
        client: TestClient,
        demo: dict,
        admin_token: dict,
        banana_field: dict,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        chamadas: list[tuple[str, dict]] = []

        def ia(url: str, params: dict, **_: object) -> httpx.Response:
            chamadas.append((url, params))
            body = {
                "model_key": params["model"],
                "tiles_analyzed": 4,
                "tiles": [_tile("Healthy")] * 3 + [_tile("Sigatoka", 0.92)],
                "zone_summary": {"folhas_baixas": {"recortes": 4, "com_achado": 1}},
                "plants": ["L3-P0001"],
                "sigatoka": {"dsi": 12.5, "scale_validated": False},
            }
            return httpx.Response(200, json=body, request=httpx.Request("POST", url))

        monkeypatch.setattr(httpx, "post", ia)
        monkeypatch.setattr(
            ai_pipeline,
            "default_analyzers",
            lambda: [ai_pipeline.HttpModelAnalyzer(name="cloud-primary", base_url="http://ia")],
        )
        rover = provision(client, admin_token, "ROVER_SCOUT_V1", "P-ROVER-B", demo["farm_id"])
        metadata = {
            "sequence_number": rover.next_sequence(),
            "field_id": banana_field["id"],
            "captured_at": datetime.now(UTC).isoformat(),
            "lat": -21.9029,
            "lon": -45.8624,
            "heading_deg": 90.0,
            "row_index": 3,
            "camera": {"camera_height_mm": 1000, "distance_mm": 270, "side": "left", "x_m": 12.5},
        }
        response = rover.request(
            "POST",
            "/v1/device/observations",
            files={"file": ("q.jpg", b"\xff\xd8\xff\xd9", "image/jpeg")},
            data={"metadata": json.dumps(metadata)},
        )

        assert response.status_code == 201, response.text
        url, params = chamadas[0]
        assert url.endswith("/predict/rover-frame")
        assert params["model"] == "banana-foliar"
        assert params["field_id"] == banana_field["id"] and params["row_id"] == "3"
        # A planta é datada pela foto, não pela chegada — o lote pode vir horas depois.
        assert params["captured_at"] == metadata["captured_at"]

        body = response.json()
        assert body["label"] == "Sigatoka"
        frame = body["signals"]["frame"]
        assert frame["plants"] == ["L3-P0001"]
        assert frame["sigatoka"]["scale_validated"] is False

        # O console lê os mesmos sinais ao abrir a observação.
        diagnostico = client.get(f"/v1/diagnoses/{body['diagnosis_id']}", headers=admin_token)
        assert diagnostico.status_code == 200, diagnostico.text
        primaria = next(d for d in diagnostico.json()["detections"] if d["signals"])
        assert primaria["signals"]["frame"]["tiles_in_scope"] == 4

    def test_posicao_nan_e_recusada(
        self, client: TestClient, demo: dict, admin_token: dict, banana_field: dict
    ) -> None:
        # json.loads aceita NaN; na fusão, toda comparação com NaN é falsa e a
        # planta nunca casaria com a vizinha.
        rover = provision(client, admin_token, "ROVER_SCOUT_V1", "P-ROVER-NAN", demo["farm_id"])
        metadata = {
            "sequence_number": rover.next_sequence(),
            "field_id": banana_field["id"],
            "captured_at": datetime.now(UTC).isoformat(),
            "lat": -21.9029,
            "lon": -45.8624,
            "camera": {"camera_height_mm": 1000, "distance_mm": 270, "x_m": float("nan")},
        }
        response = rover.request(
            "POST",
            "/v1/device/observations",
            files={"file": ("q.jpg", b"\xff\xd8\xff\xd9", "image/jpeg")},
            data={"metadata": json.dumps(metadata)},
        )
        assert response.status_code == 422
        assert "x_m" in response.text

    def test_diagnostico_inexistente_e_404(self, client: TestClient, admin_token: dict) -> None:
        response = client.get("/v1/diagnoses/nao-existe", headers=admin_token)
        assert response.status_code == 404


class TestPlantasDoTalhao:
    """As rotas leem a fusão por planta do serviço de inferência."""

    @pytest.fixture
    def ia_no_ar(self, monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
        from valtexa.services import plant_map

        monkeypatch.setattr(
            plant_map, "settings", Settings(simulated_inference=False, inference_enabled=True)
        )
        chamadas: list[tuple[str, str]] = []

        def ia(method: str, url: str, **_: object) -> httpx.Response:
            chamadas.append((method, url))
            if url.endswith("/plants"):
                body: object = [{"plant_id": "L3-P0001", "status": "doente"}]
            elif url.endswith("/map"):
                body = {"type": "FeatureCollection", "features": []}
            else:
                return httpx.Response(404, json={}, request=httpx.Request(method, url))
            return httpx.Response(200, json=body, request=httpx.Request(method, url))

        monkeypatch.setattr(httpx, "request", ia)
        return chamadas

    def test_lista_as_plantas(
        self, client: TestClient, banana_field: dict, admin_token: dict, ia_no_ar
    ) -> None:
        body = client.get(f"/v1/fields/{banana_field['id']}/plants", headers=admin_token).json()
        assert body == [{"plant_id": "L3-P0001", "status": "doente"}]
        assert ia_no_ar[0][1].endswith(f"/fields/{banana_field['id']}/plants")

    def test_mapa_e_geojson(
        self, client: TestClient, banana_field: dict, admin_token: dict, ia_no_ar
    ) -> None:
        response = client.get(f"/v1/fields/{banana_field['id']}/plants/map", headers=admin_token)
        assert response.headers["content-type"].startswith("application/geo+json")
        assert response.json()["type"] == "FeatureCollection"

    def test_planta_desconhecida_e_404(
        self, client: TestClient, banana_field: dict, admin_token: dict, ia_no_ar
    ) -> None:
        response = client.get(
            f"/v1/fields/{banana_field['id']}/plants/nada/evolution", headers=admin_token
        )
        assert response.status_code == 404

    def test_id_de_planta_nao_reescreve_o_caminho_da_inferencia(
        self, client: TestClient, banana_field: dict, admin_token: dict, ia_no_ar
    ) -> None:
        # ".." viraria /fields/<id>/evolution no serviço de inferência.
        response = client.get(
            f"/v1/fields/{banana_field['id']}/plants/%2E%2E/evolution", headers=admin_token
        )
        assert response.status_code in (404, 422)
        assert ia_no_ar == [], "nada pode chegar à inferência"

    def test_segmento_codificado(self) -> None:
        from valtexa.services.plant_map import _seg

        assert _seg("1-P0009") == "1-P0009"
        assert "/" not in _seg("a/b") and "." not in _seg("..")

    def test_sem_inferencia_responde_503(
        self, client: TestClient, banana_field: dict, admin_token: dict
    ) -> None:
        """No simulador não há fusão por planta — e a rota diz isso, em vez de lista vazia."""
        response = client.get(f"/v1/fields/{banana_field['id']}/plants", headers=admin_token)
        assert response.status_code == 503


class TestFilaPorValor:
    def _diag(self, **kwargs):
        from valtexa.models import Agreement, Diagnosis

        base = {"agreement": Agreement.AGREE, "label": "Sigatoka", "novelty_score": 0.2}
        return Diagnosis(**{**base, **kwargs})

    def _det(self, probabilities: dict, **signals):
        from valtexa.models import Detection

        return Detection(probabilities=probabilities, signals=signals)

    def test_duvida_entre_duas_doencas_vem_antes_da_certeza(self) -> None:
        from collections import Counter

        from valtexa.services.review_priority import priority

        vistos = Counter({"Sigatoka": 50})
        certa = priority(self._diag(), self._det({"Sigatoka": 0.97, "Cordana": 0.03}), vistos)
        duvida = priority(self._diag(), self._det({"Sigatoka": 0.51, "Cordana": 0.49}), vistos)

        assert duvida.score > certa.score
        assert any("incerteza" in motivo for motivo in duvida.reasons)

    def test_no_quadro_a_duvida_e_dos_recortes(self) -> None:
        # Num quadro, `probabilities` é fração de recortes: dizer "margem do
        # modelo" ao agrônomo seria descrever outra coisa.
        from collections import Counter

        from valtexa.services.review_priority import priority

        prio = priority(
            self._diag(),
            self._det({"Sigatoka": 0.5, "Cordana": 0.5}, frame={"tiles_in_scope": 4}),
            Counter({"Sigatoka": 50}),
        )
        assert "recortes divididos entre Sigatoka e Cordana" in prio.reasons
        assert not any("margem" in motivo for motivo in prio.reasons)

    def test_fora_do_escopo_e_classe_rara_sobem(self) -> None:
        from collections import Counter

        from valtexa.services.review_priority import priority

        prio = priority(
            self._diag(label="Cordana"),
            self._det({"Cordana": 0.9, "Sigatoka": 0.1}, in_scope=False, scene="pseudocaule"),
            Counter(),
        )
        assert "não é folha: pseudocaule" in prio.reasons
        assert "classe rara: Cordana" in prio.reasons

    def test_a_rota_ordena_e_explica(
        self, client: TestClient, agronomist_token: dict, admin_token: dict, demo: dict
    ) -> None:
        from tests.helpers import upload_observation

        rover = provision(client, admin_token, "ROVER_SCOUT_V1", "P-ROVER-Q", demo["farm_id"])
        for novidade in (0.1, 3.0):
            upload_observation(rover, demo["field_id"], label="Common_Rust", novelty=novidade)

        fila = client.get(
            "/v1/review/queue", params={"order": "valor"}, headers=agronomist_token
        ).json()

        assert fila, "as observações simuladas precisam cair na fila"
        scores = [item["priority_score"] for item in fila]
        assert scores == sorted(scores, reverse=True)
        assert all(item["priority_reasons"] is not None for item in fila)


class TestConsentimentoChegaNaIa:
    """Verificação da Parte 2: com ``REVIEW_DIR`` ligado, a IA guardava na fila de
    revisão (que alimenta o treino) o quadro de **qualquer** cliente. Agora o SaaS
    diz em toda chamada se o cliente consentiu (brief, seção 32)."""

    def test_o_cabecalho_segue_o_consentimento_do_cliente(
        self,
        client: TestClient,
        demo: dict,
        admin_token: dict,
        banana_field: dict,
        session_factory,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from valtexa.models import User
        from valtexa.services import consent

        cabecalhos: list[dict] = []

        def ia(url: str, params: dict, headers: dict | None = None, **_: object):
            cabecalhos.append(dict(headers or {}))
            body = {"model_key": params["model"], "tiles_analyzed": 1, "tiles": [_tile("Healthy")]}
            return httpx.Response(200, json=body, request=httpx.Request("POST", url))

        monkeypatch.setattr(httpx, "post", ia)
        monkeypatch.setattr(
            ai_pipeline,
            "default_analyzers",
            lambda: [ai_pipeline.HttpModelAnalyzer(name="cloud-primary", base_url="http://ia")],
        )
        rover = provision(client, admin_token, "ROVER_SCOUT_V1", "P-ROVER-C", demo["farm_id"])

        def manda_quadro() -> None:
            metadata = {
                "sequence_number": rover.next_sequence(),
                "field_id": banana_field["id"],
                "captured_at": datetime.now(UTC).isoformat(),
                "lat": -21.9029,
                "lon": -45.8624,
                "camera": {"camera_height_mm": 1000, "distance_mm": 270, "x_m": 1.0},
            }
            resposta = rover.request(
                "POST",
                "/v1/device/observations",
                files={"file": ("q.jpg", b"\xff\xd8\xff\xd9", "image/jpeg")},
                data={"metadata": json.dumps(metadata)},
            )
            assert resposta.status_code == 201, resposta.text

        manda_quadro()
        assert cabecalhos[-1]["X-Training-Consent"] == "0", "sem decisão registrada é NÃO"

        with session_factory() as sessao:
            dono = sessao.scalars(
                select(User).where(User.email == "admin@valtexa.dev")
            ).one()
            consent.registrar(
                sessao, tenant_id=demo["tenant_id"], allowed=True, actor=dono, source="cliente"
            )
            sessao.commit()

        manda_quadro()
        assert cabecalhos[-1]["X-Training-Consent"] == "1"
