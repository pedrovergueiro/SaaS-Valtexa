"""Hash de senha com ``scrypt`` da biblioteca padrão.

Sem bcrypt/argon2 de propósito: ``hashlib.scrypt`` é memory-hard, está no
CPython desde a 3.6 e não traz dependência binária para instalar em campo. Os
parâmetros seguem a recomendação interativa do RFC 7914 (N=2^15, r=8, p=1).

O formato armazenado é ``scrypt$N$r$p$salt_hex$hash_hex``. Os parâmetros vão
junto para que uma linha antiga continue verificável depois de endurecermos os
custos — e :func:`needs_rehash` diz quando regravar.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

SCRYPT_N = 2**15
SCRYPT_R = 8
SCRYPT_P = 1
SALT_BYTES = 16
KEY_BYTES = 32

# O scrypt precisa de memória ~ 128 * N * r bytes; com N=2^15 e r=8 são 32 MiB.
# O CPython usa 32 MiB como teto padrão de maxmem, o que faz a chamada falhar
# exatamente no limite. Pedir o dobro deixa folga sem afrouxar o custo.
MAXMEM = 64 * 1024 * 1024


class InvalidHashError(ValueError):
    """O texto guardado não é um hash scrypt reconhecível."""


def hash_password(password: str) -> str:
    """Deriva o hash de uma senha nova."""
    if not password:
        raise ValueError("Senha vazia.")
    salt = secrets.token_bytes(SALT_BYTES)
    derived = _derive(password, salt, SCRYPT_N, SCRYPT_R, SCRYPT_P)
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${salt.hex()}${derived.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Confere a senha em tempo constante.

    Devolve ``False`` para hash malformado em vez de levantar: um registro
    corrompido não deve virar erro 500 na tela de login.
    """
    try:
        scheme, n_text, r_text, p_text, salt_hex, hash_hex = stored.split("$")
    except ValueError:
        return False
    if scheme != "scrypt":
        return False
    try:
        derived = _derive(
            password, bytes.fromhex(salt_hex), int(n_text), int(r_text), int(p_text)
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(derived.hex(), hash_hex)


def needs_rehash(stored: str) -> bool:
    """Se o hash foi gerado com custo menor do que o atual."""
    try:
        _, n_text, r_text, p_text, _, _ = stored.split("$")
    except ValueError:
        return True
    return (int(n_text), int(r_text), int(p_text)) != (SCRYPT_N, SCRYPT_R, SCRYPT_P)


def _derive(password: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    return hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=n, r=r, p=p, dklen=KEY_BYTES, maxmem=MAXMEM
    )
