"""Coordenação entre réplicas: limite de taxa e travas (brief, seção 51).

Com uma réplica só, um dicionário em memória basta. Com várias atrás do
balanceador, não: o balde de fichas de um robô dividido entre três processos
deixa passar três vezes o limite, e duas réplicas do worker rodariam a retenção
e os alertas ao mesmo tempo. O estado que precisa ser **um só** mora aqui, atrás
de uma interface:

* :class:`CoordenacaoEmMemoria` — desenvolvimento, testes e réplica única;
* :class:`CoordenacaoRedis` — produção (``REDIS_URL``). O balde e a trava são
  scripts Lua, atômicos no servidor: não há janela entre ler e gravar.

O que **não** está aqui de propósito: contagem de falhas de login (no banco, ver
``login_guard.py``), nonces do protocolo (no banco), filas de trabalho (no banco,
``jobs.py``). O Redis só guarda o que pode se perder num reinício sem dano além
de um limite que recomeça cheio ou uma tarefa periódica que roda um ciclo antes.
"""

from __future__ import annotations

import threading
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Protocol

from valtexa.config import settings

PREFIXO = "valtexa:"


class Coordenacao(Protocol):
    """Contrato. ``chave`` é um nome lógico; o prefixo é responsabilidade da implementação."""

    def consumir(self, chave: str, por_minuto: int) -> float | None:
        """Tira uma ficha do balde ``chave`` (capacidade e recarga: ``por_minuto``).

        ``None`` se havia ficha; senão, os segundos até haver uma (vai no Retry-After).
        """
        ...

    def trava(self, chave: str, ttl_segundos: float) -> Iterator[bool]:
        """Gerenciador de contexto que tenta pegar a trava **sem esperar**.

        Entrega ``True`` para quem pegou e ``False`` para quem não pegou. O ``ttl``
        é o seguro contra processo que morre segurando a trava: passa sozinho.
        """
        ...

    def uma_vez(self, chave: str, intervalo_segundos: float,
                agora: float | None = None) -> bool:
        """``True`` para o primeiro que pedir ``chave`` dentro do intervalo; o resto, ``False``.

        É o "uma vez por ciclo no cluster" das tarefas periódicas do worker: a marca
        não é solta no fim, ela vence sozinha. ``agora`` é o relógio monotônico de
        quem chama (a memória usa; o Redis usa o relógio dele).
        """
        ...

    def guarda(self, chave: str, valor: bytes, ttl_segundos: float) -> None:
        """Guarda ``valor`` sob ``chave`` até vencer (estado curto compartilhado: o último
        quadro de vídeo de cada câmera, quem está assistindo)."""
        ...

    def le(self, chave: str) -> bytes | None:
        """O valor de ``chave`` se ainda não venceu; senão ``None``."""
        ...

    def apaga(self, chave: str) -> None:
        ...

    def limpar(self) -> None:
        """Esquece tudo. Existe para os testes."""
        ...


class CoordenacaoEmMemoria:
    """Por processo. Correta com uma réplica; com várias, cada uma tem o seu estado."""

    def __init__(self, relogio=time.monotonic) -> None:
        self._relogio = relogio
        self._baldes: dict[str, tuple[float, float]] = {}
        self._travas: dict[str, float] = {}
        self._valores: dict[str, tuple[bytes, float]] = {}
        self._mutex = threading.Lock()

    def consumir(self, chave: str, por_minuto: int) -> float | None:
        agora = self._relogio()
        with self._mutex:
            fichas, antes = self._baldes.get(chave, (float(por_minuto), agora))
            fichas = min(float(por_minuto), fichas + (agora - antes) * por_minuto / 60.0)
            if fichas < 1.0:
                self._baldes[chave] = (fichas, agora)
                return (1.0 - fichas) * 60.0 / por_minuto
            self._baldes[chave] = (fichas - 1.0, agora)
            return None

    @contextmanager
    def trava(self, chave: str, ttl_segundos: float) -> Iterator[bool]:
        agora = self._relogio()
        with self._mutex:
            vence = self._travas.get(chave)
            pegou = vence is None or vence <= agora
            if pegou:
                self._travas[chave] = agora + ttl_segundos
        try:
            yield pegou
        finally:
            if pegou:
                with self._mutex:
                    self._travas.pop(chave, None)

    def uma_vez(self, chave: str, intervalo_segundos: float,
                agora: float | None = None) -> bool:
        agora = self._relogio() if agora is None else agora
        with self._mutex:
            vence = self._travas.get(f"uma_vez:{chave}")
            if vence is not None and vence > agora:
                return False
            self._travas[f"uma_vez:{chave}"] = agora + intervalo_segundos
            return True

    def guarda(self, chave: str, valor: bytes, ttl_segundos: float) -> None:
        with self._mutex:
            self._valores[chave] = (bytes(valor), self._relogio() + ttl_segundos)
            if len(self._valores) > 4096:  # vencidos não ficam para sempre
                agora = self._relogio()
                for k in [k for k, (_v, vence) in self._valores.items() if vence <= agora]:
                    del self._valores[k]

    def le(self, chave: str) -> bytes | None:
        with self._mutex:
            item = self._valores.get(chave)
            if item is None or item[1] <= self._relogio():
                return None
            return item[0]

    def apaga(self, chave: str) -> None:
        with self._mutex:
            self._valores.pop(chave, None)

    def limpar(self) -> None:
        with self._mutex:
            self._baldes.clear()
            self._travas.clear()
            self._valores.clear()


# Balde de fichas no servidor. KEYS[1] = balde; ARGV = capacidade, agora (ms).
# Guarda fichas e instante num hash, com expiração de dois minutos sem uso (um
# balde parado está cheio; apagá-lo é o mesmo que deixá-lo cheio).
_LUA_BALDE = """
local cap = tonumber(ARGV[1])
local agora = tonumber(ARGV[2])
local h = redis.call('HMGET', KEYS[1], 'f', 't')
local fichas = tonumber(h[1])
local antes = tonumber(h[2])
if fichas == nil then fichas = cap; antes = agora end
fichas = math.min(cap, fichas + (agora - antes) * cap / 60000.0)
local espera = -1
if fichas < 1.0 then
  espera = math.ceil((1.0 - fichas) * 60000.0 / cap)
else
  fichas = fichas - 1.0
end
redis.call('HSET', KEYS[1], 'f', tostring(fichas), 't', tostring(agora))
redis.call('PEXPIRE', KEYS[1], 120000)
return espera
"""

# Solta a trava só se ela ainda for de quem a pegou (o ttl pode ter vencido e
# outro processo a pegado nesse meio-tempo).
_LUA_SOLTA = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
  return redis.call('DEL', KEYS[1])
end
return 0
"""


class CoordenacaoRedis:
    """O mesmo contrato num Redis compartilhado pelas réplicas.

    O relógio do balde é o do **servidor Redis** (``TIME``), não o de cada réplica:
    réplicas com relógios levemente diferentes não ganham nem perdem fichas.
    """

    def __init__(self, cliente, prefixo: str = PREFIXO) -> None:
        self.cliente = cliente
        self.prefixo = prefixo
        self._balde = cliente.register_script(_LUA_BALDE)
        self._solta = cliente.register_script(_LUA_SOLTA)

    def _agora_ms(self) -> int:
        segundos, micros = self.cliente.time()
        return int(segundos) * 1000 + int(micros) // 1000

    def consumir(self, chave: str, por_minuto: int) -> float | None:
        espera = int(self._balde(keys=[f"{self.prefixo}taxa:{chave}"],
                                 args=[por_minuto, self._agora_ms()]))
        return None if espera < 0 else espera / 1000.0

    @contextmanager
    def trava(self, chave: str, ttl_segundos: float) -> Iterator[bool]:
        nome = f"{self.prefixo}trava:{chave}"
        dono = uuid.uuid4().hex
        pegou = bool(self.cliente.set(nome, dono, nx=True,
                                      px=max(1, int(ttl_segundos * 1000))))
        try:
            yield pegou
        finally:
            if pegou:
                self._solta(keys=[nome], args=[dono])

    def uma_vez(self, chave: str, intervalo_segundos: float,
                agora: float | None = None) -> bool:
        return bool(self.cliente.set(f"{self.prefixo}uma_vez:{chave}", "1", nx=True,
                                     px=max(1, int(intervalo_segundos * 1000))))

    def guarda(self, chave: str, valor: bytes, ttl_segundos: float) -> None:
        self.cliente.set(f"{self.prefixo}valor:{chave}", valor,
                         px=max(1, int(ttl_segundos * 1000)))

    def le(self, chave: str) -> bytes | None:
        return self.cliente.get(f"{self.prefixo}valor:{chave}")

    def apaga(self, chave: str) -> None:
        self.cliente.delete(f"{self.prefixo}valor:{chave}")

    def limpar(self) -> None:
        for chave in self.cliente.scan_iter(match=f"{self.prefixo}*"):
            self.cliente.delete(chave)


def construir() -> Coordenacao:
    """Redis quando ``REDIS_URL`` está definido; senão, memória do processo."""
    if settings.redis_url:
        try:
            import redis
        except ImportError as exc:  # pragma: no cover - depende do ambiente
            raise RuntimeError("REDIS_URL definido exige 'pip install redis'.") from exc
        return CoordenacaoRedis(redis.Redis.from_url(settings.redis_url))
    return CoordenacaoEmMemoria()


coordenacao: Coordenacao = construir()
"""Instância do processo. Os testes trocam por uma em memória ou por ``fakeredis``."""
