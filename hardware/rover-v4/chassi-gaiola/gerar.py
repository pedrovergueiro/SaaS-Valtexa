"""Gera o caderno VTX-RV4-CG-E: HTML (tela e impressão), PDF A3 e DXF das peças planas.

Uso:
    python gerar.py            # HTML + PDF + DXF em ./saida
    python gerar.py --sem-pdf  # só HTML e DXF

O PDF sai do próprio HTML, impresso pelo Microsoft Edge (ou Chrome) em modo headless.
Para gerar à mão: abra saida/VTX-RV4-CG-E.html no navegador → Imprimir → Salvar como PDF,
tamanho A3 paisagem, margens "nenhuma", com "gráficos de fundo" ligado.
"""
import base64
import os
import re
import unicodedata
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))

import modelo as M                      # noqa: E402
from folhas import FOLHAS, TITULOS, DOC  # noqa: E402
from folhas_b import FOLHAS_B  # noqa: E402
from folhas_w import FOLHAS_W  # noqa: E402
from folhas_t import FOLHAS_T  # noqa: E402

TODAS = FOLHAS + FOLHAS_B + FOLHAS_W + FOLHAS_T
PARTES = {'A': (1, 16, 'Parte A — chassi, suspensão pneumática e gaiola'),
          'B': (17, 22, 'Parte B — interfaces: mastro, câmeras, bateria, eletrônica e sensores'),
          'C': (23, 27, 'Parte C — fechamento: pendências, massa, solda/FEA, validação e motor'),
          'D': (28, 35, 'Parte D — usinagem do grupo W e manual de montagem'),
          'E': (36, 42, 'Parte E — V4: mastro, interface modular de sensores, térmicas removíveis, antena e cabos')}

SAIDA = AQUI / 'saida'
FONTES = AQUI / 'fontes'
TITULO = 'Chassi e Gaiola Rover V4'

GOOGLE = ('https://fonts.googleapis.com/css2?family=Barlow:wght@400;500;600;700'
          '&family=Barlow+Semi+Condensed:wght@400;500;600;700&family=IBM+Plex+Mono:wght@500;600&display=swap')
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36'


# ------------------------------------------------------------------- fontes
def fontes_embutidas():
    """Baixa (uma vez) o subconjunto latino das fontes e devolve @font-face com data URI."""
    cache = FONTES / 'fontes.css'
    if cache.exists():
        return cache.read_text(encoding='utf8')
    FONTES.mkdir(exist_ok=True)
    try:
        req = urllib.request.Request(GOOGLE, headers={'User-Agent': UA})
        css = urllib.request.urlopen(req, timeout=30).read().decode('utf8')
    except Exception as e:  # sem rede: cai nas fontes do sistema
        print('aviso: não consegui baixar as fontes —', e)
        return ''
    blocos = re.findall(r'/\* ([a-z-]+) \*/\s*(@font-face\s*{[^}]*})', css)
    saida = []
    for subset, bloco in blocos:
        if subset != 'latin':
            continue
        url = re.search(r'url\((https://[^)]+)\)', bloco).group(1)
        dados = urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': UA}), timeout=30).read()
        b64 = base64.b64encode(dados).decode('ascii')
        saida.append(bloco.replace(url, f'data:font/woff2;base64,{b64}'))
    texto = '\n'.join(saida)
    cache.write_text(texto, encoding='utf8')
    return texto


# ---------------------------------------------------------------------- HTML
def _padrao(ident, passo, ang):
    return (f'<pattern id="{ident}" patternUnits="userSpaceOnUse" width="{passo}" height="{passo}" '
            f'patternTransform="rotate({ang})"><rect width="{passo}" height="{passo}" fill="#ffffff"/>'
            f'<line x1="0" y1="0" x2="0" y2="{passo}" stroke="#15191e" stroke-width="0.16"/></pattern>')


# Hachuras ABNT NBR 12298: 45°, peças vizinhas com ângulo ou passo diferente.
HACHURA = ('<svg width="0" height="0" style="position:absolute" aria-hidden="true"><defs>'
           + _padrao('hach', 1.1, 45) + _padrao('hach2', 1.1, -45) + _padrao('hach3', 1.8, 45)
           + '</defs></svg>')

SCRIPT = '''<script>
(function () {
  var mm = 96 / 25.4;
  function ajusta() {
    var w = document.documentElement.clientWidth - 32;
    var k = Math.min(1, w / (420 * mm));
    document.documentElement.style.setProperty('--k', k.toFixed(4));
  }
  ajusta();
  window.addEventListener('resize', ajusta);
})();
</script>'''


def corpo(faixa=None, sub=None):
    # faixa = (primeira, última) folha, ou uma coleção de números de folha; sem faixa, o caderno completo
    if faixa is None:
        sel = set(range(1, len(TODAS) + 1))
    elif isinstance(faixa, tuple) and len(faixa) == 2 and all(isinstance(v, int) for v in faixa):
        sel = set(range(faixa[0], faixa[1] + 1))
    else:
        sel = set(faixa)
    folhas = [fn().render() for i, fn in enumerate(TODAS, 1) if i in sel]
    nav = ''.join(f'<a href="#f{n:02d}" title="{t}">{n:02d}</a>'
                  for n, (t, _) in TITULOS.items() if n in sel)
    sub = sub or f'Caderno de desenhos A3 · {len(sel)} folhas · rev. 0 · emitido para cotação e validação'
    barra = (f'<header class="barra"><div class="doc"><b>VALTEXA</b> · {DOC} · Chassi estrutural e gaiola de '
             f'proteção<small>{sub}</small></div>'
             f'<nav aria-label="Folhas">{nav}</nav></header>')
    return f'{HACHURA}{barra}<main class="folhas">{"".join(folhas)}</main>{SCRIPT}'


def estilo():
    return fontes_embutidas() + '\n' + (AQUI / 'estilo.css').read_text(encoding='utf8')


def html_completo(faixa=None, sub=None):
    return (f'<!doctype html>\n<html lang="pt-BR"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">'
            f'<title>{TITULO}</title><style>{estilo()}</style></head><body>{corpo(faixa, sub)}</body></html>')


def html_artefato():
    """Mesmo conteúdo, sem o esqueleto (o publicador de Artifacts envolve a página)."""
    return f'<title>{TITULO}</title>\n<style>{estilo()}</style>\n{corpo()}'


# ----------------------------------------------------------------------- PDF
def navegador():
    for p in (r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
              r'C:\Program Files\Microsoft\Edge\Application\msedge.exe',
              r'C:\Program Files\Google\Chrome\Application\chrome.exe',
              shutil.which('msedge') or '', shutil.which('google-chrome') or '', shutil.which('chromium') or ''):
        if p and Path(p).exists():
            return p
    return None


def imprime_pdf(html_path, pdf_path):
    exe = navegador()
    if not exe:
        print('aviso: Edge/Chrome não encontrado — gere o PDF pelo navegador (Ctrl+P).')
        return False
    perfil = SAIDA / '.perfil-navegador'
    cmd = [exe, '--headless=new', '--disable-gpu', '--no-first-run', '--no-pdf-header-footer',
           f'--user-data-dir={perfil}', '--virtual-time-budget=15000', f'--print-to-pdf={pdf_path}',
           html_path.as_uri()]
    subprocess.run(cmd, check=False, capture_output=True, timeout=180)
    shutil.rmtree(perfil, ignore_errors=True)
    return pdf_path.exists()


# ----------------------------------------------------------------------- DXF
def _dxf(entidades):
    linhas = ['0', 'SECTION', '2', 'HEADER', '9', '$INSUNITS', '70', '4', '0', 'ENDSEC',
              '0', 'SECTION', '2', 'ENTITIES']
    for e in entidades:
        linhas += e
    linhas += ['0', 'ENDSEC', '0', 'EOF']
    return '\n'.join(linhas) + '\n'


def _poli(pts, camada):
    e = ['0', 'POLYLINE', '8', camada, '66', '1', '70', '1']
    for x, y in pts:
        e += ['0', 'VERTEX', '8', camada, '10', f'{x:.4f}', '20', f'{y:.4f}']
    e += ['0', 'SEQEND', '8', camada]
    return e


def _circ(x, y, d, camada):
    return ['0', 'CIRCLE', '8', camada, '10', f'{x:.4f}', '20', f'{y:.4f}', '40', f'{d / 2:.4f}']


def _texto(x, y, h, s):
    return ['0', 'TEXT', '8', 'GRAVAR-NAO', '10', f'{x:.3f}', '20', f'{y:.3f}', '40', f'{h}', '1', s]


def exporta_dxf():
    pasta = SAIDA / 'dxf'
    pasta.mkdir(parents=True, exist_ok=True)
    for arq in pasta.glob('*.dxf'):
        arq.unlink()
    pecas = M.conjunto('ABO')          # a entrega e os opcionais: T-04 também sai em DXF
    escolha = {}
    for p in pecas:
        # Fora da lista: peças que não saem de chapa plana — tubo serrado, barra torneada,
        # perfil dobrado. DXF de contorno não serve para elas; a cota está na folha.
        if p.estilo != 'solid' or p.item.startswith(('Q-01', 'Q-02', 'Q-03', 'Q-04', 'Q-05', 'G-01', 'G-02',
                                                       'G-03', 'G-04', 'G-08', 'C-02', 'M-01', 'M-10',
                                                       'M-11', 'M-12', 'B-01', 'E-11', 'N-03', 'N-05',
                                                       'N-07', 'N-09', 'T-10',
                                                       'W-01', 'W-04', 'W-07', 'W-08', 'W-10', 'W-12')):
            continue
        bb = p.bbox()
        chave = p.item
        if p.item in ('M-02', 'E-01', 'E-02', 'N-06', 'N-08') and bb[1][1] < 0:
            continue
        if p.item == 'E-02' and bb[0][0] < 0:
            continue
        # Grupo W: quatro exemplares por código (2 E + 2 D, dianteiro e traseiro).
        # Exporta só o dianteiro esquerdo; os outros três são espelhados.
        if p.item.startswith('W-') and (bb[0][0] < 0 or bb[1][1] < 0):
            continue
        if p.item == 'G-05':
            chave = f'G-05-{int(round(abs(bb[0][0]) if bb[0][0] >= 0 else abs(bb[0][1])))}'
            if bb[0][0] < 0 or bb[1][0] < 0:
                continue
        elif p.item in ('S-01', 'S-02', 'S-03', 'K-01'):
            if bb[0][0] < 0 or bb[1][1] < 0:
                continue
        escolha.setdefault(chave, p)
    nomes = {'G-05-453': 'G-05a_sapata-canto', 'G-05-30': 'G-05b_sapata-interna', 'G-05-245': 'G-05c_sapata-meio'}
    esp = {}
    lista = []
    for chave, p in sorted(escolha.items()):
        it = M.ITENS[p.item]
        a0 = min(q[0] for q in p.perfil)
        b0 = min(q[1] for q in p.perfil)
        n_circ = len(p.circulos)
        ents = [_poli([(q[0] - a0, q[1] - b0) for q in p.perfil], 'CORTE')]
        for (a, b, d) in p.circulos:
            ents.append(_circ(a - a0, b - b0, d, 'FUROS'))
        for furo in p.furos[n_circ:]:
            ents.append(_poli([(q[0] - a0, q[1] - b0) for q in furo], 'FUROS'))
        e = round(p.comprimento(), 1)
        mat = {'5052': 'Al5052-H32', '6061': 'Al6061-T6', 'pc': 'PC', 'uhmw': 'UHMW-PE',
               'aco': 'Aco-A36', 'inox': 'Inox-304', 'pu': 'PU-90ShA', 'borracha': 'NBR'}.get(p.mat, p.mat)
        ents.append(_texto(0, -12, 5, f'{p.item} {it["nome"]} - e={str(e).replace(".", ",")} mm - {mat}'))
        sem_acento = unicodedata.normalize('NFKD', it['nome'].lower()).encode('ascii', 'ignore').decode()
        slug = nomes.get(chave, f'{p.item}_' + re.sub(r'[^a-z0-9]+', '-', sem_acento).strip('-'))
        nome = f'{slug}_e{str(e).replace(".", ",")}_{mat}.dxf'
        (pasta / nome).write_text(_dxf(ents), encoding='ascii', errors='replace')
        lista.append(nome)
    leia = [f'Peças planas do caderno {DOC} — corte a laser/CNC',
            'Unidades: mm. Escala 1:1. Camadas: CORTE (contorno), FUROS, GRAVAR-NAO (identificação — não cortar).',
            'Quantidades e material: folhas 14 (Parte A) e 21 (Parte B); T-04 e os opcionais, folha 41.',
            'Peças esquerdas; as direitas são espelhadas (W-02, W-03, W-05, W-06, W-09, W-11, W-13:',
            '2 E + 2 D; K-01, M-02, E-01, E-02: mesma chapa virada).',
            '',
            'ATENÇÃO: DXF NÃO CARREGA TOLERÂNCIA. Toda cota com ajuste, planicidade, referência ou',
            'acabamento está nas folhas 28 a 31 e em revisao-h/usinagem.py. Cortar pelo DXF e usinar',
            'sem ler aquelas folhas produz peça fora de especificação nos furos de ajuste.',
            ''] + lista
    (pasta / 'LEIA-ME.txt').write_text('\n'.join(leia) + '\n', encoding='utf8')
    return lista


# --------------------------------------------------------------------- main
def main():
    SAIDA.mkdir(exist_ok=True)
    html_path = SAIDA / f'{DOC}.html'
    html_path.write_text(html_completo(), encoding='utf8')
    (SAIDA / 'artefato.html').write_text(html_artefato(), encoding='utf8')
    print('HTML:', html_path)
    dx = exporta_dxf()
    print(f'DXF: {len(dx)} arquivos em', SAIDA / 'dxf')
    if '--sem-pdf' in sys.argv:
        return
    saidas = [(html_path, SAIDA / f'{DOC}.pdf')]
    if '--so-completo' not in sys.argv:
        for letra, (a, b, sub) in PARTES.items():
            h = SAIDA / f'{DOC}-{letra}.html'
            h.write_text(html_completo((a, b), f'{sub} · folhas {a:02d} a {b:02d} de {len(TODAS)}'),
                         encoding='utf8')
            saidas.append((h, SAIDA / f'{DOC}-{letra}.pdf'))
    for (h, pdf) in saidas:
        if pdf.exists():
            pdf.unlink()
        ok = imprime_pdf(h, pdf)
        print('PDF:', pdf.name if ok else f'{pdf.name} falhou')
        if ok and h != html_path:      # o HTML das partes é intermediário; o do caderno completo fica
            h.unlink(missing_ok=True)


if __name__ == '__main__':
    main()
