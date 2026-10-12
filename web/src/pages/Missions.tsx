import { Plus } from 'lucide-react'
import { useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'

import { useDevices, useFields, useMissions } from '@/api/queries'
import { useAuth } from '@/auth/AuthProvider'
import { NewMissionModal } from '@/components/NewMissionModal'
import { Badge, Button, Card, Empty, ErrorBox, Meter, PageHeader, Spinner, Table, Tabs, td, th } from '@/components/ui'
import { fmt } from '@/lib/format'
import { ACTIVE_MISSION_STATES, missionKind, missionState, missionStateTone } from '@/lib/labels'

type Filter = 'active' | 'attention' | 'done' | 'all'

const FILTERS: Record<Filter, (state: string) => boolean> = {
  active: (state) => ACTIVE_MISSION_STATES.has(state) || state === 'authorized',
  attention: (state) => ['draft', 'pending_safety', 'blocked'].includes(state),
  done: (state) => ['completed', 'aborted', 'expired'].includes(state),
  all: () => true,
}

export default function Missions() {
  const { can } = useAuth()
  const [params, setParams] = useSearchParams()
  const [filter, setFilter] = useState<Filter>('all')
  const missions = useMissions({ limit: 300 })
  const fields = useFields()
  const devices = useDevices()

  const fieldName = useMemo(() => new Map(fields.data?.map((item) => [item.id, item.name])), [fields.data])
  const deviceName = useMemo(() => new Map(devices.data?.map((item) => [item.id, item.name])), [devices.data])

  const rows = missions.data ?? []
  const visible = rows.filter((mission) => FILTERS[filter](mission.state))
  const count = (key: Filter) => rows.filter((mission) => FILTERS[key](mission.state)).length

  return (
    <>
      <PageHeader
        title="Missões"
        subtitle="Planejar, aprovar, autorizar, despachar. A missão é o único contrato de execução: sem assinatura válida, o robô não obedece."
        actions={
          <>
            <Link to="/missoes/comparar">
              <Button>Comparar missões</Button>
            </Link>
            {can('mission:create') && (
              <Button variant="primary" icon={<Plus className="size-4" />} onClick={() => setParams({ nova: '1' })}>
                Nova missão
              </Button>
            )}
          </>
        }
      />

      <div className="mb-4 overflow-x-auto">
        <Tabs<Filter>
          value={filter}
          onChange={setFilter}
          items={[
            { value: 'all', label: 'Todas', count: count('all') },
            { value: 'active', label: 'Em andamento', count: count('active') },
            { value: 'attention', label: 'Pendentes', count: count('attention') },
            { value: 'done', label: 'Encerradas', count: count('done') },
          ]}
        />
      </div>

      <ErrorBox error={missions.error} className="mb-4" />

      <Card>
        {missions.isLoading && <Spinner />}
        {!missions.isLoading && visible.length === 0 && <Empty title="Nenhuma missão neste filtro" />}
        {visible.length > 0 && (
          <Table>
            <thead>
              <tr>
                <th className={th}>Missão</th>
                <th className={th}>Talhão</th>
                <th className={th}>Dispositivo</th>
                <th className={th}>Estado</th>
                <th className={th}>Segurança</th>
                <th className={`${th} w-44`}>Progresso</th>
                <th className={th}>Criada</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((mission) => (
                <tr key={mission.id} className="hover:bg-raised">
                  <td className={td}>
                    <Link to={`/missoes/${mission.id}`} className="font-medium hover:underline">
                      {missionKind(mission.kind)}
                    </Link>
                    <div className="num text-[12px] text-muted">{fmt.shortId(mission.id)}</div>
                  </td>
                  <td className={td}>{fieldName.get(mission.field_id) ?? '—'}</td>
                  <td className={td}>{deviceName.get(mission.device_id) ?? '—'}</td>
                  <td className={td}>
                    <Badge tone={missionStateTone(mission.state)} pulse={mission.state === 'running'}>
                      {missionState(mission.state)}
                    </Badge>
                  </td>
                  <td className={td}>
                    {mission.safety_status === 'safe_to_execute' && <Badge tone="good">Liberada</Badge>}
                    {mission.safety_status === 'blocked' && <Badge tone="critical">Bloqueada</Badge>}
                    {!mission.safety_status && <span className="text-[12px] text-muted">não avaliada</span>}
                  </td>
                  <td className={td}>
                    <div className="flex items-center gap-2">
                      <Meter value={mission.segments_total ? mission.segments_done / mission.segments_total : 0} label="Progresso" />
                      <span className="num w-12 text-right text-[12px] text-muted">
                        {mission.segments_done}/{mission.segments_total}
                      </span>
                    </div>
                  </td>
                  <td className={`${td} whitespace-nowrap text-muted`}>{fmt.ago(mission.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card>

      {params.get('nova') === '1' && (
        <NewMissionModal onClose={() => setParams({})} defaults={{ fieldId: params.get('talhao') ?? undefined }} />
      )}
    </>
  )
}
