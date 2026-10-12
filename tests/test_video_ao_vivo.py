"""Vídeo ao vivo: a estação pede, o robô fica sabendo pela consulta de comandos, manda o
quadro assinado e a estação vê o último — com prazo, auditoria e isolamento."""

from __future__ import annotations

import io
import json

import pytest
from PIL import Image
from sqlalchemy import select

from tests.helpers import provision
from valtexa.models import AuditEntry
from valtexa.services import coordenacao as coord
from valtexa.services import video_ao_vivo


def _jpeg(cor=(20, 160, 40)) -> bytes:
    b = io.BytesIO()
    Image.new("RGB", (64, 48), cor).save(b, "JPEG")
    return b.getvalue()


@pytest.fixture(autouse=True)
def _limpa():
    coord.coordenacao.limpar()
    yield
    coord.coordenacao.limpar()


@pytest.fixture
def rover(client, admin_token, demo):
    return provision(client, admin_token, "ROVER_SCOUT_V1", "RV-VIDEO", demo["farm_id"])


def _url(rover, resto=""):
    return f"/v1/platform/rovers/{rover.device_id}{resto}"


def _manda(rover, camera, jpeg, seq=1):
    return rover.request("POST", f"/v1/device/video/{camera}", content=jpeg,
                         headers={"Content-Type": "image/jpeg",
                                  "X-Capturado-Em": "2026-10-10T12:00:00+00:00",
                                  "X-Seq": str(seq)})


def test_ida_e_volta_do_quadro(client, platform_token, rover, session) -> None:
    assert client.get(_url(rover, "/video/cam-0"), headers=platform_token).status_code == 204
    r = rover.request("GET", "/v1/device/commands")
    assert "x-valtexa-video" not in {k.lower() for k in r.headers}  # ninguém assiste

    p = client.post(_url(rover, "/video"), headers=platform_token,
                    json={"cameras": ["cam-0", "cam-1"], "fps": 4, "lado": 640})
    assert p.status_code == 200 and p.json()["cameras"] == ["cam-0", "cam-1"]
    cab = rover.request("GET", "/v1/device/commands").headers
    pedido = json.loads({k.lower(): v for k, v in cab.items()}["x-valtexa-video"])
    assert pedido["fps"] == 4 and pedido["lado"] == 640 and "por" not in pedido

    jpeg = _jpeg()
    r = _manda(rover, "cam-0", jpeg, seq=7)
    assert r.status_code == 200 and r.json()["cameras"] == ["cam-0", "cam-1"]
    q = client.get(_url(rover, "/video/cam-0"), headers=platform_token)
    assert q.status_code == 200 and q.content == jpeg
    assert q.headers["content-type"] == "image/jpeg" and q.headers["x-seq"] == "7"
    assert q.headers["x-capturado-em"].startswith("2026-10-10T12:00:00")
    assert q.headers["cache-control"] == "no-store"

    # renovar não audita de novo; começar a assistir audita uma vez
    client.post(_url(rover, "/video"), headers=platform_token,
                json={"cameras": ["cam-0"], "fps": 4, "lado": 640})
    trilha = session.scalars(select(AuditEntry).where(
        AuditEntry.action == "rover.video.assistir")).all()
    assert len(trilha) == 1 and trilha[0].subject_id == rover.device_id


def test_quadro_invalido_ou_sem_pedido(client, platform_token, rover) -> None:
    assert _manda(rover, "cam-0", _jpeg()).status_code == 404  # ninguém assiste
    client.post(_url(rover, "/video"), headers=platform_token,
                json={"cameras": ["cam-0"], "fps": 4, "lado": 640})
    assert _manda(rover, "cam-9", _jpeg()).status_code == 404  # câmera não pedida
    assert _manda(rover, "cam-0", b"GIF89a....").status_code == 422
    assert _manda(rover, "cam-0", b"\xff\xd8" + b"x" * 500_000).status_code in (413, 422)
    assert client.delete(_url(rover, "/video"), headers=platform_token).status_code == 204
    assert _manda(rover, "cam-0", _jpeg()).status_code == 404  # desligou: o robô para


def test_limites_e_permissao(client, platform_token, admin_token, rover) -> None:
    for corpo in ({"cameras": [], "fps": 4}, {"cameras": ["a"], "fps": 50},
                  {"cameras": ["a"], "fps": 4, "lado": 9000}):
        assert client.post(_url(rover, "/video"), headers=platform_token,
                           json=corpo).status_code == 422
    assert client.post(_url(rover, "/video"), headers=admin_token,
                       json={"cameras": ["cam-0"]}).status_code in (401, 403)


def test_pedido_vence_sozinho(monkeypatch, rover) -> None:
    relogio = [1000.0]
    memoria = coord.CoordenacaoEmMemoria(relogio=lambda: relogio[0])
    monkeypatch.setattr(video_ao_vivo, "coordenacao", memoria)
    video_ao_vivo.pedir(rover.device_id, ["cam-0"], 4, 640, user_id="u")
    assert video_ao_vivo.cabecalho(rover.device_id)
    relogio[0] += video_ao_vivo.TTL_PEDIDO_S + 0.1  # a tela fechou e não renovou
    assert video_ao_vivo.cabecalho(rover.device_id) is None


def test_redis_guarda_e_le_com_prazo() -> None:
    fakeredis = pytest.importorskip("fakeredis")
    r = coord.CoordenacaoRedis(fakeredis.FakeRedis())
    r.guarda("video:x", b"\xff\xd8abc", 5)
    assert r.le("video:x") == b"\xff\xd8abc"
    r.apaga("video:x")
    assert r.le("video:x") is None
