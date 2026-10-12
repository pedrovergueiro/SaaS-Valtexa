import { ArrowLeft, ShieldOff } from 'lucide-react'
import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { api } from '@/api/client'
import { keys, useApiMutation, useDevice, useDeviceEvents, useFields, useTanks, useTelemetry } from '@/api/queries'
import type { DeviceOut } from '@/api/types'
import { useAuth } from '@/auth/AuthProvider'
import { TimeSeries } from '@/components/charts'
import { FarmMap } from '@/components/FarmMap'
import { Badge, Button, Card, CardHeader, Empty, ErrorBox, FormField, Meter, Modal, PageHeader, Spinner, Tabs } from '@/components/ui'
import { faultText, fleetStateTone, modelInUse, modelStatus, storageText, storageTone } from '@/lib/fleet'
import { fmt } from '@/lib/format'
import { connectivity, connectivityTone, deviceKind, deviceStatus, deviceStatusTone, severity, severityTone, tankStatus } from '@/lib/labels'
import { batteryTone } from '@/pages/Fleet'

type Window = '60' | '360' | '1440'

const CAPABILITY_LABEL: Record<string, string> = {
  has_rtk: 'RTK',
  has_camera_rgb: 'Câmera RGB',
  has_camera_multispectral: 'Multiespectral',
  has_lidar: 'LiDAR',
  has_spray: 'Pulverização',
  can_fly: 'Voa',
  can_charge: 'Recarrega',
  can_swap_battery: 'Troca bateria',
  can_refill: 'Reabastece',
  supports_offline_mission: 'Opera offline',
}

export default function DeviceDetail() {
  const { id = '' } = useParams()
  const { can } = useAuth()
  const device = useDevice(id)
  const [window, setWindow] = useState<Window>('360')
  const telemetry = useTelemetry(id, Number(window))
  const events = useDeviceEvents(id)
  const fields = useFields()
  const tanks = useTanks({ device_id: id })

  if (device.isLoading) return <Spinner />
  if (device.error || !device.data) return <ErrorBox error={device.error ?? new Error('Dispositivo não encontrado')} />
  const data = device.data
  const samples = telemetry.data ?? []
  const last = samples.at(-1)
  const capabilities = Object.entries(data.capabilities).filter(([, value]) => value === true)

  return (
    <>
      <Link to="/frota" className="mb-3 inline-flex items-center gap-1.5 text-[13px] text-muted hover:text-ink">
        <ArrowLeft className="size-4" aria-hidden /> Frota
      </Link>
      <PageHeader
        title={data.name}
        subtitle={
          <span className="num">
            {deviceKind(data.kind)} · {data.model_code} · série {data.serial_number}
          </span>
        }
        actions={
          <>
            <span title={data.fleet_state_reason}>
              <Badge tone={fleetStateTone(data.fleet_state)}>{data.fleet_state_label}</Badge>
            </span>
            <Badge tone={connectivityTone(data.connectivity)} pulse={data.connectivity === 'ok'}>
              {connectivity(data.connectivity)}
            </Badge>
            <Badge tone={deviceStatusTone(data.status)}>{deviceStatus(data.status)}</Badge>
            {can('device:manage') && <DeviceActions device={data} />}
          </>
        }
      />

      <div className="grid gap-4 xl:grid-cols-[1.6fr_1fr]">
        <div className="flex flex-col gap-4">
          <Card>
            <CardHeader
              title="Telemetria"
              subtitle={last ? `Última amostra ${fmt.ago(last.recorded_at)} · RTK ${last.rtk_fix}` : 'Sem amostras na janela'}
              actions={
                <Tabs<Window>
                  value={window}
                  onChange={setWindow}
                  items={[
                    { value: '60', label: '1 h' },
                    { value: '360', label: '6 h' },
                    { value: '1440', label: '24 h' },
                  ]}
                />
              }
            />
            <div className="grid gap-4 px-5 pb-5 lg:grid-cols-2">
              {samples.length === 0 ? (
                <div className="lg:col-span-2">
                  <Empty title="Nenhuma telemetria nesta janela">
                    O robô envia amostras enquanto está ligado. Sem enlace, ele acumula e descarrega ao voltar.
                  </Empty>
                </div>
              ) : (
                <>
                  <div>
                    <div className="mb-2 text-[13px] font-medium">Bateria (%)</div>
                    <TimeSeries
                      data={samples.map((row) => ({ at: row.recorded_at, value: row.battery_percent }))}
                      label="Bateria"
                      unit="%"
                      domain={[0, 100]}
                      threshold={{ value: 35, label: 'mínimo p/ autorizar' }}
                    />
                  </div>
                  <div>
                    <div className="mb-2 text-[13px] font-medium">Velocidade (m/s)</div>
                    <TimeSeries
                      data={samples.map((row) => ({ at: row.recorded_at, value: row.speed_ms }))}
                      label="Velocidade"
                      unit="m/s"
                    />
                  </div>
                </>
              )}
            </div>
          </Card>

          <Card className="overflow-hidden">
            <CardHeader title="Posição" subtitle={data.last_lat != null ? `${fmt.number(data.last_lat, 6)}, ${fmt.number(data.last_lon, 6)}` : 'Posição ainda desconhecida'} />
            <div className="px-5 pb-5">
              <FarmMap fields={fields.data} devices={[data]} className="h-72" />
            </div>
          </Card>
        </div>

        <div className="flex flex-col gap-4">
          <FleetHealthCard device={data} />
          <Card>
            <CardHeader title="Estado" />
            <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2.5 px-5 pb-5 text-[13px]">
              <dt className="text-muted">Bateria</dt>
              <dd>
                <div className="flex items-center gap-2">
                  <Meter value={(data.battery_percent ?? 0) / 100} tone={batteryTone(data.battery_percent)} label="Bateria" />
                  <span className="num w-10 text-right">{data.battery_percent != null ? `${fmt.number(data.battery_percent)}%` : '—'}</span>
                </div>
              </dd>
              <dt className="text-muted">Visto por último</dt>
              <dd>{fmt.dateTime(data.last_seen_at)}</dd>
              <dt className="text-muted">Firmware</dt>
              <dd className="num">{data.firmware_version ?? '—'}</dd>
              <dt className="text-muted">Protocolo</dt>
              <dd className="num">{data.protocol_version ?? '—'}</dd>
              <dt className="text-muted">Energia</dt>
              <dd>{last?.energy_state ?? '—'}</dd>
              <dt className="text-muted">Enlace</dt>
              <dd>
                {/* O robô relata a qualidade do rádio e a plataforma guardava
                    sem mostrar. É o número que separa "parou" de "sumiu": um
                    rover silencioso com último enlace em 12% estava saindo de
                    alcance; em 90%, desligou. */}
                {last?.link_quality != null ? (
                  <div className="flex items-center gap-2">
                    <Meter
                      value={Math.min(1, Math.max(0, last.link_quality))}
                      tone={last.link_quality < 0.3 ? 'critical' : last.link_quality < 0.6 ? 'warning' : 'good'}
                      label="Enlace"
                    />
                    <span className="num w-10 text-right">{fmt.percent(last.link_quality)}</span>
                  </div>
                ) : (
                  '—'
                )}
              </dd>
              <dt className="text-muted">Missão ativa</dt>
              <dd>
                {data.active_mission_id ? (
                  <Link to={`/missoes/${data.active_mission_id}`} className="font-medium hover:underline">
                    {fmt.shortId(data.active_mission_id)}
                  </Link>
                ) : (
                  'nenhuma'
                )}
              </dd>
            </dl>
            <div className="flex flex-wrap gap-1.5 border-t border-line-soft px-5 py-4">
              {capabilities.map(([key]) => (
                <span key={key} className="rounded-full bg-sunken px-2.5 py-0.5 text-[12px] text-ink-2">
                  {CAPABILITY_LABEL[key] ?? key}
                </span>
              ))}
            </div>
          </Card>

          {(tanks.data?.length ?? 0) > 0 && (
            <Card>
              <CardHeader title="Tanques" subtitle="O conteúdo declarado é o que a segurança confere antes de liberar." />
              <ul className="px-5 pb-5">
                {tanks.data?.map((tank) => (
                  <li key={tank.id} className="border-t border-line-soft py-3 first:border-0 first:pt-0">
                    <div className="flex items-center justify-between text-[13px]">
                      <span className="font-medium">Tanque {tank.index + 1}</span>
                      <span className="text-muted">{tankStatus(tank.status)}</span>
                    </div>
                    <div className="mt-2 flex items-center gap-2">
                      <Meter value={tank.capacity_l ? tank.current_level_l / tank.capacity_l : 0} tone="info" label="Nível" />
                      <span className="num w-20 text-right text-[12px]">
                        {fmt.number(tank.current_level_l, 1)}/{fmt.number(tank.capacity_l, 0)} L
                      </span>
                    </div>
                  </li>
                ))}
              </ul>
            </Card>
          )}

          <Card>
            <CardHeader title="Eventos" subtitle="Relatados pelo próprio robô" />
            {events.data?.length === 0 && <Empty title="Nenhum evento" />}
            <ul className="max-h-96 overflow-y-auto">
              {events.data?.slice(0, 30).map((event) => (
                <li key={event.id} className="flex items-start gap-3 border-t border-line-soft px-5 py-2.5">
                  <Badge tone={severityTone(event.severity)}>{severity(event.severity)}</Badge>
                  <span className="min-w-0 flex-1 text-[13px]">
                    <span className="font-medium">{event.type}</span>
                    {Object.keys(event.payload).length > 0 && (
                      <span className="block truncate text-[12px] text-muted">
                        {Object.entries(event.payload)
                          .map(([key, value]) => `${key}: ${String(value)}`)
                          .join(' · ')}
                      </span>
                    )}
                  </span>
                  <span className="shrink-0 text-[11px] text-muted">{fmt.ago(event.occurred_at)}</span>
                </li>
              ))}
            </ul>
          </Card>
        </div>
      </div>
    </>
  )
}

/**
 * O que o robô informa de si pelo protocolo (brief, seções 22 e 25): estado de frota
 * com o motivo, versões do software e do modelo, e a saúde. "sem dado" é o que o
 * robô ainda não informou — nunca um valor de exemplo.
 */
function FleetHealthCard({ device }: { device: DeviceOut }) {
  const designados = device.designated_models ?? []
  const falhas = device.active_faults ?? []
  const situacao = modelStatus(device.model_status)
  const semDado = <span className="text-muted">sem dado</span>
  return (
    <Card>
      <CardHeader title={`Frota: ${device.fleet_state_label}`} subtitle={device.fleet_state_reason} />
      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2.5 px-5 pb-4 text-[13px]">
        <dt className="text-muted">Modelo de IA</dt>
        <dd className="flex flex-wrap items-center gap-2">
          <span className="num">{modelInUse(device.ai_model_key, device.ai_model_version)}</span>
          <Badge tone={situacao.tone}>{situacao.label}</Badge>
        </dd>
        {designados.length > 0 && (
          <>
            <dt className="text-muted">Designado</dt>
            <dd className="num">{designados.join(', ').replaceAll('@', ' ')}</dd>
          </>
        )}
        <dt className="text-muted">Rover Runtime</dt>
        <dd className="num">{device.runtime_version ?? semDado}</dd>
        <dt className="text-muted">Edge AI</dt>
        <dd className="num">{device.edge_ai_version ?? semDado}</dd>
        <dt className="text-muted">dNATY</dt>
        <dd className="num">{device.dnaty_version ?? semDado}</dd>
        <dt className="text-muted">Hardware</dt>
        <dd className="num">{device.hardware_version ?? semDado}</dd>
        <dt className="text-muted">Temperatura</dt>
        <dd className="num">{device.temperature_c != null ? `${fmt.number(device.temperature_c, 1)} °C` : semDado}</dd>
        <dt className="text-muted">Armazenamento</dt>
        <dd>
          <Badge tone={storageTone(device.storage_total_bytes, device.storage_free_bytes)}>
            {storageText(device.storage_total_bytes, device.storage_free_bytes)}
          </Badge>
        </dd>
        <dt className="text-muted">Horas de operação</dt>
        <dd className="num">{device.operating_hours != null ? `${fmt.number(device.operating_hours, 1)} h` : semDado}</dd>
        <dt className="text-muted">Última sincronização</dt>
        <dd>
          {device.last_sync_at ? fmt.dateTime(device.last_sync_at) : semDado}
          {(device.sync_pending ?? 0) > 0 && <span className="ml-2 text-info">({device.sync_pending} pendentes)</span>}
        </dd>
        <dt className="text-muted">Última manutenção</dt>
        <dd>{device.last_maintenance_at ? fmt.dateTime(device.last_maintenance_at) : semDado}</dd>
        {falhas.length > 0 && (
          <>
            <dt className="text-muted">Falhas ativas</dt>
            <dd>
              <ul className="flex flex-col gap-1 text-serious">
                {falhas.map((falha, index) => (
                  <li key={index}>{faultText(falha)}</li>
                ))}
              </ul>
            </dd>
          </>
        )}
      </dl>
    </Card>
  )
}

function DeviceActions({ device }: { device: DeviceOut }) {
  const [revoking, setRevoking] = useState(false)
  const [reason, setReason] = useState('')

  const status = useApiMutation(
    (next: string) => api(`/v1/devices/${device.id}/status`, { method: 'PATCH', body: { status: next, reason: null } }),
    [['devices'], keys.alerts, keys.dashboard],
  )
  const revoke = useApiMutation(
    () => api(`/v1/devices/${device.id}/revoke-credentials`, { method: 'POST' }),
    [['devices'], keys.alerts, keys.dashboard],
  )

  return (
    <>
      <select
        className="input h-8 w-auto py-0 text-[13px]"
        value={device.status}
        onChange={(event) => status.mutate(event.target.value)}
        aria-label="Estado do dispositivo"
        disabled={status.isPending}
      >
        {['active', 'maintenance', 'suspended', 'retired'].map((value) => (
          <option key={value} value={value}>
            {deviceStatus(value)}
          </option>
        ))}
      </select>
      <Button size="sm" variant="ghost" icon={<ShieldOff className="size-4" />} onClick={() => setRevoking(true)}>
        Revogar
      </Button>
      <Modal
        open={revoking}
        onClose={() => setRevoking(false)}
        title="Revogar as credenciais"
        description="Resposta a robô roubado, perdido ou com comportamento anômalo. Toda requisição assinada com essas chaves passa a ser recusada, e voltar a operar exige provisionamento presencial."
        footer={
          <>
            <Button onClick={() => setRevoking(false)}>Cancelar</Button>
            <Button
              variant="danger"
              loading={revoke.isPending}
              disabled={reason.trim().length < 3}
              onClick={() => revoke.mutate(undefined, { onSuccess: () => setRevoking(false) })}
            >
              Revogar agora
            </Button>
          </>
        }
      >
        <FormField label="Motivo" hint="Fica registrado na auditoria.">
          <input className="input" value={reason} onChange={(event) => setReason(event.target.value)} placeholder="Ex.: rover furtado na sede" />
        </FormField>
        <ErrorBox error={revoke.error ?? status.error} className="mt-3" />
      </Modal>
    </>
  )
}
