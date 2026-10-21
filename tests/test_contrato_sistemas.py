"""Contrato entre os sistemas: tudo o que o Rover chama existe na plataforma.

Lê o código-fonte do Rover Runtime (``valtexa_rover``), acha cada chamada
``request("MÉTODO", "/v1/device/...")`` e confere que a plataforma tem a rota com esse
método. Renomear uma rota de um lado e esquecer do outro quebra aqui, não no campo. Também
confere os cabeçalhos que os dois lados combinam.

Até 20/10/2026 conferia também a base da fazenda (``valtexa_base``) e o rádio; os dois foram
arquivados (cada Rover tem a própria Starlink) — a versão anterior deste arquivo está em
``archive/legacy/radio-fazenda/tests/test_contrato_sistemas.ANTES.py``.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

rover = pytest.importorskip("valtexa_rover")

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


def test_toda_rota_que_o_rover_chama_existe_na_plataforma() -> None:
    rotas = _rotas()
    chamadas = _chamadas(rover)
    assert len(chamadas) >= 15, f"poucas chamadas achadas ({len(chamadas)}): o leitor quebrou?"
    faltando = sorted(f"{m} {c}" for m, c in chamadas if not _existe(m, c, rotas))
    assert faltando == [], f"o Rover chama rotas que a plataforma não tem: {faltando}"


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
