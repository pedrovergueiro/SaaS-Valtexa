import { ArrowLeft, Crosshair, Footprints, Layers, Map as MapIcon, ScanLine, X } from 'lucide-react'
import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { apiBlob } from '@/api/client'
import { useFields, useScene } from '@/api/queries'
import type { FieldOut, FieldSceneOut, SceneMarkerOut, SceneScanOut } from '@/api/types'
import { useAuth } from '@/auth/AuthProvider'
import { AuthImage } from '@/components/AuthImage'
import { CategoryGlyph } from '@/components/twin3d/CategoryGlyph'
import {
  FieldScene,
  type Category,
  type ColorMode,
  type Hover,
  type SceneTheme,
} from '@/components/twin3d/FieldScene'
import { Badge, Button, Card, CardHeader, Empty, ErrorBox, Meter, Modal, PageHeader, Spinner, Tabs } from '@/components/ui'
import { cn } from '@/lib/cn'
import { fmt } from '@/lib/format'
import { category as categoryName, crop, diagnosisStatus, diagnosisTone, disease } from '@/lib/labels'
import { usePalette, type Palette } from '@/lib/palette'
import { parsePly } from '@/lib/ply'
import { useTheme } from '@/lib/theme'

/**
 * A cópia 3D da lavoura.
 *
 * O rover monta a cópia rua a rua: cada passada com o sensor 3D preenche a
 * faixa que ele percorreu, e o que ele ainda não percorreu fica em branco — de
 * propósito, para ninguém decidir olhando para planta que não foi medida. Em
 * cima da cópia, cada foto diagnosticada vira um marcador preso à planta
 * fotografada: praga, doença, o que ainda espera o agrônomo.
 */

type Window = '7' | '30' | '90'
type CloudState = 'loading' | 'shown' | 'error'
type MarkerHover = Extract<Hover, { kind: 'marker' }>

const PROBLEMS: Category[] = ['pest', 'disease', 'review', 'other']
const LEGEND: Category[] = ['pest', 'disease', 'review', 'other', 'healthy']
const PRIORITY: Record<string, number> = { pest: 0, disease: 1, review: 2, other: 3, healthy: 4 }
const MODES: { value: ColorMode; label: string }[] = [
  { value: 'appearance', label: 'Aparência' },
  { value: 'height', label: 'Altura' },
  { value: 'age', label: 'Passada' },
]
const LANES_SHOWN = 12
const panel =
  'pointer-events-auto rounded-[12px] border border-line bg-surface/92 shadow-[var(--shadow)] backdrop-blur-sm'

function sceneTheme(palette: Palette, dark: boolean): SceneTheme {
  return {
    dark,
    horizon: palette.skyHorizon || (dark ? '#0f1e18' : '#e5ede3'),
    ground: dark ? '#111b16' : '#dde2d1',
    soil: dark ? '#2b241d' : '#bca78b',
    soilScanned: dark ? '#3a2e24' : '#9e8567',
    border: palette.muted,
    zone: palette.ink2,
    accent: palette.accent,
    categories: {
      pest: palette.pest,
      disease: palette.series[1] ?? '#eb6834',
      review: palette.series[0] ?? '#2a78d6',
      other: palette.other,
      healthy: palette.series[2] ?? '#1baf7a',
    },
    leaf: dark ? ['#4d9a3c', '#a89a58'] : ['#478c36', '#b8a55a'],
    // Magnitude em um só matiz: claro→escuro no tema claro; no escuro, apagado→aceso.
    heightRamp: dark ? ['#26492f', '#4f9147', '#bfe6a6'] : ['#dcefcb', '#6aad5d', '#1b5a2c'],
    ageRamp: dark ? ['#5cae47', '#4b514d'] : ['#4c9738', '#c9c2b2'],
  }
}

export default function Field3D() {
  const { id } = useParams()
  const navigate = useNavigate()
  const fields = useFields()
  const fieldId = id ?? fields.data?.[0]?.id

  useEffect(() => {
    if (!id && fieldId) navigate(`/lavoura-3d/${fieldId}`, { replace: true })
  }, [id, fieldId, navigate])

  if (fields.isLoading) return <Spinner label="Abrindo a lavoura" />
  if (fields.error) return <ErrorBox error={fields.error} />
  const field = fields.data?.find((item) => item.id === fieldId)
  if (!field) {
    return (
      <Empty title="Nenhum talhão para mostrar">
        Cadastre um talhão em Talhões. A cópia 3D dele começa a existir na primeira varredura do rover.
      </Empty>
    )
  }
  // A chave recria a cena ao trocar de talhão: câmera, filtros e nuvens abertas
  // são de um talhão, não da página.
  return <FieldCopy key={field.id} field={field} fields={fields.data ?? []} />
}

function FieldCopy({ field, fields }: { field: FieldOut; fields: FieldOut[] }) {
  const navigate = useNavigate()
  const { can } = useAuth()
  const [days, setDays] = useState<Window>('30')
  const [at, setAt] = useState<string | null>(null)
  const [mode, setMode] = useState<ColorMode>('appearance')
  const [visible, setVisible] = useState<Set<Category>>(() => new Set(PROBLEMS))
  const [hover, setHover] = useState<Hover>(null)
  const [marker, setMarker] = useState<SceneMarkerOut | null>(null)
  const [plant, setPlant] = useState<number | null>(null)
  const [clouds, setClouds] = useState<Record<string, CloudState>>({})
  const [allLanes, setAllLanes] = useState(false)

  const scene = useScene(field.id, at, Number(days))
  const data = scene.data?.field_id === field.id ? scene.data : undefined

  const palette = usePalette()
  const { resolved } = useTheme()
  const theme = useMemo(() => sceneTheme(palette, resolved === 'dark'), [palette, resolved])
  const container = useRef<HTMLDivElement>(null)
  const engine = useRef<FieldScene | null>(null)
  const initial = useRef({ theme, mode, visible })

  useEffect(() => {
    const element = container.current
    if (!element) return
    const instance = new FieldScene(element, initial.current.theme, {
      onHover: setHover,
      onSelectMarker: (item) => {
        setPlant(null)
        setMarker(item)
        instance.focusMarker(item)
      },
      onSelectPlant: (index) => {
        setMarker(null)
        setPlant(index)
      },
    })
    instance.setColorMode(initial.current.mode)
    instance.setVisible(initial.current.visible)
    engine.current = instance
    return () => {
      instance.dispose()
      engine.current = null
    }
  }, [])

  useEffect(() => engine.current?.setTheme(theme), [theme])
  useEffect(() => {
    if (data) engine.current?.setData(data)
  }, [data])
  useEffect(() => engine.current?.setColorMode(mode), [mode])
  useEffect(() => engine.current?.setVisible(visible), [visible])

  const lanes = useMemo(() => (data ? laneNumbers(data) : []), [data])
  const summary = useMemo(() => (data ? summarize(data) : null), [data])
  const problems = useMemo(
    () =>
      (data?.markers ?? [])
        .filter((item) => PROBLEMS.includes(item.category as Category))
        .sort(
          (a, b) =>
            (PRIORITY[a.category] ?? 9) - (PRIORITY[b.category] ?? 9) ||
            (b.severity ?? 0) - (a.severity ?? 0) ||
            b.captured_at.localeCompare(a.captured_at),
        ),
    [data],
  )
  const laneOf = (index: number | null | undefined) =>
    index != null && lanes[index] != null ? `Rua ${lanes[index]}` : 'fora das ruas escaneadas'

  const toggle = (item: Category) =>
    setVisible((current) => {
      const next = new Set(current)
      if (next.has(item)) next.delete(item)
      else next.add(item)
      return next
    })

  const select = (item: SceneMarkerOut) => {
    setPlant(null)
    setMarker(item)
    engine.current?.focusMarker(item)
  }

  async function toggleCloud(scan: SceneScanOut, index: number) {
    const instance = engine.current
    if (!instance) return
    if (instance.hasCloud(scan.id)) {
      instance.hideCloud(scan.id)
      setClouds((state) => {
        const next = { ...state }
        delete next[scan.id]
        return next
      })
      return
    }
    setClouds((state) => ({ ...state, [scan.id]: 'loading' }))
    try {
      const blob = await apiBlob(`/v1/row-scans/${scan.id}/pointcloud`)
      const cloud = parsePly(await blob.arrayBuffer())
      if (engine.current !== instance) return
      instance.showCloud(scan.id, cloud)
      instance.walkLane(index)
      setClouds((state) => ({ ...state, [scan.id]: 'shown' }))
    } catch {
      setClouds((state) => ({ ...state, [scan.id]: 'error' }))
    }
  }

  const lastPass = data?.scans[0]?.captured_at
  const width = container.current?.clientWidth ?? 0

  return (
    <>
      <Link
        to={`/talhoes/${field.id}`}
        className="mb-3 inline-flex items-center gap-1.5 text-[13px] text-muted hover:text-ink"
      >
        <ArrowLeft className="size-4" aria-hidden /> {field.name}
      </Link>
      <PageHeader
        eyebrow="Cópia 3D da lavoura"
        title={field.name}
        subtitle={
          <>
            {crop(field.crop)} · montada rua a rua pelo rover
            {data && <> · {fmt.percent(data.coverage_ratio)} do talhão já tem cópia</>}
            {lastPass && <> · última passada {fmt.ago(lastPass)}</>}
          </>
        }
        actions={
          <>
            {fields.length > 1 && (
              <select
                className="input h-10 w-auto py-1"
                value={field.id}
                onChange={(event) => navigate(`/lavoura-3d/${event.target.value}`)}
                aria-label="Talhão"
              >
                {fields.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name}
                  </option>
                ))}
              </select>
            )}
            <Tabs<Window>
              value={days}
              onChange={setDays}
              items={[
                { value: '7', label: '7 dias' },
                { value: '30', label: '30 dias' },
                { value: '90', label: '90 dias' },
              ]}
            />
          </>
        }
      />

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_22rem]">
        <Card className="overflow-hidden">
          <div className="scene-sky relative h-[min(74vh,800px)] min-h-[480px]">
            <div ref={container} className="absolute inset-0" />

            <div className="pointer-events-none absolute inset-0 flex flex-col justify-between gap-3 p-3">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <Legend counts={data?.counts} visible={visible} onToggle={toggle} />
                <div className="flex flex-col items-end gap-2">
                  <div className={cn(panel, 'flex gap-1 p-1')}>
                    <ViewButton icon={<Layers className="size-4" />} onClick={() => engine.current?.view('overview')}>
                      Visão geral
                    </ViewButton>
                    <ViewButton icon={<MapIcon className="size-4" />} onClick={() => engine.current?.view('top')}>
                      De cima
                    </ViewButton>
                  </div>
                  <div className="pointer-events-auto">
                    <Tabs<ColorMode> value={mode} onChange={setMode} items={MODES} />
                  </div>
                </div>
              </div>
              <div className="flex flex-wrap items-end justify-between gap-2">
                {summary && <ModeLegend mode={mode} theme={theme} summary={summary} />}
                {data && data.passes.length > 0 && <Timeline passes={data.passes} at={at} onChange={setAt} />}
              </div>
            </div>

            {data && !data.live && (
              <div className={cn(panel, 'absolute top-3 left-1/2 flex -translate-x-1/2 items-center gap-3 px-3 py-2 text-[12px]')}>
                <span>
                  Cópia como estava em <strong>{fmt.dateTime(data.at)}</strong>
                </span>
                <button type="button" className="font-medium text-accent hover:underline" onClick={() => setAt(null)}>
                  Voltar para agora
                </button>
              </div>
            )}

            {hover?.kind === 'marker' && <MarkerTooltip hover={hover} width={width} />}

            {plant != null && data && (
              <PlantCard
                data={data}
                index={plant}
                lane={laneOf(data.plants.scan[plant])}
                onFocus={() => engine.current?.focusPlant(plant)}
                onClose={() => setPlant(null)}
              />
            )}

            {!data && scene.isFetching && (
              <div className="absolute inset-0 grid place-items-center">
                <div className={cn(panel, 'px-4')}>
                  <Spinner label="Montando a cópia" />
                </div>
              </div>
            )}
            {scene.error && (
              <div className="absolute inset-x-3 top-16">
                <ErrorBox error={scene.error} />
              </div>
            )}

            {data && data.scans.length === 0 && (
              <div className="absolute inset-0 grid place-items-center p-6">
                <div className={cn(panel, 'flex max-w-md flex-col items-center gap-2 p-6 text-center')}>
                  <ScanLine className="size-6 text-muted" aria-hidden />
                  <div className="font-medium">O rover ainda não passou por este talhão</div>
                  <p className="text-[13px] text-ink-2">
                    A cópia 3D é montada rua a rua: cada passada do rover com o sensor 3D preenche a faixa que ele
                    percorreu. O que ele não percorreu fica em branco — nada aqui é desenhado sem medida.
                  </p>
                  {can('mission:create') && (
                    <Link to="/missoes" className="mt-1">
                      <Button variant="primary">Planejar uma varredura</Button>
                    </Link>
                  )}
                </div>
              </div>
            )}
          </div>
        </Card>

        <aside className="flex min-w-0 flex-col gap-4">
          {data && summary && (
            <Card>
              <CardHeader
                title="O que o rover mediu"
                subtitle={data.live ? 'Estado atual da cópia' : `Estado em ${fmt.dateTime(data.at)}`}
              />
              <div className="grid grid-cols-2 gap-x-4 gap-y-3 px-5">
                <Figure
                  label="Cobertura"
                  value={fmt.percent(data.coverage_ratio)}
                  hint={`${fmt.hectares(data.scanned_area_m2 / 10_000)} de ${fmt.hectares(data.field_area_m2 / 10_000)}`}
                />
                <Figure label="Plantas medidas" value={fmt.number(summary.count)} hint={`${data.scans.length} ruas`} />
                <Figure
                  label="Altura média"
                  value={summary.mean == null ? '—' : `${fmt.number(summary.mean, 2)} m`}
                  hint={summary.low == null ? undefined : `${fmt.number(summary.low, 2)} a ${fmt.number(summary.high, 2)} m`}
                />
                <Figure
                  label="Verde baixo"
                  value={fmt.percent(summary.stressed)}
                  hint="índice abaixo de 0,6: sintoma, sem dizer a causa"
                />
              </div>
              <div className="px-5 pt-3 pb-5">
                <Meter value={data.coverage_ratio} label="Quanto do talhão já tem cópia" />
              </div>
            </Card>
          )}

          {data?.missions.map((mission) => (
            <Card key={mission.mission_id}>
              <div className="flex flex-col gap-2 p-4">
                <div className="flex items-center justify-between gap-2 text-[13px]">
                  <span className="font-medium">Varredura em andamento</span>
                  <span className="num text-ink-2">
                    {mission.done} de {mission.segments} ruas
                  </span>
                </div>
                <Meter value={mission.segments ? mission.done / mission.segments : 0} label="Ruas percorridas" />
                <p className="text-[12px] text-muted">
                  As ruas tracejadas na cópia são as que faltam. Cada uma aparece aqui assim que o rover a termina.
                </p>
                <Link to={`/missoes/${mission.mission_id}`} className="text-[13px] font-medium text-accent hover:underline">
                  Abrir a missão
                </Link>
              </div>
            </Card>
          ))}

          <Card>
            <CardHeader
              title="Pontos de atenção"
              subtitle="Pragas e doenças fotografadas nas ruas. Clique para ir até a planta."
            />
            {problems.length === 0 ? (
              <p className="px-5 pb-5 text-[13px] text-muted">
                Nenhuma praga, doença ou foto pendente nos últimos {days} dias.
              </p>
            ) : (
              <ul className="max-h-[22rem] overflow-y-auto">
                {problems.slice(0, 80).map((item) => (
                  <li key={item.observation_id}>
                    <button
                      type="button"
                      onClick={() => select(item)}
                      className="flex w-full items-center gap-3 border-t border-line-soft px-5 py-2.5 text-left hover:bg-raised"
                    >
                      <CategoryGlyph category={item.category as Category} size={15} />
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-[13px] font-medium">{markerTitle(item)}</span>
                        <span className="block text-[12px] text-muted">
                          {laneOf(item.scan)} · {fmt.ago(item.captured_at)}
                          {item.severity ? ` · ${fmt.percent(item.severity)} lesionado` : ''}
                        </span>
                      </span>
                      <Crosshair className="size-4 shrink-0 text-muted" aria-hidden />
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          {data && data.scans.length > 0 && (
            <Card>
              <CardHeader title="Ruas percorridas" subtitle="Cada passada substitui a faixa que o sensor enxergou." />
              <ul className="max-h-[28rem] overflow-y-auto">
                {(allLanes ? data.scans : data.scans.slice(0, LANES_SHOWN)).map((scan, index) => (
                  <li key={scan.id} className="border-t border-line-soft px-5 py-3">
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-[13px] font-medium">Rua {lanes[index]}</span>
                      <span className="text-[11px] text-muted" title={fmt.dateTime(scan.captured_at)}>
                        {fmt.ago(scan.captured_at)}
                      </span>
                    </div>
                    <div className="mt-0.5 text-[12px] text-ink-2">
                      {fmt.number(scan.plant_count)} plantas · {fmt.number(scan.mean_height_m, 2)} m em média ·{' '}
                      {fmt.meters(scan.length_m)}
                      {scan.visible_plants === 0 && ' · coberta por passada mais nova'}
                    </div>
                    {Object.keys(scan.markers).length > 0 && (
                      <div className="mt-1.5 flex flex-wrap gap-2 text-[12px] text-ink-2">
                        {LEGEND.filter((item) => scan.markers[item]).map((item) => (
                          <span key={item} className="inline-flex items-center gap-1">
                            <CategoryGlyph category={item} size={11} />
                            <span className="num">{scan.markers[item]}</span>
                          </span>
                        ))}
                      </div>
                    )}
                    <div className="mt-2 flex flex-wrap gap-2">
                      <Button size="sm" icon={<Footprints className="size-4" />} onClick={() => engine.current?.walkLane(index)}>
                        Andar na rua
                      </Button>
                      {scan.has_pointcloud && (
                        <Button
                          size="sm"
                          icon={<ScanLine className="size-4" />}
                          loading={clouds[scan.id] === 'loading'}
                          onClick={() => void toggleCloud(scan, index)}
                        >
                          {clouds[scan.id] === 'shown' ? 'Esconder nuvem' : 'Nuvem de pontos'}
                        </Button>
                      )}
                    </div>
                    {clouds[scan.id] === 'error' && (
                      <p className="mt-1 text-[12px] text-critical">Não consegui abrir a nuvem desta rua.</p>
                    )}
                  </li>
                ))}
              </ul>
              {data.scans.length > LANES_SHOWN && (
                <button
                  type="button"
                  onClick={() => setAllLanes((value) => !value)}
                  className="w-full border-t border-line-soft px-5 py-2.5 text-[13px] text-ink-2 hover:bg-raised"
                >
                  {allLanes ? 'Mostrar menos' : `Mostrar as ${data.scans.length} ruas`}
                </button>
              )}
            </Card>
          )}
        </aside>
      </div>

      {marker && (
        <MarkerDialog
          marker={marker}
          lane={laneOf(marker.scan)}
          canReview={can('diagnosis:review')}
          onClose={() => setMarker(null)}
        />
      )}
    </>
  )
}

// --- sobreposições ----------------------------------------------------------------

function Legend({
  counts,
  visible,
  onToggle,
}: {
  counts: Record<string, number> | undefined
  visible: Set<Category>
  onToggle: (item: Category) => void
}) {
  return (
    <div className={cn(panel, 'flex flex-col p-1.5')} role="group" aria-label="O que mostrar na cópia">
      {LEGEND.map((item) => {
        const on = visible.has(item)
        return (
          <button
            key={item}
            type="button"
            onClick={() => onToggle(item)}
            aria-pressed={on}
            className={cn(
              'flex items-center gap-2 rounded-[8px] px-2 py-1 text-left text-[12px] transition-opacity hover:bg-raised',
              !on && 'opacity-45',
            )}
          >
            <CategoryGlyph category={item} size={13} />
            <span className="flex-1 text-ink">{categoryName(item)}</span>
            <span className="num min-w-6 text-right text-muted">{counts?.[item] ?? 0}</span>
          </button>
        )
      })}
    </div>
  )
}

function ViewButton({ icon, onClick, children }: { icon: ReactNode; onClick: () => void; children: ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="inline-flex h-8 items-center gap-1.5 rounded-[9px] px-2.5 text-[13px] font-medium text-ink-2 hover:bg-raised hover:text-ink"
    >
      {icon}
      <span className="hidden sm:inline">{children}</span>
    </button>
  )
}

type Summary = ReturnType<typeof summarize>

function ModeLegend({ mode, theme, summary }: { mode: ColorMode; theme: SceneTheme; summary: Summary }) {
  const [stops, left, right, caption] =
    mode === 'height'
      ? [
          theme.heightRamp,
          summary.low == null ? '—' : `${fmt.number(summary.low, 2)} m`,
          summary.high == null ? '—' : `${fmt.number(summary.high, 2)} m`,
          'Altura medida de cada planta',
        ]
      : mode === 'age'
        ? [theme.ageRamp, 'hoje', `há ${summary.oldest} dias`, 'Idade da passada que mediu a planta']
        : [theme.leaf, 'verde', 'amarelado', 'Índice de verde medido pelo sensor']
  return (
    <div className={cn(panel, 'w-56 px-3 py-2')}>
      <div className="text-[11px] font-medium text-muted">{caption}</div>
      <div className="mt-1.5 h-2 rounded-full" style={{ background: `linear-gradient(90deg, ${stops.join(', ')})` }} />
      <div className="mt-1 flex justify-between text-[11px] text-ink-2">
        <span>{left}</span>
        <span>{right}</span>
      </div>
    </div>
  )
}

function Timeline({
  passes,
  at,
  onChange,
}: {
  passes: FieldSceneOut['passes']
  at: string | null
  onChange: (value: string | null) => void
}) {
  const days = [...passes].reverse().slice(0, 8)
  return (
    <div className={cn(panel, 'flex max-w-full items-center gap-1 overflow-x-auto p-1')} role="group" aria-label="Estado da cópia">
      <span className="px-2 text-[11px] font-medium whitespace-nowrap text-muted">Estado em</span>
      <Chip active={at === null} onClick={() => onChange(null)}>
        Agora
      </Chip>
      {days.map((pass) => {
        const end = endOfDay(pass.day)
        return (
          <Chip key={pass.day} active={at === end} onClick={() => onChange(end)} title={`${pass.scans} ruas escaneadas`}>
            {fmt.dayMonth(new Date(`${pass.day}T12:00:00`))}
          </Chip>
        )
      })}
    </div>
  )
}

function Chip({
  active,
  onClick,
  children,
  title,
}: {
  active: boolean
  onClick: () => void
  children: ReactNode
  title?: string
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={title}
      aria-pressed={active}
      className={cn(
        'h-7 rounded-[8px] px-2.5 text-[12px] font-medium whitespace-nowrap transition-colors',
        active ? 'bg-accent text-accent-ink' : 'text-ink-2 hover:bg-raised',
      )}
    >
      {children}
    </button>
  )
}

function MarkerTooltip({ hover, width }: { hover: MarkerHover; width: number }) {
  const { marker, x, y } = hover
  const left = width && x + 280 > width ? x - 268 : x + 16
  return (
    <div
      className="pointer-events-none absolute z-10 w-64 rounded-[10px] border border-line bg-surface px-3 py-2 text-[12px] shadow-[var(--shadow)]"
      style={{ left, top: y + 16 }}
    >
      <div className="flex items-center gap-1.5 text-[13px] font-medium">
        <CategoryGlyph category={marker.category as Category} size={12} />
        {markerTitle(marker)}
      </div>
      <div className="mt-0.5 text-ink-2">
        {categoryName(marker.category)} · {fmt.ago(marker.captured_at)}
        {marker.severity != null && marker.category !== 'healthy' && ` · ${fmt.percent(marker.severity)} lesionado`}
      </div>
      <div className="mt-1 text-muted">Clique para ver a foto</div>
    </div>
  )
}

function PlantCard({
  data,
  index,
  lane,
  onFocus,
  onClose,
}: {
  data: FieldSceneOut
  index: number
  lane: string
  onFocus: () => void
  onClose: () => void
}) {
  const scan = data.scans[data.plants.scan[index] ?? -1]
  const green = data.plants.greenness[index]
  const found = data.markers.find((item) => item.plant === index)
  return (
    <div className={cn(panel, 'absolute bottom-[5.75rem] left-3 z-10 w-72 p-3 text-[12px]')}>
      <div className="flex items-center justify-between">
        <span className="text-[13px] font-medium">Planta medida</span>
        <button type="button" onClick={onClose} className="rounded p-1 text-muted hover:bg-raised" aria-label="Fechar">
          <X className="size-4" />
        </button>
      </div>
      <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1">
        <dt className="text-muted">Altura</dt>
        <dd className="num">{fmt.number(data.plants.height[index], 2)} m</dd>
        <dt className="text-muted">Copa</dt>
        <dd className="num">{fmt.number(data.plants.canopy[index], 2)} m</dd>
        <dt className="text-muted">Índice de verde</dt>
        <dd className="num">{green == null ? 'sem cor no sensor' : fmt.number(green, 2)}</dd>
        <dt className="text-muted">Onde</dt>
        <dd>{lane}</dd>
        {scan && (
          <>
            <dt className="text-muted">Medida</dt>
            <dd>
              {fmt.dateTime(scan.captured_at)}
              {scan.device_name ? ` · ${scan.device_name}` : ''}
            </dd>
          </>
        )}
        {found && (
          <>
            <dt className="text-muted">Foto</dt>
            <dd className="flex items-center gap-1">
              <CategoryGlyph category={found.category as Category} size={11} /> {markerTitle(found)}
            </dd>
          </>
        )}
      </dl>
      <Button size="sm" className="mt-3" icon={<Crosshair className="size-4" />} onClick={onFocus}>
        Ver de perto
      </Button>
    </div>
  )
}

function MarkerDialog({
  marker,
  lane,
  canReview,
  onClose,
}: {
  marker: SceneMarkerOut
  lane: string
  canReview: boolean
  onClose: () => void
}) {
  const kind = marker.category as Category
  return (
    <Modal
      open
      onClose={onClose}
      title={
        <span className="inline-flex items-center gap-2">
          <CategoryGlyph category={kind} size={16} />
          {markerTitle(marker)}
        </span>
      }
      description={`${categoryName(kind)} · ${fmt.dateTime(marker.captured_at)} · ${lane}`}
      footer={
        <>
          <Button onClick={onClose}>Fechar</Button>
          {kind === 'review' && canReview && (
            <Link to="/revisao">
              <Button variant="primary">Abrir na fila do agrônomo</Button>
            </Link>
          )}
        </>
      }
    >
      <div className="flex flex-col gap-3">
        <AuthImage
          path={`/v1/observations/${marker.observation_id}/image`}
          alt="Foto tirada pelo rover"
          className="aspect-[4/3] w-full rounded-[10px]"
        />
        <div className="flex flex-wrap items-center gap-2 text-[13px] text-ink-2">
          <Badge tone={diagnosisTone(marker.status)}>{diagnosisStatus(marker.status)}</Badge>
          {marker.confidence != null && <span>confiança {fmt.percent(marker.confidence)}</span>}
          {marker.severity != null && kind !== 'healthy' && <span>área lesionada {fmt.percent(marker.severity)}</span>}
          {marker.novelty_score != null && <span>novidade {fmt.number(marker.novelty_score, 2)}</span>}
        </div>
        <p className="text-[13px] text-ink-2">{explain(marker)}</p>
        {marker.plant != null && (
          <p className="text-[12px] text-muted">
            Presa à planta de {fmt.number(marker.z, 2)} m fotografada nesta posição — só ela carrega o diagnóstico; as
            vizinhas mostram apenas o que o sensor mediu.
          </p>
        )}
      </div>
    </Modal>
  )
}

function Figure({ label, value, hint }: { label: string; value: ReactNode; hint?: string }) {
  return (
    <div className="min-w-0">
      <div className="text-[12px] text-muted">{label}</div>
      <div className="num font-display text-[22px] leading-tight font-semibold">{value}</div>
      {hint && <div className="text-[11px] leading-snug text-muted">{hint}</div>}
    </div>
  )
}

// --- utilidades ------------------------------------------------------------------

function markerTitle(marker: SceneMarkerOut): string {
  if (marker.category === 'review') return marker.label ? `Palpite: ${disease(marker.label)}` : 'Aguardando agrônomo'
  return disease(marker.label)
}

function explain(marker: SceneMarkerOut): string {
  switch (marker.category) {
    case 'pest':
      return marker.status === 'human_confirmed'
        ? 'Praga identificada pelo agrônomo. A foto chegou com um palpite de doença e novidade alta — o modelo não conhece a praga — e é o rótulo humano que a coloca na cópia.'
        : 'Dano de praga reconhecido pelos modelos.'
    case 'disease':
      return marker.status === 'human_confirmed'
        ? 'Doença confirmada pelo agrônomo.'
        : 'Duas análises independentes concordaram. É diagnóstico, não ordem: aplicar depende do agrônomo e da camada de segurança.'
    case 'review':
      return 'A dupla validação não fechou esta foto. Até o agrônomo olhar, a cópia mostra só que há algo aqui — não o quê.'
    case 'other':
      return 'Achado registrado pelo agrônomo que não é praga nem doença do catálogo.'
    default:
      return 'Planta fotografada sem sintoma.'
  }
}

/**
 * Numera as ruas pela posição, atravessando as linhas: a mesma rua percorrida
 * em duas missões recebe o mesmo número, e a numeração segue o talhão.
 */
function laneNumbers(data: FieldSceneOut): number[] {
  const first = data.scans[0]?.path
  if (!first || first.length < 2) return data.scans.map((_, index) => index + 1)
  const [ax = 0, ay = 0] = first[0]!
  const [bx = 0, by = 0] = first[first.length - 1]!
  const length = Math.hypot(bx - ax, by - ay) || 1
  const nx = -(by - ay) / length
  const ny = (bx - ax) / length
  const offsets = data.scans.map((scan) => {
    const points = scan.path
    const sx = points.reduce((sum, point) => sum + (point[0] ?? 0), 0) / Math.max(1, points.length)
    const sy = points.reduce((sum, point) => sum + (point[1] ?? 0), 0) / Math.max(1, points.length)
    return Math.round(sx * nx + sy * ny)
  })
  const ordered = [...new Set(offsets)].sort((a, b) => a - b)
  return offsets.map((offset) => ordered.indexOf(offset) + 1)
}

function summarize(data: FieldSceneOut) {
  const heights = data.plants.height
  const count = heights.length
  const sorted = [...heights].sort((a, b) => a - b)
  const measured = data.plants.greenness.filter((value): value is number => value != null)
  const at = new Date(data.at).getTime()
  const oldest = data.scans.reduce(
    (acc, scan) => Math.max(acc, (at - new Date(scan.captured_at).getTime()) / 86_400_000),
    7,
  )
  return {
    count,
    mean: count ? heights.reduce((sum, value) => sum + value, 0) / count : null,
    low: count ? (sorted[Math.floor(count * 0.05)] ?? null) : null,
    high: count ? (sorted[Math.floor(count * 0.95)] ?? null) : null,
    stressed: measured.length ? measured.filter((value) => value < 0.6).length / measured.length : null,
    oldest: Math.ceil(oldest),
  }
}

function endOfDay(day: string): string {
  return new Date(`${day}T23:59:59`).toISOString()
}
