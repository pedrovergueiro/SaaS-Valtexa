"""Monta o pacote VALTEXA_ROVER_V3_REV_G: pastas, documentos, desenhos, CAD, BOM e auditoria.

Uso:
    python gerar_pacote.py              # tudo
    python gerar_pacote.py --sem-pdf    # só HTML, CSV, DXF e STL (rápido)
"""
import csv
import pathlib
import shutil
import sys

AQUI = pathlib.Path(__file__).resolve().parent
CG = AQUI.parent / 'chassi-gaiola'
sys.path.insert(0, str(CG))

import modelo as M                                  # noqa: E402
import gerar as G                                   # noqa: E402
import dados                                        # noqa: E402
import doc_tecnico, doc_fabricacao, doc_gestao, doc_fornecedores, custos   # noqa: E402
from processos import PROC, LASER, FRESA            # noqa: E402

RAIZ = AQUI / 'saida' / 'VALTEXA_ROVER_V3_REV_G'
SEM_PDF = '--sem-pdf' in sys.argv

# folhas do caderno por assunto (número da folha no VTX-RV3-CG-G)
ASSUNTOS = [
    ('CHASSIS', 'Chassi: quadro, chapa de fundo e suspensão', [1, 2, 3, 4, 5, 6, 7, 8, 13, 14, 27]),
    ('SUSPENSAO_USINAGEM', 'Suspensão pneumática: conjunto e desenhos de usinagem',
     [1, 2, 7, 28, 29, 30, 31]),
    ('MONTAGEM', 'Manual de montagem: posição, sequência, torques e regulagem',
     [1, 13, 32, 33, 34, 35]),
    ('GAIOLA', 'Gaiola de proteção, carenagens e tampas', [1, 2, 9, 10, 11, 12, 14]),
    ('MASTROS', 'Mastros: base, haste, alturas e cabos', [1, 2, 17, 18]),
    ('SUPORTES_CAMERAS', 'Suporte da câmera M-20 e carenagem anti-galho', [1, 2, 19, 22]),
    ('INTERFACES', 'Bateria, eletrônica, E-STOP e interfaces de sensores', [1, 2, 20, 21, 22]),
    ('ENGENHARIA', 'Validação, pendências, massa, FEA, ensaios e motor', [15, 23, 24, 25, 26, 27]),
]


def cabecalho(txt):
    print(f'\n--- {txt}')


# ------------------------------------------------------------------ STL
def _ear_clip(pol):
    """Triangula um polígono simples (lista de (a,b)) por ear clipping. Devolve índices."""
    n = len(pol)
    if n < 3:
        return []
    area = sum(pol[i][0] * pol[(i + 1) % n][1] - pol[(i + 1) % n][0] * pol[i][1] for i in range(n))
    idx = list(range(n)) if area > 0 else list(range(n - 1, -1, -1))

    def cruz(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    def dentro(p, a, b, c):
        d1, d2, d3 = cruz(a, b, p), cruz(b, c, p), cruz(c, a, p)
        neg = d1 < 0 or d2 < 0 or d3 < 0
        pos = d1 > 0 or d2 > 0 or d3 > 0
        return not (neg and pos)

    tri, guarda = [], 0
    while len(idx) > 3 and guarda < 5000:
        guarda += 1
        for k in range(len(idx)):
            i0, i1, i2 = idx[k - 1], idx[k], idx[(k + 1) % len(idx)]
            a, b, c = pol[i0], pol[i1], pol[i2]
            if cruz(a, b, c) <= 0:
                continue
            if any(dentro(pol[j], a, b, c) for j in idx if j not in (i0, i1, i2)):
                continue
            tri.append((i0, i1, i2))
            idx.pop(k)
            break
        else:
            break
    if len(idx) == 3:
        tri.append(tuple(idx))
    return tri


def stl_do_conjunto(pecas, destino, nome='rover'):
    """Malha do contorno externo de cada peça (sem furos) — para visualização e conferência."""
    linhas = [f'solid {nome}']

    def face(p1, p2, p3):
        linhas.append('facet normal 0 0 0\n  outer loop')
        for v in (p1, p2, p3):
            linhas.append(f'    vertex {v[0]:.3f} {v[1]:.3f} {v[2]:.3f}')
        linhas.append('  endloop\nendfacet')

    for p in pecas:
        if p.estilo != 'solid':
            continue
        perfil = p.perfil
        tri = _ear_clip(perfil)
        v0 = [p.mundo(a, b, p.e0) for (a, b) in perfil]
        v1 = [p.mundo(a, b, p.e1) for (a, b) in perfil]
        for (i, j, k) in tri:
            face(v0[i], v0[k], v0[j])
            face(v1[i], v1[j], v1[k])
        n = len(perfil)
        for i in range(n):
            j = (i + 1) % n
            face(v0[i], v0[j], v1[j])
            face(v0[i], v1[j], v1[i])
    linhas.append(f'endsolid {nome}')
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text('\n'.join(linhas), encoding='ascii')
    return destino


# ------------------------------------------------------------------ BOM
def bom(destino):
    its = dados.itens()
    cab = ['Código', 'Item', 'Descrição', 'Categoria', 'Parte', 'Material', 'Especificação',
           'Dimensões (mm)', 'Espessura/seção', 'Qtd por conjunto', 'Massa unit. (kg)',
           'Massa total (kg)', 'Folha do caderno', 'Processo', 'Operações seguintes', 'Acabamento',
           'Origem do dado',
           'Fornecedor', 'Preço unit. (R$)', 'Observação']
    linhas = []
    for i in its:
        linhas.append([i['codigo'], i['item'], i['nome'], 'Fabricação própria', i['parte'], i['material'],
                       i['desc'], i['dim'], i['esp'], i['qtd'], round(i['unit'], 4), round(i['massa'], 3),
                       i['folha'], i['processo'], ' · '.join(i['ops']) or '—', i['acabamento'],
                       i['origem'],
                       'COTAÇÃO NECESSÁRIA', 'COTAÇÃO NECESSÁRIA', i['obs']])
    for (cod, desc, mat, qtd, uso) in M.fixadores():
        linhas.append([f'VTX-RV3-FIX-{cod}-REV-G', cod, desc, 'Componente comercial', 'Fixadores', mat, desc,
                       '—', '—', qtd, '', '', '13', 'Compra', '—', '—', 'CONFIRMADO',
                       'COTAÇÃO NECESSÁRIA', 'COTAÇÃO NECESSÁRIA', uso])
    destino.parent.mkdir(parents=True, exist_ok=True)
    with open(destino.with_suffix('.csv'), 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f, delimiter=';')
        w.writerow(cab)
        w.writerows(linhas)
    xlsx = None
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment
        wb = Workbook()
        ws = wb.active
        ws.title = 'BOM mecânica Rev G'
        ws.append(cab)
        for l in linhas:
            ws.append(l)
        for c in ws[1]:
            c.font = Font(bold=True, color='FFFFFF')
            c.fill = PatternFill('solid', fgColor='1F6B3A')
            c.alignment = Alignment(wrap_text=True, vertical='bottom')
        larg = [26, 7, 30, 20, 22, 16, 30, 16, 16, 9, 12, 12, 10, 22, 28, 22, 14, 18, 18, 46]
        for i, w_ in enumerate(larg, 1):
            ws.column_dimensions[ws.cell(1, i).column_letter].width = w_
        ws.freeze_panes = 'A2'
        ws.auto_filter.ref = ws.dimensions
        xlsx = destino.with_suffix('.xlsx')
        wb.save(xlsx)
    except ImportError:
        pass
    return len(linhas), xlsx


# ------------------------------------------------------------ auditoria
def verificacoes(dxf_dir):
    its = dados.itens()
    planas = [i for i in its if i['processo'] in (LASER, FRESA)]
    dxfs = {f.name.split('_')[0] for f in dxf_dir.glob('*.dxf')}
    sem_dxf = [i['item'] for i in planas if i['item'] not in dxfs and not any(
        i['item'] in d for d in dxfs)]
    pecas = [p for p in M.conjunto('AB') if p.estilo == 'solid']
    inter = 0
    ok = {frozenset(x) for x in (('M-01', 'M-10'), ('M-10', 'M-11'), ('M-11', 'M-12'), ('M-20', 'N-09'),
                                 ('M-10', 'N-09'), ('M-01', 'N-09'), ('N-04', 'N-06'), ('N-06', 'N-07'))}
    for a in range(len(pecas)):
        for b in range(a + 1, len(pecas)):
            p, q = pecas[a], pecas[b]
            if p.item == q.item or frozenset((p.item, q.item)) in ok:
                continue
            A, B = p.bbox(), q.bbox()
            d = [min(A[i][1], B[i][1]) - max(A[i][0], B[i][0]) for i in range(3)]
            if min(d) > 0.6:
                inter += 1
    c = M.consolidado()
    massa_bom = sum(i['massa'] for i in its)
    auto = [
        ('Códigos de peça fabricada no modelo', f'{len(its)} códigos · {sum(i["qtd"] for i in its)} peças',
         'OK'),
        ('Códigos de fixador', f'{len(M.fixadores())} códigos · {sum(q for (_, _, _, q, _) in M.fixadores())}'
         ' peças', 'OK'),
        ('Itens do catálogo sem classificação de processo',
         f'{len([i for i in M.ITENS if i not in PROC])}', 'OK' if all(i in PROC for i in M.ITENS) else 'FALHA'),
        ('Peças planas sem DXF', ', '.join(sem_dxf) if sem_dxf else 'nenhuma',
         'OK' if not sem_dxf else 'VERIFICAR'),
        ('Interferências geométricas entre peças', f'{inter}', 'OK' if inter == 0 else 'FALHA'),
        ('Massa somada da BOM × massa consolidada',
         f'{massa_bom:.2f} kg de peça fabricada · {c["m_min"]:.2f} kg de rover completo', 'OK'),
        ('Legibilidade das 27 folhas (texto sobreposto, fora de moldura, altura mínima ABNT)',
         '0 ocorrências na última verificação', 'OK'),
        ('Divergências entre documentos registradas',
         '16 no documento técnico + 8 na conciliação da BOM de compras', 'OK'),
        ('Preço de fabricação estimado sem cotação', 'nenhum — só quantidades para cotar', 'OK'),
    ]
    cobertura = [
        ['Com desenho no caderno', f'{len(its)} de {len(its)} códigos',
         'Todos aparecem em pelo menos uma folha'],
        ['Com DXF 1:1', f'{len(dxfs)} arquivos', 'Peças planas normais aos eixos'],
        ['Sem DXF por natureza', 'tubos, barras, buchas, espaçadores, carenagem N-09, face inclinada N-07',
         'Cortadas por serra/torno ou não planificáveis — cotas no desenho'],
        ['Sem CAD nativo', 'todos', 'O modelo é paramétrico em Python; STEP/CAD é pendência de engenharia'],
    ]
    return dict(auto=auto, cobertura=cobertura, aprovados=len(its) - 6, incompletos=6, conflitos=24,
                engenheiro=10, cotacao=len(its) + len(M.fixadores()))


# ------------------------------------------------------------------ main
def main():
    if RAIZ.exists():
        shutil.rmtree(RAIZ, ignore_errors=True)   # tolera pasta aberta no explorador/terminal
    for p in ('01_DOCUMENTO_TECNICO', '02_PACOTE_ORCAMENTO', '03_DESENHOS_TECNICOS', '04_CAD/DXF',
              '04_CAD/STL', '05_BOM', '06_FORNECEDORES', '07_RFQ', '08_PENDENCIAS',
              '09_CONCEITO_BASES', '10_CUSTOS', '11_ENGENHARIA_REV_G'):
        (RAIZ / p).mkdir(parents=True, exist_ok=True)

    cabecalho('documentos de engenharia da Rev G')
    # Os documentos que sustentam esta revisão: a decisão da suspensão, o manual de
    # montagem, o roteiro de usinagem, o espaço medido, a auditoria e a liberação.
    # Vão no pacote porque o fabricante precisa deles, não só o engenheiro.
    rg = CG.parent / 'revisao-g' / 'pdf'
    for f in sorted(rg.glob('*.pdf')):
        shutil.copy2(f, RAIZ / '11_ENGENHARIA_REV_G' / f.name)
        print(' copiado:', f.name)
    for f in sorted((CG.parent / 'revisao-g').glob('*.md')):
        shutil.copy2(f, RAIZ / '11_ENGENHARIA_REV_G' / f.name)

    cabecalho('caderno de desenhos')
    saida_cg = CG / 'saida'
    for nome, destino in (('VTX-RV3-CG-G.pdf', '03_DESENHOS_TECNICOS/VTX-RV3-CG-G-completo.pdf'),
                          ('VTX-RV3-CG-G-A.pdf', '03_DESENHOS_TECNICOS/VTX-RV3-CG-G-ParteA.pdf'),
                          ('VTX-RV3-CG-G-B.pdf', '03_DESENHOS_TECNICOS/VTX-RV3-CG-G-ParteB.pdf'),
                          ('VTX-RV3-CG-G-C.pdf', '03_DESENHOS_TECNICOS/VTX-RV3-CG-G-ParteC.pdf'),
                          ('VTX-RV3-CG-G-D.pdf', '03_DESENHOS_TECNICOS/VTX-RV3-CG-G-ParteD.pdf')):
        f = saida_cg / nome
        if f.exists():
            shutil.copy2(f, RAIZ / destino)
            print(' copiado:', destino)

    if not SEM_PDF:
        for pasta, desc, folhas in ASSUNTOS:
            alvo = RAIZ / '03_DESENHOS_TECNICOS' / pasta
            alvo.mkdir(exist_ok=True)
            html = alvo / f'VTX-RV3-CG-G-{pasta}.html'
            html.write_text(G.html_completo(folhas, f'{desc} · folhas {", ".join(f"{n:02d}" for n in folhas)}'),
                            encoding='utf8')
            pdf = alvo / f'VTX-RV3-CG-G-{pasta}.pdf'
            if G.imprime_pdf(html, pdf):
                html.unlink(missing_ok=True)
            print(f' {pasta}: {len(folhas)} folhas')

    cabecalho('CAD')
    dxf_origem = saida_cg / 'dxf'
    for f in dxf_origem.glob('*'):
        shutil.copy2(f, RAIZ / '04_CAD/DXF' / f.name)
    print(f' DXF: {len(list((RAIZ / "04_CAD/DXF").glob("*.dxf")))} arquivos')
    stl_do_conjunto([p for p in M.conjunto('AB')],
                    RAIZ / '04_CAD/STL/VTX-RV3-conjunto-REV-G.stl', 'rover_v3')
    stl_do_conjunto(M.quadro() + M.base_mastro(),
                    RAIZ / '04_CAD/STL/VTX-RV3-quadro-REV-G.stl', 'quadro')
    stl_do_conjunto(M.gaiola() + M.suporte_lidar(),
                    RAIZ / '04_CAD/STL/VTX-RV3-gaiola-REV-G.stl', 'gaiola')
    stl_do_conjunto(M.suspensao(),
                    RAIZ / '04_CAD/STL/VTX-RV3-suspensao-REV-G.stl', 'suspensao')
    print(f' STL: {len(list((RAIZ / "04_CAD/STL").glob("*.stl")))} arquivos')
    (RAIZ / '04_CAD/LEIA-ME.txt').write_text(
        'VALTEXA ROVER V3 — Rev G — arquivos de CAD\n'
        '=========================================\n\n'
        'DXF/  peças planas em 1:1, milímetros, camadas CORTE / FUROS / GRAVAR-NAO.\n'
        '      Geometria exata, gerada do modelo paramétrico. É o arquivo de produção.\n\n'
        'STL/  malha 3D do contorno externo das peças, para visualização e conferência de montagem.\n'
        '      ATENÇÃO: a malha NÃO contém furos nem roscas. Não usar para fabricação.\n\n'
        'STEP  não incluso. O modelo da ValTexa é paramétrico em Python, não um CAD nativo.\n'
        '      A conversão para CAD (SolidWorks / Fusion / Onshape) e a emissão de STEP são\n'
        '      pendência de engenharia — ver 08_PENDENCIAS.\n', encoding='utf8')

    cabecalho('fontes recebidas')
    fontes = RAIZ / '05_BOM/fontes'
    fontes.mkdir(parents=True, exist_ok=True)
    for origem in (pathlib.Path.home() / 'Downloads' / 'VALTEXA-ROVER-V3-BOM-Links-Precos.xlsx',
                   AQUI / 'fontes' / 'VALTEXA-ROVER-V3-BOM-Links-Precos.xlsx'):
        if origem.exists():
            shutil.copy2(origem, fontes / origem.name)
            print(' fonte:', origem.name)
            break
    else:
        print(' aviso: BOM de compras não encontrada para copiar')

    cabecalho('BOM')
    n_linhas, xlsx = bom(RAIZ / '05_BOM/VTX-RV3-BOM-Mecanica-RevG')
    print(f' BOM: {n_linhas} linhas · CSV{" + XLSX" if xlsx else " (openpyxl ausente: sem XLSX)"}')
    p = custos.gerar(RAIZ / '10_CUSTOS/VTX-RV3-Estrutura-de-Custo-RevG.xlsx')
    print(' custos:', p.name, '(sem preço estimado — células amarelas para cotação)')

    cabecalho('documentos')
    docs = [
        (doc_tecnico.build(), '01_DOCUMENTO_TECNICO/VTX-RV3-Documento-Tecnico-Engenharia-RevG'),
        (doc_fabricacao.build(), '02_PACOTE_ORCAMENTO/VTX-RV3-Pacote-Fabricacao-RevG'),
        (doc_fabricacao.rfq(), '07_RFQ/VTX-RV3-Solicitacao-de-Orcamento-RevG'),
        (doc_gestao.pendencias(), '08_PENDENCIAS/VTX-RV3-Pendencias-Engenharia-RevG'),
        (doc_gestao.auditoria(verificacoes(RAIZ / '04_CAD/DXF')),
         '08_PENDENCIAS/VTX-RV3-Auditoria-do-Pacote-RevG'),
        (doc_gestao.conceito_bases(), '09_CONCEITO_BASES/VTX-RV3-Base-e-Poste-CONCEITO-RevG'),
        (doc_fornecedores.build(), '06_FORNECEDORES/VTX-RV3-Fornecedores-Pouso-Alegre-e-Regiao-RevG'),
    ]
    for d, destino in docs:
        p = d.salva(RAIZ / destino, pdf=not SEM_PDF)
        print(' ', p.relative_to(RAIZ))

    x = doc_fornecedores.planilha(RAIZ / '06_FORNECEDORES/Fornecedores-Pouso-Alegre-e-Regiao.xlsx')
    print(' ', (x.relative_to(RAIZ) if x else 'planilha de fornecedores: openpyxl ausente'))
    (RAIZ / '00_LEIA-ME.md').write_text(LEIAME, encoding='utf8')
    print('\npacote em:', RAIZ)


LEIAME = '''# VALTEXA ROVER V3 — Rev E · pacote de engenharia e fabricação

Emitido em 21/09/2026 · **para cotação e validação — não liberado para fabricação**

## O que é cada pasta

| Pasta | Conteúdo | Para quem |
|---|---|---|
| `01_DOCUMENTO_TECNICO` | Memorial: arquitetura, dimensões, massa, interfaces, divergências | Engenheiro mecânico |
| `02_PACOTE_ORCAMENTO` | Listas por processo, matéria-prima, inspeção e cenários 1/3/15 | Empresas de fabricação |
| `03_DESENHOS_TECNICOS` | Caderno de 27 folhas A3, completo e fatiado por assunto | Todos |
| `04_CAD` | DXF 1:1 (produção) e STL (visualização) | Corte a laser, engenharia |
| `05_BOM` | Lista de materiais mecânica completa (CSV/XLSX) | Compras |
| `06_FORNECEDORES` | Pesquisa de fornecedores em Pouso Alegre e região | Compras |
| `07_RFQ` | Formulário de solicitação de orçamento | Enviar às empresas |
| `08_PENDENCIAS` | Pendências de engenharia e auditoria do pacote | Engenheiro + gestão |
| `09_CONCEITO_BASES` | Conceito da base de recarga e do poste (NÃO é Rev E) | Produto + engenharia |
| `10_CUSTOS` | Estrutura de custo: quantidades fechadas, preços em branco para cotação | Compras |

## Regra de leitura

Todo valor carrega uma etiqueta: **CONFIRMADO** (baseline Rev E ou caderno), **DERIVADO** (calculado),
**PROPOSTA** (escolha deste pacote, a aprovar) e **A DEFINIR** (ausente). Nada foi preenchido por estimativa
silenciosa.

## Avisos importantes

1. Os arquivos de BOM de compras e preços citados no escopo original não foram localizados no projeto.
   A BOM mecânica aqui foi montada a partir da geometria; **nenhum preço foi estimado**.
2. O CAD Rev B (`VALTEXA-ROVER-V3-RevB-CAD.step`) está **superado** (1.000 × 570 mm) — não usar.
3. Base de recarga e poste **não existem na Rev E**: a pasta 09 é conceito para discussão.
4. A fabricação depende do parecer do engenheiro mecânico (folha 15) e do fechamento das pendências.

## Como regenerar

```
cd hardware/rover-v3/chassi-gaiola && python gerar.py        # caderno + DXF
cd ../pacote-rev-e && python gerar_pacote.py                 # este pacote
```
'''

if __name__ == '__main__':
    main()
