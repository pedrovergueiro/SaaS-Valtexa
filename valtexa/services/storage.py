"""Armazenamento de objetos: imagens, nuvens de pontos, mapas.

Duas implementações da mesma interface (:class:`ObjectStore`): o disco local
(desenvolvimento e servidor único) e S3 ou compatível — MinIO, R2 — para
produção (``STORAGE_BACKEND=s3``, brief seção 38), com *staging* de chunks
compartilhado entre réplicas (:class:`S3ChunkStaging`), multipart no objeto
grande, URL assinada de leitura e lifecycle por categoria. Nenhum código de
domínio abre arquivo diretamente.

O nome do arquivo nunca vem do cliente. A chave é derivada do ``sha256`` do
conteúdo, o que traz três coisas de graça: nada de travessia de caminho, upload
repetido não duplica bytes, e a auditoria pode provar que a imagem exibida é a
que o robô enviou.

A chave é prefixada pelo cliente. Endereçar por conteúdo puro faria dois
clientes com o mesmo arquivo compartilharem os mesmos bytes em disco — e aí
atender um pedido de exclusão de um deles apagaria o arquivo do outro. Um
prefixo por cliente custa duplicar bytes idênticos e devolve a possibilidade de
apagar os dados de um cliente sem tocar nos dos demais.
"""

from __future__ import annotations

import hashlib
import io
import shutil
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Protocol

from valtexa.config import settings

EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "application/octet-stream": ".bin",
    "application/json": ".json",
    "text/plain": ".txt",
    "application/vnd.laszip": ".laz",
    "application/x-ply": ".ply",
}
DEFAULT_EXTENSION = ".bin"


class AssetTooLargeError(ValueError):
    """O arquivo excede ``MAX_ASSET_MB``."""


class UnknownAssetError(KeyError):
    """A chave não existe no armazenamento."""


@dataclass(frozen=True, slots=True)
class StoredObject:
    """O que sobra depois de guardar um arquivo."""

    key: str
    sha256: str
    size_bytes: int
    content_type: str


class ObjectStore(Protocol):
    """Contrato mínimo do armazenamento."""

    def put(self, data: bytes, content_type: str, namespace: str) -> StoredObject: ...

    def open(self, key: str) -> BinaryIO: ...

    def read(self, key: str) -> bytes: ...

    def path(self, key: str) -> Path: ...

    def delete(self, key: str) -> None: ...

    def exists(self, key: str) -> bool: ...

    def url_assinada(self, key: str, segundos: int, filename: str | None = None) -> str | None:
        """URL temporária de leitura direto do armazenamento, ou ``None`` se não houver.

        Só é chamada **depois** do escopo do cliente conferido pela rota. O disco
        local não tem URL própria: devolve ``None`` e a rota serve os bytes.
        """
        ...


class LocalObjectStore:
    """Armazenamento em disco, particionado pelos primeiros dígitos do hash.

    Os dois níveis de subdiretório existem porque um único diretório com
    centenas de milhares de arquivos degrada a listagem em qualquer sistema de
    arquivos — e uma temporada de rover produz exatamente isso.
    """

    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root or settings.storage_dir)
        self.root.mkdir(parents=True, exist_ok=True)

    def put(self, data: bytes, content_type: str, namespace: str = "shared") -> StoredObject:
        if len(data) > settings.max_asset_bytes:
            raise AssetTooLargeError(
                f"Arquivo de {len(data) / 1024 / 1024:.1f} MB excede o limite de "
                f"{settings.max_asset_mb} MB."
            )
        digest = hashlib.sha256(data).hexdigest()
        suffix = EXTENSIONS.get(content_type, DEFAULT_EXTENSION)
        key = f"{_safe(namespace)}/{digest[:2]}/{digest[2:4]}/{digest}{suffix}"
        destination = self.root / key
        destination.parent.mkdir(parents=True, exist_ok=True)

        # Mesmo conteúdo, mesma chave: reescrever seria trabalho de E/S por nada.
        if not destination.exists():
            # Nome temporário único: dois envios simultâneos do mesmo conteúdo
            # (robôs diferentes, mesma foto) não podem disputar o mesmo ``.part``
            # — achado no estresse da Parte 5. ``replace`` é atômico; o segundo
            # a chegar só sobrescreve com os mesmos bytes.
            temporary = destination.with_name(f"{destination.name}.{uuid.uuid4().hex}.part")
            temporary.write_bytes(data)
            temporary.replace(destination)

        return StoredObject(
            key=key, sha256=digest, size_bytes=len(data), content_type=content_type
        )

    def path(self, key: str) -> Path:
        """Caminho absoluto, recusando qualquer chave que escape da raiz."""
        candidate = (self.root / key).resolve()
        root = self.root.resolve()
        if not candidate.is_relative_to(root):
            raise UnknownAssetError(f"Chave fora do armazenamento: {key!r}")
        if not candidate.exists():
            raise UnknownAssetError(f"Objeto não encontrado: {key!r}")
        return candidate

    def open(self, key: str) -> BinaryIO:
        return self.path(key).open("rb")

    def read(self, key: str) -> bytes:
        return self.path(key).read_bytes()

    def exists(self, key: str) -> bool:
        try:
            self.path(key)
        except UnknownAssetError:
            return False
        return True

    def delete(self, key: str) -> None:
        try:
            self.path(key).unlink()
        except UnknownAssetError:
            return

    def url_assinada(self, key: str, segundos: int, filename: str | None = None) -> None:
        return None

    def clear(self) -> None:
        """Apaga tudo. Existe para os testes; nunca é chamado pela API."""
        shutil.rmtree(self.root, ignore_errors=True)
        self.root.mkdir(parents=True, exist_ok=True)


def _safe(namespace: str) -> str:
    """Reduz o prefixo a caracteres inertes num caminho.

    O namespace é um identificador interno, não entrada de usuário, mas ele vira
    diretório — e uma checagem barata aqui vale mais do que confiar em quem
    chama.
    """
    cleaned = "".join(ch for ch in namespace if ch.isalnum() or ch in "-_")
    return cleaned or "shared"


class S3ObjectStore:
    """Armazenamento em S3 ou compatível (MinIO, Cloudflare R2).

    Mesmas chaves do disco local — prefixo do cliente e ``sha256`` do conteúdo —,
    então migrar de um para o outro é copiar os objetos, sem reescrever o banco.

    O cliente é injetável: os testes usam um falso em memória e a produção,
    ``boto3``. A dependência só é importada quando o backend é usado.
    """

    def __init__(self, bucket: str, prefix: str = "valtexa", client: object | None = None) -> None:
        if client is None:
            try:
                import boto3
            except ImportError as exc:  # pragma: no cover - depende do ambiente
                raise RuntimeError("STORAGE_BACKEND=s3 exige 'pip install boto3'.") from exc
            from botocore.config import Config

            # SigV4 sempre (a URL assinada SigV2 é aceita só por legado e não prende o
            # cabeçalho Host); endereço por caminho no MinIO (S3_ADDRESSING_STYLE=path).
            client = boto3.client(
                "s3", endpoint_url=settings.s3_endpoint_url, region_name=settings.s3_region,
                config=Config(signature_version="s3v4",
                              s3={"addressing_style": settings.s3_addressing_style}),
            )
        self.client = client
        self.bucket = bucket
        self.prefix = prefix.strip("/")
        self.cache = Path(tempfile.gettempdir()) / "valtexa-s3-cache"

    def put(self, data: bytes, content_type: str, namespace: str = "shared") -> StoredObject:
        if len(data) > settings.max_asset_bytes:
            raise AssetTooLargeError(
                f"Arquivo de {len(data) / 1024 / 1024:.1f} MB excede o limite de "
                f"{settings.max_asset_mb} MB."
            )
        digest = hashlib.sha256(data).hexdigest()
        suffix = EXTENSIONS.get(content_type, DEFAULT_EXTENSION)
        key = f"{_safe(namespace)}/{digest[:2]}/{digest[2:4]}/{digest}{suffix}"
        if not self.exists(key):
            extras = {
                "ContentType": content_type,
                "Metadata": {"sha256": digest},
                # A categoria vira etiqueta do objeto: é por ela que o lifecycle do
                # bucket decide transição e expiração (ver politica_de_ciclo_de_vida).
                "Tagging": f"categoria={categoria(content_type, namespace)}",
            }
            if len(data) > settings.s3_multipart_threshold_mb * 1024 * 1024:
                self._multipart(self._object_key(key), data, extras)
            else:
                self.client.put_object(
                    Bucket=self.bucket, Key=self._object_key(key), Body=data, **extras
                )
        return StoredObject(key=key, sha256=digest, size_bytes=len(data), content_type=content_type)

    def _multipart(self, object_key: str, data: bytes, extras: dict) -> None:
        """Envio em partes de :data:`PARTE_MULTIPART` (ortomosaico, nuvem de pontos).

        Uma parte que falhe aborta o upload inteiro: sem isso o bucket guardaria
        partes órfãs cobradas até a regra ``AbortIncompleteMultipartUpload`` passar.
        """
        criado = self.client.create_multipart_upload(
            Bucket=self.bucket, Key=object_key, **extras
        )
        upload_id = criado["UploadId"]
        partes = []
        try:
            for numero, inicio in enumerate(range(0, len(data), PARTE_MULTIPART), start=1):
                resposta = self.client.upload_part(
                    Bucket=self.bucket, Key=object_key, UploadId=upload_id,
                    PartNumber=numero, Body=data[inicio:inicio + PARTE_MULTIPART],
                )
                partes.append({"ETag": resposta["ETag"], "PartNumber": numero})
            self.client.complete_multipart_upload(
                Bucket=self.bucket, Key=object_key, UploadId=upload_id,
                MultipartUpload={"Parts": partes},
            )
        except Exception:
            self.client.abort_multipart_upload(
                Bucket=self.bucket, Key=object_key, UploadId=upload_id
            )
            raise

    def url_assinada(self, key: str, segundos: int, filename: str | None = None) -> str:
        """URL GET pré-assinada (SigV4) para **esta** chave, válida por ``segundos``.

        A assinatura cobre o caminho: trocar a chave na URL (para o objeto de outro
        cliente) invalida a assinatura e o bucket responde 403. Quem decide se a
        pessoa pode ver o objeto é a rota, antes de chamar isto.
        """
        params = {"Bucket": self.bucket, "Key": self._object_key(key)}
        if filename:
            limpo = "".join(c for c in filename if c.isalnum() or c in "-_.") or "arquivo"
            params["ResponseContentDisposition"] = f'inline; filename="{limpo}"'
        return self.client.generate_presigned_url(
            "get_object", Params=params, ExpiresIn=int(segundos)
        )

    def read(self, key: str) -> bytes:
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=self._object_key(key))
        except Exception as exc:
            if _is_missing(exc):
                raise UnknownAssetError(f"Objeto não encontrado: {key!r}") from exc
            raise
        return response["Body"].read()

    def open(self, key: str) -> BinaryIO:
        return io.BytesIO(self.read(key))

    def path(self, key: str) -> Path:
        """Baixa para um cache local e devolve o caminho.

        Existe para quem precisa de arquivo em disco (uma biblioteca de imagem,
        por exemplo). Para servir bytes, :meth:`read` é o caminho direto.
        """
        local = (self.cache / self._object_key(key)).resolve()
        if not local.is_relative_to(self.cache.resolve()):
            raise UnknownAssetError(f"Chave fora do armazenamento: {key!r}")
        if not local.exists():
            local.parent.mkdir(parents=True, exist_ok=True)
            local.write_bytes(self.read(key))
        return local

    def exists(self, key: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=self._object_key(key))
        except Exception as exc:
            if _is_missing(exc):
                return False
            raise
        return True

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=self._object_key(key))

    def _object_key(self, key: str) -> str:
        if ".." in key.split("/"):
            raise UnknownAssetError(f"Chave inválida: {key!r}")
        return f"{self.prefix}/{key}" if self.prefix else key


ASSINATURAS_DE_IMAGEM = (
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"II*\x00", "image/tiff"),
    (b"MM\x00*", "image/tiff"),
)


def tipo_de_imagem(dados: bytes) -> str | None:
    """O tipo de imagem pelos primeiros bytes (assinatura do formato), ou ``None``.

    O ``Content-Type`` do envio é o que o remetente **diz**; isto é o que o arquivo
    **é**. Seção 43: uma "imagem" que é HTML não entra como imagem.
    """
    if dados[:4] == b"RIFF" and dados[8:12] == b"WEBP":
        return "image/webp"
    for assinatura, tipo in ASSINATURAS_DE_IMAGEM:
        if dados.startswith(assinatura):
            return tipo
    return None


PARTE_MULTIPART = 8 * 1024 * 1024
"""Tamanho de cada parte no multipart (o S3 exige ≥ 5 MB, exceto a última)."""

CATEGORIAS = ("imagem", "nuvem_pontos", "ota", "log")


def categoria(content_type: str, namespace: str) -> str:
    """A categoria de retenção do objeto (etiqueta ``categoria`` no S3)."""
    if namespace == "ota":
        return "ota"
    if content_type.startswith("image/"):
        return "imagem"
    if content_type in ("application/vnd.laszip", "application/x-ply"):
        return "nuvem_pontos"
    return "log"


# ---------------------------------------------------------------------------
# Staging de chunks compartilhado entre réplicas
# ---------------------------------------------------------------------------


class S3ChunkStaging:
    """Chunks de upload como objetos no bucket, sob ``{prefixo}/_staging/{area}/``.

    Substitui o disco local quando a API tem mais de uma réplica: o chunk 3 pode
    chegar na réplica A e o 4 na B, e quem recebe o ``complete`` monta o arquivo
    lendo do bucket. A lista do que chegou é a listagem do prefixo — não depende
    de banco nem de memória.

    Por que objetos e não o *multipart upload* nativo do S3 para os chunks: o S3
    exige partes de **≥ 5 MB** (menos a última), e o Rover manda chunks de 256 KB
    (``rover/valtexa_rover/config.py``) — exatamente para retomar barato em rede
    ruim. O multipart nativo é usado no **objeto final** grande
    (:meth:`S3ObjectStore._multipart`). O que sobrar aqui (upload abandonado) é
    apagado pelo worker (``limpar_abandonados``) e, de rede de segurança, pela
    regra de lifecycle do prefixo ``_staging/``.

    Mesma interface do ``LocalChunkStaging`` de ``edge_sync``: ``put``, ``received``,
    ``assemble``, ``clear``.
    """

    def __init__(self, store: S3ObjectStore, area: str = "edge") -> None:
        self.client = store.client
        self.bucket = store.bucket
        base = f"{store.prefix}/_staging" if store.prefix else "_staging"
        self.base = f"{base}/{_safe(area)}"

    def _pasta(self, upload_pk: str) -> str:
        limpo = "".join(c for c in upload_pk if c.isalnum() or c in "-_")
        if not limpo:
            raise UnknownAssetError(f"Upload inválido: {upload_pk!r}")
        return f"{self.base}/{limpo}/"

    def put(self, upload_pk: str, index: int, data: bytes) -> None:
        self.client.put_object(
            Bucket=self.bucket, Key=f"{self._pasta(upload_pk)}{int(index):012d}", Body=data
        )

    def _chaves(self, upload_pk: str) -> list[str]:
        chaves: list[str] = []
        token = None
        while True:
            pedido = {"Bucket": self.bucket, "Prefix": self._pasta(upload_pk)}
            if token:
                pedido["ContinuationToken"] = token
            resposta = self.client.list_objects_v2(**pedido)
            chaves.extend(item["Key"] for item in resposta.get("Contents", []))
            if not resposta.get("IsTruncated"):
                return chaves
            token = resposta["NextContinuationToken"]

    def received(self, upload_pk: str) -> set[int]:
        return {int(chave.rsplit("/", 1)[1]) for chave in self._chaves(upload_pk)}

    def assemble(self, upload_pk: str, total: int | None = None) -> bytes:
        """Concatena em ordem. ``total=None`` junta tudo o que há, pela ordem do índice."""
        indices = range(total) if total is not None else sorted(self.received(upload_pk))
        pasta = self._pasta(upload_pk)
        return b"".join(
            self.client.get_object(Bucket=self.bucket, Key=f"{pasta}{i:012d}")["Body"].read()
            for i in indices
        )

    def clear(self, upload_pk: str) -> None:
        chaves = self._chaves(upload_pk)
        for inicio in range(0, len(chaves), 1000):  # limite do DeleteObjects
            self.client.delete_objects(
                Bucket=self.bucket,
                Delete={"Objects": [{"Key": k} for k in chaves[inicio:inicio + 1000]],
                        "Quiet": True},
            )


# ---------------------------------------------------------------------------
# Ciclo de vida (retenção por categoria)
# ---------------------------------------------------------------------------


def politica_de_ciclo_de_vida(prefixo: str = "valtexa") -> dict:
    """As regras de lifecycle do bucket, montadas da configuração.

    * ``_staging/``: chunk esquecido expira em ``S3_STAGING_DAYS``; multipart
      incompleto é abortado em 1 dia (em todo o bucket);
    * ``categoria=imagem`` e ``nuvem_pontos``: transição para STANDARD_IA e depois
      GLACIER_IR (continuam legíveis na hora, só mais baratos) — **sem expiração**:
      apagar a foto do cliente é contrato, não padrão de código;
    * ``categoria=log``: expira em ``S3_LOGS_EXPIRE_DAYS``, se definido;
    * ``categoria=ota``: nada (o pacote precisa existir enquanto houver robô nele).
    """
    base = f"{prefixo.strip('/')}/" if prefixo.strip("/") else ""
    regras: list[dict] = [
        {
            "ID": "staging-chunks",
            "Status": "Enabled",
            "Filter": {"Prefix": f"{base}_staging/"},
            "Expiration": {"Days": settings.s3_staging_days},
        },
        {
            "ID": "multipart-incompleto",
            "Status": "Enabled",
            "Filter": {"Prefix": base},
            "AbortIncompleteMultipartUpload": {"DaysAfterInitiation": 1},
        },
    ]
    transicoes = []
    if settings.s3_infrequent_after_days:
        transicoes.append({"Days": settings.s3_infrequent_after_days,
                           "StorageClass": "STANDARD_IA"})
    if settings.s3_archive_after_days:
        transicoes.append({"Days": settings.s3_archive_after_days,
                           "StorageClass": "GLACIER_IR"})
    if transicoes:
        for cat in ("imagem", "nuvem_pontos"):
            regras.append({
                "ID": f"{cat}-transicao",
                "Status": "Enabled",
                "Filter": {"And": {"Prefix": base,
                                   "Tags": [{"Key": "categoria", "Value": cat}]}},
                "Transitions": transicoes,
            })
    if settings.s3_logs_expire_days:
        regras.append({
            "ID": "log-expiracao",
            "Status": "Enabled",
            "Filter": {"And": {"Prefix": base,
                               "Tags": [{"Key": "categoria", "Value": "log"}]}},
            "Expiration": {"Days": settings.s3_logs_expire_days},
        })
    return {"Rules": regras}


def aplicar_ciclo_de_vida(store: S3ObjectStore) -> dict:
    """Grava a política no bucket (substitui a anterior). Passo de deploy, não da API."""
    politica = politica_de_ciclo_de_vida(store.prefix)
    store.client.put_bucket_lifecycle_configuration(
        Bucket=store.bucket, LifecycleConfiguration=politica
    )
    return politica


def _is_missing(exc: Exception) -> bool:
    """Reconhece "não existe" nas duas formas que o boto3 usa."""
    response = getattr(exc, "response", None) or {}
    code = str(response.get("Error", {}).get("Code", ""))
    return code in {"404", "NoSuchKey", "NotFound"} or type(exc).__name__ == "NoSuchKey"


def build_store() -> ObjectStore:
    """Instancia o backend configurado."""
    if settings.storage_backend == "s3":
        if not settings.s3_bucket:
            raise RuntimeError("STORAGE_BACKEND=s3 exige S3_BUCKET.")
        return S3ObjectStore(settings.s3_bucket, settings.s3_prefix)
    return LocalObjectStore()


store: ObjectStore = build_store()
"""Instância do processo. Trocada nos testes por uma apontando para ``tmp_path``."""


def preparar() -> None:
    """Chamado na subida da API. Só o disco local tem pasta a criar."""
    if isinstance(store, LocalObjectStore):
        store.root.mkdir(parents=True, exist_ok=True)


def main(argv: list[str] | None = None) -> int:
    """``python -m valtexa.services.storage --ciclo-de-vida``: aplica o lifecycle no bucket."""
    import argparse
    import json

    parser = argparse.ArgumentParser(description=main.__doc__)
    parser.add_argument("--ciclo-de-vida", action="store_true",
                        help="grava a política de lifecycle no bucket configurado")
    parser.add_argument("--mostrar", action="store_true",
                        help="só imprime a política, sem gravar")
    args = parser.parse_args(argv)
    if args.mostrar:
        print(json.dumps(politica_de_ciclo_de_vida(settings.s3_prefix), indent=2))
        return 0
    if args.ciclo_de_vida:
        if not isinstance(store, S3ObjectStore):
            parser.error("STORAGE_BACKEND não é s3: não há bucket para configurar.")
        print(json.dumps(aplicar_ciclo_de_vida(store), indent=2))
        return 0
    parser.print_help()
    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
