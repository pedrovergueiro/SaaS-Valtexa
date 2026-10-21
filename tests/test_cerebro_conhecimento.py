"""Repositório de conhecimento versionado e recuperação local (8.1).

Todos os documentos daqui são **FICTÍCIOS** (``ficticio=True``, texto que não é de bula
nenhuma, registro e dose inexistentes) — o teste prova o mecanismo, não o conteúdo. Onde o
teste precisa de um regulatório "válido", ele é marcado fictício=False só dentro do banco do
teste e o texto diz que é exemplo.
"""

from __future__ import annotations

import json
from datetime import date

import pytest
from sqlalchemy import select

from valtexa.cerebro import conhecimento, rag
from valtexa.models import AuditEntry, Tenant
from valtexa.models.cerebro import DocumentoConhecimento, TrechoConhecimento

HOJE = date(2026, 10, 19)


def meta(**extra) -> dict:
    base = {"chave": "teste:ferrugem", "versao": "1", "titulo": "Ferrugem — texto de teste",
            "tipo": "embrapa", "origem": "FICTÍCIO — gerado no teste", "licenca": "teste",
            "culturas": ["coffee"], "alvos": ["Rust"], "ficticio": True}
    return {**base, **extra}


TEXTO = """# Sintomas

Texto FICTÍCIO de teste. Manchas amarelo-alaranjadas na face inferior das folhas indicam a
ferrugem do cafeeiro neste exemplo inventado.

# Condições

Exemplo inventado: molhamento foliar prolongado e temperatura amena favorecem a doença.
"""


def _tenant(session, slug="cliente-a") -> str:
    t = Tenant(name=slug, slug=slug)
    session.add(t)
    session.flush()
    return t.id


def test_ingestao_guarda_versao_hash_trechos_e_audita(session) -> None:
    doc, criado = conhecimento.ingerir(session, tenant_id=None, metadados=meta(),
                                       conteudo=TEXTO, formato="markdown")
    session.commit()
    assert criado and doc.sha256 == conhecimento.sha256_texto(TEXTO)
    trechos = session.scalars(select(TrechoConhecimento).where(
        TrechoConhecimento.documento_id == doc.id).order_by(TrechoConhecimento.ordem)).all()
    assert [t.secao for t in trechos] == ["Sintomas", "Condições"]
    for t in trechos:  # a citação aponta para o conteúdo, byte a byte
        assert TEXTO[t.inicio:t.fim] == t.texto
        assert t.sha256 == conhecimento.sha256_texto(t.texto)
    trilha = session.scalars(select(AuditEntry).where(AuditEntry.action == "fonte.ingerida")).one()
    assert trilha.payload["sha256"] == doc.sha256
    # reenviar o mesmo é idempotente; a mesma versão com outro texto é recusada
    de_novo, criado = conhecimento.ingerir(session, tenant_id=None, metadados=meta(),
                                           conteudo=TEXTO, formato="markdown")
    assert not criado and de_novo.id == doc.id
    with pytest.raises(conhecimento.DocumentoInvalidoError, match="imutável"):
        conhecimento.ingerir(session, tenant_id=None, metadados=meta(), conteudo=TEXTO + "x")


def test_versao_nova_substitui_a_anterior_que_fica(session) -> None:
    v1, _ = conhecimento.ingerir(session, tenant_id=None, metadados=meta(), conteudo=TEXTO)
    v2, _ = conhecimento.ingerir(session, tenant_id=None, metadados=meta(versao="2"),
                                 conteudo=TEXTO + "\nRevisado (fictício).")
    session.commit()
    session.refresh(v1)
    assert (v1.estado, v1.substituido_por, v2.estado) == ("substituido", v2.id, "vigente")
    assert not conhecimento.situacao(v1, HOJE).uso_operacional
    achados = rag.buscar(session, None, "ferrugem folhas", rag.Filtros(cultura="coffee"),
                         hoje=HOJE)
    assert {a["documento_id"] for a in achados} == {v2.id}


@pytest.mark.parametrize("faltando", conhecimento.OBRIGATORIOS)
def test_metadado_obrigatorio_faltando_e_recusado(session, faltando) -> None:
    m = meta()
    m.pop(faltando)
    with pytest.raises(conhecimento.DocumentoInvalidoError, match=faltando):
        conhecimento.ingerir(session, tenant_id=None, metadados=m, conteudo=TEXTO)


def test_metadado_desconhecido_tipo_e_datas_erradas_sao_recusados(session) -> None:
    for errado, padrao in (({"dose": "1 L/ha"}, "desconhecidos"), ({"tipo": "blog"}, "tipo"),
                           ({"valido_ate": "ontem"}, "data"),
                           ({"verificado_em": "2026-10-01", "valido_ate": "2026-01-01"},
                            "antes")):
        with pytest.raises(conhecimento.DocumentoInvalidoError, match=padrao):
            conhecimento.ingerir(session, tenant_id=None, metadados=meta(**errado),
                                 conteudo=TEXTO)


def test_ficticio_nao_entra_em_producao(session) -> None:
    with pytest.raises(conhecimento.DocumentoInvalidoError, match="fictício"):
        conhecimento.ingerir(session, tenant_id=None, metadados=meta(), conteudo=TEXTO,
                             producao=True)


def _regulatorio(session, **extra):
    m = meta(chave="teste:bula-x", tipo="bula", titulo="Bula de exemplo (FICTÍCIA)",
             ficticio=False, **extra)
    doc, _ = conhecimento.ingerir(session, tenant_id=None, metadados=m,
                                  conteudo="EXEMPLO — não é bula real. Alvo: ferrugem.")
    return doc


@pytest.mark.parametrize(("extra", "motivo"), [
    ({}, "não verificado"),
    ({"verificado_em": "2026-01-10"}, "sem validade"),
    ({"verificado_em": "2026-01-10", "valido_ate": "2026-06-30"}, "vencido em 2026-06-30"),
    ({"verificado_em": "2026-12-01", "valido_ate": "2027-06-30"}, "futuro"),
])
def test_regulatorio_vencido_ou_nao_verificado_bloqueia(session, extra, motivo) -> None:
    s = conhecimento.situacao(_regulatorio(session, **extra), HOJE)
    assert s.regulatorio and not s.uso_operacional and motivo in s.motivo


def test_regulatorio_verificado_e_vigente_libera_e_ficticio_nunca(session) -> None:
    doc = _regulatorio(session, verificado_em="2026-10-01", valido_ate="2027-10-01")
    assert conhecimento.situacao(doc, HOJE).uso_operacional
    doc.ficticio = True
    assert not conhecimento.situacao(doc, HOJE).uso_operacional
    # fonte técnica nunca é base operacional, mas não é "bloqueio"
    tecnico, _ = conhecimento.ingerir(session, tenant_id=None, metadados=meta(ficticio=False),
                                      conteudo=TEXTO)
    s = conhecimento.situacao(tecnico, HOJE)
    assert (s.regulatorio, s.uso_operacional, s.motivo) == (False, False, None)


def test_verificar_atualiza_datas_sem_mudar_conteudo_e_audita(session) -> None:
    doc = _regulatorio(session)
    digest = doc.sha256
    conhecimento.verificar(session, doc, verificado_em=date(2026, 10, 18),
                           valido_ate=date(2027, 4, 18), ator_id=None)
    assert doc.sha256 == digest and conhecimento.situacao(doc, HOJE).uso_operacional
    assert session.scalars(select(AuditEntry).where(
        AuditEntry.action == "fonte.verificada")).one()


def test_busca_bm25_filtra_cultura_alvo_tipo_e_cliente(session) -> None:
    a, b = _tenant(session, "a"), _tenant(session, "b")
    conhecimento.ingerir(session, tenant_id=None, metadados=meta(), conteudo=TEXTO,
                         formato="markdown")
    conhecimento.ingerir(session, tenant_id=None, metadados=meta(
        chave="teste:milho", culturas=["corn"], alvos=["Common_Rust"]),
        conteudo="Ferrugem do milho, texto fictício de teste.")
    conhecimento.ingerir(session, tenant_id=a, metadados=meta(
        chave="historico:talhao-4", tipo="historico_propriedade", alvos=["ferrugem"]),
        conteudo="Histórico fictício do cliente A: ferrugem na safra passada, rua 22.")
    conhecimento.ingerir(session, tenant_id=b, metadados=meta(
        chave="historico:segredo-b", tipo="historico_propriedade"),
        conteudo="Histórico fictício do cliente B: ferrugem, segredo do B.")
    session.commit()
    filtros = rag.Filtros(cultura="coffee", alvos=("Rust",))
    de_a = rag.buscar(session, a, "ferrugem folha molhamento", filtros, hoje=HOJE, limite=10)
    chaves = {x["chave"] for x in de_a}
    assert chaves == {"teste:ferrugem", "historico:talhao-4"}  # nem milho, nem o do B
    assert "segredo" not in json.dumps(de_a)
    # o mais relevante para "molhamento" é o trecho das condições
    topo = rag.buscar(session, a, "molhamento temperatura", filtros, hoje=HOJE, limite=1)[0]
    assert topo["secao"] == "Condições" and topo["escore"] > 0
    so_hist = rag.buscar(session, a, "ferrugem", rag.Filtros(
        cultura="coffee", tipos=("historico_propriedade",)), hoje=HOJE)
    assert {x["chave"] for x in so_hist} == {"historico:talhao-4"}
    # determinístico e conferível
    assert de_a == rag.buscar(session, a, "ferrugem folha molhamento", filtros, hoje=HOJE,
                              limite=10)
    assert all(rag.confere_citacao(session, c) for c in de_a)


def test_citacao_adulterada_nao_confere(session) -> None:
    doc, _ = conhecimento.ingerir(session, tenant_id=None, metadados=meta(), conteudo=TEXTO)
    session.commit()
    c = rag.buscar(session, None, "ferrugem", rag.Filtros(), hoje=HOJE)[0]
    assert rag.confere_citacao(session, c)
    doc.conteudo = TEXTO.replace("amena", "alta")
    session.commit()
    assert not rag.confere_citacao(session, c)
    assert not rag.confere_citacao(session, {**c, "trecho_id": "outro"})


def test_repositorio_vazio_nao_inventa(session) -> None:
    assert session.scalars(select(DocumentoConhecimento)).all() == []
    assert rag.buscar(session, None, "ferrugem dose bula", rag.Filtros(cultura="coffee"),
                      hoje=HOJE) == []


def test_ingestao_por_arquivo(tmp_path) -> None:
    arquivo = tmp_path / "ferrugem.md"
    arquivo.write_text(TEXTO, encoding="utf-8")
    (tmp_path / "ferrugem.meta.json").write_text(json.dumps(meta()), encoding="utf-8")
    m, conteudo, formato = conhecimento.ler_arquivo(arquivo)
    assert (m["chave"], conteudo, formato) == ("teste:ferrugem", TEXTO, "markdown")
    with pytest.raises(conhecimento.DocumentoInvalidoError, match="metadados"):
        sem_meta = tmp_path / "x.txt"
        sem_meta.write_text("oi", encoding="utf-8")
        conhecimento.ler_arquivo(sem_meta)
    with pytest.raises(conhecimento.DocumentoInvalidoError, match=r"\.md ou \.txt"):
        conhecimento.ler_arquivo(tmp_path / "bula.pdf")


def test_tokens_sem_acento_e_plural() -> None:
    assert rag.tokens("Folhas com MANCHAS amarelo-alaranjadas") == [
        "folha", "mancha", "amarelo", "alaranjada"]


def test_ingestao_pela_linha_de_comando(session_factory, tmp_path, capsys) -> None:
    from valtexa.cerebro import ingestao

    arquivo = tmp_path / "bula.md"
    arquivo.write_text("EXEMPLO fictício, não é bula.", encoding="utf-8")
    (tmp_path / "bula.meta.json").write_text(json.dumps(meta(
        chave="teste:bula-cli", tipo="bula")), encoding="utf-8")
    ruim = tmp_path / "ruim.txt"
    ruim.write_text("x", encoding="utf-8")
    (tmp_path / "ruim.meta.json").write_text(json.dumps({"chave": "x"}), encoding="utf-8")
    assert ingestao.main([str(arquivo)], fabrica=session_factory) == 0
    assert ingestao.main([str(arquivo), str(ruim)], fabrica=session_factory) == 1
    saida = capsys.readouterr()
    assert "ingerido" in saida.out and "já existia" in saida.out
    assert "bloqueado para uso operacional" in saida.out and "recusado" in saida.err
    with session_factory() as s:
        docs = s.scalars(select(DocumentoConhecimento)).all()
        assert [(d.chave, d.tenant_id, d.arquivo_nome) for d in docs] == [
            ("teste:bula-cli", None, "bula.md")]
