"""O fluxo ao vivo: o servidor avisa em vez de o console perguntar.

Quinze segundos é muito tempo olhando uma tela que diz "em curso" para uma
máquina que já parou na lavoura. Este arquivo garante três coisas, nesta ordem
de importância:

1. **O fluxo não atravessa clientes.** Num fluxo aberto o servidor fala sem ser
   perguntado, então um filtro errado vaza continuamente em vez de uma vez.
2. **Chega evento de verdade**, e não só a conexão abrir.
3. **Reconectar não repete a tela inteira** nem deixa buraco.

Os testes exercitam o gerador ``_fluxo`` diretamente, e não por HTTP. A razão é
do ferramental, não do desenho: o ``TestClient`` do Starlette consome uma
resposta em fluxo até o fim antes de devolver o controle, e uma conexão SSE só
termina quando o servidor a encerra — o que trava a suíte em vez de falhar. O
contrato HTTP (cabeçalhos, 401, limite de conexões) está conferido na auditoria
ao vivo, contra o servidor de verdade, que é onde ele tem sentido.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from tests.helpers import provision, send_telemetry
from valtexa.api.routers import stream


@pytest.fixture(autouse=True)
def fluxo_curto(monkeypatch: pytest.MonkeyPatch):
    """Encurta a conexão ao vivo para a duração de um teste.

    Em produção o fluxo vive quinze minutos e o navegador reconecta. Num teste
    isso seria quinze minutos de espera por asserção.
    """
    monkeypatch.setattr(
        stream,
        "settings",
        stream.settings.model_copy(
            update={"stream_max_seconds": 1, "stream_poll_seconds": 0.05}
        ),
    )


def colhe(tenant_id: str, desde: datetime) -> list[dict]:
    """Roda o fluxo até ele se fechar e devolve os eventos que saíram."""

    async def _correr() -> list[str]:
        return [quadro async for quadro in stream._fluxo(tenant_id, desde, 1)]

    return _decodifica(asyncio.run(_correr()))


def _decodifica(quadros: list[str]) -> list[dict]:
    """Os eventos de uma lista de quadros SSE, já decodificados.

    Ignora comentários (`:` no início), que são batimento de conexão e não
    evento — contá-los faria um teste passar por atividade de keep-alive.
    """
    saida: list[dict] = []
    for bloco in quadros:
        nome = None
        dados = None
        ident = None
        for linha in bloco.splitlines():
            if linha.startswith("event: "):
                nome = linha[7:]
            elif linha.startswith("data: "):
                dados = json.loads(linha[6:])
            elif linha.startswith("id: "):
                ident = linha[4:]
        if nome and dados is not None:
            saida.append({"event": nome, "_id": ident, **dados})
    return saida


class TestAConexao:
    def test_o_fluxo_se_fecha_dizendo_de_onde_retomar(
        self, client: TestClient, demo: dict
    ) -> None:
        """Sem o `after` no quadro final, o console teria de escolher entre
        repetir eventos e perder os do intervalo entre fechar e abrir."""
        eventos = colhe(demo["tenant_id"], datetime.now(UTC))
        assert eventos, "o fluxo abriu e não disse nada"
        assert eventos[-1]["event"] == "stream.end"
        assert eventos[-1]["after"]

    def test_o_fluxo_se_encerra_e_pede_reconexao(
        self, client: TestClient, demo: dict
    ) -> None:
        """Reciclar a conexão é o que impede uma aba esquecida de segurar
        recurso para sempre — mas só serve se o cliente souber voltar."""
        eventos = colhe(demo["tenant_id"], datetime.now(UTC))
        assert eventos[-1]["event"] == "stream.end"
        assert eventos[-1]["reason"]

    def test_sem_token_nao_ha_fluxo(self, client: TestClient) -> None:
        assert client.get("/v1/stream").status_code == 401

    def test_a_conexao_e_devolvida_ao_contador_no_fim(
        self, client: TestClient, demo: dict
    ) -> None:
        """Um contador que só sobe transformaria o limite de conexões numa
        contagem regressiva até o 503 permanente."""
        antes = stream._conectados
        colhe(demo["tenant_id"], datetime.now(UTC))
        assert stream._conectados == antes


class TestOEscopoDeCliente:
    def test_o_fluxo_nao_entrega_evento_de_outro_cliente(
        self, client: TestClient, admin_token: dict, platform_token: dict, demo: dict
    ) -> None:
        """A regra que mais importa aqui: num fluxo aberto, o filtro errado vaza
        continuamente em vez de uma vez."""
        criado = client.post(
            "/v1/admin/tenants",
            json={"tenant": {"name": "Sítio do Fluxo", "slug": "sitio-do-fluxo"}},
            headers=platform_token,
        )
        assert criado.status_code == 201, criado.text
        vizinho = criado.json()["tenant"]["id"]

        # Eventos de verdade no cliente da demonstração.
        rover = provision(client, admin_token, "ROVER_SCOUT_V1", "P-SSE-1", demo["farm_id"])
        send_telemetry(rover, battery_percent=90.0)

        antigo = datetime(2020, 1, 1, tzinfo=UTC)
        assert {e["event"] for e in colhe(demo["tenant_id"], antigo)} != {"stream.end"}, (
            "o cliente da demonstração não gerou evento nenhum — o teste de "
            "vazamento passaria por vacuidade"
        )
        nomes = {e["event"] for e in colhe(vizinho, antigo)}
        assert nomes <= {"stream.end"}, f"vazou evento de outro cliente: {nomes}"


class TestOsEventos:
    def test_uma_missao_criada_aparece_no_fluxo(
        self, client: TestClient, admin_token: dict, operator_token: dict, demo: dict
    ) -> None:
        """A prova de que o fluxo entrega evento, e não só abre conexão."""
        rover = provision(client, admin_token, "ROVER_SCOUT_V1", "P-SSE-2", demo["farm_id"])
        send_telemetry(rover, battery_percent=95.0)
        marco = datetime.now(UTC)

        criada = client.post(
            "/v1/missions",
            json={"kind": "scout", "field_id": demo["field_id"], "device_id": rover.device_id},
            headers=operator_token,
        )
        assert criada.status_code == 201, criada.text

        eventos = colhe(demo["tenant_id"], marco)
        nomes = [e["event"] for e in eventos]
        assert "mission.created" in nomes, f"a missão criada não apareceu: {nomes}"

        missao = next(e for e in eventos if e["event"] == "mission.created")
        assert missao["subject_id"] == criada.json()["id"]
        assert missao["created_at"], "o evento veio sem horário"

    def test_cada_evento_tem_identificador_para_a_reconexao(
        self, client: TestClient, admin_token: dict, operator_token: dict, demo: dict
    ) -> None:
        """É por ele que o navegador reenvia `Last-Event-ID`. Sem isso, todo
        tremor de rede perderia os eventos do intervalo."""
        rover = provision(client, admin_token, "ROVER_SCOUT_V1", "P-SSE-3", demo["farm_id"])
        marco = datetime.now(UTC)
        send_telemetry(rover, battery_percent=95.0)
        client.post(
            "/v1/missions",
            json={"kind": "scout", "field_id": demo["field_id"], "device_id": rover.device_id},
            headers=operator_token,
        )

        reais = [e for e in colhe(demo["tenant_id"], marco) if e["event"] not in {"stream.end"}]
        assert reais, "nenhum evento saiu"
        assert all(e["_id"] for e in reais), "quadro sem identificador"

    def test_since_no_agora_nao_traz_historia(
        self, client: TestClient, admin_token: dict, operator_token: dict, demo: dict
    ) -> None:
        """Reconectar não pode repetir a tela inteira."""
        rover = provision(client, admin_token, "ROVER_SCOUT_V1", "P-SSE-4", demo["farm_id"])
        send_telemetry(rover, battery_percent=95.0)
        client.post(
            "/v1/missions",
            json={"kind": "scout", "field_id": demo["field_id"], "device_id": rover.device_id},
            headers=operator_token,
        )

        eventos = colhe(demo["tenant_id"], datetime.now(UTC))
        assert [e["event"] for e in eventos] == ["stream.end"]

    def test_o_mesmo_evento_nao_sai_duas_vezes(
        self, client: TestClient, admin_token: dict, operator_token: dict, demo: dict
    ) -> None:
        """O relógio avança com o último evento entregue. Sem isso, cada ciclo
        reenviaria tudo desde o começo e a tela piscaria sem parar."""
        rover = provision(client, admin_token, "ROVER_SCOUT_V1", "P-SSE-5", demo["farm_id"])
        marco = datetime.now(UTC)
        send_telemetry(rover, battery_percent=95.0)
        client.post(
            "/v1/missions",
            json={"kind": "scout", "field_id": demo["field_id"], "device_id": rover.device_id},
            headers=operator_token,
        )

        ids = [e["_id"] for e in colhe(demo["tenant_id"], marco) if e["_id"]]
        assert ids, "nenhum evento saiu"
        assert len(ids) == len(set(ids)), f"evento repetido no mesmo fluxo: {ids}"


class TestOContratoEscrito:
    """`docs/API.md` especificava este protocolo antes de ele existir.

    O contrato escrito é o que vale: um cliente que já leu a documentação não
    deve descobrir outro número no fio.
    """

    def test_o_fluxo_diz_ao_cliente_quando_reconectar(
        self, client: TestClient, demo: dict
    ) -> None:
        """`retry:` é campo de protocolo, não evento: o navegador o guarda e o
        aplica sozinho, e sem ele cada cliente inventaria o próprio intervalo."""

        async def _correr() -> list[str]:
            return [q async for q in stream._fluxo(demo["tenant_id"], datetime.now(UTC), 1)]

        quadros = asyncio.run(_correr())
        assert quadros[0] == f"retry: {stream.RECONEXAO_MS}\n\n", quadros[0]
        assert stream.RECONEXAO_MS == 3000, "docs/API.md promete 3 s"

    def test_o_keepalive_cabe_na_ociosidade_que_os_proxies_impoem(self) -> None:
        """Quinze segundos é o menor dos tempos que proxies costumam impor. Uma
        conexão derrubada em silêncio é pior do que não ter conexão, porque a
        tela continua parecendo ao vivo."""
        assert stream.BATIMENTO_S <= 15

    def test_o_padrao_de_duracao_e_o_que_a_documentacao_promete(self) -> None:
        from valtexa.config import Settings

        assert Settings().stream_max_seconds == 300
