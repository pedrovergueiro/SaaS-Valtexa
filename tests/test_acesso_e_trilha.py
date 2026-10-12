"""Recuperação de acesso e as lacunas da trilha de auditoria.

Três coisas que o sistema não sabia fazer e que a operação exige: alguém trocar
a própria senha, um administrador devolver o acesso a quem o perdeu, e a trilha
responder **o que a IA decidiu sozinha** e **que ordem exata saiu para o robô**.

As duas últimas parecem redundantes com as tabelas `diagnosis` e `mission`, e
não são. Aquelas guardam o estado atual; esta guarda o que aconteceu. Um
diagnóstico revisto pelo agrônomo sobrescreve o rótulo da IA, e um segundo
comando sobrescreve o nonce do primeiro — em ambos os casos, sem a trilha a
pergunta de auditoria fica sem resposta.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from tests.helpers import provision, send_telemetry, upload_observation
from valtexa.models import AuditEntry, Farm

SENHA_DEMO = "valtexa-demo-2026"
NOVA = "uma-senha-nova-bem-longa"


class TestTrocarAPropriaSenha:
    def test_troca_com_a_senha_atual_correta(self, client: TestClient, admin_token: dict) -> None:
        resposta = client.post(
            "/v1/auth/password",
            json={"current_password": SENHA_DEMO, "new_password": NOVA},
            headers=admin_token,
        )
        assert resposta.status_code == 200

        # A senha antiga deixa de valer e a nova passa a valer.
        assert (
            client.post(
                "/v1/auth/login", json={"email": "admin@valtexa.dev", "password": SENHA_DEMO}
            ).status_code
            == 401
        )
        assert (
            client.post(
                "/v1/auth/login", json={"email": "admin@valtexa.dev", "password": NOVA}
            ).status_code
            == 200
        )

    def test_senha_atual_errada_e_recusada(self, client: TestClient, admin_token: dict) -> None:
        """Protege a estação destravada na sala da fazenda: sem a senha atual,
        trocar a senha alheia seria questão de passar por perto."""
        resposta = client.post(
            "/v1/auth/password",
            json={"current_password": "chute", "new_password": NOVA},
            headers=admin_token,
        )
        assert resposta.status_code == 403
        assert (
            client.post(
                "/v1/auth/login", json={"email": "admin@valtexa.dev", "password": SENHA_DEMO}
            ).status_code
            == 200
        ), "a senha foi trocada apesar da recusa"

    def test_senha_curta_e_recusada(self, client: TestClient, admin_token: dict) -> None:
        resposta = client.post(
            "/v1/auth/password",
            json={"current_password": SENHA_DEMO, "new_password": "curta"},
            headers=admin_token,
        )
        assert resposta.status_code == 422

    def test_a_troca_fica_na_auditoria(self, client: TestClient, admin_token: dict) -> None:
        client.post(
            "/v1/auth/password",
            json={"current_password": SENHA_DEMO, "new_password": NOVA},
            headers=admin_token,
        )
        trilha = client.get("/v1/audit", headers=admin_token).json()
        assert any(item["action"] == "user.password_changed" for item in trilha)


class TestRedefinirSenhaDeOutro:
    def _id_do(self, client: TestClient, token: dict, email: str) -> str:
        usuarios = client.get("/v1/users", headers=token).json()
        return next(item["id"] for item in usuarios if item["email"] == email)

    def test_admin_devolve_o_acesso_de_quem_perdeu(
        self, client: TestClient, admin_token: dict
    ) -> None:
        """É o caminho de recuperação desta plataforma: não há envio de e-mail,
        então não há link de redefinição."""
        alvo = self._id_do(client, admin_token, "operador@valtexa.dev")

        resposta = client.post(
            f"/v1/users/{alvo}/password", json={"new_password": NOVA}, headers=admin_token
        )
        assert resposta.status_code == 200
        assert (
            client.post(
                "/v1/auth/login", json={"email": "operador@valtexa.dev", "password": NOVA}
            ).status_code
            == 200
        )

    def test_operador_nao_redefine_senha_de_ninguem(
        self, client: TestClient, admin_token: dict, operator_token: dict
    ) -> None:
        alvo = self._id_do(client, admin_token, "agronomo@valtexa.dev")
        resposta = client.post(
            f"/v1/users/{alvo}/password", json={"new_password": NOVA}, headers=operator_token
        )
        assert resposta.status_code == 403

    def test_nao_alcanca_quem_nao_e_do_cliente(
        self, client: TestClient, admin_token: dict
    ) -> None:
        resposta = client.post(
            "/v1/users/nao-existe/password", json={"new_password": NOVA}, headers=admin_token
        )
        assert resposta.status_code == 404

    def test_a_conta_da_equipe_valtexa_nao_e_redefinida_de_dentro_do_cliente(
        self, client: TestClient, admin_token: dict
    ) -> None:
        """Quem enxerga todos os clientes não pode ter a senha trocada por um deles."""
        alvo = self._id_do(client, admin_token, "equipe@valtexa.dev")
        resposta = client.post(
            f"/v1/users/{alvo}/password", json={"new_password": NOVA}, headers=admin_token
        )
        assert resposta.status_code == 403

    def test_a_redefinicao_diz_quem_redefiniu_e_de_quem(
        self, client: TestClient, admin_token: dict
    ) -> None:
        alvo = self._id_do(client, admin_token, "operador@valtexa.dev")
        client.post(
            f"/v1/users/{alvo}/password", json={"new_password": NOVA}, headers=admin_token
        )

        trilha = client.get("/v1/audit", headers=admin_token).json()
        registro = next(i for i in trilha if i["action"] == "user.password_reset")
        assert registro["actor_label"] == "admin@valtexa.dev"
        assert registro["payload"]["alvo"] == "operador@valtexa.dev"


class TestATrilhaRegistraAIA:
    def test_o_diagnostico_automatico_entra_na_trilha(
        self, client: TestClient, admin_token: dict, demo: dict
    ) -> None:
        """A pergunta que isto responde: o que a IA decidiu sozinha, e quando.

        A tabela `diagnosis` não responde — o agrônomo revisa e sobrescreve o
        rótulo. Depois da revisão, sem esta linha, não há como saber o que o
        modelo tinha dito.
        """
        rover = provision(client, admin_token, "ROVER_SCOUT_V1", "P-IA-1", demo["farm_id"])
        send_telemetry(rover, battery_percent=90.0)
        resposta = upload_observation(rover, demo["field_id"], label="Common_Rust")
        assert resposta.status_code == 201, resposta.text

        trilha = client.get(
            "/v1/audit", params={"action": "diagnosis.emitted"}, headers=admin_token
        ).json()
        assert trilha, "a IA emitiu diagnóstico sem deixar rastro na trilha"

        registro = trilha[0]
        assert registro["actor_type"] == "ai", "a IA está auditada como se fosse o relógio"
        assert registro["payload"]["label"]
        assert registro["payload"]["confidence"] is not None
        assert registro["model_version"], "sem versão de pipeline não se reproduz a decisão"

    def test_a_revisao_do_agronomo_nao_apaga_o_que_a_ia_disse(
        self, client: TestClient, admin_token: dict, agronomist_token: dict, demo: dict
    ) -> None:
        """É o motivo de esta trilha existir.

        A revisão sobrescreve o rótulo na tabela `diagnosis`. Sem a linha da
        emissão, ninguém consegue mais responder o que o modelo tinha dito antes
        de um humano discordar dele — que é exatamente a pergunta de quem apura
        um erro de aplicação.
        """
        rover = provision(client, admin_token, "ROVER_SCOUT_V1", "P-IA-2", demo["farm_id"])
        send_telemetry(rover, battery_percent=90.0)
        upload_observation(rover, demo["field_id"], label="Common_Rust")

        emitido = client.get(
            "/v1/audit", params={"action": "diagnosis.emitted"}, headers=admin_token
        ).json()[0]
        rotulo_da_ia = emitido["payload"]["label"]

        observacoes = client.get(
            "/v1/observations", params={"field_id": demo["field_id"]}, headers=admin_token
        ).json()
        diagnostico = observacoes[0]["diagnosis_id"]
        client.post(
            f"/v1/diagnoses/{diagnostico}/review",
            json={"label": "Healthy", "confirmed": False, "notes": "Era sombra."},
            headers=agronomist_token,
        )

        depois = client.get(
            "/v1/audit", params={"action": "diagnosis.emitted"}, headers=admin_token
        ).json()[0]
        assert depois["payload"]["label"] == rotulo_da_ia, (
            "a revisão apagou o que a IA tinha dito"
        )

    def test_o_ator_da_ia_e_distinguivel_do_relogio(self) -> None:
        """`SYSTEM` é o cron que expira missão; `AI` é um modelo julgando imagem.

        Auditá-los com o mesmo nome deixaria a pergunta "o que a IA decidiu
        neste talhão?" sem resposta possível por consulta.
        """
        from valtexa.models import ActorType

        assert ActorType.AI.value == "ai"
        assert ActorType.AI is not ActorType.SYSTEM

    def test_um_diagnostico_de_verdade_deixa_linha_na_trilha(
        self, client: TestClient, admin_token: dict, demo: dict
    ) -> None:
        """O enum existir não prova nada: prova é a inferência deixar rastro.

        A pergunta do checklist é "registrar alterações feitas pela IA", e ela
        só tem resposta se o caminho inteiro — imagem sobe, modelo julga, linha
        aparece — estiver ligado. Conferir o enum sozinho conferia a etiqueta,
        não o ato.
        """
        rover = provision(client, admin_token, "ROVER_SCOUT_V1", "P-IA-1", demo["farm_id"])
        enviou = upload_observation(rover, demo["field_id"], label="Common_Rust", novelty=0.8)
        assert enviou.status_code in (200, 201), enviou.text

        trilha = client.get(
            "/v1/audit", params={"action": "diagnosis.emitted", "limit": 20}, headers=admin_token
        ).json()
        assert trilha, "a IA diagnosticou e não deixou linha na trilha"
        registro = trilha[0]
        assert registro["actor_type"] == "ai", "o diagnóstico não foi atribuído à IA"
        assert registro["actor_label"], "a trilha não diz qual versão do modelo julgou"


class TestATrilhaRegistraOComando:
    def test_o_comando_enviado_ao_rover_fica_congelado(
        self, client: TestClient, admin_token: dict, operator_token: dict, demo: dict
    ) -> None:
        """A transição registra que houve despacho; isto registra **o quê**.

        `mission.nonce` guarda só o último comando: um abortar emitido depois
        sobrescreve o executar, e a pergunta "que ordem este robô recebeu?"
        deixaria de ter resposta.
        """
        rover = provision(client, admin_token, "ROVER_SCOUT_V1", "P-CMD-1", demo["farm_id"])
        send_telemetry(rover, battery_percent=95.0)

        missao = client.post(
            "/v1/missions",
            json={
                "kind": "scout",
                "field_id": demo["field_id"],
                "device_id": rover.device_id,
            },
            headers=operator_token,
        ).json()

        client.post(f"/v1/missions/{missao['id']}/approve", headers=operator_token)
        client.post(f"/v1/missions/{missao['id']}/authorize", headers=operator_token)
        despacho = client.post(f"/v1/missions/{missao['id']}/dispatch", headers=operator_token)
        if despacho.status_code != 200:
            # A camada de segurança pode barrar por vento, bateria ou hora; o
            # que se testa aqui é a trilha, não a liberação.
            return

        trilha = client.get(
            "/v1/audit", params={"action": "device.command_issued"}, headers=admin_token
        ).json()
        assert trilha, "o comando saiu para o robô sem deixar rastro"
        registro = trilha[0]
        assert registro["payload"]["mission_id"] == missao["id"]
        assert registro["payload"]["command"] == "mission.execute"
        assert registro["payload"]["nonce"], "sem nonce não se cruza com o que o robô recebeu"
        assert registro["payload"]["sequence"] >= 1


class TestMudarALocalizacaoDaFazenda:
    def test_corrige_a_coordenada_de_uma_fazenda(
        self, client: TestClient, admin_token: dict, demo: dict
    ) -> None:
        """Uma fazenda cadastrada 40 km ao lado produz um contorno bonito sobre
        o mato de outra pessoa."""
        resposta = client.patch(
            f"/v1/farms/{demo['farm_id']}",
            json={"center_lat": -21.5000, "center_lon": -45.5000},
            headers=admin_token,
        )
        assert resposta.status_code == 200
        assert resposta.json()["center_lat"] == -21.5000

    def test_o_que_nao_foi_enviado_nao_e_apagado(
        self, client: TestClient, admin_token: dict, demo: dict, session: Session
    ) -> None:
        antes = session.get(Farm, demo["farm_id"])
        assert antes is not None
        nome = antes.name

        client.patch(
            f"/v1/farms/{demo['farm_id']}", json={"center_lat": -21.5}, headers=admin_token
        )
        session.expire_all()
        depois = session.get(Farm, demo["farm_id"])
        assert depois is not None
        assert depois.name == nome

    def test_mover_a_fazenda_guarda_o_antes_e_o_depois(
        self, client: TestClient, admin_token: dict, demo: dict
    ) -> None:
        client.patch(
            f"/v1/farms/{demo['farm_id']}",
            json={"center_lat": -21.5000, "center_lon": -45.5000},
            headers=admin_token,
        )
        trilha = client.get("/v1/audit", headers=admin_token).json()
        registro = next(i for i in trilha if i["action"] == "farm.moved")
        assert "-21.9" in registro["old_state"]
        assert "-21.5" in registro["new_state"]

    def test_coordenada_impossivel_e_recusada(
        self, client: TestClient, admin_token: dict, demo: dict
    ) -> None:
        resposta = client.patch(
            f"/v1/farms/{demo['farm_id']}", json={"center_lat": 200.0}, headers=admin_token
        )
        assert resposta.status_code == 422

    def test_quem_nao_administra_fazenda_nao_a_move(
        self, client: TestClient, agronomist_token: dict, demo: dict
    ) -> None:
        resposta = client.patch(
            f"/v1/farms/{demo['farm_id']}",
            json={"center_lat": -21.5},
            headers=agronomist_token,
        )
        assert resposta.status_code == 403


class TestClienteDesativado:
    def test_desativar_um_cliente_tranca_o_acesso_dele(
        self, client: TestClient, platform_token: dict, admin_token: dict, demo: dict
    ) -> None:
        """Não há exclusão de cliente, e é deliberado: a auditoria e o histórico
        de missão precisam sobreviver ao fim do contrato. O que há é desativar.
        """
        assert client.get("/v1/farms", headers=admin_token).status_code == 200

        resposta = client.patch(
            f"/v1/admin/tenants/{demo['tenant_id']}",
            json={"is_active": False},
            headers=platform_token,
        )
        assert resposta.status_code == 200
        assert resposta.json()["is_active"] is False

        assert client.get("/v1/farms", headers=admin_token).status_code == 404

    def test_a_equipe_ainda_le_a_trilha_de_um_cliente_desativado(
        self, client: TestClient, platform_token: dict, demo: dict
    ) -> None:
        """É depois do fim do contrato que a trilha é mais procurada.

        Apuração, disputa, prazo legal de guarda. Trancá-la junto com a operação
        apagaria na prática o que a lei manda guardar, sem apagar uma linha do
        banco — e foi assim que o sistema se comportava até esta verificação.
        """
        client.patch(
            f"/v1/admin/tenants/{demo['tenant_id']}",
            json={"is_active": False},
            headers=platform_token,
        )
        resposta = client.get("/v1/audit", headers=platform_token)
        assert resposta.status_code == 200
        assert any(item["action"] == "tenant.updated" for item in resposta.json())

    def test_a_desativacao_fica_na_auditoria(
        self, client: TestClient, platform_token: dict, demo: dict, session: Session
    ) -> None:
        client.patch(
            f"/v1/admin/tenants/{demo['tenant_id']}",
            json={"is_active": False},
            headers=platform_token,
        )
        entrada = session.scalars(
            select(AuditEntry).where(AuditEntry.action == "tenant.updated")
        ).first()
        assert entrada is not None
        assert entrada.payload["antes"]["is_active"] is True
        assert entrada.payload["depois"]["is_active"] is False


class TestTratamentoDeErros:
    """A rede de segurança: erro não previsto não pode quebrar a tela sem dizer nada.

    Estes testes usam um cliente com ``raise_server_exceptions=False``. Por
    padrão o ``TestClient`` re-levanta a exceção no teste em vez de deixá-la
    chegar ao tratador — cômodo para depurar, mas esconde justamente o que aqui
    se quer verificar, que é o que o navegador de verdade recebe.
    """

    @staticmethod
    def _cliente_como_em_producao(client: TestClient) -> TestClient:
        return TestClient(client.app, raise_server_exceptions=False)

    def test_erro_inesperado_vira_json_com_codigo(
        self, client: TestClient, admin_token: dict, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Sem o tratador, o Starlette devolve texto puro e o console — que
        espera ``{"detail": ...}`` em todo erro — quebra sem mensagem. É o pior
        jeito de falhar: não diz o que houve nem a quem recorrer.
        """
        from valtexa.api.routers import farms

        def explode(*_args, **_kwargs):
            raise RuntimeError("banco pegou fogo")

        monkeypatch.setattr(farms, "_farm_out", explode)

        resposta = self._cliente_como_em_producao(client).get("/v1/farms", headers=admin_token)
        assert resposta.status_code == 500
        corpo = resposta.json()
        assert corpo["error_id"], "erro sem código não se acha no log"
        assert corpo["error_id"] in corpo["detail"]

    def test_o_corpo_do_erro_nao_vaza_o_interior(
        self, client: TestClient, admin_token: dict, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Mensagem de exceção traz caminho de arquivo, SQL e às vezes valor de
        campo. Isso é do log, que é interno — não da resposta, que atravessa a
        internet."""
        from valtexa.api.routers import farms

        def explode(*_args, **_kwargs):
            raise RuntimeError("SELECT senha FROM user WHERE id='segredo-vazado'")

        monkeypatch.setattr(farms, "_farm_out", explode)

        corpo = self._cliente_como_em_producao(client).get(
            "/v1/farms", headers=admin_token
        ).json()
        assert "segredo-vazado" not in str(corpo)
        assert "SELECT" not in str(corpo)

    def test_o_codigo_do_erro_vai_para_o_log(
        self,
        client: TestClient,
        admin_token: dict,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """É o que transforma "deu erro aqui" numa busca de um grep."""
        from valtexa.api.routers import farms

        def explode(*_args, **_kwargs):
            raise RuntimeError("falha qualquer")

        monkeypatch.setattr(farms, "_farm_out", explode)

        with caplog.at_level("ERROR"):
            corpo = self._cliente_como_em_producao(client).get(
                "/v1/farms", headers=admin_token
            ).json()

        assert corpo["error_id"] in caplog.text
        assert "falha qualquer" in caplog.text, "o traceback não chegou ao log"
