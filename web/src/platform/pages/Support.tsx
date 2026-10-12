import { AlertOctagon, LifeBuoy, Plus } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'

import { useCreateIncident, useIncident, useIncidents, useTickets, useUpdateIncident } from '@/api/support'
import type { IncidentOut } from '@/api/types'
import { Badge, Button, Card, CardHeader, Empty, ErrorBox, FormField, Modal, PageHeader, Spinner, Table, Tabs, td, th } from '@/components/ui'
import { fmt } from '@/lib/format'
import {
  INCIDENT_SEVERITIES,
  INCIDENT_STATUSES,
  incidentSeverityLabel,
  incidentStatusLabel,
  incidentStatusTone,
  priorityLabel,
  priorityTone,
  queueOrder,
  TICKET_STATUSES,
  ticketStatusLabel,
  ticketStatusTone,
  waitingMinutes,
} from '@/lib/support'
import { usePlatformMe } from '@/platform/api'

type Aba = 'fila' | 'incidentes'

/** Suporte no console interno (seção 49): a fila de chamados de todos os clientes e os incidentes. */
export default function PlatformSupport() {
  const [aba, setAba] = useState<Aba>('fila')
  const me = usePlatformMe()
  const gere = me.data?.capabilities.includes('platform:ticket:manage') ?? false
  return (
    <>
      <PageHeader
        title="Suporte"
        subtitle="Chamados de todos os clientes, em fila (urgentes e mais antigos primeiro), e os incidentes que agrupam vários."
      />
      <div className="mb-4">
        <Tabs
          items={[
            { value: 'fila', label: 'Chamados' },
            { value: 'incidentes', label: 'Incidentes' },
          ]}
          value={aba}
          onChange={setAba}
        />
      </div>
      {aba === 'fila' ? <Fila gere={gere} /> : <Incidentes gere={gere} />}
    </>
  )
}

function Fila({ gere }: { gere: boolean }) {
  const [status, setStatus] = useState('')
  const [selecionados, setSelecionados] = useState<string[]>([])
  const [incidente, setIncidente] = useState(false)
  const chamados = useTickets('plataforma', status ? { status } : { open_only: true })
  const agora = new Date()
  const linhas = queueOrder(chamados.data ?? [])

  return (
    <Card>
      <CardHeader
        title="Fila"
        actions={
          <>
            <select className="input h-9" value={status} onChange={(event) => setStatus(event.target.value)} aria-label="Situação">
              <option value="">Em andamento</option>
              {TICKET_STATUSES.map((valor) => (
                <option key={valor} value={valor}>
                  {ticketStatusLabel(valor)}
                </option>
              ))}
            </select>
            {gere && (
              <Button
                size="sm"
                icon={<AlertOctagon className="size-4" />}
                disabled={selecionados.length === 0}
                onClick={() => setIncidente(true)}
              >
                Agrupar em incidente ({selecionados.length})
              </Button>
            )}
          </>
        }
      />
      <ErrorBox error={chamados.error} className="mx-5 mb-3" />
      {chamados.isLoading && <Spinner />}
      {linhas.length === 0 && !chamados.isLoading && (
        <Empty title="Fila vazia" icon={<LifeBuoy className="size-5" />}>
          Nenhum chamado nesta situação.
        </Empty>
      )}
      {linhas.length > 0 && (
        <Table>
          <thead>
            <tr>
              {gere && <th className={th} />}
              <th className={th}>Chamado</th>
              <th className={th}>Cliente</th>
              <th className={th}>Situação</th>
              <th className={th}>Prioridade</th>
              <th className={th}>Responsável</th>
              <th className={th}>Espera / atividade</th>
            </tr>
          </thead>
          <tbody>
            {linhas.map((chamado) => {
              const espera = waitingMinutes(chamado, agora)
              return (
                <tr key={chamado.id} className="hover:bg-raised">
                  {gere && (
                    <td className={td}>
                      <input
                        type="checkbox"
                        aria-label={`Selecionar ${chamado.code}`}
                        checked={selecionados.includes(chamado.id)}
                        onChange={(event) =>
                          setSelecionados((antes) =>
                            event.target.checked ? [...antes, chamado.id] : antes.filter((id) => id !== chamado.id),
                          )
                        }
                      />
                    </td>
                  )}
                  <td className={td}>
                    <Link to={`/plataforma/suporte/${chamado.id}`} className="font-medium hover:underline">
                      {chamado.code} · {chamado.title}
                    </Link>
                    {chamado.incident && <div className="text-[12px] text-muted">{chamado.incident.code}</div>}
                  </td>
                  <td className={td}>{chamado.tenant_name}</td>
                  <td className={td}>
                    <Badge tone={ticketStatusTone(chamado.status)}>{ticketStatusLabel(chamado.status)}</Badge>
                  </td>
                  <td className={td}>
                    <Badge tone={priorityTone(chamado.priority)}>{priorityLabel(chamado.priority)}</Badge>
                  </td>
                  <td className={td}>{chamado.assignee_label ?? <span className="text-muted">ninguém</span>}</td>
                  <td className={td}>
                    {espera !== null ? (
                      <span className="text-warning">sem resposta há {fmt.number(espera)} min</span>
                    ) : (
                      fmt.ago(chamado.last_activity_at)
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </Table>
      )}
      {incidente && (
        <NovoIncidente
          ticketIds={selecionados}
          onClose={() => {
            setIncidente(false)
            setSelecionados([])
          }}
        />
      )}
    </Card>
  )
}

function NovoIncidente({ ticketIds, onClose }: { ticketIds: string[]; onClose: () => void }) {
  const criar = useCreateIncident()
  const [titulo, setTitulo] = useState('')
  const [severidade, setSeveridade] = useState('media')
  const [nota, setNota] = useState('')
  return (
    <Modal
      open
      onClose={onClose}
      title="Novo incidente"
      description={`${ticketIds.length} chamado(s) serão ligados. Cada cliente vê a nota pública no chamado dele.`}
      footer={
        <Button
          variant="primary"
          disabled={titulo.trim().length < 5}
          loading={criar.isPending}
          onClick={async () => {
            await criar.mutateAsync({
              title: titulo.trim(),
              severity: severidade,
              public_note: nota.trim() || null,
              ticket_ids: ticketIds,
            })
            onClose()
          }}
        >
          Criar incidente
        </Button>
      }
    >
      <div className="flex flex-col gap-4">
        <FormField label="Título">
          <input className="input" value={titulo} onChange={(event) => setTitulo(event.target.value)} />
        </FormField>
        <FormField label="Severidade">
          <select className="input" value={severidade} onChange={(event) => setSeveridade(event.target.value)}>
            {INCIDENT_SEVERITIES.map((valor) => (
              <option key={valor} value={valor}>
                {incidentSeverityLabel(valor)}
              </option>
            ))}
          </select>
        </FormField>
        <FormField label="Nota pública (o cliente lê)">
          <textarea className="input min-h-20" value={nota} onChange={(event) => setNota(event.target.value)} />
        </FormField>
        <ErrorBox error={criar.error} />
      </div>
    </Modal>
  )
}

function Incidentes({ gere }: { gere: boolean }) {
  const lista = useIncidents()
  const [aberto, setAberto] = useState<string | null>(null)
  return (
    <Card>
      <CardHeader title="Incidentes" subtitle="Um problema que atinge vários chamados (de um ou vários clientes)." />
      <ErrorBox error={lista.error} className="mx-5 mb-3" />
      {lista.isLoading && <Spinner />}
      {lista.data?.length === 0 && (
        <Empty title="Nenhum incidente" icon={<Plus className="size-5" />}>
          Selecione chamados na fila e agrupe-os em um incidente.
        </Empty>
      )}
      {!!lista.data?.length && (
        <Table>
          <thead>
            <tr>
              <th className={th}>Incidente</th>
              <th className={th}>Situação</th>
              <th className={th}>Severidade</th>
              <th className={th}>Chamados</th>
              <th className={th}>Início</th>
            </tr>
          </thead>
          <tbody>
            {lista.data.map((inc: IncidentOut) => (
              <tr key={inc.id} className="cursor-pointer hover:bg-raised" onClick={() => setAberto(inc.id)}>
                <td className={td}>
                  <span className="font-medium">{inc.code}</span> · {inc.title}
                </td>
                <td className={td}>
                  <Badge tone={incidentStatusTone(inc.status)}>{incidentStatusLabel(inc.status)}</Badge>
                </td>
                <td className={td}>{incidentSeverityLabel(inc.severity)}</td>
                <td className={td}>
                  {inc.ticket_count} em {inc.tenant_count} cliente(s)
                </td>
                <td className={td}>{fmt.dateTime(inc.started_at)}</td>
              </tr>
            ))}
          </tbody>
        </Table>
      )}
      {aberto && <DetalheDoIncidente id={aberto} gere={gere} onClose={() => setAberto(null)} />}
    </Card>
  )
}

function DetalheDoIncidente({ id, gere, onClose }: { id: string; gere: boolean; onClose: () => void }) {
  const inc = useIncident(id)
  const atualizar = useUpdateIncident(id)
  const [status, setStatus] = useState<string | null>(null)
  const [nota, setNota] = useState<string | null>(null)
  const dados = inc.data
  return (
    <Modal open wide onClose={onClose} title={dados ? `${dados.code} · ${dados.title}` : 'Incidente'}>
      {inc.isLoading && <Spinner />}
      {dados && (
        <div className="flex flex-col gap-4">
          {gere ? (
            <div className="grid gap-4 sm:grid-cols-[200px_1fr]">
              <FormField label="Situação">
                <select className="input" value={status ?? dados.status} onChange={(event) => setStatus(event.target.value)}>
                  {INCIDENT_STATUSES.map((valor) => (
                    <option key={valor} value={valor}>
                      {incidentStatusLabel(valor)}
                    </option>
                  ))}
                </select>
              </FormField>
              <FormField label="Nota pública" hint="Ao mudar a situação ou a nota, cada cliente afetado é avisado.">
                <textarea
                  className="input min-h-16"
                  value={nota ?? dados.public_note ?? ''}
                  onChange={(event) => setNota(event.target.value)}
                />
              </FormField>
              <div className="sm:col-span-2 flex justify-end">
                <Button
                  variant="primary"
                  disabled={status === null && nota === null}
                  loading={atualizar.isPending}
                  onClick={async () => {
                    await atualizar.mutateAsync({
                      ...(status !== null ? { status } : {}),
                      ...(nota !== null ? { public_note: nota } : {}),
                    })
                    setStatus(null)
                    setNota(null)
                  }}
                >
                  Salvar e avisar os clientes
                </Button>
              </div>
            </div>
          ) : (
            <p className="text-[13px]">{dados.public_note ?? 'Sem nota pública.'}</p>
          )}
          <ErrorBox error={atualizar.error} />
          <Table>
            <thead>
              <tr>
                <th className={th}>Chamado</th>
                <th className={th}>Cliente</th>
                <th className={th}>Situação</th>
              </tr>
            </thead>
            <tbody>
              {dados.tickets.map((chamado) => (
                <tr key={chamado.id}>
                  <td className={td}>
                    <Link className="hover:underline" to={`/plataforma/suporte/${chamado.id}`}>
                      {chamado.code} · {chamado.title}
                    </Link>
                  </td>
                  <td className={td}>{chamado.tenant_name}</td>
                  <td className={td}>
                    <Badge tone={ticketStatusTone(chamado.status)}>{ticketStatusLabel(chamado.status)}</Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </Table>
        </div>
      )}
    </Modal>
  )
}
