/**
 * Gráficos do console.
 *
 * Regras que valem para todos: um eixo só (nunca dois eixos Y), traço de 2 px,
 * grade discreta, legenda sempre que houver mais de uma série e dica ao passar o
 * mouse. A cor de cada doença é fixa por rótulo (ver lib/labels) — a ferrugem é
 * laranja aqui, no mapa e na fila.
 */
import type { ReactNode } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import type { TimePointOut } from '@/api/types'
import { fmt, parseUtc } from '@/lib/format'
import { assignSlots, bySlot, disease, seriesColor } from '@/lib/labels'
import { slotColor, usePalette } from '@/lib/palette'

// --- dica ---------------------------------------------------------------------

type TooltipItem = { name?: unknown; value?: unknown; color?: string; dataKey?: unknown }
type TooltipLike = { active?: boolean; payload?: ReadonlyArray<TooltipItem>; label?: unknown }

function ChartTooltip({
  active,
  payload,
  label,
  formatLabel,
  formatValue,
}: TooltipLike & { formatLabel?: (label: unknown) => ReactNode; formatValue?: (value: number) => string }) {
  if (!active || !payload?.length) return null
  const rows = payload.filter((item) => typeof item.value === 'number' && item.value !== 0)
  return (
    <div className="card min-w-40 px-3 py-2 text-[12px]">
      <div className="mb-1 font-medium">{formatLabel ? formatLabel(label) : String(label ?? '')}</div>
      {(rows.length ? rows : payload).map((item) => (
        <div key={String(item.dataKey)} className="flex items-center justify-between gap-4">
          <span className="flex items-center gap-1.5 text-ink-2">
            <span className="size-2 rounded-full" style={{ background: item.color }} />
            {String(item.name ?? item.dataKey)}
          </span>
          <span className="num font-medium">
            {typeof item.value === 'number' ? (formatValue ? formatValue(item.value) : fmt.number(item.value)) : '—'}
          </span>
        </div>
      ))}
    </div>
  )
}

// --- legenda ------------------------------------------------------------------

export function Legend({ items }: { items: { label: string; color: string }[] }) {
  return (
    <ul className="flex flex-wrap gap-x-4 gap-y-1.5 text-[12px] text-ink-2">
      {items.map((item) => (
        <li key={item.label} className="flex items-center gap-1.5">
          <span className="size-2.5 rounded-[3px]" style={{ background: item.color }} aria-hidden />
          {item.label}
        </li>
      ))}
    </ul>
  )
}

// --- distribuição -----------------------------------------------------------------

/**
 * Barras horizontais em HTML, com rótulo e valor visíveis em cada linha.
 *
 * Texto direto em vez de depender da cor: três cores da paleta ficam abaixo de
 * 3:1 no tema claro, e o rótulo escrito é o que garante a leitura.
 */
export function DistributionBars({ data }: { data: { label: string; count: number }[] }) {
  const total = data.reduce((sum, row) => sum + row.count, 0)
  const slots = assignSlots(data.map((row) => row.label))
  const max = Math.max(1, ...data.map((row) => row.count))

  return (
    <ul className="flex flex-col gap-2.5">
      {data.map((row) => (
        <li key={row.label} className="grid grid-cols-[minmax(0,9rem)_1fr_auto] items-center gap-3 text-[13px]">
          <span className="flex min-w-0 items-center gap-2">
            <span
              className="size-2.5 shrink-0 rounded-[3px]"
              style={{ background: seriesColor(slots.get(row.label) ?? 0) }}
              aria-hidden
            />
            <span className="truncate">{disease(row.label)}</span>
          </span>
          <span className="h-2 overflow-hidden rounded-full bg-sunken">
            <span
              className="block h-full rounded-full"
              style={{ width: `${(row.count / max) * 100}%`, background: seriesColor(slots.get(row.label) ?? 0) }}
            />
          </span>
          <span className="num w-20 text-right text-ink-2">
            {fmt.number(row.count)} <span className="text-muted">· {fmt.percent(total ? row.count / total : 0)}</span>
          </span>
        </li>
      ))}
    </ul>
  )
}

// --- série diária de diagnósticos -----------------------------------------------

export function LabelsTimeline({ points, height = 240 }: { points: TimePointOut[]; height?: number }) {
  const palette = usePalette()
  const labels = [...new Set(points.flatMap((point) => Object.keys(point.counts)))]
  const slots = assignSlots(labels)
  const ordered = bySlot(labels, slots)
  const rows = points.map((point) => ({ day: point.day, ...point.counts }))

  return (
    <div className="flex flex-col gap-3">
      <Legend items={ordered.map((label) => ({ label: disease(label), color: seriesColor(slots.get(label) ?? 0) }))} />
      <div style={{ height }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={rows} margin={{ top: 4, right: 4, bottom: 0, left: -18 }} barCategoryGap="22%">
            <CartesianGrid stroke={palette.grid} vertical={false} />
            <XAxis
              dataKey="day"
              tickFormatter={(value: string) => fmt.dayMonth(`${value}T12:00:00Z`)}
              tick={{ fill: palette.muted, fontSize: 11 }}
              axisLine={{ stroke: palette.axis }}
              tickLine={false}
            />
            <YAxis allowDecimals={false} tick={{ fill: palette.muted, fontSize: 11 }} axisLine={false} tickLine={false} />
            <Tooltip
              cursor={{ fill: palette.grid, opacity: 0.6 }}
              content={(props: TooltipLike) => (
                <ChartTooltip {...props} formatLabel={(value) => fmt.date(`${String(value)}T12:00:00Z`)} />
              )}
            />
            {ordered.map((label) => (
              <Bar
                key={label}
                dataKey={label}
                name={disease(label)}
                stackId="dia"
                fill={slotColor(palette, slots.get(label) ?? 0)}
                stroke={palette.surface}
                strokeWidth={1}
                isAnimationActive={false}
              />
            ))}
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}

// --- telemetria -------------------------------------------------------------------

type TimeValue = { at: string; value: number | null }

export function TimeSeries({
  data,
  label,
  unit,
  domain,
  threshold,
  height = 180,
}: {
  data: TimeValue[]
  label: string
  unit: string
  domain?: [number, number]
  threshold?: { value: number; label: string }
  height?: number
}) {
  const palette = usePalette()
  const rows = data
    .filter((row) => row.value !== null)
    .map((row) => ({ t: parseUtc(row.at)?.getTime() ?? 0, value: row.value }))

  return (
    <div style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={rows} margin={{ top: 8, right: 8, bottom: 0, left: -14 }}>
          <CartesianGrid stroke={palette.grid} vertical={false} />
          <XAxis
            dataKey="t"
            type="number"
            scale="time"
            domain={['dataMin', 'dataMax']}
            tickFormatter={(value: number) => fmt.time(new Date(value))}
            tick={{ fill: palette.muted, fontSize: 11 }}
            axisLine={{ stroke: palette.axis }}
            tickLine={false}
            minTickGap={36}
          />
          <YAxis
            domain={domain ?? ['auto', 'auto']}
            tick={{ fill: palette.muted, fontSize: 11 }}
            axisLine={false}
            tickLine={false}
            unit={unit}
            width={52}
          />
          {threshold && (
            <ReferenceLine
              y={threshold.value}
              stroke={palette.warning}
              strokeDasharray="4 4"
              label={{ value: threshold.label, fill: palette.muted, fontSize: 11, position: 'insideTopRight' }}
            />
          )}
          <Tooltip
            content={(props: TooltipLike) => (
              <ChartTooltip
                {...props}
                formatLabel={(value) => fmt.dateTime(new Date(Number(value)))}
                formatValue={(value) => `${fmt.number(value, 1)} ${unit}`}
              />
            )}
          />
          <Line
            type="monotone"
            dataKey="value"
            name={label}
            stroke={palette.accent}
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 4, stroke: palette.surface, strokeWidth: 2 }}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
