import { ArrowLeft, ArrowRight } from 'lucide-react'
import { useMemo } from 'react'
import { Link, useSearchParams } from 'react-router-dom'

import { useFields, useMissionComparison, useMissionMap, useMissions } from '@/api/queries'
import { MissionLayersMap } from '@/components/MissionLayersMap'
import { Badge, Card, CardHeader, Empty, ErrorBox, PageHeader, Spinner, Stat } from '@/components/ui'
import { fmt } from '@/lib/format'
import type { LayerId } from '@/lib/mapLayers'
import { trend } from '@/lib/missionReport'

const ANTES: Set<LayerId> = new Set(['incidencia', 'eventos'])
const DEPOIS: Set<LayerId> = new Set(['comparacao', 'eventos'])

/**
 * Comparação entre duas passadas do mesmo talhão (brief, seções 6 e 46): incidência
 * antes e depois e, planta a planta, quem se recuperou, quem persiste e o que é novo.
 * O cálculo é o de `GET /v1/missions/{id}/comparison`.
 */
export default function MissionCompare() {
  const [params, setParams] = useSearchParams()
  const nova = params.get('nova') ?? ''
  const base = params.get('base') ?? ''
  const fields = useFields()
  const missions = useMissions({ limit: 300 })
  const varreduras = useMemo(
    () => (missions.data ?? []).filter((m) => m.kind === 'scout' || m.kind === 'verify'),
    [missions.data],
  )
  const atual = varreduras.find((m) => m.id === nova)
  const anteriores = varreduras.filter((m) => atual && m.field_id === atual.field_id && m.id !== atual.id && m.created_at < atual.created_at)
  const baseId = base || anteriores[0]?.id || ''
  const comparacao = useMissionComparison(nova || null, baseId || null)
  const mapaAntes = useMissionMap(baseId || null)
  const mapaDepois = useMissionMap(nova || null)
  const field = fields.data?.find((f) => f.id === atual?.field_id)
  const nome = (id: string) => {
    const m = varreduras.find((x) => x.id === id)
    return m ? `${fmt.dateTime(m.started_at ?? m.created_at)} · ${fmt.shortId(m.id)}` : fmt.shortId(id)
  }
  const set = (k: 'nova' | 'base', v: string) => {
    const next = { nova, base: baseId, [k]: v }
    if (k === 'nova') next.base = ''
    setParams(Object.fromEntries(Object.entries(next).filter(([, x]) => x)), { replace: true })
  }
  const c = comparacao.data
  const t = trend(c?.delta ?? null)

  return (
    <>
      <Link to="/missoes" className="mb-3 inline-flex items-center gap-1.5 text-[13px] text-muted hover:text-ink">
        <ArrowLeft className="size-4" aria-hidden /> Missões
      </Link>
      <PageHeader
        title="Comparar missões"
        subtitle={field ? `${field.name} · duas passadas do mesmo talhão` : 'Escolha a passada mais nova e a anterior do mesmo talhão.'}
      />
      <div className="mb-4 flex flex-wrap items-center gap-3 text-[13px]">
        <select className="input w-72" aria-label="Passada anterior" value={baseId} onChange={(e) => set('base', e.target.value)} disabled={!atual}>
          {!anteriores.length && <option value="">Sem passada anterior</option>}
          {anteriores.map((m) => (
            <option key={m.id} value={m.id}>
              {nome(m.id)}
            </option>
          ))}
        </select>
        <ArrowRight className="size-4 text-muted" aria-hidden />
        <select className="input w-72" aria-label="Passada mais nova" value={nova} onChange={(e) => set('nova', e.target.value)}>
          <option value="">Escolha a passada…</option>
          {varreduras.map((m) => (
            <option key={m.id} value={m.id}>
              {fields.data?.find((f) => f.id === m.field_id)?.name ?? 'talhão'} · {nome(m.id)}
            </option>
          ))}
        </select>
      </div>
      <ErrorBox error={comparacao.error ?? missions.error} className="mb-4" />
      {missions.isLoading && <Spinner />}
      {!nova && !missions.isLoading && <Empty title="Escolha a passada mais nova">A anterior do mesmo talhão vem sozinha.</Empty>}
      {nova && !baseId && !missions.isLoading && <Empty title="Este talhão ainda não tem passada anterior" />}

      {c && (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-5" data-comparacao>
            <Stat label="Incidência antes" value={<span className="num">{c.incidence_before == null ? '—' : fmt.percent(c.incidence_before, 1)}</span>} />
            <Stat
              label="Incidência depois"
              value={<span className="num">{c.incidence_after == null ? '—' : fmt.percent(c.incidence_after, 1)}</span>}
              hint={<Badge tone={t.tone}>{t.text}</Badge>}
            />
            <Stat label="Recuperadas" value={<span className="num">{c.recovered.length}</span>} hint={`de ${c.plants_compared} plantas nas duas`} />
            <Stat label="Persistentes" value={<span className="num">{c.persisting.length}</span>} />
            <Stat label="Novas ocorrências" value={<span className="num">{c.new.length}</span>} />
          </div>
          <div className="mt-4 grid gap-4 xl:grid-cols-2">
            <Card className="overflow-hidden">
              <CardHeader title="Antes" subtitle={nome(baseId)} />
              <div className="px-5 pb-5">
                <MissionLayersMap className="h-[420px]" map={mapaAntes.data} field={field} layers={ANTES} />
              </div>
            </Card>
            <Card className="overflow-hidden">
              <CardHeader title="Depois" subtitle={`${nome(nova)} · verde: recuperada, vermelho: persiste, laranja: nova`} />
              <div className="px-5 pb-5">
                <MissionLayersMap className="h-[420px]" map={mapaDepois.data} field={field} layers={DEPOIS} comparison={c} />
              </div>
            </Card>
          </div>
          <Card className="mt-4">
            <CardHeader title="Planta a planta" />
            <div className="grid gap-4 px-5 pb-5 text-[13px] md:grid-cols-3">
              {(
                [
                  ['Recuperadas', c.recovered, 'good'],
                  ['Persistentes', c.persisting, 'critical'],
                  ['Novas', c.new, 'warning'],
                ] as const
              ).map(([titulo, lista, tom]) => (
                <div key={titulo}>
                  <Badge tone={tom}>{titulo}</Badge>
                  <div className="num mt-2 text-ink-2">{lista.join(', ') || '—'}</div>
                </div>
              ))}
            </div>
          </Card>
        </>
      )}
    </>
  )
}
