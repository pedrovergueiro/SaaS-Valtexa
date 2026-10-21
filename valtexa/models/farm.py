"""Geografia da lavoura: fazenda, talhão e zona.

Os limites são polígonos guardados como JSON — uma lista de pares
``[longitude, latitude]`` em WGS84, sem repetir o primeiro ponto no fim. Não há
PostGIS: as operações de que a plataforma precisa (ponto dentro do polígono,
área, distância) estão em :mod:`valtexa.services.geo`, são determinísticas e
testáveis, e rodam igual em SQLite e em Postgres.

Quando o volume justificar índice espacial, o caminho é migrar a coluna para
``geography(Polygon, 4326)`` mantendo o mesmo contrato de leitura.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from valtexa.models.base import Base, TenantScoped, Timestamped, UUIDPrimaryKey


class Farm(UUIDPrimaryKey, TenantScoped, Timestamped, Base):
    """Uma propriedade. É a unidade que tem base, dock e frota."""

    __tablename__ = "farm"

    name: Mapped[str] = mapped_column(String(160), nullable=False)
    timezone: Mapped[str] = mapped_column(
        String(64), default="America/Sao_Paulo", nullable=False, doc="Fuso para exibição."
    )
    center_lat: Mapped[float] = mapped_column(Float, nullable=False)
    center_lon: Mapped[float] = mapped_column(Float, nullable=False)
    base_lat: Mapped[float | None] = mapped_column(
        Float, doc="Ponto de retorno padrão. Nulo enquanto a base não é instalada."
    )
    base_lon: Mapped[float | None] = mapped_column(Float)
    area_ha: Mapped[float | None] = mapped_column(Float)

    # Identificação da propriedade (brief, seção 5). CPF/CNPJ só com dígitos e CAR
    # normalizado: quem valida é o schema de entrada (services/documentos.py).
    owner_name: Mapped[str | None] = mapped_column(String(160), doc="Proprietário/produtor.")
    owner_document: Mapped[str | None] = mapped_column(String(14), doc="CPF ou CNPJ, só dígitos.")
    city: Mapped[str | None] = mapped_column(String(120))
    state: Mapped[str | None] = mapped_column(String(2), doc="UF.")
    main_crop: Mapped[str | None] = mapped_column(String(64), doc="Cultura principal.")
    car_code: Mapped[str | None] = mapped_column(String(64), doc="Recibo do CAR.")
    technical_lead: Mapped[str | None] = mapped_column(
        String(160), doc="Responsável técnico (agrônomo) e registro."
    )
    notes: Mapped[str | None] = mapped_column(Text, doc="Observações livres da fazenda.")

    fields: Mapped[list[Field]] = relationship(
        back_populates="farm", cascade="all, delete-orphan", passive_deletes=True
    )


class Field(UUIDPrimaryKey, TenantScoped, Timestamped, Base):
    """Um talhão: a menor área com cultura, estágio e histórico próprios."""

    __tablename__ = "field"
    __table_args__ = (UniqueConstraint("farm_id", "name", name="uq_field_farm_name"),)

    farm_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("farm.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    crop: Mapped[str] = mapped_column(
        String(64), nullable=False, doc="Cultura: 'corn', 'coffee', 'soy'. Casa com allowed_crops."
    )
    variety: Mapped[str | None] = mapped_column(String(120))
    ai_model: Mapped[str | None] = mapped_column(
        String(64),
        doc=(
            "Versão do modelo de diagnóstico escolhida para este talhão, ex.: "
            "'banana-foliar-cc' (a comercial). Nulo: PRIMARY_MODELS ou a recomendada."
        ),
    )
    crop_stage: Mapped[str | None] = mapped_column(
        String(64), doc="Estágio fenológico: 'V6', 'VT', 'R3'. Entra na regra de decisão."
    )
    planted_on: Mapped[date | None] = mapped_column(Date)
    cobertura: Mapped[dict | None] = mapped_column(
        doc=(
            "LEGADO (rádio da fazenda, arquivado em 20/10/2026): o mapa de cobertura do "
            "rádio que a base mandava. Ninguém escreve nem lê mais; a coluna fica porque a "
            "migração 0031 já foi aplicada. Ver archive/legacy/radio-fazenda/."
        )
    )
    cobertura_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    row_spacing_m: Mapped[float | None] = mapped_column(Float)
    row_azimuth_deg: Mapped[float | None] = mapped_column(
        Float,
        doc=(
            "Direção das linhas de plantio, em graus a partir do norte, sentido "
            "horário (0 = norte-sul, 90 = leste-oeste). O planejamento alinha as "
            "passadas a ela: o rover anda entre as linhas, não por cima."
        ),
    )
    plant_spacing_m: Mapped[float | None] = mapped_column(
        Float,
        doc=(
            "Espaçamento entre plantas na linha, em metros. Com o entre linhas, é o "
            "que a fusão por planta precisa para não juntar duas plantas numa só (a IA "
            "usa 2,5 m e 4 m fixos quando falta)."
        ),
    )
    row_count: Mapped[int | None] = mapped_column(
        Integer, doc="Número de linhas (ruas de plantio) do talhão."
    )
    validation_rows: Mapped[list] = mapped_column(
        default=list,
        doc=(
            "Fileiras de validação: números das linhas (a partir de 1) em que o agrônomo "
            "rotula **todas** as plantas, para medir detecção e alarme falso no campo."
        ),
    )
    notes: Mapped[str | None] = mapped_column(Text, doc="Observações livres do talhão.")
    area_ha: Mapped[float | None] = mapped_column(Float)
    boundary: Mapped[list] = mapped_column(
        nullable=False,
        default=list,
        doc="Polígono [[lon, lat], ...]. É o limite externo de toda missão neste talhão.",
    )
    terrain: Mapped[dict | None] = mapped_column(
        doc=(
            "A última leitura de imagem deste talhão: frações de cobertura, área "
            "operável e os objetos localizados. Mesma forma do TerrainOut da API. "
            "Fica gravada porque quem a produz e quem a consome estão em telas "
            "diferentes — o encaixe de contorno a calcula, e o planejamento de "
            "missão precisa dela dias depois. Sem persistir, o obstáculo achado "
            "teria que ser reencontrado a cada planejamento, e isso são tiles "
            "baixados de novo, com a questão de licença que vem junto. "
            "É cache de uma heurística, não verdade."
        ),
    )
    terrain_read_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        doc="Quando o terreno foi lido. Uma leitura velha descreve uma lavoura que já mudou.",
    )
    relief: Mapped[dict | None] = mapped_column(
        JSON,
        doc=(
            "O relevo medido deste talhão: desnível, declividade e para onde o "
            "terreno cai. Coluna própria, e não um campo dentro de ``terrain``, "
            "porque as duas medições envelhecem em ritmos muito diferentes: a "
            "cobertura do solo muda a cada safra, a encosta não muda nunca. "
            "Guardá-las juntas faria toda releitura de imagem apagar uma "
            "consulta de DEM que continua válida."
        ),
    )
    relief_read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    farm: Mapped[Farm] = relationship(back_populates="fields")
    zones: Mapped[list[Zone]] = relationship(
        back_populates="field", cascade="all, delete-orphan", passive_deletes=True
    )


class Zone(UUIDPrimaryKey, TenantScoped, Timestamped, Base):
    """Subdivisão de manejo dentro do talhão.

    É onde a aplicação localizada acontece: o motor de decisão recomenda por
    zona, não pelo talhão inteiro, e é isso que separa este produto de uma
    pulverização em área total.
    """

    __tablename__ = "zone"

    field_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("field.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    boundary: Mapped[list] = mapped_column(nullable=False, default=list)
    area_ha: Mapped[float | None] = mapped_column(Float)

    field: Mapped[Field] = relationship(back_populates="zones")
