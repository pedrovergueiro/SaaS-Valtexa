"""Aplicação FastAPI da plataforma ValTexa.

Tudo é API-first. O SaaS visual, quando existir, consome exatamente estas rotas
— nenhuma regra de negócio vive na tela, e cada permissão é conferida aqui,
mesmo que o frontend já tenha escondido o botão.

Sobe com ``uvicorn valtexa.main:app --reload``. A documentação interativa fica em
``/docs``; ``/openapi.json`` é o contrato que gera o cliente do frontend e serve
de referência para o firmware.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select, text

from valtexa import worker as background
from valtexa.api.middleware import RawBodyMiddleware
from valtexa.api.routers import (
    agro,
    auth,
    console,
    device_protocol,
    farms,
    fleet,
    missions,
    perception,
    twin,
)
from valtexa.config import BASE_DIR, settings
from valtexa.db import engine, migrate, session_scope
from valtexa.models import OutboxEvent
from valtexa.models.fleet import PROTOCOL_VERSION
from valtexa.schemas import HealthResponse
from valtexa.seed import sync_device_models
from valtexa.services import geo, storage
from valtexa.services.mission_manager import MissionNotAuthorizedError, MissionStateError

logger = logging.getLogger(__name__)

API_PREFIX = "/v1"

_worker_stop = threading.Event()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Prepara banco, armazenamento, catálogo de hardware e o drenador de eventos."""
    logging.basicConfig(
        level=settings.log_level, format="%(asctime)s %(levelname)-8s %(name)s: %(message)s"
    )

    migrate()
    storage.store.root.mkdir(parents=True, exist_ok=True)

    with session_scope() as session:
        created = sync_device_models(session)
    if created:
        logger.info("Catálogo de hardware: %d modelo(s) cadastrado(s).", created)

    problems = settings.production_problems()
    if problems:
        if settings.is_production:
            # Em produção isso não é aviso: é impedimento. Subir assim colocaria
            # no ar um sistema que assina comandos com um segredo público.
            raise RuntimeError(
                "Configuração inadequada para produção:\n  - " + "\n  - ".join(problems)
            )
        for problem in problems:
            logger.warning("Pendência para produção: %s", problem)

    worker_thread: threading.Thread | None = None
    if settings.event_worker_in_api:
        # Uma thread basta para o piloto e mantém tudo num container. Com várias
        # réplicas, desligue e rode ``python -m valtexa.worker`` à parte.
        _worker_stop.clear()
        worker_thread = threading.Thread(
            target=background.run_forever, args=(_worker_stop,), name="valtexa-worker", daemon=True
        )
        worker_thread.start()
    try:
        yield
    finally:
        _worker_stop.set()
        if worker_thread is not None:
            worker_thread.join(timeout=background.TICK_SECONDS + 1)


app = FastAPI(
    title="ValTexa Autonomous Farm Platform",
    version="0.1.0",
    description=(
        "Nuvem da ValTexa: frota, missões, percepção, decisão, segurança e gêmeo "
        "digital da lavoura.\n\n"
        "**Princípio central:** nenhum resultado de IA comanda diretamente uma "
        "aplicação. A cadeia é percepção → diagnóstico → recomendação → validação "
        "→ autorização → execução → verificação, e cada elo grava o seu próprio "
        "registro.\n\n"
        "O robô fala em `/v1/device/**` com requisições assinadas em Ed25519; as "
        "pessoas falam no restante de `/v1/**` com token de sessão. Os dois "
        "conjuntos não se misturam."
    ),
    lifespan=lifespan,
    openapi_tags=[
        {"name": "autenticação", "description": "Login, identidade e organização."},
        {"name": "fazendas", "description": "Fazendas, talhões e zonas de manejo."},
        {"name": "frota", "description": "Catálogo de hardware, provisionamento e dispositivos."},
        {
            "name": "protocolo do dispositivo",
            "description": (
                "O que o robô chama. Requisições assinadas com Ed25519. Ver "
                "docs/DEVICE_PROTOCOL.md."
            ),
        },
        {"name": "missões", "description": "Planejar, aprovar, autorizar, despachar, abortar."},
        {"name": "percepção", "description": "Observações, diagnósticos, fila do agrônomo."},
        {"name": "insumos e aplicação", "description": "Produtos, lotes, tanques e aplicações."},
        {"name": "gêmeo digital", "description": "Estado do talhão, séries, anomalias, auditoria."},
    ],
)

# Precisa envolver tudo: a assinatura do dispositivo cobre o corpo, e o
# FastAPI o consome antes das dependências. Ver valtexa/api/middleware.py.
app.add_middleware(RawBodyMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=settings.allow_credentials,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["*"],
)

for module in (auth, farms, fleet, device_protocol, missions, perception, agro, twin, console):
    app.include_router(module.router, prefix=API_PREFIX)


@app.exception_handler(MissionStateError)
async def _handle_mission_state(_: Request, exc: MissionStateError) -> JSONResponse:
    """Transição inválida é conflito de estado, não erro do servidor."""
    return JSONResponse(status_code=status.HTTP_409_CONFLICT, content={"detail": str(exc)})


@app.exception_handler(MissionNotAuthorizedError)
async def _handle_not_authorized(_: Request, exc: MissionNotAuthorizedError) -> JSONResponse:
    return JSONResponse(status_code=status.HTTP_409_CONFLICT, content={"detail": str(exc)})


@app.exception_handler(geo.InvalidPolygonError)
async def _handle_invalid_polygon(_: Request, exc: geo.InvalidPolygonError) -> JSONResponse:
    """Geometria inválida é erro do cliente."""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, content={"detail": str(exc)}
    )


@app.exception_handler(storage.AssetTooLargeError)
async def _handle_asset_too_large(_: Request, exc: storage.AssetTooLargeError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, content={"detail": str(exc)}
    )


@app.get("/health", response_model=HealthResponse, summary="Estado da plataforma", tags=["saúde"])
def health() -> HealthResponse:
    """Diagnóstico do processo.

    Separa *liveness* de *readiness*: responder ``200`` diz que o processo está
    de pé; ``database`` e ``inference`` dizem se ele consegue trabalhar.
    """
    database = "ok"
    pending = 0
    try:
        with session_scope() as session:
            session.execute(text("SELECT 1"))
            pending = (
                session.scalar(
                    select(func.count(OutboxEvent.id)).where(OutboxEvent.delivered_at.is_(None))
                )
                or 0
            )
    except Exception as exc:  # health nunca deve levantar; um erro aqui vira o texto abaixo
        database = f"erro: {type(exc).__name__}"

    return HealthResponse(
        status="ok",
        environment=settings.environment,
        protocol_version=PROTOCOL_VERSION,
        database=database,
        inference=settings.inference_url if settings.inference_enabled else "desligado",
        pending_events=pending,
        warnings=settings.production_problems(),
    )


WEB_DIST = BASE_DIR / "web" / "dist"


def _mount_console(application: FastAPI, dist: Path) -> None:
    """Serve o console na raiz, com o *fallback* que uma SPA precisa.

    Qualquer caminho que não seja arquivo do build devolve ``index.html`` — é o
    roteador do navegador que resolve ``/missoes/123``. A exceção é ``/v1``: uma
    rota de API inexistente precisa de 404 de verdade, não de uma página HTML
    que o cliente tentaria interpretar como JSON.
    """
    root = dist.resolve()
    index = root / "index.html"
    if (root / "assets").is_dir():
        application.mount("/assets", StaticFiles(directory=root / "assets"), name="console")

    @application.get("/{path:path}", include_in_schema=False)
    def console_app(path: str) -> FileResponse:
        if path == "v1" or path.startswith("v1/"):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Rota não encontrada.")
        candidate = (root / path).resolve()
        if path and candidate.is_file() and candidate.is_relative_to(root):
            return FileResponse(candidate)
        return FileResponse(index)


if settings.serve_web and (WEB_DIST / "index.html").is_file():
    _mount_console(app, WEB_DIST)


__all__ = ["app", "engine"]
