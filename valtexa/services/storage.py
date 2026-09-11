"""Armazenamento de objetos: imagens, nuvens de pontos, mapas.

A implementação hoje é o sistema de arquivos local. A interface é a de um
armazenamento por chave, para que trocar por S3, GCS ou MinIO seja implementar
:class:`ObjectStore` — nenhum código de domínio abre arquivo diretamente.

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
            temporary = destination.with_suffix(destination.suffix + ".part")
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
            client = boto3.client(
                "s3", endpoint_url=settings.s3_endpoint_url, region_name=settings.s3_region
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
            self.client.put_object(
                Bucket=self.bucket,
                Key=self._object_key(key),
                Body=data,
                ContentType=content_type,
                Metadata={"sha256": digest},
            )
        return StoredObject(key=key, sha256=digest, size_bytes=len(data), content_type=content_type)

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
