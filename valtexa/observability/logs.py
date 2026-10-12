"""Logs estruturados (brief, seção 35): uma linha JSON por registro.

``LOG_FORMAT=json`` liga; o padrão continua ``texto`` (o formato antigo, bom para
ler no terminal). Em JSON, cada linha traz ``ts``, ``level``, ``logger``, ``msg`` e
o contexto da requisição — ``request_id``, ``tenant_id``, ``user_id``,
``device_id``, ``support_session_id`` — quando houver; os campos passados em
``extra={"campos": {...}}`` entram no mesmo nível. É o que permite, num agregador
(Loki, CloudWatch, Elastic), filtrar tudo o que aconteceu numa requisição ou num
cliente sem *regex*.

O texto também ganha o ``request_id`` no fim da linha: o código de erro que a
pessoa vê na tela continua achando o *traceback* com um ``grep``.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

from valtexa.observability import contexto

FORMATO_TEXTO = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"


class FiltroDeContexto(logging.Filter):
    """Pendura o contexto da requisição no registro (``record.contexto``)."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.contexto = contexto.atual()
        return True


class FormatoJson(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        linha: dict = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        linha.update(getattr(record, "contexto", None) or contexto.atual())
        extra = getattr(record, "campos", None)
        if isinstance(extra, dict):
            for chave, valor in extra.items():
                linha.setdefault(chave, valor)
        if record.exc_info:
            linha["exc"] = self.formatException(record.exc_info)
        return json.dumps(linha, ensure_ascii=False, default=str)


class FormatoTexto(logging.Formatter):
    def __init__(self) -> None:
        super().__init__(FORMATO_TEXTO)

    def format(self, record: logging.LogRecord) -> str:
        texto = super().format(record)
        ctx = getattr(record, "contexto", None) or {}
        if ctx.get("request_id"):
            texto += f" [req={ctx['request_id']}]"
        return texto


def configurar(nivel: str = "INFO", formato: str = "texto") -> None:
    """Configura a raiz uma vez (idempotente: troca o *handler* que pôs antes)."""
    raiz = logging.getLogger()
    raiz.setLevel(nivel)
    for h in list(raiz.handlers):
        if getattr(h, "_valtexa", False):
            raiz.removeHandler(h)
    handler = logging.StreamHandler()
    handler._valtexa = True  # type: ignore[attr-defined]
    handler.addFilter(FiltroDeContexto())
    handler.setFormatter(FormatoJson() if formato == "json" else FormatoTexto())
    raiz.addHandler(handler)


__all__ = ["FiltroDeContexto", "FormatoJson", "FormatoTexto", "configurar"]
