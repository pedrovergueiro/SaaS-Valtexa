import { describe, expect, it } from 'vitest'

import { cameraOf, categoryLabel, countByCategory, fileUrl, filterRecords, plantOf, viewableFile, type EdgeRecord } from './edgeRecords'

const arquivo = (role: string, status = 'complete') => ({
  upload_id: `up-${role}`,
  role,
  sha256: 'a'.repeat(64),
  size_bytes: 10,
  content_type: 'image/jpeg',
  status,
  asset_id: 'x',
})

const reg = (id: string, type: string, plant: string | null, files = [] as ReturnType<typeof arquivo>[]): EdgeRecord => ({
  id,
  record_id: id,
  device_id: 'd',
  kind: 'result',
  type,
  mission_id: 'm',
  field_id: 'f',
  occurred_at: '2026-10-05T10:00:00Z',
  received_at: '2026-10-05T10:00:01Z',
  severity: null,
  label: null,
  confidence: 0.9,
  model_key: 'k',
  model_version: '1',
  lat: null,
  lon: null,
  payload: plant ? { region: { plant_id: plant }, frame: { camera_id: 'cam-1' } } : {},
  files,
})

describe('registros da Edge AI', () => {
  it('planta, câmera e categoria', () => {
    expect(plantOf(reg('1', 'NORMAL', 'L1-P003'))).toBe('L1-P003')
    expect(plantOf(reg('1', 'NORMAL', null))).toBeNull()
    expect(cameraOf(reg('1', 'NORMAL', 'L1'))).toBe('cam-1')
    expect(categoryLabel('POSSIVEL_DOENCA')).toBe('Possível doença')
    expect(categoryLabel('ALGO_NOVO')).toBe('algo novo')
  })

  it('imagem: o original primeiro, só o que terminou de subir', () => {
    expect(viewableFile(reg('1', 'X', null, [arquivo('reduzida'), arquivo('original')]))?.role).toBe('original')
    expect(viewableFile(reg('1', 'X', null, [arquivo('original', 'receiving'), arquivo('reduzida')]))?.role).toBe('reduzida')
    expect(viewableFile(reg('1', 'X', null, []))).toBeNull()
    expect(fileUrl({ id: 'r1' }, { upload_id: 'up 1' })).toBe('/v1/edge/records/r1/files/up%201')
  })

  it('contagem e filtro por categoria, planta e imagem', () => {
    const lista = [
      reg('1', 'NORMAL', 'L1-P001'),
      reg('2', 'POSSIVEL_DOENCA', 'L1-P002', [arquivo('original')]),
      reg('3', 'POSSIVEL_PRAGA', 'L2-P001'),
      reg('4', 'NORMAL', 'L2-P002'),
    ]
    expect(countByCategory(lista)).toEqual([
      { type: 'POSSIVEL_DOENCA', count: 1 },
      { type: 'POSSIVEL_PRAGA', count: 1 },
      { type: 'NORMAL', count: 2 },
    ])
    const ids = (f: Parameters<typeof filterRecords>[1]) => filterRecords(lista, f).map((r) => r.id)
    expect(ids({ category: '', plant: '', onlyWithImage: false })).toEqual(['1', '2', '3', '4'])
    expect(ids({ category: 'eventos', plant: '', onlyWithImage: false })).toEqual(['2', '3'])
    expect(ids({ category: 'NORMAL', plant: 'l2', onlyWithImage: false })).toEqual(['4'])
    expect(ids({ category: '', plant: '', onlyWithImage: true })).toEqual(['2'])
  })
})
