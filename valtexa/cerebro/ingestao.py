"""Ingestão por arquivo: ``python -m valtexa.cerebro.ingestao ARQUIVO... [--cliente ID]``.

Cada ``.md``/``.txt`` vai com o ``.meta.json`` ao lado (ver
:func:`valtexa.cerebro.conhecimento.ler_arquivo`). Sem ``--cliente``, a fonte é da plataforma
(todo cliente lê). Reenviar o mesmo arquivo é idempotente; a mesma versão com outro texto é
recusada. Em produção (``ENVIRONMENT=production``) documento fictício é recusado.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from valtexa import db
from valtexa.cerebro import conhecimento
from valtexa.config import settings


def main(argv: Sequence[str] | None = None, *, fabrica=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m valtexa.cerebro.ingestao",
                                     description="Ingere fontes de conhecimento por arquivo.")
    parser.add_argument("arquivos", nargs="+", help=".md ou .txt, com o .meta.json ao lado")
    parser.add_argument("--cliente", default=None, help="tenant_id (fonte do cliente)")
    args = parser.parse_args(argv)
    fabrica = fabrica or db.SessionLocal
    codigo = 0
    with fabrica() as session:
        for caminho in args.arquivos:
            try:
                meta, conteudo, formato = conhecimento.ler_arquivo(caminho)
                doc, criado = conhecimento.ingerir(
                    session, tenant_id=args.cliente, metadados=meta, conteudo=conteudo,
                    formato=formato, arquivo_nome=Path(caminho).name,
                    producao=settings.is_production)
                session.commit()
            except conhecimento.DocumentoInvalidoError as exc:
                session.rollback()
                print(f"{caminho}: recusado — {exc}", file=sys.stderr)
                codigo = 1
                continue
            estado = "ingerido" if criado else "já existia (mesmo conteúdo)"
            s = conhecimento.situacao(doc, _hoje())
            aviso = f"; bloqueado para uso operacional: {s.motivo}" if s.regulatorio and \
                not s.uso_operacional else ""
            print(f"{caminho}: {estado} — {doc.chave} v{doc.versao} sha256 {doc.sha256[:12]}"
                  f"{aviso}")
    return codigo


def _hoje():
    from valtexa.models import utcnow

    return utcnow().date()


if __name__ == "__main__":
    raise SystemExit(main())
