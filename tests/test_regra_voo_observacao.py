"""Regra do voo de observação do drone: o desenho funciona e está DESLIGADO (aguarda o Pedro).

Prova as duas coisas: (1) o que a regra checaria — cada verificação falha pelo motivo certo e,
com tudo declarado, ela liberaria; (2) ninguém a usa — o Safety Engine não a importa e continua
bloqueando o voo de observação do drone (``scout`` exige Rover)."""

from __future__ import annotations

import ast
from datetime import UTC, datetime
from pathlib import Path

from tests.test_enxame import _ret
from tests.test_planejamento import frota  # noqa: F401
from valtexa.models import Mission, MissionKind, MissionState, RtkFix, SafetyVerdict, utcnow
from valtexa.models.operations import TelemetrySample
from valtexa.services import regra_voo_observacao as regra
from valtexa.services import safety_engine

RAIZ = Path(__file__).resolve().parents[1] / "valtexa"
MEIO_DIA = datetime(2026, 10, 19, 15, 0, tzinfo=UTC)  # 12 h em Brasília


def _voo(session, demo, drone_id: str, **plano) -> Mission:
    m = Mission(tenant_id=demo["tenant_id"], farm_id=demo["farm_id"], field_id=demo["field_id"],
                device_id=drone_id, kind=MissionKind.SCOUT, state=MissionState.DRAFT,
                target_polygon=_ret(0, 0), plan=plano)
    session.add(m)
    session.commit()
    return m


def _codigos(rel) -> dict[str, bool]:
    return {c.code: c.passed for c in rel.checks}


def test_desligada_e_ninguem_chama() -> None:
    assert regra.LIGADA is False
    for caminho in RAIZ.rglob("*.py"):
        if caminho.name == "regra_voo_observacao.py":
            continue
        for no in ast.walk(ast.parse(caminho.read_text(encoding="utf-8"))):
            if isinstance(no, (ast.Import, ast.ImportFrom)):
                nomes = [a.name for a in no.names] + [getattr(no, "module", "") or ""]
                assert not any("regra_voo_observacao" in n for n in nomes), caminho


def test_o_que_a_regra_checaria(session, demo, frota) -> None:  # noqa: F811
    drone = frota[2]
    m = _voo(session, demo, drone.device_id)
    rel = regra.verificar(session, m, agora=MEIO_DIA)
    c = _codigos(rel)
    assert rel.verdict is SafetyVerdict.BLOCKED
    assert c[regra.VOO_DISPOSITIVO] and c[regra.VOO_SEM_APLICACAO] and c[regra.VOO_JANELA]
    assert not c[regra.VOO_VENTO]  # sem leitura de vento
    assert not c[regra.VOO_ALTURA] and not c[regra.VOO_OPERADOR]
    # tudo declarado: a regra liberaria (se estivesse ligada)
    session.add(TelemetrySample(tenant_id=demo["tenant_id"], device_id=drone.device_id,
                                sequence_number=999, recorded_at=utcnow(),
                                received_at=utcnow(), rtk_fix=RtkFix.FLOAT))
    m.plan = {"altura_m": 60, "operador_vlos": "piloto EXEMPLO (fictício)"}
    session.commit()
    rel = regra.verificar(session, m, agora=MEIO_DIA, vento_ms=3.0)
    assert rel.verdict is SafetyVerdict.SAFE_TO_EXECUTE, rel.blocked_reason
    # e cada limite segura
    noite = datetime(2026, 10, 19, 23, 30, tzinfo=UTC)
    assert not _codigos(regra.verificar(session, m, agora=noite, vento_ms=3.0))[regra.VOO_JANELA]
    assert not _codigos(regra.verificar(session, m, agora=MEIO_DIA,
                                        vento_ms=30.0))[regra.VOO_VENTO]
    m.plan = {"altura_m": 300, "operador_vlos": "x"}
    m.product_id = demo["product_id"]
    session.commit()
    c = _codigos(regra.verificar(session, m, agora=MEIO_DIA, vento_ms=3.0))
    assert not c[regra.VOO_ALTURA] and not c[regra.VOO_SEM_APLICACAO]


def test_o_safety_engine_continua_bloqueando_o_voo(session, demo, frota) -> None:  # noqa: F811
    m = _voo(session, demo, frota[2].device_id, altura_m=60, operador_vlos="x")
    rel = safety_engine.check_mission(session, m, wind_ms=3.0, now=MEIO_DIA)
    assert rel.verdict is SafetyVerdict.BLOCKED
    assert {c.code: c.passed for c in rel.checks}[safety_engine.DEVICE_KIND] is False
