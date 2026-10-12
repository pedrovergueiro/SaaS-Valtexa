"""Converte os documentos da Rev F (Markdown) em PDF, no padrão do caderno.

O projeto já imprime PDF a partir de HTML com o Edge em modo headless — é como saem as
27 folhas e os documentos do pacote de cotação. Este módulo usa o mesmo caminho para os
`.md` desta revisão, de modo que tudo o que vai para o engenheiro e para o fornecedor
chegue no mesmo formato.

O conversor de Markdown é próprio e curto. Não há `markdown` instalado, e trazer a
dependência para seis arquivos de texto com tabelas e listas custaria mais do que as
cento e poucas linhas abaixo — que cobrem exatamente o que estes documentos usam:
títulos, tabelas, listas, citação, código, negrito, itálico e regra horizontal.

```
python gerar_docs.py          # HTML + PDF de todos os .md desta pasta
python gerar_docs.py --html   # só HTML, sem abrir navegador
```
"""

from __future__ import annotations

import html as _html
import pathlib
import re
import shutil
import subprocess
import sys

AQUI = pathlib.Path(__file__).resolve().parent
SAIDA = AQUI / 'pdf'

CSS = """
@page { size: A4; margin: 18mm 16mm 16mm 16mm; }
* { box-sizing: border-box; }
body { font: 10.5pt/1.5 'Segoe UI', system-ui, sans-serif; color: #1a1a1a; margin: 0; }
h1 { font-size: 19pt; line-height: 1.25; margin: 0 0 4mm; color: #15402a;
     border-bottom: 2.4pt solid #1f6b3a; padding-bottom: 2.5mm; }
h2 { font-size: 13.5pt; margin: 9mm 0 3mm; color: #1f6b3a; page-break-after: avoid;
     border-bottom: .6pt solid #cfd8d2; padding-bottom: 1.5mm; }
h3 { font-size: 11.5pt; margin: 6mm 0 2mm; color: #15402a; page-break-after: avoid; }
p { margin: 0 0 2.8mm; }
ul, ol { margin: 0 0 3mm; padding-left: 6mm; }
li { margin-bottom: 1.2mm; }
table { border-collapse: collapse; width: 100%; margin: 2mm 0 4mm;
        font-size: 9pt; page-break-inside: avoid; }
th { background: #1f6b3a; color: #fff; text-align: left; padding: 1.6mm 2mm;
     font-weight: 600; font-size: 8.6pt; }
td { border-bottom: .4pt solid #dde3df; padding: 1.5mm 2mm; vertical-align: top; }
tr:nth-child(even) td { background: #f6f8f7; }
code { font: 9pt 'Cascadia Mono', Consolas, monospace; background: #eef2ef;
       padding: .3mm 1mm; border-radius: 1mm; }
pre { background: #f4f6f5; border-left: 2.5pt solid #1f6b3a; padding: 2.5mm 3mm;
      margin: 2mm 0 4mm; overflow-x: auto; page-break-inside: avoid; }
pre code { background: none; padding: 0; font-size: 8.6pt; line-height: 1.45; }
blockquote { border-left: 2.5pt solid #c9a227; background: #fdf9ec; margin: 2mm 0 4mm;
             padding: 2mm 3mm; }
blockquote p { margin: 0; }
hr { border: 0; border-top: .6pt solid #cfd8d2; margin: 6mm 0; }
strong { font-weight: 650; color: #0d2b1c; }
.rodape { margin-top: 8mm; padding-top: 2.5mm; border-top: .6pt solid #cfd8d2;
          font-size: 8pt; color: #6a7570; }
"""


# ------------------------------------------------------------------ inline
def _inline(t: str) -> str:
    """Negrito, itálico, código e links, já com o texto escapado."""
    t = _html.escape(t)
    t = re.sub(r'`([^`]+)`', r'<code>\1</code>', t)
    t = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', t)
    t = re.sub(r'(?<![\w*])\*([^*\n]+)\*(?![\w*])', r'<em>\1</em>', t)
    t = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', t)
    return t


def _celulas(linha: str) -> list[str]:
    return [c.strip() for c in linha.strip().strip('|').split('|')]


def md_para_html(md: str) -> str:
    """O subconjunto de Markdown que estes documentos usam."""
    linhas = md.split('\n')
    out: list[str] = []
    i = 0
    lista: str | None = None

    def fecha_lista():
        nonlocal lista
        if lista:
            out.append(f'</{lista}>')
            lista = None

    while i < len(linhas):
        ln = linhas[i]

        # bloco de código
        if ln.startswith('```'):
            fecha_lista()
            i += 1
            buf = []
            while i < len(linhas) and not linhas[i].startswith('```'):
                buf.append(_html.escape(linhas[i]))
                i += 1
            out.append('<pre><code>' + '\n'.join(buf) + '</code></pre>')
            i += 1
            continue

        # tabela: linha com | seguida de separador |---|
        if (ln.strip().startswith('|') and i + 1 < len(linhas)
                and re.match(r'^\s*\|[\s:\-|]+\|\s*$', linhas[i + 1])):
            fecha_lista()
            cab = _celulas(ln)
            i += 2
            corpo = []
            while i < len(linhas) and linhas[i].strip().startswith('|'):
                corpo.append(_celulas(linhas[i]))
                i += 1
            th = ''.join(f'<th>{_inline(c)}</th>' for c in cab)
            trs = ''.join(
                '<tr>' + ''.join(f'<td>{_inline(c)}</td>' for c in linha) + '</tr>'
                for linha in corpo)
            out.append(f'<table><thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table>')
            continue

        # títulos
        m = re.match(r'^(#{1,4})\s+(.*)$', ln)
        if m:
            fecha_lista()
            n = len(m.group(1))
            out.append(f'<h{n}>{_inline(m.group(2))}</h{n}>')
            i += 1
            continue

        # regra horizontal
        if re.match(r'^\s*---+\s*$', ln):
            fecha_lista()
            out.append('<hr>')
            i += 1
            continue

        # citação
        if ln.startswith('>'):
            fecha_lista()
            buf = []
            while i < len(linhas) and linhas[i].startswith('>'):
                buf.append(linhas[i].lstrip('>').strip())
                i += 1
            out.append('<blockquote><p>' + _inline(' '.join(buf)) + '</p></blockquote>')
            continue

        # listas
        m = re.match(r'^\s*([-*])\s+(.*)$', ln)
        if m:
            if lista != 'ul':
                fecha_lista()
                out.append('<ul>')
                lista = 'ul'
            out.append(f'<li>{_inline(m.group(2))}</li>')
            i += 1
            continue
        m = re.match(r'^\s*(\d+)\.\s+(.*)$', ln)
        if m:
            if lista != 'ol':
                fecha_lista()
                out.append('<ol>')
                lista = 'ol'
            out.append(f'<li>{_inline(m.group(2))}</li>')
            i += 1
            continue

        # parágrafo
        if ln.strip():
            fecha_lista()
            buf = [ln.strip()]
            i += 1
            while (i < len(linhas) and linhas[i].strip()
                   and not re.match(r'^\s*([-*]|\d+\.|#{1,4}\s|>|\||```|---+\s*$)', linhas[i])):
                buf.append(linhas[i].strip())
                i += 1
            out.append('<p>' + _inline(' '.join(buf)) + '</p>')
            continue

        fecha_lista()
        i += 1

    fecha_lista()
    return '\n'.join(out)


def pagina(titulo: str, corpo: str, origem: str) -> str:
    return (
        '<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">'
        f'<title>{_html.escape(titulo)}</title><style>{CSS}</style></head><body>'
        f'{corpo}'
        f'<div class="rodape">VALTEXA · Rover V4 · Revisão H · gerado de <code>{origem}</code>'
        ' · EMITIDO PARA COTAÇÃO E VALIDAÇÃO</div>'
        '</body></html>')


# --------------------------------------------------------------------- PDF
def navegador() -> str | None:
    for p in (r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
              r'C:\Program Files\Microsoft\Edge\Application\msedge.exe',
              r'C:\Program Files\Google\Chrome\Application\chrome.exe',
              shutil.which('msedge') or '', shutil.which('google-chrome') or ''):
        if p and pathlib.Path(p).exists():
            return p
    return None


def imprime(html_path: pathlib.Path, pdf_path: pathlib.Path) -> bool:
    exe = navegador()
    if not exe:
        print('aviso: Edge/Chrome não encontrado — abra o HTML e use Ctrl+P.')
        return False
    perfil = SAIDA / '.perfil'
    subprocess.run(
        [exe, '--headless=new', '--disable-gpu', '--no-first-run', '--no-pdf-header-footer',
         f'--user-data-dir={perfil}', '--virtual-time-budget=15000',
         f'--print-to-pdf={pdf_path}', html_path.as_uri()],
        check=False, capture_output=True, timeout=180)
    shutil.rmtree(perfil, ignore_errors=True)
    return pdf_path.exists()


def main(so_html: bool = False) -> None:
    SAIDA.mkdir(exist_ok=True)
    fontes = sorted(AQUI.glob('*.md'))
    if not fontes:
        print('nenhum .md nesta pasta')
        return
    for md in fontes:
        texto = md.read_text(encoding='utf-8')
        m = re.search(r'^#\s+(.*)$', texto, re.M)
        titulo = m.group(1) if m else md.stem
        html_path = SAIDA / (md.stem + '.html')
        html_path.write_text(pagina(titulo, md_para_html(texto), md.name), encoding='utf-8')
        if so_html:
            print(f'  HTML: {html_path.name}')
            continue
        pdf_path = SAIDA / (md.stem + '.pdf')
        ok = imprime(html_path, pdf_path)
        kb = pdf_path.stat().st_size / 1024 if ok else 0
        print(f"  {'PDF ' if ok else 'FALHOU'} {md.stem + '.pdf':46} {kb:7.0f} KB")
    print(f'\nem: {SAIDA}')


if __name__ == '__main__':
    main(so_html='--html' in sys.argv)
