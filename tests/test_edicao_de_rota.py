"""O operador corrige a rota — e não consegue furar a cerca virtual por ali.

A validação humana era aprovar ou recusar. Quem opera sabe coisas que o
planejador não sabe: que aquela cabeceira atola em maio, que o portão do fundo
está trancado. Esse conhecimento não tinha por onde entrar.

O risco de abrir a porta é óbvio, e é o que a maior parte deste arquivo testa:
uma rota desenhada à mão não pode virar o caminho para passar por cima da mata
ou sair do talhão. O operador conhece o terreno melhor que a máquina; não
conhece melhor que o limite da propriedade, que é contrato, nem que a mata, que
é física.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.helpers import provision, send_telemetry


@pytest.fixture
def missao(client: TestClient, admin_token: dict, operator_token: dict, demo: dict):
    """Uma missão em rascunho, com rota planejada pela máquina."""
    rover = provision(client, admin_token, "ROVER_SCOUT_V1", "P-ROTA-ED", demo["farm_id"])
    send_telemetry(rover, battery_percent=95.0)
    resposta = client.post(
        "/v1/missions",
        json={"kind": "scout", "field_id": demo["field_id"], "device_id": rover.device_id},
        headers=operator_token,
    )
    assert resposta.status_code == 201, resposta.text
    return rover, resposta.json()


def rota_de(client: TestClient, token: dict, mission_id: str) -> list[list]:
    resposta = client.get(f"/v1/missions/{mission_id}/segments", headers=token)
    assert resposta.status_code == 200, resposta.text
    return [linha["path"] for linha in resposta.json()]


def _contorno_do_talhao(client: TestClient, token: dict, demo: dict) -> list:
    return client.get(f"/v1/fields/{demo['field_id']}", headers=token).json()["boundary"]


MATA = {
    "resolution_ok": True,
    "description": "mata no meio do talhão",
    "crop_fraction": 0.88,
    "obstacle_fraction": 0.07,
    "path_fraction": 0.05,
    "operable_area_ha": 20.0,
    "cover_fractions": {"lavoura": 0.88, "mata": 0.07, "solo": 0.05, "outro": 0.0},
    "objects": [
        {
            "kind": "mata",
            "center": [-45.8620, -21.9040],
            "outline": [
                [-45.8632, -21.9032],
                [-45.8608, -21.9032],
                [-45.8608, -21.9048],
                [-45.8632, -21.9048],
            ],
            "area_ha": 1.4,
            "traversable": False,
            "confidence": 0.9,
            "blocks": 11,
        }
    ],
    "heuristic": True,
}


def trilha(client: TestClient, token: dict, **filtros) -> list[dict]:
    return client.get("/v1/audit", params={"limit": 200, **filtros}, headers=token).json()


class TestCorrigirAMao:
    def test_o_operador_troca_a_rota_e_os_segmentos_acompanham(
        self, client: TestClient, operator_token: dict, missao
    ) -> None:
        _, m = missao
        antiga = rota_de(client, operator_token, m["id"])
        assert len(antiga) > 2, "o planejador precisa ter feito mais de duas passadas"

        # Duas primeiras passadas, na ordem inversa: um percurso válido e
        # visivelmente diferente do calculado.
        nova = [antiga[1], antiga[0]]
        resposta = client.patch(
            f"/v1/missions/{m['id']}/route",
            json={"legs": nova, "reason": "A cabeceira norte atola nesta época."},
            headers=operator_token,
        )
        assert resposta.status_code == 200, resposta.text

        depois = rota_de(client, operator_token, m["id"])
        assert len(depois) == 2, "os segmentos antigos não foram substituídos"
        assert depois[0] == nova[0], "a ordem que o operador mandou não foi respeitada"

    def test_o_plano_marca_que_a_rota_e_desenhada_e_nao_calculada(
        self, client: TestClient, operator_token: dict, missao
    ) -> None:
        """Sem a marca, uma rota à mão seria lida como cálculo — e a estimativa
        de tempo herdada teria uma autoridade que não tem."""
        _, m = missao
        antiga = rota_de(client, operator_token, m["id"])
        resposta = client.patch(
            f"/v1/missions/{m['id']}/route", json={"legs": antiga[:2]}, headers=operator_token
        )
        assert resposta.json()["plan"]["route_source"] == "manual"

    def test_a_distancia_e_recalculada_e_nao_aceita_do_cliente(
        self, client: TestClient, operator_token: dict, missao
    ) -> None:
        """O número que vale é o que sai da geometria. Aceitar metragem do
        cliente abriria a porta para a tela discordar do que o robô cumpre."""
        _, m = missao
        antiga = rota_de(client, operator_token, m["id"])
        antes = m["plan"]["path_length_m"]

        resposta = client.patch(
            f"/v1/missions/{m['id']}/route", json={"legs": antiga[:2]}, headers=operator_token
        )
        depois = resposta.json()["plan"]["path_length_m"]
        assert depois < antes, "duas passadas de muitas deveriam encurtar o percurso"
        assert depois > 0


class TestACercaVirtualSegura:
    def test_rota_fora_da_area_e_recusada(
        self, client: TestClient, operator_token: dict, missao
    ) -> None:
        """O teste que justifica a existência da edição manual: ela não pode
        virar o caminho para furar a cerca virtual pela porta da frente."""
        _, m = missao
        resposta = client.patch(
            f"/v1/missions/{m['id']}/route",
            json={"legs": [[[-46.5, -22.5], [-46.4, -22.4]]]},
            headers=operator_token,
        )
        assert resposta.status_code == 422, resposta.text
        assert "área" in resposta.json()["detail"].lower()

    def test_rota_com_um_ponto_so_nao_e_rota(
        self, client: TestClient, operator_token: dict, missao
    ) -> None:
        _, m = missao
        antiga = rota_de(client, operator_token, m["id"])
        resposta = client.patch(
            f"/v1/missions/{m['id']}/route",
            json={"legs": [[antiga[0][0]]]},
            headers=operator_token,
        )
        assert resposta.status_code == 422
        assert "dois" in resposta.json()["detail"]

    def test_rota_vazia_e_recusada(
        self, client: TestClient, operator_token: dict, missao
    ) -> None:
        _, m = missao
        resposta = client.patch(
            f"/v1/missions/{m['id']}/route", json={"legs": []}, headers=operator_token
        )
        assert resposta.status_code == 422

    def test_rota_nao_se_mexe_depois_de_autorizada(
        self, client: TestClient, operator_token: dict, missao
    ) -> None:
        """Depois da autorização a assinatura cobre um percurso específico.
        Trocá-lo por baixo faria o robô executar o que ninguém aprovou."""
        _, m = missao
        antiga = rota_de(client, operator_token, m["id"])
        autorizou = client.post(f"/v1/missions/{m['id']}/authorize", headers=operator_token)
        if autorizou.status_code != 200 or autorizou.json()["verdict"] != "safe_to_execute":
            pytest.skip("a camada de segurança barrou a missão neste ambiente")

        resposta = client.patch(
            f"/v1/missions/{m['id']}/route", json={"legs": antiga[:2]}, headers=operator_token
        )
        assert resposta.status_code == 409, resposta.text
        assert "aborte" in resposta.json()["detail"].lower()

    def test_a_rota_de_outro_cliente_nao_se_alcanca(
        self, client: TestClient, platform_token: dict, operator_token: dict, missao
    ) -> None:
        """De dentro de outro cliente, esta missão não existe.

        A equipe da ValTexa sem associação nem chega a entrar no vizinho (403,
        pedindo sessão de suporte); com sessão de suporte assistida no vizinho, a
        missão do primeiro cliente continua não existindo (404, não 403).
        """
        _, m = missao
        criado = client.post(
            "/v1/admin/tenants",
            json={"tenant": {"name": "Sítio Vizinho", "slug": "sitio-vizinho"}},
            headers=platform_token,
        )
        assert criado.status_code == 201, criado.text
        vizinho = criado.json()["tenant"]["id"]

        antiga = rota_de(client, operator_token, m["id"])
        resposta = client.patch(
            f"/v1/missions/{m['id']}/route",
            json={"legs": antiga[:2]},
            headers={**platform_token, "X-Tenant-Id": vizinho},
        )
        assert resposta.status_code == 403
        assert "sessão de suporte" in resposta.json()["detail"]

        suporte = client.post(
            "/v1/platform/support-sessions",
            json={
                "tenant_id": vizinho,
                "reason": "Conferir a rota de missão do vizinho",
                "assisted_reason": "Teste de isolamento com escrita liberada",
            },
            headers=platform_token,
        )
        assert suporte.status_code == 201, suporte.text
        token = {"Authorization": f"Bearer {suporte.json()['access_token']}"}
        resposta = client.patch(
            f"/v1/missions/{m['id']}/route", json={"legs": antiga[:2]}, headers=token
        )
        assert resposta.status_code == 404


class TestReplanejar:
    def test_faixa_mais_estreita_da_mais_passadas(
        self, client: TestClient, operator_token: dict, missao
    ) -> None:
        _, m = missao
        antes = len(rota_de(client, operator_token, m["id"]))
        largura = m["plan"]["swath_m"]

        resposta = client.post(
            f"/v1/missions/{m['id']}/replan",
            json={"swath_m": largura / 2},
            headers=operator_token,
        )
        assert resposta.status_code == 200, resposta.text
        depois = len(rota_de(client, operator_token, m["id"]))
        assert depois > antes, f"faixa pela metade deveria dar mais passadas: {antes} → {depois}"

    def test_replanejar_marca_a_origem_da_rota(
        self, client: TestClient, operator_token: dict, missao
    ) -> None:
        _, m = missao
        resposta = client.post(
            f"/v1/missions/{m['id']}/replan", json={}, headers=operator_token
        )
        assert resposta.json()["plan"]["route_source"] == "replan"

    def test_faixa_fora_do_limite_e_recusada_pelo_contrato(
        self, client: TestClient, operator_token: dict, missao
    ) -> None:
        _, m = missao
        for largura in (0.0, -3.0, 500.0):
            resposta = client.post(
                f"/v1/missions/{m['id']}/replan",
                json={"swath_m": largura},
                headers=operator_token,
            )
            assert resposta.status_code == 422, f"faixa {largura} passou"

    def test_o_replanejamento_aplica_a_leitura_de_terreno_que_chegou_depois(
        self, client: TestClient, admin_token: dict, operator_token: dict, demo: dict, missao
    ) -> None:
        """O uso mais comum do replanejamento, e o menos óbvio.

        A missão nasce antes de alguém rodar o encaixe de contorno, então a rota
        original não contorna nada. Replanejar sem parâmetro nenhum ainda faz
        trabalho: é o que faz a mata entrar na conta.
        """
        _, m = missao
        assert (m["plan"].get("avoided") or 0) == 0, "a missão já nasceu contornando algo"

        gravou = client.patch(
            f"/v1/fields/{demo['field_id']}/boundary",
            json={"boundary": _contorno_do_talhao(client, operator_token, demo), "terrain": MATA},
            headers=admin_token,
        )
        assert gravou.status_code == 200, gravou.text

        resposta = client.post(
            f"/v1/missions/{m['id']}/replan", json={}, headers=operator_token
        )
        assert resposta.status_code == 200, resposta.text
        assert resposta.json()["plan"]["avoided"] == 1, "a mata não entrou no replanejamento"

    def test_folga_maior_deixa_mais_area_de_fora(
        self, client: TestClient, admin_token: dict, operator_token: dict, demo: dict, missao
    ) -> None:
        """A folga é o parâmetro que o operador mexe quando o rover raspou na
        mata da última vez. Precisa ter efeito visível, senão é um campo que
        aceita número e não faz nada."""
        _, m = missao
        client.patch(
            f"/v1/fields/{demo['field_id']}/boundary",
            json={"boundary": _contorno_do_talhao(client, operator_token, demo), "terrain": MATA},
            headers=admin_token,
        )

        apertado = client.post(
            f"/v1/missions/{m['id']}/replan",
            json={"obstacle_margin_m": 0.0},
            headers=operator_token,
        )
        assert apertado.status_code == 200, apertado.text
        metros_apertado = apertado.json()["plan"]["path_length_m"]

        folgado = client.post(
            f"/v1/missions/{m['id']}/replan",
            json={"obstacle_margin_m": 25.0},
            headers=operator_token,
        )
        assert folgado.status_code == 200, folgado.text
        metros_folgado = folgado.json()["plan"]["path_length_m"]

        assert metros_folgado < metros_apertado, (
            f"folga de 25 m deveria encurtar o percurso: "
            f"{metros_apertado} → {metros_folgado}"
        )

    def test_replanejar_nao_se_faz_depois_de_autorizada(
        self, client: TestClient, operator_token: dict, missao
    ) -> None:
        _, m = missao
        autorizou = client.post(f"/v1/missions/{m['id']}/authorize", headers=operator_token)
        if autorizou.status_code != 200 or autorizou.json()["verdict"] != "safe_to_execute":
            pytest.skip("a camada de segurança barrou a missão neste ambiente")
        resposta = client.post(
            f"/v1/missions/{m['id']}/replan", json={}, headers=operator_token
        )
        assert resposta.status_code == 409


class TestATrilha:
    def test_a_troca_de_rota_fica_registrada_com_os_dois_resumos(
        self, client: TestClient, admin_token: dict, operator_token: dict, missao
    ) -> None:
        """Guardar só a rota nova diria que a missão *tem* tal percurso, não que
        ela *passou* por outro — e a pergunta de uma apuração é a segunda."""
        _, m = missao
        antiga = rota_de(client, operator_token, m["id"])
        client.patch(
            f"/v1/missions/{m['id']}/route",
            json={"legs": antiga[:2], "reason": "Portão do fundo trancado."},
            headers=operator_token,
        )

        registros = trilha(client, admin_token, action="mission.route_updated")
        deste = next(r for r in registros if r["subject_id"] == m["id"])
        assert deste["old_state"] != deste["new_state"], "os dois resumos saíram iguais"
        assert len(deste["new_state"]) == 64, "o resumo da rota não é um sha256"
        assert "Portão" in (deste["reason"] or "")
        assert deste["payload"]["origem"] == "manual"
        assert deste["payload"]["antes"]["waypoints"] > deste["payload"]["depois"]["waypoints"]

    def test_o_replanejamento_registra_as_premissas_usadas(
        self, client: TestClient, admin_token: dict, operator_token: dict, missao
    ) -> None:
        _, m = missao
        client.post(
            f"/v1/missions/{m['id']}/replan",
            json={"swath_m": m["plan"]["swath_m"] / 2},
            headers=operator_token,
        )
        registros = trilha(client, admin_token, action="mission.route_updated")
        deste = next(r for r in registros if r["subject_id"] == m["id"])
        assert deste["payload"]["origem"] == "replan"
        assert "faixa" in (deste["reason"] or "").lower()
