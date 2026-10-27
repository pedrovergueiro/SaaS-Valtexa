import { describe, expect, it } from 'vitest'

import { modoTexto, quemVence, tomDoErroDeMolhamento } from './gemeo'

describe('gêmeo do talhão', () => {
  it('em observação, o mapa do gêmeo não executa', () => {
    expect(modoTexto('observacao').tom).toBe('warning')
    expect(modoTexto('observacao').explica).toMatch(/não o executa/)
    expect(modoTexto('ativo').rotulo).toBe('ativo')
  })

  it('a maior nota vence (log-verossimilhança: menos negativo é melhor)', () => {
    expect(quemVence({ modelo: -0.1, persistencia: -0.2, prevalencia: -0.4 })).toBe('modelo')
    expect(quemVence({ modelo: -0.3, persistencia: -0.2, prevalencia: -0.4 })).toBe('persistencia')
    expect(quemVence({ modelo: null, persistencia: null, prevalencia: null })).toBeNull()
  })

  it('erro de molhamento grande é o que muda a janela de infecção', () => {
    expect(tomDoErroDeMolhamento(0.5)).toBe('good')
    expect(tomDoErroDeMolhamento(2)).toBe('warning')
    expect(tomDoErroDeMolhamento(4)).toBe('critical')
  })
})
