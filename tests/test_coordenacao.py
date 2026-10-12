"""Limite de taxa e travas compartilhados entre réplicas (Parte 9, seção 51).

A mesma bateria roda em três implementações: memória (desenvolvimento), ``fakeredis``
(Redis em memória, com Lua) e um ``redis-server`` de verdade quando o binário existe
na máquina (pulado se não houver). "Duas réplicas" = duas instâncias de
:class:`CoordenacaoRedis` com clientes próprios apontando para o mesmo servidor.
"""

from __future__ import annotations

import shutil
import socket
import subprocess
import threading
import time
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from tests.helpers import provision
from valtexa import worker
from valtexa.api.routers import edge_sync as rota_edge
from valtexa.config import settings
from valtexa.services import coordenacao

fakeredis = pytest.importorskip("fakeredis")
redis = pytest.importorskip("redis")


@pytest.fixture(scope="module")
def redis_real() -> Iterator[str]:
    binario = shutil.which("redis-server")
    if not binario:
        pytest.skip("redis-server não instalado nesta máquina")
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        porta = s.getsockname()[1]
    processo = subprocess.Popen(
        [binario, "--port", str(porta), "--save", "", "--appendonly", "no"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    url = f"redis://127.0.0.1:{porta}/0"
    cliente = redis.Redis.from_url(url)
    for _ in range(100):
        try:
            cliente.ping()
            break
        except redis.ConnectionError:
            time.sleep(0.05)
    yield url
    processo.terminate()
    processo.wait(5)


@pytest.fixture(params=["memoria", "fakeredis", "redis"])
def replicas(request) -> tuple[coordenacao.Coordenacao, coordenacao.Coordenacao]:
    """Duas "réplicas" do mesmo estado compartilhado."""
    if request.param == "memoria":
        uma = coordenacao.CoordenacaoEmMemoria()
        return uma, uma  # em memória só há uma réplica possível
    if request.param == "fakeredis":
        servidor = fakeredis.FakeServer()
        return (coordenacao.CoordenacaoRedis(fakeredis.FakeRedis(server=servidor)),
                coordenacao.CoordenacaoRedis(fakeredis.FakeRedis(server=servidor)))
    url = request.getfixturevalue("redis_real")
    a = coordenacao.CoordenacaoRedis(redis.Redis.from_url(url), prefixo="teste:")
    b = coordenacao.CoordenacaoRedis(redis.Redis.from_url(url), prefixo="teste:")
    a.limpar()
    return a, b


class TestBalde:
    def test_limite_vale_para_a_soma_das_replicas(self, replicas) -> None:
        a, b = replicas
        respostas = [(a if i % 2 else b).consumir("robo:R1", 10) for i in range(14)]
        assert respostas[:10] == [None] * 10
        assert all(espera is not None and espera > 0 for espera in respostas[10:])

    def test_balde_por_chave(self, replicas) -> None:
        a, b = replicas
        for _ in range(10):
            a.consumir("robo:R1", 10)
        assert a.consumir("robo:R1", 10) is not None
        assert b.consumir("robo:R2", 10) is None

    def test_balde_recarrega_com_o_tempo(self) -> None:
        agora = [0.0]
        mem = coordenacao.CoordenacaoEmMemoria(relogio=lambda: agora[0])
        for _ in range(60):
            assert mem.consumir("r", 60) is None
        assert mem.consumir("r", 60) == pytest.approx(1.0)
        agora[0] = 1.0  # 60/min = 1 ficha por segundo
        assert mem.consumir("r", 60) is None

    def test_concorrencia_nao_deixa_passar_alem_do_limite(self, replicas) -> None:
        a, b = replicas
        passaram = []
        trava = threading.Lock()

        def bate(c: coordenacao.Coordenacao) -> None:
            for _ in range(25):
                if c.consumir("robo:R9", 50) is None:
                    with trava:
                        passaram.append(1)

        threads = [threading.Thread(target=bate, args=(c,)) for c in (a, b, a, b)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        # 100 tentativas em < 1 s, balde de 50: passa 50 (mais a recarga do intervalo).
        assert 50 <= len(passaram) <= 52


class TestTrava:
    def test_so_uma_replica_pega(self, replicas) -> None:
        a, b = replicas
        with a.trava("upload:U1", 30) as primeira:
            with b.trava("upload:U1", 30) as segunda:
                assert primeira is True and segunda is False
            with b.trava("upload:U2", 30) as outra:
                assert outra is True
        with b.trava("upload:U1", 30) as depois:
            assert depois is True

    def test_trava_vencida_e_de_quem_chegar(self, replicas) -> None:
        a, b = replicas
        if a is b:
            pytest.skip("o vencimento em memória é testado com relógio falso abaixo")
        trava_a = a.trava("x", 0.05)
        assert trava_a.__enter__() is True
        time.sleep(0.12)  # o processo de A "travou" além do ttl
        with b.trava("x", 30) as segunda:
            assert segunda is True
            trava_a.__exit__(None, None, None)  # A acorda e sai
            # A saída de A não pode soltar a trava que agora é de B.
            with a.trava("x", 30) as terceira:
                assert terceira is False

    def test_uma_vez_por_intervalo_no_cluster(self, replicas) -> None:
        a, b = replicas
        assert a.uma_vez("worker:alertas", 30, agora=0.0) is True
        assert b.uma_vez("worker:alertas", 30, agora=1.0) is False
        assert b.uma_vez("worker:retencao", 30, agora=1.0) is True


def test_trava_em_memoria_vence_pelo_relogio() -> None:
    agora = [0.0]
    mem = coordenacao.CoordenacaoEmMemoria(relogio=lambda: agora[0])
    with mem.trava("x", 10) as a:
        agora[0] = 11.0
        with mem.trava("x", 10) as b:
            assert a and b


def test_dois_workers_nao_rodam_a_mesma_tarefa(monkeypatch) -> None:
    """Dois processos de worker (deploy sobreposto): a retenção roda uma vez só."""
    servidor = fakeredis.FakeServer()
    compartilhado = coordenacao.CoordenacaoRedis(fakeredis.FakeRedis(server=servidor))
    monkeypatch.setattr(coordenacao, "coordenacao", compartilhado)
    w1, w2 = worker.Worker(), worker.Worker()
    assert w1.due("retention", worker.RETENTION_EVERY, 0.0) is True
    assert w2.due("retention", worker.RETENTION_EVERY, 0.0) is False
    # Cada um volta a tentar no seu próximo ciclo, não a cada tick.
    assert w2.due("retention", worker.RETENTION_EVERY, 1.0) is False


def test_limite_do_robo_compartilhado_pela_api(
    client: TestClient, admin_token, demo, monkeypatch
) -> None:
    """O 429 do robô vem do Redis: o balde gasto numa réplica vale na outra."""
    servidor = fakeredis.FakeServer()
    replica_a = coordenacao.CoordenacaoRedis(fakeredis.FakeRedis(server=servidor))
    replica_b = coordenacao.CoordenacaoRedis(fakeredis.FakeRedis(server=servidor))
    monkeypatch.setattr(rota_edge, "settings", settings.model_copy(
        update={"device_rate_per_minute": 10}))
    robo = provision(client, admin_token, "ROVER_SCOUT_V1", "RDS-1", demo["farm_id"])
    codigos = []
    for i in range(12):
        monkeypatch.setattr(coordenacao, "coordenacao", replica_a if i % 2 else replica_b)
        codigos.append(robo.request("GET", "/v1/device/uploads/nao-existe").status_code)
    assert codigos[:10] == [404] * 10 and codigos[10:] == [429, 429]


def test_complete_simultaneo_e_recusado(client: TestClient, admin_token, demo,
                                        monkeypatch) -> None:
    """Enquanto uma réplica monta o arquivo, o ``complete`` repetido noutra é 409."""
    import hashlib

    from tests.test_edge_sync import DADOS, abrir, mandar_chunk
    from valtexa.models import EdgeUpload

    robo = provision(client, admin_token, "ROVER_SCOUT_V1", "RDS-2", demo["farm_id"])
    abrir(robo, DADOS)
    for i in range(5):
        mandar_chunk(robo, "up-1", i, DADOS[i * 4096:(i + 1) * 4096])
    from valtexa import db
    with db.SessionLocal() as s:
        pk = s.query(EdgeUpload).filter_by(upload_id="up-1").one().id
    corpo = {"sha256": hashlib.sha256(DADOS).hexdigest()}
    with coordenacao.coordenacao.trava(f"upload:{pk}", 30) as outra_replica:
        assert outra_replica
        r = robo.request("POST", "/v1/device/uploads/up-1/complete", json_body=corpo)
        assert r.status_code == 409 and r.headers["retry-after"] == "2"
    r = robo.request("POST", "/v1/device/uploads/up-1/complete", json_body=corpo)
    assert r.status_code == 200 and r.json()["status"] == "complete"


def test_sem_redis_url_usa_memoria_e_com_redis_url_usa_redis(monkeypatch) -> None:
    monkeypatch.setattr(coordenacao, "settings", settings.model_copy(update={"redis_url": None}))
    assert isinstance(coordenacao.construir(), coordenacao.CoordenacaoEmMemoria)
    monkeypatch.setattr(coordenacao, "settings", settings.model_copy(
        update={"redis_url": "redis://127.0.0.1:1/0"}))
    assert isinstance(coordenacao.construir(), coordenacao.CoordenacaoRedis)
