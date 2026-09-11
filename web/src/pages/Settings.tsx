import { useQuery } from '@tanstack/react-query'
import { AlertTriangle, CheckCircle2, UserPlus } from 'lucide-react'
import { useState } from 'react'

import { api } from '@/api/client'
import { keys, useApiMutation, useUsers } from '@/api/queries'
import type { HealthResponse, UserOut } from '@/api/types'
import { useAuth } from '@/auth/AuthProvider'
import { Badge, Button, Card, CardHeader, Empty, ErrorBox, FormField, Modal, PageHeader, Spinner, Table, Tabs, td, th } from '@/components/ui'
import { role as roleLabel, ROLES } from '@/lib/labels'

type View = 'people' | 'platform'

export default function Settings() {
  const [view, setView] = useState<View>('people')
  return (
    <>
      <PageHeader title="Configurações" subtitle="Pessoas, papéis e o estado da plataforma." />
      <div className="mb-4">
        <Tabs<View>
          value={view}
          onChange={setView}
          items={[
            { value: 'people', label: 'Pessoas' },
            { value: 'platform', label: 'Plataforma' },
          ]}
        />
      </div>
      {view === 'people' ? <People /> : <Platform />}
    </>
  )
}

function People() {
  const { can, me } = useAuth()
  const users = useUsers()
  const [inviting, setInviting] = useState(false)
  const manage = can('user:manage')

  const update = useApiMutation(
    ({ id, role }: { id: string; role: string }) => api<UserOut>(`/v1/users/${id}`, { method: 'PATCH', body: { role } }),
    [keys.users],
  )
  const remove = useApiMutation((id: string) => api(`/v1/users/${id}`, { method: 'DELETE' }), [keys.users])

  return (
    <Card>
      <CardHeader
        title="Pessoas com acesso"
        subtitle="Papéis são capacidades, não hierarquia: só o agrônomo aprova aplicação — nem o proprietário."
        actions={
          manage && (
            <Button variant="primary" icon={<UserPlus className="size-4" />} onClick={() => setInviting(true)}>
              Adicionar pessoa
            </Button>
          )
        }
      />
      <ErrorBox error={users.error ?? update.error ?? remove.error} className="mx-5 mb-4" />
      {users.isLoading && <Spinner />}
      {users.data?.length === 0 && <Empty title="Ninguém ainda" />}
      {(users.data?.length ?? 0) > 0 && (
        <Table>
          <thead>
            <tr>
              <th className={th}>Nome</th>
              <th className={th}>E-mail</th>
              <th className={th}>Papel</th>
              <th className={th} />
            </tr>
          </thead>
          <tbody>
            {users.data?.map((user) => {
              const self = user.id === me?.id
              return (
                <tr key={user.id} className="hover:bg-raised">
                  <td className={td}>
                    {user.full_name}
                    {self && <span className="ml-2 text-[12px] text-muted">(você)</span>}
                  </td>
                  <td className={`${td} text-ink-2`}>{user.email}</td>
                  <td className={td}>
                    {manage && !self ? (
                      <select
                        className="input h-8 w-auto py-0 text-[13px]"
                        value={user.role}
                        onChange={(event) => update.mutate({ id: user.id, role: event.target.value })}
                        aria-label={`Papel de ${user.full_name}`}
                      >
                        {ROLES.map((value) => (
                          <option key={value} value={value}>
                            {roleLabel(value)}
                          </option>
                        ))}
                      </select>
                    ) : (
                      roleLabel(user.role)
                    )}
                  </td>
                  <td className={`${td} text-right`}>
                    {manage && !self && (
                      <Button size="sm" variant="ghost" onClick={() => remove.mutate(user.id)}>
                        Remover
                      </Button>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </Table>
      )}
      {inviting && <InviteModal onClose={() => setInviting(false)} />}
    </Card>
  )
}

function InviteModal({ onClose }: { onClose: () => void }) {
  const [email, setEmail] = useState('')
  const [name, setName] = useState('')
  const [password, setPassword] = useState('')
  const [role, setRole] = useState('viewer')
  const invite = useApiMutation(
    () => api('/v1/users', { method: 'POST', body: { email, full_name: name, password, role } }),
    [keys.users],
  )
  return (
    <Modal
      open
      onClose={onClose}
      title="Adicionar pessoa"
      description="Se a pessoa já tem conta em outro cliente, ela ganha acesso a este sem duplicar a conta."
      footer={
        <>
          <Button onClick={onClose}>Cancelar</Button>
          <Button variant="primary" loading={invite.isPending} disabled={!email || !name || password.length < 8} onClick={() => invite.mutate(undefined, { onSuccess: onClose })}>
            Adicionar
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-4">
        <FormField label="Nome">
          <input className="input" value={name} onChange={(event) => setName(event.target.value)} />
        </FormField>
        <FormField label="E-mail">
          <input className="input" type="email" value={email} onChange={(event) => setEmail(event.target.value)} />
        </FormField>
        <FormField label="Senha inicial" hint="Mínimo de 8 caracteres. Combine a troca no primeiro acesso.">
          <input className="input" type="password" value={password} onChange={(event) => setPassword(event.target.value)} />
        </FormField>
        <FormField label="Papel">
          <select className="input" value={role} onChange={(event) => setRole(event.target.value)}>
            {ROLES.map((value) => (
              <option key={value} value={value}>
                {roleLabel(value)}
              </option>
            ))}
          </select>
        </FormField>
        <ErrorBox error={invite.error} />
      </div>
    </Modal>
  )
}

function Platform() {
  const health = useQuery({ queryKey: ['health'], queryFn: () => api<HealthResponse>('/health'), refetchInterval: 30_000 })
  const data = health.data
  const warnings = data?.warnings ?? []
  return (
    <Card>
      <CardHeader title="Estado da plataforma" subtitle="O que o processo diz de si mesmo em /health." />
      <ErrorBox error={health.error} className="mx-5 mb-4" />
      {data && (
        <div className="px-5 pb-5">
          <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-2.5 text-[13px]">
            <dt className="text-muted">Ambiente</dt>
            <dd>
              <Badge tone={data.environment === 'production' ? 'good' : 'info'}>{data.environment}</Badge>
            </dd>
            <dt className="text-muted">Protocolo dos robôs</dt>
            <dd className="num">v{data.protocol_version}</dd>
            <dt className="text-muted">Banco</dt>
            <dd>{data.database}</dd>
            <dt className="text-muted">Inferência</dt>
            <dd className="num break-all">{data.inference}</dd>
            <dt className="text-muted">Eventos pendentes</dt>
            <dd className="num">{data.pending_events}</dd>
          </dl>
          <div className="mt-5">
            <div className="mb-2 text-[13px] font-medium">Pendências para produção</div>
            {warnings.length === 0 ? (
              <div className="flex items-center gap-2 text-[13px] text-ink-2">
                <CheckCircle2 className="size-4 text-good" aria-hidden /> Nenhuma.
              </div>
            ) : (
              <ul className="flex flex-col gap-2">
                {warnings.map((warning) => (
                  <li key={warning} className="flex items-start gap-2 text-[13px]">
                    <AlertTriangle className="mt-0.5 size-4 shrink-0 text-warning" aria-hidden />
                    {warning}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
    </Card>
  )
}
