import { BatteryMedium, Bot, Check, Copy, KeyRound, Plane, Plus, Warehouse } from 'lucide-react'
import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'

import { api } from '@/api/client'
import { keys, useApiMutation, useDeviceModels, useDevices, useFarms } from '@/api/queries'
import type { DeviceOut, ProvisioningTokenOut } from '@/api/types'
import { useAuth } from '@/auth/AuthProvider'
import { Badge, Button, Card, Empty, ErrorBox, FormField, Meter, Modal, PageHeader, Skeleton, Tabs } from '@/components/ui'
import { fmt } from '@/lib/format'
import {
  connectivity,
  connectivityTone,
  deviceKind,
  deviceStatus,
  deviceStatusTone,
  type Tone,
} from '@/lib/labels'

type Filter = 'all' | 'rover' | 'drone' | 'dock'

export const KIND_ICON = { rover: Bot, drone: Plane, dock: Warehouse, sensor: Bot, gateway: Bot } as const

export function batteryTone(value: number | null | undefined): Tone {
  if (value == null) return 'neutral'
  if (value < 20) return 'critical'
  if (value < 35) return 'warning'
  return 'good'
}

export default function Fleet() {
  const { can } = useAuth()
  const devices = useDevices()
  const [filter, setFilter] = useState<Filter>('all')
  const [provisioning, setProvisioning] = useState(false)

  const rows = devices.data ?? []
  const visible = filter === 'all' ? rows : rows.filter((device) => device.kind === filter)
  const count = (kind: Filter) => (kind === 'all' ? rows.length : rows.filter((device) => device.kind === kind).length)

  return (
    <>
      <PageHeader
        title="Frota"
        subtitle="Cada robô tem identidade própria: gera o seu par de chaves no primeiro boot e só a chave pública sai dele."
        actions={
          can('device:provision') && (
            <Button variant="primary" icon={<Plus className="size-4" />} onClick={() => setProvisioning(true)}>
              Provisionar dispositivo
            </Button>
          )
        }
      />

      <div className="mb-4">
        <Tabs<Filter>
          value={filter}
          onChange={setFilter}
          items={[
            { value: 'all', label: 'Todos', count: count('all') },
            { value: 'rover', label: 'Rovers', count: count('rover') },
            { value: 'drone', label: 'Drones', count: count('drone') },
            { value: 'dock', label: 'Bases', count: count('dock') },
          ]}
        />
      </div>

      <ErrorBox error={devices.error} className="mb-4" />

      {devices.isLoading && (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 3 }, (_, index) => (
            <Skeleton key={index} className="h-44" />
          ))}
        </div>
      )}

      {!devices.isLoading && visible.length === 0 && (
        <Card>
          <Empty
            title="Nenhum dispositivo aqui ainda"
            action={
              can('device:provision') && (
                <Button variant="primary" onClick={() => setProvisioning(true)}>
                  Provisionar o primeiro
                </Button>
              )
            }
          >
            O técnico gera um convite de uso único, grava no robô, e o robô entra na frota no primeiro contato.
          </Empty>
        </Card>
      )}

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {visible.map((device) => (
          <DeviceCard key={device.id} device={device} />
        ))}
      </div>

      <ProvisionModal open={provisioning} onClose={() => setProvisioning(false)} />
    </>
  )
}

function DeviceCard({ device }: { device: DeviceOut }) {
  const Icon = KIND_ICON[device.kind] ?? Bot
  return (
    <Link to={`/frota/${device.id}`} className="card flex flex-col gap-4 p-4 transition-colors hover:border-accent/50">
      <div className="flex items-start gap-3">
        <span className="grid size-10 shrink-0 place-items-center rounded-[10px] bg-accent-soft">
          <Icon className="size-5" aria-hidden />
        </span>
        <div className="min-w-0 flex-1">
          <div className="truncate font-medium">{device.name}</div>
          <div className="num truncate text-[12px] text-muted">
            {deviceKind(device.kind)} · {device.serial_number}
          </div>
        </div>
        <Badge tone={connectivityTone(device.connectivity)} pulse={device.connectivity === 'ok'}>
          {connectivity(device.connectivity)}
        </Badge>
      </div>

      {device.kind !== 'dock' && (
        <div>
          <div className="mb-1.5 flex items-center justify-between text-[12px] text-ink-2">
            <span className="flex items-center gap-1.5">
              <BatteryMedium className="size-4" aria-hidden /> Bateria
            </span>
            <span className="num font-medium text-ink">
              {device.battery_percent != null ? `${fmt.number(device.battery_percent)}%` : '—'}
            </span>
          </div>
          <Meter value={(device.battery_percent ?? 0) / 100} tone={batteryTone(device.battery_percent)} label="Bateria" />
        </div>
      )}

      <div className="mt-auto flex flex-wrap items-center justify-between gap-2 text-[12px] text-muted">
        <Badge tone={deviceStatusTone(device.status)}>{deviceStatus(device.status)}</Badge>
        <span>visto {fmt.ago(device.last_seen_at)}</span>
      </div>
      {device.active_mission_id && (
        <div className="-mt-1 text-[12px] font-medium text-ink-2">Em missão · {fmt.shortId(device.active_mission_id)}</div>
      )}
    </Link>
  )
}

function ProvisionModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const models = useDeviceModels()
  const farms = useFarms()
  const [model, setModel] = useState('')
  const [serial, setSerial] = useState('')
  const [farm, setFarm] = useState('')
  const [issued, setIssued] = useState<ProvisioningTokenOut | null>(null)
  const [copied, setCopied] = useState(false)

  const create = useApiMutation(
    () =>
      api<ProvisioningTokenOut>('/v1/provisioning-tokens', {
        method: 'POST',
        body: {
          device_model_code: model,
          serial_number: serial.trim() || null,
          farm_id: farm || null,
          ttl_hours: 72,
        },
      }),
    [['devices'], keys.dashboard],
  )

  const firstModel = models.data?.[0]?.code ?? ''
  const selectedModel = model || firstModel
  const snippet = useMemo(
    () =>
      issued
        ? `POST /v1/device/provision
{
  "provisioning_token": "${issued.token}",
  "serial_number": "${issued.serial_number ?? '<número de série>'}",
  "public_key": "<Ed25519 gerada no robô, 64 hex>"
}`
        : '',
    [issued],
  )

  const close = () => {
    setIssued(null)
    setSerial('')
    setCopied(false)
    create.reset()
    onClose()
  }

  return (
    <Modal
      open={open}
      onClose={close}
      title={issued ? 'Convite gerado' : 'Provisionar dispositivo'}
      description={
        issued
          ? 'Grave este convite no robô. Ele aparece uma única vez e serve para um único provisionamento.'
          : 'Gera um convite de uso único. O robô o troca por uma identidade permanente no primeiro contato.'
      }
      footer={
        issued ? (
          <Button variant="primary" onClick={close}>
            Concluir
          </Button>
        ) : (
          <>
            <Button onClick={close}>Cancelar</Button>
            <Button
              variant="primary"
              loading={create.isPending}
              disabled={!selectedModel}
              onClick={() => {
                if (!model) setModel(selectedModel)
                create.mutate(undefined, { onSuccess: (token) => setIssued(token) })
              }}
              icon={<KeyRound className="size-4" />}
            >
              Gerar convite
            </Button>
          </>
        )
      }
    >
      {issued ? (
        <div className="flex flex-col gap-4">
          <div className="rounded-[10px] border border-line bg-sunken p-3">
            <div className="mb-1 text-[12px] text-muted">Convite ({issued.device_model_code})</div>
            <div className="num font-mono text-[13px] break-all">{issued.token}</div>
          </div>
          <Button
            icon={copied ? <Check className="size-4" /> : <Copy className="size-4" />}
            onClick={() => {
              void navigator.clipboard.writeText(issued.token).then(() => setCopied(true))
            }}
          >
            {copied ? 'Copiado' : 'Copiar convite'}
          </Button>
          <div className="text-[12px] text-ink-2">
            Vence em {fmt.dateTime(issued.expires_at)}. O que o firmware envia no primeiro boot:
          </div>
          <pre className="overflow-x-auto rounded-[10px] bg-sunken p-3 font-mono text-[12px]">{snippet}</pre>
        </div>
      ) : (
        <div className="flex flex-col gap-4">
          <FormField label="Modelo de hardware">
            <select className="input" value={selectedModel} onChange={(event) => setModel(event.target.value)}>
              {models.data?.map((item) => (
                <option key={item.code} value={item.code}>
                  {item.name} ({item.code})
                </option>
              ))}
            </select>
          </FormField>
          <FormField
            label="Número de série"
            hint="Recomendado: amarra o convite a este robô. Um convite roubado não serve para outro."
          >
            <input className="input num" value={serial} onChange={(event) => setSerial(event.target.value)} placeholder="VTX-ROVER-0002" />
          </FormField>
          <FormField label="Fazenda" hint="A base só fornece o vento para as missões da mesma fazenda.">
            <select className="input" value={farm} onChange={(event) => setFarm(event.target.value)}>
              <option value="">Sem fazenda por enquanto</option>
              {farms.data?.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
          </FormField>
          <ErrorBox error={create.error} />
        </div>
      )}
    </Modal>
  )
}
