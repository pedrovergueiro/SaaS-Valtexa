"""Ensaios de validação do Rover: catálogo, veredito no servidor, portões por fase.

O robô roda o ensaio (comando assinado ``ensaio``, ``valtexa_rover.ensaios``) e manda o
laudo com as **amostras brutas**. Aqui o veredito é **recalculado** com as amostras e com
os limites que a própria plataforma assinou no comando — o ``aprovado`` do robô é só uma
prévia, guardada para comparar (``divergente``). Um robô com software adulterado não
aprova um portão dizendo "aprovado".

**Limites.** Cada ensaio tem os limites do portão (:data:`CATALOGO`). O operador pode
**apertar** um limite ao mandar o ensaio, nunca afrouxar (422). Parâmetros de medida (a
distância da trena, o ponto conhecido do GNSS) são livres.

**Portões.** Uma fase passa quando o último resultado de cada ensaio obrigatório dela
está aprovado e vale para o portão (feito no robô de verdade, com os parâmetros que o
portão exige — ex.: GNSS com ponto conhecido e teste de perda). Resultado simulado não
abre portão (só com ``aceitar_simulado``, para o laudo do simulador). Fases sem ensaio
automático (2, 3, 4) seguem o guia de validação, à mão.

**Regressão.** Um ensaio que estava aprovado e reprova no mesmo robô publica
``ensaio.regressao`` — vira aviso para a equipe (``plataforma_ensaio_regressao``).
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from valtexa.models import Device, DeviceCommand, EnsaioResultado, SubjectType
from valtexa.services import events

GRAVIDADE_PADRAO = 9.80665
RAIO_TERRA_M = 6_378_137.0
MAX = "max"
"""Limite superior: o medido tem de ficar abaixo; apertar = diminuir."""
MIN = "min"
"""Limite inferior: o medido tem de ficar acima; apertar = aumentar."""


class EnsaioInvalidoError(ValueError):
    """Ensaio desconhecido, parâmetro estranho ou limite mais frouxo que o do portão."""


# ---------------------------------------------------------------------------
# Contas (as mesmas do robô, refeitas aqui com as amostras)
# ---------------------------------------------------------------------------


def _media(v: list[float]) -> float:
    return sum(v) / len(v)


def _desvio(v: list[float]) -> float:
    if len(v) < 2:
        return 0.0
    m = _media(v)
    return math.sqrt(sum((x - m) ** 2 for x in v) / (len(v) - 1))


def percentil(v: list[float], p: float) -> float:
    o = sorted(v)
    if len(o) == 1:
        return float(o[0])
    pos = (len(o) - 1) * p / 100.0
    baixo = math.floor(pos)
    alto = min(baixo + 1, len(o) - 1)
    return float(o[baixo] + (o[alto] - o[baixo]) * (pos - baixo))


def _numeros(valores: Any) -> list[float]:
    """Só os números finitos de uma lista vinda do robô (o resto é descartado)."""
    if not isinstance(valores, list):
        return []
    saida = []
    for v in valores:
        if isinstance(v, bool) or not isinstance(v, int | float):
            continue
        if math.isfinite(v):
            saida.append(float(v))
    return saida


def wilson(k: int, n: int, z: float = 1.96) -> list[float] | None:
    if n == 0:
        return None
    p = k / n
    centro = (p + z * z / (2 * n)) / (1 + z * z / n)
    margem = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return [round(max(0.0, centro - margem), 4), round(min(1.0, centro + margem), 4)]


def criterio(nome: str, valor: float | None, limite: float | None, op: str,
             unidade: str = "") -> dict[str, Any]:
    if valor is None or limite is None:
        ok = False
    elif op == "<=":
        ok = valor <= limite
    elif op == ">=":
        ok = valor >= limite
    else:
        ok = valor == limite
    if isinstance(valor, float):
        valor = round(valor, 4)
    return {"nome": nome, "valor": valor, "limite": limite, "op": op, "unidade": unidade,
            "ok": bool(ok)}


def _queda_clock(serie: list[float | None]) -> float | None:
    pico, pior = None, 0.0
    for v in serie:
        if v is None:
            continue
        if pico is None or v > pico:
            pico = v
        elif pico > 0:
            pior = max(pior, 100.0 * (pico - v) / pico)
    return None if pico is None else pior


def _angulo(a: float, b: float) -> float:
    d = (a - b + 180.0) % 360.0 - 180.0
    return 180.0 if d == -180.0 else d


Calculo = tuple[list[dict], dict[str, Any], str | None]
"""(critérios, medidas, motivo de não valer para o portão)."""


def _calor(p: dict, a: dict) -> Calculo:
    janelas = _numeros(a.get("janelas_qps"))
    if not janelas:
        return [criterio("perda_vazao_pct", None, p["perda_max_pct"], "<=", "%")], {}, None
    perda = 100.0 * (janelas[0] - janelas[-1]) / janelas[0] if janelas[0] > 0 else 100.0
    termica = [x for x in (a.get("termica") or []) if isinstance(x, dict)]
    quedas = [_queda_clock([x.get(k) if isinstance(x.get(k), int | float) else None
                            for x in termica]) for k in ("cpu_freq_mhz", "gpu_freq_mhz")]
    temps = [float(x["temp_c"]) for x in termica if isinstance(x.get("temp_c"), int | float)]
    crit = [criterio("perda_vazao_pct", perda, p["perda_max_pct"], "<=", "%")]
    medidas = {"perda_vazao_pct": round(perda, 2), "janelas": len(janelas),
               "vazao_primeira_qps": round(janelas[0], 3),
               "vazao_ultima_qps": round(janelas[-1], 3),
               "temp_max_c": max(temps) if temps else None}
    medidas_clock = [q for q in quedas if q is not None]
    if medidas_clock:
        crit.append(criterio("queda_clock_pct", max(medidas_clock), p["queda_clock_pct"], "<=",
                             "%"))
    if p.get("temp_max_c") is not None:
        crit.append(criterio("temp_max_c", max(temps) if temps else None, p["temp_max_c"],
                             "<=", "°C"))
    motivo = None
    if not medidas_clock:
        motivo = "sem clocks do tegrastats: throttling não medido"
    elif p.get("duracao_min", 0) < 120:
        motivo = "o portão pede 2 h de carga (duracao_min ≥ 120)"
    return crit, medidas, motivo


def _cameras(p: dict, a: dict) -> Calculo:
    esperadas = int(a.get("esperadas") or 0)
    perdidas = int(a.get("perdidas") or 0)
    perda = 100.0 * perdidas / esperadas if esperadas > 0 else None
    derivas = _numeros(a.get("derivas_ms"))
    idades = _numeros(a.get("idades_gnss_ms"))
    d95 = percentil(derivas, 95) if derivas else None
    g95 = percentil(idades, 95) if idades else None
    n = int(a.get("cameras") or 0)
    crit = [criterio("perda_pct", perda, p["perda_max_pct"], "<=", "%"),
            criterio("deriva_p95_ms", d95, p["deriva_max_ms"], "<=", "ms"),
            criterio("gnss_p95_ms", g95, p["gnss_max_ms"], "<=", "ms")]
    medidas = {"cameras": n, "esperadas": esperadas, "perdidas": perdidas,
               "perda_pct": None if perda is None else round(perda, 3),
               "deriva_p95_ms": None if d95 is None else round(d95, 2),
               "gnss_p95_ms": None if g95 is None else round(g95, 2)}
    motivo = None if n >= CAMERAS_NO_PORTAO else (
        f"o portão pede {CAMERAS_NO_PORTAO}+ câmeras juntas (foram {n})")
    return crit, medidas, motivo


def _profundidade(p: dict, a: dict) -> Calculo:
    real = float(p["distancia_real_mm"])  # o que a plataforma assinou, não o que voltou
    medianas = _numeros(a.get("medianas_mm"))
    preench = _numeros(a.get("preenchimentos"))
    medida = percentil(medianas, 50) if medianas else None
    erro = None if medida is None else medida - real
    fill = _media(preench) if preench else 0.0
    crit = [criterio("erro_abs_mm", None if erro is None else abs(erro), p["tolerancia_mm"],
                     "<=", "mm"),
            criterio("preenchimento", fill, p["preenchimento_min"], ">=")]
    medidas = {"distancia_real_mm": real, "mediana_mm": None if medida is None
               else round(medida, 1), "erro_mm": None if erro is None else round(erro, 1),
               "preenchimento": round(fill, 3), "leituras": len(medianas)}
    return crit, medidas, None


def _precisao(lats: list[float], lons: list[float], ref) -> dict[str, float]:
    lat0, lon0 = ref if ref is not None else (_media(lats), _media(lons))
    pts = [(math.radians(lo - lon0) * RAIO_TERRA_M * math.cos(math.radians(lat0)),
            math.radians(la - lat0) * RAIO_TERRA_M) for la, lo in zip(lats, lons, strict=True)]
    raios = [math.hypot(e, n) for e, n in pts]
    me, mn = _media([x[0] for x in pts]), _media([x[1] for x in pts])
    return {"cep50_cm": 100 * percentil(raios, 50), "cep95_cm": 100 * percentil(raios, 95),
            "drms2_cm": 200 * math.sqrt(_media([e * e + n * n for e, n in pts])),
            "vies_cm": 100 * math.hypot(me, mn) if ref is not None else 0.0}


def _gnss(p: dict, a: dict) -> Calculo:
    tempo = a.get("tempo_fix_s")
    tempo = float(tempo) if isinstance(tempo, int | float) else None
    crit = [criterio("tempo_fix_s", tempo, p["tempo_fix_max_s"], "<=", "s")]
    medidas: dict[str, Any] = {"tempo_fix_s": tempo}
    if tempo is None:
        return crit, medidas, None
    lats, lons = _numeros(a.get("lat")), _numeros(a.get("lon"))
    ref = None
    if p.get("lat_ref") is not None and p.get("lon_ref") is not None:
        ref = (float(p["lat_ref"]), float(p["lon_ref"]))
    prec = _precisao(lats, lons, ref) if lats and len(lats) == len(lons) else {}
    medidas.update({k: round(v, 2) for k, v in prec.items()})
    medidas["amostras"] = len(lats)
    crit.append(criterio("cep95_cm", prec.get("cep95_cm"), p["cep95_max_cm"], "<=", "cm"))
    if ref is not None:
        crit.append(criterio("vies_cm", prec.get("vies_cm"), p["vies_max_cm"], "<=", "cm"))
    if p.get("perda_s", 0) > 0:
        perdas = [x for x in (a.get("perdas") or []) if isinstance(x, dict)]
        retomadas = [float(x["retomada_s"]) for x in perdas
                     if isinstance(x.get("retomada_s"), int | float)]
        sem_volta = len(perdas) - len(retomadas)
        crit += [criterio("perdas_observadas", len(perdas), 1, ">="),
                 criterio("perdas_sem_retomada", sem_volta, 0, "=="),
                 criterio("retomada_max_s", max(retomadas) if retomadas else None,
                          p["retomada_max_s"], "<=", "s")]
        medidas["perdas"] = len(perdas)
    motivo = None
    if ref is None:
        motivo = "o portão pede o ponto conhecido (lat_ref/lon_ref)"
    elif not p.get("perda_s"):
        motivo = "o portão pede o teste de perda e retomada (perda_s > 0)"
    return crit, medidas, motivo


def _imu(p: dict, a: dict) -> Calculo:
    acc = a.get("accel_ms2") or []
    ax, ay, az = ([_numeros(x) for x in acc] + [[], [], []])[:3]
    roll, pitch = _numeros(a.get("roll_deg")), _numeros(a.get("pitch_deg"))
    n = min(len(ax), len(ay), len(az))
    tol = p["tolerancia_inclinacao_deg"]
    if n < 2 or not roll or not pitch:
        return [criterio("erro_gravidade_ms2", None, p["tolerancia_g_ms2"], "<=")], {}, None
    g = _media([math.sqrt(ax[i] ** 2 + ay[i] ** 2 + az[i] ** 2) for i in range(n)])
    ra = _media([math.degrees(math.atan2(ay[i], az[i])) for i in range(n)])
    pa = _media([math.degrees(math.atan2(-ax[i], math.hypot(ay[i], az[i]))) for i in range(n)])
    r_med, p_med = _media(roll), _media(pitch)
    eixos = [_numeros(x) for x in (a.get("gyro_dps") or [])]
    eixos = [e for e in eixos if e]
    ruido = max(_desvio(e) for e in eixos) if eixos else None
    vies = max(abs(_media(e)) for e in eixos) if eixos else None
    crit = [
        criterio("erro_gravidade_ms2", abs(g - GRAVIDADE_PADRAO), p["tolerancia_g_ms2"], "<=",
                 "m/s²"),
        criterio("erro_roll_deg", abs(_angulo(r_med, p["roll_esperado_deg"])), tol, "<=", "°"),
        criterio("erro_pitch_deg", abs(_angulo(p_med, p["pitch_esperado_deg"])), tol, "<=",
                 "°"),
        criterio("eixos_roll_deg", abs(_angulo(ra, r_med)), tol, "<=", "°"),
        criterio("eixos_pitch_deg", abs(_angulo(pa, p_med)), tol, "<=", "°"),
        criterio("ruido_gyro_dps", ruido, p["ruido_gyro_max_dps"], "<=", "°/s"),
        criterio("vies_gyro_dps", vies, p["vies_gyro_max_dps"], "<=", "°/s"),
    ]
    medidas = {"gravidade_ms2": round(g, 4), "roll_deg": round(r_med, 3),
               "pitch_deg": round(p_med, 3), "roll_pela_gravidade_deg": round(ra, 3),
               "pitch_pela_gravidade_deg": round(pa, 3),
               "ruido_gyro_dps": None if ruido is None else round(ruido, 4),
               "vies_gyro_dps": None if vies is None else round(vies, 4),
               "fonte_gyro": str(a.get("fonte_gyro") or "")[:80], "leituras": n}
    return crit, medidas, None


def _parada(p: dict, a: dict) -> Calculo:
    tentativas = int(p["tentativas"])  # o que a plataforma pediu
    lat = a.get("latencias_ms") if isinstance(a.get("latencias_ms"), list) else []
    confirmadas = _numeros(lat)
    pct = 100.0 * len(confirmadas) / tentativas if tentativas else 0.0
    if len(lat) != tentativas:
        pct = 0.0  # o robô não respondeu por todas as tentativas pedidas
    p95 = percentil(confirmadas, 95) if confirmadas else None
    crit = [criterio("confirmadas_pct", pct, 100.0, ">=", "%"),
            criterio("latencia_p95_ms", p95, p["latencia_max_ms"], "<=", "ms")]
    medidas = {"tentativas": tentativas, "confirmadas": len(confirmadas),
               "latencia_p95_ms": None if p95 is None else round(p95, 1),
               "latencia_max_ms": round(max(confirmadas), 1) if confirmadas else None}
    motivo = None if tentativas >= 5 else "o portão pede pelo menos 5 tentativas"
    return crit, medidas, motivo


def _homem_morto(p: dict, a: dict) -> Calculo:
    atrasos = _numeros(a.get("atrasos_s"))
    pior = max(atrasos) if atrasos else None
    crit = [criterio("episodios", len(atrasos), p["episodios"], ">="),
            criterio("atraso_max_s", pior, p["tolerancia_s"], "<=", "s")]
    return crit, {"episodios": len(atrasos), "atraso_max_s": pior,
                  "abertos": int(a.get("abertos") or 0)}, None


def _rede(p: dict, a: dict) -> Calculo:
    pings = int(p["pings"])
    rtts = _numeros(a.get("rtts_ms"))[:pings]
    perda = 100.0 * (pings - len(rtts)) / pings
    p95 = percentil(rtts, 95) if rtts else None
    crit = [criterio("perda_pct", perda, p["perda_max_pct"], "<=", "%"),
            criterio("rtt_p95_ms", p95, p["rtt_max_ms"], "<=", "ms")]
    medidas: dict[str, Any] = {"perda_pct": round(perda, 2),
                               "rtt_p95_ms": None if p95 is None else round(p95, 1)}
    carga = int(p["carga_kb"]) * 1024
    if carga > 0:
        for sentido in ("subida", "descida"):
            n = a.get(f"{sentido}_bytes")
            dt = a.get(f"{sentido}_s")
            kbps = 0.0
            if n == carga and isinstance(dt, int | float) and dt > 0:
                kbps = 8 * carga / 1000 / dt
            medidas[f"vazao_{sentido}_kbps"] = round(kbps, 1)
            crit.append(criterio(f"vazao_{sentido}_kbps", kbps, p["vazao_min_kbps"], ">=",
                                 "kbit/s"))
    return crit, medidas, None


def _energia(p: dict, a: dict) -> Calculo:
    leituras = [x for x in (a.get("leituras") or []) if isinstance(x, dict)]
    socs = [(float(x["t"]), float(x["soc_pct"])) for x in leituras
            if isinstance(x.get("t"), int | float) and isinstance(x.get("soc_pct"), int | float)]
    autonomia = None
    if len(socs) >= 2 and socs[-1][0] > socs[0][0]:
        queda = (socs[0][1] - socs[-1][1]) / ((socs[-1][0] - socs[0][0]) / 3600)
        if queda > 0:
            autonomia = socs[0][1] / queda
    if autonomia is None:
        return [], {"autonomia_estimada_h": None}, "aguarda protocolo do BMS/MCU"
    return ([criterio("autonomia_h", autonomia, p["autonomia_min_h"], ">=", "h")],
            {"autonomia_estimada_h": round(autonomia, 2)}, "aguarda protocolo do BMS/MCU")


# ---------------------------------------------------------------------------
# Catálogo
# ---------------------------------------------------------------------------

CAMERAS_NO_PORTAO = 6
"""O Rover V3 leva de 6 a 8 OAK-D: o portão pede pelo menos 6 fotografando juntas."""
DISTANCIAS_DO_PORTAO_MM = (300.0, 500.0, 800.0)
"""Profundidade contra a trena nas três distâncias do guia (± 50 mm)."""


def _relogio(p: dict, a: dict) -> Calculo:
    """A mesma conta de ``valtexa_rover.ensaios.relogio.avalia_relogio`` (só o Rover)."""
    r = a.get("rover") if isinstance(a.get("rover"), dict) else {}
    medidas: dict[str, Any] = {"rover": {k: r.get(k) for k in ("sincronizado", "fonte",
                                                              "offset_ms", "fonte_em_uso")}}
    crit = [criterio("rover_sincronizado", r.get("sincronizado") is True, True, "==")]
    if p.get("exigir_gnss", True):
        crit.append(criterio("rover_fonte_gnss", r.get("fonte") == "gnss", True, "=="))
    off = _numeros([r.get("offset_ms")])
    crit.append(criterio("rover_offset_ms", abs(off[0]) if off else None,
                         p["offset_max_ms"], "<=", "ms"))
    atraso = _numeros([a.get("atraso_plataforma_s")])
    medidas["atraso_plataforma_s"] = atraso[0] if atraso else None
    if atraso:
        crit.append(criterio("atraso_plataforma_s", atraso[0], p["atraso_plataforma_max_s"],
                             "<=", "s"))
    motivo = None if p.get("exigir_gnss", True) else "sem exigir o GNSS não vale para o portão"
    return crit, medidas, motivo


@dataclass(frozen=True)
class Definicao:
    nome: str
    fase: int
    titulo: str
    limites: dict[str, tuple[float | None, str]]
    """parâmetro → (padrão do portão, ``max``/``min``)."""
    livres: dict[str, Any] = field(default_factory=dict)
    """Parâmetros de medida e o padrão (``None`` = obrigatório se ``obrigatorios``)."""
    obrigatorios: tuple[str, ...] = ()
    calcula: Callable[[dict, dict], Calculo] | None = None
    no_portao: bool = True
    duracao_s: Callable[[dict], float] = lambda p: 600.0
    origem: str = "rover"

    def descreve(self) -> dict[str, Any]:
        return {"nome": self.nome, "fase": self.fase, "titulo": self.titulo,
                "origem": self.origem, "no_portao": self.no_portao,
                "limites": {k: {"padrao": v, "sentido": s} for k, (v, s) in self.limites.items()},
                "parametros": self.livres, "obrigatorios": list(self.obrigatorios)}


CATALOGO: dict[str, Definicao] = {d.nome: d for d in (
    Definicao("calor", 0, "Calor: inferência contínua sem perder vazão",
              {"perda_max_pct": (10.0, MAX), "queda_clock_pct": (20.0, MAX),
               "temp_max_c": (None, MAX)},
              {"duracao_min": 120.0, "janela_s": 60.0, "amostra_s": 1.0}, calcula=_calor,
              duracao_s=lambda p: float(p.get("duracao_min", 120)) * 60),
    Definicao("cameras", 0, "Câmeras simultâneas: perda, deriva e sincronia com o GNSS",
              {"perda_max_pct": (0.0, MAX), "deriva_max_ms": (100.0, MAX),
               "gnss_max_ms": (200.0, MAX)},
              {"cameras": None, "duracao_s": 60.0, "fps": 2.0}, calcula=_cameras,
              duracao_s=lambda p: float(p.get("duracao_s", 60))),
    Definicao("profundidade", 0, "Profundidade contra a trena (0,3 / 0,5 / 0,8 m)",
              {"tolerancia_mm": (20.0, MAX), "preenchimento_min": (0.5, MIN)},
              {"camera_id": None, "distancia_real_mm": None, "roi": [0.4, 0.4, 0.2, 0.2],
               "amostras": 10, "intervalo_s": 0.2},
              obrigatorios=("camera_id", "distancia_real_mm"), calcula=_profundidade,
              duracao_s=lambda p: float(p.get("amostras", 10)) * (
                  float(p.get("intervalo_s", 0.2)) + 1)),
    Definicao("gnss", 0, "GNSS RTK: tempo até fix, precisão, perda e retomada",
              {"tempo_fix_max_s": (120.0, MAX), "cep95_max_cm": (5.0, MAX),
               "vies_max_cm": (5.0, MAX), "retomada_max_s": (60.0, MAX)},
              {"duracao_s": 60.0, "taxa_hz": 5.0, "lat_ref": None, "lon_ref": None,
               "perda_s": 0.0}, calcula=_gnss,
              duracao_s=lambda p: float(p.get("tempo_fix_max_s", 120)) + float(
                  p.get("duracao_s", 60)) + float(p.get("perda_s", 0))),
    Definicao("imu", 0, "IMU parada: gravidade, giroscópio e eixos",
              {"tolerancia_g_ms2": (0.1, MAX), "tolerancia_inclinacao_deg": (1.5, MAX),
               "ruido_gyro_max_dps": (0.2, MAX), "vies_gyro_max_dps": (0.5, MAX)},
              {"duracao_s": 30.0, "taxa_hz": 50.0, "roll_esperado_deg": 0.0,
               "pitch_esperado_deg": 0.0}, calcula=_imu,
              duracao_s=lambda p: float(p.get("duracao_s", 30))),
    Definicao("rede", 0, "Rede até a plataforma: RTT, perda e vazão",
              {"rtt_max_ms": (500.0, MAX), "perda_max_pct": (5.0, MAX),
               "vazao_min_kbps": (256.0, MIN)},
              {"pings": 20, "intervalo_s": 0.5, "carga_kb": 256}, calcula=_rede,
              duracao_s=lambda p: float(p.get("pings", 20)) * (
                  float(p.get("intervalo_s", 0.5)) + 5) + 120),
    Definicao("energia", 0, "Bateria e energia (aguarda protocolo do BMS/MCU)",
              {"autonomia_min_h": (8.0, MIN)}, {"duracao_min": 10.0, "amostra_s": 5.0},
              calcula=_energia, no_portao=False,
              duracao_s=lambda p: float(p.get("duracao_min", 10)) * 60),
    Definicao("parada", 1, "Latência do PARAR até a navegação confirmar",
              {"latencia_max_ms": (500.0, MAX)},
              {"tentativas": 5, "intervalo_s": 2.0, "timeout_s": 3.0,
               "exigir_movimento": False, "v_min_ms": 0.1, "espera_movimento_s": 60.0},
              calcula=_parada,
              duracao_s=lambda p: float(p.get("tentativas", 5)) * (
                  float(p.get("intervalo_s", 2)) + float(p.get("timeout_s", 3)) + (
                      float(p.get("espera_movimento_s", 60))
                      if p.get("exigir_movimento") else 0))),
    Definicao("homem_morto", 1, "Homem-morto: o teleop.json zera depois do valid_until",
              {"tolerancia_s": (1.0, MAX)}, {"episodios": 1, "timeout_s": 120.0},
              calcula=_homem_morto, duracao_s=lambda p: float(p.get("timeout_s", 120))),
    Definicao("relogio", 0, "Relógio: chrony com GNSS no Rover",
              {"offset_max_ms": (10.0, MAX), "atraso_plataforma_max_s": (1.0, MAX)},
              {"exigir_gnss": True}, calcula=_relogio, duracao_s=lambda p: 30.0),
    Definicao("validacao_agronomica", 5, "Validação agronômica: Rover contra agrônomo",
              {"sensibilidade_min": (0.80, MIN), "alarme_falso_max": (0.15, MAX),
               "concordancia_min": (0.80, MIN), "doentes_min": (10.0, MIN),
               "sadias_min": (10.0, MIN)},
              {"field_id": None, "mission_id": None, "usar_ic": False},
              obrigatorios=("field_id", "mission_id"), origem="validacao_campo"),
)}

FASES = {
    0: "Bancada, sem andar", 1: "Segurança",
    2: "Mobilidade e navegação no cafezal",
    3: "Imagem e IA do café", 4: "Missão piloto de ponta a ponta",
    5: "Validação agronômica",
}


def catalogo() -> list[dict[str, Any]]:
    return [d.descreve() for d in CATALOGO.values()]


def valida_pedido(nome: str, params: dict | None) -> dict[str, Any]:
    """Os parâmetros completos que vão no comando assinado (padrões preenchidos).

    Limite mais frouxo que o do portão → :class:`EnsaioInvalidoError`."""
    d = CATALOGO.get(nome)
    if d is None or d.origem != "rover":
        rodam = [n for n, x in CATALOGO.items() if x.origem == "rover"]
        raise EnsaioInvalidoError(f"Ensaio {nome!r}: use {', '.join(rodam)}.")
    return _completa(d, params)


def _completa(d: Definicao, params: dict | None) -> dict[str, Any]:
    params = dict(params or {})
    estranhos = sorted(set(params) - set(d.limites) - set(d.livres))
    if estranhos:
        raise EnsaioInvalidoError(f"{d.nome}: parâmetros desconhecidos {estranhos}.")
    saida = {**d.livres}
    for nome, (padrao, sentido) in d.limites.items():
        valor = params.get(nome, padrao)
        if valor is not None:
            if isinstance(valor, bool) or not isinstance(valor, int | float) \
                    or not math.isfinite(valor):
                raise EnsaioInvalidoError(f"{d.nome}: {nome} tem de ser número.")
            if padrao is not None and ((sentido == MAX and valor > padrao)
                                       or (sentido == MIN and valor < padrao)):
                raise EnsaioInvalidoError(
                    f"{d.nome}: {nome} = {valor} é mais frouxo que o limite do portão "
                    f"({padrao}); dá para apertar, não afrouxar.")
        saida[nome] = valor
    for nome in d.livres:
        if nome in params:
            saida[nome] = params[nome]
    faltando = [n for n in d.obrigatorios if saida.get(n) is None]
    if faltando:
        raise EnsaioInvalidoError(f"{d.nome}: informe {', '.join(faltando)}.")
    return saida


def prazo_de_execucao(nome: str, params: dict) -> timedelta:
    """Até quando um ensaio em execução pode ficar sem notícia antes de virar falha."""
    d = CATALOGO.get(nome)
    estimado = d.duracao_s(params) if d is not None else 600.0
    return timedelta(seconds=estimado + 15 * 60)


# ---------------------------------------------------------------------------
# Registro do laudo e veredito
# ---------------------------------------------------------------------------


def _sem_amostras(laudo: dict) -> dict:
    return {k: v for k, v in laudo.items() if k != "amostras"}


def registra_do_robo(session: Session, comando: DeviceCommand, *, ok: bool,
                     laudo: dict | None, erro: str | None) -> EnsaioResultado:
    """O laudo que o robô mandou vira resultado — com o veredito recalculado aqui."""
    nome = str((comando.params or {}).get("ensaio") or "")
    d = CATALOGO.get(nome)
    params = dict((comando.params or {}).get("params") or {})
    laudo = laudo if isinstance(laudo, dict) else {}
    status_robo = laudo.get("status")
    criterios: list[dict] = []
    medidas: dict[str, Any] = {}
    motivo: str | None = None
    if not ok or d is None or d.calcula is None:
        status = "erro"
        motivo = erro or laudo.get("erro") or "ensaio sem laudo"
    elif status_robo in ("cancelado", "erro"):
        status = status_robo
        motivo = laudo.get("erro")
    else:
        amostras = laudo.get("amostras") if isinstance(laudo.get("amostras"), dict) else {}
        criterios, medidas, motivo = d.calcula(params, amostras)
        if not criterios:
            status = "nao_avaliado"
        else:
            status = "aprovado" if all(c["ok"] for c in criterios) else "reprovado"
    aprovado = {"aprovado": True, "reprovado": False}.get(status)
    simulado = bool(laudo.get("simulado", True))  # sem a marca, não confia que é real
    robo_aprovou = laudo.get("aprovado")
    resultado = EnsaioResultado(
        tenant_id=comando.tenant_id, device_id=comando.device_id, command_id=comando.id,
        ensaio=nome or "desconhecido", fase=d.fase if d else -1, origem="rover",
        status=status, aprovado=aprovado, params=params, criterios=criterios,
        medidas=medidas, laudo_robo=_sem_amostras(laudo) if laudo else None,
        divergente=(aprovado is not None and isinstance(robo_aprovou, bool)
                    and robo_aprovou != aprovado),
        simulado=simulado,
        vale_portao=bool(status in ("aprovado", "reprovado") and motivo is None
                         and d is not None and d.no_portao),
        observacao=motivo, created_by=comando.created_by)
    session.add(resultado)
    session.flush()
    _confere_regressao(session, resultado)
    return resultado


def registra_validacao_agronomica(session: Session, device: Device, relatorio: dict,
                                  params: dict | None, *, user_id: str | None,
                                  simulado: bool = False) -> EnsaioResultado:
    """FASE 5 a partir do relatório Rover contra agrônomo (validação de campo)."""
    d = CATALOGO["validacao_agronomica"]
    p = _completa(d, {**(params or {}), "field_id": relatorio.get("field_id"),
                      "mission_id": relatorio.get("mission_id")})
    doentes, achadas = int(relatorio.get("diseased") or 0), int(relatorio.get("detected") or 0)
    sadias, alarmes = int(relatorio.get("healthy") or 0), int(
        relatorio.get("false_alarms") or 0)
    n = doentes + sadias
    sens = achadas / doentes if doentes else None
    fa = alarmes / sadias if sadias else None
    conc = (achadas + sadias - alarmes) / n if n else None
    ic_sens, ic_fa, ic_conc = wilson(achadas, doentes), wilson(alarmes, sadias), wilson(
        achadas + sadias - alarmes, n)
    usar_ic = bool(p.get("usar_ic"))
    valor_sens = ic_sens[0] if (usar_ic and ic_sens) else sens
    valor_fa = ic_fa[1] if (usar_ic and ic_fa) else fa
    criterios = [
        criterio("sensibilidade", valor_sens, p["sensibilidade_min"], ">="),
        criterio("alarme_falso", valor_fa, p["alarme_falso_max"], "<="),
        criterio("concordancia", conc, p["concordancia_min"], ">="),
        criterio("doentes_rotuladas", doentes, p["doentes_min"], ">="),
        criterio("sadias_rotuladas", sadias, p["sadias_min"], ">="),
    ]
    status = "aprovado" if all(c["ok"] for c in criterios) else "reprovado"
    medidas = {
        "plantas_rotuladas": n, "doentes": doentes, "achadas": achadas,
        "doenca_certa": int(relatorio.get("right_disease") or 0), "sadias": sadias,
        "alarmes_falsos": alarmes,
        "sensibilidade": None if sens is None else round(sens, 4), "sensibilidade_ic95": ic_sens,
        "alarme_falso": None if fa is None else round(fa, 4), "alarme_falso_ic95": ic_fa,
        "concordancia": None if conc is None else round(conc, 4), "concordancia_ic95": ic_conc,
        "criterio_pelo_ic": usar_ic, "por_doenca": relatorio.get("by_disease") or {},
    }
    resultado = EnsaioResultado(
        tenant_id=device.tenant_id, device_id=device.id, command_id=None,
        ensaio=d.nome, fase=d.fase, origem=d.origem, status=status,
        aprovado=status == "aprovado", params=p, criterios=criterios, medidas=medidas,
        laudo_robo=None, divergente=False, simulado=simulado, vale_portao=True,
        observacao=relatorio.get("note"), created_by=user_id)
    session.add(resultado)
    session.flush()
    _confere_regressao(session, resultado)
    return resultado


def _balde(r: EnsaioResultado) -> str | None:
    """Resultados comparáveis entre si: profundidade só com a mesma distância."""
    if r.ensaio != "profundidade":
        return None
    real = (r.params or {}).get("distancia_real_mm")
    if not isinstance(real, int | float):
        return None
    for alvo in DISTANCIAS_DO_PORTAO_MM:
        if abs(real - alvo) <= 50:
            return f"{alvo:.0f}"
    return f"{real:.0f}"


def _anteriores(session: Session, device_id: str, ensaio: str) -> list[EnsaioResultado]:
    return list(session.scalars(
        select(EnsaioResultado).where(EnsaioResultado.device_id == device_id,
                                      EnsaioResultado.ensaio == ensaio,
                                      EnsaioResultado.status.in_(("aprovado", "reprovado")))
        .order_by(EnsaioResultado.created_at.desc(), EnsaioResultado.id.desc())))


def _confere_regressao(session: Session, novo: EnsaioResultado) -> None:
    if novo.status != "reprovado":
        return
    balde = _balde(novo)
    anterior = next((r for r in _anteriores(session, novo.device_id, novo.ensaio)
                     if r.id != novo.id and _balde(r) == balde
                     and r.simulado == novo.simulado), None)
    if anterior is None or anterior.status != "aprovado":
        return
    falhos = [c["nome"] for c in novo.criterios if not c.get("ok")]
    events.publish(session, events.ENSAIO_REGRESSAO, tenant_id=novo.tenant_id,
                   subject_type=SubjectType.DEVICE, subject_id=novo.device_id,
                   payload={"ensaio": novo.ensaio, "resultado_id": novo.id,
                            "anterior_id": anterior.id, "criterios": falhos,
                            "simulado": novo.simulado, "balde": balde})


# ---------------------------------------------------------------------------
# Leitura e portões
# ---------------------------------------------------------------------------


def como_dict(r: EnsaioResultado, *, com_laudo: bool = False) -> dict[str, Any]:
    saida = {"id": r.id, "ensaio": r.ensaio, "fase": r.fase, "origem": r.origem,
             "status": r.status, "aprovado": r.aprovado, "params": r.params,
             "criterios": r.criterios, "medidas": r.medidas, "divergente": r.divergente,
             "simulado": r.simulado, "vale_portao": r.vale_portao,
             "observacao": r.observacao, "command_id": r.command_id,
             "created_at": r.created_at.isoformat() if r.created_at else None}
    if com_laudo:
        saida["laudo_robo"] = r.laudo_robo
    return saida


def historico(session: Session, device: Device, limite: int = 200) -> list[dict[str, Any]]:
    return [como_dict(r) for r in session.scalars(
        select(EnsaioResultado).where(EnsaioResultado.device_id == device.id)
        .order_by(EnsaioResultado.created_at.desc(), EnsaioResultado.id.desc()).limit(limite))]


def _situacao(r: EnsaioResultado | None, aceitar_simulado: bool) -> str:
    if r is None:
        return "faltando"
    if r.simulado and not aceitar_simulado:
        return "so_simulado"
    return "aprovado" if r.aprovado else "reprovado"


def portoes(session: Session, device: Device, *, aceitar_simulado: bool = False
            ) -> list[dict[str, Any]]:
    """Cada fase: aprovada só com **todo** ensaio obrigatório aprovado no último resultado
    que vale para o portão. Faltando um, a fase não passa — e a lista diz qual."""
    todos = list(session.scalars(
        select(EnsaioResultado).where(EnsaioResultado.device_id == device.id,
                                      EnsaioResultado.vale_portao.is_(True))
        .order_by(EnsaioResultado.created_at.desc(), EnsaioResultado.id.desc())))
    reais = [r for r in todos if not r.simulado]

    def ultimo(condicao) -> EnsaioResultado | None:
        # O último que conta; sem nenhum real, o simulado aparece como "só simulado".
        r = next((x for x in (todos if aceitar_simulado else reais) if condicao(x)), None)
        return r or next((x for x in todos if condicao(x)), None)

    saida = []
    for fase, titulo in FASES.items():
        defs = [d for d in CATALOGO.values() if d.fase == fase and d.no_portao]
        itens = []
        for d in defs:
            if d.nome == "profundidade":
                for alvo in DISTANCIAS_DO_PORTAO_MM:
                    r = ultimo(lambda x, d=d, alvo=alvo: x.ensaio == d.nome
                               and _balde(x) == f"{alvo:.0f}")
                    itens.append({"ensaio": d.nome, "rotulo": f"{d.nome} {alvo / 1000:.1f} m",
                                  "situacao": _situacao(r, aceitar_simulado),
                                  "resultado_id": r and r.id,
                                  "quando": r and r.created_at.isoformat()})
                continue
            r = ultimo(lambda x, d=d: x.ensaio == d.nome)
            itens.append({"ensaio": d.nome, "rotulo": d.nome,
                          "situacao": _situacao(r, aceitar_simulado),
                          "resultado_id": r and r.id, "quando": r and r.created_at.isoformat()})
        informativos = [d.nome for d in CATALOGO.values() if d.fase == fase and not d.no_portao]
        if not defs:
            saida.append({"fase": fase, "titulo": titulo, "automatico": False,
                          "aprovado": None, "itens": [], "informativos": informativos,
                          "nota": "Sem ensaio automático: siga o guia de validação."})
            continue
        faltam = [i["rotulo"] for i in itens if i["situacao"] != "aprovado"]
        saida.append({"fase": fase, "titulo": titulo, "automatico": True,
                      "aprovado": not faltam, "itens": itens, "faltam": faltam,
                      "informativos": informativos, "aceitar_simulado": aceitar_simulado})
    return saida
