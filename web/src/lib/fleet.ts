/**
 * Frota e Model Registry no console: rótulos, tons e resumos (brief, seções 9, 22 e 25).
 *
 * O estado de frota vem pronto do servidor (derivado do protocolo do robô); aqui
 * só se decide como mostrar. Nada é recalculado na tela.
 */
import type { Tone } from './labels'

export const FLEET_STATES = [
  'disponivel',
  'em_missao',
  'sincronizando',
  'manutencao',
  'offline',
  'bloqueado',
  'erro',
] as const
export type FleetState = (typeof FLEET_STATES)[number]

const FLEET_LABEL: Record<FleetState, string> = {
  disponivel: 'Disponível',
  em_missao: 'Em missão',
  sincronizando: 'Sincronizando',
  manutencao: 'Manutenção',
  offline: 'Offline',
  bloqueado: 'Bloqueado',
  erro: 'Erro',
}

const FLEET_TONE: Record<FleetState, Tone> = {
  disponivel: 'good',
  em_missao: 'accent',
  sincronizando: 'info',
  manutencao: 'warning',
  offline: 'neutral',
  bloqueado: 'critical',
  erro: 'serious',
}

export function fleetStateLabel(state: string | null | undefined): string {
  return (state && FLEET_LABEL[state as FleetState]) || state || '—'
}

export function fleetStateTone(state: string | null | undefined): Tone {
  return (state && FLEET_TONE[state as FleetState]) || 'neutral'
}

/** Quantos robôs em cada estado, na ordem fixa dos estados (zeros incluídos). */
export function fleetSummary(devices: readonly { fleet_state: string }[]): { state: FleetState; count: number }[] {
  const contagem = new Map<string, number>()
  for (const device of devices) contagem.set(device.fleet_state, (contagem.get(device.fleet_state) ?? 0) + 1)
  return FLEET_STATES.map((state) => ({ state, count: contagem.get(state) ?? 0 }))
}

const MODEL_STATUS: Record<string, { label: string; tone: Tone }> = {
  conforme: { label: 'Modelo conforme', tone: 'good' },
  divergente: { label: 'Modelo diferente do designado', tone: 'warning' },
  fora_do_registry: { label: 'Modelo fora do registry', tone: 'critical' },
  sem_dado: { label: 'Modelo não informado', tone: 'neutral' },
}

export function modelStatus(status: string | null | undefined): { label: string; tone: Tone } {
  return MODEL_STATUS[status ?? 'sem_dado'] ?? { label: status ?? '—', tone: 'neutral' }
}

/** "chave 1.2.3" ou "sem dado" — nunca um traço que pareça zero. */
export function modelInUse(key: string | null | undefined, version: string | null | undefined): string {
  if (!key) return 'sem dado'
  return version ? `${key} ${version}` : key
}

const GB = 1_000_000_000

/** "12,0 de 64,0 GB livres (19 %)" ou "sem dado". */
export function storageText(total: number | null | undefined, free: number | null | undefined): string {
  if (total == null || free == null || total <= 0) return 'sem dado'
  const pct = Math.round((100 * free) / total)
  const gb = (v: number) => (v / GB).toLocaleString('pt-BR', { minimumFractionDigits: 1, maximumFractionDigits: 1 })
  return `${gb(free)} de ${gb(total)} GB livres (${pct} %)`
}

export function storageTone(total: number | null | undefined, free: number | null | undefined): Tone {
  if (total == null || free == null || total <= 0) return 'neutral'
  const livre = free / total
  if (livre < 0.1) return 'critical'
  if (livre < 0.25) return 'warning'
  return 'good'
}

/** Falha ativa como texto curto: aceita `{code, message}` ou texto. */
export function faultText(fault: unknown): string {
  if (fault && typeof fault === 'object') {
    const f = fault as { code?: unknown; message?: unknown }
    const partes = [f.code, f.message].filter((p) => typeof p === 'string' && p)
    if (partes.length) return partes.join(' — ')
    return JSON.stringify(fault)
  }
  return String(fault)
}

// --- Model Registry -------------------------------------------------------------

export const MODEL_STATES = ['treinamento', 'validacao', 'aprovado', 'staging', 'producao', 'descontinuado'] as const
export type ModelState = (typeof MODEL_STATES)[number]

const MODEL_STATE_LABEL: Record<ModelState, string> = {
  treinamento: 'Treinamento',
  validacao: 'Validação',
  aprovado: 'Aprovado',
  staging: 'Staging',
  producao: 'Produção',
  descontinuado: 'Descontinuado',
}

const MODEL_STATE_TONE: Record<ModelState, Tone> = {
  treinamento: 'neutral',
  validacao: 'info',
  aprovado: 'accent',
  staging: 'warning',
  producao: 'good',
  descontinuado: 'neutral',
}

export function modelStateLabel(state: string): string {
  return MODEL_STATE_LABEL[state as ModelState] ?? state
}

export function modelStateTone(state: string): Tone {
  return MODEL_STATE_TONE[state as ModelState] ?? 'neutral'
}

/**
 * Se a transição pede motivo — o servidor recusa sem ele: voltar no ciclo
 * (reprovar) ou descontinuar.
 */
export function transitionNeedsReason(from: string, to: string): boolean {
  if (to === 'descontinuado') return true
  return MODEL_STATES.indexOf(to as ModelState) < MODEL_STATES.indexOf(from as ModelState)
}

/** Agrupa as versões por linha de modelo, com a de produção (se houver) à frente. */
export function groupByModel<T extends { model_key: string; state: string }>(versions: readonly T[]): [string, T[]][] {
  const grupos = new Map<string, T[]>()
  for (const v of versions) grupos.set(v.model_key, [...(grupos.get(v.model_key) ?? []), v])
  for (const lista of grupos.values()) lista.sort((a, b) => Number(b.state === 'producao') - Number(a.state === 'producao'))
  return [...grupos.entries()].sort(([a], [b]) => a.localeCompare(b))
}

/** Número técnico ou "sem dado" — a tela da IA nunca mostra zero inventado. */
export function orNoData(value: number | null | undefined, unit = '', digits = 1): string {
  if (value == null) return 'sem dado'
  return `${value.toLocaleString('pt-BR', { maximumFractionDigits: digits })}${unit}`
}
