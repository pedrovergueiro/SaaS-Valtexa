import { FlaskConical, Plus } from 'lucide-react'
import { useMemo, useState } from 'react'

import { api } from '@/api/client'
import { keys, useApiMutation, useBatches, useDevices, useProducts, useTanks } from '@/api/queries'
import type { ProductOut, TankOut } from '@/api/types'
import { useAuth } from '@/auth/AuthProvider'
import { Badge, Button, Card, CardHeader, Empty, ErrorBox, FormField, Meter, Modal, PageHeader, Spinner, Table, td, th } from '@/components/ui'
import { fmt } from '@/lib/format'
import { crop, disease, KNOWN_LABELS, tankStatus } from '@/lib/labels'

export default function Inputs() {
  const { can } = useAuth()
  const products = useProducts()
  const tanks = useTanks()
  const devices = useDevices({ kind: 'drone' })
  const [creating, setCreating] = useState(false)
  const [batchesFor, setBatchesFor] = useState<ProductOut | null>(null)
  const [loading, setLoading] = useState<TankOut | null>(null)

  const productName = useMemo(() => new Map(products.data?.map((item) => [item.id, item.name])), [products.data])
  const deviceName = useMemo(() => new Map(devices.data?.map((item) => [item.id, item.name])), [devices.data])

  return (
    <>
      <PageHeader
        title="Insumos"
        subtitle="O elo tanque → lote → produto → missão. A segurança bloqueia qualquer divergência entre o que está no tanque e o que a missão autoriza."
        actions={
          can('product:manage') && (
            <Button variant="primary" icon={<Plus className="size-4" />} onClick={() => setCreating(true)}>
              Novo produto
            </Button>
          )
        }
      />

      <Card>
        <CardHeader title="Produtos" subtitle="Culturas e alvos autorizados são lista fechada: a plataforma nunca escolhe produto sozinha." />
        <ErrorBox error={products.error} className="mx-5 mb-4" />
        {products.isLoading && <Spinner />}
        {products.data?.length === 0 && <Empty title="Nenhum produto cadastrado" icon={<FlaskConical className="size-5" />} />}
        {(products.data?.length ?? 0) > 0 && (
          <Table>
            <thead>
              <tr>
                <th className={th}>Produto</th>
                <th className={th}>Registro</th>
                <th className={th}>Culturas</th>
                <th className={th}>Alvos</th>
                <th className={`${th} text-right`}>Dose (L/ha)</th>
                <th className={`${th} text-right`}>Vento máx.</th>
                <th className={th} />
              </tr>
            </thead>
            <tbody>
              {products.data?.map((product) => (
                <tr key={product.id} className="hover:bg-raised">
                  <td className={td}>
                    <div className="font-medium">{product.name}</div>
                    <div className="text-[12px] text-muted">{product.active_ingredient ?? '—'}</div>
                  </td>
                  <td className={`${td} num`}>
                    {product.registration_number ?? <Badge tone="warning">sem registro</Badge>}
                  </td>
                  <td className={td}>{(product.allowed_crops ?? []).map(crop).join(', ') || '—'}</td>
                  <td className={td}>
                    <span className="line-clamp-2 text-[12px]">{(product.authorized_targets ?? []).map(disease).join(', ') || '—'}</span>
                  </td>
                  <td className={`${td} num text-right`}>
                    {product.min_rate_l_ha ?? '?'}–{product.max_rate_l_ha ?? '?'}
                  </td>
                  <td className={`${td} num text-right`}>{product.max_wind_ms != null ? `${product.max_wind_ms} m/s` : 'global'}</td>
                  <td className={`${td} text-right`}>
                    <Button size="sm" variant="ghost" onClick={() => setBatchesFor(product)}>
                      Lotes
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card>

      <Card className="mt-4">
        <CardHeader title="Tanques" subtitle="Registrar a carga é declarar o que está fisicamente no drone. É esse registro que a segurança confere." />
        {tanks.data?.length === 0 && <Empty title="Nenhum tanque" >Tanques aparecem quando um drone é provisionado.</Empty>}
        <div className="grid gap-3 px-5 pb-5 sm:grid-cols-2 xl:grid-cols-3">
          {tanks.data?.map((tank) => (
            <div key={tank.id} className="rounded-[12px] border border-line p-4">
              <div className="flex items-center justify-between">
                <div>
                  <div className="font-medium">
                    {deviceName.get(tank.device_id) ?? 'Drone'} · tanque {tank.index + 1}
                  </div>
                  <div className="text-[12px] text-muted">{tankStatus(tank.status)}</div>
                </div>
                {can('tank:load') && (
                  <Button size="sm" onClick={() => setLoading(tank)}>
                    Carregar
                  </Button>
                )}
              </div>
              <div className="mt-3 flex items-center gap-2">
                <Meter value={tank.capacity_l ? tank.current_level_l / tank.capacity_l : 0} tone="info" label="Nível" />
                <span className="num w-20 text-right text-[12px]">
                  {fmt.number(tank.current_level_l, 1)}/{fmt.number(tank.capacity_l, 0)} L
                </span>
              </div>
              <div className="mt-2 truncate text-[12px] text-ink-2">
                {tank.loaded_product_id ? productName.get(tank.loaded_product_id) ?? 'produto' : 'vazio'}
                {tank.loaded_at ? ` · carregado ${fmt.ago(tank.loaded_at)}` : ''}
              </div>
            </div>
          ))}
        </div>
      </Card>

      {creating && <ProductModal onClose={() => setCreating(false)} />}
      {batchesFor && <BatchesModal product={batchesFor} canManage={can('product:manage')} onClose={() => setBatchesFor(null)} />}
      {loading && <LoadModal tank={loading} products={products.data ?? []} onClose={() => setLoading(null)} />}
    </>
  )
}

function ProductModal({ onClose }: { onClose: () => void }) {
  const [form, setForm] = useState({
    name: '',
    manufacturer: '',
    active_ingredient: '',
    registration_number: '',
    crops: ['corn'],
    targets: [] as string[],
    min: '',
    max: '',
    default: '',
    wind: '',
    reentry: '',
  })
  const set = (key: keyof typeof form, value: unknown) => setForm((current) => ({ ...current, [key]: value }))
  const toggle = (key: 'crops' | 'targets', value: string) =>
    set(key, form[key].includes(value) ? form[key].filter((item) => item !== value) : [...form[key], value])
  const num = (value: string) => (value ? Number(value) : null)

  const create = useApiMutation(
    () =>
      api('/v1/products', {
        method: 'POST',
        body: {
          name: form.name,
          manufacturer: form.manufacturer || null,
          active_ingredient: form.active_ingredient || null,
          registration_number: form.registration_number || null,
          allowed_crops: form.crops,
          authorized_targets: form.targets,
          min_rate_l_ha: num(form.min),
          max_rate_l_ha: num(form.max),
          default_rate_l_ha: num(form.default),
          max_wind_ms: num(form.wind),
          reentry_interval_h: num(form.reentry),
        },
      }),
    [keys.products],
  )

  return (
    <Modal
      open
      onClose={onClose}
      wide
      title="Novo produto"
      description="Cadastrar de menos bloqueia a aplicação; cadastrar errado também. É de propósito."
      footer={
        <>
          <Button onClick={onClose}>Cancelar</Button>
          <Button variant="primary" loading={create.isPending} disabled={!form.name.trim()} onClick={() => create.mutate(undefined, { onSuccess: onClose })}>
            Salvar produto
          </Button>
        </>
      }
    >
      <div className="grid gap-4 sm:grid-cols-2">
        <FormField label="Nome">
          <input className="input" value={form.name} onChange={(event) => set('name', event.target.value)} />
        </FormField>
        <FormField label="Registro no MAPA" hint="Sem registro, a segurança bloqueia.">
          <input className="input num" value={form.registration_number} onChange={(event) => set('registration_number', event.target.value)} />
        </FormField>
        <FormField label="Fabricante">
          <input className="input" value={form.manufacturer} onChange={(event) => set('manufacturer', event.target.value)} />
        </FormField>
        <FormField label="Ingrediente ativo">
          <input className="input" value={form.active_ingredient} onChange={(event) => set('active_ingredient', event.target.value)} />
        </FormField>
        <FormField label="Culturas autorizadas">
          <div className="flex flex-wrap gap-2">
            {['corn', 'coffee', 'soy'].map((value) => (
              <label key={value} className="flex items-center gap-1.5 text-[13px]">
                <input type="checkbox" checked={form.crops.includes(value)} onChange={() => toggle('crops', value)} className="accent-[var(--accent)]" />
                {crop(value)}
              </label>
            ))}
          </div>
        </FormField>
        <FormField label="Alvos autorizados">
          <div className="flex flex-wrap gap-2">
            {KNOWN_LABELS.filter((value) => value !== 'Healthy').map((value) => (
              <label key={value} className="flex items-center gap-1.5 text-[13px]">
                <input type="checkbox" checked={form.targets.includes(value)} onChange={() => toggle('targets', value)} className="accent-[var(--accent)]" />
                {disease(value)}
              </label>
            ))}
          </div>
        </FormField>
        <div className="grid grid-cols-3 gap-3 sm:col-span-2">
          <FormField label="Dose mín. (L/ha)">
            <input className="input num" type="number" step="0.05" value={form.min} onChange={(event) => set('min', event.target.value)} />
          </FormField>
          <FormField label="Dose padrão">
            <input className="input num" type="number" step="0.05" value={form.default} onChange={(event) => set('default', event.target.value)} />
          </FormField>
          <FormField label="Dose máx.">
            <input className="input num" type="number" step="0.05" value={form.max} onChange={(event) => set('max', event.target.value)} />
          </FormField>
          <FormField label="Vento máx. (m/s)" hint="Aperta o limite global.">
            <input className="input num" type="number" step="0.5" value={form.wind} onChange={(event) => set('wind', event.target.value)} />
          </FormField>
          <FormField label="Reentrada (h)">
            <input className="input num" type="number" step="1" value={form.reentry} onChange={(event) => set('reentry', event.target.value)} />
          </FormField>
        </div>
      </div>
      <ErrorBox error={create.error} className="mt-4" />
    </Modal>
  )
}

function BatchesModal({ product, canManage, onClose }: { product: ProductOut; canManage: boolean; onClose: () => void }) {
  const batches = useBatches(product.id)
  const [code, setCode] = useState('')
  const [expires, setExpires] = useState('')
  const [quantity, setQuantity] = useState('')
  const create = useApiMutation(
    () =>
      api(`/v1/products/${product.id}/batches`, {
        method: 'POST',
        body: { code, expires_on: expires || null, quantity_l: quantity ? Number(quantity) : null },
      }),
    [keys.batches(product.id)],
  )
  const today = new Date().toISOString().slice(0, 10)

  return (
    <Modal open onClose={onClose} title={`Lotes · ${product.name}`} description="A validade é conferida de novo na hora de autorizar — um lote pode vencer entre o planejamento e o voo.">
      <ul className="mb-4">
        {batches.data?.length === 0 && <li className="text-[13px] text-muted">Nenhum lote.</li>}
        {batches.data?.map((batch) => (
          <li key={batch.id} className="flex items-center justify-between border-b border-line-soft py-2 text-[13px]">
            <span className="num font-medium">{batch.code}</span>
            <span className="text-ink-2">
              {batch.expires_on ? (
                batch.expires_on < today ? <Badge tone="critical">venceu {batch.expires_on}</Badge> : `vence ${batch.expires_on}`
              ) : (
                'sem validade'
              )}
              {batch.quantity_l != null && ` · ${fmt.liters(batch.quantity_l)}`}
            </span>
          </li>
        ))}
      </ul>
      {canManage && (
        <div className="grid gap-3 sm:grid-cols-3">
          <FormField label="Código">
            <input className="input num" value={code} onChange={(event) => setCode(event.target.value)} />
          </FormField>
          <FormField label="Validade">
            <input className="input" type="date" value={expires} onChange={(event) => setExpires(event.target.value)} />
          </FormField>
          <FormField label="Volume (L)">
            <input className="input num" type="number" value={quantity} onChange={(event) => setQuantity(event.target.value)} />
          </FormField>
          <Button
            variant="primary"
            className="sm:col-span-3"
            disabled={!code.trim()}
            loading={create.isPending}
            onClick={() =>
              create.mutate(undefined, {
                onSuccess: () => {
                  setCode('')
                  setExpires('')
                  setQuantity('')
                },
              })
            }
          >
            Adicionar lote
          </Button>
          <ErrorBox error={create.error} className="sm:col-span-3" />
        </div>
      )}
    </Modal>
  )
}

function LoadModal({ tank, products, onClose }: { tank: TankOut; products: ProductOut[]; onClose: () => void }) {
  const [productId, setProductId] = useState(products[0]?.id ?? '')
  const batches = useBatches(productId || undefined)
  const [batchId, setBatchId] = useState('')
  const [volume, setVolume] = useState(String(tank.capacity_l))
  const load = useApiMutation(
    () =>
      api(`/v1/tanks/${tank.id}/load`, {
        method: 'POST',
        body: { product_id: productId, batch_id: batchId || batches.data?.[0]?.id, volume_l: Number(volume) },
      }),
    [['tanks'], ['missions']],
  )
  const empty = useApiMutation(() => api(`/v1/tanks/${tank.id}/empty`, { method: 'POST' }), [['tanks']])

  return (
    <Modal
      open
      onClose={onClose}
      title={`Carregar tanque ${tank.index + 1}`}
      description="Declare exatamente o que foi colocado. Se não for o produto e o lote que a missão autoriza, a segurança bloqueia a decolagem."
      footer={
        <>
          <Button variant="ghost" loading={empty.isPending} onClick={() => empty.mutate(undefined, { onSuccess: onClose })}>
            Esvaziar
          </Button>
          <Button onClick={onClose}>Cancelar</Button>
          <Button variant="primary" loading={load.isPending} disabled={!productId || Number(volume) <= 0} onClick={() => load.mutate(undefined, { onSuccess: onClose })}>
            Registrar carga
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-4">
        <FormField label="Produto">
          <select className="input" value={productId} onChange={(event) => { setProductId(event.target.value); setBatchId('') }}>
            {products.map((product) => (
              <option key={product.id} value={product.id}>
                {product.name}
              </option>
            ))}
          </select>
        </FormField>
        <FormField label="Lote">
          <select className="input" value={batchId || batches.data?.[0]?.id || ''} onChange={(event) => setBatchId(event.target.value)}>
            {batches.data?.map((batch) => (
              <option key={batch.id} value={batch.id}>
                {batch.code}
              </option>
            ))}
          </select>
        </FormField>
        <FormField label={`Volume (L) · capacidade ${tank.capacity_l} L`}>
          <input className="input num" type="number" min="0" max={tank.capacity_l} step="0.5" value={volume} onChange={(event) => setVolume(event.target.value)} />
        </FormField>
        <ErrorBox error={load.error ?? empty.error} />
      </div>
    </Modal>
  )
}
