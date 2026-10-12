"""Métricas no formato de exposição do Prometheus (texto, versão 0.0.4).

Sem dependência nova: o formato é simples e estável, e escrever o registro aqui
deixa o mesmo código servir às duas fontes de métrica da plataforma:

* **do processo** — contadores e histogramas que o *middleware* HTTP atualiza a cada
  requisição (:class:`Contador`, :class:`Histograma`). Valem para **esta réplica**:
  com várias réplicas, o Prometheus raspa cada uma e soma (``sum by (rota)``);
* **do banco** — fotografias tiradas na hora da raspagem (fila de trabalhos, eventos
  pendentes, frota, alertas), montadas como :class:`Familia`. São iguais em toda
  réplica: o Prometheus deve raspá-las de uma só (ver ``deploy/observabilidade``).

Os nomes seguem a convenção do Prometheus (``_total`` em contador, unidade no
nome: ``_seconds``, ``_bytes``); os rótulos são de cardinalidade limitada — rota é
o **molde** (``/v1/missions/{mission_id}``), nunca o caminho com o id.
"""

from __future__ import annotations

import math
import re
import threading
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

_NOME = re.compile(r"^[a-zA-Z_:][a-zA-Z0-9_:]*$")
_ROTULO = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")

LIMITES_LATENCIA_S: tuple[float, ...] = (
    0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0,
)
"""Limites do histograma de latência HTTP (segundos), os padrões do Prometheus."""


def _escapa(valor: str) -> str:
    return valor.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def _numero(valor: float) -> str:
    if math.isnan(valor):
        return "NaN"
    if math.isinf(valor):
        return "+Inf" if valor > 0 else "-Inf"
    if float(valor).is_integer() and abs(valor) < 1e15:
        return str(int(valor))
    return repr(float(valor))


def _rotulos(nomes: Sequence[str], valores: Sequence[str],
             extra: tuple[str, str] | None = None) -> str:
    pares = [f'{n}="{_escapa(str(v))}"' for n, v in zip(nomes, valores, strict=True)]
    if extra is not None:
        pares.append(f'{extra[0]}="{extra[1]}"')
    return "{" + ",".join(pares) + "}" if pares else ""


@dataclass
class Amostra:
    rotulos: dict[str, str]
    valor: float
    sufixo: str = ""


@dataclass
class Familia:
    """Uma métrica montada na hora (vinda do banco): nome, tipo, ajuda e amostras."""

    nome: str
    tipo: str
    ajuda: str
    amostras: list[Amostra] = field(default_factory=list)

    def add(self, valor: float | None, **rotulos: str) -> None:
        """Valor ``None`` (não medido) **não** vira amostra: ausência não é zero."""
        if valor is None:
            return
        self.amostras.append(Amostra({k: str(v) for k, v in rotulos.items()}, float(valor)))

    def render(self) -> str:
        linhas = [f"# HELP {self.nome} {_escapa(self.ajuda)}", f"# TYPE {self.nome} {self.tipo}"]
        for a in self.amostras:
            nomes = list(a.rotulos)
            linhas.append(f"{self.nome}{a.sufixo}{_rotulos(nomes, [a.rotulos[n] for n in nomes])}"
                          f" {_numero(a.valor)}")
        return "\n".join(linhas)


class _Metrica:
    tipo = "untyped"

    def __init__(self, nome: str, ajuda: str, rotulos: Sequence[str] = ()) -> None:
        if not _NOME.match(nome):
            raise ValueError(f"Nome de métrica inválido: {nome!r}")
        for r in rotulos:
            if not _ROTULO.match(r) or r == "le":
                raise ValueError(f"Rótulo inválido: {r!r}")
        self.nome = nome
        self.ajuda = ajuda
        self.rotulos = tuple(rotulos)
        self._trava = threading.Lock()

    def _chave(self, valores: dict[str, str]) -> tuple[str, ...]:
        if set(valores) != set(self.rotulos):
            raise ValueError(
                f"{self.nome} espera os rótulos {self.rotulos}, veio {sorted(valores)}"
            )
        return tuple(str(valores[r]) for r in self.rotulos)

    def _cabecalho(self) -> list[str]:
        return [f"# HELP {self.nome} {_escapa(self.ajuda)}", f"# TYPE {self.nome} {self.tipo}"]


class Contador(_Metrica):
    """Só sobe. Reinício do processo zera — o ``rate()`` do Prometheus trata isso."""

    tipo = "counter"

    def __init__(self, nome: str, ajuda: str, rotulos: Sequence[str] = ()) -> None:
        super().__init__(nome, ajuda, rotulos)
        self._valores: dict[tuple[str, ...], float] = {}

    def inc(self, valor: float = 1.0, **rotulos: str) -> None:
        if valor < 0:
            raise ValueError("Contador não desce.")
        chave = self._chave(rotulos)
        with self._trava:
            self._valores[chave] = self._valores.get(chave, 0.0) + valor

    def valor(self, **rotulos: str) -> float:
        return self._valores.get(self._chave(rotulos), 0.0)

    def render(self) -> str:
        with self._trava:
            itens = sorted(self._valores.items())
        linhas = self._cabecalho()
        linhas += [f"{self.nome}{_rotulos(self.rotulos, k)} {_numero(v)}" for k, v in itens]
        return "\n".join(linhas)


class Medidor(_Metrica):
    """Sobe e desce (o *gauge* do Prometheus)."""

    tipo = "gauge"

    def __init__(self, nome: str, ajuda: str, rotulos: Sequence[str] = ()) -> None:
        super().__init__(nome, ajuda, rotulos)
        self._valores: dict[tuple[str, ...], float] = {}

    def set(self, valor: float, **rotulos: str) -> None:
        chave = self._chave(rotulos)
        with self._trava:
            self._valores[chave] = float(valor)

    def inc(self, valor: float = 1.0, **rotulos: str) -> None:
        chave = self._chave(rotulos)
        with self._trava:
            self._valores[chave] = self._valores.get(chave, 0.0) + valor

    def render(self) -> str:
        with self._trava:
            itens = sorted(self._valores.items())
        linhas = self._cabecalho()
        linhas += [f"{self.nome}{_rotulos(self.rotulos, k)} {_numero(v)}" for k, v in itens]
        return "\n".join(linhas)


class Histograma(_Metrica):
    """Distribuição em baldes cumulativos (``_bucket{le=...}``, ``_sum``, ``_count``)."""

    tipo = "histogram"

    def __init__(self, nome: str, ajuda: str, rotulos: Sequence[str] = (),
                 limites: Sequence[float] = LIMITES_LATENCIA_S) -> None:
        super().__init__(nome, ajuda, rotulos)
        if list(limites) != sorted(limites) or not limites:
            raise ValueError("Limites do histograma precisam ser crescentes.")
        self.limites = tuple(float(x) for x in limites)
        self._dados: dict[tuple[str, ...], list[float]] = {}
        """Por série: contagem por balde (não cumulativa) + [soma, contagem]."""

    def observe(self, valor: float, **rotulos: str) -> None:
        chave = self._chave(rotulos)
        with self._trava:
            dados = self._dados.setdefault(chave, [0.0] * (len(self.limites) + 3))
            for i, limite in enumerate(self.limites):
                if valor <= limite:
                    dados[i] += 1
                    break
            else:
                dados[len(self.limites)] += 1  # acima do último limite (+Inf)
            dados[-2] += valor
            dados[-1] += 1

    def contagem(self, **rotulos: str) -> int:
        dados = self._dados.get(self._chave(rotulos))
        return int(dados[-1]) if dados else 0

    def render(self) -> str:
        with self._trava:
            itens = sorted((k, list(v)) for k, v in self._dados.items())
        linhas = self._cabecalho()
        for chave, dados in itens:
            acumulado = 0.0
            for i, limite in enumerate((*self.limites, math.inf)):
                acumulado += dados[i]
                le = "+Inf" if math.isinf(limite) else _numero(limite)
                linhas.append(f"{self.nome}_bucket{_rotulos(self.rotulos, chave, ('le', le))}"
                              f" {_numero(acumulado)}")
            linhas.append(f"{self.nome}_sum{_rotulos(self.rotulos, chave)} {_numero(dados[-2])}")
            linhas.append(f"{self.nome}_count{_rotulos(self.rotulos, chave)} "
                          f"{_numero(dados[-1])}")
        return "\n".join(linhas)


class Registro:
    """As métricas do processo, na ordem em que foram criadas."""

    def __init__(self) -> None:
        self._metricas: dict[str, _Metrica] = {}
        self._trava = threading.Lock()

    def _registra(self, metrica: _Metrica) -> _Metrica:
        with self._trava:
            if metrica.nome in self._metricas:
                raise ValueError(f"Métrica já registrada: {metrica.nome}")
            self._metricas[metrica.nome] = metrica
        return metrica

    def contador(self, nome: str, ajuda: str, rotulos: Sequence[str] = ()) -> Contador:
        return self._registra(Contador(nome, ajuda, rotulos))  # type: ignore[return-value]

    def medidor(self, nome: str, ajuda: str, rotulos: Sequence[str] = ()) -> Medidor:
        return self._registra(Medidor(nome, ajuda, rotulos))  # type: ignore[return-value]

    def histograma(self, nome: str, ajuda: str, rotulos: Sequence[str] = (),
                   limites: Sequence[float] = LIMITES_LATENCIA_S) -> Histograma:
        return self._registra(Histograma(nome, ajuda, rotulos, limites))  # type: ignore[return-value]

    def render(self, extras: Iterable[Familia] = ()) -> str:
        partes = [m.render() for m in self._metricas.values()]
        partes += [f.render() for f in extras]
        return "\n".join(partes) + "\n"


CONTENT_TYPE = "text/plain; version=0.0.4; charset=utf-8"


def quantil_dos_baldes(limites: Sequence[float], contagens: Sequence[float],
                       q: float) -> float | None:
    """Quantil aproximado a partir de baldes **não cumulativos** (o último é +Inf).

    Interpola dentro do balde, como o ``histogram_quantile`` do Prometheus. Se o
    quantil cai no balde +Inf, devolve o último limite (não dá para saber mais).
    """
    total = sum(contagens)
    if total <= 0:
        return None
    alvo = q * total
    acumulado = 0.0
    anterior = 0.0
    for i, n in enumerate(contagens):
        if acumulado + n >= alvo and n > 0:
            if i >= len(limites):
                return float(limites[-1])
            dentro = (alvo - acumulado) / n
            return anterior + (limites[i] - anterior) * dentro
        acumulado += n
        if i < len(limites):
            anterior = limites[i]
    return float(limites[-1])


__all__ = [
    "CONTENT_TYPE",
    "LIMITES_LATENCIA_S",
    "Amostra",
    "Contador",
    "Familia",
    "Histograma",
    "Medidor",
    "Registro",
    "quantil_dos_baldes",
]
