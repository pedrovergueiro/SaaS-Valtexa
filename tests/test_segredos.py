"""Segredos de produção (Parte 9, seção 36): vazios, padrão, fracos ou repetidos não sobem."""

from __future__ import annotations

import logging
import secrets
from pathlib import Path

import pytest

from valtexa import config as config_mod
from valtexa.config import INSECURE_DEFAULT_SECRET, Settings, recusar_se_inadequado

NOMES = ("session_secret", "command_signing_secret", "ota_signing_secret",
         "inference_service_token")


def _forte() -> str:
    return secrets.token_urlsafe(48)


def producao(**extra) -> Settings:
    """Uma configuração de produção completa e correta; ``extra`` estraga uma parte."""
    base = {
        "environment": "production",
        "database_url": "postgresql+psycopg://vtx@db/vtx",
        "cors_origins": "https://app.valtexa.com.br",
        "simulated_inference": False,
        "inference_enabled": True,
        "redis_url": "redis://redis:6379/0",
        "storage_backend": "s3",
        "s3_bucket": "valtexa-prod",
        **{nome: _forte() for nome in NOMES},
    }
    base.update(extra)
    return Settings(**base)


def test_configuracao_correta_sobe() -> None:
    assert producao().production_problems() == []
    recusar_se_inadequado(producao(), logging.getLogger("teste"))


@pytest.mark.parametrize("nome", NOMES)
@pytest.mark.parametrize("valor, trecho", [
    (None, "vazio"),
    ("", "vazio"),
    ("   ", "vazio"),
    (INSECURE_DEFAULT_SECRET, "padrão de desenvolvimento"),
    ("curto-demais-123", "mínimo é 32"),
    ("troque-este-valor-por-um-segredo-de-verdade-0001", "valor de exemplo"),
])
def test_cada_segredo_vazio_padrao_fraco_ou_de_exemplo_e_recusado(nome, valor, trecho) -> None:
    if valor is None and nome in ("session_secret", "command_signing_secret"):
        pytest.skip("campo obrigatório: None nem chega a ser configuração válida")
    problemas = producao(**{nome: valor}).production_problems()
    assert any(nome.upper() in p and trecho in p for p in problemas), problemas
    with pytest.raises(RuntimeError, match=nome.upper()):
        recusar_se_inadequado(producao(**{nome: valor}), logging.getLogger("teste"))


@pytest.mark.parametrize("a, b", [
    (a, b) for i, a in enumerate(NOMES) for b in NOMES[i + 1:]
])
def test_dois_segredos_iguais_sao_recusados(a, b) -> None:
    igual = _forte()
    problemas = producao(**{a: igual, b: igual}).production_problems()
    assert any(a.upper() in p and b.upper() in p and "iguais" in p for p in problemas)


def test_token_do_prometheus_nao_pode_repetir_segredo() -> None:
    sessao = _forte()
    problemas = producao(session_secret=sessao, metrics_token=sessao).production_problems()
    assert any("METRICS_TOKEN" in p for p in problemas)


def test_producao_sem_redis_e_recusada() -> None:
    assert any("REDIS_URL" in p for p in producao(redis_url=None).production_problems())


def test_s3_nao_exige_mais_pasta_de_staging() -> None:
    """Com o staging no bucket (Parte 9), UPLOAD_STAGING_DIR deixou de ser pendência."""
    assert not any("UPLOAD_STAGING_DIR" in p for p in producao().production_problems())


def test_fora_de_producao_vira_aviso(caplog) -> None:
    dev = Settings(environment="development")
    with caplog.at_level(logging.WARNING, logger="teste"):
        recusar_se_inadequado(dev, logging.getLogger("teste"))
    assert any("SESSION_SECRET" in r.message for r in caplog.records)


def test_segredo_lido_de_arquivo_montado(tmp_path: Path, monkeypatch) -> None:
    """Docker/Kubernetes secrets: um arquivo por segredo, nome do campo em minúsculas."""
    valor = _forte()
    (tmp_path / "session_secret").write_text(valor)
    monkeypatch.setenv("SECRETS_DIR", str(tmp_path))
    monkeypatch.delenv("SESSION_SECRET", raising=False)

    class ComArquivo(Settings):
        model_config = {**Settings.model_config,  # noqa: RUF012
                        "secrets_dir": config_mod._secrets_dir()}

    assert ComArquivo().session_secret == valor


def test_api_e_worker_recusam_subir_em_producao(monkeypatch) -> None:
    """A API (``lifespan``) e o worker chamam a mesma checagem antes de tocar no banco."""
    from valtexa import main, worker

    ruim = producao(session_secret=INSECURE_DEFAULT_SECRET)
    monkeypatch.setattr(worker, "settings", ruim)
    with pytest.raises(RuntimeError, match="SESSION_SECRET"):
        worker.main(["--once"])

    import asyncio

    tocou_no_banco = []
    monkeypatch.setattr(main, "settings", ruim)
    monkeypatch.setattr(main, "migrate", lambda: tocou_no_banco.append(1))

    async def subir() -> None:
        async with main.lifespan(main.app):
            pass

    with pytest.raises(RuntimeError, match="SESSION_SECRET"):
        asyncio.run(subir())
    assert tocou_no_banco == []


def test_nenhum_segredo_no_codigo() -> None:
    """Varredura simples: nada com cara de chave privada ou token de nuvem no repositório."""
    import re

    raiz = Path(__file__).resolve().parents[2]
    padroes = [
        re.compile(rb"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----"),
        re.compile(rb"AKIA[0-9A-Z]{16}"),
        re.compile(rb"ghp_[0-9A-Za-z]{36}"),
        re.compile(rb"xox[baprs]-[0-9A-Za-z-]{10,}"),
    ]
    permitidos = {"AKIAVALTEXATESTE0001"}  # chave falsa do moto em test_producao_s3.py
    achados = []
    for pasta in ("saas/valtexa", "saas/simulator", "saas/tests", "rover/valtexa_rover",
                  "ia/app", "deploy", "saas/deploy", "docs"):
        base = raiz / pasta
        if not base.exists():
            continue
        for arquivo in base.rglob("*"):
            if not arquivo.is_file() or arquivo.suffix in {".pyc", ".onnx", ".png", ".jpg"}:
                continue
            dados = arquivo.read_bytes()
            for padrao in padroes:
                for m in padrao.finditer(dados):
                    if m.group().decode() not in permitidos:
                        achados.append(f"{arquivo.relative_to(raiz)}: {m.group()[:12]!r}")
    assert achados == []
