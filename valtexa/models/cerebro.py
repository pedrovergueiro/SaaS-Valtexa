"""Cérebro agronômico (8.1, 8.2): fontes de conhecimento versionadas e pareceres.

Quatro tabelas, nenhuma muda o que já existe:

* ``documento_conhecimento`` — um documento **numa versão** (bula, registro MAPA, Embrapa,
  escala diagramática, artigo, histórico da propriedade, gêmeo/FieldHistory), com origem,
  datas, ``verificado_em``, ``valido_ate``, ``sha256`` do conteúdo e licença. ``tenant_id``
  nulo = fonte da plataforma (a equipe da ValTexa ingere, todo cliente lê); preenchido =
  fonte daquele cliente (o histórico da propriedade dele), que só ele lê. Uma versão nova
  do mesmo documento (mesma ``chave``) é outra linha; a anterior fica ``substituido``.
* ``trecho_conhecimento`` — os pedaços que a recuperação (RAG) devolve e que o parecer cita;
  ``inicio``/``fim`` apontam para o conteúdo do documento, e o ``sha256`` do trecho prova
  que a citação é a mesma que estava lá.
* ``parecer`` — o parecer gerado para um caso (planta ou observação). **Imutável**: o
  dossiê de evidências, as afirmações com as citações, as verificações pendentes e o texto
  ficam como saíram, com o ``sha256``. Gerar de novo cria outro parecer.
* ``revisao_parecer`` — o que o agrônomo achou do parecer (quem, quando, decisão,
  comentário). **Não autoriza nada**: nenhuma revisão cria missão, aprova prescrição ou
  aplicação (Princípio de Ouro, ``docs/CEREBRO.md``).
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, declared_attr, mapped_column

from valtexa.models.base import Base, TenantScoped, Timestamped, UUIDPrimaryKey

TIPOS_DOCUMENTO = (
    "bula",
    "registro_mapa",
    "embrapa",
    "escala_diagramatica",
    "artigo",
    "historico_propriedade",
    "gemeo",
)
"""Os tipos de fonte do 8.1. ``bula`` e ``registro_mapa`` são **regulatórios**."""

TIPOS_REGULATORIOS = frozenset({"bula", "registro_mapa"})
"""Vencido ou não verificado bloqueia o uso em recomendação operacional."""

ESTADOS_DOCUMENTO = ("vigente", "substituido", "retirado")

DECISOES_REVISAO = ("concorda", "discorda", "inconclusivo")
"""``inconclusivo``: o agrônomo pede mais evidência antes de concordar ou discordar."""


class DocumentoConhecimento(UUIDPrimaryKey, Timestamped, Base):
    __tablename__ = "documento_conhecimento"
    __table_args__ = (
        Index("ix_documento_conhecimento_chave", "chave", "versao"),
        Index("ix_documento_conhecimento_tipo_estado", "tipo", "estado"),
    )

    @declared_attr
    @classmethod
    def tenant_id(cls) -> Mapped[str | None]:
        # Nulo de propósito: a fonte da plataforma (bula, Embrapa) vale para todo cliente.
        return mapped_column(
            String(32), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=True, index=True
        )

    chave: Mapped[str] = mapped_column(
        String(120), nullable=False,
        doc="Identificador estável do documento entre versões (ex.: embrapa:ferrugem-cafe).",
    )
    versao: Mapped[str] = mapped_column(String(40), nullable=False)
    titulo: Mapped[str] = mapped_column(String(300), nullable=False)
    tipo: Mapped[str] = mapped_column(String(32), nullable=False)
    origem: Mapped[str] = mapped_column(
        String(500), nullable=False, doc="Quem publica e onde (instituição, URL, referência)."
    )
    publicado_em: Mapped[date | None] = mapped_column(Date)
    verificado_em: Mapped[date | None] = mapped_column(
        Date, doc="Quando alguém conferiu esta versão contra a fonte oficial."
    )
    verificado_por: Mapped[str | None] = mapped_column(String(32), ForeignKey("user.id"))
    valido_ate: Mapped[date | None] = mapped_column(
        Date, doc="Até quando a verificação vale. Regulatório sem data não é usado na operação."
    )
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    licenca: Mapped[str] = mapped_column(String(200), nullable=False)
    culturas: Mapped[list] = mapped_column(default=list)
    alvos: Mapped[list] = mapped_column(
        default=list, doc="Doenças/pragas de que o documento trata (rótulo ou nome)."
    )
    ficticio: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False,
        doc="Dado de exemplo, só para teste: nunca vale na operação, recusado em produção.",
    )
    estado: Mapped[str] = mapped_column(String(16), nullable=False, default="vigente")
    substituido_por: Mapped[str | None] = mapped_column(String(32))
    formato: Mapped[str] = mapped_column(String(16), nullable=False, default="texto")
    arquivo_nome: Mapped[str | None] = mapped_column(String(255))
    conteudo: Mapped[str] = mapped_column(Text, nullable=False)
    ingerido_por: Mapped[str | None] = mapped_column(String(32), ForeignKey("user.id"))


class TrechoConhecimento(UUIDPrimaryKey, Base):
    __tablename__ = "trecho_conhecimento"

    documento_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("documento_conhecimento.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    tenant_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("tenant.id", ondelete="CASCADE"), index=True,
        doc="Cópia do documento: a busca filtra sem juntar tabelas.",
    )
    ordem: Mapped[int] = mapped_column(Integer, nullable=False)
    secao: Mapped[str | None] = mapped_column(String(300))
    texto: Mapped[str] = mapped_column(Text, nullable=False)
    inicio: Mapped[int] = mapped_column(Integer, nullable=False)
    fim: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)


class Parecer(UUIDPrimaryKey, TenantScoped, Timestamped, Base):
    __tablename__ = "parecer"
    __table_args__ = (Index("ix_parecer_field_planta", "field_id", "plant_ref"),)

    field_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("field.id", ondelete="CASCADE"), nullable=False
    )
    caso_tipo: Mapped[str] = mapped_column(String(16), nullable=False, doc="planta | observacao")
    plant_ref: Mapped[str | None] = mapped_column(String(80))
    observation_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("observation.id", ondelete="SET NULL"), index=True
    )
    modo: Mapped[str] = mapped_column(
        String(16), nullable=False, doc="deterministico | provedor (texto validado)."
    )
    provedor: Mapped[str | None] = mapped_column(String(64))
    versao_compositor: Mapped[str] = mapped_column(String(32), nullable=False)
    dossie: Mapped[dict] = mapped_column(default=dict)
    dossie_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    fontes: Mapped[list] = mapped_column(default=list)
    afirmacoes: Mapped[list] = mapped_column(default=list)
    verificacoes: Mapped[list] = mapped_column(default=list)
    recusas: Mapped[list] = mapped_column(
        default=list, doc="O que o validador recusou do texto do provedor (e por quê)."
    )
    texto: Mapped[str] = mapped_column(Text, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    estado: Mapped[str] = mapped_column(String(24), nullable=False, default="aguardando_revisao")
    gerado_por: Mapped[str | None] = mapped_column(String(32), ForeignKey("user.id"))


class RevisaoParecer(UUIDPrimaryKey, TenantScoped, Timestamped, Base):
    __tablename__ = "revisao_parecer"

    parecer_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("parecer.id", ondelete="CASCADE"), nullable=False, index=True
    )
    revisor_id: Mapped[str] = mapped_column(String(32), ForeignKey("user.id"), nullable=False)
    papel: Mapped[str] = mapped_column(String(24), nullable=False)
    decisao: Mapped[str] = mapped_column(String(16), nullable=False)
    comentario: Mapped[str | None] = mapped_column(Text)
    diagnostico_revisor: Mapped[str | None] = mapped_column(
        String(80), doc="O que o agrônomo acha que a planta tem, se discordou do parecer."
    )
    parecer_sha256: Mapped[str] = mapped_column(
        String(64), nullable=False, doc="O parecer exatamente como foi revisado."
    )
    revisado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
