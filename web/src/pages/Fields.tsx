import { Building2, ClipboardList, Plus, Sprout } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { api } from '@/api/client'
import { keys, useApiMutation, useFarms, useFields } from '@/api/queries'
import type { FarmOut, FieldOut } from '@/api/types'
import { useAuth } from '@/auth/AuthProvider'
import { FarmMap } from '@/components/FarmMap'
import { FarmRegistryInputs, registryHasErrors } from '@/components/FarmRegistryInputs'
import { FieldSpacingInputs } from '@/components/FieldSpacingInputs'
import { PolygonDraw } from '@/components/PolygonDraw'
import { Button, Card, CardHeader, Empty, ErrorBox, FormField, Modal, PageHeader, Spinner } from '@/components/ui'
import { fmt } from '@/lib/format'
import {
  emptyRegistry,
  farmRegistryGaps,
  formatDocument,
  registryChanges,
  registryFromFarm,
  registryPayload,
  type RegistryKey,
  type RegistryValues,
} from '@/lib/farmRegistry'
import { optionalNumber, parseValidationRows } from '@/lib/fieldSetup'
import { crop } from '@/lib/labels'

export default function Fields() {
  const { can } = useAuth()
  const navigate = useNavigate()
  const farms = useFarms()
  const fields = useFields()
  const [creatingField, setCreatingField] = useState<string | null>(null)
  const [creatingFarm, setCreatingFarm] = useState(false)
  const [editingFarm, setEditingFarm] = useState<FarmOut | null>(null)

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
              <Button variant="primary" icon={<Plus className="size-4" />} disabled={!hasFarm} onClick={() => setCreatingField(farms.data?.[0]?.id ?? '')}>
                Novo talhão
              </Button>
            </>
          )
        }
      />

      <ErrorBox error={fields.error ?? farms.error} className="mb-4" />
      {fields.isLoading && <Spinner />}

      {!fields.isLoading && !farms.isLoading && !hasFarm && (
        <Card>
          <Empty
            title="Nenhuma fazenda cadastrada"
            icon={<Building2 className="size-5" />}
            action={
              canManage ? (
                <Button variant="primary" onClick={() => setCreatingFarm(true)}>
                  Cadastrar a fazenda
                </Button>
              ) : undefined
            }
          >
            {canManage
              ? 'Tudo começa pela fazenda: o centro dela e a base onde a frota recarrega.'
              : 'Peça a quem administra a conta para cadastrar a fazenda.'}
          </Empty>
        </Card>
      )}

      {hasFarm && (
        <div className="mb-4 flex flex-wrap gap-2" aria-label="Fazendas">
          {farms.data?.map((farm) => (
            <div key={farm.id} className="card flex items-center gap-3 px-4 py-2.5">
              <Building2 className="size-4 text-muted" aria-hidden />
              <span className="font-medium">{farm.name}</span>
              <span className="text-[12px] text-muted">
                {farm.fields === 0 ? 'sem talhão' : `${farm.fields} talhão(ões)`}
              </span>
              {farm.fields === 0 && canManage && (
                <Button size="sm" variant="primary" icon={<Plus className="size-4" />} onClick={() => setCreatingField(farm.id)}>
                  Desenhar o primeiro talhão
                </Button>
              )}
              <FarmRegistryChip farm={farm} canManage={canManage} onEdit={() => setEditingFarm(farm)} />
            </div>
          ))}
        </div>
      )}

      {!fields.isLoading && hasFarm && (fields.data?.length ?? 0) === 0 && (
        <Card>
          <Empty title="Nenhum talhão cadastrado" icon={<Sprout className="size-5" />}>
            {canManage
              ? 'Desenhe o talhão no mapa e informe os espaçamentos: são eles que a fusão por planta usa para separar uma planta da outra.'
              : 'Peça a quem administra a conta para desenhar os talhões.'}
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

      {creatingField !== null && farms.data && (
        <FieldModal
          farms={farms.data}
          initialFarmId={creatingField}
          existing={fields.data ?? []}
          onClose={() => setCreatingField(null)}
        />
      )}
      {creatingFarm && <FarmModal onClose={() => setCreatingFarm(false)} />}
      {editingFarm && <FarmRegistryModal farm={editingFarm} onClose={() => setEditingFarm(null)} />}
    </>
  )
}

function FieldModal({
  farms,
  initialFarmId,
  existing,
  onClose,
}: {
  farms: FarmOut[]
  initialFarmId: string
  existing: FieldOut[]
  onClose: () => void
}) {
  const navigate = useNavigate()
  const { isPlatform } = useAuth()
  const [farmId, setFarmId] = useState(initialFarmId || farms[0]?.id || '')
  const [name, setName] = useState('')
  const [cropValue, setCrop] = useState('coffee')
  const [stage, setStage] = useState('')
  const [azimuth, setAzimuth] = useState('')
  const [spacing, setSpacing] = useState('')
  const [plantSpacing, setPlantSpacing] = useState('')
  const [rowCount, setRowCount] = useState('')
  const [validation, setValidation] = useState('')
  const [notes, setNotes] = useState('')
  const [boundary, setBoundary] = useState<number[][]>([])
  const fileiras = parseValidationRows(validation, optionalNumber(rowCount))

  const create = useApiMutation(
    () =>
      api<FieldOut>(`/v1/farms/${farmId}/fields`, {
        method: 'POST',
        body: {
          name,
          crop: cropValue,
          boundary,
          crop_stage: stage || null,
          row_azimuth_deg: optionalNumber(azimuth),
          row_spacing_m: optionalNumber(spacing),
          plant_spacing_m: optionalNumber(plantSpacing),
          row_count: optionalNumber(rowCount),
          validation_rows: fileiras.rows,
          notes: notes.trim() || null,
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
            disabled={!name.trim() || boundary.length < 3 || Boolean(fileiras.error)}
            onClick={() =>
              create.mutate(undefined, {
                // A equipe segue direto para o editor: a IA encaixa o contorno, lê os
                // obstáculos e calcula a rota assim que ele abre.
                onSuccess: (novo) => (isPlatform ? navigate(`/talhoes/${novo.id}/contorno?ajustar=1`) : onClose()),
              })
            }
          >
            {isPlatform ? 'Salvar e ajustar com IA' : 'Salvar talhão'}
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
        </div>
        <FieldSpacingInputs
          values={{ spacing, plantSpacing, rowCount, validation, notes }}
          setters={{ setSpacing, setPlantSpacing, setRowCount, setValidation, setNotes }}
          validationError={fileiras.error}
        />
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
  const [registro, setRegistro] = useState<RegistryValues>(emptyRegistry)

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
          ...registryPayload(registro),
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
          <Button variant="primary" loading={create.isPending} disabled={!name.trim() || !center || registryHasErrors(registro)} onClick={() => create.mutate(undefined, { onSuccess: onClose })}>
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
        <details className="rounded-[10px] border border-line px-4 py-3">
          <summary className="cursor-pointer text-[14px] font-medium">Identificação da propriedade (opcional)</summary>
          <p className="mt-1 mb-3 text-[12px] text-muted">
            Produtor, CPF/CNPJ, município, CAR e responsável técnico. Dá para completar depois.
          </p>
          <FarmRegistryInputs values={registro} onChange={(key, value) => setRegistro((atual) => ({ ...atual, [key]: value }))} />
        </details>
        <ErrorBox error={create.error} />
      </div>
    </Modal>
  )
}

function FarmMapPicker({ points, onPick }: { points: number[][]; onPick: (point: number[]) => void }) {
  return <FarmMap className="h-72" draftPolygon={points} onMapClick={onPick} />
}


/** Situação da identificação da fazenda e o botão que a completa ou edita. */
function FarmRegistryChip({ farm, canManage, onEdit }: { farm: FarmOut; canManage: boolean; onEdit: () => void }) {
  const falta = farmRegistryGaps(farm)
  const resumo = [farm.owner_name, farm.owner_document && formatDocument(farm.owner_document), farm.city && `${farm.city}${farm.state ? `/${farm.state}` : ''}`]
    .filter(Boolean)
    .join(' · ')
  return (
    <>
      {resumo && <span className="text-[12px] text-ink-2">{resumo}</span>}
      {falta.length > 0 && (
        <span className="text-[12px] text-warning" title={`Falta: ${falta.join(', ')}`}>
          cadastro incompleto: {falta.join(', ')}
        </span>
      )}
      {canManage && (
        <Button size="sm" variant={falta.length > 0 ? 'secondary' : 'ghost'} icon={<ClipboardList className="size-4" />} onClick={onEdit}>
          {falta.length > 0 ? 'Completar cadastro' : 'Cadastro'}
        </Button>
      )}
    </>
  )
}

function FarmRegistryModal({ farm, onClose }: { farm: FarmOut; onClose: () => void }) {
  const [registro, setRegistro] = useState<RegistryValues>(() => registryFromFarm(farm))
  const mudancas = registryChanges(farm, registro)
  const salvar = useApiMutation(
    () => api<FarmOut>(`/v1/farms/${farm.id}`, { method: 'PATCH', body: mudancas }),
    [keys.farms],
  )
  const alterar = (key: RegistryKey, value: string) => setRegistro((atual) => ({ ...atual, [key]: value }))
  return (
    <Modal
      open
      onClose={onClose}
      wide
      title={`Cadastro de ${farm.name}`}
      description="Identificação da propriedade. Cada alteração fica na auditoria, com o antes e o depois."
      footer={
        <>
          <Button onClick={onClose}>Cancelar</Button>
          <Button
            variant="primary"
            loading={salvar.isPending}
            disabled={Object.keys(mudancas).length === 0 || registryHasErrors(registro)}
            onClick={() => salvar.mutate(undefined, { onSuccess: onClose })}
          >
            Salvar cadastro
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-4">
        <FarmRegistryInputs values={registro} onChange={alterar} />
        <ErrorBox error={salvar.error} />
      </div>
    </Modal>
  )
}
