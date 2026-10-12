/**
 * Registros da Edge AI no console do cliente (brief, seções 11, 47).
 *
 * Vêm de `GET /v1/edge/records?mission_id=` — o que o robô analisou e sincronizou.
 * Aqui só se decide como mostrar: categoria em português, planta, arquivo original
 * quando subiu (servido por `GET /v1/edge/records/{id}/files/{upload_id}`).
 */
import type { Tone } from './labels'

export type EdgeFile = {
  upload_id: string
  role: string | null
  sha256: string
  size_bytes: number
  content_type: string
  status: string
  asset_id: string | null
}

export type EdgeRecord = {
  id: string
  record_id: string
  device_id: string
  kind: string
  type: string
  mission_id: string | null
  field_id: string | null
  occurred_at: string
  received_at: string
  severity: string | null
  label: string | null
  confidence: number | null
  model_key: string | null
  model_version: string | null
  lat: number | null
  lon: number | null
  payload: Record<string, unknown>
  files: EdgeFile[]
}

const CATEGORY: Record<string, { label: string; tone: Tone; order: number }> = {
  POSSIVEL_DOENCA: { label: 'Possível doença', tone: 'critical', order: 0 },
  POSSIVEL_PRAGA: { label: 'Possível praga', tone: 'serious', order: 1 },
  ANOMALIA: { label: 'Anomalia', tone: 'warning', order: 2 },
  BAIXA_CONFIANCA: { label: 'Baixa confiança', tone: 'info', order: 3 },
  NORMAL: { label: 'Normal', tone: 'good', order: 4 },
}

export const EVENT_CATEGORIES = new Set(['POSSIVEL_DOENCA', 'POSSIVEL_PRAGA', 'ANOMALIA'])

export const categoryLabel = (type: string) => CATEGORY[type]?.label ?? type.replaceAll('_', ' ').toLowerCase()
export const categoryTone = (type: string): Tone => CATEGORY[type]?.tone ?? 'neutral'

/** A planta diante da câmera, quando o robô soube dizer (`payload.region.plant_id`). */
export function plantOf(record: Pick<EdgeRecord, 'payload'>): string | null {
  const region = record.payload?.region
  if (region && typeof region === 'object' && 'plant_id' in region) {
    const id = (region as { plant_id?: unknown }).plant_id
    return typeof id === 'string' ? id : null
  }
  return null
}

export function cameraOf(record: Pick<EdgeRecord, 'payload'>): string | null {
  const frame = record.payload?.frame
  if (frame && typeof frame === 'object' && 'camera_id' in frame) {
    const id = (frame as { camera_id?: unknown }).camera_id
    return typeof id === 'string' ? id : null
  }
  return null
}

/** O arquivo para olhar: o original, se subiu; senão a reduzida; senão nada. */
export function viewableFile(record: Pick<EdgeRecord, 'files'>): EdgeFile | null {
  const done = record.files.filter((f) => f.status === 'complete' && f.content_type.startsWith('image/'))
  return done.find((f) => f.role === 'original') ?? done.find((f) => f.role !== 'contexto') ?? done[0] ?? null
}

export const fileUrl = (record: Pick<EdgeRecord, 'id'>, file: Pick<EdgeFile, 'upload_id'>) =>
  `/v1/edge/records/${record.id}/files/${encodeURIComponent(file.upload_id)}`

/** Contagem por categoria (só resultados), na ordem de gravidade. */
export function countByCategory(records: EdgeRecord[]): { type: string; count: number }[] {
  const counts = new Map<string, number>()
  for (const r of records) if (r.kind === 'result') counts.set(r.type, (counts.get(r.type) ?? 0) + 1)
  return [...counts.entries()]
    .map(([type, count]) => ({ type, count }))
    .sort((a, b) => (CATEGORY[a.type]?.order ?? 9) - (CATEGORY[b.type]?.order ?? 9) || a.type.localeCompare(b.type))
}

export type RecordFilter = { category: string; plant: string; onlyWithImage: boolean }

export function filterRecords(records: EdgeRecord[], filter: RecordFilter): EdgeRecord[] {
  const plant = filter.plant.trim().toLowerCase()
  return records.filter((r) => {
    if (filter.category === 'eventos' ? !EVENT_CATEGORIES.has(r.type) : filter.category && r.type !== filter.category) {
      return false
    }
    if (plant && !(plantOf(r) ?? '').toLowerCase().includes(plant)) return false
    if (filter.onlyWithImage && !viewableFile(r)) return false
    return true
  })
}
