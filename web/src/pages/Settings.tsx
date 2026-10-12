import { useQuery } from '@tanstack/react-query'
import { KeyRound, UserPlus } from 'lucide-react'
import { useState } from 'react'

import { api } from '@/api/client'
import { keys, useApiMutation, useUsers } from '@/api/queries'
import type { SessionOut, SessionRevoked, UserOut } from '@/api/types'
import { useAuth } from '@/auth/AuthProvider'
import { DataConsentPanel, MyPlanPanel, SupportAccessPanel } from '@/components/AccountPanels'
import { Badge, Button, Card, CardHeader, Empty, ErrorBox, FormField, Modal, PageHeader, Spinner, Table, Tabs, td, th, useToast } from '@/components/ui'
import { fmt } from '@/lib/format'
import { role as roleLabel, ROLES } from '@/lib/labels'

type View = 'people' | 'account' | 'sessions' | 'plan' | 'consent' | 'support'

export default function Settings() {
  const [view, setView] = useState<View>('people')
  return (
    <>
      <PageHeader title="Configurações" subtitle="Pessoas, papéis, sua senha, o plano da conta e o uso dos dados no treino." />
      <div className="mb-4">
        <Tabs<View>
          value={view}
          onChange={setView}
          items={[
            { value: 'people', label: 'Pessoas' },
            { value: 'account', label: 'Minha conta' },
            { value: 'sessions', label: 'Aparelhos conectados' },
            { value: 'plan', label: 'Meu plano' },
            { value: 'consent', label: 'Dados no treino' },
            { value: 'support', label: 'Acessos da ValTexa' },
          ]}
        />
      </div>
      {view === 'people' && <People />}
      {view === 'account' && <MyAccount />}
      {view === 'sessions' && <MySessions />}
      {view === 'plan' && <MyPlanPanel />}
      {view === 'consent' && <DataConsentPanel />}
      {view === 'support' && <SupportAccessPanel />}
    </>
  )
}

function People() {
  const { can, me } = useAuth()
  const users = useUsers()
  const [inviting, setInviting] = useState(false)
  const [resetting, setResetting] = useState<UserOut | null>(null)
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
                      <span className="flex justify-end gap-1">
                        <Button
                          size="sm"
                          variant="ghost"
                          icon={<KeyRound className="size-4" />}
                          onClick={() => setResetting(user)}
                        >
                          Redefinir senha
                        </Button>
                        <Button size="sm" variant="ghost" onClick={() => remove.mutate(user.id)}>
                          Remover
                        </Button>
                      </span>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </Table>
      )}
      {inviting && <InviteModal onClose={() => setInviting(false)} />}
      {resetting && (
        <ResetModal user={resetting} onClose={() => setResetting(null)} />
      )}
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

/**
 * Minha conta: trocar a própria senha.
 *
 * Exige a senha atual. Não protege contra quem já roubou a sessão — esse já
 * entrou — mas protege contra o caso comum, que é a estação destravada na sala
 * da fazenda com a sessão de alguém aberta.
 */
function MyAccount() {
  const { me } = useAuth()
  const toast = useToast()
  const [atual, setAtual] = useState('')
  const [nova, setNova] = useState('')
  const [confirma, setConfirma] = useState('')

  const trocar = useApiMutation(
    (body: { current_password: string; new_password: string }) =>
      api<{ detail: string }>('/v1/auth/password', { method: 'POST', body }),
    [],
  )

  const divergem = confirma.length > 0 && nova !== confirma
  const podeTrocar = atual.length > 0 && nova.length >= 8 && nova === confirma

  async function salvar() {
    const resposta = await trocar.mutateAsync({ current_password: atual, new_password: nova })
    toast.push({ tone: 'good', title: 'Senha trocada.', detail: resposta.detail })
    setAtual('')
    setNova('')
    setConfirma('')
  }

  return (
    <Card>
      <CardHeader
        title="Minha conta"
        subtitle={me ? `${me.full_name} · ${me.email}` : undefined}
      />
      <div className="max-w-md space-y-3 p-5">
        <ErrorBox error={trocar.error} />
        <FormField label="Senha atual">
          <input
            className="input"
            type="password"
            autoComplete="current-password"
            value={atual}
            onChange={(evento) => setAtual(evento.target.value)}
          />
        </FormField>
        <FormField label="Senha nova" hint="No mínimo 8 caracteres.">
          <input
            className="input"
            type="password"
            autoComplete="new-password"
            value={nova}
            onChange={(evento) => setNova(evento.target.value)}
          />
        </FormField>
        <FormField label="Repita a senha nova">
          <input
            className="input"
            type="password"
            autoComplete="new-password"
            value={confirma}
            onChange={(evento) => setConfirma(evento.target.value)}
          />
        </FormField>
        {divergem && <p className="text-[12px] text-warning">As duas não conferem.</p>}
        <Button disabled={!podeTrocar || trocar.isPending} onClick={salvar}>
          {trocar.isPending ? 'Trocando…' : 'Trocar senha'}
        </Button>
        <p className="text-[12px] text-muted">
          Trocar a senha desconecta os outros aparelhos. Esta sessão continua aberta — veja
          e derrube as demais em <strong>Aparelhos conectados</strong>.
        </p>
      </div>
    </Card>
  )
}

/**
 * Redefinir a senha de outra pessoa.
 *
 * É o caminho de recuperação desta plataforma: não há envio de e-mail, então
 * não há link de redefinição. Quem administra define a senha e a entrega por
 * outro canal — e a ação fica na auditoria com os dois nomes.
 */
function ResetModal({ user, onClose }: { user: UserOut; onClose: () => void }) {
  const toast = useToast()
  const [nova, setNova] = useState('')

  const redefinir = useApiMutation(
    (body: { new_password: string }) =>
      api<{ detail: string }>(`/v1/users/${user.id}/password`, { method: 'POST', body }),
    [],
  )

  return (
    <Modal
      open
      onClose={onClose}
      title={`Redefinir a senha de ${user.full_name}`}
      description="Entregue a senha nova por outro canal. Esta ação fica na auditoria."
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancelar
          </Button>
          <Button
            disabled={nova.length < 8 || redefinir.isPending}
            onClick={async () => {
              const resposta = await redefinir.mutateAsync({ new_password: nova })
              toast.push({ tone: 'good', title: resposta.detail })
              onClose()
            }}
          >
            Redefinir
          </Button>
        </>
      }
    >
      <div className="space-y-3">
        <ErrorBox error={redefinir.error} />
        <FormField label="Senha nova" hint="No mínimo 8 caracteres.">
          <input
            className="input"
            type="text"
            value={nova}
            onChange={(evento) => setNova(evento.target.value)}
          />
        </FormField>
      </div>
    </Modal>
  )
}

/**
 * Os aparelhos com a conta aberta, e o botão para derrubar cada um.
 *
 * A pergunta que esta tela responde é "tem mais alguém dentro da minha conta?".
 * Ela não tinha resposta possível antes — não porque ninguém a fizesse, mas
 * porque não havia onde olhar: o token valia até vencer e nada no servidor
 * podia desdizê-lo.
 */
function MySessions() {
  const toast = useToast()
  const { logout } = useAuth()
  const sessoes = useQuery({
    queryKey: keys.sessions,
    queryFn: () => api<SessionOut[]>('/v1/auth/sessions'),
  })

  const derrubar = useApiMutation(
    (id: string) => api<SessionRevoked>(`/v1/auth/sessions/${id}`, { method: 'DELETE' }),
    [keys.sessions],
  )
  const sairDeTudo = useApiMutation(
    () => api<SessionRevoked>('/v1/auth/logout', { method: 'POST' }),
    [keys.sessions],
  )

  async function encerrar(sessao: SessionOut) {
    const resposta = await derrubar.mutateAsync(sessao.id)
    if (sessao.current) {
      // Derrubar a própria sessão é o logout: a tela precisa acompanhar o
      // servidor, senão a pessoa fica olhando uma página que já não autentica.
      logout()
      return
    }
    toast.push({ tone: 'good', title: 'Aparelho desconectado.', detail: resposta.detail })
  }

  async function encerrarTudo() {
    await sairDeTudo.mutateAsync(undefined as never)
    logout()
  }

  if (sessoes.isLoading) return <Spinner />
  if (sessoes.error) return <ErrorBox error={sessoes.error} />
  const linhas = sessoes.data ?? []

  return (
    <Card>
      <CardHeader
        title="Aparelhos conectados"
        subtitle="Onde sua conta está aberta agora. Não reconhece algum? Derrube e troque a senha."
        actions={
          <Button
            variant="danger"
            disabled={sairDeTudo.isPending}
            onClick={encerrarTudo}
          >
            {sairDeTudo.isPending ? 'Saindo…' : 'Sair de todos'}
          </Button>
        }
      />
      <ErrorBox error={derrubar.error ?? sairDeTudo.error} />
      {linhas.length === 0 ? (
        <Empty title="Nenhuma sessão aberta." />
      ) : (
        <Table>
          <thead>
            <tr>
              <th className={th}>Navegador</th>
              <th className={th}>Endereço</th>
              <th className={th}>Entrou</th>
              <th className={th}>Visto por último</th>
              <th className={th} />
            </tr>
          </thead>
          <tbody>
            {linhas.map((sessao) => (
              <tr key={sessao.id}>
                <td className={td}>
                  {navegador(sessao.user_agent)}
                  {sessao.current && (
                    <Badge tone="good" className="ml-2">
                      este aparelho
                    </Badge>
                  )}
                </td>
                <td className={td}>{sessao.ip_address ?? '—'}</td>
                <td className={td}>{fmt.dateTime(sessao.created_at)}</td>
                <td className={td}>{fmt.dateTime(sessao.last_seen_at)}</td>
                <td className={td}>
                  <Button
                    variant="ghost"
                    disabled={derrubar.isPending}
                    onClick={() => encerrar(sessao)}
                  >
                    {sessao.current ? 'Sair daqui' : 'Desconectar'}
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </Table>
      )}
      <p className="px-5 pb-5 text-[12px] text-muted">
        Derrubar um aparelho corta o acesso dele na hora — não quando a sessão vencer.
      </p>
    </Card>
  )
}

/**
 * O `User-Agent` reduzido ao que deixa alguém se reconhecer na lista.
 *
 * A string inteira tem cem caracteres de versões de motor de renderização que
 * não ajudam ninguém a decidir o que derrubar. "Chrome no Windows" ajuda.
 */
function navegador(agente: string | null | undefined): string {
  if (!agente) return 'Desconhecido'
  const nome =
    /Edg\//.test(agente) ? 'Edge'
    : /OPR\//.test(agente) ? 'Opera'
    : /Chrome\//.test(agente) ? 'Chrome'
    : /Firefox\//.test(agente) ? 'Firefox'
    : /Safari\//.test(agente) ? 'Safari'
    : null
  const sistema =
    /Windows/.test(agente) ? 'Windows'
    : /Android/.test(agente) ? 'Android'
    : /(iPhone|iPad)/.test(agente) ? 'iOS'
    : /Mac OS X/.test(agente) ? 'macOS'
    : /Linux/.test(agente) ? 'Linux'
    : null
  if (!nome && !sistema) return agente.slice(0, 40)
  return [nome, sistema].filter(Boolean).join(' no ')
}
