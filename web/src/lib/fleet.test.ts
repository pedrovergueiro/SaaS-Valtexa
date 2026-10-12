import { describe, expect, it } from 'vitest'

import {
  faultText,
  fleetStateLabel,
  fleetStateTone,
  fleetSummary,
  groupByModel,
  modelInUse,
  modelStatus,
  orNoData,
  storageText,
  storageTone,
  transitionNeedsReason,
} from './fleet'

describe('estado de frota', () => {
  it('rótulos e tons dos sete estados', () => {
    expect(fleetStateLabel('em_missao')).toBe('Em missão')
    expect(fleetStateLabel('bloqueado')).toBe('Bloqueado')
    expect(fleetStateTone('erro')).toBe('serious')
    expect(fleetStateTone('disponivel')).toBe('good')
    expect(fleetStateLabel('estado-novo')).toBe('estado-novo')
  })

  it('resumo conta cada estado, zeros incluídos, na ordem fixa', () => {
    const resumo = fleetSummary([{ fleet_state: 'offline' }, { fleet_state: 'offline' }, { fleet_state: 'erro' }])
    expect(resumo).toHaveLength(7)
    expect(resumo[0]).toEqual({ state: 'disponivel', count: 0 })
    expect(resumo.find((r) => r.state === 'offline')?.count).toBe(2)
    expect(resumo.find((r) => r.state === 'erro')?.count).toBe(1)
  })
})

describe('saúde do robô', () => {
  it('armazenamento em GB, ou sem dado', () => {
    expect(storageText(64e9, 12e9)).toBe('12,0 de 64,0 GB livres (19 %)')
    expect(storageText(null, 1)).toBe('sem dado')
    expect(storageTone(100, 5)).toBe('critical')
    expect(storageTone(100, 20)).toBe('warning')
    expect(storageTone(100, 50)).toBe('good')
  })

  it('falha com código e mensagem, ou texto', () => {
    expect(faultText({ code: 'MOTOR_ESQ', message: 'sobrecorrente' })).toBe('MOTOR_ESQ — sobrecorrente')
    expect(faultText('GNSS')).toBe('GNSS')
  })

  it('modelo em uso e conformidade', () => {
    expect(modelInUse('coffee-foliar', '1.0.0')).toBe('coffee-foliar 1.0.0')
    expect(modelInUse(null, null)).toBe('sem dado')
    expect(modelStatus('fora_do_registry').tone).toBe('critical')
    expect(modelStatus(undefined).label).toBe('Modelo não informado')
  })
})

describe('registry', () => {
  it('voltar no ciclo e descontinuar pedem motivo; avançar não', () => {
    expect(transitionNeedsReason('treinamento', 'validacao')).toBe(false)
    expect(transitionNeedsReason('validacao', 'treinamento')).toBe(true)
    expect(transitionNeedsReason('producao', 'descontinuado')).toBe(true)
    expect(transitionNeedsReason('staging', 'producao')).toBe(false)
  })

  it('agrupa por modelo com a de produção na frente', () => {
    const grupos = groupByModel([
      { model_key: 'b', state: 'treinamento' },
      { model_key: 'a', state: 'staging' },
      { model_key: 'a', state: 'producao' },
    ])
    expect(grupos.map(([k]) => k)).toEqual(['a', 'b'])
    expect(grupos[0]?.[1][0]?.state).toBe('producao')
  })

  it('sem dado nunca vira zero', () => {
    expect(orNoData(null, ' ms')).toBe('sem dado')
    expect(orNoData(12.345, ' ms')).toBe('12,3 ms')
    expect(orNoData(0)).toBe('0')
  })
})
