"""Retirado de valtexa/services/ensaios.py em 20/10/2026: a FASE ENLACE (rádio da fazenda).

As contas que a plataforma refazia dos ensaios ``enlace_*`` do Rover, a versão antiga do
``relogio`` (Rover + base) e as definições do catálogo. O ``relogio`` continua no produto,
na FASE 0, só com o lado do Rover."""

FASE_ENLACE = 6
"""A FASE ENLACE (Parte 13) tem o número 6 no banco, mas vem logo depois da Segurança: o
enlace da fazenda precisa estar provado antes de o Rover trabalhar no cafezal."""

# ---------------------------------------------------------------------------
# FASE ENLACE (Parte 13): as contas de ``rover/valtexa_rover/ensaios/enlace.py``, refeitas
# ---------------------------------------------------------------------------

_SO_MANUAL = ("feito por software ({modo}): serve de regressão, não vale para o portão — "
              "no portão, o técnico {acao} (modo manual)")


def _enlace_rssi(p: dict, a: dict) -> Calculo:
    por: dict[str, dict[str, list]] = {}
    for x in a.get("leituras") if isinstance(a.get("leituras"), list) else []:
        if not isinstance(x, dict):
            continue
        d = por.setdefault(str(x.get("enlace")), {"rssi": [], "snr": [], "perda": [],
                                                  "rtt": [], "vivo": []})
        d["vivo"].append(x.get("estado") != "morto")
        for k, c in (("rssi", "rssi_dbm"), ("snr", "snr_db"), ("perda", "perda"),
                     ("rtt", "rtt_ms")):
            d[k] += _numeros([x.get(c)])
    medidas: dict[str, Any] = {"ponto": a.get("ponto"), "enlaces": {}}
    melhor, nota = None, None
    for enlace, d in por.items():
        m = {"rssi_p50_dbm": percentil(d["rssi"], 50) if d["rssi"] else None,
             "snr_p50_db": percentil(d["snr"], 50) if d["snr"] else None,
             "perda_media_pct": 100 * _media(d["perda"]) if d["perda"] else
             (100.0 if not any(d["vivo"]) else None),
             "rtt_p95_ms": percentil(d["rtt"], 95) if d["rtt"] else None,
             "vivo_pct": 100 * sum(d["vivo"]) / len(d["vivo"])}
        medidas["enlaces"][enlace] = m
        chave = (m["vivo_pct"], m["rssi_p50_dbm"] if m["rssi_p50_dbm"] is not None else -999,
                 -(m["perda_media_pct"] or 0))
        if nota is None or chave > nota:
            melhor, nota = enlace, chave
    pos = a.get("posicao") if isinstance(a.get("posicao"), dict) else {}
    crit = [criterio("posicao_rtk", pos.get("fix") in ("fixed", "float"), True, "==")]
    if melhor is None:
        return [*crit, criterio("enlace_com_a_base", None, True, "==")], medidas, None
    m = medidas["enlaces"][melhor]
    medidas["melhor_enlace"] = melhor
    crit += [criterio(f"{melhor}_perda_media_pct", m["perda_media_pct"], p["perda_max_pct"],
                      "<=", "%"),
             criterio(f"{melhor}_rtt_p95_ms", m["rtt_p95_ms"], p["rtt_p95_max_ms"], "<=", "ms")]
    motivo = None
    if m["rssi_p50_dbm"] is not None:
        crit.append(criterio(f"{melhor}_rssi_p50_dbm", m["rssi_p50_dbm"], p["rssi_min_dbm"],
                             ">=", "dBm"))
    else:
        motivo = "o rádio não expõe RSSI: o portão pede RSSI/SNR (adaptador SNMP/HTTP)"
    if m["snr_p50_db"] is not None:
        crit.append(criterio(f"{melhor}_snr_p50_db", m["snr_p50_db"], p["snr_min_db"], ">=",
                             "dB"))
    return crit, medidas, motivo


def _enlace_latencia(p: dict, a: dict) -> Calculo:
    n = int(p["ecos"])
    rtts = _numeros(a.get("rtts_ms"))[:n]
    perda = 100.0 * (n - len(rtts)) / n
    p99 = percentil(rtts, 99) if rtts else None
    medidas = {"p50_ms": round(percentil(rtts, 50), 1) if rtts else None,
               "p95_ms": round(percentil(rtts, 95), 1) if rtts else None,
               "p99_ms": None if p99 is None else round(p99, 1), "perda_pct": round(perda, 2)}
    motivo = None if n >= 200 else "o portão pede 200 ecos ou mais"
    return [criterio("p99_ms", p99, p["p99_max_ms"], "<=", "ms"),
            criterio("perda_pct", perda, p["perda_max_pct"], "<=", "%")], medidas, motivo


def _enlace_troca(p: dict, a: dict) -> Calculo:
    t_s = a.get("t_silencio")
    if not isinstance(t_s, int | float):
        return [], {}, "o rádio não calou: nada medido"
    alvo = a.get("enlace")
    urx = a.get("t_ultimo_rx")
    inicio = min(float(urx), float(t_s)) if isinstance(urx, int | float) else float(t_s)
    troca = None
    for item in a.get("melhores") if isinstance(a.get("melhores"), list) else []:
        if isinstance(item, list) and len(item) == 2 and isinstance(item[0], int | float) \
                and item[0] >= t_s and item[1] not in (alvo, None):
            troca = item[0] - inicio
            break
    fim = float(t_s) + float(a.get("silencio_s") or p["silencio_s"])
    pior, ini = 0.0, None
    for item in a.get("ecos") if isinstance(a.get("ecos"), list) else []:
        if not (isinstance(item, list) and len(item) == 2 and isinstance(item[0], int | float)):
            continue
        t, r = item
        if t < inicio or t > fim:
            continue
        if r is None and ini is None:
            ini = t
        elif r is not None and ini is not None:
            pior, ini = max(pior, t - ini), None
    if ini is not None:
        pior = max(pior, fim - ini)
    medidas = {"enlace_silenciado": alvo, "troca_s": None if troca is None else round(troca, 2),
               "interrupcao_p1_s": round(pior, 2)}
    motivo = None if p.get("modo") == "manual" else _SO_MANUAL.format(
        modo=p.get("modo"), acao="desliga o rádio")
    return [criterio("troca_s", troca, p["troca_max_s"], "<=", "s"),
            criterio("interrupcao_p1_s", pior, p["interrupcao_p1_max_s"], "<=", "s")
            ], medidas, motivo


def _sondas(a: dict) -> list[tuple[float, float | None]]:
    saida = []
    for item in a.get("sondas") if isinstance(a.get("sondas"), list) else []:
        if isinstance(item, list) and len(item) == 2 and isinstance(item[0], int | float):
            ok = item[1] if isinstance(item[1], int | float) else None
            saida.append((float(item[0]), ok))
    return saida


def _enlace_starlink(p: dict, a: dict) -> Calculo:
    sondas = _sondas(a)
    perdidas = sum(1 for _, ok in sondas if ok is None)
    entradas = [ok for _, ok in sondas if ok is not None]
    fim = float(a.get("t_fim_queda") or 0)
    rec = max(0.0, max(entradas) - fim) if entradas else None
    medidas = {"sondas": len(sondas), "perdidas": perdidas,
               "recuperacao_s": None if rec is None else round(rec, 2),
               "nuvem_voltou_s": a.get("t_volta_nuvem")}
    motivo = None if p.get("modo") == "manual" else _SO_MANUAL.format(
        modo=p.get("modo"), acao="tira o cabo da Starlink")
    return [criterio("sondas_perdidas", perdidas, 0, "<="),
            criterio("sondas_feitas", len(sondas), 1, ">="),
            criterio("recuperacao_s", rec, p["recuperacao_max_s"], "<=", "s")], medidas, motivo


def _enlace_energia_base(p: dict, a: dict) -> Calculo:
    caiu, voltou = a.get("t_caiu"), a.get("t_voltou")
    if not isinstance(caiu, int | float):
        return [], {}, "a base não caiu dentro da janela"
    volta = voltou - caiu if isinstance(voltou, int | float) else None
    sondas = _sondas(a)
    perdidas = sum(1 for _, ok in sondas if ok is None)
    entradas = [ok for _, ok in sondas if ok is not None]
    rec = None if volta is None or not entradas else max(0.0, max(entradas) - voltou)
    medidas = {"sem_enlace_s": None if volta is None else round(volta, 2),
               "sondas": len(sondas), "perdidas": perdidas,
               "recuperacao_s": None if rec is None else round(rec, 2)}
    crit = [criterio("sem_enlace_s", volta, p["volta_max_s"], "<=", "s"),
            criterio("sondas_perdidas", perdidas, 0, "<=")]
    if sondas:
        crit.append(criterio("recuperacao_s", rec if rec is not None else (
            0.0 if not entradas and not perdidas else None), p["recuperacao_max_s"], "<=",
            "s"))
    motivo = None if p.get("modo") == "manual" else _SO_MANUAL.format(
        modo=p.get("modo"), acao="corta a energia da base")
    return crit, medidas, motivo


def _iso_s(v: Any) -> float | None:
    from datetime import datetime

    try:
        return datetime.fromisoformat(str(v)).timestamp() if v else None
    except ValueError:
        return None


def _enlace_travessia(p: dict, a: dict) -> Calculo:
    trs = [t for t in (a.get("travessias") if isinstance(a.get("travessias"), list) else [])
           if isinstance(t, dict)]
    if not trs:
        return [], {}, "nenhuma travessia registrada"
    antecedencias, syncs, fora = [], [], 0
    for t in trs:
        real = t.get("real") if isinstance(t.get("real"), dict) else {}
        prev = t.get("prevista") if isinstance(t.get("prevista"), dict) else {}
        av, ent = _iso_s(t.get("avisada_em")), _iso_s(real.get("entrou"))
        if av is not None and ent is not None:
            antecedencias.append(ent - av)
        sy = t.get("sincronizado_s_depois_de_sair")
        syncs.append(float(sy) if isinstance(sy, int | float) else None)
        pd, rd = prev.get("duracao_s"), real.get("duracao_s")
        if isinstance(pd, int | float) and isinstance(rd, int | float) and \
                rd > pd * float(p["folga"]) + 15:
            fora += 1
    pior = None if any(x is None for x in syncs) else max(syncs)
    medidas = {"travessias": len(trs),
               "antecedencia_min_s": round(min(antecedencias), 1) if antecedencias else None,
               "sincronizacao_max_s": pior, "fora_do_previsto": fora}
    return [criterio("antecedencia_min_s", min(antecedencias) if antecedencias else None,
                     p["antecedencia_min_s"], ">=", "s"),
            criterio("sincronizacao_max_s", pior, p["sincronizacao_max_s"], "<=", "s"),
            criterio("fora_do_previsto", fora, 0, "<=")], medidas, None


def _relogio(p: dict, a: dict) -> Calculo:
    crit, medidas = [], {}
    for lado in ("rover", "base"):
        r = a.get(lado) if isinstance(a.get(lado), dict) else {}
        medidas[lado] = {k: r.get(k) for k in ("sincronizado", "fonte", "offset_ms",
                                               "fonte_em_uso")}
        crit.append(criterio(f"{lado}_sincronizado", r.get("sincronizado") is True, True, "=="))
        if p.get("exigir_gnss", True):
            crit.append(criterio(f"{lado}_fonte_gnss", r.get("fonte") == "gnss", True, "=="))
        off = _numeros([r.get("offset_ms")])
        crit.append(criterio(f"{lado}_offset_ms", abs(off[0]) if off else None,
                             p["offset_max_ms"], "<=", "ms"))
    atraso = _numeros([a.get("atraso_plataforma_s")])
    medidas["atraso_plataforma_s"] = atraso[0] if atraso else None
    if atraso:
        crit.append(criterio("atraso_plataforma_s", atraso[0], p["atraso_plataforma_max_s"],
                             "<=", "s"))
    motivo = None if p.get("exigir_gnss", True) else "sem exigir o GNSS não vale para o portão"
    return crit, medidas, motivo



# --- catálogo ---
    Definicao("enlace_rssi", FASE_ENLACE, "Enlace num ponto: RSSI/SNR, RTT e perda (RTK)",
              {"rssi_min_dbm": (-85.0, MIN), "snr_min_db": (15.0, MIN),
               "perda_max_pct": (10.0, MAX), "rtt_p95_max_ms": (300.0, MAX)},
              {"ponto": None, "duracao_s": 30.0, "amostra_s": 1.0}, obrigatorios=("ponto",),
              calcula=_enlace_rssi, duracao_s=lambda p: float(p.get("duracao_s", 30)) + 10),
    Definicao("enlace_latencia", FASE_ENLACE, "Latência de P1 pelo rádio: p99 e perda",
              {"p99_max_ms": (500.0, MAX), "perda_max_pct": (1.0, MAX)},
              {"ecos": 200, "intervalo_s": 0.25, "timeout_s": 2.0}, calcula=_enlace_latencia,
              duracao_s=lambda p: float(p.get("ecos", 200)) * (
                  float(p.get("intervalo_s", 0.25)) + float(p.get("timeout_s", 2)))),
    Definicao("enlace_troca", FASE_ENLACE, "Troca de enlace: um rádio morre",
              {"troca_max_s": (5.0, MAX), "interrupcao_p1_max_s": (2.0, MAX)},
              {"enlace": None, "modo": "manual", "silencio_s": 20.0, "janela_manual_s": 120.0,
               "eco_s": 0.2}, calcula=_enlace_troca,
              duracao_s=lambda p: float(p.get("janela_manual_s", 120)) + float(
                  p.get("silencio_s", 20)) + 30),
    Definicao("enlace_starlink", FASE_ENLACE, "Starlink cai e volta: nada se perde",
              {"recuperacao_max_s": (60.0, MAX)},
              {"modo": "manual", "queda_s": 60.0, "sondas_s": 2.0}, calcula=_enlace_starlink,
              duracao_s=lambda p: float(p.get("queda_s", 60)) + 4 * float(
                  p.get("recuperacao_max_s", 60)) + 60),
    Definicao("enlace_energia_base", FASE_ENLACE, "Queda de energia da base: o enlace volta",
              {"volta_max_s": (120.0, MAX), "recuperacao_max_s": (60.0, MAX)},
              {"modo": "manual", "janela_s": 300.0, "eco_s": 1.0, "sondas_s": 2.0},
              calcula=_enlace_energia_base,
              duracao_s=lambda p: float(p.get("janela_s", 300)) + 60),
    Definicao("enlace_travessia", FASE_ENLACE, "Travessia de zona morta mapeada",
              {"antecedencia_min_s": (10.0, MIN), "sincronizacao_max_s": (60.0, MAX),
               "folga": (1.5, MAX)},
              {"ultimas": 5}, calcula=_enlace_travessia, duracao_s=lambda p: 30.0),
    Definicao("relogio", FASE_ENLACE, "Relógio: chrony com GNSS no Rover e na base",
              {"offset_max_ms": (10.0, MAX), "atraso_plataforma_max_s": (1.0, MAX)},
              {"exigir_gnss": True}, calcula=_relogio, duracao_s=lambda p: 30.0),
