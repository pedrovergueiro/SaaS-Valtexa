import { Layers } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { useDevices, useFields, useObservations } from '@/api/queries'
import type { ObservationOut } from '@/api/types'
import { FarmMap, HealthLegend } from '@/components/FarmMap'
import { ObservationModal } from '@/components/ObservationModal'
import { Card, ErrorBox, Tabs } from '@/components/ui'
import { healthClass, type HealthClass } from '@/lib/labels'

type Window = '1' | '7' | '30'

export default function MapPage() {
  const navigate = useNavigate()
  const [days, setDays] = useState<Window>('7')
  const [layers, setLayers] = useState({ fields: true, devices: true, observations: true })
  const [selected, setSelected] = useState<ObservationOut | null>(null)

  const since = useMemo(() => new Date(Date.now() - Number(days) * 86_400_000).toISOString(), [days])
  const fields = useFields()
  const devices = useDevices()
  const observations = useObservations({ since, limit: 2000 }, layers.observations)

  const counts = useMemo(() => {
    const result: Record<HealthClass, number> = { healthy: 0, disease: 0, review: 0 }
    for (const row of observations.data ?? []) result[healthClass(row.label, row.diagnosis_status)] += 1
    return result
  }, [observations.data])

  const toggle = (key: keyof typeof layers) => setLayers((current) => ({ ...current, [key]: !current[key] }))

  return (
    <div className="flex h-[calc(100dvh-8.5rem)] flex-col gap-3 lg:h-[calc(100dvh-6rem)]">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-[22px] font-semibold">Mapa da lavoura</h1>
          <p className="text-[13px] text-ink-2">Clique num talhão para abrir o gêmeo digital; num ponto, para ver a foto.</p>
        </div>
        <Tabs<Window>
          value={days}
          onChange={setDays}
          items={[
            { value: '1', label: '24 h' },
            { value: '7', label: '7 dias' },
            { value: '30', label: '30 dias' },
          ]}
        />
      </div>

      <ErrorBox error={observations.error ?? fields.error} />

      <div className="relative min-h-0 flex-1">
        <FarmMap
          className="size-full"
          fields={layers.fields ? fields.data : []}
          devices={layers.devices ? devices.data : []}
          observations={layers.observations ? observations.data : []}
          onFieldClick={(id) => navigate(`/talhoes/${id}`)}
          onObservationClick={setSelected}
        />

        <Card className="absolute bottom-3 left-3 z-[500] w-[min(88vw,300px)] p-4" as="div">
          <div className="mb-3 flex items-center gap-2 text-[13px] font-medium">
            <Layers className="size-4 text-muted" aria-hidden /> Camadas
          </div>
          <div className="flex flex-col gap-2 text-[13px]">
            {(
              [
                ['fields', 'Talhões'],
                ['devices', 'Frota'],
                ['observations', 'Observações'],
              ] as const
            ).map(([key, label]) => (
              <label key={key} className="flex items-center gap-2">
                <input type="checkbox" checked={layers[key]} onChange={() => toggle(key)} className="accent-[var(--accent)]" />
                {label}
              </label>
            ))}
          </div>
          {layers.observations && (
            <div className="mt-4 border-t border-line-soft pt-3">
              <HealthLegend counts={counts} />
            </div>
          )}
        </Card>
      </div>

      <ObservationModal observation={selected} onClose={() => setSelected(null)} />
    </div>
  )
}
