import { Lock, Search, Unlock, Users as UsersIcon } from 'lucide-react'
import { useState } from 'react'

import { Badge, Button, Card, Empty, ErrorBox, FormField, Modal, PageHeader, Spinner, Table, td, th } from '@/components/ui'
import { fmt } from '@/lib/format'
import { role as clientRoleLabel } from '@/lib/labels'
import {
  useGlobalAccounts,
  usePlatformMe,
  useSetAccountActive,
  useSetPlatformRole,
  type GlobalAccount,
  type PlatformRole,
} from '@/platform/api'
import { PLATFORM_ROLES, platformRoleLabel } from '@/platform/labels'

/** Usuários globais: qualquer conta, com os clientes a que pertence (brief, seção 28). */
export default function Users() {
  const [busca, setBusca] = useState('')
  const [soEquipe, setSoEquipe] = useState(false)
  const me = usePlatformMe()
  const contas = useGlobalAccounts({ q: busca.trim(), team_only: soEquipe })
  const mudarPapel = useSetPlatformRole()
  const [bloquear, setBloquear] = useState<GlobalAccount | null>(null)
  const superadmin = new Set(me.data?.capabilities ?? []).has('platform:role:manage')

  return (
    <>
      <PageHeader
        eyebrow="Console da plataforma"
        title="Usuários globais"
        subtitle="Toda conta da plataforma, de cliente ou da equipe. Papel de plataforma e bloqueio só o superadmin muda — e ninguém muda a própria conta."
      />
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <Search className="size-4 text-muted" aria-hidden />
        <input
          className="input w-72"
          placeholder="E-mail ou nome"
          value={busca}
          onChange={(event) => setBusca(event.target.value)}
          aria-label="Buscar usuário"
        />
        <label className="flex items-center gap-2 text-[13px]">
          <input type="checkbox" checked={soEquipe} onChange={(event) => setSoEquipe(event.target.checked)} />
          Só a equipe ValTexa
        </label>
      </div>
      <ErrorBox error={mudarPapel.error} className="mb-3" />
      <Card className="overflow-hidden p-0">
        {contas.isLoading && <Spinner />}
        <ErrorBox error={contas.error} className="m-4" />
        {contas.data && contas.data.length === 0 && (
          <Empty title="Ninguém encontrado" icon={<UsersIcon className="size-5" />}>
            Tente outro termo.
          </Empty>
        )}
        {contas.data && contas.data.length > 0 && (
          <Table>
            <thead>
              <tr>
                <th className={th}>Pessoa</th>
                <th className={th}>Clientes</th>
                <th className={th}>Papel na plataforma</th>
                <th className={th}>Último acesso</th>
                <th className={th} />
              </tr>
            </thead>
            <tbody>
              {contas.data.map((conta) => {
                const propria = conta.id === me.data?.id
                return (
                  <tr key={conta.id}>
                    <td className={td}>
                      <div className="font-medium">{conta.full_name}</div>
                      <div className="text-[12px] text-muted">{conta.email}</div>
                      {!conta.is_active && <Badge tone="critical">Bloqueada</Badge>}
                    </td>
                    <td className={td}>
                      {conta.memberships.length === 0 ? (
                        <span className="text-muted">nenhum</span>
                      ) : (
                        <ul className="text-[12px]">
                          {conta.memberships.map((vinculo) => (
                            <li key={vinculo.tenant_id}>
                              {vinculo.tenant_name} · <span className="text-muted">{clientRoleLabel(vinculo.role)}</span>
                            </li>
                          ))}
                        </ul>
                      )}
                    </td>
                    <td className={td}>
                      {superadmin && !propria ? (
                        <select
                          className="input w-auto"
                          value={conta.platform_role ?? ''}
                          aria-label={`Papel de plataforma de ${conta.email}`}
                          onChange={(event) =>
                            mudarPapel.mutate({
                              userId: conta.id,
                              role: (event.target.value || null) as PlatformRole | null,
                            })
                          }
                        >
                          <option value="">Sem papel de plataforma</option>
                          {PLATFORM_ROLES.map((papel) => (
                            <option key={papel} value={papel}>
                              {platformRoleLabel(papel)}
                            </option>
                          ))}
                        </select>
                      ) : (
                        platformRoleLabel(conta.platform_role)
                      )}
                    </td>
                    <td className={td}>{fmt.ago(conta.last_login_at)}</td>
                    <td className={`${td} text-right`}>
                      {superadmin && !propria && (
                        <Button
                          size="sm"
                          variant={conta.is_active ? 'secondary' : 'ghost'}
                          icon={conta.is_active ? <Lock className="size-4" /> : <Unlock className="size-4" />}
                          onClick={() => setBloquear(conta)}
                        >
                          {conta.is_active ? 'Bloquear' : 'Desbloquear'}
                        </Button>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </Table>
        )}
      </Card>
      {bloquear && <BlockModal conta={bloquear} onClose={() => setBloquear(null)} />}
    </>
  )
}

function BlockModal({ conta, onClose }: { conta: GlobalAccount; onClose: () => void }) {
  const mudar = useSetAccountActive()
  const [motivo, setMotivo] = useState('')
  const bloqueando = conta.is_active
  return (
    <Modal
      open
      onClose={onClose}
      title={bloqueando ? `Bloquear ${conta.email}` : `Desbloquear ${conta.email}`}
      description={
        bloqueando
          ? 'Todas as sessões abertas caem agora. A conta e o histórico dela continuam na auditoria.'
          : 'A pessoa volta a entrar com a senha que já tem.'
      }
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancelar
          </Button>
          <Button
            variant={bloqueando ? 'danger' : 'primary'}
            disabled={motivo.trim().length < 5}
            loading={mudar.isPending}
            onClick={async () => {
              await mudar.mutateAsync({ userId: conta.id, active: !bloqueando, reason: motivo.trim() })
              onClose()
            }}
          >
            {bloqueando ? 'Bloquear' : 'Desbloquear'}
          </Button>
        </>
      }
    >
      <FormField label="Motivo" hint="Vai para a auditoria.">
        <input className="input" value={motivo} onChange={(event) => setMotivo(event.target.value)} />
      </FormField>
      <ErrorBox error={mudar.error} className="mt-3" />
    </Modal>
  )
}
