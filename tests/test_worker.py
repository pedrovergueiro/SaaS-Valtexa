"""Worker de fundo e retenção: o que a plataforma faz sem ninguém pedir."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from valtexa import worker
from valtexa.models import (
    Connectivity,
    Mission,
    MissionKind,
    MissionState,
    OutboxEvent,
    RtkFix,
    TelemetryRollup,
    TelemetrySample,
    UsedNonce,
)
from valtexa.services import mission_manager, retention


def _dispatched(frota: dict) -> Mission:
    session = frota["session"]
    mission = mission_manager.create_mission(
        session,
        tenant_id=frota["tenant"].id,
        kind=MissionKind.SCOUT,
        field_row=frota["field"],
        device=frota["device"],
    )
    mission_manager.authorize(session, mission, wind_ms=2.0)
    mission_manager.dispatch(session, mission)
    session.commit()
    return mission


def _event_names(session) -> set[str]:
    return set(session.scalars(select(OutboxEvent.name)))


class TestExpiry:
    def test_missao_despachada_e_vencida_libera_o_robo(self, frota: dict) -> None:
        """Sem isto o robô ficaria preso a uma missão que nunca buscou."""
        session = frota["session"]
        mission = _dispatched(frota)
        assert frota["device"].active_mission_id == mission.id

        mission.expires_at = datetime.now(UTC) - timedelta(minutes=1)
        session.commit()
        assert mission_manager.expire_stale(session) == 1
        session.commit()

        assert mission.state is MissionState.EXPIRED
        assert frota["device"].active_mission_id is None
        assert "mission.expired" in _event_names(session)

    def test_missao_em_execucao_nao_vence(self, frota: dict) -> None:
        """A validade impede começar tarde, não interrompe quem já está no campo."""
        session = frota["session"]
        mission = _dispatched(frota)
        mission_manager.transition(session, mission, MissionState.RUNNING)
        mission.expires_at = datetime.now(UTC) - timedelta(minutes=1)
        session.commit()

        assert mission_manager.expire_stale(session) == 0
        assert mission.state is MissionState.RUNNING

    def test_missao_no_prazo_fica(self, frota: dict) -> None:
        _dispatched(frota)
        assert mission_manager.expire_stale(frota["session"]) == 0


class TestConnectivity:
    def test_robo_que_parou_de_falar_fica_offline(self, frota: dict) -> None:
        """É o robô que parou de mandar telemetria que precisa ser notado."""
        session, device = frota["session"], frota["device"]
        device.last_seen_at = datetime.now(UTC) - timedelta(minutes=10)
        device.connectivity = Connectivity.OK
        session.commit()

        assert worker.refresh_connectivity(session) == 1
        session.commit()
        assert device.connectivity is Connectivity.OFFLINE
        assert "device.offline" in _event_names(session)

    def test_ja_offline_nao_repete_o_aviso(self, frota: dict) -> None:
        session, device = frota["session"], frota["device"]
        device.last_seen_at = datetime.now(UTC) - timedelta(minutes=10)
        device.connectivity = Connectivity.OFFLINE
        session.commit()
        assert worker.refresh_connectivity(session) == 0


def _samples(frota: dict, start: datetime, count: int, *, first_sequence: int = 1) -> None:
    session, device = frota["session"], frota["device"]
    for index in range(count):
        session.add(
            TelemetrySample(
                tenant_id=device.tenant_id,
                device_id=device.id,
                sequence_number=first_sequence + index,
                recorded_at=start + timedelta(seconds=index),
                received_at=start,
                battery_percent=100.0 - index * 0.1,
                speed_ms=1.0,
                rtk_fix=RtkFix.FIXED if index % 2 == 0 else RtkFix.FLOAT,
                lat=-22.41,
                lon=-45.45 + index * 1e-6,
            )
        )
    session.commit()


def _old_minute() -> datetime:
    return (datetime.now(UTC) - timedelta(days=100)).replace(second=0, microsecond=0)


class TestRetention:
    def test_agrega_por_minuto_e_apaga_o_cru(self, frota: dict) -> None:
        session = frota["session"]
        _samples(frota, _old_minute(), 180)

        assert retention.rollup_telemetry(session, older_than_days=30) == (3, 180)
        assert session.query(TelemetrySample).count() == 0

        rollups = session.scalars(
            select(TelemetryRollup).order_by(TelemetryRollup.bucket_start)
        ).all()
        assert [rollup.samples for rollup in rollups] == [60, 60, 60]
        first = rollups[0]
        assert first.battery_max == pytest.approx(100.0)
        assert first.battery_min == pytest.approx(100.0 - 59 * 0.1)
        assert first.battery_avg == pytest.approx(100.0 - 2.95)
        assert first.rtk_fixed_ratio == pytest.approx(0.5)
        assert first.last_lon == pytest.approx(-45.45 + 59e-6)

    def test_rodar_de_novo_nao_duplica(self, frota: dict) -> None:
        session = frota["session"]
        _samples(frota, _old_minute(), 120)
        retention.rollup_telemetry(session, older_than_days=30)
        assert retention.rollup_telemetry(session, older_than_days=30) == (0, 0)
        assert session.query(TelemetryRollup).count() == 2

    def test_janela_dividida_entre_lotes_se_soma(
        self, frota: dict, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Um lote que corta um minuto ao meio não pode gerar duas linhas."""
        monkeypatch.setattr(retention, "BATCH", 50)
        session = frota["session"]
        _samples(frota, _old_minute(), 180)

        written, rolled = retention.rollup_telemetry(session, older_than_days=30)
        assert (written, rolled) == (3, 180)
        rollups = session.scalars(
            select(TelemetryRollup).order_by(TelemetryRollup.bucket_start)
        ).all()
        assert [rollup.samples for rollup in rollups] == [60, 60, 60]
        assert rollups[0].battery_avg == pytest.approx(100.0 - 2.95)

    def test_telemetria_recente_fica_crua(self, frota: dict) -> None:
        session = frota["session"]
        _samples(frota, datetime.now(UTC) - timedelta(hours=1), 30)
        assert retention.rollup_telemetry(session, older_than_days=30) == (0, 0)
        assert session.query(TelemetrySample).count() == 30

    def test_nonce_vencido_sai_e_o_valido_fica(self, frota: dict) -> None:
        session, device = frota["session"], frota["device"]
        now = datetime.now(UTC)
        session.add_all(
            [
                UsedNonce(device_id=device.id, nonce="velho", expires_at=now - timedelta(1)),
                UsedNonce(device_id=device.id, nonce="novo", expires_at=now + timedelta(1)),
            ]
        )
        session.commit()
        assert retention.purge_nonces(session) == 1
        assert [row.nonce for row in session.query(UsedNonce)] == ["novo"]


def test_worker_respeita_as_cadencias(demo: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    """Cada tarefa roda na sua frequência, não a cada ciclo."""
    calls: list[str] = []
    monkeypatch.setattr(
        worker.mission_manager, "expire_stale", lambda session: calls.append("expiry") or 0
    )
    monkeypatch.setattr(worker, "refresh_connectivity", lambda session: calls.append("conn") or 0)
    monkeypatch.setattr(
        worker.retention,
        "run",
        lambda session: calls.append("retention") or retention.RetentionReport(0, 0, 0, 0),
    )

    agenda = worker.Worker()
    agenda.tick(now=0.0)
    agenda.tick(now=1.0)
    agenda.tick(now=worker.EXPIRY_EVERY + 1)

    assert calls.count("expiry") == 2
    assert calls.count("conn") == 1
    assert calls.count("retention") == 1
