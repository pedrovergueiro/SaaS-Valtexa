"""Model Registry: o que existe, o que pode atender e quem decidiu (brief, seções 9, 22 e 23).

Este módulo é a fonte da verdade sobre modelos na plataforma. Três consumidores:

* o **pipeline de análise** (:func:`valtexa.services.ai_pipeline.resolve_model`)
  escolhe o modelo de um talhão entre as versões em PRODUÇÃO liberadas para o
  cliente — antes, um espelho do catálogo de VALTEXA-B no código fazia isso;
* o **robô** pergunta qual modelo deve rodar (``GET /v1/device/models``) e só
  recebe versão em PRODUÇÃO deste registry — nunca um modelo arbitrário;
* a **frota** compara o que o robô diz rodar com o que foi designado a ele.

Ciclo de vida (seção 9)::

    TREINAMENTO → VALIDAÇÃO → APROVADO → STAGING → PRODUÇÃO → DESCONTINUADO

com volta permitida para a etapa anterior de validação (reprovação) e saída para
DESCONTINUADO de qualquer estado. Aprovar exige papel ``ia_dados`` ou
``superadmin`` e **não pode** ser quem registrou a versão (quatro olhos). Entrar
em PRODUÇÃO exige artefato com hash e descontinua a versão anterior da mesma
chave — no máximo uma versão em PRODUÇÃO por ``model_key``. Toda transição vai
para a auditoria da plataforma.

**Pesos não estão aqui.** A plataforma guarda onde o artefato vive e o hash dele;
os arquivos ficam na máquina do Pedro (``docs/CONTEXTO_NUVEM.md``). As versões
cadastradas pelo catálogo inicial não têm artefato nem hash: o console mostra
"sem dado" até a equipe de IA preencher com o modelo real.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from valtexa.models import (
    ActorType,
    CapturePlatform,
    Device,
    Field,
    ModelOptimization,
    ModelRelease,
    ModelVersion,
    ModelVersionState,
    PlatformRole,
    ReleaseScope,
    SubjectType,
    User,
)
from valtexa.services import audit

E = ModelVersionState

BANANA = ["banana", "bananeira", "banana-prata", "banana-nanica"]
CITRUS = ["citrus", "citros", "laranja", "limão", "limao", "lima", "orange", "lemon"]

_NOTA_CATALOGO = (
    "Cadastrado a partir do espelho do catálogo de VALTEXA-B (app/registry.py, lido em "
    "27/09/2026), que antes vivia em services/ai_pipeline.py. Número de versão provisório; "
    "artefatos, hashes, FLOPs, latência e memória a preencher pela equipe de IA com o modelo "
    "real — os pesos não estão neste repositório."
)

CATALOGO_INICIAL: list[dict] = [
    {
        "model_key": "leaf-foliar",
        "name": "Doenças foliares do milho",
        "crops": ["corn", "milho"],
        "platform": CapturePlatform.GROUND,
        "state": E.PRODUCAO,
    },
    {
        "model_key": "coffee-foliar",
        "name": "Doenças foliares do café",
        "crops": ["coffee", "cafe", "café"],
        "platform": CapturePlatform.GROUND,
        "state": E.PRODUCAO,
    },
    {
        "model_key": "banana-foliar",
        "name": "Doenças foliares da banana (campo)",
        "crops": BANANA,
        "platform": CapturePlatform.GROUND,
        "state": E.PRODUCAO,
        "variant": "campo",
        "license": "CC BY 4.0 + PlantSeg CC BY-NC 4.0 (não comercial)",
        "metrics": {"field_accuracy": 0.829},
    },
    {
        "model_key": "banana-foliar-cc",
        "name": "Doenças foliares da banana (comercial)",
        "crops": BANANA,
        "platform": CapturePlatform.GROUND,
        "state": E.PRODUCAO,
        "variant": "comercial",
        "recommended": False,
        "license": "CC BY 4.0",
        "metrics": {"field_accuracy": 0.592},
        "caveat": "erra mais no campo; responde 'Healthy' a superfície verde uniforme",
    },
    {
        "model_key": "citrus-foliar",
        "name": "Doenças foliares dos citros (campo)",
        "crops": CITRUS,
        "platform": CapturePlatform.GROUND,
        "state": E.PRODUCAO,
        "variant": "campo",
        "license": "CC BY 4.0 + PlantSeg CC BY-NC 4.0 (não comercial)",
        "metrics": {"field_accuracy": 0.969},
    },
    {
        "model_key": "citrus-foliar-cc",
        "name": "Doenças foliares dos citros (comercial)",
        "crops": CITRUS,
        "platform": CapturePlatform.GROUND,
        "state": E.PRODUCAO,
        "variant": "comercial",
        "recommended": False,
        "license": "CC BY 4.0",
        "metrics": {"field_accuracy": 0.695},
        "caveat": "erra mais no campo: treinado só com folha fotografada sobre papel",
    },
    {
        "model_key": "rover-understory",
        "name": "Sub-bosque do milho (rover)",
        "crops": ["corn", "milho"],
        "platform": CapturePlatform.GROUND,
        "state": E.TREINAMENTO,
        "caveat": "em quarentena: quatro das oito classes não têm dataset",
    },
    {
        "model_key": "aerial-canopy",
        "name": "Dossel do milho (aéreo)",
        "crops": ["corn", "milho"],
        "platform": CapturePlatform.AERIAL,
        "state": E.TREINAMENTO,
        "caveat": "precisa de coleta: nenhum peso treinado",
    },
]
"""O catálogo que existia em ``ai_pipeline.CATALOGO``, agora como semente do registry.

``state=TREINAMENTO`` para ``rover-understory`` e ``aerial-canopy`` não é pendência
de código: é o estado real deles em ``VALTEXA-B/MODELS.md`` (sem peso treinado).
A acurácia de campo é a da escala do rover, medida lá; vai em ``metrics``, que
só a equipe vê.
"""

VERSAO_INICIAL = "1.0.0"

TRANSICOES: dict[ModelVersionState, frozenset[ModelVersionState]] = {
    E.TREINAMENTO: frozenset({E.VALIDACAO, E.DESCONTINUADO}),
    E.VALIDACAO: frozenset({E.APROVADO, E.TREINAMENTO, E.DESCONTINUADO}),
    E.APROVADO: frozenset({E.STAGING, E.VALIDACAO, E.DESCONTINUADO}),
    E.STAGING: frozenset({E.PRODUCAO, E.VALIDACAO, E.DESCONTINUADO}),
    E.PRODUCAO: frozenset({E.DESCONTINUADO}),
    E.DESCONTINUADO: frozenset(),
}

_ORDEM = list(ModelVersionState)
APROVADORES = frozenset({PlatformRole.IA_DADOS, PlatformRole.SUPERADMIN})
EDITAVEIS_TECNICOS = frozenset({E.TREINAMENTO, E.VALIDACAO})
"""Depois de aprovada, a versão não muda de métrica nem de artefato: mudar seria
aprovar uma coisa e publicar outra. Para mudar, registra-se versão nova."""

ROTULOS = {
    E.TREINAMENTO: "Treinamento",
    E.VALIDACAO: "Validação",
    E.APROVADO: "Aprovado",
    E.STAGING: "Staging",
    E.PRODUCAO: "Produção",
    E.DESCONTINUADO: "Descontinuado",
}


class RegistryError(ValueError):
    """Transição recusada. A mensagem vai inteira para quem pediu (409 ou 403)."""

    def __init__(self, mensagem: str, *, proibido: bool = False) -> None:
        super().__init__(mensagem)
        self.proibido = proibido


# ---------------------------------------------------------------------------
# Catálogo inicial
# ---------------------------------------------------------------------------


def sincronizar_catalogo(session: Session) -> int:
    """Cria as linhas do catálogo inicial cuja ``model_key`` ainda não existe.

    Não altera nada que já esteja no banco: uma versão que a equipe descontinuou
    pelo console não pode voltar a PRODUÇÃO a cada reinício.
    """
    existentes = set(session.scalars(select(ModelVersion.model_key).distinct()))
    criados = 0
    for item in CATALOGO_INICIAL:
        if item["model_key"] in existentes:
            continue
        dados = {
            "version": VERSAO_INICIAL,
            "problem": "doença foliar",
            "crop": item["crops"][0],
            "notes": _NOTA_CATALOGO,
            **item,
        }
        if dados["state"] is E.PRODUCAO:
            dados["promoted_at"] = datetime.now(UTC)
        session.add(ModelVersion(**dados))
        criados += 1
    if criados:
        session.commit()
    return criados


# ---------------------------------------------------------------------------
# Leitura: o que atende quem
# ---------------------------------------------------------------------------


def _atende(linha: ModelVersion, cultura: str, platform: CapturePlatform) -> bool:
    return cultura in [c.lower() for c in (linha.crops or [])] and linha.platform in (
        platform,
        CapturePlatform.ANY,
    )


def chaves_liberadas(session: Session, tenant_id: str | None) -> set[str]:
    if tenant_id is None:
        return set()
    return set(
        session.scalars(
            select(ModelRelease.model_key).where(
                ModelRelease.tenant_id == tenant_id, ModelRelease.revoked_at.is_(None)
            )
        )
    )


def liberado(linha: ModelVersion, liberadas: set[str]) -> bool:
    return linha.release_scope is ReleaseScope.TODOS or linha.model_key in liberadas


def candidatos(
    session: Session, crop: str, platform: CapturePlatform
) -> list[ModelVersion]:
    """Toda versão não descontinuada que atende a cultura nesta plataforma."""
    cultura = (crop or "").strip().lower()
    linhas = session.scalars(
        select(ModelVersion)
        .where(ModelVersion.state != E.DESCONTINUADO)
        .order_by(ModelVersion.model_key, ModelVersion.created_at)
    )
    return [linha for linha in linhas if _atende(linha, cultura, platform)]


def disponiveis(
    session: Session, crop: str, platform: CapturePlatform, tenant_id: str | None
) -> list[ModelVersion]:
    """As versões em PRODUÇÃO que o cliente pode usar, a recomendada primeiro."""
    liberadas = chaves_liberadas(session, tenant_id)
    linhas = [
        linha
        for linha in candidatos(session, crop, platform)
        if linha.state is E.PRODUCAO and liberado(linha, liberadas)
    ]
    return sorted(linhas, key=lambda linha: (not linha.recommended, linha.model_key))


def em_producao(session: Session, model_key: str) -> ModelVersion | None:
    return session.scalars(
        select(ModelVersion).where(
            ModelVersion.model_key == model_key, ModelVersion.state == E.PRODUCAO
        )
    ).first()


def treinadas(session: Session) -> list[ModelVersion]:
    """As que já passaram do treinamento e ainda valem — para mensagens de recusa."""
    return list(
        session.scalars(
            select(ModelVersion).where(
                ModelVersion.state.in_([E.VALIDACAO, E.APROVADO, E.STAGING, E.PRODUCAO])
            )
        )
    )


# ---------------------------------------------------------------------------
# Escrita: registro, edição e transições
# ---------------------------------------------------------------------------


def registrar(session: Session, dados: dict, *, actor: User) -> ModelVersion:
    existente = session.scalars(
        select(ModelVersion).where(
            ModelVersion.model_key == dados["model_key"],
            ModelVersion.version == dados["version"],
        )
    ).first()
    if existente is not None:
        raise RegistryError(
            f"{dados['model_key']} {dados['version']} já está no registry "
            f"(estado {ROTULOS[existente.state]}). Versão publicada não se reescreve: "
            f"registre uma versão nova."
        )
    crops = [c.strip().lower() for c in dados.pop("crops", []) if c and c.strip()]
    if not crops:
        raise RegistryError("Informe ao menos uma cultura que o modelo atende.")
    linha = ModelVersion(
        **dados,
        crops=crops,
        crop=crops[0],
        state=E.TREINAMENTO,
        registered_by=actor.id,
    )
    session.add(linha)
    session.flush()
    _audita(session, linha, actor, "model_version.registered", None, E.TREINAMENTO, None)
    return linha


def editar(session: Session, linha: ModelVersion, mudancas: dict, *, actor: User) -> None:
    tecnicos = {k for k in mudancas if k not in {"notes", "caveat", "release_scope"}}
    if tecnicos and linha.state not in EDITAVEIS_TECNICOS:
        raise RegistryError(
            f"Versão em {ROTULOS[linha.state]}: métricas, artefatos e dados técnicos não "
            f"mudam depois da aprovação ({', '.join(sorted(tecnicos))}). Registre uma "
            f"versão nova."
        )
    antes = {k: _serial(getattr(linha, k)) for k in mudancas}
    for campo, valor in mudancas.items():
        if campo == "crops":
            valor = [c.strip().lower() for c in valor if c and c.strip()]
            if not valor:
                raise RegistryError("Informe ao menos uma cultura que o modelo atende.")
            linha.crop = valor[0]
        setattr(linha, campo, valor)
    audit.record(
        session,
        action="model_version.updated",
        subject_type=SubjectType.MODEL_VERSION,
        subject_id=linha.id,
        actor_type=ActorType.USER,
        actor_id=actor.id,
        actor_label=actor.email,
        model_version=f"{linha.model_key}@{linha.version}",
        payload={"antes": antes, "depois": {k: _serial(v) for k, v in mudancas.items()}},
    )


def transicionar(
    session: Session,
    linha: ModelVersion,
    destino: ModelVersionState,
    *,
    actor: User,
    reason: str | None,
) -> list[ModelVersion]:
    """Leva ``linha`` para ``destino`` ou levanta :class:`RegistryError`.

    Devolve as versões afetadas (a própria e, ao publicar, a anterior que saiu de
    PRODUÇÃO).
    """
    origem = linha.state
    if destino not in TRANSICOES[origem]:
        permitidas = ", ".join(ROTULOS[e] for e in _ORDEM if e in TRANSICOES[origem])
        raise RegistryError(
            f"{ROTULOS[origem]} → {ROTULOS[destino]} não é uma transição válida. "
            f"Daqui: {permitidas or 'nenhuma (estado final)'}."
        )
    motivo = (reason or "").strip() or None
    voltando = _ORDEM.index(destino) < _ORDEM.index(origem)
    if (voltando or destino is E.DESCONTINUADO) and motivo is None:
        raise RegistryError("Reprovar ou descontinuar exige motivo.")

    agora = datetime.now(UTC)
    afetadas = [linha]
    if destino is E.APROVADO:
        if actor.platform_role not in APROVADORES:
            raise RegistryError(
                "Aprovar modelo é do papel IA & Dados (ou superadmin).", proibido=True
            )
        if linha.registered_by is not None and linha.registered_by == actor.id:
            raise RegistryError(
                "Quem registrou a versão não a aprova: precisa de outra pessoa de IA & Dados.",
                proibido=True,
            )
        if not linha.metrics:
            raise RegistryError("Sem métricas registradas não há o que aprovar.")
        if linha.optimized_artifact_sha256 and not _otimizado_aceito(session, linha):
            raise RegistryError(
                "O artefato otimizado não tem benchmark aceito pelo critério do registry "
                "(seção 23: compressão não vale só porque ficou menor). Registre a rodada "
                "de otimização (POST /v1/platform/models/{id}/optimizations) ou retire o "
                "otimizado."
            )
        linha.approved_by = actor.id
        linha.approved_at = agora
    if destino is E.PRODUCAO:
        if not (linha.original_artifact_sha256 or linha.optimized_artifact_sha256):
            raise RegistryError(
                "Publicar exige artefato com hash (original ou otimizado): é o que o robô "
                "confere antes de carregar o modelo."
            )
        anterior = em_producao(session, linha.model_key)
        if anterior is not None and anterior.id != linha.id:
            anterior.state = E.DESCONTINUADO
            anterior.retired_at = agora
            _audita(
                session, anterior, actor, "model_version.transition", E.PRODUCAO,
                E.DESCONTINUADO, f"Substituída por {linha.version}.",
            )
            afetadas.append(anterior)
        linha.promoted_at = agora
    if destino is E.DESCONTINUADO and origem is E.PRODUCAO:
        presos = _talhoes_presos(session, linha.model_key)
        if presos:
            raise RegistryError(
                f"{presos} talhão(ões) de cliente escolheram {linha.model_key} e não há "
                f"outra versão dele em PRODUÇÃO. Publique a substituta antes (ela "
                f"descontinua esta sozinha) ou peça aos clientes para trocar."
            )
    if destino is E.DESCONTINUADO:
        linha.retired_at = agora
    linha.state = destino
    _audita(session, linha, actor, "model_version.transition", origem, destino, motivo)
    return afetadas


def _otimizado_aceito(session: Session, linha: ModelVersion) -> bool:
    return session.scalar(
        select(func.count(ModelOptimization.id)).where(
            ModelOptimization.model_version_id == linha.id,
            ModelOptimization.optimized_sha256 == linha.optimized_artifact_sha256,
            ModelOptimization.accepted.is_(True),
        )
    ) > 0


def _talhoes_presos(session: Session, model_key: str) -> int:
    return session.scalar(select(func.count(Field.id)).where(Field.ai_model == model_key)) or 0


def _audita(
    session: Session,
    linha: ModelVersion,
    actor: User,
    acao: str,
    origem: ModelVersionState | None,
    destino: ModelVersionState,
    motivo: str | None,
) -> None:
    audit.record(
        session,
        action=acao,
        subject_type=SubjectType.MODEL_VERSION,
        subject_id=linha.id,
        actor_type=ActorType.USER,
        actor_id=actor.id,
        actor_label=actor.email,
        old_state=origem.value if origem else None,
        new_state=destino.value,
        reason=motivo,
        model_version=f"{linha.model_key}@{linha.version}",
    )


def _serial(valor: object) -> object:
    if isinstance(valor, datetime):
        return valor.isoformat()
    if hasattr(valor, "value"):
        return valor.value
    return valor


# ---------------------------------------------------------------------------
# Liberação por cliente
# ---------------------------------------------------------------------------


def liberar(
    session: Session, tenant_id: str, model_key: str, *, actor: User, reason: str | None
) -> ModelRelease:
    if not session.scalar(select(func.count()).where(ModelVersion.model_key == model_key)):
        raise RegistryError(f"{model_key!r} não está no registry.")
    ativa = session.scalars(
        select(ModelRelease).where(
            ModelRelease.tenant_id == tenant_id,
            ModelRelease.model_key == model_key,
            ModelRelease.revoked_at.is_(None),
        )
    ).first()
    if ativa is not None:
        return ativa
    linha = ModelRelease(
        tenant_id=tenant_id, model_key=model_key, reason=reason, released_by=actor.id
    )
    session.add(linha)
    session.flush()
    audit.record(
        session,
        tenant_id=tenant_id,
        action="model.released",
        subject_type=SubjectType.MODEL_VERSION,
        subject_id=linha.id,
        actor_type=ActorType.USER,
        actor_id=actor.id,
        actor_label=actor.email,
        reason=reason,
        payload={"model_key": model_key},
    )
    return linha


def revogar(session: Session, linha: ModelRelease, *, actor: User, reason: str | None) -> None:
    if linha.revoked_at is not None:
        return
    linha.revoked_at = datetime.now(UTC)
    linha.revoked_by = actor.id
    audit.record(
        session,
        tenant_id=linha.tenant_id,
        action="model.release_revoked",
        subject_type=SubjectType.MODEL_VERSION,
        subject_id=linha.id,
        actor_type=ActorType.USER,
        actor_id=actor.id,
        actor_label=actor.email,
        reason=reason,
        payload={"model_key": linha.model_key},
    )


# ---------------------------------------------------------------------------
# O robô: o que ele deve rodar e se está rodando
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Designado:
    field_id: str
    field_name: str
    crop: str
    version: ModelVersion | None
    reason: str | None = None
    """Por que não há modelo para o talhão, quando não há."""

    @property
    def etiqueta(self) -> str | None:
        if self.version is None:
            return None
        return f"{self.version.model_key}@{self.version.version}"


def designados(
    session: Session, device: Device, *, cache: dict | None = None
) -> list[Designado]:
    """Para cada talhão onde o robô trabalha, a versão em PRODUÇÃO que ele deve rodar.

    "Onde trabalha" é a fazenda do robô; sem fazenda, todos os talhões do cliente.
    A resolução é a mesma do pipeline da nuvem (cultura, plataforma, escolha do
    talhão, liberação do cliente): o modelo embarcado e o da nuvem não divergem.

    **Modelo fixado** pela equipe no centro de comando (``Device.pinned_model_*``) vale
    nos talhões da cultura dele e sobrepõe a escolha do talhão.
    """
    chave_cache = (device.tenant_id, device.farm_id, device.pinned_model_key,
                   device.pinned_model_version)
    if cache is not None and chave_cache in cache:
        return cache[chave_cache]
    from valtexa.services.ai_pipeline import NoModelForCaptureError, resolve_model

    consulta = select(Field).where(Field.tenant_id == device.tenant_id).order_by(Field.name)
    if device.farm_id is not None:
        consulta = consulta.where(Field.farm_id == device.farm_id)
    saida = []
    for talhao in session.scalars(consulta):
        try:
            chave = resolve_model(
                session, talhao.crop, CapturePlatform.GROUND, talhao.ai_model,
                tenant_id=device.tenant_id,
            )
        except NoModelForCaptureError as exc:
            saida.append(Designado(talhao.id, talhao.name, talhao.crop, None, str(exc)))
            continue
        saida.append(Designado(talhao.id, talhao.name, talhao.crop, em_producao(session, chave)))
    if device.pinned_model_key:
        fixado = session.scalars(select(ModelVersion).where(
            ModelVersion.model_key == device.pinned_model_key,
            ModelVersion.version == device.pinned_model_version)).first()
        if fixado is not None:
            culturas = {c.lower() for c in (fixado.crops or [])} | {
                (fixado.crop or "").lower()}
            saida = [Designado(d.field_id, d.field_name, d.crop, fixado,
                               "fixado pela equipe no centro de comando")
                     if (d.crop or "").lower() in culturas else d for d in saida]
    if cache is not None:
        cache[chave_cache] = saida
    return saida


def situacao_do_modelo(session: Session, device: Device, etiquetas: set[str]) -> str:
    """conforme, divergente, fora_do_registry ou sem_dado — o que a frota mostra."""
    if not device.ai_model_key or not device.ai_model_version:
        return "sem_dado"
    if f"{device.ai_model_key}@{device.ai_model_version}" in etiquetas:
        return "conforme"
    existe = session.scalar(
        select(func.count()).where(
            ModelVersion.model_key == device.ai_model_key,
            ModelVersion.version == device.ai_model_version,
        )
    )
    return "divergente" if existe else "fora_do_registry"


__all__ = [
    "CATALOGO_INICIAL",
    "ROTULOS",
    "TRANSICOES",
    "Designado",
    "RegistryError",
    "candidatos",
    "designados",
    "disponiveis",
    "editar",
    "em_producao",
    "liberar",
    "revogar",
    "sincronizar_catalogo",
    "situacao_do_modelo",
    "transicionar",
]
