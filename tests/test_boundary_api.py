"""A rota de encaixe de contorno: autorização, escopo e falha do serviço de imagem.

O trabalho de imagem mora no VALTEXA-B; aqui se testa o que é desta plataforma —
quem pode pedir, o que acontece quando o serviço não responde, e se o contorno
salvo realmente muda a área do talhão.
"""

from __future__ import annotations

from typing import ClassVar

import httpx
import pytest
from fastapi.testclient import TestClient

from valtexa.services import geo


class TestQuemPode:
    def test_cliente_nao_encaixa_contorno(
        self, client: TestClient, admin_token: dict, demo: dict
    ) -> None:
        """Encaixar contorno é operação da equipe da ValTexa."""
        resposta = client.post(
            "/v1/admin/boundary/refine",
            json={"polygon": [[-45.86, -21.90], [-45.85, -21.90], [-45.85, -21.91]]},
            headers=admin_token,
        )
        assert resposta.status_code == 403

    def test_poligono_pequeno_demais_e_recusado_antes_de_sair_da_plataforma(
        self, client: TestClient, platform_token: dict
    ) -> None:
        resposta = client.post(
            "/v1/admin/boundary/refine",
            json={"polygon": [[-45.86, -21.90], [-45.85, -21.90]]},
            headers=platform_token,
        )
        assert resposta.status_code == 422


class TestServicoDeImagem:
    def test_servico_fora_do_ar_vira_502_com_explicacao(
        self, client: TestClient, platform_token: dict, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Um 500 aqui esconderia que o problema é de outro serviço."""

        def cai(*_args, **_kwargs):
            raise httpx.ConnectError("conexão recusada")

        monkeypatch.setattr(httpx, "post", cai)
        resposta = client.post(
            "/v1/admin/boundary/refine",
            json={"polygon": [[-45.86, -21.90], [-45.85, -21.90], [-45.85, -21.91]]},
            headers=platform_token,
        )
        assert resposta.status_code == 502
        assert "VALTEXA-B" in resposta.json()["detail"]

    def test_recusa_do_servico_chega_inteira_ao_console(
        self, client: TestClient, platform_token: dict, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Sem fonte de imagem licenciada, o motivo precisa chegar a quem clicou."""

        def recusa(*_args, **_kwargs):
            return httpx.Response(
                422, json={"detail": "Nenhuma fonte de imagem configurada (BASEMAP_TILES)."}
            )

        monkeypatch.setattr(httpx, "post", recusa)
        resposta = client.post(
            "/v1/admin/boundary/refine",
            json={"polygon": [[-45.86, -21.90], [-45.85, -21.90], [-45.85, -21.91]]},
            headers=platform_token,
        )
        assert resposta.status_code == 422
        assert "BASEMAP_TILES" in resposta.json()["detail"]

    def test_resposta_do_servico_vira_area_em_hectares(
        self, client: TestClient, platform_token: dict, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        anel = [[-45.8660, -21.9020], [-45.8590, -21.9020], [-45.8590, -21.9060],
                [-45.8660, -21.9060]]

        def responde(*_args, **_kwargs):
            return httpx.Response(
                200,
                json={
                    "polygon": anel,
                    "confidence": 0.82,
                    "hit_limit": 0.18,
                    "area_change": 0.12,
                    "meters_per_pixel": 1.1,
                    "zoom": 17,
                    "rows": None,
                    "notes": [],
                },
            )

        monkeypatch.setattr(httpx, "post", responde)
        resposta = client.post(
            "/v1/admin/boundary/refine", json={"polygon": anel}, headers=platform_token
        )
        assert resposta.status_code == 200
        corpo = resposta.json()
        assert corpo["area_ha"] == pytest.approx(geo.area_ha(anel), rel=0.001)
        assert corpo["confidence"] == 0.82


class TestTerreno:
    """A leitura de terreno vem do VALTEXA-B; a área operável é calculada aqui.

    A divisão é essa porque só a plataforma tem os dois números: o serviço de
    imagem conhece frações de bloco, e o hectare do talhão mora no polígono em
    graus, que é desta base.
    """

    ANEL: ClassVar[list[list[float]]] = [
        [-45.8660, -21.9020], [-45.8590, -21.9020],
        [-45.8590, -21.9060], [-45.8660, -21.9060],
    ]

    def _responde(self, terreno: dict | None):
        def responde(*_args, **_kwargs):
            return httpx.Response(
                200,
                json={
                    "polygon": self.ANEL,
                    "confidence": 0.82,
                    "hit_limit": 0.18,
                    "area_change": 0.12,
                    "meters_per_pixel": 0.08,
                    "zoom": 19,
                    "rows": None,
                    "terrain": terreno,
                    "notes": [],
                },
            )

        return responde

    def test_area_operavel_sai_da_fracao_vezes_a_area_do_contorno(
        self, client: TestClient, platform_token: dict, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """É o número que o planejamento usa no lugar da área bruta."""
        monkeypatch.setattr(
            httpx,
            "post",
            self._responde(
                {
                    "resolution_ok": True,
                    "description": "88% lavoura, 7% obstáculo · 1 bloqueio(s)",
                    "crop_fraction": 0.88,
                    "obstacle_fraction": 0.07,
                    "path_fraction": 0.05,
                    "row_spacing_px": 44.0,
                    "cover": {
                        "fractions": {"lavoura": 0.88, "mata": 0.07, "solo": 0.05, "outro": 0.0},
                        "obstacle_fraction": 0.07,
                        "heuristic": True,
                    },
                    "objects": [
                        {
                            "kind": "mata",
                            "center": [-45.8620, -21.9040],
                            "outline": [[-45.863, -21.903], [-45.861, -21.903],
                                        [-45.861, -21.905], [-45.863, -21.905]],
                            "area_ha": 1.4,
                            "traversable": False,
                            "confidence": 0.9,
                            "blocks": 11,
                        }
                    ],
                    "heuristic": True,
                }
            ),
        )
        corpo = client.post(
            "/v1/admin/boundary/refine", json={"polygon": self.ANEL}, headers=platform_token
        ).json()

        terreno = corpo["terrain"]
        assert terreno["resolution_ok"] is True
        # Lavoura mais caminho: o carreador não tem planta, mas é por onde o
        # rover atravessa, e tirá-lo subestimaria o tempo de missão.
        assert terreno["operable_area_ha"] == pytest.approx(corpo["area_ha"] * 0.93, rel=1e-3)
        assert terreno["operable_area_ha"] < corpo["area_ha"]

        objeto = terreno["objects"][0]
        assert objeto["kind"] == "mata"
        assert objeto["traversable"] is False
        assert terreno["heuristic"] is True, "classe de objeto é palpite, nunca medição"

    def test_sem_resolucao_nao_devolve_area_operavel(
        self, client: TestClient, platform_token: dict, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """O erro caro: numa imagem que não resolve a rua, nada é lavoura para o
        classificador. Publicar "75% de obstáculo" num cafezal inteiro cortaria a
        área operável pela metade sem ninguém desconfiar — melhor não responder.
        """
        monkeypatch.setattr(
            httpx,
            "post",
            self._responde(
                {
                    "resolution_ok": False,
                    "description": "Resolução insuficiente para ler o terreno",
                    "crop_fraction": 0.0,
                    "obstacle_fraction": 0.0,
                    "path_fraction": 0.0,
                }
            ),
        )
        corpo = client.post(
            "/v1/admin/boundary/refine", json={"polygon": self.ANEL}, headers=platform_token
        ).json()

        terreno = corpo["terrain"]
        assert terreno["resolution_ok"] is False
        assert terreno["operable_area_ha"] is None
        assert terreno["objects"] == []

    def test_servico_sem_terreno_nao_quebra_o_encaixe(
        self, client: TestClient, platform_token: dict, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """O contorno é o que a pessoa pediu; o terreno é bônus."""
        monkeypatch.setattr(httpx, "post", self._responde(None))
        resposta = client.post(
            "/v1/admin/boundary/refine", json={"polygon": self.ANEL}, headers=platform_token
        )
        assert resposta.status_code == 200
        assert resposta.json()["terrain"] is None
        assert resposta.json()["polygon"] == self.ANEL


class TestSalvarContorno:
    def test_contorno_novo_recalcula_a_area(
        self, client: TestClient, admin_token: dict, demo: dict
    ) -> None:
        menor = [[-45.8640, -21.9030], [-45.8610, -21.9030], [-45.8610, -21.9050],
                 [-45.8640, -21.9050]]
        resposta = client.patch(
            f"/v1/fields/{demo['field_id']}/boundary",
            json={"boundary": menor},
            headers=admin_token,
        )
        assert resposta.status_code == 200
        assert resposta.json()["area_ha"] == pytest.approx(geo.area_ha(menor), rel=0.001)

    def test_a_mudanca_fica_na_auditoria_com_antes_e_depois(
        self, client: TestClient, admin_token: dict, demo: dict
    ) -> None:
        """Um talhão que encolheu entre duas missões precisa ter explicação."""
        antes = client.get(f"/v1/fields/{demo['field_id']}", headers=admin_token).json()
        client.patch(
            f"/v1/fields/{demo['field_id']}/boundary",
            json={"boundary": [[-45.864, -21.903], [-45.861, -21.903], [-45.861, -21.905]]},
            headers=admin_token,
        )
        trilha = client.get("/v1/audit", headers=admin_token).json()
        registro = next(i for i in trilha if i["action"] == "field.boundary_updated")
        assert registro["payload"]["antes"]["area_ha"] == pytest.approx(antes["area_ha"])
        assert registro["payload"]["depois"]["vertices"] == 3

    def test_quem_nao_administra_fazenda_nao_redesenha(
        self, client: TestClient, agronomist_token: dict, demo: dict
    ) -> None:
        resposta = client.patch(
            f"/v1/fields/{demo['field_id']}/boundary",
            json={"boundary": [[-45.864, -21.903], [-45.861, -21.903], [-45.861, -21.905]]},
            headers=agronomist_token,
        )
        assert resposta.status_code == 403


def test_encaixe_nos_carreadores_primeiro_e_radial_para_ia_antiga(
    client: TestClient, platform_token: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    anel = [[-45.8660, -21.9020], [-45.8590, -21.9020], [-45.8590, -21.9060]]
    corpo = {"polygon": anel, "confidence": 1.0, "hit_limit": 0.0, "area_change": 0.05,
             "meters_per_pixel": 1.1, "zoom": 17, "rows": None, "notes": []}
    chamadas: list[str] = []

    def ia_nova(url, **_kwargs):
        chamadas.append(url.rsplit("/", 1)[-1])
        return httpx.Response(200, json=corpo)

    monkeypatch.setattr(httpx, "post", ia_nova)
    r = client.post("/v1/admin/boundary/refine", json={"polygon": anel}, headers=platform_token)
    assert r.status_code == 200 and r.json()["method"] == "carreador"
    assert chamadas == ["encaixe-carreador"]

    def ia_antiga(url, **_kwargs):
        chamadas.append(url.rsplit("/", 1)[-1])
        if url.endswith("/encaixe-carreador"):
            return httpx.Response(404, json={"detail": "Not Found"})
        return httpx.Response(200, json=corpo)

    chamadas.clear()
    monkeypatch.setattr(httpx, "post", ia_antiga)
    r = client.post("/v1/admin/boundary/refine", json={"polygon": anel}, headers=platform_token)
    assert r.status_code == 200 and r.json()["method"] == "radial"
    assert chamadas == ["encaixe-carreador", "refine-boundary"]


def test_equipe_dentro_do_cliente_usa_a_ia_e_o_plano_pela_sessao_de_suporte(
    client: TestClient, platform_token: dict, admin_token: dict, demo: dict,
    monkeypatch: pytest.MonkeyPatch, session_factory,
) -> None:
    """O editor de contorno fica dentro do cliente: a equipe chega lá por sessão de suporte
    (motivo, prazo, auditoria). Encaixar e planejar são consultas — valem até no modo
    leitura — e cada uma fica na auditoria do cliente."""
    from sqlalchemy import select

    from valtexa.models import AuditEntry

    anel = [[-45.8660, -21.9020], [-45.8590, -21.9020], [-45.8590, -21.9060]]
    monkeypatch.setattr(httpx, "post", lambda *_a, **_k: httpx.Response(200, json={
        "polygon": anel, "confidence": 1.0, "hit_limit": 0.0, "area_change": 0.0,
        "meters_per_pixel": 1.1, "zoom": 17, "rows": None, "notes": []}))
    suporte = client.post("/v1/platform/support-sessions", json={
        "tenant_id": demo["tenant_id"], "reason": "Desenhar o talhão do cliente"},
        headers=platform_token)
    assert suporte.status_code == 201, suporte.text
    token = {"Authorization": f"Bearer {suporte.json()['access_token']}"}

    r = client.post("/v1/admin/boundary/refine", json={"polygon": anel}, headers=token)
    assert r.status_code == 200, r.text
    r = client.post(f"/v1/admin/fields/{demo['field_id']}/plan",
                    json={"boundary": anel, "swath_m": 3.0}, headers=token)
    assert r.status_code == 200, r.text
    # salvar continua exigindo o modo assistido
    r = client.patch(f"/v1/fields/{demo['field_id']}/boundary", json={"boundary": anel},
                   headers=token)
    assert r.status_code == 403

    with session_factory() as s:
        caminhos = [(linha.payload or {}).get("path", "") for linha in s.scalars(
            select(AuditEntry).where(AuditEntry.action == "support.request"))]
    assert any(c.endswith("/boundary/refine") for c in caminhos)
    assert any(c.endswith("/plan") for c in caminhos)

    # o cliente, mesmo administrador da fazenda, não usa
    assert client.post("/v1/admin/boundary/refine", json={"polygon": anel},
                       headers=admin_token).status_code == 403
