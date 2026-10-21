"""Validação do Rover na plataforma: limites do portão, veredito do servidor, portões,
regressão, FASE 5, cancelamento e prazo de execução."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from tests.helpers import provision
from valtexa.models import DeviceCommand, EnsaioResultado, Notification
from valtexa.security import signing
from valtexa.services import ensaios, events


@pytest.fixture
def rover(client, admin_token, demo):
    return provision(client, admin_token, "ROVER_SCOUT_V1", "RV3-ENS-01", demo["farm_id"])


@pytest.fixture
def outro_rover(client, admin_token, demo):
    return provision(client, admin_token, "ROVER_SCOUT_V1", "RV3-ENS-02", demo["farm_id"])


def _url(rover, resto: str = "") -> str:
    return f"/v1/platform/rovers/{rover.device_id}{resto}"


def manda(client, token, rover, ensaio: str, params: dict | None = None):
    return client.post(_url(rover, "/ensaios"), headers=token,
                       json={"ensaio": ensaio, "params": params or {}})


def executa(client, token, rover, ensaio: str, params: dict, laudo: dict) -> dict:
    """A equipe manda, o robô (aqui na mão) busca, conta o progresso e devolve o laudo."""
    r = manda(client, token, rover, ensaio, params)
    assert r.status_code == 201, r.text
    cid = r.json()["id"]
    entregues = rover.request("GET", "/v1/device/commands").json()
    assert [e["payload"]["body"]["command_id"] for e in entregues] == [cid]
    assert rover.request("POST", f"/v1/device/commands/{cid}/progresso",
                         json_body={"fracao": 0.5, "etapa": "meio"}).status_code == 200
    assert rover.request("POST", f"/v1/device/commands/{cid}/result",
                         json_body={"ok": True, "result": laudo}).status_code == 200
    resultados = client.get(_url(rover, "/ensaios"), headers=token).json()["resultados"]
    return next(x for x in resultados if x["command_id"] == cid)


def laudo(status="aprovado", simulado=False, **amostras) -> dict:
    return {"status": status, "aprovado": status == "aprovado", "simulado": simulado,
            "criterios": [], "medidas": {}, "amostras": amostras}


def test_catalogo_so_para_a_equipe(client, platform_token, admin_token, demo) -> None:
    corpo = client.get("/v1/platform/ensaios/catalogo", headers=platform_token).json()
    nomes = {e["nome"] for e in corpo["ensaios"]}
    assert {"calor", "cameras", "profundidade", "gnss", "imu", "rede", "energia", "parada",
            "homem_morto", "validacao_agronomica", "relogio"} == nomes
    assert corpo["fases"]["1"] == "Segurança" or corpo["fases"][1] == "Segurança"
    assert client.get("/v1/platform/ensaios/catalogo",
                      headers=admin_token).status_code in (401, 403)


@pytest.mark.parametrize(("ensaio", "params", "trecho"), [
    ("voar", {}, "use"),
    ("cameras", {"perda_max_pct": 5}, "mais frouxo"),
    ("rede", {"vazao_min_kbps": 10}, "mais frouxo"),
    ("imu", {"chute": 1}, "desconhecidos"),
    ("profundidade", {"camera_id": "oak-0"}, "distancia_real_mm"),
    ("validacao_agronomica", {}, "use"),
    ("gnss", {"cep95_max_cm": "muito"}, "número"),
])
def test_pedido_invalido_nao_vira_comando(client, platform_token, rover, ensaio, params,
                                          trecho) -> None:
    r = manda(client, platform_token, rover, ensaio, params)
    assert r.status_code == 422 and trecho in r.text
    assert rover.request("GET", "/v1/device/commands").json() == []


def test_apertar_limite_vale_e_vai_assinado(client, platform_token, rover) -> None:
    r = manda(client, platform_token, rover, "cameras", {"deriva_max_ms": 50, "cameras": 8})
    assert r.status_code == 201
    envelope = rover.request("GET", "/v1/device/commands").json()[0]
    signing.verify_command(envelope["payload"], envelope["signature"])
    params = envelope["payload"]["body"]["params"]
    assert params["ensaio"] == "cameras"
    assert params["params"]["deriva_max_ms"] == 50  # apertado
    assert params["params"]["perda_max_pct"] == 0.0  # o padrão do portão foi junto


def test_veredito_e_do_servidor_nao_do_robo(client, platform_token, rover) -> None:
    # O robô diz "aprovado", mas as amostras mostram 40 mm de erro e ainda tenta trocar a
    # distância da trena: vale a que a plataforma assinou (500 mm).
    adulterado = laudo("aprovado", medianas_mm=[540.0, 541.0, 539.0],
                       preenchimentos=[0.9, 0.9, 0.9], distancia_real_mm=540.0)
    linha = executa(client, platform_token, rover, "profundidade",
                    {"camera_id": "oak-0", "distancia_real_mm": 500}, adulterado)
    assert linha["status"] == "reprovado" and linha["divergente"] is True
    assert linha["medidas"]["erro_mm"] == 40.0
    detalhe = client.get(_url(rover, f"/ensaios/{linha['id']}"), headers=platform_token).json()
    assert detalhe["laudo_robo"]["aprovado"] is True and "amostras" not in detalhe["laudo_robo"]


def test_reenvio_do_resultado_nao_duplica(client, platform_token, rover, session) -> None:
    linha = executa(client, platform_token, rover, "rede", {"pings": 4, "carga_kb": 0},
                    laudo(rtts_ms=[50.0, 60.0, 55.0, 52.0]))
    assert linha["status"] == "aprovado"
    rover.request("POST", f"/v1/device/commands/{linha['command_id']}/result",
                  json_body={"ok": True, "result": laudo(rtts_ms=[])})
    assert len(session.scalars(select(EnsaioResultado)).all()) == 1


def test_robo_que_omite_tentativas_nao_aprova_a_parada(client, platform_token, rover) -> None:
    # Pediu 5 tentativas; o robô manda só as 2 boas.
    linha = executa(client, platform_token, rover, "parada", {"tentativas": 5},
                    laudo(latencias_ms=[120.0, 130.0]))
    assert linha["status"] == "reprovado"
    assert {c["nome"]: c["ok"] for c in linha["criterios"]}["confirmadas_pct"] is False


def test_laudo_sem_marca_de_simulacao_conta_como_simulado(client, platform_token,
                                                          rover) -> None:
    sem_marca = {"status": "aprovado", "amostras": {"rtts_ms": [10.0] * 20}}
    linha = executa(client, platform_token, rover, "rede", {"carga_kb": 0}, sem_marca)
    assert linha["status"] == "aprovado" and linha["simulado"] is True


def test_outro_robo_nao_mexe_no_ensaio(client, platform_token, rover, outro_rover) -> None:
    cid = manda(client, platform_token, rover, "imu").json()["id"]
    rover.request("GET", "/v1/device/commands")
    assert outro_rover.request("POST", f"/v1/device/commands/{cid}/progresso",
                               json_body={"fracao": 0.1}).status_code == 404
    assert outro_rover.request("POST", f"/v1/device/commands/{cid}/result",
                               json_body={"ok": True, "result": laudo()}).status_code == 404
    diag = client.post(_url(rover, "/comandos"), headers=platform_token,
                       json={"kind": "diagnostico"}).json()["id"]
    assert rover.request("POST", f"/v1/device/commands/{diag}/progresso",
                         json_body={"fracao": 0.1}).status_code == 404  # não é ensaio


def _parada_ok(n: int = 5) -> dict:
    return laudo(latencias_ms=[100.0 + i for i in range(n)])


def test_portao_da_fase1_so_abre_com_tudo_aprovado(client, platform_token, rover) -> None:
    def fase(n: int) -> dict:
        return next(p for p in client.get(_url(rover, "/portoes"), headers=platform_token)
                    .json() if p["fase"] == n)

    assert fase(1)["aprovado"] is False and set(fase(1)["faltam"]) == {"parada", "homem_morto"}
    # 3 tentativas: aprovado no ensaio, mas não vale para o portão (pede 5).
    curta = executa(client, platform_token, rover, "parada", {"tentativas": 3}, _parada_ok(3))
    assert curta["status"] == "aprovado" and curta["vale_portao"] is False
    assert "5 tentativas" in curta["observacao"]
    executa(client, platform_token, rover, "parada", {}, _parada_ok())
    assert fase(1)["faltam"] == ["homem_morto"]
    executa(client, platform_token, rover, "homem_morto", {}, laudo(atrasos_s=[0.2]))
    assert fase(1)["aprovado"] is True
    assert fase(2)["automatico"] is False and fase(2)["aprovado"] is None
    zero = fase(0)
    assert zero["aprovado"] is False and "profundidade 0.3 m" in zero["faltam"]
    assert zero["informativos"] == ["energia"]


def test_regressao_vira_aviso_para_a_equipe(client, platform_token, rover, session) -> None:
    executa(client, platform_token, rover, "parada", {}, _parada_ok())
    executa(client, platform_token, rover, "parada", {},
            laudo("aprovado", latencias_ms=[100.0, 110.0, 900.0, 950.0, 990.0]))
    events.drain(session)
    session.commit()
    avisos = session.scalars(select(Notification).where(
        Notification.kind == "plataforma_ensaio_regressao")).all()
    assert avisos and "latencia_p95_ms" in avisos[0].body
    assert avisos[0].subject_id == rover.device_id


def test_simulado_nao_regride_o_real(client, platform_token, rover, session) -> None:
    executa(client, platform_token, rover, "parada", {}, _parada_ok())
    executa(client, platform_token, rover, "parada", {},
            laudo(simulado=True, latencias_ms=[900.0] * 5))
    events.drain(session)
    session.commit()
    assert not session.scalars(select(Notification).where(
        Notification.kind == "plataforma_ensaio_regressao")).all()


RELATORIO = {"field_id": None, "mission_id": None, "plants_labeled": 40, "diseased": 20,
             "detected": 18, "right_disease": 17, "healthy": 20, "false_alarms": 2,
             "by_disease": {"Rust": {"detected": 18, "diseased": 20}}, "note": "nota"}


def test_fase5_pela_validacao_de_campo(client, platform_token, rover, demo, operator_token,
                                       monkeypatch) -> None:
    from valtexa.api.routers import ensaios_api

    criada = client.post("/v1/missions", headers=operator_token, json={
        "kind": "scout", "field_id": demo["field_id"], "zone_id": demo["zone_id"],
        "device_id": rover.device_id, "target_polygon": _zona(),
        "plan": {"swath_m": 40.0}})
    assert criada.status_code == 201, criada.text
    mid = criada.json()["id"]
    chamadas = []

    def relatorio(session, talhao, mission_id):
        chamadas.append((talhao.id, mission_id))
        return {**RELATORIO, "field_id": talhao.id, "mission_id": mission_id}

    monkeypatch.setattr(ensaios_api.validacao_campo, "relatorio", relatorio)
    url = _url(rover, "/ensaios/validacao-agronomica")
    r = client.post(url, headers=platform_token,
                    json={"field_id": demo["field_id"], "mission_id": mid})
    assert r.status_code == 201, r.text
    linha = r.json()
    assert chamadas == [(demo["field_id"], mid)]
    assert linha["status"] == "aprovado" and linha["fase"] == 5
    m = linha["medidas"]
    assert m["sensibilidade"] == 0.9 and m["alarme_falso"] == 0.1 and m["concordancia"] == 0.9
    assert m["sensibilidade_ic95"][0] < 0.9 < m["sensibilidade_ic95"][1]
    # Pelo intervalo (conservador): 20 plantas de cada lado não bastam para 80 %.
    pelo_ic = client.post(url, headers=platform_token, json={
        "field_id": demo["field_id"], "mission_id": mid, "params": {"usar_ic": True}}).json()
    assert pelo_ic["status"] == "reprovado"
    fase5 = next(p for p in client.get(_url(rover, "/portoes"), headers=platform_token).json()
                 if p["fase"] == 5)
    assert fase5["aprovado"] is False  # o último (pelo IC) reprovou
    # Missão de outro talhão / outro cliente: 404; afrouxar o limite: 422.
    assert client.post(url, headers=platform_token, json={
        "field_id": demo["field_id"], "mission_id": "x" * 32}).status_code == 404
    assert client.post(url, headers=platform_token, json={
        "field_id": demo["field_id"], "mission_id": mid,
        "params": {"sensibilidade_min": 0.5}}).status_code == 422


def _zona() -> list[list[float]]:
    from tests.test_end_to_end import ZONA

    return ZONA


def test_cancelar_na_fila_e_no_robo(client, platform_token, rover) -> None:
    na_fila = manda(client, platform_token, rover, "imu").json()["id"]
    r = client.post(_url(rover, f"/ensaios/{na_fila}/cancelar"), headers=platform_token)
    assert r.json()["state"] == "cancelado"
    rodando = manda(client, platform_token, rover, "calor").json()["id"]
    rover.request("GET", "/v1/device/commands")
    rover.request("POST", f"/v1/device/commands/{rodando}/progresso",
                  json_body={"fracao": 0.1, "etapa": "janela 1"})
    em_curso = client.get(_url(rover, "/ensaios"), headers=platform_token).json()["em_curso"]
    assert em_curso[0]["state"] == "em_execucao" and em_curso[0]["progress"]["fracao"] == 0.1
    r = client.post(_url(rover, f"/ensaios/{rodando}/cancelar"), headers=platform_token).json()
    pedido = rover.request("GET", "/v1/device/commands").json()[0]["payload"]["body"]
    assert pedido == {"command_id": r["cancel_command_id"], "kind": "ensaio_cancelar",
                      "params": {"command_id": rodando}}
    rover.request("POST", f"/v1/device/commands/{rodando}/result",
                  json_body={"ok": True, "result": laudo("cancelado")})
    assert client.post(_url(rover, f"/ensaios/{rodando}/cancelar"),
                       headers=platform_token).status_code == 409
    resultados = client.get(_url(rover, "/ensaios"), headers=platform_token).json()
    assert resultados["resultados"][0]["status"] == "cancelado"


def test_ensaio_mudo_vira_falha_no_prazo(client, platform_token, rover, session_factory) -> None:
    cid = manda(client, platform_token, rover, "imu", {"duracao_s": 30}).json()["id"]
    rover.request("GET", "/v1/device/commands")
    rover.request("POST", f"/v1/device/commands/{cid}/progresso", json_body={"fracao": 0.0})
    # Um ensaio de 30 s em execução não expira nos 2 min do comando...
    with session_factory() as s:
        c = s.get(DeviceCommand, cid)
        c.delivered_at = datetime.now(UTC) - timedelta(minutes=10)
        s.commit()
    assert client.get(_url(rover, "/ensaios"), headers=platform_token).json()["em_curso"]
    # ...mas sem notícia além da duração + 15 min, vira falha.
    with session_factory() as s:
        c = s.get(DeviceCommand, cid)
        c.delivered_at = datetime.now(UTC) - timedelta(minutes=16)
        s.commit()
    assert client.get(_url(rover, "/ensaios"), headers=platform_token).json()["em_curso"] == []
    with session_factory() as s:
        c = s.get(DeviceCommand, cid)
        assert c.state == "falhou" and "prazo" in c.error


def test_eco_de_rede_do_robo(rover) -> None:
    assert len(rover.request("GET", "/v1/device/ensaio/eco?bytes=4096").content) == 4096
    r = rover.request("POST", "/v1/device/ensaio/eco", content=b"\0" * 1000)
    assert r.json() == {"recebidos": 1000}
    assert rover.request("GET", "/v1/device/ensaio/eco?bytes=999999999").status_code == 422


def test_contas_do_servidor_batem_com_as_do_robo() -> None:
    """As contas da plataforma e as do robô são implementações separadas: conferir."""
    estatistica = pytest.importorskip("valtexa_rover.ensaios.estatistica")
    valores = [3.0, 1.0, 4.0, 1.5, 9.0, 2.6]
    for p in (50, 95):
        assert ensaios.percentil(valores, p) == pytest.approx(estatistica.percentil(valores, p))
    lats = [-21.25 + i * 1e-7 for i in range(10)]
    lons = [-45.0 - i * 2e-7 for i in range(10)]
    a = ensaios._precisao(lats, lons, (-21.25, -45.0))
    b = estatistica.precisao_horizontal(lats, lons, (-21.25, -45.0))
    for k in ("cep50_cm", "cep95_cm", "drms2_cm", "vies_cm"):
        assert a[k] == pytest.approx(b[k])


def test_servidor_refaz_a_conta_do_relogio_e_concorda_com_o_robo() -> None:
    """O ``relogio`` (FASE 0, só o Rover desde que a base foi arquivada): a mesma conta dos
    dois lados, para o servidor não confiar no "aprovado" do robô."""
    rover_relogio = pytest.importorskip("valtexa_rover.ensaios.relogio")
    amostras = {"rover": {"sincronizado": True, "fonte": "gnss", "offset_ms": 0.004},
                "atraso_plataforma_s": 0.0}
    p = ensaios.valida_pedido("relogio", None)
    assert ensaios.CATALOGO["relogio"].fase == 0
    crit_s, _, motivo = ensaios.CATALOGO["relogio"].calcula(p, amostras)
    crit_r, _ = rover_relogio.avalia_relogio(p, amostras)
    assert [(c["nome"], c["ok"]) for c in crit_s] == [(c["nome"], c["ok"]) for c in crit_r]
    assert all(c["ok"] for c in crit_s) and motivo is None
    atrasado = {**amostras, "atraso_plataforma_s": 5.0}
    assert not all(c["ok"] for c in ensaios.CATALOGO["relogio"].calcula(p, atrasado)[0])
