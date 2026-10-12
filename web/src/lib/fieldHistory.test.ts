import { describe, expect, it } from 'vitest'

import { cycleClosed, describe as descreve, stageCounts, stageLabel, stepLink, type HistoryStep } from './fieldHistory'

const passos: HistoryStep[] = [
  { stage: 'verificacao', at: '2026-10-05T12:00:00Z', conclusion: 'improved', before_ratio: 0.33, after_ratio: 0, application_id: 'a' },
  { stage: 'aplicacao', at: '2026-10-05T10:00:00Z', state: 'completed', amount_used_l: 28, area_ha: 0.25, mission_id: 's' },
  { stage: 'aprovacao', at: '2026-10-05T09:00:00Z', mission_id: 's' },
  { stage: 'prescricao', at: '2026-10-05T08:00:00Z', mission_id: 's', rate_l_ha: 120, quantity_l: 30, origin_mission_id: 'v' },
  { stage: 'ocorrencias', at: '2026-10-05T07:00:00Z', mission_id: 'v', diseased: 1, suspect: 0, plants_seen: 3, incidence: 0.3333 },
  { stage: 'missao', at: '2026-10-05T06:30:00Z', mission_id: 'v', title: 'Varredura' },
]

describe('linha do tempo do talhão', () => {
  it('frases em linguagem do produtor', () => {
    expect(stageLabel('prescricao')).toBe('Prescrição')
    expect(descreve(passos[4]!)).toBe('1 doente(s) e 0 suspeita(s) em 3 plantas — incidência 33,3%')
    expect(descreve(passos[3]!)).toBe('Pulverização prescrita · 120 L/ha · 30 L a partir da varredura')
    expect(descreve(passos[1]!)).toBe('Aplicação concluída · 28 L · 0,25 ha')
    expect(descreve(passos[0]!)).toBe('Verificação: melhorou · antes 33,0% · depois 0,0%')
  })

  it('links e contagens', () => {
    expect(stepLink(passos[1]!)).toBe('/aplicacoes')
    expect(stepLink(passos[5]!)).toBe('/missoes/v')
    expect(stageCounts(passos)).toEqual({ missao: 1, ocorrencias: 1, prescricao: 1, aprovacao: 1, aplicacao: 1, verificacao: 1 })
  })

  it('ciclo fechado só com verificação depois da última ocorrência', () => {
    expect(cycleClosed(passos)).toBe(true)
    expect(cycleClosed(passos.slice(1))).toBe(false)
    expect(cycleClosed([])).toBe(false)
  })
})
