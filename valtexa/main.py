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
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from valtexa import worker as background
from valtexa.api.middleware import (
    CabecalhosDeSeguranca,
    RawBodyMiddleware,
    ReciboDoDispositivo,
)
from valtexa.api.routers import (
    admin,
    agro,
    auth,
    collections_api,
    consent_api,
    console,
    device_protocol,
    edge_arquivos,
    edge_sync,
    ensaios_api,
    farms,
    fleet,
    localizar,
    missions,
    notifications,
    observabilidade,
    ota,
    perception,
    plans_api,
    plants,
    platform,
    platform_ai,
    platform_console,
    platform_rover,
    stream,
    support,
    twin,
    validacao_campo,
)
from valtexa.config import BASE_DIR, recusar_se_inadequado, settings
from valtexa.db import engine, migrate, session_scope
from valtexa.observability import http as obs_http
from valtexa.observability import logs
from valtexa.schemas import HealthResponse
from valtexa.seed import seed_platform_team, sync_device_models
from valtexa.services import alertas, geo, model_registry, plans, saude, storage
from valtexa.services import observabilidade as obs
from valtexa.services.mission_manager import MissionNotAuthorizedError, MissionStateError

logger = logging.getLogger(__name__)

API_PREFIX = "/v1"

_worker_stop = threading.Event()
_metrics_stop = threading.Event()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Prepara banco, armazenamento, catálogo de hardware e o drenador de eventos."""
    logs.configurar(settings.log_level, settings.log_format)
    # Antes de tocar no banco: em produção, segredo fraco ou repetido nem migra.
    recusar_se_inadequado(settings, logger)

    migrate()
    # Só o disco local tem raiz; com S3, ``store.root`` quebrava a subida (Parte 9).
    storage.preparar()

    with session_scope() as session:
        created = sync_device_models(session)
    with session_scope() as session:
        planos_criados = plans.sincronizar_catalogo(session)
    with session_scope() as session:
        modelos_criados = model_registry.sincronizar_catalogo(session)
    if modelos_criados:
        logger.info("Model Registry: %d modelo(s) do catálogo inicial.", modelos_criados)
    if planos_criados:
        logger.info("Catálogo de planos: %d plano(s) cadastrado(s).", planos_criados)
    if created:
        logger.info("Catálogo de hardware: %d modelo(s) cadastrado(s).", created)
    with session_scope() as session:
        regras_criadas = alertas.sincronizar_catalogo(session)
    if regras_criadas:
        logger.info("Regras de alerta: %d regra(s) padrão criada(s).", regras_criadas)

    # As contas da equipe da ValTexa. Sem senha no ambiente não se cria nenhuma:
    # uma senha de administrador de plataforma com padrão no código seria a mesma
    # em toda instalação, e a primeira que alguém tentaria.
    if settings.platform_admin_password:
        with session_scope() as session:
            novas = seed_platform_team(session, password=settings.platform_admin_password)
        if novas:
            logger.info("Equipe ValTexa: %d conta(s) criada(s).", len(novas))
    else:
        logger.info(
            "PLATFORM_ADMIN_PASSWORD não definida: as contas da equipe da ValTexa "
            "não foram criadas."
        )

    worker_thread: threading.Thread | None = None
    if settings.event_worker_in_api:
        # Uma thread basta para o piloto e mantém tudo num container. Com várias
        # réplicas, desligue e rode ``python -m valtexa.worker`` à parte.
        _worker_stop.clear()
        worker_thread = threading.Thread(
            target=background.run_forever, args=(_worker_stop,), name="valtexa-worker", daemon=True
        )
        worker_thread.start()
    # Estatística da API por minuto: cada réplica descarrega a sua no banco.
    _metrics_stop.clear()
    metrics_thread = threading.Thread(
        target=obs.descarregar_periodicamente, args=(_metrics_stop,),
        name="valtexa-metricas", daemon=True,
    )
    metrics_thread.start()
    try:
        yield
    finally:
        _worker_stop.set()
        _metrics_stop.set()
        if worker_thread is not None:
            worker_thread.join(timeout=background.TICK_SECONDS + 1)
        metrics_thread.join(timeout=5)


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
        {
            "name": "plataforma",
            "description": (
                "Console interno da ValTexa: papéis da equipe, sessões de suporte "
                "('entrar como cliente'), auditoria global."
            ),
        },
    ],
)

# Precisa envolver tudo: a assinatura do dispositivo cobre o corpo, e o
# FastAPI o consome antes das dependências. Ver valtexa/api/middleware.py.
app.add_middleware(RawBodyMiddleware)
# Recibo assinado das respostas do dispositivo pedidas pelo Rover que fala pela base.
app.add_middleware(ReciboDoDispositivo)
app.add_middleware(CabecalhosDeSeguranca)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=settings.allow_credentials,
    # PUT entra por causa do envio de pedaço de arquivo em /v1/admin/collections.
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["*"],
    expose_headers=["X-Request-Id"],
)

# Por fora de tudo (o último adicionado é o mais externo): mede a requisição
# inteira, inclusive a resposta de CORS, e põe o X-Request-Id em toda resposta.
app.add_middleware(obs_http.ObservabilidadeMiddleware)

for module in (
    auth,
    farms,
    fleet,
    device_protocol,
    edge_arquivos,
    edge_sync,
    ota,
    missions,
    perception,
    plants,
    validacao_campo,
    agro,
    twin,
    console,
    collections_api,
    admin,
    platform,
    platform_console,
    platform_ai,
    platform_rover,
    ensaios_api,
    plans_api,
    consent_api,
    notifications,
    support,
    observabilidade,
    stream,
    localizar,
):
    app.include_router(module.router, prefix=API_PREFIX)

# /metrics fica na raiz: é onde o Prometheus procura por padrão.
app.include_router(observabilidade.metrics_router)


@app.exception_handler(MissionStateError)
async def _handle_mission_state(_: Request, exc: MissionStateError) -> JSONResponse:
    """Transição inválida é conflito de estado, não erro do servidor."""
    return JSONResponse(status_code=status.HTTP_409_CONFLICT, content={"detail": str(exc)})


@app.exception_handler(MissionNotAuthorizedError)
async def _handle_not_authorized(_: Request, exc: MissionNotAuthorizedError) -> JSONResponse:
    return JSONResponse(status_code=status.HTTP_409_CONFLICT, content={"detail": str(exc)})


@app.exception_handler(plans.PlanError)
async def _handle_plan(_: Request, exc: plans.PlanError) -> JSONResponse:
    """Limite do plano (409) ou assinatura que não vale (402), com a mensagem pronta."""
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.exception_handler(geo.InvalidPolygonError)
async def _handle_invalid_polygon(_: Request, exc: geo.InvalidPolygonError) -> JSONResponse:
    """Geometria inválida é erro do cliente."""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, content={"detail": str(exc)}
    )


@app.exception_handler(storage.AssetTooLargeError)
async def _handle_asset_too_large(_: Request, exc: storage.AssetTooLargeError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, content={"detail": str(exc)}
    )


@app.exception_handler(Exception)
async def _handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
    """A rede de segurança: qualquer erro não previsto vira JSON com um código.

    Duas coisas acontecem aqui, e as duas importam.

    **O console recebe JSON.** Sem este tratador, uma exceção não prevista sai do
    Starlette como ``Internal Server Error`` em texto puro. O console espera
    ``{"detail": ...}`` em toda resposta de erro, então o que a pessoa via era a
    tela quebrar sem mensagem — o pior jeito de falhar, porque não diz nem o que
    houve nem a quem recorrer.

    **O erro ganha um número.** O traceback completo fica no log do servidor,
    marcado com o mesmo código que a pessoa vê na tela. É o que transforma "deu
    erro aqui" numa busca de um grep — sem ele, achar o traceback certo num log
    de um dia inteiro é sorte.

    O corpo da resposta **não** carrega o traceback, de propósito: mensagem de
    exceção interna costuma trazer caminho de arquivo, consulta SQL e às vezes
    valor de campo. Isso é do log, que é interno, não da resposta, que atravessa
    a internet.
    """
    codigo = uuid4().hex[:12]
    # Este tratador roda por fora do middleware de observabilidade (o contexto da
    # requisição já fechou): o request_id vem do scope, onde o middleware o deixou.
    request_id = request.scope.get(obs_http.REQUEST_ID_KEY)
    logger.exception(
        "Erro não tratado [%s] em %s %s (req=%s)", codigo, request.method, request.url.path,
        request_id, extra={"campos": {"request_id": request_id, "error_id": codigo}},
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": (
                "Erro interno. A equipe da ValTexa consegue localizá-lo pelo "
                f"código {codigo}."
            ),
            "error_id": codigo,
            "request_id": request_id,
        },
        headers={"X-Request-Id": request_id} if request_id else None,
    )


@app.get("/health", response_model=HealthResponse, summary="Estado da plataforma", tags=["saúde"])
def health() -> HealthResponse:
    """Diagnóstico público do processo.

    Separa *liveness* de *readiness*: responder ``200`` diz que o processo está
    de pé; ``database`` e ``inference`` dizem se ele consegue trabalhar. Sem
    autenticação, então sem detalhe interno: o completo é ``/v1/platform/health``.
    """
    return saude.publico(saude.diagnostico())


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
