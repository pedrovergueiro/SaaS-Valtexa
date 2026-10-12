"""Bananal e pomar: o rover entre as plantas, com a câmera lateral e a IA do VALTEXA-B.

O roteiro de ``python -m simulator`` mostra a plataforma no cafezal, com a IA
simulada. Este mostra a outra metade: o rover andando entre bananeiras e
laranjeiras, quadro a quadro, e a IA juntando tudo **por planta** — posterior
por doença, incidência, o que mudou de uma passada para a outra e a
prevalência no talhão.

    python -m simulator.pomar
        IA simulada. Exercita o fluxo e o painel (sinais do quadro, fila por
        valor, seletor de versão). Plantas e prevalência ficam indisponíveis:
        quem as calcula é o serviço de inferência, e aqui não há um.

    python -m simulator.pomar --ia http://127.0.0.1:8001 --fotos <pasta>
        A IA de verdade: o VALTEXA-B no ar com ``FIELDS_DIR`` configurado, e
        fotos reais em ``<pasta>/<cultura>/<Classe>/`` — monte a pasta com
        ``python -m training.demo_photos`` no VALTEXA-B.

Com ``--manter`` a plataforma fica no ar no fim, para abrir o painel.

Duas passadas por talhão, com uma semana entre elas. Na primeira, a reboleira
tem cinco plantas; na segunda ela cresceu, e no canto oposto aparece uma planta
com outra doença. É o que a evolução por planta tem de mostrar.

O resultado **não é medida** de acurácia: são poucas plantas, e a folha sadia
das fotos reais vem do dataset de treino. A medida está no MODELS.md do VALTEXA-B.
"""

from __future__ import annotations

import argparse
import contextlib
import math
import os
import random
import sys
import time
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
M_PER_DEG_LAT = 111_320.0
HEALTHY = "Healthy"

DISTANCIA_FOTO_REAL_MM = 51.0
"""Distância declarada nos quadros com foto real.

As fotos da pasta são recortes de folha de ~150 mm, ampliados a 320 px. A 51 mm
(o mínimo que o SaaS aceita é 50), a lente de 127° do rover cobre ~20 cm, e o
corte de 150 mm do /predict/rover-frame pega três quartos da foto. Medido nas
fotos da demonstração: a 75 mm (corte de meia foto) os quadros acertavam 71% no
bananal e 67% no pomar; a 51 mm, 83% e 100% — recorte pequeno demais perde a
lesão, e um recorte de folha sadia com mancha ambígua já vira achado. A OAK-D
não mede a 51 mm; é o número que faz a foto que existe caber na geometria.
"""

DISTANCIA_SIMULADA_MM = 400.0
"""No modo simulado ninguém corta o quadro: vale a distância de trabalho do rover."""


@dataclass(frozen=True)
class Talhao:
    """Um talhão da demonstração, em ruas e plantas."""

    nome: str
    cultura: str
    """Como o produtor escreve — o SaaS resolve o modelo a partir disto."""
    fotos: str
    """A subpasta de fotos: ``banana`` ou ``citrus``."""
    ruas: int
    plantas_por_rua: int
    espacamento_m: float
    """Entre plantas na rua — o mesmo da fusão por planta no VALTEXA-B."""
    entre_ruas_m: float
    cameras_mm: tuple[float, ...]
    """Andares das câmeras do mastro que veem folha nesta cultura.

    O Rover V3 tem câmeras a 450, 1000 e 1540 mm de cada lado
    (``hardware/rover-v3``, ``CAMERAS_Z``). Na bananeira, a de 450 mm vê o
    pseudocaule — e a demonstração não tem foto de pseudocaule; na laranjeira,
    ela vê a saia da copa. Cada câmera é evidência independente na fusão.
    """
    principal: str
    """A doença da reboleira."""
    secundaria: str
    """A que aparece numa planta só, na segunda passada."""
    deslocamento_m: tuple[float, float]
    """Do ponto base da fazenda, em metros (leste, norte)."""


BANANAL = Talhao(
    nome="Bananal (demonstração)",
    cultura="banana",
    fotos="banana",
    ruas=3,
    plantas_por_rua=6,
    espacamento_m=2.5,
    entre_ruas_m=3.0,
    cameras_mm=(1000.0, 1540.0),
    principal="Sigatoka",
    secundaria="Fusarium_Wilt",
    deslocamento_m=(-160.0, -90.0),
)
POMAR = Talhao(
    nome="Pomar de laranja (demonstração)",
    cultura="laranja",
    fotos="citrus",
    ruas=3,
    plantas_por_rua=5,
    espacamento_m=4.0,
    entre_ruas_m=6.0,
    cameras_mm=(450.0, 1000.0, 1540.0),
    principal="Canker",
    secundaria="Greening",
    deslocamento_m=(60.0, -90.0),
)


def verdade(talhao: Talhao, passada: int) -> dict[tuple[int, int], str]:
    """O que cada planta ``(rua, planta)`` tem de fato, nesta passada.

    A reboleira nasce na planta 2 da rua do meio e cresce de raio 1 para 2,2
    plantas; na segunda passada, a última planta da última rua pega a outra doença.
    """
    centro, raio = (1, 2), (1.0, 2.2)[passada]
    out = {}
    for rua in range(talhao.ruas):
        for planta in range(talhao.plantas_por_rua):
            doente = math.hypot(rua - centro[0], planta - centro[1]) <= raio
            out[(rua, planta)] = talhao.principal if doente else HEALTHY
    if passada == 1:
        out[(talhao.ruas - 1, talhao.plantas_por_rua - 1)] = talhao.secundaria
    return out


# --- geometria --------------------------------------------------------------------------


@dataclass(frozen=True)
class Origem:
    lon: float
    lat: float

    def ponto(self, leste_m: float, norte_m: float) -> tuple[float, float]:
        """``(lon, lat)`` de um ponto em metros a partir da origem."""
        lat = self.lat + norte_m / M_PER_DEG_LAT
        lon = self.lon + leste_m / (M_PER_DEG_LAT * math.cos(math.radians(self.lat)))
        return lon, lat


def contorno(talhao: Talhao, origem: Origem) -> list[list[float]]:
    """Retângulo que cabe as ruas, com uma rua de folga em volta."""
    folga = talhao.entre_ruas_m
    largura = talhao.plantas_por_rua * talhao.espacamento_m
    altura = (talhao.ruas - 1) * talhao.entre_ruas_m
    cantos = [(-folga, -folga), (largura + folga, -folga), (largura + folga, altura + folga)]
    cantos.append((-folga, altura + folga))
    return [list(origem.ponto(x, y)) for x, y in cantos]


def posicao_planta(talhao: Talhao, planta: int) -> float:
    """Onde a planta está ao longo da rua (a odometria do rover), em metros."""
    return (planta + 0.5) * talhao.espacamento_m


# --- fotos --------------------------------------------------------------------------------


class Fotos:
    """Escolhe a foto de cada quadro: real (da pasta) ou desenhada com a etiqueta."""

    def __init__(self, pasta: Path | None) -> None:
        self.pasta = pasta
        self._cache: dict[tuple[str, str], list[Path]] = {}

    def conferir(self, talhoes: list[Talhao]) -> None:
        if self.pasta is None:
            return
        faltando = []
        for talhao in talhoes:
            classes = {HEALTHY, talhao.principal, talhao.secundaria}
            faltando += [
                f"{talhao.fotos}/{nome}"
                for nome in sorted(classes)
                if not self._lista(talhao.fotos, nome)
            ]
        if faltando:
            raise SystemExit(
                f"Faltam fotos em {self.pasta}: {', '.join(faltando)}. "
                "Monte a pasta com 'python -m training.demo_photos' no VALTEXA-B."
            )

    def quadro(self, talhao: Talhao, rotulo: str, semente: str) -> tuple[bytes, str]:
        rng = random.Random(semente)
        if self.pasta is None:
            from simulator.devices import frame_with_label

            return frame_with_label(rotulo, novelty=0.4, seed=rng.randrange(10_000)), "quadro.png"
        caminho = rng.choice(self._lista(talhao.fotos, rotulo))
        return caminho.read_bytes(), caminho.name

    def _lista(self, cultura: str, rotulo: str) -> list[Path]:
        chave = (cultura, rotulo)
        if chave not in self._cache:
            pasta = self.pasta / cultura / rotulo
            self._cache[chave] = (
                sorted(p for p in pasta.iterdir() if p.suffix.lower() in SUFFIXES)
                if pasta.is_dir()
                else []
            )
        return self._cache[chave]


# --- roteiro ---------------------------------------------------------------------------------


def banner(text: str) -> None:
    print(f"\n{'═' * 74}\n  {text}\n{'═' * 74}")


def step(text: str) -> None:
    print(f"  → {text}")


@dataclass
class Resultado:
    quadros: int = 0
    plantas: int = 0
    situacao_certa: int = 0
    doenca_certa: int = 0
    doentes: int = 0
    plantas_indisponiveis: str = ""


def run(
    base_url: str,
    fotos: Fotos,
    quadros_por_camera: int = 1,
    talhoes: list[Talhao] | None = None,
    versao: str = "campo",
) -> dict[str, Resultado]:
    """Executa o roteiro contra uma plataforma no ar."""
    from simulator.client import DeviceClient
    from simulator.devices import SimulatedDevice
    from simulator.operator import OperatorClient
    from simulator.scenario import ADMIN, AGRONOMIST, OPERATOR

    talhoes = talhoes or [BANANAL, POMAR]
    fotos.conferir(talhoes)

    banner("1. Talhões e rover")
    admin = OperatorClient.login(base_url, *ADMIN)
    operator = OperatorClient.login(base_url, *OPERATOR)
    agronomist = OperatorClient.login(base_url, *AGRONOMIST)
    farm = admin.get("/v1/farms")[0]
    origem = Origem(
        lon=farm.get("base_lon") or farm["center_lon"],
        lat=farm.get("base_lat") or farm["center_lat"],
    )
    campos = {talhao.nome: _talhao(admin, farm["id"], talhao, origem, versao) for talhao in talhoes}

    serial = f"SIM-ROVER-POMAR-{datetime.now(UTC):%H%M%S}"
    token = admin.post(
        "/v1/provisioning-tokens",
        {"device_model_code": "ROVER_V3", "serial_number": serial, "farm_id": farm["id"]},
    )["token"]
    # A inferência de verdade, em CPU, leva segundos por quadro.
    rover_client = DeviceClient.provision(
        base_url, token, serial, name="Rover pomar", timeout=300.0
    )
    rover = SimulatedDevice(client=rover_client, name="Rover pomar", lat=origem.lat, lon=origem.lon)
    step(f"rover {serial} provisionado")

    resultados = {}
    for talhao in talhoes:
        campo = campos[talhao.nome]
        banner(f"2. {talhao.nome} — duas passadas, uma semana entre elas")
        resultado = Resultado()
        for passada, dias in ((0, 7), (1, 0)):
            quando = datetime.now(UTC) - timedelta(days=dias, hours=1)
            resultado.quadros += _passada(
                operator, rover, rover_client, fotos, talhao, campo, origem, passada, quando,
                quadros_por_camera,
            )  # fmt: skip
        _relatorio(operator, agronomist, talhao, campo, resultado)
        resultados[talhao.nome] = resultado

    banner("3. Fila do agrônomo, pelo que mais ensina")
    fila = agronomist.get("/v1/review/queue", {"order": "valor", "limit": 5})
    for item in fila[:5]:
        motivos = "; ".join(item.get("priority_reasons") or []) or "—"
        step(f"{item['label'] or 'sem rótulo':<16} {item['priority_score']:.2f}  {motivos}")
    if not fila:
        step("fila vazia")

    for client in (admin, operator, agronomist):
        client.close()
    rover_client.close()
    return resultados


def _talhao(admin, farm_id: str, talhao: Talhao, origem: Origem, versao: str) -> dict:
    """Cria o talhão — ou reaproveita o de uma execução anterior."""
    from simulator.operator import ApiError

    existente = next((f for f in admin.get("/v1/fields") if f["name"] == talhao.nome), None)
    campo = existente or admin.post(
        f"/v1/farms/{farm_id}/fields",
        {
            "name": talhao.nome,
            "crop": talhao.cultura,
            "boundary": contorno(talhao, Origem(*origem.ponto(*talhao.deslocamento_m))),
            "row_azimuth_deg": 90.0,
        },
    )
    escolhas = admin.get(f"/v1/fields/{campo['id']}/ai-models")
    chave = next((c["key"] for c in escolhas if c["variant"] == versao), None)
    if chave and chave != campo.get("ai_model_in_use"):
        try:
            campo = admin.put(f"/v1/fields/{campo['id']}/ai-model", {"ai_model": chave})
        except ApiError as exc:
            step(f"não troquei a versão do modelo: {exc.detail}")
    step(
        f"{talhao.nome}: {talhao.ruas} ruas x {talhao.plantas_por_rua} plantas, "
        f"modelo {campo.get('ai_model_in_use') or '—'}"
    )
    return campo


def _passada(
    operator, rover, rover_client, fotos: Fotos, talhao: Talhao, campo: dict, origem: Origem,
    passada: int, quando: datetime, quadros_por_camera: int,
) -> int:  # fmt: skip
    """Uma missão de varredura: autoriza, despacha, manda os quadros e conclui."""
    inicio = Origem(*origem.ponto(*talhao.deslocamento_m))
    rover.lon, rover.lat = inicio.ponto(0.0, -talhao.entre_ruas_m / 2)
    rover.push_telemetry(mission_state="idle")
    missao = operator.post(
        "/v1/missions",
        {
            "kind": "scout",
            "field_id": campo["id"],
            "device_id": rover_client.identity.device_id,
            "plan": {"swath_m": talhao.entre_ruas_m},
        },
    )
    avaliacao = operator.post(f"/v1/missions/{missao['id']}/authorize")
    if avaliacao["verdict"] != "safe_to_execute":
        falhas = [c["code"] for c in avaliacao["checks"] if not c["passed"]]
        raise SystemExit(f"Varredura bloqueada pela segurança: {', '.join(falhas)}")
    operator.post(f"/v1/missions/{missao['id']}/dispatch")
    payload = rover_client.fetch_mission()
    rover_client.ack_mission(payload["mission_id"], accepted=True)

    real = verdade(talhao, passada)
    distancia = DISTANCIA_SIMULADA_MM if fotos.pasta is None else DISTANCIA_FOTO_REAL_MM
    enviados, rotulos = 0, Counter()
    inicio_envio = time.monotonic()
    for (rua, planta), rotulo in sorted(real.items()):
        centro = posicao_planta(talhao, planta)
        for altura in talhao.cameras_mm:
            for quadro in range(quadros_por_camera):
                # Os quadros de uma câmera se espalham 30 cm ao longo da rua.
                x = centro + (quadro - (quadros_por_camera - 1) / 2) * 0.3
                # O rover anda na entrelinha ao sul da rua e olha para o norte (esquerda).
                lon, lat = inicio.ponto(x, rua * talhao.entre_ruas_m - talhao.entre_ruas_m / 2)
                semente = f"{talhao.nome}:{passada}:{rua}:{planta}:{altura}:{quadro}"
                imagem, nome = fotos.quadro(talhao, rotulo, semente)
                body = rover_client.upload_observation(
                    {
                        "sequence_number": rover_client.next_sequence(),
                        "mission_id": missao["id"],
                        "field_id": campo["id"],
                        "captured_at": (quando + timedelta(seconds=2 * enviados)).isoformat(),
                        "lat": lat,
                        "lon": lon,
                        "heading_deg": 90.0,
                        "row_index": rua,
                        "camera": {
                            "camera_height_mm": altura,
                            "distance_mm": distancia,
                            "side": "left",
                            "x_m": round(x, 3),
                            "camera_id": f"esq-{int(altura)}",
                        },
                    },
                    imagem,
                    nome,
                )
                enviados += 1
                rotulos[body.get("label") or "fora do escopo"] += 1
    rover_client.complete_mission(missao["id"])
    ritmo = (time.monotonic() - inicio_envio) / max(enviados, 1)
    doentes = sum(rotulo != HEALTHY for rotulo in real.values())
    step(
        f"passada {passada + 1}: {enviados} quadros ({ritmo:.1f} s cada), "
        f"{doentes} plantas doentes de fato"
    )
    step("   a IA disse: " + ", ".join(f"{nome} {n}" for nome, n in rotulos.most_common()))
    return enviados


def _relatorio(operator, agronomist, talhao: Talhao, campo: dict, resultado: Resultado) -> None:
    """Plantas, evolução e prevalência — o que só a IA de verdade calcula."""
    from simulator.operator import ApiError

    try:
        plantas = operator.get(f"/v1/fields/{campo['id']}/plants")
    except ApiError as exc:
        resultado.plantas_indisponiveis = exc.detail
        step(f"plantas: indisponível ({exc.status_code}) — {exc.detail}")
        return

    real = verdade(talhao, 1)
    resultado.plantas = len(plantas)
    situacao = Counter(p["status"] for p in plantas)
    step("plantas: " + ", ".join(f"{nome} {n}" for nome, n in situacao.most_common()))
    por_posicao = {}
    for planta in plantas:
        rua = int(planta["row_id"])
        indice = round(planta["x_along_m"] / talhao.espacamento_m - 0.5)
        por_posicao[(rua, indice)] = planta
        rotulo = real.get((rua, indice), HEALTHY)
        doente = rotulo != HEALTHY
        resultado.doentes += doente
        if doente == (planta["status"] in ("doente", "suspeita")):
            resultado.situacao_certa += 1
        if doente and planta["primary_disease"] == rotulo:
            resultado.doenca_certa += 1
    step(
        f"IA contra a verdade (demonstração, não é medida): situação certa em "
        f"{resultado.situacao_certa} de {len(plantas)} plantas; doença certa em "
        f"{resultado.doenca_certa} de {resultado.doentes} doentes"
    )

    # O centro da reboleira (doente nas duas passadas) e uma planta que ela
    # alcançou na segunda — o que a evolução por planta existe para mostrar.
    for posicao, papel in (((1, 2), "centro da reboleira"), ((1, 4), "alcançada na 2ª passada")):
        planta = por_posicao.get(posicao)
        if planta is None:
            continue
        with contextlib.suppress(ApiError):
            evolucao = operator.get(
                f"/v1/fields/{campo['id']}/plants/{planta['plant_id']}/evolution"
            )
            mudancas = " → ".join(c["change"] for c in evolucao.get("changes", [])) or "—"
            step(
                f"evolução de {planta['plant_id']} ({papel}): {mudancas}; "
                f"AUDPC {evolucao.get('audpc', 0):.2f} incidência·dia"
            )

    with contextlib.suppress(ApiError):
        prevalencia = agronomist.get(f"/v1/fields/{campo['id']}/prevalence")
        topo = sorted(prevalencia["field_prior"].items(), key=lambda item: -item[1])[:3]
        treino = prevalencia["training_prior"]
        step(
            "prevalência estimada: "
            + ", ".join(f"{nome} {p:.0%} (treino {treino.get(nome, 0):.0%})" for nome, p in topo)
        )


# --- ponto de entrada ----------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="simulator.pomar", description=__doc__.split("\n\n")[0])
    parser.add_argument("--url", help="Plataforma já no ar. Sem isto, sobe uma própria.")
    parser.add_argument("--ia", help="Serviço de inferência (VALTEXA-B). Sem isto, IA simulada.")
    parser.add_argument("--fotos", type=Path, help="Fotos reais: <pasta>/<cultura>/<Classe>/.")
    parser.add_argument(
        "--quadros-por-camera", type=int, default=1, help="Quadros de cada câmera por planta."
    )
    parser.add_argument(
        "--versao",
        choices=("campo", "comercial"),
        default="campo",
        help="Versão do modelo de banana e citros: a de campo ou a só com dado comercial.",
    )
    parser.add_argument("--porta", type=int, default=0, help="Porta da plataforma própria.")
    parser.add_argument(
        "--manter", action="store_true", help="Deixa a plataforma no ar no fim, para o painel."
    )
    args = parser.parse_args(argv)
    if bool(args.ia) != bool(args.fotos):
        parser.error("--ia e --fotos andam juntos: a IA de verdade precisa de foto de verdade.")

    from simulator.__main__ import _force_utf8_output

    _force_utf8_output()
    fotos = Fotos(args.fotos)
    fotos.conferir([BANANAL, POMAR])  # antes de subir a plataforma, para falhar cedo
    if args.url:
        _imprimir(run(args.url, fotos, args.quadros_por_camera, versao=args.versao))
        return 0

    workspace = Path(__file__).resolve().parent.parent / ".simulacao-pomar"
    workspace.mkdir(exist_ok=True)
    # Antes de importar valtexa: as configurações são lidas uma vez por processo.
    os.environ["DATABASE_URL"] = f"sqlite:///{workspace / 'simulacao.db'}"
    os.environ["STORAGE_DIR"] = str(workspace / "storage")
    os.environ["ENVIRONMENT"] = "test"
    os.environ.setdefault("LOG_LEVEL", "WARNING")
    if args.ia:
        os.environ["SIMULATED_INFERENCE"] = "false"
        os.environ["INFERENCE_ENABLED"] = "true"
        os.environ["INFERENCE_URL"] = args.ia
        os.environ["INFERENCE_TIMEOUT_SECONDS"] = "240"
    else:
        os.environ["SIMULATED_INFERENCE"] = "true"
        os.environ["INFERENCE_ENABLED"] = "false"

    from simulator.__main__ import (
        _close_database,
        _free_port,
        _reset,
        _start_server,
        _wait_for_health,
    )

    _reset(workspace)
    port = args.porta or _free_port()
    url = f"http://127.0.0.1:{port}"
    server = _start_server(port)
    try:
        _wait_for_health(url)
        _seed()  # depois do servidor: é a subida dele que cria as tabelas
        print(f"\nPlataforma: {url}   |   IA: {args.ia or 'simulada'}")
        _imprimir(run(url, fotos, args.quadros_por_camera, versao=args.versao))
        if args.manter:
            print(f"\nPainel em {url} — admin@valtexa.dev / valtexa-demo-2026. Ctrl+C encerra.")
            with contextlib.suppress(KeyboardInterrupt):
                while True:
                    time.sleep(1)
    finally:
        server.should_exit = True
        time.sleep(0.5)
        _close_database()
    return 0


def _seed() -> None:
    from valtexa.db import session_scope
    from valtexa.seed import seed_demo, sync_device_models

    with session_scope() as session:
        sync_device_models(session)
        seed_demo(session)


def _imprimir(resultados: dict[str, Resultado]) -> None:
    banner("RESUMO")
    for nome, r in resultados.items():
        print(f"  {nome}")
        print(f"    quadros enviados ........... {r.quadros}")
        if r.plantas_indisponiveis:
            print("    plantas .................... indisponível sem o serviço de inferência")
            continue
        print(f"    plantas fundidas ........... {r.plantas}")
        print(f"    situação certa ............. {r.situacao_certa} de {r.plantas}")
        print(f"    doença certa nas doentes ... {r.doenca_certa} de {r.doentes}")
    print()


if __name__ == "__main__":
    sys.exit(main())
