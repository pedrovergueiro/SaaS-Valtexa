"""Configuração da plataforma, lida do ambiente.

Tudo que muda entre desenvolvimento, homologação e produção passa por aqui. Os
padrões foram escolhidos para que ``uvicorn valtexa.main:app`` suba um ambiente
completo e funcional sem nenhuma variável definida — mas os segredos têm padrão
inseguro de propósito, e :func:`Settings.production_problems` recusa subir em
produção enquanto eles não forem trocados.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent

INSECURE_DEFAULT_SECRET = "dev-only-change-me"
"""Valor sentinela dos segredos. Serve para o ambiente local e é recusado em produção."""


class Settings(BaseSettings):
    """Parâmetros de execução da plataforma."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", frozen=True
    )

    environment: str = Field(
        default="development",
        description="'development', 'staging' ou 'production'. Só 'production' aperta as travas.",
    )
    log_level: str = "INFO"

    # --- banco e armazenamento -------------------------------------------------
    database_url: str = Field(
        default=f"sqlite:///{BASE_DIR / 'valtexa.db'}",
        description="URL SQLAlchemy. SQLite serve o piloto; Postgres é o alvo de produção.",
    )
    storage_dir: Path = Field(
        default=BASE_DIR / "storage",
        description="Raiz do armazenamento de objetos (imagens, nuvens de pontos, mapas).",
    )
    max_asset_mb: int = Field(default=64, ge=1, description="Limite por arquivo enviado.")

    # --- segredos --------------------------------------------------------------
    session_secret: str = Field(
        default=INSECURE_DEFAULT_SECRET,
        description="Assina os tokens de sessão de usuários e dispositivos.",
    )
    command_signing_secret: str = Field(
        default=INSECURE_DEFAULT_SECRET,
        description=(
            "Assina as missões e comandos enviados aos robôs. Trocar esta chave "
            "invalida todos os comandos ainda em trânsito — que é o efeito desejado."
        ),
    )
    command_signing_key_id: str = Field(
        default="k1", description="Identificador da chave, para permitir rotação sem downtime."
    )

    # --- janelas e limites de protocolo ----------------------------------------
    device_clock_skew_seconds: int = Field(
        default=300,
        ge=30,
        description=(
            "Tolerância do relógio do robô na verificação de assinatura. Requisições "
            "fora da janela são recusadas — é o que impede replay de gravação antiga."
        ),
    )
    device_session_ttl_seconds: int = Field(
        default=3600, ge=60, description="Validade do token de sessão do dispositivo."
    )
    user_session_ttl_seconds: int = Field(
        default=43200, ge=300, description="Validade do token de sessão do usuário."
    )
    command_ttl_seconds: int = Field(
        default=1800,
        ge=60,
        description=(
            "Validade padrão de uma missão assinada. Comando expirado nunca é "
            "executado, mesmo que chegue ao robô."
        ),
    )
    nonce_retention_seconds: int = Field(
        default=900, ge=60, description="Por quanto tempo um nonce usado continua bloqueado."
    )
    max_telemetry_batch: int = Field(
        default=500, ge=1, description="Amostras por requisição de telemetria."
    )
    max_sync_batch: int = Field(
        default=1000, ge=1, description="Registros por requisição de sincronização offline."
    )

    # --- pipeline de IA --------------------------------------------------------
    inference_url: str = Field(
        default="http://127.0.0.1:8000",
        description="Base do valtexa-disease-backend. Ver o repositório VALTEXA-B.",
    )
    inference_timeout_seconds: float = Field(default=30.0, gt=0)
    inference_enabled: bool = Field(
        default=True,
        description="Desligue para rodar a plataforma sem o serviço de modelos no ar.",
    )
    simulated_inference: bool = Field(
        default=False,
        description=(
            "Substitui os modelos reais por analisadores falsos e determinísticos. "
            "Existe para o simulador exercitar a cadeia inteira sem GPU e sem os "
            "pesos. Recusado em produção — um diagnóstico inventado que chegasse a "
            "um produtor seria pior do que não ter diagnóstico nenhum."
        ),
    )
    min_confidence: float = Field(
        default=0.70,
        ge=0.0,
        le=1.0,
        description=(
            "Abaixo disso o diagnóstico é inconclusivo. Medido em VALTEXA-B/MODELS.md: "
            "sozinho intercepta 17% de uma doença fora do catálogo."
        ),
    )
    novelty_threshold: float = Field(
        default=1.0,
        gt=0.0,
        description="Acima disso a imagem destoa do que o modelo conhece e vai para o agrônomo.",
    )
    agreement_tolerance: float = Field(
        default=0.15,
        ge=0.0,
        le=1.0,
        description=(
            "Diferença máxima de confiança entre as duas análises para que a "
            "concordância seja aceita sem revisão humana."
        ),
    )

    # --- regras agronômicas e de segurança -------------------------------------
    decision_min_confidence_for_application: float = Field(
        default=0.85,
        ge=0.0,
        le=1.0,
        description="Confiança mínima para que um diagnóstico vire candidato a aplicação.",
    )
    decision_min_incidence: float = Field(
        default=0.05,
        ge=0.0,
        le=1.0,
        description="Fração mínima do talhão afetada para justificar uma aplicação.",
    )
    safety_min_battery_percent: float = Field(
        default=35.0, ge=0.0, le=100.0, description="Bateria mínima para autorizar decolagem."
    )
    safety_max_wind_ms: float = Field(
        default=8.0, gt=0.0, description="Vento máximo para pulverização, em m/s."
    )
    geofence_margin_m: float = Field(
        default=5.0,
        ge=0.0,
        description=(
            "Margem interna do polígono autorizado. Aplica-se sempre para "
            "dentro, nunca para fora."
        ),
    )

    # --- energia (política enviada ao robô) ------------------------------------
    energy_reserve_percent: float = Field(
        default=20.0, ge=0.0, le=100.0, description="Reserva intocável, além da energia de retorno."
    )
    energy_emergency_percent: float = Field(
        default=10.0, ge=0.0, le=100.0, description="Abaixo disso o robô pousa onde estiver."
    )

    # --- HTTP ------------------------------------------------------------------
    cors_origins: str = Field(
        default="http://localhost:5173,http://127.0.0.1:5173",
        description="Origens do frontend, separadas por vírgula. '*' desabilita credenciais.",
    )

    @field_validator("environment")
    @classmethod
    def _known_environment(cls, value: str) -> str:
        allowed = {"development", "staging", "production", "test"}
        if value not in allowed:
            raise ValueError(f"environment deve ser um de {sorted(allowed)}, não {value!r}")
        return value

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def allow_credentials(self) -> bool:
        """``*`` com credenciais é recusado pelos navegadores — e é um erro de segurança."""
        return "*" not in self.cors_origin_list

    @property
    def max_asset_bytes(self) -> int:
        return self.max_asset_mb * 1024 * 1024

    def production_problems(self) -> list[str]:
        """Lista o que impede este processo de ser considerado produção.

        Chamado no ``lifespan``. Em produção a lista vazia é obrigatória; fora
        dela vira aviso no log, para o desenvolvedor saber o que falta.
        """
        problems: list[str] = []
        if self.session_secret == INSECURE_DEFAULT_SECRET:
            problems.append("SESSION_SECRET ainda é o padrão de desenvolvimento.")
        if self.command_signing_secret == INSECURE_DEFAULT_SECRET:
            problems.append("COMMAND_SIGNING_SECRET ainda é o padrão de desenvolvimento.")
        if self.session_secret == self.command_signing_secret:
            problems.append(
                "SESSION_SECRET e COMMAND_SIGNING_SECRET são iguais: vazar a sessão de "
                "um usuário passaria a permitir forjar missão assinada."
            )
        if self.database_url.startswith("sqlite"):
            problems.append("SQLite não suporta a escrita concorrente da ingestão de telemetria.")
        if "*" in self.cors_origin_list:
            problems.append("CORS_ORIGINS com '*' expõe a API a qualquer origem.")
        if self.simulated_inference:
            problems.append(
                "SIMULATED_INFERENCE está ligado: os diagnósticos são inventados."
            )
        return problems


@lru_cache
def get_settings() -> Settings:
    """Instância única, para que o ``.env`` seja lido uma vez só por processo."""
    return Settings()


settings = get_settings()
