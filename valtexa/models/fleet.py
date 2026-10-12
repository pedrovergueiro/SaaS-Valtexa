"""A frota e a identidade de cada robô.

:class:`DeviceModel` é a camada de abstração de hardware (HAL). O backend nunca
pergunta "este é o rover V1?"; pergunta "este dispositivo tem RTK? quantos
tanques? qual a autonomia?" — e a resposta vem de ``capabilities``. Trocar
LiDAR, câmera, GNSS ou fabricante do motor vira o cadastro de um modelo novo,
não uma alteração no motor de decisão.

:class:`Device` é a instância física, com número de série. :class:`DeviceCredential`
é a chave pública com que ela assina — separada da instância porque uma
credencial é rotacionada e revogada sem que o robô mude de identidade.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from valtexa.models.base import Base, TenantScoped, Timestamped, UUIDPrimaryKey, enum_column
from valtexa.models.enums import Connectivity, CredentialStatus, DeviceKind, DeviceStatus

PROTOCOL_VERSION = "1.0"
"""Versão do protocolo robô↔nuvem implementada por este servidor.

Um robô que anuncia versão maior é recusado no registro: é melhor falhar no
provisionamento do que descobrir a incompatibilidade no meio de um voo.
"""


class DeviceModel(UUIDPrimaryKey, Timestamped, Base):
    """Um modelo de hardware — a camada de abstração.

    Não é multi-tenant: o catálogo de modelos é da ValTexa, e um mesmo rover V1
    serve todos os clientes.
    """

    __tablename__ = "device_model"

    code: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True, doc="Ex.: 'ROVER_SCOUT_V1'."
    )
    kind: Mapped[DeviceKind] = mapped_column(enum_column(DeviceKind), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    manufacturer: Mapped[str | None] = mapped_column(String(160))
    protocol_version: Mapped[str] = mapped_column(String(16), default=PROTOCOL_VERSION)
    capabilities: Mapped[dict] = mapped_column(
        nullable=False,
        default=dict,
        doc=(
            "Descritor consultado pelo planejamento e pelo safety engine. Chaves "
            "reconhecidas em valtexa.services.hal.Capabilities."
        ),
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    devices: Mapped[list[Device]] = relationship(back_populates="model")


class Device(UUIDPrimaryKey, TenantScoped, Timestamped, Base):
    """Um robô físico (ou uma base, ou um sensor)."""

    __tablename__ = "device"
    __table_args__ = (
        UniqueConstraint("serial_number", name="uq_device_serial"),
        UniqueConstraint("tenant_id", "name", name="uq_device_tenant_name"),
    )

    serial_number: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    kind: Mapped[DeviceKind] = mapped_column(enum_column(DeviceKind), nullable=False, index=True)
    device_model_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("device_model.id"), nullable=False, index=True
    )
    farm_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("farm.id", ondelete="SET NULL"), index=True
    )
    home_dock_id: Mapped[str | None] = mapped_column(
        String(32),
        ForeignKey("device.id", ondelete="SET NULL"),
        doc="A dock onde este robô recarrega. Nulo para a própria dock.",
    )

    status: Mapped[DeviceStatus] = mapped_column(
        enum_column(DeviceStatus), default=DeviceStatus.UNPROVISIONED, nullable=False, index=True
    )
    firmware_version: Mapped[str | None] = mapped_column(String(32))
    hardware_version: Mapped[str | None] = mapped_column(String(32))
    protocol_version: Mapped[str | None] = mapped_column(String(16))

    # Última posição conhecida. Duplica a telemetria de propósito: a lista de
    # frota precisa de uma leitura por dispositivo, não de um MAX() sobre milhões
    # de amostras.
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    last_lat: Mapped[float | None] = mapped_column(Float)
    last_lon: Mapped[float | None] = mapped_column(Float)
    last_alt_m: Mapped[float | None] = mapped_column(Float)
    battery_percent: Mapped[float | None] = mapped_column(Float)
    connectivity: Mapped[Connectivity] = mapped_column(
        enum_column(Connectivity), default=Connectivity.OFFLINE, nullable=False
    )
    active_mission_id: Mapped[str | None] = mapped_column(String(32), index=True)
    last_sequence_number: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        doc=(
            "Marca d'água: o maior número de sequência já aceito deste "
            "dispositivo. O robô mantém um único contador para tudo que envia — "
            "telemetria, eventos e observações. O servidor **não** recusa "
            "sequência menor: um lote que ficou preso offline chega fora de "
            "ordem e é dado legítimo. O que ele faz é ignorar par "
            "(dispositivo, sequência) já gravado, o que torna o reenvio "
            "idempotente sem perder nada."
        ),
    )

    # --- Frota (brief, seções 22 e 25) -------------------------------------
    # Tudo aqui é o que o próprio robô informa pelo protocolo — na abertura da
    # sessão (versões), na telemetria (saúde) e na sincronização (pendência).
    # Ninguém digita estes campos: o estado da frota é derivado deles por
    # :func:`valtexa.services.fleet_state.derive`.
    runtime_version: Mapped[str | None] = mapped_column(
        String(32), doc="Versão do Rover Runtime (o software do robô)."
    )
    edge_ai_version: Mapped[str | None] = mapped_column(
        String(32), doc="Versão do motor de IA embarcada."
    )
    ai_model_key: Mapped[str | None] = mapped_column(
        String(64), doc="Modelo que o robô diz estar usando — chave do registry."
    )
    ai_model_version: Mapped[str | None] = mapped_column(String(32))
    dnaty_version: Mapped[str | None] = mapped_column(
        String(32), doc="Versão do dNATY que otimizou o modelo embarcado, se houver."
    )
    versions_reported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    temperature_c: Mapped[float | None] = mapped_column(Float)
    storage_total_bytes: Mapped[int | None] = mapped_column(BigInteger)
    storage_free_bytes: Mapped[int | None] = mapped_column(BigInteger)
    link_quality: Mapped[float | None] = mapped_column(Float)
    operating_hours: Mapped[float | None] = mapped_column(
        Float, doc="Horímetro do robô. Só sobe: um valor menor recebido é ignorado."
    )
    active_faults: Mapped[list] = mapped_column(
        default=list,
        nullable=False,
        doc="Falhas da amostra de telemetria mais recente. Vazio = sem falha ativa.",
    )
    sync_pending: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        doc="Registros que o robô disse ainda ter para descarregar no último /sync.",
    )
    last_sync_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), doc="Fim da última descarga completa (nada pendente)."
    )
    last_maintenance_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), doc="Quando o robô saiu da manutenção pela última vez."
    )
    maintenance_note: Mapped[str | None] = mapped_column(Text)
    health: Mapped[dict | None] = mapped_column(
        doc="Saúde padronizada da amostra mais recente (CPU, memória, acelerador, câmeras, "
            "sensores, rede, sincronização). Ver services/saude_rover.py."
    )
    health_reported_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), doc="Quando o robô mediu a saúde guardada em ``health``."
    )
    # Rádio da fazenda (valtexa.services.chave_de_enlace): a pública X25519 do enlace
    # assinada pela identidade do robô. A base busca daqui, conferindo a assinatura.
    enlace_chave: Mapped[dict | None] = mapped_column(
        doc="{nome, enlace_pub, assinatura, ed25519_pub} publicado pelo próprio robô."
    )
    enlace_chave_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Centro de comando (valtexa.services.comando_rover).
    pinned_model_key: Mapped[str | None] = mapped_column(
        String(64), doc="Modelo fixado neste robô pela equipe (sobrepõe o do talhão)."
    )
    pinned_model_version: Mapped[str | None] = mapped_column(String(32))
    control_mode: Mapped[str | None] = mapped_column(
        String(16), doc="Último modo pedido: autonomo, manual, pausado ou parado."
    )
    teleop_v: Mapped[float | None] = mapped_column(Float, doc="m/s pedido no controle remoto.")
    teleop_w: Mapped[float | None] = mapped_column(Float, doc="rad/s pedido no controle remoto.")
    teleop_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), doc="Validade do ponto de ajuste (homem-morto: ~1 s)."
    )
    teleop_seq: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    teleop_by: Mapped[str | None] = mapped_column(String(32))

    model: Mapped[DeviceModel] = relationship(back_populates="devices")
    credentials: Mapped[list[DeviceCredential]] = relationship(
        back_populates="device", cascade="all, delete-orphan", passive_deletes=True
    )

    @property
    def capabilities(self) -> dict:
        """Atalho para o descritor do modelo."""
        return self.model.capabilities if self.model else {}


class DeviceCredential(UUIDPrimaryKey, Timestamped, Base):
    """A chave pública Ed25519 de um dispositivo.

    A plataforma guarda **apenas** a chave pública: a privada é gerada dentro do
    robô no primeiro boot e nunca sai de lá. Um dump desta tabela não permite se
    passar por nenhum dispositivo — que é precisamente o motivo de o protocolo
    ser assimétrico. Ver :mod:`valtexa.security.signing`.
    """

    __tablename__ = "device_credential"

    device_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("device.id", ondelete="CASCADE"), nullable=False, index=True
    )
    key_id: Mapped[str] = mapped_column(
        String(32), nullable=False, unique=True, index=True, doc="Vai no cabeçalho da assinatura."
    )
    public_key: Mapped[str] = mapped_column(
        String(128), nullable=False, doc="Ed25519 bruta, em hexadecimal (64 caracteres)."
    )
    algorithm: Mapped[str] = mapped_column(String(32), default="Ed25519", nullable=False)
    status: Mapped[CredentialStatus] = mapped_column(
        enum_column(CredentialStatus), default=CredentialStatus.ACTIVE, nullable=False, index=True
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    device: Mapped[Device] = relationship(back_populates="credentials")


class ProvisioningToken(UUIDPrimaryKey, TenantScoped, Timestamped, Base):
    """Convite de uso único para um robô entrar na frota.

    O técnico gera o token no escritório e o grava no robô. O robô o troca por
    uma credencial permanente no primeiro contato. Um token usado nunca serve
    de novo, e um token vencido é recusado mesmo que nunca tenha sido usado.
    """

    __tablename__ = "provisioning_token"

    token_hash: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    device_model_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("device_model.id"), nullable=False
    )
    farm_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("farm.id"))
    serial_number: Mapped[str | None] = mapped_column(
        String(64), doc="Quando preenchido, o token só serve para este número de série."
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    device_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("device.id"))
    created_by: Mapped[str | None] = mapped_column(String(32), ForeignKey("user.id"))
