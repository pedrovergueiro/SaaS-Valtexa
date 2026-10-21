"""Retirado de valtexa/services/alertas.py em 20/10/2026 (rádio/base arquivados).

Os avaliadores e as 4 entradas de REGRAS (base_sem_contato, enlace_degradado, fila_base,
repetidora_bateria), e a exceção da base em _offline. Linhas antigas desses tipos em
``alert_rule`` ficam no banco sem efeito: o worker só avalia o que está em REGRAS."""

# --- em _offline(): ---
        if d.model is not None and d.model.kind == DeviceKind.GATEWAY:
            return None  # a base tem a regra dela (base_sem_contato), com o prazo dela

# ---------------------------------------------------------------------------
# Avaliadores — base da fazenda (services/estacao_base.py)
# ---------------------------------------------------------------------------


def _por_base(session: Session, regra: RegraDef, ctx: dict,
              medir: Callable[[Device, dict, Efetiva, datetime], tuple[float | None, str] | None],
              agora: datetime) -> Iterator[Violacao]:
    """Para cada base ativa (``gateway``), com o retrato que ela mandou."""
    from valtexa.services import estacao_base

    if "bases" not in ctx:
        ctx["bases"] = estacao_base.bases(session)
    for d in ctx["bases"]:
        efetiva = efetiva_para(session, regra.kind, d.tenant_id, ctx)
        if efetiva is None:
            continue
        medida = medir(d, estacao_base.retrato(d), efetiva, agora)
        if medida is not None:
            valor, mensagem = medida
            yield Violacao("device", d.id, _rotulo(d), d.tenant_id, valor, mensagem)


def _base_sem_contato(session, regra, _e, agora, ctx):
    """A base só fala com a nuvem pela Starlink: calada é internet fora ou base sem energia."""
    def medir(d: Device, _r: dict, e: Efetiva, agora: datetime):
        visto = as_utc(d.last_seen_at)
        if visto is None:
            return None
        minutos = (agora - visto).total_seconds() / 60
        if minutos < (e.threshold or 0):
            return None
        return round(minutos, 1), (f"Base sem contato há {minutos:.0f} min: Starlink fora ou "
                                   "base sem energia. Os Rovers guardam tudo na fila deles.")
    return _por_base(session, regra, ctx, medir, agora)


def _enlace_degradado(session, regra, _e, agora, ctx):
    def medir(_d: Device, r: dict, e: Efetiva, _agora):
        ruins = []
        for rover in r.get("rovers") or []:
            if rover.get("em_travessia"):
                continue  # zona morta mapeada: o Rover avisou e sincroniza na volta
            if not rover.get("vivo"):
                ruins.append(f"{rover['serial']} sem nenhum rádio")
                continue
            vivos = [x for x in rover.get("enlaces") or [] if x.get("estado") != "morto"]
            perda = min((x.get("perda") or 0.0 for x in vivos), default=1.0)
            if perda >= (e.threshold or 1.0):
                ruins.append(f"{rover['serial']} com {perda:.0%} de perda no melhor rádio")
        if not ruins:
            return None
        return float(len(ruins)), "Enlace com o Rover: " + "; ".join(ruins) + "."
    return _por_base(session, regra, ctx, medir, agora)


def _fila_da_base(session, regra, _e, agora, ctx):
    def medir(_d: Device, r: dict, e: Efetiva, _agora):
        fila = r.get("uplink") or {}
        urgentes = sum(fila.get(f"P{i}") or 0 for i in (0, 1, 2, 3))
        if urgentes < (e.threshold or 0):
            return None
        return float(urgentes), (f"{urgentes} pedido(s) de comando, telemetria ou evento "
                                 "esperando a Starlink na base.")
    return _por_base(session, regra, ctx, medir, agora)


def _repetidora_bateria(session, regra, _e, agora, ctx):
    def medir(_d: Device, r: dict, e: Efetiva, _agora):
        fracas = [x for x in r.get("repetidoras") or []
                  if x.get("bateria_pct") is not None and x["bateria_pct"] < (e.threshold or 0)]
        mortas = [x for x in r.get("repetidoras") or [] if not x.get("vivo")]
        if not fracas and not mortas:
            return None
        partes = [f"{x['nome']} com {x['bateria_pct']:.0f}% de bateria" for x in fracas]
        partes += [f"{x['nome']} sem responder" for x in mortas]
        return float(len(partes)), "Repetidora: " + "; ".join(partes) + "."
    return _por_base(session, regra, ctx, medir, agora)



# --- entradas de REGRAS: ---
        RegraDef("base_sem_contato", ROBO, "Base da fazenda sem contato",
                 "A base não fala com a plataforma há mais de X minutos (Starlink fora ou "
                 "base sem energia).", 5.0, "min", None, "critico", _base_sem_contato),
        RegraDef("enlace_degradado", ROBO, "Enlace com o Rover degradado",
                 "Rover sem nenhum rádio com a base, ou perda acima de Y no melhor rádio "
                 "(fora de zona morta mapeada).", 0.3, "fração", None, "aviso",
                 _enlace_degradado),
        RegraDef("fila_base", ROBO, "Fila da base crescendo",
                 "Mais de X pedidos P0-P3 esperando a Starlink na base.", 50.0, "pedidos",
                 None, "aviso", _fila_da_base),
        RegraDef("repetidora_bateria", ROBO, "Repetidora com bateria fraca",
                 "Repetidora da malha abaixo de Y% de bateria ou sem responder.", 20.0, "%",
                 None, "aviso", _repetidora_bateria),
