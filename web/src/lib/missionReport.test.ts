import { describe, expect, it } from 'vitest'

import { incidenceText, outcomeLabel, plantStatusLabel, plantStatusTone, sortOccurrences, trend, type ReportPlant } from './missionReport'

const planta = (plant_id: string, status: ReportPlant['status'], row = 1): ReportPlant => ({
  plant_id,
  row,
  status,
  label: null,
  frames: 2,
  cameras: ['cam-0'],
})

describe('resultado da missão', () => {
  it('doentes primeiro, depois pela ordem do campo', () => {
    const ordem = sortOccurrences([
      planta('L1-P010', 'suspeita'),
      planta('L2-P002', 'doente', 2),
      planta('L1-P002', 'doente'),
      planta('L1-P009', 'revisar'),
    ]).map((p) => p.plant_id)
    expect(ordem).toEqual(['L1-P002', 'L2-P002', 'L1-P009', 'L1-P010'])
  })

  it('incidência em linguagem operacional, com o intervalo', () => {
    expect(
      incidenceText({
        plants_seen: 54,
        incidence: { diseased: 3, suspect: 0, ratio: 0.0556, interval_95: [0.0191, 0.151], by_label: {} },
      }),
    ).toBe('3 de 54 plantas (5,6%; entre 1,9% e 15,1%)')
    expect(incidenceText({ plants_seen: 0, incidence: { diseased: 0, suspect: 0, ratio: null, interval_95: [0, 0], by_label: {} } })).toBe(
      'nenhuma planta vista',
    )
  })

  it('tendência: queda é boa notícia, alta é alerta', () => {
    expect(trend(-0.0556)).toEqual({ text: 'caiu 5,6%', tone: 'good' })
    expect(trend(0.02).tone).toBe('critical')
    expect(trend(null).text).toBe('sem passada anterior')
    expect(trend(0).text).toBe('estável')
  })

  it('rótulos', () => {
    expect(plantStatusLabel('revisar')).toBe('Com o agrônomo')
    expect(plantStatusTone('doente')).toBe('critical')
    expect(outcomeLabel('application_candidate')).toBe('Candidata a aplicação')
    expect(outcomeLabel('desconhecido')).toBe('desconhecido')
  })
})
