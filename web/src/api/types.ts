/**
 * Apelidos dos esquemas gerados a partir do `openapi.json` da plataforma.
 *
 * `schema.d.ts` é gerado (`npm run api:types`) e nunca editado à mão: o contrato
 * vive no backend. Se um campo mudar lá, o `tsc` acusa aqui — que é o objetivo.
 */
import type { components } from './schema'

type S = components['schemas']

export type TokenResponse = S['TokenResponse']
export type MeResponse = S['MeResponse']
export type MembershipOut = S['MembershipOut']
export type UserOut = S['UserOut']
export type Role = S['Role']
export type SessionOut = S['SessionOut']
export type SessionRevoked = S['SessionRevoked']

export type FarmOut = S['FarmOut']
export type FieldOut = S['FieldOut']
export type FieldCreate = S['FieldCreate']
export type ZoneOut = S['ZoneOut']

export type DeviceOut = S['DeviceOut']
export type DeviceModelOut = S['DeviceModelOut']
export type DeviceKind = S['DeviceKind']
export type DeviceStatus = S['DeviceStatus']
export type ProvisioningTokenOut = S['ProvisioningTokenOut']
export type TelemetryOut = S['TelemetryOut']
export type DeviceEventOut = S['DeviceEventOut']

export type MissionOut = S['MissionOut']
export type MissionCreate = S['MissionCreate']
export type MissionKind = S['MissionKind']
export type MissionState = S['MissionState']
export type MissionSegmentOut = S['MissionSegmentOut']
export type MissionHistoryOut = S['MissionHistoryOut']
export type CheckpointOut = S['CheckpointOut']
export type SafetyEvaluationOut = S['SafetyEvaluationOut']
export type SafetyCheckOut = S['SafetyCheckOut']
export type SignedCommandOut = S['SignedCommandOut']

export type ObservationOut = S['ObservationOut']
export type DiagnosisOut = S['DiagnosisOut']
export type DetectionOut = S['DetectionOut']
export type DiagnosisStatus = S['DiagnosisStatus']
export type DecisionOut = S['DecisionOut']

export type ProductOut = S['ProductOut']
export type ProductCreate = S['ProductCreate']
export type BatchOut = S['BatchOut']
export type TankOut = S['TankOut']
export type ApplicationOut = S['ApplicationOut']
export type VerificationOut = S['VerificationOut']

export type FieldSnapshotOut = S['FieldSnapshotOut']
export type TimePointOut = S['TimePointOut']
export type AnomalyOut = S['AnomalyOut']
export type AuditOut = S['AuditOut']

export type FieldSceneOut = S['FieldSceneOut']
export type SceneMarkerOut = S['SceneMarkerOut']
export type SceneScanOut = S['SceneScanOut']
export type RowScanOut = S['RowScanOut']

export type AlertOut = S['AlertOut']
export type DashboardOut = S['DashboardOut']
export type MissionBrief = S['MissionBrief']
export type HealthResponse = S['HealthResponse']

/** `[longitude, latitude]` — a ordem do GeoJSON, a mesma da API. */
export type LonLat = [number, number]

export type CollectionOut = S['CollectionOut']
export type CollectionCreate = S['CollectionCreate']
export type CollectionFileOut = S['CollectionFileOut']
export type CollectionState = S['CollectionState']
export type CollectionKind = S['CollectionKind']
export type CollectionSource = S['CollectionSource']
export type CapturePlatform = S['CapturePlatform']
export type CollectionProgress = S['CollectionProgress']
export type JobOut = S['JobOut']
export type DatasetOut = S['DatasetOut']
export type DatasetSampleOut = S['DatasetSampleOut']
export type DatasetVersionOut = S['DatasetVersionOut']
export type CatalogModelOut = S['CatalogModelOut']
export type TenantOut = S['TenantOut']
export type BoundaryRefineIn = S['BoundaryRefineIn']
export type BoundaryRefineOut = S['BoundaryRefineOut']
export type RowsOut = S['RowsOut']
export type TerrainOut = S['TerrainOut']
export type TerrainObjectOut = S['TerrainObjectOut']
export type TenantCreate = S['TenantCreate']
export type TenantUpdate = S['TenantUpdate']
export type OnboardIn = S['OnboardIn']
export type OnboardOut = S['OnboardOut']
export type PlanOut = S['PlanOut']
export type PlanRequest = S['PlanRequest']
export type ChargePostOut = S['ChargePostOut']

export type AiModelChoiceOut = S['AiModelChoiceOut']

/**
 * Uma planta do talhão, como a fusão por planta da inferência devolve.
 *
 * A rota do SaaS repassa o corpo sem esquema (`list[dict]`), então o tipo vive
 * aqui — espelho de `PlantSummary` em VALTEXA-B/app/plant_fusion.py. Só os
 * campos que o console usa.
 */
export type PlantOut = {
  plant_id: string
  row_id: string
  pass_id: string
  x_along_m: number
  status: 'sadia' | 'suspeita' | 'doente' | 'revisar'
  primary_disease: string | null
  primary_posterior: number
  incidence: number
  n_frames: number
  n_cameras: number
  zones_seen: string[]
  n_needs_review: number
  lat: number | null
  lon: number | null
}

/** Prevalência do talhão estimada sem rótulo (EM), contra a do treino do modelo. */
export type PrevalenceOut = {
  model_key: string
  field_id: string
  training_prior: Record<string, number>
  field_prior: Record<string, number>
  method: string
  effective_samples: number
  /** A contagem simples dos palpites, que o EM é comparado com (ausente em IA antiga). */
  predicted_shares?: Record<string, number> | null
  /** Distância entre o EM e a contagem simples; acima de 0,05 o modelo não está calibrado no talhão. */
  divergence?: number | null
  /** Falso quando o EM e a contagem discordam: a estimativa é indicação, não medida. */
  reliable?: boolean | null
  note?: string | null
  /** A fração de PLANTAS doentes na última passada (ausente em IA antiga). */
  plant_incidence?: PlantIncidenceOut | null
}

/**
 * Quantas plantas do talhão estão doentes — espelho de `PlantFusionStore.incidence`
 * em VALTEXA-B/app/plant_fusion.py. A `field_prior` da prevalência é a proporção de
 * cada classe nos recortes, que não é isto: uma planta com lesão numa folha dá
 * dezenas de recortes sadios.
 */
export type PlantIncidenceOut = {
  pass_id: string
  n_plants: number
  n_judged: number
  status_counts: Record<string, number>
  /** Plantas sinalizadas (suspeita ou doente) entre as julgadas. */
  apparent: number | null
  /** A aparente corrigida pela sensibilidade e pelo alarme falso medidos; nula sem calibração. */
  incidence: number | null
  ci95: [number, number] | null
  method: 'rogan_gladen' | 'aparente'
  flagged_by_disease: Record<string, number>
  calibration_id: string | null
  note: string | null
}

/** O resumo de um quadro do rover, em `signals.frame` da análise primária. */
export type FrameSignals = {
  tiles_analyzed: number
  tiles_in_scope: number
  zone_summary: Record<string, { recortes: number; com_achado: number; fora_de_escopo?: number }>
  out_of_scope: Record<string, Record<string, number>>
  class_share: Record<string, number>
  needs_review_share: number
  plants?: unknown
  sigatoka?: {
    dsi: number | null
    dsi_ci_low: number | null
    dsi_ci_high: number | null
    n_crops_used: number
    warnings: string[]
    scale_validated: boolean
  } | null
}

/** O que a IA disse além do rótulo — `DetectionOut.signals`. */
export type AiSignals = {
  in_scope?: boolean
  scene?: string
  prediction_set?: string[]
  frame?: FrameSignals
}

// --- Notificações e suporte (Parte 6) ------------------------------------------
export type NotificationOut = S['NotificationOut']
export type NotificationDeliveryOut = S['NotificationDeliveryOut']
export type NotificationPreferencesOut = S['NotificationPreferencesOut']
export type NotificationPreferenceOut = S['NotificationPreferenceOut']
export type NotificationPreferenceIn = S['NotificationPreferenceIn']
export type NotificationChannelOut = S['NotificationChannelOut']
export type TicketOut = S['TicketOut']
export type TicketDetailOut = S['TicketDetailOut']
export type TicketCommentOut = S['TicketCommentOut']
export type TicketEventOut = S['TicketEventOut']
export type TicketCreate = S['TicketCreate']
export type TicketUpdate = S['TicketUpdate']
export type IncidentOut = S['IncidentOut']
export type IncidentDetailOut = S['IncidentDetailOut']
export type TicketAssigneeOut = S['TicketAssigneeOut']
