"""Suspensão pneumática do Rover V3 — decisão do engenheiro mecânico, 11/10/2026.

Substitui os suportes rígidos (grupo S) e o estudo de balancim puro (grupo W) por
**molas pneumáticas sobre balancim longitudinal**.

---

## A restrição que o projeto já tinha estabelecido

`modelo.py`, no cabeçalho do grupo W, registra:

> *A articulação em rolagem (eixo oscilante, mola macia) derruba o tombamento de 37,7°
> para 20,1° — inaceitável em lavoura de café.*

Mola pneumática é mola macia. Se a maciez for aplicada **em rolagem**, a suspensão a ar
cai exatamente na condição que o projeto rejeitou — e cai mais fundo, porque um fole é
mais macio que um eixo oscilante com mola de aço.

A arquitetura abaixo resolve isso **separando os dois eixos**:

* **arfagem (pitch): pneumática.** É onde a suspensão ganha — mantém as quatro rodas no
  chão, absorve o obstáculo e permite ajustar o vão livre;
* **rolagem (roll): rígida.** Mantida pela barra de equalização de braços cruzados que o
  estudo W já tinha (W-08/W-09), agora com função nova: acoplar os dois lados para que o
  fole de um não afunde sem o outro.

Com rolagem rígida, o braço lateral de 235 mm fica intacto e o tombamento geométrico se
preserva. **Isso é uma escolha de projeto desta revisão, não uma instrução recebida** —
e está marcada como tal: se o engenheiro quiser rolagem pneumática também, os dois
números estão em :func:`comparacao_rolagem`.

Unidades: mm, kg, N, bar, L, W.
"""

from __future__ import annotations

import math
import pathlib
import sys

AQUI = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent / 'chassi-gaiola'))
sys.path.insert(0, str(AQUI))

import modelo as M  # noqa: E402

# ===================================================================== cargas
MASSA_NOMINAL = 110.07
"""kg — massa nominal recalculada na Rev F (ver auditoria, D-03)."""

FATOR_DINAMICO = 3.0
"""O mesmo da folha 15 e do caso 2 do FEA: impacto em buraco, 4 rodas."""

N_RODAS = 4
TRANSFERENCIA_LONGITUDINAL = 1.35
"""Quanto a roda mais carregada recebe acima da média, em frenagem ou rampa.

CRITÉRIO DE PROJETO. Com balancim longitudinal a transferência entre as duas rodas do
mesmo lado é limitada pela geometria do balancim, mas não é zero. 1,35 é conservador
para entre-eixos 700 mm com CG a 294 mm; o número exato sai do caso 5 do FEA.
"""


def carga_por_roda(massa_kg: float = None) -> dict:
    """Carga estática, dinâmica e de projeto em cada roda."""
    m = massa_kg if massa_kg is not None else MASSA_NOMINAL
    estatica = m * 9.80665 / N_RODAS
    return dict(
        massa=m,
        estatica_N=estatica,
        estatica_kgf=m / N_RODAS,
        dinamica_N=estatica * FATOR_DINAMICO,
        projeto_N=estatica * FATOR_DINAMICO * TRANSFERENCIA_LONGITUDINAL,
    )


# =========================================================== mola pneumática
PRESSAO_TRABALHO_BAR = 4.0
"""Pressão de regime do fole. CRITÉRIO DE PROJETO.

Escolhida baixa de propósito. Fole de baixa pressão precisa de área maior, mas:
compressor menor, linha mais barata, vazamento menos severo e — o que decide — margem
para subir a pressão quando o rover carrega acessório, sem trocar o componente.
"""

PRESSAO_MAXIMA_BAR = 8.0
"""Teto de trabalho típico de fole industrial pequeno. A CONFIRMAR no datasheet."""


def area_efetiva_necessaria(carga_N: float, pressao_bar: float = None) -> dict:
    """Área efetiva do fole para sustentar a carga na pressão dada."""
    p = (pressao_bar if pressao_bar is not None else PRESSAO_TRABALHO_BAR) * 1e5  # Pa
    area_m2 = carga_N / p
    area_mm2 = area_m2 * 1e6
    return dict(area_mm2=area_mm2, diametro_mm=2 * math.sqrt(area_mm2 / math.pi),
                pressao_bar=p / 1e5)


PRESSAO_MINIMA_FORMA_BAR = 1.0
"""Abaixo disto o fole não mantém a forma e passa a trabalhar enrugado.

É o critério que descarta as bitolas grandes nesta aplicação, e é contraintuitivo: o
rover é leve (270 N por roda), então um fole folgado demais fica *mole demais* para
funcionar como mola. Fole enrugado não tem rigidez previsível, desgasta na dobra e
mascara o controle de altura.
"""


def dimensiona_fole() -> list[dict]:
    """Varre as bitolas correntes e diz qual serve.

    Critério duplo: pressão estática entre 1 e 3 bar (o fole mantém a forma e ainda tem
    para onde subir) e pressão de projeto dentro do teto do componente.
    """
    out = []
    for d in (40.0, 50.0, 60.0, 70.0, 80.0):
        f = fole_escolhido(d)
        if f['p_projeto_bar'] > PRESSAO_MAXIMA_BAR:
            v = 'pressão de projeto acima do teto'
        elif f['p_estatica_bar'] < PRESSAO_MINIMA_FORMA_BAR:
            v = 'estática baixa: fole trabalha enrugado'
        elif f['p_estatica_bar'] > 3.0:
            v = 'estática alta: pouca margem para carga futura'
        else:
            v = 'SERVE'
        out.append({**f, 'veredito': v})
    return out


DIAMETRO_FOLE_MM = 50.0
"""Bitola escolhida: Ø50.

A única das correntes que fecha os dois critérios — 1,37 bar estático (mantém a forma,
com folga para subir) e 5,57 bar na condição de projeto, dentro do teto de 8.

Ø80, que seria a escolha intuitiva por ser a mais robusta, opera a **0,54 bar** com esta
carga: folgado demais para funcionar como mola. O rover é leve, e isso inverte o
dimensionamento habitual de suspensão pneumática.
"""


def fole_escolhido(diametro_mm: float = None) -> dict:
    """O que o fole entrega nas três condições de carga."""
    diametro_mm = diametro_mm if diametro_mm is not None else DIAMETRO_FOLE_MM
    area_mm2 = math.pi * (diametro_mm / 2) ** 2
    c = carga_por_roda()
    return dict(
        diametro_mm=diametro_mm, area_mm2=area_mm2,
        p_estatica_bar=c['estatica_N'] / (area_mm2 * 1e-6) / 1e5,
        p_dinamica_bar=c['dinamica_N'] / (area_mm2 * 1e-6) / 1e5,
        p_projeto_bar=c['projeto_N'] / (area_mm2 * 1e-6) / 1e5,
        capacidade_a_4bar_N=area_mm2 * 1e-6 * 4e5,
        capacidade_a_8bar_N=area_mm2 * 1e-6 * 8e5,
    )


CURSO_TOTAL_MM = 70.0
"""Curso do fole, de batente a batente. 2 × o ``CURSO`` de 35 mm do estudo W."""

ALTURA_AJUSTAVEL_MM = 50.0
"""Faixa de ajuste do vão livre, dentro do curso.

**É o ganho de produto da suspensão a ar**, e vale dizer por quê: o vão livre de 150 mm
da baseline é um compromisso entre passar sobre o obstáculo e manter o CG baixo. Com ar,
deixa de ser compromisso — sobe para transpor o carreador e desce para operar entre as
linhas, onde o CG baixo vale mais.
"""


# ===================================================== componentes e massas
# origem: FONTE (datasheet), FAIXA (catálogo, modelo a escolher), ESTIMATIVA.
COMPONENTES = [
    # (código, descrição, qtd, massa unitária kg, Z mm, origem)
    ('W-10', 'Mola pneumática Ø50, curso 70, 1 dobra', 4, 0.30, 150.0, 'FAIXA'),
    ('W-11', 'Compressor 12 V, 100 % ciclo, ~35 L/min', 1, 2.20, 300.0, 'FAIXA'),
    ('W-12', 'Reservatório 2 L, alumínio', 1, 1.60, 290.0, 'FAIXA'),
    ('W-13', 'Válvula solenoide 3/2, 12 V', 4, 0.18, 300.0, 'FAIXA'),
    ('W-14', 'Sensor de altura (potenciométrico ou Hall)', 2, 0.09, 200.0, 'FAIXA'),
    ('W-15', 'Secador de ar / filtro coalescente', 1, 0.35, 295.0, 'FAIXA'),
    ('W-16', 'Linhas PU Ø6, conexões e manifold', 1, 0.70, 280.0, 'ESTIMATIVA'),
    ('W-17', 'Controlador de nível + chicote', 1, 0.30, 300.0, 'ESTIMATIVA'),
    ('W-18', 'Suporte do fole, superior e inferior (chapa 6)', 8, 0.16, 170.0, 'ESTIMATIVA'),
]
"""Lista de compra e fabricação da suspensão pneumática.

**Nenhum modelo comercial foi escolhido.** As massas são de faixa de catálogo para a
classe do componente, não de datasheet de peça específica — por isso ``FAIXA``. O que é
``ESTIMATIVA`` é cálculo de engenharia sobre geometria ainda não desenhada.

Esta lista não serve para cotar. Serve para dizer **se cabe** — e é o que a seção de
massa responde.
"""

REMOVIDOS = [
    ('S-01', 'Chapa superior do suporte', 4, 1.691),
    ('S-03', 'Nervura do suporte', 8, 0.962),
]
"""O que sai com a suspensão pneumática.

**S-02 permanece**: é a interface do motor-roda (furo Ø88 e os 7 furos M4 no PCD 95), e
essa interface não muda com a suspensão. Ela deixa de soldar em S-01/S-03 e passa a
soldar no balancim — mesma peça, outra montagem. É também a peça da sugestão 2.4 do
fabricante, e a proposta de fabricá-la em aço **continua válida e fica mais forte**, pela
razão do §`NOTA_S02`.
"""

NOTA_S02 = """\
Com suspensão pneumática a S-02 passa a ser peça de suspensão, não só de montagem: ela
recebe a carga da roda e a entrega ao balancim, com o fole no meio do caminho. O caso de
carga muda do estático para o cíclico, e isso **fortalece** a sugestão 2.4 do fabricante:

* em 6061-T6 soldado, a ZTA vale 110 MPa e a categoria de detalhe de fadiga do
  EN 1999-1-3 para junta soldada em liga de alumínio é baixa;
* em aço A36 soldado não há perda de ZTA, e o limite de fadiga do aço carbono existe —
  alumínio **não tem limite de fadiga**, ele acumula dano indefinidamente.

Num componente que agora cicla a cada ondulação do terreno, a diferença deixa de ser
acadêmica. **Recomendação: se a suspensão pneumática for adiante, S-02 em aço passa de
"proposto" a "recomendado", e o caso 5 do FEA passa a exigir verificação de fadiga.**
"""


def massa_sistema() -> dict:
    """Massa que entra, massa que sai e o líquido."""
    entra = sum(q * m for (_, _, q, m, _, _) in COMPONENTES)
    z_entra = sum(q * m * z for (_, _, q, m, z, _) in COMPONENTES) / entra
    sai = sum(kg for (_, _, _, kg) in REMOVIDOS)
    # Z_cg das peças removidas, do modelo.
    ps = [p for p in M.suportes() if p.item in ('S-01', 'S-03')]
    z_sai = sum(p.massa() * p.centroide()[2] for p in ps) / sum(p.massa() for p in ps)

    balancim = sum(p.massa() for p in M.conjunto_w())
    z_bal = (sum(p.massa() * p.centroide()[2] for p in M.conjunto_w()) / balancim)

    return dict(
        entra_pneumatico=entra, z_entra=z_entra,
        entra_balancim=balancim, z_balancim=z_bal,
        sai=sai, z_sai=z_sai,
        liquido=entra + balancim - sai,
    )


def efeito_global() -> dict:
    """Massa nominal, CG e tombamento, antes e depois."""
    s = massa_sistema()
    m0, z0 = MASSA_NOMINAL, 294.1

    # Remove S-01/S-03, acrescenta balancim e pneumática.
    m1 = m0 - s['sai'] + s['entra_balancim'] + s['entra_pneumatico']
    mz = (m0 * z0
          - s['sai'] * s['z_sai']
          + s['entra_balancim'] * s['z_balancim']
          + s['entra_pneumatico'] * s['z_entra'])
    z1 = mz / m1

    return dict(
        massa_antes=m0, z_antes=z0, massa_depois=m1, z_depois=z1,
        delta_massa=m1 - m0, delta_z=z1 - z0,
        tomb_antes=math.degrees(math.atan((M.BITOLA / 2) / z0)),
        tomb_depois=math.degrees(math.atan((M.BITOLA / 2) / z1)),
        envelope_antes=M.envelope_estabilidade(z0),
        envelope_depois=M.envelope_estabilidade(z1),
        margem_baseline=M.M_NOM - m1,
    )


# ======================================================= rolagem: o conflito
RIGIDEZ_ROLAGEM_GRAUS = 3.0
"""Inclinação lateral admitida na condição de projeto, em graus.

É o ``phi_c`` que ``modelo.envelope_estabilidade`` já usa. Manter este número é o que
significa "rígido em rolagem": a suspensão não pode acrescentar inclinação além dele.
"""


def comparacao_rolagem() -> dict:
    """Tombamento com rolagem rígida e com rolagem pneumática.

    A nota do grupo W cita 37,7° → 20,1° para eixo oscilante. Aqui o cálculo é refeito
    com a geometria e a massa de hoje, para que a comparação seja entre números da mesma
    fonte — e para mostrar que a ordem de grandeza da perda se mantém.

    Modelo: com rolagem macia, o CG efetivo sobe pelo curso que o lado comprimido afunda,
    e o braço de tombamento encurta pela inclinação da carroceria.
    """
    e = efeito_global()
    z = e['z_depois']
    meia_bitola = M.BITOLA / 2

    rigida = math.degrees(math.atan(meia_bitola / z))

    # Rolagem macia: o fole do lado externo estende e o interno comprime. No limite do
    # curso, a carroceria inclina e o CG migra para fora.
    curso = CURSO_TOTAL_MM / 2
    inclinacao = math.degrees(math.atan(2 * curso / M.BITOLA))
    z_efetivo = z * math.cos(math.radians(inclinacao))
    desloc_lateral = z * math.sin(math.radians(inclinacao))
    macia = math.degrees(math.atan((meia_bitola - desloc_lateral) / z_efetivo))

    return dict(
        z_cg=z, rigida_deg=rigida, macia_deg=macia, perda_deg=rigida - macia,
        inclinacao_deg=inclinacao, desloc_lateral_mm=desloc_lateral,
        envelope_rigida=M.envelope_estabilidade(z),
        envelope_macia=M.envelope_estabilidade(z_efetivo, phi_c=RIGIDEZ_ROLAGEM_GRAUS + inclinacao),
        nota_projeto='modelo.py registra 37,7° → 20,1° para eixo oscilante com mola macia',
    )


# =============================================================== energia
COMPRESSOR_W = 180.0
"""Potência do compressor 12 V em operação. FAIXA de catálogo, a confirmar."""

CICLO_TRABALHO = 0.05
"""Fração do tempo com o compressor ligado, em regime.

CRITÉRIO DE PROJETO. Sistema estanque só repressuriza por vazamento e por mudança de
altura. 5 % é conservador para um sistema novo; um sistema com vazamento chega a 30 %, e
é por isso que o monitoramento de ciclo entra como requisito — ver `REQUISITOS_CONTROLE`.
"""


def energia() -> dict:
    """O que a suspensão tira da bateria."""
    sys.path.insert(0, str(AQUI))
    import sensores as S  # noqa: PLC0415

    medio_w = COMPRESSOR_W * CICLO_TRABALHO
    solenoides_w = 4 * 4.0 * 0.02   # 4 válvulas, ~4 W, energizadas 2 % do tempo
    controle_w = 1.5
    total = medio_w + solenoides_w + controle_w
    wh_util = S.BATERIA['wh'] * S.PROFUNDIDADE_UTIL
    return dict(
        compressor_pico_w=COMPRESSOR_W, ciclo=CICLO_TRABALHO,
        compressor_medio_w=medio_w, solenoides_w=solenoides_w, controle_w=controle_w,
        total_medio_w=total,
        wh_por_hora=total,
        fracao_da_bateria_por_hora=total / wh_util,
        nota='O pico de 180 W é curto, mas concorre com a tração no mesmo barramento. '
             'Dimensionar o DC/DC 12 V contando o compressor ligado junto com o pior '
             'caso de tração — hoje o conversor tem 360 W e o consumo já comprometido '
             'não está levantado (pendência P-05).',
    )


REQUISITOS_CONTROLE = [
    ('Nivelamento automático', 'Manter a altura de referência com o rover parado e em '
                               'marcha, sem o operador intervir.'),
    ('Altura de operação selecionável', 'Pelo menos duas: "transporte" (alta, para '
                                        'carreador) e "inspeção" (baixa, CG mínimo e '
                                        'mastro mais estável).'),
    ('Monitoramento de ciclo do compressor', 'Ciclo acima do esperado é vazamento. É o '
                                             'modo de falha mais comum de suspensão a '
                                             'ar e o mais fácil de detectar cedo — e a '
                                             'plataforma já tem para onde mandar o '
                                             'alerta: `device.fault` na trilha.'),
    ('Modo de falha seguro', 'Perda de pressão deve apoiar o chassi em batente mecânico, '
                             'não deixar a carroceria no chão. Batente é requisito, '
                             'não acessório.'),
    ('Altura reportada na telemetria', 'Entra no esquema de telemetria do SaaS, que já '
                                       'aceita campos livres em `sensors`. A altura muda '
                                       'a geometria de captura das câmeras e do LiDAR: '
                                       'sem registrá-la, duas inspeções na mesma linha '
                                       'não são comparáveis.'),
    ('Travamento em operação', 'Decidir se as válvulas fecham durante a captura. Fole '
                               'livre isola vibração; fole travado dá referência '
                               'geométrica estável. São objetivos opostos e a escolha '
                               'é de aplicação.'),
]

GANHOS = """\
O que a suspensão pneumática traz, e que nem o suporte rígido nem o balancim puro davam:

1. **Vão livre ajustável.** O 150 mm da baseline é um compromisso: alto para transpor,
   baixo para manter o CG. Com ar deixa de ser compromisso — sobe no carreador, desce na
   linha. É o ganho de produto mais claro.
2. **Isolamento de vibração para a óptica.** São 8 OAK-D e 1 LiDAR, e o caderno já
   especifica coxins antivibração no suporte do LiDAR (G-08) e 1ª frequência ≥ 7,5 Hz
   para o mastro (caso 6 do FEA). Fole filtra a excitação na origem, antes de ela chegar
   ao mastro de 1,78 m. **É provavelmente o ganho técnico maior**, e é mensurável: borrão
   de movimento e ruído de nuvem de pontos.
3. **Nivelamento.** Em terreno inclinado, manter o chassi nivelado mantém o mastro na
   vertical, o que preserva o campo de visão das câmeras laterais e simplifica a
   extrínseca. Hoje a inclinação do terreno entra direto na pose de cada câmera.
4. **Quatro rodas no solo.** É o que o balancim já dava; o ar mantém e acrescenta
   controle de carga por roda.
"""

RISCOS = """\
1. **Massa.** É a objeção principal e está quantificada em `efeito_global`. A margem da
   baseline é de 490 g (D-03) e o sistema não cabe nela — nem perto.
2. **Rolagem.** Mola macia em rolagem derruba o tombamento, e o projeto já havia
   rejeitado isso. A arquitetura proposta mantém rolagem rígida; se isso for abandonado,
   ver `comparacao_rolagem`.
3. **Vazamento.** Modo de falha mais comum, em ambiente de poeira e lavagem. Mitigação:
   batente mecânico (modo de falha seguro) e monitoramento de ciclo.
4. **Energia.** O compressor concorre com a tração no mesmo barramento, e o orçamento
   energético do rover **ainda não fecha** (P-05).
5. **Fadiga da S-02.** O carregamento passa de estático a cíclico — ver `NOTA_S02`.
6. **Nenhum FEA.** Os 8 casos da folha 25 foram escritos para suspensão rígida. Com
   suspensão, as condições de contorno mudam: o apoio deixa de ser nos 4 furos Ø88 e
   passa a ser a rigidez do fole. **Os 8 casos precisam ser reescritos antes de rodar.**
"""


if __name__ == '__main__':
    print('VTX-RV3 Rev F · suspensão pneumática — decisão do engenheiro mecânico')
    print()
    c = carga_por_roda()
    print(f"Carga por roda: {c['estatica_kgf']:.1f} kgf ({c['estatica_N']:.0f} N) · "
          f"dinâmica {c['dinamica_N']:.0f} N · projeto {c['projeto_N']:.0f} N")
    print()
    print('Dimensionamento do fole:')
    for f in dimensiona_fole():
        print(f"  Ø{f['diametro_mm']:3.0f}  estática {f['p_estatica_bar']:5.2f} bar  "
              f"projeto {f['p_projeto_bar']:5.2f} bar  → {f['veredito']}")
    print(f"  escolhido: Ø{DIAMETRO_FOLE_MM:.0f}")
    print()
    s = massa_sistema()
    print('Massa:')
    print(f"  entra · pneumática {s['entra_pneumatico']:6.3f} kg @ Z {s['z_entra']:.0f} mm")
    print(f"  entra · balancim   {s['entra_balancim']:6.3f} kg @ Z {s['z_balancim']:.0f} mm")
    print(f"  sai   · S-01, S-03 {s['sai']:6.3f} kg @ Z {s['z_sai']:.0f} mm")
    print(f"  LÍQUIDO            {s['liquido']:+6.3f} kg")
    print()
    e = efeito_global()
    print('Efeito global:')
    print(f"  massa       {e['massa_antes']:.2f} → {e['massa_depois']:.2f} kg  ({e['delta_massa']:+.2f})")
    print(f"  Z_cg        {e['z_antes']:.1f} → {e['z_depois']:.1f} mm  ({e['delta_z']:+.1f})")
    print(f"  tombamento  {e['tomb_antes']:.2f}° → {e['tomb_depois']:.2f}°  (melhora)")
    print(f"  envelope    {e['envelope_antes']:.2f}° → {e['envelope_depois']:.2f}°")
    print(f"  margem vs baseline 97,8 kg: {e['margem_baseline']:+.2f} kg")
    print()
    r = comparacao_rolagem()
    print('Rolagem — a decisão que falta:')
    print(f"  rígida (proposta): tombamento {r['rigida_deg']:.2f}°  envelope {r['envelope_rigida']:.2f}°")
    print(f"  macia:             tombamento {r['macia_deg']:.2f}°  envelope {r['envelope_macia']:.2f}°")
    print(f"  perda com rolagem macia: {r['perda_deg']:.2f}° de tombamento, "
          f"{r['envelope_rigida'] - r['envelope_macia']:.2f}° de envelope")
    print()
    en = energia()
    print(f"Energia: {en['total_medio_w']:.1f} W médios "
          f"({en['fracao_da_bateria_por_hora']:.2%} da bateria útil por hora) — não é o problema")
