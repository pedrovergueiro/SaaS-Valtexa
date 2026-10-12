"""Documentos do cadastro rural: CPF, CNPJ e CAR.

Conferidos pelo dígito verificador (CPF/CNPJ) e pelo formato (CAR), e guardados
normalizados: CPF/CNPJ só com dígitos, CAR em maiúsculas sem pontos. Um CPF
digitado errado no cadastro da fazenda só aparece meses depois, no relatório
que vai para o banco ou para a certificadora — melhor recusar na hora.
"""

from __future__ import annotations

import re

# fmt: off
UFS = frozenset({
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG", "PA", "PB",
    "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO",
})
# fmt: on

_CAR = re.compile(r"^(?P<uf>[A-Z]{2})-(?P<ibge>\d{7})-(?P<hash>[0-9A-F]{32})$")


class DocumentoInvalidoError(ValueError):
    """Mensagem em português, pronta para o 422."""


def _digitos(valor: str) -> str:
    return re.sub(r"\D", "", valor)


def _dv(base: str, pesos: list[int]) -> int:
    resto = sum(int(d) * p for d, p in zip(base, pesos, strict=True)) % 11
    return 0 if resto < 2 else 11 - resto


def cpf_valido(numeros: str) -> bool:
    if len(numeros) != 11 or numeros == numeros[0] * 11:
        return False
    d1 = _dv(numeros[:9], list(range(10, 1, -1)))
    d2 = _dv(numeros[:10], list(range(11, 1, -1)))
    return numeros[9:] == f"{d1}{d2}"


def cnpj_valido(numeros: str) -> bool:
    if len(numeros) != 14 or numeros == numeros[0] * 14:
        return False
    pesos1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    d1 = _dv(numeros[:12], pesos1)
    d2 = _dv(numeros[:13], [6, *pesos1])
    return numeros[12:] == f"{d1}{d2}"


def normalizar_cpf_cnpj(valor: str) -> str:
    """Só dígitos, se for um CPF (11) ou CNPJ (14) válido; senão, ``DocumentoInvalidoError``."""
    numeros = _digitos(valor)
    if len(numeros) == 11:
        if not cpf_valido(numeros):
            raise DocumentoInvalidoError("CPF inválido: confira os dígitos verificadores.")
        return numeros
    if len(numeros) == 14:
        if not cnpj_valido(numeros):
            raise DocumentoInvalidoError("CNPJ inválido: confira os dígitos verificadores.")
        return numeros
    raise DocumentoInvalidoError("Informe um CPF (11 dígitos) ou CNPJ (14 dígitos).")


def mascarar_cpf_cnpj(numeros: str | None) -> str | None:
    """Só o fim do documento: ``***.***.***-12`` (CPF) ou ``**.***.***/****-12`` (CNPJ).

    É o que vê quem não pode alterar o cadastro da fazenda (LGPD: o operador
    precisa saber *de quem* é a fazenda, não do número inteiro). Os dois últimos
    dígitos são os verificadores — bastam para conferir com um papel na mão sem
    revelar o número. Valor fora do formato sai todo mascarado, nunca em claro.
    """
    if not numeros:
        return numeros
    digitos = _digitos(numeros)
    if len(digitos) == 11:
        return f"***.***.***-{digitos[-2:]}"
    if len(digitos) == 14:
        return f"**.***.***/****-{digitos[-2:]}"
    return "*" * len(numeros)


def normalizar_car(valor: str) -> str:
    """Recibo do CAR no formato ``UF-1234567-<32 caracteres hexadecimais>``.

    Aceita com pontos ou minúsculas (é como o recibo costuma ser copiado) e
    devolve sem pontos, em maiúsculas.
    """
    limpo = re.sub(r"[\s.]", "", valor).upper()
    casou = _CAR.match(limpo)
    if casou is None:
        raise DocumentoInvalidoError(
            "Número do CAR fora do formato UF-1234567-XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX "
            "(UF, código IBGE do município com 7 dígitos e 32 caracteres do recibo)."
        )
    if casou["uf"] not in UFS:
        raise DocumentoInvalidoError(f"UF {casou['uf']!r} do CAR não existe.")
    return limpo


def normalizar_uf(valor: str) -> str:
    uf = valor.strip().upper()
    if uf not in UFS:
        raise DocumentoInvalidoError(f"UF {valor!r} não existe.")
    return uf
