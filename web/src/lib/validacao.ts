/**
 * Validação do Rover: o que a tela decide sobre ensaios e portões.
 *
 * O veredito é sempre o do servidor (recalculado com as amostras que o robô mandou);
 * a tela só mostra. Resultado simulado aparece marcado e não abre portão real.
 */
import type { Tone } from './labels'

export type Criterio = {
  nome: string
  valor: number | boolean | null
  limite: number | boolean | null
  op: string
  unidade: string
  ok: boolean
}

export type EnsaioResultado = {
  id: string
  ensaio: string
  fase: number
  origem: string
  status: string
  aprovado: boolean | null
  params: Record<string, unknown>
  criterios: Criterio[]
  medidas: Record<string, unknown>
  divergente: boolean
  simulado: boolean
  vale_portao: boolean
  observacao: string | null
  command_id: string | null
  created_at: string | null
}

export type ItemPortao = {
  ensaio: string
  rotulo: string
  situacao: 'aprovado' | 'reprovado' | 'faltando' | 'so_simulado'
  resultado_id: string | null
  quando: string | null
}

export type Portao = {
  fase: number
  titulo: string
  automatico: boolean
  aprovado: boolean | null
  itens: ItemPortao[]
  faltam?: string[]
  informativos: string[]
  nota?: string
}

export type DefinicaoEnsaio = {
  nome: string
  fase: number
  titulo: string
  origem: string
  no_portao: boolean
  limites: Record<string, { padrao: number | null; sentido: 'max' | 'min' }>
  parametros: Record<string, unknown>
  obrigatorios: string[]
}

const STATUS: Record<string, { label: string; tone: Tone }> = {
  aprovado: { label: 'Aprovado', tone: 'good' },
  reprovado: { label: 'Reprovado', tone: 'critical' },
  nao_avaliado: { label: 'Não avaliado', tone: 'warning' },
  cancelado: { label: 'Cancelado', tone: 'neutral' },
  erro: { label: 'Erro', tone: 'critical' },
}

export const statusEnsaio = (s: string) => STATUS[s] ?? { label: s, tone: 'neutral' as Tone }

const SITUACAO: Record<ItemPortao['situacao'], { label: string; tone: Tone }> = {
  aprovado: { label: 'Aprovado', tone: 'good' },
  reprovado: { label: 'Reprovado', tone: 'critical' },
  faltando: { label: 'Falta fazer', tone: 'neutral' },
  so_simulado: { label: 'Só simulado', tone: 'warning' },
}

export const situacaoItem = (s: ItemPortao['situacao']) => SITUACAO[s]

export function portaoInfo(p: Portao): { label: string; tone: Tone } {
  if (!p.automatico) return { label: 'Manual (guia)', tone: 'neutral' }
  return p.aprovado ? { label: 'Portão aberto', tone: 'good' } : { label: 'Portão fechado', tone: 'critical' }
}

/** "0,52 ms ≤ 100" — o critério como o operador lê. */
export function criterioTexto(c: Criterio): string {
  const num = (v: unknown) =>
    typeof v === 'number' ? v.toLocaleString('pt-BR', { maximumFractionDigits: 3 }) : String(v ?? '—')
  const op = c.op === '<=' ? '≤' : c.op === '>=' ? '≥' : '='
  const unidade = c.unidade ? ` ${c.unidade}` : ''
  return `${num(c.valor)}${unidade} ${op} ${num(c.limite)}`
}

/** Os parâmetros que o formulário mostra, com o padrão do catálogo (limites inclusos). */
export function camposDoEnsaio(d: DefinicaoEnsaio): { nome: string; padrao: unknown; limite?: 'max' | 'min'; obrigatorio: boolean }[] {
  const livres = Object.entries(d.parametros).map(([nome, padrao]) => ({
    nome,
    padrao,
    obrigatorio: d.obrigatorios.includes(nome),
  }))
  const limites = Object.entries(d.limites).map(([nome, l]) => ({
    nome,
    padrao: l.padrao,
    limite: l.sentido,
    obrigatorio: false,
  }))
  return [...livres, ...limites]
}

/**
 * O texto do formulário vira parâmetro: número, booleano, lista (`0.4, 0.4, 0.2, 0.2`) ou
 * texto. Vazio = usa o padrão (não vai no pedido).
 */
export function converteParametro(texto: string, padrao: unknown): unknown {
  const t = texto.trim()
  if (t === '') return undefined
  if (typeof padrao === 'boolean') return ['1', 'sim', 'true', 's'].includes(t.toLowerCase())
  if (Array.isArray(padrao)) return t.split(/[;,\s]+/).filter(Boolean).map((x) => Number(x.replace(',', '.')))
  const n = Number(t.replace(',', '.'))
  if (typeof padrao === 'number' || padrao === null) return Number.isFinite(n) ? n : t
  return t
}

/**
 * O nome da fase na tela. A FASE ENLACE (Parte 13) tem o número 6 no banco, mas é a
 * comunicação da fazenda: aparece como "ENLACE", não como "6".
 */
export const FASE_ENLACE = 6
export const rotuloFase = (fase: number): string => (fase === FASE_ENLACE ? 'ENLACE' : String(fase))

/** Limite que afrouxa o portão (o servidor recusaria): a tela avisa antes. */
export function afrouxa(valor: unknown, padrao: unknown, sentido?: 'max' | 'min'): boolean {
  if (typeof valor !== 'number' || typeof padrao !== 'number' || !sentido) return false
  return sentido === 'max' ? valor > padrao : valor < padrao
}

/** Fração do progresso como "42 %" (ou vazio). */
export const progressoTexto = (p?: { fracao?: number } | null) =>
  p && typeof p.fracao === 'number' ? `${Math.round(p.fracao * 100)} %` : ''
