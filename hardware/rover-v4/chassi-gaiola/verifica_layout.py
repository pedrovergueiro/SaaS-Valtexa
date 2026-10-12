"""Confere o layout de cada folha MEDINDO o que o navegador desenhou — não estimando.

Existem dois tipos de defeito que o gerador, sozinho, não vê:

* **texto sobre texto**: um bloco de notas que cresce e passa por cima de uma tabela, um
  título de vista que cai sobre o desenho, o selo de revisão que estoura a célula do
  carimbo. O gerador posiciona cada coisa por coordenada e não sabe o quanto o texto ocupa;
* **linha sobre texto**: a chamada que atravessa o parágrafo para chegar ao desenho. Esta
  é conferida por `/tmp/checa_folha.py` na geração do SVG; aqui entra só o que se mede no
  navegador.

O método é o mais simples que funciona: abre cada folha no Edge/Chrome sem janela, pede ao
navegador o retângulo de CADA linha de texto (blocos HTML e textos do SVG) e compara os
retângulos entre si. Qualquer par que se interseca mais de 0,8 mm² é um defeito.

```
python verifica_layout.py              # as 42 folhas
python verifica_layout.py 2 18 22      # só essas
```
Sai com código 1 se achar defeito — serve de portão antes de entregar o caderno.
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
import gerar  # noqa: E402

MOLDURA = (25.0, 7.0, 413.0, 290.0)
CARIMBO = (235.0, 238.0, 413.0, 290.0)
TOL_AREA = 0.8          # mm² de interseção abaixo dos quais não se reclama

SCRIPT = r'''<script>
window.addEventListener('load', async function () {
  try { await document.fonts.ready; } catch (e) {}
  setTimeout(function () {
    var mm = 96 / 25.4, out = {};
    document.querySelectorAll('section.folha').forEach(function (sec) {
      var sr = sec.getBoundingClientRect();
      function R(r) { return [(r.left - sr.left) / mm, (r.top - sr.top) / mm,
                              (r.right - sr.left) / mm, (r.bottom - sr.top) / mm]; }
      var linhas = [], textos = [], estouro = [];
      sec.querySelectorAll('.bl').forEach(function (bl, bi) {
        var w = document.createTreeWalker(bl, NodeFilter.SHOW_TEXT), n;
        while ((n = w.nextNode())) {
          if (!n.textContent.trim()) continue;
          var rg = document.createRange(); rg.selectNodeContents(n);
          var rs = rg.getClientRects();
          for (var i = 0; i < rs.length; i++) {
            if (rs[i].width < 0.5 || rs[i].height < 0.5) continue;
            linhas.push({b: bi, r: R(rs[i]), t: n.textContent.trim().slice(0, 36)});
          }
        }
        if (bl.style.height && bl.scrollHeight > bl.clientHeight + 1)
          estouro.push({b: bi, t: bl.textContent.trim().slice(0, 36),
                        extra: (bl.scrollHeight - bl.clientHeight) / mm});
      });
      sec.querySelectorAll('svg.desenho text').forEach(function (t) {
        var rc = t.getBoundingClientRect();
        if (rc.width < 0.2 || !t.textContent.trim()) return;
        textos.push({r: R(rc), t: t.textContent.trim().slice(0, 36)});
      });
      out[sec.id] = {linhas: linhas, textos: textos, estouro: estouro};
    });
    document.body.textContent = '@@' + JSON.stringify(out) + '@@';
  }, 400);
});
</script>'''


def _interseccao(a, b):
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    return w * h if w > 0 and h > 0 else 0.0


def _dentro(r, caixa, folga=0.3):
    return (r[0] >= caixa[0] - folga and r[1] >= caixa[1] - folga
            and r[2] <= caixa[2] + folga and r[3] <= caixa[3] + folga)


def medir(numeros):
    """Devolve {id_da_folha: dados medidos} para as folhas pedidas."""
    exe = gerar.navegador()
    if not exe:
        raise SystemExit('Edge/Chrome não encontrado — não há como medir o layout.')
    pasta = AQUI / 'saida' / '.layout'
    pasta.mkdir(parents=True, exist_ok=True)
    out = {}
    # uma folha por vez: o --dump-dom de 42 folhas juntas passa do tempo virtual
    for n in numeros:
        h = pasta / f'f{n:02d}.html'
        h.write_text(gerar.html_completo((n, n)).replace('</body>', SCRIPT + '</body>'), encoding='utf8')
        perfil = pasta / '.perfil'
        r = subprocess.run([exe, '--headless=new', '--disable-gpu', '--no-first-run',
                            f'--user-data-dir={perfil}', '--virtual-time-budget=20000',
                            '--window-size=1700,1300', '--dump-dom', h.as_uri()],
                           capture_output=True, timeout=180)
        shutil.rmtree(perfil, ignore_errors=True)
        m = re.search(r'@@(.*?)@@', r.stdout.decode('utf8', 'replace'), re.S)
        if not m:
            out[f'f{n:02d}'] = None
            continue
        out.update(json.loads(m.group(1)))
    shutil.rmtree(pasta, ignore_errors=True)
    return out


def _segmentos(svg):
    """Segmentos retos do SVG de uma folha: <line> e as arestas de polyline/polygon."""
    seg = []
    for m in re.finditer(r'<line x1="([-\d.]+)" y1="([-\d.]+)" x2="([-\d.]+)" y2="([-\d.]+)"', svg):
        a = list(map(float, m.groups()))
        seg.append((a[0], a[1], a[2], a[3]))
    for m in re.finditer(r'<(polyline|polygon)[^>]*?points="([^"]+)"', svg):
        pts = [tuple(map(float, q)) for q in re.findall(r'(-?\d+\.?\d*)[ ,](-?\d+\.?\d*)', m.group(2))]
        fecha = m.group(1) == 'polygon'
        for i in range(len(pts) - (0 if fecha else 1)):
            p, q = pts[i], pts[(i + 1) % len(pts)]
            seg.append((p[0], p[1], q[0], q[1]))
    return seg


def _corta(seg, r):
    """O segmento atravessa o INTERIOR do retângulo r (encostar na borda não conta)?"""
    x0, y0, x1, y1 = seg
    # Liang-Barsky contra o retângulo encolhido
    xa, ya, xb, yb = r
    dx, dy = x1 - x0, y1 - y0
    t0, t1 = 0.0, 1.0
    for p, q in ((-dx, x0 - xa), (dx, xb - x0), (-dy, y0 - ya), (dy, yb - y0)):
        if abs(p) < 1e-12:
            if q < 0:
                return False
        else:
            t = q / p
            if p < 0:
                t0 = max(t0, t)
            else:
                t1 = min(t1, t)
    return t1 - t0 > 0.12 and (dx * dx + dy * dy) ** 0.5 * (t1 - t0) > 0.8


def linhas_sobre_texto(svg, textos):
    """Textos do desenho cortados por linhas do desenho. Devolve [(texto, n_cortes, zona)]."""
    seg = [s for s in _segmentos(svg)
           if not (-16 <= s[0] <= 16 and -12 <= s[1] <= 1)]      # marcadores de seta (coord. locais)
    out = []
    for t in textos:
        r = t['r']
        if len(t['t']) <= 1 or _dentro(r, CARIMBO, 0.5):
            continue
        enc = (r[0] + 0.5, r[1] + 0.6, r[2] - 0.5, r[3] - 0.6)    # encolhe: tolera o encostar
        if enc[2] <= enc[0] or enc[3] <= enc[1]:
            continue
        n = sum(1 for s in seg if _corta(s, enc))
        if n:
            out.append((t['t'], n, f'X {r[0]:.0f}–{r[2]:.0f} Y {r[1]:.0f}–{r[3]:.0f}'))
    return out


def defeitos(dado, svg=None):
    """Lista de textos que descrevem cada defeito de uma folha medida."""
    ach = []
    linhas, textos = dado['linhas'], dado['textos']

    def zona(r):
        return f'X {r[0]:.0f}–{r[2]:.0f} Y {r[1]:.0f}–{r[3]:.0f}'

    # 1) blocos HTML: uma linha de um bloco sobre uma linha de outro
    visto = set()
    for i, a in enumerate(linhas):
        for b in linhas[i + 1:]:
            if a['b'] == b['b']:
                continue
            if _interseccao(a['r'], b['r']) > TOL_AREA:
                chave = (a['b'], b['b'])
                if chave in visto:
                    continue
                visto.add(chave)
                ach.append(f'texto sobre texto — bloco {a["b"]} "{a["t"]}" × bloco {b["b"]} '
                           f'"{b["t"]}" ({zona(a["r"])})')
    # 2) bloco HTML sobre texto do desenho
    visto = set()
    for a in linhas:
        for t in textos:
            if _interseccao(a['r'], t['r']) > TOL_AREA and not _dentro(t['r'], CARIMBO, 0.5):
                chave = (a['b'], t['t'])
                if chave in visto:
                    continue
                visto.add(chave)
                ach.append(f'bloco {a["b"]} "{a["t"]}" sobre o texto do desenho "{t["t"]}" '
                           f'({zona(t["r"])})')
    # 3) texto do desenho sobre texto do desenho
    visto = set()
    for i, a in enumerate(textos):
        for b in textos[i + 1:]:
            if _interseccao(a['r'], b['r']) > TOL_AREA:
                chave = tuple(sorted((a['t'], b['t'])))
                if chave in visto:
                    continue
                visto.add(chave)
                ach.append(f'desenho: "{a["t"]}" × "{b["t"]}" ({zona(a["r"])})')
    # 4) fora da moldura / dentro do carimbo
    for t in textos:
        r = t['r']
        if len(t['t']) <= 1:                        # letras e números de zona da moldura
            continue
        if not _dentro(r, (0.0, 0.0, 420.0, 297.0), 0.0) or (
                r[2] > MOLDURA[2] + 0.3 and r[1] < MOLDURA[3]) or r[3] > MOLDURA[3] + 0.3:
            ach.append(f'texto fora da moldura: "{t["t"]}" ({zona(r)})')
    for a in linhas:
        r = a['r']
        if r[2] > MOLDURA[2] + 0.3 or r[3] > MOLDURA[3] + 0.3:
            ach.append(f'bloco {a["b"]} "{a["t"]}" passa da moldura ({zona(r)})')
        elif _interseccao(r, CARIMBO) > TOL_AREA:
            ach.append(f'bloco {a["b"]} "{a["t"]}" entra no carimbo ({zona(r)})')
    if svg is not None:
        for (t, n, z) in linhas_sobre_texto(svg, textos):
            ach.append(f'linha do desenho corta o texto "{t}" ({n} corte(s), {z})')
    for e in dado['estouro']:
        ach.append(f'bloco {e["b"]} "{e["t"]}" estoura a própria altura em {e["extra"]:.0f} mm')
    return ach


def main(argv):
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    total = len(gerar.TODAS)
    numeros = [int(a) for a in argv] or list(range(1, total + 1))
    medido = medir(numeros)
    n_defeitos = 0
    for n in numeros:
        d = medido.get(f'f{n:02d}')
        if d is None:
            print(f'folha {n:02d}: NÃO FOI POSSÍVEL MEDIR')
            n_defeitos += 1
            continue
        ach = defeitos(d, str(gerar.TODAS[n - 1]().s))
        if ach:
            n_defeitos += len(ach)
            print(f'folha {n:02d}: {len(ach)} defeito(s)')
            for a in ach[:12]:
                print('    ' + a)
            if len(ach) > 12:
                print(f'    ... e mais {len(ach) - 12}')
    print(f'\n{len(numeros)} folha(s) medida(s), {n_defeitos} defeito(s)')
    return 1 if n_defeitos else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
