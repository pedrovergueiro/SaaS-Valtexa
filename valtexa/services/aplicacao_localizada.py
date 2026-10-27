"""O mapa de aplicação localizada na missão de pulverização: integridade e o que conferir.

A IA (``ia/app/aplicacao_localizada.py``, ``POST /fields/{id}/gemeo/aplicacao-localizada``)
transforma o risco previsto em **taxa por trecho de rua** e **ciclo de PWM por bico**, e devolve
o mapa com o ``sha256`` do que se executa (trechos, produto, equipamento, data). Aqui:

* :func:`sha256_do_mapa` recalcula esse hash do conteúdo — o mapa que chega à missão não pode
  ter sido alterado no caminho;
* a aprovação do agrônomo grava o hash que ele viu (``plan.mapa_aplicacao_aprovado``); trocar
  o mapa depois apaga a aprovação (rota ``POST /missions/{id}/mapa-aplicacao``);
* :func:`conferencias` são as checagens determinísticas que o Safety Engine roda em cada
  trecho: dentro da faixa da bula do produto cadastrado, no máximo a dose autorizada da
  missão, PWM dentro dos limites da máquina, o mesmo produto da missão — e o gêmeo que fez o
  mapa **ativo** no talhão (em observação, o mapa é registro para comparar, não proposta).

Nada aqui libera: quem decide é o :mod:`valtexa.services.safety_engine`.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

CAMPOS_DO_HASH = ("zonas", "produto", "equipamento", "data_aplicacao", "modo_gemeo")
"""Os mesmos da IA (``ia/app/aplicacao_localizada.CAMPOS_DO_HASH``): o modo do gêmeo entra
para que um mapa feito em observação não vire executável trocando um campo."""


def sha256_do_mapa(mapa: dict[str, Any]) -> str:
    """O mesmo hash que a IA calcula (chaves ordenadas, UTF-8 sem escape)."""
    return hashlib.sha256(json.dumps({k: mapa.get(k) for k in CAMPOS_DO_HASH}, sort_keys=True,
                                     ensure_ascii=False).encode("utf-8")).hexdigest()


def integro(mapa: Any) -> bool:
    return (isinstance(mapa, dict) and isinstance(mapa.get("zonas"), list)
            and isinstance(mapa.get("sha256"), str) and sha256_do_mapa(mapa) == mapa["sha256"])


def conferencias(mapa: dict[str, Any], *, aprovado: str | None, taxa_autorizada: float | None,
                 dose_min: float | None, dose_max: float | None,
                 registro_do_produto: str | None) -> list[tuple[str, bool, str]]:
    """``(código, passou, texto)`` de cada conferência do mapa. Mapa não íntegro: só essa."""
    if not integro(mapa):
        return [("map_integrity", False, "Mapa de aplicação alterado ou incompleto: o hash não "
                 "confere com o conteúdo.")]
    sha = mapa["sha256"]
    ativo = mapa.get("modo_gemeo") == "ativo"
    saida = [("map_integrity", True, f"Mapa íntegro ({sha[:12]}…)."),
             ("map_twin_active", ativo,
              "O gêmeo que fez o mapa está ativo no talhão." if ativo else
              "Mapa feito com o gêmeo em observação no talhão: é registro para comparar, não "
              "proposta executável (ative o gêmeo na IA depois da avaliação)."),
             ("map_approved", aprovado == sha,
              "O agrônomo aprovou este mapa." if aprovado == sha else
              "A aprovação não é deste mapa (mudou depois de aprovado, ou não foi aprovado).")]
    aplicadas = [z for z in mapa["zonas"] if float(z.get("taxa_l_ha") or 0) > 0]
    fora = [z for z in aplicadas
            if (dose_min is not None and z["taxa_l_ha"] < dose_min)
            or (dose_max is not None and z["taxa_l_ha"] > dose_max)]
    saida.append(("map_rates_label", not fora,
                  f"{len(aplicadas)} trecho(s) aplicados dentro da faixa de bula." if not fora
                  else f"{len(fora)} trecho(s) fora da faixa de bula ({dose_min} a {dose_max})."))
    if taxa_autorizada is None:
        saida.append(("map_rates_authorized", False, "Missão sem dose autorizada: o mapa precisa "
                      "de um teto aprovado."))
    else:
        acima = [z for z in aplicadas if z["taxa_l_ha"] > taxa_autorizada + 1e-9]
        saida.append(("map_rates_authorized", not acima,
                      f"Nenhum trecho acima da dose autorizada ({taxa_autorizada} L/ha)."
                      if not acima else f"{len(acima)} trecho(s) acima da dose autorizada."))
    eq = mapa.get("equipamento") or {}
    cmin, cmax = float(eq.get("ciclo_min", 0.2)), float(eq.get("ciclo_max", 1.0))
    ruins = [z for z in aplicadas if not (z.get("bico") or {}).get("viavel", False)
             or not cmin - 1e-9 <= float((z.get("bico") or {}).get("ciclo", -1)) <= cmax + 1e-9]
    saida.append(("map_pwm", not ruins,
                  "PWM de todo trecho dentro dos limites da máquina." if not ruins else
                  f"{len(ruins)} trecho(s) com ciclo de PWM fora de [{cmin}, {cmax}] ou "
                  "inviável."))
    registro = (mapa.get("produto") or {}).get("registro_mapa")
    saida.append(("map_product", bool(registro) and registro == registro_do_produto,
                  "O mapa é do produto da missão." if registro == registro_do_produto else
                  f"O mapa é de outro produto (registro {registro!r})."))
    return saida
