/**
 * Resultado da missão no console (brief, seções 7, 44 e 47): plantas, incidência,
 * recomendações, prescrição e comparação com a passada anterior.
 *
 * Tudo vem pronto de `GET /v1/missions/{id}/report` — aqui só se decide como mostrar.
 * O produtor vê linguagem operacional (doente, suspeita, sadia); hash e modelo, não.
 */
import type { Tone } from './labels'

export type PlantStatus = 'doente' | 'suspeita' | 'revisar' | 'sadia'

export interface ReportPlant {
  plant_id: string
  row: number | null
  status: PlantStatus
  label: string | null
  frames: number
  cameras: string[]
}

export interface MissionReport {
  mission_id: string
  kind?: string
  state?: string
  farm?: string | null
  field?: string | null
  crop?: string | null
  area_ha?: number | null
  history?: { mission_id: string; date: string | null; incidence: number | null }[]
  generated_at?: string
  rover: string | null
  date: string | null
  duration_min: number | null
  images_processed: number
  events: Record<string, number>
  edge_categories: Record<string, number>
  occurrences: ReportPlant[]
  plants_seen: number
  incidence: {
    diseased: number
    suspect: number
    ratio: number | null
    interval_95: [number, number]
    by_label: Record<string, number>
  }
  recommendations: { decision_id: string; outcome: string; rationale: string | null }[]
  prescriptions: { mission_id: string; state: string; rate_l_ha: number | null; quantity_l: number | null }[]
  comparison_with_previous: {
    incidence_before: number | null
    incidence_after: number | null
    delta: number | null
    recovered: string[]
    persisting: string[]
    new: string[]
  } | null
  simulated: boolean
}

const STATUS: Record<PlantStatus, { label: string; tone: Tone; order: number }> = {
  doente: { label: 'Doente', tone: 'critical', order: 0 },
  revisar: { label: 'Com o agrônomo', tone: 'warning', order: 1 },
  suspeita: { label: 'Suspeita', tone: 'serious', order: 2 },
  sadia: { label: 'Sadia', tone: 'good', order: 3 },
}

export const plantStatusLabel = (status: PlantStatus): string => STATUS[status]?.label ?? status
export const plantStatusTone = (status: PlantStatus): Tone => STATUS[status]?.tone ?? 'neutral'

/** Doentes primeiro; dentro do status, pela ordem de campo (linha, planta). */
export function sortOccurrences(plants: ReportPlant[]): ReportPlant[] {
  return [...plants].sort(
    (a, b) =>
      (STATUS[a.status]?.order ?? 9) - (STATUS[b.status]?.order ?? 9) ||
      (a.row ?? 0) - (b.row ?? 0) ||
      a.plant_id.localeCompare(b.plant_id, 'pt-BR', { numeric: true }),
  )
}

const pct = (v: number) => `${(v * 100).toFixed(1).replace('.', ',')}%`

/** "3 de 54 plantas (5,6%; entre 1,9% e 15,1%)" — ou "nenhuma planta vista". */
export function incidenceText(report: Pick<MissionReport, 'incidence' | 'plants_seen'>): string {
  const { incidence, plants_seen } = report
  if (!plants_seen || incidence.ratio == null) return 'nenhuma planta vista'
  const [lo, hi] = incidence.interval_95
  return `${incidence.diseased} de ${plants_seen} plantas (${pct(incidence.ratio)}; entre ${pct(lo)} e ${pct(hi)})`
}

/** Seta e tom da mudança de incidência em relação à passada anterior. */
export function trend(delta: number | null): { text: string; tone: Tone } {
  if (delta == null) return { text: 'sem passada anterior', tone: 'neutral' }
  if (Math.abs(delta) < 0.0005) return { text: 'estável', tone: 'neutral' }
  return delta < 0
    ? { text: `caiu ${pct(-delta)}`, tone: 'good' }
    : { text: `subiu ${pct(delta)}`, tone: 'critical' }
}

const OUTCOME: Record<string, string> = {
  application_candidate: 'Candidata a aplicação',
  observe: 'Observar',
  need_more_data: 'Precisa de mais dados',
  human_review: 'Com o agrônomo',
  no_action: 'Nada a fazer',
}

export const outcomeLabel = (outcome: string): string => OUTCOME[outcome] ?? outcome
