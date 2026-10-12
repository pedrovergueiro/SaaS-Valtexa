"""Processamento de uma coleta, fora da requisição.

É o que o worker faz com um :class:`~valtexa.models.collection.ProcessingJob` de
``collection_ingest``: pega os arquivos guardados, cria uma observação para cada
um e roda o pipeline de percepção — o mesmo pipeline do rover, com a mesma dupla
validação e a mesma fila do agrônomo. Uma imagem que entrou pelo painel não
recebe tratamento mais frouxo do que uma que entrou pelo rádio.

**Processa em lotes e devolve o controle.** Cada chamada de :func:`process_batch`
cuida de poucas dezenas de arquivos e faz *commit*. Uma coleta de 1.500 imagens
atravessa muitos ciclos do worker, e a barra de progresso do painel anda em cada
um. Processar tudo numa transação só significaria perder tudo num erro no
arquivo 1.499 — e nenhum progresso visível até lá.

**Sem modelo é um resultado, não um erro.** Quando não existe modelo treinado
para a cultura naquela plataforma de captura — o caso de hoje para qualquer
imagem aérea, ver ``VALTEXA-B/MODELS.md`` — os arquivos ficam em
``NO_MODEL``: guardados, catalogados, georreferenciados e disponíveis para o
agrônomo anotar. Não passam por classificador nenhum. É exatamente assim que o
dataset do ``aerial-canopy`` se forma.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from valtexa.models import (
    Agreement,
    Asset,
    Collection,
    CollectionFile,
    CollectionFileState,
    CollectionState,
    Diagnosis,
    DiagnosisStatus,
    Field,
    Observation,
    SubjectType,
)
from valtexa.services import ai_pipeline, audit, collections, consent, events, geo, storage

logger = logging.getLogger(__name__)

LOTE = 25
"""Arquivos por chamada. Segura o tempo de uma transação e o uso de memória."""


@dataclass(frozen=True, slots=True)
class BatchReport:
    """O que um lote fez. Alimenta o progresso do trabalho e o log."""

    processed: int = 0
    analyzed: int = 0
    needs_review: int = 0
    no_model: int = 0
    failed: int = 0
    finished: bool = False

    @property
    def any_work(self) -> bool:
        return self.processed > 0


def pending_files(session: Session, coleta: Collection, limit: int = LOTE) -> list[CollectionFile]:
    """Arquivos guardados que ainda não passaram pelo pipeline."""
    return list(
        session.scalars(
            select(CollectionFile)
            .where(
                CollectionFile.collection_id == coleta.id,
                CollectionFile.state == CollectionFileState.STORED,
            )
            .order_by(CollectionFile.created_at)
            .limit(limit)
        )
    )


def process_batch(session: Session, coleta: Collection, limit: int = LOTE) -> BatchReport:
    """Processa até ``limit`` arquivos. Não faz *commit*: quem chamou decide.

    A inferência do lote inteiro roda **antes** da primeira escrita. São
    minutos de HTTP para 25 imagens; com escrita pendente, a transação ficaria
    aberta esse tempo todo — no SQLite, o banco inteiro travado para a API.
    """
    arquivos = pending_files(session, coleta, limit)
    field = session.get(Field, coleta.field_id) if arquivos else None
    analisadores = ai_pipeline.default_analyzers() if coleta.model_key and arquivos else []
    previas = {
        arquivo.id: _analisar(session, coleta, field, arquivo, analisadores)
        for arquivo in (arquivos if analisadores else [])
    }

    if coleta.state is CollectionState.PROCESSING_QUEUED:
        coleta.state = CollectionState.AI_PROCESSING
        coleta.processing_started_at = datetime.now(UTC)
        if coleta.model_key is None:
            events.publish(
                session,
                events.COLLECTION_NO_MODEL,
                tenant_id=coleta.tenant_id,
                subject_type=SubjectType.COLLECTION,
                subject_id=coleta.id,
                payload={"code": coleta.code, "reason": coleta.no_model_reason},
            )

    if not arquivos:
        collections.settle(session, coleta)
        events.publish(
            session,
            events.COLLECTION_PROCESSED,
            tenant_id=coleta.tenant_id,
            subject_type=SubjectType.COLLECTION,
            subject_id=coleta.id,
            payload={
                "code": coleta.code,
                "analyzed": coleta.files_analyzed,
                "needs_review": coleta.files_needs_review,
                "no_model": coleta.files_no_model,
                "failed": coleta.files_failed,
            },
        )
        return BatchReport(finished=True)

    contagem = {"analyzed": 0, "needs_review": 0, "no_model": 0, "failed": 0}
    for arquivo in arquivos:
        try:
            resultado = _processar_arquivo(
                session, coleta, field, arquivo, analisadores, previas.get(arquivo.id)
            )
        except Exception as exc:  # um arquivo ruim não derruba o lote inteiro
            logger.exception("Falha ao processar %s da coleta %s", arquivo.id, coleta.code)
            arquivo.state = CollectionFileState.FAILED
            arquivo.error = f"{type(exc).__name__}: {exc}"[:2000]
            resultado = "failed"
        contagem[resultado] += 1

    coleta.files_processed += len(arquivos)
    coleta.files_analyzed += contagem["analyzed"]
    coleta.files_needs_review += contagem["needs_review"]
    coleta.files_no_model += contagem["no_model"]
    coleta.files_failed += contagem["failed"]

    return BatchReport(processed=len(arquivos), **contagem)


def _analisar(
    session: Session,
    coleta: Collection,
    field: Field | None,
    arquivo: CollectionFile,
    analisadores: list,
) -> list[ai_pipeline.Analysis] | Exception | None:
    """Lê o arquivo e chama os analisadores — sem escrever nada.

    A falha volta como valor, não como exceção: um arquivo ruim é desfecho
    daquele arquivo, e :func:`_processar_arquivo` o registra como tal.
    """
    if arquivo.asset_id is None:
        return None
    try:
        ativo = session.get(Asset, arquivo.asset_id)
        dados = storage.store.read(ativo.storage_key)
        return ai_pipeline.run_analyzers(
            dados,
            arquivo.filename,
            field.crop if field else "",
            analisadores,
            # A versão resolvida na criação da coleta, com a escolha do talhão.
            model_key=coleta.model_key,
            training_consent=consent.permite_treino(session, coleta.tenant_id),
        )
    except Exception as exc:  # vira FAILED do arquivo, no laço do lote
        return exc


def _processar_arquivo(
    session: Session,
    coleta: Collection,
    field: Field | None,
    arquivo: CollectionFile,
    analisadores: list,
    previa: list[ai_pipeline.Analysis] | Exception | None = None,
) -> str:
    """Cria a observação e grava o pipeline já rodado (:func:`_analisar`)."""
    if arquivo.asset_id is None:
        arquivo.state = CollectionFileState.FAILED
        arquivo.error = "Arquivo sem objeto no armazenamento."
        return "failed"

    observacao = _observacao(session, coleta, field, arquivo)
    session.add(observacao)
    session.flush()
    arquivo.observation_id = observacao.id

    if not analisadores:
        # Sem modelo treinado: a imagem fica catalogada e esperando o agrônomo.
        # Nenhum classificador é chamado — é a diferença entre "não sei" e uma
        # resposta inventada com confiança alta.
        arquivo.state = CollectionFileState.NO_MODEL
        arquivo.error = None
        session.add(
            Diagnosis(
                tenant_id=coleta.tenant_id,
                observation_id=observacao.id,
                field_id=observacao.field_id,
                status=DiagnosisStatus.NEEDS_REVIEW,
                # Nenhum analisador respondeu porque nenhum foi chamado. É o
                # mesmo vocabulário que o pipeline usa quando o serviço de
                # inferência está fora do ar: ausência de opinião, não
                # discordância.
                agreement=Agreement.UNAVAILABLE,
                pipeline_version=ai_pipeline.PIPELINE_VERSION,
                rationale=(
                    coleta.no_model_reason
                    or "Nenhum modelo treinado atende esta coleta. Aguarda anotação do agrônomo."
                ),
            )
        )
        return "no_model"

    if isinstance(previa, Exception):
        raise previa
    if previa is None:  # quem chamou sem pré-análise: roda aqui mesmo
        previa = _analisar(session, coleta, field, arquivo, analisadores)
        if isinstance(previa, Exception):
            raise previa
    deteccoes, diagnostico = ai_pipeline.analyze_observation(
        observacao, b"", arquivo.filename, field.crop if field else "", [], analyses=previa
    )
    for deteccao in deteccoes:
        session.add(deteccao)
    session.add(diagnostico)
    session.flush()
    audit.record_ai_diagnosis(
        session, diagnostico, pipeline_version=ai_pipeline.PIPELINE_VERSION
    )

    if diagnostico.status is DiagnosisStatus.AI_VALIDATED:
        arquivo.state = CollectionFileState.ANALYZED
        return "analyzed"
    arquivo.state = CollectionFileState.NEEDS_REVIEW
    return "needs_review"


def _observacao(
    session: Session, coleta: Collection, field: Field | None, arquivo: CollectionFile
) -> Observation:
    """Monta a observação a partir do arquivo e do que se sabe do talhão.

    Sem coordenada no arquivo, cai no centro do talhão. É uma aproximação
    declarada: o ponto serve para situar a imagem no mapa do cliente, não para
    guiar máquina nenhuma. Coordenada de verdade vem do EXIF do voo, que o
    painel envia quando o operador a entrega.
    """
    lat = arquivo.lat
    lon = arquivo.lon
    if lat is None or lon is None:
        centro = _centro_do_talhao(session, field)
        lat = lat if lat is not None else centro[0]
        lon = lon if lon is not None else centro[1]

    return Observation(
        tenant_id=coleta.tenant_id,
        farm_id=coleta.farm_id,
        field_id=coleta.field_id,
        device_id=None,
        collection_id=coleta.id,
        captured_at=arquivo.captured_at
        or datetime.combine(coleta.collected_on, datetime.min.time(), tzinfo=UTC),
        lat=lat,
        lon=lon,
        alt_m=arquivo.alt_m,
        image_asset_id=arquivo.asset_id,
        edge_summary={
            "collection_code": coleta.code,
            "source": coleta.source.value,
            "platform": coleta.platform.value,
            "filename": arquivo.filename,
        },
        # O enquadramento esperado pelos modelos treinados é de folha. Uma imagem
        # aérea não é "ruim": é outra pergunta. Marcar falso aqui é o que faz o
        # console mostrar a ressalva junto de qualquer resultado.
        model_input_ok=coleta.platform.value != "aerial",
    )


def _centro_do_talhao(session: Session, field: Field | None) -> tuple[float, float]:
    """Centro do polígono do talhão; na falta dele, o centro da fazenda."""
    if field is None:
        return (0.0, 0.0)
    if field.boundary:
        lon, lat = geo.centroid(field.boundary)
        return (lat, lon)
    return (field.farm.center_lat, field.farm.center_lon)
