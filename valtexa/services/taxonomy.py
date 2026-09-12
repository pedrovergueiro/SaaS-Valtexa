"""Em que categoria cai cada rótulo: saudável, doença, praga ou outro achado.

A cópia 3D e o mapa pintam cada observação por categoria, e o produtor olha
primeiro para isso — "tem praga ali?" vem antes de "qual praga?".

Os modelos de hoje classificam doença foliar; o de café reconhece o dano do
bicho-mineiro, que é praga. Praga que o modelo não conhece chega pela fila do
agrônomo: a foto destoa, vai para revisão, e o rótulo que ele escreve —
``Spodoptera_frugiperda``, por exemplo — é o que coloca a lagarta na cópia 3D.
Por isso a lista abaixo inclui pragas que nenhum modelo prevê ainda.

Um rótulo fora das listas vira ``OTHER``. É o lugar certo para "deficiência de
magnésio" ou "granizo": um achado real, que não é doença nem praga. Um rótulo
novo de praga ou doença entra aqui; esquecer de adicioná-lo não esconde nada, só
muda a cor.
"""

from __future__ import annotations

from enum import StrEnum

from valtexa.models.enums import DiagnosisStatus
from valtexa.services.ai_pipeline import HEALTHY_LABELS


class Category(StrEnum):
    HEALTHY = "healthy"
    DISEASE = "disease"
    PEST = "pest"
    REVIEW = "review"
    """A máquina não fechou e o agrônomo ainda não olhou."""

    OTHER = "other"


DISEASE_LABELS = frozenset(
    {
        "Common_Rust",
        "Rust",
        "Blight",
        "Northern_Leaf_Blight",
        "Gray_Leaf_Spot",
        "Cercospora_Leaf_Spot",
        "Phoma_Leaf_Spot",
        "Southern_Rust",
        "Tar_Spot",
    }
)

PEST_LABELS = frozenset(
    {
        # milho
        "Spodoptera_frugiperda",  # lagarta-do-cartucho
        "Dalbulus_maidis",  # cigarrinha-do-milho
        "Helicoverpa_armigera",
        "Diabrotica_speciosa",  # vaquinha
        "Dichelops_melacanthus",  # percevejo barriga-verde
        # soja
        "Euschistus_heros",  # percevejo-marrom
        "Anticarsia_gemmatalis",  # lagarta-da-soja
        # café
        "Leaf_Miner_Damage",  # dano do bicho-mineiro, classe do modelo de café
        "Leucoptera_coffeella",  # bicho-mineiro
        "Hypothenemus_hampei",  # broca-do-café
    }
)

REVIEW_STATUSES = frozenset(
    {DiagnosisStatus.PENDING, DiagnosisStatus.NEEDS_REVIEW, DiagnosisStatus.INCONCLUSIVE}
)


def categorize(label: str | None, status: DiagnosisStatus | None) -> Category:
    """A categoria do diagnóstico que vale para exibição.

    Enquanto o diagnóstico espera o agrônomo, a categoria é ``REVIEW`` mesmo que
    a máquina tenha arriscado um rótulo: mostrar "doença" ali seria dar ao
    palpite que a dupla validação recusou o peso de um diagnóstico.
    """
    if status is None or status in REVIEW_STATUSES or not label:
        return Category.REVIEW
    if label in HEALTHY_LABELS:
        return Category.HEALTHY
    if label in PEST_LABELS:
        return Category.PEST
    if label in DISEASE_LABELS:
        return Category.DISEASE
    return Category.OTHER
