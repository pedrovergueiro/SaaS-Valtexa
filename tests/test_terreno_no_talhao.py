"""A leitura de terreno gravada no talhão, e o que ela muda no planejamento.

Duas telas produzem e consomem essa informação em momentos diferentes: o encaixe
de contorno a calcula, e o planejamento de missão precisa dela dias depois. O que
se testa aqui é a ponte entre as duas — e, principalmente, que o plano **diga**
que não desvia dos obstáculos, em vez de deixar quem aprova achar que desvia.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.helpers import provision, send_telemetry
from valtexa.services import geo

CONTORNO = [
    [-45.8660, -21.9060],
    [-45.8590, -21.9060],
    [-45.8590, -21.9010],
    [-45.8660, -21.9010],
]

TERRENO = {
    "resolution_ok": True,
    "description": "88% lavoura, 7% obstáculo · 1 bloqueio(s) e 1 caminho(s) localizados",
    "crop_fraction": 0.88,
    "obstacle_fraction": 0.07,
    "path_fraction": 0.05,
    "operable_area_ha": 20.0,
    "row_spacing_px": 44.0,
    "cover_fractions": {"lavoura": 0.88, "mata": 0.07, "solo": 0.05, "outro": 0.0},
    "objects": [
        {
            "kind": "mata",
            "center": [-45.8620, -21.9040],
            "outline": [
                [-45.8630, -21.9030],
                [-45.8610, -21.9030],
                [-45.8610, -21.9050],
                [-45.8630, -21.9050],
            ],
            "area_ha": 1.4,
            "traversable": False,
            "confidence": 0.9,
            "blocks": 11,
        },
        {
            "kind": "carreador",
            "center": [-45.8600, -21.9020],
            "outline": [
                [-45.8660, -21.9018],
                [-45.8590, -21.9018],
                [-45.8590, -21.9022],
                [-45.8660, -21.9022],
            ],
            "area_ha": 0.6,
            "traversable": True,
            "confidence": 0.7,
            "blocks": 9,
        },
    ],
    "heuristic": True,
}


def salvar(client: TestClient, token: dict, field_id: str, terreno: dict | None) -> dict:
    resposta = client.patch(
        f"/v1/fields/{field_id}/boundary",
        json={"boundary": CONTORNO, "terrain": terreno},
        headers=token,
    )
    assert resposta.status_code == 200, resposta.text
    return resposta.json()


class TestGravarALeitura:
    def test_o_terreno_volta_junto_com_o_talhao(
        self, client: TestClient, admin_token: dict, demo: dict
    ) -> None:
        salvar(client, admin_token, demo["field_id"], TERRENO)

        campo = client.get(f"/v1/fields/{demo['field_id']}", headers=admin_token).json()
        assert campo["terrain"]["crop_fraction"] == 0.88
        assert len(campo["terrain"]["objects"]) == 2
        assert campo["terrain_read_at"] is not None

    def test_contorno_novo_sem_leitura_apaga_a_anterior(
        self, client: TestClient, admin_token: dict, demo: dict
    ) -> None:
        """Uma leitura vale para o contorno com que foi feita.

        Guardá-la depois que o polígono mudou seria manter no banco a medida de
        um talhão que não existe mais — e o planejamento a usaria sem saber.
        """
        salvar(client, admin_token, demo["field_id"], TERRENO)
        salvar(client, admin_token, demo["field_id"], None)

        campo = client.get(f"/v1/fields/{demo['field_id']}", headers=admin_token).json()
        assert campo["terrain"] is None
        assert campo["terrain_read_at"] is None

    def test_a_auditoria_registra_que_houve_leitura(
        self, client: TestClient, admin_token: dict, demo: dict
    ) -> None:
        salvar(client, admin_token, demo["field_id"], TERRENO)

        trilha = client.get("/v1/audit", headers=admin_token).json()
        registro = next(i for i in trilha if i["action"] == "field.boundary_updated")
        assert registro["payload"]["depois"]["terreno_lido"] is True
        assert registro["payload"]["depois"]["area_operavel_ha"] == 20.0


class TestPlanejamentoComObstaculo:
    def test_o_plano_carrega_a_leitura_e_a_area_operavel(
        self, client: TestClient, platform_token: dict, admin_token: dict, demo: dict
    ) -> None:
        salvar(client, admin_token, demo["field_id"], TERRENO)

        plano = client.post(
            f"/v1/admin/fields/{demo['field_id']}/plan",
            json={"device_model_code": "ROVER_V3", "row_azimuth_deg": 90},
            headers=platform_token,
        ).json()

        assert plano["terrain"]["crop_fraction"] == 0.88
        assert plano["operable_area_ha"] == 20.0
        assert plano["operable_area_ha"] < plano["area_ha"]

    def test_nenhuma_passada_entra_no_obstaculo(
        self, client: TestClient, platform_token: dict, admin_token: dict, demo: dict
    ) -> None:
        """O teste que importa: a rota não pisa na mata.

        Não basta descontar a área — o rover segue a rota, não a estatística. Se
        uma passada atravessa a moita, o robô entra nela. Aqui se percorre cada
        passada amostrando o segmento e se exige que nenhum ponto caia dentro do
        obstáculo.
        """
        salvar(client, admin_token, demo["field_id"], TERRENO)

        plano = client.post(
            f"/v1/admin/fields/{demo['field_id']}/plan",
            json={"device_model_code": "ROVER_V3", "row_azimuth_deg": 90},
            headers=platform_token,
        ).json()

        mata = next(o for o in TERRENO["objects"] if not o["traversable"])
        dentro = 0
        for perna in plano["rota"]:
            (lat_a, lon_a), (lat_b, lon_b) = perna[0], perna[-1]
            for passo in range(41):
                t = passo / 40
                lon = lon_a + (lon_b - lon_a) * t
                lat = lat_a + (lat_b - lat_a) * t
                if geo.contains_point(mata["outline"], lon, lat):
                    dentro += 1
        assert dentro == 0, f"{dentro} ponto(s) da rota caíram dentro da mata"

    def test_o_plano_diz_quanto_contornou(
        self, client: TestClient, platform_token: dict, admin_token: dict, demo: dict
    ) -> None:
        salvar(client, admin_token, demo["field_id"], TERRENO)

        plano = client.post(
            f"/v1/admin/fields/{demo['field_id']}/plan",
            json={"device_model_code": "ROVER_V3", "row_azimuth_deg": 90},
            headers=platform_token,
        ).json()

        assert plano["avoided"] == 1, "só a mata é contornada; o carreador é caminho"
        assert plano["area_contornada_ha"] > 0
        assert any("contorna 1 obstáculo" in aviso for aviso in plano["avisos"])

    def test_contornar_parte_as_passadas_em_duas(
        self, client: TestClient, platform_token: dict, admin_token: dict, demo: dict
    ) -> None:
        """Contornar custa: mais passadas, menos metros de linha.

        É o que acontece no campo, e é por isso que o plano com obstáculo é o
        plano confiável — o sem obstáculo conta como lavoura o chão que é mata.
        """
        # O mesmo contorno nos dois lados: salvar() também troca o polígono, e
        # comparar planos de polígonos diferentes não diria nada sobre o desvio.
        salvar(client, admin_token, demo["field_id"], None)
        antes = client.post(
            f"/v1/admin/fields/{demo['field_id']}/plan",
            json={"device_model_code": "ROVER_V3", "row_azimuth_deg": 90},
            headers=platform_token,
        ).json()

        salvar(client, admin_token, demo["field_id"], TERRENO)
        depois = client.post(
            f"/v1/admin/fields/{demo['field_id']}/plan",
            json={"device_model_code": "ROVER_V3", "row_azimuth_deg": 90},
            headers=platform_token,
        ).json()

        assert depois["passadas"] > antes["passadas"], "as passadas partidas não apareceram"
        assert depois["metros_de_linha"] < antes["metros_de_linha"], (
            "a rota continuou varrendo o chão da mata"
        )

    def test_a_margem_afasta_a_rota_da_borda(
        self, client: TestClient, platform_token: dict, admin_token: dict, demo: dict
    ) -> None:
        """O contorno de um obstáculo lido por imagem é o retângulo de um bloco
        da grade. Raspar essa borda é entrar nele."""
        salvar(client, admin_token, demo["field_id"], TERRENO)

        apertado = client.post(
            f"/v1/admin/fields/{demo['field_id']}/plan",
            json={
                "device_model_code": "ROVER_V3",
                "row_azimuth_deg": 90,
                "obstacle_margin_m": 0,
            },
            headers=platform_token,
        ).json()
        folgado = client.post(
            f"/v1/admin/fields/{demo['field_id']}/plan",
            json={
                "device_model_code": "ROVER_V3",
                "row_azimuth_deg": 90,
                "obstacle_margin_m": 30,
            },
            headers=platform_token,
        ).json()

        assert folgado["metros_de_linha"] < apertado["metros_de_linha"]

    def test_carreador_nao_conta_como_bloqueio(
        self, client: TestClient, platform_token: dict, admin_token: dict, demo: dict
    ) -> None:
        """O carreador não tem planta, mas é por onde o rover atravessa."""
        so_caminho = {
            **TERRENO,
            "objects": [o for o in TERRENO["objects"] if o["traversable"]],
            "obstacle_fraction": 0.0,
        }
        salvar(client, admin_token, demo["field_id"], so_caminho)

        plano = client.post(
            f"/v1/admin/fields/{demo['field_id']}/plan",
            json={"device_model_code": "ROVER_V3", "row_azimuth_deg": 90},
            headers=platform_token,
        ).json()

        assert plano["avoided"] == 0, "o carreador virou desvio; ele é caminho"
        assert plano["area_contornada_ha"] == 0.0

    def test_sem_leitura_o_plano_segue_valendo(
        self, client: TestClient, platform_token: dict, demo: dict
    ) -> None:
        """A leitura é opcional: o talhão desenhado já basta para planejar."""
        plano = client.post(
            f"/v1/admin/fields/{demo['field_id']}/plan",
            json={"device_model_code": "ROVER_V3", "row_azimuth_deg": 90},
            headers=platform_token,
        ).json()

        assert plano["terrain"] is None
        assert plano["operable_area_ha"] is None
        assert plano["metros_totais"] > 0
        assert plano["passadas"] > 0

    def test_leitura_sem_resolucao_nao_desconta_area(
        self, client: TestClient, platform_token: dict, admin_token: dict, demo: dict
    ) -> None:
        """O erro caro: numa imagem que não resolve a rua, nada é lavoura para o
        classificador. Descontar área a partir disso cortaria o talhão pela
        metade sem ninguém desconfiar."""
        salvar(
            client,
            admin_token,
            demo["field_id"],
            {
                "resolution_ok": False,
                "description": "Resolução insuficiente para ler o terreno",
                "crop_fraction": 0.0,
                "obstacle_fraction": 0.0,
                "path_fraction": 0.0,
            },
        )

        plano = client.post(
            f"/v1/admin/fields/{demo['field_id']}/plan",
            json={"device_model_code": "ROVER_V3", "row_azimuth_deg": 90},
            headers=platform_token,
        ).json()

        assert plano["operable_area_ha"] is None
        assert any("não resolveu a rua" in aviso for aviso in plano["avisos"])


class TestMissaoCarregaOPlano:
    def test_a_missao_guarda_os_numeros_que_apareceram_na_tela(
        self, client: TestClient, platform_token: dict, admin_token: dict, demo: dict
    ) -> None:
        """Quem valida a missão depois precisa ver os mesmos números, e não
        recalculá-los: um replanejamento com outro parâmetro daria outro
        resultado, e a discussão seria sobre qual dos dois valia."""
        plano = client.post(
            f"/v1/admin/fields/{demo['field_id']}/plan",
            json={"device_model_code": "ROVER_V3", "row_azimuth_deg": 90},
            headers=platform_token,
        ).json()

        rover = provision(client, admin_token, "ROVER_SCOUT_V1", "P-PLAN-1", demo["farm_id"])
        send_telemetry(rover, battery_percent=95.0)

        missao = client.post(
            "/v1/missions",
            json={
                "kind": "scout",
                "field_id": demo["field_id"],
                "device_id": rover.device_id,
                "plan": {
                    "origem": "admin/planejamento",
                    "metros_totais": plano["metros_totais"],
                    "minutos_totais": plano["minutos_totais"],
                    "cargas": plano["cargas"],
                    "perfil_medido": plano["perfil_medido"],
                },
            },
            headers=admin_token,
        )
        assert missao.status_code == 201, missao.text
        corpo = missao.json()
        assert corpo["state"] == "draft", "missão nasce sem valer nada no mundo físico"
        assert corpo["plan"]["metros_totais"] == pytest.approx(plano["metros_totais"])
        assert corpo["plan"]["perfil_medido"] is False
