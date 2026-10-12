import { CheckCircle2, Info, RefreshCw, Send } from 'lucide-react'
import { useParams } from 'react-router-dom'

import {
  useAdminCollection,
  useAdminCollectionFiles,
  useAdminJobs,
  useReleaseCollection,
  useRetryJob,
} from '@/api/queries'
import {
  Badge,
  Button,
  Card,
  CardHeader,
  Empty,
  ErrorBox,
  Meter,
  PageHeader,
  Spinner,
  Table,
  td,
  th,
} from '@/components/ui'
import { fmt } from '@/lib/format'
import {
  bytes,
  capturePlatform,
  collectionFileState,
  collectionFileTone,
  collectionKind,
  collectionSource,
  collectionState,
  collectionStateTone,
  jobState,
  jobStateTone,
} from '@/lib/labels'

/**
 * O acompanhamento de uma coleta.
 *
 * Duas barras separadas — upload e processamento — porque são fases com ritmos
 * muito diferentes: a primeira depende da internet da fazenda, a segunda do
 * worker. Juntá-las numa só esconderia justamente qual delas travou.
 */
export default function CollectionDetail() {
  const { id = '' } = useParams()
  const coleta = useAdminCollection(id)
  const arquivos = useAdminCollectionFiles(id)
  const fila = useAdminJobs()
  const publicar = useReleaseCollection()
  const tentarDeNovo = useRetryJob()

  if (coleta.isLoading) return <Spinner label="Abrindo a coleta" />
  if (!coleta.data) return <ErrorBox error={coleta.error ?? 'Coleta não encontrada.'} />

  const item = coleta.data
  const p = item.progress
  const trabalho = (fila.data ?? []).find((job) => job.subject_id === item.id)
  const podePublicar = ['analyzed', 'review_required', 'results_generated'].includes(item.state)

  return (
    <>
      <PageHeader
        title={item.code}
        subtitle={`${item.farm_name ?? '—'} · ${item.field_name ?? '—'} · coletada em ${fmt.date(item.collected_on)}`}
        actions={
          <div className="flex items-center gap-2">
            <Badge tone={collectionStateTone(item.state)}>{collectionState(item.state)}</Badge>
            {podePublicar && (
              <Button onClick={() => publicar.mutate(item.id)} disabled={publicar.isPending}>
                <Send className="size-4" aria-hidden />
                Publicar para o cliente
              </Button>
            )}
          </div>
        }
      />

      <ErrorBox error={publicar.error} className="mb-4" />

      {/* O aviso que não pode faltar: a plataforma diz o que ela não sabe fazer. */}
      {item.no_model_reason && (
        <Card className="mb-4 border-warning/40">
          <div className="flex items-start gap-3 p-4">
            <Info className="mt-0.5 size-5 shrink-0 text-warning" aria-hidden />
            <div className="space-y-1">
              <p className="text-sm font-medium">Nenhum modelo treinado atende esta coleta</p>
              <p className="text-[13px] text-muted">{item.no_model_reason}</p>
              <p className="text-[13px] text-muted">
                As imagens estão guardadas, catalogadas e no lugar certo. Nenhuma passou por
                classificador: quem as rotula é o agrônomo, e é esse rótulo que forma o dataset do
                modelo que ainda não existe.
              </p>
            </div>
          </div>
        </Card>
      )}

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader title="Progresso" />
          <div className="space-y-5 p-4">
            <div>
              <div className="mb-1.5 flex items-baseline justify-between text-[13px]">
                <span className="font-medium">Upload</span>
                <span className="text-muted">
                  {bytes(p.bytes_received)} de {bytes(p.bytes_total)} · {p.stored}/{p.files} arquivos
                </span>
              </div>
              <Meter value={p.upload_percent} tone={p.upload_percent >= 100 ? 'good' : 'accent'} />
            </div>

            <div>
              <div className="mb-1.5 flex items-baseline justify-between text-[13px]">
                <span className="font-medium">Processamento</span>
                <span className="text-muted">
                  {item.state === 'uploading' || item.state === 'draft'
                    ? 'Aguardando upload'
                    : `${p.processed} de ${p.stored} imagens processadas`}
                </span>
              </div>
              <Meter
                value={p.processing_percent}
                tone={p.processing_percent >= 100 ? 'good' : 'accent'}
              />
            </div>

            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <Numero rotulo="Analisadas" valor={p.analyzed} tom="good" />
              <Numero rotulo="Para o agrônomo" valor={p.needs_review} tom="warning" />
              <Numero rotulo="Sem modelo" valor={p.no_model} tom="warning" />
              <Numero rotulo="Falharam" valor={p.failed} tom="critical" />
            </div>
          </div>
        </Card>

        <Card>
          <CardHeader title="Procedência" />
          <dl className="space-y-3 p-4 text-[13px]">
            <Linha rotulo="Origem" valor={collectionSource(item.source)} />
            <Linha rotulo="Tipo" valor={collectionKind(item.kind)} />
            <Linha rotulo="Captura" valor={capturePlatform(item.platform)} />
            <Linha rotulo="Operador" valor={item.operator_name ?? 'não informado'} />
            <Linha rotulo="Cultura" valor={item.crop ?? '—'} />
            <Linha rotulo="Modelo" valor={item.model_key ?? 'nenhum treinado atende'} />
            <Linha rotulo="Upload concluído" valor={fmt.dateTime(item.upload_completed_at)} />
            <Linha rotulo="Processamento" valor={fmt.dateTime(item.processing_finished_at)} />
            <Linha rotulo="Publicada" valor={fmt.dateTime(item.released_at)} />
            {item.notes && <p className="border-t border-line-soft pt-3 text-muted">{item.notes}</p>}
          </dl>
        </Card>
      </div>

      {trabalho && (
        <Card className="mt-4">
          <CardHeader
            title="Fila de processamento"
            actions={
              trabalho.state === 'failed' ? (
                <Button variant="ghost" onClick={() => tentarDeNovo.mutate(trabalho.id)}>
                  <RefreshCw className="size-4" aria-hidden />
                  Tentar de novo
                </Button>
              ) : null
            }
          />
          <div className="flex flex-wrap items-center gap-4 p-4 text-[13px]">
            <Badge tone={jobStateTone(trabalho.state)}>{jobState(trabalho.state)}</Badge>
            <span className="text-muted">
              {trabalho.progress_done}/{trabalho.progress_total} · tentativa {trabalho.attempts} de{' '}
              {trabalho.max_attempts}
            </span>
            {trabalho.locked_by && <span className="text-muted">worker {trabalho.locked_by}</span>}
            {trabalho.last_error && <span className="text-critical">{trabalho.last_error}</span>}
          </div>
        </Card>
      )}

      <Card className="mt-4">
        <CardHeader
          title="Imagens"
          actions={<span className="text-[12px] text-muted">{arquivos.data?.length ?? 0} listadas</span>}
        />
        {arquivos.isLoading && <Spinner />}
        {!arquivos.isLoading && !arquivos.data?.length && (
          <Empty title="Nenhum arquivo" icon={<CheckCircle2 className="size-5" />}>
            Esta coleta não recebeu arquivo nenhum.
          </Empty>
        )}
        {!!arquivos.data?.length && (
          <div className="overflow-x-auto">
            <Table>
              <thead>
                <tr>
                  <th className={th}>Arquivo</th>
                  <th className={th}>Tamanho</th>
                  <th className={th}>Situação</th>
                  <th className={th}>Rótulo da máquina</th>
                  <th className={th}>Rótulo do agrônomo</th>
                </tr>
              </thead>
              <tbody>
                {arquivos.data.map((arquivo) => (
                  <tr key={arquivo.id}>
                    <td className={td}>
                      <span className="font-mono text-[12px]">{arquivo.filename}</span>
                      {arquivo.error && (
                        <p className="mt-1 text-[12px] text-critical">{arquivo.error}</p>
                      )}
                    </td>
                    <td className={td}>{bytes(arquivo.size_bytes)}</td>
                    <td className={td}>
                      <Badge tone={collectionFileTone(arquivo.state)}>
                        {collectionFileState(arquivo.state)}
                      </Badge>
                    </td>
                    <td className={td}>{arquivo.label ?? '—'}</td>
                    <td className={td}>{arquivo.reviewed_label ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </div>
        )}
      </Card>
    </>
  )
}

function Numero({ rotulo, valor, tom }: { rotulo: string; valor: number; tom: string }) {
  return (
    <div className="rounded-lg border border-line-soft px-3 py-2">
      <p className="text-[12px] text-muted">{rotulo}</p>
      <p className={`text-lg font-semibold ${valor ? `text-${tom}` : ''}`}>{valor}</p>
    </div>
  )
}

function Linha({ rotulo, valor }: { rotulo: string; valor: string }) {
  return (
    <div className="flex items-baseline justify-between gap-4">
      <dt className="text-muted">{rotulo}</dt>
      <dd className="text-right">{valor}</dd>
    </div>
  )
}
