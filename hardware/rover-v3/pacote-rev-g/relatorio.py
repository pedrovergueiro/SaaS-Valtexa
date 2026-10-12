"""Motor de documentos A4 do pacote Rev E: monta HTML e imprime em PDF pelo Edge/Chrome.

Reaproveita as fontes embutidas e o impressor do caderno de desenhos (../chassi-gaiola).
"""
import html
import pathlib
import sys

AQUI = pathlib.Path(__file__).resolve().parent
CG = AQUI.parent / 'chassi-gaiola'
sys.path.insert(0, str(CG))

from gerar import fontes_embutidas, imprime_pdf  # noqa: E402

CAT = {
    'CONFIRMADO': ('c-conf', 'presente na baseline Rev E ou no caderno VTX-RV3-CG-G'),
    'DERIVADO': ('c-der', 'calculado a partir de valores confirmados'),
    'PROPOSTA': ('c-prop', 'escolha de engenharia deste pacote, a aprovar'),
    'A DEFINIR': ('c-def', 'ausente — depende de engenheiro, fabricante ou ensaio'),
    'PESQUISA': ('c-pesq', 'dado obtido em pesquisa de mercado, a confirmar com o fornecedor'),
}


def cat(nome):
    cls = CAT.get(nome, ('c-def', ''))[0]
    return f'<span class="cat {cls}">{nome}</span>'


def esc(s):
    return html.escape(str(s), quote=False)


class Doc:
    """Documento A4 em HTML, com capa, sumário automático e blocos de conteúdo."""

    def __init__(self, titulo, subtitulo, ident, rev='E', data='21/09/2026', status=None):
        self.meta = dict(titulo=titulo, subtitulo=subtitulo, ident=ident, rev=rev, data=data,
                         status=status or 'DOCUMENTO PARA ENGENHARIA E ORÇAMENTO')
        self.blocos = []
        self.secoes = []

    # ------------------------------------------------------------- blocos
    def h1(self, txt, num=None):
        n = len(self.secoes) + 1 if num is None else num
        ident = f'sec{n}'
        self.secoes.append((n, txt, ident))
        self.blocos.append(f'<h1 id="{ident}"><span class="num">{n}</span>{esc(txt)}</h1>')
        return self

    def h2(self, txt):
        self.blocos.append(f'<h2>{esc(txt)}</h2>')
        return self

    def h3(self, txt):
        self.blocos.append(f'<h3>{esc(txt)}</h3>')
        return self

    def p(self, txt, cls=''):
        c = f' class="{cls}"' if cls else ''
        self.blocos.append(f'<p{c}>{txt}</p>')
        return self

    def nota(self, txt):
        return self.p(txt, 'nota')

    def alerta(self, txt):
        return self.p(txt, 'alerta')

    def lista(self, itens, ordenada=False):
        tag = 'ol' if ordenada else 'ul'
        li = ''.join(f'<li>{i}</li>' for i in itens)
        self.blocos.append(f'<{tag}>{li}</{tag}>')
        return self

    def tabela(self, cabecalho, linhas, larguras=None, cls='', titulo=None):
        h = []
        if titulo:
            h.append(f'<p class="tabtit">{esc(titulo)}</p>')
        h.append(f'<table class="tab {cls}">')
        if larguras:
            h.append('<colgroup>' + ''.join(f'<col style="width:{w}%">' for w in larguras) + '</colgroup>')
        h.append('<thead><tr>' + ''.join(f'<th>{c}</th>' for c in cabecalho) + '</tr></thead><tbody>')
        for l in linhas:
            if isinstance(l, str):
                h.append(l)
            else:
                h.append('<tr>' + ''.join(f'<td>{c}</td>' for c in l) + '</tr>')
        h.append('</tbody></table>')
        self.blocos.append(''.join(h))
        return self

    def campos(self, pares):
        linhas = ''.join(f'<div><span>{esc(k)}</span>{v}</div>' for k, v in pares)
        self.blocos.append(f'<div class="campos">{linhas}</div>')
        return self

    def assinatura(self, papeis):
        linhas = ''.join(f'<div><b>{esc(p)}</b><span class="linha"></span>'
                         '<small>Nome · documento · data</small></div>' for p in papeis)
        self.blocos.append(f'<div class="assin">{linhas}</div>')
        return self

    def quebra(self):
        self.blocos.append('<div class="quebra"></div>')
        return self

    def fluxo(self, etapas):
        itens = ''.join(f'<li><span>{i + 1}</span>{esc(e)}</li>' for i, e in enumerate(etapas))
        self.blocos.append(f'<ol class="fluxo">{itens}</ol>')
        return self

    # -------------------------------------------------------------- saída
    def _capa(self):
        m = self.meta
        return f'''<section class="capa">
<div class="marca"><b>VALTEXA</b><span>ROVER V3 · ENGENHARIA</span></div>
<h1 class="tit">{esc(m["titulo"])}</h1>
<p class="sub">{esc(m["subtitulo"])}</p>
<div class="selo">{esc(m["status"])}</div>
<table class="tab capa-info"><tbody>
<tr><td>Documento</td><td><b>{esc(m["ident"])}</b></td></tr>
<tr><td>Revisão · data</td><td>{esc(m["rev"])} · {esc(m["data"])}</td></tr>
<tr><td>Base técnica</td><td>VTX-RV3-BASELINE-E (Rev E) · VTX-RV3-CG-G (27 folhas A3)</td></tr>
<tr><td>Emitido por</td><td>ValTexa Engenharia</td></tr>
</tbody></table>
<div class="legenda-cat">
<p><b>Como ler as etiquetas de origem</b></p>
{''.join(f'<p>{cat(k)}<span>{esc(v[1])}</span></p>' for k, v in CAT.items())}
</div>
</section>'''

    def _sumario(self):
        if not self.secoes:
            return ''
        li = ''.join(f'<li><span>{n}</span>{esc(t)}</li>' for n, t, _ in self.secoes)
        return f'<section class="sumario"><h2>Sumário</h2><ol>{li}</ol></section><div class="quebra"></div>'

    def html(self):
        css = (AQUI / 'estilo-relatorio.css').read_text(encoding='utf8')
        m = self.meta
        rodape = (f'<div class="rodape"><span>{esc(m["ident"])} · rev. {esc(m["rev"])}</span>'
                  f'<span>ValTexa · Rover V3</span></div>')
        return (f'<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">'
                f'<title>{esc(m["titulo"])}</title>'
                f'<style>{fontes_embutidas()}\n{css}</style></head><body>'
                f'{self._capa()}<div class="quebra"></div>{self._sumario()}'
                f'<main>{"".join(self.blocos)}</main>{rodape}</body></html>')

    def salva(self, destino, pdf=True, manter_html=False):
        destino = pathlib.Path(destino)
        destino.parent.mkdir(parents=True, exist_ok=True)
        html_path = destino.with_suffix('.html')
        html_path.write_text(self.html(), encoding='utf8')
        if pdf:
            pdf_path = destino.with_suffix('.pdf')
            if pdf_path.exists():
                pdf_path.unlink()
            ok = imprime_pdf(html_path, pdf_path)
            if ok and not manter_html:      # HTML é só o caminho até o PDF
                html_path.unlink(missing_ok=True)
            return pdf_path if ok else html_path
        return html_path
