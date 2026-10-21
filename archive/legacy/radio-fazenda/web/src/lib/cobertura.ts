/**
 * Mapa de cobertura do rádio da fazenda (o levantamento da base, por talhão).
 *
 * A grade vem da análise do VALTEXA-BASE (``valtexa_base.levantamento``): célula ``"i,j"``
 * de ``celula_m`` metros, ``i`` para leste e ``j`` para norte a partir da ``origem``. Aqui só
 * a conta para desenhar: norte para cima (no SVG o y cresce para baixo).
 */

export type ClasseDeCelula = 'bom' | 'marginal' | 'morto'

export type ZonaMortaMapa = {
  id: number
  celulas: [number, number][]
  centro: [number, number]
  area_m2: number
}

export type RepetidoraSugerida = {
  ordem?: number
  lat?: number
  lon?: number
  celula?: [number, number]
  ganho_amostras?: number
  ganho_fracao?: number
  celulas_mortas_cobertas?: number
  confianca?: string
  explicacao?: string
}

export type MapaCobertura = {
  versao: number
  origem: [number, number]
  celula_m: number
  celulas: Record<string, ClasseDeCelula>
  zonas_mortas: ZonaMortaMapa[]
  repetidoras: RepetidoraSugerida[]
  contagem?: Record<ClasseDeCelula, number>
  amostras?: number | null
  fracao_morta_coberta?: number | null
}

export type CelulaDesenhada = { i: number; j: number; x: number; y: number; classe: ClasseDeCelula }

export type Grade = {
  celulas: CelulaDesenhada[]
  colunas: number
  linhas: number
  /** Posição (coluna, linha) no desenho de uma célula da grade, ou ``null`` fora dela. */
  posicao: (i: number, j: number) => { x: number; y: number } | null
  largura_m: number
  altura_m: number
}

export function grade(mapa: MapaCobertura): Grade {
  const chaves = Object.entries(mapa.celulas).flatMap(([k, classe]) => {
    const m = /^(-?\d+),(-?\d+)$/.exec(k)
    return m ? [{ i: Number(m[1]), j: Number(m[2]), classe }] : []
  })
  if (chaves.length === 0) {
    return { celulas: [], colunas: 0, linhas: 0, posicao: () => null, largura_m: 0, altura_m: 0 }
  }
  const is = chaves.map((c) => c.i)
  const js = chaves.map((c) => c.j)
  const minI = Math.min(...is)
  const maxI = Math.max(...is)
  const minJ = Math.min(...js)
  const maxJ = Math.max(...js)
  const colunas = maxI - minI + 1
  const linhas = maxJ - minJ + 1
  const posicao = (i: number, j: number) =>
    i < minI || i > maxI || j < minJ || j > maxJ ? null : { x: i - minI, y: maxJ - j }
  return {
    celulas: chaves.map((c) => ({ ...c, ...posicao(c.i, c.j)! })),
    colunas,
    linhas,
    posicao,
    largura_m: colunas * mapa.celula_m,
    altura_m: linhas * mapa.celula_m,
  }
}

export function contagem(mapa: MapaCobertura): Record<ClasseDeCelula, number> {
  const c: Record<ClasseDeCelula, number> = { bom: 0, marginal: 0, morto: 0 }
  for (const v of Object.values(mapa.celulas)) if (v in c) c[v] += 1
  return c
}

/** Fração da área medida em cada classe (0–1). */
export function fracoes(mapa: MapaCobertura): Record<ClasseDeCelula, number> {
  const c = contagem(mapa)
  const total = c.bom + c.marginal + c.morto
  if (total === 0) return { bom: 0, marginal: 0, morto: 0 }
  return { bom: c.bom / total, marginal: c.marginal / total, morto: c.morto / total }
}

export const COR_DA_CLASSE: Record<ClasseDeCelula, string> = {
  bom: 'var(--color-good, #16a34a)',
  marginal: 'var(--color-warning, #d97706)',
  morto: 'var(--color-critical, #dc2626)',
}

export const ROTULO_DA_CLASSE: Record<ClasseDeCelula, string> = {
  bom: 'enlace bom',
  marginal: 'marginal',
  morto: 'zona morta',
}

/** Área (m²) de uma contagem de células. */
export function area_m2(mapa: MapaCobertura, celulas: number): number {
  return celulas * mapa.celula_m * mapa.celula_m
}
