"""Isolamento entre clientes e escalada de privilégio, gerados do OpenAPI.

Brief, seções 27 e 43: o cliente A jamais lê nem altera dado do cliente B — e a
garantia tem de valer para **toda** rota, inclusive as que ainda vão nascer.
Por isso a lista de rotas não é escrita à mão: sai de ``app.openapi()``. Cada
operação é classificada pelo tipo de quem a pode chamar (dependências do
FastAPI) e atacada:

* **rota de cliente** — o atacante (outro cliente, com todos os papéis) chama a
  rota com os identificadores da vítima no caminho e no corpo. Tem de dar 403,
  404 ou 422 (nunca 2xx, nunca 409/500, que confirmariam a existência ou
  quebrariam), e nenhuma resposta 2xx pode conter identificador da vítima;
* **rota de plataforma** — nenhum papel de cliente passa (403): escalada;
* **rota do dispositivo** — um robô do atacante não alcança missão, aplicação
  nem talhão da vítima;
* e, no fim, **o estado da vítima no banco não mudou** — linha por linha, em
  toda tabela com ``tenant_id``.

Uma rota nova que não se encaixe em nenhuma classe faz o teste falhar: é o
aviso de que alguém criou uma porta sem dizer quem pode passar por ela.

Também daqui: com sessão de suporte em **modo leitura**, toda operação de
escrita de cliente dá 403.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, date, datetime
from typing import Any

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from tests.conftest import DEMO_PASSWORD
from tests.helpers import DeviceSession, provision, send_telemetry, upload_observation
from tests.test_collections import cria_coleta, sobe_arquivo
from valtexa.main import app
from valtexa.models import (
    Alert,
    AlertRule,
    Application,
    Base,
    EdgeRecord,
    Membership,
    Notification,
    NotificationPreference,
    PlatformRole,
    Role,
    RowScan,
    Tenant,
    TenantScoped,
    User,
    Verification,
)
from valtexa.security.passwords import hash_password
from valtexa.services import edge_sync

SEGUROS = {"GET", "HEAD", "OPTIONS"}

PUBLICAS = {
    ("POST", "/v1/auth/login"),
    ("POST", "/v1/device/provision"),
    ("GET", "/v1/device/time"),
    ("GET", "/health"),
}
"""Rotas sem autenticação, revistas uma a uma: nenhuma devolve dado de cliente.
``/device/provision`` troca um convite de uso único (hash) por identidade."""

PLATAFORMA_POR_TOKEN = {("GET", "/metrics")}
"""Autenticam sem dependência do FastAPI (o Prometheus manda ``METRICS_TOKEN``); sem
o token, exigem o login da equipe com a capacidade — por isso entram na classe
"plataforma" e apanham dos mesmos ataques: todo papel de cliente leva 403."""

SO_A_PROPRIA_CONTA = {
    ("POST", "/v1/auth/logout"),
    ("POST", "/v1/auth/password"),
}
"""Agem só sobre a conta de quem chama, sem identificador de mais ninguém. Ficam
fora do ataque porque derrubariam a sessão do próprio atacante no meio da
varredura; o comportamento delas é coberto em test_sessoes.py."""

PERMITIDOS_NO_ATAQUE = {403, 404, 422}
"""O que uma rota pode responder ao atacante. 409 ou 400 dariam pista de que o
recurso existe e está noutro estado; 2xx é vazamento; 5xx é falha."""

INCONCLUSIVOS_ESPERADOS = {
    # Exigem multipart ou parâmetros que o gerador genérico não monta; a recusa
    # 422 acontece antes do filtro de tenant. O isolamento delas é coberto por
    # testes próprios (test_security.py, test_protocol.py) e pelo snapshot final.
}


# ---------------------------------------------------------------------------
# Classificação das operações
# ---------------------------------------------------------------------------


def _rotas() -> dict[tuple[str, str], APIRoute]:
    """(método, caminho do OpenAPI) → rota, atravessando os roteadores incluídos."""

    def andar(rotas, prefixo=""):
        for rota in rotas:
            if isinstance(rota, APIRoute):
                yield prefixo, rota
            elif hasattr(rota, "original_router"):
                yield from andar(
                    rota.original_router.routes, prefixo + rota.include_context.prefix
                )

    saida = {}
    for prefixo, rota in andar(app.routes):
        for metodo in rota.methods:
            saida[(metodo, prefixo + rota.path)] = rota
    return saida


def _dependencias(rota: APIRoute) -> list[str]:
    nomes: list[str] = []

    def andar(dependant):
        for sub in dependant.dependencies:
            nomes.append(getattr(sub.call, "__qualname__", str(sub.call)))
            andar(sub)

    andar(rota.dependant)
    return nomes


def classificar(metodo: str, caminho: str, rota: APIRoute) -> str:
    if (metodo, caminho) in PUBLICAS:
        return "publica"
    if (metodo, caminho) in PLATAFORMA_POR_TOKEN:
        return "plataforma"
    nomes = _dependencias(rota)
    if any("current_device" in n or "require_active_device" in n for n in nomes):
        return "dispositivo"
    if any(n.startswith(("require_platform.", "require_platform_in_tenant.",
                         "require_platform_ou_suporte.")) for n in nomes):
        return "plataforma"
    if any("_dono_da_sessao" in n for n in nomes):
        return "suporte"
    if any("current_principal" in n for n in nomes):
        return "cliente"
    if any(n in ("current_user", "current_user_ou_suporte") for n in nomes):
        return "usuario"
    return "sem_classe"


def operacoes() -> list[tuple[str, str, str, dict]]:
    """Toda operação do OpenAPI, com a classe e a especificação dela."""
    especificacao = app.openapi()
    rotas = _rotas()
    saida = []
    for caminho, ops in especificacao["paths"].items():
        for metodo, op in ops.items():
            metodo = metodo.upper()
            rota = rotas.get((metodo, caminho))
            assert rota is not None, f"{metodo} {caminho} está no OpenAPI e não nas rotas"
            saida.append((metodo, caminho, classificar(metodo, caminho, rota), op))
    return saida


def test_toda_operacao_do_openapi_tem_classe() -> None:
    sem_classe = [f"{m} {c}" for m, c, classe, _ in operacoes() if classe == "sem_classe"]
    assert not sem_classe, (
        "Rotas sem autenticação reconhecida (declare a dependência ou acrescente a "
        f"PUBLICAS depois de revisar): {sem_classe}"
    )
    assert len(operacoes()) >= 140, "o OpenAPI encolheu: a classificação quebrou?"


# ---------------------------------------------------------------------------
# A vítima e o atacante
# ---------------------------------------------------------------------------


def _login(client: TestClient, email: str) -> dict[str, str]:
    resposta = client.post("/v1/auth/login", json={"email": email, "password": DEMO_PASSWORD})
    assert resposta.status_code == 200, resposta.text
    corpo = resposta.json()
    return {"Authorization": f"Bearer {corpo['access_token']}", "X-Tenant-Id": corpo["tenant_id"]}


@pytest.fixture
def atacante(client: TestClient, session_factory) -> dict:
    """Outro cliente, com um usuário de cada papel e um robô provisionado."""
    with session_factory() as sessao:
        tenant = Tenant(name="Atacante Agro", slug="atacante-agro")
        sessao.add(tenant)
        sessao.flush()
        for papel in Role:
            user = User(
                email=f"{papel.value}@atacante.dev",
                full_name=f"Atacante {papel.value}",
                password_hash=hash_password(DEMO_PASSWORD),
            )
            sessao.add(user)
            sessao.flush()
            sessao.add(Membership(tenant_id=tenant.id, user_id=user.id, role=papel))
        sessao.commit()
        tenant_id = tenant.id
    tokens = {papel: _login(client, f"{papel.value}@atacante.dev") for papel in Role}
    robo = provision(client, tokens[Role.OWNER], "ROVER_SCOUT_V1", "ATK-ROVER")
    return {"tenant_id": tenant_id, "tokens": tokens, "robo": robo}


@pytest.fixture
def vitima(
    client: TestClient,
    demo: dict,
    admin_token: dict,
    operator_token: dict,
    platform_token: dict,
    session: Session,
    equipe,
    store,
) -> dict:
    """O cliente de demonstração com um recurso de cada tipo que tem rota."""
    ids: dict[str, str] = {
        "tenant_id": demo["tenant_id"],
        "farm_id": demo["farm_id"],
        "field_id": demo["field_id"],
        "zone_id": demo["zone_id"],
        "product_id": demo["product_id"],
        "batch_id": demo["batch_id"],
        "product_batch_id": demo["batch_id"],
    }

    rover: DeviceSession = provision(
        client, admin_token, "ROVER_SCOUT_V1", "VIT-ROVER", demo["farm_id"]
    )
    send_telemetry(rover, battery_percent=95.0)
    ids["device_id"] = rover.device_id

    missao = client.post(
        "/v1/missions",
        json={"kind": "scout", "field_id": demo["field_id"], "device_id": rover.device_id},
        headers=operator_token,
    )
    assert missao.status_code == 201, missao.text
    ids["mission_id"] = missao.json()["id"]

    enviada = upload_observation(rover, demo["field_id"], mission_id=ids["mission_id"])
    assert enviada.status_code in (200, 201), enviada.text
    observacoes = client.get("/v1/observations", headers=admin_token).json()
    ids["observation_id"] = observacoes[0]["id"]
    diagnosticos = client.get("/v1/diagnoses", headers=admin_token).json()
    ids["diagnosis_id"] = diagnosticos[0]["id"]

    # Sincronização do Rover Runtime: um registro e um upload em andamento da vítima.
    corpo = {"id": "registro-da-vitima", "kind": "event", "type": "IMAGE_EVENT_DETECTED",
             "device_id": rover.device_id, "mission_id": ids["mission_id"],
             "field_id": demo["field_id"], "occurred_at": datetime.now(UTC).isoformat(),
             "payload": {"label": "Rust"}}
    registro = rover.request("POST", "/v1/device/edge/records", json_body={"records": [
        {"id": corpo["id"], "kind": "event", "type": corpo["type"],
         "sha256": edge_sync.canonical_sha256(corpo), "body": corpo}]})
    assert registro.json()["accepted"] == [corpo["id"]], registro.text
    aberto = rover.request("POST", "/v1/device/uploads", json_body={
        "upload_id": "upload-da-vitima", "sha256": "a" * 64, "size_bytes": 5000,
        "content_type": "image/jpeg", "chunk_size": 4096, "record_id": corpo["id"]})
    assert aberto.status_code == 200, aberto.text
    ids["upload_id"] = "upload-da-vitima"
    ids["index"] = "0"
    ids["record_pk"] = session.scalars(select(EdgeRecord.id).where(
        EdgeRecord.record_id == corpo["id"])).one()

    # OTA: um pacote destinado ao robô da vítima (o atacante tenta baixar e informar).
    from tests.test_ota import publicar, tar_de

    equipe_ops = equipe(PlatformRole.OPERACOES)
    pacote = publicar(client, equipe_ops, "config", "isolamento-1",
                      tar_de({"rover.json": b"{}"}))
    assert pacote.status_code == 201, pacote.text
    destino = client.post("/v1/platform/ota/deployments", json={
        "package_id": pacote.json()["id"], "device_ids": [rover.device_id]}, headers=equipe_ops)
    assert destino.status_code == 201, destino.text
    ids["deployment_id"] = destino.json()[0]["id"]

    tanques = client.get("/v1/tanks", headers=admin_token).json()
    if tanques:
        ids["tank_id"] = tanques[0]["id"]

    aplicacao = Application(
        tenant_id=demo["tenant_id"],
        mission_id=ids["mission_id"],
        device_id=rover.device_id,
        field_id=demo["field_id"],
        started_at=datetime.now(UTC),
    )
    session.add(aplicacao)
    session.flush()
    verificacao = Verification(
        tenant_id=demo["tenant_id"], application_id=aplicacao.id, field_id=demo["field_id"]
    )
    varredura = RowScan(
        tenant_id=demo["tenant_id"],
        farm_id=demo["farm_id"],
        field_id=demo["field_id"],
        device_id=rover.device_id,
        sequence_number=99_999,
        captured_at=datetime.now(UTC),
        origin_lat=-22.41,
        origin_lon=-45.45,
        reach_m=2.0,
    )
    session.add_all([verificacao, varredura])
    session.commit()
    ids["application_id"] = aplicacao.id
    ids["verification_id"] = verificacao.id
    ids["scan_id"] = varredura.id

    coleta = cria_coleta(client, platform_token, demo["field_id"])
    sobe_arquivo(client, platform_token, coleta["id"], "v.jpg", b"\xff\xd8" + b"0" * 64)
    client.post(f"/v1/admin/collections/{coleta['id']}/complete", headers=platform_token)
    ids["collection_id"] = coleta["id"]
    arquivos = client.get(
        f"/v1/admin/collections/{coleta['id']}/files", headers=platform_token
    ).json()
    ids["file_id"] = arquivos[0]["id"]
    trabalhos = client.get("/v1/admin/jobs", headers=platform_token).json()
    if trabalhos:
        ids["job_id"] = trabalhos[0]["id"]

    agronomo = session.scalars(select(User).where(User.email == "agronomo@valtexa.dev")).one()
    ids["user_id"] = agronomo.id
    ids["session_id"] = client.get("/v1/auth/sessions", headers=admin_token).json()[0]["id"]

    suporte = client.post(
        "/v1/platform/support-sessions",
        json={"tenant_id": demo["tenant_id"], "reason": "Sessão da vítima para o teste"},
        headers=equipe(PlatformRole.SUPORTE),
    )
    assert suporte.status_code == 201, suporte.text
    ids["support_session_id"] = suporte.json()["session"]["id"]
    # Notificação (Parte 6): um aviso real para o gestor da vítima.
    from valtexa.services import notifications as avisos

    criados = avisos.notificar(session, avisos.Aviso(
        kind="rover_offline", tenant_id=demo["tenant_id"], title="Robô da vítima caiu",
        body="", dedup="isolamento-vitima"))
    session.commit()
    assert criados
    ids["notification_id"] = criados[0].id
    # Chamado de suporte (Parte 6): ligado ao robô e à missão da vítima, com um
    # comentário da equipe e uma nota interna — o atacante tenta ler e comentar.
    chamado = client.post("/v1/support/tickets", headers=operator_token, json={
        "title": "Chamado da vítima", "description": "Robô da vítima parou no talhão.",
        "device_id": rover.device_id, "mission_id": ids["mission_id"]})
    assert chamado.status_code == 201, chamado.text
    ids["ticket_id"] = chamado.json()["id"]
    suporte_equipe = equipe(PlatformRole.SUPORTE)
    for interno in (True, False):
        r = client.post(f"/v1/platform/tickets/{ids['ticket_id']}/comments",
                        headers=suporte_equipe,
                        json={"body": "Nota da equipe sobre a vítima", "internal": interno})
        assert r.status_code == 200, r.text
    incidente = client.post("/v1/platform/incidents", headers=suporte_equipe, json={
        "title": "Incidente com a vítima", "ticket_ids": [ids["ticket_id"]]})
    assert incidente.status_code == 201, incidente.text
    ids["incident_id"] = incidente.json()["id"]
    # Observabilidade (Parte 7): robô da vítima com disco cheio → alerta real, e uma
    # regra própria da vítima. O atacante tenta reconhecer o alerta e mexer na regra.
    from valtexa.services import alertas

    r = send_telemetry(rover, health={"disk_percent": 97.0, "cameras": []})
    assert r.status_code == 200, r.text
    regra = client.put("/v1/observability/alert-rules/temperatura_rover", headers=admin_token,
                       json={"threshold": 60})
    assert regra.status_code == 200, regra.text
    assert alertas.avaliar(session).disparados >= 1
    ids["alert_id"] = session.scalars(select(Alert).where(
        Alert.tenant_id == demo["tenant_id"], Alert.kind == "disco_rover")).one().id
    ids["kind"] = "regra-inexistente"
    # Sem recurso desse tipo no cliente de demonstração, um identificador que não
    # existe: a rota precisa responder 404 de qualquer jeito.
    ids.setdefault("tank_id", "tanque-inexistente")
    ids.setdefault("job_id", "trabalho-inexistente")
    ids["plant_id"] = "planta-da-vitima"
    ids["dataset_id"] = "dataset-qualquer"
    ids["plan_id"] = "plano-qualquer"
    ids["model_version_id"] = "versao-de-modelo-qualquer"
    ids["release_id"] = "liberacao-qualquer"
    ids["plant_ref"] = "L03-P0001"
    ids["command_id"] = "comando-qualquer"
    ids["camera_id"] = "cam-0"
    ids["resultado_id"] = "resultado-qualquer"
    return ids


def _foto(session: Session, tenant_id: str) -> dict[str, list]:
    """Toda linha do cliente em toda tabela com ``tenant_id``, mais o próprio cliente."""
    session.expire_all()
    foto: dict[str, list] = {}
    for mapeador in Base.registry.mappers:
        classe = mapeador.class_
        if not issubclass(classe, TenantScoped):
            continue
        linhas = session.scalars(select(classe).where(classe.tenant_id == tenant_id)).all()
        foto[classe.__tablename__] = sorted(
            json.dumps(
                {
                    coluna.key: str(getattr(linha, coluna.key))
                    for coluna in mapeador.column_attrs
                    # Presença da sessão e crédito usado não são dado do cliente
                    # alterado pelo atacante: o próprio teste os mexe ao logar.
                    if coluna.key not in {"last_seen_at", "last_used_at", "updated_at"}
                },
                sort_keys=True,
            )
            for linha in linhas
        )
    # Tabelas com ``tenant_id`` anulável (avisos da equipe não são de cliente),
    # fora de TenantScoped, mas com dado do cliente: entram na foto também.
    for classe in (Notification, NotificationPreference, Alert, AlertRule):
        mapeador = classe.__mapper__
        foto[classe.__tablename__] = sorted(
            json.dumps({c.key: str(getattr(linha, c.key)) for c in mapeador.column_attrs
                        if c.key != "updated_at"}, sort_keys=True)
            for linha in session.scalars(select(classe).where(classe.tenant_id == tenant_id))
        )
    tenant = session.get(Tenant, tenant_id)
    foto["tenant"] = [str(tenant.name), str(tenant.is_active)]
    foto["membership"] = sorted(
        f"{m.user_id}:{m.role}"
        for m in session.scalars(select(Membership).where(Membership.tenant_id == tenant_id))
    )
    return foto


# ---------------------------------------------------------------------------
# Montagem genérica de requisição a partir do esquema
# ---------------------------------------------------------------------------

POLIGONO = [[-45.4530, -22.4120], [-45.4515, -22.4120], [-45.4515, -22.4132], [-45.4530, -22.4132]]


def _resolver(esquema: dict, componentes: dict) -> dict:
    while "$ref" in esquema:
        esquema = componentes[esquema["$ref"].rsplit("/", 1)[1]]
    if "anyOf" in esquema:
        opcoes = [o for o in esquema["anyOf"] if o.get("type") != "null"]
        if opcoes:
            return _resolver(opcoes[0], componentes)
    if "allOf" in esquema and len(esquema["allOf"]) == 1:
        return _resolver(esquema["allOf"][0], componentes)
    return esquema


def _valor(nome: str, esquema: dict, componentes: dict, ids: dict, nivel: int = 0) -> Any:
    if nome in ids:
        return ids[nome]
    esquema = _resolver(esquema, componentes)
    if "enum" in esquema:
        return esquema["enum"][0]
    tipo = esquema.get("type")
    if nome in {"boundary", "target_polygon", "polygon"}:
        return POLIGONO
    if tipo == "object" or "properties" in esquema:
        return _objeto(esquema, componentes, ids, nivel + 1)
    if tipo == "array":
        minimo = esquema.get("minItems", 0)
        item = esquema.get("items", {})
        return [_valor(nome, item, componentes, ids, nivel + 1) for _ in range(minimo)]
    if tipo == "integer":
        return max(1, esquema.get("minimum", 1))
    if tipo == "number":
        return float(max(1, esquema.get("minimum", 1) or 1))
    if tipo == "boolean":
        return True
    if esquema.get("format") == "date-time":
        return datetime.now(UTC).isoformat()
    if esquema.get("format") == "date":
        return date.today().isoformat()
    if esquema.get("format") == "email":
        return "ataque@atacante.dev"
    minimo = esquema.get("minLength", 1)
    return ("ataque-isolamento-" * 4)[: max(minimo, 18)]


def _objeto(esquema: dict, componentes: dict, ids: dict, nivel: int = 0) -> dict:
    if nivel > 4:
        return {}
    propriedades = esquema.get("properties", {})
    saida = {}
    for nome, sub in propriedades.items():
        # Todo identificador conhecido vai, obrigatório ou não: é por ele que o
        # atacante tentaria alcançar a vítima.
        if nome in esquema.get("required", []) or nome in ids:
            saida[nome] = _valor(nome, sub, componentes, ids, nivel)
    return saida


def montar(caminho: str, op: dict, ids: dict) -> tuple[str, dict, Any]:
    componentes = app.openapi()["components"]["schemas"]
    url = re.sub(r"{(\w+)}", lambda m: ids[m.group(1)], caminho)
    consulta = {}
    for parametro in op.get("parameters", []):
        if parametro["in"] == "query" and parametro.get("required"):
            consulta[parametro["name"]] = _valor(
                parametro["name"], parametro.get("schema", {}), componentes, ids
            )
    if caminho == "/v1/stream":
        consulta["timeout"] = 1
    corpo = None
    conteudo = op.get("requestBody", {}).get("content", {})
    if "application/json" in conteudo:
        corpo = _valor("body", conteudo["application/json"]["schema"], componentes, ids)
    return url, consulta, corpo


def _ids_da_vitima(ids: dict) -> set[str]:
    # Identificadores reais (32 hex) — os de mentira não aparecem em resposta nenhuma.
    return {v for v in ids.values() if isinstance(v, str) and re.fullmatch(r"[0-9a-f]{32}", v)}


# ---------------------------------------------------------------------------
# Os testes
# ---------------------------------------------------------------------------


def test_cliente_a_nao_le_nem_altera_dado_do_cliente_b(
    client: TestClient, vitima: dict, atacante: dict, session: Session
) -> None:
    antes = _foto(session, vitima["tenant_id"])
    proibidos = _ids_da_vitima(vitima)
    problemas: list[str] = []
    resultado: dict[str, int] = {}
    atacadas = 0

    for metodo, caminho, classe, op in operacoes():
        if classe not in {"cliente", "usuario"} or (metodo, caminho) in SO_A_PROPRIA_CONTA:
            continue
        url, consulta, corpo = montar(caminho, op, vitima)
        tem_alvo = "{" in caminho or (corpo is not None and proibidos & set(_folhas(corpo)))
        for papel in (Role.OWNER, Role.AGRONOMIST, Role.AUDITOR):
            headers = atacante["tokens"][papel]
            resposta = client.request(metodo, url, params=consulta, json=corpo, headers=headers)
            atacadas += 1
            chave = f"{metodo} {caminho} [{papel.value}]"
            resultado[chave] = resposta.status_code
            if resposta.status_code >= 500:
                problemas.append(f"{chave}: {resposta.status_code} (falha do servidor)")
            elif tem_alvo and resposta.status_code not in PERMITIDOS_NO_ATAQUE:
                problemas.append(f"{chave}: {resposta.status_code} {resposta.text[:160]}")
            elif 200 <= resposta.status_code < 300:
                texto = resposta.text
                vazados = [i for i in proibidos if i in texto]
                if vazados:
                    problemas.append(f"{chave}: resposta contém id da vítima {vazados[:3]}")

    assert not problemas, "\n".join(problemas)
    assert _foto(session, vitima["tenant_id"]) == antes, "o estado da vítima mudou"
    # Sanidade: a maioria das recusas com alvo é 404 (o recurso "não existe" para o
    # atacante), não 422 de corpo mal montado — senão o teste não provaria nada.
    com_alvo = [s for k, s in resultado.items() if "{" in k]
    assert com_alvo and sum(1 for s in com_alvo if s in (403, 404)) / len(com_alvo) > 0.8
    assert atacadas > 250


def _folhas(valor: Any) -> list[str]:
    if isinstance(valor, dict):
        return [f for v in valor.values() for f in _folhas(v)]
    if isinstance(valor, list):
        return [f for v in valor for f in _folhas(v)]
    return [valor] if isinstance(valor, str) else []


def test_robo_de_um_cliente_nao_alcanca_o_outro(
    client: TestClient, vitima: dict, atacante: dict, session: Session
) -> None:
    antes = _foto(session, vitima["tenant_id"])
    robo: DeviceSession = atacante["robo"]
    problemas = []
    for metodo, caminho, classe, op in operacoes():
        if classe != "dispositivo" or "{" not in caminho:
            continue
        url, _, corpo = montar(caminho, op, vitima)
        resposta = robo.request(metodo, url, json_body=corpo if corpo is not None else {})
        if resposta.status_code not in PERMITIDOS_NO_ATAQUE:
            problemas.append(f"{metodo} {caminho}: {resposta.status_code} {resposta.text[:160]}")

    # A observação com o talhão da vítima no metadado.
    foto = upload_observation(robo, vitima["field_id"])
    if foto.status_code not in PERMITIDOS_NO_ATAQUE:
        problemas.append(f"observação no talhão da vítima: {foto.status_code} {foto.text[:160]}")

    assert not problemas, "\n".join(problemas)
    assert _foto(session, vitima["tenant_id"]) == antes


CLIENTE_PAPEIS = list(Role)


def test_nenhum_papel_de_cliente_alcanca_rota_de_plataforma(
    client: TestClient, vitima: dict, atacante: dict
) -> None:
    """Escalada de privilégio: dono, gestor e os demais batem em toda rota de plataforma."""
    problemas = []
    alcancadas = 0
    for metodo, caminho, classe, op in operacoes():
        if classe not in {"plataforma", "suporte"}:
            continue
        url, consulta, corpo = montar(caminho, op, vitima)
        for papel in CLIENTE_PAPEIS:
            headers = atacante["tokens"][papel]
            resposta = client.request(metodo, url, params=consulta, json=corpo, headers=headers)
            alcancadas += 1
            if resposta.status_code != 403:
                problemas.append(
                    f"{metodo} {caminho} [{papel.value}]: {resposta.status_code} "
                    f"{resposta.text[:120]}"
                )
    assert not problemas, "\n".join(problemas)
    assert alcancadas >= 30 * len(CLIENTE_PAPEIS)


def test_dono_da_vitima_tambem_nao_alcanca_plataforma(
    client: TestClient, vitima: dict, admin_token: dict
) -> None:
    """O gestor do próprio cliente, com o cliente certo no cabeçalho, também não passa."""
    for metodo, caminho, classe, op in operacoes():
        if classe != "plataforma":
            continue
        url, consulta, corpo = montar(caminho, op, vitima)
        resposta = client.request(metodo, url, params=consulta, json=corpo, headers=admin_token)
        assert resposta.status_code == 403, f"{metodo} {caminho}: {resposta.status_code}"


def test_sessao_de_suporte_em_leitura_nao_escreve_em_rota_nenhuma(
    client: TestClient, vitima: dict, equipe, session: Session
) -> None:
    """Toda operação de escrita de cliente, com o token de suporte em modo leitura: 403."""
    aberta = client.post(
        "/v1/platform/support-sessions",
        json={"tenant_id": vitima["tenant_id"], "reason": "Leitura para conferir isolamento"},
        headers=equipe(PlatformRole.SUPORTE),
    )
    assert aberta.status_code == 201, aberta.text
    token = {"Authorization": f"Bearer {aberta.json()['access_token']}"}
    antes = _foto(session, vitima["tenant_id"])
    problemas = []
    escritas = 0
    for metodo, caminho, classe, op in operacoes():
        if classe != "cliente" or metodo in SEGUROS or (metodo, caminho) in SO_A_PROPRIA_CONTA:
            continue
        url, consulta, corpo = montar(caminho, op, vitima)
        resposta = client.request(metodo, url, params=consulta, json=corpo, headers=token)
        escritas += 1
        if resposta.status_code != 403:
            problemas.append(f"{metodo} {caminho}: {resposta.status_code} {resposta.text[:120]}")
    assert not problemas, "\n".join(problemas)
    assert escritas >= 30
    assert _foto(session, vitima["tenant_id"]) == antes
