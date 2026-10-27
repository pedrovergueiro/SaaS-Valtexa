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
import type { MissionReport } from '@/lib/missionReport'
import type { EdgeRecord } from '@/lib/edgeRecords'
import type { Caixa, Explicacao } from '@/lib/ensino'
import type { HistoryStep } from '@/lib/fieldHistory'
import type { Lugar } from '@/lib/localizar'
import type { Comparison, MapPlant, MissionMap } from '@/lib/mapLayers'

export type MissionPlants = {
  mission_id: string
  plants: (MapPlant & { cameras: string[]; edge_categories: Record<string, number> })[]
  plants_seen: number
  results_without_plant: number
  incidence: MissionMap['incidence'] & { interval_95: [number, number] }
  method: string
}

export const keys = {
  me: (tenantId: string | null) => ['me', tenantId] as const,
  memberships: ['memberships'] as const,
  sessions: ['sessions'] as const,
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
  scene: (id: string, at: string | null, days: number) => ['scene', id, at ?? 'agora', days] as const,
  missions: (query: Query = {}) => ['missions', query] as const,
  mission: (id: string) => ['missions', 'one', id] as const,
  segments: (id: string) => ['missions', 'segments', id] as const,
  missionSafety: (id: string) => ['missions', 'safety', id] as const,
  missionHistory: (id: string) => ['missions', 'history', id] as const,
  checkpoints: (id: string) => ['missions', 'checkpoints', id] as const,
  missionReport: (id: string) => ['missions', 'report', id] as const,
  observations: (query: Query = {}) => ['observations', query] as const,
  reviewQueue: ['review-queue'] as const,
  reviewQueueOrdered: (order: ReviewOrder) => ['review-queue', order] as const,
  diagnosis: (id: string) => ['diagnoses', 'one', id] as const,
  aiModels: (fieldId: string) => ['fields', 'ai-models', fieldId] as const,
  plants: (fieldId: string) => ['plants', fieldId] as const,
  prevalence: (fieldId: string) => ['plants', 'prevalence', fieldId] as const,
  decisions: (query: Query = {}) => ['decisions', query] as const,
  products: ['products'] as const,
  batches: (productId: string) => ['batches', productId] as const,
  tanks: (query: Query = {}) => ['tanks', query] as const,
  applications: (query: Query = {}) => ['applications', query] as const,
  verifications: ['verifications'] as const,
  audit: (query: Query = {}) => ['audit', query] as const,
  users: ['users'] as const,
  collections: (query: Query = {}) => ['collections', query] as const,
  collection: (id: string) => ['collections', 'one', id] as const,
  collectionFiles: (id: string) => ['collections', 'files', id] as const,
  adminCollections: (query: Query = {}) => ['admin', 'collections', query] as const,
  adminCollection: (id: string) => ['admin', 'collections', 'one', id] as const,
  adminCollectionFiles: (id: string) => ['admin', 'collections', 'files', id] as const,
  adminTenants: ['admin', 'tenants'] as const,
  adminJobs: (query: Query = {}) => ['admin', 'jobs', query] as const,
  datasets: ['admin', 'datasets'] as const,
  datasetSamples: (id: string) => ['admin', 'datasets', 'samples', id] as const,
  modelCatalog: ['admin', 'models', 'catalog'] as const,
}

// --- leitura ----------------------------------------------------------------

/**
 * Sobre os `refetchInterval` deste arquivo.
 *
 * Desde que `/v1/stream` existe, eles deixaram de ser o mecanismo e passaram a
 * ser a rede embaixo dele: o que atualiza a tela é o evento empurrado pelo
 * servidor (ver `lib/stream.ts`), e o intervalo só entra quando a conexão ao
 * vivo caiu e ninguém percebeu. Por isso continuam largos — encurtá-los agora
 * seria pagar duas vezes pelo mesmo dado.
 *
 * A exceção é `useTelemetry`. Telemetria não vira evento de outbox: uma amostra
 * por segundo por robô transformaria a tabela de eventos numa série temporal, e
 * o fluxo ao vivo numa enxurrada que ninguém lê. Ali o intervalo é o mecanismo,
 * e é por isso que ele é o mais curto.
 */
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

/**
 * A cópia 3D do talhão. Pesada (uma entrada por planta), então só volta ao
 * servidor quando o stream avisa que o rover escaneou uma rua nova.
 */
export const useScene = (id: string | undefined, at: string | null, days: number) =>
  useQuery({
    queryKey: keys.scene(id ?? '', at, days),
    queryFn: () => api<T.FieldSceneOut>(`/v1/fields/${id}/scene`, { query: { at, days } }),
    enabled: Boolean(id),
    placeholderData: keepPreviousData,
    staleTime: 20_000,
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

/** Resultado da missão (seção 47): plantas, incidência, recomendações, comparação. */
export const useMissionReport = (id: string, enabled = true) =>
  useQuery({
    queryKey: keys.missionReport(id),
    queryFn: () => api<MissionReport>(`/v1/missions/${id}/report`),
    enabled,
  })

/** Rota percorrida, eventos da Edge AI e plantas da missão (mapa, seção 46). */
export const useMissionMap = (id: string | null | undefined) =>
  useQuery({
    queryKey: ['missions', 'map', id ?? ''],
    queryFn: () => api<MissionMap>(`/v1/missions/${id}/map`),
    enabled: Boolean(id),
  })

/** Todas as plantas vistas na missão (o relatório só traz as ocorrências). */
export const useMissionPlants = (id: string, enabled = true) =>
  useQuery({
    queryKey: ['missions', 'plants', id],
    queryFn: () => api<MissionPlants>(`/v1/missions/${id}/plants`),
    enabled,
  })

export const useMissionComparison = (id: string | null | undefined, baselineId: string | null | undefined) =>
  useQuery({
    queryKey: ['missions', 'comparison', id ?? '', baselineId ?? ''],
    queryFn: () =>
      api<Comparison>(`/v1/missions/${id}/comparison`, { query: { baseline_id: baselineId } }),
    enabled: Boolean(id && baselineId && id !== baselineId),
  })

/** Registros que os robôs sincronizaram para a missão (até 1000 por página). */
export const useEdgeRecords = (query: Query, enabled = true) =>
  useQuery({
    queryKey: ['edge-records', query],
    queryFn: () => api<EdgeRecord[]>('/v1/edge/records', { query }),
    enabled,
    placeholderData: keepPreviousData,
  })

export const useFieldHistory = (fieldId: string | undefined) =>
  useQuery({
    queryKey: ['fields', 'history', fieldId ?? ''],
    queryFn: () => api<HistoryStep[]>(`/v1/fields/${fieldId}/history`),
    enabled: Boolean(fieldId),
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

/**
 * A fila do agrônomo em uma de duas ordens.
 *
 * `novidade` põe no topo o que mais destoa do conhecido; `valor`, o que mais
 * ensina ao próximo treino — e cada item volta com o motivo.
 */
export type ReviewOrder = 'novidade' | 'valor'

export const useReviewQueue = (order: ReviewOrder = 'novidade') =>
  useQuery({
    queryKey: keys.reviewQueueOrdered(order),
    queryFn: () => api<T.DiagnosisOut[]>('/v1/review/queue', { query: { limit: 100, order } }),
    placeholderData: keepPreviousData,
  })

/** Um diagnóstico com os sinais de cada análise — o que a lista de observações não traz. */
export const useDiagnosis = (id: string | null | undefined) =>
  useQuery({
    queryKey: keys.diagnosis(id ?? ''),
    queryFn: () => api<T.DiagnosisOut>(`/v1/diagnoses/${id}`),
    enabled: Boolean(id),
    staleTime: 60_000,
  })

/** As versões do modelo que servem a cultura do talhão, para o seletor. */
export const useFieldAiModels = (fieldId: string) =>
  useQuery({
    queryKey: keys.aiModels(fieldId),
    queryFn: () => api<T.AiModelChoiceOut[]>(`/v1/fields/${fieldId}/ai-models`),
    staleTime: 5 * 60_000,
  })

/**
 * As plantas do talhão, fundidas pela inferência a partir dos quadros do rover.
 *
 * Sem `retry`: o 503 aqui é estado (inferência sem talhões configurados), não
 * falha passageira — repetir três vezes só atrasa a mensagem.
 */
export const useFieldPlants = (fieldId: string) =>
  useQuery({
    queryKey: keys.plants(fieldId),
    queryFn: () => api<T.PlantOut[]>(`/v1/fields/${fieldId}/plants`),
    retry: false,
    staleTime: 30_000,
  })

export const useFieldPrevalence = (fieldId: string) =>
  useQuery({
    queryKey: keys.prevalence(fieldId),
    queryFn: () => api<T.PrevalenceOut>(`/v1/fields/${fieldId}/prevalence`),
    retry: false,
    staleTime: 60_000,
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

/**
 * Corrigir a rota à mão e mandar recalcular.
 *
 * Invalidam os segmentos junto com a missão: a rota é o que a tela desenha, e
 * uma missão atualizada com segmentos velhos mostraria o percurso antigo no
 * mapa enquanto os números ao lado já falam do novo.
 */
export function useEditRoute(missionId: string) {
  return useApiMutation(
    (body: { legs: number[][][]; reason?: string | null }) =>
      api<T.MissionOut>(`/v1/missions/${missionId}/route`, { method: 'PATCH', body }),
    [['missions'], keys.segments(missionId), keys.missionSafety(missionId), keys.missionHistory(missionId)],
  )
}

export function useReplanRoute(missionId: string) {
  return useApiMutation(
    (body: { swath_m?: number | null; row_azimuth_deg?: number | null; obstacle_margin_m?: number | null }) =>
      api<T.MissionOut>(`/v1/missions/${missionId}/replan`, { method: 'POST', body }),
    [['missions'], keys.segments(missionId), keys.missionSafety(missionId), keys.missionHistory(missionId)],
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
    ({
      id,
      label,
      confirmed,
      notes,
      explicacao,
      lesoes,
    }: {
      id: string
      label: string
      confirmed: boolean
      notes?: string
      explicacao?: Explicacao | null
      lesoes?: Caixa[]
    }) =>
      api<T.DiagnosisOut>(`/v1/diagnoses/${id}/review`, {
        method: 'POST',
        body: { label, confirmed, notes: notes || null, explicacao: explicacao ?? null, lesoes: lesoes ?? [] },
      }),
    [keys.reviewQueue, ['observations'], ['twin'], keys.dashboard, keys.alerts, ['decisions']],
  )
}

/**
 * Troca a versão do modelo do talhão.
 *
 * Vale para o que chegar depois — o que já foi diagnosticado fica com a versão
 * que o diagnosticou, registrada em cada análise.
 */
export function useSetFieldAiModel(fieldId: string) {
  return useApiMutation(
    (aiModel: string | null) =>
      api<T.FieldOut>(`/v1/fields/${fieldId}/ai-model`, { method: 'PUT', body: { ai_model: aiModel } }),
    [keys.field(fieldId), keys.fields, keys.aiModels(fieldId), keys.prevalence(fieldId)],
  )
}

export function useDecide() {
  return useApiMutation(
    (diagnosisId: string) =>
      api<T.DecisionOut>(`/v1/diagnoses/${diagnosisId}/decide`, { method: 'POST' }),
    [['decisions']],
  )
}

// --- coletas ------------------------------------------------------------------

/**
 * Coletas publicadas, do ponto de vista do cliente.
 *
 * A rota do cliente só devolve o que já foi publicado — upload e fila são
 * assunto da ValTexa e vivem no painel administrativo.
 */
export const useCollections = (query: Query = {}) =>
  useQuery({
    queryKey: keys.collections(query),
    queryFn: () => api<T.CollectionOut[]>('/v1/collections', { query }),
  })

export const useCollection = (id: string) =>
  useQuery({
    queryKey: keys.collection(id),
    queryFn: () => api<T.CollectionOut>(`/v1/collections/${id}`),
    enabled: Boolean(id),
  })

export const useCollectionFiles = (id: string) =>
  useQuery({
    queryKey: keys.collectionFiles(id),
    queryFn: () => api<T.CollectionFileOut[]>(`/v1/collections/${id}/files`),
    enabled: Boolean(id),
  })

// --- painel administrativo ----------------------------------------------------

export const useAdminTenants = () =>
  useQuery({ queryKey: keys.adminTenants, queryFn: () => api<T.TenantOut[]>('/v1/admin/tenants') })

export const useAdminCollections = (query: Query = {}) =>
  useQuery({
    queryKey: keys.adminCollections(query),
    queryFn: () => api<T.CollectionOut[]>('/v1/admin/collections', { query }),
    placeholderData: keepPreviousData,
  })

/**
 * Uma coleta, no painel.
 *
 * Reconsulta sozinha enquanto houver trabalho em curso: é o que faz a barra
 * andar sem ninguém apertar nada. Parada a coleta, o intervalo desliga — nada
 * de bater no servidor a cada cinco segundos por uma tela que não muda mais.
 */
export const useAdminCollection = (id: string) =>
  useQuery({
    queryKey: keys.adminCollection(id),
    queryFn: () => api<T.CollectionOut>(`/v1/admin/collections/${id}`),
    enabled: Boolean(id),
    refetchInterval: (query) => {
      const estado = query.state.data?.state
      const emCurso = ['uploading', 'upload_completed', 'processing_queued', 'ai_processing']
      return estado && emCurso.includes(estado) ? 3_000 : false
    },
  })

export const useAdminCollectionFiles = (id: string, query: Query = {}) =>
  useQuery({
    queryKey: [...keys.adminCollectionFiles(id), query],
    queryFn: () => api<T.CollectionFileOut[]>(`/v1/admin/collections/${id}/files`, { query }),
    enabled: Boolean(id),
  })

export const useAdminJobs = (query: Query = {}) =>
  useQuery({
    queryKey: keys.adminJobs(query),
    queryFn: () => api<T.JobOut[]>('/v1/admin/jobs', { query }),
    refetchInterval: 10_000,
  })

export const useDatasets = () =>
  useQuery({ queryKey: keys.datasets, queryFn: () => api<T.DatasetOut[]>('/v1/admin/datasets') })

export const useDatasetSamples = (id: string) =>
  useQuery({
    queryKey: keys.datasetSamples(id),
    queryFn: () => api<T.DatasetSampleOut[]>(`/v1/admin/datasets/${id}/samples`),
    enabled: Boolean(id),
  })

export const useModelCatalog = () =>
  useQuery({
    queryKey: keys.modelCatalog,
    queryFn: () => api<T.CatalogModelOut[]>('/v1/admin/models/catalog'),
    staleTime: 5 * 60_000,
  })

export function useCreateCollection() {
  return useApiMutation(
    (body: T.CollectionCreate) =>
      api<T.CollectionOut>('/v1/admin/collections', { method: 'POST', body }),
    [['admin', 'collections']],
  )
}

export function useCompleteUpload() {
  return useApiMutation(
    (id: string) =>
      api<T.CollectionOut>(`/v1/admin/collections/${id}/complete`, { method: 'POST' }),
    [['admin', 'collections'], keys.adminJobs()],
  )
}

export function useReleaseCollection() {
  return useApiMutation(
    (id: string) =>
      api<T.CollectionOut>(`/v1/admin/collections/${id}/release`, { method: 'POST' }),
    [['admin', 'collections'], ['collections']],
  )
}

export function useRetryJob() {
  return useApiMutation(
    (id: string) => api<T.JobOut>(`/v1/admin/jobs/${id}/retry`, { method: 'POST' }),
    [['admin', 'jobs'], ['admin', 'collections']],
  )
}

export function useFreezeDatasetVersion(datasetId: string) {
  return useApiMutation(
    (body: { version: string; notes?: string; politica?: 'um' | 'consenso' | 'confiabilidade' }) =>
      api<T.DatasetVersionOut>(`/v1/admin/datasets/${datasetId}/versions`, {
        method: 'POST',
        body,
      }),
    [keys.datasets],
  )
}

/**
 * Cadastra um cliente, com propriedade e primeiro talhao.
 *
 * Invalida a lista de clientes e a de associacoes: quem e da equipe da ValTexa
 * ve todo cliente na troca de cliente, entao um cadastro novo muda as duas.
 */
export function useOnboardTenant() {
  return useApiMutation(
    (body: T.OnboardIn) => api<T.OnboardOut>('/v1/admin/tenants', { method: 'POST', body }),
    [keys.adminTenants, keys.memberships],
  )
}

/** Altera contato, endereco e contrato de um cliente. */
export function useUpdateTenant(tenantId: string) {
  return useApiMutation(
    (body: T.TenantUpdate) =>
      api<T.TenantOut>(`/v1/admin/tenants/${tenantId}`, { method: 'PATCH', body }),
    [keys.adminTenants],
  )
}

/**
 * Planeja a cobertura de um talhao: rota, tempo, energia e postes de recarga.
 *
 * Nao invalida nada. Planejar e pergunta, nao escrita: o mesmo talhao e
 * replanejado dezenas de vezes enquanto se escolhe a direcao das linhas e a
 * largura da faixa, e nenhuma dessas tentativas muda o banco.
 */
export function usePlanField(fieldId: string) {
  return useMutation({
    mutationFn: (body: T.PlanRequest) =>
      api<T.PlanOut>(`/v1/admin/fields/${fieldId}/plan`, { method: 'POST', body }),
  })
}

/** O satélite do console: o do Google (Map Tiles API) quando ligado, se não o da Esri. */
export type Satelite =
  | { provedor: 'esri'; aviso?: string }
  | { provedor: 'google'; sessao: string; chave: string; url: string; tile_px: number }

export function useSatelite() {
  return useQuery({
    queryKey: ['mapa', 'satelite'],
    queryFn: () => api<Satelite>('/v1/mapa/satelite'),
    staleTime: 6 * 60 * 60 * 1000,
    retry: false,
  })
}

/** Busca um lugar pelo endereço (Google ou OpenStreetMap, no servidor). */
export function useBuscaLugar() {
  return useMutation({
    mutationFn: (q: string) =>
      api<{ lugares: Lugar[]; avisos: string[] }>(`/v1/mapa/localizar?q=${encodeURIComponent(q)}`),
  })
}

/**
 * Encaixe do contorno pela IA.
 *
 * Não invalida nada: encaixar é pergunta, não escrita. O resultado volta para a
 * tela e é a pessoa que decide salvar.
 */
export function useRefineBoundary() {
  return useMutation({
    mutationFn: (body: T.BoundaryRefineIn) =>
      api<T.BoundaryRefineOut>('/v1/admin/boundary/refine', { method: 'POST', body }),
  })
}

/**
 * Grava o contorno redesenhado, com a leitura de terreno que veio junto.
 *
 * A leitura viaja com o contorno porque é dele que ela vale: um terreno lido
 * sobre outro polígono descreve outro pedaço de chão. Salvar sem ela apaga a
 * anterior, pelo mesmo motivo.
 */
export function useUpdateFieldBoundary(fieldId: string) {
  return useApiMutation(
    ({ boundary, terrain }: { boundary: number[][]; terrain?: T.TerrainOut | null }) =>
      api<T.FieldOut>(`/v1/fields/${fieldId}/boundary`, {
        method: 'PATCH',
        body: { boundary, terrain: terrain ?? null },
      }),
    [keys.fields, keys.field(fieldId), ['twin'], ['scene'], keys.dashboard],
  )
}
