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

import { type Satelite, useSatelite } from '@/api/queries'
import type {
  ChargePostOut,
  DeviceOut,
  FieldOut,
  MissionSegmentOut,
  ObservationOut,
  TerrainObjectOut,
  ZoneOut,
} from '@/api/types'
import { cn } from '@/lib/cn'
import { fmt } from '@/lib/format'
import {
  connectivity,
  crop,
  deviceKind,
  diagnosisStatus,
  disease,
  HEALTH,
  healthClass,
  terrainKind,
} from '@/lib/labels'
import { usePalette, type Palette } from '@/lib/palette'

type Ring = number[][]
const DEFAULT_CENTER: [number, number] = [-12.7240, -55.9075]

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
  /** Leva o mapa até esta coordenada [lat, lon], no lugar do enquadramento automático. */
  focus?: [number, number]
  focusZoom?: number
  /** Enquadra esta caixa [[sul, oeste], [norte, leste]] (uma cidade achada pelo endereço). */
  focusBounds?: [[number, number], [number, number]]
  /**
   * Rota planejada, em pernas de `[lat, lon]`.
   *
   * Já vem nessa ordem do planejador — ao contrário de tudo o mais neste mapa,
   * que chega em `[lon, lat]`. É a única exceção, e está aqui em vez de ser
   * normalizada na borda porque converter duas vezes é o erro que desenha a
   * fazenda no oceano.
   */
  route?: number[][][]
  /** Postes de recarga calculados para a rota. */
  posts?: ChargePostOut[]
  /** O que a leitura de imagem achou dentro do talhão. Contorno em `[lon, lat]`. */
  obstacles?: TerrainObjectOut[]
  /** Início e fim do percurso, quando há rota. */
  showEndpoints?: boolean
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

function FlyTo({ focus, zoom }: { focus?: [number, number]; zoom: number }) {
  const map = useMap()
  const chave = focus ? `${focus[0]}:${focus[1]}` : ''
  useEffect(() => {
    if (!focus) return
    map.setView(focus, zoom)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chave, map])
  return null
}

function FitTo({ caixa }: { caixa: [[number, number], [number, number]] }) {
  const map = useMap()
  const chave = caixa.flat().join(':')
  useEffect(() => {
    map.fitBounds(L.latLngBounds(caixa), { padding: [16, 16], maxZoom: 17 })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chave, map])
  return null
}

/**
 * Os créditos que a Map Tiles API exige: o "copyright" de cada enquadramento (muda com
 * a imagem que está na tela) e o logotipo do Google. Ver a política de atribuição da
 * Map Tiles API.
 */
function AtribuicaoGoogle({ sat }: { sat: Extract<Satelite, { provedor: 'google' }> }) {
  const map = useMap()
  useEffect(() => {
    let atual = ''
    let vivo = true
    const atualiza = async () => {
      const b = map.getBounds()
      const params = new URLSearchParams({
        session: sat.sessao,
        key: sat.chave,
        zoom: String(Math.round(map.getZoom())),
        north: String(b.getNorth()),
        south: String(b.getSouth()),
        east: String(b.getEast()),
        west: String(b.getWest()),
      })
      try {
        const r = await fetch(`https://tile.googleapis.com/tile/v1/viewport?${params}`)
        const { copyright = '' } = (await r.json()) as { copyright?: string }
        if (!vivo) return
        const texto = copyright ? `Imagens ${copyright}` : 'Imagens © Google'
        if (atual) map.attributionControl.removeAttribution(atual)
        map.attributionControl.addAttribution(texto)
        atual = texto
      } catch {
        /* sem crédito novo agora: fica o anterior */
      }
    }
    void atualiza()
    map.on('moveend', atualiza)
    return () => {
      vivo = false
      map.off('moveend', atualiza)
      if (atual) map.attributionControl.removeAttribution(atual)
    }
  }, [map, sat.sessao, sat.chave])
  return (
    <img
      src="https://maps.gstatic.com/mapfiles/api-3/images/google_white5.png"
      alt="Google"
      className="pointer-events-none absolute bottom-1.5 left-2 z-[1000] h-[18px]"
    />
  )
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

function postIcon(palette: Palette): L.DivIcon {
  return L.divIcon({
    className: '',
    iconSize: [26, 26],
    iconAnchor: [13, 13],
    html: `<div style="width:26px;height:26px;border-radius:6px;background:${palette.surface};
      border:2px solid ${palette.warning};display:grid;place-items:center;font:600 13px Inter,system-ui;
      color:${palette.warning};box-shadow:0 2px 8px rgb(0 0 0 / .35)">&#9889;</div>`,
  })
}

function endpointIcon(palette: Palette, tipo: 'inicio' | 'fim'): L.DivIcon {
  const cor = tipo === 'inicio' ? palette.good : palette.info
  const marca = tipo === 'inicio' ? '&#9679;' : '&#9873;'
  return L.divIcon({
    className: '',
    iconSize: [24, 24],
    iconAnchor: [12, 12],
    html: `<div style="width:24px;height:24px;border-radius:999px;background:${palette.surface};
      border:2px solid ${cor};display:grid;place-items:center;font:600 12px Inter,system-ui;
      color:${cor}">${marca}</div>`,
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
  focus,
  focusZoom = 17,
  focusBounds,
  route = [],
  posts = [],
  obstacles = [],
  showEndpoints = true,
}: FarmMapProps) {
  const palette = usePalette()
  const satelite = useSatelite().data
  const google = satelite?.provedor === 'google' ? satelite : null

  // Primeiro e último ponto do percurso inteiro, atravessando as pernas.
  const extremos = useMemo(() => {
    const pernas = route.filter((perna) => perna.length > 0)
    if (!pernas.length) return null
    const primeira = pernas[0]!
    const ultima = pernas[pernas.length - 1]!
    return {
      inicio: primeira[0] as [number, number],
      fim: ultima[ultima.length - 1] as [number, number],
    }
  }, [route])

  const points = useMemo(() => {
    const collected: [number, number][] = []
    const push = (ring?: Ring) => ring?.forEach((point) => collected.push(toLatLng(point)))
    if (missionPolygon?.length) push(missionPolygon)
    else if (highlightFieldId) push(fields.find((field) => field.id === highlightFieldId)?.boundary)
    else fields.forEach((field) => push(field.boundary))
    // A rota já vem em [lat, lon]; ver a nota em FarmMapProps.route.
    route.forEach((perna) => perna.forEach((ponto) => collected.push([ponto[0] ?? 0, ponto[1] ?? 0])))
    if (!collected.length) observations.forEach((row) => collected.push([row.lat, row.lon]))
    if (!collected.length) {
      devices.forEach((device) => {
        if (device.last_lat != null && device.last_lon != null) collected.push([device.last_lat, device.last_lon])
      })
    }
    return collected
  }, [missionPolygon, highlightFieldId, fields, observations, devices, route])

  const fitKey = `${missionPolygon?.length ?? 0}:${highlightFieldId ?? ''}:${fields.length}:${points.length}:${route.length}`
  const placed = devices.filter((device) => device.last_lat != null && device.last_lon != null)

  return (
    <div className={cn('isolate overflow-hidden rounded-[14px] border border-line', className)}>
      <MapContainer center={DEFAULT_CENTER} zoom={15} scrollWheelZoom className="size-full" style={{ minHeight: 240 }}>
        <LayersControl position="topright">
          {google && (
            <LayersControl.BaseLayer checked name="Satélite (Google)">
              <TileLayer
                url={`${google.url}?session=${encodeURIComponent(google.sessao)}&key=${encodeURIComponent(google.chave)}`}
                attribution="Google"
                maxZoom={21}
                maxNativeZoom={20}
              />
            </LayersControl.BaseLayer>
          )}
          <LayersControl.BaseLayer checked={!google} name="Satélite (Esri)">
            <TileLayer
              url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
              attribution="Imagens &copy; Esri"
              maxZoom={20}
              // No interior a Esri costuma ter imagem só até o zoom 17 — além
              // disso ela devolve um tile escrito "Map data not yet available",
              // que é 200 e não dá para detectar. Declarando o limite, o Leaflet
              // amplia a última imagem real em vez de pedir a que não existe.
              maxNativeZoom={17}
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

        {/* Com foco explícito, quem manda no enquadramento é ele: a pessoa
            digitou uma coordenada justamente para o mapa ir até lá. */}
        {focusBounds ? (
          <FitTo caixa={focusBounds} />
        ) : focus ? (
          <FlyTo focus={focus} zoom={focusZoom} />
        ) : (
          <FitBounds points={points} fitKey={fitKey} />
        )}
        {google && <AtribuicaoGoogle sat={google} />}
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

        {/* Obstáculos antes da rota: a rota passa por cima e continua legível
            mesmo quando atravessa uma mancha. */}
        {obstacles.map((objeto, indice) => (
          <Polygon
            key={`obst-${indice}`}
            positions={objeto.outline.map(toLatLng)}
            pathOptions={{
              color: objeto.traversable ? palette.warning : palette.critical,
              weight: 2,
              dashArray: objeto.traversable ? '5 5' : undefined,
              fillColor: objeto.traversable ? palette.warning : palette.critical,
              fillOpacity: 0.22,
            }}
          >
            <Tooltip sticky>
              <strong>{terrainKind(objeto.kind)}</strong>
              <br />
              {objeto.traversable ? 'O rover atravessa' : 'O rover desvia'} ·{' '}
              {fmt.hectares(objeto.area_ha)}
              <br />
              Palpite de cor e textura · {fmt.percent(objeto.confidence)}
            </Tooltip>
          </Polygon>
        ))}

        {route.map((perna, indice) => (
          <Polyline
            key={`rota-${indice}`}
            positions={perna as [number, number][]}
            pathOptions={{ color: palette.good, weight: 2.5, opacity: 0.9 }}
          >
            <Tooltip sticky>Passada {indice + 1} de {route.length}</Tooltip>
          </Polyline>
        ))}

        {posts.map((poste) => (
          <Marker key={poste.ordem} position={[poste.lat, poste.lon]} icon={postIcon(palette)}>
            <Tooltip>
              <strong>Poste {poste.ordem}</strong>
              <br />
              Chega com {fmt.number(poste.bateria_na_chegada_percent)}% de bateria
              <br />
              {fmt.number(poste.minutos_de_recarga)} min de recarga ·{' '}
              {fmt.hectares(poste.area_coberta_ha)} cobertos até aqui
              <br />
              {poste.motivo}
            </Tooltip>
          </Marker>
        ))}

        {showEndpoints && extremos && (
          <>
            <Marker position={extremos.inicio} icon={endpointIcon(palette, 'inicio')}>
              <Tooltip>Ponto inicial</Tooltip>
            </Marker>
            <Marker position={extremos.fim} icon={endpointIcon(palette, 'fim')}>
              <Tooltip>Ponto final</Tooltip>
            </Marker>
          </>
        )}

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

/**
 * Legenda do planejamento de missão.
 *
 * Existe porque uma rota desenhada sem legenda é um rabisco: quem valida a
 * missão precisa saber, sem perguntar, o que é trajeto, o que é bloqueio e
 * onde o rover vai parar para carregar.
 */
export function PlanLegend() {
  const palette = usePalette()
  const itens: { cor: string; forma: 'linha' | 'area' | 'ponto'; texto: string }[] = [
    { cor: palette.good, forma: 'linha', texto: 'Trajeto planejado' },
    { cor: palette.critical, forma: 'area', texto: 'Bloqueio — o rover desvia' },
    { cor: palette.warning, forma: 'area', texto: 'Caminho — o rover atravessa' },
    { cor: palette.warning, forma: 'ponto', texto: 'Poste de energia' },
    { cor: palette.good, forma: 'ponto', texto: 'Ponto inicial' },
    { cor: palette.info, forma: 'ponto', texto: 'Ponto final' },
  ]
  return (
    <ul className="flex flex-wrap gap-x-4 gap-y-1.5 text-[12px] text-ink-2">
      {itens.map((item) => (
        <li key={item.texto} className="flex items-center gap-1.5">
          <span
            aria-hidden
            className={cn(
              item.forma === 'linha' && 'h-0.5 w-4',
              item.forma === 'area' && 'size-2.5 rounded-[3px] opacity-70',
              item.forma === 'ponto' && 'size-2.5 rounded-full',
            )}
            style={{ background: item.cor }}
          />
          {item.texto}
        </li>
      ))}
    </ul>
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
