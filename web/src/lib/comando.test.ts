import { describe, expect, it } from 'vitest'

import {
  commandSummary,
  isMoving,
  joystickToSetpoint,
  keysToAxes,
  latestPhotos,
  modeInfo,
  partsFromReport,
} from './comando'

const LIM = { v_ms: 0.5, w_rad_s: 1.0 }

describe('controle remoto', () => {
  it('joystick vira velocidade dentro do limite, com zona morta', () => {
    expect(joystickToSetpoint(0, 1, LIM)).toEqual({ v: 0.5, w: 0 })
    expect(joystickToSetpoint(1, 0, LIM)).toEqual({ v: 0, w: -1 }) // direita = giro negativo
    expect(joystickToSetpoint(0.05, 0.05, LIM)).toEqual({ v: 0, w: 0 })
    expect(joystickToSetpoint(0, 3, LIM)).toEqual({ v: 0.5, w: 0 }) // nunca passa do limite
    expect(joystickToSetpoint(0, 1, LIM, 0.4)).toEqual({ v: 0.2, w: 0 })
  })

  it('teclas', () => {
    expect(keysToAxes(new Set(['w', 'a']))).toEqual({ x: -1, y: 1 })
    expect(keysToAxes(new Set(['arrowdown', 'arrowright']))).toEqual({ x: 1, y: -1 })
    expect(keysToAxes(new Set(['w', 's']))).toEqual({ x: 0, y: 0 })
    expect(isMoving({ v: 0, w: 0 })).toBe(false)
  })
})

describe('painel', () => {
  it('modo e resumo de comando', () => {
    expect(modeInfo('autonomo').label).toBe('Autônomo')
    expect(modeInfo(null).tone).toBe('neutral')
    expect(commandSummary('diagnostico', {})).toBe('todas as peças')
    expect(commandSummary('diagnostico', { pecas: ['gnss', 'imu'] })).toBe('gnss, imu')
    expect(commandSummary('config', { rover_json: { retencao: {} } })).toBe('retencao')
  })

  it('peças do laudo, com as que falharam primeiro e sem a foto no detalhe', () => {
    const linhas = partsFromReport({
      pecas: {
        gnss: { ok: true, fix: 'fixed' },
        'camera:esq-450': { ok: false, erro: 'sem resposta' },
        'camera:esq-1000': { ok: true, jpeg_base64: 'xx', px: [10, 10] },
      },
    })
    expect(linhas.map((l) => l.nome)).toEqual(['camera:esq-450', 'camera:esq-1000', 'gnss'])
    expect(linhas[0]?.label).toBe('Câmera esq-450')
    expect(linhas[1]?.detalhe).toEqual({ px: [10, 10] })
  })

  it('última foto de cada câmera', () => {
    const fotos = latestPhotos([
      { kind: 'foto', state: 'concluido', finished_at: '2', result: { camera_id: 'esq-450', jpeg_base64: 'NOVA' } },
      { kind: 'diagnostico', state: 'concluido', finished_at: '1', result: { pecas: { 'camera:esq-450': { ok: true, jpeg_base64: 'VELHA' }, 'camera:dir-450': { ok: true, jpeg_base64: 'D' } } } },
      { kind: 'foto', state: 'falhou', finished_at: '3', result: null },
    ])
    expect(fotos['esq-450']?.src).toBe('data:image/jpeg;base64,NOVA')
    expect(Object.keys(fotos).sort()).toEqual(['dir-450', 'esq-450'])
  })
})
