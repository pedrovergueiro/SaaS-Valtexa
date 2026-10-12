import { describe, expect, it } from 'vitest'

import { otaKindLabel, otaResumo, otaStateLabel, otaStateTone, podeCancelar } from './ota'

describe('OTA no console', () => {
  it('rótulos e tons', () => {
    expect(otaStateLabel('verificando_saude')).toBe('Em teste')
    expect(otaStateTone('revertida')).toBe('critical')
    expect(otaStateTone('aplicada')).toBe('good')
    expect(otaKindLabel('edge_ai')).toBe('Edge AI')
  })

  it('cancelar só antes de instalar', () => {
    expect(podeCancelar('pendente')).toBe(true)
    expect(podeCancelar('baixando')).toBe(true)
    expect(podeCancelar('instalando')).toBe(false)
    expect(podeCancelar('aplicada')).toBe(false)
  })

  it('resumo do lote', () => {
    expect(otaResumo(['aplicada', 'aplicada', 'baixando', 'revertida', 'cancelada', 'pendente'])).toEqual({
      aplicadas: 2,
      emCurso: 2,
      problemas: 1,
    })
  })
})
