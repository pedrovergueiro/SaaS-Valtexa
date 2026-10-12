"""Planejamento de cobertura: rota, tempo, energia e onde ficam os postes.

Responde à pergunta que decide a viabilidade de um talhão antes de qualquer
robô entrar nele: **quanto tempo leva, e o rover consegue?** E, quando não
consegue de uma carga só, **onde precisa ter poste de recarga**.

A conta é determinística de ponta a ponta. Entra um polígono, a direção das
linhas de plantio e o perfil de autonomia do rover; sai a rota em vaivém, a
distância, o tempo, a curva de carga ao longo do percurso e a posição de cada
poste. Nada aqui é estimado por modelo estatístico — e é de propósito: um
número inventado sobre autonomia manda um rover de 98 kg para o meio de uma
lavoura e o deixa lá.

**O que é medido e o que é hipótese.** A geometria (distância, área, tempo a
uma velocidade dada) é exata. O consumo não: ele vem de dois coeficientes —
energia por metro rodado e energia por hora ligada — que começam **derivados do
datasheet** e só viram medição depois que missões reais rodarem. É o que
:func:`calibrate` faz, por mínimos quadrados sobre a telemetria. Enquanto não
houver dado de campo, o plano sai marcado como estimativa, e o
:class:`PlanoDeCobertura` diz qual das duas coisas ele é.

**Por que dois coeficientes e não "km por carga".** Um rover parado com câmera,
LiDAR e Jetson ligados gasta energia sem andar um metro. Um plano com muitas
manobras curtas gasta muito mais tempo do que distância. Um coeficiente só
erraria para os dois lados, e erraria mais justamente na lavoura de café, que é
onde o percurso tem mais curva do que reta.
"""

from __future__ import annotations

import math
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import timedelta
from itertools import pairwise

from valtexa.services import geo
from valtexa.services.hal import Capabilities

FRACAO_HOTEL = 0.35
"""Quanto do consumo de cruzeiro é carga fixa (sensores, computador, rádio).

HIPÓTESE, para repartir o número único do datasheet — autonomia a uma
velocidade — em dois coeficientes. Não é medição, e é o primeiro valor que a
calibração substitui. Se o perfil já trouxer os dois coeficientes medidos, esta
constante não é usada.
"""

MARGEM_DE_OBSTACULO_M = 2.0
"""Folga entre a passada e a borda de um obstáculo, além da largura do rover.

O obstáculo raramente tem borda exata. Quando vem da leitura de imagem, o
contorno é o retângulo de uma grade de blocos, e o bloco tem dezenas de metros
de lado; quando vem de alguém desenhando no mapa, tem o erro da mão. Raspar essa
borda é entrar no obstáculo.

Dois metros é folga de robô de 98 kg com direção diferencial, não de trator.
Quem conhece o talhão aumenta pelo parâmetro; o padrão erra para o lado seguro,
que é o lado em que o rover não fica preso no mato.
"""

SEGUNDOS_POR_MANOBRA = 12.0
"""Tempo parado na cabeceira, entre uma passada e a seguinte.

ESTIMATIVA. Numa lavoura de café com 33 ruas, a diferença entre 5 s e 20 s por
manobra é meia hora de missão — por isso o número aparece no plano em vez de
ficar diluído numa velocidade média.
"""


@dataclass(frozen=True, slots=True)
class PerfilDeAutonomia:
    """O que o rover aguenta. É o que o painel administrativo cadastra."""

    battery_wh: float
    speed_ms: float
    swath_m: float
    wh_per_m: float
    """Energia de tração por metro rodado."""

    wh_per_h: float
    """Carga fixa por hora ligada, ande ou não."""

    reserve_percent: float = 20.0
    """Reserva intocável. O plano nunca programa o rover para abaixo disto."""

    charge_kw: float = 2.5
    """Potência do poste de recarga."""

    charge_to_percent: float = 100.0
    medido: bool = False
    """Se os coeficientes vieram de telemetria ou do datasheet."""

    @property
    def usable_wh(self) -> float:
        return self.battery_wh * (1.0 - self.reserve_percent / 100.0)

    def custo_wh(self, metros: float, segundos: float) -> float:
        """Energia para percorrer ``metros`` gastando ``segundos``."""
        return metros * self.wh_per_m + segundos / 3600.0 * self.wh_per_h

    def minutos_de_recarga(self, wh: float) -> float:
        """Tempo para repor ``wh`` no poste."""
        if self.charge_kw <= 0:
            return 0.0
        return wh / (self.charge_kw * 1000.0) * 60.0

    @classmethod
    def from_capabilities(
        cls, capabilities: Capabilities, **override: float
    ) -> PerfilDeAutonomia:
        """Deriva o perfil do descritor de hardware do modelo.

        O datasheet dá autonomia a uma velocidade; daí sai a potência média de
        cruzeiro, que :data:`FRACAO_HOTEL` reparte entre carga fixa e tração.
        A repartição é hipótese declarada — ver o cabeçalho do módulo.
        """
        battery_wh = capabilities.number("battery_wh", 1200.0)
        speed = max(0.1, capabilities.cruise_speed_ms)
        horas = max(0.1, capabilities.endurance_minutes / 60.0)

        potencia_media = battery_wh / horas
        wh_per_h = potencia_media * FRACAO_HOTEL
        wh_per_m = (potencia_media * (1 - FRACAO_HOTEL)) / (speed * 3600.0)

        valores = {
            "battery_wh": battery_wh,
            "speed_ms": speed,
            "swath_m": capabilities.swath_m,
            "wh_per_m": wh_per_m,
            "wh_per_h": wh_per_h,
            "charge_kw": capabilities.number("charge_kw", 2.5),
            "medido": False,
        }
        valores.update(override)
        return cls(**valores)  # type: ignore[arg-type]


@dataclass(frozen=True, slots=True)
class Poste:
    """Um ponto do percurso onde o rover precisa de energia para continuar."""

    ordem: int
    lat: float
    lon: float
    metros_no_percurso: float
    """Distância acumulada até aqui, desde o início."""

    bateria_na_chegada_percent: float
    """Com quanto o rover chega, se não recarregar antes."""

    minutos_de_recarga: float
    area_coberta_ha: float
    """Quanto do talhão já foi varrido quando ele chega aqui."""

    motivo: str


@dataclass(frozen=True, slots=True)
class PlanoDeCobertura:
    """O plano completo de um talhão."""

    area_ha: float
    swath_m: float
    azimute_deg: float
    velocidade_ms: float
    """A velocidade de cruzeiro que gerou o tempo estimado.

    Sai no plano porque quem valida a missão precisa poder discordar dela. Um
    "4 h 20" sem a velocidade ao lado é um número que só se aceita ou recusa
    inteiro; com ela, o operador que conhece o terreno vê que 1,2 m/s é otimista
    para aquela quadra em barro e sabe *por que* o tempo vai estourar.
    """

    passadas: int
    metros_de_linha: float
    metros_de_manobra: float
    metros_totais: float
    minutos_dirigindo: float
    minutos_de_manobra: float
    minutos_de_recarga: float
    minutos_totais: float
    wh_totais: float
    cargas: int
    area_contornada_ha: float = 0.0
    """Área dos obstáculos que a rota evita. Zero quando não há obstáculo."""

    postes: list[Poste] = field(default_factory=list)
    rota: list[list[tuple[float, float]]] = field(default_factory=list)
    perfil_medido: bool = False
    avisos: list[str] = field(default_factory=list)

    @property
    def duracao(self) -> timedelta:
        return timedelta(minutes=self.minutos_totais)

    @property
    def ha_por_hora(self) -> float:
        horas = self.minutos_totais / 60.0
        return self.area_ha / horas if horas else 0.0


def plan(
    polygon: list,
    perfil: PerfilDeAutonomia,
    *,
    azimute_deg: float = 90.0,
    swath_m: float | None = None,
    bateria_inicial_percent: float = 100.0,
    obstaculos: list[list] | None = None,
    margem_de_obstaculo_m: float = MARGEM_DE_OBSTACULO_M,
) -> PlanoDeCobertura:
    """Planeja a cobertura do polígono e diz onde faltará energia.

    ``azimute_deg`` é a direção das linhas de plantio. O rover anda **ao longo**
    delas: atravessar passaria por cima das plantas, e a câmera, feita para
    olhar a folha de lado, veria só o solo.

    ``obstaculos`` são polígonos em que o rover não entra. Cada passada que
    atravessaria um deles é cortada em duas, e o buraco vira manobra de
    cabeceira — o plano sai com mais passadas e menos metros de linha, que é
    exatamente o que acontece no campo.

    Passar obstáculo muda o número que o plano devolve, e muda para melhor: sem
    eles, o tempo e o número de postes saem de uma rota que atravessa a mata em
    linha reta, e o rover real não faz isso.
    """
    faixa = perfil.swath_m if swath_m is None else swath_m
    if faixa <= 0:
        raise ValueError("A largura da faixa precisa ser positiva.")

    legs = geo.boustrophedon(
        polygon,
        faixa,
        azimute_deg,
        obstacles=obstaculos,
        margin_m=margem_de_obstaculo_m,
    )
    area_ha = geo.area_ha(polygon)
    area_de_obstaculo = sum(geo.area_ha(ring) for ring in (obstaculos or []))

    # A rota real intercala passada e manobra: o deslocamento de cabeceira entre
    # duas passadas é percurso que gasta energia e não cobre lavoura nenhuma.
    metros_linha = sum(geo.path_length_m(leg) for leg in legs)
    metros_manobra = 0.0
    for anterior, seguinte in pairwise(legs):
        metros_manobra += geo.haversine_m(*anterior[-1], *seguinte[0])

    segundos_dirigindo = (metros_linha + metros_manobra) / perfil.speed_ms
    segundos_manobra = SEGUNDOS_POR_MANOBRA * max(0, len(legs) - 1)

    postes, cargas, wh_totais = _postes(
        legs, perfil, area_ha, metros_linha, bateria_inicial_percent
    )
    minutos_recarga = sum(poste.minutos_de_recarga for poste in postes)

    avisos: list[str] = []
    if not perfil.medido:
        avisos.append(
            "Consumo derivado do datasheet, não medido em campo. O tempo e o número "
            "de postes mudam quando a primeira missão real calibrar o perfil."
        )
    if cargas > 0 and perfil.charge_kw <= 0:
        avisos.append("O perfil não informa potência de recarga: o tempo parado saiu zerado.")
    if obstaculos:
        avisos.append(
            f"A rota contorna {len(obstaculos)} obstáculo(s), somando "
            f"{area_de_obstaculo:.2f} ha, com {margem_de_obstaculo_m:.0f} m de folga. "
            f"As passadas que os atravessavam foram partidas em duas."
        )

    return PlanoDeCobertura(
        area_ha=round(area_ha, 3),
        swath_m=faixa,
        azimute_deg=azimute_deg,
        velocidade_ms=round(perfil.speed_ms, 2),
        passadas=len(legs),
        metros_de_linha=round(metros_linha, 1),
        metros_de_manobra=round(metros_manobra, 1),
        metros_totais=round(metros_linha + metros_manobra, 1),
        minutos_dirigindo=round(segundos_dirigindo / 60.0, 1),
        minutos_de_manobra=round(segundos_manobra / 60.0, 1),
        minutos_de_recarga=round(minutos_recarga, 1),
        minutos_totais=round((segundos_dirigindo + segundos_manobra) / 60.0 + minutos_recarga, 1),
        wh_totais=round(wh_totais, 1),
        cargas=cargas,
        area_contornada_ha=round(area_de_obstaculo, 3),
        postes=postes,
        rota=[[(lat, lon) for lon, lat in leg] for leg in legs],
        perfil_medido=perfil.medido,
        avisos=avisos,
    )


def _postes(
    legs: list[list[tuple[float, float]]],
    perfil: PerfilDeAutonomia,
    area_ha: float,
    metros_linha_total: float,
    bateria_inicial_percent: float,
) -> tuple[list[Poste], int, float]:
    """Caminha o percurso gastando energia e marca onde ela acaba.

    O critério é chegar ao **próximo poste**, não voltar à base: é para isso que
    os postes existem. Por isso a marcação é gulosa — anda o máximo que a carga
    permite, planta um poste ali, e recomeça de carga cheia. Para um percurso em
    linha com capacidade constante, guloso dá o menor número de postes possível.
    """
    disponivel = perfil.battery_wh * (bateria_inicial_percent / 100.0) - perfil.battery_wh * (
        perfil.reserve_percent / 100.0
    )
    postes: list[Poste] = []
    wh_totais = 0.0
    percorrido = 0.0
    linha_percorrida = 0.0
    ordem = 0

    passos = list(_passos(legs))
    for lat, lon, metros, cobre in passos:
        segundos = metros / perfil.speed_ms
        custo = perfil.custo_wh(metros, segundos)

        if custo > disponivel and metros > 0:
            # A carga não alcança o próximo ponto: o poste fica onde o rover
            # ainda chega, que é o ponto anterior.
            ordem += 1
            gasto = perfil.usable_wh - disponivel
            postes.append(
                Poste(
                    ordem=ordem,
                    lat=lat,
                    lon=lon,
                    metros_no_percurso=round(percorrido, 1),
                    bateria_na_chegada_percent=round(
                        max(0.0, disponivel) / perfil.battery_wh * 100.0
                        + perfil.reserve_percent,
                        1,
                    ),
                    minutos_de_recarga=round(perfil.minutos_de_recarga(gasto), 1),
                    area_coberta_ha=round(
                        area_ha * (linha_percorrida / metros_linha_total)
                        if metros_linha_total
                        else 0.0,
                        3,
                    ),
                    motivo=(
                        f"A carga acaba aqui: seguir sem recarregar levaria o rover abaixo "
                        f"da reserva de {perfil.reserve_percent:.0f}%."
                    ),
                )
            )
            disponivel = perfil.usable_wh

        disponivel -= custo
        wh_totais += custo
        percorrido += metros
        if cobre:
            linha_percorrida += metros

    return postes, len(postes), wh_totais


def _passos(
    legs: list[list[tuple[float, float]]], passo_m: float = 25.0
) -> Iterator[tuple[float, float, float, bool]]:
    """Quebra a rota em trechos curtos, para a simulação ter resolução.

    Sem isso, um poste cairia sempre na ponta de uma passada — que pode estar a
    centenas de metros de onde a carga realmente acaba.
    """
    anterior_fim: tuple[float, float] | None = None
    for leg in legs:
        if anterior_fim is not None:
            yield from _interpolar(anterior_fim, leg[0], passo_m, cobre=False)
        for inicio, fim in pairwise(leg):
            yield from _interpolar(inicio, fim, passo_m, cobre=True)
        anterior_fim = leg[-1]


def _interpolar(
    inicio: tuple[float, float], fim: tuple[float, float], passo_m: float, *, cobre: bool
) -> Iterator[tuple[float, float, float, bool]]:
    """Pontos intermediários entre dois vértices, a cada ``passo_m``."""
    distancia = geo.haversine_m(inicio[0], inicio[1], fim[0], fim[1])
    if distancia <= 0:
        return
    n = max(1, math.ceil(distancia / passo_m))
    for i in range(1, n + 1):
        fracao = i / n
        lon = inicio[0] + (fim[0] - inicio[0]) * fracao
        lat = inicio[1] + (fim[1] - inicio[1]) * fracao
        yield lat, lon, distancia / n, cobre


# ---------------------------------------------------------------------------
# Calibração: o perfil deixa de ser datasheet e vira medição
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Amostra:
    """Uma missão concluída, do ponto de vista do consumo."""

    metros: float
    segundos: float
    wh_gastos: float


def calibrate(amostras: list[Amostra], battery_wh: float) -> tuple[float, float, int]:
    """Ajusta ``wh_per_m`` e ``wh_per_h`` sobre missões reais.

    Mínimos quadrados em duas variáveis: ``wh = a·metros + b·horas``. É a forma
    mais simples que respeita a física do problema — e, com duas incógnitas,
    exige pelo menos duas missões com proporções diferentes de parada e
    deslocamento. Com menos que isso, ou com missões todas parecidas, o sistema
    fica mal condicionado e a função recusa em vez de devolver um número
    bonito e errado.

    Devolve ``(wh_per_m, wh_per_h, n_amostras)``.
    """
    usaveis = [a for a in amostras if a.metros > 0 and a.segundos > 0 and a.wh_gastos > 0]
    if len(usaveis) < 2:
        raise ValueError(
            f"Calibração precisa de ao menos 2 missões com consumo medido; "
            f"há {len(usaveis)}."
        )

    # Normais do ajuste: [Σm² Σmh; Σmh Σh²]·[a; b] = [Σm·wh; Σh·wh]
    smm = sum(a.metros**2 for a in usaveis)
    shh = sum((a.segundos / 3600.0) ** 2 for a in usaveis)
    smh = sum(a.metros * (a.segundos / 3600.0) for a in usaveis)
    smw = sum(a.metros * a.wh_gastos for a in usaveis)
    shw = sum((a.segundos / 3600.0) * a.wh_gastos for a in usaveis)

    determinante = smm * shh - smh * smh
    # A comparação é relativa à escala dos próprios termos. Um limiar absoluto
    # não serve: com missões de 15 km, smm·shh é da ordem de 1e7, e o resíduo de
    # ponto flutuante de um sistema singular fica bem acima de qualquer épsilon
    # fixo — foi assim que três missões proporcionais passaram batido.
    if abs(determinante) <= 1e-9 * max(smm * shh, 1.0):
        raise ValueError(
            "As missões são proporcionais demais entre si para separar tração de "
            "carga fixa. Calibre com uma missão de percurso longo e uma de muitas "
            "paradas."
        )

    wh_per_m = (smw * shh - shw * smh) / determinante
    wh_per_h = (shw * smm - smw * smh) / determinante

    if wh_per_m < 0 or wh_per_h < 0:
        raise ValueError(
            f"O ajuste devolveu coeficiente negativo (por metro {wh_per_m:.4f}, "
            f"por hora {wh_per_h:.1f}), o que não tem sentido físico. Provável "
            f"telemetria de bateria imprecisa nas missões usadas."
        )
    # battery_wh entra só na checagem de sanidade: um coeficiente que esvaziasse
    # a bateria em menos de dez minutos parada denuncia dado ruim.
    if wh_per_h > battery_wh * 6:
        raise ValueError("Carga fixa ajustada é implausível; revise a telemetria.")

    return wh_per_m, wh_per_h, len(usaveis)
