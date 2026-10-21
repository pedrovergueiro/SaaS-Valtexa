"""Taxa variável na missão de pulverização: o mapa da IA, a aprovação presa ao hash e o Safety
Engine conferindo cada trecho (``services/aplicacao_localizada.py``)."""

from __future__ import annotations

import copy

import pytest

from tests.test_planejamento import frota  # noqa: F401
from tests.test_principio_de_ouro import (  # noqa: F401
    Role,
    _checks,
    _usuario,
    pulverizacao_em_rascunho,
)
from valtexa.models import Mission, MissionState, Product
from valtexa.services import aplicacao_localizada, plant_map


def _mapa(taxas=(0.0, 80.0, 100.0), ciclo=0.5, registro=None) -> dict:
    zonas = [{"row_id": "G1", "x_inicio_m": 5.0 * i, "x_fim_m": 5.0 * (i + 1),
              "taxa_l_ha": t, "bico": {"ciclo": ciclo if t else 0.0, "viavel": True,
                                       "estado": "ok" if t else "fechado"}}
             for i, t in enumerate(taxas)]
    mapa = {"estado": "proposta", "zonas": zonas, "data_aplicacao": "2026-10-20",
            "produto": {"nome": "X", "registro_mapa": registro},
            "equipamento": {"nome": "seções", "ciclo_min": 0.2, "ciclo_max": 1.0},
            "totais": {"litros": 3.0}, "bloqueios": []}
    mapa["sha256"] = aplicacao_localizada.sha256_do_mapa(mapa)
    return mapa


@pytest.fixture
def produto_com_bula(session, demo):
    p = session.get(Product, demo["product_id"])
    p.min_rate_l_ha, p.default_rate_l_ha, p.max_rate_l_ha = 50.0, 100.0, 150.0
    p.preharvest_interval_days = 30
    p.registration_number = p.registration_number or "12345"
    session.commit()
    return p


def _pede(client, mission_id, headers, monkeypatch, mapa) -> object:
    pedidos = []

    def falso(field_id, corpo):
        pedidos.append(corpo)
        return copy.deepcopy(mapa)

    monkeypatch.setattr(plant_map, "aplicacao_localizada_gemeo", falso)
    r = client.post(f"/v1/missions/{mission_id}/mapa-aplicacao", headers=headers,
                    json={"doenca": "Rust", "equipamento": {"nome": "seções"}})
    return r, pedidos


def test_mapa_aprovado_e_conferido(client, session, session_factory, demo, frota,  # noqa: F811
                                   pulverizacao_em_rascunho, produto_com_bula,  # noqa: F811
                                   monkeypatch) -> None:
    mid = pulverizacao_em_rascunho
    gestor = _usuario(session_factory, client, Role.OPERATOR)
    mapa = _mapa(registro=produto_com_bula.registration_number)
    r, pedidos = _pede(client, mid, gestor, monkeypatch, mapa)
    assert r.status_code == 200, r.text
    # O produto vai da bula cadastrada, não do pedido.
    assert pedidos[0]["produto"]["dose_max_l_ha"] == 150.0
    assert pedidos[0]["produto"]["registro_mapa"] == produto_com_bula.registration_number
    c = _checks(session, mid)
    assert c["map_integrity"] and not c["map_approved"]  # ainda sem aprovação
    agronomo = _usuario(session_factory, client, Role.AGRONOMIST)
    assert client.post(f"/v1/missions/{mid}/approve", json={"confirm": True},
                       headers=agronomo).status_code == 200
    c = _checks(session, mid)
    assert all(c[k] for k in ("map_integrity", "map_approved", "map_rates_label",
                              "map_rates_authorized", "map_pwm", "map_product")), c
    session.expire_all()
    assert session.get(Mission, mid).state is MissionState.DRAFT  # aprovar não libera

    # Alterar o mapa depois de aprovado (no banco, à mão): o hash acusa.
    m = session.get(Mission, mid)
    plano = copy.deepcopy(m.plan)
    plano["mapa_aplicacao"]["zonas"][2]["taxa_l_ha"] = 140.0
    m.plan = plano
    session.commit()
    assert _checks(session, mid)["map_integrity"] is False

    # Um mapa novo pela rota apaga a aprovação: o agrônomo aprova o que vê.
    r, _ = _pede(client, mid, gestor, monkeypatch, _mapa(
        taxas=(100.0, 100.0, 100.0), registro=produto_com_bula.registration_number))
    assert r.status_code == 200
    session.expire_all()
    m = session.get(Mission, mid)
    assert m.approved_by is None and "mapa_aplicacao_aprovado" not in m.plan
    assert _checks(session, mid)["map_approved"] is False


def test_trechos_fora_da_bula_ou_do_autorizado(client, session, session_factory, demo,
                                                frota, pulverizacao_em_rascunho,  # noqa: F811
                                                produto_com_bula, monkeypatch) -> None:
    mid = pulverizacao_em_rascunho
    gestor = _usuario(session_factory, client, Role.OPERATOR)
    reg = produto_com_bula.registration_number
    for taxas, ciclo, registro, falha in (
            ((0.0, 30.0), 0.5, reg, "map_rates_label"),          # abaixo da mínima de bula
            ((120.0,), 0.5, reg, "map_rates_authorized"),        # acima dos 100 autorizados
            ((80.0,), 0.1, reg, "map_pwm"),                      # ciclo abaixo do mínimo
            ((80.0,), 0.5, "outro-produto", "map_product")):
        assert _pede(client, mid, gestor, monkeypatch,
                     _mapa(taxas, ciclo, registro))[0].status_code == 200
        assert _checks(session, mid)[falha] is False, falha


def test_so_em_rascunho_de_pulverizacao(client, session, session_factory, demo, frota,  # noqa: F811
                                        pulverizacao_em_rascunho, produto_com_bula,  # noqa: F811
                                        monkeypatch) -> None:
    m = session.get(Mission, pulverizacao_em_rascunho)
    m.state = MissionState.AUTHORIZED
    session.commit()
    gestor = _usuario(session_factory, client, Role.OPERATOR)
    r, pedidos = _pede(client, m.id, gestor, monkeypatch, _mapa())
    assert r.status_code == 409 and not pedidos
    # Mapa que chega adulterado da IA é recusado.
    m.state = MissionState.DRAFT
    session.commit()
    torto = _mapa()
    torto["zonas"][0]["taxa_l_ha"] = 999.0
    assert _pede(client, m.id, gestor, monkeypatch, torto)[0].status_code == 502
