"""Sessões revogáveis: o servidor passa a ter a última palavra sobre um token.

Antes destes testes existirem, o token de sessão era um papel assinado — valia
até vencer, e nada podia desdizê-lo. A pergunta que este arquivo responde é a
do notebook roubado: **dá para cortar o acesso agora?**

Cada teste aqui cobre um caminho pelo qual alguém corta acesso: a própria
pessoa saindo, a própria pessoa saindo de tudo, a troca de senha, a redefinição
por administrador e o desligamento. Um caminho que não derrube de verdade é
pior do que não existir, porque dá a impressão de ter resolvido.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def entrar(client: TestClient, email: str, senha: str = "valtexa-demo-2026") -> dict:
    """Um login novo — cada chamada abre uma sessão própria."""
    resposta = client.post("/v1/auth/login", json={"email": email, "password": senha})
    assert resposta.status_code == 200, resposta.text
    corpo = resposta.json()
    return {
        "Authorization": f"Bearer {corpo['access_token']}",
        "X-Tenant-Id": corpo["tenant_id"],
    }


class TestAListaDeAparelhos:
    def test_entrar_abre_uma_sessao_visivel(
        self, client: TestClient, admin_token: dict, demo: dict
    ) -> None:
        sessoes = client.get("/v1/auth/sessions", headers=admin_token).json()
        assert sessoes, "entrou e não apareceu sessão nenhuma"
        assert sum(1 for s in sessoes if s["current"]) == 1, "nenhuma ou mais de uma 'atual'"

    def test_cada_login_e_uma_sessao(
        self, client: TestClient, admin_token: dict, demo: dict
    ) -> None:
        """Dois navegadores são duas linhas. Se fossem uma, derrubar um
        derrubaria o outro — e a lista não serviria para nada."""
        antes = len(client.get("/v1/auth/sessions", headers=admin_token).json())
        entrar(client, "admin@valtexa.dev")
        depois = client.get("/v1/auth/sessions", headers=admin_token).json()
        assert len(depois) == antes + 1

    def test_a_lista_nao_devolve_o_token(
        self, client: TestClient, admin_token: dict, demo: dict
    ) -> None:
        """Devolver o token seria espalhar a credencial por mais um lugar."""
        sessoes = client.get("/v1/auth/sessions", headers=admin_token).json()
        texto = str(sessoes).lower()
        assert "access_token" not in texto
        assert admin_token["Authorization"].split(" ", 1)[1] not in str(sessoes)

    def test_eu_nao_vejo_sessao_de_outra_pessoa(
        self, client: TestClient, admin_token: dict, operator_token: dict, demo: dict
    ) -> None:
        minhas = client.get("/v1/auth/sessions", headers=operator_token).json()
        do_admin = client.get("/v1/auth/sessions", headers=admin_token).json()
        assert {s["id"] for s in minhas}.isdisjoint({s["id"] for s in do_admin})


class TestDerrubarUmAparelho:
    def test_derrubar_uma_sessao_corta_o_acesso_dela_na_hora(
        self, client: TestClient, admin_token: dict, demo: dict
    ) -> None:
        """O teste que dá sentido a todos os outros: o token derrubado para de
        funcionar imediatamente, e não quando vencer."""
        outro = entrar(client, "admin@valtexa.dev")
        assert client.get("/v1/farms", headers=outro).status_code == 200

        alvo = next(
            s for s in client.get("/v1/auth/sessions", headers=outro).json() if s["current"]
        )
        derrubou = client.delete(f"/v1/auth/sessions/{alvo['id']}", headers=admin_token)
        assert derrubou.status_code == 200, derrubou.text

        recusa = client.get("/v1/farms", headers=outro)
        assert recusa.status_code == 401, "a sessão derrubada continuou entrando"
        assert "encerrada" in recusa.json()["detail"].lower()

    def test_derrubar_um_aparelho_nao_derruba_os_outros(
        self, client: TestClient, admin_token: dict, demo: dict
    ) -> None:
        outro = entrar(client, "admin@valtexa.dev")
        alvo = next(
            s for s in client.get("/v1/auth/sessions", headers=outro).json() if s["current"]
        )
        client.delete(f"/v1/auth/sessions/{alvo['id']}", headers=admin_token)

        assert client.get("/v1/farms", headers=admin_token).status_code == 200

    def test_nao_derrubo_sessao_de_outra_pessoa_por_esta_rota(
        self, client: TestClient, admin_token: dict, operator_token: dict, demo: dict
    ) -> None:
        """404 e não 403: dizer "existe, mas não é sua" entregaria a existência
        de sessões alheias a quem ficasse adivinhando identificadores."""
        do_operador = client.get("/v1/auth/sessions", headers=operator_token).json()[0]
        resposta = client.delete(f"/v1/auth/sessions/{do_operador['id']}", headers=admin_token)
        assert resposta.status_code == 404
        assert client.get("/v1/farms", headers=operator_token).status_code == 200

    def test_derrubar_duas_vezes_nao_e_erro(
        self, client: TestClient, admin_token: dict, demo: dict
    ) -> None:
        outro = entrar(client, "admin@valtexa.dev")
        alvo = next(
            s for s in client.get("/v1/auth/sessions", headers=outro).json() if s["current"]
        )
        primeira = client.delete(f"/v1/auth/sessions/{alvo['id']}", headers=admin_token)
        segunda = client.delete(f"/v1/auth/sessions/{alvo['id']}", headers=admin_token)
        assert primeira.json()["revoked"] == 1
        assert segunda.status_code == 200 and segunda.json()["revoked"] == 0


class TestSairDeTudo:
    def test_logout_derruba_todas_inclusive_a_atual(
        self, client: TestClient, admin_token: dict, demo: dict
    ) -> None:
        """O botão de quem perdeu o celular: não adianta derrubar uma a uma
        quando não se sabe quais existem."""
        outro = entrar(client, "admin@valtexa.dev")
        resposta = client.post("/v1/auth/logout", headers=admin_token)
        assert resposta.status_code == 200
        assert resposta.json()["revoked"] >= 2

        assert client.get("/v1/farms", headers=admin_token).status_code == 401
        assert client.get("/v1/farms", headers=outro).status_code == 401


class TestTrocaDeSenha:
    def test_trocar_a_senha_derruba_os_outros_aparelhos(
        self, client: TestClient, admin_token: dict, demo: dict
    ) -> None:
        """É o motivo pelo qual se troca a senha às pressas: alguém entrou.
        Trocar a senha sem cortar o acesso já aberto não resolveria nada."""
        invasor = entrar(client, "admin@valtexa.dev")

        resposta = client.post(
            "/v1/auth/password",
            json={"current_password": "valtexa-demo-2026", "new_password": "senha-nova-2026"},
            headers=admin_token,
        )
        assert resposta.status_code == 200, resposta.text
        assert client.get("/v1/farms", headers=invasor).status_code == 401

    def test_quem_troca_a_senha_continua_dentro(
        self, client: TestClient, admin_token: dict, demo: dict
    ) -> None:
        """Ser deslogado pelo próprio ato de se proteger é o tipo de atrito que
        faz as pessoas não trocarem a senha."""
        client.post(
            "/v1/auth/password",
            json={"current_password": "valtexa-demo-2026", "new_password": "senha-nova-2026"},
            headers=admin_token,
        )
        assert client.get("/v1/farms", headers=admin_token).status_code == 200

    def test_a_redefinicao_por_administrador_derruba_tudo_do_alvo(
        self, client: TestClient, admin_token: dict, demo: dict
    ) -> None:
        """Aqui quem redefine é outra pessoa, e o caso típico é alguém que
        perdeu o acesso ou foi desligado. Preservar uma sessão seria preservar
        exatamente a que se quer cortar."""
        do_operador = entrar(client, "operador@valtexa.dev")
        operador_id = client.get("/v1/auth/me", headers=do_operador).json()["id"]

        resposta = client.post(
            f"/v1/users/{operador_id}/password",
            json={"new_password": "outra-senha-2026"},
            headers=admin_token,
        )
        assert resposta.status_code == 200, resposta.text
        assert client.get("/v1/farms", headers=do_operador).status_code == 401


class TestDesligamento:
    def test_administrador_desconecta_um_usuario_do_cliente(
        self, client: TestClient, admin_token: dict, demo: dict
    ) -> None:
        """O que faltava para um desligamento valer na hora. Antes, o token no
        navegador da pessoa continuava servindo por até doze horas."""
        do_operador = entrar(client, "operador@valtexa.dev")
        operador_id = client.get("/v1/auth/me", headers=do_operador).json()["id"]

        resposta = client.delete(f"/v1/users/{operador_id}/sessions", headers=admin_token)
        assert resposta.status_code == 200, resposta.text
        assert resposta.json()["revoked"] >= 1
        assert client.get("/v1/farms", headers=do_operador).status_code == 401

    def test_operador_nao_desconecta_ninguem(
        self, client: TestClient, operator_token: dict, admin_token: dict, demo: dict
    ) -> None:
        """Encerrar a sessão de alguém é ato administrativo."""
        admin_id = client.get("/v1/auth/me", headers=admin_token).json()["id"]
        resposta = client.delete(f"/v1/users/{admin_id}/sessions", headers=operator_token)
        assert resposta.status_code == 403
        assert client.get("/v1/farms", headers=admin_token).status_code == 200


class TestATrilha:
    def test_derrubar_uma_sessao_fica_na_auditoria(
        self, client: TestClient, admin_token: dict, demo: dict
    ) -> None:
        """Cortar o acesso de alguém é ato administrativo, e ato administrativo
        sem nome e hora não se apura."""
        do_operador = entrar(client, "operador@valtexa.dev")
        operador_id = client.get("/v1/auth/me", headers=do_operador).json()["id"]
        client.delete(f"/v1/users/{operador_id}/sessions", headers=admin_token)

        trilha = client.get(
            "/v1/audit", params={"action": "session.revoked", "limit": 20}, headers=admin_token
        ).json()
        assert trilha, "a sessão caiu sem deixar linha na trilha"
        registro = trilha[0]
        assert registro["subject_id"] == operador_id
        assert registro["actor_type"] == "user"
        assert registro["reason"], "a trilha não diz por que a sessão caiu"


class TestTokenSemSessao:
    def test_token_antigo_sem_sid_e_recusado(
        self, client: TestClient, admin_token: dict, demo: dict
    ) -> None:
        """Os tokens emitidos antes desta tabela existir não têm sessão para
        conferir. Tolerá-los manteria vivas justamente as que não se alcança."""
        from valtexa.security import tokens

        user_id = client.get("/v1/auth/me", headers=admin_token).json()["id"]
        antigo, _ = tokens.issue("user", user_id, admin_token["X-Tenant-Id"])

        resposta = client.get(
            "/v1/farms",
            headers={
                "Authorization": f"Bearer {antigo}",
                "X-Tenant-Id": admin_token["X-Tenant-Id"],
            },
        )
        assert resposta.status_code == 401
