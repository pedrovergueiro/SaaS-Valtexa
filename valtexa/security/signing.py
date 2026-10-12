"""Assinatura das duas direções do protocolo — e por que ambas são assimétricas.

**Robô → nuvem.** O dispositivo gera o próprio par Ed25519 no primeiro boot e
envia à plataforma **apenas a chave pública**. A privada nunca sai do hardware.
A consequência prática é a que importa: um dump do banco da ValTexa não contém
nada capaz de se passar por um robô. Um esquema HMAC não teria essa propriedade
— para conferir a assinatura, o servidor precisaria guardar o segredo em forma
recuperável, e quem lesse a tabela passaria a falar pelo robô.

**Nuvem → robô.** Mesma razão espelhada. Se o robô pudesse *verificar* uma
missão com um segredo compartilhado, também poderia *forjar* uma. Com Ed25519
ele carrega só a chave pública da plataforma: um drone comprometido continua
incapaz de se autoconceder autorização para pulverizar. Essa é a fronteira que o
sistema inteiro existe para proteger.

O que a assinatura cobre, nos dois sentidos: identidade, horário, nonce,
sequência e conteúdo. Ver ``docs/AUTHENTICATION.md``.
"""

from __future__ import annotations

import hashlib
import json
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from valtexa.config import settings
from valtexa.models.base import as_utc

REQUEST_ALGORITHM = "VALTEXA-ED25519-REQUEST-V1"
"""Prefixo do texto canônico da requisição.

Amarrar o nome do esquema à mensagem impede que uma assinatura legítima de um
contexto seja reapresentada em outro.
"""

COMMAND_ALGORITHM = "VALTEXA-ED25519-COMMAND-V1"

HEADER_KEY_ID = "x-valtexa-key-id"
HEADER_TIMESTAMP = "x-valtexa-timestamp"
HEADER_NONCE = "x-valtexa-nonce"
HEADER_SIGNATURE = "x-valtexa-signature"

PROTOCOL_VERSION = "1.0"


class SignatureError(Exception):
    """A mensagem assinada não passou na verificação."""


# ---------------------------------------------------------------------------
# Chaves
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class KeyPair:
    """Par de chaves em hexadecimal, do jeito que trafega no provisionamento."""

    private_key: str
    public_key: str


def generate_keypair() -> KeyPair:
    """Gera um par Ed25519. Roda **no robô**; está aqui para o simulador e os testes."""
    private = Ed25519PrivateKey.generate()
    return KeyPair(
        private_key=private.private_bytes_raw().hex(),
        public_key=private.public_key().public_bytes_raw().hex(),
    )


def new_key_id() -> str:
    """Identificador público da credencial. Vai no cabeçalho, não é segredo."""
    return "dk_" + secrets.token_hex(12)


def new_nonce() -> str:
    return secrets.token_hex(16)


def new_provisioning_token() -> str:
    """Convite de uso único para um robô entrar na frota."""
    return "vtx_prov_" + secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """Hash de um token de provisionamento.

    SHA-256 puro e não scrypt: ao contrário de senha humana, este valor tem
    entropia real de 256 bits, então força bruta sobre o hash é inviável sem
    custo adicional.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Robô → nuvem
# ---------------------------------------------------------------------------


def canonical_request(
    method: str, path: str, query: str, timestamp: str, nonce: str, body: bytes
) -> bytes:
    """Monta o texto assinado de uma requisição.

    Uma linha por campo. Nenhum dos valores pode conter ``\\n``, então não existe
    combinação diferente de campos que produza o mesmo texto — a ambiguidade que
    permitiria mover um trecho de um campo para o vizinho sem quebrar a
    assinatura.
    """
    return "\n".join(
        [
            REQUEST_ALGORITHM,
            method.upper(),
            path,
            query or "",
            timestamp,
            nonce,
            hashlib.sha256(body).hexdigest(),
        ]
    ).encode("utf-8")


def sign_request(
    private_key: str,
    method: str,
    path: str,
    query: str,
    timestamp: str,
    nonce: str,
    body: bytes,
) -> str:
    """Assina uma requisição com a chave privada do dispositivo."""
    key = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(private_key))
    message = canonical_request(method, path, query, timestamp, nonce, body)
    return key.sign(message).hex()


def verify_request(
    public_key: str,
    signature: str,
    method: str,
    path: str,
    query: str,
    timestamp: str,
    nonce: str,
    body: bytes,
) -> None:
    """Confere a assinatura de uma requisição do dispositivo."""
    message = canonical_request(method, path, query, timestamp, nonce, body)
    _verify(public_key, signature, message, "Assinatura da requisição inválida.")


def check_timestamp(timestamp: str, now: datetime | None = None) -> datetime:
    """Recusa horários fora da janela de tolerância.

    Sozinho isso limita o *replay* a uma janela curta; combinado com o nonce
    gravado em :class:`~valtexa.models.platform_.UsedNonce`, elimina a repetição
    dentro dela. Os dois juntos, e não cada um isolado, é o que fecha o buraco.
    """
    try:
        moment = datetime.fromtimestamp(int(timestamp), tz=UTC)
    except (ValueError, OverflowError, OSError) as exc:
        raise SignatureError("Cabeçalho de horário inválido.") from exc

    reference = now or datetime.now(UTC)
    skew = abs((reference - moment).total_seconds())
    if skew > settings.device_clock_skew_seconds:
        raise SignatureError(
            f"Horário fora da janela de {settings.device_clock_skew_seconds}s "
            f"(diferença de {skew:.0f}s). Sincronize o relógio do dispositivo."
        )
    return moment


# ---------------------------------------------------------------------------
# Nuvem → robô
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SignedCommand:
    """Comando pronto para ir ao robô, com a assinatura ao lado do conteúdo."""

    payload: dict
    signature: str
    key_id: str
    algorithm: str = COMMAND_ALGORITHM

    def as_dict(self) -> dict:
        return {
            "payload": self.payload,
            "signature": self.signature,
            "key_id": self.key_id,
            "algorithm": self.algorithm,
        }


def platform_private_key() -> Ed25519PrivateKey:
    """Chave privada da plataforma.

    Derivada por SHA-256 do segredo configurado para que o ambiente de
    desenvolvimento funcione sem cerimônia de geração de chave. Em produção,
    :meth:`Settings.production_problems` exige a troca do segredo padrão — e
    trocá-lo troca o par, invalidando todo comando ainda em trânsito, que é o
    efeito desejado de uma rotação de emergência.
    """
    seed = hashlib.sha256(settings.command_signing_secret.encode("utf-8")).digest()
    return Ed25519PrivateKey.from_private_bytes(seed)


def platform_public_key() -> str:
    """Chave pública da plataforma, gravada no robô durante o provisionamento."""
    return (
        platform_private_key()
        .public_key()
        .public_bytes(Encoding.Raw, PublicFormat.Raw)
        .hex()
    )


OTA_ALGORITHM = "VALTEXA-ED25519-OTA-V1"
"""Prefixo do que se assina num pacote de atualização: uma assinatura de missão
nunca vale como assinatura de pacote, e vice-versa."""


def ota_private_key() -> Ed25519PrivateKey:
    """Chave que assina os pacotes OTA (``ota_signing_secret``; sem ela, a das missões)."""
    segredo = settings.ota_signing_secret or settings.command_signing_secret
    return Ed25519PrivateKey.from_private_bytes(
        hashlib.sha256(("ota:" + segredo).encode("utf-8")).digest()
    )


def ota_public_key() -> str:
    """Gravada no robô no provisionamento; é com ela que ele confere cada pacote."""
    return ota_private_key().public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex()


def canonical_ota(payload: dict) -> bytes:
    corpo = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return (OTA_ALGORITHM + "\n" + corpo).encode("utf-8")


def sign_ota(payload: dict) -> str:
    return ota_private_key().sign(canonical_ota(payload)).hex()


def verify_ota(payload: dict, signature: str, public_key: str | None = None) -> None:
    _verify(public_key or ota_public_key(), signature, canonical_ota(payload),
            "assinatura do pacote OTA inválida")


def canonical_command(payload: dict) -> bytes:
    """Serialização determinística de um comando.

    ``sort_keys`` e separadores fixos garantem que nuvem e firmware produzam byte
    a byte o mesmo texto. Sem isso a assinatura falharia por ordem de chave, e o
    robô recusaria uma missão legítima em pleno campo.
    """
    return json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")


def sign_command(payload: dict) -> SignedCommand:
    """Assina um comando com a chave privada da plataforma."""
    signature = platform_private_key().sign(canonical_command(payload)).hex()
    return SignedCommand(
        payload=payload, signature=signature, key_id=settings.command_signing_key_id
    )


def verify_command(payload: dict, signature: str, public_key: str | None = None) -> None:
    """Verifica um comando — o que o firmware roda antes de obedecer.

    Implementado aqui por dois motivos: o simulador usa exatamente este código, e
    ``docs/DRONE_INTEGRATION.md`` aponta para ele como a referência que o
    firmware precisa reproduzir.
    """
    _verify(
        public_key or platform_public_key(),
        signature,
        canonical_command(payload),
        "Comando com assinatura inválida.",
    )


def command_envelope(
    command: str, device_id: str, body: dict, sequence: int, ttl_seconds: int | None = None
) -> dict:
    """Monta o envelope padrão de um comando.

    Os campos de controle não são decorativos, e cada um fecha um ataque
    diferente:

    * ``device_id`` — impede reencaminhar a outro robô o comando de um vizinho;
    * ``sequence``  — impede reordenar comandos;
    * ``nonce``     — impede repetir;
    * ``expires_at``— impede executar amanhã uma missão autorizada hoje.
    """
    now = datetime.now(UTC)
    expires = now + timedelta(seconds=ttl_seconds or settings.command_ttl_seconds)
    return {
        "algorithm": COMMAND_ALGORITHM,
        "command": command,
        "device_id": device_id,
        "sequence": sequence,
        "nonce": new_nonce(),
        "issued_at": now.isoformat(),
        "expires_at": expires.isoformat(),
        "protocol_version": PROTOCOL_VERSION,
        "body": body,
    }


def command_is_expired(payload: dict, now: datetime | None = None) -> bool:
    """Se o envelope já passou da validade."""
    expires_at = as_utc(datetime.fromisoformat(payload["expires_at"]))
    return expires_at is not None and expires_at <= (now or datetime.now(UTC))


def _verify(public_key: str, signature: str, message: bytes, failure: str) -> None:
    try:
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key)).verify(
            bytes.fromhex(signature), message
        )
    except (InvalidSignature, ValueError) as exc:
        raise SignatureError(failure) from exc
