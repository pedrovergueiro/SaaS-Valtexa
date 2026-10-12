import { Bot } from 'lucide-react'
import { useState } from 'react'

import { Badge, Card, Empty, ErrorBox, PageHeader, Spinner, Table, td, th } from '@/components/ui'
import { FLEET_STATES, faultText, fleetStateLabel, fleetStateTone, modelInUse, modelStatus, storageText, storageTone } from '@/lib/fleet'
import { fmt } from '@/lib/format'
import { FleetSummaryRow } from '@/pages/Fleet'
import { usePlatformFleet, usePlatformTenants } from '@/platform/api'

/**
 * Frota de todos os clientes (Operações; brief, seções 25, 26 e 34).
 *
 * O estado de cada robô vem do servidor, derivado do protocolo; aqui só se
 * filtra. "Modelo diferente do designado" compara o que o robô diz rodar com a
 * versão em PRODUÇÃO que o registry designa para os talhões dele.
 */
export default function PlatformFleet() {
  const [cliente, setCliente] = useState('')
  const [estado, setEstado] = useState('')
  const [divergentes, setDivergentes] = useState(false)
  const clientes = usePlatformTenants()
  const frota = usePlatformFleet({
    tenant_id: cliente || undefined,
    fleet_state: estado || undefined,
    model_divergent: divergentes || undefined,
  })
  const linhas = frota.data ?? []

  return (
    <>
      <PageHeader
        eyebrow="Console da plataforma"
        title="Frota"
        subtitle="Todos os robôs de todos os clientes. O estado é o que o protocolo diz (contato, missão, sincronização, falhas), nunca digitado. Atualiza a cada 30 s."
      />
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <select className="input w-56" value={cliente} onChange={(e) => setCliente(e.target.value)} aria-label="Cliente">
          <option value="">Todos os clientes</option>
          {clientes.data?.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
        <select className="input w-48" value={estado} onChange={(e) => setEstado(e.target.value)} aria-label="Estado">
          <option value="">Todos os estados</option>
          {FLEET_STATES.map((s) => (
            <option key={s} value={s}>
              {fleetStateLabel(s)}
            </option>
          ))}
        </select>
        <label className="flex items-center gap-2 text-[13px]">
          <input type="checkbox" checked={divergentes} onChange={(e) => setDivergentes(e.target.checked)} />
          Só com modelo diferente do designado
        </label>
      </div>

      {linhas.length > 0 && <FleetSummaryRow devices={linhas} />}

      <Card className="overflow-hidden p-0">
        {frota.isLoading && <Spinner />}
        <ErrorBox error={frota.error} className="m-4" />
        {frota.data && linhas.length === 0 && (
          <Empty title="Nenhum robô com esse filtro" icon={<Bot className="size-5" />}>
            {divergentes ? 'Todos os robôs que informaram o modelo estão com o designado.' : 'Ajuste os filtros acima.'}
          </Empty>
        )}
        {linhas.length > 0 && (
          <Table>
            <thead>
              <tr>
                <th className={th}>Robô</th>
                <th className={th}>Cliente</th>
                <th className={th}>Estado</th>
                <th className={th}>Software e modelo</th>
                <th className={th}>Saúde</th>
                <th className={th}>Contato</th>
              </tr>
            </thead>
            <tbody>
              {linhas.map((d) => {
                const situacao = modelStatus(d.model_status)
                const falhas = d.active_faults ?? []
                return (
                  <tr key={d.id}>
                    <td className={td}>
                      <div className="font-medium">{d.name}</div>
                      <div className="num text-[12px] text-muted">
                        {d.model_code} · {d.serial_number}
                      </div>
                    </td>
                    <td className={td}>{d.tenant_name}</td>
                    <td className={td}>
                      <Badge tone={fleetStateTone(d.fleet_state)}>{d.fleet_state_label}</Badge>
                      <div className="mt-1 max-w-64 text-[12px] text-ink-2">{d.fleet_state_reason}</div>
                      {falhas.length > 0 && (
                        <div className="text-[12px] text-serious">{falhas.slice(0, 2).map(faultText).join('; ')}</div>
                      )}
                    </td>
                    <td className={td}>
                      <div className="num text-[12px]">IA {modelInUse(d.ai_model_key, d.ai_model_version)}</div>
                      <Badge tone={situacao.tone}>{situacao.label}</Badge>
                      <div className="num mt-1 text-[12px] text-muted">
                        runtime {d.runtime_version ?? 'sem dado'} · edge {d.edge_ai_version ?? 'sem dado'} · dNATY{' '}
                        {d.dnaty_version ?? 'sem dado'}
                      </div>
                    </td>
                    <td className={`${td} text-[12px]`}>
                      <div className="num">bateria {d.battery_percent != null ? `${fmt.number(d.battery_percent)}%` : 'sem dado'}</div>
                      <div className="num">
                        temperatura {d.temperature_c != null ? `${fmt.number(d.temperature_c, 1)} °C` : 'sem dado'}
                      </div>
                      <Badge tone={storageTone(d.storage_total_bytes, d.storage_free_bytes)}>
                        {storageText(d.storage_total_bytes, d.storage_free_bytes)}
                      </Badge>
                      <div className="num">{d.operating_hours != null ? `${fmt.number(d.operating_hours, 1)} h de operação` : 'horímetro sem dado'}</div>
                    </td>
                    <td className={`${td} text-[12px]`}>
                      <div>visto {fmt.ago(d.last_seen_at)}</div>
                      <div className="text-muted">sincronizou {d.last_sync_at ? fmt.ago(d.last_sync_at) : 'sem dado'}</div>
                      {d.active_mission_id && <div className="text-accent">missão {fmt.shortId(d.active_mission_id)}</div>}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </Table>
        )}
      </Card>
    </>
  )
}
