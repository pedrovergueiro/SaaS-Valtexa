import { ArrowLeft, CheckCircle2 } from 'lucide-react'
import { Link, useParams } from 'react-router-dom'

import { useField, useFieldHistory } from '@/api/queries'
import { Badge, Card, Empty, ErrorBox, PageHeader, Spinner } from '@/components/ui'
import { cycleClosed, describe, STAGES, stageCounts, stageLabel, stageTone, stepLink } from '@/lib/fieldHistory'
import { fmt } from '@/lib/format'

/**
 * Linha do tempo do talhão (brief, seção 6): o ciclo inteiro, do mais novo ao mais
 * antigo — missão → ocorrências → prescrição → aprovação → aplicação → verificação.
 */
export default function FieldHistory() {
  const { id = '' } = useParams()
  const field = useField(id)
  const history = useFieldHistory(id)
  const passos = history.data ?? []
  const contagem = stageCounts(passos)

  return (
    <>
      <Link to={`/talhoes/${id}`} className="mb-3 inline-flex items-center gap-1.5 text-[13px] text-muted hover:text-ink">
        <ArrowLeft className="size-4" aria-hidden /> Talhão
      </Link>
      <PageHeader
        eyebrow="Linha do tempo"
        title={field.data?.name ?? 'Talhão'}
        subtitle="Missão → ocorrências → prescrição → aprovação → aplicação → verificação, com o vínculo entre cada passo."
        actions={
          passos.length > 0 && (
            <Badge tone={cycleClosed(passos) ? 'good' : 'warning'}>
              {cycleClosed(passos) ? 'Último ciclo verificado' : 'Último ciclo em aberto'}
            </Badge>
          )
        }
      />
      <div className="mb-4 flex flex-wrap gap-2">
        {STAGES.map((s) => (
          <Badge key={s} tone={contagem[s] ? stageTone(s) : 'neutral'}>
            {stageLabel(s)} · {contagem[s]}
          </Badge>
        ))}
      </div>
      <ErrorBox error={history.error} className="mb-4" />
      {history.isLoading && <Spinner />}
      {!history.isLoading && !passos.length && (
        <Empty title="Nada aconteceu neste talhão ainda">A primeira varredura abre a linha do tempo.</Empty>
      )}
      {!!passos.length && (
        <Card className="p-5">
          <ol className="relative ml-2 border-l border-line" data-linha-do-tempo>
            {passos.map((p, i) => {
              const link = stepLink(p)
              const corpo = (
                <>
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge tone={stageTone(p.stage)}>{stageLabel(p.stage)}</Badge>
                    <span className="text-[12px] text-muted">{p.at ? fmt.dateTime(p.at) : '—'}</span>
                    {p.stage === 'verificacao' && p.conclusion === 'improved' && <CheckCircle2 className="size-4 text-good" aria-hidden />}
                  </div>
                  <div className="mt-1 text-[13px]">{describe(p)}</div>
                  {p.origin_mission_id && (
                    <div className="mt-0.5 text-[12px] text-muted">
                      origem: varredura{' '}
                      <Link to={`/missoes/${p.origin_mission_id}/relatorio`} className="hover:underline">
                        {fmt.shortId(p.origin_mission_id)}
                      </Link>
                    </div>
                  )}
                </>
              )
              return (
                <li key={`${p.stage}-${p.mission_id ?? p.application_id ?? p.verification_id ?? i}-${i}`} className="mb-4 ml-5">
                  <span
                    className="absolute -left-[5px] mt-1.5 size-2.5 rounded-full border border-surface"
                    style={{ background: `var(--${stageTone(p.stage) === 'accent' ? 'accent' : stageTone(p.stage)})` }}
                    aria-hidden
                  />
                  {corpo}
                  {link && (
                    <Link
                      to={p.stage === 'ocorrencias' ? `/missoes/${p.mission_id}/relatorio` : link}
                      className="mt-0.5 inline-block text-[12px] text-accent hover:underline"
                    >
                      {p.stage === 'ocorrencias' ? 'Abrir o relatório' : p.stage === 'aplicacao' ? 'Ver aplicações' : 'Abrir a missão'}
                    </Link>
                  )}
                </li>
              )
            })}
          </ol>
        </Card>
      )}
    </>
  )
}
