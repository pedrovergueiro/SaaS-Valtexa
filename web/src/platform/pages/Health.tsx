import { useQuery } from '@tanstack/react-query'
import { AlertTriangle, CheckCircle2 } from 'lucide-react'

import { api } from '@/api/client'
import type { HealthResponse } from '@/api/types'
import { Badge, Card, CardHeader, ErrorBox, PageHeader, Spinner } from '@/components/ui'

/**
 * Estado do processo, com o detalhe que o `/health` público esconde (endereço da
 * IA, pendências de configuração por extenso). Antes ficava numa aba
 * "Plataforma" do console do cliente; infraestrutura é assunto da equipe
 * (brief, seções 30 e 34).
 */
export default function Health() {
  const health = useQuery({
    queryKey: ['platform', 'health'],
    queryFn: () => api<HealthResponse>('/v1/platform/health'),
    refetchInterval: 30_000,
  })
  const data = health.data
  const warnings = data?.warnings ?? []
  return (
    <>
      <PageHeader
        eyebrow="Console da plataforma"
        title="Saúde do sistema"
        subtitle="O que o processo da API diz de si mesmo. Atualiza a cada 30 s."
      />
      <Card>
        <CardHeader title="Processo da API" subtitle="Detalhe completo, só para a equipe ValTexa." />
        <ErrorBox error={health.error} className="mx-5 mb-4" />
        {health.isLoading && <Spinner />}
        {data && (
          <div className="px-5 pb-5">
            <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-2.5 text-[13px]">
              <dt className="text-muted">Ambiente</dt>
              <dd>
                <Badge tone={data.environment === 'production' ? 'good' : 'info'}>{data.environment}</Badge>
              </dd>
              <dt className="text-muted">Protocolo dos robôs</dt>
              <dd className="num">v{data.protocol_version}</dd>
              <dt className="text-muted">Banco</dt>
              <dd>{data.database}</dd>
              <dt className="text-muted">Inferência</dt>
              <dd className="num break-all">{data.inference}</dd>
              <dt className="text-muted">Eventos pendentes</dt>
              <dd className="num">{data.pending_events}</dd>
            </dl>
            <div className="mt-5">
              <div className="mb-2 text-[13px] font-medium">Pendências para produção</div>
              {warnings.length === 0 ? (
                <div className="flex items-center gap-2 text-[13px] text-ink-2">
                  <CheckCircle2 className="size-4 text-good" aria-hidden /> Nenhuma.
                </div>
              ) : (
                <ul className="flex flex-col gap-2">
                  {warnings.map((warning) => (
                    <li key={warning} className="flex items-start gap-2 text-[13px]">
                      <AlertTriangle className="mt-0.5 size-4 shrink-0 text-warning" aria-hidden />
                      {warning}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        )}
      </Card>
    </>
  )
}
