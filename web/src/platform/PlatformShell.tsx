import {
  Activity,
  BellRing,
  Bot,
  Boxes,
  BrainCircuit,
  PackageCheck,
  Radar,
  Building2,
  Compass,
  Database,
  FileText,
  Gauge,
  LifeBuoy,
  LogOut,
  Menu,
  ScrollText,
  ShieldCheck,
  Upload,
  Users,
  X,
  type LucideIcon,
} from 'lucide-react'
import { useEffect, useState, type ReactNode } from 'react'
import { Link, NavLink, useLocation } from 'react-router-dom'

import { useAuth } from '@/auth/AuthProvider'
import { Logo } from '@/components/Logo'
import { NotificationBell } from '@/components/NotificationBell'
import { cn } from '@/lib/cn'
import { usePlatformMe } from '@/platform/api'
import { platformRoleLabel } from '@/platform/labels'

/** Sem `capability`, o item vale para qualquer papel de plataforma. */
type Item = { to: string; label: string; icon: LucideIcon; capability?: string; end?: boolean }

/**
 * Menus do console interno, pelo papel de plataforma (brief, seção 28).
 *
 * Cada item pede a capacidade que a rota do servidor exige — esconder é
 * conveniência; quem decide é o servidor, rota a rota.
 */
export const PLATFORM_NAV: { group: string; items: Item[] }[] = [
  {
    group: 'Clientes',
    items: [
      { to: '/plataforma/clientes', label: 'Clientes', icon: Building2, capability: 'platform:tenant:read' },
      { to: '/plataforma/cadastro', label: 'Cadastro e contrato', icon: FileText, capability: 'platform:tenant:manage' },
    ],
  },
  {
    group: 'Atendimento',
    items: [
      { to: '/plataforma/suporte', label: 'Suporte', icon: LifeBuoy, capability: 'platform:ticket:read' },
      { to: '/plataforma/notificacoes', label: 'Notificações', icon: BellRing },
    ],
  },
  {
    group: 'Pessoas e trilha',
    items: [
      { to: '/plataforma/usuarios', label: 'Usuários globais', icon: Users, capability: 'platform:user:read' },
      { to: '/plataforma/auditoria', label: 'Auditoria global', icon: ScrollText, capability: 'platform:audit:read' },
    ],
  },
  {
    group: 'Operação e dados',
    items: [
      { to: '/plataforma/frota', label: 'Frota', icon: Bot, capability: 'platform:fleet:read' },
      { to: '/plataforma/comando', label: 'Centro de comando', icon: Radar, capability: 'platform:fleet:read' },
      { to: '/plataforma/ia', label: 'IA e modelos', icon: BrainCircuit, capability: 'platform:model:read' },
      { to: '/plataforma/atualizacoes', label: 'Atualizações (OTA)', icon: PackageCheck, capability: 'platform:fleet:read' },
      { to: '/plataforma/planejamento', label: 'Gerar missão', icon: Compass, capability: 'platform:field:operate' },
      { to: '/plataforma/coletas/nova', label: 'Importar coleta', icon: Upload, capability: 'collection:manage' },
      { to: '/plataforma/coletas', label: 'Coletas', icon: Boxes, capability: 'collection:manage', end: true },
      { to: '/plataforma/dataset', label: 'Dataset e modelos', icon: Database, capability: 'dataset:manage' },
    ],
  },
  {
    group: 'Sistema',
    items: [
      { to: '/plataforma/observabilidade', label: 'Observabilidade', icon: Gauge, capability: 'platform:observability:read' },
      { to: '/plataforma/saude', label: 'Saúde do sistema', icon: Activity },
    ],
  },
]

/** Páginas que trabalham sobre um cliente e precisam dele escolhido no topo. */
export const TOOLS_WITH_TENANT = ['/plataforma/coletas', '/plataforma/planejamento']

export function visibleNav(capabilities: readonly string[]) {
  const set = new Set(capabilities)
  // Item sem capacidade é de qualquer papel de plataforma, não de qualquer pessoa.
  if (!capabilities.some((cap) => cap.startsWith('platform:'))) return []
  return PLATFORM_NAV.map((group) => ({
    ...group,
    items: group.items.filter((item) => !item.capability || set.has(item.capability)),
  })).filter((group) => group.items.length > 0)
}

export function PlatformShell({ children }: { children: ReactNode }) {
  const { logout, memberships, session, selectTenant } = useAuth()
  const me = usePlatformMe()
  const [drawer, setDrawer] = useState(false)
  const location = useLocation()
  useEffect(() => setDrawer(false), [location.pathname])

  const grupos = visibleNav(me.data?.capabilities ?? [])
  // As ferramentas que trabalham sobre um cliente (coleta, planejamento) mandam o
  // cliente em X-Tenant-Id. Escolher aqui não abre o cliente: ver a lavoura dele
  // continua exigindo "Entrar como cliente".
  const pedeCliente = TOOLS_WITH_TENANT.some((prefixo) => location.pathname.startsWith(prefixo))

  const sidebar = (
    <nav className="flex h-full flex-col gap-6 overflow-y-auto px-3 py-5" aria-label="Console da plataforma">
      <Link to="/plataforma" className="px-2">
        <Logo />
        <div className="mt-2 inline-flex items-center gap-1.5 rounded-full bg-accent px-2.5 py-0.5 text-[11px] font-semibold tracking-wide text-accent-ink uppercase">
          <ShieldCheck className="size-3.5" aria-hidden />
          Console da plataforma
        </div>
      </Link>
      {grupos.map((grupo) => (
        <div key={grupo.group}>
          <div className="mb-1.5 px-3 text-[11px] font-medium tracking-wider text-muted uppercase">{grupo.group}</div>
          <ul className="flex flex-col gap-0.5">
            {grupo.items.map((item) => (
              <li key={item.to}>
                <NavLink
                  to={item.to}
                  end={item.end}
                  className={({ isActive }) =>
                    cn(
                      'flex items-center gap-3 rounded-[10px] px-3 py-2 text-[14px] transition-colors',
                      isActive ? 'bg-accent-soft font-medium text-ink' : 'text-ink-2 hover:bg-raised hover:text-ink',
                    )
                  }
                >
                  <item.icon className="size-[18px] shrink-0" aria-hidden />
                  {item.label}
                </NavLink>
              </li>
            ))}
          </ul>
        </div>
      ))}
      <div className="mt-auto px-3 text-[11px] leading-relaxed text-muted">
        Área da equipe ValTexa. Para ver um cliente por dentro, use “Entrar como cliente”: fica registrado na
        auditoria dele, com o seu nome e o motivo.
      </div>
    </nav>
  )

  return (
    <div className="platform-theme flex h-full">
      <aside className="hidden w-64 shrink-0 border-r-4 border-accent bg-surface lg:block">{sidebar}</aside>
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
        <header className="sticky top-0 z-[700] flex h-14 shrink-0 items-center gap-3 border-b border-line bg-accent px-4 text-accent-ink sm:px-6 lg:px-8">
          <button
            type="button"
            onClick={() => setDrawer(true)}
            className="-ml-1 rounded-lg p-2 hover:bg-white/15 lg:hidden"
            aria-label="Abrir menu"
          >
            <Menu className="size-5" />
          </button>
          <ShieldCheck className="size-4" aria-hidden />
          <span className="text-[14px] font-semibold">ValTexa · equipe interna</span>
          {pedeCliente && (
            <label className="ml-4 flex items-center gap-2 text-[13px]">
              <span className="hidden opacity-90 sm:inline">Cliente em foco</span>
              <select
                className="max-w-[40vw] truncate rounded-lg bg-white/15 px-2 py-1 text-[13px] font-medium outline-none"
                value={session?.tenantId ?? ''}
                onChange={(event) => selectTenant(event.target.value)}
                aria-label="Cliente em foco"
              >
                <option value="" disabled>
                  escolha o cliente
                </option>
                {memberships.map((item) => (
                  <option key={item.tenant_id} value={item.tenant_id} className="text-ink">
                    {item.tenant_name}
                  </option>
                ))}
              </select>
            </label>
          )}
          <span className="ml-auto truncate text-[13px] opacity-90">
            {me.data ? `${me.data.full_name} · ${platformRoleLabel(me.data.platform_role)}` : ''}
          </span>
          <NotificationBell audience="plataforma" centralPath="/plataforma/notificacoes" className="hover:bg-white/15" />
          <button
            type="button"
            onClick={logout}
            className="flex items-center gap-1.5 rounded-lg px-2 py-1.5 text-[13px] hover:bg-white/15"
          >
            <LogOut className="size-4" aria-hidden />
            Sair
          </button>
        </header>
        <main className="min-w-0 flex-1 overflow-y-auto px-4 pt-6 pb-10 sm:px-6 lg:px-8">
          <div className="mx-auto max-w-[1400px]">{children}</div>
        </main>
      </div>
    </div>
  )
}
