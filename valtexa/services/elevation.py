"""Relevo: de onde vem a altitude do terreno, e o que se faz com ela.

O planejamento de rota até aqui trata o talhão como se fosse plano. Não é, e a
diferença aparece em três lugares que custam dinheiro ou segurança:

1. **Autonomia.** Subir consome muito mais do que andar no plano. Um plano que
   ignora 40 m de desnível erra a conta de recarga para baixo — e errar para
   baixo é o rover parando no meio da lavoura.
2. **Tombamento.** Rover de esteira ou de roda tem um ângulo a partir do qual
   ele vira, e virar de lado numa encosta com a câmera embarcada é perda total.
3. **Direção das passadas.** Curva de nível é mais segura e mais econômica do
   que subir e descer a encosta; sem altitude não há como preferir uma à outra.

**Esta plataforma não tem fonte de elevação contratada.** O módulo existe para
que a falta seja explícita e para que ligar uma fonte seja configuração, não
reescrita: quem chamar sem provedor configurado recebe
:class:`ElevationNotConfiguredError`, e não um zero que passaria por medição.

Os provedores de verdade — Copernicus DEM, SRTM, OpenTopoData — respondem ao
mesmo formato: uma lista de pontos, uma lista de altitudes. É o que
:func:`amostra` pede e o que :class:`ProvedorHTTP` fala.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass

import httpx

from valtexa.config import settings

logger = logging.getLogger(__name__)


class ElevationNotConfiguredError(RuntimeError):
    """Não há fonte de elevação ligada nesta instalação.

    Distinta de um erro de rede de propósito: "não configurado" é uma decisão
    de implantação, e "não respondeu" é um incidente. Quem trata os dois igual
    acaba mostrando "serviço fora do ar" para uma instalação que nunca teve o
    serviço.
    """


class ElevationUnavailableError(RuntimeError):
    """A fonte existe mas não respondeu, ou respondeu o que não se esperava."""


@dataclass(frozen=True, slots=True)
class Relevo:
    """O que se mediu do terreno de uma área.

    As declividades são **em graus**, e não em porcentagem, porque o limite que
    importa — o ângulo de tombamento do rover — vem em graus no datasheet do
    fabricante. Converter na fronteira evita a classe de erro em que 30% vira
    30°.
    """

    amostras: int
    altitude_min_m: float
    altitude_max_m: float
    desnivel_m: float
    declividade_media_deg: float
    declividade_maxima_deg: float
    azimute_da_encosta_deg: float | None
    """Para onde o terreno cai, em graus do norte. ``None`` em terreno plano.

    É a direção em que **não** se deve planejar as passadas: cortar a encosta em
    curva de nível é perpendicular a isto.
    """

    fonte: str
    """Qual provedor respondeu. Vai para o plano, porque precisão de DEM varia
    muito entre fontes e quem lê o número precisa saber de onde veio."""

    def as_dict(self) -> dict:
        return {
            "amostras": self.amostras,
            "altitude_min_m": round(self.altitude_min_m, 1),
            "altitude_max_m": round(self.altitude_max_m, 1),
            "desnivel_m": round(self.desnivel_m, 1),
            "declividade_media_deg": round(self.declividade_media_deg, 2),
            "declividade_maxima_deg": round(self.declividade_maxima_deg, 2),
            "azimute_da_encosta_deg": (
                round(self.azimute_da_encosta_deg, 1)
                if self.azimute_da_encosta_deg is not None
                else None
            ),
            "fonte": self.fonte,
        }


class ProvedorHTTP:
    """Fala com um serviço de elevação por HTTP.

    O formato é o do OpenTopoData e do Open-Elevation, que é o mesmo: manda
    ``locations=lat,lon|lat,lon|...`` e recebe ``{"results": [{"elevation": …}]}``.
    Um provedor com formato próprio implementa a mesma função ``altitudes`` e
    entra aqui sem mudar mais nada.
    """

    def __init__(self, url: str, *, timeout: float = 30.0, lote: int = 100) -> None:
        self.url = url.rstrip("/")
        self.timeout = timeout
        self.lote = lote

    @property
    def nome(self) -> str:
        return self.url

    def altitudes(self, pontos: list[tuple[float, float]]) -> list[float]:
        """Altitude em metros de cada ``(lon, lat)``, na mesma ordem.

        Vai em lotes porque os serviços públicos limitam o tamanho da consulta,
        e um talhão amostrado com alguma densidade passa desse limite fácil.
        """
        saida: list[float] = []
        with httpx.Client(timeout=self.timeout) as cliente:
            for inicio in range(0, len(pontos), self.lote):
                pedaco = pontos[inicio : inicio + self.lote]
                locais = "|".join(f"{lat:.6f},{lon:.6f}" for lon, lat in pedaco)
                try:
                    resposta = cliente.get(self.url, params={"locations": locais})
                    resposta.raise_for_status()
                    corpo = resposta.json()
                except (httpx.HTTPError, ValueError) as exc:
                    raise ElevationUnavailableError(
                        f"A fonte de elevação não respondeu: {exc}"
                    ) from exc

                resultados = corpo.get("results")
                if not isinstance(resultados, list) or len(resultados) != len(pedaco):
                    raise ElevationUnavailableError(
                        "A fonte de elevação devolveu um formato inesperado."
                    )
                for item in resultados:
                    altura = item.get("elevation") if isinstance(item, dict) else None
                    if altura is None:
                        # Buraco no DEM (mar, borda de tile). Interpolar aqui
                        # inventaria terreno; melhor recusar a amostra inteira e
                        # deixar o plano seguir sem relevo, declaradamente.
                        raise ElevationUnavailableError(
                            "A fonte de elevação não tem dado para parte desta área."
                        )
                    saida.append(float(altura))
        return saida


def provedor() -> ProvedorHTTP:
    """O provedor configurado, ou o erro que diz que não há um."""
    url = (settings.elevation_url or "").strip()
    if not url:
        raise ElevationNotConfiguredError(
            "Nenhuma fonte de elevação configurada. Defina ELEVATION_URL para um "
            "serviço de DEM (Copernicus, SRTM, OpenTopoData) e o relevo entra no "
            "planejamento. Sem ela, a rota é planejada como se o talhão fosse plano."
        )
    return ProvedorHTTP(url, timeout=settings.elevation_timeout_seconds)


def configurado() -> bool:
    return bool((settings.elevation_url or "").strip())


GRAU_EM_METROS = 111_320.0


def grade(polygon: list, *, passo_m: float = 40.0, teto: int = 400) -> list[tuple[float, float]]:
    """Pontos em grade dentro da caixa do polígono.

    Amostrar em grade, e não nos vértices, porque o que interessa é o miolo: um
    talhão pode ter os quatro cantos na mesma cota e um barranco no meio, e é o
    barranco que derruba o rover.

    ``teto`` existe porque o número de pontos cresce com o quadrado da área, e
    um talhão de 200 ha a cada 40 m daria 12 mil consultas. Estourando o teto, o
    passo é afrouxado até caber — perde-se resolução, e é melhor do que perder a
    medição inteira.
    """
    if len(polygon) < 3:
        return []
    lons = [float(p[0]) for p in polygon]
    lats = [float(p[1]) for p in polygon]
    lon_min, lon_max = min(lons), max(lons)
    lat_min, lat_max = min(lats), max(lats)

    lat_media = (lat_min + lat_max) / 2.0
    metros_por_grau_lon = GRAU_EM_METROS * math.cos(math.radians(lat_media)) or 1.0

    passo = passo_m
    for _ in range(8):
        d_lat = passo / GRAU_EM_METROS
        d_lon = passo / metros_por_grau_lon
        n_lat = max(2, int((lat_max - lat_min) / d_lat) + 1)
        n_lon = max(2, int((lon_max - lon_min) / d_lon) + 1)
        if n_lat * n_lon <= teto:
            break
        passo *= 1.6
    else:
        logger.warning("Área grande demais para o teto de amostras: passo final %.0f m", passo)

    d_lat = passo / GRAU_EM_METROS
    d_lon = passo / metros_por_grau_lon
    pontos: list[tuple[float, float]] = []
    lat = lat_min
    while lat <= lat_max + 1e-12:
        lon = lon_min
        while lon <= lon_max + 1e-12:
            pontos.append((lon, lat))
            lon += d_lon
        lat += d_lat
    return pontos[:teto]


def amostra(polygon: list, *, passo_m: float = 40.0) -> Relevo:
    """Mede o relevo de uma área. Levanta se não houver fonte configurada."""
    fonte = provedor()
    pontos = grade(polygon, passo_m=passo_m)
    if len(pontos) < 4:
        raise ElevationUnavailableError("A área é pequena demais para amostrar relevo.")

    alturas = fonte.altitudes(pontos)
    return _resume(pontos, alturas, fonte=fonte.nome)


def _resume(pontos: list[tuple[float, float]], alturas: list[float], *, fonte: str) -> Relevo:
    """Transforma a nuvem de altitudes nos poucos números que decidem algo.

    A declividade sai de um ajuste de plano por mínimos quadrados sobre todos os
    pontos, e não da diferença entre o mais alto e o mais baixo. A diferença
    entre os extremos descreveria um degrau isolado como se fosse a encosta
    inteira — e é a encosta inteira que decide se as passadas devem correr em
    curva de nível.
    """
    lat_media = sum(lat for _, lat in pontos) / len(pontos)
    metros_por_grau_lon = GRAU_EM_METROS * math.cos(math.radians(lat_media)) or 1.0
    lon0, lat0 = pontos[0]

    xs = [(lon - lon0) * metros_por_grau_lon for lon, _ in pontos]
    ys = [(lat - lat0) * GRAU_EM_METROS for _, lat in pontos]
    zs = list(alturas)
    n = float(len(pontos))

    # Plano z = a*x + b*y + c, por mínimos quadrados. Sistema 2x2 depois de
    # centrar, o que dispensa inverter matriz 3x3 à mão.
    mx, my, mz = sum(xs) / n, sum(ys) / n, sum(zs) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True))
    sxz = sum((x - mx) * (z - mz) for x, z in zip(xs, zs, strict=True))
    syz = sum((y - my) * (z - mz) for y, z in zip(ys, zs, strict=True))

    det = sxx * syy - sxy * sxy
    if abs(det) < 1e-9:
        a = b = 0.0
    else:
        a = (sxz * syy - syz * sxy) / det
        b = (syz * sxx - sxz * sxy) / det

    declive_medio = math.degrees(math.atan(math.hypot(a, b)))

    # A máxima sai da diferença entre vizinhos na grade, que é o que o rover
    # realmente encara num trecho — a média do plano suaviza justamente o
    # barranco que importa.
    maxima = 0.0
    for i in range(len(pontos) - 1):
        dx = xs[i + 1] - xs[i]
        dy = ys[i + 1] - ys[i]
        dist = math.hypot(dx, dy)
        if dist < 1.0:
            continue
        maxima = max(maxima, math.degrees(math.atan(abs(zs[i + 1] - zs[i]) / dist)))

    azimute = None
    if math.hypot(a, b) > 1e-4:
        # O gradiente aponta para cima; a encosta cai no sentido oposto.
        azimute = (math.degrees(math.atan2(-a, -b))) % 360.0

    return Relevo(
        amostras=len(pontos),
        altitude_min_m=min(zs),
        altitude_max_m=max(zs),
        desnivel_m=max(zs) - min(zs),
        declividade_media_deg=declive_medio,
        declividade_maxima_deg=maxima,
        azimute_da_encosta_deg=azimute,
        fonte=fonte,
    )


def azimute_em_curva_de_nivel(relevo: Relevo) -> float | None:
    """A direção de passada que corta a encosta em vez de subir e descer.

    Perpendicular à queda do terreno. É o que um operador experiente escolhe
    sozinho, e o que o planejador não tinha como saber.
    """
    if relevo.azimute_da_encosta_deg is None:
        return None
    return (relevo.azimute_da_encosta_deg + 90.0) % 360.0


LIMITE_DE_TOMBAMENTO_PADRAO_DEG = 15.0
"""Declividade acima da qual se avisa, quando o hardware não declara a sua.

Quinze graus é conservador para rover de roda com centro de massa alto, que é o
caso do V-SCOUT. O número certo vem do fabricante e entra por
``capabilities.max_slope_deg``; este padrão existe só para não ficar sem aviso
nenhum quando o descritor de hardware está incompleto.
"""


def avisos_de_relevo(relevo: Relevo, *, limite_deg: float | None = None) -> list[str]:
    """O que um operador precisa ler antes de mandar o robô para uma encosta."""
    limite = limite_deg or LIMITE_DE_TOMBAMENTO_PADRAO_DEG
    avisos: list[str] = []
    if relevo.declividade_maxima_deg >= limite:
        avisos.append(
            f"Há trecho com {relevo.declividade_maxima_deg:.0f}° de inclinação, "
            f"acima do limite de {limite:.0f}° deste modelo. Confira no local "
            "antes de autorizar: o risco aqui é tombamento, não atraso."
        )
    elif relevo.declividade_maxima_deg >= limite * 0.7:
        avisos.append(
            f"Trecho de {relevo.declividade_maxima_deg:.0f}° de inclinação, perto "
            f"do limite de {limite:.0f}°. Prefira passadas em curva de nível."
        )
    if relevo.desnivel_m >= 30.0:
        avisos.append(
            f"{relevo.desnivel_m:.0f} m de desnível na área. A estimativa de "
            "energia não considera a subida — conte com autonomia menor do que a "
            "calculada."
        )
    return avisos
