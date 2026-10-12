"""Observabilidade e alertas (Parte 7, seções 34 e 35).

O que se prova aqui, pela API e pelo worker:

1. o formato de exposição do Prometheus (contador, histograma, escape, quantil);
2. toda requisição ganha ``X-Request-Id``, é medida pelo **molde** da rota e entra no
   log estruturado com cliente e usuário; a janela por minuto vai para o banco;
3. ``/metrics`` é protegido (token do Prometheus ou equipe com a capacidade);
4. a saúde padronizada que o robô manda vira o retrato dele, sem lixo nem zero falso;
5. cada regra de alerta dispara, atualiza sem duplicar, é reconhecida e resolve
   sozinha, e o aviso sai pelas notificações da Parte 6 para quem deve;
6. o cliente vê só os robôs e os alertas dele; a regra própria dele vale só para ele.
"""

from __future__ import annotations

import io
import json
import logging
import math
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from tests.conftest import DEMO_PASSWORD
from tests.helpers import provision, send_telemetry
from valtexa.config import settings
from valtexa.models import (
    Alert,
    ApiRequestStat,
    Detection,
    Device,
    Membership,
    Notification,
    Observation,
    OutboxEvent,
    PlatformRole,
    Role,
    Tenant,
    User,
)
from valtexa.models.enums import DetectionSource
from valtexa.observability import contexto, logs
from valtexa.observability import http as obs_http
from valtexa.observability.metricas import Registro, quantil_dos_baldes
from valtexa.security.passwords import hash_password
from valtexa.services import alertas, events, observabilidade

IA_OK = {"status": "ok", "detail": None}


def _login(client: TestClient, email: str) -> dict[str, str]:
    r = client.post("/v1/auth/login", json={"email": email, "password": DEMO_PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}",
            "X-Tenant-Id": r.json()["tenant_id"]}


def _avisos(session: Session, email: str, kind: str) -> list[Notification]:
    session.expire_all()
    user = session.scalars(select(User).where(User.email == email)).one()
    return list(session.scalars(select(Notification).where(
        Notification.user_id == user.id, Notification.kind == kind)
        .order_by(Notification.created_at)))


def _robo(session: Session, device_id: str) -> Device:
    session.expire_all()
    return session.get(Device, device_id)


@pytest.fixture(autouse=True)
def _sem_cache_de_metricas():
    """A fotografia do banco no /metrics é guardada 15 s; cada teste parte do zero."""
    observabilidade._FAMILIAS_CACHE.clear()
    yield
    observabilidade._FAMILIAS_CACHE.clear()


@pytest.fixture
def robo(client: TestClient, admin_token: dict, demo: dict):
    sessao = provision(client, admin_token, "ROVER_SCOUT_V1", "OBS-ROVER", demo["farm_id"])
    assert send_telemetry(sessao, battery_percent=80.0).status_code == 200
    return sessao


# ---------------------------------------------------------------------------
# 1. Formato do Prometheus
# ---------------------------------------------------------------------------


def test_exposicao_do_prometheus() -> None:
    reg = Registro()
    c = reg.contador("app_requests_total", "Pedidos.", ("route",))
    h = reg.histograma("app_latency_seconds", "Latência.", ("route",), limites=(0.1, 1.0))
    c.inc(route='/a"b\\c')
    c.inc(2, route="/x")
    for v in (0.05, 0.5, 5.0):
        h.observe(v, route="/x")
    texto = reg.render()
    assert "# TYPE app_requests_total counter" in texto
    assert 'app_requests_total{route="/a\\"b\\\\c"} 1' in texto
    assert 'app_requests_total{route="/x"} 2' in texto
    assert 'app_latency_seconds_bucket{route="/x",le="0.1"} 1' in texto
    assert 'app_latency_seconds_bucket{route="/x",le="1"} 2' in texto
    assert 'app_latency_seconds_bucket{route="/x",le="+Inf"} 3' in texto
    assert 'app_latency_seconds_count{route="/x"} 3' in texto
    assert 'app_latency_seconds_sum{route="/x"} 5.55' in texto
    with pytest.raises(ValueError):
        c.inc(-1, route="/x")
    with pytest.raises(ValueError):
        reg.contador("app_requests_total", "de novo")
    with pytest.raises(ValueError):
        c.inc(rota="/x")


def test_quantil_dos_baldes_interpola_como_o_prometheus() -> None:
    limites = (10, 100, 1000)
    assert quantil_dos_baldes(limites, [0, 0, 0, 0], 0.5) is None
    assert quantil_dos_baldes(limites, [10, 0, 0, 0], 0.5) == pytest.approx(5.0)
    assert quantil_dos_baldes(limites, [50, 50, 0, 0], 0.95) == pytest.approx(91.0)
    assert quantil_dos_baldes(limites, [0, 0, 0, 3], 0.5) == 1000  # acima do último limite


# ---------------------------------------------------------------------------
# 2. Middleware, request_id, logs e a janela por minuto
# ---------------------------------------------------------------------------


def test_request_id_rota_por_molde_e_janela(client: TestClient, admin_token: dict,
                                            demo: dict, session: Session) -> None:
    obs_http.JANELA.retirar()
    antes = obs_http.REQUISICOES.valor(method="GET", route="/v1/fields/{field_id}", status="200")
    r = client.get(f"/v1/fields/{demo['field_id']}", headers=admin_token)
    assert r.status_code == 200
    assert len(r.headers["X-Request-Id"]) == 32
    # o do balanceador é reaproveitado se for sensato; lixo é trocado
    r = client.get(f"/v1/fields/{demo['field_id']}",
                   headers={**admin_token, "X-Request-Id": "lb-abc12345"})
    assert r.headers["X-Request-Id"] == "lb-abc12345"
    r = client.get("/v1/rota-que-nao-existe", headers={"X-Request-Id": "x\nquebra"})
    assert r.status_code == 404 and r.headers["X-Request-Id"] != "x\nquebra"
    depois = obs_http.REQUISICOES.valor(method="GET", route="/v1/fields/{field_id}", status="200")
    assert depois - antes == 2  # pelo molde, não pelo caminho com o id
    # o caminho inexistente vira um molde fixo (sem rota, ou o /{path} do console):
    # nunca o texto que quem chamou inventou — senão a cardinalidade explode
    assert "rota-que-nao-existe" not in obs_http.REQUISICOES.render()
    assert sum(obs_http.REQUISICOES.valor(method="GET", route=m, status="404")
               for m in (obs_http.SEM_ROTA, "/{path}")) >= 1

    assert observabilidade.descarregar(session, instancia="teste") >= 2
    linhas = session.scalars(select(ApiRequestStat).where(
        ApiRequestStat.route == "/v1/fields/{field_id}")).all()
    assert sum(linha.requests for linha in linhas) == 2
    assert all(linha.instance == "teste" and len(linha.buckets) == 12 for linha in linhas)
    assert observabilidade.descarregar(session) == 0  # nada novo: nada a gravar
    resumo = observabilidade.api(session, minutos=5)
    rota = next(x for x in resumo["routes"] if x["route"] == "/v1/fields/{field_id}")
    assert rota["requests"] == 2 and rota["server_errors"] == 0
    assert rota["latency_ms_p95"] is not None and rota["latency_ms_p95"] > 0


def test_banco_fora_devolve_a_janela(session: Session) -> None:
    janela = obs_http.JanelaApi()
    janela.registrar("GET", "/x", 200, 12.0)

    class Quebrada:
        def add(self, _):
            raise RuntimeError("banco fora")

        def rollback(self):
            pass

    with pytest.raises(RuntimeError):
        observabilidade.descarregar(Quebrada(), janela)  # type: ignore[arg-type]
    assert len(janela) == 1  # nada perdido
    assert observabilidade.descarregar(session, janela) == 1


def test_erro_500_e_contado_e_traz_request_id() -> None:
    app = FastAPI()
    app.add_middleware(obs_http.ObservabilidadeMiddleware)

    @app.get("/quebra/{item}")
    def quebra(item: str) -> None:
        raise RuntimeError("defeito")

    antes = obs_http.ERROS.valor(method="GET", route="/quebra/{item}")
    with TestClient(app, raise_server_exceptions=False) as c:
        assert c.get("/quebra/1").status_code == 500
    assert obs_http.ERROS.valor(method="GET", route="/quebra/{item}") - antes == 1


def test_resposta_500_da_plataforma_leva_o_request_id() -> None:
    from valtexa.main import _handle_unexpected

    class Pedido:
        method, scope = "GET", {obs_http.REQUEST_ID_KEY: "abc12345xyz"}

        class url:  # noqa: N801
            path = "/v1/x"

    import asyncio

    resposta = asyncio.run(_handle_unexpected(Pedido(), RuntimeError("x")))
    corpo = json.loads(resposta.body)
    assert corpo["request_id"] == "abc12345xyz" and corpo["error_id"]
    assert resposta.headers["X-Request-Id"] == "abc12345xyz"


def test_log_estruturado_tem_cliente_usuario_e_request_id(
    client: TestClient, admin_token: dict, demo: dict
) -> None:
    saida = io.StringIO()
    handler = logging.StreamHandler(saida)
    handler.addFilter(logs.FiltroDeContexto())
    handler.setFormatter(logs.FormatoJson())
    log_http = logging.getLogger("valtexa.http")
    log_http.addHandler(handler)
    nivel = log_http.level
    log_http.setLevel(logging.INFO)
    try:
        r = client.get(f"/v1/fields/{demo['field_id']}", headers=admin_token)
    finally:
        log_http.removeHandler(handler)
        log_http.setLevel(nivel)
    linhas = [json.loads(x) for x in saida.getvalue().splitlines() if x.strip()]
    linha = next(x for x in linhas if x.get("route") == "/v1/fields/{field_id}")
    assert linha["request_id"] == r.headers["X-Request-Id"]
    assert linha["tenant_id"] == demo["tenant_id"]
    assert linha["user_id"] and linha["status"] == 200 and linha["level"] == "INFO"
    assert linha["duration_ms"] >= 0


def test_contexto_recusa_campo_desconhecido_e_fora_de_requisicao_nao_faz_nada() -> None:
    contexto.anotar(tenant_id="x")  # fora de requisição: ignora
    assert contexto.atual() == {}
    token = contexto.abrir("req-123456789")
    try:
        with pytest.raises(ValueError):
            contexto.anotar(senha="x")
    finally:
        contexto.fechar(token)


# ---------------------------------------------------------------------------
# 3. /metrics protegido
# ---------------------------------------------------------------------------


def test_metrics_protegido(client: TestClient, admin_token: dict, equipe, robo,
                           monkeypatch: pytest.MonkeyPatch) -> None:
    send_telemetry(robo, health={"cpu_percent": 42.0, "disk_percent": 61.5})
    assert client.get("/metrics").status_code == 401
    assert client.get("/metrics", headers=admin_token).status_code == 403  # cliente
    assert client.get("/metrics", headers=equipe(PlatformRole.COMERCIAL)).status_code == 403
    r = client.get("/metrics", headers=equipe(PlatformRole.OPERACOES))
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/plain")
    texto = r.text
    for nome in ("valtexa_http_requests_total", "valtexa_http_request_duration_seconds_bucket",
                 "valtexa_outbox_pending", "valtexa_active_users", "valtexa_rover_up",
                 "valtexa_alerts_open"):
        assert nome in texto, nome
    assert 'valtexa_rover_disk_percent{tenant="' in texto and 'device="OBS-ROVER"} 61.5' in texto
    assert 'device="OBS-ROVER"} 42' in texto
    # o que o robô não mandou não aparece como zero
    assert "valtexa_rover_accelerator_percent{" not in texto

    from valtexa.api.routers import observabilidade as rota

    monkeypatch.setattr(rota, "settings", settings.model_copy(
        update={"metrics_token": "segredo-do-prometheus-de-teste"}))
    assert client.get("/metrics", headers={
        "Authorization": "Bearer segredo-do-prometheus-de-teste"}).status_code == 200
    assert client.get("/metrics", headers={"Authorization": "Bearer errado"}).status_code == 401


# ---------------------------------------------------------------------------
# 4. Saúde padronizada
# ---------------------------------------------------------------------------


def test_saude_padronizada_do_robo(client: TestClient, robo, session: Session) -> None:
    r = send_telemetry(robo, temperature_c=41.0, health={
        "cpu_percent": 55.5, "memory_percent": 300, "disk_percent": float("nan"),
        "accelerator": {"name": "NPU X", "percent": None, "providers": ["CPUExecutionProvider"]},
        "cameras": [{"id": "cam-0", "ok": True}, {"id": "cam-1", "ok": False,
                                                    "detail": "sem quadro"}, {"sem": "id"}],
        "sensors": {"gps": "ok", "imu": "explodiu"},
        "sync": {"pending": 12, "oldest_pending_s": 90, "blocked": False},
        "network": {"online": True}, "simulated": ["sistema"], "lixo": {"a": 1},
    })
    # NaN é recusado na entrada (JSON do protocolo), então mandamos sem ele:
    if r.status_code == 422:
        r = send_telemetry(robo, temperature_c=41.0, health={
            "cpu_percent": 55.5, "memory_percent": 300,
            "accelerator": {"name": "NPU X", "percent": None,
                            "providers": ["CPUExecutionProvider"]},
            "cameras": [{"id": "cam-0", "ok": True},
                        {"id": "cam-1", "ok": False, "detail": "sem quadro"}, {"sem": "id"}],
            "sensors": {"gps": "ok", "imu": "explodiu"},
            "sync": {"pending": 12, "oldest_pending_s": 90, "blocked": False},
            "network": {"online": True}, "simulated": ["sistema"], "lixo": {"a": 1},
        })
    assert r.status_code == 200, r.text
    saude = _robo(session, robo.device_id).health
    assert saude["cpu_percent"] == 55.5
    assert saude["memory_percent"] is None  # 300 % não existe: descartado, não cortado
    assert saude["accelerator"]["name"] == "NPU X" and saude["accelerator"]["percent"] is None
    assert [c["id"] for c in saude["cameras"]] == ["cam-0", "cam-1"]
    assert saude["sensors"] == {"gps": "ok", "imu": None, "ambiente": None}
    assert saude["sync"]["pending"] == 12 and "lixo" not in saude
    assert saude["simulated"] == ["sistema"]
    # robô sem health (firmware antigo) continua: o retrato fica como estava
    assert send_telemetry(robo, battery_percent=70.0).status_code == 200
    assert _robo(session, robo.device_id).health["cpu_percent"] == 55.5


def test_frota_do_cliente_so_tem_os_robos_dele(
    client: TestClient, admin_token: dict, robo, session: Session, equipe
) -> None:
    send_telemetry(robo, health={"cpu_percent": 10.0, "cameras": [{"id": "c", "ok": True}]})
    outro = Tenant(name="Fazenda Outra", slug="fazenda-outra-obs")
    session.add(outro)
    session.flush()
    session.add(Device(tenant_id=outro.id, serial_number="OUTRO-1", name="Outro",
                       kind=_robo(session, robo.device_id).kind,
                       device_model_id=_robo(session, robo.device_id).device_model_id))
    session.commit()
    meus = client.get("/v1/observability/fleet", headers=admin_token).json()
    assert {r["serial_number"] for r in meus} == {"OBS-ROVER"}
    assert meus[0]["cpu_percent"] == 10.0 and meus[0]["cameras_ok"] == 1
    todos = client.get("/v1/platform/observability/fleet",
                       headers=equipe(PlatformRole.SUPORTE)).json()
    assert {"OBS-ROVER", "OUTRO-1"} <= {r["serial_number"] for r in todos}
    assert client.get("/v1/platform/observability/fleet",
                      headers=equipe(PlatformRole.COMERCIAL)).status_code == 403


# ---------------------------------------------------------------------------
# 5. Alertas
# ---------------------------------------------------------------------------


def test_disco_cheio_dispara_avisa_reconhece_e_resolve(
    client: TestClient, admin_token: dict, operator_token: dict, robo, session: Session, equipe
) -> None:
    ops = equipe(PlatformRole.OPERACOES)  # a equipe existe antes do alerta
    send_telemetry(robo, health={"disk_percent": 95.0})
    rel = alertas.avaliar(session, ia=IA_OK)
    assert rel.disparados == 1 and rel.erros == 0
    assert alertas.avaliar(session, ia=IA_OK).disparados == 0  # não duplica
    alerta = session.scalars(select(Alert).where(Alert.kind == "disco_rover")).one()
    assert alerta.state == "disparado" and alerta.value == 95.0 and alerta.threshold == 90.0
    assert "OBS-ROVER" in alerta.subject_label

    # sai pelas notificações da Parte 6: gestor do cliente e equipe de operações
    events.drain(session)
    assert _avisos(session, "admin@valtexa.dev", "alerta_robo")
    assert not _avisos(session, "operador@valtexa.dev", "alerta_robo")  # operador: padrão não
    lista = client.get("/v1/platform/notifications", headers=ops).json()
    assert [a["kind"] for a in lista] == ["plataforma_alerta"]
    events.drain(session)  # reentregar não duplica
    assert len(_avisos(session, "admin@valtexa.dev", "alerta_robo")) == 1

    # o cliente vê e reconhece (operador não tem device:manage)
    meus = client.get("/v1/observability/alerts", headers=admin_token).json()
    assert [a["kind"] for a in meus] == ["disco_rover"]
    assert client.post(f"/v1/observability/alerts/{alerta.id}/ack", headers=operator_token,
                       json={}).status_code == 403
    r = client.post(f"/v1/observability/alerts/{alerta.id}/ack", headers=admin_token,
                    json={"note": "Técnico vai esvaziar hoje."})
    assert r.status_code == 200 and r.json()["state"] == "reconhecido"
    assert r.json()["acknowledged_label"] == "Administrador da Demo"

    # disco volta ao normal: resolve sozinho; nova violação abre outro alerta
    send_telemetry(robo, health={"disk_percent": 40.0})
    assert alertas.avaliar(session, ia=IA_OK).resolvidos == 1
    session.expire_all()
    alerta = session.get(Alert, alerta.id)
    assert alerta.state == "resolvido" and alerta.open_key is None and alerta.resolved_at
    assert client.post(f"/v1/observability/alerts/{alerta.id}/ack", headers=admin_token,
                       json={}).status_code == 409
    send_telemetry(robo, health={"disk_percent": 93.0})
    assert alertas.avaliar(session, ia=IA_OK).disparados == 1
    assert len(session.scalars(select(Alert).where(Alert.kind == "disco_rover")).all()) == 2


def test_um_alerta_aberto_por_assunto_no_banco(session: Session) -> None:
    agora = datetime.now(UTC)
    for _ in range(2):
        session.add(Alert(kind="api_erros", subject_type="componente", subject_id="api",
                          subject_label="API", open_key="api_erros:componente:api",
                          state="disparado", severity="critico", message="x",
                          fired_at=agora, last_seen_at=agora))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_robo_offline_alerta_a_equipe_e_nao_repete_o_aviso_do_cliente(
    client: TestClient, robo, session: Session, equipe
) -> None:
    device = _robo(session, robo.device_id)
    device.last_seen_at = datetime.now(UTC) - timedelta(minutes=45)
    session.commit()
    assert alertas.avaliar(session, ia=IA_OK).disparados == 1
    alerta = session.scalars(select(Alert).where(Alert.kind == "rover_offline")).one()
    assert alerta.severity == "critico" and 44 <= alerta.value <= 46
    events.drain(session)
    assert not _avisos(session, "admin@valtexa.dev", "alerta_robo")  # já tem rover_offline
    assert _avisos(session, "equipe@valtexa.dev", "plataforma_alerta")
    # voltou a falar: resolve, e o crítico avisa a equipe que passou
    send_telemetry(robo, battery_percent=50.0)
    assert alertas.avaliar(session, ia=IA_OK).resolvidos == 1
    events.drain(session)
    titulos = [a.title for a in _avisos(session, "equipe@valtexa.dev", "plataforma_alerta")]
    assert any(t.startswith("Resolvido") for t in titulos)


def test_regra_propria_do_cliente_vale_so_para_ele(
    client: TestClient, admin_token: dict, operator_token: dict, robo, session: Session,
    equipe,
) -> None:
    # o gestor sobe o limite de disco dos robôs dele para 98 %
    assert client.put("/v1/observability/alert-rules/disco_rover", headers=operator_token,
                      json={"threshold": 98}).status_code == 403
    r = client.put("/v1/observability/alert-rules/disco_rover", headers=admin_token,
                   json={"threshold": 98})
    assert r.status_code == 200 and r.json()["source"] == "cliente"
    assert r.json()["default_threshold"] == 90.0
    assert client.put("/v1/observability/alert-rules/api_erros", headers=admin_token,
                      json={"threshold": 1}).status_code == 403  # regra da plataforma
    assert client.put("/v1/observability/alert-rules/disco_rover", headers=admin_token,
                      json={"threshold": 140}).status_code == 422
    regras = {x["kind"]: x for x in client.get("/v1/observability/alert-rules",
                                                 headers=admin_token).json()}
    assert "api_erros" not in regras and regras["disco_rover"]["threshold"] == 98

    # robô de outro cliente com o mesmo disco: a regra padrão (90 %) vale para ele
    outro = Tenant(name="Fazenda Vizinha", slug="fazenda-vizinha-obs")
    session.add(outro)
    session.flush()
    modelo = _robo(session, robo.device_id)
    vizinho = Device(tenant_id=outro.id, serial_number="VIZ-1", name="Vizinho",
                     kind=modelo.kind, device_model_id=modelo.device_model_id,
                     status=modelo.status, storage_total_bytes=100, storage_free_bytes=5)
    session.add(vizinho)
    session.commit()
    send_telemetry(robo, health={"disk_percent": 95.0})
    alertas.avaliar(session, ia=IA_OK)
    disparados = session.scalars(select(Alert).where(Alert.kind == "disco_rover")).all()
    assert [a.subject_id for a in disparados] == [vizinho.id]
    # o cliente não vê o alerta do vizinho
    assert client.get("/v1/observability/alerts", headers=admin_token).json() == []
    # voltar à padrão: o robô dele passa a alertar
    assert client.delete("/v1/observability/alert-rules/disco_rover",
                         headers=admin_token).status_code == 204
    alertas.avaliar(session, ia=IA_OK)
    assert len(client.get("/v1/observability/alerts", headers=admin_token).json()) == 1

    # a equipe ajusta a padrão; comercial não pode; desligar resolve o que está aberto
    ops = equipe(PlatformRole.OPERACOES)
    assert client.put("/v1/platform/observability/alert-rules/disco_rover",
                      headers=equipe(PlatformRole.COMERCIAL), json={"enabled": False}
                      ).status_code == 403
    r = client.put("/v1/platform/observability/alert-rules/disco_rover", headers=ops,
                   json={"enabled": False})
    assert r.status_code == 200 and r.json()["enabled"] is False
    assert alertas.avaliar(session, ia=IA_OK).resolvidos == 2
    acoes = {a["action"] for a in client.get(
        "/v1/platform/audit", headers=equipe(PlatformRole.SUPERADMIN),
        params={"action": "alert_rule."}).json()}
    assert acoes == {"alert_rule.updated", "alert_rule.reset"}


def test_temperatura_camera_e_sincronizacao_parada(robo, session: Session) -> None:
    send_telemetry(robo, health={
        "temperature_c": 81.0,
        "cameras": [{"id": "cam-0", "ok": False, "detail": "timeout"}],
        "sync": {"pending": 40, "oldest_pending_s": 3 * 3600, "blocked": False},
    })
    alertas.avaliar(session, ia=IA_OK)
    tipos = {a.kind: a for a in session.scalars(select(Alert))}
    assert {"temperatura_rover", "camera_rover", "sync_parada"} <= set(tipos)
    assert tipos["temperatura_rover"].value == 81.0
    assert "cam-0 (timeout)" in tipos["camera_rover"].message
    assert tipos["sync_parada"].value == 180.0
    # sem rede a fila crescendo é offline-first, não "parada": resolve
    device = _robo(session, robo.device_id)
    device.last_seen_at = datetime.now(UTC) - timedelta(hours=2)
    device.connectivity = type(device.connectivity)("offline")
    session.commit()
    alertas.avaliar(session, ia=IA_OK)
    session.expire_all()
    assert session.get(Alert, tipos["sync_parada"].id).state == "resolvido"


def test_modelo_fora_do_registry(robo, session: Session) -> None:
    device = _robo(session, robo.device_id)
    device.ai_model_key, device.ai_model_version = "modelo-pirata", "0.0.1"
    session.commit()
    alertas.avaliar(session, ia=IA_OK)
    alerta = session.scalars(select(Alert).where(Alert.kind == "modelo_divergente")).one()
    assert "modelo-pirata@0.0.1" in alerta.message and "fora do registry" in alerta.message


def _estatistica(session: Session, *, ok: int, erros: int, minutos_atras: int = 1) -> None:
    minuto = (datetime.now(UTC) - timedelta(minutes=minutos_atras)).replace(second=0,
                                                                            microsecond=0)
    for classe, n, e in (("2xx", ok, 0), ("5xx", erros, erros)):
        if n:
            session.add(ApiRequestStat(minute=minuto, instance="t", method="POST",
                                       route="/v1/device/sync", status_class=classe,
                                       requests=n, errors=e, duration_ms_sum=10.0 * n,
                                       duration_ms_max=30.0, buckets=[0] * 3 + [n] + [0] * 8))
    session.commit()


def test_taxa_de_erro_da_api(session: Session, client: TestClient, equipe) -> None:
    obs_http.JANELA.retirar()
    _estatistica(session, ok=5, erros=4)  # 44 %, mas só 9 requisições: não diz nada
    assert alertas.avaliar(session, ia=IA_OK).disparados == 0
    _estatistica(session, ok=80, erros=10)
    alertas.avaliar(session, ia=IA_OK)
    alerta = session.scalars(select(Alert).where(Alert.kind == "api_erros")).one()
    # 14 erros em 99 requisições (as 9 de antes também contam na janela)
    assert alerta.tenant_id is None and alerta.value == pytest.approx(14.14, abs=0.01)
    assert "POST /v1/device/sync" in alerta.message
    # o cliente não vê alerta da plataforma
    assert client.get("/v1/observability/alerts",
                      headers=_login(client, "admin@valtexa.dev")).json() == []
    painel = client.get("/v1/platform/observability",
                        headers=equipe(PlatformRole.SUPORTE)).json()
    assert painel["alerts_open"] == 1 and painel["alerts_critical"] == 1
    assert {c["component"] for c in painel["components"]} == {
        "banco", "api", "worker", "ia", "frota", "alertas"}
    api = next(c for c in painel["components"] if c["component"] == "api")
    assert api["status"] == "falha"


def test_ia_fora_e_taxa_de_erro_da_inferencia(session: Session, demo: dict) -> None:
    alertas.avaliar(session, ia={"status": "fora", "detail": "ConnectError"})
    alerta = session.scalars(select(Alert).where(Alert.kind == "ia_fora")).one()
    assert "ConnectError" in alerta.message
    alertas.avaliar(session, ia={"status": "desligado", "detail": None})
    session.expire_all()
    assert session.get(Alert, alerta.id).state == "resolvido"

    obs = Observation(tenant_id=demo["tenant_id"], farm_id=demo["farm_id"],
                      field_id=demo["field_id"], captured_at=datetime.now(UTC),
                      lat=-22.9, lon=-47.06)
    session.add(obs)
    session.flush()
    for i in range(12):
        session.add(Detection(tenant_id=demo["tenant_id"], observation_id=obs.id,
                              source=DetectionSource.CLOUD_PRIMARY, analyzer="ia",
                              model_key="leaf", model_version="1.0",
                              error="timeout" if i < 4 else None, label="Rust"))
    session.commit()
    alertas.avaliar(session, ia=IA_OK)
    novo = session.scalars(select(Alert).where(Alert.kind == "ia_fora",
                                               Alert.state == "disparado")).one()
    assert novo.value == pytest.approx(33.33, abs=0.01) and "4 de 12" in novo.message


def test_drift_da_distribuicao_de_classes(session: Session, demo: dict, client: TestClient,
                                          equipe) -> None:
    agora = datetime.now(UTC)
    obs = Observation(tenant_id=demo["tenant_id"], farm_id=demo["farm_id"],
                      field_id=demo["field_id"], captured_at=agora, lat=-22.9, lon=-47.06)
    session.add(obs)
    session.flush()

    def deteccoes(rotulos: dict[str, int], quando: datetime) -> None:
        for rotulo, n in rotulos.items():
            for _ in range(n):
                d = Detection(tenant_id=demo["tenant_id"], observation_id=obs.id,
                              source=DetectionSource.CLOUD_PRIMARY, analyzer="ia",
                              model_key="leaf", model_version="1.0", label=rotulo)
                d.created_at = quando
                session.add(d)

    deteccoes({"Healthy": 180, "Rust": 20}, agora - timedelta(days=3))  # base: 10 % Rust
    deteccoes({"Healthy": 10, "Rust": 5}, agora - timedelta(hours=2))  # recente: pouca amostra
    session.commit()
    d = next(x for x in observabilidade.drift(session) if x["model_key"] == "leaf")
    assert d["distance"] is None and "recentes" in d["reason"]
    assert alertas.avaliar(session, ia=IA_OK).disparados == 0

    deteccoes({"Healthy": 15, "Rust": 25}, agora - timedelta(hours=1))  # recente: 55 % Rust
    session.commit()
    d = next(x for x in observabilidade.drift(session) if x["model_key"] == "leaf")
    assert d["distance"] == pytest.approx(0.4455, abs=0.001)  # 10 % → 54,5 % de Rust
    alertas.avaliar(session, ia=IA_OK)
    alerta = session.scalars(select(Alert).where(Alert.kind == "drift_classes")).one()
    assert alerta.subject_id == "nuvem:leaf" and "45%" in alerta.message
    ia = client.get("/v1/platform/observability/ai",
                    headers=equipe(PlatformRole.IA_DADOS)).json()
    nuvem = next(m for m in ia["cloud"] if m["model_key"] == "leaf")
    assert nuvem["inferences"] == 55 and nuvem["classes"] == {"Rust": 30, "Healthy": 25}
    assert "VALTEXA-B" in ia["drift_note"]


def test_distancia_de_variacao() -> None:
    assert observabilidade.distancia_de_variacao({"a": 5}, {"a": 9}) == 0
    assert observabilidade.distancia_de_variacao({"a": 1}, {"b": 1}) == 1
    assert observabilidade.distancia_de_variacao({}, {"a": 1}) is None


def test_fila_de_eventos_parada(session: Session) -> None:
    evento = events.publish(session, "teste.parado")
    evento.created_at = datetime.now(UTC) - timedelta(minutes=25)
    session.commit()
    alertas.avaliar(session, ia=IA_OK)
    alerta = session.scalars(select(Alert).where(Alert.kind == "eventos_parados")).one()
    assert alerta.severity == "critico" and alerta.value >= 25
    f = observabilidade.filas(session)
    assert f["outbox_pending"] >= 1 and f["outbox_oldest_pending_s"] >= 25 * 60
    session.delete(session.get(OutboxEvent, evento.id))
    session.commit()


def test_regra_com_defeito_nao_derruba_as_outras(session: Session, robo,
                                                monkeypatch: pytest.MonkeyPatch) -> None:
    def quebra(*_a, **_k):
        raise RuntimeError("defeito")

    monkeypatch.setitem(alertas.REGRAS, "camera_rover", alertas.RegraDef(
        "camera_rover", alertas.ROBO, "x", "x", None, None, None, "aviso", quebra))
    send_telemetry(robo, health={"disk_percent": 99.0})
    rel = alertas.avaliar(session, ia=IA_OK)
    assert rel.erros == 1 and rel.disparados >= 1


def test_estado_do_servico_de_ia(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(observabilidade, "settings", settings.model_copy(
        update={"simulated_inference": False, "inference_enabled": True}))

    def cliente(status: int | None) -> httpx.Client:
        def responder(request: httpx.Request) -> httpx.Response:
            if status is None:
                raise httpx.ConnectError("recusado", request=request)
            assert request.url.path == "/health"
            return httpx.Response(status)
        return httpx.Client(transport=httpx.MockTransport(responder))

    assert observabilidade.estado_ia(forcar=True, cliente=cliente(200))["status"] == "ok"
    assert observabilidade.estado_ia(forcar=True, cliente=cliente(503))["detail"] == "HTTP 503"
    fora = observabilidade.estado_ia(forcar=True, cliente=cliente(None))
    assert fora["status"] == "fora" and "ConnectError" in fora["detail"]
    monkeypatch.setattr(observabilidade, "settings", settings.model_copy(
        update={"inference_enabled": False}))
    assert observabilidade.estado_ia()["status"] == "desligado"


def test_painel_da_api_e_usuarios_ativos(client: TestClient, admin_token: dict, equipe,
                                         session: Session) -> None:
    client.get("/v1/farms", headers=admin_token)
    ops = equipe(PlatformRole.OPERACOES)
    api = client.get("/v1/platform/observability/api", headers=ops,
                     params={"minutes": 10}).json()
    assert api["requests"] >= 1 and any(r["route"] == "/v1/farms" for r in api["routes"])
    painel = client.get("/v1/platform/observability", headers=ops).json()
    assert painel["users"]["active_15m"] >= 2  # gestor e operações
    assert painel["queues"]["jobs_queued"] >= 0
    assert painel["ai_service"]["status"] in {"ok", "fora", "desligado", "simulado"}
    for rota in ("/v1/platform/observability", "/v1/platform/observability/alerts",
                 "/v1/platform/observability/alert-rules"):
        assert client.get(rota, headers=admin_token).status_code == 403


def test_tecnico_do_cliente_reconhece_alerta_e_suporte_em_leitura_nao(
    client: TestClient, robo, session: Session, demo: dict, equipe
) -> None:
    tecnico = User(email="tecnico@valtexa.dev", full_name="Técnico",
                   password_hash=hash_password(DEMO_PASSWORD))
    session.add(tecnico)
    session.flush()
    session.add(Membership(tenant_id=demo["tenant_id"], user_id=tecnico.id,
                           role=Role.TECHNICIAN))
    session.commit()
    send_telemetry(robo, health={"disk_percent": 96.0})
    alertas.avaliar(session, ia=IA_OK)
    alerta = session.scalars(select(Alert)).one()
    events.drain(session)
    assert _avisos(session, "tecnico@valtexa.dev", "alerta_robo")
    suporte = client.post("/v1/platform/support-sessions", headers=equipe(PlatformRole.SUPORTE),
                          json={"tenant_id": demo["tenant_id"], "reason": "Conferir alertas"})
    token = {"Authorization": f"Bearer {suporte.json()['access_token']}"}
    assert client.get("/v1/observability/alerts", headers=token).status_code == 200
    assert client.post(f"/v1/observability/alerts/{alerta.id}/ack", headers=token,
                       json={}).status_code == 403
    r = client.post(f"/v1/observability/alerts/{alerta.id}/ack",
                    headers=_login(client, "tecnico@valtexa.dev"), json={})
    assert r.status_code == 200 and r.json()["acknowledged_label"] == "Técnico"


def test_nada_de_nan_nas_metricas(session: Session) -> None:
    for familia in observabilidade.familias(session):
        for amostra in familia.amostras:
            assert not math.isnan(amostra.valor), familia.nome


def test_catalogo_de_regras_aguenta_dois_workers(session: Session, session_factory,
                                                 monkeypatch: pytest.MonkeyPatch) -> None:
    """Dois workers num banco novo criam o catálogo ao mesmo tempo: o segundo não cai.

    Achado rodando quatro workers em paralelo no Postgres (UniqueViolation em
    ``uq_alert_rule_scope`` derrubava a avaliação). Aqui o "outro worker" é simulado:
    a consulta de existentes mente que não há nada, e as linhas já estão no banco.
    """
    with session_factory() as outro:
        assert alertas.sincronizar_catalogo(outro) == len(alertas.REGRAS)
        outro.commit()
    original = session.scalars

    def nada_existe(consulta, *a, **k):
        if "alert_rule.kind" in str(consulta) and "alert_rule.tenant_id IS NULL" in str(consulta):
            return iter(())
        return original(consulta, *a, **k)

    monkeypatch.setattr(session, "scalars", nada_existe)
    assert alertas.sincronizar_catalogo(session) == 0
    session.commit()
    monkeypatch.undo()
    assert alertas.avaliar(session, ia=IA_OK).erros == 0


def test_fotografia_do_banco_e_guardada_por_alguns_segundos(session: Session, robo) -> None:
    primeira = observabilidade.familias(session)
    send_telemetry(robo, health={"cpu_percent": 99.0})
    assert observabilidade.familias(session) == primeira  # dentro dos 15 s: a mesma
    observabilidade._FAMILIAS_CACHE["em"] = 0.0  # venceu
    texto = "\n".join(f.render() for f in observabilidade.familias(session))
    assert 'device="OBS-ROVER"} 99' in texto


# --- Verificação da Parte 7 (feita na Parte 8): três defeitos, cada um com o seu teste ---


def test_reconhecer_enquanto_o_worker_resolve_nao_deixa_alerta_eterno(
    robo, session: Session, session_factory
) -> None:
    send_telemetry(robo, health={"disk_percent": 95.0})
    assert alertas.avaliar(session, ia=IA_OK).disparados == 1
    alerta_id = session.scalars(select(Alert.id).where(Alert.kind == "disco_rover")).one()
    with session_factory() as rota:
        lido = rota.get(Alert, alerta_id)  # a rota leu "disparado"...
        quem = rota.scalars(select(User)).first()
        assert lido.state == "disparado"
        send_telemetry(robo, health={"disk_percent": 40.0})
        assert alertas.avaliar(session, ia=IA_OK).resolvidos == 1  # ...o worker resolveu
        with pytest.raises(alertas.AlertError) as erro:
            alertas.reconhecer(rota, lido, by=quem, note=None, quem="x")
        assert erro.value.status == 409
        rota.commit()
    session.expire_all()
    alerta = session.get(Alert, alerta_id)
    assert (alerta.state, alerta.open_key) == ("resolvido", None)


def test_cliente_nao_cala_o_aviso_de_robo_offline_da_equipe(
    client: TestClient, admin_token: dict, robo, session: Session, equipe
) -> None:
    r = client.put("/v1/observability/alert-rules/rover_offline", headers=admin_token,
                   json={"enabled": False})
    assert r.status_code == 403
    regras = {x["kind"] for x in client.get("/v1/observability/alert-rules",
                                              headers=admin_token).json()}
    assert "rover_offline" not in regras and "disco_rover" in regras
    device = _robo(session, robo.device_id)
    device.last_seen_at = datetime.now(UTC) - timedelta(minutes=45)
    session.commit()
    assert alertas.avaliar(session, ia=IA_OK).disparados == 1
    events.drain(session)
    assert _avisos(session, "equipe@valtexa.dev", "plataforma_alerta")


def test_equipe_desligar_a_padrao_vale_tambem_para_a_copia_do_cliente(
    client: TestClient, admin_token: dict, robo, session: Session, equipe
) -> None:
    assert client.put("/v1/observability/alert-rules/disco_rover", headers=admin_token,
                      json={"threshold": 92}).status_code == 200
    assert client.put("/v1/platform/observability/alert-rules/disco_rover",
                      headers=equipe(PlatformRole.OPERACOES), json={"enabled": False}
                      ).status_code == 200
    send_telemetry(robo, health={"disk_percent": 95.0})
    assert alertas.avaliar(session, ia=IA_OK).disparados == 0
    assert client.put("/v1/platform/observability/alert-rules/disco_rover",
                      headers=equipe(PlatformRole.OPERACOES), json={"enabled": True}
                      ).status_code == 200
    assert alertas.avaliar(session, ia=IA_OK).disparados == 1  # e a cópia (92 %) volta a valer
