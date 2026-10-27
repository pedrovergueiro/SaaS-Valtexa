import { ArrowLeft, ShieldAlert } from 'lucide-react'
import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'

import { api } from '@/api/client'
import { useApiMutation } from '@/api/queries'
import { useAuth } from '@/auth/AuthProvider'
import { Badge, Button, Card, CardHeader, ErrorBox, FormField, PageHeader, Spinner } from '@/components/ui'
import { fmt } from '@/lib/format'
import {
  alvoDaCitacao,
  decisaoTexto,
  modoTexto,
  porSecao,
  avisoDeHoje,
  seloDaFonte,
  situacaoTexto,
  situacaoTom,
  type Parecer,
  type Revisao,
} from '@/lib/parecer'

interface EntradaTrilha {
  id: string
  acao: string
  ator_id: string | null
  quando: string
  dados: Record<string, unknown>
}

function Citacoes({ p, ids }: { p: Parecer; ids: string[] }) {
  return (
    <span className="ml-1 text-[11px] text-muted">
      {ids.map((c) => (
        <a key={c} href={`#${c}`} title={alvoDaCitacao(p, c)} className="mr-1 underline decoration-dotted">
          [{c}]
        </a>
      ))}
    </span>
  )
}

/**
 * Um parecer, para o agrônomo: hipóteses e alternativas, evidências do dossiê (com origem,
 * versão do modelo e limitações), fontes citadas, o que falta verificar e a revisão.
 */
export default function ParecerDetail() {
  const { id = '' } = useParams()
  const { can } = useAuth()
  const chave = ['pareceres', id]
  const q = useQuery({ queryKey: chave, queryFn: () => api<Parecer>(`/v1/pareceres/${id}`) })
  const trilha = useQuery({ queryKey: [...chave, 'auditoria'], queryFn: () => api<EntradaTrilha[]>(`/v1/pareceres/${id}/auditoria`) })
  const [decisao, setDecisao] = useState<Revisao['decisao']>('concorda')
  const [comentario, setComentario] = useState('')
  const [diagnostico, setDiagnostico] = useState('')
  const [registrar, setRegistrar] = useState(false)
  const revisar = useApiMutation(
    () =>
      api(`/v1/pareceres/${id}/revisao`, {
        method: 'POST',
        body: {
          decisao,
          comentario: comentario || null,
          diagnostico_revisor: diagnostico || null,
          registrar_diagnostico: decisao === 'discorda' && !!diagnostico && registrar,
        },
      }),
    [chave, [...chave, 'auditoria']],
  )

  if (q.isLoading) return <Spinner />
  if (q.error || !q.data) return <ErrorBox error={q.error} />
  const p = q.data

  return (
    <>
      <Link to={`/talhoes/${p.field_id}/pareceres`} className="mb-3 inline-flex items-center gap-1.5 text-[13px] text-muted hover:text-ink">
        <ArrowLeft className="size-4" aria-hidden /> Pareceres do talhão
      </Link>
      <PageHeader
        eyebrow={`Parecer · ${modoTexto(p)}`}
        title={p.plant_ref ? `Planta ${p.plant_ref}` : `Observação ${p.observation_id}`}
        subtitle={`Gerado em ${fmt.dateTime(p.gerado_em)}. ${p.aviso}`}
        actions={
          <>
            {!p.integro && <Badge tone="critical">Não confere com o hash</Badge>}
            <Badge tone={p.estado === 'revisado' ? 'good' : 'warning'}>{p.estado === 'revisado' ? 'Revisado' : 'Aguardando revisão'}</Badge>
          </>
        }
      />

      <div className="grid gap-4 lg:grid-cols-[3fr_2fr]">
        <div className="flex flex-col gap-4">
          {porSecao(p.afirmacoes).map((g) => (
            <Card key={g.secao}>
              <CardHeader title={g.titulo} />
              <ul className="flex flex-col gap-1.5 px-5 pb-4 text-[13px]">
                {g.itens.map((a) => (
                  <li key={a.id}>
                    {a.texto}
                    <Citacoes p={p} ids={a.citacoes} />
                  </li>
                ))}
              </ul>
            </Card>
          ))}
          <Card>
            <CardHeader title="O que falta verificar antes de qualquer intervenção" subtitle="Nenhum item sai como resolvido: quem dá por verificado é o responsável." />
            <ul className="flex flex-col gap-2 px-5 pb-4 text-[13px]">
              {p.verificacoes.map((v) => (
                <li key={v.codigo} className="border-t border-line-soft pt-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-medium">{v.titulo}</span>
                    <Badge tone={situacaoTom(v.situacao)}>{situacaoTexto(v.situacao)}</Badge>
                  </div>
                  <p className="text-ink-2">
                    {v.detalhe}
                    <Citacoes p={p} ids={v.citacoes} />
                  </p>
                </li>
              ))}
            </ul>
            <p className="flex items-start gap-2 px-5 pb-5 text-[13px] font-medium">
              <ShieldAlert className="mt-0.5 size-4 shrink-0 text-warning" aria-hidden /> {p.fecho}
            </p>
          </Card>
        </div>

        <div className="flex flex-col gap-4">
          <Card>
            <CardHeader title="Evidências (dossiê)" subtitle="Cada item com a origem, a versão do modelo e o que ele não diz." />
            <ul className="flex flex-col gap-3 px-5 pb-4 text-[13px]">
              {p.dossie.itens.map((i) => (
                <li key={i.id} id={i.id} className="border-t border-line-soft pt-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-medium">
                      {i.id} · {i.titulo}
                    </span>
                    {!i.disponivel && <Badge tone="neutral">Indisponível</Badge>}
                  </div>
                  <div className="text-[12px] text-muted">
                    {String(i.origem.sistema ?? '')}
                    {i.versao_modelo ? ` · ${i.versao_modelo}` : ''}
                  </div>
                  {i.motivo_indisponivel && <p className="text-ink-2">{i.motivo_indisponivel}</p>}
                  {!!i.limitacoes.length && (
                    <ul className="ml-4 list-disc text-ink-2">
                      {i.limitacoes.map((l) => (
                        <li key={l}>{l}</li>
                      ))}
                    </ul>
                  )}
                </li>
              ))}
            </ul>
          </Card>

          <Card>
            <CardHeader title="Fontes citadas" subtitle={p.fontes.length ? 'Trechos do repositório, com versão e hash.' : 'Sem fonte no repositório para este caso.'} />
            <ul className="flex flex-col gap-3 px-5 pb-4 text-[13px]">
              {p.fontes.map((f) => {
                const selo = seloDaFonte(f)
                const hoje = avisoDeHoje(p.fontes_hoje?.find((h) => h.id === f.id))
                return (
                  <li key={f.id} id={f.id} className="border-t border-line-soft pt-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-medium">
                        {f.id} · {f.titulo} v{f.versao}
                      </span>
                      <Badge tone={selo.tom}>{selo.texto}</Badge>
                      {hoje && <Badge tone="warning">{hoje}</Badge>}
                    </div>
                    <div className="text-[12px] text-muted">
                      {f.tipo} · {f.origem} · licença {f.licenca}
                      {f.secao ? ` · ${f.secao}` : ''}
                    </div>
                    <blockquote className="mt-1 border-l-2 border-line pl-2 whitespace-pre-wrap text-ink-2">{f.texto}</blockquote>
                    <div className="num text-[11px] text-muted">sha256 {f.sha256_trecho.slice(0, 16)}…</div>
                  </li>
                )
              })}
            </ul>
          </Card>

          {!!p.recusas.length && (
            <Card>
              <CardHeader title="Recusado pelo validador" subtitle="Texto do provedor descartado; o parecer saiu do compositor determinístico." />
              <ul className="flex flex-col gap-1 px-5 pb-4 text-[12px] text-ink-2">
                {p.recusas.map((r, n) => (
                  <li key={n}>
                    {r.origem}: {r.erro ?? r.recusas?.flatMap((x) => x.motivos).join(', ')}
                  </li>
                ))}
              </ul>
            </Card>
          )}

          <Card>
            <CardHeader title="Revisão do agrônomo" subtitle="Registra quem, quando e a decisão. Não autoriza aplicação nem cria missão." />
            <div className="flex flex-col gap-2 px-5 pb-4 text-[13px]">
              {p.revisoes.map((r) => (
                <div key={r.id} className="border-t border-line-soft pt-2">
                  <Badge tone={r.decisao === 'concorda' ? 'good' : r.decisao === 'discorda' ? 'critical' : 'warning'}>{decisaoTexto(r.decisao)}</Badge>{' '}
                  <span className="text-muted">
                    {fmt.dateTime(r.revisado_em)} · {r.papel}
                  </span>
                  {r.diagnostico_revisor && <div>Diagnóstico do revisor: {r.diagnostico_revisor}</div>}
                  {r.comentario && <div className="text-ink-2">{r.comentario}</div>}
                </div>
              ))}
              {can('diagnosis:review') && (
                <form
                  className="flex flex-col gap-2 border-t border-line-soft pt-3"
                  onSubmit={(e) => {
                    e.preventDefault()
                    revisar.mutate(undefined)
                  }}
                >
                  <FormField label="Decisão">
                    <select className="input" value={decisao} onChange={(e) => setDecisao(e.target.value as Revisao['decisao'])}>
                      <option value="concorda">Concorda</option>
                      <option value="discorda">Discorda</option>
                      <option value="inconclusivo">Pede mais evidência</option>
                    </select>
                  </FormField>
                  <FormField label="Comentário" hint={decisao === 'discorda' ? 'Obrigatório ao discordar.' : undefined}>
                    <textarea className="input min-h-20" value={comentario} onChange={(e) => setComentario(e.target.value)} maxLength={4000} />
                  </FormField>
                  <FormField
                    label="Diagnóstico do revisor (opcional)"
                    hint={decisao === 'discorda' ? 'Discordando com um diagnóstico, isto vira uma lição: aparece nos próximos pareceres com o seu nome.' : undefined}
                  >
                    <input className="input" value={diagnostico} onChange={(e) => setDiagnostico(e.target.value)} maxLength={80} />
                  </FormField>
                  {decisao === 'discorda' && diagnostico && p.caso_tipo === 'observacao' && (
                    <label className="flex items-start gap-2 text-[13px]">
                      <input type="checkbox" checked={registrar} onChange={(e) => setRegistrar(e.target.checked)} className="mt-0.5" />
                      <span>
                        Registrar este diagnóstico na foto, como na fila (vira exemplo de treino e refaz a recomendação). Use o
                        nome da classe, ex.: Cercospora_Leaf_Spot.
                      </span>
                    </label>
                  )}
                  <Button type="submit" variant="primary" loading={revisar.isPending}>
                    Registrar revisão
                  </Button>
                  <ErrorBox error={revisar.error} />
                </form>
              )}
            </div>
          </Card>

          <Card>
            <CardHeader title="Trilha de auditoria" />
            <ul className="flex flex-col gap-1 px-5 pb-4 text-[12px]">
              {(trilha.data ?? []).map((e) => (
                <li key={e.id} className="flex justify-between gap-2 border-t border-line-soft py-1">
                  <span>{e.acao === 'parecer.gerado' ? 'Gerado' : e.acao === 'parecer.revisado' ? `Revisado (${String(e.dados.decisao)})` : e.acao}</span>
                  <span className="text-muted">{fmt.dateTime(e.quando)}</span>
                </li>
              ))}
            </ul>
          </Card>
        </div>
      </div>
    </>
  )
}
