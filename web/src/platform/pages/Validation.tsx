import { ClipboardCheck, FlaskConical, Square } from 'lucide-react'
import { useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { Badge, Button, Card, CardHeader, Empty, ErrorBox, PageHeader, Spinner, Table, td, th, useToast } from '@/components/ui'
import { fmt } from '@/lib/format'
import {
  type DefinicaoEnsaio,
  type EnsaioResultado,
  afrouxa,
  camposDoEnsaio,
  converteParametro,
  criterioTexto,
  portaoInfo,
  progressoTexto,
  rotuloFase,
  situacaoItem,
  statusEnsaio,
} from '@/lib/validacao'
import {
  useCancelaEnsaio,
  useEnsaiosCatalogo,
  useMandaEnsaio,
  usePlatformMe,
  useRoverEnsaios,
  useRoverPanel,
  useRoverPortoes,
} from '@/platform/api'

/**
 * Validação do Rover (console da plataforma): portões por fase, ensaios em curso e o
 * histórico. Cada ensaio sai assinado; o veredito mostrado é o que o servidor calculou
 * com as amostras do robô — nunca o que o robô disse. Resultado simulado vem marcado e
 * não abre portão real.
 */

const PODE = 'platform:rover:control'

export default function Validation() {
  const { id = '' } = useParams()
  const painel = useRoverPanel(id)
  const ensaios = useRoverEnsaios(id)
  const portoes = useRoverPortoes(id)
  const eu = usePlatformMe()
  const pode = Boolean(eu.data?.capabilities?.includes(PODE))

  if (painel.isLoading || ensaios.isLoading) return <Spinner label="Carregando a validação" />
  if (painel.error || !painel.data) return <ErrorBox error={painel.error} />
  const d = painel.data.device

  return (
    <>
      <PageHeader
        eyebrow="Centro de comando · validação"
        title={`Validação de ${d.name}`}
        subtitle="Ensaios automáticos assinados, veredito calculado na plataforma e portão de cada fase do guia de validação."
        actions={
          <Link to={`/plataforma/comando/${id}`} className="text-[13px] text-accent hover:underline">
            ← Centro de comando
          </Link>
        }
      />
      <ErrorBox error={ensaios.error ?? portoes.error} className="mb-4" />
      <Portoes portoes={portoes.data ?? []} />
      <div className="mt-5 grid gap-5 xl:grid-cols-3">
        <div className="space-y-5 xl:col-span-2">
          <EmCurso id={id} pode={pode} emCurso={ensaios.data?.em_curso ?? []} />
          <Historico resultados={ensaios.data?.resultados ?? []} />
        </div>
        <NovoEnsaio id={id} pode={pode} />
      </div>
    </>
  )
}

function Portoes({ portoes }: { portoes: NonNullable<ReturnType<typeof useRoverPortoes>['data']> }) {
  return (
    <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
      {portoes.map((p) => {
        const info = portaoInfo(p)
        return (
          <Card key={p.fase} className="p-4">
            <div className="mb-2 flex items-center justify-between gap-2">
              <div>
                <div className="text-[11px] tracking-[0.14em] text-muted uppercase">Fase {rotuloFase(p.fase)}</div>
                <div className="font-medium">{p.titulo}</div>
              </div>
              <Badge tone={info.tone}>{info.label}</Badge>
            </div>
            {p.automatico ? (
              <ul className="space-y-1 text-[13px]">
                {p.itens.map((i) => {
                  const s = situacaoItem(i.situacao)
                  return (
                    <li key={i.rotulo} className="flex items-center justify-between gap-2">
                      <span>{i.rotulo}</span>
                      <Badge tone={s.tone}>{s.label}</Badge>
                    </li>
                  )
                })}
                {p.informativos.length > 0 && (
                  <li className="text-[12px] text-muted">Informativo (fora do portão): {p.informativos.join(', ')}</li>
                )}
              </ul>
            ) : (
              <p className="text-[13px] text-muted">{p.nota}</p>
            )}
          </Card>
        )
      })}
    </div>
  )
}

function EmCurso({ id, pode, emCurso }: { id: string; pode: boolean; emCurso: NonNullable<ReturnType<typeof useRoverEnsaios>['data']>['em_curso'] }) {
  const cancela = useCancelaEnsaio(id)
  const toast = useToast()
  return (
    <Card>
      <CardHeader title="Em curso" subtitle="Um ensaio por vez; o rover conta o andamento enquanto mede." />
      {emCurso.length === 0 ? (
        <Empty title="Nenhum ensaio rodando" icon={<FlaskConical className="size-5" />}>
          Escolha um ensaio ao lado.
        </Empty>
      ) : (
        <ul className="divide-y divide-line-soft">
          {emCurso.map((c) => (
            <li key={c.id} className="flex flex-wrap items-center gap-3 px-4 py-3">
              <span className="font-medium">{c.params.ensaio}</span>
              <Badge tone="info">{c.state === 'em_execucao' ? `em execução ${progressoTexto(c.progress)}` : c.state}</Badge>
              <span className="text-[12px] text-muted">{c.progress?.etapa ?? ''}</span>
              <Button
                className="ml-auto"
                size="sm"
                icon={<Square className="size-4" />}
                disabled={!pode}
                loading={cancela.isPending}
                onClick={() =>
                  cancela.mutate(c.id, {
                    onSuccess: () => toast.push({ tone: 'info', title: 'Cancelamento enviado', detail: 'O rover para no próximo ponto de checagem.' }),
                    onError: (e) => toast.push({ tone: 'critical', title: 'Não deu para cancelar', detail: String((e as Error).message) }),
                  })
                }
              >
                Cancelar
              </Button>
            </li>
          ))}
        </ul>
      )}
    </Card>
  )
}

function Historico({ resultados }: { resultados: EnsaioResultado[] }) {
  const [aberto, setAberto] = useState<string | null>(null)
  return (
    <Card className="overflow-hidden p-0">
      <CardHeader className="px-4 pt-4" title="Resultados" subtitle="Veredito recalculado pela plataforma com as amostras brutas." />
      {resultados.length === 0 ? (
        <Empty title="Nenhum ensaio ainda" icon={<ClipboardCheck className="size-5" />}>
          Os resultados aparecem aqui quando o rover terminar.
        </Empty>
      ) : (
        <Table>
          <thead>
            <tr>
              <th className={th}>Quando</th>
              <th className={th}>Ensaio</th>
              <th className={th}>Veredito</th>
              <th className={th}>Portão</th>
            </tr>
          </thead>
          <tbody>
            {resultados.map((r) => {
              const s = statusEnsaio(r.status)
              return (
                <tr key={r.id} className="cursor-pointer hover:bg-sunken" onClick={() => setAberto(aberto === r.id ? null : r.id)}>
                  <td className={td}>{fmt.ago(r.created_at)}</td>
                  <td className={td}>
                    <div className="font-medium">
                      {r.ensaio} <span className="text-muted">· fase {rotuloFase(r.fase)}</span>
                    </div>
                    {aberto === r.id && (
                      <div className="mt-2 space-y-1 text-[12px]">
                        {r.criterios.map((c) => (
                          <div key={c.nome} className={c.ok ? 'text-ink-2' : 'text-critical'}>
                            {c.ok ? '✓' : '✗'} {c.nome}: {criterioTexto(c)}
                          </div>
                        ))}
                        {r.observacao && <div className="text-muted">{r.observacao}</div>}
                      </div>
                    )}
                  </td>
                  <td className={td}>
                    <div className="flex flex-wrap gap-1">
                      <Badge tone={s.tone}>{s.label}</Badge>
                      {r.simulado && <Badge tone="warning">simulado</Badge>}
                      {r.divergente && <Badge tone="serious">robô divergiu</Badge>}
                    </div>
                  </td>
                  <td className={td}>{r.vale_portao ? 'conta' : 'não conta'}</td>
                </tr>
              )
            })}
          </tbody>
        </Table>
      )}
    </Card>
  )
}

function NovoEnsaio({ id, pode }: { id: string; pode: boolean }) {
  const catalogo = useEnsaiosCatalogo()
  const manda = useMandaEnsaio(id)
  const toast = useToast()
  const doRobo = useMemo(() => (catalogo.data?.ensaios ?? []).filter((e) => e.origem === 'rover'), [catalogo.data])
  const [nome, setNome] = useState('')
  const [valores, setValores] = useState<Record<string, string>>({})
  const def: DefinicaoEnsaio | undefined = doRobo.find((e) => e.nome === nome) ?? doRobo[0]
  const campos = def ? camposDoEnsaio(def) : []

  const params: Record<string, unknown> = {}
  for (const c of campos) {
    const v = converteParametro(valores[c.nome] ?? '', c.padrao)
    if (v !== undefined) params[c.nome] = v
  }
  const frouxos = campos.filter((c) => afrouxa(params[c.nome], c.padrao, c.limite)).map((c) => c.nome)

  return (
    <Card>
      <CardHeader title="Novo ensaio" subtitle="Vazio = padrão do portão. Limites só podem ficar mais rígidos." />
      <ErrorBox error={catalogo.error} />
      {def && (
        <div className="space-y-3 px-4 pb-4">
          <select
            className="input w-full"
            value={def.nome}
            onChange={(e) => {
              setNome(e.target.value)
              setValores({})
            }}
            aria-label="Ensaio"
          >
            {doRobo.map((e) => (
              <option key={e.nome} value={e.nome}>
                Fase {rotuloFase(e.fase)} · {e.titulo}
              </option>
            ))}
          </select>
          {campos.map((c) => (
            <label key={c.nome} className="block text-[12px]">
              <span className="text-muted">
                {c.nome}
                {c.obrigatorio && ' *'}
                {c.limite && ` (limite ${c.limite === 'max' ? 'máximo' : 'mínimo'})`}
              </span>
              <input
                className="input num mt-1 w-full"
                placeholder={c.padrao == null ? '' : String(c.padrao)}
                value={valores[c.nome] ?? ''}
                onChange={(e) => setValores({ ...valores, [c.nome]: e.target.value })}
              />
            </label>
          ))}
          {frouxos.length > 0 && <p className="text-[12px] text-critical">Mais frouxo que o portão: {frouxos.join(', ')}.</p>}
          <Button
            variant="primary"
            icon={<FlaskConical className="size-4" />}
            disabled={!pode || frouxos.length > 0}
            loading={manda.isPending}
            onClick={() =>
              manda.mutate(
                { ensaio: def.nome, params },
                {
                  onSuccess: () => toast.push({ tone: 'info', title: 'Ensaio enviado', detail: 'Assinado; o rover começa na próxima busca.' }),
                  onError: (e) => toast.push({ tone: 'critical', title: 'Ensaio recusado', detail: String((e as Error).message) }),
                },
              )
            }
          >
            Rodar {def.nome}
          </Button>
          {!pode && <p className="text-[12px] text-muted">Somente leitura: mandar ensaio exige "{PODE}".</p>}
        </div>
      )}
    </Card>
  )
}
