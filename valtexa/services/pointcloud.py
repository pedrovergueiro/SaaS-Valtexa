"""Nuvem de pontos da passada: o formato aceito, validado antes de guardar.

O rover envia **PLY binário** — o formato que todo driver de LiDAR exporta e que
CloudCompare, MeshLab e o próprio console abrem sem conversão. O contrato é
estreito de propósito: um único layout, sem variações opcionais.

::

    ply
    format binary_little_endian 1.0
    element vertex N
    property float x
    property float y
    property float z
    property uchar red
    property uchar green
    property uchar blue
    end_header
    <N * 15 bytes>

Coordenadas em metros, no plano local da passada (origem na ``origin`` dos
metadados; x leste, y norte, z para cima). Linhas ``comment`` e ``obj_info`` são
aceitas e ignoradas.

Um layout só custa ao firmware uma conversão na saída do driver, e em troca o
servidor não precisa de biblioteca de nuvem de pontos, o navegador lê o arquivo
com vinte linhas, e um arquivo fora do contrato é recusado com uma mensagem que
diz exatamente o que está errado — em vez de ser aceito e renderizado torto.
"""

from __future__ import annotations

import math
import struct
from collections.abc import Iterable
from dataclasses import dataclass

MAX_POINTS = 500_000
"""Teto por passada. Uma rua de 300 m com voxel de 3 cm cabe com folga.

O robô deve reduzir a nuvem antes de subir (grade de voxels). Mandar a nuvem
crua do sensor seria pagar enlace de celular por redundância.
"""

MAX_EXTENT_M = 2_000.0
"""Distância máxima de um ponto à origem da passada."""

MAX_HEADER_BYTES = 4_096

_VERTEX = struct.Struct("<fffBBB")
POINT_SIZE = _VERTEX.size
_PROPERTIES = [
    ("float", "x"),
    ("float", "y"),
    ("float", "z"),
    ("uchar", "red"),
    ("uchar", "green"),
    ("uchar", "blue"),
]
_ALIASES = {"float32": "float", "uint8": "uchar"}


class PointCloudError(ValueError):
    """O arquivo não segue o contrato. A mensagem diz o que está errado."""


@dataclass(frozen=True, slots=True)
class PointCloudInfo:
    points: int
    minimum: tuple[float, float, float]
    maximum: tuple[float, float, float]


def inspect(data: bytes) -> PointCloudInfo:
    """Valida o arquivo inteiro e devolve contagem e limites.

    Confere o cabeçalho, o tamanho exato do corpo e cada coordenada. Um ``NaN``
    ou um ponto a 40 km da origem não é "detalhe do sensor": é um arquivo que
    renderizaria a lavoura como um risco no infinito.
    """
    end = data.find(b"end_header\n", 0, MAX_HEADER_BYTES)
    if not data.startswith(b"ply\n") or end < 0:
        raise PointCloudError("Não é um PLY: esperado 'ply' na primeira linha e 'end_header'.")

    header = data[:end].decode("ascii", errors="replace").splitlines()
    body = data[end + len(b"end_header\n") :]

    count: int | None = None
    properties: list[tuple[str, str]] = []
    element: str | None = None
    fmt_seen = False
    for line in header[1:]:
        parts = line.split()
        if not parts or parts[0] in {"comment", "obj_info"}:
            continue
        if parts[0] == "format":
            if parts[1:] != ["binary_little_endian", "1.0"]:
                declared = " ".join(parts[1:])
                raise PointCloudError(f"Formato {declared!r}: use binary_little_endian 1.0.")
            fmt_seen = True
        elif parts[0] == "element":
            element = parts[1] if len(parts) > 1 else None
            if element == "vertex":
                try:
                    count = int(parts[2])
                except (IndexError, ValueError) as exc:
                    raise PointCloudError("Contagem de vértices inválida.") from exc
            elif len(parts) < 3 or parts[2] != "0":
                raise PointCloudError(f"Elemento {element!r} não suportado: só 'vertex'.")
        elif parts[0] == "property" and element == "vertex":
            if len(parts) != 3:
                raise PointCloudError(f"Propriedade inválida: {line!r}.")
            properties.append((_ALIASES.get(parts[1], parts[1]), parts[2]))

    if not fmt_seen:
        raise PointCloudError("Cabeçalho sem linha 'format'.")
    if count is None:
        raise PointCloudError("Cabeçalho sem 'element vertex'.")
    if properties != _PROPERTIES:
        expected = ", ".join(f"{kind} {name}" for kind, name in _PROPERTIES)
        raise PointCloudError(f"Propriedades do vértice precisam ser, nesta ordem: {expected}.")
    if count <= 0:
        raise PointCloudError("A nuvem está vazia.")
    if count > MAX_POINTS:
        raise PointCloudError(
            f"{count} pontos excede o teto de {MAX_POINTS}. Reduza a nuvem no robô "
            "(grade de voxels) antes de enviar."
        )
    if len(body) != count * POINT_SIZE:
        raise PointCloudError(
            f"Corpo com {len(body)} bytes; {count} pontos pedem {count * POINT_SIZE}."
        )

    low = [math.inf, math.inf, math.inf]
    high = [-math.inf, -math.inf, -math.inf]
    for x, y, z, _r, _g, _b in _VERTEX.iter_unpack(body):
        for axis, value in enumerate((x, y, z)):
            if not math.isfinite(value) or abs(value) > MAX_EXTENT_M:
                raise PointCloudError(
                    f"Coordenada fora do plano da passada: {value!r} "
                    f"(limite ±{MAX_EXTENT_M:.0f} m)."
                )
            low[axis] = min(low[axis], value)
            high[axis] = max(high[axis], value)

    return PointCloudInfo(points=count, minimum=tuple(low), maximum=tuple(high))


def encode(points: Iterable[tuple[float, float, float, int, int, int]]) -> bytes:
    """Monta um PLY no formato do contrato. Referência para o firmware."""
    rows = list(points)
    buffer = bytearray(len(rows) * POINT_SIZE)
    for index, (x, y, z, red, green, blue) in enumerate(rows):
        _VERTEX.pack_into(buffer, index * POINT_SIZE, x, y, z, red, green, blue)
    header = (
        "ply\n"
        "format binary_little_endian 1.0\n"
        "comment valtexa row scan\n"
        f"element vertex {len(rows)}\n"
        "property float x\nproperty float y\nproperty float z\n"
        "property uchar red\nproperty uchar green\nproperty uchar blue\n"
        "end_header\n"
    ).encode("ascii")
    return header + bytes(buffer)
