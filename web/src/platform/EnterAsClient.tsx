import { LogIn } from 'lucide-react'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { useAuth } from '@/auth/AuthProvider'
import { Button, ErrorBox, FormField, Modal } from '@/components/ui'
import { useStartSupport, type PlatformTenant } from '@/platform/api'

/** Regras de "entrar como cliente" que a tela confere antes de chamar o servidor. */
export function supportFormProblems(form: {
  reason: string
  minutes: number
  assisted: boolean
  assistedReason: string
}): string[] {
  const problemas: string[] = []
  if (form.reason.trim().length < 10) problemas.push('Descreva o motivo (10 caracteres ou mais).')
  if (form.minutes < 5 || form.minutes > 480) problemas.push('O prazo vai de 5 min a 8 h.')
  if (form.assisted && form.assistedReason.trim().length < 10) {
    problemas.push('O modo assistido pede um motivo próprio (10 caracteres ou mais).')
  }
  return problemas
}

/**
 * Abre a sessão de suporte (brief, seção 29). Motivo obrigatório, prazo e
 * modo: leitura por padrão; escrita só marcando o assistido, com motivo próprio.
 */
export function EnterAsClient({
  tenant,
  canAssist,
  onClose,
  ticket,
}: {
  tenant: Pick<PlatformTenant, 'id' | 'name'>
  canAssist: boolean
  onClose: () => void
  /** Chamado que motiva a entrada: fica ligado à sessão e aparece no histórico dele. */
  ticket?: { id: string; code: string; title: string }
}) {
  const { enterSupport } = useAuth()
  const navigate = useNavigate()
  const iniciar = useStartSupport()
  const [reason, setReason] = useState(ticket ? `Atender o chamado ${ticket.code}: ${ticket.title}` : '')
  const [ticketRef, setTicketRef] = useState(ticket?.code ?? '')
  const [minutes, setMinutes] = useState(60)
  const [assisted, setAssisted] = useState(false)
  const [assistedReason, setAssistedReason] = useState('')
  const problemas = supportFormProblems({ reason, minutes, assisted, assistedReason })

  async function entrar() {
    const aberta = await iniciar.mutateAsync({
      tenant_id: tenant.id,
      reason: reason.trim(),
      duration_minutes: minutes,
      ticket_ref: ticketRef.trim() || null,
      ticket_id: ticket?.id ?? null,
      assisted_reason: assisted ? assistedReason.trim() : null,
    })
    enterSupport({
      ...aberta,
      session: { ...aberta.session, tenant_name: aberta.session.tenant_name ?? tenant.name },
    })
    navigate('/')
  }

  return (
    <Modal
      open
      onClose={onClose}
      title={`Entrar como cliente: ${tenant.name}`}
      description="A entrada fica na auditoria do cliente, com o seu nome, o motivo e cada tela aberta. Ele vê isso em Configurações."
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancelar
          </Button>
          <Button
            variant={assisted ? 'danger' : 'primary'}
            icon={<LogIn className="size-4" />}
            disabled={problemas.length > 0}
            loading={iniciar.isPending}
            onClick={entrar}
          >
            {assisted ? 'Entrar com escrita' : 'Entrar em modo leitura'}
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-4">
        <FormField label="Motivo" hint="Obrigatório. O cliente vê este texto.">
          <textarea
            className="input min-h-20"
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            placeholder="Ex.: chamado 42 — o talhão B sumiu do mapa"
          />
        </FormField>
        <div className="grid gap-4 sm:grid-cols-2">
          <FormField label="Chamado (opcional)" hint={ticket ? 'Ligado a esta sessão.' : undefined}>
            <input
              className="input"
              value={ticketRef}
              disabled={Boolean(ticket)}
              onChange={(event) => setTicketRef(event.target.value)}
            />
          </FormField>
          <FormField label="Prazo" hint="A sessão termina sozinha.">
            <select
              className="input"
              value={minutes}
              onChange={(event) => setMinutes(Number(event.target.value))}
            >
              <option value={15}>15 min</option>
              <option value={30}>30 min</option>
              <option value={60}>1 h</option>
              <option value={120}>2 h</option>
              <option value={240}>4 h</option>
            </select>
          </FormField>
        </div>
        {canAssist && (
          <label className="flex items-start gap-2 text-[13px]">
            <input
              type="checkbox"
              className="mt-0.5"
              checked={assisted}
              onChange={(event) => setAssisted(event.target.checked)}
            />
            <span>
              <span className="font-medium">Modo assistido</span> — alterar dados em nome do cliente. Sem isto,
              a sessão só lê.
            </span>
          </label>
        )}
        {assisted && (
          <FormField label="Motivo da escrita">
            <textarea
              className="input min-h-16"
              value={assistedReason}
              onChange={(event) => setAssistedReason(event.target.value)}
              placeholder="Ex.: o cliente pediu para corrigir o espaçamento do talhão B"
            />
          </FormField>
        )}
        {problemas.length > 0 && (reason || assisted) && (
          <ul className="list-disc pl-5 text-[12px] text-muted">
            {problemas.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        )}
        <ErrorBox error={iniciar.error} />
      </div>
    </Modal>
  )
}
