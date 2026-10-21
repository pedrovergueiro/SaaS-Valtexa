import { ArrowLeft } from 'lucide-react'
import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'

import { api } from '@/api/client'
import { useApiMutation } from '@/api/queries'
import { useAuth } from '@/auth/AuthProvider'
import { Badge, Button, Card, CardHeader, ErrorBox, FormField, PageHeader, Spinner, Table, td, th } from '@/components/ui'
import { bytesText } from '@/lib/dados'
import { fmt } from '@/lib/format'
import {
  avaliacaoTom,
  cenarioTexto,
  origemTexto,
  origemTom,
  podeRevisar,
  premissasNaoMedidas,
  revisaoValida,
  TIPOS,
  valorPremissa,
  type Plano,
  type RevisaoPlano,
} from '@/lib/planejamento'

type Linha = Record<string, any>

function Fito({ r }: { r: Linha }) {
  return (
    <>
      <Card>
        <CardHeader title="Casos para revisão" subtitle="escore = risco × incerteza × impacto. Casos de alto risco e sem dúvida aparecem nas regiões e nas alternativas." />
        <Table>
          <thead>
            <tr>
              <th className={th}>Planta</th>
              <th className={th}>Rótulo</th>
              <th className={th}>Risco</th>
              <th className={th}>Incerteza</th>
              <th className={th}>Impacto</th>
              <th className={th}>Escore</th>
              <th className={th}>Por quê</th>
            </tr>
          </thead>
          <tbody>
            {(r.fila_de_revisao as Linha[]).map((i) => (
              <tr key={i.diagnosis_id}>
                <td className={td}>{i.plant_ref ?? fmt.shortId(i.observation_id)}</td>
                <td className={td}>{i.rotulo}</td>
                <td className={td} title={JSON.stringify(i.risco_por_fonte)}>{fmt.number(i.risco, 2)}</td>
                <td className={td}>{fmt.number(i.incerteza, 2)}</td>
                <td className={td}>{fmt.number(i.impacto, 1)}</td>
                <td className={td}>{fmt.number(i.escore, 3)}</td>
                <td className={td}>{(i.motivos_da_incerteza as string[]).join('; ') || '—'}</td>
              </tr>
            ))}
          </tbody>
        </Table>
      </Card>
      <Card>
        <CardHeader title="Histórico de sintomas" subtitle="Passadas fechadas e lesões reencontradas no referencial da planta." />
        <ul className="flex flex-col gap-2 px-5 pb-4 text-[13px]">
          {(r.historico_de_sintomas as Linha[]).map((h) => (
            <li key={h.plant_ref} className="border-t border-line-soft pt-2">
              <span className="font-medium">{h.plant_ref}</span> · tendência: {h.tendencia ?? h.motivo_passadas}
              {h.lesoes && (
                <span className="text-muted">
                  {' '}
                  · lesões {Object.entries(h.lesoes.por_estado as Record<string, number>).map(([k, n]) => `${k}: ${n}`).join(', ') || 'nenhuma'}
                </span>
              )}
            </li>
          ))}
        </ul>
      </Card>
      <Card>
        <CardHeader title="Regiões prioritárias" subtitle="Do gêmeo digital: valor da informação por trecho de rua." />
        <ul className="flex flex-col gap-1 px-5 pb-4 text-[13px]">
          {(r.regioes_prioritarias as Linha[]).map((g, n) => (
            <li key={n}>
              Rua {(g.ruas as string[]).join(', ')} · {fmt.number(g.x_inicio_m, 0)}–{fmt.number(g.x_fim_m, 0)} m · valor {fmt.number(g.valor, 2)} · {g.motivo}
            </li>
          ))}
        </ul>
      </Card>
      <Card>
        <CardHeader title="Alternativas de manejo" subtitle="O plano não escolhe; nenhuma traz produto nem dose." />
        <ul className="flex flex-col gap-2 px-5 pb-4 text-[13px]">
          {(r.alternativas_de_manejo as Linha[]).map((a) => (
            <li key={a.codigo} className="border-t border-line-soft pt-2">
              <div className="font-medium">{a.titulo}</div>
              <div className="text-muted">Quando faz sentido: {a.quando_faz_sentido}. Custo de errar: {a.custo_de_errar}.</div>
              <div>Falta: {(a.o_que_falta as string[]).join('; ')}</div>
            </li>
          ))}
        </ul>
      </Card>
      <Card>
        <CardHeader title="Rotação por modo de ação" subtitle={r.rotacao.nota} />
        <div className="px-5 pb-4 text-[13px]">
          {(r.rotacao.avisos as string[]).map((a) => (
            <div key={a} className="text-warning">{a}</div>
          ))}
          <div className="text-muted">
            Último grupo: {r.rotacao.ultimo_grupo ?? '—'} ({r.rotacao.seguidas_do_ultimo_grupo} seguida(s))
          </div>
          <ul className="mt-2 flex flex-col gap-1">
            {(r.rotacao.elegiveis as Linha[]).map((e) => (
              <li key={e.product_id}>
                {e.nome} · {e.modo_de_acao} · fonte {e.fonte?.titulo} v{e.fonte?.versao} <Badge tone={avaliacaoTom(e.avaliacao)}>{e.avaliacao}</Badge>
              </li>
            ))}
          </ul>
          {!!r.rotacao.fora.length && (
            <details className="mt-2">
              <summary className="cursor-pointer text-muted">{r.rotacao.fora.length} produto(s) fora da análise</summary>
              <ul>
                {(r.rotacao.fora as Linha[]).map((f) => (
                  <li key={f.product_id}>
                    {f.nome}: {f.motivo}
                  </li>
                ))}
              </ul>
            </details>
          )}
        </div>
      </Card>
    </>
  )
}

function Robo({ r }: { r: Linha }) {
  return (
    <>
      <Card>
        <CardHeader
          title="Rotas propostas"
          subtitle={`Valor alocado ${fmt.number(r.valor_alocado, 2)} de ${fmt.number(r.valor_disponivel, 2)} (sem as restrições: ${fmt.number(r.sem_restricoes.valor_alocado, 2)}).`}
        />
        <Table>
          <thead>
            <tr>
              <th className={th}>Dispositivo</th>
              <th className={th}>Tarefas</th>
              <th className={th}>Deslocamento</th>
              <th className={th}>Trabalho</th>
              <th className={th}>Tempo</th>
              <th className={th}>Bateria</th>
              <th className={th}>Dados</th>
            </tr>
          </thead>
          <tbody>
            {(r.rotas as Linha[]).map((a) => (
              <tr key={a.device_id}>
                <td className={td}>{a.nome}</td>
                <td className={td}>{a.passos.length}</td>
                <td className={td}>{fmt.meters(a.deslocamento_m)}</td>
                <td className={td}>{fmt.meters(a.trabalho_m)}</td>
                <td className={td}>{fmt.number(a.tempo_s / 60, 0)} min</td>
                <td className={td}>
                  {fmt.number(a.bateria_inicial_pct, 0)}% → {fmt.number(a.bateria_final_estimada_pct, 0)}%
                </td>
                <td className={td}>{bytesText(a.bytes_estimados)}</td>
              </tr>
            ))}
          </tbody>
        </Table>
      </Card>
      <Card>
        <CardHeader title="O que saiu pelas restrições" subtitle="Inclinação, obstáculos da leitura de terreno e orçamento de dados da Starlink." />
        <ul className="flex flex-col gap-1 px-5 pb-4 text-[13px]">
          {(r.nao_atribuidas as Linha[]).map((n) => (
            <li key={n.tarefa}>
              {n.tipo} {fmt.shortId(n.tarefa)}: {n.motivo}
            </li>
          ))}
          {!r.nao_atribuidas.length && <li className="text-muted">Nada ficou de fora.</li>}
        </ul>
      </Card>
      <Card>
        <CardHeader title="Dados pela Starlink" subtitle="O que resta hoje a cada Rover (teto × (1 − reserva) − usado)." />
        <ul className="flex flex-col gap-1 px-5 pb-4 text-[13px]">
          {(r.dados_starlink as Linha[]).map((d) => (
            <li key={d.device_id}>
              {d.nome}: resta {d.restante_bytes == null ? 'sem teto' : bytesText(d.restante_bytes)} · teto {bytesText(d.teto_dia_bytes)} ({d.origem_do_teto}){d.nota ? ` · ${d.nota}` : ''}
            </li>
          ))}
        </ul>
      </Card>
      <p className="text-[12px] text-muted">{r.nota}</p>
    </>
  )
}

function Insumos({ r }: { r: Linha }) {
  return (
    <Card>
      <CardHeader title={`Demanda nos próximos ${r.horizonte_dias} dias`} subtitle={r.nota} />
      <Table>
        <thead>
          <tr>
            <th className={th}>Produto</th>
            <th className={th}>Aplicações</th>
            <th className={th}>Um bloco (p50, p10–p90)</th>
            <th className={th}>Estoque</th>
            <th className={th}>Comprometido</th>
            <th className={th}>Reposição</th>
          </tr>
        </thead>
        <tbody>
          {(r.produtos as Linha[]).map((p) => (
            <tr key={p.product_id}>
              <td className={td}>{p.nome}</td>
              <td className={td}>{p.aplicacoes_na_janela}</td>
              <td className={td}>{p.estimativa ? cenarioTexto(p.estimativa.um_bloco_l) : <span className="text-muted">{p.motivo}</span>}</td>
              <td className={td}>{fmt.liters(p.estoque_l)}</td>
              <td className={td}>{fmt.liters(p.comprometido_l)}</td>
              <td className={td}>
                {p.reposicao ? (
                  <Badge tone={p.reposicao.possivel_reposicao ? 'warning' : 'good'}>
                    {p.reposicao.possivel_reposicao ? `Possível: faltam ${fmt.liters(p.reposicao.falta_no_cenario_alto_l)} no cenário alto` : 'Cobre o cenário alto'}
                  </Badge>
                ) : (
                  '—'
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </Table>
    </Card>
  )
}

/** Um plano de apoio: premissas (com a origem de cada número), resultado, revisão humana. */
export default function PlanoDetail() {
  const { id = '' } = useParams()
  const { can } = useAuth()
  const chave = ['planejamento', 'plano', id]
  const q = useQuery({ queryKey: chave, queryFn: () => api<Plano>(`/v1/planejamento/${id}`) })
  const [decisao, setDecisao] = useState<RevisaoPlano['decisao']>('aceito')
  const [comentario, setComentario] = useState('')
  const revisar = useApiMutation(() => api(`/v1/planejamento/${id}/revisao`, { method: 'POST', body: { decisao, comentario: comentario || null } }), [chave])

  if (q.isLoading) return <Spinner />
  if (q.error || !q.data) return <ErrorBox error={q.error} />
  const p = q.data
  const voltar = p.field_id ? `/talhoes/${p.field_id}/planejamento` : '/planejamento/insumos'
  const naoMedidas = premissasNaoMedidas(p.premissas)

  return (
    <>
      <Link to={voltar} className="mb-3 inline-flex items-center gap-1.5 text-[13px] text-muted hover:text-ink">
        <ArrowLeft className="size-4" aria-hidden /> Planejamento
      </Link>
      <PageHeader eyebrow={`Plano ${TIPOS[p.tipo]} · ${p.versao_motor}`} title={`Plano de ${fmt.dateTime(p.gerado_em)}`} subtitle={p.aviso} />
      {!p.integro && <ErrorBox error={new Error('O plano guardado não confere com o hash.')} className="mb-4" />}
      <div className="grid gap-4 lg:grid-cols-[2fr_1fr]">
        <div className="flex flex-col gap-4">
          {p.tipo === 'fitossanitario' && <Fito r={p.resultado} />}
          {p.tipo === 'robotico' && <Robo r={p.resultado} />}
          {p.tipo === 'insumos' && <Insumos r={p.resultado} />}
          {!!(p.resultado.avisos as string[] | undefined)?.length && (
            <Card>
              <CardHeader title="Avisos" />
              <ul className="px-5 pb-4 text-[13px]">
                {(p.resultado.avisos as string[]).map((a) => (
                  <li key={a}>{a}</li>
                ))}
              </ul>
            </Card>
          )}
        </div>
        <div className="flex flex-col gap-4">
          <Card>
            <CardHeader title="Premissas" subtitle={naoMedidas ? `${naoMedidas} não medida(s) ou simulada(s): confira antes de aceitar.` : 'Todas medidas, do cadastro ou do pedido.'} />
            <ul className="flex flex-col gap-2 px-5 pb-4 text-[12px]">
              {p.premissas.map((x) => (
                <li key={x.codigo} className="border-t border-line-soft pt-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-medium">{x.codigo}</span>
                    <Badge tone={origemTom(x.origem)}>{origemTexto(x.origem)}</Badge>
                    <span className="num">{valorPremissa(x.valor)}</span>
                  </div>
                  <div className="text-muted">{x.texto}</div>
                </li>
              ))}
            </ul>
          </Card>
          <Card>
            <CardHeader title="Revisão" subtitle="Registra quem, quando e a decisão. Não cria missão nem aprova aplicação." />
            <div className="flex flex-col gap-2 px-5 pb-4 text-[13px]">
              {p.revisoes.map((r) => (
                <div key={r.id} className="border-t border-line-soft pt-2">
                  <Badge tone={r.decisao === 'aceito' ? 'good' : r.decisao === 'recusado' ? 'critical' : 'warning'}>{r.decisao}</Badge>{' '}
                  <span className="text-muted">
                    {fmt.dateTime(r.revisado_em)} · {r.papel}
                  </span>
                  {r.comentario && <div className="text-ink-2">{r.comentario}</div>}
                </div>
              ))}
              {podeRevisar(p.tipo, can) && (
                <form
                  className="flex flex-col gap-2 border-t border-line-soft pt-3"
                  onSubmit={(e) => {
                    e.preventDefault()
                    revisar.mutate(undefined)
                  }}
                >
                  <FormField label="Decisão">
                    <select className="input" value={decisao} onChange={(e) => setDecisao(e.target.value as RevisaoPlano['decisao'])}>
                      <option value="aceito">Aceito</option>
                      <option value="ajustar">Ajustar</option>
                      <option value="recusado">Recusado</option>
                    </select>
                  </FormField>
                  <FormField label="Comentário" hint={decisao === 'aceito' ? undefined : 'Obrigatório para recusar ou pedir ajuste.'}>
                    <textarea className="input min-h-20" value={comentario} onChange={(e) => setComentario(e.target.value)} maxLength={4000} />
                  </FormField>
                  <Button type="submit" variant="primary" loading={revisar.isPending} disabled={!revisaoValida(decisao, comentario)}>
                    Registrar revisão
                  </Button>
                  <ErrorBox error={revisar.error} />
                </form>
              )}
            </div>
          </Card>
          <p className="num break-all text-[11px] text-muted">sha256 {p.sha256}</p>
        </div>
      </div>
    </>
  )
}
