import type { Tone } from '@/lib/labels'

/** Planejamento de apoio à decisão (rodada 4, 8.3): tipos e regras puras da tela. */

export type TipoPlano = 'fitossanitario' | 'robotico' | 'insumos'
export type OrigemPremissa = 'padrao' | 'pedido' | 'medido' | 'cadastro' | 'simulado'

export interface Premissa {
  codigo: string
  texto: string
  valor: unknown
  origem: OrigemPremissa
}

export interface PlanoResumo {
  id: string
  tipo: TipoPlano
  farm_id: string | null
  field_id: string | null
  versao_motor: string
  estado: 'proposto' | 'revisado'
  gerado_em: string
  gerado_por: string | null
  premissas: number
}

export interface RevisaoPlano {
  id: string
  revisor_id: string
  papel: string
  decisao: 'aceito' | 'recusado' | 'ajustar'
  comentario: string | null
  plano_sha256: string
  revisado_em: string
}

export interface Plano extends Omit<PlanoResumo, 'premissas'> {
  pedido: Record<string, unknown>
  premissas: Premissa[]
  resultado: Record<string, any>
  sha256: string
  integro: boolean
  revisoes: RevisaoPlano[]
  aviso: string
}

export const TIPOS: Record<TipoPlano, string> = {
  fitossanitario: 'Fitossanitário',
  robotico: 'Robótico',
  insumos: 'Insumos',
}

const ORIGENS: Record<OrigemPremissa, { texto: string; tom: Tone }> = {
  padrao: { texto: 'Padrão (não medido)', tom: 'warning' },
  simulado: { texto: 'Simulado', tom: 'warning' },
  pedido: { texto: 'Do pedido', tom: 'neutral' },
  cadastro: { texto: 'Cadastro', tom: 'neutral' },
  medido: { texto: 'Medido', tom: 'good' },
}

export const origemTexto = (o: OrigemPremissa): string => ORIGENS[o]?.texto ?? o
export const origemTom = (o: OrigemPremissa): Tone => ORIGENS[o]?.tom ?? 'neutral'

/** Quantas premissas o revisor precisa olhar com desconfiança (não medidas ou simuladas). */
export function premissasNaoMedidas(premissas: Premissa[]): number {
  return premissas.filter((p) => p.origem === 'padrao' || p.origem === 'simulado').length
}

/** A capacidade que revisa cada tipo — a mesma regra da API (o botão some sem ela). */
export const CAPACIDADE_DE_REVISAO: Record<TipoPlano, string> = {
  fitossanitario: 'diagnosis:review',
  robotico: 'mission:create',
  insumos: 'product:manage',
}

export function podeRevisar(tipo: TipoPlano, can: (c: string) => boolean): boolean {
  return can(CAPACIDADE_DE_REVISAO[tipo])
}

/** Comentário obrigatório para recusar ou pedir ajuste (a API recusa sem ele). */
export function revisaoValida(decisao: RevisaoPlano['decisao'], comentario: string): boolean {
  return decisao === 'aceito' || comentario.trim().length > 0
}

export function valorPremissa(v: unknown): string {
  if (v === null || v === undefined) return '—'
  if (typeof v === 'number') return Number.isInteger(v) ? v.toLocaleString('pt-BR') : v.toLocaleString('pt-BR', { maximumFractionDigits: 3 })
  if (typeof v === 'boolean') return v ? 'sim' : 'não'
  if (typeof v === 'string') return v
  const texto = JSON.stringify(v)
  return texto === '{}' ? '(nenhum)' : texto
}

export interface Cenario {
  p10: number
  p50: number
  p90: number
}

/** "12,5 L (8–19,5 L)" — central e a faixa p10–p90. */
export function cenarioTexto(c: Cenario | null | undefined): string {
  if (!c) return '—'
  const n = (x: number) => x.toLocaleString('pt-BR', { maximumFractionDigits: 1 })
  return `${n(c.p50)} L (${n(c.p10)}–${n(c.p90)} L)`
}

export function avaliacaoTom(avaliacao: string): Tone {
  if (avaliacao.startsWith('passaria do limite')) return 'critical'
  if (avaliacao.startsWith('repete')) return 'warning'
  return 'good'
}
