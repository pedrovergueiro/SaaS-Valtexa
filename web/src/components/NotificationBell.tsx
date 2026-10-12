import { BellRing } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { useMarkAllRead, useMarkRead, useNotifications, useUnreadCount, type Audience } from '@/api/support'
import type { NotificationOut } from '@/api/types'
import { Badge } from '@/components/ui'
import { cn } from '@/lib/cn'
import { fmt } from '@/lib/format'
import { badgeCount, notificationSeverity, notificationTone } from '@/lib/notifications'

/**
 * O sino das notificações (seção 48): número de não lidas e as últimas, com
 * atalho para a central. Os "Alertas" do topo continuam sendo o estado ao vivo
 * (robô offline agora); aqui fica o que foi avisado a esta pessoa.
 */
export function NotificationBell({
  audience,
  centralPath,
  className,
}: {
  audience: Audience
  centralPath: string
  className?: string
}) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  const navigate = useNavigate()
  const unread = useUnreadCount(audience)
  const recentes = useNotifications(audience, { limit: 8 }, open)
  const marcar = useMarkRead(audience)
  const marcarTodas = useMarkAllRead(audience)
  const numero = badgeCount(unread.data?.unread ?? 0)

  useEffect(() => {
    const listener = (event: MouseEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', listener)
    return () => document.removeEventListener('mousedown', listener)
  }, [])

  function abrir(aviso: NotificationOut) {
    if (!aviso.read_at) marcar.mutate(aviso.id)
    setOpen(false)
    if (aviso.link) navigate(aviso.link)
  }

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className={cn('relative rounded-lg p-2', className ?? 'text-ink-2 hover:bg-raised')}
        aria-label={`Notificações${numero ? `: ${numero} não lidas` : ''}`}
        aria-expanded={open}
      >
        <BellRing className="size-5" />
        {numero && (
          <span className="num absolute top-1 right-0.5 grid min-w-4 place-items-center rounded-full bg-accent px-1 text-[10px] leading-4 font-semibold text-accent-ink">
            {numero}
          </span>
        )}
      </button>
      {open && (
        <div className="card absolute right-0 mt-2 w-[min(92vw,400px)] overflow-hidden text-ink">
          <div className="flex items-center justify-between border-b border-line-soft px-4 py-3">
            <span className="font-medium">Notificações</span>
            <button
              type="button"
              className="text-[12px] text-muted hover:text-ink disabled:opacity-50"
              disabled={!numero || marcarTodas.isPending}
              onClick={() => marcarTodas.mutate()}
            >
              Marcar todas como lidas
            </button>
          </div>
          <ul className="max-h-[60vh] overflow-y-auto">
            {recentes.isLoading && <li className="px-4 py-6 text-center text-[13px] text-muted">Carregando…</li>}
            {recentes.data?.length === 0 && (
              <li className="px-4 py-6 text-center text-[13px] text-muted">Nenhuma notificação.</li>
            )}
            {recentes.data?.map((aviso) => (
              <li key={aviso.id} className="border-b border-line-soft last:border-0">
                <button
                  type="button"
                  onClick={() => abrir(aviso)}
                  className={cn('block w-full px-4 py-3 text-left hover:bg-raised', !aviso.read_at && 'bg-accent-soft/40')}
                >
                  <div className="flex items-center justify-between gap-2">
                    <Badge tone={notificationTone(aviso.severity)}>{notificationSeverity(aviso.severity)}</Badge>
                    <span className="text-[11px] text-muted">{fmt.ago(aviso.created_at)}</span>
                  </div>
                  <div className={cn('mt-1.5 text-[13px]', !aviso.read_at && 'font-semibold')}>{aviso.title}</div>
                  <div className="line-clamp-2 text-[12px] text-ink-2">{aviso.body}</div>
                </button>
              </li>
            ))}
          </ul>
          <Link
            to={centralPath}
            onClick={() => setOpen(false)}
            className="block border-t border-line-soft px-4 py-2.5 text-center text-[13px] font-medium hover:bg-raised"
          >
            Abrir a central e as preferências
          </Link>
        </div>
      )}
    </div>
  )
}
