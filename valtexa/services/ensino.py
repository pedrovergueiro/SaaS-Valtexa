"""O agrônomo ensinando a IA: registrar a lição, devolvê-la ao parecer, medir o que mudou.

Ver :mod:`valtexa.models.ensino`. O rótulo diz **o quê**; a lição guarda também o **porquê** (os
sintomas, o terço da planta, a face da folha, o texto dele) e o **onde** (as lesões na foto).
Cada parte serve a uma coisa:

* as lesões viram recortes de treino (``training.import_licoes`` na IA): a cabeça aprende a
  lesão, não a foto inteira — numa folha com uma pústula, 95% da imagem é folha sadia;
* o porquê volta nos pareceres seguintes do talhão como evidência com autor e data;
* tudo junto vira o painel "o que a IA aprendeu com você" (:func:`painel`).

O vocabulário de sintomas é **sugestão**, não lista fechada: o agrônomo escreve o que viu, e
o que ele escrever entra como está.
"""

from __future__ import annotations

import io
import json
import math
import zipfile
from collections import Counter, defaultdict
from collections.abc import Callable
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from valtexa.models import (
    Asset,
    DatasetSample,
    DatasetSampleState,
    DatasetVersion,
    Detection,
    Diagnosis,
    DiagnosisStatus,
    Field,
    LicaoAgronomo,
    Observation,
    OpiniaoAmostra,
    RegraAgronomo,
    User,
)

ESTRATOS = ("terco_inferior", "terco_medio", "terco_superior", "indeterminado")
FACES = ("adaxial", "abaxial", "ambas", "indeterminada")
MAX_LESOES = 20

SINTOMAS: dict[str, list[str]] = {
    "Rust": ["pústulas alaranjadas (pó) na face de baixo", "manchas amareladas na face de cima",
             "lesões coalescendo", "desfolha"],
    "Cercospora_Leaf_Spot": ["mancha circular de centro claro (olho-de-pomba)",
                             "halo amarelado", "anel arroxeado na borda",
                             "lesão também no fruto"],
    "Leaf_Miner_Damage": ["mina necrótica que destaca a epiderme", "galeria com bordas",
                          "lagarta ou pupa visível", "lesão seca que rasga"],
    "Phoma_Leaf_Spot": ["necrose nas pontas e bordas de folhas novas", "seca de ponteiro",
                        "lesão escura com anéis", "folha nova deformada"],
    "Healthy": ["folha sem lesão", "dano mecânico (não é doença)",
                "deficiência nutricional (não é doença)"],
}
"""Sugestões por classe (café). Para o resto, :data:`SINTOMAS_GERAIS`."""

SINTOMAS_GERAIS = ["clorose", "necrose", "mancha", "pústula", "mina", "deformação", "desfolha",
                   "sujeira ou fuligem", "dano de inseto", "dano mecânico"]

ALVO_POR_CLASSE_NOVA = 30
"""Exemplos confirmados de uma classe que o modelo não tem, antes de valer treinar com ela:
abaixo disso, a classe nova não tem nem validação nem teste separados por planta."""


class LicaoInvalidaError(ValueError):
    """Lesão fora da foto, estrato ou face desconhecidos. Vira 422."""


def vocabulario(rotulo: str | None = None) -> dict[str, Any]:
    return {"estratos": list(ESTRATOS), "faces": list(FACES),
            "sintomas": SINTOMAS.get(rotulo or "", []) + SINTOMAS_GERAIS,
            "por_classe": SINTOMAS}


def _lesoes(brutas: list[dict] | list[list[float]]) -> list[list[float]]:
    if len(brutas) > MAX_LESOES:
        raise LicaoInvalidaError(f"No máximo {MAX_LESOES} lesões por foto.")
    saida = []
    for b in brutas:
        x, y, w, h = (b["x"], b["y"], b["w"], b["h"]) if isinstance(b, dict) else b
        if not (x >= 0 and y >= 0 and w > 0 and h > 0 and x + w <= 1 + 1e-6
                and y + h <= 1 + 1e-6):
            raise LicaoInvalidaError("Lesão fora da foto: x, y, w, h normalizados em [0, 1].")
        saida.append([round(float(v), 5) for v in (x, y, w, h)])
    return saida


def registrar(session: Session, *, tenant_id: str, field_id: str, origem: str, autor: User,
              rotulo: str, rotulo_da_ia: str | None, explicacao: dict | None = None,
              lesoes: list | None = None, observation_id: str | None = None,
              diagnosis_id: str | None = None, parecer_id: str | None = None,
              plant_ref: str | None = None) -> LicaoAgronomo:
    """Grava a lição. Não faz *commit*."""
    explicacao = explicacao or {}
    estrato, face = explicacao.get("estrato"), explicacao.get("face")
    if estrato is not None and estrato not in ESTRATOS:
        raise LicaoInvalidaError(f"Estrato {estrato!r}: use {', '.join(ESTRATOS)}.")
    if face is not None and face not in FACES:
        raise LicaoInvalidaError(f"Face {face!r}: use {', '.join(FACES)}.")
    sintomas = [s.strip() for s in explicacao.get("sintomas") or [] if s and s.strip()][:12]
    porque = (explicacao.get("porque") or "").strip() or None
    licao = LicaoAgronomo(
        tenant_id=tenant_id, field_id=field_id, origem=origem, observation_id=observation_id,
        diagnosis_id=diagnosis_id, parecer_id=parecer_id, plant_ref=plant_ref,
        autor_id=autor.id, autor_rotulo=autor.full_name or autor.email, rotulo=rotulo,
        rotulo_da_ia=rotulo_da_ia, sintomas=sintomas, estrato=estrato, face=face, porque=porque,
        lesoes=_lesoes(lesoes or []))
    session.add(licao)
    session.flush()
    return licao


def resumo(licao: LicaoAgronomo) -> dict[str, Any]:
    return {"id": licao.id, "origem": licao.origem, "field_id": licao.field_id,
            "observation_id": licao.observation_id, "plant_ref": licao.plant_ref,
            "autor": licao.autor_rotulo, "quando": licao.created_at.isoformat(),
            "rotulo": licao.rotulo, "rotulo_da_ia": licao.rotulo_da_ia,
            "sintomas": licao.sintomas, "estrato": licao.estrato, "face": licao.face,
            "porque": licao.porque, "lesoes": len(licao.lesoes or [])}


def para_o_parecer(session: Session, tenant_id: str, field_id: str, rotulos: set[str],
                   limite: int = 5) -> list[dict[str, Any]]:
    """O que o agrônomo já ensinou sobre estas classes, primeiro neste talhão (só lição com
    porquê ou sintomas: rótulo sozinho não explica nada)."""
    if not rotulos:
        return []
    linhas = session.scalars(
        select(LicaoAgronomo)
        .where(LicaoAgronomo.tenant_id == tenant_id, LicaoAgronomo.rotulo.in_(rotulos))
        .order_by(LicaoAgronomo.created_at.desc())
        .limit(200)
    ).all()
    explicadas = [x for x in linhas if x.porque or x.sintomas]
    explicadas.sort(key=lambda x: x.field_id != field_id)  # estável: do talhão primeiro
    return [resumo(x) for x in explicadas[:limite]]


# ---------------------------------------------------------------------------------------------
# O que a IA aprendeu com você
# ---------------------------------------------------------------------------------------------


def painel(session: Session, tenant_id: str, autor_id: str | None = None) -> dict[str, Any]:
    """As lições (de um agrônomo, ou do cliente todo) e a IA contra elas, mês a mês."""
    consulta = select(LicaoAgronomo).where(LicaoAgronomo.tenant_id == tenant_id)
    if autor_id is not None:
        consulta = consulta.where(LicaoAgronomo.autor_id == autor_id)
    licoes = session.scalars(consulta.order_by(LicaoAgronomo.created_at)).all()

    por_rotulo = Counter(x.rotulo for x in licoes)
    confusoes = Counter((x.rotulo_da_ia, x.rotulo) for x in licoes
                        if x.rotulo_da_ia and x.rotulo_da_ia != x.rotulo)
    mes: dict[str, dict[str, int]] = defaultdict(lambda: {"casos": 0, "ia_acertou": 0})
    for x in licoes:
        if x.origem != "fila" or x.rotulo_da_ia is None:
            continue
        m = mes[x.created_at.strftime("%Y-%m")]
        m["casos"] += 1
        m["ia_acertou"] += x.rotulo_da_ia == x.rotulo

    classes_do_modelo = _classes_do_modelo(session, tenant_id)
    novas = [{"rotulo": r, "exemplos": n, "faltam": max(0, ALVO_POR_CLASSE_NOVA - n)}
             for r, n in por_rotulo.most_common()
             if classes_do_modelo and r not in classes_do_modelo]
    return {
        "licoes": len(licoes),
        "com_porque": sum(1 for x in licoes if x.porque or x.sintomas),
        "com_lesao_marcada": sum(1 for x in licoes if x.lesoes),
        "lesoes_marcadas": sum(len(x.lesoes or []) for x in licoes),
        "por_rotulo": dict(por_rotulo.most_common()),
        "onde_a_ia_mais_erra": [{"ia_dizia": a, "voce_disse": b, "vezes": n}
                                for (a, b), n in confusoes.most_common(8)],
        "acerto_da_ia_por_mes": [
            {"mes": k, **v, "taxa": round(v["ia_acertou"] / v["casos"], 4)}
            for k, v in sorted(mes.items())],
        "classes_novas": novas,
        "alvo_por_classe_nova": ALVO_POR_CLASSE_NOVA,
        "ultimas": [resumo(x) for x in list(licoes)[-10:][::-1]],
        "vies": "O acerto é medido nos casos que foram à fila, os difíceis: a curva mostra a "
                "tendência, não o acerto na lavoura.",
    }


def _classes_do_modelo(session: Session, tenant_id: str) -> set[str]:
    """As classes que os modelos já devolveram para este cliente (das probabilidades)."""
    linha = session.scalars(
        select(Detection.probabilities)
        .where(Detection.tenant_id == tenant_id, Detection.source != "human")
        .order_by(Detection.created_at.desc())
        .limit(50)
    ).all()
    return {k for probs in linha for k in (probs or {})}


# ---------------------------------------------------------------------------------------------
# Exportação do corte para o treino
# ---------------------------------------------------------------------------------------------


def exportar_corte(session: Session, versao: DatasetVersion, ler: Any) -> bytes:
    """O corte congelado num zip: ``imagens/<amostra>.<ext>`` e ``manifesto.jsonl`` (uma linha
    por amostra: rótulo, o que a máquina dizia, o grupo para separar treino e teste — a planta,
    ou a observação —, as lesões e o porquê). ``ler(storage_key) -> bytes``.

    O cliente vai como um hash curto, não pelo id: o manifesto sai da plataforma.
    """
    import hashlib

    amostras = session.scalars(
        select(DatasetSample).where(DatasetSample.id.in_(versao.sample_ids or []))).all()
    licoes = {x.diagnosis_id: x for x in session.scalars(
        select(LicaoAgronomo).where(LicaoAgronomo.diagnosis_id.in_(
            [a.diagnosis_id for a in amostras if a.diagnosis_id]))
        .order_by(LicaoAgronomo.created_at))}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        linhas = []
        for a in amostras:
            asset = session.get(Asset, a.asset_id)
            if asset is None:
                continue
            ext = {"image/png": "png", "image/webp": "webp"}.get(asset.content_type, "jpg")
            nome = f"imagens/{a.id}.{ext}"
            z.writestr(nome, ler(asset.storage_key))
            obs = session.get(Observation, a.observation_id) if a.observation_id else None
            licao = licoes.get(a.diagnosis_id)
            linhas.append(json.dumps({
                "amostra": a.id, "arquivo": nome, "rotulo": a.label,
                "rotulo_da_maquina": a.machine_label,
                "grupo": (obs.plant_ref if obs and obs.plant_ref else a.observation_id or a.id),
                "cliente": hashlib.sha256(a.tenant_id.encode()).hexdigest()[:12],
                "lesoes": licao.lesoes if licao else [],
                "sintomas": licao.sintomas if licao else [],
                "estrato": licao.estrato if licao else None,
                "face": licao.face if licao else None,
                "porque": licao.porque if licao else None,
            }, ensure_ascii=False))
        z.writestr("manifesto.jsonl", "\n".join(linhas) + "\n")
        z.writestr("LEIAME.txt", (
            f"Corte {versao.version} ({len(linhas)} amostras), congelado em "
            f"{versao.frozen_at.isoformat() if versao.frozen_at else '?'}.\n"
            "Na IA: python -m training.import_licoes --zip <este arquivo> --out data/<pasta>\n"))
    return buf.getvalue()


# ---------------------------------------------------------------------------------------------
# Segunda opinião e confiabilidade
# ---------------------------------------------------------------------------------------------

POLITICAS = ("um", "consenso", "confiabilidade")
"""Como o corte escolhe as amostras: ``um`` (o agrônomo que rotulou basta), ``consenso`` (só o
que uma segunda opinião confirmou) e ``confiabilidade`` (confirmado, ou de quem concorda com os
colegas ao menos ``confiabilidade_minima`` das vezes, em pelo menos ``pares_minimos`` pares).
Amostra **em disputa** (alguém discordou) fica fora em qualquer política, até ser resolvida."""


class OpiniaoInvalidaError(ValueError):
    """Opinião sobre a própria amostra, ou repetida. Vira 409."""


def opinar(session: Session, *, amostra: DatasetSample, revisor: User, origem: str,
           rotulo: str, comentario: str | None = None) -> OpiniaoAmostra:
    if amostra.reviewer_id == revisor.id:
        raise OpiniaoInvalidaError("A segunda opinião é de outro agrônomo, não de quem rotulou.")
    if session.scalars(select(OpiniaoAmostra).where(
            OpiniaoAmostra.dataset_sample_id == amostra.id,
            OpiniaoAmostra.revisor_id == revisor.id)).first():
        raise OpiniaoInvalidaError("Você já deu opinião sobre esta amostra.")
    op = OpiniaoAmostra(dataset_sample_id=amostra.id, revisor_id=revisor.id,
                        revisor_rotulo=revisor.full_name or revisor.email, origem=origem,
                        rotulo=rotulo, concorda=rotulo == amostra.label,
                        comentario=(comentario or "").strip() or None)
    session.add(op)
    session.flush()
    return op


def pendentes_de_opiniao(session: Session, *, revisor_id: str, tenant_id: str | None = None,
                         dataset_id: str | None = None, limite: int = 50) -> list[dict[str, Any]]:
    """Amostras de outros agrônomos que este ainda não viu (as em disputa primeiro)."""
    ja = select(OpiniaoAmostra.dataset_sample_id).where(OpiniaoAmostra.revisor_id == revisor_id)
    consulta = select(DatasetSample).where(
        DatasetSample.state != DatasetSampleState.EXCLUDED,
        (DatasetSample.reviewer_id != revisor_id) | DatasetSample.reviewer_id.is_(None),
        DatasetSample.id.not_in(ja))
    if tenant_id is not None:
        consulta = consulta.where(DatasetSample.tenant_id == tenant_id)
    if dataset_id is not None:
        consulta = consulta.where(DatasetSample.dataset_id == dataset_id)
    amostras = session.scalars(consulta.order_by(DatasetSample.created_at.desc())
                               .limit(500)).all()
    opinioes = _opinioes(session, [a.id for a in amostras])
    licoes = {x.diagnosis_id: x for x in session.scalars(select(LicaoAgronomo).where(
        LicaoAgronomo.diagnosis_id.in_([a.diagnosis_id for a in amostras if a.diagnosis_id])))}
    saida = []
    for a in amostras:
        ops = opinioes.get(a.id, [])
        licao = licoes.get(a.diagnosis_id)
        saida.append({
            "amostra_id": a.id, "observation_id": a.observation_id, "rotulo": a.label,
            "rotulo_da_maquina": a.machine_label, "autor": a.reviewer_label,
            "em_disputa": any(not o.concorda for o in ops), "opinioes": len(ops),
            "sintomas": licao.sintomas if licao else [], "porque": licao.porque if licao else None,
            "lesoes": licao.lesoes if licao else []})
    saida.sort(key=lambda x: (not x["em_disputa"], x["opinioes"]))
    return saida[:limite]


def _opinioes(session: Session, ids: list[str]) -> dict[str, list[OpiniaoAmostra]]:
    saida: dict[str, list[OpiniaoAmostra]] = defaultdict(list)
    if ids:
        for o in session.scalars(select(OpiniaoAmostra).where(
                OpiniaoAmostra.dataset_sample_id.in_(ids))):
            saida[o.dataset_sample_id].append(o)
    return saida


def confiabilidade(session: Session) -> dict[str, dict[str, Any]]:
    """Por agrônomo: em quantos pares (ele rotulou e outro opinou, ou o contrário) os dois
    disseram o mesmo. O índice é suavizado, (concordâncias + 1) / (pares + 2), para que dois
    acertos seguidos não valham "100% confiável"."""
    pares: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    linhas = session.execute(select(DatasetSample.reviewer_id, OpiniaoAmostra.revisor_id,
                                    OpiniaoAmostra.concorda)
                             .join(DatasetSample,
                                   DatasetSample.id == OpiniaoAmostra.dataset_sample_id))
    for autor, revisor, concorda in linhas:
        for pessoa in (autor, revisor):
            if pessoa:
                pares[pessoa][0] += 1
                pares[pessoa][1] += bool(concorda)
    return {p: {"pares": n, "concordancias": k, "indice": round((k + 1) / (n + 2), 4)}
            for p, (n, k) in pares.items()}


def escolher_para_o_corte(session: Session, amostras: list[DatasetSample], politica: str,
                          confiabilidade_minima: float = 0.8, pares_minimos: int = 10
                          ) -> tuple[list[DatasetSample], dict[str, Any]]:
    """As amostras que entram no corte pela política, e o que ficou fora (e por quê)."""
    if politica not in POLITICAS:
        raise ValueError(f"Política {politica!r}: use {', '.join(POLITICAS)}.")
    opinioes = _opinioes(session, [a.id for a in amostras])
    confia = confiabilidade(session) if politica == "confiabilidade" else {}
    entram, fora = [], Counter()
    for a in amostras:
        ops = opinioes.get(a.id, [])
        if any(not o.concorda for o in ops):
            fora["em_disputa"] += 1
            continue
        if politica == "um" or ops:
            entram.append(a)
            continue
        c = confia.get(a.reviewer_id or "", {})
        if (politica == "confiabilidade" and c.get("pares", 0) >= pares_minimos
                and c.get("indice", 0.0) >= confiabilidade_minima):
            entram.append(a)
        else:
            fora["sem_segunda_opiniao" if politica == "consenso" else
                 "sem_consenso_nem_autor_confiavel"] += 1
    return entram, {"politica": politica, "confiabilidade_minima": confiabilidade_minima,
                    "pares_minimos": pares_minimos, "fora": dict(fora),
                    "com_segunda_opiniao": sum(1 for a in entram if opinioes.get(a.id))}


# ---------------------------------------------------------------------------------------------
# Regras do agrônomo, medidas no histórico
# ---------------------------------------------------------------------------------------------

VARIAVEIS_DE_CLIMA = {"chuva_mm": "soma", "molhamento_h": "soma", "ur_media": "media",
                      "t_media": "media"}
MINIMO_POR_LADO = 20
"""Observações com e sem a condição, cada lado, antes de a medida dizer alguma coisa."""


class RegraInvalidaError(ValueError):
    """Condição que não se pode medir. Vira 422."""


def valida_condicao(condicao: dict[str, Any]) -> dict[str, Any]:
    v = condicao.get("variavel")
    if v == "mes":
        meses = sorted({int(m) for m in condicao.get("meses") or []})
        if not meses or any(m < 1 or m > 12 for m in meses):
            raise RegraInvalidaError("Mês: informe os meses (1 a 12).")
        return {"variavel": "mes", "meses": meses}
    if v not in VARIAVEIS_DE_CLIMA:
        raise RegraInvalidaError(f"Variável {v!r}: use mes, {', '.join(VARIAVEIS_DE_CLIMA)}.")
    janela = int(condicao.get("janela_dias") or 0)
    if not 1 <= janela <= 60:
        raise RegraInvalidaError("janela_dias de 1 a 60.")
    if condicao.get("operador") not in ("<", ">"):
        raise RegraInvalidaError("operador: < ou >.")
    try:
        valor = float(condicao["valor"])
    except (KeyError, TypeError, ValueError) as exc:
        raise RegraInvalidaError("valor: um número.") from exc
    return {"variavel": v, "janela_dias": janela, "operador": condicao["operador"],
            "valor": valor}


def descreve_condicao(c: dict[str, Any]) -> str:
    if c["variavel"] == "mes":
        return "nos meses " + ", ".join(str(m) for m in c["meses"])
    nome = {"chuva_mm": "chuva acumulada (mm)", "molhamento_h": "horas de folha molhada",
            "ur_media": "umidade relativa média (%)", "t_media": "temperatura média (°C)"}
    return (f"{nome[c['variavel']]} nos {c['janela_dias']} dias anteriores "
            f"{'abaixo' if c['operador'] == '<' else 'acima'} de {c['valor']:g}")


def _condicao_vale(c: dict[str, Any], dia: date, serie: dict[str, dict] | None) -> bool | None:
    if c["variavel"] == "mes":
        return dia.month in c["meses"]
    if serie is None:
        return None
    valores = [serie[(dia - timedelta(days=k)).isoformat()][c["variavel"]]
               for k in range(1, c["janela_dias"] + 1)
               if (dia - timedelta(days=k)).isoformat() in serie]
    if len(valores) < 0.8 * c["janela_dias"]:
        return None  # janela sem tempo suficiente: não conta nem a favor nem contra
    agregado = sum(valores) if VARIAVEIS_DE_CLIMA[c["variavel"]] == "soma" else (
        sum(valores) / len(valores))
    return agregado < c["valor"] if c["operador"] == "<" else agregado > c["valor"]


def medir_regra(session: Session, regra: RegraAgronomo,
                serie_do_talhao: Callable[[str], dict[str, dict] | None]) -> dict[str, Any]:
    """A doença aparece mais (ou menos) quando a condição vale? No histórico do cliente.

    Conta as observações dos talhões da cultura com diagnóstico de confiança (as duas análises
    concordaram, ou o agrônomo confirmou) e compara a taxa da doença com e sem a condição, por
    teste de duas proporções. ``serie_do_talhao(field_id)`` devolve ``{data ISO: dia}`` ou
    ``None``. Não grava: quem chama decide (a rota grava em ``regra.medida``).
    """
    campos = {f.id for f in session.scalars(select(Field).where(
        Field.tenant_id == regra.tenant_id, Field.crop == regra.cultura))}
    if not campos:
        return {"veredito": "poucos_dados", "motivo": "nenhum talhão da cultura"}
    linhas = session.execute(
        select(Diagnosis.field_id, Diagnosis.label, Diagnosis.reviewed_label,
               Observation.captured_at)
        .join(Observation, Observation.id == Diagnosis.observation_id)
        .where(Diagnosis.tenant_id == regra.tenant_id, Diagnosis.field_id.in_(campos),
               Diagnosis.status.in_([DiagnosisStatus.AI_VALIDATED,
                                     DiagnosisStatus.HUMAN_CONFIRMED])))
    series: dict[str, dict[str, dict] | None] = {}
    n = {True: 0, False: 0}
    k = {True: 0, False: 0}
    sem_clima = 0
    for field_id, rotulo, revisado, quando in linhas:
        if quando is None:
            continue
        if field_id not in series and regra.condicao["variavel"] != "mes":
            series[field_id] = serie_do_talhao(field_id)
        vale = _condicao_vale(regra.condicao, quando.date(), series.get(field_id))
        if vale is None:
            sem_clima += 1
            continue
        n[vale] += 1
        k[vale] += (revisado or rotulo) == regra.doenca
    medida: dict[str, Any] = {"com_condicao": {"casos": n[True], "com_doenca": k[True]},
                              "sem_condicao": {"casos": n[False], "com_doenca": k[False]},
                              "sem_clima": sem_clima, "p_valor": None}
    if min(n.values()) < MINIMO_POR_LADO or k[True] + k[False] < 5:
        return {**medida, "veredito": "poucos_dados",
                "motivo": f"são precisos {MINIMO_POR_LADO} casos de cada lado e 5 com a doença"}
    p1, p0 = k[True] / n[True], k[False] / n[False]
    p = (k[True] + k[False]) / (n[True] + n[False])
    erro = math.sqrt(p * (1 - p) * (1 / n[True] + 1 / n[False]))
    z = (p1 - p0) / erro if erro else 0.0
    p_valor = math.erfc(abs(z) / math.sqrt(2))
    medida["p_valor"] = round(p_valor, 4)
    if p_valor >= 0.05:
        veredito = "nao_mostrada"
    elif (p1 > p0) == (regra.efeito == "aumenta"):
        veredito = "sustentada"
    else:
        veredito = "contrariada"
    return {**medida, "veredito": veredito}


VEREDITOS = {"sustentada": "sustentada pelo histórico do cliente",
             "contrariada": "contrariada pelo histórico do cliente",
             "nao_mostrada": "o histórico do cliente não mostrou diferença",
             "poucos_dados": "ainda sem casos suficientes para medir",
             "nao_medida": "ainda não medida"}


def regras_para_o_parecer(session: Session, tenant_id: str, rotulos: set[str]
                          ) -> list[dict[str, Any]]:
    if not rotulos:
        return []
    return [{"autor": r.autor_rotulo, "regra": r.texto, "doenca": r.doenca,
             "condicao": descreve_condicao(r.condicao), "efeito": r.efeito,
             "veredito": (r.medida or {}).get("veredito") or "nao_medida",
             "com_condicao": (r.medida or {}).get("com_condicao"),
             "sem_condicao": (r.medida or {}).get("sem_condicao")}
            for r in session.scalars(select(RegraAgronomo).where(
                RegraAgronomo.tenant_id == tenant_id, RegraAgronomo.ativa.is_(True),
                RegraAgronomo.doenca.in_(rotulos)).order_by(RegraAgronomo.created_at))]
