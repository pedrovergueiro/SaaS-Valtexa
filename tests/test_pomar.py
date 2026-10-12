"""A demonstração do bananal e do pomar: o que ela afirma sobre as plantas."""

from __future__ import annotations

import pytest

from simulator.pomar import (
    BANANAL,
    HEALTHY,
    POMAR,
    Fotos,
    Origem,
    contorno,
    posicao_planta,
    verdade,
)
from valtexa.services import geo


@pytest.mark.parametrize("talhao", [BANANAL, POMAR], ids=["bananal", "pomar"])
def test_a_reboleira_cresce_e_aparece_outra_doenca(talhao) -> None:
    antes, depois = verdade(talhao, 0), verdade(talhao, 1)
    doentes = [sum(rotulo != HEALTHY for rotulo in fase.values()) for fase in (antes, depois)]

    assert doentes == [5, 12]
    # Quem estava doente continua; a reboleira não salta plantas.
    assert all(depois[p] != HEALTHY for p, rotulo in antes.items() if rotulo != HEALTHY)
    assert list(depois.values()).count(talhao.secundaria) == 1
    assert talhao.secundaria not in antes.values()


@pytest.mark.parametrize("talhao", [BANANAL, POMAR], ids=["bananal", "pomar"])
def test_as_plantas_cabem_no_talhao(talhao) -> None:
    origem = Origem(lon=-45.863, lat=-21.9068)
    anel = contorno(talhao, origem)
    for planta in range(talhao.plantas_por_rua):
        for rua in range(talhao.ruas):
            ponto = origem.ponto(posicao_planta(talhao, planta), rua * talhao.entre_ruas_m)
            assert geo.contains_point(anel, ponto[0], ponto[1])


def test_faltando_foto_falha_antes_de_subir_a_plataforma(tmp_path) -> None:
    (tmp_path / "banana" / "Sigatoka").mkdir(parents=True)
    (tmp_path / "banana" / "Sigatoka" / "a.jpg").write_bytes(b"\xff\xd8\xff\xd9")

    with pytest.raises(SystemExit, match="banana/Healthy"):
        Fotos(tmp_path).conferir([BANANAL])


def test_sem_pasta_as_fotos_sao_desenhadas_com_a_etiqueta() -> None:
    imagem, nome = Fotos(None).quadro(BANANAL, "Sigatoka", "semente")
    assert nome.endswith(".png") and b"VTXSIM:Sigatoka" in imagem
