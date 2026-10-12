import { ArrowLeft, Download, GitCompare, Image as ImageIcon, Printer } from 'lucide-react'
import { useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { useEdgeRecords, useMission, useMissionPlants, useMissionReport } from '@/api/queries'
import { AuthImage } from '@/components/AuthImage'
import { Badge, Button, Card, CardHeader, Empty, ErrorBox, Modal, PageHeader, Spinner, Stat, Table, Tabs, td, th } from '@/components/ui'
import {
  cameraOf,
  categoryLabel,
  categoryTone,
  countByCategory,
  fileUrl,
  filterRecords,
  plantOf,
  viewableFile,
  type EdgeRecord,
} from '@/lib/edgeRecords'
import { fmt } from '@/lib/format'
import { disease, missionKind } from '@/lib/labels'
import { incidenceText, outcomeLabel, plantStatusLabel, plantStatusTone, sortOccurrences, trend } from '@/lib/missionReport'
import { downloadText, reportFilename, reportToCsv } from '@/lib/reportExport'

const PAGINA = 100

/**
 * Relatório da missão (brief, seção 47): onde, quando, o que o robô viu (registros da
 * Edge AI por categoria, com a imagem original quando ela subiu), plantas, incidência,
 * recomendações, prescrição e comparação — exportável em CSV e imprimível (PDF).
 */
export default function MissionReportPage() {
  const { id = '' } = useParams()
  const mission = useMission(id)
  const report = useMissionReport(id)
  const plants = useMissionPlants(id)
  const records = useEdgeRecords({ mission_id: id, limit: 1000 })

  if (report.isLoading || mission.isLoading) return <Spinner label="Montando o relatório" />
  if (report.error || !report.data) return <ErrorBox error={report.error ?? new Error('Relatório indisponível')} />
  const r = report.data
  const todas = plants.data?.plants ?? []

  const exportar = () =>
    downloadText(
      reportFilename(r.field, r.date),
      reportToCsv(
        r as typeof r & Record<string, unknown>,
        sortOccurrences(todas.map((p) => ({ ...p, cameras: p.cameras ?? [] }))),
      ),
    )

  return (
    <>
      <Link to={`/missoes/${id}`} className="print-hide mb-3 inline-flex items-center gap-1.5 text-[13px] text-muted hover:text-ink">
        <ArrowLeft className="size-4" aria-hidden /> Missão
      </Link>
      <PageHeader
        eyebrow={<span className="num">relatório · missão {fmt.shortId(r.mission_id)}</span>}
        title={`${missionKind(r.kind ?? mission.data?.kind ?? 'scout')} · ${r.field ?? 'talhão'}`}
        subtitle={`${r.farm ?? ''}${r.crop ? ` · ${r.crop}` : ''} · ${r.date ? fmt.dateTime(r.date) : 'sem data'} · gerado ${fmt.dateTime(r.generated_at ?? new Date())}`}
        actions={
          <span className="print-hide flex flex-wrap gap-2">
            <Button icon={<Download className="size-4" />} onClick={exportar} disabled={plants.isLoading}>
              Exportar CSV
            </Button>
            <Button icon={<Printer className="size-4" />} onClick={() => window.print()}>
              Imprimir / PDF
            </Button>
            <Link to={`/missoes/comparar?nova=${id}`}>
              <Button variant="ghost" icon={<GitCompare className="size-4" />}>
                Comparar
              </Button>
            </Link>
          </span>
        }
      />

      {r.simulated && (
        <div className="mb-4 rounded-[10px] border border-warning/40 bg-warning/10 px-4 py-2.5 text-[13px]">
          <strong>Dados simulados.</strong> O robô desta missão roda sobre hardware simulado — o relatório mostra o
          caminho completo, não um resultado agronômico.
        </div>
      )}

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Imagens analisadas no robô" value={<span className="num">{fmt.number(r.images_processed)}</span>} />
        <Stat label="Plantas vistas" value={<span className="num">{r.plants_seen}</span>} />
        <Stat
          label="Incidência"
          value={<span className="num">{r.incidence.ratio == null ? '—' : fmt.percent(r.incidence.ratio, 1)}</span>}
          hint={incidenceText(r)}
        />
        <Stat
          label="Duração"
          value={<span className="num">{r.duration_min == null ? '—' : `${fmt.number(r.duration_min, 1)} min`}</span>}
          hint={`Rover ${r.rover ?? '—'} · ${fmt.hectares(r.area_ha ?? null)}`}
        />
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-[1.4fr_1fr]">
        <PlantsCard plants={todas} loading={plants.isLoading} error={plants.error} withoutPlant={plants.data?.results_without_plant ?? 0} />
        <div className="flex flex-col gap-4">
          <Card className="print-break">
            <CardHeader title="O que a Edge AI viu" subtitle="Categorias dos quadros analisados no robô e eventos da missão." />
            <div className="flex flex-wrap gap-2 px-5 pb-5">
              {Object.entries(r.edge_categories).map(([cat, n]) => (
                <Badge key={cat} tone={categoryTone(cat)}>
                  {categoryLabel(cat)} · {n}
                </Badge>
              ))}
              {Object.entries(r.events).map(([ev, n]) => (
                <Badge key={ev} tone="neutral">
                  {ev} · {n}
                </Badge>
              ))}
              {!Object.keys(r.edge_categories).length && <span className="text-[13px] text-muted">Nada sincronizado ainda.</span>}
            </div>
          </Card>
          <Card className="print-break">
            <CardHeader title="Recomendações e prescrição" />
            <div className="flex flex-col gap-2 px-5 pb-5 text-[13px]">
              {r.recommendations.map((rec) => (
                <div key={rec.decision_id}>
                  <Badge tone={rec.outcome === 'application_candidate' ? 'serious' : 'neutral'}>{outcomeLabel(rec.outcome)}</Badge>
                  {rec.rationale && <span className="ml-2 text-ink-2">{rec.rationale}</span>}
                </div>
              ))}
              {r.prescriptions.map((p) => (
                <Link key={p.mission_id} to={`/missoes/${p.mission_id}`} className="hover:underline">
                  Pulverização {p.state} · {p.rate_l_ha ?? '—'} L/ha · {p.quantity_l ?? '—'} L
                </Link>
              ))}
              {!r.recommendations.length && !r.prescriptions.length && <span className="text-muted">Nenhuma recomendação nesta missão.</span>}
            </div>
          </Card>
          <Card className="print-break">
            <CardHeader title="Em relação à passada anterior" />
            <div className="px-5 pb-5 text-[13px]">
              {r.comparison_with_previous ? (
                <>
                  <Badge tone={trend(r.comparison_with_previous.delta).tone}>{trend(r.comparison_with_previous.delta).text}</Badge>
                  <ul className="mt-2 space-y-1 text-ink-2">
                    <li>Recuperadas: {r.comparison_with_previous.recovered.join(', ') || '—'}</li>
                    <li>Persistentes: {r.comparison_with_previous.persisting.join(', ') || '—'}</li>
                    <li>Novas: {r.comparison_with_previous.new.join(', ') || '—'}</li>
                  </ul>
                </>
              ) : (
                <span className="text-muted">Primeira passada deste tipo no talhão.</span>
              )}
              {!!r.history?.length && (
                <div className="mt-3 border-t border-line-soft pt-2">
                  <div className="mb-1 text-[12px] text-muted">Histórico de incidência</div>
                  {r.history.map((h) => (
                    <Link key={h.mission_id} to={`/missoes/${h.mission_id}/relatorio`} className="flex justify-between hover:underline">
                      <span>{h.date ? fmt.date(h.date) : '—'}</span>
                      <span className="num">{h.incidence == null ? '—' : fmt.percent(h.incidence, 1)}</span>
                    </Link>
                  ))}
                </div>
              )}
            </div>
          </Card>
        </div>
      </div>

      <EdgeRecordsCard records={records.data ?? []} loading={records.isLoading} error={records.error} />
    </>
  )
}

function PlantsCard({
  plants,
  loading,
  error,
  withoutPlant,
}: {
  plants: { plant_id: string; row: number | null; status: 'doente' | 'suspeita' | 'revisar' | 'sadia'; label: string | null; frames: number; cameras?: string[] }[]
  loading: boolean
  error: unknown
  withoutPlant: number
}) {
  const [aba, setAba] = useState<'ocorrencias' | 'todas'>('ocorrencias')
  const lista = useMemo(() => {
    const ordenadas = sortOccurrences(plants.map((p) => ({ ...p, cameras: p.cameras ?? [] })))
    return aba === 'todas' ? ordenadas : ordenadas.filter((p) => p.status !== 'sadia')
  }, [plants, aba])
  return (
    <Card className="print-break overflow-hidden">
      <CardHeader
        title="Plantas"
        subtitle={`Fusão operacional por planta (Edge AI + diagnóstico da nuvem).${withoutPlant ? ` ${withoutPlant} quadro(s) sem planta identificada.` : ''}`}
        actions={
          <Tabs
            value={aba}
            onChange={setAba}
            items={[
              { value: 'ocorrencias', label: 'Ocorrências' },
              { value: 'todas', label: `Todas (${plants.length})` },
            ]}
          />
        }
      />
      <ErrorBox error={error} className="mx-5 mb-3" />
      {loading && <Spinner />}
      {!loading && !lista.length && <Empty title={aba === 'todas' ? 'Nenhuma planta vista' : 'Nenhuma ocorrência'} />}
      {!!lista.length && (
        <Table>
          <thead>
            <tr>
              <th className={th}>Planta</th>
              <th className={th}>Linha</th>
              <th className={th}>Estado</th>
              <th className={th}>Doença</th>
              <th className={th}>Quadros</th>
              <th className={th}>Câmeras</th>
            </tr>
          </thead>
          <tbody>
            {lista.map((p) => (
              <tr key={p.plant_id}>
                <td className={`${td} num font-medium`}>{p.plant_id}</td>
                <td className={`${td} num`}>{p.row ?? '—'}</td>
                <td className={td}>
                  <Badge tone={plantStatusTone(p.status)}>{plantStatusLabel(p.status)}</Badge>
                </td>
                <td className={td}>{p.label ? disease(p.label) : '—'}</td>
                <td className={`${td} num`}>{p.frames}</td>
                <td className={`${td} text-[12px] text-muted`}>{p.cameras.join(', ') || '—'}</td>
              </tr>
            ))}
          </tbody>
        </Table>
      )}
    </Card>
  )
}

function EdgeRecordsCard({ records, loading, error }: { records: EdgeRecord[]; loading: boolean; error: unknown }) {
  const [category, setCategory] = useState('')
  const [plant, setPlant] = useState('')
  const [onlyWithImage, setOnlyWithImage] = useState(false)
  const [limite, setLimite] = useState(PAGINA)
  const [aberto, setAberto] = useState<EdgeRecord | null>(null)
  const contagem = useMemo(() => countByCategory(records), [records])
  const filtrados = useMemo(
    () => filterRecords(records, { category, plant, onlyWithImage }),
    [records, category, plant, onlyWithImage],
  )
  const arquivo = aberto ? viewableFile(aberto) : null

  return (
    <Card className="mt-4 overflow-hidden">
      <CardHeader
        title="Registros da Edge AI"
        subtitle={`${records.length} registro(s) sincronizado(s) pelos robôs nesta missão${records.length >= 1000 ? ' (mostrando os 1000 primeiros)' : ''}.`}
      />
      <div className="print-hide flex flex-wrap items-center gap-3 px-5 pb-4 text-[13px]">
        <select className="input w-56" value={category} onChange={(e) => setCategory(e.target.value)} aria-label="Categoria">
          <option value="">Todas as categorias</option>
          <option value="eventos">Só eventos (doença, praga, anomalia)</option>
          {contagem.map((c) => (
            <option key={c.type} value={c.type}>
              {categoryLabel(c.type)} ({c.count})
            </option>
          ))}
        </select>
        <input className="input w-44" placeholder="Planta (ex.: L1-P006)" value={plant} onChange={(e) => setPlant(e.target.value)} aria-label="Planta" />
        <label className="flex items-center gap-2">
          <input type="checkbox" checked={onlyWithImage} onChange={(e) => setOnlyWithImage(e.target.checked)} className="accent-[var(--accent)]" />
          Só com imagem
        </label>
        <span className="text-muted">{filtrados.length} no filtro</span>
      </div>
      <ErrorBox error={error} className="mx-5 mb-3" />
      {loading && <Spinner />}
      {!loading && !filtrados.length && <Empty title="Nenhum registro com esse filtro" />}
      {!!filtrados.length && (
        <Table>
          <thead>
            <tr>
              <th className={th}>Quando</th>
              <th className={th}>Categoria</th>
              <th className={th}>Planta</th>
              <th className={th}>Câmera</th>
              <th className={th}>Confiança</th>
              <th className={th}>Modelo</th>
              <th className={`${th} print-hide`}>Imagem</th>
            </tr>
          </thead>
          <tbody>
            {filtrados.slice(0, limite).map((r) => {
              const img = viewableFile(r)
              return (
                <tr key={r.id}>
                  <td className={`${td} num text-[12px]`}>{fmt.time(r.occurred_at)}</td>
                  <td className={td}>
                    <Badge tone={r.kind === 'result' ? categoryTone(r.type) : 'neutral'}>
                      {r.kind === 'result' ? categoryLabel(r.type) : r.type}
                    </Badge>
                    {r.label && <span className="ml-2 text-[12px] text-ink-2">{disease(r.label)}</span>}
                  </td>
                  <td className={`${td} num`}>{plantOf(r) ?? '—'}</td>
                  <td className={`${td} text-[12px] text-muted`}>{cameraOf(r) ?? '—'}</td>
                  <td className={`${td} num`}>{r.confidence == null ? '—' : fmt.percent(r.confidence)}</td>
                  <td className={`${td} text-[12px] text-muted`}>{r.model_key ? `${r.model_key}@${r.model_version ?? '?'}` : '—'}</td>
                  <td className={`${td} print-hide`}>
                    {img ? (
                      <Button size="sm" variant="ghost" icon={<ImageIcon className="size-4" />} onClick={() => setAberto(r)}>
                        {img.role === 'original' ? 'Original' : 'Ver'}
                      </Button>
                    ) : (
                      <span className="text-[12px] text-muted">—</span>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </Table>
      )}
      {filtrados.length > limite && (
        <div className="print-hide px-5 py-3">
          <Button size="sm" onClick={() => setLimite((l) => l + PAGINA)}>
            Mostrar mais {Math.min(PAGINA, filtrados.length - limite)}
          </Button>
        </div>
      )}
      <Modal
        open={Boolean(aberto)}
        onClose={() => setAberto(null)}
        title={aberto ? `${categoryLabel(aberto.type)} · ${plantOf(aberto) ?? 'sem planta'}` : ''}
        description={aberto && arquivo ? `Arquivo ${arquivo.role ?? ''} · ${fmt.number(arquivo.size_bytes / 1024, 0)} KB · ${fmt.dateTime(aberto.occurred_at)}` : undefined}
        wide
      >
        {aberto && arquivo && (
          <AuthImage path={fileUrl(aberto, arquivo)} alt={`Imagem ${arquivo.role ?? ''} do registro`} className="max-h-[70vh] w-full rounded-[10px] object-contain" />
        )}
      </Modal>
    </Card>
  )
}
