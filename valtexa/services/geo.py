"""Geometria de campo, sem dependência espacial externa.

Um polígono é uma lista de ``[longitude, latitude]`` em WGS84, sem repetir o
primeiro ponto no fim. As funções aqui são puras e determinísticas — é isso que
permite testar a cerca virtual sem banco, sem rede e sem PostGIS, e é isso que
faz o mesmo código rodar no firmware do robô.

**Sobre a projeção.** Um talhão tem alguns quilômetros. Nessa escala, converter
graus para metros com a aproximação local (1° de latitude ≈ 111 320 m, e a
longitude encurtando por ``cos(latitude)``) erra na casa dos centímetros, bem
abaixo da precisão do RTK. Trigonometria esférica completa aqui seria custo sem
ganho. Para distância entre pontos distantes, :func:`haversine_m` usa a fórmula
esférica de verdade.
"""

from __future__ import annotations

import math

EARTH_RADIUS_M = 6_371_008.8
"""Raio médio da Terra (IUGG), em metros."""

METERS_PER_DEGREE_LAT = 111_320.0

EDGE_TOLERANCE = 1e-12
"""Tolerância do teste de aresta, em graus ao quadrado.

Absorve o erro de ponto flutuante de quem monta o polígono, e nada além
disso — em graus decimais equivale a fração de milímetro.
"""

Point = tuple[float, float]
"""``(longitude, latitude)``. A ordem é a do GeoJSON, não a de um GPS de bolso."""


class InvalidPolygonError(ValueError):
    """O polígono não tem forma utilizável."""


def as_points(polygon: list) -> list[Point]:
    """Normaliza e valida um polígono vindo do JSON.

    Recusa qualquer coisa que não seja um anel fechável de três vértices — um
    polígono degenerado passaria silenciosamente e transformaria a cerca virtual
    numa checagem que sempre aprova.
    """
    if not isinstance(polygon, list) or len(polygon) < 3:
        raise InvalidPolygonError("Um polígono precisa de ao menos 3 vértices.")

    points: list[Point] = []
    for vertex in polygon:
        if not isinstance(vertex, list | tuple) or len(vertex) < 2:
            raise InvalidPolygonError(f"Vértice inválido: {vertex!r}. Esperado [lon, lat].")
        lon, lat = float(vertex[0]), float(vertex[1])
        if not -180.0 <= lon <= 180.0 or not -90.0 <= lat <= 90.0:
            raise InvalidPolygonError(f"Coordenada fora do intervalo válido: [{lon}, {lat}].")
        points.append((lon, lat))

    # Um anel repetido no fim é comum em GeoJSON; aqui ele viraria uma aresta de
    # comprimento zero.
    if len(points) > 3 and points[0] == points[-1]:
        points.pop()
    if len(points) < 3:
        raise InvalidPolygonError("Um polígono precisa de ao menos 3 vértices distintos.")
    return points


def contains_point(
    polygon: list, lon: float, lat: float, *, include_boundary: bool = False
) -> bool:
    """Se o ponto está dentro do polígono, pelo teste de paridade de raios.

    O ponto sobre a aresta é decidido **antes** da paridade, e isso não é
    preciosismo: o teste de paridade sozinho responde "dentro" numa borda e
    "fora" na oposta, dependendo de que lado o raio parte. Deixar a borda
    ambígua tornaria a cerca virtual dependente da ordem dos vértices.

    Os dois usos do sistema querem regras opostas na borda, e por isso ela é
    explícita:

    * ``include_boundary=False`` (padrão) — *onde o robô está*. Na dúvida, fora.
      Melhor recusar um ponto na linha do que autorizar um voo que sai da área
      por um centímetro.
    * ``include_boundary=True`` — *se uma área cabe em outra*. Aqui a borda
      coincidente é contenção legítima: uma missão que ocupa exatamente a área
      permitida está dentro dela, não fora.

    A tolerância de :data:`EDGE_TOLERANCE` cobre ruído de ponto flutuante, não
    distância operacional. A folga real vem de :func:`shrink`.
    """
    points = as_points(polygon)
    count = len(points)

    if any(
        _on_segment((lon, lat), points[index], points[(index + 1) % count])
        for index in range(count)
    ):
        return include_boundary

    inside = False
    for index in range(count):
        lon_a, lat_a = points[index]
        lon_b, lat_b = points[(index + 1) % count]

        # A aresta cruza a horizontal que passa pelo ponto?
        if (lat_a > lat) != (lat_b > lat):
            # Longitude do cruzamento, interpolada na aresta.
            crossing = lon_a + (lat - lat_a) * (lon_b - lon_a) / (lat_b - lat_a)
            if lon < crossing:
                inside = not inside

    return inside


def contains_all(polygon: list, points: list, *, include_boundary: bool = False) -> bool:
    """Se todos os pontos estão dentro."""
    return all(
        contains_point(polygon, point[0], point[1], include_boundary=include_boundary)
        for point in points
    )


def polygon_contains_polygon(outer: list, inner: list) -> bool:
    """Se ``inner`` está inteiramente dentro de ``outer``.

    Aproximação por vértices: correta para os polígonos convexos ou levemente
    côncavos de um talhão. Um ``outer`` fortemente côncavo poderia conter todos
    os vértices de ``inner`` e ainda assim ser atravessado por uma aresta dele.
    A checagem de aresta está em :func:`edges_cross` e é usada junto com esta em
    :mod:`valtexa.services.safety_engine`.

    Borda coincidente conta como dentro: uma missão planejada exatamente sobre a
    área permitida está contida nela. Recusar isso bloquearia, por construção,
    toda missão que usa a área máxima disponível.
    """
    return contains_all(outer, as_points(inner), include_boundary=True)


def edges_cross(outer: list, inner: list) -> bool:
    """Se alguma aresta de ``inner`` cruza alguma aresta de ``outer``.

    É a metade que falta do teste de contenção: junto com
    :func:`polygon_contains_polygon`, cobre o talhão em forma de C, onde os
    vértices caem dentro mas a área não.
    """
    outer_points = as_points(outer)
    inner_points = as_points(inner)
    return any(
        _segments_intersect(
            outer_points[i],
            outer_points[(i + 1) % len(outer_points)],
            inner_points[j],
            inner_points[(j + 1) % len(inner_points)],
        )
        for i in range(len(outer_points))
        for j in range(len(inner_points))
    )


def shrink(polygon: list, margin_m: float) -> list[Point]:
    """Encolhe o polígono ``margin_m`` metros em direção ao centroide.

    A margem existe para que a deriva de posição não empurre o robô para fora da
    área autorizada. Encolher em direção ao centroide é uma aproximação de
    *buffer* negativo: exata em polígono regular, conservadora nos demais — e o
    erro sempre reduz a área permitida, nunca a aumenta, que é o lado seguro.
    """
    points = as_points(polygon)
    if margin_m <= 0:
        return points

    center_lon = sum(point[0] for point in points) / len(points)
    center_lat = sum(point[1] for point in points) / len(points)

    shrunk: list[Point] = []
    for lon, lat in points:
        distance = haversine_m(lon, lat, center_lon, center_lat)
        if distance <= margin_m:
            # A margem consumiria o polígono inteiro. Colapsar no centroide faz
            # toda checagem posterior falhar — que é o resultado correto: essa
            # área é pequena demais para operar com esta tolerância.
            return [(center_lon, center_lat)] * 3
        factor = (distance - margin_m) / distance
        shrunk.append(
            (center_lon + (lon - center_lon) * factor, center_lat + (lat - center_lat) * factor)
        )
    return shrunk


def area_ha(polygon: list) -> float:
    """Área em hectares, pela fórmula do laço (*shoelace*) em metros locais."""
    points = as_points(polygon)
    center_lat = sum(point[1] for point in points) / len(points)
    scale_lon = METERS_PER_DEGREE_LAT * math.cos(math.radians(center_lat))

    total = 0.0
    for index in range(len(points)):
        lon_a, lat_a = points[index]
        lon_b, lat_b = points[(index + 1) % len(points)]
        total += (lon_a * scale_lon) * (lat_b * METERS_PER_DEGREE_LAT) - (
            lon_b * scale_lon
        ) * (lat_a * METERS_PER_DEGREE_LAT)
    return abs(total) / 2.0 / 10_000.0


def haversine_m(lon_a: float, lat_a: float, lon_b: float, lat_b: float) -> float:
    """Distância sobre a superfície, em metros."""
    phi_a, phi_b = math.radians(lat_a), math.radians(lat_b)
    delta_phi = phi_b - phi_a
    delta_lambda = math.radians(lon_b - lon_a)
    inner = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi_a) * math.cos(phi_b) * math.sin(delta_lambda / 2) ** 2
    )
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(min(1.0, inner)))


def path_length_m(path: list) -> float:
    """Comprimento de uma polilinha, em metros."""
    points = [(float(p[0]), float(p[1])) for p in path]
    return sum(
        haversine_m(points[i][0], points[i][1], points[i + 1][0], points[i + 1][1])
        for i in range(len(points) - 1)
    )


def bounding_box(polygon: list) -> tuple[float, float, float, float]:
    """``(lon_min, lat_min, lon_max, lat_max)``."""
    points = as_points(polygon)
    lons = [point[0] for point in points]
    lats = [point[1] for point in points]
    return min(lons), min(lats), max(lons), max(lats)


def centroid(polygon: list) -> Point:
    """Centro geométrico simples dos vértices."""
    points = as_points(polygon)
    return (
        sum(point[0] for point in points) / len(points),
        sum(point[1] for point in points) / len(points),
    )


def boustrophedon(polygon: list, swath_m: float) -> list[list[Point]]:
    """Planeja a cobertura em vaivém — as passadas de ida e volta do rover.

    Cada faixa vira um segmento independente da missão, e é a segmentação que
    torna a retomada possível: um rover que voltou para recarregar continua da
    faixa seguinte em vez de refazer a lavoura inteira.

    Varre no eixo leste-oeste por simplicidade. Alinhar as faixas à direção real
    das linhas de plantio é o próximo passo — precisa do azimute da linha, que
    ainda não é coletado.
    """
    if swath_m <= 0:
        raise ValueError("A largura da faixa precisa ser positiva.")

    points = as_points(polygon)
    lon_min, lat_min, lon_max, lat_max = bounding_box(points)
    center_lat = (lat_min + lat_max) / 2
    step_lat = swath_m / METERS_PER_DEGREE_LAT

    stripes: list[list[Point]] = []
    latitude = lat_min + step_lat / 2
    going_east = True

    while latitude < lat_max:
        crossings = _horizontal_crossings(points, latitude)
        for start_lon, end_lon in _pair_up(crossings):
            leg = [(start_lon, latitude), (end_lon, latitude)]
            stripes.append(leg if going_east else leg[::-1])
            going_east = not going_east
        latitude += step_lat

    # Um polígono mais estreito que uma faixa não produziria passada nenhuma.
    # Uma travessia pelo meio é melhor do que um plano vazio.
    if not stripes:
        stripes.append([(lon_min, center_lat), (lon_max, center_lat)])
    return stripes


def _horizontal_crossings(points: list[Point], latitude: float) -> list[float]:
    """Longitudes em que a horizontal ``latitude`` corta as arestas do polígono."""
    crossings: list[float] = []
    for index in range(len(points)):
        lon_a, lat_a = points[index]
        lon_b, lat_b = points[(index + 1) % len(points)]
        if (lat_a > latitude) != (lat_b > latitude):
            crossings.append(lon_a + (latitude - lat_a) * (lon_b - lon_a) / (lat_b - lat_a))
    return sorted(crossings)


def _pair_up(values: list[float]) -> list[tuple[float, float]]:
    """Agrupa cruzamentos em pares entra/sai, descartando um sobrando."""
    return [(values[i], values[i + 1]) for i in range(0, len(values) - 1, 2)]


def _orientation(a: Point, b: Point, c: Point) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _on_segment(point: Point, start: Point, end: Point) -> bool:
    """Se o ponto está sobre o segmento, dentro da tolerância."""
    cross = (end[0] - start[0]) * (point[1] - start[1]) - (end[1] - start[1]) * (
        point[0] - start[0]
    )
    if abs(cross) > EDGE_TOLERANCE:
        return False
    return (
        min(start[0], end[0]) - EDGE_TOLERANCE <= point[0] <= max(start[0], end[0]) + EDGE_TOLERANCE
        and min(start[1], end[1]) - EDGE_TOLERANCE
        <= point[1]
        <= max(start[1], end[1]) + EDGE_TOLERANCE
    )


def _segments_intersect(a1: Point, a2: Point, b1: Point, b2: Point) -> bool:
    """Se dois segmentos se cruzam propriamente (sem contar toque em vértice)."""
    d1 = _orientation(b1, b2, a1)
    d2 = _orientation(b1, b2, a2)
    d3 = _orientation(a1, a2, b1)
    d4 = _orientation(a1, a2, b2)
    return ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0))
