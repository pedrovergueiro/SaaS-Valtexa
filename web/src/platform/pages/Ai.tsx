import { BrainCircuit } from 'lucide-react'
import { Fragment, useState } from 'react'

import { Badge, Button, Card, CardHeader, Empty, ErrorBox, FormField, Modal, PageHeader, Spinner, Table, Tabs, td, th } from '@/components/ui'
import { groupByModel, modelStateLabel, modelStateTone, orNoData, transitionNeedsReason } from '@/lib/fleet'
import { fmt } from '@/lib/format'
import {
  useAiHealth,
  useModelDetail,
  useModelOptimizations,
  useModelRegistry,
  useModelReleases,
  useModelTransition,
  usePlatformMe,
  usePlatformTenants,
  useRegisterOptimization,
  useReleaseModel,
  useRevokeRelease,
  type ModelVersion,
} from '@/platform/api'
import { canOptimize, dnatyBody, parseDnatyReport, type DnatyParse } from '@/lib/platformForms'

type Aba = 'registry' | 'liberacao' | 'saude'

/**
 * AI Platform no console interno (brief, seções 8, 9, 10, 22 e 34).
 *
 * Registry com o ciclo de vida, liberação por cliente e saúde da IA. As métricas
 * técnicas só aparecem aqui — o produtor vê a versão em linguagem operacional.
 * Os pesos não estão neste repositório: versão sem artefato aparece "sem dado".
 */
export default function Ai() {
  const [aba, setAba] = useState<Aba>('registry')
  const me = usePlatformMe()
  const caps = new Set(me.data?.capabilities ?? [])
  return (
    <>
      <PageHeader
        eyebrow="Console da plataforma"
        title="IA"
        subtitle="Model Registry, liberação por cliente e saúde da IA. Um robô só recebe versão em Produção daqui."
      />
      <div className="mb-4">
        <Tabs<Aba>
          value={aba}
          onChange={setAba}
          items={[
            { value: 'registry', label: 'Registry' },
            { value: 'liberacao', label: 'Liberação por cliente' },
            { value: 'saude', label: 'Saúde da IA' },
          ]}
        />
      </div>
      {aba === 'registry' && <Registry canManage={caps.has('platform:model:manage')} />}
      {aba === 'liberacao' && <Releases canRelease={caps.has('platform:model:release')} />}
      {aba === 'saude' && <AiHealthPanel />}
    </>
  )
}

function Registry({ canManage }: { canManage: boolean }) {
  const registry = useModelRegistry()
  const [aberta, setAberta] = useState<string | null>(null)
  const grupos = groupByModel(registry.data ?? [])
  return (
    <Card className="overflow-hidden p-0">
      {registry.isLoading && <Spinner />}
      <ErrorBox error={registry.error} className="m-4" />
      {registry.data?.length === 0 && (
        <Empty title="Registry vazio" icon={<BrainCircuit className="size-5" />}>
          O catálogo inicial é cadastrado no start da API.
        </Empty>
      )}
      {grupos.length > 0 && (
        <Table>
          <thead>
            <tr>
              <th className={th}>Modelo</th>
              <th className={th}>Versão</th>
              <th className={th}>Estado</th>
              <th className={th}>Culturas</th>
              <th className={th}>Métricas</th>
              <th className={th}>Artefato</th>
              <th className={th} />
            </tr>
          </thead>
          <tbody>
            {grupos.flatMap(([chave, versoes]) =>
              versoes.map((v, i) => (
                <tr key={v.id}>
                  <td className={td}>
                    {i === 0 && (
                      <>
                        <div className="font-mono text-[13px] font-medium">{chave}</div>
                        <div className="text-[12px] text-muted">{v.name ?? '—'}</div>
                      </>
                    )}
                  </td>
                  <td className={`${td} num`}>
                    {v.version}
                    {v.release_scope === 'clientes' && <div className="text-[11px] text-warning">liberação restrita</div>}
                  </td>
                  <td className={td}>
                    <Badge tone={modelStateTone(v.state)}>{modelStateLabel(v.state)}</Badge>
                  </td>
                  <td className={`${td} text-[12px]`}>{(v.crops ?? []).slice(0, 3).join(', ')}</td>
                  <td className={`${td} text-[12px]`}>
                    <Metricas versao={v} />
                  </td>
                  <td className={`${td} text-[12px]`}>
                    {v.optimized_artifact_sha256 ? (
                      <span>otimizado (dNATY {v.dnaty_version ?? 'sem dado'})</span>
                    ) : v.original_artifact_sha256 ? (
                      <span>original</span>
                    ) : (
                      <span className="text-muted">sem dado</span>
                    )}
                  </td>
                  <td className={`${td} text-right`}>
                    <Button size="sm" onClick={() => setAberta(v.id)}>
                      Abrir
                    </Button>
                  </td>
                </tr>
              )),
            )}
          </tbody>
        </Table>
      )}
      {aberta && <ModelModal id={aberta} canManage={canManage} onClose={() => setAberta(null)} />}
    </Card>
  )
}

function Metricas({ versao }: { versao: ModelVersion }) {
  const entradas = Object.entries(versao.metrics ?? {}).filter(([, v]) => typeof v === 'number')
  if (entradas.length === 0) return <span className="text-muted">sem dado</span>
  return (
    <span className="num">
      {entradas
        .slice(0, 4)
        .map(([k, v]) => `${k} ${fmt.number(v as number, 3)}`)
        .join(' · ')}
    </span>
  )
}

function ModelModal({ id, canManage, onClose }: { id: string; canManage: boolean; onClose: () => void }) {
  const detalhe = useModelDetail(id)
  const mover = useModelTransition()
  const [destino, setDestino] = useState<string | null>(null)
  const [motivo, setMotivo] = useState('')
  const v = detalhe.data
  const precisaMotivo = v && destino ? transitionNeedsReason(v.state, destino) : false
  const semDado = <span className="text-muted">sem dado</span>
  const linha = (rotulo: string, valor: React.ReactNode) => (
    <>
      <dt className="text-muted">{rotulo}</dt>
      <dd className="num break-all">{valor ?? semDado}</dd>
    </>
  )

  return (
    <Modal open onClose={onClose} wide title={v ? `${v.model_key} ${v.version}` : 'Versão'} description={v?.name ?? undefined}>
      {detalhe.isLoading && <Spinner />}
      <ErrorBox error={detalhe.error} />
      {v && (
        <div className="flex flex-col gap-4">
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone={modelStateTone(v.state)}>{modelStateLabel(v.state)}</Badge>
            {v.recommended && <Badge tone="accent">Recomendada</Badge>}
            <span className="text-[12px] text-muted">variante {v.variant}</span>
          </div>
          <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-[13px]">
            {linha('Problema', v.problem)}
            {linha('Arquitetura', v.architecture)}
            {linha('Dataset', v.dataset_ref ?? v.dataset_version_id)}
            {linha('Treinado em', v.trained_at ? fmt.date(v.trained_at) : null)}
            {linha('Tamanho', v.size_bytes != null ? `${fmt.number(v.size_bytes / 1e6, 1)} MB` : null)}
            {linha('FLOPs', v.flops != null ? fmt.number(v.flops) : null)}
            {linha('Latência', v.latency_ms != null ? `${fmt.number(v.latency_ms, 1)} ms` : null)}
            {linha('Memória', v.memory_mb != null ? `${fmt.number(v.memory_mb, 0)} MB` : null)}
            {linha('Hardware-alvo', v.target_hardware)}
            {linha('Original', v.original_artifact_sha256 ? `${v.original_artifact_uri ?? ''} · ${v.original_artifact_sha256.slice(0, 12)}…` : null)}
            {linha('Otimizado', v.optimized_artifact_sha256 ? `${v.optimized_artifact_uri ?? ''} · ${v.optimized_artifact_sha256.slice(0, 12)}…` : null)}
            {linha('Arquivos ao lado', v.extras_manifest_sha256 ? `manifesto · ${v.extras_manifest_sha256.slice(0, 12)}…` : 'sem manifesto: o robô só confere o ONNX')}
            {linha('dNATY', v.dnaty_version)}
            {linha('Licença dos dados', v.license)}
            {linha('Aprovada em', v.approved_at ? fmt.dateTime(v.approved_at) : null)}
            {linha('Publicada em', v.promoted_at ? fmt.dateTime(v.promoted_at) : null)}
            {linha('Liberada para', v.release_scope === 'todos' ? 'todos os clientes' : v.released_to?.join(', ') || 'nenhum cliente ainda')}
          </dl>
          <div className="text-[12px]">
            <div className="mb-1 font-medium">Métricas</div>
            <Metricas versao={v} />
          </div>
          {v.caveat && <div className="text-[13px] text-warning">{v.caveat}</div>}
          {v.notes && <div className="text-[12px] text-muted">{v.notes}</div>}

          <Otimizacoes id={id} canRegister={canManage && canOptimize(v.state)} />

          <div>
            <div className="mb-1 text-[13px] font-medium">Histórico</div>
            <ul className="flex flex-col gap-1 text-[12px]">
              {(v.history ?? []).map((h, i) => (
                <li key={i}>
                  {fmt.dateTime(h.at)} · {h.actor_label ?? 'sistema'} ·{' '}
                  {h.from_state ? `${modelStateLabel(h.from_state)} → ` : ''}
                  {h.to_state ? modelStateLabel(h.to_state) : h.action}
                  {h.reason && <span className="text-muted"> — {h.reason}</span>}
                </li>
              ))}
              {(v.history ?? []).length === 0 && <li className="text-muted">Sem transição registrada (catálogo inicial).</li>}
            </ul>
          </div>

          {canManage && (v.next_states ?? []).length > 0 && (
            <div className="border-t border-line-soft pt-3">
              <div className="mb-2 text-[13px] font-medium">Mover no ciclo</div>
              <div className="flex flex-wrap gap-2">
                {(v.next_states ?? []).map((s) => (
                  <Button key={s} size="sm" variant={destino === s ? 'primary' : undefined} onClick={() => setDestino(s)}>
                    {modelStateLabel(s)}
                  </Button>
                ))}
              </div>
              {destino && (
                <div className="mt-3 flex flex-col gap-2">
                  <FormField
                    label={precisaMotivo ? 'Motivo (obrigatório)' : 'Motivo (opcional)'}
                    hint="Vai para a auditoria. Aprovar exige IA & Dados e outra pessoa que não quem registrou."
                  >
                    <input className="input" value={motivo} onChange={(e) => setMotivo(e.target.value)} />
                  </FormField>
                  <div>
                    <Button
                      variant="primary"
                      loading={mover.isPending}
                      disabled={precisaMotivo && motivo.trim().length < 3}
                      onClick={() =>
                        mover.mutate(
                          { id: v.id, to: destino, reason: motivo.trim() || null },
                          { onSuccess: () => { setDestino(null); setMotivo(''); void detalhe.refetch() } },
                        )
                      }
                    >
                      Levar para {modelStateLabel(destino)}
                    </Button>
                  </div>
                  <ErrorBox error={mover.error} />
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </Modal>
  )
}

function Releases({ canRelease }: { canRelease: boolean }) {
  const clientes = usePlatformTenants()
  const registry = useModelRegistry()
  const [cliente, setCliente] = useState('')
  const [chave, setChave] = useState('')
  const [motivo, setMotivo] = useState('')
  const liberacoes = useModelReleases(cliente)
  const liberar = useReleaseModel()
  const revogar = useRevokeRelease()
  const restritos = [...new Set((registry.data ?? []).filter((v) => v.release_scope === 'clientes').map((v) => v.model_key))]
  const chaves = [...new Set((registry.data ?? []).map((v) => v.model_key))].sort()

  return (
    <div className="grid gap-4 xl:grid-cols-[1fr_1.4fr]">
      <Card>
        <CardHeader
          title="Liberar modelo"
          subtitle="Versões com liberação restrita só atendem os clientes liberados; as demais atendem todos."
        />
        <div className="flex flex-col gap-3 px-5 pb-5">
          <FormField label="Cliente">
            <select className="input" value={cliente} onChange={(e) => setCliente(e.target.value)}>
              <option value="">Escolha</option>
              {clientes.data?.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </FormField>
          <FormField label="Modelo" hint={restritos.length ? `Restritos hoje: ${restritos.join(', ')}` : 'Nenhum modelo restrito hoje.'}>
            <select className="input" value={chave} onChange={(e) => setChave(e.target.value)}>
              <option value="">Escolha</option>
              {chaves.map((k) => (
                <option key={k} value={k}>
                  {k}
                </option>
              ))}
            </select>
          </FormField>
          <FormField label="Motivo" hint="Ex.: contrato, piloto. Vai para a trilha do cliente.">
            <input className="input" value={motivo} onChange={(e) => setMotivo(e.target.value)} />
          </FormField>
          <div>
            <Button
              variant="primary"
              disabled={!canRelease || !cliente || !chave}
              loading={liberar.isPending}
              onClick={() =>
                liberar.mutate(
                  { tenant_id: cliente, model_key: chave, reason: motivo.trim() || null },
                  { onSuccess: () => setMotivo('') },
                )
              }
            >
              Liberar
            </Button>
          </div>
          <ErrorBox error={liberar.error ?? revogar.error} />
        </div>
      </Card>
      <Card className="overflow-hidden p-0">
        <CardHeader title="Liberações" subtitle={cliente ? 'Do cliente escolhido, revogadas inclusive.' : 'De todos os clientes.'} />
        {liberacoes.isLoading && <Spinner />}
        {liberacoes.data?.length === 0 && <Empty title="Nenhuma liberação">Os modelos de escopo “todos” não precisam.</Empty>}
        {(liberacoes.data?.length ?? 0) > 0 && (
          <Table>
            <thead>
              <tr>
                <th className={th}>Cliente</th>
                <th className={th}>Modelo</th>
                <th className={th}>Por</th>
                <th className={th}>Situação</th>
                <th className={th} />
              </tr>
            </thead>
            <tbody>
              {liberacoes.data?.map((l) => (
                <tr key={l.id}>
                  <td className={td}>{l.tenant_name}</td>
                  <td className={`${td} font-mono text-[13px]`}>{l.model_key}</td>
                  <td className={`${td} text-[12px]`}>
                    {l.released_by_label ?? '—'} · {fmt.date(l.created_at)}
                    {l.reason && <div className="text-muted">{l.reason}</div>}
                  </td>
                  <td className={td}>
                    {l.revoked_at ? <Badge tone="neutral">revogada {fmt.date(l.revoked_at)}</Badge> : <Badge tone="good">ativa</Badge>}
                  </td>
                  <td className={`${td} text-right`}>
                    {canRelease && !l.revoked_at && (
                      <Button size="sm" variant="ghost" loading={revogar.isPending} onClick={() => revogar.mutate(l.id)}>
                        Revogar
                      </Button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card>
    </div>
  )
}

function AiHealthPanel() {
  const saude = useAiHealth()
  const d = saude.data
  return (
    <div className="flex flex-col gap-4">
      <ErrorBox error={saude.error} />
      {saude.isLoading && <Spinner />}
      {d && (
        <>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <div className="card p-4">
              <div className="text-[13px] text-muted">Modelos em produção</div>
              <div className="font-display text-[28px] font-semibold">{d.active_models.length}</div>
            </div>
            <div className="card p-4">
              <div className="text-[13px] text-muted">Robôs informando o modelo</div>
              <div className="font-display text-[28px] font-semibold">{d.rovers_reporting}</div>
              <div className="text-[12px] text-muted">{d.rovers_without_data} sem dado</div>
            </div>
            <div className="card p-4">
              <div className="text-[13px] text-muted">Robôs com modelo diferente</div>
              <div className="font-display text-[28px] font-semibold">{d.rovers_divergent}</div>
              <div className="text-[12px] text-muted">{d.rovers_outside_registry} fora do registry</div>
            </div>
            <div className="card p-4">
              <div className="text-[13px] text-muted">Versões descontinuadas em uso</div>
              <div className="font-display text-[28px] font-semibold">{d.outdated_in_use.length}</div>
              <div className="num text-[12px] text-muted">{d.outdated_in_use.join(', ') || '—'}</div>
            </div>
          </div>

          <Card className="overflow-hidden p-0">
            <CardHeader title={`Inferências nos últimos ${d.window_days} dias`} subtitle="Medido nas detecções gravadas. Simulação aparece marcada." />
            {d.models.length === 0 ? (
              <Empty title="Sem inferência na janela">Nenhuma detecção gravada — nada a medir, nada inventado.</Empty>
            ) : (
              <Table>
                <thead>
                  <tr>
                    <th className={th}>Modelo</th>
                    <th className={th}>Inferências</th>
                    <th className={th}>Taxa de erro</th>
                    <th className={th}>Latência média / p95</th>
                    <th className={th}>Distribuição</th>
                  </tr>
                </thead>
                <tbody>
                  {d.models.map((m) => (
                    <tr key={`${m.model_key}@${m.model_version}`}>
                      <td className={td}>
                        <span className="font-mono text-[13px]">{m.model_key ?? '—'}</span>{' '}
                        <span className="num text-[12px] text-muted">{m.model_version ?? ''}</span>
                        {m.simulated && (
                          <div>
                            <Badge tone="warning">simulação</Badge>
                          </div>
                        )}
                      </td>
                      <td className={`${td} num`}>{m.inferences}</td>
                      <td className={`${td} num`}>{m.error_rate != null ? fmt.percent(m.error_rate, 1) : 'sem dado'}</td>
                      <td className={`${td} num`}>
                        {orNoData(m.latency_ms_avg, ' ms')} / {orNoData(m.latency_ms_p95, ' ms')}
                      </td>
                      <td className={`${td} text-[12px]`}>
                        {Object.entries(m.labels)
                          .map(([k, n]) => `${k} ${n}`)
                          .join(' · ') || 'sem dado'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            )}
          </Card>

          <CalibracaoCampo blocos={(d.field_calibration ?? []) as unknown as BlocoCalibracao[]} dias={d.window_days} />

          <Card>
            <CardHeader title="Sem dado" subtitle="Indicadores da seção 34 que ainda não têm fonte. Não mostramos número para eles." />
            <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 px-5 pb-5 text-[13px]">
              {Object.entries(d.no_data).map(([k, motivo]) => (
                <div key={k} className="contents">
                  <dt className="font-medium">{k.replaceAll('_', ' ')}</dt>
                  <dd className="text-ink-2">{motivo}</dd>
                </div>
              ))}
            </dl>
          </Card>
        </>
      )}
    </div>
  )
}


type Proporcao = { k: number; n: number; taxa: number | null; ic95: [number, number] | null }
type BlocoCalibracao = {
  model_key: string | null
  model_version: string | null
  revisados: number
  fora_do_catalogo: number
  acerto: Proporcao
  cobertura: Proporcao & { prometida: number | null; estado: string; tamanho_medio_do_conjunto: number | null }
  calibracao: { ece: number | null; faixas: { de: number; ate: number; n: number; confianca_media: number | null; acerto: number | null }[] }
  vies: string
}

const ESTADO_COBERTURA: Record<string, { rotulo: string; tom: 'good' | 'warning' | 'critical' | 'neutral' }> = {
  dentro: { rotulo: 'dentro da promessa', tom: 'good' },
  abaixo: { rotulo: 'abaixo da promessa', tom: 'critical' },
  poucos_dados: { rotulo: 'poucos casos', tom: 'neutral' },
  sem_promessa: { rotulo: 'sem cobertura prometida gravada', tom: 'neutral' },
}

const pct = (p: Proporcao) =>
  p.taxa == null ? 'sem dado' : `${fmt.percent(p.taxa, 1)}${p.ic95 ? ` (${fmt.percent(p.ic95[0], 0)}–${fmt.percent(p.ic95[1], 0)})` : ''} · ${p.k}/${p.n}`

/** A IA contra o rótulo confirmado pelo agrônomo: a garantia do conjunto vale no campo? */
function CalibracaoCampo({ blocos, dias }: { blocos: BlocoCalibracao[]; dias: number }) {
  return (
    <Card className="overflow-hidden p-0">
      <CardHeader
        title={`IA contra o agrônomo (${dias} dias)`}
        subtitle="Acerto, cobertura do conjunto conformal contra a prometida e calibração, nos casos confirmados na fila. Só casos difíceis vão à fila: os números são piores que a média da lavoura."
      />
      {blocos.length === 0 ? (
        <Empty title="Nenhum caso confirmado na janela">Sem rótulo do agrônomo, não há o que medir.</Empty>
      ) : (
        <Table>
          <thead>
            <tr>
              <th className={th}>Modelo</th>
              <th className={th}>Confirmados</th>
              <th className={th}>Acerto</th>
              <th className={th}>Cobertura do conjunto</th>
              <th className={th}>Calibração (ECE)</th>
            </tr>
          </thead>
          <tbody>
            {blocos.map((b) => {
              const estado = ESTADO_COBERTURA[b.cobertura.estado] ?? { rotulo: b.cobertura.estado, tom: 'neutral' as const }
              return (
                <tr key={`${b.model_key}@${b.model_version}`}>
                  <td className={td}>
                    <span className="font-mono text-[13px]">{b.model_key ?? '—'}</span>{' '}
                    <span className="num text-[12px] text-muted">{b.model_version ?? ''}</span>
                  </td>
                  <td className={`${td} num`}>
                    {b.revisados}
                    {b.fora_do_catalogo > 0 && <div className="text-[12px] text-muted">{b.fora_do_catalogo} fora do catálogo</div>}
                  </td>
                  <td className={`${td} num text-[12px]`}>{pct(b.acerto)}</td>
                  <td className={`${td} text-[12px]`}>
                    <div className="num">{pct(b.cobertura)}</div>
                    <div className="mt-1 flex flex-wrap items-center gap-1.5">
                      <Badge tone={estado.tom}>{estado.rotulo}</Badge>
                      {b.cobertura.prometida != null && <span className="text-muted">prometida {fmt.percent(b.cobertura.prometida, 0)}</span>}
                    </div>
                  </td>
                  <td className={`${td} num text-[12px]`}>
                    {b.calibracao.ece != null ? fmt.number(b.calibracao.ece, 3) : 'sem dado'}
                    <div className="text-muted">
                      {b.calibracao.faixas
                        .filter((f) => f.n > 0)
                        .map((f) => `${fmt.percent(f.de, 0)}–${fmt.percent(f.ate, 0)}: acerta ${fmt.percent(f.acerto ?? 0, 0)} (n ${f.n})`)
                        .join(' · ')}
                    </div>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </Table>
      )}
    </Card>
  )
}

/** Rodadas da etapa dNATY: original e otimizado medidos do mesmo jeito, e o veredito. */
function Otimizacoes({ id, canRegister }: { id: string; canRegister: boolean }) {
  const rodadas = useModelOptimizations(id)
  const [registrando, setRegistrando] = useState(false)
  const lista = rodadas.data ?? []
  if (!lista.length && !canRegister) return null
  const num = (b: Record<string, unknown>, k: string, casas = 3) =>
    typeof b[k] === 'number' ? fmt.number(b[k] as number, casas) : '—'
  return (
    <div>
      <div className="mb-1 flex items-center justify-between gap-2 text-[13px] font-medium">
        Otimização (dNATY e outras)
        {canRegister && !registrando && (
          <Button size="sm" onClick={() => setRegistrando(true)}>
            Registrar rodada
          </Button>
        )}
      </div>
      {registrando && <RegistrarRodada id={id} onClose={() => setRegistrando(false)} />}
      {!lista.length && !registrando && <div className="text-[12px] text-muted">Nenhuma rodada registrada.</div>}
      <ul className="flex flex-col gap-2 text-[12px]">
        {lista.map((r) => (
          <li key={r.id} className="rounded-md border border-line-soft p-2">
            <div className="flex flex-wrap items-center gap-2">
              <Badge tone={r.accepted ? 'good' : 'critical'}>{r.accepted ? 'Aceita' : 'Recusada'}</Badge>
              {r.applied && <Badge tone="accent">É o otimizado atual</Badge>}
              <span className="num">
                {r.tool} {r.tool_version ?? ''} · {fmt.dateTime(r.created_at)}
              </span>
            </div>
            <div className="num mt-1 grid grid-cols-[auto_1fr_1fr] gap-x-3">
              <span />
              <span className="text-muted">original</span>
              <span className="text-muted">otimizado</span>
              {(['f1', 'precision', 'recall'] as const).map((k) => (
                <Fragment key={k}>
                  <span className="text-muted">{k}</span>
                  <span>{num(r.original_benchmark, k)}</span>
                  <span>{num(r.optimized_benchmark, k)}</span>
                </Fragment>
              ))}
              <span className="text-muted">latência p50 (ms)</span>
              <span>{num(r.original_benchmark, 'latency_ms_p50', 2)}</span>
              <span>{num(r.optimized_benchmark, 'latency_ms_p50', 2)}</span>
              <span className="text-muted">tamanho (MB)</span>
              <span>{typeof r.original_benchmark.size_bytes === 'number' ? fmt.number((r.original_benchmark.size_bytes as number) / 1e6, 1) : '—'}</span>
              <span>{r.optimized_size_bytes != null ? fmt.number(r.optimized_size_bytes / 1e6, 1) : '—'}</span>
            </div>
            {r.reasons.length > 0 && <div className="mt-1 text-critical">{r.reasons.join(' ')}</div>}
            {r.license_note && <div className="mt-1 text-warning">{r.license_note}</div>}
          </li>
        ))}
      </ul>
    </div>
  )
}

/**
 * Registrar uma rodada a partir do relatório do `ia/training/dnaty_pipeline.py`.
 *
 * O veredito do relatório não vale: o registry recalcula com o critério. Recusada
 * também é gravada (e aparece na lista, com os motivos).
 */
function RegistrarRodada({ id, onClose }: { id: string; onClose: () => void }) {
  const registrar = useRegisterOptimization(id)
  const [lido, setLido] = useState<DnatyParse | null>(null)
  const [nome, setNome] = useState('')
  const [uriOtimizado, setUriOtimizado] = useState('')
  const [uriOriginal, setUriOriginal] = useState('')
  const corpo = lido ? dnatyBody(lido, { original: uriOriginal, otimizado: uriOtimizado }) : null
  const faltaUri = corpo ? !corpo.otimizado.artifact_uri : true

  const abrir = async (arquivo: File | undefined) => {
    if (!arquivo) return
    setNome(arquivo.name)
    const p = parseDnatyReport(await arquivo.text())
    setLido(p)
    setUriOtimizado(p.body?.otimizado.artifact_uri ?? '')
    setUriOriginal(p.body?.original.artifact_uri ?? '')
  }

  return (
    <div className="mb-3 flex flex-col gap-2 rounded-md border border-line p-3 text-[13px]" data-registrar-rodada>
      <FormField label="Relatório JSON do dnaty_pipeline.py">
        <input type="file" accept="application/json,.json" aria-label="Relatório da otimização" onChange={(e) => void abrir(e.target.files?.[0])} />
      </FormField>
      {lido && !lido.ok && (
        <ul className="text-[12px] text-critical">
          {lido.errors.map((e) => (
            <li key={e}>{e}</li>
          ))}
        </ul>
      )}
      {lido?.ok && corpo && (
        <>
          <div className="text-[12px] text-muted">
            {nome} · {corpo.tool} {corpo.tool_version ?? ''} · original {String(corpo.original.benchmark.sha256).slice(0, 12)}… → otimizado{' '}
            {String(corpo.otimizado.benchmark.sha256).slice(0, 12)}…
            {lido.reportVerdict != null && ` · o relatório dizia ${lido.reportVerdict ? 'aceito' : 'recusado'} (o registry recalcula)`}
          </div>
          <FormField label="Onde o otimizado vive (URI no armazenamento)">
            <input
              className="input"
              value={uriOtimizado}
              onChange={(e) => setUriOtimizado(e.target.value)}
              placeholder="s3://modelos/…otimizado.onnx"
              aria-label="URI do otimizado"
            />
            {lido.paths.otimizado && <span className="mt-1 block text-[12px] text-muted">No treino: {lido.paths.otimizado}</span>}
          </FormField>
          <FormField label="URI do original (só se a versão ainda não tiver)">
            <input className="input" value={uriOriginal} onChange={(e) => setUriOriginal(e.target.value)} aria-label="URI do original" />
          </FormField>
        </>
      )}
      <ErrorBox error={registrar.error} />
      {registrar.data && (
        <Badge tone={registrar.data.accepted ? 'good' : 'critical'}>
          {registrar.data.accepted ? 'Aceita: o otimizado passa a ser o da versão' : `Recusada: ${registrar.data.reasons.join(' ')}`}
        </Badge>
      )}
      <div className="flex justify-end gap-2">
        <Button variant="ghost" size="sm" onClick={onClose}>
          Fechar
        </Button>
        <Button
          variant="primary"
          size="sm"
          disabled={!lido?.ok || faltaUri || registrar.isPending || Boolean(registrar.data)}
          loading={registrar.isPending}
          onClick={() => corpo && registrar.mutate(corpo as unknown as Record<string, unknown>)}
        >
          Registrar
        </Button>
      </div>
    </div>
  )
}
