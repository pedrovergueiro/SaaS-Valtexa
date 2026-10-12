import { ArrowLeft } from 'lucide-react'
import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { useClientTicketAction, useCommentTicket, useTicket } from '@/api/support'
import { useAuth } from '@/auth/AuthProvider'
import { TicketConversation, TicketHistory } from '@/components/TicketThread'
import { Badge, Button, Card, CardHeader, ErrorBox, FormField, Modal, PageHeader, Spinner } from '@/components/ui'
import { fmt } from '@/lib/format'
import {
  clientActions,
  incidentStatusLabel,
  incidentStatusTone,
  priorityLabel,
  priorityTone,
  ticketStatusLabel,
  ticketStatusTone,
} from '@/lib/support'

/** Um chamado, do lado do cliente: conversa, histórico, fechar e reabrir. */
export default function SupportTicket() {
  const { id = '' } = useParams()
  const { can } = useAuth()
  const chamado = useTicket('cliente', id)
  const comentar = useCommentTicket('cliente', id)
  const acao = useClientTicketAction(id)
  const [reabrir, setReabrir] = useState(false)
  const [motivo, setMotivo] = useState('')

  if (chamado.isLoading) return <Spinner />
  if (!chamado.data) return <ErrorBox error={chamado.error} />
  const t = chamado.data
  const pode = can('support:ticket')
  const acoes = clientActions(t.status)

  return (
    <>
      <Link to="/suporte" className="mb-3 inline-flex items-center gap-1 text-[13px] text-muted hover:text-ink">
        <ArrowLeft className="size-4" aria-hidden /> Suporte
      </Link>
      <PageHeader
        eyebrow={t.code}
        title={t.title}
        actions={
          <>
            <Badge tone={ticketStatusTone(t.status)}>{ticketStatusLabel(t.status, 'cliente')}</Badge>
            <Badge tone={priorityTone(t.priority)}>Prioridade {priorityLabel(t.priority).toLowerCase()}</Badge>
            {pode && acoes.close && (
              <Button size="sm" loading={acao.isPending} onClick={() => acao.mutate({ action: 'close' })}>
                Fechar (resolvido)
              </Button>
            )}
            {pode && acoes.reopen && (
              <Button size="sm" onClick={() => setReabrir(true)}>
                Reabrir
              </Button>
            )}
          </>
        }
      />
      <ErrorBox error={acao.error} className="mb-4" />
      <div className="grid gap-4 lg:grid-cols-[1fr_360px]">
        <div className="flex flex-col gap-4">
          {t.incident && (
            <Card className="border-l-4 border-l-warning">
              <CardHeader
                title={`Faz parte de um incidente: ${t.incident.title}`}
                subtitle={t.incident.public_note ?? 'A equipe está tratando o problema para todos os clientes afetados.'}
                actions={<Badge tone={incidentStatusTone(t.incident.status)}>{incidentStatusLabel(t.incident.status)}</Badge>}
              />
            </Card>
          )}
          <TicketConversation
            ticket={t}
            side="cliente"
            canComment={pode && acoes.comment}
            sending={comentar.isPending}
            error={comentar.error}
            onSend={(body) => comentar.mutateAsync({ body })}
          />
        </div>
        <div className="flex flex-col gap-4">
          <Card>
            <CardHeader title="Detalhes" />
            <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 px-5 pb-4 text-[13px]">
              <dt className="text-muted">Robô</dt>
              <dd>{t.device_id ? <Link className="hover:underline" to={`/frota/${t.device_id}`}>{t.device_label}</Link> : '—'}</dd>
              <dt className="text-muted">Missão</dt>
              <dd>{t.mission_id ? <Link className="hover:underline" to={`/missoes/${t.mission_id}`}>abrir missão</Link> : '—'}</dd>
              <dt className="text-muted">Responsável</dt>
              <dd>{t.assignee_label ?? 'ainda não atribuído'}</dd>
              <dt className="text-muted">Primeira resposta</dt>
              <dd>{t.first_response_at ? fmt.dateTime(t.first_response_at) : 'aguardando'}</dd>
            </dl>
          </Card>
          <TicketHistory ticket={t} side="cliente" />
        </div>
      </div>
      {reabrir && (
        <Modal
          open
          onClose={() => setReabrir(false)}
          title="Reabrir chamado"
          footer={
            <Button
              variant="primary"
              disabled={motivo.trim().length < 5}
              loading={acao.isPending}
              onClick={async () => {
                await acao.mutateAsync({ action: 'reopen', reason: motivo.trim() })
                setReabrir(false)
                setMotivo('')
              }}
            >
              Reabrir
            </Button>
          }
        >
          <FormField label="Por que reabrir">
            <textarea className="input min-h-20" value={motivo} onChange={(event) => setMotivo(event.target.value)} />
          </FormField>
          <ErrorBox error={acao.error} className="mt-3" />
        </Modal>
      )}
    </>
  )
}
