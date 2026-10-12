import { Images, Info } from 'lucide-react'
import { useState } from 'react'

import { useCollectionFiles, useCollections } from '@/api/queries'
import { AuthImage } from '@/components/AuthImage'
import {
  Badge,
  Card,
  CardHeader,
  Empty,
  ErrorBox,
  PageHeader,
  Spinner,
} from '@/components/ui'
import { cn } from '@/lib/cn'
import { fmt } from '@/lib/format'
import { collectionKind, disease } from '@/lib/labels'

/**
 * As coletas, do lado do produtor.
 *
 * Ele não vê upload, fila nem worker: para ele a coleta é uma data, um talhão e
 * um resultado. O que ele **vê sem rodeio** é o que a plataforma não conseguiu
 * responder — uma classificação inventada seria pior do que a ausência dela.
 */
export default function Collections() {
  const coletas = useCollections()
  const [aberta, setAberta] = useState<string | null>(null)
  const selecionada = aberta ?? coletas.data?.[0]?.id ?? null

  return (
    <>
      <PageHeader
        title="Coletas"
        subtitle="Cada passagem de imagem pela sua lavoura, com o que foi encontrado."
      />

      <ErrorBox error={coletas.error} className="mb-4" />
      {coletas.isLoading && <Spinner />}

      {!coletas.isLoading && !coletas.data?.length && (
        <Card>
          <Empty title="Nenhuma coleta publicada" icon={<Images className="size-5" />}>
            Assim que uma coleta do seu talhão estiver analisada, ela aparece aqui.
          </Empty>
        </Card>
      )}

      {!!coletas.data?.length && (
        <div className="grid gap-4 lg:grid-cols-[300px_1fr]">
          <Card className="max-h-[calc(100dvh-14rem)] overflow-y-auto">
            <ul>
              {coletas.data.map((item) => (
                <li key={item.id}>
                  <button
                    type="button"
                    onClick={() => setAberta(item.id)}
                    className={cn(
                      'w-full border-b border-line-soft px-4 py-3 text-left transition hover:bg-surface-2',
                      selecionada === item.id && 'bg-surface-2',
                    )}
                  >
                    <p className="text-sm font-medium">{fmt.date(item.collected_on)}</p>
                    <p className="text-[12px] text-muted">
                      {item.field_name} · {collectionKind(item.kind)} · {item.progress.files} imagens
                    </p>
                  </button>
                </li>
              ))}
            </ul>
          </Card>

          {selecionada && <Detalhe id={selecionada} />}
        </div>
      )}
    </>
  )
}

function Detalhe({ id }: { id: string }) {
  const coletas = useCollections()
  const arquivos = useCollectionFiles(id)
  const item = coletas.data?.find((linha) => linha.id === id)
  if (!item) return null

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader
          title={`${item.field_name ?? 'Talhão'} · ${fmt.date(item.collected_on)}`}
          actions={<Badge tone="neutral">{item.progress.files} imagens</Badge>}
        />
        <div className="p-4 text-[13px] text-muted">
          {item.operator_name && <p>Imagens coletadas por {item.operator_name}.</p>}
          {item.notes && <p className="mt-1">{item.notes}</p>}
        </div>
      </Card>

      {item.no_model_reason && (
        <Card className="border-warning/40">
          <div className="flex items-start gap-3 p-4">
            <Info className="mt-0.5 size-5 shrink-0 text-warning" aria-hidden />
            <div className="space-y-1 text-[13px]">
              <p className="font-medium text-fg">
                Estas imagens não passaram por análise automática
              </p>
              <p className="text-muted">
                Ainda não existe modelo treinado para este tipo de imagem nesta cultura. As fotos
                estão guardadas e foram avaliadas por um agrônomo, não por um classificador.
              </p>
            </div>
          </div>
        </Card>
      )}

      <Card>
        <CardHeader title="Imagens" />
        {arquivos.isLoading && <Spinner />}
        <div className="grid grid-cols-2 gap-3 p-4 sm:grid-cols-3 lg:grid-cols-4">
          {(arquivos.data ?? []).map((arquivo) => (
            <figure key={arquivo.id} className="space-y-1">
              {arquivo.observation_id && (
                <AuthImage
                  path={`/v1/observations/${arquivo.observation_id}/image`}
                  alt={arquivo.filename}
                  className="aspect-square w-full rounded-lg object-cover"
                />
              )}
              <figcaption className="text-[12px] text-muted">
                {arquivo.reviewed_label ? (
                  <span className="text-fg">{disease(arquivo.reviewed_label)}</span>
                ) : arquivo.label ? (
                  disease(arquivo.label)
                ) : (
                  'sem classificação'
                )}
              </figcaption>
            </figure>
          ))}
        </div>
      </Card>
    </div>
  )
}
