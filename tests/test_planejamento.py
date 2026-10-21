"""Planejamento de apoio à decisão (8.3): fitossanitário, robótico e de insumos.

A IA (evolução, lesões, previsão e prioridades do gêmeo) é um **dublê** com números
inventados para o teste — os pesos reais não estão neste repositório. As fontes de
conhecimento e os produtos daqui são **fictícios**.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from tests.helpers import provision, send_telemetry
from tests.test_enxame import CENTRO, _agente, _gemeo_falso, _ret, _tarefa
from valtexa.api.routers import planejamento as rotas
from valtexa.cerebro import conhecimento
from valtexa.main import app
from valtexa.models import (
    Agreement,
    Application,
    ApplicationState,
    Detection,
    DetectionSource,
    Diagnosis,
    DiagnosisStatus,
    Field,
    Mission,
    MissionKind,
    MissionState,
    Observation,
    Product,
    ProductBatch,
    utcnow,
)
from valtexa.models.planejamento import PlanoDeApoio
from valtexa.planejamento import insumos
from valtexa.services import enxame

# ---------------------------------------------------------------------------------------------
# O alocador com restrições (mudança aditiva no enxame)
# ---------------------------------------------------------------------------------------------


def test_alocar_sem_restricoes_e_o_mesmo_de_sempre() -> None:
    tarefas = [_tarefa("a", valor=3.0, centro=(0.0, 0.0)), _tarefa("b", valor=1.0)]
    agentes = [_agente("r1")]
    antes = enxame.alocar(tarefas, agentes).to_dict()
    depois = enxame.alocar(tarefas, agentes, restricao=None, bytes_da_tarefa=None,
                           orcamento_bytes=None).to_dict()
    assert antes == depois and "bytes_estimados" not in depois["atribuicoes"][0]


def test_restricao_exclui_com_motivo_e_soma_tempo() -> None:
    tarefas = [_tarefa("a", valor=3.0), _tarefa("b", valor=2.0)]
    agentes = [_agente("r1"), _agente("r2")]

    def restricao(t, a):
        if a.device_id == "r1":
            return 0.0, "encosta acima do limite"
        return (100.0 if t.id == "b" else 0.0), None

    plano = enxame.alocar(tarefas, agentes, restricao=restricao)
    assert [a.agente.device_id for a in plano.atribuicoes] == ["r2"]
    base = enxame.alocar(tarefas, [_agente("r2")])
    assert plano.atribuicoes[0].tempo_s == pytest.approx(base.atribuicoes[0].tempo_s + 100.0)
    so_r1 = enxame.alocar(tarefas, [_agente("r1")], restricao=restricao)
    assert {m for _, m in so_r1.nao_atribuidas} == {"encosta acima do limite"}


def test_orcamento_de_bytes_corta_o_que_nao_cabe() -> None:
    tarefas = [_tarefa("a", valor=3.0, comprimento=20.0), _tarefa("b", valor=2.0,
                                                                 comprimento=20.0)]
    plano = enxame.alocar(tarefas, [_agente("r1")], bytes_da_tarefa=lambda t, a:
                          t.comprimento_m * 1000.0, orcamento_bytes={"r1": 25_000.0})
    assert [t.id for t in plano.atribuicoes[0].tarefas] == ["a"]
    assert plano.atribuicoes[0].to_dict()["bytes_estimados"] == 20_000
    assert "orçamento de dados" in plano.nao_atribuidas[0][1]
    assert plano.parametros["orcamento_bytes"] == {"r1": 25_000}


# ---------------------------------------------------------------------------------------------
# A IA dublê
# ---------------------------------------------------------------------------------------------


class IADuble:
    def __init__(self, **troca: Any) -> None:
        self.prioridades_fn = _gemeo_falso([])
        self.respostas: dict[str, Any] = {
            "evolucao": {"history": [
                {"pass_id": "m-5", "status": "suspeita", "primary_disease": "Rust",
                 "incidence": 0.05},
                {"pass_id": "m-6", "status": "doente", "primary_disease": "Rust",
                 "incidence": 0.21}], "changes": [{"change": "piorou"}]},
            "lesoes": {"passes": ["m-5", "m-6"], "tracks": [
                {"id": "L1", "disease": "Rust", "state": "persistente"},
                {"id": "L2", "disease": "Rust", "state": "persistente"},
                {"id": "L3", "disease": "Rust", "state": "nova"}]},
            "previsao": {"horizonte": "2026-11-02", "infectadas_no_horizonte_esperado": 12.4,
                         "infectadas_no_horizonte_p10_p90": [8.0, 19.5],
                         "focos_no_horizonte": 2, "plantas_detalhe": [
                             {"plant_id": "L01-P0001", "risco": 0.71},
                             {"plant_id": "L01-P0002", "risco": 0.12}]},
        }
        self.respostas.update(troca)

    def _r(self, chave):
        v = self.respostas.get(chave)
        if isinstance(v, Exception):
            raise v
        return v

    def evolucao(self, field_id, plant_ref):
        return self._r("evolucao")

    def lesoes(self, field_id, plant_ref):
        return self._r("lesoes")

    def previsao(self, field_id, doenca, horizonte_dias):
        return self._r("previsao")

    def prioridades(self, field_id, params):
        if isinstance(self.respostas.get("prioridades"), Exception):
            raise self.respostas["prioridades"]
        return self.prioridades_fn(field_id, params)


@pytest.fixture
def ia() -> IADuble:
    duble = IADuble()
    app.dependency_overrides[rotas.fonte_da_ia] = lambda: duble
    yield duble
    app.dependency_overrides.pop(rotas.fonte_da_ia, None)


def _missoes(session) -> int:
    session.expire_all()
    return session.scalar(select(func.count()).select_from(Mission))


# ---------------------------------------------------------------------------------------------
# Robótico
# ---------------------------------------------------------------------------------------------


@pytest.fixture
def frota(client: TestClient, admin_token: dict, demo: dict):
    r1 = provision(client, admin_token, "ROVER_V3", "PLN-R1", demo["farm_id"])
    r2 = provision(client, admin_token, "ROVER_V3", "PLN-R2", demo["farm_id"])
    d1 = provision(client, admin_token, "DRONE_ACTION_V1", "PLN-D1", demo["farm_id"])
    for robo, dlon in ((r1, 0.0), (r2, -0.0004), (d1, 0.0)):
        assert send_telemetry(robo, lat=CENTRO[1], lon=CENTRO[0] + dlon,
                              battery_percent=90.0).status_code in (200, 201, 202)
    return r1, r2, d1


def _robotico(client, token, demo, **corpo) -> dict:
    r = client.post(f"/v1/fields/{demo['field_id']}/planejamento/robotico", json=corpo,
                    headers=token)
    assert r.status_code == 201, r.text
    return r.json()


def test_robotico_reaproveita_o_enxame_e_registra_premissas(
        client, operator_token, demo, frota, ia, session) -> None:
    antes = _missoes(session)
    p = _robotico(client, operator_token, demo)
    res = p["resultado"]
    assert p["tipo"] == "robotico" and p["estado"] == "proposto" and p["integro"]
    assert {r["device_id"] for r in res["rotas"]} == {f.device_id for f in frota}
    premissas = {x["codigo"]: x for x in p["premissas"]}
    assert premissas["bytes_por_metro"]["origem"] == "simulado"
    assert premissas["relevo"]["origem"] == "padrao"  # não medido: dito
    assert premissas["fator_declive"]["origem"] == "padrao"
    rota_r1 = next(r for r in res["rotas"] if r["device_id"] == frota[0].device_id)
    assert rota_r1["bateria_final_estimada_pct"] < rota_r1["bateria_inicial_pct"] == 90.0
    assert rota_r1["bytes_estimados"] > 0
    assert res["proximas_missoes_propostas"] and "RASCUNHO" in res["nota"]
    assert _missoes(session) == antes  # propor não cria missão


def test_robotico_inclinacao_acima_do_limite_tira_os_rovers(
        client, operator_token, demo, frota, ia, session) -> None:
    campo = session.get(Field, demo["field_id"])
    campo.relief = {"declividade_maxima_deg": 21.0, "declividade_media_deg": 12.0,
                    "fonte": "teste"}
    session.commit()
    res = _robotico(client, operator_token, demo)["resultado"]
    assert {r["tipo"] for r in res["rotas"]} == {"drone"}
    motivos = {n["motivo"] for n in res["nao_atribuidas"] if n["tipo"] == "inspecao"}
    assert any("declividade máxima medida 21°" in m and "Safety Engine" in m for m in motivos)
    assert res["sairam_pelas_restricoes"]


def test_robotico_declive_moderado_custa_tempo(client, operator_token, demo, frota, ia,
                                               session) -> None:
    plano = _robotico(client, operator_token, demo)["resultado"]
    campo = session.get(Field, demo["field_id"])
    campo.relief = {"declividade_maxima_deg": 10.0, "declividade_media_deg": 7.5,
                    "fonte": "teste"}
    session.commit()
    p = _robotico(client, operator_token, demo)
    tempo = {r["device_id"]: r["tempo_s"] for r in p["resultado"]["rotas"]}
    antes = {r["device_id"]: r["tempo_s"] for r in plano["rotas"]}
    assert tempo[frota[0].device_id] > antes[frota[0].device_id]
    assert {x["codigo"]: x for x in p["premissas"]}["relevo"]["origem"] == "medido"


def test_robotico_obstaculo_da_leitura_de_terreno(client, operator_token, demo, frota, ia,
                                                  session) -> None:
    mata = _ret(-0.0004, -0.0002, meio=0.0002)  # cobre o trecho da G9
    campo = session.get(Field, demo["field_id"])
    campo.terrain = {"resolution_ok": True, "heuristic": True, "objects": [
        {"kind": "mata", "outline": mata, "traversable": False, "confidence": 0.8},
        {"kind": "carreador", "outline": _ret(0, 0), "traversable": True, "confidence": 0.9}]}
    session.commit()
    res = _robotico(client, operator_token, demo)["resultado"]
    assert [o["tipo"] for o in res["obstaculos"]] == ["mata"]
    fora = {n["tarefa"]: n["motivo"] for n in res["nao_atribuidas"]}
    g9 = next(i for i, t in res["tarefas"].items() if t["ruas"] == ["G9"])
    assert "dentro de mata" in fora[g9]


def test_robotico_orcamento_de_dados_da_starlink(client, operator_token, admin_token, demo,
                                                 frota, ia) -> None:
    for robo in frota[:2]:
        r = client.put(f"/v1/devices/{robo.device_id}/orcamento-dados",
                       json={"bytes_dia": 1_000_000}, headers=admin_token)
        assert r.status_code == 200, r.text
    p = _robotico(client, operator_token, demo, bytes_por_metro=100_000)
    res = p["resultado"]
    assert {r["tipo"] for r in res["rotas"]} == {"drone"}
    assert any("orçamento de dados" in n["motivo"] for n in res["nao_atribuidas"])
    dados = {d["device_id"]: d for d in res["dados_starlink"]}
    assert dados[frota[0].device_id]["restante_bytes"] == 900_000  # 10% de reserva
    assert {x["codigo"]: x for x in p["premissas"]}["bytes_por_metro"]["origem"] == "pedido"


def test_robotico_gemeo_fora_do_ar_planeja_so_o_obrigatorio(
        client, operator_token, demo, frota, ia) -> None:
    from valtexa.planejamento.fitossanitario import IndisponivelError

    ia.respostas["prioridades"] = IndisponivelError("fora do ar")
    res = _robotico(client, operator_token, demo)["resultado"]
    assert res["rotas"] == [] and any("fora do ar" in a for a in res["avisos"])


# ---------------------------------------------------------------------------------------------
# Fitossanitário
# ---------------------------------------------------------------------------------------------


def _diagnostico(session, demo, plant_ref: str, *, label: str, probs: dict[str, float],
                 status=DiagnosisStatus.NEEDS_REVIEW, agreement=Agreement.AGREE,
                 conjunto=None, horas: int = 1) -> Diagnosis:
    obs = Observation(tenant_id=demo["tenant_id"], farm_id=demo["farm_id"],
                      field_id=demo["field_id"], plant_ref=plant_ref,
                      captured_at=utcnow() - timedelta(hours=horas), lat=CENTRO[1],
                      lon=CENTRO[0])
    session.add(obs)
    session.flush()
    det = Detection(tenant_id=demo["tenant_id"], observation_id=obs.id,
                    source=DetectionSource.CLOUD_PRIMARY, analyzer="teste", label=label,
                    confidence=max(probs.values()), probabilities=probs,
                    signals={"prediction_set": conjunto} if conjunto else {})
    session.add(det)
    session.flush()
    diag = Diagnosis(tenant_id=demo["tenant_id"], observation_id=obs.id,
                     field_id=demo["field_id"], status=status, agreement=agreement,
                     label=label, confidence=max(probs.values()), pipeline_version="teste",
                     primary_detection_id=det.id)
    session.add(diag)
    session.flush()
    return diag


def _fito(client, token, demo, **corpo) -> dict:
    r = client.post(f"/v1/fields/{demo['field_id']}/planejamento/fitossanitario", json=corpo,
                    headers=token)
    assert r.status_code == 201, r.text
    return r.json()


def test_fila_risco_x_incerteza_x_impacto(client, agronomist_token, demo, ia, session) -> None:
    # duvidosa: ferrugem x cercosporiose quase empatadas, conjunto de 2
    _diagnostico(session, demo, "L01-P0003", label="Rust",
                 probs={"Rust": 0.48, "Cercospora_Leaf_Spot": 0.44, "Healthy": 0.08},
                 conjunto=["Rust", "Cercospora_Leaf_Spot"])
    # confiante: ferrugem a 0,95 — risco alto, incerteza baixa
    _diagnostico(session, demo, "L01-P0004", label="Rust",
                 probs={"Rust": 0.95, "Cercospora_Leaf_Spot": 0.03, "Healthy": 0.02})
    # sadia com discordância: risco baixo, incerteza 1
    _diagnostico(session, demo, "L01-P0005", label="Healthy",
                 probs={"Healthy": 0.9, "Rust": 0.1}, agreement=Agreement.DISAGREE)
    # a mesma planta, mais antiga: não repete
    _diagnostico(session, demo, "L01-P0003", label="Rust", probs={"Rust": 0.9, "Healthy": 0.1},
                 horas=30)
    # já revisada pelo agrônomo: fora
    _diagnostico(session, demo, "L01-P0006", label="Rust", probs={"Rust": 0.6, "Healthy": 0.4},
                 status=DiagnosisStatus.HUMAN_CONFIRMED)
    # risco do gêmeo maior que o visual
    _diagnostico(session, demo, "L01-P0001", label="Healthy",
                 probs={"Healthy": 0.7, "Rust": 0.3})
    session.commit()
    p = _fito(client, agronomist_token, demo)
    fila = p["resultado"]["fila_de_revisao"]
    plantas = [i["plant_ref"] for i in fila]
    assert sorted(plantas) == ["L01-P0001", "L01-P0003", "L01-P0004", "L01-P0005"]
    assert plantas[0] == "L01-P0003"
    por = {i["plant_ref"]: i for i in fila}
    d = por["L01-P0003"]
    assert d["risco"] == pytest.approx(0.92) and d["incerteza"] == pytest.approx(0.96)
    assert d["escore"] == pytest.approx(round(0.92 * 0.96, 4))
    assert por["L01-P0005"]["incerteza"] == 1.0 and "discordaram" in str(
        por["L01-P0005"]["motivos_da_incerteza"])
    assert por["L01-P0001"]["risco_por_fonte"] == {"visual": 0.3, "gemeo": 0.71}
    assert por["L01-P0001"]["risco"] == 0.71
    # pesos do agrônomo mudam a ordem; e ficam como premissa do pedido
    p2 = _fito(client, agronomist_token, demo, pesos_impacto={"Healthy": 5.0})
    assert p2["resultado"]["fila_de_revisao"][0]["plant_ref"] in ("L01-P0001", "L01-P0005")
    assert {x["codigo"]: x for x in p2["premissas"]}["pesos_impacto"]["origem"] == "pedido"


def test_historico_regioes_e_alternativas(client, agronomist_token, demo, ia, session) -> None:
    _diagnostico(session, demo, "L01-P0003", label="Rust",
                 probs={"Rust": 0.5, "Cercospora_Leaf_Spot": 0.4, "Healthy": 0.1})
    session.commit()
    res = _fito(client, agronomist_token, demo)["resultado"]
    h = res["historico_de_sintomas"][0]
    assert h["tendencia"] == "subiu" and h["incidencia_primeira_ultima"] == [0.05, 0.21]
    assert h["lesoes"]["por_estado"] == {"nova": 1, "persistente": 2}
    assert res["regioes_prioritarias"][0]["ruas"] == ["G3"]
    codigos = [a["codigo"] for a in res["alternativas_de_manejo"]]
    assert codigos == ["monitorar", "confirmar_em_campo", "inspecao_dirigida",
                       "tratamento_localizado", "tratamento_area_total"]
    texto = str(res["alternativas_de_manejo"]).lower()
    assert "l/ha" not in texto and "dose de bula" in texto
    loc = res["alternativas_de_manejo"][3]["evidencia"]["gemeo"]
    assert loc["plantas_com_risco_acima_do_limiar"] == 1 and loc["focos_no_horizonte"] == 2


def test_ia_fora_do_ar_vira_aviso(client, agronomist_token, demo, ia, session) -> None:
    from valtexa.planejamento.fitossanitario import IndisponivelError

    for k in ("evolucao", "lesoes", "previsao", "prioridades"):
        ia.respostas[k] = IndisponivelError("sem rede")
    _diagnostico(session, demo, "L01-P0003", label="Rust", probs={"Rust": 0.6, "Healthy": 0.4})
    session.commit()
    res = _fito(client, agronomist_token, demo)["resultado"]
    assert res["fila_de_revisao"] and res["regioes_prioritarias"] == []
    assert res["historico_de_sintomas"][0]["passadas"] is None
    assert any("gêmeo" in a for a in res["avisos"])


# -- rotação ----------------------------------------------------------------------------------


def _bula(session, chave: str, **meta) -> str:
    hoje = utcnow().date()
    m = {"chave": chave, "versao": "1", "titulo": f"Bula EXEMPLO {chave} (fictícia)",
         "tipo": "bula", "origem": "inventada no teste", "licenca": "teste",
         "culturas": ["coffee"], "alvos": ["Rust"], "verificado_em": hoje.isoformat(),
         "valido_ate": (hoje + timedelta(days=90)).isoformat(), **meta}
    doc, _ = conhecimento.ingerir(session, tenant_id=None, metadados=m,
                                  conteudo=f"EXEMPLO {chave}, não é bula real.")
    return doc.id


@pytest.fixture
def robo(client, admin_token, demo) -> str:
    return provision(client, admin_token, "DRONE_ACTION_V1", "PLN-PULV", demo["farm_id"]).device_id


def _produto(session, demo, nome: str, **extra) -> Product:
    p = Product(tenant_id=demo["tenant_id"], name=nome, allowed_crops=["coffee"],
                authorized_targets=["Rust"], registration_number="EXEMPLO-000",
                active_ingredient="ingrediente EXEMPLO", **extra)
    session.add(p)
    session.flush()
    return p


def test_rotacao_so_com_produto_com_fonte_vigente(client, agronomist_token, demo, ia, session,
                                                  robo) -> None:
    ok_a = _produto(session, demo, "A grupo 3", modo_de_acao="FRAC 3",
                    fonte_documento_id=_bula(session, "teste:a"))
    ok_b = _produto(session, demo, "B grupo 11", modo_de_acao="FRAC 11",
                    fonte_documento_id=_bula(session, "teste:b"))
    _produto(session, demo, "C sem fonte", modo_de_acao="FRAC 7")
    _produto(session, demo, "D vencida", modo_de_acao="FRAC 7",
             fonte_documento_id=_bula(session, "teste:d", verificado_em="2025-01-01",
                                      valido_ate="2025-06-30"))
    _produto(session, demo, "E não verificada", modo_de_acao="FRAC 7",
             fonte_documento_id=_bula(session, "teste:e", verificado_em=None, valido_ate=None))
    _produto(session, demo, "F fonte fictícia", modo_de_acao="FRAC 7",
             fonte_documento_id=_bula(session, "teste:f", ficticio=True))
    _produto(session, demo, "G sem modo", fonte_documento_id=_bula(session, "teste:g"))
    # histórico: duas aplicações seguidas do grupo 3 no talhão
    for i in range(2):
        m = Mission(tenant_id=demo["tenant_id"], farm_id=demo["farm_id"],
                    field_id=demo["field_id"], device_id=robo, kind=MissionKind.SPRAY,
                    state=MissionState.COMPLETED, target_polygon=_ret(0, 0),
                    product_id=ok_a.id)
        session.add(m)
        session.flush()
        session.add(Application(tenant_id=demo["tenant_id"], mission_id=m.id,
                                device_id=robo, field_id=demo["field_id"],
                                product_id=ok_a.id, state=ApplicationState.COMPLETED,
                                started_at=utcnow() - timedelta(days=40 - 20 * i),
                                amount_used_l=10.0))
    session.commit()
    rot = _fito(client, agronomist_token, demo)["resultado"]["rotacao"]
    assert [e["nome"] for e in rot["elegiveis"]] == ["B grupo 11", "A grupo 3"]
    motivos = {f["nome"]: f["motivo"] for f in rot["fora"]}
    assert motivos["C sem fonte"].startswith("sem fonte")
    assert "vencido em 2025-06-30" in motivos["D vencida"]
    assert "não verificado" in motivos["E não verificada"]
    assert "fictício" in motivos["F fonte fictícia"]
    assert motivos["G sem modo"] == "sem modo de ação cadastrado"
    assert any("Demo" in n for n in motivos)  # o produto da demonstração: sem modo/fonte
    assert rot["ultimo_grupo"] == "FRAC 3" and rot["seguidas_do_ultimo_grupo"] == 2
    a = next(e for e in rot["elegiveis"] if e["product_id"] == ok_a.id)
    assert a["repete_o_ultimo_grupo"] and "repete" in a["avaliacao"]  # sem limite: não julga
    com_limite = _fito(client, agronomist_token, demo,
                       max_seguidas_mesmo_grupo=2)["resultado"]["rotacao"]
    a = next(e for e in com_limite["elegiveis"] if e["product_id"] == ok_a.id)
    b = next(e for e in com_limite["elegiveis"] if e["product_id"] == ok_b.id)
    assert "passaria do limite de 2" in a["avaliacao"]
    assert b["avaliacao"].startswith("dentro do limite")
    assert "dose" in com_limite["nota"]


def test_cadastro_do_produto_com_fonte(client, agronomist_token, demo, session) -> None:
    doc = _bula(session, "teste:cad")
    session.commit()
    corpo = {"name": "Produto EXEMPLO", "registration_number": "EXEMPLO-1",
             "allowed_crops": ["coffee"], "modo_de_acao": "FRAC 3", "fonte_documento_id": doc}
    r = client.post("/v1/products", json=corpo, headers=agronomist_token)
    assert r.status_code == 201, r.text
    assert r.json()["modo_de_acao"] == "FRAC 3" and r.json()["fonte_documento_id"] == doc
    r = client.post("/v1/products", json={**corpo, "fonte_documento_id": "naoexiste"},
                    headers=agronomist_token)
    assert r.status_code == 422


# ---------------------------------------------------------------------------------------------
# Insumos
# ---------------------------------------------------------------------------------------------


def _aplicacoes(session, demo, robo: str, produto_id: str,
                consumos: list[tuple[int, float]]) -> None:
    for dias, litros in consumos:
        m = Mission(tenant_id=demo["tenant_id"], farm_id=demo["farm_id"],
                    field_id=demo["field_id"], device_id=robo, kind=MissionKind.SPRAY,
                    state=MissionState.COMPLETED, target_polygon=_ret(0, 0),
                    product_id=produto_id)
        session.add(m)
        session.flush()
        session.add(Application(tenant_id=demo["tenant_id"], mission_id=m.id,
                                device_id=robo, field_id=demo["field_id"],
                                product_id=produto_id, state=ApplicationState.COMPLETED,
                                started_at=utcnow() - timedelta(days=dias),
                                amount_used_l=litros))


def _insumos(client, token, **corpo) -> dict:
    r = client.post("/v1/planejamento/insumos", json=corpo, headers=token)
    assert r.status_code == 201, r.text
    return r.json()


def test_insumos_sem_historico_nao_estima(client, admin_token, demo) -> None:
    p = _insumos(client, admin_token)
    linha = p["resultado"]["produtos"][0]
    assert linha["estimativa"] is None and linha["reposicao"] is None
    assert linha["motivo"].startswith("sem histórico suficiente para estimar")


def test_insumos_cenarios_com_intervalo_e_reposicao(client, admin_token, demo,
                                                    session, robo) -> None:
    _aplicacoes(session, demo, robo, demo["product_id"],
                [(5, 30.0), (20, 25.0), (40, 10.0), (70, 40.0), (100, 12.0), (130, 35.0),
                 (160, 20.0), (200, 15.0), (250, 50.0), (300, 8.0)])
    for b in session.scalars(select(ProductBatch).where(
            ProductBatch.product_id == demo["product_id"])):
        b.quantity_l, b.expires_on = 20.0, utcnow().date() + timedelta(days=300)
    session.add(Mission(tenant_id=demo["tenant_id"], farm_id=demo["farm_id"],
                        field_id=demo["field_id"], device_id=robo, kind=MissionKind.SPRAY,
                        state=MissionState.DRAFT, target_polygon=_ret(0, 0),
                        product_id=demo["product_id"], authorized_quantity_l=8.0))
    session.commit()
    p = _insumos(client, admin_token, farm_id=demo["farm_id"])
    linha = next(x for x in p["resultado"]["produtos"] if x["product_id"] == demo["product_id"])
    est = linha["estimativa"]
    assert est["blocos"] == 12 and est["blocos_com_consumo"] == 9
    m, u = est["media_por_bloco_l"], est["um_bloco_l"]
    assert m["p10"] <= m["p50"] <= m["p90"] and u["p10"] <= u["p50"] <= u["p90"]
    assert u["p90"] > m["p90"]  # um bloco varia mais que a média
    assert linha["comprometido_l"] == 8.0 and linha["estoque_l"] >= 20.0
    rep = linha["reposicao"]
    assert rep["disponivel_l"] == pytest.approx(linha["estoque_l"] - 8.0)
    assert rep["possivel_reposicao"] is (rep["disponivel_l"] < u["p90"])
    # determinístico: o mesmo histórico dá o mesmo plano
    de_novo = _insumos(client, admin_token, farm_id=demo["farm_id"])
    assert de_novo["resultado"] == p["resultado"] and de_novo["sha256"] == p["sha256"]


def test_quantil_e_blocos() -> None:
    assert insumos.quantil([1, 2, 3, 4], 0.5) == 2.5
    agora = utcnow()
    bl = insumos.blocos([(agora - timedelta(days=1), 2.0), (agora - timedelta(days=31), 3.0)],
                        agora=agora, horizonte_dias=30, janela_dias=90, mesma_epoca=False)
    assert bl == [2.0, 3.0, 0.0]


# ---------------------------------------------------------------------------------------------
# Revisão humana, permissões, isolamento
# ---------------------------------------------------------------------------------------------


def test_revisao_por_tipo_e_hash(client, agronomist_token, operator_token, admin_token, demo,
                                 frota, ia, session, session_factory) -> None:
    fito = _fito(client, agronomist_token, demo)
    rob = _robotico(client, operator_token, demo)
    url = "/v1/planejamento/{}/revisao"
    # fitossanitário: só o agrônomo
    r = client.post(url.format(fito["id"]), json={"decisao": "aceito"}, headers=operator_token)
    assert r.status_code == 403
    r = client.post(url.format(fito["id"]), json={"decisao": "recusado"},
                    headers=agronomist_token)
    assert r.status_code == 422  # recusar pede comentário
    r = client.post(url.format(fito["id"]), json={"decisao": "aceito"},
                    headers=agronomist_token)
    assert r.status_code == 201 and r.json()["estado"] == "revisado"
    assert r.json()["revisoes"][0]["papel"] == "agronomist"
    # robótico: quem cria missão (o operador)
    r = client.post(url.format(rob["id"]), json={"decisao": "ajustar",
                                                 "comentario": "sem a G9"},
                    headers=operator_token)
    assert r.status_code == 201
    trilha = client.get(f"/v1/planejamento/{rob['id']}/auditoria", headers=admin_token).json()
    assert [t["acao"] for t in trilha] == ["planejamento.gerado", "planejamento.revisado"]
    # adulterado: não revisa
    with session_factory() as s:
        linha = s.get(PlanoDeApoio, rob["id"])
        linha.resultado = {**linha.resultado, "valor_alocado": 999}
        s.commit()
    r = client.post(url.format(rob["id"]), json={"decisao": "aceito"}, headers=operator_token)
    assert r.status_code == 422 and "hash" in r.json()["detail"]
    lista = client.get("/v1/planejamento", headers=admin_token).json()
    assert {x["tipo"] for x in lista} == {"fitossanitario", "robotico"}


def test_quem_pode_pedir_e_isolamento(client, demo, session_factory, ia,
                                     agronomist_token) -> None:
    from tests.conftest import DEMO_PASSWORD
    from tests.test_isolamento_openapi import _login
    from valtexa.models import Membership, Role, Tenant, User
    from valtexa.security.passwords import hash_password

    with session_factory() as s:
        tenant = s.scalars(select(Tenant)).first()
        u = User(email="visitante-pln@valtexa.dev", full_name="Visitante",
                 password_hash=hash_password(DEMO_PASSWORD))
        s.add(u)
        s.flush()
        s.add(Membership(tenant_id=tenant.id, user_id=u.id, role=Role.VIEWER))
        s.commit()
    token = _login(client, "visitante-pln@valtexa.dev")
    url = f"/v1/fields/{demo['field_id']}/planejamento/fitossanitario"
    assert client.post(url, json={}, headers=token).status_code == 403
    assert client.post("/v1/planejamento/insumos", json={}, headers=token).status_code == 403
    p = _fito(client, agronomist_token, demo)
    assert client.get(f"/v1/planejamento/{p['id']}", headers=token).status_code == 200
    assert client.post(f"/v1/planejamento/{p['id']}/revisao", json={"decisao": "aceito"},
                       headers=token).status_code == 403
    # outro talhão / plano de outro cliente: 404
    assert client.post("/v1/fields/naoexiste/planejamento/fitossanitario", json={},
                       headers=agronomist_token).status_code == 404
    assert client.get("/v1/planejamento/naoexiste", headers=token).status_code == 404
    assert client.post("/v1/planejamento/insumos", json={"farm_id": "naoexiste"},
                       headers=agronomist_token).status_code == 404


# -- calibração do 7.3 -------------------------------------------------------------------------


def _com_trecho_esquecido(ia, dias_sem_ver):
    base = ia.prioridades_fn

    def prioridades(field_id, params):
        corpo = base(field_id, params)
        if params["canal"] == "rover":
            corpo = {**corpo, "tarefas": [*corpo["tarefas"], {
                "tipo": "inspecao", "ruas": ["G12"], "x_inicio_m": 0.0, "x_fim_m": 19.6,
                "comprimento_m": 19.6, "area_m2": 68.6, "valor": 0.0,
                "poligono": _ret(0.0003, 0.0001), "plant_ids": ["p12"],
                "dias_sem_ver": dias_sem_ver, "motivo": "gêmeo certo de que está sadia"}]}
        return corpo

    ia.prioridades_fn = prioridades


def test_piso_de_vigilancia_nao_deixa_trecho_esquecido(client, operator_token, demo, frota,
                                                       ia) -> None:
    _com_trecho_esquecido(ia, 30)
    res = _robotico(client, operator_token, demo)["resultado"]
    g12 = next(i for i, t in res["tarefas"].items() if t["ruas"] == ["G12"])
    alocadas = {p["tarefa"] for r in res["rotas"] for p in r["passos"]}
    assert g12 in alocadas and res["piso_de_vigilancia"]["tarefas"] == [g12]
    assert res["tarefas"][g12]["motivo"].startswith("piso de vigilância: vista há 30 dias")
    # com o piso em 60 dias, o trecho visto há 30 continua com valor zero e não sai
    res = _robotico(client, operator_token, demo, piso_vigilancia_dias=60)["resultado"]
    g12 = next(i for i, t in res["tarefas"].items() if t["ruas"] == ["G12"])
    assert g12 not in {p["tarefa"] for r in res["rotas"] for p in r["passos"]}
    assert "valor zero" in {n["tarefa"]: n["motivo"] for n in res["nao_atribuidas"]}[g12]


def test_valor_minimo_por_minuto_evita_missao_excessiva(client, operator_token, demo, frota,
                                                        ia) -> None:
    p = _robotico(client, operator_token, demo, valor_minimo_por_minuto=1.5)
    res = p["resultado"]
    fora = {n["tarefa"]: n["motivo"] for n in res["nao_atribuidas"]}
    baixos = [i for i, t in res["tarefas"].items() if t["tipo"] == "inspecao" and t["valor"] < 2]
    assert baixos and all("abaixo do mínimo" in fora[i] for i in baixos)
    assert {x["codigo"]: x for x in p["premissas"]}["valor_minimo_por_minuto"]["origem"] == \
        "pedido"
    sem = _robotico(client, operator_token, demo)
    assert {x["codigo"]: x for x in sem["premissas"]}["valor_minimo_por_minuto"]["valor"] is None


def test_plano_do_enxame_usa_as_mesmas_restricoes(client, operator_token, demo, frota, ia,
                                                  session, monkeypatch) -> None:
    """O plano que cria as missões em RASCUNHO respeita a inclinação (e o resto) do 8.3."""
    from valtexa.models.enxame import PlanoDoEnxame
    from valtexa.services import plant_map

    monkeypatch.setattr(plant_map, "prioridades_gemeo", ia.prioridades_fn)
    campo = session.get(Field, demo["field_id"])
    campo.relief = {"declividade_maxima_deg": 21.0, "declividade_media_deg": 12.0,
                    "fonte": "teste"}
    session.commit()
    r = client.post(f"/v1/fields/{demo['field_id']}/enxame/plano", json={},
                    headers=operator_token)
    assert r.status_code == 200, r.text
    plano = r.json()
    assert {a["tipo"] for a in plano["atribuicoes"]} == {"drone"}
    assert any("declividade máxima medida 21°" in n["motivo"] for n in plano["nao_atribuidas"])
    session.expire_all()
    linha = session.get(PlanoDoEnxame, plano["plano_id"])
    assert {p["codigo"] for p in linha.entradas["premissas"]} >= {
        "relevo", "bytes_por_metro", "piso_vigilancia_dias", "valor_minimo_por_minuto"}
