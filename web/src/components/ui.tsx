/**
 * Primitivas visuais do console.
 *
 * Poucas e consistentes: botão, cartão, selo, indicador, estado vazio, erro,
 * modal, abas. Status sempre aparece com ponto **e** texto — cor sozinha não
 * carrega significado (daltonismo, sol na tela, impressão).
 */
import { AlertTriangle, Inbox, Loader2, X } from 'lucide-react'
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ButtonHTMLAttributes,
  type ReactNode,
} from 'react'
import { createPortal } from 'react-dom'

import { ApiError } from '@/api/client'
import { cn } from '@/lib/cn'
import type { Tone } from '@/lib/labels'

// --- botão ------------------------------------------------------------------

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger'
  size?: 'sm' | 'md'
  loading?: boolean
  icon?: ReactNode
}

export function Button({
  variant = 'secondary',
  size = 'md',
  loading = false,
  icon,
  className,
  children,
  disabled,
  ...rest
}: ButtonProps) {
  return (
    <button
      type="button"
      disabled={disabled || loading}
      className={cn(
        'inline-flex items-center justify-center gap-2 rounded-[10px] font-medium whitespace-nowrap transition-colors',
        'disabled:opacity-50',
        size === 'sm' ? 'h-8 px-3 text-[13px]' : 'h-10 px-4 text-sm',
        variant === 'primary' && 'bg-accent text-accent-ink hover:brightness-110',
        variant === 'secondary' && 'border border-line bg-surface text-ink hover:bg-raised',
        variant === 'ghost' && 'text-ink-2 hover:bg-raised hover:text-ink',
        variant === 'danger' && 'bg-critical text-white hover:brightness-110',
        className,
      )}
      {...rest}
    >
      {loading ? <Loader2 className="size-4 animate-spin" aria-hidden /> : icon}
      {children}
    </button>
  )
}

// --- cartão -------------------------------------------------------------------

export function Card({
  className,
  children,
  as: Tag = 'section',
}: {
  className?: string
  children: ReactNode
  as?: 'section' | 'div' | 'article'
}) {
  return <Tag className={cn('card', className)}>{children}</Tag>
}

export function CardHeader({
  title,
  subtitle,
  actions,
  className,
}: {
  title: ReactNode
  subtitle?: ReactNode
  actions?: ReactNode
  className?: string
}) {
  return (
    <header className={cn('flex flex-wrap items-start justify-between gap-3 px-5 pt-4 pb-3', className)}>
      {/* basis-0: o texto quebra antes de empurrar as ações para a linha de baixo. */}
      <div className="min-w-[12rem] flex-1 basis-0">
        <h2 className="text-[15px] font-semibold">{title}</h2>
        {subtitle && <p className="mt-0.5 text-[13px] text-muted">{subtitle}</p>}
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
    </header>
  )
}

// --- selos e indicadores ------------------------------------------------------

const TONE_DOT: Record<Tone, string> = {
  good: 'bg-good',
  warning: 'bg-warning',
  serious: 'bg-serious',
  critical: 'bg-critical',
  info: 'bg-info',
  neutral: 'bg-muted',
  accent: 'bg-accent',
}
const TONE_BG: Record<Tone, string> = {
  good: 'bg-good/12',
  warning: 'bg-warning/15',
  serious: 'bg-serious/15',
  critical: 'bg-critical/12',
  info: 'bg-info/12',
  neutral: 'bg-sunken',
  accent: 'bg-accent-soft',
}

export function Badge({
  tone = 'neutral',
  children,
  pulse = false,
  className,
}: {
  tone?: Tone
  children: ReactNode
  pulse?: boolean
  className?: string
}) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-[12px] font-medium whitespace-nowrap text-ink',
        TONE_BG[tone],
        className,
      )}
    >
      <span className="relative flex size-1.5">
        {pulse && (
          <span className={cn('absolute inline-flex size-full animate-ping rounded-full opacity-60', TONE_DOT[tone])} />
        )}
        <span className={cn('relative inline-flex size-1.5 rounded-full', TONE_DOT[tone])} />
      </span>
      {children}
    </span>
  )
}

export function Stat({
  label,
  value,
  hint,
  icon,
  tone,
}: {
  label: string
  value: ReactNode
  hint?: ReactNode
  icon?: ReactNode
  tone?: Tone
}) {
  return (
    <div className="card flex flex-col gap-2 p-4">
      <div className="flex items-center justify-between gap-2 text-[13px] text-muted">
        <span>{label}</span>
        {icon && <span className={cn('text-ink-2', tone && `text-${tone}`)}>{icon}</span>}
      </div>
      <div className="font-display text-[28px] leading-none font-semibold tracking-tight">{value}</div>
      {hint && <div className="text-[12px] text-muted">{hint}</div>}
    </div>
  )
}

export function Meter({ value, tone = 'accent', label }: { value: number; tone?: Tone; label?: string }) {
  const clamped = Math.max(0, Math.min(1, value))
  return (
    <div className="flex items-center gap-2" role="meter" aria-valuenow={Math.round(clamped * 100)} aria-label={label}>
      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-sunken">
        <div className={cn('h-full rounded-full', TONE_DOT[tone])} style={{ width: `${clamped * 100}%` }} />
      </div>
    </div>
  )
}

// --- página -------------------------------------------------------------------

export function PageHeader({
  title,
  subtitle,
  actions,
  eyebrow,
}: {
  title: ReactNode
  subtitle?: ReactNode
  actions?: ReactNode
  eyebrow?: ReactNode
}) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0">
        {eyebrow && <div className="mb-1 text-[12px] font-medium tracking-wide text-muted uppercase">{eyebrow}</div>}
        <h1 className="text-[26px] leading-tight font-semibold">{title}</h1>
        {subtitle && <p className="mt-1 max-w-3xl text-[14px] text-ink-2">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  )
}

export function Empty({
  title,
  children,
  icon,
  action,
}: {
  title: string
  children?: ReactNode
  icon?: ReactNode
  action?: ReactNode
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 px-6 py-12 text-center">
      <div className="mb-1 rounded-full bg-sunken p-3 text-muted">{icon ?? <Inbox className="size-5" />}</div>
      <div className="font-medium">{title}</div>
      {children && <p className="max-w-md text-[13px] text-muted">{children}</p>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  )
}

export function Spinner({ label = 'Carregando' }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-2 py-10 text-[13px] text-muted" role="status">
      <Loader2 className="size-4 animate-spin" aria-hidden />
      {label}…
    </div>
  )
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn('animate-pulse rounded-lg bg-sunken', className)} />
}

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.detail
  if (error instanceof Error) return error.message
  return 'Algo deu errado.'
}

export function ErrorBox({ error, className }: { error: unknown; className?: string }) {
  if (!error) return null
  const forbidden = error instanceof ApiError && error.status === 403
  return (
    <div
      role="alert"
      className={cn(
        'flex items-start gap-2.5 rounded-[10px] border border-critical/30 bg-critical/8 px-3.5 py-2.5 text-[13px]',
        className,
      )}
    >
      <AlertTriangle className="mt-0.5 size-4 shrink-0 text-critical" aria-hidden />
      <div>
        <div className="font-medium">{forbidden ? 'Seu papel não permite esta ação' : 'Não deu certo'}</div>
        <div className="text-ink-2">{errorMessage(error)}</div>
      </div>
    </div>
  )
}

// --- formulário -----------------------------------------------------------------

export function FormField({
  label,
  hint,
  children,
  htmlFor,
}: {
  label: string
  hint?: ReactNode
  children: ReactNode
  htmlFor?: string
}) {
  return (
    <label htmlFor={htmlFor} className="flex flex-col gap-1.5">
      <span className="text-[13px] font-medium text-ink-2">{label}</span>
      {children}
      {hint && <span className="text-[12px] text-muted">{hint}</span>}
    </label>
  )
}

// --- abas -----------------------------------------------------------------------

export function Tabs<T extends string>({
  items,
  value,
  onChange,
}: {
  items: { value: T; label: ReactNode; count?: number }[]
  value: T
  onChange: (value: T) => void
}) {
  return (
    <div role="tablist" className="inline-flex gap-1 rounded-[12px] border border-line bg-raised p-1">
      {items.map((item) => (
        <button
          key={item.value}
          role="tab"
          type="button"
          aria-selected={item.value === value}
          onClick={() => onChange(item.value)}
          className={cn(
            'inline-flex h-8 items-center gap-1.5 rounded-[9px] px-3 text-[13px] font-medium transition-colors',
            item.value === value ? 'bg-surface text-ink shadow-sm' : 'text-muted hover:text-ink',
          )}
        >
          {item.label}
          {item.count !== undefined && (
            <span className="num rounded-full bg-sunken px-1.5 text-[11px] text-ink-2">{item.count}</span>
          )}
        </button>
      ))}
    </div>
  )
}

// --- modal ----------------------------------------------------------------------

export function Modal({
  open,
  onClose,
  title,
  description,
  children,
  footer,
  wide = false,
}: {
  open: boolean
  onClose: () => void
  title: ReactNode
  description?: ReactNode
  children: ReactNode
  footer?: ReactNode
  wide?: boolean
}) {
  const panel = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const previous = document.activeElement as HTMLElement | null
    panel.current?.focus()
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = ''
      previous?.focus()
    }
  }, [open, onClose])

  if (!open) return null
  return createPortal(
    <div className="fixed inset-0 z-[1000] flex items-end justify-center sm:items-center sm:p-6">
      <div className="absolute inset-0 bg-black/45 backdrop-blur-[2px]" onClick={onClose} aria-hidden />
      <div
        ref={panel}
        role="dialog"
        aria-modal="true"
        tabIndex={-1}
        className={cn(
          'card relative flex max-h-[92vh] w-full flex-col overflow-hidden rounded-b-none outline-none sm:rounded-[14px]',
          wide ? 'sm:max-w-3xl' : 'sm:max-w-lg',
        )}
      >
        <div className="flex items-start justify-between gap-4 border-b border-line-soft px-5 py-4">
          <div>
            <h2 className="text-[17px] font-semibold">{title}</h2>
            {description && <p className="mt-1 text-[13px] text-ink-2">{description}</p>}
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1.5 text-muted hover:bg-raised hover:text-ink"
            aria-label="Fechar"
          >
            <X className="size-4" />
          </button>
        </div>
        <div className="overflow-y-auto px-5 py-4">{children}</div>
        {footer && (
          <div className="flex flex-wrap justify-end gap-2 border-t border-line-soft bg-raised px-5 py-3">{footer}</div>
        )}
      </div>
    </div>,
    document.body,
  )
}

// --- tabela ----------------------------------------------------------------------

export function Table({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className="overflow-x-auto">
      <table className={cn('w-full border-collapse text-left text-[13px]', className)}>{children}</table>
    </div>
  )
}

export const th = 'border-b border-line px-4 py-2.5 text-[12px] font-medium text-muted whitespace-nowrap'
export const td = 'border-b border-line-soft px-4 py-3 align-middle'

// --- avisos ---------------------------------------------------------------------

type Toast = { id: number; tone: Tone; title: string; detail?: string }
type ToastApi = { push: (toast: Omit<Toast, 'id'>) => void }
const ToastContext = createContext<ToastApi>({ push: () => undefined })

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])
  const push = useCallback((toast: Omit<Toast, 'id'>) => {
    const id = Date.now() + Math.random()
    setToasts((current) => [...current.slice(-3), { ...toast, id }])
    window.setTimeout(() => setToasts((current) => current.filter((item) => item.id !== id)), 6500)
  }, [])

  return (
    <ToastContext.Provider value={{ push }}>
      {children}
      {createPortal(
        <div className="pointer-events-none fixed right-4 bottom-20 z-[1100] flex w-[min(92vw,380px)] flex-col gap-2 lg:bottom-4" aria-live="polite">
          {toasts.map((toast) => (
            <div key={toast.id} className="card pointer-events-auto flex items-start gap-3 px-4 py-3">
              <span className={cn('mt-1.5 size-2 shrink-0 rounded-full', TONE_DOT[toast.tone])} />
              <div className="min-w-0">
                <div className="text-[13px] font-medium">{toast.title}</div>
                {toast.detail && <div className="text-[12px] text-ink-2">{toast.detail}</div>}
              </div>
            </div>
          ))}
        </div>,
        document.body,
      )}
    </ToastContext.Provider>
  )
}

export const useToast = () => useContext(ToastContext)
