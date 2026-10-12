import { Layers } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'

import { useDevices, useFields, useMissionComparison, useMissionMap, useMissions, useObservations } from '@/api/queries'
import type { ObservationOut } from '@/api/types'
import { FarmMap, HealthLegend } from '@/components/FarmMap'
import { diseaseColors, MissionLayersMap, toneColors } from '@/components/MissionLayersMap'
import { ObservationModal } from '@/components/ObservationModal'
import { Badge, Card, ErrorBox, Tabs } from '@/components/ui'
import { fmt } from '@/lib/format'
import { disease, healthClass, type HealthClass } from '@/lib/labels'
import {
  CHANGE_LABEL,
  CHANGE_TONE,
  LAYERS,
  layerAvailable,
  PLANT_STATUS_LABEL,
  statusCounts,
  type LayerId,
} from '@/lib/mapLayers'
import { usePalette } from '@/lib/palette'

type Window = '1' | '7' | '30'
type Mode = 'geral' | 'missao'

export default function MapPage() {
  const [params, setParams] = useSearchParams()
  const mode: Mode = params.get('missao') || params.get('modo') === 'missao' ? 'missao' : 'geral'
  const setMode = (m: Mode) => setParams(m === 'missao' ? { modo: 'missao' } : {}, { replace: true })

  return (
    <div className="flex h-[calc(100dvh-8.5rem)] flex-col gap-3 lg:h-[calc(100dvh-6rem)]">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-[22px] font-semibold">Mapa da lavoura</h1>
          <p className="text-[13px] text-ink-2">
            {mode === 'geral'
              ? 'Clique num talhão para abrir o gêmeo digital; num ponto, para ver a foto.'
              : 'Uma missão por vez: plantas, calor, eventos da Edge AI, rota e comparação entre passadas.'}
          </p>
        </div>
        <Tabs<Mode>
          value={mode}
          onChange={setMode}
          items={[
            { value: 'geral', label: 'Visão geral' },
            { value: 'missao', label: 'Por missão' },
          ]}
        />
      </div>
      {mode === 'geral' ? <OverviewMap /> : <MissionMapView />}
    </div>
  )
}

function OverviewMap() {
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
    <>
      <div className="flex justify-end">
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
    </>
  )
}

const PADRAO: LayerId[] = ['incidencia', 'eventos', 'rota']

function MissionMapView() {
  const [params, setParams] = useSearchParams()
  const fields = useFields()
  const missaoParam = params.get('missao') ?? ''
  const baseParam = params.get('base') ?? ''
  const [fieldId, setFieldId] = useState(params.get('talhao') ?? '')
  const scouts = useMissions(fieldId ? { field_id: fieldId, limit: 200 } : { limit: 200 })
  const candidatas = useMemo(
    () => (scouts.data ?? []).filter((m) => (m.kind === 'scout' || m.kind === 'verify') && (!fieldId || m.field_id === fieldId)),
    [scouts.data, fieldId],
  )
  const missaoId = missaoParam || candidatas[0]?.id || ''
  const atual = candidatas.find((m) => m.id === missaoId)
  const anteriores = candidatas.filter((m) => m.id !== missaoId && atual && m.field_id === atual.field_id && m.created_at < atual.created_at)
  const [layers, setLayers] = useState<Set<LayerId>>(() => new Set(PADRAO))

  const mapa = useMissionMap(missaoId || null)
  const comparacao = useMissionComparison(missaoId || null, baseParam || null)
  const palette = usePalette()
  const field = fields.data?.find((f) => f.id === (mapa.data?.field_id ?? atual?.field_id ?? fieldId))
  const temComparacao = Boolean(comparacao.data)

  // ao escolher a missão pelo endereço, o talhão acompanha
  useEffect(() => {
    if (!fieldId && atual?.field_id) setFieldId(atual.field_id)
  }, [atual?.field_id, fieldId])

  const set = (next: Record<string, string>) => {
    const merged: Record<string, string> = { modo: 'missao', missao: missaoId, base: baseParam, talhao: fieldId, ...next }
    setParams(Object.fromEntries(Object.entries(merged).filter(([, v]) => v)), { replace: true })
  }
  const toggle = (id: LayerId) =>
    setLayers((atual) => {
      const novo = new Set(atual)
      if (novo.has(id)) novo.delete(id)
      else novo.add(id)
      return novo
    })

  const contagem = statusCounts(mapa.data?.plants ?? [])
  const porDoenca = diseaseColors(mapa.data, palette)
  const cores = toneColors(palette)

  return (
    <>
      <div className="flex flex-wrap items-center gap-3 text-[13px]">
        <select
          className="input w-52"
          aria-label="Talhão"
          value={fieldId}
          onChange={(e) => {
            setFieldId(e.target.value)
            setParams({ modo: 'missao', ...(e.target.value ? { talhao: e.target.value } : {}) }, { replace: true })
          }}
        >
          <option value="">Todos os talhões</option>
          {fields.data?.map((f) => (
            <option key={f.id} value={f.id}>
              {f.name}
            </option>
          ))}
        </select>
        <select className="input w-64" aria-label="Missão" value={missaoId} onChange={(e) => set({ missao: e.target.value, base: '' })}>
          {!candidatas.length && <option value="">Nenhuma varredura</option>}
          {candidatas.map((m) => (
            <option key={m.id} value={m.id}>
              {fmt.dateTime(m.started_at ?? m.created_at)} · {m.kind === 'verify' ? 'verificação' : 'varredura'} · {fmt.shortId(m.id)}
            </option>
          ))}
        </select>
        <select className="input w-64" aria-label="Comparar com" value={baseParam} onChange={(e) => set({ base: e.target.value })}>
          <option value="">Comparar com… (passada anterior)</option>
          {anteriores.map((m) => (
            <option key={m.id} value={m.id}>
              {fmt.dateTime(m.started_at ?? m.created_at)} · {fmt.shortId(m.id)}
            </option>
          ))}
        </select>
        {missaoId && (
          <Link to={`/missoes/${missaoId}/relatorio`} className="text-accent hover:underline">
            Relatório da missão
          </Link>
        )}
      </div>
      <ErrorBox error={mapa.error ?? scouts.error ?? comparacao.error} />

      <div className="relative min-h-0 flex-1">
        <MissionLayersMap className="size-full" map={mapa.data} field={field} layers={layers} comparison={comparacao.data} />
        <Card className="absolute bottom-3 left-3 z-[500] max-h-[calc(100%-1.5rem)] w-[min(88vw,320px)] overflow-y-auto p-4" as="div">
          <div className="mb-3 flex items-center gap-2 text-[13px] font-medium">
            <Layers className="size-4 text-muted" aria-hidden /> Camadas
          </div>
          <div className="flex flex-col gap-1.5 text-[13px]" data-camadas>
            {LAYERS.map((l) => {
              const ok = layerAvailable(l, temComparacao)
              return (
                <label key={l.id} className={`flex items-start gap-2 ${ok ? '' : 'text-muted'}`} title={ok ? (l.source ?? '') : (l.unavailable ?? 'escolha outra passada para comparar')}>
                  <input
                    type="checkbox"
                    className="mt-0.5 accent-[var(--accent)]"
                    disabled={!ok}
                    checked={ok && layers.has(l.id)}
                    onChange={() => toggle(l.id)}
                  />
                  <span>
                    {l.label}
                    {!ok && <span className="block text-[11px]">{l.source === null ? `sem dado: ${l.unavailable}` : 'escolha a passada para comparar'}</span>}
                  </span>
                </label>
              )
            })}
          </div>
          {mapa.data && (
            <div className="mt-3 border-t border-line-soft pt-3 text-[12px]">
              <div className="mb-1.5 font-medium">
                {mapa.data.plants_seen} planta(s) · incidência {mapa.data.incidence.ratio == null ? '—' : fmt.percent(mapa.data.incidence.ratio, 1)}
              </div>
              {layers.has('comparacao') && comparacao.data ? (
                <div className="flex flex-col gap-1">
                  {(['recuperada', 'persistente', 'nova'] as const).map((c) => (
                    <span key={c} className="flex items-center gap-2">
                      <span className="size-2.5 rounded-full" style={{ background: cores[CHANGE_TONE[c]] }} />
                      {CHANGE_LABEL[c]} ·{' '}
                      {c === 'recuperada' ? comparacao.data.recovered.length : c === 'persistente' ? comparacao.data.persisting.length : comparacao.data.new.length}
                    </span>
                  ))}
                  <span className="text-muted">
                    {fmt.percent(comparacao.data.incidence_before ?? 0, 1)} → {fmt.percent(comparacao.data.incidence_after ?? 0, 1)}
                  </span>
                </div>
              ) : layers.has('doenca') ? (
                <div className="flex flex-col gap-1">
                  {[...porDoenca.entries()].map(([label, cor]) => (
                    <span key={label} className="flex items-center gap-2">
                      <span className="size-2.5 rounded-full" style={{ background: cor }} />
                      {disease(label)}
                    </span>
                  ))}
                  {!porDoenca.size && <span className="text-muted">Nenhuma doença confirmada nesta missão.</span>}
                </div>
              ) : (
                <div className="flex flex-wrap gap-1.5">
                  {(['doente', 'revisar', 'suspeita', 'sadia'] as const).map((s) => (
                    <Badge key={s} tone={s === 'doente' ? 'critical' : s === 'revisar' ? 'warning' : s === 'suspeita' ? 'serious' : 'good'}>
                      {PLANT_STATUS_LABEL[s]} · {contagem[s]}
                    </Badge>
                  ))}
                </div>
              )}
              <div className="mt-2 text-muted">
                {mapa.data.events.length} evento(s) da Edge AI · rota com {mapa.data.track_points_total} posição(ões)
                {mapa.data.plants_without_position ? ` · ${mapa.data.plants_without_position} planta(s) sem posição` : ''}
              </div>
            </div>
          )}
        </Card>
      </div>
    </>
  )
}
