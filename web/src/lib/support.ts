/**
 * Chamados e incidentes no console (brief, seção 49): rótulos, tons e o que cada
 * lado pode fazer em cada situação. O servidor confere tudo de novo; isto só
 * evita mostrar um botão que daria 409.
 */
import type { Tone } from './labels'

export const TICKET_STATUSES = ['aberto', 'em_atendimento', 'aguardando_cliente', 'resolvido', 'fechado'] as const
export const TICKET_PRIORITIES = ['baixa', 'normal', 'alta', 'urgente'] as const
export const INCIDENT_STATUSES = ['aberto', 'investigando', 'mitigado', 'resolvido'] as const
export const INCIDENT_SEVERITIES = ['baixa', 'media', 'alta', 'critica'] as const

const STATUS: Record<string, { label: string; client: string; tone: Tone }> = {
  aberto: { label: 'Aberto', client: 'Aberto', tone: 'info' },
  em_atendimento: { label: 'Em atendimento', client: 'Em atendimento', tone: 'accent' },
  aguardando_cliente: { label: 'Aguardando cliente', client: 'Aguardando você', tone: 'warning' },
  resolvido: { label: 'Resolvido', client: 'Resolvido', tone: 'good' },
  fechado: { label: 'Fechado', client: 'Fechado', tone: 'neutral' },
}

export const ticketStatusLabel = (status: string, side: 'cliente' | 'plataforma' = 'plataforma') =>
  (side === 'cliente' ? STATUS[status]?.client : STATUS[status]?.label) ?? status
export const ticketStatusTone = (status: string): Tone => STATUS[status]?.tone ?? 'neutral'

const PRIORITY: Record<string, { label: string; tone: Tone }> = {
  baixa: { label: 'Baixa', tone: 'neutral' },
  normal: { label: 'Normal', tone: 'info' },
  alta: { label: 'Alta', tone: 'warning' },
  urgente: { label: 'Urgente', tone: 'critical' },
}
export const priorityLabel = (value: string) => PRIORITY[value]?.label ?? value
export const priorityTone = (value: string): Tone => PRIORITY[value]?.tone ?? 'neutral'

const INCIDENT: Record<string, { label: string; tone: Tone }> = {
  aberto: { label: 'Aberto', tone: 'critical' },
  investigando: { label: 'Investigando', tone: 'warning' },
  mitigado: { label: 'Mitigado', tone: 'info' },
  resolvido: { label: 'Resolvido', tone: 'good' },
}
export const incidentStatusLabel = (value: string) => INCIDENT[value]?.label ?? value
export const incidentStatusTone = (value: string): Tone => INCIDENT[value]?.tone ?? 'neutral'
const SEVERITY: Record<string, string> = { baixa: 'Baixa', media: 'Média', alta: 'Alta', critica: 'Crítica' }
export const incidentSeverityLabel = (value: string) => SEVERITY[value] ?? value

export const isOpen = (status: string) => ['aberto', 'em_atendimento', 'aguardando_cliente'].includes(status)

/** O que o cliente pode fazer no chamado agora. */
export function clientActions(status: string): { comment: boolean; close: boolean; reopen: boolean } {
  return {
    comment: status !== 'fechado',
    close: status !== 'fechado',
    reopen: status === 'resolvido' || status === 'fechado',
  }
}

const EVENT: Record<string, string> = {
  aberto: 'abriu o chamado',
  status: 'mudou a situação',
  prioridade: 'mudou a prioridade',
  responsavel: 'mudou o responsável',
  incidente: 'incidente',
  comentario: 'comentou',
  sessao_suporte: 'entrou na conta (sessão de suporte)',
}

export type HistoryLike = {
  kind: string
  old_value?: string | null
  new_value?: string | null
  note?: string | null
}

/** Uma linha do histórico em português: "mudou a situação: Aberto → Resolvido". */
export function historyLine(event: HistoryLike, side: 'cliente' | 'plataforma' = 'plataforma'): string {
  const base = EVENT[event.kind] ?? event.kind
  const traduz = (value: string | null | undefined) => {
    if (!value) return '—'
    if (event.kind === 'status') return ticketStatusLabel(value, side)
    if (event.kind === 'prioridade') return priorityLabel(value)
    if (event.kind === 'incidente' && value in INCIDENT) return incidentStatusLabel(value)
    return value
  }
  if (['status', 'prioridade', 'responsavel', 'incidente'].includes(event.kind)) {
    if (event.old_value || event.new_value) return `${base}: ${traduz(event.old_value)} → ${traduz(event.new_value)}`
  }
  return base
}

/** Há quanto tempo o cliente espera a primeira resposta (para ordenar a fila). */
export function waitingMinutes(ticket: { created_at: string; first_response_at?: string | null }, now: Date): number | null {
  if (ticket.first_response_at) return null
  return Math.max(0, Math.round((now.getTime() - new Date(ticket.created_at).getTime()) / 60_000))
}

/** Fila da equipe: urgentes primeiro, depois quem espera há mais tempo. */
export function queueOrder<T extends { priority: string; status: string; last_activity_at: string }>(rows: T[]): T[] {
  const peso: Record<string, number> = { urgente: 0, alta: 1, normal: 2, baixa: 3 }
  return [...rows].sort((a, b) => {
    const abertoA = isOpen(a.status) ? 0 : 1
    const abertoB = isOpen(b.status) ? 0 : 1
    if (abertoA !== abertoB) return abertoA - abertoB
    const p = (peso[a.priority] ?? 9) - (peso[b.priority] ?? 9)
    if (p !== 0) return p
    return a.last_activity_at.localeCompare(b.last_activity_at)
  })
}
