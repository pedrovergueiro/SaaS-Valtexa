"""Fazendas, talhões e zonas."""

from __future__ import annotations

from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, object_session

from valtexa.api.deps import Principal, get_scoped, require, scoped
from valtexa.db import get_session
from valtexa.models import ActorType, CapturePlatform, Farm, Field, SubjectType, Zone
from valtexa.schemas import (
    AiModelChoiceOut,
    FarmCreate,
    FarmOut,
    FarmUpdate,
    FieldAiModelUpdate,
    FieldBoundaryUpdate,
    FieldCreate,
    FieldOut,
    FieldUpdate,
    ZoneCreate,
    ZoneOut,
)
from valtexa.security import rbac
from valtexa.services import ai_pipeline, audit, documentos, geo, plans

router = APIRouter(tags=["fazendas"])


@router.get("/farms", response_model=list[FarmOut], summary="Lista as fazendas")
def list_farms(
    principal: Principal = Depends(require(rbac.FARM_READ)),
    session: Session = Depends(get_session),
) -> list[FarmOut]:
    farms = list(session.scalars(scoped(select(Farm).order_by(Farm.name), Farm, principal)))
    counts = dict(
        session.execute(
            scoped(
                select(Field.farm_id, func.count(Field.id)).group_by(Field.farm_id),
                Field,
                principal,
            )
        ).all()
    )
    _audita_documento_completo(session, principal, farms)
    return [_farm_out(farm, counts.get(farm.id, 0), principal) for farm in farms]


@router.post(
    "/farms",
    response_model=FarmOut,
    status_code=status.HTTP_201_CREATED,
    summary="Cadastra uma fazenda",
)
def create_farm(
    payload: FarmCreate,
    principal: Principal = Depends(require(rbac.FARM_MANAGE)),
    session: Session = Depends(get_session),
) -> FarmOut:
    plans.exigir(session, principal.tenant_id, "farms")
    farm = Farm(tenant_id=principal.tenant_id, **payload.model_dump())
    session.add(farm)
    audit.record(
        session,
        tenant_id=principal.tenant_id,
        action="farm.created",
        subject_type=SubjectType.FIELD,
        subject_id=farm.id,
        actor_type=ActorType.USER,
        actor_id=principal.user_id,
        actor_label=principal.user.email,
    )
    session.commit()
    return _farm_out(farm, 0, principal)


@router.patch("/farms/{farm_id}", response_model=FarmOut, summary="Altera uma propriedade")
def update_farm(
    farm_id: str,
    payload: FarmUpdate,
    principal: Principal = Depends(require(rbac.FARM_MANAGE)),
    session: Session = Depends(get_session),
) -> FarmOut:
    """Corrige o cadastro de uma propriedade, inclusive a localização.

    Mover a fazenda é a alteração que mais precisa de rastro: a coordenada é o
    que centra o mapa, e é dela que sai a imagem de satélite sobre a qual alguém
    vai desenhar o contorno do talhão. Uma fazenda cadastrada 40 km ao lado
    produz um contorno bonito sobre o mato de outra pessoa.

    Por isso o antes e o depois vão para a auditoria, e não só o depois.
    """
    fazenda = get_scoped(session, Farm, farm_id, principal)
    talhoes = session.scalar(
        select(func.count(Field.id)).where(Field.farm_id == fazenda.id)
    )
    mudancas = payload.model_dump(exclude_unset=True)
    if not mudancas:
        return _farm_out(fazenda, talhoes or 0, principal)

    antes = {campo: getattr(fazenda, campo) for campo in mudancas}
    for campo, valor in mudancas.items():
        setattr(fazenda, campo, valor)

    mudou_de_lugar = any(
        campo in mudancas for campo in ("center_lat", "center_lon", "base_lat", "base_lon")
    )
    audit.record(
        session,
        tenant_id=principal.tenant_id,
        action="farm.moved" if mudou_de_lugar else "farm.updated",
        subject_type=SubjectType.FIELD,
        subject_id=fazenda.id,
        actor_type=ActorType.USER,
        actor_id=principal.user_id,
        actor_label=principal.user.email,
        old_state=(
            f"{antes.get('center_lat')},{antes.get('center_lon')}" if mudou_de_lugar else None
        ),
        new_state=(
            f"{fazenda.center_lat},{fazenda.center_lon}" if mudou_de_lugar else None
        ),
        payload={"antes": _sem_documento(antes), "depois": _sem_documento(mudancas)},
    )
    session.commit()
    return _farm_out(fazenda, talhoes or 0, principal)


@router.get("/farms/{farm_id}/fields", response_model=list[FieldOut], summary="Talhões")
def list_fields(
    farm_id: str,
    principal: Principal = Depends(require(rbac.FARM_READ)),
    session: Session = Depends(get_session),
) -> list[FieldOut]:
    get_scoped(session, Farm, farm_id, principal)
    rows = session.scalars(
        scoped(select(Field).where(Field.farm_id == farm_id).order_by(Field.name), Field, principal)
    )
    return [_field_out(row) for row in rows]


@router.post(
    "/farms/{farm_id}/fields",
    response_model=FieldOut,
    status_code=status.HTTP_201_CREATED,
    summary="Cadastra um talhão",
)
def create_field(
    farm_id: str,
    payload: FieldCreate,
    principal: Principal = Depends(require(rbac.FARM_MANAGE)),
    session: Session = Depends(get_session),
) -> FieldOut:
    """Cria o talhão e calcula a área a partir do limite.

    A área é derivada, e não informada: um número digitado à mão divergiria do
    polígono, e é ele que manda na dose e na cerca virtual.
    """
    get_scoped(session, Farm, farm_id, principal)
    _validate_polygon(payload.boundary, "boundary")
    _validate_ai_model(session, principal.tenant_id, payload.crop, payload.ai_model)
    _confere_fileiras(payload.validation_rows, payload.row_count)
    plans.exigir(session, principal.tenant_id, "fields")
    plans.exigir(
        session, principal.tenant_id, "hectares", acrescimo=geo.area_ha(payload.boundary)
    )

    row = Field(
        tenant_id=principal.tenant_id,
        farm_id=farm_id,
        area_ha=round(geo.area_ha(payload.boundary), 4),
        **payload.model_dump(),
    )
    session.add(row)
    audit.record(
        session,
        tenant_id=principal.tenant_id,
        action="field.created",
        subject_type=SubjectType.FIELD,
        subject_id=row.id,
        actor_type=ActorType.USER,
        actor_id=principal.user_id,
        actor_label=principal.user.email,
        payload={"area_ha": row.area_ha, "crop": row.crop},
    )
    session.commit()
    return _field_out(row)


@router.get(
    "/fields/{field_id}/ai-models",
    response_model=list[AiModelChoiceOut],
    summary="Versões do modelo de diagnóstico para a cultura do talhão",
)
def list_field_ai_models(
    field_id: str,
    principal: Principal = Depends(require(rbac.FARM_READ)),
    session: Session = Depends(get_session),
) -> list[AiModelChoiceOut]:
    """As versões que atendem este talhão, a recomendada primeiro.

    Como escolher entre os modelos de um assistente: cada versão com o número de
    campo e a licença dos dados de treino. Banana e citros têm a de ``campo``
    (mais precisa, com dado não comercial) e a ``comercial`` (só CC BY).
    """
    row = get_scoped(session, Field, field_id, principal)
    in_use = _model_in_use(row)
    versions = ai_pipeline.versions_for_crop(
        session, row.crop, CapturePlatform.GROUND, tenant_id=principal.tenant_id
    )
    return [
        AiModelChoiceOut(
            key=modelo.model_key,
            name=modelo.name,
            version=modelo.version,
            variant=modelo.variant,
            recommended=modelo.recommended,
            license=modelo.license or "",
            field_performance=_desempenho_operacional(modelo.metrics),
            caveat=modelo.caveat or None,
            selected=modelo.model_key == in_use,
        )
        for modelo in versions
    ]


def _desempenho_operacional(metricas: dict | None) -> str | None:
    """A acurácia de campo dita como o produtor decide, sem o número (brief, seção 10)."""
    valor = (metricas or {}).get("field_accuracy")
    if not isinstance(valor, int | float):
        return None
    if valor >= 0.9:
        return "alto: acerta a grande maioria das folhas no campo"
    if valor >= 0.75:
        return "bom: confira com o agrônomo os casos duvidosos"
    return "limitado: serve de triagem; o agrônomo confirma cada caso"


@router.put(
    "/fields/{field_id}/ai-model",
    response_model=FieldOut,
    summary="Escolhe a versão do modelo de diagnóstico do talhão",
)
def set_field_ai_model(
    field_id: str,
    payload: FieldAiModelUpdate,
    principal: Principal = Depends(require(rbac.FARM_MANAGE)),
    session: Session = Depends(get_session),
) -> FieldOut:
    """Vale para as próximas imagens — rover e coleta. As já analisadas não mudam."""
    row = get_scoped(session, Field, field_id, principal)
    _validate_ai_model(session, principal.tenant_id, row.crop, payload.ai_model)
    before = row.ai_model
    row.ai_model = payload.ai_model
    audit.record(
        session,
        tenant_id=principal.tenant_id,
        action="field.ai_model_changed",
        subject_type=SubjectType.FIELD,
        subject_id=row.id,
        actor_type=ActorType.USER,
        actor_id=principal.user_id,
        actor_label=principal.user.email,
        payload={"from": before, "to": payload.ai_model},
    )
    session.commit()
    return _field_out(row)


@router.get("/fields", response_model=list[FieldOut], summary="Todos os talhões do cliente")
def list_all_fields(
    principal: Principal = Depends(require(rbac.FARM_READ)),
    session: Session = Depends(get_session),
) -> list[FieldOut]:
    """Os talhões de todas as fazendas — o que o mapa pinta de uma vez."""
    rows = session.scalars(scoped(select(Field).order_by(Field.name), Field, principal))
    return [_field_out(row) for row in rows]


@router.get("/fields/{field_id}", response_model=FieldOut, summary="Um talhão")
def get_field(
    field_id: str,
    principal: Principal = Depends(require(rbac.FARM_READ)),
    session: Session = Depends(get_session),
) -> FieldOut:
    return _field_out(get_scoped(session, Field, field_id, principal))


@router.patch("/fields/{field_id}", response_model=FieldOut, summary="Configura um talhão")
def update_field(
    field_id: str,
    payload: FieldUpdate,
    principal: Principal = Depends(require(rbac.FARM_MANAGE)),
    session: Session = Depends(get_session),
) -> FieldOut:
    """Variedade, estágio, espaçamentos, número de linhas, fileiras de validação, observações.

    Só o que vier no corpo muda; ``null`` explícito apaga o valor. O antes e o
    depois vão para a auditoria: espaçamento muda a contagem de plantas da
    fusão, e uma fileira de validação trocada muda o que se mede no campo.
    """
    campo = get_scoped(session, Field, field_id, principal)
    mudancas = payload.model_dump(exclude_unset=True)
    if "validation_rows" in mudancas and mudancas["validation_rows"] is None:
        mudancas["validation_rows"] = []
    linhas = mudancas.get("row_count", campo.row_count)
    fileiras = mudancas.get("validation_rows", campo.validation_rows or [])
    _confere_fileiras(fileiras, linhas)

    antes = {campo_: _json(getattr(campo, campo_)) for campo_ in mudancas}
    for nome, valor in mudancas.items():
        setattr(campo, nome, valor)
    audit.record(
        session,
        tenant_id=principal.tenant_id,
        action="field.updated",
        subject_type=SubjectType.FIELD,
        subject_id=campo.id,
        actor_type=ActorType.USER,
        actor_id=principal.user_id,
        actor_label=principal.user.email,
        payload={"antes": antes, "depois": {k: _json(v) for k, v in mudancas.items()}},
    )
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Já existe talhão com este nome nesta fazenda."
        ) from exc
    return _field_out(campo)


def _confere_fileiras(fileiras: list[int], linhas: int | None) -> None:
    if linhas is not None and any(numero > linhas for numero in fileiras):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"Fileira de validação além do número de linhas do talhão ({linhas}).",
        )


def _json(valor: object) -> object:
    return valor.isoformat() if isinstance(valor, date) else valor


@router.patch(
    "/fields/{field_id}/boundary",
    response_model=FieldOut,
    summary="Redesenha o contorno do talhão",
)
def update_boundary(
    field_id: str,
    payload: FieldBoundaryUpdate,
    principal: Principal = Depends(require(rbac.FARM_MANAGE)),
    session: Session = Depends(get_session),
) -> FieldOut:
    """Grava um contorno novo e recalcula a área.

    O contorno é a base de tudo o que vem depois — cerca virtual, cobertura,
    planejamento de rota, posição de poste. Por isso a mudança fica na
    auditoria com o antes e o depois: um talhão que encolheu 3 ha entre uma
    missão e outra precisa ter explicação.
    """
    campo = get_scoped(session, Field, field_id, principal)
    antes = {"area_ha": campo.area_ha, "vertices": len(campo.boundary or [])}
    # Guardado antes da atribuição, e não depois: comparar `campo.boundary` com
    # `payload.boundary` embaixo compararia o valor novo consigo mesmo, e a
    # comparação sempre daria "igual".
    contorno_anterior = [list(ponto) for ponto in (campo.boundary or [])]

    area_nova = round(geo.area_ha(payload.boundary), 4)
    if area_nova > (campo.area_ha or 0):
        # Só o que cresce conta contra o limite de hectares do plano.
        plans.exigir(
            session, principal.tenant_id, "hectares", acrescimo=area_nova - (campo.area_ha or 0)
        )
    campo.boundary = payload.boundary
    campo.area_ha = area_nova
    if payload.row_azimuth_deg is not None:
        campo.row_azimuth_deg = payload.row_azimuth_deg

    # A leitura de terreno vale para o contorno com que foi feita. Gravá-la aqui
    # é o que a mantém coerente; um terreno lido sobre outro polígono descreveria
    # outro pedaço de chão. Contorno novo sem leitura junto apaga a anterior pelo
    # mesmo motivo — guardá-la seria manter no banco a medida de um talhão que
    # não existe mais.
    if payload.terrain is not None:
        campo.terrain = payload.terrain.model_dump(mode="json")
        campo.terrain_read_at = datetime.now(UTC)
    else:
        campo.terrain = None
        campo.terrain_read_at = None

    # O relevo cai pelo mesmo motivo que a leitura, e só por ele: o contorno
    # mudou, então o pedaço de chão medido é outro. Uma releitura de imagem
    # sobre o **mesmo** contorno não o derruba — apagá-lo ali obrigaria a pagar
    # a consulta de DEM de novo por um terreno que continua o mesmo.
    if contorno_anterior != payload.boundary:
        campo.relief = None
        campo.relief_read_at = None

    audit.record(
        session,
        tenant_id=principal.tenant_id,
        action="field.boundary_updated",
        subject_type=SubjectType.FIELD,
        subject_id=campo.id,
        actor_type=ActorType.USER,
        actor_id=principal.user_id,
        actor_label=principal.user.email,
        old_state=f"{antes['area_ha']} ha",
        new_state=f"{campo.area_ha} ha",
        payload={
            "antes": antes,
            "depois": {
                "area_ha": campo.area_ha,
                "vertices": len(payload.boundary),
                "terreno_lido": payload.terrain is not None,
                "area_operavel_ha": (
                    payload.terrain.operable_area_ha if payload.terrain else None
                ),
            },
        },
    )
    session.commit()
    return _field_out(campo)


@router.get("/fields/{field_id}/zones", response_model=list[ZoneOut], summary="Zonas do talhão")
def list_zones(
    field_id: str,
    principal: Principal = Depends(require(rbac.FARM_READ)),
    session: Session = Depends(get_session),
) -> list[ZoneOut]:
    get_scoped(session, Field, field_id, principal)
    rows = session.scalars(
        scoped(select(Zone).where(Zone.field_id == field_id).order_by(Zone.name), Zone, principal)
    )
    return [_zone_out(row) for row in rows]


@router.post(
    "/fields/{field_id}/zones",
    response_model=ZoneOut,
    status_code=status.HTTP_201_CREATED,
    summary="Cadastra uma zona de manejo",
)
def create_zone(
    field_id: str,
    payload: ZoneCreate,
    principal: Principal = Depends(require(rbac.FARM_MANAGE)),
    session: Session = Depends(get_session),
) -> ZoneOut:
    """A zona precisa caber no talhão.

    Uma zona que vaza para fora abriria um caminho para autorizar aplicação
    além do limite — a checagem de cerca virtual do safety engine parte da
    geometria cadastrada aqui.
    """
    field_row = get_scoped(session, Field, field_id, principal)
    _validate_polygon(payload.boundary, "boundary")

    if not geo.polygon_contains_polygon(field_row.boundary, payload.boundary):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "A zona precisa estar contida no limite do talhão.",
        )

    zone = Zone(
        tenant_id=principal.tenant_id,
        field_id=field_id,
        area_ha=round(geo.area_ha(payload.boundary), 4),
        **payload.model_dump(),
    )
    session.add(zone)
    session.commit()
    return _zone_out(zone)


def _validate_polygon(polygon: list, field_name: str) -> None:
    try:
        geo.as_points(polygon)
    except geo.InvalidPolygonError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"{field_name}: {exc}"
        ) from exc


def _documento_completo(principal: Principal | None) -> bool:
    """CPF/CNPJ inteiro só para quem pode alterar o cadastro da fazenda (decisão do Pedro).

    Sem ``principal`` (uso interno) o documento sai mascarado: o padrão é esconder.
    """
    return principal is not None and principal.can(rbac.FARM_MANAGE)


def _equipe_interna(principal: Principal) -> bool:
    return principal.is_support or principal.via_platform or principal.platform_role is not None


def _audita_documento_completo(
    session: Session, principal: Principal, fazendas: list[Farm]
) -> None:
    """Toda leitura do CPF/CNPJ completo por alguém da ValTexa vira linha na trilha.

    A sessão de suporte já grava cada requisição; esta linha diz *o quê* foi
    visto — quais fazendas tiveram o documento revelado — para o cliente saber.
    """
    if not _documento_completo(principal) or not _equipe_interna(principal):
        return
    reveladas = [fazenda.id for fazenda in fazendas if fazenda.owner_document]
    if not reveladas:
        return
    audit.record(
        session,
        tenant_id=principal.tenant_id,
        action="farm.owner_document_viewed",
        subject_type=SubjectType.FIELD,
        subject_id=reveladas[0],
        actor_type=ActorType.USER,
        actor_id=principal.user_id,
        actor_label=principal.user.email,
        payload={"farm_ids": reveladas},
    )
    session.commit()


def _sem_documento(valores: dict) -> dict:
    """A trilha guarda só o fim do CPF/CNPJ: ela não se apaga, e o documento vive na fazenda."""
    if "owner_document" not in valores:
        return valores
    return {
        **valores,
        "owner_document": documentos.mascarar_cpf_cnpj(valores["owner_document"]),
    }


def _farm_out(farm: Farm, field_count: int, principal: Principal | None = None) -> FarmOut:
    completo = _documento_completo(principal)
    mascarado = bool(farm.owner_document) and not completo
    return FarmOut(
        id=farm.id,
        name=farm.name,
        timezone=farm.timezone,
        center_lat=farm.center_lat,
        center_lon=farm.center_lon,
        base_lat=farm.base_lat,
        base_lon=farm.base_lon,
        area_ha=farm.area_ha,
        owner_name=farm.owner_name,
        owner_document=(
            farm.owner_document if completo else documentos.mascarar_cpf_cnpj(farm.owner_document)
        ),
        owner_document_masked=mascarado,
        city=farm.city,
        state=farm.state,
        main_crop=farm.main_crop,
        car_code=farm.car_code,
        technical_lead=farm.technical_lead,
        notes=farm.notes,
        fields=field_count,
    )


def _validate_ai_model(
    session: Session, tenant_id: str, crop: str, ai_model: str | None
) -> None:
    """Recusa uma versão que não atende a cultura — 422 com as que atendem."""
    if ai_model is None:
        return
    try:
        ai_pipeline.resolve_model(
            session, crop, CapturePlatform.GROUND, ai_model, tenant_id=tenant_id
        )
    except ai_pipeline.NoModelForCaptureError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc


def _model_in_use(row: Field) -> str | None:
    sessao = object_session(row)
    if sessao is None:
        return None
    try:
        return ai_pipeline.resolve_model(
            sessao, row.crop, CapturePlatform.GROUND, row.ai_model,
            tenant_id=row.tenant_id,
        )
    except ai_pipeline.NoModelForCaptureError:
        return None


def _field_out(row: Field) -> FieldOut:
    return FieldOut(
        id=row.id,
        farm_id=row.farm_id,
        name=row.name,
        crop=row.crop,
        variety=row.variety,
        ai_model=row.ai_model,
        ai_model_in_use=_model_in_use(row),
        crop_stage=row.crop_stage,
        planted_on=row.planted_on,
        row_spacing_m=row.row_spacing_m,
        row_azimuth_deg=row.row_azimuth_deg,
        plant_spacing_m=row.plant_spacing_m,
        row_count=row.row_count,
        validation_rows=list(row.validation_rows or []),
        notes=row.notes,
        area_ha=row.area_ha,
        boundary=row.boundary,
        terrain=row.terrain,
        terrain_read_at=row.terrain_read_at,
        relief=row.relief,
        relief_read_at=row.relief_read_at,
    )


def _zone_out(row: Zone) -> ZoneOut:
    return ZoneOut(
        id=row.id, field_id=row.field_id, name=row.name, area_ha=row.area_ha, boundary=row.boundary
    )
