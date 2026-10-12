"""Relevo: a altitude entra no planejamento, e a falta dela é declarada.

O planejamento tratava toda lavoura como plana. A diferença aparece em três
lugares que custam dinheiro ou equipamento — a conta de autonomia, o ângulo de
tombamento e a direção das passadas.

Esta plataforma **não tem fonte de elevação contratada**, e metade deste arquivo
é sobre isso: a falta precisa aparecer como falta. Um zero devolvido no lugar de
uma altitude seria lido como "terreno plano" e entraria no plano com a
autoridade de uma medição — que é o jeito mais caro de errar aqui.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from valtexa.services import elevation


def _grava_relevo(field_id: str, *, declividade_maxima: float = 7.0) -> dict:
    """Grava um relevo no talhão como a rota de medição faria.

    Escreve pelo banco, e não pela API, porque a rota de medição depende de uma
    fonte de elevação externa: fazer o teste passar por ela exigiria rede, e o
    que se testa aqui é o que acontece **depois** de medir.
    """
    from valtexa.db import session_scope
    from valtexa.models import Field

    relevo = {
        "amostras": 64,
        "altitude_min_m": 700.0,
        "altitude_max_m": 700.0 + declividade_maxima * 3,
        "desnivel_m": declividade_maxima * 3,
        "declividade_media_deg": declividade_maxima * 0.7,
        "declividade_maxima_deg": declividade_maxima,
        "azimute_da_encosta_deg": 180.0,
        "fonte": "teste",
    }
    with session_scope() as sessao:
        campo = sessao.get(Field, field_id)
        campo.relief = relevo
        campo.relief_read_at = datetime.now(UTC)
    return relevo


TALHAO = [
    [-45.8640, -21.9060],
    [-45.8600, -21.9060],
    [-45.8600, -21.9020],
    [-45.8640, -21.9020],
]


class TestSemFonteConfigurada:
    def test_medir_sem_fonte_responde_nao_implementado(
        self, client: TestClient, platform_token: dict, demo: dict
    ) -> None:
        """501 e não 200 com zeros. A distinção é o ponto deste módulo."""
        resposta = client.post(
            f"/v1/admin/fields/{demo['field_id']}/relief", headers=platform_token
        )
        assert resposta.status_code == 501, resposta.text
        assert "ELEVATION_URL" in resposta.json()["detail"]

    def test_o_plano_declara_que_planejou_como_se_fosse_plano(
        self, client: TestClient, platform_token: dict, demo: dict
    ) -> None:
        """O operador precisa saber que a autonomia estimada não conta subida."""
        resposta = client.post(
            f"/v1/admin/fields/{demo['field_id']}/plan",
            json={"device_model_code": "ROVER_SCOUT_V1", "row_azimuth_deg": 90},
            headers=platform_token,
        )
        assert resposta.status_code == 200, resposta.text
        corpo = resposta.json()
        assert corpo["relief"] is None
        assert any("plano" in aviso.lower() for aviso in corpo["avisos"]), corpo["avisos"]

    def test_o_provedor_diz_que_nao_esta_configurado(self) -> None:
        assert elevation.configurado() is False
        with pytest.raises(elevation.ElevationNotConfiguredError) as erro:
            elevation.provedor()
        assert "ELEVATION_URL" in str(erro.value)


class TestAGradeDeAmostragem:
    def test_amostra_o_miolo_e_nao_so_os_vertices(self) -> None:
        """Um talhão pode ter os quatro cantos na mesma cota e um barranco no
        meio. É o barranco que derruba o rover."""
        pontos = elevation.grade(TALHAO, passo_m=100.0)
        assert len(pontos) > 4, "a grade não passou dos vértices"
        cantos = {(round(p[0], 4), round(p[1], 4)) for p in TALHAO}
        amostrados = {(round(lon, 4), round(lat, 4)) for lon, lat in pontos}
        assert amostrados - cantos, "nenhum ponto interno foi amostrado"

    def test_a_grade_respeita_o_teto_de_consultas(self) -> None:
        """O número de pontos cresce com o quadrado da área. Sem teto, um talhão
        de 200 ha a 40 m daria doze mil consultas."""
        enorme = [[-46.5, -22.5], [-45.5, -22.5], [-45.5, -21.5], [-46.5, -21.5]]
        pontos = elevation.grade(enorme, passo_m=40.0, teto=250)
        assert len(pontos) <= 250

    def test_poligono_degenerado_nao_gera_grade(self) -> None:
        assert elevation.grade([[0, 0], [1, 1]]) == []


class TestOResumoDoRelevo:
    """O cálculo, com altitudes fabricadas — sem rede, e com a resposta sabida.

    Uma rampa de inclinação conhecida é o único jeito de saber se a conta está
    certa: contra um DEM real não haveria com o que comparar.
    """

    def _rampa(self, subida_por_metro: float):
        """Terreno que sobe para o norte a uma taxa conhecida."""
        pontos = elevation.grade(TALHAO, passo_m=100.0)
        lat0 = min(lat for _, lat in pontos)
        alturas = [
            (lat - lat0) * elevation.GRAU_EM_METROS * subida_por_metro for _, lat in pontos
        ]
        return pontos, alturas

    def test_mede_a_inclinacao_de_uma_rampa_conhecida(self) -> None:
        # 10% de subida = atan(0.1) ≈ 5,71°.
        pontos, alturas = self._rampa(0.10)
        relevo = elevation._resume(pontos, alturas, fonte="teste")
        assert abs(relevo.declividade_media_deg - math.degrees(math.atan(0.10))) < 0.5

    def test_terreno_plano_nao_tem_direcao_de_encosta(self) -> None:
        pontos = elevation.grade(TALHAO, passo_m=100.0)
        relevo = elevation._resume(pontos, [700.0] * len(pontos), fonte="teste")
        assert relevo.declividade_media_deg < 0.01
        assert relevo.azimute_da_encosta_deg is None
        assert elevation.azimute_em_curva_de_nivel(relevo) is None

    def test_a_encosta_aponta_para_onde_o_terreno_cai(self) -> None:
        """Subindo para o norte, o terreno cai para o sul: 180°."""
        pontos, alturas = self._rampa(0.10)
        relevo = elevation._resume(pontos, alturas, fonte="teste")
        assert relevo.azimute_da_encosta_deg is not None
        assert abs(relevo.azimute_da_encosta_deg - 180.0) < 5.0

    def test_a_curva_de_nivel_e_perpendicular_a_queda(self) -> None:
        """É a direção que um operador experiente escolhe sozinho, e que o
        planejador não tinha como saber."""
        pontos, alturas = self._rampa(0.10)
        relevo = elevation._resume(pontos, alturas, fonte="teste")
        curva = elevation.azimute_em_curva_de_nivel(relevo)
        assert curva is not None
        diferenca = abs(((curva - relevo.azimute_da_encosta_deg) % 360.0) - 90.0)
        assert diferenca < 1.0

    def test_o_desnivel_sai_dos_extremos(self) -> None:
        pontos = elevation.grade(TALHAO, passo_m=100.0)
        alturas = [700.0] * len(pontos)
        alturas[0], alturas[-1] = 690.0, 730.0
        relevo = elevation._resume(pontos, alturas, fonte="teste")
        assert abs(relevo.desnivel_m - 40.0) < 0.01


class TestOsAvisos:
    def _relevo(self, maxima: float, desnivel: float = 5.0) -> elevation.Relevo:
        return elevation.Relevo(
            amostras=50,
            altitude_min_m=700.0,
            altitude_max_m=700.0 + desnivel,
            desnivel_m=desnivel,
            declividade_media_deg=maxima / 2,
            declividade_maxima_deg=maxima,
            azimute_da_encosta_deg=180.0,
            fonte="teste",
        )

    def test_encosta_acima_do_limite_avisa_do_risco_certo(self) -> None:
        """O risco aqui é tombamento, não atraso — e a mensagem diz isso."""
        avisos = elevation.avisos_de_relevo(self._relevo(20.0), limite_deg=15.0)
        assert avisos
        assert "tombamento" in avisos[0].lower()

    def test_encosta_perto_do_limite_sugere_curva_de_nivel(self) -> None:
        avisos = elevation.avisos_de_relevo(self._relevo(12.0), limite_deg=15.0)
        assert any("curva de nível" in aviso for aviso in avisos)

    def test_terreno_suave_nao_avisa_nada(self) -> None:
        assert elevation.avisos_de_relevo(self._relevo(3.0), limite_deg=15.0) == []

    def test_desnivel_grande_avisa_sobre_a_autonomia(self) -> None:
        """A estimativa de energia não considera a subida, e quem lê o número
        precisa saber disso antes de confiar nele."""
        avisos = elevation.avisos_de_relevo(self._relevo(4.0, desnivel=45.0), limite_deg=15.0)
        assert any("autonomia" in aviso.lower() for aviso in avisos)


class TestACamadaDeSeguranca:
    def test_sem_relevo_medido_a_missao_nao_e_barrada(
        self, client: TestClient, admin_token: dict, operator_token: dict, demo: dict
    ) -> None:
        """Transformar "não medi" em "não pode" travaria toda missão de toda
        instalação que ainda não ligou um DEM."""
        from tests.helpers import provision, send_telemetry

        rover = provision(client, admin_token, "ROVER_SCOUT_V1", "P-RELEVO-1", demo["farm_id"])
        send_telemetry(rover, battery_percent=95.0)
        criada = client.post(
            "/v1/missions",
            json={"kind": "scout", "field_id": demo["field_id"], "device_id": rover.device_id},
            headers=operator_token,
        )
        assert criada.status_code == 201, criada.text

        parecer = client.post(
            f"/v1/missions/{criada.json()['id']}/safety/preview", headers=operator_token
        )
        assert parecer.status_code == 200, parecer.text
        declive = next(c for c in parecer.json()["checks"] if c["code"] == "slope")
        assert declive["passed"] is True
        assert "não medido" in declive["detail"]

    def test_encosta_medida_acima_do_limite_bloqueia(
        self, client: TestClient, admin_token: dict, operator_token: dict, demo: dict
    ) -> None:
        """Tombar numa encosta é perda total. É o tipo de dano que nenhum
        operador aceita ter aprovado sem aviso."""
        from tests.helpers import provision, send_telemetry

        _grava_relevo(demo["field_id"], declividade_maxima=26.0)

        rover = provision(client, admin_token, "ROVER_SCOUT_V1", "P-RELEVO-2", demo["farm_id"])
        send_telemetry(rover, battery_percent=95.0)
        criada = client.post(
            "/v1/missions",
            json={"kind": "scout", "field_id": demo["field_id"], "device_id": rover.device_id},
            headers=operator_token,
        )
        assert criada.status_code == 201, criada.text

        parecer = client.post(
            f"/v1/missions/{criada.json()['id']}/safety/preview", headers=operator_token
        )
        declive = next(c for c in parecer.json()["checks"] if c["code"] == "slope")
        assert declive["passed"] is False, "26° de encosta passaram pela camada de segurança"
        assert "26" in declive["detail"]
        assert parecer.json()["verdict"] == "blocked"


class TestOndeORelevoVive:
    """A cobertura muda a cada safra; a encosta não muda nunca.

    Por isso o relevo tem coluna própria e não vive dentro de ``terrain``.
    """

    def test_releitura_de_imagem_nao_derruba_o_relevo(
        self, client: TestClient, admin_token: dict, demo: dict
    ) -> None:
        """Apagá-lo obrigaria a pagar a consulta de DEM de novo por um pedaço de
        chão que continua o mesmo."""
        _grava_relevo(demo["field_id"])
        campo = client.get(f"/v1/fields/{demo['field_id']}", headers=admin_token).json()
        assert campo["relief"] is not None

        resposta = client.patch(
            f"/v1/fields/{demo['field_id']}/boundary",
            json={
                "boundary": campo["boundary"],
                "terrain": {
                    "resolution_ok": True,
                    "description": "safra nova",
                    "crop_fraction": 0.9,
                    "obstacle_fraction": 0.05,
                    "path_fraction": 0.05,
                    "objects": [],
                },
            },
            headers=admin_token,
        )
        assert resposta.status_code == 200, resposta.text
        assert resposta.json()["relief"] is not None, "o relevo se perdeu numa releitura"
        assert resposta.json()["terrain"]["description"] == "safra nova"

    def test_contorno_novo_derruba_o_relevo(
        self, client: TestClient, admin_token: dict, demo: dict
    ) -> None:
        """Contorno diferente é outro pedaço de chão. Guardar o relevo seria
        manter no banco a medida de um talhão que não existe mais."""
        _grava_relevo(demo["field_id"])
        campo = client.get(f"/v1/fields/{demo['field_id']}", headers=admin_token).json()

        outro = [list(ponto) for ponto in campo["boundary"]]
        outro[0] = [outro[0][0] - 0.001, outro[0][1]]
        resposta = client.patch(
            f"/v1/fields/{demo['field_id']}/boundary",
            json={"boundary": outro},
            headers=admin_token,
        )
        assert resposta.status_code == 200, resposta.text
        assert resposta.json()["relief"] is None, "o relevo sobreviveu a um contorno novo"
