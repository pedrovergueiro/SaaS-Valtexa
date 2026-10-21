"""Consenso federado (7.1): contagens conferidas por estrato, fusão hierárquica com
encolhimento, compatibilidade, anti-eco, avaliação antes de distribuir e bytes medidos.

Os talhões, as taxas e os diagnósticos daqui são **simulados** (sementes fixas)."""

from __future__ import annotations

import random
from datetime import date, timedelta

import pytest
from sqlalchemy import select

from valtexa.models import (
    Agreement,
    Detection,
    DetectionSource,
    Diagnosis,
    DiagnosisStatus,
    Farm,
    Field,
    Observation,
    Tenant,
    utcnow,
)
from valtexa.services import federado as fed

CLASSES = ["Cercospora_Leaf_Spot", "Healthy", "Rust"]
P = fed.Protocolo(fed.Protocolo.taxonomia(CLASSES), "coffee", "cabeca-1", "agronomo")
INI, FIM = date(2026, 9, 1), date(2026, 10, 1)


def _contagens(taxas: dict[str, float], talhoes_por_estrato: int = 3, plantas: int = 80,
               semente: int = 1, classe: str = "Rust") -> list[fed.Contagem]:
    rng = random.Random(semente)
    saida = []
    for estrato, taxa in taxas.items():
        for t in range(talhoes_por_estrato):
            obs = frozenset(f"{estrato}{t}-{k}" for k in range(plantas))
            pos = frozenset(o for o in sorted(obs) if rng.random() < taxa)
            saida.append(fed.Contagem(f"talhao-{estrato}{t}", (estrato, "?", "granacao"), classe,
                                    obs, pos, INI, FIM, P))
    return saida


# -- compatibilidade e anti-eco ----------------------------------------------------------------


@pytest.mark.parametrize(("troca", "motivo"), [
    ({"protocolo": fed.Protocolo("outra", "coffee", "cabeca-1", "agronomo")}, "taxonomia"),
    ({"protocolo": fed.Protocolo(P.taxonomia_sha256, "coffee", "cabeca-2", "agronomo")}, "cabeça"),
    ({"protocolo": fed.Protocolo(P.taxonomia_sha256, "coffee", "cabeca-1", "rover")}, "validação"),
    ({"inicio": date(2025, 1, 1)}, "janela"),
    ({"observacoes": frozenset()}, "vazia"),
    ({"positivas": frozenset({"fora"})}, "positivas fora"),
])
def test_compatibilidade_recusa_com_motivo(troca, motivo) -> None:
    base = _contagens({"A": 0.1}, talhoes_por_estrato=1)[0]
    campos = {**base.__dict__, **troca}
    assert motivo in fed.compativel(fed.Contagem(**campos), P, inicio=INI, fim=FIM)
    assert fed.compativel(base, P, inicio=INI, fim=FIM) is None


def test_a_mesma_observacao_conta_uma_vez() -> None:
    a = fed.Contagem("t1", ("A", "?", "g"), "Rust", frozenset({"o1", "o2", "o3"}),
                   frozenset({"o1"}), INI, FIM, P)
    b = fed.Contagem("t2", ("A", "?", "g"), "Rust", frozenset({"o1", "o4"}),
                   frozenset({"o1", "o4"}), INI, FIM, P)  # o1 reenviada por outro Rover
    limpas, descartadas = fed.sem_eco([b, a])
    assert descartadas == 1
    assert sum(c.n for c in limpas) == 4 and sum(c.positivos for c in limpas) == 2


def test_o_prior_que_volta_ao_talhao_nao_tem_o_dado_dele() -> None:
    """Anti-eco por origem: mudar o dado do próprio talhão não muda o prior que ele recebe."""
    cs = _contagens({"A": 0.05, "B": 0.15, "C": 0.10})
    alvo = ("A", "?", "granacao")
    antes = fed.prior_para(cs, destino="talhao-A0", estrato=alvo, classe="Rust")
    trocado = [c if c.origem != "talhao-A0" else fed.Contagem(
        c.origem, c.estrato, c.classe, c.observacoes, c.observacoes, c.inicio, c.fim,
        c.protocolo) for c in cs]  # 100% de ferrugem no próprio talhão
    depois = fed.prior_para(trocado, destino="talhao-A0", estrato=alvo, classe="Rust")
    assert antes == depois
    assert antes["plantas_de_outros_talhoes"] == 8 * 80 and antes["talhoes"] == 8


# -- a fusão -----------------------------------------------------------------------------------


def test_encolhimento_segue_a_heterogeneidade_dos_estratos() -> None:
    iguais = [(10, 100), (11, 100), (9, 100)]
    diferentes = [(2, 100), (30, 100), (60, 100)]
    assert fed.concentracao(iguais, forca_maxima=200) == 200  # junta tudo
    k = fed.concentracao(diferentes, forca_maxima=200)
    assert fed.KAPPA_MINIMO <= k < 10  # cada estrato fica com o seu


def test_prior_do_estrato_puxa_para_o_estrato_e_a_forca_tem_teto() -> None:
    cs = _contagens({"A": 0.03, "B": 0.30}, talhoes_por_estrato=4, plantas=200)
    pa = fed.prior_para(cs, destino="talhao-A0", estrato=("A", "?", "granacao"), classe="Rust")
    pb = fed.prior_para(cs, destino="talhao-B0", estrato=("B", "?", "granacao"), classe="Rust")
    assert pa["prior"]["media"] < pa["media_geral"] < pb["prior"]["media"]
    assert pa["prior"]["forca"] <= fed.FORCA_MAXIMA + 1e-9
    novo = fed.prior_para(cs, destino="talhao-novo", estrato=("D", "?", "granacao"),
                        classe="Rust")  # estrato sem dado: a média geral, encolhida
    assert novo["plantas_do_estrato"] == 0
    assert novo["prior"]["media"] == pytest.approx(novo["media_geral"], abs=1e-6)


def test_avaliacao_antes_de_distribuir() -> None:
    cs = _contagens({"A": 0.05, "B": 0.15, "C": 0.10})
    fraco = fed.avaliar(cs, classe="Rust", referencia=fed.Beta(1, 1))
    assert fraco["distribuir"] and fraco["ganho_medio_log"] > 0
    # contra um prior de referência que já é a verdade, forte: compartilhar não ajuda
    iguais = _contagens({"A": 0.1, "B": 0.1, "C": 0.1}, semente=3)
    forte = fed.avaliar(iguais, classe="Rust", referencia=fed.Beta(1000, 9000))
    assert not forte["distribuir"] and "pior" in forte["motivo"]


def test_bytes_da_carga_medidos() -> None:
    """Um talhão/Rover num dia: 3 estratos x 3 classes = 9 contagens."""
    cs = [fed.Contagem("t1", (e, "latossolo", "granacao"), k, frozenset({f"{e}{k}{i}" for i in
                                                                          range(50)}),
                     frozenset(), INI, FIM, P) for e in ("catuai", "mundo novo", "bourbon")
          for k in CLASSES]
    medida = fed.tamanho(fed.carga(cs))
    assert 0 < medida["gzip_bytes"] <= medida["json_bytes"] < 1024  # menos de 1 kB


# -- pela API, com o banco ---------------------------------------------------------------------


def _conferidos(session, tenant_id, farm_id, campo: Field, n: int, taxa: float, semente: int,
                versao: str = "cabeca-1") -> None:
    rng = random.Random(semente)
    for i in range(n):
        obs = Observation(tenant_id=tenant_id, farm_id=farm_id, field_id=campo.id,
                          plant_ref=f"P{i}", captured_at=utcnow() - timedelta(days=3),
                          lat=-21.9, lon=-45.8)
        session.add(obs)
        session.flush()
        det = Detection(tenant_id=tenant_id, observation_id=obs.id,
                        source=DetectionSource.CLOUD_PRIMARY, analyzer="teste", label="Rust",
                        model_key="coffee", model_version=versao, confidence=0.6,
                        probabilities=dict.fromkeys(CLASSES, 1 / 3))
        session.add(det)
        session.flush()
        doente = rng.random() < taxa
        session.add(Diagnosis(
            tenant_id=tenant_id, observation_id=obs.id, field_id=campo.id,
            status=DiagnosisStatus.HUMAN_CONFIRMED if doente else DiagnosisStatus.HUMAN_REJECTED,
            agreement=Agreement.AGREE, label="Rust", confidence=0.6, pipeline_version="teste",
            primary_detection_id=det.id, reviewed_at=utcnow() - timedelta(days=2),
            reviewed_label="Rust" if doente else "Healthy"))


def test_prior_do_talhao_pela_api(client, agronomist_token, demo, session) -> None:
    base = session.get(Field, demo["field_id"])
    base.variety = "Catuaí"
    outros = []
    for i, variedade in enumerate(("Catuaí", "Mundo Novo", "Mundo Novo")):
        f = Field(tenant_id=demo["tenant_id"], farm_id=demo["farm_id"], name=f"T{i}",
                  crop="coffee", variety=variedade, crop_stage=base.crop_stage,
                  boundary=base.boundary)
        session.add(f)
        outros.append(f)
    session.flush()
    _conferidos(session, demo["tenant_id"], demo["farm_id"], base, 40, 0.05, 1)
    for i, f in enumerate(outros):
        _conferidos(session, demo["tenant_id"], demo["farm_id"], f, 60, 0.05 if i == 0 else
                    0.25, 10 + i)
    _conferidos(session, demo["tenant_id"], demo["farm_id"], outros[0], 10, 0.5, 99,
                versao="cabeca-velha")  # outra cabeça: recusada
    # um outro cliente com muita ferrugem: nunca entra
    intruso = Tenant(name="Outro", slug="outro-federado")
    session.add(intruso)
    session.flush()
    fazenda = Farm(tenant_id=intruso.id, name="Outra", center_lat=-21.9, center_lon=-45.8)
    session.add(fazenda)
    session.flush()
    alheio = Field(tenant_id=intruso.id, farm_id=fazenda.id, name="Alheio", crop="coffee",
                   variety="Catuaí", crop_stage=base.crop_stage, boundary=base.boundary)
    session.add(alheio)
    session.flush()
    _conferidos(session, intruso.id, fazenda.id, alheio, 50, 0.9, 7)
    session.commit()
    r = client.get(f"/v1/fields/{demo['field_id']}/federado/prior", headers=agronomist_token)
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["protocolo"]["cabeca"] == "cabeca-1"
    rust = next(p for p in corpo["priores"] if p["classe"] == "Rust")
    assert rust["plantas_de_outros_talhoes"] == 180 and rust["talhoes"] == 3
    assert rust["plantas_do_estrato"] == 60  # o outro Catuaí; o próprio talhão fica de fora
    assert rust["prior"]["media"] < rust["media_geral"]  # Catuaí tem menos que a média
    assert {x["motivo"] for x in corpo["recusadas"]} == {"modelo ou cabeça diferente"}
    assert corpo["bytes"]["prior_distribuivel"]["json_bytes"] > 0
    assert "não distribuído" in corpo["nota"]
    assert len(session.scalars(select(Diagnosis).where(
        Diagnosis.tenant_id == intruso.id)).all()) == 50  # existe, e não entrou
