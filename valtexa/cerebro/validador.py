"""O validador das afirmações do parecer: o que o texto pode dizer.

Vale para o texto do provedor de linguagem (quando ligado) e — por teste — para o do
compositor determinístico. Uma afirmação é **recusada** quando:

1. ``sem_citacao`` — não cita nada;
2. ``citacao_inexistente`` — cita ``E<n>``/``F<n>`` que não está no dossiê nem nas fontes;
3. ``numero_sem_evidencia`` — tem um número que não aparece nos itens citados (dados,
   limitações, título) nem no texto do trecho citado. Comparação pelo número de casas que o
   texto mostra ("0,62" casa com 0.6193; "62%" casa com 0.62); identificadores e datas que
   estão nos itens citados não contam como número;
4. ``linguagem_de_certeza`` — "certamente", "com certeza", "sem dúvida", "comprovado",
   "garantido", "definitivamente", "trata-se de", "100%"... sobre o que é probabilidade;
5. ``recomendacao_operacional`` — manda aplicar/pulverizar ou dá dose (``L/ha``, ``kg/ha``):
   o parecer não recomenda produto nem dose, ele lista o que verificar;
6. ``fonte_bloqueada`` — cita fonte regulatória sem uso operacional (vencida, não
   verificada, fictícia) sem dizer que ela está bloqueada.

A lista de padrões é conservadora e está aqui, à vista: um padrão novo entra com teste.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

CITACAO = re.compile(r"^[EF]\d{1,4}$")
_NUMERO = re.compile(r"(?<![\w.,])(\d+(?:[.,]\d+)?)(\s?%)?(?![\w])")
_MARCA = re.compile(r"\[[EF]\d{1,4}(?:\s*,\s*[EF]\d{1,4})*\]")

CERTEZA = tuple(re.compile(p) for p in (
    r"\bcertamente\b", r"\bcom (toda )?certeza\b", r"\bha certeza\b", r"\bsem duvidas?\b",
    r"\bdefinitivamente\b", r"\bcomprovad[oa]s?\b", r"\bgarantid[oa]s?\b", r"\binequivoc",
    r"\bindubitave", r"\btrata-se de\b", r"\bcom seguranca\b", r"\b100 ?%",
    r"\bseguramente\b", r"\bobviamente\b",
    r"(?<!nao )(?<!nao esta )(?<!nao foi )(?<!nao e )(?<!nem )\bconfirmad[oa]s?\b",
    r"\bnao ha (outra|nenhuma) (hipotese|alternativa)\b",
))
OPERACIONAL = tuple(re.compile(p) for p in (
    r"\b(aplique|aplicar|aplicacao imediata|pulverize|pulverizar|pulverizacao imediata)\b",
    r"\brecomenda-se (o uso|usar|aplicar)\b", r"\bdeve(m)? ser aplicad",
    r"\d\s*(l|ml|kg|g)\s*/\s*ha\b", r"\b(litros|quilos|gramas) por hectare\b",
))
BLOQUEIO_DECLARADO = re.compile(r"(bloquead|vencid|nao verificad|ficticia|ficticio|sem uso "
                                r"operacional|sem validade)")


LIVRES = frozenset({"talhao", "plant_ref", "diagnostico_revisor", "comentario", "nome"})
"""Chaves de texto livre do dossiê (o que alguém digitou ou o Rover mandou). O texto delas
vale como identificador, mas **um número dentro delas não é evidência**: um talhão chamado
"0,99" não sustenta "probabilidade 0,99"."""


def dobra(texto: str) -> str:
    return "".join(ch for ch in unicodedata.normalize("NFKD", texto.lower())
                   if not unicodedata.combining(ch))


def _folhas(obj: Any, numeros: list[float], textos: list[str]) -> None:
    if isinstance(obj, bool) or obj is None:
        return
    if isinstance(obj, (int, float)):
        numeros.append(float(obj))
    elif isinstance(obj, str):
        textos.append(obj)
        for m in _NUMERO.finditer(obj):
            numeros.append(float(m.group(1).replace(",", ".")))
    elif isinstance(obj, dict):
        for k, v in obj.items():
            _folhas(k, numeros, textos)
            if k in LIVRES and isinstance(v, str):
                textos.append(v)
                continue
            _folhas(v, numeros, textos)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _folhas(v, numeros, textos)


def _bate(valor: float, casas: int, percentual: bool, conhecidos: list[float]) -> bool:
    for e in conhecidos:
        candidatos = [e, e * 100] if percentual else [e]
        if percentual and e > 1:
            candidatos.append(e)
        for c in candidatos:
            if round(c, casas) == round(valor, casas):
                return True
    return False


class Validador:
    """Monta, uma vez, o índice do que cada citação permite dizer."""

    def __init__(self, dossie: dict[str, Any], fontes: list[dict[str, Any]]) -> None:
        self.itens = {i["id"]: i for i in dossie["itens"]}
        self.fontes = {f["id"]: f for f in fontes}

    def _evidencia(self, citacoes: list[str]) -> tuple[list[float], list[str]]:
        numeros: list[float] = []
        textos: list[str] = []
        for c in citacoes:
            if c in self.itens:
                it = self.itens[c]
                _folhas([it["titulo"], it["dados"], it["limitacoes"],
                         it.get("motivo_indisponivel")], numeros, textos)
            elif c in self.fontes:
                f = self.fontes[c]
                _folhas([f["texto"], f["titulo"], f["versao"], f.get("secao"),
                         f.get("bloqueio"), f.get("origem")], numeros, textos)
        return numeros, textos

    def recusas(self, afirmacao: dict[str, Any]) -> list[str]:
        texto = str(afirmacao.get("texto") or "")
        citacoes = [str(c) for c in afirmacao.get("citacoes") or []]
        motivos: list[str] = []
        if not texto.strip():
            return ["texto_vazio"]
        if not citacoes:
            motivos.append("sem_citacao")
        if any(not CITACAO.match(c) or (c not in self.itens and c not in self.fontes)
               for c in citacoes):
            motivos.append("citacao_inexistente")
        numeros, textos = self._evidencia(citacoes)
        limpo = _MARCA.sub(" ", texto)
        # Identificadores e datas que estão na evidência citada não são "números".
        for s in sorted({s for s in textos if any(ch.isdigit() for ch in s) and len(s) >= 3},
                        key=len, reverse=True):
            limpo = limpo.replace(s, " ")
        for m in _NUMERO.finditer(limpo):
            bruto = m.group(1)
            casas = len(bruto.replace(",", ".").partition(".")[2])
            if not _bate(float(bruto.replace(",", ".")), casas, bool(m.group(2)), numeros):
                motivos.append(f"numero_sem_evidencia:{bruto}{(m.group(2) or '').strip()}")
        dobrado = dobra(texto)
        if any(p.search(dobrado) for p in CERTEZA):
            motivos.append("linguagem_de_certeza")
        if any(p.search(dobrado) for p in OPERACIONAL):
            motivos.append("recomendacao_operacional")
        for c in citacoes:
            f = self.fontes.get(c)
            if f and (f.get("regulatorio") or f.get("ficticio")) and not f.get(
                    "uso_operacional") and not BLOQUEIO_DECLARADO.search(dobrado):
                motivos.append(f"fonte_bloqueada:{c}")
        return motivos

    def valida(self, afirmacoes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """As recusas (vazio = tudo aceito), uma entrada por afirmação recusada."""
        saida = []
        for i, a in enumerate(afirmacoes):
            if not isinstance(a, dict):
                saida.append({"indice": i, "texto": str(a)[:300], "motivos": ["formato"]})
                continue
            motivos = self.recusas(a)
            if motivos:
                saida.append({"indice": i, "texto": str(a.get("texto"))[:300],
                              "citacoes": a.get("citacoes"), "motivos": motivos})
        return saida
