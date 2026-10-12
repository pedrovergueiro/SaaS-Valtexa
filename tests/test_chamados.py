"""Suporte (seção 49): chamado, comentários, histórico, incidente, sessão e avisos.

O roteiro de um chamado real, pela API:

1. o operador do cliente abre o chamado ligado ao robô e à missão dele;
2. o Suporte recebe o aviso, assume, escreve uma nota **interna** (o cliente não
   vê) e responde ao cliente (o cliente recebe o aviso);
3. o Suporte entra no cliente por uma sessão de suporte **referenciando o
   chamado** — o cliente vê no histórico do chamado;
4. o problema é de vários clientes: vira incidente; quando ele é resolvido, cada
   cliente afetado é avisado com a nota pública;
5. tudo na auditoria.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from tests.conftest import DEMO_PASSWORD
from tests.helpers import provision, send_telemetry
from valtexa.models import (
    AuditEntry,
    Membership,
    Notification,
    PlatformRole,
    Role,
    SupportTicket,
    Tenant,
    TicketComment,
    User,
)
from valtexa.security.passwords import hash_password
from valtexa.services import events


def _login(client: TestClient, email: str) -> dict[str, str]:
    r = client.post("/v1/auth/login", json={"email": email, "password": DEMO_PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}",
            "X-Tenant-Id": r.json()["tenant_id"]}


def _membro(session: Session, tenant_id: str, email: str, papel: Role) -> None:
    user = User(email=email, full_name=email.split("@")[0].title(),
                password_hash=hash_password(DEMO_PASSWORD))
    session.add(user)
    session.flush()
    session.add(Membership(tenant_id=tenant_id, user_id=user.id, role=papel))
    session.commit()


def _outro_cliente(session: Session, slug: str = "outra-fazenda") -> str:
    tenant = Tenant(name=f"Fazenda {slug}", slug=slug)
    session.add(tenant)
    session.commit()
    _membro(session, tenant.id, f"dono@{slug}.dev", Role.OWNER)
    return tenant.id


def _avisos(session: Session, email: str, kind: str | None = None) -> list[Notification]:
    session.expire_all()
    user = session.scalars(select(User).where(User.email == email)).one()
    consulta = select(Notification).where(Notification.user_id == user.id)
    if kind:
        consulta = consulta.where(Notification.kind == kind)
    return list(session.scalars(consulta.order_by(Notification.created_at)))


@pytest.fixture
def robo_e_missao(client: TestClient, admin_token: dict, operator_token: dict, demo: dict):
    robo = provision(client, admin_token, "ROVER_SCOUT_V1", "CH-ROVER", demo["farm_id"])
    send_telemetry(robo, battery_percent=90.0)
    missao = client.post("/v1/missions", headers=operator_token, json={
        "kind": "scout", "field_id": demo["field_id"], "device_id": robo.device_id})
    assert missao.status_code == 201, missao.text
    return robo.device_id, missao.json()["id"]


def _abre(client: TestClient, headers: dict, **extra) -> dict:
    corpo = {"title": "Rover parou no meio da linha 3",
             "description": "Desde as 14h o rover não sincroniza e a missão parou.",
             "priority": "alta", **extra}
    r = client.post("/v1/support/tickets", headers=headers, json=corpo)
    assert r.status_code == 201, r.text
    return r.json()


def test_chamado_completo_do_cliente_a_equipe(
    client: TestClient, operator_token: dict, admin_token: dict, session: Session, equipe,
    robo_e_missao, demo: dict
) -> None:
    device_id, mission_id = robo_e_missao
    suporte = equipe(PlatformRole.SUPORTE)
    comercial = equipe(PlatformRole.COMERCIAL)

    # 1. O operador abre, ligado ao robô e à missão.
    ch = _abre(client, operator_token, device_id=device_id, mission_id=mission_id)
    assert ch["code"].startswith("CH-") and ch["status"] == "aberto"
    assert "(CH-ROVER)" in ch["device_label"]
    assert ch["mission_id"] == mission_id and ch["opened_via"] == "cliente"
    assert [h["kind"] for h in ch["history"]] == ["aberto"]
    # Todo o cliente acompanha: o gestor vê na lista.
    assert [t["id"] for t in client.get("/v1/support/tickets",
                                        headers=admin_token).json()] == [ch["id"]]

    # 2. O Suporte recebe o aviso; o comercial não.
    events.drain(session)
    lista = client.get("/v1/platform/notifications", headers=suporte).json()
    assert [a["kind"] for a in lista] == ["plataforma_chamado_novo"]
    assert ch["code"] in lista[0]["title"] and lista[0]["link"] == f"/plataforma/suporte/{ch['id']}"
    assert client.get("/v1/platform/notifications", headers=comercial).json() == []

    # A equipe vê todos os chamados, com o nome do cliente.
    todos = client.get("/v1/platform/tickets", headers=suporte).json()
    nome = session.get(Tenant, demo["tenant_id"]).name
    assert [(t["id"], t["tenant_name"]) for t in todos] == [(ch["id"], nome)]

    # 3. Assume (vai para "em atendimento"), nota interna e resposta ao cliente.
    eu = session.scalars(select(User).where(User.email == "suporte@equipe.valtexa.dev")).one()
    r = client.patch(f"/v1/platform/tickets/{ch['id']}", headers=suporte,
                     json={"assignee_id": eu.id})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "em_atendimento"
    assert r.json()["assignee_label"].endswith("(equipe ValTexa)")
    r = client.post(f"/v1/platform/tickets/{ch['id']}/comments", headers=suporte,
                    json={"body": "Log mostra certificado vencido no rover.", "internal": True})
    assert r.status_code == 200
    r = client.post(f"/v1/platform/tickets/{ch['id']}/comments", headers=suporte,
                    json={"body": "Estamos verificando. Pode reiniciar o rover?"})
    assert r.status_code == 200
    r = client.patch(f"/v1/platform/tickets/{ch['id']}", headers=suporte,
                     json={"status": "aguardando_cliente"})
    assert r.json()["status"] == "aguardando_cliente"
    equipe_ve = r.json()
    assert [c["internal"] for c in equipe_ve["comments"]] == [True, False]

    # O cliente não vê a nota interna (nem no histórico).
    cliente_ve = client.get(f"/v1/support/tickets/{ch['id']}", headers=operator_token).json()
    assert [c["body"] for c in cliente_ve["comments"]] == [
        "Estamos verificando. Pode reiniciar o rover?"]
    assert "certificado" not in str(cliente_ve)
    assert not any(h["internal"] for h in cliente_ve["history"])
    assert cliente_ve["first_response_at"] is not None
    # Nem na trilha de auditoria do cliente (a da equipe guarda, com o cliente no payload).
    trilha = client.get("/v1/audit", headers=admin_token,
                        params={"subject_id": ch["id"]}).json()
    assert trilha and not any(a["payload"].get("internal") for a in trilha)
    nota = session.scalars(select(AuditEntry).where(
        AuditEntry.subject_id == ch["id"], AuditEntry.action == "ticket.commented")).all()
    internas = [a for a in nota if a.payload.get("internal")]
    assert len(internas) == 1 and internas[0].tenant_id is None
    assert internas[0].payload["tenant_id"] == demo["tenant_id"]

    # O operador (quem abriu) é avisado: assumido, resposta e mudança — não da nota interna.
    events.drain(session)
    meus = _avisos(session, "operador@valtexa.dev", "chamado_atualizado")
    assert [a.title for a in meus] == [f"Chamado {ch['code']}: em atendimento",
                                       f"Resposta no chamado {ch['code']}",
                                       f"Chamado {ch['code']}: aguardando você"]
    assert all(a.link == f"/suporte/{ch['id']}" for a in meus)
    assert _avisos(session, "admin@valtexa.dev", "chamado_atualizado") == []

    # 4. O cliente responde: volta para a fila; o responsável é avisado uma vez só.
    r = client.post(f"/v1/support/tickets/{ch['id']}/comments", headers=operator_token,
                    json={"body": "Reiniciei, voltou a sincronizar."})
    assert r.status_code == 200 and r.json()["status"] == "em_atendimento"
    events.drain(session)
    lista = client.get("/v1/platform/notifications", headers=suporte).json()
    respostas = [a for a in lista if a["kind"] == "plataforma_chamado_resposta"]
    assert len(respostas) == 1 and "Reiniciei" in respostas[0]["body"]

    # 5. Resolvido pela equipe, fechado pelo cliente; fechado não recebe comentário.
    client.patch(f"/v1/platform/tickets/{ch['id']}", headers=suporte,
                 json={"status": "resolvido", "note": "Certificado renovado."})
    r = client.post(f"/v1/support/tickets/{ch['id']}/close", headers=operator_token, json={})
    assert r.status_code == 200 and r.json()["status"] == "fechado"
    assert r.json()["closed_at"]
    assert client.post(f"/v1/support/tickets/{ch['id']}/comments", headers=operator_token,
                       json={"body": "mais uma"}).status_code == 409
    assert client.post(f"/v1/support/tickets/{ch['id']}/reopen", headers=operator_token,
                       json={"reason": "x"}).status_code == 422
    r = client.post(f"/v1/support/tickets/{ch['id']}/reopen", headers=operator_token,
                    json={"reason": "Parou de novo hoje cedo."})
    assert r.status_code == 200 and r.json()["status"] == "aberto"
    assert r.json()["closed_at"] is None

    # 6. Histórico completo e auditoria.
    tipos = [h["kind"] for h in client.get(f"/v1/platform/tickets/{ch['id']}",
                                           headers=suporte).json()["history"]]
    assert tipos[:3] == ["aberto", "responsavel", "status"]
    assert tipos.count("comentario") == 3 and tipos[-1] == "status"
    acoes = set(session.scalars(select(AuditEntry.action).where(
        AuditEntry.subject_id == ch["id"])))
    assert {"ticket.created", "ticket.assigned", "ticket.commented",
            "ticket.status_changed"} <= acoes


def test_vinculos_so_do_proprio_cliente(
    client: TestClient, operator_token: dict, session: Session, robo_e_missao, demo
) -> None:
    device_id, mission_id = robo_e_missao
    outro = _outro_cliente(session)
    dono = _login(client, "dono@outra-fazenda.dev")
    antes = session.scalar(select(SupportTicket.id))
    for extra in ({"device_id": device_id}, {"mission_id": mission_id}):
        r = client.post("/v1/support/tickets", headers=dono, json={
            "title": "Tentativa", "description": "Ligar ao robô de outro cliente.", **extra})
        assert r.status_code == 404, r.text
    assert session.scalar(select(SupportTicket.id)) == antes

    # E o chamado de um não aparece nem abre para o outro.
    ch = _abre(client, operator_token)
    assert client.get("/v1/support/tickets", headers=dono).json() == []
    assert client.get(f"/v1/support/tickets/{ch['id']}", headers=dono).status_code == 404
    assert client.post(f"/v1/support/tickets/{ch['id']}/comments", headers=dono,
                       json={"body": "oi"}).status_code == 404
    assert outro


def test_papeis_do_cliente_e_da_equipe(
    client: TestClient, operator_token: dict, session: Session, equipe, demo
) -> None:
    _membro(session, demo["tenant_id"], "leitor@valtexa.dev", Role.VIEWER)
    leitor = _login(client, "leitor@valtexa.dev")
    ch = _abre(client, operator_token)
    # Quem só lê acompanha, mas não abre nem comenta.
    assert client.get(f"/v1/support/tickets/{ch['id']}", headers=leitor).status_code == 200
    assert client.post("/v1/support/tickets", headers=leitor, json={
        "title": "Não posso", "description": "Leitor tentando abrir."}).status_code == 403
    assert client.post(f"/v1/support/tickets/{ch['id']}/comments", headers=leitor,
                       json={"body": "oi"}).status_code == 403

    comercial, operacoes = equipe(PlatformRole.COMERCIAL), equipe(PlatformRole.OPERACOES)
    assert client.get("/v1/platform/tickets", headers=comercial).status_code == 403
    assert client.get("/v1/platform/tickets", headers=operacoes).status_code == 200
    assert client.patch(f"/v1/platform/tickets/{ch['id']}", headers=operacoes,
                        json={"status": "resolvido"}).status_code == 403
    # Quem pode ser responsável: só quem atende chamado (Suporte e superadmin).
    equipe(PlatformRole.SUPORTE)
    nomes = {a["platform_role"] for a in client.get("/v1/platform/support/assignees",
                                                       headers=operacoes).json()}
    assert nomes == {"suporte", "superadmin"}  # a conta de demonstração é superadmin
    # Responsável precisa atender chamado: o comercial não serve.
    alvo = session.scalars(select(User).where(
        User.email == "comercial@equipe.valtexa.dev")).one()
    r = client.patch(f"/v1/platform/tickets/{ch['id']}", headers=equipe(PlatformRole.SUPORTE),
                     json={"assignee_id": alvo.id})
    assert r.status_code == 422 and "Responsável" in r.text
    # O cliente não escreve nota interna (o campo nem existe na rota dele).
    r = client.post(f"/v1/support/tickets/{ch['id']}/comments", headers=operator_token,
                    json={"body": "tentando", "internal": True})
    assert r.status_code == 200
    assert not session.scalars(select(TicketComment).where(TicketComment.internal)).all()


def test_equipe_abre_em_nome_do_cliente_e_numera_em_sequencia(
    client: TestClient, operator_token: dict, equipe, demo
) -> None:
    suporte = equipe(PlatformRole.SUPORTE)
    a = _abre(client, operator_token)
    r = client.post("/v1/platform/tickets", headers=suporte, json={
        "tenant_id": demo["tenant_id"], "title": "Ligação do produtor",
        "description": "Produtor ligou: mapa não carrega no celular."})
    assert r.status_code == 201, r.text
    b = r.json()
    assert b["opened_via"] == "plataforma" and b["opened_by_label"].endswith("(equipe ValTexa)")
    assert int(b["code"][3:]) == int(a["code"][3:]) + 1
    assert client.post("/v1/platform/tickets", headers=suporte, json={
        "tenant_id": "nao-existe", "title": "Ligação", "description": "Cliente inexistente."
    }).status_code == 404
    # O cliente vê o chamado aberto em nome dele.
    assert {t["id"] for t in client.get("/v1/support/tickets", headers=operator_token).json()} \
        == {a["id"], b["id"]}


def test_sessao_de_suporte_referencia_o_chamado(
    client: TestClient, operator_token: dict, session: Session, equipe, demo
) -> None:
    suporte = equipe(PlatformRole.SUPORTE)
    ch = _abre(client, operator_token)
    r = client.post("/v1/platform/support-sessions", headers=suporte, json={
        "tenant_id": demo["tenant_id"], "reason": "Ver os registros do rover do chamado",
        "ticket_id": ch["id"]})
    assert r.status_code == 201, r.text
    sessao = r.json()["session"]
    assert sessao["ticket_id"] == ch["id"] and sessao["ticket_ref"] == ch["code"]
    token = {"Authorization": f"Bearer {r.json()['access_token']}"}

    # O cliente vê, no histórico do chamado, que a equipe entrou por causa dele.
    hist = client.get(f"/v1/support/tickets/{ch['id']}", headers=operator_token).json()["history"]
    entrada = [h for h in hist if h["kind"] == "sessao_suporte"]
    assert len(entrada) == 1 and entrada[0]["new_value"] == "leitura"
    assert "entrou na sua conta" in entrada[0]["note"]
    # A equipe vê a sessão no detalhe do chamado.
    detalhe = client.get(f"/v1/platform/tickets/{ch['id']}", headers=suporte).json()
    assert [s["id"] for s in detalhe["support_sessions"]] == [sessao["id"]]
    # Dentro do cliente, em leitura: lê o chamado, não comenta.
    assert client.get(f"/v1/support/tickets/{ch['id']}", headers=token).status_code == 200
    assert client.post(f"/v1/support/tickets/{ch['id']}/comments", headers=token,
                       json={"body": "oi"}).status_code == 403

    # Chamado de outro cliente não serve de referência.
    outro = _outro_cliente(session, "terceira")
    alheio = _abre(client, _login(client, "dono@terceira.dev"))
    r = client.post("/v1/platform/support-sessions", headers=suporte, json={
        "tenant_id": demo["tenant_id"], "reason": "Referência cruzada de cliente",
        "ticket_id": alheio["id"]})
    assert r.status_code == 404
    assert outro


def test_modo_assistido_comenta_como_equipe(
    client: TestClient, operator_token: dict, equipe, demo
) -> None:
    suporte = equipe(PlatformRole.SUPORTE)
    ch = _abre(client, operator_token)
    r = client.post("/v1/platform/support-sessions", headers=suporte, json={
        "tenant_id": demo["tenant_id"], "reason": "Ajudar o operador no chamado",
        "ticket_id": ch["id"], "assisted_reason": "Responder pelo console do cliente"})
    assert r.status_code == 201, r.text
    token = {"Authorization": f"Bearer {r.json()['access_token']}"}
    r = client.post(f"/v1/support/tickets/{ch['id']}/comments", headers=token,
                    json={"body": "Respondendo de dentro da sua conta."})
    assert r.status_code == 200, r.text
    ultimo = r.json()["comments"][-1]
    assert ultimo["side"] == "plataforma" and ultimo["author_label"].endswith("(equipe ValTexa)")


def test_incidente_agrupa_clientes_e_avisa_cada_um(
    client: TestClient, operator_token: dict, session: Session, equipe, demo
) -> None:
    suporte = equipe(PlatformRole.SUPORTE)
    _outro_cliente(session, "vizinha")
    dono = _login(client, "dono@vizinha.dev")
    a = _abre(client, operator_token)
    b = _abre(client, dono, title="Sincronização parada", priority="urgente")

    r = client.post("/v1/platform/incidents", headers=suporte, json={
        "title": "Fila de sincronização parada", "severity": "alta",
        "ticket_ids": [a["id"], b["id"]],
        "public_note": "Identificamos uma falha na fila de sincronização."})
    assert r.status_code == 201, r.text
    inc = r.json()
    assert inc["code"].startswith("INC-") and inc["ticket_count"] == 2
    assert inc["tenant_count"] == 2
    # O cliente vê o incidente pelo chamado dele, com a nota pública.
    visto = client.get(f"/v1/support/tickets/{a['id']}", headers=operator_token).json()
    assert visto["incident"]["code"] == inc["code"]
    assert visto["incident"]["public_note"].startswith("Identificamos")
    assert any(h["kind"] == "incidente" for h in visto["history"])

    events.drain(session)
    r = client.patch(f"/v1/platform/incidents/{inc['id']}", headers=suporte, json={
        "status": "resolvido", "public_note": "Corrigido às 16h; dados sincronizados."})
    assert r.status_code == 200 and r.json()["resolved_at"]
    events.drain(session)
    for email in ("operador@valtexa.dev", "dono@vizinha.dev"):
        recebidos = [x for x in _avisos(session, email, "chamado_atualizado")
                     if "incidente" in x.title]
        assert len(recebidos) == 1, email
        assert "Corrigido às 16h" in recebidos[0].body
    # Filtrar chamados por incidente; e o incidente na lista dos abertos some.
    por_inc = client.get("/v1/platform/tickets", headers=suporte,
                         params={"incident_id": inc["id"]}).json()
    assert {t["id"] for t in por_inc} == {a["id"], b["id"]}
    assert client.get("/v1/platform/incidents", headers=suporte,
                      params={"open_only": True}).json() == []
    acoes = set(session.scalars(select(AuditEntry.action).where(
        AuditEntry.subject_id == inc["id"])))
    assert {"incident.created", "incident.status_changed", "incident.note_changed"} <= acoes

    # Desligar um chamado do incidente.
    r = client.patch(f"/v1/platform/tickets/{b['id']}", headers=suporte,
                     json={"unlink_incident": True})
    assert r.json()["incident"] is None
    assert client.get(f"/v1/platform/incidents/{inc['id']}",
                      headers=suporte).json()["ticket_count"] == 1
    assert client.get("/v1/platform/incidents/nao-existe", headers=suporte).status_code == 404


def test_cliente_nao_alcanca_rotas_da_plataforma(
    client: TestClient, admin_token: dict, operator_token: dict
) -> None:
    ch = _abre(client, operator_token)
    for metodo, url, corpo in (
        ("GET", "/v1/platform/tickets", None),
        ("GET", f"/v1/platform/tickets/{ch['id']}", None),
        ("PATCH", f"/v1/platform/tickets/{ch['id']}", {"status": "resolvido"}),
        ("POST", f"/v1/platform/tickets/{ch['id']}/comments", {"body": "x", "internal": True}),
        ("GET", "/v1/platform/incidents", None),
    ):
        assert client.request(metodo, url, json=corpo, headers=admin_token).status_code == 403
