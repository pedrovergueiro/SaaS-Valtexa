import { ArrowLeft, LogIn } from 'lucide-react'
import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { useAssignees, useCommentTicket, useIncidents, useTicket, useUpdateTicket } from '@/api/support'
import type { TicketUpdate } from '@/api/types'
import { TicketConversation, TicketHistory } from '@/components/TicketThread'
import { Badge, Button, Card, CardHeader, ErrorBox, FormField, PageHeader, Spinner } from '@/components/ui'
import { fmt } from '@/lib/format'
import {
  incidentStatusLabel,
  priorityLabel,
  priorityTone,
  TICKET_PRIORITIES,
  TICKET_STATUSES,
  ticketStatusLabel,
  ticketStatusTone,
} from '@/lib/support'
import { usePlatformMe } from '@/platform/api'
import { EnterAsClient } from '@/platform/EnterAsClient'

/** Um chamado no console interno: atender, nota interna, incidente e entrar no cliente. */
export default function PlatformSupportTicket() {
  const { id = '' } = useParams()
  const me = usePlatformMe()
  const caps = new Set(me.data?.capabilities ?? [])
  const gere = caps.has('platform:ticket:manage')
  const chamado = useTicket('plataforma', id)
  const comentar = useCommentTicket('plataforma', id)
  const atualizar = useUpdateTicket(id)
  const responsaveis = useAssignees()
  const incidentes = useIncidents({ open_only: true })
  const [entrar, setEntrar] = useState(false)

  if (chamado.isLoading) return <Spinner />
  if (!chamado.data) return <ErrorBox error={chamado.error} />
  const t = chamado.data
  const muda = (corpo: Partial<TicketUpdate>) => atualizar.mutate(corpo)

  return (
    <>
      <Link to="/plataforma/suporte" className="mb-3 inline-flex items-center gap-1 text-[13px] text-muted hover:text-ink">
        <ArrowLeft className="size-4" aria-hidden /> Suporte
      </Link>
      <PageHeader
        eyebrow={`${t.code} · ${t.tenant_name ?? ''}`}
        title={t.title}
        actions={
          <>
            <Badge tone={ticketStatusTone(t.status)}>{ticketStatusLabel(t.status)}</Badge>
            <Badge tone={priorityTone(t.priority)}>{priorityLabel(t.priority)}</Badge>
            {caps.has('platform:support:session') && (
              <Button size="sm" icon={<LogIn className="size-4" />} onClick={() => setEntrar(true)}>
                Entrar como cliente
              </Button>
            )}
          </>
        }
      />
      <ErrorBox error={atualizar.error} className="mb-4" />
      <div className="grid gap-4 lg:grid-cols-[1fr_380px]">
        <TicketConversation
          ticket={t}
          side="plataforma"
          canComment={gere && t.status !== 'fechado'}
          allowInternal
          sending={comentar.isPending}
          error={comentar.error}
          onSend={(body, internal) => comentar.mutateAsync({ body, internal })}
        />
        <div className="flex flex-col gap-4">
          <Card>
            <CardHeader title="Atendimento" subtitle={gere ? 'Cada mudança vai para o histórico e a auditoria.' : 'Só leitura para o seu papel.'} />
            <div className="flex flex-col gap-3 px-5 pb-4">
              <FormField label="Situação">
                <select className="input" disabled={!gere} value={t.status} onChange={(event) => muda({ status: event.target.value as TicketUpdate['status'] })}>
                  {TICKET_STATUSES.map((valor) => (
                    <option key={valor} value={valor}>
                      {ticketStatusLabel(valor)}
                    </option>
                  ))}
                </select>
              </FormField>
              <FormField label="Prioridade">
                <select className="input" disabled={!gere} value={t.priority} onChange={(event) => muda({ priority: event.target.value as TicketUpdate['priority'] })}>
                  {TICKET_PRIORITIES.map((valor) => (
                    <option key={valor} value={valor}>
                      {priorityLabel(valor)}
                    </option>
                  ))}
                </select>
              </FormField>
              <FormField label="Responsável">
                <select
                  className="input"
                  disabled={!gere}
                  value={t.assignee_id ?? ''}
                  onChange={(event) => muda(event.target.value ? { assignee_id: event.target.value } : { unassign: true })}
                >
                  <option value="">ninguém</option>
                  {responsaveis.data?.map((pessoa) => (
                    <option key={pessoa.id} value={pessoa.id}>
                      {pessoa.full_name}
                    </option>
                  ))}
                </select>
              </FormField>
              <FormField label="Incidente">
                <select
                  className="input"
                  disabled={!gere}
                  value={t.incident?.id ?? ''}
                  onChange={(event) => muda(event.target.value ? { incident_id: event.target.value } : { unlink_incident: true })}
                >
                  <option value="">nenhum</option>
                  {t.incident && !incidentes.data?.some((inc) => inc.id === t.incident?.id) && (
                    <option value={t.incident.id}>
                      {t.incident.code} · {t.incident.title} ({incidentStatusLabel(t.incident.status)})
                    </option>
                  )}
                  {incidentes.data?.map((inc) => (
                    <option key={inc.id} value={inc.id}>
                      {inc.code} · {inc.title}
                    </option>
                  ))}
                </select>
              </FormField>
              <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 pt-1 text-[13px]">
                <dt className="text-muted">Robô</dt>
                <dd>{t.device_label ?? '—'}</dd>
                <dt className="text-muted">Missão</dt>
                <dd className="truncate">{t.mission_id ?? '—'}</dd>
                <dt className="text-muted">Aberto via</dt>
                <dd>{t.opened_via === 'cliente' ? 'console do cliente' : 'equipe, em nome do cliente'}</dd>
                <dt className="text-muted">1ª resposta</dt>
                <dd>{t.first_response_at ? fmt.dateTime(t.first_response_at) : 'pendente'}</dd>
              </dl>
            </div>
          </Card>
          {(t.support_sessions ?? []).length > 0 && (
            <Card>
              <CardHeader title="Sessões de suporte deste chamado" />
              <ul className="flex flex-col gap-2 px-5 pb-4 text-[13px]">
                {(t.support_sessions ?? []).map((sessao) => (
                  <li key={sessao.id}>
                    <span className="font-medium">{sessao.user_email}</span> · {sessao.mode} ·{' '}
                    {fmt.dateTime(sessao.started_at)} · {sessao.request_count} requisição(ões)
                    {sessao.is_open ? <Badge tone="warning">aberta</Badge> : null}
                  </li>
                ))}
              </ul>
            </Card>
          )}
          <TicketHistory ticket={t} side="plataforma" />
        </div>
      </div>
      {entrar && (
        <EnterAsClient
          tenant={{ id: t.tenant_id, name: t.tenant_name ?? 'cliente' }}
          canAssist={caps.has('platform:support:assist')}
          ticket={{ id: t.id, code: t.code, title: t.title }}
          onClose={() => setEntrar(false)}
        />
      )}
    </>
  )
}
