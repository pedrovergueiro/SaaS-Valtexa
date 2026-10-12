"""O ciclo de vida de uma missão, inteiro, visto pela trilha de auditoria.

A pergunta que este arquivo responde é a da apuração: **o que aconteceu nesta
missão, em que ordem, e quem respondia por cada passo.** Ela precisa ser
respondida por `/v1/audit` sozinho, sem juntar tabelas à mão e sem depender de
log de aplicação, que rotaciona.

Cada teste aqui corresponde a uma linha do checklist de auditoria: criação,
despacho, início, pausa, retomada, cancelamento, conclusão, falha e emergência.
A máquina de estados é um funil — toda transição passa por
``mission_manager.transition`` —, então a cobertura não vem de lembrar de
auditar em cada rota, e sim de o funil existir. Estes testes seguram o funil.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.helpers import provision, send_event, send_telemetry


@pytest.fixture
def missao_pronta(client: TestClient, admin_token: dict, operator_token: dict, demo: dict):
    """Um rover provisionado e uma missão criada, ainda em rascunho."""
    rover = provision(client, admin_token, "ROVER_SCOUT_V1", "P-TRILHA-1", demo["farm_id"])
    send_telemetry(rover, battery_percent=95.0)

    resposta = client.post(
        "/v1/missions",
        json={"kind": "scout", "field_id": demo["field_id"], "device_id": rover.device_id},
        headers=operator_token,
    )
    assert resposta.status_code == 201, resposta.text
    return rover, resposta.json()


def trilha(client: TestClient, token: dict, **filtros) -> list[dict]:
    return client.get("/v1/audit", params={"limit": 500, **filtros}, headers=token).json()


def acoes_de(client: TestClient, token: dict, mission_id: str) -> list[dict]:
    """A trilha de uma missão, da mais antiga para a mais nova."""
    linhas = trilha(client, token, subject_id=mission_id)
    return list(reversed(linhas))


class TestCriacaoEDespacho:
    def test_a_criacao_da_missao_fica_na_trilha(
        self, client: TestClient, admin_token: dict, missao_pronta
    ) -> None:
        _, missao = missao_pronta
        registros = acoes_de(client, admin_token, missao["id"])
        assert any(r["action"] == "mission.created" for r in registros)

    def test_cada_mudanca_de_estado_guarda_de_onde_veio_e_para_onde_foi(
        self, client: TestClient, admin_token: dict, operator_token: dict, missao_pronta
    ) -> None:
        """Sem o estado anterior, a trilha diz que a missão *está* em tal ponto,
        não que *passou* por ele. Reconstituir a ordem seria adivinhação."""
        _, missao = missao_pronta
        client.post(f"/v1/missions/{missao['id']}/authorize", headers=operator_token)

        transicoes = [
            r
            for r in acoes_de(client, admin_token, missao["id"])
            if r["action"] == "mission.transition"
        ]
        assert transicoes, "nenhuma transição registrada"
        for registro in transicoes:
            assert registro["new_state"], "transição sem estado de destino"
            assert registro["old_state"] or registro["new_state"] == "draft"

    def test_a_trilha_diz_quem_mandou(
        self, client: TestClient, admin_token: dict, operator_token: dict, missao_pronta
    ) -> None:
        _, missao = missao_pronta
        client.post(f"/v1/missions/{missao['id']}/authorize", headers=operator_token)

        registros = acoes_de(client, admin_token, missao["id"])
        assert all(r["at"] for r in registros), "registro sem data e hora"
        humanos = [r for r in registros if r["actor_type"] == "user"]
        assert humanos, "nenhuma ação atribuída a uma pessoa"
        assert all(r["actor_id"] or r["actor_label"] for r in humanos)


class TestCicloCompleto:
    """Início, pausa, retomada e conclusão — o caminho feliz inteiro."""

    def _ate_executando(self, client, operator_token, rover, missao) -> bool:
        """Leva a missão até RUNNING. Devolve falso se a segurança barrar.

        A camada de segurança pode recusar por vento, bateria ou horário, e
        recusar é o comportamento correto dela. O que se testa aqui é a trilha,
        não a liberação — por isso o teste se retira em vez de forçar.
        """
        # Scout não passa por `approve`: aquela é a assinatura de quem responde
        # por produto químico no ar, e não há produto aqui. Mas passa pela
        # camada de segurança como qualquer missão — é ela que confere bateria,
        # cerca virtual e enlace antes de o robô sair.
        autorizacao = client.post(
            f"/v1/missions/{missao['id']}/authorize", headers=operator_token
        )
        if autorizacao.status_code != 200:
            return False
        if (
            client.post(
                f"/v1/missions/{missao['id']}/dispatch", headers=operator_token
            ).status_code
            != 200
        ):
            return False
        confirmou = rover.request(
            "POST",
            f"/v1/device/missions/{missao['id']}/ack",
            json_body={"mission_id": missao["id"], "accepted": True},
        )
        assert confirmou.status_code == 200, confirmou.text
        return True

    def test_inicio_pausa_retomada_e_conclusao_aparecem_em_ordem(
        self, client: TestClient, admin_token: dict, operator_token: dict, missao_pronta
    ) -> None:
        rover, missao = missao_pronta
        if not self._ate_executando(client, operator_token, rover, missao):
            pytest.skip("a camada de segurança barrou o despacho neste ambiente")

        pausou = rover.request(
            "POST",
            f"/v1/device/missions/{missao['id']}/pause",
            json_body={
                "reason": "low_battery",
                "battery_percent": 18.0,
                "lat": -21.9029,
                "lon": -45.8624,
            },
        )
        assert pausou.status_code == 200, pausou.text
        recarregou = rover.request("POST", f"/v1/device/missions/{missao['id']}/recharged")
        assert recarregou.status_code == 200, recarregou.text
        retomou = client.post(f"/v1/missions/{missao['id']}/resume", headers=operator_token)
        assert retomou.status_code == 200, retomou.text
        concluiu = rover.request("POST", f"/v1/device/missions/{missao['id']}/complete")
        assert concluiu.status_code == 200, concluiu.text

        estados = [
            r["new_state"]
            for r in acoes_de(client, admin_token, missao["id"])
            if r["action"] == "mission.transition"
        ]
        # Cada item do checklist, na ordem em que aconteceu.
        for esperado in [
            "dispatched",       # comando enviado
            "running",          # início
            "paused_for_recharge",  # pausa
            "ready_to_resume",  # pronta para retomar
            "running",          # retomada
            "completed",        # conclusão
        ]:
            assert esperado in estados, f"{esperado!r} não ficou na trilha: {estados}"

        assert estados.index("dispatched") < estados.index("completed")
        assert estados.count("running") >= 2, "a retomada não aparece como início novo"

    def test_o_comando_enviado_ao_rover_e_registrado_em_cada_despacho(
        self, client: TestClient, admin_token: dict, operator_token: dict, missao_pronta
    ) -> None:
        """Despachar e retomar emitem comandos assinados diferentes. Os dois
        precisam de linha própria: `mission.nonce` guarda só o último."""
        rover, missao = missao_pronta
        if not self._ate_executando(client, operator_token, rover, missao):
            pytest.skip("a camada de segurança barrou o despacho neste ambiente")

        pausou = rover.request(
            "POST",
            f"/v1/device/missions/{missao['id']}/pause",
            json_body={"reason": "low_battery", "battery_percent": 18.0},
        )
        assert pausou.status_code == 200, pausou.text
        rover.request("POST", f"/v1/device/missions/{missao['id']}/recharged")
        retomou = client.post(f"/v1/missions/{missao['id']}/resume", headers=operator_token)
        assert retomou.status_code == 200, retomou.text

        comandos = trilha(client, admin_token, action="device.command_issued")
        desta = [c for c in comandos if c["payload"]["mission_id"] == missao["id"]]
        assert len(desta) >= 2, "a retomada não registrou comando próprio"

        nonces = {c["payload"]["nonce"] for c in desta}
        assert len(nonces) == len(desta), "dois comandos com o mesmo nonce"
        sequencias = [c["payload"]["sequence"] for c in desta]
        assert len(set(sequencias)) == len(sequencias), "sequência repetida entre comandos"


class TestCancelamento:
    def test_abortar_fica_na_trilha_com_o_motivo(
        self, client: TestClient, admin_token: dict, operator_token: dict, missao_pronta
    ) -> None:
        """Abortar nunca falha por estado — e por isso mesmo precisa de motivo
        registrado: é a ação que interrompe trabalho pago."""
        _, missao = missao_pronta
        resposta = client.post(
            f"/v1/missions/{missao['id']}/abort",
            json={"reason": "Chuva forte entrando pelo oeste."},
            headers=operator_token,
        )
        assert resposta.status_code == 200, resposta.text

        registros = acoes_de(client, admin_token, missao["id"])
        abortada = next(r for r in registros if r["new_state"] == "aborted")
        assert "Chuva" in (abortada["reason"] or ""), "o motivo do aborto não foi guardado"
        assert abortada["actor_type"] == "user"


class TestFalhaEEmergencia:
    def test_falha_critica_do_rover_entra_na_trilha(
        self, client: TestClient, admin_token: dict, missao_pronta
    ) -> None:
        """Antes desta verificação, uma parada de emergência ficava só na tabela
        de eventos do dispositivo. Quem procurasse "o que deu errado" na trilha
        não achava nada — e é a primeira pergunta de qualquer apuração.
        """
        rover, _ = missao_pronta
        send_event(
            rover,
            "emergency_stop",
            severity="critical",
            message="Botão de emergência acionado no campo.",
        )

        falhas = trilha(client, admin_token, action="device.fault")
        assert falhas, "a parada de emergência não deixou rastro na trilha"

        registro = falhas[0]
        assert registro["actor_type"] == "device"
        assert registro["new_state"] == "emergency_stop"
        assert "emergência" in (registro["reason"] or "").lower()

    def test_evento_comum_nao_polui_a_trilha(
        self, client: TestClient, admin_token: dict, missao_pronta
    ) -> None:
        """Só o crítico sobe. Uma trilha com telemetria de rotina dentro é uma
        trilha que ninguém lê — inclusive nos pontos que importam."""
        rover, _ = missao_pronta
        send_event(rover, "waypoint_reached", severity="info")

        assert trilha(client, admin_token, action="device.fault") == []

    def test_a_falha_aponta_a_missao_em_curso(
        self, client: TestClient, admin_token: dict, operator_token: dict, missao_pronta
    ) -> None:
        """Sem o vínculo, a falha fica órfã e a apuração da missão não a alcança."""
        rover, missao = missao_pronta
        send_event(
            rover,
            "motor_overcurrent",
            severity="critical",
            mission_id=missao["id"],
            message="Sobrecorrente no motor esquerdo.",
        )

        falhas = trilha(client, admin_token, action="device.fault")
        assert falhas
        assert falhas[0]["payload"]["mission_id"] == missao["id"]


class TestAIntegridadeDaTrilha:
    def test_a_trilha_de_uma_missao_e_recuperavel_por_um_filtro_so(
        self, client: TestClient, admin_token: dict, operator_token: dict, missao_pronta
    ) -> None:
        """É o que torna a apuração possível sem juntar tabelas à mão."""
        _, missao = missao_pronta
        client.post(f"/v1/missions/{missao['id']}/authorize", headers=operator_token)
        client.post(
            f"/v1/missions/{missao['id']}/abort",
            json={"reason": "teste"},
            headers=operator_token,
        )

        registros = trilha(client, admin_token, subject_id=missao["id"])
        assert len(registros) >= 3
        assert all(r["subject_id"] == missao["id"] for r in registros)

    def test_ninguem_altera_nem_apaga_a_trilha(
        self, client: TestClient, admin_token: dict, missao_pronta
    ) -> None:
        """Não há rota de escrita, e é assim que se pretende: auditoria que pode
        ser alterada não é auditoria."""
        _, missao = missao_pronta
        registros = trilha(client, admin_token, subject_id=missao["id"])
        alvo = registros[0]["id"]

        assert client.patch(f"/v1/audit/{alvo}", json={"action": "x"}, headers=admin_token
                            ).status_code in (404, 405)
        assert client.delete(f"/v1/audit/{alvo}", headers=admin_token).status_code in (404, 405)


class TestARotaFicaRegistrada:
    """A pergunta que faltava: *que percurso* foi aprovado e mandado.

    A trilha registrava que uma missão nasceu e que um comando saiu, mas não o
    conteúdo de nenhum dos dois. Numa apuração isso deixa o buraco exato onde
    mora a dúvida — "o robô passou onde devia?" — porque a resposta estava só na
    tabela de missões, que é mutável e some com a missão.
    """

    def test_a_criacao_registra_o_que_foi_criado(
        self, client: TestClient, admin_token: dict, missao_pronta
    ) -> None:
        _, missao = missao_pronta
        criacao = next(
            r
            for r in acoes_de(client, admin_token, missao["id"])
            if r["action"] == "mission.created"
        )
        carga = criacao["payload"]
        assert carga["kind"] == "scout"
        assert carga["field_id"] and carga["device_id"] and carga["farm_id"]

    def test_a_criacao_registra_a_rota_planejada(
        self, client: TestClient, admin_token: dict, missao_pronta
    ) -> None:
        _, missao = missao_pronta
        criacao = next(
            r
            for r in acoes_de(client, admin_token, missao["id"])
            if r["action"] == "mission.created"
        )
        carga = criacao["payload"]
        assert carga["waypoints"] > 0, "a rota planejada não ficou na trilha"
        assert carga["segments"] and carga["path_length_m"] > 0
        assert len(carga["route_digest"]) == 64, "o resumo da rota não é um sha256"

    def test_o_resumo_da_rota_muda_quando_a_rota_muda(
        self, client: TestClient, admin_token: dict, operator_token: dict, demo: dict
    ) -> None:
        """É o que torna o resumo útil: duas rotas diferentes não colidem.

        Se o resumo fosse igual para percursos diferentes, ele provaria nada —
        seria um carimbo, não uma impressão digital.
        """
        rover = provision(client, admin_token, "ROVER_SCOUT_V1", "P-ROTA-1", demo["farm_id"])
        send_telemetry(rover, battery_percent=95.0)

        resumos = []
        for largura in (2.0, 6.0):
            resposta = client.post(
                "/v1/missions",
                json={
                    "kind": "scout",
                    "field_id": demo["field_id"],
                    "device_id": rover.device_id,
                    "plan": {"swath_m": largura},
                },
                headers=operator_token,
            )
            assert resposta.status_code == 201, resposta.text
            criacao = next(
                r
                for r in acoes_de(client, admin_token, resposta.json()["id"])
                if r["action"] == "mission.created"
            )
            resumos.append(criacao["payload"]["route_digest"])

        assert resumos[0] != resumos[1], "faixas diferentes deram o mesmo resumo de rota"

    def test_o_comando_registra_a_assinatura_e_a_rota(
        self, client: TestClient, admin_token: dict, operator_token: dict, missao_pronta
    ) -> None:
        """Sem a assinatura, a trilha diz que um comando saiu; com ela, diz qual.

        ``mission.signature`` guarda só o último, então um abortar apaga o
        executar — e a linha da trilha é o único lugar onde o comando de verdade
        sobrevive ao seguinte.
        """
        _, missao = missao_pronta
        autorizou = client.post(
            f"/v1/missions/{missao['id']}/authorize", headers=operator_token
        )
        if autorizou.status_code != 200:
            pytest.skip("a camada de segurança barrou o despacho neste ambiente")
        despachou = client.post(f"/v1/missions/{missao['id']}/dispatch", headers=operator_token)
        assert despachou.status_code == 200, despachou.text

        comandos = trilha(client, admin_token, action="device.command_issued")
        deste = next(c for c in comandos if c["payload"]["mission_id"] == missao["id"])
        carga = deste["payload"]
        assert carga["signature"], "o comando registrado não guardou a assinatura"
        assert carga["signature"] == despachou.json()["signature"], "assinou outra coisa"
        assert carga["route_digest"], "o comando registrado não guardou a rota"
        assert carga["waypoints"] > 0
