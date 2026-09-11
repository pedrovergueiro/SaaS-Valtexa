/**
 * Mapa da lavoura: talhões, zonas, frota, observações e missões.
 *
 * Coordenadas chegam da API em `[longitude, latitude]` (GeoJSON) e o Leaflet
 * trabalha em `[lat, lng]` — a conversão fica toda aqui, num lugar só, porque
 * trocar a ordem por engano desenha a fazenda no oceano.
 *
 * Observações usam só três cores (saudável, doença, aguardando agrônomo): são
 * as únicas que a paleta distingue em todos os pares, que é o que um mapa de
 * pontos exige. A doença específica fica na dica e na legenda.
 */
import L from 'leaflet'
import { useEffect, useMemo } from 'react'
import {
  CircleMarker,
  LayersControl,
  MapContainer,
  Marker,
  Polygon,
  Polyline,
  TileLayer,
  Tooltip,
  useMap,
  useMapEvents,
} from 'react-leaflet'

import type { DeviceOut, FieldOut, MissionSegmentOut, ObservationOut, ZoneOut } from '@/api/types'
import { cn } from '@/lib/cn'
import { fmt } from '@/lib/format'
import { connectivity, crop, deviceKind, diagnosisStatus, disease, HEALTH, healthClass } from '@/lib/labels'
import { usePalette, type Palette } from '@/lib/palette'

type Ring = number[][]
const DEFAULT_CENTER: [number, number] = [-22.4129, -45.4515]

export const toLatLng = (point: number[]): [number, number] => [point[1] ?? 0, point[0] ?? 0]

export type FarmMapProps = {
  fields?: FieldOut[]
  zones?: ZoneOut[]
  devices?: DeviceOut[]
  observations?: ObservationOut[]
  missionPolygon?: Ring
  segments?: MissionSegmentOut[]
  highlightFieldId?: string
  draftPolygon?: Ring
  className?: string
  onFieldClick?: (fieldId: string) => void
  onObservationClick?: (observation: ObservationOut) => void
  onMapClick?: (point: [number, number]) => void
}

function FitBounds({ points, fitKey }: { points: [number, number][]; fitKey: string }) {
  const map = useMap()
  useEffect(() => {
    if (points.length === 0) return
    map.fitBounds(L.latLngBounds(points), { padding: [28, 28], maxZoom: 18 })
    // Reenquadra só quando o conjunto muda, não a cada renderização.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fitKey, map])
  return null
}

function ClickCapture({ onClick }: { onClick: (point: [number, number]) => void }) {
  useMapEvents({ click: (event) => onClick([event.latlng.lng, event.latlng.lat]) })
  return null
}

function deviceIcon(device: DeviceOut, palette: Palette): L.DivIcon {
  const letter = { rover: 'R', drone: 'D', dock: 'B', sensor: 'S', gateway: 'G' }[device.kind] ?? '?'
  const ring =
    device.connectivity === 'ok' ? palette.good : device.connectivity === 'degraded' ? palette.warning : palette.muted
  return L.divIcon({
    className: '',
    iconSize: [30, 30],
    iconAnchor: [15, 15],
    html: `<div style="width:30px;height:30px;border-radius:999px;background:${palette.surface};
      border:3px solid ${ring};display:grid;place-items:center;font:600 12px Inter,system-ui;
      color:${palette.ink};box-shadow:0 2px 8px rgb(0 0 0 / .35)">${letter}</div>`,
  })
}

export function FarmMap({
  fields = [],
  zones = [],
  devices = [],
  observations = [],
  missionPolygon,
  segments = [],
  highlightFieldId,
  draftPolygon,
  className,
  onFieldClick,
  onObservationClick,
  onMapClick,
}: FarmMapProps) {
  const palette = usePalette()

  const points = useMemo(() => {
    const collected: [number, number][] = []
    const push = (ring?: Ring) => ring?.forEach((point) => collected.push(toLatLng(point)))
    if (missionPolygon?.length) push(missionPolygon)
    else if (highlightFieldId) push(fields.find((field) => field.id === highlightFieldId)?.boundary)
    else fields.forEach((field) => push(field.boundary))
    if (!collected.length) observations.forEach((row) => collected.push([row.lat, row.lon]))
    if (!collected.length) {
      devices.forEach((device) => {
        if (device.last_lat != null && device.last_lon != null) collected.push([device.last_lat, device.last_lon])
      })
    }
    return collected
  }, [missionPolygon, highlightFieldId, fields, observations, devices])

  const fitKey = `${missionPolygon?.length ?? 0}:${highlightFieldId ?? ''}:${fields.length}:${points.length}`
  const placed = devices.filter((device) => device.last_lat != null && device.last_lon != null)

  return (
    <div className={cn('isolate overflow-hidden rounded-[14px] border border-line', className)}>
      <MapContainer center={DEFAULT_CENTER} zoom={15} scrollWheelZoom className="size-full" style={{ minHeight: 240 }}>
        <LayersControl position="topright">
          <LayersControl.BaseLayer checked name="Satélite">
            <TileLayer
              url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
              attribution="Imagens &copy; Esri"
              maxZoom={20}
              maxNativeZoom={19}
            />
          </LayersControl.BaseLayer>
          <LayersControl.BaseLayer name="Mapa">
            <TileLayer
              url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
              attribution="&copy; OpenStreetMap"
              maxZoom={20}
              maxNativeZoom={19}
            />
          </LayersControl.BaseLayer>
        </LayersControl>

        <FitBounds points={points} fitKey={fitKey} />
        {onMapClick && <ClickCapture onClick={onMapClick} />}

        {fields.map((field) => (
          <Polygon
            key={field.id}
            positions={field.boundary.map(toLatLng)}
            pathOptions={{
              color: palette.accent,
              weight: field.id === highlightFieldId ? 3 : 2,
              fillColor: palette.accent,
              fillOpacity: field.id === highlightFieldId ? 0.12 : 0.06,
            }}
            eventHandlers={onFieldClick ? { click: () => onFieldClick(field.id) } : undefined}
          >
            <Tooltip sticky>
              <strong>{field.name}</strong> · {crop(field.crop)} · {fmt.hectares(field.area_ha)}
            </Tooltip>
          </Polygon>
        ))}

        {zones.map((zone) => (
          <Polygon
            key={zone.id}
            positions={zone.boundary.map(toLatLng)}
            pathOptions={{ color: palette.ink2, weight: 1.5, dashArray: '4 6', fillOpacity: 0.03 }}
          >
            <Tooltip sticky>{zone.name}</Tooltip>
          </Polygon>
        ))}

        {missionPolygon && missionPolygon.length > 2 && (
          <Polygon
            positions={missionPolygon.map(toLatLng)}
            pathOptions={{ color: palette.info, weight: 2, dashArray: '6 6', fillColor: palette.info, fillOpacity: 0.08 }}
          />
        )}

        {segments.map((segment) => (
          <Polyline
            key={segment.index}
            positions={segment.path.map(toLatLng)}
            pathOptions={{
              color:
                segment.state === 'done' ? palette.good : segment.state === 'in_progress' ? palette.accent : palette.muted,
              weight: 3,
              opacity: segment.state === 'pending' ? 0.55 : 0.95,
            }}
          >
            <Tooltip sticky>
              Faixa {segment.index + 1} · {segment.state === 'done' ? 'concluída' : 'pendente'}
            </Tooltip>
          </Polyline>
        ))}

        {observations.map((row) => {
          const kind = healthClass(row.label, row.diagnosis_status)
          return (
            <CircleMarker
              key={row.id}
              center={[row.lat, row.lon]}
              radius={5.5}
              pathOptions={{ color: palette.surface, weight: 1.5, fillColor: palette.health[kind], fillOpacity: 0.95 }}
              eventHandlers={onObservationClick ? { click: () => onObservationClick(row) } : undefined}
            >
              <Tooltip>
                <div>
                  <strong>{kind === 'review' ? HEALTH.review.label : disease(row.label)}</strong>
                </div>
                <div>
                  {diagnosisStatus(row.diagnosis_status)}
                  {row.confidence != null && ` · confiança ${fmt.percent(row.confidence)}`}
                </div>
                <div>{fmt.dateTime(row.captured_at)}</div>
              </Tooltip>
            </CircleMarker>
          )
        })}

        {placed.map((device) => (
          <Marker key={device.id} position={[device.last_lat ?? 0, device.last_lon ?? 0]} icon={deviceIcon(device, palette)}>
            <Tooltip>
              <strong>{device.name}</strong> · {deviceKind(device.kind)}
              <br />
              {connectivity(device.connectivity)}
              {device.battery_percent != null && ` · bateria ${fmt.number(device.battery_percent)}%`}
            </Tooltip>
          </Marker>
        ))}

        {draftPolygon && draftPolygon.length > 1 && (
          <Polygon
            positions={draftPolygon.map(toLatLng)}
            pathOptions={{ color: palette.warning, weight: 2, dashArray: '4 4', fillOpacity: 0.1 }}
          />
        )}
        {draftPolygon?.map((point, index) => (
          <CircleMarker
            key={`${point[0]}-${point[1]}-${index}`}
            center={toLatLng(point)}
            radius={4}
            pathOptions={{ color: palette.surface, weight: 1.5, fillColor: palette.warning, fillOpacity: 1 }}
          />
        ))}
      </MapContainer>
    </div>
  )
}

export function HealthLegend({ counts }: { counts?: Partial<Record<keyof typeof HEALTH, number>> }) {
  return (
    <ul className="flex flex-wrap gap-x-4 gap-y-1.5 text-[12px] text-ink-2">
      {(Object.keys(HEALTH) as (keyof typeof HEALTH)[]).map((key) => (
        <li key={key} className="flex items-center gap-1.5">
          <span className="size-2.5 rounded-full" style={{ background: HEALTH[key].color }} aria-hidden />
          {HEALTH[key].label}
          {counts?.[key] !== undefined && <span className="num text-muted">({counts[key]})</span>}
        </li>
      ))}
    </ul>
  )
}
