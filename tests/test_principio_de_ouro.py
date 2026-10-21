"""Princípio de Ouro (brief 8.4) como **prova**, não como frase.

    O agente raciocina, explica e propõe. O agrônomo responsável valida e autoriza.
    O Safety Engine determinístico verifica as condições de segurança e libera a execução
    somente quando todos os requisitos forem atendidos.

"O agente" aqui é todo código que raciocina ou propõe: o **copiloto** (``valtexa/cerebro/`` e
``api/routers/cerebro.py``), o **planejamento** (``valtexa/planejamento/`` e
``api/routers/planejamento.py``) e o **enxame** (``services/enxame.py`` e
``api/routers/enxame.py``). Três provas, cada uma com uma parte estática (varre o código) e uma
dinâmica (varre as rotas e confere o banco):

1. **O agente não escreve estado autorizado** — missão fora de RASCUNHO, aprovação de
   aplicação (``approved_by``), liberação (``authorized_at``, assinatura, veredito de
   segurança), aplicação, verificação, decisão, diagnóstico conferido, versão/limiar de
   modelo, comando ao Rover. O enxame cria missão, e só em RASCUNHO.
2. **A autorização exige um usuário humano com o papel de agrônomo** — só o papel
   ``agronomist`` tem ``mission:approve_application`` (nenhum papel de plataforma, nem a
   sessão de suporte assistida, nem o Rover); a rota de aprovação exige token de usuário; e o
   Safety Engine **reconfere** o papel do aprovador na hora de liberar.
3. **O Safety Engine é o único caminho de liberação** — no código inteiro, só
   ``mission_manager.authorize`` leva a missão a ``AUTHORIZED``, e só depois de
   ``safety_engine.evaluate_mission`` com veredito favorável; só ``AUTHORIZED`` é despachada
   (assinada); o motor é determinístico (sem IA, sem rede, sem relógio implícito).

Um "fio de disparo" acompanha cada prova: atribuição nova a um campo de autorização, em
qualquer arquivo, ou rota nova num roteador do agente que a varredura não exercite, quebra o
teste — e obriga a revisar o Princípio de Ouro antes de passar.
"""

from __future__ import annotations

import ast
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.routing import APIRoute
from sqlalchemy import select

from tests.test_cerebro_parecer import PLANTA
from tests.test_cerebro_parecer import IADuble as IACerebro
from tests.test_enxame import _gemeo_falso, _ret
from tests.test_planejamento import IADuble as IAPlanejamento
from tests.test_planejamento import frota  # noqa: F401
from valtexa.api.routers import cerebro as rotas_cerebro
from valtexa.api.routers import enxame as rotas_enxame
from valtexa.api.routers import federado as rotas_federado
from valtexa.api.routers import planejamento as rotas_planejamento
from valtexa.main import app
from valtexa.models import (
    Base,
    Membership,
    Mission,
    MissionKind,
    MissionState,
    PlatformRole,
    Role,
    SafetyEvaluation,
    SafetyVerdict,
    Tenant,
    User,
)
from valtexa.security import rbac
from valtexa.services import mission_manager, plant_map, safety_engine

RAIZ = Path(__file__).resolve().parents[1] / "valtexa"

AGENTE: dict[str, list[Path]] = {
    "copiloto": [*sorted((RAIZ / "cerebro").glob("*.py")), RAIZ / "api/routers/cerebro.py"],
    "planejamento": [*sorted((RAIZ / "planejamento").glob("*.py")),
                     RAIZ / "api/routers/planejamento.py"],
    "enxame": [RAIZ / "services/enxame.py", RAIZ / "api/routers/enxame.py"],
    "federado": [RAIZ / "services/federado.py", RAIZ / "api/routers/federado.py"],
}
ROTEADORES_DO_AGENTE = (rotas_cerebro, rotas_planejamento, rotas_enxame, rotas_federado)

PROIBIDOS = {
    "safety_engine", "model_registry", "decision_engine", "comando_rover", "ota", "plans",
    "dataset", "edge_sync", "validacao_campo", "missao_resultado", "coordenacao",
    "collection_ingest", "verification", "signing",
}
"""Quem avalia segurança, aprova modelo, decide aplicação, assina ou manda comando ao Rover.
(``verification`` só é lido pelo enxame através de ``verification.due`` — ver abaixo.)"""

LEITURAS_PERMITIDAS = {("enxame.py", "verification", "due")}
"""Exceções de leitura, explícitas: o enxame lista as verificações vencidas (não as conclui)."""

MISSION_MANAGER_PERMITIDO = {"enxame.py": {"create_mission"}}
"""O único uso de ``mission_manager`` pelo agente: criar missão — que nasce em RASCUNHO
(provado em :func:`test_criar_missao_pelo_enxame_so_cria_rascunho`)."""

CAMPOS_AUTORIZADOS = {
    "state", "status", "approved_by", "approved_at", "authorized_at", "authorized_by",
    "authorized_rate_l_ha", "authorized_quantity_l", "safety_status", "safety_reason",
    "signature", "signing_key_id", "nonce", "command_payload", "command_sequence",
    "expires_at", "dispatched_at", "verified", "conclusion", "reviewed_by", "reviewed_label",
    "threshold", "limiar", "event_threshold", "ai_model", "lifecycle", "mission_id",
}

FUNCOES_DE_LIBERACAO = {
    "authorize", "approve", "dispatch", "resume", "transition", "submit_for_safety",
    "evaluate_mission", "check_mission", "transicionar", "conclude", "_store_command",
    "sign_command", "sign", "evaluate",
}

MODELOS_DO_AGENTE = {"DocumentoConhecimento", "TrechoConhecimento", "Parecer", "RevisaoParecer",
                     "PlanoDeApoio", "RevisaoPlanoDeApoio", "PlanoDoEnxame"}


def _arvore(caminho: Path) -> ast.Module:
    return ast.parse(caminho.read_text(encoding="utf-8"), filename=str(caminho))


def _modulos() -> list[tuple[str, Path]]:
    return [(grupo, c) for grupo, caminhos in AGENTE.items() for c in caminhos]


# =============================================================================================
# 1. O agente não escreve estado autorizado — código
# =============================================================================================


def test_agente_nao_importa_quem_autoriza() -> None:
    achados = []
    for grupo, caminho in _modulos():
        for no in ast.walk(_arvore(caminho)):
            nomes: list[str] = []
            if isinstance(no, ast.Import):
                nomes = [a.name for a in no.names]
            elif isinstance(no, ast.ImportFrom):
                nomes = [no.module or ""] + [f"{no.module}.{a.name}" for a in no.names]
            for nome in nomes:
                proibido = set(nome.split(".")) & PROIBIDOS
                if not proibido:
                    continue
                if any((caminho.name, p) == (arq, mod) for arq, mod, _ in LEITURAS_PERMITIDAS
                       for p in proibido):
                    continue
                achados.append(f"{grupo}/{caminho.name}: import {nome}")
    assert not achados, achados


def test_agente_so_le_o_que_a_excecao_diz() -> None:
    """``verification`` (exceção de leitura) só é usado pela função listada."""
    for _grupo, caminho in _modulos():
        for no in ast.walk(_arvore(caminho)):
            if isinstance(no, ast.Attribute) and isinstance(no.value, ast.Name) and \
                    no.value.id in {m for _, m, _ in LEITURAS_PERMITIDAS}:
                assert (caminho.name, no.value.id, no.attr) in LEITURAS_PERMITIDAS, \
                    f"{caminho.name}: {no.value.id}.{no.attr}"


def test_agente_so_usa_create_mission_do_mission_manager() -> None:
    usados: dict[str, set[str]] = {}
    for _grupo, caminho in _modulos():
        for no in ast.walk(_arvore(caminho)):
            if isinstance(no, ast.Attribute) and isinstance(no.value, ast.Name) and \
                    no.value.id == "mission_manager":
                usados.setdefault(caminho.name, set()).add(no.attr)
    assert usados == MISSION_MANAGER_PERMITIDO


def test_agente_nao_chama_funcao_de_liberacao() -> None:
    achados = []
    for grupo, caminho in _modulos():
        for no in ast.walk(_arvore(caminho)):
            if not isinstance(no, ast.Call):
                continue
            nome = no.func.attr if isinstance(no.func, ast.Attribute) else (
                no.func.id if isinstance(no.func, ast.Name) else None)
            if nome in FUNCOES_DE_LIBERACAO:
                achados.append(f"{grupo}/{caminho.name}:{no.lineno} {nome}(...)")
    assert not achados, achados


def test_agente_nao_atribui_campo_de_autorizacao() -> None:
    achados = []
    for grupo, caminho in _modulos():
        for no in ast.walk(_arvore(caminho)):
            alvos = no.targets if isinstance(no, ast.Assign) else (
                [no.target] if isinstance(no, (ast.AugAssign, ast.AnnAssign)) else [])
            for alvo in alvos:
                for sub in ast.walk(alvo):
                    if isinstance(sub, ast.Attribute) and sub.attr in CAMPOS_AUTORIZADOS:
                        achados.append(f"{grupo}/{caminho.name}:{no.lineno} .{sub.attr} =")
            # setattr(obj, "state", ...) também conta
            if isinstance(no, ast.Call) and isinstance(no.func, ast.Name) and \
                    no.func.id == "setattr" and len(no.args) >= 2 and \
                    isinstance(no.args[1], ast.Constant) and no.args[1].value in \
                    CAMPOS_AUTORIZADOS:
                achados.append(f"{grupo}/{caminho.name}:{no.lineno} setattr {no.args[1].value}")
    assert not achados, achados


def _modelos_importados(arvore: ast.Module) -> dict[str, str]:
    """Nome local → classe do banco, para o que o arquivo importa de ``valtexa.models``
    (``Field`` do pydantic não é ``Field`` do talhão)."""
    modelos = {m.class_.__name__ for m in Base.registry.mappers}
    saida = {}
    for no in ast.walk(arvore):
        if isinstance(no, ast.ImportFrom) and (no.module or "").startswith("valtexa.models"):
            for a in no.names:
                if a.name in modelos:
                    saida[a.asname or a.name] = a.name
    return saida


def test_agente_so_constroi_as_proprias_linhas() -> None:
    achados = []
    for grupo, caminho in _modulos():
        arvore = _arvore(caminho)
        importados = _modelos_importados(arvore)
        for no in ast.walk(arvore):
            if isinstance(no, ast.Call) and isinstance(no.func, ast.Name) and \
                    importados.get(no.func.id, "") not in ("", *MODELOS_DO_AGENTE):
                achados.append(f"{grupo}/{caminho.name}: {importados[no.func.id]}(...)")
    assert not achados, achados


# =============================================================================================
# 1. O agente não escreve estado autorizado — varredura das rotas, com o banco
# =============================================================================================

TABELAS_AUTORIZADAS = ("mission", "safety_evaluation", "application", "verification",
                       "decision", "diagnosis", "model_version", "device_command", "product",
                       "product_batch", "tank", "field", "device", "membership")
"""O que uma rota do agente nunca pode mudar (``mission`` aceita só linha **nova** em
RASCUNHO, pelo enxame — conferido à parte)."""

IGNORAR_COLUNAS = {"updated_at", "last_seen_at", "last_used_at", "health_reported_at"}


def _foto(session) -> dict[str, dict[str, str]]:
    session.expire_all()
    foto: dict[str, dict[str, str]] = {}
    for tabela in Base.metadata.sorted_tables:
        if tabela.name not in TABELAS_AUTORIZADAS:
            continue
        linhas = session.execute(select(tabela)).all()
        foto[tabela.name] = {
            str(linha._mapping["id"]): json.dumps(
                {k: str(v) for k, v in linha._mapping.items() if k not in IGNORAR_COLUNAS},
                sort_keys=True) for linha in linhas}
    return foto


@pytest.fixture
def ias(monkeypatch):
    cer, pla = IACerebro(), IAPlanejamento()
    app.dependency_overrides[rotas_cerebro.fonte_da_ia] = lambda: cer
    app.dependency_overrides[rotas_planejamento.fonte_da_ia] = lambda: pla
    monkeypatch.setattr(plant_map, "prioridades_gemeo", _gemeo_falso([]))
    yield cer, pla
    app.dependency_overrides.pop(rotas_cerebro.fonte_da_ia, None)
    app.dependency_overrides.pop(rotas_planejamento.fonte_da_ia, None)


@pytest.fixture
def pulverizacao_em_rascunho(session, demo, frota):  # noqa: F811
    """Uma missão de aplicação parada em RASCUNHO, com produto e quantidade: se algum caminho
    do agente a aprovasse ou liberasse, a foto do banco acusaria."""
    m = Mission(tenant_id=demo["tenant_id"], farm_id=demo["farm_id"], field_id=demo["field_id"],
                device_id=frota[2].device_id, kind=MissionKind.SPRAY, state=MissionState.DRAFT,
                target_polygon=_ret(0, 0), product_id=demo["product_id"],
                authorized_quantity_l=10.0, authorized_rate_l_ha=100.0)
    session.add(m)
    session.commit()
    return m.id


def _rotas_do_agente() -> set[tuple[str, str]]:
    return {(metodo, r.path) for mod in ROTEADORES_DO_AGENTE for r in mod.router.routes
            if isinstance(r, APIRoute) for metodo in r.methods}


def test_varredura_das_rotas_do_agente_nao_escreve_estado_autorizado(
        client, demo, session, agronomist_token, operator_token, equipe, ias, frota,  # noqa: F811
        pulverizacao_em_rascunho) -> None:
    from tests.helpers import upload_observation
    from valtexa.models import Observation

    r = upload_observation(frota[0], demo["field_id"], label="Rust")
    assert r.status_code in (200, 201), r.text
    obs = session.scalars(select(Observation)).first()
    obs.plant_ref = PLANTA
    session.commit()
    equipe_token = equipe(PlatformRole.IA_DADOS)
    hoje = datetime.now(UTC).date()
    f = demo["field_id"]
    feitas: set[tuple[str, str]] = set()
    antes = _foto(session)
    missoes_antes = set(antes["mission"])

    def chama(metodo: str, modelo: str, url: str, token: dict, corpo=None,
              esperado=(200, 201)) -> dict:
        resposta = client.request(metodo, "/v1" + url, json=corpo, headers=token)
        assert resposta.status_code in esperado, (metodo, url, resposta.text)
        feitas.add((metodo, modelo))
        return resposta.json()

    meta = {"chave": "teste:ouro", "versao": "1", "titulo": "Bula EXEMPLO (fictícia)",
            "tipo": "bula", "origem": "teste", "licenca": "teste", "culturas": ["coffee"],
            "alvos": ["Rust"]}
    verif = {"verificado_em": hoje.isoformat(),
             "valido_ate": (hoje + timedelta(days=30)).isoformat()}
    # copiloto: fontes da plataforma e do cliente, busca, parecer e revisão
    doc = chama("POST", "/platform/cerebro/fontes", "/platform/cerebro/fontes", equipe_token,
                {"metadados": meta, "conteudo": "EXEMPLO, não é bula: alvo ferrugem."})
    chama("POST", "/platform/cerebro/fontes/{documento_id}/verificacao",
          f"/platform/cerebro/fontes/{doc['id']}/verificacao", equipe_token, verif)
    chama("GET", "/platform/cerebro/fontes", "/platform/cerebro/fontes", equipe_token)
    meu = chama("POST", "/cerebro/fontes", "/cerebro/fontes", agronomist_token,
                {"metadados": {**meta, "chave": "teste:ouro-cliente",
                               "tipo": "historico_propriedade", "ficticio": True},
                 "conteudo": "Histórico fictício: ferrugem na rua 22."})
    chama("POST", "/cerebro/fontes/{documento_id}/verificacao",
          f"/cerebro/fontes/{meu['id']}/verificacao", agronomist_token, verif)
    chama("GET", "/cerebro/fontes", "/cerebro/fontes", agronomist_token)
    chama("GET", "/cerebro/fontes/{documento_id}", f"/cerebro/fontes/{meu['id']}",
          agronomist_token)
    chama("GET", "/cerebro/busca", "/cerebro/busca?q=ferrugem", agronomist_token)
    par = chama("POST", "/fields/{field_id}/pareceres", f"/fields/{f}/pareceres",
                agronomist_token, {"caso": "planta", "plant_ref": PLANTA})
    chama("GET", "/fields/{field_id}/pareceres", f"/fields/{f}/pareceres", agronomist_token)
    chama("GET", "/pareceres/{parecer_id}", f"/pareceres/{par['id']}", agronomist_token)
    chama("POST", "/pareceres/{parecer_id}/revisao", f"/pareceres/{par['id']}/revisao",
          agronomist_token, {"decisao": "concorda"})
    chama("GET", "/pareceres/{parecer_id}/auditoria", f"/pareceres/{par['id']}/auditoria",
          agronomist_token)
    # planejamento: os três planos, leitura, trilha e revisão ("aceito" não libera nada)
    fito = chama("POST", "/fields/{field_id}/planejamento/fitossanitario",
                 f"/fields/{f}/planejamento/fitossanitario", agronomist_token, {})
    rob = chama("POST", "/fields/{field_id}/planejamento/robotico",
                f"/fields/{f}/planejamento/robotico", operator_token, {})
    chama("POST", "/planejamento/insumos", "/planejamento/insumos", agronomist_token, {})
    chama("GET", "/planejamento", "/planejamento", agronomist_token)
    chama("GET", "/planejamento/{plano_apoio_id}", f"/planejamento/{rob['id']}",
          agronomist_token)
    chama("GET", "/planejamento/{plano_apoio_id}/auditoria",
          f"/planejamento/{rob['id']}/auditoria", agronomist_token)
    for plano, token in ((fito, agronomist_token), (rob, operator_token)):
        chama("POST", "/planejamento/{plano_apoio_id}/revisao",
              f"/planejamento/{plano['id']}/revisao", token, {"decisao": "aceito"})
    # enxame: plano e a próxima missão de cada robô — em RASCUNHO
    enx = chama("POST", "/fields/{field_id}/enxame/plano", f"/fields/{f}/enxame/plano",
                operator_token, {"doenca": "Rust"})
    chama("GET", "/fields/{field_id}/enxame/plano", f"/fields/{f}/enxame/plano",
          operator_token)
    criadas = chama("POST", "/fields/{field_id}/enxame/plano/{plano_id}/missoes",
                    f"/fields/{f}/enxame/plano/{enx['plano_id']}/missoes", operator_token, {})

    # federado: o prior fundido (só leitura)
    chama("GET", "/fields/{field_id}/federado/prior", f"/fields/{f}/federado/prior",
          agronomist_token)

    # fio de disparo: toda rota dos roteadores do agente foi exercitada
    assert feitas == _rotas_do_agente(), _rotas_do_agente() ^ feitas

    depois = _foto(session)
    for tabela in TABELAS_AUTORIZADAS:
        if tabela == "mission":
            continue
        assert depois[tabela] == antes[tabela], f"a varredura mudou {tabela}"
    # missões que já existiam: idênticas (a pulverização continua em RASCUNHO, sem aprovação)
    for mid in missoes_antes:
        assert depois["mission"][mid] == antes["mission"][mid]
    # as novas: só as do enxame, todas em RASCUNHO, sem aprovação, liberação nem assinatura
    novas = set(depois["mission"]) - missoes_antes
    assert novas == {m["mission_id"] for m in criadas["missoes"] if m["mission_id"]} != set()
    for mid in novas:
        m = session.get(Mission, mid)
        assert m.state is MissionState.DRAFT and m.kind is not MissionKind.SPRAY
        assert (m.approved_by, m.authorized_at, m.safety_status, m.signature) == \
            (None, None, None, None)
    assert session.scalars(select(SafetyEvaluation)).all() == []


def test_criar_missao_pelo_enxame_so_cria_rascunho() -> None:
    """``create_mission`` (o único uso de ``mission_manager`` pelo agente) grava RASCUNHO e não
    toca aprovação nem liberação: lido no código da função."""
    fonte = (RAIZ / "services/mission_manager.py").read_text(encoding="utf-8")
    arvore = ast.parse(fonte)
    funcao = next(n for n in arvore.body
                  if isinstance(n, ast.FunctionDef) and n.name == "create_mission")
    estados = [ast.unparse(k.value) for n in ast.walk(funcao) if isinstance(n, ast.Call)
               for k in n.keywords if k.arg == "state"]
    assert estados == ["MissionState.DRAFT"]
    chamadas = {n.func.attr if isinstance(n.func, ast.Attribute) else getattr(n.func, "id", "")
                for n in ast.walk(funcao) if isinstance(n, ast.Call)}
    assert not chamadas & FUNCOES_DE_LIBERACAO, chamadas & FUNCOES_DE_LIBERACAO
    for n in ast.walk(funcao):
        if isinstance(n, ast.keyword):
            assert n.arg not in {"approved_by", "approved_at", "authorized_at", "signature",
                                 "safety_status"}, n.arg


# =============================================================================================
# 2. A autorização exige um usuário humano com o papel de agrônomo
# =============================================================================================


def test_so_o_papel_de_agronomo_aprova_aplicacao() -> None:
    quem = {papel for papel in Role if rbac.can(papel, rbac.MISSION_APPROVE_APPLICATION)}
    assert quem == {Role.AGRONOMIST}
    assert not any(rbac.platform_can(p, rbac.MISSION_APPROVE_APPLICATION) for p in PlatformRole)
    assert rbac.SUPPORT_ASSISTED_ROLE is not Role.AGRONOMIST
    assert rbac.MISSION_APPROVE_APPLICATION not in rbac.SUPPORT_READ_CAPABILITIES
    # o agente propõe; nenhuma capacidade do agente dá aprovação
    for cap in (rbac.PARECER_GENERATE, rbac.PLANEJAMENTO_GENERATE, rbac.KNOWLEDGE_MANAGE):
        assert cap != rbac.MISSION_APPROVE_APPLICATION


def _usuario(session_factory, client, papel: Role) -> dict[str, str]:
    from tests.conftest import DEMO_PASSWORD
    from tests.test_isolamento_openapi import _login
    from valtexa.security.passwords import hash_password

    email = f"ouro-{papel.value}@valtexa.dev"
    with session_factory() as s:
        tenant = s.scalars(select(Tenant).where(Tenant.slug != "atacante-agro")).first()
        u = User(email=email, full_name=f"Ouro {papel.value}",
                 password_hash=hash_password(DEMO_PASSWORD))
        s.add(u)
        s.flush()
        s.add(Membership(tenant_id=tenant.id, user_id=u.id, role=papel))
        s.commit()
    return _login(client, email)


def test_aprovar_exige_usuario_humano_agronomo(client, session, session_factory, demo,
                                               frota, pulverizacao_em_rascunho) -> None:  # noqa: F811
    url = f"/v1/missions/{pulverizacao_em_rascunho}/approve"
    corpo = {"confirm": True, "notes": "teste"}
    for papel in Role:
        if papel is Role.AGRONOMIST:
            continue
        r = client.post(url, json=corpo, headers=_usuario(session_factory, client, papel))
        assert r.status_code == 403, (papel, r.text)
    # o Rover (token de dispositivo) não alcança a rota de aprovação
    r = frota[0].request("POST", url, json_body=corpo)
    assert r.status_code in (401, 403), r.text
    session.expire_all()
    assert session.get(Mission, pulverizacao_em_rascunho).approved_by is None
    agronomo = _usuario(session_factory, client, Role.AGRONOMIST)
    r = client.post(url, json=corpo, headers=agronomo)
    assert r.status_code == 200, r.text
    session.expire_all()
    m = session.get(Mission, pulverizacao_em_rascunho)
    assert m.approved_by and m.state is MissionState.DRAFT  # aprovar não libera


def _checks(session, mission_id: str) -> dict[str, bool]:
    session.expire_all()
    m = session.get(Mission, mission_id)
    rel = safety_engine.check_mission(session, m, now=datetime.now(UTC))
    return {c.code: c.passed for c in rel.checks}


def test_safety_engine_reconfere_o_papel_do_aprovador(client, session, session_factory, demo,
                                                      frota, pulverizacao_em_rascunho) -> None:  # noqa: F811
    m = session.get(Mission, pulverizacao_em_rascunho)
    assert _checks(session, m.id)[safety_engine.APPROVAL] is False  # sem aprovação humana
    agronomo = _usuario(session_factory, client, Role.AGRONOMIST)
    assert client.post(f"/v1/missions/{m.id}/approve", json={"confirm": True},
                       headers=agronomo).status_code == 200
    assert _checks(session, m.id)[safety_engine.APPROVER_ROLE] is True
    # o papel foi rebaixado depois da aprovação: o Safety Engine bloqueia
    m = session.get(Mission, m.id)
    vinculo = session.scalars(select(Membership).where(
        Membership.user_id == m.approved_by)).one()
    vinculo.role = Role.OPERATOR
    session.commit()
    assert _checks(session, m.id)[safety_engine.APPROVER_ROLE] is False
    # aprovador que não é do cliente: bloqueia
    de_fora = User(email="de-fora@valtexa.dev", full_name="De fora", password_hash="x")
    session.add(de_fora)
    session.flush()
    m = session.get(Mission, m.id)
    m.approved_by = de_fora.id
    session.commit()
    assert _checks(session, m.id)[safety_engine.APPROVER_ROLE] is False


# =============================================================================================
# 3. O Safety Engine determinístico é o único caminho de liberação
# =============================================================================================


class _Atribuicoes(ast.NodeVisitor):
    def __init__(self, attr: str, arquivo: str, achados: set[tuple[str, str]]) -> None:
        self.attr, self.arquivo, self.achados, self.pilha = attr, arquivo, achados, []

    def visit_FunctionDef(self, n):
        self.pilha.append(n.name)
        self.generic_visit(n)
        self.pilha.pop()

    visit_AsyncFunctionDef = visit_FunctionDef  # noqa: N815

    def visit_Assign(self, n):
        for alvo in n.targets:
            for sub in ast.walk(alvo):
                if isinstance(sub, ast.Attribute) and sub.attr == self.attr:
                    self.achados.add((self.arquivo, self.pilha[-1] if self.pilha
                                      else "<módulo>"))
        self.generic_visit(n)


def _atribuicoes(attr: str) -> set[tuple[str, str]]:
    """Todas as atribuições ``X.attr = ...`` do pacote ``valtexa``: (arquivo, função)."""
    achados: set[tuple[str, str]] = set()
    for caminho in RAIZ.rglob("*.py"):
        _Atribuicoes(attr, caminho.relative_to(RAIZ).as_posix(), achados).visit(
            _arvore(caminho))
    return achados


def test_fio_de_disparo_dos_campos_de_liberacao() -> None:
    """Quem pode escrever cada campo de aprovação/liberação, no código inteiro. Um lugar novo
    quebra o teste: revise o Princípio de Ouro antes de acrescentar à lista."""
    assert _atribuicoes("authorized_at") == {("services/mission_manager.py", "authorize")}
    assert _atribuicoes("signature") == {("services/mission_manager.py", "_store_command")}
    assert _atribuicoes("safety_status") == {("services/mission_manager.py", "authorize"),
                                             ("services/mission_manager.py",
                                              "_esquece_parecer")}
    # approved_by: a rota do agrônomo (missão), o registro de modelos (equipe de IA) e o mapa
    # de aplicação novo, que só APAGA a aprovação (o agrônomo aprova o mapa que vê —
    # test_mapa_aplicacao prova que ali ele vira None, nunca um aprovador)
    assert _atribuicoes("approved_by") == {("api/routers/missions.py", "approve"),
                                           ("api/routers/missions.py",
                                            "anexar_mapa_de_aplicacao"),
                                           ("services/model_registry.py", "transicionar")}
    # o estado da missão só muda dentro de transition (as outras são de outras tabelas)
    estado_missao = set()
    for caminho in RAIZ.rglob("*.py"):
        for no in ast.walk(_arvore(caminho)):
            if isinstance(no, ast.Assign) and "MissionState" in ast.dump(no.value) and any(
                    isinstance(s, ast.Attribute) and s.attr == "state"
                    for t in no.targets for s in ast.walk(t)):
                estado_missao.add(caminho.name)
    assert estado_missao == set(), estado_missao


def test_autorizado_so_por_authorize_depois_do_safety_engine() -> None:
    # 1) só PENDING_SAFETY leva a AUTHORIZED; só AUTHORIZED leva a DISPATCHED
    origens = {s for s, alvos in mission_manager.ALLOWED_TRANSITIONS.items()
               if MissionState.AUTHORIZED in alvos}
    assert origens == {MissionState.PENDING_SAFETY}
    para_despacho = {s for s, alvos in mission_manager.ALLOWED_TRANSITIONS.items()
                     if MissionState.DISPATCHED in alvos}
    assert para_despacho == {MissionState.AUTHORIZED}
    # 2) no código inteiro, quem pede transition(..., AUTHORIZED, ...)
    quem: set[tuple[str, str]] = set()
    for caminho in RAIZ.rglob("*.py"):
        arvore = _arvore(caminho)
        for funcao in (n for n in ast.walk(arvore) if isinstance(n, ast.FunctionDef)):
            for no in ast.walk(funcao):
                if isinstance(no, ast.Call) and getattr(no.func, "attr", getattr(
                        no.func, "id", None)) == "transition" and any(
                        "AUTHORIZED" in ast.unparse(a) for a in no.args):
                    quem.add((caminho.name, funcao.name))
    assert quem == {("mission_manager.py", "authorize")}
    # 3) dentro de authorize: avalia, grava o parecer, retorna se BLOQUEADA — e só depois libera
    arvore = ast.parse((RAIZ / "services/mission_manager.py").read_text(encoding="utf-8"))
    autoriza = next(n for n in arvore.body
                    if isinstance(n, ast.FunctionDef) and n.name == "authorize")
    linha_avalia = min(n.lineno for n in ast.walk(autoriza) if isinstance(n, ast.Call)
                       and ast.unparse(n.func) == "safety_engine.evaluate_mission")
    linha_bloqueio = min(n.lineno for n in ast.walk(autoriza) if isinstance(n, ast.If)
                         and "SafetyVerdict.BLOCKED" in ast.unparse(n.test)
                         and any(isinstance(s, ast.Return) for s in ast.walk(n)))
    linha_libera = min(n.lineno for n in ast.walk(autoriza) if isinstance(n, ast.Call)
                       and "MissionState.AUTHORIZED" in ast.unparse(n))
    assert linha_avalia < linha_bloqueio < linha_libera
    # 4) a assinatura (_store_command) só em dispatch e resume, que exigem o estado certo
    chamam = {n.name for n in arvore.body if isinstance(n, ast.FunctionDef)
              and any(isinstance(c, ast.Call) and ast.unparse(c.func) == "_store_command"
                      for c in ast.walk(n))}
    assert chamam == {"dispatch", "resume"}


def test_safety_engine_e_deterministico() -> None:
    """Sem IA, sem rede, sem sorteio: o motor importa só o banco, a tabela de papéis e a
    geometria/relevo/capacidades (e ``datetime`` só como padrão do ``now`` explícito)."""
    arvore = _arvore(RAIZ / "services/safety_engine.py")
    modulos = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.ImportFrom):
            modulos.add(no.module)
            modulos |= {f"{no.module}.{a.name}" for a in no.names}
        elif isinstance(no, ast.Import):
            modulos |= {a.name for a in no.names}
    proibidos = {"random", "requests", "httpx", "urllib", "socket", "valtexa.cerebro",
                 "valtexa.planejamento", "valtexa.services.plant_map",
                 "valtexa.services.enxame", "valtexa.services.ai_pipeline", "time"}
    assert not {m for m in modulos for p in proibidos if m == p or m.startswith(p + ".")}


def test_liberacao_bloqueada_nao_assina_e_nao_despacha(client, session, session_factory,
                                                       admin_token, demo, frota,  # noqa: F811
                                                       pulverizacao_em_rascunho) -> None:
    agronomo = _usuario(session_factory, client, Role.AGRONOMIST)
    mid = pulverizacao_em_rascunho
    assert client.post(f"/v1/missions/{mid}/approve", json={"confirm": True},
                       headers=agronomo).status_code == 200
    # aprovada pelo agrônomo, mas sem tanque carregado, sem lote etc.: o Safety Engine bloqueia
    r = client.post(f"/v1/missions/{mid}/authorize", headers=admin_token)
    assert r.status_code == 200 and r.json()["verdict"] == SafetyVerdict.BLOCKED.value
    session.expire_all()
    m = session.get(Mission, mid)
    assert m.state is MissionState.BLOCKED and m.signature is None and m.authorized_at is None
    assert client.post(f"/v1/missions/{mid}/dispatch", headers=admin_token).status_code == 409
    # o mesmo pedido, o mesmo veredito (determinístico, com o mesmo instante)
    agora = datetime.now(UTC)
    a = safety_engine.check_mission(session, m, now=agora)
    b = safety_engine.check_mission(session, m, now=agora)
    assert a == b and a.verdict is SafetyVerdict.BLOCKED


def test_missao_de_inspecao_do_enxame_so_sai_pela_camada_de_seguranca(
        client, session, operator_token, admin_token, demo, frota, ias) -> None:  # noqa: F811
    """O caminho inteiro de uma proposta do agente até o Rover: rascunho (enxame) →
    ``authorize`` (Safety Engine grava o parecer) → ``dispatch`` (assinatura)."""
    f = demo["field_id"]
    plano = client.post(f"/v1/fields/{f}/enxame/plano", json={}, headers=operator_token).json()
    r = client.post(f"/v1/fields/{f}/enxame/plano/{plano['plano_id']}/missoes", json={},
                    headers=operator_token).json()
    mid = next(m["mission_id"] for m in r["missoes"] if m["mission_id"])
    session.expire_all()
    assert session.get(Mission, mid).state is MissionState.DRAFT
    assert client.post(f"/v1/missions/{mid}/dispatch", headers=admin_token).status_code == 409
    assert client.post(f"/v1/missions/{mid}/authorize", headers=admin_token).status_code == 200
    session.expire_all()
    avaliacoes = session.scalars(select(SafetyEvaluation).where(
        SafetyEvaluation.subject_id == mid)).all()
    assert len(avaliacoes) == 1 and avaliacoes[0].engine_version == safety_engine.ENGINE_VERSION
    m = session.get(Mission, mid)
    assert m.state is MissionState.AUTHORIZED and m.safety_status is \
        SafetyVerdict.SAFE_TO_EXECUTE and m.signature is None  # libera; assina no despacho
    assert client.post(f"/v1/missions/{mid}/dispatch", headers=admin_token).status_code == 200
    session.expire_all()
    assert session.get(Mission, mid).signature

