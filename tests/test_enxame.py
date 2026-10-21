"""Enxame (Nível 4): alocação dinâmica entre Rovers e drone, plano versionado, missões pelo
fluxo de segurança de sempre, e o compartilhamento controlado das prioridades."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.helpers import provision, send_telemetry
from valtexa.models import DeviceKind
from valtexa.security import signing
from valtexa.seed import DEMO_FIELD_BOUNDARY
from valtexa.services import compartilhamento, enxame, geo, plant_map

CENTRO = geo.centroid(DEMO_FIELD_BOUNDARY)


def _ret(dlon: float, dlat: float, meio: float = 0.00008) -> list[list[float]]:
    lon, lat = CENTRO[0] + dlon, CENTRO[1] + dlat
    a, b, c, d = lon - meio, lon + meio, lat - meio / 3, lat + meio / 3
    return [[a, c], [b, c], [b, d], [a, d], [a, c]]


def _tarefa(i: str, tipo: str = "inspecao", valor: float = 1.0, *, centro=(0.0, 0.0),
            comprimento: float = 20.0, plantas=(), rua: str = "G1", x0: float = 0.0,
            x1: float = 19.6, **extra) -> enxame.Tarefa:
    return enxame.Tarefa(id=i, tipo=tipo, valor=valor, centro=centro,
                         poligono=extra.pop("poligono", [[0, 0], [1, 0], [1, 1], [0, 0]]),
                         comprimento_m=comprimento, plantas=frozenset(plantas), ruas=(rua,),
                         x_inicio_m=x0, x_fim_m=x1, **extra)


def _agente(i: str, tipo: str = "rover", orcamento: float = 3600.0, posicao=(0.0, 0.0),
            velocidade: float = 1.0) -> enxame.Agente:
    return enxame.Agente(i, i, tipo, velocidade, 3.0, orcamento, posicao)


# ---------------------------------------------------------------------------
# O alocador, sem banco
# ---------------------------------------------------------------------------


def test_valor_por_segundo_e_o_orcamento() -> None:
    perto = _tarefa("perto", valor=1.0, centro=(0.0, 0.0))
    longe = _tarefa("longe", valor=1.5, centro=(0.0, 0.01))  # ~1,1 km: 20 min de deslocamento
    plano = enxame.alocar([perto, longe], [_agente("r1", orcamento=1000.0)])
    (at,) = plano.atribuicoes
    assert [t.id for t in at.tarefas] == ["perto"] and at.tempo_s <= 1000.0
    ((fora, motivo),) = plano.nao_atribuidas
    assert fora.id == "longe" and "orçamento" in motivo


def test_dois_rovers_dividem_pelo_que_esta_perto() -> None:
    oeste = [_tarefa(f"o{i}", centro=(0.0, i * 1e-4), rua=f"G{i}") for i in range(3)]
    leste = [_tarefa(f"l{i}", centro=(0.003, i * 1e-4), rua=f"G{10 + i}") for i in range(3)]
    plano = enxame.alocar(oeste + leste, [_agente("r-oeste", posicao=(0.0, 0.0)),
                                          _agente("r-leste", posicao=(0.003, 0.0))])
    por = {a.agente.device_id: {t.id for t in a.tarefas} for a in plano.atribuicoes}
    assert por == {"r-oeste": {"o0", "o1", "o2"}, "r-leste": {"l0", "l1", "l2"}}


def test_obrigatoria_primeiro_e_tipo_sem_agente() -> None:
    verifica = _tarefa("v", tipo="verificacao", valor=0.0, obrigatoria=True)
    voo = _tarefa("voo", tipo="sobrevoo", valor=9.0)
    comum = _tarefa("i", valor=5.0)
    plano = enxame.alocar([comum, voo, verifica], [_agente("r1")])
    assert [t.id for t in plano.atribuicoes[0].tarefas] == ["v", "i"]
    ((fora, motivo),) = plano.nao_atribuidas
    assert fora.id == "voo" and "nenhum drone" in motivo


def test_desconto_quando_drone_e_rover_cobrem_as_mesmas_plantas() -> None:
    voo = _tarefa("voo", tipo="sobrevoo", valor=10.0, plantas={"a", "b", "c", "d"})
    rua = _tarefa("rua", valor=4.0, plantas={"a", "b"})
    plano = enxame.alocar([voo, rua], [_agente("d1", "drone", velocidade=6.0), _agente("r1")])
    valores = {a.agente.device_id: a.valor for a in plano.atribuicoes}
    assert valores["d1"] == pytest.approx(10.0) and valores["r1"] == pytest.approx(2.0)
    sem = enxame.alocar([voo, rua], [_agente("d1", "drone", velocidade=6.0), _agente("r1")],
                        desconto_sobreposicao=0.0)
    assert {a.agente.device_id: a.valor for a in sem.atribuicoes}["r1"] == pytest.approx(4.0)


def test_proxima_missao_junta_trechos_contiguos_e_sobrevoo_nao_vira_missao() -> None:
    p1, p2, p3 = _ret(0, 0), _ret(0.0002, 0), _ret(0.002, 0)
    trechos = [_tarefa("a", valor=3.0, x0=0.0, x1=19.6, poligono=p1),
               _tarefa("b", valor=2.9, x0=20.3, x1=39.9, poligono=p2, centro=(1e-6, 0)),
               _tarefa("c", valor=2.8, x0=80.0, x1=99.0, poligono=p3, centro=(2e-6, 0)),
               _tarefa("voo", tipo="sobrevoo", valor=1.0)]
    plano = enxame.alocar(trechos, [_agente("r1"), _agente("d1", "drone", velocidade=6.0)])
    missoes = {m["device_id"]: m for m in enxame.proximas_missoes(plano)}
    assert missoes["r1"]["tarefas"] == ["a", "b"] and missoes["r1"]["mission_kind"] == "scout"
    lons = [p[0] for p in missoes["r1"]["poligono"]]
    assert min(lons) == pytest.approx(p1[0][0]) and max(lons) == pytest.approx(p2[1][0])
    assert not missoes["d1"]["pode_criar"] and "regra de segurança" in missoes["d1"]["motivo"]
    sem_gps = enxame.alocar([_tarefa("x", poligono=None)], [_agente("r1")])
    assert not enxame.proximas_missoes(sem_gps)[0]["pode_criar"]


def test_impressao_da_frota_ignora_o_ruido_da_telemetria() -> None:
    a = enxame.Agente("r1", "r1", "rover", 1.0, 3.0, 100.0, (-45.86, -21.90), 80.0)
    ruido = enxame.Agente("r1", "r1", "rover", 1.0, 3.0, 100.0, (-45.860001, -21.90), 81.0)
    mudou = enxame.Agente("r1", "r1", "rover", 1.0, 3.0, 100.0, (-45.86, -21.90), 60.0)
    assert enxame.impressao_da_frota([a], []) == enxame.impressao_da_frota([ruido], [])
    assert enxame.impressao_da_frota([a], []) != enxame.impressao_da_frota([mudou], [])


def test_politica_de_compartilhamento() -> None:
    assert compartilhamento.pode_receber(DeviceKind.ROVER, compartilhamento.PRIORIDADES)
    assert not compartilhamento.pode_receber(DeviceKind.DRONE, compartilhamento.PRIORIDADES)
    assert not compartilhamento.pode_receber(DeviceKind.GATEWAY, compartilhamento.PRIORIDADES)
    assert not compartilhamento.pode_receber(DeviceKind.DOCK, compartilhamento.APLICACAO)


# ---------------------------------------------------------------------------
# Pela plataforma, com banco, dispositivos provisionados e o gêmeo falso
# ---------------------------------------------------------------------------


def _gemeo_falso(chamadas: list):
    def prioridades(field_id, params):
        chamadas.append(params)
        if params["canal"] == "drone":
            return {"tarefas": [{"tipo": "sobrevoo", "ruas": ["G1", "G2"], "x_inicio_m": 0.0,
                                 "x_fim_m": 39.0, "comprimento_m": 78.0, "area_m2": 270.0,
                                 "valor": 5.0, "poligono": _ret(0, 0.0003),
                                 "plant_ids": ["p1", "p2", "p9"], "motivo": "copa"}],
                    "avisos": ["Canal de observação 'drone': suposição de projeto, a medir."]}
        return {"tarefas": [
            {"tipo": "inspecao", "ruas": ["G3"], "x_inicio_m": 0.0, "x_fim_m": 19.6,
             "comprimento_m": 19.6, "area_m2": 68.6, "valor": 3.0, "poligono": _ret(0, 0),
             "plant_ids": ["p1", "p2"], "motivo": "risco"},
            {"tipo": "inspecao", "ruas": ["G3"], "x_inicio_m": 20.3, "x_fim_m": 39.9,
             "comprimento_m": 19.6, "area_m2": 68.6, "valor": 2.0, "poligono": _ret(0.0002, 0),
             "plant_ids": ["p3"], "motivo": "risco"},
            {"tipo": "inspecao", "ruas": ["G9"], "x_inicio_m": 0.0, "x_fim_m": 19.6,
             "comprimento_m": 19.6, "area_m2": 68.6, "valor": 1.0,
             "poligono": _ret(-0.0004, -0.0002), "plant_ids": ["p7"], "motivo": "dúvida"}],
            "avisos": []}
    return prioridades


@pytest.fixture
def frota(client: TestClient, admin_token: dict, demo: dict):
    r1 = provision(client, admin_token, "ROVER_V3", "ENX-R1", demo["farm_id"])
    r2 = provision(client, admin_token, "ROVER_V3", "ENX-R2", demo["farm_id"])
    d1 = provision(client, admin_token, "DRONE_ACTION_V1", "ENX-D1", demo["farm_id"])
    for robo, dlon in ((r1, 0.0), (r2, -0.0004), (d1, 0.0)):
        assert send_telemetry(robo, lat=CENTRO[1], lon=CENTRO[0] + dlon,
                              battery_percent=90.0).status_code in (200, 201, 202)
    return r1, r2, d1


def test_plano_missoes_e_prioridades_na_missao_assinada(client, admin_token, demo, frota,
                                                        monkeypatch) -> None:
    r1, r2, d1 = frota
    chamadas: list = []
    monkeypatch.setattr(plant_map, "prioridades_gemeo", _gemeo_falso(chamadas))
    url = f"/v1/fields/{demo['field_id']}/enxame/plano"
    assert client.get(url, headers=admin_token).status_code == 404
    r = client.post(url, json={"custo_tratar": 2}, headers=admin_token)
    assert r.status_code == 422  # economia vai junta
    r = client.post(url, json={"doenca": "Rust"}, headers=admin_token)
    assert r.status_code == 200, r.text
    plano = r.json()
    assert {c["canal"] for c in chamadas} == {"rover", "drone"}
    assert all(c["com_plantas"] for c in chamadas)
    assert plano["versao"] == 1 and not plano["desatualizado"]
    assert any("suposição de projeto" in a for a in plano["avisos_do_gemeo"])
    por_device = {a["device_id"]: a for a in plano["atribuicoes"]}
    assert set(por_device) == {r1.device_id, r2.device_id, d1.device_id}
    # O Rover 1 está no meio dos dois trechos contíguos da G3; o 2, perto da G9.
    missoes = {m["device_id"]: m for m in plano["proximas_missoes"]}
    assert len(missoes[r1.device_id]["tarefas"]) == 2
    assert not missoes[d1.device_id]["pode_criar"]

    # A frota muda (bateria de 90% para 40%): o plano fica desatualizado, e diz por quê.
    send_telemetry(r2, lat=CENTRO[1], lon=CENTRO[0] - 0.0004, battery_percent=40.0)
    atual = client.get(url, headers=admin_token).json()
    assert atual["desatualizado"] and "frota mudou" in atual["motivos"][0]

    criar = f"{url}/{plano['plano_id']}/missoes"
    r = client.post(criar, json={}, headers=admin_token)
    assert r.status_code == 200, r.text
    resultado = {m["device_id"]: m for m in r.json()["missoes"]}
    assert resultado[r1.device_id]["mission_id"] and resultado[r2.device_id]["mission_id"]
    assert resultado[d1.device_id]["mission_id"] is None
    de_novo = client.post(criar, json={"device_ids": [r1.device_id]}, headers=admin_token)
    assert de_novo.json()["missoes"][0]["motivo"] == "já criada por este plano"

    missao = resultado[r1.device_id]["mission_id"]
    assert client.post(f"/v1/missions/{missao}/authorize", headers=admin_token).status_code \
        == 200, client.post(f"/v1/missions/{missao}/authorize", headers=admin_token).text
    assert client.post(f"/v1/missions/{missao}/dispatch", headers=admin_token).status_code == 200
    comando = r1.request("GET", "/v1/device/missions/current")
    assert comando.status_code == 200, comando.text
    envelope = comando.json()
    # Vai dentro do corpo assinado: o Rover confere a assinatura antes de usar.
    signing.verify_command(envelope["payload"], envelope["signature"])  # levanta se falsa
    prioridades = envelope["payload"]["body"]["prioridades"]
    assert prioridades["plano_id"] == plano["plano_id"] and "não é evidência" in prioridades["uso"]
    assert {tuple(t["ruas"]) for t in prioridades["trechos"]} == {("G3",)}
    assert max(t["prioridade"] for t in prioridades["trechos"]) == 1.0
    assert "valor" not in prioridades["trechos"][0]  # o dinheiro em jogo não desce

    # Um plano novo substitui o anterior; criar missão pelo velho é recusado.
    novo = client.post(url, json={}, headers=admin_token).json()
    assert novo["versao"] == 2
    assert client.post(criar, json={}, headers=admin_token).status_code == 409
    assert client.post("/v1/fields/outro/enxame/plano", json={},
                       headers=admin_token).status_code == 404


def test_gemeo_fora_do_ar_e_recusa(client, admin_token, demo, frota, monkeypatch) -> None:
    def fora(field_id, params):
        raise plant_map.PlantMapUnavailableError("fora do ar")

    monkeypatch.setattr(plant_map, "prioridades_gemeo", fora)
    url = f"/v1/fields/{demo['field_id']}/enxame/plano"
    assert client.post(url, json={}, headers=admin_token).status_code == 503

    def sem_clima(field_id, params):
        raise plant_map.PlantMapRefusedError("Talhão sem série climática", 409)

    monkeypatch.setattr(plant_map, "prioridades_gemeo", sem_clima)
    r = client.post(url, json={}, headers=admin_token)
    assert r.status_code == 409 and "climática" in r.json()["detail"]
