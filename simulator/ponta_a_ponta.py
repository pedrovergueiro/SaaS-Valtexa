"""Ponta a ponta com o Rover Runtime de verdade (brief, seções 41, 44 e 58).

    CLIENTE → FAZENDA → TALHÃO (espaçamento) → MISSÃO → ROVER (simulador = rover/ real
    com HAL simulada) → CAPTURA → EDGE AI → EVENTO → STORAGE LOCAL → QUEDA DE REDE →
    SYNC → API → IA DE NUVEM (dublê) → FUSÃO POR PLANTA → INCIDÊNCIA → PRESCRIÇÃO →
    APROVAÇÃO → APLICAÇÃO → NOVA MISSÃO → COMPARAÇÃO → RELATÓRIO → AUDITORIA

Um roteiro só, usado pelo teste (``tests/test_ponta_a_ponta.py``, contra o
``TestClient``) e pelo ``python -m simulator --rover-runtime`` (contra o servidor
que o simulador sobe). Tudo pela API, como um cliente e a equipe usariam; o banco
só é tocado para criar as contas da equipe da ValTexa (que nascem fora do produto).

**O que é simulado (e está dito em cada saída)**: o hardware do Rover (câmeras,
GPS, rede), o modelo da Edge AI (``modelo_demo.onnx``, não agronômico), a IA de
nuvem (``SimulatedAnalyzer``, que lê o "chão de verdade" que a câmera simulada
anexa à imagem), o drone que aplica (cliente do protocolo, sem ``rover/``) e o
efeito do tratamento (as plantas tratadas aparecem sadias na passada seguinte).
"""

from __future__ import annotations

import json
import math
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from valtexa_rover.clock import ManualClock
from valtexa_rover.hal.interfaces import HttpResponse
from valtexa_rover.runtime.client import DeviceIdentity, generate_keypair
from valtexa_rover.sim import MODELO_DEMO_SHA256, CampoSimulado, PlanoDeRede, RoverSimulado

SENHA = "valtexa-ponta-a-ponta-2026"
DOENCAS = {"L1-P006": "doenca", "L1-P007": "doenca", "L2-P012": "doenca", "L3-P004": "praga"}
"""O "chão de verdade" do talhão simulado: quem está doente e onde."""
MARCA = {"doenca": "Rust", "praga": "Leaf_Miner_Damage", "sadia": "Healthy"}
ORIGEM = (-47.06000, -22.90000)


@dataclass
class Passo:
    nome: str
    ok: bool
    prova: str


@dataclass
class Resultado:
    passos: list[Passo] = field(default_factory=list)
    dados: dict[str, Any] = field(default_factory=dict)

    def registra(self, nome: str, ok: bool, prova: str) -> None:
        self.passos.append(Passo(nome, bool(ok), prova))
        if not ok:
            raise AssertionError(f"{nome}: {prova}")


def _check(r, esperado: int | tuple[int, ...] = (200, 201)) -> dict:
    esperados = (esperado,) if isinstance(esperado, int) else esperado
    if r.status_code not in esperados:
        raise AssertionError(f"{r.request.method} {r.request.url}: {r.status_code} {r.text[:400]}")
    return r.json() if r.content else {}


def _login(http, email: str) -> dict:
    corpo = _check(http.post("/v1/auth/login", json={"email": email, "password": SENHA}))
    cabecalho = {"Authorization": f"Bearer {corpo['access_token']}"}
    if corpo.get("tenant_id"):
        cabecalho["X-Tenant-Id"] = corpo["tenant_id"]
    return cabecalho


def _equipe(sessao_factory) -> dict[str, str]:
    """As contas da equipe ValTexa usadas no roteiro (nascem fora do produto)."""
    from sqlalchemy import select

    from valtexa.models import PlatformRole, User
    from valtexa.security.passwords import hash_password

    contas = {"comercial": PlatformRole.COMERCIAL, "suporte": PlatformRole.SUPORTE,
              "ia1": PlatformRole.IA_DADOS, "ia2": PlatformRole.IA_DADOS,
              "ops": PlatformRole.OPERACOES}
    emails = {}
    with sessao_factory() as s:
        for nome, papel in contas.items():
            email = f"{nome}.e2e@equipe.valtexa.dev"
            if s.scalars(select(User).where(User.email == email)).first() is None:
                s.add(User(email=email, full_name=f"Equipe {nome}", platform_role=papel,
                           password_hash=hash_password(SENHA)))
            emails[nome] = email
        s.commit()
    return emails


def _poligono(campo: CampoSimulado, margem_m: float = 6.0) -> list[list[float]]:
    lats = [p.lat for p in campo.plantas]
    lons = [p.lon for p in campo.plantas]
    dlat = margem_m / 110_540
    dlon = margem_m / (111_320 * math.cos(math.radians(lats[0])))
    a, b = min(lons) - dlon, max(lons) + dlon
    c, d = min(lats) - dlat, max(lats) + dlat
    return [[a, c], [b, c], [b, d], [a, d], [a, c]]


def provisionar_rover(transporte: Callable, token: str, serial: str) -> DeviceIdentity:
    """O robô gera o par e manda só a pública — pela mesma rede que usará depois."""
    privada, publica = generate_keypair()
    corpo = json.dumps({"provisioning_token": token, "serial_number": serial,
                        "public_key": publica}).encode()
    enviar = transporte.send if hasattr(transporte, "send") else transporte
    r: HttpResponse = enviar("POST", "/v1/device/provision", corpo,
                             {"Content-Type": "application/json"})
    if r.status not in (200, 201):
        raise AssertionError(f"provisionamento: {r.status} {r.body[:300]!r}")
    d = r.json()
    return DeviceIdentity(d["device_id"], d["key_id"], privada, d["platform_public_key"],
                          d.get("ota_public_key"))


@dataclass
class Real:
    """O roteiro com os componentes de verdade no lugar dos dublês.

    ``modelo``: o ``.onnx`` da Edge AI com os arquivos ao lado (perfil ``.edge.json``; no
    café, cabeça e torre de visão), publicado no registry pelo SHA-256 dele. ``folhas``:
    ``<pasta>/<Classe>/`` com fotos de folha que o modelo não viu no treino — cada recorte
    do quadro vira uma delas (:class:`valtexa_rover.sim.folhas.CameraDeFolhas`). A IA de
    nuvem é o serviço ``ia/`` de verdade (``INFERENCE_URL``), e a fusão por planta é a
    calibrada dele. Simulado continua: o robô andando (GPS, rede), a montagem do quadro e
    o drone que aplica.
    """

    modelo: Path
    folhas: Path
    incidencia: float = 0.5


def _cameras_de_folhas(rover, campo, relogio, real: Real, seed: int) -> None:
    from valtexa_rover.sim.folhas import CameraDeFolhas

    novas = [CameraDeFolhas(f"cam-{i}", campo, rover.gps, relogio, real.folhas, lado=lado,
                            incidencia=real.incidencia, seed=seed + i)
             for i, lado in enumerate(("left", "right"))]
    rover.cameras[:] = novas
    rover.hardware.cameras[:] = novas


def _fusao_calibrada(http, res: Resultado, sessao_factory, gestor: dict,
                     agronomo: dict, field_id: str, missao: str) -> None:
    """21b-23b com a IA de verdade: o worker leva os recortes de todo quadro do Rover à
    fusão calibrada do ``ia/``; a incidência e a prescrição planta a planta vêm de lá."""
    from valtexa.services import fusao_borda

    with sessao_factory() as s:
        while fusao_borda.varrer(s):
            s.commit()
        s.commit()
        estados = fusao_borda.resumo(s, missao)
    res.registra("21b fusão calibrada (ia/)", estados.get("ok", 0) > 0,
                 f"resultados do Rover na fusão por planta do ia/: {estados}")
    inc = _check(http.get(f"/v1/fields/{field_id}/plants/incidence", headers=gestor,
                          params={"pass_id": missao}))
    res.registra("22b incidência calibrada", inc.get("incidence") is not None,
                 f"{inc.get('n_plants')} plantas na fusão; aparente {inc.get('apparent')}, "
                 f"corrigida {inc.get('incidence')} (IC95 {inc.get('ci95')}), "
                 f"método {inc.get('method')}")
    pedido = {
        "doenca": "Rust", "pass_id": missao,
        "produto": {"nome": "Fungicida cúprico (teste)", "registro_mapa": "0000",
                    "culturas": ["coffee"], "doencas": ["Rust"], "dose_ml_por_planta": 20,
                    "dose_min_ml_por_planta": 10, "dose_max_ml_por_planta": 40,
                    "preco_por_litro": 150, "eficacia": 0.7, "carencia_dias": 3},
        "economia": {"perda_por_planta": 12.0, "custo_operacional_por_planta": 0.5},
    }
    presc = _check(http.post(f"/v1/fields/{field_id}/plants/prescription", headers=agronomo,
                             json=pedido))
    resumo = presc.get("resumo") or {}
    res.registra("23b prescrição planta a planta (ia/)", bool(presc),
                 f"recomendação do ia/ sobre a fusão calibrada: {resumo or list(presc)[:6]}")


def executar(http, transporte: Callable, sessao_factory, pasta: Path, *,
             passos: int = 70, log: Callable[[str], None] = lambda _m: None,
             real: Real | None = None) -> Resultado:
    res = Resultado()
    eq = _equipe(sessao_factory)
    campo = CampoSimulado.gerar(*ORIGEM, linhas=3, plantas_por_linha=18,
                                espacamento_linhas_m=3.5, espacamento_plantas_m=0.7,
                                doentes=DOENCAS)
    contorno = _poligono(campo, margem_m=8.0)  # talhão
    area_util = _poligono(campo, margem_m=6.0)  # zona, por dentro do talhão
    area_missao = _poligono(campo, margem_m=4.0)  # missões, por dentro da zona

    # 1 cliente, 3 fazenda, 4 talhão (com espaçamento) — cadastro pela equipe (Comercial)
    comercial = _login(http, eq["comercial"])
    sufixo = datetime.now(UTC).strftime("%H%M%S%f")
    cad = _check(http.post("/v1/admin/tenants", headers=comercial, json={
        "tenant": {"name": "Fazendas Ponta a Ponta", "slug": f"ponta-a-ponta-{sufixo}",
                   "contact_name": "Produtor", "email": "produtor@exemplo.dev"},
        "farm": {"name": "Fazenda Simulada", "center_lat": ORIGEM[1], "center_lon": ORIGEM[0]},
        "field": {"name": "Talhão Café 1", "crop": "coffee", "boundary": contorno,
                  "row_spacing_m": 3.5, "plant_spacing_m": 0.7, "row_count": 3},
    }), 201)
    tenant_id, farm_id, field_id = cad["tenant"]["id"], cad["farm_id"], cad["field_id"]
    res.registra("1 criar cliente", bool(tenant_id), f"POST /v1/admin/tenants → {tenant_id}")
    res.registra("3 criar fazenda", bool(farm_id), f"farm_id {farm_id}")
    res.registra("4 criar talhão", bool(field_id), f"field_id {field_id}")

    # 2 usuários do cliente: a equipe de Suporte, em modo assistido e auditado
    suporte = _login(http, eq["suporte"])
    sessao = _check(http.post("/v1/platform/support-sessions", headers=suporte, json={
        "tenant_id": tenant_id, "reason": "Implantação do cliente (ponta a ponta)"}), 201)
    tok = {"Authorization": f"Bearer {sessao['access_token']}"}
    _check(http.post(f"/v1/platform/support-sessions/{sessao['session']['id']}/mode",
                     headers=tok, json={"mode": "assistido",
                                        "reason": "Cadastrar a equipe do cliente"}))
    for email, papel in (("gestor@pap.dev", "admin"), ("agronomo@pap.dev", "agronomist"),
                         ("operador@pap.dev", "operator")):
        _check(http.post("/v1/users", headers=tok, json={
            "email": email, "full_name": email.split("@")[0].title(), "password": SENHA,
            "role": papel}), 201)
    gestor, agronomo = _login(http, "gestor@pap.dev"), _login(http, "agronomo@pap.dev")
    operador = _login(http, "operador@pap.dev")
    res.registra("2 criar usuário", True, "gestor, agrônomo e operador via suporte assistido")

    # 5 espaçamento confirmado pelo cliente
    # Com a IA de verdade a fusão calibrada põe cada quadro na linha pelo GNSS: o talhão
    # precisa do azimute das linhas (as do campo simulado correm para o norte).
    talhao = _check(http.patch(f"/v1/fields/{field_id}", headers=gestor,
                               json={"row_spacing_m": 3.5, "plant_spacing_m": 0.7,
                                     **({"row_azimuth_deg": 0.0} if real else {})}))
    res.registra("5 configurar espaçamento",
                 talhao.get("row_spacing_m") == 3.5 and talhao.get("plant_spacing_m") == 0.7,
                 "PATCH /v1/fields/{id}: 3,5 m entre linhas, 0,7 m entre plantas")
    zona = _check(http.post(f"/v1/fields/{field_id}/zones", headers=gestor,
                            json={"name": "Zona inteira", "boundary": area_util}), 201)

    # Rover, drone e dock entram na frota pelo protocolo de provisionamento
    def token(modelo: str, serial: str) -> str:
        return _check(http.post("/v1/provisioning-tokens", headers=gestor, json={
            "device_model_code": modelo, "serial_number": serial, "farm_id": farm_id}),
            201)["token"]

    identidade = provisionar_rover(transporte, token("ROVER_SCOUT_V1", f"PAP-R-{sufixo}"),
                                   f"PAP-R-{sufixo}")
    res.dados["rover_id"] = identidade.device_id

    # Registry: IA & Dados publica a versão com o modelo de demonstração (duas pessoas)
    ia1, ia2 = _login(http, eq["ia1"]), _login(http, eq["ia2"])
    designado = _designado(transporte, identidade, field_id)
    if real:
        from valtexa_rover.sim.folhas import instalar_modelo

        sha_modelo = instalar_modelo(real.modelo, pasta / "rover" / "artefatos")
        versao = {"version": f"real-{sufixo}", "name": f"{real.modelo.stem} (pesos reais)",
                  "original_artifact_uri": f"arquivo://{real.modelo.name}",
                  "original_artifact_sha256": sha_modelo,
                  "caveat": "Pesos reais; limiares do perfil provisórios até a coleta de campo."}
    else:
        sha_modelo = MODELO_DEMO_SHA256
        versao = {"version": f"sim-{sufixo}", "name": "Demonstração (SIMULADO)",
                  "original_artifact_uri": "pacote://valtexa_rover/sim/modelo_demo.onnx",
                  "original_artifact_sha256": MODELO_DEMO_SHA256,
                  "caveat": "Modelo de demonstração do simulador: NÃO é agronômico."}
    vid = _check(http.post("/v1/platform/models", headers=ia1, json={
        "model_key": designado, "platform": "ground", "crops": ["coffee"],
        "metrics": {"f1": 0.5}, **versao}), 201)["id"]
    for quem, para in ((ia1, "validacao"), (ia2, "aprovado"), (ia1, "staging"),
                       (ia1, "producao")):
        _check(http.post(f"/v1/platform/models/{vid}/transition", headers=quem,
                         json={"to": para, "reason": "ponta a ponta"}))

    # O robô liga, sobe a telemetria (bateria etc.) e fica DISPONÍVEL na frota.
    relogio = ManualClock(datetime.now(UTC))
    rover = RoverSimulado(pasta / "rover", identidade, transporte, campo, clock=relogio,
                          cameras=2, marca_nuvem=MARCA, seed=3)
    if real:
        _cameras_de_folhas(rover, campo, relogio, real, seed=3)
    rover.core.step()

    # 6 missão, 7 associar o Rover — criada, autorizada e despachada (comando assinado)
    missao1 = _missao(http, operador, field_id, zona["id"], identidade.device_id, area_missao)
    res.registra("6 criar missão", bool(missao1), f"mission_id {missao1}")
    res.registra("7 associar Rover", True, f"device_id {identidade.device_id} na missão")

    # 8-18 o rover/ de verdade com a HAL simulada
    aceita = rover.core.accept_cloud_mission()
    res.registra("8 executar missão no simulador", aceita == missao1,
                 "missão assinada aceita pelo Mission Manager do rover/")
    plano = PlanoDeRede(sem_rede=[(15, 45)])
    r1 = rover.rodar(30, plano)
    pendente_offline = rover.core.sync.pending()
    rover.reiniciar()  # robô desligado e ligado no meio da janela sem rede
    r2 = rover.rodar(passos - 30, plano, inicio=30)
    rover.core.complete_mission()
    quadros = r1.quadros + r2.quadros
    res.registra("9 simular captura", quadros > 0, f"{quadros} quadros de 2 câmeras")
    modelo = rover.core.engine.package
    res.registra("10 Edge AI real", modelo is not None and modelo.sha256 == sha_modelo,
                 "ONNX Runtime com o modelo designado pelo registry, hash conferido "
                 + (f"({real.modelo.name}, pesos reais, sobre fotos de folha reais)" if real
                    else "(modelo de demonstração)"))
    cats = {**r1.categorias}
    for k, v in r2.categorias.items():
        cats[k] = cats.get(k, 0) + v
    res.registra("11 classificar imagens", len(cats) >= 2, f"categorias: {cats}")
    eventos = r1.eventos + r2.eventos
    res.registra("12 criar evento", eventos > 0, f"{eventos} IMAGE_EVENT_DETECTED")
    originais = rover.core.store.scalar(
        "SELECT COUNT(*) FROM files WHERE role = 'original'")
    res.registra("13 preservar imagem importante", originais >= eventos,
                 f"{originais} originais guardados para {eventos} eventos")
    resumo = rover.core.summary()
    reduzidas = rover.core.store.scalar("SELECT COUNT(*) FROM files WHERE role = 'reduzida'")
    res.registra("14 não enviar tudo", originais < quadros,
                 f"{quadros} quadros → {originais} originais + {reduzidas} reduzidas "
                 f"({resumo['files_bytes']} bytes guardados)")
    res.registra("15 simular perda de internet", r1.passos_offline + r2.passos_offline == 30,
                 "30 passos sem rede (15-45), com reinício no meio")
    res.registra("16 continuar offline", pendente_offline > 0 and quadros >= passos,
                 f"{pendente_offline} itens na fila durante a queda; missão seguiu")
    faltando = rover.sincronizar()
    res.registra("17 recuperar conexão", True, "rede de volta: ROVER_ONLINE")
    res.registra("18 sincronizar", faltando == 0, "fila do rover zerada")

    # 19-22 plataforma: registros, ponte para a IA de nuvem, fusão por planta, incidência
    registros = _check(http.get("/v1/edge/records", headers=gestor,
                                params={"mission_id": missao1, "limit": 1000}))
    res.registra("19 processar na plataforma", len(registros) > 0,
                 f"{len(registros)} registros em /v1/edge/records")
    obs = _check(http.get("/v1/observations", headers=agronomo, params={"field_id": field_id}))
    rotulos = dict(sorted({o["label"]: 0 for o in obs}.items()))
    for o in obs:
        rotulos[o["label"]] += 1
    res.registra("20 gerar resultado", len(obs) > 0 and all(o["diagnosis_id"] for o in obs),
                 f"{len(obs)} eventos viraram observação + diagnóstico na IA de nuvem "
                 + (f"(serviço ia/ de verdade: {rotulos})" if real else "(dublê)"))
    plantas = _check(http.get(f"/v1/missions/{missao1}/plants", headers=agronomo))
    doentes = {p["plant_id"] for p in plantas["plants"] if p["status"] == "doente"}
    perto = set(DOENCAS) | {_vizinha(x, d) for x in DOENCAS for d in (-1, 1)}
    if real:
        # Com IA de verdade o critério é medir, não acertar por construção: quantas das
        # plantas doentes foram achadas e quantas sadias viraram alarme. Com um analisador
        # só na nuvem não há par independente, então nada vira "doente" sem o agrônomo:
        # conta como achada o que o Rover pôs em doente, suspeita ou revisar (o mesmo
        # critério do relatório da validação de campo).
        marcadas = {p["plant_id"] for p in plantas["plants"]
                    if p["status"] in ("doente", "suspeita", "revisar")}
        achadas = {x for x in DOENCAS if x in marcadas or any(
            _vizinha(x, d) in marcadas for d in (-1, 1))}
        alarmes = sorted(marcadas - perto)
        res.registra("21 associar à planta/região", bool(achadas),
                     f"doentes achadas {len(achadas)}/{len(DOENCAS)} ({sorted(achadas)}); "
                     f"sadias longe de doente com alarme: {len(alarmes)}/"
                     f"{plantas['plants_seen'] - len(perto)} {alarmes}")
    else:
        res.registra("21 associar à planta/região", bool(doentes) and doentes <= perto,
                     f"plantas doentes: {sorted(doentes)} (verdade: {sorted(DOENCAS)})")
    inc = plantas["incidence"]
    res.registra("22 incidência", inc["ratio"] is not None,
                 f"{inc['diseased']}/{plantas['plants_seen']} plantas = {inc['ratio']} "
                 f"(IC95 {inc['interval_95']})")
    if real:
        _fusao_calibrada(http, res, sessao_factory, gestor, agronomo, field_id, missao1)

    # 23 prescrição, 24 aprovação, 25 aplicação
    # O diagnóstico mais confiante da doença no talhão é o que vai ao motor de decisão.
    alvos = [o for o in obs if o["label"] == "Rust"] or [
        o for o in obs if o["label"] not in ("Healthy", None)]
    if not alvos:
        raise AssertionError(f"a IA de nuvem não achou doença em nenhum evento: {rotulos}")
    doente = max(alvos, key=lambda o: o["confidence"] or 0)
    if real:
        # Sem par independente na nuvem, o diagnóstico espera o agrônomo (regra da dupla
        # validação). SIMULAÇÃO: o agrônomo do roteiro confirma o mais confiante.
        _check(http.post(f"/v1/diagnoses/{doente['diagnosis_id']}/review", headers=agronomo,
                         json={"label": doente["label"], "confirmed": True,
                               "notes": "Confirmado na revisão (roteiro ponta a ponta)."}))
    produto = _check(http.post("/v1/products", headers=gestor, json={
        "name": "Fungicida cúprico (SIMULADO)", "allowed_crops": ["coffee"],
        "registration_number": "SIM-0001",
        "authorized_targets": ["Rust"], "default_rate_l_ha": 1.0, "min_rate_l_ha": 0.5,
        "max_rate_l_ha": 2.0, "max_wind_ms": 6.0}), 201)
    lote = _check(http.post(f"/v1/products/{produto['id']}/batches", headers=gestor,
                            json={"code": "L-001", "quantity_l": 100}), 201)
    decisao = _check(http.post(f"/v1/diagnoses/{doente['diagnosis_id']}/decide",
                               headers=operador))
    alvo = [campo.plantas[0].lon, campo.plantas[0].lat]
    drone = _dispositivo(http, transporte, token("DRONE_ACTION_V1", f"PAP-D-{sufixo}"),
                         f"PAP-D-{sufixo}")
    dock = _dispositivo(http, transporte, token("DOCK_BASE_V1", f"PAP-K-{sufixo}"),
                        f"PAP-K-{sufixo}")
    dock.req("POST", "/v1/device/telemetry", {"samples": [{
        "sequence_number": 1, "recorded_at": datetime.now(UTC).isoformat(),
        "sensors": {"wind_ms": 2.0}}]})
    drone.req("POST", "/v1/device/telemetry", {"samples": [{
        "sequence_number": 1, "recorded_at": datetime.now(UTC).isoformat(),
        "rtk_fix": "fixed", "battery_percent": 96.0, "lat": alvo[1], "lon": alvo[0]}]})
    tanque = _check(http.get("/v1/tanks", headers=gestor,
                             params={"device_id": drone.identity.device_id}))[0]["id"]
    prescricao = _check(http.post("/v1/missions", headers=agronomo, json={
        "kind": "spray", "field_id": field_id, "zone_id": zona["id"],
        "device_id": drone.identity.device_id, "target_polygon": area_missao,
        "product_id": produto["id"], "product_batch_id": lote["id"], "tank_id": tanque,
        "authorized_rate_l_ha": 1.0, "authorized_quantity_l": 2.0,
        "decision_id": decisao.get("id")}), 201)["id"]
    res.registra("23 prescrição", bool(prescricao),
                 f"recomendação '{decisao.get('outcome')}' ({decisao.get('rationale', '')[:90]}) "
                 f"→ missão de pulverização {prescricao} (produto, dose, quantidade)")
    bloqueada = _check(http.post(f"/v1/missions/{prescricao}/authorize", headers=operador))
    _check(http.post(f"/v1/missions/{prescricao}/approve", headers=agronomo,
                     json={"confirm": True}))
    _check(http.post(f"/v1/tanks/{tanque}/load", headers=gestor, json={
        "product_id": produto["id"], "batch_id": lote["id"], "volume_l": 5.0}))
    liberada = _check(http.post(f"/v1/missions/{prescricao}/authorize", headers=operador))
    res.registra("24 aprovar", bloqueada["verdict"] == "blocked"
                 and liberada["verdict"] == "safe_to_execute",
                 "bloqueada sem aprovação do agrônomo "
                 f"({bloqueada.get('blocked_code')}); liberada depois dela")
    _check(http.post(f"/v1/missions/{prescricao}/dispatch", headers=operador))
    drone.req("POST", f"/v1/device/missions/{prescricao}/ack",
              {"mission_id": prescricao, "accepted": True})
    app = drone.req("POST", "/v1/device/applications/start", {
        "mission_id": prescricao, "started_at": datetime.now(UTC).isoformat(),
        "tank_id": tanque})
    fim = drone.req("POST", f"/v1/device/applications/{app['id']}/stop", {
        "stopped_at": datetime.now(UTC).isoformat(), "amount_used_l": 1.6, "area_ha": 0.02,
        "track": [[alvo[0], alvo[1], 0.02], [alvo[0], alvo[1] + 0.00002, 0.02]]})
    res.registra("25 registrar aplicação", fim.get("outside_polygon_points") == 0,
                 f"aplicação {app['id']} registrada pelo drone (simulado)")

    # 26 nova missão (o tratamento fez efeito em 3 das 4 plantas — simulação)
    curadas = ["L1-P006", "L1-P007", "L2-P012"]
    campo2 = CampoSimulado.gerar(*ORIGEM, linhas=3, plantas_por_linha=18,
                                 espacamento_linhas_m=3.5, espacamento_plantas_m=0.7,
                                 doentes={k: v for k, v in DOENCAS.items() if k not in curadas})
    missao2 = _missao(http, operador, field_id, zona["id"], identidade.device_id, area_missao)
    # Outro dia: o robô religa (relógio novo, mesma pasta e identidade).
    rover2 = RoverSimulado(pasta / "rover", identidade, transporte, campo2,
                           clock=ManualClock(datetime.now(UTC)),
                           cameras=2, marca_nuvem=MARCA, seed=4)
    if real:
        _cameras_de_folhas(rover2, campo2, rover2.clock, real, seed=4)
    assert rover2.core.accept_cloud_mission() == missao2
    rover2.rodar(passos)
    rover2.core.complete_mission()
    res.registra("26 nova missão", rover2.sincronizar() == 0, f"mission_id {missao2}")

    # 27 comparar, 28 relatório
    comp = _check(http.get(f"/v1/missions/{missao2}/comparison", headers=agronomo,
                           params={"baseline_id": missao1}))
    res.registra("27 comparar resultados", comp["incidence_after"] < comp["incidence_before"],
                 f"incidência {comp['incidence_before']} → {comp['incidence_after']}; "
                 f"recuperadas {comp['recovered']}")
    rel = _check(http.get(f"/v1/missions/{missao2}/report", headers=gestor))
    res.registra("28 relatório", rel["images_processed"] > 0 and rel["history"]
                 and (real is not None or rel["simulated"] is True),
                 f"relatório da missão: {rel['images_processed']} imagens, "
                 f"{len(rel['occurrences'])} ocorrências, histórico {len(rel['history'])}")

    # 29 no SaaS do cliente, 30 no console interno, 31 auditoria
    painel = _check(http.get("/v1/dashboard", headers=gestor))
    frota = _check(http.get("/v1/devices", headers=gestor))
    res.registra("29 tudo no SaaS", bool(painel) and len(frota) >= 3,
                 "painel, frota, registros, plantas, relatório pelas rotas do cliente")
    ops = _login(http, eq["ops"])
    plataforma = _check(http.get("/v1/platform/fleet", headers=ops,
                                 params={"tenant_id": tenant_id}))
    saude = _check(http.get("/v1/platform/ai-health", headers=ia1))
    res.registra("30 tudo no console interno", len(plataforma) >= 3 and bool(saude),
                 "frota de todos os clientes, registry, saúde da IA (equipe)")
    trilha = _check(http.get("/v1/audit", headers=gestor, params={"limit": 1000}))
    acoes = {t["action"] for t in trilha}
    esperadas = {"device.provisioned", "mission.approved", "application.completed",
                 "farm.updated" if "farm.updated" in acoes else "field.updated"}
    res.registra("31 auditar as ações", esperadas <= acoes,
                 f"{len(trilha)} entradas; inclui {sorted(esperadas)}")

    res.dados.update({"tenant_id": tenant_id, "field_id": field_id, "missao1": missao1,
                      "missao2": missao2, "plantas": plantas, "comparacao": comp,
                      "relatorio": rel, "quadros": quadros, "eventos": eventos})
    return res


def _vizinha(pid: str, delta: int) -> str:
    linha, p = pid.split("-P")
    return f"{linha}-P{int(p) + delta:03d}"


def _designado(transporte, identidade: DeviceIdentity, field_id: str) -> str:
    from valtexa_rover.hal.simulated import FlakyNetwork
    from valtexa_rover.runtime.client import DeviceClient

    cliente = DeviceClient(identidade, FlakyNetwork(transporte) if not hasattr(
        transporte, "send") else transporte, ManualClock(datetime.now(UTC)))
    for d in cliente.request("GET", "/v1/device/models").json():
        if d["field_id"] == field_id:
            return d["model_key"]
    raise AssertionError("o registry não designou modelo para o talhão")


def _missao(http, operador: dict, field_id: str, zone_id: str, device_id: str,
            contorno) -> str:
    m = _check(http.post("/v1/missions", headers=operador, json={
        "kind": "scout", "field_id": field_id, "zone_id": zone_id, "device_id": device_id,
        "target_polygon": contorno, "plan": {"swath_m": 3.5}}), 201)["id"]
    parecer = _check(http.post(f"/v1/missions/{m}/authorize", headers=operador))
    if parecer["verdict"] != "safe_to_execute":
        raise AssertionError(f"missão de varredura bloqueada: {parecer}")
    _check(http.post(f"/v1/missions/{m}/dispatch", headers=operador))
    return m


@dataclass
class _Dispositivo:
    identity: DeviceIdentity
    client: Any

    def req(self, method: str, path: str, corpo: dict) -> dict:
        r = self.client.request(method, path, json_body=corpo)
        if r.status not in (200, 201):
            raise AssertionError(f"{method} {path}: {r.status} {r.body[:300]!r}")
        return r.json()


def _dispositivo(http, transporte, token: str, serial: str) -> _Dispositivo:
    """Drone e dock: clientes do mesmo protocolo assinado (não são o rover/)."""
    from valtexa_rover.hal.simulated import FlakyNetwork
    from valtexa_rover.runtime.client import DeviceClient

    ident = provisionar_rover(transporte, token, serial)
    rede = transporte if hasattr(transporte, "send") else FlakyNetwork(transporte)
    return _Dispositivo(ident, DeviceClient(ident, rede, ManualClock(datetime.now(UTC))))


__all__ = ["Resultado", "executar", "provisionar_rover"]
