import { describe, expect, it } from 'vitest'

import type { MissionReport } from './missionReport'
import { csvCell, reportFilename, reportToCsv } from './reportExport'

const relatorio = {
  mission_id: 'm1',
  farm: 'Fazenda Boa Vista',
  field: 'Talhão 2; norte',
  crop: 'banana',
  area_ha: 1.5,
  rover: 'RV-1',
  date: '2026-10-05T10:00:00+00:00',
  duration_min: 32.5,
  images_processed: 140,
  events: { MISSION_STARTED: 1 },
  edge_categories: { NORMAL: 132, POSSIVEL_DOENCA: 8 },
  occurrences: [],
  plants_seen: 54,
  incidence: { diseased: 4, suspect: 1, ratio: 0.0741, interval_95: [0.029, 0.176], by_label: { Rust: 4 } },
  recommendations: [{ decision_id: 'd', outcome: 'application_candidate', rationale: 'diz "aplicar"' }],
  prescriptions: [{ mission_id: 's', state: 'completed', rate_l_ha: 120, quantity_l: 30.5 }],
  comparison_with_previous: null,
  simulated: true,
} as unknown as MissionReport & Record<string, unknown>

describe('exportação do relatório', () => {
  it('célula com separador ou aspas vai entre aspas', () => {
    expect(csvCell('simples')).toBe('simples')
    expect(csvCell('a;b')).toBe('"a;b"')
    expect(csvCell('diz "x"')).toBe('"diz ""x"""')
    expect(csvCell(null)).toBe('')
  })

  it('neutraliza fórmula (injeção de CSV) sem estragar número negativo', () => {
    expect(csvCell('=HYPERLINK("http://x")')).toBe('"\'=HYPERLINK(""http://x"")"')
    expect(csvCell('@SUM(A1)')).toBe("'@SUM(A1)")
    expect(csvCell('+55 11')).toBe("'+55 11")
    expect(csvCell('-21,9000')).toBe('-21,9000')
    expect(csvCell(-45.8)).toBe('-45.8')
  })

  it('CSV com BOM, ; e vírgula decimal, resumo e uma linha por planta', () => {
    const csv = reportToCsv(relatorio, [
      { plant_id: 'L1-P006', row: 1, status: 'doente', label: 'Rust', frames: 3, cameras: ['cam-0', 'cam-1'], lat: -21.9, lon: -45.8 },
      { plant_id: 'L1-P007', row: 1, status: 'sadia', label: null, frames: 2, cameras: ['cam-0'] },
    ])
    expect(csv.startsWith('﻿')).toBe(true)
    const linhas = csv.slice(1).split('\r\n')
    expect(linhas).toContain('Talhão;"Talhão 2; norte"')
    expect(linhas).toContain('Incidência;0,0741')
    expect(linhas).toContain('Doentes por Rust;4')
    expect(linhas).toContain('Recomendação;application_candidate;"diz ""aplicar"""')
    expect(linhas).toContain('Prescrição;s;completed;120,0;30,5')
    expect(linhas).toContain('Dados simulados;sim')
    expect(linhas).toContain('L1-P006;1;doente;Rust;3;cam-0 cam-1;-21,9000000;-45,8000000')
    expect(linhas).toContain('L1-P007;1;sadia;;2;cam-0;;')
  })

  it('nome do arquivo sem acento', () => {
    expect(reportFilename('Talhão Café 2', '2026-10-05T10:00:00Z')).toBe('relatorio-talhao-cafe-2-2026-10-05.csv')
    expect(reportFilename(null, null, 'pdf')).toBe('relatorio-missao-sem-data.pdf')
  })
})
