import { useMemo } from 'react'

import { useTheme } from '@/lib/theme'

/**
 * As cores do tema, resolvidas para hexadecimal.
 *
 * SVG não aceita `var(--x)` em atributo de apresentação, e é por atributo que
 * o Recharts e o Leaflet pintam. Então gráfico e mapa leem as cores já
 * resolvidas daqui — e recalculam quando o tema muda.
 */
export type Palette = {
  series: string[]
  other: string
  surface: string
  ink: string
  ink2: string
  muted: string
  line: string
  grid: string
  axis: string
  accent: string
  good: string
  warning: string
  serious: string
  critical: string
  info: string
  health: { healthy: string; disease: string; review: string }
  /** Praga na cópia 3D. Validada contra doença e revisão (ver app.css). */
  pest: string
  skyTop: string
  skyHorizon: string
}

export function usePalette(): Palette {
  const { resolved } = useTheme()
  return useMemo(() => {
    const style = getComputedStyle(document.documentElement)
    const get = (name: string) => style.getPropertyValue(name).trim()
    const series = [1, 2, 3, 4, 5, 6, 7, 8].map((slot) => get(`--series-${slot}`))
    return {
      series,
      other: get('--series-other'),
      surface: get('--surface'),
      ink: get('--ink'),
      ink2: get('--ink-2'),
      muted: get('--muted'),
      line: get('--line'),
      grid: get('--grid'),
      axis: get('--axis'),
      accent: get('--accent'),
      good: get('--good'),
      warning: get('--warning'),
      serious: get('--serious'),
      critical: get('--critical'),
      info: get('--info'),
      health: { healthy: series[2] ?? '', disease: series[1] ?? '', review: series[0] ?? '' },
      pest: get('--cat-pest'),
      skyTop: get('--sky-top'),
      skyHorizon: get('--sky-horizon'),
    }
    // `resolved` é a dependência real: o CSS muda com ele.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resolved])
}

/** Cor resolvida de um slot (1–8); 0 ou fora da faixa = "Outros". */
export function slotColor(palette: Palette, slot: number): string {
  return (slot >= 1 && slot <= 8 && palette.series[slot - 1]) || palette.other
}
