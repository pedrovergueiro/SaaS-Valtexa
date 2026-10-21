"""Enxame: quem vai olhar onde, agora — alocação dinâmica entre Rovers, drone e base.

O gêmeo digital de VALTEXA-B diz **onde vale olhar** (``GET /fields/{id}/gemeo/prioridades``:
o valor da informação por trecho de rua, pela incerteza e pelo risco). Este serviço decide
**quem** olha, com o que cada dispositivo pode e tem agora:

* **Tarefas**: ``inspecao`` (trecho de rua, Rover), ``verificacao`` (o talhão tratado, de
  volta depois da aplicação — obrigatória, vai primeiro) e ``sobrevoo`` (bloco, drone).
* **Agentes**: os dispositivos **DISPONÍVEIS** da fazenda (:mod:`valtexa.services.fleet_state`):
  o orçamento de tempo é a autonomia vezes a bateria acima da reserva; o custo de uma tarefa,
  o deslocamento de onde o robô está até ela mais o percurso de trabalho, na velocidade dele.
* **Guloso por valor por segundo**: a cada passo, a tarefa e o agente de maior valor por
  tempo gasto que ainda cabem no orçamento. Quando Rover e drone cobririam as mesmas plantas,
  a segunda tarefa vale menos (``desconto_sobreposicao``: a primeira já tirou parte da dúvida).
* **Horizonte rolante**: cada plano entrega a cada agente **a próxima missão** — os trechos
  contíguos da mesma rua do começo da fila dele, juntos num polígono. Quando o robô termina
  (ou a frota muda, ou o gêmeo muda), o plano é refeito com o estado novo. É a alocação
  dinâmica sem mexer no que a missão é: uma por robô, autorizada pela camada de segurança e
  assinada pela plataforma.

Limites, de propósito:

* **Aplicação não é alocada aqui.** Sai da prescrição, com aprovação do agrônomo
  (``services/decision_engine.py`` e ``docs/MISSIONS.md``); o plano só a lista.
* **Sobrevoo de observação não vira missão.** A camada de segurança só aceita missão sem
  aplicação feita por Rover, e não existe regra de voo sem aplicação (vento, RTK, margem de
  energia estão escritos para a pulverização). O plano mostra o sobrevoo e o valor dele;
  criar a missão é recusado até essa regra existir — decisão de segurança, não de código.
* **Sem internet, a base não realoca**: realocar é criar missão, e missão só a plataforma
  assina. Cada robô termina a que tem (política offline), e o console da base arma as do
  cache (``VALTEXA-BASE/valtexa_base/missoes.py``).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterable, Sequence
from dataclasses import asdict, dataclass, field
from typing import Any

from valtexa.services import geo

TIPOS = ("inspecao", "verificacao", "sobrevoo")
TIPO_DO_AGENTE = {"inspecao": "rover", "verificacao": "rover", "sobrevoo": "drone"}
MISSAO_DO_TIPO = {"inspecao": "scout", "verificacao": "verify"}
"""O tipo de missão em que cada tarefa vira. Sobrevoo não tem (ver o topo do módulo)."""
SOBRECARGA_S = {"rover": 60.0, "drone": 90.0}
"""Por tarefa: o Rover manobra na cabeceira; o drone sobe, estabiliza e desce."""
RESERVA_BATERIA = 0.25
DESCONTO_SOBREPOSICAO = 0.5
CONTIGUO_M = 3.0
"""Dois trechos da mesma rua a menos disso viram a mesma missão."""


@dataclass(frozen=True)
class Tarefa:
    id: str
    tipo: str
    valor: float
    centro: tuple[float, float] | None
    """``(lon, lat)``."""
    poligono: list[list[float]] | None
    comprimento_m: float
    area_m2: float = 0.0
    plantas: frozenset[str] = frozenset()
    ruas: tuple[str, ...] = ()
    x_inicio_m: float = 0.0
    x_fim_m: float = 0.0
    obrigatoria: bool = False
    motivo: str = ""
    origem: str = "gemeo"
    dias_sem_ver: int | None = None
    """Do gêmeo: há quantos dias o trecho não é visto (``None``: nunca)."""

    def resumo(self) -> dict[str, Any]:
        d = asdict(self)
        d["plantas"] = len(self.plantas)
        d["centro"] = list(self.centro) if self.centro else None
        d["ruas"] = list(self.ruas)
        return d


@dataclass(frozen=True)
class Agente:
    device_id: str
    nome: str
    tipo: str
    """``rover`` ou ``drone``."""
    velocidade_ms: float
    largura_m: float
    orcamento_s: float
    posicao: tuple[float, float] | None
    bateria: float | None = None


@dataclass
class Atribuicao:
    agente: Agente
    tarefas: list[Tarefa] = field(default_factory=list)
    tempo_s: float = 0.0
    valor: float = 0.0
    bytes: float = 0.0
    """Bytes estimados pela Starlink do agente (só quando o plano tem orçamento de dados)."""

    def to_dict(self) -> dict[str, Any]:
        d = {"device_id": self.agente.device_id, "nome": self.agente.nome,
             "tipo": self.agente.tipo, "tempo_s": round(self.tempo_s, 1),
             "orcamento_s": round(self.agente.orcamento_s, 1),
             "valor": round(self.valor, 4),
             "tarefas": [t.id for t in self.tarefas]}
        if self.bytes:
            d["bytes_estimados"] = round(self.bytes)
        return d


@dataclass
class Plano:
    atribuicoes: list[Atribuicao]
    nao_atribuidas: list[tuple[Tarefa, str]]
    tarefas: dict[str, Tarefa]
    parametros: dict[str, Any]

    @property
    def valor_total(self) -> float:
        return sum(a.valor for a in self.atribuicoes)

    def to_dict(self) -> dict[str, Any]:
        return {"parametros": self.parametros,
                "valor_alocado": round(self.valor_total, 4),
                "valor_disponivel": round(sum(t.valor for t in self.tarefas.values()), 4),
                "atribuicoes": [a.to_dict() for a in self.atribuicoes],
                "nao_atribuidas": [{"tarefa": t.id, "tipo": t.tipo, "valor": round(t.valor, 4),
                                    "motivo": m} for t, m in self.nao_atribuidas],
                "tarefas": {i: t.resumo() for i, t in self.tarefas.items()},
                "proximas_missoes": proximas_missoes(self)}


def distancia_m(a: tuple[float, float] | None, b: tuple[float, float] | None) -> float:
    """Em metros (``(lon, lat)``); sem posição conhecida, zero."""
    if a is None or b is None:
        return 0.0
    return geo.haversine_m(a[0], a[1], b[0], b[1])


def tempo_de_trabalho_s(tarefa: Tarefa, agente: Agente) -> float:
    """O percurso de trabalho: o comprimento das ruas (Rover) ou a área pela largura da faixa
    (drone), o que for maior, na velocidade do agente, mais a sobrecarga por tarefa."""
    percurso = tarefa.comprimento_m
    if tarefa.area_m2 and agente.largura_m > 0:
        percurso = max(percurso, tarefa.area_m2 / agente.largura_m)
    return percurso / agente.velocidade_ms + SOBRECARGA_S.get(agente.tipo, 60.0)


def compativel(tarefa: Tarefa, agente: Agente) -> bool:
    return TIPO_DO_AGENTE.get(tarefa.tipo) == agente.tipo


def _valor_efetivo(tarefa: Tarefa, cobertas: dict[str, set[str]], desconto: float) -> float:
    if not tarefa.plantas or desconto <= 0:
        return tarefa.valor
    outras = set().union(*(p for tipo, p in cobertas.items() if tipo != tarefa.tipo))
    if not outras:
        return tarefa.valor
    fracao = len(tarefa.plantas & outras) / len(tarefa.plantas)
    return tarefa.valor * (1.0 - desconto * fracao)


Restricao = Callable[[Tarefa, Agente], tuple[float, str | None]]
"""``(segundos a mais, motivo de exclusão)`` de uma tarefa para um agente: o desvio de um
obstáculo, a encosta que deixa o Rover mais lento — ou, com motivo, "este agente não pode"
(declividade acima do limite dele, trecho dentro de mata). Ver ``valtexa/planejamento``."""


def alocar(tarefas: Iterable[Tarefa], agentes: Sequence[Agente], *,
           desconto_sobreposicao: float = DESCONTO_SOBREPOSICAO,
           restricao: Restricao | None = None,
           bytes_da_tarefa: Callable[[Tarefa, Agente], float] | None = None,
           orcamento_bytes: dict[str, float] | None = None) -> Plano:
    """O plano: as obrigatórias primeiro (a de menor custo que couber), depois o guloso.

    Opcionais (o planejamento do cérebro usa; o plano do enxame de sempre, não):
    ``restricao`` soma tempo ou exclui o par tarefa-agente; ``bytes_da_tarefa`` com
    ``orcamento_bytes`` (por ``device_id``) é o teto de dados da Starlink de cada agente —
    a tarefa que não cabe no que resta do dia fica de fora, com o motivo.
    """
    todas = {t.id: t for t in tarefas}
    livres = dict(todas)
    atrib = {a.device_id: Atribuicao(a) for a in agentes}
    fim = {a.device_id: a.posicao for a in agentes}
    cobertas: dict[str, set[str]] = {}
    orcamento_bytes = orcamento_bytes or {}

    def custo(t: Tarefa, a: Agente) -> float | None:
        extra = 0.0
        if restricao is not None:
            extra, motivo = restricao(t, a)
            if motivo is not None:
                return None
        return (distancia_m(fim[a.device_id], t.centro) / a.velocidade_ms
                + tempo_de_trabalho_s(t, a) + extra)

    def cabe_nos_dados(t: Tarefa, a: Agente) -> bool:
        if bytes_da_tarefa is None or a.device_id not in orcamento_bytes:
            return True
        return atrib[a.device_id].bytes + bytes_da_tarefa(t, a) <= orcamento_bytes[a.device_id]

    def cabe(t: Tarefa, a: Agente) -> float | None:
        c = custo(t, a)
        if c is None or not cabe_nos_dados(t, a):
            return None
        resta = a.orcamento_s - atrib[a.device_id].tempo_s
        return c if c <= resta else None

    def atribuir(t: Tarefa, a: Agente, c: float, v: float) -> None:
        at = atrib[a.device_id]
        at.tarefas.append(t)
        at.tempo_s += c
        at.valor += v
        if bytes_da_tarefa is not None:
            at.bytes += bytes_da_tarefa(t, a)
        fim[a.device_id] = t.centro or fim[a.device_id]
        cobertas.setdefault(t.tipo, set()).update(t.plantas)
        del livres[t.id]

    for t in sorted((t for t in todas.values() if t.obrigatoria), key=lambda t: -t.valor):
        opcoes = [(c, a) for a in agentes if compativel(t, a) and (c := cabe(t, a)) is not None]
        if opcoes:
            c, a = min(opcoes, key=lambda x: x[0])
            atribuir(t, a, c, t.valor)
    while True:
        melhor: tuple[float, Tarefa, Agente, float, float] | None = None
        for t in livres.values():
            if t.obrigatoria:
                continue
            v = _valor_efetivo(t, cobertas, desconto_sobreposicao)
            if v <= 0:
                continue
            for a in agentes:
                if not compativel(t, a):
                    continue
                c = cabe(t, a)
                if c is None:
                    continue
                razao = v / max(c, 1e-9)
                if melhor is None or razao > melhor[0]:
                    melhor = (razao, t, a, c, v)
        if melhor is None:
            break
        _, t, a, c, v = melhor
        atribuir(t, a, c, v)
    nao = []
    for t in sorted(livres.values(), key=lambda t: -t.valor):
        nao.append((t, _motivo_de_fora(t, agentes, atrib, custo, restricao=restricao,
                                       cabe_nos_dados=cabe_nos_dados)))
    parametros: dict[str, Any] = {"desconto_sobreposicao": desconto_sobreposicao,
                                  "agentes": [asdict(a) for a in agentes]}
    if orcamento_bytes:
        parametros["orcamento_bytes"] = {k: round(v) for k, v in orcamento_bytes.items()}
    return Plano([at for at in atrib.values() if at.tarefas], nao, todas, parametros)


def _motivo_de_fora(t: Tarefa, agentes: Sequence[Agente], atrib: dict[str, Atribuicao],
                    custo, *, restricao: Restricao | None = None,
                    cabe_nos_dados=None) -> str:
    compativeis = [a for a in agentes if compativel(t, a)]
    if not compativeis:
        return f"nenhum {TIPO_DO_AGENTE.get(t.tipo, '?')} disponível na fazenda"
    if t.valor <= 0:
        return "valor zero: olhar não muda a decisão sobre essas plantas"
    if restricao is not None:
        motivos = [m for a in compativeis if (m := restricao(t, a)[1]) is not None]
        if len(motivos) == len(compativeis):
            return "; ".join(sorted(set(motivos)))
        compativeis = [a for a in compativeis if restricao(t, a)[1] is None]
    if cabe_nos_dados is not None and not any(cabe_nos_dados(t, a) for a in compativeis):
        return ("não cabe no orçamento de dados da Starlink que resta hoje a nenhum agente "
                "(o que ele mandaria passaria do teto do dia)")
    menor = min(custo(t, a) for a in compativeis)
    resta = max(a.orcamento_s - atrib[a.device_id].tempo_s for a in compativeis)
    if menor > max(a.orcamento_s for a in compativeis):
        return (f"não cabe na autonomia de nenhum: precisa de {menor / 60:.0f} min, o maior "
                f"orçamento é {max(a.orcamento_s for a in compativeis) / 60:.0f} min")
    return (f"o orçamento acabou em tarefas que valiam mais por minuto (resta "
            f"{resta / 60:.0f} min; esta pede {menor / 60:.0f})")


def _contiguas(a: Tarefa, b: Tarefa) -> bool:
    return (a.tipo == b.tipo == "inspecao" and len(a.ruas) == len(b.ruas) == 1
            and a.ruas == b.ruas and 0 <= b.x_inicio_m - a.x_fim_m <= CONTIGUO_M)


def _envolve(poligonos: Sequence[list[list[float]]]) -> list[list[float]]:
    lons = [p[0] for poli in poligonos for p in poli]
    lats = [p[1] for poli in poligonos for p in poli]
    a, b, c, d = min(lons), max(lons), min(lats), max(lats)
    return [[a, c], [b, c], [b, d], [a, d], [a, c]]


def proximas_missoes(plano: Plano) -> list[dict[str, Any]]:
    """A próxima missão de cada agente: o começo da fila dele, juntando os trechos contíguos
    da mesma rua (na ordem do eixo) num retângulo só."""
    saida = []
    for at in plano.atribuicoes:
        primeira = at.tarefas[0]
        kind = MISSAO_DO_TIPO.get(primeira.tipo)
        grupo = [primeira]
        if primeira.tipo == "inspecao":
            # O bloco contíguo da mesma rua que contém a primeira, nos dois sentidos do eixo
            # (o desconto de sobreposição pode pôr na frente um trecho do meio do bloco).
            mesma_rua = sorted((t for t in at.tarefas if t.ruas == primeira.ruas),
                               key=lambda t: t.x_inicio_m)
            i = mesma_rua.index(primeira)
            ini, fim = i, i
            while ini > 0 and _contiguas(mesma_rua[ini - 1], mesma_rua[ini]):
                ini -= 1
            while fim + 1 < len(mesma_rua) and _contiguas(mesma_rua[fim], mesma_rua[fim + 1]):
                fim += 1
            grupo = mesma_rua[ini:fim + 1]
        poligonos = [t.poligono for t in grupo if t.poligono]
        saida.append({
            "device_id": at.agente.device_id, "tipo": primeira.tipo, "mission_kind": kind,
            "tarefas": [t.id for t in grupo],
            "primeira": primeira.id,
            "poligono": _envolve(poligonos) if len(poligonos) == len(grupo) else None,
            "valor": round(sum(t.valor for t in grupo), 4),
            "pode_criar": kind is not None and len(poligonos) == len(grupo),
            "motivo": None if kind is not None and len(poligonos) == len(grupo) else (
                "sobrevoo de observação: sem regra de segurança de voo sem aplicação"
                if kind is None else "tarefa sem polígono: as plantas não têm GPS"),
        })
    return saida


def impressao(entradas: dict[str, Any]) -> str:
    """SHA-256 das entradas do plano (frota e tarefas): mudou, o plano está desatualizado."""
    texto = json.dumps(entradas, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Com o banco: a frota, as tarefas, o plano guardado e as missões
# ---------------------------------------------------------------------------

BATERIA_DESCONHECIDA = 0.5
"""Sem leitura de bateria, o plano conta meia carga: errar para menos é voltar cedo; errar
para mais é o robô parado no meio do talhão."""
PLANO_VALE_S = 6 * 3600
"""Depois disso o plano é velho mesmo sem a frota mudar: o gêmeo já andou."""


def _aproxima(v: float | None, passo: float) -> float | None:
    return None if v is None else round(round(v / passo) * passo, 6)


def agentes_da_fazenda(session, *, tenant_id: str, farm_id: str, now=None,
                       reserva: float = RESERVA_BATERIA
                       ) -> tuple[list[Agente], list[dict[str, Any]]]:
    """Os Rovers e drones DISPONÍVEIS da fazenda, e os de fora com o porquê."""
    from datetime import UTC, datetime

    from sqlalchemy import select

    from valtexa.models import Device, DeviceKind
    from valtexa.services import fleet_state
    from valtexa.services.hal import capabilities_of

    agora = now or datetime.now(UTC)
    agentes, fora = [], []
    rows = session.scalars(select(Device).where(
        Device.tenant_id == tenant_id, Device.farm_id == farm_id,
        Device.kind.in_([DeviceKind.ROVER, DeviceKind.DRONE])).order_by(Device.name))
    for d in rows:
        situacao = fleet_state.derive(d, agora)
        if situacao.state is not fleet_state.FleetState.DISPONIVEL:
            fora.append({"device_id": d.id, "nome": d.name, "estado": situacao.state.value,
                         "motivo": situacao.reason})
            continue
        cap = capabilities_of(d.capabilities)
        carga = (d.battery_percent / 100.0 if d.battery_percent is not None
                 else BATERIA_DESCONHECIDA)
        orcamento = cap.endurance_minutes * 60.0 * max(0.0, carga - reserva)
        if orcamento <= 0:
            fora.append({"device_id": d.id, "nome": d.name, "estado": "reserva",
                         "motivo": f"bateria {carga:.0%}, abaixo da reserva de {reserva:.0%}"})
            continue
        posicao = ((d.last_lon, d.last_lat)
                   if d.last_lon is not None and d.last_lat is not None else None)
        agentes.append(Agente(d.id, d.name, "rover" if d.kind is DeviceKind.ROVER else "drone",
                              cap.cruise_speed_ms, cap.swath_m, orcamento, posicao,
                              d.battery_percent))
    return agentes, fora


def impressao_da_frota(agentes: Sequence[Agente], fora: Sequence[dict[str, Any]]) -> str:
    """A frota como o plano a leu, arredondada (bateria de 5 em 5%, posição de ~10 m): o que
    muda a alocação muda a impressão; o ruído da telemetria, não."""
    return impressao({
        "agentes": [{"id": a.device_id, "bat": _aproxima(a.bateria, 5.0),
                     "pos": None if a.posicao is None else
                     [_aproxima(a.posicao[0], 1e-4), _aproxima(a.posicao[1], 1e-4)]}
                    for a in agentes],
        "fora": sorted((f["device_id"], f["estado"]) for f in fora)})


def tarefas_do_gemeo(corpo: dict[str, Any], field_id: str) -> list[Tarefa]:
    """As tarefas que o gêmeo de VALTEXA-B priorizou (``/gemeo/prioridades``)."""
    saida = []
    for t in corpo.get("tarefas", []):
        poli = t.get("poligono")
        centro = tuple(geo.centroid(poli)) if poli else None
        chave = f"{t['tipo']}|{field_id}|{','.join(t['ruas'])}|{t['x_inicio_m']}|{t['x_fim_m']}"
        saida.append(Tarefa(
            id=f"{t['tipo']}-{hashlib.sha1(chave.encode()).hexdigest()[:10]}",
            tipo=t["tipo"], valor=float(t["valor"]), centro=centro, poligono=poli,
            comprimento_m=float(t.get("comprimento_m") or 0.0),
            area_m2=float(t.get("area_m2") or 0.0),
            plantas=frozenset(t.get("plant_ids") or ()), ruas=tuple(t.get("ruas") or ()),
            x_inicio_m=float(t["x_inicio_m"]), x_fim_m=float(t["x_fim_m"]),
            motivo=t.get("motivo", ""), origem="gemeo", dias_sem_ver=t.get("dias_sem_ver")))
    return saida


def tarefas_de_verificacao(session, *, tenant_id: str, field_row, now=None) -> list[Tarefa]:
    """As verificações pós-aplicação vencidas do talhão: o Rover volta à área tratada."""
    from valtexa.models import Application, Mission
    from valtexa.services import verification

    saida = []
    espacamento = field_row.row_spacing_m or 3.5
    for v in verification.due(session, tenant_id, now=now):
        if v.field_id != field_row.id or v.verification_mission_id:
            continue
        aplicacao = session.get(Application, v.application_id)
        missao = session.get(Mission, aplicacao.mission_id) if aplicacao else None
        if missao is None or not missao.target_polygon:
            continue
        poli = [list(p) for p in missao.target_polygon]
        area = geo.area_ha(poli) * 10_000.0
        saida.append(Tarefa(
            id=f"verificacao-{v.id}", tipo="verificacao", valor=0.0,
            centro=tuple(geo.centroid(poli)), poligono=poli,
            comprimento_m=area / espacamento, area_m2=area, obrigatoria=True,
            motivo="verificação pós-aplicação vencida: nada é eficaz sem a segunda passada",
            origem="verificacao"))
    return saida


def planejar(session, *, tenant_id: str, field_row, tarefas: Sequence[Tarefa],
             agentes: Sequence[Agente], fora: Sequence[dict[str, Any]],
             entradas: dict[str, Any], actor_id: str | None = None,
             desconto_sobreposicao: float = DESCONTO_SOBREPOSICAO, alocador=None):
    """Aloca, guarda como o plano ativo do talhão (o anterior vira ``substituido``) e audita.

    ``alocador(tarefas, agentes)``: o alocador com as restrições do talhão (inclinação,
    obstáculos, dados da Starlink, calibração — ``planejamento.robotico.Contexto.alocar``);
    sem ele, o de sempre."""
    from sqlalchemy import func, select

    from valtexa.models import ActorType, SubjectType
    from valtexa.models.enxame import PlanoDoEnxame
    from valtexa.services import audit

    plano = (alocador(tarefas, agentes) if alocador is not None
             else alocar(tarefas, agentes, desconto_sobreposicao=desconto_sobreposicao))
    corpo = plano.to_dict()
    corpo["fora_da_frota"] = list(fora)
    for anterior in session.scalars(select(PlanoDoEnxame).where(
            PlanoDoEnxame.field_id == field_row.id, PlanoDoEnxame.estado == "ativo")):
        anterior.estado = "substituido"
    versao = (session.scalar(select(func.max(PlanoDoEnxame.versao)).where(
        PlanoDoEnxame.field_id == field_row.id)) or 0) + 1
    row = PlanoDoEnxame(tenant_id=tenant_id, farm_id=field_row.farm_id, field_id=field_row.id,
                        versao=versao, estado="ativo",
                        entradas_sha256=impressao_da_frota(agentes, fora), entradas=entradas,
                        plano=corpo, created_by=actor_id)
    session.add(row)
    session.flush()
    audit.record(session, tenant_id=tenant_id, action="enxame.plano",
                 subject_type=SubjectType.FIELD, subject_id=field_row.id,
                 actor_type=ActorType.USER if actor_id else ActorType.SYSTEM, actor_id=actor_id,
                 payload={"plano_id": row.id, "versao": versao,
                          "agentes": len(agentes), "tarefas": len(tarefas),
                          "valor_alocado": corpo["valor_alocado"],
                          "atribuicoes": [a["device_id"] for a in corpo["atribuicoes"]]})
    return row


def situacao_do_plano(session, row, *, tenant_id: str, now=None) -> dict[str, Any]:
    """O plano com a pergunta que importa: ele ainda vale para a frota de agora?"""
    from datetime import UTC, datetime

    from valtexa.models.base import as_utc

    agora = now or datetime.now(UTC)
    agentes, fora = agentes_da_fazenda(session, tenant_id=tenant_id, farm_id=row.farm_id,
                                       now=agora)
    idade = (agora - as_utc(row.created_at)).total_seconds()
    motivos = []
    if impressao_da_frota(agentes, fora) != row.entradas_sha256:
        motivos.append("a frota mudou (disponibilidade, bateria ou posição) desde o plano")
    if idade > PLANO_VALE_S:
        motivos.append(f"o plano tem {idade / 3600:.0f} h: o gêmeo já andou")
    return {"plano_id": row.id, "versao": row.versao, "estado": row.estado,
            "criado_em": as_utc(row.created_at).isoformat(), "desatualizado": bool(motivos),
            "motivos": motivos, **row.plano}


def criar_missoes(session, row, *, field_row, device_ids: Sequence[str] | None = None,
                  actor_id: str | None = None, now=None) -> list[dict[str, Any]]:
    """A próxima missão de cada agente do plano, em ``DRAFT``: daí em diante, o fluxo de
    sempre (``authorize`` pela camada de segurança, ``dispatch`` assinado)."""
    from datetime import UTC, datetime

    from valtexa.models import ActorType, Device, MissionKind, SubjectType
    from valtexa.services import audit, fleet_state, mission_manager

    agora = now or datetime.now(UTC)
    criadas = dict(row.plano.get("criadas") or {})
    saida = []
    for pm in row.plano.get("proximas_missoes", []):
        dev_id = pm["device_id"]
        if device_ids is not None and dev_id not in device_ids:
            continue
        if dev_id in criadas:
            saida.append({"device_id": dev_id, "mission_id": criadas[dev_id],
                          "motivo": "já criada por este plano"})
            continue
        if not pm["pode_criar"]:
            saida.append({"device_id": dev_id, "mission_id": None, "motivo": pm["motivo"]})
            continue
        device = session.get(Device, dev_id)
        if device is None or device.tenant_id != row.tenant_id:
            saida.append({"device_id": dev_id, "mission_id": None,
                          "motivo": "dispositivo não encontrado"})
            continue
        situacao = fleet_state.derive(device, agora)
        if situacao.state is not fleet_state.FleetState.DISPONIVEL:
            saida.append({"device_id": dev_id, "mission_id": None,
                          "motivo": f"não está mais disponível: {situacao.reason} "
                                    "Refaça o plano."})
            continue
        missao = mission_manager.create_mission(
            session, tenant_id=row.tenant_id, kind=MissionKind(pm["mission_kind"]),
            field_row=field_row, device=device, target_polygon=pm["poligono"],
            created_by=actor_id)
        criadas[dev_id] = missao.id
        audit.record(session, tenant_id=row.tenant_id, action="enxame.missao",
                     subject_type=SubjectType.MISSION, subject_id=missao.id,
                     actor_type=ActorType.USER if actor_id else ActorType.SYSTEM,
                     actor_id=actor_id,
                     payload={"plano_id": row.id, "versao": row.versao,
                              "tarefas": pm["tarefas"], "valor": pm["valor"]})
        saida.append({"device_id": dev_id, "mission_id": missao.id, "motivo": None})
    row.plano = {**row.plano, "criadas": criadas}
    return saida
