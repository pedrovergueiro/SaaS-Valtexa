"""Planejamento de cobertura: rota, tempo, energia e postes de recarga.

O que estes testes protegem é a única conta da plataforma que manda um rover de
98 kg para dentro de uma lavoura. Um erro aqui não aparece na tela — aparece com
o robô parado no meio do talhão.

A estratégia é conferir contra grandezas independentes: a área do polígono pela
geometria, o comprimento de linha pela área dividida pela faixa, a energia pelos
coeficientes vezes a distância. Se o planejador e a conta de guardanapo
discordarem, um dos dois está errado.
"""

from __future__ import annotations

import math

import pytest
from fastapi.testclient import TestClient

from valtexa.services import geo, planner
from valtexa.services.hal import REFERENCE_MODELS, Capabilities

# Um retângulo de lados conhecidos, para a conta fechar na mão.
# 0,0045° de longitude e 0,0018° de latitude perto de -22°: ~463 m por ~200 m.
TALHAO = [
    [-45.9300, -22.2200],
    [-45.9255, -22.2200],
    [-45.9255, -22.2218],
    [-45.9300, -22.2218],
]


def perfil_v3(**override: float) -> planner.PerfilDeAutonomia:
    modelo = next(m for m in REFERENCE_MODELS if m["code"] == "ROVER_V3")
    return planner.PerfilDeAutonomia.from_capabilities(
        Capabilities(raw=modelo["capabilities"]), **override
    )


class TestPerfil:
    def test_deriva_os_coeficientes_do_datasheet(self) -> None:
        perfil = perfil_v3()
        # 5120 Wh em 8 h = 640 W médios; 35% é carga fixa.
        assert perfil.wh_per_h == pytest.approx(640 * 0.35, rel=0.01)
        # O resto vira tração, dividido pelos metros que ele faz numa hora.
        assert perfil.wh_per_m == pytest.approx(640 * 0.65 / (1.0 * 3600), rel=0.01)

    def test_reserva_reduz_a_energia_utilizavel(self) -> None:
        perfil = perfil_v3(reserve_percent=20.0)
        assert perfil.usable_wh == pytest.approx(5120 * 0.8)

    def test_custo_soma_tracao_e_carga_fixa(self) -> None:
        perfil = perfil_v3()
        # Uma hora parado gasta só a carga fixa.
        assert perfil.custo_wh(0, 3600) == pytest.approx(perfil.wh_per_h)
        # Mil metros a 1 m/s gastam tração mais a carga fixa desses 1000 s.
        esperado = 1000 * perfil.wh_per_m + (1000 / 3600) * perfil.wh_per_h
        assert perfil.custo_wh(1000, 1000) == pytest.approx(esperado)

    def test_datasheet_nasce_marcado_como_nao_medido(self) -> None:
        assert perfil_v3().medido is False


class TestGeometriaDoPlano:
    def test_metros_de_linha_batem_com_area_dividida_pela_faixa(self) -> None:
        """Conferência independente: varrer A m² em faixas de L m dá A/L metros."""
        perfil = perfil_v3()
        plano = planner.plan(TALHAO, perfil, azimute_deg=90.0, swath_m=3.0)

        area_m2 = geo.area_ha(TALHAO) * 10_000
        esperado = area_m2 / 3.0
        assert plano.metros_de_linha == pytest.approx(esperado, rel=0.05)

    def test_passadas_batem_com_a_largura_do_talhao(self) -> None:
        perfil = perfil_v3()
        plano = planner.plan(TALHAO, perfil, azimute_deg=90.0, swath_m=3.0)

        # ~200 m de largura em faixas de 3 m.
        largura_m = geo.haversine_m(-45.9300, -22.2200, -45.9300, -22.2218)
        assert plano.passadas == pytest.approx(largura_m / 3.0, abs=2)

    def test_faixa_mais_larga_reduz_percurso_e_tempo(self) -> None:
        perfil = perfil_v3()
        estreita = planner.plan(TALHAO, perfil, swath_m=2.0)
        larga = planner.plan(TALHAO, perfil, swath_m=6.0)

        assert larga.metros_de_linha < estreita.metros_de_linha
        assert larga.minutos_totais < estreita.minutos_totais
        assert larga.passadas < estreita.passadas

    def test_azimute_muda_o_numero_de_passadas_nao_a_area(self) -> None:
        """Varrer no sentido do lado longo dá menos passadas e menos manobra."""
        perfil = perfil_v3()
        ao_longo = planner.plan(TALHAO, perfil, azimute_deg=90.0, swath_m=3.0)
        atravessado = planner.plan(TALHAO, perfil, azimute_deg=0.0, swath_m=3.0)

        assert ao_longo.area_ha == atravessado.area_ha
        assert ao_longo.passadas < atravessado.passadas
        assert ao_longo.metros_de_manobra < atravessado.metros_de_manobra

    def test_tempo_confere_com_distancia_dividida_pela_velocidade(self) -> None:
        perfil = perfil_v3(speed_ms=1.0)
        plano = planner.plan(TALHAO, perfil, swath_m=3.0)

        minutos_esperados = plano.metros_totais / 1.0 / 60.0
        assert plano.minutos_dirigindo == pytest.approx(minutos_esperados, rel=0.01)
        # O tempo total inclui a manobra de cabeceira, então é maior.
        assert plano.minutos_totais > plano.minutos_dirigindo

    def test_faixa_invalida_e_recusada(self) -> None:
        with pytest.raises(ValueError):
            planner.plan(TALHAO, perfil_v3(), swath_m=0.0)


class TestPostesDeRecarga:
    def test_talhao_pequeno_nao_precisa_de_poste(self) -> None:
        pequeno = [
            [-45.9300, -22.2200],
            [-45.9295, -22.2200],
            [-45.9295, -22.2203],
            [-45.9300, -22.2203],
        ]
        plano = planner.plan(pequeno, perfil_v3(), swath_m=3.0)
        assert plano.cargas == 0
        assert plano.postes == []
        assert plano.minutos_de_recarga == 0.0

    def test_poste_aparece_quando_a_carga_nao_alcanca(self) -> None:
        # Bateria pequena de propósito: força a divisão do percurso.
        perfil = perfil_v3(battery_wh=600.0)
        plano = planner.plan(TALHAO, perfil, swath_m=3.0)

        assert plano.cargas >= 1
        assert len(plano.postes) == plano.cargas
        assert all("reserva" in poste.motivo for poste in plano.postes)

    def test_postes_saem_em_ordem_e_dentro_do_percurso(self) -> None:
        perfil = perfil_v3(battery_wh=600.0)
        plano = planner.plan(TALHAO, perfil, swath_m=3.0)

        distancias = [poste.metros_no_percurso for poste in plano.postes]
        assert distancias == sorted(distancias)
        assert all(0 < d <= plano.metros_totais for d in distancias)
        assert [p.ordem for p in plano.postes] == list(range(1, len(plano.postes) + 1))

    def test_o_rover_nunca_e_programado_abaixo_da_reserva(self) -> None:
        """A promessa central: o plano não manda o robô para além do que ele volta."""
        perfil = perfil_v3(battery_wh=600.0, reserve_percent=20.0)
        plano = planner.plan(TALHAO, perfil, swath_m=3.0)

        for poste in plano.postes:
            assert poste.bateria_na_chegada_percent >= perfil.reserve_percent - 0.5

    def test_bateria_menor_exige_mais_postes(self) -> None:
        grande = planner.plan(TALHAO, perfil_v3(battery_wh=2000.0), swath_m=3.0)
        pequena = planner.plan(TALHAO, perfil_v3(battery_wh=600.0), swath_m=3.0)
        assert pequena.cargas > grande.cargas

    def test_area_coberta_cresce_de_poste_em_poste(self) -> None:
        perfil = perfil_v3(battery_wh=600.0)
        plano = planner.plan(TALHAO, perfil, swath_m=3.0)

        areas = [poste.area_coberta_ha for poste in plano.postes]
        assert areas == sorted(areas)
        assert all(a <= plano.area_ha for a in areas)

    def test_comecar_com_meia_carga_antecipa_o_primeiro_poste(self) -> None:
        perfil = perfil_v3(battery_wh=600.0)
        cheio = planner.plan(TALHAO, perfil, swath_m=3.0, bateria_inicial_percent=100.0)
        pela_metade = planner.plan(TALHAO, perfil, swath_m=3.0, bateria_inicial_percent=60.0)

        assert pela_metade.postes[0].metros_no_percurso < cheio.postes[0].metros_no_percurso

    def test_tempo_de_recarga_entra_no_total(self) -> None:
        perfil = perfil_v3(battery_wh=600.0, charge_kw=2.5)
        plano = planner.plan(TALHAO, perfil, swath_m=3.0)

        assert plano.minutos_de_recarga > 0
        assert plano.minutos_totais > plano.minutos_dirigindo + plano.minutos_de_manobra

    def test_energia_total_confere_com_os_coeficientes(self) -> None:
        """Conferência independente do consumo, pela distância e pelo tempo."""
        perfil = perfil_v3()
        plano = planner.plan(TALHAO, perfil, swath_m=3.0)

        segundos = plano.metros_totais / perfil.speed_ms
        esperado = plano.metros_totais * perfil.wh_per_m + segundos / 3600 * perfil.wh_per_h
        assert plano.wh_totais == pytest.approx(esperado, rel=0.02)


class TestAvisos:
    def test_plano_de_datasheet_avisa_que_nao_foi_medido(self) -> None:
        plano = planner.plan(TALHAO, perfil_v3(), swath_m=3.0)
        assert plano.perfil_medido is False
        assert any("não medido em campo" in aviso for aviso in plano.avisos)

    def test_perfil_medido_nao_avisa(self) -> None:
        perfil = perfil_v3()
        medido = planner.PerfilDeAutonomia(
            battery_wh=perfil.battery_wh,
            speed_ms=perfil.speed_ms,
            swath_m=perfil.swath_m,
            wh_per_m=perfil.wh_per_m,
            wh_per_h=perfil.wh_per_h,
            medido=True,
        )
        plano = planner.plan(TALHAO, medido, swath_m=3.0)
        assert plano.perfil_medido is True
        assert not any("não medido" in aviso for aviso in plano.avisos)


class TestCalibracao:
    def test_recupera_os_coeficientes_de_missoes_sinteticas(self) -> None:
        """O ajuste tem que devolver os números que geraram as amostras."""
        a_real, b_real = 0.12, 220.0
        amostras = [
            planner.Amostra(metros=m, segundos=s, wh_gastos=a_real * m + b_real * s / 3600)
            for m, s in [(10_000, 10_000), (2_000, 20_000), (15_000, 16_000), (500, 30_000)]
        ]
        wh_per_m, wh_per_h, n = planner.calibrate(amostras, battery_wh=5120)

        assert wh_per_m == pytest.approx(a_real, rel=1e-6)
        assert wh_per_h == pytest.approx(b_real, rel=1e-6)
        assert n == 4

    def test_uma_missao_so_nao_calibra(self) -> None:
        """Duas incógnitas não saem de uma equação. Recusar é o certo."""
        with pytest.raises(ValueError, match="ao menos 2"):
            planner.calibrate(
                [planner.Amostra(metros=1000, segundos=1000, wh_gastos=200)], battery_wh=5120
            )

    def test_missoes_proporcionais_nao_separam_tracao_de_carga_fixa(self) -> None:
        proporcionais = [
            planner.Amostra(metros=1000, segundos=1000, wh_gastos=180),
            planner.Amostra(metros=2000, segundos=2000, wh_gastos=360),
            planner.Amostra(metros=3000, segundos=3000, wh_gastos=540),
        ]
        with pytest.raises(ValueError, match="proporcionais"):
            planner.calibrate(proporcionais, battery_wh=5120)

    def test_telemetria_ruim_nao_vira_coeficiente_negativo(self) -> None:
        ruins = [
            planner.Amostra(metros=10_000, segundos=1_000, wh_gastos=50),
            planner.Amostra(metros=1_000, segundos=10_000, wh_gastos=900),
        ]
        with pytest.raises(ValueError, match=r"negativo|implausível"):
            planner.calibrate(ruins, battery_wh=5120)

    def test_calibrado_muda_o_plano(self) -> None:
        """É o ponto da calibração: o plano deixa de ser datasheet."""
        base = perfil_v3()
        plano_datasheet = planner.plan(TALHAO, base, swath_m=3.0)

        gastando_o_dobro = planner.PerfilDeAutonomia(
            battery_wh=base.battery_wh,
            speed_ms=base.speed_ms,
            swath_m=base.swath_m,
            wh_per_m=base.wh_per_m * 2,
            wh_per_h=base.wh_per_h * 2,
            medido=True,
        )
        plano_medido = planner.plan(TALHAO, gastando_o_dobro, swath_m=3.0)

        assert plano_medido.wh_totais > plano_datasheet.wh_totais
        assert plano_medido.cargas >= plano_datasheet.cargas


class TestPelaApi:
    def test_equipe_planeja_o_talhao(
        self, client: TestClient, platform_token: dict, demo: dict
    ) -> None:
        resposta = client.post(
            f"/v1/admin/fields/{demo['field_id']}/plan",
            json={"device_model_code": "ROVER_V3", "row_azimuth_deg": 15.0, "swath_m": 3.0},
            headers=platform_token,
        )
        assert resposta.status_code == 200, resposta.text
        plano = resposta.json()

        assert plano["area_ha"] > 0
        assert plano["passadas"] > 0
        assert plano["horas_totais"] > 0
        assert plano["perfil_medido"] is False
        assert len(plano["rota"]) == plano["passadas"]
        assert any("não medido em campo" in aviso for aviso in plano["avisos"])

    def test_rascunho_do_editor_e_planejado_sem_gravar(
        self, client: TestClient, platform_token: dict, demo: dict, session_factory
    ) -> None:
        """O editor mostra a rota do desenho que ainda não foi salvo, com os obstáculos
        do encaixe — e o talhão gravado continua o mesmo."""
        from valtexa.models import Field

        with session_factory() as session:
            antes = list(session.get(Field, demo["field_id"]).boundary)
        rascunho = [[-45.9300, -22.2200], [-45.9250, -22.2200],
                    [-45.9250, -22.2244], [-45.9300, -22.2244]]
        mata = [[-45.9280, -22.2215], [-45.9270, -22.2215],
                [-45.9270, -22.2225], [-45.9280, -22.2225]]
        terreno = {"resolution_ok": True, "description": "lido", "crop_fraction": 0.9,
                   "obstacle_fraction": 0.05, "path_fraction": 0.05,
                   "objects": [{"kind": "mata", "center": [-45.9275, -22.222],
                                "outline": mata, "area_ha": 0.11, "traversable": False,
                                "confidence": 0.7, "blocks": 4}]}
        resposta = client.post(
            f"/v1/admin/fields/{demo['field_id']}/plan",
            json={"swath_m": 3.0, "boundary": rascunho, "terrain": terreno},
            headers=platform_token,
        )
        assert resposta.status_code == 200, resposta.text
        plano = resposta.json()
        assert 20 < plano["area_ha"] < 30  # o rascunho de 24 ha, não o talhão gravado
        assert plano["avoided"] == 1 and plano["area_contornada_ha"] > 0
        with session_factory() as session:
            assert session.get(Field, demo["field_id"]).boundary == antes  # nada gravado

    def test_cliente_nao_planeja(
        self, client: TestClient, admin_token: dict, demo: dict
    ) -> None:
        resposta = client.post(
            f"/v1/admin/fields/{demo['field_id']}/plan", json={}, headers=admin_token
        )
        assert resposta.status_code == 403

    def test_modelo_desconhecido_e_recusado(
        self, client: TestClient, platform_token: dict, demo: dict
    ) -> None:
        resposta = client.post(
            f"/v1/admin/fields/{demo['field_id']}/plan",
            json={"device_model_code": "ROVER_QUE_NAO_EXISTE"},
            headers=platform_token,
        )
        assert resposta.status_code == 404

    def test_talhao_sem_poligono_nao_planeja(
        self, client: TestClient, platform_token: dict, demo: dict, session_factory
    ) -> None:
        from valtexa.models import Farm, Field

        with session_factory() as session:
            fazenda = session.get(Farm, demo["farm_id"])
            sem_contorno = Field(
                tenant_id=demo["tenant_id"],
                farm_id=fazenda.id,
                name="Sem contorno",
                crop="coffee",
                boundary=[],
            )
            session.add(sem_contorno)
            session.commit()
            field_id = sem_contorno.id

        resposta = client.post(
            f"/v1/admin/fields/{field_id}/plan", json={}, headers=platform_token
        )
        assert resposta.status_code == 422
        assert "sem contorno" in resposta.json()["detail"]

    def test_plano_de_outro_cliente_nao_e_acessivel(
        self, client: TestClient, platform_token: dict, demo: dict, session_factory
    ) -> None:
        from valtexa.models import Tenant

        with session_factory() as session:
            outro = Tenant(name="Vizinho do plano", slug="vizinho-plano")
            session.add(outro)
            session.commit()
            outro_id = outro.id

        resposta = client.post(
            f"/v1/admin/fields/{demo['field_id']}/plan",
            json={},
            headers={**platform_token, "X-Tenant-Id": outro_id},
        )
        assert resposta.status_code == 404


def test_talhao_de_cinco_alqueires_tem_numeros_plausiveis() -> None:
    """Um caso concreto, do tamanho da lavoura que a ValTexa mira.

    Cinco alqueires mineiros são 24,2 ha. Os números não são promessa — o perfil
    é de datasheet —, mas precisam ser plausíveis: um resultado de 40 minutos ou
    de 40 dias denunciaria erro de unidade em algum lugar da cadeia.
    """
    cinco_alqueires = [
        [-45.9300, -22.2200],
        [-45.9250, -22.2200],
        [-45.9250, -22.2244],
        [-45.9300, -22.2244],
    ]
    area = geo.area_ha(cinco_alqueires)
    assert 20 < area < 30

    plano = planner.plan(cinco_alqueires, perfil_v3(), azimute_deg=15.0, swath_m=3.0)

    # Varrer 24 ha em faixas de 3 m são ~80 km de linha, a 1 m/s: ~22 h dirigindo.
    assert 60 < plano.metros_de_linha / 1000 < 100
    assert 20 < plano.minutos_dirigindo / 60 < 30
    # E não cabe numa carga só: o talhão precisa de poste.
    assert plano.cargas >= 2
    assert plano.ha_por_hora < 2.0
    assert math.isclose(plano.area_ha, area, rel_tol=0.01)
