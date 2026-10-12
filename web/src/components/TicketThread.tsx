import { Lock, Send } from 'lucide-react'
import { useState } from 'react'

import type { TicketDetailOut } from '@/api/types'
import { Badge, Button, Card, CardHeader, ErrorBox } from '@/components/ui'
import { cn } from '@/lib/cn'
import { fmt } from '@/lib/format'
import { historyLine } from '@/lib/support'

/** A conversa de um chamado: comentários (e notas internas, só no console interno). */
export function TicketConversation({
  ticket,
  side,
  canComment,
  allowInternal = false,
  sending,
  error,
  onSend,
}: {
  ticket: TicketDetailOut
  side: 'cliente' | 'plataforma'
  canComment: boolean
  allowInternal?: boolean
  sending: boolean
  error: unknown
  onSend: (body: string, internal: boolean) => Promise<unknown>
}) {
  const [texto, setTexto] = useState('')
  const [interno, setInterno] = useState(false)

  async function enviar() {
    // Limpa já: o que a pessoa digitar enquanto o envio anda não pode ser apagado
    // quando ele termina. Se falhar, o texto volta.
    const corpo = texto.trim()
    const eraInterno = interno
    setTexto('')
    setInterno(false)
    try {
      await onSend(corpo, eraInterno)
    } catch {
      setTexto(corpo)
      setInterno(eraInterno)
    }
  }

  return (
    <Card>
      <CardHeader title="Conversa" subtitle={`Aberto por ${ticket.opened_by_label} em ${fmt.dateTime(ticket.created_at)}`} />
      <div className="flex flex-col gap-3 px-5 pb-4">
        <div className="rounded-[10px] bg-raised px-3.5 py-2.5 text-[14px] whitespace-pre-line">{ticket.description}</div>
        {ticket.comments.map((comentario) => {
          const daEquipe = comentario.side === 'plataforma'
          return (
            <div
              key={comentario.id}
              className={cn(
                'max-w-[85%] rounded-[10px] px-3.5 py-2.5 text-[14px]',
                comentario.internal
                  ? 'self-end border border-dashed border-warning/60 bg-warning/10'
                  : daEquipe === (side === 'plataforma')
                    ? 'self-end bg-accent-soft'
                    : 'self-start border border-line bg-surface',
              )}
            >
              <div className="mb-1 flex items-center gap-2 text-[12px] text-muted">
                {comentario.internal && (
                  <Badge tone="warning">
                    <Lock className="mr-1 inline size-3" aria-hidden />
                    nota interna
                  </Badge>
                )}
                <span className="font-medium text-ink-2">{comentario.author_label}</span>
                <span>{fmt.dateTime(comentario.created_at)}</span>
              </div>
              <div className="whitespace-pre-line">{comentario.body}</div>
            </div>
          )
        })}
        {canComment ? (
          <div className="mt-2 flex flex-col gap-2">
            <textarea
              className="input min-h-20"
              placeholder={side === 'cliente' ? 'Escreva para a equipe da ValTexa…' : 'Responder ao cliente…'}
              value={texto}
              onChange={(event) => setTexto(event.target.value)}
              aria-label="Comentário"
            />
            <div className="flex flex-wrap items-center justify-end gap-3">
              {allowInternal && (
                <label className="flex items-center gap-2 text-[13px]">
                  <input type="checkbox" checked={interno} onChange={(event) => setInterno(event.target.checked)} />
                  Nota interna (o cliente não vê)
                </label>
              )}
              <Button
                variant="primary"
                icon={<Send className="size-4" />}
                disabled={!texto.trim()}
                loading={sending}
                onClick={enviar}
              >
                {interno ? 'Salvar nota' : 'Enviar'}
              </Button>
            </div>
            <ErrorBox error={error} />
          </div>
        ) : (
          <p className="text-[13px] text-muted">
            {ticket.status === 'fechado' ? 'Chamado fechado. Reabra para continuar a conversa.' : 'Seu papel só acompanha os chamados.'}
          </p>
        )}
      </div>
    </Card>
  )
}

export function TicketHistory({ ticket, side }: { ticket: TicketDetailOut; side: 'cliente' | 'plataforma' }) {
  return (
    <Card>
      <CardHeader title="Histórico" subtitle="Toda mudança, com quem e quando." />
      <ol className="flex flex-col gap-2.5 px-5 pb-4">
        {ticket.history.map((evento, indice) => (
          <li key={`${evento.at}-${indice}`} className="text-[13px]">
            <div className="flex flex-wrap items-baseline gap-x-2">
              <span className="text-[12px] text-muted">{fmt.dateTime(evento.at)}</span>
              <span className="font-medium">{evento.actor_label}</span>
              <span className="text-ink-2">{historyLine(evento, side)}</span>
              {evento.internal && <Badge tone="warning">interno</Badge>}
            </div>
            {evento.note && evento.kind !== 'comentario' && (
              <div className="mt-0.5 text-[12px] whitespace-pre-line text-muted">{evento.note}</div>
            )}
          </li>
        ))}
      </ol>
    </Card>
  )
}
