import { AlertTriangle, Building2, LogIn, Search } from 'lucide-react'
import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'

import { Badge, Card, Empty, ErrorBox, PageHeader, Spinner, Table, td, th } from '@/components/ui'
import { Button } from '@/components/ui'
import { fmt } from '@/lib/format'
import { usePlatformMe, usePlatformTenants, type PlatformTenant } from '@/platform/api'
import { EnterAsClient } from '@/platform/EnterAsClient'
import { subscriptionLabel } from '@/platform/labels'

function ConsentBadge({ consent }: { consent: PlatformTenant['consent'] }) {
  if (!consent.decided) return <Badge tone="neutral">Não respondeu (NÃO)</Badge>
  return consent.allowed ? (
    <Badge tone="good">SIM · {fmt.date(consent.decided_at)}</Badge>
  ) : (
    <Badge tone="warning">NÃO · {fmt.date(consent.decided_at)}</Badge>
  )
}

function statusTone(status: string | null | undefined) {
  if (status === 'ativa') return 'good' as const
  if (status === 'teste') return 'info' as const
  if (status === 'suspensa' || status === 'cancelada') return 'critical' as const
  return 'neutral' as const
}

/** Clientes com plano, assinatura, uso e consentimento (brief, seções 28, 31 e 32). */
export default function Clients() {
  const [busca, setBusca] = useState('')
  const [params] = useSearchParams()
  const destacado = params.get('aberto')
  const me = usePlatformMe()
  const lista = usePlatformTenants(busca.trim())
  const [entrarEm, setEntrarEm] = useState<PlatformTenant | null>(null)
  const caps = new Set(me.data?.capabilities ?? [])
  const podeEntrar = caps.has('platform:support:session')

  return (
    <>
      <PageHeader
        eyebrow="Console da plataforma"
        title="Clientes"
        subtitle="Plano, assinatura, uso contra os limites e consentimento de dados de cada cliente. Sem dado agronômico: para ver a lavoura, entre como cliente."
      />
      <div className="mb-4 flex items-center gap-2">
        <Search className="size-4 text-muted" aria-hidden />
        <input
          className="input w-72"
          placeholder="Buscar por nome ou apelido"
          value={busca}
          onChange={(event) => setBusca(event.target.value)}
          aria-label="Buscar cliente"
        />
      </div>
      <Card className="overflow-hidden p-0">
        {lista.isLoading && <Spinner />}
        <ErrorBox error={lista.error} className="m-4" />
        {lista.data && lista.data.length === 0 && (
          <Empty title="Nenhum cliente encontrado" icon={<Building2 className="size-5" />}>
            {busca ? 'Tente outro termo.' : 'Cadastre o primeiro em “Cadastro e contrato”.'}
          </Empty>
        )}
        {lista.data && lista.data.length > 0 && (
          <Table>
            <thead>
              <tr>
                <th className={th}>Cliente</th>
                <th className={th}>Plano</th>
                <th className={th}>Uso</th>
                <th className={th}>Dados no treino</th>
                <th className={th}>Pessoas</th>
                <th className={th} />
              </tr>
            </thead>
            <tbody>
              {lista.data.map((cliente) => (
                <tr key={cliente.id} className={cliente.id === destacado ? 'bg-accent-soft' : undefined}>
                  <td className={td}>
                    <div className="font-medium">{cliente.name}</div>
                    <div className="text-[12px] text-muted">
                      {cliente.slug}
                      {cliente.city ? ` · ${cliente.city}${cliente.state ? `/${cliente.state}` : ''}` : ''}
                      {!cliente.is_active && ' · desativado'}
                    </div>
                  </td>
                  <td className={td}>
                    <div>{cliente.plan_name ?? '—'}</div>
                    <Badge tone={statusTone(cliente.subscription_status)}>
                      {subscriptionLabel(cliente.subscription_status)}
                    </Badge>
                    {cliente.subscription_ends_at && (
                      <div className="text-[12px] text-muted">até {fmt.date(cliente.subscription_ends_at)}</div>
                    )}
                  </td>
                  <td className={td}>
                    {(cliente.usage ?? []).length === 0 ? (
                      <span className="text-muted">—</span>
                    ) : (
                      <ul className="flex flex-col gap-0.5 text-[12px]">
                        {(cliente.usage ?? [])
                          .filter((item) => item.limit !== null || item.used > 0)
                          .slice(0, 4)
                          .map((item) => (
                            <li key={item.resource}>
                              <span className="num">{fmt.number(item.used, item.used % 1 ? 1 : 0)}</span>
                              {item.limit !== null && <span className="text-muted"> / {fmt.number(item.limit)}</span>}{' '}
                              {item.label}
                            </li>
                          ))}
                      </ul>
                    )}
                    {(cliente.warnings ?? []).length > 0 && (
                      <div className="mt-1 flex items-center gap-1 text-[12px] text-serious">
                        <AlertTriangle className="size-3.5" aria-hidden />
                        perto do limite: {(cliente.warnings ?? []).join(', ')}
                      </div>
                    )}
                  </td>
                  <td className={td}>
                    <ConsentBadge consent={cliente.consent} />
                  </td>
                  <td className={td}>
                    <span className="num">{cliente.members}</span>
                    {cliente.open_support_sessions > 0 && (
                      <div className="text-[12px] text-info">{cliente.open_support_sessions} suporte(s) dentro agora</div>
                    )}
                  </td>
                  <td className={`${td} text-right`}>
                    {podeEntrar && (
                      <Button size="sm" icon={<LogIn className="size-4" />} onClick={() => setEntrarEm(cliente)}>
                        Entrar como cliente
                      </Button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card>
      {entrarEm && (
        <EnterAsClient
          tenant={entrarEm}
          canAssist={caps.has('platform:support:assist')}
          onClose={() => setEntrarEm(null)}
        />
      )}
    </>
  )
}
