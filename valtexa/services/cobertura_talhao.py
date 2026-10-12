"""Mapa de cobertura do rádio da fazenda, por talhão: da base para a plataforma e para a missão.

A base roda o levantamento (``valtexa-base levantamento``, sobre o que o Rover e ela
registraram com a posição RTK) e manda o resultado de um talhão
(``PUT /v1/device/base/cobertura/{field_id}``, assinado pela base). A plataforma confere o
formato e guarda no talhão; daí:

* o console mostra o mapa (células boa/marginal/morta, zonas mortas, repetidoras
  sugeridas com o ganho);
* **toda missão nova do talhão leva o mapa assinado** (``mission_command_body``): o Rover
  antecipa a sincronização antes de entrar numa zona morta, avisa a base e registra a
  travessia — sem arquivo copiado à mão no robô.

Nenhum número aqui é inventado: é o que a base mediu. Mapa velho continua valendo até
chegar um novo; ``cobertura_em`` diz de quando é.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from valtexa.models import ActorType, Device, Field, SubjectType
from valtexa.services import audit

CLASSES = {"bom", "marginal", "morto"}
MAX_CELULAS = 100_000
CAMPOS_DA_MISSAO = ("versao", "origem", "celula_m", "celulas", "zonas_mortas")


class CoberturaInvalidaError(ValueError):
    pass


def valida(rel: dict) -> dict:
    """O que a plataforma guarda do relatório do levantamento, conferido."""
    if not isinstance(rel, dict):
        raise CoberturaInvalidaError("o corpo precisa ser o relatorio.json do levantamento")
    origem = rel.get("origem")
    if (not isinstance(origem, list) or len(origem) != 2
            or not all(isinstance(v, int | float) for v in origem)
            or not -90 <= origem[0] <= 90 or not -180 <= origem[1] <= 180):
        raise CoberturaInvalidaError("origem precisa ser [lat, lon]")
    celula_m = rel.get("celula_m")
    if not isinstance(celula_m, int | float) or not 1 <= celula_m <= 200:
        raise CoberturaInvalidaError("celula_m entre 1 e 200")
    celulas = rel.get("celulas")
    if not isinstance(celulas, dict) or not celulas or len(celulas) > MAX_CELULAS:
        raise CoberturaInvalidaError(f"celulas: de 1 a {MAX_CELULAS}")
    for chave, classe in celulas.items():
        partes = str(chave).split(",")
        if len(partes) != 2 or not all(p.lstrip("-").isdigit() for p in partes) \
                or classe not in CLASSES:
            raise CoberturaInvalidaError(f"célula inválida: {chave!r}={classe!r}")
    zonas = rel.get("zonas_mortas") or []
    if not isinstance(zonas, list) or not all(
            isinstance(z, dict) and {"id", "celulas", "centro", "area_m2"} <= set(z)
            for z in zonas):
        raise CoberturaInvalidaError("zonas_mortas: cada uma com id, celulas, centro e area_m2")
    repetidoras = rel.get("repetidoras") or []
    if not isinstance(repetidoras, list):
        raise CoberturaInvalidaError("repetidoras precisa ser lista")
    contagem = {k: sum(1 for v in celulas.values() if v == k) for k in sorted(CLASSES)}
    return {"versao": int(rel.get("versao") or 1), "origem": [float(v) for v in origem],
            "celula_m": float(celula_m), "celulas": celulas, "zonas_mortas": zonas,
            "repetidoras": repetidoras[:20], "contagem": contagem,
            "raio_repetidora_m": rel.get("raio_repetidora_m"),
            "amostras": rel.get("amostras"),
            "fracao_morta_coberta": rel.get("fracao_morta_coberta")}


def guarda(session: Session, base: Device, field: Field, rel: dict) -> dict:
    """A base manda o mapa de um talhão dela (mesmo cliente; mesma fazenda, se tiver)."""
    if field.tenant_id != base.tenant_id or (base.farm_id and field.farm_id != base.farm_id):
        raise LookupError("talhão fora da fazenda desta base")
    mapa = valida(rel)
    field.cobertura = mapa
    field.cobertura_em = datetime.now(UTC)
    audit.record(session, action="field.cobertura", subject_type=SubjectType.FIELD,
                 subject_id=field.id, actor_type=ActorType.DEVICE, actor_id=base.id,
                 tenant_id=field.tenant_id,
                 new_state=f"{len(mapa['celulas'])} células, "
                           f"{len(mapa['zonas_mortas'])} zona(s) morta(s)")
    return mapa


def talhoes_da_base(session: Session, base: Device) -> list[dict]:
    """Os talhões que a base atende (mesma fazenda; sem fazenda, o cliente) e se cada um já
    tem levantamento — o console lista e desenha o mapa do que tiver."""
    consulta = select(Field).where(Field.tenant_id == base.tenant_id)
    if base.farm_id:
        consulta = consulta.where(Field.farm_id == base.farm_id)
    return [{"id": f.id, "name": f.name,
             "cobertura_em": f.cobertura_em.isoformat() if f.cobertura_em else None,
             "contagem": (f.cobertura or {}).get("contagem"),
             "zonas_mortas": len((f.cobertura or {}).get("zonas_mortas") or [])}
            for f in session.scalars(consulta.order_by(Field.name))]


def para_missao(field: Field | None) -> dict | None:
    """O que vai assinado na missão: só o que o Rover usa (a grade e as zonas mortas)."""
    if field is None or not field.cobertura:
        return None
    mapa = {k: field.cobertura[k] for k in CAMPOS_DA_MISSAO if k in field.cobertura}
    mapa["gerado_em"] = field.cobertura_em.isoformat() if field.cobertura_em else None
    return mapa
