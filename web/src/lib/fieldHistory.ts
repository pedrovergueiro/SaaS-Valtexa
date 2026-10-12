/**
 * Linha do tempo do talhão (brief, seção 6): missão → ocorrências → prescrição →
 * aprovação → aplicação → verificação. Vem de `GET /v1/fields/{id}/history`, do mais
 * novo ao mais antigo; aqui só se traduz e se agrupa em ciclos.
 */
import type { Tone } from './labels'

export type HistoryStage = 'missao' | 'ocorrencias' | 'prescricao' | 'aprovacao' | 'aplicacao' | 'verificacao'

export type HistoryStep = {
  stage: HistoryStage
  at: string | null
  mission_id?: string | null
  application_id?: string
  verification_id?: string
  decision_id?: string | null
  origin_mission_id?: string | null
  kind?: string
  state?: string
  title?: string
  plants_seen?: number
  diseased?: number
  suspect?: number
  incidence?: number | null
  by_label?: Record<string, number>
  rate_l_ha?: number | null
  quantity_l?: number | null
  amount_used_l?: number | null
  area_ha?: number | null
  outside_polygon_points?: number
  conclusion?: string
  before_ratio?: number | null
  after_ratio?: number | null
  effectiveness?: number | null
}

export const STAGES: HistoryStage[] = ['missao', 'ocorrencias', 'prescricao', 'aprovacao', 'aplicacao', 'verificacao']

const STAGE: Record<HistoryStage, { label: string; tone: Tone }> = {
  missao: { label: 'Missão', tone: 'info' },
  ocorrencias: { label: 'Ocorrências', tone: 'critical' },
  prescricao: { label: 'Prescrição', tone: 'serious' },
  aprovacao: { label: 'Aprovação', tone: 'accent' },
  aplicacao: { label: 'Aplicação', tone: 'warning' },
  verificacao: { label: 'Verificação', tone: 'good' },
}

export const stageLabel = (s: HistoryStage) => STAGE[s]?.label ?? s
export const stageTone = (s: HistoryStage): Tone => STAGE[s]?.tone ?? 'neutral'

const pct = (v: number) => `${(v * 100).toFixed(1).replace('.', ',')}%`

const CONCLUSION: Record<string, string> = {
  pending: 'aguardando a nova passada',
  improved: 'melhorou',
  unchanged: 'sem mudança',
  worsened: 'piorou',
  inconclusive: 'inconclusiva',
}

/** Uma frase por passo, em linguagem do produtor. */
export function describe(step: HistoryStep): string {
  switch (step.stage) {
    case 'missao':
      return `${step.title ?? 'Missão'}${step.state ? ` (${step.state})` : ''}`
    case 'ocorrencias': {
      const base = `${step.diseased ?? 0} doente(s) e ${step.suspect ?? 0} suspeita(s) em ${step.plants_seen ?? 0} plantas`
      return step.incidence != null ? `${base} — incidência ${pct(step.incidence)}` : base
    }
    case 'prescricao': {
      const dose = step.rate_l_ha != null ? ` · ${String(step.rate_l_ha).replace('.', ',')} L/ha` : ''
      const qtd = step.quantity_l != null ? ` · ${String(step.quantity_l).replace('.', ',')} L` : ''
      return `Pulverização prescrita${dose}${qtd}${step.origin_mission_id ? ' a partir da varredura' : ''}`
    }
    case 'aprovacao':
      return 'Aprovada pelo agrônomo'
    case 'aplicacao': {
      const litros = step.amount_used_l != null ? ` · ${String(step.amount_used_l).replace('.', ',')} L` : ''
      const area = step.area_ha != null ? ` · ${String(step.area_ha).replace('.', ',')} ha` : ''
      const fora = step.outside_polygon_points ? ` · ${step.outside_polygon_points} ponto(s) fora da área` : ''
      return `Aplicação ${step.state === 'completed' ? 'concluída' : step.state === 'aborted' ? 'interrompida' : 'em andamento'}${litros}${area}${fora}`
    }
    case 'verificacao': {
      const antes = step.before_ratio != null ? ` · antes ${pct(step.before_ratio)}` : ''
      const depois = step.after_ratio != null ? ` · depois ${pct(step.after_ratio)}` : ''
      return `Verificação: ${CONCLUSION[step.conclusion ?? ''] ?? step.conclusion ?? '—'}${antes}${depois}`
    }
  }
}

/** Link do passo no console (a missão, ou a aplicação). */
export function stepLink(step: HistoryStep): string | null {
  if (step.stage === 'aplicacao') return '/aplicacoes'
  if (step.mission_id) return `/missoes/${step.mission_id}`
  return null
}

/** Quantos passos de cada etapa — para o cabeçalho ("2 aplicações, 1 verificação"). */
export function stageCounts(steps: HistoryStep[]): Record<HistoryStage, number> {
  const out = Object.fromEntries(STAGES.map((s) => [s, 0])) as Record<HistoryStage, number>
  for (const s of steps) out[s.stage] += 1
  return out
}

/** O ciclo está fechado quando, depois da última ocorrência, já houve verificação. */
export function cycleClosed(steps: HistoryStep[]): boolean {
  const ultimaOcorrencia = steps.findIndex((s) => s.stage === 'ocorrencias')
  if (ultimaOcorrencia < 0) return false
  // a lista vem do mais novo ao mais antigo: o que está antes do índice é posterior
  return steps.slice(0, ultimaOcorrencia).some((s) => s.stage === 'verificacao')
}
