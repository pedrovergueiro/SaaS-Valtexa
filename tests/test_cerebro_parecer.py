"""Parecer do cérebro agronômico (8.2): dossiê, compositor determinístico, provedor e revisão.

A IA (fusão, lesões, evolução, gêmeo, clima) é um **dublê** (:class:`IADuble`): os números
abaixo são inventados para o teste, não saíram de modelo nenhum — os pesos reais não estão
neste repositório. As fontes de conhecimento usadas aqui são **fictícias**.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from tests.helpers import provision, upload_observation
from valtexa.api.routers import cerebro as rotas
from valtexa.cerebro import dossie, parecer, provedor
from valtexa.cerebro.validador import Validador
from valtexa.main import app
from valtexa.models import Detection, Diagnosis, Observation, PlatformRole, utcnow
from valtexa.models.cerebro import Parecer

PLANTA = "L22-P0114"


class IADuble:
    """Respostas fixas, no formato das rotas do VALTEXA-B. Números de teste."""

    def __init__(self, **troca: Any) -> None:
        hoje = utcnow().date()
        self.respostas: dict[str, Any] = {
            "planta": {"plant_id": PLANTA, "row_id": "L22", "pass_id": "m-7", "time": None,
                       "status": "suspeita", "primary_disease": "Rust",
                       "primary_posterior": 0.6193, "posteriors": {
                           "Rust": 0.6193, "Cercospora_Leaf_Spot": 0.2071, "Healthy": 0.1736},
                       "incidence": 0.18, "n_tiles": 14, "n_frames": 3, "n_cameras": 2,
                       "effective_views": 2.4, "n_needs_review": 0,
                       "n_tiles_out_of_scope": 1, "calibration_id": None},
            "evolucao": {"plant_id": PLANTA, "history": [
                {"pass_id": "m-5", "status": "sadia", "primary_disease": None,
                 "incidence": 0.0},
                {"pass_id": "m-6", "status": "suspeita", "primary_disease": "Rust",
                 "incidence": 0.07}],
                "changes": [{"change": "primeira"}, {"change": "nova_infeccao"}],
                "audpc": 0.245, "audpc_unit": "incidencia*dia"},
            "lesoes": {"plant_id": PLANTA, "passes": ["m-6", "m-7"], "tracks": [
                {"id": "L1", "disease": "Rust", "state": "persistente", "face": "abaxial",
                 "position": {"x_m": 0.1, "height_m": 0.9, "canopy_depth_m": 0.2}},
                {"id": "L2", "disease": "Rust", "state": "nova", "face": "indeterminada",
                 "position": {"x_m": 0.3, "height_m": 1.1, "canopy_depth_m": None}}]},
            "previsao": {"doenca": "Rust", "data_base": (hoje - timedelta(days=2)).isoformat(),
                         "horizonte": (hoje + timedelta(days=12)).isoformat(), "membros": 16,
                         "parametros_ajustados": False, "origem_parametros": "literatura",
                         "infectadas_no_horizonte_esperado": 41.37,
                         "infectadas_no_horizonte_p10_p90": [30.1, 55.8],
                         "janelas_de_infeccao": [{"inicio": "x"}], "focos_no_horizonte": 2,
                         "avisos": [], "plantas_detalhe": [
                             {"plant_id": PLANTA, "risco": 0.4412, "risco_p10": 0.2803,
                              "risco_p90": 0.6105, "esporulando_agora": 0.21,
                              "latente_agora": 0.12, "sinal_no_horizonte": 0.39}]},
            "clima": {"dias": 16, "serie": [
                {"data": (hoje - timedelta(days=i)).isoformat(), "t_media": 21.0 + i % 3,
                 "t_min": 15.0, "t_max": 27.0, "ur_media": 82.0, "chuva_mm": 1.5,
                 "molhamento_h": 9.0, "molhamento_medido": False,
                 "fonte": "estacao"} for i in range(1, 11)] + [
                {"data": (hoje - timedelta(days=i)).isoformat(), "t_media": 20.0, "t_min": 14,
                 "t_max": 26, "ur_media": 90, "chuva_mm": 5, "molhamento_h": 12,
                 "molhamento_medido": False, "fonte": "open-meteo:previsao"} for i in (11, 12)]},
        }
        self.respostas.update(troca)

    def _r(self, chave: str):
        valor = self.respostas.get(chave)
        if isinstance(valor, Exception):
            raise valor
        return valor

    def planta(self, field_id, plant_ref):
        return self._r("planta")

    def evolucao(self, field_id, plant_ref):
        return self._r("evolucao")

    def lesoes(self, field_id, plant_ref):
        return self._r("lesoes")

    def previsao(self, field_id, doenca, horizonte_dias):
        return self._r("previsao")

    def clima(self, field_id):
        return self._r("clima")


@pytest.fixture
def ia() -> IADuble:
    duble = IADuble()
    app.dependency_overrides[rotas.fonte_da_ia] = lambda: duble
    yield duble
    app.dependency_overrides.pop(rotas.fonte_da_ia, None)


@pytest.fixture
def caso(client: TestClient, demo: dict, admin_token: dict, session: Session) -> dict:
    """Uma observação de ferrugem (simulada) na planta, com conjunto conformal de 2 classes."""
    rover = provision(client, admin_token, "ROVER_SCOUT_V1", "CER-ROVER", demo["farm_id"])
    r = upload_observation(rover, demo["field_id"], label="Rust")
    assert r.status_code in (200, 201), r.text
    obs = session.scalars(select(Observation)).one()
    obs.plant_ref = PLANTA
    diag = session.scalars(select(Diagnosis).where(Diagnosis.observation_id == obs.id)).one()
    det = session.get(Detection, diag.primary_detection_id)
    det.signals = {**(det.signals or {}), "prediction_set": ["Rust", "Cercospora_Leaf_Spot"],
                   "in_scope": True, "scene": "folha_cafe"}
    session.commit()
    return {"observation_id": obs.id, "diagnosis_id": diag.id, "field_id": demo["field_id"]}


def _gera(client, token, alvo, **corpo) -> dict:
    pedido = corpo or {"caso": "planta", "plant_ref": PLANTA}
    r = client.post(f"/v1/fields/{alvo['field_id']}/pareceres", json=pedido, headers=token)
    assert r.status_code == 201, r.text
    return r.json()


def _bula(client, equipe_token, **extra) -> dict:
    meta = {"chave": "teste:bula-exemplo", "versao": "1", "titulo": "Bula EXEMPLO (fictícia)",
            "tipo": "bula", "origem": "texto inventado no teste", "licenca": "teste",
            "culturas": ["coffee"], "alvos": ["Rust"], **extra}
    r = client.post("/v1/platform/cerebro/fontes", headers=equipe_token, json={
        "metadados": meta, "conteudo": "EXEMPLO de teste, não é bula: alvo ferrugem."})
    assert r.status_code == 201, r.text
    return r.json()


# -- o parecer determinístico -----------------------------------------------------------------


def test_parecer_deterministico_com_dossie_alternativas_e_sem_fonte(
        client, agronomist_token, caso, ia, session) -> None:
    p = _gera(client, agronomist_token, caso)
    assert (p["modo"], p["provedor"], p["estado"]) == ("deterministico", None,
                                                       "aguardando_revisao")
    assert p["hipotese_principal"] == "Rust" and "Cercospora_Leaf_Spot" in p["alternativas"]
    tipos = [i["tipo"] for i in p["dossie"]["itens"]]
    assert tipos == ["caso", "visual", "fusao_planta", "lesoes_3d", "evolucao", "historico",
                     "gemeo", "clima", "regras"]
    for item in p["dossie"]["itens"]:  # cada item com origem e limitações declaradas
        assert item["origem"]["sistema"] in ("plataforma", "ia", "rover")
        assert isinstance(item["limitacoes"], list)
    fusao = next(i for i in p["dossie"]["itens"] if i["tipo"] == "fusao_planta")
    assert any("sem calibração" in lim for lim in fusao["limitacoes"])
    clima = next(i for i in p["dossie"]["itens"] if i["tipo"] == "clima")
    assert clima["dados"]["dias"] == 10 and clima["dados"]["por_fonte"] == {"estacao": 10}
    assert any("previsão" in lim for lim in clima["limitacoes"])  # os 2 dias de previsão saem
    # toda afirmação cita, e o próprio validador aceita o texto do compositor
    assert p["afirmacoes"] and all(a["citacoes"] for a in p["afirmacoes"])
    assert p["recusas"] == []
    texto = p["texto"]
    assert "maior compatibilidade com ferrugem (Rust)" in texto
    assert "probabilidade estimada 0,62" in texto
    assert "Hipóteses alternativas" in texto and "cercosporiose" in texto
    assert "Sem fonte no repositório" in texto
    # as 8 verificações, nenhuma "ok"; sem fonte regulatória → sem_fonte
    v = {x["codigo"]: x["situacao"] for x in p["verificacoes"]}
    assert list(v) == [c for c, _ in parecer.VERIFICACOES]
    assert set(v.values()) <= {"a_verificar", "sem_fonte", "bloqueado", "sem_dado"}
    assert all(v[c] == "sem_fonte" for c in parecer.REGULATORIAS)
    assert v["condicoes_ambientais"] == "a_verificar"
    assert texto.rstrip().endswith(parecer.FECHO)
    assert "Safety Engine" in parecer.FECHO and "revisada pelo profissional" in parecer.FECHO
    assert p["integro"] is True
    # o mesmo caso, o mesmo banco, a mesma IA: o mesmo dossiê (fora o horário)
    p2 = _gera(client, agronomist_token, caso)
    a, b = (session.get(Parecer, x["id"]) for x in (p, p2))
    sem_hora = [{**i} for i in a.dossie["itens"] if i["tipo"] != "historico"]
    assert sem_hora == [i for i in b.dossie["itens"] if i["tipo"] != "historico"]


def test_compositor_sempre_passa_no_proprio_validador(client, agronomist_token, caso, ia,
                                                      session) -> None:
    """Varia o dossiê (IA fora, sem clima, sem gêmeo, só observação) e valida cada parecer."""
    variantes = [
        {}, {"planta": dossie.IndisponivelError("fora do ar")}, {"clima": None},
        {"previsao": None}, {"lesoes": None, "evolucao": None},
        {"clima": {"serie": [{"data": "2000-01-01", "fonte": "estacao", "t_media": 1,
                              "ur_media": 1, "chuva_mm": 1, "molhamento_h": 1}]}},
    ]
    for troca in variantes:
        ia.respostas = IADuble(**troca).respostas
        for corpo in ({"caso": "planta", "plant_ref": PLANTA},
                      {"caso": "observacao", "observation_id": caso["observation_id"]}):
            p = _gera(client, agronomist_token, caso, **corpo)
            linha = session.get(Parecer, p["id"])
            assert Validador(linha.dossie, linha.fontes).valida(linha.afirmacoes) == [], troca
            assert p["recusas"] == []


def test_ia_fora_do_ar_vira_item_indisponivel_e_o_parecer_sai(client, agronomist_token, caso,
                                                             ia) -> None:
    erro = dossie.IndisponivelError("Serviço de inferência fora do ar")
    ia.respostas = IADuble(planta=erro, evolucao=erro, lesoes=erro, previsao=erro,
                           clima=erro).respostas
    p = _gera(client, agronomist_token, caso)
    indisponiveis = {i["tipo"] for i in p["dossie"]["itens"] if not i["disponivel"]}
    assert {"fusao_planta", "lesoes_3d", "evolucao", "gemeo", "clima"} <= indisponiveis
    assert p["hipotese_principal"] == "Rust"  # sobra a classificação da imagem
    assert "O classificador apresentou maior compatibilidade" in p["texto"]
    assert {x["codigo"]: x["situacao"] for x in p["verificacoes"]}[
        "condicoes_ambientais"] == "sem_dado"


def test_clima_so_de_previsao_nao_entra(client, agronomist_token, caso, ia) -> None:
    hoje = utcnow().date()
    ia.respostas["clima"] = {"serie": [
        {"data": (hoje - timedelta(days=1)).isoformat(), "fonte": "open-meteo:previsao",
         "t_media": 20, "ur_media": 90, "chuva_mm": 3, "molhamento_h": 10},
        {"data": (hoje - timedelta(days=2)).isoformat(), "fonte": "climatologia",
         "t_media": 20, "ur_media": 90, "chuva_mm": 3, "molhamento_h": 10}]}
    p = _gera(client, agronomist_token, caso)
    clima = next(i for i in p["dossie"]["itens"] if i["tipo"] == "clima")
    assert not clima["disponivel"] and "não fala de clima" in clima["motivo_indisponivel"]
    assert "## Clima" not in p["texto"]


def test_caso_observacao_e_validacoes_do_pedido(client, agronomist_token, caso, ia,
                                                demo) -> None:
    p = _gera(client, agronomist_token, caso, caso="observacao",
              observation_id=caso["observation_id"])
    assert p["caso_tipo"] == "observacao" and p["plant_ref"] == PLANTA
    base = f"/v1/fields/{caso['field_id']}/pareceres"
    assert client.post(base, json={"caso": "planta"},
                       headers=agronomist_token).status_code == 422
    assert client.post(base, json={"caso": "observacao", "observation_id": "x" * 32},
                       headers=agronomist_token).status_code == 404
    assert client.post(base, json={"caso": "planta", "plant_ref": "../x"},
                       headers=agronomist_token).status_code == 422


# -- fontes e o bloqueio regulatório -------------------------------------------------------


def test_regulatorio_nao_verificado_bloqueia_e_verificado_vira_a_verificar(
        client, agronomist_token, caso, ia, equipe) -> None:
    token = equipe(PlatformRole.IA_DADOS)
    bula = _bula(client, token)
    assert bula["uso_operacional"] is False and bula["bloqueio"] == "não verificado na versão " \
                                                                    "vigente"
    p = _gera(client, agronomist_token, caso)
    v = {x["codigo"]: x for x in p["verificacoes"]}
    assert all(v[c]["situacao"] == "bloqueado" for c in parecer.REGULATORIAS)
    assert "não verificado" in v["registro_vigente"]["detalhe"]
    f = p["fontes"][0]
    assert (f["tipo"], f["uso_operacional"], f["titulo"]) == ("bula", False,
                                                              "Bula EXEMPLO (fictícia)")
    assert "bloqueada para uso operacional" in p["texto"]
    # a equipe confere contra a oficial: passa a "a verificar" (nunca "ok")
    hoje = utcnow().date()
    r = client.post(f"/v1/platform/cerebro/fontes/{bula['id']}/verificacao", headers=token,
                    json={"verificado_em": hoje.isoformat(),
                          "valido_ate": (hoje + timedelta(days=180)).isoformat()})
    assert r.status_code == 200 and r.json()["uso_operacional"] is True
    p = _gera(client, agronomist_token, caso)
    v = {x["codigo"]: x for x in p["verificacoes"]}
    assert all(v[c]["situacao"] == "a_verificar" for c in parecer.REGULATORIAS)
    assert "O parecer não indica dose" in v["dose_de_bula"]["detalhe"]
    # vencida: bloqueia de novo
    r = client.post(f"/v1/platform/cerebro/fontes/{bula['id']}/verificacao", headers=token,
                    json={"verificado_em": (hoje - timedelta(days=400)).isoformat(),
                          "valido_ate": (hoje - timedelta(days=1)).isoformat()})
    assert r.json()["bloqueio"].startswith("vencido em")
    p = _gera(client, agronomist_token, caso)
    assert {x["codigo"]: x["situacao"] for x in p["verificacoes"]}[
        "registro_vigente"] == "bloqueado"


def test_ficticio_e_marcado_e_nunca_operacional(client, agronomist_token, caso, ia,
                                                equipe) -> None:
    token = equipe(PlatformRole.IA_DADOS)
    hoje = utcnow().date()
    _bula(client, token, ficticio=True, verificado_em=hoje.isoformat(),
          valido_ate=(hoje + timedelta(days=30)).isoformat())
    p = _gera(client, agronomist_token, caso)
    assert "FICTÍCIA (dado de teste)" in p["texto"]
    assert {x["codigo"]: x["situacao"] for x in p["verificacoes"]}[
        "registro_vigente"] == "bloqueado"


def test_permissoes_das_fontes(client, agronomist_token, operator_token, admin_token, equipe,
                               caso) -> None:
    corpo = {"metadados": {"chave": "historico:talhao", "versao": "2025", "titulo": "Safra 2025",
                           "tipo": "historico_propriedade", "origem": "caderno de campo",
                           "licenca": "do cliente", "culturas": ["coffee"],
                           "ficticio": True},
             "conteudo": "Histórico fictício: ferrugem na rua 22 em março."}
    assert client.post("/v1/cerebro/fontes", json=corpo,
                       headers=operator_token).status_code == 403
    r = client.post("/v1/cerebro/fontes", json=corpo, headers=agronomist_token)
    assert r.status_code == 201 and r.json()["escopo"] == "cliente"
    # cliente não ingere nem verifica fonte da plataforma
    assert client.post("/v1/platform/cerebro/fontes", json=corpo,
                       headers=admin_token).status_code == 403
    bula = _bula(client, equipe(PlatformRole.IA_DADOS))
    assert client.post(f"/v1/cerebro/fontes/{bula['id']}/verificacao", headers=agronomist_token,
                       json={"verificado_em": "2026-10-01", "valido_ate": "2027-01-01"}
                       ).status_code == 403
    assert client.post("/v1/platform/cerebro/fontes", json=corpo,
                       headers=equipe(PlatformRole.COMERCIAL)).status_code == 403
    lista = client.get("/v1/cerebro/fontes", headers=operator_token).json()
    assert {d["escopo"] for d in lista} == {"cliente", "plataforma"}
    achado = client.get("/v1/cerebro/busca", params={"q": "ferrugem rua", "cultura": "coffee"},
                        headers=operator_token).json()
    assert achado and achado[0]["chave"] == "historico:talhao"


# -- provedor de linguagem (dublê) e o validador -------------------------------------------


class ProvedorDuble:
    nome = "duble"

    def __init__(self, resposta) -> None:
        self.resposta = resposta
        self.pedidos: list[provedor.PedidoDeRedacao] = []

    def redigir(self, pedido):
        self.pedidos.append(pedido)
        if isinstance(self.resposta, Exception):
            raise self.resposta
        return self.resposta(pedido) if callable(self.resposta) else self.resposta


@pytest.fixture
def liga_provedor(monkeypatch):
    def liga(resposta) -> ProvedorDuble:
        duble = ProvedorDuble(resposta)
        provedor.registrar("duble", lambda: duble)
        monkeypatch.setattr(rotas, "settings",
                            rotas.settings.model_copy(update={"cerebro_provedor": "duble"}))
        return duble

    yield liga
    provedor.remover("duble")


def _ids(pedido, tipo):
    return next(i["id"] for i in pedido.dossie["itens"] if i["tipo"] == tipo)


def test_provedor_desligado_por_padrao_nao_chama_nada(client, agronomist_token, caso, ia,
                                                     monkeypatch) -> None:
    assert rotas.settings.cerebro_provedor == provedor.DESLIGADO
    chamado = []
    provedor.registrar("espiao", lambda: chamado.append(1))
    try:
        p = _gera(client, agronomist_token, caso)
    finally:
        provedor.remover("espiao")
    assert p["modo"] == "deterministico" and chamado == []


def test_provedor_com_texto_valido_e_aceito(client, agronomist_token, caso, ia,
                                            liga_provedor) -> None:
    def redige(pedido):
        fusao = _ids(pedido, "fusao_planta")
        visual = _ids(pedido, "visual")
        return [
            {"secao": "hipoteses", "texto": "A fusão estima probabilidade de 0,62 para "
             "ferrugem nesta planta.", "citacoes": [fusao]},
            {"secao": "hipoteses", "texto": "Cercosporiose segue como hipótese alternativa no "
             "conjunto conformal.", "citacoes": [visual]},
        ]

    duble = liga_provedor(redige)
    p = _gera(client, agronomist_token, caso)
    assert (p["modo"], p["provedor"], p["recusas"]) == ("provedor", "duble", [])
    assert "probabilidade de 0,62" in p["texto"]
    # verificações e fecho não vêm do provedor
    assert p["texto"].rstrip().endswith(parecer.FECHO) and len(p["verificacoes"]) == 8
    pedido = duble.pedidos[0]
    assert pedido.rascunho and pedido.regras == provedor.REGRAS
    assert pedido.imagens and pedido.imagens[0]["observation_id"] == caso["observation_id"]


@pytest.mark.parametrize(("afirmacao", "motivo"), [
    ({"texto": "A planta tem ferrugem.", "citacoes": []}, "sem_citacao"),
    ({"texto": "Ferrugem provável.", "citacoes": ["E99"]}, "citacao_inexistente"),
    ({"texto": "Probabilidade de 0,91 para ferrugem.", "citacoes": ["FUSAO"]},
     "numero_sem_evidencia:0,91"),
    ({"texto": "Certamente é ferrugem.", "citacoes": ["FUSAO"]}, "linguagem_de_certeza"),
    ({"texto": "Diagnóstico confirmado de ferrugem.", "citacoes": ["FUSAO"]},
     "linguagem_de_certeza"),
    ({"texto": "Aplicar fungicida a 2 L/ha imediatamente.", "citacoes": ["FUSAO"]},
     "recomendacao_operacional"),
])
def test_validador_recusa_e_o_parecer_cai_no_deterministico(
        client, agronomist_token, caso, ia, liga_provedor, afirmacao, motivo) -> None:
    def redige(pedido):
        cit = [_ids(pedido, "fusao_planta") if c == "FUSAO" else c
               for c in afirmacao["citacoes"]]
        return [{**afirmacao, "citacoes": cit}]

    liga_provedor(redige)
    p = _gera(client, agronomist_token, caso)
    assert p["modo"] == "deterministico" and p["provedor"] == "duble"
    motivos = [m for r in p["recusas"] for x in r["recusas"] for m in x["motivos"]]
    assert motivo in motivos
    assert "maior compatibilidade com ferrugem" in p["texto"]  # o texto determinístico


def test_validador_aceita_numero_com_menos_casas_e_percentual() -> None:
    d = {"itens": [{"id": "E1", "tipo": "fusao_planta", "titulo": "x", "dados": {
        "posterior": 0.6193, "quadros": 3, "passada": "m-7", "quando": "2026-10-17"},
        "limitacoes": [], "motivo_indisponivel": None}], "hipoteses": {}}
    v = Validador(d, [])
    for texto in ("posterior 0,62 em 3 quadros", "62% de probabilidade estimada",
                  "passada m-7 de 2026-10-17", "posterior 0.6193"):
        assert v.recusas({"texto": texto, "citacoes": ["E1"]}) == [], texto
    assert v.recusas({"texto": "posterior 0,7", "citacoes": ["E1"]}) == [
        "numero_sem_evidencia:0,7"]
    assert v.recusas({"texto": "0,62 com certeza", "citacoes": ["E1"]}) == [
        "linguagem_de_certeza"]
    assert v.recusas({"texto": "não está confirmado", "citacoes": ["E1"]}) == []


def test_validador_fonte_bloqueada_so_com_aviso() -> None:
    fonte = {"id": "F1", "texto": "EXEMPLO", "titulo": "Bula", "versao": "1", "secao": None,
             "bloqueio": "vencido em 2026-01-01", "origem": "x", "regulatorio": True,
             "uso_operacional": False, "ficticio": False}
    v = Validador({"itens": [], "hipoteses": {}}, [fonte])
    assert v.recusas({"texto": "A bula lista a ferrugem.", "citacoes": ["F1"]}) == [
        "fonte_bloqueada:F1"]
    assert v.recusas({"texto": "A bula está vencida: não serve para a operação.",
                      "citacoes": ["F1"]}) == []


def test_provedor_que_falha_ou_responde_lixo_cai_no_deterministico(
        client, agronomist_token, caso, ia, liga_provedor) -> None:
    liga_provedor(RuntimeError("tempo esgotado"))
    p = _gera(client, agronomist_token, caso)
    assert p["modo"] == "deterministico" and "tempo esgotado" in p["recusas"][0]["erro"]
    liga_provedor([])
    p = _gera(client, agronomist_token, caso)
    assert p["modo"] == "deterministico" and p["recusas"]


def test_provedor_desconhecido_na_configuracao_e_erro(client, agronomist_token, caso, ia,
                                                      monkeypatch) -> None:
    monkeypatch.setattr(rotas, "settings",
                        rotas.settings.model_copy(update={"cerebro_provedor": "nao-existe"}))
    r = client.post(f"/v1/fields/{caso['field_id']}/pareceres",
                    json={"caso": "planta", "plant_ref": PLANTA}, headers=agronomist_token)
    assert r.status_code == 503 and "não registrado" in r.json()["detail"]


# -- revisão do agrônomo e auditoria ---------------------------------------------------------


def test_revisao_do_agronomo_com_quem_quando_e_trilha(client, agronomist_token, admin_token,
                                                      operator_token, caso, ia) -> None:
    p = _gera(client, admin_token, caso)  # o gestor pode pedir
    url = f"/v1/pareceres/{p['id']}/revisao"
    assert client.post(url, json={"decisao": "concorda"},
                       headers=admin_token).status_code == 403  # só o agrônomo revisa
    assert client.post(url, json={"decisao": "discorda"},
                       headers=agronomist_token).status_code == 422  # discordar pede motivo
    assert client.post(url, json={"decisao": "autoriza"},
                       headers=agronomist_token).status_code == 422
    r = client.post(url, json={"decisao": "discorda", "comentario": "lesão de phoma, não "
                               "ferrugem", "diagnostico_revisor": "Phoma_Leaf_Spot"},
                    headers=agronomist_token)
    assert r.status_code == 201, r.text
    corpo = r.json()
    assert corpo["estado"] == "revisado"
    rev = corpo["revisoes"][0]
    assert rev["decisao"] == "discorda" and rev["papel"] == "agronomist"
    assert rev["revisor_id"] and rev["revisado_em"] and rev["parecer_sha256"] == p["sha256"]
    assert "não autoriza" in corpo["aviso"]
    trilha = client.get(f"/v1/pareceres/{p['id']}/auditoria", headers=operator_token).json()
    assert [e["acao"] for e in trilha] == ["parecer.gerado", "parecer.revisado"]
    assert trilha[1]["dados"]["decisao"] == "discorda" and trilha[1]["ator_id"] == rev[
        "revisor_id"]
    # o próximo parecer da planta mostra a revisão no histórico
    p2 = _gera(client, agronomist_token, caso)
    hist = next(i for i in p2["dossie"]["itens"] if i["tipo"] == "historico")
    assert hist["dados"]["pareceres_anteriores"][0]["revisoes"][0]["decisao"] == "discorda"


def test_parecer_adulterado_nao_e_revisado(client, agronomist_token, caso, ia,
                                           session) -> None:
    p = _gera(client, agronomist_token, caso)
    linha = session.get(Parecer, p["id"])
    linha.texto = linha.texto.replace("0,62", "0,99")
    session.commit()
    assert client.get(f"/v1/pareceres/{p['id']}", headers=agronomist_token).json()[
        "integro"] is False
    r = client.post(f"/v1/pareceres/{p['id']}/revisao", json={"decisao": "concorda"},
                    headers=agronomist_token)
    assert r.status_code == 422 and "hash" in r.json()["detail"]


def test_papeis_que_nao_geram(client, caso, ia, session_factory) -> None:
    from tests.conftest import DEMO_PASSWORD
    from tests.test_isolamento_openapi import _login
    from valtexa.models import Membership, Role, Tenant, User
    from valtexa.security.passwords import hash_password

    with session_factory() as s:
        tenant = s.scalars(select(Tenant)).first()
        u = User(email="visitante@valtexa.dev", full_name="Visitante",
                 password_hash=hash_password(DEMO_PASSWORD))
        s.add(u)
        s.flush()
        s.add(Membership(tenant_id=tenant.id, user_id=u.id, role=Role.VIEWER))
        s.commit()
    token = _login(client, "visitante@valtexa.dev")
    r = client.post(f"/v1/fields/{caso['field_id']}/pareceres",
                    json={"caso": "planta", "plant_ref": PLANTA}, headers=token)
    assert r.status_code == 403
    assert client.get(f"/v1/fields/{caso['field_id']}/pareceres", headers=token).status_code \
        == 200


def test_data_do_dossie_e_formato_dos_numeros() -> None:
    assert parecer.num(0.6193) == "0,62" and parecer.num(3) == "3" and parecer.num(2.0) == "2"
    assert parecer.num(21.34, 1) == "21,3"
    assert date.fromisoformat(utcnow().date().isoformat())
