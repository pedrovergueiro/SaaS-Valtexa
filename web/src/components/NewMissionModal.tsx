import { Info } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { useBatches, useCreateMission, useDevices, useFields, useProducts, useTanks, useZones } from '@/api/queries'
import type { MissionCreate } from '@/api/types'
import { Button, ErrorBox, FormField, Modal, Tabs } from '@/components/ui'
import { crop, missionKind } from '@/lib/labels'

type Kind = 'scout' | 'spray' | 'verify'

export type MissionDefaults = {
  kind?: Kind
  fieldId?: string
  zoneId?: string
  productId?: string
  rate?: number
  decisionId?: string
}

/**
 * Criação de missão. Ela nasce em rascunho: nada vai ao robô sem passar pela
 * camada de segurança, e uma pulverização ainda exige o agrônomo.
 *
 * Montado de novo a cada abertura — quem chama renderiza só quando aberto —,
 * então os padrões valem sempre, sem estado sobrando da vez anterior.
 */
export function NewMissionModal({ onClose, defaults = {} }: { onClose: () => void; defaults?: MissionDefaults }) {
  const navigate = useNavigate()
  const fields = useFields()
  const devices = useDevices()
  const products = useProducts()
  const create = useCreateMission()

  const [kind, setKind] = useState<Kind>(defaults.kind ?? 'scout')
  const [fieldId, setFieldId] = useState(defaults.fieldId ?? '')
  const [zoneId, setZoneId] = useState(defaults.zoneId ?? '')
  const [deviceId, setDeviceId] = useState('')
  const [swath, setSwath] = useState('')
  const [productId, setProductId] = useState(defaults.productId ?? '')
  const [batchId, setBatchId] = useState('')
  const [tankId, setTankId] = useState('')
  const [rate, setRate] = useState(defaults.rate ? String(defaults.rate) : '')
  const [quantity, setQuantity] = useState('')

  const zones = useZones(fieldId || undefined)
  const batches = useBatches(productId || undefined)
  const tanks = useTanks(deviceId ? { device_id: deviceId } : {})

  const wantedKind = kind === 'spray' ? 'drone' : 'rover'
  const eligible = useMemo(
    () => (devices.data ?? []).filter((device) => device.kind === wantedKind && device.status === 'active'),
    [devices.data, wantedKind],
  )
  const field = fields.data?.find((item) => item.id === fieldId)
  const product = products.data?.find((item) => item.id === productId)
  const compatible = (products.data ?? []).filter((item) => !field || (item.allowed_crops ?? []).includes(field.crop))

  useEffect(() => {
    if (!fieldId && fields.data?.[0]) setFieldId(fields.data[0].id)
  }, [fields.data, fieldId])
  useEffect(() => {
    setDeviceId(eligible[0]?.id ?? '')
  }, [eligible])
  useEffect(() => {
    if (product?.default_rate_l_ha && !rate) setRate(String(product.default_rate_l_ha))
  }, [product, rate])
  useEffect(() => {
    if (!batchId && batches.data?.[0]) setBatchId(batches.data[0].id)
  }, [batches.data, batchId])

  const zone = zones.data?.find((item) => item.id === zoneId)

  function submit() {
    const body: MissionCreate = {
      kind,
      field_id: fieldId,
      device_id: deviceId,
      zone_id: zoneId || null,
      target_polygon: zone ? zone.boundary : null,
      plan: swath ? { swath_m: Number(swath) } : {},
      decision_id: defaults.decisionId ?? null,
    }
    if (kind === 'spray') {
      Object.assign(body, {
        product_id: productId || null,
        product_batch_id: batchId || null,
        tank_id: tankId || null,
        authorized_rate_l_ha: rate ? Number(rate) : null,
        authorized_quantity_l: quantity ? Number(quantity) : null,
      })
    }
    create.mutate(body, {
      onSuccess: (mission) => {
        onClose()
        navigate(`/missoes/${mission.id}`)
      },
    })
  }

  const ready =
    fieldId && deviceId && (kind !== 'spray' || (productId && batchId && tankId && Number(rate) > 0 && Number(quantity) > 0))

  return (
    <Modal
      open
      onClose={onClose}
      wide
      title="Nova missão"
      description={
        defaults.decisionId
          ? 'A partir de uma recomendação do motor de decisão. Continua sendo rascunho até a aprovação e a segurança.'
          : 'A missão nasce em rascunho. Nada vai ao robô sem passar pela camada de segurança.'
      }
      footer={
        <>
          <Button onClick={onClose}>Cancelar</Button>
          <Button variant="primary" loading={create.isPending} disabled={!ready} onClick={submit}>
            Criar rascunho
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-5">
        <Tabs<Kind>
          value={kind}
          onChange={setKind}
          items={(['scout', 'spray', 'verify'] as Kind[]).map((value) => ({ value, label: missionKind(value) }))}
        />

        <div className="grid gap-4 sm:grid-cols-2">
          <FormField label="Talhão">
            <select
              className="input"
              value={fieldId}
              onChange={(event) => {
                setFieldId(event.target.value)
                setZoneId('')
              }}
            >
              {fields.data?.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name} · {crop(item.crop)}
                </option>
              ))}
            </select>
          </FormField>
          <FormField label="Área" hint="Sem zona, a missão cobre o talhão inteiro menos a margem de segurança.">
            <select className="input" value={zoneId} onChange={(event) => setZoneId(event.target.value)}>
              <option value="">Talhão inteiro</option>
              {zones.data?.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
          </FormField>
          <FormField label={kind === 'spray' ? 'Drone' : 'Rover'} hint={eligible.length ? undefined : `Nenhum ${wantedKind} ativo na frota.`}>
            <select className="input" value={deviceId} onChange={(event) => setDeviceId(event.target.value)}>
              {eligible.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name} · {item.serial_number}
                </option>
              ))}
            </select>
          </FormField>
          <FormField label="Largura da faixa (m)" hint="Vazio usa a do hardware.">
            <input className="input num" type="number" min="0.5" step="0.5" value={swath} onChange={(event) => setSwath(event.target.value)} />
          </FormField>
        </div>

        {kind === 'spray' && (
          <>
            <div className="flex items-start gap-2.5 rounded-[10px] bg-warning/12 px-3.5 py-2.5 text-[13px]">
              <Info className="mt-0.5 size-4 shrink-0" aria-hidden />
              Pulverização exige a aprovação de um agrônomo e o tanque carregado exatamente com este produto e lote. A
              segurança confere os dois antes de assinar a missão.
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <FormField label="Produto" hint={field ? `Só os autorizados para ${crop(field.crop).toLowerCase()}.` : undefined}>
                <select
                  className="input"
                  value={productId}
                  onChange={(event) => {
                    setProductId(event.target.value)
                    setBatchId('')
                  }}
                >
                  <option value="">Escolha</option>
                  {compatible.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.name}
                    </option>
                  ))}
                </select>
              </FormField>
              <FormField label="Lote">
                <select className="input" value={batchId} onChange={(event) => setBatchId(event.target.value)} disabled={!productId}>
                  <option value="">Escolha</option>
                  {batches.data?.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.code}
                      {item.expires_on ? ` · vence ${item.expires_on}` : ''}
                    </option>
                  ))}
                </select>
              </FormField>
              <FormField label="Tanque">
                <select className="input" value={tankId} onChange={(event) => setTankId(event.target.value)} disabled={!deviceId}>
                  <option value="">Escolha</option>
                  {tanks.data?.map((item) => (
                    <option key={item.id} value={item.id}>
                      Tanque {item.index + 1} · {item.current_level_l} L
                    </option>
                  ))}
                </select>
              </FormField>
              <div className="grid grid-cols-2 gap-3">
                <FormField
                  label="Dose (L/ha)"
                  hint={product?.min_rate_l_ha != null ? `Bula: ${product.min_rate_l_ha}–${product.max_rate_l_ha ?? '?'}` : undefined}
                >
                  <input className="input num" type="number" min="0" step="0.05" value={rate} onChange={(event) => setRate(event.target.value)} />
                </FormField>
                <FormField label="Volume máximo (L)" hint="É teto, não meta.">
                  <input className="input num" type="number" min="0" step="0.5" value={quantity} onChange={(event) => setQuantity(event.target.value)} />
                </FormField>
              </div>
            </div>
          </>
        )}

        <ErrorBox error={create.error} />
      </div>
    </Modal>
  )
}
