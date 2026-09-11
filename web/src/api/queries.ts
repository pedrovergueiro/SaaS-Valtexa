/**
 * Consultas e mutações do console, sobre o react-query.
 *
 * As chaves são hierárquicas de propósito: invalidar `['missions']` alcança a
 * lista e todos os filtros dela. É isso que o stream de eventos usa para manter
 * a tela em dia sem polling agressivo.
 */
import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
  type QueryKey,
} from '@tanstack/react-query'

import { api, type Query } from './client'
import type * as T from './types'

export const keys = {
  me: (tenantId: string | null) => ['me', tenantId] as const,
  memberships: ['memberships'] as const,
  dashboard: ['dashboard'] as const,
  alerts: ['alerts'] as const,
  devices: (query: Query = {}) => ['devices', query] as const,
  device: (id: string) => ['devices', 'one', id] as const,
  telemetry: (id: string, minutes: number) => ['telemetry', id, minutes] as const,
  deviceEvents: (id: string) => ['device-events', id] as const,
  deviceModels: ['device-models'] as const,
  farms: ['farms'] as const,
  fields: ['fields'] as const,
  field: (id: string) => ['fields', 'one', id] as const,
  zones: (fieldId: string) => ['zones', fieldId] as const,
  snapshot: (id: string, days: number) => ['twin', 'snapshot', id, days] as const,
  timeline: (id: string, days: number) => ['twin', 'timeline', id, days] as const,
  anomalies: (id: string) => ['twin', 'anomalies', id] as const,
  missions: (query: Query = {}) => ['missions', query] as const,
  mission: (id: string) => ['missions', 'one', id] as const,
  segments: (id: string) => ['missions', 'segments', id] as const,
  missionSafety: (id: string) => ['missions', 'safety', id] as const,
  missionHistory: (id: string) => ['missions', 'history', id] as const,
  checkpoints: (id: string) => ['missions', 'checkpoints', id] as const,
  observations: (query: Query = {}) => ['observations', query] as const,
  reviewQueue: ['review-queue'] as const,
  decisions: (query: Query = {}) => ['decisions', query] as const,
  products: ['products'] as const,
  batches: (productId: string) => ['batches', productId] as const,
  tanks: (query: Query = {}) => ['tanks', query] as const,
  applications: (query: Query = {}) => ['applications', query] as const,
  verifications: ['verifications'] as const,
  audit: (query: Query = {}) => ['audit', query] as const,
  users: ['users'] as const,
}

// --- leitura ----------------------------------------------------------------

export const useDashboard = () =>
  useQuery({
    queryKey: keys.dashboard,
    queryFn: () => api<T.DashboardOut>('/v1/dashboard'),
    refetchInterval: 60_000,
  })

export const useAlerts = () =>
  useQuery({
    queryKey: keys.alerts,
    queryFn: () => api<T.AlertOut[]>('/v1/alerts'),
    refetchInterval: 60_000,
  })

export const useDevices = (query: Query = {}) =>
  useQuery({
    queryKey: keys.devices(query),
    queryFn: () => api<T.DeviceOut[]>('/v1/devices', { query }),
    refetchInterval: 30_000,
  })

export const useDevice = (id: string) =>
  useQuery({ queryKey: keys.device(id), queryFn: () => api<T.DeviceOut>(`/v1/devices/${id}`) })

export const useTelemetry = (id: string, minutes: number) =>
  useQuery({
    queryKey: keys.telemetry(id, minutes),
    queryFn: () =>
      api<T.TelemetryOut[]>(`/v1/devices/${id}/telemetry`, { query: { minutes, limit: 2000 } }),
    placeholderData: keepPreviousData,
    refetchInterval: 15_000,
  })

export const useDeviceEvents = (id: string) =>
  useQuery({
    queryKey: keys.deviceEvents(id),
    queryFn: () => api<T.DeviceEventOut[]>(`/v1/devices/${id}/events`, { query: { limit: 100 } }),
  })

export const useDeviceModels = () =>
  useQuery({
    queryKey: keys.deviceModels,
    queryFn: () => api<T.DeviceModelOut[]>('/v1/device-models'),
    staleTime: Infinity,
  })

export const useFarms = () =>
  useQuery({ queryKey: keys.farms, queryFn: () => api<T.FarmOut[]>('/v1/farms') })

export const useFields = () =>
  useQuery({ queryKey: keys.fields, queryFn: () => api<T.FieldOut[]>('/v1/fields') })

export const useField = (id: string) =>
  useQuery({ queryKey: keys.field(id), queryFn: () => api<T.FieldOut>(`/v1/fields/${id}`) })

export const useZones = (fieldId: string | undefined) =>
  useQuery({
    queryKey: keys.zones(fieldId ?? ''),
    queryFn: () => api<T.ZoneOut[]>(`/v1/fields/${fieldId}/zones`),
    enabled: Boolean(fieldId),
  })

export const useSnapshot = (id: string, days: number) =>
  useQuery({
    queryKey: keys.snapshot(id, days),
    queryFn: () => api<T.FieldSnapshotOut>(`/v1/fields/${id}/snapshot`, { query: { days } }),
    placeholderData: keepPreviousData,
  })

export const useTimeline = (id: string, days: number) =>
  useQuery({
    queryKey: keys.timeline(id, days),
    queryFn: () => api<T.TimePointOut[]>(`/v1/fields/${id}/timeline`, { query: { days } }),
    placeholderData: keepPreviousData,
  })

export const useAnomalies = (id: string) =>
  useQuery({
    queryKey: keys.anomalies(id),
    queryFn: () => api<T.AnomalyOut[]>(`/v1/fields/${id}/anomalies`),
  })

export const useMissions = (query: Query = {}) =>
  useQuery({
    queryKey: keys.missions(query),
    queryFn: () => api<T.MissionOut[]>('/v1/missions', { query }),
    placeholderData: keepPreviousData,
  })

export const useMission = (id: string) =>
  useQuery({ queryKey: keys.mission(id), queryFn: () => api<T.MissionOut>(`/v1/missions/${id}`) })

export const useSegments = (id: string) =>
  useQuery({
    queryKey: keys.segments(id),
    queryFn: () => api<T.MissionSegmentOut[]>(`/v1/missions/${id}/segments`),
  })

export const useMissionSafety = (id: string) =>
  useQuery({
    queryKey: keys.missionSafety(id),
    queryFn: () => api<T.SafetyEvaluationOut[]>(`/v1/missions/${id}/safety`),
  })

export const useMissionHistory = (id: string) =>
  useQuery({
    queryKey: keys.missionHistory(id),
    queryFn: () => api<T.MissionHistoryOut[]>(`/v1/missions/${id}/history`),
  })

export const useCheckpoints = (id: string) =>
  useQuery({
    queryKey: keys.checkpoints(id),
    queryFn: () => api<T.CheckpointOut[]>(`/v1/missions/${id}/checkpoints`),
  })

export const useObservations = (query: Query, enabled = true) =>
  useQuery({
    queryKey: keys.observations(query),
    queryFn: () => api<T.ObservationOut[]>('/v1/observations', { query }),
    placeholderData: keepPreviousData,
    enabled,
  })

export const useReviewQueue = () =>
  useQuery({
    queryKey: keys.reviewQueue,
    queryFn: () => api<T.DiagnosisOut[]>('/v1/review/queue', { query: { limit: 100 } }),
  })

export const useDecisions = (query: Query = {}) =>
  useQuery({
    queryKey: keys.decisions(query),
    queryFn: () => api<T.DecisionOut[]>('/v1/decisions', { query }),
  })

export const useProducts = () =>
  useQuery({ queryKey: keys.products, queryFn: () => api<T.ProductOut[]>('/v1/products') })

export const useBatches = (productId: string | undefined) =>
  useQuery({
    queryKey: keys.batches(productId ?? ''),
    queryFn: () => api<T.BatchOut[]>(`/v1/products/${productId}/batches`),
    enabled: Boolean(productId),
  })

export const useTanks = (query: Query = {}) =>
  useQuery({
    queryKey: keys.tanks(query),
    queryFn: () => api<T.TankOut[]>('/v1/tanks', { query }),
  })

export const useApplications = (query: Query = {}) =>
  useQuery({
    queryKey: keys.applications(query),
    queryFn: () => api<T.ApplicationOut[]>('/v1/applications', { query }),
  })

export const useVerifications = () =>
  useQuery({
    queryKey: keys.verifications,
    queryFn: () => api<T.VerificationOut[]>('/v1/verifications'),
  })

export const useAudit = (query: Query = {}, enabled = true) =>
  useQuery({
    queryKey: keys.audit(query),
    queryFn: () => api<T.AuditOut[]>('/v1/audit', { query }),
    placeholderData: keepPreviousData,
    enabled,
  })

export const useUsers = () =>
  useQuery({ queryKey: keys.users, queryFn: () => api<T.UserOut[]>('/v1/users') })

// --- escrita ------------------------------------------------------------------

/**
 * Mutação que invalida as chaves afetadas quando dá certo.
 *
 * Invalidar é mais seguro que editar o cache à mão: o servidor pode ter mudado
 * mais do que o que a tela sabe (um bloqueio de segurança muda o estado da
 * missão e a lista de alertas ao mesmo tempo).
 */
export function useApiMutation<TVariables, TResult = unknown>(
  mutationFn: (variables: TVariables) => Promise<TResult>,
  invalidate: QueryKey[],
) {
  const client = useQueryClient()
  return useMutation({
    mutationFn,
    onSuccess: async () => {
      await Promise.all(invalidate.map((queryKey) => client.invalidateQueries({ queryKey })))
    },
  })
}

export type MissionAction = 'approve' | 'authorize' | 'dispatch' | 'resume' | 'abort'

export function useMissionAction(missionId: string) {
  return useApiMutation(
    ({ action, body, query }: { action: MissionAction; body?: unknown; query?: Query }) =>
      api<unknown>(`/v1/missions/${missionId}/${action}`, { method: 'POST', body, query }),
    [['missions'], keys.dashboard, keys.alerts, ['devices']],
  )
}

export function useCreateMission() {
  return useApiMutation(
    (body: T.MissionCreate) => api<T.MissionOut>('/v1/missions', { method: 'POST', body }),
    [['missions'], keys.dashboard],
  )
}

export function useReviewDiagnosis() {
  return useApiMutation(
    ({ id, label, confirmed, notes }: { id: string; label: string; confirmed: boolean; notes?: string }) =>
      api<T.DiagnosisOut>(`/v1/diagnoses/${id}/review`, {
        method: 'POST',
        body: { label, confirmed, notes: notes || null },
      }),
    [keys.reviewQueue, ['observations'], ['twin'], keys.dashboard, keys.alerts, ['decisions']],
  )
}

export function useDecide() {
  return useApiMutation(
    (diagnosisId: string) =>
      api<T.DecisionOut>(`/v1/diagnoses/${diagnosisId}/decide`, { method: 'POST' }),
    [['decisions']],
  )
}
