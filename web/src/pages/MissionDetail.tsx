import { ArrowLeft, CheckCircle2, CircleSlash, Play, RotateCcw, Send, ShieldCheck, Square, XCircle } from 'lucide-react'
import { useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import {
  useBatches,
  useCheckpoints,
  useDevices,
  useFields,
  useMission,
  useMissionAction,
  useMissionHistory,
  useMissionSafety,
  useProducts,
  useSegments,
  useTanks,
  useUsers,
  type MissionAction,
} from '@/api/queries'
import type { MissionOut, SafetyEvaluationOut } from '@/api/types'
import { useAuth } from '@/auth/AuthProvider'
import { FarmMap } from '@/components/FarmMap'
import { Badge, Button, Card, CardHeader, Empty, ErrorBox, FormField, Meter, Modal, PageHeader, Spinner } from '@/components/ui'
import { fmt } from '@/lib/format'
import { ACTIVE_MISSION_STATES, missionKind, missionState, missionStateTone, safetyCheck } from '@/lib/labels'

const TERMINAL = new Set(['completed', 'aborted', 'expired'])

export default function MissionDetail() {
  const { id = '' } = useParams()
  const mission = useMission(id)
  const segments = useSegments(id)
  const safety = useMissionSafety(id)
  const history = useMissionHistory(id)
  const checkpoints = useCheckpoints(id)
  const fields = useFields()
  const devices = useDevices()

  if (mission.isLoading) return <Spinner />
  if (mission.error || !mission.data) return <ErrorBox error={mission.error ?? new Error('Missão não encontrada')} />
  const data = mission.data
  const field = fields.data?.find((item) => item.id === data.field_id)
  const device = devices.data?.find((item) => item.id === data.device_id)
  const latest = safety.data?.[0]
  const plan = data.plan as Record<string, number | undefined>

  return (
    <>
      <Link to="/missoes" className="mb-3 inline-flex items-center gap-1.5 text-[13px] text-muted hover:text-ink">
        <ArrowLeft className="size-4" aria-hidden /> Missões
      </Link>
      <PageHeader
        eyebrow={<span className="num">missão {fmt.shortId(data.id)}</span>}
        title={`${missionKind(data.kind)} · ${field?.name ?? 'talhão'}`}
        subtitle={`${device?.name ?? 'dispositivo'} · criada ${fmt.ago(data.created_at)}${data.expires_at ? ` · válida até ${fmt.dateTime(data.expires_at)}` : ''}`}
        actions={
          <>
            <Badge tone={missionStateTone(data.state)} pulse={data.state === 'running'}>
              {missionState(data.state)}
            </Badge>
            <MissionActions mission={data} />
          </>
        }
      />

      <div className="grid gap-4 xl:grid-cols-[1.5fr_1fr]">
        <div className="flex flex-col gap-4">
          <Card className="overflow-hidden">
            <CardHeader
              title="Área e percurso"
              subtitle={`${data.segments_done} de ${data.segments_total} faixas concluídas`}
            />
            <div className="px-5 pb-4">
              <FarmMap
                fields={field ? [field] : []}
                missionPolygon={data.target_polygon}
                segments={segments.data}
                devices={device ? [device] : []}
                className="h-[26rem]"
              />
              <div className="mt-3 flex items-center gap-3">
                <Meter value={data.segments_total ? data.segments_done / data.segments_total : 0} label="Progresso" />
                <span className="num text-[12px] text-muted">
                  {fmt.percent(data.segments_total ? data.segments_done / data.segments_total : 0)}
                </span>
              </div>
            </div>
          </Card>

          <Card>
            <CardHeader title="Linha do tempo" subtitle="Toda transição, com quem fez e por quê." />
            {history.data?.length === 0 && <Empty title="Sem registros" />}
            <ol className="relative px-5 pb-5">
              {history.data?.map((entry, index) => (
                <li key={`${entry.at}-${index}`} className="relative border-l border-line pb-4 pl-5 last:pb-0">
                  <span className="absolute top-1 -left-[5px] size-2.5 rounded-full border-2 border-surface bg-accent" />
                  <div className="flex flex-wrap items-center gap-2 text-[13px]">
                    {entry.new_state ? (
                      <Badge tone={missionStateTone(entry.new_state)}>{missionState(entry.new_state)}</Badge>
                    ) : (
                      <span className="font-medium">{entry.action}</span>
                    )}
                    <span className="text-[12px] text-muted">
                      {fmt.dateTime(entry.at)} · {entry.actor_type === 'device' ? 'robô' : entry.actor_type === 'user' ? entry.actor ?? 'usuário' : 'sistema'}
                    </span>
                  </div>
                  {entry.reason && <p className="mt-1 text-[13px] text-ink-2">{entry.reason}</p>}
                </li>
              ))}
            </ol>
          </Card>
        </div>

        <div className="flex flex-col gap-4">
          <SafetyCard evaluation={latest} total={safety.data?.length ?? 0} />
          {data.kind === 'spray' && <SprayCard mission={data} />}

          <Card>
            <CardHeader title="Plano" />
            <dl className="grid grid-cols-2 gap-x-4 gap-y-2.5 px-5 pb-5 text-[13px]">
              <dt className="text-muted">Área</dt>
              <dd className="num">{fmt.hectares(plan.area_ha)}</dd>
              <dt className="text-muted">Percurso</dt>
              <dd className="num">{fmt.meters(plan.path_length_m)}</dd>
              <dt className="text-muted">Faixa</dt>
              <dd className="num">{plan.swath_m != null ? `${fmt.number(plan.swath_m, 1)} m` : '—'}</dd>
              <dt className="text-muted">Linhas</dt>
              <dd className="num">{plan.row_azimuth_deg != null ? `${fmt.number(plan.row_azimuth_deg)}° do norte` : '—'}</dd>
              <dt className="text-muted">Volta com</dt>
              <dd className="num">
                {data.energy_policy.abort_below_percent != null ? `${fmt.number(Number(data.energy_policy.abort_below_percent), 0)}% de bateria` : '—'}
              </dd>
              <dt className="text-muted">Sem enlace</dt>
              <dd>{data.offline_policy.on_link_loss === 'pause' ? 'pausa e fecha o bico' : data.offline_policy.on_link_loss ? 'continua' : '—'}</dd>
            </dl>
          </Card>

          {(checkpoints.data?.length ?? 0) > 0 && (
            <Card>
              <CardHeader title="Checkpoints" subtitle="O que permite retomar de onde parou." />
              <ul className="px-5 pb-5 text-[13px]">
                {checkpoints.data?.slice(-6).reverse().map((row, index) => (
                  <li key={`${row.created_at}-${index}`} className="flex items-center justify-between border-t border-line-soft py-2 first:border-0">
                    <span>
                      {row.reason === 'low_battery' ? 'Pausa para recarga' : `Faixa ${row.last_completed_segment + 1} concluída`}
                      <span className="block text-[12px] text-muted">{row.remaining_segments} restante(s)</span>
                    </span>
                    <span className="num text-right text-[12px] text-muted">
                      {row.battery_percent != null ? `${fmt.number(row.battery_percent)}%` : ''}
                      <span className="block">{fmt.time(row.created_at)}</span>
                    </span>
                  </li>
                ))}
              </ul>
            </Card>
          )}
        </div>
      </div>
    </>
  )
}

function SafetyCard({ evaluation, total }: { evaluation: SafetyEvaluationOut | undefined; total: number }) {
  if (!evaluation) {
    return (
      <Card>
        <CardHeader title="Camada de segurança" />
        <Empty title="Ainda não avaliada" icon={<ShieldCheck className="size-5" />}>
          Antes de ir ao robô, a missão passa por verificações independentes: área, hardware, bateria, e na
          pulverização, aprovação, produto, lote, tanque e vento.
        </Empty>
      </Card>
    )
  }
  const failed = evaluation.checks.filter((check) => !check.passed)
  const passed = evaluation.checks.filter((check) => check.passed)

  return (
    <Card>
      <CardHeader
        title="Camada de segurança"
        subtitle={`${fmt.dateTime(evaluation.created_at)} · ${total} avaliação(ões) · motor ${evaluation.engine_version}`}
        actions={
          evaluation.verdict === 'safe_to_execute' ? <Badge tone="good">Liberada</Badge> : <Badge tone="critical">Bloqueada</Badge>
        }
      />
      <ul className="px-5 pb-5">
        {[...failed, ...passed].map((check) => (
          <li key={check.code} className="flex items-start gap-2.5 border-t border-line-soft py-2.5 first:border-0 first:pt-0">
            {check.passed ? (
              <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-good" aria-label="Passou" />
            ) : (
              <XCircle className="mt-0.5 size-4 shrink-0 text-critical" aria-label="Bloqueou" />
            )}
            <span className="min-w-0 text-[13px]">
              <span className="font-medium">{safetyCheck(check.code)}</span>
              <span className="block text-[12px] text-ink-2">{check.detail}</span>
            </span>
          </li>
        ))}
      </ul>
    </Card>
  )
}

function SprayCard({ mission }: { mission: MissionOut }) {
  const products = useProducts()
  const batches = useBatches(mission.product_id ?? undefined)
  const tanks = useTanks({ device_id: mission.device_id })
  const users = useUsers()
  const product = products.data?.find((item) => item.id === mission.product_id)
  const tank = tanks.data?.find((item) => item.id === mission.tank_id)
  const approver = users.data?.find((item) => item.id === mission.approved_by)
  const matches = Boolean(tank && tank.loaded_product_id === mission.product_id)

  return (
    <Card>
      <CardHeader
        title="Aplicação"
        actions={mission.approved_by ? <Badge tone="good">Aprovada</Badge> : <Badge tone="warning">Aguardando agrônomo</Badge>}
      />
      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2.5 px-5 pb-5 text-[13px]">
        <dt className="text-muted">Produto</dt>
        <dd>{product?.name ?? '—'}</dd>
        <dt className="text-muted">Lote</dt>
        <dd className="num">{batches.data?.find((item) => item.id === mission.product_batch_id)?.code ?? '—'}</dd>
        <dt className="text-muted">Dose</dt>
        <dd className="num">{mission.authorized_rate_l_ha != null ? `${fmt.number(mission.authorized_rate_l_ha, 2)} L/ha` : '—'}</dd>
        <dt className="text-muted">Volume máximo</dt>
        <dd className="num">{fmt.liters(mission.authorized_quantity_l)}</dd>
        <dt className="text-muted">Tanque</dt>
        <dd>
          {tank ? `Tanque ${tank.index + 1} · ${fmt.number(tank.current_level_l, 1)} L` : '—'}
          {tank && (
            <span className={matches ? 'block text-[12px] text-ink-2' : 'block text-[12px] font-medium text-critical'}>
              {matches ? 'conteúdo confere com o autorizado' : 'conteúdo diferente do autorizado'}
            </span>
          )}
        </dd>
        <dt className="text-muted">Aprovação</dt>
        <dd>{approver ? `${approver.full_name} · ${fmt.dateTime(mission.approved_at)}` : 'pendente'}</dd>
      </dl>
    </Card>
  )
}

function MissionActions({ mission }: { mission: MissionOut }) {
  const { can } = useAuth()
  const action = useMissionAction(mission.id)
  const [approving, setApproving] = useState(false)
  const [aborting, setAborting] = useState(false)
  const [accept, setAccept] = useState(false)
  const [notes, setNotes] = useState('')
  const [reason, setReason] = useState('')

  const run = (name: MissionAction, body?: unknown) => action.mutate({ action: name, body })
  const busy = (name: MissionAction) => action.isPending && action.variables?.action === name

  const canAuthorize = ['draft', 'pending_safety', 'blocked'].includes(mission.state) && can('mission:dispatch')
  const canApprove = mission.kind === 'spray' && !mission.approved_by && !TERMINAL.has(mission.state) && can('mission:approve_application')
  const canDispatch = mission.state === 'authorized' && can('mission:dispatch')
  const canResume = mission.state === 'ready_to_resume' && can('mission:dispatch')
  const canAbort = !TERMINAL.has(mission.state) && can('mission:abort')

  const buttons = useMemo(
    () => ({ canAuthorize, canApprove, canDispatch, canResume, canAbort }),
    [canAuthorize, canApprove, canDispatch, canResume, canAbort],
  )

  return (
    <>
      {buttons.canApprove && (
        <Button size="sm" variant="primary" icon={<CheckCircle2 className="size-4" />} onClick={() => setApproving(true)}>
          Aprovar aplicação
        </Button>
      )}
      {buttons.canAuthorize && (
        <Button size="sm" variant={mission.kind === 'spray' && !mission.approved_by ? 'secondary' : 'primary'} icon={<ShieldCheck className="size-4" />} loading={busy('authorize')} onClick={() => run('authorize')}>
          Rodar segurança
        </Button>
      )}
      {buttons.canDispatch && (
        <Button size="sm" variant="primary" icon={<Send className="size-4" />} loading={busy('dispatch')} onClick={() => run('dispatch')}>
          Despachar ao robô
        </Button>
      )}
      {buttons.canResume && (
        <Button size="sm" variant="primary" icon={<RotateCcw className="size-4" />} loading={busy('resume')} onClick={() => run('resume')}>
          Retomar
        </Button>
      )}
      {buttons.canAbort && (
        <Button size="sm" variant="ghost" icon={ACTIVE_MISSION_STATES.has(mission.state) ? <Square className="size-4" /> : <CircleSlash className="size-4" />} onClick={() => setAborting(true)}>
          Abortar
        </Button>
      )}
      {mission.state === 'running' && (
        <span className="hidden items-center gap-1 text-[12px] text-muted sm:inline-flex">
          <Play className="size-3.5" aria-hidden /> em campo
        </span>
      )}
      {action.error && (
        <div className="basis-full">
          <ErrorBox error={action.error} />
        </div>
      )}

      <Modal
        open={approving}
        onClose={() => setApproving(false)}
        title="Aprovar a aplicação"
        description="É o ponto exato em que uma recomendação de software vira produto químico no ar. A segurança ainda confere produto, lote, tanque, área e vento depois desta aprovação."
        footer={
          <>
            <Button onClick={() => setApproving(false)}>Cancelar</Button>
            <Button
              variant="primary"
              disabled={!accept}
              loading={busy('approve')}
              onClick={() =>
                action.mutate(
                  { action: 'approve', body: { confirm: true, notes: notes || null } },
                  { onSuccess: () => setApproving(false) },
                )
              }
            >
              Assinar aprovação
            </Button>
          </>
        }
      >
        <label className="flex items-start gap-2.5 text-[13px]">
          <input type="checkbox" checked={accept} onChange={(event) => setAccept(event.target.checked)} className="mt-0.5 accent-[var(--accent)]" />
          Revisei o diagnóstico, o produto e a dose, e assumo a responsabilidade técnica por esta aplicação.
        </label>
        <FormField label="Observações (opcional)">
          <textarea className="input mt-3 min-h-20" value={notes} onChange={(event) => setNotes(event.target.value)} />
        </FormField>
      </Modal>

      <Modal
        open={aborting}
        onClose={() => setAborting(false)}
        title="Abortar a missão"
        description="Interrompe a missão. Se o robô estiver em campo, ele recebe a ordem na próxima consulta e volta pela política embarcada."
        footer={
          <>
            <Button onClick={() => setAborting(false)}>Voltar</Button>
            <Button
              variant="danger"
              disabled={reason.trim().length < 3}
              loading={busy('abort')}
              onClick={() => action.mutate({ action: 'abort', body: { reason } }, { onSuccess: () => setAborting(false) })}
            >
              Abortar
            </Button>
          </>
        }
      >
        <FormField label="Motivo" hint="Fica na linha do tempo da missão e na auditoria.">
          <input className="input" value={reason} onChange={(event) => setReason(event.target.value)} placeholder="Ex.: chuva chegando" />
        </FormField>
      </Modal>
    </>
  )
}
