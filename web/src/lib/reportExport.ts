/**
 * Exportação do relatório da missão (brief, seção 47): CSV e impressão (PDF pelo
 * "Salvar como PDF" do navegador). O conteúdo é o de `GET /v1/missions/{id}/report`
 * e `/plants` — nada é recalculado aqui.
 *
 * CSV com `;` e BOM: é o que o Excel em português abre direto, com acento e sem
 * confundir vírgula decimal com separador.
 */
import type { MissionReport } from './missionReport'

export type ReportPlantRow = {
  plant_id: string
  row: number | null
  status: string
  label: string | null
  frames: number
  cameras: string[]
  lat?: number | null
  lon?: number | null
}

const decimal = (v: number | null | undefined, digits = 4) =>
  v == null || Number.isNaN(v) ? '' : v.toFixed(digits).replace('.', ',')

/**
 * Uma célula de CSV: aspas quando tem separador, aspas ou quebra de linha.
 *
 * Texto que começa com `=`, `+`, `-`, `@`, tabulação ou retorno vira fórmula no Excel
 * (injeção de CSV, Parte 9): o nome da fazenda ou do talhão é digitado pelo cliente.
 * Esse texto ganha um `'` na frente; número (inclusive negativo, com vírgula) não.
 */
export function csvCell(value: unknown): string {
  if (value == null) return ''
  let text = String(value)
  if (typeof value !== 'number' && /^[=+\-@\t\r]/.test(text) && !/^-?\d+([.,]\d+)?$/.test(text)) {
    text = `'${text}`
  }
  return /[;"\n\r]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text
}

export const csvLine = (cells: unknown[]) => cells.map(csvCell).join(';')

/**
 * Duas partes no mesmo arquivo: o resumo (chave; valor) e uma linha por planta.
 * `report` é o JSON da API; `plants` são todas as plantas (o relatório só traz as
 * ocorrências).
 */
export function reportToCsv(report: MissionReport & Record<string, unknown>, plants: ReportPlantRow[]): string {
  const r = report as MissionReport & {
    farm?: string | null
    field?: string | null
    crop?: string | null
    area_ha?: number | null
  }
  const linhas: string[] = [
    csvLine(['Relatório da missão', r.mission_id]),
    csvLine(['Fazenda', r.farm ?? '']),
    csvLine(['Talhão', r.field ?? '']),
    csvLine(['Cultura', r.crop ?? '']),
    csvLine(['Rover', r.rover ?? '']),
    csvLine(['Data', r.date ?? '']),
    csvLine(['Duração (min)', decimal(r.duration_min, 1)]),
    csvLine(['Área do talhão (ha)', decimal(r.area_ha, 2)]),
    csvLine(['Imagens processadas no robô', r.images_processed]),
    csvLine(['Plantas vistas', r.plants_seen]),
    csvLine(['Plantas doentes', r.incidence.diseased]),
    csvLine(['Plantas suspeitas/com o agrônomo', r.incidence.suspect]),
    csvLine(['Incidência', decimal(r.incidence.ratio)]),
    csvLine(['IC 95% (de; até)', decimal(r.incidence.interval_95[0]), decimal(r.incidence.interval_95[1])]),
    ...Object.entries(r.incidence.by_label).map(([label, n]) => csvLine([`Doentes por ${label}`, n])),
    ...Object.entries(r.edge_categories).map(([cat, n]) => csvLine([`Edge AI: ${cat}`, n])),
    ...Object.entries(r.events).map(([ev, n]) => csvLine([`Evento: ${ev}`, n])),
    ...r.recommendations.map((rec) => csvLine(['Recomendação', rec.outcome, rec.rationale ?? ''])),
    ...r.prescriptions.map((p) =>
      csvLine(['Prescrição', p.mission_id, p.state, decimal(p.rate_l_ha, 1), decimal(p.quantity_l, 1)]),
    ),
  ]
  const c = r.comparison_with_previous
  if (c) {
    linhas.push(
      csvLine(['Incidência na passada anterior', decimal(c.incidence_before)]),
      csvLine(['Variação', decimal(c.delta)]),
      csvLine(['Recuperadas', c.recovered.join(' ')]),
      csvLine(['Persistentes', c.persisting.join(' ')]),
      csvLine(['Novas', c.new.join(' ')]),
    )
  }
  linhas.push(csvLine(['Dados simulados', r.simulated ? 'sim' : 'não']))
  linhas.push('')
  linhas.push(csvLine(['planta', 'linha', 'estado', 'doença', 'quadros', 'câmeras', 'latitude', 'longitude']))
  for (const p of plants) {
    linhas.push(
      csvLine([p.plant_id, p.row ?? '', p.status, p.label ?? '', p.frames, p.cameras.join(' '), decimal(p.lat, 7), decimal(p.lon, 7)]),
    )
  }
  return '﻿' + linhas.join('\r\n') + '\r\n'
}

/** Baixa um texto como arquivo (no navegador). */
export function downloadText(filename: string, text: string, type = 'text/csv;charset=utf-8'): void {
  const url = URL.createObjectURL(new Blob([text], { type }))
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

/** `relatorio-talhao-2-2026-10-05.csv` — sem acento nem espaço. */
export function reportFilename(field: string | null | undefined, date: string | null | undefined, ext = 'csv'): string {
  const slug = (field ?? 'missao')
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '')
  return `relatorio-${slug || 'missao'}-${(date ?? '').slice(0, 10) || 'sem-data'}.${ext}`
}
