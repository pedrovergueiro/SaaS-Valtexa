"""Comando remoto a um Rover: o que o centro de comando manda e o que o robô respondeu.

Cada comando sai **assinado** pela plataforma (o mesmo envelope Ed25519 da missão:
destinatário, sequência, nonce, validade) e o robô confere antes de obedecer. Os tipos
(:data:`KINDS`) são o que o Runtime sabe executar — ver ``valtexa_rover.runtime.comandos``.

O controle remoto (teleoperação) não passa por aqui: é um ponto de ajuste de velocidade
renovado várias vezes por segundo, guardado no próprio :class:`~valtexa.models.Device`
(``teleop_*``), que vence em 1 s sem renovação — o homem-morto.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from valtexa.models.base import Base, TenantScoped, Timestamped, UUIDPrimaryKey

KINDS = (
    "diagnostico",  # lê cada peça (ou as escolhidas) e devolve o laudo
    "foto",  # uma foto de uma câmera, reduzida, com a distância medida
    "modo",  # autonomo | manual | pausado | parado — para a navegação
    "parar",  # parada imediata, com motivo
    "config",  # troca parte do rover.json (validada no robô, troca atômica)
    "recarregar_modelos",  # busca de novo os modelos designados/fixados
    "reiniciar",  # reinicia o serviço (o systemd sobe de novo)
    "ensaio",  # roda um ensaio de validação numa thread (progresso → laudo)
    "ensaio_cancelar",  # para o ensaio em curso
    "liberar_retidos",  # volta à fila o que o orçamento de dados reteve no disco
    "orcamento",  # o consumo de dados do dia, pelo próprio robô
)
STATES = ("pendente", "entregue", "em_execucao", "concluido", "falhou", "expirado",
          "cancelado")


class DeviceCommand(UUIDPrimaryKey, TenantScoped, Timestamped, Base):
    __tablename__ = "device_command"
    __table_args__ = (Index("ix_device_command_device_state", "device_id", "state"),)

    device_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("device.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    params: Mapped[dict] = mapped_column(default=dict)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="pendente")
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    envelope: Mapped[dict] = mapped_column(default=dict, doc="O comando assinado, como saiu.")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result: Mapped[dict | None] = mapped_column()
    error: Mapped[str | None] = mapped_column(Text)
    progress: Mapped[dict | None] = mapped_column(
        doc="Ensaio em execução: fração, etapa, parcial e quando chegou.")
    created_by: Mapped[str | None] = mapped_column(String(32), ForeignKey("user.id"))
