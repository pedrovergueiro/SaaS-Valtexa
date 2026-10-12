/**
 * Camadas do mapa da lavoura (brief, seção 46).
 *
 * Cada camada declara de onde vem o dado. As que têm fonte no backend hoje
 * (incidência por planta, doença, calor, eventos da Edge AI, rota, pragas da
 * Edge AI, comparação entre passadas) são desenhadas; as que ainda não têm
 * (umidade, falhas de plantio, produtividade) existem como interface, aparecem
 * desligadas e dizem por quê — nenhum valor é inventado para preenchê-las.
 *
 * Tudo aqui é cálculo puro, testado no vitest; o desenho fica no componente.
 */
import type { Tone } from './labels'

export type MapPlant = {
  plant_id: string
  row: number | null
  status: 'doente' | 'suspeita' | 'revisar' | 'sadia'
  label: string | null
  frames: number
  lat: number | null
  lon: number | null
}

export type MapEvent = {
  id: string
  kind: string
  type: string
  label: string | null
  severity: string | null
  confidence: number | null
  lat: number
  lon: number
  at: string | null
  plant_id: string | null
  has_original: boolean
}

export type MissionMap = {
  mission_id: string
  field_id: string
  kind: string
  date: string | null
  planned_route: number[][]
  track: number[][]
  track_points_total: number
  events: MapEvent[]
  plants: MapPlant[]
  plants_without_position: number
  incidence: { diseased: number; suspect: number; ratio: number | null; by_label: Record<string, number> }
  plants_seen: number
}

export type LayerId =
  | 'incidencia'
  | 'doenca'
  | 'calor'
  | 'eventos'
  | 'rota'
  | 'pragas'
  | 'comparacao'
  | 'umidade'
  | 'falhas'
  | 'produtividade'

export type LayerDef = {
  id: LayerId
  label: string
  /** De onde vem o dado; `null` = ainda não há fonte no backend. */
  source: string | null
  /** Por que não está disponível (só quando `source` é nulo). */
  unavailable?: string
  needsComparison?: boolean
}

export const LAYERS: LayerDef[] = [
  { id: 'incidencia', label: 'Estado por planta', source: 'GET /v1/missions/{id}/map → plants' },
  { id: 'doenca', label: 'Doença por planta', source: 'GET /v1/missions/{id}/map → plants.label' },
  { id: 'calor', label: 'Mapa de calor (incidência)', source: 'plantas da missão, agregadas em células' },
  { id: 'eventos', label: 'Eventos da Edge AI', source: 'GET /v1/missions/{id}/map → events' },
  { id: 'rota', label: 'Rota percorrida e planejada', source: 'GET /v1/missions/{id}/map → track' },
  { id: 'pragas', label: 'Pragas (Edge AI)', source: 'eventos POSSÍVEL PRAGA da Edge AI' },
  {
    id: 'comparacao',
    label: 'Comparação entre passadas',
    source: 'GET /v1/missions/{id}/comparison',
    needsComparison: true,
  },
  {
    id: 'umidade',
    label: 'Umidade do solo',
    source: null,
    unavailable: 'Sem sensor de umidade definido na HAL nem dado no banco.',
  },
  {
    id: 'falhas',
    label: 'Falhas de plantio',
    source: null,
    unavailable: 'Precisa do mapa de plantas de campo (planta esperada × vista).',
  },
  {
    id: 'produtividade',
    label: 'Produtividade',
    source: null,
    unavailable: 'Sem dado de colheita/produção integrado.',
  },
]

export const layerAvailable = (layer: LayerDef, hasComparison: boolean): boolean =>
  layer.source !== null && (!layer.needsComparison || hasComparison)

// --- cor por estado da planta ----------------------------------------------------------

export const PLANT_STATUS_TONE: Record<MapPlant['status'], Tone> = {
  doente: 'critical',
  revisar: 'warning',
  suspeita: 'serious',
  sadia: 'good',
}

export const PLANT_STATUS_LABEL: Record<MapPlant['status'], string> = {
  doente: 'Doente',
  revisar: 'Com o agrônomo',
  suspeita: 'Suspeita',
  sadia: 'Sadia',
}

export type ToneColors = Record<'good' | 'warning' | 'serious' | 'critical' | 'info' | 'neutral', string>

export function plantColor(status: MapPlant['status'], colors: ToneColors): string {
  return colors[PLANT_STATUS_TONE[status] as keyof ToneColors] ?? colors.neutral
}

/** Plantas que dá para desenhar (têm posição). */
export const placedPlants = (plants: MapPlant[]) =>
  plants.filter((p): p is MapPlant & { lat: number; lon: number } => p.lat != null && p.lon != null)

// --- mapa de calor -------------------------------------------------------------------

export type HeatCell = {
  /** Canto sudoeste e nordeste, [lat, lon]. */
  bounds: [[number, number], [number, number]]
  plants: number
  diseased: number
  suspect: number
  /** Doentes / plantas da célula. */
  ratio: number
}

/**
 * Agrega as plantas em células de `cellMeters` (padrão 10 m) e calcula a incidência
 * de cada uma. Célula sem planta não aparece: ausência de dado não é "sadio".
 */
export function heatCells(plants: MapPlant[], cellMeters = 10): HeatCell[] {
  const placed = placedPlants(plants)
  if (!placed.length) return []
  const lat0 = placed.reduce((s, p) => s + p.lat, 0) / placed.length
  const dLat = cellMeters / 111_320
  const dLon = cellMeters / (111_320 * Math.max(0.01, Math.cos((lat0 * Math.PI) / 180)))
  const cells = new Map<string, HeatCell>()
  for (const p of placed) {
    const i = Math.floor(p.lat / dLat)
    const j = Math.floor(p.lon / dLon)
    const key = `${i}:${j}`
    let cell = cells.get(key)
    if (!cell) {
      cell = {
        bounds: [
          [i * dLat, j * dLon],
          [(i + 1) * dLat, (j + 1) * dLon],
        ],
        plants: 0,
        diseased: 0,
        suspect: 0,
        ratio: 0,
      }
      cells.set(key, cell)
    }
    cell.plants += 1
    if (p.status === 'doente') cell.diseased += 1
    else if (p.status === 'suspeita' || p.status === 'revisar') cell.suspect += 1
  }
  for (const cell of cells.values()) cell.ratio = cell.diseased / cell.plants
  return [...cells.values()]
}

/** Opacidade da célula: 0 doente → quase transparente; 100 % → forte. */
export const heatOpacity = (ratio: number) => 0.12 + 0.6 * Math.min(1, Math.max(0, ratio))

// --- comparação entre passadas --------------------------------------------------------

export type Comparison = {
  incidence_before: number | null
  incidence_after: number | null
  delta: number | null
  plants_compared: number
  recovered: string[]
  persisting: string[]
  new: string[]
}

export type ChangeClass = 'recuperada' | 'persistente' | 'nova' | 'sem_mudanca'

export const CHANGE_LABEL: Record<ChangeClass, string> = {
  recuperada: 'Recuperada',
  persistente: 'Persistente',
  nova: 'Nova ocorrência',
  sem_mudanca: 'Sem mudança',
}

export const CHANGE_TONE: Record<ChangeClass, keyof ToneColors> = {
  recuperada: 'good',
  persistente: 'critical',
  nova: 'warning',
  sem_mudanca: 'neutral',
}

export function changeOf(plantId: string, comparison: Comparison | null | undefined): ChangeClass {
  if (!comparison) return 'sem_mudanca'
  if (comparison.recovered.includes(plantId)) return 'recuperada'
  if (comparison.persisting.includes(plantId)) return 'persistente'
  if (comparison.new.includes(plantId)) return 'nova'
  return 'sem_mudanca'
}

// --- eventos ------------------------------------------------------------------------

export const isPest = (event: Pick<MapEvent, 'type'>) => event.type === 'POSSIVEL_PRAGA'

/** Pontos para enquadrar o mapa: plantas, eventos e rota, em [lat, lon]. */
export function boundsPoints(map: MissionMap | undefined | null): [number, number][] {
  if (!map) return []
  const out: [number, number][] = []
  for (const p of placedPlants(map.plants)) out.push([p.lat, p.lon])
  for (const e of map.events) out.push([e.lat, e.lon])
  for (const pt of map.track) if (pt.length >= 2) out.push([pt[1]!, pt[0]!])
  return out
}

/** Contagem por estado, para a legenda. */
export function statusCounts(plants: MapPlant[]): Record<MapPlant['status'], number> {
  const out = { doente: 0, suspeita: 0, revisar: 0, sadia: 0 }
  for (const p of plants) out[p.status] += 1
  return out
}
