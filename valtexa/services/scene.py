"""A cópia 3D do talhão, composta das passadas do rover.

Cada passada (:class:`~valtexa.models.RowScan`) cobre uma faixa: o eixo
percorrido mais o alcance do sensor para cada lado. A cópia é a sobreposição
dessas faixas, **a mais recente por cima**. O que uma passada nova enxergou
substitui o que havia ali — inclusive a ausência: uma planta que sumiu
(arrancada, acamada, colhida) deixa de aparecer quando o rover passa de novo, em
vez de ficar congelada na cópia para sempre.

O que nenhuma passada cobriu fica vazio. É deliberado: preencher o talhão com
plantas "prováveis" transformaria a cópia numa ilustração, e o produtor
decidiria olhando para algo que ninguém mediu.

Doença e praga entram pelas observações. Cada foto diagnosticada vira um
marcador preso à planta fotografada — e só a ela. Nada é diagnosticado por
vizinhança: a planta ao lado de uma ferrugem não ganha ferrugem na cópia. O que
a cópia mostra para *todas* as plantas é o que o sensor mediu em todas: altura,
copa e o índice de verde, que acusa clorose e lesão sem dizer a causa.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from datetime import UTC, date, datetime, timedelta
from itertools import pairwise
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.orm import Session

from valtexa.models import (
    Device,
    Diagnosis,
    Farm,
    Field,
    Mission,
    MissionKind,
    MissionSegment,
    MissionState,
    Observation,
    RowScan,
    SegmentState,
    Zone,
    as_utc,
)
from valtexa.services import geo
from valtexa.services.taxonomy import categorize

SCAN_HORIZON_DAYS = 365
"""Passadas mais velhas que isso não entram: são de outra safra."""

FOOTPRINT_CELL_M = 0.25
"""Resolução da grade que decide qual passada é a dona de cada pedaço do chão."""

SAME_PLANT_M = 0.10
"""Duas plantas a menos disso, em passadas vizinhas, são a mesma planta."""

MARKER_REACH_M = 0.6
"""Distância máxima entre a foto e a planta a que ela é presa."""

DEVICE_MARGIN_M = 60.0
"""Um robô até esta distância do limite aparece na cópia (a base fica fora do talhão)."""

MAX_MARKERS = 5_000

ACTIVE_MISSION_STATES = (
    MissionState.DISPATCHED,
    MissionState.RUNNING,
    MissionState.PAUSED,
    MissionState.PAUSED_FOR_RECHARGE,
    MissionState.READY_TO_RESUME,
)


class _Footprint:
    """Grade de ocupação: para cada célula, a passada mais recente que a cobriu.

    As passadas são marcadas da mais nova para a mais velha, e a primeira a
    marcar uma célula fica com ela. Consultar a grade responde, em tempo
    constante, "alguma passada mais nova enxergou este ponto?".
    """

    def __init__(self, cell: float = FOOTPRINT_CELL_M) -> None:
        self.cell = cell
        self.cells: dict[tuple[int, int], int] = {}

    def mark(self, path: list[tuple[float, float]], reach: float, index: int) -> None:
        step = self.cell * 0.8
        for (x0, y0), (x1, y1) in pairwise(path):
            length = math.hypot(x1 - x0, y1 - y0)
            if length == 0:
                continue
            ux, uy = (x1 - x0) / length, (y1 - y0) / length
            nx, ny = -uy, ux
            along = max(1, math.ceil(length / step))
            across = max(1, math.ceil(2 * reach / step))
            for i in range(along + 1):
                t = length * i / along
                cx, cy = x0 + ux * t, y0 + uy * t
                for j in range(across + 1):
                    s = -reach + 2 * reach * j / across
                    self.cells.setdefault(self._key(cx + nx * s, cy + ny * s), index)

    def owner(self, x: float, y: float) -> int | None:
        return self.cells.get(self._key(x, y))

    def area_m2(self) -> float:
        return len(self.cells) * self.cell * self.cell

    def _key(self, x: float, y: float) -> tuple[int, int]:
        return math.floor(x / self.cell), math.floor(y / self.cell)


class _Plants:
    """As plantas da cópia, em colunas, com um índice espacial por cima."""

    def __init__(self, cell: float = 0.25) -> None:
        self.cell = cell
        self.grid: dict[tuple[int, int], list[int]] = defaultdict(list)
        self.x: list[float] = []
        self.y: list[float] = []
        self.height: list[float] = []
        self.canopy: list[float] = []
        self.greenness: list[float | None] = []
        self.scan: list[int] = []

    def add(self, x: float, y: float, plant: list, scan: int) -> None:
        self.grid[(math.floor(x / self.cell), math.floor(y / self.cell))].append(len(self.x))
        self.x.append(x)
        self.y.append(y)
        self.height.append(float(plant[2]))
        self.canopy.append(float(plant[3]))
        self.greenness.append(float(plant[4]) if len(plant) > 4 else None)
        self.scan.append(scan)

    def nearest(self, x: float, y: float, radius: float) -> int | None:
        reach = math.ceil(radius / self.cell)
        cx, cy = math.floor(x / self.cell), math.floor(y / self.cell)
        best, best_distance = None, radius * radius
        for i in range(cx - reach, cx + reach + 1):
            for j in range(cy - reach, cy + reach + 1):
                for index in self.grid.get((i, j), ()):
                    distance = (self.x[index] - x) ** 2 + (self.y[index] - y) ** 2
                    if distance <= best_distance:
                        best, best_distance = index, distance
        return best

    def columns(self) -> dict:
        return {
            "x": [round(value, 2) for value in self.x],
            "y": [round(value, 2) for value in self.y],
            "height": [round(value, 2) for value in self.height],
            "canopy": [round(value, 2) for value in self.canopy],
            "greenness": [None if value is None else round(value, 3) for value in self.greenness],
            "scan": self.scan,
        }


def scan_summary(scan: RowScan) -> dict:
    """Os campos de :class:`~valtexa.schemas.RowScanOut`."""
    return {
        "id": scan.id,
        "field_id": scan.field_id,
        "mission_id": scan.mission_id,
        "device_id": scan.device_id,
        "sequence_number": scan.sequence_number,
        "segment_index": scan.segment_index,
        "row_index": scan.row_index,
        "captured_at": scan.captured_at,
        "sensor": scan.sensor,
        "reach_m": scan.reach_m,
        "length_m": round(scan.length_m, 2),
        "plant_count": scan.plant_count,
        "mean_height_m": scan.mean_height_m,
        "max_height_m": scan.max_height_m,
        "point_count": scan.point_count,
        "has_pointcloud": scan.pointcloud_asset_id is not None,
    }


def build(
    session: Session,
    tenant_id: str,
    field_row: Field,
    *,
    at: datetime | None = None,
    days: int = 30,
    include_diagnoses: bool = True,
) -> dict:
    """Monta a cópia do talhão como ela estava em ``at`` (padrão: agora).

    ``days`` recorta as observações — a cópia das plantas usa a passada mais
    recente de cada pedaço, por mais velha que seja, e cada rua diz de quando é.
    """
    live = at is None
    moment = as_utc(at) or datetime.now(UTC)
    since = moment - timedelta(days=days)
    origin_lon, origin_lat = geo.centroid(field_row.boundary)

    def local(lon: float, lat: float) -> tuple[float, float]:
        return geo.to_local((float(lon), float(lat)), origin_lon, origin_lat)

    scans = list(
        session.scalars(
            select(RowScan)
            .where(
                RowScan.tenant_id == tenant_id,
                RowScan.field_id == field_row.id,
                RowScan.captured_at <= moment,
                RowScan.captured_at >= moment - timedelta(days=SCAN_HORIZON_DAYS),
            )
            .order_by(RowScan.captured_at.desc(), RowScan.sequence_number.desc())
        )
    )

    # 1. Quem é dono de cada pedaço do chão: a passada mais nova que o enxergou.
    footprint = _Footprint()
    origins: list[tuple[float, float]] = []
    lanes: list[list[tuple[float, float]]] = []
    for index, scan in enumerate(scans):
        path = [local(point[0], point[1]) for point in scan.path]
        footprint.mark(path, scan.reach_m, index)
        origins.append(local(scan.origin_lon, scan.origin_lat))
        lanes.append(path)

    # 2. As plantas: cada uma vale enquanto nenhuma passada mais nova cobrir o lugar.
    plants = _Plants()
    for index, scan in enumerate(scans):
        ox, oy = origins[index]
        for plant in scan.plants:
            x, y = ox + float(plant[0]), oy + float(plant[1])
            owner = footprint.owner(x, y)
            if owner is not None and owner < index:
                continue
            if plants.nearest(x, y, SAME_PLANT_M) is not None:
                continue
            plants.add(x, y, plant, index)

    visible = Counter(plants.scan)

    # 3. As fotos diagnosticadas, presas à planta fotografada.
    markers: list[dict] = []
    counts: Counter[str] = Counter()
    per_scan: dict[int, Counter[str]] = defaultdict(Counter)
    if include_diagnoses:
        rows = _observations(session, tenant_id, field_row.id, since, moment)
        for observation, diagnosis in rows:
            label = diagnosis.effective_label if diagnosis else None
            category = categorize(label, diagnosis.status if diagnosis else None).value
            x, y = local(observation.lon, observation.lat)
            plant = plants.nearest(x, y, MARKER_REACH_M)
            scan_index = plants.scan[plant] if plant is not None else footprint.owner(x, y)
            counts[category] += 1
            if scan_index is not None:
                per_scan[scan_index][category] += 1
            markers.append(
                {
                    "observation_id": observation.id,
                    "diagnosis_id": diagnosis.id if diagnosis else None,
                    "x": round(x, 2),
                    "y": round(y, 2),
                    "z": round(plants.height[plant], 2) if plant is not None else 0.0,
                    "label": label,
                    "category": category,
                    "status": diagnosis.status if diagnosis else None,
                    "confidence": diagnosis.confidence if diagnosis else None,
                    "novelty_score": diagnosis.novelty_score if diagnosis else None,
                    "severity": diagnosis.severity if diagnosis else None,
                    "captured_at": observation.captured_at,
                    "plant": plant,
                    "scan": scan_index,
                }
            )

    device_names = _device_names(session, {scan.device_id for scan in scans})
    field_area = geo.area_ha(field_row.boundary) * 10_000.0
    scanned_area = footprint.area_m2()

    return {
        "field_id": field_row.id,
        "field_name": field_row.name,
        "crop": field_row.crop,
        "crop_stage": field_row.crop_stage,
        "row_azimuth_deg": field_row.row_azimuth_deg,
        "row_spacing_m": field_row.row_spacing_m,
        "origin_lon": origin_lon,
        "origin_lat": origin_lat,
        "at": moment,
        "since": since,
        "live": live,
        "boundary": [_round(local(*point)) for point in geo.as_points(field_row.boundary)],
        "zones": [
            {
                "id": zone.id,
                "name": zone.name,
                "boundary": [_round(local(*point)) for point in geo.as_points(zone.boundary)],
            }
            for zone in session.scalars(
                select(Zone).where(Zone.tenant_id == tenant_id, Zone.field_id == field_row.id)
            )
        ],
        "field_area_m2": round(field_area, 1),
        "scanned_area_m2": round(scanned_area, 1),
        "coverage_ratio": round(min(1.0, scanned_area / field_area), 4) if field_area else 0.0,
        "scans": [
            {
                **scan_summary(scan),
                "device_name": device_names.get(scan.device_id),
                "origin": _round(origins[index]),
                "path": [_round(point) for point in lanes[index]],
                "visible_plants": visible.get(index, 0),
                "markers": dict(per_scan.get(index, {})),
            }
            for index, scan in enumerate(scans)
        ],
        "plants": plants.columns(),
        "markers": markers,
        "counts": dict(counts),
        "devices": _devices(session, tenant_id, field_row, local) if live else [],
        "missions": _missions(session, tenant_id, field_row.id, local) if live else [],
        "passes": _passes(session, tenant_id, field_row),
    }


def _observations(
    session: Session, tenant_id: str, field_id: str, since: datetime, until: datetime
) -> list[tuple[Observation, Diagnosis | None]]:
    rows = list(
        session.scalars(
            select(Observation)
            .where(
                Observation.tenant_id == tenant_id,
                Observation.field_id == field_id,
                Observation.captured_at >= since,
                Observation.captured_at <= until,
            )
            .order_by(Observation.captured_at.desc())
            .limit(MAX_MARKERS)
        )
    )
    latest: dict[str, Diagnosis] = {}
    ids = [row.id for row in rows]
    # Em blocos: o SQLite antigo limita os parâmetros de uma consulta.
    for start in range(0, len(ids), 500):
        for diagnosis in session.scalars(
            select(Diagnosis)
            .where(Diagnosis.observation_id.in_(ids[start : start + 500]))
            .order_by(Diagnosis.created_at)
        ):
            latest[diagnosis.observation_id] = diagnosis
    return [(row, latest.get(row.id)) for row in rows]


def _device_names(session: Session, ids: set[str]) -> dict[str, str]:
    if not ids:
        return {}
    return {
        device.id: device.name
        for device in session.scalars(select(Device).where(Device.id.in_(list(ids))))
    }


def _devices(session: Session, tenant_id: str, field_row: Field, local) -> list[dict]:
    """Os robôs da fazenda que estão no talhão ou perto dele, agora."""
    corners = [local(*point) for point in geo.as_points(field_row.boundary)]
    x_min = min(x for x, _ in corners) - DEVICE_MARGIN_M
    x_max = max(x for x, _ in corners) + DEVICE_MARGIN_M
    y_min = min(y for _, y in corners) - DEVICE_MARGIN_M
    y_max = max(y for _, y in corners) + DEVICE_MARGIN_M

    found = []
    for device in session.scalars(
        select(Device).where(
            Device.tenant_id == tenant_id,
            Device.farm_id == field_row.farm_id,
            Device.last_lat.is_not(None),
            Device.last_lon.is_not(None),
        )
    ):
        x, y = local(device.last_lon, device.last_lat)
        if x_min <= x <= x_max and y_min <= y <= y_max:
            found.append(
                {
                    "id": device.id,
                    "name": device.name,
                    "kind": device.kind,
                    "x": round(x, 2),
                    "y": round(y, 2),
                    "battery_percent": device.battery_percent,
                    "last_seen_at": device.last_seen_at,
                    "active_mission_id": device.active_mission_id,
                }
            )
    return found


def _missions(session: Session, tenant_id: str, field_id: str, local) -> list[dict]:
    """Varreduras em andamento, com as ruas que ainda faltam."""
    result = []
    for mission in session.scalars(
        select(Mission).where(
            Mission.tenant_id == tenant_id,
            Mission.field_id == field_id,
            Mission.kind == MissionKind.SCOUT,
            Mission.state.in_(ACTIVE_MISSION_STATES),
        )
    ):
        segments = list(
            session.scalars(
                select(MissionSegment)
                .where(MissionSegment.mission_id == mission.id)
                .order_by(MissionSegment.index)
            )
        )
        pending = [segment for segment in segments if segment.state is not SegmentState.DONE]
        result.append(
            {
                "mission_id": mission.id,
                "state": mission.state,
                "segments": len(segments),
                "done": len(segments) - len(pending),
                "pending": [
                    [_round(local(point[0], point[1])) for point in segment.path]
                    for segment in pending
                ],
            }
        )
    return result


def _passes(session: Session, tenant_id: str, field_row: Field) -> list[dict]:
    """Em que dias o rover passou, no fuso da fazenda — é a régua do "estado em"."""
    farm = session.get(Farm, field_row.farm_id)
    try:
        zone = ZoneInfo(farm.timezone if farm else "UTC")
    except ZoneInfoNotFoundError:
        zone = ZoneInfo("UTC")

    per_day: Counter[date] = Counter()
    for captured_at in session.scalars(
        select(RowScan.captured_at).where(
            RowScan.tenant_id == tenant_id, RowScan.field_id == field_row.id
        )
    ):
        per_day[as_utc(captured_at).astimezone(zone).date()] += 1
    return [{"day": day, "scans": count} for day, count in sorted(per_day.items())]


def _round(point: tuple[float, float]) -> list[float]:
    return [round(point[0], 2), round(point[1], 2)]
