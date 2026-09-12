"""A lavoura simulada, planta por planta — o que o sensor 3D do rover enxerga.

O rover real mede as plantas com LiDAR ou câmera estéreo ao passar pela rua.
Aqui, as plantas existem numa grade determinística ancorada no talhão: linhas
paralelas à direção de plantio, no espaçamento do cadastro, com falhas de
plantio e variação de altura. Duas passadas pela mesma rua enxergam as mesmas
plantas — é o que permite testar a composição da cópia 3D, como no campo.

Doença e praga vêm de focos (reboleiras): cada foco tem centro, raio e
intensidade, e deixa as plantas ali mais baixas, menos verdes e, na nuvem de
pontos, com lesão ou folha comida. A foto que o rover tira dentro do foco mostra
o sintoma — e o modelo responde o que o modelo responderia: ferrugem ele
conhece; lagarta, não, e a foto vai para o agrônomo.

Em Python puro, como o resto do simulador. É ilustração: não serve para medir
nada sobre sensor nenhum.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from itertools import pairwise

from valtexa.services import geo, pointcloud

LEAVES = 5
POINTS_PER_LEAF = 4
STALK_POINTS = 4
GROUND_STEP_M = 0.3

Rgb = tuple[int, int, int]
HEALTHY_GREEN: Rgb = (56, 128, 44)
TIRED_GREEN: Rgb = (158, 146, 72)
STALK: Rgb = (122, 152, 84)
SOIL: Rgb = (112, 86, 62)


@dataclass(frozen=True, slots=True)
class Focus:
    """Uma reboleira: onde a lavoura tem o problema e o que o modelo diria dele."""

    lon: float
    lat: float
    radius_m: float
    drawn: str
    """O que a folha mostra — o que a lavoura tem de verdade."""

    model_label: str
    """O que o modelo responderia olhando a foto."""

    novelty: float = 0.4
    stunting: float = 0.2
    """Fração da altura perdida no centro do foco."""

    yellowing: float = 0.3
    """Perda do índice de verde no centro do foco."""

    lesion: Rgb = (150, 72, 30)
    """Cor das lesões na nuvem de pontos."""

    defoliation: float = 0.0
    """Fração da folha comida no centro — praga desfolhadora abre buracos na nuvem."""


@dataclass
class SimulatedCrop:
    """As plantas de um talhão, em grade, com os focos por cima."""

    boundary: list
    row_spacing_m: float = 0.5
    plant_spacing_m: float = 0.3
    row_azimuth_deg: float = 90.0
    height_m: float = 1.3
    gap_ratio: float = 0.04
    foci: list[Focus] = field(default_factory=list)
    seed: int = 11
    _origin: tuple[float, float] = field(init=False, repr=False)
    _rotation: float = field(init=False, repr=False)
    _foci: list[tuple[float, float, Focus]] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._origin = geo.centroid(self.boundary)
        # Mesma convenção de geo.boustrophedon: girar até as linhas ficarem
        # horizontais. u corre ao longo da linha, v atravessa as linhas.
        self._rotation = math.radians(self.row_azimuth_deg - 90.0)
        self._foci = [
            (*geo.to_local((focus.lon, focus.lat), *self._origin), focus) for focus in self.foci
        ]

    # --- consulta -------------------------------------------------------------
    def intensity_at(self, lon: float, lat: float) -> tuple[float, Focus | None]:
        """Quanto do problema há neste ponto (0 a 1) e de qual foco."""
        return self._intensity(*geo.to_local((lon, lat), *self._origin))

    def plants_along(self, path: list, reach_m: float) -> list[tuple]:
        """As plantas ao alcance do sensor numa passada, no plano do talhão.

        Cada item: ``(x, y, altura, copa, verde, intensidade, foco, linha, posição)``.
        """
        spacing, step = self.row_spacing_m, self.plant_spacing_m
        axis = [self._uv(geo.to_local((float(p[0]), float(p[1])), *self._origin)) for p in path]
        seen: set[tuple[int, int]] = set()
        found: list[tuple] = []
        for (u0, v0), (u1, v1) in pairwise(axis):
            m_low = math.ceil((min(v0, v1) - reach_m) / spacing - 0.5)
            m_high = math.floor((max(v0, v1) + reach_m) / spacing - 0.5)
            j_low = math.ceil((min(u0, u1) - reach_m) / step)
            j_high = math.floor((max(u0, u1) + reach_m) / step)
            for m in range(m_low, m_high + 1):
                for j in range(j_low, j_high + 1):
                    if (m, j) in seen or self._unit(m, j, 1) < self.gap_ratio:
                        continue
                    u = j * step + (self._unit(m, j, 2) - 0.5) * step * 0.25
                    v = (m + 0.5) * spacing + (self._unit(m, j, 3) - 0.5) * 0.04
                    if _distance_to_segment(u, v, u0, v0, u1, v1) > reach_m:
                        continue
                    seen.add((m, j))
                    found.append(self._plant(m, j, *self._xy(u, v)))
        return found

    def scan(self, path: list, reach_m: float) -> tuple[list[list[float]], bytes]:
        """O que o rover envia por passada: as plantas medidas e a nuvem de pontos.

        As plantas vão como ``[x, y, altura, copa, verde]`` em metros a partir do
        primeiro ponto do eixo — a origem declarada da passada.
        """
        ox, oy = geo.to_local((float(path[0][0]), float(path[0][1])), *self._origin)
        plants = self.plants_along(path, reach_m)
        rows = [
            [round(x - ox, 3), round(y - oy, 3), round(h, 3), round(c, 3), round(g, 3)]
            for x, y, h, c, g, *_ in plants
        ]
        points: list[tuple[float, float, float, int, int, int]] = []
        for plant in plants:
            points.extend(self._plant_points(plant, ox, oy))
        points.extend(self._ground(path, reach_m, ox, oy))
        return rows, pointcloud.encode(points)

    # --- geometria ------------------------------------------------------------
    def _uv(self, point: tuple[float, float]) -> tuple[float, float]:
        cos_a, sin_a = math.cos(self._rotation), math.sin(self._rotation)
        x, y = point
        return x * cos_a - y * sin_a, x * sin_a + y * cos_a

    def _xy(self, u: float, v: float) -> tuple[float, float]:
        cos_a, sin_a = math.cos(-self._rotation), math.sin(-self._rotation)
        return u * cos_a - v * sin_a, u * sin_a + v * cos_a

    def _intensity(self, x: float, y: float) -> tuple[float, Focus | None]:
        best, which = 0.0, None
        for fx, fy, focus in self._foci:
            distance = math.hypot(x - fx, y - fy)
            if distance < focus.radius_m:
                value = (1 - distance / focus.radius_m) ** 0.7
                if value > best:
                    best, which = value, focus
        return best, which

    def _plant(self, m: int, j: int, x: float, y: float) -> tuple:
        k, focus = self._intensity(x, y)
        # Fertilidade varia devagar pelo talhão; é o fundo sobre o qual o foco aparece.
        fertility = 1 + 0.07 * math.sin(x / 37.0) * math.cos(y / 29.0)
        noise = 1 + (self._unit(m, j, 4) - 0.5) * 0.16
        stunting = (focus.stunting if focus else 0.0) * k
        height = self.height_m * fertility * noise * (1 - stunting)
        canopy = max(0.2, 0.62 * height / self.height_m * (1 + (self._unit(m, j, 5) - 0.5) * 0.2))
        green = (
            0.78
            + (self._unit(m, j, 6) - 0.5) * 0.08
            + 0.03 * math.sin(x / 23.0)
            - (focus.yellowing if focus else 0.0) * k
        )
        return (x, y, height, canopy, min(1.0, max(0.0, green)), k, focus, m, j)

    def _plant_points(self, plant: tuple, ox: float, oy: float) -> list:
        x, y, height, canopy, green, k, focus, m, j = plant
        px, py = x - ox, y - oy
        leaf_color = _tint(green)
        points = [
            (px, py, height * 0.85 * i / (STALK_POINTS - 1), *STALK) for i in range(STALK_POINTS)
        ]
        turn = self._unit(m, j, 7) * math.tau
        for leaf in range(LEAVES):
            angle = turn + leaf * 2.4
            cos_a, sin_a = math.cos(angle), math.sin(angle)
            attach = height * (0.2 + 0.6 * leaf / LEAVES)
            length = canopy * (0.95 - 0.35 * leaf / LEAVES)
            for p in range(1, POINTS_PER_LEAF + 1):
                t = p / POINTS_PER_LEAF
                reach = length * t
                side = 0.025 if p % 2 else -0.025
                color = leaf_color
                if focus is not None:
                    roll = self._unit(m, j, 100 + leaf * 10 + p)
                    if roll < focus.defoliation * k:
                        continue
                    if roll < 0.55 * k:
                        color = focus.lesion
                points.append(
                    (
                        px + cos_a * reach - sin_a * side,
                        py + sin_a * reach + cos_a * side,
                        attach + length * (0.45 * t - 0.6 * t * t),
                        *color,
                    )
                )
        return points

    def _ground(self, path: list, reach_m: float, ox: float, oy: float) -> list:
        """O chão da rua, para a nuvem ter onde se apoiar."""
        axis = [geo.to_local((float(p[0]), float(p[1])), *self._origin) for p in path]
        points = []
        for (x0, y0), (x1, y1) in pairwise(axis):
            length = math.hypot(x1 - x0, y1 - y0)
            if length == 0:
                continue
            ux, uy = (x1 - x0) / length, (y1 - y0) / length
            across = int(2 * reach_m / GROUND_STEP_M)
            for i in range(int(length / GROUND_STEP_M) + 1):
                for n in range(across + 1):
                    s = -reach_m + n * GROUND_STEP_M
                    t = i * GROUND_STEP_M
                    shade = int((self._unit(i, n, 9) - 0.5) * 24)
                    points.append(
                        (
                            x0 + ux * t - uy * s - ox,
                            y0 + uy * t + ux * s - oy,
                            (self._unit(i, n, 10) - 0.5) * 0.03,
                            SOIL[0] + shade,
                            SOIL[1] + shade,
                            SOIL[2] + shade,
                        )
                    )
        return points

    def _unit(self, a: int, b: int, salt: int) -> float:
        """Ruído determinístico em [0, 1): a mesma planta é a mesma em toda passada."""
        value = 0x811C9DC5
        for item in (self.seed, a, b, salt):
            value = ((value ^ (item & 0xFFFFFFFF)) * 0x01000193) & 0xFFFFFFFF
        value ^= value >> 15
        value = (value * 0x2C1B3C6D) & 0xFFFFFFFF
        value ^= value >> 12
        return value / 4_294_967_296


def _tint(green: float) -> Rgb:
    """Cor da folha pelo índice de verde: sadia é verde; cansada puxa para o palha."""
    t = min(1.0, max(0.0, (0.8 - green) / 0.45))
    return tuple(int(a + (b - a) * t) for a, b in zip(HEALTHY_GREEN, TIRED_GREEN, strict=True))  # type: ignore[return-value]


def _distance_to_segment(u: float, v: float, u0: float, v0: float, u1: float, v1: float) -> float:
    du, dv = u1 - u0, v1 - v0
    length = du * du + dv * dv
    t = 0.0 if length == 0 else max(0.0, min(1.0, ((u - u0) * du + (v - v0) * dv) / length))
    return math.hypot(u - (u0 + du * t), v - (v0 + dv * t))
