"""Coletas: criar o lote, receber os arquivos e entregar ao processamento.

Este módulo é o caminho de entrada do MVP. O voo é de um operador terceirizado,
os arquivos chegam por pendrive ou link, e alguém da ValTexa os importa pelo
painel. Nada aqui controla drone nem planeja voo — a coleta começa quando os
arquivos já existem.

**Por que o upload é em pedaços.** Uma coleta aérea de um talhão médio são
centenas de arquivos e dezenas de gigabytes. Mandar isso numa requisição só
falharia por tempo limite, por memória no servidor e por qualquer oscilação da
internet da fazenda — e falharia depois de horas, do começo. O caminho
implementado é: declarar os arquivos, mandar cada um em pedaços, perguntar de
onde continuar quando cair. O limite de tamanho é o do armazenamento contratado,
não um número escolhido aqui.

**Por que o pedaço só é aceito no deslocamento certo.** O servidor guarda
``received_bytes`` e aceita o pedaço que começa exatamente ali. Um pedaço
repetido (a rede caiu depois de gravar, o cliente reenviou) é reconhecido e
ignorado sem erro; um pedaço fora de ordem é recusado. Isso dispensa tabela de
partes e torna impossível um arquivo "completo" com um buraco no meio.

**Por que a análise não roda aqui.** Quem faz o upload fecha a aba. O que este
módulo faz ao fim do upload é enfileirar um :class:`ProcessingJob`; quem
processa é o worker.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from valtexa.config import settings
from valtexa.models import (
    ActorType,
    Asset,
    AssetKind,
    CapturePlatform,
    Collection,
    CollectionFile,
    CollectionFileState,
    CollectionKind,
    CollectionSource,
    CollectionState,
    Field,
    JobKind,
    SubjectType,
    User,
)
from valtexa.services import audit, events, jobs, storage

if TYPE_CHECKING:
    from valtexa.schemas import CollectionProgress

logger = logging.getLogger(__name__)

ALLOWED_CONTENT_TYPES = frozenset(
    {"image/jpeg", "image/png", "image/webp", "image/tiff", "application/octet-stream"}
)
"""O que a plataforma aceita numa coleta.

``image/tiff`` entra porque ortomosaico e GeoTIFF é o que um operador entrega.
``application/octet-stream`` é o que navegador manda quando não reconhece a
extensão — a validação real é a extensão e o conteúdo, não o cabeçalho.
"""

EXTENSOES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
}

PLATAFORMA_POR_TIPO = {
    CollectionKind.AERIAL_IMAGE: CapturePlatform.AERIAL,
    CollectionKind.ORTHOMOSAIC: CapturePlatform.AERIAL,
    CollectionKind.GROUND_IMAGE: CapturePlatform.GROUND,
    CollectionKind.OTHER: CapturePlatform.ANY,
}
"""De onde a imagem veio, derivado do que o administrador declarou.

Não é pergunta separada no formulário de propósito: quem importa a coleta sabe
dizer se é foto aérea ou de folha, e não deveria precisar saber o vocabulário de
plataforma do catálogo de modelos.
"""

ORIGENS_SEM_INGESTAO = frozenset({CollectionSource.DRONE_OWNED})
"""Origens que existem no vocabulário e **não** têm caminho de ingestão.

``DRONE_OWNED`` é a fase futura. Aceitar uma coleta com essa origem hoje seria
registrar no banco que um drone da ValTexa voou — não voou. A recusa é explícita
para que a ausência apareça, em vez de virar um dado errado.
"""


class CollectionError(RuntimeError):
    """Falha de uso do serviço de coletas. Vira 4xx na API."""


class ChunkOutOfOrderError(CollectionError):
    """O pedaço não começa onde o arquivo parou."""

    def __init__(self, esperado: int, recebido: int) -> None:
        super().__init__(
            f"Pedaço fora de ordem: o arquivo está em {esperado} bytes e o pedaço "
            f"começa em {recebido}. Consulte o arquivo para saber de onde continuar."
        )
        self.esperado = esperado
        self.recebido = recebido


@dataclass(frozen=True, slots=True)
class ArquivoDeclarado:
    """O que o painel declara antes de mandar bytes."""

    filename: str
    size_bytes: int
    content_type: str | None = None
    sha256: str | None = None
    captured_at: datetime | None = None
    lat: float | None = None
    lon: float | None = None
    alt_m: float | None = None


# ---------------------------------------------------------------------------
# Criação
# ---------------------------------------------------------------------------


def next_code(session: Session, tenant_id: str, ano: int | None = None) -> str:
    """Próximo ``COL-2026-000001`` do cliente.

    A sequência é por cliente e por ano. Dois administradores criando coletas no
    mesmo segundo podem disputar o mesmo número; a unicidade real é do
    identificador, e o código é rótulo de conversa. Quem quiser garantia forte
    põe índice único em ``(tenant_id, code)`` — o custo é uma colisão virar erro
    em vez de um número pulado.
    """
    ano = ano or datetime.now(UTC).year
    prefixo = f"COL-{ano}-"
    ultimo = session.scalar(
        select(func.max(Collection.code)).where(
            Collection.tenant_id == tenant_id, Collection.code.like(f"{prefixo}%")
        )
    )
    proximo = int(ultimo.removeprefix(prefixo)) + 1 if ultimo else 1
    return f"{prefixo}{proximo:06d}"


def create(
    session: Session,
    *,
    tenant_id: str,
    field: Field,
    collected_on: date,
    source: CollectionSource,
    kind: CollectionKind,
    operator_name: str | None = None,
    notes: str | None = None,
    actor: User | None = None,
) -> Collection:
    """Cria a coleta vazia. Os arquivos entram depois, um a um."""
    if source in ORIGENS_SEM_INGESTAO:
        raise CollectionError(
            f"A origem {source.value!r} não tem ingestão implementada: o drone próprio "
            f"da ValTexa é fase futura. Use 'drone_third_party' para o voo do operador "
            f"terceirizado."
        )
    if field.tenant_id != tenant_id:
        raise CollectionError("O talhão é de outro cliente.")

    plataforma = PLATAFORMA_POR_TIPO[kind]
    coleta = Collection(
        tenant_id=tenant_id,
        code=next_code(session, tenant_id, collected_on.year),
        farm_id=field.farm_id,
        field_id=field.id,
        collected_on=collected_on,
        source=source,
        kind=kind,
        platform=plataforma,
        state=CollectionState.DRAFT,
        operator_name=operator_name,
        notes=notes,
        created_by=actor.id if actor else None,
    )
    _resolver_modelo(session, coleta, field)
    session.add(coleta)
    session.flush()

    audit.record(
        session,
        tenant_id=tenant_id,
        action="collection.created",
        subject_type=SubjectType.COLLECTION,
        subject_id=coleta.id,
        actor_type=ActorType.USER if actor else ActorType.SYSTEM,
        actor_id=actor.id if actor else None,
        actor_label=actor.email if actor else None,
        new_state=coleta.state.value,
        payload={
            "code": coleta.code,
            "field_id": field.id,
            "crop": field.crop,
            "source": source.value,
            "kind": kind.value,
            "platform": plataforma.value,
            "model_key": coleta.model_key,
            "no_model_reason": coleta.no_model_reason,
        },
    )
    return coleta


def _resolver_modelo(session: Session, coleta: Collection, field: Field) -> None:
    """Decide, na criação, qual modelo atenderá a coleta — ou por que nenhum.

    Resolver agora e não na fila é deliberado: o administrador descobre no
    formulário que uma coleta aérea de café não tem modelo treinado, em vez de
    descobrir meia hora depois que 1.500 imagens não geraram nada.
    """
    # Importação local: ai_pipeline traz httpx e o catálogo de analisadores, e
    # este módulo é importado pela API inteira.
    from valtexa.services.ai_pipeline import NoModelForCaptureError, resolve_model

    try:
        coleta.model_key = resolve_model(
            session, field.crop, coleta.platform, field.ai_model, tenant_id=field.tenant_id
        )
        coleta.no_model_reason = None
    except NoModelForCaptureError as exc:
        coleta.model_key = None
        coleta.no_model_reason = str(exc)


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------


def register_files(
    session: Session, coleta: Collection, declarados: list[ArquivoDeclarado]
) -> list[CollectionFile]:
    """Declara os arquivos que virão. Nenhum byte ainda.

    Declarar antes de mandar é o que dá barra de progresso honesta (o total é
    conhecido desde o início) e retomada (o painel pergunta o que falta).
    """
    if coleta.state not in {CollectionState.DRAFT, CollectionState.UPLOADING}:
        raise CollectionError(
            f"A coleta está em {coleta.state.value!r} e não aceita arquivos novos."
        )

    criados = []
    for item in declarados:
        content_type = _content_type(item.filename, item.content_type)
        if content_type not in ALLOWED_CONTENT_TYPES:
            raise CollectionError(
                f"{item.filename!r}: tipo {content_type!r} não suportado. "
                f"Aceitos: {sorted(EXTENSOES)}."
            )
        if item.size_bytes <= 0:
            raise CollectionError(f"{item.filename!r}: tamanho declarado inválido.")

        arquivo = CollectionFile(
            tenant_id=coleta.tenant_id,
            collection_id=coleta.id,
            filename=item.filename[:255],
            content_type=content_type,
            size_bytes=item.size_bytes,
            sha256_declared=item.sha256,
            captured_at=item.captured_at,
            lat=item.lat,
            lon=item.lon,
            alt_m=item.alt_m,
            state=CollectionFileState.REGISTERED,
        )
        session.add(arquivo)
        criados.append(arquivo)

    coleta.file_count += len(criados)
    coleta.bytes_total += sum(item.size_bytes for item in declarados)
    if coleta.state is CollectionState.DRAFT:
        coleta.state = CollectionState.UPLOADING
    session.flush()
    return criados


def _staging_compartilhado() -> storage.S3ChunkStaging | None:
    """Com S3, os pedaços vão para o bucket (qualquer réplica recebe qualquer pedaço).

    O índice de cada pedaço é o seu deslocamento: a montagem junta em ordem. Sem
    S3, o arquivo ``.part`` em disco de :func:`staging_path`.
    """
    if isinstance(storage.store, storage.S3ObjectStore):
        return storage.S3ChunkStaging(storage.store, area="coleta")
    return None


def _descartar_staging(arquivo: CollectionFile) -> None:
    compartilhado = _staging_compartilhado()
    if compartilhado is not None:
        compartilhado.clear(arquivo.id)
    else:
        staging_path(arquivo).unlink(missing_ok=True)


def staging_path(arquivo: CollectionFile) -> Path:
    """Onde os pedaços se acumulam até o arquivo fechar.

    Fica fora do armazenamento de objetos de propósito: um arquivo pela metade
    não é um objeto, não tem ``sha256`` final e não pode ser servido a ninguém.
    Só depois de conferido ele entra no armazenamento, e aí pela chave de
    conteúdo, como todo o resto.
    """
    base = settings.upload_staging_dir or Path(settings.storage_dir) / "_upload"
    raiz = Path(base) / arquivo.collection_id
    raiz.mkdir(parents=True, exist_ok=True)
    return raiz / f"{arquivo.id}.part"


def receive_chunk(
    session: Session, arquivo: CollectionFile, offset: int, data: bytes
) -> CollectionFile:
    """Grava um pedaço no deslocamento ``offset``.

    Reenvio do mesmo pedaço é aceito sem efeito — a rede cai justamente entre o
    servidor gravar e o cliente receber a confirmação, e nesse caso o cliente
    reenvia. Qualquer outro deslocamento é recusado.
    """
    if arquivo.state in {CollectionFileState.STORED, CollectionFileState.ANALYZED}:
        return arquivo
    if arquivo.state is CollectionFileState.REJECTED:
        raise CollectionError(f"{arquivo.filename!r} foi recusado: {arquivo.error}")

    if offset != arquivo.received_bytes:
        # Reenvio de um pedaço que já entrou inteiro: ignora e confirma.
        if offset < arquivo.received_bytes and offset + len(data) <= arquivo.received_bytes:
            return arquivo
        raise ChunkOutOfOrderError(arquivo.received_bytes, offset)

    if arquivo.received_bytes + len(data) > arquivo.size_bytes:
        raise CollectionError(
            f"{arquivo.filename!r}: o pedaço ultrapassa o tamanho declarado "
            f"({arquivo.size_bytes} bytes)."
        )

    compartilhado = _staging_compartilhado()
    if compartilhado is not None:
        compartilhado.put(arquivo.id, offset, data)
    else:
        with staging_path(arquivo).open("ab") as saida:
            saida.write(data)

    arquivo.received_bytes += len(data)
    arquivo.state = CollectionFileState.UPLOADING
    arquivo.collection.bytes_received += len(data)

    if arquivo.is_complete:
        _finalizar_arquivo(session, arquivo)
    session.flush()
    return arquivo


def _finalizar_arquivo(session: Session, arquivo: CollectionFile) -> None:
    """Confere o ``sha256`` e move os bytes para o armazenamento de objetos."""
    compartilhado = _staging_compartilhado()
    dados = (compartilhado.assemble(arquivo.id) if compartilhado is not None
             else staging_path(arquivo).read_bytes())
    digest = hashlib.sha256(dados).hexdigest()

    if arquivo.sha256_declared and digest != arquivo.sha256_declared:
        arquivo.state = CollectionFileState.REJECTED
        arquivo.error = (
            f"sha256 não confere: declarado {arquivo.sha256_declared}, recebido {digest}. "
            f"O arquivo chegou corrompido e não foi guardado."
        )
        arquivo.collection.files_failed += 1
        _descartar_staging(arquivo)
        return

    real = storage.tipo_de_imagem(dados)
    if real is None:
        # Seção 43 (Parte 9): a extensão diz .jpg, os bytes não são imagem nenhuma.
        arquivo.state = CollectionFileState.REJECTED
        arquivo.error = "O conteúdo não é uma imagem JPEG, PNG, WebP ou TIFF."
        arquivo.collection.files_failed += 1
        _descartar_staging(arquivo)
        return
    arquivo.content_type = real

    guardado = storage.store.put(dados, arquivo.content_type, namespace=arquivo.tenant_id)

    # A mesma imagem pode chegar duas vezes — quadro repetido do voo, operador
    # que reenvia a pasta inteira, lote entregue de novo. O armazenamento já é
    # endereçado por conteúdo; aqui o objeto também é reaproveitado, e os dois
    # arquivos da coleta apontam para ele. Inserir um ``Asset`` novo violaria o
    # ``UNIQUE (tenant_id, sha256)`` e derrubaria o lote inteiro por causa de
    # uma duplicata.
    ativo = session.scalars(
        select(Asset).where(
            Asset.tenant_id == arquivo.tenant_id, Asset.sha256 == guardado.sha256
        )
    ).first()
    if ativo is None:
        ativo = Asset(
            tenant_id=arquivo.tenant_id,
            kind=AssetKind.IMAGE,
            storage_key=guardado.key,
            content_type=guardado.content_type,
            size_bytes=guardado.size_bytes,
            sha256=guardado.sha256,
            captured_at=arquivo.captured_at,
        )
        session.add(ativo)
        session.flush()

    arquivo.asset_id = ativo.id
    arquivo.sha256 = digest
    arquivo.state = CollectionFileState.STORED
    arquivo.collection.files_stored += 1
    _descartar_staging(arquivo)


def complete_upload(
    session: Session, coleta: Collection, actor: User | None = None
) -> Collection:
    """Fecha o upload e enfileira o processamento.

    Arquivo incompleto não segura o lote: ele fica marcado e aparece no painel.
    Segurar a coleta inteira por um arquivo que o operador não conseguiu mandar
    é como perder as outras 1.499 imagens por causa de uma.
    """
    if coleta.state in {
        CollectionState.PROCESSING_QUEUED,
        CollectionState.AI_PROCESSING,
    }:
        return coleta
    if coleta.state not in {CollectionState.DRAFT, CollectionState.UPLOADING}:
        raise CollectionError(f"A coleta está em {coleta.state.value!r}: upload já encerrado.")

    incompletos = session.scalars(
        select(CollectionFile).where(
            CollectionFile.collection_id == coleta.id,
            CollectionFile.state.in_(
                [CollectionFileState.REGISTERED, CollectionFileState.UPLOADING]
            ),
        )
    ).all()
    for arquivo in incompletos:
        arquivo.state = CollectionFileState.FAILED
        arquivo.error = (
            f"Upload encerrado com {arquivo.received_bytes} de {arquivo.size_bytes} bytes."
        )
        coleta.files_failed += 1
        _descartar_staging(arquivo)

    coleta.upload_completed_at = datetime.now(UTC)
    coleta.state = CollectionState.UPLOAD_COMPLETED

    if coleta.files_stored == 0:
        coleta.state = CollectionState.FAILED
        _auditar(session, coleta, "collection.upload_failed", actor)
        return coleta

    jobs.enqueue(
        session,
        tenant_id=coleta.tenant_id,
        kind=JobKind.COLLECTION_INGEST,
        subject_type=SubjectType.COLLECTION,
        subject_id=coleta.id,
        total=coleta.files_stored,
    )
    coleta.state = CollectionState.PROCESSING_QUEUED
    _auditar(session, coleta, "collection.upload_completed", actor)
    events.publish(
        session,
        events.COLLECTION_QUEUED,
        tenant_id=coleta.tenant_id,
        subject_type=SubjectType.COLLECTION,
        subject_id=coleta.id,
        payload={
            "code": coleta.code,
            "files": coleta.files_stored,
            "model_key": coleta.model_key,
        },
    )
    return coleta


# ---------------------------------------------------------------------------
# Fim do processamento
# ---------------------------------------------------------------------------


def settle(session: Session, coleta: Collection) -> Collection:
    """Decide o estado final depois que o worker processou todos os arquivos."""
    coleta.processing_finished_at = datetime.now(UTC)
    if coleta.files_needs_review or coleta.files_no_model:
        coleta.state = CollectionState.REVIEW_REQUIRED
    elif coleta.files_analyzed:
        coleta.state = CollectionState.ANALYZED
    else:
        coleta.state = CollectionState.FAILED
    return coleta


def release(session: Session, coleta: Collection, actor: User | None = None) -> Collection:
    """Publica a coleta para o cliente.

    É um ato com nome: alguém da ValTexa decide que o resultado está pronto para
    o produtor ver. Não é automático de propósito — uma coleta cheia de imagens
    sem modelo chegaria ao cliente como uma tela vazia sem explicação.
    """
    if coleta.state not in {
        CollectionState.ANALYZED,
        CollectionState.REVIEW_REQUIRED,
        CollectionState.RESULTS_GENERATED,
    }:
        raise CollectionError(
            f"A coleta está em {coleta.state.value!r} e ainda não tem resultado para publicar."
        )
    coleta.state = CollectionState.AVAILABLE_TO_CLIENT
    coleta.released_at = datetime.now(UTC)
    coleta.released_by = actor.id if actor else None
    _auditar(session, coleta, "collection.released", actor)
    events.publish(
        session,
        events.COLLECTION_AVAILABLE,
        tenant_id=coleta.tenant_id,
        subject_type=SubjectType.COLLECTION,
        subject_id=coleta.id,
        payload={"code": coleta.code, "field_id": coleta.field_id},
    )
    return coleta


def progress(coleta: Collection) -> CollectionProgress:
    """Os números da barra de progresso do painel.

    Duas barras, não uma: upload e processamento são fases com ritmos muito
    diferentes, e juntá-las numa só esconderia justamente a que travou.
    """
    from valtexa.schemas import CollectionProgress

    return CollectionProgress(
        files=coleta.file_count,
        bytes_total=coleta.bytes_total,
        bytes_received=coleta.bytes_received,
        stored=coleta.files_stored,
        processed=coleta.files_processed,
        analyzed=coleta.files_analyzed,
        needs_review=coleta.files_needs_review,
        no_model=coleta.files_no_model,
        failed=coleta.files_failed,
        upload_percent=_percent(coleta.bytes_received, coleta.bytes_total),
        processing_percent=_percent(coleta.files_processed, coleta.files_stored),
    )


def _percent(feito: int, total: int) -> float:
    return round(100.0 * feito / total, 1) if total else 0.0


def on_diagnosis_reviewed(session: Session, diagnosis) -> Collection | None:
    """Fecha o arquivo da coleta quando o agrônomo dá o veredito.

    O arquivo sai de ``NEEDS_REVIEW`` ou ``NO_MODEL`` e vira ``ANALYZED`` — para
    uma imagem aérea de hoje, essa é a única forma de ela ficar analisada, e o
    responsável tem nome. Quando o último arquivo pendente fecha, a coleta passa
    de ``REVIEW_REQUIRED`` a ``ANALYZED`` e fica pronta para publicação.
    """
    arquivo = session.scalars(
        select(CollectionFile).where(
            CollectionFile.observation_id == diagnosis.observation_id
        )
    ).first()
    if arquivo is None:
        return None

    coleta = arquivo.collection
    if arquivo.state is CollectionFileState.NEEDS_REVIEW:
        coleta.files_needs_review = max(0, coleta.files_needs_review - 1)
    elif arquivo.state is CollectionFileState.NO_MODEL:
        coleta.files_no_model = max(0, coleta.files_no_model - 1)
    else:
        return coleta

    arquivo.state = CollectionFileState.ANALYZED
    coleta.files_analyzed += 1

    if (
        coleta.state is CollectionState.REVIEW_REQUIRED
        and not coleta.files_needs_review
        and not coleta.files_no_model
    ):
        coleta.state = CollectionState.ANALYZED
    return coleta


def _auditar(session: Session, coleta: Collection, acao: str, actor: User | None) -> None:
    audit.record(
        session,
        tenant_id=coleta.tenant_id,
        action=acao,
        subject_type=SubjectType.COLLECTION,
        subject_id=coleta.id,
        actor_type=ActorType.USER if actor else ActorType.SYSTEM,
        actor_id=actor.id if actor else None,
        actor_label=actor.email if actor else None,
        new_state=coleta.state.value,
        payload={
            "code": coleta.code,
            "files": coleta.file_count,
            "stored": coleta.files_stored,
            "failed": coleta.files_failed,
            "bytes": coleta.bytes_received,
        },
    )


def _content_type(filename: str, declarado: str | None) -> str:
    """O tipo real, pela extensão. O cabeçalho do navegador não é autoridade."""
    extensao = Path(filename).suffix.lower()
    if extensao in EXTENSOES:
        return EXTENSOES[extensao]
    return (declarado or "application/octet-stream").split(";")[0].strip()
