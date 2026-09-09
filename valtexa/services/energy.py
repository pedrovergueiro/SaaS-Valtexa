"""Política de energia — calculada na nuvem, decidida no robô.

A distinção é a coisa mais importante deste módulo. A nuvem **calcula** a
política e a embarca na missão; quem decide voltar é o robô, sozinho, com o
número que já tem na memória. Se a decisão de retorno dependesse de uma
requisição, um drone com 12% de bateria e sem sinal ficaria esperando resposta
até cair.

A nuvem só acompanha, e usa a telemetria para saber se a política está calibrada
— um robô que sempre volta com 45% está desperdiçando missão; um que volta com
8% está com a reserva mal dimensionada.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from valtexa.config import settings
from valtexa.models import EnergyState
from valtexa.services import geo
from valtexa.services.hal import Capabilities

RETURN_MARGIN = 1.30
"""Fator sobre a energia de retorno calculada.

30% cobre o que a conta não modela: vento contrário, desvio de obstáculo, a
tentativa de pouso que não engata. É margem para o mundo real, não folga
arbitrária.
"""


@dataclass(frozen=True, slots=True)
class EnergyPolicy:
    """O que o robô carrega e aplica sem perguntar."""

    reserve_percent: float
    """Reserva intocável, **além** da energia estimada de retorno."""

    emergency_percent: float
    """Abaixo disso o robô pousa onde estiver, em vez de tentar voltar."""

    estimated_return_percent: float
    """Custo estimado do retorno do ponto mais distante da missão."""

    abort_below_percent: float
    """Soma de retorno e reserva: o gatilho de ``RETURN_TO_BASE``."""

    def as_dict(self) -> dict:
        return asdict(self)

    def state_for(self, battery_percent: float) -> EnergyState:
        """O estado que o robô assume com esta carga.

        Esta função é a referência que o firmware reproduz. Ver
        ``docs/DRONE_INTEGRATION.md``.
        """
        if battery_percent <= self.emergency_percent:
            return EnergyState.EMERGENCY_RETURN
        if battery_percent <= self.abort_below_percent:
            return EnergyState.RETURN_TO_BASE
        if battery_percent <= self.abort_below_percent + 10.0:
            return EnergyState.LOW_BATTERY
        return EnergyState.NORMAL


def policy_for(
    capabilities: Capabilities,
    target_polygon: list,
    base_lat: float | None,
    base_lon: float | None,
) -> EnergyPolicy:
    """Monta a política de uma missão.

    Sem base cadastrada, o retorno não é estimável — e a política assume o pior
    caso configurado em vez de fingir que o custo é zero.
    """
    reserve = settings.energy_reserve_percent
    emergency = settings.energy_emergency_percent

    if base_lat is None or base_lon is None:
        return EnergyPolicy(
            reserve_percent=reserve,
            emergency_percent=emergency,
            estimated_return_percent=reserve,
            abort_below_percent=min(95.0, reserve * 2),
        )

    farthest = _farthest_distance_m(target_polygon, base_lon, base_lat)
    speed = max(0.1, capabilities.cruise_speed_ms)
    endurance_s = max(60.0, capabilities.endurance_minutes * 60.0)

    # Percentual da autonomia consumido no trajeto de volta.
    return_percent = min(90.0, (farthest / speed) / endurance_s * 100.0 * RETURN_MARGIN)

    return EnergyPolicy(
        reserve_percent=reserve,
        emergency_percent=emergency,
        estimated_return_percent=round(return_percent, 2),
        abort_below_percent=round(min(95.0, return_percent + reserve), 2),
    )


def _farthest_distance_m(polygon: list, base_lon: float, base_lat: float) -> float:
    """Distância da base ao vértice mais distante da área de trabalho."""
    try:
        points = geo.as_points(polygon)
    except geo.InvalidPolygonError:
        return 0.0
    return max(geo.haversine_m(base_lon, base_lat, lon, lat) for lon, lat in points)
