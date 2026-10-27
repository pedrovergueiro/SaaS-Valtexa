/**
 * O agrônomo ensinando a IA: a lesão marcada na foto, o porquê e o painel do que ela aprendeu.
 * As caixas vão normalizadas em [0, 1] (largura e altura da foto), como a plataforma guarda.
 */

export type Caixa = { x: number; y: number; w: number; h: number }

export type Explicacao = {
  sintomas: string[]
  estrato: 'terco_inferior' | 'terco_medio' | 'terco_superior' | 'indeterminado' | null
  face: 'adaxial' | 'abaxial' | 'ambas' | 'indeterminada' | null
  porque: string
}

export const EXPLICACAO_VAZIA: Explicacao = { sintomas: [], estrato: null, face: null, porque: '' }

export const ESTRATOS: [Explicacao['estrato'] & string, string][] = [
  ['terco_inferior', 'Terço inferior'],
  ['terco_medio', 'Terço médio'],
  ['terco_superior', 'Terço superior'],
  ['indeterminado', 'Não dá para dizer'],
]

export const FACES: [Explicacao['face'] & string, string][] = [
  ['abaxial', 'Face de baixo'],
  ['adaxial', 'Face de cima'],
  ['ambas', 'As duas'],
  ['indeterminada', 'Não dá para dizer'],
]

export const MAX_LESOES = 20
const LADO_MINIMO = 0.01

const limita = (v: number) => Math.min(1, Math.max(0, v))

/** A caixa do arraste entre dois pontos (já normalizados), dentro da foto; pequena demais = null. */
export function caixaDoArraste(a: { x: number; y: number }, b: { x: number; y: number }): Caixa | null {
  const x0 = limita(Math.min(a.x, b.x))
  const y0 = limita(Math.min(a.y, b.y))
  const x1 = limita(Math.max(a.x, b.x))
  const y1 = limita(Math.max(a.y, b.y))
  if (x1 - x0 < LADO_MINIMO || y1 - y0 < LADO_MINIMO) return null
  const r = (v: number) => Math.round(v * 1e5) / 1e5
  return { x: r(x0), y: r(y0), w: r(x1 - x0), h: r(y1 - y0) }
}

/** O ponto do evento, normalizado pelo retângulo da foto na tela. */
export function pontoNormalizado(clientX: number, clientY: number, rect: { left: number; top: number; width: number; height: number }) {
  return { x: limita((clientX - rect.left) / rect.width), y: limita((clientY - rect.top) / rect.height) }
}

/** O que vai no corpo da revisão: só o que ele disse (nada vazio vira explicação). */
export function corpoDaExplicacao(e: Explicacao): Explicacao | null {
  const porque = e.porque.trim()
  if (!e.sintomas.length && !e.estrato && !e.face && !porque) return null
  return { ...e, porque }
}

export type Painel = {
  licoes: number
  com_porque: number
  com_lesao_marcada: number
  lesoes_marcadas: number
  por_rotulo: Record<string, number>
  onde_a_ia_mais_erra: { ia_dizia: string; voce_disse: string; vezes: number }[]
  acerto_da_ia_por_mes: { mes: string; casos: number; ia_acertou: number; taxa: number }[]
  classes_novas: { rotulo: string; exemplos: number; faltam: number }[]
  alvo_por_classe_nova: number
  ultimas: {
    id: string
    origem: 'fila' | 'parecer'
    quando: string
    rotulo: string
    rotulo_da_ia: string | null
    sintomas: string[]
    porque: string | null
    lesoes: number
    autor: string
  }[]
  vies: string
  confiabilidade?: { pares: number; concordancias: number; indice: number | null }
}

/** A tendência do acerto: o último mês contra o primeiro (com pelo menos 5 casos cada). */
export function tendencia(meses: Painel['acerto_da_ia_por_mes']): number | null {
  const validos = meses.filter((m) => m.casos >= 5)
  const primeiro = validos[0]
  const ultimo = validos[validos.length - 1]
  if (validos.length < 2 || !primeiro || !ultimo) return null
  return Math.round((ultimo.taxa - primeiro.taxa) * 1000) / 1000
}

export type Pendente = {
  amostra_id: string
  observation_id: string | null
  rotulo: string
  rotulo_da_maquina: string | null
  autor: string | null
  em_disputa: boolean
  opinioes: number
  sintomas: string[]
  porque: string | null
  lesoes: number[][]
}

export type Veredito = 'sustentada' | 'contrariada' | 'nao_mostrada' | 'poucos_dados' | 'nao_medida'

export type Regra = {
  id: string
  autor: string
  cultura: string
  doenca: string
  texto: string
  condicao_texto: string
  efeito: 'aumenta' | 'diminui'
  ativa: boolean
  veredito_texto: string
  medida: {
    veredito?: Veredito
    p_valor?: number | null
    com_condicao?: { casos: number; com_doenca: number }
    sem_condicao?: { casos: number; com_doenca: number }
  }
}

export type RegraForm = {
  cultura: string
  doenca: string
  texto: string
  variavel: 'chuva_mm' | 'molhamento_h' | 'ur_media' | 't_media' | 'mes'
  janela: string
  operador: '<' | '>'
  valor: string
  meses: string
  efeito: 'aumenta' | 'diminui'
}

/** A condição como a plataforma mede: mês do ano, ou a variável de clima numa janela. */
export function condicaoDoFormulario(f: RegraForm): Record<string, unknown> {
  if (f.variavel === 'mes') {
    return { variavel: 'mes', meses: f.meses.split(/[,\s]+/).filter(Boolean).map(Number) }
  }
  return { variavel: f.variavel, janela_dias: Number(f.janela), operador: f.operador, valor: Number(f.valor.replace(',', '.')) }
}

export function tomDoVeredito(v: Veredito | undefined): 'good' | 'critical' | 'neutral' | 'warning' {
  return v === 'sustentada' ? 'good' : v === 'contrariada' ? 'critical' : v === 'nao_mostrada' ? 'warning' : 'neutral'
}
