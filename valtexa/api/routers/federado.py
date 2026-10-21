"""Consenso federado (7.1): o prior fundido para o estrato de um talhão, avaliado.

Só leitura (``decision:read``): calcula na hora, a partir das contagens conferidas pelo
agrônomo nos talhões do **próprio cliente**, e não grava nem distribui nada. Ver
``valtexa/services/federado.py`` e ``docs/FEDERADO.md``.
"""

from __future__ import annotations

from collections import Counter
from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from valtexa.api.deps import Principal, get_scoped, require
from valtexa.db import get_session
from valtexa.models import Field, utcnow
from valtexa.security import rbac
from valtexa.services import federado

router = APIRouter(tags=["federado"])


@router.get("/fields/{field_id}/federado/prior",
            summary="Prior fundido do estrato do talhão (sem o dado dele), avaliado")
def prior_do_talhao(
    field_id: str,
    janela_dias: int = Query(default=365, ge=7, le=1825),
    forca_maxima: float = Query(default=federado.FORCA_MAXIMA, gt=0, le=10_000),
    referencia_media: float = Query(default=0.5, gt=0, lt=1),
    referencia_forca: float = Query(default=2.0, gt=0, le=10_000),
    modelo: str | None = Query(default=None, max_length=160,
                               description="modelo@cabeça; padrão: o mais conferido"),
    principal: Principal = Depends(require(rbac.DECISION_READ)),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    campo = get_scoped(session, Field, field_id, principal)
    fim = utcnow().date()
    inicio = fim - timedelta(days=janela_dias)
    todas, protocolos = federado.contagens_do_cliente(session, principal.tenant_id,
                                                      inicio=inicio, fim=fim)
    premissas = [
        {"codigo": "janela_dias", "valor": janela_dias, "texto": "contagens conferidas na janela"},
        {"codigo": "forca_maxima", "valor": forca_maxima,
         "texto": "o prior fundido vale no máximo esta quantidade de plantas (padrão, não medido)"},
        {"codigo": "referencia", "valor": {"media": referencia_media, "forca": referencia_forca},
         "texto": "prior de referência da avaliação (padrão: uniforme fraco; mande o do treino)"},
        {"codigo": "escopo", "valor": "cliente",
         "texto": "só talhões do próprio cliente (entre clientes: decisão do Pedro)"},
    ]
    if not protocolos:
        return {"field_id": campo.id, "estrato": list(federado.estrato_do_talhao(campo)),
                "protocolo": None, "priores": [], "avaliacao": [], "recusadas": [],
                "eco_descartadas": 0, "premissas": premissas,
                "motivo": "sem diagnóstico conferido pelo agrônomo na janela"}
    uso = Counter(f"{c.protocolo.modelo}@{c.protocolo.cabeca}" for c in todas)
    escolhido = modelo or sorted(uso.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
    if escolhido not in protocolos:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "modelo@cabeça sem contagem na janela.")
    ref = protocolos[escolhido]
    aceitas, recusadas = [], []
    for c in todas:
        motivo = federado.compativel(c, ref, inicio=inicio, fim=fim)
        if motivo:
            recusadas.append({"talhao": c.origem, "classe": c.classe, "motivo": motivo})
        else:
            aceitas.append(c)
    limpas, descartadas = federado.sem_eco(aceitas)
    estrato = federado.estrato_do_talhao(campo)
    classes = sorted({c.classe for c in limpas})
    referencia = federado.Beta(referencia_media * referencia_forca,
                               (1 - referencia_media) * referencia_forca)
    priores = [federado.prior_para(limpas, destino=campo.id, estrato=estrato, classe=k,
                                   forca_maxima=forca_maxima) for k in classes]
    avaliacao = [federado.avaliar(limpas, classe=k, referencia=referencia,
                                  forca_maxima=forca_maxima) for k in classes]
    distribuivel = [p for p, a in zip(priores, avaliacao, strict=True)
                    if p["prior"] is not None and a["distribuir"]]
    proprias = [c for c in limpas if c.origem == campo.id]
    return {
        "field_id": campo.id, "estrato": list(estrato),
        "protocolo": {"modelo": ref.modelo, "cabeca": ref.cabeca, "validacao": ref.validacao,
                      "taxonomia_sha256": ref.taxonomia_sha256},
        "janela": [inicio.isoformat(), fim.isoformat()],
        "priores": priores, "avaliacao": avaliacao,
        "recusadas": recusadas, "eco_descartadas": descartadas,
        "bytes": {"carga_do_talhao": federado.tamanho(federado.carga(proprias)),
                  "prior_distribuivel": federado.tamanho(distribuivel)},
        "premissas": premissas,
        "nota": "Calculado, não distribuído: a descida assinada ao Rover e o uso na fusão por "
                "planta aguardam decisão (docs/FEDERADO.md).",
    }
