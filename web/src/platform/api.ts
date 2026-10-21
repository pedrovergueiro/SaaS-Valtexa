/**
 * Chamadas do console interno. Todas em `/v1/platform/*` ou `/v1/admin/*`: o
 * servidor confere a capacidade de plataforma em cada uma; o menu só esconde.
 */
import { useQuery } from '@tanstack/react-query'

import { api, apiUpload, authHeaders, buildUrl, type Query } from '@/api/client'
import { useApiMutation } from '@/api/queries'
import type { components } from '@/api/schema'
import type { DefinicaoEnsaio, EnsaioResultado, Portao } from '@/lib/validacao'

type S = components['schemas']
export type PlatformMe = S['PlatformMeOut']
export type PlatformTenant = S['PlatformTenantSummary']
export type GlobalAccount = S['GlobalAccountOut']
export type SupportSession = S['SupportSessionOut']
export type SupportStartedOut = S['SupportSessionStarted']
export type SupportStart = S['SupportSessionStart']
export type PlatformAudit = S['AuditOut']
export type PlatformRole = S['PlatformRole']

export const platformKeys = {
  me: ['platform', 'me'] as const,
  tenants: (q: string) => ['platform', 'tenants', q] as const,
  accounts: (query: Query) => ['platform', 'accounts', query] as const,
  audit: (query: Query) => ['platform', 'audit', query] as const,
  supportSessions: (query: Query) => ['platform', 'support-sessions', query] as const,
}

export const usePlatformMe = (enabled = true) =>
  useQuery({
    queryKey: platformKeys.me,
    queryFn: () => api<PlatformMe>('/v1/platform/me'),
    enabled,
    staleTime: 60_000,
    retry: false,
  })

export const usePlatformTenants = (q = '') =>
  useQuery({
    queryKey: platformKeys.tenants(q),
    queryFn: () => api<PlatformTenant[]>('/v1/platform/tenants', { query: { q } }),
  })

export const useGlobalAccounts = (query: Query) =>
  useQuery({
    queryKey: platformKeys.accounts(query),
    queryFn: () => api<GlobalAccount[]>('/v1/platform/accounts', { query }),
  })

export const usePlatformAudit = (query: Query) =>
  useQuery({
    queryKey: platformKeys.audit(query),
    queryFn: () => api<PlatformAudit[]>('/v1/platform/audit', { query }),
  })

export const useSupportSessions = (query: Query) =>
  useQuery({
    queryKey: platformKeys.supportSessions(query),
    queryFn: () => api<SupportSession[]>('/v1/platform/support-sessions', { query }),
  })

export function useStartSupport() {
  return useApiMutation(
    (body: SupportStart) =>
      api<SupportStartedOut>('/v1/platform/support-sessions', { method: 'POST', body }),
    [['platform']],
  )
}

export function useSetPlatformRole() {
  return useApiMutation(
    ({ userId, role }: { userId: string; role: PlatformRole | null }) =>
      api(`/v1/platform/users/${userId}/platform-role`, {
        method: 'PUT',
        body: { platform_role: role },
      }),
    [['platform', 'accounts']],
  )
}

export function useSetAccountActive() {
  return useApiMutation(
    ({ userId, active, reason }: { userId: string; active: boolean; reason: string }) =>
      api<GlobalAccount>(`/v1/platform/accounts/${userId}/active`, {
        method: 'PUT',
        body: { is_active: active, reason },
      }),
    [['platform', 'accounts']],
  )
}

/**
 * Fazendas e talhões do cliente em foco, pelas rotas de plataforma: as ferramentas
 * internas (importar coleta, planejar) funcionam sem sessão de suporte.
 */
export const useToolFarms = () =>
  useQuery({
    queryKey: ['platform', 'tool-farms'],
    queryFn: () => api<S['FarmOut'][]>('/v1/admin/farms'),
  })

export const useToolFields = () =>
  useQuery({
    queryKey: ['platform', 'tool-fields'],
    queryFn: () => api<S['FieldOut'][]>('/v1/admin/fields'),
  })

// --- Frota e AI Platform (Parte 3) ----------------------------------------------

export type FleetDevice = S['FleetDeviceOut']
export type ModelVersion = S['ModelVersionOut']
export type ModelVersionDetail = S['ModelVersionDetailOut']
export type ModelRelease = S['ModelReleaseOut']
export type AiHealth = S['AiHealthOut']

export const usePlatformFleet = (query: Query) =>
  useQuery({
    queryKey: ['platform', 'fleet', query],
    queryFn: () => api<FleetDevice[]>('/v1/platform/fleet', { query }),
    refetchInterval: 30_000,
  })

export const useModelRegistry = () =>
  useQuery({
    queryKey: ['platform', 'models'],
    queryFn: () => api<ModelVersion[]>('/v1/platform/models'),
  })

export const useModelDetail = (id: string | null) =>
  useQuery({
    queryKey: ['platform', 'models', id],
    queryFn: () => api<ModelVersionDetail>(`/v1/platform/models/${id}`),
    enabled: Boolean(id),
  })

export function useModelTransition() {
  return useApiMutation(
    ({ id, to, reason }: { id: string; to: string; reason: string | null }) =>
      api<ModelVersion[]>(`/v1/platform/models/${id}/transition`, { method: 'POST', body: { to, reason } }),
    [['platform', 'models'], ['platform', 'ai-health']],
  )
}

export const useModelReleases = (tenantId: string) =>
  useQuery({
    queryKey: ['platform', 'model-releases', tenantId],
    queryFn: () =>
      api<ModelRelease[]>('/v1/platform/model-releases', {
        query: { tenant_id: tenantId || undefined, include_revoked: true },
      }),
  })

export function useReleaseModel() {
  return useApiMutation(
    (body: { tenant_id: string; model_key: string; reason: string | null }) =>
      api<ModelRelease>('/v1/platform/model-releases', { method: 'POST', body }),
    [['platform', 'model-releases'], ['platform', 'models']],
  )
}

export function useRevokeRelease() {
  return useApiMutation(
    (id: string) => api<ModelRelease>(`/v1/platform/model-releases/${id}/revoke`, { method: 'POST' }),
    [['platform', 'model-releases'], ['platform', 'models']],
  )
}

export const useAiHealth = () =>
  useQuery({
    queryKey: ['platform', 'ai-health'],
    queryFn: () => api<AiHealth>('/v1/platform/ai-health'),
  })

// --- OTA e otimização dNATY (Parte 5) ----------------------------------------------

export type OtaPackage = S['OtaPackageOut']
export type OtaDeployment = S['OtaDeploymentOut']
export type ModelOptimization = S['ModelOptimizationOut']

export const useOtaDeployments = (query: Query) =>
  useQuery({
    queryKey: ['platform', 'ota', 'deployments', query],
    queryFn: () => api<OtaDeployment[]>('/v1/platform/ota/deployments', { query }),
    refetchInterval: 15_000,
  })

export const useOtaPackages = () =>
  useQuery({
    queryKey: ['platform', 'ota', 'packages'],
    queryFn: () => api<OtaPackage[]>('/v1/platform/ota/packages'),
  })

export function useCancelOta() {
  return useApiMutation(
    (id: string) => api<OtaDeployment>(`/v1/platform/ota/deployments/${id}/cancel`, { method: 'POST' }),
    [['platform', 'ota']],
  )
}

export const useModelOptimizations = (id: string | null) =>
  useQuery({
    queryKey: ['platform', 'models', id, 'optimizations'],
    queryFn: () => api<ModelOptimization[]>(`/v1/platform/models/${id}/optimizations`),
    enabled: Boolean(id),
  })

// --- publicar OTA e registrar otimização (Parte 8: antes só pela API) -----------------

export function usePublishOta() {
  return useApiMutation(
    ({ file, query }: { file: Blob; query: Record<string, string> }) =>
      apiUpload<OtaPackage>('/v1/platform/ota/packages', file, query, 'application/x-tar'),
    [['platform', 'ota']],
  )
}

export function useDeployOta() {
  return useApiMutation(
    (body: Record<string, unknown>) =>
      api<OtaDeployment[]>('/v1/platform/ota/deployments', { method: 'POST', body }),
    [['platform', 'ota']],
  )
}

export function useRegisterOptimization(id: string) {
  return useApiMutation(
    (body: Record<string, unknown>) =>
      api<ModelOptimization>(`/v1/platform/models/${id}/optimizations`, { method: 'POST', body }),
    [['platform', 'models']],
  )
}

// ---------------------------------------------------------------------------
// Centro de comando do Rover (/v1/platform/rovers/*)
// ---------------------------------------------------------------------------

export type RoverCommand = {
  id: string
  kind: string
  params: Record<string, unknown>
  state: string
  sequence: number
  created_at: string | null
  delivered_at: string | null
  finished_at: string | null
  result: Record<string, unknown> | null
  error: string | null
}

export type RoverPanel = {
  device: FleetDevice & Record<string, unknown>
  health: Record<string, unknown> | null
  health_reported_at: string | null
  control_mode: string | null
  teleop: { v: number | null; w: number | null; seq: number; valid_until: string | null; active: boolean }
  teleop_limits: { v_ms: number; w_rad_s: number; validity_s: number }
  pinned_model: { model_key: string; version: string } | null
  designated: { field_id: string; field_name: string; crop: string; model: string | null; reason: string | null }[]
  mission: { id: string; state: string; kind: string; field_id: string; started_at: string | null } | null
  commands: RoverCommand[]
  recent_results: {
    record_id: string
    type: string
    label: string | null
    confidence: number | null
    occurred_at: string | null
    camera_id: string | null
    evidence: number | null
  }[]
  telemetry: {
    t: string
    battery_percent: number | null
    temperature_c: number | null
    speed_ms: number | null
    link_quality: number | null
    rtk_fix: string
  }[]
  parts: string[]
}

export type PinnableModel = {
  model_key: string
  version: string
  name: string | null
  state: string
  crops: string[]
  platform: string
  optimized: boolean
}

const roverKey = (id: string) => ['platform', 'rover', id] as const

export const useRoverPanel = (id: string) =>
  useQuery({
    queryKey: roverKey(id),
    queryFn: () => api<RoverPanel>(`/v1/platform/rovers/${id}/painel`),
    refetchInterval: 2_000,
  })

export const useRoverModels = (id: string) =>
  useQuery({
    queryKey: [...roverKey(id), 'modelos'],
    queryFn: () => api<PinnableModel[]>(`/v1/platform/rovers/${id}/modelos`),
  })

export const useRoverCommand = (id: string) =>
  useApiMutation(
    (body: { kind: string; params?: Record<string, unknown> }) =>
      api<{ id: string; state: string }>(`/v1/platform/rovers/${id}/comandos`, { method: 'POST', body }),
    [roverKey(id)],
  )

export const useCancelRoverCommand = (id: string) =>
  useApiMutation(
    (commandId: string) => api(`/v1/platform/rovers/${id}/comandos/${commandId}/cancelar`, { method: 'POST' }),
    [roverKey(id)],
  )

export const usePinRoverModel = (id: string) =>
  useApiMutation(
    (body: { model_key: string | null; version: string | null }) =>
      api(`/v1/platform/rovers/${id}/modelo`, { method: 'PUT', body }),
    [roverKey(id)],
  )

// --- Validação do Rover: ensaios, resultados (veredito do servidor) e portões ----------

const ensaioKey = (id: string) => ['platform', 'rover', id, 'ensaios'] as const

export type EnsaiosDoRover = {
  resultados: EnsaioResultado[]
  em_curso: { id: string; params: { ensaio?: string }; state: string; progress: { fracao?: number; etapa?: string } | null; created_at: string | null }[]
}

export const useEnsaiosCatalogo = () =>
  useQuery({
    queryKey: ['platform', 'ensaios', 'catalogo'],
    queryFn: () => api<{ ensaios: DefinicaoEnsaio[]; fases: Record<string, string> }>('/v1/platform/ensaios/catalogo'),
    staleTime: 5 * 60_000,
  })

export const useRoverEnsaios = (id: string) =>
  useQuery({
    queryKey: ensaioKey(id),
    queryFn: () => api<EnsaiosDoRover>(`/v1/platform/rovers/${id}/ensaios`),
    refetchInterval: 2_000,
  })

export const useRoverPortoes = (id: string) =>
  useQuery({
    queryKey: [...ensaioKey(id), 'portoes'],
    queryFn: () => api<Portao[]>(`/v1/platform/rovers/${id}/portoes`),
    refetchInterval: 5_000,
  })

export const useMandaEnsaio = (id: string) =>
  useApiMutation(
    (body: { ensaio: string; params: Record<string, unknown> }) =>
      api<{ id: string; state: string }>(`/v1/platform/rovers/${id}/ensaios`, { method: 'POST', body }),
    [ensaioKey(id), roverKey(id)],
  )

export const useCancelaEnsaio = (id: string) =>
  useApiMutation(
    (commandId: string) => api(`/v1/platform/rovers/${id}/ensaios/${commandId}/cancelar`, { method: 'POST' }),
    [ensaioKey(id), roverKey(id)],
  )

/** Controle remoto: chamadas diretas (sem invalidar cache a cada 250 ms). */
export const sendTeleop = (id: string, v: number, w: number) =>
  api<RoverPanel['teleop']>(`/v1/platform/rovers/${id}/teleop`, { method: 'POST', body: { v, w } })

export const stopTeleop = (id: string) =>
  api<RoverPanel['teleop']>(`/v1/platform/rovers/${id}/teleop/parar`, { method: 'POST' })

// --- vídeo ao vivo (services/video_ao_vivo.py) ------------------------------------------

export type PedidoDeVideo = { cameras: string[]; fps: number; lado: number; ate: string }

/** Liga ou renova o vídeo: vence em ~12 s sem renovar (a tela renova a cada 5 s). */
export const startVideo = (id: string, cameras: string[], fps: number, lado: number) =>
  api<PedidoDeVideo>(`/v1/platform/rovers/${id}/video`, { method: 'POST', body: { cameras, fps, lado } })

export const stopVideo = (id: string) => api<void>(`/v1/platform/rovers/${id}/video`, { method: 'DELETE' })

export type QuadroAoVivo = { url: string; capturadoEm: string | null; seq: number | null; recebidoEm: number }

/** O último quadro de uma câmera (``null`` se ainda não chegou nenhum). A URL é de objeto:
 * quem guarda deve revogar a anterior. */
export async function fetchQuadroAoVivo(id: string, camera: string, signal?: AbortSignal): Promise<QuadroAoVivo | null> {
  const r = await fetch(buildUrl(`/v1/platform/rovers/${id}/video/${encodeURIComponent(camera)}`), {
    headers: authHeaders(),
    signal,
    cache: 'no-store',
  })
  if (r.status === 204) return null
  if (!r.ok) throw new Error(`vídeo ${camera}: HTTP ${r.status}`)
  const seq = r.headers.get('X-Seq')
  return {
    url: URL.createObjectURL(await r.blob()),
    capturadoEm: r.headers.get('X-Capturado-Em') || null,
    seq: seq ? Number(seq) : null,
    recebidoEm: Date.now(),
  }
}
