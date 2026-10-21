"""Regra de segurança do **voo de observação do drone** — DESENHO, **DESLIGADA**.

> **Aguarda decisão do Pedro** (``docs/historico/RODADA4.md``, item 5). Hoje o Safety Engine
> só aceita missão sem aplicação feita por **Rover** (``_check_device``: ``scout`` exige
> ``rover``), e a coordenação drone → Rover funciona com o levantamento aéreo **importado**
> (``POST /v1/fields/{id}/gemeo/levantamento-aereo``), sem a plataforma comandar o voo.
> Este módulo diz o que a regra checaria; **nenhum caminho o chama** (:data:`LIGADA` é
> falso e ``tests/test_regra_voo_observacao.py`` prova que o Safety Engine não o alcança).
> Ligá-lo é mudança de segurança: entra no ``safety_engine.check_mission`` para
> ``kind=scout`` com drone, com revisão do Pedro.

O que a regra checaria (todas, sem parar na primeira — como o Safety Engine):

* estado e geometria — os mesmos do Safety Engine (estado autorizável; polígono dentro do
  talhão com margem);
* ``voo_dispositivo`` — drone ativo, do cliente, livre, com câmera de observação;
* ``voo_sem_aplicacao`` — ``scout``, sem produto, lote, tanque nem dose;
* ``voo_vento`` — vento até ``max_wind_ms_voo`` do drone (ou o limite global); **sem
  leitura, bloqueia**;
* ``voo_gnss`` — última telemetria com posição (``single``/``float``/``fixed``); RTK fixo
  não é exigido para observar (premissa a confirmar);
* ``voo_energia`` — autonomia x (bateria - reserva) cobre o voo estimado vezes a margem de
  retorno (:data:`energy.RETURN_MARGIN`);
* ``voo_altura`` — altura declarada no plano até :data:`ALTURA_MAXIMA_M` (120 m: **premissa
  a confirmar na regulação vigente, ANAC/DECEA** — não verificada aqui);
* ``voo_operador`` — piloto remoto responsável em linha de visada registrado no plano;
* ``voo_janela`` — hora local entre :data:`HORA_INICIO` e :data:`HORA_FIM` (6 h às 18 h,
  padrão não medido).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from valtexa.config import settings
from valtexa.models import (
    Device,
    DeviceKind,
    DeviceStatus,
    Mission,
    MissionKind,
    RtkFix,
    SafetyVerdict,
)
from valtexa.models.operations import TelemetrySample
from valtexa.services import energy, geo, safety_engine
from valtexa.services.hal import capabilities_of

LIGADA = False
"""Desligada: aguarda decisão do Pedro. Nada no código lê esta regra para liberar missão."""

ALTURA_MAXIMA_M = 120.0
"""Premissa a confirmar na regulação vigente — não é afirmação regulatória."""
HORA_INICIO, HORA_FIM = 6, 18
FUSO_FAZENDA = timedelta(hours=-3)

VOO_DISPOSITIVO = "voo_dispositivo"
VOO_SEM_APLICACAO = "voo_sem_aplicacao"
VOO_VENTO = "voo_vento"
VOO_GNSS = "voo_gnss"
VOO_ENERGIA = "voo_energia"
VOO_ALTURA = "voo_altura"
VOO_OPERADOR = "voo_operador"
VOO_JANELA = "voo_janela"

Check = safety_engine.Check


def _dispositivo(mission: Mission, device: Device | None) -> Check:
    if device is None:
        return Check(VOO_DISPOSITIVO, False, "Dispositivo não existe.")
    cap = capabilities_of(device.capabilities)
    problemas = []
    if device.kind is not DeviceKind.DRONE:
        problemas.append(f"é {device.kind.value!r}, não drone")
    if device.tenant_id != mission.tenant_id:
        problemas.append("de outro cliente")
    if device.status is not DeviceStatus.ACTIVE:
        problemas.append(f"status {device.status.value!r}")
    if device.active_mission_id not in (None, mission.id):
        problemas.append(f"já executa {device.active_mission_id}")
    if cap.missing_for_scout():
        problemas.append(f"sem {cap.missing_for_scout()}")
    return Check(VOO_DISPOSITIVO, not problemas,
                 "Drone apto para observação." if not problemas else "; ".join(problemas))


def _sem_aplicacao(mission: Mission) -> Check:
    aplica = [nome for nome in ("product_id", "product_batch_id", "tank_id",
                                "authorized_rate_l_ha", "authorized_quantity_l")
              if getattr(mission, nome) is not None]
    ok = mission.kind is MissionKind.SCOUT and not aplica
    return Check(VOO_SEM_APLICACAO, ok, "Voo só de observação." if ok else
                 f"Missão {mission.kind.value!r} com {aplica or 'tipo errado'}: não é observação.")


def _vento(session: Session, mission: Mission, device: Device | None,
           vento_ms: float | None) -> Check:
    if vento_ms is None:
        vento_ms = safety_engine._wind_from_dock(session, mission)
    if vento_ms is None:
        return Check(VOO_VENTO, False, "Sem leitura de vento: voo não liberável.")
    cap = capabilities_of(device.capabilities if device else {})
    limite = cap.number("max_wind_ms_voo", settings.safety_max_wind_ms)
    return Check(VOO_VENTO, vento_ms <= limite, f"Vento {vento_ms:.1f} m/s (limite {limite:.1f}).")


def _gnss(session: Session, device: Device | None) -> Check:
    if device is None:
        return Check(VOO_GNSS, False, "Sem dispositivo.")
    ultima = session.scalars(select(TelemetrySample).where(
        TelemetrySample.device_id == device.id).order_by(
        TelemetrySample.recorded_at.desc()).limit(1)).first()
    if ultima is None:
        return Check(VOO_GNSS, False, "Sem telemetria: posição desconhecida.")
    ok = ultima.rtk_fix in (RtkFix.SINGLE, RtkFix.FLOAT, RtkFix.FIXED)
    return Check(VOO_GNSS, ok, f"Posição {ultima.rtk_fix.value!r}.")


def _energia(mission: Mission, device: Device | None) -> Check:
    if device is None or device.battery_percent is None:
        return Check(VOO_ENERGIA, False, "Sem leitura de bateria.")
    cap = capabilities_of(device.capabilities)
    disponivel_s = (cap.endurance_minutes * 60.0
                    * max(0.0, device.battery_percent - settings.energy_reserve_percent) / 100.0)
    try:
        area_m2 = geo.area_ha(mission.target_polygon) * 10_000.0
    except geo.InvalidPolygonError:
        return Check(VOO_ENERGIA, False, "Polígono inválido: voo não estimável.")
    percurso = area_m2 / max(0.1, cap.swath_m)
    necessario_s = percurso / max(0.1, cap.cruise_speed_ms) * energy.RETURN_MARGIN
    return Check(VOO_ENERGIA, necessario_s <= disponivel_s,
                 f"Voo estimado {necessario_s / 60:.0f} min (com margem); disponível "
                 f"{disponivel_s / 60:.0f} min acima da reserva.")


def _altura(mission: Mission) -> Check:
    altura = (mission.plan or {}).get("altura_m")
    if altura is None:
        return Check(VOO_ALTURA, False, "Altura de voo não declarada no plano.")
    return Check(VOO_ALTURA, 0 < float(altura) <= ALTURA_MAXIMA_M,
                 f"Altura {float(altura):.0f} m (máximo {ALTURA_MAXIMA_M:.0f} m, premissa a "
                 "confirmar na regulação vigente).")


def _operador(mission: Mission) -> Check:
    op = (mission.plan or {}).get("operador_vlos")
    return Check(VOO_OPERADOR, bool(op), f"Piloto remoto em linha de visada: {op}." if op else
                 "Sem piloto remoto em linha de visada registrado.")


def _janela(agora: datetime) -> Check:
    hora = (agora.astimezone(UTC) + FUSO_FAZENDA).hour
    ok = HORA_INICIO <= hora < HORA_FIM
    return Check(VOO_JANELA, ok, f"Hora local {hora} h (janela {HORA_INICIO} a {HORA_FIM} h).")


def verificar(session: Session, mission: Mission, *, agora: datetime,
              vento_ms: float | None = None) -> safety_engine.SafetyReport:
    """O que a regra diria — determinístico para o mesmo banco, missão e instante. **Não**
    grava, não muda a missão e não é chamada pelo Safety Engine (:data:`LIGADA`)."""
    device = session.get(Device, mission.device_id)
    checks = [
        *safety_engine._check_mission_state(mission, agora),
        _dispositivo(mission, device),
        _sem_aplicacao(mission),
        *safety_engine._check_geometry(session, mission),
        _vento(session, mission, device, vento_ms),
        _gnss(session, device),
        _energia(mission, device),
        _altura(mission),
        _operador(mission),
        _janela(agora),
    ]
    veredito = (SafetyVerdict.SAFE_TO_EXECUTE if all(c.passed for c in checks)
                else SafetyVerdict.BLOCKED)
    return safety_engine.SafetyReport(verdict=veredito, checks=tuple(checks))
