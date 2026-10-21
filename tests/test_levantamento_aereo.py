"""Levantamento aéreo importado (7.2, etapa 1): o GeoJSON vira cobertura e regiões suspeitas e
vai para o gêmeo da IA (dublê aqui; o caminho real está em
``ia/tests/test_gemeo_levantamento.py``)."""

from __future__ import annotations

from sqlalchemy import select

from tests.test_enxame import _ret
from valtexa.models import AuditEntry
from valtexa.services import plant_map


def _feicao(tipo: str, anel: list[list[float]]) -> dict:
    return {"type": "Feature", "properties": {"tipo": tipo},
            "geometry": {"type": "Polygon", "coordinates": [anel]}}


def _pedido(*feicoes) -> dict:
    return {"doenca": "Rust", "pass_id": "voo-7", "voado_em": "2026-10-18T10:00:00Z",
            "geojson": {"type": "FeatureCollection", "features": list(feicoes)}}


def test_importa_e_audita(client, operator_token, demo, session, monkeypatch) -> None:
    enviados = []

    def gemeo(field_id, pedido):
        enviados.append((field_id, pedido))
        return {"cobertas": 120, "sinalizadas": 9, "substituiu": False,
                "canal": {"origem": "suposição de projeto"}}

    monkeypatch.setattr(plant_map, "levantamento_gemeo", gemeo)
    url = f"/v1/fields/{demo['field_id']}/gemeo/levantamento-aereo"
    corpo = _pedido(_feicao("cobertura", _ret(0, 0, meio=0.001)),
                    _feicao("anomalia", _ret(0, 0)), _feicao("anomalia", _ret(0.0002, 0)))
    r = client.post(url, json=corpo, headers=operator_token)
    assert r.status_code == 200, r.text
    assert r.json()["sinalizadas"] == 9 and len(r.json()["geojson_sha256"]) == 64
    field_id, pedido = enviados[0]
    assert field_id == demo["field_id"] and pedido["fonte"] == "drone"
    assert len(pedido["anomalias"]) == 2 and len(pedido["cobertura"]) == 5
    trilha = session.scalars(select(AuditEntry).where(
        AuditEntry.action == "gemeo.levantamento_aereo")).one()
    assert trilha.payload["anomalias"] == 2


def test_recusa_geojson_sem_cobertura_ou_tipo(client, operator_token, demo,
                                              monkeypatch) -> None:
    monkeypatch.setattr(plant_map, "levantamento_gemeo", lambda f, p: {})
    url = f"/v1/fields/{demo['field_id']}/gemeo/levantamento-aereo"
    for corpo in (_pedido(_feicao("anomalia", _ret(0, 0))),
                  _pedido(_feicao("cobertura", _ret(0, 0)), _feicao("cobertura", _ret(1, 0))),
                  _pedido({"type": "Feature", "properties": {},
                           "geometry": {"type": "Polygon", "coordinates": [_ret(0, 0)]}}),
                  _pedido({"type": "Feature", "properties": {"tipo": "cobertura"},
                           "geometry": {"type": "Point", "coordinates": [0, 0]}})):
        r = client.post(url, json=corpo, headers=operator_token)
        assert r.status_code == 422, r.text


def test_so_quem_cria_missao_importa(client, demo, session_factory, monkeypatch) -> None:
    from tests.test_principio_de_ouro import _usuario
    from valtexa.models import Role

    monkeypatch.setattr(plant_map, "levantamento_gemeo", lambda f, p: {})
    leitor = _usuario(session_factory, client, Role.VIEWER)
    r = client.post(f"/v1/fields/{demo['field_id']}/gemeo/levantamento-aereo",
                    json=_pedido(_feicao("cobertura", _ret(0, 0))), headers=leitor)
    assert r.status_code == 403
