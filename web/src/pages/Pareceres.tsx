import { ArrowLeft, Brain } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'

import { api } from '@/api/client'
import { useApiMutation, useField } from '@/api/queries'
import { useAuth } from '@/auth/AuthProvider'
import { Badge, Button, Card, CardHeader, Empty, ErrorBox, FormField, PageHeader, Spinner, Table, td, th } from '@/components/ui'
import { fmt } from '@/lib/format'
import { modoTexto, type Parecer, type ParecerResumo } from '@/lib/parecer'

/**
 * Pareceres do cérebro agronômico (rodada 4, 8.2) de um talhão: a lista e o pedido de um novo,
 * por planta (id da fusão) ou por observação. O parecer é apoio à decisão — não autoriza nada.
 */
export default function Pareceres() {
  const { id = '' } = useParams()
  const { can } = useAuth()
  const navigate = useNavigate()
  const field = useField(id)
  const chave = ['fields', id, 'pareceres']
  const lista = useQuery({ queryKey: chave, queryFn: () => api<ParecerResumo[]>(`/v1/fields/${id}/pareceres`) })
  const [caso, setCaso] = useState<'planta' | 'observacao'>('planta')
  const [ref, setRef] = useState('')
  const gerar = useApiMutation(
    () =>
      api<Parecer>(`/v1/fields/${id}/pareceres`, {
        method: 'POST',
        body: caso === 'planta' ? { caso, plant_ref: ref.trim() } : { caso, observation_id: ref.trim() },
      }),
    [chave],
  )

  return (
    <>
      <Link to={`/talhoes/${id}`} className="mb-3 inline-flex items-center gap-1.5 text-[13px] text-muted hover:text-ink">
        <ArrowLeft className="size-4" aria-hidden /> Talhão
      </Link>
      <PageHeader
        eyebrow="Cérebro agronômico"
        title={`Pareceres · ${field.data?.name ?? 'Talhão'}`}
        subtitle="Evidências, hipóteses alternativas, limitações e fontes de cada caso. O parecer explica e propõe; quem valida é o agrônomo, quem libera é o Safety Engine."
      />
      {can('parecer:generate') && (
        <Card className="mb-4">
          <CardHeader title="Pedir parecer" subtitle="Sem provedor de linguagem ligado, o texto sai do compositor determinístico." />
          <form
            className="flex flex-wrap items-end gap-3 px-5 pb-5"
            onSubmit={(e) => {
              e.preventDefault()
              gerar.mutate(undefined, { onSuccess: (p) => navigate(`/pareceres/${p.id}`) })
            }}
          >
            <FormField label="Caso">
              <select className="input" value={caso} onChange={(e) => setCaso(e.target.value as 'planta' | 'observacao')}>
                <option value="planta">Planta</option>
                <option value="observacao">Observação</option>
              </select>
            </FormField>
            <FormField label={caso === 'planta' ? 'Planta (id da fusão)' : 'Observação (id)'}>
              <input className="input" value={ref} onChange={(e) => setRef(e.target.value)} placeholder={caso === 'planta' ? 'L22-P0114' : ''} maxLength={64} />
            </FormField>
            <Button type="submit" variant="primary" icon={<Brain className="size-4" />} loading={gerar.isPending} disabled={!ref.trim()}>
              Gerar parecer
            </Button>
          </form>
          <ErrorBox error={gerar.error} className="mx-5 mb-4" />
        </Card>
      )}
      <ErrorBox error={lista.error} className="mb-4" />
      {lista.isLoading && <Spinner />}
      {lista.data && !lista.data.length && <Empty title="Nenhum parecer neste talhão">Peça um parecer de uma planta ou observação.</Empty>}
      {!!lista.data?.length && (
        <Card>
          <Table>
            <thead>
              <tr>
                <th className={th}>Gerado</th>
                <th className={th}>Caso</th>
                <th className={th}>Hipótese principal</th>
                <th className={th}>Alternativas</th>
                <th className={th}>Pendências</th>
                <th className={th}>Modo</th>
                <th className={th}>Estado</th>
              </tr>
            </thead>
            <tbody>
              {lista.data.map((p) => (
                <tr key={p.id} className="cursor-pointer hover:bg-raised" onClick={() => navigate(`/pareceres/${p.id}`)}>
                  <td className={td}>{fmt.dateTime(p.gerado_em)}</td>
                  <td className={td}>{p.plant_ref ?? p.observation_id}</td>
                  <td className={td}>{p.hipotese_principal ?? '—'}</td>
                  <td className={td}>{p.alternativas.join(', ') || '—'}</td>
                  <td className={td}>{p.pendencias}</td>
                  <td className={td}>{modoTexto(p)}</td>
                  <td className={td}>
                    <Badge tone={p.estado === 'revisado' ? 'good' : 'warning'}>{p.estado === 'revisado' ? 'Revisado' : 'Aguardando revisão'}</Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </Table>
        </Card>
      )}
    </>
  )
}
