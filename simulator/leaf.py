"""Folhas desenhadas para o simulador.

O analisador simulado não olha os pixels — ele lê a marca anexada ao fim do
arquivo. Mas quem abre a fila do agrônomo olha. Um quadrado preto ali faz a
demonstração parecer quebrada; uma folha com a lesão que o rótulo diz mostra o
fluxo como ele é.

Em Python puro de propósito: o simulador continua rodando com as dependências
da plataforma, sem Pillow nem numpy. É ilustração, não dado de treino — não
serve para avaliar modelo nenhum.
"""

from __future__ import annotations

import math
import random
import struct
import zlib

WIDTH = 256
HEIGHT = 192

Color = tuple[float, float, float]

# Por rótulo: semi-eixos (ao longo e através da nervura, em pixels), cor da
# lesão, cor do halo e quantidade mínima e máxima.
LESIONS: dict[str, tuple[tuple[float, float], Color, Color | None, tuple[int, int]]] = {
    # Milho
    "Common_Rust": ((2.3, 1.7), (146, 66, 28), (196, 184, 86), (45, 80)),
    "Gray_Leaf_Spot": ((9.0, 2.2), (168, 160, 134), (186, 176, 108), (10, 18)),
    "Blight": ((27.0, 6.0), (152, 142, 106), (126, 128, 82), (2, 4)),
    # Café — os sinais visuais descritos em VALTEXA-B/MODELS.md
    "Rust": ((3.0, 2.6), (178, 96, 30), (206, 190, 90), (30, 60)),
    "Cercospora_Leaf_Spot": ((5.0, 4.6), (120, 86, 54), (214, 200, 96), (6, 14)),
    "Phoma_Leaf_Spot": ((8.0, 5.0), (62, 52, 44), (150, 140, 96), (2, 5)),
}
GENERIC = ((4.0, 3.2), (112, 72, 40), (200, 186, 92), (8, 14))
HEALTHY = {"Healthy", "healthy"}
CHEWED = {"Spodoptera_frugiperda", "Leaf_Miner_Damage"}
"""Danos de inseto: não são mancha de fungo, são galeria, furo e raspagem.

Bicho-mineiro entra aqui e não em LESIONS de propósito — o sintoma é dano
mecânico, e desenhá-lo como mancha circular ensinaria o olho errado.
"""


def leaf_png(label: str, novelty: float = 0.4, seed: int = 0) -> bytes:
    """Folha em close, com a lesão ou o dano típico do rótulo."""
    rng = random.Random(f"{label}:{seed}")
    angle = math.radians(rng.uniform(-14.0, 14.0))
    cos_a, sin_a = math.cos(angle), math.sin(angle)
    cx = WIDTH / 2 + rng.uniform(-10.0, 10.0)
    cy = HEIGHT / 2 + rng.uniform(-8.0, 8.0)
    half_width = rng.uniform(50.0, 62.0)
    wave = rng.uniform(0.0, math.tau)
    # Novidade alta costuma ser o que o catálogo não cobre — aqui, clorose
    # entre as nervuras, com cara de deficiência nutricional.
    chlorosis = novelty > 1.0 and label not in CHEWED

    pixels = bytearray(WIDTH * HEIGHT * 3)
    inside = bytearray(WIDTH * HEIGHT)
    for y in range(HEIGHT):
        for x in range(WIDTH):
            dx, dy = x - cx, y - cy
            u = dx * cos_a + dy * sin_a
            v = -dx * sin_a + dy * cos_a
            edge = half_width * (1 - 0.3 * (u / WIDTH) ** 2) + 2.5 * math.sin(u / 21 + wave)
            grain = _grain(x, y)
            if abs(v) < edge:
                inside[y * WIDTH + x] = 1
                shade = 1 - 0.28 * (abs(v) / edge) ** 3
                vein = 5 * math.cos(v * 1.25)
                color: Color = (
                    70 * shade + vein + grain * 0.5,
                    132 * shade + vein * 1.4 + grain,
                    50 * shade + grain * 0.5,
                )
                if chlorosis and math.sin(v * 0.8) > 0.35:
                    color = _mix(color, (200, 190, 80), 0.45)
                if abs(v) < 2.4:
                    color = _mix(color, (180, 200, 130), 0.7)
            else:
                color = _background(x, y)
            _put(pixels, x, y, color)

    if label in CHEWED:
        _chew(pixels, inside, rng, origin=(cx, cy), rotation=(cos_a, sin_a), half_width=half_width)
    elif label not in HEALTHY:
        (a, b), core, halo, (low, high) = LESIONS.get(label, GENERIC)
        for _ in range(rng.randint(low, high)):
            scale = rng.uniform(0.7, 1.3)
            _lesion(
                pixels,
                inside,
                center=(
                    rng.uniform(-WIDTH * 0.45, WIDTH * 0.45),
                    rng.uniform(-half_width * 0.8, half_width * 0.8),
                ),
                origin=(cx, cy),
                rotation=(cos_a, sin_a),
                axes=(a * scale, b * scale),
                core=core,
                halo=halo,
            )

    return _png(pixels)


def _lesion(
    pixels: bytearray,
    inside: bytearray,
    *,
    center: tuple[float, float],
    origin: tuple[float, float],
    rotation: tuple[float, float],
    axes: tuple[float, float],
    core: Color,
    halo: Color | None,
) -> None:
    """Carimba uma lesão elíptica alinhada à nervura, só dentro da folha."""
    (u0, v0), (cx, cy), (cos_a, sin_a), (a, b) = center, origin, rotation, axes
    px = cx + u0 * cos_a - v0 * sin_a
    py = cy + u0 * sin_a + v0 * cos_a
    reach = math.ceil(max(a, b) * 1.7)
    for y in range(max(0, int(py) - reach), min(HEIGHT, int(py) + reach + 1)):
        for x in range(max(0, int(px) - reach), min(WIDTH, int(px) + reach + 1)):
            if not inside[y * WIDTH + x]:
                continue
            du = (x - px) * cos_a + (y - py) * sin_a
            dv = -(x - px) * sin_a + (y - py) * cos_a
            distance = math.hypot(du / a, dv / b)
            current = _get(pixels, x, y)
            if distance <= 1.0:
                darker = tuple(channel * (0.8 + 0.2 * distance) for channel in core)
                _put(pixels, x, y, _mix(current, darker, 0.9))  # type: ignore[arg-type]
            elif halo is not None and distance <= 1.7:
                _put(pixels, x, y, _mix(current, halo, 0.55 * (1.7 - distance) / 0.7))


def _chew(
    pixels: bytearray,
    inside: bytearray,
    rng: random.Random,
    *,
    origin: tuple[float, float],
    rotation: tuple[float, float],
    half_width: float,
) -> None:
    """Dano de lagarta: furos irregulares, janelas raspadas e excremento.

    O furo mostra o fundo através da folha, com a borda escurecida onde o
    tecido secou; a janela é a epiderme raspada que ficou translúcida.
    """
    (cx, cy), (cos_a, sin_a) = origin, rotation
    holes = [(rng.uniform(8.0, 19.0), rng.uniform(5.0, 11.0), 0) for _ in range(rng.randint(4, 7))]
    windows = [(rng.uniform(6.0, 12.0), rng.uniform(2.5, 4.5), 1) for _ in range(rng.randint(3, 6))]
    for a, b, kind in holes + windows:
        u0 = rng.uniform(-WIDTH * 0.42, WIDTH * 0.42)
        v0 = rng.uniform(-half_width * 0.75, half_width * 0.75)
        phase = rng.uniform(0.0, math.tau)
        px = cx + u0 * cos_a - v0 * sin_a
        py = cy + u0 * sin_a + v0 * cos_a
        reach = math.ceil(max(a, b) * 1.5)
        for y in range(max(0, int(py) - reach), min(HEIGHT, int(py) + reach + 1)):
            for x in range(max(0, int(px) - reach), min(WIDTH, int(px) + reach + 1)):
                if not inside[y * WIDTH + x]:
                    continue
                du = (x - px) * cos_a + (y - py) * sin_a
                dv = -(x - px) * sin_a + (y - py) * cos_a
                wobble = 1 + 0.2 * math.sin(math.atan2(dv, du) * 5 + phase)
                distance = math.hypot(du / a, dv / b) * wobble
                current = _get(pixels, x, y)
                if kind == 0 and distance <= 1.0:
                    _put(pixels, x, y, _background(x, y))
                elif kind == 0 and distance <= 1.3:
                    _put(pixels, x, y, _mix(current, (118, 92, 50), 0.7))
                elif kind == 1 and distance <= 1.0:
                    _put(pixels, x, y, _mix(current, (214, 216, 172), 0.6))

    for _ in range(rng.randint(12, 22)):
        px = cx + rng.uniform(-WIDTH * 0.45, WIDTH * 0.45)
        py = cy + rng.uniform(-half_width * 0.8, half_width * 0.8)
        radius = rng.uniform(1.3, 2.6)
        for y in range(max(0, int(py - radius)), min(HEIGHT, int(py + radius) + 1)):
            for x in range(max(0, int(px - radius)), min(WIDTH, int(px + radius) + 1)):
                if inside[y * WIDTH + x] and math.hypot(x - px, y - py) <= radius:
                    _put(pixels, x, y, (72, 58, 34))


def _background(x: int, y: int) -> Color:
    """O fundo atrás da folha: solo e palha, escurecendo para baixo."""
    grain = _grain(x, y)
    t = y / HEIGHT
    return (34 + 14 * t + grain, 46 + 10 * t + grain, 30 + 6 * t + grain)


def _grain(x: int, y: int) -> int:
    """Ruído determinístico barato: textura sem depender de ``random`` por pixel."""
    value = (x * 374761393 + y * 668265263) & 0xFFFFFFFF
    value = ((value ^ (value >> 13)) * 1274126177) & 0xFFFFFFFF
    return (value >> 24) % 11 - 5


def _mix(base: Color, other: Color, amount: float) -> Color:
    return (
        base[0] + (other[0] - base[0]) * amount,
        base[1] + (other[1] - base[1]) * amount,
        base[2] + (other[2] - base[2]) * amount,
    )


def _get(pixels: bytearray, x: int, y: int) -> Color:
    offset = (y * WIDTH + x) * 3
    return float(pixels[offset]), float(pixels[offset + 1]), float(pixels[offset + 2])


def _put(pixels: bytearray, x: int, y: int, color: Color) -> None:
    offset = (y * WIDTH + x) * 3
    for index in range(3):
        pixels[offset + index] = max(0, min(255, int(color[index])))


def _png(pixels: bytearray) -> bytes:
    stride = WIDTH * 3
    raw = b"".join(
        b"\x00" + bytes(pixels[row * stride : (row + 1) * stride]) for row in range(HEIGHT)
    )

    def chunk(kind: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(kind + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", crc)

    header = struct.pack(">IIBBBBB", WIDTH, HEIGHT, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(raw, 6))
        + chunk(b"IEND", b"")
    )
