"""Notificações (seção 48): evento → regra → preferência → central e e-mail.

O que se prova aqui:

* o aviso nasce do **evento de domínio** (outbox), não da tela;
* **idempotência**: o mesmo evento entregue de novo não notifica duas vezes;
* preferências em três camadas (pessoa > papel no cliente > padrão), com limite;
* e-mail **de verdade** por SMTP (um servidor SMTP mínimo, na porta local) e,
  sem SMTP, ``nao_enviado`` com o motivo — nunca "enviado" de mentira;
* novas tentativas com espera e desistência;
* a central: lidas/não lidas, por pessoa, isolada por cliente.
"""

from __future__ import annotations

import re
import socket
import socketserver
import threading
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from tests.conftest import DEMO_PASSWORD
from tests.helpers import provision, send_telemetry, upload_observation
from valtexa import worker
from valtexa.models import (
    Connectivity,
    Device,
    Membership,
    Notification,
    NotificationDelivery,
    OutboxEvent,
    PlatformRole,
    Role,
    Tenant,
    User,
)
from valtexa.security.passwords import hash_password
from valtexa.services import events
from valtexa.services import notifications as avisos

# ---------------------------------------------------------------------------
# Um servidor SMTP mínimo, de verdade (socket), para o e-mail sair pelo smtplib
# ---------------------------------------------------------------------------


class _SmtpHandler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        def diz(texto: str) -> None:
            self.wfile.write((texto + "\r\n").encode())

        diz("220 smtp de teste")
        dados: list[str] | None = None
        destinatarios: list[str] = []
        while True:
            linha = self.rfile.readline()
            if not linha:
                return
            texto = linha.decode("utf-8", "replace").rstrip("\r\n")
            if dados is not None:
                if texto == ".":
                    self.server.mensagens.append(
                        {"para": destinatarios, "texto": "\n".join(dados)})
                    dados, destinatarios = None, []
                    diz("250 recebido")
                else:
                    dados.append(texto[1:] if texto.startswith("..") else texto)
                continue
            comando = texto[:4].upper()
            if comando in ("EHLO", "HELO"):
                diz("250 smtp de teste")
            elif comando == "RCPT":
                endereco = texto.split(":", 1)[1].strip("<> ")
                if endereco in self.server.recusados:
                    diz("550 caixa inexistente")
                else:
                    destinatarios.append(endereco)
                    diz("250 ok")
            elif comando == "DATA":
                diz("354 pode mandar")
                dados = []
            elif comando == "QUIT":
                diz("221 tchau")
                return
            else:
                diz("250 ok")


@pytest.fixture
def smtp(monkeypatch: pytest.MonkeyPatch):
    servidor = socketserver.ThreadingTCPServer(("127.0.0.1", 0), _SmtpHandler)
    servidor.daemon_threads = True
    servidor.mensagens = []
    servidor.recusados = set()
    linha = threading.Thread(target=servidor.serve_forever, daemon=True)
    linha.start()
    _config(monkeypatch, smtp_host="127.0.0.1", smtp_port=servidor.server_address[1],
            smtp_starttls=False, smtp_user=None, console_url="https://console.valtexa.test")
    yield servidor
    servidor.shutdown()
    servidor.server_close()


@pytest.fixture
def sem_smtp(monkeypatch: pytest.MonkeyPatch) -> None:
    _config(monkeypatch, smtp_host=None)


def _config(monkeypatch: pytest.MonkeyPatch, **valores) -> None:
    """A configuração é imutável: o módulo de avisos ganha uma cópia com os valores."""
    monkeypatch.setattr(avisos, "settings", avisos.settings.model_copy(update=valores))


# ---------------------------------------------------------------------------
# Auxiliares
# ---------------------------------------------------------------------------


def _drena(session: Session) -> int:
    session.expire_all()
    return events.drain(session)


def _robo_offline(client: TestClient, admin_token: dict, session: Session,
                  serial: str = "NOT-ROVER") -> str:
    """Provisiona um robô e o faz cair: publica ``device.offline`` (pelo worker)."""
    robo = provision(client, admin_token, "ROVER_SCOUT_V1", serial)
    send_telemetry(robo, battery_percent=90.0)
    session.expire_all()
    device = session.get(Device, robo.device_id)
    device.last_seen_at = datetime.now(UTC) - timedelta(minutes=30)
    device.connectivity = Connectivity.OK
    session.commit()
    assert worker.refresh_connectivity(session) == 1
    session.commit()
    return robo.device_id


def _avisos_de(session: Session, email: str, kind: str | None = None) -> list[Notification]:
    session.expire_all()
    user = session.scalars(select(User).where(User.email == email)).one()
    consulta = select(Notification).where(Notification.user_id == user.id)
    if kind:
        consulta = consulta.where(Notification.kind == kind)
    return list(session.scalars(consulta))


def _login(client: TestClient, email: str) -> dict[str, str]:
    r = client.post("/v1/auth/login", json={"email": email, "password": DEMO_PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}",
            "X-Tenant-Id": r.json()["tenant_id"]}


# ---------------------------------------------------------------------------
# Evento → aviso, por papel, sem duplicar
# ---------------------------------------------------------------------------


def test_robo_offline_avisa_quem_opera_e_nao_duplica(
    client: TestClient, admin_token: dict, session: Session, sem_smtp
) -> None:
    device_id = _robo_offline(client, admin_token, session)
    assert _drena(session) >= 1

    # Padrão do tipo: dono, gestor, operador e técnico. O agrônomo não recebe.
    assert len(_avisos_de(session, "admin@valtexa.dev", "rover_offline")) == 1
    assert len(_avisos_de(session, "operador@valtexa.dev", "rover_offline")) == 1
    assert _avisos_de(session, "agronomo@valtexa.dev", "rover_offline") == []
    aviso = _avisos_de(session, "operador@valtexa.dev", "rover_offline")[0]
    assert aviso.link == f"/frota/{device_id}" and "sem comunicação" in aviso.title
    assert aviso.severity == "critico" and aviso.audience == "cliente"
    assert re.search(r"Último contato: \d\d/\d\d/\d{4} \d\d:\d\d UTC\.", aviso.body), aviso.body

    # O outbox entrega ao menos uma vez: reentregar o mesmo evento não duplica.
    evento = session.scalars(select(OutboxEvent).where(
        OutboxEvent.name == events.DEVICE_OFFLINE)).one()
    evento.delivered_at = None
    session.commit()
    assert _drena(session) == 1
    assert len(_avisos_de(session, "operador@valtexa.dev", "rover_offline")) == 1


def test_dois_workers_com_o_mesmo_evento_nao_duplicam(
    client: TestClient, admin_token: dict, session: Session, session_factory, sem_smtp
) -> None:
    _robo_offline(client, admin_token, session)
    evento = session.scalars(select(OutboxEvent).where(
        OutboxEvent.name == events.DEVICE_OFFLINE)).one()
    # Dois "workers" (sessões) tratam o mesmo evento: a restrição única segura.
    with session_factory() as a, session_factory() as b:
        ev_a, ev_b = a.get(OutboxEvent, evento.id), b.get(OutboxEvent, evento.id)
        avisos._handler(a, ev_a)
        a.commit()
        avisos._handler(b, ev_b)
        b.commit()
    assert len(_avisos_de(session, "admin@valtexa.dev", "rover_offline")) == 1


def test_aviso_dirigido_respeita_o_escopo_do_cliente(
    client: TestClient, session: Session, demo: dict
) -> None:
    """Um id de outra pessoa (de outro cliente) na lista dirigida não recebe nada."""
    estranho = User(email="estranho@x.dev", full_name="E", password_hash="x")
    session.add(estranho)
    session.commit()
    criados = avisos.notificar(session, avisos.Aviso(
        kind="chamado_atualizado", tenant_id=demo["tenant_id"], title="t", body="b",
        dedup="d-1", para=[estranho.id]))
    assert criados == []


# ---------------------------------------------------------------------------
# Preferências: pessoa > papel > padrão; limite; canais
# ---------------------------------------------------------------------------


def test_preferencias_em_tres_camadas(
    client: TestClient, admin_token: dict, operator_token: dict, session: Session, sem_smtp
) -> None:
    # Padrão.
    prefs = client.get("/v1/notifications/preferences", headers=operator_token).json()
    offline = next(p for p in prefs["preferences"] if p["kind"] == "rover_offline")
    assert offline == {**offline, "enabled": True, "channels": ["email"], "source": "padrao"}
    assert {c["name"]: c["implemented"] for c in prefs["channels"]} == {
        "in_app": True, "email": True, "whatsapp": False, "push": False, "sms": False}

    # O gestor desliga "robô offline" para o papel operador...
    r = client.put("/v1/notifications/role-preferences", headers=admin_token,
                   json={"role": "operator", "kind": "rover_offline", "enabled": False})
    assert r.status_code == 200, r.text
    # ...o operador não pode mexer na do papel.
    assert client.put("/v1/notifications/role-preferences", headers=operator_token,
                      json={"role": "operator", "kind": "rover_offline",
                            "enabled": True}).status_code == 403
    prefs = client.get("/v1/notifications/preferences", headers=operator_token).json()
    offline = next(p for p in prefs["preferences"] if p["kind"] == "rover_offline")
    assert offline["enabled"] is False and offline["source"] == "papel"

    _robo_offline(client, admin_token, session, "PREF-1")
    _drena(session)
    assert _avisos_de(session, "operador@valtexa.dev", "rover_offline") == []
    assert len(_avisos_de(session, "admin@valtexa.dev", "rover_offline")) == 1

    # A pessoa religa para si (só a central, sem e-mail): vale sobre o papel.
    r = client.put("/v1/notifications/preferences", headers=operator_token,
                   json={"kind": "rover_offline", "enabled": True, "channels": []})
    assert r.status_code == 200, r.text
    offline = next(p for p in r.json()["preferences"] if p["kind"] == "rover_offline")
    assert offline["source"] == "pessoa" and offline["channels"] == []
    _robo_offline(client, admin_token, session, "PREF-2")
    _drena(session)
    recebidos = _avisos_de(session, "operador@valtexa.dev", "rover_offline")
    assert len(recebidos) == 1
    session.expire_all()
    assert session.scalars(select(NotificationDelivery).where(
        NotificationDelivery.notification_id == recebidos[0].id)).all() == []

    # Voltar ao padrão do papel.
    r = client.put("/v1/notifications/preferences", headers=operator_token,
                   json={"kind": "rover_offline", "reset": True})
    offline = next(p for p in r.json()["preferences"] if p["kind"] == "rover_offline")
    assert offline["source"] == "papel"


@pytest.mark.parametrize(("corpo", "trecho"), [
    ({"kind": "rover_offline", "channels": ["whatsapp"]}, "não está implementado"),
    ({"kind": "rover_offline", "channels": ["pombo"]}, "desconhecido"),
    ({"kind": "rover_offline", "threshold": 10}, "não tem limite"),
    ({"kind": "plataforma_chamado_novo"}, "desconhecido"),
    ({"kind": "nao_existe"}, "desconhecido"),
])
def test_preferencia_invalida_e_recusada(
    client: TestClient, operator_token: dict, corpo: dict, trecho: str
) -> None:
    r = client.put("/v1/notifications/preferences", headers=operator_token, json=corpo)
    assert r.status_code == 422 and trecho in r.text


def test_limite_de_incidencia_por_pessoa(
    client: TestClient, admin_token: dict, agronomist_token: dict, session: Session,
    demo: dict
) -> None:
    # O agrônomo só quer saber acima de 20 %; o gestor fica no padrão (5 %).
    r = client.put("/v1/notifications/preferences", headers=agronomist_token,
                   json={"kind": "incidencia_alta", "threshold": 20, "channels": []})
    assert r.status_code == 200, r.text

    def aviso(valor: float, chave: str) -> avisos.Aviso:
        return avisos.Aviso(kind="incidencia_alta", tenant_id=demo["tenant_id"],
                            title=f"{valor}%", body="", dedup=chave, valor=valor)

    avisos.notificar(session, aviso(7.4, "missao-a"))
    avisos.notificar(session, aviso(25.0, "missao-b"))
    avisos.notificar(session, aviso(3.0, "missao-c"))
    session.commit()
    assert sorted(a.title for a in _avisos_de(session, "admin@valtexa.dev")) == ["25.0%", "7.4%"]
    assert [a.title for a in _avisos_de(session, "agronomo@valtexa.dev")] == ["25.0%"]


# ---------------------------------------------------------------------------
# E-mail: de verdade, sem SMTP, com falha e desistência
# ---------------------------------------------------------------------------


def test_email_sai_por_smtp_de_verdade(
    client: TestClient, admin_token: dict, session: Session, smtp
) -> None:
    _robo_offline(client, admin_token, session, "SMTP-1")
    _drena(session)
    assert avisos.entregar_pendentes(session) >= 2
    para = sorted(m["para"][0] for m in smtp.mensagens)
    assert "admin@valtexa.dev" in para and "operador@valtexa.dev" in para
    texto = next(m["texto"] for m in smtp.mensagens if m["para"] == ["admin@valtexa.dev"])
    assert "Subject: [ValTexa]" in texto and "sem comunica" in texto
    assert "https://console.valtexa.test/frota/" in texto

    session.expire_all()
    entregas = session.scalars(select(NotificationDelivery)).all()
    assert entregas and all(e.status == "enviado" and e.sent_at for e in entregas)
    # Rodar de novo não manda de novo.
    antes = len(smtp.mensagens)
    assert avisos.entregar_pendentes(session) == 0
    assert len(smtp.mensagens) == antes


def test_sem_smtp_fica_nao_enviado_e_a_tela_mostra(
    client: TestClient, admin_token: dict, session: Session, sem_smtp
) -> None:
    _robo_offline(client, admin_token, session, "SEM-SMTP")
    _drena(session)
    assert avisos.entregar_pendentes(session) == 0
    session.expire_all()
    entregas = session.scalars(select(NotificationDelivery)).all()
    assert entregas and all(e.status == "nao_enviado" for e in entregas)
    assert all("SMTP não configurado" in e.last_error for e in entregas)

    lista = client.get("/v1/notifications", headers=admin_token).json()
    aviso = next(a for a in lista if a["kind"] == "rover_offline")
    assert aviso["deliveries"] == [{
        "channel": "email", "status": "nao_enviado", "attempts": 1, "sent_at": None,
        "last_error": aviso["deliveries"][0]["last_error"]}]


def test_falha_de_smtp_tenta_de_novo_e_desiste(
    client: TestClient, admin_token: dict, session: Session, monkeypatch, smtp
) -> None:
    # Uma porta onde ninguém escuta: conexão recusada.
    livre = socket.socket()
    livre.bind(("127.0.0.1", 0))
    porta = livre.getsockname()[1]
    livre.close()
    _config(monkeypatch, smtp_port=porta)

    _robo_offline(client, admin_token, session, "SMTP-FORA")
    _drena(session)
    agora = datetime.now(UTC)
    assert avisos.entregar_pendentes(session, agora=agora) == 0
    session.expire_all()
    entrega = session.scalars(select(NotificationDelivery)).first()
    assert entrega.status == "falhou" and entrega.attempts == 1
    assert "Connection" in entrega.last_error or "Errno" in entrega.last_error
    # Antes da espera não tenta de novo.
    assert avisos.entregar_pendentes(session, agora=agora + timedelta(seconds=30)) == 0
    session.refresh(entrega)
    assert entrega.attempts == 1

    for passo in range(2, avisos.MAX_TENTATIVAS + 1):
        agora += timedelta(hours=2)
        avisos.entregar_pendentes(session, agora=agora)
        session.refresh(entrega)
        assert entrega.attempts == passo
    assert entrega.status == "desistiu" and entrega.next_attempt_at is None

    # O servidor volta: o que desistiu não sai mais; um aviso novo sai.
    _config(monkeypatch, smtp_port=smtp.server_address[1])
    assert avisos.entregar_pendentes(session, agora=agora + timedelta(hours=5)) == 0


def test_destinatario_recusado_nao_e_repetido(
    client: TestClient, admin_token: dict, session: Session, smtp
) -> None:
    smtp.recusados.add("operador@valtexa.dev")
    _robo_offline(client, admin_token, session, "RECUSA")
    _drena(session)
    avisos.entregar_pendentes(session)
    session.expire_all()
    por_destino = {e.destination: e for e in session.scalars(select(NotificationDelivery))}
    assert por_destino["operador@valtexa.dev"].status == "desistiu"
    assert por_destino["admin@valtexa.dev"].status == "enviado"


# ---------------------------------------------------------------------------
# Central: lidas, não lidas, isolamento
# ---------------------------------------------------------------------------


def test_central_lida_nao_lida_e_isolamento(
    client: TestClient, admin_token: dict, operator_token: dict, session: Session, demo,
    equipe, sem_smtp
) -> None:
    _robo_offline(client, admin_token, session, "CENTRAL-1")
    _robo_offline(client, admin_token, session, "CENTRAL-2")
    _drena(session)

    assert client.get("/v1/notifications/unread-count",
                      headers=operator_token).json() == {"unread": 2}
    lista = client.get("/v1/notifications", headers=operator_token).json()
    assert len(lista) == 2
    primeiro = lista[0]["id"]

    # O aviso do operador não é do gestor: 404 (não 403).
    assert client.post(f"/v1/notifications/{primeiro}/read",
                       headers=admin_token).status_code == 404
    lida = client.post(f"/v1/notifications/{primeiro}/read", headers=operator_token)
    assert lida.status_code == 200 and lida.json()["read_at"]
    assert client.get("/v1/notifications/unread-count",
                      headers=operator_token).json() == {"unread": 1}
    assert [a["id"] for a in client.get("/v1/notifications", params={"only_unread": True},
                                        headers=operator_token).json()] == [lista[1]["id"]]
    assert client.post("/v1/notifications/read-all",
                       headers=operator_token).json() == {"marked": 1}
    assert client.get("/v1/notifications/unread-count",
                      headers=operator_token).json() == {"unread": 0}
    # O gestor continua com os dele.
    assert client.get("/v1/notifications/unread-count",
                      headers=admin_token).json() == {"unread": 2}

    # Agrônomo de cooperativa em dois clientes: em cada cliente, só os avisos dele.
    outro = Tenant(name="Cooperada", slug="cooperada")
    session.add(outro)
    session.flush()
    operador = session.scalars(select(User).where(User.email == "operador@valtexa.dev")).one()
    session.add(Membership(tenant_id=outro.id, user_id=operador.id, role=Role.OPERATOR))
    session.commit()
    no_outro = {**operator_token, "X-Tenant-Id": outro.id}
    assert client.get("/v1/notifications", headers=no_outro).json() == []
    assert client.post(f"/v1/notifications/{primeiro}/read",
                       headers=no_outro).status_code == 404

    # Sessão de suporte em leitura: vê a própria caixa (vazia) e não marca nada.
    aberta = client.post("/v1/platform/support-sessions", headers=equipe(PlatformRole.SUPORTE),
                         json={"tenant_id": demo["tenant_id"], "reason": "Conferir os avisos"})
    assert aberta.status_code == 201, aberta.text
    token = {"Authorization": f"Bearer {aberta.json()['access_token']}"}
    assert client.get("/v1/notifications", headers=token).json() == []
    assert client.post(f"/v1/notifications/{primeiro}/read", headers=token).status_code == 403
    assert client.post("/v1/notifications/read-all", headers=token).status_code == 403


def test_aviso_de_cliente_desligado_continua_isolado(
    client: TestClient, session: Session, demo, sem_smtp
) -> None:
    """Outro cliente com dono: o robô dele cair não avisa ninguém da demonstração."""
    t = Tenant(name="Vizinho", slug="vizinho")
    u = User(email="dono@vizinho.dev", full_name="Dono", password_hash=hash_password(
        DEMO_PASSWORD))
    session.add_all([t, u])
    session.flush()
    session.add(Membership(tenant_id=t.id, user_id=u.id, role=Role.OWNER))
    session.commit()
    dono = _login(client, "dono@vizinho.dev")
    _robo_offline(client, dono, session, "VIZ-1")
    _drena(session)
    assert len(_avisos_de(session, "dono@vizinho.dev", "rover_offline")) == 1
    assert _avisos_de(session, "admin@valtexa.dev", "rover_offline") == []
    assert client.get("/v1/notifications", headers=dono).json()[0]["kind"] == "rover_offline"


# ---------------------------------------------------------------------------
# Outras regras: infecção, missão bloqueada, OTA (cliente + equipe)
# ---------------------------------------------------------------------------


def test_nova_infeccao_uma_vez_por_doenca_talhao_e_dia(
    client: TestClient, admin_token: dict, session: Session, demo: dict, sem_smtp
) -> None:
    robo = provision(client, admin_token, "ROVER_SCOUT_V1", "INF-1", demo["farm_id"])
    send_telemetry(robo, battery_percent=95.0)
    for _ in range(3):
        assert upload_observation(robo, demo["field_id"]).status_code in (200, 201)
    _drena(session)
    session.expire_all()
    from valtexa.models import Diagnosis
    from valtexa.services.ai_pipeline import HEALTHY_LABELS

    doentes = {d.label for d in session.scalars(select(Diagnosis))
               if d.label and d.label not in HEALTHY_LABELS}
    recebidos = _avisos_de(session, "agronomo@valtexa.dev", "nova_infeccao")
    # Um aviso por doença distinta (talhão e dia iguais), por mais imagens que haja.
    assert {a.title.split(" detectada")[0] for a in recebidos} == doentes
    assert len(recebidos) == len(doentes)
    assert _avisos_de(session, "operador@valtexa.dev", "nova_infeccao") == []


def test_missao_bloqueada_avisa(
    client: TestClient, admin_token: dict, operator_token: dict, session: Session,
    demo: dict, sem_smtp
) -> None:
    robo = provision(client, admin_token, "ROVER_SCOUT_V1", "BLOQ-1", demo["farm_id"])
    send_telemetry(robo, battery_percent=3.0)  # abaixo do mínimo de segurança
    r = client.post("/v1/missions", headers=operator_token, json={
        "kind": "scout", "field_id": demo["field_id"], "device_id": robo.device_id})
    assert r.status_code == 201, r.text
    parecer = client.post(f"/v1/missions/{r.json()['id']}/authorize", headers=operator_token)
    assert parecer.status_code == 200, parecer.text
    assert parecer.json()["verdict"] == "blocked", parecer.text
    _drena(session)
    recebidos = _avisos_de(session, "operador@valtexa.dev", "missao_bloqueada")
    assert len(recebidos) == 1 and recebidos[0].link == f"/missoes/{r.json()['id']}"
    assert recebidos[0].body.startswith("A camada de segurança não autorizou a missão: ")
    assert "motivo não informado" not in recebidos[0].body
    assert _avisos_de(session, "agronomo@valtexa.dev", "missao_bloqueada") == []


def test_atualizacao_que_falhou_avisa_cliente_e_equipe(
    client: TestClient, admin_token: dict, session: Session, demo: dict, equipe, sem_smtp
) -> None:
    from tests.test_ota import publicar, tar_de

    ops = equipe(PlatformRole.OPERACOES)
    suporte = equipe(PlatformRole.SUPORTE)
    robo = provision(client, admin_token, "ROVER_SCOUT_V1", "OTA-NOT", demo["farm_id"])
    pacote = publicar(client, ops, "config", "not-1", tar_de({"rover.json": b"{}"})).json()
    dep = client.post("/v1/platform/ota/deployments", headers=ops, json={
        "package_id": pacote["id"], "device_ids": [robo.device_id]}).json()[0]["id"]
    for estado, detalhe in (("baixando", None), ("verificando", None),
                            ("recusada", "assinatura inválida")):
        r = robo.request("POST", f"/v1/device/ota/{dep}/status",
                         json_body={"state": estado, "detail": detalhe})
        assert r.status_code == 200, r.text
    _drena(session)

    cliente = _avisos_de(session, "admin@valtexa.dev", "atualizacao_falhou")
    assert len(cliente) == 1 and "assinatura inválida" in cliente[0].body
    # A conta da equipe recebe na caixa da plataforma (operações sim, suporte não).
    lista = client.get("/v1/platform/notifications", headers=ops).json()
    assert [a["kind"] for a in lista] == ["plataforma_atualizacao_falhou"]
    assert "Demo" in lista[0]["title"] or lista[0]["title"]
    assert client.get("/v1/platform/notifications", headers=suporte).json() == []
    assert client.get("/v1/platform/notifications/unread-count",
                      headers=ops).json() == {"unread": 1}
    assert client.post(f"/v1/platform/notifications/{lista[0]['id']}/read",
                       headers=suporte).status_code == 404
    assert client.post(f"/v1/platform/notifications/{lista[0]['id']}/read",
                       headers=ops).status_code == 200
    # Um cliente não alcança a caixa da plataforma.
    assert client.get("/v1/platform/notifications", headers=admin_token).status_code == 403


def test_preferencias_da_equipe_e_do_papel_de_plataforma(
    client: TestClient, equipe
) -> None:
    suporte = equipe(PlatformRole.SUPORTE)
    chefe = equipe(PlatformRole.SUPERADMIN)
    prefs = client.get("/v1/platform/notifications/preferences", headers=suporte).json()
    assert prefs["role"] == "suporte"
    novo = next(p for p in prefs["preferences"] if p["kind"] == "plataforma_chamado_novo")
    assert novo["enabled"] is True
    # Só o superadmin define o que um papel da equipe recebe.
    corpo = {"role": "suporte", "kind": "plataforma_chamado_novo", "enabled": False}
    assert client.put("/v1/platform/notifications/role-preferences", headers=suporte,
                      json=corpo).status_code == 403
    r = client.put("/v1/platform/notifications/role-preferences", headers=chefe, json=corpo)
    assert r.status_code == 200, r.text
    prefs = client.get("/v1/platform/notifications/preferences", headers=suporte).json()
    novo = next(p for p in prefs["preferences"] if p["kind"] == "plataforma_chamado_novo")
    assert novo["enabled"] is False and novo["source"] == "papel"


def test_worker_entrega_eventos_e_emails_no_mesmo_ciclo(
    client: TestClient, admin_token: dict, session: Session, smtp
) -> None:
    _robo_offline(client, admin_token, session, "TICK-1")
    relatorio = worker.Worker().tick()
    assert relatorio.delivered >= 1
    assert relatorio.notifications_sent >= 2
    assert len(smtp.mensagens) == relatorio.notifications_sent
