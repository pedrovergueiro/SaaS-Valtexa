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
  useMissionReport,
  useEditRoute,
  useMissionSafety,
  useReplanRoute,
  useProducts,
  useSegments,
  useTanks,
  useUsers,
  type MissionAction,
} from '@/api/queries'
import type { MissionOut, MissionSegmentOut, SafetyEvaluationOut } from '@/api/types'
import { useAuth } from '@/auth/AuthProvider'
import { FarmMap } from '@/components/FarmMap'
import { Badge, Button, Card, CardHeader, Empty, ErrorBox, FormField, Meter, Modal, PageHeader, Spinner, useToast } from '@/components/ui'
import { fmt } from '@/lib/format'
import { ACTIVE_MISSION_STATES, missionKind, missionState, missionStateTone, safetyCheck } from '@/lib/labels'
import { incidenceText, outcomeLabel, plantStatusLabel, plantStatusTone, sortOccurrences, trend } from '@/lib/missionReport'

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

          {data.kind === 'scout' && <MissionResultCard missionId={data.id} />}

          <RouteEditor mission={data} segments={segments.data ?? []} />

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

/** Estados em que a rota ainda se mexe. Espelha `EDITABLE_STATES` no servidor. */
const ROTA_EDITAVEL = new Set(['draft', 'pending_safety', 'blocked'])

/**
 * Corrigir a rota antes de mandar o robô.
 *
 * Até aqui a validação humana era aprovar ou recusar. Quem opera sabe coisas
 * que o planejador não sabe — que aquela cabeceira atola em maio, que o portão
 * do fundo está trancado — e esse conhecimento não tinha por onde entrar.
 *
 * Dois caminhos, porque são duas situações diferentes. **Recalcular** é para
 * quando mudou uma premissa (a faixa, o ângulo das linhas, a folga do
 * obstáculo) ou quando a leitura de terreno chegou depois da missão ter sido
 * criada — o caso mais comum, e o menos óbvio. **Remover passadas** é para
 * quando a premissa está certa e um pedaço específico é que não serve.
 *
 * O servidor recusa rota que saia da área ou atravesse obstáculo, então o que
 * esta tela precisa fazer é mostrar a recusa, não repeti-la: duplicar a
 * validação aqui criaria duas regras para divergirem.
 */
function RouteEditor({ mission, segments }: { mission: MissionOut; segments: MissionSegmentOut[] }) {
  const { can } = useAuth()
  const toast = useToast()
  const editar = useEditRoute(mission.id)
  const recalcular = useReplanRoute(mission.id)
  const [fora, setFora] = useState<Set<number>>(new Set())
  const [faixa, setFaixa] = useState('')
  const [azimute, setAzimute] = useState('')
  const [folga, setFolga] = useState('')

  if (!can('mission:create')) return null
  if (!ROTA_EDITAVEL.has(mission.state)) {
    // Depois de autorizada, a assinatura cobre um percurso específico. Dizer
    // isso é melhor do que sumir com o cartão: quem procurou a correção precisa
    // saber que ela existe e por que não está aqui agora.
    return (
      <Card>
        <CardHeader title="Rota" subtitle="Já não se corrige nesta missão." />
        <p className="px-5 pb-5 text-[13px] text-muted">
          A partir da autorização, a assinatura cobre um percurso específico — trocá-lo por baixo
          faria o robô executar o que ninguém aprovou. Para mudar, aborte esta missão e crie outra.
        </p>
      </Card>
    )
  }

  const plano = mission.plan as Record<string, unknown>
  const desenhada = plano.route_source === 'manual'

  function alterna(indice: number) {
    setFora((atual) => {
      const novo = new Set(atual)
      if (novo.has(indice)) novo.delete(indice)
      else novo.add(indice)
      return novo
    })
  }

  async function aplicarRemocao() {
    const legs = segments.filter((_, i) => !fora.has(i)).map((s) => s.path as number[][])
    const resposta = await editar.mutateAsync({
      legs,
      reason: `${fora.size} passada(s) removida(s) pelo operador.`,
    })
    setFora(new Set())
    toast.push({
      tone: 'good',
      title: 'Rota corrigida.',
      detail: `${resposta.plan.segments} passada(s), ${fmt.meters(Number(resposta.plan.path_length_m))}.`,
    })
  }

  async function aplicarRecalculo() {
    const resposta = await recalcular.mutateAsync({
      swath_m: faixa ? Number(faixa) : null,
      row_azimuth_deg: azimute ? Number(azimute) : null,
      obstacle_margin_m: folga ? Number(folga) : null,
    })
    toast.push({
      tone: 'good',
      title: 'Rota recalculada.',
      detail: `${resposta.plan.segments} passada(s), ${Number(resposta.plan.avoided ?? 0)} obstáculo(s) contornado(s).`,
    })
  }

  return (
    <Card>
      <CardHeader
        title="Corrigir a rota"
        subtitle={
          desenhada
            ? 'Esta rota foi desenhada à mão — o tempo estimado herdou o cálculo anterior.'
            : 'O planejador não conhece o terreno todo. Quem opera, sim.'
        }
      />
      <div className="space-y-5 px-5 pb-5">
        <ErrorBox error={editar.error ?? recalcular.error} />

        <div>
          <div className="mb-2 text-[13px] font-medium">Recalcular pela máquina</div>
          <p className="mb-3 text-[12px] text-muted">
            Sem preencher nada, refaz a rota aplicando a leitura de terreno do talhão — é como se
            faz a mata entrar na conta quando a leitura chegou depois da missão.
          </p>
          <div className="grid gap-3 sm:grid-cols-3">
            <FormField label="Faixa (m)" hint="Largura que a câmera cobre.">
              <input className="input num" inputMode="decimal" placeholder={String(plano.swath_m ?? '')} value={faixa} onChange={(e) => setFaixa(e.target.value)} />
            </FormField>
            <FormField label="Linhas (°)" hint="0 = norte-sul · 90 = leste-oeste">
              <input className="input num" inputMode="decimal" placeholder={String(plano.row_azimuth_deg ?? '')} value={azimute} onChange={(e) => setAzimute(e.target.value)} />
            </FormField>
            <FormField label="Folga do obstáculo (m)" hint="Aumente se o rover raspou.">
              <input className="input num" inputMode="decimal" placeholder={String(plano.obstacle_margin_m ?? 0)} value={folga} onChange={(e) => setFolga(e.target.value)} />
            </FormField>
          </div>
          <Button className="mt-3" disabled={recalcular.isPending} onClick={aplicarRecalculo}>
            {recalcular.isPending ? 'Recalculando…' : 'Recalcular rota'}
          </Button>
        </div>

        <div className="border-t border-line-soft pt-4">
          <div className="mb-2 text-[13px] font-medium">Remover passadas</div>
          <p className="mb-3 text-[12px] text-muted">
            Marque o que não deve ser percorrido. O percurso e a energia são recalculados no
            servidor a partir do que sobrar.
          </p>
          <div className="flex max-h-44 flex-wrap gap-1.5 overflow-y-auto">
            {segments.map((segmento, indice) => (
              <button
                key={`${segmento.index}-${indice}`}
                type="button"
                onClick={() => alterna(indice)}
                aria-pressed={fora.has(indice)}
                className={
                  fora.has(indice)
                    ? 'num rounded border border-danger/40 bg-danger/10 px-2 py-1 text-[12px] text-danger line-through'
                    : 'num rounded border border-line-soft px-2 py-1 text-[12px] hover:border-accent'
                }
              >
                {indice + 1}
              </button>
            ))}
          </div>
          <div className="mt-3 flex items-center gap-3">
            <Button
              variant="danger"
              disabled={fora.size === 0 || fora.size >= segments.length || editar.isPending}
              onClick={aplicarRemocao}
            >
              {editar.isPending ? 'Aplicando…' : `Remover ${fora.size || ''}`.trim()}
            </Button>
            {fora.size >= segments.length && segments.length > 0 && (
              <span className="text-[12px] text-warning">
                Tirar todas deixaria a missão sem rota. Aborte-a, em vez disso.
              </span>
            )}
          </div>
        </div>
      </div>
    </Card>
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


/** O que o Rover viu e o que a plataforma concluiu (Edge AI + IA de nuvem, por planta). */
function MissionResultCard({ missionId }: { missionId: string }) {
  const report = useMissionReport(missionId)
  if (report.isLoading) return null
  if (report.error || !report.data) return null
  const r = report.data
  const comparacao = r.comparison_with_previous
  const tendencia = trend(comparacao?.delta ?? null)
  const ocorrencias = sortOccurrences(r.occurrences)
  return (
    <Card>
      <CardHeader
        title="Resultado da missão"
        subtitle={`${fmt.number(r.images_processed, 0)} imagens analisadas no robô · ${r.plants_seen} plantas vistas`}
        actions={
          <span className="flex items-center gap-2">
            {r.simulated && <Badge tone="warning">simulação</Badge>}
            <Link to={`/missoes/${missionId}/relatorio`}>
              <Button size="sm">Relatório completo</Button>
            </Link>
            <Link to={`/mapa?modo=missao&missao=${missionId}`}>
              <Button size="sm" variant="ghost">
                No mapa
              </Button>
            </Link>
          </span>
        }
      />
      <div className="flex flex-col gap-4 px-5 pb-5 text-[13px]">
        <div>
          <div className="text-muted">Incidência</div>
          <div className="num text-[15px]">{incidenceText(r)}</div>
          {comparacao && (
            <div className="mt-1 flex flex-wrap items-center gap-2">
              <Badge tone={tendencia.tone}>{tendencia.text}</Badge>
              <span className="text-muted">
                em relação à passada anterior
                {comparacao.recovered.length > 0 && ` · ${comparacao.recovered.length} recuperada(s)`}
                {comparacao.new.length > 0 && ` · ${comparacao.new.length} nova(s)`}
              </span>
            </div>
          )}
        </div>
        {ocorrencias.length === 0 ? (
          <Empty title="Nenhuma ocorrência nesta passada" />
        ) : (
          <ul className="divide-y divide-line rounded-md border border-line">
            {ocorrencias.slice(0, 20).map((p) => (
              <li key={p.plant_id} className="flex flex-wrap items-center gap-2 px-3 py-2">
                <span className="num font-medium">{p.plant_id}</span>
                <Badge tone={plantStatusTone(p.status)}>{plantStatusLabel(p.status)}</Badge>
                {p.label && <span className="text-ink-2">{p.label}</span>}
                <span className="ml-auto text-[12px] text-muted">
                  {p.frames} quadro(s) · {p.cameras.length} câmera(s)
                </span>
              </li>
            ))}
          </ul>
        )}
        {r.recommendations.length > 0 && (
          <div>
            <div className="text-muted">Recomendações</div>
            <ul className="mt-1 flex flex-col gap-1">
              {r.recommendations.slice(0, 5).map((d) => (
                <li key={d.decision_id}>
                  <span className="font-medium">{outcomeLabel(d.outcome)}</span>
                  {d.rationale && <span className="text-ink-2"> — {d.rationale}</span>}
                </li>
              ))}
            </ul>
          </div>
        )}
        {r.prescriptions.length > 0 && (
          <div>
            <div className="text-muted">Prescrição</div>
            {r.prescriptions.map((p) => (
              <Link key={p.mission_id} to={`/missoes/${p.mission_id}`} className="block text-accent hover:underline">
                Pulverização {fmt.shortId(p.mission_id)} · {missionState(p.state)}
                {p.rate_l_ha != null && ` · ${fmt.number(p.rate_l_ha, 2)} L/ha`}
              </Link>
            ))}
          </div>
        )}
      </div>
    </Card>
  )
}
