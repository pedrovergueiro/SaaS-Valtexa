"""Planejamento de insumos (8.3): demanda pelo histórico, cenários com intervalo, reposição.

Por produto do cliente (ou da fazenda), a partir das **aplicações concluídas**
(``application.amount_used_l``, o que o drone mediu que saiu) na janela de histórico:

* o histórico é cortado em **blocos de H dias** (H = o horizonte pedido), do mais recente para
  trás; a soma de cada bloco é uma amostra do consumo de H dias;
* **bootstrap** (semente fixa → o mesmo histórico dá o mesmo plano): ``B`` reamostragens dos
  blocos, a média de cada uma; os quantis 10/50/90 da média são o cenário baixo, central e
  alto **do consumo médio de H dias** — e os quantis 10/50/90 dos próprios blocos, o que um
  bloco qualquer pode pedir (mais largo, de propósito: o próximo mês é um bloco, não a média);
* o **comprometido**: missões de aplicação ainda não concluídas com quantidade autorizada
  (``authorized_quantity_l``) — prescrição aprovada que ainda vai sair do estoque;
* o **estoque**: os lotes não vencidos (``product_batch.quantity_l``) — o que o cadastro diz;
* **possível reposição** quando ``estoque - comprometido`` não cobre o cenário alto.

**Sem histórico, não estima**: menos de ``min_aplicacoes`` aplicações ou menos de
``min_blocos`` blocos com dado → "sem histórico suficiente para estimar", sem número. O
consumo de defensivo no café é sazonal: blocos de épocas diferentes se misturam; com dois
anos ou mais de histórico, o pedido pode restringir à mesma época (``mesma_epoca``).
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from valtexa.models import (
    Application,
    ApplicationState,
    Mission,
    MissionKind,
    MissionState,
    Product,
    as_utc,
)
from valtexa.models.agro import ProductBatch
from valtexa.planejamento.premissas import Premissas

VERSAO = "insumos-1"
SEMENTE = 20261019
ENCERRADAS = (MissionState.COMPLETED, MissionState.ABORTED, MissionState.EXPIRED)
"""Missão encerrada não compromete estoque (as mesmas de ``mission_manager.TERMINAL_STATES``,
repetidas aqui para o planejamento não importar quem muda missão — Princípio de Ouro)."""


def quantil(valores: list[float], q: float) -> float:
    """Quantil com interpolação linear (o "tipo 7" do R e do NumPy)."""
    v = sorted(valores)
    if not v:
        raise ValueError("sem valores")
    pos = (len(v) - 1) * q
    i = int(pos)
    j = min(i + 1, len(v) - 1)
    return v[i] + (v[j] - v[i]) * (pos - i)


def blocos(aplicacoes: list[tuple[datetime, float]], *, agora: datetime, horizonte_dias: int,
           janela_dias: int, mesma_epoca: bool) -> list[float]:
    """Soma do consumo em cada bloco de H dias, do mais recente para trás, dentro da janela.

    ``mesma_epoca``: só os blocos que começam no mesmo dia do ano que o bloco que vem
    (agora + k anos), um por ano anterior.
    """
    h = timedelta(days=horizonte_dias)
    if mesma_epoca:
        inicios = []
        k = 1
        while timedelta(days=365 * k) <= timedelta(days=janela_dias):
            inicios.append(agora - timedelta(days=365 * k))
            k += 1
        return [sum(q for t, q in aplicacoes if ini <= t < ini + h) for ini in inicios]
    n = janela_dias // horizonte_dias
    return [sum(q for t, q in aplicacoes if agora - (i + 1) * h <= t < agora - i * h)
            for i in range(n)]


def bootstrap(amostras: list[float], *, reamostragens: int, semente: int
              ) -> dict[str, float]:
    rng = random.Random(semente)
    n = len(amostras)
    medias = [sum(rng.choice(amostras) for _ in range(n)) / n for _ in range(reamostragens)]
    return {"p10": quantil(medias, 0.10), "p50": quantil(medias, 0.50),
            "p90": quantil(medias, 0.90)}


def _comprometido(session: Session, tenant_id: str, product_id: str,
                  farm_id: str | None) -> tuple[float, list[str]]:
    q = select(Mission).where(Mission.tenant_id == tenant_id, Mission.kind == MissionKind.SPRAY,
                              Mission.product_id == product_id,
                              Mission.state.not_in(ENCERRADAS))
    if farm_id:
        q = q.where(Mission.farm_id == farm_id)
    total, ids = 0.0, []
    for m in session.scalars(q.order_by(Mission.id)):
        if m.authorized_quantity_l:
            total += float(m.authorized_quantity_l)
            ids.append(m.id)
    return total, ids


def planejar(session: Session, *, tenant_id: str, farm_id: str | None,
             pedido: dict[str, Any], agora: datetime) -> tuple[dict[str, Any], list[dict]]:
    pr = Premissas()
    h = pr.valor("horizonte_dias", pedido.get("horizonte_dias"), 30,
                 "demanda estimada para os próximos N dias")
    janela = pr.valor("janela_dias", pedido.get("janela_dias"), 365,
                      "histórico usado: aplicações concluídas dos últimos N dias")
    mesma_epoca = pr.valor("mesma_epoca", pedido.get("mesma_epoca"), False,
                           "só blocos da mesma época do ano (exige anos de histórico)")
    reamostragens = pr.valor("reamostragens", pedido.get("reamostragens"), 2000,
                             "reamostragens do bootstrap")
    min_aplic = pr.valor("min_aplicacoes", pedido.get("min_aplicacoes"), 3,
                         "abaixo disto, não estima")
    min_blocos = pr.valor("min_blocos", pedido.get("min_blocos"), 2,
                          "blocos com consumo abaixo disto, não estima")
    pr.anota("semente", "semente do bootstrap: o mesmo histórico dá o mesmo plano", SEMENTE,
             "padrao")
    pr.anota("consumo", "consumo = amount_used_l da aplicação concluída (medido no drone)",
             None, "medido")
    pr.anota("estoque", "estoque = soma de quantity_l dos lotes não vencidos (cadastro)", None,
             "cadastro")
    produtos = session.scalars(select(Product).where(Product.tenant_id == tenant_id)
                               .order_by(Product.name, Product.id)).all()
    inicio = agora - timedelta(days=janela)
    saida = []
    for p in produtos:
        q = select(Application).where(
            Application.tenant_id == tenant_id, Application.product_id == p.id,
            Application.state == ApplicationState.COMPLETED, Application.started_at >= inicio)
        if farm_id:
            q = q.join(Mission, Mission.id == Application.mission_id).where(
                Mission.farm_id == farm_id)
        aplic = [(as_utc(a.started_at), float(a.amount_used_l))
                 for a in session.scalars(q.order_by(Application.started_at, Application.id))
                 if a.amount_used_l is not None]
        lotes = session.scalars(select(ProductBatch).where(
            ProductBatch.tenant_id == tenant_id, ProductBatch.product_id == p.id)
            .order_by(ProductBatch.code)).all()
        validos = [b for b in lotes if not b.is_expired(agora.date())]
        estoque = sum(float(b.quantity_l or 0.0) for b in validos)
        sem_quantidade = sum(1 for b in validos if b.quantity_l is None)
        comprometido, missoes = _comprometido(session, tenant_id, p.id, farm_id)
        linha: dict[str, Any] = {
            "product_id": p.id, "nome": p.name, "aplicacoes_na_janela": len(aplic),
            "consumo_na_janela_l": round(sum(qtd for _, qtd in aplic), 3),
            "estoque_l": round(estoque, 3), "lotes_validos": len(validos),
            "lotes_vencidos": len(lotes) - len(validos),
            "lotes_sem_quantidade": sem_quantidade,
            "comprometido_l": round(comprometido, 3), "missoes_comprometidas": missoes,
        }
        bl = blocos(aplic, agora=agora, horizonte_dias=h, janela_dias=janela,
                    mesma_epoca=mesma_epoca)
        com_dado = [b for b in bl if b > 0]
        if len(aplic) < min_aplic or len(com_dado) < min_blocos:
            linha["estimativa"] = None
            linha["motivo"] = (f"sem histórico suficiente para estimar: {len(aplic)} "
                               f"aplicação(ões) e {len(com_dado)} bloco(s) de {h} dias com "
                               f"consumo na janela (mínimo {min_aplic} e {min_blocos})")
            linha["reposicao"] = None
        else:
            media = bootstrap(bl, reamostragens=reamostragens, semente=SEMENTE)
            linha["estimativa"] = {
                "blocos": len(bl), "blocos_com_consumo": len(com_dado),
                "media_por_bloco_l": {k: round(v, 3) for k, v in media.items()},
                "um_bloco_l": {"p10": round(quantil(bl, 0.10), 3),
                               "p50": round(quantil(bl, 0.50), 3),
                               "p90": round(quantil(bl, 0.90), 3)},
                "metodo": f"bootstrap de {len(bl)} blocos de {h} dias, {reamostragens} "
                          "reamostragens",
            }
            disponivel = estoque - comprometido
            alto = linha["estimativa"]["um_bloco_l"]["p90"]
            central = linha["estimativa"]["um_bloco_l"]["p50"]
            linha["reposicao"] = {
                "disponivel_l": round(disponivel, 3),
                "cobre_cenario_central": disponivel >= central,
                "cobre_cenario_alto": disponivel >= alto,
                "falta_no_cenario_alto_l": round(max(0.0, alto - disponivel), 3),
                "possivel_reposicao": disponivel < alto,
            }
        if sem_quantidade:
            linha["aviso"] = (f"{sem_quantidade} lote(s) válido(s) sem quantidade cadastrada: o "
                              "estoque está subestimado")
        saida.append(linha)
    resultado = {"versao": VERSAO, "farm_id": farm_id, "horizonte_dias": h,
                 "produtos": saida,
                 "avisos": [] if produtos else ["nenhum produto cadastrado"],
                 "nota": "Cenários a partir do histórico, não previsão de safra: a decisão de "
                         "compra é de quem responde pelos insumos."}
    return resultado, pr.lista()
