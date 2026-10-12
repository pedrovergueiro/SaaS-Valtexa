"""FASE 0 inteira, automática, contra a plataforma: ``python -m simulator --fase0``.

O Rover Runtime de verdade (pacote ``rover/``) com a bancada **SIMULADA** de ensaios
(``valtexa_rover.ensaios.simulado``: 8 OAK-D, ZED-F9P, MTi, Jetson, navegação). A equipe
de Operações manda cada ensaio pelo centro de comando (comando **assinado** ``ensaio``),
o robô roda numa thread e devolve o laudo com as amostras brutas, a plataforma
**recalcula o veredito** e o portão da FASE 0 é conferido. No fim, o laudo em Markdown.

O ensaio de rede mede de verdade a ida e volta até a API (é o único número real aqui);
o resto é simulação e o laudo diz isso. Sem BMS/MCU, energia sai "aguarda protocolo".

Usado pelo teste ``tests/test_simulador_fase0.py`` (contra o ``TestClient``) e pelo
``python -m simulator --fase0`` (contra o servidor que o simulador sobe).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from valtexa_rover.ensaios import fontes_do_runtime
from valtexa_rover.ensaios.fase0 import etapas_fase0, laudo_markdown
from valtexa_rover.ensaios.simulado import RelogioDeBancada, bancada
from valtexa_rover.hal.simulated import FlakyNetwork
from valtexa_rover.runtime.comandos import CommandExecutor
from valtexa_rover.runtime.core import RoverCore
from valtexa_rover.runtime.model_manager import FolderArtifactSource

from simulator.ponta_a_ponta import Resultado, _check, _equipe, _login, provisionar_rover


def executar(http, transporte: Callable, sessao_factory, pasta: Path, *,
             falhas: dict | None = None, log: Callable[[str], None] = lambda _m: None
             ) -> Resultado:
    res = Resultado()
    eq = _equipe(sessao_factory)
    comercial, ops = _login(http, eq["comercial"]), _login(http, eq["ops"])
    sufixo = datetime.now(UTC).strftime("%H%M%S%f")
    cad = _check(http.post("/v1/admin/tenants", headers=comercial, json={
        "tenant": {"name": "Bancada FASE 0", "slug": f"bancada-fase0-{sufixo}",
                   "contact_name": "Engenharia", "email": "engenharia@exemplo.dev"},
        "farm": {"name": "Bancada", "center_lat": -21.25, "center_lon": -45.0},
    }), 201)
    tenant_id, farm_id = cad["tenant"]["id"], cad["farm_id"]
    sessao = _check(http.post("/v1/platform/support-sessions", headers=_login(
        http, eq["suporte"]), json={"tenant_id": tenant_id, "reason": "Bancada FASE 0"}), 201)
    tok = {"Authorization": f"Bearer {sessao['access_token']}"}
    _check(http.post(f"/v1/platform/support-sessions/{sessao['session']['id']}/mode",
                     headers=tok, json={"mode": "assistido", "reason": "Provisionar o rover"}))
    serial = f"BANCADA-{sufixo}"
    token = _check(http.post("/v1/provisioning-tokens", headers=tok, json={
        "device_model_code": "ROVER_SCOUT_V1", "serial_number": serial, "farm_id": farm_id}),
        201)["token"]
    identidade = provisionar_rover(transporte, token, serial)
    rover_id = identidade.device_id
    res.dados["rover_id"] = rover_id
    res.registra("1 provisionar o rover", bool(rover_id), f"device {rover_id}")

    relogio = RelogioDeBancada()
    hardware, fontes = bancada(pasta / "bancada", relogio, falhas=falhas)
    hardware.network = transporte if hasattr(transporte, "send") else FlakyNetwork(transporte)
    core = RoverCore(hardware, pasta / "dados", identidade, clock=relogio,
                     artifact_source=FolderArtifactSource(pasta / "artefatos"))
    core.boot()
    executor = CommandExecutor(core, pasta / "rover.json")
    # Calor e energia da bancada; a rede é a de verdade, pelo canal assinado.
    executor.ensaios._fontes = lambda: {**fontes, "rede": fontes_do_runtime(core)["rede"]}

    linhas: list[dict[str, Any]] = []
    for i, etapa in enumerate(etapas_fase0(), start=2):
        if etapa.preparo is not None:
            etapa.preparo(hardware, relogio)
        pedido = _check(http.post(f"/v1/platform/rovers/{rover_id}/ensaios", headers=ops,
                                  json={"ensaio": etapa.ensaio, "params": etapa.params}), 201)
        executor.poll()  # o robô busca, confere a assinatura e começa
        if not executor.ensaios.aguardar(600):
            raise AssertionError(f"{etapa.rotulo}: o ensaio não terminou")
        executor.poll()  # laudo que ficou pendente (se a rede caiu no fim) vai agora
        historico = _check(http.get(f"/v1/platform/rovers/{rover_id}/ensaios", headers=ops))
        linha = next((r for r in historico["resultados"] if r["command_id"] == pedido["id"]),
                     None)
        if linha is None:
            raise AssertionError(f"{etapa.rotulo}: a plataforma não registrou o resultado")
        linha["rotulo"] = etapa.rotulo
        linhas.append(linha)
        esperado = "nao_avaliado" if etapa.ensaio == "energia" else "aprovado"
        log(f"  {linha['status']:<12} {etapa.rotulo}")
        res.registra(f"{i} {etapa.rotulo}", linha["status"] == esperado or bool(falhas),
                     f"servidor: {linha['status']}" + (" (divergente do robô)"
                                                       if linha["divergente"] else ""))
    portoes = _check(http.get(f"/v1/platform/rovers/{rover_id}/portoes", headers=ops,
                              params={"aceitar_simulado": "true"}))
    fase0 = next(p for p in portoes if p["fase"] == 0)
    real = next(p for p in _check(http.get(f"/v1/platform/rovers/{rover_id}/portoes",
                                           headers=ops)) if p["fase"] == 0)
    res.dados.update({"portao_simulado": fase0, "portao_real": real, "linhas": linhas})
    n = len(etapas_fase0()) + 2
    res.registra(f"{n} portão da FASE 0 (simulado)", fase0["aprovado"] or bool(falhas),
                 "aprovado" if fase0["aprovado"] else f"faltam: {', '.join(fase0['faltam'])}")
    res.registra(f"{n + 1} portão real continua fechado", real["aprovado"] is False,
                 "resultado simulado não abre o portão de verdade")
    nota = (f"Rover `{rover_id}` · veredito **calculado na plataforma** a partir das amostras "
            f"brutas · portão da FASE 0 (aceitando simulado): "
            f"**{'aprovado' if fase0['aprovado'] else 'reprovado'}**"
            + ("" if fase0["aprovado"] else f" — faltam {', '.join(fase0['faltam'])}")
            + " · portão real: fechado (só resultado de hardware abre).")
    res.dados["markdown"] = laudo_markdown(linhas, titulo="FASE 0 — laudo da plataforma",
                                           nota=nota)
    core.close()
    return res


__all__ = ["executar"]
