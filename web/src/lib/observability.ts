/**
 * Observabilidade (Parte 7, brief seções 34 e 35): o que a tela decide sozinha.
 *
 * Regra que vale em tudo aqui: **`null` não é zero**. O que o robô ou o servidor não
 * mediu aparece como "não medido", nunca como 0 % (um 0 % de CPU é uma medida).
 */
import { useQuery } from '@tanstack/react-query'

import { api, type Query } from '@/api/client'
import { useApiMutation } from '@/api/queries'
import type { components } from '@/api/schema'
import { fmt } from '@/lib/format'
import type { Tone } from '@/lib/labels'

type S = components['schemas']
export type ObsOverview = S['ObservabilityOverviewOut']
export type ObsComponent = S['ObsComponentOut']
export type ApiStats = S['ApiStatsOut']
export type ApiRouteStat = S['ApiRouteStatOut']
export type RoverHealth = S['RoverHealthOut']
export type AiObservability = S['AiObservabilityOut']
export type AiModelStat = S['AiModelStatOut']
export type AiDrift = S['AiDriftOut']
export type ObsAlert = S['ObsAlertOut']
export type AlertRule = S['AlertRuleOut']
export type AlertRuleIn = S['AlertRuleIn']

// --- textos e tons ----------------------------------------------------------------

export const NAO_MEDIDO = 'não medido'

export function componentLabel(component: string): string {
  return (
    { banco: 'Banco de dados', api: 'API', worker: 'Worker e eventos', ia: 'Serviço de IA', frota: 'Frota', alertas: 'Alertas' }[
      component
    ] ?? component
  )
}

export function componentTone(status: string): Tone {
  return status === 'ok' ? 'good' : status === 'falha' ? 'critical' : 'warning'
}

export function componentStatusLabel(status: string): string {
  return { ok: 'ok', atencao: 'atenção', falha: 'falha' }[status] ?? status
}

export function deliveryLabel(status: string): string {
  return (
    { pendente: 'pendente(s)', enviado: 'enviado(s)', nao_enviado: 'não enviado(s)', falhou: 'falhou (tenta de novo)', desistiu: 'desistiu' }[
      status
    ] ?? status
  )
}

export function alertStateLabel(state: string): string {
  return { disparado: 'Disparado', reconhecido: 'Reconhecido', resolvido: 'Resolvido' }[state] ?? state
}

export function alertTone(alert: Pick<ObsAlert, 'state' | 'severity'>): Tone {
  if (alert.state === 'resolvido') return 'good'
  if (alert.state === 'reconhecido') return 'info'
  return alert.severity === 'critico' ? 'critical' : 'warning'
}

export function severityLabel(severity: string): string {
  return severity === 'critico' ? 'Crítico' : 'Aviso'
}

/** Disparados primeiro (críticos antes), depois reconhecidos, depois resolvidos; recentes primeiro. */
export function sortAlerts<T extends Pick<ObsAlert, 'state' | 'severity' | 'fired_at'>>(alerts: readonly T[]): T[] {
  const peso = (a: T) =>
    (a.state === 'disparado' ? 0 : a.state === 'reconhecido' ? 2 : 4) + (a.severity === 'critico' ? 0 : 1)
  return [...alerts].sort((a, b) => peso(a) - peso(b) || b.fired_at.localeCompare(a.fired_at))
}

export function alertCounts(alerts: readonly Pick<ObsAlert, 'state' | 'severity'>[]) {
  return {
    open: alerts.filter((a) => a.state !== 'resolvido').length,
    critical: alerts.filter((a) => a.state === 'disparado' && a.severity === 'critico').length,
    acknowledged: alerts.filter((a) => a.state === 'reconhecido').length,
  }
}

// --- números ----------------------------------------------------------------------

export function pct(value: number | null | undefined, digits = 0): string {
  return value === null || value === undefined ? NAO_MEDIDO : `${fmt.number(value, digits)}%`
}

export function ms(value: number | null | undefined): string {
  if (value === null || value === undefined) return NAO_MEDIDO
  return value >= 1000 ? `${fmt.number(value / 1000, 2)} s` : `${fmt.number(value, value < 10 ? 1 : 0)} ms`
}

export function seconds(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—'
  if (value < 90) return `${fmt.number(value, 0)} s`
  if (value < 5400) return `${fmt.number(value / 60, 0)} min`
  return `${fmt.number(value / 3600, 1)} h`
}

/** Tom de um uso em % contra um limite (atenção a 85 % do limite). */
export function usageTone(value: number | null | undefined, limit: number): Tone {
  if (value === null || value === undefined) return 'neutral'
  if (value >= limit) return 'critical'
  if (value >= limit * 0.85) return 'warning'
  return 'good'
}

/** Os problemas de um robô, em frases curtas (vazio = nada a dizer). */
export function roverIssues(r: RoverHealth, limits = { disk: 90, temperature: 75 }): string[] {
  const saida: string[] = []
  if (r.connectivity === 'offline') saida.push(`sem comunicação${r.offline_minutes != null ? ` há ${seconds(r.offline_minutes * 60)}` : ''}`)
  if (r.disk_percent != null && r.disk_percent >= limits.disk) saida.push(`disco em ${pct(r.disk_percent)}`)
  if (r.temperature_c != null && r.temperature_c >= limits.temperature) saida.push(`${fmt.number(r.temperature_c, 1)} °C`)
  const ruins = r.cameras.filter((c) => !c.ok)
  if (ruins.length) saida.push(`câmera ${ruins.map((c) => c.id).join(', ')} sem responder`)
  if (r.sync_blocked) saida.push('sincronização travada')
  else if (r.sync_pending > 0 && r.sync_oldest_pending_s != null && r.sync_oldest_pending_s >= 1800)
    saida.push(`${r.sync_pending} registro(s) esperando há ${seconds(r.sync_oldest_pending_s)}`)
  return saida
}

export function ruleThreshold(rule: Pick<AlertRule, 'threshold' | 'unit' | 'window_minutes'>): string {
  if (rule.threshold === null || rule.threshold === undefined) return 'sem limite (qualquer ocorrência)'
  const valor = rule.unit === 'distância' ? fmt.number(rule.threshold, 2) : fmt.number(rule.threshold, rule.threshold % 1 ? 1 : 0)
  const unidade = rule.unit === '%' ? '%' : rule.unit && rule.unit !== 'distância' ? ` ${rule.unit}` : ''
  const janela = rule.window_minutes ? ` em ${seconds(rule.window_minutes * 60)}` : ''
  return `${valor}${unidade}${janela}`
}

/** Classes de uma distribuição, maiores primeiro, com a fração de cada uma. */
export function classShares(classes: Record<string, number>): { label: string; count: number; share: number }[] {
  const total = Object.values(classes).reduce((a, b) => a + b, 0)
  return Object.entries(classes)
    .map(([label, count]) => ({ label, count, share: total ? count / total : 0 }))
    .sort((a, b) => b.count - a.count || a.label.localeCompare(b.label))
}

export function driftTone(distance: number | null | undefined, limit = 0.25): Tone {
  if (distance === null || distance === undefined) return 'neutral'
  return distance >= limit ? 'warning' : 'good'
}

// --- chamadas ------------------------------------------------------------------------

export const obsKeys = {
  overview: ['observability', 'overview'] as const,
  api: (minutes: number) => ['observability', 'api', minutes] as const,
  fleet: (scope: 'plataforma' | 'cliente', query?: Query) => ['observability', 'fleet', scope, query ?? {}] as const,
  ai: (hours: number) => ['observability', 'ai', hours] as const,
  alerts: (scope: 'plataforma' | 'cliente', query?: Query) => ['observability', 'alerts', scope, query ?? {}] as const,
  rules: (scope: 'plataforma' | 'cliente') => ['observability', 'rules', scope] as const,
}

const base = (scope: 'plataforma' | 'cliente') =>
  scope === 'plataforma' ? '/v1/platform/observability' : '/v1/observability'

export const useObsOverview = () =>
  useQuery({ queryKey: obsKeys.overview, queryFn: () => api<ObsOverview>('/v1/platform/observability'), refetchInterval: 30_000 })

export const useApiStats = (minutes: number) =>
  useQuery({
    queryKey: obsKeys.api(minutes),
    queryFn: () => api<ApiStats>('/v1/platform/observability/api', { query: { minutes } }),
    refetchInterval: 60_000,
  })

export const useFleetHealth = (scope: 'plataforma' | 'cliente', query?: Query) =>
  useQuery({
    queryKey: obsKeys.fleet(scope, query),
    queryFn: () => api<RoverHealth[]>(`${base(scope)}/fleet`, { query }),
    refetchInterval: 30_000,
  })

export const useAiObservability = (hours: number) =>
  useQuery({
    queryKey: obsKeys.ai(hours),
    queryFn: () => api<AiObservability>('/v1/platform/observability/ai', { query: { hours } }),
  })

export const useObsAlerts = (scope: 'plataforma' | 'cliente', query?: Query) =>
  useQuery({
    queryKey: obsKeys.alerts(scope, query),
    queryFn: () => api<ObsAlert[]>(`${base(scope)}/alerts`, { query }),
    refetchInterval: 30_000,
  })

export const useAlertRules = (scope: 'plataforma' | 'cliente') =>
  useQuery({ queryKey: obsKeys.rules(scope), queryFn: () => api<AlertRule[]>(`${base(scope)}/alert-rules`) })

export const useAckAlert = (scope: 'plataforma' | 'cliente') =>
  useApiMutation(
    ({ id, note }: { id: string; note?: string }) =>
      api<ObsAlert>(`${base(scope)}/alerts/${id}/ack`, { method: 'POST', body: { note: note || null } }),
    [['observability']],
  )

export const useSaveRule = (scope: 'plataforma' | 'cliente') =>
  useApiMutation(
    ({ kind, body }: { kind: string; body: AlertRuleIn }) =>
      api<AlertRule>(`${base(scope)}/alert-rules/${kind}`, { method: 'PUT', body }),
    [['observability']],
  )

export const useResetRule = () =>
  useApiMutation(
    (kind: string) => api<void>(`/v1/observability/alert-rules/${kind}`, { method: 'DELETE' }),
    [['observability']],
  )
