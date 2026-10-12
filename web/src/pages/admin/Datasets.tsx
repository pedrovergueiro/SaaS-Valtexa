import { Database, Snowflake } from 'lucide-react'
import { useState } from 'react'

import { useDatasets, useFreezeDatasetVersion, useModelCatalog } from '@/api/queries'
import type { DatasetOut } from '@/api/types'
import {
  Badge,
  Button,
  Card,
  CardHeader,
  Empty,
  ErrorBox,
  FormField,
  Modal,
  PageHeader,
  Spinner,
  Table,
  td,
  th,
} from '@/components/ui'
import { capturePlatform } from '@/lib/labels'

/**
 * O dataset proprietário e o catálogo de modelos.
 *
 * As duas coisas aparecem na mesma tela de propósito: o valor de um conjunto
 * está em relação ao modelo que ele pretende treinar. A linha do
 * `aerial-canopy` sem pesos, ao lado de um conjunto aéreo crescendo, é a
 * fotografia exata de onde a ValTexa está.
 */
export default function Datasets() {
  const datasets = useDatasets()
  const catalogo = useModelCatalog()
  const [congelando, setCongelando] = useState<DatasetOut | null>(null)

  return (
    <>
      <PageHeader
        title="Dataset e modelos"
        subtitle="O que a operação produz de mais valioso: imagem rotulada por agrônomo, inclusive de coisa que nenhum modelo conhece."
      />

      <ErrorBox error={datasets.error} className="mb-4" />

      <Card className="mb-4">
        <CardHeader
          title="Catálogo ValTexa-B"
          actions={<span className="text-[12px] text-muted">espelho de VALTEXA-B/MODELS.md</span>}
        />
        {catalogo.isLoading && <Spinner />}
        {!!catalogo.data?.length && (
          <div className="overflow-x-auto">
            <Table>
              <thead>
                <tr>
                  <th className={th}>Modelo</th>
                  <th className={th}>Culturas</th>
                  <th className={th}>Captura</th>
                  <th className={th}>Estado</th>
                </tr>
              </thead>
              <tbody>
                {catalogo.data.map((modelo) => (
                  <tr key={modelo.key}>
                    <td className={td}>
                      <span className="font-mono text-[12px]">{modelo.key}</span>
                    </td>
                    <td className={td}>{modelo.crops.join(', ')}</td>
                    <td className={td}>{capturePlatform(modelo.platform)}</td>
                    <td className={td}>
                      <Badge tone={modelo.trained ? 'good' : 'warning'}>
                        {modelo.trained ? 'Treinado' : 'Sem pesos'}
                      </Badge>
                      {modelo.caveat && (
                        <span className="ml-2 text-[12px] text-muted">{modelo.caveat}</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </div>
        )}
      </Card>

      {datasets.isLoading && <Spinner />}
      {!datasets.isLoading && !datasets.data?.length && (
        <Card>
          <Empty title="Nenhum conjunto ainda" icon={<Database className="size-5" />}>
            O primeiro rótulo que um agrônomo escrever cria o conjunto daquela cultura e plataforma.
          </Empty>
        </Card>
      )}

      <div className="grid gap-4 md:grid-cols-2">
        {(datasets.data ?? []).map((conjunto) => (
          <Card key={conjunto.id}>
            <CardHeader
              title={conjunto.key}
              actions={
                <Button variant="ghost" onClick={() => setCongelando(conjunto)}>
                  <Snowflake className="size-4" aria-hidden />
                  Congelar corte
                </Button>
              }
            />
            <div className="space-y-3 p-4 text-[13px]">
              <div className="flex flex-wrap gap-2">
                <Badge tone="neutral">{conjunto.crop}</Badge>
                <Badge tone="neutral">{capturePlatform(conjunto.platform)}</Badge>
                <Badge tone="info">{conjunto.samples} amostras</Badge>
                {conjunto.disagreements > 0 && (
                  <Badge tone="warning">{conjunto.disagreements} contradizem a máquina</Badge>
                )}
                {conjunto.sem_modelo > 0 && (
                  <Badge tone="accent">{conjunto.sem_modelo} sem opinião da máquina</Badge>
                )}
              </div>

              <ul className="space-y-1">
                {Object.entries(conjunto.labels)
                  .sort((a, b) => b[1] - a[1])
                  .map(([rotulo, quantidade]) => (
                    <li key={rotulo} className="flex justify-between gap-4">
                      <span>{rotulo}</span>
                      <span className="text-muted">{quantidade}</span>
                    </li>
                  ))}
              </ul>

              <p className="text-[12px] text-muted">
                {conjunto.versions} corte(s) congelado(s) · {conjunto.candidates} amostra(s) ainda
                fora de qualquer corte
              </p>
            </div>
          </Card>
        ))}
      </div>

      {congelando && (
        <CongelarCorte conjunto={congelando} onClose={() => setCongelando(null)} />
      )}
    </>
  )
}

function CongelarCorte({ conjunto, onClose }: { conjunto: DatasetOut; onClose: () => void }) {
  const congelar = useFreezeDatasetVersion(conjunto.id)
  const [versao, setVersao] = useState('')
  const [notas, setNotas] = useState('')

  return (
    <Modal
      open
      onClose={onClose}
      title={`Congelar corte de ${conjunto.key}`}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancelar
          </Button>
          <Button
            disabled={!versao || congelar.isPending}
            onClick={async () => {
              await congelar.mutateAsync({ version: versao, notes: notas || undefined })
              onClose()
            }}
          >
            Congelar {conjunto.samples} amostras
          </Button>
        </>
      }
    >
      <ErrorBox error={congelar.error} className="mb-3" />
      <p className="mb-4 text-[13px] text-muted">
        Um corte guarda a lista exata de amostras, não um filtro por data. É o que torna dois treinos
        comparáveis: amostras excluídas depois não mudam o que este corte continha. A plataforma não
        treina — o corte é o que vai para o ValTexa-B.
      </p>
      <div className="space-y-3">
        <FormField label="Versão" hint="'v1', '2026.09.1'.">
          <input
            className="input"
            value={versao}
            onChange={(evento) => setVersao(evento.target.value)}
            placeholder="v1"
          />
        </FormField>
        <FormField label="Notas">
          <textarea
            className="input min-h-20"
            value={notas}
            onChange={(evento) => setNotas(evento.target.value)}
            placeholder="O que entrou neste corte e por quê."
          />
        </FormField>
      </div>
    </Modal>
  )
}
