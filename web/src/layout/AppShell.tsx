import {
  Bell,
  BellRing,
  Bot,
  Box,
  Building2,
  ChevronDown,
  Droplets,
  FlaskConical,
  HeartPulse,
  Images,
  LayoutDashboard,
  LifeBuoy,
  LogOut,
  Map as MapIcon,
  Menu,
  Monitor,
  Moon,
  Route,
  ScanSearch,
  ScrollText,
  Settings,
  ShieldCheck,
  Sprout,
  Sun,
  X,
  type LucideIcon,
} from 'lucide-react'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { Link, NavLink, useLocation } from 'react-router-dom'

import { useAlerts, useDashboard } from '@/api/queries'
import type { AlertOut } from '@/api/types'
import { useAuth } from '@/auth/AuthProvider'
import { Logo } from '@/components/Logo'
import { NotificationBell } from '@/components/NotificationBell'
import { Badge } from '@/components/ui'
import { cn } from '@/lib/cn'
import { fmt } from '@/lib/format'
import { role as roleLabel, severity, severityTone } from '@/lib/labels'
import { useEventStream, type StreamStatus } from '@/lib/stream'
import { useTheme, type ThemeChoice } from '@/lib/theme'
import { SupportBanner } from '@/platform/SupportBanner'

type NavItem = {
  to: string
  label: string
  icon: LucideIcon
  end?: boolean
  capability?: string
  badge?: 'review'
}

const NAV: { group: string; items: NavItem[] }[] = [
  {
    group: 'Operação',
    items: [
      { to: '/', label: 'Painel', icon: LayoutDashboard, end: true },
      { to: '/mapa', label: 'Mapa', icon: MapIcon },
      { to: '/missoes', label: 'Missões', icon: Route },
      { to: '/frota', label: 'Frota', icon: Bot },
      { to: '/observabilidade', label: 'Saúde da frota', icon: HeartPulse, capability: 'device:read' },
    ],
  },
  {
    group: 'Diagnóstico',
    items: [
      { to: '/revisao', label: 'Fila do agrônomo', icon: ScanSearch, badge: 'review' },
      { to: '/talhoes', label: 'Talhões', icon: Sprout },
      { to: '/coletas', label: 'Coletas', icon: Images },
      { to: '/lavoura-3d', label: 'Lavoura 3D', icon: Box },
    ],
  },
  {
    group: 'Aplicação',
    items: [
      { to: '/aplicacoes', label: 'Aplicações', icon: Droplets },
      { to: '/insumos', label: 'Insumos', icon: FlaskConical },
    ],
  },
  {
    group: 'Governança',
    items: [
      { to: '/auditoria', label: 'Auditoria', icon: ScrollText, capability: 'audit:read' },
      { to: '/suporte', label: 'Suporte', icon: LifeBuoy },
      { to: '/notificacoes', label: 'Notificações', icon: BellRing },
      { to: '/configuracoes', label: 'Configurações', icon: Settings },
    ],
  },
]

const MOBILE_TABS = ['/', '/mapa', '/lavoura-3d', '/revisao', '/missoes']
const MOBILE_LABEL: Record<string, string> = { 'Fila do agrônomo': 'Revisão', 'Lavoura 3D': '3D' }

export function alertLink(alert: AlertOut): string {
  switch (alert.subject_type) {
    case 'device':
      return alert.subject_id ? `/frota/${alert.subject_id}` : '/frota'
    case 'mission':
      return alert.subject_id ? `/missoes/${alert.subject_id}` : '/missoes'
    case 'field':
      return alert.subject_id ? `/talhoes/${alert.subject_id}` : '/talhoes'
    case 'diagnosis':
      return '/revisao'
    case 'application':
    case 'verification':
      return '/aplicacoes'
    default:
      return '/'
  }
}

export function AppShell({ children }: { children: ReactNode }) {
  const { can } = useAuth()
  const dashboard = useDashboard()
  const stream = useEventStream()
  const [drawer, setDrawer] = useState(false)
  const location = useLocation()

  useEffect(() => setDrawer(false), [location.pathname])

  const reviewCount = dashboard.data?.review_queue ?? 0
  const visible = NAV.map((group) => ({
    ...group,
    items: group.items.filter((item) => !item.capability || can(item.capability)),
  })).filter((group) => group.items.length > 0)
  const flat = visible.flatMap((group) => group.items)

  const sidebar = (
    <nav className="flex h-full flex-col gap-6 overflow-y-auto px-3 py-5" aria-label="Navegação principal">
      <Link to="/" className="px-2">
        <Logo />
      </Link>
      {visible.map((group) => (
        <div key={group.group}>
          <div className="mb-1.5 px-3 text-[11px] font-medium tracking-wider text-muted uppercase">
            {group.group}
          </div>
          <ul className="flex flex-col gap-0.5">
            {group.items.map((item) => (
              <li key={item.to}>
                <NavLink
                  to={item.to}
                  end={item.end}
                  className={({ isActive }) =>
                    cn(
                      'flex items-center gap-3 rounded-[10px] px-3 py-2 text-[14px] transition-colors',
                      isActive
                        ? 'bg-accent-soft font-medium text-ink'
                        : 'text-ink-2 hover:bg-raised hover:text-ink',
                    )
                  }
                >
                  <item.icon className="size-[18px] shrink-0" aria-hidden />
                  <span className="flex-1">{item.label}</span>
                  {item.badge === 'review' && reviewCount > 0 && (
                    <span className="num rounded-full bg-warning/20 px-2 text-[11px] font-semibold text-ink">
                      {reviewCount}
                    </span>
                  )}
                </NavLink>
              </li>
            ))}
          </ul>
        </div>
      ))}
      <div className="mt-auto px-3 text-[11px] leading-relaxed text-muted">
        Nenhum resultado de IA comanda uma aplicação. Toda ação física passa por um agrônomo e pela camada de
        segurança.
      </div>
    </nav>
  )

  return (
    <div className="flex h-full">
      <aside className="hidden w-64 shrink-0 border-r border-line bg-surface lg:block">{sidebar}</aside>

      {drawer && (
        <div className="fixed inset-0 z-[900] lg:hidden">
          <div className="absolute inset-0 bg-black/45" onClick={() => setDrawer(false)} aria-hidden />
          <aside className="relative h-full w-72 bg-surface shadow-xl">
            <button
              type="button"
              onClick={() => setDrawer(false)}
              className="absolute top-4 right-3 rounded-lg p-2 text-muted hover:bg-raised"
              aria-label="Fechar menu"
            >
              <X className="size-5" />
            </button>
            {sidebar}
          </aside>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <SupportBanner />
        <TopBar onMenu={() => setDrawer(true)} stream={stream} />
        <main className="min-w-0 flex-1 overflow-y-auto px-4 pt-6 pb-24 sm:px-6 lg:px-8 lg:pb-10">
          <div className="mx-auto max-w-[1400px]">{children}</div>
        </main>
      </div>

      <nav
        className="fixed inset-x-0 bottom-0 z-[800] grid grid-cols-5 border-t border-line bg-surface/95 pb-[env(safe-area-inset-bottom)] backdrop-blur lg:hidden"
        aria-label="Atalhos"
      >
        {MOBILE_TABS.map((path) => {
          const item = flat.find((entry) => entry.to === path)
          if (!item) return null
          return (
            <NavLink
              key={path}
              to={path}
              end={item.end}
              className={({ isActive }) =>
                cn(
                  'relative flex flex-col items-center gap-0.5 py-2 text-[11px]',
                  isActive ? 'text-ink' : 'text-muted',
                )
              }
            >
              <item.icon className="size-5" aria-hidden />
              <span>{MOBILE_LABEL[item.label] ?? item.label}</span>
              {item.badge === 'review' && reviewCount > 0 && (
                <span className="absolute top-1 right-[calc(50%-18px)] size-2 rounded-full bg-warning" />
              )}
            </NavLink>
          )
        })}
      </nav>
    </div>
  )
}

function TopBar({ onMenu, stream }: { onMenu: () => void; stream: StreamStatus }) {
  const { me, memberships, selectTenant, logout, support, isPlatform } = useAuth()
  const active = memberships.find((item) => item.tenant_id === me?.active_tenant_id)
  // Na sessão de suporte o cliente é fixo: o token só vale para ele.
  const trocaCliente = memberships.length > 1 && !support

  return (
    <header className="sticky top-0 z-[700] flex h-14 shrink-0 items-center gap-3 border-b border-line bg-surface/90 px-4 backdrop-blur sm:px-6 lg:px-8">
      <button
        type="button"
        onClick={onMenu}
        className="-ml-1 rounded-lg p-2 text-ink-2 hover:bg-raised lg:hidden"
        aria-label="Abrir menu"
      >
        <Menu className="size-5" />
      </button>

      <div className="flex min-w-0 items-center gap-2">
        <Building2 className="size-4 shrink-0 text-muted" aria-hidden />
        {trocaCliente ? (
          <select
            className="max-w-[46vw] truncate rounded-lg bg-transparent py-1 pr-6 text-[14px] font-medium outline-none hover:bg-raised"
            value={me?.active_tenant_id ?? ''}
            onChange={(event) => selectTenant(event.target.value)}
            aria-label="Cliente ativo"
          >
            {memberships.map((item) => (
              <option key={item.tenant_id} value={item.tenant_id}>
                {item.tenant_name}
              </option>
            ))}
          </select>
        ) : (
          <span className="truncate text-[14px] font-medium">
            {support?.tenantName ?? active?.tenant_name ?? '—'}
          </span>
        )}
      </div>

      <div className="ml-auto flex items-center gap-1 sm:gap-2">
        <LiveIndicator status={stream} />
        <NotificationBell audience="cliente" centralPath="/notificacoes" />
        <AlertsMenu />
        <ThemeToggle />
        <UserMenu
          name={me?.full_name ?? ''}
          role={me?.role ?? ''}
          onLogout={logout}
          platformLink={isPlatform && !support}
        />
      </div>
    </header>
  )
}

function LiveIndicator({ status }: { status: StreamStatus }) {
  const label = { live: 'Ao vivo', connecting: 'Conectando', retrying: 'Reconectando', off: 'Desconectado' }[status]
  return (
    <span className="hidden items-center gap-1.5 rounded-full px-2 py-1 text-[12px] text-muted sm:inline-flex" title="Eventos da plataforma em tempo real">
      <span className={cn('size-2 rounded-full', status === 'live' ? 'bg-good' : status === 'off' ? 'bg-muted' : 'bg-warning')} />
      {label}
    </span>
  )
}

function useClickAway(onAway: () => void) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const listener = (event: MouseEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node)) onAway()
    }
    document.addEventListener('mousedown', listener)
    return () => document.removeEventListener('mousedown', listener)
  }, [onAway])
  return ref
}

function AlertsMenu() {
  const alerts = useAlerts()
  const [open, setOpen] = useState(false)
  const ref = useClickAway(() => setOpen(false))
  const rows = alerts.data ?? []
  const urgent = rows.filter((alert) => alert.severity !== 'info').length

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className="relative rounded-lg p-2 text-ink-2 hover:bg-raised"
        aria-label={`Alertas${urgent ? `: ${urgent} pedem atenção` : ''}`}
        aria-expanded={open}
      >
        <Bell className="size-5" />
        {urgent > 0 && (
          <span className="num absolute top-1 right-1 grid min-w-4 place-items-center rounded-full bg-critical px-1 text-[10px] leading-4 font-semibold text-white">
            {urgent}
          </span>
        )}
      </button>
      {open && (
        <div className="card absolute right-0 mt-2 w-[min(92vw,400px)] overflow-hidden">
          <div className="flex items-center justify-between border-b border-line-soft px-4 py-3">
            <span className="font-medium">Alertas</span>
            <span className="text-[12px] text-muted">{rows.length} ativo(s)</span>
          </div>
          <ul className="max-h-[60vh] overflow-y-auto">
            {rows.length === 0 && <li className="px-4 py-6 text-center text-[13px] text-muted">Nada pedindo atenção.</li>}
            {rows.slice(0, 12).map((alert) => (
              <li key={alert.id} className="border-b border-line-soft last:border-0">
                <Link to={alertLink(alert)} onClick={() => setOpen(false)} className="block px-4 py-3 hover:bg-raised">
                  <div className="flex items-center justify-between gap-2">
                    <Badge tone={severityTone(alert.severity)}>{severity(alert.severity)}</Badge>
                    <span className="text-[11px] text-muted">{fmt.ago(alert.at)}</span>
                  </div>
                  <div className="mt-1.5 text-[13px] font-medium">{alert.title}</div>
                  <div className="line-clamp-2 text-[12px] text-ink-2">{alert.detail}</div>
                </Link>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

function ThemeToggle() {
  const { choice, setChoice } = useTheme()
  const next: Record<ThemeChoice, ThemeChoice> = { system: 'light', light: 'dark', dark: 'system' }
  const Icon = choice === 'light' ? Sun : choice === 'dark' ? Moon : Monitor
  const label = { system: 'Tema do sistema', light: 'Tema claro', dark: 'Tema escuro' }[choice]
  return (
    <button
      type="button"
      onClick={() => setChoice(next[choice])}
      className="rounded-lg p-2 text-ink-2 hover:bg-raised"
      title={`${label} — clique para trocar`}
      aria-label={label}
    >
      <Icon className="size-5" />
    </button>
  )
}

function UserMenu({
  name,
  role,
  onLogout,
  platformLink,
}: {
  name: string
  role: string
  onLogout: () => void
  platformLink: boolean
}) {
  const [open, setOpen] = useState(false)
  const ref = useClickAway(() => setOpen(false))
  const initials = name
    .split(' ')
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join('')

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className="flex items-center gap-2 rounded-lg py-1 pr-1.5 pl-1 hover:bg-raised"
        aria-expanded={open}
      >
        <span className="grid size-8 place-items-center rounded-full bg-accent-soft text-[12px] font-semibold">
          {initials || '·'}
        </span>
        <ChevronDown className="hidden size-4 text-muted sm:block" aria-hidden />
      </button>
      {open && (
        <div className="card absolute right-0 mt-2 w-64 overflow-hidden">
          <div className="border-b border-line-soft px-4 py-3">
            <div className="truncate font-medium">{name}</div>
            <div className="text-[12px] text-muted">{roleLabel(role)}</div>
          </div>
          {platformLink && (
            <Link
              to="/plataforma"
              className="flex w-full items-center gap-2 border-b border-line-soft px-4 py-3 text-[13px] hover:bg-raised"
            >
              <ShieldCheck className="size-4" aria-hidden />
              Console da plataforma
            </Link>
          )}
          <button
            type="button"
            onClick={onLogout}
            className="flex w-full items-center gap-2 px-4 py-3 text-left text-[13px] hover:bg-raised"
          >
            <LogOut className="size-4" aria-hidden />
            Sair
          </button>
        </div>
      )}
    </div>
  )
}
