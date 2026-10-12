"""Rover, drone e dock simulados.

Cada um reproduz o comportamento que o firmware precisa ter — principalmente as
decisões que o robô toma **sozinho**:

* o rover mede a própria energia e decide voltar à base sem perguntar à nuvem;
* o drone verifica a assinatura da missão e a cerca virtual antes de abrir o
  bico, e fecha por conta própria se a trilha sair da área;
* a dock informa o vento, que é o dado sem o qual a pulverização é bloqueada.

Quando o hardware existir, ele substitui estas classes. A nuvem não muda.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from datetime import UTC, datetime

from simulator.client import DeviceClient
from simulator.leaf import leaf_png
from simulator.plants import SimulatedCrop
from valtexa.models.enums import EnergyState, RtkFix
from valtexa.services import geo
from valtexa.services.ai_pipeline import SIMULATION_MARKER


def frame_with_label(
    label: str, novelty: float = 0.4, seed: int = 0, drawn: str | None = None
) -> bytes:
    """Monta um quadro que carrega a resposta esperada.

    PNG ignora bytes depois do ``IEND``, então a etiqueta viaja junto sem
    corromper o arquivo. É andaime de simulação, e o único lugar do sistema que
    o lê é o :class:`~valtexa.services.ai_pipeline.SimulatedAnalyzer`. A folha
    desenhada é só para quem olha a foto no console.

    ``drawn`` separa o que a folha tem do que o modelo responde: bicho-mineiro
    desenhado com a etiqueta "Cercospora_Leaf_Spot" é exatamente o caso de uma praga fora do
    catálogo — o modelo arrisca uma doença, com novidade alta, e a foto vai para
    o agrônomo.
    """
    marker = SIMULATION_MARKER + f"{label}:{novelty}".encode("ascii")
    return leaf_png(drawn or label, novelty, seed) + marker


@dataclass
class Battery:
    """Bateria simples, com decisão local de retorno.

    O ponto do simulador não é modelar química: é reproduzir que **o robô decide
    sozinho**. Uma decisão de retorno que dependesse da nuvem deixaria um drone
    com 12% de carga e sem sinal esperando resposta até cair.
    """

    percent: float = 100.0
    drain_per_meter: float = 0.02
    drain_per_second: float = 0.01

    def travel(self, meters: float, seconds: float = 0.0) -> None:
        self.percent = max(
            0.0, self.percent - meters * self.drain_per_meter - seconds * self.drain_per_second
        )

    @classmethod
    def do_perfil(cls, perfil, percent: float = 100.0) -> Battery:
        """Bateria com o consumo do perfil de autonomia do rover.

        Os dois coeficientes saem do mesmo lugar que o planejador usa — ver
        ``valtexa/services/planner.py``. Manter um número inventado aqui faria o
        simulador contradizer o plano que a própria plataforma calcula, e a
        demonstração mostraria um rover parando onde o painel promete que ele
        chega.
        """
        return cls(
            percent=percent,
            drain_per_meter=100.0 * perfil.wh_per_m / perfil.battery_wh,
            drain_per_second=100.0 * (perfil.wh_per_h / 3600.0) / perfil.battery_wh,
        )

    def recharge(self) -> None:
        self.percent = 100.0

    def state(self, policy: dict) -> EnergyState:
        """Aplica a política embarcada. Espelha ``EnergyPolicy.state_for``."""
        emergency = float(policy.get("emergency_percent", 10.0))
        abort_below = float(policy.get("abort_below_percent", 30.0))
        if self.percent <= emergency:
            return EnergyState.EMERGENCY_RETURN
        if self.percent <= abort_below:
            return EnergyState.RETURN_TO_BASE
        if self.percent <= abort_below + 10.0:
            return EnergyState.LOW_BATTERY
        return EnergyState.NORMAL


@dataclass
class SimulatedDevice:
    """Base comum: telemetria, eventos e buffer offline."""

    client: DeviceClient
    name: str
    battery: Battery = field(default_factory=Battery)
    lat: float = 0.0
    lon: float = 0.0
    online: bool = True
    log: list[str] = field(default_factory=list)
    _buffer_samples: list[dict] = field(default_factory=list, init=False)
    _buffer_events: list[dict] = field(default_factory=list, init=False)

    def say(self, message: str) -> None:
        line = f"[{self.name}] {message}"
        self.log.append(line)
        print(line)

    def telemetry(self, **extra: object) -> dict:
        return {
            "sequence_number": self.client.next_sequence(),
            "recorded_at": datetime.now(UTC).isoformat(),
            "lat": self.lat,
            "lon": self.lon,
            "battery_percent": round(self.battery.percent, 2),
            "rtk_fix": RtkFix.FIXED.value,
            "link_quality": 1.0 if self.online else 0.0,
            **extra,
        }

    def push_telemetry(self, **extra: object) -> None:
        """Envia — ou guarda, quando offline.

        Ficar sem enlace não pode significar perder dado. O robô continua
        medindo e acumula; a descarga acontece na reconexão.
        """
        sample = self.telemetry(**extra)
        if self.online:
            self.client.send_telemetry([sample])
        else:
            self._buffer_samples.append(sample)

    def push_event(self, event_type: str, severity: str = "info", **payload: object) -> None:
        record = {
            "sequence_number": self.client.next_sequence(),
            "type": event_type,
            "severity": severity,
            "occurred_at": datetime.now(UTC).isoformat(),
            "payload": payload,
        }
        if self.online:
            self.client.send_events([record])
        else:
            self._buffer_events.append(record)

    def go_offline(self) -> None:
        self.online = False
        self.say("perdeu o enlace — segue operando pela política embarcada")

    def reconnect(self, sync_id: str) -> dict:
        """Reconecta e descarrega o que ficou acumulado."""
        self.online = True
        if not self._buffer_samples and not self._buffer_events:
            return {"accepted": 0, "duplicated": 0, "rejected": 0}

        result = self.client.sync(sync_id, self._buffer_samples, self._buffer_events)
        self.say(
            f"reconectou e sincronizou {result['accepted']} registro(s) "
            f"({result['duplicated']} já conhecidos)"
        )
        self._buffer_samples.clear()
        self._buffer_events.clear()
        return result

    def move_to(self, lon: float, lat: float) -> float:
        """Move em linha reta, gastando bateria. Devolve a distância percorrida."""
        distance = geo.haversine_m(self.lon, self.lat, lon, lat) if (self.lat or self.lon) else 0.0
        self.lon, self.lat = lon, lat
        self.battery.travel(distance, seconds=distance / 1.5)
        return distance


@dataclass
class SimulatedRover(SimulatedDevice):
    """Rover Scout: percorre os segmentos e fotografa.

    Reproduz o comportamento que torna o produto viável em área grande: quando a
    energia acaba no meio, ele volta, recarrega e **continua de onde parou** em
    vez de refazer a lavoura.
    """

    photos_per_segment: int = 4
    disease_ratio: float = 0.0
    """Fração de quadros com doença. Do cenário, não do modelo."""

    disease_label: str = "Rust"
    novelty_ratio: float = 0.2
    """Fração de quadros que destoam do que os modelos conhecem.

    Numa lavoura real isso é o normal, não a exceção: sujeira na lente, folha
    fora de enquadramento, deficiência nutricional, praga que não está no
    catálogo. É esse material que enche a fila do agrônomo — e é dele que sai o
    dataset próprio.
    """

    field_id: str = ""
    seed: int = 7

    crop: SimulatedCrop | None = None
    """A lavoura que o sensor 3D enxerga.

    Com ela, cada rua percorrida vira uma passada da cópia 3D, e as fotos
    seguem os focos da lavoura em vez do sorteio de ``disease_ratio``.
    """

    scan_reach_m: float = 1.5
    """Alcance lateral do LiDAR, a partir do eixo. Metade da faixa do hardware."""

    photo_every_m: float = 12.0
    """Com a lavoura: uma foto de rotina a cada tantos metros."""

    symptom_every_m: float = 3.0
    """E uma a cada tantos metros onde o sensor vê sintoma — o robô prioriza o que destoa."""

    max_photos_per_segment: int = 12
    frames: list[tuple[str, dict]] = field(default_factory=list)
    """``(o que a folha mostrava, resposta da plataforma)`` de cada foto enviada."""

    def run_mission(self, payload: dict, base: tuple[float, float]) -> str:
        """Executa a missão até o fim ou até a bateria mandar voltar.

        Devolve ``"completed"`` ou ``"paused"``.
        """
        mission_id = payload["mission_id"]
        policy = payload.get("energy_policy") or {}
        rng = random.Random(self.seed)

        for segment in payload["segments"]:
            state = self.battery.state(policy)
            if state in {EnergyState.RETURN_TO_BASE, EnergyState.EMERGENCY_RETURN}:
                # Decisão local. A nuvem só fica sabendo depois.
                self.say(
                    f"bateria em {self.battery.percent:.0f}% ({state.value}): "
                    f"retornando à base antes do segmento {segment['index']}"
                )
                self.push_event("return_to_base", severity="warning", battery=self.battery.percent)
                self.move_to(*base)
                self.client.pause_mission(
                    mission_id,
                    reason=f"bateria em {self.battery.percent:.0f}%",
                    lat=self.lat,
                    lon=self.lon,
                    battery_percent=round(self.battery.percent, 2),
                )
                return "paused"

            self._walk_segment(mission_id, segment, rng)

        self.client.complete_mission(mission_id)
        self.say(f"missão concluída com {self.battery.percent:.0f}% de bateria")
        return "completed"

    def _walk_segment(self, mission_id: str, segment: dict, rng: random.Random) -> None:
        path = segment["path"]
        started = datetime.now(UTC)
        for lon, lat in path:
            self.move_to(lon, lat)
            self.push_telemetry(mission_id=mission_id, mission_state="running", speed_ms=1.2)

        photos = 0
        for index, (lon, lat, label, drawn, novelty) in enumerate(self._shots(path, rng)):
            response = self.client.upload_observation(
                metadata={
                    "sequence_number": self.client.next_sequence(),
                    "mission_id": mission_id,
                    "field_id": self.field_id,
                    "captured_at": datetime.now(UTC).isoformat(),
                    "lat": lat,
                    "lon": lon,
                    "model_input_ok": True,
                    "edge_summary": {"blur": 0.1, "leaf_fill": 0.8},
                },
                image=frame_with_label(
                    label, novelty, seed=segment["index"] * 100 + index, drawn=drawn
                ),
                filename=f"seg{segment['index']}_{index}.png",
            )
            self.frames.append((drawn, response))
            photos += 1

        scanned = ""
        if self.crop is not None:
            plants = self._scan(mission_id, segment, started)
            scanned = f", {plants} plantas na cópia 3D"

        self.client.complete_segment(
            mission_id,
            segment["index"],
            lat=self.lat,
            lon=self.lon,
            battery_percent=round(self.battery.percent, 2),
        )
        self.say(
            f"segmento {segment['index']} concluído "
            f"({photos} imagens{scanned}, bateria {self.battery.percent:.0f}%)"
        )

    def _shots(self, path: list, rng: random.Random):
        """Onde fotografar e o que cada foto mostra: ``(lon, lat, rótulo, desenho, novidade)``.

        Sem a lavoura, fotos igualmente espaçadas e doença por sorteio. Com ela,
        uma foto de rotina a cada ``photo_every_m`` e uma a cada
        ``symptom_every_m`` onde o sensor enxerga sintoma — o que o firmware de
        verdade faz para gastar enlace com o que importa.
        """
        if self.crop is None:
            for index in range(self.photos_per_segment):
                lon, lat = _interpolate(path, (index + 0.5) / self.photos_per_segment)
                label = self.disease_label if rng.random() < self.disease_ratio else "Healthy"
                novelty = 1.4 if rng.random() < self.novelty_ratio else 0.4
                yield lon, lat, label, label, novelty
            return

        length = geo.path_length_m(path)
        routine = max(1, round(self.photo_every_m / self.symptom_every_m))
        taken = 0
        step = 0
        while (step + 0.5) * self.symptom_every_m < length and taken < self.max_photos_per_segment:
            lon, lat = _interpolate(path, (step + 0.5) * self.symptom_every_m / length)
            intensity, focus = self.crop.intensity_at(lon, lat)
            step += 1
            if (step - 1) % routine and intensity < 0.3:
                continue
            taken += 1
            if focus is not None and rng.random() < min(1.0, intensity * 1.4):
                yield lon, lat, focus.model_label, focus.drawn, focus.novelty
            else:
                novelty = 1.4 if rng.random() < self.novelty_ratio else 0.4
                yield lon, lat, "Healthy", "Healthy", novelty

    def _scan(self, mission_id: str, segment: dict, started: datetime) -> int:
        """Envia a passada pela rua: as plantas medidas e a nuvem de pontos."""
        assert self.crop is not None
        path = segment["path"]
        plants, cloud = self.crop.scan(path, self.scan_reach_m)
        self.client.upload_row_scan(
            {
                "sequence_number": self.client.next_sequence(),
                "mission_id": mission_id,
                "field_id": self.field_id,
                "segment_index": segment["index"],
                "started_at": started.isoformat(),
                "captured_at": datetime.now(UTC).isoformat(),
                "sensor": "lidar",
                "origin_lon": path[0][0],
                "origin_lat": path[0][1],
                "path": path,
                "reach_m": self.scan_reach_m,
                "plants": plants,
            },
            cloud,
        )
        return len(plants)


@dataclass
class SimulatedDrone(SimulatedDevice):
    """Drone Action: aplica só dentro do polígono autorizado.

    A contenção é **local**. A nuvem confere depois, pela trilha, mas quem
    impede a calda de sair da área é o próprio drone, em tempo real — e é isso
    que continua valendo quando o enlace cai.
    """

    rate_l_ha: float = 0.75

    def run_spray(self, payload: dict) -> dict:
        """Executa uma missão de pulverização e devolve o resumo."""
        mission_id = payload["mission_id"]
        polygon = payload["target_polygon"]
        application = payload.get("application") or {}
        max_quantity = float(application.get("max_quantity_l") or 0.0)

        started = self.client.start_application(mission_id, application.get("tank_id"))
        self.say(f"aplicação iniciada (missão {mission_id[:8]})")

        track: list[list[float]] = []
        used = 0.0
        blocked = 0
        area_ha = geo.area_ha(polygon)

        exhausted = False
        for segment in payload["segments"]:
            if exhausted:
                break
            for lon, lat in _densify(segment["path"], step_m=8.0):
                self.move_to(lon, lat)
                self.push_telemetry(mission_id=mission_id, mission_state="running", alt_m=3.0)

                # Trava de bordo: fora do polígono, o bico fecha. É a verificação
                # que continua valendo com a nuvem fora do ar.
                if not geo.contains_point(polygon, lon, lat):
                    blocked += 1
                    continue

                if max_quantity and used >= max_quantity:
                    # Trava dura: o volume autorizado é um teto, não uma meta. O
                    # que sobrar de área fica para outra missão, com outra
                    # autorização.
                    self.say("volume autorizado esgotado: bico fechado")
                    exhausted = True
                    break

                dose = self.rate_l_ha * area_ha / max(1, _point_count(payload))
                used += dose
                track.append([lon, lat, round(dose, 4)])

            if not exhausted:
                # Mesmo contrato do rover: faixa terminada vira checkpoint. Sem
                # isso, um drone que cai no meio refaria a área já aplicada.
                self.client.complete_segment(
                    mission_id,
                    segment["index"],
                    lat=self.lat,
                    lon=self.lon,
                    battery_percent=round(self.battery.percent, 2),
                )

        result = self.client.stop_application(
            started["id"],
            amount_used_l=round(used, 3),
            area_ha=round(area_ha, 4),
            track=track,
            stop_reason="cobertura concluída",
        )
        self.client.complete_mission(mission_id)
        self.say(
            f"aplicação encerrada: {used:.2f} L em {area_ha:.2f} ha, "
            f"{blocked} ponto(s) bloqueado(s) por cerca virtual"
        )
        return result


@dataclass
class SimulatedDock(SimulatedDevice):
    """Dock: recarrega, reabastece e — o que mais importa — mede o vento.

    Sem leitura de vento o safety engine bloqueia toda pulverização. A dock é a
    fonte esperada desse dado justamente por ficar parada no talhão.
    """

    wind_ms: float = 3.2
    temperature_c: float = 26.0
    humidity: float = 62.0

    def report_weather(self) -> None:
        self.push_telemetry(
            sensors={
                "wind_ms": self.wind_ms,
                "temperature_c": self.temperature_c,
                "humidity_percent": self.humidity,
            },
            battery_percent=100.0,
        )
        self.say(f"vento {self.wind_ms:.1f} m/s, {self.temperature_c:.0f} °C")

    def recharge(self, device: SimulatedDevice) -> None:
        device.battery.recharge()
        self.push_event("battery_swapped", device=device.name)
        self.say(f"{device.name} recarregado a 100%")


def _interpolate(path: list, fraction: float) -> tuple[float, float]:
    """Ponto a uma fração do comprimento da polilinha."""
    if len(path) < 2:
        return float(path[0][0]), float(path[0][1])
    start, end = path[0], path[-1]
    return (
        float(start[0]) + (float(end[0]) - float(start[0])) * fraction,
        float(start[1]) + (float(end[1]) - float(start[1])) * fraction,
    )


def _densify(path: list, step_m: float) -> list[tuple[float, float]]:
    """Insere pontos intermediários para simular o voo contínuo."""
    if len(path) < 2:
        return [(float(p[0]), float(p[1])) for p in path]

    points: list[tuple[float, float]] = []
    for index in range(len(path) - 1):
        lon_a, lat_a = float(path[index][0]), float(path[index][1])
        lon_b, lat_b = float(path[index + 1][0]), float(path[index + 1][1])
        distance = geo.haversine_m(lon_a, lat_a, lon_b, lat_b)
        steps = max(1, math.ceil(distance / step_m))
        for step in range(steps):
            ratio = step / steps
            points.append((lon_a + (lon_b - lon_a) * ratio, lat_a + (lat_b - lat_a) * ratio))
    points.append((float(path[-1][0]), float(path[-1][1])))
    return points


def _point_count(payload: dict) -> int:
    return sum(len(segment["path"]) for segment in payload.get("segments", [])) or 1
