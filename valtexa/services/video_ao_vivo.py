"""Vídeo ao vivo das câmeras do Rover para a estação de pilotagem do centro de comando.

Como funciona, de ponta a ponta:

1. **Alguém assiste.** A estação pede (``POST /v1/platform/rovers/{id}/video``) quais
   câmeras, quantos quadros por segundo e o lado maior da imagem. O pedido **vence em
   ``TTL_PEDIDO_S``**: a tela o renova enquanto está aberta. Fechou a aba, o Rover para de
   mandar sozinho — vídeo nunca fica ligado esquecido gastando rádio e Starlink.
2. **O Rover fica sabendo sem nenhuma consulta a mais.** O pedido vai no cabeçalho
   ``X-Valtexa-Video`` da resposta de ``GET /v1/device/commands``, que o Runtime já busca
   a cada 2 s, e na resposta de cada quadro enviado.
3. **O Rover manda** ``POST /v1/device/video/{camera}`` (JPEG, assinado como todo o
   protocolo do dispositivo). Pela base da fazenda, cada câmera é um *slot* "só o último
   vale" (``rover/valtexa_rover/enlace/rpc.py``): quadro velho é descartado no caminho,
   nunca enfileirado, e o vídeo nunca passa na frente de comando ou controle remoto.
4. **A plataforma guarda só o último quadro** de cada câmera, por ``TTL_QUADRO_S``, na
   coordenação compartilhada (memória em desenvolvimento, Redis com várias réplicas).
   Nada de vídeo vai para o banco nem para o storage.
5. **A estação busca** o último quadro (``GET .../video/{camera}``), com o instante da
   captura: a tela mostra a idade do quadro, o que diz ao operador quanto confiar nele.

Começar a assistir fica na auditoria do cliente (quem viu as câmeras da fazenda, quando).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from valtexa.services.coordenacao import coordenacao

TTL_PEDIDO_S = 12.0
TTL_QUADRO_S = 15.0
MAX_JPEG_BYTES = 400_000
MAX_CAMERAS = 4
FPS_MIN, FPS_MAX = 0.5, 10.0
LADO_MIN, LADO_MAX = 240, 1280
CABECALHO = "X-Valtexa-Video"


class VideoInvalidoError(ValueError):
    pass


def _agora() -> datetime:
    return datetime.now(UTC)


def _chave_pedido(device_id: str) -> str:
    return f"video:pedido:{device_id}"


def _chave_quadro(device_id: str, camera_id: str) -> str:
    return f"video:quadro:{device_id}:{camera_id}"


def pedir(device_id: str, cameras: list[str], fps: float, lado: int, *,
          user_id: str | None) -> tuple[dict, bool]:
    """Liga (ou renova) o vídeo. Devolve ``(pedido, novo)`` — ``novo`` só no começo."""
    cameras = [str(c)[:64] for c in cameras if str(c).strip()][:MAX_CAMERAS]
    if not cameras:
        raise VideoInvalidoError("Escolha ao menos uma câmera.")
    if not FPS_MIN <= fps <= FPS_MAX:
        raise VideoInvalidoError(f"fps entre {FPS_MIN:g} e {FPS_MAX:g}.")
    if not LADO_MIN <= lado <= LADO_MAX:
        raise VideoInvalidoError(f"lado entre {LADO_MIN} e {LADO_MAX} px.")
    novo = pedido(device_id) is None
    corpo = {"cameras": cameras, "fps": round(float(fps), 2), "lado": int(lado),
             "ate": (_agora() + timedelta(seconds=TTL_PEDIDO_S)).isoformat(),
             "por": user_id}
    coordenacao.guarda(_chave_pedido(device_id), json.dumps(corpo).encode(), TTL_PEDIDO_S)
    return corpo, novo


def parar(device_id: str) -> None:
    coordenacao.apaga(_chave_pedido(device_id))


def pedido(device_id: str) -> dict | None:
    bruto = coordenacao.le(_chave_pedido(device_id))
    return json.loads(bruto) if bruto else None


def cabecalho(device_id: str) -> str | None:
    """O pedido em JSON compacto para o Rover (sem quem pediu: o robô não precisa)."""
    p = pedido(device_id)
    if p is None:
        return None
    return json.dumps({k: p[k] for k in ("cameras", "fps", "lado", "ate")},
                      separators=(",", ":"))


def recebe(device_id: str, camera_id: str, jpeg: bytes, *, capturado_em: str | None,
           seq: int | None) -> dict | None:
    """Guarda o quadro. Devolve o pedido em vigor (``None``: ninguém assiste, pare)."""
    p = pedido(device_id)
    if p is None or camera_id not in p["cameras"]:
        return None
    if not jpeg or len(jpeg) > MAX_JPEG_BYTES:
        raise VideoInvalidoError(f"Quadro vazio ou acima de {MAX_JPEG_BYTES} bytes.")
    if not jpeg.startswith(b"\xff\xd8"):
        raise VideoInvalidoError("O quadro precisa ser JPEG.")
    meta = {"capturado_em": capturado_em, "recebido_em": _agora().isoformat(),
            "seq": seq, "bytes": len(jpeg)}
    cabeca = json.dumps(meta, separators=(",", ":")).encode()
    coordenacao.guarda(_chave_quadro(device_id, camera_id),
                       len(cabeca).to_bytes(4, "big") + cabeca + jpeg, TTL_QUADRO_S)
    return p


def quadro(device_id: str, camera_id: str) -> tuple[bytes, dict] | None:
    bruto = coordenacao.le(_chave_quadro(device_id, camera_id))
    if not bruto:
        return None
    n = int.from_bytes(bruto[:4], "big")
    return bruto[4 + n:], json.loads(bruto[4:4 + n])
