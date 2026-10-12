"""As sugestões 2.2, 2.3 e 2.4 do fabricante, respondidas com cálculo.

A 2.1 (estrutura de aço) está em :mod:`materiais`, que é longa o bastante para viver
sozinha.

Cada resposta aqui diz três coisas, nesta ordem: **o que o desenho da Rev E realmente
especifica** (porque uma das quatro sugestões pede algo que já está feito), **o que o
cálculo mostra** e **o que falta para aprovar**.
"""

from __future__ import annotations

import pathlib
import sys

AQUI = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent / 'chassi-gaiola'))
sys.path.insert(0, str(AQUI))

import materiais as MAT  # noqa: E402
import modelo as M  # noqa: E402

# =============================================================================
# 2.2 · Fixações aparafusadas nas tampas
# =============================================================================
# Conclusão: JÁ IMPLEMENTADO na Rev E. O que falta é tornar isso legível no desenho —
# o fabricante leu "rebite" e presumiu o pior, e tinha motivo para presumir.

CLASSES_DE_UNIAO = {
    # (classe, o que caracteriza, como se desfaz)
    1: ('União estrutural permanente',
        'Transmite carga entre elementos do mesmo conjunto soldado. Desfazer exige '
        'cortar.',
        'Solda MIG/TIG. Não se desmonta.'),
    2: ('União estrutural desmontável',
        'Transmite carga entre conjuntos. Sai na manutenção pesada, não na rotina.',
        'Parafuso de alta resistência com porca autotravante ou trava química.'),
    3: ('Fixação de tampa',
        'Não transmite carga de serviço. Sai sempre que alguém abre o rover.',
        'Parafuso de cabeça baixa em castanha roscada permanente (porca-rebite).'),
    4: ('Fixação de carenagem',
        'Protege contra galho e poeira. Sai na manutenção, raramente.',
        'Igual à tampa, com passo maior entre fixadores.'),
    5: ('Fixação de módulo de sensor',
        'Posiciona e alinha instrumento. Sai na troca de configuração, e exige '
        'recalibração depois.',
        'Parafuso em inserto roscado, com pino de referência quando a posição importa.'),
}


def uniao_por_fixador() -> list[dict]:
    """Classifica cada fixador da Rev E nas cinco classes acima.

    É a resposta documental à sugestão 2.2: as tampas **já** são aparafusadas, e o único
    rebite permanente do projeto (F-09) une a nervura C-02 à chapa de fundo C-01 —
    subconjunto interno, embaixo do rover, que não é tampa de manutenção nenhuma.
    """
    classe = {
        'F-01': 2, 'F-02': 2, 'F-03': 2,          # suporte do motor-roda → quadro
        'F-04': 3, 'F-05': 3, 'F-12': 3,          # chapa de fundo no anel inferior
        'F-06': 4, 'F-07': 4, 'F-13': 4,          # carenagens e tampas
        'F-08': 5,                                # suporte do LiDAR
        'F-09': 1,                                # nervura → chapa de fundo (rebite)
        'F-10': 2,                                # MPW86 → suporte
        'F-11': 4, 'F-20': 5, 'F-21': 5, 'F-22': 3, 'F-23': 2, 'F-24': 2,
        'F-25': 3, 'F-26': 5, 'F-27': 5, 'F-28': 3, 'F-29': 4,
    }
    out = []
    for (item, desc, mat, qtd, obs) in M.fixadores():
        c = classe.get(item)
        out.append(dict(item=item, desc=desc, material=mat, qtd=qtd, obs=obs,
                        classe=c, classe_nome=CLASSES_DE_UNIAO[c][0] if c else '—',
                        removivel=c in (2, 3, 4, 5)))
    return out


def resumo_2_2() -> dict:
    f = uniao_por_fixador()
    rebites = [d for d in f if 'Rebite de repuxo' in d['desc']]
    tampas = [d for d in f if d['classe'] in (3, 4)]
    return dict(
        total_fixadores=sum(d['qtd'] for d in f),
        removiveis=sum(d['qtd'] for d in f if d['removivel']),
        permanentes=sum(d['qtd'] for d in f if d['classe'] == 1),
        rebites=rebites,
        n_tampa_carenagem=sum(d['qtd'] for d in tampas),
        por_classe={c: sum(d['qtd'] for d in f if d['classe'] == c)
                    for c in sorted(CLASSES_DE_UNIAO)},
    )


ACAO_2_2 = """\
A sugestão já está atendida na geometria: carenagens e tampas saem com parafuso M5×12
ISO 7380 (F-07) em porca-rebite M5 instalada na parede do tubo (F-06), e a chapa de
fundo com M6×16 (F-05) em porca-rebite M6 (F-04). Cabeça ISO 7380 é baixa e lisa, o que
o próprio caderno justifica: "não prende galho".

O que a Rev F acrescenta não é fixador, é **legibilidade**. O fabricante leu o desenho e
concluiu que o chassi era rebitado — e a leitura dele é defensável, porque a lista de
fixadores mostra "Rebite de repuxo Ø4,8×10" sem dizer que aquele rebite está embaixo da
chapa de fundo, num subconjunto que não se abre. A ação é classificar as uniões nas
cinco classes e publicar a tabela na folha de fixação, para que a resposta à pergunta
"o que eu preciso soltar para abrir isto?" esteja no desenho e não numa troca de
e-mails.

Uma única mudança física é proposta, e é pequena: **passar F-09 (rebite) a parafuso M5
em porca-rebite** nas nervuras C-02. Não é para manutenção — ninguém desmonta nervura —
é para que não exista nenhum rebite no projeto, e a dúvida não se repita na próxima
cotação. Custa 16 parafusos e some com a única fixação permanente não soldada do rover.
"""

# =============================================================================
# 2.3 · Planicidade de 0,1 mm
# =============================================================================

PLANICIDADE_ATUAL = 0.1
PERPENDICULARIDADE_ATUAL = 0.3
RUGOSIDADE_ATUAL = 'Ra 3,2'
PLANICIDADE_PROPOSTA = 0.2


def contexto_2_3() -> dict:
    """A superfície, sua função e os números que o desenho já traz ao lado dela."""
    return dict(
        peca='W-02 · chapa de montagem do motor-roda (era S-02 até a Rev F)',
        espessura_bruta=M.E_PLACA,
        face=f'Y = {M._n(M.Y_FACE)} (datum B)',
        funcao='Face de montagem do motor-roda: recebe a flange Ø105,7 do MPW86 por 7 '
               'parafusos M4 no PCD 95, com o furo central Ø88 passando o corpo do motor.',
        classificacao='Superfície de montagem de motor-roda (a mais crítica das cinco '
                      'categorias listadas no pedido de revisão).',
        gdt_vizinho=dict(perpendicularidade=PERPENDICULARIDADE_ATUAL,
                         paralelismo_X=0.3, rugosidade=RUGOSIDADE_ATUAL),
        pcd=M.MPW_PCD, n_parafusos=M.MPW_N_FUROS,
        engajamento_max=M.MPW_ROSCA_MAX,
    )


def incoerencia_2_3() -> dict:
    """Por que 0,1 mm é desproporcional **dentro do próprio desenho**.

    O argumento não é "0,1 é difícil" — é que o mesmo desenho aceita 0,3 mm de
    perpendicularidade na mesma face. Perpendicularidade é o que desalinha a roda:
    0,3 mm sobre a altura da face inclina o eixo e manda o pneu raspar. Planicidade é o
    que faz a flange assentar: ela se fecha com o aperto dos 7 parafusos, porque a
    flange do motor é rígida e a chapa tem 10 mm.

    Especificar a característica **menos** crítica três vezes mais apertada que a mais
    crítica é a incoerência que o fabricante percebeu, mesmo sem a formular assim.
    """
    ctx = contexto_2_3()
    # Inclinação equivalente de cada tolerância, sobre a base em que ela atua.
    base_plan = M.MPW_PCD                       # entre apoios diametralmente opostos
    base_perp = 2 * M.R_PLACA                   # altura útil da face
    return dict(
        plan_mm=PLANICIDADE_ATUAL, plan_base=base_plan,
        plan_incl_pct=100 * PLANICIDADE_ATUAL / base_plan,
        perp_mm=PERPENDICULARIDADE_ATUAL, perp_base=base_perp,
        perp_incl_pct=100 * PERPENDICULARIDADE_ATUAL / base_perp,
        proposta_mm=PLANICIDADE_PROPOSTA,
        proposta_incl_pct=100 * PLANICIDADE_PROPOSTA / base_plan,
        razao_atual=(PERPENDICULARIDADE_ATUAL / base_perp) / (PLANICIDADE_ATUAL / base_plan),
        razao_proposta=(PERPENDICULARIDADE_ATUAL / base_perp) / (PLANICIDADE_PROPOSTA / base_plan),
        ctx=ctx,
    )


CUSTO_2_3 = """\
O que 0,1 mm cobra, numa chapa de 10 mm soldada a duas nervuras e depois usinada:

* **alívio de tensões antes do faceamento**, ou a peça abre depois de usinada — solda
  de 190 mm de cordão por conjunto deixa tensão residual suficiente para isso;
* **duas passadas** (desbaste e acabamento) com ferramenta afiada, porque alumínio
  empasta e 0,1 mm não tolera aresta postiça;
* **inspeção com desempeno e relógio comparador** ou tridimensional, peça a peça, nas
  quatro unidades.

A 0,2 mm, uma passada de faceamento em fresadora comum entrega, e a inspeção é com
régua de precisão e calibre de folga. É o degrau onde o processo muda de categoria, e é
por isso que a proposta é 0,2 e não 0,15 ou 0,25.

Economia em reais: PENDENTE DE COTAÇÃO. A diferença não está no tempo de máquina — está
em ter ou não ter a etapa de alívio e a inspeção dimensional individual, e isso quem
precifica é o fornecedor, na RFQ.
"""

PENDENCIA_2_3 = """\
**Não se aprova 0,2 mm sem o fabricante do motor.** O datasheet 011121 do ElectroCraft
MPW86 publica a interface (face Ø105,7, PCD 95, 7 furos M4, engajamento máximo 5 mm) mas
**não publica a planicidade exigida da contrapeça**. Sem esse número, 0,2 mm é proposta
fundamentada, não requisito validado.

Pergunta a fazer à ElectroCraft, junto com as que já estão na folha de pendências:
*qual a planicidade e a rugosidade máximas da superfície de montagem que o MPW86 admite,
e qual o torque de aperto dos 7 parafusos M4 com engajamento de 4 a 5 mm?*

A segunda pergunta importa tanto quanto a primeira: é o aperto que fecha o erro de
planicidade, e sem o torque não há como mostrar por cálculo que 0,2 mm se fecha.
"""

# =============================================================================
# 2.4 · Flange / placa de interface da roda em aço
# =============================================================================


def identifica_2_4() -> dict:
    """O que o fabricante chamou de "flange da roda", nos termos do desenho.

    O pedido de revisão manda não supor que a flange seja independente do motor sem
    verificar. Verificado: são **duas peças diferentes**, e só uma é da ValTexa.
    """
    return dict(
        do_motor=dict(
            peca='Flange integrada ao MPW86',
            desc=f'Face Ø{M._n(M.MPW_FACE)} com {M.MPW_N_FUROS} furos M4×0,7-6H no '
                 f'PCD {M._n(M.MPW_PCD)}, passantes',
            fornecedor='ElectroCraft (parte do motor)',
            acao='NÃO ALTERAR. É componente do motor; mexer exige documentação e '
                 'aprovação do fabricante, que este projeto não tem.'),
        da_valtexa=dict(
            peca='W-02 · chapa de montagem do motor-roda (era S-02 até a Rev F)',
            desc=f'Chapa {M._n(2 * M.R_PLACA)}×204×{M._n(M.E_PLACA)}, furo central '
                 f'Ø{M._n(M.D_BORE)}, {M.MPW_N_FUROS} furos Ø4,5 no PCD {M._n(M.MPW_PCD)}',
            material_atual='Al 6061-T6',
            fornecedor='fabricação ValTexa',
            acao='É ESTA a peça da sugestão. Placa de montagem independente, soldada a '
                 'duas nervuras S-03 e à chapa superior S-01, com a face usinada. '
                 'Fabricável em aço sem tocar no motor.'),
        classificacao='Placa de montagem (interface mecânica), não flange integrada.',
    )


def espessura_equivalente_em_aco(e_al: float = None, sigma_al: float = None,
                                 sigma_aco: float = None) -> list[dict]:
    """Espessuras comerciais de chapa de aço que igualam a resistência à flexão da
    chapa de alumínio atual, na condição soldada.

    Critério: módulo de resistência × tensão admissível. Para uma seção retangular de
    largura unitária, W ∝ t²/6 — então a espessura equivalente cresce com a raiz da
    razão de tensões, e não linearmente.
    """
    e_al = e_al if e_al is not None else M.E_PLACA
    sigma_al = sigma_al if sigma_al is not None else MAT.SIGMA_SOLDADO['Al6061T6']
    sigma_aco = sigma_aco if sigma_aco is not None else MAT.SIGMA_SOLDADO['AcoA36']

    capacidade_al = e_al**2 * sigma_al
    rho_al = MAT.MATERIAIS['Al6061T6']['rho']
    rho_aco = MAT.MATERIAIS['AcoA36']['rho']
    out = []
    for e in (5.0, 6.0, 8.0, 10.0, 12.0):
        cap = e**2 * sigma_aco
        out.append(dict(
            espessura=e,
            razao_resistencia=cap / capacidade_al,
            # EI por largura unitária ∝ E·t³/12
            razao_rigidez=(MAT.MATERIAIS['AcoA36']['E'] * e**3)
            / (MAT.MATERIAIS['Al6061T6']['E'] * e_al**3),
            razao_massa=(e * rho_aco) / (e_al * rho_al),
            atende=cap >= capacidade_al,
        ))
    return out


def massa_2_4(espessura_aco: float) -> dict:
    """Massa das 4 chapas do motor-roda: em aço (como está) e se fosse alumínio.

    **A sugestão 2.4 saiu do papel na Rev G.** A peça — que era S-02 e agora é W-02 — é
    fabricada em aço A36, e não por preferência de material: ela passou a ser peça de
    suspensão, recebe a carga da roda a cada ondulação, e alumínio não tem limite de
    fadiga. A conta aqui inverteu de sentido: mostra o que o alumínio economizaria, para
    que o custo da decisão fique explícito.
    """
    uma_aco_real = next(p for p in M.braco(1, 1) if p.item == 'W-02').massa()
    rho_aco = MAT.MATERIAIS['AcoA36']['rho']
    rho_al = MAT.MATERIAIS['Al6061T6']['rho']
    uma_aco = uma_aco_real * (espessura_aco / M.E_PLACA)
    uma_al = uma_aco_real * rho_al / rho_aco
    return dict(uma_al=uma_al, uma_aco=uma_aco, uma_aco_real=uma_aco_real,
                quatro_al=4 * uma_al, quatro_aco=4 * uma_aco,
                delta=4 * (uma_aco - uma_al), espessura=espessura_aco)


GANHO_2_4 = """\
O ganho do aço nesta peça **não é resistência nominal**: 6061-T6 virgem (240 MPa) e A36
(250 MPa) são quase iguais. É outra coisa, e são três:

1. **Não perde na solda.** W-02 é soldada ao braço W-01 e à tampa W-03. Em 6061-T6 a
   zona afetada cai para os 110 MPa que a folha 25 adota; em A36 não há essa perda. Na
   condição em que a peça realmente vai estar, o aço tem 2,3× a tensão utilizável.
2. **Mantém a face usinada sob aperto repetido.** São 7 parafusos M4 apertados contra a
   face, e o motor sai e volta em manutenção. Alumínio ameassa sob a cabeça do parafuso
   a cada ciclo; aço não. É o que liga esta sugestão à 2.3 — não serve especificar
   planicidade de montagem numa face que se deforma na terceira desmontagem.
3. **Usina melhor para tolerância apertada.** Alumínio empasta e forma aresta postiça,
   que é justamente o que impede manter planicidade fina com ferramenta comum.

4. **Fadiga, e este é o argumento que decidiu.** Na Rev G a peça cicla: ela está entre
   a roda e o fole. Aço carbono tem limite de fadiga — abaixo dele não acumula dano.
   Alumínio não tem patamar nenhum: acumula sempre. Para um componente que vê uma
   ondulação de terreno a cada metro de lavoura, isso deixa de ser acadêmico.

O custo é massa, e a massa é o problema deste projeto — ver o relatório. A economia que o
alumínio daria está em `massa_2_4`, para que a decisão fique com número ao lado.
"""


if __name__ == '__main__':
    print('VTX-RV3 Rev G · sugestões 2.2, 2.3 e 2.4 do fabricante')
    print()
    r = resumo_2_2()
    print('2.2 · FIXAÇÕES APARAFUSADAS — JÁ IMPLEMENTADO na Rev E')
    print(f"    {r['total_fixadores']} itens de fixador; {r['removiveis']} removíveis "
          f"({100 * r['removiveis'] / r['total_fixadores']:.1f} %)")
    for c, n in r['por_classe'].items():
        print(f"      classe {c} · {CLASSES_DE_UNIAO[c][0]:36} {n:4} itens")
    for d in r['rebites']:
        print(f"    único rebite permanente: {d['item']} ({d['qtd']} un) — {d['obs']}")
    print()
    i = incoerencia_2_3()
    print('2.3 · PLANICIDADE DE 0,1 mm — PROPOSTA: 0,2 mm')
    print(f"    peça {i['ctx']['peca']}, face {i['ctx']['face']}")
    print(f"    planicidade      {i['plan_mm']} mm / base {i['plan_base']:.0f} mm "
          f"= {i['plan_incl_pct']:.3f} %")
    print(f"    perpendicularidade {i['perp_mm']} mm / base {i['perp_base']:.0f} mm "
          f"= {i['perp_incl_pct']:.3f} %")
    print(f"    → a planicidade está {i['razao_atual']:.1f}× mais apertada que a "
          f"perpendicularidade, na mesma face")
    print(f"    com 0,2 mm a razão cai para {i['razao_proposta']:.1f}× (proporcional)")
    print()
    d = identifica_2_4()
    print('2.4 · FLANGE DA RODA EM AÇO')
    print(f"    classificação: {d['classificacao']}")
    print(f"    NÃO alterar: {d['do_motor']['peca']} — {d['do_motor']['desc']}")
    print(f"    a alterar:   {d['da_valtexa']['peca']} ({d['da_valtexa']['material_atual']})")
    for e in espessura_equivalente_em_aco():
        print(f"      aço {e['espessura']:4.0f} mm  "
              f"{'atende' if e['atende'] else '  —   '}  "
              f"resistência {e['razao_resistencia'] * 100:5.0f}%  "
              f"rigidez {e['razao_rigidez'] * 100:5.0f}%")
    for esp in (6.0, 8.0):
        m = massa_2_4(esp)
        print(f"      4× S-02 em aço {esp:.0f} mm: {m['quatro_aco']:.3f} kg "
              f"(Al: {m['quatro_al']:.3f} kg) → {m['delta']:+.3f} kg")
