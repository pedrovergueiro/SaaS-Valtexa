"""Ponto de entrada do simulador: ``python -m simulator``.

Sobe a plataforma num processo próprio, prepara a fazenda de demonstração e roda
o roteiro completo. Não precisa de servidor no ar, nem de banco configurado, nem
de GPU — a ideia é que qualquer pessoa consiga ver o sistema inteiro funcionando
em um comando.

Com ``--url`` ele fala com uma plataforma já em execução, o que serve para
validar um ambiente de homologação.
"""

from __future__ import annotations

import argparse
import contextlib
import os
import socket
import sys
import threading
import time
from pathlib import Path

import httpx


def main(argv: list[str] | None = None) -> int:
    _force_utf8_output()
    parser = argparse.ArgumentParser(
        prog="simulator", description="Roda uma missão ponta a ponta na plataforma ValTexa."
    )
    parser.add_argument(
        "--url",
        default=None,
        help="Plataforma já no ar. Sem isto, o simulador sobe uma própria em memória.",
    )
    parser.add_argument(
        "--database",
        default=None,
        help="URL do banco. O padrão é um SQLite descartável dentro de .simulacao/.",
    )
    parser.add_argument("--keep", action="store_true", help="Não apaga o banco ao terminar.")
    parser.add_argument(
        "--rover-runtime",
        action="store_true",
        help=(
            "Ponta a ponta com o Rover Runtime de verdade (pacote rover/, HAL simulada): "
            "cliente → talhão → missão → Edge AI → queda de rede → sync → IA de nuvem → "
            "planta → incidência → prescrição → aplicação → nova missão → relatório."
        ),
    )
    parser.add_argument(
        "--fase0",
        action="store_true",
        help=(
            "Validação do Rover: roda a FASE 0 inteira (ensaios assinados no Rover Runtime "
            "com a bancada SIMULADA), confere o portão e escreve o laudo em Markdown."
        ),
    )
    parser.add_argument(
        "--ia",
        default=None,
        help="Com --rover-runtime: a IA de nuvem de verdade (serviço VALTEXA-B, ex.: "
        "http://127.0.0.1:8001, com FIELDS_DIR) no lugar do dublê.",
    )
    parser.add_argument(
        "--modelo-real",
        type=Path,
        default=None,
        help="Com --rover-runtime: o .onnx da Edge AI com os arquivos ao lado (perfil; no "
        "café, cabeça e torre) no lugar do modelo de demonstração.",
    )
    parser.add_argument(
        "--folhas",
        type=Path,
        default=None,
        help="Com --modelo-real: <pasta>/<Classe>/ com fotos de folha que o modelo não viu.",
    )
    args = parser.parse_args(argv)
    if bool(args.modelo_real) != bool(args.folhas) or (args.modelo_real and not args.ia):
        parser.error("--modelo-real, --folhas e --ia vão juntos (o modo com pesos reais)")
    real = None
    if args.modelo_real:
        from simulator.ponta_a_ponta import Real

        real = Real(args.modelo_real, args.folhas)
    if args.fase0:
        runner = _run_fase0
    elif args.rover_runtime:
        def runner(url: str) -> int:
            return _run_rover_runtime(url, real)
    else:
        runner = _run_against

    if args.url:
        return runner(args.url)

    workspace = Path(__file__).resolve().parent.parent / ".simulacao"
    workspace.mkdir(exist_ok=True)
    database = args.database or f"sqlite:///{workspace / 'simulacao.db'}"

    # Precisa vir antes de importar valtexa: as configurações são lidas uma vez
    # por processo e ficam em cache.
    os.environ["DATABASE_URL"] = database
    os.environ["STORAGE_DIR"] = str(workspace / "storage")
    if args.ia:
        os.environ["INFERENCE_URL"] = args.ia
        os.environ["SIMULATED_INFERENCE"] = "false"
        os.environ["INFERENCE_ENABLED"] = "true"
    else:
        os.environ["SIMULATED_INFERENCE"] = "true"
        os.environ["INFERENCE_ENABLED"] = "false"
    os.environ["ENVIRONMENT"] = "test"
    os.environ.setdefault("LOG_LEVEL", "WARNING")

    if not args.keep:
        _reset(workspace)

    port = _free_port()
    url = f"http://127.0.0.1:{port}"
    server = _start_server(port)
    try:
        _wait_for_health(url)
        code = runner(url)
    finally:
        server.should_exit = True
        time.sleep(0.5)
        _close_database()

    if not args.keep:
        _reset(workspace)
    return code


def _force_utf8_output() -> None:
    """Garante que o console aguente o texto do roteiro.

    O terminal do Windows abre em cp1252, que não tem acentos nem os traços
    usados nos títulos — e um ``UnicodeEncodeError`` no meio da simulação
    pareceria falha do sistema quando é só o console.
    """
    for stream in (sys.stdout, sys.stderr):
        with contextlib.suppress(AttributeError, ValueError):
            stream.reconfigure(encoding="utf-8", errors="replace")


def _run_against(url: str) -> int:
    from simulator.scenario import run
    from valtexa.db import session_scope
    from valtexa.seed import (
        DEMO_FIELD_BOUNDARY,
        DEMO_ZONE_BOUNDARY,
        seed_demo,
        sync_device_models,
    )

    with session_scope() as session:
        sync_device_models(session)
        demo = seed_demo(session)

    from sqlalchemy import select

    from valtexa.models import Farm

    with session_scope() as session:
        farm = session.get(Farm, demo["farm_id"]) if demo["farm_id"] else None
        if farm is None:
            farm = session.scalars(select(Farm)).first()
        demo["base_lat"] = farm.base_lat
        demo["base_lon"] = farm.base_lon
    demo["zone_boundary"] = DEMO_ZONE_BOUNDARY
    demo["field_boundary"] = DEMO_FIELD_BOUNDARY

    print(f"\nPlataforma: {url}   |   documentação interativa: {url}/docs")
    result = run(url, demo)

    print(f"\n{'═' * 74}\n  RESUMO\n{'═' * 74}")
    print(f"  observações coletadas ....... {result.observations}")
    print(f"  missão retomada de checkpoint {'sim' if result.resumed else 'não'}")
    print(f"  registros sincronizados ..... {result.synced}")
    print(
        f"  cópia 3D .................... {result.plants} plantas em {result.scans} ruas "
        f"({result.coverage:.0%} do talhão)"
    )
    print(f"  pragas rotuladas pelo agrônomo {result.pests_reviewed}")
    print(f"  bloqueios de segurança ...... {len(result.blocked_reasons)}")
    for reason in result.blocked_reasons:
        print(f"      • {reason}")
    for outcome, rationale in result.decisions.items():
        print(f"  decisão: {outcome} — {rationale[:60]}")
    if result.application_id:
        print(f"  aplicação registrada ........ {result.application_id[:12]}")
    print()
    return 0


def _run_rover_runtime(url: str, real=None) -> int:
    """O roteiro de ``simulator/ponta_a_ponta.py`` contra a plataforma em ``url``.

    O Rover fala HTTPS de verdade (``HttpNetwork``) com a API — o mesmo protocolo
    do robô real. As contas da equipe ValTexa são criadas direto no banco.
    """
    import tempfile

    from valtexa_rover.hal.local import HttpNetwork

    from simulator.ponta_a_ponta import executar
    from valtexa.db import session_scope
    from valtexa.seed import seed_demo, sync_device_models
    from valtexa.services import model_registry, plans

    with session_scope() as session:
        sync_device_models(session)
        plans.sincronizar_catalogo(session)
        model_registry.sincronizar_catalogo(session)
        seed_demo(session)
    with httpx.Client(base_url=url, timeout=60) as http, \
            tempfile.TemporaryDirectory(prefix="rover-sim-", ignore_cleanup_errors=True) as pasta:
        res = executar(http, HttpNetwork(url), session_scope, Path(pasta),
                       log=print, real=real)
    titulo = ("PONTA A PONTA COM O ROVER RUNTIME (pesos reais, folhas reais, IA de nuvem real;"
              " hardware SIMULADO)" if real else
              "PONTA A PONTA COM O ROVER RUNTIME (hardware e IA SIMULADOS)")
    print(f"\n{'═' * 74}\n  {titulo}\n{'═' * 74}")
    def ordem(p) -> tuple[int, str]:
        n = p.nome.split()[0]
        return int(n.rstrip("abc")), n

    for passo in sorted(res.passos, key=ordem):
        print(f"  {'OK ' if passo.ok else 'FALHA'} {passo.nome:<34} {passo.prova}")
    print()
    return 0 if all(p.ok for p in res.passos) else 1


def _run_fase0(url: str) -> int:
    """A FASE 0 de ``simulator/fase0.py`` contra a plataforma em ``url``; laudo em
    ``laudo-fase0.md`` (pasta atual)."""
    import tempfile

    from valtexa_rover.hal.local import HttpNetwork

    from simulator.fase0 import executar
    from valtexa.db import session_scope
    from valtexa.seed import sync_device_models
    from valtexa.services import plans

    with session_scope() as session:
        sync_device_models(session)
        plans.sincronizar_catalogo(session)
    with httpx.Client(base_url=url, timeout=60) as http, \
            tempfile.TemporaryDirectory(prefix="fase0-") as pasta:
        print("FASE 0 na bancada SIMULADA, veredito da plataforma:")
        res = executar(http, HttpNetwork(url), session_scope, Path(pasta), log=print)
    saida = Path("laudo-fase0.md")
    saida.write_text(res.dados["markdown"], encoding="utf-8")
    print(f"\n{'═' * 74}\n  FASE 0 (hardware SIMULADO)\n{'═' * 74}")
    for passo in res.passos:
        print(f"  {'OK ' if passo.ok else 'FALHA'} {passo.nome:<40} {passo.prova}")
    print(f"\n  laudo: {saida.resolve()}\n")
    return 0 if all(p.ok for p in res.passos) else 1


def _start_server(port: int):
    """Sobe o uvicorn numa thread e devolve o servidor, para poder desligá-lo."""
    import uvicorn

    from valtexa.main import app

    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    threading.Thread(target=server.run, daemon=True).start()
    return server


def _wait_for_health(url: str, timeout: float = 30.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        with contextlib.suppress(httpx.HTTPError):
            if httpx.get(f"{url}/health", timeout=2.0).status_code == 200:
                return
        time.sleep(0.2)
    raise RuntimeError(f"A plataforma não respondeu em {timeout:.0f}s.")


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _close_database() -> None:
    """Devolve as conexões ao sistema operacional.

    No Windows um arquivo aberto não pode ser removido, e o pool do SQLAlchemy
    segura a conexão SQLite até ser descartado. Sem isto, a limpeza falha com
    ``PermissionError`` depois de uma simulação bem-sucedida — e o simulador
    terminaria com erro tendo dado certo.
    """
    with contextlib.suppress(Exception):
        from valtexa.db import engine

        engine.dispose()


def _reset(workspace: Path) -> None:
    """Limpa o banco e o armazenamento da simulação.

    Rodar sempre do zero é o que torna o resultado comparável entre execuções —
    e evita a pergunta "isso é do run de agora ou sobrou do anterior?".

    Falha em remover não é motivo para o simulador terminar com erro: o
    resultado da simulação já foi produzido. Avisa e segue.
    """
    import shutil

    for path in workspace.glob("simulacao.db*"):
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:
            print(f"  (não consegui remover {path.name}: {exc})")
    shutil.rmtree(workspace / "storage", ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
