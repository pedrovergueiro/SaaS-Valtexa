"""Tokens de sessão para usuários e dispositivos.

Formato ``<payload_b64url>.<assinatura_b64url>``, HMAC-SHA256 sobre o payload —
equivalente a um JWT ``HS256`` sem o cabeçalho negociável. O algoritmo não é
negociado no token justamente para eliminar a classe de ataque em que o cliente
declara ``alg: none``.

O token é *bearer*: quem o tem, é. Por isso a validade é curta e nada nele
autoriza uma ação física — a missão que o robô executa é assinada à parte, com
Ed25519, em :mod:`valtexa.security.signing`.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from valtexa.config import settings


class TokenError(Exception):
    """Token ausente, malformado, adulterado ou vencido."""


@dataclass(frozen=True, slots=True)
class TokenClaims:
    """Conteúdo verificado de um token."""

    subject: str
    """``user:<id>`` ou ``device:<id>``."""

    kind: str
    """``user`` ou ``device``."""

    tenant_id: str | None
    issued_at: datetime
    expires_at: datetime
    extra: dict

    @property
    def subject_id(self) -> str:
        return self.subject.split(":", 1)[1]


def issue(
    subject_kind: str,
    subject_id: str,
    tenant_id: str | None = None,
    ttl_seconds: int | None = None,
    **extra: object,
) -> tuple[str, datetime]:
    """Emite um token. Devolve ``(token, expiração)``."""
    if subject_kind not in {"user", "device"}:
        raise ValueError(f"Tipo de sujeito desconhecido: {subject_kind!r}")
    now = datetime.now(UTC)
    ttl = ttl_seconds or (
        settings.user_session_ttl_seconds
        if subject_kind == "user"
        else settings.device_session_ttl_seconds
    )
    expires_at = now + timedelta(seconds=ttl)
    payload = {
        "sub": f"{subject_kind}:{subject_id}",
        "knd": subject_kind,
        "tid": tenant_id,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
        **extra,
    }
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    body = _b64encode(raw)
    return f"{body}.{_sign(body)}", expires_at


def verify(token: str) -> TokenClaims:
    """Valida assinatura e validade, devolvendo o conteúdo."""
    try:
        body, signature = token.split(".", 1)
    except ValueError as exc:
        raise TokenError("Token malformado.") from exc

    if not hmac.compare_digest(signature, _sign(body)):
        raise TokenError("Assinatura inválida.")

    try:
        payload = json.loads(_b64decode(body))
    except (ValueError, UnicodeDecodeError) as exc:
        raise TokenError("Conteúdo do token ilegível.") from exc

    expires_at = datetime.fromtimestamp(payload["exp"], tz=UTC)
    if expires_at <= datetime.now(UTC):
        raise TokenError("Token expirado.")

    reserved = {"sub", "knd", "tid", "iat", "exp"}
    return TokenClaims(
        subject=payload["sub"],
        kind=payload["knd"],
        tenant_id=payload.get("tid"),
        issued_at=datetime.fromtimestamp(payload["iat"], tz=UTC),
        expires_at=expires_at,
        extra={key: value for key, value in payload.items() if key not in reserved},
    )


def _sign(body: str) -> str:
    digest = hmac.new(
        settings.session_secret.encode("utf-8"), body.encode("ascii"), hashlib.sha256
    ).digest()
    return _b64encode(digest)


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64decode(text: str) -> bytes:
    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + padding)
