"""Resposta HTTP de arquivo do cliente (imagem, nuvem de pontos, anexo da Edge AI).

Seção 43 (Parte 9). O arquivo veio de fora — de um robô, de um drone terceirizado,
de um upload — e é servido na **mesma origem do console**. Se um arquivo com HTML
dentro saísse com ``Content-Type: text/html``, o navegador o executaria com a sessão
de quem abriu (XSS armazenado). Então:

* só tipos da lista :data:`INLINE` saem com o próprio tipo; o resto vira
  ``application/octet-stream`` com ``Content-Disposition: attachment``;
* toda resposta leva ``Content-Security-Policy: default-src 'none'; sandbox`` — mesmo
  aberta direto na aba, nada roda — e ``nosniff``.
"""

from __future__ import annotations

from fastapi import Response

INLINE = frozenset({
    "image/jpeg", "image/png", "image/webp", "image/tiff", "application/json", "text/plain",
})

CSP_DE_ARQUIVO = "default-src 'none'; img-src 'self' data:; sandbox"


def resposta_de_arquivo(dados: bytes, content_type: str | None, *,
                        cache: str | None = None, nome: str = "arquivo") -> Response:
    tipo = (content_type or "").split(";")[0].strip().lower()
    headers = {
        "Content-Security-Policy": CSP_DE_ARQUIVO,
        "X-Content-Type-Options": "nosniff",
    }
    if cache:
        headers["Cache-Control"] = cache
    if tipo not in INLINE:
        limpo = "".join(c for c in nome if c.isalnum() or c in "-_.") or "arquivo"
        headers["Content-Disposition"] = f'attachment; filename="{limpo}"'
        tipo = "application/octet-stream" if not tipo.startswith(
            ("application/x-ply", "application/vnd.laszip")) else tipo
    return Response(content=dados, media_type=tipo, headers=headers)
