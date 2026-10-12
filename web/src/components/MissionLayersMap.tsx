/**
 * Mapa de uma missão em camadas (brief, seção 46): estado ou doença por planta, calor
 * de incidência, eventos da Edge AI, rota percorrida e planejada, pragas e a comparação
 * com outra passada. As camadas e a cor vêm de `lib/mapLayers.ts` (testado); aqui só
 * se desenha.
 *
 * Coordenadas da API em `[lon, lat]`; Leaflet em `[lat, lon]` — a troca é feita na hora
 * de desenhar, num lugar só.
 */
import L from 'leaflet'
import { useEffect, useMemo } from 'react'
import { CircleMarker, LayersControl, MapContainer, Polygon, Polyline, Rectangle, TileLayer, Tooltip, useMap } from 'react-leaflet'

import type { FieldOut } from '@/api/types'
import { cn } from '@/lib/cn'
import { categoryLabel } from '@/lib/edgeRecords'
import { fmt } from '@/lib/format'
import { assignSlots, disease } from '@/lib/labels'
import {
  boundsPoints,
  CHANGE_LABEL,
  CHANGE_TONE,
  changeOf,
  heatCells,
  heatOpacity,
  isPest,
  PLANT_STATUS_LABEL,
  placedPlants,
  plantColor,
  type Comparison,
  type LayerId,
  type MissionMap,
} from '@/lib/mapLayers'
import { usePalette, type Palette } from '@/lib/palette'

const toLatLng = (p: number[]): [number, number] => [p[1] ?? 0, p[0] ?? 0]

function Fit({ points, fitKey }: { points: [number, number][]; fitKey: string }) {
  const map = useMap()
  useEffect(() => {
    if (points.length) map.fitBounds(L.latLngBounds(points), { padding: [28, 28], maxZoom: 22 })
    // reenquadra só quando a missão (ou o talhão) muda
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fitKey, map])
  return null
}

export function toneColors(p: Palette) {
  return { good: p.good, warning: p.warning, serious: p.serious, critical: p.critical, info: p.info, neutral: p.muted }
}

export function diseaseColors(map: MissionMap | undefined, palette: Palette): Map<string, string> {
  const labels = [...new Set((map?.plants ?? []).map((p) => p.label).filter((l): l is string => Boolean(l)))]
  const slots = assignSlots(labels)
  return new Map(labels.map((l) => [l, palette.series[(slots.get(l) ?? 0) - 1] ?? palette.other]))
}

export function MissionLayersMap({
  map,
  field,
  layers,
  comparison,
  className,
  onPlantClick,
}: {
  map: MissionMap | undefined
  field?: FieldOut
  layers: Set<LayerId>
  comparison?: Comparison | null
  className?: string
  onPlantClick?: (plantId: string) => void
}) {
  const palette = usePalette()
  const cores = toneColors(palette)
  const porDoenca = useMemo(() => diseaseColors(map, palette), [map, palette])
  const plantas = useMemo(() => placedPlants(map?.plants ?? []), [map])
  const celulas = useMemo(() => (layers.has('calor') ? heatCells(map?.plants ?? []) : []), [map, layers])
  const pontos = useMemo(() => {
    const out = boundsPoints(map)
    if (!out.length && field) field.boundary.forEach((p) => out.push(toLatLng(p)))
    return out
  }, [map, field])

  const corDaPlanta = (p: (typeof plantas)[number]) => {
    if (layers.has('comparacao') && comparison) return cores[CHANGE_TONE[changeOf(p.plant_id, comparison)]]
    if (layers.has('doenca')) return p.label ? (porDoenca.get(p.label) ?? palette.other) : palette.muted
    return plantColor(p.status, cores)
  }
  const mostraPlantas = layers.has('incidencia') || layers.has('doenca') || (layers.has('comparacao') && comparison)

  return (
    <div className={cn('isolate overflow-hidden rounded-[14px] border border-line', className)} data-mapa-missao={map?.mission_id ?? ''}>
      <MapContainer center={[-12.724, -55.9075]} zoom={16} maxZoom={22} scrollWheelZoom className="size-full" style={{ minHeight: 280 }}>
        <LayersControl position="topright">
          <LayersControl.BaseLayer checked name="Satélite">
            <TileLayer
              url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
              attribution="Imagens &copy; Esri"
              maxZoom={22}
              maxNativeZoom={17}
            />
          </LayersControl.BaseLayer>
          <LayersControl.BaseLayer name="Mapa">
            <TileLayer url="https://tile.openstreetmap.org/{z}/{x}/{y}.png" attribution="&copy; OpenStreetMap" maxZoom={22} maxNativeZoom={19} />
          </LayersControl.BaseLayer>
        </LayersControl>
        <Fit points={pontos} fitKey={`${map?.mission_id ?? ''}:${field?.id ?? ''}:${pontos.length}`} />

        {field && (
          <Polygon
            positions={field.boundary.map(toLatLng)}
            pathOptions={{ color: palette.accent, weight: 2, fillColor: palette.accent, fillOpacity: 0.04 }}
          />
        )}

        {celulas.map((c, i) => (
          <Rectangle
            key={`calor-${i}`}
            bounds={c.bounds}
            pathOptions={{ stroke: false, fillColor: palette.critical, fillOpacity: heatOpacity(c.ratio) }}
          >
            <Tooltip>
              {c.diseased} doente(s) de {c.plants} planta(s) · {fmt.percent(c.ratio)}
              {c.suspect ? ` · ${c.suspect} suspeita(s)` : ''}
            </Tooltip>
          </Rectangle>
        ))}

        {layers.has('rota') && !!map?.planned_route.length && (
          <Polyline positions={map.planned_route.map(toLatLng)} pathOptions={{ color: palette.ink2, weight: 2, dashArray: '6 6', opacity: 0.7 }} />
        )}
        {layers.has('rota') && !!map?.track.length && (
          <Polyline positions={map.track.map(toLatLng)} pathOptions={{ color: palette.info, weight: 3, opacity: 0.9 }}>
            <Tooltip sticky>
              Rota percorrida · {map.track_points_total} posição(ões)
              {map.track_points_total > map.track.length ? ` (desenhadas ${map.track.length})` : ''}
            </Tooltip>
          </Polyline>
        )}

        {mostraPlantas &&
          plantas.map((p) => (
            <CircleMarker
              key={p.plant_id}
              center={[p.lat, p.lon]}
              radius={p.status === 'sadia' ? 4 : 6}
              pathOptions={{ color: palette.surface, weight: 1, fillColor: corDaPlanta(p), fillOpacity: 0.95 }}
              eventHandlers={onPlantClick ? { click: () => onPlantClick(p.plant_id) } : undefined}
            >
              <Tooltip>
                <strong>{p.plant_id}</strong> · {PLANT_STATUS_LABEL[p.status]}
                {p.label ? ` · ${disease(p.label)}` : ''} · {p.frames} quadro(s)
                {comparison ? ` · ${CHANGE_LABEL[changeOf(p.plant_id, comparison)]}` : ''}
              </Tooltip>
            </CircleMarker>
          ))}

        {(layers.has('eventos') || layers.has('pragas')) &&
          (map?.events ?? [])
            .filter((e) => layers.has('eventos') || isPest(e))
            .map((e) => (
              <CircleMarker
                key={e.id}
                center={[e.lat, e.lon]}
                radius={isPest(e) ? 8 : 7}
                pathOptions={{
                  color: isPest(e) ? palette.pest : palette.serious,
                  weight: 2.5,
                  fillOpacity: 0,
                  dashArray: isPest(e) ? '2 3' : undefined,
                }}
              >
                <Tooltip>
                  {categoryLabel(e.type)}
                  {e.label ? ` · ${disease(e.label)}` : ''}
                  {e.plant_id ? ` · ${e.plant_id}` : ''}
                  {e.confidence != null ? ` · ${fmt.percent(e.confidence)}` : ''}
                  {e.at ? ` · ${fmt.time(e.at)}` : ''}
                  {e.has_original ? ' · com original' : ''}
                </Tooltip>
              </CircleMarker>
            ))}
      </MapContainer>
    </div>
  )
}
