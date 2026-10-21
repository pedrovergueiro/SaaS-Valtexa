"""Guardar, ler e revisar planos de apoio — com hash e auditoria de cada passo.

O que este módulo **escreve**: ``plano_apoio``, ``revisao_plano_apoio`` e ``audit_entry``.
Nada mais. Revisar ("aceito") **não autoriza nada**: é o registro de que uma pessoa leu as
premissas e concordou; agir continua sendo pelos fluxos de sempre.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from valtexa.models import ActorType, SubjectType, as_utc
from valtexa.models.planejamento import DECISOES_PLANO, PlanoDeApoio, RevisaoPlanoDeApoio
from valtexa.services import audit

AVISO = ("Apoio à decisão, com premissas registradas. Aceitar este plano não cria missão, não "
         "aprova prescrição nem aplicação e não muda limiar de modelo: quem age é a pessoa, "
         "pelos fluxos de sempre, e quem libera a execução é o Safety Engine.")


class RevisaoInvalidaError(ValueError):
    pass


def sha256(objeto: Any) -> str:
    return hashlib.sha256(json.dumps(objeto, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":"), default=str).encode()).hexdigest()


def _corpo(tipo: str, pedido: dict, premissas: list, resultado: dict) -> dict[str, Any]:
    return {"tipo": tipo, "pedido": pedido, "premissas": premissas, "resultado": resultado}


def guardar(session: Session, *, tenant_id: str, tipo: str, farm_id: str | None,
            field_id: str | None, versao: str, pedido: dict[str, Any],
            premissas: list[dict[str, Any]], resultado: dict[str, Any],
            ator_id: str | None) -> PlanoDeApoio:
    """Não faz *commit*."""
    # Ida e volta pelo JSON: o que se guarda é exatamente o que o hash cobre.
    pedido, premissas, resultado = json.loads(json.dumps(
        [pedido, premissas, resultado], ensure_ascii=False, default=str))
    p = PlanoDeApoio(tenant_id=tenant_id, tipo=tipo, farm_id=farm_id, field_id=field_id,
                     versao_motor=versao, pedido=pedido, premissas=premissas,
                     resultado=resultado, sha256=sha256(_corpo(tipo, pedido, premissas,
                                                               resultado)),
                     estado="proposto", gerado_por=ator_id)
    session.add(p)
    session.flush()
    audit.record(session, tenant_id=tenant_id, action="planejamento.gerado",
                 subject_type=SubjectType.PLANEJAMENTO, subject_id=p.id,
                 actor_type=ActorType.USER if ator_id else ActorType.SYSTEM, actor_id=ator_id,
                 new_state=p.estado, model_version=versao,
                 payload={"tipo": tipo, "field_id": field_id, "farm_id": farm_id,
                          "sha256": p.sha256,
                          "premissas": [x["codigo"] for x in premissas]})
    return p


def integro(p: PlanoDeApoio) -> bool:
    return sha256(_corpo(p.tipo, p.pedido, p.premissas, p.resultado)) == p.sha256


def revisar(session: Session, p: PlanoDeApoio, *, revisor_id: str, papel: str, decisao: str,
            comentario: str | None, agora: datetime) -> RevisaoPlanoDeApoio:
    if decisao not in DECISOES_PLANO:
        raise RevisaoInvalidaError(f"decisão: uma de {', '.join(DECISOES_PLANO)}.")
    if decisao in ("recusado", "ajustar") and not (comentario or "").strip():
        raise RevisaoInvalidaError("recusar ou pedir ajuste pede um comentário (o quê e por quê).")
    if not integro(p):
        raise RevisaoInvalidaError("o plano guardado não confere com o hash: não revise.")
    rev = RevisaoPlanoDeApoio(tenant_id=p.tenant_id, plano_id=p.id, revisor_id=revisor_id,
                              papel=papel, decisao=decisao,
                              comentario=(comentario or "").strip() or None,
                              plano_sha256=p.sha256, revisado_em=agora)
    session.add(rev)
    antes, p.estado = p.estado, "revisado"
    session.flush()
    audit.record(session, tenant_id=p.tenant_id, action="planejamento.revisado",
                 subject_type=SubjectType.PLANEJAMENTO, subject_id=p.id,
                 actor_type=ActorType.USER, actor_id=revisor_id, old_state=antes,
                 new_state=p.estado, reason=rev.comentario,
                 payload={"decisao": decisao, "papel": papel, "plano_sha256": p.sha256,
                          "revisao_id": rev.id})
    return rev


def resumo(p: PlanoDeApoio) -> dict[str, Any]:
    return {"id": p.id, "tipo": p.tipo, "farm_id": p.farm_id, "field_id": p.field_id,
            "versao_motor": p.versao_motor, "estado": p.estado,
            "gerado_em": as_utc(p.created_at).isoformat(), "gerado_por": p.gerado_por,
            "premissas": len(p.premissas or [])}


def detalhe(p: PlanoDeApoio, revisoes: list[RevisaoPlanoDeApoio]) -> dict[str, Any]:
    return {**resumo(p), "pedido": p.pedido, "premissas": p.premissas,
            "resultado": p.resultado, "sha256": p.sha256, "integro": integro(p),
            "revisoes": [{"id": r.id, "revisor_id": r.revisor_id, "papel": r.papel,
                          "decisao": r.decisao, "comentario": r.comentario,
                          "plano_sha256": r.plano_sha256,
                          "revisado_em": as_utc(r.revisado_em).isoformat()}
                         for r in revisoes],
            "aviso": AVISO}
