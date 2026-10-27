"""As rotas do gêmeo digital: proxies finos para ``app.gemeo`` de VALTEXA-B, com o escopo por
cliente, o RBAC e o plano daqui, e o status da recusa da inferência preservado."""

from __future__ import annotations

import httpx
from sqlalchemy import select

from valtexa.services import plant_map


def test_rotas_do_gemeo_pela_plataforma(client, admin_token, demo, session_factory,
                                        monkeypatch) -> None:
    from valtexa.models import Plan, Tenant
    from valtexa.services import plans

    chamadas = []

    def registra(nome, resposta):
        def f(*args):
            chamadas.append((nome, args))
            if isinstance(resposta, Exception):
                raise resposta
            return resposta
        return f

    monkeypatch.setattr(plant_map, "clima", registra("clima", {"dias": 40}))
    monkeypatch.setattr(plant_map, "enviar_clima", registra("enviar", {"acrescentados": 2}))
    monkeypatch.setattr(plant_map, "gemeo", registra("gemeo", {"plantas": 10}))
    monkeypatch.setattr(plant_map, "ajustar_gemeo", registra("ajuste", {"diagnostico": {}}))
    monkeypatch.setattr(plant_map, "previsao_gemeo", registra("previsao", {"focos_agora": 1}))
    monkeypatch.setattr(plant_map, "prescricao_gemeo",
                        registra("prescricao", {"data_aplicacao": "2026-03-10"}))
    url = f"/v1/fields/{demo['field_id']}"

    assert client.get(f"{url}/clima", headers=admin_token).json() == {"dias": 40}
    r = client.post(f"{url}/clima", json={"dias": []}, headers=admin_token)
    assert r.status_code == 200 and r.json() == {"acrescentados": 2}
    assert client.get(f"{url}/gemeo", headers=admin_token).json() == {"plantas": 10}
    assert client.post(f"{url}/gemeo/ajuste", params={"doenca": "Rust"},
                       headers=admin_token).status_code == 200
    r = client.get(f"{url}/gemeo/previsao", params={"doenca": "Rust", "horizonte_dias": 14},
                   headers=admin_token)
    assert r.status_code == 200 and r.json() == {"focos_agora": 1}
    assert chamadas[-1] == ("previsao", (demo["field_id"], {
        "doenca": "Rust", "horizonte_dias": 14, "membros": 16, "plantas": "em_risco"}))
    pedido = {"doenca": "Rust", "produto": {}, "economia": {"perda_por_planta": 30},
              "residual_dias": 21}
    r = client.post(f"{url}/gemeo/prescricao", json=pedido, headers=admin_token)
    assert r.status_code == 200 and r.json()["data_aplicacao"] == "2026-03-10"

    # Doença com caractere de caminho: recusada aqui, antes de chegar à inferência.
    assert client.post(f"{url}/gemeo/ajuste", params={"doenca": "../x"},
                       headers=admin_token).status_code == 422
    # A recusa da inferência mantém o status dela: 409 é "falta algo no talhão".
    monkeypatch.setattr(plant_map, "previsao_gemeo", registra(
        "previsao", plant_map.PlantMapRefusedError("Talhão sem série climática", 409)))
    r = client.get(f"{url}/gemeo/previsao", params={"doenca": "Rust"}, headers=admin_token)
    assert r.status_code == 409 and "climática" in r.json()["detail"]
    monkeypatch.setattr(plant_map, "gemeo", registra("gemeo", None))
    assert client.get(f"{url}/gemeo", headers=admin_token).status_code == 404
    monkeypatch.setattr(plant_map, "gemeo", registra(
        "gemeo", plant_map.PlantMapUnavailableError("fora do ar")))
    assert client.get(f"{url}/gemeo", headers=admin_token).status_code == 503
    # Talhão de outro cliente (ou inexistente): 404, sem chamar a inferência.
    antes = len(chamadas)
    assert client.get("/v1/fields/outro/gemeo", headers=admin_token).status_code == 404
    assert len(chamadas) == antes

    with session_factory() as s:  # plano sem prescrição: 402 na prescrição por risco
        plano = s.scalars(select(Plan).where(Plan.code == "essencial")).one()
        if "prescricao" in (plano.features or []):
            plano.features = [f for f in plano.features if f != "prescricao"]
        plans.assinar(s, s.get(Tenant, demo["tenant_id"]), plano, actor=None)
        s.commit()
    assert client.post(f"{url}/gemeo/prescricao", json=pedido,
                       headers=admin_token).status_code == 402


def test_request_preserva_status_e_timeout_longo(monkeypatch) -> None:
    from valtexa.config import settings

    monkeypatch.setattr(plant_map, "settings", settings.model_copy(
        update={"simulated_inference": False, "inference_enabled": True}))
    vistos = []

    def falso(method, url, **kwargs):
        vistos.append((method, url, kwargs["timeout"], kwargs.get("params")))
        if "previsao" in url:
            return httpx.Response(409, json={"detail": "Talhão sem série climática"},
                                  request=httpx.Request(method, url))
        return httpx.Response(200, json={"ok": True}, request=httpx.Request(method, url))

    monkeypatch.setattr(httpx, "request", falso)
    assert plant_map.ajustar_gemeo("T.1", "Rust") == {"ok": True}
    metodo, url, timeout, params = vistos[-1]
    assert metodo == "POST" and url.endswith("/fields/T%2E1/gemeo/ajuste")
    assert timeout >= plant_map.GEMEO_AJUSTE_TIMEOUT_SECONDS and params == {"doenca": "Rust"}
    try:
        plant_map.previsao_gemeo("T1", {"doenca": "Rust"})
    except plant_map.PlantMapRefusedError as exc:
        assert exc.status_code == 409
    else:
        raise AssertionError("409 da inferência deveria virar recusa")


def test_modo_do_gemeo_pelo_agronomo(client, agronomist_token, operator_token, demo, session,
                                     monkeypatch) -> None:
    from valtexa.models import AuditEntry

    chamadas = []

    def mudar(field_id, pedido):
        chamadas.append(pedido)
        if pedido["modo"] == "ativo" and pedido["doenca"] == "Rust":
            raise plant_map.PlantMapRefusedError("ainda não venceu as referências", 409)
        return {**pedido, "evidencia": None}

    monkeypatch.setattr(plant_map, "mudar_modo_gemeo", mudar)
    monkeypatch.setattr(plant_map, "avaliacao_gemeo",
                        lambda f, d: {"doenca": d, "pode_ativar": False, "motivos": ["poucas"]})
    url = f"/v1/fields/{demo['field_id']}/gemeo"

    av = client.get(f"{url}/avaliacao", params={"doenca": "Rust"}, headers=agronomist_token)
    assert av.status_code == 200 and av.json()["pode_ativar"] is False
    pedido = {"doenca": "Rust", "modo": "ativo", "motivo": "venceu na safra"}
    # A recusa da IA (sem avaliação favorável) chega com o status dela.
    assert client.post(f"{url}/modo", json=pedido, headers=agronomist_token).status_code == 409
    # Só o agrônomo muda o modo; quem decide vai junto, com o nome.
    assert client.post(f"{url}/modo", json={**pedido, "modo": "observacao"},
                       headers=operator_token).status_code == 403
    r = client.post(f"{url}/modo", json={**pedido, "modo": "observacao"},
                    headers=agronomist_token)
    assert r.status_code == 200 and chamadas[-1]["responsavel"]
    acoes = session.scalars(select(AuditEntry.action).where(
        AuditEntry.action == "gemeo.modo")).all()
    assert acoes == ["gemeo.modo"]
