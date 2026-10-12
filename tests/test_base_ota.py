"""OTA da base da fazenda: o mesmo OTA do Rover (assinado, lado a lado, teste de boot),
para o pacote ``valtexa_base`` — publicado e destinado pela plataforma."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from tests.helpers import provision
from tests.test_ota import _destinar, _estado, publicar, tar_de
from valtexa.models import PlatformRole
from valtexa.security import signing

pytest.importorskip("valtexa_base")

from valtexa_base.plataforma import RelatorioParaPlataforma, ota_da_base
from valtexa_rover import launcher
from valtexa_rover.hal.simulated import FlakyNetwork
from valtexa_rover.runtime.client import DeviceIdentity

from tests.test_rover_integracao import ponte


@pytest.fixture
def ops(equipe) -> dict:
    return equipe(PlatformRole.OPERACOES)


@pytest.fixture
def base(client, admin_token, demo, tmp_path: Path):
    ds = provision(client, admin_token, "FARM_BASE_V1", "BASE-OTA", demo["farm_id"])
    caminho = tmp_path / "identity.json"
    DeviceIdentity(ds.device_id, ds.key_id, ds.private_key, signing.platform_public_key(),
                   signing.ota_public_key()).save(caminho)
    rel = RelatorioParaPlataforma(caminho, "http://teste", lambda: {}, dados=tmp_path,
                                  rede=FlakyNetwork(ponte(client)))
    ota = ota_da_base(tmp_path, rel)
    ota.chunk_size = 512
    return ds, ota, tmp_path


def test_base_atualiza_o_proprio_pacote_e_confirma_no_boot(client, ops, base,
                                                            session: Session) -> None:
    ds, ota, dados = base
    pacote = publicar(client, ops, "runtime", "9.9.9", tar_de({
        "valtexa_base/__init__.py": b'__version__ = "9.9.9"\n',
        "valtexa_base/extra.py": b"VALOR = 1\n" * 200}))
    assert pacote.status_code == 201, pacote.text
    dep = _destinar(client, ops, pacote.json()["id"], ds.device_id)

    rel = ota.step()
    assert rel.applied == [dep], rel
    assert ota.current()["runtime"]["state"] == "teste"
    # O lançador põe a versão nova no PYTHONPATH do próximo boot.
    _revertidos, ambiente = launcher.prepare(dados / "ota-base")
    assert str(Path(ota.current()["runtime"]["path"])) in ambiente["PYTHONPATH"]
    assert ota.confirm_boot() == ["runtime"]  # a base subiu inteira na versão nova
    assert _estado(session, dep).state == "aplicada"


def test_pacote_errado_nao_entra_na_base(client, ops, base, session: Session) -> None:
    ds, ota, _dados = base
    do_rover = publicar(client, ops, "runtime", "0.9.0", tar_de({
        "valtexa_rover/__init__.py": b'RUNTIME_VERSION = "0.9.0"\n'})).json()
    config = publicar(client, ops, "config", "c-base", tar_de({"rover.json": b"{}"})).json()
    dep_rover = _destinar(client, ops, do_rover["id"], ds.device_id)
    dep_config = _destinar(client, ops, config["id"], ds.device_id)
    rel = ota.step()
    assert dep_rover in (rel.failed or []) and dep_config in (rel.rejected or [])
    assert _estado(session, dep_rover).state == "falhou"  # sem valtexa_base/__init__.py
    assert _estado(session, dep_config).state == "recusada"  # a base só aceita runtime
    assert ota.current().get("runtime") is None
