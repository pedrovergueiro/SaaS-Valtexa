import { ScrollText } from 'lucide-react'
import { useDeferredValue, useState } from 'react'

import { useAudit } from '@/api/queries'
import { useAuth } from '@/auth/AuthProvider'
import { Card, Empty, ErrorBox, PageHeader, Spinner, Table, td, th } from '@/components/ui'
import { fmt } from '@/lib/format'

const SUBJECTS = [
  ['', 'Tudo'],
  ['mission', 'Missões'],
  ['device', 'Dispositivos'],
  ['diagnosis', 'Diagnósticos'],
  ['application', 'Aplicações'],
  ['tank', 'Tanques'],
  ['product', 'Produtos'],
  ['user', 'Pessoas'],
] as const

const ACTOR = { user: 'pessoa', device: 'robô', system: 'sistema' } as Record<string, string>

export default function Audit() {
  const { can } = useAuth()
  const [subject, setSubject] = useState('')
  const [action, setAction] = useState('')
  const deferredAction = useDeferredValue(action.trim())
  const audit = useAudit({ subject_type: subject, action: deferredAction, limit: 400 }, can('audit:read'))

  if (!can('audit:read')) {
    return (
      <Card>
        <Empty title="Seu papel não lê a auditoria" icon={<ScrollText className="size-5" />}>
          Proprietário, administrador e auditor leem. A linha do tempo de cada missão fica aberta a quem opera.
        </Empty>
      </Card>
    )
  }

  return (
    <>
      <PageHeader
        title="Auditoria"
        subtitle="Quem fez o quê, quando e por quê. Imutável: auditoria que pode ser alterada não é auditoria."
      />
      <div className="mb-4 flex flex-wrap gap-3">
        <select className="input w-auto" value={subject} onChange={(event) => setSubject(event.target.value)} aria-label="Assunto">
          {SUBJECTS.map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
        <input
          className="input w-72 font-mono"
          placeholder="ação exata, ex.: mission.approved"
          value={action}
          onChange={(event) => setAction(event.target.value)}
        />
      </div>
      <ErrorBox error={audit.error} className="mb-4" />
      <Card>
        {audit.isLoading && <Spinner />}
        {audit.data?.length === 0 && <Empty title="Nenhum registro com esses filtros" />}
        {(audit.data?.length ?? 0) > 0 && (
          <Table>
            <thead>
              <tr>
                <th className={th}>Quando</th>
                <th className={th}>Quem</th>
                <th className={th}>Ação</th>
                <th className={th}>Sobre</th>
                <th className={th}>Transição</th>
                <th className={th}>Motivo</th>
              </tr>
            </thead>
            <tbody>
              {audit.data?.map((entry) => (
                <tr key={entry.id} className="align-top hover:bg-raised">
                  <td className={`${td} whitespace-nowrap`}>{fmt.dateTime(entry.at)}</td>
                  <td className={td}>
                    <div className="max-w-48 truncate">{entry.actor_label ?? ACTOR[entry.actor_type] ?? entry.actor_type}</div>
                    <div className="text-[12px] text-muted">{ACTOR[entry.actor_type] ?? entry.actor_type}</div>
                  </td>
                  <td className={`${td} font-mono text-[12px]`}>{entry.action}</td>
                  <td className={`${td} num text-[12px] text-ink-2`}>
                    {entry.subject_type} · {fmt.shortId(entry.subject_id)}
                  </td>
                  <td className={`${td} text-[12px]`}>
                    {entry.old_state || entry.new_state ? `${entry.old_state ?? '—'} → ${entry.new_state ?? '—'}` : '—'}
                  </td>
                  <td className={`${td} max-w-md text-[12px] text-ink-2`}>
                    <span className="line-clamp-3">{entry.reason ?? ''}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card>
    </>
  )
}
