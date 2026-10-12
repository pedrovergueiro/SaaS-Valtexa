"""Fazenda completa (brief, seção 5): produtor, CPF/CNPJ, município, UF, cultura, CAR,
responsável técnico e observações — no cadastro, na edição, na resposta e na auditoria."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from valtexa.models import AuditEntry
from valtexa.services import documentos

CPF = "529.982.247-25"
CNPJ = "11.222.333/0001-81"
CAR = "mt-5107925-0123.4567.89ab.cdef.0123.4567.89ab.cdef"


class TestDocumentos:
    def test_cpf_e_cnpj_validos_viram_so_digitos(self) -> None:
        assert documentos.normalizar_cpf_cnpj(CPF) == "52998224725"
        assert documentos.normalizar_cpf_cnpj(CNPJ) == "11222333000181"

    @pytest.mark.parametrize(
        "valor", ["529.982.247-26", "111.111.111-11", "11.222.333/0001-80", "1234", ""]
    )
    def test_documento_errado_e_recusado(self, valor: str) -> None:
        with pytest.raises(documentos.DocumentoInvalidoError):
            documentos.normalizar_cpf_cnpj(valor)

    def test_car_normalizado(self) -> None:
        assert documentos.normalizar_car(CAR) == "MT-5107925-0123456789ABCDEF0123456789ABCDEF"

    @pytest.mark.parametrize(
        "valor",
        [
            "XX-5107925-0123456789ABCDEF0123456789ABCDEF",
            "MT-510792-0123456789ABCDEF0123456789ABCDEF",
            "MT-5107925-0123456789ABCDEF",
        ],
    )
    def test_car_fora_do_formato(self, valor: str) -> None:
        with pytest.raises(documentos.DocumentoInvalidoError):
            documentos.normalizar_car(valor)


def _cria(client: TestClient, headers: dict, **extra) -> dict:
    corpo = {"name": "Fazenda Boa Vista", "center_lat": -12.54, "center_lon": -55.72, **extra}
    resposta = client.post("/v1/farms", json=corpo, headers=headers)
    assert resposta.status_code == 201, resposta.text
    return resposta.json()


class TestCadastro:
    def test_cadastro_com_os_campos_novos(self, client: TestClient, admin_token: dict) -> None:
        fazenda = _cria(
            client,
            admin_token,
            owner_name="Maria Souza",
            owner_document=CPF,
            city="Sorriso",
            state="mt",
            main_crop="soja",
            car_code=CAR,
            technical_lead="Eng. Agr. João Lima — CREA-MT 12345",
            notes="Pivô central no talhão 3.",
        )
        assert fazenda["owner_name"] == "Maria Souza"
        assert fazenda["owner_document"] == "52998224725"
        assert fazenda["state"] == "MT"
        assert fazenda["car_code"] == "MT-5107925-0123456789ABCDEF0123456789ABCDEF"
        assert fazenda["technical_lead"].startswith("Eng. Agr.")
        todas = client.get("/v1/farms", headers=admin_token).json()
        listada = next(f for f in todas if f["id"] == fazenda["id"])
        assert listada["main_crop"] == "soja"
        assert listada["notes"] == "Pivô central no talhão 3."

    def test_fazenda_sem_os_campos_continua_valida(
        self, client: TestClient, admin_token: dict
    ) -> None:
        fazenda = _cria(client, admin_token)
        assert fazenda["owner_document"] is None
        assert fazenda["car_code"] is None

    @pytest.mark.parametrize(
        ("campo", "valor"),
        [("owner_document", "529.982.247-26"), ("car_code", "123"), ("state", "ZZ")],
    )
    def test_documento_invalido_e_422_com_mensagem(
        self, client: TestClient, admin_token: dict, campo: str, valor: str
    ) -> None:
        resposta = client.post(
            "/v1/farms",
            json={"name": "X", "center_lat": -12.5, "center_lon": -55.7, campo: valor},
            headers=admin_token,
        )
        assert resposta.status_code == 422
        assert any(campo in str(erro["loc"]) for erro in resposta.json()["detail"])


class TestEdicao:
    def test_edita_e_audita_antes_e_depois(
        self, client: TestClient, admin_token: dict, session: Session
    ) -> None:
        fazenda = _cria(client, admin_token, owner_document=CPF)
        resposta = client.patch(
            f"/v1/farms/{fazenda['id']}",
            json={"owner_document": CNPJ, "technical_lead": "Ana — CREA-MT 999"},
            headers=admin_token,
        )
        assert resposta.status_code == 200, resposta.text
        assert resposta.json()["owner_document"] == "11222333000181"

        trilha = session.scalars(
            select(AuditEntry).where(
                AuditEntry.subject_id == fazenda["id"], AuditEntry.action == "farm.updated"
            )
        ).all()
        assert len(trilha) == 1
        # A trilha não se apaga: guarda só o fim do documento (o inteiro vive na fazenda).
        assert trilha[0].payload["antes"]["owner_document"] == "***.***.***-25"
        assert trilha[0].payload["depois"]["owner_document"] == "**.***.***/****-81"

    def test_texto_vazio_apaga_o_campo(self, client: TestClient, admin_token: dict) -> None:
        fazenda = _cria(client, admin_token, car_code=CAR)
        resposta = client.patch(
            f"/v1/farms/{fazenda['id']}", json={"car_code": "  "}, headers=admin_token
        )
        assert resposta.status_code == 200, resposta.text
        assert resposta.json()["car_code"] is None

    def test_quem_nao_gerencia_fazenda_nao_edita(
        self, client: TestClient, admin_token: dict, operator_token: dict
    ) -> None:
        fazenda = _cria(client, admin_token)
        resposta = client.patch(
            f"/v1/farms/{fazenda['id']}", json={"owner_name": "Outro"}, headers=operator_token
        )
        assert resposta.status_code == 403


def test_migracao_0015_ida_e_volta(tmp_path) -> None:
    """Sobe até a 0015, confere as colunas, desce para a 0014 e elas saem."""
    from alembic import command
    from sqlalchemy import create_engine, inspect

    from valtexa import db

    url = f"sqlite:///{tmp_path / 'm.db'}"
    cfg = db.alembic_config(url)
    command.upgrade(cfg, "0015")
    colunas = {c["name"] for c in inspect(create_engine(url)).get_columns("farm")}
    assert {"owner_name", "owner_document", "car_code", "technical_lead", "notes"} <= colunas
    command.downgrade(cfg, "0014")
    colunas = {c["name"] for c in inspect(create_engine(url)).get_columns("farm")}
    assert "car_code" not in colunas and "owner_name" not in colunas


def test_ferramenta_interna_nao_ve_o_cpf(
    client: TestClient, admin_token: dict, equipe, demo: dict
) -> None:
    """``/v1/admin/farms`` (importar coleta, planejar) mostra o cadastro sem o CPF/CNPJ."""
    from valtexa.models import PlatformRole

    client.patch(
        f"/v1/farms/{demo['farm_id']}",
        json={"owner_document": CPF, "owner_name": "Maria"},
        headers=admin_token,
    )
    ia = {**equipe(PlatformRole.IA_DADOS), "X-Tenant-Id": demo["tenant_id"]}
    fazenda = client.get("/v1/admin/farms", headers=ia).json()[0]
    assert fazenda["owner_name"] == "Maria"
    assert fazenda["owner_document"] is None


class TestDocumentoMascarado:
    """Decisão do Pedro (Parte 3): CPF/CNPJ inteiro só para quem tem ``farm:manage``.

    O mascaramento é na API — o operador nunca recebe o número, nem que a tela
    queira mostrá-lo. Toda leitura do completo pela equipe da ValTexa fica na trilha.
    """

    def test_mascara(self) -> None:
        assert documentos.mascarar_cpf_cnpj("52998224725") == "***.***.***-25"
        assert documentos.mascarar_cpf_cnpj("11222333000181") == "**.***.***/****-81"
        assert documentos.mascarar_cpf_cnpj(None) is None
        assert documentos.mascarar_cpf_cnpj("123") == "***"

    @pytest.mark.parametrize("papel", ["operator_token", "agronomist_token"])
    def test_quem_nao_gerencia_fazenda_ve_so_o_fim(
        self, client: TestClient, admin_token: dict, papel: str, request
    ) -> None:
        fazenda = _cria(client, admin_token, owner_document=CPF)
        cabecalho = request.getfixturevalue(papel)
        lista = client.get("/v1/farms", headers=cabecalho)
        assert lista.status_code == 200
        vista = next(f for f in lista.json() if f["id"] == fazenda["id"])
        assert vista["owner_document"] == "***.***.***-25"
        assert vista["owner_document_masked"] is True
        assert "52998224725" not in lista.text

    def test_quem_gerencia_ve_completo(self, client: TestClient, admin_token: dict) -> None:
        fazenda = _cria(client, admin_token, owner_document=CNPJ)
        assert fazenda["owner_document"] == "11222333000181"
        assert fazenda["owner_document_masked"] is False
        vista = next(
            f for f in client.get("/v1/farms", headers=admin_token).json()
            if f["id"] == fazenda["id"]
        )
        assert vista["owner_document"] == "11222333000181"

    def test_cliente_lendo_completo_nao_gera_linha(
        self, client: TestClient, admin_token: dict, session: Session
    ) -> None:
        _cria(client, admin_token, owner_document=CPF)
        client.get("/v1/farms", headers=admin_token)
        linhas = session.scalars(
            select(AuditEntry).where(AuditEntry.action == "farm.owner_document_viewed")
        ).all()
        assert linhas == []

    def test_suporte_em_leitura_ve_mascarado(
        self, client: TestClient, admin_token: dict, equipe, demo: dict
    ) -> None:
        from tests.test_plataforma_e_suporte import _abrir_suporte
        from valtexa.models import PlatformRole

        client.patch(
            f"/v1/farms/{demo['farm_id']}", json={"owner_document": CPF}, headers=admin_token
        )
        _, token = _abrir_suporte(client, equipe(PlatformRole.SUPORTE), demo["tenant_id"])
        vista = client.get("/v1/farms", headers=token).json()[0]
        assert vista["owner_document"] == "***.***.***-25"

    def test_suporte_assistido_ve_completo_e_fica_na_trilha(
        self, client: TestClient, admin_token: dict, equipe, demo: dict, session: Session
    ) -> None:
        from tests.test_plataforma_e_suporte import _abrir_suporte
        from valtexa.models import PlatformRole

        client.patch(
            f"/v1/farms/{demo['farm_id']}", json={"owner_document": CPF}, headers=admin_token
        )
        dados, token = _abrir_suporte(
            client,
            equipe(PlatformRole.SUPORTE),
            demo["tenant_id"],
            assisted_reason="Conferir o cadastro com o produtor",
        )
        vista = client.get("/v1/farms", headers=token).json()[0]
        assert vista["owner_document"] == "52998224725"

        linha = session.scalars(
            select(AuditEntry).where(AuditEntry.action == "farm.owner_document_viewed")
        ).one()
        assert linha.tenant_id == demo["tenant_id"]
        assert linha.actor_label == "suporte@equipe.valtexa.dev"
        assert linha.payload["farm_ids"] == [demo["farm_id"]]
        assert linha.support_session_id == dados["session"]["id"]
