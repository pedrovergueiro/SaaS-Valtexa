"""O agrônomo ensinando a IA: cada lição, com o porquê e onde está a lesão.

Uma tabela, ``licao_agronomo``. Uma lição nasce quando o agrônomo diz o que a planta tem e,
se quiser, **por quê** — os sintomas que viu, o terço da planta, a face da folha, o texto dele
— e **onde** — as lesões marcadas na foto. Duas origens:

* ``fila`` — o veredito na fila de revisão (o mesmo que vira amostra do dataset);
* ``parecer`` — a discordância dele com um parecer do cérebro agronômico.

O que a lição alimenta: o treino (a exportação do corte do dataset leva as lesões, e o
``training.import_licoes`` da IA recorta cada uma), os pareceres seguintes do talhão (que
citam o que ele ensinou) e o painel "o que a IA aprendeu com você". **Imutável**: corrigir é
ensinar de novo; a anterior fica, com data e autor. Sai do treino com o consentimento do
cliente (o corte do dataset confere) e pode ser apagada a pedido (LGPD) pelo id.
"""

from __future__ import annotations

from sqlalchemy import ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from valtexa.models.base import Base, TenantScoped, Timestamped, UUIDPrimaryKey


class LicaoAgronomo(UUIDPrimaryKey, TenantScoped, Timestamped, Base):
    __tablename__ = "licao_agronomo"
    __table_args__ = (
        Index("ix_licao_agronomo_field_rotulo", "field_id", "rotulo"),
        Index("ix_licao_agronomo_autor", "autor_id"),
    )

    field_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("field.id", ondelete="CASCADE"), nullable=False
    )
    origem: Mapped[str] = mapped_column(String(16), nullable=False, doc="fila | parecer")
    observation_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("observation.id", ondelete="SET NULL"), index=True
    )
    diagnosis_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("diagnosis.id", ondelete="SET NULL"), index=True
    )
    parecer_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("parecer.id", ondelete="SET NULL")
    )
    plant_ref: Mapped[str | None] = mapped_column(String(80))
    autor_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("user.id", ondelete="SET NULL")
    )
    autor_rotulo: Mapped[str] = mapped_column(
        String(255), nullable=False, doc="Nome do agrônomo na hora: sobrevive à conta apagada."
    )
    rotulo: Mapped[str] = mapped_column(String(120), nullable=False, doc="O que a planta tem.")
    rotulo_da_ia: Mapped[str | None] = mapped_column(String(120), doc="O que a IA dizia.")
    sintomas: Mapped[list] = mapped_column(default=list, doc="Os sintomas que ele viu.")
    estrato: Mapped[str | None] = mapped_column(String(24), doc="Terço da planta.")
    face: Mapped[str | None] = mapped_column(String(16), doc="Face da folha.")
    porque: Mapped[str | None] = mapped_column(Text, doc="O porquê, nas palavras dele.")
    lesoes: Mapped[list] = mapped_column(
        default=list, doc="Caixas [x, y, w, h] na foto, normalizadas em [0, 1]."
    )


class OpiniaoAmostra(UUIDPrimaryKey, Timestamped, Base):
    """A segunda opinião sobre uma amostra do dataset: outro agrônomo (do cliente ou da
    ValTexa) olha a foto e diz o que a planta tem. É o que permite congelar um corte só com o
    que dois concordaram, e medir a confiabilidade de cada um (concordância com os colegas)."""

    __tablename__ = "opiniao_amostra"
    __table_args__ = (
        UniqueConstraint("dataset_sample_id", "revisor_id", name="uq_opiniao_amostra_revisor"),
    )

    dataset_sample_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("dataset_sample.id", ondelete="CASCADE"), nullable=False,
        index=True)
    revisor_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("user.id", ondelete="SET NULL"), index=True)
    revisor_rotulo: Mapped[str] = mapped_column(String(255), nullable=False)
    origem: Mapped[str] = mapped_column(String(16), nullable=False, doc="cliente | plataforma")
    rotulo: Mapped[str] = mapped_column(String(120), nullable=False)
    concorda: Mapped[bool] = mapped_column(nullable=False, doc="Mesmo rótulo da amostra.")
    comentario: Mapped[str | None] = mapped_column(Text)


class RegraAgronomo(UUIDPrimaryKey, TenantScoped, Timestamped, Base):
    """O que o agrônomo sabe, escrito como regra que se pode medir: "bicho-mineiro sobe na
    seca" vira *chuva acumulada em 14 dias < 10 mm aumenta Leaf_Miner_Damage*. A plataforma
    mede no histórico do cliente (:func:`valtexa.services.ensino.medir_regra`) e o parecer cita
    a regra com o veredito da medida — nunca como fato só porque alguém escreveu."""

    __tablename__ = "regra_agronomo"

    autor_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("user.id", ondelete="SET NULL"), index=True)
    autor_rotulo: Mapped[str] = mapped_column(String(255), nullable=False)
    cultura: Mapped[str] = mapped_column(String(64), nullable=False)
    doenca: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    texto: Mapped[str] = mapped_column(Text, nullable=False, doc="A regra nas palavras dele.")
    condicao: Mapped[dict] = mapped_column(
        default=dict, doc="{variavel, janela_dias, operador, valor} ou {variavel: mes, meses}.")
    efeito: Mapped[str] = mapped_column(String(16), nullable=False, doc="aumenta | diminui")
    ativa: Mapped[bool] = mapped_column(default=True, nullable=False)
    medida: Mapped[dict] = mapped_column(default=dict, doc="O resultado da última medida.")
