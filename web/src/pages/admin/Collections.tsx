import { Boxes, Plus } from 'lucide-react'
import { Link } from 'react-router-dom'

import { useAdminCollections } from '@/api/queries'
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
import { bytes, collectionKind, collectionState, collectionStateTone } from '@/lib/labels'

/** As coletas do cliente ativo, do ponto de vista de quem opera a plataforma. */
export default function Collections() {
  const coletas = useAdminCollections()

  return (
    <>
      <PageHeader
        title="Coletas"
        subtitle="Lotes de imagens que entraram na plataforma. No MVP, o voo é de operador terceirizado e a importação é manual."
        actions={
          <Link to="/plataforma/coletas/nova">
            <Button>
              <Plus className="size-4" aria-hidden />
              Importar coleta
            </Button>
          </Link>
        }
      />

      <ErrorBox error={coletas.error} className="mb-4" />
      {coletas.isLoading && <Spinner />}

      {!coletas.isLoading && !coletas.data?.length && (
        <Card>
          <Empty title="Nenhuma coleta" icon={<Boxes className="size-5" />}>
            Quando o operador entregar as imagens de um voo, importe por aqui.
          </Empty>
        </Card>
      )}

      {!!coletas.data?.length && (
        <Card>
          <CardHeader title={`${coletas.data.length} coleta(s)`} />
          <div className="overflow-x-auto">
            <Table>
              <thead>
                <tr>
                  <th className={th}>Código</th>
                  <th className={th}>Talhão</th>
                  <th className={th}>Data</th>
                  <th className={th}>Tipo</th>
                  <th className={th}>Arquivos</th>
                  <th className={th}>Situação</th>
                  <th className={th}>Processamento</th>
                </tr>
              </thead>
              <tbody>
                {coletas.data.map((item) => (
                  <tr key={item.id}>
                    <td className={td}>
                      <Link to={`/plataforma/coletas/${item.id}`} className="font-mono text-[12px] underline-offset-2 hover:underline">
                        {item.code}
                      </Link>
                    </td>
                    <td className={td}>{item.field_name ?? '—'}</td>
                    <td className={td}>{fmt.date(item.collected_on)}</td>
                    <td className={td}>{collectionKind(item.kind)}</td>
                    <td className={td}>
                      {item.progress.files} · {bytes(item.progress.bytes_total)}
                    </td>
                    <td className={td}>
                      <Badge tone={collectionStateTone(item.state)}>
                        {collectionState(item.state)}
                      </Badge>
                      {!item.model_key && (
                        <span className="ml-2 text-[12px] text-warning">sem modelo</span>
                      )}
                    </td>
                    <td className={`${td} w-40`}>
                      <Meter value={item.progress.processing_percent} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </div>
        </Card>
      )}
    </>
  )
}
