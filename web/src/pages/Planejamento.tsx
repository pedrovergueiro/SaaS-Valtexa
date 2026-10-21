import { ArrowLeft, ClipboardList, Route } from 'lucide-react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'

import { api } from '@/api/client'
import { useApiMutation, useField } from '@/api/queries'
import { useAuth } from '@/auth/AuthProvider'
import { Badge, Button, Card, CardHeader, Empty, ErrorBox, PageHeader, Spinner, Table, td, th } from '@/components/ui'
import { fmt } from '@/lib/format'
import { TIPOS, type Plano, type PlanoResumo } from '@/lib/planejamento'

/**
 * Planejamento de apoio à decisão de um talhão (rodada 4, 8.3): o plano fitossanitário e o
 * robótico. Cada plano sai com as premissas registradas e espera a revisão humana; nenhum
 * cria missão nem aprova aplicação.
 */
export default function Planejamento() {
  const { id = '' } = useParams()
  const { can } = useAuth()
  const navigate = useNavigate()
  const field = useField(id)
  const chave = ['planejamento', id]
  const lista = useQuery({ queryKey: chave, queryFn: () => api<PlanoResumo[]>(`/v1/planejamento?field_id=${encodeURIComponent(id)}`) })
  const fito = useApiMutation(() => api<Plano>(`/v1/fields/${id}/planejamento/fitossanitario`, { method: 'POST', body: {} }), [chave])
  const rob = useApiMutation(() => api<Plano>(`/v1/fields/${id}/planejamento/robotico`, { method: 'POST', body: {} }), [chave])
  const abre = (p: Plano) => navigate(`/planejamento/${p.id}`)

  return (
    <>
      <Link to={`/talhoes/${id}`} className="mb-3 inline-flex items-center gap-1.5 text-[13px] text-muted hover:text-ink">
        <ArrowLeft className="size-4" aria-hidden /> Talhão
      </Link>
      <PageHeader
        eyebrow="Cérebro agronômico"
        title={`Planejamento · ${field.data?.name ?? 'Talhão'}`}
        subtitle="Apoio à decisão com premissas registradas. O agente propõe; a pessoa responsável revisa e age pelos fluxos de sempre; o Safety Engine libera."
      />
      {can('planejamento:generate') && (
        <Card className="mb-4">
          <CardHeader title="Pedir plano" subtitle="Com os padrões da plataforma; cada valor usado aparece nas premissas do plano." />
          <div className="flex flex-wrap gap-3 px-5 pb-5">
            <Button variant="primary" icon={<ClipboardList className="size-4" />} loading={fito.isPending} onClick={() => fito.mutate(undefined, { onSuccess: abre })}>
              Plano fitossanitário
            </Button>
            <Button icon={<Route className="size-4" />} loading={rob.isPending} onClick={() => rob.mutate(undefined, { onSuccess: abre })}>
              Plano robótico
            </Button>
            <Link to="/planejamento/insumos">
              <Button>Insumos</Button>
            </Link>
          </div>
          <ErrorBox error={fito.error ?? rob.error} className="mx-5 mb-4" />
        </Card>
      )}
      <ErrorBox error={lista.error} className="mb-4" />
      {lista.isLoading && <Spinner />}
      {lista.data && !lista.data.length && <Empty title="Nenhum plano neste talhão">Peça um plano fitossanitário ou robótico.</Empty>}
      {!!lista.data?.length && <ListaDePlanos planos={lista.data} />}
    </>
  )
}

export function ListaDePlanos({ planos }: { planos: PlanoResumo[] }) {
  const navigate = useNavigate()
  return (
    <Card>
      <Table>
        <thead>
          <tr>
            <th className={th}>Gerado</th>
            <th className={th}>Tipo</th>
            <th className={th}>Premissas</th>
            <th className={th}>Motor</th>
            <th className={th}>Estado</th>
          </tr>
        </thead>
        <tbody>
          {planos.map((p) => (
            <tr key={p.id} className="cursor-pointer hover:bg-raised" onClick={() => navigate(`/planejamento/${p.id}`)}>
              <td className={td}>{fmt.dateTime(p.gerado_em)}</td>
              <td className={td}>{TIPOS[p.tipo]}</td>
              <td className={td}>{p.premissas}</td>
              <td className={td}>{p.versao_motor}</td>
              <td className={td}>
                <Badge tone={p.estado === 'revisado' ? 'good' : 'warning'}>{p.estado === 'revisado' ? 'Revisado' : 'Proposto'}</Badge>
              </td>
            </tr>
          ))}
        </tbody>
      </Table>
    </Card>
  )
}
