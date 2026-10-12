"""Painel administrativo da ValTexa.

Tudo aqui exige um papel de plataforma com a capacidade da rota
(:func:`~valtexa.api.deps.require_platform` e
:func:`~valtexa.api.deps.require_platform_in_tenant`). É a fronteira
que o produto pede: o cliente vê a sua lavoura e os seus resultados; a
complexidade operacional — de onde vieram as imagens, que fila está travada, que
modelo respondeu — fica deste lado.

A área central é **Importar Coleta**: o voo é de um operador terceirizado e os
arquivos chegam pela mão de alguém. O fluxo é sempre o mesmo, e é o que as rotas
abaixo desenham, em ordem:

1. ``POST /admin/collections`` — cliente, propriedade, talhão, data, origem, tipo;
2. ``POST /admin/collections/{id}/files`` — declara os arquivos que virão;
3. ``PUT  /admin/collections/{id}/files/{file_id}/chunk`` — manda os bytes, em pedaços;
4. ``POST /admin/collections/{id}/complete`` — fecha o upload e enfileira;
5. ``GET  /admin/collections/{id}`` — acompanha, sem manter aba aberta;
6. ``POST /admin/collections/{id}/release`` — publica para o cliente.

O que **não** existe aqui, de propósito: planejar voo, comandar drone, iniciar
missão aérea. O drone próprio da ValTexa é fase futura e não tem rota nenhuma —
nem desabilitada, nem "em breve".
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from valtexa.api.deps import (
    PlatformCaller,
    Principal,
    get_scoped,
    require_platform,
    require_platform_in_tenant,
    require_platform_ou_suporte,
    scoped,
)
from valtexa.config import settings
from valtexa.db import get_session
from valtexa.models import (
    ActorType,
    Collection,
    CollectionFile,
    CollectionState,
    Dataset,
    DatasetSample,
    DatasetVersion,
    DeviceModel,
    Diagnosis,
    Farm,
    Field,
    JobState,
    ModelVersion,
    ModelVersionState,
    ProcessingJob,
    SubjectType,
    Tenant,
)
from valtexa.schemas import (
    BoundaryRefineIn,
    BoundaryRefineOut,
    CatalogModelOut,
    ChargePostOut,
    ChunkAccepted,
    CollectionCreate,
    CollectionFileOut,
    CollectionFilesDeclare,
    CollectionOut,
    DatasetOut,
    DatasetSampleOut,
    DatasetVersionCreate,
    DatasetVersionOut,
    JobOut,
    Message,
    ModelVersionOut,
    OnboardIn,
    OnboardOut,
    PlanOut,
    PlanRequest,
    ReliefOut,
    RowsOut,
    TenantOut,
    TenantUpdate,
    TerrainObjectOut,
    TerrainOut,
)
from valtexa.security import rbac
from valtexa.services import (
    audit,
    collections,
    dataset,
    elevation,
    geo,
    jobs,
    planner,
    plans,
)
from valtexa.services.hal import Capabilities

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])

MAX_CHUNK_BYTES = 32 * 1024 * 1024
"""Teto de **um pedaço**, não do arquivo nem da coleta.

Existe para limitar a memória de uma requisição, e é isso. Um arquivo de 8 GB
sobe em pedaços de 8 MB sem encostar neste número; o tamanho total que a
plataforma aceita é o do armazenamento contratado.
"""


# ---------------------------------------------------------------------------
# Clientes
# ---------------------------------------------------------------------------


@router.get("/tenants", response_model=list[TenantOut], summary="Todos os clientes")
def list_tenants(
    _: PlatformCaller = Depends(require_platform(rbac.PLATFORM_TENANT_READ)),
    session: Session = Depends(get_session),
) -> list[TenantOut]:
    """A lista que abre o formulário de importação.

    É a única rota da plataforma que atravessa clientes de propósito — e só a
    atravessa para *listar*. Qualquer leitura de dado de lavoura continua
    passando pelo filtro de tenant.
    """
    linhas = session.scalars(select(Tenant).order_by(Tenant.name)).all()
    return [_tenant_out(session, linha) for linha in linhas]


@router.post(
    "/tenants",
    response_model=OnboardOut,
    status_code=status.HTTP_201_CREATED,
    summary="Cadastra um cliente, com propriedade e primeiro talhao",
)
def onboard_tenant(
    payload: OnboardIn,
    principal: PlatformCaller = Depends(require_platform(rbac.PLATFORM_TENANT_MANAGE)),
    session: Session = Depends(get_session),
) -> OnboardOut:
    """Cria cliente, propriedade e talhao numa transacao so.

    As tres coisas juntas porque e assim que a informacao chega -- numa ligacao
    com o produtor, nao em tres visitas ao sistema. E numa transacao so porque a
    alternativa e pior: um cliente criado sem propriedade, depois de um erro no
    meio, fica orfao no banco e alguem precisa limpa-lo a mao.

    Propriedade e talhao sao opcionais. Da para cadastrar o cliente com o que se
    sabe e voltar depois -- e o caso comum, porque o contorno do talhao se
    desenha no editor, com a imagem de satelite na frente, e nao ao telefone.
    """
    existe = session.scalars(select(Tenant).where(Tenant.slug == payload.tenant.slug)).first()
    if existe is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Ja existe cliente com o apelido {payload.tenant.slug!r}.",
        )

    tenant = Tenant(**payload.tenant.model_dump())
    session.add(tenant)
    session.flush()

    avisos: list[str] = []
    codigo = payload.plan_code or plans.PLANO_PADRAO
    plano = plans.plano_por_codigo(session, codigo)
    if plano is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Plano {codigo!r} não existe.")
    if payload.plan_code is None:
        avisos.append(
            "Cliente sem plano escolhido: ficou no Piloto, sem limites. Defina o plano "
            "comercial em Planos e uso."
        )
    plans.assinar(
        session,
        tenant,
        plano,
        actor=principal.user,
        notes=(
            f"Serviço contratado: {tenant.contracted_service}"
            if tenant.contracted_service
            else None
        ),
    )
    farm_id: str | None = None
    field_id: str | None = None

    if payload.farm is not None:
        plans.exigir(session, tenant.id, "farms")
        farm = Farm(tenant_id=tenant.id, **payload.farm.model_dump())
        session.add(farm)
        session.flush()
        farm_id = farm.id
        # A mesma linha que `POST /v1/farms` grava. Sem ela, uma propriedade
        # nascida pelo cadastro de cliente nao aparecia em "criacao de
        # propriedades" -- so dentro da carga do `tenant.onboarded`, que ninguem
        # filtra. Duas portas para o mesmo ato precisam deixar o mesmo rastro,
        # senao a trilha conta uma historia que depende de por onde se entrou.
        audit.record(
            session,
            tenant_id=tenant.id,
            action="farm.created",
            subject_type=SubjectType.FIELD,
            subject_id=farm.id,
            actor_type=ActorType.USER,
            actor_id=principal.user_id,
            actor_label=principal.user.email,
            payload={"name": farm.name, "via": "cadastro de cliente"},
        )

        if payload.field is not None:
            contorno = payload.field.boundary
            area = None
            if contorno:
                try:
                    area = round(geo.area_ha(contorno), 4)
                except (ValueError, geo.InvalidPolygonError) as exc:
                    raise HTTPException(
                        status.HTTP_422_UNPROCESSABLE_CONTENT,
                        f"O contorno do talhao nao fecha um poligono: {exc}",
                    ) from exc
            else:
                avisos.append(
                    "O talhao ficou sem contorno. Desenhe-o no editor antes de "
                    "planejar missao: sem poligono nao ha area, rota nem cerca virtual."
                )

            plans.exigir(session, tenant.id, "fields")
            plans.exigir(session, tenant.id, "hectares", acrescimo=area or 0)
            campo = Field(
                tenant_id=tenant.id,
                farm_id=farm.id,
                boundary=contorno,
                area_ha=area,
                **payload.field.model_dump(exclude={"boundary"}),
            )
            session.add(campo)
            session.flush()
            field_id = campo.id
            audit.record(
                session,
                tenant_id=tenant.id,
                action="field.created",
                subject_type=SubjectType.FIELD,
                subject_id=campo.id,
                actor_type=ActorType.USER,
                actor_id=principal.user_id,
                actor_label=principal.user.email,
                payload={
                    "area_ha": campo.area_ha,
                    "crop": campo.crop,
                    "farm_id": farm.id,
                    "via": "cadastro de cliente",
                },
            )
    elif payload.field is not None:
        avisos.append(
            "O talhao foi ignorado: talhao pertence a uma propriedade, e nenhuma "
            "foi informada."
        )

    audit.record(
        session,
        tenant_id=tenant.id,
        action="tenant.onboarded",
        subject_type=SubjectType.TENANT,
        subject_id=tenant.id,
        actor_type=ActorType.USER,
        actor_id=principal.user_id,
        actor_label=principal.user.email,
        new_state=tenant.slug,
        payload={
            "name": tenant.name,
            "document": tenant.document,
            "contracted_service": tenant.contracted_service,
            "farm_id": farm_id,
            "field_id": field_id,
        },
    )
    session.commit()
    session.refresh(tenant)
    return OnboardOut(
        tenant=_tenant_out(session, tenant),
        farm_id=farm_id,
        field_id=field_id,
        warnings=avisos,
    )


@router.patch(
    "/tenants/{tenant_id}",
    response_model=TenantOut,
    summary="Altera o cadastro de um cliente",
)
def update_tenant(
    tenant_id: str,
    payload: TenantUpdate,
    principal: PlatformCaller = Depends(require_platform(rbac.PLATFORM_TENANT_MANAGE)),
    session: Session = Depends(get_session),
) -> TenantOut:
    """Atualiza contato, endereco e contrato. O apelido nao muda.

    O ``slug`` e a identidade publica do cliente e aparece em link e em token;
    troca-lo quebraria o que ja foi compartilhado. Renomear a empresa e mudar
    ``name``, que e o que as telas mostram.
    """
    tenant = session.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cliente nao encontrado.")

    mudancas = payload.model_dump(exclude_unset=True)
    antes = {campo: getattr(tenant, campo) for campo in mudancas}
    for campo, valor in mudancas.items():
        setattr(tenant, campo, valor)

    audit.record(
        session,
        tenant_id=tenant.id,
        action="tenant.updated",
        subject_type=SubjectType.TENANT,
        subject_id=tenant.id,
        actor_type=ActorType.USER,
        actor_id=principal.user_id,
        actor_label=principal.user.email,
        payload={"antes": antes, "depois": mudancas},
    )
    session.commit()
    session.refresh(tenant)
    return _tenant_out(session, tenant)


def _tenant_out(session: Session, tenant: Tenant) -> TenantOut:
    """O cadastro com o tamanho da operacao junto.

    Propriedades, talhoes e area somada vem na mesma resposta porque e o que a
    lista de clientes precisa mostrar para ser util -- um nome sozinho nao diz
    se aquele cliente tem 2 ou 200 hectares em operacao.
    """
    fazendas = session.scalars(select(Farm).where(Farm.tenant_id == tenant.id)).all()
    talhoes = session.scalars(select(Field).where(Field.tenant_id == tenant.id)).all()
    areas = [campo.area_ha for campo in talhoes if campo.area_ha]
    sub = plans.assinatura(session, tenant.id)
    return TenantOut(
        id=tenant.id,
        name=tenant.name,
        slug=tenant.slug,
        document=tenant.document,
        is_active=tenant.is_active,
        created_at=tenant.created_at,
        contact_name=tenant.contact_name,
        email=tenant.email,
        phone=tenant.phone,
        address=tenant.address,
        city=tenant.city,
        state=tenant.state,
        postal_code=tenant.postal_code,
        contracted_service=tenant.contracted_service,
        notes=tenant.notes,
        farms=len(fazendas),
        fields=len(talhoes),
        area_ha=round(sum(areas), 4) if areas else None,
        plan_code=sub.plan.code if sub else None,
        plan_name=sub.plan.name if sub else None,
        subscription_status=sub.status if sub else None,
    )


# ---------------------------------------------------------------------------
# Coletas
# ---------------------------------------------------------------------------


@router.post(
    "/collections",
    response_model=CollectionOut,
    status_code=status.HTTP_201_CREATED,
    summary="Cria uma coleta",
)
def create_collection(
    payload: CollectionCreate,
    principal: Principal = Depends(require_platform_in_tenant(rbac.COLLECTION_MANAGE)),
    session: Session = Depends(get_session),
) -> CollectionOut:
    """Abre o lote. O modelo que vai atendê-lo é resolvido já aqui.

    Resolver agora é o que faz o painel dizer, no próprio formulário, que uma
    coleta aérea de café não tem modelo treinado — em vez de o administrador
    descobrir isso depois de subir 1.500 imagens.
    """
    field = get_scoped(session, Field, payload.field_id, principal)
    try:
        coleta = collections.create(
            session,
            tenant_id=principal.tenant_id,
            field=field,
            collected_on=payload.collected_on,
            source=payload.source,
            kind=payload.kind,
            operator_name=payload.operator_name,
            notes=payload.notes,
            actor=principal.user,
        )
    except collections.CollectionError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    session.commit()
    return _collection_out(session, coleta)


@router.get("/collections", response_model=list[CollectionOut], summary="Coletas do cliente")
def list_collections(
    state: CollectionState | None = None,
    field_id: str | None = None,
    limit: int = Query(default=100, le=500),
    principal: Principal = Depends(require_platform_in_tenant(rbac.COLLECTION_MANAGE)),
    session: Session = Depends(get_session),
) -> list[CollectionOut]:
    consulta = scoped(select(Collection), Collection, principal)
    if state is not None:
        consulta = consulta.where(Collection.state == state)
    if field_id:
        consulta = consulta.where(Collection.field_id == field_id)
    linhas = session.scalars(consulta.order_by(Collection.created_at.desc()).limit(limit))
    return [_collection_out(session, linha) for linha in linhas]


@router.get("/collections/{collection_id}", response_model=CollectionOut, summary="Uma coleta")
def get_collection(
    collection_id: str,
    principal: Principal = Depends(require_platform_in_tenant(rbac.COLLECTION_MANAGE)),
    session: Session = Depends(get_session),
) -> CollectionOut:
    return _collection_out(session, get_scoped(session, Collection, collection_id, principal))


@router.post(
    "/collections/{collection_id}/files",
    response_model=list[CollectionFileOut],
    status_code=status.HTTP_201_CREATED,
    summary="Declara os arquivos da coleta",
)
def declare_files(
    collection_id: str,
    payload: CollectionFilesDeclare,
    principal: Principal = Depends(require_platform_in_tenant(rbac.COLLECTION_MANAGE)),
    session: Session = Depends(get_session),
) -> list[CollectionFileOut]:
    """Registra nome, tamanho e (opcionalmente) ``sha256`` de cada arquivo.

    Declarar antes de mandar é o que dá barra de progresso honesta — o total é
    conhecido desde o primeiro byte — e o que permite retomar: o painel pergunta
    o que falta e continua de onde parou.
    """
    coleta = get_scoped(session, Collection, collection_id, principal)
    try:
        arquivos = collections.register_files(
            session,
            coleta,
            [
                collections.ArquivoDeclarado(
                    filename=item.filename,
                    size_bytes=item.size_bytes,
                    content_type=item.content_type,
                    sha256=item.sha256,
                    captured_at=item.captured_at,
                    lat=item.lat,
                    lon=item.lon,
                    alt_m=item.alt_m,
                )
                for item in payload.files
            ],
        )
    except collections.CollectionError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    session.commit()
    return [_file_out(session, arquivo) for arquivo in arquivos]


@router.get(
    "/collections/{collection_id}/files",
    response_model=list[CollectionFileOut],
    summary="Arquivos da coleta",
)
def list_files(
    collection_id: str,
    state: str | None = None,
    limit: int = Query(default=500, le=2000),
    principal: Principal = Depends(require_platform_in_tenant(rbac.COLLECTION_MANAGE)),
    session: Session = Depends(get_session),
) -> list[CollectionFileOut]:
    """A lista que o painel usa para retomar um upload interrompido."""
    coleta = get_scoped(session, Collection, collection_id, principal)
    consulta = select(CollectionFile).where(CollectionFile.collection_id == coleta.id)
    if state:
        consulta = consulta.where(CollectionFile.state == state)
    linhas = session.scalars(consulta.order_by(CollectionFile.created_at).limit(limit))
    return [_file_out(session, linha) for linha in linhas]


@router.put(
    "/collections/{collection_id}/files/{file_id}/chunk",
    response_model=ChunkAccepted,
    summary="Envia um pedaço de arquivo",
)
async def upload_chunk(
    collection_id: str,
    file_id: str,
    request: Request,
    offset: int = Query(ge=0, description="Byte em que este pedaço começa."),
    principal: Principal = Depends(require_platform_in_tenant(rbac.COLLECTION_MANAGE)),
    session: Session = Depends(get_session),
) -> ChunkAccepted:
    """Grava um pedaço no deslocamento informado.

    O corpo é binário cru, não ``multipart``: o pedaço já é um recorte de bytes,
    e envolvê-lo num formulário custaria uma cópia em memória de cada pedaço sem
    dar nada em troca.

    Reenviar o mesmo pedaço é seguro — a rede cai justamente entre o servidor
    gravar e o cliente receber a confirmação. Qualquer outro deslocamento é
    recusado com 409 e ``received_bytes`` diz de onde continuar.
    """
    coleta = get_scoped(session, Collection, collection_id, principal)
    arquivo = session.get(CollectionFile, file_id)
    if arquivo is None or arquivo.collection_id != coleta.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Arquivo não encontrado nesta coleta.")

    dados = await request.body()
    if not dados:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Pedaço vazio.")
    if len(dados) > MAX_CHUNK_BYTES:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"Pedaço de {len(dados)} bytes excede {MAX_CHUNK_BYTES}. Divida em pedaços "
            f"menores — o limite é do pedaço, não do arquivo.",
        )

    try:
        collections.receive_chunk(session, arquivo, offset, dados)
    except collections.ChunkOutOfOrderError as exc:
        session.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"{exc} (received_bytes={exc.esperado})",
            headers={"X-Received-Bytes": str(exc.esperado)},
        ) from exc
    except collections.CollectionError as exc:
        session.rollback()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc

    session.commit()
    return ChunkAccepted(
        file_id=arquivo.id,
        received_bytes=arquivo.received_bytes,
        size_bytes=arquivo.size_bytes,
        state=arquivo.state,
        complete=arquivo.is_complete,
    )


@router.post(
    "/collections/{collection_id}/complete",
    response_model=CollectionOut,
    summary="Fecha o upload e enfileira o processamento",
)
def complete_upload(
    collection_id: str,
    principal: Principal = Depends(require_platform_in_tenant(rbac.COLLECTION_MANAGE)),
    session: Session = Depends(get_session),
) -> CollectionOut:
    """Encerra o recebimento. Daqui em diante quem trabalha é o worker.

    Arquivo incompleto não segura o lote: fica marcado e aparece no painel.
    """
    coleta = get_scoped(session, Collection, collection_id, principal)
    try:
        collections.complete_upload(session, coleta, actor=principal.user)
    except collections.CollectionError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    session.commit()
    return _collection_out(session, coleta)


@router.post(
    "/collections/{collection_id}/release",
    response_model=CollectionOut,
    summary="Publica a coleta para o cliente",
)
def release_collection(
    collection_id: str,
    principal: Principal = Depends(require_platform_in_tenant(rbac.COLLECTION_MANAGE)),
    session: Session = Depends(get_session),
) -> CollectionOut:
    """Torna a coleta visível no console do cliente.

    Não é automático: alguém da ValTexa afirma que o resultado está apresentável.
    Uma coleta inteira sem modelo chegaria ao produtor como uma tela vazia.
    """
    coleta = get_scoped(session, Collection, collection_id, principal)
    try:
        collections.release(session, coleta, actor=principal.user)
    except collections.CollectionError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    session.commit()
    return _collection_out(session, coleta)


# ---------------------------------------------------------------------------
# Fila
# ---------------------------------------------------------------------------


@router.get("/jobs", response_model=list[JobOut], summary="Fila de processamento")
def list_jobs(
    state: JobState | None = None,
    limit: int = Query(default=100, le=500),
    principal: Principal = Depends(require_platform_in_tenant(rbac.COLLECTION_MANAGE)),
    session: Session = Depends(get_session),
) -> list[JobOut]:
    consulta = scoped(select(ProcessingJob), ProcessingJob, principal)
    if state is not None:
        consulta = consulta.where(ProcessingJob.state == state.value)
    linhas = session.scalars(consulta.order_by(ProcessingJob.created_at.desc()).limit(limit))
    return [_job_out(linha) for linha in linhas]


@router.post("/jobs/{job_id}/retry", response_model=JobOut, summary="Tenta o trabalho de novo")
def retry_job(
    job_id: str,
    principal: Principal = Depends(require_platform_in_tenant(rbac.COLLECTION_MANAGE)),
    session: Session = Depends(get_session),
) -> JobOut:
    """Devolve um trabalho falho à fila, zerando as tentativas.

    Zerar é intencional: quem clica está afirmando que a causa foi tratada.
    """
    job = get_scoped(session, ProcessingJob, job_id, principal)
    jobs.requeue(job)
    session.commit()
    return _job_out(job)


# ---------------------------------------------------------------------------
# Catálogo de modelos e dataset
# ---------------------------------------------------------------------------


@router.get("/models/catalog", response_model=list[CatalogModelOut], summary="Catálogo ValTexa-B")
def model_catalog(
    _: PlatformCaller = Depends(require_platform(rbac.PLATFORM_MODEL_READ)),
    session: Session = Depends(get_session),
) -> list[CatalogModelOut]:
    """O que existe, e o que existe **só de nome** — uma linha por modelo, do registry.

    A coluna que importa é ``trained``. ``aerial-canopy`` aparece aqui como não
    treinado porque é o que ele é: sem isso, o painel daria a entender que a
    plataforma analisa imagem aérea hoje. A versão completa, com estados e
    métricas, está em ``GET /v1/platform/models``.
    """
    por_chave: dict[str, ModelVersion] = {}
    for linha in session.scalars(
        select(ModelVersion)
        .where(ModelVersion.state != ModelVersionState.DESCONTINUADO)
        .order_by(ModelVersion.model_key, ModelVersion.created_at)
    ):
        atual = por_chave.get(linha.model_key)
        if atual is None or linha.state is ModelVersionState.PRODUCAO:
            por_chave[linha.model_key] = linha
    return [
        CatalogModelOut(
            key=linha.model_key,
            crops=sorted(linha.crops or []),
            platform=linha.platform,
            trained=linha.state is not ModelVersionState.TREINAMENTO,
            caveat=linha.caveat or None,
        )
        for linha in por_chave.values()
    ]


@router.get("/models/versions", response_model=list[ModelVersionOut], summary="Versões de modelo")
def list_model_versions(
    _: PlatformCaller = Depends(require_platform(rbac.PLATFORM_MODEL_READ)),
    session: Session = Depends(get_session),
) -> list[ModelVersionOut]:
    """Atalho antigo do console; o registry completo é ``GET /v1/platform/models``."""
    from valtexa.api.routers.platform_ai import model_version_out

    linhas = session.scalars(select(ModelVersion).order_by(ModelVersion.created_at.desc()))
    return [model_version_out(linha) for linha in linhas]


@router.get("/datasets", response_model=list[DatasetOut], summary="Datasets proprietários")
def list_datasets(
    _: PlatformCaller = Depends(require_platform(rbac.DATASET_READ)),
    session: Session = Depends(get_session),
) -> list[DatasetOut]:
    linhas = session.scalars(select(Dataset).order_by(Dataset.key))
    saida = []
    for linha in linhas:
        resumo = dataset.summary(session, linha)
        saida.append(
            DatasetOut(
                id=linha.id,
                key=linha.key,
                name=linha.name,
                crop=linha.crop,
                platform=linha.platform,
                samples=resumo["samples"],
                candidates=resumo["candidates"],
                disagreements=resumo["disagreements"],
                sem_modelo=resumo["sem_modelo"],
                labels=resumo["labels"],
                versions=resumo["versions"],
            )
        )
    return saida


@router.get(
    "/datasets/{dataset_id}/samples",
    response_model=list[DatasetSampleOut],
    summary="Amostras do dataset",
)
def list_samples(
    dataset_id: str,
    limit: int = Query(default=200, le=1000),
    _: PlatformCaller = Depends(require_platform(rbac.DATASET_READ)),
    session: Session = Depends(get_session),
) -> list[DatasetSampleOut]:
    linhas = session.scalars(
        select(DatasetSample)
        .where(DatasetSample.dataset_id == dataset_id)
        .order_by(DatasetSample.created_at.desc())
        .limit(limit)
    )
    return [
        DatasetSampleOut(
            id=linha.id,
            dataset_id=linha.dataset_id,
            tenant_id=linha.tenant_id,
            asset_id=linha.asset_id,
            label=linha.label,
            machine_label=linha.machine_label,
            machine_confidence=linha.machine_confidence,
            disagreed=linha.disagreed,
            reviewer_label=linha.reviewer_label,
            reviewed_at=linha.reviewed_at,
            state=linha.state,
            collection_id=linha.collection_id,
        )
        for linha in linhas
    ]


@router.post(
    "/datasets/{dataset_id}/versions",
    response_model=DatasetVersionOut,
    status_code=status.HTTP_201_CREATED,
    summary="Congela um corte do dataset",
)
def freeze_dataset_version(
    dataset_id: str,
    payload: DatasetVersionCreate,
    principal: PlatformCaller = Depends(require_platform(rbac.DATASET_MANAGE)),
    session: Session = Depends(get_session),
) -> DatasetVersionOut:
    """Fecha um corte reproduzível — o que vai para o treino.

    A plataforma **não treina**. O que ela entrega é o conjunto exato, com a
    contagem por rótulo à vista, para que o treino aconteça no VALTEXA-B e a
    versão de modelo resultante possa apontar de volta para cá.
    """
    conjunto = session.get(Dataset, dataset_id)
    if conjunto is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Dataset não encontrado.")
    try:
        corte = dataset.freeze_version(
            session, conjunto, payload.version, notes=payload.notes, actor=principal.user
        )
    except dataset.DatasetError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    session.commit()
    return DatasetVersionOut(
        id=corte.id,
        dataset_id=corte.dataset_id,
        version=corte.version,
        sample_count=corte.sample_count,
        label_counts=corte.label_counts,
        notes=corte.notes,
        frozen_at=corte.frozen_at,
    )


@router.get(
    "/datasets/{dataset_id}/versions",
    response_model=list[DatasetVersionOut],
    summary="Cortes congelados",
)
def list_dataset_versions(
    dataset_id: str,
    _: PlatformCaller = Depends(require_platform(rbac.DATASET_READ)),
    session: Session = Depends(get_session),
) -> list[DatasetVersionOut]:
    linhas = session.scalars(
        select(DatasetVersion)
        .where(DatasetVersion.dataset_id == dataset_id)
        .order_by(DatasetVersion.created_at.desc())
    )
    return [
        DatasetVersionOut(
            id=linha.id,
            dataset_id=linha.dataset_id,
            version=linha.version,
            sample_count=linha.sample_count,
            label_counts=linha.label_counts,
            notes=linha.notes,
            frozen_at=linha.frozen_at,
        )
        for linha in linhas
    ]


# ---------------------------------------------------------------------------
# Planejamento de cobertura
# ---------------------------------------------------------------------------


@router.post(
    "/fields/{field_id}/relief",
    response_model=ReliefOut,
    summary="Mede o relevo do talhão e grava na leitura",
)
def read_relief(
    field_id: str,
    principal: Principal = Depends(require_platform_in_tenant(rbac.PLATFORM_FIELD_OPERATE)),
    session: Session = Depends(get_session),
) -> ReliefOut:
    """Amostra a altitude do talhão numa grade e guarda o resumo.

    Até aqui o planejamento tratava toda lavoura como plana. A diferença
    aparece em três lugares que custam dinheiro ou equipamento: a conta de
    autonomia (subir consome muito mais), o ângulo de tombamento, e a direção
    das passadas — curva de nível é mais segura e mais barata que subir e descer
    a encosta.

    **Sem fonte de elevação configurada, responde 501.** É deliberado: um zero
    devolvido aqui seria lido como "terreno plano" e entraria no plano com a
    autoridade de uma medição. Ver ``ELEVATION_URL`` em ``valtexa/config.py``.

    O resultado fica gravado junto da leitura de imagem do talhão, em
    ``field.terrain['relief']``, porque quem mede e quem usa estão em telas e
    momentos diferentes — e remedir a cada planejamento seria pagar a consulta
    de novo por um terreno que não mudou.
    """
    campo = get_scoped(session, Field, field_id, principal)
    if not campo.boundary:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "O talhão não tem contorno. Desenhe-o antes de medir o relevo.",
        )

    try:
        relevo = elevation.amostra(campo.boundary)
    except elevation.ElevationNotConfiguredError as exc:
        raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, str(exc)) from exc
    except elevation.ElevationUnavailableError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc

    campo.relief = relevo.as_dict()
    campo.relief_read_at = datetime.now(UTC)
    audit.record(
        session,
        tenant_id=campo.tenant_id,
        action="field.relief_measured",
        subject_type=SubjectType.FIELD,
        subject_id=campo.id,
        actor_type=ActorType.USER,
        actor_id=principal.user_id,
        actor_label=principal.user.email,
        payload=relevo.as_dict(),
    )
    session.commit()
    return _relief_out(relevo)


def _relief_out(relevo: elevation.Relevo) -> ReliefOut:
    return ReliefOut(
        **relevo.as_dict(),
        azimute_em_curva_de_nivel_deg=elevation.azimute_em_curva_de_nivel(relevo),
        avisos=elevation.avisos_de_relevo(relevo),
    )


@router.post(
    "/fields/{field_id}/plan",
    response_model=PlanOut,
    summary="Planeja a cobertura do talhão e diz onde precisa de poste",
)
def plan_field(
    field_id: str,
    payload: PlanRequest,
    principal: Principal = Depends(require_platform_ou_suporte(rbac.PLATFORM_FIELD_OPERATE)),
    session: Session = Depends(get_session),
) -> PlanOut:
    """Calcula rota, tempo, energia e a posição dos postes de recarga.

    É a conta que decide se um talhão é operável antes de mandar um rover de
    98 kg para dentro dele. Não escreve nada: planejar é pergunta, não ação, e
    o mesmo talhão é replanejado dezenas de vezes enquanto se escolhe a direção
    das linhas e a largura da faixa.

    O plano sai marcado como **estimativa** enquanto o consumo vier do datasheet.
    Ver ``valtexa/services/planner.py``.
    """
    campo = get_scoped(session, Field, field_id, principal)
    # O rascunho do editor (contorno e leitura ainda não salvos) vale sobre o gravado.
    contorno = payload.boundary or campo.boundary
    if not contorno:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "O talhão não tem polígono desenhado: sem contorno não há o que planejar.",
        )

    modelo = session.scalars(
        select(DeviceModel).where(DeviceModel.code == payload.device_model_code)
    ).first()
    if modelo is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"Modelo {payload.device_model_code!r} não está no catálogo de hardware.",
        )

    override: dict[str, float] = {}
    if payload.reserve_percent is not None:
        override["reserve_percent"] = payload.reserve_percent
    if payload.speed_ms is not None:
        override["speed_ms"] = payload.speed_ms
    perfil = planner.PerfilDeAutonomia.from_capabilities(
        Capabilities(raw=modelo.capabilities or {}), **override
    )

    # Os obstáculos que a rota vai contornar saem da leitura de imagem gravada
    # no talhão. Só os intransponíveis: carreador e solo exposto são caminho, e
    # tirá-los da rota faria o rover dar a volta para não pisar em chão batido.
    leitura = payload.terrain or (TerrainOut(**campo.terrain) if campo.terrain else None)
    contornar: list[list] = []
    if leitura is not None and leitura.resolution_ok:
        contornar = [
            objeto.outline
            for objeto in leitura.objects
            if not objeto.traversable and len(objeto.outline) >= 3
        ]

    try:
        plano = planner.plan(
            contorno,
            perfil,
            azimute_deg=payload.row_azimuth_deg,
            swath_m=payload.swath_m,
            bateria_inicial_percent=payload.start_battery_percent,
            obstaculos=contornar or None,
            margem_de_obstaculo_m=payload.obstacle_margin_m,
        )
    except (ValueError, geo.InvalidPolygonError) as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc

    avisos = list(plano.avisos)

    # O relevo gravado entra no plano com os avisos que ele gera. Sem isto, o
    # operador veria o tempo estimado de uma encosta de 18° com a mesma cara do
    # tempo estimado de uma várzea.
    relevo_out = None
    bruto = campo.relief
    if bruto:
        relevo_medido = elevation.Relevo(**bruto)
        relevo_out = _relief_out(relevo_medido)
        avisos.extend(relevo_out.avisos)
        se_em_nivel = relevo_out.azimute_em_curva_de_nivel_deg
        if se_em_nivel is not None and abs(
            ((plano.azimute_deg - se_em_nivel + 180.0) % 360.0) - 180.0
        ) > 25.0:
            avisos.append(
                f"As passadas correm a {plano.azimute_deg:.0f}°, e a curva de nível "
                f"deste talhão fica em {se_em_nivel:.0f}°. Subir e descer a encosta "
                "gasta mais bateria e é onde o rover tomba."
            )
    else:
        avisos.append(
            "Relevo não medido: a rota foi calculada como se o talhão fosse plano. "
            "A autonomia estimada não conta a subida."
        )
    operavel = None
    if leitura is not None and leitura.resolution_ok:
        operavel = leitura.operable_area_ha
    elif leitura is not None:
        avisos.append(
            "Há uma leitura de imagem deste talhão, mas ela não resolveu a rua de "
            "plantio — nada foi descontado da área e a rota não contorna nada. "
            "Para ler obstáculo é preciso ortomosaico de 3 a 10 cm por pixel."
        )

    return PlanOut(
        field_id=campo.id,
        field_name=campo.name,
        device_model_code=modelo.code,
        area_ha=plano.area_ha,
        swath_m=plano.swath_m,
        azimute_deg=plano.azimute_deg,
        velocidade_ms=plano.velocidade_ms,
        relief=relevo_out,
        passadas=plano.passadas,
        metros_de_linha=plano.metros_de_linha,
        metros_de_manobra=plano.metros_de_manobra,
        metros_totais=plano.metros_totais,
        minutos_dirigindo=plano.minutos_dirigindo,
        minutos_de_manobra=plano.minutos_de_manobra,
        minutos_de_recarga=plano.minutos_de_recarga,
        minutos_totais=plano.minutos_totais,
        horas_totais=round(plano.minutos_totais / 60.0, 2),
        wh_totais=plano.wh_totais,
        ha_por_hora=round(plano.ha_por_hora, 3),
        cargas=plano.cargas,
        postes=[
            ChargePostOut(
                ordem=poste.ordem,
                lat=poste.lat,
                lon=poste.lon,
                metros_no_percurso=poste.metros_no_percurso,
                bateria_na_chegada_percent=poste.bateria_na_chegada_percent,
                minutos_de_recarga=poste.minutos_de_recarga,
                area_coberta_ha=poste.area_coberta_ha,
                motivo=poste.motivo,
            )
            for poste in plano.postes
        ],
        rota=[[[lat, lon] for lat, lon in leg] for leg in plano.rota],
        perfil_medido=plano.perfil_medido,
        terrain=leitura,
        operable_area_ha=operavel,
        area_contornada_ha=plano.area_contornada_ha,
        avoided=len(contornar),
        avisos=avisos,
    )


@router.post(
    "/boundary/refine",
    response_model=BoundaryRefineOut,
    summary="Encaixa um contorno desenhado a mão no limite real do talhão",
)
def refine_boundary(
    payload: BoundaryRefineIn,
    _: object = Depends(
        require_platform_ou_suporte(rbac.PLATFORM_FIELD_OPERATE, exige_cliente=False)
    ),
) -> BoundaryRefineOut:
    """Manda o traço para o VALTEXA-B e devolve o contorno encaixado.

    O trabalho de imagem mora lá, com numpy e Pillow, e não aqui: a plataforma
    não carrega pilha de imagem de propósito — é o que permite escalar a API sem
    GPU. Aqui fica a autorização, o escopo de cliente e a conversão de área.

    Não escreve nada. Encaixar contorno é pergunta, e a mesma lavoura é
    redesenhada várias vezes até o produtor aprovar o traço.
    """
    # Primeiro o encaixe nos carreadores (talhão de café é polígono cercado de estrada
    # de terra); IA antiga, sem essa rota (404), cai no encaixe radial.
    base = settings.inference_url.rstrip("/")
    for metodo, caminho in (("carreador", "/encaixe-carreador"), ("radial", "/refine-boundary")):
        try:
            resposta = httpx.post(
                f"{base}{caminho}",
                json={
                    "polygon": payload.polygon,
                    "tolerance": payload.tolerance,
                    "vertices": payload.vertices,
                },
                headers=settings.inference_headers(),
                timeout=settings.inference_timeout_seconds * 3,
            )
        except httpx.HTTPError as exc:
            raise HTTPException(
                status.HTTP_502_BAD_GATEWAY,
                f"O serviço de imagem (VALTEXA-B) não respondeu: {exc}",
            ) from exc
        usado = metodo
        if resposta.status_code != status.HTTP_404_NOT_FOUND:
            break

    if resposta.status_code >= 400:
        detalhe = "erro sem corpo"
        try:
            detalhe = resposta.json().get("detail", detalhe)
        except ValueError:
            detalhe = resposta.text[:400]
        raise HTTPException(resposta.status_code, f"VALTEXA-B: {detalhe}")

    corpo = resposta.json()
    anel = corpo["polygon"]
    ruas = corpo.get("rows")
    area = round(geo.area_ha(anel), 4)
    return BoundaryRefineOut(
        polygon=anel,
        area_ha=area,
        area_change=corpo["area_change"],
        confidence=corpo["confidence"],
        hit_limit=corpo["hit_limit"],
        meters_per_pixel=corpo["meters_per_pixel"],
        rows=RowsOut(**ruas) if ruas else None,
        terrain=_terreno_out(corpo.get("terrain"), area),
        notes=corpo.get("notes", []),
        method=usado,
    )


def _terreno_out(bruto: dict | None, area_ha: float) -> TerrainOut | None:
    """Traduz a leitura de terreno do VALTEXA-B e aplica a área do contorno.

    A área operável é calculada **aqui** e não lá porque só a plataforma sabe a
    área real do talhão em hectares: o serviço de imagem conhece frações e
    pixels, não o polígono em graus que virou hectare. Multiplicar a fração pela
    área do contorno é a conversão, e ela vive do lado que tem os dois números.
    """
    if not bruto:
        return None

    operavel = None
    if bruto.get("resolution_ok"):
        util = bruto.get("crop_fraction", 0.0) + bruto.get("path_fraction", 0.0)
        operavel = round(area_ha * util, 4)

    return TerrainOut(
        resolution_ok=bruto["resolution_ok"],
        description=bruto["description"],
        crop_fraction=bruto["crop_fraction"],
        obstacle_fraction=bruto["obstacle_fraction"],
        path_fraction=bruto["path_fraction"],
        operable_area_ha=operavel,
        row_spacing_px=bruto.get("row_spacing_px"),
        cover_fractions=(bruto.get("cover") or {}).get("fractions", {}),
        objects=[TerrainObjectOut(**objeto) for objeto in bruto.get("objects", [])],
        heuristic=bruto.get("heuristic", True),
    )


# ---------------------------------------------------------------------------
# Fase futura
# ---------------------------------------------------------------------------


@router.post(
    "/drone-missions",
    response_model=Message,
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
    summary="Missão aérea autônoma — NÃO IMPLEMENTADO",
)
def drone_mission_not_implemented(
    _: PlatformCaller = Depends(require_platform(rbac.PLATFORM_FIELD_OPERATE)),
) -> Message:
    """Recusa explícita, para a ausência aparecer.

    O drone próprio da ValTexa é fase futura: não há planejamento de voo, não há
    navegação, não há transmissão automática. Esta rota existe para que a
    integração futura tenha um lugar combinado e para que quem procurar por ela
    hoje receba um ``501`` em vez de encontrar uma tela que finge funcionar.

    O caminho implementado para imagem aérea é o voo do operador terceirizado
    seguido de ``POST /v1/admin/collections``.
    """
    raise HTTPException(
        status.HTTP_501_NOT_IMPLEMENTED,
        "Missão aérea autônoma não faz parte do MVP. O caminho implementado para "
        "imagem aérea é a coleta manual: POST /v1/admin/collections.",
    )


# ---------------------------------------------------------------------------
# Serializadores
# ---------------------------------------------------------------------------


def _collection_out(session: Session, coleta: Collection) -> CollectionOut:
    farm = session.get(Farm, coleta.farm_id)
    field = session.get(Field, coleta.field_id)
    return CollectionOut(
        id=coleta.id,
        code=coleta.code,
        tenant_id=coleta.tenant_id,
        farm_id=coleta.farm_id,
        farm_name=farm.name if farm else None,
        field_id=coleta.field_id,
        field_name=field.name if field else None,
        crop=field.crop if field else None,
        collected_on=coleta.collected_on,
        source=coleta.source,
        kind=coleta.kind,
        platform=coleta.platform,
        state=coleta.state,
        operator_name=coleta.operator_name,
        notes=coleta.notes,
        model_key=coleta.model_key,
        no_model_reason=coleta.no_model_reason,
        progress=collections.progress(coleta),
        created_at=coleta.created_at,
        upload_completed_at=coleta.upload_completed_at,
        processing_finished_at=coleta.processing_finished_at,
        released_at=coleta.released_at,
    )


def _file_out(session: Session, arquivo: CollectionFile) -> CollectionFileOut:
    diagnostico = None
    if arquivo.observation_id:
        diagnostico = session.scalars(
            select(Diagnosis)
            .where(Diagnosis.observation_id == arquivo.observation_id)
            .order_by(Diagnosis.created_at.desc())
            .limit(1)
        ).first()
    return CollectionFileOut(
        id=arquivo.id,
        filename=arquivo.filename,
        content_type=arquivo.content_type,
        size_bytes=arquivo.size_bytes,
        received_bytes=arquivo.received_bytes,
        state=arquivo.state,
        sha256=arquivo.sha256,
        error=arquivo.error,
        captured_at=arquivo.captured_at,
        lat=arquivo.lat,
        lon=arquivo.lon,
        asset_id=arquivo.asset_id,
        observation_id=arquivo.observation_id,
        diagnosis_id=diagnostico.id if diagnostico else None,
        label=diagnostico.label if diagnostico else None,
        reviewed_label=diagnostico.reviewed_label if diagnostico else None,
        confidence=diagnostico.confidence if diagnostico else None,
    )


def _job_out(job: ProcessingJob) -> JobOut:
    return JobOut(
        id=job.id,
        kind=job.kind,
        state=job.state,
        subject_type=job.subject_type,
        subject_id=job.subject_id,
        attempts=job.attempts,
        max_attempts=job.max_attempts,
        progress_done=job.progress_done,
        progress_total=job.progress_total,
        last_error=job.last_error,
        locked_by=job.locked_by,
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
    )
