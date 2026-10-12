import { Activity } from 'lucide-react'
import { useState } from 'react'

import { AlertsTable, FleetHealthTable, RulesTable } from '@/components/Observability'
import { Badge, Card, CardHeader, Empty, ErrorBox, PageHeader, Spinner, Stat, Table, Tabs, td, th } from '@/components/ui'
import { fmt } from '@/lib/format'
import {
  classShares,
  componentLabel,
  componentStatusLabel,
  componentTone,
  deliveryLabel,
  driftTone,
  ms,
  pct,
  seconds,
  useAiObservability,
  useAlertRules,
  useApiStats,
  useFleetHealth,
  useObsAlerts,
  useObsOverview,
  type AiModelStat,
} from '@/lib/observability'
import { usePlatformMe, usePlatformTenants } from '@/platform/api'

type Aba = 'geral' | 'api' | 'frota' | 'ia' | 'alertas' | 'regras'

/**
 * Observabilidade do console interno (Parte 7, brief seções 34 e 35).
 *
 * Saúde por componente (banco, API, worker, IA, frota, alertas), a API por rota,
 * filas, usuários ativos, a saúde de cada robô de todos os clientes, a IA por modelo
 * (inferências, erros, latência, classes e drift) e os alertas com as regras. Tudo
 * vem de `/v1/platform/observability/**` — os mesmos números que o `/metrics` dá
 * ao Prometheus.
 */
export default function PlatformObservability() {
  const [aba, setAba] = useState<Aba>('geral')
  const geral = useObsOverview()
  const me = usePlatformMe()
  const gerencia = (me.data?.capabilities ?? []).includes('platform:alert:manage')
  return (
    <>
      <PageHeader
        eyebrow="Console da plataforma"
        title="Observabilidade"
        subtitle="Saúde da plataforma, da IA e dos robôs, com alertas. Atualiza a cada 30 s."
      />
      <div className="mb-4">
        <Tabs<Aba>
          value={aba}
          onChange={setAba}
          items={[
            { value: 'geral', label: 'Visão geral' },
            { value: 'api', label: 'API' },
            { value: 'frota', label: 'Robôs' },
            { value: 'ia', label: 'IA' },
            { value: 'alertas', label: 'Alertas', count: geral.data?.alerts_open },
            { value: 'regras', label: 'Regras' },
          ]}
        />
      </div>
      {aba === 'geral' && <Geral />}
      {aba === 'api' && <Api />}
      {aba === 'frota' && <Frota />}
      {aba === 'ia' && <Ia />}
      {aba === 'alertas' && <Alertas gerencia={gerencia} />}
      {aba === 'regras' && <Regras gerencia={gerencia} />}
    </>
  )
}

function Geral() {
  const q = useObsOverview()
  const d = q.data
  return (
    <>
      <ErrorBox error={q.error} className="mb-4" />
      {q.isLoading && <Spinner />}
      {d && (
        <>
          <div className="mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {d.components.map((c) => (
              <div key={c.component} className="card flex items-start justify-between gap-3 p-4" data-componente={c.component}>
                <div>
                  <div className="text-[13px] font-medium">{componentLabel(c.component)}</div>
                  <div className="mt-1 text-[12px] text-ink-2">{c.detail}</div>
                </div>
                <Badge tone={componentTone(c.status)} pulse={c.status === 'falha'}>
                  {componentStatusLabel(c.status)}
                </Badge>
              </div>
            ))}
          </div>
          <div className="mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Stat label="Requisições (60 min)" value={fmt.number(d.api.requests)} hint={`${d.api.server_errors} com erro 5xx`} />
            <Stat label="Latência p95 da API" value={ms(d.api.latency_ms_p95)} hint={`média ${ms(d.api.latency_ms_avg)}`} />
            <Stat
              label="Usuários ativos"
              value={fmt.number(d.users.active_15m)}
              hint={`${fmt.number(d.users.active_24h)} nas últimas 24 h`}
            />
            <Stat
              label="Alertas abertos"
              value={fmt.number(d.alerts_open)}
              hint={`${d.alerts_critical} crítico(s)`}
              tone={d.alerts_critical ? 'critical' : undefined}
            />
          </div>
          <Card>
            <CardHeader title="Filas" subtitle="Eventos de domínio (outbox), trabalhos pesados e entregas de aviso por e-mail." />
            <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-2 px-5 pb-5 text-[13px]">
              <dt className="text-muted">Eventos pendentes</dt>
              <dd className="num">
                {d.queues.outbox_pending}
                {d.queues.outbox_oldest_pending_s != null && ` · o mais antigo há ${seconds(d.queues.outbox_oldest_pending_s)}`}
                {d.queues.outbox_with_error > 0 && ` · ${d.queues.outbox_with_error} com erro`}
              </dd>
              <dt className="text-muted">Trabalhos</dt>
              <dd className="num">
                {d.queues.jobs_queued} na fila · {d.queues.jobs_running} rodando · {d.queues.jobs_failed_24h} falha(s) em 24 h
                {d.queues.jobs_oldest_queued_s != null && ` · o mais antigo há ${seconds(d.queues.jobs_oldest_queued_s)}`}
              </dd>
              <dt className="text-muted">Entregas de aviso</dt>
              <dd className="num">
                {Object.entries(d.queues.deliveries)
                  .map(([k, v]) => `${v} ${deliveryLabel(k)}`)
                  .join(' · ') || 'nenhuma'}
              </dd>
              <dt className="text-muted">Serviço de IA</dt>
              <dd>
                {d.ai_service.status}
                {d.ai_service.detail ? ` — ${d.ai_service.detail}` : ''}
              </dd>
            </dl>
          </Card>
        </>
      )}
    </>
  )
}

function Api() {
  const [minutos, setMinutos] = useState(60)
  const q = useApiStats(minutos)
  const rotas = q.data?.routes ?? []
  return (
    <Card className="overflow-hidden p-0">
      <CardHeader
        title="API por rota"
        subtitle="Rota pelo molde (com {parâmetros}); p50/p95 aproximados pelos baldes do histograma, somando todas as réplicas."
        actions={
          <select className="input w-40" value={minutos} onChange={(e) => setMinutos(Number(e.target.value))} aria-label="Janela">
            <option value={15}>15 min</option>
            <option value={60}>1 hora</option>
            <option value={360}>6 horas</option>
            <option value={1440}>24 horas</option>
          </select>
        }
      />
      <ErrorBox error={q.error} className="m-4" />
      {q.isLoading && <Spinner />}
      {q.data && rotas.length === 0 && <Empty title="Nenhuma requisição na janela" />}
      {rotas.length > 0 && (
        <Table>
          <thead>
            <tr>
              <th className={th}>Rota</th>
              <th className={th}>Requisições</th>
              <th className={th}>5xx</th>
              <th className={th}>4xx</th>
              <th className={th}>p50</th>
              <th className={th}>p95</th>
              <th className={th}>máx.</th>
            </tr>
          </thead>
          <tbody>
            {rotas.map((r) => (
              <tr key={`${r.method} ${r.route}`}>
                <td className={`${td} num text-[12px]`}>
                  <span className="text-muted">{r.method}</span> {r.route}
                </td>
                <td className={`${td} num`}>{fmt.number(r.requests)}</td>
                <td className={`${td} num`}>
                  {r.server_errors ? <Badge tone="critical">{r.server_errors} ({pct((r.error_rate ?? 0) * 100, 1)})</Badge> : 0}
                </td>
                <td className={`${td} num`}>{r.client_errors}</td>
                <td className={`${td} num`}>{ms(r.latency_ms_p50)}</td>
                <td className={`${td} num`}>{ms(r.latency_ms_p95)}</td>
                <td className={`${td} num`}>{ms(r.latency_ms_max)}</td>
              </tr>
            ))}
          </tbody>
        </Table>
      )}
    </Card>
  )
}

function Frota() {
  const [cliente, setCliente] = useState('')
  const clientes = usePlatformTenants()
  const q = useFleetHealth('plataforma', cliente ? { tenant_id: cliente } : undefined)
  return (
    <>
      <div className="mb-4">
        <select className="input w-56" value={cliente} onChange={(e) => setCliente(e.target.value)} aria-label="Cliente">
          <option value="">Todos os clientes</option>
          {clientes.data?.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
      </div>
      <Card className="overflow-hidden p-0">
        <ErrorBox error={q.error} className="m-4" />
        {q.isLoading && <Spinner />}
        {q.data && <FleetHealthTable rovers={q.data} showTenant />}
      </Card>
    </>
  )
}

function Modelo({ m }: { m: AiModelStat }) {
  const classes = classShares(m.classes)
  return (
    <tr>
      <td className={td}>
        <div className="font-medium">{m.model_key}</div>
        <div className="num text-[12px] text-muted">
          {m.source} · {m.model_version}
          {m.simulated && ' · simulado'}
        </div>
      </td>
      <td className={`${td} num`}>{fmt.number(m.inferences)}</td>
      <td className={`${td} num`}>{m.errors == null ? '—' : `${m.errors} (${pct((m.error_rate ?? 0) * 100, 1)})`}</td>
      <td className={`${td} num`}>{m.source === 'nuvem' ? ms(m.latency_ms_p95) : '—'}</td>
      <td className={`${td} text-[12px]`}>
        {classes.slice(0, 5).map((c) => (
          <div key={c.label} className="num">
            {c.label}: {fmt.percent(c.share)} ({c.count})
          </div>
        ))}
      </td>
    </tr>
  )
}

function Ia() {
  const [horas, setHoras] = useState(24)
  const q = useAiObservability(horas)
  const d = q.data
  const modelos = [...(d?.cloud ?? []), ...(d?.edge ?? [])]
  return (
    <>
      <ErrorBox error={q.error} className="mb-4" />
      {q.isLoading && <Spinner />}
      {d && (
        <>
          <Card className="mb-4 overflow-hidden p-0">
            <CardHeader
              title="Inferências por modelo"
              subtitle={`Serviço de IA: ${d.service.status}${d.service.detail ? ` — ${d.service.detail}` : ''}. Nuvem = diagnósticos gravados; borda = resultados da Edge AI que subiram.`}
              actions={
                <select className="input w-36" value={horas} onChange={(e) => setHoras(Number(e.target.value))} aria-label="Janela">
                  <option value={1}>1 hora</option>
                  <option value={24}>24 horas</option>
                  <option value={168}>7 dias</option>
                </select>
              }
            />
            {modelos.length === 0 ? (
              <Empty title="Nenhuma inferência na janela" icon={<Activity className="size-5" />} />
            ) : (
              <Table>
                <thead>
                  <tr>
                    <th className={th}>Modelo</th>
                    <th className={th}>Inferências</th>
                    <th className={th}>Erros</th>
                    <th className={th}>p95</th>
                    <th className={th}>Classes</th>
                  </tr>
                </thead>
                <tbody>
                  {modelos.map((m) => (
                    <Modelo key={`${m.source}-${m.model_key}-${m.model_version}`} m={m} />
                  ))}
                </tbody>
              </Table>
            )}
          </Card>
          <Card className="overflow-hidden p-0">
            <CardHeader title="Drift da distribuição de classes" subtitle={d.drift_note} />
            {d.drift.length === 0 ? (
              <Empty title="Sem previsões para comparar" />
            ) : (
              <Table>
                <thead>
                  <tr>
                    <th className={th}>Modelo</th>
                    <th className={th}>Distância</th>
                    <th className={th}>Recente</th>
                    <th className={th}>Base (7 dias antes)</th>
                  </tr>
                </thead>
                <tbody>
                  {d.drift.map((x) => (
                    <tr key={`${x.source}-${x.model_key}`}>
                      <td className={td}>
                        {x.model_key} <span className="text-[12px] text-muted">({x.source})</span>
                      </td>
                      <td className={td}>
                        {x.distance == null ? (
                          <span className="text-[12px] text-muted">{x.reason}</span>
                        ) : (
                          <Badge tone={driftTone(x.distance)}>{fmt.number(x.distance, 2)}</Badge>
                        )}
                      </td>
                      <td className={`${td} num text-[12px]`}>
                        {x.recent} · {classShares(x.recent_classes).slice(0, 3).map((c) => `${c.label} ${fmt.percent(c.share)}`).join(', ')}
                      </td>
                      <td className={`${td} num text-[12px]`}>
                        {x.baseline} · {classShares(x.baseline_classes).slice(0, 3).map((c) => `${c.label} ${fmt.percent(c.share)}`).join(', ')}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            )}
          </Card>
        </>
      )}
    </>
  )
}

function Alertas({ gerencia }: { gerencia: boolean }) {
  const [abertos, setAbertos] = useState(true)
  const q = useObsAlerts('plataforma', abertos ? { open_only: true } : undefined)
  return (
    <>
      <label className="mb-4 flex items-center gap-2 text-[13px]">
        <input type="checkbox" checked={abertos} onChange={(e) => setAbertos(e.target.checked)} /> Só os abertos
      </label>
      <Card className="overflow-hidden p-0">
        <ErrorBox error={q.error} className="m-4" />
        {q.isLoading && <Spinner />}
        {q.data && <AlertsTable alerts={q.data} scope="plataforma" canAck={gerencia} showTenant />}
      </Card>
    </>
  )
}

function Regras({ gerencia }: { gerencia: boolean }) {
  const q = useAlertRules('plataforma')
  return (
    <Card className="overflow-hidden p-0">
      <CardHeader
        title="Regras de alerta"
        subtitle="Avaliadas pelo worker a cada minuto. As de robô podem ter versão própria em cada cliente; o aviso sai pelas notificações."
      />
      <ErrorBox error={q.error} className="m-4" />
      {q.isLoading && <Spinner />}
      {q.data && <RulesTable rules={q.data} scope="plataforma" canEdit={gerencia} />}
    </Card>
  )
}
