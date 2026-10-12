"""Camada de abstração de hardware.

O resto da plataforma nunca pergunta *qual* robô é este. Pergunta o que ele
consegue fazer, e a resposta vem do descritor de capacidades do modelo. É o que
permite trocar LiDAR, câmera, GNSS, controladora ou fabricante do motor — ou
receber o rover de um parceiro — sem mexer no planejamento, no motor de decisão
ou no safety engine.

Um descritor não declarado é um descritor **ausente**, e ausente é tratado como
"não tem". Nenhuma capacidade é presumida: um dispositivo que não declara
``spray`` jamais recebe missão de pulverização, mesmo que fisicamente consiga.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from valtexa.models.enums import DeviceKind

# --- chaves reconhecidas no JSON de capabilities ----------------------------
HAS_RTK = "has_rtk"
HAS_CAMERA_RGB = "has_camera_rgb"
HAS_CAMERA_MULTISPECTRAL = "has_camera_multispectral"
HAS_LIDAR = "has_lidar"
HAS_SPRAY = "has_spray"
CAN_FLY = "can_fly"
CAN_CHARGE = "can_charge"
CAN_SWAP_BATTERY = "can_swap_battery"
CAN_REFILL = "can_refill"
TANK_COUNT = "tank_count"
TANK_CAPACITY_L = "tank_capacity_l"
MAX_SPEED_MS = "max_speed_ms"
CRUISE_SPEED_MS = "cruise_speed_ms"
BATTERY_WH = "battery_wh"
ENDURANCE_MINUTES = "endurance_minutes"
SWATH_M = "swath_m"
CAMERA_GSD_MM_AT_1M = "camera_gsd_mm_at_1m"
MAX_PAYLOAD_KG = "max_payload_kg"
SUPPORTS_OFFLINE_MISSION = "supports_offline_mission"
CHARGE_KW = "charge_kw"


@dataclass(frozen=True, slots=True)
class Capabilities:
    """Leitura tipada do descritor.

    Existe para que uma chave escrita errada no JSON não vire silenciosamente
    ``False`` no meio de uma decisão de segurança: aqui o padrão está num lugar
    só, explícito e testável.
    """

    raw: dict = field(default_factory=dict)

    def flag(self, key: str) -> bool:
        return bool(self.raw.get(key, False))

    def number(self, key: str, default: float = 0.0) -> float:
        value = self.raw.get(key, default)
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def integer(self, key: str, default: int = 0) -> int:
        return int(self.number(key, default))

    # --- perguntas que o resto do sistema faz ------------------------------
    @property
    def has_rtk(self) -> bool:
        return self.flag(HAS_RTK)

    @property
    def can_spray(self) -> bool:
        return self.flag(HAS_SPRAY)

    @property
    def can_fly(self) -> bool:
        return self.flag(CAN_FLY)

    @property
    def can_image(self) -> bool:
        return self.flag(HAS_CAMERA_RGB) or self.flag(HAS_CAMERA_MULTISPECTRAL)

    @property
    def tank_count(self) -> int:
        return self.integer(TANK_COUNT)

    @property
    def swath_m(self) -> float:
        """Largura útil de uma passada. Define a densidade do plano de cobertura."""
        return self.number(SWATH_M, 3.0)

    @property
    def cruise_speed_ms(self) -> float:
        return self.number(CRUISE_SPEED_MS, self.number(MAX_SPEED_MS, 1.5))

    @property
    def endurance_minutes(self) -> float:
        return self.number(ENDURANCE_MINUTES, 60.0)

    @property
    def supports_offline_mission(self) -> bool:
        return self.flag(SUPPORTS_OFFLINE_MISSION)

    def missing_for_spray(self) -> list[str]:
        """O que falta para este hardware poder pulverizar. Vazio significa apto."""
        missing = []
        if not self.can_spray:
            missing.append(HAS_SPRAY)
        if self.tank_count < 1:
            missing.append(TANK_COUNT)
        if not self.has_rtk:
            # Sem RTK a posição erra metros. Aplicar produto com esse erro é
            # aplicar no vizinho.
            missing.append(HAS_RTK)
        return missing

    def missing_for_scout(self) -> list[str]:
        return [] if self.can_image else [HAS_CAMERA_RGB]


def capabilities_of(raw: dict | None) -> Capabilities:
    return Capabilities(raw or {})


# --- catálogo de referência --------------------------------------------------
# Estes são os modelos que a ValTexa projeta hoje. O sistema não depende deles:
# são linhas na tabela ``device_model``, e um parceiro entra cadastrando a sua.

REFERENCE_MODELS: list[dict] = [
    {
        "code": "ROVER_SCOUT_V1",
        "kind": DeviceKind.ROVER,
        "name": "ValTexa Rover Scout V1",
        "manufacturer": "ValTexa",
        "capabilities": {
            HAS_RTK: True,
            HAS_CAMERA_RGB: True,
            HAS_LIDAR: True,
            CAN_FLY: False,
            HAS_SPRAY: False,
            SWATH_M: 3.0,
            CRUISE_SPEED_MS: 1.2,
            MAX_SPEED_MS: 2.0,
            BATTERY_WH: 1200,
            ENDURANCE_MINUTES: 240,
            CAMERA_GSD_MM_AT_1M: 0.35,
            SUPPORTS_OFFLINE_MISSION: True,
        },
    },
    {
        "code": "ROVER_V3",
        "kind": DeviceKind.ROVER,
        "name": "ValTexa Rover V3",
        "manufacturer": "ValTexa",
        # Números do projeto do V3 (infraestrutura + chassi). São de PROJETO, não
        # medidos em campo: é exatamente por isso que o planejador marca todo
        # plano feito com eles como estimativa, até a primeira missão calibrar.
        # Ver valtexa/services/planner.py.
        "capabilities": {
            HAS_RTK: True,
            HAS_CAMERA_RGB: True,
            HAS_LIDAR: True,
            CAN_FLY: False,
            HAS_SPRAY: False,
            SWATH_M: 3.0,
            CRUISE_SPEED_MS: 1.0,
            MAX_SPEED_MS: 1.5,
            BATTERY_WH: 5120,          # 48 V, 100 Ah
            ENDURANCE_MINUTES: 480,    # 6 a 10 h por missão; 8 h é o meio
            CHARGE_KW: 2.5,            # poste de recarga por acoplamento
            CAMERA_GSD_MM_AT_1M: 0.35,
            SUPPORTS_OFFLINE_MISSION: True,
        },
    },
    {
        "code": "DRONE_ACTION_V1",
        "kind": DeviceKind.DRONE,
        "name": "ValTexa Drone Action V1",
        "manufacturer": "ValTexa",
        "capabilities": {
            HAS_RTK: True,
            HAS_CAMERA_RGB: True,
            CAN_FLY: True,
            HAS_SPRAY: True,
            TANK_COUNT: 2,
            TANK_CAPACITY_L: 10.0,
            SWATH_M: 4.0,
            CRUISE_SPEED_MS: 6.0,
            MAX_SPEED_MS: 12.0,
            BATTERY_WH: 900,
            ENDURANCE_MINUTES: 18,
            MAX_PAYLOAD_KG: 20.0,
            SUPPORTS_OFFLINE_MISSION: True,
        },
    },
    {
        "code": "DOCK_BASE_V1",
        "kind": DeviceKind.DOCK,
        "name": "ValTexa Dock / Base Autônoma V1",
        "manufacturer": "ValTexa",
        "capabilities": {
            CAN_CHARGE: True,
            CAN_SWAP_BATTERY: True,
            CAN_REFILL: True,
            HAS_RTK: True,
            SUPPORTS_OFFLINE_MISSION: False,
        },
    },
    {
        # A base da fazenda (VALTEXA-BASE): Starlink de um lado, rádios dos Rovers do
        # outro. Não anda nem fotografa: repassa o que os Rovers assinam e manda o
        # retrato dela (health.base) — ver valtexa/services/estacao_base.py.
        "code": "FARM_BASE_V1",
        "kind": DeviceKind.GATEWAY,
        "name": "ValTexa Base da Fazenda V1",
        "manufacturer": "ValTexa",
        "capabilities": {
            SUPPORTS_OFFLINE_MISSION: False,
        },
    },
]
