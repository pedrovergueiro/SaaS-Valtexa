"""O agrônomo ensinando a IA: a lição na fila e no parecer, o parecer que cita, o corte que leva."""

from __future__ import annotations

import io
import json
import zipfile

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from tests.test_cerebro_parecer import PLANTA, _gera, caso, ia  # noqa: F401
from valtexa.models import DatasetSample, Diagnosis, LicaoAgronomo

POR_QUE = {"sintomas": ["pústulas alaranjadas (pó) na face de baixo"], "estrato": "terco_inferior",
           "face": "abaxial", "porque": "pó alaranjado que sai no dedo, folhas velhas"}
LESAO = {"x": 0.2, "y": 0.3, "w": 0.1, "h": 0.15}


def _revisa(client, token, diag_id, **extra):
    corpo = {"label": "Rust", "confirmed": True, **extra}
    return client.post(f"/v1/diagnoses/{diag_id}/review", json=corpo, headers=token)


def test_fila_grava_o_porque_e_as_lesoes(client, agronomist_token, caso, ia,  # noqa: F811
                                         session: Session) -> None:
    r = _revisa(client, agronomist_token, caso["diagnosis_id"], explicacao=POR_QUE,
                lesoes=[LESAO])
    assert r.status_code == 200, r.text
    [licao] = session.scalars(select(LicaoAgronomo)).all()
    assert (licao.origem, licao.rotulo, licao.estrato, licao.face) == (
        "fila", "Rust", "terco_inferior", "abaxial")
    assert licao.lesoes == [[0.2, 0.3, 0.1, 0.15]] and licao.plant_ref == PLANTA
    assert licao.porque.startswith("pó alaranjado") and licao.autor_rotulo

    painel = client.get("/v1/ensino/painel", headers=agronomist_token).json()
    assert painel["licoes"] == 1 and painel["com_lesao_marcada"] == 1
    assert painel["com_porque"] == 1 and painel["por_rotulo"] == {"Rust": 1}
    licoes = client.get(f"/v1/fields/{caso['field_id']}/licoes", headers=agronomist_token)
    assert licoes.json()[0]["lesoes"] == 1


def test_lesao_fora_da_foto_e_recusada_sem_mudar_nada(client, agronomist_token, caso,  # noqa: F811
                                                       session: Session) -> None:
    r = _revisa(client, agronomist_token, caso["diagnosis_id"],
                lesoes=[{"x": 0.9, "y": 0.1, "w": 0.3, "h": 0.1}])
    assert r.status_code == 422
    session.expire_all()
    assert session.get(Diagnosis, caso["diagnosis_id"]).reviewed_label is None
    assert session.scalars(select(LicaoAgronomo)).all() == []


def test_imagem_sem_condicao_nao_ensina(client, agronomist_token, caso,  # noqa: F811
                                        session: Session) -> None:
    r = _revisa(client, agronomist_token, caso["diagnosis_id"], label="Imagem_sem_condicao",
                confirmed=False)
    assert r.status_code == 200
    assert session.scalars(select(LicaoAgronomo)).all() == []


def test_o_parecer_cita_o_que_o_agronomo_ensinou(client, agronomist_token, caso, ia,  # noqa: F811
                                                 session: Session) -> None:
    assert _revisa(client, agronomist_token, caso["diagnosis_id"],
                   explicacao=POR_QUE).status_code == 200
    p = _gera(client, agronomist_token, caso)
    licoes = [a for a in p["afirmacoes"] if a["secao"] == "licoes"]
    assert len(licoes) == 1 and "pó alaranjado" in licoes[0]["texto"]
    assert "neste talhão" in licoes[0]["texto"] and "terco_inferior" in licoes[0]["texto"]
    assert p["recusas"] == []  # o compositor passou no próprio validador


def test_numero_no_texto_do_agronomo_fica_no_dossie(client, agronomist_token, caso, ia,  # noqa: F811
                                                    session: Session) -> None:
    com_numero = {**POR_QUE, "porque": "vi em 30% das folhas do terço de baixo"}
    _revisa(client, agronomist_token, caso["diagnosis_id"], explicacao=com_numero)
    p = _gera(client, agronomist_token, caso)
    [licao] = [a for a in p["afirmacoes"] if a["secao"] == "licoes"]
    assert "30%" not in licao["texto"] and "pústulas" in licao["texto"]
    assert p["recusas"] == []


def test_discordar_do_parecer_vira_licao_e_pode_registrar_o_diagnostico(
        client, agronomist_token, caso, ia, session: Session) -> None:  # noqa: F811
    p = _gera(client, agronomist_token, caso, caso="observacao",
              observation_id=caso["observation_id"])
    r = client.post(f"/v1/pareceres/{p['id']}/revisao", headers=agronomist_token, json={
        "decisao": "discorda", "diagnostico_revisor": "Cercospora_Leaf_Spot",
        "comentario": "o centro é claro, olho-de-pomba"})
    assert r.status_code == 201, r.text
    [licao] = session.scalars(select(LicaoAgronomo)).all()
    assert (licao.origem, licao.rotulo, licao.parecer_id) == (
        "parecer", "Cercospora_Leaf_Spot", p["id"])
    session.expire_all()
    assert session.get(Diagnosis, caso["diagnosis_id"]).reviewed_label is None  # só a lição

    p2 = _gera(client, agronomist_token, caso, caso="observacao",
               observation_id=caso["observation_id"])
    r = client.post(f"/v1/pareceres/{p2['id']}/revisao", headers=agronomist_token, json={
        "decisao": "discorda", "diagnostico_revisor": "Cercospora_Leaf_Spot",
        "comentario": "o centro é claro", "registrar_diagnostico": True})
    assert r.status_code == 201, r.text
    session.expire_all()
    assert session.get(Diagnosis, caso["diagnosis_id"]).reviewed_label == "Cercospora_Leaf_Spot"
    assert {x.origem for x in session.scalars(select(LicaoAgronomo))} == {"parecer"}
    # Nome que não é classe não vira diagnóstico.
    p3 = _gera(client, agronomist_token, caso, caso="observacao",
               observation_id=caso["observation_id"])
    ruim = client.post(f"/v1/pareceres/{p3['id']}/revisao", headers=agronomist_token, json={
        "decisao": "discorda", "diagnostico_revisor": "mancha estranha",
        "registrar_diagnostico": True})
    assert ruim.status_code == 422


def test_corte_exportado_leva_as_lesoes_e_o_porque(client, agronomist_token, platform_token,
                                                   caso, ia, demo, session: Session) -> None:  # noqa: F811
    autorizado = client.put(f"/v1/admin/tenants/{demo['tenant_id']}/data-consent",
                            json={"allowed": True, "document_ref": "Termo 1/2026"},
                            headers=platform_token)
    assert autorizado.status_code == 200, autorizado.text
    assert _revisa(client, agronomist_token, caso["diagnosis_id"], explicacao=POR_QUE,
                   lesoes=[LESAO]).status_code == 200
    amostra = session.scalars(select(DatasetSample)).one()
    corte = client.post(f"/v1/admin/datasets/{amostra.dataset_id}/versions",
                        json={"version": "v-ensino"}, headers=platform_token)
    assert corte.status_code == 201, corte.text
    url = f"/v1/admin/datasets/{amostra.dataset_id}/versions/{corte.json()['id']}/export"
    assert client.get(url, headers=agronomist_token).status_code in (401, 403)  # só a equipe
    r = client.get(url, headers=platform_token)
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        [linha] = [json.loads(x) for x in z.read("manifesto.jsonl").decode().splitlines() if x]
        assert linha["rotulo"] == "Rust" and linha["lesoes"] == [[0.2, 0.3, 0.1, 0.15]]
        assert linha["grupo"] == PLANTA and linha["face"] == "abaxial"
        assert z.read(linha["arquivo"])  # a imagem foi junto
        assert demo["tenant_id"] not in z.read("manifesto.jsonl").decode()


def test_vocabulario_sugere_por_classe(client: TestClient, agronomist_token) -> None:
    v = client.get("/v1/ensino/vocabulario", params={"rotulo": "Cercospora_Leaf_Spot"},
                   headers=agronomist_token).json()
    assert "olho-de-pomba" in v["sintomas"][0] and "abaxial" in v["faces"]


# -- consenso antes do treino ----------------------------------------------------------------


def _colega(session_factory, client, demo) -> dict:
    """Um segundo agrônomo no cliente da demonstração."""
    from tests.conftest import DEMO_PASSWORD
    from tests.test_isolamento_openapi import _login
    from valtexa.models import Membership, Role, User
    from valtexa.security.passwords import hash_password

    with session_factory() as s:
        u = User(email="colega@valtexa.dev", full_name="Eng. Agr. Colega",
                 password_hash=hash_password(DEMO_PASSWORD))
        s.add(u)
        s.flush()
        s.add(Membership(tenant_id=demo["tenant_id"], user_id=u.id, role=Role.AGRONOMIST))
        s.commit()
    return _login(client, "colega@valtexa.dev")


def test_corte_por_consenso_e_disputa(client, agronomist_token, platform_token, caso, ia,  # noqa: F811
                                      demo, session: Session, session_factory) -> None:
    client.put(f"/v1/admin/tenants/{demo['tenant_id']}/data-consent",
               json={"allowed": True, "document_ref": "Termo 1/2026"}, headers=platform_token)
    assert _revisa(client, agronomist_token, caso["diagnosis_id"],
                   explicacao=POR_QUE).status_code == 200
    amostra = session.scalars(select(DatasetSample)).one()
    colega = _colega(session_factory, client, demo)
    # Quem rotulou não vê a própria lição; o colega vê.
    assert client.get("/v1/ensino/segunda-opiniao", headers=agronomist_token).json() == []
    [pendente] = client.get("/v1/ensino/segunda-opiniao", headers=colega).json()
    assert pendente["amostra_id"] == amostra.id and pendente["porque"]

    versoes = f"/v1/admin/datasets/{amostra.dataset_id}/versions"
    sem = client.post(versoes, json={"version": "c0", "politica": "consenso"},
                      headers=platform_token)
    assert sem.status_code == 422 and "sem_segunda_opiniao" in sem.text
    op = client.post(f"/v1/ensino/segunda-opiniao/{amostra.id}", json={"rotulo": "Rust"},
                     headers=colega)
    assert op.status_code == 201 and op.json()["concorda"] is True
    assert client.post(f"/v1/ensino/segunda-opiniao/{amostra.id}", json={"rotulo": "Rust"},
                       headers=colega).status_code == 409  # uma opinião por pessoa
    c1 = client.post(versoes, json={"version": "c1", "politica": "consenso"},
                     headers=platform_token)
    assert c1.status_code == 201, c1.text
    assert c1.json()["sample_count"] == 1 and c1.json()["criterio"]["com_segunda_opiniao"] == 1

    # O agrônomo da equipe discorda: a amostra entra em disputa e sai de qualquer corte.
    r = client.post(f"/v1/admin/datasets/{amostra.dataset_id}/segunda-opiniao/{amostra.id}",
                    json={"rotulo": "Cercospora_Leaf_Spot"}, headers=platform_token)
    assert r.status_code == 201 and r.json()["concorda"] is False
    um = client.post(versoes, json={"version": "c2", "politica": "um"}, headers=platform_token)
    assert um.status_code == 422 and "em_disputa" in um.text
    # A confiabilidade de quem rotulou: 2 pares, 1 concordância -> (1+1)/(2+2).
    painel = client.get("/v1/ensino/painel", headers=agronomist_token).json()
    assert painel["confiabilidade"] == {"pares": 2, "concordancias": 1, "indice": 0.5}


# -- regras do agrônomo, medidas -------------------------------------------------------------


def _historico(client, admin_token, demo, session) -> None:
    """25 casos de ferrugem em julho e 25 sadios em março, todos confirmados."""
    from datetime import UTC, datetime

    from tests.helpers import provision, upload_observation
    from valtexa.models import DiagnosisStatus

    rover = provision(client, admin_token, "ROVER_SCOUT_V1", "REGRA-1", demo["farm_id"])
    for mes, rotulo in ((7, "Rust"), (3, "Healthy")):
        for i in range(25):
            r = upload_observation(rover, demo["field_id"], label=rotulo,
                                   captured_at=datetime(2026, mes, 1 + i, 10, tzinfo=UTC))
            assert r.status_code in (200, 201), r.text
    for d in session.scalars(select(Diagnosis)).all():
        d.status = DiagnosisStatus.HUMAN_CONFIRMED
        d.reviewed_label = d.label
    session.commit()


def test_regra_medida_no_historico_e_citada_no_parecer(client, admin_token, agronomist_token,
                                                       demo, caso, ia, session: Session) -> None:  # noqa: F811
    _historico(client, admin_token, demo, session)
    cultura = client.get(f"/v1/fields/{demo['field_id']}", headers=agronomist_token).json()["crop"]
    corpo = {"cultura": cultura, "doenca": "Rust", "texto": "ferrugem pega no inverno seco",
             "condicao": {"variavel": "mes", "meses": [6, 7, 8]}, "efeito": "aumenta"}
    r = client.post("/v1/ensino/regras", json=corpo, headers=agronomist_token)
    assert r.status_code == 201, r.text
    assert r.json()["veredito_texto"] == "ainda não medida"
    medida = client.post(f"/v1/ensino/regras/{r.json()['id']}/medir",
                         headers=agronomist_token).json()
    assert medida["medida"]["veredito"] == "sustentada", medida
    assert medida["medida"]["com_condicao"]["casos"] >= 25

    contraria = client.post("/v1/ensino/regras", headers=agronomist_token,
                            json={**corpo, "texto": "ferrugem some no inverno",
                                  "efeito": "diminui"}).json()
    assert client.post(f"/v1/ensino/regras/{contraria['id']}/medir", headers=agronomist_token
                       ).json()["medida"]["veredito"] == "contrariada"
    client.post(f"/v1/ensino/regras/{contraria['id']}/ativa", params={"ativa": False},
                headers=agronomist_token)

    p = _gera(client, agronomist_token, caso)
    [regra] = [a for a in p["afirmacoes"] if a["secao"] == "regras_agronomo"]
    assert "inverno seco" in regra["texto"] and "sustentada" in regra["texto"]
    assert p["recusas"] == []  # o compositor passou no próprio validador


def test_regra_que_nao_se_mede_e_recusada(client, agronomist_token) -> None:
    corpo = {"cultura": "coffee", "doenca": "Rust", "texto": "chove e dá ferrugem",
             "condicao": {"variavel": "lua", "janela_dias": 3, "operador": ">", "valor": 1},
             "efeito": "aumenta"}
    assert client.post("/v1/ensino/regras", json=corpo, headers=agronomist_token
                       ).status_code == 422


def test_condicao_de_clima_pela_janela() -> None:
    from datetime import date, timedelta

    from valtexa.services import ensino

    c = ensino.valida_condicao({"variavel": "chuva_mm", "janela_dias": 5, "operador": "<",
                                "valor": 10})
    dia = date(2026, 7, 20)
    seca = {(dia - timedelta(days=k)).isoformat(): {"chuva_mm": 1.0} for k in range(1, 6)}
    chuva = {k: {"chuva_mm": 8.0} for k in seca}
    assert ensino._condicao_vale(c, dia, seca) is True
    assert ensino._condicao_vale(c, dia, chuva) is False
    assert ensino._condicao_vale(c, dia, dict(list(seca.items())[:2])) is None  # janela falha
