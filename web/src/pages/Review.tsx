import { ChevronLeft, ChevronRight, Keyboard, ScanSearch, Trash2 } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'

import { useFields, useReviewDiagnosis, useReviewQueue } from '@/api/queries'
import type { DiagnosisOut } from '@/api/types'
import { useAuth } from '@/auth/AuthProvider'
import { AuthImage } from '@/components/AuthImage'
import { Badge, Button, Card, CardHeader, Empty, ErrorBox, FormField, Meter, PageHeader, Spinner } from '@/components/ui'
import { cn } from '@/lib/cn'
import { fmt } from '@/lib/format'
import { agreement, disease, KNOWN_LABELS } from '@/lib/labels'

const NOVELTY_THRESHOLD = 1.0

/**
 * A fila do agrônomo.
 *
 * O que chega aqui é o que a IA não conseguiu fechar sozinha — discordância,
 * confiança baixa ou imagem que destoa do que os modelos conhecem. O rótulo que
 * o agrônomo escreve **não precisa existir no catálogo**: é assim que uma doença
 * nova entra no dataset próprio.
 */
export default function Review() {
  const { can } = useAuth()
  const queue = useReviewQueue()
  const fields = useFields()
  const [index, setIndex] = useState(0)
  const items = queue.data ?? []
  const current = items[Math.min(index, Math.max(0, items.length - 1))]
  const fieldName = useMemo(() => new Map(fields.data?.map((item) => [item.id, item.name])), [fields.data])

  useEffect(() => {
    if (index >= items.length && items.length > 0) setIndex(items.length - 1)
  }, [index, items.length])

  return (
    <>
      <PageHeader
        title="Fila do agrônomo"
        subtitle="O que a IA não fechou sozinha, do que mais destoa do conhecido para o que menos. Seu rótulo pode ser uma doença que o modelo nunca viu."
        actions={<Badge tone={items.length ? 'warning' : 'good'}>{items.length} aguardando</Badge>}
      />

      <ErrorBox error={queue.error} className="mb-4" />
      {queue.isLoading && <Spinner />}

      {!queue.isLoading && items.length === 0 && (
        <Card>
          <Empty title="Fila vazia" icon={<ScanSearch className="size-5" />}>
            Nada esperando diagnóstico. Quando a IA discordar de si mesma ou encontrar algo fora do catálogo, aparece
            aqui.
          </Empty>
        </Card>
      )}

      {current && (
        <div className="grid gap-4 xl:grid-cols-[320px_1fr]">
          <Card className="hidden max-h-[calc(100dvh-14rem)] overflow-y-auto xl:block">
            <ul>
              {items.map((item, position) => (
                <li key={item.id}>
                  <button
                    type="button"
                    onClick={() => setIndex(position)}
                    className={cn(
                      'flex w-full items-center gap-3 border-b border-line-soft px-3 py-2.5 text-left',
                      item.id === current.id ? 'bg-accent-soft' : 'hover:bg-raised',
                    )}
                  >
                    <AuthImage path={`/v1/observations/${item.observation_id}/image`} alt="" className="size-12 shrink-0 rounded-lg" />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-[13px] font-medium">{disease(item.label)}</span>
                      <span className="block truncate text-[12px] text-muted">{fieldName.get(item.field_id) ?? '—'}</span>
                    </span>
                    {item.novelty_score != null && (
                      <span className="num text-[11px] text-muted" title="Pontuação de novidade">
                        {fmt.number(item.novelty_score, 2)}
                      </span>
                    )}
                  </button>
                </li>
              ))}
            </ul>
          </Card>

          <ReviewItem
            key={current.id}
            item={current}
            position={index}
            total={items.length}
            fieldName={fieldName.get(current.field_id)}
            canReview={can('diagnosis:review')}
            onPrevious={() => setIndex((value) => Math.max(0, value - 1))}
            onNext={() => setIndex((value) => Math.min(items.length - 1, value + 1))}
          />
        </div>
      )}
    </>
  )
}

function ReviewItem({
  item,
  position,
  total,
  fieldName,
  canReview,
  onPrevious,
  onNext,
}: {
  item: DiagnosisOut
  position: number
  total: number
  fieldName?: string
  canReview: boolean
  onPrevious: () => void
  onNext: () => void
}) {
  const review = useReviewDiagnosis()
  const [label, setLabel] = useState(item.label ?? '')
  const [notes, setNotes] = useState('')
  const valid = /^[A-Za-z][A-Za-z0-9_]{0,63}$/.test(label)
  const novel = (item.novelty_score ?? 0) > NOVELTY_THRESHOLD
  const machine = (item.detections ?? []).filter((detection) => detection.source !== 'human')

  const submit = (confirmed: boolean, forcedLabel?: string) =>
    review.mutate({ id: item.id, label: forcedLabel ?? label, confirmed, notes })

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement
      if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA') return
      if (event.key === 'ArrowLeft' || event.key === 'k') onPrevious()
      if (event.key === 'ArrowRight' || event.key === 'j') onNext()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onPrevious, onNext])

  return (
    <div className="grid gap-4 lg:grid-cols-[1.2fr_1fr]">
      <Card className="overflow-hidden">
        <AuthImage path={`/v1/observations/${item.observation_id}/image`} alt="Folha em revisão" className="aspect-[4/3] w-full" />
        <div className="flex items-center justify-between gap-2 px-4 py-3">
          <div className="text-[12px] text-muted">
            {fieldName ?? '—'} · {fmt.dateTime(item.created_at)}
          </div>
          <div className="flex items-center gap-1">
            <Button size="sm" variant="ghost" onClick={onPrevious} disabled={position === 0} aria-label="Anterior">
              <ChevronLeft className="size-4" />
            </Button>
            <span className="num text-[12px] text-muted">
              {position + 1}/{total}
            </span>
            <Button size="sm" variant="ghost" onClick={onNext} disabled={position >= total - 1} aria-label="Próxima">
              <ChevronRight className="size-4" />
            </Button>
          </div>
        </div>
      </Card>

      <div className="flex flex-col gap-4">
        <Card>
          <CardHeader title="Por que está aqui" />
          <div className="flex flex-col gap-4 px-5 pb-5 text-[13px]">
            <p className="text-ink-2">{item.rationale ?? 'Sem justificativa registrada.'}</p>
            <div>
              <div className="mb-1.5 flex items-center justify-between">
                <span className="font-medium">Novidade</span>
                <span className="num">
                  {item.novelty_score != null ? fmt.number(item.novelty_score, 2) : '—'}
                  <span className="text-muted"> / limiar {fmt.number(NOVELTY_THRESHOLD, 1)}</span>
                </span>
              </div>
              <Meter value={Math.min(1, (item.novelty_score ?? 0) / 2)} tone={novel ? 'warning' : 'neutral'} label="Novidade" />
              <p className="mt-1.5 text-[12px] text-muted">
                {novel
                  ? 'Destoa do que os modelos conhecem: pode ser doença fora do catálogo, deficiência, praga ou foto ruim.'
                  : 'Parecida com o que os modelos conhecem. Atenção: uma doença nova da mesma cultura costuma cair aqui.'}
              </p>
            </div>
          </div>
        </Card>

        <Card>
          <CardHeader title="O que a IA respondeu" subtitle={`Concordância: ${agreement(item.agreement)}`} />
          <ul className="px-5 pb-5">
            {machine.map((detection) => (
              <li key={detection.id} className="border-t border-line-soft py-3 first:border-0 first:pt-0">
                <div className="flex items-center justify-between text-[13px]">
                  <span className="font-medium">{detection.label ? disease(detection.label) : 'sem resposta'}</span>
                  <span className="num text-ink-2">{detection.confidence != null ? fmt.percent(detection.confidence) : '—'}</span>
                </div>
                <div className="text-[12px] text-muted">
                  {detection.analyzer}
                  {detection.model_key ? ` · ${detection.model_key}` : ''}
                  {detection.error ? ` · ${detection.error}` : ''}
                </div>
              </li>
            ))}
          </ul>
          {item.severity != null && (
            <div className="border-t border-line-soft px-5 py-3 text-[13px]">
              <div className="flex items-center justify-between">
                <span className="font-medium">Área lesionada no quadro</span>
                <span className="num">{fmt.percent(item.severity)}</span>
              </div>
              <p className="mt-1 text-[12px] text-muted">
                Medida pela segmentação de lesão. Aproxima a severidade quando a folha preenche o quadro; não entra na
                decisão de aplicar.
              </p>
            </div>
          )}
        </Card>

        {canReview ? (
          <Card className="p-5">
            <div className="flex flex-col gap-3">
              <FormField label="Diagnóstico do agrônomo" hint="Escolha da lista ou escreva uma classe nova — ex.: Cigarrinha, Mancha_branca.">
                <input
                  className="input font-mono"
                  list="rotulos-conhecidos"
                  value={label}
                  onChange={(event) => setLabel(event.target.value.replaceAll(' ', '_'))}
                  aria-invalid={!valid}
                />
              </FormField>
              <datalist id="rotulos-conhecidos">
                {KNOWN_LABELS.map((value) => (
                  <option key={value} value={value}>
                    {disease(value)}
                  </option>
                ))}
              </datalist>
              {label && !KNOWN_LABELS.includes(label) && valid && (
                <Badge tone="info" className="self-start">
                  Classe nova — entra no dataset próprio
                </Badge>
              )}
              <FormField label="Observações">
                <textarea className="input min-h-16" value={notes} onChange={(event) => setNotes(event.target.value)} />
              </FormField>
              <ErrorBox error={review.error} />
              <div className="flex flex-wrap gap-2">
                <Button variant="primary" className="flex-1" disabled={!valid} loading={review.isPending} onClick={() => submit(true)}>
                  {label === item.label ? 'Confirmar diagnóstico' : 'Registrar diagnóstico'}
                </Button>
                <Button variant="ghost" icon={<Trash2 className="size-4" />} loading={review.isPending} onClick={() => submit(false, 'Imagem_sem_condicao')}>
                  Imagem sem condição
                </Button>
              </div>
              <div className="flex items-center gap-1.5 text-[11px] text-muted">
                <Keyboard className="size-3.5" aria-hidden /> ← → para navegar
              </div>
            </div>
          </Card>
        ) : (
          <Card className="p-5 text-[13px] text-ink-2">Só o agrônomo registra diagnóstico. Você pode acompanhar a fila.</Card>
        )}
      </div>
    </div>
  )
}
