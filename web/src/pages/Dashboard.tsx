import { Bot, BrainCircuit, CloudUpload, Droplets, Map as MapIcon, Plus, Radio, ScanSearch, Sprout, TriangleAlert } from 'lucide-react'
import { Link } from 'react-router-dom'

import { useDashboard, useDevices, useFields } from '@/api/queries'
import type { DashboardOut } from '@/api/types'
import { useAuth } from '@/auth/AuthProvider'
import { DistributionBars } from '@/components/charts'
import { FarmMap } from '@/components/FarmMap'
import { Badge, Button, Card, CardHeader, Empty, ErrorBox, Meter, PageHeader, Skeleton, Stat, Table, td, th } from '@/components/ui'
import { alertLink } from '@/layout/AppShell'
import { fmt } from '@/lib/format'
import { missionKind, missionState, missionStateTone, severity, severityTone } from '@/lib/labels'

export default function Dashboard() {
  const { me, can } = useAuth()
  const board = useDashboard()
  const fields = useFields()
  const devices = useDevices()

  const data = board.data
  const running = data?.missions_by_state.running ?? 0
  const labels = Object.entries(data?.labels_7d ?? {}).map(([label, count]) => ({ label, count }))

  return (
    <>
      <PageHeader
        eyebrow={fmt.dateTime(new Date())}
        title={`Olá, ${me?.full_name.split(' ')[0] ?? ''}`}
        subtitle="O que está acontecendo na lavoura e o que precisa de uma pessoa agora."
        actions={
          can('mission:create') && (
            <Link to="/missoes?nova=1">
              <Button variant="primary" icon={<Plus className="size-4" />}>
                Nova missão
              </Button>
            </Link>
          )
        }
      />

      <ErrorBox error={board.error} className="mb-4" />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        {data ? (
          <>
            <Stat
              label="Frota online"
              value={
                <span className="num">
                  {data.devices.online}
                  <span className="text-[18px] text-muted">/{data.devices.active}</span>
                </span>
              }
              hint={data.devices.low_battery ? `${data.devices.low_battery} com bateria baixa` : 'dispositivos ativos'}
              icon={<Bot className="size-4" />}
            />
            <Stat
              label="Missões em execução"
              value={<span className="num">{running}</span>}
              hint={`${data.missions_by_state.blocked ?? 0} bloqueada(s) pela segurança`}
              icon={<Radio className="size-4" />}
            />
            <Link to="/revisao" className="contents">
              <Stat
                label="Fila do agrônomo"
                value={<span className="num">{data.review_queue}</span>}
                hint="o que a IA não fechou sozinha"
                icon={<ScanSearch className="size-4" />}
              />
            </Link>
            <Stat
              label="Observações · 7 dias"
              value={<span className="num">{fmt.number(data.observations_7d)}</span>}
              hint="imagens da lavoura analisadas"
              icon={<Sprout className="size-4" />}
            />
            <Stat
              label="Aplicado · 30 dias"
              value={<span className="num">{fmt.liters(data.applications_30d.liters)}</span>}
              hint={`${data.applications_30d.count} aplicação(ões) · ${fmt.hectares(data.applications_30d.area_ha)}`}
              icon={<Droplets className="size-4" />}
            />
          </>
        ) : (
          Array.from({ length: 5 }, (_, index) => <Skeleton key={index} className="h-28" />)
        )}
      </div>

      {data?.overview && <Overview overview={data.overview} />}

      <div className="mt-4 grid gap-4 xl:grid-cols-[1fr_1.15fr]">
        <Card>
          <CardHeader
            title="Pede atenção"
            subtitle="Derivado do estado do sistema — some quando a causa é resolvida."
            actions={
              data && (
                <span className="flex gap-1.5">
                  {data.alert_counts.critical ? <Badge tone="critical">{data.alert_counts.critical}</Badge> : null}
                  {data.alert_counts.warning ? <Badge tone="warning">{data.alert_counts.warning}</Badge> : null}
                </span>
              )
            }
          />
          {data && data.alerts.length === 0 && <Empty title="Nada pedindo atenção">Frota em dia, fila vazia, nenhum desvio.</Empty>}
          <ul>
            {data?.alerts.map((alert) => (
              <li key={alert.id} className="border-t border-line-soft">
                <Link to={alertLink(alert)} className="flex items-start gap-3 px-5 py-3 hover:bg-raised">
                  <Badge tone={severityTone(alert.severity)} className="mt-0.5">
                    {severity(alert.severity)}
                  </Badge>
                  <span className="min-w-0 flex-1">
                    <span className="block text-[13px] font-medium">{alert.title}</span>
                    <span className="line-clamp-2 block text-[12px] text-ink-2">{alert.detail}</span>
                  </span>
                  <span className="shrink-0 text-[11px] text-muted">{fmt.ago(alert.at)}</span>
                </Link>
              </li>
            ))}
          </ul>
        </Card>

        <Card className="flex flex-col overflow-hidden">
          <CardHeader
            title="Lavoura e frota"
            subtitle={`${fields.data?.length ?? 0} talhão(ões) · ${devices.data?.length ?? 0} dispositivo(s)`}
            actions={
              <Link to="/mapa">
                <Button size="sm">Abrir mapa</Button>
              </Link>
            }
          />
          <div className="px-5 pb-5">
            <FarmMap fields={fields.data} devices={devices.data} className="h-80" />
          </div>
        </Card>
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-[1fr_1.4fr]">
        <Card>
          <CardHeader title="Diagnósticos · 7 dias" subtitle="Rótulo que vale: o do agrônomo quando existe, senão o da IA." />
          <div className="px-5 pb-5">
            {labels.length ? <DistributionBars data={labels} /> : <Empty title="Sem diagnósticos na semana" />}
          </div>
        </Card>

        <Card>
          <CardHeader
            title="Missões recentes"
            actions={
              <Link to="/missoes">
                <Button size="sm" variant="ghost">
                  Ver todas
                </Button>
              </Link>
            }
          />
          {data && data.recent_missions.length === 0 ? (
            <Empty title="Nenhuma missão ainda" />
          ) : (
            <Table>
              <thead>
                <tr>
                  <th className={th}>Missão</th>
                  <th className={th}>Talhão · dispositivo</th>
                  <th className={th}>Estado</th>
                  <th className={`${th} w-40`}>Progresso</th>
                </tr>
              </thead>
              <tbody>
                {data?.recent_missions.map((mission) => (
                  <tr key={mission.id} className="hover:bg-raised">
                    <td className={td}>
                      <Link to={`/missoes/${mission.id}`} className="font-medium hover:underline">
                        {missionKind(mission.kind)}
                      </Link>
                      <div className="text-[12px] text-muted">{fmt.ago(mission.created_at)}</div>
                    </td>
                    <td className={td}>
                      <div>{mission.field_name ?? '—'}</div>
                      <div className="text-[12px] text-muted">{mission.device_name ?? '—'}</div>
                    </td>
                    <td className={td}>
                      <Badge tone={missionStateTone(mission.state)} pulse={mission.state === 'running'}>
                        {missionState(mission.state)}
                      </Badge>
                    </td>
                    <td className={td}>
                      <div className="flex items-center gap-2">
                        <Meter
                          value={mission.segments_total ? mission.segments_done / mission.segments_total : 0}
                          label="Progresso da missão"
                        />
                        <span className="num w-12 text-right text-[12px] text-muted">
                          {mission.segments_done}/{mission.segments_total}
                        </span>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </Table>
          )}
        </Card>
      </div>
    </>
  )
}

type Overview = NonNullable<DashboardOut['overview']>

const SERVICO: Record<string, { label: string; tone: 'good' | 'critical' | 'warning' | 'neutral' }> = {
  ok: { label: 'IA de nuvem no ar', tone: 'good' },
  fora: { label: 'IA de nuvem fora do ar', tone: 'critical' },
  simulado: { label: 'IA de nuvem simulada', tone: 'warning' },
  desligado: { label: 'IA de nuvem desligada', tone: 'neutral' },
}

/** Seção 45: área, ocorrências, sincronização, saúde da frota e da IA — tudo do backend. */
function Overview({ overview: o }: { overview: Overview }) {
  const saude = o.fleet_health
  const servico = SERVICO[o.ai_health.cloud_service] ?? { label: o.ai_health.cloud_service, tone: 'neutral' as const }
  const atrasados = o.sync.filter((s) => (s.queue_pending ?? 0) > 0 || s.uploads_incomplete > 0)
  return (
    <>
      <div className="mt-3 grid grid-cols-2 gap-3 lg:grid-cols-4" data-painel-visao>
        <Stat
          label="Área"
          value={<span className="num">{fmt.hectares(o.hectares)}</span>}
          hint={`${o.farms} fazenda(s) · ${o.fields} talhão(ões)`}
          icon={<MapIcon className="size-4" />}
        />
        <Stat
          label="Varreduras · 30 dias"
          value={<span className="num">{o.scouts_completed_30d}</span>}
          hint={`${fmt.hectares(o.hectares_scouted_30d)} percorridos`}
          icon={<Radio className="size-4" />}
        />
        <Link to="/mapa?modo=missao" className="contents">
          <Stat
            label="Ocorrências · 7 dias"
            value={<span className="num">{o.occurrences_7d}</span>}
            hint={
              Object.entries(o.occurrences_by_category_7d)
                .map(([k, n]) => `${n} ${k === 'POSSIVEL_DOENCA' ? 'doença' : k === 'POSSIVEL_PRAGA' ? 'praga' : 'anomalia'}`)
                .join(' · ') || 'eventos da Edge AI'
            }
            icon={<TriangleAlert className="size-4" />}
          />
        </Link>
        <Stat
          label="IA · 24 h"
          value={<span className="num">{fmt.number(o.ai_health.edge_results_24h)}</span>}
          hint={`quadros no robô · ${o.ai_health.cloud_inferences_24h} análise(s) na nuvem${o.ai_health.cloud_errors_24h ? ` (${o.ai_health.cloud_errors_24h} com erro)` : ''}`}
          icon={<BrainCircuit className="size-4" />}
        />
      </div>
      <div className="mt-4 grid gap-4 xl:grid-cols-[1fr_1.4fr]">
        <Card>
          <CardHeader title="Saúde da frota e da IA" subtitle="Robô offline há mais de 5 min, com alerta aberto ou em dia." />
          <div className="flex flex-wrap gap-2 px-5 pb-3">
            <Badge tone="good">{saude.ok ?? 0} em dia</Badge>
            <Badge tone={saude.com_alerta ? 'warning' : 'neutral'}>{saude.com_alerta ?? 0} com alerta</Badge>
            <Badge tone={saude.offline ? 'critical' : 'neutral'}>{saude.offline ?? 0} offline</Badge>
            {!!saude.inativo && <Badge tone="neutral">{saude.inativo} inativo(s)</Badge>}
          </div>
          <div className="flex flex-wrap gap-2 px-5 pb-5">
            <Badge tone={servico.tone}>{servico.label}</Badge>
            {o.ai_health.edge_models.map((m) => (
              <Badge key={`${m.model_key}@${m.model_version}`} tone="info">
                {m.model_key}@{m.model_version ?? '?'} · {m.results_24h}
              </Badge>
            ))}
            <Link to="/observabilidade" className="text-[13px] text-accent hover:underline">
              Saúde da frota
            </Link>
          </div>
        </Card>
        <Card className="overflow-hidden">
          <CardHeader
            title="Sincronização"
            subtitle={atrasados.length ? `${atrasados.length} robô(s) com fila ou arquivo pela metade` : 'O que cada robô mandou por último.'}
            actions={<CloudUpload className="size-4 text-muted" aria-hidden />}
          />
          {o.sync.length === 0 ? (
            <Empty title="Nenhum robô ainda" />
          ) : (
            <Table>
              <thead>
                <tr>
                  <th className={th}>Robô</th>
                  <th className={th}>Último registro</th>
                  <th className={th}>Fila</th>
                  <th className={th}>Arquivos pela metade</th>
                </tr>
              </thead>
              <tbody>
                {o.sync.map((s) => (
                  <tr key={s.device_id}>
                    <td className={td}>
                      <Badge tone={s.online ? 'good' : 'neutral'}>{s.online ? 'online' : 'offline'}</Badge>{' '}
                      <Link to={`/frota/${s.device_id}`} className="font-medium hover:underline">
                        {s.name}
                      </Link>
                      {s.open_alerts > 0 && <Badge tone="warning" className="ml-1">{s.open_alerts} alerta(s)</Badge>}
                    </td>
                    <td className={`${td} text-[12px]`}>{s.last_record_received_at ? fmt.ago(s.last_record_received_at) : '—'}</td>
                    <td className={`${td} num`}>
                      {s.queue_pending ?? '—'}
                      {s.queue_oldest_s ? <span className="text-[12px] text-muted"> · mais antigo {fmt.number(s.queue_oldest_s / 60)} min</span> : null}
                    </td>
                    <td className={`${td} num`}>{s.uploads_incomplete}</td>
                  </tr>
                ))}
              </tbody>
            </Table>
          )}
        </Card>
      </div>
    </>
  )
}
