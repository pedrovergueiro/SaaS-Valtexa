"""Camada de segurança e geometria.

O safety engine é a última coisa entre uma linha de banco e produto químico no
ar. Cada teste aqui é um bloqueio que precisa acontecer — e a maioria descreve
um erro operacional plausível, não um ataque: o tanque carregado com o produto
errado, o lote vencido, o vento sem leitura.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from valtexa.models import (
    Device,
    DeviceKind,
    DeviceModel,
    DeviceStatus,
    Farm,
    Field,
    Membership,
    Mission,
    MissionKind,
    MissionState,
    Product,
    ProductBatch,
    Role,
    RtkFix,
    SafetyVerdict,
    Tank,
    TankStatus,
    TelemetrySample,
    Tenant,
    User,
)
from valtexa.services import geo, safety_engine
from valtexa.services.hal import REFERENCE_MODELS

# Um quadrado de ~200 m perto de Itajubá.
CAMPO = [[-45.4530, -22.4120], [-45.4500, -22.4120], [-45.4500, -22.4140], [-45.4530, -22.4140]]
DENTRO = [[-45.4522, -22.4126], [-45.4510, -22.4126], [-45.4510, -22.4134], [-45.4522, -22.4134]]
FORA = [[-45.4600, -22.4126], [-45.4590, -22.4126], [-45.4590, -22.4134], [-45.4600, -22.4134]]


class TestGeometry:
    """Cerca virtual e planejamento — matemática pura, sem banco."""

    def test_ponto_dentro(self) -> None:
        assert geo.contains_point(CAMPO, -45.4515, -22.4130)

    def test_ponto_fora(self) -> None:
        assert not geo.contains_point(CAMPO, -45.4600, -22.4130)

    def test_ponto_sobre_a_aresta_conta_como_fora(self) -> None:
        """Na dúvida, o lado conservador.

        Melhor recusar um ponto na linha do que autorizar um voo que sai da área
        por um centímetro.
        """
        assert not geo.contains_point(CAMPO, -45.4530, -22.4130)

    def test_poligono_degenerado_e_recusado(self) -> None:
        """Sem isso, a cerca virtual viraria uma checagem que sempre aprova."""
        for ruim in ([], [[0, 0]], [[0, 0], [1, 1]], "nao-e-poligono"):
            with pytest.raises(geo.InvalidPolygonError):
                geo.as_points(ruim)

    def test_coordenada_impossivel_e_recusada(self) -> None:
        with pytest.raises(geo.InvalidPolygonError):
            geo.as_points([[0, 0], [200, 0], [0, 95]])

    def test_anel_fechado_nao_vira_aresta_de_comprimento_zero(self) -> None:
        fechado = [*CAMPO, CAMPO[0]]
        assert len(geo.as_points(fechado)) == len(CAMPO)

    def test_encolher_reduz_a_area(self) -> None:
        """A margem sempre aperta para dentro, nunca para fora."""
        assert geo.area_ha(geo.shrink(CAMPO, 10.0)) < geo.area_ha(CAMPO)

    def test_encolher_demais_colapsa_em_vez_de_inverter(self) -> None:
        """Uma área menor que a margem precisa falhar, não virar do avesso."""
        minusculo = [[-45.45300, -22.41200], [-45.45298, -22.41200], [-45.45298, -22.41202]]
        assert geo.area_ha(geo.shrink(minusculo, 50.0)) == pytest.approx(0.0, abs=1e-6)

    def test_area_bate_com_a_ordem_de_grandeza(self) -> None:
        """~300 m x 220 m ≈ 6,6 ha."""
        assert 5.0 < geo.area_ha(CAMPO) < 8.0

    def test_contencao_de_poligonos(self) -> None:
        assert geo.polygon_contains_polygon(CAMPO, DENTRO)
        assert not geo.polygon_contains_polygon(CAMPO, FORA)

    def test_cobertura_cobre_o_poligono(self) -> None:
        faixas = geo.boustrophedon(CAMPO, swath_m=20.0)
        assert len(faixas) > 1
        assert all(len(faixa) == 2 for faixa in faixas)

    def test_cobertura_alterna_o_sentido(self) -> None:
        """É o vaivém: sem alternar, o robô voltaria vazio a cada passada."""
        faixas = geo.boustrophedon(CAMPO, swath_m=20.0)
        primeira_para_leste = faixas[0][0][0] < faixas[0][1][0]
        segunda_para_leste = faixas[1][0][0] < faixas[1][1][0]
        assert primeira_para_leste != segunda_para_leste

    def test_faixa_maior_que_o_talhao_ainda_produz_um_percurso(self) -> None:
        """Um plano vazio deixaria o robô parado sem explicação."""
        assert geo.boustrophedon(CAMPO, swath_m=10_000.0)

    def test_faixa_precisa_ser_positiva(self) -> None:
        with pytest.raises(ValueError, match="positiva"):
            geo.boustrophedon(CAMPO, swath_m=0.0)


@pytest.fixture
def cenario(session: Session) -> dict:
    """Uma missão de pulverização com tudo em ordem. Cada teste quebra uma peça."""
    tenant = Tenant(name="Cliente", slug="cliente")
    agronomo = User(email="a@x.dev", full_name="Agrônomo", password_hash="x")
    session.add_all([tenant, agronomo])
    session.flush()
    session.add(Membership(tenant_id=tenant.id, user_id=agronomo.id, role=Role.AGRONOMIST))

    modelo = DeviceModel(**next(m for m in REFERENCE_MODELS if m["code"] == "DRONE_ACTION_V1"))
    session.add(modelo)
    session.flush()

    farm = Farm(
        tenant_id=tenant.id, name="Fazenda", center_lat=-22.413, center_lon=-45.4515,
        base_lat=-22.4145, base_lon=-45.4515,
    )
    session.add(farm)
    session.flush()

    field_row = Field(
        tenant_id=tenant.id, farm_id=farm.id, name="Talhão", crop="corn", boundary=CAMPO
    )
    session.add(field_row)
    session.flush()

    device = Device(
        tenant_id=tenant.id,
        serial_number="D-1",
        name="Drone",
        kind=DeviceKind.DRONE,
        device_model_id=modelo.id,
        farm_id=farm.id,
        status=DeviceStatus.ACTIVE,
        battery_percent=90.0,
    )
    session.add(device)
    session.flush()

    session.add(
        TelemetrySample(
            tenant_id=tenant.id,
            device_id=device.id,
            sequence_number=1,
            recorded_at=datetime.now(UTC),
            received_at=datetime.now(UTC),
            rtk_fix=RtkFix.FIXED,
            battery_percent=90.0,
        )
    )

    product = Product(
        tenant_id=tenant.id,
        name="Fungicida",
        registration_number="MAPA-1",
        allowed_crops=["corn"],
        authorized_targets=["Common_Rust"],
        min_rate_l_ha=0.5,
        max_rate_l_ha=1.0,
    )
    session.add(product)
    session.flush()

    batch = ProductBatch(
        tenant_id=tenant.id,
        product_id=product.id,
        code="L1",
        expires_on=date.today() + timedelta(days=180),
    )
    session.add(batch)
    session.flush()

    tank = Tank(
        tenant_id=tenant.id,
        device_id=device.id,
        index=0,
        capacity_l=10.0,
        current_level_l=10.0,
        status=TankStatus.LOADED,
        loaded_product_id=product.id,
        loaded_batch_id=batch.id,
    )
    session.add(tank)
    session.flush()

    mission = Mission(
        tenant_id=tenant.id,
        kind=MissionKind.SPRAY,
        state=MissionState.DRAFT,
        farm_id=farm.id,
        field_id=field_row.id,
        device_id=device.id,
        target_polygon=DENTRO,
        product_id=product.id,
        product_batch_id=batch.id,
        tank_id=tank.id,
        authorized_rate_l_ha=0.75,
        authorized_quantity_l=5.0,
        approved_by=agronomo.id,
        approved_at=datetime.now(UTC),
    )
    session.add(mission)
    session.commit()

    return {
        "session": session,
        "mission": mission,
        "device": device,
        "tank": tank,
        "batch": batch,
        "product": product,
        "agronomo": agronomo,
        "tenant": tenant,
    }


def _check(cenario: dict, wind_ms: float | None = 3.0) -> safety_engine.SafetyReport:
    return safety_engine.check_mission(cenario["session"], cenario["mission"], wind_ms=wind_ms)


def _blocked_codes(report: safety_engine.SafetyReport) -> set[str]:
    return {check.code for check in report.blocked}


class TestSafetyEngine:
    """Cada teste desliga uma peça e confere que a missão é barrada."""

    def test_o_caminho_completo_e_aprovado(self, cenario: dict) -> None:
        """Se o feliz não passa, nenhum dos bloqueios abaixo prova nada."""
        report = _check(cenario)
        assert report.verdict is SafetyVerdict.SAFE_TO_EXECUTE, report.blocked_reason

    def test_o_parecer_registra_tambem_o_que_passou(self, cenario: dict) -> None:
        """Um histórico só de bloqueios não deixa auditar por que algo passou."""
        report = _check(cenario)
        assert len(report.checks) > 10
        assert all(check.passed for check in report.checks)

    def test_bloqueia_sem_aprovacao_humana(self, cenario: dict) -> None:
        cenario["mission"].approved_by = None
        assert safety_engine.APPROVAL in _blocked_codes(_check(cenario))

    def test_bloqueia_quando_o_aprovador_perdeu_o_papel(self, cenario: dict) -> None:
        """O papel é reconferido na autorização, não confiado ao momento do clique."""
        session = cenario["session"]
        membership = session.query(Membership).filter_by(user_id=cenario["agronomo"].id).one()
        membership.role = Role.VIEWER
        session.commit()
        assert safety_engine.APPROVER_ROLE in _blocked_codes(_check(cenario))

    def test_bloqueia_tanque_com_produto_diferente(self, cenario: dict) -> None:
        """A pior falha possível: aplicar o produto errado na área certa."""
        outro = Product(tenant_id=cenario["tenant"].id, name="Outro", allowed_crops=["corn"])
        cenario["session"].add(outro)
        cenario["session"].flush()
        cenario["tank"].loaded_product_id = outro.id
        cenario["session"].commit()
        assert safety_engine.TANK_CONTENT in _blocked_codes(_check(cenario))

    def test_bloqueia_tanque_de_outro_dispositivo(self, cenario: dict) -> None:
        """Carregar o tanque do drone vizinho não autoriza este a voar."""
        session = cenario["session"]
        vizinho = Device(
            tenant_id=cenario["tenant"].id,
            serial_number="D-2",
            name="Drone 2",
            kind=DeviceKind.DRONE,
            device_model_id=cenario["device"].device_model_id,
            status=DeviceStatus.ACTIVE,
        )
        session.add(vizinho)
        session.flush()
        cenario["tank"].device_id = vizinho.id
        session.commit()
        assert safety_engine.TANK_DEVICE in _blocked_codes(_check(cenario))

    def test_bloqueia_volume_insuficiente(self, cenario: dict) -> None:
        cenario["tank"].current_level_l = 1.0
        cenario["session"].commit()
        assert safety_engine.TANK_VOLUME in _blocked_codes(_check(cenario))

    def test_bloqueia_lote_vencido(self, cenario: dict) -> None:
        cenario["batch"].expires_on = date.today() - timedelta(days=1)
        cenario["session"].commit()
        assert safety_engine.BATCH_VALID in _blocked_codes(_check(cenario))

    def test_bloqueia_produto_nao_autorizado_para_a_cultura(self, cenario: dict) -> None:
        cenario["product"].allowed_crops = ["soy"]
        cenario["session"].commit()
        assert safety_engine.PRODUCT_CROP in _blocked_codes(_check(cenario))

    def test_bloqueia_produto_sem_registro(self, cenario: dict) -> None:
        cenario["product"].registration_number = None
        cenario["session"].commit()
        assert safety_engine.PRODUCT_REGISTERED in _blocked_codes(_check(cenario))

    @pytest.mark.parametrize("dose", [0.1, 5.0])
    def test_bloqueia_dose_fora_da_bula(self, cenario: dict, dose: float) -> None:
        cenario["mission"].authorized_rate_l_ha = dose
        cenario["session"].commit()
        assert safety_engine.RATE_RANGE in _blocked_codes(_check(cenario))

    def test_bloqueia_area_fora_do_talhao(self, cenario: dict) -> None:
        cenario["mission"].target_polygon = FORA
        cenario["session"].commit()
        assert safety_engine.GEOFENCE in _blocked_codes(_check(cenario))

    def test_bloqueia_area_colada_na_borda(self, cenario: dict) -> None:
        """A margem existe para a deriva de posição não empurrar o robô para fora."""
        cenario["mission"].target_polygon = CAMPO
        cenario["session"].commit()
        assert safety_engine.GEOFENCE in _blocked_codes(_check(cenario))

    def test_bloqueia_bateria_baixa(self, cenario: dict) -> None:
        cenario["device"].battery_percent = 12.0
        cenario["session"].commit()
        assert safety_engine.BATTERY in _blocked_codes(_check(cenario))

    def test_bloqueia_sem_leitura_de_bateria(self, cenario: dict) -> None:
        """Falha fechada: dado ausente é bloqueio, não permissão."""
        cenario["device"].battery_percent = None
        cenario["session"].commit()
        assert safety_engine.BATTERY in _blocked_codes(_check(cenario))

    def test_bloqueia_sem_rtk_fixo(self, cenario: dict) -> None:
        """Sem RTK o erro é de metros: aplicar assim é aplicar no vizinho."""
        session = cenario["session"]
        sample = session.query(TelemetrySample).one()
        sample.rtk_fix = RtkFix.FLOAT
        session.commit()
        assert safety_engine.RTK in _blocked_codes(_check(cenario))

    def test_bloqueia_sem_leitura_de_vento(self, cenario: dict) -> None:
        """Pulverizar sem saber o vento é como a deriva atinge o vizinho."""
        assert safety_engine.WEATHER in _blocked_codes(_check(cenario, wind_ms=None))

    def test_bloqueia_vento_forte(self, cenario: dict) -> None:
        assert safety_engine.WEATHER in _blocked_codes(_check(cenario, wind_ms=25.0))

    def test_respeita_o_limite_de_vento_da_bula(self, cenario: dict) -> None:
        """O limite do produto aperta o global; nunca o afrouxa."""
        cenario["product"].max_wind_ms = 2.0
        cenario["session"].commit()
        assert safety_engine.WEATHER in _blocked_codes(_check(cenario, wind_ms=5.0))

    def test_bloqueia_dispositivo_suspenso(self, cenario: dict) -> None:
        cenario["device"].status = DeviceStatus.SUSPENDED
        cenario["session"].commit()
        assert safety_engine.DEVICE_ACTIVE in _blocked_codes(_check(cenario))

    def test_bloqueia_dispositivo_com_outra_missao(self, cenario: dict) -> None:
        """O robô tem um corpo só: duas autorizações são duas verdades."""
        cenario["device"].active_mission_id = "outra-missao"
        cenario["session"].commit()
        assert safety_engine.DEVICE_FREE in _blocked_codes(_check(cenario))

    def test_bloqueia_rover_em_missao_de_pulverizacao(self, cenario: dict) -> None:
        cenario["device"].kind = DeviceKind.ROVER
        cenario["session"].commit()
        codes = _blocked_codes(_check(cenario))
        assert safety_engine.DEVICE_KIND in codes

    def test_bloqueia_missao_vencida(self, cenario: dict) -> None:
        cenario["mission"].expires_at = datetime.now(UTC) - timedelta(minutes=1)
        cenario["session"].commit()
        assert safety_engine.MISSION_NOT_EXPIRED in _blocked_codes(_check(cenario))

    def test_lista_todos_os_impedimentos_de_uma_vez(self, cenario: dict) -> None:
        """O operador precisa ver a lista inteira, não descobrir um por tentativa."""
        cenario["mission"].approved_by = None
        cenario["device"].battery_percent = 5.0
        cenario["mission"].target_polygon = FORA
        cenario["session"].commit()
        codes = _blocked_codes(_check(cenario))
        assert {safety_engine.APPROVAL, safety_engine.BATTERY, safety_engine.GEOFENCE} <= codes
