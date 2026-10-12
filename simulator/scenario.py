"""Uma temporada inteira em dois minutos, sem hardware nenhum.

O roteiro percorre o fluxo completo do produto e, de propósito, passa por três
momentos em que o sistema **recusa** fazer algo. Um simulador que só mostra o
caminho feliz não prova nada: o valor da plataforma está exatamente nos
bloqueios.

    rover coleta → IA A + IA B → dupla validação → motor de decisão
    → agrônomo aprova → safety engine → missão assinada → drone aplica
    → rover verifica → gêmeo digital

Rode com ``python -m simulator``.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from simulator.client import DeviceClient, ProtocolError
from simulator.devices import Battery, SimulatedDock, SimulatedDrone, SimulatedRover
from simulator.operator import ApiError, OperatorClient
from simulator.plants import Focus, SimulatedCrop
from valtexa.seed import DEMO_FIELD_BOUNDARY
from valtexa.services.hal import REFERENCE_MODELS, Capabilities
from valtexa.services.planner import PerfilDeAutonomia
from valtexa.services.taxonomy import PEST_LABELS

PERFIL_ROVER = PerfilDeAutonomia.from_capabilities(
    Capabilities(
        raw=next(m for m in REFERENCE_MODELS if m["code"] == "ROVER_V3")["capabilities"]
    )
)
"""Autonomia do Rover V3, a mesma que o planejador usa para dizer onde falta poste."""

MAX_RECARGAS = 0
"""Ciclos de recarga que o roteiro encena depois da primeira carga.

Varrer 24 ha de café rua a rua são 79 km e seis cargas — mais do que cabe numa
demonstração. Com zero, o rover sai com a bateria cheia, anda até a política
embarcada mandar voltar, e o roteiro para ali, com o robô no dock.

A cobertura parcial que sobra **é o resultado que a demonstração precisa
mostrar**: a cópia 3D tem exatamente as ruas que o rover mediu, e o resto do
talhão aparece como não visitado. Uma cópia cheia depois de meia varredura seria
lavoura inventada.
"""

ADMIN = ("admin@valtexa.dev", "valtexa-demo-2026")
AGRONOMIST = ("agronomo@valtexa.dev", "valtexa-demo-2026")
OPERATOR = ("operador@valtexa.dev", "valtexa-demo-2026")

ROVER_SERIAL = "SIM-ROVER-0001"
DRONE_SERIAL = "SIM-DRONE-0001"
DOCK_SERIAL = "SIM-DOCK-0001"


@dataclass
class ScenarioResult:
    """O que aconteceu, para os testes conferirem."""

    steps: list[str]
    mission_scout_id: str = ""
    mission_spray_id: str = ""
    blocked_reasons: list[str] = None  # type: ignore[assignment]
    observations: int = 0
    decisions: dict = None  # type: ignore[assignment]
    application_id: str = ""
    resumed: bool = False
    synced: int = 0
    scans: int = 0
    plants: int = 0
    coverage: float = 0.0
    pests_reviewed: int = 0

    def __post_init__(self) -> None:
        if self.blocked_reasons is None:
            self.blocked_reasons = []
        if self.decisions is None:
            self.decisions = {}


def demo_crop(boundary: list | None = None) -> SimulatedCrop:
    """O cafezal do talhão de demonstração, com duas reboleiras.

    Uma de ferrugem — que o ``coffee-foliar`` conhece e acerta — e uma de
    bicho-mineiro, que sai do modelo como mancha foliar qualquer e com novidade
    alta: é o agrônomo quem diz que é praga, não doença. É o caminho real de um
    ataque até a cópia 3D, e a razão de o fungicida da demonstração **não**
    listar bicho-mineiro entre os alvos autorizados.

    Espaçamento 3,5 m entre ruas e 0,7 m entre plantas, porte de 2,2 m: lavoura
    formada, como a da foto.
    """
    return SimulatedCrop(
        boundary=boundary or DEMO_FIELD_BOUNDARY,
        row_spacing_m=3.5,
        plant_spacing_m=0.7,
        # As ruas da foto seguem o contorno do terreno; 25° é a direção média do
        # bloco norte, que é por onde o rover entra.
        row_azimuth_deg=25.0,
        height_m=2.2,
        # Café adulto fecha a rua: a copa chega perto da metade do espaçamento.
        canopy_m=1.7,
        foci=[
            Focus(
                lon=-45.86300,
                lat=-21.90250,
                radius_m=90.0,
                drawn="Rust",
                model_label="Rust",
                novelty=0.4,
                stunting=0.12,
                yellowing=0.34,
                lesion=(178, 96, 30),
            ),
            Focus(
                lon=-45.86100,
                lat=-21.90240,
                radius_m=60.0,
                drawn="Leaf_Miner_Damage",
                model_label="Cercospora_Leaf_Spot",
                novelty=1.6,
                stunting=0.22,
                yellowing=0.20,
                lesion=(150, 132, 84),
                defoliation=0.40,
            ),
        ],
    )


def banner(text: str) -> None:
    print(f"\n{'═' * 74}\n  {text}\n{'═' * 74}")


def step(text: str) -> None:
    print(f"  → {text}")


def run(base_url: str, demo: dict) -> ScenarioResult:
    """Executa o roteiro completo contra uma plataforma no ar."""
    result = ScenarioResult(steps=[])
    field_id = demo["field_id"]
    zone_id = demo["zone_id"]
    product_id = demo["product_id"]
    batch_id = demo["batch_id"]

    # ---------------------------------------------------------------- 1
    banner("1. Provisionamento — os robôs entram na frota")
    admin = OperatorClient.login(base_url, *ADMIN)
    step(f"admin autenticado como {admin.role} ({len(admin.capabilities)} capacidades)")

    tokens = {
        "rover": _token(admin, "ROVER_V3", ROVER_SERIAL, demo["farm_id"]),
        "drone": _token(admin, "DRONE_ACTION_V1", DRONE_SERIAL, demo["farm_id"]),
        "dock": _token(admin, "DOCK_BASE_V1", DOCK_SERIAL, demo["farm_id"]),
    }

    rover_client = DeviceClient.provision(base_url, tokens["rover"], ROVER_SERIAL, name="Rover 01")
    drone_client = DeviceClient.provision(base_url, tokens["drone"], DRONE_SERIAL, name="Drone 01")
    dock_client = DeviceClient.provision(base_url, tokens["dock"], DOCK_SERIAL, name="Dock 01")
    step("três dispositivos provisionados — cada um gerou o próprio par de chaves")

    # O convite é de uso único. Tentar de novo é recusado.
    try:
        DeviceClient.provision(base_url, tokens["rover"], ROVER_SERIAL)
        step("FALHA: o convite foi aceito duas vezes")
    except ProtocolError as exc:
        step(f"convite reutilizado foi recusado ({exc.status_code}) — correto")
        result.steps.append("provisioning_token_single_use")

    base_point = (demo["base_lon"], demo["base_lat"])
    crop = demo_crop(demo.get("field_boundary"))
    rover = SimulatedRover(
        client=rover_client,
        name="Rover 01",
        # Consumo do perfil real do Rover V3 — o mesmo do planejador. A carga
        # inicial fica logo acima do mínimo de segurança: a plataforma autoriza,
        # e é durante a varredura que a política embarcada manda voltar.
        battery=Battery.do_perfil(PERFIL_ROVER, percent=38.0),
        lat=base_point[1],
        lon=base_point[0],
        field_id=field_id,
        disease_ratio=0.45,
        photos_per_segment=3,
        # Com a lavoura, cada rua percorrida também vira passada da cópia 3D, e
        # as fotos seguem as reboleiras em vez do sorteio.
        crop=crop,
    )
    drone = SimulatedDrone(
        client=drone_client, name="Drone 01", lat=base_point[1], lon=base_point[0]
    )
    dock = SimulatedDock(client=dock_client, name="Dock 01", lat=base_point[1], lon=base_point[0])

    dock.report_weather()
    drone.push_telemetry(alt_m=0.0, mission_state="idle")
    rover.push_telemetry(mission_state="idle")

    # ---------------------------------------------------------------- 2
    banner("2. Varredura — o rover percorre o talhão")
    operator = OperatorClient.login(base_url, *OPERATOR)
    scout = operator.post(
        "/v1/missions",
        {
            "kind": "scout",
            "field_id": field_id,
            "device_id": rover_client.identity.device_id,
            # Reconhecimento do talhão inteiro, com faixa larga: é a passada
            # rápida que situa o agrônomo antes da varredura detalhada. Sem
            # polígono, create_mission usa o talhão menos a margem da cerca.
            #
            # São 24 ha: mais do que o rover faz com a carga que ele tem, e é
            # justamente aí que a política embarcada manda voltar no meio do
            # caminho — o que a plataforma precisa saber atravessar.
            "plan": {"swath_m": 25.0},
        },
    )
    result.mission_scout_id = scout["id"]
    step(
        f"missão de varredura criada: {scout['plan']['segments']} segmentos, "
        f"{scout['plan']['path_length_m']:.0f} m, {scout['plan']['area_ha']:.2f} ha"
    )

    evaluation = operator.post(f"/v1/missions/{scout['id']}/authorize")
    step(f"segurança: {evaluation['verdict']} ({len(evaluation['checks'])} verificações)")

    envelope = operator.post(f"/v1/missions/{scout['id']}/dispatch")
    step(f"missão assinada com {envelope['algorithm']}")

    payload = rover_client.fetch_mission()
    step("rover verificou a assinatura da nuvem antes de aceitar")
    rover_client.ack_mission(payload["mission_id"], accepted=True)

    outcome = rover.run_mission(payload, base_point)

    # ---------------------------------------------------------------- 3
    if outcome == "paused":
        banner("3. Recarga e retomada — continuar de onde parou")
        dock.recharge(rover)
        rover_client.report_recharged(payload["mission_id"])

        resumed = operator.post(f"/v1/missions/{scout['id']}/resume")
        remaining = len(resumed["payload"]["body"]["segments"])
        step(f"missão retomada com {remaining} segmento(s) restantes — não do zero")
        result.resumed = True

        payload = rover_client.fetch_mission()

        # ------------------------------------------------------------ 3b
        # O enlace cai no meio da retomada. O rover não para: acumula e envia
        # depois. É o comportamento que a lavoura exige.
        rover.go_offline()
        rover.push_telemetry(mission_state="running", link_quality=0.0)
        rover.push_event("communication_lost", severity="warning")
        sync = rover.reconnect(sync_id="sync-0001")
        result.synced = sync["accepted"]

        # Reenviar o mesmo lote não pode duplicar nada.
        repeat = rover_client.sync("sync-0001", [], [])
        step(
            f"reenvio do mesmo lote: {repeat['accepted']} aceitos, "
            f"{repeat['duplicated']} já conhecidos — idempotente"
        )

        rover.run_mission(payload, base_point)

    observations = operator.get("/v1/observations", {"field_id": field_id, "limit": 500})
    result.observations = len(observations)
    step(f"{len(observations)} observações no talhão")

    # ---------------------------------------------------------------- 4
    banner("4. Diagnóstico e decisão")
    _wait_for_events(admin)

    queue = operator.get("/v1/review/queue", {"limit": 50})
    step(f"fila do agrônomo: {len(queue)} item(ns)")

    candidate = _first_diseased(observations)
    if candidate is None:
        step("nenhuma observação com doença nesta rodada")
    else:
        decision = operator.post(f"/v1/diagnoses/{candidate['diagnosis_id']}/decide")
        result.decisions[decision["outcome"]] = decision["rationale"]
        step(f"decisão: {decision['outcome']} — {decision['rationale']}")

    agronomist = OperatorClient.login(base_url, *AGRONOMIST)
    if queue:
        reviewed = agronomist.post(
            f"/v1/diagnoses/{queue[0]['id']}/review",
            {
                "label": "Cercospora_Leaf_Spot",
                "confirmed": True,
                "notes": "Cercosporiose confirmada: olho pardo com halo amarelado.",
            },
        )
        step(
            f"agrônomo rotulou {reviewed['reviewed_label']!r} "
            f"(máquina dizia {reviewed['label']!r}) — assim nasce o dataset próprio"
        )
        result.steps.append("agronomist_review")

    # ---------------------------------------------------------------- 5
    banner("5. Cópia 3D — o rover percorre o talhão rua a rua")
    _survey(result, operator, agronomist, admin, rover, rover_client, dock, demo, base_point)

    # ---------------------------------------------------------------- 6
    banner("6. Pulverização — três bloqueios antes de qualquer autorização")
    spray = agronomist.post(
        "/v1/missions",
        {
            "kind": "spray",
            "field_id": field_id,
            "zone_id": zone_id,
            "device_id": drone_client.identity.device_id,
            "target_polygon": demo["zone_boundary"],
            "product_id": product_id,
            "product_batch_id": batch_id,
            "tank_id": _drone_tank(admin, drone_client.identity.device_id)["id"],
            "authorized_rate_l_ha": 0.75,
            "authorized_quantity_l": 6.0,
        },
    )
    result.mission_spray_id = spray["id"]
    step("missão de pulverização criada")

    # (a) sem aprovação humana
    blocked = operator.post(f"/v1/missions/{spray['id']}/authorize")
    _record_block(result, blocked, "sem aprovação do agrônomo")

    # (b) o operador tenta aprovar — não é o papel dele
    denied = operator.try_post(f"/v1/missions/{spray['id']}/approve", {"confirm": True})
    if denied.get("error"):
        step(f"operador tentou aprovar e foi recusado ({denied['status_code']}) — correto")
        result.steps.append("operator_cannot_approve")

    agronomist.post(f"/v1/missions/{spray['id']}/approve", {"confirm": True})
    step("agrônomo assinou a aprovação")

    # (c) tanque com o produto errado
    tank = _drone_tank(admin, drone_client.identity.device_id)
    other = agronomist.post(
        "/v1/products",
        {
            "name": "Herbicida Demo (produto errado)",
            "registration_number": "DEMO-99999",
            "allowed_crops": ["corn"],
            "authorized_targets": ["Buva"],
            "default_rate_l_ha": 1.0,
            "min_rate_l_ha": 0.5,
            "max_rate_l_ha": 2.0,
        },
    )
    other_batch = agronomist.post(f"/v1/products/{other['id']}/batches", {"code": "LOTE-ERRADO"})
    admin.post(
        f"/v1/tanks/{tank['id']}/load",
        {"product_id": other["id"], "batch_id": other_batch["id"], "volume_l": 10.0},
    )
    blocked = operator.post(f"/v1/missions/{spray['id']}/authorize")
    _record_block(result, blocked, "tanque com produto diferente do autorizado")

    # (d) tanque correto
    admin.post(
        f"/v1/tanks/{tank['id']}/load",
        {"product_id": product_id, "batch_id": batch_id, "volume_l": 10.0},
    )
    dock.report_weather()
    drone.push_telemetry(alt_m=0.0, mission_state="idle")

    approved = operator.post(f"/v1/missions/{spray['id']}/authorize")
    step(f"segurança: {approved['verdict']}")
    if approved["verdict"] != "safe_to_execute":
        step(f"ainda bloqueada: {approved['blocked_reason']}")
        result.blocked_reasons.append(approved["blocked_reason"])
        return result

    # ---------------------------------------------------------------- 7
    banner("7. Aplicação")
    operator.post(f"/v1/missions/{spray['id']}/dispatch")
    spray_payload = drone_client.fetch_mission()
    drone_client.ack_mission(spray_payload["mission_id"], accepted=True)
    application = drone.run_spray(spray_payload)
    result.application_id = application["id"]
    step(
        f"aplicação registrada: {application['amount_used_l']} L, "
        f"{application['outside_polygon_points']} ponto(s) fora do polígono"
    )

    # ---------------------------------------------------------------- 8
    banner("8. Gêmeo digital e auditoria")
    _wait_for_events(admin)

    snapshot = operator.get(f"/v1/fields/{field_id}/snapshot", {"days": 7})
    step(
        f"talhão: {snapshot['observations']} observações, "
        f"{snapshot['needs_review']} para o agrônomo"
    )
    for item in snapshot["classes"][:4]:
        step(f"   {item['label']:<18} {item['count']:>3} ({item['ratio']:.0%})")

    verifications = operator.get("/v1/verifications")
    if verifications:
        step(
            f"verificação agendada para {verifications[0]['scheduled_for'][:16]} "
            f"— nada é declarado eficaz sem uma segunda passada"
        )
        result.steps.append("verification_scheduled")

    trail = admin.get("/v1/audit", {"limit": 500})
    step(f"trilha de auditoria: {len(trail)} registro(s)")
    for entry in [e for e in trail if e["action"] == "mission.approved"][:1]:
        step(f"   aprovação da aplicação: {entry['actor_label']} ({entry['payload'].get('role')})")

    for client in (admin, operator, agronomist):
        client.close()
    for device in (rover_client, drone_client, dock_client):
        device.close()
    return result


def _survey(
    result: ScenarioResult,
    operator: OperatorClient,
    agronomist: OperatorClient,
    admin: OperatorClient,
    rover: SimulatedRover,
    rover_client: DeviceClient,
    dock: SimulatedDock,
    demo: dict,
    base_point: tuple[float, float],
) -> None:
    """Varredura rua a rua, na faixa real do sensor: é o que monta a cópia 3D.

    A primeira varredura do roteiro passa a cada 25 m para caber no tempo; esta
    anda em todas as ruas, com a faixa de 3 m do LiDAR, e sobre o **talhão
    inteiro** — 24 ha de café, não só o bloco norte. É aí que a autonomia
    aparece: o percurso é de dezenas de quilômetros, e o rover volta, recarrega
    e continua da rua seguinte, várias vezes.

    A cópia 3D cresce rua a rua. Ela **não** representa o talhão inteiro: ela
    representa exatamente o que o rover já mediu. Um talhão varrido pela metade
    tem metade da cópia, e o console mostra o resto como não visitado — inventar
    as ruas que faltam seria inventar lavoura.

    O roteiro tem orçamento de tempo: ``MAX_RECARGAS`` limita quantos ciclos de
    recarga ele encena. A varredura para onde parou, e a cobertura parcial que
    sobra é o resultado honesto, não uma falha da demonstração.
    """
    field_id = demo["field_id"]
    dock.recharge(rover)
    rover.push_telemetry(mission_state="idle")
    rover.battery = Battery.do_perfil(PERFIL_ROVER, percent=100.0)
    rover.novelty_ratio = 0.06
    rover.photo_every_m = 40.0
    rover.symptom_every_m = 5.0

    survey = operator.post(
        "/v1/missions",
        {
            "kind": "scout",
            "field_id": field_id,
            "device_id": rover_client.identity.device_id,
            # Sem polígono: create_mission usa o talhão inteiro menos a
            # margem da cerca virtual. É a varredura completa dos 24 ha.
            "plan": {"swath_m": 2 * rover.scan_reach_m},
        },
    )
    step(
        f"varredura rua a rua: {survey['plan']['segments']} ruas, "
        f"{survey['plan']['path_length_m']:.0f} m de percurso"
    )
    evaluation = operator.post(f"/v1/missions/{survey['id']}/authorize")
    if evaluation["verdict"] != "safe_to_execute":
        step(f"varredura bloqueada: {evaluation['blocked_reason']}")
        return
    operator.post(f"/v1/missions/{survey['id']}/dispatch")
    payload = rover_client.fetch_mission()
    rover_client.ack_mission(payload["mission_id"], accepted=True)

    recargas = 0
    while rover.run_mission(payload, base_point) == "paused":
        recargas += 1
        if recargas > MAX_RECARGAS:
            step(
                "varredura interrompida na parada para recarga — o roteiro tem "
                "orçamento de tempo. A cópia 3D fica com as ruas que o rover "
                "realmente mediu; o resto do talhão segue não visitado."
            )
            break
        dock.recharge(rover)
        rover_client.report_recharged(payload["mission_id"])
        operator.post(f"/v1/missions/{survey['id']}/resume")
        payload = rover_client.fetch_mission()

    _wait_for_events(admin)
    pests = [
        (drawn, response)
        for drawn, response in rover.frames
        if drawn in PEST_LABELS and response.get("diagnosis_status") == "needs_review"
    ]
    for drawn, response in pests:
        reviewed = agronomist.try_post(
            f"/v1/diagnoses/{response['diagnosis_id']}/review",
            {
                "label": drawn,
                "confirmed": True,
                "notes": "Bicho-mineiro: galerias e manchas secas irregulares na folha.",
            },
        )
        if not reviewed.get("error"):
            result.pests_reviewed += 1
    if pests:
        step(
            f"agrônomo identificou bicho-mineiro em {result.pests_reviewed} foto(s) — "
            "o modelo não conhece a praga; o rótulo dele é o que a põe na cópia 3D"
        )

    scene = operator.get(f"/v1/fields/{field_id}/scene")
    result.scans = len(scene["scans"])
    result.plants = len(scene["plants"]["x"])
    result.coverage = scene["coverage_ratio"]
    counts = ", ".join(f"{name} {count}" for name, count in sorted(scene["counts"].items()))
    step(
        f"cópia 3D: {result.plants} plantas medidas em {result.scans} ruas, "
        f"{result.coverage:.0%} do talhão — o resto continua não visitado, "
        f"e a cópia não inventa o que ninguém mediu"
    )
    step(f"marcadores na cópia: {counts}")
    result.steps.append("digital_copy_3d")


def _token(admin: OperatorClient, model_code: str, serial: str, farm_id: str) -> str:
    body = admin.post(
        "/v1/provisioning-tokens",
        {"device_model_code": model_code, "serial_number": serial, "farm_id": farm_id},
    )
    return body["token"]


def _drone_tank(admin: OperatorClient, device_id: str) -> dict:
    tanks = admin.get("/v1/tanks", {"device_id": device_id})
    if not tanks:
        raise ApiError(404, "O drone não tem tanque cadastrado.")
    return tanks[0]


def _record_block(result: ScenarioResult, evaluation: dict, expected: str) -> None:
    if evaluation["verdict"] == "blocked":
        failed = [c["code"] for c in evaluation["checks"] if not c["passed"]]
        step(f"BLOQUEADA ({expected}): {', '.join(failed)}")
        result.blocked_reasons.append(evaluation["blocked_code"])
    else:
        step(f"ATENÇÃO: esperava bloqueio por {expected} e passou")


def _first_diseased(observations: list) -> dict | None:
    for row in observations:
        if row.get("diagnosis_id") and row.get("label") not in (None, "Healthy"):
            return row
    return None


def _wait_for_events(client: OperatorClient, attempts: int = 6) -> None:
    """Espera o *outbox* esvaziar.

    O barramento é assíncrono de propósito — é o que garante que o estado e o
    evento sejam gravados na mesma transação. O roteiro só precisa esperar a
    entrega para que as consultas seguintes vejam o efeito.
    """
    for _ in range(attempts):
        pending = client.get("/v1/events", {"pending_only": True, "limit": 1})
        if not pending:
            return
        time.sleep(1.0)
