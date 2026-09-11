"""Armazenamento de objetos: disco local e S3."""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from pydantic import ValidationError

from valtexa.config import Settings
from valtexa.services import storage


class _MissingError(Exception):
    """Imita o ``ClientError`` do boto3 para objeto inexistente."""

    def __init__(self) -> None:
        super().__init__("404")
        self.response = {"Error": {"Code": "404"}}


class FakeS3:
    """Cliente S3 em memória. Só o que o adaptador usa."""

    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}
        self.puts = 0

    def put_object(self, Bucket, Key, Body, ContentType, Metadata):
        self.puts += 1
        self.objects[(Bucket, Key)] = Body

    def get_object(self, Bucket, Key):
        if (Bucket, Key) not in self.objects:
            raise _MissingError()
        return {"Body": io.BytesIO(self.objects[(Bucket, Key)])}

    def head_object(self, Bucket, Key):
        if (Bucket, Key) not in self.objects:
            raise _MissingError()
        return {}

    def delete_object(self, Bucket, Key):
        self.objects.pop((Bucket, Key), None)


@pytest.fixture
def s3(tmp_path: Path) -> tuple[storage.S3ObjectStore, FakeS3]:
    fake = FakeS3()
    store = storage.S3ObjectStore("bucket", "vtx", client=fake)
    store.cache = tmp_path / "cache"
    return store, fake


class TestS3:
    def test_guarda_uma_vez_e_le(self, s3) -> None:
        store, fake = s3
        first = store.put(b"imagem", "image/jpeg", namespace="cliente-a")
        second = store.put(b"imagem", "image/jpeg", namespace="cliente-a")

        assert first.key == second.key
        assert fake.puts == 1, "mesmo conteúdo não é reenviado"
        assert ("bucket", f"vtx/{first.key}") in fake.objects
        assert store.read(first.key) == b"imagem"

    def test_mesma_imagem_de_clientes_diferentes_nao_se_mistura(self, s3) -> None:
        store, _ = s3
        a = store.put(b"imagem", "image/jpeg", namespace="cliente-a")
        b = store.put(b"imagem", "image/jpeg", namespace="cliente-b")
        assert a.key != b.key

    def test_objeto_ausente(self, s3) -> None:
        store, _ = s3
        assert not store.exists("x/aa/bb/nada.jpg")
        with pytest.raises(storage.UnknownAssetError):
            store.read("x/aa/bb/nada.jpg")

    def test_recusa_chave_com_travessia(self, s3) -> None:
        store, _ = s3
        with pytest.raises(storage.UnknownAssetError):
            store.read("../fora")

    def test_path_baixa_para_o_cache(self, s3) -> None:
        store, _ = s3
        stored = store.put(b"conteudo", "image/png", namespace="c")
        local = store.path(stored.key)
        assert local.read_bytes() == b"conteudo"
        assert local.is_relative_to(store.cache.resolve())

    def test_apaga(self, s3) -> None:
        store, _ = s3
        stored = store.put(b"x", "image/png", namespace="c")
        store.delete(stored.key)
        assert not store.exists(stored.key)

    def test_respeita_o_limite_de_tamanho(self, s3, monkeypatch: pytest.MonkeyPatch) -> None:
        store, fake = s3
        monkeypatch.setattr(storage, "settings", Settings(max_asset_mb=1))
        with pytest.raises(storage.AssetTooLargeError):
            store.put(b"0" * (2 * 1024 * 1024), "image/jpeg", namespace="c")
        assert fake.puts == 0


class TestLocal:
    def test_le_o_que_guardou(self, tmp_path: Path) -> None:
        store = storage.LocalObjectStore(tmp_path)
        stored = store.put(b"folha", "image/jpeg", namespace="c")
        assert store.read(stored.key) == b"folha"

    def test_separa_clientes(self, tmp_path: Path) -> None:
        """Apagar os dados de um cliente não pode apagar o arquivo de outro."""
        store = storage.LocalObjectStore(tmp_path)
        a = store.put(b"folha", "image/jpeg", namespace="cliente-a")
        b = store.put(b"folha", "image/jpeg", namespace="cliente-b")
        assert a.key != b.key
        store.delete(a.key)
        assert store.read(b.key) == b"folha"

    def test_recusa_travessia(self, tmp_path: Path) -> None:
        store = storage.LocalObjectStore(tmp_path)
        with pytest.raises(storage.UnknownAssetError):
            store.path("../../etc/passwd")


class TestConfiguration:
    def test_s3_sem_bucket_nao_sobe(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(storage, "settings", Settings(storage_backend="s3", s3_bucket=None))
        with pytest.raises(RuntimeError, match="S3_BUCKET"):
            storage.build_store()

    def test_s3_sem_bucket_aparece_como_pendencia_de_producao(self) -> None:
        problems = Settings(storage_backend="s3").production_problems()
        assert any("S3_BUCKET" in problem for problem in problems)

    def test_backend_desconhecido_e_recusado(self) -> None:
        with pytest.raises(ValidationError):
            Settings(storage_backend="ftp")
