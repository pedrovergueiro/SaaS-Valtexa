import { ArrowLeft, Box, Plus, TrendingUp } from 'lucide-react'
import { useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { api } from '@/api/client'
import { keys, useAnomalies, useApiMutation, useDecisions, useField, useObservations, useSnapshot, useTimeline, useZones } from '@/api/queries'
import type { DecisionOut, ObservationOut, ZoneOut } from '@/api/types'
import { useAuth } from '@/auth/AuthProvider'
import { DistributionBars, LabelsTimeline } from '@/components/charts'
import { FarmMap, HealthLegend } from '@/components/FarmMap'
import { NewMissionModal, type MissionDefaults } from '@/components/NewMissionModal'
import { ObservationModal } from '@/components/ObservationModal'
import { PolygonDraw } from '@/components/PolygonDraw'
import { Badge, Button, Card, CardHeader, Empty, ErrorBox, FormField, Modal, PageHeader, Spinner, Stat, Tabs } from '@/components/ui'
import { fmt } from '@/lib/format'
import { crop, decisionOutcome, decisionTone, disease, healthClass, type HealthClass } from '@/lib/labels'

type Window = '7' | '30' | '90'

export default function FieldDetail() {
  const { id = '' } = useParams()
  const { can } = useAuth()
  const [days, setDays] = useState<Window>('30')
  const field = useField(id)
  const zones = useZones(id)
  const snapshot = useSnapshot(id, Number(days))
  const timeline = useTimeline(id, Number(days))
  const anomalies = useAnomalies(id)
  const decisions = useDecisions({ field_id: id, limit: 20 })
  const since = useMemo(() => new Date(Date.now() - Number(days) * 86_400_000).toISOString(), [days])
  const observations = useObservations({ field_id: id, since, limit: 2000 })
  const [selected, setSelected] = useState<ObservationOut | null>(null)
  const [mission, setMission] = useState<MissionDefaults | null>(null)
  const [drawingZone, setDrawingZone] = useState(false)

  const counts = useMemo(() => {
    const result: Record<HealthClass, number> = { healthy: 0, disease: 0, review: 0 }
    for (const row of observations.data ?? []) result[healthClass(row.label, row.diagnosis_status)] += 1
    return result
  }, [observations.data])

  if (field.isLoading) return <Spinner />
  if (field.error || !field.data) return <ErrorBox error={field.error ?? new Error('Talhão não encontrado')} />
  const data = field.data
  const snap = snapshot.data

  return (
    <>
      <Link to="/talhoes" className="mb-3 inline-flex items-center gap-1.5 text-[13px] text-muted hover:text-ink">
        <ArrowLeft className="size-4" aria-hidden /> Talhões
      </Link>
      <PageHeader
        eyebrow="Gêmeo digital"
        title={data.name}
        subtitle={`${crop(data.crop)}${data.variety ? ` · ${data.variety}` : ''}${data.crop_stage ? ` · estágio ${data.crop_stage}` : ''} · ${fmt.hectares(data.area_ha)}${data.row_azimuth_deg != null ? ` · linhas a ${fmt.number(data.row_azimuth_deg)}°` : ''}`}
        actions={
          <>
            <Tabs<Window>
              value={days}
              onChange={setDays}
              items={[
                { value: '7', label: '7 dias' },
                { value: '30', label: '30 dias' },
                { value: '90', label: '90 dias' },
              ]}
            />
            <Link to={`/lavoura-3d/${id}`}>
              <Button icon={<Box className="size-4" />}>Cópia 3D</Button>
            </Link>
            {can('mission:create') && (
              <Button variant="primary" icon={<Plus className="size-4" />} onClick={() => setMission({ fieldId: id })}>
                Nova missão
              </Button>
            )}
          </>
        }
      />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Observações" value={<span className="num">{fmt.number(snap?.observations)}</span>} hint={`últimos ${days} dias`} />
        <Stat label="Diagnosticadas" value={<span className="num">{fmt.number(snap?.diagnosed)}</span>} />
        <Stat label="Aguardando agrônomo" value={<span className="num">{fmt.number(snap?.needs_review)}</span>} />
        <Stat
          label="Classe dominante"
          value={<span className="text-[20px]">{snap?.classes[0] ? disease(snap.classes[0].label) : '—'}</span>}
          hint={snap?.classes[0] ? fmt.percent(snap.classes[0].ratio) : undefined}
        />
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-[1.4fr_1fr]">
        <Card className="overflow-hidden">
          <CardHeader
            title="Onde"
            subtitle="Cada ponto é uma foto do rover, com o diagnóstico que vale."
            actions={
              can('farm:manage') && (
                <Button size="sm" onClick={() => setDrawingZone(true)}>
                  Nova zona
                </Button>
              )
            }
          />
          <div className="px-5 pb-5">
            <FarmMap
              fields={[data]}
              zones={zones.data}
              observations={observations.data}
              highlightFieldId={id}
              onObservationClick={setSelected}
              className="h-[26rem]"
            />
            <div className="mt-3">
              <HealthLegend counts={counts} />
            </div>
          </div>
        </Card>

        <div className="flex flex-col gap-4">
          <Card>
            <CardHeader
              title="Desvios do padrão"
              subtitle="A semana contra a linha de base do próprio talhão."
              actions={<TrendingUp className="size-4 text-muted" aria-hidden />}
            />
            <div className="px-5 pb-5">
              {anomalies.data?.length ? (
                <ul className="flex flex-col gap-3">
                  {anomalies.data.map((item) => (
                    <li key={`${item.zone_id}-${item.label}`} className="rounded-[10px] border border-warning/40 bg-warning/10 p-3 text-[13px]">
                      <div className="flex items-center justify-between">
                        <span className="font-medium">{disease(item.label)}</span>
                        <span className="num">
                          {fmt.percent(item.baseline_ratio)} → <strong>{fmt.percent(item.current_ratio)}</strong>
                        </span>
                      </div>
                      <p className="mt-1 text-[12px] text-ink-2">{item.detail}</p>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-[13px] text-ink-2">
                  Nenhum desvio. Esta é a detecção que funciona quando a de novidade falha: uma doença nova classificada
                  como outra conhecida não aparece foto a foto, mas faz a incidência saltar aqui. Precisa de ao menos 30
                  diagnósticos na linha de base.
                </p>
              )}
            </div>
          </Card>

          <Card>
            <CardHeader title="Distribuição" subtitle={`Diagnósticos dos últimos ${days} dias`} />
            <div className="px-5 pb-5">
              {snap?.classes.length ? (
                <DistributionBars data={snap.classes.map((row) => ({ label: row.label, count: row.count }))} />
              ) : (
                <Empty title="Sem diagnósticos na janela" />
              )}
            </div>
          </Card>
        </div>
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-[1.4fr_1fr]">
        <Card>
          <CardHeader title="Evolução" subtitle="Uma foto diz que há ferrugem; a série diz quão rápido ela avança." />
          <div className="px-5 pb-5">
            {timeline.data?.length ? <LabelsTimeline points={timeline.data} /> : <Empty title="Sem série na janela" />}
          </div>
        </Card>

        <Card>
          <CardHeader title="Recomendações" subtitle="Do motor de decisão — recomendação, nunca ordem." />
          {decisions.data?.length === 0 && <Empty title="Nenhuma recomendação" />}
          <ul>
            {decisions.data?.map((decision) => (
              <DecisionRow
                key={decision.id}
                decision={decision}
                canCreate={can('mission:create')}
                onCreate={() =>
                  setMission({
                    kind: 'spray',
                    fieldId: id,
                    zoneId: decision.zone_id ?? undefined,
                    productId: decision.recommended_product_id ?? undefined,
                    rate: decision.recommended_rate_l_ha ?? undefined,
                    decisionId: decision.id,
                  })
                }
              />
            ))}
          </ul>
          {(zones.data?.length ?? 0) > 0 && (
            <div className="border-t border-line-soft px-5 py-4">
              <div className="mb-2 text-[13px] font-medium">Zonas de manejo</div>
              <ul className="flex flex-wrap gap-2">
                {zones.data?.map((zone: ZoneOut) => (
                  <li key={zone.id} className="rounded-full bg-sunken px-3 py-1 text-[12px]">
                    {zone.name} · {fmt.hectares(zone.area_ha)}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </Card>
      </div>

      <ObservationModal observation={selected} onClose={() => setSelected(null)} showFieldLink={false} />
      {mission && <NewMissionModal defaults={mission} onClose={() => setMission(null)} />}
      {drawingZone && <ZoneModal fieldId={id} field={data} zones={zones.data ?? []} onClose={() => setDrawingZone(false)} />}
    </>
  )
}

function DecisionRow({ decision, canCreate, onCreate }: { decision: DecisionOut; canCreate: boolean; onCreate: () => void }) {
  return (
    <li className="border-t border-line-soft px-5 py-3 first:border-0">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Badge tone={decisionTone(decision.outcome)}>{decisionOutcome(decision.outcome)}</Badge>
        <span className="text-[11px] text-muted">
          {fmt.ago(decision.created_at)} · regra {decision.rule_version}
        </span>
      </div>
      <p className="mt-1.5 text-[13px] text-ink-2">{decision.rationale}</p>
      {decision.outcome === 'application_candidate' && canCreate && !decision.mission_id && (
        <Button size="sm" variant="primary" className="mt-2" onClick={onCreate}>
          Criar pulverização a partir desta recomendação
        </Button>
      )}
    </li>
  )
}

function ZoneModal({
  fieldId,
  field,
  zones,
  onClose,
}: {
  fieldId: string
  field: Parameters<typeof PolygonDraw>[0]['fields'] extends (infer T)[] | undefined ? T : never
  zones: ZoneOut[]
  onClose: () => void
}) {
  const [name, setName] = useState('')
  const [boundary, setBoundary] = useState<number[][]>([])
  const create = useApiMutation(
    () => api(`/v1/fields/${fieldId}/zones`, { method: 'POST', body: { name, boundary } }),
    [keys.zones(fieldId)],
  )
  return (
    <Modal
      open
      onClose={onClose}
      wide
      title="Nova zona de manejo"
      description="A zona precisa caber inteira no talhão. É por zona que o motor recomenda — o que separa aplicação localizada de área total."
      footer={
        <>
          <Button onClick={onClose}>Cancelar</Button>
          <Button variant="primary" loading={create.isPending} disabled={!name.trim() || boundary.length < 3} onClick={() => create.mutate(undefined, { onSuccess: onClose })}>
            Salvar zona
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-4">
        <FormField label="Nome">
          <input className="input" value={name} onChange={(event) => setName(event.target.value)} placeholder="Zona Sul" />
        </FormField>
        <PolygonDraw value={boundary} onChange={setBoundary} fields={[field]} zones={zones} highlightFieldId={fieldId} />
        <ErrorBox error={create.error} />
      </div>
    </Modal>
  )
}
