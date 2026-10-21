"""Compartilhamento controlado: o que cada dispositivo recebe do que o enxame sabe.

O princípio é o da necessidade de saber, escrito como tabela (:data:`POLITICA`) e não como
``if`` espalhado:

* **o Rover** recebe, dentro da missão assinada, as **prioridades** dos trechos que a missão
  cobre (onde vale gastar a percepção ativa) — do talhão da missão, de mais nada;
* **o drone** recebe a missão de aplicação; prioridade de inspeção não é assunto dele.

(Até 20/10/2026 havia também o mapa de cobertura do rádio e a base da fazenda; os dois foram
arquivados com o rádio — cada Rover tem a própria Starlink.)

O que **nunca** desce para dispositivo: imagem, posterior por planta, os números do produtor
(custo, perda, preço), dado de outro talhão ou de outra fazenda.

**Anti-eco.** A prioridade desce para **decidir** a bordo — onde olhar de novo, o que subir
primeiro —, nunca como evidência. O que o Rover vê sobe puro (a razão de verossimilhança dos
recortes), e o gêmeo assimila uma vez só. Se o prior fundido voltasse como evidência, a
mesma observação seria contada duas vezes, e a cada ciclo a certeza cresceria sem nenhum
dado novo. Por isso o valor vai **relativo** (0 a 1 entre os trechos da missão) e marcado
``uso``.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from valtexa.models import DeviceKind
from valtexa.services import geo

PRIORIDADES = "prioridades"
APLICACAO = "aplicacao"

POLITICA: dict[DeviceKind, frozenset[str]] = {
    DeviceKind.ROVER: frozenset({PRIORIDADES}),
    DeviceKind.DRONE: frozenset({APLICACAO}),
    DeviceKind.DOCK: frozenset(),
}
PRIORIDADES_VALEM = timedelta(hours=24)
MAX_TRECHOS = 400
"""Teto de trechos na missão: o corpo vai assinado e conta no orçamento da Starlink."""
USO = ("decidir a bordo (percepção ativa, ordem de envio); não é evidência e não volta ao "
       "gêmeo como observação")


def pode_receber(kind: DeviceKind, classe: str) -> bool:
    return classe in POLITICA.get(kind, frozenset())


def prioridades_para_missao(session, mission, device_kind: DeviceKind) -> dict[str, Any] | None:
    """Os trechos priorizados do plano ativo do talhão que caem na área da missão.

    ``None`` quando a política não deixa, quando não há plano ou quando ele venceu.
    """
    from sqlalchemy import select

    from valtexa.models.base import as_utc, utcnow
    from valtexa.models.enxame import PlanoDoEnxame

    if not pode_receber(device_kind, PRIORIDADES):
        return None
    row = session.scalars(select(PlanoDoEnxame).where(
        PlanoDoEnxame.tenant_id == mission.tenant_id,
        PlanoDoEnxame.field_id == mission.field_id,
        PlanoDoEnxame.estado == "ativo").order_by(PlanoDoEnxame.versao.desc())).first()
    if row is None:
        return None
    criado = as_utc(row.created_at)
    if utcnow() - criado > PRIORIDADES_VALEM:
        return None
    tarefas = [t for t in (row.plano.get("tarefas") or {}).values()
               if t["tipo"] == "inspecao" and t.get("centro")
               and geo.contains_point(mission.target_polygon, *t["centro"],
                                      include_boundary=True)]
    if not tarefas:
        return None
    maior = max(t["valor"] for t in tarefas) or 1.0
    tarefas.sort(key=lambda t: -t["valor"])
    return {
        "plano_id": row.id, "versao": row.versao, "gerado_em": criado.isoformat(),
        "valido_ate": (criado + PRIORIDADES_VALEM).isoformat(), "uso": USO,
        "trechos": [{"ruas": t["ruas"], "x_inicio_m": t["x_inicio_m"], "x_fim_m": t["x_fim_m"],
                     "prioridade": round(t["valor"] / maior, 4)}
                    for t in tarefas[:MAX_TRECHOS]],
    }
