import { LifeBuoy, Plus } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { useDevices, useMissions } from '@/api/queries'
import { useOpenTicket, useTickets } from '@/api/support'
import { useAuth } from '@/auth/AuthProvider'
import { Badge, Button, Card, Empty, ErrorBox, FormField, Modal, PageHeader, Spinner, Table, Tabs, td, th } from '@/components/ui'
import { fmt } from '@/lib/format'
import { missionKind } from '@/lib/labels'
import { priorityLabel, priorityTone, TICKET_PRIORITIES, ticketStatusLabel, ticketStatusTone } from '@/lib/support'

/** Chamados do cliente (seção 49): abre e acompanha os da sua organização. */
export default function Support() {
  const { can } = useAuth()
  const [aba, setAba] = useState<'abertos' | 'todos'>('abertos')
  const [novo, setNovo] = useState(false)
  const chamados = useTickets('cliente', aba === 'abertos' ? { open_only: true } : {})

  return (
    <>
      <PageHeader
        eyebrow="Governança"
        title="Suporte"
        subtitle="Chamados com a equipe da ValTexa. Todo mundo da sua organização acompanha; cada resposta chega como notificação para quem abriu."
        actions={
          can('support:ticket') && (
            <Button variant="primary" icon={<Plus className="size-4" />} onClick={() => setNovo(true)}>
              Abrir chamado
            </Button>
          )
        }
      />
      <div className="mb-4">
        <Tabs
          items={[
            { value: 'abertos', label: 'Em andamento' },
            { value: 'todos', label: 'Todos' },
          ]}
          value={aba}
          onChange={setAba}
        />
      </div>
      <Card>
        <ErrorBox error={chamados.error} className="m-4" />
        {chamados.isLoading && <Spinner />}
        {chamados.data?.length === 0 && (
          <Empty title="Nenhum chamado" icon={<LifeBuoy className="size-5" />}>
            Algo não funciona como deveria? Abra um chamado e ligue ao robô ou à missão.
          </Empty>
        )}
        {!!chamados.data?.length && (
          <Table>
            <thead>
              <tr>
                <th className={th}>Chamado</th>
                <th className={th}>Situação</th>
                <th className={th}>Prioridade</th>
                <th className={th}>Aberto por</th>
                <th className={th}>Última atividade</th>
              </tr>
            </thead>
            <tbody>
              {chamados.data.map((chamado) => (
                <tr key={chamado.id} className="hover:bg-raised">
                  <td className={td}>
                    <Link to={`/suporte/${chamado.id}`} className="font-medium hover:underline">
                      {chamado.code} · {chamado.title}
                    </Link>
                    {chamado.incident && (
                      <div className="text-[12px] text-muted">Incidente {chamado.incident.code}: {chamado.incident.title}</div>
                    )}
                  </td>
                  <td className={td}>
                    <Badge tone={ticketStatusTone(chamado.status)}>{ticketStatusLabel(chamado.status, 'cliente')}</Badge>
                  </td>
                  <td className={td}>
                    <Badge tone={priorityTone(chamado.priority)}>{priorityLabel(chamado.priority)}</Badge>
                  </td>
                  <td className={td}>{chamado.opened_by_label}</td>
                  <td className={td}>{fmt.ago(chamado.last_activity_at)}</td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card>
      {novo && <NewTicket onClose={() => setNovo(false)} />}
    </>
  )
}

function NewTicket({ onClose }: { onClose: () => void }) {
  const navigate = useNavigate()
  const abrir = useOpenTicket('cliente')
  const robos = useDevices()
  const missoes = useMissions({ limit: 30 })
  const [titulo, setTitulo] = useState('')
  const [descricao, setDescricao] = useState('')
  const [prioridade, setPrioridade] = useState('normal')
  const [robo, setRobo] = useState('')
  const [missao, setMissao] = useState('')
  const pronto = titulo.trim().length >= 5 && descricao.trim().length >= 10

  async function enviar() {
    const criado = await abrir.mutateAsync({
      title: titulo.trim(),
      description: descricao.trim(),
      priority: prioridade as (typeof TICKET_PRIORITIES)[number],
      device_id: robo || null,
      mission_id: missao || null,
    })
    navigate(`/suporte/${criado.id}`)
  }

  return (
    <Modal
      open
      onClose={onClose}
      title="Abrir chamado"
      description="Descreva o que aconteceu. Se tem a ver com um robô ou uma missão, ligue aqui: a equipe já abre com o contexto."
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancelar
          </Button>
          <Button variant="primary" disabled={!pronto} loading={abrir.isPending} onClick={enviar}>
            Abrir chamado
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-4">
        <FormField label="Título">
          <input className="input" value={titulo} onChange={(event) => setTitulo(event.target.value)} maxLength={200} />
        </FormField>
        <FormField label="O que aconteceu" hint="Quando começou, o que você já tentou.">
          <textarea className="input min-h-28" value={descricao} onChange={(event) => setDescricao(event.target.value)} />
        </FormField>
        <div className="grid gap-4 sm:grid-cols-3">
          <FormField label="Prioridade">
            <select className="input" value={prioridade} onChange={(event) => setPrioridade(event.target.value)}>
              {TICKET_PRIORITIES.map((valor) => (
                <option key={valor} value={valor}>
                  {priorityLabel(valor)}
                </option>
              ))}
            </select>
          </FormField>
          <FormField label="Robô (opcional)">
            <select className="input" value={robo} onChange={(event) => setRobo(event.target.value)}>
              <option value="">—</option>
              {robos.data?.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name} ({item.serial_number})
                </option>
              ))}
            </select>
          </FormField>
          <FormField label="Missão (opcional)">
            <select className="input" value={missao} onChange={(event) => setMissao(event.target.value)}>
              <option value="">—</option>
              {missoes.data?.map((item) => (
                <option key={item.id} value={item.id}>
                  {missionKind(item.kind)} · {fmt.dateTime(item.created_at)}
                </option>
              ))}
            </select>
          </FormField>
        </div>
        <ErrorBox error={abrir.error} />
      </div>
    </Modal>
  )
}
