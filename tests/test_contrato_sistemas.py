"""Contrato entre os sistemas: tudo o que o Rover e a base chamam existe na plataforma.

Lê o código-fonte do Rover Runtime (``valtexa_rover``) e da base da fazenda
(``valtexa_base``), acha cada chamada ``request("MÉTODO", "/v1/device/...")`` e confere
que a plataforma tem a rota com esse método. Renomear uma rota de um lado e esquecer do
outro quebra aqui, não no campo. Também confere os cabeçalhos que os dois lados combinam
e que a base classifica toda rota do Rover numa prioridade conhecida.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

rover = pytest.importorskip("valtexa_rover")
base = pytest.importorskip("valtexa_base")

from valtexa.main import app  # noqa: E402

CHAMADA = re.compile(
    r"""request\(\s*["'](GET|POST|PUT|PATCH|DELETE)["']\s*,\s*f?["']"""
    r"""(/v1/device/(?:\{[^}]*\}|[^"'?{])*)""")
PARAMETRO = re.compile(r"\{[^}]*\}")
ACAO_DE_MISSAO = re.compile(r"""_report_mission\(\s*["'](\w+)["']""")
"""O Runtime monta ``/v1/device/missions/{id}/{acao}`` com a ação numa variável: cada ação
que ele informa vira uma chamada concreta do contrato."""


def _chamadas(pacote) -> set[tuple[str, str]]:
    raiz = Path(pacote.__file__).parent
    achadas = set()
    for arquivo in raiz.rglob("*.py"):
        if "vendor" in arquivo.parts:
            continue
        texto = arquivo.read_text(encoding="utf-8")
        for metodo, caminho in CHAMADA.findall(texto):
            caminho = PARAMETRO.sub("{p}", caminho).rstrip("/")
            if caminho == "/v1/device/missions/{p}/{p}":
                achadas |= {(metodo, f"/v1/device/missions/{{p}}/{acao}")
                            for acao in ACAO_DE_MISSAO.findall(texto)}
                continue
            achadas.add((metodo, caminho))
    return achadas


def _rotas() -> list[tuple[set[str], re.Pattern]]:
    """Do contrato publicado (OpenAPI): é o que a plataforma promete."""
    rotas = []
    for caminho, metodos in app.openapi()["paths"].items():
        if caminho.startswith("/v1/device"):
            rotas.append(({m.upper() for m in metodos},
                          re.compile("^" + PARAMETRO.sub("[^/]+", caminho) + "$")))
    return rotas


def _existe(metodo: str, caminho: str, rotas) -> bool:
    exemplo = caminho.replace("{p}", "x1")
    return any(metodo in ms and padrao.match(exemplo) for ms, padrao in rotas)


def test_toda_rota_que_o_rover_e_a_base_chamam_existe_na_plataforma() -> None:
    rotas = _rotas()
    chamadas = _chamadas(rover) | _chamadas(base)
    assert len(chamadas) >= 15, f"poucas chamadas achadas ({len(chamadas)}): o leitor quebrou?"
    faltando = sorted(f"{m} {c}" for m, c in chamadas if not _existe(m, c, rotas))
    assert faltando == [], f"o Rover/base chamam rotas que a plataforma não tem: {faltando}"


def test_rotas_essenciais_do_robo_estao_no_contrato() -> None:
    chamadas = _chamadas(rover)
    essenciais = {("GET", "/v1/device/commands"), ("GET", "/v1/device/teleop"),
                  ("POST", "/v1/device/video/{p}"), ("POST", "/v1/device/sync"),
                  ("POST", "/v1/device/commands/{p}/result"), ("GET", "/v1/device/models"),
                  ("POST", "/v1/device/missions/{p}/ack"),
                  ("POST", "/v1/device/missions/{p}/complete")}
    assert essenciais <= chamadas, sorted(essenciais - chamadas)


def test_cabecalhos_combinados_sao_os_mesmos_dos_dois_lados() -> None:
    from valtexa_rover.runtime import video as video_rover

    from valtexa.services import video_ao_vivo

    assert video_rover.CABECALHO == video_ao_vivo.CABECALHO == "X-Valtexa-Video"


def test_a_chave_do_radio_e_assinada_do_mesmo_jeito_nos_dois_lados() -> None:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
    from valtexa_rover.enlace import cripto

    from valtexa.services import chave_de_enlace

    assert cripto.ALGORITMO_PUBLICA == chave_de_enlace.ALGORITMO_PUBLICA
    k = cripto.ChaveDeEnlace(X25519PrivateKey.generate())
    privada = Ed25519PrivateKey.generate()
    doc = cripto.publica_assinada(k, "rv-1", privada.private_bytes_raw().hex())
    publica = privada.public_key().public_bytes_raw().hex()
    chave_de_enlace.confere(doc, publica)  # o que o robô assina a plataforma aceita


def test_a_base_classifica_toda_rota_do_rover() -> None:
    """Toda rota que o Rover usa cai numa prioridade do enlace; vídeo e teleop em slot."""
    from valtexa_rover.enlace.no import P1, P4
    from valtexa_rover.enlace.rpc import Classificador

    classifica = Classificador()
    for metodo, caminho in _chamadas(rover):
        prio, slot = classifica(metodo, caminho.replace("{p}", "x1"), b"{}")
        assert 0 <= prio <= P4, (metodo, caminho)
        if caminho == "/v1/device/teleop":
            assert prio == P1 and slot == "teleop"
        if caminho.startswith("/v1/device/video/"):
            assert prio > P1 and slot and slot.startswith("video:")


def test_mapa_de_cobertura_da_base_a_plataforma_ao_rover() -> None:
    """O relatório que a análise da base gera é aceito pela plataforma, e o que a plataforma
    põe na missão o Rover lê com as mesmas zonas mortas (perfil SIMULADO de cafezal)."""
    from datetime import UTC, datetime

    from valtexa_base import levantamento as lv
    from valtexa_base.plataforma import CAMPOS_DA_COBERTURA
    from valtexa_rover.enlace import cafezal
    from valtexa_rover.enlace.levantamento import MapaDeCobertura

    from valtexa.models import Field
    from valtexa.services import cobertura_talhao

    t = cafezal.Talhao()
    rel = lv.analisa(cafezal.amostras_de_levantamento(t, ruas=range(0, 68, 4)),
                     base_pos=t.base_latlon)
    enviado = {k: rel[k] for k in CAMPOS_DA_COBERTURA if k in rel}
    guardado = cobertura_talhao.valida(enviado)
    assert guardado["contagem"] == rel["contagem"] and guardado["zonas_mortas"]
    talhao = Field(cobertura=guardado, cobertura_em=datetime.now(UTC))
    na_missao = cobertura_talhao.para_missao(talhao)
    mapa = MapaDeCobertura(na_missao)
    assert [z.id for z in mapa.zonas] == [z["id"] for z in rel["zonas_mortas"]]
    z = rel["zonas_mortas"][0]
    assert mapa.zona(*z["centro"]) is not None  # o centro da zona morta cai nela no Rover
