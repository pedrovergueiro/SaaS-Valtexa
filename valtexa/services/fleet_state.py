"""Estado de cada robô na frota (brief, seção 25), derivado do protocolo.

Os sete estados — DISPONÍVEL, EM MISSÃO, SINCRONIZANDO, MANUTENÇÃO, OFFLINE,
BLOQUEADO e ERRO — **não são digitados por ninguém**. Saem do que o robô
informou e de quando informou:

* **contato** (``last_seen_at``): telemetria, ``/sync`` e abertura de sessão;
* **missão** (``active_mission_id``): mantido pelo gerenciador de missões —
  EM MISSÃO vem antes de SINCRONIZANDO, porque a descarga de um robô que está
  trabalhando se resolve sozinha no fim;
* **sincronização** (``sync_pending``): o próprio robô diz, a cada lote do
  ``/sync``, quantos registros ainda tem para descarregar;
* **falhas** (``active_faults``): a lista da amostra de telemetria mais recente;
* **administração** (``Device.status`` e credenciais): suspender, aposentar e pôr
  em manutenção são decisões de uma pessoa, auditadas em ``PATCH .../status`` —
  e mesmo elas só *entram* no cálculo, não o substituem.

A ordem da precedência é a pergunta "o que impede este robô de trabalhar agora?",
da causa mais forte para a mais fraca. Um robô suspenso que também está offline é
BLOQUEADO: religar o enlace não o libera. Um robô offline com falha na última
amostra é OFFLINE: a falha é de minutos atrás e pode já ter passado.

Função pura, com ``now`` injetável: a frota de 1.000 robôs é calculada na leitura
sem depender do worker ter passado, e o teste não precisa de relógio.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from valtexa.models import Connectivity, CredentialStatus, Device, DeviceStatus, as_utc
from valtexa.services.ingestion import DEGRADED_AFTER, OFFLINE_AFTER


class FleetState(StrEnum):
    DISPONIVEL = "disponivel"
    EM_MISSAO = "em_missao"
    SINCRONIZANDO = "sincronizando"
    MANUTENCAO = "manutencao"
    OFFLINE = "offline"
    BLOQUEADO = "bloqueado"
    ERRO = "erro"


ROTULOS = {
    FleetState.DISPONIVEL: "Disponível",
    FleetState.EM_MISSAO: "Em missão",
    FleetState.SINCRONIZANDO: "Sincronizando",
    FleetState.MANUTENCAO: "Manutenção",
    FleetState.OFFLINE: "Offline",
    FleetState.BLOQUEADO: "Bloqueado",
    FleetState.ERRO: "Erro",
}


@dataclass(frozen=True, slots=True)
class Situacao:
    state: FleetState
    reason: str
    connectivity: Connectivity


def connectivity(last_seen_at: datetime | None, now: datetime) -> Connectivity:
    """O enlace pelo tempo desde o último contato — a mesma régua do worker."""
    visto = as_utc(last_seen_at)
    if visto is None or now - visto > OFFLINE_AFTER:
        return Connectivity.OFFLINE
    if now - visto > DEGRADED_AFTER:
        return Connectivity.DEGRADED
    return Connectivity.OK


def _tem_credencial_valida(device: Device) -> bool:
    return any(c.status is not CredentialStatus.REVOKED for c in device.credentials)


def _descreve_falhas(falhas: list) -> str:
    nomes = []
    for falha in falhas[:3]:
        if isinstance(falha, dict):
            nomes.append(str(falha.get("code") or falha.get("message") or falha))
        else:
            nomes.append(str(falha))
    extra = f" e mais {len(falhas) - 3}" if len(falhas) > 3 else ""
    return ", ".join(nomes) + extra


def derive(device: Device, now: datetime | None = None) -> Situacao:
    """O estado de frota de ``device`` em ``now``, com o motivo em português."""
    agora = now or datetime.now(UTC)
    enlace = connectivity(device.last_seen_at, agora)

    if device.status is DeviceStatus.SUSPENDED:
        return Situacao(FleetState.BLOQUEADO, "Suspenso: não recebe missão.", enlace)
    if device.status is DeviceStatus.RETIRED:
        return Situacao(FleetState.BLOQUEADO, "Aposentado.", enlace)
    if not _tem_credencial_valida(device):
        return Situacao(
            FleetState.BLOQUEADO,
            "Sem credencial válida: precisa de provisionamento presencial.",
            enlace,
        )
    if device.status is DeviceStatus.MAINTENANCE:
        nota = f": {device.maintenance_note}" if device.maintenance_note else "."
        return Situacao(FleetState.MANUTENCAO, f"Em manutenção{nota}", enlace)
    if device.status is DeviceStatus.UNPROVISIONED:
        return Situacao(FleetState.OFFLINE, "Ainda não provisionado.", enlace)

    if enlace is Connectivity.OFFLINE:
        if device.last_seen_at is None:
            return Situacao(FleetState.OFFLINE, "Nunca fez contato.", enlace)
        minutos = int((agora - as_utc(device.last_seen_at)).total_seconds() // 60)
        return Situacao(FleetState.OFFLINE, f"Sem contato há {minutos} min.", enlace)

    falhas = list(device.active_faults or [])
    if falhas:
        return Situacao(
            FleetState.ERRO, f"Falha na última telemetria: {_descreve_falhas(falhas)}.", enlace
        )
    pendentes = f"{device.sync_pending} registro(s) pendente(s)"
    if device.active_mission_id:
        # Missão vem antes da descarga: o robô está trabalhando, e a pendência
        # se resolve sozinha no fim. O motivo conta as duas coisas.
        extra = f"; descarregando {pendentes}" if device.sync_pending > 0 else ""
        return Situacao(FleetState.EM_MISSAO, f"Executando uma missão{extra}.", enlace)
    if device.sync_pending > 0:
        return Situacao(
            FleetState.SINCRONIZANDO, f"Descarregando o período offline: {pendentes}.", enlace
        )
    return Situacao(FleetState.DISPONIVEL, "Pronto para receber missão.", enlace)


__all__ = ["ROTULOS", "FleetState", "Situacao", "connectivity", "derive"]
