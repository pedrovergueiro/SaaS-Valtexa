/**
 * Formatação em pt-BR.
 *
 * Todo horário que vem da API está em UTC com fuso explícito; exibimos no fuso
 * do navegador. `parseUtc` ainda trata o caso sem fuso como UTC — defesa contra
 * um horário ingênuo que escape do servidor, que o navegador leria como local.
 */

const LOCALE = 'pt-BR'

export function parseUtc(value: string | Date | null | undefined): Date | null {
  if (!value) return null
  if (value instanceof Date) return value
  const hasZone = /([zZ]|[+-]\d{2}:?\d{2})$/.test(value)
  return new Date(hasZone ? value : `${value}Z`)
}

const dateTime = new Intl.DateTimeFormat(LOCALE, { dateStyle: 'short', timeStyle: 'short' })
const dateOnly = new Intl.DateTimeFormat(LOCALE, { day: '2-digit', month: '2-digit', year: 'numeric' })
const dayMonth = new Intl.DateTimeFormat(LOCALE, { day: '2-digit', month: 'short' })
const timeOnly = new Intl.DateTimeFormat(LOCALE, { hour: '2-digit', minute: '2-digit' })
const relative = new Intl.RelativeTimeFormat(LOCALE, { numeric: 'auto' })

export const fmt = {
  number(value: number | null | undefined, digits = 0): string {
    if (value === null || value === undefined || Number.isNaN(value)) return '—'
    return value.toLocaleString(LOCALE, {
      minimumFractionDigits: digits,
      maximumFractionDigits: digits,
    })
  },

  /** Recebe fração (0,25) e devolve "25%". */
  percent(ratio: number | null | undefined, digits = 0): string {
    if (ratio === null || ratio === undefined || Number.isNaN(ratio)) return '—'
    return `${(ratio * 100).toLocaleString(LOCALE, { maximumFractionDigits: digits })}%`
  },

  dateTime(value: string | Date | null | undefined): string {
    const date = parseUtc(value)
    return date ? dateTime.format(date) : '—'
  },

  date(value: string | Date | null | undefined): string {
    const date = parseUtc(value)
    return date ? dateOnly.format(date) : '—'
  },

  dayMonth(value: string | Date | null | undefined): string {
    const date = parseUtc(value)
    return date ? dayMonth.format(date) : '—'
  },

  time(value: string | Date | null | undefined): string {
    const date = parseUtc(value)
    return date ? timeOnly.format(date) : '—'
  },

  /** "há 3 min", "em 2 h". */
  ago(value: string | Date | null | undefined): string {
    const date = parseUtc(value)
    if (!date) return '—'
    const seconds = Math.round((date.getTime() - Date.now()) / 1000)
    const abs = Math.abs(seconds)
    if (abs < 45) return 'agora'
    if (abs < 3600) return relative.format(Math.round(seconds / 60), 'minute')
    if (abs < 86400) return relative.format(Math.round(seconds / 3600), 'hour')
    if (abs < 86400 * 30) return relative.format(Math.round(seconds / 86400), 'day')
    return dateOnly.format(date)
  },

  hectares(value: number | null | undefined): string {
    return value === null || value === undefined ? '—' : `${fmt.number(value, value < 10 ? 2 : 1)} ha`
  },

  liters(value: number | null | undefined): string {
    return value === null || value === undefined ? '—' : `${fmt.number(value, 1)} L`
  },

  meters(value: number | null | undefined): string {
    if (value === null || value === undefined) return '—'
    return value >= 1000 ? `${fmt.number(value / 1000, 2)} km` : `${fmt.number(value, 0)} m`
  },

  shortId(id: string | null | undefined): string {
    return id ? id.slice(0, 8) : '—'
  },
}
