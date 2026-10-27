import { ArrowLeft, CloudSun, Gauge, ShieldCheck } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'

import { api } from '@/api/client'
import { useApiMutation, useField } from '@/api/queries'
import { useAuth } from '@/auth/AuthProvider'
import { Badge, Button, Card, CardHeader, Empty, ErrorBox, FormField, PageHeader, Spinner, Table, Tabs, td, th } from '@/components/ui'
import { fmt } from '@/lib/format'
import {
  FONTE_DO_CLIMA,
  modoTexto,
  quemVence,
  tomDoErroDeMolhamento,
  type Avaliacao,
  type Gemeo,
  type Previsao,
} from '@/lib/gemeo'
import { disease } from '@/lib/labels'

const NOME_DA_REFERENCIA = { modelo: 'gêmeo', persistencia: 'persistência', prevalencia: 'prevalência' } as const

/**
 * Gêmeo digital do talhão: clima, previsão, a avaliação das previsões contra o que o Rover viu
 * e o modo (observação ou ativo). Em observação, o mapa de aplicação feito pelo gêmeo é
 * registro — o Safety Engine não o executa. Só o agrônomo ativa, e só com avaliação favorável.
 */
export default function GemeoTalhao() {
  const { id = '' } = useParams()
  const field = useField(id)
  const gemeo = useQuery({ queryKey: ['fields', id, 'gemeo'], queryFn: () => api<Gemeo>(`/v1/fields/${id}/gemeo`) })
  const doencas = gemeo.data?.doencas ?? []
  const [doenca, setDoenca] = useState<string>('')
  useEffect(() => {
    if (!doenca && doencas.length) setDoenca(doencas.includes('Rust') ? 'Rust' : (doencas[0] ?? ''))
  }, [doenca, doencas])

  return (
    <>
      <Link to={`/talhoes/${id}`} className="mb-3 inline-flex items-center gap-1.5 text-[13px] text-muted hover:text-ink">
        <ArrowLeft className="size-4" aria-hidden /> Talhão
      </Link>
      <PageHeader
        eyebrow="Gêmeo digital"
        title={`Previsão e modo${field.data ? ` · ${field.data.name}` : ''}`}
        subtitle="O gêmeo começa em observação: prevê, é comparado com o que o Rover viu depois e só então pode mudar a taxa de aplicação."
        actions={
          doencas.length > 1 && (
            <Tabs<string> value={doenca} onChange={setDoenca} items={doencas.map((d) => ({ value: d, label: disease(d) }))} />
          )
        }
      />
      <ErrorBox error={gemeo.error} className="mb-4" />
      {gemeo.isLoading && <Spinner />}
      {gemeo.data && (
        <div className="flex flex-col gap-4">
          <ClimaCard g={gemeo.data} />
          {doenca && <ModoEAvaliacao fieldId={id} doenca={doenca} />}
          {doenca && <PrevisaoCard fieldId={id} doenca={doenca} />}
        </div>
      )}
    </>
  )
}

function ClimaCard({ g }: { g: Gemeo }) {
  const a = g.clima.atualidade
  return (
    <Card>
      <CardHeader
        title="Clima do talhão"
        subtitle="O que dirige o modelo. A estação vence a reanálise, e o observado vence a previsão."
        actions={<CloudSun className="size-5 text-muted" aria-hidden />}
      />
      <div className="flex flex-wrap items-center gap-3 px-5 pb-5 text-[13px]">
        <span className="num">
          {g.clima.dias} dias{g.clima.inicio ? ` · ${fmt.date(g.clima.inicio)} a ${fmt.date(g.clima.fim ?? g.clima.inicio)}` : ''}
        </span>
        {Object.entries(g.clima.por_fonte).map(([fonte, n]) => (
          <Badge key={fonte} tone="neutral">
            {FONTE_DO_CLIMA[fonte] ?? fonte}: {n}
          </Badge>
        ))}
        {a && (
          <Badge tone={a.desatualizada ? 'warning' : 'good'}>
            {a.ultimo_dia_observado
              ? `observado até ${fmt.date(a.ultimo_dia_observado)}${a.desatualizada ? ' — desatualizado' : ''}`
              : 'sem tempo observado'}
          </Badge>
        )}
        <span className="text-muted">
          {g.plantas} plantas · {g.passadas.length} passada(s)
        </span>
      </div>
    </Card>
  )
}

function ModoEAvaliacao({ fieldId, doenca }: { fieldId: string; doenca: string }) {
  const { can } = useAuth()
  const chave = ['fields', fieldId, 'gemeo', 'avaliacao', doenca]
  const av = useQuery({
    queryKey: chave,
    queryFn: () => api<Avaliacao>(`/v1/fields/${fieldId}/gemeo/avaliacao`, { query: { doenca } }),
  })
  const [motivo, setMotivo] = useState('')
  const mudar = useApiMutation(
    (modo: 'ativo' | 'observacao') =>
      api(`/v1/fields/${fieldId}/gemeo/modo`, { method: 'POST', body: { doenca, modo, motivo: motivo.trim() } }),
    [chave],
  )
  if (av.isLoading) return <Spinner />
  if (av.error || !av.data) return <ErrorBox error={av.error ?? new Error('Sem avaliação')} />
  const d = av.data
  const modo = modoTexto(d.modo.modo)
  const vence = quemVence(d.nota_por_planta)
  const podeDecidir = can('diagnosis:review')
  return (
    <div className="grid gap-4 xl:grid-cols-2">
      <Card>
        <CardHeader title="Modo do gêmeo" actions={<ShieldCheck className="size-5 text-muted" aria-hidden />} />
        <div className="flex flex-col gap-3 px-5 pb-5 text-[13px]">
          <div className="flex items-center gap-2">
            <Badge tone={modo.tom}>{modo.rotulo}</Badge>
            {d.modo.desde && (
              <span className="text-muted">
                desde {fmt.dateTime(d.modo.desde)}
                {d.modo.responsavel ? ` · ${d.modo.responsavel}` : ''}
              </span>
            )}
          </div>
          <p className="text-ink-2">{modo.explica}</p>
          {d.modo.motivo && <p className="text-muted">Motivo: {d.modo.motivo}</p>}
          {podeDecidir ? (
            <>
              <FormField label="Motivo da decisão" hint="Fica no registro da IA e na auditoria.">
                <textarea className="input min-h-14" value={motivo} onChange={(e) => setMotivo(e.target.value)} />
              </FormField>
              <ErrorBox error={mudar.error} />
              <div className="flex flex-wrap gap-2">
                {d.modo.modo !== 'ativo' && (
                  <Button
                    variant="primary"
                    disabled={!d.pode_ativar || motivo.trim().length < 3}
                    loading={mudar.isPending}
                    onClick={() => mudar.mutate('ativo')}
                  >
                    Ativar o gêmeo
                  </Button>
                )}
                {d.modo.modo === 'ativo' && (
                  <Button disabled={motivo.trim().length < 3} loading={mudar.isPending} onClick={() => mudar.mutate('observacao')}>
                    Voltar à observação
                  </Button>
                )}
              </div>
              {d.modo.modo !== 'ativo' && !d.pode_ativar && (
                <p className="text-[12px] text-muted">Ativar fica liberado quando a avaliação ao lado permitir.</p>
              )}
            </>
          ) : (
            <p className="text-[12px] text-muted">Só o agrônomo muda o modo.</p>
          )}
        </div>
      </Card>

      <Card>
        <CardHeader
          title="As previsões contra o que o Rover viu"
          subtitle={`Um passo à frente, nas passadas que o ajuste não viu · parâmetros: ${d.parametros} · clima ${d.clima}.`}
          actions={<Gauge className="size-5 text-muted" aria-hidden />}
        />
        <div className="flex flex-col gap-3 px-5 pb-5 text-[13px]">
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone={d.pode_ativar ? 'good' : 'neutral'}>{d.pode_ativar ? 'pode ativar' : 'ainda não'}</Badge>
            <span className="num text-muted">
              {d.passadas_avaliadas} passada(s) · {d.plantas} plantas
            </span>
            {vence && <span className="text-muted">quem prevê melhor: {NOME_DA_REFERENCIA[vence]}</span>}
          </div>
          {d.motivos.length > 0 && (
            <ul className="list-disc pl-5 text-ink-2">
              {d.motivos.map((m) => (
                <li key={m}>{m}</li>
              ))}
            </ul>
          )}
          {d.por_passada.length === 0 ? (
            <p className="text-muted">
              Nenhuma passada fora do ajuste ainda: cada passada nova do Rover, antes do próximo ajuste, vira uma nota.
            </p>
          ) : (
            <Table>
              <thead>
                <tr>
                  <th className={th}>Passada</th>
                  <th className={th}>Plantas</th>
                  <th className={th}>Gêmeo</th>
                  <th className={th}>Persistência</th>
                  <th className={th}>Prevalência</th>
                </tr>
              </thead>
              <tbody>
                {d.por_passada.map((p) => (
                  <tr key={p.pass_id}>
                    <td className={`${td} font-mono text-[12px]`}>{p.pass_id}</td>
                    <td className={`${td} num`}>{p.plantas}</td>
                    {(['modelo', 'persistencia', 'prevalencia'] as const).map((k) => (
                      <td key={k} className={`${td} num`}>
                        {p[k] != null ? fmt.number(p[k] as number, 4) : '—'}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </Table>
          )}
          <p className="text-[12px] text-muted">Nota: log-verossimilhança por planta; maior é melhor, zero é "a passada não disse nada".</p>
        </div>
      </Card>

      <Card className="xl:col-span-2">
        <CardHeader
          title="O tempo previsto contra o observado"
          subtitle="O tempo que o gêmeo usou nos mapas e prescrições, comparado com o que a estação mediu depois. O molhamento é o que mais pesa."
        />
        {d.tempo_previsto.comparados === 0 ? (
          <Empty title="Nada a comparar ainda">Quando chegar o tempo observado dos dias que o gêmeo previu, o erro aparece aqui.</Empty>
        ) : (
          <Table>
            <thead>
              <tr>
                <th className={th}>Fonte</th>
                <th className={th}>Dias à frente</th>
                <th className={th}>Dias</th>
                <th className={th}>Molhamento (h)</th>
                <th className={th}>Temperatura (°C)</th>
                <th className={th}>Umidade (%)</th>
                <th className={th}>Chuva (mm)</th>
              </tr>
            </thead>
            <tbody>
              {d.tempo_previsto.por_fonte_e_antecedencia.map((x) => (
                <tr key={`${x.fonte}-${x.dias_a_frente}`}>
                  <td className={td}>{FONTE_DO_CLIMA[x.fonte] ?? x.fonte}</td>
                  <td className={`${td} num`}>{x.dias_a_frente}</td>
                  <td className={`${td} num`}>{x.n}</td>
                  <td className={td}>
                    <Badge tone={tomDoErroDeMolhamento(x.erro_medio.molhamento_h)}>{fmt.number(x.erro_medio.molhamento_h, 1)}</Badge>
                  </td>
                  <td className={`${td} num`}>{fmt.number(x.erro_medio.t_media, 1)}</td>
                  <td className={`${td} num`}>{fmt.number(x.erro_medio.ur_media, 0)}</td>
                  <td className={`${td} num`}>{fmt.number(x.erro_medio.chuva_mm, 1)}</td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card>
    </div>
  )
}

function PrevisaoCard({ fieldId, doenca }: { fieldId: string; doenca: string }) {
  const prev = useQuery({
    queryKey: ['fields', fieldId, 'gemeo', 'previsao', doenca],
    queryFn: () =>
      api<Previsao>(`/v1/fields/${fieldId}/gemeo/previsao`, { query: { doenca, horizonte_dias: 21, plantas: 'nenhuma' } }),
  })
  return (
    <Card>
      <CardHeader title={`Previsão · ${disease(doenca)}`} subtitle="Inclui o que o Rover ainda não vê (o latente). Faixa p10–p90 do conjunto." />
      <div className="px-5 pb-5 text-[13px]">
        <ErrorBox error={prev.error} />
        {prev.isLoading && <Spinner />}
        {prev.data && (
          <div className="flex flex-col gap-3">
            <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
              <div>
                <div className="text-muted">Esporulando agora</div>
                <div className="num text-[20px] font-semibold">{fmt.number(prev.data.esporulando_agora_esperado, 1)}</div>
              </div>
              <div>
                <div className="text-muted">Infectadas até {fmt.date(prev.data.horizonte)}</div>
                <div className="num text-[20px] font-semibold">{fmt.number(prev.data.infectadas_no_horizonte_esperado, 1)}</div>
                {prev.data.infectadas_no_horizonte_p10_p90 && (
                  <div className="num text-[12px] text-muted">
                    {fmt.number(prev.data.infectadas_no_horizonte_p10_p90[0], 1)}–{fmt.number(prev.data.infectadas_no_horizonte_p10_p90[1], 1)}
                  </div>
                )}
              </div>
              <div>
                <div className="text-muted">Focos agora / no horizonte</div>
                <div className="num text-[20px] font-semibold">
                  {prev.data.focos_agora} / {prev.data.focos_no_horizonte}
                </div>
                <div className="text-[12px] text-muted">{prev.data.focos_novos_no_horizonte} novo(s)</div>
              </div>
              <div>
                <div className="text-muted">Parâmetros</div>
                <div className="text-[13px]">{prev.data.parametros_ajustados ? 'ajustados ao talhão' : 'da literatura (prior)'}</div>
              </div>
            </div>
            <div>
              <div className="mb-1 font-medium">Janelas de infecção</div>
              {prev.data.janelas_de_infeccao.length === 0 ? (
                <span className="text-muted">Nenhuma no horizonte.</span>
              ) : (
                <div className="flex flex-wrap gap-1.5">
                  {prev.data.janelas_de_infeccao.map((j) => (
                    <Badge key={j.inicio} tone="warning">
                      {fmt.date(j.inicio)} a {fmt.date(j.fim)} · {j.dias} dia(s)
                    </Badge>
                  ))}
                </div>
              )}
            </div>
            {prev.data.avisos.length > 0 && (
              <ul className="list-disc pl-5 text-[12px] text-muted">
                {prev.data.avisos.map((a) => (
                  <li key={a}>{a}</li>
                ))}
              </ul>
            )}
          </div>
        )}
      </div>
    </Card>
  )
}
