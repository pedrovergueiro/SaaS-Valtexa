import { Package } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'

import { api } from '@/api/client'
import { useApiMutation } from '@/api/queries'
import { useAuth } from '@/auth/AuthProvider'
import { Button, Card, CardHeader, Empty, ErrorBox, PageHeader, Spinner } from '@/components/ui'
import { type Plano, type PlanoResumo } from '@/lib/planejamento'
import { ListaDePlanos } from '@/pages/Planejamento'

/** Planejamento de insumos (8.3): demanda pelo histórico de aplicações, com intervalo. */
export default function PlanejamentoInsumos() {
  const { can } = useAuth()
  const navigate = useNavigate()
  const chave = ['planejamento', 'insumos']
  const lista = useQuery({ queryKey: chave, queryFn: () => api<PlanoResumo[]>('/v1/planejamento?tipo=insumos') })
  const gerar = useApiMutation(() => api<Plano>('/v1/planejamento/insumos', { method: 'POST', body: {} }), [chave])
  return (
    <>
      <PageHeader
        eyebrow="Cérebro agronômico"
        title="Planejamento de insumos"
        subtitle="Cenários de consumo a partir das aplicações concluídas, com faixa p10–p90, o comprometido pelas aplicações aprovadas e o estoque dos lotes válidos. Sem histórico, o plano diz que não dá para estimar."
      />
      {can('planejamento:generate') && (
        <Card className="mb-4">
          <CardHeader title="Pedir plano" subtitle="Horizonte de 30 dias e histórico de 365, por padrão (premissas do plano)." />
          <div className="px-5 pb-5">
            <Button variant="primary" icon={<Package className="size-4" />} loading={gerar.isPending} onClick={() => gerar.mutate(undefined, { onSuccess: (p) => navigate(`/planejamento/${p.id}`) })}>
              Plano de insumos
            </Button>
          </div>
          <ErrorBox error={gerar.error} className="mx-5 mb-4" />
        </Card>
      )}
      <ErrorBox error={lista.error} className="mb-4" />
      {lista.isLoading && <Spinner />}
      {lista.data && !lista.data.length && <Empty title="Nenhum plano de insumos">Peça o primeiro.</Empty>}
      {!!lista.data?.length && <ListaDePlanos planos={lista.data} />}
    </>
  )
}
