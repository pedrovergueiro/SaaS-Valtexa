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

export type AlertOut = S['AlertOut']
export type DashboardOut = S['DashboardOut']
export type MissionBrief = S['MissionBrief']
export type HealthResponse = S['HealthResponse']

/** `[longitude, latitude]` — a ordem do GeoJSON, a mesma da API. */
export type LonLat = [number, number]
