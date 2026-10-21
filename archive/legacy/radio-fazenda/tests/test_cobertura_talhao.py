"""Mapa de cobertura do rádio: a base manda, o talhão guarda, a missão leva assinado."""

from __future__ import annotations

from sqlalchemy import select

from tests.helpers import provision
from valtexa.models import AuditEntry, Farm, Field, Mission, Tenant
from valtexa.models.enums import MissionKind, MissionState
from valtexa.services.mission_manager import mission_command_body

MAPA = {
    "versao": 1, "origem": [-22.4145, -45.4515], "celula_m": 10.0,
    "celulas": {"0,0": "bom", "0,1": "marginal", "1,1": "morto", "1,2": "morto"},
    "zonas_mortas": [{"id": 0, "celulas": [[1, 1], [1, 2]], "centro": [-22.414, -45.4514],
                      "area_m2": 200.0}],
    "repetidoras": [{"lat": -22.4141, "lon": -45.4512, "ganho_amostras": 40}],
    "raio_repetidora_m": 150.0, "amostras": 812, "fracao_morta_coberta": 0.9,
}


def test_base_manda_o_talhao_guarda_e_a_missao_leva(client, admin_token, platform_token,
                                                     demo, session) -> None:
    base = provision(client, admin_token, "FARM_BASE_V1", "BASE-COB-01", demo["farm_id"])
    robo = provision(client, admin_token, "ROVER_SCOUT_V1", "RV-COB-00", demo["farm_id"])
    url = f"/v1/device/base/cobertura/{demo['field_id']}"
    r = base.request("PUT", url, json_body=MAPA)
    assert r.status_code == 200, r.text
    assert r.json()["contagem"] == {"bom": 1, "marginal": 1, "morto": 2}
    assert r.json()["zonas_mortas"] == 1

    # a equipe vê o mapa (o console desenha a grade)
    lido = client.get(f"/v1/platform/fields/{demo['field_id']}/cobertura",
                      headers=platform_token).json()
    assert lido["mapa"]["celulas"] == MAPA["celulas"] and lido["cobertura_em"]
    assert lido["mapa"]["repetidoras"][0]["ganho_amostras"] == 40
    # e na lista de bases, cada talhão que a base atende diz se já tem levantamento
    (b,) = [x for x in client.get("/v1/platform/bases", headers=platform_token).json()
            if x["serial_number"] == "BASE-COB-01"]
    (t,) = [x for x in b["talhoes"] if x["id"] == demo["field_id"]]
    assert t["cobertura_em"] and t["zonas_mortas"] == 1 and t["contagem"]["morto"] == 2

    # toda missão nova do talhão leva o mapa — só o que o Rover usa
    missao = Mission(tenant_id=demo["tenant_id"], kind=MissionKind.SCOUT,
                     state=MissionState.AUTHORIZED, farm_id=demo["farm_id"],
                     field_id=demo["field_id"], device_id=robo.device_id)
    session.add(missao)
    session.flush()
    corpo = mission_command_body(session, missao)["cobertura"]
    assert set(corpo) == {"versao", "origem", "celula_m", "celulas", "zonas_mortas",
                          "gerado_em"}
    assert corpo["zonas_mortas"][0]["celulas"] == [[1, 1], [1, 2]]

    trilha = session.scalars(select(AuditEntry).where(
        AuditEntry.action == "field.cobertura")).all()
    assert len(trilha) == 1 and trilha[0].actor_id == base.device_id


def test_talhao_sem_levantamento_a_missao_vai_sem_mapa(client, admin_token, demo,
                                                       session) -> None:
    robo = provision(client, admin_token, "ROVER_SCOUT_V1", "RV-COB-02", demo["farm_id"])
    missao = Mission(tenant_id=demo["tenant_id"], kind=MissionKind.SCOUT,
                     state=MissionState.AUTHORIZED, farm_id=demo["farm_id"],
                     field_id=demo["field_id"], device_id=robo.device_id)
    session.add(missao)
    session.flush()
    assert mission_command_body(session, missao)["cobertura"] is None


def test_so_a_base_e_so_o_talhao_dela(client, admin_token, demo, session) -> None:
    rover = provision(client, admin_token, "ROVER_SCOUT_V1", "RV-COB-01", demo["farm_id"])
    url = f"/v1/device/base/cobertura/{demo['field_id']}"
    assert rover.request("PUT", url, json_body=MAPA).status_code == 403

    outro = Tenant(name="Outro", slug="outro-cobertura")
    session.add(outro)
    session.flush()
    fazenda = Farm(tenant_id=outro.id, name="F2", center_lat=-22.0, center_lon=-45.0)
    session.add(fazenda)
    session.flush()
    alheio = Field(tenant_id=outro.id, farm_id=fazenda.id, name="Alheio", crop="coffee")
    session.add(alheio)
    session.commit()

    base = provision(client, admin_token, "FARM_BASE_V1", "BASE-COB-02", demo["farm_id"])
    # talhão de outro cliente e talhão que não existe: a mesma resposta (sem pista)
    r1 = base.request("PUT", f"/v1/device/base/cobertura/{alheio.id}", json_body=MAPA)
    r2 = base.request("PUT", "/v1/device/base/cobertura/nao-existe", json_body=MAPA)
    assert r1.status_code == r2.status_code == 404 and r1.json() == r2.json()
    session.refresh(alheio)
    assert alheio.cobertura is None

    ruim = {**MAPA, "celulas": {"a,b": "bom"}}
    assert base.request("PUT", f"/v1/device/base/cobertura/{demo['field_id']}",
                        json_body=ruim).status_code == 422
    sem_origem = {k: v for k, v in MAPA.items() if k != "origem"}
    assert base.request("PUT", f"/v1/device/base/cobertura/{demo['field_id']}",
                        json_body=sem_origem).status_code == 422
