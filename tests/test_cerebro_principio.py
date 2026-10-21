"""Princípio de Ouro (8.4) no cérebro agronômico: o agente raciocina, explica e propõe.

Prova por três lados que nenhum caminho do cérebro (módulos ``valtexa/cerebro`` e as rotas de
``api/routers/cerebro.py``) cria missão fora de RASCUNHO, aprova prescrição ou aplicação, muda
limiar de modelo nem chama o Safety Engine:

1. **código** — os módulos não importam nem chamam quem escreve estado autorizado
   (``mission_manager``, ``safety_engine``, ``plans``, ``decision_engine``, ``model_registry``,
   ``enxame``, ``comando_rover``, ``ota``...) e só constroem as linhas dele;
2. **rotas** — todas as rotas do roteador são de fonte, busca e parecer; nenhuma toca missão,
   aplicação, prescrição, modelo ou dispositivo;
3. **banco** — gerar e revisar parecer (com um provedor dublê ligado) só muda as tabelas do
   cérebro e a auditoria: o resto do banco do cliente fica idêntico, linha por linha.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

from fastapi.routing import APIRoute
from sqlalchemy import select

from tests.test_cerebro_parecer import PLANTA, caso, ia, liga_provedor  # noqa: F401
from valtexa.api.routers import cerebro as rotas
from valtexa.models import Base, Mission, SafetyEvaluation

RAIZ = Path(__file__).resolve().parents[1] / "valtexa"
MODULOS = [*sorted((RAIZ / "cerebro").glob("*.py")), RAIZ / "api" / "routers" / "cerebro.py"]

PROIBIDOS = {
    "mission_manager", "safety_engine", "plans", "decision_engine", "model_registry",
    "enxame", "comando_rover", "ota", "mission_resultado", "missao_resultado", "planner",
    "coordenacao", "validacao_campo", "edge_sync", "dataset", "hal",
}
"""Serviços que criam/alteram missão, prescrição, aplicação, modelo ou comando do robô."""

CONSTRUIDOS_PERMITIDOS = {"DocumentoConhecimento", "TrechoConhecimento", "Parecer",
                          "RevisaoParecer"}
"""Os únicos modelos do banco que o cérebro instancia (a auditoria vai por ``audit.record``)."""

TABELAS_DO_CEREBRO = {"documento_conhecimento", "trecho_conhecimento", "parecer",
                      "revisao_parecer", "audit_entry"}


def _arvore(caminho: Path) -> ast.Module:
    return ast.parse(caminho.read_text(encoding="utf-8"), filename=str(caminho))


def test_modulos_do_cerebro_nao_importam_quem_autoriza() -> None:
    achados = []
    for caminho in MODULOS:
        for no in ast.walk(_arvore(caminho)):
            nomes: list[str] = []
            if isinstance(no, ast.Import):
                nomes = [a.name for a in no.names]
            elif isinstance(no, ast.ImportFrom):
                nomes = [no.module or ""] + [f"{no.module}.{a.name}" for a in no.names]
            for nome in nomes:
                if set(nome.split(".")) & PROIBIDOS:
                    achados.append(f"{caminho.name}: import {nome}")
    assert not achados, achados


def test_cerebro_so_constroi_as_proprias_linhas() -> None:
    """Toda chamada ``Classe(...)`` com nome em maiúscula é das tabelas do cérebro ou estrutura
    de dados dele. Um ``Mission(...)``, ``Decision(...)`` ou ``SafetyEvaluation(...)`` aqui
    quebraria o Princípio de Ouro."""
    modelos = {m.class_.__name__ for m in Base.registry.mappers}
    achados = []
    for caminho in MODULOS:
        for no in ast.walk(_arvore(caminho)):
            if isinstance(no, ast.Call) and isinstance(no.func, ast.Name) and \
                    no.func.id[:1].isupper():
                nome = no.func.id
                if nome in modelos and nome not in CONSTRUIDOS_PERMITIDOS:
                    achados.append(f"{caminho.name}: {nome}(...)")
    assert not achados, achados


def test_cerebro_nao_atribui_em_estado_autorizado() -> None:
    """Nenhuma atribuição de ``status``/``state``/``approved_*``/limiar em objeto nenhum."""
    perigosos = {"status", "state", "approved_by", "approved_at", "authorized_by",
                 "threshold", "limiar", "event_threshold", "lifecycle", "mission_id"}
    achados = []
    for caminho in MODULOS:
        for no in ast.walk(_arvore(caminho)):
            alvos = no.targets if isinstance(no, ast.Assign) else (
                [no.target] if isinstance(no, (ast.AugAssign, ast.AnnAssign)) else [])
            for alvo in alvos:
                for sub in ast.walk(alvo):
                    if isinstance(sub, ast.Attribute) and sub.attr in perigosos:
                        achados.append(f"{caminho.name}:{no.lineno} .{sub.attr} =")
    assert not achados, achados


def test_rotas_do_cerebro_sao_so_de_fonte_busca_e_parecer() -> None:
    caminhos = [(sorted(r.methods), r.path) for r in rotas.router.routes
                if isinstance(r, APIRoute)]
    assert caminhos
    for _metodos, caminho in caminhos:
        assert caminho.startswith(("/cerebro/", "/platform/cerebro/", "/pareceres/")) or (
            caminho.startswith("/fields/{field_id}/pareceres")), caminho
        for proibido in ("mission", "missao", "application", "aplicacao", "prescri", "device",
                         "model", "safety", "approve", "aprova", "threshold", "limiar"):
            assert proibido not in caminho.lower(), caminho


def _foto(session, tenant_id: str) -> dict[str, list[str]]:
    session.expire_all()
    foto = {}
    for tabela in Base.metadata.sorted_tables:
        if tabela.name in TABELAS_DO_CEREBRO or "tenant_id" not in tabela.c:
            continue
        linhas = session.execute(select(tabela).where(tabela.c.tenant_id == tenant_id)).all()
        foto[tabela.name] = sorted(json.dumps(
            {k: str(v) for k, v in linha._mapping.items()
             if k not in ("updated_at", "last_seen_at", "last_used_at")}, sort_keys=True)
            for linha in linhas)
    return foto


def test_gerar_e_revisar_so_mudam_as_tabelas_do_cerebro(
        client, agronomist_token, caso, ia, liga_provedor, session, demo) -> None:  # noqa: F811
    def redige(pedido):  # um provedor "ambicioso" que pede para aplicar — é recusado
        return [{"texto": "Aplicar fungicida agora e liberar a missão.",
                 "citacoes": [pedido.dossie["itens"][0]["id"]]}]

    liga_provedor(redige)
    missoes = session.scalars(select(Mission)).all()
    estados = {m.id: m.state for m in missoes}
    antes = _foto(session, demo["tenant_id"])
    r = client.post(f"/v1/fields/{caso['field_id']}/pareceres",
                    json={"caso": "planta", "plant_ref": PLANTA}, headers=agronomist_token)
    assert r.status_code == 201 and r.json()["modo"] == "deterministico"
    assert "recomendacao_operacional" in json.dumps(r.json()["recusas"])
    pid = r.json()["id"]
    for decisao in ("concorda", "inconclusivo"):
        assert client.post(f"/v1/pareceres/{pid}/revisao", json={"decisao": decisao},
                           headers=agronomist_token).status_code == 201
    assert _foto(session, demo["tenant_id"]) == antes
    assert session.scalars(select(SafetyEvaluation)).all() == []
    assert {m.id: m.state for m in session.scalars(select(Mission)).all()} == estados
