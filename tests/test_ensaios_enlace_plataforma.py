"""FASE ENLACE na plataforma (Parte 13): catálogo, limites, veredito do servidor igual ao do
robô (as contas são refeitas aqui), modo manual para o portão e o portão da fase."""

from __future__ import annotations

import pytest
from valtexa_rover.ensaios import enlace as rover_enlace

from tests.test_ensaios_plataforma import executa, manda, rover  # noqa: F401 (fixture)
from valtexa.services import ensaios


def _laudo(criterios, amostras, simulado=False) -> dict:
    aprovado = bool(criterios) and all(c["ok"] for c in criterios)
    return {"status": "aprovado" if aprovado else "reprovado", "aprovado": aprovado,
            "simulado": simulado, "criterios": criterios, "medidas": {}, "amostras": amostras}


AMOSTRAS = {
    "enlace_rssi": {"ponto": "P1", "posicao": {"lat": -21.75, "lon": -45.25, "fix": "fixed"},
                    "leituras": [{"i": i, "enlace": e, "estado": "vivo", "rssi_dbm": r,
                                  "snr_db": 25.0, "perda": 0.02, "rtt_ms": 20.0}
                                 for i in range(10) for e, r in (("alta", -70.0),
                                                                 ("subghz", -95.0))]},
    "enlace_latencia": {"ecos": 200, "rtts_ms": [30.0 + (i % 50) for i in range(200)]},
    "enlace_troca": {"enlace": "alta", "modo": "manual", "t_silencio": 2.0,
                     "t_ultimo_rx": 1.6, "silencio_s": 20.0,
                     "melhores": [[0.0, "alta"], [2.7, "subghz"]],
                     "ecos": [[t / 5, 25.0] for t in range(120)]},
    "enlace_starlink": {"modo": "manual", "t_fim_queda": 60.0, "t_volta_nuvem": 68.0,
                        "sondas": [[float(t), 75.0] for t in range(0, 60, 2)]},
    "enlace_energia_base": {"modo": "manual", "t_caiu": 3.0, "t_voltou": 65.0,
                            "ecos": [[0.0, 20.0], [3.0, None], [65.0, 22.0]],
                            "sondas": [[4.0, 70.0], [6.0, 71.0]]},
    "enlace_travessia": {"travessias": [{
        "zona": 1, "avisada_em": "2026-10-09T10:00:00+00:00",
        "prevista": {"duracao_s": 200.0},
        "real": {"entrou": "2026-10-09T10:00:21+00:00", "duracao_s": 209.0},
        "sincronizado_s_depois_de_sair": 12.5}]},
    "relogio": {"rover": {"sincronizado": True, "fonte": "gnss", "offset_ms": 0.004},
                "base": {"sincronizado": True, "fonte": "gnss", "offset_ms": -0.2},
                "atraso_plataforma_s": 0.0},
}
CONTA_DO_ROBO = {
    "enlace_rssi": rover_enlace.avalia_rssi, "enlace_latencia": rover_enlace.avalia_latencia,
    "enlace_troca": rover_enlace.avalia_troca, "enlace_starlink": rover_enlace.avalia_starlink,
    "enlace_energia_base": rover_enlace.avalia_energia_base,
    "enlace_travessia": rover_enlace.avalia_travessia, "relogio": rover_enlace.avalia_relogio,
}
PARAMS = {"enlace_rssi": {"ponto": "P1"}}


def test_catalogo_tem_a_fase_enlace_logo_depois_da_seguranca() -> None:
    assert list(ensaios.FASES)[:3] == [0, 1, ensaios.FASE_ENLACE]
    nomes = {d.nome for d in ensaios.CATALOGO.values() if d.fase == ensaios.FASE_ENLACE}
    assert nomes == set(AMOSTRAS)
    with pytest.raises(ensaios.EnsaioInvalidoError, match="mais frouxo"):
        ensaios.valida_pedido("enlace_latencia", {"p99_max_ms": 900})
    assert ensaios.valida_pedido("enlace_latencia", {"p99_max_ms": 200})["p99_max_ms"] == 200
    assert ensaios.valida_pedido("enlace_troca", {})["modo"] == "manual"  # padrão do portão


@pytest.mark.parametrize("nome", sorted(AMOSTRAS))
def test_servidor_refaz_a_conta_e_concorda_com_o_robo(nome) -> None:
    p = ensaios.valida_pedido(nome, PARAMS.get(nome))
    crit_s, _, motivo = ensaios.CATALOGO[nome].calcula(p, AMOSTRAS[nome])
    crit_r, _ = CONTA_DO_ROBO[nome](p, AMOSTRAS[nome])
    assert [(c["nome"], c["ok"]) for c in crit_s] == [(c["nome"], c["ok"]) for c in crit_r]
    assert all(c["ok"] for c in crit_s), crit_s
    assert motivo is None  # modo manual, GNSS exigido, 200 ecos: vale para o portão


def test_feito_por_software_aprova_mas_nao_abre_o_portao(client, platform_token,
                                                         rover) -> None:  # noqa: F811
    amostras = {**AMOSTRAS["enlace_troca"], "modo": "base"}
    crit, _ = rover_enlace.avalia_troca(ensaios.valida_pedido("enlace_troca", {}), amostras)
    r = executa(client, platform_token, rover, "enlace_troca", {"modo": "base"},
                _laudo(crit, amostras))
    assert r["status"] == "aprovado" and r["vale_portao"] is False
    assert "não vale para o portão" in r["observacao"]


def test_portao_da_fase_enlace_so_abre_com_os_sete(client, platform_token,
                                                   rover) -> None:  # noqa: F811
    def fase() -> dict:
        return next(f for f in client.get(f"/v1/platform/rovers/{rover.device_id}/portoes",
                                          headers=platform_token).json()
                    if f["fase"] == ensaios.FASE_ENLACE)

    assert fase()["aprovado"] is False and len(fase()["faltam"]) == 7
    for nome in sorted(AMOSTRAS):
        p = ensaios.valida_pedido(nome, PARAMS.get(nome))
        crit, _ = CONTA_DO_ROBO[nome](p, AMOSTRAS[nome])
        r = executa(client, platform_token, rover, nome, PARAMS.get(nome, {}),
                    _laudo(crit, AMOSTRAS[nome]))
        assert r["status"] == "aprovado" and r["vale_portao"], (nome, r)
    assert fase()["aprovado"] is True and fase()["faltam"] == []
    # o servidor não confia no "aprovado" do robô: p99 de 900 ms reprova
    ruim = {"ecos": 200, "rtts_ms": [900.0] * 200}
    r = executa(client, platform_token, rover, "enlace_latencia", {},
                {**_laudo([], ruim), "status": "aprovado", "aprovado": True})
    assert r["status"] == "reprovado" and r["divergente"] is True
    assert fase()["aprovado"] is False and fase()["faltam"] == ["enlace_latencia"]
    assert manda(client, platform_token, rover, "enlace_rssi", {}).status_code == 422
