/**
 * A IA do talhão: qual versão do modelo diagnostica, e o que ela viu planta a planta.
 *
 * As plantas e a prevalência vêm da fusão por planta do serviço de inferência —
 * o SaaS só repassa. Quando a inferência não guarda talhões, a rota responde
 * 503 e a tela diz o que falta configurar, em vez de mostrar "vazio".
 */
import { Check, Sprout } from 'lucide-react'
import { useMemo, useState } from 'react'

import { ApiError } from '@/api/client'
import { useFieldAiModels, useFieldPlants, useFieldPrevalence, useSetFieldAiModel } from '@/api/queries'
import type { AiModelChoiceOut, PlantIncidenceOut, PlantOut } from '@/api/types'
import { Badge, Button, Card, CardHeader, Empty, ErrorBox, Meter, Spinner, Table, td, th } from '@/components/ui'
import { cn } from '@/lib/cn'
import { fmt } from '@/lib/format'
import { disease, modelVariant, PLANT_STATUSES, plantStatus, plantStatusTone, plantZone } from '@/lib/labels'

/** Pior primeiro: é a ordem em que alguém vai ao campo conferir. */
const STATUS_ORDER: Record<string, number> = { doente: 0, suspeita: 1, revisar: 2, sadia: 3 }
const PLANTS_PREVIEW = 12

// --- versão do modelo ---------------------------------------------------------------

export function AiModelCard({ fieldId, canManage }: { fieldId: string; canManage: boolean }) {
  const choices = useFieldAiModels(fieldId)
  const change = useSetFieldAiModel(fieldId)

  if (choices.isLoading) return <Card className="p-5"><Spinner /></Card>
  if (!choices.data?.length) return null
  const editable = canManage && choices.data.length > 1

  return (
    <Card>
      <CardHeader
        title="Modelo de diagnóstico"
        subtitle={
          editable
            ? 'Como escolher entre versões de um assistente. Vale para o que o rover e os uploads mandarem daqui em diante.'
            : 'A versão que diagnostica este talhão.'
        }
      />
      <ul className="flex flex-col gap-2 px-5 pb-5">
        {choices.data.map((choice) => (
          <li key={choice.key}>
            <ModelChoice
              choice={choice}
              editable={editable}
              busy={change.isPending && change.variables === choice.key}
              // Sempre a chave, nunca nulo: com PRIMARY_MODELS apontando a outra versão,
              // "voltar à recomendada" com nulo cairia nela, não na que a pessoa clicou.
              onSelect={() => change.mutate(choice.key)}
            />
          </li>
        ))}
      </ul>
      {change.error != null && <ErrorBox error={change.error} className="mx-5 mb-5" />}
    </Card>
  )
}

function ModelChoice({
  choice,
  editable,
  busy,
  onSelect,
}: {
  choice: AiModelChoiceOut
  editable: boolean
  busy: boolean
  onSelect: () => void
}) {
  const body = (
    <>
      <div className="flex flex-wrap items-center gap-2">
        <span
          className={cn(
            'flex size-4 shrink-0 items-center justify-center rounded-full border',
            choice.selected ? 'border-accent bg-accent text-accent-ink' : 'border-line',
          )}
          aria-hidden
        >
          {choice.selected && <Check className="size-3" />}
        </span>
        <span className="font-mono text-[13px] font-medium">{choice.key}</span>
        <span className="num text-[12px] text-muted">v{choice.version}</span>
        <Badge tone="neutral">{modelVariant(choice.variant)}</Badge>
        {choice.recommended && <Badge tone="accent">Recomendado</Badge>}
        {busy && <span className="text-[12px] text-muted">salvando…</span>}
      </div>
      <div className="mt-1.5 grid gap-0.5 pl-6 text-[12px] text-ink-2">
        {choice.name && <span>{choice.name}</span>}
        {choice.field_performance && (
          <span>
            Desempenho no campo: <strong>{choice.field_performance}</strong>
          </span>
        )}
        <span className="text-muted">Dados de treino: {choice.license}</span>
        {choice.caveat && <span className="text-warning">{choice.caveat}</span>}
      </div>
    </>
  )
  const box = cn(
    'w-full rounded-[10px] border p-3 text-left',
    choice.selected ? 'border-accent/60 bg-accent-soft' : 'border-line-soft',
  )
  if (!editable) return <div className={box}>{body}</div>
  return (
    <button
      type="button"
      role="radio"
      aria-checked={choice.selected}
      disabled={choice.selected || busy}
      onClick={onSelect}
      className={cn(box, !choice.selected && 'hover:bg-raised')}
    >
      {body}
    </button>
  )
}

// --- plantas do talhão ------------------------------------------------------------

export function PlantsCard({ fieldId, roverCrop }: { fieldId: string; roverCrop: boolean }) {
  const plants = useFieldPlants(fieldId)
  const [all, setAll] = useState(false)

  const sorted = useMemo(
    () =>
      [...(plants.data ?? [])].sort(
        (a, b) =>
          (STATUS_ORDER[a.status] ?? 9) - (STATUS_ORDER[b.status] ?? 9) ||
          b.primary_posterior - a.primary_posterior,
      ),
    [plants.data],
  )
  const counts = useMemo(() => {
    const result: Record<string, number> = {}
    for (const plant of plants.data ?? []) result[plant.status] = (result[plant.status] ?? 0) + 1
    return result
  }, [plants.data])

  // Talhão de milho ou café sem quadro do rover: o cartão só ocuparia espaço.
  if (!roverCrop && !plants.data?.length) return null
  const unavailable = plants.error instanceof ApiError && plants.error.status === 503
  const shown = all ? sorted : sorted.slice(0, PLANTS_PREVIEW)

  return (
    <Card>
      <CardHeader
        title="Plantas"
        subtitle="Cada planta vista pelo rover, somando as câmeras e os quadros em que apareceu."
        actions={<Sprout className="size-4 text-muted" aria-hidden />}
      />
      {plants.isLoading && <Spinner />}
      {unavailable && (
        <p className="px-5 pb-5 text-[13px] text-ink-2">
          O serviço de inferência deste ambiente não guarda talhões, então não há diagnóstico por planta. Ele precisa de{' '}
          <code className="font-mono text-[12px]">FIELDS_DIR</code> configurado.
        </p>
      )}
      {plants.error != null && !unavailable && <ErrorBox error={plants.error} className="mx-5 mb-5" />}
      {plants.data?.length === 0 && (
        <Empty title="O rover ainda não passou por aqui" icon={<Sprout className="size-5" />}>
          As plantas aparecem quando o rover manda quadros com a posição da câmera: rua, lado e distância no rumo.
        </Empty>
      )}
      {sorted.length > 0 && (
        <>
          <div className="flex flex-wrap gap-2 px-5 pb-3">
            {PLANT_STATUSES.filter((status) => counts[status]).map((status) => (
              <Badge key={status} tone={plantStatusTone(status)}>
                {plantStatus(status)} <span className="num">{counts[status]}</span>
              </Badge>
            ))}
          </div>
          <Table>
            <thead>
              <tr>
                <th className={th}>Planta</th>
                <th className={th}>Situação</th>
                <th className={th}>Doença</th>
                <th className={th}>Incidência</th>
                <th className={th}>Vista em</th>
              </tr>
            </thead>
            <tbody>
              {shown.map((plant) => (
                <PlantRow key={plant.plant_id} plant={plant} />
              ))}
            </tbody>
          </Table>
          {sorted.length > PLANTS_PREVIEW && (
            <div className="px-5 py-3">
              <Button size="sm" variant="ghost" onClick={() => setAll((value) => !value)}>
                {all ? 'Mostrar menos' : `Mostrar todas (${sorted.length})`}
              </Button>
            </div>
          )}
        </>
      )}
    </Card>
  )
}

function PlantRow({ plant }: { plant: PlantOut }) {
  return (
    <tr className="hover:bg-raised">
      <td className={td}>
        <div className="font-mono text-[12px]">{plant.plant_id}</div>
        <div className="text-[12px] text-muted">
          rua {plant.row_id} · {fmt.number(plant.x_along_m, 1)} m
        </div>
      </td>
      <td className={td}>
        <Badge tone={plantStatusTone(plant.status)}>{plantStatus(plant.status)}</Badge>
      </td>
      <td className={td}>
        {plant.primary_disease ? (
          <>
            <div>{disease(plant.primary_disease)}</div>
            <div className="num text-[12px] text-muted">{fmt.percent(plant.primary_posterior)} de certeza</div>
          </>
        ) : (
          <span className="text-muted">—</span>
        )}
      </td>
      <td className={`${td} num`}>{fmt.percent(plant.incidence)}</td>
      <td className={`${td} text-[12px] text-ink-2`}>
        <div className="num">
          {plant.n_cameras} {plant.n_cameras === 1 ? 'câmera' : 'câmeras'} · {plant.n_frames}{' '}
          {plant.n_frames === 1 ? 'quadro' : 'quadros'}
        </div>
        {plant.zones_seen.length > 0 && <div className="text-muted">{plant.zones_seen.map(plantZone).join(', ')}</div>}
      </td>
    </tr>
  )
}

// --- prevalência ----------------------------------------------------------------------

/**
 * Quanto de cada doença o talhão tem, contra o que o modelo viu no treino.
 *
 * Some quando não há estimativa (404: o rover ainda não passou; 409/503: a
 * inferência não tem o prior de treino ou não guarda talhões) — o cartão das
 * plantas já explica o motivo.
 */
export function PrevalenceCard({ fieldId }: { fieldId: string }) {
  const prevalence = useFieldPrevalence(fieldId)
  const rows = useMemo(() => {
    const data = prevalence.data
    if (!data) return []
    return Object.entries(data.field_prior)
      .map(([label, share]) => ({ label, share, training: data.training_prior[label] ?? 0 }))
      .sort((a, b) => b.share - a.share)
  }, [prevalence.data])

  const plants = prevalence.data?.plant_incidence
  if (!prevalence.data || (!rows.length && !plants)) return null
  return (
    <Card>
      <CardHeader
        title="Prevalência no talhão"
        subtitle="Quantas plantas estão doentes e, embaixo, a proporção de cada classe nos recortes que o rover classificou."
      />
      {plants && plants.apparent !== null && <PlantIncidence data={plants} />}
      <p className="mx-5 mb-2 text-[12px] text-muted">
        Proporção nos recortes, sem rótulo — {fmt.number(prevalence.data.effective_samples)} amostras.
        Não é a fração de plantas: o modelo põe probabilidade de doença em pedaço de folha sadia.
      </p>
      {prevalence.data.reliable === false && prevalence.data.note && (
        <p className="mx-5 mb-3 flex items-start gap-2 text-[12.5px] text-ink-2">
          <Badge tone="warning">Estimativa instável</Badge>
          <span>{prevalence.data.note}</span>
        </p>
      )}
      <ul className="flex flex-col gap-3 px-5 pb-5 text-[13px]">
        {rows.map((row) => (
          <li key={row.label}>
            <div className="mb-1 flex items-center justify-between gap-2">
              <span className="font-medium">{disease(row.label)}</span>
              <span className="num text-ink-2">
                <strong>{fmt.percent(row.share, 1)}</strong>
                <span className="text-muted"> · treino {fmt.percent(row.training, 1)}</span>
              </span>
            </div>
            <Meter value={row.share} tone={row.label === 'Healthy' ? 'good' : 'warning'} label={disease(row.label)} />
          </li>
        ))}
      </ul>
    </Card>
  )
}

/**
 * A fração de plantas doentes da última passada. Com a fusão calibrada, já descontado
 * o alarme falso e corrigida a sensibilidade (com intervalo); sem, a fração aparente.
 */
function PlantIncidence({ data }: { data: PlantIncidenceOut }) {
  const value = data.incidence ?? data.apparent ?? 0
  const corrected = data.method === 'rogan_gladen' && data.ci95 !== null
  return (
    <div className="mx-5 mb-4 rounded-[10px] border border-line-soft p-3 text-[13px]">
      <div className="mb-1 flex items-baseline justify-between gap-2">
        <span className="font-medium">Plantas doentes</span>
        <strong className="num text-[18px]">{fmt.percent(value, 1)}</strong>
      </div>
      <Meter value={value} tone="warning" label="Plantas doentes" />
      <p className="mt-2 text-[12.5px] text-ink-2">
        {corrected && data.ci95
          ? `Intervalo de 95%: ${fmt.percent(data.ci95[0], 1)} a ${fmt.percent(data.ci95[1], 1)}. ` +
            `${fmt.number(data.n_judged)} plantas julgadas, ${fmt.percent(data.apparent, 1)} sinalizadas.`
          : `Fração aparente: ${fmt.percent(data.apparent, 1)} de ${fmt.number(data.n_judged)} plantas sinalizadas, sem descontar alarme falso.`}
        {data.status_counts['revisar'] ? ` ${fmt.number(data.status_counts['revisar'])} para revisar ficaram fora da conta.` : ''}
      </p>
      {data.note && <p className="mt-1 text-[12px] text-muted">{data.note}</p>}
    </div>
  )
}
