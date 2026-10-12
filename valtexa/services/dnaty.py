"""Etapa de otimização (dNATY) no Model Registry (brief, seção 23).

    MODELO TREINADO → VALIDAÇÃO → BENCHMARK → dNATY → MODELO OTIMIZADO →
    NOVO BENCHMARK → VALIDAÇÃO → APROVAÇÃO → PUBLICAÇÃO → ROVER

A plataforma não roda modelo: quem mede é a AI Platform
(``ia/training/dnaty_pipeline.py``), pelo ONNX Runtime, o original e o otimizado
sobre o mesmo conjunto de validação. Aqui o registry **recebe o relatório,
recalcula o veredito** com o critério de aceite (o do relatório não vale por si)
e grava a rodada em :class:`~valtexa.models.ModelOptimization`. Só rodada aceita
leva o otimizado para a versão — e a versão com otimizado só é aprovada se a
rodada aceita for **daquele** hash.

Compressão não vale só porque ficou menor: precisa manter F1, precisão, recall
e o recall de cada classe dentro da tolerância **e** ganhar de verdade em
latência, memória, tamanho ou custo computacional.

**dNATY é BSL 1.1**: uso não comercial liberado; **uso comercial pede licença
própria do autor**. A nota vai gravada em toda rodada feita com ele.

O critério e a comparação existem igual no ``ia/`` (para o relatório local); a
decisão que vale é a deste módulo.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from valtexa.models import ActorType, ModelOptimization, ModelVersion, SubjectType, User
from valtexa.services import audit
from valtexa.services.model_registry import EDITAVEIS_TECNICOS, ROTULOS, RegistryError

LICENCA_DNATY = (
    "dNATY é licenciado sob BSL 1.1: uso não comercial liberado; uso comercial "
    "(modelo otimizado servindo cliente pagante) pede licença própria do autor."
)

METRICAS_OBRIGATORIAS = ("precision", "recall", "f1", "latency_ms_p50", "size_bytes", "sha256")


@dataclass
class CriterioDeAceite:
    """Tolerâncias e ganho mínimo. Quedas em pontos absolutos (0,01 = 1 p.p.)."""

    max_queda_f1: float = 0.01
    max_queda_precisao: float = 0.02
    max_queda_recall: float = 0.02
    max_queda_recall_por_classe: float = 0.03
    latencia_max_relativa: float = 1.10
    ganho_minimo: float = 0.10
    ganhos_validos: tuple[str, ...] = ("latency_ms_p50", "memory_mb", "size_bytes", "flops")
    ruido_latencia_ms: float = 0.5
    """Diferença de latência menor que isto é ruído de medição (CPU disputada): não
    conta como ganho nem como perda. Modelo de borda real roda em milissegundos."""
    ruido_memoria_mb: float = 16.0
    """Idem para a memória, medida pela residente a mais do processo — a primeira
    sessão do ONNX Runtime paga a inicialização da biblioteca e a segunda não."""

    @classmethod
    def from_dict(cls, dados: dict | None) -> CriterioDeAceite:
        conhecidos = {f.name for f in fields(cls)}
        dados = dict(dados or {})
        desconhecidos = set(dados) - conhecidos
        if desconhecidos:
            raise RegistryError(
                f"Critério com campo desconhecido: {', '.join(sorted(desconhecidos))}."
            )
        if "ganhos_validos" in dados:
            validos = {"latency_ms_p50", "latency_ms_p95", "memory_mb", "size_bytes", "flops"}
            if not set(dados["ganhos_validos"]) <= validos or not dados["ganhos_validos"]:
                raise RegistryError(f"ganhos_validos aceita só: {', '.join(sorted(validos))}.")
            dados["ganhos_validos"] = tuple(dados["ganhos_validos"])
        criterio = cls(**dados)
        if criterio.ganho_minimo <= 0:
            raise RegistryError(
                "ganho_minimo precisa ser positivo: compressão não vale só por existir."
            )
        return criterio

    def as_dict(self) -> dict[str, Any]:
        return {**asdict(self), "ganhos_validos": list(self.ganhos_validos)}


def comparar(original: dict, otimizado: dict) -> dict[str, Any]:
    saida: dict[str, Any] = {}
    for chave in ("accuracy", "precision", "recall", "f1"):
        if original.get(chave) is not None and otimizado.get(chave) is not None:
            saida[f"delta_{chave}"] = round(otimizado[chave] - original[chave], 6)
    for chave in ("latency_ms_p50", "latency_ms_p95", "memory_mb", "size_bytes", "flops", "fps"):
        a, b = original.get(chave), otimizado.get(chave)
        saida[f"razao_{chave}"] = round(b / a, 6) if a and b is not None else None
    por_classe = {}
    novos = {c.get("class_name"): c for c in otimizado.get("por_classe") or []}
    for o in original.get("por_classe") or []:
        n = novos.get(o.get("class_name"))
        if n is not None:
            por_classe[o["class_name"]] = round(n["recall"] - o["recall"], 6)
    saida["delta_recall_por_classe"] = por_classe
    return saida


def _diferenca(a: dict, b: dict, chave: str) -> float:
    """``a[chave] - b[chave]`` (0 se faltar algum dos dois)."""
    if a.get(chave) is None or b.get(chave) is None:
        return 0.0
    return float(a[chave]) - float(b[chave])


def _ruido(criterio: CriterioDeAceite, chave: str) -> float:
    if chave.startswith("latency_ms"):
        return criterio.ruido_latencia_ms
    if chave == "memory_mb":
        return criterio.ruido_memoria_mb
    return 0.0


def avaliar(original: dict, otimizado: dict, criterio: CriterioDeAceite) -> dict[str, Any]:
    c = comparar(original, otimizado)
    motivos: list[str] = []
    if c["delta_f1"] < -criterio.max_queda_f1:
        motivos.append(f"F1 caiu {-c['delta_f1']:.4f} (máximo {criterio.max_queda_f1}).")
    if c["delta_precision"] < -criterio.max_queda_precisao:
        motivos.append(f"Precisão caiu {-c['delta_precision']:.4f} "
                       f"(máximo {criterio.max_queda_precisao}).")
    if c["delta_recall"] < -criterio.max_queda_recall:
        motivos.append(f"Recall caiu {-c['delta_recall']:.4f} "
                       f"(máximo {criterio.max_queda_recall}).")
    for classe, delta in c["delta_recall_por_classe"].items():
        if delta < -criterio.max_queda_recall_por_classe:
            motivos.append(f"Recall de {classe} caiu {-delta:.4f} "
                           f"(máximo {criterio.max_queda_recall_por_classe} por classe).")
    razao_lat = c.get("razao_latency_ms_p50")
    if razao_lat is not None and razao_lat > criterio.latencia_max_relativa \
            and _diferenca(otimizado, original, "latency_ms_p50") >= criterio.ruido_latencia_ms:
        motivos.append(f"Latência ficou {razao_lat:.2f}x a do original "
                       f"(máximo {criterio.latencia_max_relativa}x).")
    ganhos = {}
    for chave in criterio.ganhos_validos:
        razao = c.get(f"razao_{chave}")
        if razao is None:
            continue
        piso = _ruido(criterio, chave)
        if razao < 1 and _diferenca(original, otimizado, chave) < piso:
            razao = 1.0  # melhora dentro do ruído de medição não é ganho
        ganhos[chave] = round(1 - razao, 6)
    melhor = max(ganhos.values(), default=0.0)
    if melhor < criterio.ganho_minimo:
        motivos.append(f"Sem ganho de eficiência de ao menos {criterio.ganho_minimo:.0%} "
                       f"(melhor: {melhor:.1%}).")
    return {"aceito": not motivos, "motivos": motivos, "ganhos": ganhos, "comparacao": c}


def _confere_benchmark(nome: str, b: dict) -> None:
    faltam = [k for k in METRICAS_OBRIGATORIAS if b.get(k) is None]
    if faltam:
        raise RegistryError(f"Benchmark do {nome} sem {', '.join(faltam)}.")


def registrar_otimizacao(
    session: Session, linha: ModelVersion, relatorio: dict, *, actor: User
) -> ModelOptimization:
    """Grava uma rodada e, se aceita, leva o otimizado para a versão (original intocado)."""
    if linha.state not in EDITAVEIS_TECNICOS:
        raise RegistryError(
            f"Versão em {ROTULOS[linha.state]}: a otimização entra antes da aprovação "
            f"(TREINAMENTO ou VALIDAÇÃO). Registre uma versão nova."
        )
    original = relatorio["original"]["benchmark"]
    otimizado = relatorio["otimizado"]["benchmark"]
    _confere_benchmark("original", original)
    _confere_benchmark("otimizado", otimizado)
    if linha.original_artifact_sha256 and original["sha256"] != linha.original_artifact_sha256:
        raise RegistryError(
            "O benchmark é de outro artefato: o SHA-256 do original não é o desta versão."
        )
    if otimizado["sha256"] == original["sha256"]:
        raise RegistryError("Otimizado e original são o mesmo arquivo: nada a registrar.")
    if not linha.original_artifact_sha256:
        uri = relatorio["original"].get("artifact_uri")
        if not uri:
            raise RegistryError(
                "A versão não tem artefato original: informe original.artifact_uri."
            )
        linha.original_artifact_uri = uri
        linha.original_artifact_sha256 = original["sha256"]
        linha.size_bytes = linha.size_bytes or original["size_bytes"]

    criterio = CriterioDeAceite.from_dict(relatorio.get("criterio"))
    veredito = avaliar(original, otimizado, criterio)
    dnaty_version = relatorio.get("dnaty_version")
    rodada = ModelOptimization(
        model_version_id=linha.id,
        tool=relatorio["tool"],
        tool_version=relatorio.get("tool_version"),
        dnaty_version=dnaty_version,
        parameters=relatorio.get("parametros") or {},
        original_sha256=original["sha256"],
        original_benchmark=original,
        optimized_artifact_uri=relatorio["otimizado"]["artifact_uri"],
        optimized_sha256=otimizado["sha256"],
        optimized_size_bytes=otimizado.get("size_bytes"),
        optimized_benchmark=otimizado,
        criterion=criterio.as_dict(),
        comparison={**veredito["comparacao"], "ganhos": veredito["ganhos"]},
        accepted=veredito["aceito"],
        reasons=veredito["motivos"],
        license_note=LICENCA_DNATY if dnaty_version else None,
        created_by=actor.id,
    )
    session.add(rodada)
    session.flush()
    if rodada.accepted:
        linha.optimized_artifact_uri = rodada.optimized_artifact_uri
        linha.optimized_artifact_sha256 = rodada.optimized_sha256
        linha.optimized_size_bytes = rodada.optimized_size_bytes
        linha.dnaty_version = dnaty_version
        linha.flops = linha.flops or original.get("flops")
        linha.latency_ms = otimizado.get("latency_ms_p50")
        linha.memory_mb = otimizado.get("memory_mb")
        metricas = dict(linha.metrics or {})
        metricas["benchmark"] = {"otimizacao_id": rodada.id, "original": _resumo(original),
                                 "otimizado": _resumo(otimizado)}
        for chave in ("precision", "recall", "f1"):
            metricas.setdefault(chave, original[chave])
        linha.metrics = metricas
    audit.record(
        session,
        action="model_version.optimization",
        subject_type=SubjectType.MODEL_VERSION,
        subject_id=linha.id,
        actor_type=ActorType.USER,
        actor_id=actor.id,
        actor_label=actor.email,
        model_version=f"{linha.model_key}@{linha.version}",
        reason="; ".join(rodada.reasons) or None,
        payload={"optimization_id": rodada.id, "tool": rodada.tool, "accepted": rodada.accepted,
                 "optimized_sha256": rodada.optimized_sha256,
                 "dnaty_version": dnaty_version},
    )
    return rodada


def _resumo(b: dict) -> dict:
    chaves = ("precision", "recall", "f1", "accuracy", "latency_ms_p50", "latency_ms_p95", "fps",
              "memory_mb", "size_bytes", "flops", "map", "hardware", "amostras")
    return {k: b.get(k) for k in chaves}


def otimizacao_aceita(session: Session, linha: ModelVersion) -> ModelOptimization | None:
    """A rodada aceita que gerou o otimizado atual da versão (``None`` se não há)."""
    if not linha.optimized_artifact_sha256:
        return None
    return session.scalars(
        select(ModelOptimization)
        .where(
            ModelOptimization.model_version_id == linha.id,
            ModelOptimization.optimized_sha256 == linha.optimized_artifact_sha256,
            ModelOptimization.accepted.is_(True),
        )
        .order_by(ModelOptimization.created_at.desc())
    ).first()


__all__ = ["LICENCA_DNATY", "CriterioDeAceite", "avaliar", "comparar", "otimizacao_aceita",
           "registrar_otimizacao"]
