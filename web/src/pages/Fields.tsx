import { Plus, Sprout } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { api } from '@/api/client'
import { keys, useApiMutation, useFarms, useFields } from '@/api/queries'
import type { FarmOut, FieldOut } from '@/api/types'
import { useAuth } from '@/auth/AuthProvider'
import { FarmMap } from '@/components/FarmMap'
import { PolygonDraw } from '@/components/PolygonDraw'
import { Button, Card, CardHeader, Empty, ErrorBox, FormField, Modal, PageHeader, Spinner } from '@/components/ui'
import { fmt } from '@/lib/format'
import { crop } from '@/lib/labels'

export default function Fields() {
  const { can } = useAuth()
  const navigate = useNavigate()
  const farms = useFarms()
  const fields = useFields()
  const [creatingField, setCreatingField] = useState(false)
  const [creatingFarm, setCreatingFarm] = useState(false)

  const farmName = new Map(farms.data?.map((farm) => [farm.id, farm.name]))
  const canManage = can('farm:manage')
  const hasFarm = (farms.data?.length ?? 0) > 0

  return (
    <>
      <PageHeader
        title="Talhões"
        subtitle="O gêmeo digital de cada talhão: o que existe onde, e o que mudou desde a última passada."
        actions={
          canManage && (
            <>
              <Button onClick={() => setCreatingFarm(true)}>Nova fazenda</Button>
              <Button variant="primary" icon={<Plus className="size-4" />} disabled={!hasFarm} onClick={() => setCreatingField(true)}>
                Novo talhão
              </Button>
            </>
          )
        }
      />

      <ErrorBox error={fields.error ?? farms.error} className="mb-4" />
      {fields.isLoading && <Spinner />}

      {!fields.isLoading && (fields.data?.length ?? 0) === 0 && (
        <Card>
          <Empty title="Nenhum talhão cadastrado" icon={<Sprout className="size-5" />}>
            {hasFarm ? 'Desenhe o primeiro talhão no mapa.' : 'Comece cadastrando a fazenda.'}
          </Empty>
        </Card>
      )}

      {(fields.data?.length ?? 0) > 0 && (
        <div className="grid gap-4 xl:grid-cols-[1fr_1.2fr]">
          <div className="grid content-start gap-3 sm:grid-cols-2 xl:grid-cols-1">
            {fields.data?.map((field) => (
              <Link key={field.id} to={`/talhoes/${field.id}`} className="card flex items-center gap-4 p-4 hover:border-accent/50">
                <span className="grid size-11 shrink-0 place-items-center rounded-[10px] bg-accent-soft">
                  <Sprout className="size-5" aria-hidden />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-medium">{field.name}</span>
                  <span className="block truncate text-[12px] text-muted">
                    {farmName.get(field.farm_id) ?? '—'} · {crop(field.crop)}
                    {field.crop_stage ? ` · ${field.crop_stage}` : ''}
                  </span>
                </span>
                <span className="num text-[13px] text-ink-2">{fmt.hectares(field.area_ha)}</span>
              </Link>
            ))}
          </div>
          <Card className="overflow-hidden">
            <CardHeader title="Mapa" subtitle="Clique num talhão para abrir." />
            <div className="px-5 pb-5">
              <FarmMap fields={fields.data} className="h-[28rem]" onFieldClick={(id) => navigate(`/talhoes/${id}`)} />
            </div>
          </Card>
        </div>
      )}

      {creatingField && farms.data && (
        <FieldModal farms={farms.data} existing={fields.data ?? []} onClose={() => setCreatingField(false)} />
      )}
      {creatingFarm && <FarmModal onClose={() => setCreatingFarm(false)} />}
    </>
  )
}

function FieldModal({ farms, existing, onClose }: { farms: FarmOut[]; existing: FieldOut[]; onClose: () => void }) {
  const [farmId, setFarmId] = useState(farms[0]?.id ?? '')
  const [name, setName] = useState('')
  const [cropValue, setCrop] = useState('corn')
  const [stage, setStage] = useState('')
  const [azimuth, setAzimuth] = useState('')
  const [spacing, setSpacing] = useState('')
  const [boundary, setBoundary] = useState<number[][]>([])

  const create = useApiMutation(
    () =>
      api<FieldOut>(`/v1/farms/${farmId}/fields`, {
        method: 'POST',
        body: {
          name,
          crop: cropValue,
          boundary,
          crop_stage: stage || null,
          row_azimuth_deg: azimuth ? Number(azimuth) : null,
          row_spacing_m: spacing ? Number(spacing) : null,
        },
      }),
    [keys.fields, keys.farms],
  )

  return (
    <Modal
      open
      onClose={onClose}
      wide
      title="Novo talhão"
      description="A área é calculada a partir do desenho — é ela que manda na dose e na cerca virtual."
      footer={
        <>
          <Button onClick={onClose}>Cancelar</Button>
          <Button
            variant="primary"
            loading={create.isPending}
            disabled={!name.trim() || boundary.length < 3}
            onClick={() => create.mutate(undefined, { onSuccess: onClose })}
          >
            Salvar talhão
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-4">
        <div className="grid gap-4 sm:grid-cols-3">
          <FormField label="Fazenda">
            <select className="input" value={farmId} onChange={(event) => setFarmId(event.target.value)}>
              {farms.map((farm) => (
                <option key={farm.id} value={farm.id}>
                  {farm.name}
                </option>
              ))}
            </select>
          </FormField>
          <FormField label="Nome">
            <input className="input" value={name} onChange={(event) => setName(event.target.value)} placeholder="Talhão B — Milho" />
          </FormField>
          <FormField label="Cultura">
            <select className="input" value={cropValue} onChange={(event) => setCrop(event.target.value)}>
              <option value="corn">Milho</option>
              <option value="coffee">Café</option>
              <option value="soy">Soja (sem modelo ainda)</option>
            </select>
          </FormField>
          <FormField label="Estágio" hint="Ex.: V8, VT, R3">
            <input className="input" value={stage} onChange={(event) => setStage(event.target.value)} />
          </FormField>
          <FormField label="Direção das linhas (°)" hint="0 = norte-sul · 90 = leste-oeste">
            <input className="input num" type="number" min="0" max="179" value={azimuth} onChange={(event) => setAzimuth(event.target.value)} />
          </FormField>
          <FormField label="Espaçamento (m)">
            <input className="input num" type="number" min="0.1" step="0.05" value={spacing} onChange={(event) => setSpacing(event.target.value)} />
          </FormField>
        </div>
        <PolygonDraw value={boundary} onChange={setBoundary} fields={existing} />
        <ErrorBox error={create.error} />
      </div>
    </Modal>
  )
}

function FarmModal({ onClose }: { onClose: () => void }) {
  const [name, setName] = useState('')
  const [center, setCenter] = useState<number[] | null>(null)
  const [base, setBase] = useState<number[] | null>(null)
  const [picking, setPicking] = useState<'center' | 'base'>('center')

  const create = useApiMutation(
    () =>
      api<FarmOut>('/v1/farms', {
        method: 'POST',
        body: {
          name,
          center_lon: center?.[0],
          center_lat: center?.[1],
          base_lon: base?.[0] ?? null,
          base_lat: base?.[1] ?? null,
        },
      }),
    [keys.farms],
  )

  return (
    <Modal
      open
      onClose={onClose}
      wide
      title="Nova fazenda"
      description="Marque o centro da propriedade e, se já existir, a base onde a frota recarrega — é de lá que a política de energia calcula o retorno."
      footer={
        <>
          <Button onClick={onClose}>Cancelar</Button>
          <Button variant="primary" loading={create.isPending} disabled={!name.trim() || !center} onClick={() => create.mutate(undefined, { onSuccess: onClose })}>
            Salvar fazenda
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-4">
        <FormField label="Nome">
          <input className="input" value={name} onChange={(event) => setName(event.target.value)} placeholder="Fazenda Boa Vista" />
        </FormField>
        <div className="flex flex-wrap gap-2 text-[13px]">
          <Button size="sm" variant={picking === 'center' ? 'primary' : 'secondary'} onClick={() => setPicking('center')}>
            Marcar centro {center ? '✓' : ''}
          </Button>
          <Button size="sm" variant={picking === 'base' ? 'primary' : 'secondary'} onClick={() => setPicking('base')}>
            Marcar base {base ? '✓' : ''}
          </Button>
        </div>
        <FarmMapPicker
          points={[center, base].filter((point): point is number[] => Boolean(point))}
          onPick={(point) => (picking === 'center' ? setCenter(point) : setBase(point))}
        />
        <ErrorBox error={create.error} />
      </div>
    </Modal>
  )
}

function FarmMapPicker({ points, onPick }: { points: number[][]; onPick: (point: number[]) => void }) {
  return <FarmMap className="h-72" draftPolygon={points} onMapClick={onPick} />
}
