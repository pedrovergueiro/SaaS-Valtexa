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
import shutil
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


store: ObjectStore = LocalObjectStore()
"""Instância do processo. Trocada nos testes por uma apontando para ``tmp_path``."""
