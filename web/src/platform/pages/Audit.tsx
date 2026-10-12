import { ScrollText } from 'lucide-react'
import { useState } from 'react'

import { Badge, Card, Empty, ErrorBox, PageHeader, Spinner, Table, Tabs, td, th } from '@/components/ui'
import { fmt } from '@/lib/format'
import { usePlatformAudit, usePlatformTenants, useSupportSessions } from '@/platform/api'

type Aba = 'trilha' | 'suporte'

/** Auditoria de todos os clientes e as entradas da equipe em cada um (brief, seções 29 e 50). */
export default function PlatformAudit() {
  const [aba, setAba] = useState<Aba>('trilha')
  const [cliente, setCliente] = useState('')
  const [acao, setAcao] = useState('')
  const clientes = usePlatformTenants()
  const nomes = new Map((clientes.data ?? []).map((item) => [item.id, item.name]))

  return (
    <>
      <PageHeader
        eyebrow="Console da plataforma"
        title="Auditoria global"
        subtitle="Quem fez o quê, em qual cliente. Inclui cliente desativado — é depois do contrato que a trilha mais se procura."
      />
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <Tabs
          items={[
            { value: 'trilha', label: 'Trilha' },
            { value: 'suporte', label: 'Entradas em clientes' },
          ]}
          value={aba}
          onChange={setAba}
        />
        <select className="input w-auto" value={cliente} onChange={(event) => setCliente(event.target.value)} aria-label="Cliente">
          <option value="">Todos os clientes</option>
          {(clientes.data ?? []).map((item) => (
            <option key={item.id} value={item.id}>
              {item.name}
            </option>
          ))}
        </select>
        {aba === 'trilha' && (
          <input
            className="input w-56 font-mono"
            placeholder="Ação (prefixo): support."
            value={acao}
            onChange={(event) => setAcao(event.target.value)}
            aria-label="Ação"
          />
        )}
      </div>
      {aba === 'trilha' ? (
        <Trilha cliente={cliente} acao={acao.trim()} nomes={nomes} />
      ) : (
        <Entradas cliente={cliente} />
      )}
    </>
  )
}

function Trilha({ cliente, acao, nomes }: { cliente: string; acao: string; nomes: Map<string, string> }) {
  const trilha = usePlatformAudit({ tenant_id: cliente, action: acao, limit: 300 })
  return (
    <Card className="overflow-hidden p-0">
      {trilha.isLoading && <Spinner />}
      <ErrorBox error={trilha.error} className="m-4" />
      {trilha.data && trilha.data.length === 0 && (
        <Empty title="Nada registrado com este filtro" icon={<ScrollText className="size-5" />} />
      )}
      {trilha.data && trilha.data.length > 0 && (
        <Table>
          <thead>
            <tr>
              <th className={th}>Quando</th>
              <th className={th}>Cliente</th>
              <th className={th}>Quem</th>
              <th className={th}>Ação</th>
              <th className={th}>Detalhe</th>
            </tr>
          </thead>
          <tbody>
            {trilha.data.map((linha) => (
              <tr key={linha.id}>
                <td className={`${td} whitespace-nowrap`}>{fmt.dateTime(linha.at)}</td>
                <td className={td}>{linha.tenant_id ? (nomes.get(linha.tenant_id) ?? fmt.shortId(linha.tenant_id)) : 'plataforma'}</td>
                <td className={td}>
                  {linha.actor_label ?? linha.actor_type}
                  {linha.support_session_id && <Badge tone="info">suporte</Badge>}
                </td>
                <td className={`${td} font-mono text-[12px]`}>{linha.action}</td>
                <td className={`${td} max-w-md text-[12px] text-ink-2`}>
                  {[linha.old_state && `${linha.old_state} →`, linha.new_state, linha.reason].filter(Boolean).join(' ')}
                </td>
              </tr>
            ))}
          </tbody>
        </Table>
      )}
    </Card>
  )
}

function Entradas({ cliente }: { cliente: string }) {
  const sessoes = useSupportSessions({ tenant_id: cliente, limit: 200 })
  return (
    <Card className="overflow-hidden p-0">
      {sessoes.isLoading && <Spinner />}
      <ErrorBox error={sessoes.error} className="m-4" />
      {sessoes.data && sessoes.data.length === 0 && <Empty title="Ninguém da equipe entrou em cliente ainda" />}
      {sessoes.data && sessoes.data.length > 0 && (
        <Table>
          <thead>
            <tr>
              <th className={th}>Início</th>
              <th className={th}>Quem</th>
              <th className={th}>Cliente</th>
              <th className={th}>Modo</th>
              <th className={th}>Motivo</th>
              <th className={th}>Requisições</th>
              <th className={th}>Saída</th>
            </tr>
          </thead>
          <tbody>
            {sessoes.data.map((linha) => (
              <tr key={linha.id}>
                <td className={`${td} whitespace-nowrap`}>{fmt.dateTime(linha.started_at)}</td>
                <td className={td}>{linha.user_email ?? fmt.shortId(linha.user_id)}</td>
                <td className={td}>{linha.tenant_name ?? fmt.shortId(linha.tenant_id)}</td>
                <td className={td}>
                  <Badge tone={linha.mode === 'assistido' ? 'critical' : 'info'}>{linha.mode}</Badge>
                </td>
                <td className={`${td} max-w-sm text-[12px]`}>
                  {linha.reason}
                  {linha.ticket_ref && <span className="text-muted"> · {linha.ticket_ref}</span>}
                </td>
                <td className={`${td} num`}>{linha.request_count}</td>
                <td className={td}>
                  {linha.is_open ? <Badge tone="warning">aberta</Badge> : `${fmt.dateTime(linha.ended_at)} · ${linha.ended_reason ?? ''}`}
                </td>
              </tr>
            ))}
          </tbody>
        </Table>
      )}
    </Card>
  )
}
