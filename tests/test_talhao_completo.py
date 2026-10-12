"""Talhão completo (brief, seção 5): espaçamento entre plantas, linhas, fileiras de
validação e observações — no cadastro, na edição, na resposta e na auditoria."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from valtexa.models import AuditEntry

CONTORNO = [[-45.4530, -22.4120], [-45.4515, -22.4120], [-45.4515, -22.4132], [-45.4530, -22.4132]]


def test_cadastro_com_os_campos_novos(
    client: TestClient, admin_token: dict, demo: dict
) -> None:
    resposta = client.post(
        f"/v1/farms/{demo['farm_id']}/fields",
        json={
            "name": "Café Novo",
            "crop": "coffee",
            "boundary": CONTORNO,
            "row_spacing_m": 3.5,
            "plant_spacing_m": 0.7,
            "row_count": 40,
            "validation_rows": [12, 3],
            "notes": "Plantio adensado; cuidado com a curva de nível no fundo.",
        },
        headers=admin_token,
    )
    assert resposta.status_code == 201, resposta.text
    corpo = resposta.json()
    assert corpo["plant_spacing_m"] == 0.7
    assert corpo["row_count"] == 40
    assert corpo["validation_rows"] == [3, 12], "em ordem"
    assert corpo["notes"].startswith("Plantio adensado")


def test_fileira_alem_das_linhas_e_recusada(
    client: TestClient, admin_token: dict, demo: dict
) -> None:
    resposta = client.post(
        f"/v1/farms/{demo['farm_id']}/fields",
        json={
            "name": "Café X",
            "crop": "coffee",
            "boundary": CONTORNO,
            "row_count": 10,
            "validation_rows": [11],
        },
        headers=admin_token,
    )
    assert resposta.status_code == 422


def test_fileira_repetida_ou_zero_e_recusada(
    client: TestClient, admin_token: dict, demo: dict
) -> None:
    for fileiras in ([2, 2], [0]):
        resposta = client.patch(
            f"/v1/fields/{demo['field_id']}",
            json={"validation_rows": fileiras},
            headers=admin_token,
        )
        assert resposta.status_code == 422, fileiras


def test_edicao_parcial_com_auditoria(
    client: TestClient, admin_token: dict, demo: dict, session: Session
) -> None:
    rota = f"/v1/fields/{demo['field_id']}"
    antes = client.get(rota, headers=admin_token).json()

    resposta = client.patch(
        rota,
        json={"plant_spacing_m": 2.5, "row_count": 30, "validation_rows": [5, 20]},
        headers=admin_token,
    )
    assert resposta.status_code == 200, resposta.text
    depois = resposta.json()
    assert depois["plant_spacing_m"] == 2.5
    assert depois["validation_rows"] == [5, 20]
    # O que não veio no corpo não mudou.
    assert depois["name"] == antes["name"]
    assert depois["row_spacing_m"] == antes["row_spacing_m"]

    registro = session.scalars(
        select(AuditEntry).where(
            AuditEntry.action == "field.updated", AuditEntry.subject_id == demo["field_id"]
        )
    ).one()
    assert registro.payload["depois"]["row_count"] == 30
    assert registro.payload["antes"]["plant_spacing_m"] is None

    # Diminuir as linhas abaixo de uma fileira de validação é recusado.
    recusado = client.patch(rota, json={"row_count": 10}, headers=admin_token)
    assert recusado.status_code == 422


def test_null_apaga_e_campo_desconhecido_e_recusado(
    client: TestClient, admin_token: dict, demo: dict
) -> None:
    rota = f"/v1/fields/{demo['field_id']}"
    client.patch(rota, json={"notes": "provisório"}, headers=admin_token)
    apagado = client.patch(rota, json={"notes": None}, headers=admin_token)
    assert apagado.json()["notes"] is None
    assert client.patch(rota, json={"boundary": CONTORNO}, headers=admin_token).status_code == 422


def test_quem_so_le_nao_edita(
    client: TestClient, operator_token: dict, agronomist_token: dict, demo: dict
) -> None:
    rota = f"/v1/fields/{demo['field_id']}"
    assert client.patch(rota, json={"row_count": 5}, headers=operator_token).status_code == 403
    assert client.get(rota, headers=operator_token).status_code == 200
