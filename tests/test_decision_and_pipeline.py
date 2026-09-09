"""Dupla validação e motor de decisão.

O tema destes testes é um só: **o que impede um palpite de virar aplicação**.
A limitação está medida em ``VALTEXA-B/MODELS.md`` — diante de uma doença fora
do catálogo, o modelo responde com 0,88 de confiança média e os filtros pegam
19%. As regras testadas aqui são as barreiras construídas em cima disso.
"""

from __future__ import annotations

import pytest

from valtexa.models import Agreement, DecisionOutcome, DiagnosisStatus
from valtexa.services import ai_pipeline as pipeline
from valtexa.services import decision_engine as engine


def analysis(
    name: str = "a", label: str = "Common_Rust", confidence: float = 0.95, **extra: object
) -> pipeline.Analysis:
    return pipeline.Analysis(analyzer=name, label=label, confidence=confidence, **extra)


class TestPipelineCombination:
    """A regra que decide se um diagnóstico está fechado."""

    def test_duas_concordando_validam(self) -> None:
        outcome = pipeline.combine([analysis("a"), analysis("b")])
        assert outcome.status is DiagnosisStatus.AI_VALIDATED
        assert outcome.agreement is Agreement.AGREE

    def test_uma_analise_sozinha_nunca_valida(self) -> None:
        """Uma opinião isolada não é dupla validação, por mais confiante que seja."""
        outcome = pipeline.combine([analysis("a", confidence=0.999)])
        assert outcome.status is DiagnosisStatus.NEEDS_REVIEW
        assert outcome.agreement is Agreement.UNAVAILABLE

    def test_nenhuma_analise_e_inconclusivo(self) -> None:
        outcome = pipeline.combine([])
        assert outcome.status is DiagnosisStatus.INCONCLUSIVE

    def test_analisador_que_falhou_nao_conta_como_concordancia(self) -> None:
        """Erro de rede não pode virar 'os dois concordaram'."""
        quebrado = pipeline.Analysis(
            analyzer="b", label=None, confidence=None, error="Timeout"
        )
        outcome = pipeline.combine([analysis("a"), quebrado])
        assert outcome.status is DiagnosisStatus.NEEDS_REVIEW
        assert outcome.agreement is Agreement.UNAVAILABLE

    def test_rotulos_diferentes_vao_para_o_agronomo(self) -> None:
        outcome = pipeline.combine([analysis("a", label="Blight"), analysis("b", label="Healthy")])
        assert outcome.status is DiagnosisStatus.NEEDS_REVIEW
        assert outcome.agreement is Agreement.DISAGREE

    def test_confianca_baixa_e_inconclusiva(self) -> None:
        outcome = pipeline.combine([analysis("a", confidence=0.95), analysis("b", confidence=0.3)])
        assert outcome.status is DiagnosisStatus.INCONCLUSIVE
        assert outcome.agreement is Agreement.ABSTAIN

    def test_novidade_vence_a_concordancia(self) -> None:
        """As duas podem concordar e ainda assim estar diante de algo novo.

        É exatamente o caso medido: uma doença fora do catálogo classificada com
        confiança alta e consistente. A concordância não redime.
        """
        outcome = pipeline.combine(
            [analysis("a", novelty_score=2.5), analysis("b", novelty_score=2.4)]
        )
        assert outcome.status is DiagnosisStatus.NEEDS_REVIEW
        assert "Novidade" in outcome.rationale

    def test_concordancia_fragil_vai_para_revisao(self) -> None:
        """Mesmo rótulo com confianças distantes é acordo frouxo, não validação."""
        outcome = pipeline.combine([analysis("a", confidence=0.99), analysis("b", confidence=0.72)])
        assert outcome.status is DiagnosisStatus.NEEDS_REVIEW

    def test_a_confianca_reportada_e_a_menor_do_par(self) -> None:
        """Reportar a maior apagaria justamente a dúvida que a segunda revelou."""
        outcome = pipeline.combine([analysis("a", confidence=0.98), analysis("b", confidence=0.90)])
        assert outcome.confidence == pytest.approx(0.90)

    def test_par_dependente_e_marcado(self) -> None:
        outcome = pipeline.combine([analysis("a"), analysis("dependent:tta")])
        assert not outcome.independent_pair
        assert "não é independente" in outcome.rationale

    def test_cultura_sem_modelo_e_recusada(self) -> None:
        """Classificar soja com o modelo de milho devolveria uma classe de milho."""
        with pytest.raises(pipeline.AnalyzerUnavailableError, match="soja"):
            pipeline.model_for_crop("soja")

    def test_culturas_atendidas_resolvem(self) -> None:
        assert pipeline.model_for_crop("corn") == "leaf-foliar"
        assert pipeline.model_for_crop("coffee") == "coffee-foliar"


def context(**overrides: object) -> engine.DecisionContext:
    """Contexto que resultaria em recomendação de aplicação. Cada teste quebra um campo."""
    base = {
        "label": "Common_Rust",
        "confidence": 0.95,
        "status": DiagnosisStatus.AI_VALIDATED.value,
        "novelty_score": 0.3,
        "independent_pair": True,
        "crop": "corn",
        "crop_stage": "V8",
        "sample_size": 40,
        "affected_ratio": 0.35,
        "zone_area_ha": 2.0,
        "available_product_id": "prod-1",
        "available_product_rate": 0.75,
        "days_since_last_application": None,
    }
    return engine.DecisionContext(**{**base, **overrides})


class TestDecisionEngine:
    """As regras que separam um diagnóstico de uma aplicação."""

    def test_o_caminho_completo_recomenda_aplicacao(self) -> None:
        result = engine.decide(context())
        assert result.outcome is DecisionOutcome.APPLICATION_CANDIDATE
        assert result.product_id == "prod-1"

    def test_saudavel_nao_gera_acao(self) -> None:
        assert engine.decide(context(label="Healthy")).outcome is DecisionOutcome.NO_ACTION

    def test_amostra_pequena_pede_mais_dados(self) -> None:
        """A defesa direta contra o erro pontual de alta confiança.

        Uma detecção isolada não distingue infestação de engano do modelo; uma
        infestação real aparece em dezenas de plantas vizinhas.
        """
        result = engine.decide(context(sample_size=3))
        assert result.outcome is DecisionOutcome.NEED_MORE_DATA
        assert result.reason_code == engine.SMALL_SAMPLE

    def test_incidencia_baixa_so_observa(self) -> None:
        result = engine.decide(context(affected_ratio=0.01))
        assert result.outcome is DecisionOutcome.OBSERVE
        assert result.reason_code == engine.LOW_INCIDENCE

    def test_confianca_insuficiente_so_observa(self) -> None:
        assert engine.decide(context(confidence=0.80)).outcome is DecisionOutcome.OBSERVE

    def test_novidade_vai_para_o_agronomo(self) -> None:
        result = engine.decide(context(novelty_score=3.0))
        assert result.outcome is DecisionOutcome.HUMAN_REVIEW
        assert result.reason_code == engine.NOVELTY

    def test_par_nao_independente_nao_sustenta_aplicacao(self) -> None:
        """Concordância entre modelos correlacionados não é evidência."""
        result = engine.decide(context(independent_pair=False))
        assert result.outcome is DecisionOutcome.HUMAN_REVIEW
        assert result.reason_code == engine.NOT_INDEPENDENT

    def test_diagnostico_humano_dispensa_a_segunda_maquina(self) -> None:
        """A confirmação do agrônomo substitui a segunda opinião de máquina."""
        result = engine.decide(
            context(independent_pair=False, status=DiagnosisStatus.HUMAN_CONFIRMED.value)
        )
        assert result.outcome is DecisionOutcome.APPLICATION_CANDIDATE

    def test_sem_produto_cadastrado_vai_para_o_agronomo(self) -> None:
        """A plataforma não escolhe defensivo por conta própria."""
        result = engine.decide(context(available_product_id=None))
        assert result.outcome is DecisionOutcome.HUMAN_REVIEW
        assert result.reason_code == engine.NO_PRODUCT

    def test_respeita_a_carencia_de_reaplicacao(self) -> None:
        """Sem isso, um talhão diagnosticado todo dia seria tratado todo dia."""
        result = engine.decide(
            context(days_since_last_application=2.0, last_application_product_id="prod-1")
        )
        assert result.outcome is DecisionOutcome.OBSERVE
        assert result.reason_code == engine.COOLDOWN

    def test_produto_diferente_nao_cai_na_carencia(self) -> None:
        result = engine.decide(
            context(days_since_last_application=2.0, last_application_product_id="outro")
        )
        assert result.outcome is DecisionOutcome.APPLICATION_CANDIDATE

    def test_diagnostico_em_revisao_nunca_vira_acao(self) -> None:
        result = engine.decide(context(status=DiagnosisStatus.NEEDS_REVIEW.value))
        assert result.outcome is DecisionOutcome.HUMAN_REVIEW

    def test_a_decisao_e_reproduzivel(self) -> None:
        """``Decision.inputs`` guarda tudo que a regra leu.

        É o que permite responder, meses depois, por que o sistema recomendou
        aquilo — reexecutando a regra com os mesmos números.
        """
        ctx = context()
        primeira = engine.decide(ctx)
        segunda = engine.decide(engine.DecisionContext(**ctx.as_dict()))
        assert primeira == segunda
