"""Dataset proprietário: o que a operação deixa para trás.

Toda vez que um agrônomo escreve um rótulo numa imagem, nasce uma amostra que
nenhum dataset público tem — com a cultura certa, o estágio certo, a câmera
certa e, no caso que mais importa, um nome que o modelo não conhece. Este módulo
é o caminho dessa amostra: da revisão para o conjunto, do conjunto para o corte,
do corte para o treino.

**Uma revisão vira uma amostra, não um treino.** Reagir a cada correção seria o
mesmo erro que a plataforma evita no resto do fluxo: deixar um dado isolado
mandar sozinho. A amostra entra como ``CANDIDATE``; o treino roda sobre um corte
fechado por alguém, com data e contagem por rótulo.

**Só entra amostra de cliente que autorizou** (brief, seção 32): consentimento
SIM vigente, registrado em :mod:`valtexa.services.consent`. Sem decisão, é NÃO.
A verificação acontece duas vezes — quando a revisão vira amostra e quando o
corte é congelado —, porque o consentimento pode ser revogado no meio.

**O conjunto é escolhido pela pergunta, não pelo cliente.** Café de solo e café
aéreo não entram no mesmo dataset: são perguntas diferentes, com modelos
diferentes. O ``tenant_id`` viaja na amostra para rastreabilidade e para atender
pedido de exclusão, mas não separa conjuntos — a soma dos clientes é justamente
o que dá volume ao dataset.
"""

from __future__ import annotations

import logging
from collections import Counter
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from valtexa.models import (
    ActorType,
    CapturePlatform,
    Collection,
    Dataset,
    DatasetSample,
    DatasetSampleState,
    DatasetVersion,
    Diagnosis,
    Observation,
    SubjectType,
    User,
)
from valtexa.services import audit, consent, ensino, events

logger = logging.getLogger(__name__)


class DatasetError(RuntimeError):
    """Falha de uso do serviço de dataset. Vira 4xx na API."""


def dataset_key(session: Session, crop: str, platform: CapturePlatform) -> str:
    """Chave do conjunto para uma cultura numa plataforma de captura.

    Quando existe modelo treinado, a chave é a dele: as amostras novas vão
    engrossar exatamente o conjunto que treinou aquele modelo. Quando não existe
    — imagem aérea, hoje —, a chave é descritiva, e é esse conjunto que precisa
    encher antes de o modelo existir.
    """
    from valtexa.services.ai_pipeline import NoModelForCaptureError, resolve_model

    try:
        return resolve_model(session, crop, platform)
    except NoModelForCaptureError:
        return f"{(crop or 'desconhecido').strip().lower()}-{platform.value}"


def ensure_dataset(session: Session, crop: str, platform: CapturePlatform) -> Dataset:
    """O conjunto para esta cultura e plataforma, criando-o na primeira amostra."""
    key = dataset_key(session, crop, platform)
    existente = session.scalars(select(Dataset).where(Dataset.key == key)).first()
    if existente is not None:
        return existente

    conjunto = Dataset(
        key=key,
        name=f"{crop or 'desconhecido'} · {platform.value}",
        crop=(crop or "desconhecido").strip().lower(),
        platform=platform,
        description=(
            "Criado na primeira anotação de agrônomo para esta combinação. "
            "As amostras vêm da operação, não de fonte pública."
        ),
    )
    session.add(conjunto)
    session.flush()
    return conjunto


def record_review(
    session: Session, diagnosis: Diagnosis, reviewer: User | None = None
) -> DatasetSample | None:
    """Transforma o veredito do agrônomo numa amostra do dataset.

    Devolve ``None`` quando não há o que guardar — diagnóstico sem imagem, ou
    revisão já registrada. Não faz *commit*.
    """
    if not diagnosis.reviewed_label:
        return None

    # Brief, seção 32: só dado de cliente que disse SIM entra no treino. A
    # revisão do agrônomo continua valendo para o diagnóstico dele; o que não
    # acontece é a imagem virar amostra.
    if not consent.permite_treino(session, diagnosis.tenant_id):
        logger.info(
            "Revisão do diagnóstico %s não vira amostra: o cliente %s não autorizou "
            "o uso dos dados em treino.",
            diagnosis.id,
            diagnosis.tenant_id,
        )
        return None

    observacao = session.get(Observation, diagnosis.observation_id)
    if observacao is None or observacao.image_asset_id is None:
        return None

    ja_existe = session.scalars(
        select(DatasetSample).where(DatasetSample.diagnosis_id == diagnosis.id)
    ).first()
    if ja_existe is not None:
        return ja_existe

    plataforma, cultura = _contexto(session, observacao)
    conjunto = ensure_dataset(session, cultura, plataforma)

    amostra = DatasetSample(
        dataset_id=conjunto.id,
        tenant_id=diagnosis.tenant_id,
        asset_id=observacao.image_asset_id,
        observation_id=observacao.id,
        diagnosis_id=diagnosis.id,
        collection_id=observacao.collection_id,
        label=diagnosis.reviewed_label,
        machine_label=diagnosis.label,
        machine_confidence=diagnosis.confidence,
        disagreed=bool(diagnosis.label) and diagnosis.label != diagnosis.reviewed_label,
        reviewer_id=reviewer.id if reviewer else diagnosis.reviewed_by,
        reviewer_label=reviewer.email if reviewer else None,
        reviewed_at=diagnosis.reviewed_at or datetime.now(UTC),
        notes=diagnosis.review_notes,
        state=DatasetSampleState.CANDIDATE,
    )
    session.add(amostra)
    session.flush()

    events.publish(
        session,
        events.DATASET_SAMPLE_ADDED,
        tenant_id=diagnosis.tenant_id,
        subject_type=SubjectType.DATASET,
        subject_id=conjunto.id,
        payload={
            "dataset": conjunto.key,
            "label": amostra.label,
            "machine_label": amostra.machine_label,
            "disagreed": amostra.disagreed,
            "sem_modelo": amostra.machine_label is None,
        },
    )
    return amostra


def _contexto(session: Session, observacao: Observation) -> tuple[CapturePlatform, str]:
    """Plataforma de captura e cultura de onde a imagem veio."""
    plataforma = CapturePlatform.GROUND
    if observacao.collection_id:
        coleta = session.get(Collection, observacao.collection_id)
        if coleta is not None:
            plataforma = coleta.platform
    campo = observacao.field if hasattr(observacao, "field") else None
    if campo is None:
        from valtexa.models import Field

        campo = session.get(Field, observacao.field_id)
    return plataforma, (campo.crop if campo else "")


def freeze_version(
    session: Session,
    conjunto: Dataset,
    version: str,
    *,
    notes: str | None = None,
    actor: User | None = None,
    politica: str = "um",
    confiabilidade_minima: float = 0.8,
    pares_minimos: int = 10,
) -> DatasetVersion:
    """Congela as amostras candidatas num corte reproduzível.

    ``politica`` (:data:`valtexa.services.ensino.POLITICAS`): o que basta para uma amostra
    entrar — um agrônomo, o consenso de dois, ou um agrônomo confiável. Amostra em disputa nunca
    entra; a que fica fora continua candidata para o próximo corte.

    Guarda a lista de identificadores, não um filtro por data: amostras podem
    ser excluídas depois, e um corte definido por consulta mudaria de conteúdo
    com o tempo — dois treinos com o mesmo nome deixariam de ser comparáveis.
    """
    if session.scalars(
        select(DatasetVersion).where(
            DatasetVersion.dataset_id == conjunto.id, DatasetVersion.version == version
        )
    ).first():
        raise DatasetError(f"A versão {version!r} já existe em {conjunto.key!r}.")

    candidatas = list(
        session.scalars(
            select(DatasetSample).where(
                DatasetSample.dataset_id == conjunto.id,
                DatasetSample.state != DatasetSampleState.EXCLUDED,
            )
        )
    )
    # Segunda barreira do consentimento: a amostra entrou com SIM, mas o corte
    # vale o consentimento de **hoje**. Quem revogou e por algum caminho ainda
    # tem amostra viva fica fora do corte.
    autorizados = consent.clientes_com_consentimento(
        session, {amostra.tenant_id for amostra in candidatas}
    )
    amostras = [amostra for amostra in candidatas if amostra.tenant_id in autorizados]
    try:
        amostras, criterio = ensino.escolher_para_o_corte(
            session, amostras, politica, confiabilidade_minima, pares_minimos)
    except ValueError as exc:
        raise DatasetError(str(exc)) from exc
    if not amostras:
        raise DatasetError(f"{conjunto.key!r} não tem amostra para congelar com a política "
                           f"{politica!r} (fora: {criterio['fora'] or 'nada'}).")

    corte = DatasetVersion(
        dataset_id=conjunto.id,
        version=version,
        sample_count=len(amostras),
        label_counts=dict(Counter(amostra.label for amostra in amostras)),
        sample_ids=[amostra.id for amostra in amostras],
        notes=notes,
        criterio=criterio,
        frozen_at=datetime.now(UTC),
        frozen_by=actor.id if actor else None,
    )
    session.add(corte)
    for amostra in amostras:
        amostra.state = DatasetSampleState.INCLUDED
    session.flush()

    audit.record(
        session,
        action="dataset.version_frozen",
        subject_type=SubjectType.DATASET_VERSION,
        subject_id=corte.id,
        actor_type=ActorType.USER if actor else ActorType.SYSTEM,
        actor_id=actor.id if actor else None,
        actor_label=actor.email if actor else None,
        new_state=version,
        payload={
            "dataset": conjunto.key,
            "samples": corte.sample_count,
            "labels": corte.label_counts,
            "criterio": criterio,
        },
    )
    events.publish(
        session,
        events.DATASET_VERSION_FROZEN,
        subject_type=SubjectType.DATASET_VERSION,
        subject_id=corte.id,
        payload={"dataset": conjunto.key, "version": version, "samples": corte.sample_count},
    )
    return corte


def summary(session: Session, conjunto: Dataset) -> dict:
    """Números do conjunto para o painel: quanto tem, de que rótulo, quanto é novo."""
    amostras = list(
        session.scalars(select(DatasetSample).where(DatasetSample.dataset_id == conjunto.id))
    )
    return {
        "key": conjunto.key,
        "crop": conjunto.crop,
        "platform": conjunto.platform.value,
        "samples": len(amostras),
        "candidates": sum(
            1 for a in amostras if a.state is DatasetSampleState.CANDIDATE
        ),
        "disagreements": sum(1 for a in amostras if a.disagreed),
        "sem_modelo": sum(1 for a in amostras if a.machine_label is None),
        "labels": dict(Counter(a.label for a in amostras)),
        "versions": len(conjunto.versions),
    }
