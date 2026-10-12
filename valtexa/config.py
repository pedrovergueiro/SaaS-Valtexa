"""Configuração da plataforma, lida do ambiente.

Tudo que muda entre desenvolvimento, homologação e produção passa por aqui. Os
padrões foram escolhidos para que ``uvicorn valtexa.main:app`` suba um ambiente
completo e funcional sem nenhuma variável definida — mas os segredos têm padrão
inseguro de propósito, e :func:`Settings.production_problems` recusa subir em
produção enquanto eles não forem trocados.
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent

INSECURE_DEFAULT_SECRET = "dev-only-change-me"
"""Valor sentinela dos segredos. Serve para o ambiente local e é recusado em produção."""

MIN_SECRET_CHARS = 32
"""Tamanho mínimo de segredo em produção (``openssl rand -base64 48`` dá 64)."""

_PLACEHOLDERS = ("change-me", "changeme", "troque", "secret", "senha", "password", "xxx")
"""Trechos que denunciam valor de exemplo copiado do ``.env.example``."""


def _secrets_dir() -> str | None:
    """Pasta de segredos montados como arquivo (Docker/Kubernetes secrets).

    ``SECRETS_DIR`` explícito, ou ``/run/secrets`` quando existe. Cada arquivo tem o
    nome do campo em minúsculas (``session_secret``) e o conteúdo é o valor; a
    variável de ambiente, se houver, vence o arquivo.
    """
    explicito = os.environ.get("SECRETS_DIR")
    if explicito:
        return explicito
    return "/run/secrets" if Path("/run/secrets").is_dir() else None


class Settings(BaseSettings):
    """Parâmetros de execução da plataforma."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", frozen=True,
        secrets_dir=_secrets_dir(),
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
    max_asset_mb: int = Field(
        default=64,
        ge=1,
        description=(
            "Limite por arquivo **já montado**, no armazenamento de objetos. Não é o "
            "limite de uma coleta: o lote inteiro sobe em pedaços e o teto dele é o do "
            "armazenamento contratado. Suba este número para aceitar ortomosaico."
        ),
    )
    upload_staging_dir: Path | None = Field(
        default=None,
        description=(
            "Só com STORAGE_BACKEND=local: onde os pedaços de um upload de coleta se "
            "acumulam até o arquivo fechar. Vazio usa STORAGE_DIR/_upload. Com "
            "STORAGE_BACKEND=s3 os pedaços (de coleta e do Rover) vão para o bucket, sob "
            "_staging/, e qualquer réplica da API recebe qualquer pedaço (Parte 9)."
        ),
    )
    storage_backend: str = Field(
        default="local", description="'local' (disco em STORAGE_DIR) ou 's3' (S3, MinIO, R2)."
    )
    s3_bucket: str | None = Field(default=None, description="Bucket, quando STORAGE_BACKEND=s3.")
    s3_prefix: str = Field(default="valtexa", description="Prefixo dentro do bucket.")
    s3_endpoint_url: str | None = Field(
        default=None, description="Endpoint compatível com S3 (MinIO, R2). Vazio usa a AWS."
    )
    s3_region: str | None = None
    s3_addressing_style: str = Field(
        default="auto", description="'auto', 'path' (MinIO) ou 'virtual'."
    )
    s3_presign_seconds: int = Field(
        default=300, ge=30, le=3600,
        description=(
            "Validade da URL assinada que a API entrega ao cliente para baixar uma imagem "
            "direto do bucket (só com STORAGE_BACKEND=s3). Curta de propósito: quem tem o "
            "endereço baixa sem login até ela vencer."
        ),
    )
    s3_multipart_threshold_mb: int = Field(
        default=8, ge=5,
        description="Objeto maior que isto sobe em multipart (partes de 8 MB; o S3 exige ≥ 5).",
    )
    s3_staging_days: int = Field(
        default=3, ge=1,
        description="Lifecycle: chunk de upload esquecido no bucket é apagado depois disto.",
    )
    s3_infrequent_after_days: int | None = Field(
        default=30, ge=30,
        description="Lifecycle: imagem e nuvem de pontos vão para STANDARD_IA depois disto.",
    )
    s3_archive_after_days: int | None = Field(
        default=365, ge=90,
        description="Lifecycle: imagem e nuvem de pontos vão para GLACIER_IR depois disto.",
    )
    s3_logs_expire_days: int | None = Field(
        default=None, ge=30,
        description=(
            "Lifecycle: arquivos de log/JSON do robô expiram depois disto. Vazio = nunca "
            "(apagar dado do cliente é decisão de contrato, não padrão do código)."
        ),
    )
    redis_url: str | None = Field(
        default=None,
        description=(
            "Redis compartilhado pelas réplicas (limite de taxa dos robôs e travas do "
            "worker). Vazio: em memória, por processo — só serve com uma réplica."
        ),
    )

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
    upload_ttl_hours: float = Field(
        default=72.0, gt=0,
        description="Upload parado há mais que isto é abandonado: o worker apaga os chunks.",
    )
    device_rate_per_minute: int = Field(
        default=1200, ge=10,
        description=(
            "Requisições por minuto que um robô pode fazer nas rotas de sincronização "
            "(registros, uploads, chunks). Acima disso: 429 com Retry-After — o Rover "
            "espera com backoff. Compartilhado entre réplicas com REDIS_URL; sem ele, "
            "por processo (com várias réplicas, multiplica)."
        ),
    )
    ota_signing_secret: str | None = Field(
        default=None,
        description=(
            "Assina os pacotes de atualização (OTA) enviados aos robôs. Separada da "
            "chave das missões para poder morar noutro cofre (ou na esteira de build). "
            "Sem ela, usa a das missões — aceitável em desenvolvimento, não em produção."
        ),
    )
    command_signing_key_id: str = Field(
        default="k1", description="Identificador da chave, para permitir rotação sem downtime."
    )
    platform_admin_password: str | None = Field(
        default=None,
        description=(
            "Senha inicial das contas da equipe da ValTexa (ver PLATFORM_TEAM em "
            "valtexa/seed.py). Vazio não cria conta nenhuma — é por isso que não "
            "há padrão: uma senha de administrador de plataforma escrita no código "
            "seria a mesma em toda instalação. Definida uma vez, no ambiente; o "
            "seed não sobrescreve quem já existe, então trocá-la depois se faz "
            "pelo próprio console."
        ),
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
    login_window_seconds: int = Field(
        default=900, ge=60, description="Janela em que as falhas de login são contadas."
    )
    login_max_failures_per_email: int = Field(
        default=5,
        ge=1,
        description="Falhas seguidas numa conta, na janela, antes de recusar novas tentativas.",
    )
    login_max_failures_per_ip: int = Field(
        default=30,
        ge=1,
        description="Falhas vindas de um mesmo endereço, na janela, em contas quaisquer.",
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
    inference_service_token: str | None = Field(
        default=None,
        description=(
            "Token de serviço que o SaaS manda à IA (Authorization: Bearer). Precisa "
            "ser igual ao SERVICE_TOKEN do servidor de IA. Obrigatório em produção."
        ),
    )

    def inference_headers(self) -> dict[str, str]:
        """Cabeçalhos de toda chamada do SaaS à IA."""
        if not self.inference_service_token:
            return {}
        return {"Authorization": f"Bearer {self.inference_service_token}"}

    # --- relevo ----------------------------------------------------------------
    elevation_url: str | None = Field(
        default=None,
        description=(
            "Serviço de elevação (DEM) no formato OpenTopoData/Open-Elevation: "
            "responde a ?locations=lat,lon|... com {'results':[{'elevation':...}]}. "
            "Vazio de propósito: sem fonte contratada, o planejamento trata o "
            "talhão como plano — e diz isso, em vez de devolver zero como se "
            "fosse medição."
        ),
    )
    elevation_timeout_seconds: float = Field(default=30.0, gt=0)

    # --- localizar a fazenda (endereço → mapa) -----------------------------------
    google_maps_api_key: str | None = Field(
        default=None,
        description=(
            "Chave do Google do SERVIDOR (Geocoding API), restrita por IP. Só é usada "
            "junto com GOOGLE_MAPS_TILES_KEY: o resultado do Google só pode aparecer "
            "sobre mapa do Google. Ver valtexa/services/localizar.py."
        ),
    )
    google_maps_tiles_key: str | None = Field(
        default=None,
        description=(
            "Chave do Google do NAVEGADOR (Map Tiles API: satélite no console), restrita "
            "por referenciador. Vai para o navegador de quem está logado."
        ),
    )
    geocoder_osm_url: str = Field(
        default="https://nominatim.openstreetmap.org",
        description="Nominatim (OpenStreetMap) quando o Google não está ligado. Vazio desliga.",
    )
    geocoder_user_agent: str = Field(
        default="ValTexa-Plataforma/1.0",
        description="A política do Nominatim exige que quem pergunta se identifique.",
    )
    geocoder_timeout_seconds: float = Field(default=8.0, gt=0)

    # --- fluxo ao vivo ---------------------------------------------------------
    stream_poll_seconds: float = Field(
        default=1.0,
        ge=0.2,
        le=10.0,
        description=(
            "De quanto em quanto tempo o fluxo SSE procura evento novo. É o teto "
            "da latência que o console mostra."
        ),
    )
    stream_max_seconds: int = Field(
        default=300,
        ge=30,
        description=(
            "Duração máxima de uma conexão ao vivo antes de o servidor pedir "
            "reconexão. Recicla aba esquecida em vez de segurar recurso para "
            "sempre, e é o padrão que docs/API.md promete ao cliente."
        ),
    )
    stream_max_clients: int = Field(
        default=200,
        ge=1,
        description=(
            "Conexões ao vivo simultâneas por réplica. Estourar devolve 503, que "
            "é melhor do que aceitar e ficar lento para todo mundo."
        ),
    )
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

    primary_models: str = Field(
        default="",
        description=(
            "Versão do modelo por cultura, 'cultura:modelo' separados por vírgula. "
            "Ex.: 'banana:banana-foliar-cc' põe a banana na versão comercial. "
            "O talhão (Field.ai_model) tem precedência; sem nenhum dos dois, vale "
            "a versão recomendada do catálogo."
        ),
    )

    secondary_models: str = Field(
        default="",
        description=(
            "Segundo analisador por cultura, 'cultura:modelo' separados por vírgula. "
            "Ex.: 'corn:leaf-foliar-b'. Cultura fora da lista fica com um analisador só."
        ),
    )
    secondary_model_independent: bool = Field(
        default=False,
        description=(
            "Se a concordância com o segundo modelo conta como validação independente. "
            "Falso por padrão: ver a medição em docs/AI_PIPELINE.md antes de ligar."
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

    # --- notificações (seção 48) -----------------------------------------------
    # Sem SMTP_HOST o e-mail não sai: a entrega fica 'nao_enviado', com o motivo,
    # e o aviso continua na central do console. Nada finge que mandou.
    smtp_host: str | None = Field(default=None, description="Servidor SMTP do e-mail.")
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_user: str | None = Field(default=None)
    smtp_password: str | None = Field(default=None, description="Vem do ambiente, nunca do código.")
    smtp_from: str = Field(
        default="ValTexa <nao-responda@valtexa.com.br>", description="Remetente dos avisos."
    )
    smtp_starttls: bool = Field(default=True, description="STARTTLS depois do EHLO (porta 587).")
    smtp_ssl: bool = Field(default=False, description="TLS desde a conexão (porta 465).")
    smtp_timeout_seconds: float = Field(default=15.0, gt=0)
    console_url: str | None = Field(
        default=None,
        description="Endereço público do console, para o link no e-mail ('https://app...').",
    )

    # --- observabilidade (seções 34 e 35) ---------------------------------------
    log_format: str = Field(
        default="texto",
        description="'texto' (terminal) ou 'json' (uma linha JSON por registro, com "
                    "request_id, cliente e usuário — para Loki/CloudWatch/Elastic).",
    )
    metrics_token: str | None = Field(
        default=None,
        description=(
            "Token que o Prometheus manda em /metrics (Authorization: Bearer). Vem do "
            "ambiente. Sem ele, só a equipe da ValTexa logada lê /metrics."
        ),
    )
    metrics_flush_seconds: float = Field(
        default=30.0, gt=0, description="De quanto em quanto a API grava a estatística por minuto."
    )
    api_metrics_retention_days: int = Field(
        default=7, ge=1, description="Estatística da API por minuto guardada por estes dias."
    )
    alerts_every_seconds: float = Field(
        default=60.0, ge=5, description="De quanto em quanto o worker avalia as regras de alerta."
    )

    # --- processos -------------------------------------------------------------
    event_worker_in_api: bool = Field(
        default=True,
        description=(
            "Roda o worker de fundo como thread da API. Com várias réplicas, desligue "
            "e rode 'python -m valtexa.worker' num processo único."
        ),
    )
    telemetry_retention_days: int = Field(
        default=90, ge=1, description="Depois disso a telemetria crua vira agregado por minuto."
    )
    serve_web: bool = Field(
        default=True, description="Serve o console (web/dist) na raiz quando o build existir."
    )

    # --- HTTP ------------------------------------------------------------------
    cors_origins: str = Field(
        default="http://localhost:5173,http://127.0.0.1:5173",
        description="Origens do frontend, separadas por vírgula. '*' desabilita credenciais.",
    )

    @field_validator("s3_infrequent_after_days", "s3_archive_after_days",
                     "s3_logs_expire_days", "redis_url", mode="before")
    @classmethod
    def _vazio_e_nenhum(cls, value: object) -> object:
        """Variável definida e vazia (``S3_ARCHIVE_AFTER_DAYS=``) desliga, em vez de quebrar."""
        return None if isinstance(value, str) and not value.strip() else value

    @field_validator("log_format")
    @classmethod
    def _known_log_format(cls, value: str) -> str:
        if value not in ("texto", "json"):
            raise ValueError("log_format deve ser 'texto' ou 'json'")
        return value

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

    @field_validator("storage_backend")
    @classmethod
    def _known_backend(cls, value: str) -> str:
        if value not in {"local", "s3"}:
            raise ValueError(f"storage_backend deve ser 'local' ou 's3', não {value!r}")
        return value

    @property
    def max_asset_bytes(self) -> int:
        return self.max_asset_mb * 1024 * 1024

    @property
    def primary_model_map(self) -> dict[str, str]:
        """``PRIMARY_MODELS`` como dicionário ``{cultura: modelo}``."""
        return _crop_model_map(self.primary_models)

    @property
    def secondary_model_map(self) -> dict[str, str]:
        """``SECONDARY_MODELS`` como dicionário ``{cultura: modelo}``."""
        pairs: dict[str, str] = {}
        for item in self.secondary_models.split(","):
            if ":" not in item:
                continue
            crop, model = (part.strip() for part in item.split(":", 1))
            if crop and model:
                pairs[crop.lower()] = model
        return pairs

    def secret_problems(self) -> list[str]:
        """Os segredos (seção 36): presentes, fortes e **distintos entre si**.

        Quatro chaves com papéis diferentes — sessão, comando ao robô, pacote OTA e
        token de serviço da IA. Iguais, vazar uma (o token da IA, que mora noutro
        servidor) entregaria as outras (forjar missão assinada ou atualização).
        """
        problems: list[str] = []
        segredos = {
            "SESSION_SECRET": self.session_secret,
            "COMMAND_SIGNING_SECRET": self.command_signing_secret,
            "OTA_SIGNING_SECRET": self.ota_signing_secret,
            "INFERENCE_SERVICE_TOKEN": self.inference_service_token,
        }
        for nome, valor in segredos.items():
            if not valor or not valor.strip():
                problems.append(f"{nome} está vazio.")
            elif valor == INSECURE_DEFAULT_SECRET:
                problems.append(f"{nome} ainda é o padrão de desenvolvimento.")
            elif len(valor) < MIN_SECRET_CHARS:
                problems.append(
                    f"{nome} tem {len(valor)} caracteres: o mínimo é {MIN_SECRET_CHARS} "
                    "(gere com 'openssl rand -base64 48')."
                )
            elif any(p in valor.lower() for p in _PLACEHOLDERS):
                problems.append(f"{nome} parece valor de exemplo (contém palavra de modelo).")
        nomes = list(segredos)
        for a_i, a in enumerate(nomes):
            for b in nomes[a_i + 1:]:
                if segredos[a] and segredos[a] == segredos[b]:
                    problems.append(
                        f"{a} e {b} são iguais: cada segredo precisa ser próprio — vazar "
                        "um não pode entregar o outro."
                    )
        if self.metrics_token and self.metrics_token in segredos.values():
            problems.append("METRICS_TOKEN igual a outro segredo: o Prometheus o guarda em "
                            "arquivo, fora do cofre.")
        return problems

    def production_problems(self) -> list[str]:
        """Lista o que impede este processo de ser considerado produção.

        Chamado no ``lifespan`` da API e na subida do worker
        (:func:`recusar_se_inadequado`). Em produção a lista vazia é obrigatória;
        fora dela vira aviso no log, para o desenvolvedor saber o que falta.
        """
        problems: list[str] = self.secret_problems()
        if self.database_url.startswith("sqlite"):
            problems.append("SQLite não suporta a escrita concorrente da ingestão de telemetria.")
        if "*" in self.cors_origin_list:
            problems.append("CORS_ORIGINS com '*' expõe a API a qualquer origem.")
        if self.storage_backend == "s3" and not self.s3_bucket:
            problems.append("STORAGE_BACKEND=s3 sem S3_BUCKET.")
        if self.simulated_inference:
            problems.append(
                "SIMULATED_INFERENCE está ligado: os diagnósticos são inventados."
            )
        if not self.redis_url:
            problems.append(
                "REDIS_URL vazio: limite de taxa dos robôs e travas do worker ficam por "
                "processo — com mais de uma réplica, o limite multiplica e o worker duplica."
            )
        return problems


@lru_cache
def _crop_model_map(raw: str) -> dict[str, str]:
    """``'cultura:modelo, ...'`` como dicionário; entradas sem os dois lados são ignoradas."""
    pairs: dict[str, str] = {}
    for item in raw.split(","):
        if ":" not in item:
            continue
        crop, model = (part.strip() for part in item.split(":", 1))
        if crop and model:
            pairs[crop.lower()] = model
    return pairs


def recusar_se_inadequado(config: Settings, logger: logging.Logger) -> None:
    """Em produção, recusa subir com pendência; fora dela, registra cada uma como aviso."""
    problems = config.production_problems()
    if not problems:
        return
    if config.is_production:
        # Em produção isso não é aviso: é impedimento. Subir assim colocaria
        # no ar um sistema que assina comandos com um segredo público.
        raise RuntimeError(
            "Configuração inadequada para produção:\n  - " + "\n  - ".join(problems)
        )
    for problem in problems:
        logger.warning("Pendência para produção: %s", problem)


def get_settings() -> Settings:
    """Instância única, para que o ``.env`` seja lido uma vez só por processo."""
    return Settings()


settings = get_settings()
