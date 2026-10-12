"""Consentimento de uso dos dados no treino (brief, seção 32).

A prova que importa: **o pipeline de dataset só aceita amostra de cliente com
consentimento SIM**. Sem decisão é NÃO; revogar tira as amostras do caminho; o
corte congelado respeita o consentimento de hoje; e cada decisão fica registrada
com quem e quando.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from tests.helpers import frame
from tests.test_collections import cria_coleta, roda_worker, sobe_arquivo
from valtexa.models import (
    AuditEntry,
    DatasetSample,
    DatasetSampleState,
    Membership,
    PlatformRole,
    Role,
    User,
)
from valtexa.security.passwords import hash_password

ROTA_ADMIN = "/v1/admin/tenants/{tenant_id}/data-consent"


@pytest.fixture
def coleta_para_revisar(
    client: TestClient, platform_token: dict, demo: dict, store, session_factory: sessionmaker
) -> list[dict]:
    """Duas imagens aéreas processadas, com diagnóstico esperando o agrônomo."""
    coleta = cria_coleta(client, platform_token, demo["field_id"], kind="aerial_image")
    for i in range(2):
        sobe_arquivo(client, platform_token, coleta["id"], f"c_{i}.jpg", frame("Healthy") * 3)
    client.post(f"/v1/admin/collections/{coleta['id']}/complete", headers=platform_token)
    roda_worker(session_factory)
    return client.get(
        f"/v1/admin/collections/{coleta['id']}/files", headers=platform_token
    ).json()


def _revisar(client: TestClient, agronomist_token: dict, arquivos: list[dict]) -> None:
    for arquivo in arquivos:
        resposta = client.post(
            f"/v1/diagnoses/{arquivo['diagnosis_id']}/review",
            json={"label": "Falha_de_stand", "confirmed": True},
            headers=agronomist_token,
        )
        assert resposta.status_code == 200, resposta.text


def _amostras(session: Session, tenant_id: str) -> list[DatasetSample]:
    session.expire_all()
    return list(
        session.scalars(select(DatasetSample).where(DatasetSample.tenant_id == tenant_id))
    )


def _autorizar(client: TestClient, headers: dict, tenant_id: str, allowed: bool) -> dict:
    resposta = client.put(
        ROTA_ADMIN.format(tenant_id=tenant_id),
        json={"allowed": allowed, "document_ref": "Termo 7/2026", "notes": "teste"},
        headers=headers,
    )
    assert resposta.status_code == 200, resposta.text
    return resposta.json()


class TestPadraoNao:
    def test_sem_decisao_e_nao(self, client: TestClient, admin_token: dict) -> None:
        estado = client.get("/v1/tenants/current/data-consent", headers=admin_token).json()
        assert estado["allowed"] is False
        assert estado["decided"] is False

    def test_sem_consentimento_a_revisao_nao_vira_amostra(
        self,
        client: TestClient,
        agronomist_token: dict,
        coleta_para_revisar: list[dict],
        demo: dict,
        session: Session,
    ) -> None:
        _revisar(client, agronomist_token, coleta_para_revisar)
        assert _amostras(session, demo["tenant_id"]) == []

    def test_com_nao_explicito_a_revisao_nao_vira_amostra(
        self,
        client: TestClient,
        agronomist_token: dict,
        platform_token: dict,
        coleta_para_revisar: list[dict],
        demo: dict,
        session: Session,
    ) -> None:
        _autorizar(client, platform_token, demo["tenant_id"], allowed=False)
        _revisar(client, agronomist_token, coleta_para_revisar)
        assert _amostras(session, demo["tenant_id"]) == []


class TestComSim:
    def test_com_sim_a_revisao_vira_amostra(
        self,
        client: TestClient,
        agronomist_token: dict,
        platform_token: dict,
        coleta_para_revisar: list[dict],
        demo: dict,
        session: Session,
    ) -> None:
        _autorizar(client, platform_token, demo["tenant_id"], allowed=True)
        _revisar(client, agronomist_token, coleta_para_revisar)
        amostras = _amostras(session, demo["tenant_id"])
        assert len(amostras) == len(coleta_para_revisar)
        assert all(a.state is DatasetSampleState.CANDIDATE for a in amostras)

    def test_revogar_tira_as_amostras_do_treino(
        self,
        client: TestClient,
        agronomist_token: dict,
        platform_token: dict,
        coleta_para_revisar: list[dict],
        demo: dict,
        session: Session,
    ) -> None:
        _autorizar(client, platform_token, demo["tenant_id"], allowed=True)
        _revisar(client, agronomist_token, coleta_para_revisar)
        _autorizar(client, platform_token, demo["tenant_id"], allowed=False)

        amostras = _amostras(session, demo["tenant_id"])
        assert amostras
        assert all(a.state is DatasetSampleState.EXCLUDED for a in amostras)
        assert all("consentimento revogado" in (a.notes or "") for a in amostras)

        dataset_id = amostras[0].dataset_id
        corte = client.post(
            f"/v1/admin/datasets/{dataset_id}/versions",
            json={"version": "v-sem-consentimento"},
            headers=platform_token,
        )
        assert corte.status_code == 422, "nada autorizado: não há o que congelar"

    def test_corte_respeita_o_consentimento_de_hoje(
        self,
        client: TestClient,
        agronomist_token: dict,
        platform_token: dict,
        coleta_para_revisar: list[dict],
        demo: dict,
        session: Session,
    ) -> None:
        """Mesmo que uma amostra escape da exclusão, o corte não a aceita."""
        _autorizar(client, platform_token, demo["tenant_id"], allowed=True)
        _revisar(client, agronomist_token, coleta_para_revisar)
        amostras = _amostras(session, demo["tenant_id"])
        _autorizar(client, platform_token, demo["tenant_id"], allowed=False)
        # Simula uma amostra que ficou viva por outro caminho.
        viva = session.get(DatasetSample, amostras[0].id)
        viva.state = DatasetSampleState.CANDIDATE
        session.commit()

        corte = client.post(
            f"/v1/admin/datasets/{viva.dataset_id}/versions",
            json={"version": "v-escape"},
            headers=platform_token,
        )
        assert corte.status_code == 422


class TestQuemDecide:
    def test_o_dono_decide_no_console_e_fica_registrado(
        self, client: TestClient, demo: dict, session: Session
    ) -> None:
        dono = User(
            email="dono-dados@valtexa.dev",
            full_name="Dono",
            password_hash=hash_password("valtexa-demo-2026"),
        )
        session.add(dono)
        session.flush()
        session.add(Membership(tenant_id=demo["tenant_id"], user_id=dono.id, role=Role.OWNER))
        session.commit()
        login = client.post(
            "/v1/auth/login",
            json={"email": "dono-dados@valtexa.dev", "password": "valtexa-demo-2026"},
        ).json()
        headers = {"Authorization": f"Bearer {login['access_token']}"}

        resposta = client.put(
            "/v1/tenants/current/data-consent",
            json={"allowed": True, "notes": "Pode usar para melhorar o modelo do café."},
            headers=headers,
        )
        assert resposta.status_code == 200, resposta.text
        corpo = resposta.json()
        assert corpo["allowed"] is True
        assert corpo["current"]["decided_by_label"] == "dono-dados@valtexa.dev"
        assert corpo["current"]["source"] == "cliente"

        client.put(
            "/v1/tenants/current/data-consent", json={"allowed": False}, headers=headers
        )
        historico = client.get("/v1/tenants/current/data-consent", headers=headers).json()
        assert [h["allowed"] for h in historico["history"]] == [False, True]

        trilha = session.scalars(
            select(AuditEntry)
            .where(AuditEntry.action == "consent.changed")
            .order_by(AuditEntry.at)
        ).all()
        assert [(t.old_state, t.new_state) for t in trilha] == [
            ("nao_decidido", "sim"),
            ("sim", "nao"),
        ]

    def test_gestor_e_agronomo_nao_decidem(
        self, client: TestClient, admin_token: dict, agronomist_token: dict
    ) -> None:
        for headers in (admin_token, agronomist_token):
            resposta = client.put(
                "/v1/tenants/current/data-consent", json={"allowed": True}, headers=headers
            )
            assert resposta.status_code == 403

    def test_suporte_nao_registra_termo_comercial_registra(
        self, client: TestClient, equipe, demo: dict
    ) -> None:
        corpo = {"allowed": True, "document_ref": "Contrato 12/2026"}
        rota = ROTA_ADMIN.format(tenant_id=demo["tenant_id"])
        suporte = client.put(rota, json=corpo, headers=equipe(PlatformRole.SUPORTE))
        assert suporte.status_code == 403
        comercial = client.put(rota, json=corpo, headers=equipe(PlatformRole.COMERCIAL))
        assert comercial.status_code == 200
        assert comercial.json()["current"]["source"] == "contrato"

    def test_registro_da_valtexa_exige_documento(
        self, client: TestClient, platform_token: dict, demo: dict
    ) -> None:
        resposta = client.put(
            ROTA_ADMIN.format(tenant_id=demo["tenant_id"]),
            json={"allowed": True},
            headers=platform_token,
        )
        assert resposta.status_code == 422
