import { describe, expect, it } from 'vitest'

import {
  boundsPoints,
  changeOf,
  heatCells,
  heatOpacity,
  LAYERS,
  layerAvailable,
  plantColor,
  statusCounts,
  type MapPlant,
  type MissionMap,
} from './mapLayers'

const planta = (id: string, status: MapPlant['status'], lat: number | null, lon: number | null): MapPlant => ({
  plant_id: id,
  row: 1,
  status,
  label: status === 'doente' ? 'Rust' : null,
  frames: 2,
  lat,
  lon,
})

describe('camadas do mapa', () => {
  it('umidade, falhas e produtividade existem como interface, sem dado inventado', () => {
    const semFonte = LAYERS.filter((l) => l.source === null).map((l) => l.id)
    expect(semFonte).toEqual(['umidade', 'falhas', 'produtividade'])
    for (const l of LAYERS.filter((x) => x.source === null)) {
      expect(layerAvailable(l, true)).toBe(false)
      expect(l.unavailable).toBeTruthy()
    }
  })

  it('comparação só com outra passada escolhida', () => {
    const comp = LAYERS.find((l) => l.id === 'comparacao')!
    expect(layerAvailable(comp, false)).toBe(false)
    expect(layerAvailable(comp, true)).toBe(true)
    expect(layerAvailable(LAYERS[0]!, false)).toBe(true)
  })

  it('cor por estado', () => {
    const cores = { good: 'G', warning: 'W', serious: 'S', critical: 'C', info: 'I', neutral: 'N' }
    expect(plantColor('doente', cores)).toBe('C')
    expect(plantColor('sadia', cores)).toBe('G')
    expect(plantColor('suspeita', cores)).toBe('S')
    expect(plantColor('revisar', cores)).toBe('W')
  })

  it('calor: incidência por célula, sem célula onde não há planta', () => {
    const plantas = [
      planta('a', 'doente', -21.9, -45.8),
      planta('b', 'sadia', -21.90001, -45.80001),
      planta('c', 'sadia', -21.9005, -45.8005), // ~70 m: outra célula
      planta('d', 'doente', null, null), // sem posição: fora do mapa
    ]
    const cells = heatCells(plantas, 10)
    expect(cells).toHaveLength(2)
    const comDoente = cells.find((c) => c.diseased === 1)!
    expect(comDoente.plants).toBe(2)
    expect(comDoente.ratio).toBeCloseTo(0.5)
    expect(cells.reduce((s, c) => s + c.plants, 0)).toBe(3)
    expect(heatCells([], 10)).toEqual([])
    expect(heatOpacity(0)).toBeCloseTo(0.12)
    expect(heatOpacity(1)).toBeCloseTo(0.72)
    expect(heatOpacity(7)).toBeCloseTo(0.72)
  })

  it('comparação: recuperada, persistente, nova', () => {
    const comp = { incidence_before: 0.1, incidence_after: 0.05, delta: -0.05, plants_compared: 3, recovered: ['a'], persisting: ['b'], new: ['c'] }
    expect(changeOf('a', comp)).toBe('recuperada')
    expect(changeOf('b', comp)).toBe('persistente')
    expect(changeOf('c', comp)).toBe('nova')
    expect(changeOf('d', comp)).toBe('sem_mudanca')
    expect(changeOf('a', null)).toBe('sem_mudanca')
  })

  it('enquadramento junta plantas, eventos e rota em [lat, lon]', () => {
    const mapa = {
      plants: [planta('a', 'sadia', -21.9, -45.8), planta('x', 'sadia', null, null)],
      events: [{ lat: -21.91, lon: -45.81 }],
      track: [[-45.82, -21.92]],
    } as unknown as MissionMap
    expect(boundsPoints(mapa)).toEqual([
      [-21.9, -45.8],
      [-21.91, -45.81],
      [-21.92, -45.82],
    ])
    expect(boundsPoints(null)).toEqual([])
    expect(statusCounts(mapa.plants)).toEqual({ doente: 0, suspeita: 0, revisar: 0, sadia: 2 })
  })
})
