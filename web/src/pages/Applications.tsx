import { ArrowRight } from 'lucide-react'
import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'

import { api } from '@/api/client'
import { keys, useApiMutation, useApplications, useFields, useObservations, useProducts, useVerifications } from '@/api/queries'
import type { ApplicationOut, VerificationOut } from '@/api/types'
import { useAuth } from '@/auth/AuthProvider'
import { AuthImage } from '@/components/AuthImage'
import { Badge, Button, Card, CardHeader, Empty, ErrorBox, PageHeader, Spinner, Table, Tabs, td, th } from '@/components/ui'
import { fmt } from '@/lib/format'
import { applicationState, disease, verification as verificationLabel, verificationTone } from '@/lib/labels'

type View = 'applications' | 'verifications'

export default function Applications() {
  const [view, setView] = useState<View>('applications')
  const applications = useApplications({ limit: 300 })
  const verifications = useVerifications()
  const fields = useFields()
  const products = useProducts()

  const fieldName = useMemo(() => new Map(fields.data?.map((item) => [item.id, item.name])), [fields.data])
  const productName = useMemo(() => new Map(products.data?.map((item) => [item.id, item.name])), [products.data])
  const byId = useMemo(() => new Map(applications.data?.map((item) => [item.id, item])), [applications.data])

  return (
    <>
      <PageHeader
        title="Aplicações"
        subtitle="O comprovante do produtor e a prova para a fiscalização. E, depois, a pergunta que importa: funcionou?"
      />
      <div className="mb-4">
        <Tabs<View>
          value={view}
          onChange={setView}
          items={[
            { value: 'applications', label: 'Aplicações', count: applications.data?.length },
            { value: 'verifications', label: 'Antes e depois', count: verifications.data?.length },
          ]}
        />
      </div>

      {view === 'applications' ? (
        <Card>
          <ErrorBox error={applications.error} className="m-4" />
          {applications.isLoading && <Spinner />}
          {applications.data?.length === 0 && <Empty title="Nenhuma aplicação registrada">Aparecem aqui quando o drone reporta que abriu o bico.</Empty>}
          {(applications.data?.length ?? 0) > 0 && (
            <Table>
              <thead>
                <tr>
                  <th className={th}>Quando</th>
                  <th className={th}>Talhão</th>
                  <th className={th}>Produto</th>
                  <th className={`${th} text-right`}>Volume</th>
                  <th className={`${th} text-right`}>Área</th>
                  <th className={`${th} text-right`}>Dose</th>
                  <th className={th}>Cerca virtual</th>
                  <th className={th}>Estado</th>
                </tr>
              </thead>
              <tbody>
                {applications.data?.map((item) => (
                  <tr key={item.id} className="hover:bg-raised">
                    <td className={`${td} whitespace-nowrap`}>
                      {fmt.dateTime(item.started_at)}
                      <Link to={`/missoes/${item.mission_id}`} className="num block text-[12px] text-muted hover:underline">
                        missão {fmt.shortId(item.mission_id)}
                      </Link>
                    </td>
                    <td className={td}>{fieldName.get(item.field_id) ?? '—'}</td>
                    <td className={td}>{item.product_id ? productName.get(item.product_id) ?? '—' : '—'}</td>
                    <td className={`${td} num text-right`}>{fmt.liters(item.amount_used_l)}</td>
                    <td className={`${td} num text-right`}>{fmt.hectares(item.area_ha)}</td>
                    <td className={`${td} num text-right`}>{item.mean_rate_l_ha != null ? `${fmt.number(item.mean_rate_l_ha, 2)} L/ha` : '—'}</td>
                    <td className={td}>
                      {item.outside_polygon_points > 0 ? (
                        <Badge tone="critical">{item.outside_polygon_points} ponto(s) fora</Badge>
                      ) : (
                        <Badge tone="good">Dentro da área</Badge>
                      )}
                    </td>
                    <td className={td}>
                      <span className="text-[13px]">{applicationState(item.state)}</span>
                      {item.verified && <span className="block text-[12px] text-muted">verificada</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </Table>
          )}
        </Card>
      ) : (
        <div className="flex flex-col gap-4">
          <ErrorBox error={verifications.error} />
          {verifications.isLoading && <Spinner />}
          {verifications.data?.length === 0 && (
            <Card>
              <Empty title="Nenhuma verificação ainda">
                Cada aplicação agenda uma. Nada é declarado eficaz sem uma segunda passada do rover.
              </Empty>
            </Card>
          )}
          {verifications.data?.map((item) => (
            <VerificationCard
              key={item.id}
              verification={item}
              application={byId.get(item.application_id)}
              fieldName={fieldName.get(item.field_id)}
            />
          ))}
        </div>
      )}
    </>
  )
}

function VerificationCard({
  verification,
  application,
  fieldName,
}: {
  verification: VerificationOut
  application: ApplicationOut | undefined
  fieldName: string | undefined
}) {
  const { can } = useAuth()
  const conclude = useApiMutation(
    () => api(`/v1/verifications/${verification.id}/conclude`, { method: 'POST' }),
    [keys.verifications, ['applications'], keys.alerts],
  )
  const started = application?.started_at
  const stopped = application?.stopped_at ?? started
  const before = useObservations(
    {
      field_id: verification.field_id,
      zone_id: verification.zone_id,
      until: started,
      since: started ? new Date(new Date(started).getTime() - 7 * 86_400_000).toISOString() : undefined,
      limit: 4,
    },
    Boolean(started),
  )
  const after = useObservations(
    { field_id: verification.field_id, zone_id: verification.zone_id, since: stopped, limit: 4 },
    Boolean(stopped),
  )
  const due = verification.scheduled_for ? new Date(verification.scheduled_for).getTime() <= Date.now() : false

  return (
    <Card>
      <CardHeader
        title={`${fieldName ?? 'Talhão'} · aplicação de ${fmt.date(application?.started_at)}`}
        subtitle={
          verification.conclusion === 'pending'
            ? `Segunda passada prevista para ${fmt.dateTime(verification.scheduled_for)} — respeita a reentrada do produto.`
            : verification.notes ?? undefined
        }
        actions={
          <>
            <Badge tone={verificationTone(verification.conclusion)}>{verificationLabel(verification.conclusion)}</Badge>
            {verification.conclusion === 'pending' && can('diagnosis:review') && (
              <Button size="sm" loading={conclude.isPending} disabled={!due} onClick={() => conclude.mutate(undefined)} title={due ? undefined : 'Ainda não chegou a hora'}>
                Fechar comparação
              </Button>
            )}
          </>
        }
      />
      <div className="grid gap-5 px-5 pb-5 lg:grid-cols-[1fr_auto_1fr]">
        <Side title="Antes" ratio={verification.before_ratio} sample={verification.before_sample} rows={before.data ?? []} />
        <div className="hidden items-center lg:flex">
          <ArrowRight className="size-5 text-muted" aria-hidden />
        </div>
        <Side title="Depois" ratio={verification.after_ratio} sample={verification.after_sample} rows={after.data ?? []} />
      </div>
      {verification.effectiveness != null && (
        <div className="border-t border-line-soft px-5 py-3 text-[13px]">
          Eficácia medida: <strong className="num">{fmt.percent(verification.effectiveness)}</strong> de redução relativa da incidência.
        </div>
      )}
      <ErrorBox error={conclude.error} className="mx-5 mb-4" />
    </Card>
  )
}

function Side({
  title,
  ratio,
  sample,
  rows,
}: {
  title: string
  ratio: number | null | undefined
  sample: number | null | undefined
  rows: { id: string; label?: string | null; image_asset_id?: string | null }[]
}) {
  return (
    <div>
      <div className="mb-2 flex items-baseline justify-between">
        <span className="text-[13px] font-medium">{title}</span>
        <span className="num text-[13px]">
          {ratio != null ? <strong>{fmt.percent(ratio)}</strong> : <span className="text-muted">sem medida</span>}
          {sample != null && <span className="text-muted"> · {sample} obs.</span>}
        </span>
      </div>
      <div className="mb-3 h-2 overflow-hidden rounded-full bg-sunken">
        <div className="h-full rounded-full bg-serious" style={{ width: `${Math.min(100, (ratio ?? 0) * 100)}%` }} />
      </div>
      {rows.length ? (
        <div className="grid grid-cols-4 gap-2">
          {rows.map((row) => (
            <figure key={row.id} className="min-w-0">
              <AuthImage
                path={row.image_asset_id ? `/v1/observations/${row.id}/image` : null}
                alt=""
                className="aspect-square w-full rounded-lg"
              />
              <figcaption className="mt-1 truncate text-[11px] text-muted">{disease(row.label)}</figcaption>
            </figure>
          ))}
        </div>
      ) : (
        <p className="text-[12px] text-muted">Sem fotos nesta janela.</p>
      )}
    </div>
  )
}
